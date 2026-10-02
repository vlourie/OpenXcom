using Xp.Manifest;

namespace Xp.Launcher.Core;

/// <summary>What the migration did with one options.cfg.</summary>
public enum HdCoreStep
{
    Added,          // hd_core put on right before the active hd
    Activated,      // hd_core was in the list switched off (the engine adds new mods off) with hd on: switched on in place
    AlreadyOn,      // hd_core already on: nothing to do
    HdOff,          // hd off or not in the list: the build plays without HD and gets no hd_core
    Done,           // migrated before: the player's choice since then is theirs
    Unrecognized,   // the mods list is not in the engine's own layout: left as it is, to look at by hand
}

public sealed record HdCoreFile(string Path, HdCoreStep Step);

/// <summary>
/// Step 2 of the HD split (docs/portal/HD_SUBMODS.md §5): the fonts moved out of the hd pack into the mod hd_core.
/// Every options.cfg of the installation - each build's and the user/options.cfg the exe started by hand reads -
/// gets hd_core on exactly where the pack hd is on, inserted right before hd; the order of the other mods and every
/// option stay byte for byte. A file is migrated once: it is remembered in launcher/migrations/hd_core.done, and a
/// later run leaves it alone, so a player who switched hd_core off keeps it off. Never while the game runs (MULTIMOD §3.6).
/// Before each write the file and its old checksum go to launcher/migrations/hd_core.pending: a run broken off between
/// the write and the mark finds it there and marks the file done unless it still holds the old text, so the write is
/// not repeated over what the player has chosen since.
/// </summary>
public static class HdCoreMigration
{
    public const string CoreId = "hd_core";
    public const string PackId = "hd";

    public static string DoneFile(GamePaths paths) => Path.Combine(paths.StateDir, "migrations", "hd_core.done");
    public static string PendingFile(GamePaths paths) => Path.Combine(paths.StateDir, "migrations", "hd_core.pending");

    /// <summary>Runs the migration; with <paramref name="dryRun"/> reports what it would do and writes nothing.</summary>
    public static List<HdCoreFile> Run(GamePaths paths, Func<string, bool>? isGameRunning = null, bool dryRun = false) =>
        Run(paths, isGameRunning, dryRun, _ => { });

    /// <param name="checkpoint">Test seam: called at the named steps, to break the run off exactly there.</param>
    internal static List<HdCoreFile> Run(GamePaths paths, Func<string, bool>? isGameRunning, bool dryRun, Action<string> checkpoint)
    {
        var result = new List<HdCoreFile>();
        // without the mod installed an id in the list names nothing: the engine would drop it on the next save
        if (!ProfileWriter.ScanMods(paths.GameDir).Any(m => m.Id == CoreId)) return result;
        if (!dryRun && (isGameRunning ?? GameProcess.IsRunningIn)(paths.GameDir))
            throw new UpdateBlockedException("the game is running: close it to move the HD fonts to hd_core");

        var donePath = DoneFile(paths);
        var pendingPath = PendingFile(paths);
        var done = File.Exists(donePath)
            ? new HashSet<string>(File.ReadAllLines(donePath).Where(l => l.Length > 0), StringComparer.OrdinalIgnoreCase)
            : new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        void SaveDone() => FileUtil.WriteAtomic(donePath, System.Text.Encoding.UTF8.GetBytes(string.Join("\n", done.Order(StringComparer.OrdinalIgnoreCase)) + "\n"));

        // a run broken off after a write and before its mark: the write landed unless the file still holds the old
        // text; a file changed since is the migrated one, maybe switched otherwise by the player since - left as it is
        if (File.Exists(pendingPath))
        {
            var p = File.ReadAllText(pendingPath).TrimEnd('\n').Split('\t');
            var file = p.Length == 2 ? Path.Combine(paths.GameDir, p[0]) : "";
            if (p.Length == 2 && !done.Contains(p[0]) && File.Exists(file) && Hashing.Sha256Hex(File.ReadAllBytes(file)) != p[1])
            {
                done.Add(p[0]);
                if (!dryRun) SaveDone();
            }
            if (!dryRun) File.Delete(pendingPath);
        }

        foreach (var (file, key) in OptionsFiles(paths))
        {
            var rel = Path.GetRelativePath(paths.GameDir, file).Replace('\\', '/');
            if (done.Contains(rel)) { result.Add(new HdCoreFile(rel, HdCoreStep.Done)); continue; }
            var bytes = File.ReadAllBytes(file);
            var text = File.ReadAllText(file);
            var (step, after) = Migrate(text);
            result.Add(new HdCoreFile(rel, step));
            if (dryRun || step == HdCoreStep.Unrecognized) continue;
            if (after != text)
            {
                var backup = Path.Combine(paths.Backup, "hd_core", rel.Replace('/', Path.DirectorySeparatorChar));
                if (!File.Exists(backup))
                {
                    Directory.CreateDirectory(Path.GetDirectoryName(backup)!);
                    File.Copy(file, backup);
                }
                FileUtil.WriteAtomic(pendingPath, System.Text.Encoding.UTF8.GetBytes($"{rel}\t{Hashing.Sha256Hex(bytes)}\n"));
                checkpoint("pending");
                // before the file: a run broken off here writes the file again, and this then finds the record moved already
                if (key is not null) FollowProfile(paths, key, text, after);
                // the engine reads it with yaml-cpp: plain UTF-8, no BOM (R-001, the exception for game files)
                FileUtil.WriteAtomic(file, new System.Text.UTF8Encoding(false).GetBytes(after));
                checkpoint("written");
            }
            done.Add(rel);
            SaveDone();
            if (File.Exists(pendingPath)) File.Delete(pendingPath);
        }
        return result;
    }

    /// <summary>
    /// Each build's options.cfg that exists, then user/options.cfg; each file once. Key - the file's entry in the
    /// launcher's profile records (ProfileWriter.Apply's stateKey): the build's id, for user/ the master that is on.
    /// </summary>
    static IEnumerable<(string File, string? Key)> OptionsFiles(GamePaths paths)
    {
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var store = new BuildStore(paths, _ => false);
        if (store.Exists)
            foreach (var b in store.Load().Builds)
            {
                var f = Path.GetFullPath(store.OptionsFile(b));
                if (File.Exists(f) && seen.Add(f)) yield return (f, b.Id.ToLowerInvariant());
            }
        var legacy = Path.GetFullPath(Path.Combine(paths.GameDir, "user", "options.cfg"));
        if (File.Exists(legacy) && seen.Add(legacy))
        {
            var masters = ProfileWriter.ScanMods(paths.GameDir).Where(m => m.IsMaster).Select(m => m.Id).ToHashSet(StringComparer.Ordinal);
            var master = OptionsCfg.Parse(File.ReadAllText(legacy)).Mods.FirstOrDefault(m => m.Active && masters.Contains(m.Id)).Id;
            yield return (legacy, master?.ToLowerInvariant());
        }
    }

    /// <summary>
    /// The launcher's record of the mods list it wrote last (profile-mods.json) follows the migration: a list the
    /// launcher still kept stays its own, instead of reading on the next "Play" as the player's change and being
    /// left unordered from then on. A list the player had already made theirs is not recorded and stays theirs.
    /// </summary>
    static void FollowProfile(GamePaths paths, string key, string before, string after)
    {
        var state = new ProfileState(paths);
        var written = state.LoadMods();
        if (!written.TryGetValue(key, out var wrote)) return;
        var installed = ProfileWriter.ScanMods(paths.GameDir).GroupBy(m => m.Id, StringComparer.Ordinal).ToDictionary(g => g.Key, g => g.First(), StringComparer.Ordinal);
        var launchers = ProfileWriter.ModsSignature(wrote.Split('\n').Select(id => (id, true)), installed);
        if (launchers != ProfileWriter.ModsSignature(OptionsCfg.Parse(before).Mods, installed)) return;
        written[key] = ProfileWriter.ModsSignature(OptionsCfg.Parse(after).Mods, installed);
        state.SaveMods(written);
    }

    /// <summary>
    /// One options.cfg as text. Only the mods list is touched and only by inserting or flipping one line,
    /// so everything else - order, options, comments, line ends - stays as it was.
    /// </summary>
    public static (HdCoreStep Step, string Text) Migrate(string text)
    {
        var cfg = OptionsCfg.Parse(text);
        int hd = cfg.Mods.FindIndex(m => m.Id == PackId);
        int core = cfg.Mods.FindIndex(m => m.Id == CoreId);
        if (hd < 0 || !cfg.Mods[hd].Active) return (HdCoreStep.HdOff, text);
        if (core >= 0 && cfg.Mods[core].Active) return (HdCoreStep.AlreadyOn, text);

        var nl = text.Contains("\r\n") ? "\r\n" : "\n";
        var lines = text.Split('\n').ToList();   // each keeps its '\r' when the file has CRLF
        var items = Items(lines);
        if (items.Count != cfg.Mods.Count) return (HdCoreStep.Unrecognized, text);

        if (core >= 0)
        {
            var (start, end) = items[core];
            for (int i = start; i < end; i++)
            {
                var t = lines[i].TrimEnd('\r');
                var at = t.IndexOf("active: false", StringComparison.Ordinal);
                if (at < 0) continue;
                lines[i] = t[..at] + "active: true" + t[(at + "active: false".Length)..] + (lines[i].EndsWith('\r') ? "\r" : "");
                return (HdCoreStep.Activated, string.Join("\n", lines));
            }
            return (HdCoreStep.Unrecognized, text);
        }

        // the engine's layout of one item, as the item of hd itself is written
        var (hdStart, hdEnd) = items[hd];
        var block = new List<string>();
        for (int i = hdStart; i < hdEnd; i++)
        {
            var t = lines[i].TrimEnd('\r');
            var key = t.TrimStart(' ', '-').Split(':')[0];
            if (key == "id") t = t[..(t.IndexOf("id:", StringComparison.Ordinal) + 3)] + " " + CoreId;
            else if (key != "active") return (HdCoreStep.Unrecognized, text);
            block.Add(t + (nl == "\r\n" ? "\r" : ""));
        }
        lines.InsertRange(hdStart, block);
        return (HdCoreStep.Added, string.Join("\n", lines));
    }

    /// <summary>Line ranges [start, end) of the items of the mods list, in order.</summary>
    static List<(int Start, int End)> Items(List<string> lines)
    {
        var items = new List<(int, int)>();
        int i = lines.FindIndex(l => l.TrimEnd('\r', ' ') == "mods:");
        if (i < 0) return items;
        int start = -1;
        for (i++; i < lines.Count; i++)
        {
            var t = lines[i].TrimEnd('\r');
            if (t.Length > 0 && !char.IsWhiteSpace(t[0]) && !t.StartsWith('-')) break;   // the next section
            if (t.TrimStart().StartsWith("- "))
            {
                if (start >= 0) items.Add((start, i));
                start = i;
            }
            else if (t.Trim().Length == 0 || t.TrimStart().StartsWith('#'))
            {
                if (start >= 0) { items.Add((start, i)); start = -1; }
            }
        }
        if (start >= 0) items.Add((start, i));
        return items;
    }
}
