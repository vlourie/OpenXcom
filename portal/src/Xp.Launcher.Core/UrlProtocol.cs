using System.Runtime.Versioning;
using Microsoft.Win32;

namespace Xp.Launcher.Core;

/// <summary>The few registry operations the link registration needs, so tests run on a dictionary.</summary>
public interface IRegistryValues
{
    /// <summary>A string value; name null is the key's default value. Null when the key or value is missing.</summary>
    string? Get(string subKey, string? name);
    void Set(string subKey, string? name, string value);
}

/// <summary>HKEY_CURRENT_USER\Software\Classes: per-user, no administrator rights needed.</summary>
[SupportedOSPlatform("windows")]
public sealed class CurrentUserClasses : IRegistryValues
{
    const string Root = @"Software\Classes\";

    public string? Get(string subKey, string? name)
    {
        using var k = Registry.CurrentUser.OpenSubKey(Root + subKey);
        return k?.GetValue(name) as string;
    }

    public void Set(string subKey, string? name, string value)
    {
        using var k = Registry.CurrentUser.CreateSubKey(Root + subKey, writable: true);
        k.SetValue(name, value, RegistryValueKind.String);
    }
}

/// <summary>
/// Makes xpiratez:// links of the site open this launcher. Done at every start: the launcher may have moved,
/// and the key then points at the place it is in now. Values already right are not written again.
/// </summary>
public static class UrlProtocol
{
    /// <summary>The values this exe needs, key -> (value name, data).</summary>
    public static IReadOnlyList<(string Key, string? Name, string Value)> Wanted(string exePath)
    {
        string scheme = VoiceLink.Scheme;
        return
        [
            (scheme, null, "URL:X-Piratez"),
            (scheme, "URL Protocol", ""),
            (scheme + @"\DefaultIcon", null, $"\"{exePath}\",0"),
            (scheme + @"\shell\open\command", null, $"\"{exePath}\" \"%1\""),
        ];
    }

    /// <summary>Writes what differs; returns how many values were written (0 when everything was in place).</summary>
    public static int Register(IRegistryValues reg, string exePath)
    {
        int written = 0;
        foreach (var (key, name, value) in Wanted(exePath))
        {
            if (reg.Get(key, name) == value) continue;
            reg.Set(key, name, value);
            written++;
        }
        return written;
    }
}

/// <summary>
/// What a second start of the launcher tells the one already running, over a named pipe: just come to the
/// front ("show"), or open a room ("voice &lt;publicId&gt;"). One line; anything else is ignored.
/// </summary>
public static class LauncherSignal
{
    public const string Show = "show";
    const string VoicePrefix = "voice ";

    /// <summary>The pipe of this user in this Windows session: two people on one machine do not reach each other.</summary>
    public static string PipeName(string userName, int sessionId) =>
        $"XPiratezLauncher-{sessionId}-{Sanitize(userName)}";

    public static string For(string? voiceRoom) => voiceRoom is null ? Show : VoicePrefix + voiceRoom;

    /// <summary>(true, room) for a valid message, room null for "show"; (false, null) for anything else.</summary>
    public static (bool Ok, string? Room) Parse(string? line)
    {
        line = line?.Trim();
        if (line == Show) return (true, null);
        if (line is not null && line.StartsWith(VoicePrefix, StringComparison.Ordinal) &&
            line[VoicePrefix.Length..].Trim() is var room && VoiceLink.IsRoomId(room))
            return (true, room.ToLowerInvariant());
        return (false, null);
    }

    static string Sanitize(string s)
    {
        var chars = s.Select(c => char.IsLetterOrDigit(c) ? c : '_').Take(64).ToArray();
        return chars.Length == 0 ? "user" : new string(chars);
    }
}
