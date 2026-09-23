using System.Text;
using System.Text.Json;
using Xp.Manifest;

namespace Xp.Launcher.Core.Tests;

/// <summary>The launcher/updater scenarios of the spec, section 15.</summary>
public sealed class UpdaterTests : IDisposable
{
    readonly Fixture f = new();
    public void Dispose() => f.Dispose();

    [Fact]
    public async Task Clean_install_puts_every_file_and_keeps_player_data()
    {
        f.StageV1();
        f.BuildAndPublish("v1");
        await f.UpdateAsync();

        Assert.Equal("engine v1", f.ReadGame("openxcom_hd.exe"));
        Assert.Equal("strings v1", f.ReadGame("common/Language/en-US.yml"));
        Assert.Equal("desert 0 v1", f.ReadGame("user/mods/hd/hd/TERRAIN/DESERT.PCK/1.png"));
        Assert.Equal("original engine", f.ReadGame("OpenXcomEx.exe"));   // not managed: untouched
        f.AssertPlayerDataIntact();
        // identical files are stored and downloaded once
        Assert.Single(f.Server.Requests, r => r.Key.EndsWith(Hashing.Sha256Hex(Encoding.UTF8.GetBytes("desert 0 v1"))));
    }

    [Fact]
    public async Task Missing_file_is_restored_by_quick_check()
    {
        f.StageV1(); f.BuildAndPublish("v1");
        await f.UpdateAsync();
        File.Delete(Path.Combine(f.Game, "user/mods/hd/metadata.yml"));

        var plan = await f.UpdateAsync();
        Assert.Equal(["user/mods/hd/metadata.yml"], plan.ToWrite.Select(c => c.File.Path));
        Assert.Equal("id: hd", f.ReadGame("user/mods/hd/metadata.yml"));
    }

    [Fact]
    public async Task Damaged_file_of_same_size_and_time_is_found_only_by_full_check()
    {
        f.StageV1(); f.BuildAndPublish("v1");
        await f.UpdateAsync();
        var p = Path.Combine(f.Game, "user/mods/hd/hd/UI/big.png");
        var time = File.GetLastWriteTimeUtc(p);
        var bytes = File.ReadAllBytes(p);
        bytes[1000] ^= 0xFF;
        File.WriteAllBytes(p, bytes);
        File.SetLastWriteTimeUtc(p, time);

        var state = f.Updater.LoadState();
        var latest = await f.Updater.CheckAsync(state, default);
        Assert.True(f.Updater.Scan(state, latest.Manifest, full: false, null, default).NothingToDo);

        var plan = f.Updater.Scan(state, latest.Manifest, full: true, null, default);
        // differs from what we installed: shown to the player, never replaced silently
        Assert.Equal(["user/mods/hd/hd/UI/big.png"], plan.PlayerModified.Select(c => c.File.Path));

        await f.UpdateAsync(full: true, replace: new HashSet<string> { "user/mods/hd/hd/UI/big.png" });
        Assert.Equal(Hashing.FileSha256(Path.Combine(f.Stage, "user/mods/hd/hd/UI/big.png")), Hashing.FileSha256(p));
    }

    [Fact]
    public async Task Broken_download_resumes_from_part_file()
    {
        f.StageV1(); f.BuildAndPublish("v1");
        f.Server.CutBlobsAfter = 100_000;
        await f.UpdateAsync();

        var bigSha = Hashing.FileSha256(Path.Combine(f.Stage, "user/mods/hd/hd/UI/big.png"));
        Assert.Contains(f.Server.Requests, r => r.Key.EndsWith(bigSha) && r.From == 100_000);
        Assert.Equal(bigSha, Hashing.FileSha256(Path.Combine(f.Game, "user/mods/hd/hd/UI/big.png")));
    }

    [Fact]
    public async Task Server_ignoring_range_restarts_instead_of_appending()
    {
        f.StageV1(); f.BuildAndPublish("v1");
        f.Server.CutBlobsAfter = 100_000;
        f.Server.IgnoreRange = true;
        await f.UpdateAsync();
        Assert.Equal(Hashing.FileSha256(Path.Combine(f.Stage, "user/mods/hd/hd/UI/big.png")),
                     Hashing.FileSha256(Path.Combine(f.Game, "user/mods/hd/hd/UI/big.png")));
    }

    [Fact]
    public async Task Not_enough_disk_space_stops_before_writing()
    {
        f.StageV1(); f.BuildAndPublish("v1");
        f.Updater.FreeSpace = _ => 1000;
        var before = f.Snapshot();
        await Assert.ThrowsAsync<UpdateBlockedException>(() => f.UpdateAsync());
        Assert.Equal(before, f.Snapshot());
    }

    [Fact]
    public async Task Running_game_blocks_install()
    {
        f.StageV1(); f.BuildAndPublish("v1");
        f.Updater.IsGameRunning = _ => true;
        var before = f.Snapshot();
        await Assert.ThrowsAsync<UpdateBlockedException>(() => f.UpdateAsync());
        Assert.Equal(before, f.Snapshot());
    }

    [Fact]
    public async Task Manifest_signed_by_unknown_key_is_refused()
    {
        f.StageV1();
        var (otherKey, _) = Signing.CreateKeyPair();
        f.Repo.Build(new Xp.ReleaseBuilder.BuildOptions { StageDir = f.Stage, Id = "v1", Version = "1", Launch = "openxcom_hd.exe" }, otherKey);
        f.Repo.Publish("stable", "v1", otherKey);
        await Assert.ThrowsAsync<TrustException>(() => f.UpdateAsync());
    }

    [Fact]
    public async Task Manifest_changed_after_signing_is_refused()
    {
        f.StageV1(); f.BuildAndPublish("v1");
        var key = BlobKeys.Manifest("v1");
        var bytes = File.ReadAllBytes(Path.Combine(f.RepoDir, key));
        f.Server.Overrides[key] = Encoding.UTF8.GetBytes(Encoding.UTF8.GetString(bytes).Replace("engine", "enginE"));
        await Assert.ThrowsAsync<TrustException>(() => f.UpdateAsync());
    }

    [Fact]
    public async Task File_with_wrong_hash_is_discarded_and_not_installed()
    {
        f.StageV1(); f.BuildAndPublish("v1");
        var sha = Hashing.FileSha256(Path.Combine(f.Stage, "openxcom_hd.exe"));
        f.Server.Overrides[BlobKeys.For(sha)] = Encoding.UTF8.GetBytes("engine vX");      // same size, other bytes
        var before = f.Snapshot();
        await Assert.ThrowsAsync<TrustException>(() => f.UpdateAsync());
        Assert.Equal(before, f.Snapshot());
        Assert.False(File.Exists(Path.Combine(f.Game, "launcher/staging", sha + ".part")));
    }

    [Theory]
    [InlineData("../escape.txt")]
    [InlineData("user/mods/hd/../../../escape.txt")]
    [InlineData("C:/Windows/evil.dll")]
    [InlineData("//server/share/evil.dll")]
    [InlineData("user/mods/hd\\..\\..\\evil.dll")]
    [InlineData("user/mods/hd/CON.png")]
    [InlineData("user/mods/hd/x./y.png")]
    public async Task Path_traversal_in_a_signed_manifest_is_refused(string evil)
    {
        await ServeHandMadeRelease(m => m.Files.Add(new ManifestFile { Path = evil, Size = 1, Sha256 = new string('a', 64), Component = "engine" }));
        await Assert.ThrowsAsync<TrustException>(() => f.UpdateAsync());
        Assert.False(File.Exists(Path.Combine(f.Root, "escape.txt")));
    }

    [Theory]
    [InlineData("user/piratez/save1.sav", "user/piratez/")]
    [InlineData("user/options.cfg", "user/options.cfg")]
    [InlineData("launcher/state.json", "launcher/")]
    [InlineData("user/mods/Piratez/metadata.yml", "user/")]
    public async Task Player_data_is_off_limits_even_for_a_signed_manifest(string path, string root)
    {
        await ServeHandMadeRelease(m => { m.Roots.Add(root); m.Files.Add(new ManifestFile { Path = path, Size = 1, Sha256 = new string('a', 64), Component = "engine" }); });
        await Assert.ThrowsAsync<ManifestException>(() => f.UpdateAsync());
        f.AssertPlayerDataIntact();
    }

    [Fact]
    public async Task Crash_in_the_middle_of_install_is_undone_on_next_start()
    {
        f.StageV1(); f.BuildAndPublish("v1");
        await f.UpdateAsync();
        f.StageV2(); f.BuildAndPublish("v2");
        var before = f.Snapshot();

        var state = f.Updater.LoadState();
        var latest = await f.Updater.CheckAsync(state, default);
        var plan = f.Updater.Scan(state, latest.Manifest, false, null, default);
        await f.Updater.DownloadAsync(plan, null, default);
        using var cts = new CancellationTokenSource();
        int written = 0;
        var progress = new SyncProgress(p => { if (p.Phase == Phase.Installing && ++written == 1) cts.Cancel(); });
        Assert.ThrowsAny<OperationCanceledException>(() => f.Updater.Install(state, plan, progress, cts.Token));
        Assert.NotEqual(before, f.Snapshot());   // really half-installed

        Assert.True(f.Updater.Recover());
        Assert.Equal(before, f.Snapshot());
        Assert.Equal("v1", f.Updater.LoadState().InstalledReleaseId);
        await f.UpdateAsync();                     // and the next attempt finishes
        Assert.Equal("engine v2", f.ReadGame("openxcom_hd.exe"));
    }

    [Fact]
    public async Task Update_removes_dropped_files_but_not_the_players_own()
    {
        f.StageV1(); f.BuildAndPublish("v1");
        await f.UpdateAsync();
        Fixture.Write(f.Game, "user/mods/hd/hd/UI/my_own.png", "made by the player");
        f.StageV2(); f.BuildAndPublish("v2");
        await f.UpdateAsync();

        Assert.False(f.GameHas("user/mods/hd/hd/UI/old.png"));
        Assert.Equal("new in v2", f.ReadGame("user/mods/hd/hd/UI/new.png"));
        Assert.Equal("made by the player", f.ReadGame("user/mods/hd/hd/UI/my_own.png"));
        f.AssertPlayerDataIntact();
    }

    [Fact]
    public async Task Rollback_restores_the_previous_release_exactly()
    {
        f.StageV1(); f.BuildAndPublish("v1");
        await f.UpdateAsync();
        var v1 = f.Snapshot();
        f.StageV2(); f.BuildAndPublish("v2");
        await f.UpdateAsync();
        Assert.NotEqual(v1, f.Snapshot());

        f.Updater.RollbackLast();
        Assert.Equal(v1, f.Snapshot());
        var state = f.Updater.LoadState();
        Assert.Equal("v1", state.InstalledReleaseId);
        Assert.Equal(2, state.LastSequence["stable"]);   // replay protection survives the rollback
        Assert.False(f.Updater.CanRollback);
    }

    [Fact]
    public async Task Player_modified_file_is_kept_when_the_player_says_so()
    {
        f.StageV1(); f.BuildAndPublish("v1");
        await f.UpdateAsync();
        Fixture.Write(f.Game, "user/mods/hd/hd/TERRAIN/DESERT.PCK/0.png", "repainted by the player");
        f.StageV2(); f.BuildAndPublish("v2");

        var plan = await f.UpdateAsync(replace: new HashSet<string>());
        Assert.Contains(plan.Checks, c => c.State == FileState.Kept);
        Assert.Equal("repainted by the player", f.ReadGame("user/mods/hd/hd/TERRAIN/DESERT.PCK/0.png"));
        Assert.Equal("engine v2", f.ReadGame("openxcom_hd.exe"));
        Assert.True((await f.UpdateAsync()).NothingToDo);    // not asked again for the same release
    }

    [Fact]
    public async Task Kept_file_is_offered_again_by_full_check()
    {
        f.StageV1(); f.BuildAndPublish("v1");
        await f.UpdateAsync();
        Fixture.Write(f.Game, "user/mods/hd/hd/UI/big.png", "damaged");
        await f.UpdateAsync(replace: new HashSet<string>());          // kept on a plain update
        Assert.Equal("damaged", f.ReadGame("user/mods/hd/hd/UI/big.png"));

        var state = f.Updater.LoadState();
        var latest = await f.Updater.CheckAsync(state, default);
        Assert.True(f.Updater.Scan(state, latest.Manifest, full: false, null, default).NothingToDo);
        Assert.Single(f.Updater.Scan(state, latest.Manifest, full: true, null, default).PlayerModified);
    }

    [Fact]
    public async Task Replayed_old_channel_pointer_is_refused()
    {
        f.StageV1(); f.BuildAndPublish("v1");
        var oldPointer = File.ReadAllBytes(Path.Combine(f.RepoDir, BlobKeys.Channel("stable")));
        var oldSig = File.ReadAllBytes(Path.Combine(f.RepoDir, BlobKeys.Sig(BlobKeys.Channel("stable"))));
        f.StageV2(); f.BuildAndPublish("v2");
        await f.UpdateAsync();

        f.Server.Overrides[BlobKeys.Channel("stable")] = oldPointer;
        f.Server.Overrides[BlobKeys.Sig(BlobKeys.Channel("stable"))] = oldSig;
        var e = await Assert.ThrowsAsync<TrustException>(() => f.UpdateAsync());
        Assert.Contains("replayed", e.Message);
    }

    [Fact]
    public async Task Revoked_release_sends_the_channel_back_to_the_previous_one()
    {
        f.StageV1(); f.BuildAndPublish("v1");
        f.StageV2(); f.BuildAndPublish("v2");
        await f.UpdateAsync();
        Assert.Equal("engine v2", f.ReadGame("openxcom_hd.exe"));

        var pointer = f.Repo.Revoke("stable", "v2", f.Key);
        Assert.Equal("v1", pointer!.ReleaseId);
        Assert.Equal(3, pointer.Sequence);
        await f.UpdateAsync();
        Assert.Equal("engine v1", f.ReadGame("openxcom_hd.exe"));
        Assert.Equal("to be dropped in v2", f.ReadGame("user/mods/hd/hd/UI/old.png"));
        Assert.False(f.GameHas("user/mods/hd/hd/UI/new.png"));
    }

    [Fact]
    public async Task Switching_channel_installs_that_channel_and_drops_what_it_lacks()
    {
        f.StageV1(); f.BuildAndPublish("s1", "stable");
        Fixture.Write(f.Stage, "user/mods/hd/hd/UI/test_only.png", "experimental");
        f.BuildAndPublish("t1", "test");

        var state = f.Updater.LoadState(); state.Channel = "test"; state.Save(f.Updater.Paths);
        await f.UpdateAsync();
        Assert.True(f.GameHas("user/mods/hd/hd/UI/test_only.png"));

        state = f.Updater.LoadState(); state.Channel = "stable"; state.Save(f.Updater.Paths);
        await f.UpdateAsync();
        Assert.False(f.GameHas("user/mods/hd/hd/UI/test_only.png"));
        f.AssertPlayerDataIntact();
    }

    /// <summary>Publishes a manifest written by hand (signed with the trusted key), bypassing the builder's checks.</summary>
    async Task ServeHandMadeRelease(Action<ReleaseManifest> edit)
    {
        var m = new ReleaseManifest
        {
            Release = new ReleaseInfo { Id = "evil", Version = "1", Channel = "stable", MinLauncher = "0.0.0" },
            Roots = ["user/mods/hd/"],
            Components = [new ComponentInfo { Id = "engine", Kind = ComponentKind.Engine }],
        };
        edit(m);
        var mBytes = JsonSerializer.SerializeToUtf8Bytes(m, ManifestJson.Default.ReleaseManifest);
        var pointer = new ChannelPointer { Channel = "stable", Sequence = 1, ReleaseId = "evil", ManifestSha256 = Hashing.Sha256Hex(mBytes), ManifestSize = mBytes.Length };
        var pBytes = JsonSerializer.SerializeToUtf8Bytes(pointer, ManifestJson.Default.ChannelPointer);
        f.Server.Overrides[BlobKeys.Manifest("evil")] = mBytes;
        f.Server.Overrides[BlobKeys.Sig(BlobKeys.Manifest("evil"))] = Signing.SerializeSignature(Signing.Sign(f.Key, mBytes));
        f.Server.Overrides[BlobKeys.Channel("stable")] = pBytes;
        f.Server.Overrides[BlobKeys.Sig(BlobKeys.Channel("stable"))] = Signing.SerializeSignature(Signing.Sign(f.Key, pBytes));
        await Task.CompletedTask;
    }
}

/// <summary>IProgress that reports synchronously (Progress&lt;T&gt; posts to the thread pool).</summary>
sealed class SyncProgress(Action<Progress> action) : IProgress<Progress>
{
    public void Report(Progress value) => action(value);
}
