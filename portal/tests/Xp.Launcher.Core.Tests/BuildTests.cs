using System.Security.Cryptography;

namespace Xp.Launcher.Core.Tests;

/// <summary>Builds: one installation, many options.cfg (docs/portal/MULTIMOD.md §3, stage 1).</summary>
public sealed class BuildTests : IDisposable
{
    readonly Fixture f = new();
    public void Dispose() => f.Dispose();

    GamePaths P => new(f.Game);
    BuildStore Store(bool running = false) => new(P, _ => running);
    string Legacy => Path.Combine(f.Game, "user", "options.cfg");

    const string PlayerCfg =
        "mods:\n  - active: false\n    id: xcom1\n  - active: true\n    id: piratez\n  - active: true\n    id: hd\n" +
        "options:\n  battleScrollSpeed: 21\n  language: ru\n  oxceHdMode: 2\n  oxceRecommendedOptionsWereSet: true\n";

    const string Profiles =
        "{ \"schema\": 1, \"profiles\": [ { \"master\": \"piratez\", \"version\": 1,\n" +
        "  \"mods\": [ { \"id\": \"*\" }, { \"id\": \"hd\" } ],\n" +
        "  \"options\": [ { \"key\": \"oxceHdMode\", \"value\": \"2\", \"needsMod\": \"hd\" },\n" +
        "                 { \"key\": \"battleAutoEnd\", \"value\": \"true\", \"mode\": \"fixed\" } ] } ] }";

    void Install()
    {
        Fixture.Write(f.Game, "standard/xcom1/metadata.yml", "id: xcom1\nisMaster: true\n");
        Fixture.Write(f.Game, "user/mods/Piratez/metadata.yml", "id: piratez\nname: X-Piratez\nisMaster: true\nmaster: xcom1\n");
        Fixture.Write(f.Game, "user/mods/hd/metadata.yml", "id: hd\nmaster: \"*\"\n");
        Fixture.Write(f.Game, "xp-profiles.json", Profiles);
        Fixture.Write(f.Game, "user/options.cfg", PlayerCfg);
        // what the launcher before builds remembered per master
        Fixture.Write(f.Game, "launcher/profiles.json", "{\"piratez\": 1}");
        Fixture.Write(f.Game, "launcher/profile-mods.json", "{\"piratez\": \"piratez\\nhd\"}");
    }

    static string Hash(string file) => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(file)));

    /// <summary>Every file under the game folder with its hash: "nothing changed" is checked on all of them.</summary>
    Dictionary<string, string> Snapshot() =>
        Directory.EnumerateFiles(f.Game, "*", SearchOption.AllDirectories)
                 .Where(p => !p.Contains(Path.DirectorySeparatorChar + "logs" + Path.DirectorySeparatorChar))
                 .ToDictionary(p => Path.GetRelativePath(f.Game, p), Hash);

    [Fact]
    public void Migration_copies_options_cfg_byte_for_byte_and_leaves_the_old_file_and_saves()
    {
        Install();
        var save = Hash(Path.Combine(f.Game, "user", "piratez", "save1.sav"));
        var b = Store().Ensure();

        Assert.Equal("piratez", b.Id);
        Assert.Equal("X-Piratez", b.Title);
        Assert.Equal("piratez", b.EngineMaster);
        Assert.Equal("piratez", b.Template);
        Assert.Equal("user/builds/piratez/", b.Cfg);
        Assert.Equal(PlayerCfg, File.ReadAllText(Store().OptionsFile(b)));   // the same config: every setting kept
        Assert.Equal(PlayerCfg, File.ReadAllText(Legacy));                    // kept for the exe started by hand
        Assert.Equal(save, Hash(Path.Combine(f.Game, "user", "piratez", "save1.sav")));
        Assert.Equal("piratez", Store().Load().Last);
    }

    [Fact]
    public void After_migration_the_profile_does_not_change_the_settings_it_already_set()
    {
        Install();
        var b = Store().Ensure();
        // what "Play" does before the start: the same per-master memory, now the build's - nothing to change
        var r = ProfileWriter.ApplyForGame(P, null, null, 1080, build: b, isGameRunning: _ => false);
        Assert.NotNull(r);
        var cfg = OptionsCfg.Parse(File.ReadAllText(Store().OptionsFile(b)));
        Assert.Equal("21", cfg.Get("battleScrollSpeed"));
        Assert.Equal("true", cfg.Get("battleAutoEnd"));   // a fixed option is still set before every start
        Assert.Equal(PlayerCfg, File.ReadAllText(Legacy));
    }

    [Fact]
    public void Migration_happens_once_and_never_overwrites_a_build()
    {
        Install();
        var s = Store();
        var b = s.Ensure();
        File.WriteAllText(s.OptionsFile(b), "changed in the build");
        File.WriteAllText(Legacy, "changed by the exe started by hand");
        s.Ensure();
        Assert.Equal("changed in the build", File.ReadAllText(s.OptionsFile(b)));
    }

    [Fact]
    public void A_migration_cut_short_keeps_the_copy_and_a_lost_list_is_rebuilt_from_the_folders()
    {
        Install();
        // cut short: the copy is there, builds.json is not
        Fixture.Write(f.Game, "user/builds/piratez/options.cfg", PlayerCfg);
        Fixture.Write(f.Game, "user/builds/second/options.cfg", PlayerCfg.Replace("21", "7"));
        var b = Store().Ensure();
        Assert.Equal("piratez", b.Id);
        Assert.Equal(["piratez", "second"], Store().Load().Builds.Select(x => x.Id));
        Assert.All(Store().Load().Builds, x => Assert.Equal("piratez", x.EngineMaster));

        // a damaged list: a read rebuilds it in memory and writes nothing; the start repairs it - kept aside, rebuilt
        File.WriteAllText(Store().FilePath, "{ not json");
        Assert.Equal(2, Store().Load().Builds.Count);
        Assert.False(File.Exists(Store().FilePath + ".bad"));
        Assert.Equal("piratez", Store().Ensure().Id);
        Assert.True(File.Exists(Store().FilePath + ".bad"));
        Assert.Equal(["piratez", "second"], Store().Load().Builds.Select(x => x.Id));
        Assert.Equal("{ not json", File.ReadAllText(Store().FilePath + ".bad"));
    }

    [Fact]
    public void A_damaged_list_under_a_running_game_is_read_and_nothing_is_written()
    {
        Install();
        var a = Store().Ensure();
        Store().Copy(a.Id, "Second");
        File.WriteAllText(Store().FilePath, "{ not json");
        var before = Snapshot();

        var s = Store(running: true);
        // every read of the window and of headless: the list from the folders, in memory
        Assert.Equal(["piratez", "second"], s.Load().Builds.Select(x => x.Id));
        Assert.Equal(s.OptionsFile(a), s.CurrentOptionsFile());
        Assert.Equal("piratez", s.Ensure().Id);
        s.MarkPlayed(a.Id);
        // and every write is refused, as with a sound list
        Assert.Throws<UpdateBlockedException>(() => s.Create("New", "piratez", "ru", 1080));
        Assert.Throws<UpdateBlockedException>(() => s.Copy(a.Id, "Third"));
        Assert.Throws<UpdateBlockedException>(() => s.Rename(a.Id, "Renamed"));
        Assert.Throws<UpdateBlockedException>(() => s.Select("second"));
        Assert.Throws<UpdateBlockedException>(() => s.Delete("second"));
        Assert.Equal(before, Snapshot());
        Assert.False(File.Exists(s.FilePath + ".bad"));

        // the game closed: the next start repairs it
        Assert.Equal("piratez", Store().Ensure().Id);
        Assert.True(File.Exists(s.FilePath + ".bad"));
        Assert.Equal(2, Store().Load().Builds.Count);
    }

    static Exception? Refused(Action a)
    {
        var e = Record.Exception(a);
        Assert.True(e is IOException or UnauthorizedAccessException, $"expected a refusal of the file system, got {e?.GetType().Name ?? "none"}");
        return e;
    }

    [Fact]
    public void A_delete_whose_list_cannot_be_written_keeps_the_build_with_its_settings()
    {
        Install();
        var s = Store();
        var a = s.Ensure();
        var c = s.Copy(a.Id, "Second");
        var cfg = Hash(s.OptionsFile(c));
        // the list is held open by another program (an antivirus, a backup): it cannot be replaced
        using (new FileStream(s.FilePath, FileMode.Open, FileAccess.Read, FileShare.Read))
            Refused(() => s.Delete(c.Id));

        Assert.Equal(["piratez", "second"], s.Load().Builds.Select(x => x.Id));
        Assert.Equal(c.Id, s.Load().Last);
        Assert.Equal(cfg, Hash(s.OptionsFile(c)));
        Assert.False(Directory.Exists(s.DeletedDir));
        // and it is deleted once the list can be written
        s.Delete(c.Id);
        Assert.Equal(["piratez"], s.Load().Builds.Select(x => x.Id));
    }

    [Fact]
    public void A_delete_whose_folder_cannot_be_moved_puts_the_build_back()
    {
        Install();
        var s = Store();
        var a = s.Ensure();
        var c = s.Copy(a.Id, "Second");
        var cfg = Hash(s.OptionsFile(c));
        // a file of the build's folder is open: the folder cannot be moved, the list is written already
        using (new FileStream(s.OptionsFile(c), FileMode.Open, FileAccess.Read, FileShare.Read))
            Refused(() => s.Delete(c.Id));

        Assert.Equal(["piratez", "second"], s.Load().Builds.Select(x => x.Id));
        Assert.Equal(c.Id, s.Load().Last);
        Assert.Equal(cfg, Hash(s.OptionsFile(c)));
        Assert.Empty(Directory.Exists(s.DeletedDir) ? Directory.EnumerateFileSystemEntries(s.DeletedDir) : []);
    }

    [Fact]
    public void Settings_of_two_builds_are_independent()
    {
        Install();
        var s = Store();
        var a = s.Ensure();
        var c = s.Copy(a.Id, "Пиратки — копия");
        Assert.Equal("build", c.Id);   // nothing latin in the name: a neutral folder name
        Assert.Equal(File.ReadAllBytes(s.OptionsFile(a)), File.ReadAllBytes(s.OptionsFile(c)));

        // the first build is started as it is
        ProfileWriter.ApplyForGame(P, null, null, 1080, build: a, isGameRunning: _ => false);
        var before = Hash(s.OptionsFile(a));

        // the player changes a setting and a mod in the copy (the game writes its own options.cfg on exit) and starts it
        var cfg = OptionsCfg.Parse(File.ReadAllText(s.OptionsFile(c)));
        cfg.Set("battleScrollSpeed", "3");
        cfg.Mods[cfg.Mods.FindIndex(m => m.Id == "hd")] = ("hd", false);
        File.WriteAllText(s.OptionsFile(c), cfg.Render());
        ProfileWriter.ApplyForGame(P, null, null, 1080, build: c, isGameRunning: _ => false);
        // and the first again
        ProfileWriter.ApplyForGame(P, null, null, 1080, build: a, isGameRunning: _ => false);
        Assert.Equal("21", OptionsCfg.Parse(File.ReadAllText(s.OptionsFile(a))).Get("battleScrollSpeed"));
        Assert.Equal("3", OptionsCfg.Parse(File.ReadAllText(s.OptionsFile(c))).Get("battleScrollSpeed"));
        // the copy's mods list is the player's now; the original's is not touched by it
        Assert.Contains(("hd", false), OptionsCfg.Parse(File.ReadAllText(s.OptionsFile(c))).Mods);
        Assert.Contains(("hd", true), OptionsCfg.Parse(File.ReadAllText(s.OptionsFile(a))).Mods);
        Assert.Equal(before, Hash(s.OptionsFile(a)));
        Assert.Equal(PlayerCfg, File.ReadAllText(Legacy));
    }

    [Fact]
    public void A_new_build_gets_the_profile_and_none_of_the_players_keys()
    {
        Install();
        var s = Store();
        s.Ensure();
        var n = s.Create("RoSigma test", "piratez", "ru", 1440);
        Assert.Equal("rosigma-test", n.Id);
        var cfg = OptionsCfg.Parse(File.ReadAllText(s.OptionsFile(n)));
        Assert.Equal([("piratez", true), ("xcom1", false), ("hd", true)], cfg.Mods);
        Assert.Equal("2", cfg.Get("oxceHdMode"));
        Assert.Equal("ru", cfg.Get("language"));
        Assert.Null(cfg.Get("battleScrollSpeed"));                 // the player's setting of another build
        Assert.Null(cfg.Get("oxceRecommendedOptionsWereSet"));     // the engine's recommendations come on the first start
        Assert.Equal(n.Id, s.Load().Last);
        // its own memory of the profile: recommended options were offered to it, not to the first build
        Assert.True(new ProfileState(P).Load().ContainsKey(n.Id));
    }

    [Fact]
    public void A_copy_keeps_the_profile_memory_and_a_delete_keeps_the_settings_aside()
    {
        Install();
        var s = Store();
        var a = s.Ensure();
        var c = s.Copy(a.Id, "Copy");
        Assert.Equal(1, new ProfileState(P).Load()[c.Id]);
        Assert.Equal("piratez\nhd", new ProfileState(P).LoadMods()[c.Id]);

        var kept = s.Delete(c.Id);
        Assert.True(File.Exists(Path.Combine(kept, "options.cfg")));
        Assert.False(Directory.Exists(Path.Combine(f.Game, "user", "builds", c.Id)));
        Assert.StartsWith(s.DeletedDir, kept);
        Assert.Equal(a.Id, s.Load().Last);
        Assert.False(new ProfileState(P).Load().ContainsKey(c.Id));
        Assert.True(File.Exists(Path.Combine(f.Game, "user", "mods", "hd", "metadata.yml")));   // mods stay
        Assert.Throws<InvalidOperationException>(() => s.Delete(a.Id));                         // the only one
    }

    [Fact]
    public void Under_a_running_game_nothing_is_written()
    {
        Install();
        var a = Store().Ensure();
        Store().Copy(a.Id, "Second");
        Store().Select(a.Id);
        var before = Snapshot();

        var s = Store(running: true);
        Assert.Throws<UpdateBlockedException>(() => s.Create("New", "piratez", "ru", 1080));
        Assert.Throws<UpdateBlockedException>(() => s.Copy(a.Id, "Third"));
        Assert.Throws<UpdateBlockedException>(() => s.Rename(a.Id, "Renamed"));
        Assert.Throws<UpdateBlockedException>(() => s.Select("second"));
        Assert.Throws<UpdateBlockedException>(() => s.Delete("second"));
        Assert.Throws<UpdateBlockedException>(() =>
            ProfileWriter.ApplyForGame(P, null, null, 1080, build: a, isGameRunning: _ => true));
        Assert.Throws<UpdateBlockedException>(() =>
            ProfileWriter.ApplyForGame(P, null, null, 1080, resetMods: true, build: a, isGameRunning: _ => true));

        Assert.Equal(before, Snapshot());
    }

    [Fact]
    public void Under_a_running_game_the_first_start_does_not_migrate()
    {
        Install();
        var before = Snapshot();
        Assert.Throws<UpdateBlockedException>(() => Store(running: true).Ensure());
        Assert.Equal(before, Snapshot());
        Assert.False(Store().Exists);
    }

    [Fact]
    public void Launch_arguments_are_absolute_with_slashes_and_name_the_master()
    {
        Install();
        var s = Store();
        var b = s.Ensure();
        var args = s.LaunchArgs(b);
        var game = f.Game.Replace('\\', '/');
        Assert.Equal(["-user", game + "/user/", "-cfg", game + "/user/builds/piratez/", "-master", "piratez"], args);
        Assert.All(args.Where(a => a.Contains('/')), a => Assert.True(Path.IsPathRooted(a)));
    }

    [Fact]
    public void Build_folders_are_player_data_no_release_may_write()
    {
        Assert.NotNull(InstallPolicy.WhyProtected("user/builds/piratez/options.cfg"));
        Assert.NotNull(InstallPolicy.WhyRootProtected("user/builds/"));
    }

    [Fact]
    public void The_wizard_lists_own_mods_as_the_current_build_has_them()
    {
        Install();
        var s = Store();
        var b = s.Ensure();
        Fixture.Write(f.Game, "user/mods/Mine/metadata.yml", "id: mine\nmaster: piratez\n");
        var cfg = OptionsCfg.Parse(File.ReadAllText(s.OptionsFile(b)));
        cfg.Mods.Add(("mine", true));
        File.WriteAllText(s.OptionsFile(b), cfg.Render());
        Assert.Equal(s.OptionsFile(b), s.CurrentOptionsFile());
        var m = new Xp.Manifest.ReleaseManifest();
        Assert.True(Setup.OwnMods(f.Game, m, "piratez", s.CurrentOptionsFile()).Single(o => o.Id == "mine").Active);
        Assert.False(Setup.OwnMods(f.Game, m, "piratez").Single(o => o.Id == "mine").Active);   // user/options.cfg does not have it
    }
}
