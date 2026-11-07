namespace Xp.Launcher.Core;

/// <summary>
/// The unread-messages counter of the rail button "Chat" and when it is news. The launcher asks the site together
/// with the tickets (not on a timer of its own); this only remembers the answer. What waited when the launcher
/// started is on the button already, so the first look never calls for a notice: only a count that grew afterwards does.
/// </summary>
public sealed class MessageWatch
{
    int? _last;

    public int Unread { get; private set; }

    /// <summary>The site's count. True when there are more unread messages than at the last look (and it was not the first look).</summary>
    public bool Update(int unread)
    {
        unread = Math.Max(0, unread);
        bool grew = _last is { } before && unread > before;
        _last = unread;
        Unread = unread;
        return grew;
    }

    /// <summary>Not linked, or unlinked: no counter, and the next answer is a first look again.</summary>
    public void Reset()
    {
        _last = null;
        Unread = 0;
    }

    /// <summary>The person read a dialogue here: the counter goes down at once, without waiting for the next look.</summary>
    public void Read(int count)
    {
        Unread = Math.Max(0, Unread - Math.Max(0, count));
        if (_last is { } l) _last = Math.Max(0, l - Math.Max(0, count));
    }
}
