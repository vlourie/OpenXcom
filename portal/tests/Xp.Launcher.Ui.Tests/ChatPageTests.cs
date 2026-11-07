using System.Diagnostics;
using System.Reflection;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Documents;
using Avalonia.Headless;
using Avalonia.Headless.XUnit;
using Avalonia.Input;
using Avalonia.LogicalTree;
using Avalonia.Threading;
using Xp.Launcher;
using Xp.Launcher.Core;
using Xunit.Abstractions;

namespace Xp.Launcher.Ui.Tests;

/// <summary>
/// The «Общение» page in three columns (docs/portal/VOICE_IRC.md): the channels, the rooms and the private dialogues on the
/// left; the topic, the feed as plain lines and one input in the middle; who is here on the right. The private messages of
/// ticket XP-000476 live in the same column now (the counter on the rail, a dialogue as a feed, a reply, "/msg", a blocked
/// person), and a running game gets a plate for a private message or a mention. The "site" is ChatSite, a listener on localhost.
/// </summary>
public sealed class ChatPageTests : IDisposable
{
    readonly ITestOutputHelper _out;
    readonly string _root = Path.Combine(Path.GetTempPath(), "xp-ui-tests", Guid.NewGuid().ToString("N"));
    readonly string _shots;
    readonly List<ChatSite> _sites = [];
    string Game => Path.Combine(_root, "game");
    string DeviceFile => Path.Combine(_root, "settings", "device.json");

    public ChatPageTests(ITestOutputHelper output)
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
        foreach (var s in _sites) s.Dispose();
        try { Directory.Delete(_root, recursive: true); } catch (IOException) { } catch (UnauthorizedAccessException) { }
    }

    void Write(string rel, string text)
    {
        var p = Path.Combine(Game, rel);
        Directory.CreateDirectory(Path.GetDirectoryName(p)!);
        File.WriteAllText(p, text);
    }

    ChatSite StartSite()
    {
        var s = new ChatSite();
        _sites.Add(s);
        return s;
    }

    static T F<T>(object o, string name) =>
        (T)o.GetType().GetField(name, BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(o)!;

    /// <summary>A private async method of the page, run on the UI thread and waited for.</summary>
    static void Run(object page, string method)
    {
        var task = (Task)page.GetType().GetMethod(method, BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(page, null)!;
        Pump(() => task.IsCompleted, method);
        task.GetAwaiter().GetResult();
    }

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

    static IEnumerable<string?> Texts(Control c) => c.GetLogicalDescendants().OfType<TextBlock>().Select(t => t.Text);

    /// <summary>The feed as the player reads it: one string per line, "12:34 &lt;nick&gt; text".</summary>
    static List<string> Lines(StackPanel feed) =>
        feed.Children.OfType<Border>().Select(b => string.Concat(((SelectableTextBlock)b.Child!).Inlines!.OfType<Run>().Select(r => r.Text))).ToList();

    /// <summary>Plain text only: nothing in a line of the feed is a link, a button or any other inline but a run.</summary>
    static bool OnlyRuns(StackPanel feed) =>
        feed.Children.OfType<Border>().All(b => ((SelectableTextBlock)b.Child!).Inlines!.All(i => i is Run));

    MainWindow Open(ChatSite site, double width = 1280, double height = 900)
    {
        new Settings { GameDir = Game, RepoUrl = "http://127.0.0.1:9/", PortalUrl = site.Url, Language = "ru" }.Save();
        var w = new MainWindow([]) { WindowState = WindowState.Normal, Width = width, Height = height };
        w.Show();
        Pump(() => F<object?>(w, "_updater") is not null && F<object>(w, "_work").ToString() == "None", "the window to go idle");
        return w;
    }

    /// <summary>The «Общение» page opened, the first channel on screen with its three lines.</summary>
    VoicePage OpenChat(MainWindow w)
    {
        var page = F<VoicePage>(w, "_voicePage");
        Click(F<Dictionary<string, Button>>(w, "_nav")["voice"]);
        Pump(() => Lines(F<StackPanel>(page, "_feed")).Count == 3, "the first channel's feed");
        return page;
    }

    string Plate => ChatNotice.PathIn(new GamePaths(Game));

    [AvaloniaFact]
    public void A_channel_is_three_columns_of_plain_lines_and_every_slash_line_is_a_command()
    {
        Link();
        var site = StartSite();
        var w = Open(site);
        var page = OpenChat(w);
        var feed = F<StackPanel>(page, "_feed");
        var input = F<TextBox>(page, "_input");
        string Posts() => "POST /api/v1/voice/rooms/ch-general/messages";

        // the left column: the channels with their counters, my rooms, the dialogues; the first channel opens without joining
        var channels = F<StackPanel>(page, "_channelList");
        Assert.Equal(3, channels.Children.Count);
        Assert.Contains("#общий", Texts(channels));
        Assert.Contains("@1", Texts(channels));
        Assert.Contains("2", Texts(channels));
        Assert.Contains("Моя каюта", Texts(F<StackPanel>(page, "_roomList")));
        Assert.Contains("Анна", Texts(F<StackPanel>(page, "_dialogueList")));
        Assert.False(site.Called("POST /api/v1/voice/rooms/ch-general/join"));

        // the middle: the topic and the feed, a service line grey with "--", an action with "*", the text as typed
        Assert.Equal("#общий", F<TextBlock>(page, "_topicTitle").Text);
        Assert.StartsWith("Общий разговор", F<TextBlock>(page, "_topicText").Text);
        var lines = Lines(feed);
        Assert.EndsWith("<Анна> " + ChatSite.Evil, lines[0]);
        Assert.EndsWith("-- Борис вошёл в канал", lines[1]);
        Assert.EndsWith("* Борис машет рукой", lines[2]);
        Assert.Matches(@"^\d\d:\d\d ", lines[0]);
        Assert.True(OnlyRuns(feed));

        // the right: who is here, @ for the owner or staff, + for voice, - for the one who may not talk
        var here = F<StackPanel>(page, "_attendees");
        Assert.Equal(3, here.Children.Count);
        Assert.Contains("@", Texts(here));
        Assert.Contains("+", Texts(here));
        Assert.Contains("−", Texts(here));
        Assert.Contains("Катя", Texts(here));
        Assert.Contains(L.T("chat.here", 3).ToUpperInvariant(), Texts(F<Border>(page, "_rightPanel")));
        Shot(w, "chat-1-channel");

        // a line goes to the site and stays in the feed as the site gave it back
        input.Text = ChatSite.Evil;
        Click(F<Button>(page, "_send"));
        Pump(() => Lines(feed).Count == 4, "my line");
        Assert.EndsWith("<Капитан> " + ChatSite.Evil, Lines(feed)[3]);
        Assert.Equal(1, site.Count(Posts()));
        Assert.True(string.IsNullOrEmpty(input.Text));
        Assert.True(OnlyRuns(feed));

        // /help and /who are answered here: nothing leaves for the site and the line is not a message
        input.Text = "/help";
        Click(F<Button>(page, "_send"));
        Pump(() => Lines(feed).Any(l => l.Contains("/join #канал")), "the help");
        input.Text = "/who";
        Click(F<Button>(page, "_send"));
        Pump(() => Lines(feed).Any(l => l.Contains("Здесь 3: @Анна, +Борис, -Катя")), "the list of people");
        Assert.Equal(1, site.Count(Posts()));
        Assert.DoesNotContain(Lines(feed), l => l.Contains("<Капитан> /"));

        // a slash line the site does not know is not a message either: it gets there, and only a hint comes back
        input.Text = "/dance";
        Click(F<Button>(page, "_send"));
        Pump(() => site.Count(Posts()) == 2, "the unknown command to reach the site");
        Pump(() => Lines(feed).Any(l => l.Contains("Нет такой команды")), "the hint");
        Assert.DoesNotContain(Lines(feed), l => l.Contains("<Капитан> /dance"));
        Assert.True(string.IsNullOrEmpty(input.Text));
        Shot(w, "chat-2-commands");

        // /join moves to the other channel, joining it, and sends no line
        input.Text = "/join #english";
        Click(F<Button>(page, "_send"));
        Pump(() => site.Called("POST /api/v1/voice/rooms/ch-english/join"), "the join");
        Pump(() => F<TextBlock>(page, "_topicTitle").Text == "#english", "the other channel");
        Assert.Equal(2, site.Count(Posts()));
        Assert.False(site.Called("POST /api/v1/voice/rooms/ch-english/messages"));

        // /part leaves it, on the site, and says so
        input.Text = "/part";
        Click(F<Button>(page, "_send"));
        Pump(() => site.Called("POST /api/v1/voice/rooms/ch-english/part"), "the part");
        Pump(() => Lines(feed).Any(l => l.Contains("Вы вышли из #english")), "the word about it");
        w.Close();
        _out.WriteLine(string.Join("\n", site.Calls));
    }

    [AvaloniaFact]
    public void The_feed_is_asked_after_its_cursor_and_only_while_the_section_is_open_and_the_window_is_up()
    {
        Link();
        var site = StartSite();
        var w = Open(site);
        var page = OpenChat(w);
        var feed = F<StackPanel>(page, "_feed");
        var feedCalls = () => site.Calls.Count(c => c.StartsWith("GET /api/v1/voice/rooms/ch-general/messages?after="));

        // nothing new: the cursor goes out and nothing comes back
        Run(page, "PollAsync");
        Assert.True(site.Called("GET /api/v1/voice/rooms/ch-general/messages?after=12"));
        Assert.Equal(3, Lines(feed).Count);

        // a new line after the cursor is appended, not the whole feed read again
        site.More = true;
        Run(page, "PollAsync");
        Pump(() => Lines(feed).Count == 4, "the new line");
        Assert.EndsWith("<Борис> новая строка", Lines(feed)[3]);
        Run(page, "PollAsync");
        Assert.True(site.Called("GET /api/v1/voice/rooms/ch-general/messages?after=13"));
        Assert.Equal(4, Lines(feed).Count);

        // a minimized window asks for nothing
        int before = feedCalls();
        w.WindowState = WindowState.Minimized;
        Settle();
        Run(page, "PollAsync");
        Assert.Equal(before, feedCalls());
        w.WindowState = WindowState.Normal;
        Settle();

        // another section of the launcher: the page is not on screen and asks for nothing
        Click(F<Dictionary<string, Button>>(w, "_nav")["home"]);
        Run(page, "PollAsync");
        Assert.Equal(before, feedCalls());

        // back: asked again
        Click(F<Dictionary<string, Button>>(w, "_nav")["voice"]);
        Run(page, "PollAsync");
        Assert.True(feedCalls() > before);
        w.Close();
    }

    [AvaloniaFact]
    public void Private_dialogues_counter_feed_reply_msg_a_stray_command_and_a_blocked_person()
    {
        Link();
        var site = StartSite();
        var w = Open(site);
        var page = F<VoicePage>(w, "_voicePage");

        // the first look of the launcher: the counter sits on the "Chat" button and a notice waits on the home page
        var badge = F<Border>(w, "_chatBadge");
        Pump(() => badge.IsVisible, "the counter on the rail");
        Assert.Equal("2", F<TextBlock>(w, "_chatCount").Text);
        Assert.Contains(L.T("notice.messages", 2), Texts(F<Border>(w, "_notice")));

        Click(F<Dictionary<string, Button>>(w, "_nav")["voice"]);
        var dialogues = F<StackPanel>(page, "_dialogueList");
        Pump(() => dialogues.Children.Count == 2, "the conversations");
        Assert.Contains("Анна", Texts(dialogues));
        Assert.Contains("Борис", Texts(dialogues));
        Assert.Contains("2", Texts(dialogues));            // the unread pill
        Shot(w, "chat-3-inbox");

        // open the unread one: plain text as typed, read on the site, the counters go
        Click((Control)dialogues.Children[0]);
        var feed = F<StackPanel>(page, "_feed");
        Pump(() => Lines(feed).Count == 2 && Lines(feed)[1].Contains("<Анна>"), "the dialogue");
        var lines = Lines(feed);
        Assert.EndsWith("<Капитан> Здравствуй  · " + L.T("msgs.readMark"), lines[0]);
        Assert.EndsWith("<Анна> " + ChatSite.Evil, lines[1]);
        Assert.True(OnlyRuns(feed));
        Assert.Equal("Анна", F<TextBlock>(page, "_topicTitle").Text);
        Pump(() => site.Called($"POST /api/v1/messages/{ChatSite.Ann}/read"), "the dialogue to be read");
        Pump(() => !badge.IsVisible, "the counter to go");
        Shot(w, "chat-4-dialogue");

        // a reply is the text of the input
        var input = F<TextBox>(page, "_input");
        input.Text = "ответ";
        Click(F<Button>(page, "_send"));
        Pump(() => site.Called($"POST /api/v1/messages/{ChatSite.Ann} {{\"body\":\"ответ\"}}"), "the reply");

        // /msg writes to anybody by the name; a channel command is not a message and goes nowhere
        input.Text = "/msg Анна новое";
        Click(F<Button>(page, "_send"));
        Pump(() => site.Called("POST /api/v1/messages {\"who\":\"Анна\",\"body\":\"новое\"}"), "the /msg");
        int posts = site.Calls.Count(c => c.StartsWith("POST"));
        input.Text = "/dance";
        Click(F<Button>(page, "_send"));
        Pump(() => Lines(feed).Any(l => l.Contains("Команда /dance")), "the hint");
        input.Text = "/kick Борис";
        Click(F<Button>(page, "_send"));
        Pump(() => Lines(feed).Any(l => l.Contains("Команда /kick")), "the second hint");
        Assert.Equal(posts, site.Calls.Count(c => c.StartsWith("POST")));
        Assert.DoesNotContain(site.Calls, c => c.Contains("dance") || c.Contains("kick"));

        // somebody I blocked: no reply, the button lifts the block
        site.Blocked = true;
        Click((Control)dialogues.Children[1]);
        var block = F<Button>(page, "_block");
        Pump(() => (block.Content as string) == L.T("msgs.unblock"), "the blocked dialogue");
        Assert.False(input.IsEnabled);
        Assert.False(F<Button>(page, "_send").IsEnabled);
        Click(block);
        Pump(() => site.Called($"DELETE /api/v1/blocks/{ChatSite.Bob}"), "the block to be lifted");
        Pump(() => input.IsEnabled, "the input to come back");
        w.Close();
        _out.WriteLine(string.Join("\n", site.Calls));
    }

    [AvaloniaFact]
    public void An_unlinked_launcher_gets_the_hint_and_asks_for_nothing()
    {
        var site = StartSite();
        var w = Open(site);
        var page = F<VoicePage>(w, "_voicePage");

        Click(F<Dictionary<string, Button>>(w, "_nav")["voice"]);
        Assert.True(F<StackPanel>(page, "_unlinked").IsVisible);
        Assert.False(F<Control>(page, "_body").IsVisible);
        Assert.False(F<Border>(w, "_chatBadge").IsVisible);
        Settle();
        Assert.False(site.Called("GET /api/v1/messages"));
        Assert.False(site.Called("GET /api/v1/voice/channels"));
        Run(page, "PollAsync");
        Run(page, "BackgroundAsync");
        Assert.False(site.Called("GET /api/v1/voice/channels"));
        Shot(w, "chat-5-unlinked");
        w.Close();
    }

    [AvaloniaFact]
    public void A_running_game_gets_a_plate_for_a_mention_a_private_message_or_every_line_with_the_option_and_never_for_old_lines()
    {
        Link();
        var site = StartSite();
        var w = Open(site);
        var page = OpenChat(w);
        var feed = F<StackPanel>(page, "_feed");
        var plate = Plate;
        string[] Said() => File.Exists(plate) ? File.ReadAllLines(plate) : [];

        // what the first look found is history: even with a game running there is no plate for it, nor for the same data again
        page.GameRunning = () => true;
        Run(page, "PollAsync");
        Run(page, "BackgroundAsync");
        Assert.False(File.Exists(plate));

        // no game: a mention is read in the feed and nothing is written, not even the folder
        page.GameRunning = () => false;
        site.More = true; site.MoreMention = true; site.LineId = 13;
        Run(page, "PollAsync");
        Pump(() => Lines(feed).Count == 4, "the mention in the feed");
        Assert.False(File.Exists(plate));
        Assert.False(Directory.Exists(Path.GetDirectoryName(plate)!) && Directory.EnumerateFiles(Path.GetDirectoryName(plate)!, "chat.txt").Any());

        // a game: a plain line of a channel is no plate, a mention is
        page.GameRunning = () => true;
        site.MoreMention = false; site.LineId = 15;
        Run(page, "PollAsync");
        Pump(() => Lines(feed).Count == 5, "the plain line");
        Assert.False(File.Exists(plate));
        site.MoreMention = true; site.LineId = 16;
        Run(page, "PollAsync");
        Pump(() => Lines(feed).Count == 6, "the mention");
        Assert.Equal("Борис: новая строка", Said()[1]);
        long counter = long.Parse(Said()[0]);

        // a private message: the inbox says Anna wrote again
        site.NewPrivate = true;
        Run(page, "BackgroundAsync");
        Pump(() => Said().Length > 1 && Said()[1].StartsWith("Анна: "), "the private message on the plate");
        Assert.Equal("Анна: Новое сообщение", Said()[1]);
        Assert.True(long.Parse(Said()[0]) > counter);

        // the option: every new line of a channel
        F<Settings>(w, "_settings").ChatNoticeAll = true;
        site.MoreMention = false; site.LineId = 17;
        Run(page, "PollAsync");
        Pump(() => Lines(feed).Count == 7, "the line for the option");
        Assert.Equal("Борис: новая строка", Said()[1]);

        // the launcher closes: the plate has nothing more to say
        w.Close();
        Pump(() => !File.Exists(plate), "the plate's file to go");
    }

    [AvaloniaFact]
    public void A_narrow_window_puts_the_people_on_a_page_of_their_own()
    {
        Link();
        var site = StartSite();
        var w = Open(site, width: 900, height: 800);
        var page = OpenChat(w);
        Assert.True(page.Bounds.Width < 760, "the page is " + page.Bounds.Width + " wide");
        var people = F<Control>(page, "_rightPanel");
        var button = F<Button>(page, "_peopleButton");
        Assert.False(people.IsVisible);
        Assert.True(button.IsVisible);
        Shot(w, "chat-6-narrow");

        Click(button);
        Assert.True(people.IsVisible);
        Assert.False(F<Control>(page, "_middle").IsVisible);
        Assert.Contains("Катя", Texts(F<StackPanel>(page, "_attendees")));
        Shot(w, "chat-7-narrow-people");
        // the middle column is gone with its button: the way back is on the page of the people
        var back = F<Button>(page, "_peopleBack");
        Assert.True(back.IsVisible);
        Click(back);
        Assert.False(people.IsVisible);
        Assert.True(F<Control>(page, "_middle").IsVisible);
        Assert.True(button.IsVisible);
        w.Close();
    }
}
