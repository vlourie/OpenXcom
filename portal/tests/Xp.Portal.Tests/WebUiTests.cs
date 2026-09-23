using System.Net;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Xp.Portal.Auth;
using Xp.Portal.Data;
using Xp.Portal.Files;
using Xp.Portal.Tickets;

namespace Xp.Portal.Tests;

/// <summary>The site as a browser sees it: cookies, antiforgery, redirects, the second factor.</summary>
public sealed partial class WebUiTests(PortalFactory f) : IClassFixture<PortalFactory>
{
    const string Password = "Long-enough-passw0rd!";

    HttpClient Browser() => f.CreateClient(new WebApplicationFactoryClientOptions { AllowAutoRedirect = false, HandleCookies = true });

    [GeneratedRegex("name=\"__RequestVerificationToken\" type=\"hidden\" value=\"([^\"]+)\"")]
    private static partial Regex AntiforgeryRx();

    static async Task<string> TokenFrom(HttpClient c, string url)
    {
        var html = await c.GetStringAsync(url);
        return AntiforgeryRx().Match(html) is { Success: true } m ? m.Groups[1].Value : throw new Xunit.Sdk.XunitException("no antiforgery token on " + url);
    }

    static async Task<HttpResponseMessage> PostForm(HttpClient c, string url, Dictionary<string, string> fields, string? tokenFrom = null)
    {
        fields["__RequestVerificationToken"] = await TokenFrom(c, tokenFrom ?? url);
        return await c.PostAsync(url, new FormUrlEncodedContent(fields));
    }

    // ---- users ----

    sealed record Staff(string Email, string Key);

    async Task<Staff> MakeUserAsync(string role, bool twoFactor, params string[] perms)
    {
        var email = $"{role.ToLowerInvariant()}-{Guid.NewGuid():N}@x.test";
        var key = await f.ScopedAsync(async sp =>
        {
            var users = sp.GetRequiredService<UserManager<PortalUser>>();
            var u = new PortalUser { UserName = email, Email = email, EmailConfirmed = true, DisplayName = role };
            Assert.True((await users.CreateAsync(u, Password)).Succeeded);
            await users.AddToRoleAsync(u, role);
            var db = sp.GetRequiredService<PortalDb>();
            foreach (var p in perms) db.UserPermissions.Add(new UserPermission { UserId = u.Id, Permission = p });
            await db.SaveChangesAsync();
            if (!twoFactor) return "";
            await users.ResetAuthenticatorKeyAsync(u);
            await users.SetTwoFactorEnabledAsync(u, true);
            return (await users.GetAuthenticatorKeyAsync(u))!;
        });
        return new Staff(email, key);
    }

    /// <summary>A TOTP code the server accepts: tried against real time and the test clock.</summary>
    async Task<string> CodeAsync(Staff s)
    {
        foreach (var now in new[] { DateTimeOffset.UtcNow, f.Clock.GetUtcNow() })
        {
            var code = Totp(s.Key, now);
            var ok = await f.ScopedAsync(async sp =>
            {
                var users = sp.GetRequiredService<UserManager<PortalUser>>();
                var u = await users.FindByEmailAsync(s.Email);
                return await users.VerifyTwoFactorTokenAsync(u!, users.Options.Tokens.AuthenticatorTokenProvider, code);
            });
            if (ok) return code;
        }
        throw new Xunit.Sdk.XunitException("no TOTP code accepted");
    }

    static string Totp(string base32, DateTimeOffset at)
    {
        var bits = string.Concat(base32.TrimEnd('=').ToUpperInvariant().Select(ch => Convert.ToString("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567".IndexOf(ch), 2).PadLeft(5, '0')));
        var key = Enumerable.Range(0, bits.Length / 8).Select(i => Convert.ToByte(bits.Substring(i * 8, 8), 2)).ToArray();
        var counter = BitConverter.GetBytes(at.ToUnixTimeSeconds() / 30);
        if (BitConverter.IsLittleEndian) Array.Reverse(counter);
        var h = HMACSHA1.HashData(key, counter);
        var o = h[^1] & 0xf;
        var bin = ((h[o] & 0x7f) << 24) | (h[o + 1] << 16) | (h[o + 2] << 8) | h[o + 3];
        return (bin % 1_000_000).ToString("D6");
    }

    async Task<HttpClient> SignInAsync(Staff s, bool withSecondFactor = true)
    {
        var c = Browser();
        var r = await PostForm(c, "/account/login", new() { ["Email"] = s.Email, ["Password"] = Password });
        Assert.Equal(HttpStatusCode.Redirect, r.StatusCode);
        if (s.Key.Length == 0) return c;
        Assert.StartsWith("/account/login2fa", r.Headers.Location!.OriginalString);
        if (!withSecondFactor) return c;
        var loc = r.Headers.Location!.OriginalString;
        r = await PostForm(c, loc, new() { ["Code"] = await CodeAsync(s) });
        Assert.Equal(HttpStatusCode.Redirect, r.StatusCode);
        return c;
    }

    async Task<Ticket> NewTicketAsync(string category, string title = "t") => await f.ScopedAsync(async sp =>
        (await sp.GetRequiredService<TicketService>().CreateAsync(new NewTicket(category, title, "d"), null, null, null, default)).Ticket);

    // ---- guest ----

    [Fact]
    public async Task Pages_render_in_both_languages()
    {
        var c = Browser();
        foreach (var url in new[] { "/", "/tickets/new", "/account/login", "/account/register", "/account/forgot" })
        {
            var ru = await c.GetAsync(url);
            Assert.Equal(HttpStatusCode.OK, ru.StatusCode);
            var html = await ru.Content.ReadAsStringAsync();
            Assert.Contains("lang=\"ru\"", html);
            Assert.Contains("Сообщить о проблеме", html);   // plain text, not &#x...; entities
        }
        var en = await f.CreateClient().GetStringAsync("/tickets/new?culture=en&ui-culture=en");
        Assert.Contains("Report a problem", en);
    }

    [Fact]
    public async Task Guest_sends_the_form_and_gets_a_private_link()
    {
        var c = Browser();
        var r = await PostForm(c, "/tickets/new", new()
        {
            ["Form.Key"] = Guid.NewGuid().ToString("N"), ["Form.Category"] = "graphics",
            ["Form.Title"] = "<script>alert('x')</script> broken sprite", ["Form.Description"] = "<img src=x onerror=alert(1)>",
        });
        Assert.Equal(HttpStatusCode.Redirect, r.StatusCode);
        var link = r.Headers.Location!.OriginalString;
        Assert.Matches(@"^/t/\d+\?k=[A-Za-z0-9_-]{22}$", link);

        var page = await c.GetAsync(link);
        Assert.Equal(HttpStatusCode.OK, page.StatusCode);
        Assert.Contains("no-store", page.Headers.CacheControl!.ToString());
        var html = await page.Content.ReadAsStringAsync();
        Assert.Contains("&lt;script&gt;", html);
        Assert.DoesNotContain("<script>alert", html);
        Assert.DoesNotContain("<img src=x", html);
        Assert.Contains("&lt;img src=x onerror=alert(1)&gt;", html);

        var number = link[3..link.IndexOf('?')];
        Assert.Equal(HttpStatusCode.NotFound, (await Browser().GetAsync($"/t/{number}")).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await Browser().GetAsync($"/t/{number}?k=AAAAAAAAAAAAAAAAAAAAAA")).StatusCode);
    }

    [Fact]
    public async Task Double_submit_of_one_form_makes_one_ticket()
    {
        var c = Browser();
        var fields = new Dictionary<string, string> { ["Form.Key"] = Guid.NewGuid().ToString("N"), ["Form.Category"] = "code", ["Form.Title"] = "twice", ["Form.Description"] = "d" };
        var a = await PostForm(c, "/tickets/new", new(fields));
        var b = await PostForm(c, "/tickets/new", new(fields));
        Assert.Equal(a.Headers.Location, b.Headers.Location);
    }

    [Fact]
    public async Task Honeypot_filled_makes_no_ticket()
    {
        var before = await f.DbAsync(db => db.Tickets.CountAsync());
        var r = await PostForm(Browser(), "/tickets/new", new() { ["Form.Category"] = "code", ["Form.Title"] = "bot", ["Form.Description"] = "d", ["Form.Website"] = "http://spam" });
        Assert.Equal("/", r.Headers.Location!.OriginalString);
        Assert.Equal(before, await f.DbAsync(db => db.Tickets.CountAsync()));
    }

    [Fact]
    public async Task Post_without_antiforgery_is_refused()
    {
        var c = Browser();
        await c.GetAsync("/tickets/new");
        var r = await c.PostAsync("/tickets/new", new FormUrlEncodedContent(new Dictionary<string, string> { ["Form.Category"] = "code", ["Form.Title"] = "csrf", ["Form.Description"] = "d" }));
        Assert.Equal(HttpStatusCode.BadRequest, r.StatusCode);
    }

    [Fact]
    public async Task Language_switch_only_redirects_locally()
    {
        var r = await Browser().GetAsync("/lang/en?back=//evil.example/x");
        Assert.Equal("/", r.Headers.Location!.OriginalString);
        r = await Browser().GetAsync("/lang/en?back=/tickets/new");
        Assert.Equal("/tickets/new", r.Headers.Location!.OriginalString);
    }

    // ---- roles ----

    [Fact]
    public async Task Role_matrix_over_http()
    {
        var anon = Browser();
        Assert.StartsWith("/account/login", (await anon.GetAsync("/admin")).Headers.Location!.PathAndQuery());

        var user = await SignInAsync(await MakeUserAsync(Roles.User, false));
        Assert.StartsWith("/account/denied", (await user.GetAsync("/admin")).Headers.Location!.PathAndQuery());
        Assert.Equal(HttpStatusCode.OK, (await user.GetAsync("/me")).StatusCode);

        // an admin who signed in without the second factor is refused and told why
        var halfAdmin = await SignInAsync(await MakeUserAsync(Roles.Admin, false, "tickets.code"));
        var denied = await halfAdmin.GetAsync("/admin");
        Assert.StartsWith("/account/denied", denied.Headers.Location!.PathAndQuery());
        Assert.Contains("/me/security", await halfAdmin.GetStringAsync(denied.Headers.Location!.PathAndQuery()));

        var admin = await SignInAsync(await MakeUserAsync(Roles.Admin, true, "tickets.code"));
        Assert.Equal(HttpStatusCode.OK, (await admin.GetAsync("/admin")).StatusCode);
        Assert.StartsWith("/account/denied", (await admin.GetAsync("/admin/super/users")).Headers.Location!.PathAndQuery());

        var super = await SignInAsync(await MakeUserAsync(Roles.SuperAdmin, true));
        foreach (var p in new[] { "/admin", "/admin/super/users", "/admin/super/telegram", "/admin/super/audit" })
            Assert.Equal(HttpStatusCode.OK, (await super.GetAsync(p)).StatusCode);
    }

    [Fact]
    public async Task Code_admin_gets_404_on_a_graphics_ticket_and_never_sees_it_in_the_queue()
    {
        var art = await NewTicketAsync("graphics", "only-for-artists-" + Guid.NewGuid().ToString("N")[..6]);
        var code = await NewTicketAsync("code", "for-coders-" + Guid.NewGuid().ToString("N")[..6]);
        var admin = await SignInAsync(await MakeUserAsync(Roles.Admin, true, "tickets.code"));
        Assert.Equal(HttpStatusCode.NotFound, (await admin.GetAsync($"/admin/tickets/{art.Number}")).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await admin.GetAsync($"/admin/tickets/{code.Number}")).StatusCode);
        var queue = await admin.GetStringAsync("/admin?Status=all");
        Assert.Contains(code.Title, queue);
        Assert.DoesNotContain(art.Title, queue);
        // and a staff POST on the invisible ticket is the same 404
        var r = await PostForm(admin, $"/admin/tickets/{art.Number}?handler=Status", new() { ["to"] = "Rejected" }, tokenFrom: "/admin");
        Assert.Equal(HttpStatusCode.NotFound, r.StatusCode);
        Assert.Equal(TicketStatus.New, await f.DbAsync(db => db.Tickets.Where(t => t.Id == art.Id).Select(t => t.Status).FirstAsync()));
    }

    [Fact]
    public async Task Queue_is_split_by_language_and_staff_can_correct_it()
    {
        var tag = Guid.NewGuid().ToString("N")[..6];
        Task<Ticket> Make(string title, string? lang) => f.ScopedAsync(async sp =>
            (await sp.GetRequiredService<TicketService>().CreateAsync(new NewTicket("code", title, "d", Language: lang), null, null, null, default)).Ticket);
        var ru = await Make("ru-" + tag, "ru");
        var us = await Make("us-" + tag, "en-US");
        var none = await Make("none-" + tag, null);
        var admin = await SignInAsync(await MakeUserAsync(Roles.Admin, true, "tickets.code"));

        var en = await admin.GetStringAsync("/admin?Status=all&Lang=en");
        Assert.Contains(us.Title, en);   // en-US sits with en
        Assert.DoesNotContain(ru.Title, en);
        Assert.DoesNotContain(none.Title, en);
        var unknown = await admin.GetStringAsync("/admin?Status=all&Lang=none");
        Assert.Contains(none.Title, unknown);
        Assert.DoesNotContain(ru.Title, unknown);

        var r = await PostForm(admin, $"/admin/tickets/{none.Number}?handler=Language", new() { ["language"] = "pt_br" }, tokenFrom: "/admin");
        Assert.Equal(HttpStatusCode.Redirect, r.StatusCode);
        Assert.Equal("pt-BR", await f.DbAsync(db => db.Tickets.Where(t => t.Id == none.Id).Select(t => t.Language).FirstAsync()));
    }

    [Fact]
    public async Task Admin_works_a_ticket_and_the_guest_sees_only_the_public_part()
    {
        var created = await f.ScopedAsync(sp => sp.GetRequiredService<TicketService>().CreateAsync(new NewTicket("code", "crash on load", "d"), null, null, null, default));
        var n = created.Ticket.Number;
        var admin = await SignInAsync(await MakeUserAsync(Roles.Admin, true, "tickets.code"));
        var page = $"/admin/tickets/{n}";
        Assert.Equal(HttpStatusCode.Redirect, (await PostForm(admin, page + "?handler=Status", new() { ["to"] = "NeedsInfo" }, page)).StatusCode);
        Assert.Equal(HttpStatusCode.Redirect, (await PostForm(admin, page + "?handler=Message", new() { ["body"] = "secret-staff-note", ["internal"] = "true" }, page)).StatusCode);
        Assert.Equal(HttpStatusCode.Redirect, (await PostForm(admin, page + "?handler=Message", new() { ["body"] = "please attach the save" }, page)).StatusCode);

        var guest = Browser();
        var html = await guest.GetStringAsync($"/t/{n}?k={created.GuestToken}");
        Assert.Contains("please attach the save", html);
        Assert.DoesNotContain("secret-staff-note", html);
        var r = await PostForm(guest, $"/t/{n}?handler=Reply", new() { ["k"] = created.GuestToken!, ["body"] = "here it is" }, $"/t/{n}?k={created.GuestToken}");
        Assert.Equal(HttpStatusCode.Redirect, r.StatusCode);
        Assert.Equal(TicketStatus.Triaged, await f.DbAsync(db => db.Tickets.Where(t => t.Number == n).Select(t => t.Status).FirstAsync()));
        Assert.Contains("secret-staff-note", await admin.GetStringAsync(page));
    }

    [Fact]
    public async Task Second_factor_mark_survives_the_security_stamp_check()
    {
        var admin = await SignInAsync(await MakeUserAsync(Roles.Admin, true, "tickets.code"));
        Assert.Equal(HttpStatusCode.OK, (await admin.GetAsync("/admin")).StatusCode);
        f.Clock.Advance(TimeSpan.FromMinutes(3));   // past the 1-minute validation interval
        Assert.Equal(HttpStatusCode.OK, (await admin.GetAsync("/admin")).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await admin.GetAsync("/admin")).StatusCode);
    }

    [Fact]
    public async Task Demoted_admin_loses_access_at_once()
    {
        var s = await MakeUserAsync(Roles.Admin, true, "tickets.code");
        var admin = await SignInAsync(s);
        Assert.Equal(HttpStatusCode.OK, (await admin.GetAsync("/admin")).StatusCode);
        var super = await SignInAsync(await MakeUserAsync(Roles.SuperAdmin, true));
        var id = await f.DbAsync(db => db.Users.Where(u => u.Email == s.Email).Select(u => u.Id).FirstAsync());
        var r = await PostForm(super, "/admin/super/users", new() { ["id"] = id.ToString(), ["role"] = Roles.User });
        Assert.Equal(HttpStatusCode.Redirect, r.StatusCode);
        f.Clock.Advance(TimeSpan.FromMinutes(2));
        Assert.NotEqual(HttpStatusCode.OK, (await admin.GetAsync("/admin")).StatusCode);
        Assert.True(await f.DbAsync(db => db.AuditLogs.AnyAsync(a => a.Action == "user.access" && a.Target == s.Email)));
    }

    [Fact]
    public async Task Last_superadmin_cannot_demote_themselves()
    {
        var s = await MakeUserAsync(Roles.SuperAdmin, true);
        var c = await SignInAsync(s);
        var id = await f.DbAsync(db => db.Users.Where(u => u.Email == s.Email).Select(u => u.Id).FirstAsync());
        var r = await PostForm(c, "/admin/super/users", new() { ["id"] = id.ToString(), ["role"] = Roles.User });
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);   // the page again, with the error
        await using var scope = f.Services.CreateAsyncScope();
        var users = scope.ServiceProvider.GetRequiredService<UserManager<PortalUser>>();
        Assert.True(await users.IsInRoleAsync((await users.FindByEmailAsync(s.Email))!, Roles.SuperAdmin));
    }

    // ---- files ----

    [Fact]
    public async Task Signed_file_link_opens_for_staff_sandboxed_and_expires()
    {
        var t = await NewTicketAsync("code");
        var (clean, quarantined) = await f.ScopedAsync(async sp =>
        {
            var store = sp.GetRequiredService<ObjectStore>();
            var db = sp.GetRequiredService<PortalDb>();
            TicketAttachment Add(ScanStatus scan)
            {
                var key = ObjectStore.NewKey();
                using (var w = store.Create(key)) w.Write([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]);
                var a = new TicketAttachment { TicketId = t.Id, ObjectKey = key, FileName = "shot.png", ContentType = "image/png", Size = 8, Scan = scan };
                db.TicketAttachments.Add(a);
                return a;
            }
            var c = Add(ScanStatus.Clean);
            var q = Add(ScanStatus.Quarantined);
            await db.SaveChangesAsync();
            return (c, q);
        });
        var urls = f.Services.GetRequiredService<SignedUrls>();
        var staff = await SignInAsync(await MakeUserAsync(Roles.Admin, true, "tickets.code"));
        var outsider = await SignInAsync(await MakeUserAsync(Roles.Admin, true, "tickets.graphics"));

        var link = urls.For(clean);
        var ok = await staff.GetAsync(link);
        Assert.Equal(HttpStatusCode.OK, ok.StatusCode);
        Assert.Equal("image/png", ok.Content.Headers.ContentType!.MediaType);
        Assert.Contains("sandbox", ok.Headers.GetValues("Content-Security-Policy").Single());
        Assert.Equal(HttpStatusCode.NotFound, (await outsider.GetAsync(link)).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await staff.GetAsync(urls.For(quarantined))).StatusCode);
        f.Clock.Advance(TimeSpan.FromMinutes(10));
        Assert.Equal(HttpStatusCode.NotFound, (await staff.GetAsync(link)).StatusCode);
    }

    // ---- strings ----

    [Fact]
    public void Every_text_key_exists_in_both_languages()
    {
        var text = f.Services.GetRequiredService<Xp.Portal.Site.Text>();
        var ru = text.Keys("ru").ToHashSet();
        var en = text.Keys("en").ToHashSet();
        Assert.Empty(ru.Except(en));
        Assert.Empty(en.Except(ru));

        var dynamic = Categories.All.Select(c => "cat." + c)
            .Concat(Enum.GetNames<TicketStatus>().Select(s => "status." + s))
            .Concat(Enum.GetNames<TicketPriority>().Select(s => "prio." + s))
            .Concat(Enum.GetNames<ScanStatus>().Select(s => "scan." + s))
            .Concat(Permissions.All.Select(p => "perm." + p));
        var missingDynamic = dynamic.Where(k => !ru.Contains(k)).ToList();
        Assert.Empty(missingDynamic);

        // literal keys in the pages
        var src = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "../../../../../src/Xp.Portal"));
        var used = Directory.EnumerateFiles(Path.Combine(src, "Pages"), "*.*", SearchOption.AllDirectories)
            .Where(p => p.EndsWith(".cshtml") || p.EndsWith(".cs"))
            .SelectMany(p => KeyRx().Matches(File.ReadAllText(p)).Select(m => m.Groups[1].Value))
            .Where(k => !k.EndsWith('.'))
            .ToHashSet();
        Assert.NotEmpty(used);
        var missingUsed = used.Where(k => !ru.Contains(k)).ToList();
        Assert.Empty(missingUsed);

        // every error code the service can throw has a text
        var codes = Directory.EnumerateFiles(src, "*.cs", SearchOption.AllDirectories)
            .SelectMany(p => CodeRx().Matches(File.ReadAllText(p)).Select(m => m.Groups[1].Value)).ToHashSet();
        var missingCodes = codes.Where(k => !ru.Contains(k)).ToList();
        Assert.Empty(missingCodes);
    }

    [GeneratedRegex(@"T(?:\.Format\(|\[)""([a-z0-9_.]+)""")]
    private static partial Regex KeyRx();

    [GeneratedRegex(@"(?:TicketException\(|Errors\.Add\()""([a-z_]+)""")]
    private static partial Regex CodeRx();
}

static class UriExt
{
    public static string PathAndQuery(this Uri u) => u.IsAbsoluteUri ? u.PathAndQuery : u.OriginalString;
}
