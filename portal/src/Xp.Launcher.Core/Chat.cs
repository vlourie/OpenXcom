using System.Net.Http.Json;
using System.Text.Json.Serialization;

namespace Xp.Launcher.Core;

// The text half of the voice API (docs/portal/VOICE_IRC.md section 4, portal/src/Xp.Portal/Voice/VoiceChat.cs): public
// channels and rooms with a feed of lines, read after a cursor. The site owns every rule (who may read, write, moderate);
// the launcher draws what it is given as text and shows the reason it gets back.

/// <summary>
/// One line of a feed. Kind: text, action or system; for a system line Event names what happened (join, part, topic,
/// kick, ban, unban, mute, unmute) and Body is its argument. Mention is the site's decision for this reader.
/// </summary>
public sealed record ChatLine(long Id, string Kind, string? Event, VoicePerson Author, string Body, DateTimeOffset At, bool Mine, bool Mention)
{
    public bool IsSystem => Kind == "system";
}

/// <summary>Somebody in the channel: Operator is the owner or staff, Voice is in the voice room now, Muted may not talk there.</summary>
public sealed record ChatAttendee(VoicePerson Person, bool Operator, bool Voice, bool Muted);

/// <summary>New lines after a cursor, who is here, and what the page above the feed needs. Last is the next cursor.</summary>
public sealed record ChatFeed(string Room, string Title, string? Topic, bool IsPublic, bool CanModerate, bool CanTalk, long Last,
    List<ChatLine> Lines, List<long> Removed, List<ChatAttendee> Attendees);

/// <summary>A channel or a room in the list on the left. Unread and Mentions count only for a channel the person has joined.</summary>
public sealed record ChatChannel(string Room, string Title, string? Topic, bool IsPublic, bool Mine, VoicePerson Owner, string State,
    bool Joined, int Here, int Unread, int Mentions, long LastId)
{
    public bool CanEnter => State == "ok";
}

public sealed record ChatChannels(List<ChatChannel> Channels, List<ChatChannel> Rooms);

/// <summary>
/// What a sent line came to. Result: posted (Line), done (a command of the moderators ran), private (/msg went to Person),
/// topic (/topic without text: Text is the current one), client (the client's own command: nothing happened there),
/// unknown (no such command: nothing was sent, the client shows the hint).
/// </summary>
public sealed record ChatPosted(string Result, ChatLine? Line, string? Command, VoicePerson? Person, string? Text);

internal sealed record ChatSayBody(string Text);

/// <summary>The limits of the site (Xp.Portal VoiceLimits) the input box keeps to.</summary>
public static class ChatRules
{
    public const int LineMax = 1000;
    public const int HistoryDefault = 100;
}

public sealed partial class PortalClient
{
    /// <summary>Public channels, my rooms and what is new in each: one answer for the list on the left.</summary>
    public Task<ChatChannels> ChatChannelsAsync(string deviceToken, CancellationToken ct) =>
        AskAsync(DeviceRequest(HttpMethod.Get, "api/v1/voice/channels", deviceToken), ChatJson.Default.ChatChannels, ct);

    /// <summary>
    /// The lines after a cursor (the newest ones when none is given) and who is here. Asking is also being here, and the
    /// lines handed over are read: call it only for a channel that is in front of the person.
    /// </summary>
    public Task<ChatFeed> ChatFeedAsync(string deviceToken, string room, long? after, int? limit, CancellationToken ct)
    {
        var query = new List<string>();
        if (after is { } a) query.Add("after=" + a.ToString(System.Globalization.CultureInfo.InvariantCulture));
        if (limit is { } l) query.Add("limit=" + l.ToString(System.Globalization.CultureInfo.InvariantCulture));
        var path = RoomPath(room, "messages") + (query.Count > 0 ? "?" + string.Join("&", query) : "");
        return AskAsync(DeviceRequest(HttpMethod.Get, path, deviceToken), ChatJson.Default.ChatFeed, ct);
    }

    /// <summary>A line or a command; the site tells which it was (<see cref="ChatPosted.Result"/>).</summary>
    public Task<ChatPosted> ChatSayAsync(string deviceToken, string room, string text, CancellationToken ct) =>
        AskAsync(DeviceRequest(HttpMethod.Post, RoomPath(room, "messages"), deviceToken,
            JsonContent.Create(new ChatSayBody(text), ChatJson.Default.ChatSayBody)), ChatJson.Default.ChatPosted, ct);

    public Task ChatDeleteAsync(string deviceToken, string room, long id, CancellationToken ct) =>
        DoAsync(DeviceRequest(HttpMethod.Delete, RoomPath(room, "messages/" + id.ToString(System.Globalization.CultureInfo.InvariantCulture)), deviceToken), ct);

    public Task ChatJoinAsync(string deviceToken, string room, CancellationToken ct) =>
        DoAsync(DeviceRequest(HttpMethod.Post, RoomPath(room, "join"), deviceToken), ct);

    public Task ChatPartAsync(string deviceToken, string room, CancellationToken ct) =>
        DoAsync(DeviceRequest(HttpMethod.Post, RoomPath(room, "part"), deviceToken), ct);
}

[JsonSourceGenerationOptions(PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase, PropertyNameCaseInsensitive = true,
    NumberHandling = JsonNumberHandling.AllowReadingFromString)]
[JsonSerializable(typeof(ChatChannels))]
[JsonSerializable(typeof(ChatFeed))]
[JsonSerializable(typeof(ChatPosted))]
[JsonSerializable(typeof(ChatSayBody))]
internal sealed partial class ChatJson : JsonSerializerContext
{
}

public enum ChatInputKind
{
    /// <summary>Nothing but spaces: nothing to do.</summary>
    Empty,
    /// <summary>Words for the channel.</summary>
    Say,
    /// <summary>/join /part /who /help: the launcher does it itself, the site never hears of it.</summary>
    Client,
    /// <summary>Any other slash line: the site decides (/me /topic /msg /kick ...) and answers "unknown" to what it does not know.</summary>
    Server,
}

/// <summary>What the input box got. A line that starts with a slash is a command and never becomes a message by mistake.</summary>
public sealed record ChatInput(ChatInputKind Kind, string Command, string Argument, string Text)
{
    static readonly HashSet<string> ClientCommands = new(StringComparer.Ordinal) { "join", "part", "who", "help" };

    public static ChatInput Parse(string? typed)
    {
        var text = (typed ?? "").Trim();
        if (text.Length == 0) return new ChatInput(ChatInputKind.Empty, "", "", "");
        if (text[0] != '/') return new ChatInput(ChatInputKind.Say, "", "", text);
        int space = text.IndexOf(' ');
        var command = (space < 0 ? text[1..] : text[1..space]).ToLowerInvariant();
        var rest = space < 0 ? "" : text[(space + 1)..].Trim();
        return ClientCommands.Contains(command)
            ? new ChatInput(ChatInputKind.Client, command, rest, text)
            : new ChatInput(ChatInputKind.Server, command, rest, text);
    }
}

/// <summary>"12:34 &lt;nick&gt; text" and its kin: the one place that says how a line of the feed reads.</summary>
public static class ChatFormat
{
    public static string Time(DateTimeOffset at) => at.ToLocalTime().ToString("HH:mm", System.Globalization.CultureInfo.InvariantCulture);

    /// <summary>"12:34" for today, "02.11 12:34" for another day: the stamp in front of a line.</summary>
    public static string Stamp(DateTimeOffset at, DateTimeOffset now)
    {
        var local = at.ToLocalTime();
        return local.Date == now.ToLocalTime().Date ? Time(at) : local.ToString("dd.MM HH:mm", System.Globalization.CultureInfo.InvariantCulture);
    }

    /// <summary>The nick as shown for a channel title: a public channel is "#name" even if the title was typed without it.</summary>
    public static string Title(ChatChannel c) => c.IsPublic && !c.Title.StartsWith('#') ? "#" + c.Title : c.Title;
}

/// <summary>
/// The lines of one open feed, kept in order by id: new lines after the cursor are added, lines the site says were removed
/// are taken out, and a line seen twice is shown once. The cursor is the site's <see cref="ChatFeed.Last"/>.
/// </summary>
public sealed class ChatBuffer(int capacity = 500)
{
    readonly List<ChatLine> _lines = [];

    public IReadOnlyList<ChatLine> Lines => _lines;
    /// <summary>The cursor for the next question; null before the first answer (then the newest lines are asked for).</summary>
    public long? Cursor { get; private set; }

    public void Reset()
    {
        _lines.Clear();
        Cursor = null;
    }

    /// <summary>Adds an answer. Returns the lines that were new here (the ones to notify about, none on the first answer).</summary>
    public List<ChatLine> Add(ChatFeed feed)
    {
        bool first = Cursor is null;
        var fresh = new List<ChatLine>();
        foreach (var l in feed.Lines)
        {
            if (_lines.Any(x => x.Id == l.Id)) continue;
            _lines.Add(l);
            fresh.Add(l);
        }
        _lines.Sort((a, b) => a.Id.CompareTo(b.Id));
        if (feed.Removed.Count > 0) _lines.RemoveAll(l => feed.Removed.Contains(l.Id) && !l.IsSystem);
        if (_lines.Count > capacity) _lines.RemoveRange(0, _lines.Count - capacity);
        Cursor = Math.Max(Cursor ?? 0, feed.Last);
        return first ? [] : fresh;
    }

    /// <summary>My own line just posted: shown at once and not asked for again.</summary>
    public void Add(ChatLine mine)
    {
        if (_lines.Any(x => x.Id == mine.Id)) return;
        _lines.Add(mine);
        _lines.Sort((a, b) => a.Id.CompareTo(b.Id));
    }
}

/// <summary>
/// Decides when a running game is told (<see cref="ChatNotice"/>): a private message, a mention of the nick, and with the
/// option every new line of a channel. It writes only while the game runs. What was there at the first look is old and
/// never a notice: every source is read once as a baseline before it can announce anything.
/// </summary>
public sealed class ChatNoticer(Func<GamePaths?> paths, Func<bool> gameRunning, Func<bool> allChannels)
{
    readonly Dictionary<string, long> _lines = new(StringComparer.Ordinal);
    readonly Dictionary<string, (int Unread, int Mentions)> _counts = new(StringComparer.Ordinal);
    readonly Dictionary<string, DateTime> _polled = new(StringComparer.Ordinal);
    readonly Dictionary<Guid, DateTimeOffset> _dialogues = [];
    bool _channelsSeen, _inboxSeen;

    /// <summary>How long a feed that is being read covers its channel: the list of channels leaves it alone.</summary>
    public static readonly TimeSpan Covers = TimeSpan.FromSeconds(10);

    /// <summary>A channel is opened afresh: what the first answer brings is its history and no notice.</summary>
    public void Forget(string room) => _lines.Remove(room);

    /// <summary>Unlinked or another account: every source is a first look again.</summary>
    public void Reset()
    {
        _lines.Clear();
        _counts.Clear();
        _polled.Clear();
        _dialogues.Clear();
        _channelsSeen = _inboxSeen = false;
    }

    bool Tell(string nick, string text)
    {
        if (paths() is not { } p || !gameRunning()) return false;
        return ChatNotice.Write(p, nick, text) > 0;
    }

    /// <summary>Lines of an open feed. The first answer for a channel is its history: no notice. True when the game was told.</summary>
    public bool Feed(string room, IReadOnlyList<ChatLine> lines)
    {
        _polled[room] = DateTime.UtcNow;
        if (!_lines.TryGetValue(room, out var seen))
        {
            _lines[room] = lines.Select(l => l.Id).DefaultIfEmpty(0).Max();
            return false;
        }
        ChatLine? worth = null;
        foreach (var l in lines.Where(l => l.Id > seen).OrderBy(l => l.Id))
        {
            if (l.Mine || l.IsSystem) continue;
            if (l.Mention || allChannels()) worth = l;
        }
        _lines[room] = Math.Max(seen, lines.Select(l => l.Id).DefaultIfEmpty(0).Max());
        return worth is not null && Tell(worth.Author.Name, worth.Body);
    }

    /// <summary>
    /// The list of channels with its counters, asked in the background. A mention that was not there at the last look is a
    /// notice naming the channel; with the option, so is any growth of unread lines. A channel whose feed is on screen
    /// is the feed's business. The text of the lines is not asked for: asking would mark them read.
    /// </summary>
    public bool Channels(ChatChannels list, string mentionText, Func<int, string> unreadText)
    {
        bool told = false;
        var now = DateTime.UtcNow;
        foreach (var c in list.Channels.Concat(list.Rooms))
        {
            bool known = _counts.TryGetValue(c.Room, out var was);
            _counts[c.Room] = (c.Unread, c.Mentions);
            if (!_channelsSeen || !known) continue;
            if (_polled.TryGetValue(c.Room, out var at) && now - at < Covers) continue;
            if (c.Mentions > was.Mentions) told |= Tell(ChatFormat.Title(c), mentionText);
            else if (allChannels() && c.Unread > was.Unread) told |= Tell(ChatFormat.Title(c), unreadText(c.Unread - was.Unread));
        }
        _channelsSeen = true;
        return told;
    }

    /// <summary>The inbox of private messages: a dialogue whose last message is from the other side, unread and newer than the last look.</summary>
    public bool Inbox(MessageInbox inbox)
    {
        MessageDialogue? worth = null;
        foreach (var d in inbox.Dialogues.OrderBy(d => d.At))
        {
            bool known = _dialogues.TryGetValue(d.Person.Id, out var was);
            _dialogues[d.Person.Id] = d.At;
            if (_inboxSeen && !d.LastMine && d.Unread > 0 && (!known || d.At > was)) worth = d;
        }
        _inboxSeen = true;
        return worth is not null && Tell(worth.Person.Name, worth.Preview);
    }
}
