using System.Collections.Concurrent;
using System.Text.Json;
using Xp.Manifest;

namespace Xp.Launcher.Core;

public enum FileState { Ok, Missing, Changed, PlayerModified, Kept }

public sealed record FileCheck(ManifestFile File, FileState State, string? CurrentSha);

public sealed class UpdatePlan
{
    public required ReleaseManifest Manifest { get; init; }
    public required List<FileCheck> Checks { get; init; }
    /// <summary>Installed files this release no longer ships and the player did not touch.</summary>
    public required List<string> Deletes { get; init; }
    public IEnumerable<FileCheck> ToWrite => Checks.Where(c => c.State is FileState.Missing or FileState.Changed);
    public IEnumerable<FileCheck> PlayerModified => Checks.Where(c => c.State == FileState.PlayerModified);
    public long DownloadBytes => ToWrite.DistinctBy(c => c.File.Sha256).Sum(c => c.File.Size);
    public bool NothingToDo => !ToWrite.Any() && Deletes.Count == 0 && !PlayerModified.Any();
}

public enum Phase { Checking, Scanning, Downloading, Installing, RollingBack, Done }

public sealed record Progress(Phase Phase, long Done, long Total, string? Current, double BytesPerSecond);

public sealed class UpdateBlockedException(string message) : Exception(message);

/// <summary>
/// Everything the launcher does to the game directory. Order of an install:
/// download to staging (hash-checked) -> journal -> move replaced files to backup -> put new files ->
/// save state -> mark committed in the journal -> backup becomes "last". A crash before the mark is
/// undone by <see cref="Recover"/>, a crash after it is finished by it.
/// </summary>
public sealed class Updater(GamePaths paths, RepoClient repo, ILauncherLog log)
{
    /// <summary>
    /// How many files are asked for at once. Over HTTP/2 these are streams of one connection, not
    /// sockets: four of them left the link three times idle (10.9 MB/s of 29.5 measured on the
    /// station), twenty-four fill it. See <see cref="RepoClient.NewHttpClient"/>.
    /// </summary>
    public const int DownloadParallelism = 24;
    const long DiskMargin = 256L * 1024 * 1024;

    public GamePaths Paths { get; } = paths;
    public Func<string, bool> IsGameRunning { get; set; } = GameProcess.IsRunningIn;
    public Func<string, long> FreeSpace { get; set; } = dir => new DriveInfo(Path.GetPathRoot(dir)!).AvailableFreeSpace;

    public LauncherState LoadState() => LauncherState.Load(Paths, log);

    // ------------------------------------------------------------------ check

    public async Task<LatestRelease> CheckAsync(LauncherState state, CancellationToken ct)
    {
        state.LastSequence.TryGetValue(state.Channel, out var seen);
        var latest = await repo.GetLatestAsync(state.Channel, seen, ct);
        InstallPolicy.Check(latest.Manifest);
        state.LastSequence[state.Channel] = latest.Pointer.Sequence;
        state.Save(Paths);
        log.Info($"channel {state.Channel}: release {latest.Manifest.Release.Id} (sequence {latest.Pointer.Sequence})");
        return latest;
    }

    /// <summary>
    /// The profiles of a release before it is installed: the wizard needs them to tick the language's
    /// addons. Fetched as the blob the manifest names, so the hash is checked like any file's.
    /// </summary>
    public async Task<ProfileSet?> ProfilesAsync(ReleaseManifest manifest, CancellationToken ct)
    {
        var f = manifest.Files.FirstOrDefault(x => x.Path.Equals(ProfileSet.FileName, StringComparison.OrdinalIgnoreCase));
        if (f is null) return null;
        Directory.CreateDirectory(Paths.Staging);
        var blob = StagedBlob(f.Sha256);
        if (!File.Exists(blob)) await repo.DownloadBlobAsync(f.Sha256, f.Size, blob, _ => { }, ct);
        return ProfileSet.Parse(await File.ReadAllTextAsync(blob, ct));
    }

    /// <summary>
    /// Compares disk with the manifest. Quick mode trusts the cache when size and time match;
    /// <paramref name="full"/> re-hashes every managed file ("check / repair").
    /// </summary>
    public UpdatePlan Scan(LauncherState state, ReleaseManifest manifest, bool full, IProgress<Progress>? progress, CancellationToken ct)
    {
        // only the ticked components: files of an unticked one we installed fall out as deletes
        manifest = Setup.Chosen(manifest, state.Components);
        var total = manifest.Files.Sum(f => f.Size);
        long done = 0;
        var results = new ConcurrentBag<FileCheck>();
        var newCache = new ConcurrentDictionary<string, CacheEntry>(StringComparer.OrdinalIgnoreCase);

        Parallel.ForEach(manifest.Files, new ParallelOptions { CancellationToken = ct, MaxDegreeOfParallelism = Math.Max(1, Environment.ProcessorCount / 2) }, f =>
        {
            var path = Paths.Full(f.Path);
            var fi = new FileInfo(path);
            FileCheck check;
            if (!fi.Exists) check = new FileCheck(f, FileState.Missing, null);
            else
            {
                string sha;
                if (!full && state.Cache.TryGetValue(f.Path, out var c) && c.Size == fi.Length && c.MtimeUtcTicks == fi.LastWriteTimeUtc.Ticks)
                    sha = c.Sha256;
                else if (fi.Length != f.Size && !state.Installed.ContainsKey(f.Path))
                    sha = "";   // different size and nothing to compare against: no need to hash
                else
                    sha = Hashing.FileSha256(path);
                if (sha.Length > 0) newCache[f.Path] = new CacheEntry { Size = fi.Length, MtimeUtcTicks = fi.LastWriteTimeUtc.Ticks, Sha256 = sha };
                check = new FileCheck(f, Classify(state, manifest, f, sha, full), sha.Length > 0 ? sha : null);
            }
            results.Add(check);
            var d = Interlocked.Add(ref done, f.Size);
            progress?.Report(new Progress(Phase.Scanning, d, total, f.Path, 0));
        });

        foreach (var kv in newCache) state.Cache[kv.Key] = kv.Value;
        var shipped = new HashSet<string>(manifest.Files.Select(f => f.Path), StringComparer.OrdinalIgnoreCase);
        var deletes = new List<string>();
        foreach (var candidate in manifest.Deletes.Concat(state.Installed.Keys).Distinct(StringComparer.OrdinalIgnoreCase))
        {
            if (shipped.Contains(candidate) || InstallPolicy.WhyProtected(candidate) is not null) continue;
            if (!SafePath.UnderAnyRoot(candidate, manifest.Roots) && !SafePath.UnderAnyRoot(candidate, state.InstalledRoots)) continue;
            var path = Paths.Full(candidate);
            if (!File.Exists(path)) continue;
            // a file is removed only if it is still exactly what we installed (or the manifest names it
            // and we have no record): the player's own files in managed folders stay
            if (state.Installed.TryGetValue(candidate, out var mine))
            {
                if (Hashing.FileSha256(path) != mine) { log.Info($"kept (changed by player): {candidate}"); continue; }
            }
            else if (!manifest.Deletes.Contains(candidate, StringComparer.OrdinalIgnoreCase)) continue;
            deletes.Add(candidate);
        }

        var plan = new UpdatePlan { Manifest = manifest, Checks = results.OrderBy(c => c.File.Path, StringComparer.Ordinal).ToList(), Deletes = deletes };
        log.Info($"scan ({(full ? "full" : "quick")}): {plan.ToWrite.Count()} to write, {plan.PlayerModified.Count()} changed by player, {deletes.Count} to remove");
        return plan;
    }

    static FileState Classify(LauncherState state, ReleaseManifest manifest, ManifestFile f, string currentSha, bool full)
    {
        if (currentSha == f.Sha256) return FileState.Ok;
        if (state.Installed.TryGetValue(f.Path, out var installed) && currentSha.Length > 0 && currentSha != installed)
        {
            // not what we put there and not what we are about to put: the player's work
            // "keep" holds for updates only: a full check always asks again, a damaged file looks the same
            if (!full && state.Kept.TryGetValue(f.Path, out var k) && k.Sha256 == currentSha && k.ReleaseId == manifest.Release.Id)
                return FileState.Kept;
            return FileState.PlayerModified;
        }
        return FileState.Changed;
    }

    /// <summary>Player's answer for modified files: replace them, or keep them until the next release.</summary>
    public UpdatePlan Resolve(LauncherState state, UpdatePlan plan, ISet<string> replace)
    {
        var checks = plan.Checks.Select(c =>
        {
            if (c.State != FileState.PlayerModified) return c;
            if (replace.Contains(c.File.Path)) return c with { State = FileState.Changed };
            state.Kept[c.File.Path] = new KeptFile { Sha256 = c.CurrentSha ?? "", ReleaseId = plan.Manifest.Release.Id };
            log.Info($"player keeps: {c.File.Path}");
            return c with { State = FileState.Kept };
        }).ToList();
        state.Save(Paths);
        return new UpdatePlan { Manifest = plan.Manifest, Checks = checks, Deletes = plan.Deletes };
    }

    // --------------------------------------------------------------- download

    public async Task DownloadAsync(UpdatePlan plan, IProgress<Progress>? progress, CancellationToken ct)
    {
        if (plan.PlayerModified.Any()) throw new InvalidOperationException("player-modified files are not resolved");
        var blobs = plan.ToWrite.Select(c => c.File).DistinctBy(f => f.Sha256).ToList();
        Directory.CreateDirectory(Paths.Staging);

        long need = blobs.Where(b => !File.Exists(StagedBlob(b.Sha256))).Sum(b => b.Size - PartLength(b.Sha256))
                    + plan.ToWrite.Sum(c => c.File.Size);
        var free = FreeSpace(Paths.GameDir);
        if (free < need + DiskMargin)
            throw new UpdateBlockedException($"not enough disk space: need {Mb(need + DiskMargin)}, free {Mb(free)}");

        long total = blobs.Sum(b => b.Size), done = 0;
        var meter = new SpeedMeter();
        foreach (var b in blobs.Where(b => File.Exists(StagedBlob(b.Sha256)))) done += b.Size;
        foreach (var b in blobs) done += Math.Min(PartLength(b.Sha256), b.Size);

        var toFetch = blobs.Where(b => !File.Exists(StagedBlob(b.Sha256))).ToList();
        if (toFetch.Count < blobs.Count) log.Info($"{blobs.Count - toFetch.Count} files already downloaded by an earlier attempt");
        await Parallel.ForEachAsync(toFetch,
            new ParallelOptions { MaxDegreeOfParallelism = DownloadParallelism, CancellationToken = ct }, async (b, token) =>
            {
                var name = plan.ToWrite.First(c => c.File.Sha256 == b.Sha256).File.Path;
                for (int attempt = 1; ; attempt++)
                {
                    try
                    {
                        await repo.DownloadBlobAsync(b.Sha256, b.Size, StagedBlob(b.Sha256), n =>
                        {
                            var d = Interlocked.Add(ref done, n);
                            meter.Add(n);
                            progress?.Report(new Progress(Phase.Downloading, d, total, name, meter.BytesPerSecond));
                        }, token);
                        return;
                    }
                    catch (Exception e) when (attempt < 4 && e is IOException or HttpRequestException && !token.IsCancellationRequested)
                    {
                        log.Info($"download retry {attempt} for {name}: {e.Message}");
                        await Task.Delay(TimeSpan.FromSeconds(1 << attempt), token);
                    }
                }
            });
        log.Info($"downloaded {toFetch.Count} files ({blobs.Count} needed, {Mb(total)})");
    }

    string StagedBlob(string sha) => Path.Combine(Paths.Staging, sha);
    long PartLength(string sha) { var p = StagedBlob(sha) + ".part"; return File.Exists(p) ? new FileInfo(p).Length : 0; }
    static string Mb(long bytes) => $"{bytes / (1024.0 * 1024):F0} MB";

    // ---------------------------------------------------------------- install

    public void Install(LauncherState state, UpdatePlan plan, IProgress<Progress>? progress, CancellationToken ct = default)
    {
        if (IsGameRunning(Paths.GameDir)) throw new UpdateBlockedException("the game is running: close it before updating");
        if (File.Exists(Paths.Journal)) throw new InvalidOperationException("an unfinished install exists: run recovery first");
        var writes = plan.ToWrite.ToList();
        foreach (var w in writes)
        {
            var blob = StagedBlob(w.File.Sha256);
            if (!File.Exists(blob) || Hashing.FileSha256(blob) != w.File.Sha256)
                throw new TrustException($"staged file for {w.File.Path} is missing or damaged");
        }

        var journal = new Journal
        {
            Id = RandomId.New(),
            ReleaseId = plan.Manifest.Release.Id,
            PreviousReleaseId = state.InstalledReleaseId,
            Started = DateTimeOffset.UtcNow,
            Writes = writes.Select(w => new JournalOp { Path = w.File.Path, Sha256 = w.File.Sha256, Existed = File.Exists(Paths.Full(w.File.Path)) }).ToList(),
            Deletes = plan.Deletes.ToList(),
        };
        var backup = Path.Combine(Paths.Backup, journal.Id);
        Directory.CreateDirectory(backup);
        if (File.Exists(Paths.StateFile)) File.Copy(Paths.StateFile, Path.Combine(backup, "state.json"), overwrite: true);
        SaveJournal(Paths.Journal, journal);

        var remainingUses = writes.GroupBy(w => w.File.Sha256).ToDictionary(g => g.Key, g => g.Count());
        long total = writes.Sum(w => w.File.Size), done = 0;
        foreach (var w in writes)
        {
            ct.ThrowIfCancellationRequested();
            var target = Paths.Full(w.File.Path);
            if (File.Exists(target)) FileUtil.MoveInto(target, Path.Combine(backup, "files", w.File.Path));
            Directory.CreateDirectory(Path.GetDirectoryName(target)!);
            var blob = StagedBlob(w.File.Sha256);
            if (--remainingUses[w.File.Sha256] == 0) File.Move(blob, target);
            else { File.Copy(blob, target + ".xp-tmp", overwrite: true); File.Move(target + ".xp-tmp", target); }
            state.Cache[w.File.Path] = FileUtil.Stat(target, w.File.Sha256);
            done += w.File.Size;
            progress?.Report(new Progress(Phase.Installing, done, total, w.File.Path, 0));
        }
        foreach (var d in journal.Deletes)
        {
            var target = Paths.Full(d);
            if (File.Exists(target)) FileUtil.MoveInto(target, Path.Combine(backup, "files", d));
            state.Cache.Remove(d);
        }

        state.InstalledReleaseId = plan.Manifest.Release.Id;
        state.InstalledVersion = plan.Manifest.Release.Version;
        state.InstalledRoots = plan.Manifest.Roots.ToList();
        state.InstalledLaunch = plan.Manifest.Release.Launch;
        state.Installed = plan.Manifest.Files.ToDictionary(f => f.Path, f => f.Sha256, StringComparer.OrdinalIgnoreCase);
        foreach (var k in state.Kept.Keys.ToList())
            if (state.Kept[k].ReleaseId != plan.Manifest.Release.Id) state.Kept.Remove(k);
        state.Save(Paths);
        Checkpoint("state saved");

        // the commit point, recorded in the journal itself: past it a crash is finished on the next start
        // rather than undone - files and state already say "new release", and the backup may already
        // have become backup/last, where an undo would not look for it
        journal.Phase = "committed";
        SaveJournal(Paths.Journal, journal);
        Checkpoint("committed");
        FinishCommit(journal, backup);
        log.Info($"installed {journal.ReleaseId}: {writes.Count} written, {journal.Deletes.Count} removed");
        MigrateSettings();
    }

    /// <summary>
    /// The player's settings a release asks to carry over (HdCoreMigration: hd_core on wherever hd is on). Runs after
    /// every install and at start-up after <see cref="Recover"/>, so a run broken off is finished by the next start;
    /// a file once migrated is not touched again. Never fails the caller: what is not done now is done next time.
    /// </summary>
    public void MigrateSettings()
    {
        try
        {
            foreach (var f in HdCoreMigration.Run(Paths, IsGameRunning))
                if (f.Step is not HdCoreStep.Done) log.Info($"hd_core: {f.Path} - {f.Step}");
        }
        catch (Exception e) when (e is UpdateBlockedException or IOException or UnauthorizedAccessException or InvalidOperationException)
        {
            log.Error("hd_core: settings not migrated now: " + e.Message);
        }
    }

    /// <summary>Test seam: called at the named steps of an install, to break it off exactly there.</summary>
    internal Action<string> Checkpoint { get; set; } = _ => { };

    /// <summary>Everything after the commit point. Safe to run again after a crash in the middle of it.</summary>
    void FinishCommit(Journal journal, string backup)
    {
        if (journal.Rollback)
        {
            // the update is undone for good: its undo set goes, and so does the reserve of what the rollback replaced
            if (Directory.Exists(Paths.LastBackup)) Directory.Delete(Paths.LastBackup, recursive: true);
            File.Delete(Paths.Journal);
            if (Directory.Exists(backup)) Directory.Delete(backup, recursive: true);
            return;
        }
        // keep exactly one undo set: this one becomes "last". No backup here means an earlier
        // attempt already moved it, and deleting "last" now would delete this very set
        if (Directory.Exists(backup))
        {
            SaveJournal(Path.Combine(backup, "undo.json"), journal);
            if (Directory.Exists(Paths.LastBackup)) Directory.Delete(Paths.LastBackup, recursive: true);
            Directory.Move(backup, Paths.LastBackup);
        }
        File.Delete(Paths.Journal);
        CleanStaging();
    }

    /// <summary>
    /// Called at start-up. An install that did not reach the commit point is undone; one that did is
    /// finished. Also run again if it is itself interrupted: the journal goes only after the undo is complete.
    /// </summary>
    public bool Recover()
    {
        if (!File.Exists(Paths.Journal)) return false;
        var journal = LoadJournal(Paths.Journal);
        var backup = Path.Combine(Paths.Backup, journal.Id);
        // a journal from a launcher before the commit record: the move to "last" is the only sign it committed
        var lastUndo = Path.Combine(Paths.LastBackup, "undo.json");
        var movedToLast = !Directory.Exists(backup) && File.Exists(lastUndo) && LoadJournal(lastUndo).Id == journal.Id;
        var what = journal.Rollback ? $"rollback to {journal.ReleaseId}" : $"install {journal.ReleaseId}";
        RecoveryFinished = journal.Phase == "committed" || movedToLast;
        if (RecoveryFinished)
        {
            log.Info($"{what} was interrupted after it committed: finishing it");
            FinishCommit(journal, backup);
            return true;
        }
        log.Info($"unfinished {what} found: undoing");
        Undo(journal, backup);
        // journal first: an undo interrupted after its backup is gone would find no old state to restore
        File.Delete(Paths.Journal);
        if (Directory.Exists(backup)) Directory.Delete(backup, recursive: true);
        return true;
    }

    /// <summary>After <see cref="Recover"/> returned true: the interrupted work was finished rather than undone.</summary>
    public bool RecoveryFinished { get; private set; }

    public bool CanRollback => File.Exists(Path.Combine(Paths.LastBackup, "undo.json"));

    /// <summary>
    /// "Undo the last update": puts back every replaced and removed file and the previous state. It is a
    /// transaction of its own, like an install: what it replaces is moved aside into a reserve first and
    /// the undo set is copied rather than moved, so a crash in the middle is undone by <see cref="Recover"/>
    /// and leaves the update installed and still undoable.
    /// </summary>
    public void RollbackLast()
    {
        if (IsGameRunning(Paths.GameDir)) throw new UpdateBlockedException("the game is running: close it before rolling back");
        if (File.Exists(Paths.Journal)) throw new InvalidOperationException("an unfinished install exists: run recovery first");
        if (!CanRollback) throw new InvalidOperationException("nothing to roll back");
        var undo = LoadJournal(Path.Combine(Paths.LastBackup, "undo.json"));
        var saved = Path.Combine(Paths.LastBackup, "files");

        // what goes where: the saved copy, or nothing for a file the update created
        var steps = new List<(string Path, string? Old)>();
        foreach (var d in undo.Deletes)
            if (File.Exists(Path.Combine(saved, d))) steps.Add((d, Path.Combine(saved, d)));
        foreach (var w in Enumerable.Reverse(undo.Writes))
        {
            var old = Path.Combine(saved, w.Path);
            if (File.Exists(old)) steps.Add((w.Path, old));
            else if (!w.Existed && File.Exists(Paths.Full(w.Path))) steps.Add((w.Path, null));
        }

        var journal = new Journal
        {
            Id = RandomId.New(),
            ReleaseId = undo.PreviousReleaseId ?? "",
            PreviousReleaseId = undo.ReleaseId,
            Rollback = true,
            Started = DateTimeOffset.UtcNow,
            Writes = steps.Select(s => new JournalOp { Path = s.Path, Existed = File.Exists(Paths.Full(s.Path)) }).ToList(),
        };
        var reserve = Path.Combine(Paths.Backup, journal.Id);
        Directory.CreateDirectory(reserve);
        if (File.Exists(Paths.StateFile)) File.Copy(Paths.StateFile, Path.Combine(reserve, "state.json"), overwrite: true);
        SaveJournal(Paths.Journal, journal);

        foreach (var (rel, old) in steps)
        {
            var target = Paths.Full(rel);
            if (File.Exists(target)) FileUtil.MoveInto(target, Path.Combine(reserve, "files", rel));
            if (old is not null)
            {
                Directory.CreateDirectory(Path.GetDirectoryName(target)!);
                File.Copy(old, target + ".xp-tmp", overwrite: true);
                File.Move(target + ".xp-tmp", target);
            }
            Checkpoint("rollback file");
        }
        RestoreState(Path.Combine(Paths.LastBackup, "state.json"));

        journal.Phase = "committed";
        SaveJournal(Paths.Journal, journal);
        Checkpoint("committed");
        FinishCommit(journal, reserve);
        log.Info($"rolled back {undo.ReleaseId} -> {undo.PreviousReleaseId ?? "(nothing installed)"}");
    }

    void Undo(Journal journal, string backup)
    {
        var files = Path.Combine(backup, "files");
        foreach (var d in journal.Deletes)
        {
            var saved = Path.Combine(files, d);
            if (File.Exists(saved)) FileUtil.MoveInto(saved, Paths.Full(d));
        }
        foreach (var w in Enumerable.Reverse(journal.Writes))
        {
            var target = Paths.Full(w.Path);
            var saved = Path.Combine(files, w.Path);
            if (File.Exists(saved)) FileUtil.MoveInto(saved, target);
            else if (!w.Existed && File.Exists(target)) File.Delete(target);
        }
        RestoreState(Path.Combine(backup, "state.json"));
    }

    void RestoreState(string oldState)
    {
        // replay protection survives an undo: the highest sequence ever seen is kept
        var seen = File.Exists(Paths.StateFile) ? LauncherState.Load(Paths, log).LastSequence : new();
        if (File.Exists(oldState))
        {
            File.Copy(oldState, Paths.StateFile, overwrite: true);
            var s = LauncherState.Load(Paths, log);
            foreach (var kv in seen) s.LastSequence[kv.Key] = Math.Max(kv.Value, s.LastSequence.GetValueOrDefault(kv.Key));
            s.Save(Paths);
        }
        else if (File.Exists(Paths.StateFile))
        {
            // there was no state before: keep channel and replay protection, forget the install
            var s = LauncherState.Load(Paths, log);
            s.InstalledReleaseId = null; s.InstalledVersion = null; s.Installed.Clear(); s.InstalledRoots.Clear(); s.Cache.Clear();
            s.Save(Paths);
        }
    }

    void CleanStaging()
    {
        if (!Directory.Exists(Paths.Staging)) return;
        foreach (var f in Directory.EnumerateFiles(Paths.Staging)) File.Delete(f);
    }

    static void SaveJournal(string path, Journal j) => FileUtil.WriteAtomic(path, JsonSerializer.SerializeToUtf8Bytes(j, CoreJson.Default.Journal));
    static Journal LoadJournal(string path) => JsonSerializer.Deserialize(File.ReadAllBytes(path), CoreJson.Default.Journal)
                                                ?? throw new InvalidOperationException("empty journal");
}
