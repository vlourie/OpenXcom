using System.Text;

namespace Xp.Launcher.Core;

/// <summary>
/// The launcher's word to a running game: a private message or a mention came in. Two lines in
/// launcher/chat.txt of the game folder: a counter that only grows, then "nick: the start of the text". The game
/// looks at the file's date every two seconds and shows a small plate in the top right corner for six seconds
/// for every new counter (option oxceHdChatNotice, src/Engine/HdChatNotice.h); the file it finds at its own start
/// is an old message and is not shown. The text comes from other players: it is cut here and the game cuts it
/// again, as only a string to show. Like update.txt the file is the launcher's own, in its state folder.
/// The caller writes only while the game runs and clears the file when the launcher exits.
/// </summary>
public static class ChatNotice
{
    /// <summary>The longest line ("nick: text") in characters; the game shows less, it cuts to the plate's width.</summary>
    public const int MaxLine = 200;
    /// <summary>The longest nick in characters; the rest of the line is the text's.</summary>
    public const int MaxNick = 32;

    static readonly object Gate = new();
    static long _last;

    public static string PathIn(GamePaths p) => Path.Combine(p.StateDir, "chat.txt");

    /// <summary>
    /// Replaces the file with the counter and "nick: text". The counter is above the last one written in this run and
    /// above the one in the file, and never below the clock's seconds, so it does not repeat after a clear and a new run.
    /// </summary>
    /// <returns>The counter written, or 0 when there was nothing to show or the file could not be written.</returns>
    public static long Write(GamePaths p, string nick, string text)
    {
        var line = Line(nick, text);
        if (line.Length == 0) return 0;
        lock (Gate)
        {
            var path = PathIn(p);
            long counter = Math.Max(_last, Math.Max(CounterIn(path), DateTimeOffset.UtcNow.ToUnixTimeSeconds() - 1)) + 1;
            var bytes = new UTF8Encoding(false).GetBytes(counter.ToString(System.Globalization.CultureInfo.InvariantCulture) + "\n" + line + "\n");
            // the game may have the file open for a moment: the replace then fails, and the next try goes through
            for (var attempt = 0; attempt < 4; attempt++)
            {
                try
                {
                    FileUtil.WriteAtomic(path, bytes);
                    _last = counter;
                    return counter;
                }
                catch (Exception e) when (e is IOException or UnauthorizedAccessException)
                {
                    Thread.Sleep(40);
                }
            }
            return 0;
        }
    }

    /// <summary>The game is closed or the launcher exits: nothing to show, nothing left to be taken for new.</summary>
    public static void Clear(GamePaths p)
    {
        try { File.Delete(PathIn(p)); }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { }
    }

    /// <summary>
    /// "nick: text" on one line: control characters and line breaks are spaces, runs of spaces are one, the ends trimmed,
    /// the nick cut to <see cref="MaxNick"/> and the line to <see cref="MaxLine"/> (never in the middle of a surrogate pair).
    /// Empty when there is no text.
    /// </summary>
    public static string Line(string? nick, string? text)
    {
        var body = Flat(text);
        if (body.Length == 0) return "";
        var who = Cut(Flat(nick), MaxNick);
        var line = who.Length == 0 ? body : who + ": " + body;
        return Cut(line, MaxLine).TrimEnd();
    }

    static string Flat(string? s)
    {
        if (string.IsNullOrEmpty(s)) return "";
        var sb = new StringBuilder(s.Length);
        foreach (var c in s)
        {
            if (char.IsControl(c) || char.IsWhiteSpace(c) || Hidden(c))
            {
                if (sb.Length > 0 && sb[^1] != ' ') sb.Append(' ');
            }
            else sb.Append(c);
        }
        return sb.ToString().TrimEnd();
    }

    /// <summary>Zero-width marks, line and paragraph separators, direction overrides and isolates, the byte order mark.</summary>
    static bool Hidden(char c) => c is (char)0x200B or (char)0x200E or (char)0x200F or (char)0x2028 or (char)0x2029 or (char)0xFEFF
        || (c >= (char)0x202A && c <= (char)0x202E) || (c >= (char)0x2066 && c <= (char)0x2069);

    static string Cut(string s, int max)
    {
        if (s.Length <= max) return s;
        var n = max;
        if (char.IsHighSurrogate(s[n - 1])) n--;
        return s[..n];
    }

    static long CounterIn(string path)
    {
        try
        {
            if (!File.Exists(path)) return 0;
            using var r = new StreamReader(path, Encoding.UTF8);
            return long.TryParse(r.ReadLine()?.Trim(), out var n) && n > 0 ? n : 0;
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { return 0; }
    }
}
