using System.Text.Json;

namespace Xp.Launcher.Core.Tests;

/// <summary>Which sent tickets are news for the player: a team answer, a status move, "needs info" - and what clears them.</summary>
public sealed class TicketAttentionTests : IDisposable
{
    static readonly DateTimeOffset T0 = new(2026, 11, 1, 12, 0, 0, TimeSpan.Zero);

    readonly string _root = Path.Combine(Path.GetTempPath(), "xp-tests", Guid.NewGuid().ToString("N"));

    public void Dispose()
    {
        try { Directory.Delete(_root, true); } catch (IOException) { }
    }

    static ReportDraft Sent(string status, DateTimeOffset? reply = null, DateTimeOffset? changed = null, long number = 7) => new()
    {
        Id = Guid.NewGuid().ToString(), Status = ReportStatus.Sent, TicketNumber = number, TicketStatus = status,
        StaffReplyAt = reply, StatusChangedAt = changed,
    };

    static Dictionary<string, DateTimeOffset> SeenAt(DateTimeOffset at, long number = 7) => new() { [number.ToString()] = at };

    [Fact]
    public void A_ticket_nobody_touched_is_not_news()
    {
        Assert.Equal(TicketMark.None, TicketAttention.MarkOf(Sent("New"), null));
        Assert.Equal(TicketMark.None, TicketAttention.MarkOf(Sent("InProgress"), new Dictionary<string, DateTimeOffset>()));
    }

    [Fact]
    public void An_answer_after_the_last_look_is_a_new_reply_and_opening_clears_it()
    {
        var d = Sent("InProgress", reply: T0);
        Assert.Equal(TicketMark.NewReply, TicketAttention.MarkOf(d, SeenAt(T0.AddMinutes(-1))));
        Assert.Equal(TicketMark.NewReply, TicketAttention.MarkOf(d, null));

        var seen = SeenAt(T0.AddMinutes(-1));
        TicketAttention.MarkSeen(seen, d);
        Assert.Equal(TicketMark.None, TicketAttention.MarkOf(d, seen));

        // the next answer lights it again
        d.StaffReplyAt = T0.AddHours(2);
        Assert.Equal(TicketMark.NewReply, TicketAttention.MarkOf(d, seen));
    }

    [Theory]
    [InlineData("Resolved", TicketMark.Resolved)]
    [InlineData("Closed", TicketMark.Closed)]
    [InlineData("Rejected", TicketMark.Closed)]
    [InlineData("Duplicate", TicketMark.Closed)]
    [InlineData("InProgress", TicketMark.StatusChanged)]
    [InlineData("Triaged", TicketMark.StatusChanged)]
    public void A_status_move_after_the_last_look_is_named_by_where_it_went(string status, TicketMark expected)
    {
        var d = Sent(status, changed: T0);
        Assert.Equal(expected, TicketAttention.MarkOf(d, SeenAt(T0.AddMinutes(-5))));
        Assert.Equal(TicketMark.None, TicketAttention.MarkOf(d, SeenAt(T0)));
    }

    [Fact]
    public void Fixed_with_a_comment_says_fixed_rather_than_new_reply()
    {
        var d = Sent("Resolved", reply: T0, changed: T0.AddSeconds(1));
        Assert.Equal(TicketMark.Resolved, TicketAttention.MarkOf(d, SeenAt(T0.AddMinutes(-1))));
    }

    [Fact]
    public void Needs_info_stays_lit_whatever_was_seen_until_the_ticket_moves_on()
    {
        var d = Sent("NeedsInfo", reply: T0, changed: T0);
        var seen = SeenAt(T0.AddDays(1));
        Assert.Equal(TicketMark.NeedsInfo, TicketAttention.MarkOf(d, seen));
        TicketAttention.MarkSeen(seen, d);
        Assert.Equal(TicketMark.NeedsInfo, TicketAttention.MarkOf(d, seen));

        // the player answered: the portal returned the ticket to triage, the old team message was seen
        d.TicketStatus = "Triaged";
        Assert.Equal(TicketMark.None, TicketAttention.MarkOf(d, seen));
    }

    [Fact]
    public void Drafts_queued_ones_and_vanished_tickets_are_never_marked()
    {
        var queued = Sent("InProgress", reply: T0);
        queued.Status = ReportStatus.Queued;
        Assert.Equal(TicketMark.None, TicketAttention.MarkOf(queued, null));
        Assert.Equal(TicketMark.None, TicketAttention.MarkOf(Sent("Gone", reply: T0), null));
        var noNumber = Sent("InProgress", reply: T0);
        noNumber.TicketNumber = null;
        Assert.Equal(TicketMark.None, TicketAttention.MarkOf(noNumber, null));
    }

    [Fact]
    public void Each_ticket_is_seen_on_its_own()
    {
        var a = Sent("InProgress", reply: T0, number: 7);
        var b = Sent("InProgress", reply: T0, number: 8);
        var seen = new Dictionary<string, DateTimeOffset>();
        TicketAttention.MarkSeen(seen, a);
        Assert.Equal(TicketMark.None, TicketAttention.MarkOf(a, seen));
        Assert.Equal(TicketMark.NewReply, TicketAttention.MarkOf(b, seen));
        // seen never goes back in time
        a.StaffReplyAt = T0.AddDays(-1);
        TicketAttention.MarkSeen(seen, a);
        Assert.Equal(T0, seen["7"]);
    }

    Report Stored(ReportDraft d)
    {
        var dir = Path.Combine(_root, d.Id);
        Directory.CreateDirectory(dir);
        File.WriteAllText(Path.Combine(dir, Report.DraftFile), JsonSerializer.Serialize(new
        {
            id = d.Id, status = "Sent", token = "tok", ticketNumber = d.TicketNumber, ticketStatus = d.TicketStatus,
            staffReplyAt = d.StaffReplyAt, statusChangedAt = d.StatusChangedAt,
        }));
        return Report.Open(dir);
    }

    [Fact]
    public void The_first_run_takes_what_the_tickets_hold_as_seen_and_counts_only_later_news()
    {
        var old = Stored(Sent("Resolved", reply: T0.AddDays(-9), changed: T0.AddDays(-9), number: 3));
        var open = Stored(Sent("InProgress", reply: T0.AddDays(-2), number: 4));
        var seen = new Dictionary<string, DateTimeOffset>();
        TicketAttention.Baseline(seen, [old, open], T0);

        Assert.Empty(TicketAttention.Unread([old, open], seen));
        // an older launcher's file has no status time; the first refresh brings the week-old "fixed": still old news
        old.Draft.StatusChangedAt = T0.AddDays(-9);
        Assert.Empty(TicketAttention.Unread([old, open], seen));
        // a real answer after the baseline shows
        open.Draft.StaffReplyAt = T0.AddHours(1);
        Assert.Equal([open], TicketAttention.Unread([old, open], seen));
    }

    // ---- what the refresh writes from the portal's answer ----

    [Fact]
    public async Task Refresh_stores_the_status_time_the_portal_gives()
    {
        var portal = new FakePortal { Status = "Resolved", StaffReply = "Исправлено", StatusChangedAt = "2026-11-01T10:00:00Z" };
        var r = Stored(Sent("InProgress"));
        await ReportStore.RefreshAsync([r], new PortalClient(new HttpClient(portal), new Uri("https://p.test/")), CancellationToken.None);

        var d = Report.Open(r.Dir).Draft;
        Assert.Equal(DateTimeOffset.Parse("2026-11-01T10:00:00Z"), d.StatusChangedAt);
        Assert.Equal(DateTimeOffset.Parse("2026-09-23T02:00:00Z"), d.StaffReplyAt);
        Assert.Equal(TicketMark.Resolved, TicketAttention.MarkOf(d, SeenAt(DateTimeOffset.Parse("2026-10-30T00:00:00Z"))));
    }

    [Fact]
    public async Task Refresh_against_a_portal_without_the_field_dates_a_changed_status_by_the_look()
    {
        var portal = new FakePortal { Status = "InProgress" };   // no StatusChangedAt: an older portal
        var r = Stored(Sent("New"));
        var before = DateTimeOffset.UtcNow.AddSeconds(-1);
        await ReportStore.RefreshAsync([r], new PortalClient(new HttpClient(portal), new Uri("https://p.test/")), CancellationToken.None);
        var d = Report.Open(r.Dir).Draft;
        Assert.True(d.StatusChangedAt > before);

        // the same status on the next look is no change
        var stamp = d.StatusChangedAt;
        await ReportStore.RefreshAsync([Report.Open(r.Dir)], new PortalClient(new HttpClient(portal), new Uri("https://p.test/")), CancellationToken.None);
        Assert.Equal(stamp, Report.Open(r.Dir).Draft.StatusChangedAt);
    }
}
