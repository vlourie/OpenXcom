using System.IO.Compression;
using System.Net;
using System.Text;
using Xp.Manifest;

namespace Xp.Launcher.Core.Tests;

/// <summary>Games not ours (docs/portal/MODIO-GAMES.md): profiles by key, fetching from the author's site, TFTD.</summary>
public sealed class GameTests : IDisposable
{
    readonly Fixture f = new();
    public void Dispose() => f.Dispose();

    const string Url = "https://mods.test/40k.zip";

    /// <summary>Serves one file, and its tail for a Range request, as mod.io's CDN does.</summary>
    sealed class FileServer(byte[] body) : HttpMessageHandler
    {
        public int Requests;
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage req, CancellationToken ct)
        {
            Interlocked.Increment(ref Requests);
            if (req.RequestUri!.AbsoluteUri != Url) return Task.FromResult(new HttpResponseMessage(HttpStatusCode.NotFound));
            long from = req.Headers.Range?.Ranges.First().From ?? 0;
            var r = new HttpResponseMessage(from > 0 ? HttpStatusCode.PartialContent : HttpStatusCode.OK)
            {
                Content = new ByteArrayContent(body[(int)from..]),
            };
            return Task.FromResult(r);
        }
    }

    static byte[] Zip(params (string Path, string Text)[] files)
    {
        using var ms = new MemoryStream();
        using (var z = new ZipArchive(ms, ZipArchiveMode.Create, leaveOpen: true))
            foreach (var (path, text) in files)
            {
                using var s = z.CreateEntry(path).Open();
                s.Write(Encoding.UTF8.GetBytes(text));
            }
        return ms.ToArray();
    }

    static ModProfile Game(byte[] zip, string key = "40k") => new()
    {
        Master = "40k",
        Id = key == "40k" ? null : key,
        Source = new GameSource
        {
            Url = Url, Version = "039", Size = zip.Length, Sha256 = Hashing.Sha256Hex(zip),
            Folders = [new() { Name = "40k", Id = "40k" }, new() { Name = "Blood Angels", Id = "Blood Angels" }],
        },
    };

    GameInstaller Installer(byte[] body, out FileServer server)
    {
        server = new FileServer(body);
        var repo = new RepoClient(new HttpClient(server), new Uri("http://repo.test/"), new TrustedKeys([Convert.ToBase64String(f.PublicKey)]));
        return new GameInstaller(new GamePaths(f.Game), repo, f.Log) { IsGameRunning = _ => false, FreeSpace = _ => long.MaxValue };
    }

    static readonly (string, string)[] Good =
    [
        ("40k/metadata.yml", "id: 40k\nisMaster: true\n"),
        ("40k/Ruleset/a.rul", "items: []"),
        ("Blood Angels/metadata.yml", "name: Blood Angels\nmaster: 40k\n"),
        ("Readme of the author.txt", "not a mod"),
    ];

    [Fact]
    public void A_profile_is_found_by_its_own_id_before_its_master()
    {
        var set = new ProfileSet
        {
            Profiles = [new() { Master = "40k" }, new() { Id = "rosigma", Master = "40k" }, new() { Master = "piratez" }, new() { Id = "twots", Master = "xcom2" }],
        };
        Assert.Equal("rosigma", set.For("ROSIGMA")!.Key);
        Assert.Equal("40k", set.For("40k")!.Key);
        Assert.Equal("piratez", set.For("piratez")!.Key);
        // plain TFTD is not TWoTS: a profile with an id of its own is not the master's
        Assert.Null(set.For("xcom2"));
    }

    [Fact]
    public void A_build_of_rosigma_keeps_its_profile_though_the_master_is_40k()
    {
        Fixture.Write(f.Game, "standard/xcom1/metadata.yml", "id: xcom1\nisMaster: true\n");
        Fixture.Write(f.Game, "user/mods/40k/metadata.yml", "id: 40k\nisMaster: true\n");
        Fixture.Write(f.Game, "user/mods/rosigma/metadata.yml", "id: 40k_ROSIGMA_edits\nmaster: 40k\n");
        Fixture.Write(f.Game, ProfileSet.FileName, """
            { "profiles": [
              { "master": "40k", "mods": [ { "id": "*" } ] },
              { "id": "rosigma", "master": "40k", "requires": "40k", "mods": [ { "id": "40k_ROSIGMA_edits" }, { "id": "*" } ] } ] }
            """);
        var store = new BuildStore(new GamePaths(f.Game));
        store.Ensure("40k");
        var b = store.Create("ROSIGMA", "rosigma", "en", null);
        Assert.Equal("rosigma", b.Template);
        Assert.Equal("40k", b.EngineMaster);
        var cfg = OptionsCfg.Parse(File.ReadAllText(store.OptionsFile(b)));
        Assert.Contains(("40k_ROSIGMA_edits", true), cfg.Mods.Select(m => (m.Id, m.Active)));

        // applied again before a start, the build's own profile, not the first one of its master
        ProfileWriter.ApplyForGame(new GamePaths(f.Game), null, "en", null, resetMods: true, build: b, isGameRunning: _ => false);
        cfg = OptionsCfg.Parse(File.ReadAllText(store.OptionsFile(b)));
        Assert.Contains(("40k_ROSIGMA_edits", true), cfg.Mods.Select(m => (m.Id, m.Active)));
    }

    [Fact]
    public async Task A_game_is_fetched_checked_and_put_into_user_mods_folder_by_folder()
    {
        var zip = Zip(Good);
        var gi = Installer(zip, out _);
        var game = Game(zip);
        Assert.Equal(GameStatus.Missing, gi.Status(game));

        await gi.InstallAsync(game, null, default);

        Assert.Equal("items: []", f.ReadGame("user/mods/40k/Ruleset/a.rul"));
        Assert.True(f.GameHas("user/mods/Blood Angels/metadata.yml"));
        Assert.False(f.GameHas("user/mods/Readme of the author.txt"));
        Assert.False(f.GameHas("Readme of the author.txt"));
        Assert.Equal(GameStatus.Ready, gi.Status(game));
        Assert.Empty(Directory.EnumerateFiles(Path.Combine(f.Game, "launcher", "downloads")));
        f.AssertPlayerDataIntact();
    }

    [Fact]
    public async Task A_broken_download_resumes_where_it_stopped()
    {
        var zip = Zip(Good);
        var gi = Installer(zip, out var server);
        var game = Game(zip);
        var part = Path.Combine(f.Game, "launcher", "downloads", $"40k-{game.Source!.Sha256[..12]}.zip.part");
        Directory.CreateDirectory(Path.GetDirectoryName(part)!);
        File.WriteAllBytes(part, zip[..(zip.Length / 2)]);

        await gi.InstallAsync(game, null, default);

        Assert.Equal(1, server.Requests);
        Assert.Equal(GameStatus.Ready, gi.Status(game));
    }

    [Fact]
    public async Task An_archive_other_than_the_one_we_checked_is_refused_and_nothing_is_installed()
    {
        var zip = Zip(Good);
        var other = (byte[])zip.Clone();
        other[^1] ^= 1;   // the same size, another file: the author uploaded anew under the same link
        var gi = Installer(other, out _);

        await Assert.ThrowsAsync<TrustException>(() => gi.InstallAsync(Game(zip), null, default));
        Assert.False(f.GameHas("user/mods/40k/metadata.yml"));
        Assert.Empty(Directory.EnumerateFiles(Path.Combine(f.Game, "launcher", "downloads")));
    }

    [Fact]
    public async Task A_folder_whose_mod_id_is_not_the_checked_one_is_refused_and_the_old_version_stays()
    {
        Fixture.Write(f.Game, "user/mods/40k/metadata.yml", "id: 40k\nisMaster: true\nversion: old\n");
        var zip = Zip(("40k/metadata.yml", "id: something-else\n"), ("Blood Angels/metadata.yml", "master: 40k\n"));
        var gi = Installer(zip, out _);

        await Assert.ThrowsAsync<TrustException>(() => gi.InstallAsync(Game(zip), null, default));
        Assert.Contains("version: old", f.ReadGame("user/mods/40k/metadata.yml"));
        Assert.False(f.GameHas("user/mods/Blood Angels/metadata.yml"));
    }

    [Fact]
    public async Task An_entry_that_climbs_out_of_its_folder_is_refused()
    {
        var zip = Zip(("40k/metadata.yml", "id: 40k\nisMaster: true\n"), ("40k/../../../evil.txt", "x"),
            ("Blood Angels/metadata.yml", "master: 40k\n"));
        var gi = Installer(zip, out _);

        await Assert.ThrowsAsync<UnsafePathException>(() => gi.InstallAsync(Game(zip), null, default));
        Assert.False(File.Exists(Path.Combine(f.Root, "evil.txt")));
        Assert.False(f.GameHas("user/mods/40k/metadata.yml"));
    }

    [Fact]
    public async Task Nothing_is_changed_under_a_running_game()
    {
        var zip = Zip(Good);
        var gi = Installer(zip, out var server);
        gi.IsGameRunning = _ => true;

        await Assert.ThrowsAsync<UpdateBlockedException>(() => gi.InstallAsync(Game(zip), null, default));
        Assert.Equal(0, server.Requests);
    }

    [Fact]
    public void A_game_brings_the_one_it_runs_on_first()
    {
        var zip = Zip(Good);
        var gi = Installer(zip, out _);
        var plain = Game(zip);
        var rosigma = new ModProfile
        {
            Id = "rosigma", Master = "40k", Requires = "40k",
            Source = new GameSource { Url = Url, Size = 1, Sha256 = new string('a', 64), Folders = [new() { Name = "rosigma", Id = "40k_ROSIGMA_edits" }] },
        };
        var set = new ProfileSet { Profiles = [plain, rosigma] };

        Assert.Equal(["40k", "rosigma"], gi.ToFetch(set, rosigma).Select(p => p.Key));
    }

    [Fact]
    public void Tftd_counts_as_there_only_with_the_folders_the_engine_takes()
    {
        var tftd = Path.Combine(f.Root, "steam", "TFD");
        foreach (var d in TftdData.DataDirs) Fixture.Write(tftd, d + "/x.dat", "x");
        foreach (var k in UfoData.KeyFiles) Fixture.Write(tftd, k, "x");
        Fixture.Write(f.Game, "TFTD/README.txt", "put TFTD here");
        Assert.False(TftdData.Check(Path.Combine(f.Game, "TFTD")).Ok);

        var r = TftdData.Copy(tftd, f.Game);

        Assert.True(r.Ok);
        Assert.True(f.GameHas("TFTD/GEODATA/PALETTES.DAT"));
        Assert.True(f.GameHas("TFTD/README.txt"));
    }
}
