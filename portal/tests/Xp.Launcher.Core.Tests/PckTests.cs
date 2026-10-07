using System.Text;
using Xp.Launcher.Core;
using Xunit.Abstractions;

namespace Xp.Launcher.Core.Tests;

/// <summary>
/// Reading the game's sprites must give exactly what the art pipeline reads in python — otherwise a
/// player's verdict would point at a different picture than our repainting queue. The last two tests
/// prove it on the real installation: they run only where the game is installed (a build machine
/// without it says so in the output instead of failing).
/// </summary>
public sealed class PckTests(ITestOutputHelper output)
{
    [Fact]
    public void Tab_offsets_are_read_as_16_bit_in_ufo_files()
    {
        // 0x0000, 0x0500, 0x0A00 — the second entry's high byte is not zero, so these are 16-bit
        var tab = new byte[] { 0, 0, 0x05, 0x01, 0x0A, 0x02 };
        Assert.Equal([0L, 0x0105L, 0x020AL], Pck.ReadTab(tab));
    }

    [Fact]
    public void Tab_offsets_are_read_as_32_bit_in_tftd_files()
    {
        var tab = new byte[] { 0, 0, 0, 0, 0x20, 0x03, 0, 0 };
        Assert.Equal([0L, 0x0320L], Pck.ReadTab(tab));
    }

    [Fact]
    public void Rle_decoding_follows_the_engine()
    {
        // two empty rows, then: one pixel 7, skip 3, two pixels 9 and 11, end of frame
        var pck = new byte[] { 2, 7, 0xFE, 3, 9, 11, 0xFF };
        var set = Pck.Decode(pck, [0L], 4, 4);
        var frame = set.Frames[0]!;
        Assert.Equal(7, frame[8]);            // row 2, column 0
        Assert.Equal(0, frame[9]);            // the three skipped ones stay transparent
        Assert.Equal(0, frame[11]);
        Assert.Equal(9, frame[12]);
        Assert.Equal(11, frame[13]);
        Assert.Equal(13, frame.Count(v => v == 0));   // 16 pixels, 3 of them painted
    }

    [Fact]
    public void A_frame_whose_offset_is_past_the_file_is_missing_rather_than_empty()
    {
        var set = Pck.Decode(new byte[] { 0, 5, 0xFF }, [0L, 99L], 2, 2);
        Assert.NotNull(set.Frames[0]);
        Assert.Null(set.Frames[1]);
    }

    [Fact]
    public void Palettes_dat_channels_are_six_bit_and_mod_palettes_are_not()
    {
        var dir = Directory.CreateTempSubdirectory("xp-pal").FullName;
        try
        {
            // PALETTES.DAT: the battlescape palette is the fifth, channels 0..63 to be multiplied by 4
            var dat = new byte[774 * 5];
            dat[774 * 4 + 3] = 10;
            dat[774 * 4 + 4] = 20;
            dat[774 * 4 + 5] = 30;
            var datPath = Path.Combine(dir, "PALETTES.DAT");
            File.WriteAllBytes(datPath, dat);
            Assert.Equal(new Rgb(40, 80, 120), Pck.LoadPalette(datPath, battlescapeFix: false)[1]);

            var jasc = Path.Combine(dir, "mod.pal");
            File.WriteAllText(jasc, "JASC-PAL\n0100\n2\n0 0 0\n40 80 120\n", Encoding.ASCII);
            Assert.Equal(new Rgb(40, 80, 120), Pck.LoadPaletteFile(jasc)[1]);

            // the engine replaces the tail of the battlescape palette with its own greys
            Assert.Equal(new Rgb(3, 3, 6), Pck.LoadPaletteFile(jasc, battlescapeFix: true)[255]);
        }
        finally { Directory.Delete(dir, recursive: true); }
    }

    [Fact]
    public void Index_zero_stays_transparent()
    {
        var palette = new Rgb[256];
        palette[0] = new Rgb(255, 0, 255);        // the vanilla palette really is magenta at 0
        palette[1] = new Rgb(10, 20, 30);
        var rgba = Pck.ToRgba(new byte[] { 0, 1 }, palette);
        Assert.Equal(0, rgba[3]);
        Assert.Equal([10, 20, 30, 255], rgba[4..8]);
    }

    [Fact]
    public void Frames_match_the_census_fingerprints()
    {
        var repo = RepoRoot();
        var census = repo is null ? null : Path.Combine(repo, "census", "frames.tsv");
        var terrain = repo is null ? null : Path.Combine(repo, "Пиратки", "Dioxine_XPiratez", "user", "mods", "Piratez", "TERRAIN");
        if (census is null || !File.Exists(census) || terrain is null || !Directory.Exists(terrain))
        {
            output.WriteLine("the game is not installed here: nothing to compare against");
            return;
        }

        var want = new Dictionary<(string Set, int Frame), string>();
        using (var reader = new StreamReader(census, new UTF8Encoding(false)))
        {
            var header = (reader.ReadLine() ?? "").TrimStart('﻿').Split('\t');
            int section = Array.IndexOf(header, "раздел"), set = Array.IndexOf(header, "набор"),
                frame = Array.IndexOf(header, "кадр"), exact = Array.IndexOf(header, "точный");
            Assert.True(section >= 0 && set >= 0 && frame >= 0 && exact >= 0, "census/frames.tsv has lost its columns");
            while (reader.ReadLine() is { } line)
            {
                var c = line.Split('\t');
                if (c.Length <= exact || c[section] != "TERRAIN") continue;
                // set names in a mod are written any which way (Nuke1, beds): compare without case
                want[(c[set].ToUpperInvariant(), int.Parse(c[frame]))] = c[exact];
            }
        }

        int checked_ = 0, missing = 0;
        var wrong = new List<string>();
        foreach (var pck in Directory.EnumerateFiles(terrain, "*.PCK"))
        {
            var name = Path.GetFileNameWithoutExtension(pck).ToUpperInvariant();
            var sprites = Pck.ReadSet(pck);
            for (var i = 0; i < sprites.Count; i++)
            {
                var frame = sprites.Frames[i];
                if (frame is null || Pck.IsEmpty(frame)) continue;
                if (!want.TryGetValue((name, i), out var expected)) { missing++; continue; }
                var got = Pck.Fingerprint(frame);
                if (got != expected && wrong.Count < 10) wrong.Add($"{name} #{i}: {got} instead of {expected}");
                if (got == expected) checked_++;
            }
        }
        output.WriteLine($"frames compared with the census: {checked_}, not in the census: {missing}");
        Assert.Empty(wrong);
        Assert.Equal(0, missing);        // a picture outside the census has no identity for a verdict
        Assert.True(checked_ > 20000, $"too few frames compared ({checked_}): is the census stale?");
    }

    [Fact]
    public void Tile_types_and_ground_flags_match_the_python_pipeline()
    {
        // the baseline is census/ground.tsv, taken by tools/hdart/ground_dump.py from the same
        // installation; the art/TERRAIN sheets are not a baseline — two of them were built from
        // vanilla bin/UFO rather than from Piratez (rake R-015), so the data behind them differs
        var repo = RepoRoot();
        var baseline = repo is null ? null : Path.Combine(repo, "census", "ground.tsv");
        var terrain = repo is null ? null : Path.Combine(repo, "Пиратки", "Dioxine_XPiratez", "user", "mods", "Piratez", "TERRAIN");
        if (baseline is null || !File.Exists(baseline) || terrain is null || !Directory.Exists(terrain))
        {
            output.WriteLine("no census/ground.tsv here: run tools/hdart/ground_dump.py to compare");
            return;
        }

        var want = new Dictionary<string, List<(bool Missing, int Type, bool Ground, bool Base)>>();
        foreach (var line in File.ReadLines(baseline, new UTF8Encoding(false)).Skip(1))
        {
            var c = line.TrimStart('﻿').Split('\t');
            if (c.Length < 7) continue;
            var rows = want.TryGetValue(c[1], out var list) ? list : want[c[1]] = [];
            Assert.Equal(rows.Count, int.Parse(c[2]));      // the baseline lists every frame in order
            rows.Add((c[3] == "1", int.Parse(c[4]), c[5] == "1", c[6] == "1"));
        }

        int sets = 0, frames = 0;
        var wrong = new List<string>();
        foreach (var (name, rows) in want.OrderBy(p => p.Key, StringComparer.Ordinal))
        {
            var pck = Pck.Find(terrain, name);
            var mcd = Pck.Find(terrain, Path.GetFileNameWithoutExtension(name) + ".MCD");
            Assert.NotNull(pck);
            var sprites = Pck.ReadSet(pck);
            var (types, walkable, raised) = mcd is null
                ? (Enumerable.Repeat(-1, sprites.Count).ToArray(), Enumerable.Repeat(true, sprites.Count).ToArray(), new bool[sprites.Count])
                : Pck.FrameTypes(Pck.ReadMcd(mcd), sprites.Count);
            var (ground, onDiamond) = Pck.GroundFlags(sprites, types, walkable, raised);

            if (sprites.Count != rows.Count)
            {
                wrong.Add($"{name}: {sprites.Count} frames, python says {rows.Count}");
                continue;
            }
            sets++;
            for (var i = 0; i < rows.Count && wrong.Count < 10; i++)
            {
                var (missing, type, isGround, isBase) = rows[i];
                frames++;
                if ((sprites.Frames[i] is null) != missing) wrong.Add($"{name} #{i}: missing {sprites.Frames[i] is null}, python says {missing}");
                if (types[i] != type) wrong.Add($"{name} #{i}: type {types[i]}, python says {type}");
                if (ground[i] != isGround) wrong.Add($"{name} #{i}: ground {ground[i]}, python says {isGround}");
                if (onDiamond[i] != isBase) wrong.Add($"{name} #{i}: on a diamond {onDiamond[i]}, python says {isBase}");
            }
        }
        output.WriteLine($"sets compared with python: {sets}, frames: {frames}");
        Assert.Empty(wrong);
        Assert.True(sets > 600, $"too few sets compared ({sets}): is census/ground.tsv stale?");
    }

    /// <summary>The repository root, found by walking up from the test binary; null off the repo.</summary>
    static string? RepoRoot()
    {
        var dir = AppContext.BaseDirectory;
        for (var i = 0; i < 12 && dir is not null; i++)
        {
            if (File.Exists(Path.Combine(dir, "CLAUDE.md")) && Directory.Exists(Path.Combine(dir, "census"))) return dir;
            dir = Path.GetDirectoryName(dir.TrimEnd(Path.DirectorySeparatorChar));
        }
        return null;
    }
}
