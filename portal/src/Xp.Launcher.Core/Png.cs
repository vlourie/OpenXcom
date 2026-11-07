using System.Buffers.Binary;
using System.IO.Compression;

namespace Xp.Launcher.Core;

/// <summary>
/// A PNG decoder, just enough for the frames of an HD pack. The launcher has to look at those
/// pixels — to lay a floor out as a field and to measure how far the colour went — and it may not
/// pull in an image library: it publishes AOT and its core stays free of the interface.
/// Eight bits per channel, no interlacing; anything else is refused by name rather than guessed at.
/// </summary>
public static class Png
{
    static ReadOnlySpan<byte> Signature => [0x89, (byte)'P', (byte)'N', (byte)'G', 0x0D, 0x0A, 0x1A, 0x0A];

    /// <summary>Width, height and the pixels as RGBA, row by row, top row first.</summary>
    public static (int Width, int Height, byte[] Rgba) Decode(ReadOnlySpan<byte> png)
    {
        if (png.Length < 8 || !png[..8].SequenceEqual(Signature)) throw new PngException("not a PNG file");

        int width = 0, height = 0, bitDepth = 0, colorType = -1;
        byte[]? palette = null, alpha = null;
        var idat = new MemoryStream();
        var at = 8;
        while (at + 8 <= png.Length)
        {
            var length = BinaryPrimitives.ReadInt32BigEndian(png[at..]);
            if (length < 0 || at + 12 + length > png.Length) throw new PngException("a chunk runs past the end of the file");
            var type = System.Text.Encoding.ASCII.GetString(png.Slice(at + 4, 4));
            var body = png.Slice(at + 8, length);
            switch (type)
            {
                case "IHDR":
                    if (length < 13) throw new PngException("IHDR is too short");
                    width = BinaryPrimitives.ReadInt32BigEndian(body);
                    height = BinaryPrimitives.ReadInt32BigEndian(body[4..]);
                    bitDepth = body[8];
                    colorType = body[9];
                    if (body[12] != 0) throw new PngException("an interlaced PNG is not read here");
                    if (bitDepth != 8) throw new PngException($"{bitDepth} bits per channel: only 8 are read here");
                    if (width <= 0 || height <= 0 || (long)width * height > 64_000_000) throw new PngException($"suspicious size {width}x{height}");
                    break;
                case "PLTE": palette = body.ToArray(); break;
                case "tRNS": alpha = body.ToArray(); break;
                case "IDAT": idat.Write(body); break;
                case "IEND": at = png.Length; break;
            }
            at += 12 + length;
        }
        if (colorType < 0) throw new PngException("the file has no IHDR");

        var channels = colorType switch
        {
            0 => 1, 2 => 3, 3 => 1, 4 => 2, 6 => 4,
            _ => throw new PngException($"colour type {colorType} is not read here"),
        };
        if (colorType == 3 && palette is null) throw new PngException("an indexed PNG without a palette");

        idat.Position = 0;
        var stride = width * channels;
        if ((long)stride * height > int.MaxValue) throw new PngException("the image is too large");
        var raw = new byte[stride * height];
        Inflate(idat, raw, stride, height, channels);

        var rgba = new byte[width * height * 4];
        for (var i = 0; i < width * height; i++)
        {
            var s = i * channels;
            var d = i * 4;
            switch (colorType)
            {
                case 0:                                   // grey
                    rgba[d] = rgba[d + 1] = rgba[d + 2] = raw[s];
                    rgba[d + 3] = 255;
                    break;
                case 2:                                   // RGB
                    rgba[d] = raw[s]; rgba[d + 1] = raw[s + 1]; rgba[d + 2] = raw[s + 2];
                    rgba[d + 3] = 255;
                    break;
                case 3:                                   // indexed
                    var idx = raw[s];
                    if (idx * 3 + 2 >= palette!.Length) throw new PngException("an index points outside the palette");
                    rgba[d] = palette[idx * 3]; rgba[d + 1] = palette[idx * 3 + 1]; rgba[d + 2] = palette[idx * 3 + 2];
                    rgba[d + 3] = alpha is not null && idx < alpha.Length ? alpha[idx] : (byte)255;
                    break;
                case 4:                                   // grey + alpha
                    rgba[d] = rgba[d + 1] = rgba[d + 2] = raw[s];
                    rgba[d + 3] = raw[s + 1];
                    break;
                default:                                  // RGBA
                    rgba[d] = raw[s]; rgba[d + 1] = raw[s + 1]; rgba[d + 2] = raw[s + 2]; rgba[d + 3] = raw[s + 3];
                    break;
            }
        }
        return (width, height, rgba);
    }

    /// <summary>Unpack the image data and undo the per-row filter (PNG specification, 9. Filtering).</summary>
    static void Inflate(Stream deflated, byte[] raw, int stride, int height, int channels)
    {
        using var z = new ZLibStream(deflated, CompressionMode.Decompress);
        var line = new byte[stride + 1];
        var previous = new byte[stride];
        for (var y = 0; y < height; y++)
        {
            z.ReadExactly(line);
            var filter = line[0];
            var row = raw.AsSpan(y * stride, stride);
            line.AsSpan(1).CopyTo(row);
            for (var x = 0; x < stride; x++)
            {
                int a = x >= channels ? row[x - channels] : 0, b = previous[x], c = x >= channels ? previous[x - channels] : 0;
                row[x] = filter switch
                {
                    0 => row[x],
                    1 => (byte)(row[x] + a),
                    2 => (byte)(row[x] + b),
                    3 => (byte)(row[x] + (a + b) / 2),
                    4 => (byte)(row[x] + Paeth(a, b, c)),
                    _ => throw new PngException($"row filter {filter} is unknown"),
                };
            }
            row.CopyTo(previous);
        }
    }

    static int Paeth(int a, int b, int c)
    {
        int p = a + b - c, pa = Math.Abs(p - a), pb = Math.Abs(p - b), pc = Math.Abs(p - c);
        return pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
    }
}

public sealed class PngException(string message) : Exception(message);
