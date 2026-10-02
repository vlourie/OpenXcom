using System.ComponentModel.DataAnnotations;
using System.Security.Claims;
using System.Text.Json;
using Microsoft.AspNetCore.Mvc;
using Xp.Portal.Data;
using Xp.Portal.Devices;

namespace Xp.Portal.Voice;

public sealed record FriendRequestBody([property: Required, StringLength(256)] string Who);
public sealed record FriendRequestResult(string Result);
public sealed record RoomsResponse(IReadOnlyList<RoomSummary> Owned, IReadOnlyList<RoomSummary> Invited);
public sealed record CreateRoomBody([property: Required, StringLength(VoiceLimits.TitleMax)] string Title);
public sealed record ReasonBody([property: StringLength(VoiceLimits.ReasonMax)] string? Reason);
public sealed record InviteBody(Guid User);
public sealed record SpeakingBody(bool Allowed, [property: StringLength(VoiceLimits.ReasonMax)] string? Reason);
public sealed record ComplaintBody(Guid User, [property: Required, StringLength(2000)] string Text);
public sealed record ComplaintResult(long Number, string DisplayNumber);

/// <summary>
/// Friends and voice rooms for the launcher (docs/portal/VOICE_CHAT.md, section 7). The launcher
/// speaks with its device token; a signed-in browser may read with its session, but changes from a
/// browser go through the site's pages, which carry their antiforgery token. Every rule is in
/// <see cref="VoiceService"/>; this file only translates HTTP.
/// </summary>
public static class VoiceApi
{
    public static void Map(IEndpointRouteBuilder app)
    {
        var api = app.MapGroup("/api/v1").WithTags("voice").DisableAntiforgery();

        api.MapGet("/friends", FriendsAsync).RequireRateLimiting("api-read").Produces<FriendsView>().Auth();
        api.MapPost("/friends/requests", RequestAsync).RequireRateLimiting("voice-write").Produces<FriendRequestResult>().Write();
        api.MapPost("/friends/requests/{id:guid}/accept", (Guid id, HttpContext h, VoiceService v, PortalDb db, TimeProvider c, CancellationToken ct) =>
            Run(h, db, c, true, me => v.AcceptAsync(me, id, ct), ct)).RequireRateLimiting("voice-write").Write(204);
        api.MapPost("/friends/requests/{id:guid}/decline", (Guid id, HttpContext h, VoiceService v, PortalDb db, TimeProvider c, CancellationToken ct) =>
            Run(h, db, c, true, me => v.DeclineAsync(me, id, ct), ct)).RequireRateLimiting("voice-write").Write(204);
        api.MapDelete("/friends/requests/{id:guid}", (Guid id, HttpContext h, VoiceService v, PortalDb db, TimeProvider c, CancellationToken ct) =>
            Run(h, db, c, true, me => v.CancelRequestAsync(me, id, ct), ct)).RequireRateLimiting("voice-write").Write(204);
        api.MapDelete("/friends/{user:guid}", (Guid user, HttpContext h, VoiceService v, PortalDb db, TimeProvider c, CancellationToken ct) =>
            Run(h, db, c, true, me => v.UnfriendAsync(me, user, ct), ct)).RequireRateLimiting("voice-write").Write(204);
        api.MapPut("/blocks/{user:guid}", (Guid user, HttpContext h, VoiceService v, PortalDb db, TimeProvider c, CancellationToken ct) =>
            Run(h, db, c, true, me => v.BlockAsync(me, user, ct), ct)).RequireRateLimiting("voice-write").Write(204);
        api.MapDelete("/blocks/{user:guid}", (Guid user, HttpContext h, VoiceService v, PortalDb db, TimeProvider c, CancellationToken ct) =>
            Run(h, db, c, true, me => v.UnblockAsync(me, user, ct), ct)).RequireRateLimiting("voice-write").Write(204);

        var rooms = api.MapGroup("/voice/rooms");
        rooms.MapGet("", RoomsAsync).RequireRateLimiting("api-read").Produces<RoomsResponse>().Auth();
        rooms.MapPost("", CreateRoomAsync).RequireRateLimiting("voice-write").Produces<RoomSummary>(StatusCodes.Status201Created).Write();
        rooms.MapGet("/{room}", RoomAsync).RequireRateLimiting("api-read").Produces<RoomView>().Auth();
        rooms.MapDelete("/{room}", (string room, HttpContext h, VoiceService v, PortalDb db, TimeProvider c, CancellationToken ct) =>
            Run(h, db, c, true, me => v.DeleteRoomAsync(me, room, ct), ct)).RequireRateLimiting("voice-write").Write(204);
        rooms.MapPost("/{room}/close", (string room, ReasonBody? b, HttpContext h, VoiceService v, PortalDb db, TimeProvider c, CancellationToken ct) =>
            Run(h, db, c, true, me => v.CloseRoomAsync(me, room, b?.Reason, staff: false, ct), ct)).RequireRateLimiting("voice-write").Write(204);
        rooms.MapPost("/{room}/reopen", (string room, HttpContext h, VoiceService v, PortalDb db, TimeProvider c, CancellationToken ct) =>
            Run(h, db, c, true, me => v.ReopenRoomAsync(me, room, staff: false, ct), ct)).RequireRateLimiting("voice-write").Write(204);
        rooms.MapPost("/{room}/pass", PassAsync).RequireRateLimiting("voice-pass").Produces<PassView>().Write()
            .ProducesProblem(StatusCodes.Status409Conflict).ProducesProblem(StatusCodes.Status503ServiceUnavailable);
        rooms.MapGet("/{room}/live", LiveAsync).RequireRateLimiting("api-read").Produces<IReadOnlyList<LiveView>>().Auth()
            .ProducesProblem(StatusCodes.Status503ServiceUnavailable);
        rooms.MapPost("/{room}/invites", (string room, InviteBody b, HttpContext h, VoiceService v, PortalDb db, TimeProvider c, CancellationToken ct) =>
            Run(h, db, c, true, me => v.InviteAsync(me, room, b.User, ct), ct)).RequireRateLimiting("voice-write").Write(204);
        rooms.MapDelete("/{room}/invites/{user:guid}", (string room, Guid user, string? reason, HttpContext h, VoiceService v, PortalDb db, TimeProvider c, CancellationToken ct) =>
            Run(h, db, c, true, me => v.RevokeAsync(me, room, user, reason, ct), ct)).RequireRateLimiting("voice-write").Write(204);
        rooms.MapPost("/{room}/decline", (string room, HttpContext h, VoiceService v, PortalDb db, TimeProvider c, CancellationToken ct) =>
            Run(h, db, c, true, me => v.DeclineInviteAsync(me, room, ct), ct)).RequireRateLimiting("voice-write").Write(204);
        rooms.MapPost("/{room}/members/{user:guid}/kick", (string room, Guid user, ReasonBody? b, HttpContext h, VoiceService v, PortalDb db, TimeProvider c, CancellationToken ct) =>
            Run(h, db, c, true, me => v.KickAsync(me, room, user, b?.Reason, ct), ct)).RequireRateLimiting("voice-write").Write(204);
        rooms.MapPost("/{room}/members/{user:guid}/ban", (string room, Guid user, ReasonBody? b, HttpContext h, VoiceService v, PortalDb db, TimeProvider c, CancellationToken ct) =>
            Run(h, db, c, true, me => v.BanAsync(me, room, user, b?.Reason, ct), ct)).RequireRateLimiting("voice-write").Write(204);
        rooms.MapDelete("/{room}/bans/{user:guid}", (string room, Guid user, HttpContext h, VoiceService v, PortalDb db, TimeProvider c, CancellationToken ct) =>
            Run(h, db, c, true, me => v.UnbanAsync(me, room, user, ct), ct)).RequireRateLimiting("voice-write").Write(204);
        rooms.MapPut("/{room}/members/{user:guid}/speaking", (string room, Guid user, SpeakingBody b, HttpContext h, VoiceService v, PortalDb db, TimeProvider c, CancellationToken ct) =>
            Run(h, db, c, true, me => v.SetSpeakingAsync(me, room, user, b.Allowed, b.Reason, ct), ct)).RequireRateLimiting("voice-write").Write(204);
        rooms.MapPost("/{room}/complaints", ComplainAsync).RequireRateLimiting("tickets-create").Produces<ComplaintResult>(StatusCodes.Status201Created).Write();

        // the media server's side: signed with the API secret, not a person
        api.MapPost("/voice/webhook", WebhookAsync).ExcludeFromDescription();
    }

    static RouteHandlerBuilder Auth(this RouteHandlerBuilder b) =>
        b.ProducesProblem(StatusCodes.Status401Unauthorized).ProducesProblem(StatusCodes.Status404NotFound).ProducesProblem(StatusCodes.Status429TooManyRequests);

    static RouteHandlerBuilder Write(this RouteHandlerBuilder b, int? ok = null)
    {
        if (ok is { } status) b.Produces(status);
        return b.Auth().ProducesProblem(StatusCodes.Status400BadRequest).ProducesProblem(StatusCodes.Status403Forbidden)
            .ProducesProblem(StatusCodes.Status409Conflict);
    }

    /// <summary>
    /// Who is asking: the launcher's device token, or for reading only a signed-in browser session.
    /// Changes through the session would bypass the antiforgery check of the site's forms, so they are not taken.
    /// </summary>
    static async Task<Guid?> WhoAsync(HttpContext http, PortalDb db, TimeProvider clock, bool write, CancellationToken ct)
    {
        http.Response.Headers.CacheControl = "no-store";
        var token = http.Request.Headers[DeviceApi.TokenHeader].ToString();
        if (token.Length > 0) return (await DeviceApi.AuthenticateAsync(db, token, clock, ct))?.UserId;
        if (!write && http.User.Identity?.IsAuthenticated == true && Guid.TryParse(http.User.FindFirstValue(ClaimTypes.NameIdentifier), out var id))
            return id;
        return null;
    }

    static async Task<IResult> Run(HttpContext http, PortalDb db, TimeProvider clock, bool write, Func<Guid, Task> act, CancellationToken ct)
    {
        if (await WhoAsync(http, db, clock, write, ct) is not { } me) return Unauthorized();
        try { await act(me); return Results.NoContent(); }
        catch (VoiceException e) { return Problem(e); }
    }

    static async Task<IResult> Answer<T>(HttpContext http, PortalDb db, TimeProvider clock, bool write, Func<Guid, Task<T>> act, CancellationToken ct)
    {
        if (await WhoAsync(http, db, clock, write, ct) is not { } me) return Unauthorized();
        try { return Results.Ok(await act(me)); }
        catch (VoiceException e) { return Problem(e); }
    }

    static Task<IResult> FriendsAsync(int? page, HttpContext h, VoiceService v, PortalDb db, TimeProvider c, CancellationToken ct) =>
        Answer(h, db, c, false, me => v.FriendsAsync(me, Math.Max(1, page ?? 1), 100, ct), ct);

    static Task<IResult> RequestAsync(FriendRequestBody b, HttpContext h, VoiceService v, PortalDb db, TimeProvider c, CancellationToken ct) =>
        Answer(h, db, c, true, async me => new FriendRequestResult(await v.RequestAsync(me, await v.FindPersonAsync(b.Who, ct), ct)), ct);

    static Task<IResult> RoomsAsync(HttpContext h, VoiceService v, PortalDb db, TimeProvider c, CancellationToken ct) =>
        Answer(h, db, c, false, async me => { var (owned, invited) = await v.RoomsAsync(me, ct); return new RoomsResponse(owned, invited); }, ct);

    static async Task<IResult> CreateRoomAsync(CreateRoomBody b, HttpContext h, VoiceService v, PortalDb db, TimeProvider c, CancellationToken ct)
    {
        if (await WhoAsync(h, db, c, true, ct) is not { } me) return Unauthorized();
        try
        {
            var room = await v.CreateRoomAsync(me, b.Title, ct);
            return Results.Created($"/api/v1/voice/rooms/{room.PublicId}", room);
        }
        catch (VoiceException e) { return Problem(e); }
    }

    static Task<IResult> RoomAsync(string room, HttpContext h, VoiceService v, PortalDb db, TimeProvider c, CancellationToken ct) =>
        Answer(h, db, c, false, me => v.RoomViewAsync(me, room, ct), ct);

    static Task<IResult> PassAsync(string room, HttpContext h, VoiceService v, PortalDb db, TimeProvider c, CancellationToken ct) =>
        Answer(h, db, c, true, me => v.PassAsync(me, room, ct), ct);

    static Task<IResult> LiveAsync(string room, HttpContext h, VoiceService v, PortalDb db, TimeProvider c, CancellationToken ct) =>
        Answer(h, db, c, false, me => v.LiveAsync(me, room, ct), ct);

    static async Task<IResult> ComplainAsync(string room, ComplaintBody b, HttpContext h, VoiceService v, PortalDb db, TimeProvider c, CancellationToken ct)
    {
        if (await WhoAsync(h, db, c, true, ct) is not { } me) return Unauthorized();
        try
        {
            var t = await v.ComplainAsync(me, room, b.User, b.Text, ct);
            return Results.Created($"/t/{t.Number}", new ComplaintResult(t.Number, t.DisplayNumber));
        }
        catch (VoiceException e) { return Problem(e); }
    }

    /// <summary>
    /// LiveKit tells who came in and who left. The body is read raw: the signature covers its exact
    /// bytes. Anything unsigned or signed with another key is a 401 and nothing else.
    /// </summary>
    static async Task<IResult> WebhookAsync(HttpContext http, LiveKitTokens tokens, VoiceService v, ILogger<VoiceService> log, CancellationToken ct)
    {
        using var buffer = new MemoryStream();
        await http.Request.Body.CopyToAsync(buffer, ct);
        if (buffer.Length > 64 * 1024) return Results.StatusCode(StatusCodes.Status413PayloadTooLarge);
        var body = buffer.ToArray();
        if (!tokens.WebhookValid(http.Request.Headers.Authorization.ToString(), body)) return Results.Unauthorized();
        string? kind, room, identity;
        bool canPublish;
        try
        {
            using var doc = JsonDocument.Parse(body);
            var root = doc.RootElement;
            kind = root.TryGetProperty("event", out var e) ? e.GetString() : null;
            room = root.TryGetProperty("room", out var r) && r.TryGetProperty("name", out var n) ? n.GetString() : null;
            var p = root.TryGetProperty("participant", out var pp) ? pp : default;
            identity = p.ValueKind == JsonValueKind.Object && p.TryGetProperty("identity", out var i) ? i.GetString() : null;
            canPublish = p.ValueKind == JsonValueKind.Object && p.TryGetProperty("permission", out var perm)
                && (perm.TryGetProperty("canPublish", out var cp) || perm.TryGetProperty("can_publish", out cp)) && cp.ValueKind == JsonValueKind.True;
        }
        catch (JsonException) { return Results.BadRequest(); }
        if (room is null || identity is null) return Results.Ok();
        switch (kind)
        {
            case "participant_joined":
                await v.RecheckAsync(room, identity, canPublish, joined: true, ct);
                break;
            case "participant_left":
                await v.LeftAsync(room, identity, ct);
                break;
        }
        return Results.Ok();
    }

    static IResult Unauthorized() => Results.Problem(detail: "sign in on the site and link the launcher", statusCode: 401,
        extensions: new Dictionary<string, object?> { ["code"] = "device_unknown" });

    static IResult Problem(VoiceException e) =>
        Results.Problem(detail: e.Code, statusCode: e.Status, extensions: new Dictionary<string, object?> { ["code"] = e.Code });
}
