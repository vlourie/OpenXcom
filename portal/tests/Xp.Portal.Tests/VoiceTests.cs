using System.Net;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Xp.Portal.Auth;
using Xp.Portal.Data;
using Xp.Portal.Voice;

namespace Xp.Portal.Tests;

/// <summary>The portal with a media server that is only a list in memory: what it was told, and who is "inside".</summary>
public sealed class VoiceFactory : PortalFactory
{
    public const string Key = "APItestkey";
    public static readonly string Secret = new('k', 48);
    public FakeVoiceServer Voice { get; } = new();

    public VoiceFactory()
    {
        Settings["LiveKit:Url"] = "wss://voice.test";
        Settings["LiveKit:ApiUrl"] = "https://voice.test";
        Settings["LiveKit:ApiKey"] = Key;
        Settings["LiveKit:ApiSecret"] = Secret;
        Settings["RateLimits:VoicePer10Min"] = "1000";
        Settings["RateLimits:VoicePassPerMin"] = "1000";
    }

    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        base.ConfigureWebHost(builder);
        builder.ConfigureTestServices(s => s.AddSingleton<IVoiceServer>(Voice));
    }
}

public sealed class FakeVoiceServer : IVoiceServer
{
    public bool Enabled => true;
    public volatile bool Down;
    public Dictionary<Guid, List<LivePeer>> Rooms { get; } = new();
    readonly List<string> _calls = new();

    public IReadOnlyList<string> Calls { get { lock (_calls) return _calls.ToList(); } }
    public bool Called(string call) => Calls.Contains(call);

    void Call(string what)
    {
        if (Down) throw new VoiceServerException("connection refused");
        lock (_calls) _calls.Add(what);
    }

    public void Inside(Guid room, params LivePeer[] peers)
    {
        lock (Rooms) Rooms[room] = peers.ToList();
    }

    public Task EnsureRoomAsync(Guid room, int capacity, CancellationToken ct)
    {
        Call($"ensure {room} {capacity}");
        lock (Rooms) Rooms.TryAdd(room, new());
        return Task.CompletedTask;
    }

    public Task<IReadOnlyList<LivePeer>> ParticipantsAsync(Guid room, CancellationToken ct)
    {
        Call($"list {room}");
        lock (Rooms) return Task.FromResult<IReadOnlyList<LivePeer>>(Rooms.TryGetValue(room, out var l) ? l.ToList() : []);
    }

    public Task<IReadOnlyList<string>> RoomsAsync(CancellationToken ct)
    {
        Call("rooms");
        lock (Rooms) return Task.FromResult<IReadOnlyList<string>>(Rooms.Keys.Select(k => k.ToString()).ToList());
    }

    public Task RemoveAsync(Guid room, string identity, CancellationToken ct)
    {
        Call($"remove {room} {identity}");
        lock (Rooms) if (Rooms.TryGetValue(room, out var l)) l.RemoveAll(p => p.Identity == identity);
        return Task.CompletedTask;
    }

    public Task SetPublishAsync(Guid room, string identity, bool canPublish, CancellationToken ct)
    {
        Call($"publish {room} {identity} {canPublish}");
        return Task.CompletedTask;
    }

    public Task CloseRoomAsync(Guid room, CancellationToken ct)
    {
        Call($"close {room}");
        lock (Rooms) Rooms.Remove(room);
        return Task.CompletedTask;
    }
}

/// <summary>
/// Friends, rooms and passes (docs/portal/VOICE_CHAT.md): who may get into which room, that every
/// refusal is decided by the site, and that a decision reaches the media server even when it is down.
/// </summary>
public sealed partial class VoiceTests(VoiceFactory f) : IClassFixture<VoiceFactory>
{
    const string Password = "Long-enough-passw0rd!";

    async Task<Guid> UserAsync(string name, string? password = null, string? email = null) =>
        await f.ScopedAsync(async sp =>
        {
            var users = sp.GetRequiredService<UserManager<PortalUser>>();
            email ??= $"voice-{Guid.NewGuid():N}@x.test";
            var u = new PortalUser { UserName = email, Email = email, EmailConfirmed = true, DisplayName = name };
            var r = password is null ? await users.CreateAsync(u) : await users.CreateAsync(u, password);
            Assert.True(r.Succeeded, string.Join(", ", r.Errors.Select(e => e.Description)));
            return u.Id;
        });

    Task V(Func<VoiceService, Task> act) => f.ScopedAsync(async sp => { await act(sp.GetRequiredService<VoiceService>()); return 0; });
    Task<T> V<T>(Func<VoiceService, Task<T>> act) => f.ScopedAsync(sp => act(sp.GetRequiredService<VoiceService>()));

    async Task<VoiceException> Refused(Func<VoiceService, Task> act) =>
        await Assert.ThrowsAsync<VoiceException>(() => V(act));

    async Task<(string Code, int Status)> Why(Func<VoiceService, Task> act)
    {
        var e = await Refused(act);
        return (e.Code, e.Status);
    }

    /// <summary>The room's log as "kind:reason" lines, glued here: SQL would turn a missing reason into a missing line.</summary>
    async Task<List<string>> LogAsync(Guid roomId, Guid? user = null)
    {
        var rows = await f.DbAsync(db => db.VoiceEvents.Where(e => e.RoomId == roomId && (user == null || e.UserId == user))
            .Select(e => new { e.Kind, e.Reason }).ToListAsync());
        return rows.Select(r => r.Kind + ":" + r.Reason).ToList();
    }

    async Task FriendsAsync(Guid a, Guid b)
    {
        Assert.Equal("sent", await V(v => v.RequestAsync(a, b, default)));
        Assert.Equal("accepted", await V(v => v.RequestAsync(b, a, default)));
    }

    async Task<(string PublicId, Guid Id)> RoomAsync(Guid owner, string title = "Вечерний рейд")
    {
        var room = await V(v => v.CreateRoomAsync(owner, title, default));
        var id = await f.DbAsync(db => db.VoiceRooms.Where(r => r.PublicId == room.PublicId).Select(r => r.Id).SingleAsync());
        return (room.PublicId, id);
    }

    /// <summary>An owner with a room and one invited friend in it.</summary>
    async Task<(Guid Owner, Guid Guest, string Room, Guid RoomId)> PartyAsync()
    {
        var owner = await UserAsync("Хозяин");
        var guest = await UserAsync("Гость");
        await FriendsAsync(owner, guest);
        var (room, id) = await RoomAsync(owner);
        await V(v => v.InviteAsync(owner, room, guest, default));
        return (owner, guest, room, id);
    }

    static JsonObject Claims(string token) => LiveKitTokens.Verify(token, VoiceFactory.Secret) ?? throw new Xunit.Sdk.XunitException("pass not signed with the API secret");

    [Fact]
    public async Task Friend_requests_meet_in_the_middle_and_a_refusal_looks_like_a_block()
    {
        var a = await UserAsync("Анна");
        var b = await UserAsync("Борис");
        Assert.Equal("self", (await Refused(v => v.RequestAsync(a, a, default))).Code);
        Assert.Equal("sent", await V(v => v.RequestAsync(a, b, default)));
        Assert.Equal("already_sent", (await Refused(v => v.RequestAsync(a, b, default))).Code);
        // the other side asking back is an answer, not a second request
        Assert.Equal("accepted", await V(v => v.RequestAsync(b, a, default)));
        Assert.Equal("already_friends", (await Refused(v => v.RequestAsync(a, b, default))).Code);
        Assert.Equal(0, await f.DbAsync(db => db.FriendRequests.CountAsync(r => (r.SenderId == a || r.SenderId == b) && r.Status == FriendRequestStatus.Pending)));

        var c = await UserAsync("Вера");
        var d = await UserAsync("Глеб");
        await V(v => v.RequestAsync(d, c, default));
        var req = await V(v => v.FriendsAsync(c, 1, 50, default));
        await V(v => v.DeclineAsync(c, req.Incoming.Single().Id, default));
        var turnedDown = await Refused(v => v.RequestAsync(d, c, default));
        Assert.Equal(("request_refused", 403), (turnedDown.Code, turnedDown.Status));
        f.Clock.Advance(TimeSpan.FromDays(8));
        Assert.Equal("sent", await V(v => v.RequestAsync(d, c, default)));

        var e = await UserAsync("Дина");
        var g = await UserAsync("Ефим");
        await V(v => v.BlockAsync(e, g, default));
        // blocked and turned down read the same to the one asking
        Assert.Equal(("request_refused", 403), await Why(v => v.RequestAsync(g, e, default)));
        Assert.Equal("you_blocked", (await Refused(v => v.RequestAsync(e, g, default))).Code);
    }

    [Fact]
    public async Task Asking_both_ways_at_once_makes_one_friendship()
    {
        for (int i = 0; i < 5; i++)
        {
            var a = await UserAsync("Раз");
            var b = await UserAsync("Два");
            await Task.WhenAll(V(v => v.RequestAsync(a, b, default)), V(v => v.RequestAsync(b, a, default)));
            var (lo, hi) = Friendship.Pair(a, b);
            Assert.Equal(1, await f.DbAsync(db => db.Friendships.CountAsync(x => x.UserLowId == lo && x.UserHighId == hi)));
            Assert.Equal(0, await f.DbAsync(db => db.FriendRequests.CountAsync(r => (r.SenderId == a || r.SenderId == b) && r.Status == FriendRequestStatus.Pending)));
        }
    }

    [Fact]
    public async Task Only_the_owner_and_invited_friends_get_a_pass_and_it_holds_nothing_more()
    {
        var (owner, guest, room, roomId) = await PartyAsync();
        var stranger = await UserAsync("Чужой");
        Assert.Equal(("not_friends", 403), await Why(v => v.InviteAsync(owner, room, stranger, default)));

        var pass = await V(v => v.PassAsync(guest, room, default));
        Assert.Equal("wss://voice.test", pass.Url);
        Assert.True(pass.CanPublish);
        Assert.Equal(60, pass.ExpiresIn);
        Assert.True(f.Voice.Called($"ensure {roomId} 16"));
        var c = Claims(pass.Token);
        Assert.Equal(VoiceFactory.Key, c["iss"]!.GetValue<string>());
        Assert.Equal(guest.ToString(), c["sub"]!.GetValue<string>());
        Assert.Equal(60, c["exp"]!.GetValue<long>() - f.Clock.GetUtcNow().ToUnixTimeSeconds());
        var video = c["video"]!.AsObject();
        Assert.Equal(roomId.ToString(), video["room"]!.GetValue<string>());
        Assert.True(video["roomJoin"]!.GetValue<bool>());
        Assert.True(video["canPublish"]!.GetValue<bool>());
        Assert.False(video["canPublishData"]!.GetValue<bool>());
        Assert.Equal(new[] { "microphone" }, video["canPublishSources"]!.AsArray().Select(s => s!.GetValue<string>()));
        Assert.Null(video["roomAdmin"]);
        Assert.Null(video["roomCreate"]);

        // a stranger, a made-up room and a room that is not theirs: the same answer, nothing to learn from it
        var s1 = await Refused(v => v.PassAsync(stranger, room, default));
        var s2 = await Refused(v => v.PassAsync(stranger, "abcdefghjk", default));
        Assert.Equal(("no_access", 404), (s1.Code, s1.Status));
        Assert.Equal(("no_access", 404), (s2.Code, s2.Status));
        Assert.Equal("no_access", (await Refused(v => v.RoomViewAsync(stranger, room, default))).Code);
        // a guest sees the room, not who else is invited
        Assert.Null((await V(v => v.RoomViewAsync(guest, room, default))).Members);
        Assert.Single((await V(v => v.RoomViewAsync(owner, room, default))).Members!);
        Assert.Equal("owner_only", (await Refused(v => v.KickAsync(guest, room, owner, null, default))).Code);
    }

    [Fact]
    public async Task A_muted_guest_keeps_listening_and_stays_muted_across_reconnects()
    {
        var (owner, guest, room, roomId) = await PartyAsync();
        Assert.Equal("owner_target", (await Refused(v => v.SetSpeakingAsync(owner, room, owner, false, null, default))).Code);
        await V(v => v.SetSpeakingAsync(owner, room, guest, false, "шумит", default));
        Assert.True(f.Voice.Called($"publish {roomId} {guest} False"));
        for (int i = 0; i < 2; i++)
        {
            var pass = await V(v => v.PassAsync(guest, room, default));
            Assert.False(pass.CanPublish);
            Assert.False(Claims(pass.Token)["video"]!["canPublish"]!.GetValue<bool>());
            Assert.True(Claims(pass.Token)["video"]!["canSubscribe"]!.GetValue<bool>());
        }
        await V(v => v.SetSpeakingAsync(owner, room, guest, true, null, default));
        Assert.True(f.Voice.Called($"publish {roomId} {guest} True"));
        Assert.True((await V(v => v.PassAsync(guest, room, default))).CanPublish);
        var log = await LogAsync(roomId);
        Assert.Contains("mute:шумит", log);
        Assert.Contains("unmute:", log);
    }

    [Fact]
    public async Task Kick_and_ban_take_the_person_out_at_once_and_keep_them_out()
    {
        var (owner, guest, room, roomId) = await PartyAsync();
        await V(v => v.KickAsync(owner, room, guest, "хватит", default));
        Assert.True(f.Voice.Called($"remove {roomId} {guest}"));
        Assert.Equal(("invite_revoked", 403), await Why(v => v.PassAsync(guest, room, default)));
        await V(v => v.InviteAsync(owner, room, guest, default));
        await V(v => v.PassAsync(guest, room, default));

        await V(v => v.BanAsync(owner, room, guest, "грубит", default));
        Assert.Equal("banned", (await Refused(v => v.PassAsync(guest, room, default))).Code);
        Assert.Equal("banned_in_room", (await Refused(v => v.InviteAsync(owner, room, guest, default))).Code);
        Assert.Equal("banned", (await V(v => v.RoomsAsync(guest, default))).Invited.Single(r => r.PublicId == room).State);
        await V(v => v.UnbanAsync(owner, room, guest, default));
        await V(v => v.InviteAsync(owner, room, guest, default));
        await V(v => v.PassAsync(guest, room, default));
        var log = await LogAsync(roomId, guest);
        Assert.Contains("kick:хватит", log);
        Assert.Contains("ban:грубит", log);
        Assert.Contains("unban:", log);
    }

    [Fact]
    public async Task Unfriend_and_block_revoke_invites_both_ways()
    {
        var a = await UserAsync("Первый");
        var b = await UserAsync("Второй");
        await FriendsAsync(a, b);
        var (ra, ida) = await RoomAsync(a);
        var (rb, idb) = await RoomAsync(b);
        await V(v => v.InviteAsync(a, ra, b, default));
        await V(v => v.InviteAsync(b, rb, a, default));
        await V(v => v.UnfriendAsync(b, a, default));
        Assert.Equal("invite_revoked", (await Refused(v => v.PassAsync(b, ra, default))).Code);
        Assert.Equal("invite_revoked", (await Refused(v => v.PassAsync(a, rb, default))).Code);
        Assert.True(f.Voice.Called($"remove {ida} {b}"));
        Assert.True(f.Voice.Called($"remove {idb} {a}"));

        var c = await UserAsync("Третий");
        await FriendsAsync(a, c);
        await V(v => v.InviteAsync(a, ra, c, default));
        await V(v => v.BlockAsync(c, a, default));
        Assert.Equal("invite_revoked", (await Refused(v => v.PassAsync(c, ra, default))).Code);
        Assert.Equal("not_friends", (await Refused(v => v.InviteAsync(a, ra, c, default))).Code);
        Assert.Empty((await V(v => v.FriendsAsync(a, 1, 50, default))).Friends);
    }

    [Fact]
    public async Task A_room_closed_by_staff_stays_closed_for_its_owner()
    {
        var (owner, guest, room, roomId) = await PartyAsync();
        var staff = await UserAsync("Модератор");
        Assert.Equal("reason_required", (await Refused(v => v.CloseRoomAsync(staff, room, " ", staff: true, default))).Code);
        await V(v => v.CloseRoomAsync(staff, room, "жалобы", staff: true, default));
        Assert.True(f.Voice.Called($"close {roomId}"));
        Assert.Equal("room_closed", (await Refused(v => v.PassAsync(owner, room, default))).Code);
        Assert.Equal("room_closed", (await Refused(v => v.PassAsync(guest, room, default))).Code);
        Assert.Equal("closed_by_staff", (await Refused(v => v.ReopenRoomAsync(owner, room, staff: false, default))).Code);
        var view = await V(v => v.RoomViewAsync(owner, room, default));
        Assert.True(view.ClosedByStaff);
        await V(v => v.ReopenRoomAsync(staff, room, staff: true, default));
        await V(v => v.PassAsync(guest, room, default));

        // the owner's own closing is the owner's to undo
        await V(v => v.CloseRoomAsync(owner, room, null, staff: false, default));
        await V(v => v.ReopenRoomAsync(owner, room, staff: false, default));
        await V(v => v.PassAsync(owner, room, default));
    }

    [Fact]
    public async Task An_account_ban_shuts_every_room_until_lifted()
    {
        var (owner, guest, room, roomId) = await PartyAsync();
        var (own, ownId) = await RoomAsync(guest, "Своя");
        var admin = await UserAsync("Суперадмин");
        await V(v => v.AccountBanAsync(admin, guest, "спам", default));
        Assert.True(f.Voice.Called($"remove {roomId} {guest}"));
        Assert.True(f.Voice.Called($"remove {ownId} {guest}"));
        Assert.Equal("account_banned", (await Refused(v => v.PassAsync(guest, room, default))).Code);
        Assert.Equal("account_banned", (await Refused(v => v.PassAsync(guest, own, default))).Code);
        await V(v => v.AccountUnbanAsync(admin, guest, default));
        await V(v => v.PassAsync(guest, room, default));
        // a second ban after the first was lifted is a new row, the old one stays in the history
        await V(v => v.AccountBanAsync(admin, guest, "снова", default));
        Assert.Equal(2, await f.DbAsync(db => db.VoiceAccountBans.CountAsync(b => b.UserId == guest)));
    }

    [Fact]
    public async Task A_full_room_turns_away_newcomers_but_not_someone_coming_back()
    {
        var (owner, guest, room, roomId) = await PartyAsync();
        var others = Enumerable.Range(0, 15).Select(i => new LivePeer(Guid.NewGuid().ToString(), $"p{i}", true, null)).ToList();
        f.Voice.Inside(roomId, [.. others, new LivePeer(Guid.NewGuid().ToString(), "last", true, null)]);
        Assert.Equal(("room_full", 409), await Why(v => v.PassAsync(guest, room, default)));
        f.Voice.Inside(roomId, [.. others, new LivePeer(guest.ToString(), "Гость", true, null)]);
        await V(v => v.PassAsync(guest, room, default));
    }

    [Fact]
    public async Task With_the_media_server_down_decisions_hold_and_reach_it_later()
    {
        var (owner, guest, room, roomId) = await PartyAsync();
        f.Voice.Down = true;
        try
        {
            Assert.Equal(("voice_unavailable", 503), await Why(v => v.PassAsync(guest, room, default)));
            // the ban is the site's: it holds at once even though nobody could be told
            await V(v => v.BanAsync(owner, room, guest, null, default));
            var job = await f.DbAsync(db => db.VoiceJobs.SingleAsync(j => j.RoomId == roomId && j.UserId == guest));
            Assert.Equal((JobState.Pending, 1), (job.State, job.Attempts));
            Assert.Contains("refused", job.LastError);
        }
        finally { f.Voice.Down = false; }
        Assert.Equal("banned", (await Refused(v => v.PassAsync(guest, room, default))).Code);

        var worker = ActivatorUtilities.CreateInstance<VoiceWorker>(f.Services);
        // only due jobs: the other tests' finished ones never come back
        f.Clock.Advance(TimeSpan.FromSeconds(16));
        while (await worker.RunOneAsync(default)) { }
        var done = await f.DbAsync(db => db.VoiceJobs.SingleAsync(j => j.RoomId == roomId && j.UserId == guest));
        Assert.Equal(JobState.Done, done.State);
        Assert.True(f.Voice.Called($"remove {roomId} {guest}"));
    }

    static string Webhook(string secret, string key, string body, long exp)
    {
        var sha = Convert.ToBase64String(SHA256.HashData(Encoding.UTF8.GetBytes(body)));
        return LiveKitTokens.Sign(new JsonObject { ["iss"] = key, ["exp"] = exp, ["sha256"] = sha }, secret);
    }

    async Task<HttpResponseMessage> PostHook(string body, string? authorization)
    {
        var c = f.CreateClient();
        using var req = new HttpRequestMessage(HttpMethod.Post, "/api/v1/voice/webhook") { Content = new StringContent(body, Encoding.UTF8, "application/webhook+json") };
        if (authorization is not null) req.Headers.TryAddWithoutValidation("Authorization", authorization);
        return await c.SendAsync(req);
    }

    [Fact]
    public async Task The_webhook_takes_only_signed_news_and_ejects_whoever_slipped_in()
    {
        var (owner, guest, room, roomId) = await PartyAsync();
        await V(v => v.BanAsync(owner, room, guest, null, default));
        var body = JsonSerializer.Serialize(new
        {
            @event = "participant_joined",
            room = new { name = roomId.ToString() },
            participant = new { identity = guest.ToString(), permission = new { canPublish = true } },
        });
        var exp = f.Clock.GetUtcNow().ToUnixTimeSeconds() + 300;
        Assert.Equal(HttpStatusCode.Unauthorized, (await PostHook(body, null)).StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, (await PostHook(body, Webhook(new string('x', 48), VoiceFactory.Key, body, exp))).StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, (await PostHook(body, Webhook(VoiceFactory.Secret, VoiceFactory.Key, body + " ", exp))).StatusCode);
        Assert.Equal(0, await f.DbAsync(db => db.VoiceEvents.CountAsync(e => e.RoomId == roomId && e.Kind == VoiceEventKinds.Join)));

        var before = f.Voice.Calls.Count(c => c == $"remove {roomId} {guest}");
        Assert.Equal(HttpStatusCode.OK, (await PostHook(body, Webhook(VoiceFactory.Secret, VoiceFactory.Key, body, exp))).StatusCode);
        Assert.Equal(before + 1, f.Voice.Calls.Count(c => c == $"remove {roomId} {guest}"));
        var kinds = await LogAsync(roomId, guest);
        Assert.Contains("join:", kinds);
        Assert.Contains("ejected:banned", kinds);

        // the sweep finds the same without any webhook: somebody inside a room the site deleted
        var (gone, goneId) = await RoomAsync(owner, "Удалим");
        f.Voice.Inside(goneId, new LivePeer(owner.ToString(), "Хозяин", true, null));
        await V(v => v.DeleteRoomAsync(owner, gone, default));
        f.Voice.Inside(goneId, new LivePeer(owner.ToString(), "Хозяин", true, null));
        var worker = ActivatorUtilities.CreateInstance<VoiceWorker>(f.Services);
        await worker.SweepAsync(default);
        Assert.True(f.Voice.Calls.Count(c => c == $"close {goneId}") >= 2);
    }

    [GeneratedRegex("name=\"__RequestVerificationToken\" type=\"hidden\" value=\"([^\"]+)\"")]
    private static partial Regex AntiforgeryRx();

    async Task<HttpClient> SignedInAsync(string email)
    {
        var c = f.CreateClient(new WebApplicationFactoryClientOptions { AllowAutoRedirect = false, HandleCookies = true });
        var html = await c.GetStringAsync("/account/login");
        var form = new Dictionary<string, string> { ["Email"] = email, ["Password"] = Password, ["__RequestVerificationToken"] = AntiforgeryRx().Match(html).Groups[1].Value };
        Assert.Equal(HttpStatusCode.Redirect, (await c.PostAsync("/account/login", new FormUrlEncodedContent(form))).StatusCode);
        return c;
    }

    async Task<HttpClient> LauncherAsync(Guid user)
    {
        var token = DeviceSecrets.NewToken();
        await f.DbAsync(async db =>
        {
            db.DeviceTokens.Add(new DeviceToken { UserId = user, TokenHash = DeviceSecrets.Hash(token), Name = "test", CreatedAt = f.Clock.GetUtcNow() });
            return await db.SaveChangesAsync();
        });
        var c = f.CreateClient();
        c.DefaultRequestHeaders.Add("X-Device-Token", token);
        return c;
    }

    static async Task<string?> CodeOf(HttpResponseMessage r) =>
        JsonDocument.Parse(await r.Content.ReadAsStringAsync()).RootElement.TryGetProperty("code", out var c) ? c.GetString() : null;

    [Fact]
    public async Task The_api_takes_changes_only_from_a_linked_launcher()
    {
        var email = $"voice-{Guid.NewGuid():N}@x.test";
        var me = await UserAsync("Лаунчер", Password, email);
        var bare = f.CreateClient();
        Assert.Equal(HttpStatusCode.Unauthorized, (await bare.GetAsync("/api/v1/voice/rooms")).StatusCode);
        var wrong = f.CreateClient();
        wrong.DefaultRequestHeaders.Add("X-Device-Token", DeviceSecrets.NewToken());
        Assert.Equal(HttpStatusCode.Unauthorized, (await wrong.GetAsync("/api/v1/voice/rooms")).StatusCode);

        var launcher = await LauncherAsync(me);
        var created = await launcher.PostAsJsonAsync("/api/v1/voice/rooms", new CreateRoomBody("Комната лаунчера"));
        Assert.Equal(HttpStatusCode.Created, created.StatusCode);
        var room = (await created.Content.ReadFromJsonAsync<RoomSummary>())!;
        var rooms = (await launcher.GetFromJsonAsync<RoomsResponse>("/api/v1/voice/rooms"))!;
        Assert.Contains(rooms.Owned, r => r.PublicId == room.PublicId);
        var pass = await launcher.PostAsync($"/api/v1/voice/rooms/{room.PublicId}/pass", null);
        Assert.Equal(HttpStatusCode.OK, pass.StatusCode);
        Assert.NotNull(LiveKitTokens.Verify((await pass.Content.ReadFromJsonAsync<PassView>())!.Token, VoiceFactory.Secret));
        Assert.Equal("no-store", pass.Headers.CacheControl?.ToString());
        var missing = await launcher.PostAsync("/api/v1/voice/rooms/abcdefghjk/pass", null);
        Assert.Equal(HttpStatusCode.NotFound, missing.StatusCode);
        Assert.Equal("no_access", await CodeOf(missing));

        // a browser session reads, but a change through it would skip the forms' antiforgery check
        var browser = await SignedInAsync(email);
        Assert.Equal(HttpStatusCode.OK, (await browser.GetAsync("/api/v1/voice/rooms")).StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, (await browser.PostAsync($"/api/v1/voice/rooms/{room.PublicId}/pass", null)).StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, (await browser.PostAsJsonAsync("/api/v1/voice/rooms", new CreateRoomBody("Через сессию"))).StatusCode);
    }

    /// <summary>
    /// The ban window (VOICE_CHAT.md section 7) the way the launchers meet it: a guest inside with a pass
    /// taken before the ban is taken out, gets no new pass, and the old one, used again within its
    /// minute, lets them in only until the join is checked - or until the sweep, if the webhook is lost.
    /// </summary>
    [Fact]
    public async Task A_ban_through_the_launcher_api_takes_the_guest_out_and_no_old_pass_keeps_them_in()
    {
        var (owner, guest, room, roomId) = await PartyAsync();
        var ownerApp = await LauncherAsync(owner);
        var guestApp = await LauncherAsync(guest);
        string Url(string tail) => $"/api/v1/voice/rooms/{room}{tail}";
        bool Inside() { lock (f.Voice.Rooms) return f.Voice.Rooms.TryGetValue(roomId, out var l) && l.Any(p => p.Identity == guest.ToString()); }
        void Enter() => f.Voice.Inside(roomId, new LivePeer(owner.ToString(), "Хозяин", true, null), new LivePeer(guest.ToString(), "Гость", true, null));
        int Removes() => f.Voice.Calls.Count(c => c == $"remove {roomId} {guest}");

        var issued = f.Clock.GetUtcNow().ToUnixTimeSeconds();
        var taken = await guestApp.PostAsync(Url("/pass"), null);
        Assert.Equal(HttpStatusCode.OK, taken.StatusCode);
        var old = (await taken.Content.ReadFromJsonAsync<PassView>())!;
        Enter();

        var ban = await ownerApp.PostAsJsonAsync(Url($"/members/{guest}/ban"), new ReasonBody("грубит"));
        Assert.True(ban.IsSuccessStatusCode, $"ban: {(int)ban.StatusCode}");
        Assert.Equal(1, Removes());
        Assert.False(Inside());

        // no new pass and no look inside, however often asked
        for (int i = 0; i < 3; i++)
        {
            var again = await guestApp.PostAsync(Url("/pass"), null);
            Assert.Equal((HttpStatusCode.Forbidden, "banned"), (again.StatusCode, await CodeOf(again)));
        }
        var live = await guestApp.GetAsync(Url("/live"));
        Assert.Equal((HttpStatusCode.Forbidden, "banned"), (live.StatusCode, await CodeOf(live)));

        // the pass from before the ban lives one minute from its issue, not from the ban
        Assert.Equal(60, Claims(old.Token)["exp"]!.GetValue<long>() - issued);
        Assert.Equal(60, old.ExpiresIn);

        // used again within that minute: the media server lets them in, the join is checked, they are out
        Enter();
        var body = JsonSerializer.Serialize(new
        {
            @event = "participant_joined",
            room = new { name = roomId.ToString() },
            participant = new { identity = guest.ToString(), permission = new { canPublish = true } },
        });
        var hook = await PostHook(body, Webhook(VoiceFactory.Secret, VoiceFactory.Key, body, issued + 300));
        Assert.Equal(HttpStatusCode.OK, hook.StatusCode);
        Assert.Equal(2, Removes());
        Assert.False(Inside());

        // the webhook lost, or a token the media server renewed itself: the sweep finds them all the same
        Enter();
        await ActivatorUtilities.CreateInstance<VoiceWorker>(f.Services).SweepAsync(default);
        Assert.Equal(3, Removes());
        Assert.False(Inside());
        lock (f.Voice.Rooms) Assert.Contains(f.Voice.Rooms[roomId], p => p.Identity == owner.ToString());

        var log = await LogAsync(roomId, guest);
        Assert.Contains("ban:грубит", log);
        Assert.Equal(2, log.Count(l => l == "ejected:banned"));
        Assert.Equal(1, await f.DbAsync(db => db.RoomBans.CountAsync(b => b.RoomId == roomId && b.UserId == guest)));
    }

    [Fact]
    public async Task A_complaint_is_a_voice_ticket_that_holds_its_log_until_a_year_after_closing()
    {
        var (owner, guest, room, roomId) = await PartyAsync();
        await V(v => v.KickAsync(owner, room, guest, "оскорбления", default));
        var ticket = await V(v => v.ComplainAsync(owner, room, guest, "Оскорблял всех в комнате", default));
        Assert.Equal((Categories.Voice, TicketSource.Voice), (ticket.Category, ticket.Source));
        var held = await f.DbAsync(db => db.VoiceEventTickets.Where(l => l.TicketId == ticket.Id).Select(l => l.EventId).ToListAsync());
        Assert.NotEmpty(held);
        var stranger = await UserAsync("Посторонний");
        Assert.Equal("no_access", (await Refused(v => v.ComplainAsync(stranger, room, guest, "текст", default))).Code);

        // nobody files a voice ticket by hand: it would come without the log it needs
        var form = await f.CreateClient().PostAsJsonAsync("/api/v1/tickets", new { category = "voice", title = "Жалоба", description = "текст" });
        Assert.Equal(HttpStatusCode.BadRequest, form.StatusCode);
        Assert.Equal("category_invalid", await CodeOf(form));

        // a year and more on: the log kept by the open complaint stays, an unrelated record goes
        f.Clock.Advance(TimeSpan.FromDays(400));
        var loose = await f.DbAsync(async db =>
        {
            var e = new VoiceEvent { RoomId = roomId, UserId = guest, Kind = VoiceEventKinds.Join, At = f.Clock.GetUtcNow().AddDays(-40) };
            db.VoiceEvents.Add(e);
            await db.SaveChangesAsync();
            return e.Id;
        });
        var worker = ActivatorUtilities.CreateInstance<VoiceWorker>(f.Services);
        await worker.PruneAsync(default);
        Assert.False(await f.DbAsync(db => db.VoiceEvents.AnyAsync(e => e.Id == loose)));
        Assert.Equal(held.Count, await f.DbAsync(db => db.VoiceEvents.CountAsync(e => held.Contains(e.Id))));

        // closed now: still held for a year after the closing, then let go
        await f.ScopedAsync(async sp =>
        {
            var t = await sp.GetRequiredService<PortalDb>().Tickets.SingleAsync(x => x.Id == ticket.Id);
            await sp.GetRequiredService<Xp.Portal.Tickets.TicketService>().ChangeStatusAsync(t, TicketStatus.Resolved, owner, default);
            return 0;
        });
        await worker.PruneAsync(default);
        Assert.Equal(held.Count, await f.DbAsync(db => db.VoiceEvents.CountAsync(e => held.Contains(e.Id))));
        f.Clock.Advance(TimeSpan.FromDays(366));
        await worker.PruneAsync(default);
        Assert.Equal(0, await f.DbAsync(db => db.VoiceEvents.CountAsync(e => held.Contains(e.Id))));
    }
}
