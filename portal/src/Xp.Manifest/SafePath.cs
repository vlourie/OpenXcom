namespace Xp.Manifest;

/// <summary>
/// Rules for relative paths coming from a manifest. Nothing from the network may leave the
/// game directory: no absolute, UNC or drive paths, no "..", no Windows device names.
/// Paths use '/' and are compared case-insensitively, like the file system they land on.
/// </summary>
public static class SafePath
{
    public const int MaxLength = 240;

    static readonly HashSet<string> Devices = new(StringComparer.OrdinalIgnoreCase)
    {
        "CON", "PRN", "AUX", "NUL", "CLOCK$", "CONIN$", "CONOUT$",
        "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
        "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
        "COM¹", "COM²", "COM³", "LPT¹", "LPT²", "LPT³",
    };

    const string BadChars = "<>:\"|?*\\";

    public static bool IsValid(string? path) => Validate(path) is null;

    /// <summary>Returns null when the path is acceptable, otherwise the reason.</summary>
    public static string? Validate(string? path)
    {
        if (string.IsNullOrEmpty(path)) return "empty path";
        if (path.Length > MaxLength) return "path too long";
        if (path[0] == '/') return "absolute path";
        foreach (char c in path)
        {
            if (c < 0x20 || c == 0x7f) return "control character";
            if (BadChars.Contains(c)) return $"forbidden character '{c}'";
        }
        foreach (var seg in path.Split('/'))
        {
            if (seg.Length == 0) return "empty segment";
            if (seg == "." || seg == "..") return "dot segment";
            if (seg.EndsWith('.') || seg.EndsWith(' ') || seg.StartsWith(' ')) return "segment ends with dot or space";
            int dot = seg.IndexOf('.');
            var stem = dot < 0 ? seg : seg[..dot];
            if (Devices.Contains(stem.TrimEnd(' '))) return "device name";
        }
        return null;
    }

    /// <summary>Same as <see cref="Validate"/> for a root: a directory root ends with '/'.</summary>
    public static string? ValidateRoot(string? root)
    {
        if (string.IsNullOrEmpty(root)) return "empty root";
        var body = root.EndsWith('/') ? root[..^1] : root;
        return Validate(body);
    }

    public static bool UnderRoot(string path, string root) =>
        root.EndsWith('/')
            ? path.StartsWith(root, StringComparison.OrdinalIgnoreCase)
            : string.Equals(path, root, StringComparison.OrdinalIgnoreCase);

    public static bool UnderAnyRoot(string path, IEnumerable<string> roots) =>
        roots.Any(r => UnderRoot(path, r));

    /// <summary>
    /// Full local path for a validated relative path. Throws if, after normalisation,
    /// it does not lie strictly inside <paramref name="baseDir"/> (second line of defence).
    /// </summary>
    public static string Resolve(string baseDir, string relative)
    {
        var reason = Validate(relative);
        if (reason is not null) throw new UnsafePathException(relative, reason);
        var root = Path.GetFullPath(baseDir);
        if (!root.EndsWith(Path.DirectorySeparatorChar)) root += Path.DirectorySeparatorChar;
        var full = Path.GetFullPath(Path.Combine(root, relative.Replace('/', Path.DirectorySeparatorChar)));
        if (!full.StartsWith(root, StringComparison.OrdinalIgnoreCase))
            throw new UnsafePathException(relative, "escapes the base directory");
        return full;
    }

    /// <summary>Relative '/'-path of a file under a base directory.</summary>
    public static string ToRelative(string baseDir, string fullPath) =>
        Path.GetRelativePath(baseDir, fullPath).Replace('\\', '/');
}

public sealed class UnsafePathException(string path, string reason)
    : Exception($"unsafe path '{path}': {reason}")
{
    public string PathValue { get; } = path;
    public string Reason { get; } = reason;
}
