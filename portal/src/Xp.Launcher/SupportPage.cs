using Avalonia;
using Avalonia.Controls;
using Avalonia.Layout;
using Avalonia.Media;

namespace Xp.Launcher;

/// <summary>
/// Two big buttons: support Dioxine, the author of X-Piratez, and support the HD developers.
/// The pages are in defaults.json (supportModUrl, supportHdUrl); a button without a page stays
/// visible but disabled, so the page never looks as if one of the two was forgotten.
/// </summary>
public sealed class SupportPage : UserControl
{
    public SupportPage()
    {
        var panel = new StackPanel { Spacing = 14, Margin = new Thickness(28, 24, 28, 28), MaxWidth = 640, HorizontalAlignment = HorizontalAlignment.Left };
        panel.Children.Add(Skin.H1(L.T("support.title")));
        panel.Children.Add(Skin.Note(L.T("support.hint"), 14, Skin.Text2));
        panel.Children.Add(Big("support.mod", "support.modNote", BuiltIn.Defaults.SupportModUrl));
        panel.Children.Add(Big("support.hd", "support.hdNote", BuiltIn.Defaults.SupportHdUrl));
        Content = new ScrollViewer { Content = panel };
    }

    static Button Big(string key, string noteKey, string url)
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
        text.Children.Add(new TextBlock { Text = L.T(key), FontSize = 20, FontFamily = Skin.Medium });
        text.Children.Add(new TextBlock { Text = ok ? L.T(noteKey) : L.T("support.noLink"), FontSize = 13, Foreground = Skin.B(ok ? Skin.Text2 : Skin.Dim), TextWrapping = TextWrapping.Wrap });
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
