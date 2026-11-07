using System.Text;
using System.Text.RegularExpressions;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Caching.Memory;
using Xp.Portal.Auth;
using Xp.Portal.Data;
using Xp.Portal.Messages;
using Xp.Portal.Tickets;

namespace Xp.Portal.Voice;

/// <summary>
/// One line of a feed as a reader gets it. For a system line <see cref="Event"/> names what happened (join, part, topic,
/// kick, ban, unban, mute, unmute) and <see cref="Body"/> is its argument (the topic, or the name of the person acted on).
/// <see cref="Mention"/> is decided on the server for the reader: their nick is in the text.
/// </summary>
public sealed record ChatLine(long Id, string Kind, string? Event, PersonView Author, string Body, DateTimeOffset At, bool Mine, bool Mention);
/// <summary>Somebody in the channel: Operator is the owner or staff, Voice is in the voice room now, Muted may not talk there.</summary>
public sealed record Attendee(PersonView Person, bool Operator, bool Voice, bool Muted);
/// <summary>New lines after a cursor, who is here, and the facts the page above the feed needs. Last is the next cursor.</summary>
public sealed record MessagesView(string Room, string Title, string? Topic, bool IsPublic, bool CanModerate, bool CanTalk, long Last,
    IReadOnlyList<ChatLine> Lines, IReadOnlyList<long> Removed, IReadOnlyList<Attendee> Attendees);
/// <summary>A channel or room in the list on the left. Unread and Mentions count only for a channel the person has joined.</summary>
public sealed record ChannelRow(string Room, string Title, string? Topic, bool IsPublic, bool Mine, PersonView Owner, string State, bool Joined,
    int Here, int Unread, int Mentions, long LastId);
public sealed record ChannelsView(IReadOnlyList<ChannelRow> Channels, IReadOnlyList<ChannelRow> Rooms);
/// <summary>
/// What a sent line came to. Result: posted (Line), done (a command of the moderators ran), private (/msg went to Person),
/// topic (/topic without text: Text is the current one), client (/join /part /who /help are the client's own: nothing happened here),
/// unknown (no such command: the client shows the hint, nothing was sent).
/// </summary>
public sealed record PostResult(string Result, ChatLine? Line, string? Command, PersonView? Person, string? Text);

/// <summary>Text feed of rooms and public channels (docs/portal/VOICE_IRC.md). The rules of who may read, write and moderate are here, like all the others.</summary>
public sealed partial class VoiceService
{
    static readonly TimeSpan SeenEvery = TimeSpan.FromSeconds(30);
    static readonly TimeSpan LiveCache = TimeSpan.FromSeconds(5);
    static readonly TimeSpan LiveWait = TimeSpan.FromSeconds(2);

    // ---------------------------------------------------------------- who is who

    /// <summary>Admin and SuperAdmin: the people who keep the public channels in order.</summary>
    public async Task<bool> IsStaffAsync(Guid user, CancellationToken ct) =>
        await (from ur in db.UserRoles join r in db.Roles on ur.RoleId equals r.Id
               where ur.UserId == user && (r.Name == Roles.Admin || r.Name == Roles.SuperAdmin) select ur.UserId).AnyAsync(ct);

    async Task<bool> CanModerateAsync(Guid me, VoiceRoom room, CancellationToken ct) =>
        room.OwnerId == me || (room.IsPublic && await IsStaffAsync(me, ct));

    /// <summary>
    /// The room to moderate: the owner's, and in a public channel (whose owner is the site itself) staff's. Everybody else
    /// is told it is not theirs to do, or gets the plain "no access" of a room they are not in.
    /// </summary>
    async Task<VoiceRoom> ModeratedAsync(Guid me, string? publicId, CancellationToken ct)
    {
        var room = await RoomAsync(publicId, ct) ?? throw NoAccess();
        if (room.OwnerId == me) return room;
        if (!room.IsPublic) return await OwnedAsync(me, publicId, ct);
        if (await IsStaffAsync(me, ct)) return room;
        throw Fail("moderator_only", 403);
    }

    /// <summary>The room the person may read and write in, or the refusal that says why not.</summary>
    async Task<(VoiceRoom Room, bool CanPublish)> ChatRoomAsync(Guid me, string? publicId, CancellationToken ct)
    {
        var room = await RoomAsync(publicId, ct);
        var (access, canPublish) = await AccessAsync(me, room, ct);
        if (access == RoomAccess.NoAccess) throw NoAccess();
        if (access != RoomAccess.Ok) throw Fail(StateCode(access), 403);
        return (room!, canPublish);
    }

    // ---------------------------------------------------------------- the lists

    /// <summary>Public channels, my rooms and what is new in each: one answer for the whole list on the left.</summary>
    public async Task<ChannelsView> ChannelsAsync(Guid me, CancellationToken ct)
    {
        var now = clock.GetUtcNow();
        var publics = await db.VoiceRooms.AsNoTracking().Where(r => r.IsPublic && r.Status == VoiceRoomStatus.Open)
            .OrderBy(r => r.CreatedAt).ThenBy(r => r.Title).ToListAsync(ct);
        var (owned, invited) = await RoomsAsync(me, ct);
        var mine = owned.Concat(invited).Where(r => r.Status == "open" || r.Mine).ToList();
        var ids = new List<Guid>();
        var rows = new List<(VoiceRoom? Pub, RoomSummary? Sum)>();
        foreach (var p in publics) rows.Add((p, null));
        foreach (var s in mine) rows.Add((null, s));

        var codes = mine.Select(s => s.PublicId).ToList();
        var privateRooms = await db.VoiceRooms.AsNoTracking().Where(r => codes.Contains(r.PublicId)).ToDictionaryAsync(r => r.PublicId, ct);
        ids.AddRange(publics.Select(p => p.Id));
        ids.AddRange(privateRooms.Values.Select(r => r.Id));

        var states = await db.RoomChannelStates.AsNoTracking().Where(s => s.UserId == me && ids.Contains(s.RoomId)).ToDictionaryAsync(s => s.RoomId, ct);
        var last = await db.RoomMessages.AsNoTracking().Where(m => ids.Contains(m.RoomId)).GroupBy(m => m.RoomId)
            .Select(g => new { Room = g.Key, Last = g.Max(m => m.Id) }).ToDictionaryAsync(x => x.Room, x => x.Last, ct);
        var hereFrom = now - VoiceLimits.HereWindow;
        var here = await db.RoomChannelStates.AsNoTracking().Where(s => s.Joined && s.SeenAt >= hereFrom && ids.Contains(s.RoomId))
            .GroupBy(s => s.RoomId).Select(g => new { Room = g.Key, N = g.Count() }).ToDictionaryAsync(x => x.Room, x => x.N, ct);

        // new lines in the channels the person is in: others', not removed, not from somebody they blocked, no service lines
        var unseen = from m in db.RoomMessages.AsNoTracking()
                     join s in db.RoomChannelStates on m.RoomId equals s.RoomId
                     where s.UserId == me && s.Joined && ids.Contains(m.RoomId) && m.Id > s.LastReadId && m.AuthorId != me
                           && m.DeletedAt == null && m.Kind != ChatKinds.System
                           && !db.UserBlocks.Any(x => x.BlockerId == me && x.BlockedId == m.AuthorId)
                     select m;
        var unread = await unseen.GroupBy(m => m.RoomId).Select(g => new { Room = g.Key, N = g.Count() }).ToDictionaryAsync(x => x.Room, x => x.N, ct);
        var mentions = new Dictionary<Guid, int>();
        if (unread.Count > 0)
        {
            var name = (await PersonAsync(me, ct)).Name;
            var candidates = await unseen.Where(m => EF.Functions.ILike(EF.Functions.Collate(m.Body, Site.Search.Collation), LikeContains(name)))
                .OrderByDescending(m => m.Id).Take(1000).Select(m => new { m.RoomId, m.Body }).ToListAsync(ct);
            foreach (var c in candidates.Where(c => Mentions(c.Body, name)))
                mentions[c.RoomId] = mentions.GetValueOrDefault(c.RoomId) + 1;
        }

        ChannelRow Row(VoiceRoom r, bool isMine, PersonView owner, string state)
        {
            states.TryGetValue(r.Id, out var st);
            return new ChannelRow(r.PublicId, r.Title, r.Topic, r.IsPublic, isMine, owner, state, st?.Joined ?? false,
                here.GetValueOrDefault(r.Id), unread.GetValueOrDefault(r.Id), mentions.GetValueOrDefault(r.Id), last.GetValueOrDefault(r.Id));
        }

        var ownerNames = await NamesAsync(publics.Select(p => p.OwnerId), ct);
        var channels = new List<ChannelRow>();
        foreach (var p in publics)
        {
            var (access, _) = await AccessAsync(me, p, ct);
            channels.Add(Row(p, false, new PersonView(p.OwnerId, ownerNames.GetValueOrDefault(p.OwnerId, "")), StateCode(access)));
        }
        var roomRows = mine.Where(s => privateRooms.TryGetValue(s.PublicId, out var pr) && !pr.IsPublic)
            .Select(s => Row(privateRooms[s.PublicId], s.Mine, s.Owner, s.State)).ToList();
        return new ChannelsView(channels, roomRows);
    }

    static string LikeContains(string s) => "%" + s.Replace("\\", "\\\\").Replace("%", "\\%").Replace("_", "\\_") + "%";

    /// <summary>The nick as a word of its own in the line, with or without an @ before it, in any case.</summary>
    public static bool Mentions(string body, string nick)
    {
        nick = nick.Trim();
        if (nick.Length == 0) return false;
        return Regex.IsMatch(body, @"(?<![\p{L}\p{N}_])@?" + Regex.Escape(nick) + @"(?![\p{L}\p{N}_])",
            RegexOptions.IgnoreCase | RegexOptions.CultureInvariant, TimeSpan.FromMilliseconds(200));
    }

    // ---------------------------------------------------------------- reading a feed

    /// <summary>
    /// New lines after a cursor (or the newest ones when none is given), at most <paramref name="limit"/>, and who is here.
    /// Looking is also marking as read. Lines of people the reader blocked are not handed over; the cursor passes them.
    /// </summary>
    public async Task<MessagesView> MessagesAsync(Guid me, string? publicId, long? after, int? limit, CancellationToken ct)
    {
        var (room, canPublish) = await ChatRoomAsync(me, publicId, ct);
        var take = Math.Clamp(limit ?? VoiceLimits.HistoryDefault, 1, VoiceLimits.HistoryMax);
        var now = clock.GetUtcNow();
        var feed = db.RoomMessages.AsNoTracking().Where(m => m.RoomId == room.Id);
        List<RoomMessage> rows;
        if (after is { } cursor)
            rows = await feed.Where(m => m.Id > cursor).OrderBy(m => m.Id).Take(take).ToListAsync(ct);
        else
        {
            rows = await feed.OrderByDescending(m => m.Id).Take(take).ToListAsync(ct);
            rows.Reverse();
        }
        var next = rows.Count > 0 ? rows[^1].Id : after ?? 0;

        var authors = rows.Select(m => m.AuthorId).Distinct().ToList();
        var blocked = await db.UserBlocks.AsNoTracking().Where(x => x.BlockerId == me && authors.Contains(x.BlockedId)).Select(x => x.BlockedId).ToListAsync(ct);
        var names = await NamesAsync(authors, ct);
        var myName = (await PersonAsync(me, ct)).Name;
        var lines = rows.Where(m => m.DeletedAt == null && !blocked.Contains(m.AuthorId))
            .Select(m => Line(m, names, me, myName)).ToList();

        IReadOnlyList<long> removed = [];
        if (after is not null)
        {
            var from = now - VoiceLimits.RemovedNotice;
            removed = await db.RoomMessages.AsNoTracking().Where(m => m.RoomId == room.Id && m.DeletedAt != null && m.DeletedAt >= from)
                .OrderByDescending(m => m.Id).Take(100).Select(m => m.Id).ToListAsync(ct);
        }

        // reading is being here, and what was handed over is read; one write in half a minute unless there is something new
        await db.RoomChannelStates.Where(x => x.RoomId == room.Id && x.UserId == me && (x.SeenAt < now - SeenEvery || x.LastReadId < next))
            .ExecuteUpdateAsync(s => s.SetProperty(x => x.SeenAt, now).SetProperty(x => x.LastReadId, x => x.LastReadId > next ? x.LastReadId : next), ct);

        return new MessagesView(room.PublicId, room.Title, room.Topic, room.IsPublic, await CanModerateAsync(me, room, ct), canPublish, next,
            lines, removed, await AttendeesAsync(room, now, ct));
    }

    static ChatLine Line(RoomMessage m, IReadOnlyDictionary<Guid, string> names, Guid me, string myName)
    {
        var author = new PersonView(m.AuthorId, names.GetValueOrDefault(m.AuthorId, ""));
        if (m.Kind == ChatKinds.System)
        {
            var space = m.Body.IndexOf(' ');
            return new ChatLine(m.Id, m.Kind, space < 0 ? m.Body : m.Body[..space], author, space < 0 ? "" : m.Body[(space + 1)..], m.CreatedAt, m.AuthorId == me, false);
        }
        return new ChatLine(m.Id, m.Kind, null, author, m.Body, m.CreatedAt, m.AuthorId == me, m.AuthorId != me && Mentions(m.Body, myName));
    }

    /// <summary>Who has looked at the channel in the last minute and a half, and who is in its voice room. The owner and staff come first.</summary>
    async Task<IReadOnlyList<Attendee>> AttendeesAsync(VoiceRoom room, DateTimeOffset now, CancellationToken ct)
    {
        var from = now - VoiceLimits.HereWindow;
        var here = await db.RoomChannelStates.AsNoTracking().Where(s => s.RoomId == room.Id && s.Joined && s.SeenAt >= from)
            .Select(s => s.UserId).ToListAsync(ct);
        var speaking = await LiveIdsAsync(room, ct);
        var ids = here.Concat(speaking).Distinct().ToList();
        if (ids.Count == 0) return [];
        var names = await NamesAsync(ids, ct);
        var staff = await (from ur in db.UserRoles join r in db.Roles on ur.RoleId equals r.Id
                           where ids.Contains(ur.UserId) && (r.Name == Roles.Admin || r.Name == Roles.SuperAdmin) select ur.UserId).Distinct().ToListAsync(ct);
        var muted = await db.RoomSpeakingRestrictions.AsNoTracking().Where(x => x.RoomId == room.Id && x.Restricted && ids.Contains(x.UserId))
            .Select(x => x.UserId).ToListAsync(ct);
        return ids.Where(names.ContainsKey)
            .Select(id => new Attendee(new PersonView(id, names[id]), id == room.OwnerId && !room.IsPublic || staff.Contains(id), speaking.Contains(id), muted.Contains(id)))
            .OrderByDescending(a => a.Operator).ThenBy(a => a.Person.Name, StringComparer.CurrentCultureIgnoreCase).ToList();
    }

    /// <summary>Who is in the voice room: asked of the media server briefly and remembered for a few seconds, so a busy channel does not hammer it.</summary>
    async Task<HashSet<Guid>> LiveIdsAsync(VoiceRoom room, CancellationToken ct)
    {
        if (!server.Enabled) return [];
        if (cache.TryGetValue<HashSet<Guid>>("voice-live:" + room.Id, out var known) && known is not null) return known;
        var ids = new HashSet<Guid>();
        try
        {
            using var wait = CancellationTokenSource.CreateLinkedTokenSource(ct);
            wait.CancelAfter(LiveWait);
            foreach (var p in await server.ParticipantsAsync(room.Id, wait.Token))
                if (Guid.TryParse(p.Identity, out var id)) ids.Add(id);
        }
        catch (VoiceServerException) { }
        catch (OperationCanceledException) when (!ct.IsCancellationRequested) { }
        cache.Set("voice-live:" + room.Id, ids, LiveCache);
        return ids;
    }

    // ---------------------------------------------------------------- being in a channel

    /// <summary>Comes into the channel: it shows in the list of who is here and a "joined" line is written once.</summary>
    public async Task JoinAsync(Guid me, string? publicId, CancellationToken ct)
    {
        var (room, _) = await ChatRoomAsync(me, publicId, ct);
        await SetJoinedAsync(room, me, joined: true, ct);
    }

    public async Task PartAsync(Guid me, string? publicId, CancellationToken ct)
    {
        var (room, _) = await ChatRoomAsync(me, publicId, ct);
        await SetJoinedAsync(room, me, joined: false, ct);
    }

    async Task SetJoinedAsync(VoiceRoom room, Guid me, bool joined, CancellationToken ct)
    {
        await using var tx = await LockAsync("chat", me, null, ct);
        var now = clock.GetUtcNow();
        var st = await db.RoomChannelStates.FirstOrDefaultAsync(x => x.RoomId == room.Id && x.UserId == me, ct);
        if (st is null)
        {
            // what happened before the person came is not unread for them
            var newest = await db.RoomMessages.Where(m => m.RoomId == room.Id).MaxAsync(m => (long?)m.Id, ct) ?? 0;
            db.RoomChannelStates.Add(st = new RoomChannelState { RoomId = room.Id, UserId = me, LastReadId = newest, SeenAt = now });
        }
        st.SeenAt = now;
        if (st.Joined != joined)
        {
            st.Joined = joined;
            await AddSystemAsync(room.Id, me, joined ? "join" : "part", null, now, ct);
        }
        await db.SaveChangesAsync(ct);
        await tx.CommitAsync(ct);
    }

    /// <summary>
    /// A service line. Joining and leaving are cheap to repeat, so a person who has already written their quota this minute
    /// simply gets no line for it; the actions of moderators are always written.
    /// </summary>
    async Task AddSystemAsync(Guid room, Guid actor, string ev, string? argument, DateTimeOffset now, CancellationToken ct)
    {
        if (ev is "join" or "part" && await LinesInLastMinuteAsync(actor, now, wordsOnly: false, ct) >= VoiceLimits.LinesPerMinute) return;
        var body = argument is { Length: > 0 } ? ev + " " + argument : ev;
        db.RoomMessages.Add(new RoomMessage { RoomId = room, AuthorId = actor, Kind = ChatKinds.System, Body = body.Length > VoiceLimits.LineMax ? body[..VoiceLimits.LineMax] : body, CreatedAt = now });
    }

    /// <summary>What the person wrote in the last minute, in every room. Service lines count only against their own kind of limit: a "joined" line is not the person's words.</summary>
    Task<int> LinesInLastMinuteAsync(Guid author, DateTimeOffset now, bool wordsOnly, CancellationToken ct) =>
        db.RoomMessages.CountAsync(m => m.AuthorId == author && m.CreatedAt > now - TimeSpan.FromMinutes(1) && (!wordsOnly || m.Kind != ChatKinds.System), ct);

    // ---------------------------------------------------------------- writing

    /// <summary>
    /// A line or a command from the input box. Anything that starts with a slash is a command and is never sent as text:
    /// an unknown one comes back as "unknown" for the client to answer with its hint.
    /// </summary>
    public async Task<PostResult> PostAsync(Guid me, string? publicId, string? text, CancellationToken ct)
    {
        var (room, _) = await ChatRoomAsync(me, publicId, ct);
        if (text is { Length: > 10_000 }) throw Fail("too_long");
        var line = TicketService.Clean(text, int.MaxValue, singleLine: true) ?? throw Fail("empty");
        if (line.Length > VoiceLimits.LineMax) throw Fail("too_long");
        if (line[0] != '/') return await SayAsync(me, room, ChatKinds.Text, line, ct);

        var space = line.IndexOf(' ');
        var command = (space < 0 ? line[1..] : line[1..space]).ToLowerInvariant();
        var rest = space < 0 ? "" : line[(space + 1)..].Trim();
        switch (command)
        {
            case "me":
                if (rest.Length == 0) throw Fail("empty");
                return await SayAsync(me, room, ChatKinds.Action, rest, ct);
            case "topic":
                if (rest.Length == 0) return new PostResult("topic", null, "topic", null, room.Topic);
                await SetTopicAsync(me, room.PublicId, rest == "-" ? "" : rest, ct);
                return new PostResult("done", null, "topic", null, null);
            case "msg":
            {
                var (nick, body) = SplitFirst(rest);
                if (nick.Length == 0 || body.Length == 0) throw Fail("empty");
                var to = await FindPersonAsync(nick.TrimStart('@'), ct);
                try { await messages.SendAsync(me, to, body, ct); }
                catch (MessageException e) { throw Fail("msg_" + e.Code, e.Status); }
                return new PostResult("private", null, "msg", await PersonAsync(to, ct), null);
            }
            case "kick" or "ban" or "unban" or "mute" or "unmute":
            {
                var (nick, reason) = SplitFirst(rest);
                if (nick.Length == 0) throw Fail("empty");
                var who = await ResolveInRoomAsync(room, nick.TrimStart('@'), ct);
                var why = reason.Length > 0 ? reason : null;
                switch (command)
                {
                    case "kick": await KickAsync(me, room.PublicId, who, why, ct); break;
                    case "ban": await BanAsync(me, room.PublicId, who, why, ct); break;
                    case "unban": await UnbanAsync(me, room.PublicId, who, ct); break;
                    case "mute": await SetSpeakingAsync(me, room.PublicId, who, allowed: false, why, ct); break;
                    default: await SetSpeakingAsync(me, room.PublicId, who, allowed: true, why, ct); break;
                }
                return new PostResult("done", null, command, await PersonAsync(who, ct), null);
            }
            case "join" or "part" or "who" or "help":
                return new PostResult("client", null, command, null, null);
            default:
                return new PostResult("unknown", null, "/" + command, null, null);
        }
    }

    static (string First, string Tail) SplitFirst(string s)
    {
        var i = s.IndexOf(' ');
        return i < 0 ? (s, "") : (s[..i], s[(i + 1)..].Trim());
    }

    async Task<PostResult> SayAsync(Guid me, VoiceRoom room, string kind, string body, CancellationToken ct)
    {
        await using var tx = await LockAsync("chat", me, null, ct);
        var now = clock.GetUtcNow();
        if (await LinesInLastMinuteAsync(me, now, wordsOnly: true, ct) >= VoiceLimits.LinesPerMinute) throw Fail("limit_rate", 429);
        var st = await db.RoomChannelStates.FirstOrDefaultAsync(x => x.RoomId == room.Id && x.UserId == me, ct);
        if (st is null)
        {
            var newest = await db.RoomMessages.Where(m => m.RoomId == room.Id).MaxAsync(m => (long?)m.Id, ct) ?? 0;
            db.RoomChannelStates.Add(st = new RoomChannelState { RoomId = room.Id, UserId = me, LastReadId = newest });
        }
        // writing is coming in
        if (!st.Joined) { st.Joined = true; await AddSystemAsync(room.Id, me, "join", null, now, ct); }
        st.SeenAt = now;
        var row = new RoomMessage { RoomId = room.Id, AuthorId = me, Kind = kind, Body = body, CreatedAt = now };
        db.RoomMessages.Add(row);
        await db.SaveChangesAsync(ct);
        // the person's own line is not new to them
        st.LastReadId = row.Id;
        await db.SaveChangesAsync(ct);
        await tx.CommitAsync(ct);
        var name = (await PersonAsync(me, ct)).Name;
        return new PostResult("posted", new ChatLine(row.Id, kind, null, new PersonView(me, name), body, now, true, false), null, null, null);
    }

    /// <summary>The person of that name among those the channel knows: the owner, the invited, the banned, whoever came in or wrote.</summary>
    async Task<Guid> ResolveInRoomAsync(VoiceRoom room, string nick, CancellationToken ct)
    {
        var lower = nick.ToLowerInvariant();
        var named = await db.Users.AsNoTracking().Where(u => u.DisplayName.ToLower() == lower).Select(u => u.Id).Take(20).ToListAsync(ct);
        var known = new List<Guid>();
        foreach (var id in named)
            if (id == room.OwnerId
                || await db.RoomChannelStates.AnyAsync(s => s.RoomId == room.Id && s.UserId == id, ct)
                || await db.RoomInvites.AnyAsync(i => i.RoomId == room.Id && i.UserId == id, ct)
                || await db.RoomBans.AnyAsync(b => b.RoomId == room.Id && b.UserId == id, ct)
                || await db.RoomMessages.AnyAsync(m => m.RoomId == room.Id && m.AuthorId == id, ct))
                known.Add(id);
        return known.Count switch
        {
            0 => throw Fail("user_not_found", 404),
            1 => known[0],
            _ => throw Fail("name_ambiguous", 409),
        };
    }

    /// <summary>The topic over the feed. Empty clears it. Written to the log of actions like every act of a moderator.</summary>
    public async Task SetTopicAsync(Guid me, string? publicId, string? topic, CancellationToken ct)
    {
        var room = await ModeratedAsync(me, publicId, ct);
        var clean = TicketService.Clean(topic, int.MaxValue, singleLine: true) ?? "";
        if (clean.Length > VoiceLimits.TopicMax) throw Fail("topic_too_long");
        await using var tx = await LockAsync("room", room.Id, null, ct);
        var now = clock.GetUtcNow();
        room.Topic = clean.Length == 0 ? null : clean;
        await AddSystemAsync(room.Id, me, "topic", clean, now, ct);
        db.VoiceEvents.Add(new VoiceEvent { RoomId = room.Id, UserId = me, ActorId = me, Kind = VoiceEventKinds.Topic, Reason = clean.Length == 0 ? null : clean, At = now });
        await db.SaveChangesAsync(ct);
        await tx.CommitAsync(ct);
    }

    /// <summary>Takes a line out of the feed: its author may, and so may the owner of the room or, in a public channel, staff. A service line stays.</summary>
    public async Task DeleteLineAsync(Guid me, string? publicId, long id, CancellationToken ct)
    {
        var (room, _) = await ChatRoomAsync(me, publicId, ct);
        var line = await db.RoomMessages.FirstOrDefaultAsync(m => m.Id == id && m.RoomId == room.Id && m.DeletedAt == null && m.Kind != ChatKinds.System, ct)
                   ?? throw Fail("message_not_found", 404);
        var now = clock.GetUtcNow();
        if (line.AuthorId != me)
        {
            if (!await CanModerateAsync(me, room, ct)) throw Fail("moderator_only", 403);
            db.VoiceEvents.Add(new VoiceEvent { RoomId = room.Id, UserId = line.AuthorId, ActorId = me, Kind = VoiceEventKinds.LineDelete, At = now });
        }
        line.DeletedAt = now;
        line.DeletedById = me;
        await db.SaveChangesAsync(ct);
    }

    // ---------------------------------------------------------------- retention and complaints

    /// <summary>The newest lines of a room as plain text for a complaint, oldest first; <paramref name="held"/> receives the ids copied.</summary>
    async Task<string> CopyOfFeedAsync(VoiceRoom room, Guid about, List<long> held, CancellationToken ct)
    {
        var since = clock.GetUtcNow() - VoiceLimits.ComplaintLookback;
        var rows = await db.RoomMessages.AsNoTracking().Where(m => m.RoomId == room.Id && m.DeletedAt == null && m.CreatedAt >= since)
            .OrderByDescending(m => m.Id).Take(VoiceLimits.ComplaintLines).ToListAsync(ct);
        var names = await NamesAsync(rows.Select(m => m.AuthorId).Append(about), ct);
        var sb = new StringBuilder();
        foreach (var m in rows)
        {
            var who = names.GetValueOrDefault(m.AuthorId, "");
            var text = m.Kind switch
            {
                ChatKinds.Action => $"* {who} {m.Body}",
                ChatKinds.System => $"-- {who}: {m.Body}",
                _ => $"{who}: {m.Body}",
            };
            var line = $"{(m.AuthorId == about ? "► " : "")}[{m.CreatedAt:yyyy-MM-dd HH:mm}] {text}\n";
            if (sb.Length + line.Length > VoiceLimits.ComplaintLineChars && held.Count > 0) break;
            sb.Insert(0, line);
            held.Add(m.Id);
        }
        return sb.ToString().TrimEnd();
    }

    /// <summary>Whom a complaint about a public channel can be about: those who wrote in it lately.</summary>
    public async Task<IReadOnlyList<PersonView>> ChannelPeopleAsync(Guid me, string? publicId, CancellationToken ct)
    {
        var (room, _) = await ChatRoomAsync(me, publicId, ct);
        var authors = await db.RoomMessages.AsNoTracking().Where(m => m.RoomId == room.Id && m.Kind != ChatKinds.System && m.DeletedAt == null)
            .OrderByDescending(m => m.Id).Take(300).Select(m => m.AuthorId).ToListAsync(ct);
        var ids = authors.Where(a => a != me).Distinct().Take(50).ToList();
        var names = await NamesAsync(ids, ct);
        return ids.Where(names.ContainsKey).Select(id => new PersonView(id, names[id])).OrderBy(p => p.Name, StringComparer.CurrentCultureIgnoreCase).ToList();
    }

    async Task<bool> KnownInChannelAsync(VoiceRoom room, Guid who, CancellationToken ct) =>
        await db.RoomChannelStates.AnyAsync(s => s.RoomId == room.Id && s.UserId == who, ct)
        || await db.RoomMessages.AnyAsync(m => m.RoomId == room.Id && m.AuthorId == who, ct);
}
