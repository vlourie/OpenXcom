using System.Reflection;
using System.Text;
using Xp.Manifest;

namespace Xp.Launcher.Core;

/// <summary>A mod with Lua that the author keeps in user/mods: not from a release, not checked by us.</summary>
/// <param name="OtherMaster">the master it is made for, when that is not the build's; the engine will not switch it on</param>
public sealed record LocalLuaMod(string Id, string Name, string Version, string Folder, bool Active, string? OtherMaster);

/// <summary>The folder or the id a new mod would take is someone else's: nothing was created.</summary>
public sealed class LuaModNameTakenException(string folder) : Exception($"the name is taken: {folder}")
{
    public string Folder { get; } = folder;
}

/// <summary>
/// The modding mode of one installation and the author's Lua mods (docs/portal/LUA_MODS.md §4, §6). The launcher only
/// writes the template and flips switches: Lua runs in the game and nowhere else, this class never executes a mod's code.
/// </summary>
public static class LuaMods
{
    public const string Option = "oxceLuaMods";

    static string ModeFile(GamePaths paths) => Path.Combine(paths.StateDir, "modding.txt");

    public static string ErrorLog(GamePaths paths) => Path.Combine(paths.GameDir, "user", "lua_errors.log");

    public static bool ModeOn(GamePaths paths) => File.Exists(ModeFile(paths));

    public static void SetMode(GamePaths paths, bool on)
    {
        if (on) FileUtil.WriteAtomic(ModeFile(paths), Encoding.UTF8.GetBytes("on\n"));
        else File.Delete(ModeFile(paths));
    }

    /// <summary>The label of §6: a lua folder, or luaApi in metadata.yml. The engine runs it only with both, and the option.</summary>
    public static bool IsLua(string modDir, ModMetadata md) => md.LuaApi > 0 || Directory.Exists(Path.Combine(modDir, "lua"));

    /// <summary>
    /// The option as the mode says, before every start. A player who never turned the mode on keeps options.cfg as it
    /// is, without the line: the engine's default is off. True when the file changed.
    /// </summary>
    public static bool ApplyOption(GamePaths paths, string cfgPath)
    {
        var before = File.Exists(cfgPath) ? File.ReadAllText(cfgPath) : "";
        var cfg = OptionsCfg.Parse(before);
        var have = cfg.Get(Option);
        bool on = ModeOn(paths);
        if (on ? have == "true" : have is null or "false") return false;
        cfg.Set(Option, on ? "true" : "false");
        WriteCfg(cfgPath, before, cfg.Render());
        return true;
    }

    /// <summary>The mods of §4 in the build's options.cfg. What a release installed is not listed, whatever it carries.</summary>
    /// <param name="installedFiles">the keys of the state's Installed: the files of the release, with '/'</param>
    public static List<LocalLuaMod> List(GamePaths paths, string cfgPath, string? master, IEnumerable<string> installedFiles)
    {
        var shipped = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var f in installedFiles)
        {
            var seg = f.Split('/');
            if (seg.Length > 3 && seg[0].Equals("user", StringComparison.OrdinalIgnoreCase) && seg[1].Equals("mods", StringComparison.OrdinalIgnoreCase))
                shipped.Add(seg[2]);
        }
        var result = new List<LocalLuaMod>();
        var root = Path.Combine(paths.GameDir, "user", "mods");
        if (!Directory.Exists(root)) return result;
        var cfg = OptionsCfg.Parse(File.Exists(cfgPath) ? File.ReadAllText(cfgPath) : "");
        foreach (var dir in Directory.EnumerateDirectories(root).Order(StringComparer.OrdinalIgnoreCase))
        {
            var folder = Path.GetFileName(dir);
            if (shipped.Contains(folder)) continue;
            var meta = Path.Combine(dir, "metadata.yml");
            ModMetadata md;
            try { md = ModMetadata.Parse(File.Exists(meta) ? File.ReadAllText(meta) : "", folder); }
            catch (Exception e) when (e is IOException or UnauthorizedAccessException) { continue; }
            if (!IsLua(dir, md)) continue;
            var otherMaster = !md.IsMaster && !md.AnyMaster && master is not null && md.Master != master ? md.Master : null;
            result.Add(new LocalLuaMod(md.Id, md.Name, md.Version, folder, cfg.Mods.Any(x => x.Id == md.Id && x.Active), otherMaster));
        }
        return result;
    }

    /// <summary>On or off in the build's options.cfg, as the game's own menu would. A list the launcher kept stays the launcher's.</summary>
    public static void SetActive(BuildStore builds, Build build, string id, bool on, Func<string, bool>? isGameRunning = null)
    {
        if ((isGameRunning ?? GameProcess.IsRunningIn)(builds.Paths.GameDir))
            throw new UpdateBlockedException("the game is running: its options are not changed under it");
        var path = builds.OptionsFile(build);
        var before = File.Exists(path) ? File.ReadAllText(path) : "";
        var cfg = OptionsCfg.Parse(before);
        int at = cfg.Mods.FindIndex(m => m.Id == id);
        if (at >= 0) cfg.Mods[at] = (id, on);
        else if (on) cfg.Mods.Add((id, true));
        var after = cfg.Render();
        if (after == before) return;
        WriteCfg(path, before, after);
        HdCoreMigration.FollowProfile(builds.Paths, build.Id.ToLowerInvariant(), before, after);
    }

    static void WriteCfg(string path, string before, string after)
    {
        if (before.Length > 0) File.Copy(path, path + ".bak", overwrite: true);
        // the engine reads it with yaml-cpp: plain UTF-8, no BOM (R-001, the exception for game files)
        FileUtil.WriteAtomic(path, new UTF8Encoding(false).GetBytes(after));
    }

    /// <summary>The master a new mod is made for: the build's, then the one on in its options.cfg, then the engine's default.</summary>
    public static string MasterOf(GamePaths paths, Build? build, string cfgPath)
    {
        if (build?.EngineMaster is { Length: > 0 } m) return m;
        var installed = ProfileWriter.ScanMods(paths.GameDir);
        return OptionsCfg.Parse(File.Exists(cfgPath) ? File.ReadAllText(cfgPath) : "").Mods
            .Where(x => x.Active && installed.Any(i => i.IsMaster && i.Id == x.Id)).Select(x => x.Id).FirstOrDefault() ?? "xcom1";
    }

    /// <summary>The folder and the id of a mod called so: ASCII, so that a report and a log can name it on any machine.</summary>
    public static string FolderFor(string name)
    {
        var sb = new StringBuilder();
        foreach (var c in name.Trim().ToLowerInvariant())
        {
            if (c is >= 'a' and <= 'z' or >= '0' and <= '9' or '_' or '-') sb.Append(c);
            else if (Translit.TryGetValue(c, out var t)) sb.Append(t);
            else if (sb.Length > 0 && sb[^1] != '_') sb.Append('_');
        }
        var folder = sb.ToString().Trim('_', '-');
        if (folder.Length > 40) folder = folder[..40].TrimEnd('_', '-');
        return folder.Length > 0 ? folder : "lua_mod";
    }

    static readonly Dictionary<char, string> Translit = new()
    {
        ['а'] = "a", ['б'] = "b", ['в'] = "v", ['г'] = "g", ['д'] = "d", ['е'] = "e", ['ё'] = "e", ['ж'] = "zh", ['з'] = "z", ['и'] = "i", ['й'] = "y",
        ['к'] = "k", ['л'] = "l", ['м'] = "m", ['н'] = "n", ['о'] = "o", ['п'] = "p", ['р'] = "r", ['с'] = "s", ['т'] = "t", ['у'] = "u", ['ф'] = "f",
        ['х'] = "h", ['ц'] = "ts", ['ч'] = "ch", ['ш'] = "sh", ['щ'] = "sch", ['ъ'] = "", ['ы'] = "y", ['ь'] = "", ['э'] = "e", ['ю'] = "yu", ['я'] = "ya",
    };

    /// <summary>
    /// The new mod from the template: metadata.yml, lua/main.lua, README.txt. Never over a folder that exists, never
    /// under an id or a folder that is taken: what a release would bring there would overwrite the author's work.
    /// </summary>
    /// <param name="reserved">folders and ids of the release, when it is known</param>
    /// <returns>the folder's name under user/mods</returns>
    public static string Create(GamePaths paths, string name, string master, string language, IEnumerable<string>? reserved = null,
        Func<string, bool>? isGameRunning = null)
    {
        if ((isGameRunning ?? GameProcess.IsRunningIn)(paths.GameDir))
            throw new UpdateBlockedException("the game is running: its mods are not changed under it");
        name = string.Join(' ', name.Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries));
        var folder = FolderFor(name);
        var rel = "user/mods/" + folder;
        if (!SafePath.IsValid(rel)
            || (reserved ?? []).Contains(folder, StringComparer.OrdinalIgnoreCase)
            || ProfileWriter.ScanMods(paths.GameDir).Any(m => m.Id.Equals(folder, StringComparison.OrdinalIgnoreCase)))
            throw new LuaModNameTakenException(folder);
        var dir = paths.Full(rel);
        if (Directory.Exists(dir) || File.Exists(dir)) throw new LuaModNameTakenException(folder);
        bool ru = language.StartsWith("ru", StringComparison.OrdinalIgnoreCase);
        var plain = new UTF8Encoding(false);
        Directory.CreateDirectory(Path.Combine(dir, "lua"));
        try
        {
            var quoted = name.Replace("\\", "\\\\").Replace("\"", "\\\"");
            File.WriteAllBytes(Path.Combine(dir, "metadata.yml"), plain.GetBytes(
                $"id: {folder}\nname: \"{quoted}\"\nversion: 0.1\nmaster: \"{master}\"\nluaApi: 1\n"));
            File.WriteAllBytes(Path.Combine(dir, "lua", "main.lua"), plain.GetBytes(MainLua(name, ru)));
            // R-001: Notepad and the player read Russian in it, the game does not read it at all
            File.WriteAllBytes(Path.Combine(dir, "README.txt"), new UTF8Encoding(true).GetPreamble().Concat(plain.GetBytes(Readme(name, folder, ru))).ToArray());
        }
        catch
        {
            Directory.Delete(dir, recursive: true);
            throw;
        }
        return folder;
    }

    /// <summary>The API documentation in the game folder, both languages; the page in this language.</summary>
    public static string WriteDocs(GamePaths paths, string language)
    {
        var dir = Path.Combine(paths.StateDir, "docs");
        Directory.CreateDirectory(dir);
        foreach (var lang in new[] { "ru", "en" })
        {
            var file = $"lua_api.{lang}.html";
            using var s = typeof(LuaMods).Assembly.GetManifestResourceStream(file) ?? throw new InvalidOperationException("no resource " + file);
            using var ms = new MemoryStream();
            s.CopyTo(ms);
            var target = Path.Combine(dir, file);
            if (!File.Exists(target) || !File.ReadAllBytes(target).AsSpan().SequenceEqual(ms.ToArray())) FileUtil.WriteAtomic(target, ms.ToArray());
        }
        return Path.Combine(dir, language.StartsWith("ru", StringComparison.OrdinalIgnoreCase) ? "lua_api.ru.html" : "lua_api.en.html");
    }

    static string MainLua(string name, bool ru) => ru
        ? $$"""
            -- {{name}}
            -- Пример: в начале хода каждой стороны пишет строку в журнал игры (user/openxcom.log).
            -- Документация: launcher/docs/lua_api.ru.html в папке игры.
            -- Переменные Lua обнуляются при загрузке сейва, в новом бою и по Ctrl+F5.

            local last = nil

            game.on("newTurnUnit", function(unit, battle, turn, side)
              local now = turn .. "/" .. side
              if now ~= last then
                last = now
                game.log("new turn", turn, "side", side)
                -- battle:flashMessage("Ход {0}", turn)   -- то же на экране
              end
            end)

            """.ReplaceLineEndings("\n")
        : $$"""
            -- {{name}}
            -- An example: at the start of each side's turn it writes a line to the game's log (user/openxcom.log).
            -- Documentation: launcher/docs/lua_api.en.html in the game folder.
            -- Lua variables are reset when a save is loaded, in a new battle and by Ctrl+F5.

            local last = nil

            game.on("newTurnUnit", function(unit, battle, turn, side)
              local now = turn .. "/" .. side
              if now ~= last then
                last = now
                game.log("new turn", turn, "side", side)
                -- battle:flashMessage("Turn {0}", turn)   -- the same on the screen
              end
            end)

            """.ReplaceLineEndings("\n");

    static string Readme(string name, string folder, bool ru) => ru
        ? $$"""
            {{name}}

            Это ваш локальный Lua-мод. Он работает только в вашей игре. Лаунчер отправит его, только если нажать «Предложить».

            Что здесь лежит
              metadata.yml   имя, версия, для какой игры мод; luaApi - версия API
              lua/main.lua   код мода, игра запускает этот файл

            Как проверить
              1. В лаунчере: Настройки, «Режим мододела» включён, мод в списке «Мои моды» включён.
              2. Запустите игру и начните бой. В файле user/openxcom.log появятся строки «[lua] {{folder}}: new turn ...».
              3. Поправьте main.lua и нажмите Ctrl+F5 в бою: код перечитается без перезапуска.

            Где ошибки
              Файл user/lua_errors.log (кнопка «Журнал ошибок» в лаунчере), на экране короткое сообщение.
              После 5 ошибок подряд мод выключается до Ctrl+F5 или новой загрузки. Игра при этом не падает.

            Документация
              launcher/docs/lua_api.ru.html в папке игры, кнопка «Документация» в лаунчере.

            Важно
              Локальный мод может менять механику и сломать сейв. Для опытов лучше отдельная сборка.
              Если заводите тикет об игре, сначала проверьте, повторяется ли ошибка без этого мода.

            """.ReplaceLineEndings("\r\n")
        : $$"""
            {{name}}

            This is your local Lua mod. It works in your game only. The launcher sends it only if you press "Submit".

            What is here
              metadata.yml   name, version, the game the mod is for; luaApi is the API version
              lua/main.lua   the mod's code, the game runs this file

            How to try it
              1. In the launcher: Settings, "Modding mode" is on, the mod is on in the "My mods" list.
              2. Start the game and begin a battle. Lines "[lua] {{folder}}: new turn ..." appear in user/openxcom.log.
              3. Change main.lua and press Ctrl+F5 in battle: the code is read again without a restart.

            Where the errors are
              The file user/lua_errors.log (the "Error log" button in the launcher), a short message on the screen.
              After 5 errors in a row the mod is off until Ctrl+F5 or a new load. The game does not crash.

            Documentation
              launcher/docs/lua_api.en.html in the game folder, the "Documentation" button in the launcher.

            Important
              A local mod can change game mechanics and break a save. A separate build is better for experiments.
              Before you file a ticket about the game, check whether the error repeats without this mod.

            """.ReplaceLineEndings("\r\n");
}
