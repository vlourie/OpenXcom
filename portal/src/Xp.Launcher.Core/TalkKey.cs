using System.Globalization;
using System.Text.RegularExpressions;

namespace Xp.Launcher.Core;

/// <summary>
/// The push-to-talk button: a keyboard key by its Windows virtual-key code (Extended tells Enter from the
/// keypad Enter, the way the low-level hook reports it) or a side mouse button, 1 for XButton1, 2 for XButton2.
/// Kept in the launcher settings as "vk:192", "vk:13:ext" or "mouse:1".
/// </summary>
public readonly record struct TalkKey(bool Mouse, int Code, bool Extended = false)
{
    const int VkOem3 = 0xC0;

    /// <summary>The key left of 1 (` on a US layout, Ё on a Russian one): no game key uses it by default.</summary>
    public static readonly TalkKey Default = new(false, VkOem3);

    public override string ToString() =>
        Mouse ? $"mouse:{Code}" : Extended ? $"vk:{Code}:ext" : $"vk:{Code}";

    public static TalkKey? Parse(string? s)
    {
        if (string.IsNullOrWhiteSpace(s)) return null;
        var parts = s.Trim().Split(':');
        if (parts.Length is < 2 or > 3 || !int.TryParse(parts[1], NumberStyles.None, CultureInfo.InvariantCulture, out int code)) return null;
        bool ext = parts.Length == 3 && parts[2] == "ext";
        if (parts.Length == 3 && !ext) return null;
        return parts[0] switch
        {
            "vk" when code is > 0 and < 0xFF && !IsMouseVk(code) => new TalkKey(false, code, ext),
            "mouse" when code is 1 or 2 && !ext => new TalkKey(true, code),
            _ => null,
        };
    }

    /// <summary>VK_LBUTTON, VK_RBUTTON, VK_MBUTTON, VK_XBUTTON1/2: the keyboard hook never sees them.</summary>
    static bool IsMouseVk(int vk) => vk is 1 or 2 or 4 or 5 or 6;

    /// <summary>
    /// The SDL 1.2 code the game gets for this button, as written in options.cfg: SDLKey for a key
    /// (mapping of SDL 1.2 SDL_dibevents.c, DIB_InitOSKeymap), SDL_BUTTON_X1 6 / X2 7 for the mouse.
    /// Null when SDL has no name for the key (the game cannot bind it either).
    /// </summary>
    public int? SdlCode => Mouse ? Code + 5 : GameKeys.SdlKey(Code, Extended);
}

/// <summary>The game's key options (key* in options.cfg) and which of them a push-to-talk button would share.</summary>
public static class GameKeys
{
    /// <summary>
    /// Every key option of the game with its default (src/Engine/Options.cpp). options.cfg keeps only what
    /// the player changed, so a missing option means its default.
    /// </summary>
    public static readonly IReadOnlyDictionary<string, int> Defaults = new Dictionary<string, int>
    {
        ["keyOk"] = 13,
        ["keyCancel"] = 27,
        ["keyScreenshot"] = 293,
        ["keyFps"] = 288,
        ["keyQuickSave"] = 286,
        ["keyQuickLoad"] = 290,
        ["keyGeoLeft"] = 276,
        ["keyGeoRight"] = 275,
        ["keyGeoUp"] = 273,
        ["keyGeoDown"] = 274,
        ["keyGeoZoomIn"] = 43,
        ["keyGeoZoomOut"] = 45,
        ["keyGeoSpeed1"] = 49,
        ["keyGeoSpeed2"] = 50,
        ["keyGeoSpeed3"] = 51,
        ["keyGeoSpeed4"] = 52,
        ["keyGeoSpeed5"] = 53,
        ["keyGeoSpeed6"] = 54,
        ["keyGeoIntercept"] = 105,
        ["keyGeoBases"] = 98,
        ["keyGeoGraphs"] = 103,
        ["keyGeoUfopedia"] = 117,
        ["keyGeoOptions"] = 27,
        ["keyGeoFunding"] = 102,
        ["keyGeoToggleDetail"] = 9,
        ["keyGeoToggleRadar"] = 114,
        ["keyBaseSelect1"] = 49,
        ["keyBaseSelect2"] = 50,
        ["keyBaseSelect3"] = 51,
        ["keyBaseSelect4"] = 52,
        ["keyBaseSelect5"] = 53,
        ["keyBaseSelect6"] = 54,
        ["keyBaseSelect7"] = 55,
        ["keyBaseSelect8"] = 56,
        ["keyBattleLeft"] = 276,
        ["keyBattleRight"] = 275,
        ["keyBattleUp"] = 273,
        ["keyBattleDown"] = 274,
        ["keyBattleLevelUp"] = 280,
        ["keyBattleLevelDown"] = 281,
        ["keyBattleCenterUnit"] = 278,
        ["keyBattlePrevUnit"] = 0,
        ["keyBattleNextUnit"] = 9,
        ["keyBattleDeselectUnit"] = 92,
        ["keyBattleUseLeftHand"] = 113,
        ["keyBattleUseRightHand"] = 101,
        ["keyBattleInventory"] = 105,
        ["keyBattleMap"] = 109,
        ["keyBattleOptions"] = 27,
        ["keyBattleEndTurn"] = 8,
        ["keyBattleAbort"] = 97,
        ["keyBattleStats"] = 115,
        ["keyBattleKneel"] = 107,
        ["keyBattleReload"] = 114,
        ["keyBattlePersonalLighting"] = 108,
        ["keyBattleReserveNone"] = 282,
        ["keyBattleReserveSnap"] = 283,
        ["keyBattleReserveAimed"] = 284,
        ["keyBattleReserveAuto"] = 285,
        ["keyBattleReserveKneel"] = 106,
        ["keyBattleZeroTUs"] = 127,
        ["keyBattleCenterEnemy1"] = 49,
        ["keyBattleCenterEnemy2"] = 50,
        ["keyBattleCenterEnemy3"] = 51,
        ["keyBattleCenterEnemy4"] = 52,
        ["keyBattleCenterEnemy5"] = 53,
        ["keyBattleCenterEnemy6"] = 54,
        ["keyBattleCenterEnemy7"] = 55,
        ["keyBattleCenterEnemy8"] = 56,
        ["keyBattleCenterEnemy9"] = 57,
        ["keyBattleCenterEnemy10"] = 48,
        ["keyBattleVoxelView"] = 291,
        ["keyInvCreateTemplate"] = 99,
        ["keyInvApplyTemplate"] = 118,
        ["keyInvClear"] = 120,
        ["keyInvAutoEquip"] = 122,
        ["keyBattleHdTestDump"] = 289,
        ["keyFeedback"] = 289,
        ["keyBattleHdModeToggle"] = 292,
        ["keyToggleQuickSearch"] = 113,
        ["keyInstaSave"] = 287,
        ["keyGeoUfoTracker"] = 116,
        ["keyGeoTechTreeViewer"] = 113,
        ["keyGeoGlobalProduction"] = 112,
        ["keyGeoGlobalResearch"] = 99,
        ["keyGeoGlobalAlienContainment"] = 106,
        ["keyGeoGlobalTransfers"] = 0,
        ["keyGeoDailyPilotExperience"] = 101,
        ["keyGraphsZoomIn"] = 270,
        ["keyGraphsZoomOut"] = 269,
        ["keyBasescapeBuildNewBase"] = 110,
        ["keyBasescapeBaseInformation"] = 105,
        ["keyBasescapeSoldiers"] = 115,
        ["keyBasescapeEquipCraft"] = 101,
        ["keyBasescapeBuildFacilities"] = 102,
        ["keyBasescapeResearch"] = 114,
        ["keyBasescapeManufacture"] = 109,
        ["keyBasescapeTransfer"] = 116,
        ["keyBasescapePurchase"] = 112,
        ["keyBasescapeSell"] = 108,
        ["keyRemoveSoldiersFromTraining"] = 120,
        ["keyAddSoldiersToTraining"] = 122,
        ["keyCraftLoadoutSave"] = 286,
        ["keyCraftLoadoutLoad"] = 290,
        ["keyRemoveSoldiersFromAllCrafts"] = 120,
        ["keyRemoveSoldiersFromCraft"] = 122,
        ["keyRemoveEquipmentFromCraft"] = 120,
        ["keyRemoveArmorFromAllCrafts"] = 120,
        ["keyRemoveArmorFromCraft"] = 122,
        ["keyInventorySave"] = 286,
        ["keyInventoryLoad"] = 290,
        ["keyInvSavePersonalEquipment"] = 115,
        ["keyInvLoadPersonalEquipment"] = 108,
        ["keyInvShowPersonalEquipment"] = 112,
        ["keyInventoryArmor"] = 97,
        ["keyInventoryAvatar"] = 109,
        ["keyInventoryDiaryLight"] = 100,
        ["keySellAll"] = 120,
        ["keySellAllButOne"] = 122,
        ["keyTransferAll"] = 120,
        ["keyMarkAllAsSeen"] = 120,
        ["keyBattleUnitUp"] = 0,
        ["keyBattleUnitDown"] = 0,
        ["keyBattleShowLayers"] = 0,
        ["keyBattleUseSpecial"] = 119,
        ["keyBattleActionItem1"] = 49,
        ["keyBattleActionItem2"] = 50,
        ["keyBattleActionItem3"] = 51,
        ["keyBattleActionItem4"] = 52,
        ["keyBattleActionItem5"] = 53,
        ["keyNightVisionToggle"] = 302,
        ["keyNightVisionHold"] = 32,
        ["keySelectMusicTrack"] = 279,
    };

    // Mouse options whose value is an SDL button number; the side buttons are 6 and 7 there as well.
    static readonly string[] MouseOptions = ["battleDragScrollButton", "geoDragScrollButton"];
    const string ThumbButtons = "oxceThumbButtons";

    static readonly Regex Line = new(@"^\s+([A-Za-z]\w*):\s*(\S+)\s*$", RegexOptions.CultureInvariant);

    /// <summary>The flat name: value lines of options.cfg (the mods list and anything nested is skipped).</summary>
    public static Dictionary<string, string> ReadOptions(string text)
    {
        var d = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var raw in text.Split('\n'))
            if (Line.Match(raw.TrimEnd('\r')) is { Success: true } m) d[m.Groups[1].Value] = m.Groups[2].Value;
        return d;
    }

    /// <summary>
    /// The game options that the button already does something in: key options bound to the same SDL key,
    /// for a side mouse button the drag-scroll options set to it and the next/previous soldier of
    /// oxceThumbButtons (on by default). Sorted by name; empty when nothing collides or options.cfg is missing.
    /// </summary>
    public static List<string> Conflicts(TalkKey key, string? optionsText)
    {
        var cfg = optionsText is null ? new Dictionary<string, string>() : ReadOptions(optionsText);
        var hits = new List<string>();
        if (key.SdlCode is not int sdl) return hits;
        if (key.Mouse)
        {
            foreach (var name in MouseOptions)
                if (cfg.TryGetValue(name, out var v) && int.TryParse(v, NumberStyles.Integer, CultureInfo.InvariantCulture, out int b) && b == sdl)
                    hits.Add(name);
            if (!cfg.TryGetValue(ThumbButtons, out var thumb) || thumb != "false") hits.Add(ThumbButtons);
        }
        else
        {
            foreach (var (name, def) in Defaults)
            {
                int bound = cfg.TryGetValue(name, out var v) && int.TryParse(v, NumberStyles.Integer, CultureInfo.InvariantCulture, out int n) ? n : def;
                if (bound != 0 && bound == sdl) hits.Add(name);
            }
        }
        hits.Sort(StringComparer.Ordinal);
        return hits;
    }

    /// <summary>The conflicts in the options.cfg the game reads now; a file that cannot be read counts as defaults.</summary>
    public static List<string> Conflicts(TalkKey key, BuildStore builds)
    {
        string? text = null;
        try
        {
            var file = builds.CurrentOptionsFile();
            if (File.Exists(file)) text = File.ReadAllText(file);
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { }
        return Conflicts(key, text ?? "");
    }

    /// <summary>SDL 1.2's SDLKey for a Windows virtual key, null where SDL 1.2 has none.</summary>
    public static int? SdlKey(int vk, bool extended)
    {
        switch (vk)
        {
            case >= 'A' and <= 'Z': return vk + 32;           // SDLK_a..z
            case >= '0' and <= '9': return vk;                // SDLK_0..9
            case >= 0x60 and <= 0x69: return 256 + vk - 0x60; // VK_NUMPAD0..9 -> SDLK_KP0..9
            case >= 0x70 and <= 0x7E: return 282 + vk - 0x70; // VK_F1..F15 -> SDLK_F1..F15
            // SDL_dibevents.c: an Enter with the extended bit is the keypad one
            case 0x0D: return extended ? 271 : 13;
        }
        return vk switch
        {
            0x08 => 8, 0x09 => 9, 0x0C => 12, 0x13 => 19, 0x1B => 27, 0x20 => 32, // BACKSPACE TAB CLEAR PAUSE ESCAPE SPACE
            0x2E => 127,                                                          // DELETE
            0x6A => 268, 0x6B => 270, 0x6D => 269, 0x6E => 266, 0x6F => 267,      // KP_MULTIPLY PLUS MINUS PERIOD DIVIDE
            0x26 => 273, 0x28 => 274, 0x27 => 275, 0x25 => 276,                   // UP DOWN RIGHT LEFT
            0x2D => 277, 0x24 => 278, 0x23 => 279, 0x21 => 280, 0x22 => 281,      // INSERT HOME END PAGEUP PAGEDOWN
            0x90 => 300, 0x14 => 301, 0x91 => 302,                                // NUMLOCK CAPSLOCK SCROLLOCK
            0xA1 => 303, 0xA0 => 304, 0xA3 => 305, 0xA2 => 306, 0xA5 => 307, 0xA4 => 308, // RSHIFT LSHIFT RCTRL LCTRL RALT LALT
            0x10 => 304, 0x11 => 306, 0x12 => 308,                                // a bare SHIFT/CONTROL/MENU: the left one
            0x5B => 311, 0x5C => 312,                                             // LSUPER RSUPER
            0x2F => 315, 0x2C => 316, 0x03 => 318, 0x5D => 319,                   // HELP PRINT BREAK MENU
            0xBA => 59, 0xBB => 61, 0xBC => 44, 0xBD => 45, 0xBE => 46, 0xBF => 47, // ; = , - . /
            0xC0 => 96, 0xDB => 91, 0xDC => 92, 0xDD => 93, 0xDE => 39, 0xE2 => 60, // ` [ \ ] ' <
            _ => null,
        };
    }
}
