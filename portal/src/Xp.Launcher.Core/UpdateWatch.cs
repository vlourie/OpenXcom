using Xp.Manifest;

namespace Xp.Launcher.Core;

/// <summary>
/// A running launcher (open, minimized or in the tray) looks at its channels between the checks the player
/// starts: only the small signed pointers, every five minutes, so a release reaches the player within
/// minutes without the multi-megabyte manifest. Nothing is written - the game may be running.
/// </summary>
public sealed class UpdateWatch(RepoClient repo)
{
    /// <summary>A pointer and its signature are under a kilobyte: two hundred launchers make one request a second.</summary>
    public static readonly TimeSpan Every = TimeSpan.FromMinutes(5);

    readonly Dictionary<string, long> _known = new();

    /// <summary>The highest sequence seen on each channel, for the launcher log.</summary>
    public string Summary => string.Join(", ", _known.Select(k => $"{k.Key} {k.Value}"));

    /// <summary>A pointer the launcher already shows (the check fetched it): no news about it later.</summary>
    public void Know(ChannelPointer p)
    {
        if (!_known.TryGetValue(p.Channel, out var s) || p.Sequence > s) _known[p.Channel] = p.Sequence;
    }

    /// <summary>
    /// Pointers of these channels with a sequence above the known one. The first look at a channel only
    /// remembers it: what was out when the launcher started is on the home page already.
    /// A channel that is not on the server is skipped.
    /// </summary>
    public async Task<List<ChannelPointer>> NewsAsync(IEnumerable<string> channels, CancellationToken ct)
    {
        var news = new List<ChannelPointer>();
        foreach (var channel in channels)
        {
            ChannelPointer p;
            try { p = await repo.GetPointerAsync(channel, 0, ct); }
            catch (FileNotFoundException) { continue; }
            if (_known.TryGetValue(channel, out var s) && p.Sequence > s) news.Add(p);
            Know(p);
        }
        return news;
    }
}
