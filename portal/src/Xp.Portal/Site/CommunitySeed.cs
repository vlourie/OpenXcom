using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.EntityFrameworkCore;
using Xp.Portal.Data;

namespace Xp.Portal.Site;

/// <summary>
/// The catalogue of the site - which mods have a section and which boards the forum has - kept in a
/// file next to the deployment rather than typed into an admin screen. Two reasons: it is reviewed
/// in the repository like everything else, and a new server comes up with the same sections as the
/// old one instead of whatever someone remembered to recreate.
///
/// The file is the source of truth: applying it again updates the rows it names and leaves the rest
/// alone. It never deletes: a board that disappears from the file keeps its topics and is hidden by
/// hand, because dropping a board would drop conversations with it.
/// </summary>
public sealed class CommunitySeed(PortalDb db, TimeProvider clock)
{
    public sealed record TextRow(string Name = "", string Summary = "", string Body = "");

    public sealed record ModRow(
        string Slug = "", int Order = 0, bool Published = true,
        string? Author = null, string? HomeUrl = null, string? DownloadUrl = null,
        string? Version = null, string? Image = null,
        Dictionary<string, TextRow>? Texts = null);

    public sealed record SectionRow(
        string Slug = "", int Order = 0, bool StaffOnly = false, bool Published = true,
        string? Mod = null, Dictionary<string, TextRow>? Texts = null);

    public sealed record File(
        [property: JsonPropertyName("mods")] List<ModRow>? Mods = null,
        [property: JsonPropertyName("sections")] List<SectionRow>? Sections = null);

    static readonly JsonSerializerOptions Json = new()
    {
        PropertyNameCaseInsensitive = true,
        ReadCommentHandling = JsonCommentHandling.Skip,
        AllowTrailingCommas = true,
    };

    public sealed record Report(int ModsAdded, int ModsUpdated, int SectionsAdded, int SectionsUpdated);

    public static File Read(string path)
    {
        using var stream = System.IO.File.OpenRead(path);
        return JsonSerializer.Deserialize<File>(stream, Json) ?? throw new ArgumentException($"{path} is empty");
    }

    public async Task<Report> ApplyAsync(File file, CancellationToken ct)
    {
        var now = clock.GetUtcNow();
        int modsAdded = 0, modsUpdated = 0, sectionsAdded = 0, sectionsUpdated = 0;

        var mods = await db.Mods.Include(m => m.Texts).ToDictionaryAsync(m => m.Slug, ct);
        foreach (var row in file.Mods ?? [])
        {
            Check(row.Slug);
            if (!mods.TryGetValue(row.Slug, out var mod))
            {
                mod = new GameMod { Slug = row.Slug, CreatedAt = now };
                db.Mods.Add(mod);
                mods[row.Slug] = mod;
                modsAdded++;
            }
            else modsUpdated++;
            mod.Order = row.Order;
            mod.Published = row.Published;
            mod.Author = Trim(row.Author);
            mod.HomeUrl = Trim(row.HomeUrl);
            mod.DownloadUrl = Trim(row.DownloadUrl);
            mod.Version = Trim(row.Version);
            mod.Image = Trim(row.Image);
            mod.UpdatedAt = now;
            foreach (var (lang, text) in row.Texts ?? [])
            {
                var t = mod.Texts.FirstOrDefault(x => x.Lang == lang);
                if (t is null) { t = new ModText { Lang = lang }; mod.Texts.Add(t); }
                t.Name = Cut(text.Name, CommunityLimits.NameMax);
                t.Summary = Cut(text.Summary, CommunityLimits.SummaryMax);
                t.Body = text.Body;
            }
        }

        var sections = await db.ForumSections.Include(s => s.Texts).ToDictionaryAsync(s => s.Slug, ct);
        foreach (var row in file.Sections ?? [])
        {
            Check(row.Slug);
            if (!sections.TryGetValue(row.Slug, out var section))
            {
                section = new ForumSection { Slug = row.Slug };
                db.ForumSections.Add(section);
                sections[row.Slug] = section;
                sectionsAdded++;
            }
            else sectionsUpdated++;
            section.Order = row.Order;
            section.StaffOnly = row.StaffOnly;
            section.Published = row.Published;
            // a board may name a mod that the same file creates a line above, so the lookup is the
            // dictionary we have been filling, not the database
            section.ModId = string.IsNullOrWhiteSpace(row.Mod) ? null
                : mods.TryGetValue(row.Mod, out var owner) ? owner.Id
                : throw new ArgumentException($"board {row.Slug} names mod {row.Mod}, which the file does not have");
            foreach (var (lang, text) in row.Texts ?? [])
            {
                var t = section.Texts.FirstOrDefault(x => x.Lang == lang);
                if (t is null) { t = new ForumSectionText { Lang = lang }; section.Texts.Add(t); }
                t.Name = Cut(text.Name, CommunityLimits.NameMax);
                t.Summary = Cut(text.Summary, CommunityLimits.SummaryMax);
            }
        }

        await db.SaveChangesAsync(ct);
        return new Report(modsAdded, modsUpdated, sectionsAdded, sectionsUpdated);
    }

    static void Check(string slug)
    {
        if (!Slugs.IsValid(slug)) throw new ArgumentException($"\"{slug}\" is not an address: latin letters, digits and dashes only");
    }

    static string? Trim(string? s) => string.IsNullOrWhiteSpace(s) ? null : s.Trim();

    static string Cut(string s, int max) => s.Length <= max ? s : s[..max];
}
