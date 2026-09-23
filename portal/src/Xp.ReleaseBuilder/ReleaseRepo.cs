using System.Collections.Concurrent;
using System.Text.Json;
using System.Text.Json.Serialization;
using Xp.Manifest;

namespace Xp.ReleaseBuilder;

public sealed class BuildOptions
{
    /// <summary>Prepared version directory (dist/_stage); may be null when only <see cref="Adds"/> are used.</summary>
    public string? StageDir { get; set; }
    /// <summary>Extra files: relative destination -> local source.</summary>
    public Dictionary<string, string> Adds { get; } = new(StringComparer.OrdinalIgnoreCase);
    public string Id { get; set; } = "";
    public string Version { get; set; } = "";
    public string Channel { get; set; } = "stable";
    public List<string>? Roots { get; set; }
    public string Launch { get; set; } = "";
    public string MinLauncher { get; set; } = "0.0.0";
    public bool Mandatory { get; set; }
    public Dictionary<string, string> Changelog { get; } = new();
    /// <summary>Component id -> version, for components whose version no metadata.yml gives (the engine).</summary>
    public Dictionary<string, string> Components { get; } = new();
    /// <summary>Engine line of the release: "oxce" (Meridian's) or "oxce-hd" (ours).</summary>
    public string Line { get; set; } = "";
    /// <summary>What the line's exe answers to in requiredExtendedEngine; a mod asking for another is refused.</summary>
    public List<string> Engines { get; } = new();
    /// <summary>Path prefix -> component id, for trees the rules do not know.</summary>
    public Dictionary<string, string> Maps { get; } = new(StringComparer.OrdinalIgnoreCase);
    /// <summary>Keep hd_18+ files that are byte-identical to their hd twins (off by default).</summary>
    public bool KeepHd18Copies { get; set; }
    /// <summary>Launcher releases: every top-level entry is its own root, no component mapping.</summary>
    public bool LauncherKind { get; set; }
}

public enum ReleaseStatus { Draft, Published, Revoked }

public sealed class ReleaseRecord
{
    public string Id { get; set; } = "";
    public string Channel { get; set; } = "";
    public ReleaseStatus Status { get; set; }
    public DateTimeOffset Created { get; set; }
    public DateTimeOffset? Changed { get; set; }
    public int Files { get; set; }
    public long Bytes { get; set; }
    public int NewBlobs { get; set; }
}

public sealed class HistoryEntry
{
    public long Sequence { get; set; }
    public string ReleaseId { get; set; } = "";
    public string Action { get; set; } = "";
    public DateTimeOffset At { get; set; }
}

[JsonSourceGenerationOptions(WriteIndented = true, PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase,
    UseStringEnumConverter = true)]
[JsonSerializable(typeof(ReleaseRecord))]
[JsonSerializable(typeof(List<HistoryEntry>))]
internal sealed partial class RepoJson : JsonSerializerContext
{
}

/// <summary>
/// The release repository: a plain directory tree that any static web server can serve.
/// Signed: channel pointers and manifests. Unsigned bookkeeping: release.json, history.
/// </summary>
public sealed class ReleaseRepo(string root, Action<string>? log = null)
{
    public string Root { get; } = Path.GetFullPath(root);
    readonly Action<string> _log = log ?? (_ => { });

    string Full(string key) => SafePath.Resolve(Root, key);
    string RecordPath(string id) => Full($"releases/{id}/release.json");
    string HistoryPath(string channel) => Full($"channels/{channel}.history.json");

    // ------------------------------------------------------------------ build

    public ReleaseManifest Build(BuildOptions o, byte[] privateSeed)
    {
        if (!ManifestValidator.IsValidId(o.Id)) throw new ArgumentException($"bad release id '{o.Id}'");
        if (!ManifestValidator.IsValidId(o.Channel)) throw new ArgumentException($"bad channel '{o.Channel}'");
        if (File.Exists(Full(BlobKeys.Manifest(o.Id)))) throw new InvalidOperationException($"release '{o.Id}' already exists");

        var sources = CollectSources(o);
        if (sources.Count == 0) throw new InvalidOperationException("nothing to release");
        if (o.Line.Length > 0 && !ManifestValidator.IsValidId(o.Line)) throw new ArgumentException($"bad line '{o.Line}'");
        var roots = o.Roots ?? AutoRoots(sources.Keys, o.LauncherKind);
        var plan = o.LauncherKind ? null : ComponentPlan.Build(sources,
            o.Engines.Count > 0 ? o.Engines : ["Extended"], o.Maps, o.Components);
        foreach (var w in plan?.Warnings ?? []) _log("warning: " + w);

        var hashed = new ConcurrentBag<ManifestFile>();
        int newBlobs = 0;
        Parallel.ForEach(sources, new ParallelOptions { MaxDegreeOfParallelism = Math.Max(1, Environment.ProcessorCount / 2) }, kv =>
        {
            var info = new FileInfo(kv.Value);
            var sha = Hashing.FileSha256(kv.Value);
            if (StoreBlob(kv.Value, sha)) Interlocked.Increment(ref newBlobs);
            hashed.Add(new ManifestFile { Path = kv.Key, Size = info.Length, Sha256 = sha, Component = plan?.FileComponent[kv.Key] ?? ComponentKind.Launcher });
        });

        var files = hashed.OrderBy(f => f.Path, StringComparer.Ordinal).ToList();
        if (plan is not null && !o.KeepHd18Copies)
        {
            var copies = ComponentPlan.Hd18Copies(files);
            if (copies.Count > 0)
            {
                var drop = copies.Select(f => f.Path).ToHashSet(StringComparer.OrdinalIgnoreCase);
                files.RemoveAll(f => drop.Contains(f.Path));
                _log($"{ComponentPlan.Hd18Folder}: {copies.Count} files identical to {ComponentPlan.HdFolder}/ left out, " +
                     $"{copies.Sum(f => f.Size) / (1024.0 * 1024):F1} MiB");
            }
        }
        List<ComponentInfo> components;
        if (plan is null)
            components = [new ComponentInfo { Id = ComponentKind.Launcher, Kind = ComponentKind.Launcher, Name = "launcher",
                                              Version = o.Version, Size = files.Sum(f => f.Size), Files = files.Count }];
        else
        {
            plan.Count(files);
            components = plan.Components.Values.OrderBy(c => c.Id, StringComparer.Ordinal).ToList();
        }

        var manifest = new ReleaseManifest
        {
            Release = new ReleaseInfo
            {
                Id = o.Id, Version = o.Version, Channel = o.Channel, Line = o.Line, Published = DateTimeOffset.UtcNow,
                Mandatory = o.Mandatory, MinLauncher = o.MinLauncher, Launch = o.Launch,
            },
            Roots = roots.ToList(),
            Files = files,
            Components = components,
        };
        foreach (var kv in o.Changelog) manifest.Release.Changelog[kv.Key] = kv.Value;
        manifest.Deletes = ComputeDeletes(o.Channel, manifest);

        ManifestValidator.Validate(manifest);
        var bytes = JsonSerializer.SerializeToUtf8Bytes(manifest, ManifestJson.Default.ReleaseManifest);
        WriteAtomic(Full(BlobKeys.Manifest(o.Id)), bytes);
        WriteAtomic(Full(BlobKeys.Sig(BlobKeys.Manifest(o.Id))), Signing.SerializeSignature(Signing.Sign(privateSeed, bytes)));
        SaveRecord(new ReleaseRecord
        {
            Id = o.Id, Channel = o.Channel, Status = ReleaseStatus.Draft, Created = DateTimeOffset.UtcNow,
            Files = manifest.Files.Count, Bytes = manifest.Files.Sum(f => f.Size), NewBlobs = newBlobs,
        });
        foreach (var c in components)
            _log($"  {c.Id,-24} {c.Kind,-8} {c.Files,7} files {c.Size / (1024.0 * 1024),9:F1} MiB" +
                 (c.Requires.Count > 0 ? "  needs " + string.Join(", ", c.Requires) : ""));
        _log($"release {o.Id}: {manifest.Files.Count} files, {manifest.Files.Sum(f => f.Size) / (1024.0 * 1024):F1} MiB, " +
             $"{newBlobs} new blobs, {manifest.Deletes.Count} deletes, status draft");
        return manifest;
    }

    /// <summary>
    /// The launcher's own files. tools/build/build.ps1 puts them into dist/_stage next to the game
    /// exe (the game looks for the launcher there), but they are released on the launcher-* channels:
    /// a game release that owned them would overwrite the running launcher.
    /// </summary>
    public static readonly string[] LauncherFiles =
        ["XPiratezLauncher.exe", "xp-bootstrap.exe", "libHarfBuzzSharp.dll", "libSkiaSharp.dll", "libsodium.dll"];

    /// <summary>A stage file that does not belong in this kind of release: launcher files in a game
    /// release, debug symbols anywhere at the top level; a launcher release takes its own files and
    /// nothing else (a zip of them left in the folder would otherwise ship to every player).</summary>
    public static bool SkipInStage(string rel, bool launcherKind) =>
        launcherKind ? !LauncherFiles.Contains(rel, StringComparer.OrdinalIgnoreCase)
                     : !rel.Contains('/') && (rel.EndsWith(".pdb", StringComparison.OrdinalIgnoreCase) ||
                                              LauncherFiles.Contains(rel, StringComparer.OrdinalIgnoreCase));

    Dictionary<string, string> CollectSources(BuildOptions o)
    {
        var map = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        if (o.StageDir is not null)
        {
            var stage = Path.GetFullPath(o.StageDir);
            var skipped = new List<string>();
            foreach (var f in Directory.EnumerateFiles(stage, "*", SearchOption.AllDirectories))
            {
                // reparse points (junctions) are never followed: R-047
                if ((File.GetAttributes(f) & FileAttributes.ReparsePoint) != 0) continue;
                var rel = SafePath.ToRelative(stage, f);
                if (SkipInStage(rel, o.LauncherKind)) { skipped.Add(rel); continue; }
                map[rel] = f;
            }
            if (skipped.Count > 0) _log($"not released from the stage: {string.Join(", ", skipped.Order(StringComparer.Ordinal))}");
        }
        foreach (var kv in o.Adds)
        {
            if (!File.Exists(kv.Value)) throw new FileNotFoundException("--add source not found", kv.Value);
            map[kv.Key.Replace('\\', '/')] = Path.GetFullPath(kv.Value);
        }
        foreach (var rel in map.Keys)
            if (SafePath.Validate(rel) is { } why) throw new UnsafePathException(rel, why);
        return map;
    }

    /// <summary>
    /// Roots derived from the files: top-level files exactly, "user/mods/&lt;mod&gt;/" per mod,
    /// every other top-level directory as a whole. Never "user/" itself: saves live there.
    /// </summary>
    public static List<string> AutoRoots(IEnumerable<string> paths, bool launcherKind)
    {
        var roots = new SortedSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var p in paths)
        {
            var seg = p.Split('/');
            if (seg.Length == 1) roots.Add(p);
            else if (!launcherKind && seg[0].Equals("user", StringComparison.OrdinalIgnoreCase))
            {
                if (seg.Length >= 4 && seg[1].Equals("mods", StringComparison.OrdinalIgnoreCase))
                    roots.Add($"{seg[0]}/{seg[1]}/{seg[2]}/");
                else
                    throw new InvalidOperationException($"'{p}': only user/mods/<mod>/ may be shipped under user/");
            }
            else roots.Add(seg[0] + "/");
        }
        return roots.ToList();
    }

    List<string> ComputeDeletes(string channel, ReleaseManifest next)
    {
        var current = TryLoadPointer(channel);
        if (current is null) return new();
        var prev = LoadManifest(current.ReleaseId);
        var shipped = new HashSet<string>(next.Files.Select(f => f.Path), StringComparer.OrdinalIgnoreCase);
        var deletes = new List<string>();
        foreach (var f in prev.Files)
        {
            if (shipped.Contains(f.Path)) continue;
            if (SafePath.UnderAnyRoot(f.Path, next.Roots)) deletes.Add(f.Path);
            else _log($"warning: '{f.Path}' left behind: its root is no longer managed");
        }
        deletes.Sort(StringComparer.Ordinal);
        return deletes;
    }

    /// <summary>Copies a file into the content-addressed store. Returns true if it was new.</summary>
    bool StoreBlob(string source, string sha)
    {
        var target = Full(BlobKeys.For(sha));
        if (File.Exists(target)) return false;
        Directory.CreateDirectory(Path.GetDirectoryName(target)!);
        var tmp = target + "." + Guid.NewGuid().ToString("N") + ".tmp";
        File.Copy(source, tmp);
        try { File.Move(tmp, target); }
        catch (IOException) when (File.Exists(target)) { File.Delete(tmp); return false; }
        return true;
    }

    // ------------------------------------------------------------ publishing

    public ChannelPointer Publish(string channel, string releaseId, byte[] privateSeed)
    {
        var rec = LoadRecord(releaseId);
        if (rec.Status == ReleaseStatus.Revoked) throw new InvalidOperationException($"release '{releaseId}' is revoked");
        var manifest = LoadManifest(releaseId);
        if (!string.Equals(manifest.Release.Channel, channel, StringComparison.Ordinal))
            throw new InvalidOperationException($"release '{releaseId}' was built for channel '{manifest.Release.Channel}'");
        var pointer = WritePointer(channel, releaseId, privateSeed, "publish");
        rec.Status = ReleaseStatus.Published;
        rec.Changed = DateTimeOffset.UtcNow;
        SaveRecord(rec);
        return pointer;
    }

    /// <summary>Marks a release revoked; if the channel points at it, moves the channel back to the previous good release.</summary>
    public ChannelPointer? Revoke(string channel, string releaseId, byte[] privateSeed)
    {
        var rec = LoadRecord(releaseId);
        rec.Status = ReleaseStatus.Revoked;
        rec.Changed = DateTimeOffset.UtcNow;
        SaveRecord(rec);
        var current = TryLoadPointer(channel);
        if (current is null || current.ReleaseId != releaseId) return null;

        var previous = LoadHistory(channel)
            .Where(h => h.Action is "publish" or "rollback" && h.ReleaseId != releaseId)
            .Reverse()
            .Select(h => h.ReleaseId)
            .FirstOrDefault(id => TryLoadRecord(id)?.Status == ReleaseStatus.Published)
            ?? throw new InvalidOperationException($"no earlier good release in '{channel}' to fall back to");
        _log($"channel {channel}: {releaseId} revoked, back to {previous}");
        return WritePointer(channel, previous, privateSeed, "rollback");
    }

    ChannelPointer WritePointer(string channel, string releaseId, byte[] privateSeed, string action)
    {
        var manifestBytes = File.ReadAllBytes(Full(BlobKeys.Manifest(releaseId)));
        var old = TryLoadPointer(channel);
        var pointer = new ChannelPointer
        {
            Channel = channel,
            Sequence = (old?.Sequence ?? 0) + 1,
            ReleaseId = releaseId,
            ManifestSha256 = Hashing.Sha256Hex(manifestBytes),
            ManifestSize = manifestBytes.Length,
            Updated = DateTimeOffset.UtcNow,
        };
        var bytes = JsonSerializer.SerializeToUtf8Bytes(pointer, ManifestJson.Default.ChannelPointer);
        // signature first: a reader that sees the new pointer must also see its signature;
        // a reader in between gets a mismatch and retries, never a wrongly trusted pointer
        var key = BlobKeys.Channel(channel);
        WriteAtomic(Full(BlobKeys.Sig(key)), Signing.SerializeSignature(Signing.Sign(privateSeed, bytes)));
        WriteAtomic(Full(key), bytes);
        var history = LoadHistory(channel);
        history.Add(new HistoryEntry { Sequence = pointer.Sequence, ReleaseId = releaseId, Action = action, At = pointer.Updated });
        WriteAtomic(HistoryPath(channel), JsonSerializer.SerializeToUtf8Bytes(history, RepoJson.Default.ListHistoryEntry));
        _log($"channel {channel} -> {releaseId} (sequence {pointer.Sequence}, {action})");
        return pointer;
    }

    // -------------------------------------------------------------- catalog

    /// <summary>
    /// Signs and writes catalog.json. Every preset component must exist in the release each
    /// published channel of its line points at, and that release must be built for the line.
    /// </summary>
    public Catalog PublishCatalog(Catalog catalog, byte[] privateSeed)
    {
        ManifestValidator.ValidateCatalog(catalog);
        foreach (var line in catalog.Lines)
            foreach (var channel in line.Channels)
            {
                if (TryLoadPointer(channel) is not { } pointer) { _log($"warning: channel '{channel}' of line '{line.Id}' is not published yet"); continue; }
                var m = LoadManifest(pointer.ReleaseId);
                if (m.Release.Line.Length > 0 && m.Release.Line != line.Id)
                    throw new InvalidOperationException($"channel '{channel}' points at {m.Release.Id}, built for line '{m.Release.Line}', not '{line.Id}'");
                var have = m.Components.Select(c => c.Id).ToHashSet(StringComparer.Ordinal);
                foreach (var p in catalog.Presets.Where(p => p.Line == line.Id))
                    foreach (var id in p.Components.Where(id => !have.Contains(id)))
                        throw new InvalidOperationException($"preset '{p.Id}': component '{id}' is not in {m.Release.Id} (channel '{channel}')");
            }

        var path = Full(BlobKeys.Catalog);
        long old = File.Exists(path) ? ManifestValidator.ParseCatalog(File.ReadAllBytes(path)).Sequence : 0;
        catalog.Sequence = old + 1;
        catalog.Updated = DateTimeOffset.UtcNow;
        var bytes = JsonSerializer.SerializeToUtf8Bytes(catalog, ManifestJson.Default.Catalog);
        WriteAtomic(Full(BlobKeys.Sig(BlobKeys.Catalog)), Signing.SerializeSignature(Signing.Sign(privateSeed, bytes)));
        WriteAtomic(path, bytes);
        _log($"catalog: {catalog.Lines.Count} lines, {catalog.Presets.Count} presets (sequence {catalog.Sequence})");
        return catalog;
    }

    // ------------------------------------------------------------- checking

    /// <summary>Checks the whole chain a launcher would check; with <paramref name="deep"/> re-hashes every blob.</summary>
    public List<string> Verify(string channel, TrustedKeys keys, bool deep)
    {
        var problems = new List<string>();
        var key = BlobKeys.Channel(channel);
        var pBytes = File.ReadAllBytes(Full(key));
        if (!keys.Verify(pBytes, File.ReadAllBytes(Full(BlobKeys.Sig(key))))) problems.Add("channel pointer: bad signature");
        var pointer = ManifestValidator.ParsePointer(pBytes);
        var mKey = BlobKeys.Manifest(pointer.ReleaseId);
        var mBytes = File.ReadAllBytes(Full(mKey));
        if (Hashing.Sha256Hex(mBytes) != pointer.ManifestSha256) problems.Add("manifest: hash differs from pointer");
        if (!keys.Verify(mBytes, File.ReadAllBytes(Full(BlobKeys.Sig(mKey))))) problems.Add("manifest: bad signature");
        var manifest = ManifestValidator.Parse(mBytes);
        var found = new ConcurrentBag<string>();
        Parallel.ForEach(manifest.Files.DistinctBy(f => f.Sha256), f =>
        {
            var blob = Full(BlobKeys.For(f.Sha256));
            if (!File.Exists(blob)) found.Add($"missing blob for {f.Path}");
            else if (new FileInfo(blob).Length != f.Size) found.Add($"blob size differs for {f.Path}");
            else if (deep && Hashing.FileSha256(blob) != f.Sha256) found.Add($"blob hash differs for {f.Path}");
        });
        problems.AddRange(found.Order());
        return problems;
    }

    public IEnumerable<ReleaseRecord> List()
    {
        var dir = Full("releases");
        if (!Directory.Exists(dir)) yield break;
        foreach (var d in Directory.EnumerateDirectories(dir).Order())
            if (TryLoadRecord(Path.GetFileName(d)) is { } r) yield return r;
    }

    // ---------------------------------------------------------------- store

    public ChannelPointer? TryLoadPointer(string channel)
    {
        var p = Full(BlobKeys.Channel(channel));
        return File.Exists(p) ? ManifestValidator.ParsePointer(File.ReadAllBytes(p)) : null;
    }

    public ReleaseManifest LoadManifest(string id) => ManifestValidator.Parse(File.ReadAllBytes(Full(BlobKeys.Manifest(id))));

    ReleaseRecord LoadRecord(string id) => TryLoadRecord(id) ?? throw new InvalidOperationException($"no release '{id}'");

    ReleaseRecord? TryLoadRecord(string id)
    {
        if (!ManifestValidator.IsValidId(id)) return null;
        var p = RecordPath(id);
        return File.Exists(p) ? JsonSerializer.Deserialize(File.ReadAllBytes(p), RepoJson.Default.ReleaseRecord) : null;
    }

    void SaveRecord(ReleaseRecord r) => WriteAtomic(RecordPath(r.Id), JsonSerializer.SerializeToUtf8Bytes(r, RepoJson.Default.ReleaseRecord));

    List<HistoryEntry> LoadHistory(string channel)
    {
        var p = HistoryPath(channel);
        return File.Exists(p) ? JsonSerializer.Deserialize(File.ReadAllBytes(p), RepoJson.Default.ListHistoryEntry) ?? new() : new();
    }

    static void WriteAtomic(string path, byte[] bytes)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        var tmp = path + ".tmp";
        File.WriteAllBytes(tmp, bytes);
        File.Move(tmp, path, overwrite: true);
    }
}
