using System.Text.Json;

namespace Xp.Launcher.Core;

/// <summary>One way to support the authors, as the site lists it. The title and the note are already in the player's language.</summary>
public sealed record SupportItem(string Title, string Note, string Url);

/// <summary>
/// The list "Support" shows besides its built-in buttons, read from the site's /support.json (portal wwwroot): changing
/// it needs a site deployment, not a launcher release. A player who cannot reach one payment service gets others, and
/// a dead service can be taken off the built-in buttons with "hide" without waiting for a new launcher.
/// <code>
/// { "version": 1,
///   "hide": ["hd"],
///   "items": [ { "title": {"ru": "...", "en": "..."}, "note": {"ru": "...", "en": "..."}, "url": "https://..." } ] }
/// </code>
/// "hide" names built-in buttons: "mod", "hd", "hdPage". "title" and "note" may be a plain string instead of a
/// per-language object; "note" may be absent. An item without an https address, without a title, past the 12th - is
/// skipped, so a slip in the file cannot put a broken or foreign-scheme link in front of a player.
/// </summary>
public sealed class SupportList
{
    public const int MaxItems = 12;
    public const string File = "support.json";
    public static readonly string[] BuiltIn = ["mod", "hd", "hdPage"];

    public IReadOnlyList<SupportItem> Items { get; private init; } = [];
    public IReadOnlySet<string> Hidden { get; private init; } = new HashSet<string>();

    public static SupportList Empty { get; } = new();

    /// <summary>The file's content for a language; null when it is not a usable list at all (the caller keeps what it had).</summary>
    public static SupportList? Parse(ReadOnlyMemory<byte> json, string language)
    {
        try
        {
            using var doc = JsonDocument.Parse(json, new JsonDocumentOptions { AllowTrailingCommas = true, CommentHandling = JsonCommentHandling.Skip });
            var root = doc.RootElement;
            if (root.ValueKind != JsonValueKind.Object) return null;

            var hidden = new HashSet<string>(StringComparer.Ordinal);
            if (root.TryGetProperty("hide", out var hide) && hide.ValueKind == JsonValueKind.Array)
                foreach (var h in hide.EnumerateArray())
                    if (h.ValueKind == JsonValueKind.String && h.GetString() is { } id && Array.IndexOf(BuiltIn, id) >= 0) hidden.Add(id);

            var items = new List<SupportItem>();
            if (root.TryGetProperty("items", out var arr) && arr.ValueKind == JsonValueKind.Array)
            {
                foreach (var it in arr.EnumerateArray())
                {
                    if (items.Count >= MaxItems) break;
                    if (it.ValueKind != JsonValueKind.Object) continue;
                    var url = it.TryGetProperty("url", out var u) && u.ValueKind == JsonValueKind.String ? u.GetString()?.Trim() : null;
                    var title = Localized(it, "title", language);
                    if (string.IsNullOrWhiteSpace(title) || !IsWebAddress(url)) continue;
                    items.Add(new SupportItem(Cap(title, 80), Cap(Localized(it, "note", language) ?? "", 240), url!));
                }
            }
            return new SupportList { Items = items, Hidden = hidden };
        }
        catch (JsonException) { return null; }
    }

    /// <summary>An address that may be opened from here: https with a host, nothing else (no file:, no javascript:, no http:).</summary>
    public static bool IsWebAddress(string? url) =>
        url is { Length: <= 2000 } && Uri.TryCreate(url, UriKind.Absolute, out var u) && u.Scheme == Uri.UriSchemeHttps && u.Host.Length > 0 && u.UserInfo.Length == 0;

    static string? Localized(JsonElement item, string name, string language)
    {
        if (!item.TryGetProperty(name, out var v)) return null;
        if (v.ValueKind == JsonValueKind.String) return v.GetString()?.Trim();
        if (v.ValueKind != JsonValueKind.Object) return null;
        foreach (var lang in new[] { language, language == "ru" ? "en" : "ru" })
            if (v.TryGetProperty(lang, out var s) && s.ValueKind == JsonValueKind.String && !string.IsNullOrWhiteSpace(s.GetString())) return s.GetString()!.Trim();
        return null;
    }

    static string Cap(string s, int max) => s.Length <= max ? s : s[..max];

    /// <summary>The list from the site; the answer is kept at <paramref name="cachePath"/> for the next start without a network.</summary>
    public static async Task<SupportList?> FetchAsync(HttpClient http, Uri portal, string language, string? cachePath, CancellationToken ct)
    {
        var baseUri = portal.AbsoluteUri.EndsWith('/') ? portal : new Uri(portal.AbsoluteUri + "/");
        using var resp = await http.GetAsync(new Uri(baseUri, File), ct);
        if (!resp.IsSuccessStatusCode) return null;
        var bytes = await resp.Content.ReadAsByteArrayAsync(ct);
        if (bytes.Length > 64 * 1024) return null;
        var list = Parse(bytes, language);
        if (list is not null && cachePath is not null)
        {
            try { FileUtil.WriteAtomic(cachePath, bytes); }
            catch (Exception e) when (e is IOException or UnauthorizedAccessException) { }
        }
        return list;
    }

    /// <summary>What the last fetch kept; null - none or unreadable.</summary>
    public static SupportList? Cached(string cachePath, string language)
    {
        try { return System.IO.File.Exists(cachePath) ? Parse(System.IO.File.ReadAllBytes(cachePath), language) : null; }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { return null; }
    }
}
