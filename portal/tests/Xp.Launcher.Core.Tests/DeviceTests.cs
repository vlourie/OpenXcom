using System.Net;
using System.Text;
using System.Text.Json;

namespace Xp.Launcher.Core.Tests;

/// <summary>A fake site that links devices: it answers "pending" until somebody confirms the code.</summary>
public sealed class FakeDevices : HttpMessageHandler
{
    public bool Offline;
    public string? Confirmed;                 // the account name, once a person said yes on the site
    public bool Expired;
    public string Token = "device-token-0123456789";
    public readonly List<string> Names = new();
    public readonly HashSet<string> Revoked = new();
    /// <summary>The token is handed out once, the way the portal does it.</summary>
    public bool TokenTaken;

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage req, CancellationToken ct)
    {
        if (Offline) throw new HttpRequestException("no route to host");
        var path = req.RequestUri!.AbsolutePath;
        if (req.Method == HttpMethod.Post && path == "/api/v1/devices/link")
        {
            var body = JsonDocument.Parse(await req.Content!.ReadAsStringAsync(ct)).RootElement;
            Names.Add(body.GetProperty("name").GetString()!);
            return Json(HttpStatusCode.Created, """{"code":"K7P-Q42","deviceId":"11111111-1111-1111-1111-111111111111","expiresIn":600}""");
        }
        if (req.Method == HttpMethod.Get && path.StartsWith("/api/v1/devices/1111"))
        {
            if (Expired) return Json(HttpStatusCode.OK, """{"status":"expired","token":null,"account":null}""");
            if (Confirmed is null) return Json(HttpStatusCode.OK, """{"status":"pending","token":null,"account":null}""");
            var token = TokenTaken ? "null" : $"\"{Token}\"";
            TokenTaken = true;
            return Json(HttpStatusCode.OK, $$"""{"status":"linked","token":{{token}},"account":"{{Confirmed}}"}""");
        }
        var given = req.Headers.TryGetValues("X-Device-Token", out var v) ? v.Single() : null;
        bool known = given == Token && !Revoked.Contains(given);
        if (path == "/api/v1/devices/me" && req.Method == HttpMethod.Get)
            return known
                ? Json(HttpStatusCode.OK, $$"""{"account":"{{Confirmed}}","name":"{{Names[^1]}}","linkedAt":"2026-09-24T10:00:00Z"}""")
                : Json(HttpStatusCode.Unauthorized, """{"code":"device_unknown","detail":"no"}""");
        if (path == "/api/v1/devices/me" && req.Method == HttpMethod.Delete)
        {
            if (!known) return Json(HttpStatusCode.Unauthorized, """{"code":"device_unknown","detail":"no"}""");
            Revoked.Add(given!);
            return new HttpResponseMessage(HttpStatusCode.NoContent);
        }
        return new HttpResponseMessage(HttpStatusCode.NotFound);
    }

    static HttpResponseMessage Json(HttpStatusCode code, string body) =>
        new(code) { Content = new StringContent(body, Encoding.UTF8, "application/json") };
}

public sealed class DeviceTests : IDisposable
{
    readonly string _root = Path.Combine(Path.GetTempPath(), "xp-tests", Guid.NewGuid().ToString("N"));
    readonly FakeDevices _site = new();

    PortalClient Client() => new(new HttpClient(_site), new Uri("https://p.test/"));
    DeviceStore Store() => new(Path.Combine(_root, "device.json"));

    public void Dispose()
    {
        try { Directory.Delete(_root, true); } catch (IOException) { }
    }

    [Fact]
    public async Task The_token_comes_only_after_somebody_confirms_the_code()
    {
        var client = Client();
        var start = await client.StartLinkAsync("Лаунчер 0.1.1", default);
        Assert.Equal("K7P-Q42", start.Code);
        Assert.Equal(600, start.ExpiresIn);
        Assert.Equal("Лаунчер 0.1.1", _site.Names.Single());

        Assert.Equal("pending", (await client.LinkStatusAsync(start.DeviceId, default)).Status);

        _site.Confirmed = "Мария";
        var linked = await client.LinkStatusAsync(start.DeviceId, default);
        Assert.Equal("linked", linked.Status);
        Assert.Equal("Мария", linked.Account);
        Assert.Equal(_site.Token, linked.Token);

        // asking again says linked and nothing more: the secret is not kept anywhere to be given twice
        Assert.Null((await client.LinkStatusAsync(start.DeviceId, default)).Token);
    }

    [Fact]
    public async Task A_code_nobody_confirmed_runs_out()
    {
        var client = Client();
        var start = await client.StartLinkAsync("Лаунчер", default);
        _site.Expired = true;
        Assert.Equal("expired", (await client.LinkStatusAsync(start.DeviceId, default)).Status);
    }

    [Fact]
    public async Task The_site_says_who_we_are_until_the_link_is_taken_away()
    {
        _site.Confirmed = "Витали";
        var client = Client();
        var start = await client.StartLinkAsync("Лаунчер 0.1.1", default);
        var token = (await client.LinkStatusAsync(start.DeviceId, default)).Token!;

        var me = await client.WhoAmIAsync(token, default);
        Assert.Equal("Витали", me!.Account);
        Assert.Equal("Лаунчер 0.1.1", me.Name);

        await client.ForgetAsync(token, default);
        Assert.Null(await client.WhoAmIAsync(token, default));
        // a key the site has already forgotten is not an error to give back again
        await client.ForgetAsync(token, default);
    }

    [Fact]
    public async Task An_unknown_key_is_nobody()
    {
        Assert.Null(await Client().WhoAmIAsync("not-a-real-token", default));
    }

    [Fact]
    public void The_key_is_kept_apart_from_the_settings_and_comes_back_whole()
    {
        var store = Store();
        Assert.Null(store.Load());
        store.Save(new DeviceAccount { Token = "k", Account = "Мария", Name = "Лаунчер 0.1.1", LinkedAt = DateTimeOffset.UtcNow });

        Assert.EndsWith("device.json", store.Path);
        Assert.DoesNotContain("settings.json", store.Path);
        var back = Store().Load()!;
        Assert.Equal("k", back.Token);
        Assert.Equal("Мария", back.Account);

        store.Clear();
        Assert.Null(Store().Load());
        // clearing what is not there is the same as clearing: unlinking must work twice
        store.Clear();
    }

    [Fact]
    public void A_damaged_key_file_is_no_key()
    {
        Directory.CreateDirectory(_root);
        File.WriteAllText(Path.Combine(_root, "device.json"), "{ this is not json");
        Assert.Null(Store().Load());
        File.WriteAllText(Path.Combine(_root, "device.json"), """{"account":"Мария"}""");
        Assert.Null(Store().Load());
    }

    [Fact]
    public async Task A_site_that_does_not_answer_is_not_a_refusal()
    {
        _site.Offline = true;
        await Assert.ThrowsAsync<HttpRequestException>(() => Client().StartLinkAsync("Лаунчер", default));
    }
}
