using Microsoft.AspNetCore.Mvc.RazorPages;
using Xp.Portal.Site;

namespace Xp.Portal.Pages.Roadmap;

/// <summary>
/// The plan of the game: what is done, what is being done, what comes next. It is the Markdown the
/// signed history of the channel carries — the page has no numbers of its own. (Players' art verdicts
/// are still accepted at /api/v1/review, but the site no longer shows them.)
/// </summary>
public sealed class RoadmapModel(ReleaseFeed feed) : PageModel
{
    /// <summary>What is done, what is being done, what comes next — Markdown from the signed history
    /// of the channel (Выпуск/roadmap.*.md, carried by every release). Empty until a release carries it.</summary>
    public string Plan { get; private set; } = "";
    public DateTimeOffset? PlanUpdated { get; private set; }

    public async Task OnGetAsync(CancellationToken ct)
    {
        if (await feed.NotesAsync(Text.Lang, ct) is { } notes)
        {
            Plan = notes.Roadmap;
            PlanUpdated = notes.Releases.Count > 0 ? notes.Releases[0].Published : notes.Updated;
        }
    }
}
