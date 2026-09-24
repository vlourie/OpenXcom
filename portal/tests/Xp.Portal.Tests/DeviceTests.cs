using System.Net;
using System.Net.Http.Json;
using System.Text.RegularExpressions;
using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Xp.Portal.Auth;
using Xp.Portal.Data;
using Xp.Portal.Devices;

namespace Xp.Portal.Tests;

/// <summary>
/// Linking a launcher to an account: the launcher asks for a code, a person confirms it on the site,
/// and only then does a token exist. Nothing here ever carries a password.
/// </summary>
public sealed partial class DeviceTests(PortalFactory f) : IClassFixture<PortalFactory>
{
    const string Password = "Long-enough-passw0rd!";

    HttpClient Browser() => f.CreateClient(new WebApplicationFactoryClientOptions { AllowAutoRedirect = false, HandleCookies = true });

    [GeneratedRegex("name=\"__RequestVerificationToken\" type=\"hidden\" value=\"([^\"]+)\"")]
    private static partial Regex AntiforgeryRx();

    static async Task<HttpResponseMessage> PostForm(HttpClient c, string url, Dictionary<string, string> fields, string? tokenFrom = null)
    {
        var html = await c.GetStringAsync(tokenFrom ?? url);
        fields["__RequestVerificationToken"] = AntiforgeryRx().Match(html) is { Success: true } m
            ? m.Groups[1].Value : throw new Xunit.Sdk.XunitException("no antiforgery token on " + (tokenFrom ?? url));
        return await c.PostAsync(url, new FormUrlEncodedContent(fields));
    }

    /// <summary>A signed-in person with a name of their own, the way the launcher will see it.</summary>
    async Task<(HttpClient Browser, string Name)> PersonAsync(string name)
    {
        // the address is plain ASCII on purpose: a user name may hold only the characters Identity allows
        var email = $"person-{Guid.NewGuid():N}@x.test";
        await f.ScopedAsync(async sp =>
        {
            var users = sp.GetRequiredService<UserManager<PortalUser>>();
            var u = new PortalUser { UserName = email, Email = email, EmailConfirmed = true, DisplayName = name };
            var r = await users.CreateAsync(u, Password);
            Assert.True(r.Succeeded, string.Join(", ", r.Errors.Select(e => e.Description)));
            return u.Id;
        });
        var c = Browser();
        var r = await PostForm(c, "/account/login", new() { ["Email"] = email, ["Password"] = Password });
        Assert.Equal(HttpStatusCode.Redirect, r.StatusCode);
        return (c, name);
    }

    // the page handler is named in the query string; the antiforgery token is taken from the page itself
    static Task<HttpResponseMessage> Confirm(HttpClient c, string code) =>
        PostForm(c, "/me/devices?handler=Confirm", new() { ["code"] = code }, "/me/devices");

    static Task<HttpResponseMessage> Revoke(HttpClient c, Guid id) =>
        PostForm(c, "/me/devices?handler=Revoke", new() { ["id"] = id.ToString() }, "/me/devices");

    /// <summary>The launcher's side: a bare client with no cookies at all.</summary>
    HttpClient Launcher() => f.CreateClient();

    async Task<LinkResponse> AskForCodeAsync(HttpClient launcher, string name = "Лаунчер 0.1.1")
    {
        var r = await launcher.PostAsJsonAsync("/api/v1/devices/link", new LinkRequest(name));
        Assert.Equal(HttpStatusCode.Created, r.StatusCode);
        return (await r.Content.ReadFromJsonAsync<LinkResponse>())!;
    }

    async Task<LinkStatusResponse> StatusAsync(HttpClient launcher, Guid deviceId)
    {
        var r = await launcher.GetAsync($"/api/v1/devices/{deviceId}");
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        return (await r.Content.ReadFromJsonAsync<LinkStatusResponse>())!;
    }

    /// <summary>The token a link ended up issuing. Looked up by the device, never by the launcher name: the tests share one.</summary>
    Task<Guid> TokenIdAsync(Guid deviceId) =>
        f.DbAsync(db => db.DeviceLinkCodes.Where(c => c.DeviceId == deviceId).Select(c => c.IssuedTokenId!.Value).FirstAsync());

    static HttpRequestMessage WithToken(HttpMethod method, string url, string token)
    {
        var msg = new HttpRequestMessage(method, url);
        msg.Headers.Add(DeviceApi.TokenHeader, token);
        return msg;
    }

    [Fact]
    public async Task A_launcher_gets_its_token_only_after_a_person_confirms_the_code()
    {
        var launcher = Launcher();
        var link = await AskForCodeAsync(launcher);
        Assert.Matches("^[A-Z2-9]{3}-[A-Z2-9]{3}$", link.Code);
        Assert.Equal(600, link.ExpiresIn);

        var before = await StatusAsync(launcher, link.DeviceId);
        Assert.Equal("pending", before.Status);
        Assert.Null(before.Token);

        var (browser, name) = await PersonAsync("Мария");
        var confirm = await Confirm(browser, link.Code);
        Assert.Equal(HttpStatusCode.Redirect, confirm.StatusCode);

        var after = await StatusAsync(launcher, link.DeviceId);
        Assert.Equal("linked", after.Status);
        Assert.Equal(name, after.Account);
        Assert.False(string.IsNullOrEmpty(after.Token));

        // the token is handed out once: asking again says linked and nothing more
        var again = await StatusAsync(launcher, link.DeviceId);
        Assert.Equal("linked", again.Status);
        Assert.Null(again.Token);

        // only the hash is kept, never the secret itself
        var stored = await f.DbAsync(db => db.DeviceTokens.Select(d => d.TokenHash).ToListAsync());
        Assert.Contains(DeviceSecrets.Hash(after.Token!), stored);
        Assert.DoesNotContain(after.Token!, stored);
    }

    [Fact]
    public async Task The_token_names_the_account_until_the_person_takes_it_away()
    {
        var launcher = Launcher();
        var link = await AskForCodeAsync(launcher, "Лаунчер 0.1.1");
        var (browser, name) = await PersonAsync("Витали");
        await Confirm(browser, link.Code);
        var token = (await StatusAsync(launcher, link.DeviceId)).Token!;

        var me = await launcher.SendAsync(WithToken(HttpMethod.Get, "/api/v1/devices/me", token));
        Assert.Equal(HttpStatusCode.OK, me.StatusCode);
        var view = (await me.Content.ReadFromJsonAsync<DeviceResponse>())!;
        Assert.Equal(name, view.Account);
        Assert.Equal("Лаунчер 0.1.1", view.Name);

        var page = await browser.GetStringAsync("/me/devices");
        Assert.Contains("Лаунчер 0.1.1", page);
        var id = await TokenIdAsync(link.DeviceId);
        var revoked = await Revoke(browser, id);
        Assert.Equal(HttpStatusCode.Redirect, revoked.StatusCode);

        var after = await launcher.SendAsync(WithToken(HttpMethod.Get, "/api/v1/devices/me", token));
        Assert.Equal(HttpStatusCode.Unauthorized, after.StatusCode);
    }

    [Fact]
    public async Task Somebody_elses_launcher_is_not_theirs_to_unlink()
    {
        var launcher = Launcher();
        var link = await AskForCodeAsync(launcher, "Лаунчер хозяина");
        var (owner, _) = await PersonAsync("Хозяин");
        await Confirm(owner, link.Code);
        var token = (await StatusAsync(launcher, link.DeviceId)).Token!;
        var id = await TokenIdAsync(link.DeviceId);

        var (stranger, _) = await PersonAsync("Чужой");
        Assert.DoesNotContain("Лаунчер хозяина", await stranger.GetStringAsync("/me/devices"));
        await Revoke(stranger, id);

        var still = await launcher.SendAsync(WithToken(HttpMethod.Get, "/api/v1/devices/me", token));
        Assert.Equal(HttpStatusCode.OK, still.StatusCode);
    }

    [Fact]
    public async Task The_launcher_can_forget_itself()
    {
        var launcher = Launcher();
        var link = await AskForCodeAsync(launcher);
        var (browser, _) = await PersonAsync("Забывчивый");
        await Confirm(browser, link.Code);
        var token = (await StatusAsync(launcher, link.DeviceId)).Token!;

        var gone = await launcher.SendAsync(WithToken(HttpMethod.Delete, "/api/v1/devices/me", token));
        Assert.Equal(HttpStatusCode.NoContent, gone.StatusCode);
        var after = await launcher.SendAsync(WithToken(HttpMethod.Get, "/api/v1/devices/me", token));
        Assert.Equal(HttpStatusCode.Unauthorized, after.StatusCode);
    }

    [Fact]
    public async Task A_code_that_waited_too_long_confirms_nobody()
    {
        var launcher = Launcher();
        var link = await AskForCodeAsync(launcher);
        f.Clock.Advance(TimeSpan.FromMinutes(11));

        Assert.Equal("expired", (await StatusAsync(launcher, link.DeviceId)).Status);

        var (browser, _) = await PersonAsync("Опоздавший");
        var r = await Confirm(browser, link.Code);
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);   // the page comes back with the reason, not a redirect
        Assert.Contains("истёк", await r.Content.ReadAsStringAsync());
        Assert.Equal("expired", (await StatusAsync(launcher, link.DeviceId)).Status);
    }

    [Fact]
    public async Task The_code_is_read_however_a_person_typed_it()
    {
        Assert.Equal("K7PQ42", DeviceSecrets.Normalize("k7p-q42"));
        Assert.Equal("K7PQ42", DeviceSecrets.Normalize(" K7P Q42 "));
        Assert.Null(DeviceSecrets.Normalize("K7P-Q4"));          // too short
        Assert.Null(DeviceSecrets.Normalize("K7P-Q420"));        // too long
        Assert.Null(DeviceSecrets.Normalize("K7P-Q4O"));         // O is not in the alphabet, so it cannot be mistyped for 0
        Assert.Equal("ABC-DEF", DeviceSecrets.Format("ABCDEF"));

        var launcher = Launcher();
        var link = await AskForCodeAsync(launcher);
        var (browser, _) = await PersonAsync("Торопливый");
        var typed = link.Code.Replace("-", "").ToLowerInvariant();
        var r = await Confirm(browser, typed);
        Assert.Equal(HttpStatusCode.Redirect, r.StatusCode);
        Assert.Equal("linked", (await StatusAsync(launcher, link.DeviceId)).Status);
    }

    [Fact]
    public async Task The_page_asks_about_the_code_the_launcher_opened_it_with()
    {
        var launcher = Launcher();
        var link = await AskForCodeAsync(launcher);
        var (browser, _) = await PersonAsync("Пришедший");
        var html = await browser.GetStringAsync($"/me/devices?code={link.Code}");
        Assert.Contains(link.Code, html);
        Assert.Contains("Привязать лаунчер?", html);

        // an unknown code is not announced as unknown: the page simply offers the plain form
        var blank = await browser.GetStringAsync("/me/devices?code=ZZZ-ZZZ");
        Assert.DoesNotContain("Привязать лаунчер?", blank);
    }

    [Fact]
    public async Task An_unknown_device_gets_nothing()
    {
        var launcher = Launcher();
        Assert.Equal(HttpStatusCode.NotFound, (await launcher.GetAsync($"/api/v1/devices/{Guid.NewGuid()}")).StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, (await launcher.SendAsync(WithToken(HttpMethod.Get, "/api/v1/devices/me", "not-a-real-token"))).StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, (await launcher.GetAsync("/api/v1/devices/me")).StatusCode);
    }
}
