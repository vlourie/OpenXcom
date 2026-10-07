using Xp.Launcher.Core;

namespace Xp.Launcher;

/// <summary>
/// What applying a profile changed, in the player's words: "HD interface: on, smoothed" rather than
/// "oxceHdUi: 2". Option names follow the game's own (STR_HD_* in common/Language/OXCE); an option
/// without a string of its own is shown as key = value, so a new one in xp-profiles.json is never lost.
/// </summary>
public static class ProfileText
{
    public static string Lines(IEnumerable<ProfileChange> items) => string.Join("\n", items.Select(i => "•  " + Line(i)));

    public static string Line(ProfileChange c) => c.Kind switch
    {
        ProfileChangeKind.ModsKept => L.T("pc.modsKept"),
        ProfileChangeKind.Mods => L.T("pc.mods", string.Join(", ", c.Mods ?? [])),
        ProfileChangeKind.Language => L.T("pc.language", L.Has("pc.lang." + c.Value) ? L.T("pc.lang." + c.Value) : c.Value),
        _ => L.Has($"pc.opt.{c.Key}.{c.Value}") ? L.T($"pc.opt.{c.Key}.{c.Value}")
           : L.Has("pc.opt." + c.Key) ? L.T("pc.opt." + c.Key, c.Value)
           : $"{c.Key} = {c.Value}",
    };
}
