using Xp.Manifest;
using Xp.ReleaseBuilder;

namespace Xp.Launcher.Core.Tests;

/// <summary>
/// The history of the «Обновления» page kept on disk (XP-000268): shown at once, asked from the server
/// only after a new release, once a day or on "Reload".
/// </summary>
public sealed class NotesCacheTests : IDisposable
{
    readonly Fixture f = new();
    readonly NotesCache _cache;

    public NotesCacheTests()
    {
        _cache = new NotesCache(new GamePaths(f.Game));
        f.StageV1();
    }

    public void Dispose() => f.Dispose();

    void Release(string id, string ru)
    {
        var o = new BuildOptions { StageDir = f.Stage, Id = id, Version = id, Channel = "stable", Launch = "openxcom_hd.exe" };
        o.Changelog["ru"] = ru;
        f.Repo.Build(o, f.Key);
        f.Repo.Publish("stable", id, f.Key);
    }

    int NotesAsked() { lock (f.Server.Requests) return f.Server.Requests.Count(r => r.Key == BlobKeys.Notes("stable")); }

    [Fact]
    public async Task The_kept_history_is_shown_and_the_server_is_not_asked_again_for_the_same_release()
    {
        Release("r1", "— первое");
        var first = await _cache.GetAsync(f.Client, "stable", "r1", default);
        Assert.Equal(["r1"], first.Releases.Select(r => r.Id));
        Assert.Equal(1, NotesAsked());

        Assert.False(_cache.Due("stable", "r1", DateTime.UtcNow));
        var again = await _cache.GetAsync(f.Client, "stable", "r1", default);
        Assert.Equal(["r1"], again.Releases.Select(r => r.Id));
        Assert.Equal(1, NotesAsked());   // from disk
        Assert.Equal(["r1"], _cache.Load(f.Client, "stable")!.Releases.Select(r => r.Id));
    }

    [Fact]
    public async Task A_new_release_fetches_the_history_once()
    {
        Release("r1", "— первое");
        await _cache.GetAsync(f.Client, "stable", "r1", default);
        f.StageV2();
        Release("r2", "— второе");

        Assert.True(_cache.Due("stable", "r2", DateTime.UtcNow));
        var notes = await _cache.GetAsync(f.Client, "stable", "r2", default);
        Assert.Equal(["r2", "r1"], notes.Releases.Select(r => r.Id));
        await _cache.GetAsync(f.Client, "stable", "r2", default);
        Assert.Equal(2, NotesAsked());
        // the release not known yet (no update check so far): the kept one stands
        Assert.False(_cache.Due("stable", null, DateTime.UtcNow));
    }

    [Fact]
    public async Task Once_a_day_the_history_is_due_without_a_release()
    {
        Release("r1", "— первое");
        await _cache.GetAsync(f.Client, "stable", "r1", default);
        Assert.False(_cache.Due("stable", "r1", DateTime.UtcNow.AddHours(23)));
        Assert.True(_cache.Due("stable", "r1", DateTime.UtcNow.AddHours(24).AddMinutes(1)));
    }

    [Fact]
    public async Task A_kept_file_changed_on_disk_is_not_shown_and_is_fetched_anew()
    {
        Release("r1", "— первое");
        await _cache.GetAsync(f.Client, "stable", "r1", default);
        var path = _cache.FilePath("stable");
        var text = File.ReadAllText(path);
        Assert.Contains("\"sequence\":1,", text);   // control: the tamper below really changes the file
        File.WriteAllText(path, text.Replace("\"sequence\":1,", "\"sequence\":9,"));

        Assert.Null(_cache.Load(f.Client, "stable"));
        var notes = await _cache.GetAsync(f.Client, "stable", "r1", default);
        Assert.Equal("— первое", notes.Releases[0].Changelog["ru"]);
        Assert.Equal(2, NotesAsked());
        Assert.NotNull(_cache.Load(f.Client, "stable"));
    }

    [Fact]
    public async Task Under_a_running_game_the_history_is_shown_and_nothing_is_written()
    {
        Release("r1", "— первое");
        var running = new NotesCache(new GamePaths(f.Game)) { IsGameRunning = () => true };
        var notes = await running.GetAsync(f.Client, "stable", "r1", default);
        Assert.Equal(["r1"], notes.Releases.Select(r => r.Id));
        Assert.False(Directory.Exists(Path.GetDirectoryName(running.FilePath("stable"))));
        Assert.True(running.Due("stable", "r1", DateTime.UtcNow));
    }

    [Fact]
    public void A_channel_name_that_is_not_an_id_reads_nothing()
    {
        Assert.Null(_cache.Load(f.Client, "../stable"));
        Assert.True(_cache.Due("../stable", null, DateTime.UtcNow));
    }
}
