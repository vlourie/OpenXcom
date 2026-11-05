using System.Diagnostics;
using System.Reflection;
using System.Text.Json;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Headless;
using Avalonia.Headless.XUnit;
using Avalonia.Input;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Threading;
using Avalonia.VisualTree;
using Xp.Launcher;
using Xp.Launcher.Core;
using Xunit.Abstractions;

namespace Xp.Launcher.Ui.Tests;

/// <summary>
/// Frames of the look (docs/portal/VOICE_IRC.md §8): the pages of the real window in Russian, the setup wizard, the report
/// window, an open drop-down and a gallery of every control kind in its states. Off screen (Headless + Skia), nothing starts.
/// Runs only when XP_SKIN_SHOTS names the folder for the frames. The game folder is a throwaway one in %TEMP%.
/// </summary>
public sealed class SkinShotsTests : IDisposable
{
    const string PlayerCfg =
        "mods:\n  - active: false\n    id: xcom1\n  - active: true\n    id: piratez\n  - active: true\n    id: hd\n" +
        "options:\n  language: ru-RU\n  oxceHdMode: 2\n  oxceRecommendedOptionsWereSet: true\n";

    readonly ITestOutputHelper _out;
    readonly string _root = Path.Combine(Path.GetTempPath(), "xp-ui-tests", "skin-" + Guid.NewGuid().ToString("N"));
    readonly string? _shots = Environment.GetEnvironmentVariable("XP_SKIN_SHOTS") is { Length: > 0 } s ? s : null;
    string Game => Path.Combine(_root, "game");

    public SkinShotsTests(ITestOutputHelper output)
    {
        _out = output;
        if (_shots is null) return;
        Directory.CreateDirectory(_shots);
        Write("standard/xcom1/metadata.yml", "id: xcom1\nisMaster: true\n");
        Write("user/mods/Piratez/metadata.yml", "id: piratez\nname: X-Piratez\nisMaster: true\nmaster: xcom1\n");
        Write("user/mods/hd/metadata.yml", "id: hd\nname: X-Piratez HD\nmaster: \"*\"\n");
        Write("common/readme.txt", "");
        Write("user/options.cfg", PlayerCfg);
        File.Copy(Path.Combine(Environment.SystemDirectory, "PING.EXE"), Path.Combine(Game, "openxcom_hd.exe"));
        Write("launcher/state.json",
            $"{{\"channel\":\"stable\",\"installedReleaseId\":\"2026.11.05\",\"installedVersion\":\"2026.11.05\"," +
            $"\"lastScanUtc\":\"{DateTime.UtcNow.AddMinutes(-1):O}\",\"lastScanReleaseId\":\"2026.11.05\"}}");
        File.Copy(Path.Combine(Repo(), "portal", "profiles", "xp-profiles.json"), Path.Combine(Game, "xp-profiles.json"));
        Settings.DirOverride = Path.Combine(_root, "settings");
        new Settings { GameDir = Game, RepoUrl = "http://127.0.0.1:9/", PortalUrl = "not a url", Language = "ru" }.Save();
        L.Use("ru");
    }

    public void Dispose()
    {
        Settings.DirOverride = null;
        try { Directory.Delete(_root, recursive: true); } catch (IOException) { } catch (UnauthorizedAccessException) { }
    }

    static string Repo()
    {
        for (var d = new DirectoryInfo(AppContext.BaseDirectory); d is not null; d = d.Parent)
            if (File.Exists(Path.Combine(d.FullName, "portal", "profiles", "xp-profiles.json"))) return d.FullName;
        throw new DirectoryNotFoundException("the repository above " + AppContext.BaseDirectory);
    }

    void Write(string rel, string text)
    {
        var p = Path.Combine(Game, rel);
        Directory.CreateDirectory(Path.GetDirectoryName(p)!);
        File.WriteAllText(p, text);
    }

    static T F<T>(object o, string name) =>
        (T)o.GetType().GetField(name, BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(o)!;

    static void Idle(int ms)
    {
        var sw = Stopwatch.StartNew();
        while (sw.ElapsedMilliseconds < ms)
        {
            Dispatcher.UIThread.RunJobs();
            AvaloniaHeadlessPlatform.ForceRenderTimerTick();
            Thread.Sleep(10);
        }
    }

    static void Pump(Func<bool> until, string what, int ms = 60000)
    {
        var sw = Stopwatch.StartNew();
        while (!until())
        {
            Dispatcher.UIThread.RunJobs();
            AvaloniaHeadlessPlatform.ForceRenderTimerTick();
            if (sw.ElapsedMilliseconds > ms) throw new TimeoutException("waited for " + what);
            Thread.Sleep(10);
        }
        Dispatcher.UIThread.RunJobs();
    }

    static Point Centre(Control c) => c.TranslatePoint(new Point(c.Bounds.Width / 2, c.Bounds.Height / 2), TopLevel.GetTopLevel(c)!)!.Value;

    static void Click(Control c)
    {
        c.BringIntoView();
        Idle(100);
        var top = TopLevel.GetTopLevel(c)!;
        var p = Centre(c);
        top.MouseMove(p, RawInputModifiers.None);
        top.MouseDown(p, MouseButton.Left, RawInputModifiers.None);
        top.MouseUp(p, MouseButton.Left, RawInputModifiers.None);
        Idle(100);
    }

    void Shot(TopLevel top, string name)
    {
        Idle(300);
        var frame = top.CaptureRenderedFrame();
        if (frame is null) { _out.WriteLine("no frame for " + name); return; }
        var path = Path.Combine(_shots!, name + ".png");
        frame.Save(path);
        _out.WriteLine("frame: " + path);
    }

    [AvaloniaFact]
    public void Pages_of_the_window()
    {
        if (_shots is null) return;
        var w = new MainWindow([]) { WindowState = WindowState.Normal, Width = 1280, Height = 800 };
        w.Show();
        Pump(() => F<object?>(w, "_updater") is not null, "the updater");
        Idle(2500);
        Shot(w, "01-home");
        // hover over the rail item and the main button; the pointer stays there for the frame
        var nav = F<Dictionary<string, Button>>(w, "_nav");
        w.MouseMove(Centre(nav["support"]), RawInputModifiers.None);
        Shot(w, "01b-home-rail-hover");
        foreach (var page in new[] { "news", "reports", "support", "settings" })
        {
            Click(nav[page]);
            Idle(1500);
            Shot(w, "02-" + page);
        }
        // the open drop-down of the language in Settings
        var language = F<ComboBox>(w, "_language");
        language.IsDropDownOpen = true;
        Shot(w, "03-settings-dropdown");
        language.IsDropDownOpen = false;
        Click(nav["home"]);
        var build = F<ComboBox>(w, "_build");
        if (build.Items.Count > 0)
        {
            build.IsDropDownOpen = true;
            Shot(w, "03b-home-dropdown");
            build.IsDropDownOpen = false;
        }
        w.Close();
    }

    [AvaloniaFact]
    public void Setup_wizard()
    {
        if (_shots is null) return;
        var setup = new SetupPage(new Settings { Language = "ru" }, () => null);
        var w = new Window { Width = 1280, Height = 800, Content = setup };
        w.Show();
        setup.Start(null);
        Idle(800);
        Shot(w, "04-setup-where");
        w.Close();
    }

    [AvaloniaFact]
    public void Reports_and_the_report_window()
    {
        if (_shots is null) return;
        var reports = Path.Combine(_root, "reports");
        var t0 = DateTimeOffset.UtcNow.AddHours(-3);
        void Sent(long number, string title, string status, DateTimeOffset? reply = null, string? text = null)
        {
            var id = Guid.NewGuid().ToString();
            var dir = Path.Combine(reports, id);
            Directory.CreateDirectory(dir);
            File.WriteAllText(Path.Combine(dir, Report.DraftFile), JsonSerializer.Serialize(new
            {
                id, title, kind = "bug", status = "Sent", token = "tok", ticketNumber = number, displayNumber = $"XP-{number:D6}",
                ticketUrl = $"https://p.test/t/{number}?k=tok", ticketStatus = status, staffReply = text, staffReplyAt = reply, statusChangedAt = reply,
                createdAt = t0.AddDays(-1), checkedAt = DateTimeOffset.UtcNow,
            }));
        }
        Sent(1, "Нужна подробность", "NeedsInfo", t0, "Какой мод включён?");
        Sent(2, "Есть ответ", "InProgress", t0, "Смотрим");
        Sent(3, "Тихий", "InProgress");
        Sent(4, "Давно закрыт", "Closed", t0.AddDays(-5));
        var draftId = Guid.NewGuid().ToString();
        var draftDir = Path.Combine(reports, draftId);
        Directory.CreateDirectory(draftDir);
        File.WriteAllText(Path.Combine(draftDir, Report.DraftFile),
            JsonSerializer.Serialize(new { id = draftId, title = "Черновик без номера", kind = "bug", status = "Draft", createdAt = t0 }));
        var settings = new Settings { PortalUrl = "not a url", SeenTickets = new() { ["4"] = t0 } };
        var page = new ReportsPage(settings, () => [reports]);
        var w = new Window { Width = 1100, Height = 800, Content = page, Background = Skin.B(Skin.Bg) };
        w.Show();
        page.Shown();
        Idle(500);
        Shot(w, "05-reports-list");
        w.Close();

        var rw = new ReportWindow(Report.Open(draftDir), settings);
        rw.Show();
        Idle(500);
        Shot(rw, "06-report-window");
        rw.Close();
    }

    /// <summary>Every kind of button and field in a row, then the same with the pointer over one and the keyboard on another.</summary>
    [AvaloniaFact]
    public void Gallery()
    {
        if (_shots is null) return;
        Control Row(string caption, params Control[] items)
        {
            var r = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 10 };
            foreach (var i in items) r.Children.Add(i);
            var s = new StackPanel { Spacing = 6 };
            s.Children.Add(Skin.H2(caption));
            s.Children.Add(r);
            return s;
        }
        Button Off(Button b) { b.IsEnabled = false; return b; }
        var main = Skin.Btn("Главная", "primary");
        var normal = Skin.Btn("Обычная");
        var quiet = Skin.Btn("Тихая", "quiet");
        var danger = Skin.Btn("Опасная", "warn");
        var combo = new ComboBox { MinWidth = 200, Items = { new ComboBoxItem { Content = "Русский" }, new ComboBoxItem { Content = "English" }, new ComboBoxItem { Content = "Polski" } } };
        combo.SelectedIndex = 0;
        var tabs = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 4 };
        tabs.Children.Add(Skin.Btn("Вкладка 1", "tab on"));
        tabs.Children.Add(Skin.Btn("Вкладка 2", "tab"));
        var slider = new Slider { Minimum = 0, Maximum = 100, Value = 40, Width = 200 };
        var box = new TextBox { Text = "Поле ввода", Width = 200 };
        var empty = new TextBox { Watermark = "Подсказка в поле", Width = 200 };
        var tip = Skin.Btn("С подсказкой");
        ToolTip.SetTip(tip, "Всплывающая подсказка");
        var scroll = new ScrollViewer { Height = 80, Width = 220, Content = new TextBlock { Text = string.Join("\n", Enumerable.Range(1, 12).Select(i => "Строка " + i)) } };
        var list = new StackPanel { Spacing = 16, Margin = new Thickness(24) };
        list.Children.Add(Row("Кнопки", main, normal, quiet, danger));
        list.Children.Add(Row("Недоступные", Off(Skin.Btn("Главная", "primary")), Off(Skin.Btn("Обычная")), Off(Skin.Btn("Тихая", "quiet")), Off(Skin.Btn("Опасная", "warn"))));
        list.Children.Add(Row("Поля", box, empty, combo, new TextBox { Text = "Недоступное", IsEnabled = false, Width = 200 }));
        list.Children.Add(Row("Галочки, ползунок, вкладки", new CheckBox { Content = "Галочка", IsChecked = true }, new CheckBox { Content = "Пустая" },
            new RadioButton { Content = "Выбор", IsChecked = true }, new RadioButton { Content = "Выбор 2" }, slider, tabs));
        list.Children.Add(Row("Подсказка, прокрутка", tip, scroll, new ProgressBar { Minimum = 0, Maximum = 100, Value = 40, Width = 200 }));
        var w = new Window { Width = 1000, Height = 640, Content = list };
        w.Show();
        Idle(500);
        Shot(w, "07-gallery");
        // the pointer over "Обычная", then over "Главная" pressed, then the keyboard on "Тихая"
        w.MouseMove(Centre(normal), RawInputModifiers.None);
        Shot(w, "07b-gallery-hover-normal");
        w.MouseMove(Centre(main), RawInputModifiers.None);
        Shot(w, "07c-gallery-hover-main");
        w.MouseDown(Centre(main), MouseButton.Left, RawInputModifiers.None);
        Shot(w, "07d-gallery-pressed-main");
        w.MouseUp(Centre(main), MouseButton.Left, RawInputModifiers.None);
        w.MouseMove(new Point(2, 2), RawInputModifiers.None);
        quiet.Focus(NavigationMethod.Tab);
        Shot(w, "07e-gallery-focus-quiet");
        danger.Focus(NavigationMethod.Tab);
        Shot(w, "07f-gallery-focus-danger");
        combo.IsDropDownOpen = true;
        Shot(w, "07g-gallery-dropdown");
        combo.IsDropDownOpen = false;
        w.MouseMove(Centre(tip), RawInputModifiers.None);
        ToolTip.SetIsOpen(tip, true);
        Idle(500);
        Shot(w, "07h-gallery-tooltip");
        ToolTip.SetIsOpen(tip, false);
        w.MouseMove(Centre(scroll), RawInputModifiers.None);
        Idle(600);
        Shot(w, "07i-gallery-scroll-hover");
        w.Close();
    }
}
