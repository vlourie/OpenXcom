using System.Formats.Tar;
using System.IO.Compression;
using System.Security.Cryptography;
using Xp.Manifest;

namespace Xp.Launcher.Core;

/// <summary>An update pack (<see cref="UpdatePack"/>): a brotli tar of blobs named by their SHA-256. Read by the game's updates and the launcher's own.</summary>
public static class PackReader
{
    /// <summary>
    /// Unpacks the blobs named in <paramref name="sizes"/> to <paramref name="blobPath"/>, each checked against its own
    /// SHA-256 and the size the manifest gives; a blob not wanted, or already there, is skipped. Returns how many were written.
    /// </summary>
    public static int Unpack(string file, IReadOnlyDictionary<string, long> sizes, Func<string, string> blobPath, Action<string>? unpacked, CancellationToken ct)
    {
        int got = 0;
        var buf = new byte[1 << 16];
        using var fs = new FileStream(file, FileMode.Open, FileAccess.Read, FileShare.Read, 1 << 20);
        using var br = new BrotliStream(fs, CompressionMode.Decompress);
        using var tar = new TarReader(br);
        while (tar.GetNextEntry() is { } e)
        {
            ct.ThrowIfCancellationRequested();
            if (e.EntryType is not (TarEntryType.RegularFile or TarEntryType.V7RegularFile) || !Hashing.IsSha256Hex(e.Name))
                throw new TrustException($"pack: unexpected entry '{e.Name}'");
            var target = blobPath(e.Name);
            if (!sizes.TryGetValue(e.Name, out var size) || File.Exists(target)) continue;
            if (e.Length != size) throw new TrustException($"pack: {e.Name[..12]} is not the size the manifest gives");
            var tmp = target + ".unpack";
            using var sha = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
            using (var output = new FileStream(tmp, FileMode.Create, FileAccess.Write, FileShare.None, 1 << 16))
                if (e.DataStream is { } data)
                    for (int n; (n = data.Read(buf)) > 0;) { output.Write(buf, 0, n); sha.AppendData(buf, 0, n); }
            if (Convert.ToHexStringLower(sha.GetHashAndReset()) != e.Name)
            {
                File.Delete(tmp);
                throw new TrustException($"pack: {e.Name[..12]} does not match its hash");
            }
            File.Move(tmp, target, overwrite: true);
            unpacked?.Invoke(e.Name);
            got++;
        }
        return got;
    }
}
