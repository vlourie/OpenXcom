namespace Xp.Launcher.Core.Tests;

public sealed class UfoDataTests : IDisposable
{
    readonly Fixture f = new();
    public void Dispose() => f.Dispose();

    /// <summary>A store install: the data one level down, next to DOS executables that are not data.</summary>
    string SteamLike(string root, bool lowerCase = false)
    {
        var xcom = Path.Combine(root, "XCOM");
        foreach (var d in UfoData.DataDirs)
            Fixture.Write(xcom, (lowerCase ? d.ToLowerInvariant() : d) + "/filler.dat", d);
        foreach (var k in UfoData.KeyFiles)
            Fixture.Write(xcom, lowerCase ? k.ToLowerInvariant() : k, k);
        Fixture.Write(xcom, "UFO Defense.exe", "dos");
        Fixture.Write(root, "dosbox/dosbox.exe", "emulator");
        return xcom;
    }

    [Fact]
    public void A_copy_is_judged_by_the_files_the_engine_loads_not_by_counting_folders()
    {
        var xcom = SteamLike(Path.Combine(f.Root, "steam"));
        Assert.True(UfoData.Check(xcom).Ok);

        // nine folders of anything would pass the engine's own count; here a missing palette is named
        File.Delete(Path.Combine(xcom, "GEODATA", "PALETTES.DAT"));
        Assert.Equal(["GEODATA/PALETTES.DAT"], UfoData.Check(xcom).Missing);

        // the intro is optional: without it the game still starts
        var lower = SteamLike(Path.Combine(f.Root, "repack"), lowerCase: true);
        Directory.Delete(Path.Combine(lower, "ufointro"), recursive: true);
        Assert.True(UfoData.Check(lower).Ok, "lower-case names and no intro must still count as a copy");

        Assert.False(UfoData.Check(Path.Combine(f.Root, "nowhere")).Ok);
    }

    [Fact]
    public void Steam_libraries_are_read_with_their_escaped_backslashes()
    {
        var vdf = "\"libraryfolders\"\n{\n\t\"0\"\n\t{\n\t\t\"path\"\t\t\"C:\\\\Program Files (x86)\\\\Steam\"\n\t\t\"label\"\t\t\"\"\n\t}\n"
                + "\t\"1\"\n\t{\n\t\t\"path\"\t\t\"D:\\\\SteamLibrary\"\n\t}\n}\n";
        Assert.Equal([@"C:\Program Files (x86)\Steam", @"D:\SteamLibrary"], UfoData.ParseLibraryFolders(vdf));
    }

    [Fact]
    public void A_store_folder_is_found_one_level_down_and_only_once()
    {
        var root = Path.Combine(f.Root, "XCom UFO Defense");
        var xcom = SteamLike(root);
        var empty = Path.Combine(f.Root, "empty");
        Directory.CreateDirectory(empty);

        var found = UfoData.Probe([(empty, "GOG"), (root, "Steam"), (root, "Steam again")]);
        Assert.Equal([new UfoFound(Path.GetFullPath(xcom), "Steam")], found);
    }

    [Fact]
    public void Only_the_data_is_copied_and_the_result_is_checked()
    {
        var root = Path.Combine(f.Root, "steam");
        var xcom = SteamLike(root, lowerCase: true);
        var dest = Path.Combine(f.Game, "UFO");

        var result = UfoData.Copy(xcom, dest);
        Assert.True(result.Ok);
        Assert.True(File.Exists(Path.Combine(dest, "GEODATA", "palettes.dat")), "the data folders arrive under the names the engine asks for");
        Assert.False(File.Exists(Path.Combine(dest, "UFO Defense.exe")), "a DOS executable is not data");
        Assert.Empty(Directory.GetDirectories(dest).Select(Path.GetFileName).Except(UfoData.DataDirs));

        // a folder that is not a copy is refused before anything is written
        Assert.Throws<InvalidOperationException>(() => UfoData.Copy(Path.Combine(f.Root, "nowhere"), Path.Combine(f.Root, "dest2")));
        Assert.False(Directory.Exists(Path.Combine(f.Root, "dest2")));
    }
}
