using System.Runtime.InteropServices;
using Xp.Launcher.Core;

namespace Xp.Launcher;

/// <summary>
/// XPiratezLauncher.exe --headless &lt;check|update|repair|rollback|self-update&gt; [--game &lt;dir&gt;] [--channel &lt;ch&gt;] [--repo &lt;url&gt;]
/// The same core as the window, for scripts and tests. "update" keeps player-modified files,
/// "repair" replaces them, "check" changes nothing.
/// Exit codes: 0 done / up to date, 1 error, 2 refused (signature, running game), 3 update available (check).
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

    static async Task<int> RunAsync(string[] args, Settings settings)
    {
        var cmd = args.Length > 1 ? args[1] : "check";
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
