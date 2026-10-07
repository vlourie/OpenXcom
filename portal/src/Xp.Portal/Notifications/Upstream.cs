using System.Globalization;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Xml.Linq;
using Microsoft.Extensions.Options;
using Xp.Portal.Data;

namespace Xp.Portal.Notifications;

public sealed class UpstreamOptions
{
    public const string Section = "Upstream";
    public bool Enabled { get; set; } = true;
    public double CheckHours { get; set; } = 24;
    /// <summary>A pause after start, so a restart loop never hammers the sources.</summary>
    public int StartDelaySeconds { get; set; } = 120;
    /// <summary>Failed checks in a row before the one "cannot check" notice.</summary>
    public int FailuresToReport { get; set; } = 3;
    public string ModDbRss { get; set; } = "https://rss.moddb.com/mods/x-piratez/downloads/feed/rss.xml";
    public string OxceVersionUrl { get; set; } = "https://raw.githubusercontent.com/MeridianOXC/OpenXcom/oxce-plus/src/version.h";
    public string OxcePageUrl { get; set; } = "https://github.com/MeridianOXC/OpenXcom/commits/oxce-plus";
    public string VkApiBase { get; set; } = "https://api.vk.com/method";
    /// <summary>VK service key; a secret, only from the environment (Upstream__VkToken). Without it the group is not checked:
    /// VK answers an anonymous request with a captcha.</summary>
    public string VkToken { get; set; } = "";
    public string VkDomain { get; set; } = "xpz_ru";
    /// <summary>A post counts as a patch release when its text matches.</summary>
    public string VkMatch { get; set; } = "(?i)патч|patch";
}

/// <summary>What a source shows now: <see cref="Value"/> identifies the version, <see cref="Label"/> is for a human.</summary>
public sealed record UpstreamSeen(string Value, string Label, string Url);

/// <summary>Parsers of the three sources; pure functions, so the formats are pinned by tests on real samples.</summary>
public static partial class UpstreamParse
{
    /// <summary>The newest file of a ModDB files feed, identified by its guid ("downloads311212").</summary>
    public static UpstreamSeen? ModDbRss(string xml)
    {
        var doc = XDocument.Parse(xml.Trim());
        var newest = doc.Descendants("item")
            .Select(i => (Id: ((string?)i.Element("guid") ?? (string?)i.Element("link") ?? "").Trim(),
                          Title: ((string?)i.Element("title") ?? "").Trim(),
                          Link: ((string?)i.Element("link") ?? "").Trim(),
                          Date: RfcDate((string?)i.Element("pubDate"))))
            .Where(i => i.Id.Length > 0)
            .OrderByDescending(i => i.Date ?? DateTimeOffset.MinValue)
            .FirstOrDefault();
        if (newest.Id is null) return null;
        var label = newest.Date is { } d ? $"{newest.Title} ({d:yyyy-MM-dd})" : newest.Title;
        return new(newest.Id, label, newest.Link);
    }

    /// <summary>RSS dates are RFC 822 with a "+0000" offset, which the invariant parser does not take without a colon.</summary>
    static DateTimeOffset? RfcDate(string? s)
    {
        if (string.IsNullOrWhiteSpace(s)) return null;
        var t = OffsetRx().Replace(s.Trim(), "$1:$2");
        return DateTimeOffset.TryParseExact(t, "ddd, dd MMM yyyy HH:mm:ss zzz", CultureInfo.InvariantCulture, DateTimeStyles.None, out var d) ? d : null;
    }

    [GeneratedRegex(@"([+-]\d\d)(\d\d)$")]
    private static partial Regex OffsetRx();

    /// <summary>OXCE version from src/version.h: "Extended 8.7.1 (v2026-09-19)". The date part changes with every
    /// build Meridian tags, the number only with a release; both are news for a fork.</summary>
    public static UpstreamSeen? OxceVersion(string header, string pageUrl)
    {
        var shortV = ShortRx().Match(header);
        if (!shortV.Success) return null;
        var git = GitRx().Match(header);
        var label = (shortV.Groups[1].Value + (git.Success ? git.Groups[1].Value : "")).Trim();
        return new(label, label, pageUrl);
    }

    [GeneratedRegex(@"#define\s+OPENXCOM_VERSION_SHORT\s+""([^""]*)""")]
    private static partial Regex ShortRx();

    [GeneratedRegex(@"#define\s+OPENXCOM_VERSION_GIT\s+""([^""]*)""")]
    private static partial Regex GitRx();

    /// <summary>The newest post of a VK wall.get answer whose text matches; null when none does.</summary>
    public static UpstreamSeen? VkWall(string json, Regex match)
    {
        using var doc = JsonDocument.Parse(json);
        if (doc.RootElement.TryGetProperty("error", out var err))
            throw new InvalidOperationException("VK: " + (err.TryGetProperty("error_msg", out var m) ? m.GetString() : "error"));
        (long Id, long Owner, string Text, long Date)? best = null;
        foreach (var it in doc.RootElement.GetProperty("response").GetProperty("items").EnumerateArray())
        {
            var text = it.TryGetProperty("text", out var t) ? t.GetString() ?? "" : "";
            if (!match.IsMatch(text)) continue;
            var id = it.GetProperty("id").GetInt64();
            // a pinned post comes first in the answer whatever its age: the newest is the largest id
            if (best is null || id > best.Value.Id)
                best = (id, it.GetProperty("owner_id").GetInt64(), text, it.TryGetProperty("date", out var dt) ? dt.GetInt64() : 0);
        }
        if (best is not { } b) return null;
        var first = b.Text.Split('\n', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries).FirstOrDefault() ?? "";
        var when = DateTimeOffset.FromUnixTimeSeconds(b.Date).ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
        return new(b.Id.ToString(CultureInfo.InvariantCulture), $"{TelegramNotices.Shorten(first, 120)} ({when})",
            $"https://vk.com/wall{b.Owner}_{b.Id}");
    }
}

/// <summary>
/// Compares each upstream source with what it showed last time and queues a Telegram notice on a change.
/// The first sight of a source is announced once ("watching"), so a working route is visible right away;
/// a source that keeps failing is reported once, at <see cref="UpstreamOptions.FailuresToReport"/> in a row.
/// </summary>
public sealed class UpstreamCheck(PortalDb db, TelegramNotices notices, IHttpClientFactory http, IOptions<UpstreamOptions> options,
    TimeProvider clock, ILogger<UpstreamCheck> log)
{
    public sealed record Source(string Key, string Name, Func<CancellationToken, Task<UpstreamSeen?>> Fetch);

    public IReadOnlyList<Source> Sources()
    {
        var o = options.Value;
        var list = new List<Source>
        {
            new("piratez", "X-Piratez (ModDB)", async ct => UpstreamParse.ModDbRss(await GetAsync(o.ModDbRss, ct))),
            new("oxce", "OXCE (GitHub)", async ct => UpstreamParse.OxceVersion(await GetAsync(o.OxceVersionUrl, ct), o.OxcePageUrl)),
        };
        if (!string.IsNullOrWhiteSpace(o.VkToken))
            list.Add(new("ru-patch", "Русский патч (ВК)", async ct => UpstreamParse.VkWall(await VkWallAsync(ct), new Regex(o.VkMatch))));
        return list;
    }

    /// <summary>Checks every source; returns how many notices were queued.</summary>
    public async Task<int> RunAsync(CancellationToken ct)
    {
        int queued = 0;
        foreach (var s in Sources())
            if (await CheckAsync(s, ct)) queued++;
        return queued;
    }

    async Task<bool> CheckAsync(Source s, CancellationToken ct)
    {
        var state = await db.UpstreamStates.FindAsync([s.Key], ct);
        if (state is null) db.UpstreamStates.Add(state = new UpstreamState { Source = s.Key });
        var now = clock.GetUtcNow();
        state.CheckedAt = now;
        string? text = null;
        try
        {
            var seen = await s.Fetch(ct);
            state.Failures = 0;
            state.LastError = null;
            if (seen is not null && seen.Value != state.Value)
            {
                text = state.Value.Length == 0 ? WatchingText(s.Name, seen) : ChangedText(s.Name, state.Label, seen);
                log.LogInformation("Upstream {Source}: {Old} -> {New}", s.Key, state.Label, seen.Label);
                state.Value = Cut(seen.Value, 256);
                state.Label = Cut(seen.Label, 512);
                state.Url = Cut(seen.Url, 512);
                state.ChangedAt = now;
            }
        }
        catch (Exception e) when (!ct.IsCancellationRequested && e is HttpRequestException or TaskCanceledException
                                  or InvalidOperationException or System.Xml.XmlException or JsonException or KeyNotFoundException)
        {
            var error = e.GetType().Name + ": " + e.Message;
            if (options.Value.VkToken.Length > 0) error = error.Replace(options.Value.VkToken, "***");
            state.Failures++;
            state.LastError = Cut(error, 512);
            log.LogWarning("Upstream {Source}: check {N} failed: {Error}", s.Key, state.Failures, state.LastError);
            if (state.Failures == options.Value.FailuresToReport) text = FailedText(s.Name, state.Failures, state.LastError);
        }
        if (text is not null) await notices.EnqueueAsync(TelegramNotices.UpstreamCategory, text, ct);
        await db.SaveChangesAsync(ct);
        return text is not null;
    }

    async Task<string> GetAsync(string url, CancellationToken ct)
    {
        using var client = http.CreateClient("upstream");
        using var resp = await client.GetAsync(url, ct);
        if (!resp.IsSuccessStatusCode) throw new HttpRequestException($"HTTP {(int)resp.StatusCode} from {new Uri(url).Host}");
        return await resp.Content.ReadAsStringAsync(ct);
    }

    /// <summary>The key goes in the form body, never in the URL: request URLs end up in logs.</summary>
    async Task<string> VkWallAsync(CancellationToken ct)
    {
        var o = options.Value;
        using var client = http.CreateClient("upstream");
        using var body = new FormUrlEncodedContent(new Dictionary<string, string>
        {
            ["domain"] = o.VkDomain, ["count"] = "20", ["v"] = "5.199", ["access_token"] = o.VkToken,
        });
        using var resp = await client.PostAsync($"{o.VkApiBase.TrimEnd('/')}/wall.get", body, ct);
        if (!resp.IsSuccessStatusCode) throw new HttpRequestException($"HTTP {(int)resp.StatusCode} from VK");
        return await resp.Content.ReadAsStringAsync(ct);
    }

    static string Cut(string s, int max) => s.Length > max ? s[..max] : s;

    static string Link(string url, string text) =>
        url.Length == 0 ? "" : $"\n<a href=\"{TelegramNotices.Html(url)}\">{text}</a>";

    public static string WatchingText(string name, UpstreamSeen seen) =>
        $"👀 Слежу за <b>{TelegramNotices.Html(name)}</b>\nсейчас: {TelegramNotices.Html(seen.Label)}{Link(seen.Url, "открыть")}";

    public static string ChangedText(string name, string oldLabel, UpstreamSeen seen) =>
        new StringBuilder()
            .Append("🆕 <b>").Append(TelegramNotices.Html(name)).Append("</b>: новая версия\n")
            .Append(TelegramNotices.Html(seen.Label)).Append('\n')
            .Append("было: ").Append(TelegramNotices.Html(oldLabel))
            .Append(Link(seen.Url, "открыть"))
            .ToString();

    public static string FailedText(string name, int failures, string error) =>
        $"⚠️ Не получается проверить <b>{TelegramNotices.Html(name)}</b> {failures} раз подряд\n{TelegramNotices.Html(TelegramNotices.Shorten(error, 200))}";
}

/// <summary>Runs <see cref="UpstreamCheck"/> once in <see cref="UpstreamOptions.CheckHours"/>, a little after start.</summary>
public sealed class UpstreamWorker(IServiceScopeFactory scopes, IOptions<UpstreamOptions> options, TimeProvider clock,
    ILogger<UpstreamWorker> log) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stop)
    {
        var o = options.Value;
        if (!o.Enabled) { log.LogInformation("Upstream: checks are off"); return; }
        try { await Task.Delay(TimeSpan.FromSeconds(o.StartDelaySeconds), clock, stop); }
        catch (OperationCanceledException) { return; }
        while (!stop.IsCancellationRequested)
        {
            try
            {
                using var scope = scopes.CreateScope();
                var queued = await scope.ServiceProvider.GetRequiredService<UpstreamCheck>().RunAsync(stop);
                log.LogInformation("Upstream: checked, {N} notice(s) queued", queued);
            }
            catch (Exception e) when (e is not OperationCanceledException) { log.LogError(e, "Upstream check failed"); }
            try { await Task.Delay(TimeSpan.FromHours(o.CheckHours), clock, stop); }
            catch (OperationCanceledException) { return; }
        }
    }
}
