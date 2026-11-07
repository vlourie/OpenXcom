using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Caching.Memory;
using Xp.Portal.Data;

namespace Xp.Portal.Stats;

/// <summary>What the launcher says about itself. Everything but the random number may be empty.</summary>
public sealed record StatsPing(string? Install, bool Playing, string? Launcher = null, string? Game = null);

/// <summary>The three numbers of the entrance screen. <c>Hours</c> is whole hours, rounded down.</summary>
public sealed record StatsTotals(int Installs, long Hours, int PlayingNow);

/// <summary>
/// Anonymous statistics of the launcher: how many installations there are, how long they have played
/// and how many play now. The sender is a random number the launcher made up; no address, no name and
/// nothing else personal is read from the request, let alone stored.
/// </summary>
public static class StatsApi
{
    /// <summary>A ping is a few dozen bytes; anything near Kestrel's own 30 MB is not one.</summary>
    public const long BodyLimit = 1024;

    public static void Map(IEndpointRouteBuilder app)
    {
        var api = app.MapGroup("/api/v1").WithTags("stats").DisableAntiforgery();

        // the limit goes in as endpoint metadata for the same reason as in ReviewApi: before the body is bound
        api.MapPost("/stats/ping", PingAsync).RequireRateLimiting("stats-ping")
            .WithMetadata(new RequestSizeLimitAttribute(BodyLimit))
            .Produces(StatusCodes.Status204NoContent)
            .ProducesProblem(StatusCodes.Status400BadRequest)
            .ProducesProblem(StatusCodes.Status413PayloadTooLarge)
            .ProducesProblem(StatusCodes.Status429TooManyRequests);
        api.MapGet("/stats", async (LauncherStatsService stats, CancellationToken ct) => Results.Ok(await stats.TotalsAsync(ct)))
            .RequireRateLimiting("api-read")
            .Produces<StatsTotals>();
    }

    static async Task<IResult> PingAsync(StatsPing? ping, PortalDb db, TimeProvider clock, CancellationToken ct)
    {
        if (ping is null || LauncherStatsService.NormalizeInstall(ping.Install) is not { } id)
            return Results.Problem(detail: "install must be 32 hexadecimal digits", statusCode: StatusCodes.Status400BadRequest,
                extensions: new Dictionary<string, object?> { ["code"] = "install_invalid" });

        // two pings of one installation at the same moment both find no row and both insert: the second loses
        // on the key, and the retry then finds the first one's row
        for (var attempt = 0; ; attempt++)
        {
            try
            {
                await LauncherStatsService.RecordAsync(db, id, ping, clock.GetUtcNow(), ct);
                return Results.NoContent();
            }
            catch (DbUpdateException) when (attempt == 0)
            {
                db.ChangeTracker.Clear();
            }
        }
    }
}

public sealed class LauncherStatsService(IServiceScopeFactory scopes, IMemoryCache cache, TimeProvider clock)
{
    const string CacheKey = "stats:totals";

    /// <summary>The install number as it is stored (lower case), or null if it is not 32 hex digits.</summary>
    public static string? NormalizeInstall(string? install)
    {
        if (install is null || install.Length != StatsLimits.InstallLength) return null;
        foreach (var c in install)
            if (!Uri.IsHexDigit(c)) return null;
        return install.ToLowerInvariant();
    }

    /// <summary>
    /// Counts the time between two pings as played when both are close enough to be one session. A ping
    /// that says "not playing" still pays for the stretch before it, and then closes the session.
    /// </summary>
    public static async Task RecordAsync(PortalDb db, string id, StatsPing ping, DateTimeOffset now, CancellationToken ct)
    {
        var row = await db.LauncherInstalls.FirstOrDefaultAsync(i => i.Id == id, ct);
        if (row is null)
        {
            row = new LauncherInstall { Id = id, FirstSeen = now };
            db.LauncherInstalls.Add(row);
        }
        if (row.LastPlayingAt is { } last)
        {
            var gap = now - last;
            if (gap >= TimeSpan.Zero && gap <= StatsLimits.PlayWindow) row.PlaySeconds += (long)gap.TotalSeconds;
        }
        row.LastPlayingAt = ping.Playing ? now : null;
        row.LastSeen = now;
        row.LauncherVersion = Cut(ping.Launcher, StatsLimits.LauncherMax);
        row.GameRelease = Cut(ping.Game, StatsLimits.GameMax);
        await db.SaveChangesAsync(ct);
    }

    /// <summary>
    /// The numbers, from memory for a minute: the entrance screen asks on every visit, and a crowd
    /// of visitors must not turn into a crowd of table scans.
    /// </summary>
    public async Task<StatsTotals> TotalsAsync(CancellationToken ct)
    {
        var totals = await cache.GetOrCreateAsync(CacheKey, async e =>
        {
            e.AbsoluteExpirationRelativeToNow = TimeSpan.FromSeconds(60);
            await using var scope = scopes.CreateAsyncScope();
            var db = scope.ServiceProvider.GetRequiredService<PortalDb>();
            var since = clock.GetUtcNow() - StatsLimits.PlayWindow;
            var installs = await db.LauncherInstalls.CountAsync(ct);
            var seconds = await db.LauncherInstalls.SumAsync(i => i.PlaySeconds, ct);
            var playing = await db.LauncherInstalls.CountAsync(i => i.LastPlayingAt != null && i.LastPlayingAt >= since, ct);
            return new StatsTotals(installs, seconds / 3600, playing);
        });
        return totals!;
    }

    static string Cut(string? s, int max)
    {
        s = (s ?? "").Trim();
        return s.Length <= max ? s : s[..max];
    }
}
