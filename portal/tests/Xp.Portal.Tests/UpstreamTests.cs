using System.Net;
using System.Text.RegularExpressions;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Xp.Portal.Data;
using Xp.Portal.Notifications;

namespace Xp.Portal.Tests;

/// <summary>The portal with a VK key set, so all three upstream sources are on.</summary>
public sealed class UpstreamPortal : PortalFactory
{
    public const string VkKey = "vk-SECRET-key";
    public UpstreamPortal() => Settings["Upstream:VkToken"] = VkKey;
}

/// <summary>The portal with a mod.io key set: the mod.io games are checked too.</summary>
public sealed class ModioPortal : PortalFactory
{
    public const string ModioKey = "modio-SECRET-key";
    public ModioPortal() => Settings["Upstream:ModioKey"] = ModioKey;
}

/// <summary>The mod.io answer alone, without the database fixture.</summary>
public sealed class ModioParseTests
{
    [Fact]
    public void Modio_mod_is_the_primary_file_id_with_version_and_date()
    {
        var seen = UpstreamParse.ModioMod(ModioUpstreamTests.Mod(158, 8236968, "4.2", 1792022400))!;
        Assert.Equal("8236968", seen.Value);
        Assert.Equal("4.2 (2026-10-15)", seen.Label);
        Assert.Equal("https://mod.io/g/openxcom/m/the-x-com-files", seen.Url);
        Assert.Equal("XComFiles_4.2.zip (2026-10-15)", UpstreamParse.ModioMod(ModioUpstreamTests.Mod(158, 1, null, 1792022400))!.Label);
        Assert.Null(UpstreamParse.ModioMod("""{"id":158,"modfile":null}"""));
        Assert.Throws<InvalidOperationException>(() => UpstreamParse.ModioMod("""{"error":{"code":401,"message":"bad key"}}"""));
    }
}

public sealed class ModioUpstreamTests(ModioPortal f) : IClassFixture<ModioPortal>
{
    const string Api = "https://g-51.modapi.io/v1/games/51/mods/";

    // the shape of GET /games/51/mods/{id}, trimmed to what the check reads
    internal static string Mod(long mod, long file, string? version, long added) =>
        "{\"id\":" + mod + ",\"name\":\"The X-Com Files\",\"profile_url\":\"https://mod.io/g/openxcom/m/the-x-com-files\"," +
        "\"modfile\":{\"id\":" + file + ",\"mod_id\":" + mod + ",\"date_added\":" + added +
        ",\"filename\":\"XComFiles_4.2.zip\",\"version\":" + (version is null ? "null" : "\"" + version + "\"") + "}}";

    [Fact]
    public async Task Modio_games_are_watched_and_a_new_file_is_reported()
    {
        await f.DbAsync(async db =>
        {
            db.TelegramRoutes.Add(new TelegramRoute { Category = TelegramNotices.UpstreamCategory, ChatId = "-100news" });
            return await db.SaveChangesAsync();
        });
        var mods = new UpstreamOptions().ModioMods.Keys.ToList();
        foreach (var m in mods) f.Upstream.Pages[Api + m] = (HttpStatusCode.OK, Mod(long.Parse(m), 1000 + mods.IndexOf(m), "1.0", 1792022400));

        async Task<List<string>> Run()
        {
            var before = await f.DbAsync(db => db.NotificationJobs.Select(j => j.Id).ToListAsync());
            await f.ScopedAsync(sp => sp.GetRequiredService<UpstreamCheck>().RunAsync(default));
            return await f.DbAsync(db => db.NotificationJobs.Where(j => !before.Contains(j.Id)).OrderBy(j => j.Id).Select(j => j.Text).ToListAsync());
        }

        var first = (await Run()).Where(t => t.Contains("(mod.io)")).ToList();
        Assert.Equal(mods.Count, first.Count);
        Assert.Contains(first, t => t.Contains("<b>The X-Com Files (mod.io)</b>") && t.Contains("1.0 (2026-10-15)"));
        Assert.Contains(f.Upstream.Requests, r => r.Url == Api + "158?api_key=" + ModioPortal.ModioKey);

        // the author uploads 4.3: one notice for that game only
        f.Upstream.Pages[Api + "158"] = (HttpStatusCode.OK, Mod(158, 9000000, "4.3", 1793000000));
        var changed = Assert.Single(await Run(), t => t.Contains("(mod.io)"));
        Assert.Contains("The X-Com Files (mod.io)", changed);
        Assert.Contains("4.3 (", changed);

        // a refused key never lands in the stored error, even when echoed
        f.Upstream.Pages[Api + "378"] = (HttpStatusCode.OK, "{\"error\":{\"code\":401,\"message\":\"key " + ModioPortal.ModioKey + " revoked\"}}");
        await Run();
        var bad = await f.DbAsync(db => db.UpstreamStates.SingleAsync(u => u.Source == "modio-378"));
        Assert.Equal(1, bad.Failures);
        Assert.DoesNotContain(ModioPortal.ModioKey, bad.LastError);
    }
}

public sealed class UpstreamTests(UpstreamPortal f) : IClassFixture<UpstreamPortal>
{
    const string Rss = "https://rss.moddb.com/mods/x-piratez/downloads/feed/rss.xml";
    const string VersionH = "https://raw.githubusercontent.com/MeridianOXC/OpenXcom/oxce-plus/src/version.h";
    const string VkWall = "https://api.vk.com/method/wall.get";

    // the shape of the real feed (2026-09-24): leading space after the declaration, entities, CDATA, newest not first
    static string Feed(params (string Guid, string Title, string Date)[] items) =>
        "<?xml version=\"1.0\" encoding=\"utf-8\"?> \n<rss version=\"2.0\" xmlns:media=\"http://search.yahoo.com/mrss/\"><channel>\n" +
        "<title>Files RSS feed &#45; X&#45;Piratez mod for OpenXcom - ModDB</title>\n" +
        string.Concat(items.Select(i =>
            $"<item><title>{i.Title}</title><link>https://www.moddb.com/mods/x-piratez/downloads/{i.Guid}</link>" +
            $"<pubDate>{i.Date}</pubDate><guid isPermaLink=\"false\">{i.Guid}</guid><description><![CDATA[<br />text]]></description></item>\n")) +
        "</channel></rss>";

    static string Header(string version, string git) =>
        "#pragma once\n#define OPENXCOM_VERSION_ENGINE \"Extended\"\n" +
        $"#define OPENXCOM_VERSION_SHORT \"Extended {version}\"\n#define OPENXCOM_VERSION_LONG \"{version}.0\"\n" +
        $"#define OPENXCOM_VERSION_GIT \" ({git})\"\n";

    const string Wall = """
        {"response":{"count":3,"items":[
          {"id":90,"owner_id":-777,"date":1751846400,"is_pinned":1,"text":"Русский патч 12.2\nстарый, но закреплён"},
          {"id":120,"owner_id":-777,"date":1790000000,"text":"Скриншоты недели"},
          {"id":110,"owner_id":-777,"date":1789000000,"text":"XPZ RU-patch 12.3.1 / 07-JUL-2026\nчто нового"}
        ]}}
        """;

    [Fact]
    public void ModDb_feed_gives_the_newest_file_by_date_not_by_order()
    {
        var seen = UpstreamParse.ModDbRss(Feed(
            ("downloads200000", "Dioxine XPiratez N14 So Many Snakes", "Mon, 01 Jan 2024 10:00:00 +0000"),
            ("downloads311212", "XPZ o1 19&#45;Jun&#45;2026 Reincarnated", "Fri, 19 Jun 2026 13:50:52 +0000")))!;
        Assert.Equal("downloads311212", seen.Value);
        Assert.Equal("XPZ o1 19-Jun-2026 Reincarnated (2026-06-19)", seen.Label);
        Assert.Equal("https://www.moddb.com/mods/x-piratez/downloads/downloads311212", seen.Url);
    }

    [Fact]
    public void Oxce_version_is_number_plus_build_tag()
    {
        var seen = UpstreamParse.OxceVersion(Header("8.7.1", "v2026-09-19"), "https://github.com/x")!;
        Assert.Equal("Extended 8.7.1 (v2026-09-19)", seen.Value);
        Assert.Null(UpstreamParse.OxceVersion("not a header", "u"));
    }

    [Fact]
    public void Vk_wall_takes_the_newest_matching_post_not_the_pinned_one()
    {
        var seen = UpstreamParse.VkWall(Wall, new Regex("(?i)патч|patch"))!;
        Assert.Equal("110", seen.Value);
        Assert.StartsWith("XPZ RU-patch 12.3.1 / 07-JUL-2026 (", seen.Label);
        Assert.Equal("https://vk.com/wall-777_110", seen.Url);
        Assert.Throws<InvalidOperationException>(() => UpstreamParse.VkWall("""{"error":{"error_code":15,"error_msg":"Access denied"}}""", new Regex("x")));
    }

    /// <summary>The real sites, on demand only (XP_LIVE_UPSTREAM=1): catches a format change the samples above cannot.</summary>
    [Fact]
    public async Task Live_sources_still_parse()
    {
        if (Environment.GetEnvironmentVariable("XP_LIVE_UPSTREAM") != "1") return;
        using var http = new HttpClient();
        http.DefaultRequestHeaders.UserAgent.ParseAdd("XPiratezPortal/1.0 (+https://x-piratez.mywire.org:8443/)");
        var o = new UpstreamOptions();
        var moddb = UpstreamParse.ModDbRss(await http.GetStringAsync(o.ModDbRss));
        var oxce = UpstreamParse.OxceVersion(await http.GetStringAsync(o.OxceVersionUrl), o.OxcePageUrl);
        Assert.NotNull(moddb);
        Assert.StartsWith("downloads", moddb.Value);
        Assert.NotNull(oxce);
        Assert.StartsWith("Extended ", oxce.Value);
        Console.WriteLine($"LIVE moddb: {moddb.Label} | oxce: {oxce.Label}");
    }

    async Task<List<string>> RunAsync()
    {
        var before = await f.DbAsync(db => db.NotificationJobs.Select(j => j.Id).ToListAsync());
        await f.ScopedAsync(sp => sp.GetRequiredService<UpstreamCheck>().RunAsync(default));
        return await f.DbAsync(db => db.NotificationJobs.Where(j => !before.Contains(j.Id)).OrderBy(j => j.Id).Select(j => j.Text).ToListAsync());
    }

    [Fact]
    public async Task Watches_notices_changes_once_and_reports_a_broken_source_once()
    {
        await f.DbAsync(async db =>
        {
            db.TelegramRoutes.Add(new TelegramRoute { Category = "*", ChatId = "-100default" });
            db.TelegramRoutes.Add(new TelegramRoute { Category = TelegramNotices.UpstreamCategory, ChatId = "-100news" });
            return await db.SaveChangesAsync();
        });
        f.Upstream.Pages[Rss] = (HttpStatusCode.OK, Feed(("downloads311212", "XPZ o1 19-Jun-2026", "Fri, 19 Jun 2026 13:50:52 +0000")));
        f.Upstream.Pages[VersionH] = (HttpStatusCode.OK, Header("8.7.1", "v2026-09-19"));
        f.Upstream.Pages[VkWall] = (HttpStatusCode.OK, Wall);

        // first sight: one "watching" per source, on the upstream route
        var first = await RunAsync();
        Assert.Equal(3, first.Count);
        Assert.All(first, t => Assert.StartsWith("👀", t));
        Assert.Contains(first, t => t.Contains("Extended 8.7.1 (v2026-09-19)"));
        Assert.Equal(3, await f.DbAsync(db => db.NotificationJobs.CountAsync(j => j.ChatId == "-100news")));

        // nothing changed: silence
        Assert.Empty(await RunAsync());

        // Dioxine uploads a new file: one notice with the old and the new
        f.Upstream.Pages[Rss] = (HttpStatusCode.OK, Feed(
            ("downloads311212", "XPZ o1 19-Jun-2026", "Fri, 19 Jun 2026 13:50:52 +0000"),
            ("downloads400000", "XPZ o2 &lt;beta&gt;", "Sat, 03 Oct 2026 09:00:00 +0000")));
        var changed = Assert.Single(await RunAsync());
        Assert.Contains("новая версия", changed);
        Assert.Contains("XPZ o2 &lt;beta&gt; (2026-10-03)", changed);   // escaped for Telegram HTML
        Assert.Contains("было: XPZ o1 19-Jun-2026 (2026-06-19)", changed);

        // GitHub goes away: silent twice, one warning on the third failure, silent after
        f.Upstream.Pages.Remove(VersionH);
        Assert.Empty(await RunAsync());
        Assert.Empty(await RunAsync());
        var broken = Assert.Single(await RunAsync());
        Assert.Contains("Не получается проверить <b>OXCE (GitHub)</b> 3 раз подряд", broken);
        Assert.Empty(await RunAsync());
        var state = await f.DbAsync(db => db.UpstreamStates.SingleAsync(u => u.Source == "oxce"));
        Assert.Equal(4, state.Failures);
        Assert.Equal("Extended 8.7.1 (v2026-09-19)", state.Label);   // the last good value is kept

        // back again with a new build: failures reset, the change is reported
        f.Upstream.Pages[VersionH] = (HttpStatusCode.OK, Header("8.7.2", "v2026-10-01"));
        var back = Assert.Single(await RunAsync());
        Assert.Contains("Extended 8.7.2 (v2026-10-01)", back);
        Assert.Equal(0, (await f.DbAsync(db => db.UpstreamStates.SingleAsync(u => u.Source == "oxce"))).Failures);

        // the VK key travels in the body, never in a URL, and never into a stored error
        Assert.All(f.Upstream.Requests, r => Assert.DoesNotContain(UpstreamPortal.VkKey, r.Url));
        Assert.Contains(f.Upstream.Requests, r => r.Url.StartsWith(VkWall) && r.Body.Contains(UpstreamPortal.VkKey));
        f.Upstream.Pages[VkWall] = (HttpStatusCode.OK, "{\"error\":{\"error_msg\":\"bad token " + UpstreamPortal.VkKey + "\"}}");
        await RunAsync();
        var vk = await f.DbAsync(db => db.UpstreamStates.SingleAsync(u => u.Source == "ru-patch"));
        Assert.DoesNotContain(UpstreamPortal.VkKey, vk.LastError);
    }
}
