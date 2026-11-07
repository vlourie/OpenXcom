using System.Net;

namespace Xp.Launcher.Core.Tests;

/// <summary>The text channels of the launcher (docs/portal/VOICE_IRC.md): the calls, the cursor, the input line, and when a running game is told.</summary>
public sealed class ChatTests : IDisposable
{
    const string Token = "device-token-0123456789";
    const string Ann = """{"id":"11111111-1111-1111-1111-111111111111","name":"Анна"}""";
    const string Bob = """{"id":"22222222-2222-2222-2222-222222222222","name":"Борис"}""";

    readonly string _root = Path.Combine(Path.GetTempPath(), "xp-tests", Guid.NewGuid().ToString("N"));
    readonly GamePaths _paths;
    readonly FakeVoiceSite _site = new();
    readonly PortalClient _portal;

    public ChatTests()
    {
        Directory.CreateDirectory(_root);
        _paths = new GamePaths(_root);
        _portal = new PortalClient(new HttpClient(_site), new Uri("https://portal.test"));
    }

    public void Dispose()
    {
        try { Directory.Delete(_root, recursive: true); } catch (IOException) { }
    }

    static ChatLine Line(long id, string author, string body, bool mine = false, bool mention = false, string kind = "text") =>
        new(id, kind, null, new VoicePerson(Guid.NewGuid(), author), body, DateTimeOffset.UtcNow, mine, mention);

    static ChatFeed Feed(long last, params ChatLine[] lines) =>
        new("ch-general", "#общий", null, true, false, true, last, [.. lines], [], []);

    // ---------------------------------------------------------------- the calls

    [Fact]
    public async Task The_list_of_channels_is_read_in_one_call_with_the_counters()
    {
        _site.Answers["GET /api/v1/voice/channels"] = (HttpStatusCode.OK, $$"""
            {"channels":[{"room":"ch-general","title":"#общий","topic":"Общий разговор","isPublic":true,"mine":false,"owner":{{Ann}},"state":"ok","joined":true,"here":3,"unread":5,"mentions":1,"lastId":120}],
             "rooms":[{"room":"abcdefgh23","title":"Каюта","topic":null,"isPublic":false,"mine":true,"owner":{{Bob}},"state":"room_closed","joined":false,"here":0,"unread":0,"mentions":0,"lastId":"7"}]}
            """);

        var list = await _portal.ChatChannelsAsync(Token, default);

        var c = Assert.Single(list.Channels);
        Assert.Equal((5, 1, 120L, true), (c.Unread, c.Mentions, c.LastId, c.CanEnter));
        var r = Assert.Single(list.Rooms);
        Assert.False(r.CanEnter);                // a closed room is not worth a "Join voice"
        Assert.Equal(7L, r.LastId);              // numbers may come as strings
        Assert.Null(r.Topic);
        Assert.Equal(Token, Assert.Single(_site.Seen).Token);
    }

    [Fact]
    public async Task The_feed_is_asked_after_the_cursor_and_the_text_goes_as_it_was_typed()
    {
        _site.Answers["GET /api/v1/voice/rooms/ch-general/messages?limit=100"] = (HttpStatusCode.OK, $$"""
            {"room":"ch-general","title":"#общий","topic":"Тема","isPublic":true,"canModerate":false,"canTalk":true,"last":12,
             "lines":[{"id":11,"kind":"text","event":null,"author":{{Ann}},"body":"Привет <b>всем</b> https://evil.test","at":"2026-11-05T10:00:00Z","mine":false,"mention":true},
                      {"id":12,"kind":"system","event":"join","author":{{Bob}},"body":"","at":"2026-11-05T10:01:00Z","mine":false,"mention":false}],
             "removed":[],"attendees":[{"person":{{Ann}},"operator":true,"voice":false,"muted":false},{"person":{{Bob}},"operator":false,"voice":true,"muted":true}]}
            """);
        _site.Answers["GET /api/v1/voice/rooms/ch-general/messages?after=12&limit=200"] = (HttpStatusCode.OK,
            """{"room":"ch-general","title":"#общий","topic":null,"isPublic":true,"canModerate":true,"canTalk":true,"last":12,"lines":[],"removed":[11],"attendees":[]}""");
        _site.Answers["POST /api/v1/voice/rooms/ch-general/messages"] = (HttpStatusCode.OK,
            """{"result":"unknown","line":null,"command":"/dance","person":null,"text":null}""");

        var first = await _portal.ChatFeedAsync(Token, "ch-general", null, 100, default);
        var next = await _portal.ChatFeedAsync(Token, "ch-general", first.Last, 200, default);
        var posted = await _portal.ChatSayAsync(Token, "ch-general", "/dance now", default);

        Assert.Equal("Привет <b>всем</b> https://evil.test", first.Lines[0].Body);   // text is text, never markup
        Assert.True(first.Lines[0].Mention);
        Assert.True(first.Lines[1].IsSystem);
        Assert.Equal("join", first.Lines[1].Event);
        Assert.Equal([true, false], first.Attendees.Select(a => a.Operator));
        Assert.True(first.Attendees[1].Voice && first.Attendees[1].Muted);
        Assert.Equal([11L], next.Removed);
        Assert.True(next.CanModerate);
        Assert.Equal("unknown", posted.Result);
        Assert.Null(posted.Line);
        Assert.Equal("""{"text":"/dance now"}""", _site.Seen[^1].Body);
    }

    [Fact]
    public async Task Join_part_and_delete_are_calls_of_their_own()
    {
        _site.Answers["POST /api/v1/voice/rooms/ch-general/join"] = (HttpStatusCode.NoContent, "");
        _site.Answers["POST /api/v1/voice/rooms/ch-general/part"] = (HttpStatusCode.NoContent, "");
        _site.Answers["DELETE /api/v1/voice/rooms/ch-general/messages/33"] = (HttpStatusCode.NoContent, "");

        await _portal.ChatJoinAsync(Token, "ch-general", default);
        await _portal.ChatPartAsync(Token, "ch-general", default);
        await _portal.ChatDeleteAsync(Token, "ch-general", 33, default);

        Assert.Equal(3, _site.Seen.Count);
        Assert.All(_site.Seen, s => Assert.Equal(Token, s.Token));
    }

    [Fact]
    public async Task A_refusal_of_the_site_is_an_exception_with_its_code()
    {
        _site.Problem("POST /api/v1/voice/rooms/ch-general/messages", HttpStatusCode.TooManyRequests, "limit_rate");
        var e = await Assert.ThrowsAsync<PortalException>(() => _portal.ChatSayAsync(Token, "ch-general", "раз", default));
        Assert.Equal("limit_rate", e.Code);
    }

    [Fact]
    public void A_link_to_a_public_channel_names_it_in_spite_of_the_hyphen()
    {
        Assert.Equal("ch-general", VoiceLink.Parse("xpiratez://voice/ch-general"));
        Assert.Equal("abcdefgh23", VoiceLink.Parse("xpiratez://voice/abcdefgh23"));
        Assert.Null(VoiceLink.Parse("xpiratez://voice/-x"));
        Assert.Null(VoiceLink.Parse("xpiratez://voice/ch-general/extra"));
        Assert.Null(VoiceLink.Parse("xpiratez://voice/ch general"));
    }

    // ---------------------------------------------------------------- the input line

    [Theory]
    [InlineData("", ChatInputKind.Empty)]
    [InlineData("   ", ChatInputKind.Empty)]
    [InlineData("привет, мир", ChatInputKind.Say)]
    [InlineData("не /команда", ChatInputKind.Say)]
    [InlineData("/join #english", ChatInputKind.Client)]
    [InlineData("  /PART ", ChatInputKind.Client)]
    [InlineData("/who", ChatInputKind.Client)]
    [InlineData("/help", ChatInputKind.Client)]
    [InlineData("/me машет рукой", ChatInputKind.Server)]
    [InlineData("/msg Анна привет", ChatInputKind.Server)]
    [InlineData("/kick Борис за дело", ChatInputKind.Server)]
    [InlineData("/dance", ChatInputKind.Server)]
    [InlineData("//", ChatInputKind.Server)]
    [InlineData("/", ChatInputKind.Server)]
    public void A_line_with_a_slash_is_a_command_and_never_a_message(string typed, ChatInputKind kind)
    {
        Assert.Equal(kind, ChatInput.Parse(typed).Kind);
    }

    [Fact]
    public void The_command_and_its_argument_are_split_and_the_text_is_kept()
    {
        var join = ChatInput.Parse("  /Join   #общий  ");
        Assert.Equal(("join", "#общий"), (join.Command, join.Argument));
        var msg = ChatInput.Parse("/msg Анна  привет, как дела?");
        Assert.Equal(("msg", "Анна  привет, как дела?"), (msg.Command, msg.Argument));
        Assert.Equal("/msg Анна  привет, как дела?", msg.Text);
    }

    // ---------------------------------------------------------------- the feed buffer

    [Fact]
    public void The_first_answer_is_history_the_next_ones_add_only_what_is_new_by_the_cursor()
    {
        var b = new ChatBuffer();
        Assert.Null(b.Cursor);

        Assert.Empty(b.Add(Feed(2, Line(1, "a", "один"), Line(2, "b", "два"))));   // history: nothing is "new" in it
        Assert.Equal(2L, b.Cursor);
        Assert.Equal(2, b.Lines.Count);

        var fresh = b.Add(Feed(4, Line(2, "b", "два"), Line(3, "a", "три"), Line(4, "b", "четыре")));
        Assert.Equal([3L, 4L], fresh.Select(l => l.Id));
        Assert.Equal([1L, 2L, 3L, 4L], b.Lines.Select(l => l.Id));
        Assert.Equal(4L, b.Cursor);

        Assert.Empty(b.Add(Feed(4)));           // nothing new: the cursor stays
        Assert.Equal(4L, b.Cursor);
    }

    [Fact]
    public void A_removed_line_goes_but_a_service_line_stays_and_my_own_line_is_not_doubled()
    {
        var b = new ChatBuffer();
        b.Add(Feed(3, Line(1, "a", "плохое"), Line(2, "sys", "", kind: "system"), Line(3, "a", "хорошее")));
        var gone = new ChatFeed("ch-general", "#общий", null, true, false, true, 3, [], [1, 2], []);
        b.Add(gone);
        Assert.Equal([2L, 3L], b.Lines.Select(l => l.Id));

        var mine = Line(4, "me", "моё", mine: true);
        b.Add(mine);
        b.Add(Feed(4, mine));
        Assert.Equal(3, b.Lines.Count);
    }

    // ---------------------------------------------------------------- the plate in a running game

    ChatNoticer Noticer(bool running, bool all = false) => new(() => _paths, () => running, () => all);

    string? PlateText() => File.Exists(ChatNotice.PathIn(_paths)) ? File.ReadAllLines(ChatNotice.PathIn(_paths))[1] : null;

    [Fact]
    public void The_first_look_at_a_channel_is_history_and_gives_no_plate()
    {
        var n = Noticer(running: true, all: true);
        Assert.False(n.Feed("ch-general", [Line(1, "Анна", "старое", mention: true), Line(2, "Борис", "тоже старое")]));
        Assert.False(File.Exists(ChatNotice.PathIn(_paths)));
    }

    [Fact]
    public void A_running_game_hears_of_a_mention_and_not_of_chatter_unless_the_option_is_on()
    {
        var n = Noticer(running: true);
        n.Feed("ch-general", [Line(1, "Анна", "старое")]);

        Assert.False(n.Feed("ch-general", [Line(2, "Борис", "просто болтовня")]));
        Assert.False(File.Exists(ChatNotice.PathIn(_paths)));

        Assert.True(n.Feed("ch-general", [Line(3, "Анна", "Капитан, ты где?", mention: true)]));
        Assert.Equal("Анна: Капитан, ты где?", PlateText());

        // the same lines again are not news
        Assert.False(n.Feed("ch-general", [Line(3, "Анна", "Капитан, ты где?", mention: true)]));
    }

    [Fact]
    public void With_the_option_every_line_of_others_is_a_plate_but_never_my_own_or_a_service_line()
    {
        var n = Noticer(running: true, all: true);
        n.Feed("ch-general", []);

        Assert.False(n.Feed("ch-general", [Line(1, "я", "моя строка", mine: true), Line(2, "система", "вошёл", kind: "system")]));
        Assert.True(n.Feed("ch-general", [Line(3, "Борис", "общая новость")]));
        Assert.Equal("Борис: общая новость", PlateText());
    }

    [Fact]
    public void Without_a_game_nothing_is_written_and_what_passed_meanwhile_is_not_shown_later()
    {
        bool running = false;
        var n = new ChatNoticer(() => _paths, () => running, () => false);
        n.Feed("ch-general", []);

        Assert.False(n.Feed("ch-general", [Line(1, "Анна", "пока игры нет", mention: true)]));
        Assert.False(File.Exists(ChatNotice.PathIn(_paths)));
        Assert.False(Directory.Exists(Path.Combine(_root, "launcher")));   // not even the folder (R-179)

        running = true;
        Assert.False(n.Feed("ch-general", [Line(1, "Анна", "пока игры нет", mention: true)]));
        Assert.False(File.Exists(ChatNotice.PathIn(_paths)));
        Assert.True(n.Feed("ch-general", [Line(2, "Анна", "а теперь есть", mention: true)]));
    }

    [Fact]
    public void A_channel_opened_afresh_has_a_history_again()
    {
        var n = Noticer(running: true);
        n.Feed("ch-general", []);
        n.Forget("ch-general");
        Assert.False(n.Feed("ch-general", [Line(5, "Анна", "пока вас не было", mention: true)]));
    }

    static ChatChannel Row(string room, int unread, int mentions, bool joined = true) =>
        new(room, "#" + room, null, true, false, new VoicePerson(Guid.Empty, ""), "ok", joined, 0, unread, mentions, 0);

    [Fact]
    public void The_background_list_gives_a_plate_for_a_new_mention_only_and_for_new_lines_with_the_option()
    {
        var quiet = Noticer(running: true);
        Assert.False(quiet.Channels(new([Row("общий", 4, 1)], []), "вас упомянули", n => $"новых: {n}"));   // the first look
        Assert.False(File.Exists(ChatNotice.PathIn(_paths)));

        Assert.False(quiet.Channels(new([Row("общий", 6, 1)], []), "вас упомянули", n => $"новых: {n}"));   // chatter
        Assert.True(quiet.Channels(new([Row("общий", 7, 2)], []), "вас упомянули", n => $"новых: {n}"));
        Assert.Equal("#общий: вас упомянули", PlateText());

        var loud = Noticer(running: true, all: true);
        loud.Channels(new([Row("общий", 0, 0)], []), "вас упомянули", n => $"новых: {n}");
        Assert.True(loud.Channels(new([Row("общий", 3, 0)], []), "вас упомянули", n => $"новых: {n}"));
        Assert.Equal("#общий: новых: 3", PlateText());
    }

    [Fact]
    public void A_channel_whose_feed_is_on_screen_is_left_to_the_feed_and_a_new_channel_is_only_a_baseline()
    {
        var n = Noticer(running: true);
        n.Channels(new([Row("общий", 0, 0)], []), "m", c => "n");
        n.Feed("общий", []);                                             // the feed is being read just now
        Assert.False(n.Channels(new([Row("общий", 1, 1), Row("новый", 9, 9)], []), "m", c => "n"));
        Assert.False(n.Channels(new([Row("общий", 1, 1), Row("новый", 9, 9)], []), "m", c => "n"));
        Assert.False(File.Exists(ChatNotice.PathIn(_paths)));
    }

    static MessageDialogue Dialogue(string name, string preview, int unread, bool lastMine, DateTimeOffset at) =>
        new(new VoicePerson(Guid.NewGuid(), name), preview, lastMine, at, unread);

    [Fact]
    public void A_private_message_is_a_plate_but_what_waited_at_the_start_is_not()
    {
        var n = Noticer(running: true);
        var t0 = DateTimeOffset.UtcNow.AddHours(-1);
        var ann = new VoicePerson(Guid.NewGuid(), "Анна");
        MessageInbox Inbox(params MessageDialogue[] d) => new(d.Sum(x => x.Unread), [.. d]);

        Assert.False(n.Inbox(Inbox(new MessageDialogue(ann, "давнее", false, t0, 3))));   // the first look: 3 unread, no plate
        Assert.False(File.Exists(ChatNotice.PathIn(_paths)));

        Assert.False(n.Inbox(Inbox(new MessageDialogue(ann, "давнее", false, t0, 3))));   // the same again
        Assert.False(n.Inbox(Inbox(new MessageDialogue(ann, "мой ответ", true, t0.AddMinutes(1), 0))));
        Assert.True(n.Inbox(Inbox(new MessageDialogue(ann, "ты тут?", false, t0.AddMinutes(2), 1))));
        Assert.Equal("Анна: ты тут?", PlateText());
        Assert.False(n.Inbox(Inbox(new MessageDialogue(ann, "ты тут?", false, t0.AddMinutes(2), 1))));
    }

    [Fact]
    public void A_private_message_without_a_game_writes_nothing()
    {
        var n = Noticer(running: false);
        var ann = new VoicePerson(Guid.NewGuid(), "Анна");
        n.Inbox(new MessageInbox(0, []));
        Assert.False(n.Inbox(new MessageInbox(1, [new MessageDialogue(ann, "эй", false, DateTimeOffset.UtcNow, 1)])));
        Assert.False(Directory.Exists(Path.Combine(_root, "launcher")));
    }

    [Fact]
    public void The_file_is_cleared_when_the_launcher_goes()
    {
        var n = Noticer(running: true);
        n.Feed("ch-general", []);
        Assert.True(n.Feed("ch-general", [Line(2, "Анна", "эй", mention: true)]));
        Assert.True(File.Exists(ChatNotice.PathIn(_paths)));
        ChatNotice.Clear(_paths);
        Assert.False(File.Exists(ChatNotice.PathIn(_paths)));
    }

    [Fact]
    public void A_stamp_is_the_time_today_and_the_date_with_it_on_another_day()
    {
        var now = new DateTimeOffset(2026, 11, 5, 15, 0, 0, TimeSpan.Zero);
        Assert.Equal(ChatFormat.Time(now), ChatFormat.Stamp(now, now));
        Assert.Matches(@"^\d\d\.\d\d \d\d:\d\d$", ChatFormat.Stamp(now.AddDays(-3), now));
    }
}
