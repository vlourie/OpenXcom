using Avalonia;
using Avalonia.Controls;
using Avalonia.Layout;
using Avalonia.Media;

namespace Xp.Launcher;

/// <summary>
/// Two big buttons: support Dioxine, the author of X-Piratez, and support the HD developers.
/// The pages are in defaults.json (supportModUrl, supportHdUrl); a button without a page stays
/// visible but disabled, so the window never looks as if one of the two was forgotten.
/// </summary>
public sealed class SupportWindow : Window
{
    public SupportWindow()
    {
        Title = L.T("support.title");
        Width = 560; Height = 360;
        CanResize = false;
        WindowStartupLocation = WindowStartupLocation.CenterOwner;

        var panel = new StackPanel { Spacing = 14, Margin = new Thickness(24) };
        panel.Children.Add(new TextBlock { Text = L.T("support.hint"), TextWrapping = TextWrapping.Wrap, Opacity = 0.8 });
        panel.Children.Add(Big("support.mod", "support.modNote", BuiltIn.Defaults.SupportModUrl));
        panel.Children.Add(Big("support.hd", "support.hdNote", BuiltIn.Defaults.SupportHdUrl));
        Content = panel;
    }

    static Button Big(string key, string noteKey, string url)
    {
        bool ok = url.StartsWith("https://", StringComparison.OrdinalIgnoreCase);
        var text = new StackPanel { Spacing = 4 };
        text.Children.Add(new TextBlock { Text = L.T(key), FontSize = 20, FontWeight = FontWeight.SemiBold, HorizontalAlignment = HorizontalAlignment.Center });
        text.Children.Add(new TextBlock { Text = ok ? L.T(noteKey) : L.T("support.noLink"), FontSize = 12, Opacity = 0.75, TextWrapping = TextWrapping.Wrap, HorizontalAlignment = HorizontalAlignment.Center, TextAlignment = TextAlignment.Center });
        var b = new Button
        {
            Content = text,
            HorizontalAlignment = HorizontalAlignment.Stretch,
            HorizontalContentAlignment = HorizontalAlignment.Center,
            Padding = new Thickness(16, 18),
            IsEnabled = ok,
        };
        b.Classes.Add("accent");
        b.Click += (_, _) => ReportWindow.OpenUrl(url);
        return b;
    }
}
