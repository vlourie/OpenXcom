namespace Xp.Launcher.Core.Tests;

public sealed class TalkKeyTests
{
    [Theory]
    [InlineData("vk:192", false, 192, false)]
    [InlineData("vk:13:ext", false, 13, true)]
    [InlineData("mouse:1", true, 1, false)]
    [InlineData("mouse:2", true, 2, false)]
    public void A_saved_key_reads_back(string saved, bool mouse, int code, bool ext)
    {
        var k = TalkKey.Parse(saved);

        Assert.Equal(new TalkKey(mouse, code, ext), k);
        Assert.Equal(saved, k!.Value.ToString());
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("vk:")]
    [InlineData("vk:-5")]
    [InlineData("vk:0")]
    [InlineData("vk:300")]
    [InlineData("vk:1")]        // VK_LBUTTON: the keyboard hook never sees it
    [InlineData("vk:5")]        // VK_XBUTTON1 as a key
    [InlineData("vk:13:x")]
    [InlineData("mouse:0")]
    [InlineData("mouse:3")]
    [InlineData("mouse:1:ext")]
    [InlineData("joy:1")]
    public void A_damaged_key_is_none(string? saved) => Assert.Null(TalkKey.Parse(saved));

    [Fact]
    public void The_default_is_free_in_a_fresh_game()
    {
        Assert.Equal(96, TalkKey.Default.SdlCode);      // SDLK_BACKQUOTE
        Assert.Empty(GameKeys.Conflicts(TalkKey.Default, ""));
        Assert.Empty(GameKeys.Conflicts(TalkKey.Default, (string?)null));
    }

    [Theory]
    [InlineData('A', false, 97)]
    [InlineData('Z', false, 122)]
    [InlineData('7', false, 55)]
    [InlineData(0x60, false, 256)]   // NUMPAD0 -> KP0
    [InlineData(0x70, false, 282)]   // F1
    [InlineData(0x7E, false, 296)]   // F15
    [InlineData(0x0D, false, 13)]    // Enter
    [InlineData(0x0D, true, 271)]    // keypad Enter
    [InlineData(0x20, false, 32)]
    [InlineData(0xA0, false, 304)]   // LSHIFT
    [InlineData(0xA5, true, 307)]    // RALT
    [InlineData(0x91, false, 302)]   // SCROLLOCK
    [InlineData(0xC0, false, 96)]
    [InlineData(0xE2, false, 60)]    // the extra key of European keyboards -> SDLK_LESS
    public void Windows_keys_map_to_sdl(int vk, bool ext, int sdl) => Assert.Equal(sdl, GameKeys.SdlKey(vk, ext));

    [Fact]
    public void A_key_without_an_sdl_name_has_no_conflicts()
    {
        var k = new TalkKey(false, 0xAD);   // VK_VOLUME_MUTE
        Assert.Null(k.SdlCode);
        Assert.Empty(GameKeys.Conflicts(k, "options:\n  keyOk: 0\n"));
    }

    [Fact]
    public void A_default_binding_collides()
    {
        // Space is the night vision hold by default; F1 reserves no TU in battle
        Assert.Equal(["keyNightVisionHold"], GameKeys.Conflicts(new TalkKey(false, 0x20), ""));
        Assert.Equal(["keyBattleReserveNone"], GameKeys.Conflicts(new TalkKey(false, 0x70), ""));
        Assert.Contains("keyGeoSpeed1", GameKeys.Conflicts(new TalkKey(false, '1'), ""));
    }

    [Fact]
    public void The_players_bindings_win_over_defaults()
    {
        const string cfg = """
            mods:
              - active: true
                id: piratez
            options:
              keyNightVisionHold: 0
              keyBattleKneel: 96
              keyboardMode: 1
              battleDragScrollButton: 6
            """;

        Assert.Empty(GameKeys.Conflicts(new TalkKey(false, 0x20), cfg));          // unbound by the player
        Assert.Equal(["keyBattleKneel"], GameKeys.Conflicts(TalkKey.Default, cfg));
    }

    [Fact]
    public void A_side_button_collides_with_thumb_buttons_and_drag_scroll()
    {
        const string cfg = "options:\n  battleDragScrollButton: 6\n  geoDragScrollButton: 2\n";

        Assert.Equal(["battleDragScrollButton", "oxceThumbButtons"], GameKeys.Conflicts(new TalkKey(true, 1), cfg));
        Assert.Equal(["oxceThumbButtons"], GameKeys.Conflicts(new TalkKey(true, 2), cfg));
        Assert.Empty(GameKeys.Conflicts(new TalkKey(true, 2), "options:\r\n  oxceThumbButtons: false\r\n"));
    }

    [Fact]
    public void The_defaults_table_is_whole()
    {
        Assert.Equal(133, GameKeys.Defaults.Count);
        Assert.Equal(13, GameKeys.Defaults["keyOk"]);
        Assert.Equal(279, GameKeys.Defaults["keySelectMusicTrack"]);
        Assert.DoesNotContain("keyboardMode", GameKeys.Defaults.Keys);
    }
}
