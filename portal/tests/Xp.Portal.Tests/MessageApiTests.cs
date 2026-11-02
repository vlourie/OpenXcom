using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.AspNetCore.Identity;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Xp.Portal.Auth;
using Xp.Portal.Data;
using Xp.Portal.Devices;
using Xp.Portal.Messages;
using Xp.Portal.Voice;

namespace Xp.Portal.Tests;

/// <summary>
/// The launcher's side of private messages (ticket XP-000476): /api/v1/messages under the device token. The
/// rules themselves are MessageTests'; here: that the API is shut to anybody not linked, that it goes through
/// the same service (limits, blocks, text as typed), and that reading does not mark but the launcher can.
/// </summary>
public sealed class MessageApiTests(PortalFactory f) : IClassFixture<PortalFactory>
{
    const string Password = "Long-enough-passw0rd!";
    static readonly JsonSerializerOptions Web = new(JsonSerializerDefaults.Web);

    record Launcher(HttpClient Http, Guid Id, string Name);

    async Task<Launcher> LauncherAsync(string name)
    {
        name = $"{name}-{Guid.NewGuid().ToString("N")[..6]}";
        var email = $"pma-{Guid.NewGuid():N}@x.test";
        var id = await f.ScopedAsync(async sp =>
        {
            var users = sp.GetRequiredService<UserManager<PortalUser>>();
            var u = new PortalUser { UserName = email, Email = email, EmailConfirmed = true, DisplayName = name };
            Assert.True((await users.CreateAsync(u, Password)).Succeeded);
            return u.Id;
        });
        var token = DeviceSecrets.NewToken();
        await f.DbAsync(async db =>
        {
            db.DeviceTokens.Add(new DeviceToken { UserId = id, TokenHash = DeviceSecrets.Hash(token), Name = "test", CreatedAt = f.Clock.GetUtcNow() });
            return await db.SaveChangesAsync();
        });
        var c = f.CreateClient();
        c.DefaultRequestHeaders.Add("X-Device-Token", token);
        return new Launcher(c, id, name);
    }

    static async Task<string?> CodeOf(HttpResponseMessage r) =>
        JsonDocument.Parse(await r.Content.ReadAsStringAsync()).RootElement.TryGetProperty("code", out var c) ? c.GetString() : null;

    /// <summary>The clock of the tests stands still, and a dialogue is ordered by time: every message gets its own second.</summary>
    async Task<HttpResponseMessage> SendAsync(Launcher from, Launcher to, string body)
    {
        f.Clock.Advance(TimeSpan.FromSeconds(1));
        return await from.Http.PostAsJsonAsync($"/api/v1/messages/{to.Id}", new { body });
    }

    [Fact]
    public async Task Only_a_linked_launcher_gets_in()
    {
        Assert.Equal(HttpStatusCode.Unauthorized, (await f.CreateClient().GetAsync("/api/v1/messages")).StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, (await f.CreateClient().GetAsync("/api/v1/messages/unread")).StatusCode);
        var wrong = f.CreateClient();
        wrong.DefaultRequestHeaders.Add("X-Device-Token", DeviceSecrets.NewToken());
        Assert.Equal(HttpStatusCode.Unauthorized, (await wrong.GetAsync("/api/v1/messages")).StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, (await wrong.PostAsJsonAsync("/api/v1/messages", new { who = "кто-то", body = "x" })).StatusCode);
    }

    [Fact]
    public async Task A_message_goes_by_name_is_counted_listed_and_read_only_when_the_launcher_says_so()
    {
        var ann = await LauncherAsync("Анна");
        var bob = await LauncherAsync("Борис");

        var sent = await ann.Http.PostAsJsonAsync("/api/v1/messages", new { who = bob.Name, body = "Привет <b>Борис</b>\nhttps://evil.test/x" });
        Assert.Equal(HttpStatusCode.Created, sent.StatusCode);
        var made = (await sent.Content.ReadFromJsonAsync<SentResponse>(Web))!;
        Assert.Equal(bob.Id, made.To.Id);

        Assert.Equal(1, (await bob.Http.GetFromJsonAsync<UnreadResponse>("/api/v1/messages/unread", Web))!.Unread);
        var inbox = (await bob.Http.GetFromJsonAsync<InboxResponse>("/api/v1/messages", Web))!;
        Assert.Equal(1, inbox.Unread);
        var row = Assert.Single(inbox.Dialogues);
        Assert.Equal(ann.Id, row.Person.Id);
        Assert.Equal(1, row.Unread);
        Assert.False(row.LastMine);

        // looking does not read; the text comes as typed (the launcher shows it as text, the site escapes it)
        var thread = (await bob.Http.GetFromJsonAsync<ThreadResponse>($"/api/v1/messages/{ann.Id}", Web))!;
        Assert.Equal("Привет <b>Борис</b>\nhttps://evil.test/x", Assert.Single(thread.Messages).Body);
        Assert.Equal(1, thread.Total);
        Assert.Equal(50, thread.PerPage);
        Assert.Equal(1, (await bob.Http.GetFromJsonAsync<UnreadResponse>("/api/v1/messages/unread", Web))!.Unread);

        Assert.Equal(HttpStatusCode.NoContent, (await bob.Http.PostAsync($"/api/v1/messages/{ann.Id}/read", null)).StatusCode);
        Assert.Equal(0, (await bob.Http.GetFromJsonAsync<UnreadResponse>("/api/v1/messages/unread", Web))!.Unread);
        var again = (await ann.Http.GetFromJsonAsync<ThreadResponse>($"/api/v1/messages/{bob.Id}", Web))!;
        Assert.True(Assert.Single(again.Messages).Read);

        Assert.Equal(HttpStatusCode.Created, (await SendAsync(bob, ann, "Здравствуй.")).StatusCode);
        var feed = (await bob.Http.GetFromJsonAsync<ThreadResponse>($"/api/v1/messages/{ann.Id}", Web))!;
        Assert.Equal(["Привет <b>Борис</b>\nhttps://evil.test/x", "Здравствуй."], feed.Messages.Select(m => m.Body));
        Assert.Equal([false, true], feed.Messages.Select(m => m.Mine));
    }

    [Fact]
    public async Task The_service_rules_hold_over_the_api()
    {
        var ann = await LauncherAsync("Анна");
        var bob = await LauncherAsync("Борис");

        var empty = await SendAsync(ann, bob, "   ");
        Assert.Equal(HttpStatusCode.BadRequest, empty.StatusCode);
        Assert.Equal("empty", await CodeOf(empty));
        var big = await SendAsync(ann, bob, new string('я', MessageLimits.BodyMax + 1));
        Assert.Equal("too_long", await CodeOf(big));
        Assert.Equal(HttpStatusCode.Created, (await SendAsync(ann, bob, new string('я', MessageLimits.BodyMax))).StatusCode);
        Assert.Equal("self", await CodeOf(await ann.Http.PostAsJsonAsync($"/api/v1/messages/{ann.Id}", new { body = "себе" })));
        var nobody = await ann.Http.PostAsJsonAsync("/api/v1/messages", new { who = "Никто-такого-нет", body = "?" });
        Assert.Equal(HttpStatusCode.NotFound, nobody.StatusCode);
        Assert.Equal("user_not_found", await CodeOf(nobody));
        Assert.Equal(HttpStatusCode.NotFound, (await ann.Http.GetAsync($"/api/v1/messages/{Guid.NewGuid()}")).StatusCode);

        // a stranger who has not answered gets three messages and then silence
        await SendAsync(ann, bob, "два");
        await SendAsync(ann, bob, "три");
        var fourth = await SendAsync(ann, bob, "четыре");
        Assert.Equal(HttpStatusCode.TooManyRequests, fourth.StatusCode);
        Assert.Equal("limit_unanswered", await CodeOf(fourth));
    }

    [Fact]
    public async Task Block_refusal_and_complaint_go_through_the_api_like_on_the_site()
    {
        var ann = await LauncherAsync("Анна");
        var bob = await LauncherAsync("Борис");
        await SendAsync(bob, ann, "оскорбление");

        // the block is the site's one (voice and friends use it too)
        Assert.Equal(HttpStatusCode.NoContent, (await ann.Http.PutAsync($"/api/v1/blocks/{bob.Id}", null)).StatusCode);
        var mine = await SendAsync(ann, bob, "ответ");
        Assert.Equal(HttpStatusCode.Conflict, mine.StatusCode);
        Assert.Equal("you_blocked", await CodeOf(mine));
        var theirs = await SendAsync(bob, ann, "ещё");
        Assert.Equal(HttpStatusCode.Forbidden, theirs.StatusCode);
        Assert.Equal("refused", await CodeOf(theirs));
        Assert.True((await ann.Http.GetFromJsonAsync<ThreadResponse>($"/api/v1/messages/{bob.Id}", Web))!.IBlocked);

        var bad = (await ann.Http.GetFromJsonAsync<ThreadResponse>($"/api/v1/messages/{bob.Id}", Web))!.Messages[0];
        var complained = await ann.Http.PostAsJsonAsync($"/api/v1/messages/{bob.Id}/complaints", new { message = bad.Id, text = "оскорбляет" });
        Assert.Equal(HttpStatusCode.Created, complained.StatusCode);
        var ticket = (await complained.Content.ReadFromJsonAsync<ComplaintResult>(Web))!;
        Assert.True(ticket.Number > 0);
        var stranger = await LauncherAsync("Чужой");
        var none = await stranger.Http.PostAsJsonAsync($"/api/v1/messages/{bob.Id}/complaints", new { text = "ни за что" });
        Assert.Equal("no_dialogue", await CodeOf(none));
        Assert.Equal("complaint_invalid", await CodeOf(await ann.Http.PostAsJsonAsync($"/api/v1/messages/{bob.Id}/complaints", new { text = "  " })));

        Assert.Equal(HttpStatusCode.NoContent, (await ann.Http.DeleteAsync($"/api/v1/blocks/{bob.Id}")).StatusCode);
        Assert.Equal(HttpStatusCode.Created, (await SendAsync(ann, bob, "мир")).StatusCode);
    }

    [Fact]
    public async Task A_long_dialogue_comes_in_pages_newest_first()
    {
        var ann = await LauncherAsync("Анна");
        var bob = await LauncherAsync("Борис");
        // two people who write to each other: the limits (ten minutes, unanswered in a row) are not what is tested here
        await SendAsync(bob, ann, "первое");
        for (var i = 0; i < 54; i++)
        {
            Assert.Equal(HttpStatusCode.Created, (await SendAsync(ann, bob, $"m{i}")).StatusCode);
            if (i % 10 == 9)
            {
                f.Clock.Advance(TimeSpan.FromMinutes(11));
                Assert.Equal(HttpStatusCode.Created, (await SendAsync(bob, ann, $"b{i}")).StatusCode);
            }
        }
        // 1 + 54 + 5 answers
        var p1 = (await bob.Http.GetFromJsonAsync<ThreadResponse>($"/api/v1/messages/{ann.Id}", Web))!;
        var p2 = (await bob.Http.GetFromJsonAsync<ThreadResponse>($"/api/v1/messages/{ann.Id}?page=2", Web))!;
        Assert.Equal(60, p1.Total);
        Assert.Equal(50, p1.Messages.Count);
        Assert.Equal("m53", p1.Messages[^1].Body);
        Assert.Equal(10, p2.Messages.Count);
        Assert.Equal(2, p2.Page);
        Assert.Equal("первое", p2.Messages[0].Body);
    }
}
