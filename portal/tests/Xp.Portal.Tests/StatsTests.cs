using System.Net;
using System.Net.Http.Json;
using Microsoft.EntityFrameworkCore;
using Xp.Portal.Data;
using Xp.Portal.Stats;

namespace Xp.Portal.Tests;

/// <summary>A portal that lets a launcher ping only twice per window, to see the limit work.</summary>
public sealed class StatsLimitedFactory : PortalFactory
{
    public StatsLimitedFactory() => Settings["RateLimits:StatsPingPer10Min"] = "2";
}

/// <summary>
/// The anonymous statistics of the launcher. A ping is a random installation number and whether the game
/// runs; played time is the sum of the stretches between two pings that are close enough to be one session.
/// </summary>
public sealed class StatsTests(PortalFactory f) : IClassFixture<PortalFactory>
{
    static string NewInstall() => Guid.NewGuid().ToString("N");

    Task<HttpResponseMessage> PingAsync(string? install, bool playing, string launcher = "0.3.14", string game = "2026.10.22-10") =>
        f.CreateClient().PostAsJsonAsync("/api/v1/stats/ping", new { install, playing, launcher, game });

    Task<LauncherInstall> RowAsync(string install) => f.DbAsync(db => db.LauncherInstalls.AsNoTracking().SingleAsync(i => i.Id == install));

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("abc")]
    [InlineData("0123456789abcdef0123456789abcdeg")]      // 32 characters, one of them not hex
    [InlineData("0123456789abcdef0123456789abcdef0")]     // 33
    [InlineData("01234567-89ab-cdef-0123-456789abcdef")]  // a Guid with dashes is not the N format
    public async Task A_ping_without_a_proper_installation_number_is_400(string? install)
    {
        var before = await f.DbAsync(db => db.LauncherInstalls.CountAsync());
        Assert.Equal(HttpStatusCode.BadRequest, (await PingAsync(install, false)).StatusCode);
        Assert.Equal(before, await f.DbAsync(db => db.LauncherInstalls.CountAsync()));
    }

    [Fact]
    public async Task A_ping_without_a_body_is_400()
    {
        var r = await f.CreateClient().PostAsync("/api/v1/stats/ping", new StringContent("", System.Text.Encoding.UTF8, "application/json"));
        Assert.Equal(HttpStatusCode.BadRequest, r.StatusCode);
    }

    [Fact]
    public async Task A_first_ping_makes_the_row_and_answers_204_without_a_login()
    {
        var id = NewInstall();
        var r = await PingAsync(id, false, "0.3.14", "2026.10.22-10");
        Assert.Equal(HttpStatusCode.NoContent, r.StatusCode);
        var row = await RowAsync(id);
        Assert.Equal(0, row.PlaySeconds);
        Assert.Null(row.LastPlayingAt);
        Assert.Equal("0.3.14", row.LauncherVersion);
        Assert.Equal("2026.10.22-10", row.GameRelease);
        Assert.Equal(row.FirstSeen, row.LastSeen);
    }

    [Fact]
    public async Task An_upper_case_number_is_the_same_installation_as_the_lower_case_one()
    {
        var id = NewInstall();
        await PingAsync(id, false);
        await PingAsync(id.ToUpperInvariant(), false);
        Assert.Equal(1, await f.DbAsync(db => db.LauncherInstalls.CountAsync(i => i.Id == id)));
    }

    [Fact]
    public async Task Played_time_is_counted_between_pings_of_one_session_and_closed_by_the_last_one()
    {
        var id = NewInstall();
        await PingAsync(id, false);                         // the launcher starts
        f.Clock.Advance(TimeSpan.FromMinutes(1));
        await PingAsync(id, true);                          // the game starts: nothing counted for the minute before it
        Assert.Equal(0, (await RowAsync(id)).PlaySeconds);
        Assert.NotNull((await RowAsync(id)).LastPlayingAt);

        f.Clock.Advance(TimeSpan.FromMinutes(5));
        await PingAsync(id, true);                          // five minutes of play
        f.Clock.Advance(TimeSpan.FromMinutes(5));
        await PingAsync(id, true);
        Assert.Equal(600, (await RowAsync(id)).PlaySeconds);

        f.Clock.Advance(TimeSpan.FromMinutes(2));
        await PingAsync(id, false);                         // the game exits: the last stretch is paid, the session is closed
        var closed = await RowAsync(id);
        Assert.Equal(720, closed.PlaySeconds);
        Assert.Null(closed.LastPlayingAt);

        f.Clock.Advance(TimeSpan.FromMinutes(30));
        await PingAsync(id, false);                         // nothing to pay for after a closed session
        Assert.Equal(720, (await RowAsync(id)).PlaySeconds);
    }

    [Fact]
    public async Task A_gap_longer_than_eleven_minutes_is_not_play()
    {
        var id = NewInstall();
        await PingAsync(id, true);
        f.Clock.Advance(TimeSpan.FromMinutes(11));          // exactly the window: still one session
        await PingAsync(id, true);
        Assert.Equal(11 * 60, (await RowAsync(id)).PlaySeconds);

        f.Clock.Advance(TimeSpan.FromMinutes(11) + TimeSpan.FromSeconds(1));   // the launcher died, the machine slept
        await PingAsync(id, true);
        Assert.Equal(11 * 60, (await RowAsync(id)).PlaySeconds);               // not counted, but a new session starts here

        f.Clock.Advance(TimeSpan.FromMinutes(5));
        await PingAsync(id, false);
        Assert.Equal(11 * 60 + 5 * 60, (await RowAsync(id)).PlaySeconds);
    }

    [Fact]
    public async Task Overlong_texts_are_cut_and_nothing_else_about_the_sender_is_kept()
    {
        var id = NewInstall();
        await PingAsync(id, false, new string('x', 200), new string('y', 200));
        var row = await RowAsync(id);
        Assert.Equal(StatsLimits.LauncherMax, row.LauncherVersion.Length);
        Assert.Equal(StatsLimits.GameMax, row.GameRelease.Length);
        // the entity has no place for an address or a name: the columns are the whole of what is stored
        Assert.Equal(["FirstSeen", "GameRelease", "Id", "LastPlayingAt", "LastSeen", "LauncherVersion", "PlaySeconds"],
            typeof(LauncherInstall).GetProperties().Select(p => p.Name).Order().ToArray());
    }
}

/// <summary>The totals live in their own class: they are cached for a minute, and a fresh portal starts with a fresh cache.</summary>
public sealed class StatsTotalsTests(PortalFactory f) : IClassFixture<PortalFactory>
{
    [Fact]
    public async Task Totals_count_installations_hours_and_those_playing_now_and_the_entrance_screen_shows_the_same()
    {
        var c = f.CreateClient();
        Task<HttpResponseMessage> Ping(string id, bool playing) => c.PostAsJsonAsync("/api/v1/stats/ping", new { install = id, playing, launcher = "0.3.14", game = "" });
        string a = Guid.NewGuid().ToString("N"), b = Guid.NewGuid().ToString("N"), idle = Guid.NewGuid().ToString("N");

        await Ping(idle, false);
        await Ping(b, false);
        await Ping(a, true);
        // an hour and a half in ten-minute steps: stays inside the window, so every step is play
        for (var i = 0; i < 9; i++)
        {
            f.Clock.Advance(TimeSpan.FromMinutes(10));
            await Ping(a, true);
        }
        await Ping(b, true);        // b has just begun

        var totals = await c.GetFromJsonAsync<StatsTotals>("/api/v1/stats");
        Assert.Equal(new StatsTotals(3, 1, 2), totals);   // 5400 s of a is one whole hour; a and b play now
        // the names of the json are the contract the launcher is written against
        var json = await c.GetStringAsync("/api/v1/stats");
        Assert.Contains("\"installs\":3", json);
        Assert.Contains("\"hours\":1", json);
        Assert.Contains("\"playingNow\":2", json);

        // the page reads the same numbers from the same service
        var html = System.Net.WebUtility.HtmlDecode(await c.GetStringAsync("/?culture=ru&ui-culture=ru"));
        Assert.Contains("Лаунчер установили: 3 · Наиграно: 1 ч · Сейчас играют: 2", html);
        var en = await c.GetStringAsync("/?culture=en&ui-culture=en");
        Assert.Contains("Launcher installed: 3 · Hours played: 1 · Playing now: 2", System.Net.WebUtility.HtmlDecode(en));

        // a minute of memory: a new ping does not move the numbers until the cache lets go
        await Ping(Guid.NewGuid().ToString("N"), false);
        Assert.Equal(3, (await c.GetFromJsonAsync<StatsTotals>("/api/v1/stats"))!.Installs);
    }
}

public sealed class StatsLimitTests(StatsLimitedFactory f) : IClassFixture<StatsLimitedFactory>
{
    [Fact]
    public async Task A_third_ping_in_the_window_from_one_address_is_429_and_reading_stays_free()
    {
        var c = f.CreateClient();
        var id = Guid.NewGuid().ToString("N");
        Assert.Equal(HttpStatusCode.NoContent, (await c.PostAsJsonAsync("/api/v1/stats/ping", new { install = id, playing = false })).StatusCode);
        Assert.Equal(HttpStatusCode.NoContent, (await c.PostAsJsonAsync("/api/v1/stats/ping", new { install = id, playing = false })).StatusCode);
        Assert.Equal(HttpStatusCode.TooManyRequests, (await c.PostAsJsonAsync("/api/v1/stats/ping", new { install = id, playing = false })).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await c.GetAsync("/api/v1/stats")).StatusCode);
    }
}
