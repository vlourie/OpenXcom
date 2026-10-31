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
/// The «Общение» page of a linked launcher (VOICE_CHAT.md §3, version 0.5): the sound settings behind a button,
/// my rooms, everybody's open rooms with "ask to enter", the knocks at my door with let in / decline / ban, and who is
/// online beside it with "add friend" and "invite". The "site" is a listener on localhost that answers from a script and
/// writes down every call; frames go to XP_UI_SHOTS when it is set.
/// </summary>
public sealed class VoiceLobbyTests : IDisposable
{
    static readonly Guid Friend = Guid.Parse("11111111-1111-1111-1111-111111111111");
    static readonly Guid Stranger = Guid.Parse("22222222-2222-2222-2222-222222222222");
    static readonly Guid Knocker = Guid.Parse("33333333-3333-3333-3333-333333333333");

    readonly ITestOutputHelper _out;
    readonly string _root = Path.Combine(Path.GetTempPath(), "xp-ui-tests", Guid.NewGuid().ToString("N"));
    readonly string _shots;
    readonly List<string> _calls = [];
    HttpListener? _site;
    volatile bool _letIn;
    string Game => Path.Combine(_root, "game");
    string DeviceFile => Path.Combine(_root, "settings", "device.json");

    public VoiceLobbyTests(ITestOutputHelper output)
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
        ReportWindow.OpenUrlOverride = _ => { };
        L.Use("ru");
        Directory.CreateDirectory(Path.GetDirectoryName(DeviceFile)!);
        File.WriteAllText(DeviceFile, "{\"token\":\"tok-v\",\"account\":\"Капитан\",\"name\":\"x\",\"linkedAt\":\"2026-10-03T00:00:00Z\"}");
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

    static string Person(Guid id, string name) => $"{{\"id\":\"{id}\",\"name\":\"{name}\"}}";

    const string Me = "{\"id\":\"99999999-9999-9999-9999-999999999999\",\"name\":\"Капитан\"}";

    static string Room(string id, string title, string owner, bool mine, string state = "ok") =>
        $"{{\"publicId\":\"{id}\",\"title\":\"{title}\",\"owner\":{owner},\"mine\":{(mine ? "true" : "false")},\"status\":\"open\",\"state\":\"{state}\",\"inviteDeclined\":false,\"capacity\":10,\"createdAt\":\"2026-10-03T10:00:00Z\"}}";

    string Lobby() =>
        "{\"online\":[" +
            $"{{\"person\":{Person(Friend, "Друг Ваня")},\"friend\":true,\"asked\":false}}," +
            $"{{\"person\":{Person(Stranger, "Прохожий")},\"friend\":false,\"asked\":false}}" +
        "],\"rooms\":[" +
            $"{{\"publicId\":\"deck1\",\"title\":\"Палуба Ани\",\"owner\":{Person(Stranger, "Прохожий")},\"state\":\"request\",\"capacity\":10,\"createdAt\":\"2026-10-03T10:00:00Z\"}}," +
            $"{{\"publicId\":\"hold2\",\"title\":\"Трюм\",\"owner\":{Person(Knocker, "Стучащий")},\"state\":\"requested\",\"capacity\":10,\"createdAt\":\"2026-10-03T10:00:00Z\"}}" +
        "],\"requests\":[" +
            (_letIn ? "" : $"{{\"room\":\"cabin\",\"roomTitle\":\"Моя каюта\",\"person\":{Person(Knocker, "Стучащий")},\"at\":\"2026-10-03T10:05:00Z\"}}") +
        "]}";

    /// <summary>The voice half of the site, written down call by call.</summary>
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
        _ = Task.Run(async () =>
        {
            while (_site.IsListening)
            {
                HttpListenerContext ctx;
                try { ctx = await _site.GetContextAsync(); } catch (Exception) { return; }
                var path = ctx.Request.Url!.AbsolutePath;
                var method = ctx.Request.HttpMethod;
                string sent = new StreamReader(ctx.Request.InputStream).ReadToEnd();
                lock (_calls) _calls.Add($"{method} {path} {sent}".TrimEnd());
                string body = ""; int status = 204;
                if (ctx.Request.Headers["X-Device-Token"] != "tok-v") { status = 401; body = "{\"error\":\"device_unknown\"}"; }
                else if (method == "GET" && path == "/api/v1/voice/rooms")
                    (status, body) = (200, $"{{\"owned\":[{Room("cabin", "Моя каюта", Me, mine: true)}],\"invited\":[]}}");
                else if (method == "GET" && path == "/api/v1/voice/lobby") (status, body) = (200, Lobby());
                else if (method == "POST" && path.EndsWith("/requests")) (status, body) = (200, "{\"result\":\"sent\"}");
                else if (method == "POST" && path == "/api/v1/friends/requests") (status, body) = (200, "{\"result\":\"sent\"}");
                else if (method == "POST" && path == $"/api/v1/voice/rooms/cabin/requests/{Knocker}/accept") _letIn = true;
                else if (path is "/api/v1/voice/presence" || path.StartsWith("/api/v1/voice/rooms/")) { }
                else { status = 404; body = "{\"error\":\"not_found\"}"; }
                var bytes = Encoding.UTF8.GetBytes(body);
                ctx.Response.StatusCode = status;
                if (bytes.Length > 0) ctx.Response.ContentType = "application/json";
                await ctx.Response.OutputStream.WriteAsync(bytes);
                ctx.Response.Close();
            }
        });
        return url;
    }

    bool Called(string call) { lock (_calls) return _calls.Any(c => c.StartsWith(call)); }

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

    static Button Btn(Control within, string key) =>
        within.GetLogicalDescendants().OfType<Button>().First(b => (b.Content as string) == L.T(key) && b.IsEffectivelyVisible);

    [AvaloniaFact]
    public void The_lobby_lists_rooms_knocks_and_people_and_its_buttons_reach_the_site()
    {
        var site = StartSite();
        new Settings { GameDir = Game, RepoUrl = "http://127.0.0.1:9/", PortalUrl = site, Language = "ru" }.Save();
        var w = new MainWindow([]) { WindowState = WindowState.Normal, Width = 1280, Height = 860 };
        w.Show();
        Pump(() => F<object?>(w, "_updater") is not null && F<object>(w, "_work").ToString() == "None", "the window to go idle");
        // a linked launcher says "here" at once, before anybody opens the page
        Pump(() => Called("POST /api/v1/voice/presence"), "the first 'here'");

        var nav = F<Dictionary<string, Button>>(w, "_nav")["voice"];
        Assert.Contains(L.T("nav.voice"), nav.GetLogicalDescendants().OfType<TextBlock>().Select(t => t.Text));
        Assert.Equal("Общение", L.T("nav.voice"));
        Click(nav);
        var page = F<VoicePage>(w, "_voicePage");
        var side = F<Border>(page, "_side");
        Pump(() => side.IsVisible && F<StackPanel>(page, "_catalog").Children.Count == 2, "the lobby");

        // the sound settings wait behind their button
        var sound = F<Border>(page, "_soundPanel");
        Assert.False(sound.IsVisible);
        Assert.Equal(L.T("voice.online", 2), F<TextBlock>(page, "_onlineTitle").Text);
        Assert.True(F<Border>(page, "_requestsBox").IsVisible);
        Assert.Equal(L.T("voice.openAdmin"), Btn(F<StackPanel>(page, "_owned"), "voice.openAdmin").Content);
        Shot(w, "voice-1-lobby");

        Click(F<Button>(page, "_settingsButton"));
        Assert.True(sound.IsVisible);
        Assert.Equal(L.T("voice.settingsHide"), F<Button>(page, "_settingsButton").Content);
        Shot(w, "voice-2-settings");
        Click(F<Button>(page, "_settingsButton"));
        Assert.False(sound.IsVisible);

        // a knock at an open room of a stranger
        Click(Btn(F<StackPanel>(page, "_catalog"), "voice.ask"));
        Pump(() => Called("POST /api/v1/voice/rooms/deck1/requests"), "the knock");
        // and one taken back
        Click(Btn(F<StackPanel>(page, "_catalog"), "voice.askCancel"));
        Pump(() => Called("DELETE /api/v1/voice/rooms/hold2/requests"), "the knock taken back");

        // somebody online: a friend request by id, and the friend called into my only open room
        var online = F<StackPanel>(page, "_online");
        Click(Btn(online, "voice.befriend"));
        Pump(() => Called($"POST /api/v1/friends/requests {{\"who\":\"{Stranger}\"}}"), "the friend request");
        Click(Btn(online, "voice.invite"));
        Pump(() => Called($"POST /api/v1/voice/rooms/cabin/invites {{\"user\":\"{Friend}\"}}"), "the invite");

        // the owner lets the knocker in: the knock leaves the list
        Click(Btn(F<StackPanel>(page, "_requests"), "voice.letIn"));
        Pump(() => Called($"POST /api/v1/voice/rooms/cabin/requests/{Knocker}/accept"), "let in");
        Pump(() => !F<Border>(page, "_requestsBox").IsVisible, "the knock to leave");
        Shot(w, "voice-3-after");

        // closing the launcher takes it off the online list
        w.Close();
        Pump(() => Called("DELETE /api/v1/voice/presence"), "the 'gone'");
        Pump(() => !w.IsVisible, "the window to close", 5000);
        lock (_calls) _out.WriteLine(string.Join("\n", _calls));
    }
}
