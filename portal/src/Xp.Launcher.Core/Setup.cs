using Xp.Manifest;

namespace Xp.Launcher.Core;

/// <summary>
/// One line of the install wizard's list (docs/portal/EDITIONS.md §12.1 step 3). <see cref="Locked"/>:
/// the engine, always on. <see cref="Needs"/>: the name of a component it cannot go without, not
/// ticked. <see cref="WrongEngine"/>: the mod asks for an engine this release is not.
/// </summary>
/// <summary>A mod of the player's own in user/mods: its compatibility with our build was never checked.</summary>
/// <param name="OtherMaster">the master it is made for, when that is not the game's; the engine will not switch it on</param>
/// <param name="WrongEngine">the engine it asks for, when that is not ours</param>
public sealed record OwnMod(string Id, string Name, string Version, string Folder, bool IsMaster, bool Active,
    string? OtherMaster, string? WrongEngine);

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
                ComponentKind.Addon => profile?.Mods.Any(pm => Same(pm.Id, c.Mod) && pm.OnFor(lang)) == true,
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

    /// <summary>
    /// The mods the player put into user/mods themselves: none of our components is that mod.
    /// The launcher does not install or remove them, it only says what the engine will make of them;
    /// on and off stays with the game's Mods menu.
    /// </summary>
    /// <param name="master">the master mod the ticks make the game, or null when none is ticked</param>
    public static List<OwnMod> OwnMods(string gameDir, ReleaseManifest m, string? master)
    {
        var ours = new HashSet<string>(m.Components.Select(c => c.Mod).Where(id => id.Length > 0), StringComparer.Ordinal);
        var cfgPath = Path.Combine(gameDir, "user", "options.cfg");
        var cfg = OptionsCfg.Parse(File.Exists(cfgPath) ? File.ReadAllText(cfgPath) : "");
        var result = new List<OwnMod>();
        var root = Path.Combine(gameDir, "user", "mods");
        if (!Directory.Exists(root)) return result;
        foreach (var dir in Directory.EnumerateDirectories(root).Order(StringComparer.OrdinalIgnoreCase))
        {
            var folder = Path.GetFileName(dir);
            var meta = Path.Combine(dir, "metadata.yml");
            ModMetadata md;
            try { md = ModMetadata.Parse(File.Exists(meta) ? File.ReadAllText(meta) : "", folder); }
            catch (Exception e) when (e is IOException or UnauthorizedAccessException) { continue; }
            if (ours.Contains(md.Id) || result.Any(o => o.Id == md.Id)) continue;
            // the engine's rule (ModInfo::canActivate): a master mod, a mod for any master, or one for this very master
            var otherMaster = !md.IsMaster && !md.AnyMaster && master is not null && md.Master != master ? md.Master : null;
            result.Add(new OwnMod(md.Id, md.Name, md.Version, folder, md.IsMaster,
                cfg.Mods.Any(x => x.Id == md.Id && x.Active), otherMaster, EngineMismatch(m, md.Engine)));
        }
        return result;
    }

    /// <summary>requiredExtendedEngine: "" any, "Extended" any OXCE (ours is one), "OXCE-HD" only our line.</summary>
    static string? EngineMismatch(ReleaseManifest m, ComponentInfo c) => EngineMismatch(m, c.Engine);

    static string? EngineMismatch(ReleaseManifest m, string engine) => engine switch
    {
        "" or "Extended" => null,
        "OXCE-HD" => m.Release.Line is "" or "oxce-hd" ? null : engine,
        _ => engine,
    };

    static bool Same(string a, string b) => string.Equals(a, b, StringComparison.OrdinalIgnoreCase);
}
