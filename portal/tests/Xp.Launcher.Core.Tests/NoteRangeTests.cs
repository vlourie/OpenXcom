using Xp.Manifest;

namespace Xp.Launcher.Core.Tests;

/// <summary>"What's new" on the home page: every release one update brings, from the player's version up.</summary>
public sealed class NoteRangeTests
{
    // the history as the channel keeps it: newest first
    static readonly List<ReleaseNote> History =
        new[] { "2026.10.21-2", "2026.10.21", "2026.10.20-17", "2026.10.20-16", "2026.10.20-9", "2026.10.20", "2026.10.17-3" }
            .Select(v => new ReleaseNote { Version = v, Changelog = { ["ru"] = "в " + v } }).ToList();

    static List<string> Since(string latest, string? before) => NoteRange.Since(History, latest, before).Select(r => r.Version).ToList();

    [Fact]
    public void An_update_several_releases_behind_shows_them_all_newest_first()
    {
        Assert.Equal(["2026.10.21-2", "2026.10.21", "2026.10.20-17"], Since("2026.10.21-2", "2026.10.20-16"));
    }

    [Fact]
    public void One_release_behind_or_nothing_before_shows_the_latest_alone()
    {
        Assert.Equal(["2026.10.21-2"], Since("2026.10.21-2", "2026.10.21"));
        Assert.Equal(["2026.10.21-2"], Since("2026.10.21-2", null));
        Assert.Equal(["2026.10.21-2"], Since("2026.10.21-2", "2026.10.21-2"));   // a repair of the same version
    }

    [Fact]
    public void A_version_missing_from_the_history_stops_at_the_first_older_one()
    {
        // 2026.10.20-12 was revoked: not in the history, the range still ends where it would have stood
        Assert.Equal(["2026.10.21-2", "2026.10.21", "2026.10.20-17", "2026.10.20-16"], Since("2026.10.21-2", "2026.10.20-12"));
        // older than all the history: the whole of it
        Assert.Equal(History.Count, Since("2026.10.21-2", "2026.09.24").Count);
    }

    [Fact]
    public void The_range_starts_at_the_latest_of_the_channel_not_at_the_top_of_the_history()
    {
        Assert.Equal(["2026.10.20-17", "2026.10.20-16", "2026.10.20-9"], Since("2026.10.20-17", "2026.10.20"));
        Assert.Empty(Since("2026.11.01", "2026.10.20"));   // the latest not in the history: the caller shows the manifest
    }

    [Fact]
    public void Versions_compare_by_numbers_and_the_bare_date_is_the_first_of_the_day()
    {
        Assert.True(NoteRange.Compare("2026.10.20-9", "2026.10.20-10") < 0);    // not as strings
        Assert.True(NoteRange.Compare("2026.10.20", "2026.10.20-2") < 0);
        Assert.Equal(0, NoteRange.Compare("2026.10.20", "2026.10.20-1"));
        Assert.True(NoteRange.Compare("2026.10.21", "2026.10.20-17") > 0);
        Assert.Null(NoteRange.Compare("v2", "2026.10.20"));
    }
}
