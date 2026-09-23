using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.Identity.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore;

namespace Xp.Portal.Data;

public sealed class PortalDb(DbContextOptions<PortalDb> options)
    : IdentityDbContext<PortalUser, IdentityRole<Guid>, Guid>(options)
{
    public DbSet<UserPermission> UserPermissions => Set<UserPermission>();
    public DbSet<Ticket> Tickets => Set<Ticket>();
    public DbSet<TicketMessage> TicketMessages => Set<TicketMessage>();
    public DbSet<TicketAttachment> TicketAttachments => Set<TicketAttachment>();
    public DbSet<TicketHistory> TicketHistory => Set<TicketHistory>();
    public DbSet<TelegramRoute> TelegramRoutes => Set<TelegramRoute>();
    public DbSet<NotificationJob> NotificationJobs => Set<NotificationJob>();
    public DbSet<AuditLog> AuditLogs => Set<AuditLog>();

    protected override void OnModelCreating(ModelBuilder b)
    {
        base.OnModelCreating(b);
        b.HasSequence<long>("ticket_numbers").StartsAt(1);

        b.Entity<PortalUser>(e =>
        {
            e.Property(u => u.DisplayName).HasMaxLength(64);
            e.HasMany(u => u.Permissions).WithOne().HasForeignKey(p => p.UserId).OnDelete(DeleteBehavior.Cascade);
        });
        b.Entity<UserPermission>(e =>
        {
            e.HasKey(p => new { p.UserId, p.Permission });
            e.Property(p => p.Permission).HasMaxLength(64);
        });

        b.Entity<Ticket>(e =>
        {
            e.Property(t => t.Number).HasDefaultValueSql("nextval('ticket_numbers')");
            e.HasIndex(t => t.Number).IsUnique();
            e.HasIndex(t => t.IdempotencyKey).IsUnique();
            e.HasIndex(t => new { t.Category, t.Status });
            e.HasIndex(t => t.AuthorId);
            e.Property(t => t.Category).HasMaxLength(32);
            e.Property(t => t.Title).HasMaxLength(Limits.TitleMax);
            e.Property(t => t.Description).HasMaxLength(Limits.TextMax);
            e.Property(t => t.Steps).HasMaxLength(Limits.TextMax);
            e.Property(t => t.Expected).HasMaxLength(Limits.TextMax);
            e.Property(t => t.Actual).HasMaxLength(Limits.TextMax);
            e.Property(t => t.GameVersion).HasMaxLength(64);
            e.Property(t => t.ModVersion).HasMaxLength(64);
            e.Property(t => t.LauncherVersion).HasMaxLength(64);
            e.Property(t => t.GuestEmail).HasMaxLength(256);
            e.Property(t => t.GuestTokenHash).HasMaxLength(64);
            e.Property(t => t.IdempotencyKey).HasMaxLength(64);
            e.Property(t => t.IdempotencyFingerprint).HasMaxLength(64);
            e.Property(t => t.CorrelationId).HasMaxLength(64);
            e.Property(t => t.Status).HasConversion<string>().HasMaxLength(16);
            e.Property(t => t.Priority).HasConversion<string>().HasMaxLength(16);
            e.Property(t => t.Source).HasConversion<string>().HasMaxLength(16);
            e.HasOne(t => t.Author).WithMany().HasForeignKey(t => t.AuthorId).OnDelete(DeleteBehavior.SetNull);
            e.HasOne(t => t.Assignee).WithMany().HasForeignKey(t => t.AssigneeId).OnDelete(DeleteBehavior.SetNull);
            e.HasOne(t => t.DuplicateOf).WithMany().HasForeignKey(t => t.DuplicateOfId).OnDelete(DeleteBehavior.SetNull);
            e.HasMany(t => t.Messages).WithOne().HasForeignKey(m => m.TicketId).OnDelete(DeleteBehavior.Cascade);
            e.HasMany(t => t.Attachments).WithOne().HasForeignKey(a => a.TicketId).OnDelete(DeleteBehavior.Cascade);
            e.HasMany(t => t.History).WithOne().HasForeignKey(h => h.TicketId).OnDelete(DeleteBehavior.Cascade);
        });
        b.Entity<TicketMessage>(e =>
        {
            e.Property(m => m.Body).HasMaxLength(Limits.TextMax);
            e.HasOne(m => m.Author).WithMany().HasForeignKey(m => m.AuthorId).OnDelete(DeleteBehavior.SetNull);
        });
        b.Entity<TicketAttachment>(e =>
        {
            e.Property(a => a.ObjectKey).HasMaxLength(128);
            e.HasIndex(a => a.ObjectKey).IsUnique();
            e.Property(a => a.FileName).HasMaxLength(Limits.FileNameMax);
            e.Property(a => a.ContentType).HasMaxLength(64);
            e.Property(a => a.Sha256).HasMaxLength(64);
            e.Property(a => a.Scan).HasConversion<string>().HasMaxLength(16);
            e.Property(a => a.ScanDetail).HasMaxLength(256);
        });
        b.Entity<TicketHistory>(e =>
        {
            e.Property(h => h.Action).HasMaxLength(32);
            e.Property(h => h.From).HasMaxLength(128);
            e.Property(h => h.To).HasMaxLength(128);
        });
        b.Entity<TelegramRoute>(e =>
        {
            e.HasIndex(r => r.Category).IsUnique();
            e.Property(r => r.Category).HasMaxLength(32);
            e.Property(r => r.ChatId).HasMaxLength(64);
        });
        b.Entity<NotificationJob>(e =>
        {
            e.HasIndex(j => new { j.State, j.NextAttemptAt });
            e.Property(j => j.Kind).HasMaxLength(16);
            e.Property(j => j.ChatId).HasMaxLength(64);
            e.Property(j => j.Text).HasMaxLength(4096);
            e.Property(j => j.State).HasConversion<string>().HasMaxLength(16);
            e.Property(j => j.LastError).HasMaxLength(512);
        });
        b.Entity<AuditLog>(e =>
        {
            e.HasIndex(a => a.At);
            e.Property(a => a.Action).HasMaxLength(64);
            e.Property(a => a.Target).HasMaxLength(128);
            e.Property(a => a.Detail).HasMaxLength(1024);
        });
    }
}

public static class Limits
{
    public const int TitleMax = 140;
    public const int TextMax = 20_000;
    public const int FileNameMax = 128;
}
