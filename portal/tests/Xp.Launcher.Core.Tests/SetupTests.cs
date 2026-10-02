using Xp.Manifest;
using Xp.ReleaseBuilder;

namespace Xp.Launcher.Core.Tests;

public sealed class SetupTests : IDisposable
{
    readonly Fixture f = new();
    public void Dispose() => f.Dispose();

    const string Profiles = """
        { "profiles": [ { "master": "piratez", "version": 1,
            "mods": [ { "id": "XPZ_EX_RU-patch", "lang": "ru" }, { "id": "*" }, { "id": "hd" } ],
            "options": [ { "key": "oxceHdUi", "value": "2", "needsMod": "hd" } ] } ] }
        """;

    /// <summary>A release as build.ps1 stages it: the engine, Piratez with two addons, our art mod, the profiles.</summary>
    void StageRelease()
    {
        Fixture.Write(f.Stage, "openxcom_hd.exe", "engine");
        Fixture.Write(f.Stage, "common/Language/en-US.yml", "strings");
        Fixture.Write(f.Stage, "standard/xcom1/metadata.yml", "id: xcom1\nisMaster: true\n");
        Fixture.Write(f.Stage, ProfileSet.FileName, Profiles);
        Fixture.Write(f.Stage, "user/mods/Piratez/metadata.yml", "id: piratez\nname: X-Piratez\nisMaster: true\nmaster: xcom1\n");
        Fixture.Write(f.Stage, "user/mods/Piratez/Ruleset/a.rul", "rules");
        Fixture.Write(f.Stage, "user/mods/XPZ RU-patch/metadata.yml", "id: XPZ_EX_RU-patch\nname: RU-patch\nmaster: piratez\n");
        Fixture.Write(f.Stage, "user/mods/XPZ RU-patch/Language/ru.yml", "ru strings");
        Fixture.Write(f.Stage, "user/mods/Piratez Czech Names/metadata.yml", "id: piratezCzechNames\nmaster: piratez\n");
        Fixture.Write(f.Stage, "user/mods/Piratez Czech Names/SoldierName/Czech.nam", "names");
        Fixture.Write(f.Stage, "user/mods/hd/metadata.yml", "id: hd\nmaster: \"*\"\n");
        Fixture.Write(f.Stage, "user/mods/hd/hd/UI/a.png", "art");
        f.BuildAndPublish("r1");
        // a fresh folder: the wizard installs into nothing
        Directory.Delete(f.Game, recursive: true);
    }

    async Task<ReleaseManifest> LatestAsync() => (await f.Updater.CheckAsync(f.Updater.LoadState(), default)).Manifest;

    static string Id(ReleaseManifest m, string mod) => m.Components.Single(c => c.Mod == mod).Id;

    [Fact]
    public async Task The_language_ticks_its_patch_and_leaves_the_rest_to_the_player()
    {
        StageRelease();
        var m = await LatestAsync();
        var profiles = await f.Updater.ProfilesAsync(m, default);
        var pz = profiles!.For("piratez");

        var ru = Setup.Defaults(m, pz, "ru");
        Assert.Contains(Id(m, "piratez"), ru);
        Assert.Contains(Id(m, "XPZ_EX_RU-patch"), ru);
        Assert.Contains(Id(m, "hd"), ru);
        Assert.DoesNotContain(Id(m, "piratezCzechNames"), ru);   // not in the profile: the player ticks it
        Assert.Contains(m.Components.Single(c => c.Kind == ComponentKind.Engine).Id, ru);

        var en = Setup.Defaults(m, pz, "en");
        Assert.DoesNotContain(Id(m, "XPZ_EX_RU-patch"), en);
    }

    [Fact]
    public async Task A_ticked_component_switches_on_every_mod_it_brings_its_own_last()
    {
        Fixture.Write(f.Stage, "user/mods/hd_core/metadata.yml", "id: hd_core\nmaster: \"*\"\n");
        Fixture.Write(f.Stage, "user/mods/hd_core/hd/UI/fonts/Curvy-Big.ttf", "font");
        StageRelease();
        var m = await LatestAsync();
        var hd = m.Components.Single(c => c.Mod == "hd");
        var piratez = m.Components.Single(c => c.Mod == "piratez");

        // read from the game folder: before the install the component brings nothing but its own mod
        Assert.Equal(["hd"], Setup.ModsOf(m, hd, f.Game));
        Fixture.Write(f.Game, "user/mods/hd/metadata.yml", "id: hd\nmaster: \"*\"\n");
        Fixture.Write(f.Game, "user/mods/hd_core/metadata.yml", "id: hd_core\nmaster: \"*\"\n");
        Fixture.Write(f.Game, "user/mods/Piratez/metadata.yml", "id: piratez\nisMaster: true\nmaster: xcom1\n");
        Assert.Equal(["hd_core", "hd"], Setup.ModsOf(m, hd, f.Game));   // the fonts load before the art
        Assert.Equal(["piratez"], Setup.ModsOf(m, piratez, f.Game));
    }

    [Fact]
    public async Task Without_its_master_an_addon_is_grey_and_says_what_it_needs()
    {
        StageRelease();
        var m = await LatestAsync();
        var picked = Setup.Defaults(m, null, "ru");
        picked.Add(Id(m, "XPZ_EX_RU-patch"));
        picked.Remove(Id(m, "piratez"));

        var rows = Setup.Rows(m, picked);
        var patch = rows.Single(r => r.Component.Mod == "XPZ_EX_RU-patch");
        Assert.False(patch.Checked);
        Assert.Equal("X-Piratez", patch.Needs);
        var engine = rows.Single(r => r.Component.Kind == ComponentKind.Engine);
        Assert.True(engine.Checked && engine.Locked);
        Assert.True(rows.Single(r => r.Component.Mod == "hd").Checked);   // a shared layer needs no master
    }

    [Fact]
    public void A_mod_for_another_engine_cannot_be_ticked()
    {
        var m = new ReleaseManifest
        {
            Release = new ReleaseInfo { Line = "oxce" },
            Components =
            [
                new() { Id = "engine", Kind = ComponentKind.Engine },
                new() { Id = "mod.hd", Kind = ComponentKind.Shared, Mod = "hd", Engine = "OXCE-HD", Requires = ["engine"] },
                new() { Id = "mod.x", Kind = ComponentKind.Shared, Mod = "x", Engine = "Extended", Requires = ["engine"] },
            ],
        };
        var rows = Setup.Rows(m, ["mod.hd", "mod.x"]);
        Assert.Equal("OXCE-HD", rows.Single(r => r.Component.Id == "mod.hd").WrongEngine);
        Assert.False(rows.Single(r => r.Component.Id == "mod.hd").Checked);
        Assert.True(rows.Single(r => r.Component.Id == "mod.x").Checked);   // OXCE-HD is an OXCE
    }

    [Fact]
    public async Task Only_the_ticked_components_come_and_an_unticked_one_goes_away()
    {
        StageRelease();
        var m = await LatestAsync();
        var state = f.Updater.LoadState();
        state.Components = Setup.Defaults(m, null, "en").ToList();   // no Czech names, no RU patch
        state.Save(f.Updater.Paths);
        await f.UpdateAsync();
        Assert.True(f.GameHas("user/mods/Piratez/Ruleset/a.rul"));
        Assert.False(f.GameHas("user/mods/Piratez Czech Names/SoldierName/Czech.nam"));
        Assert.False(f.GameHas("user/mods/XPZ RU-patch/Language/ru.yml"));

        // the player ticks the Czech names, then gives up on the HD art
        state = f.Updater.LoadState();
        state.Components = [.. state.Components!, Id(m, "piratezCzechNames")];
        state.Components.Remove(Id(m, "hd"));
        state.Save(f.Updater.Paths);
        var plan = await f.UpdateAsync();
        Assert.True(f.GameHas("user/mods/Piratez Czech Names/SoldierName/Czech.nam"));
        Assert.False(f.GameHas("user/mods/hd/hd/UI/a.png"));
        Assert.Contains("user/mods/hd/hd/UI/a.png", plan.Deletes);
        Assert.DoesNotContain("user/mods/hd/hd/UI/a.png", f.Updater.LoadState().Installed.Keys);
    }

    [Fact]
    public async Task After_the_install_the_profile_sets_the_game_up_and_again_before_each_start()
    {
        StageRelease();
        var m = await LatestAsync();
        var pz = (await f.Updater.ProfilesAsync(m, default))!.For("piratez");
        var state = f.Updater.LoadState();
        state.Components = Setup.Defaults(m, pz, "ru").ToList();
        state.Save(f.Updater.Paths);
        await f.UpdateAsync();

        var r = ProfileWriter.ApplyForGame(f.Updater.Paths, Setup.Master(m, state.Components), Setup.GameLanguage("ru"), 1080);
        Assert.NotNull(r);
        Assert.True(r!.Written);
        var cfg = OptionsCfg.Parse(f.ReadGame("user/options.cfg"));
        Assert.Equal("ru", cfg.Get("language"));
        Assert.Equal("2", cfg.Get("oxceHdUi"));
        Assert.Equal([("piratez", true), ("xcom1", false), ("XPZ_EX_RU-patch", true), ("hd", true)], cfg.Mods);

        // before a start: the master is read from options.cfg, the player's language stays
        var again = ProfileWriter.ApplyForGame(f.Updater.Paths, null, null, 1080);
        Assert.NotNull(again);
        Assert.False(again!.Written);
    }

    /// <summary>Installs the Russian defaults and applies the profile, as the wizard does.</summary>
    async Task<ReleaseManifest> InstallRussianAsync()
    {
        StageRelease();
        var m = await LatestAsync();
        var pz = (await f.Updater.ProfilesAsync(m, default))!.For("piratez");
        var state = f.Updater.LoadState();
        state.Components = Setup.Defaults(m, pz, "ru").ToList();
        state.Save(f.Updater.Paths);
        await f.UpdateAsync();
        ProfileWriter.ApplyForGame(f.Updater.Paths, "piratez", "ru", 1080);
        return m;
    }

    /// <summary>What the engine does when the player switches a mod off in its Mods menu.</summary>
    void PlayerSwitches(string id, bool on)
    {
        var cfg = OptionsCfg.Parse(f.ReadGame("user/options.cfg"));
        int at = cfg.Mods.FindIndex(x => x.Id == id);
        cfg.Mods[at] = (id, on);
        Fixture.Write(f.Game, "user/options.cfg", cfg.Render());
    }

    List<(string Id, bool Active)> Mods() => OptionsCfg.Parse(f.ReadGame("user/options.cfg")).Mods;

    [Fact]
    public async Task A_mod_the_player_switched_off_in_the_game_stays_off()
    {
        await InstallRussianAsync();
        PlayerSwitches("hd", false);

        var r = ProfileWriter.ApplyForGame(f.Updater.Paths, null, null, 1080);   // before a start
        Assert.Contains(("hd", false), Mods());
        Assert.Contains(r!.Changes, c => c.Contains("kept"));
        // and on the next start too: the launcher remembers what it wrote, not what it would write
        ProfileWriter.ApplyForGame(f.Updater.Paths, null, null, 1080);
        Assert.Contains(("hd", false), Mods());
    }

    [Fact]
    public async Task Back_to_recommended_brings_the_profile_list_back()
    {
        await InstallRussianAsync();
        PlayerSwitches("hd", false);
        ProfileWriter.ApplyForGame(f.Updater.Paths, null, null, 1080);

        var r = ProfileWriter.ApplyForGame(f.Updater.Paths, null, null, 1080, resetMods: true);
        Assert.True(r!.Written);
        Assert.Contains(("hd", true), Mods());
        // from here on the list is ours again: a start keeps it as it is
        Assert.False(ProfileWriter.ApplyForGame(f.Updater.Paths, null, null, 1080)!.Written);
    }

    [Fact]
    public async Task A_mod_ticked_in_the_launcher_comes_on_even_in_the_players_list()
    {
        var m = await InstallRussianAsync();
        PlayerSwitches("hd", false);   // the list is the player's now

        var state = f.Updater.LoadState();
        state.Components = [.. state.Components!, Id(m, "piratezCzechNames")];
        state.Save(f.Updater.Paths);
        await f.UpdateAsync();
        ProfileWriter.ApplyForGame(f.Updater.Paths, "piratez", "ru", 1080, switchOn: ["piratezCzechNames"]);

        Assert.Contains(("piratezCzechNames", true), Mods());
        Assert.Contains(("hd", false), Mods());   // what the player switched off stays off
    }

    [Fact]
    public async Task A_component_removed_in_the_launcher_is_not_the_players_change()
    {
        var m = await InstallRussianAsync();
        var state = f.Updater.LoadState();
        state.Components!.Remove(Id(m, "hd"));
        state.Save(f.Updater.Paths);
        await f.UpdateAsync();
        // options.cfg still names hd on, but its files are gone: that is not a choice of the player

        ProfileWriter.ApplyForGame(f.Updater.Paths, null, null, 1080);
        // still the launcher's list: the profile order is kept up, the RU patch on
        Assert.DoesNotContain(Mods(), x => x.Id == "hd");
        Assert.Contains(("XPZ_EX_RU-patch", true), Mods());
        Assert.DoesNotContain(f.Updater.LoadState().Installed.Keys, k => k.StartsWith("user/mods/hd/"));
        var r = ProfileWriter.ApplyForGame(f.Updater.Paths, null, null, 1080);
        Assert.DoesNotContain(r!.Changes, c => c.Contains("kept"));
    }

    [Fact]
    public async Task The_players_own_mods_are_listed_with_what_the_engine_will_make_of_them()
    {
        var m = await InstallRussianAsync();
        Fixture.Write(f.Game, "user/mods/MoreGuns/metadata.yml", "id: moreGuns\nname: More Guns\nversion: 1.2\nmaster: piratez\n");
        Fixture.Write(f.Game, "user/mods/VanillaTweak/metadata.yml", "id: vanillaTweak\n");   // master defaults to xcom1
        Fixture.Write(f.Game, "user/mods/Brutal/metadata.yml", "id: brutal\nmaster: \"*\"\nrequiredExtendedEngine: BrutalOXCE\n");
        PlayerAdds("moreGuns", true);

        var own = Setup.OwnMods(f.Game, m, "piratez");
        Assert.Equal(["brutal", "moreGuns", "vanillaTweak"], own.Select(o => o.Id).Order(StringComparer.Ordinal));   // ours are not listed
        var guns = own.Single(o => o.Id == "moreGuns");
        Assert.True(guns.Active);
        Assert.Null(guns.OtherMaster);
        Assert.Null(guns.WrongEngine);
        Assert.Equal("xcom1", own.Single(o => o.Id == "vanillaTweak").OtherMaster);
        Assert.Equal("BrutalOXCE", own.Single(o => o.Id == "brutal").WrongEngine);

        // before a start the profile leaves them as the player set them
        ProfileWriter.ApplyForGame(f.Updater.Paths, null, null, 1080);
        Assert.Contains(("moreGuns", true), Mods());
    }

    void PlayerAdds(string id, bool on)
    {
        var cfg = OptionsCfg.Parse(f.ReadGame("user/options.cfg"));
        cfg.Mods.Add((id, on));
        Fixture.Write(f.Game, "user/options.cfg", cfg.Render());
    }

    [Fact]
    public void A_game_without_profiles_starts_as_it_is()
    {
        Assert.Null(ProfileWriter.ApplyForGame(new GamePaths(f.Game), null, null, 1080));
    }

    // ------------------------------------------- R-183: the wizard on an installed game without a saved choice

    /// <summary>
    /// A game installed before the wizard: the whole release on disk, the 18+ art and the Czech names
    /// included, and no saved choice (state.Components null) - as on Vitali's machine on 02.10.
    /// </summary>
    async Task<(ReleaseManifest M, ModProfile? Profile)> InstalledWithoutChoiceAsync()
    {
        Fixture.Write(f.Stage, "user/mods/hd/hd_18+/UI/a.png", "adult art");
        StageRelease();
        await f.UpdateAsync();
        var m = await LatestAsync();
        Assert.Null(f.Updater.LoadState().Components);
        Assert.True(f.GameHas("user/mods/hd/hd_18+/UI/a.png"));
        Assert.True(f.GameHas("user/mods/Piratez Czech Names/SoldierName/Czech.nam"));
        return (m, (await f.Updater.ProfilesAsync(m, default))!.For("piratez"));
    }

    static string AdultId(ReleaseManifest m) => m.Components.Single(c => c.Adult).Id;

    static Func<IReadOnlyList<ComponentInfo>, Task<bool>> Answer(bool yes, List<IReadOnlyList<ComponentInfo>> asked) =>
        r => { asked.Add(r); return Task.FromResult(yes); };

    [Fact]
    public async Task On_an_installed_game_without_a_saved_choice_Next_removes_nothing()
    {
        var (m, pz) = await InstalledWithoutChoiceAsync();
        var before = f.Snapshot();

        var picked = Setup.Initial(m, f.Updater.LoadState(), pz, "ru");   // the ticks the list opens with
        Assert.Contains(AdultId(m), picked);
        Assert.Contains(Id(m, "piratezCzechNames"), picked);
        var asked = new List<IReadOnlyList<ComponentInfo>>();
        Assert.NotNull(await Setup.CommitAsync(f.Updater, m, picked, Answer(false, asked)));
        Assert.Empty(asked);   // nothing to remove: no question

        var plan = await f.UpdateAsync();
        Assert.Empty(plan.Deletes);
        Assert.Equal(before, f.Snapshot());
    }

    [Fact]
    public async Task Control_the_old_first_ticks_remove_installed_components()
    {
        // what SetupPage did before R-183: no saved choice - the defaults, and Next saved them unasked
        var (m, pz) = await InstalledWithoutChoiceAsync();
        var state = f.Updater.LoadState();
        var old = state.Components is { } mine ? Setup.Normalize(m, mine) : Setup.Defaults(m, pz, "ru");
        Assert.Equal([AdultId(m), Id(m, "piratezCzechNames")], Setup.Removing(m, state, old).Select(c => c.Id).Order());
        state.Components = [.. old];
        state.Save(f.Updater.Paths);

        var plan = await f.UpdateAsync();
        Assert.Contains("user/mods/hd/hd_18+/UI/a.png", plan.Deletes);
        Assert.False(f.GameHas("user/mods/hd/hd_18+/UI/a.png"));
        Assert.False(f.GameHas("user/mods/Piratez Czech Names/SoldierName/Czech.nam"));
    }

    [Fact]
    public async Task Unticking_an_installed_component_names_it_and_removes_it_on_yes()
    {
        var (m, pz) = await InstalledWithoutChoiceAsync();
        var picked = Setup.Initial(m, f.Updater.LoadState(), pz, "ru");
        picked.Remove(Id(m, "piratezCzechNames"));

        var asked = new List<IReadOnlyList<ComponentInfo>>();
        Assert.NotNull(await Setup.CommitAsync(f.Updater, m, picked, Answer(true, asked)));
        Assert.Equal(["Piratez Czech Names"], asked.Single().Select(Setup.Title));

        var plan = await f.UpdateAsync();
        Assert.Equal(["user/mods/Piratez Czech Names/SoldierName/Czech.nam", "user/mods/Piratez Czech Names/metadata.yml"], plan.Deletes.Order(StringComparer.Ordinal));
        Assert.False(f.GameHas("user/mods/Piratez Czech Names/SoldierName/Czech.nam"));
        Assert.True(f.GameHas("user/mods/hd/hd_18+/UI/a.png"));
    }

    [Fact]
    public async Task Cancel_keeps_the_components_and_the_saved_choice()
    {
        var (m, pz) = await InstalledWithoutChoiceAsync();
        var before = f.Snapshot();
        var picked = Setup.Initial(m, f.Updater.LoadState(), pz, "ru");
        picked.Remove(AdultId(m));

        // no saved choice yet: it stays unknown
        var asked = new List<IReadOnlyList<ComponentInfo>>();
        Assert.Null(await Setup.CommitAsync(f.Updater, m, picked, Answer(false, asked)));
        Assert.Equal([AdultId(m)], asked.Single().Select(c => c.Id));
        Assert.Null(f.Updater.LoadState().Components);
        Assert.Empty((await f.UpdateAsync()).Deletes);
        Assert.Equal(before, f.Snapshot());

        // a saved choice: it stays as saved
        var all = Setup.Initial(m, f.Updater.LoadState(), pz, "ru");
        Assert.NotNull(await Setup.CommitAsync(f.Updater, m, all, Answer(true, asked)));
        var saved = f.Updater.LoadState().Components;
        Assert.Null(await Setup.CommitAsync(f.Updater, m, picked, Answer(false, asked)));
        Assert.Equal(saved, f.Updater.LoadState().Components);
        Assert.Empty((await f.UpdateAsync()).Deletes);
        Assert.Equal(before, f.Snapshot());
    }

    [Fact]
    public async Task The_wizard_opens_again_with_the_choice_made()
    {
        var (m, pz) = await InstalledWithoutChoiceAsync();
        var picked = Setup.Initial(m, f.Updater.LoadState(), pz, "ru");
        picked.Remove(Id(m, "piratezCzechNames"));
        Assert.NotNull(await Setup.CommitAsync(f.Updater, m, picked, Answer(true, [])));
        await f.UpdateAsync();

        var again = Setup.Initial(m, f.Updater.LoadState(), pz, "ru");
        Assert.Equal(Setup.Normalize(m, picked).Order(), again.Order());
        Assert.DoesNotContain(Id(m, "piratezCzechNames"), again);
        Assert.Contains(AdultId(m), again);   // not the defaults: 18+ stays as the player left it
    }

    [Fact]
    public async Task A_game_started_during_the_question_blocks_saving_and_installing()
    {
        var (m, pz) = await InstalledWithoutChoiceAsync();
        var before = f.Snapshot();
        var stateFile = f.Updater.Paths.StateFile;
        var stateBytes = File.ReadAllBytes(stateFile);
        var picked = Setup.Initial(m, f.Updater.LoadState(), pz, "ru");
        picked.Remove(Id(m, "piratezCzechNames"));

        var running = false;
        f.Updater.IsGameRunning = _ => running;
        await Assert.ThrowsAsync<UpdateBlockedException>(() =>
            Setup.CommitAsync(f.Updater, m, picked, _ => { running = true; return Task.FromResult(true); }));

        Assert.Equal(stateBytes, File.ReadAllBytes(stateFile));   // the choice is not saved
        Assert.Null(f.Updater.LoadState().Components);
        await Assert.ThrowsAsync<UpdateBlockedException>(() => f.UpdateAsync());   // and nothing is installed
        Assert.Equal(before, f.Snapshot());

        // closed again: the same choice goes through
        running = false;
        Assert.NotNull(await Setup.CommitAsync(f.Updater, m, picked, Answer(true, [])));
        Assert.Equal(Setup.Normalize(m, picked).Order(StringComparer.Ordinal), f.Updater.LoadState().Components!);
    }
}
