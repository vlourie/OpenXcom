using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;

namespace Xp.Launcher.Core;

/// <summary>
/// The anonymous count on the site's home page: how many launchers are installed, how many hours were played
/// through them, how many play right now. A launcher is a random number made once on its machine - no name, no
/// account, no address. It says "playing" or "not playing" when that changes and every few minutes while a game
/// runs (POST /api/v1/stats/ping); the site adds up the time between the "playing" words. Off in the settings.
/// </summary>
public static class LauncherStats
{
    /// <summary>While a game runs; the site counts a launcher as playing for 11 minutes after its last word.</summary>
    public static readonly TimeSpan Every = TimeSpan.FromMinutes(5);

    public static string NewInstallId() => Guid.NewGuid().ToString("N");

    public static bool IsInstallId(string? id) =>
        id is { Length: 32 } && id.All(c => c is >= '0' and <= '9' or >= 'a' and <= 'f');

    public static byte[] Body(string install, bool playing, string launcher, string? game)
    {
        using var buf = new MemoryStream();
        using (var w = new Utf8JsonWriter(buf))
        {
            w.WriteStartObject();
            w.WriteString("install", install);
            w.WriteBoolean("playing", playing);
            w.WriteString("launcher", launcher);
            w.WriteString("game", game ?? "");
            w.WriteEndObject();
        }
        return buf.ToArray();
    }

    /// <summary>One word to the site. A failure is the caller's to swallow: the count is not worth a message.</summary>
    public static async Task PingAsync(HttpClient http, Uri portal, string install, bool playing, string launcher, string? game, CancellationToken ct)
    {
        var baseUri = portal.AbsoluteUri.EndsWith('/') ? portal : new Uri(portal.AbsoluteUri + "/");
        using var content = new ByteArrayContent(Body(install, playing, launcher, game));
        content.Headers.ContentType = new MediaTypeHeaderValue("application/json") { CharSet = Encoding.UTF8.WebName };
        using var resp = await http.PostAsync(new Uri(baseUri, "api/v1/stats/ping"), content, ct);
        resp.EnsureSuccessStatusCode();
    }
}
