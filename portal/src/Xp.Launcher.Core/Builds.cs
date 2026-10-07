using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;

namespace Xp.Launcher.Core;

/// <summary>
/// One build: a game, its mods in order and the player's settings, all in its own options.cfg, which the game
/// gets with -cfg (docs/portal/MULTIMOD.md §3, §4.2). The mods and options are not repeated here: the truth
/// is that options.cfg, the one the game's Mods and Options menus write.
/// </summary>
public sealed class Build
{
    public string Id { get; set; } = "";
    public string Title { get; set; } = "";
    /// <summary>The profile (by its master, xp-profiles.json) the build was made from; null - none.</summary>
    public string? Template { get; set; }
    /// <summary>What the player plays. A claim, not a fact: the mods on decide (MULTIMOD §3.3). Stage 1: the engine master.</summary>
    public string? TargetGame { get; set; }
    /// <summary>The engine's master mod: -master, and the save folder user/&lt;master&gt;/.</summary>
    public string? EngineMaster { get; set; }
    /// <summary>The config folder, relative to the game folder with '/': "user/builds/piratez/".</summary>
    public string Cfg { get; set; } = "";
    public DateTimeOffset Created { get; set; }
    public DateTimeOffset? LastPlayed { get; set; }
}

/// <summary>launcher/builds.json: the builds of one installation and the one the player picked last.</summary>
public sealed class BuildSet
{
    public int Schema { get; set; } = 1;
    public string? Last { get; set; }
    public List<Build> Builds { get; set; } = [];

    public Build? Find(string id) => Builds.FirstOrDefault(b => b.Id.Equals(id, StringComparison.OrdinalIgnoreCase));

    /// <summary>The build "Play" starts: the last picked, or the first.</summary>
    [JsonIgnore]
    public Build? Current =>(Last is { } l ? Find(l) : null) ?? Builds.FirstOrDefault();
}

/// <summary>What the first start of a launcher with builds did with the old user/options.cfg.</summary>
public sealed record BuildMigration(Build Build, bool CopiedOptions, bool FromFolders);

/// <summary>
/// The builds of one installation. Every change refuses while a game of this installation runs: the game writes
/// its options.cfg on exit and would overwrite whatever was written in between (MULTIMOD §3.6).
/// </summary>
public sealed class BuildStore(GamePaths paths, Func<string, bool>? isGameRunning = null)
{
    public const string BuildsFolder = "user/builds/";
    readonly Func<string, bool> _running = isGameRunning ?? GameProcess.IsRunningIn;

    public GamePaths Paths { get; } = paths;
    public string FilePath => Path.Combine(Paths.StateDir, "builds.json");
    /// <summary>Folders of deleted builds: a delete moves the settings here, it does not destroy them.</summary>
    public string DeletedDir => Path.Combine(Paths.StateDir, "backup", "builds");

    public bool Exists => File.Exists(FilePath);

    /// <summary>
    /// The builds as written. Reading only: a damaged file gives the list rebuilt from the build folders in memory,
    /// and stays as it is until a write repairs it (<see cref="Repaired"/>) - a read may come while the game runs.
    /// </summary>
    public BuildSet Load(ILauncherLog? log = null) => Read(log, repair: false);

    bool _toldDamaged;

    BuildSet Read(ILauncherLog? log, bool repair)
    {
        if (!File.Exists(FilePath)) return new BuildSet();
        try
        {
            return JsonSerializer.Deserialize(File.ReadAllBytes(FilePath), BuildJson.Default.BuildSet) ?? new BuildSet();
        }
        catch (JsonException e)
        {
            var set = FromFolders();
            if (!repair || _running(Paths.GameDir))
            {
                if (!_toldDamaged) log?.Error($"builds.json unreadable ({e.Message}): the list is rebuilt from {BuildsFolder} in memory, the file is repaired when the game is closed");
                _toldDamaged = true;
                return set;
            }
            var bad = FilePath + ".bad";
            File.Move(FilePath, bad, overwrite: true);
            log?.Error($"builds.json unreadable ({e.Message}): moved to {Path.GetFileName(bad)}, the list is rebuilt from {BuildsFolder}");
            if (set.Builds.Count > 0) Save(set);
            return set;
        }
    }

    /// <summary>The list for a change: a damaged file is kept aside as .bad and written anew. Only after <see cref="Guard"/>.</summary>
    BuildSet Repaired(ILauncherLog? log = null) => Read(log, repair: true);

    void Save(BuildSet set) => FileUtil.WriteAtomic(FilePath, JsonSerializer.SerializeToUtf8Bytes(set, BuildJson.Default.BuildSet));

    /// <summary>The options.cfg of a build, absolute.</summary>
    public string OptionsFile(Build b) => Path.Combine(Paths.Full(b.Cfg.TrimEnd('/')), "options.cfg");

    /// <summary>
    /// The options.cfg the game of this installation reads now: the current build's, or user/options.cfg before
    /// the first start with builds. Reading only: nothing is migrated.
    /// </summary>
    public string CurrentOptionsFile() =>
        Exists && Load().Current is { } b ? OptionsFile(b) : Path.Combine(Paths.GameDir, "user", "options.cfg");

    /// <summary>
    /// The build to play, migrating on the first start (MULTIMOD §3.3): user/options.cfg is copied into the folder
    /// of a build named after the master mod on in it; user/options.cfg itself stays for the exe started by hand.
    /// </summary>
    /// <param name="master">the master to use when options.cfg names none (a fresh install: the wizard's)</param>
    public Build Ensure(string? master = null, ILauncherLog? log = null)
    {
        // under a running game a damaged list is not repaired: the rebuilt one is played from as it is
        if (Exists && Read(log, repair: true).Current is { } current) return current;
        var m = Migrate(master);
        log?.Info(m.FromFolders ? $"builds: list rebuilt from {BuildsFolder}, current '{m.Build.Id}'"
            : $"builds: first start with builds, user/options.cfg {(m.CopiedOptions ? "copied" : "absent, nothing copied")} into {m.Build.Cfg}");
        return m.Build;
    }

    BuildMigration Migrate(string? master)
    {
        Guard("set the builds up");
        var folders = FromFolders();
        if (folders.Builds.Count > 0)
        {
            Save(folders);
            return new BuildMigration(folders.Current!, false, true);
        }
        var installed = ProfileWriter.ScanMods(Paths.GameDir);
        var legacy = Path.Combine(Paths.GameDir, "user", "options.cfg");
        var cfg = OptionsCfg.Parse(File.Exists(legacy) ? File.ReadAllText(legacy) : "");
        bool IsMaster(string id) => installed.Any(i => i.IsMaster && i.Id == id);
        master = cfg.Mods.Where(x => x.Active && IsMaster(x.Id)).Select(x => x.Id).FirstOrDefault()
                 ?? (master is not null && IsMaster(master) ? master : null);
        // the id is the master's: the launcher's per-master state (profiles.json, profile-mods.json) becomes this build's
        var id = master?.ToLowerInvariant() ?? "default";
        var b = NewBuild(id, installed.FirstOrDefault(i => i.Id == master)?.Name is { Length: > 0 } n ? n : id, master);
        b.Template = master is not null && ProfileSet.Load(Paths.GameDir)?.For(master) is not null ? master : null;
        var target = OptionsFile(b);
        bool copied = false;
        // a target already there is a migration cut short: the game never ran with it (no builds.json yet), keep it
        if (File.Exists(legacy) && !File.Exists(target))
        {
            FileUtil.WriteAtomic(target, File.ReadAllBytes(legacy));
            copied = true;
        }
        else Directory.CreateDirectory(Path.GetDirectoryName(target)!);
        Save(new BuildSet { Last = b.Id, Builds = [b] });
        return new BuildMigration(b, copied, false);
    }

    /// <summary>The builds as their folders say, for a lost or damaged builds.json: user/builds/&lt;id&gt;/options.cfg.</summary>
    BuildSet FromFolders()
    {
        var set = new BuildSet();
        var root = Paths.Full(BuildsFolder.TrimEnd('/'));
        if (!Directory.Exists(root)) return set;
        var installed = ProfileWriter.ScanMods(Paths.GameDir);
        foreach (var dir in Directory.EnumerateDirectories(root).Order(StringComparer.OrdinalIgnoreCase))
        {
            var file = Path.Combine(dir, "options.cfg");
            if (!File.Exists(file)) continue;
            var master = OptionsCfg.Parse(File.ReadAllText(file)).Mods
                .Where(x => x.Active && installed.Any(i => i.IsMaster && i.Id == x.Id)).Select(x => x.Id).FirstOrDefault();
            var id = Path.GetFileName(dir);
            set.Builds.Add(NewBuild(id, id, master));
        }
        set.Last = set.Builds.FirstOrDefault()?.Id;
        return set;
    }

    static Build NewBuild(string id, string title, string? master) => new()
    {
        Id = id, Title = title, EngineMaster = master, TargetGame = master,
        Cfg = BuildsFolder + id + "/", Created = DateTimeOffset.Now,
    };

    /// <summary>
    /// A new build from a profile (MULTIMOD §3.5): its mods and options, none of the player's keys, recommended
    /// options of its own on the first start. The game language is the one given (the current build's).
    /// </summary>
    public Build Create(string title, string template, string? language, int? screenHeight)
    {
        Guard("create a build");
        var set = Repaired();
        var profile = ProfileSet.Load(Paths.GameDir)?.For(template)
                      ?? throw new InvalidOperationException($"no profile '{template}' in {ProfileSet.FileName}");
        var b = NewBuild(UniqueId(set, title), Title(title), profile.Master);
        b.Template = template;
        var dir = Path.GetDirectoryName(OptionsFile(b))!;
        if (Directory.Exists(dir)) throw new InvalidOperationException($"folder {b.Cfg} already exists");
        Directory.CreateDirectory(dir);
        try
        {
            var state = new ProfileState(Paths);
            var done = state.Load();
            var written = state.LoadMods();
            ProfileWriter.Apply(Paths.GameDir, profile, ProfileWriter.ScanMods(Paths.GameDir), language, screenHeight, done,
                writtenMods: written, cfgDir: dir, stateKey: b.Id);
            state.Save(done);
            state.SaveMods(written);
        }
        catch
        {
            Directory.Delete(dir, recursive: true);   // only what was made here a moment ago
            throw;
        }
        set.Builds.Add(b);
        set.Last = b.Id;
        Save(set);
        return b;
    }

    /// <summary>A copy (MULTIMOD §3.5): options.cfg byte for byte, so the player's settings and the engine's
    /// "recommended options were set" come along, and so does the launcher's memory of the profile.</summary>
    public Build Copy(string sourceId, string title)
    {
        Guard("copy a build");
        var set = Repaired();
        var src = set.Find(sourceId) ?? throw new InvalidOperationException($"no build '{sourceId}'");
        var b = NewBuild(UniqueId(set, title), Title(title), src.EngineMaster);
        b.Template = src.Template;
        b.TargetGame = src.TargetGame;
        var from = OptionsFile(src);
        var to = OptionsFile(b);
        if (Directory.Exists(Path.GetDirectoryName(to))) throw new InvalidOperationException($"folder {b.Cfg} already exists");
        if (File.Exists(from)) FileUtil.WriteAtomic(to, File.ReadAllBytes(from));
        else Directory.CreateDirectory(Path.GetDirectoryName(to)!);
        var state = new ProfileState(Paths);
        var done = state.Load();
        var written = state.LoadMods();
        var key = src.Id.ToLowerInvariant();
        if (done.TryGetValue(key, out var v)) { done[b.Id] = v; state.Save(done); }
        if (written.TryGetValue(key, out var w)) { written[b.Id] = w; state.SaveMods(written); }
        set.Builds.Add(b);
        set.Last = b.Id;
        Save(set);
        return b;
    }

    public void Rename(string id, string title)
    {
        Guard("rename a build");
        var set = Repaired();
        var b = set.Find(id) ?? throw new InvalidOperationException($"no build '{id}'");
        b.Title = Title(title);
        Save(set);
    }

    /// <summary>The build "Play" starts from now on.</summary>
    public void Select(string id)
    {
        Guard("switch the build");
        var set = Repaired();
        var b = set.Find(id) ?? throw new InvalidOperationException($"no build '{id}'");
        set.Last = b.Id;
        Save(set);
    }

    /// <summary>
    /// Removes a build from the list; its folder goes to launcher/backup/builds, not away. The mods stay: they are
    /// the installation's, other builds use them. The last build is not deleted - there would be nothing to play.
    /// The list is written first and the folder moved after: cut short anywhere, no build of the list is left
    /// without its options.cfg (at worst a folder stays in user/builds without a build).
    /// </summary>
    public string Delete(string id)
    {
        Guard("delete a build");
        var set = Repaired();
        var b = set.Find(id) ?? throw new InvalidOperationException($"no build '{id}'");
        if (set.Builds.Count == 1) throw new InvalidOperationException("the only build cannot be deleted");
        var dir = Path.GetDirectoryName(OptionsFile(b))!;
        var kept = Path.Combine(DeletedDir, $"{b.Id}-{DateTime.Now:yyyyMMdd-HHmmss}");
        var at = set.Builds.IndexOf(b);
        var last = set.Last;
        set.Builds.Remove(b);
        if (b.Id.Equals(set.Last, StringComparison.OrdinalIgnoreCase)) set.Last = set.Builds[0].Id;
        Save(set);   // fails - nothing has changed yet
        if (Directory.Exists(dir))
        {
            try
            {
                Directory.CreateDirectory(DeletedDir);
                Directory.Move(dir, kept);
            }
            catch
            {
                // the folder is where it was: the build goes back into the list
                set.Builds.Insert(at, b);
                set.Last = last;
                Save(set);
                throw;
            }
        }
        var state = new ProfileState(Paths);
        var done = state.Load();
        if (done.Remove(b.Id.ToLowerInvariant())) state.Save(done);
        var written = state.LoadMods();
        if (written.Remove(b.Id.ToLowerInvariant())) state.SaveMods(written);
        return kept;
    }

    /// <summary>Just before "Play" starts the game: the build was played now. A note, not a change the player asked
    /// for: under a running game it is skipped, not refused.</summary>
    public void MarkPlayed(string id)
    {
        if (_running(Paths.GameDir)) return;
        var set = Repaired();
        if (set.Find(id) is not { } b) return;
        b.LastPlayed = DateTimeOffset.Now;
        set.Last = b.Id;
        Save(set);
    }

    /// <summary>
    /// The engine's arguments for a build: absolute paths with '/', so neither the working folder nor the quoting of
    /// a trailing backslash matters (MULTIMOD §3.1, R-097). The engine adds the closing '/' itself, we give it too.
    /// </summary>
    public IReadOnlyList<string> LaunchArgs(Build b)
    {
        var args = new List<string>
        {
            "-user", Slash(Path.Combine(Paths.GameDir, "user")),
            "-cfg", Slash(Paths.Full(b.Cfg.TrimEnd('/'))),
        };
        if (b.EngineMaster is { Length: > 0 } m) args.AddRange(["-master", m]);
        return args;
    }

    static string Slash(string dir) => Path.GetFullPath(dir).Replace('\\', '/').TrimEnd('/') + "/";

    void Guard(string what)
    {
        if (_running(Paths.GameDir)) throw new UpdateBlockedException($"the game is running: close it to {what}");
    }

    static string Title(string title) => title.Trim() is { Length: > 0 } t ? t : throw new InvalidOperationException("a build needs a name");

    static readonly Regex NotSlug = new("[^a-z0-9]+");
    static readonly HashSet<string> Reserved = new(StringComparer.OrdinalIgnoreCase)
        { "con", "prn", "aux", "nul", "com1", "com2", "com3", "com4", "lpt1", "lpt2", "lpt3" };

    /// <summary>A folder name from the title: latin letters and digits, the rest "-"; "build" when nothing is left.</summary>
    string UniqueId(BuildSet set, string title)
    {
        var slug = NotSlug.Replace(title.Trim().ToLowerInvariant(), "-").Trim('-');
        if (slug.Length > 32) slug = slug[..32].TrimEnd('-');
        if (slug.Length == 0 || Reserved.Contains(slug)) slug = "build";
        var id = slug;
        // a folder without a build (left by hand, or a deleted one put back) is not taken over either
        for (int i = 2; set.Find(id) is not null || Directory.Exists(Paths.Full(BuildsFolder + id)); i++) id = $"{slug}-{i}";
        return id;
    }
}

[JsonSourceGenerationOptions(WriteIndented = true, PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase,
    PropertyNameCaseInsensitive = true, DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull)]
[JsonSerializable(typeof(BuildSet))]
internal sealed partial class BuildJson : JsonSerializerContext
{
}
