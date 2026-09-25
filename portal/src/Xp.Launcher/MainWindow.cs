using System.Diagnostics;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Documents;
using Avalonia.Input;
using Avalonia.Interactivity;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Platform.Storage;
using Avalonia.Threading;
using Xp.Launcher.Core;
using Xp.Manifest;

namespace Xp.Launcher;

/// <summary>
/// The launcher: a rail with four pages (docs/portal/LAUNCHER_UI.md). The home page has one main
/// button whose caption is the status; everything rare lives in Settings.
/// </summary>
public sealed class MainWindow : Window
{
    enum Work { None, Check, Update, Repair, Rollback, SelfUpdate }

    readonly Settings _settings = Settings.Load();
    readonly HttpClient _http = RepoClient.NewHttpClient();
    readonly string[] _args;

    // rail
    readonly Dictionary<string, Button> _nav = new();
    readonly Dictionary<string, Control> _pages = new();
    readonly Border _reportsBadge = new() { Background = Skin.B(Skin.Accent), CornerRadius = new CornerRadius(2), Padding = new Thickness(6, 1), IsVisible = false, VerticalAlignment = VerticalAlignment.Center };
    readonly TextBlock _reportsCount = new() { Foreground = Skin.B(Skin.OnAccent), FontSize = 12, FontFamily = Skin.Medium };

    // home
    readonly Border _notice = new() { Background = Skin.B(Skin.WarnFill), BorderBrush = Skin.B(Skin.WarnFrame), BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(2), Padding = new Thickness(14, 8), IsVisible = false, Margin = new Thickness(0, 0, 0, 16) };
    readonly TextBlock _version = new() { FontSize = 14, Foreground = Skin.B(Skin.Muted) };
    readonly Button _main = new() { Height = 64, HorizontalAlignment = HorizontalAlignment.Stretch, HorizontalContentAlignment = HorizontalAlignment.Center, VerticalContentAlignment = VerticalAlignment.Center, FontFamily = Skin.Medium, FontSize = 22 };
    readonly TextBlock _mainText = new();
    readonly ProgressBar _progress = new() { Minimum = 0, Maximum = 1000, Height = 4, MinHeight = 4, VerticalAlignment = VerticalAlignment.Bottom, Margin = new Thickness(2), IsVisible = false, CornerRadius = new CornerRadius(0) };
    readonly WrapPanel _sub = new() { Orientation = Orientation.Horizontal, MinHeight = 20 };
    readonly TextBlock _current = new() { FontSize = 11, Foreground = Skin.B(Skin.Dim), TextTrimming = TextTrimming.CharacterEllipsis };
    readonly Border _whatsNew;
    readonly TextBlock _whatsNewTitle = new() { FontFamily = Skin.Medium, FontSize = 18, TextWrapping = TextWrapping.Wrap };
    readonly TextBlock _changelog = new() { TextWrapping = TextWrapping.Wrap, FontSize = 13, LineHeight = 19, Foreground = Skin.B(Skin.Text2) };

    // settings
    readonly TextBox _gameDir = new() { IsReadOnly = true, FontSize = 13 };
    readonly ComboBox _language = new() { HorizontalAlignment = HorizontalAlignment.Stretch, FontSize = 13 };
    readonly TextBlock _languageNote = new() { FontSize = 12, Foreground = Skin.B(Skin.Muted), IsVisible = false, TextWrapping = TextWrapping.Wrap };
    readonly TextBlock _installed = new() { FontSize = 13, Foreground = Skin.B(Skin.Text2), TextWrapping = TextWrapping.Wrap };
    readonly TextBlock _launcherLine = new() { FontSize = 12, Foreground = Skin.B(Skin.Muted), VerticalAlignment = VerticalAlignment.Center, TextWrapping = TextWrapping.Wrap };
    readonly TextBlock _rollbackNote = new() { FontSize = 12, Foreground = Skin.B(Skin.Muted), TextWrapping = TextWrapping.Wrap };
    readonly TextBlock _log = new() { FontFamily = new FontFamily("Consolas,monospace"), FontSize = 11, TextWrapping = TextWrapping.Wrap, Foreground = Skin.B(Skin.Muted), LineHeight = 16 };
    readonly Button _check, _repair, _rollback, _selfUpdate, _choose, _updateOnly, _components, _resetProfile;

    readonly SetupPage _setupPage;
    readonly ReportsPage _reportsPage;
    readonly ReviewPage _reviewPage;
    readonly AccountPanel _account;

    GamePaths? _paths;
    Updater? _updater;
    FileLog? _fileLog;
    RepoClient? _repo;
    LatestRelease? _latest;
    ReleaseManifest? _launcherUpdate;
    CancellationTokenSource? _cts;
    Process? _game;
    Work _work;
    bool _cancelable;
    long _lastProgressTicks;

    // what the main button says, besides "busy" and "running"
    string? _pendingLine;       // an update or a repair is waiting: its one-line summary
    Version? _needLauncher;     // the release asks for a newer launcher
    string? _offline;           // the last check could not reach the server
    string? _error;             // the last update failed
    string? _note;              // a neutral one-off result ("rolled back to 1.2")
    string _progressLine = "";
    double _percent;
    Phase _phase;

    public MainWindow(string[] args)
    {
        _args = args;
        Title = L.T("title") + " " + BuiltIn.VersionText;
        Width = _settings.WindowWidth is >= 800 and <= 4000 ? _settings.WindowWidth.Value : 960;
        Height = _settings.WindowHeight is >= 520 and <= 3000 ? _settings.WindowHeight.Value : 600;
        MinWidth = 800; MinHeight = 520;
        WindowStartupLocation = WindowStartupLocation.CenterScreen;
        // открываемся во весь экран: паре картинок на вкладке «Графика» нужно место, а окно,
        // размер которого свой на каждой машине, даёт кадру каждый раз разное
        WindowState = WindowState.Maximized;

        _check = Skin.Btn(L.T("checkUpdates"), "ghost");
        _check.Click += async (_, _) => await RunAsync(Work.Check, () => CheckAsync(full: false, apply: false));
        // «Играть» обновляет и запускает; эта кнопка только обновляет - игру запускать не обязательно
        _updateOnly = Skin.Btn(L.T("main.updateOnly"), "ghost", 64);
        _updateOnly.Click += async (_, _) => await RunAsync(Work.Check, () => CheckAsync(full: false, apply: true));
        _repair = Skin.Btn(L.T("repair"));
        _repair.HorizontalContentAlignment = HorizontalAlignment.Left;
        _repair.Click += async (_, _) => await RunAsync(Work.Repair, () => CheckAsync(full: true, apply: true));
        _rollback = Skin.Btn(L.T("rollback"), "warn");
        _rollback.HorizontalContentAlignment = HorizontalAlignment.Left;
        _rollback.Click += async (_, _) => await RunAsync(Work.Rollback, RollbackAsync);
        _selfUpdate = Skin.Btn(L.T("self.install"), "primary");
        _selfUpdate.IsVisible = false;
        _selfUpdate.Click += async (_, _) => await RunAsync(Work.SelfUpdate, SelfUpdateAsync);
        _choose = Skin.Btn(L.T("settings.change"));
        _choose.Click += async (_, _) => await ChooseGameDirAsync();
        _components = Skin.Btn(L.T("settings.components"));
        _components.Click += (_, _) => OpenSetup(_paths?.GameDir);
        _resetProfile = Skin.Btn(L.T("settings.resetProfile"));
        _resetProfile.Click += async (_, _) => await ResetProfileAsync();
        _main.Content = _mainText;
        _main.Click += async (_, _) => await OnMainAsync();

        _reportsPage = new ReportsPage(_settings, ReportRoots);
        _reportsPage.Changed += CountReports;
        _reviewPage = new ReviewPage(_settings, () => _paths?.GameDir);
        _account = new AccountPanel(_settings);
        _setupPage = new SetupPage(_settings, () => _repo);
        _setupPage.Finished += (dir, play) => OnSetupFinished(dir, play);
        _setupPage.PickExisting += async () => await ChooseGameDirAsync();

        _whatsNew = Skin.Panel(WhatsNewContent(), new Thickness(20));
        _whatsNew.Width = 250;
        _whatsNew.IsVisible = false;

        _pages["home"] = HomePage();
        _pages["setup"] = _setupPage;
        _pages["reports"] = _reportsPage;
        _pages["review"] = _reviewPage;
        _pages["support"] = new SupportPage();
        _pages["settings"] = SettingsPage();

        var host = new Panel();
        foreach (var p in _pages.Values) host.Children.Add(p);
        var root = new Grid { ColumnDefinitions = new ColumnDefinitions("180,*") };
        root.Children.Add(RailPanel());
        Grid.SetColumn(host, 1);
        root.Children.Add(host);
        Content = root;
        // F11 - весь экран без заголовка окна и панели задач: для разбора картинок кадром больше
        AddHandler(KeyDownEvent, (object? _, KeyEventArgs e) =>
        {
            if (e.Key is not Key.F11) return;
            WindowState = WindowState == WindowState.FullScreen ? WindowState.Maximized : WindowState.FullScreen;
            e.Handled = true;
        }, RoutingStrategies.Tunnel);
        Navigate("home");
#if DEBUG
        // screenshots of every page without clicking through them
        if (Array.IndexOf(args, "--page") is var i and >= 0 && i + 1 < args.Length && _pages.ContainsKey(args[i + 1])) Navigate(args[i + 1]);
#endif

        Opened += async (_, _) =>
        {
            await StartupAsync();
#if DEBUG
            // the wizard for screenshots: --setup new (its first step), --setup <scratch dir> (the list of components);
            // only after the start-up check, the wizard does not open while the launcher is busy
            if (Array.IndexOf(args, "--setup") is var j and >= 0 && j + 1 < args.Length) OpenSetup(args[j + 1] == "new" ? null : args[j + 1]);
#endif
        };
        Closing += (_, _) =>
        {
            _cts?.Cancel();
            if (WindowState == WindowState.Normal)
            {
                _settings.WindowWidth = Width;
                _settings.WindowHeight = Height;
                try { _settings.Save(); } catch (IOException) { }
            }
        };
    }

    // ------------------------------------------------------------------ layout

    Control RailPanel()
    {
        var logo = new TextBlock { FontFamily = Skin.Medium, FontWeight = FontWeight.Bold, FontSize = 20, LineHeight = 21, Margin = new Thickness(12, 0, 12, 24) };
        logo.Inlines!.Add(new Run("X-PIRATEZ"));
        logo.Inlines.Add(new LineBreak());
        logo.Inlines.Add(new Run("HD") { Foreground = Skin.B(Skin.Accent) });

        var top = new StackPanel { Spacing = 2 };
        top.Children.Add(logo);
        top.Children.Add(NavButton("home", "nav.home", Skin.IconHome, null));
        _reportsBadge.Child = _reportsCount;
        top.Children.Add(NavButton("reports", "nav.reports", Skin.IconReports, _reportsBadge));
        top.Children.Add(NavButton("review", "nav.review", Skin.IconCheck, null));
        top.Children.Add(NavButton("support", "nav.support", Skin.IconHeart, null));
        top.Children.Add(NavButton("settings", "nav.settings", Skin.IconSettings, null));

        var site = NavLike(L.T("nav.site") + "  ↗", Skin.IconGlobe, null);
        site.Foreground = Skin.B(Skin.Accent);
        var portal = _settings.PortalUrl ?? BuiltIn.Defaults.PortalUrl;
        site.IsEnabled = portal.StartsWith("http", StringComparison.OrdinalIgnoreCase);
        site.Click += (_, _) => ReportWindow.OpenUrl(portal);
        var quit = NavLike(L.T("nav.quit"), Skin.IconQuit, null);
        quit.Click += (_, _) => Close();

        var bottom = new StackPanel();
        bottom.Children.Add(site);
        bottom.Children.Add(quit);
        bottom.Children.Add(new TextBlock { Text = L.T("nav.version", BuiltIn.VersionText), FontSize = 12, Foreground = Skin.B(Skin.Muted), Margin = new Thickness(12, 8, 12, 0) });

        var dock = new DockPanel { Margin = new Thickness(12, 24, 12, 16) };
        DockPanel.SetDock(bottom, Dock.Bottom);
        dock.Children.Add(bottom);
        dock.Children.Add(top);
        return new Border { Background = Skin.B(Skin.Rail), BorderBrush = Skin.B(Skin.Track), BorderThickness = new Thickness(0, 0, 1, 0), Child = dock };
    }

    Button NavButton(string page, string key, string icon, Control? badge)
    {
        var b = NavLike(L.T(key), icon, badge);
        b.Click += (_, _) => Navigate(page);
        _nav[page] = b;
        return b;
    }

    static Button NavLike(string text, string icon, Control? badge)
    {
        var b = new Button { Height = 44, HorizontalAlignment = HorizontalAlignment.Stretch, HorizontalContentAlignment = HorizontalAlignment.Stretch, VerticalContentAlignment = VerticalAlignment.Center, Padding = new Thickness(12, 0), FontSize = 15, BorderThickness = new Thickness(0) };
        b.Classes.Add("nav");
        var row = new DockPanel();
        var ic = Skin.Icon(icon, b);
        ic.Margin = new Thickness(0, 0, 12, 0);
        DockPanel.SetDock(ic, Dock.Left);
        row.Children.Add(ic);
        if (badge is not null) { DockPanel.SetDock(badge, Dock.Right); row.Children.Add(badge); }
        row.Children.Add(new TextBlock { Text = text, VerticalAlignment = VerticalAlignment.Center });
        b.Content = row;
        return b;
    }

    void Navigate(string page)
    {
        foreach (var (name, p) in _pages) p.IsVisible = name == page;
        foreach (var (name, b) in _nav)
        {
            bool on = name == page;
            b.Classes.Set("on", on);
            b.BorderThickness = new Thickness(on ? 3 : 0, 0, 0, 0);
        }
        if (page == "reports") _reportsPage.Shown();
        if (page == "review") _reviewPage.Shown();
    }

    Control HomePage()
    {
        var title = new TextBlock { FontFamily = Skin.Medium, FontWeight = FontWeight.Bold, FontSize = 44, LetterSpacing = 1 };
        title.Inlines!.Add(new Run("X-PIRATEZ "));
        title.Inlines.Add(new Run("HD") { Foreground = Skin.B(Skin.Accent) });
        var heading = new StackPanel { Spacing = 6 };
        heading.Children.Add(new Viewbox { Child = title, Stretch = Stretch.Uniform, StretchDirection = StretchDirection.DownOnly, HorizontalAlignment = HorizontalAlignment.Left });
        heading.Children.Add(_version);

        var mainArea = new Grid { ColumnDefinitions = new ColumnDefinitions("*,Auto") };
        mainArea.Children.Add(_main);
        mainArea.Children.Add(_progress);
        _updateOnly.Margin = new Thickness(10, 0, 0, 0);
        _updateOnly.Padding = new Thickness(22, 0);
        Grid.SetColumn(_updateOnly, 1);
        mainArea.Children.Add(_updateOnly);

        var content = new StackPanel { Spacing = 14, VerticalAlignment = VerticalAlignment.Bottom };
        content.Children.Add(heading);
        content.Children.Add(mainArea);
        content.Children.Add(_sub);
        content.Children.Add(_current);

        var hero = new Grid();
        // the card art: indigo duotone like the pictures in the game's windows; the gradient shows while it loads or if it is missing
        hero.Children.Add(new Border
        {
            CornerRadius = new CornerRadius(3),
            Background = new LinearGradientBrush
            {
                StartPoint = new RelativePoint(0.2, 0, RelativeUnit.Relative),
                EndPoint = new RelativePoint(0.8, 1, RelativeUnit.Relative),
                GradientStops = { new GradientStop(Color.Parse("#181868"), 0), new GradientStop(Color.Parse("#180810"), 1) },
            },
        });
        if (HeroArt() is { } art)
            hero.Children.Add(new Border { CornerRadius = new CornerRadius(3), ClipToBounds = true, Background = new ImageBrush(art) { Stretch = Stretch.UniformToFill } });
        hero.Children.Add(new Border { CornerRadius = new CornerRadius(3), Background = Glow(0.7, 0.3, "#8C185888") });
        hero.Children.Add(new Border { CornerRadius = new CornerRadius(3), Background = Glow(0.2, 0.8, "#CC181868") });
        hero.Children.Add(new Border
        {
            BorderBrush = Skin.B(Skin.FrameOuter), BorderThickness = new Thickness(2), CornerRadius = new CornerRadius(3),
            Child = new Border { BorderBrush = Skin.B(Skin.FrameInner), BorderThickness = new Thickness(2), Padding = new Thickness(28), Child = content },
        });

        var body = new Grid { ColumnDefinitions = new ColumnDefinitions("*,Auto") };
        body.Children.Add(hero);
        _whatsNew.Margin = new Thickness(16, 0, 0, 0);
        Grid.SetColumn(_whatsNew, 1);
        body.Children.Add(_whatsNew);

        var page = new DockPanel { Margin = new Thickness(28, 24, 28, 28) };
        DockPanel.SetDock(_notice, Dock.Top);
        page.Children.Add(_notice);
        page.Children.Add(body);
        return page;
    }

    static Avalonia.Media.Imaging.Bitmap? HeroArt()
    {
        try
        {
            using var s = Avalonia.Platform.AssetLoader.Open(new Uri("avares://XPiratezLauncher/Assets/hero.jpg"));
            return new Avalonia.Media.Imaging.Bitmap(s);
        }
        catch (Exception) { return null; }   // a build without the picture keeps the gradient
    }

    static RadialGradientBrush Glow(double x, double y, string color)
    {
        var c = Color.Parse(color);
        return new()
        {
            Center = new RelativePoint(x, y, RelativeUnit.Relative),
            GradientOrigin = new RelativePoint(x, y, RelativeUnit.Relative),
            RadiusX = new RelativeScalar(0.6, RelativeUnit.Relative),
            RadiusY = new RelativeScalar(0.6, RelativeUnit.Relative),
            // fade to the same colour at zero alpha: fading to Colors.Transparent (white) greys the middle
            GradientStops = { new GradientStop(c, 0), new GradientStop(Color.FromArgb(0, c.R, c.G, c.B), 1) },
        };
    }

    Control WhatsNewContent()
    {
        var dock = new DockPanel();
        _whatsNewTitle.Margin = new Thickness(0, 0, 0, 12);
        DockPanel.SetDock(_whatsNewTitle, Dock.Top);
        dock.Children.Add(_whatsNewTitle);
        dock.Children.Add(new ScrollViewer { Content = _changelog });
        return dock;
    }

    Control SettingsPage()
    {
        var game = Group("settings.game");
        game.Children.Add(Skin.Note(L.T("gameDir"), 13, Skin.Text2));
        var dirRow = new DockPanel();
        _choose.Margin = new Thickness(8, 0, 0, 0);
        DockPanel.SetDock(_choose, Dock.Right);
        dirRow.Children.Add(_choose);
        dirRow.Children.Add(_gameDir);
        game.Children.Add(dirRow);
        var modsRow = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8 };
        modsRow.Children.Add(_components);
        modsRow.Children.Add(_resetProfile);
        game.Children.Add(modsRow);
        game.Children.Add(Skin.Note(L.T("settings.modsHint"), 13, Skin.Text2));
        game.Children.Add(Skin.Note(L.T("settings.language"), 13, Skin.Text2));
        _language.Items.Add(new ComboBoxItem { Content = "Русский", Tag = "ru" });
        _language.Items.Add(new ComboBoxItem { Content = "English", Tag = "en" });
        _language.SelectedIndex = L.Language == "en" ? 1 : 0;
        _language.SelectionChanged += (_, _) =>
        {
            if (_language.SelectedItem is not ComboBoxItem { Tag: string lang }) return;
            _settings.Language = lang;
            try { _settings.Save(); } catch (IOException) { }
            _languageNote.Text = L.T("settings.languageRestart");
            _languageNote.IsVisible = lang != L.Language;
        };
        game.Children.Add(_language);
        game.Children.Add(_languageNote);

        var updates = Group("settings.updates");
        updates.Children.Add(_installed);
        var upRow = new WrapPanel { Orientation = Orientation.Horizontal };
        _check.Margin = new Thickness(0, 0, 10, 6);
        _selfUpdate.Margin = new Thickness(0, 0, 10, 6);
        upRow.Children.Add(_check);
        upRow.Children.Add(_selfUpdate);
        upRow.Children.Add(_launcherLine);
        updates.Children.Add(upRow);

        var broken = Group("settings.broken");
        _repair.HorizontalAlignment = HorizontalAlignment.Stretch;
        _rollback.HorizontalAlignment = HorizontalAlignment.Stretch;
        broken.Children.Add(_repair);
        broken.Children.Add(Skin.Note(L.T("settings.repairHint"), 12));
        broken.Children.Add(_rollback);
        _rollbackNote.Text = L.T("settings.rollbackHint");
        broken.Children.Add(_rollbackNote);

        var log = new StackPanel { Spacing = 10 };
        var logHead = new DockPanel();
        var copy = Skin.Btn(L.T("settings.copy"), null, 28);
        copy.Margin = new Thickness(8, 0, 0, 0);
        copy.FontSize = 12;
        copy.Padding = new Thickness(10, 0);
        copy.Click += async (_, _) => { if (GetTopLevel(this)?.Clipboard is { } c) await c.SetTextAsync(_log.Text ?? ""); };
        var folder = Skin.Btn(L.T("settings.logFolder"), null, 28);
        folder.Margin = new Thickness(8, 0, 0, 0);
        folder.FontSize = 12;
        folder.Padding = new Thickness(10, 0);
        folder.Click += (_, _) => { if (_paths is not null && Directory.Exists(_paths.Logs)) ReportWindow.OpenUrl(_paths.Logs); };
        DockPanel.SetDock(folder, Dock.Right);
        DockPanel.SetDock(copy, Dock.Right);
        logHead.Children.Add(folder);
        logHead.Children.Add(copy);
        logHead.Children.Add(Skin.H2(L.T("log")));
        log.Children.Add(logHead);
        log.Children.Add(new Border
        {
            Background = Skin.B(Skin.Rail), CornerRadius = new CornerRadius(2), Padding = new Thickness(10), Height = 150,
            Child = new ScrollViewer { Content = _log },
        });

        var grid = new Grid { ColumnDefinitions = new ColumnDefinitions("*,14,*"), RowDefinitions = new RowDefinitions("Auto,14,Auto,14,Auto") };
        void Put(Control c, int row, int col) { Grid.SetRow(c, row); Grid.SetColumn(c, col); grid.Children.Add(c); }
        Put(Skin.Panel(game), 0, 0);
        Put(Skin.Panel(updates), 0, 2);
        Put(Skin.Panel(broken), 2, 0);
        Put(Skin.Panel(log), 2, 2);
        var account = Skin.Panel(_account);
        Grid.SetColumnSpan(account, 3);
        Put(account, 4, 0);

        var page = new StackPanel { Spacing = 14, Margin = new Thickness(28, 24, 28, 28) };
        page.Children.Add(Skin.H1(L.T("nav.settings")));
        page.Children.Add(grid);
        return new ScrollViewer { Content = page };
    }

    static StackPanel Group(string key)
    {
        var s = new StackPanel { Spacing = 10 };
        s.Children.Add(Skin.H2(L.T(key)));
        return s;
    }

    // --------------------------------------------------------------- start-up

    async Task StartupAsync()
    {
        var repoUrl = _settings.RepoUrl ?? BuiltIn.Defaults.RepoUrl;
        _repo = new RepoClient(_http, new Uri(repoUrl), BuiltIn.Keys);
        if (_settings.GameDir is { } dir && GamePaths.LooksLikeGameDir(dir)) OpenGameDir(dir);
        Refresh();
        // first start: no game yet - the wizard installs it
        if (_paths is null) OpenSetup(null);
        await _account.CheckAsync();

        if (_updater is not null) await RunAsync(Work.Check, () => CheckAsync(full: false, apply: false));
    }

    void OpenGameDir(string dir)
    {
        _paths = new GamePaths(dir);
        _fileLog = new FileLog(_paths);
        _fileLog.Written += line => Dispatcher.UIThread.Post(() => AppendLog(line));
        _updater = new Updater(_paths, _repo!, _fileLog);
        _gameDir.Text = _paths.GameDir;
        // the review page may already be on screen: until now it had no folder to read packs from
        if (_reviewPage.IsVisible) _reviewPage.Shown();
        _fileLog.Info($"launcher {BuiltIn.VersionText} started, game dir <game>");
        try
        {
            if (_updater.Recover()) SetStatus(L.T("status.recovered"));
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException)
        {
            SetStatus(L.T("err.generic", e.Message));
        }
        TellGameWhereWeAre();
        CountReports();
    }

    /// <summary>
    /// F8 in a game started without us (from its own exe) still needs to find the report form:
    /// the game reads this file when XP_LAUNCHER is not set.
    /// </summary>
    void TellGameWhereWeAre()
    {
        if (_paths is null || Environment.ProcessPath is not { } self) return;
        try
        {
            Directory.CreateDirectory(_paths.StateDir);
            var file = Path.Combine(_paths.StateDir, "launcher-path.txt");
            if (!File.Exists(file) || File.ReadAllText(file).Trim() != self) FileUtil.WriteAtomic(file, System.Text.Encoding.UTF8.GetBytes(self));
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { _fileLog?.Error("launcher-path.txt: " + e.Message); }
    }

    List<string> ReportRoots()
    {
        var roots = new List<string>();
        if (_paths is not null) roots.Add(Path.Combine(_paths.GameDir, "user", "reports"));
        roots.AddRange(_settings.ReportRoots);
        return roots;
    }

    /// <summary>The rail counter and the home notices: reports the team asked about, reports not yet sent.</summary>
    void CountReports()
    {
        var reports = ReportStore.List(ReportRoots());
        var needInfo = reports.Where(r => r.Draft.Status == ReportStatus.Sent && r.Draft.TicketStatus == "NeedsInfo").ToList();
        int unsent = reports.Count(r => r.Draft.Status != ReportStatus.Sent);
        int queued = reports.Count(r => r.Draft.Status == ReportStatus.Queued);
        int count = needInfo.Count + unsent;
        _reportsCount.Text = count.ToString();
        _reportsBadge.IsVisible = count > 0;

        if (needInfo.Count > 0) ShowNotice(L.T("notice.needsInfo", needInfo[0].Draft.DisplayNumber ?? ""), L.T("notice.open"), () => Navigate("reports"));
        else if (_launcherUpdate is not null && _needLauncher is null) ShowNotice(L.T("notice.launcher", _launcherUpdate.Release.Version), L.T("self.install"), async () => await RunAsync(Work.SelfUpdate, SelfUpdateAsync));
        else if (queued > 0) ShowNotice(L.T("notice.queued", queued), L.T("notice.send"), () => { Navigate("reports"); _reportsPage.SendQueued(); });
        else _notice.IsVisible = false;
    }

    void ShowNotice(string text, string action, Action onClick)
    {
        var row = new DockPanel();
        var icon = new Border { Width = 18, Height = 18, Margin = new Thickness(0, 0, 12, 0), Child = new Avalonia.Controls.Shapes.Path { Data = Geometry.Parse(Skin.IconMessage), Stroke = Skin.B(Skin.Accent), StrokeThickness = 2, Stretch = Stretch.Uniform } };
        DockPanel.SetDock(icon, Dock.Left);
        row.Children.Add(icon);
        var link = new Button { Content = action, FontFamily = Skin.Medium, FontSize = 14, VerticalAlignment = VerticalAlignment.Center };
        link.Classes.Add("link");
        link.Click += (_, _) => onClick();
        DockPanel.SetDock(link, Dock.Right);
        row.Children.Add(link);
        row.Children.Add(new TextBlock { Text = text, FontSize = 14, TextWrapping = TextWrapping.Wrap, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(0, 0, 12, 0) });
        _notice.Child = row;
        _notice.IsVisible = true;
    }

    async Task ChooseGameDirAsync()
    {
        var picked = await StorageProvider.OpenFolderPickerAsync(new FolderPickerOpenOptions { Title = L.T("gameDir"), AllowMultiple = false });
        var dir = picked.FirstOrDefault()?.TryGetLocalPath();
        if (dir is null) return;
        if (!GamePaths.LooksLikeGameDir(dir)) { SetStatus(L.T("status.notGameDir")); Navigate("home"); return; }
        _settings.GameDir = dir;
        _settings.Save();
        OpenGameDir(dir);
        Refresh();
        Navigate("home");
        await RunAsync(Work.Check, () => CheckAsync(full: false, apply: false));
    }

    // ---------------------------------------------------------------- actions

    void OpenSetup(string? installedGame)
    {
        if (_work != Work.None || (installedGame is not null && GameIsRunning())) return;
        _setupPage.Start(installedGame);
        Navigate("setup");
    }

    /// <summary>The player changed the mods in the game and wants ours back: the profile's list and recommended options.</summary>
    async Task ResetProfileAsync()
    {
        if (_paths is null || GameIsRunning() || !await ConfirmAsync(L.T("settings.resetConfirm"))) return;
        string text;
        try
        {
            var r = ProfileWriter.ApplyForGame(_paths, null, null, Screens.ScreenFromWindow(this)?.Bounds.Height, resetMods: true);
            text = r is null ? L.T("settings.resetNothing")
                 : r.Changes.Count == 0 ? L.T("settings.resetSame")
                 : L.T("settings.resetDone", string.Join("; ", r.Changes));
            if (r is { Written: true }) _fileLog?.Info("options.cfg back to the profile: " + string.Join("; ", r.Changes));
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or System.Text.Json.JsonException or InvalidOperationException)
        {
            text = L.T("err.generic", e.Message);
        }
        await new MessageDialog(text, withNo: false).ShowDialog<bool>(this);
    }

    void OnSetupFinished(string dir, bool play)
    {
        if (_paths is null || !Path.GetFullPath(dir).Equals(_paths.GameDir, StringComparison.OrdinalIgnoreCase)) OpenGameDir(dir);
        _pendingLine = null;
        _error = null;
        Refresh();
        Navigate("home");
        if (play) Play();
    }

    async Task OnMainAsync()
    {
        if (_paths is null) { OpenSetup(null); await Task.CompletedTask; return; }
        if (_needLauncher is not null) { await RunAsync(Work.SelfUpdate, SelfUpdateAsync); return; }
        if (_error is not null || _pendingLine is not null)
        {
            await RunAsync(Work.Update, () => CheckAsync(full: false, apply: true));
            if (_error is null && _pendingLine is null && _needLauncher is null) Play();
            return;
        }
        Play();
    }

    async Task RunAsync(Work work, Func<Task> action)
    {
        if (_work != Work.None || _updater is null) return;
        _work = work;
        _cts = new CancellationTokenSource();
        _note = null;
        if (work != Work.Check) _error = null;
        _percent = 0;
        _phase = Phase.Checking;
        _progressLine = "";
        Refresh();
        try
        {
            await action();
            _offline = null;
        }
        catch (OperationCanceledException) { SetStatus(L.T("status.cancelled")); }
        catch (TrustException e) { Fail(L.T("err.trust", e.Message)); }
        catch (ManifestException e) { Fail(L.T("err.trust", e.Message)); }
        catch (UpdateBlockedException e) when (!e.Message.Contains("disk")) { SetStatus(L.T("err.gameRunning")); }
        catch (UpdateBlockedException e) { Fail(L.T("err.disk", e.Message)); }
        catch (HttpRequestException e) { Offline(L.T("err.network", e.Message)); }
        catch (FileNotFoundException e) when (e.Message.StartsWith("not on server")) { Offline(L.T("err.network", e.Message)); }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or InvalidOperationException) { Fail(L.T("err.generic", e.Message)); }
        finally
        {
            _work = Work.None;
            _cancelable = false;
            _cts.Dispose();
            _cts = null;
            _current.Text = "";
            Refresh();
        }
    }

    void Fail(string message)
    {
        _error = message;
        _fileLog?.Error(message);
    }

    /// <summary>No server is not a failure of the game: it still plays, the button only says the check did not happen.</summary>
    void Offline(string message)
    {
        if (_work is Work.Update or Work.Repair) { Fail(message); return; }
        _offline = message;
        _fileLog?.Error(message);
    }

    async Task CheckAsync(bool full, bool apply)
    {
        var u = _updater!;
        var ct = _cts!.Token;
        var state = u.LoadState();
        _latest = await u.CheckAsync(state, ct);
        ShowRelease(_latest.Manifest);
        await CheckLauncherAsync(state.Channel, ct);

        _needLauncher = Version.TryParse(_latest.Manifest.Release.MinLauncher, out var need) && need > BuiltIn.Version ? need : null;
        if (_needLauncher is not null) return;

        var progress = new Progress<Core.Progress>(ShowProgress);
        var plan = await Task.Run(() => u.Scan(state, _latest.Manifest, full, progress, ct), ct);
        if (plan.PlayerModified.Any())
        {
            if (!apply)
            {
                ShowPending(plan, full);
                return;
            }
            var replace = await new ModifiedFilesDialog(plan.PlayerModified.Select(c => c.File.Path).ToList(), preselect: full).ShowDialog<HashSet<string>?>(this);
            if (replace is null) { SetStatus(L.T("status.cancelled")); return; }
            plan = u.Resolve(state, plan, replace);
        }

        if (plan.NothingToDo || (!plan.ToWrite.Any() && plan.Deletes.Count == 0))
        {
            _pendingLine = null;
            if (_work != Work.Check) SetStatus(L.T("status.upToDate"));
            return;
        }
        if (!apply)
        {
            ShowPending(plan, full);
            return;
        }
        if (GameIsRunning()) throw new UpdateBlockedException("the game is running");

        _cancelable = true;
        await u.DownloadAsync(plan, progress, ct);
        _cancelable = false;
        Refresh();
        await Task.Run(() => u.Install(state, plan, progress, CancellationToken.None));
        _pendingLine = null;
        SetStatus(L.T("status.done", _latest.Manifest.Release.Version));
    }

    async Task RollbackAsync()
    {
        if (!await ConfirmAsync(L.T("rollback.confirm"))) return;
        await Task.Run(() => _updater!.RollbackLast());
        var state = _updater!.LoadState();
        _pendingLine = null;
        SetStatus(L.T("status.rolledBack", state.InstalledVersion ?? L.T("none")));
        Navigate("home");
    }

    async Task CheckLauncherAsync(string channel, CancellationToken ct)
    {
        try { _launcherUpdate = await new SelfUpdate(_repo!, _settings, _fileLog!).CheckAsync(channel, ct); }
        catch (Exception e) when (e is HttpRequestException or TrustException or ManifestException)
        {
            _fileLog?.Error("launcher channel: " + e.Message);
            _launcherUpdate = null;
        }
        if (_launcherUpdate is not null) _fileLog?.Info($"launcher {_launcherUpdate.Release.Version} available");
    }

    async Task SelfUpdateAsync()
    {
        if (_launcherUpdate is null) return;
        if (!SelfUpdate.AppDirWritable()) { Fail(L.T("self.readonly")); return; }
        var su = new SelfUpdate(_repo!, _settings, _fileLog!);
        var dir = await su.PrepareAsync(_launcherUpdate, _cts!.Token);
        su.Apply(dir, _launcherUpdate);
        Close();
    }

    void Play()
    {
        if (_updater is null || GameIsRunning()) return;
        var state = _updater.LoadState();
        var exe = new[] { state.InstalledLaunch, "openxcom_hd.exe", "OpenXcomEx.exe" }
            .FirstOrDefault(e => e.Length > 0 && File.Exists(Path.Combine(_updater.Paths.GameDir, e)));
        if (exe is null) { Fail(L.T("err.noLaunch")); Refresh(); return; }
        try
        {
            // the profile of the master mod: fixed options and the mod order, before every start
            try
            {
                var screen = Screens.ScreenFromWindow(this)?.Bounds.Height;
                if (ProfileWriter.ApplyForGame(_updater.Paths, null, null, screen) is { Written: true } r)
                    _fileLog?.Info("options.cfg by the profile: " + string.Join("; ", r.Changes));
            }
            catch (Exception e) when (e is IOException or UnauthorizedAccessException or System.Text.Json.JsonException or InvalidOperationException)
            {
                _fileLog?.Error("profile not applied: " + e.Message);   // the game still starts, as the player left it
            }
            _game = GameProcess.Start(_updater.Paths, exe);
            _fileLog?.Info($"game started: {exe}");
            _game.EnableRaisingEvents = true;
            _game.Exited += (_, _) => Dispatcher.UIThread.Post(() =>
            {
                _fileLog?.Info($"game exited with code {_game?.ExitCode}");
                _game = null;
                Refresh();
            });
        }
        catch (Exception e) when (e is IOException or System.ComponentModel.Win32Exception or InvalidOperationException)
        {
            Fail(L.T("err.generic", e.Message));
        }
        Refresh();
    }

    bool GameIsRunning() => _game is { HasExited: false } || (_paths is not null && GameProcess.IsRunningIn(_paths.GameDir));

    // ----------------------------------------------------------------- display

    void ShowRelease(ReleaseManifest m)
    {
        var text = m.Release.Changelog.TryGetValue(L.Language, out var t) ? t : m.Release.Changelog.Values.FirstOrDefault() ?? "";
        _changelog.Text = text.Trim();
        _whatsNewTitle.Text = L.T("home.whatsNew", m.Release.Version);
        _whatsNew.IsVisible = _changelog.Text.Length > 0;
    }

    void ShowProgress(Core.Progress p)
    {
        // at most ~10 updates a second: 39 000 files would otherwise flood the UI thread
        var now = Environment.TickCount64;
        if (now - _lastProgressTicks < 100 && p.Done < p.Total) return;
        _lastProgressTicks = now;
        _phase = p.Phase;
        _percent = p.Total > 0 ? 100.0 * p.Done / p.Total : 0;
        _progress.Value = _percent * 10;
        _progressLine = p.Phase switch
        {
            Phase.Scanning => L.T("status.scanning", L.Size(p.Done), L.Size(p.Total)),
            Phase.Downloading => L.T("status.downloading", L.Size(p.Done), L.Size(p.Total), L.Size(p.BytesPerSecond)),
            Phase.Installing => L.T("status.installing", L.Size(p.Done), L.Size(p.Total)),
            _ => _progressLine,
        };
        _current.Text = _work == Work.Check ? "" : p.Current ?? "";
        UpdateMain();
    }

    void ShowPending(UpdatePlan plan, bool repair)
    {
        int files = plan.ToWrite.Count() + plan.PlayerModified.Count() + plan.Deletes.Count;
        _pendingLine = plan.Manifest.Release.Id == _updater?.LoadState().InstalledReleaseId || repair
            ? L.T("status.repairNeeded", files, L.Size(plan.DownloadBytes))
            : L.T("main.updateLine", plan.Manifest.Release.Version, L.Size(plan.DownloadBytes));
    }

    void SetStatus(string text) => _note = text;

    void AppendLog(string line)
    {
        var lines = (_log.Text ?? "").Split('\n').TakeLast(200).Append(line);
        _log.Text = string.Join('\n', lines).TrimStart('\n');
    }

    void Refresh()
    {
        var state = _updater?.LoadState();
        _version.Text = _paths is null ? L.T("main.whereIsGame")
                      : state?.InstalledVersion is { } v ? L.T("home.version", v) : L.T("home.notInstalled");
        _installed.Text = state?.InstalledVersion is { } iv ? L.T("settings.installed", iv) : L.T("settings.installedNone");
        _launcherLine.Text = _launcherUpdate is { } lu ? L.T("settings.launcherNew", BuiltIn.VersionText, lu.Release.Version) : L.T("settings.launcherLatest", BuiltIn.VersionText);

        bool idle = _updater is not null && _work == Work.None;
        bool running = _game is { HasExited: false };
        _check.IsEnabled = idle;
        _updateOnly.IsEnabled = idle && !running && _paths is not null;
        _repair.IsEnabled = idle && !running && state?.InstalledReleaseId is not null;
        _rollback.IsEnabled = idle && !running && _updater!.CanRollback;
        _choose.IsEnabled = _work == Work.None;
        _components.IsEnabled = idle && !running && _paths is not null;
        _resetProfile.IsEnabled = idle && !running && _paths is not null;
        _selfUpdate.IsVisible = _launcherUpdate is not null;
        _selfUpdate.IsEnabled = idle;
        if (_launcherUpdate is not null) _selfUpdate.Content = L.T("self.install") + " " + _launcherUpdate.Release.Version;
        CountReports();
        UpdateMain();
    }

    /// <summary>The main button and the line under it: the table in LAUNCHER_UI.md §5.</summary>
    void UpdateMain()
    {
        string caption;
        string look = "primary";
        bool enabled = true;
        _sub.Children.Clear();
        _progress.IsVisible = false;

        if (_paths is null)
        {
            caption = L.T("main.install");
            Sub(L.T("main.installHint"));
            SubLink(L.T("main.haveGame"), async () => await ChooseGameDirAsync());
        }
        else if (_work is Work.Update or Work.Repair or Work.Rollback or Work.SelfUpdate)
        {
            bool scanning = _work is Work.Repair or Work.Update && _phase is Phase.Checking or Phase.Scanning;
            caption = L.T(scanning ? "main.repairing" : "main.updating", (int)_percent);
            look = "busy";
            _progress.IsVisible = true;
            if (_progressLine.Length > 0) Sub(_progressLine);
            if (_cancelable) SubLink(L.T("cancel"), () => _cts?.Cancel());
        }
        else if (_game is { HasExited: false } || (_work == Work.None && GameIsRunning()))
        {
            caption = L.T("main.running");
            enabled = false;
            if (_pendingLine is not null) Sub(L.T("main.runningUpdate"));
        }
        else if (_needLauncher is not null)
        {
            caption = L.T("self.install");
            enabled = _launcherUpdate is not null;
            Sub(L.T("self.required", _needLauncher));
        }
        else if (_error is not null)
        {
            caption = L.T("main.retry");
            look = "warnfill";
            Sub(FirstLine(_error), Skin.WarnText);
            SubLink(L.T("main.details"), () => Navigate("settings"));
        }
        else if (_pendingLine is not null)
        {
            caption = L.T("main.update");
            Sub(_pendingLine);
            SubLink(L.T("main.playAnyway"), Play);
        }
        else
        {
            caption = L.T("play");
            if (_work == Work.Check) Sub(_progressLine.Length > 0 ? L.T("status.checking") + " " + _progressLine : L.T("status.checking"));
            else if (_offline is not null) { Sub(L.T("main.offline")); SubLink(L.T("main.retry"), async () => await RunAsync(Work.Check, () => CheckAsync(full: false, apply: false))); }
            else if (_note is not null) Sub(_note);
        }

        _mainText.Text = caption;
        foreach (var c in new[] { "primary", "busy", "warnfill" }) _main.Classes.Set(c, c == look);
        _main.IsEnabled = enabled && (_work is Work.None or Work.Check || look == "busy");
        _main.IsHitTestVisible = look != "busy";
    }

    static string FirstLine(string s) => s.Split('\n')[0].Trim();

    void Sub(string text, Color? color = null)
    {
        if (_sub.Children.Count > 0) _sub.Children.Add(Dot());
        _sub.Children.Add(new TextBlock { Text = text, FontSize = 13, Foreground = Skin.B(color ?? Skin.Muted), TextWrapping = TextWrapping.Wrap, VerticalAlignment = VerticalAlignment.Center });
    }

    void SubLink(string text, Action onClick)
    {
        if (_sub.Children.Count > 0) _sub.Children.Add(Dot());
        var l = Skin.Link(text, onClick);
        l.Foreground = Skin.B(Skin.Text2);
        _sub.Children.Add(l);
    }

    static TextBlock Dot() => new() { Text = "·", FontSize = 13, Foreground = Skin.B(Skin.Muted), Margin = new Thickness(8, 0), VerticalAlignment = VerticalAlignment.Center };

    // ----------------------------------------------------------------- dialogs

    Task<bool> ConfirmAsync(string text) => new MessageDialog(text, withNo: true).ShowDialog<bool>(this);
}

sealed class MessageDialog : Window
{
    public MessageDialog(string text, bool withNo)
    {
        Title = L.T("title");
        Width = 460; SizeToContent = SizeToContent.Height; CanResize = false;
        WindowStartupLocation = WindowStartupLocation.CenterOwner;
        var yes = Skin.Btn(L.T(withNo ? "yes" : "modified.ok"), "primary");
        yes.Margin = new Thickness(0, 0, 8, 0);
        yes.Click += (_, _) => Close(true);
        var buttons = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right };
        buttons.Children.Add(yes);
        if (withNo)
        {
            var no = Skin.Btn(L.T("no"));
            no.Click += (_, _) => Close(false);
            buttons.Children.Add(no);
        }
        var panel = new StackPanel { Margin = new Thickness(20), Spacing = 16 };
        panel.Children.Add(new TextBlock { Text = text, TextWrapping = TextWrapping.Wrap });
        panel.Children.Add(buttons);
        Content = Skin.Panel(panel, new Thickness(0));
    }
}

/// <summary>Files the player changed: checked ones get replaced, the rest are kept until the next release.</summary>
sealed class ModifiedFilesDialog : Window
{
    public ModifiedFilesDialog(List<string> files, bool preselect)
    {
        Title = L.T("modified.title");
        Width = 640; Height = 460;
        WindowStartupLocation = WindowStartupLocation.CenterOwner;
        var boxes = files.Select(f => new CheckBox { Content = f, IsChecked = preselect }).ToList();
        var list = new StackPanel();
        foreach (var b in boxes) list.Children.Add(b);

        var ok = Skin.Btn(L.T("modified.ok"), "primary");
        ok.Margin = new Thickness(0, 0, 8, 0);
        ok.Click += (_, _) => Close(boxes.Where(b => b.IsChecked == true).Select(b => (string)b.Content!).ToHashSet(StringComparer.OrdinalIgnoreCase));
        var cancel = Skin.Btn(L.T("cancel"));
        cancel.Click += (_, _) => Close(null);
        var buttons = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, Margin = new Thickness(0, 8, 0, 0) };
        buttons.Children.Add(ok);
        buttons.Children.Add(cancel);

        var root = new DockPanel { Margin = new Thickness(16) };
        var text = new TextBlock { Text = L.T("modified.text"), TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 0, 0, 8) };
        DockPanel.SetDock(text, Dock.Top);
        DockPanel.SetDock(buttons, Dock.Bottom);
        root.Children.Add(text);
        root.Children.Add(buttons);
        root.Children.Add(new ScrollViewer { Content = list });
        Content = root;
    }
}
