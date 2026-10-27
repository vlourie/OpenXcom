using System.IO.Compression;
using System.Text.Json;
using System.Text.Json.Serialization;
using Xp.Manifest;

namespace Xp.Launcher.Core;

/// <summary>
/// Where a game that is not ours comes from (docs/portal/MODIO-GAMES.md §3): its author's file on mod.io. We do not
/// ship it - the rights are the author's - the launcher fetches it on the player's machine. The file and its SHA-256
/// are pinned to the one we checked with our engine: a newer upload of the author's is not taken until we check it.
/// This record rides in xp-profiles.json, which our signed release carries, so the hash is ours to trust.
/// </summary>
public sealed class GameSource
{
    public string Site { get; set; } = "mod.io";
    /// <summary>The author's page, for the player.</summary>
    public string Page { get; set; } = "";
    public string Url { get; set; } = "";
    public string Version { get; set; } = "";
    public long Size { get; set; }
    public string Sha256 { get; set; } = "";
    /// <summary>The archive's top folders that are mods; each goes to user/mods under the same name. The rest stays in the archive.</summary>
    public List<GameFolder> Folders { get; set; } = [];
}

public sealed class GameFolder
{
    /// <summary>The folder in the archive and in user/mods.</summary>
    public string Name { get; set; } = "";
    /// <summary>The mod id its metadata.yml must give; a different one means the archive is not the one we checked.</summary>
    public string Id { get; set; } = "";
}

public enum GameStatus
{
    /// <summary>Installed, the version we checked.</summary>
    Ready,
    /// <summary>Installed, but a version other than the one this release pins: install again.</summary>
    Outdated,
    /// <summary>Not installed; the launcher can fetch it.</summary>
    Missing,
    /// <summary>A game of ours whose master is not installed (a component left out at setup).</summary>
    Absent,
}

/// <summary>What the launcher installed of the games not ours: launcher/games.json.</summary>
public sealed class GameStateFile
{
    public Dictionary<string, InstalledGame> Games { get; set; } = new(StringComparer.OrdinalIgnoreCase);
}

public sealed class InstalledGame
{
    public string Version { get; set; } = "";
    public string Sha256 { get; set; } = "";
    public List<string> Folders { get; set; } = [];
    public DateTimeOffset Installed { get; set; }
}

/// <summary>
/// The games of xp-profiles.json and fetching the ones not ours. On disk every mod stays one level under user/mods
/// (FileMap::scanModDir reads no deeper); "a game and its add-ons" is the launcher's grouping, not folders.
/// </summary>
public sealed class GameInstaller(GamePaths paths, RepoClient repo, ILauncherLog log)
{
    public GamePaths Paths { get; } = paths;
    public Func<string, bool> IsGameRunning { get; set; } = GameProcess.IsRunningIn;
    public Func<string, long> FreeSpace { get; set; } = dir => new DriveInfo(Path.GetPathRoot(dir)!).AvailableFreeSpace;

    public string StateFile => Path.Combine(Paths.StateDir, "games.json");
    string Downloads => Path.Combine(Paths.StateDir, "downloads");
    string ModsDir => Path.Combine(Paths.GameDir, "user", "mods");

    public GameStateFile LoadState()
    {
        try
        {
            return File.Exists(StateFile)
                ? JsonSerializer.Deserialize(File.ReadAllBytes(StateFile), ProfileJson.Default.GameStateFile) ?? new()
                : new();
        }
        catch (Exception e) when (e is JsonException or IOException or UnauthorizedAccessException) { return new(); }
    }

    void SaveState(GameStateFile s) =>
        FileUtil.WriteAtomic(StateFile, JsonSerializer.SerializeToUtf8Bytes(s, ProfileJson.Default.GameStateFile));

    /// <summary>Whether the game is here to play. A game of ours is its master's folder; a fetched one, what games.json says of it.</summary>
    public GameStatus Status(ModProfile game, GameStateFile? state = null)
    {
        if (game.Source is not { } src)
            return ProfileWriter.ScanMods(Paths.GameDir).Any(m => m.IsMaster && m.Id.Equals(game.Master, StringComparison.OrdinalIgnoreCase))
                || game.Master is "xcom1" or "xcom2" ? GameStatus.Ready : GameStatus.Absent;
        bool here = src.Folders.All(f => File.Exists(Path.Combine(ModsDir, f.Name, "metadata.yml")));
        if (!here) return GameStatus.Missing;
        return (state ?? LoadState()).Games.TryGetValue(game.Key, out var g) && g.Sha256 == src.Sha256 ? GameStatus.Ready : GameStatus.Outdated;
    }

    /// <summary>What a game needs fetched before it can be played: itself and what it requires (ROSIGMA - 40k), required first.</summary>
    public List<ModProfile> ToFetch(ProfileSet set, ModProfile game)
    {
        var list = new List<ModProfile>();
        var state = LoadState();
        void Add(ModProfile p, int depth)
        {
            if (depth > 4) throw new InvalidOperationException($"profile '{game.Key}': requires go round in a circle");
            if (p.Requires is { Length: > 0 } r)
                Add(set.For(r) ?? throw new InvalidOperationException($"profile '{p.Key}' requires '{r}', which is not in {ProfileSet.FileName}"), depth + 1);
            if (p.Source is not null && Status(p, state) != GameStatus.Ready && !list.Contains(p)) list.Add(p);
        }
        Add(game, 0);
        return list;
    }

    /// <summary>
    /// Fetches a game from its author's site, checks it against the pinned size and SHA-256, and puts its mod folders
    /// into user/mods. Each folder is unpacked aside and swapped in whole, so a broken install leaves the old one;
    /// a folder's metadata.yml must name the id we checked. The archive is deleted after.
    /// </summary>
    public async Task InstallAsync(ModProfile game, IProgress<Progress>? progress, CancellationToken ct)
    {
        var src = game.Source ?? throw new InvalidOperationException($"'{game.Key}' is not fetched: it comes with the release");
        if (src.Folders.Count == 0) throw new InvalidOperationException($"'{game.Key}': no folders to install");
        foreach (var f in src.Folders)
            if ((f.Name.Contains('/') ? "nested folder" : SafePath.Validate(f.Name)) is { } why) throw new UnsafePathException(f.Name, why);
        if (IsGameRunning(Paths.GameDir)) throw new UpdateBlockedException("the game is running: its mods are not changed under it");

        var zip = Path.Combine(Downloads, $"{game.Key}-{src.Sha256[..12]}.zip");
        if (!File.Exists(zip))
        {
            long have = File.Exists(zip + ".part") ? new FileInfo(zip + ".part").Length : 0;
            // the archive and, unpacked, about as much again
            if (FreeSpace(Paths.GameDir) < (src.Size - have) + src.Size * 2)
                throw new IOException($"not enough free space for {game.Key}: {src.Size * 3 / (1 << 20)} MB needed");
            log.Info($"games: fetching {game.Key} {src.Version} from {src.Site} ({src.Size / (1 << 20)} MB)");
            long done = have;
            var meter = new SpeedMeter();
            await repo.DownloadFileAsync(new Uri(src.Url), src.Sha256, src.Size, zip, game.Key, n =>
            {
                done += n;
                meter.Add(n);
                progress?.Report(new Progress(Phase.Downloading, done, src.Size, game.Key, meter.BytesPerSecond));
            }, ct);
        }

        var stage = Path.Combine(Paths.StateDir, "games-staging", game.Key);
        var old = Path.Combine(Paths.StateDir, "games-old", game.Key);
        DeleteTree(stage);
        DeleteTree(old);
        Unpack(zip, src, stage, progress, ct);
        foreach (var f in src.Folders)
        {
            var meta = Path.Combine(stage, f.Name, "metadata.yml");
            if (!File.Exists(meta)) throw new TrustException($"{game.Key}: no {f.Name}/metadata.yml in the archive");
            var m = ModMetadata.Parse(File.ReadAllText(meta), f.Name);
            if (!m.Id.Equals(f.Id, StringComparison.Ordinal)) throw new TrustException($"{game.Key}: {f.Name} is mod '{m.Id}', not '{f.Id}'");
        }

        if (IsGameRunning(Paths.GameDir)) throw new UpdateBlockedException("the game is running: its mods are not changed under it");
        Directory.CreateDirectory(ModsDir);
        Directory.CreateDirectory(old);
        var moved = new List<string>();
        var placed = new List<string>();
        try
        {
            foreach (var f in src.Folders)
            {
                var target = Path.Combine(ModsDir, f.Name);
                if (Directory.Exists(target))
                {
                    Directory.Move(target, Path.Combine(old, f.Name));
                    moved.Add(f.Name);
                }
                Directory.Move(Path.Combine(stage, f.Name), target);
                placed.Add(f.Name);
            }
        }
        catch
        {
            // back as it was: the new folders out, the old ones in
            foreach (var n in placed) DeleteTree(Path.Combine(ModsDir, n));
            foreach (var n in moved) Directory.Move(Path.Combine(old, n), Path.Combine(ModsDir, n));
            throw;
        }
        var state = LoadState();
        state.Games[game.Key] = new InstalledGame
        {
            Version = src.Version, Sha256 = src.Sha256, Folders = src.Folders.Select(f => f.Name).ToList(), Installed = DateTimeOffset.Now,
        };
        SaveState(state);
        DeleteTree(old);
        DeleteTree(stage);
        File.Delete(zip);
        log.Info($"games: {game.Key} {src.Version} installed: {string.Join(", ", src.Folders.Select(f => f.Name))}");
        progress?.Report(new Progress(Phase.Done, 1, 1, game.Key, 0));
    }

    /// <summary>
    /// Unpacks the listed top folders of the archive into &lt;stage&gt;. Every entry path is held to SafePath, as
    /// a release file is: an archive that tries to write outside its folder, or a name Windows cannot keep, is refused.
    /// </summary>
    internal static void Unpack(string zip, GameSource src, string stage, IProgress<Progress>? progress, CancellationToken ct)
    {
        var tops = src.Folders.Select(f => f.Name).ToHashSet(StringComparer.Ordinal);
        using var archive = ZipFile.OpenRead(zip);
        var entries = archive.Entries
            .Select(e => (Entry: e, Path: e.FullName.Replace('\\', '/')))
            .Where(e => e.Path.Split('/')[0] is var top && tops.Contains(top))
            .ToList();
        long total = entries.Sum(e => e.Entry.Length), done = 0;
        foreach (var (entry, path) in entries)
        {
            ct.ThrowIfCancellationRequested();
            if (path.EndsWith('/'))
            {
                Directory.CreateDirectory(SafePath.Resolve(stage, path.TrimEnd('/')));
                continue;
            }
            var to = SafePath.Resolve(stage, path);
            Directory.CreateDirectory(Path.GetDirectoryName(to)!);
            // a packing the zip reader does not know (Deflate64, LZMA) or a broken entry: an error the window shows, not a crash
            try { entry.ExtractToFile(to, overwrite: true); }
            catch (Exception e) when (e is NotSupportedException or InvalidDataException)
            {
                throw new IOException($"{path}: cannot unpack this archive ({e.Message})", e);
            }
            done += entry.Length;
            progress?.Report(new Progress(Phase.Installing, done, total, path, 0));
        }
        foreach (var f in src.Folders)
            if (!Directory.Exists(Path.Combine(stage, f.Name))) throw new TrustException($"no folder '{f.Name}' in the archive");
    }

    static void DeleteTree(string dir)
    {
        if (!Directory.Exists(dir)) return;
        foreach (var f in Directory.EnumerateFiles(dir, "*", SearchOption.AllDirectories))
            File.SetAttributes(f, FileAttributes.Normal);
        Directory.Delete(dir, recursive: true);
    }
}
