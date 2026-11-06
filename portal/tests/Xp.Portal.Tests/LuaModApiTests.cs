using System.IO.Compression;
using System.Net;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using Microsoft.AspNetCore.Identity;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Xp.Manifest;
using Xp.Portal.Auth;
using Xp.Portal.Data;
using Xp.Portal.Devices;
using Xp.Portal.Tickets;

namespace Xp.Portal.Tests;

/// <summary>
/// Offering a Lua mod from the launcher (docs/portal/LUA_MODS.md §8.1): a ticket of its own category with the archive,
/// only under a device token, and nothing is left behind when the archive is refused.
/// </summary>
public sealed class LuaModApiTests(PortalFactory f) : IClassFixture<PortalFactory>
{
    const string Password = "Long-enough-passw0rd!";

    async Task<(HttpClient Http, Guid Id)> LauncherAsync()
    {
        var email = $"lua-{Guid.NewGuid():N}@x.test";
        var id = await f.ScopedAsync(async sp =>
        {
            var users = sp.GetRequiredService<UserManager<PortalUser>>();
            var u = new PortalUser { UserName = email, Email = email, EmailConfirmed = true, DisplayName = email[..12] };
            Assert.True((await users.CreateAsync(u, Password)).Succeeded);
            return u.Id;
        });
        var token = DeviceSecrets.NewToken();
        await f.DbAsync(async db =>
        {
            db.DeviceTokens.Add(new DeviceToken { UserId = id, TokenHash = DeviceSecrets.Hash(token), Name = "test", CreatedAt = f.Clock.GetUtcNow() });
            return await db.SaveChangesAsync();
        });
        var c = f.CreateClient();
        c.DefaultRequestHeaders.Add("X-Device-Token", token);
        return (c, id);
    }

    static byte[] Zip(params (string Name, string Text)[] files)
    {
        using var ms = new MemoryStream();
        using (var zip = new ZipArchive(ms, ZipArchiveMode.Create, leaveOpen: true))
            foreach (var (name, text) in files)
            {
                using var w = new StreamWriter(zip.CreateEntry(name).Open());
                w.Write(text);
            }
        return ms.ToArray();
    }

    static byte[] GoodMod(string id = "mymod", string version = "1.0") => Zip(
        ("metadata.yml", $"id: {id}\nname: My mod\nversion: {version}\nmaster: xpiratez\nluaApi: 1\n"),
        ("main.lua", "on(\"battle_start\", function() end)\n"),
        ("Language/en-US.yml", "en-US:\n  STR_X: x\n"));

    static MultipartFormDataContent Form(byte[]? archive, object? meta)
    {
        var form = new MultipartFormDataContent();
        if (meta is not null) form.Add(new StringContent(JsonSerializer.Serialize(meta), Encoding.UTF8, "application/json"), "meta");
        if (archive is not null) form.Add(new ByteArrayContent(archive), "file", "mod.zip");
        return form;
    }

    static object Meta(string id = "mymod", string version = "1.0", bool rights = true, string license = "MIT", string description = "Does a thing") =>
        new { id, version, description, license, rightsConfirmed = rights, language = "ru", launcherVersion = "0.4.5", precheck = "signals: 1" };

    static async Task<string?> CodeOf(HttpResponseMessage r) =>
        JsonDocument.Parse(await r.Content.ReadAsStringAsync()).RootElement.TryGetProperty("code", out var c) ? c.GetString() : null;

    Task<int> CountAsync(Guid id) => f.DbAsync(db => db.Tickets.CountAsync(t => t.AuthorId == id));

    [Fact]
    public async Task Only_a_linked_launcher_gets_in()
    {
        Assert.Equal(HttpStatusCode.Unauthorized, (await f.CreateClient().GetAsync("/api/v1/lua-mods")).StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, (await f.CreateClient().PostAsync("/api/v1/lua-mods", Form(GoodMod(), Meta()))).StatusCode);
    }

    [Fact]
    public async Task An_offered_mod_is_a_ticket_with_its_archive_and_the_author_sees_its_step()
    {
        var (http, id) = await LauncherAsync();
        var bytes = GoodMod();
        var r = await http.PostAsync("/api/v1/lua-mods", Form(bytes, Meta()));
        Assert.Equal(HttpStatusCode.Created, r.StatusCode);
        var made = (await r.Content.ReadFromJsonAsync<LuaModSubmitted>())!;
        Assert.Equal("queue", made.Status);

        var (ticket, files) = await f.DbAsync(async db =>
        {
            var t = await db.Tickets.FirstAsync(x => x.Number == made.Number);
            return (t, await db.TicketAttachments.Where(a => a.TicketId == t.Id).ToListAsync());
        });
        Assert.Equal(Categories.LuaMod, ticket.Category);
        Assert.Equal(id, ticket.AuthorId);
        Assert.Null(ticket.GuestTokenHash);
        Assert.True(ticket.ConsentToFiles);
        Assert.Contains("license: MIT", ticket.Context);
        Assert.Contains("master: xpiratez", ticket.Context);
        Assert.Contains("precheck: signals: 1", ticket.Context);
        var file = Assert.Single(files);
        Assert.Equal("mymod-1.0.zip", file.FileName);
        Assert.Equal(bytes.Length, file.Size);

        var rows = (await http.GetFromJsonAsync<List<LuaModRow>>("/api/v1/lua-mods"))!;
        var row = Assert.Single(rows);
        Assert.Equal(("mymod", "1.0", "queue"), (row.Mod, row.Version, row.Status));
        Assert.Null(row.Reason);
    }

    [Theory]
    [InlineData("metadata.yml", "tool.exe", "file_executable")]
    [InlineData("metadata.yml", "code.luac", "lua_bytecode")]
    [InlineData("metadata.yml", "sub/../../evil.lua", "path_parent")]
    [InlineData("metadata.yml", "maps/a.map", "file_type")]
    [InlineData("other.yml", "main.lua", "metadata_missing")]
    public async Task A_refused_archive_leaves_no_ticket(string meta, string second, string code)
    {
        var (http, id) = await LauncherAsync();
        var r = await http.PostAsync("/api/v1/lua-mods", Form(Zip((meta, "id: mymod\nversion: 1.0\nluaApi: 1\n"), (second, "x")), Meta()));
        Assert.Equal(HttpStatusCode.BadRequest, r.StatusCode);
        Assert.Equal(code, await CodeOf(r));
        Assert.Equal(0, await CountAsync(id));
    }

    [Fact]
    public async Task What_the_author_must_say_is_required_and_a_broken_archive_is_refused()
    {
        var (http, id) = await LauncherAsync();
        async Task Refused(MultipartFormDataContent form, string code)
        {
            var r = await http.PostAsync("/api/v1/lua-mods", form);
            Assert.Equal(HttpStatusCode.BadRequest, r.StatusCode);
            Assert.Equal(code, await CodeOf(r));
        }
        await Refused(Form(GoodMod(), null), "meta_required");
        await Refused(Form(null, Meta()), "file_required");
        await Refused(Form(GoodMod(), Meta(rights: false)), "rights_required");
        await Refused(Form(GoodMod(), Meta(license: " ")), "license_required");
        await Refused(Form(GoodMod(), Meta(description: " ")), "description_required");
        await Refused(Form(GoodMod(), Meta(id: "../up")), "mod_id_invalid");
        await Refused(Form(GoodMod(), Meta(id: "other")), "metadata_mismatch");
        await Refused(Form(GoodMod(), Meta(version: "2.0")), "metadata_mismatch");
        await Refused(Form(Encoding.UTF8.GetBytes("PK not really"), Meta()), "archive_corrupt");
        Assert.Equal(0, await CountAsync(id));
    }

    [Fact]
    public async Task A_retry_is_not_a_second_mod_and_too_many_open_wait()
    {
        var (http, id) = await LauncherAsync();
        var post = new HttpRequestMessage(HttpMethod.Post, "/api/v1/lua-mods") { Content = Form(GoodMod(), Meta()) };
        post.Headers.Add("Idempotency-Key", "retry-key-" + id);
        Assert.Equal(HttpStatusCode.Created, (await http.SendAsync(post)).StatusCode);
        var again = new HttpRequestMessage(HttpMethod.Post, "/api/v1/lua-mods") { Content = Form(GoodMod(), Meta()) };
        again.Headers.Add("Idempotency-Key", "retry-key-" + id);
        Assert.Equal(HttpStatusCode.OK, (await http.SendAsync(again)).StatusCode);
        Assert.Equal(1, await CountAsync(id));

        for (var i = 2; i <= LuaModApi.MaxOpen; i++)
            Assert.Equal(HttpStatusCode.Created, (await http.PostAsync("/api/v1/lua-mods", Form(GoodMod("mod" + i), Meta("mod" + i)))).StatusCode);
        var over = await http.PostAsync("/api/v1/lua-mods", Form(GoodMod("mod9"), Meta("mod9")));
        Assert.Equal(HttpStatusCode.Conflict, over.StatusCode);
        Assert.Equal("too_many_open", await CodeOf(over));
    }

    [Fact]
    public async Task The_public_form_cannot_file_one_and_each_author_sees_only_their_own()
    {
        var guest = await f.CreateClient().PostAsJsonAsync("/api/v1/tickets",
            new { category = Categories.LuaMod, title = "Lua: x", description = "x", consentToFiles = true });
        Assert.Equal(HttpStatusCode.BadRequest, guest.StatusCode);

        var (a, _) = await LauncherAsync();
        var (b, _) = await LauncherAsync();
        Assert.Equal(HttpStatusCode.Created, (await a.PostAsync("/api/v1/lua-mods", Form(GoodMod(), Meta()))).StatusCode);
        Assert.Empty((await b.GetFromJsonAsync<List<LuaModRow>>("/api/v1/lua-mods"))!);
    }

    [Fact]
    public async Task The_team_moves_it_and_the_author_reads_the_answer()
    {
        var (http, _) = await LauncherAsync();
        var made = (await (await http.PostAsync("/api/v1/lua-mods", Form(GoodMod(), Meta()))).Content.ReadFromJsonAsync<LuaModSubmitted>())!;
        await f.DbAsync(async db =>
        {
            var t = await db.Tickets.FirstAsync(x => x.Number == made.Number);
            t.Status = TicketStatus.Rejected;
            db.TicketMessages.Add(new TicketMessage { TicketId = t.Id, FromStaff = true, Internal = true, Body = "inside note", CreatedAt = f.Clock.GetUtcNow().AddSeconds(2) });
            db.TicketMessages.Add(new TicketMessage { TicketId = t.Id, FromStaff = true, Body = "main.lua calls something it may not", CreatedAt = f.Clock.GetUtcNow().AddSeconds(1) });
            return await db.SaveChangesAsync();
        });
        var row = Assert.Single((await http.GetFromJsonAsync<List<LuaModRow>>("/api/v1/lua-mods"))!);
        Assert.Equal("rejected", row.Status);
        Assert.Equal("main.lua calls something it may not", row.Reason);
    }

    [Fact]
    public async Task A_mod_waiting_for_its_author_is_not_closed_because_the_author_would_read_approved()
    {
        var (http, _) = await LauncherAsync();
        var made = (await (await http.PostAsync("/api/v1/lua-mods", Form(GoodMod(), Meta()))).Content.ReadFromJsonAsync<LuaModSubmitted>())!;
        await f.ScopedAsync(async sp =>
        {
            var db = sp.GetRequiredService<PortalDb>();
            var svc = sp.GetRequiredService<TicketService>();
            var t = await db.Tickets.FirstAsync(x => x.Number == made.Number);
            t.Status = TicketStatus.NeedsInfo;
            await db.SaveChangesAsync();
            Assert.Equal("status_move_invalid", (await Assert.ThrowsAsync<TicketException>(() => svc.ChangeStatusAsync(t, TicketStatus.Closed, Guid.Empty, default))).Code);
            await svc.ChangeStatusAsync(t, TicketStatus.Rejected, Guid.Empty, default);
            Assert.Equal(TicketStatus.Rejected, t.Status);
            return 0;
        });
    }

    [Fact]
    public void The_archive_rules_are_the_same_as_the_check_that_decides()
    {
        // tools/lua_mod_check.py is what decides, in isolation; here the same list is only said earlier
        var py = File.ReadAllText(Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "../../../../../../tools/lua_mod_check.py")));
        Assert.Contains($"MAX_FILES = {LuaModArchive.MaxFiles}", py);
        Assert.Contains($"MAX_ARCHIVE = {LuaModArchive.MaxArchive / 1024 / 1024} * 1024 * 1024", py);
        Assert.Contains($"MAX_UNPACKED = {LuaModArchive.MaxUnpacked / 1024 / 1024} * 1024 * 1024", py);
        Assert.Contains($"MAX_FILE = {LuaModArchive.MaxFile / 1024 / 1024} * 1024 * 1024", py);
        var allowed = py.Split("ALLOWED = {")[1].Split('}')[0].Split(',').Select(s => s.Trim().Trim('"')).Order();
        Assert.Equal(LuaModArchive.Allowed.Order(), allowed);
    }
}

/// <summary>On Kestrel, where the 30 MB default for a request body is real (R-053).</summary>
public sealed class LuaModUploadKestrelTests(KestrelPortalFactory f) : IClassFixture<KestrelPortalFactory>
{
    [Fact]
    public async Task A_mod_above_the_default_body_limit_goes_through()
    {
        var token = DeviceSecrets.NewToken();
        var id = await f.ScopedAsync(async sp =>
        {
            var users = sp.GetRequiredService<UserManager<PortalUser>>();
            var email = $"lua-{Guid.NewGuid():N}@x.test";
            var u = new PortalUser { UserName = email, Email = email, EmailConfirmed = true, DisplayName = email[..12] };
            Assert.True((await users.CreateAsync(u, "Long-enough-passw0rd!")).Succeeded);
            return u.Id;
        });
        await f.DbAsync(async db =>
        {
            db.DeviceTokens.Add(new DeviceToken { UserId = id, TokenHash = DeviceSecrets.Hash(token), Name = "test", CreatedAt = f.Clock.GetUtcNow() });
            return await db.SaveChangesAsync();
        });
        using var ms = new MemoryStream();
        using (var zip = new ZipArchive(ms, ZipArchiveMode.Create, leaveOpen: true))
        {
            using (var w = new StreamWriter(zip.CreateEntry("metadata.yml").Open())) w.Write("id: bigmod\nversion: 1\nmaster: xpiratez\nluaApi: 1\n");
            // not compressed and random, so the archive stays as large as what is in it
            var noise = new byte[32 * 1024 * 1024];
            new Random(1).NextBytes(noise);
            using var s = zip.CreateEntry("big.wav", CompressionLevel.NoCompression).Open();
            s.Write(noise);
        }
        var c = f.CreateClient();
        c.DefaultRequestHeaders.Add("X-Device-Token", token);
        var form = new MultipartFormDataContent
        {
            { new StringContent(JsonSerializer.Serialize(new { id = "bigmod", version = "1", description = "big", license = "MIT", rightsConfirmed = true }), Encoding.UTF8, "application/json"), "meta" },
            { new ByteArrayContent(ms.ToArray()), "file", "mod.zip" },
        };
        var r = await c.PostAsync("/api/v1/lua-mods", form);
        Assert.True(r.StatusCode == HttpStatusCode.Created, await r.Content.ReadAsStringAsync());
    }
}
