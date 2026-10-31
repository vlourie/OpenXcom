using System.Text;
using System.Text.Json;

namespace Xp.Launcher.Core.Tests;

public sealed class UpdateNoticeTests : IDisposable
{
    readonly string _root = Path.Combine(Path.GetTempPath(), "xp-tests", Guid.NewGuid().ToString("N"));
    readonly GamePaths _paths;

    public UpdateNoticeTests()
    {
        Directory.CreateDirectory(_root);
        _paths = new GamePaths(_root);
    }

    public void Dispose()
    {
        try { Directory.Delete(_root, recursive: true); } catch (IOException) { }
    }

    [Fact]
    public void The_game_reads_one_line_in_the_launcher_folder()
    {
        UpdateNotice.Raise(_paths, " 2026.10.23-1 ");
        Assert.Equal(Path.Combine(_root, "launcher", "update.txt"), UpdateNotice.PathIn(_paths));
        // what src/Engine/HdUpdateNotice reads: the release and a newline, no BOM
        Assert.Equal("2026.10.23-1\n", Encoding.UTF8.GetString(File.ReadAllBytes(UpdateNotice.PathIn(_paths))));
        Assert.Equal("2026.10.23-1", UpdateNotice.Read(_paths));
    }

    [Fact]
    public void The_same_release_again_leaves_the_file_alone_and_clear_removes_it()
    {
        UpdateNotice.Raise(_paths, "2026.10.23-1");
        var stamp = new DateTime(2020, 1, 1, 0, 0, 0, DateTimeKind.Utc);
        File.SetLastWriteTimeUtc(UpdateNotice.PathIn(_paths), stamp);
        UpdateNotice.Raise(_paths, "2026.10.23-1");
        Assert.Equal(stamp, File.GetLastWriteTimeUtc(UpdateNotice.PathIn(_paths)));
        UpdateNotice.Raise(_paths, "");
        Assert.Equal("2026.10.23-1", UpdateNotice.Read(_paths));

        UpdateNotice.Clear(_paths);
        Assert.Null(UpdateNotice.Read(_paths));
        UpdateNotice.Clear(_paths);                 // nothing there: no error
    }

    [Fact]
    public void A_stats_word_is_the_agreed_json_and_nothing_more()
    {
        var id = LauncherStats.NewInstallId();
        Assert.True(LauncherStats.IsInstallId(id));
        Assert.False(LauncherStats.IsInstallId(null));
        Assert.False(LauncherStats.IsInstallId(id.ToUpperInvariant()));
        Assert.False(LauncherStats.IsInstallId(id[..31]));

        using var doc = JsonDocument.Parse(LauncherStats.Body(id, true, "0.3.15", null));
        var names = doc.RootElement.EnumerateObject().Select(p => p.Name).ToArray();
        Assert.Equal(["install", "playing", "launcher", "game"], names);
        Assert.Equal(id, doc.RootElement.GetProperty("install").GetString());
        Assert.True(doc.RootElement.GetProperty("playing").GetBoolean());
        Assert.Equal("", doc.RootElement.GetProperty("game").GetString());
    }
}
