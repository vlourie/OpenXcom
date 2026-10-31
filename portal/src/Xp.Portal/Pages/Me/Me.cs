using System.Globalization;
using System.Security.Claims;
using System.Text;
using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.AspNetCore.RateLimiting;
using Microsoft.EntityFrameworkCore;
using Xp.Portal.Auth;
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

/// <summary>
/// The launchers linked to this account. A launcher never holds the password: it shows a code, the
/// person confirms it here, and from then on it works with a device token that can be taken away
/// from this page alone.
/// </summary>
[EnableRateLimiting("devices")]
public sealed class DevicesModel(PortalDb db, TimeProvider clock, Audit audit) : PageModel
{
    public List<DeviceToken> Devices { get; private set; } = new();
    /// <summary>A code waiting for a yes, as the launcher shows it (XXX-XXX).</summary>
    public string? Pending { get; private set; }
    public string PendingName { get; private set; } = "";
    public List<string> Errors { get; } = new();

    Guid Me => Guid.Parse(User.FindFirstValue(ClaimTypes.NameIdentifier)!);

    async Task LoadAsync(string? code, CancellationToken ct)
    {
        Devices = await db.DeviceTokens.Where(d => d.UserId == Me && d.RevokedAt == null)
            .OrderByDescending(d => d.CreatedAt).ToListAsync(ct);
        if (DeviceSecrets.Normalize(code) is not { } clean) return;
        var row = await db.DeviceLinkCodes.FirstOrDefaultAsync(c => c.Code == clean, ct);
        // an unknown code and an expired one answer the same: the page tells nothing about codes it was not given
        if (row is null || row.ConsumedByUserId is not null || row.ExpiresAt <= clock.GetUtcNow()) return;
        Pending = DeviceSecrets.Format(row.Code);
        PendingName = row.Name;
    }

    public async Task OnGetAsync(string? code, CancellationToken ct) => await LoadAsync(code, ct);

    public async Task<IActionResult> OnPostConfirmAsync(string? code, CancellationToken ct)
    {
        var clean = DeviceSecrets.Normalize(code);
        var row = clean is null ? null : await db.DeviceLinkCodes.FirstOrDefaultAsync(c => c.Code == clean, ct);
        if (row is null || row.ConsumedByUserId is not null || row.ExpiresAt <= clock.GetUtcNow())
        {
            Errors.Add("devices.code_bad");
            await LoadAsync(null, ct);
            return Page();
        }
        row.ConsumedByUserId = Me;
        row.ConsumedAt = clock.GetUtcNow();
        audit.Add(Me, "device.link", row.DeviceId.ToString(), row.Name);
        await db.SaveChangesAsync(ct);
        TempData["flash"] = "devices.flash.linked";
        return RedirectToPage();
    }

    public async Task<IActionResult> OnPostRevokeAsync(Guid id, CancellationToken ct)
    {
        var device = await db.DeviceTokens.FirstOrDefaultAsync(d => d.Id == id && d.UserId == Me && d.RevokedAt == null, ct);
        if (device is not null)
        {
            device.RevokedAt = clock.GetUtcNow();
            audit.Add(Me, "device.revoke", device.Id.ToString(), device.Name);
            await db.SaveChangesAsync(ct);
            TempData["flash"] = "devices.flash.revoked";
        }
        return RedirectToPage();
    }
}
