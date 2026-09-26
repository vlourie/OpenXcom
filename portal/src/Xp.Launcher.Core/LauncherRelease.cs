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
    /// Every file of <paramref name="m"/> into <paramref name="dir"/>, each verified by size and SHA-256.
    /// A file already there and right is kept; one found right in <paramref name="reuseFrom"/> (the
    /// running launcher's folder) is copied instead of downloaded. A release without
    /// <paramref name="exeName"/> is refused before anything is fetched. <paramref name="onBytes"/> gets
    /// the bytes that became ready, kept and copied files included, so it sums to the release size.
    /// </summary>
    public static async Task FetchAsync(RepoClient repo, ReleaseManifest m, string dir, string exeName, string? reuseFrom,
        Action<long> onBytes, CancellationToken ct)
    {
        if (!m.Files.Any(f => f.Path.Equals(exeName, StringComparison.OrdinalIgnoreCase)))
            throw new ManifestException($"launcher release {m.Release.Id} has no {exeName}");
        foreach (var f in m.Files)
        {
            ct.ThrowIfCancellationRequested();
            var target = SafePath.Resolve(dir, f.Path);
            if (Matches(target, f)) { onBytes(f.Size); continue; }
            if (reuseFrom is not null && SafePath.Resolve(reuseFrom, f.Path) is var current && Matches(current, f))
            {
                Directory.CreateDirectory(Path.GetDirectoryName(target)!);
                File.Copy(current, target + ".xp-new", overwrite: true);
                File.Move(target + ".xp-new", target, overwrite: true);
                onBytes(f.Size);
                continue;
            }
            // RepoClient writes <target>.part and moves it in only after the hash matched
            await repo.DownloadBlobAsync(f.Sha256, f.Size, target, onBytes, ct);
        }
    }

    static bool Matches(string path, ManifestFile f) =>
        File.Exists(path) && new FileInfo(path).Length == f.Size && Hashing.FileSha256(path) == f.Sha256;
}
