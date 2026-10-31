using System.ComponentModel.DataAnnotations;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Xp.Portal.Auth;
using Xp.Portal.Data;
using Xp.Portal.Site;

namespace Xp.Portal.Devices;

public sealed record LinkRequest([property: StringLength(DeviceLimits.NameMax)] string? Name);

/// <summary>What the launcher shows the person: the code, and how long it is worth waiting.</summary>
public sealed record LinkResponse(string Code, Guid DeviceId, int ExpiresIn);

/// <summary>
/// The answer to "was it confirmed yet": pending, linked or expired. The token comes exactly once,
/// on the first ask after confirmation — it is never stored in the clear, so it cannot come twice.
/// </summary>
public sealed record LinkStatusResponse(string Status, string? Token, string? Account);

public sealed record DeviceResponse(string Account, string Name, DateTimeOffset LinkedAt);

/// <summary>
/// Linking a launcher to an account. The password is never typed into the launcher: the launcher
/// shows a code, the person confirms it on the site while already signed in, and the launcher gets
/// a device token of its own. Losing it costs one revocation, not the account.
/// </summary>
public static class DeviceApi
{
    public const string TokenHeader = "X-Device-Token";

    public static void Map(IEndpointRouteBuilder app)
    {
        var api = app.MapGroup("/api/v1").WithTags("devices").DisableAntiforgery();

        api.MapPost("/devices/link", StartAsync).RequireRateLimiting("devices")
            .Produces<LinkResponse>(StatusCodes.Status201Created).ProducesProblem(StatusCodes.Status429TooManyRequests);
        api.MapGet("/devices/{deviceId:guid}", StatusAsync).RequireRateLimiting("api-read")
            .Produces<LinkStatusResponse>().ProducesProblem(StatusCodes.Status404NotFound).ProducesProblem(StatusCodes.Status429TooManyRequests);
        api.MapGet("/devices/me", MeAsync).RequireRateLimiting("api-read")
            .Produces<DeviceResponse>().ProducesProblem(StatusCodes.Status401Unauthorized).ProducesProblem(StatusCodes.Status429TooManyRequests);
        api.MapDelete("/devices/me", ForgetAsync).RequireRateLimiting("devices")
            .Produces(StatusCodes.Status204NoContent).ProducesProblem(StatusCodes.Status401Unauthorized).ProducesProblem(StatusCodes.Status429TooManyRequests);
    }

    static async Task<IResult> StartAsync(LinkRequest req, PortalDb db, TimeProvider clock, CancellationToken ct)
    {
        var now = clock.GetUtcNow();
        // spent and forgotten codes are swept here, so nothing has to run on a timer for them
        await db.DeviceLinkCodes.Where(c => c.ExpiresAt < now.AddDays(-1)).ExecuteDeleteAsync(ct);

        var name = (req.Name ?? "").Trim();
        if (name.Length > DeviceLimits.NameMax) name = name[..DeviceLimits.NameMax];
        var code = new DeviceLinkCode
        {
            Code = await FreeCodeAsync(db, ct),
            Name = name,
            CreatedAt = now,
            ExpiresAt = now + DeviceLimits.CodeLife,
        };
        db.DeviceLinkCodes.Add(code);
        await db.SaveChangesAsync(ct);
        return Results.Created($"/api/v1/devices/{code.DeviceId}",
            new LinkResponse(DeviceSecrets.Format(code.Code), code.DeviceId, (int)DeviceLimits.CodeLife.TotalSeconds));
    }

    static async Task<string> FreeCodeAsync(PortalDb db, CancellationToken ct)
    {
        // a live code is unique; a collision is one chance in a billion, and retrying is cheaper than caring
        for (int i = 0; i < 5; i++)
        {
            var code = DeviceSecrets.NewCode();
            if (!await db.DeviceLinkCodes.AnyAsync(c => c.Code == code, ct)) return code;
        }
        throw new InvalidOperationException("cannot find a free link code");
    }

    static async Task<IResult> StatusAsync(Guid deviceId, HttpContext http, PortalDb db, TimeProvider clock, CancellationToken ct)
    {
        http.Response.Headers.CacheControl = "no-store";
        var code = await db.DeviceLinkCodes.FirstOrDefaultAsync(c => c.DeviceId == deviceId, ct);
        if (code is null) return Problem("not_found", "no such link request", 404);
        var now = clock.GetUtcNow();

        if (code.ConsumedByUserId is not { } userId)
            return Results.Ok(new LinkStatusResponse(code.ExpiresAt <= now ? "expired" : "pending", null, null));

        var user = await db.Users.FirstOrDefaultAsync(u => u.Id == userId, ct);
        var account = user is null ? "" : Display(user);
        if (code.IssuedTokenId is not null) return Results.Ok(new LinkStatusResponse("linked", null, account));

        var secret = DeviceSecrets.NewToken();
        var device = new DeviceToken
        {
            UserId = userId,
            TokenHash = DeviceSecrets.Hash(secret),
            Name = code.Name,
            CreatedAt = now,
        };
        db.DeviceTokens.Add(device);
        await db.SaveChangesAsync(ct);
        // two launchers asking at once must not both get a token: the row is claimed by one update
        var claimed = await db.DeviceLinkCodes.Where(c => c.Code == code.Code && c.IssuedTokenId == null)
            .ExecuteUpdateAsync(s => s.SetProperty(c => c.IssuedTokenId, device.Id), ct);
        if (claimed == 0)
        {
            db.DeviceTokens.Remove(device);
            await db.SaveChangesAsync(ct);
            return Results.Ok(new LinkStatusResponse("linked", null, account));
        }
        return Results.Ok(new LinkStatusResponse("linked", secret, account));
    }

    static async Task<IResult> MeAsync([FromHeader(Name = TokenHeader)] string? token, HttpContext http, PortalDb db, TimeProvider clock, CancellationToken ct)
    {
        var device = await AuthenticateAsync(db, token, clock, ct);
        if (device is null) return Unauthorized();
        http.Response.Headers.CacheControl = "no-store";
        var user = await db.Users.FirstAsync(u => u.Id == device.UserId, ct);
        return Results.Ok(new DeviceResponse(Display(user), device.Name, device.CreatedAt));
    }

    static async Task<IResult> ForgetAsync([FromHeader(Name = TokenHeader)] string? token, PortalDb db, TimeProvider clock, Audit audit, CancellationToken ct)
    {
        var device = await AuthenticateAsync(db, token, clock, ct);
        if (device is null) return Unauthorized();
        device.RevokedAt = clock.GetUtcNow();
        audit.Add(device.UserId, "device.revoke", device.Id.ToString(), "by the launcher itself");
        await db.SaveChangesAsync(ct);
        return Results.NoContent();
    }

    /// <summary>
    /// Who is behind <c>X-Device-Token</c>, or null. The token is found by the hash of what came in,
    /// so a wrong token is one failed lookup and nothing else; a revoked one never matches again.
    /// </summary>
    public static async Task<DeviceToken?> AuthenticateAsync(PortalDb db, string? token, TimeProvider clock, CancellationToken ct)
    {
        if (token is null || token.Length is < 16 or > 128) return null;
        var hash = DeviceSecrets.Hash(token);
        var device = await db.DeviceTokens.FirstOrDefaultAsync(d => d.TokenHash == hash && d.RevokedAt == null, ct);
        if (device is null) return null;
        var now = clock.GetUtcNow();
        // "last used" is for the person reading the list, not a log: one write an hour is enough
        if (device.LastUsedAt is null || now - device.LastUsedAt > TimeSpan.FromHours(1))
        {
            device.LastUsedAt = now;
            await db.SaveChangesAsync(ct);
        }
        return device;
    }

    /// <summary>The name shown in the launcher: what the person chose, never their address.</summary>
    public static string Display(PortalUser user) =>
        user.DisplayName is { Length: > 0 } name ? name : user.UserName ?? "";

    static IResult Unauthorized() => Problem("device_unknown", "the device token is unknown or revoked", 401);

    static IResult Problem(string code, string detail, int status) =>
        Results.Problem(detail: detail, statusCode: status, extensions: new Dictionary<string, object?> { ["code"] = code });
}
