using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.EntityFrameworkCore;
using Xp.Portal.Auth;
using Xp.Portal.Data;
using Xp.Portal.Files;
using Xp.Portal.Tickets;

namespace Xp.Portal.Pages.Admin;

/// <summary>The ticket queue: only the categories this admin works on, never the others.</summary>
public sealed class QueueModel(PortalDb db) : PageModel
{
    public const int PageSize = 50;
    static readonly TicketStatus[] Open = [TicketStatus.New, TicketStatus.Triaged, TicketStatus.InProgress, TicketStatus.NeedsInfo];

    [BindProperty(SupportsGet = true)] public string? Status { get; set; }
    [BindProperty(SupportsGet = true)] public string? Category { get; set; }
    [BindProperty(SupportsGet = true)] public bool Mine { get; set; }
    [BindProperty(SupportsGet = true)] public string? Q { get; set; }
    [BindProperty(SupportsGet = true, Name = "p")] public int PageNo { get; set; } = 1;

    public Viewer Viewer { get; private set; } = null!;
    public List<Ticket> Tickets { get; private set; } = new();
    public bool HasMore { get; private set; }

    public async Task OnGetAsync(CancellationToken ct)
    {
        Viewer = new Viewer(User);
        var q = Viewer.VisibleToStaff(db.Tickets);
        if (Categories.IsValid(Category)) q = q.Where(t => t.Category == Category);
        if (Status == "all") { }
        else if (Enum.TryParse<TicketStatus>(Status, out var st)) q = q.Where(t => t.Status == st);
        else q = q.Where(t => Open.Contains(t.Status));
        if (Mine && Viewer.UserId is { } me) q = q.Where(t => t.AssigneeId == me);
        if (!string.IsNullOrWhiteSpace(Q))
        {
            var s = Q.Trim();
            var digits = s.StartsWith("XP-", StringComparison.OrdinalIgnoreCase) ? s[3..] : s;
            if (long.TryParse(digits, out var n)) q = q.Where(t => t.Number == n);
            else q = q.Where(t => EF.Functions.ILike(t.Title, "%" + s.Replace("\\", "\\\\").Replace("%", "\\%").Replace("_", "\\_") + "%"));
        }
        PageNo = Math.Max(1, PageNo);
        // priority is stored as text: order by rank, not alphabetically
        var rows = await q.OrderByDescending(t => t.Priority == TicketPriority.Critical ? 3 : t.Priority == TicketPriority.High ? 2 : t.Priority == TicketPriority.Normal ? 1 : 0)
            .ThenBy(t => t.CreatedAt)
            .Skip((PageNo - 1) * PageSize).Take(PageSize + 1).ToListAsync(ct);
        HasMore = rows.Count > PageSize;
        Tickets = rows.Take(PageSize).ToList();
    }
}

public sealed record StaffOption(Guid Id, string Name);
public sealed record MessageRow(TicketMessage Message, string? Author);
public sealed record HistoryRow(TicketHistory Entry, string? Actor);

public sealed class TicketModel(PortalDb db, TicketService tickets, SignedUrls urls, UserManager<PortalUser> users) : PageModel
{
    public Ticket Ticket { get; private set; } = null!;
    public Viewer Viewer { get; private set; } = null!;
    public List<MessageRow> Messages { get; private set; } = new();
    public List<TicketAttachment> Files { get; private set; } = new();
    public List<HistoryRow> History { get; private set; } = new();
    public List<StaffOption> Staff { get; private set; } = new();
    public string? AuthorName { get; private set; }
    public Ticket? DuplicateOf { get; private set; }
    public List<string> Errors { get; } = new();

    public string? LinkFor(TicketAttachment a) => a.Scan is ScanStatus.Clean or ScanStatus.Unscanned ? urls.For(a) : null;

    async Task<bool> LoadAsync(long number, CancellationToken ct)
    {
        Viewer = new Viewer(User);
        var t = await db.Tickets.FirstOrDefaultAsync(x => x.Number == number, ct);
        // another category's ticket does not exist for this admin: same 404 as a wrong number
        if (t is null || !Viewer.IsStaffFor(t)) return false;
        Ticket = t;
        Response.Headers.CacheControl = "no-store";
        Messages = await db.TicketMessages.Where(m => m.TicketId == t.Id).OrderBy(m => m.CreatedAt)
            .Select(m => new MessageRow(m, m.Author == null ? null : m.Author.DisplayName)).ToListAsync(ct);
        Files = await db.TicketAttachments.Where(a => a.TicketId == t.Id).OrderBy(a => a.CreatedAt).ToListAsync(ct);
        History = await db.TicketHistory.Where(h => h.TicketId == t.Id).OrderBy(h => h.Id)
            .Select(h => new HistoryRow(h, db.Users.Where(u => u.Id == h.ActorId).Select(u => u.DisplayName).FirstOrDefault())).ToListAsync(ct);
        AuthorName = t.AuthorId is { } a ? await db.Users.Where(u => u.Id == a).Select(u => u.DisplayName + " <" + u.Email + ">").FirstOrDefaultAsync(ct) : null;
        DuplicateOf = t.DuplicateOfId is { } d ? await db.Tickets.FirstOrDefaultAsync(x => x.Id == d, ct) : null;
        if (DuplicateOf is not null && !Viewer.IsStaffFor(DuplicateOf)) DuplicateOf = null;
        Staff = await StaffForAsync(t.Category);
        return true;
    }

    async Task<List<StaffOption>> StaffForAsync(string category)
    {
        var perm = Permissions.ForCategory(category);
        var supers = await users.GetUsersInRoleAsync(Roles.SuperAdmin);
        var admins = await users.GetUsersInRoleAsync(Roles.Admin);
        var withPerm = (await db.UserPermissions.Where(p => p.Permission == perm).Select(p => p.UserId).ToListAsync()).ToHashSet();
        return supers.Concat(admins.Where(a => withPerm.Contains(a.Id)))
            .DistinctBy(u => u.Id).OrderBy(u => u.DisplayName).Select(u => new StaffOption(u.Id, u.DisplayName)).ToList();
    }

    Guid Me => Viewer.UserId ?? throw new InvalidOperationException("staff without an id");

    public async Task<IActionResult> OnGetAsync(long number, CancellationToken ct) =>
        await LoadAsync(number, ct) ? Page() : NotFound();

    async Task<IActionResult> ActAsync(long number, Func<Task> act, CancellationToken ct)
    {
        if (!await LoadAsync(number, ct)) return NotFound();
        try { await act(); }
        catch (TicketException e)
        {
            Errors.Add(e.Code);
            await LoadAsync(number, ct);
            return Page();
        }
        // a ticket moved to a category this admin does not work on leaves their sight
        return Viewer.IsStaffFor(Ticket) ? Redirect($"/admin/tickets/{number}") : Redirect("/admin");
    }

    public Task<IActionResult> OnPostStatusAsync(long number, TicketStatus to, CancellationToken ct) =>
        ActAsync(number, () => tickets.ChangeStatusAsync(Ticket, to, Me, ct), ct);

    public Task<IActionResult> OnPostPriorityAsync(long number, TicketPriority priority, CancellationToken ct) =>
        ActAsync(number, () => tickets.SetPriorityAsync(Ticket, priority, Me, ct), ct);

    public Task<IActionResult> OnPostCategoryAsync(long number, string? category, CancellationToken ct) =>
        ActAsync(number, () => tickets.SetCategoryAsync(Ticket, category ?? "", Me, ct), ct);

    public Task<IActionResult> OnPostAssignAsync(long number, Guid? assignee, CancellationToken ct) =>
        ActAsync(number, () => tickets.AssignAsync(Ticket, assignee, Me, ct), ct);

    public Task<IActionResult> OnPostDuplicateAsync(long number, string? of, CancellationToken ct) =>
        ActAsync(number, () =>
        {
            var s = (of ?? "").Trim();
            if (s.StartsWith("XP-", StringComparison.OrdinalIgnoreCase)) s = s[3..];
            if (!long.TryParse(s, out var n)) throw new TicketException("duplicate_target_invalid", "not a ticket number");
            return tickets.MarkDuplicateAsync(Ticket, n, Viewer, ct);
        }, ct);

    public Task<IActionResult> OnPostMessageAsync(long number, string? body, bool @internal, CancellationToken ct) =>
        ActAsync(number, () => tickets.AddMessageAsync(Ticket, body ?? "", Me, fromStaff: true, isInternal: @internal, ct), ct);
}
