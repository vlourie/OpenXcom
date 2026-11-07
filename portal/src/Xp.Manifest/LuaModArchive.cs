using System.IO.Compression;
using System.Text.RegularExpressions;

namespace Xp.Manifest;

/// <summary>One reason an archive of a Lua mod is refused: a stable code, and the entry when it is about one.</summary>
public sealed record LuaArchiveProblem(string Code, string? File = null);

/// <summary>
/// What an archive of a Lua mod may hold (docs/portal/LUA_MODS.md §8.2, step 1): the launcher says it before sending, the site
/// before storing. tools/lua_mod_check.py has the same list in the isolated check, which is the one that decides.
/// </summary>
public static partial class LuaModArchive
{
    [GeneratedRegex("^[a-z0-9][a-z0-9_-]{0,39}$")]
    private static partial Regex IdRx();

    /// <summary>The id of a mod for the catalog: the folder cm-&lt;id&gt; is made of it.</summary>
    public static bool IsModId(string? id) => id is not null && IdRx().IsMatch(id);

    public const long MaxArchive = 50L * 1024 * 1024;
    public const long MaxUnpacked = 200L * 1024 * 1024;
    public const long MaxFile = 50L * 1024 * 1024;
    public const int MaxFiles = 2000;

    public static readonly IReadOnlySet<string> Allowed = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
        { ".lua", ".yml", ".rul", ".txt", ".md", ".png", ".wav" };

    static readonly HashSet<string> Executable = new(StringComparer.OrdinalIgnoreCase)
    {
        ".exe", ".dll", ".bat", ".cmd", ".com", ".ps1", ".psm1", ".scr", ".vbs", ".vbe", ".js", ".jse", ".msi", ".lnk", ".sh", ".jar",
        ".pyd", ".py", ".hta", ".wsf", ".reg", ".cpl", ".sys", ".so",
    };

    static readonly HashSet<string> Reserved = new(StringComparer.OrdinalIgnoreCase)
    {
        "con", "prn", "aux", "nul", "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8", "com9",
        "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9",
    };

    /// <summary>The code of what is wrong with the name of an entry, or null.</summary>
    public static string? PathProblem(string name)
    {
        if (name.Contains('\\') || name.Contains(':') || name.StartsWith('/') || name.Contains('\0')) return "path_absolute";
        var parts = name.Split('/');
        if (parts.Contains("..")) return "path_parent";
        foreach (var p in parts)
        {
            if (p != p.Trim() || p.EndsWith('.')) return "path_name";
            if (Reserved.Contains(p.Split('.')[0])) return "path_name";
        }
        var ext = Path.GetExtension(name);
        if (ext.Equals(".luac", StringComparison.OrdinalIgnoreCase)) return "lua_bytecode";
        if (Executable.Contains(ext)) return "file_executable";
        return Allowed.Contains(ext) ? null : "file_type";
    }

    /// <summary>The rules of names and sizes over a list of files: what would go, or what went.</summary>
    public static List<LuaArchiveProblem> Check(IReadOnlyCollection<(string Name, long Size)> files)
    {
        var problems = new List<LuaArchiveProblem>();
        if (files.Count == 0) problems.Add(new("archive_empty"));
        if (files.Count > MaxFiles) problems.Add(new("too_many_files"));
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        long total = 0;
        foreach (var (name, size) in files)
        {
            if (PathProblem(name) is { } code) problems.Add(new(code, name));
            if (size > MaxFile) problems.Add(new("file_too_large", name));
            if (!seen.Add(name)) problems.Add(new("path_duplicate", name));
            total += size;
        }
        if (total > MaxUnpacked) problems.Add(new("unpacked_too_large"));
        return problems;
    }

    /// <summary>
    /// The same rules over the archive's own directory: nothing is unpacked, so what the site reads here is only headers.
    /// The sizes in them can lie: the isolated check reads the files themselves.
    /// </summary>
    public static List<LuaArchiveProblem> CheckZip(Stream archive)
    {
        try
        {
            using var zip = new ZipArchive(archive, ZipArchiveMode.Read, leaveOpen: true);
            var files = zip.Entries.Where(e => !e.FullName.EndsWith('/')).Select(e => (e.FullName, e.Length)).ToList();
            return Check(files);
        }
        catch (InvalidDataException) { return [new("archive_corrupt")]; }
    }

    /// <summary>metadata.yml at the root of the archive, at most 64 KiB, or null.</summary>
    public static ModMetadata? ReadMetadata(Stream archive)
    {
        try
        {
            using var zip = new ZipArchive(archive, ZipArchiveMode.Read, leaveOpen: true);
            var entry = zip.GetEntry("metadata.yml");
            if (entry is null || entry.Length > 64 * 1024) return null;
            using var reader = new StreamReader(entry.Open());
            return ModMetadata.Parse(reader.ReadToEnd(), "");
        }
        catch (InvalidDataException) { return null; }
    }
}
