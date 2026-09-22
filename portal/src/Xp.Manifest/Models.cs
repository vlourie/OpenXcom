using System.Text.Json.Serialization;

namespace Xp.Manifest;

/// <summary>
/// Signed description of one release: every managed file with its size and SHA-256.
/// Blobs are content-addressed: the object key of a file is <see cref="BlobKeys.For"/> of its hash.
/// </summary>
public sealed class ReleaseManifest
{
    public const int CurrentSchema = 1;

    public int Schema { get; set; } = CurrentSchema;
    public ReleaseInfo Release { get; set; } = new();
    /// <summary>Component name -> human readable version (engine commit, mod stamp).</summary>
    public Dictionary<string, string> Components { get; set; } = new();
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

/// <summary>
/// Signed pointer "channel -> release". The sequence only grows, so a replayed older pointer
/// (rollback attack) is refused by the launcher; revoking a release publishes a new pointer
/// with a higher sequence that names the previous release.
/// </summary>
public sealed class ChannelPointer
{
    public int Schema { get; set; } = ReleaseManifest.CurrentSchema;
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
[JsonSerializable(typeof(SignatureFile))]
public sealed partial class ManifestJson : JsonSerializerContext
{
}
