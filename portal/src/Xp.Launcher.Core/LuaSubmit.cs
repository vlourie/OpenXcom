using System.ComponentModel;
using System.Diagnostics;
using System.IO.Compression;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;
using Xp.Manifest;

namespace Xp.Launcher.Core;

/// <summary>What the check says about a mod: a code (the key of the words), the file it is about, a detail from the engine or the code.</summary>
public sealed record LuaNote(string Code, string? File = null, string? Detail = null);

public sealed record LuaFile(string Path, long Size);

/// <summary>What would go, and what the author should know before it does. Any error: nothing goes.</summary>
public sealed class LuaPrecheck
{
    public required ModMetadata Meta { get; init; }
    public List<LuaFile> Files { get; } = [];
    public List<LuaNote> Errors { get; } = [];
    public List<LuaNote> Signals { get; } = [];
    public bool CanSend => Errors.Count == 0;
    public long Total => Files.Sum(f => f.Size);
}

public sealed record LuaModSubmitted(long Number, string DisplayNumber, string Status);

/// <summary>One offered mod as the site tells its author. Status: queue, check, review, needsInfo, approved, rejected.</summary>
public sealed record LuaModRow(long Number, string DisplayNumber, string Mod, string Version, string Status, string? Reason,
    DateTimeOffset CreatedAt, DateTimeOffset UpdatedAt);

internal sealed record LuaModMeta(string Id, string Version, string Description, string License, bool RightsConfirmed,
    string Language, string? GameVersion, string? LauncherVersion, string? Precheck);

/// <summary>
/// "Submit" (docs/portal/LUA_MODS.md §8.1): the steps 1-3 of the check on the author's machine, so that the author hears it before anything
/// goes, then the archive. tools/lua_mod_check.py decides in isolation; a signal here only warns. Nothing here runs the mod's code:
/// the engine only compiles the Lua and reads the YAML (-modcheck, src/Engine/ModCheck.cpp).
/// </summary>
public static partial class LuaSubmit
{
    const int LongLine = 2000, LongString = 4000, Escapes = 200;
    static readonly TimeSpan EngineLimit = TimeSpan.FromSeconds(120);

    static readonly HashSet<string> EscapeNames = ["io", "os", "debug", "package", "coroutine"];
    static readonly HashSet<string> EscapeCalls = ["require", "load", "loadstring", "loadfile", "dofile", "collectgarbage"];
    static readonly HashSet<string> StringMethods = ["byte", "find", "format", "gmatch", "gsub", "len", "lower", "match", "rep", "reverse", "sub", "upper"];
    static readonly HashSet<string> Engines = ["", "Extended", "OXCE-HD"];

    [GeneratedRegex(@"\b([A-Za-z_]\w*)\s*\.")] private static partial Regex FieldRx();
    [GeneratedRegex(@"(?<![.:\w])([A-Za-z_]\w*)\s*\(")] private static partial Regex CallRx();
    [GeneratedRegex(@"\bstring\s*\.\s*dump\b")] private static partial Regex DumpRx();
    [GeneratedRegex(@"\bgame\s*\.\s*(\w+)")] private static partial Regex GameRx();
    [GeneratedRegex(@":\s*([A-Za-z_]\w*)\s*[(""'{]")] private static partial Regex MethodRx();
    [GeneratedRegex(@"\bgame\s*\.\s*on\s*\(\s*[""']([^""']*)[""']")] private static partial Regex EventRx();
    [GeneratedRegex(@"[A-Za-z0-9+/=]{512,}")] private static partial Regex EncodedRx();
    [GeneratedRegex(@"\\(?:x[0-9a-fA-F]{2}|\d{1,3})")] private static partial Regex EscapeRx();

    /// <summary>The names of the API as the engine's table has them (tools/lua_api_doc.py writes this file).</summary>
    sealed class Names
    {
        public int Api = 1;
        public readonly HashSet<string> Event = [], Const = [], Method = [];

        public static readonly Lazy<Names> Embedded = new(() =>
        {
            using var s = typeof(LuaSubmit).Assembly.GetManifestResourceStream("lua_api.names.txt") ?? throw new InvalidOperationException("no resource lua_api.names.txt");
            using var r = new StreamReader(s);
            var n = new Names();
            foreach (var line in r.ReadToEnd().Split('\n'))
            {
                var part = line.TrimEnd('\r').Split('\t');
                if (part.Length != 2) continue;
                if (part[0] == "api") n.Api = int.Parse(part[1]);
                else if (part[0] == "event") n.Event.Add(part[1]);
                else if (part[0] == "const") n.Const.Add(part[1]);
                else if (part[0] == "method") n.Method.Add(part[1]);
            }
            return n;
        });
    }

    /// <summary>The list of files, the rules of the archive, the metadata and a look over the Lua. Every file there is, none left out silently.</summary>
    public static LuaPrecheck Prepare(string modDir)
    {
        var meta = Path.Combine(modDir, "metadata.yml");
        var text = File.Exists(meta) ? File.ReadAllText(meta) : null;
        var p = new LuaPrecheck { Meta = ModMetadata.Parse(text ?? "", "") };
        Walk(modDir, "", p);
        p.Files.Sort((a, b) => string.CompareOrdinal(a.Path, b.Path));
        foreach (var e in LuaModArchive.Check(p.Files.Select(f => (f.Path, f.Size)).ToList()))
            p.Errors.Add(new(e.Code, e.File));
        CheckMetadata(text, p);
        foreach (var f in p.Files.Where(f => f.Path.EndsWith(".lua", StringComparison.OrdinalIgnoreCase) && f.Size <= LuaModArchive.MaxFile))
            ScanLua(f.Path, File.ReadAllText(Path.Combine(modDir, f.Path)), p);
        return p;
    }

    /// <summary>A link would make the archive hold what is not in the folder, and the author could not see it in the list.</summary>
    static void Walk(string dir, string rel, LuaPrecheck p)
    {
        var options = new EnumerationOptions { AttributesToSkip = 0, IgnoreInaccessible = false, ReturnSpecialDirectories = false };
        foreach (var e in new DirectoryInfo(dir).EnumerateFileSystemInfos("*", options))
        {
            var name = rel + e.Name;
            if (e.Attributes.HasFlag(FileAttributes.ReparsePoint)) p.Errors.Add(new("path_link", name));
            else if (e is DirectoryInfo d) Walk(d.FullName, name + "/", p);
            else p.Files.Add(new(name, ((FileInfo)e).Length));
        }
    }

    static void CheckMetadata(string? text, LuaPrecheck p)
    {
        if (text is null)
        {
            p.Errors.Add(new("metadata_missing", "metadata.yml"));
            return;
        }
        var m = p.Meta;
        if (!LuaModArchive.IsModId(m.Id)) p.Errors.Add(new("metadata_id", "metadata.yml", m.Id));
        // ModMetadata fills in the engine's default, and the catalog must know whose mod this is
        if (!text.Split('\n').Any(l => l.StartsWith("master:", StringComparison.Ordinal))) p.Errors.Add(new("metadata_master", "metadata.yml"));
        else if (m.AnyMaster) p.Signals.Add(new("master_any", "metadata.yml"));
        if (m.Version.Length == 0) p.Errors.Add(new("metadata_version", "metadata.yml"));
        if (m.LuaApi < 1 || m.LuaApi > Names.Embedded.Value.Api) p.Errors.Add(new("metadata_luaapi", "metadata.yml", m.LuaApi.ToString()));
        if (!Engines.Contains(m.Engine)) p.Errors.Add(new("metadata_engine", "metadata.yml", m.Engine));
        if (m.IsMaster) p.Signals.Add(new("is_master", "metadata.yml"));
        if (!p.Files.Any(f => f.Path == "lua/main.lua")) p.Errors.Add(new("lua_main_missing", "lua/main.lua"));
    }

    /// <summary>The code without comments and strings, and the strings apart. Not a lexer: the engine compiles the file itself.</summary>
    static (string Code, List<string> Strings) Strip(string t)
    {
        var code = new StringBuilder(t.Length);
        var strings = new List<string>();
        int i = 0, n = t.Length;
        // [[ or [==[ at i: the closing bracket, or null
        static string? LongOpen(string s, int at)
        {
            int j = at + 1;
            while (j < s.Length && s[j] == '=') j++;
            return j < s.Length && s[j] == '[' ? "]" + new string('=', j - at - 1) + "]" : null;
        }
        while (i < n)
        {
            char c = t[i];
            if (c == '-' && i + 1 < n && t[i + 1] == '-')
            {
                var close = i + 2 < n && t[i + 2] == '[' ? LongOpen(t, i + 2) : null;
                int end = close is not null ? t.IndexOf(close, i, StringComparison.Ordinal) : t.IndexOf('\n', i);
                i = end < 0 ? n : end + (close?.Length ?? 0);
                continue;
            }
            if (c == '[' && LongOpen(t, i) is { } shut)
            {
                int from = i + shut.Length;
                int end = t.IndexOf(shut, from, StringComparison.Ordinal);
                if (end < 0) end = n;
                strings.Add(t[from..end]);
                code.Append("\"\"");
                i = end + shut.Length;
                continue;
            }
            if (c is '"' or '\'')
            {
                int j = i + 1;
                while (j < n && t[j] != c && t[j] != '\n') j += t[j] == '\\' ? 2 : 1;
                strings.Add(t[(i + 1)..Math.Min(j, n)]);
                code.Append("\"\"");
                i = j + 1;
                continue;
            }
            code.Append(c);
            i++;
        }
        return (code.ToString(), strings);
    }

    static void ScanLua(string path, string text, LuaPrecheck p)
    {
        var names = Names.Embedded.Value;
        var (code, strings) = Strip(text);
        var found = new HashSet<LuaNote>();
        if (!path.StartsWith("lua/", StringComparison.Ordinal)) found.Add(new("lua_outside", path));
        foreach (Match m in FieldRx().Matches(code))
            if (EscapeNames.Contains(m.Groups[1].Value)) found.Add(new("api_escape", path, m.Groups[1].Value));
        foreach (Match m in CallRx().Matches(code))
            if (EscapeCalls.Contains(m.Groups[1].Value)) found.Add(new("api_escape", path, m.Groups[1].Value));
        if (DumpRx().IsMatch(code)) found.Add(new("api_escape", path, "string.dump"));
        foreach (Match m in GameRx().Matches(code))
            if (m.Groups[1].Value is not ("on" or "log") && !names.Const.Contains(m.Groups[1].Value)) found.Add(new("api_unknown", path, "game." + m.Groups[1].Value));
        foreach (Match m in MethodRx().Matches(code))
            if (!names.Method.Contains(m.Groups[1].Value) && !StringMethods.Contains(m.Groups[1].Value)) found.Add(new("api_unknown", path, ":" + m.Groups[1].Value + "()"));
        foreach (Match m in EventRx().Matches(text))
            if (!names.Event.Contains(m.Groups[1].Value)) found.Add(new("api_event", path, m.Groups[1].Value));
        if (text.Split('\n').Any(l => l.Length > LongLine)) found.Add(new("long_line", path));
        foreach (var s in strings)
        {
            if (s.Length > LongString) found.Add(new("long_string", path));
            if (EncodedRx().IsMatch(s) || EscapeRx().Count(s) > Escapes) found.Add(new("encoded_block", path));
        }
        p.Signals.AddRange(found);
    }

    /// <summary>
    /// The engine compiles every Lua file and reads the YAML, without running anything. A game older than this launcher would start
    /// as a game on the unknown word: that is looked for in the exe first. A failure of the engine itself is only a signal, not the mod's fault.
    /// </summary>
    public static async Task EngineCheckAsync(string exe, string modDir, LuaPrecheck p, CancellationToken ct)
    {
        if (!File.Exists(exe) || !KnowsModCheck(exe))
        {
            p.Signals.Add(new("engine_old"));
            return;
        }
        var work = Path.Combine(Path.GetTempPath(), "xp-lua-" + Guid.NewGuid().ToString("N")[..8]);
        Directory.CreateDirectory(work);
        try
        {
            var report = Path.Combine(work, "report.txt");
            var empty = Directory.CreateDirectory(Path.Combine(work, "empty")).FullName;
            if (await RunEngineAsync(exe, empty, report, ct) != 0 || !File.Exists(report))
            {
                p.Signals.Add(new("engine_failed"));
                return;
            }
            File.Delete(report);
            if (await RunEngineAsync(exe, modDir, report, ct) is null)
            {
                p.Errors.Add(new("parser_hang"));
                return;
            }
            var lines = File.Exists(report) ? File.ReadAllLines(report) : [];
            if (lines.Length == 0 || !lines[^1].StartsWith("done\t", StringComparison.Ordinal))
            {
                p.Errors.Add(new("parser_crash", null, lines.Length.ToString()));
                return;
            }
            foreach (var line in lines[..^1])
            {
                var part = line.Split('\t');
                if (part[0] != "bad" || part.Length < 3) continue;
                p.Errors.Add(new(part[1].EndsWith(".lua", StringComparison.OrdinalIgnoreCase) ? "lua_syntax" : "yaml_broken", part[1], part[2]));
            }
        }
        catch (Win32Exception) { p.Signals.Add(new("engine_failed")); }
        finally
        {
            try { Directory.Delete(work, recursive: true); }
            catch (Exception e) when (e is IOException or UnauthorizedAccessException) { }
        }
    }

    static bool KnowsModCheck(string exe)
    {
        // a word in the exe's data; a game that cannot be read is treated as one that does not know it
        try { return File.ReadAllBytes(exe).AsSpan().IndexOf("-modcheck"u8) >= 0; }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { return false; }
    }

    /// <summary>The exit code, or null when the limit ran out and the engine was stopped.</summary>
    static async Task<int?> RunEngineAsync(string exe, string folder, string report, CancellationToken ct)
    {
        var psi = new ProcessStartInfo(exe) { UseShellExecute = false, CreateNoWindow = true, WorkingDirectory = Path.GetDirectoryName(exe)! };
        psi.ArgumentList.Add("-modcheck");
        psi.ArgumentList.Add(folder);
        psi.ArgumentList.Add(report);
        using var proc = Process.Start(psi) ?? throw new Win32Exception("the game did not start");
        using var limit = CancellationTokenSource.CreateLinkedTokenSource(ct);
        limit.CancelAfter(EngineLimit);
        try
        {
            await proc.WaitForExitAsync(limit.Token);
            return proc.ExitCode;
        }
        catch (OperationCanceledException)
        {
            proc.Kill(entireProcessTree: true);
            ct.ThrowIfCancellationRequested();
            return null;
        }
    }

    /// <summary>The archive: its root is the mod's root, exactly the files of the list. False: it came out larger than the site takes.</summary>
    public static bool Pack(string modDir, LuaPrecheck p, string target)
    {
        using (var fs = new FileStream(target, FileMode.Create, FileAccess.Write))
        using (var zip = new ZipArchive(fs, ZipArchiveMode.Create))
            foreach (var f in p.Files)
                zip.CreateEntryFromFile(Path.Combine(modDir, f.Path), f.Path, CompressionLevel.Optimal);
        return new FileInfo(target).Length <= LuaModArchive.MaxArchive;
    }

    /// <summary>The same mod sent again by the same person is a retry, whatever the network did to the first one.</summary>
    public static string RetryKey(string token, string archive, string description)
    {
        using var s = File.OpenRead(archive);
        var body = Convert.ToHexStringLower(SHA256.HashData(s));
        return "lua-" + Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes($"{token}\n{body}\n{description}")));
    }

    /// <summary>The signals in one line for the team's queue: which ones, not the code.</summary>
    public static string PrecheckLine(LuaPrecheck p) =>
        p.Signals.Count == 0 ? "clean" : string.Join(", ", p.Signals.Select(s => s.Code).Distinct().Order(StringComparer.Ordinal));
}

public sealed partial class PortalClient
{
    /// <summary>Sends the archive. The site checks the rules again and keeps nothing it refuses.</summary>
    public async Task<LuaModSubmitted> SubmitLuaModAsync(string token, LuaPrecheck p, string archive, string description, string license, string language,
        string? gameVersion, string? launcherVersion, CancellationToken ct)
    {
        var meta = new LuaModMeta(p.Meta.Id, p.Meta.Version, description, license, true, language, gameVersion, launcherVersion, LuaSubmit.PrecheckLine(p));
        await using var file = File.OpenRead(archive);
        using var form = new MultipartFormDataContent();
        form.Add(new StringContent(JsonSerializer.Serialize(meta, LuaJson.Default.LuaModMeta), Encoding.UTF8, "application/json"), "meta");
        var part = new StreamContent(file);
        part.Headers.ContentType = new MediaTypeHeaderValue("application/zip");
        form.Add(part, "file", "mod.zip");
        using var msg = new HttpRequestMessage(HttpMethod.Post, new Uri(BaseUri, "api/v1/lua-mods")) { Content = form };
        msg.Headers.Add(DeviceTokenHeader, token);
        msg.Headers.Add("Idempotency-Key", LuaSubmit.RetryKey(token, archive, description));
        using var resp = await Http.SendAsync(msg, ct);
        await ThrowIfFailedAsync(resp, ct);
        return await resp.Content.ReadFromJsonAsync(LuaJson.Default.LuaModSubmitted, ct)
               ?? throw new PortalException((int)resp.StatusCode, "bad_response", "empty answer");
    }

    /// <summary>The author's own offered mods, newest first.</summary>
    public async Task<List<LuaModRow>> MyLuaModsAsync(string token, CancellationToken ct)
    {
        using var msg = new HttpRequestMessage(HttpMethod.Get, new Uri(BaseUri, "api/v1/lua-mods"));
        msg.Headers.Add(DeviceTokenHeader, token);
        using var resp = await Http.SendAsync(msg, ct);
        await ThrowIfFailedAsync(resp, ct);
        return await resp.Content.ReadFromJsonAsync(LuaJson.Default.ListLuaModRow, ct) ?? [];
    }
}

[JsonSourceGenerationOptions(PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase, PropertyNameCaseInsensitive = true)]
[JsonSerializable(typeof(LuaModMeta))]
[JsonSerializable(typeof(LuaModSubmitted))]
[JsonSerializable(typeof(List<LuaModRow>))]
internal sealed partial class LuaJson : JsonSerializerContext
{
}
