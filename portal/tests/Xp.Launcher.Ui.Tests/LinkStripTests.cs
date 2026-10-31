using System.Diagnostics;
using System.Net;
using System.Net.Sockets;
using System.Reflection;
using System.Text;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Headless;
using Avalonia.Headless.XUnit;
using Avalonia.Input;
using Avalonia.LogicalTree;
using Avalonia.Threading;
using Xp.Launcher;
using Xunit.Abstractions;

namespace Xp.Launcher.Ui.Tests;

/// <summary>
/// The link strip over the picture on the home page: shown until the launcher is linked, its button opens the site with the
/// code and waits for the yes there, an error stands still in it, and a linked launcher has no strip. The "site" is a listener
/// on localhost; the browser never opens (ReportWindow.OpenUrlOverride). Frames go to XP_UI_SHOTS when it is set.
/// </summary>
public sealed class LinkStripTests : IDisposable
{
    readonly ITestOutputHelper _out;
    readonly string _root = Path.Combine(Path.GetTempPath(), "xp-ui-tests", Guid.NewGuid().ToString("N"));
    readonly string _shots;
    readonly List<string> _opened = [];
    HttpListener? _site;
    volatile bool _confirmed;
    string Game => Path.Combine(_root, "game");
    string DeviceFile => Path.Combine(_root, "settings", "device.json");

    public LinkStripTests(ITestOutputHelper output)
    {
        _out = output;
        _shots = Environment.GetEnvironmentVariable("XP_UI_SHOTS") is { Length: > 0 } s ? s : Path.Combine(_root, "shots");
        Directory.CreateDirectory(_shots);
        Write("standard/xcom1/metadata.yml", "id: xcom1\nisMaster: true\n");
        Write("user/mods/Piratez/metadata.yml", "id: piratez\nname: X-Piratez\nisMaster: true\nmaster: xcom1\n");
        Write("user/mods/hd/metadata.yml", "id: hd\nmaster: \"*\"\n");
        Write("common/readme.txt", "");
        Write("xp-profiles.json", "{ \"schema\": 1, \"profiles\": [ { \"master\": \"piratez\", \"version\": 1, \"mods\": [ { \"id\": \"*\" }, { \"id\": \"hd\" } ], \"options\": [] } ] }");
        Write("user/options.cfg", "mods:\n  - active: true\n    id: piratez\n  - active: true\n    id: hd\noptions:\n  language: ru\n  oxceRecommendedOptionsWereSet: true\n");
        File.Copy(Path.Combine(Environment.SystemDirectory, "PING.EXE"), Path.Combine(Game, "openxcom_hd.exe"));
        Settings.DirOverride = Path.Combine(_root, "settings");
        ReportWindow.OpenUrlOverride = url => { lock (_opened) _opened.Add(url); };
        L.Use("ru");
    }

    public void Dispose()
    {
        ReportWindow.OpenUrlOverride = null;
        Settings.DirOverride = null;
        try { _site?.Stop(); } catch (ObjectDisposedException) { }
        try { Directory.Delete(_root, recursive: true); } catch (IOException) { } catch (UnauthorizedAccessException) { }
    }

    void Write(string rel, string text)
    {
        var p = Path.Combine(Game, rel);
        Directory.CreateDirectory(Path.GetDirectoryName(p)!);
        File.WriteAllText(p, text);
    }

    /// <summary>The device half of the site: a code on the first call, "pending" until the test says yes, then the token.</summary>
    string StartSite()
    {
        var probe = new TcpListener(IPAddress.Loopback, 0);
        probe.Start();
        int port = ((IPEndPoint)probe.LocalEndpoint).Port;
        probe.Stop();
        var url = $"http://localhost:{port}/";
        _site = new HttpListener();
        _site.Prefixes.Add(url);
        _site.Start();
        var device = Guid.NewGuid();
        _ = Task.Run(async () =>
        {
            while (_site.IsListening)
            {
                HttpListenerContext ctx;
                try { ctx = await _site.GetContextAsync(); } catch (Exception) { return; }
                var path = ctx.Request.Url!.AbsolutePath;
                string body; int status = 200;
                if (ctx.Request.HttpMethod == "POST" && path == "/api/v1/devices/link")
                    body = $"{{\"code\":\"KX7-4PQ\",\"deviceId\":\"{device}\",\"expiresIn\":600}}";
                else if (path == $"/api/v1/devices/{device}")
                    body = _confirmed ? "{\"status\":\"linked\",\"token\":\"tok-1\",\"account\":\"Тестер\"}" : "{\"status\":\"pending\"}";
                else { status = 404; body = "{\"error\":\"not_found\"}"; }
                var bytes = Encoding.UTF8.GetBytes(body);
                ctx.Response.StatusCode = status;
                ctx.Response.ContentType = "application/json";
                await ctx.Response.OutputStream.WriteAsync(bytes);
                ctx.Response.Close();
            }
        });
        return url;
    }

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

    static void Click(Control c)
    {
        Settle();
        var top = TopLevel.GetTopLevel(c)!;
        var p = c.TranslatePoint(new Point(c.Bounds.Width / 2, c.Bounds.Height / 2), top)!.Value;
        top.MouseMove(p, RawInputModifiers.None);
        top.MouseDown(p, MouseButton.Left, RawInputModifiers.None);
        top.MouseUp(p, MouseButton.Left, RawInputModifiers.None);
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

    MainWindow Open(string portal)
    {
        new Settings { GameDir = Game, RepoUrl = "http://127.0.0.1:9/", PortalUrl = portal, Language = "ru" }.Save();
        var w = new MainWindow([]) { WindowState = WindowState.Normal, Width = 1280, Height = 820 };
        w.Show();
        Pump(() => F<object?>(w, "_updater") is not null && F<object>(w, "_work").ToString() == "None", "the window to go idle");
        Settle();
        return w;
    }

    static Button StripButton(MainWindow w, string key) =>
        F<Border>(w, "_linkStrip").GetLogicalDescendants().OfType<Button>().Single(b => (b.Content as string) == L.T(key));

    [AvaloniaFact]
    public void The_strip_links_through_the_site_and_goes_away()
    {
        var w = Open(StartSite());
        var strip = F<Border>(w, "_linkStrip");
        var timer = F<DispatcherTimer>(w, "_linkTimer");
        var run = F<TextBlock>(w, "_linkRun");
        var say = F<TextBlock>(w, "_linkSay");
        Assert.True(strip.IsEffectivelyVisible);
        Assert.True(timer.IsEnabled);
        Assert.Equal(L.T("link.strip"), run.Text);
        // the line runs: a few ticks later it stands elsewhere
        var x0 = ((Avalonia.Media.TranslateTransform)run.RenderTransform!).X;
        // RunJobs does not fire timers in the headless platform: the real loop does, for half a second
        using (var loop = new CancellationTokenSource(500)) Dispatcher.UIThread.MainLoop(loop.Token);
        Assert.True(((Avalonia.Media.TranslateTransform)run.RenderTransform!).X < x0 - 5, "the line stood still");
        Shot(w, "link-1-strip");

        Click(StripButton(w, "link.go"));
        Pump(() => say.IsVisible, "the waiting words");
        lock (_opened) Assert.Contains(_opened, u => u.EndsWith("/me/devices?code=KX7-4PQ"));
        Assert.Contains("KX7-4PQ", say.Text);
        Assert.False(timer.IsEnabled);   // words to be read whole stand still
        Assert.True(StripButton(w, "account.open").IsVisible);
        Assert.False(StripButton(w, "link.go").IsVisible);
        Shot(w, "link-2-waiting");

        // a second press of "open the site" opens it again with the same code
        Click(StripButton(w, "account.open"));
        lock (_opened) Assert.Equal(2, _opened.Count(u => u.EndsWith("code=KX7-4PQ")));

        _confirmed = true;
        Pump(() => !strip.IsVisible, "the strip to go after the yes");
        Assert.True(File.Exists(DeviceFile));
        Assert.Contains("tok-1", File.ReadAllText(DeviceFile));
        Assert.False(timer.IsEnabled);
        Shot(w, "link-3-linked");
        Click(F<Dictionary<string, Button>>(w, "_nav")["settings"]);
        Shot(w, "link-4-settings-linked");
        w.Close();
    }

    [AvaloniaFact]
    public void An_unreachable_site_is_said_in_the_strip_and_the_button_stays()
    {
        var w = Open("http://127.0.0.1:9/");
        var say = F<TextBlock>(w, "_linkSay");
        var timer = F<DispatcherTimer>(w, "_linkTimer");
        Click(StripButton(w, "link.go"));
        Pump(() => say.IsVisible, "the error in the strip");
        Assert.Equal(L.T("account.offline"), say.Text);
        Assert.False(timer.IsEnabled);
        Assert.True(StripButton(w, "link.go").IsVisible);   // the player can try again
        lock (_opened) Assert.Empty(_opened);
        Shot(w, "link-5-offline");
        w.Close();
    }

    [AvaloniaFact]
    public void A_linked_launcher_has_no_strip()
    {
        Directory.CreateDirectory(Path.GetDirectoryName(DeviceFile)!);
        File.WriteAllText(DeviceFile, "{\"token\":\"tok-0\",\"account\":\"Тестер\",\"name\":\"x\",\"linkedAt\":\"2026-10-03T00:00:00Z\"}");
        var w = Open("http://127.0.0.1:9/");   // the site is away: the stored link is not forgotten for that
        Assert.False(F<Border>(w, "_linkStrip").IsVisible);
        Assert.False(F<DispatcherTimer>(w, "_linkTimer").IsEnabled);
        w.Close();
    }
}
