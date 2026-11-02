using System.Net;
using System.Text.RegularExpressions;
using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Xp.Portal.Auth;
using Xp.Portal.Data;
using Xp.Portal.Messages;
using Xp.Portal.Voice;

namespace Xp.Portal.Tests;

/// <summary>
/// Private messages (ticket XP-000476) as people use them: text between two accounts, the unread
/// counter, the limits against spam, block and complaint, deleting for oneself, the e-mail and the
/// way out of it. Staff are shown at the end not to see a dialogue they are not part of.
/// </summary>
public sealed partial class MessageTests(PortalFactory f) : IClassFixture<PortalFactory>
{
    const string Password = "Long-enough-passw0rd!";

    HttpClient Browser() => f.CreateClient(new WebApplicationFactoryClientOptions { AllowAutoRedirect = false, HandleCookies = true });

    [GeneratedRegex("name=\"__RequestVerificationToken\" type=\"hidden\" value=\"([^\"]+)\"")]
    private static partial Regex AntiforgeryRx();

    [GeneratedRegex("<main[^>]*>(.*)</main>", RegexOptions.Singleline)]
    private static partial Regex MainRx();

    static async Task<HttpResponseMessage> PostForm(HttpClient c, string url, Dictionary<string, string> fields, string? tokenFrom = null)
    {
        var html = await c.GetStringAsync(tokenFrom ?? url.Split('?')[0]);
        fields["__RequestVerificationToken"] = AntiforgeryRx().Match(html) is { Success: true } m
            ? m.Groups[1].Value
            : throw new Xunit.Sdk.XunitException("no antiforgery token on " + (tokenFrom ?? url));
        return await c.PostAsync(url, new FormUrlEncodedContent(fields));
    }

    static async Task<string> Read(HttpResponseMessage r) => System.Net.WebUtility.HtmlDecode(await r.Content.ReadAsStringAsync());

    record Person(HttpClient Browser, Guid Id, string Name, string Email);

    async Task<Person> PersonAsync(string name, string? role = null, string? permission = null)
    {
        var email = $"pm-{Guid.NewGuid():N}@x.test";
        name = $"{name}-{Guid.NewGuid().ToString("N")[..6]}";
        var id = await f.ScopedAsync(async sp =>
        {
            var users = sp.GetRequiredService<UserManager<PortalUser>>();
            var u = new PortalUser { UserName = email, Email = email, EmailConfirmed = true, DisplayName = name };
            Assert.True((await users.CreateAsync(u, Password)).Succeeded);
            if (role is not null) await users.AddToRoleAsync(u, role);
            return u.Id;
        });
        if (permission is not null)
            await f.DbAsync(async db => { db.UserPermissions.Add(new UserPermission { UserId = id, Permission = permission }); return await db.SaveChangesAsync(); });
        var c = Browser();
        var r = await PostForm(c, "/account/login", new() { ["Email"] = email, ["Password"] = Password });
        Assert.Equal(HttpStatusCode.Redirect, r.StatusCode);
        return new Person(c, id, name, email);
    }

    Task M(Func<MessageService, Task> act) => f.ScopedAsync(async sp => { await act(sp.GetRequiredService<MessageService>()); return 0; });
    Task<T> M<T>(Func<MessageService, Task<T>> act) => f.ScopedAsync(sp => act(sp.GetRequiredService<MessageService>()));

    /// <summary>The clock of the tests stands still, and a dialogue is ordered by time: every message gets its own second.</summary>
    Task<PrivateMessage> Send(Person from, Person to, string text)
    {
        f.Clock.Advance(TimeSpan.FromSeconds(1));
        return M(m => m.SendAsync(from.Id, to.Id, text, default));
    }

    async Task<string> Code(Func<Task> act)
    {
        var e = await Assert.ThrowsAsync<MessageException>(act);
        return e.Code;
    }

    async Task FriendsAsync(Person a, Person b)
    {
        await f.ScopedAsync(async sp => { var v = sp.GetRequiredService<VoiceService>(); await v.RequestAsync(a.Id, b.Id, default); return 0; });
        await f.ScopedAsync(async sp => { var v = sp.GetRequiredService<VoiceService>(); await v.RequestAsync(b.Id, a.Id, default); return 0; });
    }

    [Fact]
    public async Task A_message_by_name_reaches_the_other_with_a_counter_and_is_shown_as_plain_text()
    {
        var ann = await PersonAsync("Анна");
        var bob = await PersonAsync("Борис");

        var text = "Привет!\nСтрока <b>два</b> <script>alert(1)</script> https://evil.test/x";
        var r = await PostForm(ann.Browser, "/me/messages?handler=Send", new() { ["who"] = bob.Name, ["body"] = text });
        Assert.Equal(HttpStatusCode.Redirect, r.StatusCode);
        Assert.Equal($"/me/messages/{bob.Id}", r.Headers.Location!.OriginalString);

        // the counter sits in the header of every page, and the inbox says who wrote
        var home = await bob.Browser.GetStringAsync("/");
        Assert.Matches("<span class=\"unread-count\"[^>]*>1</span>", home);
        var inbox = await Read(await bob.Browser.GetAsync("/me/messages"));
        Assert.Contains(ann.Name, inbox);
        Assert.Contains("Привет!", inbox);

        // opening the dialogue reads it: the counter goes
        var raw = await (await bob.Browser.GetAsync($"/me/messages/{ann.Id}")).Content.ReadAsStringAsync();
        var main = MainRx().Match(raw).Groups[1].Value;
        Assert.Contains("&lt;script&gt;alert(1)&lt;/script&gt;", main);
        Assert.DoesNotContain("<script>alert", main);
        Assert.DoesNotContain("<b>два</b>", main);
        Assert.DoesNotContain("<a href=\"https://evil.test", main);   // a link in a message is text, not a link
        Assert.Contains("https://evil.test/x", WebUtility.HtmlDecode(main));
        Assert.DoesNotMatch("class=\"unread-count\"", await bob.Browser.GetStringAsync("/"));

        // the answer, and the sender sees it was read
        f.Clock.Advance(TimeSpan.FromSeconds(1));
        r = await PostForm(bob.Browser, $"/me/messages/{ann.Id}?handler=Send", new() { ["body"] = "Здравствуй." }, tokenFrom: $"/me/messages/{ann.Id}");
        Assert.Equal(HttpStatusCode.Redirect, r.StatusCode);
        var feed = await Read(await ann.Browser.GetAsync($"/me/messages/{bob.Id}"));
        Assert.True(feed.IndexOf("Привет!", StringComparison.Ordinal) is var first and >= 0 && feed.IndexOf("Здравствуй.", StringComparison.Ordinal) is var second && first < second,
            MainRx().Match(feed).Groups[1].Value);
        Assert.Contains("прочитано", feed);
    }

    [Fact]
    public async Task Only_a_signed_in_person_writes_and_reads()
    {
        var anon = Browser();
        var r = await anon.GetAsync("/me/messages");
        Assert.Equal(HttpStatusCode.Redirect, r.StatusCode);
        Assert.StartsWith("/account/login", r.Headers.Location!.OriginalString.Replace("http://localhost", ""));
        var someone = await PersonAsync("Некто");
        r = await anon.GetAsync($"/me/messages/{someone.Id}");
        Assert.Equal(HttpStatusCode.Redirect, r.StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await someone.Browser.GetAsync($"/me/messages/{Guid.NewGuid()}")).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await someone.Browser.GetAsync($"/me/messages/{someone.Id}")).StatusCode);
    }

    [Fact]
    public async Task Length_emptiness_and_oneself_are_refused()
    {
        var ann = await PersonAsync("Анна");
        var bob = await PersonAsync("Борис");
        Assert.Equal("empty", await Code(() => Send(ann, bob, "   \n ")));
        Assert.Equal("too_long", await Code(() => Send(ann, bob, new string('я', MessageLimits.BodyMax + 1))));
        Assert.Equal("self", await Code(() => Send(ann, ann, "себе")));
        Assert.Equal("user_not_found", await Code(() => M(m => m.SendAsync(ann.Id, Guid.NewGuid(), "никому", default))));
        // the longest allowed goes through whole
        var max = new string('ж', MessageLimits.BodyMax);
        await Send(ann, bob, max);
        Assert.Equal(max, await f.DbAsync(db => db.PrivateMessages.Where(x => x.SenderId == ann.Id).Select(x => x.Body).SingleAsync()));
        // the page says it in words, not as a key
        var r = await PostForm(ann.Browser, "/me/messages?handler=Send", new() { ["who"] = bob.Name, ["body"] = new string('я', MessageLimits.BodyMax + 1) });
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Contains("Сообщение длиннее 4000 символов.", await Read(r));
    }

    [Fact]
    public async Task A_stranger_who_does_not_answer_gets_three_messages_a_friend_more()
    {
        var spammer = await PersonAsync("Спамер");
        var victim = await PersonAsync("Жертва");
        for (var i = 0; i < MessageLimits.UnansweredStranger; i++) await Send(spammer, victim, "раз " + i);
        Assert.Equal("limit_unanswered", await Code(() => Send(spammer, victim, "ещё")));
        // an answer opens the conversation again
        await Send(victim, spammer, "слушаю");
        await Send(spammer, victim, "спасибо");

        var a = await PersonAsync("Друг");
        var b = await PersonAsync("Подруга");
        await FriendsAsync(a, b);
        for (var i = 0; i < MessageLimits.UnansweredStranger + 2; i++) await Send(a, b, "друзьям можно " + i);
    }

    [Fact]
    public async Task Too_many_in_ten_minutes_and_too_many_strangers_in_a_day_are_stopped()
    {
        var talker = await PersonAsync("Болтун");
        var friends = new List<Person>();
        for (var i = 0; i < MessageLimits.PerTenMinutes; i++)
        {
            // each to a person who wrote first, so only the rate limit can stop it
            var other = await PersonAsync("Собеседник");
            await Send(other, talker, "привет");
            await Send(talker, other, "и вам");
            friends.Add(other);
        }
        // 30 sent in the ten minutes: the next is too many, whoever it is for
        Assert.Equal("limit_rate", await Code(() => Send(talker, friends[0], "ещё")));
        f.Clock.Advance(TimeSpan.FromMinutes(11));
        await Send(talker, friends[0], "теперь можно");

        // strangers: ten dialogues with people who never wrote back, then no more new ones
        var cold = await PersonAsync("Холодный");
        var coldOnes = new List<Person>();
        for (var i = 0; i < MessageLimits.StrangersPerDay; i++)
        {
            var s = await PersonAsync("Незнакомец");
            await Send(cold, s, "здравствуйте");
            coldOnes.Add(s);
        }
        var eleventh = await PersonAsync("Одиннадцатый");
        Assert.Equal("limit_strangers", await Code(() => Send(cold, eleventh, "и вам здравствуйте")));
        await Send(cold, coldOnes[0], "второе");   // an old dialogue is not a new stranger
    }

    [Fact]
    public async Task Blocking_shuts_the_door_both_ways_without_telling_the_blocked_and_lifts()
    {
        var ann = await PersonAsync("Анна");
        var bob = await PersonAsync("Борис");
        await FriendsAsync(ann, bob);
        await Send(ann, bob, "ты тут?");

        var r = await PostForm(bob.Browser, $"/me/messages/{ann.Id}?handler=Block", new(), tokenFrom: $"/me/messages/{ann.Id}");
        Assert.Equal(HttpStatusCode.Redirect, r.StatusCode);
        Assert.Contains("Собеседник заблокирован.", await Read(await bob.Browser.GetAsync($"/me/messages/{ann.Id}")));
        // the friendship went with it
        Assert.False(await f.DbAsync(db => db.Friendships.AnyAsync(x => x.UserLowId == ann.Id || x.UserHighId == ann.Id)));

        // the one shut out gets a plain refusal, the one who blocked is told to lift the block first
        Assert.Equal("refused", await Code(() => Send(ann, bob, "ответь")));
        Assert.Equal("you_blocked", await Code(() => Send(bob, ann, "прости")));
        var page = await Read(await PostForm(ann.Browser, $"/me/messages/{bob.Id}?handler=Send", new() { ["body"] = "ответь" }, tokenFrom: $"/me/messages/{bob.Id}"));
        Assert.Contains("этот человек не принимает сообщения", page);
        Assert.DoesNotContain("заблокировали", page);

        r = await PostForm(bob.Browser, $"/me/messages/{ann.Id}?handler=Unblock", new(), tokenFrom: $"/me/messages/{ann.Id}");
        Assert.Equal(HttpStatusCode.Redirect, r.StatusCode);
        await Send(ann, bob, "вот и я");
    }

    [Fact]
    public async Task A_complaint_goes_to_staff_as_a_voice_ticket_with_a_copy_of_the_dialogue_and_staff_see_no_dialogues()
    {
        var troll = await PersonAsync("Тролль");
        var victim = await PersonAsync("Пострадавший");
        var moderator = await PersonAsync("Модератор", Roles.Admin, "tickets.voice");
        await Send(troll, victim, "первое безобидное");
        var bad = await Send(troll, victim, "второе: гадость про маму");
        await Send(victim, troll, "прекрати");

        var r = await PostForm(victim.Browser, $"/me/messages/{troll.Id}?handler=Complain", new() { ["message"] = bad.Id.ToString(), ["text"] = "оскорбляет" },
            tokenFrom: $"/me/messages/{troll.Id}");
        Assert.Equal(HttpStatusCode.Redirect, r.StatusCode);
        Assert.Contains("Жалоба отправлена модераторам.", await Read(await victim.Browser.GetAsync($"/me/messages/{troll.Id}")));

        var ticket = await f.DbAsync(db => db.Tickets.SingleAsync(t => t.AuthorId == victim.Id));
        Assert.Equal(Categories.Voice, ticket.Category);
        Assert.Equal(TicketSource.Voice, ticket.Source);
        Assert.Contains("оскорбляет", ticket.Description);
        Assert.Contains("► [", ticket.Description);                         // the message complained about is marked
        Assert.Contains("второе: гадость про маму", ticket.Description);
        Assert.Contains("первое безобидное", ticket.Description);           // and the dialogue around it
        Assert.Contains(troll.Name, ticket.Description);
        Assert.Contains(troll.Id.ToString(), ticket.Description);

        // a complaint needs something of theirs to complain about, and a message that is theirs
        var stranger = await PersonAsync("Посторонний");
        Assert.Equal("no_dialogue", await Code(() => M(m => m.ComplainAsync(victim.Id, stranger.Id, null, "ни за что", default))));
        Assert.Equal("message_not_found", await Code(() => M(m => m.ComplainAsync(victim.Id, troll.Id, Guid.NewGuid(), "нет такого", default))));
        Assert.Equal("complaint_invalid", await Code(() => M(m => m.ComplainAsync(victim.Id, troll.Id, null, "  ", default))));

        // staff open the ticket, and have no page that lists or opens somebody else's dialogue
        // (the ticket page sends staff to the queue, which wants the second factor; the copy is in the ticket itself, checked above)
        var shown = await moderator.Browser.GetAsync($"/t/{ticket.Number}");
        Assert.Equal($"/admin/tickets/{ticket.Number}", shown.Headers.Location?.OriginalString);
        var theirs = await Read(await moderator.Browser.GetAsync($"/me/messages/{troll.Id}"));
        Assert.DoesNotContain("гадость", theirs);
        var inbox = await Read(await moderator.Browser.GetAsync("/me/messages"));
        Assert.DoesNotContain("гадость", inbox);
        Assert.DoesNotContain(troll.Name, inbox);
    }

    [Fact]
    public async Task A_long_dialogue_is_copied_into_a_complaint_within_the_ticket_limit_and_an_old_message_is_not_lost()
    {
        var a = await PersonAsync("Автор");
        var b = await PersonAsync("Жалобщик");
        var old = await Send(a, b, "самое старое, на него жалоба");
        // eight long messages: the copy of the newest cannot fit them all, and must still reach the old one
        for (var i = 0; i < 8; i++)
        {
            await Send(a, b, $"длинное {i} " + new string('ы', 3800));
            await Send(b, a, "ответ");
        }
        var t = await M(m => m.ComplainAsync(b.Id, a.Id, old.Id, "см. старое", default));
        var saved = await f.DbAsync(db => db.Tickets.SingleAsync(x => x.Id == t.Id));
        Assert.True(saved.Description.Length <= Limits.TextMax);
        Assert.Contains("самое старое, на него жалоба", saved.Description);
        Assert.True(saved.Description.Contains("длинное 7"), saved.Description.Length + " " + saved.Description[..Math.Min(600, saved.Description.Length)]);
    }

    [Fact]
    public async Task Delete_is_for_oneself_and_the_message_goes_when_both_have_deleted_it()
    {
        var ann = await PersonAsync("Анна");
        var bob = await PersonAsync("Борис");
        var m = await Send(ann, bob, "удали меня");

        var r = await PostForm(ann.Browser, $"/me/messages/{bob.Id}?handler=Delete", new() { ["message"] = m.Id.ToString() }, tokenFrom: $"/me/messages/{bob.Id}");
        Assert.Equal(HttpStatusCode.Redirect, r.StatusCode);
        Assert.DoesNotContain("удали меня", await Read(await ann.Browser.GetAsync($"/me/messages/{bob.Id}")));
        Assert.Contains("удали меня", await Read(await bob.Browser.GetAsync($"/me/messages/{ann.Id}")));
        Assert.True(await f.DbAsync(db => db.PrivateMessages.AnyAsync(x => x.Id == m.Id)));

        // somebody else's message cannot be deleted
        var third = await PersonAsync("Третий");
        Assert.Equal("message_not_found", await Code(() => M(s => s.DeleteAsync(third.Id, m.Id, default))));

        await PostForm(bob.Browser, $"/me/messages/{ann.Id}?handler=Delete", new() { ["message"] = m.Id.ToString() }, tokenFrom: $"/me/messages/{ann.Id}");
        Assert.False(await f.DbAsync(db => db.PrivateMessages.AnyAsync(x => x.Id == m.Id)));
        // a deleted unread message is not counted
        var n = await Send(ann, bob, "ещё");
        Assert.Equal(1, await M(s => s.UnreadAsync(bob.Id)));
        await M(s => s.DeleteAsync(bob.Id, n.Id, default));
        Assert.Equal(0, await M(s => s.UnreadAsync(bob.Id)));
    }

    [Fact]
    public async Task The_letter_is_opt_in_one_per_run_without_the_text_and_the_link_in_it_turns_it_off()
    {
        var ann = await PersonAsync("Анна");
        var bob = await PersonAsync("Борис");

        // off by default: nothing is sent to a person who never asked
        await Send(ann, bob, "первое без письма");
        Assert.Empty(RegistrationTests.Letters(f, bob.Email));

        var r = await PostForm(bob.Browser, "/me/messages?handler=Notice", new() { ["on"] = "true" }, tokenFrom: "/me/messages");
        Assert.Equal(HttpStatusCode.Redirect, r.StatusCode);
        Assert.Contains("Письма о новых сообщениях включены.", await Read(await bob.Browser.GetAsync("/me/messages")));
        await bob.Browser.GetAsync($"/me/messages/{ann.Id}");   // reads what waits

        await Send(ann, bob, "СЕКРЕТНЫЙ ТЕКСТ второго");
        await Send(ann, bob, "третье, пока второе не прочитано");
        var letters = RegistrationTests.Letters(f, bob.Email);
        var letter = Assert.Single(letters);                   // one letter for the run
        Assert.Contains(ann.Name, letter);
        Assert.Contains($"https://portal.test/me/messages/{ann.Id}", letter);
        Assert.DoesNotContain("СЕКРЕТНЫЙ ТЕКСТ", letter);       // the text never leaves the site
        var link = Regex.Match(letter, @"https://portal\.test(/account/unsubscribe\?[^\s]+)").Groups[1].Value;
        Assert.NotEmpty(link);

        // a forged link does nothing; the real one works without signing in, and only for the person it names
        var anon = Browser();
        var forged = Regex.Replace(link, "sig=[^&\\s]+", "sig=AAAA");
        Assert.Contains("Ссылка не подошла", await Read(await anon.GetAsync(forged)));
        Assert.True(await M(s => s.EmailNoticeAsync(bob.Id, default)));
        var done = await anon.GetAsync(link);
        Assert.Equal(HttpStatusCode.OK, done.StatusCode);
        Assert.Contains("письма о новых личных сообщениях больше не приходят", await Read(done));
        Assert.False(await M(s => s.EmailNoticeAsync(bob.Id, default)));
        var swapped = Regex.Replace(link, "u=[0-9a-f-]+", "u=" + ann.Id);
        Assert.Contains("Ссылка не подошла", await Read(await anon.GetAsync(swapped)));
    }

    [Fact]
    public void Strings_exist_in_both_languages_for_everything_the_pages_say()
    {
        var text = f.Services.GetRequiredService<Xp.Portal.Site.Text>();
        string[] keys =
        [
            "nav.messages", "msg.title", "msg.intro", "msg.send", "msg.block", "msg.complain", "msg.delete", "msg.notice",
            "msg.err.limit_rate", "msg.err.limit_unanswered", "msg.err.refused", "msg.err.you_blocked", "msg.unsub.done", "mail.pm.subject", "mail.pm.body",
        ];
        foreach (var lang in new[] { "ru", "en" })
            foreach (var k in keys)
                Assert.NotEqual(k, text.In(lang, k));
        Assert.NotEqual(text.In("ru", "msg.title"), text.In("en", "msg.title"));
    }
}
