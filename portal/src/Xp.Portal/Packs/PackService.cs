using System.Collections.Concurrent;
using System.Text;
using System.Text.Json;
using Microsoft.Extensions.Options;
using Xp.Manifest;

namespace Xp.Portal.Packs;

public sealed class PackOptions
{
    public const string Section = "Packs";

    /// <summary>The release repository on disk (the tree Caddy serves at /releases/). Empty: no packs on request.</summary>
    public string ReleaseDir { get; set; } = "";
    /// <summary>Where the packs go; Caddy serves it at /releases/lazy/.</summary>
    public string CacheDir { get; set; } = "";
    /// <summary>The channels whose releases are packed on request.</summary>
    public string[] Channels { get; set; } = ["stable"];
    /// <summary>The cache never grows past this; the packs asked for longest ago go first.</summary>
    public double CacheMaxGb { get; set; } = 30;
    /// <summary>Brotli quality 0-11. The release builder packs at 9; here a player may be waiting, and PNG does not shrink anyway.</summary>
    public int Quality { get; set; } = 4;
    /// <summary>Packs waiting or building at once; past it a request is turned away and the launcher fetches file by file.</summary>
    public int MaxQueued { get; set; } = 4;
}

/// <summary>What a launcher asks for: its release, the one it updates to and the art layers it installs. <c>From</c> empty: a first install.</summary>
public sealed record PackRequest(string? Channel, string? To, string? From, string[]? Art);

/// <summary>A pack ready at releases/lazy/&lt;to&gt;/&lt;key&gt;.tar.br: its size and SHA-256, the blobs inside and their size unpacked.</summary>
public sealed record PackOffer(string Key, long Size, string Sha256, int Blobs, long Raw);

/// <summary>The pack is being made: ask again in this many seconds.</summary>
public sealed record PackPending(int RetryAfter);

public enum PackState { Ready, Building, Empty, Busy, NotFound }

public sealed record PackAnswer(PackState State, PackOffer? Offer = null);

/// <summary>
/// The update from any published release in one file, made on request and kept. The release builder packs the
/// update from its last three releases only; a player further behind got tens of thousands of files one by one.
/// The pack is the same tar + brotli of blobs named by their hash (<see cref="PackWriter"/>), and the launcher
/// checks every blob in it against the signed manifest, so the pack itself needs no signature.
/// </summary>
public sealed class PackService(IOptions<PackOptions> options, ILogger<PackService> log, TimeProvider clock)
{
    public const int RetryAfterSeconds = 5;
    const int MaxArt = 8;

    readonly PackOptions _o = options.Value;
    readonly ConcurrentDictionary<string, Task> _building = new(StringComparer.Ordinal);
    readonly ConcurrentDictionary<string, ReleaseManifest> _manifests = new(StringComparer.Ordinal);
    readonly SemaphoreSlim _gate = new(1, 1);
    int _swept;

    public bool Enabled => _o.ReleaseDir.Length > 0 && _o.CacheDir.Length > 0;

    /// <summary>Releases and channels are checked against the repository; a malformed request is an <see cref="ArgumentException"/>.</summary>
    public PackAnswer Ask(PackRequest r)
    {
        var channel = r.Channel ?? "";
        var to = r.To ?? "";
        var from = r.From ?? "";
        if (!ManifestValidator.IsValidId(channel) || !ManifestValidator.IsValidId(to) || from.Length > 0 && !ManifestValidator.IsValidId(from))
            throw new ArgumentException("bad channel or release id");
        var art = (r.Art ?? []).Distinct(StringComparer.Ordinal).Order(StringComparer.Ordinal).ToArray();
        if (art.Length > MaxArt || art.Any(a => !ManifestValidator.IsValidId(a))) throw new ArgumentException("bad art list");
        if (from == to) throw new ArgumentException("nothing to update");
        if (Interlocked.Exchange(ref _swept, 1) == 0) DropLeftovers();

        var key = Key(to, from, art);
        if (Ready(to, key) is { } ready) return ready;
        if (_building.ContainsKey(key)) return new PackAnswer(PackState.Building);

        if (!_o.Channels.Contains(channel, StringComparer.Ordinal) || Targets(channel) is not { } targets || !targets.Contains(to)
            || from.Length > 0 && !Published(channel).Contains(from))
            return new PackAnswer(PackState.NotFound);
        var target = Manifest(to);
        var arts = target.Components.Where(c => c.Kind == ComponentKind.Art).Select(c => c.Id).ToHashSet(StringComparer.Ordinal);
        if (!art.All(arts.Contains)) throw new ArgumentException("art layer not in the release");

        if (_building.Count >= _o.MaxQueued) return new PackAnswer(PackState.Busy);
        // two requests for one pack at the same moment: one build, the other only waits for it
        var done = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        if (_building.GetOrAdd(key, done.Task) == done.Task)
            _ = Task.Run(async () =>
            {
                try { await BuildAsync(channel, to, from, art, arts, key); }
                finally { _building.TryRemove(key, out _); done.SetResult(); }
            });
        return new PackAnswer(PackState.Building);
    }

    /// <summary>Done when nothing is being built: for tests.</summary>
    public Task Idle() => Task.WhenAll(_building.Values);

    /// <summary>The name of a pack in the cache: the same request is the same pack.</summary>
    public static string Key(string to, string from, IEnumerable<string> art) =>
        Hashing.Sha256Hex(Encoding.UTF8.GetBytes($"{to}|{from}|{string.Join(',', art)}"))[..32];

    string PackPath(string to, string key) => Path.Combine(_o.CacheDir, to, key + ".tar.br");
    string MetaPath(string to, string key) => Path.Combine(_o.CacheDir, to, key + ".json");
    string RepoPath(string key) => SafePath.Resolve(_o.ReleaseDir, key);

    PackAnswer? Ready(string to, string key)
    {
        var meta = MetaPath(to, key);
        if (!File.Exists(meta) || !File.Exists(PackPath(to, key))) return null;
        var offer = JsonSerializer.Deserialize<PackOffer>(File.ReadAllBytes(meta), Json)!;
        // asked for again: the cache keeps it longest
        try { File.SetLastWriteTimeUtc(meta, clock.GetUtcNow().UtcDateTime); } catch (IOException) { }
        return new PackAnswer(offer.Blobs == 0 ? PackState.Empty : PackState.Ready, offer);
    }

    async Task BuildAsync(string channel, string to, string from, string[] art, HashSet<string> arts, string key)
    {
        await _gate.WaitAsync();
        try
        {
            var clockStart = clock.GetTimestamp();
            var target = Manifest(to);
            var have = from.Length == 0 ? [] : Manifest(from).Files.Select(f => f.Sha256).ToHashSet(StringComparer.Ordinal);
            // every component but the art layers goes always: engine and mods are a few megabytes, and the pack then
            // has at most three shapes for one pair of releases instead of one per set of mods
            var add = PackWriter.Order(target.Files.Where(f => (!arts.Contains(f.Component) || art.Contains(f.Component)) && !have.Contains(f.Sha256)));
            var offer = new PackOffer(key, 0, "", 0, 0);
            if (add.Count > 0)
            {
                var pack = PackWriter.Write(from, add, sha => RepoPath(BlobKeys.For(sha)), PackPath(to, key), _o.Quality);
                offer = new PackOffer(key, pack.Size, pack.Sha256, pack.Blobs, pack.Raw);
            }
            Directory.CreateDirectory(Path.Combine(_o.CacheDir, to));
            var meta = MetaPath(to, key);
            File.WriteAllBytes(meta + ".tmp", JsonSerializer.SerializeToUtf8Bytes(offer, Json));
            File.Move(meta + ".tmp", meta, overwrite: true);
            if (add.Count == 0) File.WriteAllBytes(PackPath(to, key), []);
            log.LogInformation("pack {To} from {From} [{Art}]: {Blobs} files, {Raw} -> {Size} bytes, {Seconds:F1} s",
                to, from.Length > 0 ? from : "(none)", string.Join(',', art), offer.Blobs, offer.Raw, offer.Size, clock.GetElapsedTime(clockStart).TotalSeconds);
            Sweep(channel, keep: PackPath(to, key));
        }
        catch (Exception e)
        {
            log.LogError(e, "pack {To} from {From} failed", to, from);
            try { File.Delete(PackPath(to, key) + ".tmp"); } catch (IOException) { }
        }
        finally
        {
            _gate.Release();
        }
    }

    /// <summary>The releases a pack may go to: the channel's current one and the one before it (a player halfway through).</summary>
    HashSet<string>? Targets(string channel)
    {
        var pointer = RepoPath(BlobKeys.Channel(channel));
        if (!File.Exists(pointer)) return null;
        var current = ManifestValidator.ParsePointer(File.ReadAllBytes(pointer)).ReleaseId;
        var set = new HashSet<string>(StringComparer.Ordinal) { current };
        if (Published(channel).Where(id => id != current).LastOrDefault() is { } previous) set.Add(previous);
        return set;
    }

    /// <summary>Every release ever published in the channel and not revoked since, oldest first.</summary>
    List<string> Published(string channel)
    {
        var path = RepoPath($"channels/{channel}.history.json");
        if (!File.Exists(path)) return [];
        var ids = new List<string>();
        foreach (var h in JsonSerializer.Deserialize<List<HistoryRow>>(File.ReadAllBytes(path), Json) ?? [])
        {
            if (h.Action is not ("publish" or "rollback") || !ManifestValidator.IsValidId(h.ReleaseId)) continue;
            ids.Remove(h.ReleaseId);
            ids.Add(h.ReleaseId);
        }
        return ids.Where(IsPublished).ToList();
    }

    bool IsPublished(string id)
    {
        var path = RepoPath($"releases/{id}/release.json");
        if (!File.Exists(path) || !File.Exists(RepoPath(BlobKeys.Manifest(id)))) return false;
        using var doc = JsonDocument.Parse(File.ReadAllBytes(path));
        return doc.RootElement.TryGetProperty("status", out var s) && s.GetString() == "Published";
    }

    /// <summary>A manifest runs to tens of megabytes: the few in use stay parsed.</summary>
    ReleaseManifest Manifest(string id)
    {
        if (_manifests.TryGetValue(id, out var m)) return m;
        m = ManifestValidator.Parse(File.ReadAllBytes(RepoPath(BlobKeys.Manifest(id))));
        if (_manifests.Count >= 4) _manifests.Clear();
        return _manifests[id] = m;
    }

    /// <summary>
    /// Packs to releases that are no longer a target go; then, past <see cref="PackOptions.CacheMaxGb"/>, the ones
    /// asked for longest ago. <paramref name="keep"/> is the pack just made.
    /// </summary>
    void Sweep(string channel, string keep)
    {
        var targets = new HashSet<string>(StringComparer.Ordinal);
        foreach (var ch in _o.Channels) targets.UnionWith(Targets(ch) ?? []);
        // builds go one at a time and this runs inside one: no other pack is being written now
        foreach (var dir in Directory.EnumerateDirectories(_o.CacheDir))
            if (!targets.Contains(Path.GetFileName(dir)))
            {
                log.LogInformation("packs to {To} dropped: not a target of {Channel} any more", Path.GetFileName(dir), channel);
                Directory.Delete(dir, recursive: true);
            }

        var packs = Directory.EnumerateFiles(_o.CacheDir, "*.tar.br", SearchOption.AllDirectories)
            .Select(p => new FileInfo(p))
            .Select(p => (Pack: p, Meta: new FileInfo(Path.ChangeExtension(Path.ChangeExtension(p.FullName, null), ".json"))))
            .OrderBy(p => p.Meta.Exists ? p.Meta.LastWriteTimeUtc : DateTime.MinValue)
            .ToList();
        var total = packs.Sum(p => p.Pack.Length);
        var cap = (long)(_o.CacheMaxGb * 1024 * 1024 * 1024);
        foreach (var (pack, meta) in packs)
        {
            if (total <= cap) break;
            if (pack.FullName == Path.GetFullPath(keep)) continue;
            total -= pack.Length;
            pack.Delete();
            if (meta.Exists) meta.Delete();
        }
    }

    /// <summary>A pack the service was writing when it stopped: never finished, never served.</summary>
    void DropLeftovers()
    {
        if (!Directory.Exists(_o.CacheDir)) return;
        foreach (var tmp in Directory.EnumerateFiles(_o.CacheDir, "*.tmp", SearchOption.AllDirectories))
            try { File.Delete(tmp); } catch (IOException) { }
    }

    sealed record HistoryRow(string ReleaseId, string Action);

    static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);
}
