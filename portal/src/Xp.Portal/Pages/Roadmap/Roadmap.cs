using Microsoft.AspNetCore.Mvc.RazorPages;
using Xp.Portal.Review;
using Xp.Portal.Site;

namespace Xp.Portal.Pages.Roadmap;

/// <summary>
/// Where the art stands: how much of it players have looked at, which sets are being worked through
/// right now, and which nobody has opened yet. Everything here is counted from the verdicts people
/// sent from the launcher — the page has no numbers of its own.
/// </summary>
public sealed class RoadmapModel(Xp.Portal.Review.Roadmap roadmap, ReleaseFeed feed) : PageModel
{
    /// <summary>What is done, what is being done, what comes next — Markdown from the signed history
    /// of the channel (Выпуск/roadmap.*.md, carried by every release). Empty until a release carries it.</summary>
    public string Plan { get; private set; } = "";
    public DateTimeOffset? PlanUpdated { get; private set; }
    public RoadmapTotals Totals { get; private set; } = new(0, 0, 0, 0, 0, 0, 0, 0);
    public List<PackProgress> InProgress { get; private set; } = new();
    public List<PackProgress> Next { get; private set; } = new();
    public List<RepaintRow> Queue { get; private set; } = new();

    public int PicturesLooked => InProgress.Sum(p => p.Covered);

    public async Task OnGetAsync(CancellationToken ct)
    {
        if (await feed.NotesAsync(Text.Lang, ct) is { } notes)
        {
            Plan = notes.Roadmap;
            PlanUpdated = notes.Releases.Count > 0 ? notes.Releases[0].Published : notes.Updated;
        }
        Totals = await roadmap.TotalsAsync(ct);
        InProgress = await roadmap.ProgressAsync(null, 60, ct);
        Next = await roadmap.NextAsync(12, ct);
        Queue = await roadmap.RepaintAsync(10, ct);
    }
}

/// <summary>
/// The queue of pictures to be drawn again, most complained-about first. This is the answer to "what
/// did my evening of clicking change": a picture two different people called bad goes back to the
/// model, and the queue is the order it goes in.
/// </summary>
public sealed class RepaintQueueModel(Xp.Portal.Review.Roadmap roadmap) : PageModel
{
    public List<RepaintRow> Rows { get; private set; } = new();

    public async Task OnGetAsync(CancellationToken ct) => Rows = await roadmap.RepaintAsync(200, ct);
}
