using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.EntityFrameworkCore;
using Xp.Portal.Data;

namespace Xp.Portal.Review;

/// <summary>
/// The list of what there is to check: every set of the game with how many frames it has, how many
/// different pictures are in it and how much of the maps it covers. It is counted from the game's own
/// data by tools/pck_census.py and carried here as a file (deploy/seed/packs.json) — the site has no
/// game data of its own and must not have any.
///
/// Applying the file again updates the rows it names and never deletes: a set missing from a newer
/// census is not proof that it is gone, and verdicts already given about it must keep their meaning.
/// </summary>
public sealed class PackSeed(PortalDb db)
{
    public sealed record PackRow(
        string Section = "TERRAIN", string Name = "",
        int Frames = 0, int Pictures = 0, int HdFrames = 0, long Cells = 0, double CellShare = 0);

    public sealed record File([property: JsonPropertyName("packs")] List<PackRow>? Packs = null);

    public sealed record Report(int Added, int Updated);

    static readonly JsonSerializerOptions Json = new()
    {
        PropertyNameCaseInsensitive = true,
        ReadCommentHandling = JsonCommentHandling.Skip,
        AllowTrailingCommas = true,
    };

    public static File Read(string path)
    {
        using var stream = System.IO.File.OpenRead(path);
        return JsonSerializer.Deserialize<File>(stream, Json) ?? throw new ArgumentException($"{path} is empty");
    }

    public async Task<Report> ApplyAsync(File file, CancellationToken ct)
    {
        var have = await db.ArtPacks.ToDictionaryAsync(p => (p.Section, p.Name), ct);
        int added = 0, updated = 0;
        foreach (var row in file.Packs ?? [])
        {
            var section = row.Section.Trim().ToUpperInvariant();
            var name = row.Name.Trim().ToUpperInvariant();
            if (section.Length is 0 or > ReviewLimits.SectionMax || name.Length is 0 or > ReviewLimits.SetMax)
                throw new ArgumentException($"a pack is named by its section and its set: '{row.Section}' '{row.Name}'");

            if (!have.TryGetValue((section, name), out var pack))
            {
                pack = new ArtPack { Section = section, Name = name };
                db.ArtPacks.Add(pack);
                have[(section, name)] = pack;
                added++;
            }
            else updated++;

            pack.Frames = row.Frames;
            pack.Pictures = row.Pictures;
            pack.HdFrames = row.HdFrames;
            pack.Cells = row.Cells;
            pack.CellShare = row.CellShare;
        }
        await db.SaveChangesAsync(ct);
        return new Report(added, updated);
    }
}
