using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Xp.Portal.Auth;
using Xp.Portal.Data;
using Xp.Portal.Devices;
using Xp.Portal.Voice;

namespace Xp.Portal.Tests;

/// <summary>
/// The text channels in the manner of IRC (docs/portal/VOICE_IRC.md): who may read and write, the commands and what they
/// leave behind in the log, the limits, the cursor, retention, and the page that shows it. Every rule is VoiceService's,
/// so most of this goes through the service; the API and the page are checked for translating it and for escaping.
/// </summary>
public sealed partial class ChannelTests(VoiceFactory f) : IClassFixture<VoiceFactory>
{
    const string Password = "Long-enough-passw0rd!";
    const string General = "ch-general";
    static readonly JsonSerializerOptions Web = new(JsonSerializerDefaults.Web);

    [GeneratedRegex("name=\"__RequestVerificationToken\" type=\"hidden\" value=\"([^\"]+)\"")]
    private static partial Regex AntiforgeryRx();

    // ---------------------------------------------------------------- helpers

    async Task<Guid> UserAsync(string name, string? role = null)
    {
        name = $"{name}-{Guid.NewGuid().ToString("N")[..6]}";
        var email = $"ch-{Guid.NewGuid():N}@x.test";
        return await f.ScopedAsync(async sp =>
        {
            var users = sp.GetRequiredService<UserManager<PortalUser>>();
            var u = new PortalUser { UserName = email, Email = email, EmailConfirmed = true, DisplayName = name };
            Assert.True((await users.CreateAsync(u, Password)).Succeeded);
            if (role is not null) await users.AddToRoleAsync(u, role);
            return u.Id;
        });
    }

    Task<string> NameOf(Guid id) => f.DbAsync(db => db.Users.Where(u => u.Id == id).Select(u => u.DisplayName).SingleAsync());

    Task V(Func<VoiceService, Task> act) => f.ScopedAsync(async sp => { await act(sp.GetRequiredService<VoiceService>()); return 0; });
    Task<T> V<T>(Func<VoiceService, Task<T>> act) => f.ScopedAsync(sp => act(sp.GetRequiredService<VoiceService>()));

    async Task<(string Code, int Status)> Why(Func<VoiceService, Task> act)
    {
        var e = await Assert.ThrowsAsync<VoiceException>(() => V(act));
        return (e.Code, e.Status);
    }

    Task<PostResult> Say(Guid me, string room, string text) => V(v => v.PostAsync(me, room, text, default));
    Task<MessagesView> Feed(Guid me, string room, long? after = null, int? limit = null) => V(v => v.MessagesAsync(me, room, after, limit, default));

    static List<string> Bodies(MessagesView v) => v.Lines.Where(l => l.Kind != "system").Select(l => l.Body).ToList();

    async Task<(string Code, Guid Id)> RoomAsync(Guid owner, string title = "Своя комната")
    {
        var room = await V(v => v.CreateRoomAsync(owner, title, default));
        var id = await f.DbAsync(db => db.VoiceRooms.Where(r => r.PublicId == room.PublicId).Select(r => r.Id).SingleAsync());
        return (room.PublicId, id);
    }

    Task<Guid> ChannelIdAsync(string code = General) => f.DbAsync(db => db.VoiceRooms.Where(r => r.PublicId == code).Select(r => r.Id).SingleAsync());

    /// <summary>A new, quiet channel of its own for a test, so that lines from other tests do not get into the count.</summary>
    async Task<(string Code, Guid Id)> OwnChannelAsync()
    {
        var code = "ch-" + Guid.NewGuid().ToString("N")[..7];
        var owner = await f.DbAsync(db => db.VoiceRooms.Where(r => r.PublicId == General).Select(r => r.OwnerId).SingleAsync());
        var id = await f.DbAsync(async db =>
        {
            var r = new VoiceRoom { PublicId = code, OwnerId = owner, Title = "#" + code, Capacity = 16, IsPublic = true, CreatedAt = f.Clock.GetUtcNow() };
            db.VoiceRooms.Add(r);
            await db.SaveChangesAsync();
            return r.Id;
        });
        return (code, id);
    }

    async Task FriendsAsync(Guid a, Guid b)
    {
        await V(v => v.RequestAsync(a, b, default));
        await V(v => v.RequestAsync(b, a, default));
    }

    // ---------------------------------------------------------------- the channels themselves

    [Fact]
    public async Task The_three_channels_exist_once_and_do_not_count_against_the_rooms_a_person_may_keep()
    {
        var rows = await f.DbAsync(db => db.VoiceRooms.Where(r => r.IsPublic).OrderBy(r => r.PublicId).Select(r => new { r.PublicId, r.Title, r.Topic }).ToListAsync());
        Assert.Equal(["ch-english", "ch-general", "ch-pomosch"], rows.Where(r => ChannelSeed.Channels.Any(c => c.PublicId == r.PublicId)).Select(r => r.PublicId));
        // the list and /voice go by CreatedAt: the general channel is the first one a player sees
        Assert.Equal(General, await f.DbAsync(db => db.VoiceRooms.Where(r => r.IsPublic).OrderBy(r => r.CreatedAt).Select(r => r.PublicId).FirstAsync()));
        Assert.Contains(rows, r => r.Title == "#общий");
        Assert.Contains(rows, r => r.Title == "#english");
        Assert.Contains(rows, r => r.Title == "#помощь");

        // the deployment runs the seed every time: nothing is added, and what staff changed stays changed
        var staff = await UserAsync("Персонал", Roles.Admin);
        await V(v => v.SetTopicAsync(staff, General, "Своя тема", default));
        var again = await f.ScopedAsync(async sp => await ChannelSeed.EnsureAsync(sp));
        Assert.Equal(0, again);
        Assert.Equal("Своя тема", await f.DbAsync(db => db.VoiceRooms.Where(r => r.PublicId == General).Select(r => r.Topic).SingleAsync()));
        Assert.Equal(1, await f.DbAsync(db => db.VoiceRooms.CountAsync(r => r.PublicId == General)));

        // a missing one comes back and only that one
        await f.DbAsync(async db => await db.VoiceRooms.Where(r => r.PublicId == "ch-english").ExecuteDeleteAsync());
        Assert.Equal(1, await f.ScopedAsync(async sp => await ChannelSeed.EnsureAsync(sp)));

        // the owner of the channels is an account nobody can sign in with
        var owner = await f.DbAsync(db => db.Users.SingleAsync(u => u.Email == ChannelSeed.OwnerEmail));
        Assert.Null(owner.PasswordHash);
        Assert.True(owner.LockoutEnd > f.Clock.GetUtcNow().AddYears(100));

        // the limit of rooms per owner counts the person's own rooms and not a channel they happen to own
        var me = await UserAsync("Строитель");
        await f.DbAsync(async db =>
        {
            db.VoiceRooms.Add(new VoiceRoom { PublicId = "ch-" + Guid.NewGuid().ToString("N")[..7], OwnerId = me, Title = "#его", Capacity = 16, IsPublic = true, CreatedAt = f.Clock.GetUtcNow() });
            return await db.SaveChangesAsync();
        });
        for (var i = 0; i < VoiceLimits.RoomsPerOwner; i++) await V(v => v.CreateRoomAsync(me, "Комната " + i, default));
        Assert.Equal("limit_rooms", (await Why(v => v.CreateRoomAsync(me, "Лишняя", default))).Code);

        // the list: channels on one side, the person's own rooms on the other, and no channel among the rooms
        var view = await V(v => v.ChannelsAsync(me, default));
        Assert.Contains(view.Channels, c => c.Room == General && c.State == "ok");
        Assert.Equal(VoiceLimits.RoomsPerOwner, view.Rooms.Count);
        Assert.DoesNotContain(view.Rooms, r => r.IsPublic);
    }

    // ---------------------------------------------------------------- who may do what

    [Fact]
    public async Task A_public_channel_is_open_to_anyone_signed_in_and_a_private_room_only_to_those_with_a_pass()
    {
        var (chan, _) = await OwnChannelAsync();
        var ann = await UserAsync("Анна");
        var bob = await UserAsync("Борис");
        var stranger = await UserAsync("Чужой");

        // free entry: the first look also writes a line, with no invite, no friendship
        var posted = await Say(ann, chan, "Привет всем");
        Assert.Equal("posted", posted.Result);
        Assert.Equal("Привет всем", posted.Line!.Body);
        var seen = await Feed(bob, chan);
        Assert.Equal(["Привет всем"], Bodies(seen));
        Assert.True(seen.IsPublic);
        Assert.True(seen.CanTalk);
        Assert.False(seen.CanModerate);

        // a private room: the owner and the invited friend; a stranger is told the same as for a room that is not there
        var (room, _) = await RoomAsync(ann);
        await FriendsAsync(ann, bob);
        await V(v => v.InviteAsync(ann, room, bob, default));
        await Say(ann, room, "Только для своих");
        Assert.Equal(["Только для своих"], Bodies(await Feed(bob, room)));
        await Say(bob, room, "Я здесь");
        Assert.Equal(("no_access", 404), await Why(v => v.MessagesAsync(stranger, room, null, null, default)));
        Assert.Equal(("no_access", 404), await Why(v => v.MessagesAsync(stranger, "zzzzzzzz22", null, null, default)));
        Assert.Equal(("no_access", 404), await Why(v => v.PostAsync(stranger, room, "я тоже", default)));
        Assert.Equal(("no_access", 404), await Why(v => v.JoinAsync(stranger, room, default)));
        Assert.Equal(("no_access", 404), await Why(v => v.DeleteLineAsync(stranger, room, 1, default)));
        Assert.DoesNotContain("я тоже", Bodies(await Feed(ann, room)));

        // the channels are not an way into a private room through the list either
        var theirs = await V(v => v.ChannelsAsync(stranger, default));
        Assert.DoesNotContain(theirs.Rooms, r => r.Room == room);
    }

    [Fact]
    public async Task A_person_banned_from_a_channel_or_from_voice_is_shut_out_of_its_text_too()
    {
        var (chan, _) = await OwnChannelAsync();
        var staff = await UserAsync("Модератор", Roles.Admin);
        var rude = await UserAsync("Грубиян");
        await Say(rude, chan, "до бана");

        await V(v => v.BanAsync(staff, chan, rude, "грубит", default));
        Assert.Equal(("banned", 403), await Why(v => v.PostAsync(rude, chan, "после", default)));
        Assert.Equal(("banned", 403), await Why(v => v.MessagesAsync(rude, chan, null, null, default)));
        Assert.DoesNotContain("после", Bodies(await Feed(staff, chan)));
        var row = (await V(v => v.ChannelsAsync(rude, default))).Channels.Single(c => c.Room == chan);
        Assert.Equal("banned", row.State);

        await V(v => v.UnbanAsync(staff, chan, rude, default));
        Assert.Equal("posted", (await Say(rude, chan, "прощён")).Result);

        // the ban of the account in voice takes the text away in every channel
        var admin = await UserAsync("Суперадмин", Roles.SuperAdmin);
        await V(v => v.AccountBanAsync(admin, rude, "спам", default));
        Assert.Equal(("account_banned", 403), await Why(v => v.PostAsync(rude, chan, "снова", default)));
        Assert.Equal(("account_banned", 403), await Why(v => v.PostAsync(rude, General, "и тут", default)));
        await V(v => v.AccountUnbanAsync(admin, rude, default));
        Assert.Equal("posted", (await Say(rude, chan, "вернулся")).Result);
    }

    [Fact]
    public async Task Lines_of_a_person_the_reader_blocked_are_not_handed_over_but_the_cursor_passes_them()
    {
        var (chan, _) = await OwnChannelAsync();
        var ann = await UserAsync("Анна");
        var troll = await UserAsync("Тролль");
        var carl = await UserAsync("Карл");
        await Say(troll, chan, "ту-ту");
        await Say(carl, chan, "здравствуйте");
        await V(v => v.BlockAsync(ann, troll, default));

        var seen = await Feed(ann, chan);
        Assert.Equal(["здравствуйте"], Bodies(seen));
        var last = await Feed(carl, chan);
        Assert.Equal(last.Last, seen.Last);

        await Say(troll, chan, "ещё раз");
        var next = await Feed(ann, chan, seen.Last);
        Assert.Empty(next.Lines);
        Assert.True(next.Last > seen.Last);
        // and the channel list does not count what the reader will never see
        Assert.Equal(0, (await V(v => v.ChannelsAsync(ann, default))).Channels.Single(c => c.Room == chan).Unread);
        Assert.Equal(["ту-ту", "здравствуйте", "ещё раз"], Bodies(await Feed(carl, chan)));
    }

    // ---------------------------------------------------------------- limits

    [Fact]
    public async Task A_line_is_at_most_a_thousand_characters_not_empty_and_twenty_in_a_minute()
    {
        var (chan, _) = await OwnChannelAsync();
        var ann = await UserAsync("Анна");
        var max = new string('ж', VoiceLimits.LineMax);
        Assert.Equal(max, (await Say(ann, chan, max)).Line!.Body);
        Assert.Equal("too_long", (await Why(v => v.PostAsync(ann, chan, max + "я", default))).Code);
        Assert.Equal("empty", (await Why(v => v.PostAsync(ann, chan, "   ", default))).Code);
        Assert.Equal("empty", (await Why(v => v.PostAsync(ann, chan, null, default))).Code);
        Assert.Equal("empty", (await Why(v => v.PostAsync(ann, chan, "/me", default))).Code);

        // a line is one line: a break in the text does not make two
        var one = await Say(ann, chan, "раз\nдва");
        Assert.DoesNotContain('\n', one.Line!.Body);

        // 20 in the minute; the join line and the commands are not words and do not use the quota
        var sent = 2;
        for (; sent < VoiceLimits.LinesPerMinute; sent++) await Say(ann, chan, "строка " + sent);
        var over = await Assert.ThrowsAsync<VoiceException>(() => Say(ann, chan, "лишняя"));
        Assert.Equal(("limit_rate", 429), (over.Code, over.Status));
        // the limit is the person's, not the channel's
        Assert.Equal("limit_rate", (await Why(v => v.PostAsync(ann, General, "в другом канале тоже нельзя", default))).Code);
        // a commands that is not a line is not counted
        Assert.Equal("unknown", (await Say(ann, chan, "/dance")).Result);
        // a minute later it is allowed again
        f.Clock.Advance(TimeSpan.FromSeconds(61));
        Assert.Equal("posted", (await Say(ann, chan, "минута прошла")).Result);
    }

    // ---------------------------------------------------------------- commands

    [Fact]
    public async Task Commands_do_what_the_buttons_do_with_the_same_rights_and_leave_the_same_log()
    {
        var (chan, chanId) = await OwnChannelAsync();
        var staff = await UserAsync("Модератор", Roles.Admin);
        var ann = await UserAsync("Анна");
        var bob = await UserAsync("Борис");
        var annName = await NameOf(ann);
        var bobName = await NameOf(bob);
        await Say(ann, chan, "я здесь");
        await Say(bob, chan, "и я");

        // /me is a line of its own kind
        var act = await Say(ann, chan, "/me машет рукой");
        Assert.Equal(("posted", "action", "машет рукой"), (act.Result, act.Line!.Kind, act.Line.Body));

        // /topic: anyone may read it, only the owner or staff may set it, and it is written to the log
        Assert.Equal("topic", (await Say(ann, chan, "/topic")).Result);
        Assert.Equal(("moderator_only", 403), await Why(v => v.PostAsync(ann, chan, "/topic Моя тема", default)));
        Assert.Equal("done", (await Say(staff, chan, "/topic Новая тема")).Result);
        Assert.Equal("Новая тема", (await Say(ann, chan, "/topic")).Text);
        Assert.Equal("Новая тема", (await Feed(ann, chan)).Topic);
        Assert.Equal("done", (await Say(staff, chan, "/topic -")).Result);
        Assert.Null((await Feed(ann, chan)).Topic);
        Assert.Equal("topic_too_long", (await Why(v => v.PostAsync(staff, chan, "/topic " + new string('т', VoiceLimits.TopicMax + 1), default))).Code);
        Assert.Contains("topic:Новая тема", await LogAsync(chanId));

        // /msg goes through the message service: a dialogue, with its limits and blocks
        var sent = await Say(ann, chan, $"/msg {bobName} тихо, только тебе");
        Assert.Equal(("private", bobName), (sent.Result, sent.Person!.Name));
        Assert.True(await f.DbAsync(db => db.PrivateMessages.AnyAsync(m => m.SenderId == ann && m.RecipientId == bob && m.Body == "тихо, только тебе")));
        Assert.DoesNotContain("тихо, только тебе", Bodies(await Feed(ann, chan)));
        Assert.Equal("user_not_found", (await Why(v => v.PostAsync(ann, chan, "/msg Никто-Такого привет", default))).Code);
        Assert.Equal("empty", (await Why(v => v.PostAsync(ann, chan, $"/msg {bobName}", default))).Code);
        await V(v => v.BlockAsync(bob, ann, default));
        Assert.StartsWith("msg_", (await Why(v => v.PostAsync(ann, chan, $"/msg {bobName} ещё", default))).Code);
        await V(v => v.UnblockAsync(bob, ann, default));

        // the moderators' commands: refused to everyone else, written to the log and to the feed as service lines
        Assert.Equal(("moderator_only", 403), await Why(v => v.PostAsync(ann, chan, $"/kick {bobName}", default)));
        Assert.Equal(("moderator_only", 403), await Why(v => v.PostAsync(ann, chan, $"/ban {bobName}", default)));
        Assert.Equal(("moderator_only", 403), await Why(v => v.PostAsync(ann, chan, $"/mute {bobName}", default)));
        Assert.Equal("done", (await Say(staff, chan, $"/mute {bobName} шумит")).Result);
        Assert.Equal("done", (await Say(staff, chan, $"/unmute @{bobName}")).Result);
        Assert.Equal("done", (await Say(staff, chan, $"/kick {bobName} спокойнее")).Result);
        Assert.Equal("done", (await Say(staff, chan, $"/ban {annName} флуд")).Result);
        Assert.Equal(("banned", 403), await Why(v => v.PostAsync(ann, chan, "после бана", default)));
        Assert.Equal("done", (await Say(staff, chan, $"/unban {annName}")).Result);
        Assert.Equal("posted", (await Say(ann, chan, "снова здесь")).Result);

        var log = await LogAsync(chanId, bob);
        Assert.Contains("mute:шумит", log);
        Assert.Contains("unmute:", log);
        Assert.Contains("kick:спокойнее", log);
        var annLog = await LogAsync(chanId, ann);
        Assert.Contains("ban:флуд", annLog);
        Assert.Contains("unban:", annLog);
        var events = (await Feed(staff, chan)).Lines.Where(l => l.Kind == "system").Select(l => l.Event).ToList();
        Assert.Contains("kick", events);
        Assert.Contains("ban", events);
        Assert.Contains("unban", events);
        Assert.Contains("topic", events);

        // staff cannot be put out by a command, nor the owner of a room by the guest
        var staffName = await NameOf(staff);
        Assert.Equal("owner_target", (await Why(v => v.PostAsync(staff, chan, $"/kick {staffName}", default))).Code);

        // an unknown command is answered with a hint and is never a line of the feed
        var before = await f.DbAsync(db => db.RoomMessages.CountAsync(m => m.RoomId == chanId));
        var unknown = await Say(ann, chan, "/dance сейчас же");
        Assert.Equal(("unknown", "/dance"), (unknown.Result, unknown.Command));
        Assert.Null(unknown.Line);
        Assert.Equal("client", (await Say(ann, chan, "/help")).Result);
        Assert.Equal(before, await f.DbAsync(db => db.RoomMessages.CountAsync(m => m.RoomId == chanId)));
        Assert.DoesNotContain(Bodies(await Feed(ann, chan)), b => b.StartsWith('/'));
    }

    async Task<List<string>> LogAsync(Guid room, Guid? user = null)
    {
        var rows = await f.DbAsync(db => db.VoiceEvents.Where(e => e.RoomId == room && (user == null || e.UserId == user))
            .Select(e => new { e.Kind, e.Reason }).ToListAsync());
        return rows.Select(r => r.Kind + ":" + r.Reason).ToList();
    }

    [Fact]
    public async Task The_owner_of_a_private_room_has_the_commands_and_the_guest_does_not()
    {
        var owner = await UserAsync("Хозяин");
        var guest = await UserAsync("Гость");
        await FriendsAsync(owner, guest);
        var (room, id) = await RoomAsync(owner);
        await V(v => v.InviteAsync(owner, room, guest, default));
        var guestName = await NameOf(guest);
        await Say(guest, room, "привет");

        Assert.Equal(("owner_only", 403), await Why(v => v.PostAsync(guest, room, "/topic тема гостя", default)));
        Assert.Equal("done", (await Say(owner, room, "/topic Рейд в восемь")).Result);
        Assert.Equal("Рейд в восемь", (await Feed(guest, room)).Topic);
        Assert.Equal("done", (await Say(owner, room, $"/kick {guestName} тише")).Result);
        Assert.Contains("kick:тише", await LogAsync(id, guest));
        // kicked from a room means the invite is gone, as with the button
        Assert.Equal("invite_revoked", (await Why(v => v.PostAsync(guest, room, "ещё", default))).Code);
    }

    [Fact]
    public async Task A_line_is_taken_out_by_its_author_the_owner_or_staff_and_a_service_line_stays()
    {
        var (chan, chanId) = await OwnChannelAsync();
        var staff = await UserAsync("Модератор", Roles.Admin);
        var ann = await UserAsync("Анна");
        var bob = await UserAsync("Борис");
        var mine = (await Say(ann, chan, "моя строка")).Line!.Id;
        var other = (await Say(bob, chan, "чужая строка")).Line!.Id;
        var third = (await Say(bob, chan, "третья строка")).Line!.Id;

        await V(v => v.DeleteLineAsync(ann, chan, mine, default));
        Assert.Equal(("moderator_only", 403), await Why(v => v.DeleteLineAsync(ann, chan, other, default)));
        Assert.Equal(("message_not_found", 404), await Why(v => v.DeleteLineAsync(ann, chan, mine, default)));
        await V(v => v.DeleteLineAsync(staff, chan, other, default));
        Assert.Contains("line_delete:", await LogAsync(chanId, bob));
        Assert.Equal(["третья строка"], Bodies(await Feed(ann, chan)));

        var service = await f.DbAsync(db => db.RoomMessages.Where(m => m.RoomId == chanId && m.Kind == ChatKinds.System).Select(m => m.Id).FirstAsync());
        Assert.Equal("message_not_found", (await Why(v => v.DeleteLineAsync(staff, chan, service, default))).Code);

        // a client that already has the line learns that it is gone, for a few minutes
        var after = await Feed(bob, chan, third - 1);
        Assert.Equal([third], after.Lines.Select(l => l.Id));
        var polled = await Feed(bob, chan, third);
        Assert.Contains(mine, polled.Removed);
        Assert.Contains(other, polled.Removed);
        f.Clock.Advance(VoiceLimits.RemovedNotice + TimeSpan.FromSeconds(5));
        Assert.Empty((await Feed(bob, chan, third)).Removed);
    }

    // ---------------------------------------------------------------- cursor, unread, mentions

    [Fact]
    public async Task The_cursor_gives_only_what_came_after_it_and_a_limit_cuts_the_history()
    {
        var (chan, _) = await OwnChannelAsync();
        var ann = await UserAsync("Анна");
        var ids = new List<long>();
        for (var i = 1; i <= 5; i++) ids.Add((await Say(ann, chan, "строка " + i)).Line!.Id);

        var all = await Feed(ann, chan);
        Assert.Equal(5, Bodies(all).Count);
        Assert.Equal(ids[^1], all.Last);
        var newest = await Feed(ann, chan, limit: 2);
        Assert.Equal(["строка 4", "строка 5"], Bodies(newest));
        var later = await Feed(ann, chan, ids[2]);
        Assert.Equal(["строка 4", "строка 5"], Bodies(later));
        // nothing new: the same cursor back
        var none = await Feed(ann, chan, ids[^1]);
        Assert.Empty(none.Lines);
        Assert.Equal(ids[^1], none.Last);
        // paging by the cursor never skips a line
        var first = await Feed(ann, chan, ids[0] - 1, 2);
        var second = await Feed(ann, chan, first.Last, 2);
        Assert.Equal(["строка 1", "строка 2", "строка 3", "строка 4"], Bodies(first).Concat(Bodies(second)));
        // a limit beyond the maximum is the maximum, below one is one
        Assert.Single((await Feed(ann, chan, limit: 0)).Lines);
        Assert.Equal(5, (await Feed(ann, chan, limit: 100000)).Lines.Count(l => l.Kind != "system"));
    }

    [Fact]
    public async Task What_is_new_and_who_was_called_by_name_is_counted_for_the_reader()
    {
        var (chan, _) = await OwnChannelAsync();
        var ann = await UserAsync("Анна");
        var bob = await UserAsync("Борис");
        var bobName = await NameOf(bob);
        await V(v => v.JoinAsync(bob, chan, default));

        await Say(ann, chan, "просто строка");
        await Say(ann, chan, $"{bobName.ToUpperInvariant()}, ты тут?");
        await Say(ann, chan, $"@{bobName} ответь");
        await Say(ann, chan, $"{bobName}ов не звали");
        var row = (await V(v => v.ChannelsAsync(bob, default))).Channels.Single(c => c.Room == chan);
        Assert.True(row.Joined);
        Assert.Equal(4, row.Unread);
        Assert.Equal(2, row.Mentions);
        Assert.Equal(["просто строка", $"{bobName.ToUpperInvariant()}, ты тут?", $"@{bobName} ответь", $"{bobName}ов не звали"], Bodies(await Feed(bob, chan)));
        var lines = (await Feed(bob, chan)).Lines.Where(l => l.Kind != "system").ToList();
        Assert.Equal([false, true, true, false], lines.Select(l => l.Mention));

        // looking is reading; one's own line is not new to oneself
        row = (await V(v => v.ChannelsAsync(bob, default))).Channels.Single(c => c.Room == chan);
        Assert.Equal((0, 0), (row.Unread, row.Mentions));
        await Say(bob, chan, "я тут");
        Assert.Equal(0, (await V(v => v.ChannelsAsync(bob, default))).Channels.Single(c => c.Room == chan).Unread);
        // a person who left or never joined has nothing counted
        await V(v => v.PartAsync(bob, chan, default));
        await Say(ann, chan, "пока без тебя");
        Assert.Equal(0, (await V(v => v.ChannelsAsync(bob, default))).Channels.Single(c => c.Room == chan).Unread);
    }

    [Theory]
    [InlineData("Борис", "борис, привет", true)]
    [InlineData("Борис", "@Борис", true)]
    [InlineData("Борис", "Борисов", false)]
    [InlineData("Борис", "супер_Борис", false)]
    [InlineData("Борис", "ну что, Борис?", true)]
    [InlineData("a.b", "a.b!", true)]
    [InlineData("a.b", "axb", false)]
    [InlineData("", "что угодно", false)]
    public void A_mention_is_the_nick_as_a_word_of_its_own(string nick, string body, bool expected) =>
        Assert.Equal(expected, VoiceService.Mentions(body, nick));

    // ---------------------------------------------------------------- retention

    [Fact]
    public async Task Lines_are_kept_thirty_days_and_a_complaint_keeps_the_ones_it_rests_on()
    {
        var owner = await UserAsync("Хозяин");
        var guest = await UserAsync("Гость");
        await FriendsAsync(owner, guest);
        var (room, roomId) = await RoomAsync(owner);
        await V(v => v.InviteAsync(owner, room, guest, default));
        await Say(guest, room, "оскорбление");
        await Say(owner, room, "ответ хозяина");
        var (chan, chanId) = await OwnChannelAsync();
        await Say(guest, chan, "старая строка канала");

        var ticket = await V(v => v.ComplainAsync(owner, room, guest, "Оскорбляет", default));
        var held = await f.DbAsync(db => db.RoomMessageTickets.Where(t => t.TicketId == ticket.Id).Select(t => t.MessageId).ToListAsync());
        Assert.NotEmpty(held);
        // the complaint carries the lines of the feed as text, marked for the one complained about
        var description = await f.DbAsync(db => db.Tickets.Where(t => t.Id == ticket.Id).Select(t => t.Description).SingleAsync());
        Assert.Contains("оскорбление", description);
        Assert.Matches("► \\[[^\\]]+\\] .*: оскорбление", description);

        f.Clock.Advance(TimeSpan.FromDays(10));
        await Say(owner, room, "свежая строка");
        f.Clock.Advance(TimeSpan.FromDays(21));
        var worker = ActivatorUtilities.CreateInstance<VoiceWorker>(f.Services);
        await worker.PruneAsync(default);

        // older than thirty days: gone, unless a complaint holds it
        Assert.False(await f.DbAsync(db => db.RoomMessages.AnyAsync(m => m.RoomId == chanId && m.Body == "старая строка канала")));
        Assert.Equal(held.Count, await f.DbAsync(db => db.RoomMessages.CountAsync(m => held.Contains(m.Id))));
        Assert.True(await f.DbAsync(db => db.RoomMessages.AnyAsync(m => m.RoomId == roomId && m.Body == "свежая строка")));

        // the complaint is closed: held for a year more, then let go
        await f.ScopedAsync(async sp =>
        {
            var t = await sp.GetRequiredService<PortalDb>().Tickets.SingleAsync(x => x.Id == ticket.Id);
            await sp.GetRequiredService<Xp.Portal.Tickets.TicketService>().ChangeStatusAsync(t, TicketStatus.Resolved, owner, default);
            return 0;
        });
        await worker.PruneAsync(default);
        Assert.Equal(held.Count, await f.DbAsync(db => db.RoomMessages.CountAsync(m => held.Contains(m.Id))));
        f.Clock.Advance(TimeSpan.FromDays(366));
        await worker.PruneAsync(default);
        Assert.Equal(0, await f.DbAsync(db => db.RoomMessages.CountAsync(m => held.Contains(m.Id))));
        Assert.Equal(0, await f.DbAsync(db => db.RoomMessageTickets.CountAsync(t => t.TicketId == ticket.Id)));
    }

    // ---------------------------------------------------------------- the API

    async Task<HttpClient> LauncherAsync(Guid id)
    {
        var token = DeviceSecrets.NewToken();
        await f.DbAsync(async db =>
        {
            db.DeviceTokens.Add(new DeviceToken { UserId = id, TokenHash = DeviceSecrets.Hash(token), Name = "test", CreatedAt = f.Clock.GetUtcNow() });
            return await db.SaveChangesAsync();
        });
        var c = f.CreateClient();
        c.DefaultRequestHeaders.Add("X-Device-Token", token);
        return c;
    }

    static async Task<string?> CodeOf(HttpResponseMessage r) =>
        JsonDocument.Parse(await r.Content.ReadAsStringAsync()).RootElement.TryGetProperty("code", out var c) ? c.GetString() : null;

    [Fact]
    public async Task The_api_lists_reads_after_a_cursor_writes_and_refuses_the_unknown()
    {
        var (chan, _) = await OwnChannelAsync();
        var ann = await UserAsync("Анна");
        var bob = await UserAsync("Борис");
        var annHttp = await LauncherAsync(ann);
        var bobHttp = await LauncherAsync(bob);
        var base_ = $"/api/v1/voice/rooms/{chan}";

        // closed to anybody who is not signed in, and to a wrong token
        Assert.Equal(HttpStatusCode.Unauthorized, (await f.CreateClient().GetAsync("/api/v1/voice/channels")).StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, (await f.CreateClient().GetAsync(base_ + "/messages")).StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, (await f.CreateClient().PostAsJsonAsync(base_ + "/messages", new { text = "x" })).StatusCode);

        var sent = await annHttp.PostAsJsonAsync(base_ + "/messages", new { text = "Привет из лаунчера" });
        Assert.Equal(HttpStatusCode.OK, sent.StatusCode);
        var made = JsonDocument.Parse(await sent.Content.ReadAsStringAsync()).RootElement;
        Assert.Equal("posted", made.GetProperty("result").GetString());
        var id = made.GetProperty("line").GetProperty("id").GetInt64();

        var got = JsonDocument.Parse(await bobHttp.GetStringAsync(base_ + "/messages")).RootElement;
        Assert.Equal("Привет из лаунчера", got.GetProperty("lines").EnumerateArray().Last().GetProperty("body").GetString());
        Assert.Equal(id, got.GetProperty("last").GetInt64());
        Assert.True(got.GetProperty("isPublic").GetBoolean());
        var after = JsonDocument.Parse(await bobHttp.GetStringAsync(base_ + $"/messages?after={id}")).RootElement;
        Assert.Equal(0, after.GetProperty("lines").GetArrayLength());
        Assert.Equal(id, after.GetProperty("last").GetInt64());

        // a command is parsed by the server, not the client; the unknown one is a hint, not a line
        var hint = JsonDocument.Parse(await (await annHttp.PostAsJsonAsync(base_ + "/messages", new { text = "/dance" })).Content.ReadAsStringAsync()).RootElement;
        Assert.Equal("unknown", hint.GetProperty("result").GetString());
        Assert.Equal(JsonValueKind.Null, hint.GetProperty("line").ValueKind);
        var forbidden = await bobHttp.PostAsJsonAsync(base_ + "/messages", new { text = "/topic своя" });
        Assert.Equal(HttpStatusCode.Forbidden, forbidden.StatusCode);
        Assert.Equal("moderator_only", await CodeOf(forbidden));

        // the list: the channel is there, with what is new for the one who joined
        Assert.Equal(HttpStatusCode.NoContent, (await bobHttp.PostAsync(base_ + "/join", null)).StatusCode);
        await annHttp.PostAsJsonAsync(base_ + "/messages", new { text = "ещё одна" });
        var list = JsonDocument.Parse(await bobHttp.GetStringAsync("/api/v1/voice/channels")).RootElement;
        var mine = list.GetProperty("channels").EnumerateArray().Single(c => c.GetProperty("room").GetString() == chan);
        Assert.Equal(1, mine.GetProperty("unread").GetInt32());
        Assert.True(mine.GetProperty("joined").GetBoolean());

        // taking out a line, going out, a stranger, and the limits of the body
        Assert.Equal(HttpStatusCode.Forbidden, (await bobHttp.DeleteAsync(base_ + $"/messages/{id}")).StatusCode);
        Assert.Equal(HttpStatusCode.NoContent, (await annHttp.DeleteAsync(base_ + $"/messages/{id}")).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await annHttp.DeleteAsync(base_ + $"/messages/{id}")).StatusCode);
        Assert.Equal(HttpStatusCode.NoContent, (await bobHttp.PostAsync(base_ + "/part", null)).StatusCode);
        Assert.Equal(HttpStatusCode.BadRequest, (await annHttp.PostAsJsonAsync(base_ + "/messages", new { text = new string('я', VoiceLimits.LineMax + 1) })).StatusCode);
        Assert.Equal(HttpStatusCode.BadRequest, (await annHttp.PostAsJsonAsync(base_ + "/messages", new { text = "" })).StatusCode);

        var (room, _) = await RoomAsync(ann);
        var stranger = await bobHttp.GetAsync($"/api/v1/voice/rooms/{room}/messages");
        var nowhere = await bobHttp.GetAsync("/api/v1/voice/rooms/zzzzzzzz22/messages");
        Assert.Equal((HttpStatusCode.NotFound, HttpStatusCode.NotFound), (stranger.StatusCode, nowhere.StatusCode));
        Assert.Equal(await CodeOf(nowhere), await CodeOf(stranger));

        // the twenty-first line of the minute is a 429 with its code
        for (var i = 0; i < VoiceLimits.LinesPerMinute; i++) await annHttp.PostAsJsonAsync(base_ + "/messages", new { text = "поток " + i });
        var rate = await annHttp.PostAsJsonAsync(base_ + "/messages", new { text = "лишняя" });
        Assert.Equal(HttpStatusCode.TooManyRequests, rate.StatusCode);
        Assert.Equal("limit_rate", await CodeOf(rate));
    }

    // ---------------------------------------------------------------- the pages

    HttpClient Browser() => f.CreateClient(new WebApplicationFactoryClientOptions { AllowAutoRedirect = false, HandleCookies = true });

    static async Task<HttpResponseMessage> PostForm(HttpClient c, string url, Dictionary<string, string> fields, string? tokenFrom = null)
    {
        var html = await c.GetStringAsync(tokenFrom ?? url);
        fields["__RequestVerificationToken"] = AntiforgeryRx().Match(html) is { Success: true } m
            ? m.Groups[1].Value
            : throw new Xunit.Sdk.XunitException("no antiforgery token on " + (tokenFrom ?? url));
        return await c.PostAsync(url, new FormUrlEncodedContent(fields));
    }

    async Task<(HttpClient Browser, Guid Id, string Name)> PersonAsync(string name, string? role = null)
    {
        var id = await UserAsync(name, role);
        var email = await f.DbAsync(db => db.Users.Where(u => u.Id == id).Select(u => u.Email!).SingleAsync());
        var c = Browser();
        var r = await PostForm(c, "/account/login", new() { ["Email"] = email, ["Password"] = Password });
        Assert.Equal(HttpStatusCode.Redirect, r.StatusCode);
        return (c, id, await NameOf(id));
    }

    [Fact]
    public async Task The_page_shows_three_columns_escapes_every_line_and_links_only_web_addresses()
    {
        var (chan, _) = await OwnChannelAsync();
        var ann = await PersonAsync("Анна");
        var url = $"/voice/rooms/{chan}";

        var page = WebUtility.HtmlDecode(await ann.Browser.GetStringAsync(url));
        Assert.Contains("class=\"chan-list\"", page);
        Assert.Contains("class=\"chan-main\"", page);
        Assert.Contains("class=\"chan-who\"", page);
        Assert.Contains("#общий", page);
        Assert.Contains("/js/channel.js", page);

        // what a player writes is text and nothing else
        var evil = "<script>alert(1)</script> <img src=x onerror=alert(2)> https://example.test/a?b=1&c=2 javascript:alert(3) [x](javascript:alert(4))";
        var r = await PostForm(ann.Browser, $"{url}?handler=Say", new() { ["line"] = evil }, tokenFrom: url);
        Assert.Equal(HttpStatusCode.Redirect, r.StatusCode);
        var raw = await ann.Browser.GetStringAsync(url);
        Assert.DoesNotContain("<script>alert(1)", raw);
        Assert.DoesNotContain("<img src=x", raw);
        Assert.Contains("&lt;script&gt;alert(1)&lt;/script&gt;", raw);
        Assert.Matches("<a [^>]*href=\"https://example.test/a\\?b=1&amp;c=2\"[^>]*rel=\"nofollow noopener\"", raw);
        Assert.DoesNotContain("href=\"javascript:", raw);

        // a name with markup in it is escaped as well, in the feed and in the list of who is here
        var markup = await PersonAsync("<b>Жирный</b>");
        await PostForm(markup.Browser, $"{url}?handler=Say", new() { ["line"] = "я здесь" }, tokenFrom: url);
        var withName = await ann.Browser.GetStringAsync(url);
        Assert.DoesNotContain("<b>Жирный</b>", withName);
        Assert.Contains("&lt;b&gt;Жирный&lt;/b&gt;", withName);

        // an unknown command comes back as a hint on the page and is not a line
        r = await PostForm(ann.Browser, $"{url}?handler=Say", new() { ["line"] = "/dance" }, tokenFrom: url);
        Assert.Equal(HttpStatusCode.Redirect, r.StatusCode);
        var hinted = WebUtility.HtmlDecode(await ann.Browser.GetStringAsync(url));
        Assert.Contains("Нет такой команды: /dance", hinted);
        Assert.DoesNotContain("&lt;" + ann.Name + "&gt; /dance", hinted);
        Assert.False(await f.DbAsync(db => db.RoomMessages.AnyAsync(m => m.Body.StartsWith("/dance"))));
        // and the hint is shown once
        Assert.DoesNotContain("Нет такой команды", WebUtility.HtmlDecode(await ann.Browser.GetStringAsync(url)));
    }

    [Fact]
    public async Task The_form_needs_its_token_the_stranger_gets_the_same_404_and_the_old_links_still_work()
    {
        var (chan, _) = await OwnChannelAsync();
        var ann = await PersonAsync("Анна");
        var stranger = await PersonAsync("Чужой");
        var (room, _) = await RoomAsync(ann.Id, "Моя для проверки");
        // the invite form lists friends, so the owner needs one
        await FriendsAsync(ann.Id, await UserAsync("Друг"));

        var bare = await ann.Browser.PostAsync($"/voice/rooms/{chan}?handler=Say", new FormUrlEncodedContent(new Dictionary<string, string> { ["line"] = "без токена" }));
        Assert.Equal(HttpStatusCode.BadRequest, bare.StatusCode);
        Assert.False(await f.DbAsync(db => db.RoomMessages.AnyAsync(m => m.Body == "без токена")));

        // the link of a room that was sent around before is its page, with the controls one click away
        var old = await ann.Browser.GetAsync($"/voice/rooms/{room}");
        Assert.Equal(HttpStatusCode.OK, old.StatusCode);
        var html = await old.Content.ReadAsStringAsync();
        Assert.Contains($"/voice/rooms/{room}/manage", html);
        var manage = await ann.Browser.GetAsync($"/voice/rooms/{room}/manage");
        Assert.Equal(HttpStatusCode.OK, manage.StatusCode);
        var managed = await manage.Content.ReadAsStringAsync();
        Assert.Contains("handler=Invite", managed);
        Assert.Contains("handler=Delete", managed);

        // a channel can be managed only by staff: others see the page without the owner's controls
        var theirs = await stranger.Browser.GetAsync($"/voice/rooms/{room}/manage");
        Assert.Equal(HttpStatusCode.NotFound, theirs.StatusCode);
        var inChannel = await stranger.Browser.GetStringAsync($"/voice/rooms/{chan}/manage");
        Assert.DoesNotContain("handler=Invite", inChannel);
        Assert.DoesNotContain("handler=Delete", inChannel);

        // /voice itself opens the first channel for a person with no rooms
        var start = await stranger.Browser.GetAsync("/voice");
        Assert.Equal(HttpStatusCode.OK, start.StatusCode);
        Assert.Contains("#общий", WebUtility.HtmlDecode(await start.Content.ReadAsStringAsync()));
    }
}
