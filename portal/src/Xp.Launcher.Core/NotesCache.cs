using System.Globalization;
using System.Text;
using Xp.Manifest;

namespace Xp.Launcher.Core;

/// <summary>
/// The channel's history (the «Обновления» page and "What's new") kept in the launcher's state folder:
/// the page shows it at once, and the server's copy is asked for only when a release came out that the
/// kept one was not fetched for, once a day besides (the roadmap changes without a release), or on
/// "Refresh" (XP-000268). The bytes are kept as signed and checked again on every reading, so a file
/// changed on disk is never shown: it is dropped and fetched anew.
/// </summary>
public sealed class NotesCache(GamePaths paths)
{
    public static readonly TimeSpan MaxAge = TimeSpan.FromDays(1);

    /// <summary>The game is running: the fetched history is shown but not kept, nothing is written under the game (R-179).</summary>
    public Func<bool> IsGameRunning { get; init; } = () => false;

    string Dir => Path.Combine(paths.StateDir, "notes");
    public string FilePath(string channel) => Path.Combine(Dir, channel + ".notes.json");
    string SigPath(string channel) => FilePath(channel) + ".sig";
    /// <summary>Two lines: when it was fetched (UTC, ISO) and the release the channel pointed to then.</summary>
    string MetaPath(string channel) => FilePath(channel) + ".meta";

    /// <summary>The kept history, checked like the server's; null when there is none or it does not pass.</summary>
    public ChannelNotes? Load(RepoClient repo, string channel)
    {
        if (!ManifestValidator.IsValidId(channel)) return null;
        try
        {
            if (!File.Exists(FilePath(channel)) || !File.Exists(SigPath(channel))) return null;
            return repo.VerifyNotes(channel, File.ReadAllBytes(FilePath(channel)), File.ReadAllBytes(SigPath(channel)));
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or TrustException) { return null; }
    }

    /// <summary>
    /// Is the server's copy worth asking for: nothing kept, kept a day ago or longer, or the channel now points
    /// to a release (<paramref name="latestRelease"/>, from the update check; null - not known) the kept one was not fetched for.
    /// </summary>
    public bool Due(string channel, string? latestRelease, DateTime nowUtc)
    {
        if (ReadMeta(channel) is not var (fetched, forRelease)) return true;
        if (nowUtc - fetched >= MaxAge || fetched > nowUtc + TimeSpan.FromMinutes(5)) return true;
        return !string.IsNullOrEmpty(latestRelease) && latestRelease != forRelease;
    }

    /// <summary>The server's history, kept for the next time. The server's errors pass to the caller; a failed write keeps nothing.</summary>
    public async Task<ChannelNotes> FetchAsync(RepoClient repo, string channel, string? latestRelease, CancellationToken ct)
    {
        var s = await repo.GetSignedNotesAsync(channel, ct);
        if (IsGameRunning()) return s.Notes;
        try
        {
            if (File.Exists(MetaPath(channel))) File.Delete(MetaPath(channel));   // the pair below is not written at once: without the meta line it is due again
            FileUtil.WriteAtomic(FilePath(channel), s.Bytes);
            FileUtil.WriteAtomic(SigPath(channel), s.Signature);
            var forRelease = !string.IsNullOrEmpty(latestRelease) ? latestRelease : s.Notes.Releases.FirstOrDefault()?.Id ?? "";
            FileUtil.WriteAtomic(MetaPath(channel), Encoding.UTF8.GetBytes(
                DateTime.UtcNow.ToString("o", CultureInfo.InvariantCulture) + "\n" + forRelease + "\n"));
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { }
        return s.Notes;
    }

    /// <summary>The kept history when it is not due, else the server's.</summary>
    public async Task<ChannelNotes> GetAsync(RepoClient repo, string channel, string? latestRelease, CancellationToken ct)
    {
        if (!Due(channel, latestRelease, DateTime.UtcNow) && Load(repo, channel) is { } kept) return kept;
        return await FetchAsync(repo, channel, latestRelease, ct);
    }

    (DateTime Fetched, string ForRelease)? ReadMeta(string channel)
    {
        if (!ManifestValidator.IsValidId(channel)) return null;
        try
        {
            if (!File.Exists(MetaPath(channel)) || !File.Exists(FilePath(channel))) return null;
            var lines = File.ReadAllText(MetaPath(channel), Encoding.UTF8).Split('\n');
            if (!DateTime.TryParse(lines[0].Trim(), CultureInfo.InvariantCulture, DateTimeStyles.RoundtripKind, out var at)) return null;
            return (at.ToUniversalTime(), lines.Length > 1 ? lines[1].Trim() : "");
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { return null; }
    }
}
