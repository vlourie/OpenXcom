using System.Globalization;
using System.Net;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json.Serialization;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;
using Xp.Portal.Data;

namespace Xp.Portal.Notifications;

public sealed class TelegramOptions
{
    public const string Section = "Telegram";
    /// <summary>Bot token; a server-side secret, only from the environment (Telegram__BotToken).</summary>
    public string BotToken { get; set; } = "";
    public string ApiBase { get; set; } = "https://api.telegram.org";
    public int MaxAttempts { get; set; } = 8;
    public int PollSeconds { get; set; } = 5;
    public bool Enabled => !string.IsNullOrWhiteSpace(BotToken);
}

/// <summary>
/// Builds the new-ticket notice and puts it in the queue. The text carries only: number, category,
/// a shortened title, versions, time and the admin link — never the description, e-mail, IP or files.
/// </summary>
public sealed class TelegramNotices(PortalDb db, IOptions<PortalOptions> portal)
{
    public const int TitleMax = 80;

    /// <summary>Route of the upstream-version notices (UpstreamCheck); falls back to the default one.</summary>
    public const string UpstreamCategory = "upstream";

    public Task EnqueueNewTicketAsync(Ticket t, CancellationToken ct) => EnqueueAsync(t.Category, NewTicketText(t, portal.Value.PublicUrl), ct);

    /// <summary>Queues a ready, escaped text on the category's route, or the default route; nothing when neither is set.</summary>
    public async Task EnqueueAsync(string category, string text, CancellationToken ct)
    {
        var routes = await db.TelegramRoutes.Where(r => r.Enabled && (r.Category == category || r.Category == "*")).ToListAsync(ct);
        // a category's own route wins over the default one
        var route = routes.FirstOrDefault(r => r.Category == category) ?? routes.FirstOrDefault();
        if (route is null) return;
        db.NotificationJobs.Add(new NotificationJob { ChatId = route.ChatId, ThreadId = route.ThreadId, Text = text });
    }

    public static string NewTicketText(Ticket t, string publicUrl)
    {
        var versions = string.Join(" / ", new[] { t.GameVersion, t.ModVersion }.Where(v => !string.IsNullOrWhiteSpace(v)));
        var sb = new StringBuilder();
        sb.Append("🆕 <b>").Append(Html(t.DisplayNumber)).Append("</b> · ").Append(Html(t.Category));
        if (!string.IsNullOrEmpty(t.Language)) sb.Append(" · ").Append(Html(t.Language));
        sb.Append('\n');
        sb.Append(Html(Shorten(t.Title, TitleMax))).Append('\n');
        if (versions.Length > 0) sb.Append("v ").Append(Html(Shorten(versions, 64))).Append('\n');
        sb.Append(t.CreatedAt.UtcDateTime.ToString("yyyy-MM-dd HH:mm 'UTC'", CultureInfo.InvariantCulture)).Append('\n');
        sb.Append("<a href=\"").Append(Html($"{publicUrl.TrimEnd('/')}/admin/tickets/{t.Number}")).Append("\">open</a>");
        return sb.ToString();
    }

    /// <summary>Telegram's HTML mode knows only these three entities; everything else is text.</summary>
    public static string Html(string s) => s.Replace("&", "&amp;").Replace("<", "&lt;").Replace(">", "&gt;").Replace("\"", "&quot;");

    /// <summary>Cuts by text elements, so an emoji or a letter with diacritics is never split in half.</summary>
    public static string Shorten(string s, int max)
    {
        var e = System.Globalization.StringInfo.GetTextElementEnumerator(s);
        var sb = new StringBuilder();
        int n = 0;
        while (e.MoveNext())
        {
            if (++n > max) return sb.ToString().TrimEnd() + "…";
            sb.Append(e.GetTextElement());
        }
        return sb.ToString();
    }
}

/// <summary>Sends queued notices; a failure is retried with growing delays and ends in "dead", never blocks a ticket.</summary>
public sealed class TelegramWorker(IServiceScopeFactory scopes, IHttpClientFactory http, IOptions<TelegramOptions> options,
    TimeProvider clock, ILogger<TelegramWorker> log) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stop)
    {
        var o = options.Value;
        if (!o.Enabled) { log.LogInformation("Telegram: no bot token, notices stay in the queue"); return; }
        while (!stop.IsCancellationRequested)
        {
            try { while (await SendOneAsync(stop)) { } }
            catch (Exception e) when (e is not OperationCanceledException) { log.LogError(e, "Telegram worker pass failed"); }
            try { await Task.Delay(TimeSpan.FromSeconds(o.PollSeconds), clock, stop); }
            catch (OperationCanceledException) { return; }
        }
    }

    /// <summary>Takes one due job (SKIP LOCKED: several instances never send the same one) and tries it.</summary>
    internal async Task<bool> SendOneAsync(CancellationToken ct)
    {
        using var scope = scopes.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<PortalDb>();
        await using var tx = await db.Database.BeginTransactionAsync(ct);
        var now = clock.GetUtcNow();
        var job = await db.NotificationJobs
            .FromSql($"SELECT * FROM \"NotificationJobs\" WHERE \"State\" = 'Pending' AND \"NextAttemptAt\" <= {now} ORDER BY \"Id\" LIMIT 1 FOR UPDATE SKIP LOCKED")
            .FirstOrDefaultAsync(ct);
        if (job is null) return false;

        var (ok, error, retryAfter) = await SendAsync(job, ct);
        job.Attempts++;
        if (ok)
        {
            job.State = JobState.Done;
            job.DoneAt = clock.GetUtcNow();
            job.LastError = null;
        }
        else
        {
            job.LastError = error.Length > 500 ? error[..500] : error;
            if (job.Attempts >= options.Value.MaxAttempts) job.State = JobState.Dead;
            else job.NextAttemptAt = clock.GetUtcNow() + (retryAfter ?? Backoff(job.Attempts));
            log.LogWarning("Telegram job {Id} attempt {N} failed: {Error}", job.Id, job.Attempts, job.LastError);
        }
        await db.SaveChangesAsync(ct);
        await tx.CommitAsync(ct);
        return true;
    }

    /// <summary>30 s, 1, 2, 4 … minutes, capped at an hour.</summary>
    internal static TimeSpan Backoff(int attempts) => TimeSpan.FromSeconds(Math.Min(3600, 30 * Math.Pow(2, attempts - 1)));

    async Task<(bool ok, string error, TimeSpan? retryAfter)> SendAsync(NotificationJob job, CancellationToken ct)
    {
        var o = options.Value;
        var body = new SendMessage(job.ChatId, job.Text, "HTML", job.ThreadId, new LinkPreview(true));
        try
        {
            using var client = http.CreateClient("telegram");
            // the token is part of the URL by Telegram's design: it must never reach a log line
            using var resp = await client.PostAsJsonAsync($"{o.ApiBase.TrimEnd('/')}/bot{o.BotToken}/sendMessage", body, TelegramJson.Default.SendMessage, ct);
            if (resp.IsSuccessStatusCode) return (true, "", null);
            var answer = await resp.Content.ReadFromJsonAsync(TelegramJson.Default.TelegramAnswer, ct);
            TimeSpan? after = answer?.Parameters?.RetryAfter is int s ? TimeSpan.FromSeconds(s) : null;
            return (false, $"HTTP {(int)resp.StatusCode}: {answer?.Description}", after);
        }
        catch (Exception e) when (e is HttpRequestException or TaskCanceledException or System.Text.Json.JsonException)
        {
            return (false, e.GetType().Name + ": " + e.Message.Replace(o.BotToken, "***"), null);
        }
    }
}

public sealed record SendMessage(
    [property: JsonPropertyName("chat_id")] string ChatId,
    [property: JsonPropertyName("text")] string Text,
    [property: JsonPropertyName("parse_mode")] string ParseMode,
    [property: JsonPropertyName("message_thread_id"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] int? MessageThreadId,
    [property: JsonPropertyName("link_preview_options")] LinkPreview LinkPreviewOptions);

public sealed record LinkPreview([property: JsonPropertyName("is_disabled")] bool IsDisabled);

public sealed record TelegramAnswer(
    [property: JsonPropertyName("ok")] bool Ok,
    [property: JsonPropertyName("description")] string? Description,
    [property: JsonPropertyName("parameters")] TelegramParameters? Parameters);

public sealed record TelegramParameters([property: JsonPropertyName("retry_after")] int? RetryAfter);

[JsonSerializable(typeof(SendMessage))]
[JsonSerializable(typeof(TelegramAnswer))]
internal sealed partial class TelegramJson : JsonSerializerContext;
