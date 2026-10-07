using System.Buffers.Binary;
using System.Net.Sockets;
using System.Text;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;
using Xp.Portal.Data;

namespace Xp.Portal.Files;

public enum ScanVerdict { Clean, Infected, Error }

/// <summary>clamd INSTREAM: the file goes over the socket in chunks, clamd answers "stream: OK" or "... FOUND".</summary>
public sealed class ClamdScanner(IOptions<AttachmentOptions> options)
{
    public bool Configured => !string.IsNullOrWhiteSpace(options.Value.ClamdAddress);

    public async Task<(ScanVerdict verdict, string detail)> ScanAsync(Stream file, CancellationToken ct)
    {
        var parts = options.Value.ClamdAddress.Split(':');
        using var tcp = new TcpClient();
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(ct);
        timeout.CancelAfter(TimeSpan.FromMinutes(2));
        try
        {
            await tcp.ConnectAsync(parts[0], parts.Length > 1 ? int.Parse(parts[1]) : 3310, timeout.Token);
            await using var s = tcp.GetStream();
            await s.WriteAsync("zINSTREAM\0"u8.ToArray(), timeout.Token);
            var buf = new byte[64 * 1024];
            var len = new byte[4];
            int n;
            while ((n = await file.ReadAsync(buf, timeout.Token)) > 0)
            {
                BinaryPrimitives.WriteUInt32BigEndian(len, (uint)n);
                await s.WriteAsync(len, timeout.Token);
                await s.WriteAsync(buf.AsMemory(0, n), timeout.Token);
            }
            BinaryPrimitives.WriteUInt32BigEndian(len, 0);
            await s.WriteAsync(len, timeout.Token);
            using var reader = new StreamReader(s, Encoding.ASCII);
            var answer = (await reader.ReadToEndAsync(timeout.Token)).TrimEnd('\0', '\n', ' ');
            if (answer.EndsWith("OK", StringComparison.Ordinal)) return (ScanVerdict.Clean, answer);
            if (answer.EndsWith("FOUND", StringComparison.Ordinal)) return (ScanVerdict.Infected, answer);
            return (ScanVerdict.Error, answer);
        }
        catch (Exception e) when (e is SocketException or IOException or OperationCanceledException && !ct.IsCancellationRequested)
        {
            return (ScanVerdict.Error, e.GetType().Name);
        }
    }
}

/// <summary>Scans pending attachments. Infected files go to quarantine: kept for the record, never downloadable.</summary>
public sealed class ScanWorker(IServiceScopeFactory scopes, ClamdScanner scanner, ObjectStore store, ILogger<ScanWorker> log) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stop)
    {
        while (!stop.IsCancellationRequested)
        {
            try { await PassAsync(stop); }
            catch (Exception e) when (e is not OperationCanceledException) { log.LogError(e, "scan pass failed"); }
            try { await Task.Delay(TimeSpan.FromSeconds(10), stop); }
            catch (OperationCanceledException) { return; }
        }
    }

    internal async Task<int> PassAsync(CancellationToken ct)
    {
        using var scope = scopes.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<PortalDb>();
        var pending = await db.TicketAttachments.Where(a => a.Scan == ScanStatus.Pending).OrderBy(a => a.CreatedAt).Take(20).ToListAsync(ct);
        foreach (var a in pending)
        {
            if (!scanner.Configured)
            {
                a.Scan = ScanStatus.Unscanned;
                continue;
            }
            await using var f = store.OpenRead(a.ObjectKey);
            var (verdict, detail) = await scanner.ScanAsync(f, ct);
            if (verdict == ScanVerdict.Error) { log.LogWarning("clamd: {Detail}, attachment {Id} stays pending", detail, a.Id); break; }
            a.Scan = verdict == ScanVerdict.Clean ? ScanStatus.Clean : ScanStatus.Quarantined;
            a.ScanDetail = detail.Length > 250 ? detail[..250] : detail;
            if (verdict == ScanVerdict.Infected) log.LogWarning("attachment {Id} quarantined: {Detail}", a.Id, detail);
        }
        await db.SaveChangesAsync(ct);
        return pending.Count;
    }
}
