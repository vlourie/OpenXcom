using System.Security.Cryptography;
using System.Text;
using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.WebUtilities;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;
using Xp.Portal.Auth;
using Xp.Portal.Data;
using Xp.Portal.Devices;
using Xp.Portal.Site;
using Xp.Portal.Tickets;
using Xp.Portal.Voice;

namespace Xp.Portal.Messages;

/// <summary>A refusal with its machine-readable reason (also the key of the text people read: msg.err.&lt;code&gt;).</summary>
public sealed class MessageException(string code, int status) : Exception(code)
{
    public string Code { get; } = code;
    public int Status { get; } = status;
}

public sealed record BubbleView(Guid Id, bool Mine, string Body, DateTimeOffset At, bool Read);
public sealed record DialogueRow(PersonView Person, string Preview, bool LastMine, DateTimeOffset At, int Unread);
public sealed record ThreadView(PersonView Person, IReadOnlyList<BubbleView> Messages, int Total, bool IBlocked, bool Friend);

/// <summary>
/// Private messages (ticket XP-000476): text between registered people. The rules live here and the
/// pages only show them. Blocking is the site's one block (<see cref="UserBlock"/>, the same as for
/// friends and voice), so a person shut out stays shut out everywhere. Staff never browse dialogues:
/// a message reaches them only in a complaint, which carries a copy of the dialogue as it stood.
/// </summary>
public sealed class MessageService(PortalDb db, TimeProvider clock, IOptions<PortalOptions> portal, TicketService tickets,
    Text text, IEmailSender<PortalUser> mail)
{
    static MessageException Fail(string code, int status = 400) => new(code, status);

    // ---------------------------------------------------------------- reading

    /// <summary>Unread messages, for the counter in the header. Messages the person deleted do not count.</summary>
    public Task<int> UnreadAsync(Guid me, CancellationToken ct = default) =>
        db.PrivateMessages.CountAsync(m => m.RecipientId == me && m.ReadAt == null && !m.RecipientDeleted, ct);

    /// <summary>One line per person written to or by, the latest dialogue first.</summary>
    public async Task<IReadOnlyList<DialogueRow>> InboxAsync(Guid me, CancellationToken ct)
    {
        var mine = db.PrivateMessages.Where(m => (m.SenderId == me && !m.SenderDeleted) || (m.RecipientId == me && !m.RecipientDeleted));
        var groups = await mine
            .Select(m => new { Other = m.SenderId == me ? m.RecipientId : m.SenderId, m.CreatedAt, Unread = m.RecipientId == me && m.ReadAt == null })
            .GroupBy(x => x.Other)
            .Select(g => new { Other = g.Key, Last = g.Max(x => x.CreatedAt), Unread = g.Count(x => x.Unread) })
            .OrderByDescending(g => g.Last)
            .Take(MessageLimits.DialoguesMax)
            .ToListAsync(ct);
        if (groups.Count == 0) return [];

        var others = groups.Select(g => g.Other).ToList();
        var times = groups.Select(g => g.Last).ToList();
        var lastRows = await mine
            .Where(m => times.Contains(m.CreatedAt) && (others.Contains(m.SenderId) || others.Contains(m.RecipientId)))
            .Select(m => new { Other = m.SenderId == me ? m.RecipientId : m.SenderId, Mine = m.SenderId == me, m.CreatedAt, m.Body })
            .ToListAsync(ct);
        var names = await NamesAsync(others, ct);
        return groups.Select(g =>
        {
            var last = lastRows.FirstOrDefault(r => r.Other == g.Other && r.CreatedAt == g.Last);
            return new DialogueRow(new PersonView(g.Other, names.GetValueOrDefault(g.Other, "")), Preview(last?.Body), last?.Mine ?? false, g.Last, g.Unread);
        }).ToList();
    }

    static string Preview(string? body)
    {
        var s = (body ?? "").Replace('\n', ' ');
        return s.Length <= 120 ? s : s[..120] + "…";
    }

    /// <summary>
    /// A dialogue with one person, newest page first (page 1 is the end of the conversation), each page in
    /// reading order. Opening it marks what the other wrote as read.
    /// </summary>
    public async Task<ThreadView> ThreadAsync(Guid me, Guid other, int page, CancellationToken ct, bool markRead = true)
    {
        var person = await PersonAsync(other, ct);
        var q = Dialogue(me, other);
        var total = await q.CountAsync(ct);
        var rows = await q.OrderByDescending(m => m.CreatedAt).Skip(Math.Max(0, page - 1) * MessageLimits.PerPage)
            .Take(MessageLimits.PerPage).ToListAsync(ct);
        rows.Reverse();
        if (markRead) await MarkReadAsync(me, other, ct);
        var blocked = await db.UserBlocks.AnyAsync(x => x.BlockerId == me && x.BlockedId == other, ct);
        var (lo, hi) = Friendship.Pair(me, other);
        var friend = await db.Friendships.AnyAsync(f => f.UserLowId == lo && f.UserHighId == hi, ct);
        return new ThreadView(person,
            rows.Select(m => new BubbleView(m.Id, m.SenderId == me, m.Body, m.CreatedAt, m.ReadAt != null)).ToList(), total, blocked, friend);
    }

    /// <summary>What the other wrote to this person is read. The launcher says so itself, once the dialogue is in view.</summary>
    public async Task MarkReadAsync(Guid me, Guid other, CancellationToken ct)
    {
        var now = clock.GetUtcNow();
        await db.PrivateMessages.Where(m => m.SenderId == other && m.RecipientId == me && m.ReadAt == null)
            .ExecuteUpdateAsync(s => s.SetProperty(m => m.ReadAt, now), ct);
    }

    /// <summary>The messages of a pair that this person has not deleted for themselves.</summary>
    IQueryable<PrivateMessage> Dialogue(Guid me, Guid other) =>
        db.PrivateMessages.Where(m => (m.SenderId == me && m.RecipientId == other && !m.SenderDeleted)
            || (m.SenderId == other && m.RecipientId == me && !m.RecipientDeleted));

    // ---------------------------------------------------------------- people

    public async Task<PersonView> PersonAsync(Guid id, CancellationToken ct)
    {
        var u = await db.Users.AsNoTracking().FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw Fail("user_not_found", 404);
        return new PersonView(u.Id, DeviceApi.Display(u));
    }

    async Task<Dictionary<Guid, string>> NamesAsync(IEnumerable<Guid> ids, CancellationToken ct)
    {
        var set = ids.Distinct().ToList();
        var users = await db.Users.AsNoTracking().Where(u => set.Contains(u.Id)).ToListAsync(ct);
        return users.ToDictionary(u => u.Id, DeviceApi.Display);
    }

    // ---------------------------------------------------------------- sending

    public async Task<PrivateMessage> SendAsync(Guid me, Guid to, string? body, CancellationToken ct)
    {
        if (to == me) throw Fail("self");
        var raw = (body ?? "").Trim();
        if (raw.Length > MessageLimits.BodyMax) throw Fail("too_long");
        // control characters and invisible direction marks go; line breaks stay
        var clean = TicketService.Clean(raw, MessageLimits.BodyMax) ?? throw Fail("empty");
        var recipient = await db.Users.AsNoTracking().FirstOrDefaultAsync(u => u.Id == to, ct) ?? throw Fail("user_not_found", 404);

        if (await db.UserBlocks.AnyAsync(x => x.BlockerId == me && x.BlockedId == to, ct)) throw Fail("you_blocked", 409);
        // blocked by them reads as a refusal, not as a block: the one who was shut out is not told so
        if (await db.UserBlocks.AnyAsync(x => x.BlockerId == to && x.BlockedId == me, ct)) throw Fail("refused", 403);

        var now = clock.GetUtcNow();
        if (await db.PrivateMessages.CountAsync(m => m.SenderId == me && m.CreatedAt > now.AddMinutes(-10), ct) >= MessageLimits.PerTenMinutes
            || await db.PrivateMessages.CountAsync(m => m.SenderId == me && m.CreatedAt > now.AddDays(-1), ct) >= MessageLimits.PerDay)
            throw Fail("limit_rate", 429);

        var (lo, hi) = Friendship.Pair(me, to);
        var friend = await db.Friendships.AnyAsync(f => f.UserLowId == lo && f.UserHighId == hi, ct);
        var theirLast = await db.PrivateMessages.Where(m => m.SenderId == to && m.RecipientId == me)
            .MaxAsync(m => (DateTimeOffset?)m.CreatedAt, ct);
        // somebody who wrote back, or a friend, is talked to; a stranger who has not answered gets a few messages and then silence
        var talked = friend || theirLast is not null;
        var since = theirLast ?? DateTimeOffset.UnixEpoch;
        var unanswered = await db.PrivateMessages.CountAsync(m => m.SenderId == me && m.RecipientId == to && m.CreatedAt > since, ct);
        if (unanswered >= (talked ? MessageLimits.UnansweredFriend : MessageLimits.UnansweredStranger)) throw Fail("limit_unanswered", 429);
        if (!talked)
        {
            var cold = await StrangersTodayAsync(me, now, ct);
            if (!cold.Contains(to) && cold.Count >= MessageLimits.StrangersPerDay) throw Fail("limit_strangers", 429);
        }

        // one letter for a run of messages, not one per message: it goes out when nothing waited unread before this one
        var hadUnread = await db.PrivateMessages.AnyAsync(m => m.RecipientId == to && m.ReadAt == null && !m.RecipientDeleted, ct);
        var message = new PrivateMessage { SenderId = me, RecipientId = to, Body = clean, CreatedAt = now };
        db.PrivateMessages.Add(message);
        await db.SaveChangesAsync(ct);

        if (!hadUnread && recipient.Email is { Length: > 0 } address && recipient.EmailConfirmed
            && await db.MessageSettings.AnyAsync(s => s.UserId == to && s.EmailNotice, ct)
            && mail is EmailSender sender)
        {
            var from = DeviceApi.Display((await db.Users.AsNoTracking().FirstAsync(u => u.Id == me, ct)));
            var site = portal.Value.PublicUrl.TrimEnd('/');
            await sender.SendMessageNoticeAsync(address, from, $"{site}/me/messages/{me}", $"{site}{UnsubscribePath(to)}");
        }
        return message;
    }

    /// <summary>People written to in the last day who are neither friends nor ever wrote back.</summary>
    async Task<HashSet<Guid>> StrangersTodayAsync(Guid me, DateTimeOffset now, CancellationToken ct)
    {
        var recent = await db.PrivateMessages.Where(m => m.SenderId == me && m.CreatedAt > now.AddDays(-1))
            .Select(m => m.RecipientId).Distinct().ToListAsync(ct);
        if (recent.Count == 0) return [];
        var replied = await db.PrivateMessages.Where(m => m.RecipientId == me && recent.Contains(m.SenderId))
            .Select(m => m.SenderId).Distinct().ToListAsync(ct);
        var friends = await db.Friendships
            .Where(f => (f.UserLowId == me && recent.Contains(f.UserHighId)) || (f.UserHighId == me && recent.Contains(f.UserLowId)))
            .Select(f => f.UserLowId == me ? f.UserHighId : f.UserLowId).ToListAsync(ct);
        return recent.Except(replied).Except(friends).ToHashSet();
    }

    // ---------------------------------------------------------------- deleting

    /// <summary>Deletes a message for this person only; the other keeps theirs. The row goes when both have.</summary>
    public async Task DeleteAsync(Guid me, Guid id, CancellationToken ct)
    {
        var m = await db.PrivateMessages.FirstOrDefaultAsync(x => x.Id == id && (x.SenderId == me || x.RecipientId == me), ct)
            ?? throw Fail("message_not_found", 404);
        if (m.SenderId == me) m.SenderDeleted = true; else m.RecipientDeleted = true;
        if (m.SenderDeleted && m.RecipientDeleted) db.PrivateMessages.Remove(m);
        await db.SaveChangesAsync(ct);
    }

    // ---------------------------------------------------------------- complaints

    /// <summary>
    /// A complaint about somebody's messages becomes a ticket of category voice, the one staff already
    /// read complaints from. It carries the person's own words and a copy of the newest messages of the
    /// dialogue (and of the one complained about, if it is older): that copy is all staff ever see.
    /// </summary>
    public async Task<Ticket> ComplainAsync(Guid me, Guid about, Guid? messageId, string? comment, CancellationToken ct)
    {
        if (about == me) throw Fail("self");
        var note = (comment ?? "").Trim();
        if (note.Length is 0 or > MessageLimits.ComplaintMax) throw Fail("complaint_invalid");
        var who = await PersonAsync(about, ct);
        var reporter = await PersonAsync(me, ct);

        var visible = Dialogue(me, about);
        // there must be something of theirs to complain about, and the one complained about must be theirs and in view
        if (!await visible.AnyAsync(m => m.SenderId == about, ct)) throw Fail("no_dialogue", 404);
        PrivateMessage? pointed = null;
        if (messageId is { } mid)
            pointed = await visible.FirstOrDefaultAsync(m => m.Id == mid && m.SenderId == about, ct) ?? throw Fail("message_not_found", 404);

        var now = clock.GetUtcNow();
        if (await db.Tickets.CountAsync(t => t.AuthorId == me && t.Source == TicketSource.Voice && t.CreatedAt > now.AddDays(-1), ct) >= MessageLimits.ComplaintsPerDay)
            throw Fail("limit_complaints", 429);

        var newest = await visible.OrderByDescending(m => m.CreatedAt).Take(MessageLimits.ComplaintContextMessages).ToListAsync(ct);
        var lines = new List<string>();
        var shown = new HashSet<Guid>();
        var spent = 0;
        foreach (var m in newest)
        {
            var line = Line(m, me, who, reporter, m.Id == pointed?.Id);
            if (spent + line.Length > MessageLimits.ComplaintContextChars && lines.Count > 0) break;
            lines.Add(line);
            shown.Add(m.Id);
            spent += line.Length;
        }
        lines.Reverse();
        var copy = new StringBuilder();
        // the message complained about is older than the copy reaches: it goes first, on its own
        if (pointed is not null && !shown.Contains(pointed.Id))
            copy.Append(text["msg.complaint.pointed"]).Append('\n').Append(Line(pointed, me, who, reporter, true)).Append("\n\n");
        copy.Append(text["msg.complaint.dialogue"]).Append('\n').Append(string.Join("\n", lines));

        var title = text.Format("msg.complaint.title", who.Name);
        var description = $"{note}\n\n---\n{text["voice.complaint.about"]}: {who.Name} ({who.Id})\n{text["voice.complaint.from"]}: {reporter.Name} ({reporter.Id})\n\n{copy}";
        var created = await tickets.CreateAsync(new NewTicket(Categories.Voice, title.Length > Limits.TitleMax ? title[..Limits.TitleMax] : title, description,
            Source: TicketSource.Voice, Language: Text.Lang), me, null, null, ct);
        return created.Ticket;
    }

    static string Line(PrivateMessage m, Guid me, PersonView other, PersonView reporter, bool pointed) =>
        $"{(pointed ? "► " : "")}[{m.CreatedAt:yyyy-MM-dd HH:mm}] {(m.SenderId == me ? reporter.Name : other.Name)}: {m.Body}";

    // ---------------------------------------------------------------- e-mail about new messages

    public async Task<bool> EmailNoticeAsync(Guid me, CancellationToken ct) =>
        await db.MessageSettings.AnyAsync(s => s.UserId == me && s.EmailNotice, ct);

    public async Task SetEmailNoticeAsync(Guid me, bool on, CancellationToken ct)
    {
        var s = await db.MessageSettings.FirstOrDefaultAsync(x => x.UserId == me, ct);
        if (s is null) db.MessageSettings.Add(new MessageSetting { UserId = me, EmailNotice = on, UpdatedAt = clock.GetUtcNow() });
        else { s.EmailNotice = on; s.UpdatedAt = clock.GetUtcNow(); }
        await db.SaveChangesAsync(ct);
    }

    /// <summary>The link in the letter: it works without signing in, and only turns the letters off for the one it names.</summary>
    public string UnsubscribePath(Guid user) => $"/account/unsubscribe?u={user}&sig={Sign(user)}";

    string Sign(Guid user) =>
        WebEncoders.Base64UrlEncode(HMACSHA256.HashData(portal.Value.SecretBytes(), Encoding.UTF8.GetBytes($"pm-unsubscribe:{user}")));

    /// <summary>True when the link was genuine; the letters are off for that person afterwards.</summary>
    public async Task<bool> UnsubscribeAsync(Guid user, string? sig, CancellationToken ct)
    {
        if (sig is null || !CryptographicOperations.FixedTimeEquals(Encoding.ASCII.GetBytes(Sign(user)), Encoding.ASCII.GetBytes(sig))) return false;
        // no row to write for somebody who never turned them on, and none to create for an id that is no user
        if (await db.MessageSettings.AnyAsync(s => s.UserId == user, ct)) await SetEmailNoticeAsync(user, false, ct);
        return true;
    }
}
