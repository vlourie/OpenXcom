using System.Collections.Concurrent;
using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http.Features;
using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.TestHost;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Xp.Portal.Auth;
using Xp.Portal.Data;
using Xp.Portal.Devices;
using Xp.Portal.Review;
using Xp.Portal.Tickets;

namespace Xp.Portal.Tests;

/// <summary>
/// The portal on real Kestrel, with the production attachment limits. TestServer has no body limit
/// at all, so a size test on it passes at any size (R-053); Kestrel cuts bodies at 30 MB on its own.
/// </summary>
public sealed class KestrelPortalFactory : PortalFactory
{
    /// <summary>Per request: the path and the body limit it ended with.</summary>
    public ConcurrentQueue<(string Path, long? Limit)> Limits { get; } = new();

    public KestrelPortalFactory()
    {
        Settings["Attachments:MaxFileBytes"] = "52428800";
        Settings["Attachments:MaxZipBytes"] = "104857600";
        Settings["Attachments:MaxBytesPerTicket"] = "209715200";
        UseKestrel(0);
    }

    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        base.ConfigureWebHost(builder);
        builder.ConfigureTestServices(s => s.AddSingleton<IStartupFilter>(new LimitProbe(Limits)));
    }

    sealed class LimitProbe(ConcurrentQueue<(string, long?)> seen) : IStartupFilter
    {
        public Action<IApplicationBuilder> Configure(Action<IApplicationBuilder> next) => app =>
        {
            app.Use((ctx, go) =>
            {
                // taken as the answer starts, not after the pipeline: by then the client may already be reading it
                ctx.Response.OnStarting(() =>
                {
                    seen.Enqueue((ctx.Request.Path, ctx.Features.Get<IHttpMaxRequestBodySizeFeature>()?.MaxRequestBodySize));
                    return Task.CompletedTask;
                });
                return go();
            });
            next(app);
        };
    }
}

/// <summary>Attachments against the server that really runs on the station (audit P-6, P-10).</summary>
public sealed class KestrelUploadTests(KestrelPortalFactory f) : IClassFixture<KestrelPortalFactory>
{
    const long KestrelDefault = 30_000_000;
    static readonly byte[] Png = [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0, 0, 0, 13, 0x49, 0x48, 0x44, 0x52];

    async Task<CreateTicketResponse> CreateAsync()
    {
        var r = await f.CreateClient().PostAsJsonAsync("/api/v1/tickets", new
        {
            category = "code", title = "Big screenshot", description = "A screenshot bigger than Kestrel's own limit.",
            gameVersion = "2026.09.26", modVersion = "HD 1.0", consentToFiles = false,
        });
        Assert.True(r.IsSuccessStatusCode, await r.Content.ReadAsStringAsync());
        return (await r.Content.ReadFromJsonAsync<CreateTicketResponse>())!;
    }

    static MultipartFormDataContent File(string name, byte[] data)
    {
        var c = new ByteArrayContent(data);
        c.Headers.ContentType = new MediaTypeHeaderValue("application/octet-stream");
        return new MultipartFormDataContent { { c, "file", name } };
    }

    Task<HttpResponseMessage> UploadAsync(long number, string? token, byte[] data)
    {
        var c = f.CreateClient();
        c.Timeout = TimeSpan.FromMinutes(2);
        if (token is not null) c.DefaultRequestHeaders.Add(TicketApi.TokenHeader, token);
        return c.PostAsync($"/api/v1/tickets/{number}/attachments", File("big.png", data));
    }

    [Fact]
    public async Task A_file_above_kestrels_own_30_MB_gets_through_to_our_limit()
    {
        Assert.StartsWith("http://127.0.0.1:", f.CreateClient().BaseAddress!.ToString());   // really Kestrel, not TestServer
        var t = await CreateAsync();
        var big = new byte[31 * 1024 * 1024];
        Png.CopyTo(big, 0);
        var r = await UploadAsync(t.Number, t.Token, big);
        Assert.True(r.StatusCode == HttpStatusCode.Created, $"{(int)r.StatusCode}: {await r.Content.ReadAsStringAsync()}");
    }

    [Fact]
    public async Task A_stranger_without_the_token_never_gets_the_bigger_limit()
    {
        var t = await CreateAsync();
        var path = $"/api/v1/tickets/{t.Number}/attachments";
        foreach (var token in new string?[] { null, "wrong-token-wrong-token" })
        {
            f.Limits.Clear();
            var r = await UploadAsync(t.Number, token, Png);
            Assert.Equal(HttpStatusCode.NotFound, r.StatusCode);
            var limit = Assert.Single(f.Limits, x => x.Path == path).Limit;
            Assert.Equal(KestrelDefault, limit);
        }

        // and the owner does get it: the probe sees the lifted limit
        f.Limits.Clear();
        Assert.Equal(HttpStatusCode.Created, (await UploadAsync(t.Number, t.Token, Png)).StatusCode);
        Assert.True(Assert.Single(f.Limits, x => x.Path == path).Limit > KestrelDefault);
    }
}

/// <summary>
/// The review envelope's own 8 MB, on real Kestrel. Set inside the handler it came after the body was
/// bound and changed nothing: 9 MB went through under Kestrel's 30 MB.
/// </summary>
public sealed class KestrelReviewLimitTests(KestrelPortalFactory f) : IClassFixture<KestrelPortalFactory>
{
    const string Url = "/api/v1/review/packs";

    /// <summary>A linked launcher, made straight in the database: the link dance is ReviewTests' business.</summary>
    async Task<string> DeviceAsync()
    {
        var secret = DeviceSecrets.NewToken();
        await f.ScopedAsync(async sp =>
        {
            var users = sp.GetRequiredService<UserManager<PortalUser>>();
            var email = $"kr-{Guid.NewGuid():N}@x.test";
            var u = new PortalUser { UserName = email, Email = email, EmailConfirmed = true, DisplayName = "Kestrel" };
            var r = await users.CreateAsync(u);
            Assert.True(r.Succeeded, string.Join(", ", r.Errors.Select(e => e.Description)));
            var db = sp.GetRequiredService<PortalDb>();
            db.DeviceTokens.Add(new DeviceToken { UserId = u.Id, TokenHash = DeviceSecrets.Hash(secret), Name = "test", CreatedAt = f.Clock.GetUtcNow() });
            return await db.SaveChangesAsync();
        });
        return secret;
    }

    /// <summary>One verdict whose note is padded to make the whole send about <paramref name="bytes"/> long.</summary>
    static VerdictEnvelope Padded(long bytes) => new()
    {
        Tool = "launcher",
        Packs =
        [
            new PackVerdicts
            {
                Set = "KESTREL_" + Guid.NewGuid().ToString("N")[..6].ToUpperInvariant(),
                Pictures = 1,
                Frames = [new FrameVerdict { Frame = 0, Orig = "0000aaaa", Hd = "0000bbbb", Verdict = "ok", Note = new string('n', (int)bytes) }],
            },
        ],
    };

    async Task<HttpResponseMessage> SendAsync(string token, VerdictEnvelope envelope)
    {
        var c = f.CreateClient();
        c.Timeout = TimeSpan.FromMinutes(2);
        var msg = new HttpRequestMessage(HttpMethod.Post, Url) { Content = JsonContent.Create(envelope) };
        msg.Headers.Add(DeviceApi.TokenHeader, token);
        return await c.SendAsync(msg);
    }

    [Fact]
    public async Task A_send_under_8_MB_is_taken_with_the_review_limit_on_it()
    {
        Assert.StartsWith("http://127.0.0.1:", f.CreateClient().BaseAddress!.ToString());
        var token = await DeviceAsync();
        f.Limits.Clear();
        var r = await SendAsync(token, Padded(ReviewApi.BodyLimit - 512 * 1024));
        Assert.True(r.StatusCode == HttpStatusCode.Created, $"{(int)r.StatusCode}: {await r.Content.ReadAsStringAsync()}");
        // the endpoint's own limit, not Kestrel's 30 MB
        Assert.Equal(ReviewApi.BodyLimit, Assert.Single(f.Limits, x => x.Path == Url).Limit);
    }

    [Fact]
    public async Task A_send_over_8_MB_is_refused_with_413_before_anything_is_stored()
    {
        var token = await DeviceAsync();
        var envelope = Padded(ReviewApi.BodyLimit + 1024 * 1024);
        var r = await SendAsync(token, envelope);
        Assert.Equal(HttpStatusCode.RequestEntityTooLarge, r.StatusCode);
        Assert.Equal("application/problem+json", r.Content.Headers.ContentType?.MediaType);   // as the OpenAPI description promises
        var set = envelope.Packs[0].Set;
        Assert.Equal(0, await f.DbAsync(db => db.PackReviews.CountAsync(x => x.SetName == set)));
    }
}
