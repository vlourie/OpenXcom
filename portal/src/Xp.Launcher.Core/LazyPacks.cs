using System.Net;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using Xp.Manifest;

namespace Xp.Launcher.Core;

/// <summary>A pack the site made for this update; its hash comes from the site, the blobs in it are checked against the signed manifest.</summary>
public sealed record LazyPack(string Key, long Size, string Sha256, int Blobs, long Raw);

/// <summary>What the site said: a pack, or why there is none (the files then come one by one).</summary>
public sealed record LazyAnswer(LazyPack? Pack, string Note);

/// <summary>
/// Asks the site to pack the update from the installed release (POST /api/v1/packs), for a release too old to have
/// a pack in its manifest. The site makes it once and keeps it: the first player waits while it is made, the rest
/// get it at once. Never throws but for a cancel: any trouble is an answer without a pack.
/// </summary>
public sealed class LazyPacks(HttpClient http, Uri portal)
{
    /// <summary>How long the player waits for the site to make the pack before the files come one by one.</summary>
    public TimeSpan MaxWait { get; init; } = TimeSpan.FromMinutes(3);
    public Func<TimeSpan, CancellationToken, Task> Delay { get; init; } = Task.Delay;
    const int MaxAnswerBytes = 4096;

    readonly Uri _api = new(portal.AbsoluteUri.EndsWith('/') ? portal : new Uri(portal.AbsoluteUri + "/"), "api/v1/packs");

    /// <summary>The site of the settings; none set or not a web address - no packs from the site.</summary>
    public static LazyPacks? For(HttpClient http, string? portalUrl) =>
        Uri.TryCreate(portalUrl, UriKind.Absolute, out var u) && u.Scheme is "https" or "http" ? new LazyPacks(http, u) : null;

    public static string Body(string channel, string to, string from, IEnumerable<string> art)
    {
        using var buf = new MemoryStream();
        using (var w = new Utf8JsonWriter(buf))
        {
            w.WriteStartObject();
            w.WriteString("channel", channel);
            w.WriteString("to", to);
            w.WriteString("from", from);
            w.WriteStartArray("art");
            foreach (var a in art.Distinct(StringComparer.Ordinal).Order(StringComparer.Ordinal)) w.WriteStringValue(a);
            w.WriteEndArray();
            w.WriteEndObject();
        }
        return Encoding.UTF8.GetString(buf.ToArray());
    }

    /// <param name="waiting">Called each time the site says it is still making the pack.</param>
    public async Task<LazyAnswer> AskAsync(string channel, string to, string from, IEnumerable<string> art, Action? waiting, CancellationToken ct)
    {
        var body = Body(channel, to, from, art);
        var waited = TimeSpan.Zero;
        try
        {
            while (true)
            {
                using var content = new StringContent(body, Encoding.UTF8, "application/json");
                using var resp = await http.PostAsync(_api, content, ct);
                switch (resp.StatusCode)
                {
                    case HttpStatusCode.OK:
                        return Offer(await resp.Content.ReadAsByteArrayAsync(ct));
                    case HttpStatusCode.Accepted:
                        var wait = Clamp(resp.Headers.RetryAfter);
                        if (waited + wait > MaxWait) return new LazyAnswer(null, $"the site did not make it in {MaxWait.TotalSeconds:0} s");
                        waiting?.Invoke();
                        await Delay(wait, ct);
                        waited += wait;
                        continue;
                    case HttpStatusCode.NoContent:
                        return new LazyAnswer(null, "the site has nothing to pack");
                    default:
                        return new LazyAnswer(null, $"the site answered {(int)resp.StatusCode}");
                }
            }
        }
        catch (Exception e) when (e is HttpRequestException or IOException or JsonException or TaskCanceledException && !ct.IsCancellationRequested)
        {
            return new LazyAnswer(null, e.Message);
        }
    }

    static TimeSpan Clamp(RetryConditionHeaderValue? h) =>
        TimeSpan.FromSeconds(Math.Clamp(h?.Delta?.TotalSeconds ?? 5, 1, 30));

    static LazyAnswer Offer(byte[] json)
    {
        if (json.Length > MaxAnswerBytes) return new LazyAnswer(null, "the site's answer is too long");
        // read by hand, not by reflection: the launcher is AOT-compiled
        using var doc = JsonDocument.Parse(json);
        var o = doc.RootElement;
        string Str(string name) => o.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString()! : "";
        long Num(string name) => o.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.Number && v.TryGetInt64(out var n) ? n : 0;
        if (o.ValueKind != JsonValueKind.Object) return new LazyAnswer(null, "the site's answer is not a pack");
        var p = new LazyPack(Str("key"), Num("size"), Str("sha256"), (int)Math.Clamp(Num("blobs"), 0, int.MaxValue), Num("raw"));
        // the key becomes a file name in a URL: 32 hex, nothing else
        if (p.Key is not { Length: 32 } || !p.Key.All(char.IsAsciiHexDigitLower) || !Hashing.IsSha256Hex(p.Sha256) || p.Size <= 0 || p.Blobs <= 0)
            return new LazyAnswer(null, "the site's answer is not a pack");
        return new LazyAnswer(p, "");
    }
}
