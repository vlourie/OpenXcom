namespace Xp.Launcher.Core.Tests;

/// <summary>HD split step 2: hd_core on where hd is on, in every build (docs/portal/HD_SUBMODS.md §5).</summary>
public sealed class HdCoreMigrationTests : IDisposable
{
    readonly Fixture f = new();
    public void Dispose() => f.Dispose();

    GamePaths P => new(f.Game);
    string Legacy => Path.Combine(f.Game, "user", "options.cfg");

    const string HdOn =
        "mods:\n  - active: false\n    id: xcom1\n  - active: true\n    id: piratez\n  - active: true\n    id: XPZ_EX_RU-patch\n" +
        "  - active: true\n    id: hd\n  - active: true\n    id: hd_18+\n" +
        "options:\n  battleScrollSpeed: 21\n  language: ru\n  oxceHdMode: 2\n";

    const string HdOff =
        "mods:\n  - active: true\n    id: piratez\n  - active: false\n    id: hd\n" +
        "options:\n  oxceHdMode: 0\n";

    void Install(bool core = true)
    {
        Fixture.Write(f.Game, "standard/xcom1/metadata.yml", "id: xcom1\nisMaster: true\n");
        Fixture.Write(f.Game, "user/mods/Piratez/metadata.yml", "id: piratez\nisMaster: true\nmaster: xcom1\n");
        Fixture.Write(f.Game, "user/mods/hd/metadata.yml", "id: hd\nmaster: piratez\n");
        if (core) Fixture.Write(f.Game, "user/mods/hd_core/metadata.yml", "id: hd_core\nmaster: \"*\"\n");
        Fixture.Write(f.Game, "user/options.cfg", HdOn);
    }

    /// <summary>Two builds besides the legacy file: one with HD on, one with it off.</summary>
    BuildStore Builds()
    {
        var store = new BuildStore(P, _ => false);
        var piratez = store.Ensure("piratez");
        var plain = store.Copy(piratez.Id, "Без HD");
        File.WriteAllText(store.OptionsFile(plain), HdOff);
        return store;
    }

    [Fact]
    public void Hd_core_goes_on_right_before_hd_and_nothing_else_changes()
    {
        Install();
        var r = HdCoreMigration.Run(P, _ => false);

        Assert.Equal([new HdCoreFile("user/options.cfg", HdCoreStep.Added)], r);
        Assert.Equal(HdOn.Replace("  - active: true\n    id: hd\n", "  - active: true\n    id: hd_core\n  - active: true\n    id: hd\n"),
                     File.ReadAllText(Legacy));
        var mods = OptionsCfg.Parse(File.ReadAllText(Legacy)).Mods.Select(m => m.Id);
        Assert.Equal(["xcom1", "piratez", "XPZ_EX_RU-patch", "hd_core", "hd", "hd_18+"], mods);
        Assert.Equal(HdOn, File.ReadAllText(Path.Combine(P.Backup, "hd_core", "user", "options.cfg")));
    }

    [Fact]
    public void Every_build_is_migrated_and_a_build_without_hd_is_left_alone()
    {
        Install();
        var store = Builds();
        var r = HdCoreMigration.Run(P, _ => false);

        var piratez = store.OptionsFile(store.Load().Find("piratez")!);
        var plain = store.OptionsFile(store.Load().Builds.Single(b => b.Id != "piratez"));
        Assert.Contains("id: hd_core", File.ReadAllText(piratez));
        Assert.Contains("id: hd_core", File.ReadAllText(Legacy));
        Assert.Equal(HdOff, File.ReadAllText(plain));   // HD off: hd_core is not switched on behind the player's back
        Assert.Equal(3, r.Count);
        Assert.Single(r, x => x.Step == HdCoreStep.HdOff);
    }

    [Fact]
    public void A_second_run_changes_nothing_even_after_the_player_switched_hd_core_off()
    {
        Install();
        Builds();
        HdCoreMigration.Run(P, _ => false);
        var off = File.ReadAllText(Legacy).Replace("  - active: true\n    id: hd_core\n", "  - active: false\n    id: hd_core\n");
        File.WriteAllText(Legacy, off);
        var snapshot = Directory.EnumerateFiles(f.Game, "*", SearchOption.AllDirectories).ToDictionary(p => p, File.ReadAllText);

        var r = HdCoreMigration.Run(P, _ => false);

        Assert.All(r, x => Assert.Equal(HdCoreStep.Done, x.Step));
        Assert.Equal(snapshot, Directory.EnumerateFiles(f.Game, "*", SearchOption.AllDirectories).ToDictionary(p => p, File.ReadAllText));
    }

    [Fact]
    public void Hd_core_the_engine_added_switched_off_is_switched_on_in_place()
    {
        Install();
        // the new exe started by hand before the launcher: the engine appends a new mod switched off
        File.WriteAllText(Legacy, HdOn.Replace("options:\n", "  - active: false\n    id: hd_core\noptions:\n"));
        var r = HdCoreMigration.Run(P, _ => false);

        Assert.Equal(HdCoreStep.Activated, r.Single().Step);
        Assert.Equal(HdOn.Replace("options:\n", "  - active: true\n    id: hd_core\noptions:\n"), File.ReadAllText(Legacy));
    }

    [Fact]
    public void Line_ends_of_the_file_are_kept()
    {
        Install();
        File.WriteAllText(Legacy, HdOn.Replace("\n", "\r\n"));
        HdCoreMigration.Run(P, _ => false);

        var text = File.ReadAllText(Legacy);
        Assert.Contains("  - active: true\r\n    id: hd_core\r\n  - active: true\r\n    id: hd\r\n", text);
        Assert.DoesNotContain("\n", text.Replace("\r\n", ""));
    }

    [Fact]
    public void Nothing_is_written_while_the_game_runs()
    {
        Install();
        var before = File.ReadAllText(Legacy);
        Assert.Throws<UpdateBlockedException>(() => HdCoreMigration.Run(P, _ => true));
        Assert.Equal(before, File.ReadAllText(Legacy));
        Assert.False(File.Exists(HdCoreMigration.DoneFile(P)));
    }

    [Fact]
    public void Without_hd_core_installed_nothing_happens()
    {
        Install(core: false);
        Assert.Empty(HdCoreMigration.Run(P, _ => false));
        Assert.Equal(HdOn, File.ReadAllText(Legacy));
    }

    [Fact]
    public void A_dry_run_reports_and_writes_nothing()
    {
        Install();
        var r = HdCoreMigration.Run(P, _ => true, dryRun: true);
        Assert.Equal(HdCoreStep.Added, r.Single().Step);
        Assert.Equal(HdOn, File.ReadAllText(Legacy));
        Assert.False(File.Exists(HdCoreMigration.DoneFile(P)));
    }

    [Fact]
    public void A_list_not_in_the_engine_layout_is_left_for_a_human()
    {
        Install();
        var odd = "mods:\n  - {active: true, id: hd}\noptions:\n  language: ru\n";
        File.WriteAllText(Legacy, odd);
        var r = HdCoreMigration.Run(P, _ => false);
        // the flow-style item is not even read as a mod: hd is not on as far as the parser knows
        Assert.NotEqual(HdCoreStep.Added, r.Single().Step);
        Assert.Equal(odd, File.ReadAllText(Legacy));
    }
}
