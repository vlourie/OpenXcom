using System.Net;
using System.Text.Json;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;
using Xp.Manifest;

namespace Xp.Portal.Tests;

/// <summary>The portal with a release repository of its own: a launcher release signed by a test key.</summary>
public sealed class ReleaseRepoFactory : PortalFactory
{
    public const string Setup = "setup of the launcher, version 1.2.3";
    public Dictionary<string, byte[]> Blobs { get; } = new();

    public ReleaseRepoFactory()
    {
        var (key, pub) = Signing.CreateKeyPair();
        Settings["Portal:ReleaseRepo"] = "http://repo.test/";
        Settings["Portal:ReleaseKeys:0"] = Convert.ToBase64String(pub);
        Settings["Portal:LauncherChannel"] = "launcher-stable";

        var setup = System.Text.Encoding.UTF8.GetBytes(Setup);
        var m = new ReleaseManifest
        {
            Release = new ReleaseInfo { Id = "launcher-1.2.3", Version = "1.2.3", Channel = "launcher-stable", MinLauncher = "0.0.0" },
            Roots = ["xp-bootstrap.exe"],
            Components = [new ComponentInfo { Id = "launcher", Kind = ComponentKind.Launcher }],
            Files = [new ManifestFile { Path = "xp-bootstrap.exe", Size = setup.Length, Sha256 = Hashing.Sha256Hex(setup), Component = "launcher" }],
        };
        var mBytes = JsonSerializer.SerializeToUtf8Bytes(m, ManifestJson.Default.ReleaseManifest);
        var pointer = new ChannelPointer { Channel = "launcher-stable", Sequence = 1, ReleaseId = "launcher-1.2.3", ManifestSha256 = Hashing.Sha256Hex(mBytes), ManifestSize = mBytes.Length };
        var pBytes = JsonSerializer.SerializeToUtf8Bytes(pointer, ManifestJson.Default.ChannelPointer);
        Blobs[BlobKeys.Manifest("launcher-1.2.3")] = mBytes;
        Blobs[BlobKeys.Sig(BlobKeys.Manifest("launcher-1.2.3"))] = Signing.SerializeSignature(Signing.Sign(key, mBytes));
        Blobs[BlobKeys.Channel("launcher-stable")] = pBytes;
        Blobs[BlobKeys.Sig(BlobKeys.Channel("launcher-stable"))] = Signing.SerializeSignature(Signing.Sign(key, pBytes));
        Blobs[BlobKeys.For(Hashing.Sha256Hex(setup))] = setup;

        // the history of the game channel, as xp-release writes it: newest first, roadmap beside
        Settings["Portal:ReleaseChannel"] = "stable";
        var notes = new ChannelNotes
        {
            Channel = "stable", Sequence = 4,
            Releases =
            [
                new ReleaseNote { Id = "2026.10.15-2", Version = "2026.10.15.2", Published = new DateTimeOffset(2026, 10, 15, 12, 0, 0, TimeSpan.Zero), Changelog = { ["ru"] = "- walls-ru-2", ["en"] = "- walls-en-2" } },
                new ReleaseNote { Id = "2026.10.14", Version = "2026.10.14", Published = new DateTimeOffset(2026, 10, 14, 12, 0, 0, TimeSpan.Zero), Changelog = { ["ru"] = "- floors-ru-1" } },
                new ReleaseNote { Id = "2026.10.13", Version = "2026.10.13", Published = new DateTimeOffset(2026, 10, 13, 12, 0, 0, TimeSpan.Zero) },
            ],
            Roadmap = { ["ru"] = "## Plan-ru\n\n- inventory-next", ["en"] = "## Plan-en\n\n- inventory-next" },
        };
        // the latest game release: the mod writes its version as "v.o9", and the entrance screen must say "o9"
        var game = new ReleaseManifest
        {
            Release = new ReleaseInfo
            {
                Id = "2026.10.15-2", Version = "2026.10.15.2", Channel = "stable", Launch = "openxcom_hd.exe",
                Published = new DateTimeOffset(2026, 10, 15, 12, 0, 0, TimeSpan.Zero), Changelog = { ["ru"] = "- walls-ru-2" },
            },
            Roots = ["openxcom_hd.exe"],
            Components =
            [
                new ComponentInfo { Id = "engine", Kind = ComponentKind.Engine, Name = "engine" },
                new ComponentInfo { Id = "mod.piratez", Kind = ComponentKind.Master, Mod = "piratez", Name = "X-Piratez", Version = "v.o9", Master = "xcom1" },
            ],
            Files = [new ManifestFile { Path = "openxcom_hd.exe", Size = 1, Sha256 = Hashing.Sha256Hex([1]), Component = "engine" }],
        };
        var gBytes = JsonSerializer.SerializeToUtf8Bytes(game, ManifestJson.Default.ReleaseManifest);
        var gPointer = new ChannelPointer { Channel = "stable", Sequence = 4, ReleaseId = "2026.10.15-2", ManifestSha256 = Hashing.Sha256Hex(gBytes), ManifestSize = gBytes.Length };
        var gpBytes = JsonSerializer.SerializeToUtf8Bytes(gPointer, ManifestJson.Default.ChannelPointer);
        Blobs[BlobKeys.Manifest("2026.10.15-2")] = gBytes;
        Blobs[BlobKeys.Sig(BlobKeys.Manifest("2026.10.15-2"))] = Signing.SerializeSignature(Signing.Sign(key, gBytes));
        Blobs[BlobKeys.Channel("stable")] = gpBytes;
        Blobs[BlobKeys.Sig(BlobKeys.Channel("stable"))] = Signing.SerializeSignature(Signing.Sign(key, gpBytes));

        var nBytes = JsonSerializer.SerializeToUtf8Bytes(notes, ManifestJson.Default.ChannelNotes);
        Blobs[BlobKeys.Notes("stable")] = nBytes;
        Blobs[BlobKeys.Sig(BlobKeys.Notes("stable"))] = Signing.SerializeSignature(Signing.Sign(key, nBytes));
    }

    public string SetupKey => BlobKeys.For(Hashing.Sha256Hex(System.Text.Encoding.UTF8.GetBytes(Setup)));

    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        base.ConfigureWebHost(builder);
        builder.ConfigureTestServices(services =>
            services.AddHttpClient("releases").ConfigurePrimaryHttpMessageHandler(() => new Repo(Blobs)));
    }

    sealed class Repo(Dictionary<string, byte[]> blobs) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            byte[]? body;
            lock (blobs) blobs.TryGetValue(request.RequestUri!.AbsolutePath.TrimStart('/'), out body);
            return Task.FromResult(body is null
                ? new HttpResponseMessage(HttpStatusCode.NotFound)
                : new HttpResponseMessage(HttpStatusCode.OK) { Content = new ByteArrayContent(body) });
        }
    }
}

/// <summary>
/// /download/launcher hands out the setup straight from the release repository. The person who downloads
/// it has nothing yet to check it with, so the site checks it for them against the signed manifest - and
/// a file the repository swapped is not handed out at all (audit P-5).
/// </summary>
public sealed class LauncherDownloadTests(ReleaseRepoFactory f) : IClassFixture<ReleaseRepoFactory>
{
    [Fact]
    public async Task The_setup_is_handed_out_only_while_it_matches_the_signed_manifest()
    {
        var c = f.CreateClient();
        var good = await c.GetAsync("/download/launcher");
        Assert.Equal(HttpStatusCode.OK, good.StatusCode);
        Assert.Equal(ReleaseRepoFactory.Setup, await good.Content.ReadAsStringAsync());
        Assert.Equal("XPiratezHD-Setup-1.2.3.exe", good.Content.Headers.ContentDisposition?.FileName);

        var original = f.Blobs[f.SetupKey];
        try
        {
            // the same size, one byte different: only the hash tells them apart
            var swapped = (byte[])original.Clone();
            swapped[0] ^= 0x20;
            lock (f.Blobs) f.Blobs[f.SetupKey] = swapped;
            Assert.Equal(HttpStatusCode.InternalServerError, (await c.GetAsync("/download/launcher")).StatusCode);

            // and a longer file with the right beginning
            lock (f.Blobs) f.Blobs[f.SetupKey] = [.. original, .. "tail"u8.ToArray()];
            Assert.Equal(HttpStatusCode.InternalServerError, (await c.GetAsync("/download/launcher")).StatusCode);
        }
        finally { lock (f.Blobs) f.Blobs[f.SetupKey] = original; }
    }

    [Fact]
    public async Task Every_update_is_listed_newest_first_with_its_own_text()
    {
        var html = await f.CreateClient().GetStringAsync("/releases");
        // by the entries themselves: the day chips above them link to every release too
        int newest = html.IndexOf("id=\"r-2026.10.15-2\"", StringComparison.Ordinal), older = html.IndexOf("id=\"r-2026.10.14\"", StringComparison.Ordinal);
        Assert.True(newest >= 0 && older > newest, "the newest update comes first");
        Assert.Contains("2026.10.15.2", html);   // shown by its version, not its id
        Assert.Contains("walls-ru-2", html);
        Assert.Contains("floors-ru-1", html);
        Assert.Contains("id=\"r-2026.10.13\"", html);   // an update without a text is still in the list
    }

    [Fact]
    public async Task The_entrance_screen_names_the_game_with_the_piratez_version_of_the_release()
    {
        var html = await f.CreateClient().GetStringAsync("/");
        Assert.Contains("<div class=\"v\">o9</div>", html);               // "v.o9" of the manifest, as players say it
        Assert.Contains("OpenXcom Extended 8.7.1 + HD", System.Net.WebUtility.HtmlDecode(html));   // the engine: from the settings
        Assert.Contains("2026.10.15.2", html);                              // the latest release
        Assert.DoesNotContain("<div class=\"v\">o2</div>", html);          // not the fallback of the settings
    }

    [Fact]
    public async Task The_roadmap_page_shows_the_plan_from_the_history_as_markup()
    {
        var html = await f.CreateClient().GetStringAsync("/roadmap");
        Assert.Contains(">Plan-ru</h2>", html);
        Assert.Contains("<li>inventory-next</li>", html);
        Assert.Contains("href=\"/releases\"", html);
    }
}
