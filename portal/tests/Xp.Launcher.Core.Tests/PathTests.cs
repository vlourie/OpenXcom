using Xp.Manifest;
using Xp.ReleaseBuilder;

namespace Xp.Launcher.Core.Tests;

public sealed class PathTests
{
    [Theory]
    [InlineData("user/mods/hd/hd/TERRAIN/DESERT.PCK/0.png")]
    [InlineData("openxcom_hd.exe")]
    [InlineData("common/Language/ru.yml")]
    public void Ordinary_paths_pass(string p) => Assert.Null(SafePath.Validate(p));

    [Theory]
    [InlineData("")]
    [InlineData("/etc/passwd")]
    [InlineData("a//b")]
    [InlineData("a/./b")]
    [InlineData("a/../b")]
    [InlineData("C:/x")]
    [InlineData("a\b")]
    [InlineData("nul")]
    [InlineData("dir/COM1.txt")]
    [InlineData("dir/name.")]
    [InlineData("dir/ name")]
    [InlineData("a\u0001b")]
    public void Dangerous_paths_fail(string p) => Assert.NotNull(SafePath.Validate(p));

    [Fact]
    public void Resolve_never_leaves_the_base()
    {
        var root = Path.Combine(Path.GetTempPath(), "xp-base");
        Assert.StartsWith(root, SafePath.Resolve(root, "a/b.txt"));
        Assert.Throws<UnsafePathException>(() => SafePath.Resolve(root, "../x"));
    }

    [Fact]
    public void Auto_roots_cover_mods_one_by_one_and_never_user_itself()
    {
        var roots = ReleaseRepo.AutoRoots(["openxcom_hd.exe", "common/a.yml", "user/mods/hd/x.png", "user/mods/intro_voice/y.ogg"], launcherKind: false);
        Assert.Equal(["common/", "openxcom_hd.exe", "user/mods/hd/", "user/mods/intro_voice/"], roots);
        Assert.Throws<InvalidOperationException>(() => ReleaseRepo.AutoRoots(["user/piratez/save.sav"], false));
    }

    [Theory]
    [InlineData("user/options.cfg", true)]
    [InlineData("user/piratez/a.sav", true)]
    [InlineData("user/mods/hd/x.png", false)]
    [InlineData("launcher/state.json", true)]
    [InlineData("common/x.yml", false)]
    public void Install_policy(string p, bool isProtected) => Assert.Equal(isProtected, InstallPolicy.WhyProtected(p) is not null);
}
