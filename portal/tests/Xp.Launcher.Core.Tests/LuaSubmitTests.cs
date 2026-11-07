using System.IO.Compression;
using System.Net;
using System.Text;
using Xp.Launcher.Core;
using Xp.Manifest;

namespace Xp.Launcher.Core.Tests;

/// <summary>
/// "Submit" on the author's machine (docs/portal/LUA_MODS.md §8.1): every file goes on the list, an error stops the sending,
/// a signal only warns, the archive holds exactly the list.
/// </summary>
public sealed class LuaSubmitTests : IDisposable
{
    readonly string _dir = Directory.CreateTempSubdirectory("xp-lua-submit-").FullName;

    public void Dispose() => Directory.Delete(_dir, recursive: true);

    void Put(string rel, string text)
    {
        var path = Path.Combine(_dir, rel);
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllText(path, text);
    }

    void GoodMod(string lua = "game.on(\"newTurnUnit\", function(unit, battle, turn, side)\n  game.log(\"turn\", turn)\nend)\n")
    {
        Put("metadata.yml", "id: mymod\nname: \"My mod\"\nversion: 1.0\nmaster: \"xpiratez\"\nluaApi: 1\n");
        Put("lua/main.lua", lua);
    }

    static string[] Codes(IEnumerable<LuaNote> notes) => notes.Select(n => n.Code).Order().ToArray();

    [Fact]
    public void A_clean_mod_can_go_and_the_list_has_every_file()
    {
        GoodMod();
        Put("README.txt", "x");
        Put("Language/en-US.yml", "en-US:\n  STR_X: x\n");
        var p = LuaSubmit.Prepare(_dir);
        Assert.Empty(p.Errors);
        Assert.Empty(p.Signals);
        Assert.True(p.CanSend);
        Assert.Equal(["Language/en-US.yml", "README.txt", "lua/main.lua", "metadata.yml"], p.Files.Select(f => f.Path));
        Assert.Equal("mymod", p.Meta.Id);
        Assert.Equal("clean", LuaSubmit.PrecheckLine(p));
    }

    [Theory]
    [InlineData("tool.exe", "file_executable")]
    [InlineData("x.dll", "file_executable")]
    [InlineData("run.ps1", "file_executable")]
    [InlineData("lua/code.luac", "lua_bytecode")]
    [InlineData("map.pck", "file_type")]
    [InlineData("con.txt", "path_name")]
    public void A_file_the_archive_may_not_hold_stops_it(string file, string code)
    {
        GoodMod();
        Put(file, "x");
        var p = LuaSubmit.Prepare(_dir);
        Assert.False(p.CanSend);
        Assert.Contains(p.Errors, e => e.Code == code && e.File == file);
    }

    [Theory]
    [InlineData("id: My Mod\nversion: 1\nmaster: x\nluaApi: 1\n", "metadata_id")]
    [InlineData("id: m\nversion: 1\nluaApi: 1\n", "metadata_master")]
    [InlineData("id: m\nmaster: x\nluaApi: 1\n", "metadata_version")]
    [InlineData("id: m\nversion: 1\nmaster: x\n", "metadata_luaapi")]
    [InlineData("id: m\nversion: 1\nmaster: x\nluaApi: 99\n", "metadata_luaapi")]
    [InlineData("id: m\nversion: 1\nmaster: x\nluaApi: 2\nluaCaps: [flight]\n", "metadata_luacaps")]
    [InlineData("id: m\nversion: 1\nmaster: x\nluaApi: 1\nluaCaps: [screens]\n", "metadata_luacaps_api")]
    [InlineData("id: m\nversion: 1\nmaster: x\nluaApi: 1\nrequiredExtendedEngine: Other\n", "metadata_engine")]
    public void Metadata_is_checked(string yml, string code)
    {
        Put("metadata.yml", yml);
        Put("lua/main.lua", "");
        Assert.Contains(LuaSubmit.Prepare(_dir).Errors, e => e.Code == code);
    }

    [Fact]
    public void No_metadata_and_no_main_are_errors()
    {
        Put("README.txt", "x");
        Assert.Contains(LuaSubmit.Prepare(_dir).Errors, e => e.Code == "metadata_missing");
        Put("metadata.yml", "id: m\nversion: 1\nmaster: x\nluaApi: 1\n");
        Assert.Contains(LuaSubmit.Prepare(_dir).Errors, e => e.Code == "lua_main_missing");
    }

    [Theory]
    [InlineData("io.open('x')", "api_escape")]
    [InlineData("require('x')", "api_escape")]
    [InlineData("local s = string.dump(print)", "api_escape")]
    [InlineData("game.nothing()", "api_unknown")]
    [InlineData("game.on(\"nope\", print)", "api_event")]
    [InlineData("game.on(\"newDay\", print)", "api_event")]
    public void Suspicious_calls_warn_but_do_not_stop(string lua, string code)
    {
        GoodMod(lua + "\n");
        var p = LuaSubmit.Prepare(_dir);
        Assert.True(p.CanSend);
        Assert.Contains(p.Signals, s => s.Code == code);
        Assert.Contains(code, LuaSubmit.PrecheckLine(p));
    }

    [Fact]
    public void The_events_of_api_2_and_the_word_economy_pass_with_api_2()
    {
        GoodMod("game.on(\"newDay\", print)\ngame.on(\"battleEnd\", print)\n");
        Put("metadata.yml", "id: m\nversion: 1\nmaster: x\nluaApi: 2\nluaCaps: [screens, economy, spawn]\n");
        var p = LuaSubmit.Prepare(_dir);
        Assert.DoesNotContain(p.Errors, e => e.Code == "metadata_luacaps");
        Assert.DoesNotContain(p.Signals, s => s.Code == "api_event");
    }

    [Fact]
    public void What_comments_and_strings_say_is_not_a_call()
    {
        GoodMod("-- io.open('x')\n--[[ require('y') ]]\nlocal s = \"os.execute('z')\"\nlocal t = [[ debug.traceback() ]]\ngame.log(s, t)\n");
        Assert.Empty(LuaSubmit.Prepare(_dir).Signals);
    }

    [Fact]
    public void Long_and_encoded_text_warns()
    {
        GoodMod("local a = \"" + new string('A', 600) + "\"\ngame.log(a)\n" + "local b = 1 -- " + new string('x', 2100) + "\n");
        var p = LuaSubmit.Prepare(_dir);
        Assert.True(p.CanSend);
        Assert.Contains("encoded_block", Codes(p.Signals));
        Assert.Contains("long_line", Codes(p.Signals));
    }

    [Fact]
    public void Lua_outside_its_folder_warns()
    {
        GoodMod();
        Put("other.lua", "");
        Assert.Contains(LuaSubmit.Prepare(_dir).Signals, s => s.Code == "lua_outside" && s.File == "other.lua");
    }

    [Fact]
    public void The_archive_holds_exactly_the_list_under_its_root()
    {
        GoodMod();
        Put("Руководство.txt", "текст");
        var p = LuaSubmit.Prepare(_dir);
        var zipPath = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N") + ".zip");
        try
        {
            Assert.True(LuaSubmit.Pack(_dir, p, zipPath));
            using (var fs = File.OpenRead(zipPath))
            using (var zip = new ZipArchive(fs))
                Assert.Equal(p.Files.Select(f => f.Path), zip.Entries.Select(e => e.FullName));
            using (var fs = File.OpenRead(zipPath))
                Assert.Empty(LuaModArchive.CheckZip(fs));
            // the same mod is the same retry; other words about it are another submission
            Assert.Equal(LuaSubmit.RetryKey("t", zipPath, "d"), LuaSubmit.RetryKey("t", zipPath, "d"));
            Assert.NotEqual(LuaSubmit.RetryKey("t", zipPath, "d"), LuaSubmit.RetryKey("t", zipPath, "e"));
            Assert.NotEqual(LuaSubmit.RetryKey("t", zipPath, "d"), LuaSubmit.RetryKey("u", zipPath, "d"));
        }
        finally { File.Delete(zipPath); }
    }

    [Fact]
    public async Task A_game_that_does_not_know_the_check_is_not_started()
    {
        GoodMod();
        var p = LuaSubmit.Prepare(_dir);
        var fake = Path.Combine(_dir, "fake.bin");
        File.WriteAllText(fake, "an old game");
        await LuaSubmit.EngineCheckAsync(fake, _dir, p, CancellationToken.None);
        Assert.Contains(p.Signals, s => s.Code == "engine_old");
        Assert.True(p.CanSend);
    }

    sealed class Stub(Func<HttpRequestMessage, Task<HttpResponseMessage>> answer) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct) => answer(request);
    }

    [Fact]
    public async Task The_client_sends_the_token_the_key_the_words_and_the_file()
    {
        GoodMod();
        var p = LuaSubmit.Prepare(_dir);
        var zipPath = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N") + ".zip");
        LuaSubmit.Pack(_dir, p, zipPath);
        string? body = null, token = null, key = null;
        var http = new HttpClient(new Stub(async r =>
        {
            body = await r.Content!.ReadAsStringAsync();
            token = r.Headers.GetValues("X-Device-Token").Single();
            key = r.Headers.GetValues("Idempotency-Key").Single();
            return new HttpResponseMessage(HttpStatusCode.Created) { Content = new StringContent("{\"number\":7,\"displayNumber\":\"XP-000007\",\"status\":\"queue\"}", Encoding.UTF8, "application/json") };
        }));
        try
        {
            var made = await new PortalClient(http, new Uri("http://site.test/")).SubmitLuaModAsync("tok", p, zipPath, "Does a thing", "MIT", "ru", null, "0.4.5", CancellationToken.None);
            Assert.Equal(("XP-000007", "queue"), (made.DisplayNumber, made.Status));
            Assert.Equal("tok", token);
            Assert.StartsWith("lua-", key);
            Assert.Contains("\"rightsConfirmed\":true", body);
            Assert.Contains("\"id\":\"mymod\"", body);
            Assert.Contains("\"license\":\"MIT\"", body);
            Assert.Contains("filename=mod.zip", body);
        }
        finally { File.Delete(zipPath); }
    }

    [Fact]
    public async Task The_site_says_what_became_of_them()
    {
        var http = new HttpClient(new Stub(_ => Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new StringContent("[{\"number\":7,\"displayNumber\":\"XP-000007\",\"mod\":\"mymod\",\"version\":\"1.0\",\"status\":\"rejected\",\"reason\":\"why\",\"createdAt\":\"2026-11-06T10:00:00+00:00\",\"updatedAt\":\"2026-11-06T11:00:00+00:00\"}]", Encoding.UTF8, "application/json"),
        })));
        var row = Assert.Single(await new PortalClient(http, new Uri("http://site.test/")).MyLuaModsAsync("tok", CancellationToken.None));
        Assert.Equal(("mymod", "rejected", "why"), (row.Mod, row.Status, row.Reason));
    }
}
