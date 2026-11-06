using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.WebUtilities;
using Microsoft.EntityFrameworkCore;
using Microsoft.Net.Http.Headers;
using Xp.Manifest;
using Xp.Portal.Auth;
using Xp.Portal.Data;
using Xp.Portal.Devices;
using Xp.Portal.Files;

namespace Xp.Portal.Tickets;

/// <summary>What the author says about the mod they offer, next to the archive.</summary>
public sealed record LuaModMeta(string? Id, string? Version, string? Description, string? License, bool RightsConfirmed,
    string? Language = null, string? GameVersion = null, string? LauncherVersion = null, string? Precheck = null);

public sealed record LuaModSubmitted(long Number, string DisplayNumber, string Status);

/// <summary>One offered mod as its author sees it. Status: queue, check, review, needsInfo, approved or rejected.</summary>
public sealed record LuaModRow(long Number, string DisplayNumber, string Mod, string Version, string Status, string? Reason,
    DateTimeOffset CreatedAt, DateTimeOffset UpdatedAt);

/// <summary>
/// "Submit" in the launcher (docs/portal/LUA_MODS.md §8.1). An offered mod is a ticket of its own category with the archive attached:
/// the queue, the quarantine, the messages to the author and the team's automation are the ticket's. The author is whoever the device
/// token belongs to, so there is no guest here. The site only reads the archive's directory; nothing in it is ever unpacked or run here.
/// </summary>
public static partial class LuaModApi
{
    /// <summary>Waiting on us at once, per author: the queue is for people, a flood of versions is not worth the reading.</summary>
    public const int MaxOpen = 5;
    const int MetaMax = 64 * 1024;
    const string IdPrefix = "luaMod: ";

    [GeneratedRegex("^[a-z0-9][a-z0-9_-]{0,39}$")]
    private static partial Regex IdRx();

    public static void Map(IEndpointRouteBuilder app)
    {
        var api = app.MapGroup("/api/v1/lua-mods").WithTags("lua-mods").DisableAntiforgery();
        api.MapPost("", SubmitAsync).RequireRateLimiting("tickets-create")
            .Accepts<IFormFile>("multipart/form-data").Produces<LuaModSubmitted>(StatusCodes.Status201Created).Produces<LuaModSubmitted>(StatusCodes.Status200OK)
            .ProducesProblem(StatusCodes.Status400BadRequest).ProducesProblem(StatusCodes.Status401Unauthorized).ProducesProblem(StatusCodes.Status409Conflict)
            .ProducesProblem(StatusCodes.Status413PayloadTooLarge).ProducesProblem(StatusCodes.Status429TooManyRequests);
        api.MapGet("", MineAsync).RequireRateLimiting("api-read")
            .Produces<List<LuaModRow>>().ProducesProblem(StatusCodes.Status401Unauthorized).ProducesProblem(StatusCodes.Status429TooManyRequests);
    }

    /// <summary>The steps of §8.1 in the ticket's statuses. Only the team's automation moves them.</summary>
    public static string AuthorStatus(TicketStatus s) => s switch
    {
        TicketStatus.New => "queue",
        TicketStatus.Triaged => "check",
        TicketStatus.InProgress => "review",
        TicketStatus.NeedsInfo => "needsInfo",
        TicketStatus.Resolved or TicketStatus.Closed => "approved",
        _ => "rejected",
    };

    static readonly TicketStatus[] Waiting = [TicketStatus.New, TicketStatus.Triaged, TicketStatus.InProgress, TicketStatus.NeedsInfo];

    static async Task<IResult> SubmitAsync([FromHeader(Name = DeviceApi.TokenHeader)] string? token, [FromHeader(Name = "Idempotency-Key")] string? idempotencyKey,
        HttpContext http, PortalDb db, TicketService tickets, AttachmentService files, TimeProvider clock, CancellationToken ct)
    {
        var device = await DeviceApi.AuthenticateAsync(db, token, clock, ct);
        if (device is null) return TicketApi.Problem("device_unknown", "the device token is unknown or revoked", 401);
        // the body is read by hand here, so the limit can still be lifted (R-053), and only for a caller with a token
        if (http.Features.Get<Microsoft.AspNetCore.Http.Features.IHttpMaxRequestBodySizeFeature>() is { IsReadOnly: false } body)
            body.MaxRequestBodySize = LuaModArchive.MaxArchive + 1024 * 1024;
        var boundary = HeaderUtilities.RemoveQuotes(MediaTypeHeaderValue.Parse(http.Request.ContentType ?? "").Boundary).Value;
        if (string.IsNullOrEmpty(boundary)) return TicketApi.Problem("multipart_required", "send the mod as multipart/form-data", 400);

        LuaModMeta? meta = null;
        // the archive waits in a temp file until it is checked: a refused one leaves no ticket behind
        await using var spool = new FileStream(Path.Combine(Path.GetTempPath(), Path.GetRandomFileName()), FileMode.CreateNew, FileAccess.ReadWrite,
            FileShare.None, 81920, FileOptions.DeleteOnClose | FileOptions.Asynchronous);
        bool gotFile = false;
        var reader = new MultipartReader(boundary, http.Request.Body);
        for (var section = await reader.ReadNextSectionAsync(ct); section is not null; section = await reader.ReadNextSectionAsync(ct))
        {
            if (!ContentDispositionHeaderValue.TryParse(section.ContentDisposition, out var cd)) continue;
            if (cd.IsFileDisposition())
            {
                var buf = new byte[81920];
                long size = 0;
                int n;
                while ((n = await section.Body.ReadAsync(buf, ct)) > 0)
                {
                    size += n;
                    if (size > LuaModArchive.MaxArchive) return TicketApi.Problem("file_too_large", "the archive is too large", 413);
                    await spool.WriteAsync(buf.AsMemory(0, n), ct);
                }
                gotFile = size > 0;
            }
            else if (cd.Name.Value == "meta")
            {
                var text = await ReadLimitedAsync(section.Body, ct);
                if (text is null) return TicketApi.Problem("meta_too_large", "the description is too large", 413);
                try { meta = JsonSerializer.Deserialize<LuaModMeta>(text, JsonSerializerOptions.Web); }
                catch (JsonException) { return TicketApi.Problem("meta_invalid", "the description is not valid JSON", 400); }
            }
        }
        if (meta is null) return TicketApi.Problem("meta_required", "no description in the request", 400);
        if (!gotFile) return TicketApi.Problem("file_required", "no archive in the request", 400);

        if (meta.Id is not { } id || !IdRx().IsMatch(id)) return TicketApi.Problem("mod_id_invalid", "the mod id is not valid", 400);
        var version = (meta.Version ?? "").Trim();
        if (version.Length is 0 or > 64) return TicketApi.Problem("mod_version_invalid", "the mod version is not valid", 400);
        var license = (meta.License ?? "").Trim();
        if (license.Length is 0 or > 200) return TicketApi.Problem("license_required", "name the licence of the mod", 400);
        if (string.IsNullOrWhiteSpace(meta.Description)) return TicketApi.Problem("description_required", "say what the mod does", 400);
        if (!meta.RightsConfirmed) return TicketApi.Problem("rights_required", "the author has to allow distribution and confirm the rights", 400);

        spool.Position = 0;
        if (LuaModArchive.CheckZip(spool) is { Count: > 0 } problems)
        {
            var first = problems[0];
            return TicketApi.Problem(first.Code, first.File is null ? "the archive is refused" : $"the archive is refused: {FileRules.SafeName(first.File)}", 400);
        }
        spool.Position = 0;
        var inside = LuaModArchive.ReadMetadata(spool);
        if (inside is null) return TicketApi.Problem("metadata_missing", "no metadata.yml at the root of the archive", 400);
        if (inside.Id != id || inside.Version != version) return TicketApi.Problem("metadata_mismatch", "metadata.yml names another mod or version", 400);

        var open = await db.Tickets.CountAsync(t => t.AuthorId == device.UserId && t.Category == Categories.LuaMod && Waiting.Contains(t.Status), ct);
        var context = new StringBuilder()
            .Append(IdPrefix).Append(id).Append('\n')
            .Append("version: ").Append(version).Append('\n')
            .Append("master: ").Append(inside.AnyMaster ? "*" : inside.Master).Append('\n')
            .Append("license: ").Append(license).Append('\n')
            .Append("rights: confirmed by the author\n");
        if (!string.IsNullOrWhiteSpace(meta.Precheck)) context.Append("precheck: ").Append(meta.Precheck.Trim()).Append('\n');
        var n2 = new NewTicket(Categories.LuaMod, $"Lua: {id} {version}", meta.Description, GameVersion: meta.GameVersion, ModVersion: version,
            LauncherVersion: meta.LauncherVersion, ConsentToFiles: true, Context: context.ToString(), Language: meta.Language);
        try
        {
            // a retry of what already came is not a new mod in the queue, whatever the count says
            if (idempotencyKey is null || !await tickets.KnowsKeyAsync(idempotencyKey, ct))
                if (open >= MaxOpen) return TicketApi.Problem("too_many_open", "wait for an answer on the mods already offered", 409);
            var r = await tickets.CreateAsync(n2, device.UserId, idempotencyKey, http.TraceIdentifier, ct);
            var view = new LuaModSubmitted(r.Ticket.Number, r.Ticket.DisplayNumber, AuthorStatus(r.Ticket.Status));
            // a retry after the file was lost on the way still has to bring it: a mod in the queue without its archive is nothing to check
            if (r.Replayed && await db.TicketAttachments.AnyAsync(a => a.TicketId == r.Ticket.Id, ct)) return Results.Ok(view);
            spool.Position = 0;
            await files.AddAsync(r.Ticket, $"{id}-{version}.zip", spool, ct, new ArchiveRule(LuaModArchive.MaxArchive, s => LuaModArchive.CheckZip(s).FirstOrDefault()?.Code));
            return Results.Created($"/api/v1/lua-mods/{r.Ticket.Number}", view);
        }
        catch (TicketException e) { return TicketApi.Problem(e.Code, e.Message, e.Code == "idempotency_key_reused" ? 409 : 400); }
    }

    static async Task<string?> ReadLimitedAsync(Stream s, CancellationToken ct)
    {
        using var ms = new MemoryStream();
        var buf = new byte[8192];
        int n;
        while ((n = await s.ReadAsync(buf, ct)) > 0)
        {
            if (ms.Length + n > MetaMax) return null;
            ms.Write(buf, 0, n);
        }
        return Encoding.UTF8.GetString(ms.ToArray());
    }

    static async Task<IResult> MineAsync([FromHeader(Name = DeviceApi.TokenHeader)] string? token, HttpContext http, PortalDb db, TimeProvider clock, CancellationToken ct)
    {
        var device = await DeviceApi.AuthenticateAsync(db, token, clock, ct);
        if (device is null) return TicketApi.Problem("device_unknown", "the device token is unknown or revoked", 401);
        http.Response.Headers.CacheControl = "no-store";
        // sort on the table's columns first, build the answer in memory after (R-072)
        var rows = await db.Tickets.Where(t => t.AuthorId == device.UserId && t.Category == Categories.LuaMod).OrderByDescending(t => t.CreatedAt).Take(100)
            .Select(t => new
            {
                t.Number, t.Status, t.ModVersion, t.Context, t.CreatedAt, t.UpdatedAt,
                Reason = db.TicketMessages.Where(m => m.TicketId == t.Id && m.FromStaff && !m.Internal).OrderByDescending(m => m.CreatedAt).Select(m => m.Body).FirstOrDefault(),
            })
            .ToListAsync(ct);
        return Results.Ok(rows.Select(r => new LuaModRow(r.Number, Ticket.FormatNumber(r.Number), ModIdOf(r.Context), r.ModVersion ?? "", AuthorStatus(r.Status), r.Reason, r.CreatedAt, r.UpdatedAt)).ToList());
    }

    /// <summary>The mod's id, from the first line of the ticket's context this API wrote.</summary>
    static string ModIdOf(string? context) =>
        context is { } c && c.StartsWith(IdPrefix, StringComparison.Ordinal) ? c[IdPrefix.Length..].Split('\n')[0] : "";
}
