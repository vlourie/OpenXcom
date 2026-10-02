using Microsoft.EntityFrameworkCore;
using Xp.Portal.Data;

namespace Xp.Portal.Voice;

/// <summary>
/// The voice service's background work: retries media-server commands that did not get through at
/// once, checks every live room against the database every half minute (the second line behind the
/// webhook), and once a day lets the log go by its retention rules.
/// </summary>
public sealed class VoiceWorker(IServiceScopeFactory scopes, IVoiceServer server, TimeProvider clock, ILogger<VoiceWorker> log) : BackgroundService
{
    internal const int MaxAttempts = 30;
    static readonly TimeSpan SweepEvery = TimeSpan.FromSeconds(30);
    static readonly TimeSpan PruneEvery = TimeSpan.FromHours(24);

    protected override async Task ExecuteAsync(CancellationToken stop)
    {
        if (!server.Enabled) log.LogInformation("Voice: no media server configured (LiveKit:*), commands stay in the queue");
        DateTimeOffset nextSweep = default, nextPrune = default;
        while (!stop.IsCancellationRequested)
        {
            var now = clock.GetUtcNow();
            if (server.Enabled)
            {
                try { while (await RunOneAsync(stop)) { } }
                catch (Exception e) when (e is not OperationCanceledException) { log.LogError(e, "Voice job pass failed"); }
                if (now >= nextSweep)
                {
                    try { await SweepAsync(stop); }
                    catch (Exception e) when (e is not OperationCanceledException) { log.LogWarning("Voice sweep failed: {Error}", e.Message); }
                    nextSweep = now + SweepEvery;
                }
            }
            if (now >= nextPrune)
            {
                try { await PruneAsync(stop); }
                catch (Exception e) when (e is not OperationCanceledException) { log.LogError(e, "Voice log prune failed"); }
                nextPrune = now + PruneEvery;
            }
            try { await Task.Delay(TimeSpan.FromSeconds(5), clock, stop); }
            catch (OperationCanceledException) { return; }
        }
    }

    /// <summary>Takes one due command (SKIP LOCKED: several instances never run the same one) and tries it.</summary>
    internal async Task<bool> RunOneAsync(CancellationToken ct)
    {
        using var scope = scopes.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<PortalDb>();
        await using var tx = await db.Database.BeginTransactionAsync(ct);
        var now = clock.GetUtcNow();
        var job = await db.VoiceJobs
            .FromSql($"SELECT * FROM \"VoiceJobs\" WHERE \"State\" = 'Pending' AND \"NextAttemptAt\" <= {now} ORDER BY \"Id\" LIMIT 1 FOR UPDATE SKIP LOCKED")
            .FirstOrDefaultAsync(ct);
        if (job is null) return false;
        var error = await TryAsync(server, job, ct);
        Record(job, error, clock.GetUtcNow());
        if (error is not null) log.LogWarning("Voice job {Id} ({Kind}) attempt {N} failed: {Error}", job.Id, job.Kind, job.Attempts, error);
        await db.SaveChangesAsync(ct);
        await tx.CommitAsync(ct);
        return true;
    }

    /// <summary>Runs one command against the media server. Null when done, the error otherwise.</summary>
    internal static async Task<string?> TryAsync(IVoiceServer server, VoiceJob job, CancellationToken ct)
    {
        try
        {
            var who = job.Identity ?? job.UserId?.ToString();
            switch (job.Kind)
            {
                case VoiceJobKind.Remove when who is not null: await server.RemoveAsync(job.RoomId, who, ct); break;
                case VoiceJobKind.SetPublish when who is not null: await server.SetPublishAsync(job.RoomId, who, job.CanPublish, ct); break;
                case VoiceJobKind.CloseRoom: await server.CloseRoomAsync(job.RoomId, ct); break;
                default: return "nobody to act on";
            }
            return null;
        }
        catch (VoiceServerException e) { return e.Message; }
    }

    internal static void Record(VoiceJob job, string? error, DateTimeOffset now)
    {
        job.Attempts++;
        if (error is null)
        {
            job.State = JobState.Done;
            job.DoneAt = now;
            job.LastError = null;
            return;
        }
        job.LastError = error.Length > 500 ? error[..500] : error;
        if (job.Attempts >= MaxAttempts) job.State = JobState.Dead;
        else job.NextAttemptAt = now + Backoff(job.Attempts);
    }

    /// <summary>15 s, 30 s, 1, 2 … minutes, capped at ten: a ban must reach the server soon after it comes back.</summary>
    internal static TimeSpan Backoff(int attempts) => TimeSpan.FromSeconds(Math.Min(600, 15 * Math.Pow(2, attempts - 1)));

    /// <summary>
    /// Everybody in every live room, checked against the database. Catches what a lost or late webhook
    /// let through: a pass issued a second before a ban, a renewed token, a room deleted on the site.
    /// </summary>
    internal async Task SweepAsync(CancellationToken ct)
    {
        foreach (var room in await server.RoomsAsync(ct))
        {
            if (!Guid.TryParse(room, out var id)) continue;
            IReadOnlyList<LivePeer> peers;
            try { peers = await server.ParticipantsAsync(id, ct); }
            catch (VoiceServerException e) { log.LogWarning("Voice sweep of room {Room}: {Error}", room, e.Message); continue; }
            foreach (var p in peers)
            {
                using var scope = scopes.CreateScope();
                var voice = scope.ServiceProvider.GetRequiredService<VoiceService>();
                await voice.RecheckAsync(room, p.Identity, p.CanPublish, joined: false, ct);
            }
        }
    }

    /// <summary>
    /// Retention (VOICE_CHAT.md section 8): comings and goings 30 days, actions a year; a record a
    /// complaint rests on stays while the ticket is open and a year after it closes. Finished
    /// commands and old answered friend requests go too.
    /// </summary>
    internal async Task PruneAsync(CancellationToken ct)
    {
        using var scope = scopes.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<PortalDb>();
        var now = clock.GetUtcNow();
        TicketStatus[] closed = [TicketStatus.Resolved, TicketStatus.Closed, TicketStatus.Duplicate, TicketStatus.Rejected];
        var complaintFrom = now - VoiceLimits.ComplaintKeep;
        // a complaint closed for over a year (its last status change is that old) lets its records go
        var released = await db.VoiceEventTickets
            .Where(l => db.Tickets.Any(t => t.Id == l.TicketId && closed.Contains(t.Status))
                && !db.TicketHistory.Any(h => h.TicketId == l.TicketId && h.Action == "status" && h.At > complaintFrom))
            .ExecuteDeleteAsync(ct);
        var held = db.VoiceEventTickets.Select(l => l.EventId);
        var presenceFrom = now - VoiceLimits.PresenceKeep;
        var actionFrom = now - VoiceLimits.ActionKeep;
        var presence = await db.VoiceEvents.Where(e => VoiceEventKinds.Presence.Contains(e.Kind) && e.At < presenceFrom && !held.Contains(e.Id))
            .ExecuteDeleteAsync(ct);
        var actions = await db.VoiceEvents.Where(e => e.At < actionFrom && !held.Contains(e.Id)).ExecuteDeleteAsync(ct);
        var jobsFrom = now - TimeSpan.FromDays(30);
        var jobs = await db.VoiceJobs.Where(j => j.State != JobState.Pending && j.CreatedAt < jobsFrom).ExecuteDeleteAsync(ct);
        var requests = await db.FriendRequests.Where(r => r.Status != FriendRequestStatus.Pending && r.AnsweredAt < jobsFrom).ExecuteDeleteAsync(ct);
        if (released + presence + actions + jobs + requests > 0)
            log.LogInformation("Voice log pruned: {Presence} presence, {Actions} actions, {Released} complaint links, {Jobs} jobs, {Requests} requests",
                presence, actions, released, jobs, requests);
    }
}
