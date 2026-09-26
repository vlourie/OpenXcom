using System.Collections.Concurrent;
using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http.Features;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;
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
