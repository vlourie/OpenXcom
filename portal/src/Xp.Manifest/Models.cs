using System.Text.Json.Serialization;

namespace Xp.Manifest;

/// <summary>
/// Signed description of one release: every managed file with its size and SHA-256.
/// Blobs are content-addressed: the object key of a file is <see cref="BlobKeys.For"/> of its hash.
/// </summary>
public sealed class ReleaseManifest
{
    /// <summary>2: components are a described list (engine, mods, art layers) instead of name -> version.</summary>
    public const int CurrentSchema = 2;

    public int Schema { get; set; } = CurrentSchema;
    public ReleaseInfo Release { get; set; } = new();
    /// <summary>What a player can pick from this release; every file belongs to exactly one of them.</summary>
    public List<ComponentInfo> Components { get; set; } = new();
    /// <summary>
    /// Where this release may write. "dir/" is a directory prefix, anything else is an exact
    /// top-level file. Every file and every delete must fall under a root.
    /// </summary>
    public List<string> Roots { get; set; } = new();
    public List<ManifestFile> Files { get; set; } = new();
    /// <summary>Managed deletions: files of the previous release that this one no longer ships.</summary>
    public List<string> Deletes { get; set; } = new();
}

public sealed class ReleaseInfo
{
    public string Id { get; set; } = "";
    public string Version { get; set; } = "";
    public string Channel { get; set; } = "";
    /// <summary>The engine line this release is for ("oxce", "oxce-hd"); see docs/portal/EDITIONS.md.</summary>
    public string Line { get; set; } = "";
    public DateTimeOffset Published { get; set; }
    /// <summary>Only for incompatibility or a critical vulnerability.</summary>
    public bool Mandatory { get; set; }
    public string MinLauncher { get; set; } = "0.0.0";
    /// <summary>Relative path of the executable the launcher starts; empty for launcher releases.</summary>
    public string Launch { get; set; } = "";
    /// <summary>Language code -> text.</summary>
    public Dictionary<string, string> Changelog { get; set; } = new();
}

public sealed class ManifestFile
{
    public string Path { get; set; } = "";
    public long Size { get; set; }
    public string Sha256 { get; set; } = "";
    public string Component { get; set; } = "";
}

public static class ComponentKind
{
    public const string Engine = "engine";
    /// <summary>A master mod (isMaster: true): a game of its own, a card in the launcher.</summary>
    public const string Master = "master";
    /// <summary>A mod bound to one master (master: piratez): shown only when that master is installed.</summary>
    public const string Addon = "addon";
    /// <summary>A mod for any master (master: "*").</summary>
    public const string Shared = "shared";
    /// <summary>An art layer: the hd/ and hd_18+/ trees of every mod.</summary>
    public const string Art = "art";
    /// <summary>The whole of a launcher release.</summary>
    public const string Launcher = "launcher";

    public static readonly string[] All = [Engine, Master, Addon, Shared, Art, Launcher];
}

public sealed class ComponentInfo
{
    public string Id { get; set; } = "";
    public string Kind { get; set; } = "";
    /// <summary>Mod id from metadata.yml, for mod components.</summary>
    public string Mod { get; set; } = "";
    public string Name { get; set; } = "";
    public string Version { get; set; } = "";
    /// <summary>For addons: the master mod id they belong to.</summary>
    public string Master { get; set; } = "";
    /// <summary>requiredExtendedEngine of the mod: "" any, "Extended" OXCE, "OXCE-HD" ours only.</summary>
    public string Engine { get; set; } = "";
    public List<string> Requires { get; set; } = new();
    /// <summary>Installed only after the player confirmed the age.</summary>
    public bool Adult { get; set; }
    public long Size { get; set; }
    public int Files { get; set; }
}

/// <summary>
/// Signed list of what can be downloaded at all: engine lines with their channels, and presets
/// (ready sets of components) shown as cards on first install. Read before any channel.
/// </summary>
public sealed class Catalog
{
    public const int CurrentSchema = 1;

    public int Schema { get; set; } = CurrentSchema;
    /// <summary>Only grows, like a channel pointer's: an older catalog is refused.</summary>
    public long Sequence { get; set; }
    public DateTimeOffset Updated { get; set; }
    public List<CatalogLine> Lines { get; set; } = new();
    public List<CatalogPreset> Presets { get; set; } = new();
}

public sealed class CatalogLine
{
    public string Id { get; set; } = "";
    /// <summary>What the line's exe answers to in requiredExtendedEngine: "Extended" for OXCE, "OXCE-HD" for ours.</summary>
    public string Engine { get; set; } = "";
    public Dictionary<string, string> Title { get; set; } = new();
    public List<string> Channels { get; set; } = new();
}

public sealed class CatalogPreset
{
    public string Id { get; set; } = "";
    public string Line { get; set; } = "";
    public Dictionary<string, string> Title { get; set; } = new();
    public Dictionary<string, string> Description { get; set; } = new();
    public List<string> Components { get; set; } = new();
}

/// <summary>
/// Signed pointer "channel -> release". The sequence only grows, so a replayed older pointer
/// (rollback attack) is refused by the launcher; revoking a release publishes a new pointer
/// with a higher sequence that names the previous release.
/// </summary>
public sealed class ChannelPointer
{
    /// <summary>The pointer format did not change with manifest schema 2.</summary>
    public const int CurrentSchema = 1;

    public int Schema { get; set; } = CurrentSchema;
    public string Channel { get; set; } = "";
    public long Sequence { get; set; }
    public string ReleaseId { get; set; } = "";
    public string ManifestSha256 { get; set; } = "";
    public long ManifestSize { get; set; }
    public DateTimeOffset Updated { get; set; }
}

/// <summary>Detached signature stored next to the signed file as "&lt;file&gt;.sig".</summary>
public sealed class SignatureFile
{
    public string Algorithm { get; set; } = "ed25519";
    public string KeyId { get; set; } = "";
    public string Signature { get; set; } = "";
}

[JsonSourceGenerationOptions(
    WriteIndented = false,
    PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase,
    DefaultIgnoreCondition = JsonIgnoreCondition.Never)]
[JsonSerializable(typeof(ReleaseManifest))]
[JsonSerializable(typeof(ChannelPointer))]
[JsonSerializable(typeof(Catalog))]
[JsonSerializable(typeof(SignatureFile))]
public sealed partial class ManifestJson : JsonSerializerContext
{
}
