using System.Diagnostics;
using System.Net;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using Xp.Manifest;

namespace Xp.Launcher.Core;

public sealed record LatestRelease(ChannelPointer Pointer, ReleaseManifest Manifest);

/// <summary>Thrown when something from the server fails verification. Never retried silently.</summary>
public sealed class TrustException(string message) : Exception(message);

/// <summary>
/// Talks to the static release repository. Trust comes only from signatures checked here,
/// never from HTTPS alone: pointer signature -> manifest hash and signature -> file hashes.
/// </summary>
public sealed class RepoClient(HttpClient http, Uri baseUri, TrustedKeys keys)
{
    const int MaxPointerBytes = 64 * 1024;
    const int MaxSigBytes = 4 * 1024;
    const int MaxManifestBytes = 128 * 1024 * 1024;

    public Uri BaseUri { get; } = baseUri.AbsoluteUri.EndsWith('/') ? baseUri : new Uri(baseUri.AbsoluteUri + "/");

    /// <summary>
    /// The client every download goes through. A release is 38 791 files of 54 KB on average, so
    /// what it costs is not the bytes but the requests. Measured against the live station on a
    /// sample of 1000 blobs: HTTP/1.1 over four connections 10.9 MB/s, HTTP/2 over one 25.2 MB/s —
    /// the speed of a single large file in a single stream (29.5 MB/s), which is the ceiling of the
    /// link itself. HTTP/2 carries the requests over one socket, so it is also gentler on the
    /// station than sixteen sockets would be; a server that cannot speak it falls back to 1.1.
    /// </summary>
    public static HttpClient NewHttpClient() => new(new SocketsHttpHandler
    {
        // matters on the fallback path only: without multiplexing every request in flight wants its own socket
        MaxConnectionsPerServer = 8,
        PooledConnectionLifetime = TimeSpan.FromMinutes(5),
    })
    {
        DefaultRequestVersion = HttpVersion.Version20,
        DefaultVersionPolicy = HttpVersionPolicy.RequestVersionOrLower,
        Timeout = Timeout.InfiniteTimeSpan,
    };

    Uri Url(string key) => new(BaseUri, key);

    /// <summary>
    /// Latest verified release of a channel. <paramref name="minSequence"/> is the highest sequence
    /// seen before: a lower one is a replayed old pointer and is refused.
    /// </summary>
    public async Task<LatestRelease> GetLatestAsync(string channel, long minSequence, CancellationToken ct)
    {
        if (!ManifestValidator.IsValidId(channel)) throw new ArgumentException("bad channel name");
        var key = BlobKeys.Channel(channel);
        var pBytes = await GetSmallAsync(key, MaxPointerBytes, ct);
        var pSig = await GetSmallAsync(BlobKeys.Sig(key), MaxSigBytes, ct);
        if (!keys.Verify(pBytes, pSig)) throw new TrustException($"channel '{channel}': signature check failed");
        var pointer = ManifestValidator.ParsePointer(pBytes);
        if (pointer.Channel != channel) throw new TrustException("channel pointer names another channel");
        if (pointer.Sequence < minSequence)
            throw new TrustException($"channel '{channel}': server offers sequence {pointer.Sequence}, already seen {minSequence} (replayed old release)");
        if (pointer.ManifestSize > MaxManifestBytes) throw new TrustException("manifest too large");

        var mKey = BlobKeys.Manifest(pointer.ReleaseId);
        var mBytes = await GetSmallAsync(mKey, (int)pointer.ManifestSize, ct);
        if (mBytes.Length != pointer.ManifestSize || Hashing.Sha256Hex(mBytes) != pointer.ManifestSha256)
            throw new TrustException("manifest does not match the channel pointer");
        var mSig = await GetSmallAsync(BlobKeys.Sig(mKey), MaxSigBytes, ct);
        if (!keys.Verify(mBytes, mSig)) throw new TrustException("manifest: signature check failed");

        ReleaseManifest manifest;
        try { manifest = ManifestValidator.Parse(mBytes); }
        catch (ManifestException e) { throw new TrustException("manifest rejected: " + e.Message); }
        if (manifest.Release.Id != pointer.ReleaseId || manifest.Release.Channel != channel)
            throw new TrustException("manifest does not belong to this channel pointer");
        return new LatestRelease(pointer, manifest);
    }

    async Task<byte[]> GetSmallAsync(string key, int limit, CancellationToken ct)
    {
        using var resp = await http.GetAsync(Url(key), HttpCompletionOption.ResponseHeadersRead, ct);
        if (resp.StatusCode == HttpStatusCode.NotFound) throw new FileNotFoundException($"not on server: {key}");
        resp.EnsureSuccessStatusCode();
        if (resp.Content.Headers.ContentLength > limit) throw new TrustException($"{key}: larger than allowed");
        await using var s = await resp.Content.ReadAsStreamAsync(ct);
        using var ms = new MemoryStream();
        var buf = new byte[81920];
        int n;
        while ((n = await s.ReadAsync(buf, ct)) > 0)
        {
            if (ms.Length + n > limit) throw new TrustException($"{key}: larger than allowed");
            ms.Write(buf, 0, n);
        }
        return ms.ToArray();
    }

    /// <summary>
    /// Downloads one blob to &lt;target&gt;, resuming &lt;target&gt;.part if a previous attempt broke off.
    /// The file appears under its final name only after its size and SHA-256 matched.
    /// </summary>
    public async Task DownloadBlobAsync(string sha256, long size, string target, Action<long> onBytes, CancellationToken ct)
    {
        if (!Hashing.IsSha256Hex(sha256)) throw new TrustException("bad blob hash");
        var part = target + ".part";
        Directory.CreateDirectory(Path.GetDirectoryName(target)!);
        long have = File.Exists(part) ? new FileInfo(part).Length : 0;
        if (have > size) { File.Delete(part); have = 0; }

        if (have < size)
        {
            using var req = new HttpRequestMessage(HttpMethod.Get, Url(BlobKeys.For(sha256)));
            if (have > 0) req.Headers.Range = new RangeHeaderValue(have, null);
            using var resp = await http.SendAsync(req, HttpCompletionOption.ResponseHeadersRead, ct);
            if (resp.StatusCode == HttpStatusCode.NotFound) throw new FileNotFoundException($"blob {sha256} not on server");
            resp.EnsureSuccessStatusCode();
            bool resumed = have > 0 && resp.StatusCode == HttpStatusCode.PartialContent;
            if (!resumed && have > 0)
            {
                // server ignored the range: start over rather than append a second copy
                onBytes(-have);
                have = 0;
            }
            await using var input = await resp.Content.ReadAsStreamAsync(ct);
            await using (var output = new FileStream(part, resumed ? FileMode.Append : FileMode.Create, FileAccess.Write, FileShare.None, 1 << 16, true))
            {
                var buf = new byte[1 << 16];
                int n;
                while ((n = await input.ReadAsync(buf, ct)) > 0)
                {
                    if (have + n > size) throw new TrustException($"blob {sha256[..12]}: server sent more than the manifest size");
                    await output.WriteAsync(buf.AsMemory(0, n), ct);
                    have += n;
                    onBytes(n);
                }
            }
            if (have != size) throw new IOException($"blob {sha256[..12]}: connection closed at {have} of {size} bytes");
        }

        var actual = await Hashing.FileSha256Async(part, ct);
        if (actual != sha256)
        {
            File.Delete(part);
            onBytes(-size);
            throw new TrustException($"blob {sha256[..12]}: SHA-256 mismatch, file discarded");
        }
        File.Move(part, target, overwrite: true);
    }
}

/// <summary>Speed over a sliding window, for the progress line.</summary>
public sealed class SpeedMeter
{
    readonly Stopwatch _sw = Stopwatch.StartNew();
    readonly Queue<(double T, long Bytes)> _window = new();
    long _total;

    public void Add(long bytes)
    {
        lock (_window)
        {
            _total += bytes;
            var t = _sw.Elapsed.TotalSeconds;
            _window.Enqueue((t, _total));
            while (_window.Count > 2 && t - _window.Peek().T > 3) _window.Dequeue();
        }
    }

    public double BytesPerSecond
    {
        get
        {
            lock (_window)
            {
                if (_window.Count < 2) return 0;
                var first = _window.Peek();
                var dt = _sw.Elapsed.TotalSeconds - first.T;
                return dt <= 0 ? 0 : Math.Max(0, (_total - first.Bytes) / dt);
            }
        }
    }
}

internal static class RandomId
{
    public static string New() => Convert.ToHexStringLower(RandomNumberGenerator.GetBytes(8));
}
