namespace Xp.Portal.Data;

/// <summary>
/// One pack looked through by one person: the envelope the launcher sends, kept as it came. The
/// numbers on the roadmap are counted from these rows, so nothing here is a summary — a summary
/// cannot be recounted after a result is revoked.
/// </summary>
public sealed class PackReview
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public Guid UserId { get; set; }
    public PortalUser? User { get; set; }

    public string Section { get; set; } = "TERRAIN";
    public string SetName { get; set; } = "";
    /// <summary>Which pack was judged: a repainted pack is a different one, and old verdicts do not carry over.</summary>
    public string ModVersion { get; set; } = "";
    /// <summary>Who produced the file: the launcher, or review_floors.py when we check a pack ourselves.</summary>
    public string Tool { get; set; } = "";

    /// <summary>Pictures the launcher offered in this set — the denominator of "checked".</summary>
    public int PlanPictures { get; set; }
    public int FrameCount { get; set; }
    public int BadCount { get; set; }

    public DateTimeOffset CheckedAt { get; set; }
    public DateTimeOffset SubmittedAt { get; set; } = DateTimeOffset.UtcNow;
    /// <summary>Hash of the Idempotency-Key: a launcher that sent twice must not be counted twice.</summary>
    public string? IdempotencyKey { get; set; }

    /// <summary>The same person looked at the same pack again: the earlier result stops counting, but stays.</summary>
    public DateTimeOffset? SupersededAt { get; set; }

    /// <summary>Taken out of the count by a moderator. Rows stay, so the reason can be seen afterwards.</summary>
    public DateTimeOffset? RevokedAt { get; set; }
    public Guid? RevokedById { get; set; }
    public string RevokedReason { get; set; } = "";

    public List<PackReviewFrame> Frames { get; set; } = new();

    /// <summary>Counts only while it is neither replaced by its author nor revoked by a moderator.</summary>
    public bool Counts => SupersededAt is null && RevokedAt is null;
}

/// <summary>
/// One picture's verdict. It points at a picture twice: <see cref="Orig"/> is the game's own frame
/// (the census counts by the same fingerprint, so a verdict lands on the same group the repaint plan
/// works with), <see cref="Hd"/> is the sha256 of the pack's PNG, that is the version of the answer.
/// </summary>
public sealed class PackReviewFrame
{
    public long Id { get; set; }
    public Guid ReviewId { get; set; }
    public PackReview? Review { get; set; }

    public int Frame { get; set; }
    public string Orig { get; set; } = "";
    public string Hd { get; set; } = "";
    public string Verdict { get; set; } = "";
    public List<string> Reasons { get; set; } = new();
    public string Note { get; set; } = "";
}

/// <summary>
/// A pack of the game as the census knows it: how many frames, how many different pictures, and how
/// much of the maps it covers. Nobody reviews this table — it is the list of what there is to check,
/// so that "nobody has looked at this set yet" can be said at all.
/// </summary>
public sealed class ArtPack
{
    public int Id { get; set; }
    public string Section { get; set; } = "TERRAIN";
    public string Name { get; set; } = "";
    public int Frames { get; set; }
    /// <summary>Different pictures in the set: one tile lives in dozens of packs (rake R-049).</summary>
    public int Pictures { get; set; }
    /// <summary>How many frames the HD pack has — a set without them is not worth offering.</summary>
    public int HdFrames { get; set; }
    /// <summary>Share of the map cells of the whole game drawn with this set, in percent.</summary>
    public double CellShare { get; set; }
    public long Cells { get; set; }
}

public static class ReviewLimits
{
    public const int SectionMax = 32;
    public const int SetMax = 64;
    public const int VersionMax = 64;
    public const int ToolMax = 32;
    public const int HashMax = 64;
    public const int VerdictMax = 8;
    public const int ReasonMax = 16;
    public const int NoteMax = 500;
    public const int ReasonsPerFrame = 8;
    public const int FramesPerPack = 4000;
    public const int PacksPerSend = 200;

    /// <summary>The closed list the statistics are counted by; anything else is not a verdict.</summary>
    public static readonly string[] Verdicts = ["ok", "bad", "doubt"];

    /// <summary>
    /// Why a picture is bad. The list is closed on purpose: a reason names the script that fixes it,
    /// so twenty "panel" complaints on one set are work for unpanel_batch.py, not for a painter.
    /// </summary>
    public static readonly string[] Reasons = ["color", "shape", "panel", "seams", "invented", "blurry"];
}
