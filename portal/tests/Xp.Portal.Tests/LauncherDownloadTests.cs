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
}
