using System.Diagnostics;
using System.Text.Json;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Headless;
using Avalonia.Headless.XUnit;
using Avalonia.Input;
using Avalonia.LogicalTree;
using Avalonia.Threading;
using Xp.Launcher;
using Xp.Launcher.Core;
using Xunit.Abstractions;

namespace Xp.Launcher.Ui.Tests;

/// <summary>
/// "Reports": a ticket with news since the player looked is lit (dot, accent frame, label), "needs info" stays lit until
/// the player answers, "Mark as read" clears the rest; and "Support" shows the site's extra ways. No network: the portal
/// address is unusable for the reports page, the support list comes from a fake handler. Frames go to XP_UI_SHOTS when set.
/// </summary>
public sealed class TicketMarksTests : IDisposable
{
    readonly ITestOutputHelper _out;
    readonly string _root = Path.Combine(Path.GetTempPath(), "xp-ui-tests", Guid.NewGuid().ToString("N"));
    readonly string _shots;
    static readonly DateTimeOffset T0 = DateTimeOffset.UtcNow.AddHours(-3);

    public TicketMarksTests(ITestOutputHelper output)
    {
        _out = output;
        _shots = Environment.GetEnvironmentVariable("XP_UI_SHOTS") is { Length: > 0 } s ? s : Path.Combine(_root, "shots");
        Directory.CreateDirectory(_shots);
        Settings.DirOverride = Path.Combine(_root, "settings");
        Directory.CreateDirectory(Settings.DirOverride);
    }

    public void Dispose()
    {
        Settings.DirOverride = null;
        try { Directory.Delete(_root, true); } catch (IOException) { }
    }

    string Reports => Path.Combine(_root, "reports");

    void Sent(long number, string title, string status, DateTimeOffset? reply = null, DateTimeOffset? changed = null, string? text = null)
    {
        var id = Guid.NewGuid().ToString();
        var dir = Path.Combine(Reports, id);
        Directory.CreateDirectory(dir);
        File.WriteAllText(Path.Combine(dir, Report.DraftFile), JsonSerializer.Serialize(new
        {
            id, title, kind = "bug", status = "Sent", token = "tok", ticketNumber = number, displayNumber = $"XP-{number:D6}",
            ticketUrl = $"https://p.test/t/{number}?k=tok", ticketStatus = status, staffReply = text, staffReplyAt = reply, statusChangedAt = changed,
            createdAt = T0.AddDays(-1), checkedAt = DateTimeOffset.UtcNow,
        }));
    }

    [AvaloniaFact]
    public void News_and_needs_info_are_lit_a_quiet_ticket_is_not_and_mark_as_read_clears_only_the_news()
    {
        L.Use("ru");
        Sent(1, "Нужна подробность", "NeedsInfo", reply: T0, changed: T0, text: "Какой мод включён?");
        Sent(2, "Есть ответ", "InProgress", reply: T0, text: "Смотрим");
        Sent(3, "Исправлено", "Resolved", reply: T0, changed: T0.AddMinutes(1), text: "Готово");
        Sent(4, "Тихий", "InProgress");
        Sent(5, "Давно прочитан", "Closed", reply: T0.AddDays(-5), changed: T0.AddDays(-5));
        var settings = new Settings { PortalUrl = "not a url", SeenTickets = new() { ["5"] = T0 } };   // 5 was looked at after its last event
        int changed = 0;
        var page = new ReportsPage(settings, () => [Reports]);
        page.Changed += () => changed++;
        var w = new Window { Width = 1100, Height = 900, Content = page, Background = Skin.B(Skin.Bg) };
        w.Show();
        page.Shown();
        Settle();

        var texts = Texts(page);
        Assert.Contains(L.T("tickets.mark.needsInfo"), texts);
        Assert.Contains(L.T("tickets.mark.newReply"), texts);
        Assert.Contains(L.T("tickets.mark.resolved"), texts);
        Assert.Equal(3, texts.Count(t => t == "●"));
        Assert.Equal(2, Buttons(page).Count(b => b.Content as string == L.T("reports.markRead")));   // not on "needs info"
        Assert.Equal(3, TicketAttention.Unread(ReportStore.List([Reports]), settings.SeenTickets).Count);
        Shot(w, "reports-marks");

        // reading the answer of #2 clears it, the others stay
        Click(Buttons(page).First(b => b.Content as string == L.T("reports.markRead")));
        Assert.Equal(1, changed);
        texts = Texts(page);
        Assert.Equal(2, texts.Count(t => t == "●"));
        Assert.Equal(2, TicketAttention.Unread(ReportStore.List([Reports]), settings.SeenTickets).Count);
        Assert.Contains(L.T("tickets.mark.needsInfo"), texts);

        // opening a ticket on the site is looking at it; "needs info" still stands
        var opened = new List<string>();
        ReportWindow.OpenUrlOverride = opened.Add;
        try
        {
            // every click rebuilds the list, so the buttons are looked up again each time
            for (int i = 0; i < 5; i++) Click(Buttons(page).Where(b => b.Content as string == L.T("reports.onSite")).ElementAt(i));
        }
        finally { ReportWindow.OpenUrlOverride = null; }
        Assert.NotEmpty(opened);
        var left = TicketAttention.Unread(ReportStore.List([Reports]), settings.SeenTickets);
        Assert.Equal(["XP-000001"], left.Select(r => r.Draft.DisplayNumber));
        Assert.Equal(TicketMark.NeedsInfo, TicketAttention.MarkOf(left[0].Draft, settings.SeenTickets));
        Shot(w, "reports-after-reading");
        w.Close();
    }

    [AvaloniaFact]
    public void The_first_run_after_the_update_lights_nothing_that_was_already_there()
    {
        L.Use("ru");
        Sent(8, "Старый ответ", "InProgress", reply: T0.AddDays(-9), text: "Давно");
        Sent(9, "Старое закрытие", "Closed", reply: T0.AddDays(-9), changed: T0.AddDays(-9));
        var settings = new Settings { PortalUrl = "not a url" };   // SeenTickets never set up
        var page = new ReportsPage(settings, () => [Reports]);
        var w = new Window { Width = 1100, Height = 900, Content = page, Background = Skin.B(Skin.Bg) };
        w.Show();
        page.Shown();
        Settle();
        Assert.NotNull(settings.SeenTickets);
        Assert.DoesNotContain("●", Texts(page));
        Assert.Empty(TicketAttention.Unread(ReportStore.List([Reports]), settings.SeenTickets));
        w.Close();
    }

    static IEnumerable<Button> Buttons(Control root) => root.GetLogicalDescendants().OfType<Button>().Where(b => b.IsEffectivelyVisible);

    internal static List<string> Texts(Control root) =>
        root.GetLogicalDescendants().OfType<TextBlock>().Where(t => t.IsEffectivelyVisible).Select(t => t.Text ?? "").ToList();

    internal static void Pump(Func<bool> until, string what, int ms = 20000)
    {
        var sw = Stopwatch.StartNew();
        while (!until())
        {
            Dispatcher.UIThread.RunJobs();
            AvaloniaHeadlessPlatform.ForceRenderTimerTick();
            if (sw.ElapsedMilliseconds > ms) throw new TimeoutException("waited for " + what);
            Thread.Sleep(10);
        }
        Dispatcher.UIThread.RunJobs();
    }

    internal static void Settle()
    {
        for (int i = 0; i < 5; i++) { Dispatcher.UIThread.RunJobs(); AvaloniaHeadlessPlatform.ForceRenderTimerTick(); }
    }

    static void Click(Control c)
    {
        Settle();
        var top = TopLevel.GetTopLevel(c)!;
        var p = c.TranslatePoint(new Point(c.Bounds.Width / 2, c.Bounds.Height / 2), top)!.Value;
        top.MouseMove(p, RawInputModifiers.None);
        top.MouseDown(p, MouseButton.Left, RawInputModifiers.None);
        top.MouseUp(p, MouseButton.Left, RawInputModifiers.None);
        Settle();
    }

    void Shot(TopLevel top, string name) => Shot(_out, top, name, _shots);

    internal static void Shot(ITestOutputHelper output, TopLevel top, string name, string? shots = null)
    {
        var dir = shots ?? (Environment.GetEnvironmentVariable("XP_UI_SHOTS") is { Length: > 0 } s ? s : Path.Combine(Path.GetTempPath(), "xp-ui-tests", "shots"));
        Directory.CreateDirectory(dir);
        Settle();
        var frame = top.CaptureRenderedFrame();
        if (frame is null) { output.WriteLine("no frame for " + name); return; }
        var path = Path.Combine(dir, name + ".png");
        frame.Save(path);
        output.WriteLine("frame: " + path);
    }
}
