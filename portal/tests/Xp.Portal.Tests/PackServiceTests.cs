using System.Net;
using System.Net.Http.Json;
using System.Text;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using Microsoft.Extensions.Time.Testing;
using Xp.Launcher.Core;
using Xp.Manifest;
using Xp.Portal.Packs;
using Xp.ReleaseBuilder;

namespace Xp.Portal.Tests;

/// <summary>The update from any release in one file, made by the site from a repository the release builder wrote.</summary>
public sealed class PackServiceTests : IDisposable
{
    readonly string _root = Path.Combine(Path.GetTempPath(), "xp-packs-" + Guid.NewGuid().ToString("N")[..8]);
    string Repo => Path.Combine(_root, "repo");
    string Stage => Path.Combine(_root, "stage");
    string Cache => Path.Combine(_root, "cache");
    readonly (byte[] Key, byte[] Pub) _keys = Signing.CreateKeyPair();
    readonly ListLogger _log = new();

    public void Dispose()
    {
        try { Directory.Delete(_root, recursive: true); } catch (IOException) { }
    }

    static void Write(string dir, string rel, string text)
    {
        var p = Path.Combine(dir, rel.Replace('/', Path.DirectorySeparatorChar));
        Directory.CreateDirectory(Path.GetDirectoryName(p)!);
        File.WriteAllText(p, text);
    }

    ReleaseRepo R => _repoAt ??= new ReleaseRepo(Repo);
    ReleaseRepo? _repoAt;

    /// <summary>Engine, a master mod and the hd art layer, as a real edition splits them.</summary>
    void StageV1()
    {
        Write(Stage, "openxcom_hd.exe", "engine v1");
        Write(Stage, "user/mods/Piratez/metadata.yml", "id: piratez\nisMaster: true\nmaster: xcom1\n");
        Write(Stage, "user/mods/Piratez/Ruleset/a.rul", "rules v1");
        Write(Stage, "user/mods/hd/metadata.yml", "id: hd\nmaster: \"*\"\nversion: 2.0\nrequiredExtendedEngine: OXCE-HD\n");
        Write(Stage, "user/mods/hd/hd/UI/a.png", "picture a v1");
        Write(Stage, "user/mods/hd/hd/UI/b.png", "picture b");
    }

    void Publish(string id)
    {
        var o = new BuildOptions { StageDir = Stage, Id = id, Version = "1", Line = "oxce-hd", Launch = "openxcom_hd.exe", PackFrom = 0 };
        o.Engines.AddRange(["Extended", "OXCE-HD"]);
        o.Components["engine"] = "8.7.0-hd";
        R.Build(o, _keys.Key);
        R.Publish("stable", id, _keys.Key);
    }

    PackService Service(double capGb = 30) => new(Options.Create(new PackOptions { ReleaseDir = Repo, CacheDir = Cache, CacheMaxGb = capGb }),
        _log, new FakeTimeProvider(DateTimeOffset.UtcNow));

    static async Task<PackAnswer> Made(PackService s, PackRequest r)
    {
        Assert.Equal(PackState.Building, s.Ask(r).State);
        await s.Idle();
        return s.Ask(r);
    }

    /// <summary>The blob names inside a pack, read the way the launcher reads it.</summary>
    HashSet<string> Inside(string to, PackOffer offer)
    {
        var pack = Path.Combine(Cache, to, offer.Key + ".tar.br");
        Assert.Equal(offer.Size, new FileInfo(pack).Length);
        Assert.Equal(offer.Sha256, Hashing.FileSha256(pack));
        var all = R.LoadManifest(to).Files.Concat(R.LoadManifest("v1").Files).DistinctBy(f => f.Sha256).ToDictionary(f => f.Sha256, f => f.Size);
        var outDir = Path.Combine(_root, "unpacked-" + offer.Key);
        Directory.CreateDirectory(outDir);
        var got = new HashSet<string>();
        PackReader.Unpack(pack, all, sha => Path.Combine(outDir, sha), sha => got.Add(sha), default);
        return got;
    }

    static string Sha(string text) => Hashing.Sha256Hex(Encoding.UTF8.GetBytes(text));

    async Task V1ToV2()
    {
        StageV1();
        Publish("v1");
        Write(Stage, "openxcom_hd.exe", "engine v2");
        Write(Stage, "user/mods/hd/hd/UI/a.png", "picture a v2");
        Write(Stage, "user/mods/hd/hd/UI/c.png", "picture c");
        Publish("v2");
        await Task.CompletedTask;
    }

    [Fact]
    public async Task The_update_from_an_old_release_comes_in_one_pack_with_only_what_changed()
    {
        await V1ToV2();
        var s = Service();

        var a = await Made(s, new PackRequest("stable", "v2", "v1", ["art.hd"]));

        Assert.Equal(PackState.Ready, a.State);
        Assert.Equal(3, a.Offer!.Blobs);
        Assert.Equal([Sha("engine v2"), Sha("picture a v2"), Sha("picture c")], Inside("v2", a.Offer).Order());
        // asked again: the same file, not a second build
        Assert.Equal(a.Offer, s.Ask(new PackRequest("stable", "v2", "v1", ["art.hd"])).Offer);
        Assert.Single(_log.Lines, l => l.StartsWith("pack v2 from v1"));
    }

    [Fact]
    public async Task Without_the_art_layer_the_pack_carries_only_engine_and_mods()
    {
        await V1ToV2();
        var a = await Made(Service(), new PackRequest("stable", "v2", "v1", []));

        Assert.Equal([Sha("engine v2")], Inside("v2", a.Offer!));
    }

    [Fact]
    public async Task A_first_install_gets_the_whole_release()
    {
        await V1ToV2();
        var a = await Made(Service(), new PackRequest("stable", "v2", "", ["art.hd"]));

        var want = R.LoadManifest("v2").Files.Select(f => f.Sha256).ToHashSet();
        Assert.Equal(want.Order(), Inside("v2", a.Offer!).Order());
    }

    [Fact]
    public async Task One_pack_is_made_once_however_many_ask_at_once()
    {
        await V1ToV2();
        var s = Service();
        var r = new PackRequest("stable", "v2", "v1", ["art.hd"]);

        var answers = await Task.WhenAll(Enumerable.Range(0, 16).Select(_ => Task.Run(() => s.Ask(r))));
        await s.Idle();

        Assert.All(answers, x => Assert.Equal(PackState.Building, x.State));
        Assert.Equal(PackState.Ready, s.Ask(r).State);
        Assert.Single(_log.Lines, l => l.StartsWith("pack v2 from v1"));
    }

    [Fact]
    public async Task Releases_that_are_not_there_or_not_a_target_are_not_packed()
    {
        await V1ToV2();
        var s = Service();

        Assert.Equal(PackState.NotFound, s.Ask(new PackRequest("stable", "v2", "v0", [])).State);        // never published
        Assert.Equal(PackState.NotFound, s.Ask(new PackRequest("test", "v2", "v1", [])).State);          // not a channel of packs
        Assert.Equal(PackState.NotFound, s.Ask(new PackRequest("stable", "v9", "v1", [])).State);        // no such target
        Assert.Throws<ArgumentException>(() => s.Ask(new PackRequest("stable", "v2", "../v1", [])));
        Assert.Throws<ArgumentException>(() => s.Ask(new PackRequest("stable", "v2", "v1", ["art.nope"])));
        Assert.Throws<ArgumentException>(() => s.Ask(new PackRequest("stable", "v2", "v2", [])));
        await s.Idle();
        Assert.False(Directory.Exists(Cache) && Directory.EnumerateFiles(Cache, "*", SearchOption.AllDirectories).Any());
    }

    [Fact]
    public async Task Nothing_to_pack_is_said_so()
    {
        await V1ToV2();
        Write(Stage, "user/mods/hd/hd/UI/b.png", "picture b v3");   // only art changes
        Publish("v3");

        var a = await Made(Service(), new PackRequest("stable", "v3", "v2", []));

        Assert.Equal(PackState.Empty, a.State);
    }

    [Fact]
    public async Task Packs_to_old_releases_go_and_the_cache_keeps_to_its_size()
    {
        await V1ToV2();
        var s = Service(capGb: 1e-12);   // smaller than any pack: only the one just made stays
        var first = (await Made(s, new PackRequest("stable", "v2", "v1", ["art.hd"]))).Offer!;
        var second = (await Made(s, new PackRequest("stable", "v2", "", ["art.hd"]))).Offer!;
        Assert.False(File.Exists(Path.Combine(Cache, "v2", first.Key + ".tar.br")));
        Assert.True(File.Exists(Path.Combine(Cache, "v2", second.Key + ".tar.br")));

        Write(Stage, "openxcom_hd.exe", "engine v3");
        Publish("v3");
        Write(Stage, "openxcom_hd.exe", "engine v4");
        Publish("v4");
        await Made(s, new PackRequest("stable", "v4", "v1", []));

        Assert.False(Directory.Exists(Path.Combine(Cache, "v2")));   // v4 is current, v3 before it: v2 is no target
        Assert.True(Directory.Exists(Path.Combine(Cache, "v4")));
    }

    [Fact]
    public async Task The_launcher_asks_the_site_and_comes_back_for_the_pack()
    {
        await V1ToV2();
        var web = new PortalFactory();
        web.Settings["Packs:ReleaseDir"] = Repo;
        web.Settings["Packs:CacheDir"] = Cache;
        await web.InitializeAsync();
        try
        {
            var http = web.CreateClient();
            var ask = new { channel = "stable", to = "v2", from = "v1", art = new[] { "art.hd" } };

            var first = await http.PostAsJsonAsync("/api/v1/packs", ask);
            Assert.Equal(HttpStatusCode.Accepted, first.StatusCode);
            Assert.Equal(TimeSpan.FromSeconds(PackService.RetryAfterSeconds), first.Headers.RetryAfter?.Delta);
            await web.Services.GetRequiredService<PackService>().Idle();

            var ready = await http.PostAsJsonAsync("/api/v1/packs", ask);
            Assert.Equal(HttpStatusCode.OK, ready.StatusCode);
            var offer = (await ready.Content.ReadFromJsonAsync<PackOffer>())!;
            Assert.Equal(PackService.Key("v2", "v1", ["art.hd"]), offer.Key);
            Assert.True(File.Exists(Path.Combine(Cache, "v2", offer.Key + ".tar.br")));

            var unknown = await http.PostAsJsonAsync("/api/v1/packs", ask with { from = "v0" });
            Assert.Equal(HttpStatusCode.NotFound, unknown.StatusCode);
            Assert.Contains("pack_unknown_release", await unknown.Content.ReadAsStringAsync());
            var bad = await http.PostAsJsonAsync("/api/v1/packs", ask with { from = "../v1" });
            Assert.Equal(HttpStatusCode.BadRequest, bad.StatusCode);
            Assert.Contains("pack_invalid", await bad.Content.ReadAsStringAsync());
        }
        finally { await web.DisposeAsync(); }
    }

    [Fact]
    public async Task A_site_without_a_pack_cache_says_so()
    {
        var web = new PortalFactory();
        await web.InitializeAsync();
        try
        {
            var r = await web.CreateClient().PostAsJsonAsync("/api/v1/packs", new { channel = "stable", to = "v2", from = "v1", art = Array.Empty<string>() });
            Assert.Equal(HttpStatusCode.NotFound, r.StatusCode);
            Assert.Contains("packs_off", await r.Content.ReadAsStringAsync());
        }
        finally { await web.DisposeAsync(); }
    }

    sealed class ListLogger : ILogger<PackService>
    {
        public List<string> Lines { get; } = new();
        public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;
        public bool IsEnabled(LogLevel level) => true;
        public void Log<TState>(LogLevel level, EventId id, TState state, Exception? e, Func<TState, Exception?, string> format)
        {
            lock (Lines) Lines.Add(format(state, e));
        }
    }
}
