using Microsoft.AspNetCore.Identity;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;
using Xp.Portal.Data;

namespace Xp.Portal.Voice;

/// <summary>
/// The public channels every site starts with (docs/portal/VOICE_IRC.md section 2). They are ordinary rooms owned by an
/// account of the site's own that nobody can sign in with, so the owner's powers belong to staff in practice.
/// Run by <c>migrate</c> on every deployment: it adds what is missing and never touches what exists, so a topic changed
/// later stays changed. A channel deleted by hand comes back at the next deployment, so one to be gone is closed instead.
/// </summary>
public static class ChannelSeed
{
    /// <summary>Stable ids of ten characters: the launcher and links may keep them.</summary>
    public static readonly (string PublicId, string Title, string Topic)[] Channels =
    [
        ("ch-general", "#общий", "Общий разговор об X-Piratez. Будьте вежливы."),
        ("ch-english", "#english", "General chat about X-Piratez. Please be polite."),
        ("ch-pomosch", "#помощь", "Вопросы по игре и лаунчеру. Что-то сломалось - напишите и приложите F8."),
    ];

    public const string OwnerEmail = "channels@" + BotLimits.EmailDomain;

    public static async Task<int> EnsureAsync(IServiceProvider sp, CancellationToken ct = default)
    {
        var db = sp.GetRequiredService<PortalDb>();
        var clock = sp.GetRequiredService<TimeProvider>();
        var missing = new List<(string PublicId, string Title, string Topic)>();
        foreach (var c in Channels)
            if (!await db.VoiceRooms.AnyAsync(r => r.PublicId == c.PublicId, ct)) missing.Add(c);
        if (missing.Count == 0) return 0;

        var users = sp.GetRequiredService<UserManager<PortalUser>>();
        var owner = await users.FindByEmailAsync(OwnerEmail);
        if (owner is null)
        {
            // no password, locked for good: the account exists to own rooms and to be named on the lines of the site itself
            owner = new PortalUser { UserName = OwnerEmail, Email = OwnerEmail, EmailConfirmed = false, DisplayName = "X-Piratez", LockoutEnabled = true, LockoutEnd = DateTimeOffset.MaxValue };
            var made = await users.CreateAsync(owner);
            if (!made.Succeeded) throw new InvalidOperationException("cannot create the account that owns the channels: " + string.Join("; ", made.Errors.Select(e => e.Description)));
        }
        var capacity = Math.Clamp(sp.GetRequiredService<IOptions<LiveKitOptions>>().Value.Capacity, 2, 100);
        var now = clock.GetUtcNow();
        // the list goes by CreatedAt: a second apart, so #общий comes first and is the channel /voice opens
        foreach (var (id, title, topic) in missing)
        {
            db.VoiceRooms.Add(new VoiceRoom { PublicId = id, OwnerId = owner.Id, Title = title, Topic = topic, Capacity = capacity, IsPublic = true, CreatedAt = now });
            now = now.AddSeconds(1);
        }
        await db.SaveChangesAsync(ct);
        return missing.Count;
    }
}
