using Avalonia;
using Avalonia.Controls;
using Avalonia.Layout;
using Avalonia.Media;
using Xp.Launcher.Core;

namespace Xp.Launcher;

/// <summary>
/// Reports on this machine: drafts, the queue of ones that could not be sent, and sent ones with
/// their ticket links. Sending the queue is a button, never done in the background.
/// </summary>
public sealed class ReportsPage : UserControl
{
    readonly Settings _settings;
    readonly Func<List<string>> _roots;
    readonly StackPanel _list = new() { Spacing = 10 };
    readonly TextBlock _status = new() { TextWrapping = TextWrapping.Wrap, FontSize = 13, Foreground = Skin.B(Skin.Text2) };
    readonly TextBlock _checked = new() { FontSize = 13, Foreground = Skin.B(Skin.Muted), VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(0, 0, 16, 0) };
    readonly Button _sendAll;
    bool _busy, _refreshing;

    /// <summary>Something was sent, deleted or refreshed: the rail counter and the home notices recount.</summary>
    public event Action? Changed;

    public ReportsPage(Settings settings, Func<List<string>> roots)
    {
        _settings = settings;
        _roots = roots;

        _sendAll = Skin.Btn(L.T("reports.sendQueued"), "primary", 40);
        _sendAll.FontFamily = Skin.Medium;
        _sendAll.FontSize = 14;
        _sendAll.Click += async (_, _) => await SendQueuedAsync();

        var head = new DockPanel();
        DockPanel.SetDock(_sendAll, Dock.Right);
        DockPanel.SetDock(_checked, Dock.Right);
        head.Children.Add(_sendAll);
        head.Children.Add(_checked);
        head.Children.Add(Skin.H1(L.T("reports.title")));

        var top = new StackPanel { Spacing = 10, Margin = new Thickness(0, 0, 0, 14) };
        top.Children.Add(head);
        top.Children.Add(Skin.Note(L.T("reports.hint")));
        top.Children.Add(_status);

        var root = new DockPanel { Margin = new Thickness(28, 24, 28, 24) };
        DockPanel.SetDock(top, Dock.Top);
        root.Children.Add(top);
        root.Children.Add(new ScrollViewer { Content = _list });
        Content = root;
    }

    /// <summary>
    /// The page was opened: show what is on disk, then fresh ticket statuses. Asking is harmless,
    /// unlike sending, so it needs no button.
    /// </summary>
    public async void Shown()
    {
        Fill();
        if (_refreshing || _busy) return;
        var portalUrl = _settings.PortalUrl ?? BuiltIn.Defaults.PortalUrl;
        if (!Uri.TryCreate(portalUrl, UriKind.Absolute, out var baseUri)) return;
        _refreshing = true;
        try { await ReportFlow.RefreshAsync(_roots(), baseUri, CancellationToken.None); }
        catch (Exception e) when (e is HttpRequestException or OperationCanceledException or PortalException or IOException or UnauthorizedAccessException) { }
        _refreshing = false;
        if (!_busy) Fill();
        Changed?.Invoke();
    }

    public async void SendQueued() => await SendQueuedAsync();

    void Fill()
    {
        _list.Children.Clear();
        var reports = ReportStore.List(_roots());
        int queued = reports.Count(r => r.Draft.Status == ReportStatus.Queued);
        _sendAll.IsVisible = queued > 0;
        _sendAll.IsEnabled = !_busy;
        _sendAll.Content = L.T("reports.sendQueuedCount", queued);
        var last = reports.Select(r => r.Draft.CheckedAt).Where(t => t is not null).Max();
        _checked.Text = last is { } t ? L.T("reports.checkedAt", t.ToLocalTime().ToString("HH:mm")) : "";
        if (reports.Count == 0) _list.Children.Add(Skin.Note(L.T("reports.empty"), 14));
        foreach (var r in reports) _list.Children.Add(Row(r));
    }

    Control Row(Report r)
    {
        var d = r.Draft;
        var (tag, tagBg, tagFg) = d.Status switch
        {
            ReportStatus.Sent => StatusTag(d.TicketStatus),
            ReportStatus.Queued => (L.T("reports.state.queued"), Skin.WarnFill, Skin.WarnText),
            _ => (L.T("reports.state.draft"), Color.Parse("#1A1828"), Skin.Muted),
        };

        var meta = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 10 };
        if (d.DisplayNumber is { } num) meta.Children.Add(new TextBlock { Text = num, FontFamily = Skin.Medium, FontSize = 13, VerticalAlignment = VerticalAlignment.Center });
        meta.Children.Add(new TextBlock { Text = $"{d.CreatedAt.ToLocalTime():yyyy-MM-dd HH:mm} · {L.T("report.kind." + d.Kind)}", FontSize = 13, Foreground = Skin.B(Skin.Muted), VerticalAlignment = VerticalAlignment.Center });
        meta.Children.Add(new Border
        {
            Background = Skin.B(tagBg), CornerRadius = new CornerRadius(2), Padding = new Thickness(8, 2),
            Child = new TextBlock { Text = tag, FontSize = 12, FontFamily = Skin.Medium, Foreground = Skin.B(tagFg) },
        });

        var text = new StackPanel { Spacing = 6 };
        text.Children.Add(meta);
        text.Children.Add(new TextBlock { Text = string.IsNullOrWhiteSpace(d.Title) ? L.T("reports.untitled") : d.Title, FontSize = 15, FontFamily = Skin.Medium, TextTrimming = TextTrimming.CharacterEllipsis });
        var note = d.Status == ReportStatus.Sent
            ? (string.IsNullOrWhiteSpace(d.StaffReply) ? null : L.T("reports.team", d.StaffReply.Trim()))
            : d.LastErrorDetail;
        if (note is not null)
            text.Children.Add(new TextBlock { Text = note, FontSize = 13, LineHeight = 19, Foreground = Skin.B(Skin.Text2), TextWrapping = TextWrapping.Wrap, MaxLines = 2, TextTrimming = TextTrimming.CharacterEllipsis });

        var buttons = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8, VerticalAlignment = VerticalAlignment.Top };
        if (d.Status == ReportStatus.Sent)
        {
            if (d.TicketUrl is { } url && url.StartsWith("http", StringComparison.OrdinalIgnoreCase))
                buttons.Children.Add(Small("reports.onSite", null, () => ReportWindow.OpenUrl(url)));
        }
        else
        {
            if (d.Status == ReportStatus.Queued)
                buttons.Children.Add(Small("reports.send", "primary", async () => await SendOneAsync(r)));
            buttons.Children.Add(Small("reports.openForm", null, async () =>
            {
                if (TopLevel.GetTopLevel(this) is not Window owner) return;
                await new ReportWindow(Report.Open(r.Dir), _settings).ShowDialog(owner);
                Fill();
                Changed?.Invoke();
            }));
        }
        buttons.Children.Add(Small("reports.delete", null, async () =>
        {
            if (TopLevel.GetTopLevel(this) is not Window owner) return;
            if (!await new MessageDialog(L.T("reports.deleteConfirm"), withNo: true).ShowDialog<bool>(owner)) return;
            try { r.Discard(); }
            catch (Exception e) when (e is IOException or UnauthorizedAccessException) { _status.Text = L.T("err.generic", e.Message); }
            Fill();
            Changed?.Invoke();
        }));

        var row = new DockPanel();
        buttons.Margin = new Thickness(16, 0, 0, 0);
        DockPanel.SetDock(buttons, Dock.Right);
        row.Children.Add(buttons);
        row.Children.Add(text);
        return Skin.Panel(row, new Thickness(16, 12));
    }

    /// <summary>The ticket's stage as a coloured label: "needs info" in the accent, the rest calm.</summary>
    static (string, Color, Color) StatusTag(string? status)
    {
        var text = status is null ? L.T("reports.state.sent", "").TrimEnd(',', ' ') : L.T("ticket.status." + status);
        return status switch
        {
            "NeedsInfo" => (text, Color.Parse("#1E3008"), Skin.AccentHover),
            "Closed" or "Duplicate" or "Rejected" or "Gone" => (text, Color.Parse("#1A1828"), Skin.Muted),
            _ => (text, Color.Parse("#082420"), Skin.Teal),
        };
    }

    Button Small(string key, string? cls, Action onClick)
    {
        var b = Skin.Btn(L.T(key), cls, 34);
        b.IsEnabled = !_busy;
        b.Click += (_, _) => onClick();
        return b;
    }

    async Task SendOneAsync(Report r)
    {
        var portalUrl = _settings.PortalUrl ?? BuiltIn.Defaults.PortalUrl;
        if (!Uri.TryCreate(portalUrl, UriKind.Absolute, out var baseUri)) { _status.Text = L.T("report.noPortal"); return; }
        _busy = true;
        Fill();
        try
        {
            await ReportFlow.SendAsync(r, baseUri, CancellationToken.None);
            _status.Text = L.T("reports.sendResult", 1, 0);
        }
        catch (Exception e) when (e is ReportQueuedException or PortalException or IOException or UnauthorizedAccessException)
        {
            _status.Text = L.T("reports.sendResult", 0, 1);
        }
        _busy = false;
        Fill();
        Changed?.Invoke();
    }

    async Task SendQueuedAsync()
    {
        if (_busy) return;
        var portalUrl = _settings.PortalUrl ?? BuiltIn.Defaults.PortalUrl;
        if (!Uri.TryCreate(portalUrl, UriKind.Absolute, out var baseUri)) { _status.Text = L.T("report.noPortal"); return; }
        _busy = true;
        Fill();
        int sent = 0, left = 0;
        foreach (var r in ReportStore.List(_roots()).Where(r => r.Draft.Status == ReportStatus.Queued))
        {
            try
            {
                await ReportFlow.SendAsync(r, baseUri, CancellationToken.None);
                sent++;
            }
            catch (Exception e) when (e is ReportQueuedException or PortalException or IOException or UnauthorizedAccessException)
            {
                left++;
            }
        }
        _busy = false;
        _status.Text = L.T("reports.sendResult", sent, left);
        ReportStore.Rotate(ReportStore.List(_roots()), new ReportLimits().KeepSent);
        Fill();
        Changed?.Invoke();
    }
}
