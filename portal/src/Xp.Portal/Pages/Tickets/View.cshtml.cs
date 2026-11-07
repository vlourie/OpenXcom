using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.AspNetCore.RateLimiting;
using Microsoft.EntityFrameworkCore;
using Xp.Portal.Auth;
using Xp.Portal.Data;
using Xp.Portal.Files;
using Xp.Portal.Tickets;

namespace Xp.Portal.Pages.Tickets;

/// <summary>
/// The author's view of a ticket: by the secret guest link (?k=) or signed in as the author.
/// A wrong link and a missing ticket are the same 404.
/// </summary>
[EnableRateLimiting("tickets-write")]
[RequestSizeLimit(128L * 1024 * 1024)]
[RequestFormLimits(MultipartBodyLengthLimit = 128L * 1024 * 1024)]
public sealed class ViewTicketModel(PortalDb db, TicketService tickets, AttachmentService files) : PageModel
{
    public Ticket Ticket { get; private set; } = null!;
    public List<TicketMessage> Messages { get; private set; } = new();
    public List<TicketAttachment> Files { get; private set; } = new();
    public string? Token { get; private set; }
    public List<string> Errors { get; } = new();
    public bool CanReply => Ticket.Status is not (TicketStatus.Closed or TicketStatus.Duplicate or TicketStatus.Rejected);

    async Task<bool> LoadAsync(long number, string? k, CancellationToken ct)
    {
        var t = await db.Tickets.FirstOrDefaultAsync(x => x.Number == number, ct);
        if (t is null) return false;
        var viewer = new Viewer(User);
        var byLink = k is not null && t.GuestTokenHash is not null && GuestTokens.Matches(k, t.GuestTokenHash);
        if (!byLink && !viewer.IsOwner(t)) return false;
        Ticket = t;
        Token = byLink ? k : null;
        Messages = await db.TicketMessages.Where(m => m.TicketId == t.Id && !m.Internal).OrderBy(m => m.CreatedAt).ToListAsync(ct);
        Files = await db.TicketAttachments.Where(a => a.TicketId == t.Id).OrderBy(a => a.CreatedAt).ToListAsync(ct);
        // the page carries the secret link: no copies in caches, no Referer (set site-wide)
        Response.Headers.CacheControl = "no-store";
        return true;
    }

    IActionResult Back() => Token is null ? Redirect($"/t/{Ticket.Number}") : Redirect($"/t/{Ticket.Number}?k={Uri.EscapeDataString(Token)}");

    public async Task<IActionResult> OnGetAsync(long number, string? k, CancellationToken ct)
    {
        if (await LoadAsync(number, k, ct)) return Page();
        // staff reach tickets through the admin page, which checks their category and second factor
        var viewer = new Viewer(User);
        if (viewer.IsAdmin && await db.Tickets.FirstOrDefaultAsync(x => x.Number == number, ct) is { } t && viewer.IsStaffFor(t))
            return Redirect($"/admin/tickets/{number}");
        return NotFound();
    }

    public async Task<IActionResult> OnPostReplyAsync(long number, string? k, string? body, CancellationToken ct)
    {
        if (!await LoadAsync(number, k, ct)) return NotFound();
        try { await tickets.AddMessageAsync(Ticket, body ?? "", new Viewer(User).UserId is { } u && Ticket.AuthorId == u ? u : null, false, false, ct); }
        catch (TicketException e)
        {
            Errors.Add(e.Code);
            return Page();
        }
        TempData["flash"] = "view.sent";
        return Back();
    }

    public async Task<IActionResult> OnPostFileAsync(long number, string? k, IFormFile? file, CancellationToken ct)
    {
        if (!await LoadAsync(number, k, ct)) return NotFound();
        if (file is null || file.Length == 0) Errors.Add("file_required");
        else if (FileRules.KindOf(file.FileName) is not { } kind) Errors.Add("file_type_not_allowed");
        else if (!FileRules.IsImage(kind) && !Ticket.ConsentToFiles) Errors.Add("consent_required");
        else
        {
            try
            {
                await using var s = file.OpenReadStream();
                await files.AddAsync(Ticket, file.FileName, s, ct);
                TempData["flash"] = "view.uploaded";
                return Back();
            }
            catch (TicketException e) { Errors.Add(e.Code); }
        }
        return Page();
    }
}
