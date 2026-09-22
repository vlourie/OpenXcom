using System.Diagnostics;
using Xp.Launcher.Core;
using Xp.Manifest;

namespace Xp.Launcher;

/// <summary>
/// The launcher updates itself from its own channel ("launcher-&lt;channel&gt;"): new files are downloaded
/// and verified into %LOCALAPPDATA%, then the bootstrapper swaps them in after this process exits.
/// </summary>
public sealed class SelfUpdate(RepoClient repo, Settings settings, ILauncherLog log)
{
    public const string BootstrapperName = "xp-bootstrap.exe";
    public static string AppDir => AppContext.BaseDirectory;
    public static string ExeName => Path.GetFileName(Environment.ProcessPath ?? "XPiratezLauncher.exe");

    public static string ChannelFor(string gameChannel) => "launcher-" + gameChannel;

    public async Task<ReleaseManifest?> CheckAsync(string gameChannel, CancellationToken ct)
    {
        var channel = ChannelFor(gameChannel);
        settings.LauncherSequence.TryGetValue(channel, out var seen);
        LatestRelease latest;
        try { latest = await repo.GetLatestAsync(channel, seen, ct); }
        catch (FileNotFoundException) { return null; }   // no launcher channel published yet
        settings.LauncherSequence[channel] = latest.Pointer.Sequence;
        settings.Save();
        return Version.TryParse(latest.Manifest.Release.Version, out var v) && v > BuiltIn.Version ? latest.Manifest : null;
    }

    public static bool AppDirWritable()
    {
        try
        {
            var probe = Path.Combine(AppDir, ".write-test-" + Environment.ProcessId);
            File.WriteAllText(probe, "");
            File.Delete(probe);
            return true;
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { return false; }
    }

    /// <summary>Downloads and verifies every file of the new launcher; returns the directory holding it.</summary>
    public async Task<string> PrepareAsync(ReleaseManifest m, CancellationToken ct)
    {
        var dir = Path.Combine(Settings.Dir, "update", m.Release.Id);
        foreach (var f in m.Files)
        {
            var target = SafePath.Resolve(dir, f.Path);
            if (File.Exists(target) && Hashing.FileSha256(target) == f.Sha256) continue;
            var current = SafePath.Resolve(AppDir, f.Path);
            if (File.Exists(current) && new FileInfo(current).Length == f.Size && Hashing.FileSha256(current) == f.Sha256)
            {
                Directory.CreateDirectory(Path.GetDirectoryName(target)!);
                File.Copy(current, target, overwrite: true);
                continue;
            }
            await repo.DownloadBlobAsync(f.Sha256, f.Size, target, _ => { }, ct);
        }
        if (!m.Files.Any(f => f.Path.Equals(ExeName, StringComparison.OrdinalIgnoreCase)))
            throw new ManifestException($"launcher release has no {ExeName}");
        log.Info($"launcher {m.Release.Version} prepared");
        return dir;
    }

    /// <summary>Starts the bootstrapper from a temporary copy and returns; the caller must exit right away.</summary>
    public void Apply(string preparedDir, ReleaseManifest m)
    {
        var boot = Path.Combine(preparedDir, BootstrapperName);
        if (!File.Exists(boot)) boot = Path.Combine(AppDir, BootstrapperName);
        if (!File.Exists(boot)) throw new FileNotFoundException("bootstrapper missing", BootstrapperName);
        // run from a copy: the bootstrapper may itself be among the files being replaced
        var tmp = Path.Combine(Path.GetTempPath(), $"xp-bootstrap-{Environment.ProcessId}.exe");
        File.Copy(boot, tmp, overwrite: true);
        // shell execute: the bootstrapper must not inherit our handles (a console pipe would stay open)
        var psi = new ProcessStartInfo(tmp) { UseShellExecute = true };
        psi.ArgumentList.Add("--pid"); psi.ArgumentList.Add(Environment.ProcessId.ToString());
        psi.ArgumentList.Add("--source"); psi.ArgumentList.Add(preparedDir);
        psi.ArgumentList.Add("--target"); psi.ArgumentList.Add(AppDir);
        psi.ArgumentList.Add("--exe"); psi.ArgumentList.Add(ExeName);
        foreach (var f in m.Files) { psi.ArgumentList.Add("--file"); psi.ArgumentList.Add(f.Path); }
        Process.Start(psi);
        log.Info($"bootstrapper started for launcher {m.Release.Version}");
    }

    /// <summary>A freshly updated launcher confirms it started, or the bootstrapper rolls it back.</summary>
    public static void ConfirmStarted()
    {
        try { File.WriteAllText(Path.Combine(AppDir, ".update-ok"), BuiltIn.VersionText); }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { }
    }
}
