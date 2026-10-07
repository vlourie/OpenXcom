using System.Text.Json;

namespace Xp.Launcher.Core.Tests;

/// <summary>
/// The launcher tells the player what a profile changed in words (Xp.Launcher/ProfileText.cs):
/// every option our profiles set needs a string in both languages, or it shows up as "oxceHdUi = 2".
/// </summary>
public sealed class ProfileWordsTests
{
    static string Portal()
    {
        for (var d = new DirectoryInfo(AppContext.BaseDirectory); d is not null; d = d.Parent)
            if (File.Exists(Path.Combine(d.FullName, "profiles", ProfileSet.FileName))) return d.FullName;
        throw new DirectoryNotFoundException("portal/profiles not found above " + AppContext.BaseDirectory);
    }

    [Theory]
    [InlineData("ru")]
    [InlineData("en")]
    public void Every_option_of_our_profiles_has_words_for_the_player(string lang)
    {
        var portal = Portal();
        var set = ProfileSet.Load(Path.Combine(portal, "profiles"))!;
        var strings = JsonSerializer.Deserialize<Dictionary<string, string>>(
            File.ReadAllText(Path.Combine(portal, "src", "Xp.Launcher", "Strings", lang + ".json")))!;

        var missing = set.Profiles.SelectMany(p => p.Options)
            .Where(o => !strings.ContainsKey($"pc.opt.{o.Key}.{o.Value}") && !strings.ContainsKey("pc.opt." + o.Key))
            .Select(o => $"{o.Key}={o.Value}").ToList();
        Assert.Empty(missing);
        // "auto" becomes a number on the player's screen: the key needs its own string with {0}
        foreach (var o in set.Profiles.SelectMany(p => p.Options).Where(o => o.Value == "auto"))
            Assert.Contains("{0}", strings["pc.opt." + o.Key]);
    }
}
