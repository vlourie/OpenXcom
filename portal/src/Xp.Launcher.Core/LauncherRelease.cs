using Xp.Manifest;

namespace Xp.Launcher.Core;

/// <summary>
/// The launcher's own release, fetched the same way by both paths that deliver it: the setup
/// (xp-bootstrap with no arguments, Installer.cs) fetches it straight into the install folder, the
/// running launcher (SelfUpdate) into a staging folder that the bootstrapper swaps in after it exits.
/// Only what happens after the fetch differs; which files, how they are verified and which release
/// is refused is decided here once.
/// </summary>
public static class LauncherRelease
{
    /// <summary>The launcher of a game channel lives on its own channel: "stable" -> "launcher-stable".</summary>
    public static string ChannelFor(string gameChannel) => "launcher-" + gameChannel;

    /// <summary>
    /// The id Выпуск/release.ps1 gives a launcher version on a launcher channel ("launcher-0.3.20", "launcher-0.3.20-beta"):
    /// the running launcher finds the pack from its own release by it.
    /// </summary>
    public static string IdFor(string version, string launcherChannel) =>
        launcherChannel == ChannelFor("stable") ? $"launcher-{version}" : $"launcher-{version}-{launcherChannel[ChannelFor("").Length..]}";

    /// <summary>
    /// Every file of <paramref name="m"/> into <paramref name="dir"/>, each verified by size and SHA-256.
    /// A file already there and right is kept; one found right in <paramref name="reuseFrom"/> (the
    /// running launcher's folder) is copied instead of downloaded. A release without
    /// <paramref name="exeName"/> is refused before anything is fetched. <paramref name="onBytes"/> gets
    /// the bytes that became ready, kept and copied files included, so it sums to the release size. With
    /// <paramref name="packFrom"/> (the running launcher's release) the new files come as the release's pack from it when
    /// there is one smaller than they are: brotli takes the exe to about two fifths. Any failure of the pack but a cancel
    /// only means the files are fetched one by one. <paramref name="progress"/> sees only what comes over the network:
    /// the pack against its own size, then the files still missing against theirs.
    /// </summary>
    public static async Task FetchAsync(RepoClient repo, ReleaseManifest m, string dir, string exeName, string? reuseFrom,
        Action<long> onBytes, CancellationToken ct, string? packFrom = null, IProgress<Progress>? progress = null)
    {
        if (!m.Files.Any(f => f.Path.Equals(exeName, StringComparison.OrdinalIgnoreCase)))
            throw new ManifestException($"launcher release {m.Release.Id} has no {exeName}");
        var need = new List<ManifestFile>();
        foreach (var f in m.Files)
        {
            ct.ThrowIfCancellationRequested();
            var target = SafePath.Resolve(dir, f.Path);
            if (Matches(target, f)) { onBytes(f.Size); continue; }
            if (reuseFrom is not null && SafePath.Resolve(reuseFrom, f.Path) is var current && Matches(current, f))
            {
                Put(current, target);
                onBytes(f.Size);
                continue;
            }
            need.Add(f);
        }
        var meter = new SpeedMeter();
        if (packFrom is not null && m.Packs.FirstOrDefault(p => p.From.Equals(packFrom, StringComparison.OrdinalIgnoreCase)) is { } pack
            && pack.Size < need.DistinctBy(f => f.Sha256).Sum(f => f.Size))
        {
            long got = 0;
            need = await FromPackAsync(repo, m, pack, dir, need, onBytes, n =>
            {
                got += n;
                meter.Add(n);
                progress?.Report(new Progress(Phase.Downloading, got, pack.Size, $"pack {pack.From}", meter.BytesPerSecond));
            }, ct);
        }
        // RepoClient writes <target>.part and moves it in only after the hash matched
        long total = need.Sum(f => f.Size), done = 0;
        foreach (var f in need)
            await repo.DownloadBlobAsync(f.Sha256, f.Size, SafePath.Resolve(dir, f.Path), n =>
            {
                onBytes(n);
                done += n;
                meter.Add(n);
                progress?.Report(new Progress(Phase.Downloading, done, total, f.Path, meter.BytesPerSecond));
            }, ct);
    }

    /// <summary>The files of <paramref name="need"/> from the pack, each checked by its SHA-256; returns those still to fetch.</summary>
    static async Task<List<ManifestFile>> FromPackAsync(RepoClient repo, ReleaseManifest m, UpdatePack pack, string dir, List<ManifestFile> need,
        Action<long> onBytes, Action<long> onPackBytes, CancellationToken ct)
    {
        // beside the prepared folder, not in it: the folder holds the release's files and nothing else
        var file = dir.TrimEnd(Path.DirectorySeparatorChar) + ".pack.tar.br";
        var blobs = dir.TrimEnd(Path.DirectorySeparatorChar) + ".blobs";
        try
        {
            await repo.DownloadPackAsync(m.Release.Id, pack, file, onPackBytes, ct);
            Directory.CreateDirectory(blobs);
            var sizes = need.DistinctBy(f => f.Sha256).ToDictionary(f => f.Sha256, f => f.Size, StringComparer.Ordinal);
            await Task.Run(() => PackReader.Unpack(file, sizes, sha => Path.Combine(blobs, sha), null, ct), ct);
            var rest = new List<ManifestFile>();
            foreach (var f in need)
            {
                var blob = Path.Combine(blobs, f.Sha256);
                if (!File.Exists(blob)) { rest.Add(f); continue; }
                Put(blob, SafePath.Resolve(dir, f.Path));
                onBytes(f.Size);
            }
            return rest;
        }
        catch (Exception e) when (e is not OperationCanceledException)
        {
            return need.Where(f => !Matches(SafePath.Resolve(dir, f.Path), f)).ToList();
        }
        finally
        {
            try { File.Delete(file); File.Delete(file + ".part"); } catch (IOException) { }
            try { if (Directory.Exists(blobs)) Directory.Delete(blobs, recursive: true); } catch (IOException) { }
        }
    }

    static void Put(string source, string target)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(target)!);
        File.Copy(source, target + ".xp-new", overwrite: true);
        File.Move(target + ".xp-new", target, overwrite: true);
    }

    static bool Matches(string path, ManifestFile f) =>
        File.Exists(path) && new FileInfo(path).Length == f.Size && Hashing.FileSha256(path) == f.Sha256;
}
