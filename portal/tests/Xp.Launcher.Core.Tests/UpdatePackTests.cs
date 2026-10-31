using System.Formats.Tar;
using System.IO.Compression;
using System.Text;
using System.Text.Json;
using Xp.Manifest;
using Xp.ReleaseBuilder;

namespace Xp.Launcher.Core.Tests;

/// <summary>The update in one file: releases/&lt;id&gt;/packs/&lt;from&gt;.tar.br, and the blobs when it cannot be used.</summary>
public sealed class UpdatePackTests : IDisposable
{
    readonly Fixture f = new();
    public void Dispose() => f.Dispose();

    static readonly string Rules = string.Concat(Enumerable.Repeat("items:\n  - type: STR_PISTOL\n    power: 26\n", 3000));

    /// <summary>v1 installed, v2 built with a large ruleset - text, so the pack is far smaller than the files.</summary>
    async Task InstallV1BuildV2()
    {
        f.StageV1();
        f.BuildAndPublish("v1");
        await f.UpdateAsync();
        f.StageV2();
        Fixture.Write(f.Stage, "user/mods/hd/Ruleset/items.rul", Rules);
        f.Repo.Build(new BuildOptions { StageDir = f.Stage, Id = "v2", Version = "v2", Channel = "stable", Launch = "openxcom_hd.exe" }, f.Key);
        f.Server.Requests.Clear();
    }

    void AssertV2Installed()
    {
        Assert.Equal("engine v2", f.ReadGame("openxcom_hd.exe"));
        Assert.Equal("desert 0 v2", f.ReadGame("user/mods/hd/hd/TERRAIN/DESERT.PCK/0.png"));
        Assert.Equal("new in v2", f.ReadGame("user/mods/hd/hd/UI/new.png"));
        Assert.Equal(Rules, f.ReadGame("user/mods/hd/Ruleset/items.rul"));
        Assert.False(f.GameHas("user/mods/hd/hd/UI/old.png"));
        f.AssertPlayerDataIntact();
        Assert.Empty(Directory.EnumerateFiles(Path.Combine(f.Game, "launcher", "staging"), "pack-*"));
    }

    [Fact]
    public async Task An_update_comes_as_one_file()
    {
        await InstallV1BuildV2();
        var pack = Assert.Single(f.Repo.LoadManifest("v2").Packs);
        Assert.Equal("v1", pack.From);
        Assert.Equal(4, pack.Blobs);
        Assert.True(pack.Size < Rules.Length / 20, $"pack {pack.Size} bytes");
        f.Repo.Publish("stable", "v2", f.Key);
        f.Server.Gzip = true;   // the station gzips /releases/* for whoever asks: the pack must not ask (ranges, hash)

        await f.UpdateAsync();

        AssertV2Installed();
        Assert.Contains(f.Server.Requests, r => r.Key == "releases/v2/packs/v1.tar.br");
        Assert.DoesNotContain(f.Server.AskedGzip, k => k.Contains("/packs/"));
        Assert.DoesNotContain(f.Server.Requests, r => r.Key.StartsWith("blobs/"));
        Assert.Empty(f.Repo.Verify("stable", new TrustedKeys([Convert.ToBase64String(f.PublicKey)]), deep: true));
    }

    [Fact]
    public async Task An_update_comes_as_one_file_with_components_picked()
    {
        await InstallV1BuildV2();
        f.Repo.Publish("stable", "v2", f.Key);
        // a player through the setup wizard: the manifest is cut down to the picked components and must keep its packs (R-527)
        var components = f.Repo.LoadManifest("v2").Components.Select(c => c.Id).ToList();
        Assert.NotEmpty(components);
        var state = f.Updater.LoadState();
        state.Components = components;
        f.Updater.SaveState(state);

        await f.UpdateAsync();

        AssertV2Installed();
        Assert.Contains(f.Server.Requests, r => r.Key == "releases/v2/packs/v1.tar.br");
        Assert.DoesNotContain(f.Server.Requests, r => r.Key.StartsWith("blobs/"));
    }

    [Fact]
    public async Task A_first_install_takes_files_one_by_one()
    {
        f.StageV1();
        f.BuildAndPublish("v1");
        f.StageV2();
        f.BuildAndPublish("v2");
        Assert.Single(f.Repo.LoadManifest("v2").Packs);

        await f.UpdateAsync();   // nothing installed: no pack is from here

        Assert.Equal("engine v2", f.ReadGame("openxcom_hd.exe"));
        Assert.DoesNotContain(f.Server.Requests, r => r.Key.Contains("/packs/"));
    }

    [Fact]
    public async Task A_damaged_pack_falls_back_to_the_files()
    {
        await InstallV1BuildV2();
        f.Repo.Publish("stable", "v2", f.Key);
        f.Server.Overrides["releases/v2/packs/v1.tar.br"] = new byte[new FileInfo(Path.Combine(f.RepoDir, "releases/v2/packs/v1.tar.br")).Length];

        await f.UpdateAsync();

        AssertV2Installed();
        Assert.Contains(f.Log.Lines, l => l.StartsWith("ERROR pack from v1") && l.Contains("SHA-256"));
        Assert.Contains(f.Server.Requests, r => r.Key.StartsWith("blobs/"));
    }

    [Fact]
    public async Task A_pack_missing_on_the_server_falls_back_to_the_files()
    {
        await InstallV1BuildV2();
        f.Repo.Publish("stable", "v2", f.Key);
        File.Delete(Path.Combine(f.RepoDir, "releases/v2/packs/v1.tar.br"));
        Assert.Contains("missing pack from v1", f.Repo.Verify("stable", new TrustedKeys([Convert.ToBase64String(f.PublicKey)]), deep: false));

        await f.UpdateAsync();

        AssertV2Installed();
    }

    [Fact]
    public async Task A_signed_pack_with_a_path_inside_is_refused_and_writes_nothing()
    {
        await InstallV1BuildV2();
        // a pack that matches its signed hash but carries an entry that is not a blob name
        var evil = new MemoryStream();
        using (var br = new BrotliStream(evil, CompressionLevel.Fastest, leaveOpen: true))
        using (var tar = new TarWriter(br, TarEntryFormat.Ustar))
            tar.WriteEntry(new UstarTarEntry(TarEntryType.RegularFile, "../../evil.txt") { DataStream = new MemoryStream(Encoding.UTF8.GetBytes(Rules)) });
        var packPath = Path.Combine(f.RepoDir, "releases/v2/packs/v1.tar.br");
        File.WriteAllBytes(packPath, evil.ToArray());
        Resign("v2", m => { m.Packs[0].Size = evil.Length; m.Packs[0].Sha256 = Hashing.Sha256Hex(evil.ToArray()); });
        f.Repo.Publish("stable", "v2", f.Key);

        await f.UpdateAsync();

        AssertV2Installed();
        Assert.Contains(f.Log.Lines, l => l.StartsWith("ERROR pack from v1") && l.Contains("unexpected entry"));
        Assert.False(File.Exists(Path.Combine(f.Game, "evil.txt")));
        Assert.False(File.Exists(Path.Combine(f.Game, "launcher", "evil.txt")));
    }

    [Fact]
    public async Task A_pack_larger_than_the_files_it_replaces_is_not_used()
    {
        f.StageV1();
        f.BuildAndPublish("v1");
        await f.UpdateAsync();
        f.StageV2();   // a few bytes of changes: the tar headers alone outweigh them
        f.BuildAndPublish("v2");
        f.Server.Requests.Clear();

        await f.UpdateAsync();

        Assert.Equal("engine v2", f.ReadGame("openxcom_hd.exe"));
        Assert.DoesNotContain(f.Server.Requests, r => r.Key.Contains("/packs/"));
    }

    [Fact]
    public void A_manifest_with_a_bad_pack_is_refused()
    {
        f.StageV1();
        f.BuildAndPublish("v1");
        var m = f.Repo.LoadManifest("v1");
        m.Packs.Add(new UpdatePack { From = "../x", Size = 1, Sha256 = new string('a', 64), Blobs = 1 });
        Assert.Throws<ManifestException>(() => ManifestValidator.Validate(m));
        m.Packs[0].From = "v1";   // from itself
        Assert.Throws<ManifestException>(() => ManifestValidator.Validate(m));
    }

    // ------------------------------------------------------------ packs the site makes

    /// <summary>v1 installed, v2 published without a pack in its manifest: a release too old for the manifest's packs.</summary>
    async Task InstallV1PublishV2WithoutPacks()
    {
        f.StageV1();
        f.BuildAndPublish("v1");
        await f.UpdateAsync();
        f.StageV2();
        Fixture.Write(f.Stage, "user/mods/hd/Ruleset/items.rul", Rules);
        f.Repo.Build(new BuildOptions { StageDir = f.Stage, Id = "v2", Version = "v2", Channel = "stable", Launch = "openxcom_hd.exe", PackFrom = 0 }, f.Key);
        f.Repo.Publish("stable", "v2", f.Key);
        f.Server.Requests.Clear();
        f.Updater.LazyPackMinFiles = 1;
        f.Updater.Lazy = new LazyPacks(new HttpClient(f.Server), new Uri("http://portal.test/")) { Delay = (_, _) => Task.CompletedTask };
    }

    const string LazyKey = "0123456789abcdef0123456789abcdef";

    /// <summary>The site: "making it" the first time, then the pack of v2 from v1 at lazy/v2/&lt;key&gt;.tar.br.</summary>
    List<string> SiteMakesPack(int waits = 1)
    {
        var bodies = new List<string>();
        f.Server.Api = req =>
        {
            lock (bodies) bodies.Add(req.Content!.ReadAsStringAsync().Result);
            if (waits-- > 0)
            {
                var wait = new HttpResponseMessage(System.Net.HttpStatusCode.Accepted) { Content = new StringContent("{\"retryAfter\":5}") };
                wait.Headers.RetryAfter = new System.Net.Http.Headers.RetryConditionHeaderValue(TimeSpan.FromSeconds(5));
                return wait;
            }
            var have = f.Repo.LoadManifest("v1").Files.Select(x => x.Sha256).ToHashSet();
            var add = PackWriter.Order(f.Repo.LoadManifest("v2").Files.Where(x => !have.Contains(x.Sha256)));
            var p = PackWriter.Write("v1", add, sha => Path.Combine(f.RepoDir, BlobKeys.For(sha)), Path.Combine(f.RepoDir, "lazy", "v2", LazyKey + ".tar.br"), 4);
            var json = $"{{\"key\":\"{LazyKey}\",\"size\":{p.Size},\"sha256\":\"{p.Sha256}\",\"blobs\":{p.Blobs},\"raw\":{p.Raw}}}";
            return new HttpResponseMessage(System.Net.HttpStatusCode.OK) { Content = new StringContent(json, Encoding.UTF8, "application/json") };
        };
        return bodies;
    }

    [Fact]
    public async Task An_old_release_gets_its_update_as_one_file_the_site_makes()
    {
        await InstallV1PublishV2WithoutPacks();
        var asked = SiteMakesPack();

        await f.UpdateAsync();

        AssertV2Installed();
        Assert.Equal(2, asked.Count);   // "making it", then the pack
        Assert.Contains("\"from\":\"v1\"", asked[0]);
        Assert.Contains("\"to\":\"v2\"", asked[0]);
        Assert.Contains(f.Server.Requests, r => r.Key == $"lazy/v2/{LazyKey}.tar.br");
        Assert.DoesNotContain(f.Server.Requests, r => r.Key.StartsWith("blobs/"));
        Assert.Contains(f.Log.Lines, l => l.StartsWith("site pack from v1:"));
    }

    [Fact]
    public async Task Without_room_for_the_pack_beside_the_files_they_come_one_by_one()
    {
        await InstallV1PublishV2WithoutPacks();
        SiteMakesPack(waits: 0);
        var state = f.Updater.LoadState();
        var latest = await f.Updater.CheckAsync(state, default);
        var plan = f.Updater.Scan(state, latest.Manifest, false, null, default);
        long files = plan.ToWrite.DistinctBy(c => c.File.Sha256).Sum(c => c.File.Size) + plan.ToWrite.Sum(c => c.File.Size);
        f.Updater.FreeSpace = _ => files + 256L * 1024 * 1024 + 10;   // room for the files, not for the pack too

        await f.Updater.DownloadAsync(plan, null, default);
        f.Updater.Install(state, plan, null);

        AssertV2Installed();
        Assert.Contains(f.Server.Requests, r => r.Key.StartsWith("blobs/"));
        Assert.DoesNotContain(f.Server.Requests, r => r.Key.StartsWith("lazy/"));
        Assert.Contains(f.Log.Lines, l => l.StartsWith("no room for the site pack from v1"));
    }

    [Fact]
    public async Task When_the_site_makes_no_pack_the_files_come_one_by_one()
    {
        await InstallV1PublishV2WithoutPacks();
        f.Server.Api = _ => new HttpResponseMessage(System.Net.HttpStatusCode.NotFound);

        await f.UpdateAsync();

        AssertV2Installed();
        Assert.Contains(f.Server.Requests, r => r.Key.StartsWith("blobs/"));
        Assert.Contains(f.Log.Lines, l => l.StartsWith("no pack from the site for v1") && l.Contains("404"));
    }

    [Fact]
    public async Task A_site_that_takes_too_long_is_not_waited_for()
    {
        await InstallV1PublishV2WithoutPacks();
        SiteMakesPack(waits: 1000);

        await f.UpdateAsync();

        AssertV2Installed();
        Assert.Contains(f.Server.Requests, r => r.Key.StartsWith("blobs/"));
        Assert.Contains(f.Log.Lines, l => l.StartsWith("no pack from the site") && l.Contains("did not make it"));
    }

    [Fact]
    public async Task A_site_pack_that_is_not_what_the_site_said_is_thrown_away()
    {
        await InstallV1PublishV2WithoutPacks();
        SiteMakesPack(waits: 0);
        // the file the site serves is not the one it described: its hash fails, the files come one by one
        var real = f.Server.Api!;
        f.Server.Api = req =>
        {
            var resp = real(req);
            var size = new FileInfo(Path.Combine(f.RepoDir, "lazy", "v2", LazyKey + ".tar.br")).Length;
            lock (f.Server.Overrides) f.Server.Overrides[$"lazy/v2/{LazyKey}.tar.br"] = new byte[size];
            return resp;
        };

        await f.UpdateAsync();

        AssertV2Installed();
        Assert.Contains(f.Server.Requests, r => r.Key.StartsWith("blobs/"));
        Assert.Contains(f.Log.Lines, l => l.StartsWith("ERROR site pack from v1 failed") && l.Contains("SHA-256"));
    }

    [Fact]
    public async Task A_site_answer_that_is_no_pack_is_not_followed()
    {
        await InstallV1PublishV2WithoutPacks();
        f.Server.Api = _ => new HttpResponseMessage(System.Net.HttpStatusCode.OK)
        {
            Content = new StringContent($"{{\"key\":\"../../blobs/x\",\"size\":10,\"sha256\":\"{new string('a', 64)}\",\"blobs\":1,\"raw\":10}}"),
        };

        await f.UpdateAsync();

        AssertV2Installed();
        Assert.DoesNotContain(f.Server.Requests, r => r.Key.StartsWith("lazy/") || r.Key.Contains(".."));
        Assert.Contains(f.Log.Lines, l => l.StartsWith("no pack from the site") && l.Contains("not a pack"));
    }

    void Resign(string id, Action<ReleaseManifest> change)
    {
        var m = f.Repo.LoadManifest(id);
        change(m);
        var bytes = JsonSerializer.SerializeToUtf8Bytes(m, ManifestJson.Default.ReleaseManifest);
        var path = Path.Combine(f.RepoDir, BlobKeys.Manifest(id));
        File.WriteAllBytes(path, bytes);
        File.WriteAllBytes(path + ".sig", Signing.SerializeSignature(Signing.Sign(f.Key, bytes)));
    }
}
