namespace Xp.Portal.Data;

// Private messages between registered people: plain text, one row per message. Nothing here is
// visible to staff on its own; a message reaches staff only inside a complaint (a ticket of the
// voice category carries a copy of the dialogue as it stood).

/// <summary>
/// One message. Each side deletes it for itself (<see cref="SenderDeleted"/>, <see cref="RecipientDeleted"/>);
/// the row goes when both have. <see cref="ReadAt"/> is set when the recipient opens the dialogue.
/// </summary>
public sealed class PrivateMessage
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public Guid SenderId { get; set; }
    public Guid RecipientId { get; set; }
    public string Body { get; set; } = "";
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
    public DateTimeOffset? ReadAt { get; set; }
    public bool SenderDeleted { get; set; }
    public bool RecipientDeleted { get; set; }
}

/// <summary>A person's message settings. No row means the defaults: no e-mail about new messages.</summary>
public sealed class MessageSetting
{
    public Guid UserId { get; set; }
    public bool EmailNotice { get; set; }
    public DateTimeOffset UpdatedAt { get; set; } = DateTimeOffset.UtcNow;
}

public static class MessageLimits
{
    public const int BodyMax = 4000;
    public const int ComplaintMax = 2000;
    public const int PerPage = 50;
    public const int DialoguesMax = 200;
    /// <summary>Sent by one person in ten minutes, and in a day.</summary>
    public const int PerTenMinutes = 30;
    public const int PerDay = 300;
    /// <summary>Messages in a row to somebody who has not written back: a friend may be sent more than a stranger.</summary>
    public const int UnansweredFriend = 20;
    public const int UnansweredStranger = 3;
    /// <summary>Strangers (neither a friend nor anybody who ever wrote to me) one person may start a dialogue with in a day.</summary>
    public const int StrangersPerDay = 10;
    /// <summary>Complaints about messages one person may file in a day.</summary>
    public const int ComplaintsPerDay = 10;
    /// <summary>How much of the dialogue a complaint carries: the newest messages, up to this many characters in all.</summary>
    public const int ComplaintContextMessages = 30;
    public const int ComplaintContextChars = 12_000;
}
