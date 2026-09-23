namespace Xp.Portal;

public sealed class PortalOptions
{
    public const string Section = "Portal";

    /// <summary>Public address of the site, used in links (Telegram, e-mail). No trailing slash.</summary>
    public string PublicUrl { get; set; } = "http://localhost:5080";
    /// <summary>Server secret, base64, at least 32 bytes: guest links and signed file URLs derive from it.</summary>
    public string Secret { get; set; } = "";
    /// <summary>Where the "Download launcher" button leads.</summary>
    public string LauncherDownloadUrl { get; set; } = "";
    /// <summary>Release repository (the tree xp-release builds): a URL or a local folder.</summary>
    public string ReleaseRepo { get; set; } = "";
    public string ReleaseChannel { get; set; } = "stable";
    /// <summary>Base64 Ed25519 public keys the site trusts for releases (the "prod" lines of release-keys.txt).</summary>
    public string[] ReleaseKeys { get; set; } = [];
    /// <summary>Addresses of reverse proxies whose X-Forwarded-For is believed (rate limits go by client IP).</summary>
    public string[] TrustedProxies { get; set; } = [];

    public byte[] SecretBytes()
    {
        var b = Convert.FromBase64String(Secret);
        if (b.Length < 32) throw new InvalidOperationException("Portal:Secret must be at least 32 bytes (base64)");
        return b;
    }
}
