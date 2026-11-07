using Microsoft.AspNetCore.Mvc.RazorPages;
using Xp.Portal.Site;

namespace Xp.Portal.Pages.Releases;

/// <summary>
/// Every update players have received, newest first, each with its "What's new" — the same list the
/// launcher shows. Read from the signed history in the release repository; a repository that has no
/// history yet shows the current release alone, so the page is never empty while there is a game.
/// </summary>
public sealed class ReleasesModel(ReleaseFeed feed) : PageModel
{
    public List<ReleaseView> Releases { get; private set; } = new();

    public async Task OnGetAsync(CancellationToken ct)
    {
        if (await feed.NotesAsync(Text.Lang, ct) is { Releases.Count: > 0 } notes) Releases = notes.Releases;
        else if (await feed.CurrentAsync(Text.Lang, ct) is { } current) Releases = [current];
    }
}
