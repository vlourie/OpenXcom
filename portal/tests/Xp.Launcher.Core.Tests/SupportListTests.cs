using System.Net;
using System.Text;

namespace Xp.Launcher.Core.Tests;

/// <summary>"Support": the list the site gives besides the launcher's own buttons. A slip in that file must not put a bad link in front of a player.</summary>
public sealed class SupportListTests : IDisposable
{
    readonly string _root = Path.Combine(Path.GetTempPath(), "xp-tests", Guid.NewGuid().ToString("N"));

    public void Dispose()
    {
        try { Directory.Delete(_root, true); } catch (IOException) { }
    }

    static SupportList? Parse(string json, string lang = "ru") => SupportList.Parse(Encoding.UTF8.GetBytes(json), lang);

    [Fact]
    public void The_file_the_site_ships_empty_is_a_usable_list_with_nothing_in_it()
    {
        var list = Parse("""{ "version": 1, "hide": [], "items": [] }""");
        Assert.NotNull(list);
        Assert.Empty(list.Items);
        Assert.Empty(list.Hidden);
    }

    [Fact]
    public void Items_come_in_the_players_language_with_the_other_as_fallback_and_plain_strings_allowed()
    {
        var json = """
            { "items": [
              { "title": {"ru": "Через X", "en": "Via X"}, "note": {"ru": "картой", "en": "by card"}, "url": "https://x.example/pay" },
              { "title": {"en": "Only English"}, "url": "https://y.example/" },
              { "title": "Plain", "note": "plain note", "url": "https://z.example/" }
            ] }
            """;
        var ru = Parse(json, "ru")!.Items;
        Assert.Equal([new SupportItem("Через X", "картой", "https://x.example/pay"), new SupportItem("Only English", "", "https://y.example/"), new SupportItem("Plain", "plain note", "https://z.example/")], ru);
        Assert.Equal("Via X", Parse(json, "en")!.Items[0].Title);
    }

    [Theory]
    [InlineData("http://plain.example/")]
    [InlineData("file:///C:/Windows/System32/calc.exe")]
    [InlineData("javascript:alert(1)")]
    [InlineData("ftp://x.example/")]
    [InlineData("https://user:pass@x.example/")]
    [InlineData("https://")]
    [InlineData("x.example/pay")]
    [InlineData("")]
    public void An_address_that_is_not_https_with_a_host_is_dropped(string url)
    {
        var list = Parse($$"""{ "items": [ { "title": "Bad", "url": "{{url}}" }, { "title": "Good", "url": "https://ok.example/" } ] }""")!;
        Assert.Equal(["Good"], list.Items.Select(i => i.Title));
    }

    [Fact]
    public void Items_without_a_title_or_a_link_and_ones_past_the_limit_are_dropped()
    {
        var many = string.Join(",", Enumerable.Range(1, 20).Select(i => $$"""{ "title": "T{{i}}", "url": "https://s{{i}}.example/" }"""));
        var list = Parse($$"""{ "items": [ { "url": "https://no-title.example/" }, { "title": "No link" }, 5, null, {{many}} ] }""")!;
        Assert.Equal(SupportList.MaxItems, list.Items.Count);
        Assert.Equal("T1", list.Items[0].Title);
    }

    [Fact]
    public void Hide_names_only_the_built_in_buttons()
    {
        var list = Parse("""{ "hide": ["hd", "nonsense", 7, "mod"], "items": [] }""")!;
        Assert.Equal(["hd", "mod"], list.Hidden.Order());
    }

    [Theory]
    [InlineData("")]
    [InlineData("<html>404</html>")]
    [InlineData("[1,2]")]
    [InlineData("{ broken")]
    public void Something_that_is_not_a_list_is_refused_so_the_caller_keeps_what_it_had(string body)
    {
        Assert.Null(Parse(body));
    }

    sealed class Site(HttpStatusCode code, string body) : HttpMessageHandler
    {
        public int Calls;
        public Uri? Asked;
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage req, CancellationToken ct)
        {
            Calls++;
            Asked = req.RequestUri;
            return Task.FromResult(new HttpResponseMessage(code) { Content = new StringContent(body, Encoding.UTF8, "application/json") });
        }
    }

    [Fact]
    public async Task Fetch_asks_the_sites_file_and_keeps_it_for_the_next_start_without_a_network()
    {
        var cache = Path.Combine(_root, SupportList.File);
        var site = new Site(HttpStatusCode.OK, """{ "items": [ { "title": "Via X", "url": "https://x.example/" } ] }""");
        var list = await SupportList.FetchAsync(new HttpClient(site), new Uri("https://p.test/base"), "en", cache, CancellationToken.None);
        Assert.Equal("https://p.test/base/support.json", site.Asked!.AbsoluteUri);
        Assert.Equal("Via X", list!.Items.Single().Title);
        Assert.Equal("Via X", SupportList.Cached(cache, "en")!.Items.Single().Title);
        Assert.Null(SupportList.Cached(Path.Combine(_root, "none.json"), "en"));
    }

    [Theory]
    [InlineData(HttpStatusCode.NotFound, "<html>not here</html>")]
    [InlineData(HttpStatusCode.OK, "<html>a captive portal</html>")]
    public async Task A_missing_or_wrong_answer_changes_nothing_and_does_not_spoil_the_kept_list(HttpStatusCode code, string body)
    {
        var cache = Path.Combine(_root, SupportList.File);
        Directory.CreateDirectory(_root);
        File.WriteAllText(cache, """{ "items": [ { "title": "Kept", "url": "https://kept.example/" } ] }""");
        var list = await SupportList.FetchAsync(new HttpClient(new Site(code, body)), new Uri("https://p.test/"), "ru", cache, CancellationToken.None);
        Assert.Null(list);
        Assert.Equal("Kept", SupportList.Cached(cache, "ru")!.Items.Single().Title);
    }

    [Fact]
    public async Task A_dead_network_is_an_exception_for_the_page_to_swallow()
    {
        var offline = new HttpClient(new Offline());
        await Assert.ThrowsAsync<HttpRequestException>(() => SupportList.FetchAsync(offline, new Uri("https://p.test/"), "ru", null, CancellationToken.None));
    }

    sealed class Offline : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage req, CancellationToken ct) => throw new HttpRequestException("no route to host");
    }
}
