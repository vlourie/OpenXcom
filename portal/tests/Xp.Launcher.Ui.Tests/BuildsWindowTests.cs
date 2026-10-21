using System.Diagnostics;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Headless;
using Avalonia.Headless.XUnit;
using Avalonia.Input;
using Avalonia.Threading;
using Xp.Launcher;
using Xunit.Abstractions;

[assembly: AvaloniaTestApplication(typeof(Xp.Launcher.Ui.Tests.TestApp))]

namespace Xp.Launcher.Ui.Tests;

public static class TestApp
{
    // the launcher's own App: its fonts, theme and styles; Skia renders the frames the tests save
    public static AppBuilder BuildAvaloniaApp() => AppBuilder.Configure<App>()
        .UseSkia()
        .UseHeadless(new AvaloniaHeadlessPlatformOptions { UseHeadlessDrawing = false });
}

/// <summary>
/// The builds in the launcher window (docs/portal/MULTIMOD.md §7): the switcher, a new build, a copy, the choice kept
/// over a restart, and the controls locked while the game runs. The window is the real MainWindow, off screen; clicks go
/// through hit-testing, so a disabled button does nothing. Frames go to XP_UI_SHOTS when it is set.
/// </summary>
public sealed class BuildsWindowTests : IDisposable
{
    const string PlayerCfg =
        "mods:\n  - active: false\n    id: xcom1\n  - active: true\n    id: piratez\n  - active: true\n    id: hd\n" +
        "options:\n  battleScrollSpeed: 21\n  language: ru\n  oxceHdMode: 2\n  oxceRecommendedOptionsWereSet: true\n";
    const string Profiles =
        "{ \"schema\": 1, \"profiles\": [ { \"master\": \"piratez\", \"version\": 1,\n" +
        "  \"mods\": [ { \"id\": \"*\" }, { \"id\": \"hd\" } ],\n" +
        "  \"options\": [ { \"key\": \"oxceHdMode\", \"value\": \"2\", \"needsMod\": \"hd\" },\n" +
        "                 { \"key\": \"battleAutoEnd\", \"value\": \"true\", \"mode\": \"fixed\" } ] } ] }";

    readonly ITestOutputHelper _out;
    readonly string _root = Path.Combine(Path.GetTempPath(), "xp-ui-tests", Guid.NewGuid().ToString("N"));
    readonly string _shots;
    Process? _sleeper;
    string Game => Path.Combine(_root, "game");

    public BuildsWindowTests(ITestOutputHelper output)
    {
        _out = output;
        _shots = Environment.GetEnvironmentVariable("XP_UI_SHOTS") is { Length: > 0 } s ? s : Path.Combine(_root, "shots");
        Directory.CreateDirectory(_shots);
        Write("standard/xcom1/metadata.yml", "id: xcom1\nisMaster: true\n");
        Write("user/mods/Piratez/metadata.yml", "id: piratez\nname: X-Piratez\nisMaster: true\nmaster: xcom1\n");
        Write("user/mods/hd/metadata.yml", "id: hd\nmaster: \"*\"\n");
        Write("common/readme.txt", "");
        Write("xp-profiles.json", Profiles);
        Write("user/options.cfg", PlayerCfg);
        Write("user/piratez/save1.sav", "a save");
        // the "game": any program whose exe lies in the game folder is a running game to the launcher (GameProcess.IsRunningIn)
        File.Copy(Path.Combine(Environment.SystemDirectory, "PING.EXE"), Path.Combine(Game, "openxcom_hd.exe"));
        // the launcher's own settings in a folder of the test: never the player's
        Settings.DirOverride = Path.Combine(_root, "settings");
        // a dead address: the start-up check fails at once and the window goes idle offline
        new Settings { GameDir = Game, RepoUrl = "http://127.0.0.1:9/", Language = "ru" }.Save();
        L.Use("ru");
    }

    public void Dispose()
    {
        try { if (_sleeper is { HasExited: false }) _sleeper.Kill(); } catch (InvalidOperationException) { }
        Settings.DirOverride = null;
        try { Directory.Delete(_root, recursive: true); } catch (IOException) { } catch (UnauthorizedAccessException) { }
    }

    void Write(string rel, string text)
    {
        var p = Path.Combine(Game, rel);
        Directory.CreateDirectory(Path.GetDirectoryName(p)!);
        File.WriteAllText(p, text);
    }

    // ------------------------------------------------------------- window helpers

    static T F<T>(object o, string name) =>
        (T)o.GetType().GetField(name, BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(o)!;

    static void Pump(Func<bool> until, string what, int ms = 20000)
    {
        var sw = Stopwatch.StartNew();
        while (!until())
        {
            Dispatcher.UIThread.RunJobs();
            AvaloniaHeadlessPlatform.ForceRenderTimerTick();
            if (sw.ElapsedMilliseconds > ms) throw new TimeoutException("waited for " + what);
            Thread.Sleep(10);
        }
        Dispatcher.UIThread.RunJobs();
    }

    static void Settle()
    {
        for (int i = 0; i < 5; i++) { Dispatcher.UIThread.RunJobs(); AvaloniaHeadlessPlatform.ForceRenderTimerTick(); }
    }

    /// <summary>A real left click in the middle of the control: through hit-testing, so a disabled one ignores it.</summary>
    static void Click(Control c)
    {
        c.BringIntoView();
        Settle();
        var top = TopLevel.GetTopLevel(c)!;
        var p = c.TranslatePoint(new Point(c.Bounds.Width / 2, c.Bounds.Height / 2), top)!.Value;
        top.MouseMove(p, RawInputModifiers.None);
        top.MouseDown(p, MouseButton.Left, RawInputModifiers.None);
        top.MouseUp(p, MouseButton.Left, RawInputModifiers.None);
        Settle();
    }

    /// <summary>The player was in another window (the game) and comes back to the launcher.</summary>
    static void ComeBack(Window w)
    {
        var other = new Window { Width = 200, Height = 100 };
        other.Show();
        other.Activate();
        Settle();
        other.Close();
        w.Activate();
        Settle();
    }

    void Shot(TopLevel top, string name)
    {
        Settle();
        var frame = top.CaptureRenderedFrame();
        if (frame is null) { _out.WriteLine("no frame for " + name); return; }
        var path = Path.Combine(_shots, name + ".png");
        frame.Save(path);
        _out.WriteLine("frame: " + path);
    }

    MainWindow Open()
    {
        var w = new MainWindow([]) { WindowState = WindowState.Normal, Width = 1280, Height = 820 };
        w.Show();
        // the start-up: the game folder, the first-start migration, then the update check against the dead address
        Pump(() => F<object?>(w, "_updater") is not null && F<object>(w, "_work").ToString() == "None"
                   && F<ComboBox>(w, "_build").IsEnabled, "the window to go idle");
        return w;
    }

    /// <summary>Types the name into the dialog the click opened and presses Enter in it.</summary>
    Window Dialog(MainWindow w, string shot)
    {
        Pump(() => w.OwnedWindows.Count > 0, "the name dialog");
        var d = w.OwnedWindows[0];
        Settle();
        Shot(d, shot);
        return d;
    }

    static void Answer(Window d, string text)
    {
        d.KeyTextInput(text);   // the dialog opens with its text selected: typing replaces it
        Settle();
        d.KeyPress(Key.Enter, RawInputModifiers.None, PhysicalKey.Enter, null);
        Settle();
    }

    JsonElement BuildsJson() => JsonDocument.Parse(File.ReadAllBytes(Path.Combine(Game, "launcher", "builds.json"))).RootElement;
    string Last() => BuildsJson().GetProperty("last").GetString()!;
    List<(string Id, string Title)> Builds() =>
        BuildsJson().GetProperty("builds").EnumerateArray().Select(b => (b.GetProperty("id").GetString()!, b.GetProperty("title").GetString()!)).ToList();
    static List<string> Items(ComboBox c) => c.Items.Cast<ComboBoxItem>().Select(i => (string)i.Content!).ToList();
    static string Hash(string file) => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(file)));
    string Cfg(string id) => Path.Combine(Game, "user", "builds", id, "options.cfg");

    // ------------------------------------------------------------------- tests

    [AvaloniaFact]
    public void Switcher_new_copy_and_the_choice_kept_over_a_restart()
    {
        var legacy = Hash(Path.Combine(Game, "user", "options.cfg"));
        var w = Open();
        var combo = F<ComboBox>(w, "_build");
        // the first start migrated: one build, chosen, named after the master mod
        Assert.Equal(["X-Piratez"], Items(combo));
        Assert.Equal(0, combo.SelectedIndex);
        Assert.Equal("piratez", Last());
        Shot(w, "1-home-first-start");

        Click(F<Dictionary<string, Button>>(w, "_nav")["settings"]);
        Shot(w, "2-settings-builds");

        // a new build by its button: the name dialog, the build from the profile, chosen at once
        Click(F<Button>(w, "_buildNew"));
        Answer(Dialog(w, "3-new-build-dialog"), "Испытание");
        Pump(() => Builds().Count == 2 && w.OwnedWindows.Count == 0, "the new build");
        var created = Builds().Single(b => b.Title == "Испытание").Id;
        Assert.True(File.Exists(Cfg(created)));
        Assert.Equal(created, Last());
        Assert.Equal(["X-Piratez", "Испытание"], Items(combo));
        Assert.Equal(1, combo.SelectedIndex);

        // a copy of the chosen build: the same settings byte for byte
        Click(F<Button>(w, "_buildCopy"));
        Answer(Dialog(w, "4-copy-dialog"), "Копия испытания");
        Pump(() => Builds().Count == 3 && w.OwnedWindows.Count == 0, "the copy");
        var copy = Builds().Single(b => b.Title == "Копия испытания").Id;
        Assert.Equal(Hash(Cfg(created)), Hash(Cfg(copy)));
        Assert.Equal(["X-Piratez", "Испытание", "Копия испытания"], Items(combo));
        Shot(w, "5-settings-three-builds");

        // the list in Settings: every build, the chosen one lit; a click on a row picks it like the switcher
        var list = F<StackPanel>(w, "_buildList");
        Assert.Equal(3, list.Children.Count);
        Assert.Equal("✓  Копия испытания", (string)((Button)list.Children[2]).Content!);
        Click((Button)list.Children[1]);
        Pump(() => Last() == created, "the pick from the list");
        Assert.Equal(1, combo.SelectedIndex);
        Assert.Equal("✓  Испытание", (string)((Button)F<StackPanel>(w, "_buildList").Children[1]).Content!);
        Shot(w, "5b-settings-picked-from-list");

        // the switcher on the home page: open the list, click the first build
        Click(F<Dictionary<string, Button>>(w, "_nav")["home"]);
        Click(combo);
        Pump(() => combo.IsDropDownOpen, "the list to open");
        Shot(w, "6-switcher-open");
        Click((Control)combo.ContainerFromIndex(0)!);
        Pump(() => Last() == "piratez", "the choice saved");
        Assert.Equal(0, combo.SelectedIndex);
        Shot(w, "7-home-switched");
        w.Close();
        Settle();

        // a new launcher start: the choice is where the player left it
        var w2 = Open();
        var combo2 = F<ComboBox>(w2, "_build");
        Assert.Equal(["X-Piratez", "Испытание", "Копия испытания"], Items(combo2));
        Assert.Equal("piratez", (string)((ComboBoxItem)combo2.SelectedItem!).Tag!);
        Shot(w2, "8-after-restart");
        // the same again with another choice, so the first build is not just the default
        Click(combo2);
        Pump(() => combo2.IsDropDownOpen, "the list to open");
        Click((Control)combo2.ContainerFromIndex(2)!);
        Pump(() => Last() == copy, "the choice saved");
        w2.Close();
        Settle();
        var w3 = Open();
        Assert.Equal(copy, (string)((ComboBoxItem)F<ComboBox>(w3, "_build").SelectedItem!).Tag!);
        Shot(w3, "9-after-second-restart");
        w3.Close();

        // the file the exe started by hand reads is never touched
        Assert.Equal(legacy, Hash(Path.Combine(Game, "user", "options.cfg")));
    }

    [AvaloniaFact]
    public void Under_a_running_game_the_builds_are_locked_in_the_window()
    {
        var w = Open();
        Click(F<Dictionary<string, Button>>(w, "_nav")["settings"]);
        var combo = F<ComboBox>(w, "_build");
        Button[] buttons = [F<Button>(w, "_buildNew"), F<Button>(w, "_buildCopy"), F<Button>(w, "_buildRename"), F<Button>(w, "_buildDelete")];
        Button[] update = [F<Button>(w, "_updateOnly"), F<Button>(w, "_components"), F<Button>(w, "_resetProfile")];
        // control: with the game closed everything is on
        Assert.True(combo.IsEnabled);
        Assert.All(buttons, b => Assert.True(b.IsEnabled));
        Assert.All(update, b => Assert.True(b.IsEnabled));

        // the game starts outside the launcher (its own exe), the player comes back to the launcher window
        _sleeper = Process.Start(new ProcessStartInfo(Path.Combine(Game, "openxcom_hd.exe"), "-n 600 127.0.0.1")
            { UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true })!;
        Pump(() => Xp.Launcher.Core.GameProcess.IsRunningIn(Game), "the game process");
        ComeBack(w);
        Pump(() => !combo.IsEnabled, "the lock");
        Assert.All(buttons, b => Assert.False(b.IsEnabled));
        Assert.All(F<StackPanel>(w, "_buildList").Children, r => Assert.False(r.IsEnabled));
        Assert.All(update, b => Assert.False(b.IsEnabled));
        Shot(w, "10-settings-locked-under-game");

        var before = Directory.EnumerateFiles(Game, "*", SearchOption.AllDirectories)
            .Where(p => !p.Contains(Path.DirectorySeparatorChar + "logs" + Path.DirectorySeparatorChar))
            .ToDictionary(p => p, Hash);
        foreach (var b in buttons) Click(b);
        Assert.Empty(w.OwnedWindows);   // no name dialog, no confirmation: the clicks did nothing
        Click(F<Dictionary<string, Button>>(w, "_nav")["home"]);
        Click(combo);
        Assert.False(combo.IsDropDownOpen);
        Shot(w, "11-home-locked-under-game");
        var after = Directory.EnumerateFiles(Game, "*", SearchOption.AllDirectories)
            .Where(p => !p.Contains(Path.DirectorySeparatorChar + "logs" + Path.DirectorySeparatorChar))
            .ToDictionary(p => p, Hash);
        Assert.Equal(before, after);

        // the game closes: back in the window, everything is on again
        _sleeper.Kill();
        _sleeper.WaitForExit();
        ComeBack(w);
        Pump(() => combo.IsEnabled, "the unlock");
        Assert.All(buttons, b => Assert.True(b.IsEnabled));
        Shot(w, "12-home-unlocked");
        w.Close();
    }

    [AvaloniaFact]
    public void Whats_new_lists_every_release_since_the_players_version()
    {
        var w = Open();
        static Xp.Manifest.ReleaseNote Note(string v, string text) => new() { Version = v, Changelog = { ["ru"] = text, ["en"] = text } };
        var notes = new Xp.Manifest.ChannelNotes
        {
            Releases = [Note("2026.10.21-2", "- Радары: волны по очереди"), Note("2026.10.21", "- План базы: постройки в своей клетке"),
                        Note("2026.10.20-17", "- Экраны базы: картинки по темам"), Note("2026.10.20-16", "- Старое")],
        };
        var m = new Xp.Manifest.ReleaseManifest { Release = { Version = "2026.10.21-2", Changelog = { ["ru"] = "- Радары: волны по очереди" } } };
        var show = typeof(MainWindow).GetMethod("ShowRelease", BindingFlags.Instance | BindingFlags.NonPublic)!;
        var title = F<TextBlock>(w, "_whatsNewTitle");
        var list = F<StackPanel>(w, "_changelog");

        // an update waits: the player has 2026.10.20-16, three releases come with it
        show.Invoke(w, [m, notes, "2026.10.20-16"]);
        Settle();
        Assert.Equal(L.T("home.whatsNewSince", "2026.10.20-16"), title.Text);
        Assert.Equal(3, list.Children.Count);
        Shot(w, "14-whats-new-since");

        // no history (an old repository, no network): the latest manifest's own text, as before
        show.Invoke(w, [m, null, "2026.10.20-16"]);
        Settle();
        Assert.Equal(L.T("home.whatsNew", "2026.10.21-2"), title.Text);
        Assert.Single(list.Children);
        w.Close();
    }

    Process Sleeper(string args) => Process.Start(new ProcessStartInfo(Path.Combine(Game, "openxcom_hd.exe"), args)
        { UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true })!;

    /// <summary>As if "Play" had started this process: the window follows it.</summary>
    static void Follow(MainWindow w, Process game)
    {
        typeof(MainWindow).GetField("_game", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(w, game);
        typeof(MainWindow).GetMethod("FollowGame", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(w, null);
        Settle();
    }

    [AvaloniaFact]
    public void While_the_game_runs_the_window_waits_in_the_tray()
    {
        var w = Open();
        Assert.True(F<Settings>(w, "_settings").TrayWhilePlaying);   // on by default

        // a clean exit (code 0): the window is in the tray while the game runs, then back without an error line
        var clean = Sleeper("-n 3 127.0.0.1");
        Follow(w, clean);
        Assert.False(w.IsVisible);
        var tray = F<TrayIcon>(w, "_tray");
        Assert.True(tray.IsVisible);
        Assert.Equal(L.T("tray.playing"), tray.ToolTipText);
        Assert.False(F<NativeMenuItem>(w, "_trayLeave").IsVisible);   // not in a room: nothing to leave
        Pump(() => w.IsVisible, "the window back after the game");
        Assert.Null(F<object?>(w, "_game"));
        Assert.False(tray.IsVisible);
        Assert.Null(F<string?>(w, "_gameFailed"));

        // a crash (here the process killed, code -1): back with the code on the home page
        _sleeper = Sleeper("-n 600 127.0.0.1");
        Follow(w, _sleeper);
        Assert.False(w.IsVisible);
        _sleeper.Kill();
        Pump(() => w.IsVisible, "the window back after the crash");
        Assert.False(tray.IsVisible);
        Assert.Equal(L.T("main.gameFailed", "0xFFFFFFFF"), F<string?>(w, "_gameFailed"));
        Shot(w, "13-home-after-crash");

        // the option off: the window stays where it is, no tray icon
        F<Settings>(w, "_settings").TrayWhilePlaying = false;
        _sleeper = Sleeper("-n 600 127.0.0.1");
        Follow(w, _sleeper);
        Assert.True(w.IsVisible);
        Assert.False(tray.IsVisible);
        _sleeper.Kill();
        Pump(() => F<object?>(w, "_game") is null, "the game's exit");
        Assert.True(w.IsVisible);

        // "Play" for real: the "game" (ping) is given -user and -cfg it does not know and ends at once with code 1
        F<Settings>(w, "_settings").TrayWhilePlaying = true;
        Click(F<Button>(w, "_main"));
        Pump(() => F<object?>(w, "_game") is null && w.IsVisible && F<string?>(w, "_gameFailed") == L.T("main.gameFailed", "1"), "the exit of the game Play started");
        Assert.False(tray.IsVisible);
        w.Close();
    }

    [AvaloniaFact]
    public void The_cross_hides_the_launcher_to_the_tray_and_the_tray_brings_it_back()
    {
        var w = Open();
        var settings = F<Settings>(w, "_settings");
        Assert.True(settings.CloseToTray);   // on by default
        Assert.False(settings.CloseToTrayTold);

        // what the cross does (a headless window has no real cross: Closing with WindowClosing comes only from the system)
        typeof(MainWindow).GetMethod("CloseToTray", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(w, null);
        Assert.False(w.IsVisible);
        var tray = F<TrayIcon>(w, "_tray");
        Assert.True(tray.IsVisible);
        Assert.Equal(L.T("tray.idle"), tray.ToolTipText);
        Assert.False(F<NativeMenuItem>(w, "_trayLeave").IsVisible);
        Assert.True(Settings.Load().CloseToTrayTold);   // the hint once, remembered on disk

        // what "Open" in the tray menu and a click on the icon do
        typeof(MainWindow).GetMethod("ShowWindow", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(w, null);
        Assert.True(w.IsVisible);
        Assert.False(tray.IsVisible);
        Assert.False(F<bool>(w, "_closedToTray"));

        // a programmatic close (the self-update, the tray's "Close the launcher") closes for real
        w.Close();
        Assert.False(w.IsVisible);
        Assert.False(tray.IsVisible);
    }
}
