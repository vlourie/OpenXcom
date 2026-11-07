using System.Formats.Tar;
using System.IO.Compression;

namespace Xp.Manifest;

/// <summary>
/// An update pack (<see cref="UpdatePack"/>): blobs as tar entries named by their SHA-256, in one brotli stream.
/// The release builder writes them from its recent releases; the site writes the same for any other release on request.
/// </summary>
public static class PackWriter
{
    /// <summary>Each blob once, like files next to like: brotli finds the repeats of one kind (rul with rul, exe alone).</summary>
    public static List<ManifestFile> Order(IEnumerable<ManifestFile> files) =>
        files.DistinctBy(f => f.Sha256)
            .OrderBy(f => Path.GetExtension(f.Path), StringComparer.OrdinalIgnoreCase).ThenBy(f => f.Path, StringComparer.Ordinal)
            .ToList();

    /// <summary>
    /// Writes <paramref name="blobs"/> (already <see cref="Order"/>ed) to <paramref name="target"/>: through
    /// &lt;target&gt;.tmp, so the name appears only for a whole pack. <paramref name="blobPath"/> finds a blob by its hash.
    /// </summary>
    public static UpdatePack Write(string from, IReadOnlyList<ManifestFile> blobs, Func<string, string> blobPath, string target, int quality, CancellationToken ct = default)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(target)!);
        var tmp = target + ".tmp";
        using (var fs = new FileStream(tmp, FileMode.Create, FileAccess.Write, FileShare.None, 1 << 20))
        using (var br = new BrotliStream(fs, new BrotliCompressionOptions { Quality = quality }))
        using (var tar = new TarWriter(br, TarEntryFormat.Ustar, leaveOpen: false))
            foreach (var f in blobs)
            {
                ct.ThrowIfCancellationRequested();
                using var data = File.OpenRead(blobPath(f.Sha256));
                tar.WriteEntry(new UstarTarEntry(TarEntryType.RegularFile, f.Sha256) { DataStream = data });
            }
        File.Move(tmp, target, overwrite: true);
        return new UpdatePack { From = from, Size = new FileInfo(target).Length, Sha256 = Hashing.FileSha256(target), Blobs = blobs.Count, Raw = blobs.Sum(f => f.Size) };
    }
}
