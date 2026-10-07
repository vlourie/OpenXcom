using Microsoft.EntityFrameworkCore;
using Xp.Launcher.Core;
using Xp.Portal.Data;

namespace Xp.Portal.Tests;

/// <summary>
/// F8 end to end on the server side: the launcher's own ReportSender, unchanged, against the real API.
/// A field renamed on either end breaks this test, not the player's report.
/// </summary>
public sealed class F8ReportTests(PortalFactory f) : IClassFixture<PortalFactory>, IDisposable
{
    readonly string _root = Path.Combine(Path.GetTempPath(), "xp-f8-" + Guid.NewGuid().ToString("N")[..8]);

    public void Dispose()
    {
        try { Directory.Delete(_root, true); } catch (IOException) { }
    }

    Report GameWroteReport()
    {
        var dir = Path.Combine(_root, "user", "reports", Guid.NewGuid().ToString());
        var saves = Path.Combine(_root, "user", "piratez");
        Directory.CreateDirectory(dir);
        Directory.CreateDirectory(saves);
        File.WriteAllBytes(Path.Combine(dir, "shot.png"), [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0, 0, 0, 13, 0x49, 0x48, 0x44, 0x52]);
        var log = Path.Combine(_root, "user", "openxcom.log");
        File.WriteAllText(log, $"[INFO] User folder is: {_root.Replace('\\', '/')}/user/\n[INFO] Feedback: report written\n");
        File.WriteAllText(Path.Combine(saves, "ship.sav"), "name: Ship\nversion: Extended 8.7.1\n");
        var fwd = (string p) => p.Replace('\\', '/');
        File.WriteAllText(Path.Combine(dir, "context.json"), $$"""
            {"format": 1, "id": "x", "session": "s1", "createdAt": "2026-09-23T01:02:03Z",
             "engine": "Extended 8.7.1 (vlourie)", "master": "piratez", "mods": [{"id": "Piratez", "version": "0.99N"}],
             "os": "Windows 10.0.26200", "language": "ru", "state": "BattlescapeState", "battle": true,
             "screenWidth": 1920, "screenHeight": 1080, "fullscreen": false, "borderless": true, "openGL": true,
             "hdMode": 1, "hdScale": 3, "shot": "shot.png", "log": "{{fwd(log)}}", "saveDir": "{{fwd(saves)}}/", "gameDir": "{{fwd(_root)}}/"}
            """);
        var r = Report.Open(dir);
        r.Draft.Kind = "suggestion";
        r.Draft.Title = "Отряд не видит врага за дверью";
        r.Draft.Description = "Открыл дверь, враг стоит, а стрелять нельзя.";
        r.Draft.Steps = "1. Открыть дверь\n2. Выбрать бойца";
        r.Draft.AttachLog = true;
        r.Draft.SavePath = r.RecentSaves()[0].Path;
        return r;
    }

    ReportSender Sender() =>
        new(new PortalClient(f.CreateClient(), f.Server.BaseAddress), new ReportLimits(), new Redactor(_root, null, null), "0.2.0");

    [Fact]
    public async Task A_report_from_the_game_becomes_an_f8_ticket_with_its_files()
    {
        var r = GameWroteReport();
        await Sender().SendAsync(r, CancellationToken.None);

        Assert.Equal(ReportStatus.Sent, r.Draft.Status);
        Assert.StartsWith("XP-", r.Draft.DisplayNumber);
        Assert.Contains($"/t/{r.Draft.TicketNumber}?k=", r.Draft.TicketUrl);
        Assert.Empty(r.Draft.Skipped);
        Assert.Equal(["shot.png", "openxcom.log", "ship.sav"], r.Draft.Uploaded);

        var t = await f.DbAsync(db => db.Tickets.Include(x => x.Attachments).SingleAsync(x => x.Number == r.Draft.TicketNumber));
        Assert.Equal(TicketSource.F8, t.Source);
        Assert.Equal("general", t.Category);
        Assert.True(t.ConsentToFiles);
        Assert.Equal("Extended 8.7.1 (vlourie)", t.GameVersion);
        Assert.Equal("Piratez 0.99N", t.ModVersion);
        Assert.Equal("0.2.0", t.LauncherVersion);
        Assert.Contains("screen: BattlescapeState (battle)", t.Context);
        Assert.Contains("display: 1920x1080 borderless, OpenGL", t.Context);
        Assert.DoesNotContain(_root.Replace('\\', '/'), t.Context);
        Assert.Equal(3, t.Attachments.Count);

        // the log on the server is the cleaned one
        var logRow = t.Attachments.Single(a => a.FileName == "openxcom.log");
        var stored = await File.ReadAllTextAsync(Path.Combine(f.Storage, logRow.ObjectKey[..2], logRow.ObjectKey));
        Assert.Contains("<game>/user/", stored);
        Assert.DoesNotContain(_root.Replace('\\', '/'), stored);
    }

    [Fact]
    public async Task The_launcher_reads_back_the_status_and_the_team_reply()
    {
        var r = GameWroteReport();
        r.Draft.AttachLog = false;
        r.Draft.SavePath = null;
        await Sender().SendAsync(r, CancellationToken.None);
        await f.DbAsync(async db =>
        {
            var t = await db.Tickets.SingleAsync(x => x.Number == r.Draft.TicketNumber);
            t.Status = TicketStatus.NeedsInfo;
            db.TicketMessages.Add(new TicketMessage { TicketId = t.Id, FromStaff = true, Body = "Какой мод включён?", CreatedAt = DateTimeOffset.UtcNow });
            db.TicketMessages.Add(new TicketMessage { TicketId = t.Id, FromStaff = true, Internal = true, Body = "между нами", CreatedAt = DateTimeOffset.UtcNow.AddMinutes(1) });
            await db.SaveChangesAsync();
            return 0;
        });

        var n = await ReportStore.RefreshAsync(ReportStore.List([Path.GetDirectoryName(r.Dir)!]), new PortalClient(f.CreateClient(), f.Server.BaseAddress), CancellationToken.None);
        Assert.Equal(1, n);
        var d = Report.Open(r.Dir).Draft;
        Assert.Equal("NeedsInfo", d.TicketStatus);
        Assert.Equal("Какой мод включён?", d.StaffReply);   // internal notes never reach the player
    }

    [Fact]
    public async Task Sending_the_same_report_twice_makes_one_ticket()
    {
        var r = GameWroteReport();
        r.Draft.AttachLog = false;
        r.Draft.SavePath = null;
        await Sender().SendAsync(r, CancellationToken.None);

        // the launcher lost report.json's answer and starts over from the draft
        var again = Report.Open(r.Dir);
        again.Draft.TicketNumber = null;
        again.Draft.Uploaded.Clear();
        again.Draft.Status = ReportStatus.Queued;
        await Sender().SendAsync(again, CancellationToken.None);

        Assert.Equal(r.Draft.TicketNumber, again.Draft.TicketNumber);
        var count = await f.DbAsync(db => db.TicketAttachments.CountAsync(a => db.Tickets.Any(t => t.Id == a.TicketId && t.Number == r.Draft.TicketNumber)));
        Assert.Equal(1, count);   // the screenshot that was already there is recognised, not sent again
    }
}
