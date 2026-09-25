namespace Xp.Launcher.Core.Tests;

public sealed class ProfileTests : IDisposable
{
    readonly Fixture f = new();
    public void Dispose() => f.Dispose();

    string Cfg => Path.Combine(f.Game, "user", "options.cfg");

    // the shape Options::save writes: mods first, then a sorted map of scalars
    const string PlayerCfg =
        "mods:\n  - active: false\n    id: xcom1\n  - active: true\n    id: piratez\n" +
        "  - active: true\n    id: Smarter_Equip\n  - active: false\n    id: piratezCzechNames\n" +
        "options:\n  battleAutoEnd: true\n  keyBattleHdTestDump: 1089\n  language: en-US\n  oxceHdScale: 1\n  someFutureFork: \"kept: as is\"\n";

    void Install()
    {
        Fixture.Write(f.Game, "standard/xcom1/metadata.yml", "id: xcom1\nisMaster: true\n");
        Fixture.Write(f.Game, "standard/Smarter_Equip/metadata.yml", "id: Smarter_Equip\n");
        Fixture.Write(f.Game, "user/mods/Piratez/metadata.yml", "id: piratez\nisMaster: true\nmaster: xcom1\n");
        Fixture.Write(f.Game, "user/mods/XPZ RU-patch/metadata.yml", "id: XPZ_EX_RU-patch\nmaster: piratez\n");
        Fixture.Write(f.Game, "user/mods/OAK patch for RU Piratez/metadata.yml", "id: OAK-RU\nmaster: piratez\n");
        Fixture.Write(f.Game, "user/mods/Piratez Czech Names/metadata.yml", "id: piratezCzechNames\nmaster: piratez\n");
        Fixture.Write(f.Game, "user/mods/hd/metadata.yml", "id: hd\nmaster: \"*\"\n");
    }

    static ModProfile Piratez() => new()
    {
        Master = "piratez",
        Version = 1,
        Mods =
        [
            new() { Id = "OAK-RU", Off = true }, new() { Id = "XPZ_EX_RU-patch", Lang = "ru" },
            new() { Id = "piratezRusNames", Lang = "ru" }, new() { Id = "*" }, new() { Id = "hd" },
        ],
        Options =
        [
            new() { Key = "oxceHdScale", Value = "auto", NeedsMod = "hd" },
            new() { Key = "oxceHdUi", Value = "2", NeedsMod = "hd" },
            new() { Key = "battleAutoEnd", Value = "true", Mode = "fixed" },
        ],
    };

    [Fact]
    public void The_profile_orders_the_mods_and_keeps_every_line_it_does_not_own()
    {
        Install();
        Fixture.Write(f.Game, "user/options.cfg", PlayerCfg);
        var done = new Dictionary<string, int>();

        var r = ProfileWriter.Apply(f.Game, Piratez(), ProfileWriter.ScanMods(f.Game), "ru", 1440, done);
        Assert.True(r.Written);
        Assert.Equal(PlayerCfg, File.ReadAllText(Cfg + ".bak"));

        var cfg = OptionsCfg.Parse(File.ReadAllText(Cfg));
        // master first and alone; the RU patch on for ru, the old one it replaced off whatever the player had;
        // the player's mods where "*" stands; hd last; a profile mod that is not installed (piratezRusNames) is not invented
        Assert.Equal(
            [("piratez", true), ("xcom1", false), ("OAK-RU", false), ("XPZ_EX_RU-patch", true),
             ("Smarter_Equip", true), ("piratezCzechNames", false), ("hd", true)],
            cfg.Mods);
        Assert.Equal("ru", cfg.Get("language"));
        Assert.Equal("true", cfg.Get("oxceLanguageChosen"));   // chosen in the launcher: the game does not ask again
        Assert.Equal("4", cfg.Get("oxceHdScale"));   // 1440 lines of screen
        Assert.Equal("2", cfg.Get("oxceHdUi"));
        // what the profile does not name stays byte for byte, including a key of another fork
        var text = File.ReadAllText(Cfg);
        Assert.Contains("  keyBattleHdTestDump: 1089\n", text);
        Assert.Contains("  someFutureFork: \"kept: as is\"\n", text);
        Assert.DoesNotContain('﻿', text);
        Assert.Equal(1, done["piratez"]);
    }

    [Fact]
    public void Recommended_options_are_offered_once_and_fixed_ones_every_time()
    {
        Install();
        Fixture.Write(f.Game, "user/options.cfg", PlayerCfg);
        var done = new Dictionary<string, int>();
        ProfileWriter.Apply(f.Game, Piratez(), ProfileWriter.ScanMods(f.Game), "ru", 1080, done);

        // the player turns the HD interface off and the auto-end on again off; the launcher runs again
        var cfg = OptionsCfg.Parse(File.ReadAllText(Cfg));
        cfg.Set("oxceHdUi", "0");
        cfg.Set("battleAutoEnd", "false");
        File.WriteAllText(Cfg, cfg.Render());
        ProfileWriter.Apply(f.Game, Piratez(), ProfileWriter.ScanMods(f.Game), null, 1080, done);

        cfg = OptionsCfg.Parse(File.ReadAllText(Cfg));
        Assert.Equal("0", cfg.Get("oxceHdUi"));          // their choice, not ours any more
        Assert.Equal("true", cfg.Get("battleAutoEnd"));   // fixed: the mod does not work otherwise
        Assert.Equal("ru", cfg.Get("language"));          // no language given - the player's stays

        // a new profile version offers its recommendations again
        var v2 = Piratez();
        v2.Version = 2;
        ProfileWriter.Apply(f.Game, v2, ProfileWriter.ScanMods(f.Game), null, 1080, done);
        Assert.Equal("2", OptionsCfg.Parse(File.ReadAllText(Cfg)).Get("oxceHdUi"));
    }

    [Fact]
    public void An_english_game_gets_no_russian_patch_and_nothing_is_rewritten_twice()
    {
        Install();
        File.Delete(Cfg);   // a fresh installation: the engine has not run yet
        var done = new Dictionary<string, int>();
        var r = ProfileWriter.Apply(f.Game, Piratez(), ProfileWriter.ScanMods(f.Game), "en-US", null, done);
        Assert.Null(r.Backup);   // there was no file before: nothing to keep

        var cfg = OptionsCfg.Parse(File.ReadAllText(Cfg));
        Assert.Contains(("XPZ_EX_RU-patch", false), cfg.Mods);
        Assert.Contains(("OAK-RU", false), cfg.Mods);
        Assert.Null(cfg.Get("oxceHdScale"));   // no screen height: the engine's own default stays

        var again = ProfileWriter.Apply(f.Game, Piratez(), ProfileWriter.ScanMods(f.Game), "en-US", null, done);
        Assert.False(again.Written);
    }

    [Fact]
    public void A_profile_without_its_master_installed_is_refused()
    {
        Fixture.Write(f.Game, "standard/xcom1/metadata.yml", "id: xcom1\nisMaster: true\n");
        Assert.Throws<InvalidOperationException>(() =>
            ProfileWriter.Apply(f.Game, Piratez(), ProfileWriter.ScanMods(f.Game), "ru", 1080, new Dictionary<string, int>()));
    }

    [Fact]
    public void The_shipped_profiles_parse_and_name_mods_by_their_metadata_ids()
    {
        var file = Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", "..", "profiles", ProfileSet.FileName);
        var set = ProfileSet.Parse(File.ReadAllText(file));
        var pz = set.For("piratez");
        Assert.NotNull(pz);
        Assert.Contains(pz!.Mods, m => m.Id == "XPZ_EX_RU-patch" && m.Lang == "ru");
        // XPZ RU-patch 12.3 is built on OAK and replaces it: the two together fight over the same strings
        Assert.Contains(pz.Mods, m => m.Id == "OAK-RU" && m.Off && !m.OnFor("ru"));
        Assert.Contains(pz.Options, o => o.Key == ProfileWriter.ScaleKey && o.Value == "auto");
    }

    [Theory]
    [InlineData(720, 2)]
    [InlineData(1080, 3)]
    [InlineData(1440, 4)]
    [InlineData(2160, 4)]
    [InlineData(400, 1)]
    public void The_hd_scale_follows_the_screen(int height, int k) => Assert.Equal(k, ProfileWriter.ScaleFor(height));
}
