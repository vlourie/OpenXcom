using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.AspNetCore.WebUtilities;
using Microsoft.Extensions.Options;

namespace Xp.Portal.Voice;

public sealed class LiveKitOptions
{
    public const string Section = "LiveKit";
    /// <summary>What the launcher connects to: the public signalling address, wss://host[:port] (Caddy passes /rtc to LiveKit).</summary>
    public string Url { get; set; } = "";
    /// <summary>Where the site sends moderation commands: http://livekit:7880 in one compose, https://host of the media server otherwise.</summary>
    public string ApiUrl { get; set; } = "";
    public string ApiKey { get; set; } = "";
    /// <summary>The media server's API secret. Lives only in portal.env; the launcher never sees it.</summary>
    public string ApiSecret { get; set; } = "";
    /// <summary>People in one room, the owner included (VOICE_CHAT.md section 3).</summary>
    public int Capacity { get; set; } = 16;
    /// <summary>Life of a pass. One minute: a pass handed out before a ban is worth nothing a minute later.</summary>
    public int PassSeconds { get; set; } = 60;
    /// <summary>
    /// E-mails that get a pass while the media server is the station's probe (<see cref="IsProbeFor"/>):
    /// the closed acceptance. Everybody else hears that the voice server is unavailable.
    /// </summary>
    public string[] Testers { get; set; } = [];
    /// <summary>
    /// The media server on the site's own host is the production one, open to everybody the room lets in
    /// (Vitali 03.10: the station is the voice server of the release). Said in so many words, by
    /// 'station.ps1 voice-open', so that a probe never opens by itself.
    /// </summary>
    public bool Open { get; set; }

    public bool Enabled => Url.Length > 0 && ApiUrl.Length > 0 && ApiKey.Length > 0 && ApiSecret.Length > 0;

    /// <summary>The media server sits on the site's own host and is not <see cref="Open"/>: that is the station's probe, for its testers only.</summary>
    public bool IsProbeFor(string publicUrl) =>
        !Open && Uri.TryCreate(Url, UriKind.Absolute, out var media) && Uri.TryCreate(publicUrl, UriKind.Absolute, out var site)
        && string.Equals(media.Host, site.Host, StringComparison.OrdinalIgnoreCase);
}

/// <summary>
/// LiveKit access tokens: HS256 JWTs signed with the API secret. Written by hand because the format
/// is a dozen fields and a library would bring a second idea of what a token is into the site.
/// </summary>
public sealed class LiveKitTokens(IOptions<LiveKitOptions> options, TimeProvider clock)
{
    /// <summary>
    /// A pass into one room for one person. Listening always; talking only without a restriction;
    /// no room admin ever, and only the microphone may be published.
    /// </summary>
    public string Pass(Guid room, Guid user, string name, bool canPublish)
    {
        var o = options.Value;
        var now = clock.GetUtcNow().ToUnixTimeSeconds();
        var video = new JsonObject
        {
            ["room"] = room.ToString(),
            ["roomJoin"] = true,
            ["canSubscribe"] = true,
            ["canPublish"] = canPublish,
            ["canPublishData"] = false,
            ["canPublishSources"] = new JsonArray("microphone"),
            ["canUpdateOwnMetadata"] = false,
        };
        return Sign(new JsonObject
        {
            ["iss"] = o.ApiKey,
            ["sub"] = user.ToString(),
            ["name"] = name,
            // a little slack before, none after: clocks of two machines may differ by seconds
            ["nbf"] = now - 30,
            ["exp"] = now + o.PassSeconds,
            ["jti"] = Guid.NewGuid().ToString("N"),
            ["video"] = video,
        }, o.ApiSecret);
    }

    /// <summary>The site's own short token for the server API: admin of one room, or of rooms in general.</summary>
    public string Server(Guid? room)
    {
        var o = options.Value;
        var now = clock.GetUtcNow().ToUnixTimeSeconds();
        var video = new JsonObject { ["roomAdmin"] = true, ["roomCreate"] = true, ["roomList"] = true };
        if (room is { } r) video["room"] = r.ToString();
        return Sign(new JsonObject { ["iss"] = o.ApiKey, ["nbf"] = now - 30, ["exp"] = now + 60, ["video"] = video }, o.ApiSecret);
    }

    /// <summary>
    /// Checks the Authorization header of a webhook: a token of our own key, signed with our secret,
    /// not expired, and carrying the SHA-256 of exactly this body.
    /// </summary>
    public bool WebhookValid(string? authorization, ReadOnlySpan<byte> body)
    {
        var o = options.Value;
        if (authorization is null || !o.Enabled) return false;
        var token = authorization.StartsWith("Bearer ", StringComparison.OrdinalIgnoreCase) ? authorization[7..] : authorization;
        if (Verify(token, o.ApiSecret) is not { } claims) return false;
        if (claims["iss"]?.GetValue<string>() != o.ApiKey) return false;
        var now = clock.GetUtcNow().ToUnixTimeSeconds();
        if (claims["exp"] is { } exp && exp.GetValue<long>() < now - 30) return false;
        var want = Convert.ToBase64String(SHA256.HashData(body));
        return claims["sha256"]?.GetValue<string>() is { } got
            && CryptographicOperations.FixedTimeEquals(Encoding.ASCII.GetBytes(got), Encoding.ASCII.GetBytes(want));
    }

    static readonly string Header = WebEncoders.Base64UrlEncode("""{"alg":"HS256","typ":"JWT"}"""u8.ToArray());

    internal static string Sign(JsonObject claims, string secret)
    {
        var head = Header + "." + WebEncoders.Base64UrlEncode(Encoding.UTF8.GetBytes(claims.ToJsonString()));
        var sig = HMACSHA256.HashData(Encoding.UTF8.GetBytes(secret), Encoding.ASCII.GetBytes(head));
        return head + "." + WebEncoders.Base64UrlEncode(sig);
    }

    internal static JsonObject? Verify(string token, string secret)
    {
        var parts = token.Split('.');
        if (parts.Length != 3) return null;
        try
        {
            var header = JsonNode.Parse(WebEncoders.Base64UrlDecode(parts[0]));
            if (header?["alg"]?.GetValue<string>() != "HS256") return null;
            var want = HMACSHA256.HashData(Encoding.UTF8.GetBytes(secret), Encoding.ASCII.GetBytes(parts[0] + "." + parts[1]));
            if (!CryptographicOperations.FixedTimeEquals(want, WebEncoders.Base64UrlDecode(parts[2]))) return null;
            return JsonNode.Parse(WebEncoders.Base64UrlDecode(parts[1])) as JsonObject;
        }
        catch (Exception e) when (e is FormatException or JsonException or InvalidOperationException) { return null; }
    }
}

/// <summary>Someone in a room right now, as the media server sees them.</summary>
public sealed record LivePeer(string Identity, string Name, bool CanPublish, DateTimeOffset? JoinedAt);

public sealed class VoiceServerException(string message) : Exception(message);

/// <summary>What the site needs from the media server. A fake stands in for it in the tests.</summary>
public interface IVoiceServer
{
    bool Enabled { get; }
    /// <summary>Creates the room if it is not there, with its capacity; harmless if it is.</summary>
    Task EnsureRoomAsync(Guid room, int capacity, CancellationToken ct);
    Task<IReadOnlyList<LivePeer>> ParticipantsAsync(Guid room, CancellationToken ct);
    /// <summary>Rooms the server holds open right now, by name.</summary>
    Task<IReadOnlyList<string>> RoomsAsync(CancellationToken ct);
    /// <summary>Disconnects one person. Somebody who is not there counts as done.</summary>
    Task RemoveAsync(Guid room, string identity, CancellationToken ct);
    Task SetPublishAsync(Guid room, string identity, bool canPublish, CancellationToken ct);
    /// <summary>Ends the room for everyone in it.</summary>
    Task CloseRoomAsync(Guid room, CancellationToken ct);
}

/// <summary>LiveKit's RoomService over Twirp (JSON), authorised by a fresh server token per call.</summary>
public sealed class LiveKitServer(IHttpClientFactory http, IOptions<LiveKitOptions> options, LiveKitTokens tokens) : IVoiceServer
{
    public bool Enabled => options.Value.Enabled;

    public Task EnsureRoomAsync(Guid room, int capacity, CancellationToken ct) =>
        CallAsync("CreateRoom", null, new JsonObject
        {
            ["name"] = room.ToString(),
            // an empty room does not hold a media session: it ends five minutes after the last one leaves
            ["emptyTimeout"] = 300,
            ["departureTimeout"] = 20,
            ["maxParticipants"] = capacity,
        }, ct);

    public async Task<IReadOnlyList<LivePeer>> ParticipantsAsync(Guid room, CancellationToken ct)
    {
        var answer = await CallAsync("ListParticipants", room, new JsonObject { ["room"] = room.ToString() }, ct);
        var list = new List<LivePeer>();
        if (answer?["participants"] is not JsonArray all) return list;
        foreach (var p in all.OfType<JsonObject>())
        {
            var identity = p["identity"]?.GetValue<string>() ?? "";
            var publish = p["permission"]?["canPublish"]?.GetValue<bool>() ?? p["permission"]?["can_publish"]?.GetValue<bool>() ?? false;
            DateTimeOffset? joined = long.TryParse(p["joinedAt"]?.ToString() ?? p["joined_at"]?.ToString(), out var s) ? DateTimeOffset.FromUnixTimeSeconds(s) : null;
            list.Add(new LivePeer(identity, p["name"]?.GetValue<string>() ?? "", publish, joined));
        }
        return list;
    }

    public async Task<IReadOnlyList<string>> RoomsAsync(CancellationToken ct)
    {
        var answer = await CallAsync("ListRooms", null, new JsonObject(), ct);
        return answer?["rooms"] is JsonArray all
            ? all.OfType<JsonObject>().Select(r => r["name"]?.GetValue<string>() ?? "").Where(n => n.Length > 0).ToList()
            : [];
    }

    public Task RemoveAsync(Guid room, string identity, CancellationToken ct) =>
        CallAsync("RemoveParticipant", room, new JsonObject { ["room"] = room.ToString(), ["identity"] = identity }, ct);

    public Task SetPublishAsync(Guid room, string identity, bool canPublish, CancellationToken ct) =>
        // the permission is replaced whole, so it is written whole: the same shape as a pass
        CallAsync("UpdateParticipant", room, new JsonObject
        {
            ["room"] = room.ToString(),
            ["identity"] = identity,
            ["permission"] = new JsonObject
            {
                ["canSubscribe"] = true,
                ["canPublish"] = canPublish,
                ["canPublishData"] = false,
                ["canPublishSources"] = new JsonArray("MICROPHONE"),
            },
        }, ct);

    public Task CloseRoomAsync(Guid room, CancellationToken ct) =>
        CallAsync("DeleteRoom", room, new JsonObject { ["room"] = room.ToString() }, ct);

    async Task<JsonObject?> CallAsync(string method, Guid? room, JsonObject body, CancellationToken ct)
    {
        var o = options.Value;
        if (!o.Enabled) throw new VoiceServerException("the media server is not configured (LiveKit:*)");
        var client = http.CreateClient("livekit");
        using var req = new HttpRequestMessage(HttpMethod.Post, $"{o.ApiUrl.TrimEnd('/')}/twirp/livekit.RoomService/{method}")
        {
            Content = new StringContent(body.ToJsonString(), Encoding.UTF8, "application/json"),
        };
        req.Headers.Authorization = new AuthenticationHeaderValue("Bearer", tokens.Server(room));
        HttpResponseMessage resp;
        try { resp = await client.SendAsync(req, ct); }
        catch (HttpRequestException e) { throw new VoiceServerException($"{method}: {e.Message}"); }
        catch (TaskCanceledException) when (!ct.IsCancellationRequested) { throw new VoiceServerException($"{method}: timed out"); }
        using (resp)
        {
            var text = await resp.Content.ReadAsStringAsync(ct);
            if (resp.IsSuccessStatusCode) return text.Length > 0 ? JsonNode.Parse(text) as JsonObject : null;
            // nobody there, or no such room: for removing and muting that is the goal already reached
            if (resp.StatusCode == System.Net.HttpStatusCode.NotFound || text.Contains("\"not_found\"")) return null;
            throw new VoiceServerException($"{method}: HTTP {(int)resp.StatusCode} {(text.Length > 200 ? text[..200] : text)}");
        }
    }
}
