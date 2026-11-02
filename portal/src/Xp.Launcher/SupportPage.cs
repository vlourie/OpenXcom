using Avalonia;
using Avalonia.Controls;
using Avalonia.Layout;
using Avalonia.Media;
using Xp.Launcher.Core;

namespace Xp.Launcher;

/// <summary>
/// Big buttons: support Dioxine, the author of X-Piratez, and the HD developers.
/// The pages are in defaults.json (supportModUrl, supportHdUrl); a button without a page stays
/// visible but disabled, so the page never looks as if one of the two was forgotten.
/// Below them "Other ways" - a list the site gives (/support.json, Core.SupportList), for a player to whom the
/// main services do not open; the same file can take a built-in button off if its service is dead. It is kept on
/// disk, so the page shows it at once and the site is asked when the page opens.
/// </summary>
public sealed class SupportPage : UserControl
{
    static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(15) };

    readonly Settings _settings;
    readonly Func<HttpClient> _http;
    readonly StackPanel _panel = new() { Spacing = 14, Margin = new Thickness(28, 24, 28, 28), MaxWidth = 640, HorizontalAlignment = HorizontalAlignment.Left };
    SupportList _list = SupportList.Empty;
    DateTime _askedAt;
    bool _asking;

    public SupportPage(Settings settings, Func<HttpClient>? http = null)
    {
        _settings = settings;
        _http = http ?? (() => Http);
        _list = SupportList.Cached(CachePath, L.Language) ?? SupportList.Empty;
        Build();
        Content = new ScrollViewer { Content = _panel };
    }

    static string CachePath => System.IO.Path.Combine(Settings.Dir, SupportList.File);

    void Build()
    {
        _panel.Children.Clear();
        _panel.Children.Add(Skin.H1(L.T("support.title")));
        _panel.Children.Add(Skin.Note(L.T("support.hint"), 14, Skin.Text2));
        if (!_list.Hidden.Contains("mod"))
        {
            _panel.Children.Add(Big(L.T("support.mod"), L.T("support.modNote"), BuiltIn.Defaults.SupportModUrl, builtIn: true));
            // the credit Dioxine asked for (27.10), beside his button
            _panel.Children.Add(Skin.Note(L.T("credit.piratez"), 13, Skin.Text2));
        }
        if (!_list.Hidden.Contains("hd"))
            _panel.Children.Add(Big(L.T("support.hd"), L.T("support.hdNote"), BuiltIn.Defaults.SupportHdUrl, builtIn: true));
        if (!_list.Hidden.Contains("hdPage"))
            _panel.Children.Add(Big(L.T("support.hdPage"), L.T("support.hdPageNote"), BuiltIn.Defaults.SupportHdPageUrl, builtIn: true));

        if (_list.Items.Count > 0)
        {
            _panel.Children.Add(Skin.H2(L.T("support.more")));
            _panel.Children.Add(Skin.Note(L.T("support.moreHint"), 14, Skin.Text2));
            foreach (var item in _list.Items) _panel.Children.Add(Big(item.Title, item.Note, item.Url, builtIn: false));
        }
    }

    /// <summary>The page came on screen: the kept list is there already, the site's is fetched when the last look is old.</summary>
    public async void Shown()
    {
        if (_asking || DateTime.UtcNow - _askedAt < TimeSpan.FromMinutes(10)) return;
        var portalUrl = _settings.PortalUrl ?? BuiltIn.Defaults.PortalUrl;
        if (!Uri.TryCreate(portalUrl, UriKind.Absolute, out var baseUri)) return;
        _asking = true;
        _askedAt = DateTime.UtcNow;
        try
        {
            using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(15));
            if (await SupportList.FetchAsync(_http(), baseUri, L.Language, CachePath, cts.Token) is { } fresh)
            {
                _list = fresh;
                Build();
            }
        }
        catch (Exception e) when (e is HttpRequestException or OperationCanceledException or IOException) { }
        _asking = false;
    }

    static Button Big(string title, string note, string url, bool builtIn)
    {
        bool ok = url.StartsWith("https://", StringComparison.OrdinalIgnoreCase);
        var b = new Button
        {
            HorizontalAlignment = HorizontalAlignment.Stretch,
            HorizontalContentAlignment = HorizontalAlignment.Stretch,
            Padding = new Thickness(20, 18),
            BorderThickness = new Thickness(2),
            IsEnabled = ok,
        };
        b.Classes.Add("card");
        var text = new StackPanel { Spacing = 4 };
        text.Children.Add(new TextBlock { Text = title, FontSize = 20, FontFamily = Skin.Medium, TextWrapping = TextWrapping.Wrap });
        // the built-in button without a page says the link comes later; a listed way always has its address
        if (ok ? note.Length > 0 : builtIn)
            text.Children.Add(new TextBlock { Text = ok ? note : L.T("support.noLink"), FontSize = 13, Foreground = Skin.B(ok ? Skin.Text2 : Skin.Dim), TextWrapping = TextWrapping.Wrap });
        var row = new DockPanel();
        var icon = Skin.Icon(Skin.IconHeart, null, 28);
        icon.Stroke = Skin.B(ok ? Skin.Accent : Skin.Dim);
        icon.Margin = new Thickness(0, 0, 16, 0);
        DockPanel.SetDock(icon, Dock.Left);
        row.Children.Add(icon);
        row.Children.Add(text);
        b.Content = row;
        b.Click += (_, _) => ReportWindow.OpenUrl(url);
        return b;
    }
}
