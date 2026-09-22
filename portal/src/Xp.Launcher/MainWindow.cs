using System.Diagnostics;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Platform.Storage;
using Avalonia.Threading;
using Xp.Launcher.Core;
using Xp.Manifest;

namespace Xp.Launcher;

public sealed class MainWindow : Window
{
    readonly Settings _settings = Settings.Load();
    readonly HttpClient _http = new() { Timeout = Timeout.InfiniteTimeSpan };
    readonly string[] _args;

    readonly TextBox _gameDir = new() { IsReadOnly = true };
    readonly ComboBox _channel = new() { MinWidth = 200 };
    readonly TextBlock _installed = new();
    readonly TextBlock _available = new();
    readonly TextBlock _status = new() { TextWrapping = TextWrapping.Wrap };
    readonly TextBlock _current = new() { FontSize = 11, Opacity = 0.7, TextTrimming = TextTrimming.CharacterEllipsis };
    readonly ProgressBar _progress = new() { Minimum = 0, Maximum = 1000, Height = 8 };
    readonly TextBlock _changelog = new() { TextWrapping = TextWrapping.Wrap };
    readonly TextBlock _log = new() { FontFamily = new FontFamily("Consolas,monospace"), FontSize = 11, TextWrapping = TextWrapping.Wrap };
    readonly Button _check, _update, _repair, _rollback, _play, _cancel, _selfUpdate;

    GamePaths? _paths;
    Updater? _updater;
    FileLog? _fileLog;
    RepoClient? _repo;
    LatestRelease? _latest;
    ReleaseManifest? _launcherUpdate;
    CancellationTokenSource? _cts;
    Process? _game;
    bool _busy;
    long _lastProgressTicks;

    public MainWindow(string[] args)
    {
        _args = args;
        Title = L.T("title") + " " + BuiltIn.VersionText;
        Width = 760; Height = 620; MinWidth = 560; MinHeight = 480;

        _check = MakeButton("checkUpdates", async () => await RunAsync(() => CheckAsync(full: false, apply: false)));
        _update = MakeButton("update", async () => await RunAsync(() => CheckAsync(full: false, apply: true)));
        _repair = MakeButton("repair", async () => await RunAsync(() => CheckAsync(full: true, apply: true)));
        _rollback = MakeButton("rollback", async () => await RunAsync(RollbackAsync));
        _play = MakeButton("play", Play);
        _play.Classes.Add("accent");
        _cancel = MakeButton("cancel", () => _cts?.Cancel());
        _cancel.IsVisible = false;
        _selfUpdate = MakeButton("self.install", async () => await RunAsync(SelfUpdateAsync));
        _selfUpdate.IsVisible = false;
        var choose = MakeButton("choose", async () => await ChooseGameDirAsync());

        foreach (var c in BuiltIn.Defaults.Channels) _channel.Items.Add(new ComboBoxItem { Content = L.T("channel." + c), Tag = c });
        _channel.SelectionChanged += async (_, _) => await OnChannelChangedAsync();

        var dirRow = new DockPanel { LastChildFill = true };
        DockPanel.SetDock(choose, Dock.Right);
        dirRow.Children.Add(choose);
        dirRow.Children.Add(_gameDir);

        var actions = new WrapPanel { Orientation = Orientation.Horizontal };
        foreach (var b in new[] { _play, _update, _check, _repair, _rollback, _selfUpdate, _cancel })
        {
            b.Margin = new Thickness(0, 0, 8, 8);
            actions.Children.Add(b);
        }

        var body = new StackPanel { Spacing = 8, Margin = new Thickness(16) };
        body.Children.Add(Label("gameDir"));
        body.Children.Add(dirRow);
        body.Children.Add(Row(Label("channel"), _channel));
        body.Children.Add(Row(Label("installed"), _installed));
        body.Children.Add(Row(Label("available"), _available));
        body.Children.Add(actions);
        body.Children.Add(_progress);
        body.Children.Add(_status);
        body.Children.Add(_current);
        body.Children.Add(new Expander { Header = L.T("changelog"), Content = new ScrollViewer { MaxHeight = 160, Content = _changelog }, IsExpanded = true });
        body.Children.Add(new Expander { Header = L.T("log"), Content = new ScrollViewer { MaxHeight = 140, Content = _log } });
        Content = new ScrollViewer { Content = body };

        Opened += async (_, _) => await StartupAsync();
        Closing += (_, _) => _cts?.Cancel();
    }

    static Button MakeButton(string key, Action onClick)
    {
        var b = new Button { Content = L.T(key) };
        b.Click += (_, _) => onClick();
        return b;
    }

    static Button MakeButton(string key, Func<Task> onClick)
    {
        var b = new Button { Content = L.T(key) };
        b.Click += async (_, _) => await onClick();
        return b;
    }

    static TextBlock Label(string key) => new() { Text = L.T(key), FontWeight = FontWeight.SemiBold, VerticalAlignment = VerticalAlignment.Center };

    static Control Row(Control label, Control value)
    {
        var g = new Grid { ColumnDefinitions = new ColumnDefinitions("140,*") };
        g.Children.Add(label);
        Grid.SetColumn(value, 1);
        g.Children.Add(value);
        return g;
    }

    // --------------------------------------------------------------- start-up

    async Task StartupAsync()
    {
        var repoUrl = _settings.RepoUrl ?? BuiltIn.Defaults.RepoUrl;
        _repo = new RepoClient(_http, new Uri(repoUrl), BuiltIn.Keys);
        if (_settings.GameDir is { } dir && GamePaths.LooksLikeGameDir(dir)) OpenGameDir(dir);
        else SetStatus(L.T("status.noGameDir"));
        Refresh();

        var reportIdx = Array.IndexOf(_args, "--report");
        if (reportIdx >= 0)
        {
            // F8 from the game (stage 3): for now the report stays on disk, the game waits for us to close
            await MessageAsync(L.T("report.later"));
            Close();
            return;
        }
        if (_updater is not null) await RunAsync(() => CheckAsync(full: false, apply: false));
    }

    void OpenGameDir(string dir)
    {
        _paths = new GamePaths(dir);
        _fileLog = new FileLog(_paths);
        _fileLog.Written += line => Dispatcher.UIThread.Post(() => AppendLog(line));
        _updater = new Updater(_paths, _repo!, _fileLog);
        _gameDir.Text = _paths.GameDir;
        _fileLog.Info($"launcher {BuiltIn.VersionText} started, game dir <game>");
        try
        {
            if (_updater.Recover()) SetStatus(L.T("status.recovered"));
            else SetStatus(L.T("status.idle"));
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException)
        {
            SetStatus(L.T("err.generic", e.Message));
        }
        var state = _updater.LoadState();
        SelectChannel(state.Channel);
    }

    async Task ChooseGameDirAsync()
    {
        var picked = await StorageProvider.OpenFolderPickerAsync(new FolderPickerOpenOptions { Title = L.T("gameDir"), AllowMultiple = false });
        var dir = picked.FirstOrDefault()?.TryGetLocalPath();
        if (dir is null) return;
        if (!GamePaths.LooksLikeGameDir(dir)) { SetStatus(L.T("status.notGameDir")); return; }
        _settings.GameDir = dir;
        _settings.Save();
        OpenGameDir(dir);
        Refresh();
        await RunAsync(() => CheckAsync(full: false, apply: false));
    }

    void SelectChannel(string channel)
    {
        foreach (var item in _channel.Items.OfType<ComboBoxItem>())
            if ((string?)item.Tag == channel) _channel.SelectedItem = item;
    }

    async Task OnChannelChangedAsync()
    {
        if (_updater is null || _channel.SelectedItem is not ComboBoxItem { Tag: string channel }) return;
        var state = _updater.LoadState();
        if (state.Channel == channel) return;
        state.Channel = channel;
        state.Save(_updater.Paths);
        _latest = null;
        await RunAsync(() => CheckAsync(full: false, apply: false));
    }

    // ---------------------------------------------------------------- actions

    async Task RunAsync(Func<Task> work)
    {
        if (_busy || _updater is null) return;
        _busy = true;
        _cts = new CancellationTokenSource();
        Refresh();
        try { await work(); }
        catch (OperationCanceledException) { SetStatus(L.T("status.cancelled")); }
        catch (TrustException e) { Fail(L.T("err.trust", e.Message)); }
        catch (ManifestException e) { Fail(L.T("err.trust", e.Message)); }
        catch (UpdateBlockedException e) { Fail(e.Message.Contains("disk") ? L.T("err.disk", e.Message) : L.T("err.gameRunning")); }
        catch (HttpRequestException e) { Fail(L.T("err.network", e.Message)); }
        catch (FileNotFoundException e) when (e.Message.StartsWith("not on server")) { Fail(L.T("err.network", e.Message)); }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or InvalidOperationException) { Fail(L.T("err.generic", e.Message)); }
        finally
        {
            _busy = false;
            _cts.Dispose();
            _cts = null;
            _current.Text = "";
            Refresh();
        }
    }

    void Fail(string message)
    {
        SetStatus(message);
        _fileLog?.Error(message);
    }

    async Task CheckAsync(bool full, bool apply)
    {
        var u = _updater!;
        var ct = _cts!.Token;
        var state = u.LoadState();
        SetStatus(L.T("status.checking"));
        _latest = await u.CheckAsync(state, ct);
        ShowRelease(_latest.Manifest);
        await CheckLauncherAsync(state.Channel, ct);

        if (Version.TryParse(_latest.Manifest.Release.MinLauncher, out var need) && need > BuiltIn.Version)
        {
            SetStatus(L.T("self.required", need));
            return;
        }

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
            SetStatus(L.T("status.upToDate"));
            return;
        }
        if (!apply)
        {
            ShowPending(plan, full);
            return;
        }
        if (GameIsRunning()) throw new UpdateBlockedException("the game is running");

        _cancel.IsVisible = true;
        await u.DownloadAsync(plan, progress, ct);
        _cancel.IsVisible = false;
        await Task.Run(() => u.Install(state, plan, progress, CancellationToken.None));
        SetStatus(L.T("status.done", _latest.Manifest.Release.Version));
    }

    async Task RollbackAsync()
    {
        if (!await ConfirmAsync(L.T("rollback.confirm"))) return;
        await Task.Run(() => _updater!.RollbackLast());
        var state = _updater!.LoadState();
        SetStatus(L.T("status.rolledBack", state.InstalledVersion ?? L.T("none")));
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
        if (!SelfUpdate.AppDirWritable()) { SetStatus(L.T("self.readonly")); return; }
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
        if (exe is null) { SetStatus(L.T("err.noLaunch")); return; }
        try
        {
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
        _available.Text = $"{m.Release.Version} ({m.Release.Id}, {m.Release.Published.ToLocalTime():yyyy-MM-dd})";
        _changelog.Text = m.Release.Changelog.TryGetValue(L.Language, out var text) ? text
                         : m.Release.Changelog.Values.FirstOrDefault() ?? "";
    }

    void ShowProgress(Core.Progress p)
    {
        // at most ~10 updates a second: 39 000 files would otherwise flood the UI thread
        var now = Environment.TickCount64;
        if (now - _lastProgressTicks < 100 && p.Done < p.Total) return;
        _lastProgressTicks = now;
        _progress.Value = p.Total > 0 ? 1000.0 * p.Done / p.Total : 0;
        _status.Text = p.Phase switch
        {
            Phase.Scanning => L.T("status.scanning", L.Size(p.Done), L.Size(p.Total)),
            Phase.Downloading => L.T("status.downloading", L.Size(p.Done), L.Size(p.Total), L.Size(p.BytesPerSecond)),
            Phase.Installing => L.T("status.installing", L.Size(p.Done), L.Size(p.Total)),
            _ => _status.Text,
        };
        _current.Text = p.Current ?? "";
    }

    void ShowPending(UpdatePlan plan, bool repair)
    {
        int files = plan.ToWrite.Count() + plan.PlayerModified.Count() + plan.Deletes.Count;
        SetStatus(plan.Manifest.Release.Id == _updater?.LoadState().InstalledReleaseId || repair
            ? L.T("status.repairNeeded", files, L.Size(plan.DownloadBytes))
            : L.T("status.updateAvailable", plan.Manifest.Release.Version, files, L.Size(plan.DownloadBytes)));
    }

    void SetStatus(string text) => _status.Text = text;

    void AppendLog(string line)
    {
        var lines = (_log.Text ?? "").Split('\n').TakeLast(200).Append(line);
        _log.Text = string.Join('\n', lines).TrimStart('\n');
    }

    void Refresh()
    {
        var state = _updater?.LoadState();
        _installed.Text = state?.InstalledVersion is { } v ? $"{v} ({state.InstalledReleaseId})" : L.T("none");
        bool ready = _updater is not null && !_busy;
        bool running = _game is { HasExited: false };
        _check.IsEnabled = ready;
        _update.IsEnabled = ready && !running;
        _repair.IsEnabled = ready && !running && state?.InstalledReleaseId is not null;
        _rollback.IsEnabled = ready && !running && _updater!.CanRollback;
        _play.IsEnabled = ready && !running;
        _channel.IsEnabled = ready;
        _selfUpdate.IsVisible = _launcherUpdate is not null;
        _selfUpdate.IsEnabled = ready;
        if (_launcherUpdate is not null) _selfUpdate.Content = L.T("self.install") + " " + _launcherUpdate.Release.Version;
        if (!_busy) { _cancel.IsVisible = false; _progress.Value = 0; }
    }

    // ----------------------------------------------------------------- dialogs

    Task MessageAsync(string text) => new MessageDialog(text, withNo: false).ShowDialog<bool>(this);
    Task<bool> ConfirmAsync(string text) => new MessageDialog(text, withNo: true).ShowDialog<bool>(this);
}

sealed class MessageDialog : Window
{
    public MessageDialog(string text, bool withNo)
    {
        Title = L.T("title");
        Width = 460; SizeToContent = SizeToContent.Height; CanResize = false;
        WindowStartupLocation = WindowStartupLocation.CenterOwner;
        var yes = new Button { Content = L.T(withNo ? "yes" : "modified.ok"), Margin = new Thickness(0, 0, 8, 0) };
        yes.Click += (_, _) => Close(true);
        var buttons = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right };
        buttons.Children.Add(yes);
        if (withNo)
        {
            var no = new Button { Content = L.T("no") };
            no.Click += (_, _) => Close(false);
            buttons.Children.Add(no);
        }
        var panel = new StackPanel { Margin = new Thickness(16), Spacing = 16 };
        panel.Children.Add(new TextBlock { Text = text, TextWrapping = TextWrapping.Wrap });
        panel.Children.Add(buttons);
        Content = panel;
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

        var ok = new Button { Content = L.T("modified.ok"), Margin = new Thickness(0, 0, 8, 0) };
        ok.Click += (_, _) => Close(boxes.Where(b => b.IsChecked == true).Select(b => (string)b.Content!).ToHashSet(StringComparer.OrdinalIgnoreCase));
        var cancel = new Button { Content = L.T("cancel") };
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
