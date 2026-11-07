using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.AspNetCore.Identity;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Xp.Portal.Data;
using Xp.Portal.Tickets;

namespace Xp.Portal.Tests;

/// <summary>/api/v1/bot: the key, its categories and networks, and what the bot may do to a ticket.</summary>
public sealed class BotApiTests(PortalFactory f) : IClassFixture<PortalFactory>
{
    static readonly byte[] Png = [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0, 0, 0, 13, 0x49, 0x48, 0x44, 0x52];

    async Task<CreateTicketResponse> TicketAsync(string category = "code", string title = "Tank turret jumps off in mode 0")
    {
        var body = new { category, title, description = "Turret drawn 32 px off the hull.", gameVersion = "2026.10.20-17", consentToFiles = true, language = "ru" };
        var r = await f.CreateClient().PostAsJsonAsync("/api/v1/tickets", body);
        Assert.True(r.IsSuccessStatusCode, await r.Content.ReadAsStringAsync());
        return (await r.Content.ReadFromJsonAsync<CreateTicketResponse>())!;
    }

    async Task<BotAccounts.Created> KeyAsync(string? categories = null, string? networks = null) =>
        await f.ScopedAsync(sp => BotAccounts.CreateAsync(sp, "Автоматика " + Guid.NewGuid().ToString("N")[..6], categories, networks));

    HttpClient Bot(string? key)
    {
        var c = f.CreateClient();
        if (key is not null) c.DefaultRequestHeaders.Add(BotApi.KeyHeader, key);
        return c;
    }

    static async Task<string> CodeOf(HttpResponseMessage r) => (await r.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("code").GetString()!;

    [Fact]
    public async Task No_key_a_wrong_key_and_a_revoked_key_all_get_401()
    {
        var t = await TicketAsync();
        Assert.Equal(HttpStatusCode.Unauthorized, (await Bot(null).GetAsync("/api/v1/bot/tickets")).StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, (await Bot("wrong-key-wrong-key-wrong-key").GetAsync($"/api/v1/bot/tickets/{t.Number}")).StatusCode);

        var k = await KeyAsync();
        Assert.Equal(HttpStatusCode.OK, (await Bot(k.Secret).GetAsync("/api/v1/bot/tickets")).StatusCode);
        Assert.Equal(1, await f.ScopedAsync(sp => BotAccounts.RevokeAsync(sp, k.Key.Name)));
        var r = await Bot(k.Secret).GetAsync("/api/v1/bot/tickets");
        Assert.Equal(HttpStatusCode.Unauthorized, r.StatusCode);
        Assert.Equal("bot_key_unknown", await CodeOf(r));
    }

    [Fact]
    public async Task Only_the_hash_is_stored_and_nobody_signs_in_as_the_bot()
    {
        var k = await KeyAsync();
        var row = await f.DbAsync(db => db.BotKeys.SingleAsync(x => x.Id == k.Key.Id));
        Assert.NotEqual(k.Secret, row.TokenHash);
        Assert.Equal(64, row.TokenHash.Length);
        var user = await f.ScopedAsync(async sp =>
        {
            var users = sp.GetRequiredService<UserManager<PortalUser>>();
            var u = (await users.FindByIdAsync(row.UserId.ToString()))!;
            return (u, await users.HasPasswordAsync(u), await users.IsLockedOutAsync(u), await users.GetRolesAsync(u));
        });
        Assert.False(user.Item2);                       // no password to guess
        Assert.True(user.Item3);                        // locked to the end of time
        Assert.Empty(user.Item4);                       // no role: the key is not a staff sign-in
        Assert.False(user.u.EmailConfirmed);
        Assert.EndsWith("@bot.invalid", user.u.Email);
    }

    [Fact]
    public async Task The_key_sees_only_its_categories()
    {
        var code = await TicketAsync("code");
        var art = await TicketAsync("graphics", "Blurry slopes in the jungle");
        var k = await KeyAsync("code");
        var list = await Bot(k.Secret).GetFromJsonAsync<List<BotTicketRow>>("/api/v1/bot/tickets?status=all");
        Assert.Contains(list!, x => x.Number == code.Number);
        Assert.DoesNotContain(list!, x => x.Number == art.Number);
        // another category's ticket does not exist for this key: same 404 as a wrong number
        Assert.Equal(HttpStatusCode.NotFound, (await Bot(k.Secret).GetAsync($"/api/v1/bot/tickets/{art.Number}")).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await Bot(k.Secret).PostAsJsonAsync($"/api/v1/bot/tickets/{art.Number}/status", new { status = "InProgress" })).StatusCode);
    }

    [Fact]
    public async Task Voice_complaints_stay_out_unless_named()
    {
        var k = await KeyAsync();
        Assert.DoesNotContain("voice", BotApi.SplitList(k.Key.Categories));
    }

    [Fact]
    public async Task A_key_bound_to_a_network_refuses_other_addresses()
    {
        var k = await KeyAsync(networks: "203.0.113.0/24");
        // the test server has no client address at all: not inside the network
        Assert.Equal(HttpStatusCode.Unauthorized, (await Bot(k.Secret).GetAsync("/api/v1/bot/tickets")).StatusCode);
        Assert.True(BotApi.Allowed("203.0.113.0/24", IPAddress.Parse("203.0.113.7")));
        Assert.True(BotApi.Allowed("198.51.100.1, 203.0.113.0/24", IPAddress.Parse("198.51.100.1")));
        Assert.False(BotApi.Allowed("203.0.113.0/24", IPAddress.Parse("198.51.100.1")));
        Assert.True(BotApi.Allowed("", null));
        await Assert.ThrowsAsync<ArgumentException>(() => f.ScopedAsync(sp => BotAccounts.CreateAsync(sp, "bad net", null, "not-a-network")));
    }

    [Fact]
    public async Task Bot_takes_a_ticket_into_work_with_a_note_and_answers_the_player()
    {
        var t = await TicketAsync();
        var k = await KeyAsync();
        var bot = Bot(k.Secret);

        var view = await bot.GetFromJsonAsync<BotTicketView>($"/api/v1/bot/tickets/{t.Number}");
        Assert.Equal("New", view!.Status);
        Assert.Equal("ru", view.Language);
        Assert.Equal("2026.10.20-17", view.GameVersion);

        var r = await bot.PostAsJsonAsync($"/api/v1/bot/tickets/{t.Number}/status", new { status = "InProgress", note = "taken by the automation" });
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        view = await r.Content.ReadFromJsonAsync<BotTicketView>();
        Assert.Equal("InProgress", view!.Status);
        var move = Assert.Single(view.History, h => h.Action == "status");
        Assert.Equal(("New", "InProgress", k.Key.Name), (move.From, move.To, move.Actor));
        var note = Assert.Single(view.Messages);
        Assert.True(note.Internal);
        Assert.Equal(k.Key.Name, note.Author);

        r = await bot.PostAsJsonAsync($"/api/v1/bot/tickets/{t.Number}/messages", new { body = "Взяли в работу.", @internal = false });
        Assert.Equal(HttpStatusCode.NoContent, r.StatusCode);

        // the player sees the answer, never the note
        var guest = f.CreateClient();
        guest.DefaultRequestHeaders.Add(TicketApi.TokenHeader, t.Token);
        var seen = await guest.GetFromJsonAsync<TicketView>($"/api/v1/tickets/{t.Number}");
        Assert.Equal("InProgress", seen!.Status);
        var answer = Assert.Single(seen.Messages);
        Assert.True(answer.FromStaff);
        Assert.Equal("Взяли в работу.", answer.Body);
    }

    [Fact]
    public async Task A_move_the_workflow_forbids_is_409_and_changes_nothing()
    {
        var t = await TicketAsync();
        var bot = Bot((await KeyAsync()).Secret);
        Assert.Equal(HttpStatusCode.OK, (await bot.PostAsJsonAsync($"/api/v1/bot/tickets/{t.Number}/status", new { status = "Resolved" })).StatusCode);
        var r = await bot.PostAsJsonAsync($"/api/v1/bot/tickets/{t.Number}/status", new { status = "NeedsInfo", note = "lost" });
        Assert.Equal(HttpStatusCode.Conflict, r.StatusCode);
        Assert.Equal("status_move_invalid", await CodeOf(r));
        var view = await bot.GetFromJsonAsync<BotTicketView>($"/api/v1/bot/tickets/{t.Number}");
        Assert.Equal("Resolved", view!.Status);
        Assert.Empty(view.Messages);
        Assert.Equal("status_invalid", await CodeOf(await bot.PostAsJsonAsync($"/api/v1/bot/tickets/{t.Number}/status", new { status = "Done" })));
    }

    [Fact]
    public async Task A_player_writing_to_a_resolved_ticket_brings_it_back_to_the_queue()
    {
        var t = await TicketAsync();
        var bot = Bot((await KeyAsync()).Secret);
        await bot.PostAsJsonAsync($"/api/v1/bot/tickets/{t.Number}/status", new { status = "Resolved" });
        var guest = f.CreateClient();
        guest.DefaultRequestHeaders.Add(TicketApi.TokenHeader, t.Token);
        Assert.Equal(HttpStatusCode.NoContent, (await guest.PostAsJsonAsync($"/api/v1/tickets/{t.Number}/messages", new { body = "Всё ещё сдвинута." })).StatusCode);
        var list = await bot.GetFromJsonAsync<List<BotTicketRow>>("/api/v1/bot/tickets?status=Triaged");
        Assert.Contains(list!, x => x.Number == t.Number);
    }

    [Fact]
    public async Task Duplicate_needs_the_original()
    {
        var first = await TicketAsync();
        var second = await TicketAsync();
        var bot = Bot((await KeyAsync()).Secret);
        Assert.Equal(HttpStatusCode.BadRequest, (await bot.PostAsJsonAsync($"/api/v1/bot/tickets/{second.Number}/status", new { status = "Duplicate" })).StatusCode);
        var r = await bot.PostAsJsonAsync($"/api/v1/bot/tickets/{second.Number}/status", new { status = "Duplicate", duplicateOf = first.Number });
        var view = await r.Content.ReadFromJsonAsync<BotTicketView>();
        Assert.Equal(("Duplicate", (long?)first.Number), (view!.Status, view.DuplicateOf));
    }

    [Fact]
    public async Task List_takes_statuses_and_defaults_to_the_open_ones()
    {
        var open = await TicketAsync();
        var done = await TicketAsync();
        var bot = Bot((await KeyAsync()).Secret);
        await bot.PostAsJsonAsync($"/api/v1/bot/tickets/{done.Number}/status", new { status = "Resolved" });

        var list = await bot.GetFromJsonAsync<List<BotTicketRow>>("/api/v1/bot/tickets");
        Assert.Contains(list!, x => x.Number == open.Number);
        Assert.DoesNotContain(list!, x => x.Number == done.Number);
        list = await bot.GetFromJsonAsync<List<BotTicketRow>>("/api/v1/bot/tickets?status=resolved");
        Assert.Equal([done.Number], list!.Select(x => x.Number));
        Assert.Equal(HttpStatusCode.BadRequest, (await bot.GetAsync("/api/v1/bot/tickets?status=bogus")).StatusCode);
    }

    [Fact]
    public async Task Files_come_as_downloads_once_scanned_and_never_from_another_ticket()
    {
        var t = await TicketAsync();
        var other = await TicketAsync();
        var guest = f.CreateClient();
        guest.DefaultRequestHeaders.Add(TicketApi.TokenHeader, t.Token);
        var m = new MultipartFormDataContent();
        var c = new ByteArrayContent(Png);
        c.Headers.ContentType = new MediaTypeHeaderValue("application/octet-stream");
        m.Add(c, "file", "shot.png");
        Assert.Equal(HttpStatusCode.Created, (await guest.PostAsync($"/api/v1/tickets/{t.Number}/attachments", m)).StatusCode);

        var bot = Bot((await KeyAsync()).Secret);
        var view = await bot.GetFromJsonAsync<BotTicketView>($"/api/v1/bot/tickets/{t.Number}");
        var file = Assert.Single(view!.Attachments);
        Assert.Equal("Pending", file.Scan);
        var url = $"/api/v1/bot/tickets/{t.Number}/files/{file.Id}";
        var r = await bot.GetAsync(url);
        Assert.Equal(HttpStatusCode.Conflict, r.StatusCode);
        Assert.Equal("file_not_ready", await CodeOf(r));

        await f.DbAsync(db => db.TicketAttachments.Where(a => a.Id == file.Id).ExecuteUpdateAsync(s => s.SetProperty(a => a.Scan, ScanStatus.Clean)));
        r = await bot.GetAsync(url);
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Equal("application/octet-stream", r.Content.Headers.ContentType!.MediaType);
        Assert.Equal(Png, await r.Content.ReadAsByteArrayAsync());
        Assert.Equal(HttpStatusCode.NotFound, (await bot.GetAsync($"/api/v1/bot/tickets/{other.Number}/files/{file.Id}")).StatusCode);
    }

    [Fact]
    public async Task Bot_routes_stay_out_of_the_published_api()
    {
        var doc = JsonDocument.Parse(await f.CreateClient().GetStringAsync("/openapi/v1.json"));
        Assert.DoesNotContain(doc.RootElement.GetProperty("paths").EnumerateObject(), p => p.Name.StartsWith("/api/v1/bot"));
    }
}
