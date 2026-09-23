using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.Extensions.Options;
using Xp.Portal.Data;
using Xp.Portal.Site;

namespace Xp.Portal.Pages;

public sealed class IndexModel(ReleaseFeed feed, CommunityService community, IOptions<PortalOptions> options) : PageModel
{
    public ReleaseView? Release { get; private set; }
    public HomeCounts Counts { get; private set; } = new(0, 0, 0, 0);
    public List<ForumTopic> Latest { get; private set; } = new();
    public string LauncherUrl => options.Value.LauncherDownloadUrl;
    public string HeroImage => options.Value.HeroImage;

    public async Task OnGetAsync(CancellationToken ct)
    {
        Release = await feed.CurrentAsync(Text.Lang, ct);
        Counts = await community.CountsAsync(Text.Lang, ct);
        Latest = await community.LatestTopicsAsync(6, ct);
    }

    /// <summary>The board's name in the reader's language, falling back to the one that exists.</summary>
    public string SectionName(ForumTopic t)
    {
        var texts = t.Section?.Texts;
        if (texts is null || texts.Count == 0) return t.Section?.Slug ?? "";
        return (texts.FirstOrDefault(x => x.Lang == Text.Lang) ?? texts[0]).Name;
    }
}
