using System.Globalization;
using System.Security.Claims;
using System.Text;
using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.AspNetCore.RateLimiting;
using Microsoft.EntityFrameworkCore;
using Xp.Portal.Data;
using Xp.Portal.Site;

namespace Xp.Portal.Pages.Me;

public sealed class MyTicketsModel(PortalDb db) : PageModel
{
    public List<Ticket> Tickets { get; private set; } = new();

    public async Task OnGetAsync(CancellationToken ct)
    {
        var me = Guid.Parse(User.FindFirstValue(ClaimTypes.NameIdentifier)!);
        Tickets = await db.Tickets.Where(t => t.AuthorId == me).OrderByDescending(t => t.UpdatedAt).Take(200).ToListAsync(ct);
    }
}

[EnableRateLimiting("login")]
public sealed class SecurityModel(UserManager<PortalUser> users, SignInManager<PortalUser> signIn, PortalDb db, Audit audit) : PageModel
{
    public bool Enabled { get; private set; }
    public string SharedKey { get; private set; } = "";
    public string AuthenticatorUri { get; private set; } = "";
    public string[]? RecoveryCodes { get; private set; }
    public int RecoveryLeft { get; private set; }
    public List<string> Errors { get; } = new();

    async Task<PortalUser> LoadAsync()
    {
        var u = await users.GetUserAsync(User) ?? throw new InvalidOperationException("signed-in user is gone");
        Enabled = await users.GetTwoFactorEnabledAsync(u);
        if (!Enabled)
        {
            var key = await users.GetAuthenticatorKeyAsync(u);
            if (string.IsNullOrEmpty(key))
            {
                await users.ResetAuthenticatorKeyAsync(u);
                key = await users.GetAuthenticatorKeyAsync(u);
            }
            SharedKey = Group(key!);
            AuthenticatorUri = $"otpauth://totp/{Uri.EscapeDataString("X-Piratez")}:{Uri.EscapeDataString(u.Email!)}?secret={key}&issuer={Uri.EscapeDataString("X-Piratez")}&digits=6";
        }
        else RecoveryLeft = await users.CountRecoveryCodesAsync(u);
        return u;
    }

    static string Group(string key)
    {
        var sb = new StringBuilder();
        for (int i = 0; i < key.Length; i += 4) sb.Append(key.AsSpan(i, Math.Min(4, key.Length - i))).Append(' ');
        return sb.ToString().TrimEnd().ToLower(CultureInfo.InvariantCulture);
    }

    Guid Me => Guid.Parse(User.FindFirstValue(ClaimTypes.NameIdentifier)!);

    public async Task OnGetAsync() => await LoadAsync();

    public async Task<IActionResult> OnPostEnableAsync(string? code)
    {
        var u = await LoadAsync();
        if (Enabled) return Page();
        var clean = (code ?? "").Replace(" ", "").Replace("-", "");
        if (!await users.VerifyTwoFactorTokenAsync(u, users.Options.Tokens.AuthenticatorTokenProvider, clean))
        {
            Errors.Add("code_invalid");
            return Page();
        }
        await users.SetTwoFactorEnabledAsync(u, true);
        RecoveryCodes = (await users.GenerateNewTwoFactorRecoveryCodesAsync(u, 10))!.ToArray();
        audit.Add(Me, "2fa.enable", u.Email!);
        await db.SaveChangesAsync();
        Enabled = true;
        // the session in hand was opened without the second factor; staff pages need a new sign-in
        await signIn.SignOutAsync();
        return Page();
    }

    public async Task<IActionResult> OnPostDisableAsync(string? code)
    {
        var u = await LoadAsync();
        if (!Enabled) return Page();
        var clean = (code ?? "").Replace(" ", "").Replace("-", "");
        if (!await users.VerifyTwoFactorTokenAsync(u, users.Options.Tokens.AuthenticatorTokenProvider, clean))
        {
            Errors.Add("code_invalid");
            return Page();
        }
        await users.SetTwoFactorEnabledAsync(u, false);
        await users.ResetAuthenticatorKeyAsync(u);
        audit.Add(Me, "2fa.disable", u.Email!);
        await db.SaveChangesAsync();
        await signIn.RefreshSignInAsync(u);
        TempData["flash"] = "security.disabled";
        return RedirectToPage();
    }

    public async Task<IActionResult> OnPostRecoveryAsync()
    {
        var u = await LoadAsync();
        if (!Enabled) return Page();
        RecoveryCodes = (await users.GenerateNewTwoFactorRecoveryCodesAsync(u, 10))!.ToArray();
        audit.Add(Me, "2fa.recovery.renew", u.Email!);
        await db.SaveChangesAsync();
        RecoveryLeft = 10;
        return Page();
    }

    public async Task<IActionResult> OnPostPasswordAsync(string? current, string? password)
    {
        var u = await LoadAsync();
        var r = await users.ChangePasswordAsync(u, current ?? "", password ?? "");
        if (!r.Succeeded)
        {
            Errors.AddRange(r.Errors.Select(e => e.Code == "PasswordMismatch" ? "password_wrong" : "identity." + e.Code));
            return Page();
        }
        await signIn.RefreshSignInAsync(u);
        TempData["flash"] = "security.password_changed";
        return RedirectToPage();
    }
}
