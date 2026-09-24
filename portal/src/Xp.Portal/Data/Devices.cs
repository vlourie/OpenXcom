namespace Xp.Portal.Data;

/// <summary>
/// A launcher allowed to act for an account. The launcher keeps the secret, we keep only its
/// SHA-256 — the same way a guest's ticket link is kept, so a stolen database hands nobody a
/// working device. The name is what the launcher calls itself ("Лаунчер 0.1.1"): never the
/// machine's name, because a name like that is personal data we have no reason to hold.
/// </summary>
public sealed class DeviceToken
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public Guid UserId { get; set; }
    public PortalUser? User { get; set; }
    public string TokenHash { get; set; } = "";
    public string Name { get; set; } = "";
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
    public DateTimeOffset? LastUsedAt { get; set; }
    public DateTimeOffset? RevokedAt { get; set; }

    public bool Active => RevokedAt is null;
}

/// <summary>
/// The short code a person reads off the launcher and confirms on the site. It lives ten minutes
/// and is spent once. The secret of the exchange is not the code — it is <see cref="DeviceId"/>,
/// which only the launcher knows and by which it asks whether the code was confirmed yet.
/// </summary>
public sealed class DeviceLinkCode
{
    /// <summary>Six letters and digits without look-alikes, shown as XXX-XXX.</summary>
    public string Code { get; set; } = "";
    public Guid DeviceId { get; set; } = Guid.NewGuid();
    public string Name { get; set; } = "";
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
    public DateTimeOffset ExpiresAt { get; set; }
    public Guid? ConsumedByUserId { get; set; }
    public DateTimeOffset? ConsumedAt { get; set; }
    /// <summary>The device row made when the launcher came for its token; the token goes out once.</summary>
    public Guid? IssuedTokenId { get; set; }
}

public static class DeviceLimits
{
    public const int CodeMax = 8;
    public const int NameMax = 64;
    /// <summary>How long a code is worth confirming. Long enough to find the browser, short enough to guess nothing.</summary>
    public static readonly TimeSpan CodeLife = TimeSpan.FromMinutes(10);
}
