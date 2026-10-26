using Xp.Manifest;

namespace Xp.Launcher.Core.Tests;

/// <summary>What an unticked mod leaves behind: nothing of ours, and with "Remove completely" nothing at all.</summary>
public sealed class RemovalTests : IDisposable
{
    readonly Fixture f = new();
    public void Dispose() => f.Dispose();

    const string Intro = "user/mods/intro";

    /// <summary>The engine, Piratez with our art inside it, the hd mod and the intro - everything installed.</summary>
    async Task<ReleaseManifest> InstallAllAsync()
    {
        Fixture.Write(f.Stage, "openxcom_hd.exe", "engine");
        Fixture.Write(f.Stage, "common/Language/en-US.yml", "strings");
        Fixture.Write(f.Stage, "user/mods/Piratez/metadata.yml", "id: piratez\nisMaster: true\n");
        Fixture.Write(f.Stage, "user/mods/Piratez/Ruleset/a.rul", "rules");
        Fixture.Write(f.Stage, "user/mods/Piratez/hd/UI/b.png", "art in piratez");
        Fixture.Write(f.Stage, "user/mods/hd/metadata.yml", "id: hd\nmaster: \"*\"\n");
        Fixture.Write(f.Stage, "user/mods/hd/hd/UI/a.png", "art");
        Fixture.Write(f.Stage, "user/mods/intro/metadata.yml", "id: xp_intro\nmaster: \"*\"\n");
        Fixture.Write(f.Stage, "user/mods/intro/Resources/intro_01.png", "frame 1");
        Fixture.Write(f.Stage, "user/mods/intro/Resources/sub/intro_02.png", "frame 2");
        Fixture.Write(f.Stage, "user/mods/intro/Sound/voice.ogg", "voice");
        f.BuildAndPublish("r1");
        Directory.Delete(f.Game, recursive: true);

        var m = (await f.Updater.CheckAsync(f.Updater.LoadState(), default)).Manifest;
        Assert.NotNull(await Setup.CommitAsync(f.Updater, m, m.Components.Select(c => c.Id), _ => Task.FromResult(true)));
        await f.UpdateAsync();
        Assert.True(f.GameHas("user/mods/intro/Resources/sub/intro_02.png"));
        Fixture.Write(f.Game, "user/piratez/save1.sav", "my precious save");
        return m;
    }

    static ComponentInfo Of(ReleaseManifest m, string mod) => m.Components.Single(c => c.Mod == mod);

    /// <summary>Unticks the components the way the wizard does; returns the folders "Remove completely" would take.</summary>
    async Task<List<string>> UntickAsync(ReleaseManifest m, params string[] mods)
    {
        var picked = Setup.Normalize(m, m.Components.Select(c => c.Id));
        foreach (var mod in mods) picked.Remove(Of(m, mod).Id);
        var folders = new List<string>();
        Assert.NotNull(await Setup.CommitAsync(f.Updater, m, picked, removing =>
        {
            folders = Setup.OwnFolders(m, removing, picked);
            return Task.FromResult(true);
        }));
        await f.UpdateAsync();
        return folders;
    }

    bool GameDir(string rel) => Directory.Exists(Path.Combine(f.Game, rel));

    [Fact]
    public async Task An_unticked_mod_leaves_no_empty_folders()
    {
        var m = await InstallAllAsync();
        await UntickAsync(m, "xp_intro");
        Assert.False(GameDir(Intro));
        Assert.True(GameDir("user/mods"));
        Assert.True(f.GameHas("user/mods/Piratez/Ruleset/a.rul"));
        // the undo set still has the files: "undo the update" brings the intro back, folders and all
        f.Updater.RollbackLast();
        Assert.Equal("frame 2", f.ReadGame("user/mods/intro/Resources/sub/intro_02.png"));
    }

    [Fact]
    public async Task Control_without_remove_completely_the_players_files_stay()
    {
        var m = await InstallAllAsync();
        Fixture.Write(f.Game, "user/mods/intro/Sound/voice.ogg", "voice edited");
        Fixture.Write(f.Game, "user/mods/intro/Thumbs.db", "x");
        await UntickAsync(m, "xp_intro");
        Assert.Equal("voice edited", f.ReadGame("user/mods/intro/Sound/voice.ogg"));
        Assert.True(f.GameHas("user/mods/intro/Thumbs.db"));
        Assert.False(GameDir("user/mods/intro/Resources"));   // emptied by the removal: gone
        Assert.True(File.Exists(Path.Combine(f.Updater.Paths.LastBackup, "files/user/mods/intro/Resources/intro_01.png")));
    }

    [Fact]
    public async Task Remove_completely_takes_the_players_files_and_the_undo_copy()
    {
        var m = await InstallAllAsync();
        Fixture.Write(f.Game, "user/mods/intro/Sound/voice.ogg", "voice edited");
        Fixture.Write(f.Game, "user/mods/intro/Thumbs.db", "x");
        File.SetAttributes(Path.Combine(f.Game, "user/mods/intro/Thumbs.db"), FileAttributes.ReadOnly);
        var folders = await UntickAsync(m, "xp_intro");
        Assert.Equal([Intro], folders);

        Assert.Equal([Intro], f.Updater.Purge(folders));
        Assert.False(GameDir(Intro));
        Assert.False(Directory.Exists(Path.Combine(f.Updater.Paths.LastBackup, "files/user/mods/intro")));
        Assert.True(f.Updater.CanRollback);
        Assert.Equal("my precious save", f.ReadGame("user/piratez/save1.sav"));
        Assert.True(f.GameHas("user/mods/hd/hd/UI/a.png"));
        Assert.DoesNotContain(f.Updater.LoadState().Cache.Keys, k => k.StartsWith(Intro + "/"));
    }

    [Fact]
    public async Task A_folder_a_kept_component_ships_into_is_not_taken()
    {
        var m = await InstallAllAsync();
        // art.hd: its own mod hd and hd_core-like hd/ trees inside Piratez - Piratez stays ticked
        var folders = await UntickAsync(m, "hd");
        Assert.Equal(["user/mods/hd"], folders);
        f.Updater.Purge(folders);
        Assert.False(GameDir("user/mods/hd"));
        Assert.False(f.GameHas("user/mods/Piratez/hd/UI/b.png"));
        Assert.False(GameDir("user/mods/Piratez/hd"));
        Assert.True(f.GameHas("user/mods/Piratez/Ruleset/a.rul"));
    }

    [Fact]
    public async Task Purge_refuses_installed_mods_and_anything_but_a_mod_folder()
    {
        await InstallAllAsync();
        Assert.Empty(f.Updater.Purge(["user/mods/Piratez", "user/piratez", "user/mods", "user/mods/../piratez", "common", Intro + "/Resources"]));
        Assert.True(f.GameHas("user/mods/Piratez/Ruleset/a.rul"));
        Assert.True(f.GameHas("user/mods/intro/Resources/intro_01.png"));
        Assert.Equal("my precious save", f.ReadGame("user/piratez/save1.sav"));
    }

    [Fact]
    public async Task Purge_under_a_running_game_writes_nothing()
    {
        var m = await InstallAllAsync();
        var folders = await UntickAsync(m, "xp_intro");
        Fixture.Write(f.Game, "user/mods/intro/Thumbs.db", "x");
        f.Updater.IsGameRunning = _ => true;
        Assert.Throws<UpdateBlockedException>(() => f.Updater.Purge(folders));
        Assert.True(f.GameHas("user/mods/intro/Thumbs.db"));
    }
}
