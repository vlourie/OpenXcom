using System.Net;
using System.Net.Http.Json;
using Microsoft.EntityFrameworkCore;
using Xp.Portal.Data;
using Xp.Portal.Voice;

namespace Xp.Portal.Tests;

/// <summary>
/// The lobby of the launcher's «Общение» page (VOICE_CHAT.md §3, version 0.5): who is online, the open
/// rooms of everybody, and a knock at the door the owner answers - the one way into a room of somebody
/// who is not a friend.
/// </summary>
public sealed partial class VoiceTests
{
    static bool Has(IEnumerable<OnlineView> online, Guid id) => online.Any(o => o.Person.Id == id);
    static CatalogRoom? In(IEnumerable<CatalogRoom> rooms, string publicId) => rooms.FirstOrDefault(r => r.PublicId == publicId);

    [Fact]
    public async Task Online_is_a_running_launcher_and_hides_blocks_both_ways()
    {
        var me = await UserAsync("Смотрящий");
        var friend = await UserAsync("Друг онлайн");
        var stranger = await UserAsync("Прохожий");
        var rude = await UserAsync("Грубиян");
        await FriendsAsync(me, friend);
        await V(v => v.BlockAsync(rude, me, default));
        foreach (var who in new[] { me, friend, stranger, rude }) await V(v => v.SeenAsync(who, default));
        await V(v => v.SeenAsync(stranger, default));   // twice is still one row

        var online = await V(v => v.OnlineAsync(me, default));
        Assert.False(Has(online, me));
        Assert.True(online.Single(o => o.Person.Id == friend).Friend);
        Assert.False(online.Single(o => o.Person.Id == stranger).Friend);
        Assert.False(Has(online, rude));
        Assert.False(Has(await V(v => v.OnlineAsync(rude, default)), me));
        Assert.Equal(1, await f.DbAsync(db => db.VoicePresences.CountAsync(p => p.UserId == stranger)));

        Assert.Equal("sent", await V(v => v.RequestAsync(me, stranger, default)));
        Assert.True((await V(v => v.OnlineAsync(me, default))).Single(o => o.Person.Id == stranger).Asked);

        // a closed launcher is gone at once; a silent one after the window
        await V(v => v.GoneAsync(friend, default));
        Assert.False(Has(await V(v => v.OnlineAsync(me, default)), friend));
        f.Clock.Advance(VoiceLimits.OnlineWindow + TimeSpan.FromSeconds(1));
        Assert.False(Has(await V(v => v.OnlineAsync(me, default)), stranger));
    }

    [Fact]
    public async Task A_stranger_knocks_the_owner_lets_them_in_and_a_block_shuts_the_door_again()
    {
        var owner = await UserAsync("Хозяин двери");
        var stranger = await UserAsync("Стучащий");
        var (room, roomId) = await RoomAsync(owner, "Открытая палуба");

        // the room is in the list, but nothing more than its name lets anybody in
        var seen = In(await V(v => v.CatalogAsync(stranger, default)), room);
        Assert.Equal(("request", "Открытая палуба", owner), (seen!.State, seen.Title, seen.Owner.Id));
        Assert.Null(In(await V(v => v.CatalogAsync(owner, default)), room));
        Assert.Equal(("no_access", 404), await Why(v => v.PassAsync(stranger, room, default)));
        Assert.Equal(("no_access", 404), await Why(v => v.LiveAsync(stranger, room, default)));

        Assert.Equal("sent", await V(v => v.AskToEnterAsync(stranger, room, default)));
        Assert.Equal("sent", await V(v => v.AskToEnterAsync(stranger, room, default)));
        Assert.Equal("requested", In(await V(v => v.CatalogAsync(stranger, default)), room)!.State);
        var knock = Assert.Single(await V(v => v.JoinRequestsAsync(owner, default)), r => r.Room == room);
        Assert.Equal(stranger, knock.Person.Id);
        Assert.Empty(await V(v => v.JoinRequestsAsync(stranger, default)));
        // only the owner answers
        Assert.Equal(("no_access", 404), await Why(v => v.AcceptEntryAsync(stranger, room, stranger, default)));

        await V(v => v.AcceptEntryAsync(owner, room, stranger, default));
        var (_, invited) = await V(v => v.RoomsAsync(stranger, default));
        Assert.Equal("ok", invited.Single(r => r.PublicId == room).State);
        Assert.Null(In(await V(v => v.CatalogAsync(stranger, default)), room));
        var pass = await V(v => v.PassAsync(stranger, room, default));
        Assert.True(pass.CanPublish);
        Assert.Equal("already", await V(v => v.AskToEnterAsync(stranger, room, default)));
        Assert.Contains("invite:request", await LogAsync(roomId, stranger));

        // the owner moderates the newcomer like any guest
        await V(v => v.SetSpeakingAsync(owner, room, stranger, false, null, default));
        Assert.False((await V(v => v.PassAsync(stranger, room, default))).CanPublish);

        // a block undoes the consent the way it undoes a friendship
        await V(v => v.BlockAsync(owner, stranger, default));
        Assert.Equal(403, (await Refused(v => v.PassAsync(stranger, room, default))).Status);
        Assert.Equal(("no_access", 404), await Why(v => v.AskToEnterAsync(stranger, room, default)));
        await V(v => v.UnblockAsync(owner, stranger, default));
    }

    [Fact]
    public async Task A_no_holds_for_a_while_a_ban_for_good_and_a_closed_room_takes_no_knocks()
    {
        var owner = await UserAsync("Строгий хозяин");
        var pest = await UserAsync("Настырный");
        var (room, _) = await RoomAsync(owner, "Тихая каюта");

        Assert.Equal("sent", await V(v => v.AskToEnterAsync(pest, room, default)));
        await V(v => v.DeclineEntryAsync(owner, room, pest, default));
        Assert.Equal(("request_not_found", 404), await Why(v => v.DeclineEntryAsync(owner, room, pest, default)));
        Assert.Equal(("request_declined", 409), await Why(v => v.AskToEnterAsync(pest, room, default)));
        Assert.Equal("request", In(await V(v => v.CatalogAsync(pest, default)), room)!.State);
        f.Clock.Advance(VoiceLimits.JoinRetryAfterDecline + TimeSpan.FromSeconds(1));
        Assert.Equal("sent", await V(v => v.AskToEnterAsync(pest, room, default)));

        // taken back by the one who knocked
        await V(v => v.CancelAskAsync(pest, room, default));
        Assert.DoesNotContain(await V(v => v.JoinRequestsAsync(owner, default)), r => r.Person.Id == pest);
        Assert.Equal("sent", await V(v => v.AskToEnterAsync(pest, room, default)));

        // a ban of the one at the door answers the knock and keeps them away
        await V(v => v.BanAsync(owner, room, pest, "надоел", default));
        Assert.Empty(await V(v => v.JoinRequestsAsync(owner, default)));
        Assert.Equal(("banned", 403), await Why(v => v.AskToEnterAsync(pest, room, default)));
        Assert.Equal("banned", In(await V(v => v.CatalogAsync(pest, default)), room)!.State);
        Assert.Equal(("banned", 403), await Why(v => v.PassAsync(pest, room, default)));

        // a closed room is not in the list and takes no knocks
        var other = await UserAsync("Другой гость");
        await V(v => v.CloseRoomAsync(owner, room, null, staff: false, default));
        Assert.Null(In(await V(v => v.CatalogAsync(other, default)), room));
        Assert.Equal(("room_closed", 403), await Why(v => v.AskToEnterAsync(other, room, default)));
        Assert.Equal(("owner_target", 400), await Why(v => v.AskToEnterAsync(owner, room, default)));
    }

    [Fact]
    public async Task The_lobby_api_works_from_a_linked_launcher_only()
    {
        var owner = await UserAsync("Хозяин лобби");
        var guest = await UserAsync("Гость лобби");
        var (room, _) = await RoomAsync(owner, "Кают-компания");
        var ownerApp = await LauncherAsync(owner);
        var guestApp = await LauncherAsync(guest);

        Assert.Equal(HttpStatusCode.Unauthorized, (await f.CreateClient().PostAsync("/api/v1/voice/presence", null)).StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, (await f.CreateClient().GetAsync("/api/v1/voice/lobby")).StatusCode);
        Assert.Equal(HttpStatusCode.NoContent, (await ownerApp.PostAsync("/api/v1/voice/presence", null)).StatusCode);
        Assert.Equal(HttpStatusCode.NoContent, (await guestApp.PostAsync("/api/v1/voice/presence", null)).StatusCode);

        var lobby = (await guestApp.GetFromJsonAsync<LobbyView>("/api/v1/voice/lobby"))!;
        Assert.True(Has(lobby.Online, owner));
        Assert.Equal("request", In(lobby.Rooms, room)!.State);

        var asked = await guestApp.PostAsync($"/api/v1/voice/rooms/{room}/requests", null);
        Assert.Equal("sent", (await asked.Content.ReadFromJsonAsync<FriendRequestResult>())!.Result);
        var mine = (await ownerApp.GetFromJsonAsync<LobbyView>("/api/v1/voice/lobby"))!;
        Assert.Contains(mine.Requests, r => r.Room == room && r.Person.Id == guest);
        Assert.Equal(HttpStatusCode.NoContent, (await ownerApp.PostAsync($"/api/v1/voice/rooms/{room}/requests/{guest}/accept", null)).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await guestApp.PostAsync($"/api/v1/voice/rooms/{room}/pass", null)).StatusCode);

        Assert.Equal(HttpStatusCode.NoContent, (await guestApp.DeleteAsync("/api/v1/voice/presence")).StatusCode);
        Assert.False(Has((await ownerApp.GetFromJsonAsync<LobbyView>("/api/v1/voice/lobby"))!.Online, guest));
    }
}
