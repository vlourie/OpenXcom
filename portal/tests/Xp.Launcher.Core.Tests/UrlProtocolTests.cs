namespace Xp.Launcher.Core.Tests;

public sealed class UrlProtocolTests
{
    sealed class FakeRegistry : IRegistryValues
    {
        public readonly Dictionary<(string, string?), string> Values = new();
        public int Writes;
        public string? Get(string subKey, string? name) => Values.GetValueOrDefault((subKey, name));
        public void Set(string subKey, string? name, string value) { Values[(subKey, name)] = value; Writes++; }
    }

    const string Exe = @"C:\Games\X-Piratez\XPiratezLauncher.exe";

    [Fact]
    public void The_scheme_opens_this_exe_with_the_link()
    {
        var reg = new FakeRegistry();

        Assert.Equal(4, UrlProtocol.Register(reg, Exe));

        Assert.Equal("", reg.Values[("xpiratez", "URL Protocol")]);
        Assert.Equal("\"" + Exe + "\" \"%1\"", reg.Values[(@"xpiratez\shell\open\command", null)]);
    }

    [Fact]
    public void A_second_start_writes_nothing_a_moved_launcher_rewrites_the_path()
    {
        var reg = new FakeRegistry();
        UrlProtocol.Register(reg, Exe);
        reg.Writes = 0;

        Assert.Equal(0, UrlProtocol.Register(reg, Exe));
        Assert.Equal(2, UrlProtocol.Register(reg, @"D:\XP\XPiratezLauncher.exe"));
        Assert.Equal(2, reg.Writes);
        Assert.StartsWith("\"D:\\XP\\", reg.Values[(@"xpiratez\shell\open\command", null)]);
    }

    [Theory]
    [InlineData("show", true, null)]
    [InlineData("voice abcdefgh23", true, "abcdefgh23")]
    [InlineData("voice ABCDEFGH23\r\n", true, "abcdefgh23")]
    [InlineData("voice ../x", false, null)]
    [InlineData("voice ", false, null)]
    [InlineData("run calc.exe", false, null)]
    [InlineData(null, false, null)]
    public void Signals_between_launchers(string? line, bool ok, string? room) =>
        Assert.Equal((ok, room), LauncherSignal.Parse(line));

    [Fact]
    public void A_signal_reads_back_and_the_pipe_is_per_user()
    {
        Assert.Equal((true, "abcdefgh23"), LauncherSignal.Parse(LauncherSignal.For("abcdefgh23")));
        Assert.Equal((true, (string?)null), LauncherSignal.Parse(LauncherSignal.For(null)));
        Assert.NotEqual(LauncherSignal.PipeName("Вася", 1), LauncherSignal.PipeName("Петя", 1));
        Assert.DoesNotContain('\\', LauncherSignal.PipeName(@"DOMAIN\user", 2));
    }
}
