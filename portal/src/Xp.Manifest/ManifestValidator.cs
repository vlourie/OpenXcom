using System.Text.Json;
using System.Text.RegularExpressions;

namespace Xp.Manifest;

/// <summary>Structural checks done after the signature: a signed manifest is still validated.</summary>
public static partial class ManifestValidator
{
    /// <summary>Hard upper bound on a single file; a manifest asking for more is refused.</summary>
    public const long MaxFileSize = 4L << 30;
    public const int MaxFiles = 500_000;

    [GeneratedRegex(@"^[A-Za-z0-9][A-Za-z0-9._\-]{0,63}$")]
    private static partial Regex IdRegex();

    public static bool IsValidId(string? s) => s is not null && IdRegex().IsMatch(s) && !s.Contains("..");

    public static ReleaseManifest Parse(ReadOnlySpan<byte> json)
    {
        ReleaseManifest? m;
        try { m = JsonSerializer.Deserialize(json, ManifestJson.Default.ReleaseManifest); }
        catch (JsonException e) { throw new ManifestException("manifest is not valid JSON: " + e.Message); }
        if (m is null) throw new ManifestException("empty manifest");
        Validate(m);
        return m;
    }

    public static ChannelPointer ParsePointer(ReadOnlySpan<byte> json)
    {
        ChannelPointer? p;
        try { p = JsonSerializer.Deserialize(json, ManifestJson.Default.ChannelPointer); }
        catch (JsonException e) { throw new ManifestException("channel pointer is not valid JSON: " + e.Message); }
        if (p is null) throw new ManifestException("empty channel pointer");
        if (p.Schema != ReleaseManifest.CurrentSchema) throw new ManifestException($"unsupported schema {p.Schema}");
        if (!IsValidId(p.Channel) || !IsValidId(p.ReleaseId)) throw new ManifestException("bad channel or release id");
        if (!Hashing.IsSha256Hex(p.ManifestSha256) || p.ManifestSize <= 0) throw new ManifestException("bad manifest reference");
        return p;
    }

    public static void Validate(ReleaseManifest m)
    {
        if (m.Schema != ReleaseManifest.CurrentSchema) throw new ManifestException($"unsupported schema {m.Schema}");
        if (!IsValidId(m.Release.Id)) throw new ManifestException("bad release id");
        if (!IsValidId(m.Release.Channel)) throw new ManifestException("bad channel");
        if (!Version.TryParse(m.Release.MinLauncher, out _)) throw new ManifestException("bad minLauncher");
        if (m.Roots.Count == 0) throw new ManifestException("no roots");
        foreach (var r in m.Roots)
            if (SafePath.ValidateRoot(r) is { } why) throw new ManifestException($"bad root '{r}': {why}");
        if (m.Files.Count > MaxFiles) throw new ManifestException("too many files");
        if (m.Release.Launch.Length > 0)
        {
            if (SafePath.Validate(m.Release.Launch) is { } why) throw new ManifestException($"bad launch path: {why}");
            if (!m.Release.Launch.EndsWith(".exe", StringComparison.OrdinalIgnoreCase)) throw new ManifestException("launch is not an .exe");
            if (!m.Files.Any(f => string.Equals(f.Path, m.Release.Launch, StringComparison.OrdinalIgnoreCase)))
                throw new ManifestException("launch target is not a managed file");
        }

        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var f in m.Files)
        {
            if (SafePath.Validate(f.Path) is { } why) throw new ManifestException($"bad path '{f.Path}': {why}");
            if (!SafePath.UnderAnyRoot(f.Path, m.Roots)) throw new ManifestException($"'{f.Path}' is outside the roots");
            if (!seen.Add(f.Path)) throw new ManifestException($"duplicate path '{f.Path}'");
            if (f.Size < 0 || f.Size > MaxFileSize) throw new ManifestException($"bad size for '{f.Path}'");
            if (!Hashing.IsSha256Hex(f.Sha256)) throw new ManifestException($"bad sha256 for '{f.Path}'");
        }
        foreach (var d in m.Deletes)
        {
            if (SafePath.Validate(d) is { } why) throw new ManifestException($"bad delete '{d}': {why}");
            if (!SafePath.UnderAnyRoot(d, m.Roots)) throw new ManifestException($"delete '{d}' is outside the roots");
            if (seen.Contains(d)) throw new ManifestException($"'{d}' is both shipped and deleted");
        }
    }
}

public sealed class ManifestException(string message) : Exception(message);
