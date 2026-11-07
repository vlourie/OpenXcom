using System.ComponentModel.DataAnnotations;
using Xp.Portal.Data;
using Xp.Portal.Voice;

namespace Xp.Portal.Messages;

public sealed record UnreadResponse(int Unread);
public sealed record InboxResponse(int Unread, IReadOnlyList<DialogueRow> Dialogues);
public sealed record ThreadResponse(PersonView Person, IReadOnlyList<BubbleView> Messages, int Total, int Page, int PerPage, bool IBlocked, bool Friend);
public sealed record SendBody([property: Required, StringLength(256)] string Who, string? Body);
public sealed record ReplyBody(string? Body);
public sealed record SentResponse(Guid Id, PersonView To, DateTimeOffset At);
public sealed record MessageComplaintBody(Guid? Message, [property: Required, StringLength(MessageLimits.ComplaintMax)] string Text);

/// <summary>
/// Private messages for the launcher (ticket XP-000476): the same dialogues as the site's /me/messages, under
/// the launcher's device token (a signed-in browser may read with its session, as in the voice API). Every
/// rule - rate limits, blocks, the length, the complaint - is in <see cref="MessageService"/>; blocking is
/// the one that friends and voice have already (PUT/DELETE /api/v1/blocks/{user}).
/// </summary>
public static class MessageApi
{
    public static void Map(IEndpointRouteBuilder app)
    {
        var api = app.MapGroup("/api/v1/messages").WithTags("messages").DisableAntiforgery();

        api.MapGet("", (HttpContext h, MessageService m, PortalDb db, TimeProvider c, CancellationToken ct) =>
            Answer(h, db, c, false, async me => new InboxResponse(await m.UnreadAsync(me, ct), await m.InboxAsync(me, ct)), ct))
            .RequireRateLimiting("api-read").Produces<InboxResponse>().Auth();
        api.MapGet("/unread", (HttpContext h, MessageService m, PortalDb db, TimeProvider c, CancellationToken ct) =>
            Answer(h, db, c, false, async me => new UnreadResponse(await m.UnreadAsync(me, ct)), ct))
            .RequireRateLimiting("api-read").Produces<UnreadResponse>().Auth();
        // reading does not mark: the launcher marks (POST .../read) when the dialogue is in front of the person
        api.MapGet("/{user:guid}", (Guid user, int? page, HttpContext h, MessageService m, PortalDb db, TimeProvider c, CancellationToken ct) =>
            Answer(h, db, c, false, async me =>
            {
                if (user == me) throw new MessageException("self", 400);
                var p = Math.Max(1, page ?? 1);
                var t = await m.ThreadAsync(me, user, p, ct, markRead: false);
                return new ThreadResponse(t.Person, t.Messages, t.Total, p, MessageLimits.PerPage, t.IBlocked, t.Friend);
            }, ct)).RequireRateLimiting("api-read").Produces<ThreadResponse>().Auth();
        api.MapPost("/{user:guid}/read", (Guid user, HttpContext h, MessageService m, PortalDb db, TimeProvider c, CancellationToken ct) =>
            Run(h, db, c, me => m.MarkReadAsync(me, user, ct), ct)).RequireRateLimiting("messages-write").Write(204);
        api.MapPost("", (SendBody b, HttpContext h, MessageService m, VoiceService v, PortalDb db, TimeProvider c, CancellationToken ct) =>
            Sent(h, db, c, async me => await m.SendAsync(me, await v.FindPersonAsync(b.Who, ct), b.Body, ct), ct))
            .RequireRateLimiting("messages-write").Produces<SentResponse>(StatusCodes.Status201Created).Write();
        api.MapPost("/{user:guid}", (Guid user, ReplyBody b, HttpContext h, MessageService m, PortalDb db, TimeProvider c, CancellationToken ct) =>
            Sent(h, db, c, me => m.SendAsync(me, user, b.Body, ct), ct))
            .RequireRateLimiting("messages-write").Produces<SentResponse>(StatusCodes.Status201Created).Write();
        api.MapPost("/{user:guid}/complaints", (Guid user, MessageComplaintBody b, HttpContext h, MessageService m, PortalDb db, TimeProvider c, CancellationToken ct) =>
            Answer(h, db, c, true, async me =>
            {
                var t = await m.ComplainAsync(me, user, b.Message, b.Text, ct);
                return new ComplaintResult(t.Number, t.DisplayNumber);
            }, ct, created: true)).RequireRateLimiting("tickets-create").Produces<ComplaintResult>(StatusCodes.Status201Created).Write();
    }

    static RouteHandlerBuilder Auth(this RouteHandlerBuilder b) =>
        b.ProducesProblem(StatusCodes.Status401Unauthorized).ProducesProblem(StatusCodes.Status404NotFound).ProducesProblem(StatusCodes.Status429TooManyRequests);

    static RouteHandlerBuilder Write(this RouteHandlerBuilder b, int? ok = null)
    {
        if (ok is { } status) b.Produces(status);
        return b.Auth().ProducesProblem(StatusCodes.Status400BadRequest).ProducesProblem(StatusCodes.Status403Forbidden)
            .ProducesProblem(StatusCodes.Status409Conflict);
    }

    static async Task<IResult> Answer<T>(HttpContext http, PortalDb db, TimeProvider clock, bool write, Func<Guid, Task<T>> act, CancellationToken ct, bool created = false)
    {
        if (await VoiceApi.WhoAsync(http, db, clock, write, ct) is not { } me) return Unauthorized();
        try
        {
            var result = await act(me);
            return created ? Results.Json(result, statusCode: StatusCodes.Status201Created) : Results.Ok(result);
        }
        catch (MessageException e) { return Problem(e.Code, e.Status); }
        catch (VoiceException e) { return Problem(e.Code, e.Status); }
    }

    static async Task<IResult> Run(HttpContext http, PortalDb db, TimeProvider clock, Func<Guid, Task> act, CancellationToken ct)
    {
        if (await VoiceApi.WhoAsync(http, db, clock, true, ct) is not { } me) return Unauthorized();
        try { await act(me); return Results.NoContent(); }
        catch (MessageException e) { return Problem(e.Code, e.Status); }
        catch (VoiceException e) { return Problem(e.Code, e.Status); }
    }

    static Task<IResult> Sent(HttpContext http, PortalDb db, TimeProvider clock, Func<Guid, Task<PrivateMessage>> send, CancellationToken ct) =>
        Answer(http, db, clock, true, async me =>
        {
            var m = await send(me);
            var to = await db.Users.FindAsync([m.RecipientId], ct);
            return new SentResponse(m.Id, new PersonView(m.RecipientId, to is null ? "" : Devices.DeviceApi.Display(to)), m.CreatedAt);
        }, ct, created: true);

    static IResult Unauthorized() => Results.Problem(detail: "sign in on the site and link the launcher", statusCode: 401,
        extensions: new Dictionary<string, object?> { ["code"] = "device_unknown" });

    static IResult Problem(string code, int status) =>
        Results.Problem(detail: code, statusCode: status, extensions: new Dictionary<string, object?> { ["code"] = code });
}
