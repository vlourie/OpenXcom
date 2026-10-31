using System.Security.Claims;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.AspNetCore.RateLimiting;
using Microsoft.Extensions.Options;
using Xp.Portal.Auth;
using Xp.Portal.Data;
using Xp.Portal.Files;
using Xp.Portal.Site;
using Xp.Portal.Tickets;

namespace Xp.Portal.Pages.Tickets;

public sealed class TicketForm
{
    /// <summary>Idempotency key made when the form was shown: a double click makes one ticket.</summary>
    public string Key { get; set; } = "";
    public string Category { get; set; } = Categories.Code;
    public string Title { get; set; } = "";
    public string Description { get; set; } = "";
    public string? Steps { get; set; }
    public string? Expected { get; set; }
    public string? Actual { get; set; }
    public string? GameVersion { get; set; }
    public string? ModVersion { get; set; }
    public string? Email { get; set; }
    public bool Consent { get; set; }
    /// <summary>Honeypot: hidden from people, filled in by bots.</summary>
    public string? Website { get; set; }
}

[EnableRateLimiting("tickets-create")]
[RequestSizeLimit(MaxBody)]
[RequestFormLimits(MultipartBodyLengthLimit = MaxBody)]
public sealed class NewTicketModel(TicketService tickets, AttachmentService files, PortalDb db, IOptions<AttachmentOptions> fileOptions) : PageModel
{
    // the transport ceiling only; the real limits are AttachmentOptions, checked file by file
    const long MaxBody = 512L * 1024 * 1024;

    [BindProperty] public TicketForm Form { get; set; } = new();
    public List<string> Errors { get; } = new();
    public bool SignedIn => User.Identity?.IsAuthenticated == true;
    public int MaxFiles => fileOptions.Value.MaxFilesPerTicket;
    public long MaxFileMb => Math.Max(1, fileOptions.Value.MaxFileBytes / (1024 * 1024));

    public void OnGet() => Form.Key = Guid.NewGuid().ToString("N");

    public async Task<IActionResult> OnPostAsync(CancellationToken ct)
    {
        if (!string.IsNullOrEmpty(Form.Website)) return Redirect("/");   // a bot: tell it nothing
        var uploads = Request.Form.Files.Where(f => f.Length > 0).ToList();
        if (uploads.Count > MaxFiles) Errors.Add("too_many_files");
        foreach (var f in uploads)
        {
            var kind = FileRules.KindOf(f.FileName);
            if (kind is null) Errors.Add("file_type_not_allowed");
            else if (!FileRules.IsImage(kind.Value) && !Form.Consent) Errors.Add("consent_required");
        }
        if (Errors.Count > 0) return Page();

        Guid? author = SignedIn && Guid.TryParse(User.FindFirstValue(ClaimTypes.NameIdentifier), out var id) ? id : null;
        CreatedTicket created;
        try
        {
            created = await tickets.CreateAsync(new NewTicket(Form.Category, Form.Title, Form.Description, Form.Steps, Form.Expected, Form.Actual,
                Form.GameVersion, Form.ModVersion, null, author is null ? Form.Email : null, Form.Consent,
                Language: Text.Lang), author,
                string.IsNullOrEmpty(Form.Key) ? null : "web:" + Form.Key, HttpContext.TraceIdentifier, ct);
        }
        catch (TicketException e)
        {
            Errors.Add(e.Code);
            return Page();
        }

        var failed = false;
        if (!created.Replayed)
        {
            var t = await db.Tickets.FindAsync([created.Ticket.Id], ct) ?? created.Ticket;
            foreach (var f in uploads)
            {
                try
                {
                    await using var s = f.OpenReadStream();
                    await files.AddAsync(t, f.FileName, s, ct);
                }
                catch (TicketException) { failed = true; }
            }
        }
        TempData["flash"] = failed ? "new.done.files_failed" : "new.done";
        return created.GuestToken is { } token
            ? Redirect($"/t/{created.Ticket.Number}?k={Uri.EscapeDataString(token)}")
            : Redirect($"/t/{created.Ticket.Number}");
    }
}
