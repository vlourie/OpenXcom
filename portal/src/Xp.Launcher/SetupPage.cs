using Avalonia;
using Avalonia.Controls;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Platform.Storage;
using Avalonia.Threading;
using Xp.Launcher.Core;
using Xp.Manifest;

namespace Xp.Launcher;

/// <summary>
/// The install wizard (docs/portal/EDITIONS.md §12.1): language and folder, the original UFO, the
/// components, the install, and "Play". Also opened from Settings on an installed game to change
/// the components: then it starts at the list.
/// </summary>
public sealed class SetupPage : UserControl
{
    enum Step { Where, Ufo, Parts, Install, Done }
    const int Steps = 5;

    readonly Settings _settings;
    readonly Func<RepoClient?> _repo;

    /// <summary>The wizard is over: the game folder, and whether the player pressed "Play".</summary>
    public event Action<string, bool>? Finished;
    /// <summary>"The game is already installed": the main window's own folder picker.</summary>
    public event Action? PickExisting;

    readonly TextBlock _stepLine = new() { FontSize = 13, Foreground = Skin.B(Skin.Muted) };
    readonly TextBlock _title = Skin.H1("");
    readonly ContentControl _body = new();
    readonly TextBlock _error = new() { FontSize = 13, Foreground = Skin.B(Skin.WarnText), TextWrapping = TextWrapping.Wrap, IsVisible = false };
    readonly Button _back = Skin.Btn(L.T("setup.back"));
    readonly Button _next = Skin.Btn(L.T("setup.next"), "primary", 44);
    readonly Button _toLauncher = Skin.Btn(L.T("setup.toLauncher"));
    readonly DispatcherTimer _ufoTimer = new() { Interval = TimeSpan.FromSeconds(3) };

    Step _step;
    Step _first;
    string _dir;
    string _lang;
    string? _ufoFrom;            // where the UFO files get copied from; null - already in the game folder
    List<UfoFound> _ufoFound = [];
    GamePaths? _paths;
    Updater? _updater;
    ReleaseManifest? _manifest;
    ModProfile? _profile;
    HashSet<string> _picked = [];
    CancellationTokenSource? _cts;
    string _doneText = "";

    public SetupPage(Settings settings, Func<RepoClient?> repo)
    {
        _settings = settings;
        _repo = repo;
        _lang = settings.Language ?? L.Language;
        _dir = settings.GameDir ?? DefaultDir();

        _back.Click += (_, _) => Go(_step == Step.Ufo ? Step.Where : Step.Ufo);
        _next.Click += async (_, _) => await NextAsync();
        _next.MinWidth = 160;
        _toLauncher.Click += (_, _) => Finished?.Invoke(_dir, false);
        _ufoTimer.Tick += async (_, _) => { if (_step == Step.Ufo && _ufoFrom is null) await SearchUfoAsync(quiet: true); };

        var buttons = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 10, HorizontalAlignment = HorizontalAlignment.Right };
        buttons.Children.Add(_back);
        buttons.Children.Add(_toLauncher);
        buttons.Children.Add(_next);
        // the buttons are as tall as each other, and their text stands in the middle
        foreach (var b in new[] { _back, _toLauncher, _next }) { b.VerticalAlignment = VerticalAlignment.Stretch; b.VerticalContentAlignment = VerticalAlignment.Center; }

        var head = new StackPanel { Spacing = 4 };
        head.Children.Add(_stepLine);
        head.Children.Add(_title);

        head.Margin = new Thickness(0, 0, 0, 18);
        _error.Margin = new Thickness(0, 12, 0, 0);
        buttons.Margin = new Thickness(0, 12, 0, 0);
        // the card is as tall as its step and the buttons stand right under it;
        // a long list of components stops at the window and scrolls (a star row in a top-aligned grid)
        var card = new Grid { RowDefinitions = new RowDefinitions("*,Auto,Auto"), VerticalAlignment = VerticalAlignment.Top };
        var panel = Skin.Panel(new ScrollViewer { Content = _body }, new Thickness(20));
        Grid.SetRow(_error, 1);
        Grid.SetRow(buttons, 2);
        card.Children.Add(panel);
        card.Children.Add(_error);
        card.Children.Add(buttons);

        var dock = new DockPanel();
        DockPanel.SetDock(head, Dock.Top);
        dock.Children.Add(head);
        dock.Children.Add(card);
        // one column up to 820 wide, pinned to the left; a narrow window squeezes it
        var page = new Grid { ColumnDefinitions = new ColumnDefinitions("*,Auto"), Margin = new Thickness(28, 24, 28, 28) };
        page.ColumnDefinitions[0].MaxWidth = 820;
        page.Children.Add(dock);

        // each step has its own picture behind it (Assets/setup_<step>.jpg, tools/hdart/gen_promo.py);
        // the scene is in its right part, and the shade keeps the left, under the card, dark and calm
        var shade = new Border
        {
            Background = new LinearGradientBrush
            {
                StartPoint = new RelativePoint(0, 0, RelativeUnit.Relative),
                EndPoint = new RelativePoint(1, 0, RelativeUnit.Relative),
                GradientStops =
                {
                    new GradientStop(Skin.Bg, 0),
                    new GradientStop(Color.FromArgb(0xD0, Skin.Bg.R, Skin.Bg.G, Skin.Bg.B), 0.4),
                    new GradientStop(Color.FromArgb(0x30, Skin.Bg.R, Skin.Bg.G, Skin.Bg.B), 0.75),
                    new GradientStop(Color.FromArgb(0x10, Skin.Bg.R, Skin.Bg.G, Skin.Bg.B), 1),
                },
            },
        };
        var root = new Grid { Background = new SolidColorBrush(Skin.Bg), ClipToBounds = true };
        root.Children.Add(_backdrop);
        root.Children.Add(shade);
        root.Children.Add(page);
        Content = root;
    }

    /// <summary>A fresh install starts at the folder; an installed game (Settings) at the list of components.</summary>
    public void Start(string? installedGame)
    {
        _cts?.Cancel();
        _manifest = null;
        _profile = null;
        _ufoFrom = null;
        if (installedGame is not null)
        {
            _dir = installedGame;
            if (!Open()) return;
            _first = Step.Parts;
        }
        else _first = Step.Where;
        Go(_first);
    }

    static string DefaultDir()
    {
        var root = Path.GetPathRoot(Environment.ProcessPath ?? AppContext.BaseDirectory) ?? "C:\\";
        return Path.Combine(root, "Games", "X-Piratez HD");
    }

    // ------------------------------------------------------------------ steps

    readonly Image _backdrop = new() { Stretch = Stretch.UniformToFill, HorizontalAlignment = HorizontalAlignment.Right };
    readonly Dictionary<Step, Avalonia.Media.Imaging.Bitmap?> _art = new();

    Avalonia.Media.Imaging.Bitmap? Art(Step step)
    {
        if (_art.TryGetValue(step, out var b)) return b;
        try
        {
            using var s = Avalonia.Platform.AssetLoader.Open(new Uri($"avares://XPiratezLauncher/Assets/setup_{step.ToString().ToLowerInvariant()}.jpg"));
            b = new Avalonia.Media.Imaging.Bitmap(s);
        }
        catch (Exception) { b = null; }   // a build without the picture keeps the plain background
        return _art[step] = b;
    }

    void Go(Step step)
    {
        _step = step;
        _backdrop.Source = Art(step);
        _error.IsVisible = false;
        _ufoTimer.IsEnabled = step == Step.Ufo;
        _stepLine.Text = L.T("setup.step", (int)step + 1, Steps);
        _back.IsVisible = step is Step.Ufo or Step.Parts && step != _first;
        _next.IsVisible = step != Step.Install;
        _toLauncher.IsVisible = step == Step.Done;
        _next.IsEnabled = true;
        _next.Content = L.T(step switch { Step.Parts => "setup.install", Step.Done => "setup.play", _ => "setup.next" });
        switch (step)
        {
            case Step.Where: _title.Text = L.T("setup.title"); _body.Content = WhereView(); break;
            case Step.Ufo: _title.Text = L.T("setup.ufo"); _body.Content = UfoView(); _ = SearchUfoAsync(quiet: false); break;
            case Step.Parts: _title.Text = L.T("setup.parts"); _ = LoadPartsAsync(); break;
            case Step.Install: _title.Text = L.T("setup.installing"); _ = InstallAsync(); break;
            case Step.Done: _title.Text = L.T("setup.done"); _body.Content = DoneView(); break;
        }
    }

    async Task NextAsync()
    {
        switch (_step)
        {
            case Step.Where:
                if (Open()) Go(Step.Ufo);
                break;
            case Step.Ufo: Go(Step.Parts); break;
            case Step.Parts: Go(Step.Install); break;
            case Step.Done: Finished?.Invoke(_dir, true); break;
        }
        await Task.CompletedTask;
    }

    void Fail(string text)
    {
        _error.Text = text;
        _error.IsVisible = true;
    }

    /// <summary>Takes the chosen folder: empty, missing or a game already. Anything else is somebody's files.</summary>
    bool Open()
    {
        try
        {
            var dir = Path.GetFullPath(_dir.Trim());
            if (Directory.Exists(dir) && Directory.EnumerateFileSystemEntries(dir).Any() && !GamePaths.LooksLikeGameDir(dir)
                && !File.Exists(Path.Combine(dir, "launcher", "state.json")))
            {
                Fail(L.T("setup.dirNotEmpty"));
                return false;
            }
            Directory.CreateDirectory(dir);
            _dir = dir;
            _paths = new GamePaths(dir);
            var log = new FileLog(_paths);
            _updater = new Updater(_paths, _repo() ?? throw new InvalidOperationException("no repository"), log);
            _updater.Recover();
            return true;
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or ArgumentException or NotSupportedException or InvalidOperationException)
        {
            Fail(L.T("setup.dirBad", e.Message));
            return false;
        }
    }

    Control WhereView()
    {
        var s = new StackPanel { Spacing = 10 };
        s.Children.Add(Skin.H2(L.T("setup.lang")));
        var langs = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 18 };
        foreach (var (code, name) in new[] { ("ru", "Русский"), ("en", "English") })
        {
            var r = new RadioButton { Content = name, GroupName = "setup-lang", IsChecked = _lang == code, FontSize = 14 };
            r.IsCheckedChanged += (_, _) => { if (r.IsChecked == true) { _lang = code; _manifest = null; } };
            langs.Children.Add(r);
        }
        s.Children.Add(langs);
        s.Children.Add(Skin.Note(L.T("setup.langHint")));
        if (_lang != L.Language) s.Children.Add(Skin.Note(L.T("setup.langRestart")));

        var dirBox = new TextBox { Text = _dir, FontSize = 13 };
        dirBox.TextChanged += (_, _) => _dir = dirBox.Text ?? "";
        var change = Skin.Btn(L.T("settings.change"));
        change.Margin = new Thickness(8, 0, 0, 0);
        change.Click += async (_, _) => { if (await PickFolderAsync(L.T("setup.dir")) is { } d) dirBox.Text = d; };
        var row = new DockPanel();
        DockPanel.SetDock(change, Dock.Right);
        row.Children.Add(change);
        row.Children.Add(dirBox);
        var dirHead = Skin.H2(L.T("setup.dir"));
        dirHead.Margin = new Thickness(0, 14, 0, 0);
        s.Children.Add(dirHead);
        s.Children.Add(row);
        s.Children.Add(Skin.Note(L.T("setup.dirHint")));
        var have = Skin.Link(L.T("main.haveGame"), () => PickExisting?.Invoke());
        have.Margin = new Thickness(0, 10, 0, 0);
        s.Children.Add(have);
        return s;
    }

    // -------------------------------------------------------------------- UFO

    readonly StackPanel _ufoList = new() { Spacing = 8 };

    Control UfoView()
    {
        var s = new StackPanel { Spacing = 12 };
        s.Children.Add(Skin.Note(L.T("setup.ufoHint"), 14, Skin.Text2));
        s.Children.Add(_ufoList);
        return s;
    }

    async Task SearchUfoAsync(bool quiet)
    {
        var inGame = Path.Combine(_dir, "UFO");
        if (UfoData.Check(inGame).Ok) { _ufoFrom = null; ShowUfo(inPlace: true); return; }
        if (!quiet) { _next.IsEnabled = false; _ufoList.Children.Clear(); _ufoList.Children.Add(Skin.Note(L.T("setup.ufoSearching"))); }
        // besides Steam and GOG: the folder of a game this launcher knew before (an older Pirates install)
        var extra = _settings.GameDir is { } old && !old.Equals(_dir, StringComparison.OrdinalIgnoreCase)
            ? new[] { (Path.Combine(old, "UFO"), "OpenXcom") } : [];
        var found = await Task.Run(() => UfoData.Probe(extra.Concat(UfoData.Roots(null))));
        if (_step != Step.Ufo) return;
        if (quiet && found.Select(f => f.Dir).SequenceEqual(_ufoFound.Select(f => f.Dir))) return;
        _ufoFound = found;
        if (_ufoFrom is null || !found.Any(f => f.Dir == _ufoFrom)) _ufoFrom = found.FirstOrDefault()?.Dir;
        ShowUfo(inPlace: false);
    }

    void ShowUfo(bool inPlace)
    {
        _ufoList.Children.Clear();
        if (inPlace)
        {
            _ufoList.Children.Add(Skin.Note(L.T("setup.ufoInPlace"), 14, Skin.Accent));
            _next.IsEnabled = true;
            return;
        }
        if (_ufoFound.Count > 0)
        {
            _ufoList.Children.Add(Skin.Note(L.T("setup.ufoFound"), 14, Skin.Text));
            foreach (var u in _ufoFound)
            {
                var r = new RadioButton { Content = $"{u.Source}:  {u.Dir}", GroupName = "setup-ufo", IsChecked = u.Dir == _ufoFrom, FontSize = 13 };
                r.IsCheckedChanged += (_, _) => { if (r.IsChecked == true) _ufoFrom = u.Dir; };
                _ufoList.Children.Add(r);
            }
        }
        else _ufoList.Children.Add(Skin.Note(L.T("setup.ufoNone"), 14, Skin.Text2));

        var buttons = new WrapPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 8, 0, 0) };
        if (_ufoFound.Count == 0)
        {
            var steam = Skin.Btn(L.T("setup.ufoSteam"), "primary");
            steam.Click += (_, _) => OpenSteam();
            var gog = Skin.Btn(L.T("setup.ufoGog"));
            gog.Click += (_, _) => ReportWindow.OpenUrl(UfoData.GogUrl);
            steam.Margin = gog.Margin = new Thickness(0, 0, 10, 6);
            buttons.Children.Add(steam);
            buttons.Children.Add(gog);
        }
        var pick = Skin.Btn(L.T("setup.ufoPick"));
        pick.Margin = new Thickness(0, 0, 10, 6);
        pick.Click += async (_, _) => await PickUfoAsync();
        buttons.Children.Add(pick);
        _ufoList.Children.Add(buttons);
        _next.IsEnabled = _ufoFrom is not null;
    }

    /// <summary>The Steam client's store page when Steam is installed, the web page otherwise.</summary>
    static void OpenSteam() =>
        ReportWindow.OpenUrl(UfoData.SteamLibraries().Count > 0 ? UfoData.SteamClientUrl : UfoData.SteamStoreUrl);

    async Task PickUfoAsync()
    {
        if (await PickFolderAsync(L.T("setup.ufo")) is not { } dir) return;
        var found = UfoData.Probe([(dir, L.T("setup.ufoPick").TrimEnd('…'))]);
        if (found.Count == 0)
        {
            Fail(L.T("setup.ufoMissing", string.Join(", ", UfoData.Check(dir).Missing.Take(6))));
            return;
        }
        _error.IsVisible = false;
        _ufoFound.RemoveAll(f => f.Dir == found[0].Dir);
        _ufoFound.Insert(0, found[0]);
        _ufoFrom = found[0].Dir;
        ShowUfo(inPlace: false);
    }

    async Task<string?> PickFolderAsync(string title)
    {
        if (TopLevel.GetTopLevel(this)?.StorageProvider is not { } sp) return null;
        var picked = await sp.OpenFolderPickerAsync(new FolderPickerOpenOptions { Title = title, AllowMultiple = false });
        return picked.FirstOrDefault()?.TryGetLocalPath();
    }

    // ------------------------------------------------------------- components

    async Task LoadPartsAsync()
    {
        _next.IsEnabled = false;
        if (_manifest is null)
        {
            _body.Content = Skin.Note(L.T("setup.loading"), 14);
            try
            {
                var state = _updater!.LoadState();
                var latest = await _updater.CheckAsync(state, CancellationToken.None);
                _manifest = latest.Manifest;
                var profiles = await _updater.ProfilesAsync(_manifest, CancellationToken.None);
                _profile = Setup.Master(_manifest, (IEnumerable<string>?)state.Components ?? Setup.Defaults(_manifest, null, _lang)) is { } master
                    ? profiles?.For(master) : null;
                _picked = state.Components is { } mine ? Setup.Normalize(_manifest, mine) : Setup.Defaults(_manifest, _profile, _lang);
            }
            catch (Exception e) when (e is HttpRequestException or TrustException or ManifestException or IOException or FileNotFoundException or System.Text.Json.JsonException)
            {
                var s = new StackPanel { Spacing = 12 };
                s.Children.Add(Skin.Note(L.T("err.network", e.Message), 14, Skin.WarnText));
                var retry = Skin.Btn(L.T("setup.retry"), "primary");
                retry.HorizontalAlignment = HorizontalAlignment.Left;
                retry.Click += (_, _) => Go(Step.Parts);
                s.Children.Add(retry);
                _body.Content = s;
                return;
            }
        }
        if (_step != Step.Parts) return;
        ShowParts();
    }

    void ShowParts()
    {
        var m = _manifest!;
        var s = new StackPanel { Spacing = 6 };
        s.Children.Add(Skin.Note(L.T("setup.partsHint")));
        var rows = Setup.Rows(m, _picked);
        foreach (var r in rows) s.Children.Add(PartRow(r));
        var total = rows.Where(r => r.Checked).Sum(r => r.Component.Size);
        var sum = Skin.Note(L.T("setup.total", L.Size(total)), 14, Skin.Text);
        sum.Margin = new Thickness(0, 10, 0, 0);
        s.Children.Add(sum);
        AddOwnMods(s, m);
        _body.Content = s;
        _next.Content = L.T("setup.install");
        _next.IsEnabled = true;
    }

    /// <summary>The player's own mods: shown, never touched - no box to tick, the game's Mods menu switches them.</summary>
    void AddOwnMods(StackPanel s, ReleaseManifest m)
    {
        List<OwnMod> own;
        try { own = Setup.OwnMods(_dir, m, Setup.Master(m, _picked)); }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { return; }
        if (own.Count == 0) return;
        var head = Skin.Note(L.T("setup.own"), 14, Skin.Text);
        head.Margin = new Thickness(0, 18, 0, 0);
        s.Children.Add(head);
        s.Children.Add(Skin.Note(L.T("setup.ownHint")));
        foreach (var o in own)
        {
            var text = new StackPanel { Spacing = 1, Margin = new Thickness(28, 2, 0, 0) };
            bool bad = o.OtherMaster is not null || o.WrongEngine is not null;
            var name = o.Name + (o.Version.Length > 0 ? "  " + o.Version : "");
            text.Children.Add(new TextBlock { Text = name, FontSize = 14, FontFamily = Skin.Medium, Foreground = Skin.B(bad ? Skin.Dim : Skin.Text) });
            var why = o.OtherMaster is { } om ? L.T("setup.ownOtherMaster", om)
                    : o.WrongEngine is { } e ? L.T("setup.wrongEngine", e)
                    : L.T("setup.ownUntested");
            var state = o.IsMaster ? L.T("setup.kind.master") : L.T(o.Active ? "setup.ownOn" : "setup.ownOff");
            var line = string.Join("  ·  ", new[] { state, "user/mods/" + o.Folder, why });
            text.Children.Add(new TextBlock { Text = line, FontSize = 12, TextWrapping = TextWrapping.Wrap, Foreground = Skin.B(Skin.WarnText) });
            s.Children.Add(text);
        }
    }

    Control PartRow(SetupRow r)
    {
        var c = r.Component;
        var box = new CheckBox { IsChecked = r.Checked, IsEnabled = !r.Locked && !r.Blocked, VerticalAlignment = VerticalAlignment.Top };
        var text = new StackPanel { Spacing = 1 };
        // the manifest names the engine by its id: the player reads "OXCE-HD engine", not "engine"
        var title = c.Kind == ComponentKind.Engine ? L.T("setup.engineName") : Setup.Title(c);
        var name = title + (c.Version.Length > 0 ? "  " + c.Version : "");
        text.Children.Add(new TextBlock { Text = name, FontSize = 14, FontFamily = Skin.Medium, Foreground = Skin.B(r.Blocked ? Skin.Dim : Skin.Text) });
        var kind = L.T("setup.kind." + c.Kind);
        var why = r.Locked ? L.T("setup.always")
                : r.Needs is { } n ? L.T("setup.needs", n)
                : r.WrongEngine is { } e ? L.T("setup.wrongEngine", e) : null;
        var line = string.Join("  ·  ", new[] { kind, c.Size > 0 ? L.Size(c.Size) : null, why }.Where(x => !string.IsNullOrEmpty(x)));
        text.Children.Add(new TextBlock { Text = line, FontSize = 12, Foreground = Skin.B(r.Blocked ? Skin.WarnText : Skin.Muted) });
        box.Content = text;
        box.IsCheckedChanged += async (_, _) =>
        {
            bool on = box.IsChecked == true;
            if (on == _picked.Contains(c.Id)) return;
            if (on && c.Adult && !await new MessageDialog(L.T("setup.adult", Setup.Title(c)), withNo: true).ShowDialog<bool>((Window)TopLevel.GetTopLevel(this)!))
            {
                box.IsChecked = false;
                return;
            }
            if (on) _picked.Add(c.Id); else _picked.Remove(c.Id);
            _picked = Setup.Normalize(_manifest!, _picked);
            ShowParts();
        };
        return box;
    }

    // ---------------------------------------------------------------- install

    readonly ProgressBar _bar = new() { Minimum = 0, Maximum = 1000, Height = 6 };
    readonly TextBlock _barLine = new() { FontSize = 13, Foreground = Skin.B(Skin.Text2), TextWrapping = TextWrapping.Wrap };
    readonly TextBlock _barFile = new() { FontSize = 11, Foreground = Skin.B(Skin.Dim), TextTrimming = TextTrimming.CharacterEllipsis };
    long _lastTick;

    async Task InstallAsync()
    {
        var s = new StackPanel { Spacing = 10 };
        s.Children.Add(_bar);
        s.Children.Add(_barLine);
        s.Children.Add(_barFile);
        _body.Content = s;
        _bar.Value = 0;
        _barLine.Text = _barFile.Text = "";
        _cts = new CancellationTokenSource();
        var ct = _cts.Token;
        var u = _updater!;
        try
        {
            if (_ufoFrom is not null)
            {
                var from = _ufoFrom;
                var copy = new Progress<(int Done, int Total)>(p =>
                {
                    _bar.Value = p.Total > 0 ? 1000.0 * p.Done / p.Total : 0;
                    _barLine.Text = L.T("setup.copyUfo", p.Done, p.Total);
                });
                var check = await Task.Run(() => UfoData.Copy(from, Path.Combine(_dir, "UFO"), copy), ct);
                if (!check.Ok) throw new IOException(L.T("setup.ufoMissing", string.Join(", ", check.Missing.Take(6))));
                _ufoFrom = null;
            }

            var state = u.LoadState();
            var before = new HashSet<string>(state.Components ?? []);
            state.Components = [.. Setup.Normalize(_manifest!, _picked).Order(StringComparer.Ordinal)];
            // what the player has just ticked is switched on in the game too, even in a mods list they set themselves
            var ticked = _manifest!.Components.Where(c => c.Mod.Length > 0 && state.Components.Contains(c.Id) && !before.Contains(c.Id))
                                              .Select(c => c.Mod).ToList();
            state.Save(u.Paths);
            var progress = new Progress<Core.Progress>(ShowProgress);
            var plan = await Task.Run(() => u.Scan(state, _manifest!, full: false, progress, ct), ct);
            // an installed game the player edited: the wizard keeps their files, Settings can replace them
            if (plan.PlayerModified.Any()) plan = u.Resolve(state, plan, new HashSet<string>());
            if (plan.ToWrite.Any() || plan.Deletes.Count > 0)
            {
                await u.DownloadAsync(plan, progress, ct);
                await Task.Run(() => u.Install(state, plan, progress, CancellationToken.None), CancellationToken.None);
            }

            var master = Setup.Master(_manifest!, _picked);
            var r = ProfileWriter.ApplyForGame(u.Paths, master, Setup.GameLanguage(_lang), ScreenHeight(), switchOn: ticked);
            // without this line a game with every mod off is a guess: was the profile written, and where
            new FileLog(u.Paths).Info(r is null
                ? $"setup: no profile applied (master '{master}', {ProfileSet.FileName} {(File.Exists(Path.Combine(u.Paths.GameDir, ProfileSet.FileName)) ? "found" : "missing")}, mods {string.Join(",", ProfileWriter.ScanMods(u.Paths.GameDir).Select(m => m.Id + (m.IsMaster ? "*" : "")))})"
                : $"setup: options.cfg by the profile in {u.Paths.GameDir}: {string.Join("; ", r.Changes)}");
            _doneText = L.T("setup.doneText", _manifest!.Release.Version)
                        + (r is { Changes.Count: > 0 } ? "\n\n" + L.T("setup.doneChanges", ProfileText.Lines(r.Items)) : "");
            _settings.GameDir = _dir;
            _settings.Language = _lang;
            try { _settings.Save(); } catch (IOException) { }
            Go(Step.Done);
        }
        catch (Exception e) when (e is OperationCanceledException or HttpRequestException or TrustException or ManifestException
                                      or UpdateBlockedException or IOException or UnauthorizedAccessException or InvalidOperationException)
        {
            Fail(L.T("setup.failed", e.Message));
            var retry = Skin.Btn(L.T("setup.retry"), "primary");
            retry.Click += (_, _) => Go(Step.Install);
            var back = Skin.Btn(L.T("setup.back"));
            back.Click += (_, _) => Go(Step.Parts);
            var row = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 10 };
            row.Children.Add(retry);
            row.Children.Add(back);
            s.Children.Add(row);
        }
        finally
        {
            _cts.Dispose();
            _cts = null;
        }
    }

    void ShowProgress(Core.Progress p)
    {
        var now = Environment.TickCount64;
        if (now - _lastTick < 100 && p.Done < p.Total) return;
        _lastTick = now;
        _bar.Value = p.Total > 0 ? 1000.0 * p.Done / p.Total : 0;
        _barLine.Text = p.Phase switch
        {
            Phase.Scanning => L.T("status.scanning", L.Size(p.Done), L.Size(p.Total)),
            Phase.Downloading => L.T("status.downloading", L.Size(p.Done), L.Size(p.Total), L.Size(p.BytesPerSecond)),
            Phase.Installing => L.T("status.installing", L.Size(p.Done), L.Size(p.Total)),
            _ => _barLine.Text,
        };
        _barFile.Text = p.Current ?? "";
    }

    /// <summary>The height of the screen the window is on, in real pixels: the HD scale follows it.</summary>
    int? ScreenHeight() =>
        TopLevel.GetTopLevel(this) is Window w && w.Screens.ScreenFromWindow(w) is { } sc ? sc.Bounds.Height : null;

    Control DoneView()
    {
        // "Play" and "To the launcher" stand together in the button row under the card, not in the text
        return Skin.Note(_doneText, 15, Skin.Text);
    }
}
