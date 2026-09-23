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
public sealed class ReportsWindow : Window
{
    readonly Settings _settings;
    readonly IReadOnlyList<string> _roots;
    readonly StackPanel _list = new() { Spacing = 6 };
    readonly TextBlock _status = new() { TextWrapping = TextWrapping.Wrap };
    readonly Button _sendAll;
    bool _busy;

    public ReportsWindow(Settings settings, IReadOnlyList<string> roots)
    {
        _settings = settings;
        _roots = roots;
        Title = L.T("reports.title");
        Width = 720; Height = 520;
        WindowStartupLocation = WindowStartupLocation.CenterOwner;

        _sendAll = new Button { Content = L.T("reports.sendQueued") };
        _sendAll.Classes.Add("accent");
        _sendAll.Click += async (_, _) => await SendQueuedAsync();

        var top = new StackPanel { Spacing = 8, Margin = new Thickness(16, 16, 16, 8) };
        top.Children.Add(new TextBlock { Text = L.T("reports.hint"), TextWrapping = TextWrapping.Wrap, Opacity = 0.8 });
        top.Children.Add(_sendAll);
        top.Children.Add(_status);
        var root = new DockPanel();
        DockPanel.SetDock(top, Dock.Top);
        root.Children.Add(top);
        root.Children.Add(new ScrollViewer { Content = _list, Margin = new Thickness(16, 0, 16, 16) });
        Content = root;
        Fill();
    }

    public static IReadOnlyList<Report> Load(IEnumerable<string> roots) => ReportStore.List(roots);

    void Fill()
    {
        _list.Children.Clear();
        var reports = Load(_roots);
        _sendAll.IsEnabled = !_busy && reports.Any(r => r.Draft.Status == ReportStatus.Queued);
        if (reports.Count == 0) _list.Children.Add(new TextBlock { Text = L.T("reports.empty"), Opacity = 0.7 });
        foreach (var r in reports) _list.Children.Add(Row(r));
    }

    Control Row(Report r)
    {
        var d = r.Draft;
        var title = string.IsNullOrWhiteSpace(d.Title) ? L.T("reports.untitled") : d.Title;
        var state = d.Status switch
        {
            ReportStatus.Sent => L.T("reports.state.sent", d.DisplayNumber ?? ""),
            ReportStatus.Queued => L.T("reports.state.queued"),
            _ => L.T("reports.state.draft"),
        };
        var text = new StackPanel();
        text.Children.Add(new TextBlock { Text = title, FontWeight = FontWeight.SemiBold, TextTrimming = TextTrimming.CharacterEllipsis });
        text.Children.Add(new TextBlock { Text = $"{d.CreatedAt.ToLocalTime():yyyy-MM-dd HH:mm} · {L.T("report.kind." + d.Kind)} · {state}", FontSize = 12, Opacity = 0.75 });

        var buttons = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 6, VerticalAlignment = VerticalAlignment.Center };
        if (d.Status == ReportStatus.Sent)
        {
            if (d.TicketUrl is { } url && url.StartsWith("http", StringComparison.OrdinalIgnoreCase))
                buttons.Children.Add(Small("report.openTicket", () => ReportWindow.OpenUrl(url)));
        }
        else
        {
            buttons.Children.Add(Small("reports.open", async () =>
            {
                await new ReportWindow(Report.Open(r.Dir), _settings).ShowDialog(this);
                Fill();
            }));
        }
        buttons.Children.Add(Small("reports.delete", async () =>
        {
            if (!await new MessageDialog(L.T("reports.deleteConfirm"), withNo: true).ShowDialog<bool>(this)) return;
            try { r.Discard(); }
            catch (Exception e) when (e is IOException or UnauthorizedAccessException) { _status.Text = L.T("err.generic", e.Message); }
            Fill();
        }));

        var row = new DockPanel { Margin = new Thickness(0, 0, 0, 4) };
        DockPanel.SetDock(buttons, Dock.Right);
        row.Children.Add(buttons);
        row.Children.Add(text);
        return new Border { Child = row, Padding = new Thickness(8), BorderThickness = new Thickness(1), BorderBrush = Brushes.Gray, CornerRadius = new CornerRadius(4) };
    }

    Button Small(string key, Func<Task> onClick)
    {
        var b = new Button { Content = L.T(key), IsEnabled = !_busy };
        b.Click += async (_, _) => await onClick();
        return b;
    }

    Button Small(string key, Action onClick)
    {
        var b = new Button { Content = L.T(key) };
        b.Click += (_, _) => onClick();
        return b;
    }

    async Task SendQueuedAsync()
    {
        var portalUrl = _settings.PortalUrl ?? BuiltIn.Defaults.PortalUrl;
        if (!Uri.TryCreate(portalUrl, UriKind.Absolute, out var baseUri)) { _status.Text = L.T("report.noPortal"); return; }
        _busy = true;
        Fill();
        int sent = 0, left = 0;
        foreach (var r in Load(_roots).Where(r => r.Draft.Status == ReportStatus.Queued))
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
        ReportStore.Rotate(Load(_roots), new ReportLimits().KeepSent);
        Fill();
    }
}
