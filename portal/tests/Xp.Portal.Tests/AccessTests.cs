using System.Net;
using System.Net.Http.Json;
using System.Net.Sockets;
using System.Security.Claims;
using System.Text;
using Microsoft.AspNetCore.Identity;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Options;
using Xp.Portal.Auth;
using Xp.Portal.Data;
using Xp.Portal.Files;
using Xp.Portal.Tickets;

namespace Xp.Portal.Tests;

public sealed class AccessTests(PortalFactory f) : IClassFixture<PortalFactory>
{
    static Viewer As(string? role, params string[] perms)
    {
        var claims = new List<Claim> { new(ClaimTypes.NameIdentifier, Guid.NewGuid().ToString()) };
        if (role is not null) claims.Add(new Claim(ClaimTypes.Role, role));
        claims.AddRange(perms.Select(p => new Claim(Permissions.ClaimType, p)));
        return new Viewer(new ClaimsPrincipal(new ClaimsIdentity(claims, "test")));
    }

    async Task<Ticket> NewAsync(string category, string title = "t") => await f.ScopedAsync(async sp =>
        (await sp.GetRequiredService<TicketService>().CreateAsync(
            new NewTicket(category, title, "d"), null, null, null, default)).Ticket);

    [Fact]
    public void Role_matrix_of_ticket_categories()
    {
        Assert.Empty(As(null).TicketCategories);
        Assert.Empty(As(Roles.User).TicketCategories);
        Assert.Empty(As(Roles.Admin).TicketCategories);                 // an admin with no permission sees nothing
        Assert.Equal(["code"], As(Roles.Admin, "tickets.code").TicketCategories);
        Assert.Empty(As(Roles.User, "tickets.code").TicketCategories);  // a stray permission without the role does nothing
        Assert.Equal(Categories.All.Order(), As(Roles.SuperAdmin).TicketCategories.Order());
    }

    [Fact]
    public async Task Code_admin_never_sees_graphics_tickets()
    {
        var code = await NewAsync("code", "code-bug");
        var art = await NewAsync("graphics", "art-bug");
        var admin = As(Roles.Admin, "tickets.code");
        var seen = await f.DbAsync(db => admin.VisibleToStaff(db.Tickets).Select(t => t.Number).ToListAsync());
        Assert.Contains(code.Number, seen);
        Assert.DoesNotContain(art.Number, seen);
        Assert.False(admin.CanRead(art, null));
        Assert.True(admin.CanRead(code, null));
        Assert.True(As(Roles.SuperAdmin).CanRead(art, null));
    }

    [Fact]
    public async Task Duplicate_target_must_be_visible_to_the_admin()
    {
        var code = await NewAsync("code");
        var art = await NewAsync("graphics");
        var admin = As(Roles.Admin, "tickets.code");
        var e = await Assert.ThrowsAsync<TicketException>(() => f.ScopedAsync(async sp =>
        {
            var db = sp.GetRequiredService<PortalDb>();
            var t = await db.Tickets.FirstAsync(x => x.Id == code.Id);
            await sp.GetRequiredService<TicketService>().MarkDuplicateAsync(t, art.Number, admin, default);
            return 0;
        }));
        Assert.Equal("duplicate_target_invalid", e.Code);
    }

    [Fact]
    public async Task Status_machine_refuses_jumps()
    {
        var t = await NewAsync("code");
        var actor = Guid.Empty;
        await f.ScopedAsync(async sp =>
        {
            var db = sp.GetRequiredService<PortalDb>();
            var svc = sp.GetRequiredService<TicketService>();
            var x = await db.Tickets.FirstAsync(y => y.Id == t.Id);
            Assert.Equal("status_move_invalid", (await Assert.ThrowsAsync<TicketException>(() => svc.ChangeStatusAsync(x, TicketStatus.Closed, actor, default))).Code);
            Assert.Equal("use_duplicate", (await Assert.ThrowsAsync<TicketException>(() => svc.ChangeStatusAsync(x, TicketStatus.Duplicate, actor, default))).Code);
            await svc.ChangeStatusAsync(x, TicketStatus.InProgress, actor, default);
            await svc.ChangeStatusAsync(x, TicketStatus.Resolved, actor, default);
            await svc.ChangeStatusAsync(x, TicketStatus.Closed, actor, default);
            Assert.Equal("ticket_closed", (await Assert.ThrowsAsync<TicketException>(() => svc.AddMessageAsync(x, "hello?", null, false, false, default))).Code);
            var history = await db.TicketHistory.Where(h => h.TicketId == x.Id && h.Action == "status").OrderBy(h => h.Id).Select(h => h.To).ToListAsync();
            Assert.Equal(["InProgress", "Resolved", "Closed"], history);
            return 0;
        });
    }

    [Fact]
    public async Task Only_staff_of_the_category_can_be_assigned()
    {
        var art = await NewAsync("graphics");
        var (coder, artist, super) = await f.ScopedAsync(async sp =>
        {
            var users = sp.GetRequiredService<UserManager<PortalUser>>();
            async Task<Guid> Make(string name, string role, string? perm)
            {
                var u = new PortalUser { UserName = name + "@x.test", Email = name + "@x.test", DisplayName = name };
                Assert.True((await users.CreateAsync(u, "Long-enough-passw0rd!")).Succeeded);
                await users.AddToRoleAsync(u, role);
                if (perm is not null)
                {
                    var db = sp.GetRequiredService<PortalDb>();
                    db.UserPermissions.Add(new UserPermission { UserId = u.Id, Permission = perm });
                    await db.SaveChangesAsync();
                }
                return u.Id;
            }
            return (await Make("coder", Roles.Admin, "tickets.code"), await Make("artist", Roles.Admin, "tickets.graphics"), await Make("boss", Roles.SuperAdmin, null));
        });
        await f.ScopedAsync(async sp =>
        {
            var db = sp.GetRequiredService<PortalDb>();
            var svc = sp.GetRequiredService<TicketService>();
            var x = await db.Tickets.FirstAsync(y => y.Id == art.Id);
            Assert.Equal("assignee_not_allowed", (await Assert.ThrowsAsync<TicketException>(() => svc.AssignAsync(x, coder, super, default))).Code);
            await svc.AssignAsync(x, artist, super, default);
            await svc.AssignAsync(x, super, super, default);
            Assert.Equal(super, (await db.Tickets.AsNoTracking().FirstAsync(y => y.Id == art.Id)).AssigneeId);
            return 0;
        });
    }

    [Fact]
    public void Guest_token_is_stored_only_as_a_hash()
    {
        var token = GuestTokens.New();
        var hash = GuestTokens.Hash(token);
        Assert.DoesNotContain(token, hash);
        Assert.True(GuestTokens.Matches(token, hash));
        Assert.False(GuestTokens.Matches(token + "x", hash));
    }

    [Fact]
    public void Argon2_roundtrip_rehash_and_tamper()
    {
        var weak = new Argon2PasswordHasher(Options.Create(new Argon2Options { MemoryKib = 1024, Iterations = 1, Parallelism = 1 }));
        var strong = new Argon2PasswordHasher(Options.Create(new Argon2Options { MemoryKib = 2048, Iterations = 2, Parallelism = 1 }));
        var u = new PortalUser();
        var h = weak.HashPassword(u, "correct horse");
        Assert.StartsWith("$argon2id$v=19$m=1024,t=1,p=1$", h);
        Assert.Equal(PasswordVerificationResult.Success, weak.VerifyHashedPassword(u, h, "correct horse"));
        Assert.Equal(PasswordVerificationResult.Failed, weak.VerifyHashedPassword(u, h, "correct horsE"));
        Assert.Equal(PasswordVerificationResult.SuccessRehashNeeded, strong.VerifyHashedPassword(u, h, "correct horse"));
        Assert.Equal(PasswordVerificationResult.Failed, weak.VerifyHashedPassword(u, h.Replace("m=1024", "m=99999999"), "correct horse"));
        Assert.Equal(PasswordVerificationResult.Failed, weak.VerifyHashedPassword(u, "AQAAAAIAAYagAAAAE", "x"));
    }

    [Fact]
    public void Signed_links_expire_and_resist_tampering()
    {
        var urls = f.Services.GetRequiredService<SignedUrls>();
        var a = new TicketAttachment();
        var link = urls.For(a);
        var q = System.Web.HttpUtility.ParseQueryString(link[link.IndexOf('?')..]);
        var exp = long.Parse(q["exp"]!);
        var sig = q["sig"]!;
        Assert.True(urls.Valid(a.Id, exp, sig));
        Assert.False(urls.Valid(Guid.NewGuid(), exp, sig));         // another file
        Assert.False(urls.Valid(a.Id, exp + 3600, sig));           // longer life
        Assert.False(urls.Valid(a.Id, exp, sig[..^2] + "AA"));
        Assert.False(urls.Valid(a.Id, exp, null));
        f.Clock.Advance(TimeSpan.FromMinutes(6));
        Assert.False(urls.Valid(a.Id, exp, sig));
    }

    [Fact]
    public async Task Signed_link_alone_does_not_open_a_file_for_a_stranger()
    {
        var urls = f.Services.GetRequiredService<SignedUrls>();
        var r = await f.CreateClient().GetAsync(urls.For(new TicketAttachment()));
        Assert.Equal(HttpStatusCode.NotFound, r.StatusCode);
    }

    // ---- antivirus ----

    static async Task<(TcpListener, Task)> FakeClamd()
    {
        var l = new TcpListener(IPAddress.Loopback, 0);
        l.Start();
        var loop = Task.Run(async () =>
        {
            while (true)
            {
                using var c = await l.AcceptTcpClientAsync();
                var s = c.GetStream();
                var data = new MemoryStream();
                var cmd = new byte[10];
                await s.ReadExactlyAsync(cmd);
                var len = new byte[4];
                while (true)
                {
                    await s.ReadExactlyAsync(len);
                    var n = System.Buffers.Binary.BinaryPrimitives.ReadInt32BigEndian(len);
                    if (n == 0) break;
                    var buf = new byte[n];
                    await s.ReadExactlyAsync(buf);
                    data.Write(buf);
                }
                var infected = Encoding.ASCII.GetString(data.ToArray()).Contains("EICAR");
                await s.WriteAsync(Encoding.ASCII.GetBytes(infected ? "stream: Eicar-Test-Signature FOUND\0" : "stream: OK\0"));
            }
        });
        return (l, loop);
    }

    async Task<Guid> AttachAsync(Ticket t, string name, byte[] data) => await f.ScopedAsync(async sp =>
    {
        var store = sp.GetRequiredService<ObjectStore>();
        var key = ObjectStore.NewKey();
        await using (var w = store.Create(key)) await w.WriteAsync(data);
        var db = sp.GetRequiredService<PortalDb>();
        var a = new TicketAttachment { TicketId = t.Id, ObjectKey = key, FileName = name, ContentType = "text/plain", Size = data.Length, Sha256 = "" };
        db.TicketAttachments.Add(a);
        await db.SaveChangesAsync();
        return a.Id;
    });

    [Fact]
    public async Task Scanner_quarantines_infected_and_marks_unscanned_without_clamd()
    {
        var t = await NewAsync("code");
        var (listener, _) = await FakeClamd();
        try
        {
            var clean = await AttachAsync(t, "a.log", "all fine"u8.ToArray());
            var bad = await AttachAsync(t, "b.log", "X5O!P%@AP EICAR-STANDARD-ANTIVIRUS-TEST-FILE"u8.ToArray());
            var port = ((IPEndPoint)listener.LocalEndpoint).Port;
            var scanner = new ClamdScanner(Options.Create(new AttachmentOptions { ClamdAddress = $"127.0.0.1:{port}" }));
            var worker = ActivatorUtilities.CreateInstance<ScanWorker>(f.Services, scanner);
            await worker.PassAsync(default);
            Assert.Equal(ScanStatus.Clean, await f.DbAsync(db => db.TicketAttachments.Where(a => a.Id == clean).Select(a => a.Scan).FirstAsync()));
            Assert.Equal(ScanStatus.Quarantined, await f.DbAsync(db => db.TicketAttachments.Where(a => a.Id == bad).Select(a => a.Scan).FirstAsync()));

            var later = await AttachAsync(t, "c.log", "x"u8.ToArray());
            var none = ActivatorUtilities.CreateInstance<ScanWorker>(f.Services, new ClamdScanner(Options.Create(new AttachmentOptions())));
            await none.PassAsync(default);
            Assert.Equal(ScanStatus.Unscanned, await f.DbAsync(db => db.TicketAttachments.Where(a => a.Id == later).Select(a => a.Scan).FirstAsync()));
        }
        finally { listener.Stop(); }
    }

    [Fact]
    public async Task Clamd_down_leaves_the_file_pending()
    {
        var t = await NewAsync("code");
        var id = await AttachAsync(t, "d.log", "x"u8.ToArray());
        var dead = new TcpListener(IPAddress.Loopback, 0);
        dead.Start();
        var port = ((IPEndPoint)dead.LocalEndpoint).Port;
        dead.Stop();   // nobody listens there now
        var worker = ActivatorUtilities.CreateInstance<ScanWorker>(f.Services, new ClamdScanner(Options.Create(new AttachmentOptions { ClamdAddress = $"127.0.0.1:{port}" })));
        await worker.PassAsync(default);
        Assert.Equal(ScanStatus.Pending, await f.DbAsync(db => db.TicketAttachments.Where(a => a.Id == id).Select(a => a.Scan).FirstAsync()));
    }
}

public sealed class LimitedFactory : PortalFactory
{
    public LimitedFactory() => Settings["RateLimits:TicketsPer10Min"] = "2";
}

public sealed class RateLimitTests(LimitedFactory f) : IClassFixture<LimitedFactory>
{
    [Fact]
    public async Task Third_ticket_in_ten_minutes_is_429()
    {
        var c = f.CreateClient();
        object body = new { category = "code", title = "spam", description = "spam" };
        Assert.Equal(HttpStatusCode.Created, (await c.PostAsJsonAsync("/api/v1/tickets", body)).StatusCode);
        Assert.Equal(HttpStatusCode.Created, (await c.PostAsJsonAsync("/api/v1/tickets", body)).StatusCode);
        Assert.Equal(HttpStatusCode.TooManyRequests, (await c.PostAsJsonAsync("/api/v1/tickets", body)).StatusCode);
    }
}
