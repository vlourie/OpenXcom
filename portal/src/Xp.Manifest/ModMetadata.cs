namespace Xp.Manifest;

/// <summary>
/// The fields of a mod's metadata.yml that decide where the mod belongs, read the way
/// OXCE reads them (src/Engine/ModInfo.cpp): master defaults to "xcom1", a master mod has
/// none unless it names one, "*" means any, requiredExtendedVersion alone means "Extended".
/// Only top-level "key: value" lines are read; metadata.yml has no nesting we need.
/// </summary>
public sealed class ModMetadata
{
    public string Id { get; set; } = "";
    public string Name { get; set; } = "";
    public string Version { get; set; } = "";
    public bool IsMaster { get; set; }
    /// <summary>Master mod id; "" for a master mod or for "*".</summary>
    public string Master { get; set; } = "";
    /// <summary>True when the file said master: "*" (a mod for any master).</summary>
    public bool AnyMaster { get; set; }
    /// <summary>"" any engine, "Extended" OXCE, "OXCE-HD" ours only.</summary>
    public string Engine { get; set; } = "";
    public bool AutoEnable { get; set; }

    public static ModMetadata Parse(string text, string folder)
    {
        var kv = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var raw in text.TrimStart('﻿').Split('\n'))
        {
            var line = raw.TrimEnd('\r');
            if (line.Length == 0 || char.IsWhiteSpace(line[0]) || line[0] is '#' or '-') continue;
            var colon = line.IndexOf(':');
            if (colon <= 0) continue;
            var key = line[..colon].Trim();
            if (!kv.ContainsKey(key)) kv[key] = Unquote(line[(colon + 1)..]);
        }

        var m = new ModMetadata { Id = folder, Name = folder };
        if (kv.TryGetValue("id", out var id) && id.Length > 0) m.Id = id;
        if (kv.TryGetValue("name", out var name) && name.Length > 0) m.Name = name;
        if (kv.TryGetValue("version", out var ver)) m.Version = ver;
        m.IsMaster = kv.TryGetValue("isMaster", out var im) && IsTrue(im);
        m.AutoEnable = kv.TryGetValue("autoEnable", out var ae) && IsTrue(ae);
        if (kv.ContainsKey("requiredExtendedVersion")) m.Engine = "Extended";
        if (kv.TryGetValue("requiredExtendedEngine", out var eng)) m.Engine = eng;
        m.Master = m.IsMaster ? "" : "xcom1";
        if (kv.TryGetValue("master", out var master)) m.Master = master;
        if (m.Master == "*") { m.Master = ""; m.AnyMaster = true; }
        return m;
    }

    static bool IsTrue(string v) => v.Equals("true", StringComparison.OrdinalIgnoreCase) || v == "1";

    static string Unquote(string v)
    {
        v = v.Trim();
        if (v.Length >= 2 && (v[0] == '"' || v[0] == '\''))
        {
            var end = v.IndexOf(v[0], 1);
            if (end > 0) return v[1..end];
        }
        var hash = v.IndexOf(" #", StringComparison.Ordinal);
        return (hash >= 0 ? v[..hash] : v).Trim();
    }
}
