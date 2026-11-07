using System.Net;

namespace Xp.ReleaseBuilder;

/// <summary>
/// Development-only static server for a release repository, with HTTP Range support so that
/// download resume can be tried by hand. Production serves the same tree with nginx or a CDN.
/// Listens on localhost only.
/// </summary>
public static class DevServer
{
    public static async Task RunAsync(string repoRoot, int port, CancellationToken ct)
    {
        var root = Path.GetFullPath(repoRoot);
        using var listener = new HttpListener();
        listener.Prefixes.Add($"http://localhost:{port}/");
        listener.Start();
        Console.WriteLine($"serving {root} at http://localhost:{port}/ (Ctrl+C to stop)");
        using var reg = ct.Register(listener.Stop);
        while (!ct.IsCancellationRequested)
        {
            HttpListenerContext ctx;
            try { ctx = await listener.GetContextAsync(); }
            catch (HttpListenerException) when (ct.IsCancellationRequested) { break; }
            catch (ObjectDisposedException) { break; }
            _ = Task.Run(() => Serve(root, ctx));
        }
    }

    static async Task Serve(string root, HttpListenerContext ctx)
    {
        var resp = ctx.Response;
        try
        {
            var key = Uri.UnescapeDataString(ctx.Request.Url!.AbsolutePath.TrimStart('/'));
            string path;
            try { path = Xp.Manifest.SafePath.Resolve(root, key); }
            catch (Xp.Manifest.UnsafePathException) { resp.StatusCode = 400; return; }
            if (ctx.Request.HttpMethod != "GET" || !File.Exists(path) || path.EndsWith(".key", StringComparison.OrdinalIgnoreCase))
            {
                resp.StatusCode = 404;
                return;
            }
            await using var fs = File.OpenRead(path);
            long from = 0;
            var range = ctx.Request.Headers["Range"];
            if (range is not null && range.StartsWith("bytes=") && range.EndsWith('-')
                && long.TryParse(range.AsSpan(6, range.Length - 7), out var r) && r < fs.Length)
            {
                from = r;
                resp.StatusCode = 206;
                resp.AddHeader("Content-Range", $"bytes {from}-{fs.Length - 1}/{fs.Length}");
            }
            resp.AddHeader("Accept-Ranges", "bytes");
            resp.ContentLength64 = fs.Length - from;
            fs.Seek(from, SeekOrigin.Begin);
            await fs.CopyToAsync(resp.OutputStream);
            Console.WriteLine($"{resp.StatusCode} {key}{(from > 0 ? $" from {from}" : "")}");
        }
        catch (Exception e) when (e is IOException or HttpListenerException)
        {
            Console.WriteLine($"client gone: {e.Message}");
        }
        finally
        {
            try { resp.Close(); } catch (HttpListenerException) { }
        }
    }
}
