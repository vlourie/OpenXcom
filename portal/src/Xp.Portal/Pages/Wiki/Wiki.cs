using System.Security.Claims;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.EntityFrameworkCore;
using Xp.Portal.Auth;
using Xp.Portal.Data;
using Xp.Portal.Site;

namespace Xp.Portal.Pages.Wiki;

public sealed class WikiHomeModel(CommunityService community) : PageModel
{
    public List<ModCard> Mods { get; private set; } = new();

    public async Task OnGetAsync(CancellationToken ct) =>
        Mods = [.. (await community.ModsAsync(Text.Lang, ct)).Where(m => m.WikiPages > 0)];
}

public sealed class ContentsModel(CommunityService community, PortalDb db) : PageModel
{
    public string ModSlug { get; private set; } = "";
    public string ModName { get; private set; } = "";
    public string Query { get; private set; } = "";
    public string Group { get; private set; } = "";
    public List<WikiGroup> Groups { get; private set; } = new();
    public List<WikiEntry> Pages { get; private set; } = new();
    public PagerView Pager { get; private set; } = new("", 1, 1);
    public bool CanEdit { get; private set; }

    public async Task<IActionResult> OnGetAsync(string mod, string? q, string? s, int p, CancellationToken ct)
    {
        var m = await community.ModAsync(mod, ct);
        if (m is null) return NotFound();
        ModSlug = m.Slug;
        ModName = (m.Texts.FirstOrDefault(t => t.Lang == Text.Lang) ?? m.Texts.FirstOrDefault())?.Name ?? m.Slug;
        CanEdit = new Viewer(User).CanEditWiki;
        Query = (q ?? "").Trim();
        Groups = await community.WikiGroupsAsync(m.Id, Text.Lang, ct);
        if (Query.Length == 0)
        {
            // no group chosen and only one exists: skip the extra click
            Group = (s ?? "").Trim();
            if (Group.Length == 0 && Groups.Count == 1) Group = Groups[0].Section;
            if (Group.Length == 0 && Groups.Count == 0) return Page();
            if (Group.Length == 0) return Page();
            var page = Math.Max(1, p);
            var (list, total) = await community.WikiGroupAsync(m.Id, Text.Lang, Group, page, ct);
            Pages = list;
            Pager = PagerView.Of($"/wiki/{m.Slug}?s={Uri.EscapeDataString(Group)}", page, total, CommunityLimits.WikiPerPage);
            return Page();
        }
        // the title first, then the text: a search for "gauss" should put the page about it on top.
        // ILIKE folds case by the collation of the column, and a database created in the C locale
        // folds ASCII only - "альф" would not find "Альфа". The collation is named here so the
        // search works the same whatever locale the server was set up in.
        var pattern = "%" + Query.Replace("%", "").Replace("_", "") + "%";
        Pages = await db.WikiPages
            .Where(p => p.ModId == m.Id && p.Lang == Text.Lang && p.Published
                        && (EF.Functions.ILike(EF.Functions.Collate(p.Title, Search.Collation), pattern)
                            || EF.Functions.ILike(EF.Functions.Collate(p.Body, Search.Collation), pattern)))
            .OrderByDescending(p => EF.Functions.ILike(EF.Functions.Collate(p.Title, Search.Collation), pattern)).ThenBy(p => p.Title)
            .Take(100)
            .Select(p => new WikiEntry(p.Slug, p.Title, p.Section, p.Kind))
            .ToListAsync(ct);
        return Page();
    }
}

public sealed class ArticleModel(CommunityService community) : PageModel
{
    public WikiPage Article { get; private set; } = null!;
    public string ModSlug { get; private set; } = "";
    public string ModName { get; private set; } = "";
    public bool OtherLanguage { get; private set; }
    public bool CanEdit { get; private set; }

    public async Task<IActionResult> OnGetAsync(string mod, string slug, CancellationToken ct)
    {
        var m = await community.ModAsync(mod, ct);
        if (m is null) return NotFound();
        var p = await community.WikiPageAsync(m.Id, slug, Text.Lang, ct);
        if (p is null) return NotFound();
        Article = p;
        ModSlug = m.Slug;
        ModName = (m.Texts.FirstOrDefault(t => t.Lang == Text.Lang) ?? m.Texts.FirstOrDefault())?.Name ?? m.Slug;
        OtherLanguage = p.Lang != Text.Lang;
        CanEdit = new Viewer(User).CanEditWiki;
        return Page();
    }
}

public sealed class HistoryModel(CommunityService community, PortalDb db) : PageModel
{
    public string ModSlug { get; private set; } = "";
    public string ModName { get; private set; } = "";
    public string Slug { get; private set; } = "";
    public string PageTitle { get; private set; } = "";
    public List<WikiRevision> Revisions { get; private set; } = new();

    public async Task<IActionResult> OnGetAsync(string mod, string slug, CancellationToken ct)
    {
        var m = await community.ModAsync(mod, ct);
        if (m is null) return NotFound();
        var p = await community.WikiPageAsync(m.Id, slug, Text.Lang, ct);
        if (p is null) return NotFound();
        ModSlug = m.Slug;
        ModName = (m.Texts.FirstOrDefault(t => t.Lang == Text.Lang) ?? m.Texts.FirstOrDefault())?.Name ?? m.Slug;
        Slug = p.Slug;
        PageTitle = p.Title;
        Revisions = await db.WikiRevisions.Include(r => r.Editor).Where(r => r.PageId == p.Id)
            .OrderByDescending(r => r.At).Take(100).ToListAsync(ct);
        return Page();
    }
}

/// <summary>
/// Writing an article. Only somebody with wiki.edit gets here, and a generated page says out loud
/// that the next import will overwrite what is being typed - the two kinds of page are not mixed
/// silently.
/// </summary>
public sealed class EditModel(CommunityService community, PortalDb db, Audit audit) : PageModel
{
    public string ModSlug { get; private set; } = "";
    public string ModName { get; private set; } = "";
    public bool IsNew { get; private set; }
    public bool WasGenerated { get; private set; }
    public string Title { get; private set; } = "";
    public string Slug { get; private set; } = "";
    public string Section { get; private set; } = "";
    public string Body { get; private set; } = "";
    public bool Published { get; private set; } = true;
    public string? Preview { get; private set; }
    public List<string> Errors { get; } = new();

    GameMod _mod = null!;
    WikiPage? _page;

    async Task<bool> LoadAsync(string mod, string slug, CancellationToken ct)
    {
        var m = await community.ModAsync(mod, ct);
        if (m is null) return false;
        _mod = m;
        ModSlug = m.Slug;
        ModName = (m.Texts.FirstOrDefault(t => t.Lang == Text.Lang) ?? m.Texts.FirstOrDefault())?.Name ?? m.Slug;
        IsNew = slug == "new";
        if (IsNew) return true;
        _page = await db.WikiPages.FirstOrDefaultAsync(p => p.ModId == m.Id && p.Slug == slug && p.Lang == Text.Lang, ct);
        if (_page is null) return false;
        WasGenerated = _page.Kind == WikiKind.Generated;
        Title = _page.Title;
        Slug = _page.Slug;
        Section = _page.Section ?? "";
        Body = _page.Body;
        Published = _page.Published;
        return true;
    }

    public async Task<IActionResult> OnGetAsync(string mod, string slug, CancellationToken ct)
    {
        if (!new Viewer(User).CanEditWiki) return Forbid();
        return await LoadAsync(mod, slug, ct) ? Page() : NotFound();
    }

    public async Task<IActionResult> OnPostPreviewAsync(string mod, string slug, string? title, string? body,
        string? section, string? pageSlug, CancellationToken ct)
    {
        if (!new Viewer(User).CanEditWiki) return Forbid();
        if (!await LoadAsync(mod, slug, ct)) return NotFound();
        Title = title ?? "";
        Body = body ?? "";
        Section = section ?? "";
        if (!string.IsNullOrWhiteSpace(pageSlug)) Slug = pageSlug;
        Preview = Body;
        return Page();
    }

    public async Task<IActionResult> OnPostSaveAsync(string mod, string slug, string? title, string? body,
        string? section, string? pageSlug, string? comment, bool published, CancellationToken ct)
    {
        if (!new Viewer(User).CanEditWiki) return Forbid();
        if (!await LoadAsync(mod, slug, ct)) return NotFound();
        Title = (title ?? "").Trim();
        Body = body ?? "";
        Section = (section ?? "").Trim();
        Published = published;
        Slug = string.IsNullOrWhiteSpace(pageSlug) ? Slugs.Make(Title) : pageSlug.Trim();

        if (Title.Length == 0) Errors.Add("wiki.err.title");
        if (Body.Trim().Length == 0) Errors.Add("wiki.err.body");
        if (!Slugs.IsValid(Slug)) Errors.Add("wiki.err.slug");
        var modId = _mod.Id;
        var lang = Text.Lang;
        var mine = _page?.Id;
        if (Errors.Count == 0 && await db.WikiPages.AnyAsync(
                p => p.ModId == modId && p.Lang == lang && p.Slug == Slug && p.Id != mine, ct))
            Errors.Add("wiki.err.taken");
        if (Errors.Count > 0) return Page();

        var editor = User.FindFirstValue(ClaimTypes.NameIdentifier) is { } s && Guid.TryParse(s, out var id) ? id : (Guid?)null;
        if (_page is null)
        {
            _page = new WikiPage { ModId = _mod.Id, Lang = Text.Lang, Kind = WikiKind.Manual };
            db.WikiPages.Add(_page);
        }
        _page.Slug = Slug;
        _page.Section = Section.Length > 0 ? Section : null;
        _page.Published = Published;
        await community.SaveWikiAsync(_page, Title, Body, editor, comment, ct);
        audit.Add(editor, "wiki.save", _mod.Slug + "/" + Slug, comment);
        await db.SaveChangesAsync(ct);
        TempData["flash"] = "wiki.saved";
        return Redirect($"/wiki/{_mod.Slug}/{Slug}");
    }
}
