using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.EntityFrameworkCore;
using Xp.Portal.Data;
using Xp.Portal.Site;

namespace Xp.Portal.Pages.Mods;

public sealed class ModsModel(CommunityService community) : PageModel
{
    public List<ModCard> Mods { get; private set; } = new();

    public async Task OnGetAsync(CancellationToken ct) => Mods = await community.ModsAsync(Text.Lang, ct);
}

public sealed class ModPageModel(CommunityService community, PortalDb db) : PageModel
{
    public GameMod Mod { get; private set; } = null!;
    public string Name { get; private set; } = "";
    public string Summary { get; private set; } = "";
    public string Body { get; private set; } = "";
    public List<WikiGroup> Groups { get; private set; } = new();
    public int WikiPages => Groups.Sum(g => g.Count);
    /// <summary>The board that belongs to this mod, if it has one.</summary>
    public string? ForumSlug { get; private set; }

    public async Task<IActionResult> OnGetAsync(string slug, CancellationToken ct)
    {
        var mod = await community.ModAsync(slug, ct);
        if (mod is null) return NotFound();
        Mod = mod;
        // a mod described in one language only still has a page: show what exists
        var text = mod.Texts.FirstOrDefault(t => t.Lang == Text.Lang) ?? mod.Texts.FirstOrDefault();
        Name = text?.Name ?? mod.Slug;
        Summary = text?.Summary ?? "";
        Body = text?.Body ?? "";
        Groups = await community.WikiGroupsAsync(mod.Id, Text.Lang, ct);
        ForumSlug = await db.ForumSections.Where(s => s.ModId == mod.Id && s.Published)
            .OrderBy(s => s.Order).Select(s => s.Slug).FirstOrDefaultAsync(ct);
        return Page();
    }
}
