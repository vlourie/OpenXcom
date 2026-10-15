using System.Text.RegularExpressions;

namespace Xp.Launcher.Core;

public enum NoteKind { Heading, Bullet, Paragraph }

/// <summary>One block of a "What's new" or of the roadmap: a heading (Level 1-3), a list item
/// (Level = nesting, 0 at the margin) or a paragraph.</summary>
public sealed record NoteBlock(NoteKind Kind, int Level, string Text);

/// <summary>
/// The little Markdown the history and the roadmap are written in, for the launcher, which has no
/// Markdown renderer: headings, list items (- * — – •, numbered too), paragraphs. Everything else
/// stays text, so a line the reader does not know shows as written rather than disappearing.
/// The site renders the same text with Markdig.
/// </summary>
public static partial class NoteText
{
    [GeneratedRegex(@"^(#{1,6})\s+(.*)$")]
    private static partial Regex HeadingRx();

    [GeneratedRegex(@"^(\s*)(?:[-*•—–]|\d+[.)])\s+(.*)$")]
    private static partial Regex BulletRx();

    public static List<NoteBlock> Parse(string? text)
    {
        var blocks = new List<NoteBlock>();
        if (string.IsNullOrWhiteSpace(text)) return blocks;
        NoteBlock? open = null;     // the block a following plain line continues

        foreach (var raw in text.Replace("\r\n", "\n").Split('\n'))
        {
            var line = raw.TrimEnd();
            if (line.Trim().Length == 0) { Close(); continue; }
            if (HeadingRx().Match(line.Trim()) is { Success: true } h)
            {
                Close();
                blocks.Add(new NoteBlock(NoteKind.Heading, Math.Min(h.Groups[1].Length, 3), h.Groups[2].Value.Trim().TrimEnd('#').Trim()));
                continue;
            }
            if (BulletRx().Match(line) is { Success: true } b)
            {
                Close();
                var number = Regex.Match(line.TrimStart(), @"^\d+[.)]");
                var item = (number.Success ? number.Value + " " : "") + b.Groups[2].Value.Trim();
                open = new NoteBlock(NoteKind.Bullet, Math.Min(b.Groups[1].Value.Replace("\t", "  ").Length / 2, 3), item);
                continue;
            }
            // a plain line: carries on the open item or paragraph, or starts a paragraph
            open = open is null ? new NoteBlock(NoteKind.Paragraph, 0, line.Trim()) : open with { Text = open.Text + " " + line.Trim() };
        }
        Close();
        return blocks;

        void Close()
        {
            if (open is not null) blocks.Add(open);
            open = null;
        }
    }

    /// <summary>The text in the player's language, else Russian (the mod's own), else whatever there is.</summary>
    public static string Pick(IReadOnlyDictionary<string, string> texts, string lang) =>
        texts.TryGetValue(lang, out var t) && !string.IsNullOrWhiteSpace(t) ? t
        : texts.TryGetValue("ru", out var ru) ? ru
        : texts.Values.FirstOrDefault() ?? "";

    /// <summary>"**bold**" split into runs: (text, bold). An unclosed ** stays as written.</summary>
    public static List<(string Text, bool Bold)> Runs(string text)
    {
        var parts = text.Split("**");
        if (parts.Length % 2 == 0) return [(text, false)];
        var runs = new List<(string, bool)>();
        for (int i = 0; i < parts.Length; i++)
            if (parts[i].Length > 0) runs.Add((parts[i], i % 2 == 1));
        return runs;
    }
}
