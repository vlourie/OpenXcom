using System.Text;
using Markdig;
using Microsoft.AspNetCore.Html;
using Xp.Portal.Data;

namespace Xp.Portal.Site;

/// <summary>
/// Markdown for wiki articles, mod descriptions and forum posts.
///
/// Raw HTML is disabled in the pipeline, so a post that contains &lt;script&gt; renders as the text
/// &lt;script&gt; and never as a tag. That is the whole defence against someone dressing a post up as
/// part of the site, and it must stay: the content security policy blocks external scripts, but an
/// inline one would be same-origin.
/// </summary>
public sealed class Markup
{
    readonly MarkdownPipeline _pipeline = new MarkdownPipelineBuilder()
        .DisableHtml()
        .UseAutoLinks()
        .UsePipeTables()
        .UseEmphasisExtras()
        .UseListExtras()
        .UseFootnotes()
        .Build();

    public HtmlString Render(string? markdown) =>
        new(string.IsNullOrWhiteSpace(markdown) ? "" : Markdown.ToHtml(markdown, _pipeline));

    /// <summary>First sentences of an article, for a list or a card. No markup at all.</summary>
    public static string Excerpt(string? markdown, int max = 220)
    {
        if (string.IsNullOrWhiteSpace(markdown)) return "";
        var text = Markdown.ToPlainText(markdown).Replace('\n', ' ').Replace('\r', ' ');
        while (text.Contains("  ", StringComparison.Ordinal)) text = text.Replace("  ", " ", StringComparison.Ordinal);
        text = text.Trim();
        if (text.Length <= max) return text;
        var cut = text.LastIndexOf(' ', Math.Min(max, text.Length - 1));
        return text[..(cut > max / 2 ? cut : max)] + "…";
    }
}

/// <summary>
/// Addresses made of a title. A Russian title has to become a latin address, so the letters are
/// transliterated rather than dropped: "Гаусс-пистолет" becomes "gauss-pistolet" and not "--".
/// </summary>
public static class Slugs
{
    static readonly string[] Cyrillic =
    [
        "a", "b", "v", "g", "d", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p",
        "r", "s", "t", "u", "f", "h", "c", "ch", "sh", "sch", "", "y", "", "e", "yu", "ya"
    ];

    public static string Make(string? title, int max = CommunityLimits.SlugMax)
    {
        if (string.IsNullOrWhiteSpace(title)) return "";
        var sb = new StringBuilder(title.Length);
        foreach (var raw in title.Trim().ToLowerInvariant())
        {
            var ch = raw == 'ё' ? 'е' : raw;
            if (ch is >= 'a' and <= 'z' or >= '0' and <= '9') sb.Append(ch);
            else if (ch >= 'а' && ch <= 'я') sb.Append(Cyrillic[ch - 'а']);
            else if (sb.Length > 0 && sb[^1] != '-') sb.Append('-');
        }
        var s = sb.ToString().Trim('-');
        if (s.Length > max) s = s[..max].TrimEnd('-');
        return s;
    }

    /// <summary>True for an address we are willing to route: lowercase, digits, single dashes.</summary>
    public static bool IsValid(string? slug) =>
        !string.IsNullOrEmpty(slug) && slug.Length <= CommunityLimits.SlugMax && slug == Make(slug, slug.Length);
}
