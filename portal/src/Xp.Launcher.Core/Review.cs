using System.IO.Compression;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Xp.Launcher.Core;

/// <summary>
/// Reviewing an HD pack against what the game draws without it. Everything here works on the
/// installed game — the data the player has and the pack the player got — because the only honest
/// thing to judge is the file the game reads (rake R-019). No text lives here: the page names
/// things, this measures them.
/// </summary>
public static class Review
{
    /// <summary>Why a frame was marked bad. Closed list: the statistics on the site count by it.</summary>
    public static readonly string[] Reasons = ["color", "shape", "panel", "seams", "invented", "blurry"];

    /// <summary>The dark battle floor: on a chequerboard a leftover panel is invisible (rake R-041).</summary>
    public static readonly Rgb Floor = new(34, 34, 40);

    /// <summary>
    /// Where the pictures to compare live in this installation: the mod that carries the HD pack
    /// and the mod whose PCK files the game draws without it. Both are found by what is inside
    /// them, not by name, because a player may rename a mod folder.
    /// </summary>
    public static (string? Data, string? Mod) FindMods(string gameDir, string section = "TERRAIN")
    {
        var root = Path.Combine(gameDir, "user", "mods");
        if (!Directory.Exists(root)) return (null, null);
        string? mod = null, data = null;
        var richest = 0;
        foreach (var dir in Directory.EnumerateDirectories(root).Order(StringComparer.OrdinalIgnoreCase))
        {
            if (Directory.Exists(Path.Combine(dir, "hd", section)) && mod is null) mod = dir;
            var terrain = Path.Combine(dir, section);
            if (!Directory.Exists(terrain)) continue;
            var count = Directory.EnumerateFiles(terrain, "*.PCK").Count();
            if (count > richest) (data, richest) = (dir, count);
        }
        return (data, mod);
    }

    /// <summary>Sets the pack has pictures for, as &lt;SET&gt;.PCK, sorted.</summary>
    public static List<string> SetsWithPack(string mod, string section)
    {
        var names = new List<string>();
        if (mod.EndsWith(".zip", StringComparison.OrdinalIgnoreCase))
        {
            using var zip = ZipFile.OpenRead(mod);
            var head = ("hd/" + section + "/").ToLowerInvariant();
            foreach (var e in zip.Entries)
            {
                var low = e.FullName.Replace('\\', '/').ToLowerInvariant();
                var pos = low.IndexOf(head, StringComparison.Ordinal);
                if (pos < 0) continue;
                var rest = low[(pos + head.Length)..].Split('/');
                if (rest.Length > 1 && rest[0].EndsWith(".pck", StringComparison.Ordinal)) names.Add(rest[0].ToUpperInvariant());
            }
        }
        else
        {
            var root = Path.Combine(mod, "hd", section);
            if (Directory.Exists(root))
                foreach (var dir in Directory.EnumerateDirectories(root, "*.PCK"))
                    names.Add(Path.GetFileName(dir).ToUpperInvariant());
        }
        return names.Distinct().Order(StringComparer.Ordinal).ToList();
    }

    /// <summary>
    /// The battle palette the game draws this data with. A mod like X-Piratez has no PALETTES.DAT
    /// of its own: it replaces the battle palette from its own .pal, and reading the wrong one
    /// gives a picture exactly four times too dark.
    ///
    /// A mod's file is taken as it is, greyish tail included. The engine corrects the tail of the
    /// palette it read from PALETTES.DAT, and only then lets customPalettes write all 256 colours
    /// over it (Mod.cpp, "Correct Battlescape palette" and "Loading custom palettes from ruleset"),
    /// so for a mod the file wins. Correcting it here turned the dark colours of ABUNKER into the
    /// engine's greys and moved the colour error of one frame from 1.9 to 7.2.
    /// </summary>
    public static Rgb[] FindPalette(string dataDir, string? preferred = null)
    {
        if (!string.IsNullOrEmpty(preferred) && File.Exists(preferred)) return Pck.LoadPaletteFile(preferred);
        if (Pck.Find(Path.Combine(dataDir, "GEODATA"), "PALETTES.DAT") is { } dat) return Pck.LoadPalette(dat);
        var pals = Path.Combine(dataDir, "Resources", "Pals");
        if (Directory.Exists(pals))
        {
            var pick = Pck.Find(pals, "delicious_regular.pal")
                       ?? Directory.EnumerateFiles(pals, "*.pal").Order(StringComparer.OrdinalIgnoreCase).FirstOrDefault();
            if (pick is not null) return Pck.LoadPaletteFile(pick);
        }
        throw new ReviewException($"no palette next to {dataDir}: neither GEODATA/PALETTES.DAT nor Resources/Pals/*.pal");
    }

    /// <summary>
    /// What is worth looking at in one set, hardest first. Skipped on purpose: empty frames, frames
    /// no MCD record points at (the game never draws them, rake R-052) and frames the pack has no
    /// picture for.
    /// </summary>
    public static ReviewPlan Build(string dataDir, string section, string set, HdPack pack, Rgb[] palette)
    {
        var folder = Path.Combine(dataDir, section);
        var pckPath = Pck.Find(folder, set) ?? throw new ReviewException($"{set} is not in {folder}");
        var stem = Path.GetFileNameWithoutExtension(pckPath);
        var sprites = Pck.ReadSet(pckPath, Pck.Find(folder, stem + ".TAB"));
        var mcd = Pck.Find(folder, stem + ".MCD");
        var (types, walkable, raised) = mcd is null
            ? (Enumerable.Repeat(-1, sprites.Count).ToArray(), Enumerable.Repeat(true, sprites.Count).ToArray(), new bool[sprites.Count])
            : Pck.FrameTypes(Pck.ReadMcd(mcd), sprites.Count);
        var (ground, _) = Pck.GroundFlags(sprites, types, walkable, raised);

        var plan = new ReviewPlan { Section = section, Set = set.ToUpperInvariant() };
        for (var i = 0; i < sprites.Count; i++)
        {
            var frame = sprites.Frames[i];
            if (frame is null || Pck.IsEmpty(frame)) continue;
            if (mcd is not null && types[i] < 0) { plan.Orphans++; continue; }
            var (png, sha) = pack.Frame(i);
            if (png is null) { plan.Skipped.Add($"{i}"); continue; }

            var hd = Image32.FromPng(png);
            var big = Image32.FromIndices(frame, sprites.Width, sprites.Height, palette).ScaleNearest(Math.Max(1, hd.Width / sprites.Width));
            plan.Frames.Add(new ReviewFrame
            {
                Frame = i,
                Orig = Pck.Fingerprint(frame),
                Hd = sha,
                Error = hd.Width == big.Width && hd.Height == big.Height ? Math.Round(ChromaError(hd, big), 1) : -1,
                Type = types[i],
                Ground = ground[i],
                Variants = pack.VariantCount(i),
            });
        }
        plan.Frames.Sort((a, b) => b.Error.CompareTo(a.Error) is var c and not 0 ? c : a.Frame.CompareTo(b.Frame));
        plan.Pictures = plan.Frames.Select(f => f.Orig).Distinct(StringComparer.Ordinal).Count();
        return plan;
    }

    /// <summary>
    /// How far the colour went, brightness aside — the painter is allowed to change brightness.
    /// The same measure as build_pack.chroma_error: the mean distance in the a,b plane of CIELAB,
    /// over the pixels the original has painted.
    /// </summary>
    public static double ChromaError(Image32 painted, Image32 original)
    {
        if (painted.Width != original.Width || painted.Height != original.Height)
            throw new ReviewException("the pictures are of different sizes: there is nothing to compare pixel by pixel");
        double sum = 0;
        var count = 0;
        for (var i = 0; i < original.Rgba.Length; i += 4)
        {
            if (original.Rgba[i + 3] <= 128) continue;
            var (_, a1, b1) = Lab(painted.Rgba[i], painted.Rgba[i + 1], painted.Rgba[i + 2]);
            var (_, a2, b2) = Lab(original.Rgba[i], original.Rgba[i + 1], original.Rgba[i + 2]);
            sum += Math.Sqrt((a1 - a2) * (a1 - a2) + (b1 - b2) * (b1 - b2));
            count++;
        }
        return count < 16 ? 0.0 : sum / count;
    }

    static (double L, double A, double B) Lab(byte r, byte g, byte b)
    {
        static double Linear(byte v)
        {
            var c = v / 255.0;
            return c <= 0.04045 ? c / 12.92 : Math.Pow((c + 0.055) / 1.055, 2.4);
        }
        double rl = Linear(r), gl = Linear(g), bl = Linear(b);
        var x = (0.4124564 * rl + 0.3575761 * gl + 0.1804375 * bl) / 0.95047;
        var y = 0.2126729 * rl + 0.7151522 * gl + 0.0721750 * bl;
        var z = (0.0193339 * rl + 0.1191920 * gl + 0.9503041 * bl) / 1.08883;
        const double e = 216.0 / 24389.0, k = 24389.0 / 27.0;
        static double F(double v, double e2, double k2) => v > e2 ? Math.Cbrt(v) : (k2 * v + 16) / 116;
        double fx = F(x, e, k), fy = F(y, e, k), fz = F(z, e, k);
        return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz));
    }
}

/// <summary>A picture in memory: RGBA, row by row. Small on purpose — the page needs to show it.</summary>
public sealed class Image32(int width, int height, byte[] rgba)
{
    public int Width { get; } = width;
    public int Height { get; } = height;
    public byte[] Rgba { get; } = rgba;

    public static Image32 Empty(int w, int h) => new(w, h, new byte[w * h * 4]);

    public static Image32 FromPng(ReadOnlySpan<byte> png)
    {
        var (w, h, rgba) = Png.Decode(png);
        return new Image32(w, h, rgba);
    }

    /// <summary>An indexed frame through the palette; index 0 is transparent, as in the engine.</summary>
    public static Image32 FromIndices(byte[] frame, int w, int h, Rgb[] palette) => new(w, h, Pck.ToRgba(frame, palette));

    public Image32 ScaleNearest(int k)
    {
        if (k <= 1) return this;
        var to = Empty(Width * k, Height * k);
        for (var y = 0; y < to.Height; y++)
            for (var x = 0; x < to.Width; x++)
            {
                var s = ((y / k) * Width + x / k) * 4;
                var d = (y * to.Width + x) * 4;
                to.Rgba[d] = Rgba[s]; to.Rgba[d + 1] = Rgba[s + 1]; to.Rgba[d + 2] = Rgba[s + 2]; to.Rgba[d + 3] = Rgba[s + 3];
            }
        return to;
    }

    /// <summary>Source-over, the way the engine and the art pipeline lay one frame over another.</summary>
    public void Composite(Image32 src, int ox, int oy)
    {
        for (var y = 0; y < src.Height; y++)
        {
            var ty = oy + y;
            if (ty < 0 || ty >= Height) continue;
            for (var x = 0; x < src.Width; x++)
            {
                var tx = ox + x;
                if (tx < 0 || tx >= Width) continue;
                var s = (y * src.Width + x) * 4;
                var sa = src.Rgba[s + 3];
                if (sa == 0) continue;
                var d = (ty * Width + tx) * 4;
                if (sa == 255)
                {
                    Array.Copy(src.Rgba, s, Rgba, d, 4);
                    continue;
                }
                var da = Rgba[d + 3];
                var outA = sa + da * (255 - sa) / 255;
                for (var c = 0; c < 3; c++)
                    Rgba[d + c] = (byte)(outA == 0 ? 0 : (src.Rgba[s + c] * sa + Rgba[d + c] * da * (255 - sa) / 255) / outA);
                Rgba[d + 3] = (byte)outA;
            }
        }
    }

    /// <summary>Every d-th pixel: the only honest way down for pixel art that outgrew its box.</summary>
    public Image32 ShrinkNearest(int d)
    {
        if (d <= 1) return this;
        var to = Empty(Math.Max(1, Width / d), Math.Max(1, Height / d));
        for (var y = 0; y < to.Height; y++)
            for (var x = 0; x < to.Width; x++)
            {
                var s = (y * d * Width + x * d) * 4;
                var t = (y * to.Width + x) * 4;
                to.Rgba[t] = Rgba[s]; to.Rgba[t + 1] = Rgba[s + 1]; to.Rgba[t + 2] = Rgba[s + 2]; to.Rgba[t + 3] = Rgba[s + 3];
            }
        return to;
    }

    /// <summary>
    /// The picture centred on a canvas of a FIXED size, magnified by a whole number so pixels stay
    /// pixels. Every frame is shown in the same box on purpose: a box that changes with the frame
    /// makes the page jump under the hand and two frames in a row incomparable by eye.
    /// </summary>
    public Image32 Fit(int boxW, int boxH, Rgb floor)
    {
        var picture = Width > boxW || Height > boxH
            ? ShrinkNearest(Math.Max((Width + boxW - 1) / boxW, (Height + boxH - 1) / boxH))
            : ScaleNearest(Math.Max(1, Math.Min(boxW / Width, boxH / Height)));
        var to = Empty(boxW, boxH);
        for (var i = 0; i < to.Rgba.Length; i += 4)
        {
            to.Rgba[i] = floor.R; to.Rgba[i + 1] = floor.G; to.Rgba[i + 2] = floor.B; to.Rgba[i + 3] = 255;
        }
        to.Composite(picture, (boxW - picture.Width) / 2, (boxH - picture.Height) / 2);
        return to;
    }

    /// <summary>The frame on the dark battle floor, with a margin, so a leftover panel shows.</summary>
    public Image32 OnFloor(Rgb floor, int pad = 10)
    {
        var to = Empty(Width + 2 * pad, Height + 2 * pad);
        for (var i = 0; i < to.Rgba.Length; i += 4)
        {
            to.Rgba[i] = floor.R; to.Rgba[i + 1] = floor.G; to.Rgba[i + 2] = floor.B; to.Rgba[i + 3] = 255;
        }
        to.Composite(this, pad, pad);
        return to;
    }

    /// <summary>
    /// A field of cells x cells map cells of one floor, on the isometric grid the engine lays tiles
    /// on: 32x16 base pixels of a diamond, scaled by k. A floor is judged as a field and never as a
    /// single diamond — one tile looks fine while the field of it is a lattice (rake R-039).
    /// </summary>
    public Image32 Field(int cells, int k)
    {
        var bh = Height / k;
        var to = Empty(cells * 2 * 16 * k, cells * 16 * k + bh * k);
        for (var s = 0; s < 2 * cells - 1; s++)
            for (var cx = 0; cx < cells; cx++)
            {
                var cy = s - cx;
                if (cy < 0 || cy >= cells) continue;
                to.Composite(this, (cx - cy) * 16 * k + (cells - 1) * 16 * k, (cx + cy) * 8 * k);
            }
        return to;
    }
}

/// <summary>The pictures of an HD pack where the game reads them: &lt;mod&gt;/hd/&lt;section&gt;/&lt;SET&gt;/&lt;N&gt;.png.</summary>
public sealed class HdPack : IDisposable
{
    readonly ZipArchive? _zip;
    readonly Dictionary<string, ZipArchiveEntry> _entries = new(StringComparer.OrdinalIgnoreCase);
    readonly string _dir = "";

    /// <summary>A mod is handed out both as a folder and as a zip; the player may have either.</summary>
    public HdPack(string mod, string section, string set)
    {
        Set = set.ToUpperInvariant();
        var rel = $"hd/{section}/{Set}";
        Where = mod.EndsWith(".zip", StringComparison.OrdinalIgnoreCase) ? $"{mod}!{rel}" : Path.Combine(mod, "hd", section, Set);
        if (!mod.EndsWith(".zip", StringComparison.OrdinalIgnoreCase)) { _dir = Where; return; }
        _zip = ZipFile.OpenRead(mod);
        var tail = (rel + "/").ToLowerInvariant();
        foreach (var e in _zip.Entries)
        {
            var low = e.FullName.Replace('\\', '/').ToLowerInvariant();
            if (low.EndsWith('/') || !(low.StartsWith(tail, StringComparison.Ordinal) || low.Contains("/" + tail, StringComparison.Ordinal))) continue;
            _entries[low[(low.LastIndexOf('/') + 1)..]] = e;
        }
    }

    public string Set { get; }
    public string Where { get; }

    public byte[]? Data(string fileName)
    {
        if (_zip is not null)
        {
            if (!_entries.TryGetValue(fileName, out var e)) return null;
            using var s = e.Open();
            using var ms = new MemoryStream();
            s.CopyTo(ms);
            return ms.ToArray();
        }
        var path = Path.Combine(_dir, fileName);
        return File.Exists(path) ? File.ReadAllBytes(path) : null;
    }

    /// <summary>The picture and its sha256 — the same value the release manifest carries, so it is the version key.</summary>
    public (byte[]? Png, string Sha) Frame(int i)
    {
        var raw = Data($"{i}.png");
        return raw is null ? (null, "") : (raw, Convert.ToHexStringLower(SHA256.HashData(raw)));
    }

    /// <summary>Variants &lt;N&gt;.v1.png, v2... — the engine lays them over the field in a pattern.</summary>
    public int VariantCount(int i)
    {
        var n = 0;
        while (Data($"{i}.v{n + 1}.png") is not null) n++;
        return n;
    }

    public void Dispose() => _zip?.Dispose();
}

public sealed class ReviewFrame
{
    public int Frame { get; set; }
    /// <summary>The picture's fingerprint, the same one the census counts by: a verdict points at a picture.</summary>
    public string Orig { get; set; } = "";
    /// <summary>sha256 of the pack's PNG: the version. Repainted picture — the old verdicts no longer apply.</summary>
    public string Hd { get; set; } = "";
    public double Error { get; set; }
    public int Type { get; set; } = -1;
    public bool Ground { get; set; }
    public int Variants { get; set; }
    public string Verdict { get; set; } = "";
    public List<string> Reasons { get; set; } = [];
    /// <summary>What the person wrote about this frame. The closed list of reasons cannot say everything.</summary>
    public string Note { get; set; } = "";
}

/// <summary>One pack's frames, hardest first. This is also the block that goes to the site.</summary>
public sealed class ReviewPlan
{
    public string Section { get; set; } = "TERRAIN";
    public string Set { get; set; } = "";
    public string ModVersion { get; set; } = "";
    /// <summary>
    /// How many different pictures the set offered for judging. It travels with the verdicts because
    /// the site has no game data of its own: without it "checked" has no denominator, and three
    /// frames out of forty one would close the set.
    /// </summary>
    public int Pictures { get; set; }
    public List<ReviewFrame> Frames { get; set; } = [];
    [JsonIgnore] public List<string> Skipped { get; set; } = [];
    [JsonIgnore] public int Orphans { get; set; }
}

/// <summary>The envelope the launcher sends and review_floors.py writes: one block per pack.</summary>
public sealed class VerdictFile
{
    public string Tool { get; set; } = "";
    public DateTimeOffset CheckedAt { get; set; }
    public List<ReviewPlan> Packs { get; set; } = [];
}

/// <summary>
/// Marks live on this machine until they are sent: %LOCALAPPDATA%\XPiratezLauncher\review\&lt;SET&gt;.json.
/// A pack is hundreds of pictures — closing the launcher may not lose an evening of work.
/// </summary>
public static class ReviewStore
{
    public static string Dir { get; set; } =
        Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "XPiratezLauncher", "review");

    static string PathOf(string section, string set) => Path.Combine(Dir, $"{section}_{set}.json".Replace('/', '_'));

    public static ReviewPlan? Load(string section, string set)
    {
        var path = PathOf(section, set);
        if (!File.Exists(path)) return null;
        try { return JsonSerializer.Deserialize(File.ReadAllBytes(path), ReviewJson.Default.ReviewPlan); }
        catch (JsonException) { return null; }
    }

    public static void Save(ReviewPlan plan) =>
        FileUtil.WriteAtomic(PathOf(plan.Section, plan.Set), JsonSerializer.SerializeToUtf8Bytes(Marked(plan), ReviewJson.Default.ReviewPlan));

    /// <summary>Every set that has marks on this machine.</summary>
    public static List<ReviewPlan> All()
    {
        var out_ = new List<ReviewPlan>();
        if (!Directory.Exists(Dir)) return out_;
        foreach (var f in Directory.EnumerateFiles(Dir, "*.json").Order(StringComparer.OrdinalIgnoreCase))
        {
            try
            {
                if (JsonSerializer.Deserialize(File.ReadAllBytes(f), ReviewJson.Default.ReviewPlan) is { } p && p.Frames.Count > 0) out_.Add(p);
            }
            catch (JsonException) { }
        }
        return out_;
    }

    /// <summary>The file to send: only the frames a person actually judged.</summary>
    public static VerdictFile Envelope(IEnumerable<ReviewPlan> packs) => new()
    {
        Tool = "launcher",
        CheckedAt = DateTimeOffset.UtcNow,
        Packs = packs.Select(Marked).Where(p => p.Frames.Count > 0).ToList(),
    };

    public static byte[] Serialize(VerdictFile file) => JsonSerializer.SerializeToUtf8Bytes(file, ReviewJson.Default.VerdictFile);

    static ReviewPlan Marked(ReviewPlan plan) => new()
    {
        Section = plan.Section,
        Set = plan.Set,
        ModVersion = plan.ModVersion,
        Pictures = plan.Pictures,
        // a written note without a verdict is worth sending too: it is the part the six reasons cannot say
        Frames = plan.Frames.Where(f => !string.IsNullOrEmpty(f.Verdict) || !string.IsNullOrWhiteSpace(f.Note)).ToList(),
    };

    /// <summary>
    /// Marks made earlier, put back on the frames they were made about. The match is by the picture
    /// and by the pack's version: a repainted picture has a new sha256, and an old verdict about the
    /// old picture may not be counted for the new one.
    /// </summary>
    public static int Restore(ReviewPlan plan, ReviewPlan? saved)
    {
        if (saved is null) return 0;
        var was = saved.Frames.ToDictionary(f => (f.Frame, f.Orig, f.Hd), f => f);
        var back = 0;
        foreach (var f in plan.Frames)
        {
            if (!was.TryGetValue((f.Frame, f.Orig, f.Hd), out var old)) continue;
            if (string.IsNullOrEmpty(old.Verdict) && string.IsNullOrWhiteSpace(old.Note)) continue;
            f.Verdict = old.Verdict;
            f.Reasons = old.Reasons.Where(Review.Reasons.Contains).ToList();
            f.Note = old.Note;
            back++;
        }
        return back;
    }
}

/// <summary>The mod's own name and version from its metadata.yml: a verdict says what was judged.</summary>
public static class ModInfo
{
    public static string Version(string mod)
    {
        byte[]? raw = null;
        if (mod.EndsWith(".zip", StringComparison.OrdinalIgnoreCase))
        {
            using var zip = ZipFile.OpenRead(mod);
            var e = zip.Entries.FirstOrDefault(x => x.FullName.Replace('\\', '/').EndsWith("metadata.yml", StringComparison.OrdinalIgnoreCase));
            if (e is not null)
            {
                using var s = e.Open();
                using var ms = new MemoryStream();
                s.CopyTo(ms);
                raw = ms.ToArray();
            }
        }
        else if (File.Exists(Path.Combine(mod, "metadata.yml"))) raw = File.ReadAllBytes(Path.Combine(mod, "metadata.yml"));
        if (raw is null) return "";

        string id = "", version = "";
        foreach (var line in System.Text.Encoding.UTF8.GetString(raw).Split('\n'))
        {
            var colon = line.IndexOf(':');
            if (colon < 0) continue;
            var key = line[..colon].Trim();
            var value = line[(colon + 1)..].Trim().Trim('"');
            if (key == "id") id = value;
            else if (key == "version") version = value;
        }
        return string.Join(' ', new[] { id, version }.Where(x => x.Length > 0));
    }
}

public sealed class ReviewException(string message) : Exception(message);

/// <summary>What the site made of a send: packs taken, pictures in them, and own earlier results replaced.</summary>
public sealed record ReviewAccepted(int Packs, int Frames, int Replaced);

/// <summary>The review half of the portal API: the marks go up under the device's own key.</summary>
public sealed partial class PortalClient
{
    /// <summary>
    /// Sends what the person judged. The idempotency key is the send, not the moment: a repeat after
    /// a broken connection must not count the same evening twice.
    /// </summary>
    public async Task<ReviewAccepted> SendReviewAsync(VerdictFile file, string deviceToken, string idempotencyKey, CancellationToken ct)
    {
        using var msg = new HttpRequestMessage(HttpMethod.Post, new Uri(BaseUri, "api/v1/review/packs"))
        {
            Content = JsonContent.Create(file, ReviewJson.Default.VerdictFile),
        };
        msg.Headers.Add(DeviceTokenHeader, deviceToken);
        msg.Headers.Add("Idempotency-Key", idempotencyKey);
        using var resp = await Http.SendAsync(msg, ct);
        await ThrowIfFailedAsync(resp, ct);
        return await resp.Content.ReadFromJsonAsync(ReviewJson.Default.ReviewAccepted, ct)
               ?? throw new PortalException((int)resp.StatusCode, "bad_response", "empty answer");
    }
}

[JsonSourceGenerationOptions(WriteIndented = true, PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase, DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull)]
[JsonSerializable(typeof(ReviewPlan))]
[JsonSerializable(typeof(VerdictFile))]
[JsonSerializable(typeof(ReviewAccepted))]
internal sealed partial class ReviewJson : JsonSerializerContext
{
}
