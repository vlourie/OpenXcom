using System.Globalization;
using System.Net.Mail;
using System.Reflection;
using System.Text.Json;
using Microsoft.AspNetCore.Identity;
using Microsoft.Extensions.Caching.Memory;
using Microsoft.Extensions.Options;
using Xp.Launcher.Core;
using Xp.Manifest;
using Xp.Portal.Data;

namespace Xp.Portal.Site;

public sealed record ReleaseView(string Id, string Version, DateTimeOffset Published, string Changelog);

/// <summary>What the entrance screen offers a new player: one file, its version and its size.</summary>
public sealed record LauncherView(string Version, string Sha256, long Size, DateTimeOffset Published)
{
    /// <summary>The name the file is saved under — the version is in it, so a support question names it.</summary>
    public string FileName => $"XPiratezHD-Setup-{Version}.exe";
    public double Megabytes => Math.Round(Size / 1024.0 / 1024.0, 1);
}

/// <summary>
/// The version shown on the site, read from the release repository with the same verification as the
/// launcher: a release whose signature does not check out is not shown at all.
/// </summary>
public sealed class ReleaseFeed(IOptions<PortalOptions> options, IHttpClientFactory http, IMemoryCache cache, ILogger<ReleaseFeed> log)
{
    /// <summary>The first file a new player runs. Small: it fetches the launcher itself.</summary>
    public const string BootstrapFile = "xp-bootstrap.exe";

    public async Task<ReleaseView?> CurrentAsync(string lang, CancellationToken ct)
    {
        var latest = await LatestAsync(options.Value.ReleaseChannel, ct);
        if (latest is null) return null;
        var r = latest.Manifest.Release;
        var log_ = r.Changelog.TryGetValue(lang, out var c) ? c : r.Changelog.Values.FirstOrDefault() ?? "";
        return new ReleaseView(r.Id, r.Version, r.Published, log_);
    }

    /// <summary>
    /// The launcher to download, taken from the launcher channel of the same repository. Read from
    /// the repository and never from a setting: the site went out with an empty setting and the
    /// entrance screen simply had no download button, which nothing in the code or the log said.
    /// </summary>
    public async Task<LauncherView?> LauncherAsync(CancellationToken ct)
    {
        var latest = await LatestAsync(options.Value.LauncherChannel, ct);
        if (latest is null) return null;
        var files = latest.Manifest.Files;
        var file = files.FirstOrDefault(f => f.Path.Equals(BootstrapFile, StringComparison.OrdinalIgnoreCase));
        if (file is null)
        {
            log.LogWarning("launcher release {Id} has no {File}", latest.Manifest.Release.Id, BootstrapFile);
            return null;
        }
        var r = latest.Manifest.Release;
        return new LauncherView(r.Version, file.Sha256, file.Size, r.Published);
    }

    async Task<LatestRelease?> LatestAsync(string channel, CancellationToken ct)
    {
        var o = options.Value;
        if (string.IsNullOrWhiteSpace(o.ReleaseRepo) || o.ReleaseKeys.Length == 0 || string.IsNullOrWhiteSpace(channel)) return null;
        return await cache.GetOrCreateAsync("release:" + channel, async e =>
        {
            e.AbsoluteExpirationRelativeToNow = TimeSpan.FromMinutes(5);
            try
            {
                var repo = new RepoClient(http.CreateClient("releases"), new Uri(o.ReleaseRepo), new TrustedKeys(o.ReleaseKeys));
                return await repo.GetLatestAsync(channel, 0, ct);
            }
            catch (Exception ex) when (ex is HttpRequestException or TrustException or ManifestException or IOException or TaskCanceledException)
            {
                log.LogWarning("release feed ({Channel}): {Error}", channel, ex.Message);
                e.AbsoluteExpirationRelativeToNow = TimeSpan.FromMinutes(1);
                return null;
            }
        });
    }
}

/// <summary>
/// A picture and its double twin. A screen with scaling asks for twice the pixels; a site that has only
/// one size lets the browser stretch what it has, and the art floats. The twin lies beside the picture
/// as &lt;name&gt;@2x.&lt;ext&gt; (tools/site_art_2x.py builds it); where there is no twin the markup asks for
/// nothing extra, so a missing file never turns into a 404 in every visitor's log.
/// </summary>
public sealed class Art(IWebHostEnvironment env)
{
    readonly System.Collections.Concurrent.ConcurrentDictionary<string, string?> _known = new();

    /// <summary>For "img/hero.jpg" — "/img/hero.jpg 1x, /img/hero@2x.jpg 2x", or null when there is no twin.</summary>
    public string? SrcSet(string path)
    {
        if (string.IsNullOrEmpty(path)) return null;
        return _known.GetOrAdd(path.TrimStart('/'), p =>
        {
            var twin = $"{System.IO.Path.ChangeExtension(p, null)}@2x{System.IO.Path.GetExtension(p)}";
            return env.WebRootFileProvider.GetFileInfo(twin).Exists ? $"/{p} 1x, /{twin} 2x" : null;
        });
    }
}

/// <summary>
/// UI strings from Strings/&lt;lang&gt;.json, embedded. A missing key shows as the key itself, so a gap is
/// visible on the page instead of silently empty.
/// </summary>
public sealed class Text
{
    public static readonly string[] Languages = ["ru", "en"];
    readonly Dictionary<string, Dictionary<string, string>> _all = new();

    public Text()
    {
        var asm = Assembly.GetExecutingAssembly();
        foreach (var lang in Languages)
        {
            using var s = asm.GetManifestResourceStream($"strings.{lang}.json") ?? throw new InvalidOperationException($"strings.{lang}.json missing");
            _all[lang] = JsonSerializer.Deserialize<Dictionary<string, string>>(s) ?? new();
        }
    }

    public static string Lang => CultureInfo.CurrentUICulture.TwoLetterISOLanguageName == "en" ? "en" : "ru";

    public string this[string key] => _all[Lang].TryGetValue(key, out var v) ? v : _all["ru"].TryGetValue(key, out var r) ? r : key;

    public string Format(string key, params object[] args) => string.Format(CultureInfo.CurrentCulture, this[key], args);

    internal IEnumerable<string> Keys(string lang) => _all[lang].Keys;
}

public sealed class EmailOptions
{
    public const string Section = "Email";
    public string From { get; set; } = "noreply@localhost";
    /// <summary>SMTP host; empty = messages are written as .eml files into PickupDir (development).</summary>
    public string SmtpHost { get; set; } = "";
    public int SmtpPort { get; set; } = 587;
    public string SmtpUser { get; set; } = "";
    public string SmtpPassword { get; set; } = "";
    public string PickupDir { get; set; } = "";
}

public sealed class EmailSender(IOptions<EmailOptions> options, Text text) : IEmailSender<PortalUser>
{
    public Task SendConfirmationLinkAsync(PortalUser user, string email, string link) =>
        SendAsync(email, text["mail.confirm.subject"], text.Format("mail.confirm.body", link));

    public Task SendPasswordResetLinkAsync(PortalUser user, string email, string link) =>
        SendAsync(email, text["mail.reset.subject"], text.Format("mail.reset.body", link));

    public Task SendPasswordResetCodeAsync(PortalUser user, string email, string code) =>
        SendAsync(email, text["mail.reset.subject"], code);

    async Task SendAsync(string to, string subject, string body)
    {
        var o = options.Value;
        using var msg = new MailMessage(o.From, to, subject, body) { IsBodyHtml = false };
        using var smtp = new SmtpClient();
        if (string.IsNullOrWhiteSpace(o.SmtpHost))
        {
            Directory.CreateDirectory(o.PickupDir);
            smtp.DeliveryMethod = SmtpDeliveryMethod.SpecifiedPickupDirectory;
            smtp.PickupDirectoryLocation = Path.GetFullPath(o.PickupDir);
        }
        else
        {
            smtp.Host = o.SmtpHost;
            smtp.Port = o.SmtpPort;
            smtp.EnableSsl = true;
            if (o.SmtpUser.Length > 0) smtp.Credentials = new System.Net.NetworkCredential(o.SmtpUser, o.SmtpPassword);
        }
        await smtp.SendMailAsync(msg);
    }
}

public sealed class Audit(PortalDb db, TimeProvider clock)
{
    /// <summary>Adds a record to the current unit of work; the caller's SaveChanges writes it with the change itself.</summary>
    public void Add(Guid? actor, string action, string target, string? detail = null) =>
        db.AuditLogs.Add(new AuditLog { ActorId = actor, Action = action, Target = target, Detail = detail, At = clock.GetUtcNow() });
}
