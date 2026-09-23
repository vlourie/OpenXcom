using System.Reflection;
using System.Text.Json;
using System.Text.Json.Serialization;
using Xp.Manifest;

namespace Xp.Launcher;

/// <summary>User-level settings, in %LOCALAPPDATA%\XPiratezLauncher\settings.json. No secrets here.</summary>
public sealed class Settings
{
    public string? GameDir { get; set; }
    /// <summary>Overrides the built-in repository URL (development, own server).</summary>
    public string? RepoUrl { get; set; }
    public string? Language { get; set; }
    /// <summary>Overrides the built-in portal address for reports (development, own server).</summary>
    public string? PortalUrl { get; set; }
    /// <summary>Folders reports came from besides &lt;game&gt;/user/reports: a game with its user folder elsewhere.</summary>
    public List<string> ReportRoots { get; set; } = new();
    public Dictionary<string, long> LauncherSequence { get; set; } = new();

    public static string Dir => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "XPiratezLauncher");
    static string FilePath => Path.Combine(Dir, "settings.json");

    public static Settings Load()
    {
        try
        {
            return File.Exists(FilePath)
                ? JsonSerializer.Deserialize(File.ReadAllBytes(FilePath), LauncherJson.Default.Settings) ?? new Settings()
                : new Settings();
        }
        catch (JsonException) { return new Settings(); }
    }

    public void Save() => Core.FileUtil.WriteAtomic(FilePath, JsonSerializer.SerializeToUtf8Bytes(this, LauncherJson.Default.Settings));
}

public sealed class Defaults
{
    public string RepoUrl { get; set; } = "";
    public List<string> Channels { get; set; } = new();
    /// <summary>The site that takes F8 and crash reports (its /api/v1).</summary>
    public string PortalUrl { get; set; } = "";
    /// <summary>Per-file limit of the portal (Attachments:MaxFileBytes); a bigger save is zipped, then skipped.</summary>
    public long ReportMaxFileBytes { get; set; }
    /// <summary>"Support the mod's author" (Dioxine) page; empty - the button is shown disabled.</summary>
    public string SupportModUrl { get; set; } = "";
    /// <summary>"Support the HD developers" page; empty - the button is shown disabled.</summary>
    public string SupportHdUrl { get; set; } = "";
}

[JsonSourceGenerationOptions(WriteIndented = true, PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase)]
[JsonSerializable(typeof(Settings))]
[JsonSerializable(typeof(Defaults))]
[JsonSerializable(typeof(Dictionary<string, string>))]
internal sealed partial class LauncherJson : JsonSerializerContext
{
}

/// <summary>What is compiled into the launcher: trusted public keys, default server, version.</summary>
public static class BuiltIn
{
    public static Version Version { get; } = typeof(BuiltIn).Assembly.GetName().Version ?? new Version(0, 0, 0);
    public static string VersionText => $"{Version.Major}.{Version.Minor}.{Version.Build}";

    public static Defaults Defaults { get; } = JsonSerializer.Deserialize(Resource("defaults.json"), LauncherJson.Default.Defaults) ?? new Defaults();

    /// <summary>
    /// Keys from keys/release-keys.txt. Release builds trust only "prod" keys; "dev" keys only in
    /// Debug or with -p:AllowDevKeys=true, so a development key can never ship to players.
    /// </summary>
    public static TrustedKeys Keys { get; } = LoadKeys();

    static TrustedKeys LoadKeys()
    {
        var text = System.Text.Encoding.UTF8.GetString(Resource("release-keys.txt"));
        var keys = new List<string>();
        foreach (var raw in text.Split('\n'))
        {
            var line = raw.Trim();
            if (line.Length == 0 || line.StartsWith('#')) continue;
            var parts = line.Split(' ', 2, StringSplitOptions.TrimEntries);
            if (parts.Length != 2) continue;
            if (parts[0] == "prod") keys.Add(parts[1]);
#if ALLOW_DEV_KEYS
            else if (parts[0] == "dev") keys.Add(parts[1]);
#endif
        }
        return new TrustedKeys(keys);
    }

    public static byte[] Resource(string name)
    {
        using var s = Assembly.GetExecutingAssembly().GetManifestResourceStream(name)
                      ?? throw new InvalidOperationException($"missing resource {name}");
        using var ms = new MemoryStream();
        s.CopyTo(ms);
        var b = ms.ToArray();
        return b.Length >= 3 && b[0] == 0xEF && b[1] == 0xBB && b[2] == 0xBF ? b[3..] : b;
    }
}

/// <summary>Interface strings from Strings/&lt;lang&gt;.json; business logic never carries text.</summary>
public static class L
{
    static Dictionary<string, string> _s = Load("ru");

    public static string Language { get; private set; } = "ru";

    public static void Use(string? lang)
    {
        lang = lang is "en" ? "en" : "ru";
        _s = Load(lang);
        Language = lang;
    }

    static Dictionary<string, string> Load(string lang) =>
        JsonSerializer.Deserialize(BuiltIn.Resource($"strings.{lang}.json"), LauncherJson.Default.DictionaryStringString) ?? new();

    public static string T(string key) => _s.TryGetValue(key, out var v) ? v : key;
    public static string T(string key, params object[] args) => string.Format(System.Globalization.CultureInfo.CurrentCulture, T(key), args);

    public static string Size(double bytes) =>
        bytes >= 1 << 30 ? T("size.gb", bytes / (1 << 30))
        : bytes >= 1 << 20 ? T("size.mb", bytes / (1 << 20))
        : T("size.kb", bytes / 1024);
}
