using Xp.Bootstrapper;

namespace Xp.Launcher.Core.Tests;

/// <summary>
/// Shortcuts after a self-update (kondrak001, 02.10): a launcher that never ran the setup gets them once,
/// a shortcut the player deleted after that is not brought back, one of the same name is not replaced.
/// Real .lnk files, in temp folders standing for the desktop and the Start menu.
/// </summary>
public sealed class ShortcutTests : IDisposable
{
    readonly string _root = Path.Combine(Path.GetTempPath(), "xp-lnk-" + Guid.NewGuid().ToString("N")[..8]);
    string Desktop => Path.Combine(_root, "Desktop");
    string Programs => Path.Combine(_root, "Programs");
    string Marker => Path.Combine(_root, "state", "shortcuts.made");
    string Exe => Path.Combine(_root, "launcher", "XPiratezLauncher.exe");
    string Lnk(string dir) => Path.Combine(dir, "X-Piratez HD.lnk");
    readonly List<string> _log = [];

    public ShortcutTests()
    {
        Directory.CreateDirectory(Desktop);
        Directory.CreateDirectory(Programs);
        Directory.CreateDirectory(Path.GetDirectoryName(Exe)!);
        File.WriteAllText(Exe, "exe");
    }

    public void Dispose()
    {
        try { Directory.Delete(_root, true); } catch (IOException) { }
    }

    void Update() => Installer.AfterUpdate(Exe, [Desktop, Programs], Marker, _log.Add);

    [Fact]
    public void The_first_update_makes_the_missing_shortcuts_once()
    {
        Update();
        Assert.True(File.Exists(Lnk(Desktop)), string.Join("\n", _log));
        Assert.True(File.Exists(Lnk(Programs)));
        Assert.True(File.Exists(Marker));
        // a real shell link (starts with its header size 0x4C), not an empty file
        Assert.Equal(0x4C, File.ReadAllBytes(Lnk(Desktop))[0]);

        File.Delete(Lnk(Desktop));   // the player does not want it
        Update();
        Assert.False(File.Exists(Lnk(Desktop)));
        Assert.True(File.Exists(Lnk(Programs)));
    }

    [Fact]
    public void A_shortcut_of_the_same_name_is_kept_as_it_is()
    {
        File.WriteAllText(Lnk(Desktop), "the player's own");
        Update();
        Assert.Equal("the player's own", File.ReadAllText(Lnk(Desktop)));
        Assert.True(File.Exists(Lnk(Programs)));
    }

    [Fact]
    public void After_the_setup_made_them_an_update_adds_nothing()
    {
        Directory.CreateDirectory(Path.GetDirectoryName(Marker)!);
        File.WriteAllText(Marker, "setup");
        Update();
        Assert.False(File.Exists(Lnk(Desktop)));
        Assert.False(File.Exists(Lnk(Programs)));
    }
}
