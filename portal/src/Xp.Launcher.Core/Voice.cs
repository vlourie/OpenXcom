using System.Net;
using System.Net.Http.Json;
using System.Text.Json.Serialization;

namespace Xp.Launcher.Core;

// The voice half of the portal API (docs/portal/VOICE_CHAT.md §7, portal/src/Xp.Portal/Voice/VoiceApi.cs).
// Every call goes under the launcher's own device key: the site takes no changes through its cookie.

public sealed record VoicePerson(Guid Id, string Name);

/// <summary>A room as this person sees it. State is their standing there: ok, room_closed, account_banned,
/// banned, invite_revoked, not_friends, no_access; Status is the room's own: open or closed.</summary>
public sealed record VoiceRoom(string PublicId, string Title, VoicePerson Owner, bool Mine, string Status, string State,
    bool InviteDeclined, int Capacity, DateTimeOffset CreatedAt)
{
    /// <summary>Whether "Join" is worth pressing: the site still checks everything when it gives the pass.</summary>
    public bool CanJoin => State == "ok" && Status == "open";
}

public sealed record VoiceRooms(List<VoiceRoom> Owned, List<VoiceRoom> Invited);

/// <summary>One person the owner invited or banned. Invite: active, declined, revoked or none.</summary>
public sealed record VoiceMember(VoicePerson Person, string Invite, bool Banned, bool Restricted, bool Friend);

/// <summary>Members - the owner only, null for everybody else.</summary>
public sealed record VoiceRoomView(VoiceRoom Room, List<VoiceMember>? Members, bool ClosedByStaff, string? ClosedReason);

/// <summary>One entry into a room: where the media server is and a pass that lives about a minute.</summary>
public sealed record VoicePassView(string Url, string Token, string Room, string RoomName, string Identity, string Name,
    bool CanPublish, int ExpiresIn);

/// <summary>Who is in the room now. Person.Id is the LiveKit identity of that participant.</summary>
public sealed record VoiceLive(VoicePerson Person, bool CanPublish, DateTimeOffset? JoinedAt);

public sealed record VoiceFriend(Guid Id, string Name, DateTimeOffset Since);
public sealed record VoiceFriendRequest(Guid Id, VoicePerson Person, DateTimeOffset At);
public sealed record VoiceFriends(List<VoiceFriend> Friends, int FriendsTotal, List<VoiceFriendRequest> Incoming,
    List<VoiceFriendRequest> Outgoing, List<VoicePerson> Blocked);

public sealed record VoiceComplaint(long Number, string DisplayNumber);

/// <summary>The site's limits on what a person types (Xp.Portal VoiceLimits): longer is refused there.</summary>
public static class VoiceRules
{
    public const int TitleMax = 80;
    public const int ReasonMax = 500;
    public const int ComplaintMax = 2000;
}

internal sealed record VoiceTitleBody(string Title);
internal sealed record VoiceReasonBody(string? Reason);
internal sealed record VoiceInviteBody(Guid User);
internal sealed record VoiceSpeakingBody(bool Allowed, string? Reason);
internal sealed record VoiceWhoBody(string Who);
internal sealed record VoiceResultBody(string Result);
internal sealed record VoiceComplaintBody(Guid User, string Text);

/// <summary>
/// The site will not give a pass and asking again will not change that: no_access, banned, room_closed,
/// account_banned, invite_revoked, not_friends, device_unknown (the launcher was unlinked), room_full.
/// A network failure, 429 or 503 is a <see cref="HttpRequestException"/> or a transient
/// <see cref="PortalException"/> instead - the voice session asks again by itself.
/// </summary>
public sealed class VoicePassRefusedException(string code, int status) : Exception("voice pass refused: " + code)
{
    public string Code { get; } = code;
    public int Status { get; } = status;
}

public sealed partial class PortalClient
{
    const string Rooms = "api/v1/voice/rooms";

    static string RoomPath(string publicId, string? tail = null) =>
        $"{Rooms}/{Uri.EscapeDataString(publicId)}" + (tail is null ? "" : "/" + tail);

    HttpRequestMessage DeviceRequest(HttpMethod method, string path, string deviceToken, HttpContent? content = null)
    {
        var msg = new HttpRequestMessage(method, new Uri(BaseUri, path)) { Content = content };
        msg.Headers.Add(DeviceTokenHeader, deviceToken);
        return msg;
    }

    async Task<T> AskAsync<T>(HttpRequestMessage msg, System.Text.Json.Serialization.Metadata.JsonTypeInfo<T> type, CancellationToken ct)
    {
        using (msg)
        {
            using var resp = await Http.SendAsync(msg, ct);
            await ThrowIfFailedAsync(resp, ct);
            return await resp.Content.ReadFromJsonAsync(type, ct)
                   ?? throw new PortalException((int)resp.StatusCode, "bad_response", "empty answer");
        }
    }

    async Task DoAsync(HttpRequestMessage msg, CancellationToken ct)
    {
        using (msg)
        {
            using var resp = await Http.SendAsync(msg, ct);
            await ThrowIfFailedAsync(resp, ct);
        }
    }

    /// <summary>The rooms this person owns and the ones they are invited to.</summary>
    public Task<VoiceRooms> VoiceRoomsAsync(string deviceToken, CancellationToken ct) =>
        AskAsync(DeviceRequest(HttpMethod.Get, Rooms, deviceToken), VoiceJson.Default.VoiceRooms, ct);

    /// <summary>A new room of one's own (limit_rooms at the fifth one).</summary>
    public Task<VoiceRoom> CreateVoiceRoomAsync(string deviceToken, string title, CancellationToken ct) =>
        AskAsync(DeviceRequest(HttpMethod.Post, Rooms, deviceToken, JsonContent.Create(new VoiceTitleBody(title), VoiceJson.Default.VoiceTitleBody)),
            VoiceJson.Default.VoiceRoom, ct);

    public Task<VoiceRoomView> VoiceRoomAsync(string deviceToken, string publicId, CancellationToken ct) =>
        AskAsync(DeviceRequest(HttpMethod.Get, RoomPath(publicId), deviceToken), VoiceJson.Default.VoiceRoomView, ct);

    /// <summary>
    /// A pass into the room, asked for afresh at every entry and never kept: the site checks the ban, the
    /// invite and the right to speak each time it gives one (VOICE_CHAT.md §3, §7).
    /// </summary>
    /// <exception cref="VoicePassRefusedException">the site refused, and will refuse again</exception>
    public async Task<VoicePassView> VoicePassAsync(string deviceToken, string publicId, CancellationToken ct)
    {
        try
        {
            return await AskAsync(DeviceRequest(HttpMethod.Post, RoomPath(publicId, "pass"), deviceToken), VoiceJson.Default.VoicePassView, ct);
        }
        catch (PortalException e) when (!e.Transient)
        {
            // 401 device_unknown, 403 banned & co., 404 no_access, 409 room_full: none of them goes away by asking again
            throw new VoicePassRefusedException(e.Status == (int)HttpStatusCode.Unauthorized && e.Code.StartsWith("http_") ? "device_unknown" : e.Code, e.Status);
        }
    }

    public Task<List<VoiceLive>> VoiceLiveAsync(string deviceToken, string publicId, CancellationToken ct) =>
        AskAsync(DeviceRequest(HttpMethod.Get, RoomPath(publicId, "live"), deviceToken), VoiceJson.Default.ListVoiceLive, ct);

    /// <summary>Turns an invite down: the room leaves the list, the owner may invite again.</summary>
    public Task DeclineVoiceInviteAsync(string deviceToken, string publicId, CancellationToken ct) =>
        DoAsync(DeviceRequest(HttpMethod.Post, RoomPath(publicId, "decline"), deviceToken), ct);

    // ---------------------------------------------------------------- the owner

    public Task InviteToVoiceRoomAsync(string deviceToken, string publicId, Guid user, CancellationToken ct) =>
        DoAsync(DeviceRequest(HttpMethod.Post, RoomPath(publicId, "invites"), deviceToken,
            JsonContent.Create(new VoiceInviteBody(user), VoiceJson.Default.VoiceInviteBody)), ct);

    public Task RevokeVoiceInviteAsync(string deviceToken, string publicId, Guid user, string? reason, CancellationToken ct) =>
        DoAsync(DeviceRequest(HttpMethod.Delete, RoomPath(publicId, $"invites/{user}") +
            (string.IsNullOrWhiteSpace(reason) ? "" : "?reason=" + Uri.EscapeDataString(reason.Trim())), deviceToken), ct);

    /// <summary>Out of the room now and the invite revoked; may be invited again.</summary>
    public Task KickFromVoiceRoomAsync(string deviceToken, string publicId, Guid user, string? reason, CancellationToken ct) =>
        DoAsync(DeviceRequest(HttpMethod.Post, RoomPath(publicId, $"members/{user}/kick"), deviceToken,
            JsonContent.Create(new VoiceReasonBody(Blank(reason)), VoiceJson.Default.VoiceReasonBody)), ct);

    /// <summary>Out of the room now and kept out until let back in.</summary>
    public Task BanFromVoiceRoomAsync(string deviceToken, string publicId, Guid user, string? reason, CancellationToken ct) =>
        DoAsync(DeviceRequest(HttpMethod.Post, RoomPath(publicId, $"members/{user}/ban"), deviceToken,
            JsonContent.Create(new VoiceReasonBody(Blank(reason)), VoiceJson.Default.VoiceReasonBody)), ct);

    public Task UnbanInVoiceRoomAsync(string deviceToken, string publicId, Guid user, CancellationToken ct) =>
        DoAsync(DeviceRequest(HttpMethod.Delete, RoomPath(publicId, $"bans/{user}"), deviceToken), ct);

    /// <summary>Takes the right to speak away (allowed false) or gives it back.</summary>
    public Task SetVoiceSpeakingAsync(string deviceToken, string publicId, Guid user, bool allowed, string? reason, CancellationToken ct) =>
        DoAsync(DeviceRequest(HttpMethod.Put, RoomPath(publicId, $"members/{user}/speaking"), deviceToken,
            JsonContent.Create(new VoiceSpeakingBody(allowed, Blank(reason)), VoiceJson.Default.VoiceSpeakingBody)), ct);

    /// <summary>A complaint about somebody in the room: a ticket of the voice category on the site.</summary>
    public Task<VoiceComplaint> ComplainInVoiceRoomAsync(string deviceToken, string publicId, Guid user, string text, CancellationToken ct) =>
        AskAsync(DeviceRequest(HttpMethod.Post, RoomPath(publicId, "complaints"), deviceToken,
            JsonContent.Create(new VoiceComplaintBody(user, text.Trim()), VoiceJson.Default.VoiceComplaintBody)), VoiceJson.Default.VoiceComplaint, ct);

    // ---------------------------------------------------------------- friends

    public Task<VoiceFriends> FriendsAsync(string deviceToken, int page, CancellationToken ct) =>
        AskAsync(DeviceRequest(HttpMethod.Get, $"api/v1/friends?page={Math.Max(1, page)}", deviceToken), VoiceJson.Default.VoiceFriends, ct);

    /// <summary>A friend request by the profile name (or a profile link): "sent", or "accepted" when the
    /// other side had already asked.</summary>
    public async Task<string> RequestFriendAsync(string deviceToken, string who, CancellationToken ct) =>
        (await AskAsync(DeviceRequest(HttpMethod.Post, "api/v1/friends/requests", deviceToken,
            JsonContent.Create(new VoiceWhoBody(who.Trim()), VoiceJson.Default.VoiceWhoBody)), VoiceJson.Default.VoiceResultBody, ct)).Result;

    public Task AcceptFriendAsync(string deviceToken, Guid request, CancellationToken ct) =>
        DoAsync(DeviceRequest(HttpMethod.Post, $"api/v1/friends/requests/{request}/accept", deviceToken), ct);

    public Task DeclineFriendAsync(string deviceToken, Guid request, CancellationToken ct) =>
        DoAsync(DeviceRequest(HttpMethod.Post, $"api/v1/friends/requests/{request}/decline", deviceToken), ct);

    static string? Blank(string? s) => string.IsNullOrWhiteSpace(s) ? null : s.Trim();
}

/// <summary>
/// xpiratez://voice/&lt;publicId&gt; - the "Open in the launcher" link of a room page. It names a room and
/// nothing more: whether the person may come in, the site decides when it gives the pass.
/// </summary>
public static class VoiceLink
{
    public const string Scheme = "xpiratez";

    /// <summary>The room a link names, or null for anything else (another host, a path with more in it,
    /// characters a room id never has).</summary>
    public static string? Parse(string? arg)
    {
        if (string.IsNullOrWhiteSpace(arg)) return null;
        if (!Uri.TryCreate(arg.Trim(), UriKind.Absolute, out var u)) return null;
        if (!u.Scheme.Equals(Scheme, StringComparison.OrdinalIgnoreCase) || !u.Host.Equals("voice", StringComparison.OrdinalIgnoreCase)) return null;
        var id = u.AbsolutePath.Trim('/');
        return IsRoomId(id) ? id.ToLowerInvariant() : null;
    }

    /// <summary>Looks like a room's public id: letters and digits only, nothing a path or a query is made of.</summary>
    public static bool IsRoomId(string? id) => id is { Length: > 0 and <= 32 } && id.All(char.IsAsciiLetterOrDigit);

    /// <summary>The first link among the command line arguments (the browser passes it as the only one).</summary>
    public static string? Find(IEnumerable<string> args) => args.Select(Parse).FirstOrDefault(id => id is not null);

    public static string For(string publicId) => $"{Scheme}://voice/{publicId}";
}

[JsonSourceGenerationOptions(PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase, PropertyNameCaseInsensitive = true)]
[JsonSerializable(typeof(VoiceRooms))]
[JsonSerializable(typeof(VoiceRoom))]
[JsonSerializable(typeof(VoiceRoomView))]
[JsonSerializable(typeof(VoicePassView))]
[JsonSerializable(typeof(List<VoiceLive>))]
[JsonSerializable(typeof(VoiceFriends))]
[JsonSerializable(typeof(VoiceComplaint))]
[JsonSerializable(typeof(VoiceTitleBody))]
[JsonSerializable(typeof(VoiceReasonBody))]
[JsonSerializable(typeof(VoiceInviteBody))]
[JsonSerializable(typeof(VoiceSpeakingBody))]
[JsonSerializable(typeof(VoiceWhoBody))]
[JsonSerializable(typeof(VoiceResultBody))]
[JsonSerializable(typeof(VoiceComplaintBody))]
internal sealed partial class VoiceJson : JsonSerializerContext
{
}
