using Microsoft.EntityFrameworkCore;
using Xp.Portal.Data;

namespace Xp.Portal.Site;

public sealed record ModCard(string Slug, string Name, string Summary, string? Image, string? Version, int WikiPages, int Topics);
public sealed record WikiEntry(string Slug, string Title, string? Section, WikiKind Kind);
public sealed record WikiGroup(string Section, int Count);
public sealed record SectionCard(string Slug, string Name, string Summary, string? ModSlug, bool StaffOnly, int TopicCount, int PostCount, DateTimeOffset? LastPostAt);
public sealed record HomeCounts(int Mods, int WikiPages, int Topics, int Posts);

/// <summary>
/// Everything the public pages ask the database for: sections, wiki and forum. Writes live here too,
/// because a reply has to touch three rows at once (the post, the topic's counters, the board's) and
/// doing that in a page would mean doing it differently on every page.
///
/// Every query filters by language and by published: a page half-translated shows in the language it
/// exists in, and an unpublished one shows to nobody but staff, who use the admin pages.
/// </summary>
public sealed class CommunityService(PortalDb db, TimeProvider clock)
{
    public async Task<List<ModCard>> ModsAsync(string lang, CancellationToken ct)
    {
        var rows = await db.Mods.Where(m => m.Published).OrderBy(m => m.Order).ThenBy(m => m.Slug)
            .Select(m => new
            {
                m.Id, m.Slug, m.Image, m.Version,
                Text = m.Texts.FirstOrDefault(t => t.Lang == lang) ?? m.Texts.FirstOrDefault(),
                Wiki = db.WikiPages.Count(p => p.ModId == m.Id && p.Lang == lang && p.Published),
                Topics = db.ForumTopics.Count(t => !t.Deleted && t.Section!.ModId == m.Id),
            })
            .ToListAsync(ct);
        return [.. rows.Select(r => new ModCard(r.Slug, r.Text?.Name ?? r.Slug, r.Text?.Summary ?? "",
            r.Image, r.Version, r.Wiki, r.Topics))];
    }

    public Task<GameMod?> ModAsync(string slug, CancellationToken ct) =>
        db.Mods.Include(m => m.Texts).FirstOrDefaultAsync(m => m.Slug == slug && m.Published, ct);

    /// <summary>
    /// Table of contents of one mod's wiki, in the reader's language: the groups and how many
    /// pages each holds. X-Piratez alone builds six thousand pages out of its rulesets, so the
    /// contents page names the groups and only the chosen group lists its pages.
    /// </summary>
    public async Task<List<WikiGroup>> WikiGroupsAsync(Guid modId, string lang, CancellationToken ct)
    {
        // the coalesce of a null group has to happen here, not in the query: it is the key of the
        // grouping, and the database has no name for "the pages with no group"
        var rows = await db.WikiPages.Where(p => p.ModId == modId && p.Lang == lang && p.Published)
            .GroupBy(p => p.Section)
            .Select(g => new { g.Key, Count = g.Count() })
            .ToListAsync(ct);
        return [.. rows.Select(r => new WikiGroup(r.Key ?? "", r.Count)).OrderBy(g => g.Section, StringComparer.CurrentCulture)];
    }

    /// <summary>One group of the contents, a page at a time.</summary>
    public async Task<(List<WikiEntry> Pages, int Total)> WikiGroupAsync(Guid modId, string lang, string section, int page, CancellationToken ct)
    {
        var rows = db.WikiPages.Where(p => p.ModId == modId && p.Lang == lang && p.Published
                                           && (p.Section ?? "") == section);
        var total = await rows.CountAsync(ct);
        var list = await rows.OrderBy(p => p.Title)
            .Skip((page - 1) * CommunityLimits.WikiPerPage).Take(CommunityLimits.WikiPerPage)
            .Select(p => new WikiEntry(p.Slug, p.Title, p.Section, p.Kind))
            .ToListAsync(ct);
        return (list, total);
    }

    /// <summary>
    /// One article. If it does not exist in the reader's language, the other language is served
    /// rather than a blank page - a Russian article is more use to an English reader than nothing,
    /// and the page says which language it is showing.
    /// </summary>
    public async Task<WikiPage?> WikiPageAsync(Guid modId, string slug, string lang, CancellationToken ct) =>
        await db.WikiPages.Include(p => p.Editor).FirstOrDefaultAsync(p => p.ModId == modId && p.Slug == slug && p.Lang == lang && p.Published, ct)
        ?? await db.WikiPages.Include(p => p.Editor).FirstOrDefaultAsync(p => p.ModId == modId && p.Slug == slug && p.Published, ct);

    public async Task<List<SectionCard>> SectionsAsync(string lang, CancellationToken ct)
    {
        var rows = await db.ForumSections.Where(s => s.Published).OrderBy(s => s.Order).ThenBy(s => s.Slug)
            .Select(s => new
            {
                s.Slug, s.StaffOnly, s.TopicCount, s.PostCount, s.LastPostAt,
                ModSlug = s.Mod != null ? s.Mod.Slug : null,
                Text = s.Texts.FirstOrDefault(t => t.Lang == lang) ?? s.Texts.FirstOrDefault(),
            })
            .ToListAsync(ct);
        return [.. rows.Select(r => new SectionCard(r.Slug, r.Text?.Name ?? r.Slug, r.Text?.Summary ?? "",
            r.ModSlug, r.StaffOnly, r.TopicCount, r.PostCount, r.LastPostAt))];
    }

    public Task<ForumSection?> SectionAsync(string slug, CancellationToken ct) =>
        db.ForumSections.Include(s => s.Texts).Include(s => s.Mod)
            .FirstOrDefaultAsync(s => s.Slug == slug && s.Published, ct);

    public async Task<(List<ForumTopic> Topics, int Total)> TopicsAsync(Guid sectionId, int page, CancellationToken ct)
    {
        var q = db.ForumTopics.Where(t => t.SectionId == sectionId && !t.Deleted);
        var total = await q.CountAsync(ct);
        var topics = await q.Include(t => t.Author).Include(t => t.LastPostAuthor)
            .OrderByDescending(t => t.Pinned).ThenByDescending(t => t.LastPostAt)
            .Skip((page - 1) * CommunityLimits.TopicsPerPage).Take(CommunityLimits.TopicsPerPage)
            .ToListAsync(ct);
        return (topics, total);
    }

    public Task<ForumTopic?> TopicAsync(long number, CancellationToken ct) =>
        db.ForumTopics.Include(t => t.Section).ThenInclude(s => s!.Texts).Include(t => t.Author)
            .FirstOrDefaultAsync(t => t.Number == number, ct);

    public async Task<(List<ForumPost> Posts, int Total)> PostsAsync(Guid topicId, int page, CancellationToken ct)
    {
        var q = db.ForumPosts.Where(p => p.TopicId == topicId);
        var total = await q.CountAsync(ct);
        var posts = await q.Include(p => p.Author).OrderBy(p => p.CreatedAt)
            .Skip((page - 1) * CommunityLimits.PostsPerPage).Take(CommunityLimits.PostsPerPage)
            .ToListAsync(ct);
        return (posts, total);
    }

    /// <summary>A new topic and its first post, counted into the board in the same transaction.</summary>
    public async Task<ForumTopic> StartTopicAsync(ForumSection section, Guid authorId, string title, string body, CancellationToken ct)
    {
        var now = clock.GetUtcNow();
        var topic = new ForumTopic
        {
            SectionId = section.Id, AuthorId = authorId, Title = title.Trim(),
            CreatedAt = now, LastPostAt = now, LastPostAuthorId = authorId, PostCount = 1,
        };
        db.ForumTopics.Add(topic);
        db.ForumPosts.Add(new ForumPost { TopicId = topic.Id, AuthorId = authorId, Body = body.Trim(), CreatedAt = now });
        section.TopicCount++;
        section.PostCount++;
        section.LastPostAt = now;
        await db.SaveChangesAsync(ct);
        return topic;
    }

    public async Task<ForumPost> ReplyAsync(ForumTopic topic, Guid authorId, string body, CancellationToken ct)
    {
        var now = clock.GetUtcNow();
        var post = new ForumPost { TopicId = topic.Id, AuthorId = authorId, Body = body.Trim(), CreatedAt = now };
        db.ForumPosts.Add(post);
        topic.PostCount++;
        topic.LastPostAt = now;
        topic.LastPostAuthorId = authorId;
        var section = await db.ForumSections.FirstAsync(s => s.Id == topic.SectionId, ct);
        section.PostCount++;
        section.LastPostAt = now;
        await db.SaveChangesAsync(ct);
        return post;
    }

    /// <summary>
    /// Saves an article and keeps what it said before. The revision holds the OLD text, so the
    /// history reads as "this is what the page was until that edit".
    /// </summary>
    public async Task SaveWikiAsync(WikiPage page, string title, string body, Guid? editorId, string? comment, CancellationToken ct)
    {
        if (db.Entry(page).State != EntityState.Added)
            db.WikiRevisions.Add(new WikiRevision
            {
                PageId = page.Id, Title = page.Title, Body = page.Body,
                EditorId = page.EditorId, At = page.UpdatedAt, Comment = comment,
            });
        page.Title = title.Trim();
        page.Body = body;
        page.EditorId = editorId;
        page.UpdatedAt = clock.GetUtcNow();
        await db.SaveChangesAsync(ct);
    }

    public async Task<HomeCounts> CountsAsync(string lang, CancellationToken ct) => new(
        await db.Mods.CountAsync(m => m.Published, ct),
        await db.WikiPages.CountAsync(p => p.Published && p.Lang == lang, ct),
        await db.ForumTopics.CountAsync(t => !t.Deleted, ct),
        await db.ForumPosts.CountAsync(p => !p.Deleted, ct));

    /// <summary>The last few topics, for the entrance screen.</summary>
    public Task<List<ForumTopic>> LatestTopicsAsync(int take, CancellationToken ct) =>
        db.ForumTopics.Where(t => !t.Deleted).Include(t => t.Section).ThenInclude(s => s!.Texts)
            .Include(t => t.LastPostAuthor)
            .OrderByDescending(t => t.LastPostAt).Take(take).ToListAsync(ct);
}
