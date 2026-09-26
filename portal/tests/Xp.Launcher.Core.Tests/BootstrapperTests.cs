using System.Diagnostics;
using Xp.Launcher.Core;
using Xp.Manifest;
using Boot = Xp.Bootstrapper.Program;

namespace Xp.Launcher.Core.Tests;

/// <summary>
/// xp-bootstrap swaps the launcher's own files after it exits (audit P-9). The swap runs here in-process;
/// only starting the new launcher is stubbed - the stub writes the confirmation marker, or does not.
/// </summary>
public sealed class BootstrapperTests : IDisposable
{
    readonly string _root = Path.Combine(Path.GetTempPath(), "xp-boot-" + Guid.NewGuid().ToString("N")[..8]);
    string Target => Path.Combine(_root, "launcher");
    string Source => Path.Combine(_root, "update");
    readonly List<bool> _starts = [];

    public BootstrapperTests()
    {
        Write(Target, "xp-launcher.exe", "old exe");
        Write(Target, "lib/core.dll", "old core");
        Write(Target, "keep.txt", "not part of the update");
        Write(Source, "xp-launcher.exe", "new exe");
        Write(Source, "lib/core.dll", "new core");
        Write(Source, "lib/added.dll", "new file");
    }

    public void Dispose()
    {
        Boot.StartOverride = null;
        Boot.ConfirmWait = TimeSpan.FromSeconds(30);
        try { Directory.Delete(_root, true); } catch (IOException) { }
    }

    static void Write(string dir, string rel, string text)
    {
        var p = Path.Combine(dir, rel);
        Directory.CreateDirectory(Path.GetDirectoryName(p)!);
        File.WriteAllText(p, text);
    }

    string Read(string rel) => File.ReadAllText(Path.Combine(Target, rel));

    Boot.Job Job(params string[] extra) => Boot.Parse([
        "--pid", "0", "--source", Source, "--target", Target, "--exe", "xp-launcher.exe",
        "--file", "xp-launcher.exe", "--file", "lib/core.dll", "--file", "lib/added.dll", .. extra]);

    /// <summary>The new launcher: records the start and confirms it if <paramref name="confirms"/>.</summary>
    void Launcher(bool confirms) => Boot.StartOverride = (job, updated) =>
    {
        lock (_starts) _starts.Add(updated);
        if (updated && confirms) File.WriteAllText(Path.Combine(job.Target, ".update-ok"), "");
        return null;
    };

    [Fact]
    public void A_confirmed_update_keeps_the_new_files_and_cleans_up()
    {
        Launcher(confirms: true);
        Assert.Equal(0, Boot.Run(Job()));
        Assert.Equal("new exe", Read("xp-launcher.exe"));
        Assert.Equal("new core", Read("lib/core.dll"));
        Assert.Equal("new file", Read("lib/added.dll"));
        Assert.Equal("not part of the update", Read("keep.txt"));
        Assert.Equal([true], _starts);
        Assert.Empty(Directory.GetDirectories(Target, ".old-*"));
        Assert.False(File.Exists(Path.Combine(Target, ".update-ok")));
        Assert.False(Directory.Exists(Source));
    }

    [Fact]
    public void A_new_launcher_that_never_confirms_is_rolled_back_and_the_old_one_started()
    {
        Launcher(confirms: false);
        Boot.ConfirmWait = TimeSpan.FromSeconds(1);
        Assert.Equal(4, Boot.Run(Job()));
        Assert.Equal("old exe", Read("xp-launcher.exe"));
        Assert.Equal("old core", Read("lib/core.dll"));
        Assert.False(File.Exists(Path.Combine(Target, "lib/added.dll")));   // new in this update: gone again
        Assert.Equal("not part of the update", Read("keep.txt"));
        Assert.Equal([true, false], _starts);
        Assert.Empty(Directory.GetDirectories(Target, ".old-*"));
        Assert.True(Directory.Exists(Source));   // the prepared files stay for the next attempt
    }

    [Fact]
    public void A_swap_that_breaks_off_restores_what_it_had_replaced()
    {
        Launcher(confirms: true);
        // listed after two good files, missing from the prepared folder: the swap stops on it
        Assert.Equal(3, Boot.Run(Job("--file", "lib/missing.dll")));
        Assert.Equal("old exe", Read("xp-launcher.exe"));
        Assert.Equal("old core", Read("lib/core.dll"));
        Assert.False(File.Exists(Path.Combine(Target, "lib/added.dll")));
        Assert.Equal([false], _starts);
        Assert.Empty(Directory.GetDirectories(Target, ".old-*"));
    }

    [Theory]
    [InlineData("../outside.exe")]
    [InlineData("C:/Windows/evil.dll")]
    [InlineData("lib/../../outside.dll")]
    public void A_path_that_leaves_the_launcher_folder_is_refused_before_anything_moves(string file)
    {
        Assert.Throws<UnsafePathException>(() => Job("--file", file));
        Assert.Equal("old exe", Read("xp-launcher.exe"));
    }

    [Fact]
    public void Arguments_that_do_not_make_a_job_are_refused()
    {
        Assert.Throws<ArgumentException>(() => Boot.Parse(["--source", Source, "--target", Target, "--exe", "xp-launcher.exe"]));   // no files
        Assert.Throws<ArgumentException>(() => Boot.Parse(["--source", Source, "--target", Target, "--exe", "other.exe", "--file", "lib/core.dll"]));
        Assert.Throws<ArgumentException>(() => Boot.Parse(["--bogus", "1"]));
    }
}

/// <summary>
/// The launcher refuses to update while the game runs; its own folder (launcher/) does not count, or it
/// would block itself (audit P-9). Real processes: a copy of cmd.exe waiting on ping, started from a folder.
/// </summary>
public sealed class GameProcessTests : IDisposable
{
    readonly string _root = Path.Combine(Path.GetTempPath(), "xp-running-" + Guid.NewGuid().ToString("N")[..8]);
    readonly List<Process> _started = [];

    public void Dispose()
    {
        foreach (var p in _started)
        {
            try { p.Kill(entireProcessTree: true); p.WaitForExit(5000); } catch (InvalidOperationException) { }
            p.Dispose();
        }
        try { Directory.Delete(_root, true); } catch (Exception e) when (e is IOException or UnauthorizedAccessException) { }
    }

    /// <summary>Starts a copy of cmd.exe from <paramref name="dir"/>; it lives about a minute.</summary>
    void RunFrom(string dir)
    {
        Directory.CreateDirectory(dir);
        var exe = Path.Combine(dir, "game.exe");
        File.Copy(Path.Combine(Environment.SystemDirectory, "cmd.exe"), exe);
        var psi = new ProcessStartInfo(exe, "/c ping -n 60 127.0.0.1 >nul") { UseShellExecute = false, CreateNoWindow = true };
        var p = Process.Start(psi)!;
        _started.Add(p);
        // a process just started has no module list yet, and IsRunningIn would skip it
        var sw = Stopwatch.StartNew();
        while (true)
        {
            try { if (p.MainModule is not null) return; }
            catch (Exception e) when (e is System.ComponentModel.Win32Exception or InvalidOperationException) { }
            if (sw.Elapsed > TimeSpan.FromSeconds(10)) throw new TimeoutException("the test process never showed its module");
            Thread.Sleep(50);
        }
    }

    [Fact]
    public void A_process_from_the_game_folder_counts_one_from_its_launcher_folder_does_not()
    {
        var game = Path.Combine(_root, "game");
        var other = Path.Combine(_root, "game-old");   // shares the prefix, not the folder
        Directory.CreateDirectory(game);
        Assert.False(GameProcess.IsRunningIn(game));

        RunFrom(Path.Combine(game, "launcher"));
        RunFrom(other);
        Assert.False(GameProcess.IsRunningIn(game));

        RunFrom(Path.Combine(game, "bin"));
        Assert.True(GameProcess.IsRunningIn(game));
        Assert.True(GameProcess.IsRunningIn(game + Path.DirectorySeparatorChar));
        Assert.True(GameProcess.IsRunningIn(other));
    }
}
