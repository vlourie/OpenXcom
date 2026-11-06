using System.Text;
using Xp.Launcher.Core;
using Xp.Manifest;
using Xp.ReleaseBuilder;

namespace Xp.Launcher.Core.Tests;

/// <summary>
/// The catalog on the player's side (docs/portal/LUA_MODS.md §8.4): the mod installs only when ticked, Lua follows it
/// without the modding mode, and a revocation takes it away with a word and without touching saves.
/// </summary>
public sealed class LuaCatalogTests : IDisposable
{
    readonly Fixture f = new();
    const string Folder = "cm-good_mod";
    const string Id = "mod.good_mod";

    public void Dispose() => f.Dispose();

    void BaseStage()
    {
        Fixture.Write(f.Stage, "openxcom_hd.exe", "engine");
        Fixture.Write(f.Stage, "user/mods/Piratez/metadata.yml", "id: piratez\nisMaster: true\n");
        Fixture.Write(f.Stage, "user/mods/Piratez/Ruleset/a.rul", "rules");
    }

    void CatalogMod(string master = "piratez", string version = "1.0")
    {
        Fixture.Write(f.Stage, $"user/mods/{Folder}/metadata.yml", $"id: good_mod\nname: \"Good\"\nversion: {version}\nmaster: \"{master}\"\nluaApi: 1\n");
        Fixture.Write(f.Stage, $"user/mods/{Folder}/lua/main.lua", "game.log('hi')\n");
        Fixture.Write(f.Stage, $"user/mods/{Folder}/hd/UI/a.png", "its own art");
    }

    static RevokedMod Gone(string version = "1.0") => new()
    {
        Mod = "good_mod", Version = version, Folder = Folder,
        Reason = new() { ["ru"] = "вредит сейвам", ["en"] = "harms saves" },
    };

    void Publish(string id, params RevokedMod[] revoked)
    {
        f.Repo.Build(new BuildOptions { StageDir = f.Stage, Id = id, Version = id, Channel = "stable", Launch = "openxcom_hd.exe", Revoked = [.. revoked] }, f.Key);
        f.Repo.Publish("stable", id, f.Key);
    }

    async Task<ReleaseManifest> InstallAsync(params string[] extra)
    {
        Directory.Delete(f.Game, recursive: true);
        var m = (await f.Updater.CheckAsync(f.Updater.LoadState(), default)).Manifest;
        Assert.NotNull(await Setup.CommitAsync(f.Updater, m, Setup.Defaults(m, null, "en").Concat(extra), _ => Task.FromResult(true)));
        await f.UpdateAsync();
        return m;
    }

    BuildStore Builds(ReleaseManifest m)
    {
        var store = new BuildStore(f.Updater.Paths);
        store.Ensure(Setup.Master(m, m.Components.Select(c => c.Id)), new TestLog());
        return store;
    }

    string Cfg(BuildStore store) => store.OptionsFile(store.Load().Current!);

    [Fact]
    public async Task It_is_a_component_marked_catalog_with_its_own_hd_inside()
    {
        BaseStage();
        CatalogMod();
        f.BuildAndPublish("r1");
        var m = (await f.Updater.CheckAsync(f.Updater.LoadState(), default)).Manifest;
        var c = m.Components.Single(x => x.Id == Id);
        Assert.True(c.Catalog);
        Assert.Equal(ComponentKind.Addon, c.Kind);
        Assert.All(m.Files.Where(x => x.Path.StartsWith($"user/mods/{Folder}/")), x => Assert.Equal(Id, x.Component));
        Assert.False(m.Components.Single(x => x.Mod == "piratez").Catalog);
    }

    [Theory]
    [InlineData("cm-other", "id: good_mod\nmaster: \"piratez\"\n")]
    [InlineData("cm-good_mod", "id: good_mod\nisMaster: true\n")]
    public void A_folder_that_does_not_fit_stops_the_build(string folder, string meta)
    {
        BaseStage();
        Fixture.Write(f.Stage, $"user/mods/{folder}/metadata.yml", meta);
        Assert.Throws<InvalidOperationException>(() => f.BuildAndPublish("r1"));
    }

    [Fact]
    public void The_same_id_in_a_folder_of_ours_stops_the_build()
    {
        BaseStage();
        CatalogMod();
        Fixture.Write(f.Stage, "user/mods/good/metadata.yml", "id: good_mod\nmaster: \"piratez\"\n");
        Assert.Throws<InvalidOperationException>(() => f.BuildAndPublish("r1"));
    }

    [Theory]
    [InlineData("piratez")]
    [InlineData("*")]
    public async Task It_is_never_ticked_and_never_offered(string master)
    {
        BaseStage();
        CatalogMod(master);
        f.BuildAndPublish("r1");
        var m = await InstallAsync();
        Assert.DoesNotContain(Id, Setup.Defaults(m, null, "en"));
        Assert.False(f.GameHas($"user/mods/{Folder}/metadata.yml"));
        Assert.Empty(Setup.Unseen(m, f.Updater.LoadState(), null, "en"));
    }

    [Fact]
    public async Task Ticked_it_runs_without_the_modding_mode_and_only_while_on()
    {
        BaseStage();
        CatalogMod();
        f.BuildAndPublish("r1");
        var m = await InstallAsync(Id);
        Assert.True(f.GameHas($"user/mods/{Folder}/lua/main.lua"));
        var store = Builds(m);
        var cfg = Cfg(store);
        var build = store.Load().Current!;
        var installed = f.Updater.LoadState().Installed.Keys;

        // not switched on in this build: Lua stays off
        LuaMods.ApplyOption(f.Updater.Paths, cfg, installed);
        Assert.NotEqual("true", OptionsCfg.Parse(File.Exists(cfg) ? File.ReadAllText(cfg) : "").Get(LuaMods.Option));

        LuaMods.SetActive(store, build, "good_mod", true, _ => false);
        Assert.True(LuaMods.ApplyOption(f.Updater.Paths, cfg, installed));
        Assert.Equal("true", OptionsCfg.Parse(File.ReadAllText(cfg)).Get(LuaMods.Option));

        LuaMods.SetActive(store, build, "good_mod", false, _ => false);
        Assert.True(LuaMods.ApplyOption(f.Updater.Paths, cfg, installed));
        Assert.Equal("false", OptionsCfg.Parse(File.ReadAllText(cfg)).Get(LuaMods.Option));
    }

    [Fact]
    public async Task A_folder_merely_named_so_does_not_turn_lua_on()
    {
        BaseStage();
        f.BuildAndPublish("r1");
        var m = await InstallAsync();
        Fixture.Write(f.Game, $"user/mods/{Folder}/metadata.yml", "id: good_mod\nmaster: \"piratez\"\nluaApi: 1\n");
        var store = Builds(m);
        LuaMods.SetActive(store, store.Load().Current!, "good_mod", true, _ => false);
        LuaMods.ApplyOption(f.Updater.Paths, Cfg(store), f.Updater.LoadState().Installed.Keys);
        Assert.NotEqual("true", OptionsCfg.Parse(File.ReadAllText(Cfg(store))).Get(LuaMods.Option));
    }

    [Fact]
    public void A_local_mod_may_not_take_the_catalog_prefix()
    {
        Directory.CreateDirectory(Path.Combine(f.Game, "user", "mods"));
        Assert.Throws<LuaModNameTakenException>(() => LuaMods.Create(f.Updater.Paths, "cm-good_mod", "piratez", "en", isGameRunning: _ => false));
    }

    [Fact]
    public async Task The_author_is_warned_when_both_are_here()
    {
        BaseStage();
        CatalogMod();
        f.BuildAndPublish("r1");
        var m = await InstallAsync(Id);
        Fixture.Write(f.Game, "user/mods/good_mod/metadata.yml", "id: good_mod\nmaster: \"piratez\"\nluaApi: 1\n");
        Fixture.Write(f.Game, "user/mods/mine/metadata.yml", "id: mine\nmaster: \"piratez\"\nluaApi: 1\n");
        var list = LuaMods.List(f.Updater.Paths, Cfg(Builds(m)), "piratez", f.Updater.LoadState().Installed.Keys);
        Assert.True(list.Single(x => x.Folder == "good_mod").Twin);
        Assert.False(list.Single(x => x.Folder == "mine").Twin);
        Assert.DoesNotContain(list, x => x.Folder == Folder);
    }

    async Task<(ReleaseManifest M, BuildStore Store)> InstalledThenRevokedAsync()
    {
        BaseStage();
        CatalogMod();
        f.BuildAndPublish("r1");
        var m = await InstallAsync(Id);
        var store = Builds(m);
        LuaMods.SetActive(store, store.Load().Current!, "good_mod", true, _ => false);
        Assert.True(LuaMods.ApplyOption(f.Updater.Paths, Cfg(store), f.Updater.LoadState().Installed.Keys));
        Fixture.Write(f.Game, "user/piratez/save1.sav", "my precious save");
        Fixture.Write(f.Game, "user/mods/good_mod/metadata.yml", "id: good_mod\nmaster: \"piratez\"\nluaApi: 1\n");
        Directory.Delete(Path.Combine(f.Stage, "user", "mods", Folder), recursive: true);
        Publish("r2", Gone());
        return ((await f.Updater.CheckAsync(f.Updater.LoadState(), default)).Manifest, store);
    }

    [Fact]
    public async Task Revoked_it_goes_off_at_the_check_and_leaves_with_the_update()
    {
        var (m, store) = await InstalledThenRevokedAsync();
        Assert.Equal("good_mod", Assert.Single(m.Revoked).Mod);

        var state = f.Updater.LoadState();
        var said = LuaMods.ApplyRevoked(f.Updater, store, m, state);
        Assert.Equal("good_mod", Assert.Single(said).Mod);
        Assert.Equal("harms saves", LuaMods.ReasonOf(said[0], "en"));
        Assert.Equal("вредит сейвам", LuaMods.ReasonOf(said[0], "ru"));
        Assert.DoesNotContain(OptionsCfg.Parse(File.ReadAllText(Cfg(store))).Mods, x => x.Id == "good_mod" && x.Active);
        // the folder is still there until the update, the option falls with the next start
        Assert.True(f.GameHas($"user/mods/{Folder}/lua/main.lua"));
        Assert.True(LuaMods.ApplyOption(f.Updater.Paths, Cfg(store), f.Updater.LoadState().Installed.Keys));
        Assert.Equal("false", OptionsCfg.Parse(File.ReadAllText(Cfg(store))).Get(LuaMods.Option));

        // said once, even with the files still here
        Assert.Empty(LuaMods.ApplyRevoked(f.Updater, store, m, f.Updater.LoadState()));

        await f.UpdateAsync();
        Assert.False(Directory.Exists(Path.Combine(f.Game, "user", "mods", Folder)));   // R-482: the folder, not only the files
        Assert.True(f.GameHas("user/piratez/save1.sav"));
        Assert.True(f.GameHas("user/mods/good_mod/metadata.yml"));   // the author's own
        Assert.Empty(LuaMods.ApplyRevoked(f.Updater, store, m, f.Updater.LoadState()));
    }

    [Fact]
    public async Task A_player_without_the_mod_hears_nothing()
    {
        BaseStage();
        Publish("r1", Gone());
        var m = await InstallAsync();
        Assert.Empty(LuaMods.ApplyRevoked(f.Updater, Builds(m), m, f.Updater.LoadState()));
    }

    [Fact]
    public async Task Under_a_running_game_it_waits_for_the_next_check()
    {
        var (m, store) = await InstalledThenRevokedAsync();
        var running = f.Updater.IsGameRunning;
        f.Updater.IsGameRunning = _ => true;
        Assert.Empty(LuaMods.ApplyRevoked(f.Updater, store, m, f.Updater.LoadState()));
        Assert.Contains(OptionsCfg.Parse(File.ReadAllText(Cfg(store))).Mods, x => x.Id == "good_mod" && x.Active);
        f.Updater.IsGameRunning = _ => false;
        Assert.Single(LuaMods.ApplyRevoked(f.Updater, store, m, f.Updater.LoadState()));
        f.Updater.IsGameRunning = running;
    }

    [Fact]
    public async Task The_cut_down_release_keeps_the_list_R527()
    {
        var (m, _) = await InstalledThenRevokedAsync();
        Assert.Single(Setup.Chosen(m, [ComponentPlan.EngineId]).Revoked);
    }

    [Fact]
    public async Task Approved_again_and_revoked_again_it_is_said_again()
    {
        var (m, store) = await InstalledThenRevokedAsync();
        Assert.Single(LuaMods.ApplyRevoked(f.Updater, store, m, f.Updater.LoadState()));
        var later = new ReleaseManifest { Revoked = [Gone("2.0")] };
        Assert.Single(LuaMods.ApplyRevoked(f.Updater, store, later, f.Updater.LoadState()));
    }

    [Theory]
    [InlineData("good_mod", "cm-good_mod", null)]
    [InlineData("", "cm-good_mod", "bad revoked")]
    [InlineData("good_mod", "Piratez", "bad revoked")]
    [InlineData("good_mod", "cm-../../x", "bad revoked")]
    [InlineData("good_mod", "cm-a/b", "bad revoked")]
    public void The_validator_takes_only_a_catalog_folder(string mod, string folder, string? error)
    {
        var m = new ReleaseManifest
        {
            Release = new ReleaseInfo { Id = "r1", Version = "1", Channel = "stable" },
            Roots = ["user/"],
            Revoked = [new RevokedMod { Mod = mod, Folder = folder }],
        };
        if (error is null) ManifestValidator.Validate(m);
        else Assert.Contains(error, Assert.Throws<ManifestException>(() => ManifestValidator.Validate(m)).Message);
    }

    [Fact]
    public void A_report_says_which_lua_it_was()
    {
        Assert.Equal("m 1 [lua local]", new ModRef { Id = "m", Version = "1", Lua = true }.Line);
        Assert.Equal("m 1 [lua catalog]", new ModRef { Id = "m", Version = "1", Lua = true, Catalog = true }.Line);
        Assert.Equal("m 1", new ModRef { Id = "m", Version = "1" }.Line);
    }
}
