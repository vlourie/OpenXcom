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

    /// <summary>Components of the release that have a file this launcher installed and still records.</summary>
    public static HashSet<string> Installed(ReleaseManifest m, LauncherState state)
    {
        var ids = m.Components.Select(c => c.Id).ToHashSet(StringComparer.Ordinal);
        return m.Files.Where(f => ids.Contains(f.Component) && state.Installed.ContainsKey(f.Path))
                      .Select(f => f.Component).ToHashSet(StringComparer.Ordinal);
    }

    /// <summary>
    /// The wizard's first ticks: the player's saved choice; on an installed game that has none (installs
    /// from before the wizard) what is installed - an unknown choice keeps the files (R-183); the
    /// defaults only for a folder with nothing of ours.
    /// </summary>
    public static HashSet<string> Initial(ReleaseManifest m, LauncherState state, ModProfile? profile, string language)
    {
        if (state.Components is { } mine) return Normalize(m, mine);
        var installed = Installed(m, state);
        return installed.Count > 0 ? Normalize(m, installed) : Defaults(m, profile, language);
    }

    /// <summary>Installed components the ticks leave out: the install removes their files.</summary>
    public static List<ComponentInfo> Removing(ReleaseManifest m, LauncherState state, IEnumerable<string> picked)
    {
        var keep = Normalize(m, picked);
        var installed = Installed(m, state);
        return m.Components.Where(c => installed.Contains(c.Id) && !keep.Contains(c.Id)).ToList();
    }

    /// <summary>
    /// Saves the ticks as the player's choice. When they remove installed components, <paramref name="confirm"/>
    /// gets the list first; no - nothing is saved and the files stay. Returns the saved state and the
    /// choice it had before (the installed components when there was none), or null when cancelled.
    /// A running game - before the question or after it - throws <see cref="UpdateBlockedException"/>, nothing saved.
    /// </summary>
    public static async Task<(LauncherState State, HashSet<string> Before)?> CommitAsync(Updater u, ReleaseManifest m,
        IEnumerable<string> picked, Func<IReadOnlyList<ComponentInfo>, Task<bool>> confirm)
    {
        var state = u.LoadState();
        var keep = Normalize(m, picked);
        var removing = Removing(m, state, keep);
        BlockUnderGame(u);
        if (removing.Count > 0 && !await confirm(removing)) return null;
        BlockUnderGame(u);   // the game may have been started while the question was open
        var before = state.Components is { } mine ? new HashSet<string>(mine, StringComparer.Ordinal) : Installed(m, state);
        state.Components = [.. keep.Order(StringComparer.Ordinal)];
        state.Save(u.Paths);
        return (state, before);
    }

    static void BlockUnderGame(Updater u)
    {
        if (u.IsGameRunning(u.Paths.GameDir))
            throw new UpdateBlockedException("the game is running: close it before changing components");
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

    /// <summary>
    /// The mods a component brings, by the id in their metadata.yml: each user/mods/&lt;folder&gt;/metadata.yml the release
    /// files under it (art.hd ships hd and hd_core), read from the game folder, so call it after the install. Its own
    /// mod comes last - the ones it brings along load before it (hd_core before hd).
    /// </summary>
    public static List<string> ModsOf(ReleaseManifest m, ComponentInfo c, string gameDir)
    {
        var ids = new List<string>();
        foreach (var f in m.Files.Where(f => f.Component == c.Id).OrderBy(f => f.Path, StringComparer.Ordinal))
        {
            var seg = f.Path.Split('/');
            if (seg.Length != 4 || !Same(seg[0], "user") || !Same(seg[1], "mods") || !Same(seg[3], "metadata.yml")) continue;
            var file = Path.Combine(gameDir, "user", "mods", seg[2], "metadata.yml");
            if (!File.Exists(file)) continue;
            var id = ModMetadata.Parse(File.ReadAllText(file), seg[2]).Id;
            if (id != c.Mod && !ids.Contains(id)) ids.Add(id);
        }
        if (c.Mod.Length > 0) ids.Add(c.Mod);
        return ids;
    }

    /// <summary>The master mod the ticks make the game: its profile sets options.cfg up.</summary>
    public static string? Master(ReleaseManifest m, IEnumerable<string> picked)
    {
        var set = Normalize(m, picked);
        return m.Components.FirstOrDefault(c => c.Kind == ComponentKind.Master && set.Contains(c.Id))?.Mod;
    }

    public static string Title(ComponentInfo c) => c.Name.Length > 0 ? c.Name : c.Mod.Length > 0 ? c.Mod : c.Id;

    /// <summary>
    /// The mods the player put into user/mods themselves: none of our components is that mod, and the release ships
    /// nothing into its folder (art.hd brings hd_core along with hd - it is no component's own mod, yet ours).
    /// The launcher does not install or remove them, it only says what the engine will make of them;
    /// on and off stays with the game's Mods menu.
    /// </summary>
    /// <param name="master">the master mod the ticks make the game, or null when none is ticked</param>
    /// <param name="cfgPath">the options.cfg that says which are on (the current build's); null - user/options.cfg</param>
    public static List<OwnMod> OwnMods(string gameDir, ReleaseManifest m, string? master, string? cfgPath = null)
    {
        var ours = new HashSet<string>(m.Components.Select(c => c.Mod).Where(id => id.Length > 0), StringComparer.Ordinal);
        var shipped = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var f in m.Files)
        {
            var seg = f.Path.Split('/');
            if (seg.Length > 3 && Same(seg[0], "user") && Same(seg[1], "mods")) shipped.Add(seg[2]);
        }
        cfgPath ??= Path.Combine(gameDir, "user", "options.cfg");
        var cfg = OptionsCfg.Parse(File.Exists(cfgPath) ? File.ReadAllText(cfgPath) : "");
        var result = new List<OwnMod>();
        var root = Path.Combine(gameDir, "user", "mods");
        if (!Directory.Exists(root)) return result;
        foreach (var dir in Directory.EnumerateDirectories(root).Order(StringComparer.OrdinalIgnoreCase))
        {
            var folder = Path.GetFileName(dir);
            if (shipped.Contains(folder)) continue;
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
