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
/// The "Messages" tab of the chat page (ticket XP-000476): the counter on the rail button, the conversations with the unread
/// ones marked, a dialogue as a feed in plain text, a reply, a new message to a friend, a blocked person; and what an
/// unlinked launcher sees. The "site" is a listener on localhost that answers from a script and writes down every call.
/// </summary>
public sealed class MessagesPageTests : IDisposable
{
    static readonly Guid Ann = Guid.Parse("11111111-1111-1111-1111-111111111111");
    static readonly Guid Bob = Guid.Parse("22222222-2222-2222-2222-222222222222");

    readonly ITestOutputHelper _out;
    readonly string _root = Path.Combine(Path.GetTempPath(), "xp-ui-tests", Guid.NewGuid().ToString("N"));
    readonly string _shots;
    readonly List<string> _calls = [];
    HttpListener? _site;
    volatile int _unread = 2;
    string Game => Path.Combine(_root, "game");
    string DeviceFile => Path.Combine(_root, "settings", "device.json");

    const string Evil = "Привет <b>там</b>\nhttps://evil.test/x";

    public MessagesPageTests(ITestOutputHelper output)
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
    }

    void Link() =>
        File.WriteAllText(DeviceFile, "{\"token\":\"tok-v\",\"account\":\"Капитан\",\"name\":\"x\",\"linkedAt\":\"2026-10-03T00:00:00Z\"}");

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

    static string Json(string s) => System.Text.Json.JsonSerializer.Serialize(s);

    string Inbox() =>
        $"{{\"unread\":{_unread},\"dialogues\":[" +
        $"{{\"person\":{Person(Ann, "Анна")},\"preview\":{Json("Привет <b>там</b> https://evil.test/x")},\"lastMine\":false,\"at\":\"2026-11-02T10:00:00Z\",\"unread\":{_unread}}}," +
        $"{{\"person\":{Person(Bob, "Борис")},\"preview\":\"Ладно\",\"lastMine\":true,\"at\":\"2026-11-01T10:00:00Z\",\"unread\":0}}]}}";

    static string ThreadJson(Guid id, string name, bool blocked) =>
        $"{{\"person\":{Person(id, name)},\"total\":2,\"page\":1,\"perPage\":50,\"iBlocked\":{(blocked ? "true" : "false")},\"friend\":true,\"messages\":[" +
        $"{{\"id\":\"aaaaaaaa-0000-0000-0000-000000000001\",\"mine\":true,\"body\":\"Здравствуй\",\"at\":\"2026-11-02T09:00:00Z\",\"read\":true}}," +
        $"{{\"id\":\"aaaaaaaa-0000-0000-0000-000000000002\",\"mine\":false,\"body\":{Json(Evil)},\"at\":\"2026-11-02T10:00:00Z\",\"read\":false}}]}}";

    const string Sent = "{\"id\":\"bbbbbbbb-0000-0000-0000-000000000001\",\"to\":{\"id\":\"11111111-1111-1111-1111-111111111111\",\"name\":\"Анна\"},\"at\":\"2026-11-02T11:00:00Z\"}";

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
                else if (method == "GET" && path == "/api/v1/messages/unread") (status, body) = (200, $"{{\"unread\":{_unread}}}");
                else if (method == "GET" && path == "/api/v1/messages") (status, body) = (200, Inbox());
                else if (method == "GET" && path == $"/api/v1/messages/{Ann}") (status, body) = (200, ThreadJson(Ann, "Анна", false));
                else if (method == "GET" && path == $"/api/v1/messages/{Bob}") (status, body) = (200, ThreadJson(Bob, "Борис", true));
                else if (method == "POST" && path == $"/api/v1/messages/{Ann}/read") _unread = 0;
                else if (method == "POST" && (path == $"/api/v1/messages/{Ann}" || path == "/api/v1/messages")) (status, body) = (201, Sent);
                else if (method == "GET" && path == "/api/v1/friends")
                    (status, body) = (200, $"{{\"friends\":[{{\"id\":\"{Ann}\",\"name\":\"Анна\",\"since\":\"2026-10-01T00:00:00Z\"}}],\"friendsTotal\":1,\"incoming\":[],\"outgoing\":[],\"blocked\":[]}}");
                else if (method == "DELETE" && path == $"/api/v1/blocks/{Bob}") { }
                else if (method == "GET" && path == "/api/v1/voice/rooms") (status, body) = (200, "{\"owned\":[],\"invited\":[]}");
                else if (method == "GET" && path == "/api/v1/voice/lobby") (status, body) = (200, "{\"online\":[],\"rooms\":[],\"requests\":[]}");
                else if (path is "/api/v1/voice/presence") { }
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

    bool Called(string call) { lock (_calls) return _calls.Any(c => System.Text.RegularExpressions.Regex.Unescape(c).StartsWith(call)); }

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

    static IEnumerable<string?> Texts(Control c) => c.GetLogicalDescendants().OfType<TextBlock>().Select(t => t.Text);

    static MainWindow Open(string site, Dirs game)
    {
        new Settings { GameDir = game.Dir, RepoUrl = "http://127.0.0.1:9/", PortalUrl = site, Language = "ru" }.Save();
        var w = new MainWindow([]) { WindowState = WindowState.Normal, Width = 1280, Height = 900 };
        w.Show();
        Pump(() => F<object?>(w, "_updater") is not null && F<object>(w, "_work").ToString() == "None", "the window to go idle");
        return w;
    }

    record Dirs(string Dir);

    [AvaloniaFact]
    public void Unread_counter_conversations_feed_reply_new_message_and_a_blocked_person()
    {
        Link();
        var site = StartSite();
        var w = Open(site, new Dirs(Game));
        var page = F<VoicePage>(w, "_voicePage");

        // the first look of the launcher: the counter sits on the "Chat" button and a notice waits on the home page
        var badge = F<Border>(w, "_chatBadge");
        Pump(() => badge.IsVisible, "the counter on the rail");
        Assert.Equal("2", F<TextBlock>(w, "_chatCount").Text);
        Assert.Contains(L.T("notice.messages", 2), Texts(F<Border>(w, "_notice")));

        Click(F<Dictionary<string, Button>>(w, "_nav")["voice"]);
        Pump(() => (F<Button>(page, "_tabMessages").Content as string) == L.T("msgs.tabMessagesN", 2), "the tab to show the count");
        Click(F<Button>(page, "_tabMessages"));
        var messages = page.Messages;
        Assert.True(messages.IsVisible);
        Assert.False(F<Grid>(page, "_columns").IsVisible);
        var list = F<StackPanel>(messages, "_list");
        Pump(() => list.Children.Count == 2, "the conversations");
        Assert.Contains("Анна", Texts(list));
        Assert.Contains("Борис", Texts(list));
        Shot(w, "messages-1-inbox");

        // open the unread one: plain text as typed, read on the site, the counters go
        Click((Control)list.Children[0]);
        var feed = F<StackPanel>(messages, "_feed");
        Pump(() => feed.Children.Count == 2, "the feed");
        var bodies = feed.GetLogicalDescendants().OfType<SelectableTextBlock>().Select(t => t.Text).ToList();
        Assert.Equal(["Здравствуй", Evil], bodies);
        Pump(() => Called($"POST /api/v1/messages/{Ann}/read"), "the dialogue to be read");
        Pump(() => !badge.IsVisible, "the counter to go");
        Assert.Equal(L.T("msgs.tabMessages"), F<Button>(page, "_tabMessages").Content);
        Shot(w, "messages-2-thread");

        // a reply
        F<TextBox>(messages, "_reply").Text = "ответ";
        Click(F<Button>(messages, "_send"));
        Pump(() => Called($"POST /api/v1/messages/{Ann} {{\"body\":\"ответ\"}}"), "the reply");

        // a new message to a friend picked from the list
        Click(Btn(messages, "msgs.new"));
        var chips = F<WrapPanel>(messages, "_friends");
        Pump(() => chips.Children.Count == 1, "the friends");
        Click((Control)chips.Children[0]);
        Assert.Equal("Анна", F<TextBox>(messages, "_to").Text);
        F<TextBox>(messages, "_text").Text = "новое";
        Click(F<StackPanel>(messages, "_composeBox").GetLogicalDescendants().OfType<Button>().First(b => (b.Content as string) == L.T("msgs.send")));
        Pump(() => Called("POST /api/v1/messages {\"who\":\"Анна\",\"body\":\"новое\"}"), "the new message");
        Shot(w, "messages-3-new");

        // somebody I blocked: no reply, the button lifts the block
        Click((Control)F<StackPanel>(messages, "_list").Children[1]);
        var block = F<Button>(messages, "_block");
        Pump(() => (block.Content as string) == L.T("msgs.unblock"), "the blocked dialogue");
        Assert.False(F<TextBox>(messages, "_reply").IsEnabled);
        Click(block);
        Pump(() => Called($"DELETE /api/v1/blocks/{Bob}"), "the block to be lifted");
        Shot(w, "messages-4-blocked");

        w.Close();
        lock (_calls) _out.WriteLine(string.Join("\n", _calls));
    }

    [AvaloniaFact]
    public void An_unlinked_launcher_gets_the_hint_and_asks_for_no_messages()
    {
        var site = StartSite();
        var w = Open(site, new Dirs(Game));
        var page = F<VoicePage>(w, "_voicePage");

        Click(F<Dictionary<string, Button>>(w, "_nav")["voice"]);
        Click(F<Button>(page, "_tabMessages"));
        Assert.True(F<StackPanel>(page, "_unlinked").IsVisible);
        Assert.False(page.Messages.IsVisible);
        Assert.False(F<Border>(w, "_chatBadge").IsVisible);
        Settle();
        Assert.False(Called("GET /api/v1/messages"));
        Shot(w, "messages-5-unlinked");

        // back to the rooms
        Click(F<Button>(page, "_tabRooms"));
        Assert.True(F<Grid>(page, "_columns").IsVisible);
        w.Close();
    }
}
