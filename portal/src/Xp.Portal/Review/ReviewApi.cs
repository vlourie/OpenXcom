using System.Security.Cryptography;
using System.Text;
using Microsoft.AspNetCore.Http.Features;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Xp.Portal.Data;
using Xp.Portal.Devices;

namespace Xp.Portal.Review;

/// <summary>One picture's verdict, exactly as the launcher writes it into its file.</summary>
public sealed class FrameVerdict
{
    public int Frame { get; set; }
    public string Orig { get; set; } = "";
    public string Hd { get; set; } = "";
    public string Verdict { get; set; } = "";
    public List<string> Reasons { get; set; } = new();
    public string Note { get; set; } = "";
}

/// <summary>One pack's block of the envelope.</summary>
public sealed class PackVerdicts
{
    public string Section { get; set; } = "TERRAIN";
    public string Set { get; set; } = "";
    public string ModVersion { get; set; } = "";
    /// <summary>How many different pictures the launcher offered in this set — the denominator of "checked".</summary>
    public int Pictures { get; set; }
    public List<FrameVerdict> Frames { get; set; } = new();
}

public sealed class VerdictEnvelope
{
    public string Tool { get; set; } = "";
    public DateTimeOffset CheckedAt { get; set; }
    public List<PackVerdicts> Packs { get; set; } = new();
}

/// <summary>What came of it. <c>Replaced</c> is the sender's own earlier results that stopped counting.</summary>
public sealed record ReviewAccepted(int Packs, int Frames, int Replaced, Guid[] ReviewIds);

/// <summary>A set worth checking next, and why it is in the queue.</summary>
public sealed record QueueSet(string Section, string Set, int Frames, int Pictures, int Reviews, double CellShare);

/// <summary>
/// Taking in what people saw. The launcher shows the original beside the pack's picture and sends a
/// verdict per picture; the roadmap and the repaint queue are counted from these rows and from
/// nothing else, so a revoked result changes every number by itself.
/// </summary>
public static class ReviewApi
{
    /// <summary>Kestrel cuts a body at 30 MB before our own limits are even reached (rake R-053).</summary>
    public const long BodyLimit = 8 * 1024 * 1024;

    public static void Map(IEndpointRouteBuilder app)
    {
        var api = app.MapGroup("/api/v1").WithTags("review").DisableAntiforgery();

        api.MapPost("/review/packs", TakeAsync).RequireRateLimiting("review-write")
            .Produces<ReviewAccepted>(StatusCodes.Status201Created)
            .ProducesProblem(StatusCodes.Status400BadRequest)
            .ProducesProblem(StatusCodes.Status401Unauthorized)
            .ProducesProblem(StatusCodes.Status429TooManyRequests);
        api.MapGet("/review/queue", QueueAsync).RequireRateLimiting("api-read")
            .Produces<QueueSet[]>();
    }

    static async Task<IResult> TakeAsync(
        VerdictEnvelope envelope,
        [FromHeader(Name = DeviceApi.TokenHeader)] string? token,
        [FromHeader(Name = "Idempotency-Key")] string? idempotencyKey,
        HttpContext http, PortalDb db, TimeProvider clock, CancellationToken ct)
    {
        // our own limit is only real if the server's is at least as high
        if (http.Features.Get<IHttpMaxRequestBodySizeFeature>() is { IsReadOnly: false } size) size.MaxRequestBodySize = BodyLimit;

        var device = await DeviceApi.AuthenticateAsync(db, token, clock, ct);
        if (device is null)
            return Problem("device_unknown", "the device token is unknown or revoked", StatusCodes.Status401Unauthorized);

        if (envelope.Packs.Count is 0 or > ReviewLimits.PacksPerSend)
            return Problem("bad_envelope", $"a send carries 1..{ReviewLimits.PacksPerSend} packs", StatusCodes.Status400BadRequest);

        var key = Key(idempotencyKey);
        if (key is not null)
        {
            var already = await db.PackReviews.Where(r => r.IdempotencyKey == key).ToListAsync(ct);
            if (already.Count > 0)
                return Results.Ok(new ReviewAccepted(already.Count, already.Sum(r => r.FrameCount), 0, [.. already.Select(r => r.Id)]));
        }

        var now = clock.GetUtcNow();
        var made = new List<PackReview>();
        var replaced = 0;
        foreach (var pack in envelope.Packs)
        {
            var section = Clean(pack.Section, ReviewLimits.SectionMax).ToUpperInvariant();
            var set = Clean(pack.Set, ReviewLimits.SetMax).ToUpperInvariant();
            if (section.Length == 0 || set.Length == 0)
                return Problem("bad_pack", "a pack is named by its section and its set", StatusCodes.Status400BadRequest);
            if (pack.Frames.Count is 0 or > ReviewLimits.FramesPerPack)
                return Problem("bad_pack", $"{set}: a pack carries 1..{ReviewLimits.FramesPerPack} frames", StatusCodes.Status400BadRequest);

            var frames = new List<PackReviewFrame>(pack.Frames.Count);
            foreach (var f in pack.Frames)
            {
                var verdict = Clean(f.Verdict, ReviewLimits.VerdictMax).ToLowerInvariant();
                if (verdict.Length > 0 && !ReviewLimits.Verdicts.Contains(verdict))
                    return Problem("bad_verdict", $"{set} frame {f.Frame}: '{verdict}' is not a verdict", StatusCodes.Status400BadRequest);
                var orig = Hash(f.Orig);
                var hd = Hash(f.Hd);
                if (orig is null || hd is null)
                    return Problem("bad_frame", $"{set} frame {f.Frame}: the picture is named by two hashes", StatusCodes.Status400BadRequest);

                var reasons = f.Reasons.Select(r => Clean(r, ReviewLimits.ReasonMax).ToLowerInvariant())
                    .Where(r => r.Length > 0).Distinct().Take(ReviewLimits.ReasonsPerFrame).ToList();
                if (reasons.FirstOrDefault(r => !ReviewLimits.Reasons.Contains(r)) is { } strange)
                    return Problem("bad_reason", $"{set} frame {f.Frame}: '{strange}' is not one of the reasons", StatusCodes.Status400BadRequest);

                frames.Add(new PackReviewFrame
                {
                    Frame = f.Frame,
                    Orig = orig,
                    Hd = hd,
                    Verdict = verdict,
                    Reasons = reasons,
                    Note = Clean(f.Note, ReviewLimits.NoteMax),
                });
            }

            // the same person looking at the same pack again replaces what they said, never adds a second voice
            replaced += await db.PackReviews
                .Where(r => r.UserId == device.UserId && r.Section == section && r.SetName == set
                            && r.SupersededAt == null && r.RevokedAt == null)
                .ExecuteUpdateAsync(s => s.SetProperty(r => r.SupersededAt, now), ct);

            made.Add(new PackReview
            {
                UserId = device.UserId,
                Section = section,
                SetName = set,
                ModVersion = Clean(pack.ModVersion, ReviewLimits.VersionMax),
                Tool = Clean(envelope.Tool, ReviewLimits.ToolMax),
                PlanPictures = Math.Clamp(pack.Pictures, 0, ReviewLimits.FramesPerPack),
                FrameCount = frames.Count,
                BadCount = frames.Count(f => f.Verdict == "bad"),
                CheckedAt = envelope.CheckedAt == default ? now : envelope.CheckedAt,
                SubmittedAt = now,
                IdempotencyKey = key,
                Frames = frames,
            });
        }

        db.PackReviews.AddRange(made);
        await db.SaveChangesAsync(ct);
        return Results.Created("/roadmap", new ReviewAccepted(made.Count, made.Sum(r => r.FrameCount), replaced, [.. made.Select(r => r.Id)]));
    }

    /// <summary>What to check next: the sets nobody has looked at yet, the widest on the maps first.</summary>
    static async Task<IResult> QueueAsync(PortalDb db, int? take, CancellationToken ct)
    {
        var want = Math.Clamp(take ?? 25, 1, 200);
        // the count goes into an anonymous row first: ordering by a member of a record built in the
        // projection is not translatable, and the whole query falls back to the client
        var rows = await db.ArtPacks.Where(p => p.HdFrames > 0)
            .Select(p => new
            {
                p.Section,
                p.Name,
                p.Frames,
                p.Pictures,
                p.CellShare,
                Reviews = db.PackReviews.Count(r => r.Section == p.Section && r.SetName == p.Name
                                                    && r.SupersededAt == null && r.RevokedAt == null),
            })
            .OrderBy(q => q.Reviews).ThenByDescending(q => q.CellShare).ThenBy(q => q.Name).Take(want)
            .ToListAsync(ct);
        return Results.Ok(rows.Select(q => new QueueSet(q.Section, q.Name, q.Frames, q.Pictures, q.Reviews, q.CellShare)));
    }

    /// <summary>The key is kept as its hash: it is the sender's string, and we have no use for it itself.</summary>
    static string? Key(string? key)
    {
        key = key?.Trim();
        if (key is null || key.Length is < 8 or > 128) return null;
        return Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(key))).ToLowerInvariant();
    }

    static string Clean(string? value, int max)
    {
        value = (value ?? "").Trim();
        return value.Length <= max ? value : value[..max];
    }

    /// <summary>A hash is hex and nothing else: a verdict that names no picture is not a verdict.</summary>
    static string? Hash(string? value)
    {
        value = (value ?? "").Trim().ToLowerInvariant();
        if (value.Length is < 8 or > ReviewLimits.HashMax) return null;
        return value.All(c => c is >= '0' and <= '9' or >= 'a' and <= 'f') ? value : null;
    }

    static IResult Problem(string code, string detail, int status) =>
        Results.Problem(detail: detail, statusCode: status, extensions: new Dictionary<string, object?> { ["code"] = code });
}
