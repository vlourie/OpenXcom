using System.Text.Json;
using System.Text.RegularExpressions;
using Xp.Portal.Site;

namespace Xp.Portal.Tests;

/// <summary>
/// Pictures of the mod pages: every card image and every picture inside a description, in both languages, is a
/// file the site serves. A name typed into deploy/seed/community.json without its file would show as a broken
/// picture only on the server. Needs no database.
/// </summary>
public sealed partial class ModArtTests
{
    static readonly string Portal = Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", "..");
    static readonly string SeedFile = Path.Combine(Portal, "deploy", "seed", "community.json");
    static readonly string WebRoot = Path.Combine(Portal, "src", "Xp.Portal", "wwwroot");

    [GeneratedRegex("<img src=\"(/img/mods/[^\"]+)\"")]
    private static partial Regex ImgRx();

    [Fact]
    public void Every_mod_picture_named_in_the_catalogue_is_on_the_site()
    {
        using var doc = JsonDocument.Parse(File.ReadAllText(SeedFile));
        var md = new Markup();
        var seen = 0;
        foreach (var mod in doc.RootElement.GetProperty("mods").EnumerateArray())
        {
            var slug = mod.GetProperty("slug").GetString();
            if (mod.GetProperty("image").GetString() is { Length: > 0 } card)
            {
                Assert.True(File.Exists(Path.Combine(WebRoot, "img", "mods", card)), $"{slug}: no card picture img/mods/{card}");
                seen++;
            }
            foreach (var lang in mod.GetProperty("texts").EnumerateObject())
            {
                var html = md.Render(lang.Value.GetProperty("body").GetString()).Value ?? "";
                foreach (Match m in ImgRx().Matches(html))
                {
                    var file = Path.Combine(WebRoot, m.Groups[1].Value.TrimStart('/').Replace('/', Path.DirectorySeparatorChar));
                    Assert.True(File.Exists(file), $"{slug} ({lang.Name}): no picture {m.Groups[1].Value}");
                    seen++;
                }
            }
        }
        Assert.True(seen >= 5, "the catalogue names hardly any pictures - is the check reading the right file?");
    }
}
