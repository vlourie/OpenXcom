using System.Security.Claims;
using System.Text;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.AspNetCore.RateLimiting;
using Xp.Portal.Auth;
using Xp.Portal.Data;
using Xp.Portal.Site;
using Xp.Portal.Tickets;

namespace Xp.Portal.Pages.Team;

public sealed class TeamForm
{
    /// <summary>Idempotency key made when the form was shown: a double click makes one ticket.</summary>
    public string Key { get; set; } = "";
    public string Role { get; set; } = TeamApplyModel.Roles[0];
    public string Name { get; set; } = "";
    public string Contact { get; set; } = "";
    public string About { get; set; } = "";
    public string? Links { get; set; }
    /// <summary>Honeypot: hidden from people, filled in by bots.</summary>
    public string? Website { get; set; }
}

/// <summary>
/// "We are recruiting": the application is an ordinary ticket of the "team" category, made by the same
/// service and under the same rate limit as /tickets/new, so it has the same reader list: its author
/// (by the signed-in account or the private link) and the staff granted tickets.team, nobody else.
/// The contact lives in the ticket text, never in a public list.
/// </summary>
[EnableRateLimiting("tickets-create")]
public sealed class TeamApplyModel(TicketService tickets, Text text) : PageModel
{
    public static readonly string[] Roles = ["artists", "programmers", "translators", "testers"];
    public const int NameMax = 80, ContactMax = 200, AboutMax = 2000, LinksMax = 300;

    [BindProperty] public TeamForm Form { get; set; } = new();
    public List<string> Errors { get; } = new();
    public bool SignedIn => User.Identity?.IsAuthenticated == true;

    public void OnGet() => Form.Key = Guid.NewGuid().ToString("N");

    public async Task<IActionResult> OnPostAsync(CancellationToken ct)
    {
        if (!string.IsNullOrEmpty(Form.Website)) return Redirect("/");   // a bot: tell it nothing
        var name = TicketService.Clean(Form.Name, int.MaxValue, singleLine: true);
        var contact = TicketService.Clean(Form.Contact, int.MaxValue, singleLine: true);
        var about = TicketService.Clean(Form.About, int.MaxValue);
        var links = TicketService.Clean(Form.Links, int.MaxValue, singleLine: true);

        if (!Roles.Contains(Form.Role)) Errors.Add("team_role_invalid");
        if (name is null) Errors.Add("team_name_required");
        else if (name.Length > NameMax) Errors.Add("team_name_too_long");
        if (contact is null) Errors.Add("team_contact_required");
        else if (contact.Length > ContactMax) Errors.Add("team_contact_too_long");
        if (about is null) Errors.Add("team_about_required");
        else if (about.Length > AboutMax) Errors.Add("team_about_too_long");
        if (links is not null)
        {
            if (links.Length > LinksMax) Errors.Add("team_link_too_long");
            else if (!Uri.TryCreate(links, UriKind.Absolute, out var u) || u.Scheme is not ("http" or "https")) Errors.Add("team_link_invalid");
        }
        if (Errors.Count > 0) return Page();

        // staff read it in Russian whatever language the applicant used
        string Ru(string key) => text.In("ru", key);
        var body = new StringBuilder()
            .Append(Ru("team.ticket.role")).Append(": ").Append(Ru("team.role." + Form.Role)).Append('\n')
            .Append(Ru("team.ticket.name")).Append(": ").Append(name).Append('\n')
            .Append(Ru("team.ticket.contact")).Append(": ").Append(contact).Append('\n');
        if (links is not null) body.Append(Ru("team.ticket.links")).Append(": ").Append(links).Append('\n');
        body.Append('\n').Append(Ru("team.ticket.about")).Append(":\n").Append(about);

        var title = $"{Ru("team.ticket.title")}: {Ru("team.role." + Form.Role)} — {name}";
        if (title.Length > Limits.TitleMax) title = title[..Limits.TitleMax];

        Guid? author = SignedIn && Guid.TryParse(User.FindFirstValue(ClaimTypes.NameIdentifier), out var id) ? id : null;
        CreatedTicket created;
        try
        {
            created = await tickets.CreateAsync(new NewTicket(Categories.Team, title, body.ToString(), Language: Text.Lang), author,
                string.IsNullOrEmpty(Form.Key) ? null : "web:" + Form.Key, HttpContext.TraceIdentifier, ct);
        }
        catch (TicketException e)
        {
            Errors.Add(e.Code);
            return Page();
        }
        TempData["flash"] = "team.done";
        return created.GuestToken is { } token
            ? Redirect($"/t/{created.Ticket.Number}?k={Uri.EscapeDataString(token)}")
            : Redirect($"/t/{created.Ticket.Number}");
    }
}
