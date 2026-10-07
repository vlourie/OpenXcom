using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.EntityFrameworkCore;
using Xp.Portal.Data;

namespace Xp.Portal.Site;

/// <summary>
/// Takes what tools/portal_wiki.py read out of a mod's rulesets and puts it in the wiki.
///
/// Two rules keep the import from destroying work. A page somebody wrote by hand is never touched,
/// even if a generated page wants the same address - the hand-written one wins and the generated one
/// is dropped. And a generated page that the file no longer has is deleted, because it describes a
/// record the mod no longer has: leaving it would leave a page about a weapon that does not exist.
/// </summary>
public sealed class WikiImport(PortalDb db, TimeProvider clock)
{
    public sealed record PageRow(
        [property: JsonPropertyName("slug")] string Slug,
        [property: JsonPropertyName("lang")] string Lang,
        [property: JsonPropertyName("title")] string Title,
        [property: JsonPropertyName("section")] string? Section,
        [property: JsonPropertyName("source")] string? Source,
        [property: JsonPropertyName("body")] string Body);

    public sealed record File(
        [property: JsonPropertyName("mod")] string Mod,
        [property: JsonPropertyName("version")] string? Version,
        [property: JsonPropertyName("generated")] string? Generated,
        [property: JsonPropertyName("pages")] List<PageRow> Pages);

    static readonly JsonSerializerOptions Json = new() { PropertyNameCaseInsensitive = true };

    public sealed record Report(int Written, int Removed, int KeptByHand, int Skipped);

    public static File Read(string path)
    {
        using var stream = System.IO.File.OpenRead(path);
        return JsonSerializer.Deserialize<File>(stream, Json) ?? throw new ArgumentException($"{path} is empty");
    }

    public async Task<Report> ApplyAsync(File file, CancellationToken ct)
    {
        var mod = await db.Mods.FirstOrDefaultAsync(m => m.Slug == file.Mod, ct)
            ?? throw new ArgumentException($"no mod {file.Mod} on the site: apply the catalogue first (seed --file)");
        var now = clock.GetUtcNow();
        if (!string.IsNullOrWhiteSpace(file.Version)) mod.Version = file.Version.Trim();

        // Addresses somebody wrote by hand. They are read first and never written over.
        var byHand = (await db.WikiPages
                .Where(p => p.ModId == mod.Id && p.Kind != WikiKind.Generated)
                .Select(p => new { p.Slug, p.Lang })
                .ToListAsync(ct))
            .Select(p => (p.Slug, p.Lang)).ToHashSet();

        // The generated half is replaced wholesale rather than compared row by row: thirteen
        // thousand pages mean thirteen thousand round trips otherwise, and there is nothing in a
        // generated page worth preserving - it is rebuilt from the same rulesets either way.
        var removed = await db.WikiPages
            .Where(p => p.ModId == mod.Id && p.Kind == WikiKind.Generated)
            .ExecuteDeleteAsync(ct);

        int written = 0, kept = 0, skipped = 0;
        var seen = new HashSet<(string, string)>();
        var fresh = new List<WikiPage>();

        foreach (var row in file.Pages)
        {
            if (!Slugs.IsValid(row.Slug) || string.IsNullOrWhiteSpace(row.Lang) || string.IsNullOrWhiteSpace(row.Title))
            {
                skipped++;
                continue;
            }
            var key = (row.Slug, row.Lang);
            if (byHand.Contains(key)) { kept++; continue; }
            if (!seen.Add(key)) { skipped++; continue; }   // the file names one address twice
            fresh.Add(new WikiPage
            {
                ModId = mod.Id,
                Slug = row.Slug,
                Lang = row.Lang,
                Title = Cut(row.Title, CommunityLimits.TitleMax),
                Body = Cut(row.Body, CommunityLimits.ArticleMax),
                Section = Cut(row.Section ?? "", CommunityLimits.SlugMax),
                Kind = WikiKind.Generated,
                Source = Cut(row.Source ?? "", 256),
                SourceVersion = mod.Version,
                CreatedAt = now,
                UpdatedAt = now,
            });
            written++;
            if (fresh.Count >= 500) await FlushAsync(fresh, ct);
        }
        await FlushAsync(fresh, ct);

        mod.UpdatedAt = now;
        await db.SaveChangesAsync(ct);
        return new Report(written, removed, kept, skipped);
    }

    async Task FlushAsync(List<WikiPage> pages, CancellationToken ct)
    {
        if (pages.Count == 0) return;
        db.WikiPages.AddRange(pages);
        await db.SaveChangesAsync(ct);
        foreach (var p in pages) db.Entry(p).State = EntityState.Detached;
        pages.Clear();
    }

    static string Cut(string s, int max) => s.Length <= max ? s : s[..max];
}
