using System.Net;
using System.Net.Http.Json;
using System.Text.RegularExpressions;
using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Xp.Portal.Data;
using Xp.Portal.Devices;
using Xp.Portal.Review;

namespace Xp.Portal.Tests;

/// <summary>
/// What players saw in the launcher, and what the site makes of it. Every number on the roadmap is
/// counted from these rows, so the tests below are about counting: one person is one voice, a result
/// taken out of the count changes the page by itself, and a glance at three frames out of forty one
/// does not close a set.
/// </summary>
public sealed partial class ReviewTests(PortalFactory f) : IClassFixture<PortalFactory>
{
    const string Password = "Long-enough-passw0rd!";

    /// <summary>
    /// The tests of a class share one database, and the roadmap counts everything in it. So every
    /// test names its own sets and its own pictures: six hex digits go into the set name and into
    /// both hashes, and a test then looks only at what it sent itself.
    /// </summary>
    readonly string _tag = Guid.NewGuid().ToString("N")[..6];

    string S(string name) => $"{name}_{_tag}".ToUpperInvariant();

    HttpClient Browser() => f.CreateClient(new WebApplicationFactoryClientOptions { AllowAutoRedirect = false, HandleCookies = true });
    HttpClient Launcher() => f.CreateClient();

    [GeneratedRegex("name=\"__RequestVerificationToken\" type=\"hidden\" value=\"([^\"]+)\"")]
    private static partial Regex AntiforgeryRx();

    /// <summary>A person with a launcher of their own: the site sees them only through its token.</summary>
    async Task<(string Token, Guid UserId, HttpClient Browser)> ReviewerAsync(string name)
    {
        var email = $"rev-{Guid.NewGuid():N}@x.test";
        var userId = await f.ScopedAsync(async sp =>
        {
            var users = sp.GetRequiredService<UserManager<PortalUser>>();
            var u = new PortalUser { UserName = email, Email = email, EmailConfirmed = true, DisplayName = name };
            var r = await users.CreateAsync(u, Password);
            Assert.True(r.Succeeded, string.Join(", ", r.Errors.Select(e => e.Description)));
            return u.Id;
        });

        var browser = Browser();
        var login = await browser.PostAsync("/account/login", await FormAsync(browser, "/account/login",
            new() { ["Email"] = email, ["Password"] = Password }));
        Assert.Equal(HttpStatusCode.Redirect, login.StatusCode);

        var launcher = Launcher();
        var start = await launcher.PostAsJsonAsync("/api/v1/devices/link", new LinkRequest("Лаунчер тест"));
        var link = (await start.Content.ReadFromJsonAsync<LinkResponse>())!;
        var confirm = await browser.PostAsync("/me/devices?handler=Confirm",
            await FormAsync(browser, "/me/devices", new() { ["code"] = link.Code }));
        Assert.Equal(HttpStatusCode.Redirect, confirm.StatusCode);
        var status = (await (await launcher.GetAsync($"/api/v1/devices/{link.DeviceId}")).Content.ReadFromJsonAsync<LinkStatusResponse>())!;
        return (status.Token!, userId, browser);
    }

    static async Task<FormUrlEncodedContent> FormAsync(HttpClient c, string page, Dictionary<string, string> fields)
    {
        var html = await c.GetStringAsync(page);
        fields["__RequestVerificationToken"] = AntiforgeryRx().Match(html) is { Success: true } m
            ? m.Groups[1].Value : throw new Xunit.Sdk.XunitException("no antiforgery token on " + page);
        return new FormUrlEncodedContent(fields);
    }

    VerdictEnvelope Envelope(string set, int pictures, params (int Frame, string Verdict, string[] Reasons)[] frames) => new()
    {
        Tool = "launcher",
        CheckedAt = new DateTimeOffset(2026, 9, 25, 10, 0, 0, TimeSpan.Zero),
        Packs =
        [
            new PackVerdicts
            {
                Section = "TERRAIN",
                Set = S(set),
                ModVersion = "hd 0.1",
                Pictures = pictures,
                Frames = [.. frames.Select(x => new FrameVerdict
                {
                    Frame = x.Frame,
                    // one picture per frame number, and the same picture whoever is looking at it
                    Orig = $"{x.Frame:x4}{_tag}aaaa",
                    Hd = $"{x.Frame:x4}{_tag}bbbb",
                    Verdict = x.Verdict,
                    Reasons = [.. x.Reasons],
                })],
            },
        ],
    };

    async Task<HttpResponseMessage> SendAsync(string token, VerdictEnvelope envelope, string? key = null)
    {
        var msg = new HttpRequestMessage(HttpMethod.Post, "/api/v1/review/packs") { Content = JsonContent.Create(envelope) };
        msg.Headers.Add(DeviceApi.TokenHeader, token);
        if (key is not null) msg.Headers.Add("Idempotency-Key", key);
        return await Launcher().SendAsync(msg);
    }

    async Task PacksAsync(params (string Set, int Frames, int Pictures)[] packs) =>
        await f.ScopedAsync(async sp =>
        {
            var seed = sp.GetRequiredService<PackSeed>();
            await seed.ApplyAsync(new PackSeed.File([.. packs.Select(p =>
                new PackSeed.PackRow("TERRAIN", S(p.Set), p.Frames, p.Pictures, p.Frames, 1000, 1.5))]), default);
            return 0;
        });

    /// <summary>Only the sets of this test: the database also holds what its neighbours sent.</summary>
    async Task<List<PackProgress>> ProgressAsync()
    {
        var all = await f.ScopedAsync(async sp => await sp.GetRequiredService<Roadmap>().ProgressAsync(null, 1000, default));
        return [.. all.Where(p => p.Set.EndsWith(_tag, StringComparison.OrdinalIgnoreCase))];
    }

    async Task<List<RepaintRow>> QueueAsync()
    {
        var all = await f.ScopedAsync(async sp => await sp.GetRequiredService<Roadmap>().RepaintAsync(500, default));
        return [.. all.Where(r => r.Hd.Contains(_tag, StringComparison.OrdinalIgnoreCase))];
    }

    [Fact]
    public async Task Without_a_linked_launcher_nothing_is_taken()
    {
        var set = S("CAVEBROWN");
        var anonymous = await SendAsync("no-such-token-at-all", Envelope("CAVEBROWN", 41, (12, "bad", ["color"])));
        Assert.Equal(HttpStatusCode.Unauthorized, anonymous.StatusCode);
        Assert.Equal(0, await f.DbAsync(db => db.PackReviews.CountAsync(r => r.SetName == set)));
    }

    [Fact]
    public async Task A_verdict_the_list_does_not_know_is_refused_whole()
    {
        var me = await ReviewerAsync("Проверяющий");
        var strange = await SendAsync(me.Token, Envelope("ABUNKER", 10, (1, "terrible", [])));
        Assert.Equal(HttpStatusCode.BadRequest, strange.StatusCode);

        var reason = await SendAsync(me.Token, Envelope("ABUNKER", 10, (1, "bad", ["ugly"])));
        Assert.Equal(HttpStatusCode.BadRequest, reason.StatusCode);

        // nothing of a refused send is kept: it is one envelope, not a stream of rows
        var set = S("ABUNKER");
        Assert.Equal(0, await f.DbAsync(db => db.PackReviews.CountAsync(r => r.SetName == set)));
    }

    [Fact]
    public async Task Sending_the_same_pack_again_replaces_what_that_person_said()
    {
        var me = await ReviewerAsync("Мария");
        await PacksAsync(("ACHURCH", 20, 20));

        var first = await SendAsync(me.Token, Envelope("ACHURCH", 20, (1, "bad", ["color"]), (2, "ok", [])));
        Assert.Equal(HttpStatusCode.Created, first.StatusCode);

        var second = await SendAsync(me.Token, Envelope("ACHURCH", 20, (1, "ok", []), (2, "ok", [])));
        Assert.Equal(HttpStatusCode.Created, second.StatusCode);
        Assert.Equal(1, (await second.Content.ReadFromJsonAsync<ReviewAccepted>())!.Replaced);

        // both sends are kept, but only the later one counts — and it says the picture is fine now
        var set = S("ACHURCH");
        Assert.Equal(2, await f.DbAsync(db => db.PackReviews.CountAsync(r => r.SetName == set)));
        var live = (await ProgressAsync()).Single(p => p.Set == set);
        Assert.Equal(2, live.Covered);
        Assert.Equal(0, live.Bad);
        Assert.Equal(1, live.Reviewers);
    }

    [Fact]
    public async Task The_same_send_twice_over_a_broken_connection_counts_once()
    {
        var me = await ReviewerAsync("Витали");
        var envelope = Envelope("NUKE3", 36, (5, "ok", []));
        var once = await SendAsync(me.Token, envelope, "key-of-this-evening");
        var twice = await SendAsync(me.Token, envelope, "key-of-this-evening");

        Assert.Equal(HttpStatusCode.Created, once.StatusCode);
        Assert.Equal(HttpStatusCode.OK, twice.StatusCode);
        var set = S("NUKE3");
        Assert.Equal(1, await f.DbAsync(db => db.PackReviews.CountAsync(r => r.SetName == set)));
    }

    [Fact]
    public async Task Three_frames_out_of_forty_one_do_not_make_a_set_checked()
    {
        var me = await ReviewerAsync("Беглый");
        await PacksAsync(("CAVEAQUA", 41, 41));
        await SendAsync(me.Token, Envelope("CAVEAQUA", 41, (1, "ok", []), (2, "ok", []), (3, "bad", ["seams"])));

        var row = (await ProgressAsync()).Single(p => p.Set == S("CAVEAQUA"));
        Assert.Equal("partial", row.State);
        Assert.Equal(3, row.Covered);
        Assert.Equal(41, row.Denominator);
        Assert.Equal(7, row.Percent);
    }

    [Fact]
    public async Task A_set_is_checked_when_every_picture_is_judged_and_confirmed_when_two_people_did_it()
    {
        var one = await ReviewerAsync("Первый");
        var two = await ReviewerAsync("Второй");
        await PacksAsync(("FLOORHOLE", 2, 2));

        await SendAsync(one.Token, Envelope("FLOORHOLE", 2, (1, "ok", []), (2, "bad", ["panel"])));
        var afterOne = (await ProgressAsync()).Single(p => p.Set == S("FLOORHOLE"));
        Assert.Equal("checked", afterOne.State);
        Assert.Equal(1, afterOne.Reviewers);

        await SendAsync(two.Token, Envelope("FLOORHOLE", 2, (1, "ok", []), (2, "bad", ["panel"])));
        var afterTwo = (await ProgressAsync()).Single(p => p.Set == S("FLOORHOLE"));
        Assert.Equal("confirmed", afterTwo.State);
        Assert.Equal(2, afterTwo.Reviewers);
    }

    [Fact]
    public async Task Two_people_on_one_picture_stand_above_ten_complaints_from_one()
    {
        var one = await ReviewerAsync("Первый");
        var two = await ReviewerAsync("Второй");
        await PacksAsync(("MOUNTWASTE2", 60, 60));

        // frame 41 is called bad by one person in two different packs: still one voice
        await SendAsync(one.Token, Envelope("MOUNTWASTE2", 60, (41, "bad", ["color"])));
        await SendAsync(one.Token, Envelope("MOUNTWASTE3", 60, (41, "bad", ["color", "seams"])));
        // frame 7 is called bad by two different people
        await SendAsync(one.Token, Envelope("DESERT", 60, (7, "bad", ["blurry"])));
        await SendAsync(two.Token, Envelope("DESERT", 60, (7, "bad", ["invented"])));

        var queue = await QueueAsync();
        Assert.Equal(2, queue.Count);
        Assert.Equal(2, queue[0].People);
        Assert.Contains("blurry", queue[0].Reasons);
        Assert.Contains("invented", queue[0].Reasons);
        Assert.Equal(1, queue[1].People);
        Assert.Equal(2, queue[1].Packs);
    }

    [Fact]
    public async Task A_revoked_result_leaves_the_numbers_as_if_it_never_came()
    {
        var me = await ReviewerAsync("Вандал");
        await PacksAsync(("XBASE2", 4, 4));
        await SendAsync(me.Token, Envelope("XBASE2", 4, (1, "bad", ["invented"]), (2, "bad", ["invented"])));
        var set = S("XBASE2");
        Assert.Equal("partial", (await ProgressAsync()).Single(p => p.Set == set).State);

        await f.ScopedAsync(async sp =>
        {
            var db = sp.GetRequiredService<PortalDb>();
            var review = await db.PackReviews.FirstAsync(r => r.SetName == set);
            review.RevokedAt = DateTimeOffset.UtcNow;
            review.RevokedReason = "накрутка";
            return await db.SaveChangesAsync();
        });

        Assert.DoesNotContain(await ProgressAsync(), p => p.Set == set);
        Assert.Empty(await QueueAsync());
        // the rows are still there: a revoked result must stay readable, with its reason
        Assert.Equal(2, await f.DbAsync(db => db.PackReviewFrames.CountAsync(x => x.Review!.SetName == set)));
    }

    [Fact]
    public async Task The_roadmap_page_shows_the_sets_and_the_queue()
    {
        var me = await ReviewerAsync("Читатель");
        await PacksAsync(("CORP", 52, 52), ("ICEKING_RUINS", 96, 96));
        await SendAsync(me.Token, Envelope("CORP", 52, (37, "bad", ["invented"]), (39, "ok", [])));

        var page = await Launcher().GetStringAsync("/roadmap");
        Assert.Contains("/roadmap/queue", page);
        Assert.Contains("/download/launcher", page);

        // the picture somebody called bad is in the queue, named by the set it lives in
        var queue = await Launcher().GetStringAsync("/roadmap/queue");
        Assert.Contains(S("CORP"), queue);

        // a set nobody has opened is what the launcher is told to look at next
        var next = await Launcher().GetFromJsonAsync<List<QueueSet>>("/api/v1/review/queue?take=200");
        Assert.Contains(next!, q => q.Set == S("ICEKING_RUINS") && q.Reviews == 0);

        // and the person sees their own work on their own page
        var mine = await me.Browser.GetStringAsync("/me");
        Assert.Contains("Проверка графики", mine);
    }

    [Fact]
    public async Task What_to_check_next_is_asked_of_the_site_by_the_launcher_too()
    {
        await PacksAsync(("WIDE", 30, 30), ("NARROW", 5, 5));
        var queue = await Launcher().GetFromJsonAsync<List<QueueSet>>("/api/v1/review/queue?take=200");
        Assert.NotNull(queue);
        Assert.Contains(queue!, q => q.Set == S("WIDE") && q.Frames == 30 && q.Reviews == 0);
        // the queue is what to check NEXT: a set somebody has already sent in stands behind untouched ones
        Assert.True(queue!.SkipWhile(q => q.Reviews == 0).All(q => q.Reviews > 0),
            "sets already reviewed are mixed in among the untouched ones");
    }
}
