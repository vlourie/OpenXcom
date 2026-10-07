using System.Security.Claims;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.AspNetCore.RateLimiting;
using Microsoft.EntityFrameworkCore;
using Xp.Portal.Auth;
using Xp.Portal.Data;
using Xp.Portal.Site;

namespace Xp.Portal.Pages.Forum;

public sealed class ForumModel(CommunityService community) : PageModel
{
    public List<SectionCard> Sections { get; private set; } = new();

    public async Task OnGetAsync(CancellationToken ct) => Sections = await community.SectionsAsync(Text.Lang, ct);
}

public sealed class SectionModel(CommunityService community) : PageModel
{
    public ForumSection Section { get; private set; } = null!;
    public string Slug => Section.Slug;
    public string Name { get; private set; } = "";
    public string Summary { get; private set; } = "";
    public List<ForumTopic> Topics { get; private set; } = new();
    public PagerView Pager { get; private set; } = new("", 1, 1);
    public bool CanStart { get; private set; }

    public async Task<IActionResult> OnGetAsync(string section, int p, CancellationToken ct)
    {
        var s = await community.SectionAsync(section, ct);
        if (s is null) return NotFound();
        Section = s;
        var text = s.Texts.FirstOrDefault(t => t.Lang == Text.Lang) ?? s.Texts.FirstOrDefault();
        Name = text?.Name ?? s.Slug;
        Summary = text?.Summary ?? "";
        var page = Math.Max(1, p);
        var (topics, total) = await community.TopicsAsync(s.Id, page, ct);
        Topics = topics;
        Pager = PagerView.Of("/forum/" + s.Slug, page, total, CommunityLimits.TopicsPerPage);
        var viewer = new Viewer(User);
        CanStart = User.Identity?.IsAuthenticated == true && (!s.StaffOnly || viewer.CanModerateForum || viewer.IsAdmin);
        return Page();
    }
}

[EnableRateLimiting("forum-write")]
public sealed class TopicModel(CommunityService community, PortalDb db, Audit audit) : PageModel
{
    public ForumTopic Topic { get; private set; } = null!;
    public string SectionName { get; private set; } = "";
    public List<ForumPost> Posts { get; private set; } = new();
    public PagerView Pager { get; private set; } = new("", 1, 1);
    public bool CanReply { get; private set; }
    public bool CanModerate { get; private set; }
    public List<string> Errors { get; } = new();

    async Task<bool> LoadAsync(long number, int p, CancellationToken ct)
    {
        var t = await community.TopicAsync(number, ct);
        var viewer = new Viewer(User);
        // a hidden topic stays readable for the people who hid it, and for nobody else
        if (t is null || (t.Deleted && !viewer.CanModerateForum)) return false;
        Topic = t;
        var texts = t.Section?.Texts;
        SectionName = texts is { Count: > 0 } ? (texts.FirstOrDefault(x => x.Lang == Text.Lang) ?? texts[0]).Name : t.Section?.Slug ?? "";
        var page = Math.Max(1, p);
        var (posts, total) = await community.PostsAsync(t.Id, page, ct);
        Posts = posts;
        Pager = PagerView.Of("/forum/t/" + t.Number, page, total, CommunityLimits.PostsPerPage);
        CanModerate = viewer.CanModerateForum;
        CanReply = User.Identity?.IsAuthenticated == true && (!t.Locked || CanModerate);
        return true;
    }

    public async Task<IActionResult> OnGetAsync(long number, int p, CancellationToken ct) =>
        await LoadAsync(number, p, ct) ? Page() : NotFound();

    public async Task<IActionResult> OnPostReplyAsync(long number, int p, string? body, CancellationToken ct)
    {
        if (!await LoadAsync(number, p, ct)) return NotFound();
        if (!CanReply) return Forbid();
        var text = (body ?? "").Trim();
        if (text.Length == 0) { Errors.Add("forum.err.empty"); return Page(); }
        if (text.Length > CommunityLimits.PostMax) { Errors.Add("forum.err.long"); return Page(); }
        await community.ReplyAsync(Topic, Me, text, ct);
        // the new post is on the last page, and that is where the reader expects to land
        var pages = (Topic.PostCount + CommunityLimits.PostsPerPage - 1) / CommunityLimits.PostsPerPage;
        return Redirect(pages > 1 ? $"/forum/t/{number}?p={pages}" : $"/forum/t/{number}");
    }

    public async Task<IActionResult> OnPostPinAsync(long number, CancellationToken ct)
    {
        if (!await LoadAsync(number, 1, ct)) return NotFound();
        if (!CanModerate) return Forbid();
        Topic.Pinned = !Topic.Pinned;
        audit.Add(Me, "forum.pin", "t/" + number, Topic.Pinned.ToString());
        await db.SaveChangesAsync(ct);
        return Redirect($"/forum/t/{number}");
    }

    public async Task<IActionResult> OnPostLockAsync(long number, CancellationToken ct)
    {
        if (!await LoadAsync(number, 1, ct)) return NotFound();
        if (!CanModerate) return Forbid();
        Topic.Locked = !Topic.Locked;
        audit.Add(Me, "forum.lock", "t/" + number, Topic.Locked.ToString());
        await db.SaveChangesAsync(ct);
        return Redirect($"/forum/t/{number}");
    }

    Guid Me => Guid.Parse(User.FindFirstValue(ClaimTypes.NameIdentifier)!);
}

[EnableRateLimiting("forum-write")]
public sealed class NewTopicModel(CommunityService community) : PageModel
{
    public string Slug { get; private set; } = "";
    public string Name { get; private set; } = "";
    public string Title { get; private set; } = "";
    public string Body { get; private set; } = "";
    public List<string> Errors { get; } = new();

    ForumSection _section = null!;

    async Task<bool> LoadAsync(string section, CancellationToken ct)
    {
        var s = await community.SectionAsync(section, ct);
        if (s is null) return false;
        _section = s;
        Slug = s.Slug;
        var text = s.Texts.FirstOrDefault(t => t.Lang == Text.Lang) ?? s.Texts.FirstOrDefault();
        Name = text?.Name ?? s.Slug;
        return true;
    }

    bool MayStart()
    {
        var viewer = new Viewer(User);
        return !_section.StaffOnly || viewer.CanModerateForum || viewer.IsAdmin;
    }

    public async Task<IActionResult> OnGetAsync(string section, CancellationToken ct)
    {
        if (!await LoadAsync(section, ct)) return NotFound();
        return MayStart() ? Page() : Forbid();
    }

    public async Task<IActionResult> OnPostAsync(string section, string? title, string? body, CancellationToken ct)
    {
        if (!await LoadAsync(section, ct)) return NotFound();
        if (!MayStart()) return Forbid();
        Title = (title ?? "").Trim();
        Body = (body ?? "").Trim();
        if (Title.Length == 0) Errors.Add("forum.err.title");
        if (Title.Length > CommunityLimits.TitleMax) Errors.Add("forum.err.title.long");
        if (Body.Length == 0) Errors.Add("forum.err.empty");
        if (Body.Length > CommunityLimits.PostMax) Errors.Add("forum.err.long");
        if (Errors.Count > 0) return Page();
        var me = Guid.Parse(User.FindFirstValue(ClaimTypes.NameIdentifier)!);
        var topic = await community.StartTopicAsync(_section, me, Title, Body, ct);
        return Redirect($"/forum/t/{topic.Number}");
    }
}
