using System.Runtime.InteropServices;
using Xp.Launcher.Core;
using Xp.Manifest;

namespace Xp.Launcher;

/// <summary>
/// XPiratezLauncher.exe --headless &lt;check|update|repair|rollback|self-update|ufo|builds&gt; [--game &lt;dir&gt;] [--channel &lt;ch&gt;] [--repo &lt;url&gt;]
/// The same core as the window, for scripts and tests. "update" keeps player-modified files,
/// "repair" replaces them, "check" changes nothing.
/// Exit codes: 0 done / up to date, 1 error, 2 refused (signature, running game, the release needs a newer launcher), 3 update available (check),
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
    /// "profile [--master piratez] [--lang ru] [--screen 1440] [--profiles file] [--dry-run]": sets the options.cfg
    /// of the current build up for the master mod by xp-profiles.json; refused (2) while the game runs. --dry-run only prints what would change.
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
        var paths = new GamePaths(game);
        if (!dry && GameProcess.IsRunningIn(game))
            throw new UpdateBlockedException("the game is running: its options are not changed under it");
        // the options of the current build (the first call migrates user/options.cfg); a dry run writes nothing
        var store = new BuildStore(paths);
        var build = dry ? (store.Exists ? store.Load().Current : null) : store.Ensure(master);
        Console.WriteLine("options: " + (build?.Cfg ?? "user/") + "options.cfg");
        var state = new ProfileState(paths);
        var done = state.Load();
        var r = ProfileWriter.Apply(game, profile, ProfileWriter.ScanMods(game), Opt(args, "--lang"), screen, done, dry,
            cfgDir: build is null ? null : paths.Full(build.Cfg.TrimEnd('/')), stateKey: build?.Id);
        foreach (var c in r.Changes) Console.WriteLine((dry ? "would set " : "set ") + c);
        if (r.Changes.Count == 0) Console.WriteLine("options.cfg already matches the profile");
        if (r.Backup is not null) Console.WriteLine("previous file kept as " + r.Backup);
        if (!dry) state.Save(done);
        return 0;
    }

    /// <summary>
    /// "builds [list|new|copy|rename|delete|select|args] [--id b] [--title t] [--template piratez] [--lang ru] [--screen 1440]":
    /// the builds of the installation (docs/portal/MULTIMOD.md §3); the first call migrates user/options.cfg.
    /// "args" prints the engine arguments "Play" starts the build with, one per line: a check starts the game
    /// with them itself, out of sight. Refused (2) while the game runs.
    /// </summary>
    static int Builds(string? game, string[] args)
    {
        if (game is null || !GamePaths.LooksLikeGameDir(game)) throw new InvalidOperationException("not a game folder: " + game);
        var paths = new GamePaths(game);
        var log = new FileLog(paths);
        log.Written += Console.WriteLine;
        var store = new BuildStore(paths);
        var what = args.Length > 2 && !args[2].StartsWith("--") ? args[2] : "list";
        var current = store.Ensure(log: log);
        string Id() => Opt(args, "--id") ?? current.Id;
        string TitleArg() => Opt(args, "--title") ?? throw new InvalidOperationException("--title is needed");
        switch (what)
        {
            case "list": break;
            case "new":
                int? screen = int.TryParse(Opt(args, "--screen"), out var h) ? h : null;
                var cfg = store.OptionsFile(current);
                var lang = Opt(args, "--lang") ?? OptionsCfg.Parse(File.Exists(cfg) ? File.ReadAllText(cfg) : "").Get("language");
                Console.WriteLine("created " + store.Create(TitleArg(), Opt(args, "--template") ?? current.Template ?? "piratez", lang, screen).Id);
                break;
            case "copy": Console.WriteLine("created " + store.Copy(Id(), TitleArg()).Id); break;
            case "rename": store.Rename(Id(), TitleArg()); break;
            case "select": store.Select(Id()); break;
            case "delete": Console.WriteLine("settings kept in " + store.Delete(Id())); break;
            case "args":
                var b = store.Load().Find(Id()) ?? throw new InvalidOperationException($"no build '{Id()}'");
                foreach (var a in store.LaunchArgs(b)) Console.WriteLine(a);
                return 0;
            default: throw new InvalidOperationException("builds: list, new, copy, rename, delete, select or args");
        }
        var set = store.Load();
        foreach (var b in set.Builds)
            Console.WriteLine($"{(b.Id == set.Current?.Id ? "*" : " ")} {b.Id} | {b.Title} | {b.EngineMaster ?? "-"} | {b.Cfg}");
        return 0;
    }

    static async Task<int> RunAsync(string[] args, Settings settings)
    {
        var cmd = args.Length > 1 ? args[1] : "check";
        if (cmd == "builds") return Builds(Opt(args, "--game") ?? settings.GameDir, args);
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
        if (u.Recover()) Console.WriteLine(u.RecoveryFinished ? "an interrupted install was finished" : "an interrupted install was undone");
        if (cmd != "check") u.MigrateSettings();

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
        // a release that asks for a newer launcher is not installed by this one, as in the window (MainWindow.CheckAsync):
        // its files may need what only the newer launcher does after the install (HdCoreMigration)
        if (cmd != "check" && Version.TryParse(latest.Manifest.Release.MinLauncher, out var need) && need > BuiltIn.Version)
            throw new UpdateBlockedException($"{latest.Manifest.Release.Id} needs launcher {need}, this is {BuiltIn.VersionText}: run self-update first");
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
