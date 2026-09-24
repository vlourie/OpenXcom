using System.Security.Claims;
using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.EntityFrameworkCore;
using Xp.Portal.Auth;
using Xp.Portal.Data;
using Xp.Portal.Notifications;
using Xp.Portal.Site;

namespace Xp.Portal.Pages.Admin.Super;

public sealed record UserRow(PortalUser User, string Role, HashSet<string> Permissions);

/// <summary>Roles and admin specializations. Every change is audited and signs the person out of old sessions.</summary>
public sealed class UsersModel(PortalDb db, UserManager<PortalUser> users, Audit audit) : PageModel
{
    [BindProperty(SupportsGet = true)] public string? Q { get; set; }
    public List<UserRow> Rows { get; private set; } = new();
    public List<string> Errors { get; } = new();

    Guid Me => Guid.Parse(User.FindFirstValue(ClaimTypes.NameIdentifier)!);

    async Task LoadAsync(CancellationToken ct)
    {
        var q = db.Users.AsQueryable();
        if (!string.IsNullOrWhiteSpace(Q))
        {
            var s = "%" + Q.Trim().Replace("\\", "\\\\").Replace("%", "\\%").Replace("_", "\\_") + "%";
            q = q.Where(u => EF.Functions.ILike(u.Email!, s) || EF.Functions.ILike(u.DisplayName, s));
        }
        var list = await q.OrderBy(u => u.Email).Take(100).ToListAsync(ct);
        var ids = list.Select(u => u.Id).ToList();
        var roles = await (from ur in db.UserRoles join r in db.Roles on ur.RoleId equals r.Id where ids.Contains(ur.UserId) select new { ur.UserId, r.Name }).ToListAsync(ct);
        var perms = await db.UserPermissions.Where(p => ids.Contains(p.UserId)).ToListAsync(ct);
        Rows = list.Select(u => new UserRow(u,
            roles.Where(r => r.UserId == u.Id).Select(r => r.Name!).OrderByDescending(Rank).FirstOrDefault() ?? Roles.User,
            perms.Where(p => p.UserId == u.Id).Select(p => p.Permission).ToHashSet())).ToList();
    }

    static int Rank(string r) => r == Roles.SuperAdmin ? 2 : r == Roles.Admin ? 1 : 0;

    public async Task OnGetAsync(CancellationToken ct) => await LoadAsync(ct);

    public async Task<IActionResult> OnPostAsync(Guid id, string role, string[]? perms, CancellationToken ct)
    {
        var u = await users.FindByIdAsync(id.ToString());
        if (u is null) return NotFound();
        if (!Roles.All.Contains(role)) { Errors.Add("role_invalid"); await LoadAsync(ct); return Page(); }
        var current = await users.GetRolesAsync(u);
        var wasSuper = current.Contains(Roles.SuperAdmin);
        if (wasSuper && role != Roles.SuperAdmin)
        {
            // nobody demotes themselves by a stray click, and the last SuperAdmin stays
            if (u.Id == Me) { Errors.Add("cannot_demote_self"); await LoadAsync(ct); return Page(); }
            if ((await users.GetUsersInRoleAsync(Roles.SuperAdmin)).Count <= 1) { Errors.Add("last_superadmin"); await LoadAsync(ct); return Page(); }
        }
        var wanted = (perms ?? []).Where(Permissions.IsValid).ToHashSet();
        if (role == Roles.User) wanted.Clear();   // permissions mean nothing without the Admin role

        var before = $"{string.Join(",", current.Order())} [{string.Join(",", (await db.UserPermissions.Where(p => p.UserId == u.Id).Select(p => p.Permission).ToListAsync(ct)).Order())}]";
        await users.RemoveFromRolesAsync(u, current);
        await users.AddToRoleAsync(u, role);
        db.UserPermissions.RemoveRange(db.UserPermissions.Where(p => p.UserId == u.Id));
        foreach (var p in wanted) db.UserPermissions.Add(new UserPermission { UserId = u.Id, Permission = p });
        var after = $"{role} [{string.Join(",", wanted.Order())}]";
        audit.Add(Me, "user.access", u.Email!, $"{before} -> {after}");
        await db.SaveChangesAsync(ct);
        // old sessions carry the old roles in their cookie: invalidate them now, not in a minute
        if (before != after) await users.UpdateSecurityStampAsync(u);
        TempData["flash"] = "super.saved";
        return Redirect("/admin/super/users" + (string.IsNullOrEmpty(Q) ? "" : "?Q=" + Uri.EscapeDataString(Q)));
    }
}

public sealed class TelegramModel(PortalDb db, Audit audit, TimeProvider clock, Microsoft.Extensions.Options.IOptions<TelegramOptions> options) : PageModel
{
    public List<TelegramRoute> Routes { get; private set; } = new();
    public Dictionary<JobState, int> Counts { get; private set; } = new();
    public List<NotificationJob> Dead { get; private set; } = new();
    public List<UpstreamState> Upstream { get; private set; } = new();
    public bool TokenSet => !string.IsNullOrWhiteSpace(options.Value.BotToken);
    public List<string> Errors { get; } = new();

    Guid Me => Guid.Parse(User.FindFirstValue(ClaimTypes.NameIdentifier)!);

    async Task LoadAsync(CancellationToken ct)
    {
        Routes = await db.TelegramRoutes.OrderBy(r => r.Category).ToListAsync(ct);
        Counts = (await db.NotificationJobs.GroupBy(j => j.State).Select(g => new { g.Key, N = g.Count() }).ToListAsync(ct)).ToDictionary(x => x.Key, x => x.N);
        Dead = await db.NotificationJobs.Where(j => j.State == JobState.Dead).OrderByDescending(j => j.Id).Take(20).ToListAsync(ct);
        Upstream = await db.UpstreamStates.OrderBy(u => u.Source).ToListAsync(ct);
    }

    public async Task OnGetAsync(CancellationToken ct) => await LoadAsync(ct);

    public async Task<IActionResult> OnPostSaveAsync(string category, string chatId, int? threadId, bool enabled, CancellationToken ct)
    {
        category = (category ?? "").Trim();
        chatId = (chatId ?? "").Trim();
        if (category != "*" && category != TelegramNotices.UpstreamCategory && !Categories.IsValid(category)) Errors.Add("category_invalid");
        // chat ids are numbers (-100… for groups) or @channelname
        if (!(long.TryParse(chatId, out _) || (chatId.StartsWith('@') && chatId.Length is > 1 and <= 64))) Errors.Add("chat_invalid");
        if (Errors.Count > 0) { await LoadAsync(ct); return Page(); }
        var r = await db.TelegramRoutes.FirstOrDefaultAsync(x => x.Category == category, ct);
        if (r is null) db.TelegramRoutes.Add(r = new TelegramRoute { Category = category });
        r.ChatId = chatId;
        r.ThreadId = threadId;
        r.Enabled = enabled;
        audit.Add(Me, "telegram.route", category, $"{chatId} thread {threadId?.ToString() ?? "-"} {(enabled ? "on" : "off")}");
        await db.SaveChangesAsync(ct);
        TempData["flash"] = "super.saved";
        return RedirectToPage();
    }

    public async Task<IActionResult> OnPostDeleteAsync(int id, CancellationToken ct)
    {
        var r = await db.TelegramRoutes.FindAsync([id], ct);
        if (r is not null)
        {
            db.TelegramRoutes.Remove(r);
            audit.Add(Me, "telegram.route.delete", r.Category, r.ChatId);
            await db.SaveChangesAsync(ct);
        }
        return RedirectToPage();
    }

    public async Task<IActionResult> OnPostTestAsync(int id, CancellationToken ct)
    {
        var r = await db.TelegramRoutes.FindAsync([id], ct);
        if (r is null) return RedirectToPage();
        db.NotificationJobs.Add(new NotificationJob
        {
            ChatId = r.ChatId, ThreadId = r.ThreadId, NextAttemptAt = clock.GetUtcNow(), CreatedAt = clock.GetUtcNow(),
            Text = "✅ X-Piratez portal: test message for <b>" + TelegramNotices.Html(r.Category) + "</b>",
        });
        audit.Add(Me, "telegram.test", r.Category, r.ChatId);
        await db.SaveChangesAsync(ct);
        TempData["flash"] = "super.test_queued";
        return RedirectToPage();
    }

    /// <summary>The daily upstream check, now: a way to see the notices work without waiting a day.</summary>
    public async Task<IActionResult> OnPostCheckUpstreamAsync([FromServices] UpstreamCheck check, CancellationToken ct)
    {
        var queued = await check.RunAsync(ct);
        audit.Add(Me, "upstream.check", "all", queued.ToString());
        await db.SaveChangesAsync(ct);
        TempData["flash"] = "super.upstream.checked_flash";
        return RedirectToPage();
    }

    public async Task<IActionResult> OnPostRetryAsync(CancellationToken ct)
    {
        var now = clock.GetUtcNow();
        var n = await db.NotificationJobs.Where(j => j.State == JobState.Dead)
            .ExecuteUpdateAsync(s => s.SetProperty(j => j.State, JobState.Pending).SetProperty(j => j.Attempts, 0).SetProperty(j => j.NextAttemptAt, now), ct);
        audit.Add(Me, "telegram.retry", "dead jobs", n.ToString());
        await db.SaveChangesAsync(ct);
        return RedirectToPage();
    }
}

public sealed record AuditRow(AuditLog Entry, string? Actor);

public sealed class AuditModel(PortalDb db) : PageModel
{
    [BindProperty(SupportsGet = true)] public string? Action { get; set; }
    public List<AuditRow> Rows { get; private set; } = new();

    public async Task OnGetAsync(CancellationToken ct)
    {
        var q = db.AuditLogs.AsQueryable();
        if (!string.IsNullOrWhiteSpace(Action)) q = q.Where(a => a.Action.StartsWith(Action.Trim()));
        Rows = await q.OrderByDescending(a => a.Id).Take(300)
            .Select(a => new AuditRow(a, db.Users.Where(u => u.Id == a.ActorId).Select(u => u.Email).FirstOrDefault())).ToListAsync(ct);
    }
}
