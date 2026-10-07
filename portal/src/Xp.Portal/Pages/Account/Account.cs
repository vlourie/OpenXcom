using System.Text;
using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.AspNetCore.RateLimiting;
using Microsoft.AspNetCore.WebUtilities;
using Microsoft.Extensions.Caching.Memory;
using Microsoft.Extensions.Options;
using Xp.Portal.Auth;
using Xp.Portal.Data;

namespace Xp.Portal.Pages.Account;

static class Codes
{
    public static string Encode(string token) => WebEncoders.Base64UrlEncode(Encoding.UTF8.GetBytes(token));
    public static string? Decode(string? code)
    {
        if (string.IsNullOrEmpty(code)) return null;
        try { return Encoding.UTF8.GetString(WebEncoders.Base64UrlDecode(code)); }
        catch (FormatException) { return null; }
    }

    /// <summary>
    /// Only a path of this site goes on: the launcher sends people to /me/devices?code=..., and that
    /// address has to survive registration, the letter and the first sign-in.
    /// </summary>
    public static string? Local(string? url) =>
        !string.IsNullOrEmpty(url) && url.Length <= 512 && url[0] == '/' && !url.StartsWith("//") && !url.StartsWith("/\\") ? url : null;

    /// <summary>The address in the confirmation letter, carrying where the person was going.</summary>
    public static async Task<string> ConfirmLinkAsync(UserManager<PortalUser> users, PortalUser u, PortalOptions portal, string? returnUrl)
    {
        var code = Encode(await users.GenerateEmailConfirmationTokenAsync(u));
        var link = $"{portal.PublicUrl.TrimEnd('/')}/account/confirm?user={u.Id}&code={code}";
        return Local(returnUrl) is { } back ? link + "&returnUrl=" + Uri.EscapeDataString(back) : link;
    }

    public static string Login(string? returnUrl) =>
        Local(returnUrl) is { } back ? "/account/login?ReturnUrl=" + Uri.EscapeDataString(back) : "/account/login";
}

[EnableRateLimiting("login")]
public sealed class RegisterModel(UserManager<PortalUser> users, IEmailSender<PortalUser> mail, IOptions<PortalOptions> portal) : PageModel
{
    [BindProperty] public string Email { get; set; } = "";
    [BindProperty] public string DisplayName { get; set; } = "";
    [BindProperty] public string Password { get; set; } = "";
    [BindProperty(SupportsGet = true)] public string? ReturnUrl { get; set; }
    public List<string> Errors { get; } = new();
    public bool Sent { get; private set; }

    public void OnGet() => ReturnUrl = Codes.Local(ReturnUrl);

    public async Task<IActionResult> OnPostAsync()
    {
        ReturnUrl = Codes.Local(ReturnUrl);
        Email = Email.Trim();
        DisplayName = DisplayName.Trim();
        if (Email.Length is 0 or > 256 || !Email.Contains('@')) Errors.Add("email_invalid");
        if (DisplayName.Length is 0 or > 64) Errors.Add("name_invalid");
        if (Errors.Count > 0) return Page();
        if (await users.FindByEmailAsync(Email) is null)
        {
            var u = new PortalUser { UserName = Email, Email = Email, DisplayName = DisplayName };
            var r = await users.CreateAsync(u, Password);
            if (!r.Succeeded)
            {
                Errors.AddRange(r.Errors.Select(e => "identity." + e.Code));
                return Page();
            }
            await users.AddToRoleAsync(u, Roles.User);
            await mail.SendConfirmationLinkAsync(u, Email, await Codes.ConfirmLinkAsync(users, u, portal.Value, ReturnUrl));
        }
        // the same answer whether the address was free or not: registration is not an address oracle
        Sent = true;
        return Page();
    }
}

public sealed class ConfirmModel(UserManager<PortalUser> users) : PageModel
{
    public bool Ok { get; private set; }
    public string LoginUrl { get; private set; } = "/account/login";

    public async Task OnGetAsync(Guid user, string? code, string? returnUrl)
    {
        var u = await users.FindByIdAsync(user.ToString());
        var token = Codes.Decode(code);
        Ok = u is not null && token is not null && (await users.ConfirmEmailAsync(u, token)).Succeeded;
        LoginUrl = Codes.Login(returnUrl);
    }
}

/// <summary>
/// Another confirmation letter, for whoever lost the first. The same answer whatever the address,
/// and at most one letter per address in a few minutes, so the page cannot be used to flood a mailbox.
/// </summary>
[EnableRateLimiting("login")]
public sealed class ResendModel(UserManager<PortalUser> users, IEmailSender<PortalUser> mail, IOptions<PortalOptions> portal,
    IMemoryCache cache) : PageModel
{
    static readonly TimeSpan Pause = TimeSpan.FromMinutes(3);

    [BindProperty] public string Email { get; set; } = "";
    [BindProperty(SupportsGet = true)] public string? ReturnUrl { get; set; }
    public bool Sent { get; private set; }

    public void OnGet() => ReturnUrl = Codes.Local(ReturnUrl);

    public async Task<IActionResult> OnPostAsync()
    {
        ReturnUrl = Codes.Local(ReturnUrl);
        var u = await users.FindByEmailAsync(Email.Trim());
        if (u is not null && !await users.IsEmailConfirmedAsync(u) && !cache.TryGetValue("resend:" + u.Id, out _))
        {
            cache.Set("resend:" + u.Id, true, Pause);
            await mail.SendConfirmationLinkAsync(u, u.Email!, await Codes.ConfirmLinkAsync(users, u, portal.Value, ReturnUrl));
        }
        Sent = true;
        return Page();
    }
}

[EnableRateLimiting("login")]
public sealed class LoginModel(SignInManager<PortalUser> signIn) : PageModel
{
    [BindProperty] public string Email { get; set; } = "";
    [BindProperty] public string Password { get; set; } = "";
    [BindProperty(SupportsGet = true)] public string? ReturnUrl { get; set; }
    public List<string> Errors { get; } = new();

    public void OnGet() { }

    public async Task<IActionResult> OnPostAsync()
    {
        var r = await signIn.PasswordSignInAsync(Email.Trim(), Password, isPersistent: true, lockoutOnFailure: true);
        if (r.Succeeded) return LocalRedirect(Safe(ReturnUrl));
        if (r.RequiresTwoFactor) return RedirectToPage("/Account/Login2fa", new { returnUrl = Safe(ReturnUrl) });
        Errors.Add(r.IsLockedOut ? "login_locked" : r.IsNotAllowed ? "email_not_confirmed" : "login_failed");
        return Page();
    }

    internal string Safe(string? url) => !string.IsNullOrEmpty(url) && Url.IsLocalUrl(url) ? url : "/";

    /// <summary>A link to another account page that keeps where the person was going.</summary>
    public string Keep(string path) => Codes.Local(ReturnUrl) is { } back ? path + "?returnUrl=" + Uri.EscapeDataString(back) : path;
}

[EnableRateLimiting("login")]
public sealed class Login2faModel(SignInManager<PortalUser> signIn) : PageModel
{
    [BindProperty] public string Code { get; set; } = "";
    [BindProperty] public bool Recovery { get; set; }
    [BindProperty(SupportsGet = true)] public string? ReturnUrl { get; set; }
    public List<string> Errors { get; } = new();

    public async Task<IActionResult> OnGetAsync() =>
        await signIn.GetTwoFactorAuthenticationUserAsync() is null ? RedirectToPage("/Account/Login") : Page();

    public async Task<IActionResult> OnPostAsync()
    {
        if (await signIn.GetTwoFactorAuthenticationUserAsync() is null) return RedirectToPage("/Account/Login");
        var code = Code.Replace(" ", "").Replace("-", "");
        // no "remember this device": staff pages want the second factor on every sign-in
        var r = Recovery
            ? await signIn.TwoFactorRecoveryCodeSignInAsync(Code.Trim())
            : await signIn.TwoFactorAuthenticatorSignInAsync(code, isPersistent: true, rememberClient: false);
        if (r.Succeeded) return LocalRedirect(!string.IsNullOrEmpty(ReturnUrl) && Url.IsLocalUrl(ReturnUrl) ? ReturnUrl : "/");
        Errors.Add(r.IsLockedOut ? "login_locked" : "code_invalid");
        return Page();
    }
}

public sealed class LogoutModel(SignInManager<PortalUser> signIn) : PageModel
{
    public IActionResult OnGet() => Redirect("/");

    public async Task<IActionResult> OnPostAsync()
    {
        await signIn.SignOutAsync();
        return Redirect("/");
    }
}

[EnableRateLimiting("login")]
public sealed class ForgotModel(UserManager<PortalUser> users, IEmailSender<PortalUser> mail, IOptions<PortalOptions> portal) : PageModel
{
    [BindProperty] public string Email { get; set; } = "";
    public bool Sent { get; private set; }

    public void OnGet() { }

    public async Task<IActionResult> OnPostAsync()
    {
        var u = await users.FindByEmailAsync(Email.Trim());
        if (u is not null && await users.IsEmailConfirmedAsync(u))
        {
            var code = Codes.Encode(await users.GeneratePasswordResetTokenAsync(u));
            await mail.SendPasswordResetLinkAsync(u, u.Email!, $"{portal.Value.PublicUrl.TrimEnd('/')}/account/reset?user={u.Id}&code={code}");
        }
        Sent = true;
        return Page();
    }
}

[EnableRateLimiting("login")]
public sealed class ResetModel(UserManager<PortalUser> users) : PageModel
{
    [BindProperty(SupportsGet = true, Name = "user")] public Guid UserId { get; set; }
    [BindProperty(SupportsGet = true)] public string? Code { get; set; }
    [BindProperty] public string Password { get; set; } = "";
    public List<string> Errors { get; } = new();
    public bool Done { get; private set; }

    public void OnGet() { }

    public async Task<IActionResult> OnPostAsync()
    {
        var u = await users.FindByIdAsync(UserId.ToString());
        var token = Codes.Decode(Code);
        if (u is null || token is null) { Errors.Add("reset_invalid"); return Page(); }
        var r = await users.ResetPasswordAsync(u, token, Password);
        if (!r.Succeeded)
        {
            Errors.AddRange(r.Errors.Select(e => e.Code == "InvalidToken" ? "reset_invalid" : "identity." + e.Code));
            return Page();
        }
        await users.UpdateSecurityStampAsync(u);   // sign out every other session
        Done = true;
        return Page();
    }
}

public sealed class DeniedModel : PageModel
{
    public bool IsStaffWithout2fa { get; private set; }

    public void OnGet() =>
        IsStaffWithout2fa = (User.IsInRole(Roles.Admin) || User.IsInRole(Roles.SuperAdmin)) && !User.HasClaim("amr", "mfa");
}
