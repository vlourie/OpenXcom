using System.ComponentModel.DataAnnotations;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.WebUtilities;
using Microsoft.EntityFrameworkCore;
using Microsoft.Net.Http.Headers;
using Xp.Portal.Auth;
using Xp.Portal.Data;
using Xp.Portal.Files;

namespace Xp.Portal.Tickets;

public sealed record CreateTicketRequest(
    [property: Required] string Category,
    [property: Required] string Title,
    [property: Required] string Description,
    string? Steps, string? Expected, string? Actual,
    string? GameVersion, string? ModVersion, string? LauncherVersion,
    string? Email, bool ConsentToFiles, string? Source);

public sealed record CreateTicketResponse(long Number, string DisplayNumber, string? Token, string Url);

public sealed record TicketMessageView(bool FromStaff, string Body, DateTimeOffset CreatedAt);
public sealed record TicketAttachmentView(Guid Id, string FileName, long Size, string Scan);
public sealed record TicketView(long Number, string DisplayNumber, string Category, string Status, string Title, string Description,
    DateTimeOffset CreatedAt, DateTimeOffset UpdatedAt, IReadOnlyList<TicketMessageView> Messages, IReadOnlyList<TicketAttachmentView> Attachments);

public sealed record ReplyRequest([property: Required] string Body);

/// <summary>
/// /api/v1 — used by the launcher (F8, crash reports) and scripts. It never reads the site's cookies:
/// a caller is a guest proving access with the ticket token (header X-Ticket-Token), so a cross-site
/// request from a logged-in browser can do nothing here.
/// </summary>
public static class TicketApi
{
    public const string TokenHeader = "X-Ticket-Token";

    public static void Map(IEndpointRouteBuilder app)
    {
        var api = app.MapGroup("/api/v1").WithTags("tickets").DisableAntiforgery();

        api.MapPost("/tickets", CreateAsync).RequireRateLimiting("tickets-create")
            .Produces<CreateTicketResponse>(StatusCodes.Status201Created).Produces<CreateTicketResponse>(StatusCodes.Status200OK)
            .ProducesProblem(StatusCodes.Status400BadRequest).ProducesProblem(StatusCodes.Status409Conflict)
            .ProducesProblem(StatusCodes.Status429TooManyRequests);
        api.MapGet("/tickets/{number:long}", GetAsync).RequireRateLimiting("api-read")
            .Produces<TicketView>().ProducesProblem(StatusCodes.Status404NotFound).ProducesProblem(StatusCodes.Status429TooManyRequests);
        api.MapPost("/tickets/{number:long}/messages", ReplyAsync).RequireRateLimiting("tickets-write")
            .Produces(StatusCodes.Status204NoContent).ProducesProblem(StatusCodes.Status400BadRequest)
            .ProducesProblem(StatusCodes.Status404NotFound).ProducesProblem(StatusCodes.Status429TooManyRequests);
        api.MapPost("/tickets/{number:long}/attachments", UploadAsync).RequireRateLimiting("tickets-write")
            .Accepts<IFormFile>("multipart/form-data").Produces<TicketAttachmentView>(StatusCodes.Status201Created)
            .ProducesProblem(StatusCodes.Status400BadRequest).ProducesProblem(StatusCodes.Status403Forbidden)
            .ProducesProblem(StatusCodes.Status404NotFound).ProducesProblem(StatusCodes.Status413PayloadTooLarge)
            .ProducesProblem(StatusCodes.Status429TooManyRequests);
    }

    static async Task<IResult> CreateAsync(CreateTicketRequest req, HttpContext http, TicketService tickets,
        [FromHeader(Name = "Idempotency-Key")] string? idempotencyKey, [FromHeader(Name = "X-Correlation-Id")] string? correlationId,
        Microsoft.Extensions.Options.IOptions<PortalOptions> portal, CancellationToken ct)
    {
        var source = req.Source?.ToLowerInvariant() switch { "f8" => TicketSource.F8, "crash" => TicketSource.Crash, _ => TicketSource.Web };
        var n = new NewTicket(req.Category, req.Title, req.Description, req.Steps, req.Expected, req.Actual,
            req.GameVersion, req.ModVersion, req.LauncherVersion, req.Email, req.ConsentToFiles, source);
        try
        {
            var r = await tickets.CreateAsync(n, authorId: null, idempotencyKey, correlationId ?? http.TraceIdentifier, ct);
            var body = new CreateTicketResponse(r.Ticket.Number, r.Ticket.DisplayNumber, r.GuestToken,
                $"{portal.Value.PublicUrl.TrimEnd('/')}/t/{r.Ticket.Number}?k={r.GuestToken}");
            return r.Replayed ? Results.Ok(body) : Results.Created($"/api/v1/tickets/{r.Ticket.Number}", body);
        }
        catch (TicketException e) { return Problem(e, e.Code == "idempotency_key_reused" ? 409 : 400); }
    }

    static async Task<Ticket?> FindForGuestAsync(PortalDb db, long number, string? token, CancellationToken ct)
    {
        if (string.IsNullOrEmpty(token)) return null;
        var t = await db.Tickets.FirstOrDefaultAsync(x => x.Number == number, ct);
        // a wrong token and a missing ticket look the same: the number alone reveals nothing
        return t?.GuestTokenHash is not null && GuestTokens.Matches(token, t.GuestTokenHash) ? t : null;
    }

    static async Task<IResult> GetAsync(long number, [FromHeader(Name = TokenHeader)] string? token, HttpContext http, PortalDb db, CancellationToken ct)
    {
        var t = await FindForGuestAsync(db, number, token, ct);
        if (t is null) return NotFound();
        http.Response.Headers.CacheControl = "no-store";
        return Results.Ok(await ViewAsync(db, t, ct));
    }

    public static async Task<TicketView> ViewAsync(PortalDb db, Ticket t, CancellationToken ct)
    {
        var msgs = await db.TicketMessages.Where(m => m.TicketId == t.Id && !m.Internal).OrderBy(m => m.CreatedAt)
            .Select(m => new TicketMessageView(m.FromStaff, m.Body, m.CreatedAt)).ToListAsync(ct);
        var files = await db.TicketAttachments.Where(a => a.TicketId == t.Id).OrderBy(a => a.CreatedAt)
            .Select(a => new TicketAttachmentView(a.Id, a.FileName, a.Size, a.Scan.ToString())).ToListAsync(ct);
        return new TicketView(t.Number, t.DisplayNumber, t.Category, t.Status.ToString(), t.Title, t.Description, t.CreatedAt, t.UpdatedAt, msgs, files);
    }

    static async Task<IResult> ReplyAsync(long number, ReplyRequest req, [FromHeader(Name = TokenHeader)] string? token, PortalDb db, TicketService tickets, CancellationToken ct)
    {
        var t = await FindForGuestAsync(db, number, token, ct);
        if (t is null) return NotFound();
        try { await tickets.AddMessageAsync(t, req.Body, author: null, fromStaff: false, isInternal: false, ct); }
        catch (TicketException e) { return Problem(e, 400); }
        return Results.NoContent();
    }

    static async Task<IResult> UploadAsync(long number, [FromHeader(Name = TokenHeader)] string? token, HttpContext http, PortalDb db, AttachmentService files,
        Microsoft.Extensions.Options.IOptions<AttachmentOptions> limits, CancellationToken ct)
    {
        // Kestrel stops bodies at 30 MB by default, below our own limits: lift it to them, plus room for the multipart framing
        if (http.Features.Get<Microsoft.AspNetCore.Http.Features.IHttpMaxRequestBodySizeFeature>() is { IsReadOnly: false } body)
            body.MaxRequestBodySize = Math.Max(limits.Value.MaxFileBytes, limits.Value.MaxZipBytes) + 1024 * 1024;
        var t = await FindForGuestAsync(db, number, token, ct);
        if (t is null) return NotFound();
        var boundary = HeaderUtilities.RemoveQuotes(MediaTypeHeaderValue.Parse(http.Request.ContentType ?? "").Boundary).Value;
        if (string.IsNullOrEmpty(boundary)) return Problem("multipart_required", "send the file as multipart/form-data", 400);

        // read the multipart body section by section: the file streams straight to storage
        var reader = new MultipartReader(boundary, http.Request.Body);
        var section = await reader.ReadNextSectionAsync(ct);
        while (section is not null)
        {
            if (ContentDispositionHeaderValue.TryParse(section.ContentDisposition, out var cd) && cd.IsFileDisposition())
            {
                var name = cd.FileNameStar.HasValue ? cd.FileNameStar.Value! : cd.FileName.Value ?? "";
                var kind = FileRules.KindOf(name);
                // logs, saves and archives carry personal data: only with the author's consent
                if (kind is not null && !FileRules.IsImage(kind.Value) && !t.ConsentToFiles)
                    return Problem("consent_required", "the ticket was sent without consent to attach logs and saves", 403);
                try
                {
                    var a = await files.AddAsync(t, name, section.Body, ct);
                    return Results.Created($"/api/v1/tickets/{number}", new TicketAttachmentView(a.Id, a.FileName, a.Size, a.Scan.ToString()));
                }
                catch (TicketException e)
                {
                    return Problem(e, e.Code is "file_too_large" or "ticket_files_too_large" ? 413 : 400);
                }
            }
            section = await reader.ReadNextSectionAsync(ct);
        }
        return Problem("file_required", "no file in the request", 400);
    }

    static IResult NotFound() => Problem("not_found", "no such ticket, or the token does not match", 404);

    static IResult Problem(TicketException e, int status) => Problem(e.Code, e.Message, status);

    public static IResult Problem(string code, string detail, int status) =>
        Results.Problem(detail: detail, statusCode: status, extensions: new Dictionary<string, object?> { ["code"] = code });
}
