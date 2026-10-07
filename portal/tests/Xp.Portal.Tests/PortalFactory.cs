using System.Net;
using System.Text;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Time.Testing;
using Npgsql;
using Xp.Portal;
using Xp.Portal.Data;

namespace Xp.Portal.Tests;

/// <summary>
/// The whole portal on a fresh PostgreSQL database of its own. Server: XP_TEST_PG, default the
/// development instance on localhost:5433. The database is dropped when the tests of the class end.
/// </summary>
public class PortalFactory : WebApplicationFactory<Program>, IAsyncLifetime
{
    public static string ServerConnection =>
        Environment.GetEnvironmentVariable("XP_TEST_PG") ?? "Host=localhost;Port=5433;Database=postgres;Username=xp;Password=xpdev";

    readonly string _db = "xp_test_" + Guid.NewGuid().ToString("N")[..12];
    public string Storage { get; } = Path.Combine(Path.GetTempPath(), "xp-portal-test-" + Guid.NewGuid().ToString("N")[..8]);
    public FakeTimeProvider Clock { get; } = new(new DateTimeOffset(2026, 9, 23, 12, 0, 0, TimeSpan.Zero));
    public FakeTelegram Telegram { get; } = new();
    public FakeWeb Upstream { get; } = new();
    public Dictionary<string, string?> Settings { get; } = new();
    public string ConnectionString => new NpgsqlConnectionStringBuilder(ServerConnection) { Database = _db }.ConnectionString;

    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.UseEnvironment("Development");
        var s = new Dictionary<string, string?>
        {
            ["ConnectionStrings:Portal"] = ConnectionString,
            ["Portal:Secret"] = Convert.ToBase64String(Encoding.ASCII.GetBytes("test-secret-test-secret-test-secret-1234")),
            ["Portal:PublicUrl"] = "https://portal.test",
            ["Portal:ReleaseRepo"] = "",
            ["Attachments:StorageRoot"] = Storage,
            ["Attachments:MaxFileBytes"] = "65536",
            ["Attachments:MaxZipBytes"] = "131072",
            ["Attachments:MaxFilesPerTicket"] = "3",
            ["Attachments:MaxBytesPerTicket"] = "200000",
            ["Telegram:BotToken"] = "123:SECRET-TOKEN",
            ["Telegram:MaxAttempts"] = "3",
            ["Email:PickupDir"] = Path.Combine(Storage, "mail"),
            ["Workers:Enabled"] = "false",
            ["Argon2:MemoryKib"] = "1024",
            ["Argon2:Iterations"] = "1",
            ["RateLimits:TicketsPer10Min"] = "1000",
            ["RateLimits:WritesPer10Min"] = "1000",
            ["RateLimits:LoginPer5Min"] = "1000",
            ["RateLimits:ForumPer10Min"] = "1000",
        };
        foreach (var kv in Settings) s[kv.Key] = kv.Value;
        foreach (var kv in s) builder.UseSetting(kv.Key, kv.Value);
        builder.ConfigureTestServices(services =>
        {
            services.AddSingleton<TimeProvider>(Clock);
            services.AddHttpClient("telegram").ConfigurePrimaryHttpMessageHandler(() => Telegram);
            services.AddHttpClient("upstream").ConfigurePrimaryHttpMessageHandler(() => Upstream);
        });
    }

    public async Task InitializeAsync()
    {
        await using (var c = new NpgsqlConnection(ServerConnection))
        {
            await c.OpenAsync();
            await using var cmd = new NpgsqlCommand($"CREATE DATABASE \"{_db}\"", c);
            await cmd.ExecuteNonQueryAsync();
        }
        using var scope = Services.CreateScope();
        await PortalCli.MigrateAsync(scope.ServiceProvider);
    }

    public new async Task DisposeAsync()
    {
        await base.DisposeAsync();
        NpgsqlConnection.ClearAllPools();
        await using (var c = new NpgsqlConnection(ServerConnection))
        {
            await c.OpenAsync();
            await using var cmd = new NpgsqlCommand($"DROP DATABASE IF EXISTS \"{_db}\" WITH (FORCE)", c);
            await cmd.ExecuteNonQueryAsync();
        }
        try { Directory.Delete(Storage, true); } catch (IOException) { }
    }

    public T Scoped<T>(Func<IServiceProvider, T> f)
    {
        using var scope = Services.CreateScope();
        return f(scope.ServiceProvider);
    }

    public async Task<T> ScopedAsync<T>(Func<IServiceProvider, Task<T>> f)
    {
        using var scope = Services.CreateScope();
        return await f(scope.ServiceProvider);
    }

    public async Task<T> DbAsync<T>(Func<PortalDb, Task<T>> f) => await ScopedAsync(sp => f(sp.GetRequiredService<PortalDb>()));
}

/// <summary>Stands in for outside sites by URL (without the query): a missing URL answers 404. Records every request.</summary>
public sealed class FakeWeb : HttpMessageHandler
{
    public Dictionary<string, (HttpStatusCode Status, string Body)> Pages { get; } = new();
    public List<(string Url, string Body)> Requests { get; } = new();

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
    {
        var body = request.Content is null ? "" : await request.Content.ReadAsStringAsync(ct);
        var url = request.RequestUri!.GetLeftPart(UriPartial.Path);
        lock (Requests) Requests.Add((request.RequestUri.ToString(), body));
        var (status, answer) = Pages.TryGetValue(url, out var p) ? p : (HttpStatusCode.NotFound, "");
        return new HttpResponseMessage(status) { Content = new StringContent(answer, Encoding.UTF8) };
    }
}

/// <summary>Stands in for api.telegram.org: records requests, answers with a scripted status.</summary>
public sealed class FakeTelegram : HttpMessageHandler
{
    public List<(string Url, string Body)> Requests { get; } = new();
    public Queue<(HttpStatusCode Status, string Body)> Answers { get; } = new();

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
    {
        var body = request.Content is null ? "" : await request.Content.ReadAsStringAsync(ct);
        lock (Requests) Requests.Add((request.RequestUri!.ToString(), body));
        var (status, answer) = Answers.Count > 0 ? Answers.Dequeue() : (HttpStatusCode.OK, "{\"ok\":true}");
        return new HttpResponseMessage(status) { Content = new StringContent(answer, Encoding.UTF8, "application/json") };
    }
}
