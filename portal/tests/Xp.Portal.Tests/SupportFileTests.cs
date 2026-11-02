using System.Net;
using Xp.Launcher.Core;

namespace Xp.Portal.Tests;

/// <summary>The launcher's "Support" page reads the site's /support.json; the file the site ships must be one the launcher accepts.</summary>
public sealed class SupportFileTests(PortalFactory f) : IClassFixture<PortalFactory>
{
    [Fact]
    public async Task The_site_serves_support_json_and_the_launcher_reads_it()
    {
        var r = await f.CreateClient().GetAsync("/support.json");
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Equal("application/json", r.Content.Headers.ContentType?.MediaType);
        var list = SupportList.Parse(await r.Content.ReadAsByteArrayAsync(), "ru");
        Assert.NotNull(list);   // empty is fine: the owner fills it in; a slip in the file would show here
        // every address the owner has put there is one the launcher will show
        Assert.All(list.Items, i => Assert.True(SupportList.IsWebAddress(i.Url)));
    }

    [Fact]
    public async Task The_page_of_the_site_is_not_shadowed_by_the_file()
    {
        var r = await f.CreateClient().GetAsync("/support");
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Contains("text/html", r.Content.Headers.ContentType?.MediaType);
    }
}
