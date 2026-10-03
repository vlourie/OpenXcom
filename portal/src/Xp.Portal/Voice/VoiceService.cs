using System.Security.Cryptography;
using System.Text;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Storage;
using Microsoft.Extensions.Options;
using Xp.Portal.Auth;
using Xp.Portal.Data;
using Xp.Portal.Devices;
using Xp.Portal.Site;
using Xp.Portal.Tickets;

namespace Xp.Portal.Voice;

/// <summary>A refusal with its machine-readable reason (also the key of the text people read) and the HTTP status it maps to.</summary>
public sealed class VoiceException(string code, int status) : Exception(code)
{
    public string Code { get; } = code;
    public int Status { get; } = status;
}

/// <summary>Where a person stands with one room. Anything but Ok keeps them out.</summary>
public enum RoomAccess { Ok, NoAccess, RoomClosed, AccountBanned, Banned, InviteRevoked, NotFriends }

public sealed record PersonView(Guid Id, string Name);
public sealed record FriendView(Guid Id, string Name, DateTimeOffset Since);
public sealed record RequestView(Guid Id, PersonView Person, DateTimeOffset At);
public sealed record FriendsView(IReadOnlyList<FriendView> Friends, int FriendsTotal, IReadOnlyList<RequestView> Incoming,
    IReadOnlyList<RequestView> Outgoing, IReadOnlyList<PersonView> Blocked);
/// <summary>A room as one person sees it. State is that person's standing: ok, room_closed, account_banned, banned, invite_revoked, not_friends.</summary>
public sealed record RoomSummary(string PublicId, string Title, PersonView Owner, bool Mine, string Status, string State, bool InviteDeclined,
    int Capacity, DateTimeOffset CreatedAt);
public sealed record MemberView(PersonView Person, string Invite, bool Banned, bool Restricted, bool Friend);
public sealed record RoomView(RoomSummary Room, IReadOnlyList<MemberView>? Members, bool ClosedByStaff, string? ClosedReason);
public sealed record LiveView(PersonView Person, bool CanPublish, DateTimeOffset? JoinedAt);
public sealed record PassView(string Url, string Token, string Room, string RoomName, string Identity, string Name, bool CanPublish, int ExpiresIn);

/// <summary>
/// Friends, rooms, invites and who may talk where (docs/portal/VOICE_CHAT.md). Every rule lives here:
/// the API and the site pages both call it, and a refusal is a <see cref="VoiceException"/>.
/// Changes to one pair of people or one room are serialised by a PostgreSQL advisory lock for the
/// length of their transaction, so two clicks at once cannot leave two pending requests or a ban
/// that the next pass does not see.
/// </summary>
public sealed class VoiceService(PortalDb db, TimeProvider clock, IVoiceServer server, IOptions<LiveKitOptions> options,
    IOptions<PortalOptions> portal, LiveKitTokens tokens, TicketService tickets, Text text, ILogger<VoiceService> log)
{
    readonly List<VoiceJob> _fresh = [];

    static VoiceException Fail(string code, int status = 400) => new(code, status);
    static VoiceException NoAccess() => Fail("no_access", 404);

    // ---------------------------------------------------------------- people

    public async Task<PersonView> PersonAsync(Guid id, CancellationToken ct)
    {
        var u = await db.Users.AsNoTracking().FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw Fail("user_not_found", 404);
        return new PersonView(u.Id, DeviceApi.Display(u));
    }

    /// <summary>
    /// Finds who a request is for: a profile link or a bare id first, then an exact display name.
    /// A name two people share is not guessed at - the person is asked for the link instead.
    /// </summary>
    public async Task<Guid> FindPersonAsync(string? who, CancellationToken ct)
    {
        who = (who ?? "").Trim();
        if (who.Length is 0 or > 256) throw Fail("user_not_found", 404);
        var tail = who.TrimEnd('/');
        tail = tail[(tail.LastIndexOf('/') + 1)..];
        if (Guid.TryParse(tail, out var id))
            return await db.Users.AnyAsync(u => u.Id == id, ct) ? id : throw Fail("user_not_found", 404);
        var lower = who.ToLowerInvariant();
        var found = await db.Users.Where(u => u.DisplayName.ToLower() == lower).Select(u => u.Id).Take(2).ToListAsync(ct);
        return found.Count switch
        {
            0 => throw Fail("user_not_found", 404),
            1 => found[0],
            _ => throw Fail("name_ambiguous", 409),
        };
    }

    async Task<Dictionary<Guid, string>> NamesAsync(IEnumerable<Guid> ids, CancellationToken ct)
    {
        var set = ids.Distinct().ToList();
        var users = await db.Users.AsNoTracking().Where(u => set.Contains(u.Id)).ToListAsync(ct);
        return users.ToDictionary(u => u.Id, DeviceApi.Display);
    }

    Task<bool> AreFriendsAsync(Guid a, Guid b, CancellationToken ct)
    {
        var (lo, hi) = Friendship.Pair(a, b);
        return db.Friendships.AnyAsync(f => f.UserLowId == lo && f.UserHighId == hi, ct);
    }

    Task<bool> BlockedEitherWayAsync(Guid a, Guid b, CancellationToken ct) =>
        db.UserBlocks.AnyAsync(x => (x.BlockerId == a && x.BlockedId == b) || (x.BlockerId == b && x.BlockedId == a), ct);

    // ---------------------------------------------------------------- friends

    public async Task<FriendsView> FriendsAsync(Guid me, int page, int perPage, CancellationToken ct)
    {
        var mine = db.Friendships.Where(f => f.UserLowId == me || f.UserHighId == me);
        var total = await mine.CountAsync(ct);
        var rows = await mine.Select(f => new { Other = f.UserLowId == me ? f.UserHighId : f.UserLowId, f.CreatedAt }).ToListAsync(ct);
        var incoming = await db.FriendRequests.Where(r => r.RecipientId == me && r.Status == FriendRequestStatus.Pending)
            .OrderByDescending(r => r.CreatedAt).Take(100).ToListAsync(ct);
        var outgoing = await db.FriendRequests.Where(r => r.SenderId == me && r.Status == FriendRequestStatus.Pending)
            .OrderByDescending(r => r.CreatedAt).Take(VoiceLimits.PendingOutgoing).ToListAsync(ct);
        var blocked = await db.UserBlocks.Where(x => x.BlockerId == me).OrderByDescending(x => x.CreatedAt).Take(VoiceLimits.Blocks)
            .Select(x => x.BlockedId).ToListAsync(ct);
        var names = await NamesAsync(rows.Select(r => r.Other).Concat(incoming.Select(r => r.SenderId))
            .Concat(outgoing.Select(r => r.RecipientId)).Concat(blocked), ct);
        string N(Guid id) => names.GetValueOrDefault(id, "");
        // sorted by name for a person reading the list; paged here, not in SQL, because the name lives on another table
        var friends = rows.Select(r => new FriendView(r.Other, N(r.Other), r.CreatedAt))
            .OrderBy(f => f.Name, StringComparer.CurrentCultureIgnoreCase)
            .Skip(Math.Max(0, page - 1) * perPage).Take(perPage).ToList();
        return new FriendsView(friends, total,
            incoming.Select(r => new RequestView(r.Id, new PersonView(r.SenderId, N(r.SenderId)), r.CreatedAt)).ToList(),
            outgoing.Select(r => new RequestView(r.Id, new PersonView(r.RecipientId, N(r.RecipientId)), r.CreatedAt)).ToList(),
            blocked.Select(id => new PersonView(id, N(id))).ToList());
    }

    /// <summary>Sends a request, or accepts the one already waiting from the other side. Returns "sent" or "accepted".</summary>
    public async Task<string> RequestAsync(Guid me, Guid to, CancellationToken ct)
    {
        if (to == me) throw Fail("self");
        if (!await db.Users.AnyAsync(u => u.Id == to, ct)) throw Fail("user_not_found", 404);
        await using var tx = await LockPairAsync(me, to, ct);
        if (await db.UserBlocks.AnyAsync(x => x.BlockerId == me && x.BlockedId == to, ct)) throw Fail("you_blocked", 409);
        // blocked by them, or turned down a week ago: the same answer, so a refusal does not read as a block
        var now = clock.GetUtcNow();
        if (await db.UserBlocks.AnyAsync(x => x.BlockerId == to && x.BlockedId == me, ct)
            || await db.FriendRequests.AnyAsync(r => r.SenderId == me && r.RecipientId == to && r.Status == FriendRequestStatus.Declined
                && r.AnsweredAt > now.AddDays(-7), ct))
            throw Fail("request_refused", 403);
        if (await AreFriendsAsync(me, to, ct)) throw Fail("already_friends", 409);
        if (await db.FriendRequests.AnyAsync(r => r.SenderId == me && r.RecipientId == to && r.Status == FriendRequestStatus.Pending, ct))
            throw Fail("already_sent", 409);

        var theirs = await db.FriendRequests.FirstOrDefaultAsync(r => r.SenderId == to && r.RecipientId == me && r.Status == FriendRequestStatus.Pending, ct);
        if (theirs is not null)
        {
            await BefriendAsync(me, to, ct);
            theirs.Status = FriendRequestStatus.Accepted;
            theirs.AnsweredAt = now;
            await db.SaveChangesAsync(ct);
            await tx.CommitAsync(ct);
            return "accepted";
        }

        if (await db.FriendRequests.CountAsync(r => r.SenderId == me && r.Status == FriendRequestStatus.Pending, ct) >= VoiceLimits.PendingOutgoing
            || await db.FriendRequests.CountAsync(r => r.SenderId == me && r.CreatedAt > now.AddDays(-1), ct) >= VoiceLimits.RequestsPerDay)
            throw Fail("limit_requests", 429);
        db.FriendRequests.Add(new FriendRequest { SenderId = me, RecipientId = to, CreatedAt = now });
        await db.SaveChangesAsync(ct);
        await tx.CommitAsync(ct);
        return "sent";
    }

    async Task BefriendAsync(Guid a, Guid b, CancellationToken ct)
    {
        foreach (var who in new[] { a, b })
            if (await db.Friendships.CountAsync(f => f.UserLowId == who || f.UserHighId == who, ct) >= VoiceLimits.Friends)
                throw Fail("limit_friends", 409);
        var (lo, hi) = Friendship.Pair(a, b);
        db.Friendships.Add(new Friendship { UserLowId = lo, UserHighId = hi, CreatedAt = clock.GetUtcNow() });
    }

    public async Task AcceptAsync(Guid me, Guid requestId, CancellationToken ct) => await AnswerAsync(me, requestId, accept: true, ct);
    public async Task DeclineAsync(Guid me, Guid requestId, CancellationToken ct) => await AnswerAsync(me, requestId, accept: false, ct);

    async Task AnswerAsync(Guid me, Guid requestId, bool accept, CancellationToken ct)
    {
        var r = await db.FriendRequests.AsNoTracking().FirstOrDefaultAsync(x => x.Id == requestId && x.RecipientId == me, ct)
            ?? throw Fail("request_not_found", 404);
        await using var tx = await LockPairAsync(r.SenderId, me, ct);
        var row = await db.FriendRequests.FirstAsync(x => x.Id == requestId, ct);
        if (row.Status != FriendRequestStatus.Pending) throw Fail("request_not_found", 404);
        if (accept)
        {
            if (await BlockedEitherWayAsync(me, row.SenderId, ct)) throw Fail("request_refused", 403);
            if (!await AreFriendsAsync(me, row.SenderId, ct)) await BefriendAsync(me, row.SenderId, ct);
        }
        row.Status = accept ? FriendRequestStatus.Accepted : FriendRequestStatus.Declined;
        row.AnsweredAt = clock.GetUtcNow();
        await db.SaveChangesAsync(ct);
        await tx.CommitAsync(ct);
    }

    public async Task CancelRequestAsync(Guid me, Guid requestId, CancellationToken ct)
    {
        var n = await db.FriendRequests.Where(r => r.Id == requestId && r.SenderId == me && r.Status == FriendRequestStatus.Pending)
            .ExecuteUpdateAsync(s => s.SetProperty(r => r.Status, FriendRequestStatus.Cancelled).SetProperty(r => r.AnsweredAt, clock.GetUtcNow()), ct);
        if (n == 0) throw Fail("request_not_found", 404);
    }

    /// <summary>No longer friends: each loses every invite to the other's rooms at once and is taken out of them.</summary>
    public async Task UnfriendAsync(Guid me, Guid other, CancellationToken ct)
    {
        await using var tx = await LockPairAsync(me, other, ct);
        var (lo, hi) = Friendship.Pair(me, other);
        var n = await db.Friendships.Where(f => f.UserLowId == lo && f.UserHighId == hi).ExecuteDeleteAsync(ct);
        if (n == 0) throw Fail("not_friends", 404);
        await SeverAsync(me, other, VoiceEventKinds.Unfriend, ct);
        await db.SaveChangesAsync(ct);
        await tx.CommitAsync(ct);
        await RunFreshAsync(ct);
    }

    /// <summary>A block undoes everything between the two: friendship, waiting requests, invites both ways.</summary>
    public async Task BlockAsync(Guid me, Guid other, CancellationToken ct)
    {
        if (other == me) throw Fail("self");
        if (!await db.Users.AnyAsync(u => u.Id == other, ct)) throw Fail("user_not_found", 404);
        await using var tx = await LockPairAsync(me, other, ct);
        if (await db.UserBlocks.AnyAsync(x => x.BlockerId == me && x.BlockedId == other, ct)) { await tx.CommitAsync(ct); return; }
        if (await db.UserBlocks.CountAsync(x => x.BlockerId == me, ct) >= VoiceLimits.Blocks) throw Fail("limit_blocks", 409);
        db.UserBlocks.Add(new UserBlock { BlockerId = me, BlockedId = other, CreatedAt = clock.GetUtcNow() });
        var (lo, hi) = Friendship.Pair(me, other);
        await db.Friendships.Where(f => f.UserLowId == lo && f.UserHighId == hi).ExecuteDeleteAsync(ct);
        await db.FriendRequests.Where(r => r.Status == FriendRequestStatus.Pending
                && ((r.SenderId == me && r.RecipientId == other) || (r.SenderId == other && r.RecipientId == me)))
            .ExecuteUpdateAsync(s => s.SetProperty(r => r.Status, FriendRequestStatus.Cancelled).SetProperty(r => r.AnsweredAt, clock.GetUtcNow()), ct);
        await SeverAsync(me, other, VoiceEventKinds.Block, ct);
        await db.SaveChangesAsync(ct);
        await tx.CommitAsync(ct);
        await RunFreshAsync(ct);
    }

    public async Task UnblockAsync(Guid me, Guid other, CancellationToken ct) =>
        await db.UserBlocks.Where(x => x.BlockerId == me && x.BlockedId == other).ExecuteDeleteAsync(ct);

    /// <summary>Revokes the invites of each to the other's rooms and takes each out of them, with a log line per room.</summary>
    async Task SeverAsync(Guid a, Guid b, string kind, CancellationToken ct)
    {
        var now = clock.GetUtcNow();
        var invites = await db.RoomInvites
            .Join(db.VoiceRooms, i => i.RoomId, r => r.Id, (i, r) => new { Invite = i, r.OwnerId })
            .Where(x => (x.OwnerId == a && x.Invite.UserId == b) || (x.OwnerId == b && x.Invite.UserId == a))
            .Select(x => x.Invite).ToListAsync(ct);
        foreach (var i in invites)
        {
            if (i.Status != RoomInviteStatus.Revoked) { i.Status = RoomInviteStatus.Revoked; i.UpdatedAt = now; }
            Enqueue(VoiceJobKind.Remove, i.RoomId, i.UserId);
            db.VoiceEvents.Add(new VoiceEvent { RoomId = i.RoomId, UserId = i.UserId, ActorId = i.UserId == a ? b : a, Kind = kind, At = now });
        }
    }

    // ---------------------------------------------------------------- rooms

    public async Task<(IReadOnlyList<RoomSummary> Owned, IReadOnlyList<RoomSummary> Invited)> RoomsAsync(Guid me, CancellationToken ct)
    {
        var owned = await db.VoiceRooms.AsNoTracking().Where(r => r.OwnerId == me).OrderBy(r => r.CreatedAt).ToListAsync(ct);
        var invites = await db.RoomInvites.AsNoTracking().Where(i => i.UserId == me)
            .Join(db.VoiceRooms.AsNoTracking(), i => i.RoomId, r => r.Id, (i, r) => new { i, r })
            .OrderByDescending(x => x.i.UpdatedAt).Take(200).ToListAsync(ct);
        var names = await NamesAsync(owned.Select(r => r.OwnerId).Concat(invites.Select(x => x.r.OwnerId)), ct);
        var result = new List<RoomSummary>();
        foreach (var x in invites)
        {
            // a declined invite is hidden from the list; a revoked or banned one stays, so the person knows why
            if (x.i.Status == RoomInviteStatus.Declined) continue;
            var a = await AccessAsync(me, x.r, ct);
            result.Add(Summary(x.r, names, me, a, x.i));
        }
        var mine = new List<RoomSummary>();
        foreach (var r in owned) mine.Add(Summary(r, names, me, await AccessAsync(me, r, ct), null));
        return (mine, result);
    }

    static RoomSummary Summary(VoiceRoom r, IReadOnlyDictionary<Guid, string> names, Guid me, (RoomAccess Access, bool CanPublish) a, RoomInvite? invite) =>
        new(r.PublicId, r.Title, new PersonView(r.OwnerId, names.GetValueOrDefault(r.OwnerId, "")), r.OwnerId == me,
            r.Status == VoiceRoomStatus.Open ? "open" : "closed", StateCode(a.Access), invite?.Status == RoomInviteStatus.Declined,
            r.Capacity, r.CreatedAt);

    public static string StateCode(RoomAccess a) => a switch
    {
        RoomAccess.Ok => "ok",
        RoomAccess.RoomClosed => "room_closed",
        RoomAccess.AccountBanned => "account_banned",
        RoomAccess.Banned => "banned",
        RoomAccess.InviteRevoked => "invite_revoked",
        RoomAccess.NotFriends => "not_friends",
        _ => "no_access",
    };

    public async Task<RoomSummary> CreateRoomAsync(Guid me, string? title, CancellationToken ct)
    {
        title = (title ?? "").Trim();
        if (title.Length is 0 or > VoiceLimits.TitleMax || title.Any(char.IsControl)) throw Fail("title_invalid");
        await using var tx = await LockAsync("owner", me, null, ct);
        if (await db.VoiceRooms.CountAsync(r => r.OwnerId == me, ct) >= VoiceLimits.RoomsPerOwner) throw Fail("limit_rooms", 409);
        var room = new VoiceRoom
        {
            PublicId = await FreePublicIdAsync(ct),
            OwnerId = me,
            Title = title,
            Capacity = Math.Clamp(options.Value.Capacity, 2, 100),
            CreatedAt = clock.GetUtcNow(),
        };
        db.VoiceRooms.Add(room);
        await db.SaveChangesAsync(ct);
        await tx.CommitAsync(ct);
        var me_ = await PersonAsync(me, ct);
        return new RoomSummary(room.PublicId, room.Title, me_, true, "open", "ok", false, room.Capacity, room.CreatedAt);
    }

    const string PublicAlphabet = "abcdefghjkmnpqrstuvwxyz23456789";

    async Task<string> FreePublicIdAsync(CancellationToken ct)
    {
        for (int i = 0; i < 5; i++)
        {
            var id = new string(RandomNumberGenerator.GetItems<char>(PublicAlphabet, VoiceLimits.PublicIdLength));
            if (!await db.VoiceRooms.AnyAsync(r => r.PublicId == id, ct)) return id;
        }
        throw new InvalidOperationException("cannot find a free room id");
    }

    Task<VoiceRoom?> RoomAsync(string? publicId, CancellationToken ct) =>
        publicId is { Length: VoiceLimits.PublicIdLength }
            ? db.VoiceRooms.FirstOrDefaultAsync(r => r.PublicId == publicId, ct)
            : Task.FromResult<VoiceRoom?>(null);

    /// <summary>The room page. An outsider and a room that does not exist get the same answer.</summary>
    public async Task<RoomView> RoomViewAsync(Guid me, string? publicId, CancellationToken ct)
    {
        var room = await RoomAsync(publicId, ct);
        var a = await AccessAsync(me, room, ct);
        if (a.Access == RoomAccess.NoAccess) throw NoAccess();
        var invite = room!.OwnerId == me ? null : await db.RoomInvites.AsNoTracking().FirstOrDefaultAsync(i => i.RoomId == room.Id && i.UserId == me, ct);
        var names = await NamesAsync([room.OwnerId], ct);
        var summary = Summary(room, names, me, a, invite);
        var byStaff = room.Status == VoiceRoomStatus.Closed && room.ClosedById is { } by && by != room.OwnerId;
        if (room.OwnerId != me) return new RoomView(summary, null, byStaff, room.ClosedReason);

        var invites = await db.RoomInvites.AsNoTracking().Where(i => i.RoomId == room.Id).ToListAsync(ct);
        var bans = await db.RoomBans.AsNoTracking().Where(b => b.RoomId == room.Id).Select(b => b.UserId).ToListAsync(ct);
        var muted = await db.RoomSpeakingRestrictions.AsNoTracking().Where(x => x.RoomId == room.Id && x.Restricted).Select(x => x.UserId).ToListAsync(ct);
        var people = invites.Select(i => i.UserId).Concat(bans).Distinct().ToList();
        var friends = await db.Friendships.AsNoTracking().Where(f => f.UserLowId == me || f.UserHighId == me)
            .Select(f => f.UserLowId == me ? f.UserHighId : f.UserLowId).Where(id => people.Contains(id)).ToListAsync(ct);
        var who = await NamesAsync(people, ct);
        var members = people.Select(id =>
        {
            var inv = invites.FirstOrDefault(i => i.UserId == id);
            var state = inv is null ? "none" : inv.Status.ToString().ToLowerInvariant();
            return new MemberView(new PersonView(id, who.GetValueOrDefault(id, "")), state, bans.Contains(id), muted.Contains(id), friends.Contains(id));
        }).OrderBy(m => m.Person.Name, StringComparer.CurrentCultureIgnoreCase).ToList();
        return new RoomView(summary, members, byStaff, room.ClosedReason);
    }

    public async Task DeleteRoomAsync(Guid me, string? publicId, CancellationToken ct)
    {
        var room = await OwnedAsync(me, publicId, ct);
        await using var tx = await LockAsync("room", room.Id, null, ct);
        Enqueue(VoiceJobKind.CloseRoom, room.Id, null);
        db.VoiceRooms.Remove(room);
        await db.SaveChangesAsync(ct);
        await tx.CommitAsync(ct);
        await RunFreshAsync(ct);
    }

    /// <summary>Closes a room: everyone out, nobody in. By the owner, or by a SuperAdmin (staff) with a reason.</summary>
    public async Task CloseRoomAsync(Guid actor, string? publicId, string? reason, bool staff, CancellationToken ct)
    {
        var room = staff ? await RoomAsync(publicId, ct) ?? throw NoAccess() : await OwnedAsync(actor, publicId, ct);
        reason = Reason(reason, required: staff);
        await using var tx = await LockAsync("room", room.Id, null, ct);
        if (room.Status == VoiceRoomStatus.Closed) { await tx.CommitAsync(ct); return; }
        var now = clock.GetUtcNow();
        room.Status = VoiceRoomStatus.Closed;
        room.ClosedAt = now;
        room.ClosedById = actor;
        room.ClosedReason = reason;
        db.VoiceEvents.Add(new VoiceEvent { RoomId = room.Id, UserId = room.OwnerId, ActorId = actor, Kind = VoiceEventKinds.Close, Reason = reason, At = now });
        Enqueue(VoiceJobKind.CloseRoom, room.Id, null);
        await db.SaveChangesAsync(ct);
        await tx.CommitAsync(ct);
        await RunFreshAsync(ct);
    }

    public async Task ReopenRoomAsync(Guid actor, string? publicId, bool staff, CancellationToken ct)
    {
        var room = staff ? await RoomAsync(publicId, ct) ?? throw NoAccess() : await OwnedAsync(actor, publicId, ct);
        await using var tx = await LockAsync("room", room.Id, null, ct);
        if (room.Status == VoiceRoomStatus.Open) { await tx.CommitAsync(ct); return; }
        // staff's decision is staff's to undo
        if (!staff && room.ClosedById is { } by && by != room.OwnerId) throw Fail("closed_by_staff", 403);
        room.Status = VoiceRoomStatus.Open;
        room.ClosedAt = null;
        room.ClosedById = null;
        room.ClosedReason = null;
        db.VoiceEvents.Add(new VoiceEvent { RoomId = room.Id, UserId = room.OwnerId, ActorId = actor, Kind = VoiceEventKinds.Reopen, At = clock.GetUtcNow() });
        await db.SaveChangesAsync(ct);
        await tx.CommitAsync(ct);
    }

    /// <summary>The caller's own room, or the same "no access" an outsider gets; an invited guest is told it is the owner's to do.</summary>
    async Task<VoiceRoom> OwnedAsync(Guid me, string? publicId, CancellationToken ct)
    {
        var room = await RoomAsync(publicId, ct) ?? throw NoAccess();
        if (room.OwnerId == me) return room;
        if (await db.RoomInvites.AnyAsync(i => i.RoomId == room.Id && i.UserId == me, ct)) throw Fail("owner_only", 403);
        throw NoAccess();
    }

    static string? Reason(string? reason, bool required = false)
    {
        reason = reason?.Trim();
        if (string.IsNullOrEmpty(reason)) return required ? throw Fail("reason_required") : null;
        if (reason.Length > VoiceLimits.ReasonMax) throw Fail("reason_too_long");
        return reason;
    }

    // ---------------------------------------------------------------- invites

    public async Task InviteAsync(Guid me, string? publicId, Guid user, CancellationToken ct)
    {
        var room = await OwnedAsync(me, publicId, ct);
        if (user == me) throw Fail("self");
        await using var tx = await LockAsync("room", room.Id, null, ct);
        if (!await AreFriendsAsync(me, user, ct) || await BlockedEitherWayAsync(me, user, ct)) throw Fail("not_friends", 403);
        if (await db.RoomBans.AnyAsync(b => b.RoomId == room.Id && b.UserId == user, ct)) throw Fail("banned_in_room", 409);
        var now = clock.GetUtcNow();
        var invite = await db.RoomInvites.FirstOrDefaultAsync(i => i.RoomId == room.Id && i.UserId == user, ct);
        if (invite is null)
        {
            if (await db.RoomInvites.CountAsync(i => i.RoomId == room.Id, ct) >= VoiceLimits.InvitesPerRoom) throw Fail("limit_invites", 409);
            db.RoomInvites.Add(new RoomInvite { RoomId = room.Id, UserId = user, CreatedAt = now, UpdatedAt = now });
        }
        else if (invite.Status == RoomInviteStatus.Active) { await tx.CommitAsync(ct); return; }
        else { invite.Status = RoomInviteStatus.Active; invite.UpdatedAt = now; }
        db.VoiceEvents.Add(new VoiceEvent { RoomId = room.Id, UserId = user, ActorId = me, Kind = VoiceEventKinds.Invite, At = now });
        await db.SaveChangesAsync(ct);
        await tx.CommitAsync(ct);
    }

    public Task RevokeAsync(Guid me, string? publicId, Guid user, string? reason, CancellationToken ct) =>
        RemoveMemberAsync(me, publicId, user, reason, VoiceEventKinds.Revoke, ban: false, ct);

    /// <summary>The invited person turns the invite down: it disappears from their list, and the owner may invite again.</summary>
    public async Task DeclineInviteAsync(Guid me, string? publicId, CancellationToken ct)
    {
        var room = await RoomAsync(publicId, ct) ?? throw NoAccess();
        var n = await db.RoomInvites.Where(i => i.RoomId == room.Id && i.UserId == me && i.Status == RoomInviteStatus.Active)
            .ExecuteUpdateAsync(s => s.SetProperty(i => i.Status, RoomInviteStatus.Declined).SetProperty(i => i.UpdatedAt, clock.GetUtcNow()), ct);
        if (n == 0 && !await db.RoomInvites.AnyAsync(i => i.RoomId == room.Id && i.UserId == me, ct)) throw NoAccess();
    }

    // ---------------------------------------------------------------- moderation (the owner only)

    public Task KickAsync(Guid me, string? publicId, Guid user, string? reason, CancellationToken ct) =>
        RemoveMemberAsync(me, publicId, user, reason, VoiceEventKinds.Kick, ban: false, ct);

    public Task BanAsync(Guid me, string? publicId, Guid user, string? reason, CancellationToken ct) =>
        RemoveMemberAsync(me, publicId, user, reason, VoiceEventKinds.Ban, ban: true, ct);

    /// <summary>
    /// Out of the room now, invite revoked, and with a ban also out until let back. The order is the
    /// one the design asks for: the database first, then the media server, retried from the queue.
    /// </summary>
    async Task RemoveMemberAsync(Guid me, string? publicId, Guid user, string? reason, string kind, bool ban, CancellationToken ct)
    {
        var room = await OwnedAsync(me, publicId, ct);
        if (user == me) throw Fail("owner_target");
        reason = Reason(reason);
        await using var tx = await LockAsync("room", room.Id, null, ct);
        var now = clock.GetUtcNow();
        var invite = await db.RoomInvites.FirstOrDefaultAsync(i => i.RoomId == room.Id && i.UserId == user, ct);
        var banned = await db.RoomBans.AnyAsync(b => b.RoomId == room.Id && b.UserId == user, ct);
        if (invite is null && !banned)
        {
            // never invited: nothing to revoke, but a ban of a stranger is still a ban the owner may want
            if (!ban || !await db.Users.AnyAsync(u => u.Id == user, ct)) throw Fail("user_not_found", 404);
        }
        if (invite is not null && invite.Status != RoomInviteStatus.Revoked) { invite.Status = RoomInviteStatus.Revoked; invite.UpdatedAt = now; }
        if (ban && !banned) db.RoomBans.Add(new RoomBan { RoomId = room.Id, UserId = user, ById = me, CreatedAt = now });
        db.VoiceEvents.Add(new VoiceEvent { RoomId = room.Id, UserId = user, ActorId = me, Kind = kind, Reason = reason, At = now });
        Enqueue(VoiceJobKind.Remove, room.Id, user);
        await db.SaveChangesAsync(ct);
        await tx.CommitAsync(ct);
        await RunFreshAsync(ct);
    }

    public async Task UnbanAsync(Guid me, string? publicId, Guid user, CancellationToken ct)
    {
        var room = await OwnedAsync(me, publicId, ct);
        await using var tx = await LockAsync("room", room.Id, null, ct);
        var n = await db.RoomBans.Where(b => b.RoomId == room.Id && b.UserId == user).ExecuteDeleteAsync(ct);
        if (n > 0) db.VoiceEvents.Add(new VoiceEvent { RoomId = room.Id, UserId = user, ActorId = me, Kind = VoiceEventKinds.Unban, At = clock.GetUtcNow() });
        await db.SaveChangesAsync(ct);
        await tx.CommitAsync(ct);
    }

    /// <summary>
    /// Takes away (or gives back) the right to talk. Written to the database first, so every later pass
    /// is issued without it whatever device or client comes; then the live participant is told.
    /// </summary>
    public async Task SetSpeakingAsync(Guid me, string? publicId, Guid user, bool allowed, string? reason, CancellationToken ct)
    {
        var room = await OwnedAsync(me, publicId, ct);
        if (user == me) throw Fail("owner_target");
        reason = Reason(reason);
        await using var tx = await LockAsync("room", room.Id, null, ct);
        if (!await db.RoomInvites.AnyAsync(i => i.RoomId == room.Id && i.UserId == user, ct)) throw Fail("user_not_found", 404);
        var now = clock.GetUtcNow();
        var row = await db.RoomSpeakingRestrictions.FirstOrDefaultAsync(x => x.RoomId == room.Id && x.UserId == user, ct);
        if (row is null) db.RoomSpeakingRestrictions.Add(row = new RoomSpeakingRestriction { RoomId = room.Id, UserId = user });
        row.Restricted = !allowed;
        row.UpdatedAt = now;
        db.VoiceEvents.Add(new VoiceEvent { RoomId = room.Id, UserId = user, ActorId = me, Kind = allowed ? VoiceEventKinds.Unmute : VoiceEventKinds.Mute, Reason = reason, At = now });
        var job = Enqueue(VoiceJobKind.SetPublish, room.Id, user);
        job.CanPublish = allowed;
        await db.SaveChangesAsync(ct);
        await tx.CommitAsync(ct);
        await RunFreshAsync(ct);
    }

    // ---------------------------------------------------------------- access and the pass

    /// <summary>
    /// The one answer to "may this person be in this room": owner, or invited friend of the owner,
    /// with the room open, no ban of the room or of the account, no block. And whether they may talk.
    /// </summary>
    public async Task<(RoomAccess Access, bool CanPublish)> AccessAsync(Guid me, VoiceRoom? room, CancellationToken ct)
    {
        if (room is null) return (RoomAccess.NoAccess, false);
        var owner = room.OwnerId == me;
        var invite = owner ? null : await db.RoomInvites.AsNoTracking().FirstOrDefaultAsync(i => i.RoomId == room.Id && i.UserId == me, ct);
        // never invited (or since forgotten with the room): the same as no such room
        if (!owner && invite is null && !await db.RoomBans.AnyAsync(b => b.RoomId == room.Id && b.UserId == me, ct)) return (RoomAccess.NoAccess, false);
        if (room.Status == VoiceRoomStatus.Closed) return (RoomAccess.RoomClosed, false);
        if (await db.VoiceAccountBans.AnyAsync(b => b.UserId == me && b.LiftedAt == null, ct)) return (RoomAccess.AccountBanned, false);
        if (owner) return (RoomAccess.Ok, true);
        if (await db.RoomBans.AnyAsync(b => b.RoomId == room.Id && b.UserId == me, ct)) return (RoomAccess.Banned, false);
        if (invite!.Status == RoomInviteStatus.Revoked) return (RoomAccess.InviteRevoked, false);
        if (!await AreFriendsAsync(me, room.OwnerId, ct) || await BlockedEitherWayAsync(me, room.OwnerId, ct)) return (RoomAccess.NotFriends, false);
        var restricted = await db.RoomSpeakingRestrictions.AnyAsync(x => x.RoomId == room.Id && x.UserId == me && x.Restricted, ct);
        return (RoomAccess.Ok, !restricted);
    }

    /// <summary>
    /// A pass into one room, checked afresh every time: session, room open, friendship, invite, no ban
    /// or block, a free place. One minute of life; the launcher asks again on every reconnect.
    /// </summary>
    public async Task<PassView> PassAsync(Guid me, string? publicId, CancellationToken ct)
    {
        var room = await RoomAsync(publicId, ct);
        var (access, canPublish) = await AccessAsync(me, room, ct);
        if (access == RoomAccess.NoAccess) throw NoAccess();
        if (access != RoomAccess.Ok) throw Fail(StateCode(access), 403);
        if (!server.Enabled) throw Fail("voice_unavailable", 503);
        var o = options.Value;
        // the station's probe is for the closed acceptance: it must never become the players' voice server
        if (o.IsProbeFor(portal.Value.PublicUrl) && !await TesterAsync(me, o, ct))
        {
            log.LogInformation("voice pass for {User}: the media server is the station's probe, and only testers get passes", me);
            throw Fail("voice_unavailable", 503);
        }
        var identity = me.ToString();
        try
        {
            await server.EnsureRoomAsync(room!.Id, room.Capacity, ct);
            var inside = await server.ParticipantsAsync(room.Id, ct);
            // the same person coming back replaces their old connection, so they do not count against the place
            if (inside.Count(p => p.Identity != identity) >= room.Capacity) throw Fail("room_full", 409);
        }
        catch (VoiceServerException e)
        {
            log.LogWarning("voice pass for room {Room}: media server unavailable: {Error}", room!.Id, e.Message);
            throw Fail("voice_unavailable", 503);
        }
        // coming in after all is taking the invite back up
        await db.RoomInvites.Where(i => i.RoomId == room.Id && i.UserId == me && i.Status == RoomInviteStatus.Declined)
            .ExecuteUpdateAsync(s => s.SetProperty(i => i.Status, RoomInviteStatus.Active).SetProperty(i => i.UpdatedAt, clock.GetUtcNow()), ct);
        var name = (await PersonAsync(me, ct)).Name;
        return new PassView(o.Url, tokens.Pass(room.Id, me, name, canPublish), room.PublicId, room.Id.ToString(), identity, name, canPublish, o.PassSeconds);
    }

    async Task<bool> TesterAsync(Guid me, LiveKitOptions o, CancellationToken ct)
    {
        if (o.Testers.Length == 0) return false;
        var email = await db.Users.Where(u => u.Id == me).Select(u => u.Email).FirstOrDefaultAsync(ct);
        return email is not null && o.Testers.Any(t => string.Equals(t.Trim(), email, StringComparison.OrdinalIgnoreCase));
    }

    /// <summary>Who is in the room right now. Only for those who may be in it themselves.</summary>
    public async Task<IReadOnlyList<LiveView>> LiveAsync(Guid me, string? publicId, CancellationToken ct)
    {
        var room = await RoomAsync(publicId, ct);
        var (access, _) = await AccessAsync(me, room, ct);
        if (access == RoomAccess.NoAccess) throw NoAccess();
        if (access != RoomAccess.Ok) throw Fail(StateCode(access), 403);
        if (!server.Enabled) return [];
        IReadOnlyList<LivePeer> peers;
        try { peers = await server.ParticipantsAsync(room!.Id, ct); }
        catch (VoiceServerException) { throw Fail("voice_unavailable", 503); }
        var ids = peers.Select(p => Guid.TryParse(p.Identity, out var g) ? g : Guid.Empty).Where(g => g != Guid.Empty).ToList();
        var names = await NamesAsync(ids, ct);
        return peers.Where(p => Guid.TryParse(p.Identity, out _))
            .Select(p => { var id = Guid.Parse(p.Identity); return new LiveView(new PersonView(id, names.GetValueOrDefault(id, p.Name)), p.CanPublish, p.JoinedAt); })
            .ToList();
    }

    // ---------------------------------------------------------------- the media server's side

    /// <summary>
    /// Somebody is in a room (webhook, or the sweep). Checked against the database again: whoever
    /// should not be there is taken out, whoever may not talk loses the right. This is what closes
    /// the window of a pass handed out before a ban, including one the media server renewed itself.
    /// Returns true if the person may stay.
    /// </summary>
    public async Task<bool> RecheckAsync(string roomName, string identity, bool canPublishNow, bool joined, CancellationToken ct)
    {
        if (!Guid.TryParse(roomName, out var roomId)) return true;   // not a room of ours: not ours to judge
        var room = await db.VoiceRooms.AsNoTracking().FirstOrDefaultAsync(r => r.Id == roomId, ct);
        var now = clock.GetUtcNow();
        if (!Guid.TryParse(identity, out var user) || room is null)
        {
            // a room deleted on the site, or a stranger's identity: nobody may be there
            if (room is null) Enqueue(VoiceJobKind.CloseRoom, roomId, null);
            else Enqueue(VoiceJobKind.Remove, roomId, null).Identity = identity;
            await db.SaveChangesAsync(ct);
            await RunFreshAsync(ct);
            return false;
        }
        var (access, canPublish) = await AccessAsync(user, room, ct);
        var known = await db.Users.AnyAsync(u => u.Id == user, ct);
        if (joined && known) db.VoiceEvents.Add(new VoiceEvent { RoomId = room.Id, UserId = user, Kind = VoiceEventKinds.Join, At = now });
        if (access != RoomAccess.Ok)
        {
            if (known) db.VoiceEvents.Add(new VoiceEvent { RoomId = room.Id, UserId = user, Kind = VoiceEventKinds.Ejected, Reason = StateCode(access), At = now });
            Enqueue(VoiceJobKind.Remove, room.Id, user);
        }
        else if (!canPublish && canPublishNow)
        {
            Enqueue(VoiceJobKind.SetPublish, room.Id, user).CanPublish = false;
        }
        await db.SaveChangesAsync(ct);
        await RunFreshAsync(ct);
        return access == RoomAccess.Ok;
    }

    public async Task LeftAsync(string roomName, string identity, CancellationToken ct)
    {
        if (!Guid.TryParse(roomName, out var roomId) || !Guid.TryParse(identity, out var user)) return;
        if (!await db.VoiceRooms.AnyAsync(r => r.Id == roomId, ct) || !await db.Users.AnyAsync(u => u.Id == user, ct)) return;
        db.VoiceEvents.Add(new VoiceEvent { RoomId = roomId, UserId = user, Kind = VoiceEventKinds.Leave, At = clock.GetUtcNow() });
        await db.SaveChangesAsync(ct);
    }

    // ---------------------------------------------------------------- staff

    /// <summary>No voice anywhere for an account: SuperAdmin's decision, independent of any room.</summary>
    public async Task AccountBanAsync(Guid actor, Guid user, string? reason, CancellationToken ct)
    {
        reason = Reason(reason, required: true);
        if (!await db.Users.AnyAsync(u => u.Id == user, ct)) throw Fail("user_not_found", 404);
        await using var tx = await LockAsync("account", user, null, ct);
        if (await db.VoiceAccountBans.AnyAsync(b => b.UserId == user && b.LiftedAt == null, ct)) { await tx.CommitAsync(ct); return; }
        var now = clock.GetUtcNow();
        db.VoiceAccountBans.Add(new VoiceAccountBan { UserId = user, ById = actor, Reason = reason!, CreatedAt = now });
        db.VoiceEvents.Add(new VoiceEvent { UserId = user, ActorId = actor, Kind = VoiceEventKinds.AccountBan, Reason = reason, At = now });
        // out of every room they could be in: their own and every one they were invited to
        var rooms = await db.VoiceRooms.Where(r => r.OwnerId == user).Select(r => r.Id)
            .Union(db.RoomInvites.Where(i => i.UserId == user).Select(i => i.RoomId)).ToListAsync(ct);
        foreach (var r in rooms) Enqueue(VoiceJobKind.Remove, r, user);
        await db.SaveChangesAsync(ct);
        await tx.CommitAsync(ct);
        await RunFreshAsync(ct);
    }

    public async Task AccountUnbanAsync(Guid actor, Guid user, CancellationToken ct)
    {
        await using var tx = await LockAsync("account", user, null, ct);
        var ban = await db.VoiceAccountBans.FirstOrDefaultAsync(b => b.UserId == user && b.LiftedAt == null, ct);
        if (ban is null) { await tx.CommitAsync(ct); return; }
        var now = clock.GetUtcNow();
        ban.LiftedAt = now;
        ban.LiftedById = actor;
        db.VoiceEvents.Add(new VoiceEvent { UserId = user, ActorId = actor, Kind = VoiceEventKinds.AccountUnban, At = now });
        await db.SaveChangesAsync(ct);
        await tx.CommitAsync(ct);
    }

    /// <summary>
    /// A complaint about somebody in a room becomes a ticket of category voice; the log of that room
    /// and that person over the last 30 days is tied to it and kept as long as the complaint needs it.
    /// No recording exists, so none is attached.
    /// </summary>
    public async Task<Ticket> ComplainAsync(Guid me, string? publicId, Guid about, string? body, CancellationToken ct)
    {
        var room = await RoomAsync(publicId, ct) ?? throw NoAccess();
        async Task<bool> Belongs(Guid who) => room.OwnerId == who
            || await db.RoomInvites.AnyAsync(i => i.RoomId == room.Id && i.UserId == who, ct)
            || await db.RoomBans.AnyAsync(b => b.RoomId == room.Id && b.UserId == who, ct);
        if (!await Belongs(me)) throw NoAccess();
        if (about == me || !await Belongs(about)) throw Fail("user_not_found", 404);
        body = (body ?? "").Trim();
        if (body.Length is 0 or > 2000) throw Fail("complaint_invalid");

        var who = await PersonAsync(about, ct);
        var reporter = await PersonAsync(me, ct);
        var title = text.Format("voice.complaint.title", who.Name, room.Title);
        var description = $"{body}\n\n---\n{text["voice.complaint.room"]}: {room.Title} ({room.PublicId})\n"
            + $"{text["voice.complaint.about"]}: {who.Name} ({who.Id})\n{text["voice.complaint.from"]}: {reporter.Name} ({reporter.Id})";
        var created = await tickets.CreateAsync(new NewTicket(Categories.Voice, title.Length > Limits.TitleMax ? title[..Limits.TitleMax] : title, description,
            Source: TicketSource.Voice, Language: Text.Lang), me, null, null, ct);
        var since = clock.GetUtcNow() - VoiceLimits.ComplaintLookback;
        var events = await db.VoiceEvents.Where(e => e.RoomId == room.Id && (e.UserId == about || e.ActorId == about) && e.At >= since)
            .Select(e => e.Id).ToListAsync(ct);
        foreach (var id in events) db.VoiceEventTickets.Add(new VoiceEventTicket { EventId = id, TicketId = created.Ticket.Id });
        await db.SaveChangesAsync(ct);
        return created.Ticket;
    }

    // ---------------------------------------------------------------- the queue of media-server commands

    VoiceJob Enqueue(VoiceJobKind kind, Guid room, Guid? user)
    {
        var now = clock.GetUtcNow();
        // tried right after the commit; the worker only steps in if that try did not get through
        var job = new VoiceJob { Kind = kind, RoomId = room, UserId = user, CreatedAt = now, NextAttemptAt = now + TimeSpan.FromSeconds(15) };
        db.VoiceJobs.Add(job);
        _fresh.Add(job);
        return job;
    }

    /// <summary>Runs the commands this unit of work queued, at once; what fails stays for the worker.</summary>
    async Task RunFreshAsync(CancellationToken ct)
    {
        var jobs = _fresh.ToList();
        _fresh.Clear();
        // without a media server there is nobody to tell; the queue keeps the commands for when it comes
        if (jobs.Count == 0 || !server.Enabled) return;
        var results = await Task.WhenAll(jobs.Select(j => VoiceWorker.TryAsync(server, j, ct)));
        var now = clock.GetUtcNow();
        for (int i = 0; i < jobs.Count; i++) VoiceWorker.Record(jobs[i], results[i], now);
        await db.SaveChangesAsync(CancellationToken.None);
    }

    // ---------------------------------------------------------------- locks

    Task<IDbContextTransaction> LockPairAsync(Guid a, Guid b, CancellationToken ct)
    {
        var (lo, hi) = Friendship.Pair(a, b);
        return LockAsync("pair", lo, hi, ct);
    }

    async Task<IDbContextTransaction> LockAsync(string scope, Guid a, Guid? b, CancellationToken ct)
    {
        var tx = await db.Database.BeginTransactionAsync(ct);
        var key = BitConverter.ToInt64(SHA256.HashData(Encoding.UTF8.GetBytes($"voice:{scope}:{a}:{b}")), 0);
        await db.Database.ExecuteSqlAsync($"SELECT pg_advisory_xact_lock({key})", ct);
        return tx;
    }
}
