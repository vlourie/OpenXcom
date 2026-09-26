using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using Xp.Portal.Tickets;

namespace Xp.Portal.Tests;

/// <summary>
/// The portal on real Kestrel, with the production attachment limits. TestServer has no body limit
/// at all, so a size test on it passes at any size (R-053); Kestrel cuts bodies at 30 MB on its own.
/// </summary>
public sealed class KestrelPortalFactory : PortalFactory
{
    public KestrelPortalFactory()
    {
        Settings["Attachments:MaxFileBytes"] = "52428800";
        Settings["Attachments:MaxZipBytes"] = "104857600";
        Settings["Attachments:MaxBytesPerTicket"] = "209715200";
        UseKestrel(0);
    }
}

/// <summary>Attachments against the server that really runs on the station (audit P-10).</summary>
public sealed class KestrelUploadTests(KestrelPortalFactory f) : IClassFixture<KestrelPortalFactory>
{
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
}
