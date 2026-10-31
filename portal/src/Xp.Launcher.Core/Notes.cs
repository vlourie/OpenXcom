using System.Text.RegularExpressions;
using Xp.Manifest;

namespace Xp.Launcher.Core;

/// <summary>
/// "What's new" on the home page: every release one update brings (or brought), not only the last one -
/// a player six releases behind gets the six, newest first.
/// </summary>
public static partial class NoteRange
{
    [GeneratedRegex(@"^(\d+)\.(\d+)\.(\d+)(?:-(\d+))?$")]
    private static partial Regex VersionRx();

    /// <summary>
    /// The history (newest first) from <paramref name="latest"/> down to, not including, <paramref name="before"/> -
    /// the version the player had before the update. No <paramref name="before"/> (a fresh install, nothing kept) -
    /// the latest alone; <paramref name="latest"/> not in the history - nothing, the caller shows the manifest's own text.
    /// </summary>
    public static List<ReleaseNote> Since(IReadOnlyList<ReleaseNote> newestFirst, string latest, string? before)
    {
        var range = new List<ReleaseNote>();
        int start = -1;
        for (int i = 0; i < newestFirst.Count && start < 0; i++)
            if (newestFirst[i].Version == latest) start = i;
        if (start < 0) return range;
        for (int i = start; i < newestFirst.Count; i++)
        {
            var r = newestFirst[i];
            // the version the player had may be revoked and missing from the history: then the first one older stops too
            if (i > start && (before is null || r.Version == before || Compare(r.Version, before) is <= 0)) break;
            range.Add(r);
        }
        return range;
    }

    /// <summary>"2026.10.20-17" against "2026.10.21": number by number, no suffix - the first of the day; null - not of that form.</summary>
    public static int? Compare(string a, string b)
    {
        if (Key(a) is not { } x || Key(b) is not { } y) return null;
        for (int i = 0; i < 4; i++)
            if (x[i] != y[i]) return x[i].CompareTo(y[i]);
        return 0;
    }

    static long[]? Key(string v)
    {
        var m = VersionRx().Match(v.Trim());
        if (!m.Success) return null;
        var k = new long[4];
        for (int i = 0; i < 3; i++)
            if (!long.TryParse(m.Groups[i + 1].Value, out k[i])) return null;
        k[3] = m.Groups[4].Success && long.TryParse(m.Groups[4].Value, out var n) ? n : 1;
        return k;
    }
}

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
