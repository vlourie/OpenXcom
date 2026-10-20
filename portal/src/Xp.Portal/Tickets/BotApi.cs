using System.Net;
using System.Security.Claims;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Xp.Portal.Auth;
using Xp.Portal.Data;
using Xp.Portal.Files;

namespace Xp.Portal.Tickets;

public sealed record BotTicketRow(long Number, string DisplayNumber, string Category, string Status, string Priority, string Source,
    string? Language, string Title, string? GameVersion, int Files, DateTimeOffset CreatedAt, DateTimeOffset UpdatedAt);

public sealed record BotMessageView(bool FromStaff, bool Internal, string? Author, string Body, DateTimeOffset CreatedAt);
public sealed record BotAttachmentView(Guid Id, string FileName, string ContentType, long Size, string Sha256, string Scan, DateTimeOffset CreatedAt);
public sealed record BotHistoryView(string Action, string? From, string? To, string? Actor, DateTimeOffset At);

/// <summary>Everything staff see on the ticket page, except who the author is and their address.</summary>
public sealed record BotTicketView(long Number, string DisplayNumber, string Category, string Status, string Priority, string Source,
    string? Language, string Title, string Description, string? Steps, string? Expected, string? Actual,
    string? GameVersion, string? ModVersion, string? LauncherVersion, string? Context, bool ConsentToFiles, bool Registered,
    long? DuplicateOf, DateTimeOffset CreatedAt, DateTimeOffset UpdatedAt,
    IReadOnlyList<BotMessageView> Messages, IReadOnlyList<BotAttachmentView> Attachments, IReadOnlyList<BotHistoryView> History);

public sealed record BotStatusRequest(string Status, string? Note, long? DuplicateOf);
public sealed record BotMessageRequest(string Body, bool Internal);

/// <summary>
/// /api/v1/bot - the team's automation: list the queue, read a ticket with its files, move it, write.
/// A caller proves itself with X-Bot-Key (made by "admin bot create" on the server); the key is not
/// a sign-in, never reads cookies, and sees only its own categories - the rest answer 404, as for an
/// admin of another category. Not part of the published API: clients out there never call it.
/// </summary>
public static class BotApi
{
    public const string KeyHeader = "X-Bot-Key";

    public static void Map(IEndpointRouteBuilder app)
    {
        var api = app.MapGroup("/api/v1/bot").DisableAntiforgery().RequireRateLimiting("bot").ExcludeFromDescription();
        api.MapGet("/tickets", ListAsync);
        api.MapGet("/tickets/{number:long}", GetAsync);
        api.MapGet("/tickets/{number:long}/files/{id:guid}", FileAsync);
        api.MapPost("/tickets/{number:long}/status", StatusAsync);
        api.MapPost("/tickets/{number:long}/messages", MessageAsync);
    }

    static readonly TicketStatus[] Open = [TicketStatus.New, TicketStatus.Triaged, TicketStatus.InProgress, TicketStatus.NeedsInfo];
    const int ListMax = 200;

    /// <summary>The bot's identity for this request: its account and the categories its key opens.</summary>
    public sealed record Caller(BotKey Key, Viewer Viewer)
    {
        public Guid UserId => Key.UserId;
    }

    /// <summary>
    /// Who is behind X-Bot-Key, or null. Found by the hash of what came in, like a device token; a revoked
    /// key, or a key used from outside the networks it was given, is the same 401 as an unknown one.
    /// </summary>
    public static async Task<Caller?> AuthenticateAsync(HttpContext http, PortalDb db, TimeProvider clock, CancellationToken ct)
    {
        var token = http.Request.Headers[KeyHeader].ToString();
        if (token.Length is < 16 or > 128) return null;
        var hash = DeviceSecrets.Hash(token);
        var key = await db.BotKeys.FirstOrDefaultAsync(k => k.TokenHash == hash && k.RevokedAt == null, ct);
        if (key is null) return null;
        var ip = http.Connection.RemoteIpAddress;
        if (ip is { IsIPv4MappedToIPv6: true }) ip = ip.MapToIPv4();
        if (!Allowed(key.Networks, ip)) return null;

        var now = clock.GetUtcNow();
        var ipText = ip?.ToString();
        // "last used" answers "is the automation alive and where from": once an hour, or when the address moves
        if (key.LastUsedAt is null || now - key.LastUsedAt > TimeSpan.FromHours(1) || key.LastIp != ipText)
        {
            key.LastUsedAt = now;
            key.LastIp = ipText;
            await db.SaveChangesAsync(ct);
        }
        return new Caller(key, ViewerFor(key));
    }

    /// <summary>The key seen through the same Viewer as a person: an Admin holding exactly the key's categories.</summary>
    public static Viewer ViewerFor(BotKey key)
    {
        var id = new ClaimsIdentity("bot");
        id.AddClaim(new Claim(ClaimTypes.NameIdentifier, key.UserId.ToString()));
        id.AddClaim(new Claim(ClaimTypes.Role, Roles.Admin));
        foreach (var c in SplitList(key.Categories).Where(Categories.IsValid))
            id.AddClaim(new Claim(Permissions.ClaimType, Permissions.ForCategory(c)));
        return new Viewer(new ClaimsPrincipal(id));
    }

    public static IEnumerable<string> SplitList(string list) =>
        list.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);

    public static bool Allowed(string networks, IPAddress? ip)
    {
        var nets = SplitList(networks).ToList();
        if (nets.Count == 0) return true;
        if (ip is null) return false;
        foreach (var n in nets)
            if (System.Net.IPNetwork.TryParse(n, out var net) ? net.Contains(ip) : IPAddress.TryParse(n, out var one) && one.Equals(ip))
                return true;
        return false;
    }

    static async Task<IResult> ListAsync(HttpContext http, PortalDb db, TimeProvider clock, [FromQuery] string[]? status, int? take, CancellationToken ct)
    {
        var me = await AuthenticateAsync(http, db, clock, ct);
        if (me is null) return Unauthorized();
        var q = me.Viewer.VisibleToStaff(db.Tickets);
        if (status is { Length: > 0 } && status.All(s => s == "all")) { }
        else if (status is { Length: > 0 })
        {
            var want = new List<TicketStatus>();
            foreach (var s in status)
            {
                if (!Enum.TryParse<TicketStatus>(s, ignoreCase: true, out var st)) return TicketApi.Problem("status_invalid", $"unknown status '{s}'", 400);
                want.Add(st);
            }
            q = q.Where(t => want.Contains(t.Status));
        }
        else q = q.Where(t => Open.Contains(t.Status));
        var n = Math.Clamp(take ?? 100, 1, ListMax);
        // sort on the table's columns first, build the answer in memory after (R-072)
        var rows = await q.OrderBy(t => t.CreatedAt).Take(n)
            .Select(t => new { t.Number, t.Category, t.Status, t.Priority, t.Source, t.Language, t.Title, t.GameVersion, t.CreatedAt, t.UpdatedAt,
                Files = db.TicketAttachments.Count(a => a.TicketId == t.Id) })
            .ToListAsync(ct);
        http.Response.Headers.CacheControl = "no-store";
        return Results.Ok(rows.Select(r => new BotTicketRow(r.Number, Ticket.FormatNumber(r.Number), r.Category, r.Status.ToString(), r.Priority.ToString(),
            r.Source.ToString(), r.Language, r.Title, r.GameVersion, r.Files, r.CreatedAt, r.UpdatedAt)).ToList());
    }

    static async Task<Ticket?> FindAsync(PortalDb db, Caller me, long number, CancellationToken ct)
    {
        var t = await db.Tickets.FirstOrDefaultAsync(x => x.Number == number, ct);
        // another category's ticket does not exist for this key: same 404 as a wrong number
        return t is not null && me.Viewer.IsStaffFor(t) ? t : null;
    }

    static async Task<IResult> GetAsync(long number, HttpContext http, PortalDb db, TimeProvider clock, CancellationToken ct)
    {
        var me = await AuthenticateAsync(http, db, clock, ct);
        if (me is null) return Unauthorized();
        var t = await FindAsync(db, me, number, ct);
        if (t is null) return NotFound();
        http.Response.Headers.CacheControl = "no-store";
        return Results.Ok(await ViewAsync(db, t, ct));
    }

    public static async Task<BotTicketView> ViewAsync(PortalDb db, Ticket t, CancellationToken ct)
    {
        var msgs = await db.TicketMessages.Where(m => m.TicketId == t.Id).OrderBy(m => m.CreatedAt)
            .Select(m => new { m.FromStaff, m.Internal, Author = m.FromStaff && m.Author != null ? m.Author.DisplayName : null, m.Body, m.CreatedAt })
            .ToListAsync(ct);
        var files = await db.TicketAttachments.Where(a => a.TicketId == t.Id).OrderBy(a => a.CreatedAt).ToListAsync(ct);
        var history = await db.TicketHistory.Where(h => h.TicketId == t.Id).OrderBy(h => h.Id)
            .Select(h => new { h.Action, h.From, h.To, Actor = db.Users.Where(u => u.Id == h.ActorId).Select(u => u.DisplayName).FirstOrDefault(), h.At })
            .ToListAsync(ct);
        long? dupOf = t.DuplicateOfId is { } d ? await db.Tickets.Where(x => x.Id == d).Select(x => (long?)x.Number).FirstOrDefaultAsync(ct) : null;
        return new BotTicketView(t.Number, t.DisplayNumber, t.Category, t.Status.ToString(), t.Priority.ToString(), t.Source.ToString(),
            t.Language, t.Title, t.Description, t.Steps, t.Expected, t.Actual, t.GameVersion, t.ModVersion, t.LauncherVersion, t.Context,
            t.ConsentToFiles, t.AuthorId is not null, dupOf, t.CreatedAt, t.UpdatedAt,
            msgs.Select(m => new BotMessageView(m.FromStaff, m.Internal, m.Author, m.Body, m.CreatedAt)).ToList(),
            files.Select(a => new BotAttachmentView(a.Id, a.FileName, a.ContentType, a.Size, a.Sha256, a.Scan.ToString(), a.CreatedAt)).ToList(),
            history.Select(h => new BotHistoryView(h.Action, h.From, h.To, h.Actor, h.At)).ToList());
    }

    /// <summary>A file of the ticket, always as a download. Pending and quarantined files are not handed out, as on the staff page.</summary>
    static async Task<IResult> FileAsync(long number, Guid id, HttpContext http, PortalDb db, ObjectStore store, TimeProvider clock, CancellationToken ct)
    {
        var me = await AuthenticateAsync(http, db, clock, ct);
        if (me is null) return Unauthorized();
        var t = await FindAsync(db, me, number, ct);
        if (t is null) return NotFound();
        var a = await db.TicketAttachments.FirstOrDefaultAsync(x => x.Id == id && x.TicketId == t.Id, ct);
        if (a is null) return TicketApi.Problem("not_found", "no such file in this ticket", 404);
        if (a.Scan is ScanStatus.Pending or ScanStatus.Quarantined)
            return TicketApi.Problem("file_not_ready", $"the file is {a.Scan.ToString().ToLowerInvariant()}", 409);
        http.Response.Headers.CacheControl = "private, no-store";
        return Results.Stream(store.OpenRead(a.ObjectKey), "application/octet-stream", a.FileName);
    }

    static async Task<IResult> StatusAsync(long number, BotStatusRequest req, HttpContext http, PortalDb db, TicketService tickets, TimeProvider clock, CancellationToken ct)
    {
        var me = await AuthenticateAsync(http, db, clock, ct);
        if (me is null) return Unauthorized();
        var t = await FindAsync(db, me, number, ct);
        if (t is null) return NotFound();
        if (!Enum.TryParse<TicketStatus>(req.Status, ignoreCase: true, out var to))
            return TicketApi.Problem("status_invalid", $"unknown status '{req.Status}'", 400);
        try
        {
            if (to == TicketStatus.Duplicate)
            {
                if (req.DuplicateOf is not { } of) return TicketApi.Problem("duplicate_target_invalid", "duplicateOf is required", 400);
                await tickets.MarkDuplicateAsync(t, of, me.Viewer, ct);
            }
            else await tickets.ChangeStatusAsync(t, to, me.UserId, ct);
            // the reason goes next to the move, for the team only
            if (!string.IsNullOrWhiteSpace(req.Note))
                await tickets.AddMessageAsync(t, req.Note, me.UserId, fromStaff: true, isInternal: true, ct);
        }
        catch (TicketException e) { return TicketApi.Problem(e.Code, e.Message, 409); }
        return Results.Ok(await ViewAsync(db, t, ct));
    }

    static async Task<IResult> MessageAsync(long number, BotMessageRequest req, HttpContext http, PortalDb db, TicketService tickets, TimeProvider clock, CancellationToken ct)
    {
        var me = await AuthenticateAsync(http, db, clock, ct);
        if (me is null) return Unauthorized();
        var t = await FindAsync(db, me, number, ct);
        if (t is null) return NotFound();
        try { await tickets.AddMessageAsync(t, req.Body ?? "", me.UserId, fromStaff: true, isInternal: req.Internal, ct); }
        catch (TicketException e) { return TicketApi.Problem(e.Code, e.Message, 400); }
        return Results.NoContent();
    }

    static IResult Unauthorized() => TicketApi.Problem("bot_key_unknown", "the bot key is unknown, revoked, or not allowed from this address", 401);
    static IResult NotFound() => TicketApi.Problem("not_found", "no such ticket", 404);
}

/// <summary>Making and revoking bot keys - from the server's command line only, never from the web.</summary>
public static class BotAccounts
{
    public sealed record Created(BotKey Key, string Secret);

    /// <summary>
    /// A new bot account with one key. The account has no password, an unconfirmed address on a reserved
    /// domain and a lockout to the end of time: nobody signs in as it, it exists to sign the ticket's history.
    /// </summary>
    public static async Task<Created> CreateAsync(IServiceProvider sp, string name, string? categories, string? networks)
    {
        name = name.Trim();
        if (name.Length is 0 or > BotLimits.NameMax) throw new ArgumentException($"--name: 1..{BotLimits.NameMax} characters");
        var cats = categories is null ? Categories.Open : BotApi.SplitList(categories).ToArray();
        if (cats.Length == 0 || cats.Any(c => !Categories.IsValid(c)))
            throw new ArgumentException($"--categories: comma-separated, of {string.Join(",", Categories.All)}");
        var nets = networks is null ? [] : BotApi.SplitList(networks).ToArray();
        foreach (var n in nets)
            if (!System.Net.IPNetwork.TryParse(n, out _) && !IPAddress.TryParse(n, out _))
                throw new ArgumentException($"--networks: '{n}' is neither an address nor a CIDR network");
        var catList = string.Join(",", cats.Distinct());
        var netList = string.Join(",", nets);
        if (catList.Length > BotLimits.ListMax || netList.Length > BotLimits.ListMax) throw new ArgumentException("the list is too long");

        var db = sp.GetRequiredService<PortalDb>();
        if (await db.BotKeys.AnyAsync(k => k.Name == name && k.RevokedAt == null))
            throw new ArgumentException($"an active key named '{name}' exists; revoke it first");
        var users = sp.GetRequiredService<Microsoft.AspNetCore.Identity.UserManager<PortalUser>>();
        var key = new BotKey { Name = name, Categories = catList, Networks = netList };
        var email = $"bot-{key.Id:N}@{BotLimits.EmailDomain}";
        var u = new PortalUser { UserName = email, Email = email, EmailConfirmed = false, DisplayName = name, LockoutEnabled = true, LockoutEnd = DateTimeOffset.MaxValue };
        var r = await users.CreateAsync(u);
        if (!r.Succeeded) throw new ArgumentException(string.Join("; ", r.Errors.Select(e => e.Description)));
        var secret = DeviceSecrets.NewToken();
        key.UserId = u.Id;
        key.TokenHash = DeviceSecrets.Hash(secret);
        key.CreatedAt = sp.GetRequiredService<TimeProvider>().GetUtcNow();
        db.BotKeys.Add(key);
        sp.GetRequiredService<Site.Audit>().Add(null, "bot.create.cli", name, $"categories {catList}; networks {(netList.Length > 0 ? netList : "any")}");
        await db.SaveChangesAsync();
        return new Created(key, secret);
    }

    public static async Task<int> RevokeAsync(IServiceProvider sp, string name)
    {
        var db = sp.GetRequiredService<PortalDb>();
        var keys = await db.BotKeys.Where(k => k.Name == name && k.RevokedAt == null).ToListAsync();
        var now = sp.GetRequiredService<TimeProvider>().GetUtcNow();
        foreach (var k in keys) k.RevokedAt = now;
        if (keys.Count > 0) sp.GetRequiredService<Site.Audit>().Add(null, "bot.revoke.cli", name);
        await db.SaveChangesAsync();
        return keys.Count;
    }
}
