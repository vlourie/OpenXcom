using System.Security.Cryptography;
using System.Text;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;
using Npgsql;
using Xp.Portal.Auth;
using Xp.Portal.Data;
using Xp.Portal.Notifications;

namespace Xp.Portal.Tickets;

public sealed record NewTicket(
    string Category, string Title, string Description,
    string? Steps = null, string? Expected = null, string? Actual = null,
    string? GameVersion = null, string? ModVersion = null, string? LauncherVersion = null,
    string? GuestEmail = null, bool ConsentToFiles = false, TicketSource Source = TicketSource.Web, string? Context = null,
    string? Language = null);

public sealed record CreatedTicket(Ticket Ticket, string? GuestToken, bool Replayed);

public sealed class TicketException(string code, string message) : Exception(message)
{
    /// <summary>Machine-readable reason, also the key of the user-facing text.</summary>
    public string Code { get; } = code;
}

public sealed class TicketService(PortalDb db, TelegramNotices notices, IOptions<PortalOptions> options, TimeProvider clock)
{
    static readonly Dictionary<TicketStatus, TicketStatus[]> Moves = new()
    {
        [TicketStatus.New] = [TicketStatus.Triaged, TicketStatus.InProgress, TicketStatus.NeedsInfo, TicketStatus.Resolved, TicketStatus.Rejected],
        [TicketStatus.Triaged] = [TicketStatus.InProgress, TicketStatus.NeedsInfo, TicketStatus.Resolved, TicketStatus.Rejected],
        [TicketStatus.InProgress] = [TicketStatus.Triaged, TicketStatus.NeedsInfo, TicketStatus.Resolved, TicketStatus.Rejected],
        [TicketStatus.NeedsInfo] = [TicketStatus.Triaged, TicketStatus.InProgress, TicketStatus.Resolved, TicketStatus.Rejected, TicketStatus.Closed],
        [TicketStatus.Resolved] = [TicketStatus.Closed, TicketStatus.InProgress],
        [TicketStatus.Closed] = [TicketStatus.InProgress],
        [TicketStatus.Duplicate] = [TicketStatus.Triaged],
        [TicketStatus.Rejected] = [TicketStatus.Triaged],
    };

    public static IReadOnlyList<TicketStatus> AllowedMoves(TicketStatus from) => Moves[from];

    public async Task<CreatedTicket> CreateAsync(NewTicket n, Guid? authorId, string? idempotencyKey, string? correlationId, CancellationToken ct)
    {
        Validate(n, authorId);
        string? keyHash = null, fingerprint = null;
        if (idempotencyKey is not null)
        {
            if (idempotencyKey.Length is < 8 or > 128) throw new TicketException("idempotency_key_invalid", "Idempotency-Key must be 8..128 characters");
            keyHash = Sha(idempotencyKey);
            fingerprint = Sha($"{authorId}\n{n.Category}\n{n.Title}\n{n.Description}");
            var existing = await db.Tickets.FirstOrDefaultAsync(t => t.IdempotencyKey == keyHash, ct);
            if (existing is not null) return Replay(existing, fingerprint);
        }

        var now = clock.GetUtcNow();
        var t = new Ticket
        {
            Category = n.Category,
            Title = Clean(n.Title, Limits.TitleMax, singleLine: true)!,
            Description = Clean(n.Description, Limits.TextMax)!,
            Steps = Clean(n.Steps, Limits.TextMax),
            Expected = Clean(n.Expected, Limits.TextMax),
            Actual = Clean(n.Actual, Limits.TextMax),
            GameVersion = Clean(n.GameVersion, 64, true),
            ModVersion = Clean(n.ModVersion, 64, true),
            LauncherVersion = Clean(n.LauncherVersion, 64, true),
            Context = Clean(n.Context, Limits.ContextMax),
            Language = TicketLanguage.Normalize(n.Language),
            Source = n.Source,
            AuthorId = authorId,
            GuestEmail = authorId is null ? Clean(n.GuestEmail, 256, true) : null,
            ConsentToFiles = n.ConsentToFiles,
            IdempotencyKey = keyHash,
            IdempotencyFingerprint = fingerprint,
            CorrelationId = Clean(correlationId, 64, true),
            CreatedAt = now,
            UpdatedAt = now,
        };
        await using var tx = await db.Database.BeginTransactionAsync(ct);
        db.Tickets.Add(t);
        try { await db.SaveChangesAsync(ct); }
        catch (DbUpdateException e) when (keyHash is not null && e.InnerException is PostgresException { SqlState: PostgresErrorCodes.UniqueViolation })
        {
            // two retries raced: the other one won, answer with its ticket
            await tx.RollbackAsync(ct);
            db.ChangeTracker.Clear();
            var winner = await db.Tickets.FirstAsync(x => x.IdempotencyKey == keyHash, ct);
            return Replay(winner, fingerprint!);
        }
        string? token = null;
        if (authorId is null)
        {
            token = GuestTokenFor(t);
            t.GuestTokenHash = GuestTokens.Hash(token);
        }
        db.TicketHistory.Add(new TicketHistory { TicketId = t.Id, ActorId = authorId, Action = "created", To = t.Status.ToString(), At = now });
        await notices.EnqueueNewTicketAsync(t, ct);   // same transaction: the notice exists iff the ticket does
        await db.SaveChangesAsync(ct);
        await tx.CommitAsync(ct);
        return new CreatedTicket(t, token, false);
    }

    CreatedTicket Replay(Ticket existing, string fingerprint)
    {
        if (existing.IdempotencyFingerprint != fingerprint)
            throw new TicketException("idempotency_key_reused", "this Idempotency-Key was already used for a different ticket");
        return new CreatedTicket(existing, existing.AuthorId is null ? GuestTokenFor(existing) : null, true);
    }

    /// <summary>
    /// The guest token is derived from the server secret, so a retried request can be answered with the
    /// same link without storing the token anywhere; only its hash is in the database.
    /// </summary>
    string GuestTokenFor(Ticket t)
    {
        var mac = HMACSHA256.HashData(options.Value.SecretBytes(), Encoding.UTF8.GetBytes("guest-link:" + t.Id));
        return GuestTokens.Base64Url(mac[..16]);
    }

    static void Validate(NewTicket n, Guid? authorId)
    {
        if (!Categories.IsValid(n.Category)) throw new TicketException("category_invalid", "unknown category");
        if (string.IsNullOrWhiteSpace(n.Title)) throw new TicketException("title_required", "title is required");
        if (string.IsNullOrWhiteSpace(n.Description)) throw new TicketException("description_required", "description is required");
        if (n.Title.Length > Limits.TitleMax) throw new TicketException("title_too_long", $"title is longer than {Limits.TitleMax}");
        foreach (var s in new[] { n.Description, n.Steps, n.Expected, n.Actual })
            if (s?.Length > Limits.TextMax) throw new TicketException("text_too_long", $"text is longer than {Limits.TextMax}");
        if (n.Context?.Length > Limits.ContextMax) throw new TicketException("text_too_long", $"context is longer than {Limits.ContextMax}");
        if (authorId is null && !string.IsNullOrWhiteSpace(n.GuestEmail) && !System.Net.Mail.MailAddress.TryCreate(n.GuestEmail.Trim(), out _))
            throw new TicketException("email_invalid", "e-mail address is not valid");
    }

    /// <summary>Trims, drops control characters (except line breaks in multi-line text) and caps the length.</summary>
    internal static string? Clean(string? s, int max, bool singleLine = false)
    {
        if (string.IsNullOrWhiteSpace(s)) return null;
        var sb = new StringBuilder(s.Length);
        foreach (var ch in s.Trim())
        {
            if (ch == '\r') continue;
            if (ch == '\n' || ch == '\t') { sb.Append(singleLine ? ' ' : ch); continue; }
            if (char.IsControl(ch) || ch is '​' or '‮' or '‭' or '⁦' or '⁧' or '⁨' or '⁩') continue;
            sb.Append(ch);
        }
        var r = sb.ToString().Trim();
        return r.Length == 0 ? null : r.Length > max ? r[..max] : r;
    }

    static string Sha(string s) => Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(s)));

    // ---- staff actions; the caller has already checked Viewer.IsStaffFor(ticket) ----

    public async Task ChangeStatusAsync(Ticket t, TicketStatus to, Guid actor, CancellationToken ct)
    {
        if (to == t.Status) return;
        if (to == TicketStatus.Duplicate) throw new TicketException("use_duplicate", "mark duplicates with the duplicate action");
        if (!Moves[t.Status].Contains(to)) throw new TicketException("status_move_invalid", $"{t.Status} cannot become {to}");
        await HistoryAsync(t, actor, "status", t.Status.ToString(), to.ToString(), ct);
        t.Status = to;
        if (to != TicketStatus.Duplicate) t.DuplicateOfId = null;
        await TouchAsync(t, ct);
    }

    public async Task SetPriorityAsync(Ticket t, TicketPriority p, Guid actor, CancellationToken ct)
    {
        if (p == t.Priority) return;
        await HistoryAsync(t, actor, "priority", t.Priority.ToString(), p.ToString(), ct);
        t.Priority = p;
        await TouchAsync(t, ct);
    }

    public async Task SetCategoryAsync(Ticket t, string category, Guid actor, CancellationToken ct)
    {
        if (!Categories.IsValid(category)) throw new TicketException("category_invalid", "unknown category");
        if (category == t.Category) return;
        await HistoryAsync(t, actor, "category", t.Category, category, ct);
        t.Category = category;
        await TouchAsync(t, ct);
    }

    public async Task SetLanguageAsync(Ticket t, string? language, Guid actor, CancellationToken ct)
    {
        var tag = TicketLanguage.Normalize(language);
        if (tag == t.Language) return;
        await HistoryAsync(t, actor, "language", t.Language, tag, ct);
        t.Language = tag;
        await TouchAsync(t, ct);
    }

    public async Task AssignAsync(Ticket t, Guid? assignee, Guid actor, CancellationToken ct)
    {
        if (assignee == t.AssigneeId) return;
        if (assignee is { } a)
        {
            // only someone who may work on this category can be made responsible for it
            var perm = Permissions.ForCategory(t.Category);
            var ok = await db.Users.AnyAsync(u => u.Id == a && (
                db.UserRoles.Any(r => r.UserId == a && db.Roles.Any(x => x.Id == r.RoleId && x.Name == Roles.SuperAdmin)) ||
                (db.UserRoles.Any(r => r.UserId == a && db.Roles.Any(x => x.Id == r.RoleId && x.Name == Roles.Admin)) &&
                 db.UserPermissions.Any(p => p.UserId == a && p.Permission == perm))), ct);
            if (!ok) throw new TicketException("assignee_not_allowed", "this person cannot work on this category");
        }
        await HistoryAsync(t, actor, "assignee", t.AssigneeId?.ToString(), assignee?.ToString(), ct);
        t.AssigneeId = assignee;
        await TouchAsync(t, ct);
    }

    public async Task MarkDuplicateAsync(Ticket t, long ofNumber, Viewer viewer, CancellationToken ct)
    {
        var of = await db.Tickets.FirstOrDefaultAsync(x => x.Number == ofNumber, ct);
        // the original must be visible to the same admin, or the link would leak its existence
        if (of is null || !viewer.IsStaffFor(of)) throw new TicketException("duplicate_target_invalid", "no such ticket");
        if (of.Id == t.Id || of.DuplicateOfId == t.Id) throw new TicketException("duplicate_target_invalid", "a ticket cannot duplicate itself");
        await HistoryAsync(t, viewer.UserId, "duplicate", t.Status.ToString(), of.DisplayNumber, ct);
        t.Status = TicketStatus.Duplicate;
        t.DuplicateOfId = of.Id;
        await TouchAsync(t, ct);
    }

    public async Task<TicketMessage> AddMessageAsync(Ticket t, string body, Guid? author, bool fromStaff, bool isInternal, CancellationToken ct)
    {
        var text = Clean(body, Limits.TextMax) ?? throw new TicketException("message_required", "message is empty");
        if (isInternal && !fromStaff) throw new TicketException("internal_staff_only", "only staff write internal notes");
        if (!fromStaff && t.Status is TicketStatus.Closed or TicketStatus.Duplicate or TicketStatus.Rejected)
            throw new TicketException("ticket_closed", "the ticket is closed");
        var m = new TicketMessage { TicketId = t.Id, AuthorId = author, Body = text, FromStaff = fromStaff, Internal = isInternal, CreatedAt = clock.GetUtcNow() };
        db.TicketMessages.Add(m);
        // the player answered the question: the ticket needs a look again
        if (!fromStaff && t.Status == TicketStatus.NeedsInfo)
        {
            await HistoryAsync(t, author, "status", t.Status.ToString(), TicketStatus.Triaged.ToString(), ct);
            t.Status = TicketStatus.Triaged;
        }
        await TouchAsync(t, ct);
        return m;
    }

    Task HistoryAsync(Ticket t, Guid? actor, string action, string? from, string? to, CancellationToken ct)
    {
        db.TicketHistory.Add(new TicketHistory { TicketId = t.Id, ActorId = actor, Action = action, From = from, To = to, At = clock.GetUtcNow() });
        return Task.CompletedTask;
    }

    async Task TouchAsync(Ticket t, CancellationToken ct)
    {
        t.UpdatedAt = clock.GetUtcNow();
        await db.SaveChangesAsync(ct);
    }
}
