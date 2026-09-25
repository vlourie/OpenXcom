using Microsoft.EntityFrameworkCore;
using Xp.Portal.Data;

namespace Xp.Portal.Review;

/// <summary>
/// One set on the roadmap. <c>Covered</c> is how many different pictures of the set somebody has
/// judged, <c>Confirmed</c> how many two different people judged; the state is read off those two,
/// not off "a file arrived" — a person may mark three frames out of forty one and press send.
/// </summary>
public sealed class PackProgress
{
    public string Section { get; set; } = "";
    public string Set { get; set; } = "";
    public int Frames { get; set; }
    public int Pictures { get; set; }
    public double CellShare { get; set; }
    public int Reviewers { get; set; }
    public int Covered { get; set; }
    public int Confirmed { get; set; }
    public int Bad { get; set; }

    /// <summary>How many pictures there are to judge — never less than the number already judged.</summary>
    public int Denominator => Math.Max(Pictures, Covered);

    public string State =>
        Covered == 0 ? "none"
        : Confirmed >= Denominator ? "confirmed"
        : Covered >= Denominator ? "checked"
        : "partial";

    /// <summary>How much of the set is looked at, in percent — what the bar on the page shows.</summary>
    public int Percent => Denominator == 0 ? 0 : (int)Math.Round(100.0 * Covered / Denominator);
}

/// <summary>Everything in one line: how much art there is and how much of it has been looked at.</summary>
public sealed record RoadmapTotals(int Packs, int Frames, int Pictures, int Started, int Checked, int Confirmed, int Reviews, int Reviewers);

/// <summary>
/// A picture people asked to be repainted, the most complained-about first. This queue is the whole
/// point of the review: it is what the model gets to draw again (review_pull.py).
/// </summary>
public sealed class RepaintRow
{
    public string Hd { get; set; } = "";
    public string Orig { get; set; } = "";
    public int People { get; set; }
    public int Packs { get; set; }
    public string Sets { get; set; } = "";
    public string Reasons { get; set; } = "";
}

/// <summary>What one person has done, for their own page.</summary>
public sealed record MyReviewWork(int Packs, int Pictures, int Bad, int WentToRepaint, DateTimeOffset? Last);

/// <summary>
/// The numbers of the art roadmap. Every one of them is counted from the verdicts themselves, so a
/// result taken out of the count — revoked by a moderator, or replaced by its own author — changes
/// the page by itself and nothing has to be recalculated by hand.
/// </summary>
public sealed class Roadmap(PortalDb db)
{
    /// <summary>
    /// Sets somebody has already looked at, the least finished first. A set nobody has touched is not
    /// here: there are 626 of them, and a list of untouched names says nothing — what to check next
    /// is the question <see cref="NextAsync"/> answers.
    /// </summary>
    public async Task<List<PackProgress>> ProgressAsync(string? section, int take, CancellationToken ct)
    {
        var rows = await db.Database.SqlQuery<PackProgress>($"""
            with live as (
                select r."Id", r."Section", r."SetName", r."UserId", r."PlanPictures"
                from "PackReviews" r
                where r."SupersededAt" is null and r."RevokedAt" is null
            ),
            picture as (
                select l."Section", l."SetName", f."Orig",
                       count(distinct l."UserId") as people,
                       count(*) filter (where f."Verdict" = 'bad') as bad
                from "PackReviewFrames" f
                join live l on l."Id" = f."ReviewId"
                where f."Verdict" <> ''
                group by l."Section", l."SetName", f."Orig"
            ),
            per_set as (
                select "Section", "SetName", count(*) as covered,
                       count(*) filter (where people >= 2) as confirmed,
                       sum(bad) as bad
                from picture group by "Section", "SetName"
            ),
            who as (
                select "Section", "SetName", count(distinct "UserId") as reviewers, max("PlanPictures") as plan
                from live group by "Section", "SetName"
            )
            select s."Section" as "Section", s."SetName" as "Set",
                   coalesce(p."Frames", 0) as "Frames",
                   greatest(coalesce(p."Pictures", 0), coalesce(w.plan, 0))::int as "Pictures",
                   coalesce(p."CellShare", 0) as "CellShare",
                   coalesce(w.reviewers, 0)::int as "Reviewers",
                   s.covered::int as "Covered",
                   s.confirmed::int as "Confirmed",
                   coalesce(s.bad, 0)::int as "Bad"
            from per_set s
            left join who w on w."Section" = s."Section" and w."SetName" = s."SetName"
            left join "ArtPacks" p on p."Section" = s."Section" and p."Name" = s."SetName"
            order by s.covered::float
                     / greatest(coalesce(p."Pictures", 0), coalesce(w.plan, 0), s.covered) asc,
                     coalesce(p."CellShare", 0) desc
            """).ToListAsync(ct);

        if (!string.IsNullOrEmpty(section))
            rows = rows.Where(r => string.Equals(r.Section, section, StringComparison.OrdinalIgnoreCase)).ToList();
        return take >= rows.Count ? rows : rows.Take(take).ToList();
    }

    public async Task<RoadmapTotals> TotalsAsync(CancellationToken ct)
    {
        var packs = await db.ArtPacks.Where(p => p.HdFrames > 0)
            .GroupBy(_ => 1)
            .Select(g => new { Packs = g.Count(), Frames = g.Sum(p => p.Frames), Pictures = g.Sum(p => p.Pictures) })
            .FirstOrDefaultAsync(ct);
        var live = db.PackReviews.Where(r => r.SupersededAt == null && r.RevokedAt == null);
        var reviews = await live.CountAsync(ct);
        var reviewers = await live.Select(r => r.UserId).Distinct().CountAsync(ct);

        var states = (await ProgressAsync(null, int.MaxValue, ct)).Select(p => p.State).ToList();
        return new RoadmapTotals(
            packs?.Packs ?? 0, packs?.Frames ?? 0, packs?.Pictures ?? 0,
            states.Count, states.Count(s => s is "checked" or "confirmed"), states.Count(s => s == "confirmed"),
            reviews, reviewers);
    }

    /// <summary>What to look at next: nobody has been here, and the maps are full of it.</summary>
    public async Task<List<PackProgress>> NextAsync(int take, CancellationToken ct)
    {
        var seen = db.PackReviews.Where(r => r.SupersededAt == null && r.RevokedAt == null)
            .Select(r => new { r.Section, r.SetName });
        return await db.ArtPacks.Where(p => p.HdFrames > 0 && !seen.Any(s => s.Section == p.Section && s.SetName == p.Name))
            .OrderByDescending(p => p.CellShare).ThenBy(p => p.Name).Take(take)
            .Select(p => new PackProgress
            {
                Section = p.Section, Set = p.Name, Frames = p.Frames, Pictures = p.Pictures, CellShare = p.CellShare,
            })
            .ToListAsync(ct);
    }

    /// <summary>
    /// The repaint queue: pictures called bad, by how many different people. Different people is the
    /// whole trick — one person pressing "bad" ten times on the same picture is still one complaint.
    /// </summary>
    public async Task<List<RepaintRow>> RepaintAsync(int take, CancellationToken ct) =>
        await db.Database.SqlQuery<RepaintRow>($"""
            with live as (
                select r."Id", r."Section", r."SetName", r."UserId"
                from "PackReviews" r
                where r."SupersededAt" is null and r."RevokedAt" is null
            ),
            bad as (
                select f."Id", f."Hd", f."Orig", f."Reasons", l."SetName", l."Section", l."UserId"
                from "PackReviewFrames" f
                join live l on l."Id" = f."ReviewId"
                where f."Verdict" = 'bad'
            )
            select b."Hd" as "Hd",
                   min(b."Orig") as "Orig",
                   count(distinct b."UserId")::int as "People",
                   count(distinct b."Section" || '/' || b."SetName")::int as "Packs",
                   string_agg(distinct b."SetName", ', ') as "Sets",
                   coalesce((select string_agg(distinct reason, ', ')
                             from bad b2, unnest(b2."Reasons") as reason
                             where b2."Hd" = b."Hd"), '') as "Reasons"
            from bad b
            group by b."Hd"
            order by count(distinct b."UserId") desc, count(*) desc, b."Hd"
            limit {take}
            """).ToListAsync(ct);

    /// <summary>What this person has done, and how much of it turned into work for the model.</summary>
    public async Task<MyReviewWork> MineAsync(Guid userId, CancellationToken ct)
    {
        var mine = db.PackReviews.Where(r => r.UserId == userId && r.SupersededAt == null && r.RevokedAt == null);
        var packs = await mine.CountAsync(ct);
        if (packs == 0) return new MyReviewWork(0, 0, 0, 0, null);

        var frames = db.PackReviewFrames.Where(f => f.Verdict != "" && mine.Any(r => r.Id == f.ReviewId));
        var pictures = await frames.Select(f => f.Hd).Distinct().CountAsync(ct);
        var bad = await frames.Where(f => f.Verdict == "bad").Select(f => f.Hd).Distinct().CountAsync(ct);
        var last = await mine.MaxAsync(r => (DateTimeOffset?)r.SubmittedAt, ct);

        // a complaint becomes work for the model when a second person agrees: the queue is built that way
        var queue = await RepaintAsync(500, ct);
        var mineBad = await frames.Where(f => f.Verdict == "bad").Select(f => f.Hd).Distinct().ToListAsync(ct);
        var seconded = queue.Count(q => q.People >= 2 && mineBad.Contains(q.Hd));

        return new MyReviewWork(packs, pictures, bad, seconded, last);
    }
}
