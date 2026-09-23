using Xp.Manifest;

namespace Xp.ReleaseBuilder;

/// <summary>
/// Splits a release into components by the rules of docs/portal/EDITIONS.md:
/// user/mods/&lt;m&gt;/hd_18+/ is the adult art layer, user/mods/&lt;m&gt;/hd/ and the whole of mod "hd"
/// the HD art layer, the rest of a mod its own component (kind from its metadata.yml),
/// top-level files, common/ and standard/ the engine. Anything else stops the build unless
/// an explicit --map names its component.
/// </summary>
public sealed class ComponentPlan
{
    public const string EngineId = "engine";
    public const string HdId = "art.hd";
    public const string Hd18Id = "art.hd18";
    public const string HdFolder = "hd";
    public const string Hd18Folder = "hd_18+";
    /// <summary>The HD mod itself: all its files are the art layer, not a mod of their own.</summary>
    public const string HdModId = "hd";

    public Dictionary<string, string> FileComponent { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, ComponentInfo> Components { get; } = new(StringComparer.Ordinal);
    public List<string> Warnings { get; } = new();

    static readonly string[] EngineDirs = ["common", "standard"];

    /// <param name="sources">relative path -> local file</param>
    /// <param name="engines">what the line's exe answers to in requiredExtendedEngine</param>
    /// <param name="maps">explicit path prefix -> component id, for trees the rules do not know</param>
    public static ComponentPlan Build(IReadOnlyDictionary<string, string> sources, IReadOnlyCollection<string> engines,
        IReadOnlyDictionary<string, string> maps, IReadOnlyDictionary<string, string> versions)
    {
        var plan = new ComponentPlan();
        var mods = new Dictionary<string, ModMetadata>(StringComparer.OrdinalIgnoreCase);

        foreach (var path in sources.Keys.Order(StringComparer.Ordinal))
        {
            var seg = path.Split('/');
            string id;
            var mapped = maps.Where(m => path.StartsWith(m.Key, StringComparison.OrdinalIgnoreCase))
                             .OrderByDescending(m => m.Key.Length).Select(m => m.Value).FirstOrDefault();
            if (mapped is not null) id = mapped;
            else if (seg.Length >= 4 && Is(seg[0], "user") && Is(seg[1], "mods"))
            {
                var folder = seg[2];
                if (!mods.TryGetValue(folder, out var meta))
                    mods[folder] = meta = plan.ReadMetadata(sources, folder);
                if (Is(seg[3], Hd18Folder) && seg.Length > 4) id = Hd18Id;
                else if ((Is(seg[3], HdFolder) && seg.Length > 4) || meta.Id == HdModId) id = HdId;
                else id = plan.ModComponent(meta);
            }
            else if (seg.Length == 1 || EngineDirs.Any(d => Is(seg[0], d))) id = EngineId;
            else throw new InvalidOperationException(
                $"'{path}' matches no component rule; add --map {seg[0]}/=<component> if it belongs to the release");
            plan.FileComponent[path] = id;
        }

        foreach (var id in plan.FileComponent.Values.Distinct())
            if (!plan.Components.ContainsKey(id)) plan.Components[id] = plan.Fixed(id, mods);

        plan.Link(mods, engines);
        foreach (var c in plan.Components.Values)
            if (versions.TryGetValue(c.Id, out var v)) c.Version = v;
        return plan;
    }

    ModMetadata ReadMetadata(IReadOnlyDictionary<string, string> sources, string folder)
    {
        if (sources.TryGetValue($"user/mods/{folder}/metadata.yml", out var file))
            return ModMetadata.Parse(File.ReadAllText(file), folder);
        Warnings.Add($"user/mods/{folder}: no metadata.yml, taken as a mod with id '{folder}'");
        return ModMetadata.Parse("", folder);
    }

    string ModComponent(ModMetadata meta)
    {
        var id = "mod." + meta.Id;
        if (!ManifestValidator.IsValidId(id)) throw new InvalidOperationException($"mod id '{meta.Id}' cannot name a component");
        if (!Components.ContainsKey(id))
            Components[id] = new ComponentInfo
            {
                Id = id, Mod = meta.Id, Name = meta.Name, Version = meta.Version, Engine = meta.Engine,
                Kind = meta.IsMaster ? ComponentKind.Master : meta.AnyMaster ? ComponentKind.Shared : ComponentKind.Addon,
                Master = meta.Master,
            };
        return id;
    }

    ComponentInfo Fixed(string id, Dictionary<string, ModMetadata> mods) => id switch
    {
        EngineId => new ComponentInfo { Id = id, Kind = ComponentKind.Engine, Name = "engine" },
        HdId => new ComponentInfo
        {
            Id = id, Kind = ComponentKind.Art, Name = "HD",
            Mod = mods.Values.Any(m => m.Id == HdModId) ? HdModId : "",
            Version = mods.Values.FirstOrDefault(m => m.Id == HdModId)?.Version ?? "",
            Engine = mods.Values.FirstOrDefault(m => m.Id == HdModId)?.Engine ?? "",
        },
        Hd18Id => new ComponentInfo { Id = id, Kind = ComponentKind.Art, Name = "HD 18+", Adult = true },
        _ => throw new InvalidOperationException($"--map names component '{id}' that no rule creates " +
                                                 $"(use engine, {HdId}, {Hd18Id} or mod.<id>)"),
    };

    void Link(Dictionary<string, ModMetadata> mods, IReadOnlyCollection<string> engines)
    {
        bool hasEngine = Components.ContainsKey(EngineId);
        foreach (var c in Components.Values)
        {
            if (c.Engine.Length > 0 && !engines.Contains(c.Engine))
                throw new InvalidOperationException(
                    $"{c.Id} requires engine '{c.Engine}', this line provides {string.Join(", ", engines.Select(e => $"'{e}'"))}");
            if (c.Kind != ComponentKind.Engine && hasEngine) c.Requires.Add(EngineId);
            if (c.Id == Hd18Id)
            {
                if (Components.ContainsKey(HdId)) c.Requires.Add(HdId);
                else Warnings.Add($"{Hd18Id} ships without {HdId}: the 18+ tree only holds files that differ from hd");
            }
            if (c.Kind == ComponentKind.Addon)
            {
                if (Components.ContainsKey("mod." + c.Master)) c.Requires.Add("mod." + c.Master);
                else if (c.Master is not ("xcom1" or "xcom2"))
                    Warnings.Add($"{c.Id}: its master '{c.Master}' is not in this release");
            }
        }
    }

    public void Count(IEnumerable<ManifestFile> files)
    {
        foreach (var c in Components.Values) { c.Size = 0; c.Files = 0; }
        foreach (var f in files)
        {
            var c = Components[f.Component];
            c.Size += f.Size;
            c.Files++;
        }
    }

    static bool Is(string a, string b) => a.Equals(b, StringComparison.OrdinalIgnoreCase);

    /// <summary>
    /// The 18+ tree needs only the files that differ from hd: HdSprites::artPath falls back to
    /// hd/ when hd_18+/ has no such file. Returns the paths of byte-identical copies.
    /// </summary>
    public static List<ManifestFile> Hd18Copies(IEnumerable<ManifestFile> files)
    {
        var byPath = files.ToDictionary(f => f.Path, StringComparer.OrdinalIgnoreCase);
        var copies = new List<ManifestFile>();
        foreach (var f in byPath.Values)
        {
            var seg = f.Path.Split('/');
            if (seg.Length < 5 || !Is(seg[3], Hd18Folder)) continue;
            seg[3] = HdFolder;
            if (byPath.TryGetValue(string.Join('/', seg), out var twin) && twin.Sha256 == f.Sha256) copies.Add(f);
        }
        return copies;
    }
}
