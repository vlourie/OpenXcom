using System.Net;
using System.Text;
using System.Text.Json;

namespace Xp.Launcher.Core.Tests;

/// <summary>A fake site that answers each request with whatever the test put down for "METHOD path".</summary>
public sealed class FakeVoiceSite : HttpMessageHandler
{
    public readonly Dictionary<string, (HttpStatusCode Code, string Body)> Answers = new();
    public readonly List<(string Line, string? Token, string? Body)> Seen = new();
    public bool Offline;

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage req, CancellationToken ct)
    {
        if (Offline) throw new HttpRequestException("no route to host");
        var line = $"{req.Method} {req.RequestUri!.PathAndQuery}";
        var token = req.Headers.TryGetValues(PortalClient.DeviceTokenHeader, out var v) ? v.Single() : null;
        var body = req.Content is null ? null : await req.Content.ReadAsStringAsync(ct);
        Seen.Add((line, token, body));
        if (!Answers.TryGetValue(line, out var a)) return new HttpResponseMessage(HttpStatusCode.NotFound);
        return new HttpResponseMessage(a.Code) { Content = new StringContent(a.Body, Encoding.UTF8, "application/json") };
    }

    public void Problem(string line, HttpStatusCode code, string problemCode) =>
        Answers[line] = (code, $$"""{"type":"about:blank","status":{{(int)code}},"code":"{{problemCode}}","detail":"no"}""");
}

public sealed class VoiceClientTests
{
    const string Token = "device-token-0123456789";
    const string Room = "abcdefgh23";
    readonly FakeVoiceSite _site = new();
    readonly PortalClient _portal;

    public VoiceClientTests() => _portal = new PortalClient(new HttpClient(_site), new Uri("https://portal.test"));

    const string Summary = """
        {"publicId":"abcdefgh23","title":"Пятничный рейд","owner":{"id":"11111111-1111-1111-1111-111111111111","name":"Капитан"},
         "mine":false,"status":"open","state":"ok","inviteDeclined":false,"capacity":10,"createdAt":"2026-10-01T10:00:00+00:00"}
        """;

    [Fact]
    public async Task Rooms_are_read_with_the_owner_and_the_standing()
    {
        _site.Answers["GET /api/v1/voice/rooms"] = (HttpStatusCode.OK, $$"""
            {"owned":[],"invited":[{{Summary}},
              {"publicId":"zzzzzzzz22","title":"Закрытая","owner":{"id":"22222222-2222-2222-2222-222222222222","name":"Боцман"},
               "mine":false,"status":"closed","state":"room_closed","inviteDeclined":true,"capacity":10,"createdAt":"2026-10-01T10:00:00Z"}]}
            """);

        var rooms = await _portal.VoiceRoomsAsync(Token, default);

        Assert.Empty(rooms.Owned);
        Assert.Equal(2, rooms.Invited.Count);
        var open = rooms.Invited[0];
        Assert.Equal("Пятничный рейд", open.Title);
        Assert.Equal("Капитан", open.Owner.Name);
        Assert.Equal(Guid.Parse("11111111-1111-1111-1111-111111111111"), open.Owner.Id);
        Assert.True(open.CanJoin);
        Assert.False(rooms.Invited[1].CanJoin);
        Assert.True(rooms.Invited[1].InviteDeclined);
        Assert.Equal(Token, _site.Seen.Single().Token);
    }

    [Fact]
    public async Task Every_call_carries_the_device_key()
    {
        _site.Answers["POST /api/v1/voice/rooms"] = (HttpStatusCode.Created, Summary);
        _site.Answers[$"GET /api/v1/voice/rooms/{Room}/live"] = (HttpStatusCode.OK, "[]");
        _site.Answers[$"POST /api/v1/voice/rooms/{Room}/decline"] = (HttpStatusCode.NoContent, "");
        _site.Answers["GET /api/v1/friends?page=1"] = (HttpStatusCode.OK,
            """{"friends":[],"friendsTotal":0,"incoming":[],"outgoing":[],"blocked":[]}""");

        await _portal.CreateVoiceRoomAsync(Token, "Пятничный рейд", default);
        await _portal.VoiceLiveAsync(Token, Room, default);
        await _portal.DeclineVoiceInviteAsync(Token, Room, default);
        await _portal.FriendsAsync(Token, 0, default);

        Assert.Equal(4, _site.Seen.Count);
        Assert.All(_site.Seen, s => Assert.Equal(Token, s.Token));
        Assert.Equal("Пятничный рейд", JsonDocument.Parse(_site.Seen[0].Body!).RootElement.GetProperty("title").GetString());
    }

    [Fact]
    public async Task The_pass_is_read_whole()
    {
        _site.Answers[$"POST /api/v1/voice/rooms/{Room}/pass"] = (HttpStatusCode.OK, """
            {"url":"wss://voice.test","token":"jwt.jwt.jwt","room":"abcdefgh23","roomName":"33333333-3333-3333-3333-333333333333",
             "identity":"44444444-4444-4444-4444-444444444444","name":"Юнга","canPublish":false,"expiresIn":60}
            """);

        var pass = await _portal.VoicePassAsync(Token, Room, default);

        Assert.Equal("wss://voice.test", pass.Url);
        Assert.Equal("jwt.jwt.jwt", pass.Token);
        Assert.Equal("44444444-4444-4444-4444-444444444444", pass.Identity);
        Assert.False(pass.CanPublish);
        Assert.Equal(60, pass.ExpiresIn);
    }

    [Theory]
    [InlineData(HttpStatusCode.NotFound, "no_access")]
    [InlineData(HttpStatusCode.Forbidden, "banned")]
    [InlineData(HttpStatusCode.Forbidden, "room_closed")]
    [InlineData(HttpStatusCode.Forbidden, "account_banned")]
    [InlineData(HttpStatusCode.Forbidden, "invite_revoked")]
    [InlineData(HttpStatusCode.Forbidden, "not_friends")]
    [InlineData(HttpStatusCode.Unauthorized, "device_unknown")]
    [InlineData(HttpStatusCode.Conflict, "room_full")]
    public async Task A_refusal_becomes_its_code(HttpStatusCode status, string code)
    {
        _site.Problem($"POST /api/v1/voice/rooms/{Room}/pass", status, code);

        var e = await Assert.ThrowsAsync<VoicePassRefusedException>(() => _portal.VoicePassAsync(Token, Room, default));

        Assert.Equal(code, e.Code);
        Assert.Equal((int)status, e.Status);
    }

    [Fact]
    public async Task A_bare_401_means_the_launcher_was_unlinked()
    {
        _site.Answers[$"POST /api/v1/voice/rooms/{Room}/pass"] = (HttpStatusCode.Unauthorized, "");

        var e = await Assert.ThrowsAsync<VoicePassRefusedException>(() => _portal.VoicePassAsync(Token, Room, default));

        Assert.Equal("device_unknown", e.Code);
    }

    [Theory]
    [InlineData(HttpStatusCode.ServiceUnavailable, "voice_unavailable")]
    [InlineData(HttpStatusCode.TooManyRequests, "rate_limited")]
    public async Task A_passing_trouble_is_not_a_refusal(HttpStatusCode status, string code)
    {
        _site.Problem($"POST /api/v1/voice/rooms/{Room}/pass", status, code);

        var e = await Assert.ThrowsAsync<PortalException>(() => _portal.VoicePassAsync(Token, Room, default));

        Assert.True(e.Transient);
        Assert.Equal(code, e.Code);
    }

    [Fact]
    public async Task No_network_is_not_a_refusal()
    {
        _site.Offline = true;

        await Assert.ThrowsAsync<HttpRequestException>(() => _portal.VoicePassAsync(Token, Room, default));
    }

    [Fact]
    public async Task The_owner_sees_members_others_do_not()
    {
        _site.Answers[$"GET /api/v1/voice/rooms/{Room}"] = (HttpStatusCode.OK, $$"""
            {"room":{{Summary}},"members":[{"person":{"id":"55555555-5555-5555-5555-555555555555","name":"Кок"},
              "invite":"active","banned":false,"restricted":true,"friend":true}],"closedByStaff":false,"closedReason":null}
            """);
        _site.Answers[$"GET /api/v1/voice/rooms/zzzzzzzz22"] = (HttpStatusCode.OK, $$"""
            {"room":{{Summary}},"members":null,"closedByStaff":true,"closedReason":"спам"}
            """);

        var mine = await _portal.VoiceRoomAsync(Token, Room, default);
        var theirs = await _portal.VoiceRoomAsync(Token, "zzzzzzzz22", default);

        var m = Assert.Single(mine.Members!);
        Assert.Equal("Кок", m.Person.Name);
        Assert.True(m.Restricted);
        Assert.Equal("active", m.Invite);
        Assert.Null(theirs.Members);
        Assert.True(theirs.ClosedByStaff);
        Assert.Equal("спам", theirs.ClosedReason);
    }

    [Fact]
    public async Task Moderation_sends_the_reason_or_nothing()
    {
        var who = Guid.Parse("55555555-5555-5555-5555-555555555555");
        _site.Answers[$"POST /api/v1/voice/rooms/{Room}/members/{who}/kick"] = (HttpStatusCode.NoContent, "");
        _site.Answers[$"POST /api/v1/voice/rooms/{Room}/members/{who}/ban"] = (HttpStatusCode.NoContent, "");
        _site.Answers[$"PUT /api/v1/voice/rooms/{Room}/members/{who}/speaking"] = (HttpStatusCode.NoContent, "");
        _site.Answers[$"DELETE /api/v1/voice/rooms/{Room}/bans/{who}"] = (HttpStatusCode.NoContent, "");
        _site.Answers[$"DELETE /api/v1/voice/rooms/{Room}/invites/{who}?reason=%D1%84%D0%BB%D1%83%D0%B4%20%26%20%D0%BC%D0%B0%D1%82"] = (HttpStatusCode.NoContent, "");
        _site.Answers[$"POST /api/v1/voice/rooms/{Room}/invites"] = (HttpStatusCode.NoContent, "");

        await _portal.KickFromVoiceRoomAsync(Token, Room, who, "   ", default);
        await _portal.BanFromVoiceRoomAsync(Token, Room, who, " флуд ", default);
        await _portal.SetVoiceSpeakingAsync(Token, Room, who, false, null, default);
        await _portal.UnbanInVoiceRoomAsync(Token, Room, who, default);
        await _portal.RevokeVoiceInviteAsync(Token, Room, who, "флуд & мат", default);
        await _portal.InviteToVoiceRoomAsync(Token, Room, who, default);

        Assert.Equal(JsonValueKind.Null, Body(0).GetProperty("reason").ValueKind);
        Assert.Equal("флуд", Body(1).GetProperty("reason").GetString());
        Assert.False(Body(2).GetProperty("allowed").GetBoolean());
        Assert.Equal(who, Body(5).GetProperty("user").GetGuid());
        Assert.Equal(6, _site.Seen.Count);
    }

    [Fact]
    public async Task A_refused_action_says_why()
    {
        var who = Guid.NewGuid();
        _site.Problem($"POST /api/v1/voice/rooms/{Room}/members/{who}/ban", HttpStatusCode.Forbidden, "not_owner");

        var e = await Assert.ThrowsAsync<PortalException>(() => _portal.BanFromVoiceRoomAsync(Token, Room, who, null, default));

        Assert.Equal("not_owner", e.Code);
        Assert.False(e.Transient);
    }

    [Fact]
    public async Task Friends_requests_and_complaints()
    {
        var req = Guid.Parse("66666666-6666-6666-6666-666666666666");
        _site.Answers["GET /api/v1/friends?page=2"] = (HttpStatusCode.OK, """
            {"friends":[{"id":"77777777-7777-7777-7777-777777777777","name":"Штурман","since":"2026-09-30T08:00:00Z"}],"friendsTotal":51,
             "incoming":[{"id":"66666666-6666-6666-6666-666666666666","person":{"id":"88888888-8888-8888-8888-888888888888","name":"Юнга"},"at":"2026-10-02T08:00:00Z"}],
             "outgoing":[],"blocked":[{"id":"99999999-9999-9999-9999-999999999999","name":"Тролль"}]}
            """);
        _site.Answers["POST /api/v1/friends/requests"] = (HttpStatusCode.OK, """{"result":"accepted"}""");
        _site.Answers[$"POST /api/v1/friends/requests/{req}/accept"] = (HttpStatusCode.NoContent, "");
        _site.Answers[$"POST /api/v1/friends/requests/{req}/decline"] = (HttpStatusCode.NoContent, "");
        _site.Answers[$"POST /api/v1/voice/rooms/{Room}/complaints"] = (HttpStatusCode.Created, """{"number":42,"displayNumber":"V-42"}""");

        var f = await _portal.FriendsAsync(Token, 2, default);
        var result = await _portal.RequestFriendAsync(Token, " Юнга ", default);
        await _portal.AcceptFriendAsync(Token, req, default);
        await _portal.DeclineFriendAsync(Token, req, default);
        var c = await _portal.ComplainInVoiceRoomAsync(Token, Room, req, " орёт в микрофон ", default);

        Assert.Equal("Штурман", f.Friends.Single().Name);
        Assert.Equal(51, f.FriendsTotal);
        Assert.Equal("Юнга", f.Incoming.Single().Person.Name);
        Assert.Equal("Тролль", f.Blocked.Single().Name);
        Assert.Equal("accepted", result);
        Assert.Equal("Юнга", Body(1).GetProperty("who").GetString());
        Assert.Equal("орёт в микрофон", Body(4).GetProperty("text").GetString());
        Assert.Equal("V-42", c.DisplayNumber);
    }

    [Theory]
    [InlineData("xpiratez://voice/abcdefgh23", "abcdefgh23")]
    [InlineData("xpiratez://voice/abcdefgh23/", "abcdefgh23")]
    [InlineData("XPIRATEZ://VOICE/ABCDEFGH23", "abcdefgh23")]
    [InlineData("xpiratez://other/abcdefgh23", null)]
    [InlineData("https://voice/abcdefgh23", null)]
    [InlineData("xpiratez://voice/", null)]
    [InlineData("xpiratez://voice/abc/def", null)]
    [InlineData("xpiratez://voice/abc%20def", null)]
    [InlineData("xpiratez://voice/..%2Fapi", null)]
    [InlineData("--headless", null)]
    [InlineData("", null)]
    [InlineData(null, null)]
    public void A_link_names_a_room_or_nothing(string? link, string? room) => Assert.Equal(room, VoiceLink.Parse(link));

    [Fact]
    public void The_link_is_found_among_the_arguments()
    {
        Assert.Equal("abcdefgh23", VoiceLink.Find(["--refresh", "xpiratez://voice/abcdefgh23"]));
        Assert.Null(VoiceLink.Find(["--refresh"]));
        Assert.Equal("abcdefgh23", VoiceLink.Parse(VoiceLink.For("abcdefgh23")));
    }

    JsonElement Body(int i) => JsonDocument.Parse(_site.Seen[i].Body!).RootElement;
}
