using System.Diagnostics;
using Avalonia;
using Avalonia.Controls;
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
    readonly ComboBox _kind = new() { MinWidth = 220 };
    readonly TextBox _title = new() { MaxLength = 140 };
    readonly TextBox _description = Multi(110);
    readonly TextBox _steps = Multi(70);
    readonly TextBox _expected = Multi(50);
    readonly TextBox _actual = Multi(50);
    readonly CheckBox _shot = new();
    readonly CheckBox _log = new();
    readonly CheckBox _save = new();
    readonly ComboBox _saves = new() { MinWidth = 360 };
    readonly TextBlock _status = new() { TextWrapping = TextWrapping.Wrap };
    readonly Button _send, _draft, _cancel;
    readonly StackPanel _form = new() { Spacing = 6, Margin = new Thickness(16) };
    bool _busy;
    bool _closingHandled;

    public ReportWindow(Report report, Settings settings)
    {
        _report = report;
        _settings = settings;
        Title = L.T("report.title");
        Width = 720; Height = 820; MinWidth = 560; MinHeight = 520;
        WindowStartupLocation = WindowStartupLocation.CenterScreen;

        foreach (var k in ReportKinds.All) _kind.Items.Add(new ComboBoxItem { Content = L.T("report.kind." + k), Tag = k });
        _send = Button("report.send", async () => await SendAsync());
        _send.Classes.Add("accent");
        _draft = Button("report.draft", SaveDraft);
        _cancel = Button("report.cancel", async () => await CancelAsync());

        var d = report.Draft;
        if (d.Status == ReportStatus.Sent) { ShowSent(); }
        else
        {
            BuildForm();
            Load(d);
            // the ticket already exists (only files were left): its text can no longer change
            bool created = d.TicketNumber is not null;
            foreach (var c in new Control[] { _kind, _title, _description, _steps, _expected, _actual }) c.IsEnabled = !created;
            if (d.Status == ReportStatus.Queued) _status.Text = L.T("report.queuedBefore");
            else if (d.LastError is { } err) _status.Text = ErrorText(err);
        }

        Opened += (_, _) => { Activate(); _title.Focus(); };
        // closing the window without a choice keeps what was typed, like "save as draft"
        Closing += (_, e) =>
        {
            if (_busy) { e.Cancel = true; return; }
            if (!_closingHandled && _report.Draft.Status == ReportStatus.Draft && Directory.Exists(_report.Dir)) { Store(); _report.Save(); }
        };
    }

    static TextBox Multi(double height) => new() { AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, Height = height, MaxLength = 20_000 };

    static Button Button(string key, Action onClick)
    {
        var b = new Button { Content = L.T(key), Margin = new Thickness(0, 0, 8, 0) };
        b.Click += (_, _) => onClick();
        return b;
    }

    static Button Button(string key, Func<Task> onClick)
    {
        var b = new Button { Content = L.T(key), Margin = new Thickness(0, 0, 8, 0) };
        b.Click += async (_, _) => await onClick();
        return b;
    }

    static TextBlock Label(string key) => new() { Text = L.T(key), FontWeight = FontWeight.SemiBold, Margin = new Thickness(0, 6, 0, 0) };
    static TextBlock Hint(string text) => new() { Text = text, FontSize = 12, Opacity = 0.75, TextWrapping = TextWrapping.Wrap };

    void BuildForm()
    {
        _form.Children.Add(Hint(L.T("report.paused")));
        _form.Children.Add(Label("report.kind"));
        _form.Children.Add(_kind);
        _form.Children.Add(Label("report.field.title"));
        _form.Children.Add(_title);
        _form.Children.Add(Label("report.field.description"));
        _form.Children.Add(_description);
        _form.Children.Add(Label("report.field.steps"));
        _form.Children.Add(_steps);
        _form.Children.Add(Label("report.field.expected"));
        _form.Children.Add(_expected);
        _form.Children.Add(Label("report.field.actual"));
        _form.Children.Add(_actual);

        _form.Children.Add(Label("report.files"));
        if (File.Exists(_report.ShotPath))
        {
            try
            {
                using var s = File.OpenRead(_report.ShotPath);
                _form.Children.Add(new Image { Source = new Bitmap(s), MaxHeight = 220, HorizontalAlignment = HorizontalAlignment.Left, Stretch = Stretch.Uniform });
            }
            catch (Exception e) when (e is IOException or ArgumentException or InvalidOperationException) { }
            _shot.Content = L.T("report.attachShot", L.Size(new FileInfo(_report.ShotPath).Length));
            _form.Children.Add(_shot);
        }

        if (_report.LogPath is { } log)
        {
            _log.Content = L.T("report.attachLog", Path.GetFileName(log), L.Size(new FileInfo(log).Length));
            _form.Children.Add(_log);
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
            var row = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8 };
            row.Children.Add(_save);
            row.Children.Add(_saves);
            _form.Children.Add(row);
        }
        _form.Children.Add(Hint(L.T("report.consent")));

        var tech = new TextBox { Text = _report.ContextText(BuiltIn.VersionText), IsReadOnly = true, TextWrapping = TextWrapping.Wrap, FontFamily = new FontFamily("Consolas,monospace"), FontSize = 11 };
        _form.Children.Add(new Expander { Header = L.T("report.tech"), Content = tech, HorizontalAlignment = HorizontalAlignment.Stretch });

        var buttons = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 12, 0, 0) };
        buttons.Children.Add(_send);
        buttons.Children.Add(_draft);
        buttons.Children.Add(_cancel);
        _form.Children.Add(buttons);
        _form.Children.Add(_status);
        Content = new ScrollViewer { Content = _form };
    }

    void Load(ReportDraft d)
    {
        foreach (var item in _kind.Items.OfType<ComboBoxItem>())
            if ((string?)item.Tag == d.Kind) _kind.SelectedItem = item;
        if (_kind.SelectedItem is null) _kind.SelectedIndex = 0;
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
            d.Kind = (_kind.SelectedItem as ComboBoxItem)?.Tag as string ?? ReportKinds.Bug;
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
            _status.Text = L.T("report.queued");
            _send.Content = L.T("report.retry");
        }
        catch (PortalException e)
        {
            _status.Text = ErrorText(e.Code);
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

    static string ErrorText(string code)
    {
        var key = "report.err." + code;
        var text = L.T(key);
        return text == key ? L.T("report.err.other", code) : text;
    }

    void ShowSent()
    {
        var d = _report.Draft;
        var panel = new StackPanel { Spacing = 12, Margin = new Thickness(16) };
        panel.Children.Add(new TextBlock { Text = L.T("report.sent", d.DisplayNumber ?? ""), FontSize = 18, FontWeight = FontWeight.SemiBold, TextWrapping = TextWrapping.Wrap });
        panel.Children.Add(Hint(L.T("report.sentHint")));
        foreach (var s in d.Skipped)
            panel.Children.Add(Hint(L.T("report.skipped", s.Name, ErrorText(s.Reason))));
        var buttons = new StackPanel { Orientation = Orientation.Horizontal };
        if (d.TicketUrl is { } url && (url.StartsWith("https://", StringComparison.OrdinalIgnoreCase) || url.StartsWith("http://", StringComparison.OrdinalIgnoreCase)))
            buttons.Children.Add(Button("report.openTicket", () => OpenUrl(url)));
        buttons.Children.Add(Button("report.close", () => { _closingHandled = true; Close(); }));
        panel.Children.Add(buttons);
        Content = panel;
        Height = 300;
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
}
