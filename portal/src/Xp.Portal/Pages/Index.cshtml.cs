using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.Extensions.Options;
using Xp.Portal.Site;

namespace Xp.Portal.Pages;

public sealed class IndexModel(ReleaseFeed feed, IOptions<PortalOptions> options) : PageModel
{
    public ReleaseView? Release { get; private set; }
    public string LauncherUrl => options.Value.LauncherDownloadUrl;

    public async Task OnGetAsync(CancellationToken ct) => Release = await feed.CurrentAsync(Text.Lang, ct);
}
