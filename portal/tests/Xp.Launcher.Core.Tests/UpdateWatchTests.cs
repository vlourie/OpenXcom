using Xp.Manifest;

namespace Xp.Launcher.Core.Tests;

/// <summary>The quarter-hour look at the channels of a running launcher: news without the manifest.</summary>
public sealed class UpdateWatchTests : IDisposable
{
    readonly Fixture f = new();
    public void Dispose() => f.Dispose();

    static readonly string[] Channels = ["stable", "launcher-stable"];

    [Fact]
    public async Task A_release_out_after_the_first_look_is_news_once_and_only_the_pointer_is_read()
    {
        f.StageV1();
        f.BuildAndPublish("2026.10.21-4");
        var watch = new UpdateWatch(f.Client);

        Assert.Empty(await watch.NewsAsync(Channels, default));   // the first look only remembers; no launcher channel - skipped
        Assert.Empty(await watch.NewsAsync(Channels, default));   // nothing new

        f.StageV2();
        f.BuildAndPublish("2026.10.21-5");
        f.Server.Requests.Clear();
        var news = Assert.Single(await watch.NewsAsync(Channels, default));
        Assert.Equal("2026.10.21-5", news.ReleaseId);
        Assert.All(f.Server.Requests, r => Assert.StartsWith("channels/", r.Key));   // the manifest runs to megabytes

        Assert.Empty(await watch.NewsAsync(Channels, default));   // told once
    }

    [Fact]
    public async Task A_release_after_the_check_is_news_on_the_very_first_look()
    {
        f.StageV1();
        f.BuildAndPublish("v1");
        var watch = new UpdateWatch(f.Client);
        watch.Know((await f.Client.GetLatestAsync("stable", 0, default)).Pointer);   // what the home page shows

        f.StageV2();
        f.BuildAndPublish("v2");
        Assert.Equal("v2", Assert.Single(await watch.NewsAsync(["stable"], default)).ReleaseId);
    }

    [Fact]
    public async Task An_old_pointer_served_again_is_no_news()
    {
        f.StageV1();
        f.BuildAndPublish("v1");
        var old = File.ReadAllBytes(Path.Combine(f.RepoDir, "channels", "stable.json"));
        var oldSig = File.ReadAllBytes(Path.Combine(f.RepoDir, "channels", "stable.json.sig"));
        f.StageV2();
        f.BuildAndPublish("v2");
        var watch = new UpdateWatch(f.Client);
        Assert.Empty(await watch.NewsAsync(["stable"], default));

        f.Server.Overrides["channels/stable.json"] = old;
        f.Server.Overrides["channels/stable.json.sig"] = oldSig;
        Assert.Empty(await watch.NewsAsync(["stable"], default));
    }
}
