namespace Xp.Portal.Data;

// Friends and voice rooms (docs/portal/VOICE_CHAT.md, section 7). The site is the one place that
// knows who may talk where: the media server only carries sound and is told nothing it could keep.

public enum FriendRequestStatus { Pending, Accepted, Declined, Cancelled }

/// <summary>A request to become friends. At most one pending per ordered pair, and the service never lets both directions wait at once.</summary>
public sealed class FriendRequest
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public Guid SenderId { get; set; }
    public Guid RecipientId { get; set; }
    public FriendRequestStatus Status { get; set; } = FriendRequestStatus.Pending;
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
    public DateTimeOffset? AnsweredAt { get; set; }
}

/// <summary>Friendship is mutual, so it is one row per pair, the smaller id first.</summary>
public sealed class Friendship
{
    public Guid UserLowId { get; set; }
    public Guid UserHighId { get; set; }
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;

    public static (Guid Low, Guid High) Pair(Guid a, Guid b) => a.CompareTo(b) < 0 ? (a, b) : (b, a);
}

/// <summary>One person shutting another out: no requests, no friendship, no invites either way.</summary>
public sealed class UserBlock
{
    public Guid BlockerId { get; set; }
    public Guid BlockedId { get; set; }
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
}

public enum VoiceRoomStatus { Open, Closed }

/// <summary>
/// A private room. Its media-server name is <see cref="Id"/>; <see cref="PublicId"/> is what links
/// and pages show, and knowing it opens nothing. Closed rooms keep their row: a room closed by staff
/// stays closed for its owner too.
/// </summary>
public sealed class VoiceRoom
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public string PublicId { get; set; } = "";
    public Guid OwnerId { get; set; }
    public PortalUser? Owner { get; set; }
    public string Title { get; set; } = "";
    public VoiceRoomStatus Status { get; set; } = VoiceRoomStatus.Open;
    public int Capacity { get; set; }
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
    public DateTimeOffset? ClosedAt { get; set; }
    /// <summary>Who closed it; a room closed by someone other than its owner is staff's decision and only staff reopen it.</summary>
    public Guid? ClosedById { get; set; }
    public string? ClosedReason { get; set; }
}

public enum RoomInviteStatus { Active, Declined, Revoked }

public sealed class RoomInvite
{
    public Guid RoomId { get; set; }
    public Guid UserId { get; set; }
    public RoomInviteStatus Status { get; set; } = RoomInviteStatus.Active;
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
    public DateTimeOffset UpdatedAt { get; set; } = DateTimeOffset.UtcNow;
}

/// <summary>Shut out of one room until its owner lets the person back.</summary>
public sealed class RoomBan
{
    public Guid RoomId { get; set; }
    public Guid UserId { get; set; }
    public Guid? ById { get; set; }
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
}

/// <summary>May listen but not talk. Kept across reconnects: every pass is issued without the right to publish.</summary>
public sealed class RoomSpeakingRestriction
{
    public Guid RoomId { get; set; }
    public Guid UserId { get; set; }
    public bool Restricted { get; set; }
    public DateTimeOffset UpdatedAt { get; set; } = DateTimeOffset.UtcNow;
}

/// <summary>No voice anywhere for this account. Only a SuperAdmin sets or lifts it; one active row per account.</summary>
public sealed class VoiceAccountBan
{
    public long Id { get; set; }
    public Guid UserId { get; set; }
    public Guid? ById { get; set; }
    public string Reason { get; set; } = "";
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
    public DateTimeOffset? LiftedAt { get; set; }
    public Guid? LiftedById { get; set; }
}

/// <summary>
/// The voice log: who came and went, and every action of an owner or of staff, with its reason.
/// Never any sound. Kept 30 days for comings and goings, 365 for actions, longer while a complaint holds it.
/// </summary>
public sealed class VoiceEvent
{
    public long Id { get; set; }
    public Guid? RoomId { get; set; }
    public Guid UserId { get; set; }
    public Guid? ActorId { get; set; }
    public string Kind { get; set; } = "";
    public string? Reason { get; set; }
    public DateTimeOffset At { get; set; } = DateTimeOffset.UtcNow;
}

/// <summary>A log record a complaint rests on: kept while the ticket is open and a year after it closes.</summary>
public sealed class VoiceEventTicket
{
    public long EventId { get; set; }
    public Guid TicketId { get; set; }
}

public enum VoiceJobKind { Remove, SetPublish, CloseRoom }

/// <summary>
/// A command for the media server that must not be lost: written in the same transaction as the
/// decision behind it, tried at once, and retried by the worker until the server confirms.
/// Room and user are plain ids, not keys: a room deleted a moment ago still has people to disconnect.
/// </summary>
public sealed class VoiceJob
{
    public long Id { get; set; }
    public VoiceJobKind Kind { get; set; }
    public Guid RoomId { get; set; }
    public Guid? UserId { get; set; }
    /// <summary>For somebody in a room who is not one of our users at all: the media server's identity to disconnect.</summary>
    public string? Identity { get; set; }
    public bool CanPublish { get; set; }
    public JobState State { get; set; } = JobState.Pending;
    public int Attempts { get; set; }
    public DateTimeOffset NextAttemptAt { get; set; } = DateTimeOffset.UtcNow;
    public string? LastError { get; set; }
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
    public DateTimeOffset? DoneAt { get; set; }
}

public static class VoiceEventKinds
{
    public const string Join = "join";
    public const string Leave = "leave";
    public const string Invite = "invite";
    public const string Revoke = "revoke";
    public const string Mute = "mute";
    public const string Unmute = "unmute";
    public const string Kick = "kick";
    public const string Ban = "ban";
    public const string Unban = "unban";
    /// <summary>Somebody got into the room whom the site no longer lets in, and was taken out again.</summary>
    public const string Ejected = "ejected";
    public const string Close = "close";
    public const string Reopen = "reopen";
    public const string AccountBan = "account_ban";
    public const string AccountUnban = "account_unban";
    public const string Unfriend = "unfriend";
    public const string Block = "block";
    /// <summary>Comings and goings: the short-lived part of the log.</summary>
    public static readonly string[] Presence = [Join, Leave];
}

public static class VoiceLimits
{
    public const int TitleMax = 80;
    public const int ReasonMax = 500;
    public const int PublicIdLength = 10;
    public const int RoomsPerOwner = 5;
    public const int InvitesPerRoom = 100;
    public const int Friends = 500;
    public const int PendingOutgoing = 50;
    public const int RequestsPerDay = 30;
    public const int Blocks = 500;
    public static readonly TimeSpan PresenceKeep = TimeSpan.FromDays(30);
    public static readonly TimeSpan ActionKeep = TimeSpan.FromDays(365);
    public static readonly TimeSpan ComplaintKeep = TimeSpan.FromDays(365);
    /// <summary>How far back a complaint reaches into the log of its room and person.</summary>
    public static readonly TimeSpan ComplaintLookback = TimeSpan.FromDays(30);
}
