using System.Net;
using System.Text.RegularExpressions;
using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Xp.Portal.Data;
using Xp.Portal.Voice;

namespace Xp.Portal.Tests;

/// <summary>
/// The voice pages as a browser sees them (docs/portal/VOICE_CHAT.md §3-§5): a friend found by a link,
/// a room made and filled on the site, the way into the launcher, a refusal told in words, and the
/// same "no access" for a stranger whether the room exists or not.
/// </summary>
public sealed partial class VoicePageTests(VoiceFactory f) : IClassFixture<VoiceFactory>
{
    const string Password = "Long-enough-passw0rd!";

    HttpClient Browser() => f.CreateClient(new WebApplicationFactoryClientOptions { AllowAutoRedirect = false, HandleCookies = true });

    [GeneratedRegex("name=\"__RequestVerificationToken\" type=\"hidden\" value=\"([^\"]+)\"")]
    private static partial Regex AntiforgeryRx();

    [GeneratedRegex("<main[^>]*>(.*)</main>", RegexOptions.Singleline)]
    private static partial Regex MainRx();

    static async Task<HttpResponseMessage> PostForm(HttpClient c, string url, Dictionary<string, string> fields, string? tokenFrom = null)
    {
        var html = await c.GetStringAsync(tokenFrom ?? url);
        fields["__RequestVerificationToken"] = AntiforgeryRx().Match(html) is { Success: true } m
            ? m.Groups[1].Value
            : throw new Xunit.Sdk.XunitException("no antiforgery token on " + (tokenFrom ?? url));
        return await c.PostAsync(url, new FormUrlEncodedContent(fields));
    }

    /// <summary>The page as text a reader sees: entities decoded.</summary>
    static async Task<string> Read(HttpResponseMessage r) => WebUtility.HtmlDecode(await r.Content.ReadAsStringAsync());

    async Task<(HttpClient Browser, Guid Id, string Name)> PersonAsync(string name)
    {
        var email = $"vp-{Guid.NewGuid():N}@x.test";
        name = $"{name}-{Guid.NewGuid().ToString("N")[..6]}";
        var id = await f.ScopedAsync(async sp =>
        {
            var users = sp.GetRequiredService<UserManager<PortalUser>>();
            var u = new PortalUser { UserName = email, Email = email, EmailConfirmed = true, DisplayName = name };
            Assert.True((await users.CreateAsync(u, Password)).Succeeded);
            return u.Id;
        });
        var c = Browser();
        var r = await PostForm(c, "/account/login", new() { ["Email"] = email, ["Password"] = Password });
        Assert.Equal(HttpStatusCode.Redirect, r.StatusCode);
        return (c, id, name);
    }

    Task V(Func<VoiceService, Task> act) => f.ScopedAsync(async sp => { await act(sp.GetRequiredService<VoiceService>()); return 0; });
    Task<T> V<T>(Func<VoiceService, Task<T>> act) => f.ScopedAsync(sp => act(sp.GetRequiredService<VoiceService>()));

    async Task<(string Code, Guid Id)> RoomAsync(Guid owner, string title)
    {
        var room = await V(v => v.CreateRoomAsync(owner, title, default));
        var id = await f.DbAsync(db => db.VoiceRooms.Where(r => r.PublicId == room.PublicId).Select(r => r.Id).SingleAsync());
        return (room.PublicId, id);
    }

    async Task FriendsAsync(Guid a, Guid b)
    {
        await V(v => v.RequestAsync(a, b, default));
        await V(v => v.RequestAsync(b, a, default));
    }

    [Fact]
    public async Task A_friend_by_link_then_a_room_made_and_filled_on_the_site()
    {
        var owner = await PersonAsync("Хозяин");
        var guest = await PersonAsync("Гость");

        // the owner's link opens a page that offers a request to exactly that person
        var link = $"/me/friends/{owner.Id}";
        var offer = await guest.Browser.GetAsync(link);
        Assert.Equal(HttpStatusCode.OK, offer.StatusCode);
        Assert.Contains(owner.Name, await Read(offer));
        var r = await PostForm(guest.Browser, "/me/friends?handler=Request", new() { ["who"] = $"https://portal.test{link}" }, tokenFrom: link);
        Assert.Equal(HttpStatusCode.Redirect, r.StatusCode);
        Assert.Equal("/me/friends", r.Headers.Location!.OriginalString);
        Assert.Contains("Заявка отправлена.", await Read(await guest.Browser.GetAsync("/me/friends")));

        var incoming = await Read(await owner.Browser.GetAsync("/me/friends"));
        Assert.Contains(guest.Name, incoming);
        var request = await f.DbAsync(db => db.FriendRequests.Where(q => q.SenderId == guest.Id && q.RecipientId == owner.Id).Select(q => q.Id).SingleAsync());
        r = await PostForm(owner.Browser, "/me/friends?handler=Accept", new() { ["id"] = request.ToString() });
        Assert.Equal(HttpStatusCode.Redirect, r.StatusCode);
        Assert.Contains("Теперь вы друзья.", await Read(await owner.Browser.GetAsync("/me/friends")));

        // a room is made on the site and the friend is offered for an invite
        var title = "Рейд " + Guid.NewGuid().ToString("N")[..6];
        r = await PostForm(owner.Browser, "/voice?handler=Create", new() { ["title"] = title });
        Assert.Equal(HttpStatusCode.Redirect, r.StatusCode);
        var back = r.Headers.Location!.OriginalString;
        Assert.StartsWith("/voice/rooms/", back);
        var code = back["/voice/rooms/".Length..];
        Assert.Contains(guest.Name, await Read(await owner.Browser.GetAsync(back)));
        r = await PostForm(owner.Browser, $"{back}?handler=Invite", new() { ["user"] = guest.Id.ToString() }, tokenFrom: back);
        Assert.Equal(HttpStatusCode.Redirect, r.StatusCode);
        Assert.Equal(back, r.Headers.Location!.OriginalString);

        // the guest finds it on /voice and is sent to the launcher, which asks the site for the pass itself
        var list = await Read(await guest.Browser.GetAsync("/voice"));
        Assert.Contains(title, list);
        Assert.Contains($"xpiratez://voice/{code}", list);
        var roomId = await f.DbAsync(db => db.VoiceRooms.Where(x => x.PublicId == code).Select(x => x.Id).SingleAsync());
        f.Voice.Inside(roomId, new LivePeer(owner.Id.ToString(), owner.Name, true, null));
        var page = await guest.Browser.GetAsync(back);
        Assert.Equal(HttpStatusCode.OK, page.StatusCode);
        var html = await Read(page);
        Assert.Contains($"xpiratez://voice/{code}", html);
        Assert.Contains("Сейчас в комнате", html);
        Assert.Contains(owner.Name, html);
        // the guest sees no owner's controls
        Assert.DoesNotContain("handler=Invite", html);
        Assert.DoesNotContain("handler=Ban", html);
    }

    [Fact]
    public async Task A_stranger_gets_the_same_404_for_a_room_and_for_no_room_whatever_he_tries()
    {
        var owner = await PersonAsync("Хозяин");
        var stranger = await PersonAsync("Чужой");
        var title = "Тайная " + Guid.NewGuid().ToString("N")[..6];
        var (code, roomId) = await RoomAsync(owner.Id, title);

        var there = await stranger.Browser.GetAsync($"/voice/rooms/{code}");
        var nowhere = await stranger.Browser.GetAsync("/voice/rooms/no-such-room");
        Assert.Equal(HttpStatusCode.NotFound, there.StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, nowhere.StatusCode);
        var a = await Read(there);
        var b = await Read(nowhere);
        Assert.Contains("Нет доступа", a);
        Assert.DoesNotContain(title, a);
        Assert.DoesNotContain(owner.Name, a);
        Assert.Equal(MainRx().Match(b).Groups[1].Value, MainRx().Match(a).Groups[1].Value);

        // a change is refused with the same answer and changes nothing
        foreach (var (handler, fields) in new (string, Dictionary<string, string>)[]
        {
            ("Invite", new() { ["user"] = stranger.Id.ToString() }),
            ("Close", new() { ["reason"] = "моё" }),
            ("Delete", new() { ["sure"] = "true" }),
        })
        {
            var r = await PostForm(stranger.Browser, $"/voice/rooms/{code}?handler={handler}", fields, tokenFrom: "/voice");
            Assert.Equal(HttpStatusCode.NotFound, r.StatusCode);
            Assert.DoesNotContain(title, await Read(r));
        }
        var room = await f.DbAsync(db => db.VoiceRooms.SingleAsync(x => x.Id == roomId));
        Assert.Equal(VoiceRoomStatus.Open, room.Status);
        Assert.False(await f.DbAsync(db => db.RoomInvites.AnyAsync(i => i.RoomId == roomId)));
    }

    [Fact]
    public async Task A_refusal_is_told_in_words_and_changes_nothing()
    {
        var owner = await PersonAsync("Хозяин");
        var other = await PersonAsync("Незнакомец");
        var (code, roomId) = await RoomAsync(owner.Id, "Своя");
        var url = $"/voice/rooms/{code}";

        var r = await PostForm(owner.Browser, $"{url}?handler=Invite", new() { ["user"] = other.Id.ToString() }, tokenFrom: url);
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Contains("Пригласить можно только друга.", await Read(r));
        Assert.False(await f.DbAsync(db => db.RoomInvites.AnyAsync(i => i.RoomId == roomId)));

        r = await PostForm(owner.Browser, "/voice?handler=Create", new() { ["title"] = "   " });
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Contains("Название — от 1 до 80 знаков.", await Read(r));

        // deleting asks for the tick first
        r = await PostForm(owner.Browser, $"{url}?handler=Delete", new(), tokenFrom: url);
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Contains("Отметьте «да, удалить насовсем».", await Read(r));
        Assert.True(await f.DbAsync(db => db.VoiceRooms.AnyAsync(x => x.Id == roomId)));
        r = await PostForm(owner.Browser, $"{url}?handler=Delete", new() { ["sure"] = "true" }, tokenFrom: url);
        Assert.Equal(HttpStatusCode.Redirect, r.StatusCode);
        Assert.Equal("/voice", r.Headers.Location!.OriginalString);
        Assert.False(await f.DbAsync(db => db.VoiceRooms.AnyAsync(x => x.Id == roomId)));
    }

    [Fact]
    public async Task The_owners_buttons_reach_the_media_server_and_the_log()
    {
        var owner = await PersonAsync("Хозяин");
        var guest = await PersonAsync("Гость");
        await FriendsAsync(owner.Id, guest.Id);
        var (code, roomId) = await RoomAsync(owner.Id, "Шумная");
        await V(v => v.InviteAsync(owner.Id, code, guest.Id, default));
        var url = $"/voice/rooms/{code}";

        var r = await PostForm(owner.Browser, $"{url}?handler=Speaking", new() { ["user"] = guest.Id.ToString(), ["allowed"] = "false", ["reason"] = "шумит" }, tokenFrom: url);
        Assert.Equal(HttpStatusCode.Redirect, r.StatusCode);
        Assert.True(f.Voice.Called($"publish {roomId} {guest.Id} False"));
        r = await PostForm(owner.Browser, $"{url}?handler=Ban", new() { ["user"] = guest.Id.ToString(), ["reason"] = "грубит" }, tokenFrom: url);
        Assert.Equal(HttpStatusCode.Redirect, r.StatusCode);
        Assert.True(f.Voice.Called($"remove {roomId} {guest.Id}"));
        Assert.Equal("banned", (await V(v => v.RoomsAsync(guest.Id, default))).Invited.Single(x => x.PublicId == code).State);

        // the guest's page tells why, and the owner can take it back
        Assert.Contains("Вы заблокированы", await Read(await guest.Browser.GetAsync(url)));
        r = await PostForm(owner.Browser, $"{url}?handler=Unban", new() { ["user"] = guest.Id.ToString() }, tokenFrom: url);
        Assert.Equal(HttpStatusCode.Redirect, r.StatusCode);
        var log = await f.DbAsync(db => db.VoiceEvents.Where(e => e.RoomId == roomId && e.UserId == guest.Id).Select(e => e.Kind + ":" + (e.Reason ?? "")).ToListAsync());
        Assert.Contains("mute:шумит", log);
        Assert.Contains("ban:грубит", log);
        Assert.Contains("unban:", log);
    }

    [Fact]
    public async Task Voice_forms_without_antiforgery_are_refused()
    {
        var owner = await PersonAsync("Хозяин");
        var before = await f.DbAsync(db => db.VoiceRooms.CountAsync(x => x.OwnerId == owner.Id));
        var r = await owner.Browser.PostAsync("/voice?handler=Create", new FormUrlEncodedContent(new Dictionary<string, string> { ["title"] = "без токена" }));
        Assert.Equal(HttpStatusCode.BadRequest, r.StatusCode);
        r = await owner.Browser.PostAsync("/me/friends?handler=Request", new FormUrlEncodedContent(new Dictionary<string, string> { ["who"] = Guid.NewGuid().ToString() }));
        Assert.Equal(HttpStatusCode.BadRequest, r.StatusCode);
        Assert.Equal(before, await f.DbAsync(db => db.VoiceRooms.CountAsync(x => x.OwnerId == owner.Id)));
    }

    [Fact]
    public async Task Voice_pages_need_a_signed_in_person_and_staff_powers_need_the_superadmin()
    {
        var anon = Browser();
        foreach (var p in new[] { "/voice", "/me/friends", "/voice/rooms/anything" })
            Assert.StartsWith("/account/login", (await anon.GetAsync(p)).Headers.Location!.PathAndQuery());
        var user = await PersonAsync("Игрок");
        Assert.StartsWith("/account/denied", (await user.Browser.GetAsync("/admin/super/voice")).Headers.Location!.PathAndQuery());
    }
}
