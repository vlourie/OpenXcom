using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;
using Xp.Manifest;

namespace Xp.Launcher.Core;

/// <summary>
/// How we want the game set up for one master mod: which mods are on and in what order, and which
/// options. The engine has this idea too (recommendedUserOptions in a ruleset), but applies the
/// recommended ones once per installation, so switching to another master never gets its own.
/// Profiles ship with the game release in xp-profiles.json, next to the exe: they belong to the
/// mod versions of that release, not to the launcher. docs/portal/EDITIONS.md §12.5.
/// </summary>
public sealed class ProfileSet
{
    public const string FileName = "xp-profiles.json";

    public int Schema { get; set; } = 1;
    public List<ModProfile> Profiles { get; set; } = [];

    public ModProfile? For(string master) =>
        Profiles.FirstOrDefault(p => p.Master.Equals(master, StringComparison.OrdinalIgnoreCase));

    public static ProfileSet Parse(string json) =>
        JsonSerializer.Deserialize(json, ProfileJson.Default.ProfileSet) ?? throw new JsonException("empty profile file");

    /// <summary>The profiles of an installed game, or null when this release has none.</summary>
    public static ProfileSet? Load(string gameDir)
    {
        var path = Path.Combine(gameDir, FileName);
        return File.Exists(path) ? Parse(File.ReadAllText(path)) : null;
    }
}

public sealed class ModProfile
{
    /// <summary>The master mod id as in its metadata.yml ("piratez").</summary>
    public string Master { get; set; } = "";
    /// <summary>Raised when the recommended options change and should be offered again.</summary>
    public int Version { get; set; } = 1;
    /// <summary>
    /// Load order after the master, by mod id. "*" is where the player's own mods go; without it
    /// they go last. Mods that are not installed are skipped.
    /// </summary>
    public List<ProfileMod> Mods { get; set; } = [];
    public List<ProfileOption> Options { get; set; } = [];
}

public sealed class ProfileMod
{
    public string Id { get; set; } = "";
    /// <summary>On only for this game language ("ru"): a translation patch must be off for the others.</summary>
    public string? Lang { get; set; }
    /// <summary>Always off, whatever the language: a mod another one replaces (OAK-RU under XPZ RU-patch 12.3).</summary>
    public bool Off { get; set; }

    /// <summary>Is the mod on in a game of this language (as <see cref="ProfileWriter.LangOf"/> gives it)?</summary>
    public bool OnFor(string lang) => !Off && (Lang is null || ProfileWriter.LangOf(Lang) == lang);
}

public sealed class ProfileOption
{
    public string Key { get; set; } = "";
    /// <summary>As written in options.cfg; "auto" for oxceHdScale means "by the screen height".</summary>
    public string Value { get; set; } = "";
    /// <summary>"fixed": set before every start; "recommended": set once per profile version, then the player's.</summary>
    public string Mode { get; set; } = "recommended";
    /// <summary>Only when this mod is installed: HD options mean nothing without the HD art.</summary>
    public string? NeedsMod { get; set; }
}

/// <summary>A mod of the installation, as the engine will see it.</summary>
public sealed record InstalledMod(string Id, bool IsMaster, string Name = "");

public enum ProfileChangeKind { ModsKept, Mods, Language, Option }

/// <summary>
/// One thing applying a profile changed. The window words it for the player (ProfileText in the launcher),
/// ToString is the line for the log.
/// </summary>
/// <param name="Mods">for <see cref="ProfileChangeKind.Mods"/>: the mods on, by the name in their metadata.yml</param>
public sealed record ProfileChange(ProfileChangeKind Kind, string Key = "", string Value = "", IReadOnlyList<string>? Mods = null)
{
    public override string ToString() => Kind switch
    {
        ProfileChangeKind.ModsKept => "mods: kept as the player set them in the game",
        ProfileChangeKind.Mods => "mods: " + string.Join(", ", Mods ?? []),
        ProfileChangeKind.Language => "language: " + Value,
        _ => $"{Key}: {Value}",
    };
}

/// <summary>What applying a profile changed, for the log and the window.</summary>
public sealed record ProfileResult(bool Written, IReadOnlyList<ProfileChange> Items, string? Backup)
{
    /// <summary>The lines for the log.</summary>
    public IReadOnlyList<string> Changes => [.. Items.Select(i => i.ToString())];
}

/// <summary>
/// user/options.cfg, edited the way the engine writes it (Options::save): a "mods" sequence of
/// {active, id} whose order is the load order, then an "options" map of scalars. Only the mods list
/// and our keys change; every other line stays as the player or the engine left it.
/// </summary>
public sealed class OptionsCfg
{
    public List<(string Id, bool Active)> Mods { get; } = [];
    readonly List<string> head = [];       // anything before "mods:" we do not understand, kept
    readonly List<string> options = [];    // the lines of the options map, as they were
    readonly List<string> tail = [];       // top-level sections after options, kept
    public bool HasOptions { get; private set; }

    static readonly Regex OptionLine = new(@"^  ([A-Za-z0-9_]+):(?:\s(.*))?$");

    public static OptionsCfg Parse(string text)
    {
        var cfg = new OptionsCfg();
        string section = "";
        (string? Id, bool Active)? item = null;
        void Flush()
        {
            if (item is { Id: { } id } it) cfg.Mods.Add((id, it.Active));
            item = null;
        }
        foreach (var raw in text.Replace("\r\n", "\n").Split('\n'))
        {
            var line = raw.TrimEnd('\r');
            if (line.Length > 0 && !char.IsWhiteSpace(line[0]) && !line.StartsWith('-') && !line.StartsWith('#'))
            {
                Flush();
                section = line.TrimEnd();
                if (section == "options:") cfg.HasOptions = true;
                else if (section != "mods:") (cfg.HasOptions ? cfg.tail : cfg.head).Add(line);
                continue;
            }
            switch (section)
            {
                case "mods:":
                    var t = line.Trim();
                    if (t.StartsWith("- ")) { Flush(); item = (null, false); t = t[2..].Trim(); }
                    if (item is null || t.Length == 0) break;
                    var colon = t.IndexOf(':');
                    if (colon < 0) break;
                    var key = t[..colon].Trim();
                    var val = Unquote(t[(colon + 1)..].Trim());
                    if (key == "id") item = (val, item.Value.Active);
                    else if (key == "active") item = (item.Value.Id, val.Equals("true", StringComparison.OrdinalIgnoreCase));
                    break;
                case "options:":
                    if (line.Length > 0) cfg.options.Add(line);
                    break;
                default:
                    if (line.Length > 0) (cfg.HasOptions ? cfg.tail : cfg.head).Add(line);
                    break;
            }
        }
        Flush();
        return cfg;
    }

    /// <summary>The value of an option as written, or null when the file does not name it.</summary>
    public string? Get(string key)
    {
        foreach (var l in options)
            if (OptionLine.Match(l) is { Success: true } m && m.Groups[1].Value == key) return Unquote(m.Groups[2].Value.Trim());
        return null;
    }

    public void Set(string key, string value)
    {
        HasOptions = true;
        var line = $"  {key}: {Quote(value)}";
        for (int i = 0; i < options.Count; i++)
            if (OptionLine.Match(options[i]) is { Success: true } m && m.Groups[1].Value == key) { options[i] = line; return; }
        options.Add(line);
    }

    public string Render()
    {
        var sb = new StringBuilder();
        foreach (var l in head) sb.Append(l).Append('\n');
        sb.Append("mods:\n");
        foreach (var (id, active) in Mods)
            sb.Append("  - active: ").Append(active ? "true" : "false").Append("\n    id: ").Append(Quote(id)).Append('\n');
        if (HasOptions)
        {
            sb.Append("options:\n");
            foreach (var l in options) sb.Append(l).Append('\n');
        }
        foreach (var l in tail) sb.Append(l).Append('\n');
        return sb.ToString();
    }

    static string Unquote(string v) =>
        v.Length >= 2 && (v[0] == '"' && v[^1] == '"' || v[0] == '\'' && v[^1] == '\'') ? v[1..^1] : v;

    static readonly Regex Plain = new(@"^[A-Za-z0-9_][A-Za-z0-9_.+\-]*$");

    static string Quote(string v) =>
        Plain.IsMatch(v) ? v : "\"" + v.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"";
}

/// <summary>Applies a profile to user/options.cfg. Nothing else in the installation is touched.</summary>
public static class ProfileWriter
{
    public const string ScaleKey = "oxceHdScale";

    /// <summary>The mods the engine will find: user/mods and standard/, by the id in metadata.yml.</summary>
    public static List<InstalledMod> ScanMods(string gameDir)
    {
        var found = new List<InstalledMod>();
        foreach (var root in new[] { Path.Combine(gameDir, "user", "mods"), Path.Combine(gameDir, "standard") })
        {
            if (!Directory.Exists(root)) continue;
            foreach (var dir in Directory.EnumerateDirectories(root))
            {
                var meta = Path.Combine(dir, "metadata.yml");
                if (!File.Exists(meta)) continue;
                var m = ModMetadata.Parse(File.ReadAllText(meta), Path.GetFileName(dir));
                if (!found.Any(f => f.Id == m.Id)) found.Add(new InstalledMod(m.Id, m.IsMaster, m.Name));
            }
        }
        return found;
    }

    /// <summary>k for the HD layer by screen height: 720 -> 2, 1080 -> 3, 1440 and up -> 4.</summary>
    public static int ScaleFor(int screenHeight) => Math.Clamp((int)Math.Round(screenHeight / 360.0), 1, 4);

    /// <param name="language">the game language to set ("ru", "en-US"), or null to leave the player's</param>
    /// <param name="recommendedDone">profile versions whose recommended options were already applied; updated here</param>
    /// <param name="dryRun">only say what would change: nothing is written, recommendedDone stays</param>
    /// <param name="writtenMods">per master, the mods list the launcher wrote last (<see cref="ModsSignature"/>); updated here.
    /// When options.cfg no longer matches it, the player changed the mods in the game, and the list is theirs</param>
    /// <param name="resetMods">"back to recommended": the profile's mods list and recommended options, whatever the player did</param>
    /// <param name="switchOn">mods the player has just ticked in the launcher: on, whichever way the list is kept</param>
    public static ProfileResult Apply(string gameDir, ModProfile profile, IReadOnlyList<InstalledMod> installed,
        string? language, int? screenHeight, IDictionary<string, int> recommendedDone, bool dryRun = false,
        IDictionary<string, string>? writtenMods = null, bool resetMods = false, IReadOnlyCollection<string>? switchOn = null)
    {
        var path = Path.Combine(gameDir, "user", "options.cfg");
        var before = File.Exists(path) ? File.ReadAllText(path) : "";
        var cfg = OptionsCfg.Parse(before);
        var changes = new List<ProfileChange>();
        var byId = installed.ToDictionary(m => m.Id, StringComparer.Ordinal);
        if (!byId.TryGetValue(profile.Master, out var master) || !master.IsMaster)
            throw new InvalidOperationException($"master mod '{profile.Master}' is not installed");

        var doneKey = profile.Master.ToLowerInvariant();
        if (resetMods) recommendedDone.Remove(doneKey);
        var lang = LangOf(language ?? cfg.Get("language") ?? "");
        bool playersList = !resetMods && writtenMods is not null && writtenMods.TryGetValue(doneKey, out var wrote)
                           && ModsSignature(wrote.Split('\n').Select(id => (id, true)), byId) != ModsSignature(cfg.Mods, byId);
        var mods = playersList ? [.. cfg.Mods] : OrderMods(cfg.Mods, profile, byId, lang);
        if (playersList) changes.Add(new ProfileChange(ProfileChangeKind.ModsKept));
        foreach (var id in switchOn ?? [])
        {
            if (!byId.TryGetValue(id, out var sm) || sm.IsMaster) continue;
            int at = mods.FindIndex(m => m.Id == id);
            // a mod the profile switches by language stays as the profile said (the RU patch in an English game)
            if (!playersList && profile.Mods.Any(pm => pm.Id == id && (pm.Lang is not null || pm.Off))) continue;
            if (at < 0) mods.Add((id, true));
            else mods[at] = (id, true);
        }
        if (!mods.SequenceEqual(cfg.Mods))
            changes.Add(new ProfileChange(ProfileChangeKind.Mods, Mods: [.. mods.Where(m => m.Active)
                .Select(m => byId.TryGetValue(m.Id, out var im) && im.Name.Length > 0 ? im.Name : m.Id)]));
        // the player's list is not remembered as ours: it would pass for ours on the next start and be rewritten
        if (!dryRun && writtenMods is not null && !playersList) writtenMods[doneKey] = ModsSignature(mods, byId);
        cfg.Mods.Clear();
        cfg.Mods.AddRange(mods);

        if (language is { Length: > 0 } && cfg.Get("language") != language)
        {
            cfg.Set("language", language);
            changes.Add(new ProfileChange(ProfileChangeKind.Language, "language", language));
        }
        // the language was chosen in the launcher: the game does not ask it again on its first start
        if (language is { Length: > 0 } && cfg.Get("oxceLanguageChosen") != "true") cfg.Set("oxceLanguageChosen", "true");

        bool offerRecommended = !recommendedDone.TryGetValue(doneKey, out var done) || done < profile.Version;
        foreach (var o in profile.Options)
        {
            bool fixedOne = o.Mode.Equals("fixed", StringComparison.OrdinalIgnoreCase);
            if (!fixedOne && !offerRecommended) continue;
            if (o.NeedsMod is { Length: > 0 } need && !mods.Any(m => m.Active && m.Id == need)) continue;
            var value = o.Value;
            if (o.Key == ScaleKey && value.Equals("auto", StringComparison.OrdinalIgnoreCase))
            {
                if (screenHeight is not > 0) continue;
                value = ScaleFor(screenHeight.Value).ToString();
            }
            if (cfg.Get(o.Key) == value) continue;
            cfg.Set(o.Key, value);
            changes.Add(new ProfileChange(ProfileChangeKind.Option, o.Key, value));
        }
        var after = cfg.Render();
        if (dryRun) return new ProfileResult(false, changes, null);
        if (offerRecommended) recommendedDone[doneKey] = profile.Version;
        if (after == before) return new ProfileResult(false, changes, null);
        string? backup = null;
        if (before.Length > 0)
        {
            backup = path + ".bak";
            File.Copy(path, backup, overwrite: true);
        }
        // the engine reads it with yaml-cpp: plain UTF-8, no BOM (R-001, the exception for game files)
        FileUtil.WriteAtomic(path, new UTF8Encoding(false).GetBytes(after));
        return new ProfileResult(true, changes, backup);
    }

    /// <summary>
    /// The launcher's call: the profile shipped in the game folder for <paramref name="master"/>, or for
    /// the master on in options.cfg. Null when there is nothing to apply (no profiles in this release,
    /// no profile for that master, the master not installed) - the game still starts.
    /// </summary>
    public static ProfileResult? ApplyForGame(GamePaths paths, string? master, string? language, int? screenHeight,
        bool resetMods = false, IReadOnlyCollection<string>? switchOn = null)
    {
        if (ProfileSet.Load(paths.GameDir) is not { } set) return null;
        var installed = ScanMods(paths.GameDir);
        var cfgPath = Path.Combine(paths.GameDir, "user", "options.cfg");
        master ??= OptionsCfg.Parse(File.Exists(cfgPath) ? File.ReadAllText(cfgPath) : "").Mods
            .Where(m => m.Active && installed.Any(i => i.IsMaster && i.Id == m.Id)).Select(m => m.Id).FirstOrDefault();
        if (master is null || set.For(master) is not { } profile || !installed.Any(i => i.IsMaster && i.Id == profile.Master)) return null;
        var state = new ProfileState(paths);
        var done = state.Load();
        var written = state.LoadMods();
        var r = Apply(paths.GameDir, profile, installed, language, screenHeight, done, false, written, resetMods, switchOn);
        state.Save(done);
        state.SaveMods(written);
        return r;
    }

    /// <summary>
    /// What of a mods list the player decides: the mods on, in their order. Mods that are not installed
    /// drop out (a component removed in the launcher is not the player's change), and so do the ones
    /// off - the engine adds every mod it finds switched off, and that is not the player's change either.
    /// </summary>
    public static string ModsSignature(IEnumerable<(string Id, bool Active)> mods, IReadOnlyDictionary<string, InstalledMod> installed) =>
        string.Join("\n", mods.Where(m => m.Active && installed.ContainsKey(m.Id)).Select(m => m.Id).Distinct());

    /// <summary>"ru", "ru-RU" -> "ru"; the part a profile's Lang is compared with.</summary>
    public static string LangOf(string language) => language.Split('-', '_')[0].ToLowerInvariant();

    internal static List<(string Id, bool Active)> OrderMods(List<(string Id, bool Active)> current, ModProfile profile,
        IReadOnlyDictionary<string, InstalledMod> installed, string lang)
    {
        bool IsMaster(string id) => installed.TryGetValue(id, out var m) && m.IsMaster;
        var inProfile = new HashSet<string>(profile.Mods.Select(m => m.Id), StringComparer.Ordinal);

        // masters first, as the engine keeps them; ours is the only one on
        var result = new List<(string Id, bool Active)> { (profile.Master, true) };
        foreach (var id in current.Select(m => m.Id).Concat(installed.Values.Where(m => m.IsMaster).Select(m => m.Id)))
            if (IsMaster(id) && !result.Any(r => r.Id == id)) result.Add((id, false));

        var others = current.Where(m => !IsMaster(m.Id) && m.Id != profile.Master && !inProfile.Contains(m.Id))
                            .GroupBy(m => m.Id).Select(g => g.First()).ToList();
        bool placed = false;
        foreach (var pm in profile.Mods)
        {
            if (pm.Id == "*") { result.AddRange(others); placed = true; continue; }
            if (!installed.ContainsKey(pm.Id) || IsMaster(pm.Id)) continue;
            result.Add((pm.Id, pm.OnFor(lang)));
        }
        if (!placed) result.AddRange(others);
        return result;
    }
}

/// <summary>Which profile versions already had their recommended options applied, per game folder.</summary>
public sealed class ProfileState(GamePaths paths)
{
    public string Path { get; } = System.IO.Path.Combine(paths.StateDir, "profiles.json");

    public Dictionary<string, int> Load()
    {
        try
        {
            return File.Exists(Path) ? JsonSerializer.Deserialize(File.ReadAllBytes(Path), ProfileJson.Default.DictionaryStringInt32) ?? [] : [];
        }
        catch (Exception e) when (e is JsonException or IOException or UnauthorizedAccessException) { return []; }
    }

    public void Save(Dictionary<string, int> done) =>
        FileUtil.WriteAtomic(Path, JsonSerializer.SerializeToUtf8Bytes(done, ProfileJson.Default.DictionaryStringInt32));

    /// <summary>Per master, the mods list the launcher wrote last (<see cref="ProfileWriter.ModsSignature"/>).</summary>
    public string ModsPath { get; } = System.IO.Path.Combine(paths.StateDir, "profile-mods.json");

    public Dictionary<string, string> LoadMods()
    {
        try
        {
            return File.Exists(ModsPath) ? JsonSerializer.Deserialize(File.ReadAllBytes(ModsPath), ProfileJson.Default.DictionaryStringString) ?? [] : [];
        }
        catch (Exception e) when (e is JsonException or IOException or UnauthorizedAccessException) { return []; }
    }

    public void SaveMods(Dictionary<string, string> written) =>
        FileUtil.WriteAtomic(ModsPath, JsonSerializer.SerializeToUtf8Bytes(written, ProfileJson.Default.DictionaryStringString));
}

[JsonSourceGenerationOptions(WriteIndented = true, PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase,
    PropertyNameCaseInsensitive = true, ReadCommentHandling = JsonCommentHandling.Skip, AllowTrailingCommas = true)]
[JsonSerializable(typeof(ProfileSet))]
[JsonSerializable(typeof(Dictionary<string, int>))]
[JsonSerializable(typeof(Dictionary<string, string>))]
internal sealed partial class ProfileJson : JsonSerializerContext
{
}
