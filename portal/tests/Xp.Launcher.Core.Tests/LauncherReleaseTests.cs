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

    /// <summary>l3 over l2 with an exe that packs well (text): the release carries a pack from l2.</summary>
    async Task<ReleaseManifest> PublishL3()
    {
        var exe = string.Concat(Enumerable.Repeat("launcher 3.0 code ", 20000));
        Fixture.Write(Launcher, "XPiratezLauncher.exe", exe);
        f.Repo.Build(new BuildOptions { StageDir = Launcher, Id = "l3", Version = "3.0.0", Channel = "launcher-stable", LauncherKind = true }, f.Key);
        f.Repo.Publish("launcher-stable", "l3", f.Key);
        var m = await LatestAsync();
        Assert.Equal("l2", Assert.Single(m.Packs).From);
        return m;
    }

    [Fact]
    public async Task A_launcher_update_comes_as_the_pack_from_the_running_release()
    {
        var running = Path.Combine(f.Root, "running");
        await LauncherRelease.FetchAsync(_repo, await LatestAsync(), running, "XPiratezLauncher.exe", null, _ => { }, default);
        var m = await PublishL3();
        lock (f.Server.Requests) f.Server.Requests.Clear();

        long bytes = 0;
        await LauncherRelease.FetchAsync(_repo, m, Into, "XPiratezLauncher.exe", running, n => bytes += n, default, packFrom: "l2");

        Assert.Equal(File.ReadAllText(Path.Combine(Launcher, "XPiratezLauncher.exe")), File.ReadAllText(Path.Combine(Into, "XPiratezLauncher.exe")));
        Assert.Equal("bootstrap 2.0", File.ReadAllText(Path.Combine(Into, "xp-bootstrap.exe")));
        Assert.Equal(m.Files.Sum(x => x.Size), bytes);
        Assert.Equal(0, BlobRequests());
        lock (f.Server.Requests) Assert.Contains(f.Server.Requests, r => r.Key == "releases/l3/packs/l2.tar.br");
        Assert.Equal(new[] { "into" }, Directory.GetFileSystemEntries(f.Root, "into*").Select(e => Path.GetFileName(e)).ToArray());   // pack and blobs cleaned up
    }

    sealed class Seen : IProgress<Progress>
    {
        public readonly List<Progress> All = [];
        public void Report(Progress p) { lock (All) All.Add(p); }
    }

    [Fact]
    public async Task The_window_sees_the_download_of_the_files_up_to_their_size()
    {
        var m = await LatestAsync();
        var seen = new Seen();
        await LauncherRelease.FetchAsync(_repo, m, Into, "XPiratezLauncher.exe", null, _ => { }, default, progress: seen);
        var last = seen.All[^1];
        Assert.All(seen.All, p => Assert.Equal(Phase.Downloading, p.Phase));
        Assert.Equal(m.Files.Sum(x => x.Size), last.Total);
        Assert.Equal(last.Total, last.Done);
    }

    [Fact]
    public async Task The_window_sees_the_download_of_the_pack_up_to_its_size()
    {
        var running = Path.Combine(f.Root, "running");
        await LauncherRelease.FetchAsync(_repo, await LatestAsync(), running, "XPiratezLauncher.exe", null, _ => { }, default);
        var m = await PublishL3();
        var seen = new Seen();
        await LauncherRelease.FetchAsync(_repo, m, Into, "XPiratezLauncher.exe", running, _ => { }, default, packFrom: "l2", progress: seen);
        Assert.NotEmpty(seen.All);
        Assert.All(seen.All, p => Assert.Equal("pack l2", p.Current));
        Assert.Equal(m.Packs[0].Size, seen.All[^1].Done);
        Assert.Equal(m.Packs[0].Size, seen.All[^1].Total);
    }

    [Fact]
    public async Task A_damaged_launcher_pack_falls_back_to_the_files()
    {
        var m = await PublishL3();
        f.Server.Overrides["releases/l3/packs/l2.tar.br"] = new byte[m.Packs[0].Size];   // the size the manifest gives, other bytes
        await LauncherRelease.FetchAsync(_repo, m, Into, "XPiratezLauncher.exe", null, _ => { }, default, packFrom: "l2");
        Assert.Equal(File.ReadAllText(Path.Combine(Launcher, "XPiratezLauncher.exe")), File.ReadAllText(Path.Combine(Into, "XPiratezLauncher.exe")));
        Assert.True(BlobRequests() > 0);
    }

    [Fact]
    public void The_running_launcher_names_its_release_as_the_release_script_does()
    {
        Assert.Equal("launcher-0.3.20", LauncherRelease.IdFor("0.3.20", "launcher-stable"));
        Assert.Equal("launcher-0.3.20-beta", LauncherRelease.IdFor("0.3.20", "launcher-beta"));
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
