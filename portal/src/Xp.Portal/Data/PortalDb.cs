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
    public DbSet<UpstreamState> UpstreamStates => Set<UpstreamState>();
    public DbSet<AuditLog> AuditLogs => Set<AuditLog>();
    public DbSet<GameMod> Mods => Set<GameMod>();
    public DbSet<ModText> ModTexts => Set<ModText>();
    public DbSet<WikiPage> WikiPages => Set<WikiPage>();
    public DbSet<WikiRevision> WikiRevisions => Set<WikiRevision>();
    public DbSet<ForumSection> ForumSections => Set<ForumSection>();
    public DbSet<ForumSectionText> ForumSectionTexts => Set<ForumSectionText>();
    public DbSet<ForumTopic> ForumTopics => Set<ForumTopic>();
    public DbSet<ForumPost> ForumPosts => Set<ForumPost>();

    protected override void OnModelCreating(ModelBuilder b)
    {
        base.OnModelCreating(b);
        b.HasSequence<long>("ticket_numbers").StartsAt(1);
        b.HasSequence<long>("forum_topic_numbers").StartsAt(1);
        Community(b);

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
            e.HasIndex(t => t.Language);
            e.Property(t => t.Category).HasMaxLength(32);
            e.Property(t => t.Title).HasMaxLength(Limits.TitleMax);
            e.Property(t => t.Description).HasMaxLength(Limits.TextMax);
            e.Property(t => t.Steps).HasMaxLength(Limits.TextMax);
            e.Property(t => t.Expected).HasMaxLength(Limits.TextMax);
            e.Property(t => t.Actual).HasMaxLength(Limits.TextMax);
            e.Property(t => t.Context).HasMaxLength(Limits.ContextMax);
            e.Property(t => t.Language).HasMaxLength(Xp.Portal.Tickets.TicketLanguage.Max);
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
        b.Entity<UpstreamState>(e =>
        {
            e.HasKey(u => u.Source);
            e.Property(u => u.Source).HasMaxLength(32);
            e.Property(u => u.Value).HasMaxLength(256);
            e.Property(u => u.Label).HasMaxLength(512);
            e.Property(u => u.Url).HasMaxLength(512);
            e.Property(u => u.LastError).HasMaxLength(512);
        });
        b.Entity<AuditLog>(e =>
        {
            e.HasIndex(a => a.At);
            e.Property(a => a.Action).HasMaxLength(64);
            e.Property(a => a.Target).HasMaxLength(128);
            e.Property(a => a.Detail).HasMaxLength(1024);
        });
    }

    /// <summary>Mods, wiki and forum. Kept in its own method so the ticket model above stays readable.</summary>
    static void Community(ModelBuilder b)
    {
        b.Entity<GameMod>(e =>
        {
            e.HasIndex(m => m.Slug).IsUnique();
            e.Property(m => m.Slug).HasMaxLength(CommunityLimits.SlugMax);
            e.Property(m => m.Author).HasMaxLength(CommunityLimits.NameMax);
            e.Property(m => m.HomeUrl).HasMaxLength(512);
            e.Property(m => m.DownloadUrl).HasMaxLength(512);
            e.Property(m => m.Version).HasMaxLength(64);
            e.Property(m => m.Image).HasMaxLength(128);
            e.HasMany(m => m.Texts).WithOne().HasForeignKey(t => t.ModId).OnDelete(DeleteBehavior.Cascade);
        });
        b.Entity<ModText>(e =>
        {
            e.HasKey(t => new { t.ModId, t.Lang });
            e.Property(t => t.Lang).HasMaxLength(2);
            e.Property(t => t.Name).HasMaxLength(CommunityLimits.NameMax);
            e.Property(t => t.Summary).HasMaxLength(CommunityLimits.SummaryMax);
            e.Property(t => t.Body).HasMaxLength(CommunityLimits.ArticleMax);
        });

        b.Entity<WikiPage>(e =>
        {
            // one address per mod and language; the same slug may exist in ru and en
            e.HasIndex(p => new { p.ModId, p.Lang, p.Slug }).IsUnique();
            e.HasIndex(p => new { p.ModId, p.Lang, p.Section });
            e.Property(p => p.Slug).HasMaxLength(CommunityLimits.SlugMax);
            e.Property(p => p.Lang).HasMaxLength(2);
            e.Property(p => p.Title).HasMaxLength(CommunityLimits.TitleMax);
            e.Property(p => p.Body).HasMaxLength(CommunityLimits.ArticleMax);
            e.Property(p => p.Section).HasMaxLength(CommunityLimits.SlugMax);
            e.Property(p => p.Source).HasMaxLength(256);
            e.Property(p => p.SourceVersion).HasMaxLength(64);
            e.Property(p => p.Kind).HasConversion<string>().HasMaxLength(16);
            e.HasOne(p => p.Mod).WithMany().HasForeignKey(p => p.ModId).OnDelete(DeleteBehavior.Cascade);
            e.HasOne(p => p.Editor).WithMany().HasForeignKey(p => p.EditorId).OnDelete(DeleteBehavior.SetNull);
        });
        b.Entity<WikiRevision>(e =>
        {
            e.HasIndex(r => new { r.PageId, r.At });
            e.Property(r => r.Title).HasMaxLength(CommunityLimits.TitleMax);
            e.Property(r => r.Body).HasMaxLength(CommunityLimits.ArticleMax);
            e.Property(r => r.Comment).HasMaxLength(CommunityLimits.SummaryMax);
            e.HasOne<WikiPage>().WithMany().HasForeignKey(r => r.PageId).OnDelete(DeleteBehavior.Cascade);
            e.HasOne(r => r.Editor).WithMany().HasForeignKey(r => r.EditorId).OnDelete(DeleteBehavior.SetNull);
        });

        b.Entity<ForumSection>(e =>
        {
            e.HasIndex(s => s.Slug).IsUnique();
            e.Property(s => s.Slug).HasMaxLength(CommunityLimits.SlugMax);
            e.HasOne(s => s.Mod).WithMany().HasForeignKey(s => s.ModId).OnDelete(DeleteBehavior.SetNull);
            e.HasMany(s => s.Texts).WithOne().HasForeignKey(t => t.SectionId).OnDelete(DeleteBehavior.Cascade);
        });
        b.Entity<ForumSectionText>(e =>
        {
            e.HasKey(t => new { t.SectionId, t.Lang });
            e.Property(t => t.Lang).HasMaxLength(2);
            e.Property(t => t.Name).HasMaxLength(CommunityLimits.NameMax);
            e.Property(t => t.Summary).HasMaxLength(CommunityLimits.SummaryMax);
        });
        b.Entity<ForumTopic>(e =>
        {
            e.Property(t => t.Number).HasDefaultValueSql("nextval('forum_topic_numbers')");
            e.HasIndex(t => t.Number).IsUnique();
            // the board list: pinned first, then by the last post - this index is the one it uses
            e.HasIndex(t => new { t.SectionId, t.Pinned, t.LastPostAt });
            e.Property(t => t.Title).HasMaxLength(CommunityLimits.TitleMax);
            e.HasOne(t => t.Section).WithMany().HasForeignKey(t => t.SectionId).OnDelete(DeleteBehavior.Cascade);
            e.HasOne(t => t.Author).WithMany().HasForeignKey(t => t.AuthorId).OnDelete(DeleteBehavior.Cascade);
            e.HasOne(t => t.LastPostAuthor).WithMany().HasForeignKey(t => t.LastPostAuthorId).OnDelete(DeleteBehavior.SetNull);
        });
        b.Entity<ForumPost>(e =>
        {
            e.HasIndex(p => new { p.TopicId, p.CreatedAt });
            e.Property(p => p.Body).HasMaxLength(CommunityLimits.PostMax);
            e.HasOne(p => p.Topic).WithMany().HasForeignKey(p => p.TopicId).OnDelete(DeleteBehavior.Cascade);
            e.HasOne(p => p.Author).WithMany().HasForeignKey(p => p.AuthorId).OnDelete(DeleteBehavior.Cascade);
        });
    }
}

public static class Limits
{
    public const int TitleMax = 140;
    public const int TextMax = 20_000;
    public const int FileNameMax = 128;
    /// <summary>Technical data the launcher adds to an F8 or crash report: versions, OS, screen mode.</summary>
    public const int ContextMax = 4_000;
}
