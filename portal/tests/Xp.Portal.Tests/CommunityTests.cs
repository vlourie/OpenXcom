using System.Net;
using System.Text.RegularExpressions;
using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Xp.Portal.Auth;
using Xp.Portal.Data;
using Xp.Portal.Site;

namespace Xp.Portal.Tests;

/// <summary>
/// The public half of the site: the mod sections, the wiki built from rulesets, and the forum.
///
/// The catalogue is applied from the very file the deployment uses, so a typo in it fails here
/// rather than on the server, and the wiki import is checked on what it must never do - lose a page
/// somebody wrote by hand.
/// </summary>
public sealed partial class CommunityTests(PortalFactory f) : IClassFixture<PortalFactory>
{
    const string Password = "Long-enough-passw0rd!";
    static readonly string SeedFile = Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", "..", "deploy", "seed", "community.json");

    HttpClient Browser() => f.CreateClient(new WebApplicationFactoryClientOptions { AllowAutoRedirect = false, HandleCookies = true });

    [GeneratedRegex("name=\"__RequestVerificationToken\" type=\"hidden\" value=\"([^\"]+)\"")]
    private static partial Regex AntiforgeryRx();

    static async Task<HttpResponseMessage> PostForm(HttpClient c, string url, Dictionary<string, string> fields, string? tokenFrom = null)
    {
        var html = await c.GetStringAsync(tokenFrom ?? url);
        fields["__RequestVerificationToken"] = AntiforgeryRx().Match(html) is { Success: true } m
            ? m.Groups[1].Value
            : throw new Xunit.Sdk.XunitException("no antiforgery token on " + (tokenFrom ?? url));
        return await c.PostAsync(url, new FormUrlEncodedContent(fields));
    }

    /// <summary>The catalogue, applied once for the whole class. Applying it twice must be safe.</summary>
    async Task SeedAsync()
    {
        var file = CommunitySeed.Read(Path.GetFullPath(SeedFile));
        await f.ScopedAsync(async sp => await sp.GetRequiredService<CommunitySeed>().ApplyAsync(file, default));
    }

    async Task<HttpClient> SignedInAsync(bool canEditWiki = false)
    {
        var email = $"u-{Guid.NewGuid():N}@x.test";
        await f.ScopedAsync(async sp =>
        {
            var users = sp.GetRequiredService<UserManager<PortalUser>>();
            var u = new PortalUser { UserName = email, Email = email, EmailConfirmed = true, DisplayName = "Пират" };
            Assert.True((await users.CreateAsync(u, Password)).Succeeded);
            if (canEditWiki)
            {
                var db = sp.GetRequiredService<PortalDb>();
                db.UserPermissions.Add(new UserPermission { UserId = u.Id, Permission = Permissions.WikiEdit });
                await db.SaveChangesAsync();
            }
            return 0;
        });
        var c = Browser();
        var r = await PostForm(c, "/account/login", new() { ["Email"] = email, ["Password"] = Password });
        Assert.Equal(HttpStatusCode.Redirect, r.StatusCode);
        return c;
    }

    // ---- the catalogue ----

    [Fact]
    public async Task Catalogue_file_of_the_deployment_applies_and_applies_again()
    {
        await SeedAsync();
        var first = await f.DbAsync(async db => (await db.Mods.CountAsync(), await db.ForumSections.CountAsync()));
        Assert.True(first.Item1 >= 2, "the catalogue must describe at least X-Piratez and our own mod");
        Assert.True(first.Item2 >= 2);

        await SeedAsync();   // the same file again: rows are matched by address, never doubled
        var second = await f.DbAsync(async db => (await db.Mods.CountAsync(), await db.ForumSections.CountAsync()));
        Assert.Equal(first, second);

        // a board that names a mod is tied to it, so the mod's page can link to its board
        var tied = await f.DbAsync(db => db.ForumSections.CountAsync(s => s.ModId != null));
        Assert.True(tied > 0);
    }

    [Fact]
    public async Task Sections_of_the_site_render_for_a_guest()
    {
        await SeedAsync();
        var c = Browser();
        foreach (var url in new[] { "/", "/mods", "/mods/piratez", "/wiki", "/wiki/piratez", "/forum", "/forum/talk" })
        {
            var r = await c.GetAsync(url);
            Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        }
        Assert.Contains("X-Piratez", await c.GetStringAsync("/mods"));
        Assert.Contains("Разговоры", await c.GetStringAsync("/forum"));
    }

    // ---- the wiki built from rulesets ----

    static WikiImport.File Built(string version, params (string Slug, string Title)[] pages) => new(
        "piratez", version, "2026-09-23T00:00:00",
        [.. pages.Select(p => new WikiImport.PageRow(p.Slug, "ru", p.Title, "Оружие", "STR_" + p.Slug.ToUpperInvariant(), "| | |\n|---|---|\n| Вес | 4 |"))]);

    async Task<WikiImport.Report> ImportAsync(WikiImport.File file) =>
        await f.ScopedAsync(async sp => await sp.GetRequiredService<WikiImport>().ApplyAsync(file, default));

    [Fact]
    public async Task Import_writes_pages_stamps_the_version_and_drops_what_the_rulesets_lost()
    {
        await SeedAsync();
        var r = await ImportAsync(Built("v.1", ("pistol", "Пистолет"), ("rifle", "Винтовка")));
        Assert.Equal(2, r.Written);

        var page = await f.DbAsync(db => db.WikiPages.FirstAsync(p => p.Slug == "pistol"));
        Assert.Equal(WikiKind.Generated, page.Kind);
        Assert.Equal("v.1", page.SourceVersion);
        Assert.Equal("STR_PISTOL", page.Source);
        Assert.Equal("v.1", (await f.DbAsync(db => db.Mods.FirstAsync(m => m.Slug == "piratez"))).Version);

        // the mod dropped the rifle: the page about it must go, or the wiki describes what is not there
        var again = await ImportAsync(Built("v.2", ("pistol", "Пистолет")));
        Assert.Equal(1, again.Written);
        Assert.False(await f.DbAsync(db => db.WikiPages.AnyAsync(p => p.Slug == "rifle")));
        Assert.Equal("v.2", (await f.DbAsync(db => db.WikiPages.FirstAsync(p => p.Slug == "pistol"))).SourceVersion);
    }

    [Fact]
    public async Task Import_never_writes_over_a_page_written_by_hand()
    {
        await SeedAsync();
        var mod = await f.DbAsync(db => db.Mods.FirstAsync(m => m.Slug == "piratez"));
        await f.DbAsync(async db =>
        {
            db.WikiPages.Add(new WikiPage
            {
                ModId = mod.Id, Slug = "tactics", Lang = "ru", Title = "Тактика",
                Body = "Написано человеком.", Kind = WikiKind.Manual,
            });
            return await db.SaveChangesAsync();
        });

        var r = await ImportAsync(Built("v.3", ("tactics", "Тактика из рулсетов"), ("knife", "Нож")));
        Assert.Equal(1, r.KeptByHand);
        Assert.Equal(1, r.Written);
        var kept = await f.DbAsync(db => db.WikiPages.FirstAsync(p => p.Slug == "tactics"));
        Assert.Equal("Написано человеком.", kept.Body);
        Assert.Equal(WikiKind.Manual, kept.Kind);
    }

    [Fact]
    public async Task Article_page_says_where_its_numbers_came_from()
    {
        await SeedAsync();
        await ImportAsync(Built("v.4", ("gauss-pistol", "Гаусс-пистолет")));
        var html = await Browser().GetStringAsync("/wiki/piratez/gauss-pistol");
        Assert.Contains("Гаусс-пистолет", html);
        Assert.Contains("v.4", html);                 // the version the page was built from
        Assert.Contains("STR_GAUSS-PISTOL", html);    // and the record it was built from
        Assert.Contains("<table>", html);             // the pipe table is rendered, not printed
    }

    [Fact]
    public async Task Contents_of_a_big_wiki_opens_by_group_rather_than_all_at_once()
    {
        await SeedAsync();
        await ImportAsync(Built("v.5", ("a1", "Альфа"), ("b2", "Бета")));
        var c = Browser();
        // the contents name the groups; six thousand titles are not printed on one page
        var index = await c.GetStringAsync("/wiki/piratez");
        Assert.Contains("Оружие", index);

        // the chosen group lists what is in it, and only that
        var chosen = await c.GetStringAsync("/wiki/piratez?s=%D0%9E%D1%80%D1%83%D0%B6%D0%B8%D0%B5");
        Assert.Contains("Альфа", chosen);
        Assert.Contains("Бета", chosen);
        Assert.Contains("Альфа", await c.GetStringAsync("/wiki/piratez?q=Альф"));
        Assert.DoesNotContain("Бета", await c.GetStringAsync("/wiki/piratez?q=Альф"));
        // the search must not care about case, and Russian is the language it is used in
        Assert.Contains("Альфа", await c.GetStringAsync("/wiki/piratez?q=альф"));
    }

    [Fact]
    public async Task Only_an_editor_may_write_in_the_wiki()
    {
        await SeedAsync();
        var guest = Browser();
        var r = await guest.GetAsync("/wiki/piratez/new/edit");
        Assert.Equal(HttpStatusCode.Redirect, r.StatusCode);
        Assert.Contains("/account/login", r.Headers.Location!.OriginalString);

        var reader = await SignedInAsync();
        Assert.Equal(HttpStatusCode.Redirect, (await reader.GetAsync("/wiki/piratez/new/edit")).StatusCode);

        var editor = await SignedInAsync(canEditWiki: true);
        Assert.Equal(HttpStatusCode.OK, (await editor.GetAsync("/wiki/piratez/new/edit")).StatusCode);
        var saved = await PostForm(editor, "/wiki/piratez/new/edit?handler=Save", new()
        {
            ["title"] = "Как выжить", ["pageSlug"] = "survival", ["section"] = "Советы",
            ["body"] = "Не лезь <script>alert(1)</script> в трюм.", ["published"] = "true",
        }, tokenFrom: "/wiki/piratez/new/edit");
        Assert.Equal(HttpStatusCode.Redirect, saved.StatusCode);
        Assert.Equal("/wiki/piratez/survival", saved.Headers.Location!.OriginalString);

        var html = await editor.GetStringAsync("/wiki/piratez/survival");
        Assert.Contains("Не лезь", html);
        Assert.DoesNotContain("<script>alert(1)</script>", html);   // markdown renders html as text
    }

    // ---- the forum ----

    [Fact]
    public async Task A_topic_is_started_answered_and_counted()
    {
        await SeedAsync();
        var author = await SignedInAsync();
        var started = await PostForm(author, "/forum/talk/new", new()
        {
            ["title"] = "Где брать порох", ["body"] = "Второй месяц ищу. <b>Подскажите</b>",
        });
        Assert.Equal(HttpStatusCode.Redirect, started.StatusCode);
        var url = started.Headers.Location!.OriginalString;
        Assert.Matches(@"^/forum/t/\d+$", url);

        var html = await author.GetStringAsync(url);
        Assert.Contains("Где брать порох", html);
        Assert.Contains("&lt;b&gt;", html);    // html in a post is text, not markup

        var replied = await PostForm(author, url + "?handler=Reply", new() { ["body"] = "Варить самому." }, tokenFrom: url);
        Assert.Equal(HttpStatusCode.Redirect, replied.StatusCode);
        Assert.Contains("Варить самому.", await author.GetStringAsync(url));

        var board = await f.DbAsync(db => db.ForumSections.FirstAsync(s => s.Slug == "talk"));
        Assert.Equal(1, board.TopicCount);
        Assert.Equal(2, board.PostCount);
        Assert.NotNull(board.LastPostAt);

        // and the home page counts it
        Assert.Contains("Где брать порох", await Browser().GetStringAsync("/"));
    }

    [Fact]
    public async Task A_guest_reads_the_forum_but_does_not_write_in_it()
    {
        await SeedAsync();
        var c = Browser();
        var html = await c.GetStringAsync("/forum/talk");
        Assert.DoesNotContain("/forum/talk/new", html);
        var r = await c.GetAsync("/forum/talk/new");
        Assert.Equal(HttpStatusCode.Redirect, r.StatusCode);
        Assert.Contains("/account/login", r.Headers.Location!.OriginalString);
    }

    [Fact]
    public async Task Announcements_are_started_by_the_team_only()
    {
        await SeedAsync();
        var reader = await SignedInAsync();
        var r = await reader.GetAsync("/forum/news/new");
        Assert.Equal(HttpStatusCode.Redirect, r.StatusCode);   // Forbid on a cookie scheme redirects
        Assert.Contains("denied", r.Headers.Location!.OriginalString, StringComparison.OrdinalIgnoreCase);
    }
}
