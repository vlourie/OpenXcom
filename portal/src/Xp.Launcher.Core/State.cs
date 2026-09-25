using System.Text.Json;
using System.Text.Json.Serialization;
using Xp.Manifest;

namespace Xp.Launcher.Core;

/// <summary>Directories the launcher owns inside the game directory.</summary>
public sealed class GamePaths
{
    public GamePaths(string gameDir)
    {
        GameDir = Path.GetFullPath(gameDir);
        StateDir = Path.Combine(GameDir, "launcher");
    }

    public string GameDir { get; }
    public string StateDir { get; }
    public string StateFile => Path.Combine(StateDir, "state.json");
    public string Staging => Path.Combine(StateDir, "staging");
    public string Backup => Path.Combine(StateDir, "backup");
    public string LastBackup => Path.Combine(Backup, "last");
    public string Journal => Path.Combine(StateDir, "transaction.json");
    public string Logs => Path.Combine(StateDir, "logs");

    public string Full(string relative) => SafePath.Resolve(GameDir, relative);

    /// <summary>A game directory looks like one when it has the engine data next to a user folder.</summary>
    public static bool LooksLikeGameDir(string dir) =>
        Directory.Exists(Path.Combine(dir, "common")) && Directory.Exists(Path.Combine(dir, "user"))
        && (File.Exists(Path.Combine(dir, "OpenXcomEx.exe")) || File.Exists(Path.Combine(dir, "openxcom_hd.exe"))
            || Directory.EnumerateFiles(dir, "OpenXComEx*.exe").Any());
}

/// <summary>
/// What the launcher may never write, whatever a signed manifest says: saves, options and
/// everything else under user/ except user/mods/&lt;mod&gt;/, and its own state directory.
/// </summary>
public static class InstallPolicy
{
    public static string? WhyProtected(string relative)
    {
        var seg = relative.Split('/');
        if (seg[0].Equals("launcher", StringComparison.OrdinalIgnoreCase)) return "launcher state";
        if (seg[0].Equals("user", StringComparison.OrdinalIgnoreCase))
        {
            if (seg.Length < 3 || !seg[1].Equals("mods", StringComparison.OrdinalIgnoreCase))
                return "player data (saves, options, logs)";
        }
        return null;
    }

    public static string? WhyRootProtected(string root)
    {
        var body = root.TrimEnd('/');
        if (body.Equals("user", StringComparison.OrdinalIgnoreCase) || body.Equals("user/mods", StringComparison.OrdinalIgnoreCase))
            return "a root may not cover all of user/ or user/mods/";
        return WhyProtected(body + (root.EndsWith('/') ? "/x" : ""));
    }

    public static void Check(ReleaseManifest m)
    {
        foreach (var r in m.Roots)
            if (WhyRootProtected(r) is { } why) throw new ManifestException($"root '{r}' refused: {why}");
        foreach (var f in m.Files)
            if (WhyProtected(f.Path) is { } why) throw new ManifestException($"'{f.Path}' refused: {why}");
        foreach (var d in m.Deletes)
            if (WhyProtected(d) is { } why) throw new ManifestException($"delete '{d}' refused: {why}");
    }
}

public sealed class CacheEntry
{
    public long Size { get; set; }
    public long MtimeUtcTicks { get; set; }
    public string Sha256 { get; set; } = "";
}

public sealed class KeptFile
{
    public string Sha256 { get; set; } = "";
    public string ReleaseId { get; set; } = "";
}

/// <summary>Persistent per-game-directory state, in launcher/state.json.</summary>
public sealed class LauncherState
{
    public string Channel { get; set; } = "stable";
    public string? InstalledReleaseId { get; set; }
    public string? InstalledVersion { get; set; }
    /// <summary>Highest pointer sequence ever accepted, per channel: older pointers are replays.</summary>
    public Dictionary<string, long> LastSequence { get; set; } = new();
    /// <summary>Path -> SHA-256 of what this launcher installed. Anything else on disk is the player's.</summary>
    public Dictionary<string, string> Installed { get; set; } = new(StringComparer.OrdinalIgnoreCase);
    public List<string> InstalledRoots { get; set; } = new();
    public string InstalledLaunch { get; set; } = "";
    /// <summary>Component ids the player ticked in the wizard; null - the whole release (installs from before the wizard).</summary>
    public List<string>? Components { get; set; }
    /// <summary>Files the player chose to keep modified, until the next release.</summary>
    public Dictionary<string, KeptFile> Kept { get; set; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, CacheEntry> Cache { get; set; } = new(StringComparer.OrdinalIgnoreCase);

    public static LauncherState Load(GamePaths p)
    {
        if (!File.Exists(p.StateFile)) return new LauncherState();
        var s = JsonSerializer.Deserialize(File.ReadAllBytes(p.StateFile), CoreJson.Default.LauncherState) ?? new LauncherState();
        // dictionaries come back case-sensitive from JSON; paths on Windows are not
        s.Installed = new(s.Installed, StringComparer.OrdinalIgnoreCase);
        s.Kept = new(s.Kept, StringComparer.OrdinalIgnoreCase);
        s.Cache = new(s.Cache, StringComparer.OrdinalIgnoreCase);
        return s;
    }

    public void Save(GamePaths p) => FileUtil.WriteAtomic(p.StateFile, JsonSerializer.SerializeToUtf8Bytes(this, CoreJson.Default.LauncherState));
}

public sealed class JournalOp
{
    public string Path { get; set; } = "";
    public string Sha256 { get; set; } = "";
    public bool Existed { get; set; }
}

/// <summary>An install in progress, or (once committed, in backup/last) the recipe to undo it.</summary>
public sealed class Journal
{
    public string Id { get; set; } = "";
    public string ReleaseId { get; set; } = "";
    public string? PreviousReleaseId { get; set; }
    public string Phase { get; set; } = "applying";
    public List<JournalOp> Writes { get; set; } = new();
    public List<string> Deletes { get; set; } = new();
    public DateTimeOffset Started { get; set; }
}

[JsonSourceGenerationOptions(WriteIndented = false, PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase)]
[JsonSerializable(typeof(LauncherState))]
[JsonSerializable(typeof(Journal))]
internal sealed partial class CoreJson : JsonSerializerContext
{
}

public static class FileUtil
{
    public static void WriteAtomic(string path, byte[] bytes)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        var tmp = path + ".tmp";
        using (var fs = new FileStream(tmp, FileMode.Create, FileAccess.Write, FileShare.None))
        {
            fs.Write(bytes);
            fs.Flush(flushToDisk: true);
        }
        File.Move(tmp, path, overwrite: true);
    }

    public static void MoveInto(string source, string target)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(target)!);
        File.Move(source, target, overwrite: true);
    }

    public static CacheEntry Stat(string path, string sha)
    {
        var fi = new FileInfo(path);
        return new CacheEntry { Size = fi.Length, MtimeUtcTicks = fi.LastWriteTimeUtc.Ticks, Sha256 = sha };
    }
}
