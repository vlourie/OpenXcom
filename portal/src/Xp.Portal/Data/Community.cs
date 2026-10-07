namespace Xp.Portal.Data;

/// <summary>
/// A mod the site keeps a section for: X-Piratez itself, our HD layer, anything else we host pages
/// about. The row carries nothing a reader sees in words - names and descriptions live in
/// <see cref="ModText"/>, one row per language, so a mod may be described in Russian before anyone
/// has written the English text.
/// </summary>
public sealed class GameMod
{
    public Guid Id { get; set; } = Guid.NewGuid();
    /// <summary>Address of the section: /mods/piratez. Lowercase letters, digits and dashes.</summary>
    public string Slug { get; set; } = "";
    public int Order { get; set; }
    public bool Published { get; set; }
    public string? Author { get; set; }
    public string? HomeUrl { get; set; }
    public string? DownloadUrl { get; set; }
    /// <summary>Version of the mod the generated wiki pages were built from.</summary>
    public string? Version { get; set; }
    /// <summary>File name under wwwroot/img/mods. Empty until the picture is drawn.</summary>
    public string? Image { get; set; }
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
    public DateTimeOffset UpdatedAt { get; set; } = DateTimeOffset.UtcNow;
    public List<ModText> Texts { get; set; } = new();
}

public sealed class ModText
{
    public Guid ModId { get; set; }
    public string Lang { get; set; } = "";
    public string Name { get; set; } = "";
    public string Summary { get; set; } = "";
    /// <summary>The section's own page, in Markdown.</summary>
    public string Body { get; set; } = "";
}

/// <summary>
/// Where a wiki page came from. A generated page is rebuilt from the mod's rulesets on every import
/// and hand edits to it would be lost, so the two kinds are kept apart and marked apart on screen.
/// </summary>
public enum WikiKind { Manual, Generated }

public sealed class WikiPage
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public Guid ModId { get; set; }
    public GameMod? Mod { get; set; }
    /// <summary>Address inside the mod's wiki: /wiki/piratez/gauss-pistol.</summary>
    public string Slug { get; set; } = "";
    public string Lang { get; set; } = "";
    public string Title { get; set; } = "";
    public string Body { get; set; } = "";
    /// <summary>Group in the mod's table of contents: "weapons", "armour", "research".</summary>
    public string? Section { get; set; }
    public WikiKind Kind { get; set; } = WikiKind.Manual;
    /// <summary>For a generated page: what it was built from, e.g. "Piratez_Items.rul STR_GAUSS_PISTOL".</summary>
    public string? Source { get; set; }
    /// <summary>Version of the mod a generated page was built from; shown to the reader.</summary>
    public string? SourceVersion { get; set; }
    public bool Published { get; set; } = true;
    public Guid? EditorId { get; set; }
    public PortalUser? Editor { get; set; }
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
    public DateTimeOffset UpdatedAt { get; set; } = DateTimeOffset.UtcNow;
}

/// <summary>The page as it was before an edit. Kept for every change, so a wrong edit is undone by reading.</summary>
public sealed class WikiRevision
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public Guid PageId { get; set; }
    public string Title { get; set; } = "";
    public string Body { get; set; } = "";
    public string? Comment { get; set; }
    public Guid? EditorId { get; set; }
    public PortalUser? Editor { get; set; }
    public DateTimeOffset At { get; set; } = DateTimeOffset.UtcNow;
}

/// <summary>
/// A board of the forum. A section may belong to a mod (then it shows up in that mod's section too)
/// or stand on its own, like "off topic".
/// </summary>
public sealed class ForumSection
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public string Slug { get; set; } = "";
    public int Order { get; set; }
    public Guid? ModId { get; set; }
    public GameMod? Mod { get; set; }
    /// <summary>Nobody but staff may start a topic here: announcements, rules.</summary>
    public bool StaffOnly { get; set; }
    public bool Published { get; set; } = true;
    public int TopicCount { get; set; }
    public int PostCount { get; set; }
    public DateTimeOffset? LastPostAt { get; set; }
    public List<ForumSectionText> Texts { get; set; } = new();
}

public sealed class ForumSectionText
{
    public Guid SectionId { get; set; }
    public string Lang { get; set; } = "";
    public string Name { get; set; } = "";
    public string Summary { get; set; } = "";
}

public sealed class ForumTopic
{
    public Guid Id { get; set; } = Guid.NewGuid();
    /// <summary>Human number in the address: /forum/t/1234-title. Unique across the forum.</summary>
    public long Number { get; set; }
    public Guid SectionId { get; set; }
    public ForumSection? Section { get; set; }
    public Guid AuthorId { get; set; }
    public PortalUser? Author { get; set; }
    public string Title { get; set; } = "";
    public bool Pinned { get; set; }
    public bool Locked { get; set; }
    /// <summary>Hidden by a moderator. The row stays, so the moderation can be read back and undone.</summary>
    public bool Deleted { get; set; }
    public int PostCount { get; set; }
    public int Views { get; set; }
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
    public DateTimeOffset LastPostAt { get; set; } = DateTimeOffset.UtcNow;
    public Guid? LastPostAuthorId { get; set; }
    public PortalUser? LastPostAuthor { get; set; }
}

public sealed class ForumPost
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public Guid TopicId { get; set; }
    public ForumTopic? Topic { get; set; }
    public Guid AuthorId { get; set; }
    public PortalUser? Author { get; set; }
    public string Body { get; set; } = "";
    public bool Deleted { get; set; }
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
    public DateTimeOffset? EditedAt { get; set; }
    public Guid? EditedById { get; set; }
}

public static class CommunityLimits
{
    public const int SlugMax = 64;
    public const int NameMax = 120;
    public const int SummaryMax = 400;
    public const int TitleMax = 160;
    /// <summary>A wiki article. Long on purpose: a generated weapon page with tables is not short.</summary>
    public const int ArticleMax = 120_000;
    public const int PostMax = 20_000;
    public const int PostsPerPage = 20;
    public const int TopicsPerPage = 30;
    public const int WikiPerPage = 100;
}
