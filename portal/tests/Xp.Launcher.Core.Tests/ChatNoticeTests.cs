using System.Text;

namespace Xp.Launcher.Core.Tests;

public sealed class ChatNoticeTests : IDisposable
{
    readonly string _root = Path.Combine(Path.GetTempPath(), "xp-tests", Guid.NewGuid().ToString("N"));
    readonly GamePaths _paths;

    public ChatNoticeTests()
    {
        Directory.CreateDirectory(_root);
        _paths = new GamePaths(_root);
    }

    public void Dispose()
    {
        try { Directory.Delete(_root, recursive: true); } catch (IOException) { }
    }

    [Fact]
    public void The_game_reads_a_counter_and_one_line_in_the_launcher_folder()
    {
        var counter = ChatNotice.Write(_paths, "Маша", "привет, Hello!");
        Assert.True(counter > 0);
        Assert.Equal(Path.Combine(_root, "launcher", "chat.txt"), ChatNotice.PathIn(_paths));
        // what src/Engine/HdChatNotice reads: the counter, a newline, "nick: text", a newline, no BOM
        var bytes = File.ReadAllBytes(ChatNotice.PathIn(_paths));
        Assert.NotEqual(0xEF, bytes[0]);
        Assert.Equal(counter + "\nМаша: привет, Hello!\n", Encoding.UTF8.GetString(bytes));
        Assert.False(File.Exists(ChatNotice.PathIn(_paths) + ".tmp"));
    }

    [Fact]
    public void The_counter_only_grows_even_after_a_clear()
    {
        var a = ChatNotice.Write(_paths, "a", "one");
        var b = ChatNotice.Write(_paths, "a", "two");
        ChatNotice.Clear(_paths);
        Assert.False(File.Exists(ChatNotice.PathIn(_paths)));
        var c = ChatNotice.Write(_paths, "a", "three");
        Assert.True(a < b && b < c);
        ChatNotice.Clear(_paths);
        ChatNotice.Clear(_paths);                   // nothing there: no error
    }

    [Fact]
    public void The_text_is_one_short_clean_line()
    {
        Assert.Equal("a: b c d", ChatNotice.Line(" a\n", "b\r\n\tc\u0001 ‮ d  "));
        Assert.Equal("", ChatNotice.Line("a", " \n\t "));
        Assert.Equal("", ChatNotice.Line("a", null));
        Assert.Equal("text", ChatNotice.Line(null, "text"));

        var longNick = new string('n', 100);
        var line = ChatNotice.Line(longNick, new string('x', 1000));
        Assert.Equal(ChatNotice.MaxLine, line.Length);
        Assert.StartsWith(new string('n', ChatNotice.MaxNick) + ": x", line);

        // a pair of surrogates is never cut in half
        var emoji = char.ConvertFromUtf32(0x1F600);
        var cut = ChatNotice.Line("", new string('x', ChatNotice.MaxLine - 1) + emoji);
        Assert.Equal(ChatNotice.MaxLine - 1, cut.Length);
        Assert.DoesNotContain(cut, char.IsSurrogate);
    }

    [Fact]
    public void Nothing_to_show_writes_nothing()
    {
        Assert.Equal(0, ChatNotice.Write(_paths, "a", "  "));
        Assert.False(File.Exists(ChatNotice.PathIn(_paths)));
    }
}
