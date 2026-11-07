using System.Diagnostics;
using System.Reflection;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Headless;
using Avalonia.Headless.XUnit;
using Avalonia.Input;
using Avalonia.Threading;
using Avalonia.VisualTree;
using Xp.Launcher;
using Xunit.Abstractions;

namespace Xp.Launcher.Ui.Tests;

/// <summary>
/// Frames of the launcher in English for the mod.io page (docs/research/modio-launcher-page-2026-10-27.md): every page
/// of the real window and the game picker of a new build. Runs only when XP_PROMO_SHOTS names the folder for the frames;
/// XP_PROMO_REPO (the release repository) lets the window see the real updates and news instead of going offline.
/// </summary>
public sealed class PromoShotsTests : IDisposable
{
    const string PlayerCfg =
        "mods:\n  - active: false\n    id: xcom1\n  - active: true\n    id: piratez\n  - active: true\n    id: hd\n" +
        "options:\n  language: en-US\n  oxceHdMode: 2\n  oxceRecommendedOptionsWereSet: true\n";

    readonly ITestOutputHelper _out;
    readonly string _root = Path.Combine(Path.GetTempPath(), "xp-ui-tests", "promo-" + Guid.NewGuid().ToString("N"));
    readonly string? _shots = Environment.GetEnvironmentVariable("XP_PROMO_SHOTS") is { Length: > 0 } s ? s : null;
    string Game => Path.Combine(_root, "game");

    public PromoShotsTests(ITestOutputHelper output)
    {
        _out = output;
        if (_shots is null) return;
        Directory.CreateDirectory(_shots);
        Write("standard/xcom1/metadata.yml", "id: xcom1\nisMaster: true\n");
        Write("user/mods/Piratez/metadata.yml", "id: piratez\nname: X-Piratez\nisMaster: true\nmaster: xcom1\n");
        Write("user/mods/hd/metadata.yml", "id: hd\nname: X-Piratez HD\nmaster: \"*\"\n");
        Write("common/readme.txt", "");
        Write("user/options.cfg", PlayerCfg);
        // the game folder is known by its exe; nothing here starts it
        File.Copy(Path.Combine(Environment.SystemDirectory, "PING.EXE"), Path.Combine(Game, "openxcom_hd.exe"));
        // a player on the newest release, scanned a minute ago: the home page as it is between updates
        var release = Environment.GetEnvironmentVariable("XP_PROMO_RELEASE") is { Length: > 0 } rel ? rel : "2026.10.27-2";
        Write("launcher/state.json",
            $"{{\"channel\":\"stable\",\"installedReleaseId\":\"{release}\",\"installedVersion\":\"{release.Replace('-', '.')}\"," +
            $"\"lastScanUtc\":\"{DateTime.UtcNow.AddMinutes(-1):O}\",\"lastScanReleaseId\":\"{release}\"}}");
        // the games of the release as they are: the picker shows each with its download from mod.io
        var profiles = Path.Combine(Repo(), "portal", "profiles", "xp-profiles.json");
        File.Copy(profiles, Path.Combine(Game, "xp-profiles.json"));
        Settings.DirOverride = Path.Combine(_root, "settings");
        var repo = Environment.GetEnvironmentVariable("XP_PROMO_REPO") is { Length: > 0 } r ? r : "http://127.0.0.1:9/";
        new Settings { GameDir = Game, RepoUrl = repo, Language = "en" }.Save();
        L.Use("en");
    }

    public void Dispose()
    {
        Settings.DirOverride = null;
        try { Directory.Delete(_root, recursive: true); } catch (IOException) { } catch (UnauthorizedAccessException) { }
    }

    static string Repo()
    {
        for (var d = new DirectoryInfo(AppContext.BaseDirectory); d is not null; d = d.Parent)
            if (File.Exists(Path.Combine(d.FullName, "portal", "profiles", "xp-profiles.json"))) return d.FullName;
        throw new DirectoryNotFoundException("the repository above " + AppContext.BaseDirectory);
    }

    void Write(string rel, string text)
    {
        var p = Path.Combine(Game, rel);
        Directory.CreateDirectory(Path.GetDirectoryName(p)!);
        File.WriteAllText(p, text);
    }

    static T F<T>(object o, string name) =>
        (T)o.GetType().GetField(name, BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(o)!;

    static void Pump(Func<bool> until, string what, int ms = 60000)
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

    /// <summary>Lets the page run for a while: pictures and lists that load in the background come in.</summary>
    static void Idle(int ms)
    {
        var sw = Stopwatch.StartNew();
        while (sw.ElapsedMilliseconds < ms)
        {
            Dispatcher.UIThread.RunJobs();
            AvaloniaHeadlessPlatform.ForceRenderTimerTick();
            Thread.Sleep(10);
        }
    }

    static void Click(Control c)
    {
        c.BringIntoView();
        Idle(100);
        var top = TopLevel.GetTopLevel(c)!;
        var p = c.TranslatePoint(new Point(c.Bounds.Width / 2, c.Bounds.Height / 2), top)!.Value;
        top.MouseMove(p, RawInputModifiers.None);
        top.MouseDown(p, MouseButton.Left, RawInputModifiers.None);
        top.MouseUp(p, MouseButton.Left, RawInputModifiers.None);
        Idle(100);
    }

    void Shot(TopLevel top, string name)
    {
        Idle(300);
        var frame = top.CaptureRenderedFrame();
        if (frame is null) { _out.WriteLine("no frame for " + name); return; }
        var path = Path.Combine(_shots!, name + ".png");
        frame.Save(path);
        _out.WriteLine("frame: " + path);
    }

    [AvaloniaFact]
    public void Every_page_in_English()
    {
        if (_shots is null) return;
        var w = new MainWindow([]) { WindowState = WindowState.Normal, Width = 1600, Height = 900 };
        w.Show();
        Pump(() => F<object?>(w, "_updater") is not null, "the updater");
        Idle(5000);
        _out.WriteLine("work: " + F<object>(w, "_work"));
        Shot(w, "l01-home");
        foreach (var (page, i) in new[] { "news", "reports", "voice", "support", "settings" }.Select((p, i) => (p, i)))
        {
            Click(F<Dictionary<string, Button>>(w, "_nav")[page]);
            Idle(3000);
            Shot(w, $"l{i + 2:00}-{page}");
        }
        Click(F<Button>(w, "_buildNew"));
        Pump(() => w.OwnedWindows.Count > 0, "the game picker");
        var pick = w.OwnedWindows[0];
        Idle(500);
        _out.WriteLine("games: " + pick.GetVisualDescendants().OfType<RadioButton>().Count());
        Shot(pick, "l08-new-build-games");
        pick.Close();
        w.Close();
    }
}
