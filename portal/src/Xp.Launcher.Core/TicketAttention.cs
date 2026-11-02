using System.Globalization;

namespace Xp.Launcher.Core;

/// <summary>What the player should be told about a sent report's ticket, most pressing first.</summary>
public enum TicketMark
{
    None,
    /// <summary>The team asked for details: stays until the player answers (the portal then moves the ticket on).</summary>
    NeedsInfo,
    /// <summary>The ticket was fixed since the player last looked.</summary>
    Resolved,
    /// <summary>Closed, rejected or marked a duplicate since the player last looked.</summary>
    Closed,
    NewReply,
    /// <summary>Taken into work, triaged and the like.</summary>
    StatusChanged,
}

/// <summary>
/// Which tickets are news for the player. "Seen" is kept by the launcher (Settings.SeenTickets: ticket number ->
/// the time of the newest team event the player has looked at), never on the site and never in report.json,
/// which the game reads too. A team event is a reply or a status move; the portal says when
/// (TicketView.LastStaffReplyAt, StatusChangedAt), and an older portal at least gives the reply in the messages.
/// </summary>
public static class TicketAttention
{
    public static string? Key(ReportDraft d) => d.TicketNumber?.ToString(CultureInfo.InvariantCulture);

    /// <summary>When the team last did anything on the ticket, as far as the launcher knows.</summary>
    public static DateTimeOffset? EventAt(ReportDraft d) =>
        d.StaffReplyAt is { } r && d.StatusChangedAt is { } s ? (r > s ? r : s) : d.StaffReplyAt ?? d.StatusChangedAt;

    public static TicketMark MarkOf(ReportDraft d, IReadOnlyDictionary<string, DateTimeOffset>? seen)
    {
        if (d.Status != ReportStatus.Sent || Key(d) is not { } key) return TicketMark.None;
        if (d.TicketStatus == "NeedsInfo") return TicketMark.NeedsInfo;
        if (d.TicketStatus is null or "Gone") return TicketMark.None;
        // never looked at: only what happened after the ticket was made counts, and nothing did if there are no events
        DateTimeOffset after = seen is not null && seen.TryGetValue(key, out var s) ? s : DateTimeOffset.MinValue;
        bool statusNew = d.StatusChangedAt is { } sc && sc > after;
        bool replyNew = d.StaffReplyAt is { } rc && rc > after;
        if (statusNew && d.TicketStatus == "Resolved") return TicketMark.Resolved;
        if (statusNew && d.TicketStatus is "Closed" or "Duplicate" or "Rejected") return TicketMark.Closed;
        if (replyNew) return TicketMark.NewReply;
        return statusNew ? TicketMark.StatusChanged : TicketMark.None;
    }

    /// <summary>The player opened the ticket (or said it is read): everything up to now is seen.</summary>
    public static void MarkSeen(IDictionary<string, DateTimeOffset> seen, ReportDraft d)
    {
        if (Key(d) is not { } key || EventAt(d) is not { } at) return;
        if (!seen.TryGetValue(key, out var old) || at > old) seen[key] = at;
    }

    /// <summary>
    /// The first run with this feature: whatever happened to the tickets before now is old news, so tickets answered or
    /// closed long ago do not all light up at once. (Dated now, not by the events: a report.json written by an older
    /// launcher has no status time yet, and the first refresh would then bring a week-old "fixed" in as new.)
    /// </summary>
    public static void Baseline(IDictionary<string, DateTimeOffset> seen, IEnumerable<Report> reports, DateTimeOffset now)
    {
        foreach (var r in reports)
            if (r.Draft.Status == ReportStatus.Sent && Key(r.Draft) is { } key) seen[key] = now;
    }

    public static IReadOnlyList<Report> Unread(IEnumerable<Report> reports, IReadOnlyDictionary<string, DateTimeOffset>? seen) =>
        reports.Where(r => MarkOf(r.Draft, seen) != TicketMark.None).ToList();
}
