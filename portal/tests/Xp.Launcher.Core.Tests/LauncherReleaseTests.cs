using Xp.Manifest;
using Xp.ReleaseBuilder;

namespace Xp.Launcher.Core.Tests;

/// <summary>
/// The one fetch of a launcher release that both the setup and the launcher's self-update use (audit P-7).
/// </summary>
public sealed class LauncherReleaseTests : IDisposable
{
    readonly Fixture f = new();
    readonly RepoClient _repo;
    string Launcher => Path.Combine(f.Root, "launcher-stage");
    string Into => Path.Combine(f.Root, "into");

    public LauncherReleaseTests()
    {
        _repo = new RepoClient(new HttpClient(f.Server), new Uri("http://repo.test/"), new TrustedKeys([Convert.ToBase64String(f.PublicKey)]));
        Fixture.Write(Launcher, "XPiratezLauncher.exe", "launcher 2.0");
        Fixture.Write(Launcher, "xp-bootstrap.exe", "bootstrap 2.0");
        Fixture.Write(Launcher, "libsodium.dll", "sodium");
        f.Repo.Build(new BuildOptions { StageDir = Launcher, Id = "l2", Version = "2.0.0", Channel = "launcher-stable", LauncherKind = true }, f.Key);
        f.Repo.Publish("launcher-stable", "l2", f.Key);
    }

    public void Dispose() => f.Dispose();

    async Task<ReleaseManifest> LatestAsync() => (await _repo.GetLatestAsync(LauncherRelease.ChannelFor("stable"), 0, default)).Manifest;

    int BlobRequests() { lock (f.Server.Requests) return f.Server.Requests.Count(r => r.Key.StartsWith("blobs/")); }

    [Fact]
    public async Task Every_file_arrives_verified_and_the_progress_sums_to_the_release()
    {
        var m = await LatestAsync();
        long bytes = 0;
        await LauncherRelease.FetchAsync(_repo, m, Into, "XPiratezLauncher.exe", null, n => bytes += n, default);
        Assert.Equal("launcher 2.0", File.ReadAllText(Path.Combine(Into, "XPiratezLauncher.exe")));
        Assert.Equal("bootstrap 2.0", File.ReadAllText(Path.Combine(Into, "xp-bootstrap.exe")));
        Assert.Equal(m.Files.Sum(x => x.Size), bytes);

        // a second run finds everything in place and downloads nothing
        var before = BlobRequests();
        bytes = 0;
        await LauncherRelease.FetchAsync(_repo, m, Into, "XPiratezLauncher.exe", null, n => bytes += n, default);
        Assert.Equal(before, BlobRequests());
        Assert.Equal(m.Files.Sum(x => x.Size), bytes);
    }

    [Fact]
    public async Task A_file_the_running_launcher_already_has_is_copied_not_downloaded()
    {
        var m = await LatestAsync();
        var running = Path.Combine(f.Root, "running");
        Fixture.Write(running, "libsodium.dll", "sodium");            // the same file
        Fixture.Write(running, "xp-bootstrap.exe", "bootstrap 1.0");   // an older one: must not be taken
        await LauncherRelease.FetchAsync(_repo, m, Into, "XPiratezLauncher.exe", running, _ => { }, default);

        Assert.Equal("sodium", File.ReadAllText(Path.Combine(Into, "libsodium.dll")));
        Assert.Equal("bootstrap 2.0", File.ReadAllText(Path.Combine(Into, "xp-bootstrap.exe")));
        var sodium = BlobKeys.For(Hashing.Sha256Hex("sodium"u8));
        lock (f.Server.Requests) Assert.DoesNotContain(f.Server.Requests, r => r.Key == sodium);
    }

    [Fact]
    public async Task A_release_without_the_launcher_exe_is_refused_before_anything_is_fetched()
    {
        var m = await LatestAsync();
        var before = BlobRequests();
        await Assert.ThrowsAsync<ManifestException>(() =>
            LauncherRelease.FetchAsync(_repo, m, Into, "SomeOtherLauncher.exe", null, _ => { }, default));
        Assert.Equal(before, BlobRequests());
        Assert.False(Directory.Exists(Into));
    }

    [Fact]
    public async Task A_swapped_blob_never_lands_under_its_name()
    {
        var m = await LatestAsync();
        var exe = m.Files.Single(x => x.Path == "XPiratezLauncher.exe");
        f.Server.Overrides[BlobKeys.For(exe.Sha256)] = "launcher 6.6"u8.ToArray();   // same size, other bytes
        await Assert.ThrowsAsync<TrustException>(() =>
            LauncherRelease.FetchAsync(_repo, m, Into, "XPiratezLauncher.exe", null, _ => { }, default));
        Assert.False(File.Exists(Path.Combine(Into, "XPiratezLauncher.exe")));
    }
}
