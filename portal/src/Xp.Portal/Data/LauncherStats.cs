namespace Xp.Portal.Data;

/// <summary>
/// One launcher installation, counted without knowing who it belongs to. The key is a random number
/// the launcher made for itself and sends in every ping: it is tied to no account, name or address,
/// and the site keeps nothing else about the sender — no IP, no machine name. What is kept is just
/// enough for three numbers on the entrance screen: how many installations there are, how long the
/// game has been played in all of them, and how many are playing right now.
/// </summary>
public sealed class LauncherInstall
{
    /// <summary>32 lower-case hex digits (a Guid in "N" format), made by the launcher.</summary>
    public string Id { get; set; } = "";
    public DateTimeOffset FirstSeen { get; set; }
    public DateTimeOffset LastSeen { get; set; }
    /// <summary>The last ping that said "the game is running"; null once the launcher said it has stopped.</summary>
    public DateTimeOffset? LastPlayingAt { get; set; }
    public long PlaySeconds { get; set; }
    public string LauncherVersion { get; set; } = "";
    /// <summary>Id of the game release the launcher had installed at its last ping; empty if none.</summary>
    public string GameRelease { get; set; } = "";
}

public static class StatsLimits
{
    public const int InstallLength = 32;
    public const int LauncherMax = 32;
    public const int GameMax = 64;
    /// <summary>
    /// The launcher pings every five minutes while the game runs. Two pings further apart than this are not
    /// one session (the launcher was closed, the machine slept), so the gap between them is not played time.
    /// </summary>
    public static readonly TimeSpan PlayWindow = TimeSpan.FromMinutes(11);
}
