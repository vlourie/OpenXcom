namespace Xp.Launcher.Core;

/// <summary>
/// The original Terror from the Deep data, for games on the xcom2 master (TWoTS). Like UFO, never ours to ship: the
/// launcher finds the player's copy - Steam keeps it in "X-COM Terror from the Deep\TFD" - and copies the data folders
/// into &lt;game&gt;/TFTD. The engine takes the first TFTD folder with at least 9 entries (CrossPlatform::searchDataFolder),
/// so the check counts them too: X-Piratez ships that folder with a README alone.
/// </summary>
public static class TftdData
{
    public const int SteamApp = 7650;
    public static string SteamStoreUrl => $"https://store.steampowered.com/app/{SteamApp}/";
    public const string GogUrl = "https://www.gog.com/game/xcom_terror_from_the_deep";
    public const string Folder = "TFTD";

    /// <summary>The folders OpenXcom reads for TFTD; ANIMS and FLOP_INT only play the intro.</summary>
    public static readonly string[] DataDirs = ["ANIMS", "FLOP_INT", "GEODATA", "GEOGRAPH", "MAPS", "ROUTES", "SOUND", "TERRAIN", "UFOGRAPH", "UNITS"];
    static readonly string[] OptionalDirs = ["ANIMS", "FLOP_INT"];
    const int EngineMinEntries = 9;

    public static UfoCheck Check(string dir)
    {
        var c = UfoData.Check(dir, DataDirs, OptionalDirs, UfoData.KeyFiles);
        if (!c.Ok || Directory.EnumerateFileSystemEntries(dir).Count() >= EngineMinEntries) return c;
        return new UfoCheck(dir, [$"(fewer than {EngineMinEntries} entries: the engine would not take the folder)"]);
    }

    /// <summary>Folders that hold TFTD, best first: the game's own, Steam, GOG, an older OpenXcom.</summary>
    public static List<UfoFound> Search(string? gameDir = null)
    {
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var found = new List<UfoFound>();
        foreach (var (root, source) in Roots(gameDir))
            foreach (var dir in new[] { root, Path.Combine(root, "TFD"), Path.Combine(root, Folder) })
            {
                string full;
                try { full = Path.GetFullPath(dir); }
                catch (Exception e) when (e is ArgumentException or NotSupportedException or PathTooLongException) { continue; }
                if (seen.Add(full.TrimEnd(Path.DirectorySeparatorChar)) && UfoData.Check(full, DataDirs, OptionalDirs, UfoData.KeyFiles).Ok)
                    found.Add(new UfoFound(full, source));
            }
        return found;
    }

    public static IEnumerable<(string Root, string Source)> Roots(string? gameDir)
    {
        if (!string.IsNullOrEmpty(gameDir)) yield return (Path.Combine(gameDir, Folder), "game");
        foreach (var lib in UfoData.SteamLibraries())
            yield return (Path.Combine(lib, "steamapps", "common", "X-COM Terror from the Deep"), "Steam");
        foreach (var dir in UfoData.GogGames(name => name.Contains("Terror", StringComparison.OrdinalIgnoreCase))) yield return (dir, "GOG");
        var docs = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments);
        if (docs.Length > 0) yield return (Path.Combine(docs, "OpenXcom"), "OpenXcom");
        var appData = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
        if (appData.Length > 0) yield return (Path.Combine(appData, "OpenXcom"), "OpenXcom");
    }

    /// <summary>Copies the data folders of a found copy into &lt;game&gt;/TFTD and checks the result as the engine will.</summary>
    public static UfoCheck Copy(string source, string gameDir, IProgress<(int Done, int Total)>? progress = null)
    {
        var dest = Path.Combine(gameDir, Folder);
        UfoData.Copy(source, dest, progress, "TFTD", d => UfoData.Check(d, DataDirs, OptionalDirs, UfoData.KeyFiles), DataDirs);
        return Check(dest);
    }
}
