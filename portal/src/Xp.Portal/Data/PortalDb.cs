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
    public DbSet<DeviceToken> DeviceTokens => Set<DeviceToken>();
    public DbSet<DeviceLinkCode> DeviceLinkCodes => Set<DeviceLinkCode>();
    public DbSet<GameMod> Mods => Set<GameMod>();
    public DbSet<ModText> ModTexts => Set<ModText>();
    public DbSet<WikiPage> WikiPages => Set<WikiPage>();
    public DbSet<WikiRevision> WikiRevisions => Set<WikiRevision>();
    public DbSet<ForumSection> ForumSections => Set<ForumSection>();
    public DbSet<ForumSectionText> ForumSectionTexts => Set<ForumSectionText>();
    public DbSet<ForumTopic> ForumTopics => Set<ForumTopic>();
    public DbSet<ForumPost> ForumPosts => Set<ForumPost>();
    public DbSet<PackReview> PackReviews => Set<PackReview>();
    public DbSet<PackReviewFrame> PackReviewFrames => Set<PackReviewFrame>();
    public DbSet<ArtPack> ArtPacks => Set<ArtPack>();
    public DbSet<FriendRequest> FriendRequests => Set<FriendRequest>();
    public DbSet<Friendship> Friendships => Set<Friendship>();
    public DbSet<UserBlock> UserBlocks => Set<UserBlock>();
    public DbSet<VoiceRoom> VoiceRooms => Set<VoiceRoom>();
    public DbSet<RoomInvite> RoomInvites => Set<RoomInvite>();
    public DbSet<RoomBan> RoomBans => Set<RoomBan>();
    public DbSet<RoomSpeakingRestriction> RoomSpeakingRestrictions => Set<RoomSpeakingRestriction>();
    public DbSet<VoiceAccountBan> VoiceAccountBans => Set<VoiceAccountBan>();
    public DbSet<VoiceEvent> VoiceEvents => Set<VoiceEvent>();
    public DbSet<VoiceEventTicket> VoiceEventTickets => Set<VoiceEventTicket>();
    public DbSet<VoiceJob> VoiceJobs => Set<VoiceJob>();

    protected override void OnModelCreating(ModelBuilder b)
    {
        base.OnModelCreating(b);
        b.HasSequence<long>("ticket_numbers").StartsAt(1);
        b.HasSequence<long>("forum_topic_numbers").StartsAt(1);
        Community(b);
        Art(b);
        Voice(b);

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
        b.Entity<DeviceToken>(e =>
        {
            // the hash is how a request finds its device: one row per secret, looked up by equality
            e.HasIndex(d => d.TokenHash).IsUnique();
            e.HasIndex(d => d.UserId);
            e.Property(d => d.TokenHash).HasMaxLength(64);
            e.Property(d => d.Name).HasMaxLength(DeviceLimits.NameMax);
            e.HasOne(d => d.User).WithMany().HasForeignKey(d => d.UserId).OnDelete(DeleteBehavior.Cascade);
        });
        b.Entity<DeviceLinkCode>(e =>
        {
            e.HasKey(c => c.Code);
            e.HasIndex(c => c.DeviceId).IsUnique();
            e.HasIndex(c => c.ExpiresAt);
            e.Property(c => c.Code).HasMaxLength(DeviceLimits.CodeMax);
            e.Property(c => c.Name).HasMaxLength(DeviceLimits.NameMax);
        });
    }

    /// <summary>
    /// Friends and voice rooms. Everything hangs off the accounts and the room with a cascade: deleting
    /// an account or a room leaves nothing of it behind (VOICE_CHAT.md section 7), only the name of
    /// whoever acted on someone else is let go (set null) so the other person's record stays whole.
    /// </summary>
    static void Voice(ModelBuilder b)
    {
        b.Entity<FriendRequest>(e =>
        {
            e.HasIndex(r => new { r.SenderId, r.RecipientId }).IsUnique().HasFilter("\"Status\" = 'Pending'");
            e.HasIndex(r => new { r.RecipientId, r.Status });
            e.HasIndex(r => new { r.SenderId, r.CreatedAt });
            e.Property(r => r.Status).HasConversion<string>().HasMaxLength(16);
            e.HasOne<PortalUser>().WithMany().HasForeignKey(r => r.SenderId).OnDelete(DeleteBehavior.Cascade);
            e.HasOne<PortalUser>().WithMany().HasForeignKey(r => r.RecipientId).OnDelete(DeleteBehavior.Cascade);
        });
        b.Entity<Friendship>(e =>
        {
            e.HasKey(f => new { f.UserLowId, f.UserHighId });
            e.HasIndex(f => f.UserHighId);
            e.HasOne<PortalUser>().WithMany().HasForeignKey(f => f.UserLowId).OnDelete(DeleteBehavior.Cascade);
            e.HasOne<PortalUser>().WithMany().HasForeignKey(f => f.UserHighId).OnDelete(DeleteBehavior.Cascade);
        });
        b.Entity<UserBlock>(e =>
        {
            e.HasKey(x => new { x.BlockerId, x.BlockedId });
            e.HasIndex(x => x.BlockedId);
            e.HasOne<PortalUser>().WithMany().HasForeignKey(x => x.BlockerId).OnDelete(DeleteBehavior.Cascade);
            e.HasOne<PortalUser>().WithMany().HasForeignKey(x => x.BlockedId).OnDelete(DeleteBehavior.Cascade);
        });
        b.Entity<VoiceRoom>(e =>
        {
            e.HasIndex(r => r.PublicId).IsUnique();
            e.HasIndex(r => r.OwnerId);
            e.Property(r => r.PublicId).HasMaxLength(VoiceLimits.PublicIdLength);
            e.Property(r => r.Title).HasMaxLength(VoiceLimits.TitleMax);
            e.Property(r => r.ClosedReason).HasMaxLength(VoiceLimits.ReasonMax);
            e.Property(r => r.Status).HasConversion<string>().HasMaxLength(16);
            e.HasOne(r => r.Owner).WithMany().HasForeignKey(r => r.OwnerId).OnDelete(DeleteBehavior.Cascade);
            e.HasOne<PortalUser>().WithMany().HasForeignKey(r => r.ClosedById).OnDelete(DeleteBehavior.SetNull);
        });
        b.Entity<RoomInvite>(e =>
        {
            e.HasKey(i => new { i.RoomId, i.UserId });
            e.HasIndex(i => new { i.UserId, i.Status });
            e.Property(i => i.Status).HasConversion<string>().HasMaxLength(16);
            e.HasOne<VoiceRoom>().WithMany().HasForeignKey(i => i.RoomId).OnDelete(DeleteBehavior.Cascade);
            e.HasOne<PortalUser>().WithMany().HasForeignKey(i => i.UserId).OnDelete(DeleteBehavior.Cascade);
        });
        b.Entity<RoomBan>(e =>
        {
            e.HasKey(x => new { x.RoomId, x.UserId });
            e.HasIndex(x => x.UserId);
            e.HasOne<VoiceRoom>().WithMany().HasForeignKey(x => x.RoomId).OnDelete(DeleteBehavior.Cascade);
            e.HasOne<PortalUser>().WithMany().HasForeignKey(x => x.UserId).OnDelete(DeleteBehavior.Cascade);
            e.HasOne<PortalUser>().WithMany().HasForeignKey(x => x.ById).OnDelete(DeleteBehavior.SetNull);
        });
        b.Entity<RoomSpeakingRestriction>(e =>
        {
            e.HasKey(x => new { x.RoomId, x.UserId });
            e.HasIndex(x => x.UserId);
            e.HasOne<VoiceRoom>().WithMany().HasForeignKey(x => x.RoomId).OnDelete(DeleteBehavior.Cascade);
            e.HasOne<PortalUser>().WithMany().HasForeignKey(x => x.UserId).OnDelete(DeleteBehavior.Cascade);
        });
        b.Entity<VoiceAccountBan>(e =>
        {
            e.HasIndex(x => x.UserId).IsUnique().HasFilter("\"LiftedAt\" IS NULL");
            e.Property(x => x.Reason).HasMaxLength(VoiceLimits.ReasonMax);
            e.HasOne<PortalUser>().WithMany().HasForeignKey(x => x.UserId).OnDelete(DeleteBehavior.Cascade);
            e.HasOne<PortalUser>().WithMany().HasForeignKey(x => x.ById).OnDelete(DeleteBehavior.SetNull);
            e.HasOne<PortalUser>().WithMany().HasForeignKey(x => x.LiftedById).OnDelete(DeleteBehavior.SetNull);
        });
        b.Entity<VoiceEvent>(e =>
        {
            e.HasIndex(x => new { x.RoomId, x.UserId, x.At });
            e.HasIndex(x => new { x.Kind, x.At });
            e.Property(x => x.Kind).HasMaxLength(32);
            e.Property(x => x.Reason).HasMaxLength(VoiceLimits.ReasonMax);
            // the room is a plain id: deleting a room must not take a complaint's evidence with it
            e.HasOne<PortalUser>().WithMany().HasForeignKey(x => x.UserId).OnDelete(DeleteBehavior.Cascade);
            e.HasOne<PortalUser>().WithMany().HasForeignKey(x => x.ActorId).OnDelete(DeleteBehavior.SetNull);
        });
        b.Entity<VoiceEventTicket>(e =>
        {
            e.HasKey(x => new { x.EventId, x.TicketId });
            e.HasIndex(x => x.TicketId);
            e.HasOne<VoiceEvent>().WithMany().HasForeignKey(x => x.EventId).OnDelete(DeleteBehavior.Cascade);
            e.HasOne<Ticket>().WithMany().HasForeignKey(x => x.TicketId).OnDelete(DeleteBehavior.Cascade);
        });
        b.Entity<VoiceJob>(e =>
        {
            e.HasIndex(j => new { j.State, j.NextAttemptAt });
            e.Property(j => j.Kind).HasConversion<string>().HasMaxLength(16);
            e.Property(j => j.State).HasConversion<string>().HasMaxLength(16);
            e.Property(j => j.LastError).HasMaxLength(512);
            e.Property(j => j.Identity).HasMaxLength(128);
        });
    }

    /// <summary>The art review: what there is to check, and what people said about it.</summary>
    static void Art(ModelBuilder b)
    {
        b.Entity<PackReview>(e =>
        {
            // the roadmap asks one question above all: who looked at this set
            e.HasIndex(r => new { r.Section, r.SetName });
            e.HasIndex(r => new { r.UserId, r.Section, r.SetName });
            e.HasIndex(r => r.IdempotencyKey);
            e.Property(r => r.Section).HasMaxLength(ReviewLimits.SectionMax);
            e.Property(r => r.SetName).HasMaxLength(ReviewLimits.SetMax);
            e.Property(r => r.ModVersion).HasMaxLength(ReviewLimits.VersionMax);
            e.Property(r => r.Tool).HasMaxLength(ReviewLimits.ToolMax);
            e.Property(r => r.IdempotencyKey).HasMaxLength(64);
            e.Property(r => r.RevokedReason).HasMaxLength(256);
            e.HasOne(r => r.User).WithMany().HasForeignKey(r => r.UserId).OnDelete(DeleteBehavior.Cascade);
            e.HasMany(r => r.Frames).WithOne(f => f.Review!).HasForeignKey(f => f.ReviewId).OnDelete(DeleteBehavior.Cascade);
        });
        b.Entity<PackReviewFrame>(e =>
        {
            // the repaint queue groups by the picture, not by the frame number
            e.HasIndex(f => f.Hd);
            e.HasIndex(f => f.Orig);
            e.Property(f => f.Orig).HasMaxLength(ReviewLimits.HashMax);
            e.Property(f => f.Hd).HasMaxLength(ReviewLimits.HashMax);
            e.Property(f => f.Verdict).HasMaxLength(ReviewLimits.VerdictMax);
            e.Property(f => f.Note).HasMaxLength(ReviewLimits.NoteMax);
        });
        b.Entity<ArtPack>(e =>
        {
            e.HasIndex(p => new { p.Section, p.Name }).IsUnique();
            e.Property(p => p.Section).HasMaxLength(ReviewLimits.SectionMax);
            e.Property(p => p.Name).HasMaxLength(ReviewLimits.SetMax);
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
