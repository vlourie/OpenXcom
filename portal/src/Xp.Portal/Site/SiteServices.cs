using System.Globalization;
using System.Net.Mail;
using System.Reflection;
using System.Text.Json;
using Microsoft.AspNetCore.Identity;
using Microsoft.Extensions.Caching.Memory;
using Microsoft.Extensions.Options;
using Xp.Manifest;
using Xp.Portal.Data;

namespace Xp.Portal.Site;

public sealed record ReleaseView(string Id, string Version, DateTimeOffset Published, string Changelog);

/// <summary>The game as it is played: Piratez, the engine under it and the build (release) of the launcher's channel.</summary>
public sealed record GameView(string Piratez, string Engine, string? Build, DateTimeOffset? Published);

/// <summary>The history of the channel, newest first, and the roadmap in the reader's language (Markdown).</summary>
public sealed record NotesView(List<ReleaseView> Releases, string Roadmap, DateTimeOffset Updated);

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
        var latest = await LatestAsync(options.Value.ReleaseChannel);
        if (latest is null) return null;
        var r = latest.Release;
        var log_ = r.Changelog.TryGetValue(lang, out var c) ? c : r.Changelog.Values.FirstOrDefault() ?? "";
        return new ReleaseView(r.Id, r.Version, r.Published, log_);
    }

    /// <summary>
    /// What game this site is about. The Piratez version comes from the release itself (its mod.piratez
    /// component), the engine from the settings; with no release the settings give the Piratez too.
    /// </summary>
    public async Task<GameView> GameAsync(CancellationToken ct)
    {
        var o = options.Value;
        var latest = await LatestAsync(o.ReleaseChannel);
        // the mod writes "v.o2"; the players say "o2"
        var piratez = (latest?.Piratez ?? "").Trim().TrimStart('v', 'V').TrimStart('.');
        if (piratez.Length == 0) piratez = o.PiratezVersion;
        var r = latest?.Release;
        return new GameView(piratez, o.EngineName, r?.Version, r?.Published);
    }

    /// <summary>
    /// Every release of the channel with its "What's new" in the reader's language, newest first, and
    /// the roadmap. Null when the repository has no history yet (or it did not verify): the pages then
    /// fall back to the current release alone.
    /// </summary>
    public async Task<NotesView?> NotesAsync(string lang, CancellationToken ct)
    {
        var o = options.Value;
        if (string.IsNullOrWhiteSpace(o.ReleaseRepo) || o.ReleaseKeys.Length == 0 || string.IsNullOrWhiteSpace(o.ReleaseChannel)) return null;
        var notes = await cache.GetOrCreateAsync("notes:" + o.ReleaseChannel, async e =>
        {
            e.AbsoluteExpirationRelativeToNow = TimeSpan.FromMinutes(5);
            try
            {
                var repo = new RepoClient(http.CreateClient("releases"), new Uri(o.ReleaseRepo), new TrustedKeys(o.ReleaseKeys));
                // not the visitor's token: the answer is shared, and one who left must not leave an error cached for all
                return await repo.GetNotesAsync(o.ReleaseChannel, CancellationToken.None);
            }
            catch (Exception ex) when (ex is HttpRequestException or TrustException or ManifestException or IOException or TaskCanceledException)
            {
                // FileNotFoundException is an IOException: a repository from before the history is not an error
                if (ex is not FileNotFoundException) log.LogWarning("release notes ({Channel}): {Error}", o.ReleaseChannel, ex.Message);
                e.AbsoluteExpirationRelativeToNow = TimeSpan.FromMinutes(1);
                return null;
            }
        });
        if (notes is null) return null;
        var releases = notes.Releases
            .Select(r => new ReleaseView(r.Id, r.Version, r.Published, Pick(r.Changelog, lang).Trim()))
            .ToList();
        return new NotesView(releases, Pick(notes.Roadmap, lang).Trim(), notes.Updated);
    }

    /// <summary>The text in the reader's language, else Russian, else whatever there is.</summary>
    static string Pick(Dictionary<string, string> texts, string lang) =>
        texts.TryGetValue(lang, out var t) && !string.IsNullOrWhiteSpace(t) ? t
        : texts.TryGetValue("ru", out var ru) ? ru
        : texts.Values.FirstOrDefault() ?? "";

    /// <summary>
    /// The launcher to download, taken from the launcher channel of the same repository. Read from
    /// the repository and never from a setting: the site went out with an empty setting and the
    /// entrance screen simply had no download button, which nothing in the code or the log said.
    /// </summary>
    public async Task<LauncherView?> LauncherAsync(CancellationToken ct)
    {
        var latest = await LatestAsync(options.Value.LauncherChannel);
        if (latest is null) return null;
        var file = latest.Bootstrap;
        if (file is null)
        {
            log.LogWarning("launcher release {Id} has no {File}", latest.Release.Id, BootstrapFile);
            return null;
        }
        var r = latest.Release;
        return new LauncherView(r.Version, file.Sha256, file.Size, r.Published);
    }

    /// <summary>
    /// What the pages take from a release. The game's manifest lists every file (113 thousand, ~46 MB
    /// parsed): it is fetched once per release and only these fields are kept (code audit 2026-10-27, portal §6).
    /// </summary>
    sealed record ReleaseSummary(string ManifestSha256, ReleaseInfo Release, string? Piratez, ManifestFile? Bootstrap);

    /// <summary>The last summary of each channel: while the pointer names the same manifest, it is not fetched again.</summary>
    readonly System.Collections.Concurrent.ConcurrentDictionary<string, ReleaseSummary> _last = new();

    async Task<ReleaseSummary?> LatestAsync(string channel)
    {
        var o = options.Value;
        if (string.IsNullOrWhiteSpace(o.ReleaseRepo) || o.ReleaseKeys.Length == 0 || string.IsNullOrWhiteSpace(channel)) return null;
        return await cache.GetOrCreateAsync("release:" + channel, async e =>
        {
            e.AbsoluteExpirationRelativeToNow = TimeSpan.FromMinutes(5);
            try
            {
                var repo = new RepoClient(http.CreateClient("releases"), new Uri(o.ReleaseRepo), new TrustedKeys(o.ReleaseKeys));
                // not the visitor's token: the answer is shared, and one who left must not leave an error cached for all
                var pointer = await repo.GetPointerAsync(channel, 0, CancellationToken.None);
                if (_last.TryGetValue(channel, out var last) && last.ManifestSha256 == pointer.ManifestSha256) return last;
                var m = await repo.GetManifestAsync(pointer, CancellationToken.None);
                var summary = new ReleaseSummary(pointer.ManifestSha256, m.Release,
                    m.Components.FirstOrDefault(c => c.Id == "mod.piratez")?.Version,
                    m.Files.FirstOrDefault(f => f.Path.Equals(BootstrapFile, StringComparison.OrdinalIgnoreCase)));
                _last[channel] = summary;
                return summary;
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
    /// <summary>STARTTLS port; SmtpClient cannot speak implicit TLS, so 465 does not work.</summary>
    public int SmtpPort { get; set; } = 587;
    public string SmtpUser { get; set; } = "";
    public string SmtpPassword { get; set; } = "";
    public string PickupDir { get; set; } = "";
}

/// <summary>
/// Account letters never fail the page that sends them: the answer there is the same whether a letter
/// went or not, and the person can ask for another one. A failure goes to the log with the domain
/// only; the server checks the mail setup with <see cref="SendTestAsync"/>, which does throw.
/// </summary>
public sealed class EmailSender(IOptions<EmailOptions> options, Text text, ILogger<EmailSender> log) : IEmailSender<PortalUser>
{
    public Task SendConfirmationLinkAsync(PortalUser user, string email, string link) =>
        TrySendAsync(email, text["mail.confirm.subject"], text.Format("mail.confirm.body", link));

    public Task SendPasswordResetLinkAsync(PortalUser user, string email, string link) =>
        TrySendAsync(email, text["mail.reset.subject"], text.Format("mail.reset.body", link));

    public Task SendPasswordResetCodeAsync(PortalUser user, string email, string code) =>
        TrySendAsync(email, text["mail.reset.subject"], code);

    public Task SendTestAsync(string to) =>
        SendAsync(to, text["mail.test.subject"], text["mail.test.body"]);

    async Task TrySendAsync(string to, string subject, string body)
    {
        try { await SendAsync(to, subject, body); }
        catch (Exception e) when (e is SmtpException or InvalidOperationException or IOException or FormatException)
        {
            log.LogError("Mail to *@{Domain} failed: {Error}: {Message}", to[(to.LastIndexOf('@') + 1)..], e.GetType().Name, e.Message);
        }
    }

    async Task SendAsync(string to, string subject, string body)
    {
        var o = options.Value;
        using var msg = new MailMessage(o.From, to, subject, body) { IsBodyHtml = false };
        using var smtp = new SmtpClient { Timeout = 20_000 };
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
