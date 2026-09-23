using Microsoft.AspNetCore.Identity;

namespace Xp.Portal.Data;

public sealed class PortalUser : IdentityUser<Guid>
{
    public string DisplayName { get; set; } = "";
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
    public List<UserPermission> Permissions { get; set; } = new();
}

/// <summary>An admin specialization ("tickets.code", "tickets.graphics", …) granted to one user.</summary>
public sealed class UserPermission
{
    public Guid UserId { get; set; }
    public string Permission { get; set; } = "";
}

public enum TicketStatus { New, Triaged, InProgress, NeedsInfo, Resolved, Closed, Duplicate, Rejected }
public enum TicketPriority { Low, Normal, High, Critical }
public enum TicketSource { Web, F8, Crash }

public sealed class Ticket
{
    public Guid Id { get; set; } = Guid.NewGuid();
    /// <summary>Human number, shown as XP-000123. Knowing it opens nothing by itself.</summary>
    public long Number { get; set; }
    public string Category { get; set; } = "";
    public TicketStatus Status { get; set; } = TicketStatus.New;
    public TicketPriority Priority { get; set; } = TicketPriority.Normal;
    public TicketSource Source { get; set; } = TicketSource.Web;
    public string Title { get; set; } = "";
    public string Description { get; set; } = "";
    public string? Steps { get; set; }
    public string? Expected { get; set; }
    public string? Actual { get; set; }
    public string? GameVersion { get; set; }
    public string? ModVersion { get; set; }
    public string? LauncherVersion { get; set; }
    public Guid? AuthorId { get; set; }
    public PortalUser? Author { get; set; }
    /// <summary>Guests only: the reply address they chose to leave, never shown to other people.</summary>
    public string? GuestEmail { get; set; }
    /// <summary>SHA-256 of the guest's secret link token; the token itself is never stored.</summary>
    public string? GuestTokenHash { get; set; }
    public Guid? AssigneeId { get; set; }
    public PortalUser? Assignee { get; set; }
    public Guid? DuplicateOfId { get; set; }
    public Ticket? DuplicateOf { get; set; }
    /// <summary>SHA-256 of the client's Idempotency-Key, and of the request it came with.</summary>
    public string? IdempotencyKey { get; set; }
    public string? IdempotencyFingerprint { get; set; }
    public string? CorrelationId { get; set; }
    public bool ConsentToFiles { get; set; }
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
    public DateTimeOffset UpdatedAt { get; set; } = DateTimeOffset.UtcNow;
    public List<TicketMessage> Messages { get; set; } = new();
    public List<TicketAttachment> Attachments { get; set; } = new();
    public List<TicketHistory> History { get; set; } = new();

    public string DisplayNumber => FormatNumber(Number);
    public static string FormatNumber(long n) => $"XP-{n:D6}";
}

public sealed class TicketMessage
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public Guid TicketId { get; set; }
    public Guid? AuthorId { get; set; }
    public PortalUser? Author { get; set; }
    /// <summary>Internal notes are visible to staff only.</summary>
    public bool Internal { get; set; }
    public bool FromStaff { get; set; }
    public string Body { get; set; } = "";
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
}

public enum ScanStatus { Pending, Clean, Quarantined, Unscanned }

public sealed class TicketAttachment
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public Guid TicketId { get; set; }
    /// <summary>Generated storage key; the user's file name is never part of it.</summary>
    public string ObjectKey { get; set; } = "";
    /// <summary>Name the user gave, sanitised, for display and Content-Disposition only.</summary>
    public string FileName { get; set; } = "";
    public string ContentType { get; set; } = "";
    public long Size { get; set; }
    public string Sha256 { get; set; } = "";
    public ScanStatus Scan { get; set; } = ScanStatus.Pending;
    public string? ScanDetail { get; set; }
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
}

public sealed class TicketHistory
{
    public long Id { get; set; }
    public Guid TicketId { get; set; }
    public Guid? ActorId { get; set; }
    public string Action { get; set; } = "";
    public string? From { get; set; }
    public string? To { get; set; }
    public DateTimeOffset At { get; set; } = DateTimeOffset.UtcNow;
}

/// <summary>Where the new-ticket notice of one category goes. Managed by SuperAdmin only.</summary>
public sealed class TelegramRoute
{
    public int Id { get; set; }
    /// <summary>Ticket category, or "*" for the default route.</summary>
    public string Category { get; set; } = "*";
    public string ChatId { get; set; } = "";
    public int? ThreadId { get; set; }
    public bool Enabled { get; set; } = true;
}

public enum JobState { Pending, Done, Dead }

public sealed class NotificationJob
{
    public long Id { get; set; }
    public string Kind { get; set; } = "telegram";
    public string ChatId { get; set; } = "";
    public int? ThreadId { get; set; }
    /// <summary>Ready-to-send, already escaped text: the worker never builds text from user data.</summary>
    public string Text { get; set; } = "";
    public JobState State { get; set; } = JobState.Pending;
    public int Attempts { get; set; }
    public DateTimeOffset NextAttemptAt { get; set; } = DateTimeOffset.UtcNow;
    public string? LastError { get; set; }
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
    public DateTimeOffset? DoneAt { get; set; }
}

public sealed class AuditLog
{
    public long Id { get; set; }
    public Guid? ActorId { get; set; }
    public string Action { get; set; } = "";
    public string Target { get; set; } = "";
    public string? Detail { get; set; }
    public DateTimeOffset At { get; set; } = DateTimeOffset.UtcNow;
}
