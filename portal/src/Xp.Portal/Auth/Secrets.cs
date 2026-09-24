using System.Security.Cryptography;
using System.Text;
using Konscious.Security.Cryptography;
using Microsoft.AspNetCore.Identity;
using Microsoft.Extensions.Options;
using Xp.Portal.Data;

namespace Xp.Portal.Auth;

/// <summary>The guest's secret link: 128 random bits, only its SHA-256 is stored.</summary>
public static class GuestTokens
{
    public static string New() => Base64Url(RandomNumberGenerator.GetBytes(16));

    public static string Hash(string token) => Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(token)));

    public static bool Matches(string token, string hash)
    {
        if (token.Length is < 16 or > 64) return false;
        return CryptographicOperations.FixedTimeEquals(Encoding.ASCII.GetBytes(Hash(token)), Encoding.ASCII.GetBytes(hash));
    }

    internal static string Base64Url(byte[] b) => Convert.ToBase64String(b).TrimEnd('=').Replace('+', '-').Replace('/', '_');
}

/// <summary>
/// The launcher's device secret: 256 random bits, kept as its SHA-256, and the short code a person
/// reads off the screen. The code's alphabet has no look-alikes (no O and 0, no I and 1), because
/// it is read aloud and typed by hand.
/// </summary>
public static class DeviceSecrets
{
    public const string Alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
    public const int CodeLength = 6;

    public static string NewToken() => GuestTokens.Base64Url(RandomNumberGenerator.GetBytes(32));

    public static string Hash(string token) => GuestTokens.Hash(token);

    /// <summary>Six characters, shown as XXX-XXX.</summary>
    public static string NewCode()
    {
        var c = new char[CodeLength];
        for (int i = 0; i < c.Length; i++) c[i] = Alphabet[RandomNumberGenerator.GetInt32(Alphabet.Length)];
        return new string(c);
    }

    public static string Format(string code) => code.Length == CodeLength ? code[..3] + "-" + code[3..] : code;

    /// <summary>What a person typed, made comparable: case, spaces and the dash do not matter.</summary>
    public static string? Normalize(string? typed)
    {
        if (typed is null) return null;
        var c = new char[CodeLength];
        int n = 0;
        foreach (var ch in typed.ToUpperInvariant())
        {
            if (ch is ' ' or '-' or '_') continue;
            if (n == CodeLength || !Alphabet.Contains(ch)) return null;
            c[n++] = ch;
        }
        return n == CodeLength ? new string(c) : null;
    }
}

public sealed class Argon2Options
{
    /// <summary>KiB. OWASP 2024 minimum for Argon2id: m=19 MiB, t=2, p=1; we use a bit more.</summary>
    public int MemoryKib { get; set; } = 64 * 1024;
    public int Iterations { get; set; } = 3;
    public int Parallelism { get; set; } = 1;
}

/// <summary>
/// Argon2id in PHC format: $argon2id$v=19$m=65536,t=3,p=1$salt$hash. Parameters travel with the hash,
/// so raising them later re-hashes old passwords on the next login (SuccessRehashNeeded).
/// </summary>
public sealed class Argon2PasswordHasher(IOptions<Argon2Options> options) : IPasswordHasher<PortalUser>
{
    const int SaltBytes = 16, HashBytes = 32;
    readonly Argon2Options _o = options.Value;

    public string HashPassword(PortalUser user, string password)
    {
        var salt = RandomNumberGenerator.GetBytes(SaltBytes);
        var hash = Compute(password, salt, _o.MemoryKib, _o.Iterations, _o.Parallelism);
        return $"$argon2id$v=19$m={_o.MemoryKib},t={_o.Iterations},p={_o.Parallelism}${B64(salt)}${B64(hash)}";
    }

    public PasswordVerificationResult VerifyHashedPassword(PortalUser user, string hashedPassword, string providedPassword)
    {
        var parts = hashedPassword.Split('$');
        if (parts.Length != 6 || parts[1] != "argon2id") return PasswordVerificationResult.Failed;
        int m = 0, t = 0, p = 0;
        foreach (var kv in parts[3].Split(','))
        {
            if (kv.Length < 3 || kv[1] != '=' || !int.TryParse(kv.AsSpan(2), out var n)) return PasswordVerificationResult.Failed;
            switch (kv[0]) { case 'm': m = n; break; case 't': t = n; break; case 'p': p = n; break; }
        }
        // refuse absurd parameters from a tampered row instead of allocating gigabytes
        if (m > 1024 * 1024 || t > 20 || p > 16) return PasswordVerificationResult.Failed;
        if (m <= 0 || t <= 0 || p <= 0) return PasswordVerificationResult.Failed;
        byte[] salt, expected;
        try { salt = FromB64(parts[4]); expected = FromB64(parts[5]); }
        catch (FormatException) { return PasswordVerificationResult.Failed; }
        var actual = Compute(providedPassword, salt, m, t, p, expected.Length);
        if (!CryptographicOperations.FixedTimeEquals(actual, expected)) return PasswordVerificationResult.Failed;
        return m < _o.MemoryKib || t < _o.Iterations ? PasswordVerificationResult.SuccessRehashNeeded : PasswordVerificationResult.Success;
    }

    static byte[] Compute(string password, byte[] salt, int m, int t, int p, int len = HashBytes)
    {
        using var a = new Argon2id(Encoding.UTF8.GetBytes(password)) { Salt = salt, MemorySize = m, Iterations = t, DegreeOfParallelism = p };
        return a.GetBytes(len);
    }

    static string B64(byte[] b) => Convert.ToBase64String(b).TrimEnd('=');
    static byte[] FromB64(string s) => Convert.FromBase64String(s.PadRight(s.Length + (4 - s.Length % 4) % 4, '='));
}

/// <summary>Adds the admin specializations as claims, so every request checks them without a query.</summary>
public sealed class PortalClaimsFactory(
    Microsoft.AspNetCore.Identity.UserManager<PortalUser> users,
    Microsoft.AspNetCore.Identity.RoleManager<Microsoft.AspNetCore.Identity.IdentityRole<Guid>> roles,
    IOptions<IdentityOptions> options,
    PortalDb db)
    : UserClaimsPrincipalFactory<PortalUser, Microsoft.AspNetCore.Identity.IdentityRole<Guid>>(users, roles, options)
{
    protected override async Task<System.Security.Claims.ClaimsIdentity> GenerateClaimsAsync(PortalUser user)
    {
        var id = await base.GenerateClaimsAsync(user);
        foreach (var p in db.UserPermissions.Where(p => p.UserId == user.Id).Select(p => p.Permission))
            id.AddClaim(new System.Security.Claims.Claim(Permissions.ClaimType, p));
        if (!string.IsNullOrEmpty(user.DisplayName)) id.AddClaim(new System.Security.Claims.Claim("xp:name", user.DisplayName));
        return id;
    }
}
