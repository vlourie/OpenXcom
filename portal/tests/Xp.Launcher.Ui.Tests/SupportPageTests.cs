using System.Net;
using System.Text;
using Avalonia.Controls;
using Avalonia.Headless.XUnit;
using Xp.Launcher;
using Xunit.Abstractions;

namespace Xp.Launcher.Ui.Tests;

/// <summary>
/// "Support": besides the built-in buttons the page shows the ways the site lists (/support.json), takes a dead built-in
/// button off when the site says so, and keeps the list on disk for the next start without a network. The site is a fake
/// handler. Frames go to XP_UI_SHOTS when it is set.
/// </summary>
public sealed class SupportPageTests : IDisposable
{
    readonly ITestOutputHelper _out;
    readonly string _root = Path.Combine(Path.GetTempPath(), "xp-ui-tests", Guid.NewGuid().ToString("N"));

    public SupportPageTests(ITestOutputHelper output)
    {
        _out = output;
        Settings.DirOverride = Path.Combine(_root, "settings");
        Directory.CreateDirectory(Settings.DirOverride);
    }

    public void Dispose()
    {
        Settings.DirOverride = null;
        try { Directory.Delete(_root, true); } catch (IOException) { }
    }

    sealed class Site(string? body) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage req, CancellationToken ct) =>
            body is null ? throw new HttpRequestException("no route to host")
                : Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(body, Encoding.UTF8, "application/json") });
    }

    [AvaloniaFact]
    public void Support_shows_the_sites_extra_ways_takes_a_dead_button_off_and_keeps_the_list_for_the_next_start()
    {
        L.Use("ru");
        var list = """
            { "hide": ["hd"],
              "items": [ { "title": {"ru": "Способ из списка", "en": "Listed way"}, "note": {"ru": "заметка способа"}, "url": "https://listed.example/pay" },
                         { "title": "Небезопасный", "url": "http://insecure.example/" } ] }
            """;
        var settings = new Settings { PortalUrl = "https://p.test/" };

        // before the site answers: only the built-in buttons
        var page = new SupportPage(settings, () => new HttpClient(new Site(list)));
        var w = new Window { Width = 900, Height = 900, Content = page, Background = Skin.B(Skin.Bg) };
        w.Show();
        TicketMarksTests.Settle();
        Assert.Contains(L.T("support.hd"), TicketMarksTests.Texts(page));
        Assert.DoesNotContain(L.T("support.more").ToUpperInvariant(), TicketMarksTests.Texts(page));

        page.Shown();
        TicketMarksTests.Pump(() => TicketMarksTests.Texts(page).Contains("Способ из списка"), "the site's list");
        var texts = TicketMarksTests.Texts(page);
        Assert.Contains(L.T("support.more").ToUpperInvariant(), texts);   // a small heading, drawn in capitals
        Assert.Contains("заметка способа", texts);
        Assert.DoesNotContain("Небезопасный", texts);
        Assert.DoesNotContain(L.T("support.hd"), texts);                // taken off by the site
        Assert.Contains(L.T("support.hdPage"), texts);                  // the rest stays
        TicketMarksTests.Shot(_out, w, "support-more");
        w.Close();

        // the next start with no network shows the kept list at once
        var again = new SupportPage(settings, () => new HttpClient(new Site(null)));
        var w2 = new Window { Width = 900, Height = 900, Content = again, Background = Skin.B(Skin.Bg) };
        w2.Show();
        TicketMarksTests.Settle();
        Assert.Contains("Способ из списка", TicketMarksTests.Texts(again));
        again.Shown();
        TicketMarksTests.Settle();
        Assert.Contains("Способ из списка", TicketMarksTests.Texts(again));   // a dead network leaves the kept list in place
        w2.Close();
    }
}
