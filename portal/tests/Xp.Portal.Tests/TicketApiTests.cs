using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Xp.Portal.Data;
using Xp.Portal.Files;
using Xp.Portal.Notifications;
using Xp.Portal.Tickets;

namespace Xp.Portal.Tests;

public sealed class TicketApiTests(PortalFactory f) : IClassFixture<PortalFactory>
{
    static readonly byte[] Png = [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0, 0, 0, 13, 0x49, 0x48, 0x44, 0x52];

    static object Body(string title = "Game freezes on the geoscape", string category = "code", bool consent = false, string? email = null) => new
    {
        category, title, description = "After saving, the globe stops turning.", gameVersion = "2026.09.22", modVersion = "HD 1.0",
        email, consentToFiles = consent,
    };

    async Task<CreateTicketResponse> CreateAsync(object? body = null, string? key = null)
    {
        using var req = new HttpRequestMessage(HttpMethod.Post, "/api/v1/tickets") { Content = JsonContent.Create(body ?? Body()) };
        if (key is not null) req.Headers.Add("Idempotency-Key", key);
        var r = await f.CreateClient().SendAsync(req);
        Assert.True(r.IsSuccessStatusCode, await r.Content.ReadAsStringAsync());
        return (await r.Content.ReadFromJsonAsync<CreateTicketResponse>())!;
    }

    HttpClient Guest(string? token)
    {
        var c = f.CreateClient();
        if (token is not null) c.DefaultRequestHeaders.Add(TicketApi.TokenHeader, token);
        return c;
    }

    [Fact]
    public async Task Guest_creates_a_ticket_and_reads_it_with_the_link_only()
    {
        var t = await CreateAsync();
        Assert.StartsWith("XP-", t.DisplayNumber);
        Assert.NotNull(t.Token);
        Assert.Equal($"https://portal.test/t/{t.Number}?k={t.Token}", t.Url);

        var view = await Guest(t.Token).GetFromJsonAsync<TicketView>($"/api/v1/tickets/{t.Number}");
        Assert.Equal("New", view!.Status);

        Assert.Equal(HttpStatusCode.NotFound, (await Guest(null).GetAsync($"/api/v1/tickets/{t.Number}")).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await Guest("wrong-token-wrong-token").GetAsync($"/api/v1/tickets/{t.Number}")).StatusCode);
    }

    [Fact]
    public async Task Another_tickets_token_opens_nothing()   // IDOR: numbers are sequential, tokens are not
    {
        var mine = await CreateAsync();
        var theirs = await CreateAsync(Body("someone else's"));
        var r = await Guest(mine.Token).GetAsync($"/api/v1/tickets/{theirs.Number}");
        Assert.Equal(HttpStatusCode.NotFound, r.StatusCode);
        var problem = await r.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("not_found", problem.GetProperty("code").GetString());
    }

    [Fact]
    public async Task Same_idempotency_key_returns_the_same_ticket_and_link()
    {
        var key = Guid.NewGuid().ToString();
        var a = await CreateAsync(key: key);
        var b = await CreateAsync(key: key);
        Assert.Equal(a.Number, b.Number);
        Assert.Equal(a.Token, b.Token);
        Assert.Equal(1, await f.DbAsync(db => db.Tickets.CountAsync(t => t.Number == a.Number)));
    }

    [Fact]
    public async Task Same_key_with_another_body_is_a_conflict()
    {
        var key = Guid.NewGuid().ToString();
        await CreateAsync(key: key);
        using var req = new HttpRequestMessage(HttpMethod.Post, "/api/v1/tickets") { Content = JsonContent.Create(Body("different title")) };
        req.Headers.Add("Idempotency-Key", key);
        var r = await f.CreateClient().SendAsync(req);
        Assert.Equal(HttpStatusCode.Conflict, r.StatusCode);
    }

    [Fact]
    public async Task Parallel_retries_with_one_key_make_one_ticket()
    {
        var key = Guid.NewGuid().ToString();
        var results = await Task.WhenAll(Enumerable.Range(0, 8).Select(_ => CreateAsync(key: key)));
        Assert.Single(results.Select(r => r.Number).Distinct());
        Assert.Single(results.Select(r => r.Token).Distinct());
    }

    [Theory]
    [InlineData("nonsense", "category_invalid")]
    [InlineData("", "category_invalid")]
    public async Task Bad_category_is_refused_with_a_code(string category, string code)
    {
        var r = await f.CreateClient().PostAsJsonAsync("/api/v1/tickets", Body(category: category));
        Assert.Equal(HttpStatusCode.BadRequest, r.StatusCode);
        var p = await r.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal(code, p.GetProperty("code").GetString());
        Assert.True(p.TryGetProperty("traceId", out _));
        Assert.DoesNotContain("   at ", await r.Content.ReadAsStringAsync());   // no stack trace
    }

    [Fact]
    public async Task Too_long_title_is_refused()
    {
        var r = await f.CreateClient().PostAsJsonAsync("/api/v1/tickets", Body(new string('x', 141)));
        Assert.Equal(HttpStatusCode.BadRequest, r.StatusCode);
    }

    [Fact]
    public async Task Control_and_bidi_characters_are_dropped_from_the_title()
    {
        var t = await CreateAsync(Body("evil‮txt.exe\u0007 title\nwith break"));
        var title = await f.DbAsync(db => db.Tickets.Where(x => x.Number == t.Number).Select(x => x.Title).FirstAsync());
        Assert.Equal("eviltxt.exe title with break", title);
    }

    // ---- attachments ----

    static MultipartFormDataContent File(string name, byte[] data)
    {
        var m = new MultipartFormDataContent();
        var c = new ByteArrayContent(data);
        c.Headers.ContentType = new MediaTypeHeaderValue("application/octet-stream");
        m.Add(c, "file", name);
        return m;
    }

    async Task<HttpResponseMessage> UploadAsync(CreateTicketResponse t, string name, byte[] data) =>
        await Guest(t.Token).PostAsync($"/api/v1/tickets/{t.Number}/attachments", File(name, data));

    async Task<string> CodeOf(HttpResponseMessage r) => (await r.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("code").GetString()!;

    [Fact]
    public async Task Png_is_accepted_and_stored_under_a_generated_key()
    {
        var t = await CreateAsync();
        var r = await UploadAsync(t, "../../..\\evil<>name.png", Png);
        Assert.Equal(HttpStatusCode.Created, r.StatusCode);
        var a = await f.DbAsync(db => db.TicketAttachments.SingleAsync(x => db.Tickets.Any(y => y.Id == x.TicketId && y.Number == t.Number)));
        Assert.Equal("evil__name.png", a.FileName);
        Assert.Matches("^[0-9a-f]{32}$", a.ObjectKey);
        Assert.Equal(ScanStatus.Pending, a.Scan);
        Assert.True(System.IO.File.Exists(Path.Combine(f.Storage, a.ObjectKey[..2], a.ObjectKey)));
    }

    [Fact]
    public async Task Text_disguised_as_png_is_refused_and_not_kept()
    {
        var t = await CreateAsync();
        int Stored() => Directory.Exists(f.Storage) ? Directory.GetFiles(f.Storage, "*", SearchOption.AllDirectories).Count(p => !p.Contains("mail")) : 0;
        var before = Stored();
        var r = await UploadAsync(t, "shot.png", Encoding.UTF8.GetBytes("<html><script>alert(1)</script></html>"));
        Assert.Equal(HttpStatusCode.BadRequest, r.StatusCode);
        Assert.Equal("file_content_mismatch", await CodeOf(r));
        Assert.Equal(before, Stored());
        Assert.Equal(0, await f.DbAsync(db => db.TicketAttachments.CountAsync(x => x.TicketId == db.Tickets.First(y => y.Number == t.Number).Id)));
    }

    [Theory]
    [InlineData("tool.exe")]
    [InlineData("script.ps1")]
    [InlineData("page.html")]
    [InlineData("noextension")]
    public async Task Other_types_are_refused(string name)
    {
        var t = await CreateAsync();
        var r = await UploadAsync(t, name, Encoding.UTF8.GetBytes("MZ..."));
        Assert.Equal("file_type_not_allowed", await CodeOf(r));
    }

    [Fact]
    public async Task Oversized_file_is_cut_off()
    {
        var t = await CreateAsync();
        var big = new byte[70_000];
        Png.CopyTo(big, 0);
        var r = await UploadAsync(t, "big.png", big);
        Assert.Equal(HttpStatusCode.RequestEntityTooLarge, r.StatusCode);
    }

    [Fact]
    public async Task Logs_and_saves_need_consent()
    {
        var no = await CreateAsync(Body(consent: false));
        Assert.Equal(HttpStatusCode.Forbidden, (await UploadAsync(no, "openxcom.log", "[INFO] started"u8.ToArray())).StatusCode);
        var yes = await CreateAsync(Body(consent: true));
        Assert.Equal(HttpStatusCode.Created, (await UploadAsync(yes, "openxcom.log", "[INFO] started"u8.ToArray())).StatusCode);
        Assert.Equal(HttpStatusCode.Created, (await UploadAsync(yes, "battle.sav", "name: Battle\nversion: 1\n"u8.ToArray())).StatusCode);
    }

    [Fact]
    public async Task Binary_named_as_log_is_refused()
    {
        var t = await CreateAsync(Body(consent: true));
        var r = await UploadAsync(t, "crash.log", [0x4D, 0x5A, 0x90, 0x00, 0x03]);
        Assert.Equal("file_content_mismatch", await CodeOf(r));
    }

    [Fact]
    public async Task File_count_per_ticket_is_limited()
    {
        var t = await CreateAsync();
        for (int i = 0; i < 3; i++) Assert.Equal(HttpStatusCode.Created, (await UploadAsync(t, $"s{i}.png", Png)).StatusCode);
        var r = await UploadAsync(t, "s4.png", Png);
        Assert.Equal("too_many_files", await CodeOf(r));
    }

    [Fact]
    public async Task Upload_without_the_token_is_not_found()
    {
        var t = await CreateAsync();
        var r = await Guest("not-the-token-at-all").PostAsync($"/api/v1/tickets/{t.Number}/attachments", File("a.png", Png));
        Assert.Equal(HttpStatusCode.NotFound, r.StatusCode);
    }

    // ---- replies ----

    [Fact]
    public async Task Guest_reply_moves_needs_info_back_to_triage()
    {
        var t = await CreateAsync();
        await f.DbAsync(async db =>
        {
            var x = await db.Tickets.FirstAsync(y => y.Number == t.Number);
            x.Status = TicketStatus.NeedsInfo;
            return await db.SaveChangesAsync();
        });
        var r = await Guest(t.Token).PostAsJsonAsync($"/api/v1/tickets/{t.Number}/messages", new { body = "Here is the save." });
        Assert.Equal(HttpStatusCode.NoContent, r.StatusCode);
        var view = await Guest(t.Token).GetFromJsonAsync<TicketView>($"/api/v1/tickets/{t.Number}");
        Assert.Equal("Triaged", view!.Status);
        Assert.Single(view.Messages);
    }

    [Fact]
    public async Task Internal_notes_never_reach_the_guest()
    {
        var t = await CreateAsync();
        await f.ScopedAsync(async sp =>
        {
            var db = sp.GetRequiredService<PortalDb>();
            var svc = sp.GetRequiredService<TicketService>();
            var x = await db.Tickets.FirstAsync(y => y.Number == t.Number);
            await svc.AddMessageAsync(x, "suspect a mod conflict", null, fromStaff: true, isInternal: true, default);
            await svc.AddMessageAsync(x, "Could you attach the save?", null, fromStaff: true, isInternal: false, default);
            return 0;
        });
        var raw = await Guest(t.Token).GetStringAsync($"/api/v1/tickets/{t.Number}");
        Assert.DoesNotContain("mod conflict", raw);
        Assert.Contains("attach the save", raw);
    }

    // ---- telegram ----

    [Fact]
    public async Task Telegram_notice_is_short_escaped_and_routed_by_category()
    {
        await f.DbAsync(async db =>
        {
            db.TelegramRoutes.AddRange(new TelegramRoute { Category = "*", ChatId = "-100default" },
                                       new TelegramRoute { Category = "graphics", ChatId = "-100art", ThreadId = 7 });
            return await db.SaveChangesAsync();
        });
        var evil = "<b>hi</b> & <a href=\"x\">" + new string('Я', 100);
        var t = await CreateAsync(Body(evil, "graphics", email: "player@example.com"));
        var job = await f.DbAsync(db => db.NotificationJobs.OrderByDescending(j => j.Id).FirstAsync());
        Assert.Equal("-100art", job.ChatId);
        Assert.Equal(7, job.ThreadId);
        Assert.Contains($"XP-{t.Number:D6}", job.Text);
        Assert.Contains("&lt;b&gt;hi&lt;/b&gt; &amp; &lt;a href=&quot;x&quot;&gt;", job.Text);
        Assert.DoesNotContain("<a href=\"x\">", job.Text);
        Assert.DoesNotContain("player@example.com", job.Text);
        Assert.DoesNotContain("globe stops turning", job.Text);    // description never goes out
        Assert.Contains("…", job.Text);                            // title shortened
        Assert.Contains($"https://portal.test/admin/tickets/{t.Number}", job.Text);

        var code = await CreateAsync(Body("code bug", "code"));
        var job2 = await f.DbAsync(db => db.NotificationJobs.OrderByDescending(j => j.Id).FirstAsync());
        Assert.Equal("-100default", job2.ChatId);
    }

    [Fact]
    public void Telegram_text_matches_the_template()
    {
        var t = new Ticket { Number = 42, Category = "code", Title = "Crash & burn", GameVersion = "1.2", ModVersion = "HD",
            CreatedAt = new DateTimeOffset(2026, 9, 23, 10, 5, 0, TimeSpan.Zero) };
        Assert.Equal(
            "🆕 <b>XP-000042</b> · code\nCrash &amp; burn\nv 1.2 / HD\n2026-09-23 10:05 UTC\n<a href=\"https://portal.test/admin/tickets/42\">open</a>",
            TelegramNotices.NewTicketText(t, "https://portal.test/"));
    }

    [Fact]
    public async Task Worker_sends_retries_with_backoff_and_gives_up_without_leaking_the_token()
    {
        await f.DbAsync(async db =>
        {
            db.NotificationJobs.RemoveRange(db.NotificationJobs);
            db.NotificationJobs.Add(new NotificationJob { ChatId = "-1", Text = "hello", NextAttemptAt = f.Clock.GetUtcNow() });
            return await db.SaveChangesAsync();
        });
        var worker = f.Services.GetServices<Microsoft.Extensions.Hosting.IHostedService>().OfType<TelegramWorker>().FirstOrDefault()
                     ?? ActivatorUtilities.CreateInstance<TelegramWorker>(f.Services);

        f.Telegram.Answers.Enqueue((HttpStatusCode.TooManyRequests, "{\"ok\":false,\"description\":\"Too Many Requests\",\"parameters\":{\"retry_after\":42}}"));
        Assert.True(await worker.SendOneAsync(default));
        var j = await f.DbAsync(db => db.NotificationJobs.SingleAsync());
        Assert.Equal(JobState.Pending, j.State);
        Assert.Equal(f.Clock.GetUtcNow().AddSeconds(42), j.NextAttemptAt);   // Telegram's retry_after wins
        Assert.False(await worker.SendOneAsync(default));                     // not due yet

        f.Clock.Advance(TimeSpan.FromSeconds(43));
        f.Telegram.Answers.Enqueue((HttpStatusCode.BadGateway, "{\"ok\":false,\"description\":\"Bad Gateway\"}"));
        Assert.True(await worker.SendOneAsync(default));
        j = await f.DbAsync(db => db.NotificationJobs.SingleAsync());
        Assert.Equal(f.Clock.GetUtcNow() + TelegramWorker.Backoff(2), j.NextAttemptAt);

        f.Clock.Advance(TimeSpan.FromHours(1));
        f.Telegram.Answers.Enqueue((HttpStatusCode.BadGateway, "{\"ok\":false,\"description\":\"Bad Gateway\"}"));
        Assert.True(await worker.SendOneAsync(default));
        j = await f.DbAsync(db => db.NotificationJobs.SingleAsync());
        Assert.Equal(JobState.Dead, j.State);           // MaxAttempts = 3 in tests
        Assert.DoesNotContain("SECRET-TOKEN", j.LastError);

        var sent = f.Telegram.Requests[^1];
        Assert.Contains("/bot123:SECRET-TOKEN/sendMessage", sent.Url);
        var body = JsonDocument.Parse(sent.Body).RootElement;
        Assert.Equal("HTML", body.GetProperty("parse_mode").GetString());
        Assert.Equal("-1", body.GetProperty("chat_id").GetString());
    }

    [Fact]
    public async Task Health_endpoints_answer_without_details()
    {
        var c = f.CreateClient();
        Assert.Equal("Healthy", await c.GetStringAsync("/health"));
        Assert.Equal("Healthy", await c.GetStringAsync("/ready"));
    }

    [Fact]
    public async Task Openapi_describes_the_ticket_api()
    {
        var doc = await f.CreateClient().GetStringAsync("/openapi/v1.json");
        Assert.Contains("/api/v1/tickets/{number}/attachments", doc);
        Assert.Contains("Idempotency-Key", doc);
    }
}
