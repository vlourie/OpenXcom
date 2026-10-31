using System.IO.Compression;
using System.Text;
using System.Text.Json;
using Xp.Launcher.Core;
using Xunit.Abstractions;

namespace Xp.Launcher.Core.Tests;

/// <summary>
/// The review the player does in the launcher: which frames it offers, in what order, and with what
/// number next to them. All of it must agree with the art pipeline in python — a verdict that
/// points at a different picture than the repainting queue is worse than no verdict at all.
/// </summary>
public sealed class ReviewTests(ITestOutputHelper output)
{
    [Fact]
    public void Png_rows_come_back_through_every_filter()
    {
        var rnd = new Random(1);
        var want = new byte[17 * 9 * 4];
        rnd.NextBytes(want);
        foreach (var filter in new byte[] { 0, 1, 2, 3, 4 })
        {
            var (w, h, got) = Png.Decode(WritePng(17, 9, want, filter));
            Assert.Equal((17, 9), (w, h));
            Assert.Equal(want, got);
        }
    }

    [Fact]
    public void An_unreadable_png_is_refused_by_name()
    {
        Assert.Contains("not a PNG", Assert.Throws<PngException>(() => Png.Decode(new byte[] { 1, 2, 3 })).Message);
        var broken = WritePng(2, 2, new byte[2 * 2 * 4], 0);
        broken[24] = 16;                  // IHDR bit depth
        Assert.Contains("16 bits", Assert.Throws<PngException>(() => Png.Decode(broken)).Message);
    }

    [Fact]
    public void A_pack_frame_reads_the_same_from_a_folder_and_from_a_zip()
    {
        var mod = HdMod();
        if (mod is null) { output.WriteLine("no hd mod installed here: nothing to read"); return; }

        using var folder = new HdPack(mod, "TERRAIN", "CAVEBROWN.PCK");
        var (png, sha) = folder.Frame(0);
        Assert.NotNull(png);
        var picture = Image32.FromPng(png);
        Assert.Equal(128, picture.Width);          // 32 x 40 of the base, four times over
        Assert.Equal(160, picture.Height);

        var zipPath = Path.Combine(Directory.CreateTempSubdirectory("xp-pack").FullName, "mod.zip");
        try
        {
            using (var zip = ZipFile.Open(zipPath, ZipArchiveMode.Create))
                zip.CreateEntryFromFile(Path.Combine(mod, "hd", "TERRAIN", "CAVEBROWN.PCK", "0.png"), "hd/TERRAIN/CAVEBROWN.PCK/0.png");
            using var packed = new HdPack(zipPath, "TERRAIN", "CAVEBROWN.PCK");
            var (zipped, zipSha) = packed.Frame(0);
            Assert.Equal(png, zipped);
            Assert.Equal(sha, zipSha);
        }
        finally { Directory.Delete(Path.GetDirectoryName(zipPath)!, recursive: true); }
    }

    [Fact]
    public void The_plan_matches_the_one_python_builds()
    {
        // the baseline is census/review_plan/pairs.json, written by
        //   review_floors.py --from-game --sets CAVEBROWN,ABUNKER,ACHURCH --mod <hd mod> --out census/review_plan
        var repo = RepoRoot();
        var baseline = repo is null ? null : Path.Combine(repo, "census", "review_plan", "pairs.json");
        var mod = HdMod();
        if (baseline is null || !File.Exists(baseline) || mod is null)
        {
            output.WriteLine("no census/review_plan/pairs.json here: run review_floors.py --from-game to compare");
            return;
        }

        using var doc = JsonDocument.Parse(File.ReadAllText(baseline, new UTF8Encoding(false)).TrimStart('﻿'));
        var want = doc.RootElement.EnumerateArray()
            .Select(e => (Set: e.GetProperty("set").GetString()!, Frame: e.GetProperty("frame").GetInt32(),
                          Err: e.GetProperty("err").GetDouble(), Orig: e.GetProperty("orig").GetString()!,
                          Hd: e.GetProperty("hd").GetString()!))
            .ToList();
        Assert.NotEmpty(want);

        var data = Path.Combine(Path.GetDirectoryName(mod)!, "Piratez");
        var palette = Review.FindPalette(data);
        var mine = new List<(string Set, int Frame, double Err, string Orig, string Hd)>();
        foreach (var set in want.Select(w => w.Set).Distinct())
        {
            using var pack = new HdPack(mod, "TERRAIN", set);
            var plan = Review.Build(data, "TERRAIN", set, pack, palette);
            mine.AddRange(plan.Frames.Select(f => (plan.Set, f.Frame, f.Error, f.Orig, f.Hd)));
        }

        // first the numbers themselves, keyed by frame: an order that differs because a number
        // differs is a different fault than an order that differs on equal numbers
        var byFrame = mine.ToDictionary(m => (m.Set, m.Frame), m => m);
        var worst = ("", 0.0);
        foreach (var w in want)
        {
            Assert.True(byFrame.TryGetValue((w.Set, w.Frame), out var got), $"{w.Set} #{w.Frame}: python offers it, the launcher does not");
            Assert.Equal(w.Orig, got.Orig);
            Assert.Equal(w.Hd, got.Hd);
            var diff = Math.Abs(w.Err - got.Err);
            if (diff > worst.Item2) worst = ($"{w.Set} #{w.Frame}: {got.Err} against python's {w.Err}", diff);
        }
        output.WriteLine($"the widest difference in the colour error: {worst.Item1}");
        Assert.True(worst.Item2 <= 0.1, worst.Item1);

        // then the order: hardest first, so that the frames worth repainting come up first
        foreach (var set in want.Select(w => w.Set).Distinct())
        {
            Assert.Equal(want.Where(w => w.Set == set).Select(x => x.Frame),
                         mine.Where(m => m.Set == set).Select(x => x.Frame));
        }
        output.WriteLine($"frames compared with python: {mine.Count} in {want.Select(w => w.Set).Distinct().Count()} sets");
    }

    [Fact]
    public void A_field_of_a_floor_repeats_the_tile_on_the_isometric_grid()
    {
        var tile = Image32.Empty(128, 160);
        for (var i = 0; i < tile.Rgba.Length; i += 4) { tile.Rgba[i] = 200; tile.Rgba[i + 3] = 255; }
        var field = tile.Field(cells: 4, k: 4);
        Assert.Equal(4 * 2 * 16 * 4, field.Width);
        Assert.Equal(4 * 16 * 4 + 40 * 4, field.Height);
        // the middle of the field is covered; the top left corner is outside the diamonds
        Assert.Equal(255, field.Rgba[((field.Height / 2) * field.Width + field.Width / 2) * 4 + 3]);
        Assert.Equal(0, field.Rgba[3]);
    }

    /// <summary>
    /// The box a frame is shown in must not follow the frame: a floor as a field is four times wider
    /// than a single object, and a box that changes makes the page jump and two frames incomparable.
    /// </summary>
    [Fact]
    public void Every_frame_is_shown_in_the_same_box_whatever_its_own_size()
    {
        var floor = new Rgb(34, 34, 40);
        foreach (var (w, h) in new[] { (32, 40), (128, 160), (148, 180), (512, 416), (1200, 900) })
        {
            var fit = Image32.Empty(w, h).Fit(544, 448, floor);
            Assert.Equal(544, fit.Width);
            Assert.Equal(448, fit.Height);
            // the whole box is painted: nothing of the frame before it shows through
            Assert.Equal(255, fit.Rgba[3]);
            Assert.Equal(floor.R, fit.Rgba[^4]);
        }
        // a small frame is magnified by a whole number, so pixels stay pixels
        var one = Image32.Empty(1, 1);
        one.Rgba[0] = one.Rgba[3] = 255;
        var big = one.ScaleNearest(2).Fit(8, 8, floor);
        Assert.Equal(8, big.Width);
        output.WriteLine("box 544x448 holds every frame size");
    }

    [Fact]
    public void Marks_come_back_only_for_the_picture_they_were_made_about()
    {
        var dir = Directory.CreateTempSubdirectory("xp-review").FullName;
        var was = ReviewStore.Dir;
        ReviewStore.Dir = dir;
        try
        {
            var plan = new ReviewPlan
            {
                Section = "TERRAIN", Set = "CAVEBROWN.PCK", ModVersion = "hd 0.1",
                Frames =
                [
                    new ReviewFrame { Frame = 1, Orig = "aaa", Hd = "111", Verdict = "bad", Reasons = ["panel", "nonsense"] },
                    new ReviewFrame { Frame = 2, Orig = "bbb", Hd = "222", Verdict = "ok" },
                    new ReviewFrame { Frame = 3, Orig = "ccc", Hd = "333" },
                ],
            };
            ReviewStore.Save(plan);

            // the pack was repainted: frame 2 has a new picture, so its verdict is about a picture that is gone
            var fresh = new ReviewPlan
            {
                Section = "TERRAIN", Set = "CAVEBROWN.PCK",
                Frames =
                [
                    new ReviewFrame { Frame = 1, Orig = "aaa", Hd = "111" },
                    new ReviewFrame { Frame = 2, Orig = "bbb", Hd = "999" },
                    new ReviewFrame { Frame = 3, Orig = "ccc", Hd = "333" },
                ],
            };
            Assert.Equal(1, ReviewStore.Restore(fresh, ReviewStore.Load("TERRAIN", "CAVEBROWN.PCK")));
            Assert.Equal("bad", fresh.Frames[0].Verdict);
            Assert.Equal(["panel"], fresh.Frames[0].Reasons);     // a reason outside the closed list is dropped
            Assert.Equal("", fresh.Frames[1].Verdict);

            var envelope = ReviewStore.Envelope(ReviewStore.All());
            var json = JsonDocument.Parse(ReviewStore.Serialize(envelope)).RootElement;
            var frames = json.GetProperty("packs")[0].GetProperty("frames");
            Assert.Equal(2, frames.GetArrayLength());             // only what was judged goes out
            Assert.Equal("CAVEBROWN.PCK", json.GetProperty("packs")[0].GetProperty("set").GetString());
            Assert.Equal("hd 0.1", json.GetProperty("packs")[0].GetProperty("modVersion").GetString());
            Assert.Equal("panel", frames[0].GetProperty("reasons")[0].GetString());
        }
        finally
        {
            ReviewStore.Dir = was;
            Directory.Delete(dir, recursive: true);
        }
    }

    [Fact]
    public void The_mod_names_itself_from_its_metadata()
    {
        var mod = HdMod();
        if (mod is null) { output.WriteLine("no hd mod installed here"); return; }
        var version = ModInfo.Version(mod);
        output.WriteLine($"mod version: {version}");
        Assert.StartsWith("hd", version);
    }

    /// <summary>A PNG of the given RGBA pixels, every row written with one filter.</summary>
    static byte[] WritePng(int w, int h, byte[] rgba, byte filter)
    {
        var raw = new MemoryStream();
        var previous = new byte[w * 4];
        for (var y = 0; y < h; y++)
        {
            raw.WriteByte(filter);
            var row = rgba.AsSpan(y * w * 4, w * 4);
            for (var x = 0; x < w * 4; x++)
            {
                int a = x >= 4 ? row[x - 4] : 0, b = previous[x], c = x >= 4 ? previous[x - 4] : 0;
                int p = a + b - c, pa = Math.Abs(p - a), pb = Math.Abs(p - b), pc = Math.Abs(p - c);
                var paeth = pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
                raw.WriteByte((byte)(row[x] - filter switch { 1 => a, 2 => b, 3 => (a + b) / 2, 4 => paeth, _ => 0 }));
            }
            row.CopyTo(previous);
        }

        var deflated = new MemoryStream();
        using (var z = new ZLibStream(deflated, CompressionLevel.Optimal, leaveOpen: true)) z.Write(raw.ToArray());

        var png = new MemoryStream();
        png.Write([0x89, (byte)'P', (byte)'N', (byte)'G', 0x0D, 0x0A, 0x1A, 0x0A]);
        var ihdr = new byte[13];
        System.Buffers.Binary.BinaryPrimitives.WriteInt32BigEndian(ihdr, w);
        System.Buffers.Binary.BinaryPrimitives.WriteInt32BigEndian(ihdr.AsSpan(4), h);
        ihdr[8] = 8; ihdr[9] = 6;                    // eight bits, RGBA
        Chunk(png, "IHDR", ihdr);
        Chunk(png, "IDAT", deflated.ToArray());
        Chunk(png, "IEND", []);
        return png.ToArray();

        static void Chunk(Stream to, string type, byte[] body)
        {
            var length = new byte[4];
            System.Buffers.Binary.BinaryPrimitives.WriteInt32BigEndian(length, body.Length);
            to.Write(length);
            var typed = Encoding.ASCII.GetBytes(type).Concat(body).ToArray();
            to.Write(typed);
            var crc = new byte[4];
            System.Buffers.Binary.BinaryPrimitives.WriteUInt32BigEndian(crc, Crc32(typed));
            to.Write(crc);
        }
    }

    static uint Crc32(byte[] data)
    {
        uint crc = 0xFFFFFFFF;
        foreach (var b in data)
        {
            crc ^= b;
            for (var i = 0; i < 8; i++) crc = (crc >> 1) ^ (0xEDB88320 & (uint)-(crc & 1));
        }
        return crc ^ 0xFFFFFFFF;
    }

    /// <summary>The hd mod of the installation next to the repository, or null off this machine.</summary>
    static string? HdMod()
    {
        var repo = RepoRoot();
        if (repo is null) return null;
        var mod = Path.Combine(repo, "Пиратки", "Dioxine_XPiratez", "user", "mods", "hd");
        return Directory.Exists(Path.Combine(mod, "hd", "TERRAIN")) ? mod : null;
    }

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
