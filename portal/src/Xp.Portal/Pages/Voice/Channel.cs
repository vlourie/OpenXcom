using System.Net;
using System.Text.RegularExpressions;
using Microsoft.AspNetCore.Html;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.RateLimiting;
using Xp.Portal.Data;
using Xp.Portal.Messages;
using Xp.Portal.Site;
using Xp.Portal.Voice;

namespace Xp.Portal.Pages.Voice;

/// <summary>
/// The page of a channel or a room in the shape of an IRC client (docs/portal/VOICE_IRC.md): the channels and dialogues on
/// the left, the feed with its topic in the middle, who is here on the right. It serves /voice (the first channel) and
/// /voice/rooms/{room}. Every rule is <see cref="VoiceService"/>'s; this class only turns its answers into a page and a
/// form post into its calls. Without scripts a post reloads the page; js/channel.js only asks for new lines.
/// </summary>
[EnableRateLimiting("voice-write")]
public sealed class ChannelModel(VoiceService voice, MessageService messages, Text text) : VoicePage
{
    [BindProperty(SupportsGet = true)] public string? Room { get; set; }
    public ChannelsView Lists { get; private set; } = new([], []);
    public IReadOnlyList<DialogueRow> Dialogues { get; private set; } = [];
    /// <summary>Where the person stands with the open room; null when it is not theirs to see (or there is none).</summary>
    public RoomView? Summary { get; private set; }
    public MessagesView? Feed { get; private set; }
    public int Incoming { get; private set; }
    public string? Notice { get; private set; }
    public Guid MeId => Me;
    public string LauncherLink => $"xpiratez://voice/{Room}";
    public string FeedUrl => $"/api/v1/voice/rooms/{Uri.EscapeDataString(Room ?? "")}/messages";
    public string ChannelPath(string room) => $"/voice/rooms/{Uri.EscapeDataString(room)}";
    public bool Open => Feed is not null;
    /// <summary>The room is shown as missing: asked for by a code that is not theirs, whatever the reason.</summary>
    public bool Missing => Room is not null && Summary is null;

    async Task LoadAsync(bool join, CancellationToken ct)
    {
        Lists = await voice.ChannelsAsync(Me, ct);
        Dialogues = await messages.InboxAsync(Me, ct);
        Incoming = (await voice.FriendsAsync(Me, 1, 1, ct)).Incoming.Count;
        Notice = TempData["chat.notice"] as string;
        Room ??= Lists.Channels.FirstOrDefault(c => c.State == "ok")?.Room;
        if (Room is null) return;
        // a stranger gets the same 404 on a look and on a post: nothing tells a room from no room
        try { Summary = await voice.RoomViewAsync(Me, Room, ct); }
        catch (VoiceException) { Summary = null; return; }
        if (Summary.Room.State != "ok") return;
        try
        {
            if (join) await voice.JoinAsync(Me, Room, ct);
            Feed = await voice.MessagesAsync(Me, Room, null, VoiceLimits.HistoryDefault, ct);
        }
        catch (VoiceException e) { Errors.Add(ErrorKey(e.Code)); }
    }

    public async Task<IActionResult> OnGetAsync(CancellationToken ct)
    {
        await LoadAsync(join: true, ct);
        if (Missing) Response.StatusCode = StatusCodes.Status404NotFound;
        return Page();
    }

    string Back => $"/voice/rooms/{Uri.EscapeDataString(Room ?? "")}";

    async Task<IActionResult> ReloadAsync(CancellationToken ct)
    {
        await LoadAsync(join: false, ct);
        if (Missing) Response.StatusCode = StatusCodes.Status404NotFound;
        return Page();
    }

    public async Task<IActionResult> OnPostSayAsync(string? line, CancellationToken ct)
    {
        PostResult result;
        try { result = await voice.PostAsync(Me, Room, line, ct); }
        catch (VoiceException e)
        {
            Errors.Add(ErrorKey(e.Code));
            return await ReloadAsync(ct);
        }
        switch (result.Result)
        {
            case "private": TempData["chat.notice"] = text.Format("chan.notice.private", result.Person?.Name ?? ""); break;
            case "topic": TempData["chat.notice"] = string.IsNullOrEmpty(result.Text) ? text["chan.notice.notopic"] : text.Format("chan.notice.topic", result.Text); break;
            case "unknown": TempData["chat.notice"] = text.Format("chan.notice.unknown", result.Command ?? ""); break;
            case "client": return await ClientCommandAsync(result.Command ?? "", line ?? "", ct);
        }
        return LocalRedirect(Back + "#end");
    }

    /// <summary>/join, /part, /who and /help are the client's: here the client is this page.</summary>
    async Task<IActionResult> ClientCommandAsync(string command, string line, CancellationToken ct)
    {
        switch (command)
        {
            case "help":
                TempData["chat.notice"] = text["chan.help"];
                break;
            case "who":
            {
                var feed = await voice.MessagesAsync(Me, Room, null, 1, ct);
                TempData["chat.notice"] = text.Format("chan.notice.who", string.Join(", ", feed.Attendees.Select(a => a.Person.Name)));
                break;
            }
            case "part":
                await voice.PartAsync(Me, Room, ct);
                return LocalRedirect("/voice");
            case "join":
            {
                var space = line.IndexOf(' ');
                var wanted = (space < 0 ? "" : line[(space + 1)..]).Trim().TrimStart('#').ToLowerInvariant();
                var found = wanted.Length == 0 ? null
                    : Lists.Channels.Concat(Lists.Rooms).FirstOrDefault(c => c.Title.TrimStart('#').ToLowerInvariant() == wanted);
                if (found is null) { TempData["chat.notice"] = text.Format("chan.notice.nochannel", wanted); break; }
                return LocalRedirect(ChannelPath(found.Room));
            }
        }
        return LocalRedirect(Back + "#end");
    }

    public async Task<IActionResult> OnPostDeleteAsync(long id, CancellationToken ct)
    {
        try { await voice.DeleteLineAsync(Me, Room, id, ct); }
        catch (VoiceException e)
        {
            Errors.Add(ErrorKey(e.Code));
            return await ReloadAsync(ct);
        }
        return LocalRedirect(Back + "#end");
    }

    public async Task<IActionResult> OnPostCreateAsync(string? title, CancellationToken ct)
    {
        try
        {
            var room = await voice.CreateRoomAsync(Me, title, ct);
            TempData["flash"] = "voice.flash.created";
            return LocalRedirect($"/voice/rooms/{room.PublicId}");
        }
        catch (VoiceException e)
        {
            Errors.Add(ErrorKey(e.Code));
            Room = null;
            await LoadAsync(join: false, ct);
            return Page();
        }
    }

    /// <summary>The words of a system line, in the reader's language.</summary>
    public string Sys(ChatLine l) => l.Event switch
    {
        "topic" when l.Body.Length == 0 => text.Format("chan.sys.topic_cleared", l.Author.Name),
        "join" or "part" or "topic" or "kick" or "ban" or "unban" or "mute" or "unmute" => text.Format("chan.sys." + l.Event, l.Author.Name, l.Body),
        _ => l.Event + " " + l.Body,
    };
}

/// <summary>
/// A player's line as markup: everything is encoded, and only an http(s) address becomes a link, with rel="nofollow noopener".
/// There is no other route from a player's text to the page.
/// </summary>
public static partial class ChatMarkup
{
    [GeneratedRegex(@"https?://[^\s<>""']+", RegexOptions.IgnoreCase)]
    private static partial Regex UrlRx();

    public static IHtmlContent Render(string body)
    {
        var sb = new System.Text.StringBuilder();
        var at = 0;
        foreach (Match m in UrlRx().Matches(body))
        {
            // the full stop that ends the sentence is not the address's
            var url = m.Value.TrimEnd('.', ',', ';', ':', '!', '?', ')');
            sb.Append(WebUtility.HtmlEncode(body[at..m.Index]));
            sb.Append("<a href=\"").Append(WebUtility.HtmlEncode(url)).Append("\" rel=\"nofollow noopener\" target=\"_blank\">")
              .Append(WebUtility.HtmlEncode(url)).Append("</a>");
            at = m.Index + url.Length;
        }
        sb.Append(WebUtility.HtmlEncode(body[at..]));
        return new HtmlString(sb.ToString());
    }
}
