using System.Net;
using System.Net.Http.Json;
using System.Text;
using System.Text.RegularExpressions;
using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.DependencyInjection;
using Xp.Portal.Data;
using Xp.Portal.Devices;
using Xp.Portal.Site;

namespace Xp.Portal.Tests;

/// <summary>
/// A new player comes from the launcher with a link code and no account. The code has to survive
/// registration, the letter, the confirmation and the first sign-in, and end on the page that links the
/// launcher. Letters are read the way the server writes them without SMTP: .eml files in a folder.
/// </summary>
public sealed partial class RegistrationTests(PortalFactory f) : IClassFixture<PortalFactory>
{
    const string Password = "Long-enough-passw0rd!";

    HttpClient Browser() => f.CreateClient(new WebApplicationFactoryClientOptions { AllowAutoRedirect = false, HandleCookies = true });

    [GeneratedRegex("name=\"__RequestVerificationToken\" type=\"hidden\" value=\"([^\"]+)\"")]
    private static partial Regex AntiforgeryRx();

    [GeneratedRegex("name=\"ReturnUrl\" value=\"([^\"]*)\"")]
    private static partial Regex ReturnFieldRx();

    [GeneratedRegex("https://portal\\.test(/account/confirm\\?\\S+)")]
    private static partial Regex ConfirmLinkRx();

    static async Task<HttpResponseMessage> PostForm(HttpClient c, string url, Dictionary<string, string> fields, string? tokenFrom = null)
    {
        var html = await c.GetStringAsync(tokenFrom ?? url);
        fields["__RequestVerificationToken"] = AntiforgeryRx().Match(html) is { Success: true } m
            ? m.Groups[1].Value : throw new Xunit.Sdk.XunitException("no antiforgery token on " + (tokenFrom ?? url));
        return await c.PostAsync(url, new FormUrlEncodedContent(fields));
    }

    /// <summary>What a browser would send back from the hidden field of the page.</summary>
    static string ReturnField(string html) =>
        ReturnFieldRx().Match(html) is { Success: true } m ? WebUtility.HtmlDecode(m.Groups[1].Value) : "";

    /// <summary>A link in the page itself; the header above the title has plain sign-in and register links of its own.</summary>
    static string Href(string html, string startsWith)
    {
        var page = html[html.IndexOf("<h1", StringComparison.Ordinal)..];
        var m = Regex.Match(page, "href=\"(" + Regex.Escape(startsWith) + "[^\"]*)\"");
        Assert.True(m.Success, "no link to " + startsWith);
        return WebUtility.HtmlDecode(m.Groups[1].Value);
    }

    static string Where(HttpResponseMessage r) => r.Headers.Location is { } l ? (l.IsAbsoluteUri ? l.PathAndQuery : l.OriginalString) : "";

    static string Fresh() => $"new-{Guid.NewGuid():N}@x.test";

    /// <summary>Every letter the site wrote to this address, decoded.</summary>
    public static List<string> Letters(PortalFactory f, string to)
    {
        var dir = Path.Combine(f.Storage, "mail");
        var found = new List<string>();
        if (!Directory.Exists(dir)) return found;
        foreach (var file in Directory.GetFiles(dir, "*.eml"))
        {
            var raw = File.ReadAllText(file);
            var split = raw.IndexOf("\r\n\r\n", StringComparison.Ordinal);
            var head = raw[..split];
            var body = raw[(split + 4)..];
            if (!Regex.IsMatch(head, "^To: .*" + Regex.Escape(to), RegexOptions.Multiline | RegexOptions.IgnoreCase)) continue;
            if (head.Contains("Content-Transfer-Encoding: base64", StringComparison.OrdinalIgnoreCase))
                body = Encoding.UTF8.GetString(Convert.FromBase64String(Regex.Replace(body, "\\s", "")));
            else if (head.Contains("Content-Transfer-Encoding: quoted-printable", StringComparison.OrdinalIgnoreCase))
                body = QuotedPrintable(body);
            found.Add(body);
        }
        return found;
    }

    static string QuotedPrintable(string s)
    {
        s = s.Replace("=\r\n", "");
        var bytes = new List<byte>();
        for (var i = 0; i < s.Length; i++)
        {
            if (s[i] == '=' && i + 2 < s.Length) { bytes.Add(Convert.ToByte(s.Substring(i + 1, 2), 16)); i += 2; }
            else bytes.AddRange(Encoding.UTF8.GetBytes(s[i].ToString()));
        }
        return Encoding.UTF8.GetString(bytes.ToArray());
    }

    static string ConfirmLink(string letter) =>
        ConfirmLinkRx().Match(letter) is { Success: true } m ? m.Groups[1].Value : throw new Xunit.Sdk.XunitException("no confirmation link in the letter");

    async Task<HttpResponseMessage> RegisterAsync(HttpClient c, string url, string email, string name = "Новичок")
    {
        var page = await c.GetStringAsync(url);
        return await PostForm(c, url, new()
        {
            ["Email"] = email, ["DisplayName"] = name, ["Password"] = Password, ["ReturnUrl"] = ReturnField(page),
        });
    }

    async Task<HttpResponseMessage> SignInAsync(HttpClient c, string url, string email)
    {
        var page = await c.GetStringAsync(url);
        return await PostForm(c, url, new() { ["Email"] = email, ["Password"] = Password, ["ReturnUrl"] = ReturnField(page) });
    }

    [Fact]
    public async Task A_player_from_the_launcher_registers_confirms_signs_in_and_links_it_without_retyping_the_code()
    {
        var launcher = f.CreateClient();
        var linkResponse = await launcher.PostAsJsonAsync("/api/v1/devices/link", new LinkRequest("Лаунчер 0.3.6"));
        Assert.Equal(HttpStatusCode.Created, linkResponse.StatusCode);
        var link = (await linkResponse.Content.ReadFromJsonAsync<LinkResponse>())!;
        var target = "/me/devices?code=" + Uri.EscapeDataString(link.Code);
        var kept = Uri.EscapeDataString(target);

        // the launcher opens the device page; no account yet, so the site asks to sign in
        var browser = Browser();
        var first = await browser.GetAsync(target);
        Assert.Equal(HttpStatusCode.Redirect, first.StatusCode);
        var login = Where(first);
        Assert.StartsWith("/account/login", login);

        // the sign-in page sends to registration with the same destination
        var register = Href(await browser.GetStringAsync(login), "/account/register");
        Assert.Equal("/account/register?returnUrl=" + kept, register);

        var email = Fresh();
        var registered = await RegisterAsync(browser, register, email, "Новичок");
        Assert.Equal(HttpStatusCode.OK, registered.StatusCode);
        Assert.Contains("/account/resend?returnUrl=" + kept, WebUtility.HtmlDecode(await registered.Content.ReadAsStringAsync()));

        // before the letter is opened, signing in says so and offers another letter, still with the destination
        var early = await SignInAsync(browser, login, email);
        Assert.Equal(HttpStatusCode.OK, early.StatusCode);
        Assert.Equal("/account/resend?returnUrl=" + kept, Href(await early.Content.ReadAsStringAsync(), "/account/resend"));

        var letters = Letters(f, email);
        Assert.Single(letters);
        var confirm = ConfirmLink(letters[0]);
        Assert.EndsWith("&returnUrl=" + kept, confirm);

        var confirmed = await browser.GetAsync(confirm);
        Assert.Equal(HttpStatusCode.OK, confirmed.StatusCode);
        var signIn = Href(await confirmed.Content.ReadAsStringAsync(), "/account/login");
        Assert.Equal("/account/login?ReturnUrl=" + kept, signIn);

        var signedIn = await SignInAsync(browser, signIn, email);
        Assert.Equal(HttpStatusCode.Redirect, signedIn.StatusCode);
        Assert.Equal(target, Where(signedIn));

        // the device page already holds the code; the person only presses the button
        Assert.Contains(link.Code, await browser.GetStringAsync(target));
        var linked = await PostForm(browser, "/me/devices?handler=Confirm", new() { ["code"] = link.Code }, target);
        Assert.Equal(HttpStatusCode.Redirect, linked.StatusCode);

        var status = (await launcher.GetFromJsonAsync<LinkStatusResponse>($"/api/v1/devices/{link.DeviceId}"))!;
        Assert.Equal("linked", status.Status);
        Assert.Equal("Новичок", status.Account);
        Assert.False(string.IsNullOrEmpty(status.Token));
    }

    [Fact]
    public async Task Another_letter_goes_only_to_an_unconfirmed_address_and_not_twice_in_a_row()
    {
        var browser = Browser();
        var email = Fresh();
        Assert.Equal(HttpStatusCode.OK, (await RegisterAsync(browser, "/account/register", email)).StatusCode);
        Assert.Single(Letters(f, email));

        var again = await PostForm(browser, "/account/resend", new() { ["Email"] = email, ["ReturnUrl"] = "" });
        Assert.Equal(HttpStatusCode.OK, again.StatusCode);
        Assert.Equal(2, Letters(f, email).Count);

        // a second ask right away is answered the same and sends nothing
        var flood = await PostForm(browser, "/account/resend", new() { ["Email"] = email, ["ReturnUrl"] = "" });
        Assert.Equal(HttpStatusCode.OK, flood.StatusCode);
        Assert.Equal(2, Letters(f, email).Count);

        // both letters work until one is used: the newest one confirms
        var newest = ConfirmLink(Letters(f, email)[^1]);
        Assert.Equal(HttpStatusCode.OK, (await browser.GetAsync(newest)).StatusCode);

        // a confirmed address and an unknown one get the very same answer, and no letter
        var done = Fresh();
        await f.ScopedAsync(async sp =>
        {
            var users = sp.GetRequiredService<UserManager<PortalUser>>();
            var r = await users.CreateAsync(new PortalUser { UserName = done, Email = done, EmailConfirmed = true, DisplayName = "Старожил" }, Password);
            Assert.True(r.Succeeded);
            return 0;
        });
        var known = await PostForm(Browser(), "/account/resend", new() { ["Email"] = done, ["ReturnUrl"] = "" });
        var unknown = await PostForm(Browser(), "/account/resend", new() { ["Email"] = Fresh(), ["ReturnUrl"] = "" });
        Assert.Empty(Letters(f, done));
        Assert.Equal(AntiforgeryRx().Replace(await unknown.Content.ReadAsStringAsync(), ""),
            AntiforgeryRx().Replace(await known.Content.ReadAsStringAsync(), ""));
    }

    [Theory]
    [InlineData("https://evil.test/me/devices")]
    [InlineData("//evil.test/me/devices")]
    [InlineData("/\\evil.test/me/devices")]
    public async Task A_destination_off_the_site_is_dropped_on_every_step(string evil)
    {
        var escaped = Uri.EscapeDataString(evil);
        var browser = Browser();
        Assert.Equal("", ReturnField(await browser.GetStringAsync("/account/register?returnUrl=" + escaped)));
        Assert.Equal("/account/register", Href(await browser.GetStringAsync("/account/login?ReturnUrl=" + escaped), "/account/register"));

        // even posted straight past the page, it does not reach the letter
        var email = Fresh();
        Assert.Equal(HttpStatusCode.OK, (await PostForm(browser, "/account/register", new()
        {
            ["Email"] = email, ["DisplayName"] = "Гость", ["Password"] = Password, ["ReturnUrl"] = evil,
        })).StatusCode);
        var confirm = ConfirmLink(Assert.Single(Letters(f, email)));
        Assert.DoesNotContain("returnUrl", confirm);
        Assert.DoesNotContain("evil", confirm);

        var page = await (await browser.GetAsync(confirm + "&returnUrl=" + escaped)).Content.ReadAsStringAsync();
        Assert.Equal("/account/login", Href(page, "/account/login"));
    }
}

/// <summary>The mail server is down: the pages still answer, and the server-side check says why.</summary>
public sealed class MailDownFactory : PortalFactory
{
    public MailDownFactory()
    {
        // nothing listens on port 1: the connection is refused at once
        Settings["Email:SmtpHost"] = "127.0.0.1";
        Settings["Email:SmtpPort"] = "1";
    }
}

public sealed partial class MailDownTests(MailDownFactory f) : IClassFixture<MailDownFactory>
{
    [GeneratedRegex("name=\"__RequestVerificationToken\" type=\"hidden\" value=\"([^\"]+)\"")]
    private static partial Regex AntiforgeryRx();

    async Task<HttpResponseMessage> PostForm(string url, Dictionary<string, string> fields)
    {
        var c = f.CreateClient(new WebApplicationFactoryClientOptions { AllowAutoRedirect = false, HandleCookies = true });
        fields["__RequestVerificationToken"] = AntiforgeryRx().Match(await c.GetStringAsync(url)).Groups[1].Value;
        return await c.PostAsync(url, new FormUrlEncodedContent(fields));
    }

    [Fact]
    public async Task Registration_and_the_letters_after_it_answer_normally_when_the_mail_server_is_down()
    {
        var email = $"down-{Guid.NewGuid():N}@x.test";
        var r = await PostForm("/account/register", new() { ["Email"] = email, ["DisplayName"] = "Терпеливый", ["Password"] = "Long-enough-passw0rd!" });
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await PostForm("/account/resend", new() { ["Email"] = email })).StatusCode);

        // the account exists; the person asks for another letter once the mail is back
        var exists = await f.ScopedAsync(async sp => await sp.GetRequiredService<UserManager<PortalUser>>().FindByEmailAsync(email) is not null);
        Assert.True(exists);

        var mail = (EmailSender)f.Services.GetRequiredService<IEmailSender<PortalUser>>();
        await Assert.ThrowsAsync<System.Net.Mail.SmtpException>(() => mail.SendTestAsync("admin@x.test"));
    }
}
