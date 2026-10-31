using System.Globalization;
using System.Security.Cryptography;
using System.Text;

namespace Xp.Launcher.Core;

/// <summary>One colour of a game palette.</summary>
public readonly record struct Rgb(byte R, byte G, byte B);

/// <summary>A sprite set of the game: frames of palette indices, all the same size.</summary>
public sealed class SpriteSet(int width, int height, IReadOnlyList<byte[]?> frames)
{
    public int Width { get; } = width;
    public int Height { get; } = height;
    /// <summary>Width * Height palette indices per frame; null where the TAB points past the file.</summary>
    public IReadOnlyList<byte[]?> Frames { get; } = frames;
    public int Count => Frames.Count;
}

/// <summary>One MCD record: which sprite frames it uses and how the engine treats the tile.</summary>
public readonly record struct McdRecord(byte[] Frames, byte WalkCost, byte Type, sbyte TerrainLevel);

/// <summary>
/// Reads the game's own sprite files the way the engine reads them: PCK + TAB, the mod's palette,
/// and the terrain's MCD. The art pipeline (tools/hdart/xcom_sprites.py) reads them by the same
/// rules, and <see cref="Fingerprint"/> is the very key the census keys pictures by — so a verdict
/// from a player points at the same picture as our repainting queue.
/// </summary>
public static class Pck
{
    public const int FloorType = 0, WestWallType = 1, NorthWallType = 2, ObjectType = 3;
    const int McdRecordSize = 62, PaletteStride = 774;
    /// <summary>The battlescape palette the engine uses (PALETTES.DAT holds several).</summary>
    public const int BattlescapePalette = 4;

    // OpenXcom replaces the last 16 colours of the battlescape palette with a greyish gradient
    static readonly Rgb[] BattlescapeTail =
    [
        new(140, 152, 148), new(132, 136, 140), new(116, 124, 132), new(108, 116, 124),
        new(92, 104, 108), new(84, 92, 100), new(76, 80, 92), new(56, 68, 84),
        new(48, 56, 68), new(40, 48, 56), new(32, 36, 48), new(24, 28, 32),
        new(16, 20, 24), new(8, 12, 16), new(3, 4, 8), new(3, 3, 6),
    ];

    /// <summary>The sets whose frames are not the usual 32x40.</summary>
    public static (int Width, int Height) FrameSizeFor(string setName) =>
        Path.GetFileName(setName).ToUpperInvariant() switch
        {
            "X1.PCK" => (128, 64),
            "BIGOBS.PCK" => (32, 48),
            _ => (32, 40),
        };

    /// <summary>A file in a folder regardless of case: mods spell set names both ways.</summary>
    public static string? Find(string folder, string name)
    {
        var direct = Path.Combine(folder, name);
        if (File.Exists(direct)) return direct;
        if (!Directory.Exists(folder)) return null;
        foreach (var f in Directory.EnumerateFiles(folder))
            if (string.Equals(Path.GetFileName(f), name, StringComparison.OrdinalIgnoreCase))
                return f;
        return null;
    }

    /// <summary>Frame offsets from a TAB: 16-bit in UFO files, 32-bit in TFTD ones.</summary>
    public static IReadOnlyList<long> ReadTab(ReadOnlySpan<byte> tab)
    {
        var offsets = new List<long>();
        // the second entry's high word is zero only in the 32-bit form
        if (tab.Length >= 4 && tab[2] == 0 && tab[3] == 0)
        {
            for (var i = 0; i + 4 <= tab.Length; i += 4)
                offsets.Add((uint)(tab[i] | (tab[i + 1] << 8) | (tab[i + 2] << 16) | (tab[i + 3] << 24)));
        }
        else
        {
            for (var i = 0; i + 2 <= tab.Length; i += 2)
                offsets.Add(tab[i] | (tab[i + 1] << 8));
        }
        return offsets;
    }

    /// <summary>
    /// Decodes every frame of a PCK. No TAB means one frame. Frames are read one after another, the
    /// way SurfaceSet::loadPck does: the TAB gives only their number, its offsets are ignored. Some
    /// X-Piratez PCKs were rebuilt next to a stale TAB (BARN), and by the offsets their frames come
    /// out wrong or empty (docs/RAKES.md R-075).
    /// </summary>
    public static SpriteSet Decode(ReadOnlySpan<byte> pck, IReadOnlyList<long> offsets, int width, int height)
    {
        var frames = new List<byte[]?>(offsets.Count);
        var pos = 0;
        for (var n = 0; n < offsets.Count; n++)
        {
            if (pos >= pck.Length) { frames.Add(null); continue; }
            var pixels = new byte[width * height];
            var i = pck[pos] * width;                 // the first byte counts the empty rows on top
            pos++;
            while (pos < pck.Length)
            {
                var v = pck[pos];
                pos++;
                if (v == 0xFF) break;                 // end of frame
                if (v == 0xFE) { i += pck[pos]; pos++; continue; }   // a run of transparent pixels
                if (i < pixels.Length) pixels[i] = v;
                i++;
            }
            frames.Add(pixels);
        }
        return new SpriteSet(width, height, frames);
    }

    /// <summary>A set by its PCK; the TAB and the frame size are found next to it.</summary>
    public static SpriteSet ReadSet(string pckPath, string? tabPath = null)
    {
        var (w, h) = FrameSizeFor(pckPath);
        var pck = File.ReadAllBytes(pckPath);
        tabPath ??= Find(Path.GetDirectoryName(pckPath) ?? ".", Path.GetFileNameWithoutExtension(pckPath) + ".TAB");
        var offsets = tabPath is not null && File.Exists(tabPath)
            ? ReadTab(File.ReadAllBytes(tabPath))
            : [0L];
        return Decode(pck, offsets, w, h);
    }

    /// <summary>
    /// The picture's key: SHA-1 of the palette indices, first 12 hex characters. The same value the
    /// census writes in census/frames.tsv, so verdicts and the repainting queue speak of one picture.
    /// </summary>
    public static string Fingerprint(ReadOnlySpan<byte> frame) =>
        Convert.ToHexStringLower(SHA1.HashData(frame))[..12];

    public static bool IsEmpty(ReadOnlySpan<byte> frame)
    {
        foreach (var v in frame) if (v != 0) return false;
        return true;
    }

    /// <summary>The terrain's MCD records: byte 39 the walking cost (255 = impassable), 48 the terrain level, 53 the tile type.</summary>
    public static IReadOnlyList<McdRecord> ReadMcd(string path)
    {
        var data = File.ReadAllBytes(path);
        var records = new List<McdRecord>(data.Length / McdRecordSize);
        for (var i = 0; i + McdRecordSize <= data.Length; i += McdRecordSize)
            records.Add(new McdRecord(data[i..(i + 8)], data[i + 39], data[i + 53], (sbyte)data[i + 48]));
        return records;
    }

    /// <summary>
    /// Per sprite frame: the tile type, whether one may walk on it and whether it is raised.
    /// Type -1 means no record uses the frame at all — the game never draws it, so nobody should
    /// be asked to review it. A frame used by several records gets the lowest type (floor wins).
    /// </summary>
    public static (int[] Types, bool[] Walkable, bool[] Raised) FrameTypes(IReadOnlyList<McdRecord> records, int count)
    {
        var types = new int[count];
        var walkable = new bool[count];
        var raised = new bool[count];
        Array.Fill(types, -1);
        Array.Fill(walkable, true);
        foreach (var rec in records)
            foreach (var fr in rec.Frames)
                if (fr < count && (types[fr] < 0 || rec.Type < types[fr]))
                {
                    types[fr] = rec.Type;
                    walkable[fr] = rec.WalkCost != 255;
                    raised[fr] = rec.TerrainLevel != 0;
                }
        return (types, walkable, raised);
    }

    /// <summary>How much of the floor diamond (the bottom 32x16 of a tile) the frame covers.</summary>
    public static double DiamondCoverage(ReadOnlySpan<byte> frame, int width, int height)
    {
        int inside = 0, drawn = 0;
        for (var y = height - 16; y < height; y++)
            for (var x = 0; x < width; x++)
            {
                if (Math.Abs(x - (width - 1) / 2.0) / (width / 2.0) + Math.Abs(y - (height - 8.5)) / 8.0 > 1) continue;
                inside++;
                if (frame[y * width + x] != 0) drawn++;
            }
        return inside == 0 ? 0.0 : (double)drawn / inside;
    }

    /// <summary>
    /// Which frames are a continuous field (a floor, or a walkable object filling the floor diamond)
    /// rather than a thing standing on one, and which stand on a full ground diamond of their own
    /// (a tree on grass). The same rule as extract_pck.ground_flags in the art pipeline: the review
    /// must lay a floor out exactly as the pipeline painted it.
    /// </summary>
    public static (bool[] Ground, bool[] Base) GroundFlags(SpriteSet set, int[] types, bool[] walkable, bool[] raised)
    {
        var ground = new bool[set.Count];
        var onDiamond = new bool[set.Count];
        if ((set.Width, set.Height) != (32, 40)) return (ground, onDiamond);
        for (var i = 0; i < set.Count; i++)
        {
            var frame = set.Frames[i];
            if (frame is null) continue;
            var top = set.Height;
            for (var y = 0; y < set.Height && top == set.Height; y++)
                for (var x = 0; x < set.Width; x++)
                    if (frame[y * set.Width + x] != 0) { top = y; break; }
            var coverage = DiamondCoverage(frame, set.Width, set.Height);
            // flat only: slopes, stairs and hay bales (terrain level != 0) are objects, not a field
            ground[i] = !raised[i] && ((types[i] == FloorType && top >= set.Height - 16 - 8) ||
                                       (types[i] == ObjectType && walkable[i] && coverage >= 0.85));
            onDiamond[i] = !ground[i] && types[i] is FloorType or ObjectType && coverage >= 0.85;
        }
        return (ground, onDiamond);
    }

    /// <summary>The battlescape palette from GEODATA/PALETTES.DAT, where the channels are six-bit.</summary>
    public static Rgb[] LoadPalette(string palettesDat, int index = BattlescapePalette, bool battlescapeFix = true)
    {
        using var f = File.OpenRead(palettesDat);
        f.Seek((long)PaletteStride * index, SeekOrigin.Begin);
        var raw = new byte[768];
        f.ReadExactly(raw);
        var pal = new Rgb[256];
        for (var i = 0; i < 256; i++)
            pal[i] = new Rgb((byte)(raw[i * 3] * 4), (byte)(raw[i * 3 + 1] * 4), (byte)(raw[i * 3 + 2] * 4));
        if (battlescapeFix && index == BattlescapePalette) ApplyBattlescapeTail(pal);
        return pal;
    }

    /// <summary>
    /// A mod's own palette file. OXCE mods keep it beside their resources instead of PALETTES.DAT,
    /// and its values are full bytes, not the six-bit ones of PALETTES.DAT: mixing the two up makes
    /// everything exactly four times too dark, or overflows.
    /// </summary>
    public static Rgb[] LoadPaletteFile(string path, bool battlescapeFix = false)
    {
        var raw = File.ReadAllBytes(path);
        var head = Encoding.ASCII.GetString(raw, 0, Math.Min(16, raw.Length)).TrimStart().ToUpperInvariant();
        var pal = new List<Rgb>(256);

        if (head.StartsWith("JASC-PAL", StringComparison.Ordinal))
        {
            var lines = Encoding.ASCII.GetString(raw).Split('\n');
            // JASC-PAL / 0100 / <how many> / then "r g b" per line
            var want = int.Parse(lines[2].Trim(), CultureInfo.InvariantCulture);
            for (var i = 3; i < lines.Length && pal.Count < want; i++)
                if (TryColour(lines[i], out var c)) pal.Add(c);
            if (pal.Count != want)
                throw new InvalidDataException($"{path}: claims {want} colours, read {pal.Count}");
        }
        else if (head.StartsWith("GIMP PALETTE", StringComparison.Ordinal))
        {
            foreach (var line in Encoding.ASCII.GetString(raw).Split('\n'))
            {
                var t = line.Trim();
                if (t.Length == 0 || t[0] == '#' || char.IsLetter(t[0])) continue;
                if (TryColour(t, out var c)) pal.Add(c);
            }
        }
        else if (raw.Length == 768)
        {
            for (var i = 0; i < 256; i++) pal.Add(new Rgb(raw[i * 3], raw[i * 3 + 1], raw[i * 3 + 2]));
        }
        else
        {
            throw new InvalidDataException($"{path}: neither JASC-PAL, nor GIMP, nor 768 bytes ({raw.Length} bytes)");
        }

        while (pal.Count < 256) pal.Add(new Rgb(0, 0, 0));
        var result = pal.GetRange(0, 256).ToArray();
        if (battlescapeFix) ApplyBattlescapeTail(result);
        return result;
    }

    static void ApplyBattlescapeTail(Rgb[] pal)
    {
        for (var i = 0; i < BattlescapeTail.Length; i++) pal[224 + 16 + i] = BattlescapeTail[i];
    }

    static bool TryColour(string line, out Rgb colour)
    {
        colour = default;
        var parts = line.Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries);
        if (parts.Length < 3) return false;
        if (!byte.TryParse(parts[0], out var r) || !byte.TryParse(parts[1], out var g) || !byte.TryParse(parts[2], out var b))
            return false;
        colour = new Rgb(r, g, b);
        return true;
    }

    /// <summary>A frame as RGBA bytes, index 0 transparent — the engine's own rule (see rake R-043).</summary>
    public static byte[] ToRgba(ReadOnlySpan<byte> frame, Rgb[] palette)
    {
        var rgba = new byte[frame.Length * 4];
        for (var i = 0; i < frame.Length; i++)
        {
            var idx = frame[i];
            if (idx == 0) continue;
            var c = palette[idx];
            rgba[i * 4] = c.R;
            rgba[i * 4 + 1] = c.G;
            rgba[i * 4 + 2] = c.B;
            rgba[i * 4 + 3] = 255;
        }
        return rgba;
    }
}
