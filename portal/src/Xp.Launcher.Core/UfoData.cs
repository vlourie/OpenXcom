using System.Text.RegularExpressions;
using Microsoft.Win32;

namespace Xp.Launcher.Core;

/// <summary>What a folder holds of the original UFO: Enemy Unknown, and what it lacks.</summary>
public sealed record UfoCheck(string Dir, IReadOnlyList<string> Missing)
{
    public bool Ok => Missing.Count == 0;
}

/// <summary>A folder with the original game, and where the launcher found it.</summary>
public sealed record UfoFound(string Dir, string Source);

/// <summary>
/// The original UFO: Enemy Unknown / X-COM: UFO Defense data. X-Piratez is built on it
/// (master: xcom1), and it is never ours to ship: the launcher finds a copy the player owns -
/// Steam, GOG, an older OpenXcom - and copies the data folders into &lt;game&gt;/UFO.
/// The engine only counts entries in the folder (CrossPlatform::searchDataFolder), so a folder of
/// nine anything passes it; here the check is by the files Mod.cpp actually loads.
/// </summary>
public static class UfoData
{
    /// <summary>Steam app of X-COM: UFO Defense; the store page and the client link are built from it.</summary>
    public const int SteamApp = 7760;
    public static string SteamStoreUrl => $"https://store.steampowered.com/app/{SteamApp}/";
    public static string SteamClientUrl => $"steam://store/{SteamApp}";
    public const string GogUrl = "https://www.gog.com/game/xcom_ufo_defense";

    /// <summary>The folders OpenXcom reads; UFOINTRO only plays the intro and may be absent.</summary>
    public static readonly string[] DataDirs = ["GEODATA", "GEOGRAPH", "MAPS", "ROUTES", "SOUND", "TERRAIN", "UFOGRAPH", "UFOINTRO", "UNITS"];
    static readonly string[] OptionalDirs = ["UFOINTRO"];

    /// <summary>Files Mod.cpp loads by name at start: without any of them the game stops on load.</summary>
    public static readonly string[] KeyFiles =
    [
        "GEODATA/PALETTES.DAT", "GEODATA/BACKPALS.DAT", "GEODATA/LOFTEMPS.DAT", "GEODATA/INTERWIN.DAT",
        "GEODATA/SCANG.DAT", "UFOGRAPH/CURSOR.PCK", "UFOGRAPH/SPICONS.DAT",
    ];

    /// <summary>Checks a folder case-insensitively: DOS copies are upper case, repacks often are not.</summary>
    public static UfoCheck Check(string dir)
    {
        var missing = new List<string>();
        if (!Directory.Exists(dir)) return new UfoCheck(dir, ["(no folder)"]);
        foreach (var d in DataDirs)
        {
            if (OptionalDirs.Contains(d)) continue;
            var found = Find(dir, d, directory: true);
            if (found is null || !Directory.EnumerateFileSystemEntries(found).Any()) missing.Add(d + "/");
        }
        foreach (var f in KeyFiles)
        {
            var parts = f.Split('/');
            var sub = Find(dir, parts[0], directory: true);
            if (sub is null || Find(sub, parts[1], directory: false) is null) missing.Add(f);
        }
        return new UfoCheck(dir, missing.Distinct().ToList());
    }

    /// <summary>
    /// Folders that hold the game, best first, each once. A root is looked at itself and one level
    /// down in XCOM and UFO: Steam keeps the data in "XCom UFO Defense\XCOM", OpenXcom in "UFO".
    /// </summary>
    public static List<UfoFound> Probe(IEnumerable<(string Root, string Source)> roots)
    {
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var found = new List<UfoFound>();
        foreach (var (root, source) in roots)
        {
            foreach (var dir in new[] { root, Path.Combine(root, "XCOM"), Path.Combine(root, "UFO") })
            {
                string full;
                try { full = Path.GetFullPath(dir); }
                catch (Exception e) when (e is ArgumentException or NotSupportedException or PathTooLongException) { continue; }
                if (!seen.Add(full.TrimEnd(Path.DirectorySeparatorChar))) continue;
                if (Check(full).Ok) found.Add(new UfoFound(full, source));
            }
        }
        return found;
    }

    /// <summary>Everywhere the player's own copy may be on this machine; the game folder itself goes first.</summary>
    public static List<UfoFound> Search(string? gameDir = null) => Probe(Roots(gameDir));

    public static IEnumerable<(string Root, string Source)> Roots(string? gameDir)
    {
        if (!string.IsNullOrEmpty(gameDir)) yield return (Path.Combine(gameDir, "UFO"), "game");
        foreach (var lib in SteamLibraries())
            yield return (Path.Combine(lib, "steamapps", "common", "XCom UFO Defense"), "Steam");
        foreach (var dir in GogGames()) yield return (dir, "GOG");
        var docs = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments);
        if (docs.Length > 0) yield return (Path.Combine(docs, "OpenXcom"), "OpenXcom");
        var appData = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
        if (appData.Length > 0) yield return (Path.Combine(appData, "OpenXcom"), "OpenXcom");
    }

    /// <summary>Steam libraries: the client's own folder and every one listed in libraryfolders.vdf.</summary>
    public static List<string> SteamLibraries()
    {
        var libs = new List<string>();
        if (!OperatingSystem.IsWindows()) return libs;
        foreach (var steam in new[]
        {
            Reg(Registry.CurrentUser, @"Software\Valve\Steam", "SteamPath"),
            Reg(Registry.LocalMachine, @"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
            Reg(Registry.LocalMachine, @"SOFTWARE\Valve\Steam", "InstallPath"),
        })
        {
            if (string.IsNullOrEmpty(steam)) continue;
            var root = steam.Replace('/', Path.DirectorySeparatorChar);
            libs.Add(root);
            var vdf = Path.Combine(root, "steamapps", "libraryfolders.vdf");
            try { if (File.Exists(vdf)) libs.AddRange(ParseLibraryFolders(File.ReadAllText(vdf))); }
            catch (Exception e) when (e is IOException or UnauthorizedAccessException) { }
        }
        return libs.Distinct(StringComparer.OrdinalIgnoreCase).ToList();
    }

    /// <summary>The "path" values of Steam's libraryfolders.vdf; backslashes there are escaped.</summary>
    public static List<string> ParseLibraryFolders(string vdf) =>
        Regex.Matches(vdf, "\"path\"\\s+\"((?:[^\"\\\\]|\\\\.)*)\"", RegexOptions.IgnoreCase)
            .Select(m => Regex.Unescape(m.Groups[1].Value))
            .ToList();

    /// <summary>GOG Galaxy and the offline installers both register games under GOG.com\Games.</summary>
    public static List<string> GogGames()
    {
        var dirs = new List<string>();
        if (!OperatingSystem.IsWindows()) return dirs;
        foreach (var hive in new[] { @"SOFTWARE\WOW6432Node\GOG.com\Games", @"SOFTWARE\GOG.com\Games" })
        {
            try
            {
                using var games = Registry.LocalMachine.OpenSubKey(hive);
                if (games is null) continue;
                foreach (var id in games.GetSubKeyNames())
                {
                    using var g = games.OpenSubKey(id);
                    var name = g?.GetValue("gameName") as string ?? "";
                    var path = g?.GetValue("path") as string;
                    if (path is { Length: > 0 } && name.Contains("UFO", StringComparison.OrdinalIgnoreCase)
                        && !name.Contains("Terror", StringComparison.OrdinalIgnoreCase))
                        dirs.Add(path);
                }
            }
            catch (Exception e) when (e is System.Security.SecurityException or IOException or UnauthorizedAccessException) { }
        }
        return dirs;
    }

    /// <summary>
    /// Copies the data folders of a checked copy into &lt;dest&gt; (the game's UFO folder), in the
    /// upper-case names the engine looks for, and checks the result. DOS executables, DOSBox and
    /// the rest of a store install stay behind: they are not data.
    /// </summary>
    public static UfoCheck Copy(string source, string dest, IProgress<(int Done, int Total)>? progress = null)
    {
        var from = Check(source);
        if (!from.Ok) throw new InvalidOperationException($"'{source}' is not a UFO copy: missing {string.Join(", ", from.Missing)}");
        var files = new List<(string From, string To)>();
        foreach (var d in DataDirs)
        {
            var src = Find(source, d, directory: true);
            if (src is null) continue;
            foreach (var f in Directory.EnumerateFiles(src, "*", SearchOption.AllDirectories))
                files.Add((f, Path.Combine(dest, d, Path.GetRelativePath(src, f))));
        }
        for (int i = 0; i < files.Count; i++)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(files[i].To)!);
            File.Copy(files[i].From, files[i].To, overwrite: true);
            progress?.Report((i + 1, files.Count));
        }
        return Check(dest);
    }

    static string? Find(string dir, string name, bool directory)
    {
        try
        {
            var entries = directory ? Directory.EnumerateDirectories(dir) : Directory.EnumerateFiles(dir);
            return entries.FirstOrDefault(e => Path.GetFileName(e).Equals(name, StringComparison.OrdinalIgnoreCase));
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { return null; }
    }

    [System.Runtime.Versioning.SupportedOSPlatform("windows")]
    static string? Reg(RegistryKey hive, string key, string value)
    {
        try
        {
            using var k = hive.OpenSubKey(key);
            return k?.GetValue(value) as string;
        }
        catch (Exception e) when (e is System.Security.SecurityException or IOException or UnauthorizedAccessException) { return null; }
    }
}
