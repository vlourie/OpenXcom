using System.Text.RegularExpressions;

namespace Xp.Portal.Tickets;

/// <summary>
/// The language a ticket is written in: the game's language for F8 and crash reports, the site's for
/// web tickets. Kept as the tag the game uses ("ru", "en-US", "pt-BR"); the queue groups by the part
/// before the dash, so en-US and en-GB land with the same people.
/// </summary>
public static partial class TicketLanguage
{
    public const int Max = 16;

    [GeneratedRegex("^[a-z]{2,3}(-[a-z0-9]{2,8}){0,2}$", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant)]
    private static partial Regex Tag();

    /// <summary>"EN_us" → "en-US", "zh-hans-cn" → "zh-Hans-CN"; null for empty; throws on anything else.</summary>
    public static string? Normalize(string? tag)
    {
        if (string.IsNullOrWhiteSpace(tag)) return null;
        tag = tag.Trim().Replace('_', '-');
        if (tag.Length > Max || !Tag().IsMatch(tag)) throw new TicketException("language_invalid", "language must be a tag like ru, en-US");
        var parts = tag.Split('-');
        parts[0] = parts[0].ToLowerInvariant();
        for (int i = 1; i < parts.Length; i++)
            parts[i] = parts[i].Length == 4 ? char.ToUpperInvariant(parts[i][0]) + parts[i][1..].ToLowerInvariant()
                : parts[i].ToUpperInvariant();
        return string.Join('-', parts);
    }

    /// <summary>The group a tag belongs to in the queue: "en-US" → "en".</summary>
    public static string Primary(string tag)
    {
        var dash = tag.IndexOf('-');
        return dash < 0 ? tag : tag[..dash];
    }
}
