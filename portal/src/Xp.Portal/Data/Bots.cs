namespace Xp.Portal.Data;

/// <summary>
/// A key for the team's own automation (pulling tickets, moving them into work, writing to the player).
/// It acts as its own account <see cref="UserId"/> - a user nobody can sign in as - so every change shows
/// in the ticket's history under the bot's name. We keep only the key's SHA-256, like a device token.
/// The key is not a staff sign-in: it opens only /api/v1/bot, and only the categories it was given.
/// </summary>
public sealed class BotKey
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public Guid UserId { get; set; }
    public PortalUser? User { get; set; }
    public string TokenHash { get; set; } = "";
    public string Name { get; set; } = "";
    /// <summary>Ticket categories, comma-separated ("code,graphics"). Voice complaints only when named.</summary>
    public string Categories { get; set; } = "";
    /// <summary>Addresses the key works from, comma-separated CIDR ("203.0.113.7/32"); empty - any.</summary>
    public string Networks { get; set; } = "";
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
    public DateTimeOffset? LastUsedAt { get; set; }
    public string? LastIp { get; set; }
    public DateTimeOffset? RevokedAt { get; set; }

    public bool Active => RevokedAt is null;
}

public static class BotLimits
{
    public const int NameMax = 64;
    public const int ListMax = 256;
    /// <summary>The bot account's address: a reserved domain, so no letter can ever reach anyone.</summary>
    public const string EmailDomain = "bot.invalid";
}
