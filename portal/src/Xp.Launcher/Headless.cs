using System.Runtime.InteropServices;
using Xp.Launcher.Core;

namespace Xp.Launcher;

/// <summary>
/// XPiratezLauncher.exe --headless &lt;check|update|repair|rollback|self-update|ufo&gt; [--game &lt;dir&gt;] [--channel &lt;ch&gt;] [--repo &lt;url&gt;]
/// The same core as the window, for scripts and tests. "update" keeps player-modified files,
/// "repair" replaces them, "check" changes nothing.
/// Exit codes: 0 done / up to date, 1 error, 2 refused (signature, running game), 3 update available (check),
/// 4 the original UFO is nowhere on this machine (ufo).
/// </summary>
static partial class Headless
{
    [LibraryImport("kernel32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static partial bool AttachConsole(int pid);

    public static int Run(string[] args, Settings settings)
    {
        AttachConsole(-1);   // WinExe has no console of its own; print into the caller's
        var stdout = new StreamWriter(Console.OpenStandardOutput()) { AutoFlush = true };
        Console.SetOut(stdout);
        try { return RunAsync(args, settings).GetAwaiter().GetResult(); }
        catch (Exception e) when (e is TrustException or Xp.Manifest.ManifestException or UpdateBlockedException)
        {
            Console.WriteLine("REFUSED: " + e.Message);
            return 2;
        }
        catch (Exception e) when (e is HttpRequestException or IOException or InvalidOperationException or UnauthorizedAccessException)
        {
            Console.WriteLine("ERROR: " + e.Message);
            return 1;
        }
    }

    static string? Opt(string[] args, string name)
    {
        int i = Array.IndexOf(args, name);
        return i >= 0 && i + 1 < args.Length ? args[i + 1] : null;
    }

    /// <summary>"ufo": where the original game is on this machine, and what each place lacks. Changes nothing; 0 found, 4 not found.</summary>
    static int FindUfo(string? game)
    {
        foreach (var (root, source) in UfoData.Roots(game))
            Console.WriteLine($"{source,-9} {root}{(Directory.Exists(root) ? "" : "  (no folder)")}");
        var found = UfoData.Search(game);
        foreach (var u in found) Console.WriteLine($"FOUND {u.Source}: {u.Dir}");
        if (found.Count == 0) Console.WriteLine($"not found; Steam: {UfoData.SteamStoreUrl}  GOG: {UfoData.GogUrl}");
        return found.Count > 0 ? 0 : 4;
    }

    /// <summary>
    /// "profile [--master piratez] [--lang ru] [--screen 1440] [--profiles file] [--dry-run]": sets user/options.cfg
    /// up for the master mod by xp-profiles.json. --dry-run only prints what would change.
    /// </summary>
    static int ApplyProfile(string? game, string[] args)
    {
        if (game is null || !GamePaths.LooksLikeGameDir(game)) throw new InvalidOperationException("not a game folder: " + game);
        var file = Opt(args, "--profiles");
        var set = file is not null ? ProfileSet.Parse(File.ReadAllText(file)) : ProfileSet.Load(game)
                  ?? throw new InvalidOperationException($"no {ProfileSet.FileName} in {game}: this release has no profiles");
        var master = Opt(args, "--master") ?? "piratez";
        var profile = set.For(master) ?? throw new InvalidOperationException($"no profile for master '{master}'");
        int? screen = int.TryParse(Opt(args, "--screen"), out var h) ? h : null;
        bool dry = args.Contains("--dry-run");
        var state = new ProfileState(new GamePaths(game));
        var done = state.Load();
        var r = ProfileWriter.Apply(game, profile, ProfileWriter.ScanMods(game), Opt(args, "--lang"), screen, done, dry);
        foreach (var c in r.Changes) Console.WriteLine((dry ? "would set " : "set ") + c);
        if (r.Changes.Count == 0) Console.WriteLine("options.cfg already matches the profile");
        if (r.Backup is not null) Console.WriteLine("previous file kept as " + r.Backup);
        if (!dry) state.Save(done);
        return 0;
    }

    static async Task<int> RunAsync(string[] args, Settings settings)
    {
        var cmd = args.Length > 1 ? args[1] : "check";
        if (cmd == "ufo") return FindUfo(Opt(args, "--game") ?? settings.GameDir);
        if (cmd == "profile") return ApplyProfile(Opt(args, "--game") ?? settings.GameDir, args);
        var game = Opt(args, "--game") ?? settings.GameDir ?? throw new InvalidOperationException("no game folder: pass --game");
        if (!GamePaths.LooksLikeGameDir(game)) throw new InvalidOperationException("not a game folder: " + game);
        var paths = new GamePaths(game);
        var log = new FileLog(paths);
        log.Written += Console.WriteLine;
        using var http = RepoClient.NewHttpClient();
        var repo = new RepoClient(http, new Uri(Opt(args, "--repo") ?? settings.RepoUrl ?? BuiltIn.Defaults.RepoUrl), BuiltIn.Keys);
        var u = new Updater(paths, repo, log);
        if (u.Recover()) Console.WriteLine("an interrupted install was undone");

        var state = u.LoadState();
        if (Opt(args, "--channel") is { } ch) { state.Channel = ch; state.Save(paths); }
        if (cmd == "rollback") { u.RollbackLast(); return 0; }
        if (cmd == "self-update")
        {
            var su = new SelfUpdate(repo, settings, log);
            var m = await su.CheckAsync(state.Channel, CancellationToken.None);
            if (m is null) { Console.WriteLine($"launcher {BuiltIn.VersionText} is current"); return 0; }
            if (!SelfUpdate.AppDirWritable()) throw new InvalidOperationException("launcher folder is read-only");
            var dir = await su.PrepareAsync(m, CancellationToken.None);
            su.Apply(dir, m);
            Console.WriteLine($"launcher {m.Release.Version} handed to the bootstrapper");
            return 0;
        }

        var latest = await u.CheckAsync(state, CancellationToken.None);
        long lastPct = -1;
        var progress = new SyncProgress(p =>
        {
            var pct = p.Total > 0 ? p.Done * 100 / p.Total : 100;
            if (pct / 10 != lastPct / 10) { lastPct = pct; Console.WriteLine($"{p.Phase} {pct}%"); }
        });
        var plan = u.Scan(state, latest.Manifest, full: cmd == "repair", progress, CancellationToken.None);
        var modified = plan.PlayerModified.Select(c => c.File.Path).ToList();
        foreach (var m in modified) Console.WriteLine($"changed by player: {m}");
        if (cmd != "check" && modified.Count > 0)
        {
            // repair means "make it as released"; a plain update keeps the player's changes
            plan = u.Resolve(state, plan, cmd == "repair" ? modified.ToHashSet(StringComparer.OrdinalIgnoreCase) : new HashSet<string>());
        }
        if (!plan.ToWrite.Any() && plan.Deletes.Count == 0 && (cmd != "check" || modified.Count == 0))
        {
            Console.WriteLine($"up to date: {latest.Manifest.Release.Id}");
            return 0;
        }
        Console.WriteLine($"{latest.Manifest.Release.Id}: {plan.ToWrite.Count() + (cmd == "check" ? modified.Count : 0)} to write ({plan.DownloadBytes / (1024.0 * 1024):F1} MiB to download), {plan.Deletes.Count} to remove");
        if (cmd == "check") return 3;
        await u.DownloadAsync(plan, progress, CancellationToken.None);
        u.Install(state, plan, progress);
        Console.WriteLine($"installed {latest.Manifest.Release.Id}");
        return 0;
    }

    sealed class SyncProgress(Action<Progress> a) : IProgress<Progress>
    {
        public void Report(Progress value) => a(value);
    }
}
