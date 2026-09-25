using Xp.Manifest;

namespace Xp.Launcher.Core;

/// <summary>
/// One line of the install wizard's list (docs/portal/EDITIONS.md §12.1 step 3). <see cref="Locked"/>:
/// the engine, always on. <see cref="Needs"/>: the name of a component it cannot go without, not
/// ticked. <see cref="WrongEngine"/>: the mod asks for an engine this release is not.
/// </summary>
public sealed record SetupRow(ComponentInfo Component, bool Checked, bool Locked, string? Needs, string? WrongEngine)
{
    public bool Blocked => Needs is not null || WrongEngine is not null;
}

/// <summary>Which components of a release get installed: the wizard's ticks and what follows from them.</summary>
public static class Setup
{
    /// <summary>The game language the launcher's own one stands for: OXCE names English "en-US".</summary>
    public static string GameLanguage(string launcherLanguage) => launcherLanguage == "ru" ? "ru" : "en-US";

    /// <summary>
    /// First install: the engine, every master (or only the profile's), art and shared layers, and the
    /// addons the profile names for this language. Nothing 18+ - that waits for the age question.
    /// </summary>
    public static HashSet<string> Defaults(ReleaseManifest m, ModProfile? profile, string language)
    {
        var lang = ProfileWriter.LangOf(language);
        var picked = new HashSet<string>(StringComparer.Ordinal);
        foreach (var c in m.Components)
        {
            bool on = c.Kind switch
            {
                ComponentKind.Engine => true,
                ComponentKind.Master => profile is null || Same(c.Mod, profile.Master),
                ComponentKind.Art or ComponentKind.Shared => !c.Adult,
                ComponentKind.Addon => profile?.Mods.Any(pm => Same(pm.Id, c.Mod) && (pm.Lang is null || ProfileWriter.LangOf(pm.Lang) == lang)) == true,
                _ => false,
            };
            if (on) picked.Add(c.Id);
        }
        return Normalize(m, picked);
    }

    /// <summary>
    /// What the ticks really give: the engine always, and without everything whose requirement is
    /// not ticked or whose engine is not this one - repeated, because dropping a master drops its addons.
    /// </summary>
    public static HashSet<string> Normalize(ReleaseManifest m, IEnumerable<string> picked)
    {
        var set = new HashSet<string>(picked, StringComparer.Ordinal);
        var ids = m.Components.Select(c => c.Id).ToHashSet(StringComparer.Ordinal);
        set.IntersectWith(ids);
        foreach (var c in m.Components.Where(c => c.Kind == ComponentKind.Engine)) set.Add(c.Id);
        for (bool changed = true; changed;)
        {
            changed = false;
            foreach (var c in m.Components)
            {
                if (!set.Contains(c.Id) || c.Kind == ComponentKind.Engine) continue;
                if (c.Requires.Any(r => ids.Contains(r) && !set.Contains(r)) || EngineMismatch(m, c) is not null)
                {
                    set.Remove(c.Id);
                    changed = true;
                }
            }
        }
        return set;
    }

    /// <summary>The list as the wizard shows it: ticks after <see cref="Normalize"/>, and why a line is grey.</summary>
    public static List<SetupRow> Rows(ReleaseManifest m, IEnumerable<string> picked)
    {
        var set = Normalize(m, picked);
        var byId = m.Components.ToDictionary(c => c.Id, StringComparer.Ordinal);
        return m.Components.Where(c => c.Kind != ComponentKind.Launcher).Select(c =>
        {
            var missing = c.Requires.FirstOrDefault(r => byId.ContainsKey(r) && !set.Contains(r));
            return new SetupRow(c, set.Contains(c.Id), c.Kind == ComponentKind.Engine,
                missing is null ? null : Title(byId[missing]), EngineMismatch(m, c));
        }).ToList();
    }

    /// <summary>
    /// The release cut down to the player's components. Files of a component not described in the
    /// manifest stay (an older manifest has none): a list can only take away what it knows.
    /// </summary>
    public static ReleaseManifest Chosen(ReleaseManifest m, IReadOnlyCollection<string>? picked)
    {
        if (picked is null || m.Components.Count == 0) return m;
        var keep = Normalize(m, picked);
        var known = m.Components.Select(c => c.Id).ToHashSet(StringComparer.Ordinal);
        return new ReleaseManifest
        {
            Schema = m.Schema,
            Release = m.Release,
            Components = m.Components.Where(c => keep.Contains(c.Id)).ToList(),
            Roots = m.Roots,
            Files = m.Files.Where(f => keep.Contains(f.Component) || !known.Contains(f.Component)).ToList(),
            Deletes = m.Deletes,
        };
    }

    /// <summary>The master mod the ticks make the game: its profile sets options.cfg up.</summary>
    public static string? Master(ReleaseManifest m, IEnumerable<string> picked)
    {
        var set = Normalize(m, picked);
        return m.Components.FirstOrDefault(c => c.Kind == ComponentKind.Master && set.Contains(c.Id))?.Mod;
    }

    public static string Title(ComponentInfo c) => c.Name.Length > 0 ? c.Name : c.Mod.Length > 0 ? c.Mod : c.Id;

    /// <summary>requiredExtendedEngine: "" any, "Extended" any OXCE (ours is one), "OXCE-HD" only our line.</summary>
    static string? EngineMismatch(ReleaseManifest m, ComponentInfo c) => c.Engine switch
    {
        "" or "Extended" => null,
        "OXCE-HD" => m.Release.Line is "" or "oxce-hd" ? null : c.Engine,
        _ => c.Engine,
    };

    static bool Same(string a, string b) => string.Equals(a, b, StringComparison.OrdinalIgnoreCase);
}
