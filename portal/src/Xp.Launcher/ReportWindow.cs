using System.Diagnostics;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Documents;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Media.Imaging;
using Xp.Launcher.Core;

namespace Xp.Launcher;

/// <summary>
/// The F8 form. Opened by the game with --report &lt;folder&gt; (the game stays paused until this
/// window closes) or from the launcher's report list. Nothing leaves the machine before "Send".
/// </summary>
public sealed class ReportWindow : Window
{
    readonly Report _report;
    readonly Settings _settings;
    readonly WrapPanel _kind = new() { Orientation = Orientation.Horizontal };
    readonly TextBox _title = new() { MaxLength = 140, FontSize = 14 };
    readonly TextBox _description = Multi(96);
    readonly TextBox _steps = Multi(64);
    readonly TextBox _expected = Multi(52);
    readonly TextBox _actual = Multi(52);
    readonly CheckBox _shot = new() { FontSize = 13 };
    readonly CheckBox _log = new() { FontSize = 13 };
    readonly CheckBox _save = new() { FontSize = 13 };
    readonly ComboBox _saves = new() { HorizontalAlignment = HorizontalAlignment.Stretch, FontSize = 13, Margin = new Thickness(28, 0, 0, 0) };
    readonly TextBlock _status = new() { TextWrapping = TextWrapping.Wrap, FontSize = 13, VerticalAlignment = VerticalAlignment.Center };
    readonly Button _send, _draft, _cancel;
    string _kindValue = ReportKinds.Bug;
    bool _busy;
    bool _closingHandled;

    public ReportWindow(Report report, Settings settings)
    {
        _report = report;
        _settings = settings;
        Title = L.T("report.title");
        Width = 960; Height = 640; MinWidth = 800; MinHeight = 560;
        WindowStartupLocation = WindowStartupLocation.CenterScreen;

        foreach (var k in ReportKinds.All)
        {
            var chip = Skin.Btn(L.T("report.kind." + k), "chip", 32);
            chip.Tag = k;
            chip.Margin = new Thickness(0, 0, 6, 6);
            chip.Click += (_, _) => SelectKind(k);
            _kind.Children.Add(chip);
        }
        _send = Button("report.send", async () => await SendAsync());
        _send.Classes.Add("primary");
        _send.FontFamily = Skin.Medium;
        _send.Padding = new Thickness(22, 0);
        _draft = Button("report.draft", SaveDraft);
        _cancel = Button("report.cancel", async () => await CancelAsync());
        _cancel.Classes.Add("nav");
        _cancel.BorderThickness = new Thickness(0);

        var d = report.Draft;
        if (d.Status == ReportStatus.Sent) { ShowSent(); }
        else
        {
            BuildForm();
            Load(d);
            // the ticket already exists (only files were left): its text can no longer change
            bool created = d.TicketNumber is not null;
            foreach (var c in new Control[] { _kind, _title, _description, _steps, _expected, _actual }) c.IsEnabled = !created;
            if (d.Status == ReportStatus.Queued) _status.Text = WithReason(L.T("report.queuedBefore"));
            else if (d.LastError is { } err) _status.Text = WithReason(ErrorText(err));
        }

        Opened += (_, _) => { Activate(); _title.Focus(); };
        // closing the window without a choice keeps what was typed, like "save as draft"
        Closing += (_, e) =>
        {
            if (_busy) { e.Cancel = true; return; }
            if (!_closingHandled && _report.Draft.Status == ReportStatus.Draft && Directory.Exists(_report.Dir)) { Store(); _report.Save(); }
        };
    }

    static TextBox Multi(double height) => new() { AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, Height = height, MaxLength = 20_000, FontSize = 14 };

    static Button Button(string key, Action onClick)
    {
        var b = Skin.Btn(L.T(key), null, 40);
        b.FontSize = 14;
        b.Margin = new Thickness(10, 0, 0, 0);
        b.Click += (_, _) => onClick();
        return b;
    }

    static Button Button(string key, Func<Task> onClick)
    {
        var b = Skin.Btn(L.T(key), null, 40);
        b.FontSize = 14;
        b.Margin = new Thickness(10, 0, 0, 0);
        b.Click += async (_, _) => await onClick();
        return b;
    }

    /// <summary>A field with its caption above, as in the sketch; <paramref name="aside"/> is a dim remark after the caption.</summary>
    static Control Field(string key, Control input, string? aside = null)
    {
        var caption = new TextBlock { FontSize = 13, Foreground = Skin.B(Skin.Text2) };
        caption.Inlines!.Add(new Run(L.T(key)));
        if (aside is not null) caption.Inlines.Add(new Run(" — " + aside) { Foreground = Skin.B(Skin.Dim) });
        var s = new StackPanel { Spacing = 6 };
        s.Children.Add(caption);
        s.Children.Add(input);
        return s;
    }

    static Border Bar(Control child, bool top) => new()
    {
        Background = Skin.B(Skin.Rail),
        BorderBrush = Skin.B(Skin.Track),
        BorderThickness = top ? new Thickness(0, 0, 0, 2) : new Thickness(0, 2, 0, 0),
        Padding = new Thickness(24, 14),
        Child = child,
    };

    void SelectKind(string kind)
    {
        _kindValue = kind;
        foreach (var chip in _kind.Children.OfType<Button>()) chip.Classes.Set("on", (string?)chip.Tag == kind);
    }

    void BuildForm()
    {
        // header: what this is and that the game waits
        var head = new DockPanel();
        var paused = new TextBlock { Text = L.T("report.paused"), FontSize = 13, Foreground = Skin.B(Skin.Muted), TextWrapping = TextWrapping.Wrap, MaxWidth = 460, VerticalAlignment = VerticalAlignment.Center, TextAlignment = TextAlignment.Right };
        DockPanel.SetDock(paused, Dock.Right);
        head.Children.Add(paused);
        head.Children.Add(new TextBlock { Text = L.T("report.title"), FontFamily = Skin.Medium, FontWeight = FontWeight.Bold, FontSize = 24, Foreground = Skin.B(Skin.Accent), VerticalAlignment = VerticalAlignment.Center });

        // left: the screenshot large, what to attach, technical data folded
        var left = new StackPanel { Spacing = 12 };
        if (File.Exists(_report.ShotPath))
        {
            try
            {
                using var s = File.OpenRead(_report.ShotPath);
                left.Children.Add(Skin.Panel(new Image { Source = new Bitmap(s), Height = 202, Stretch = Stretch.UniformToFill }, new Thickness(2)));
            }
            catch (Exception e) when (e is IOException or ArgumentException or InvalidOperationException) { }
        }
        var files = new StackPanel { Spacing = 10 };
        files.Children.Add(Skin.H2(L.T("report.files")));
        if (File.Exists(_report.ShotPath))
        {
            _shot.Content = L.T("report.attachShot", L.Size(new FileInfo(_report.ShotPath).Length));
            files.Children.Add(_shot);
        }
        if (_report.LogPath is { } log)
        {
            _log.Content = L.T("report.attachLog", Path.GetFileName(log), L.Size(new FileInfo(log).Length));
            files.Children.Add(_log);
        }
        var saves = _report.RecentSaves();
        if (saves.Count > 0)
        {
            foreach (var s in saves)
                _saves.Items.Add(new ComboBoxItem { Content = s.Snapshot ? L.T("report.saveSnapshot", L.Size(s.Size)) : $"{s.Name} — {L.Size(s.Size)} — {s.Modified:yyyy-MM-dd HH:mm}", Tag = s.Path });
            _saves.SelectedIndex = 0;
            _save.Content = L.T("report.attachSave");
            _saves.IsEnabled = false;
            _save.IsCheckedChanged += (_, _) => _saves.IsEnabled = _save.IsChecked == true;
            files.Children.Add(_save);
            files.Children.Add(_saves);
        }
        files.Children.Add(Skin.Note(L.T("report.consent"), 12));
        left.Children.Add(Skin.Panel(files, new Thickness(14, 12)));
        var tech = new TextBox { Text = _report.ContextText(BuiltIn.VersionText), IsReadOnly = true, TextWrapping = TextWrapping.Wrap, FontFamily = new FontFamily("Consolas,monospace"), FontSize = 11 };
        left.Children.Add(new Expander { Header = L.T("report.tech"), Content = tech, HorizontalAlignment = HorizontalAlignment.Stretch, FontSize = 13 });

        // right: the words
        var right = new StackPanel { Spacing = 12 };
        right.Children.Add(_kind);
        right.Children.Add(Field("report.field.title", _title));
        right.Children.Add(Field("report.field.description", _description));
        right.Children.Add(Field("report.field.steps", _steps, L.T("report.optional")));
        var pair = new Grid { ColumnDefinitions = new ColumnDefinitions("*,12,*") };
        var expected = Field("report.field.expected", _expected);
        var actual = Field("report.field.actual", _actual);
        Grid.SetColumn(actual, 2);
        pair.Children.Add(expected);
        pair.Children.Add(actual);
        right.Children.Add(pair);

        var body = new Grid { ColumnDefinitions = new ColumnDefinitions("380,20,*"), Margin = new Thickness(24, 18) };
        var leftScroll = new ScrollViewer { Content = left };
        var rightScroll = new ScrollViewer { Content = right };
        Grid.SetColumn(rightScroll, 2);
        body.Children.Add(leftScroll);
        body.Children.Add(rightScroll);

        // footer: the status, then the choices
        var foot = new DockPanel();
        var buttons = new StackPanel { Orientation = Orientation.Horizontal };
        buttons.Children.Add(_cancel);
        buttons.Children.Add(_draft);
        buttons.Children.Add(_send);
        DockPanel.SetDock(buttons, Dock.Right);
        foot.Children.Add(buttons);
        foot.Children.Add(_status);

        var root = new DockPanel();
        var top = Bar(head, top: true);
        var bottom = Bar(foot, top: false);
        DockPanel.SetDock(top, Dock.Top);
        DockPanel.SetDock(bottom, Dock.Bottom);
        root.Children.Add(top);
        root.Children.Add(bottom);
        root.Children.Add(body);
        Content = root;
    }

    void Load(ReportDraft d)
    {
        SelectKind(ReportKinds.All.Contains(d.Kind) ? d.Kind : ReportKinds.Bug);
        _title.Text = d.Title;
        _description.Text = d.Description;
        _steps.Text = d.Steps;
        _expected.Text = d.Expected;
        _actual.Text = d.Actual;
        _shot.IsChecked = d.AttachShot;
        _log.IsChecked = d.AttachLog;
        if (d.SavePath is { } save)
        {
            _save.IsChecked = true;
            foreach (var item in _saves.Items.OfType<ComboBoxItem>())
                if (string.Equals((string?)item.Tag, save, StringComparison.OrdinalIgnoreCase)) _saves.SelectedItem = item;
        }
    }

    void Store()
    {
        var d = _report.Draft;
        if (d.TicketNumber is null)
        {
            d.Kind = _kindValue;
            d.Title = _title.Text ?? "";
            d.Description = _description.Text ?? "";
            d.Steps = _steps.Text ?? "";
            d.Expected = _expected.Text ?? "";
            d.Actual = _actual.Text ?? "";
        }
        d.AttachShot = _shot.IsChecked == true;
        d.AttachLog = _log.IsChecked == true && _report.LogPath is not null;
        d.SavePath = _save.IsChecked == true ? (_saves.SelectedItem as ComboBoxItem)?.Tag as string : null;
    }

    void SaveDraft()
    {
        Store();
        _report.Draft.Status = _report.Draft.TicketNumber is null ? ReportStatus.Draft : ReportStatus.Queued;
        _report.Save();
        _closingHandled = true;
        Close();
    }

    async Task CancelAsync()
    {
        if (!await new MessageDialog(L.T("report.cancelConfirm"), withNo: true).ShowDialog<bool>(this)) return;
        try { _report.Discard(); }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { _status.Text = L.T("err.generic", e.Message); return; }
        _closingHandled = true;
        Close();
    }

    async Task SendAsync()
    {
        Store();
        var d = _report.Draft;
        if (d.TicketNumber is null && (string.IsNullOrWhiteSpace(d.Title) || string.IsNullOrWhiteSpace(d.Description)))
        {
            _status.Text = L.T("report.required");
            return;
        }
        var portalUrl = _settings.PortalUrl ?? BuiltIn.Defaults.PortalUrl;
        if (string.IsNullOrWhiteSpace(portalUrl) || !Uri.TryCreate(portalUrl, UriKind.Absolute, out var baseUri))
        {
            d.Status = ReportStatus.Queued;
            _report.Save();
            _status.Text = L.T("report.noPortal");
            return;
        }

        SetBusy(true);
        _status.Text = L.T("report.sending");
        try
        {
            await ReportFlow.SendAsync(_report, baseUri, CancellationToken.None);
            ShowSent();
        }
        catch (ReportQueuedException)
        {
            _status.Text = WithReason(L.T("report.queued"));
            _send.Content = L.T("report.retry");
        }
        catch (PortalException e)
        {
            _status.Text = WithReason(ErrorText(e.Code));
            foreach (var c in new Control[] { _kind, _title, _description, _steps, _expected, _actual }) c.IsEnabled = _report.Draft.TicketNumber is null;
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException)
        {
            _status.Text = L.T("err.generic", e.Message);
        }
        finally { SetBusy(false); }
    }

    void SetBusy(bool busy)
    {
        _busy = busy;
        _send.IsEnabled = _draft.IsEnabled = _cancel.IsEnabled = !busy;
    }

    /// <summary>The status line plus what exactly failed: "the site is unreachable" alone does not say what to fix.</summary>
    string WithReason(string text) =>
        string.IsNullOrWhiteSpace(_report.Draft.LastErrorDetail) ? text : text + "\n" + L.T("report.reason", _report.Draft.LastErrorDetail);

    static string ErrorText(string code)
    {
        var key = "report.err." + code;
        var text = L.T(key);
        return text == key ? L.T("report.err.other", code) : text;
    }

    void ShowSent()
    {
        var d = _report.Draft;
        var panel = new StackPanel { Spacing = 16 };

        var title = new DockPanel();
        var check = new Avalonia.Controls.Shapes.Path { Data = Geometry.Parse(Skin.IconCheck), Stroke = Skin.B(Skin.Teal), StrokeThickness = 2, Width = 40, Height = 40, Stretch = Stretch.Uniform, Margin = new Thickness(0, 0, 14, 0) };
        DockPanel.SetDock(check, Dock.Left);
        title.Children.Add(check);
        var words = new StackPanel { Spacing = 2, VerticalAlignment = VerticalAlignment.Center };
        words.Children.Add(new TextBlock { Text = L.T("report.sentTitle"), FontFamily = Skin.Medium, FontWeight = FontWeight.Bold, FontSize = 26 });
        if (d.DisplayNumber is { } num) words.Children.Add(new TextBlock { Text = num, FontFamily = Skin.Medium, FontSize = 15, Foreground = Skin.B(Skin.Teal) });
        title.Children.Add(words);
        panel.Children.Add(title);

        panel.Children.Add(Skin.Note(L.T("report.sentHint"), 14, Skin.Text2));
        foreach (var s in d.Skipped)
            panel.Children.Add(Skin.Note(L.T("report.skipped", s.Name, ErrorText(s.Reason)), 13, Skin.WarnText));

        var buttons = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 10, Margin = new Thickness(0, 6, 0, 0) };
        if (d.TicketUrl is { } url && (url.StartsWith("https://", StringComparison.OrdinalIgnoreCase) || url.StartsWith("http://", StringComparison.OrdinalIgnoreCase)))
        {
            var open = Skin.Btn(L.T("report.openTicket"), "primary", 44);
            open.FontFamily = Skin.Medium;
            open.FontSize = 17;
            open.Padding = new Thickness(22, 0);
            open.Click += (_, _) => OpenUrl(url);
            buttons.Children.Add(open);
        }
        var close = Skin.Btn(L.T(App.Report is not null ? "report.backToGame" : "report.close"), null, 44);
        close.FontSize = 15;
        close.Padding = new Thickness(22, 0);
        close.Click += (_, _) => { _closingHandled = true; Close(); };
        buttons.Children.Add(close);
        panel.Children.Add(buttons);

        var head = new TextBlock { Text = L.T("report.title"), FontFamily = Skin.Medium, FontWeight = FontWeight.Bold, FontSize = 24, Foreground = Skin.B(Skin.Accent) };
        var root = new DockPanel();
        var top = Bar(head, top: true);
        DockPanel.SetDock(top, Dock.Top);
        root.Children.Add(top);
        var card = Skin.Panel(panel, new Thickness(36, 32));
        card.Width = 560;
        card.HorizontalAlignment = HorizontalAlignment.Center;
        card.VerticalAlignment = VerticalAlignment.Center;
        root.Children.Add(card);
        Content = root;
    }

    public static void OpenUrl(string url)
    {
        try { Process.Start(new ProcessStartInfo(url) { UseShellExecute = true })?.Dispose(); }
        catch (Exception e) when (e is System.ComponentModel.Win32Exception or InvalidOperationException) { }
    }
}

/// <summary>Sending, shared by the form and the "send queued" button: one sender setup for both.</summary>
public static class ReportFlow
{
    static readonly HttpClient Http = new() { Timeout = TimeSpan.FromMinutes(10) };

    public static async Task SendAsync(Report report, Uri portal, CancellationToken ct)
    {
        var gameDir = report.Context?.GameDir is { Length: > 0 } g ? Path.GetFullPath(g) : null;
        var limits = new ReportLimits();
        if (BuiltIn.Defaults.ReportMaxFileBytes > 0) limits.MaxFileBytes = BuiltIn.Defaults.ReportMaxFileBytes;
        var sender = new ReportSender(new PortalClient(Http, portal), limits, Redactor.ForThisMachine(gameDir), BuiltIn.VersionText);
        await sender.SendAsync(report, ct);
        if (report.Draft.Status == ReportStatus.Sent)
        {
            try { report.TrimSent(); }
            catch (Exception e) when (e is IOException or UnauthorizedAccessException) { }
        }
    }

    /// <summary>
    /// Ticket statuses for the sent reports under <paramref name="roots"/>, then the rotation that may now drop
    /// finished ones. Bounded in time: the game's list waits for this, and a dead network must not hang it.
    /// </summary>
    public static async Task RefreshAsync(IEnumerable<string> roots, Uri portal, CancellationToken ct)
    {
        var list = roots.ToList();
        using var cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
        cts.CancelAfter(TimeSpan.FromSeconds(30));
        try { await ReportStore.RefreshAsync(ReportStore.List(list), new PortalClient(Http, portal), cts.Token); }
        finally { ReportStore.Rotate(ReportStore.List(list), new ReportLimits().KeepSent); }
    }
}
