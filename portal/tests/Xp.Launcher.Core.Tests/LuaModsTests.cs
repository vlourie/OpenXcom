using System.Text;
using System.Text.RegularExpressions;
using Xp.Manifest;

namespace Xp.Launcher.Core.Tests;

/// <summary>The modding mode, the template and what of a local mod can leave the machine (docs/portal/LUA_MODS.md §6, §7, §11).</summary>
public sealed class LuaModsTests : IDisposable
{
    readonly Fixture f = new();
    public void Dispose() => f.Dispose();

    GamePaths Paths => f.Updater.Paths;
    static bool NoGame(string _) => false;

    string Create(string name = "Мой мод", string master = "piratez", IEnumerable<string>? reserved = null) =>
        LuaMods.Create(Paths, name, master, "ru", reserved, NoGame);

    string Mod(string folder, string rel) => Path.Combine(f.Game, "user", "mods", folder, rel);

    static Dictionary<string, string> Hashes(string dir) => Directory.EnumerateFiles(dir, "*", SearchOption.AllDirectories)
        .ToDictionary(p => Path.GetRelativePath(dir, p), p => Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(File.ReadAllBytes(p))));

    [Fact]
    public void A_new_mod_is_three_files_the_engine_reads_as_a_mod_of_this_game()
    {
        var folder = Create();
        Assert.Equal("moy_mod", folder);
        var md = ModMetadata.Parse(File.ReadAllText(Mod(folder, "metadata.yml")), folder);
        Assert.Equal(("moy_mod", "Мой мод", "0.1", "piratez", 1), (md.Id, md.Name, md.Version, md.Master, md.LuaApi));
        Assert.Contains("game.on(\"newTurnUnit\"", File.ReadAllText(Mod(folder, "lua/main.lua")));
        Assert.True(File.Exists(Mod(folder, "README.txt")));
        // Lua takes a BOM for a syntax error unless the engine strips it, and yaml-cpp is told plain UTF-8 everywhere (R-001)
        foreach (var plain in new[] { "lua/main.lua", "metadata.yml" })
            Assert.NotEqual(0xEF, File.ReadAllBytes(Mod(folder, plain))[0]);
        Assert.Equal(0xEF, File.ReadAllBytes(Mod(folder, "README.txt"))[0]);
    }

    [Theory]
    [InlineData("Мой мод!", "moy_mod")]
    [InlineData("My Cool Mod v2", "my_cool_mod_v2")]
    [InlineData("../../evil", "evil")]
    [InlineData("C:\\Windows\\system32", "c_windows_system32")]
    [InlineData("???", "lua_mod")]
    [InlineData("a_b-c", "a_b-c")]
    public void The_folder_of_a_name_is_plain_and_stays_inside(string name, string folder) => Assert.Equal(folder, LuaMods.FolderFor(name));

    [Fact]
    public void A_name_with_quotes_stays_one_yaml_value()
    {
        var folder = Create("The \"best\" \\ mod\nsecond: line");
        var md = ModMetadata.Parse(File.ReadAllText(Mod(folder, "metadata.yml")), folder);
        Assert.Equal(1, md.LuaApi);
        Assert.DoesNotContain("\nsecond", File.ReadAllText(Mod(folder, "metadata.yml")));
    }

    [Fact]
    public void An_existing_folder_is_not_touched()
    {
        Fixture.Write(f.Game, "user/mods/moy_mod/lua/main.lua", "-- my precious code");
        var e = Assert.Throws<LuaModNameTakenException>(() => Create());
        Assert.Equal("moy_mod", e.Folder);
        Assert.Equal("-- my precious code", File.ReadAllText(Mod("moy_mod", "lua/main.lua")));
        Assert.False(File.Exists(Mod("moy_mod", "metadata.yml")));
    }

    [Theory]
    [InlineData("con")]
    [InlineData("Piratez")]
    public void A_reserved_or_taken_name_is_refused(string name)
    {
        var before = Directory.GetDirectories(Path.Combine(f.Game, "user", "mods")).Length;
        Assert.Throws<LuaModNameTakenException>(() => Create(name));
        Assert.Equal(before, Directory.GetDirectories(Path.Combine(f.Game, "user", "mods")).Length);
    }

    [Fact]
    public void A_name_the_release_would_bring_or_an_id_in_another_folder_is_refused()
    {
        Assert.Throws<LuaModNameTakenException>(() => Create("art_hd", reserved: ["art_hd"]));
        Assert.False(Directory.Exists(Mod("art_hd", "")));
        Fixture.Write(f.Game, "user/mods/Other Folder/metadata.yml", "id: wanted\nmaster: piratez\n");
        Assert.Throws<LuaModNameTakenException>(() => Create("wanted"));
    }

    [Fact]
    public void Nothing_is_made_or_switched_under_a_running_game()
    {
        Assert.Throws<UpdateBlockedException>(() => LuaMods.Create(Paths, "x", "piratez", "ru", null, _ => true));
        Assert.False(Directory.Exists(Mod("x", "")));
        var store = new BuildStore(Paths, NoGame);
        var build = store.Ensure();
        var cfg = File.Exists(store.OptionsFile(build)) ? File.ReadAllText(store.OptionsFile(build)) : "";
        Assert.Throws<UpdateBlockedException>(() => LuaMods.SetActive(store, build, "x", true, _ => true));
        Assert.Equal(cfg, File.Exists(store.OptionsFile(build)) ? File.ReadAllText(store.OptionsFile(build)) : "");
    }

    [Fact]
    public void The_mode_is_of_one_installation_and_the_option_follows_it_before_a_start()
    {
        var cfg = Path.Combine(f.Game, "user", "options.cfg");
        var other = new GamePaths(Path.Combine(f.Root, "another"));
        Directory.CreateDirectory(other.StateDir);
        const string text = "mods:\n  - active: true\n    id: piratez\noptions:\n  language: ru\n";
        File.WriteAllBytes(cfg, new UTF8Encoding(false).GetBytes(text));

        // never turned on: not a byte of a player's options.cfg changes
        Assert.False(LuaMods.ApplyOption(Paths, cfg));
        Assert.Equal(text, File.ReadAllText(cfg));

        Directory.CreateDirectory(Paths.StateDir);
        LuaMods.SetMode(Paths, true);
        Assert.True(LuaMods.ModeOn(Paths));
        Assert.False(LuaMods.ModeOn(other));
        Assert.True(LuaMods.ApplyOption(Paths, cfg));
        Assert.Equal("true", OptionsCfg.Parse(File.ReadAllText(cfg)).Get(LuaMods.Option));
        Assert.Equal("ru", OptionsCfg.Parse(File.ReadAllText(cfg)).Get("language"));
        Assert.False(File.ReadAllBytes(cfg)[0] == 0xEF);
        Assert.False(LuaMods.ApplyOption(Paths, cfg));

        LuaMods.SetMode(Paths, false);
        Assert.True(LuaMods.ApplyOption(Paths, cfg));
        Assert.Equal("false", OptionsCfg.Parse(File.ReadAllText(cfg)).Get(LuaMods.Option));
        Assert.True(Directory.Exists(Paths.StateDir));
    }

    [Fact]
    public void Only_mods_with_lua_that_no_release_brought_are_listed()
    {
        Fixture.Write(f.Game, "user/mods/plain/metadata.yml", "id: plain\nmaster: piratez\n");
        Fixture.Write(f.Game, "user/mods/byapi/metadata.yml", "id: byapi\nname: By API\nversion: 2\nmaster: piratez\nluaApi: 1\n");
        Fixture.Write(f.Game, "user/mods/byfolder/metadata.yml", "id: byfolder\nmaster: xcom1\n");
        Fixture.Write(f.Game, "user/mods/byfolder/lua/main.lua", "");
        Fixture.Write(f.Game, "user/mods/shipped/metadata.yml", "id: shipped\nluaApi: 1\n");
        var cfg = Path.Combine(f.Game, "user", "options.cfg");
        File.WriteAllText(cfg, "mods:\n  - active: true\n    id: byapi\n");

        var mods = LuaMods.List(Paths, cfg, "piratez", ["user/mods/shipped/metadata.yml"]);

        Assert.Equal(["byapi", "byfolder"], mods.Select(m => m.Id));
        Assert.True(mods[0].Active);
        Assert.Null(mods[0].OtherMaster);
        Assert.False(mods[1].Active);
        Assert.Equal("xcom1", mods[1].OtherMaster);
    }

    [Fact]
    public void The_setup_page_labels_a_lua_mod()
    {
        Assert.Equal(["screens", "spawn"], ModMetadata.Parse("luaApi: 2\nluaCaps: [screens, spawn]\n", "x").LuaCaps);
        Assert.Equal(["screens", "spawn"], ModMetadata.Parse("luaCaps:\n  - screens\n  - \"spawn\"\nname: m\n", "x").LuaCaps);
        Assert.Empty(ModMetadata.Parse("luaApi: 2\n", "x").LuaCaps);
        Assert.True(LuaMods.IsLua("no such dir", ModMetadata.Parse("luaApi: 1\n", "x")));
        Assert.False(LuaMods.IsLua("no such dir", ModMetadata.Parse("luaApi: nonsense\n", "x")));
        Fixture.Write(f.Game, "user/mods/x/lua/main.lua", "");
        Assert.True(LuaMods.IsLua(Mod("x", ""), ModMetadata.Parse("", "x")));
    }

    void InstallProfile()
    {
        Fixture.Write(f.Game, "standard/xcom1/metadata.yml", "id: xcom1\nisMaster: true\n");
        Fixture.Write(f.Game, "user/mods/Piratez/metadata.yml", "id: piratez\nisMaster: true\nmaster: xcom1\n");
        Fixture.Write(f.Game, "user/mods/hd/metadata.yml", "id: hd\nmaster: \"*\"\n");
        Fixture.Write(f.Game, "xp-profiles.json", """{"profiles":[{"master":"piratez","version":1,"mods":[{"id":"*"},{"id":"hd"}],"options":[]}]}""");
    }

    [Fact]
    public void Switching_a_mod_keeps_the_list_the_launchers_and_reset_keeps_the_folder()
    {
        InstallProfile();
        Fixture.Write(f.Game, "user/options.cfg", "mods:\n  - active: true\n    id: piratez\n  - active: true\n    id: hd\n");
        var store = new BuildStore(Paths, NoGame);
        var build = store.Ensure();
        ProfileWriter.ApplyForGame(Paths, null, null, 1080, build: build, isGameRunning: NoGame);
        var state = new ProfileState(Paths);
        Assert.True(state.LoadMods().ContainsKey(build.Id.ToLowerInvariant()));

        var folder = Create();
        var code = Hashes(Mod(folder, ""));
        LuaMods.SetActive(store, build, folder, true, NoGame);
        Assert.Contains((folder, true), OptionsCfg.Parse(File.ReadAllText(store.OptionsFile(build))).Mods);

        // not the player's list: the profile still orders it, and our mod is still on after the next "Play"
        var r = ProfileWriter.ApplyForGame(Paths, null, null, 1080, build: build, isGameRunning: NoGame)!;
        Assert.DoesNotContain(r.Items, i => i.Kind == ProfileChangeKind.ModsKept);
        Assert.Contains((folder, true), OptionsCfg.Parse(File.ReadAllText(store.OptionsFile(build))).Mods);

        LuaMods.SetActive(store, build, folder, false, NoGame);
        r = ProfileWriter.ApplyForGame(Paths, null, null, 1080, build: build, isGameRunning: NoGame)!;
        Assert.DoesNotContain(r.Items, i => i.Kind == ProfileChangeKind.ModsKept);
        Assert.Contains((folder, false), OptionsCfg.Parse(File.ReadAllText(store.OptionsFile(build))).Mods);

        // "back to recommended" rewrites the list, the folder is not its business
        LuaMods.SetActive(store, build, folder, true, NoGame);
        ProfileWriter.ApplyForGame(Paths, null, null, 1080, resetMods: true, build: build, isGameRunning: NoGame);
        Assert.Equal(code, Hashes(Mod(folder, "")));
    }

    [Fact]
    public async Task An_update_a_repair_and_a_rollback_leave_a_local_mod_as_it_was_to_the_byte()
    {
        f.StageV1();
        f.BuildAndPublish("v1");
        await f.UpdateAsync();
        var folder = Create();
        Fixture.Write(f.Game, $"user/mods/{folder}/lua/extra.bin", [0, 1, 2, 3, 255]);
        var before = Hashes(Mod(folder, ""));

        f.StageV2();
        f.BuildAndPublish("v2");
        await f.UpdateAsync();
        Assert.Equal(before, Hashes(Mod(folder, "")));

        await f.UpdateAsync(full: true);
        Assert.Equal(before, Hashes(Mod(folder, "")));

        Assert.True(f.Updater.CanRollback);
        f.Updater.RollbackLast();
        Assert.Equal(before, Hashes(Mod(folder, "")));
    }

    [Fact]
    public async Task Delete_takes_the_whole_folder_of_a_local_mod_and_refuses_a_folder_of_the_release()
    {
        f.StageV1();
        f.BuildAndPublish("v1");
        await f.UpdateAsync();
        var folder = Create();
        Fixture.Write(f.Game, $"user/mods/{folder}/lua/sub/deep.lua", "x");

        Assert.Equal([$"user/mods/{folder}"], f.Updater.Purge([$"user/mods/{folder}"]));
        Assert.False(Directory.Exists(Mod(folder, "")));

        Assert.Empty(f.Updater.Purge(["user/mods/hd"]));
        Assert.True(f.GameHas("user/mods/hd/metadata.yml"));
    }

    /// <summary>For tools/lua_stage2/stage2.py: the stand runs in the game the very files the launcher writes.</summary>
    [Fact]
    public void The_template_for_the_stand()
    {
        if (Environment.GetEnvironmentVariable("OXCE_LUA_TEMPLATE_GAME") is not { Length: > 0 } game) return;
        LuaMods.Create(new GamePaths(game), "Мой мод", Environment.GetEnvironmentVariable("OXCE_LUA_TEMPLATE_MASTER")!, "ru", null, NoGame);
    }

    [Fact]
    public void The_documentation_names_all_of_the_engines_api_in_both_languages()
    {
        var repo = RepoRoot();
        if (repo is null) return;   // off the repository there is no engine to compare with
        var host = File.ReadAllText(Path.Combine(repo, "src", "Mod", "LuaHost.cpp"));
        var ids = new List<string>();
        foreach (var (table, type) in new[] { ("UNIT", "unit"), ("ITEM", "item"), ("BATTLE", "battle"), ("SOLDIER", "soldier"), ("RULE_ARMOR", "ruleArmor"), ("RULE_ITEM", "ruleItem"), ("SKILL", "skill"),
            ("RULE_DAMAGE", "ruleDamage"), ("RULE_UNIT", "ruleUnit"), ("RULE_SOLDIER", "ruleSoldier"), ("RULE_BONUS", "ruleSoldierBonus"), ("RULE_COUNTRY", "ruleCountry"),
            ("RULE_UFO", "ruleUfo"), ("RULE_CRAFT", "ruleCraft"), ("TILE", "tile"), ("GEOSCAPE", "geoscape"), ("COUNTRY", "country"), ("UFO", "ufo"), ("CRAFT", "craft"), ("RULE_RESEARCH", "ruleResearch"), ("RULE_INVENTORY", "ruleInventory"), ("RULES", "rules"), ("NERDS", "statsForNerds"), ("UI", "ui"), ("UI_WIDGET", "uiWidget") })
        {
            var body = Regex.Match(host, $@"const luaL_Reg {table}_METHODS\[\] = \{{(.*?)\n?\}};", RegexOptions.Singleline);
            Assert.True(body.Success, table);
            ids.AddRange(Regex.Matches(body.Groups[1].Value, @"\{\s*""(\w+)""\s*,").Select(m => $"{type}.{m.Groups[1].Value}"));
        }
        var events = Regex.Match(host, @"const EventInfo EVENTS\[.*?\] = \{(.*?)\n\};", RegexOptions.Singleline);
        ids.AddRange(Regex.Matches(events.Groups[1].Value, @"^\s*\{ ""(\w+)"",", RegexOptions.Multiline).Select(m => $"event.{m.Groups[1].Value}"));
        Assert.Equal(441, ids.Count);

        var page = LuaMods.WriteDocs(Paths, "ru");
        Assert.EndsWith("lua_api.ru.html", page);
        foreach (var lang in new[] { "ru", "en" })
        {
            var html = File.ReadAllText(Path.Combine(Paths.StateDir, "docs", $"lua_api.{lang}.html"));
            var missing = ids.Where(id => !html.Contains($"id=\"{id}\"")).ToList();
            Assert.Empty(missing);
            Assert.Equal(ids.Count, Regex.Matches(html, @"<tr id=""").Count);   // and nothing the engine no longer has
        }
    }

    static string? RepoRoot()
    {
        var dir = AppContext.BaseDirectory;
        for (var i = 0; i < 12 && dir is not null; i++)
        {
            if (File.Exists(Path.Combine(dir, "CLAUDE.md")) && File.Exists(Path.Combine(dir, "src", "Mod", "LuaHost.cpp"))) return dir;
            dir = Path.GetDirectoryName(dir.TrimEnd(Path.DirectorySeparatorChar));
        }
        return null;
    }
}
