using System.Security.Cryptography;

namespace Xp.Manifest;

public static class Hashing
{
    const int BufferSize = 1 << 20;

    public static string Sha256Hex(ReadOnlySpan<byte> data) => Convert.ToHexStringLower(SHA256.HashData(data));

    public static string FileSha256(string path)
    {
        using var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read, BufferSize, FileOptions.SequentialScan);
        return Convert.ToHexStringLower(SHA256.HashData(fs));
    }

    public static async Task<string> FileSha256Async(string path, CancellationToken ct = default)
    {
        await using var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read, BufferSize, FileOptions.SequentialScan | FileOptions.Asynchronous);
        return Convert.ToHexStringLower(await SHA256.HashDataAsync(fs, ct));
    }

    public static bool IsSha256Hex(string? s) =>
        s is { Length: 64 } && s.All(c => c is >= '0' and <= '9' or >= 'a' and <= 'f');
}

/// <summary>Object keys in the release repository (a static tree, served as-is).</summary>
public static class BlobKeys
{
    public static string For(string sha256) => $"blobs/sha256/{sha256[..2]}/{sha256}";
    public static string Channel(string channel) => $"channels/{channel}.json";
    /// <summary>History and roadmap of a channel (<see cref="ChannelNotes"/>), signed like the pointer beside it.</summary>
    public static string Notes(string channel) => $"channels/{channel}.notes.json";
    public static string Manifest(string releaseId) => $"releases/{releaseId}/manifest.json";
    /// <summary>The update from <paramref name="from"/> to <paramref name="releaseId"/> in one file (<see cref="UpdatePack"/>).</summary>
    public static string Pack(string releaseId, string from) => $"releases/{releaseId}/packs/{from}.tar.br";
    public static string Sig(string key) => key + ".sig";
    public const string Catalog = "catalog.json";
}
