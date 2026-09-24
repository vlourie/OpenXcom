using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Presenters;
using Avalonia.Controls.Primitives;
using Avalonia.Controls.Shapes;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Styling;
using Avalonia.Themes.Fluent;
using Path = Avalonia.Controls.Shapes.Path;

namespace Xp.Launcher;

/// <summary>
/// The X-Piratez geoscape palette (docs/portal/LAUNCHER_UI.md §3), measured off a game frame:
/// space-violet background, windows with a dark green fill and a lime frame, acid lime accent,
/// turquoise lists, magenta for attention. Everything is code: the launcher has no XAML.
/// </summary>
public static class Skin
{
    public static readonly Color Bg = Color.Parse("#100010");
    public static readonly Color Rail = Color.Parse("#080008");
    public static readonly Color Fill = Color.Parse("#0A1404");
    public static readonly Color FrameOuter = Color.Parse("#081000");
    public static readonly Color FrameInner = Color.Parse("#507818");
    public static readonly Color Accent = Color.Parse("#80D000");
    public static readonly Color AccentHover = Color.Parse("#A8F030");
    public static readonly Color AccentPressed = Color.Parse("#6AB000");
    public static readonly Color OnAccent = Color.Parse("#0A1400");
    public static readonly Color Teal = Color.Parse("#00C8B8");
    public static readonly Color Text = Color.Parse("#D4ECDA");
    public static readonly Color Text2 = Color.Parse("#A8D8C8");
    public static readonly Color Muted = Color.Parse("#8E8AB0");
    public static readonly Color Dim = Color.Parse("#6A6690");
    public static readonly Color WarnFrame = Color.Parse("#782878");
    public static readonly Color WarnText = Color.Parse("#F080E0");
    public static readonly Color WarnFill = Color.Parse("#200A24");
    public static readonly Color Track = Color.Parse("#2E4410");
    public static readonly Color Inactive = Color.Parse("#121A0C");
    public static readonly Color Hover = Color.Parse("#16240A");
    public static readonly Color Pressed = Color.Parse("#1E3008");

    public static IBrush B(Color c) => new SolidColorBrush(c);

    static FontFamily? _regular, _medium;
    // each weight by its own file: a folder URI groups the two files under one name and hands out Regular for both
    public static FontFamily Regular => _regular ??= new FontFamily("avares://XPiratezLauncher/Assets/Fonts/Roboto-Regular.ttf#Roboto");
    /// <summary>Headings and the main button (the spec asks for Roboto Condensed; Medium keeps the launcher small).</summary>
    public static FontFamily Medium => _medium ??= new FontFamily("avares://XPiratezLauncher/Assets/Fonts/Roboto-Medium.ttf#Roboto Medium");

    public static FluentTheme Fluent() => new()
    {
        Palettes =
        {
            [ThemeVariant.Dark] = new ColorPaletteResources
            {
                Accent = Accent,
                RegionColor = Bg,
                AltHigh = Bg,
                AltMediumHigh = Bg,
                AltMedium = Rail,
                AltMediumLow = Rail,
                AltLow = Rail,
                BaseHigh = Text,
                BaseMediumHigh = Text2,
                BaseMedium = Muted,
                BaseMediumLow = Dim,
                BaseLow = Track,
                ChromeAltLow = Text2,
                ChromeBlackHigh = Rail,
                ChromeBlackMedium = Rail,
                ChromeBlackMediumLow = Rail,
                ChromeBlackLow = Track,
                ChromeDisabledHigh = Track,
                ChromeDisabledLow = Dim,
                ChromeHigh = FrameInner,
                ChromeLow = Fill,
                ChromeMedium = Fill,
                ChromeMediumLow = Fill,
                ChromeWhite = Text,
                ListLow = Hover,
                ListMedium = Pressed,
                ErrorText = WarnText,
            },
        },
    };

    /// <summary>Fluent brushes the palette alone does not reach: buttons, inputs, lists.</summary>
    public static void AddResources(IResourceDictionary r)
    {
        void Set(string key, Color c) => r[key] = B(c);
        r["ControlCornerRadius"] = new CornerRadius(2);
        r["OverlayCornerRadius"] = new CornerRadius(3);

        Set("ButtonBackground", Colors.Transparent);
        Set("ButtonBackgroundPointerOver", Hover);
        Set("ButtonBackgroundPressed", Pressed);
        Set("ButtonBackgroundDisabled", Colors.Transparent);
        Set("ButtonBorderBrush", FrameInner);
        Set("ButtonBorderBrushPointerOver", Accent);
        Set("ButtonBorderBrushPressed", Accent);
        Set("ButtonBorderBrushDisabled", Track);
        Set("ButtonForeground", Text);
        Set("ButtonForegroundPointerOver", Text);
        Set("ButtonForegroundPressed", Text);
        Set("ButtonForegroundDisabled", Dim);

        foreach (var s in new[] { "", "PointerOver", "Focused" })
        {
            Set("TextControlBackground" + s, s == "Focused" ? Rail : Bg);
            Set("TextControlForeground" + s, Text);
        }
        Set("TextControlBorderBrush", Track);
        Set("TextControlBorderBrushPointerOver", FrameInner);
        Set("TextControlBorderBrushFocused", Accent);
        Set("TextControlBackgroundDisabled", Bg);
        Set("TextControlBorderBrushDisabled", Track);
        Set("TextControlForegroundDisabled", Muted);
        Set("TextControlPlaceholderForeground", Dim);
        Set("TextControlPlaceholderForegroundPointerOver", Dim);
        Set("TextControlPlaceholderForegroundFocused", Dim);
        Set("TextControlSelectionHighlightColor", Pressed);

        Set("ComboBoxBackground", Bg);
        Set("ComboBoxBackgroundPointerOver", Bg);
        Set("ComboBoxBackgroundPressed", Rail);
        Set("ComboBoxBackgroundDisabled", Bg);
        Set("ComboBoxBorderBrush", Track);
        Set("ComboBoxBorderBrushPointerOver", FrameInner);
        Set("ComboBoxBorderBrushPressed", Accent);
        Set("ComboBoxBorderBrushDisabled", Track);
        Set("ComboBoxForeground", Text);
        Set("ComboBoxForegroundDisabled", Muted);
        Set("ComboBoxDropDownBackground", Fill);
        Set("ComboBoxDropDownBorderBrush", FrameInner);
        Set("ComboBoxItemBackgroundPointerOver", Hover);
        Set("ComboBoxItemBackgroundSelected", Pressed);
        Set("ComboBoxItemBackgroundSelectedPointerOver", Pressed);
        Set("ComboBoxItemForegroundSelected", Text);

        Set("CheckBoxCheckBackgroundFillChecked", Accent);
        Set("CheckBoxCheckBackgroundFillCheckedPointerOver", AccentHover);
        Set("CheckBoxCheckBackgroundFillCheckedPressed", AccentPressed);
        Set("CheckBoxCheckBackgroundStrokeChecked", Accent);
        Set("CheckBoxCheckGlyphForegroundChecked", OnAccent);
        Set("CheckBoxCheckGlyphForegroundCheckedPointerOver", OnAccent);
        Set("CheckBoxCheckGlyphForegroundCheckedPressed", OnAccent);
        Set("CheckBoxCheckBackgroundStrokeUnchecked", FrameInner);
        Set("CheckBoxCheckBackgroundStrokeUncheckedPointerOver", Accent);

        Set("ProgressBarBackground", Track);
        Set("ProgressBarForeground", Accent);
        Set("ExpanderHeaderBackground", Fill);
        Set("ExpanderHeaderBackgroundPointerOver", Hover);
        Set("ExpanderHeaderBackgroundPressed", Pressed);
        Set("ExpanderHeaderBorderBrush", Track);
        Set("ExpanderHeaderBorderBrushPointerOver", FrameInner);
        Set("ExpanderContentBackground", Rail);
        Set("ExpanderContentBorderBrush", Track);
    }

    public static void AddStyles(Styles styles)
    {
        styles.Add(new Style(x => x.OfType<Window>())
        {
            Setters =
            {
                new Setter(TemplatedControl.BackgroundProperty, B(Bg)),
                new Setter(TemplatedControl.FontFamilyProperty, Regular),
                new Setter(TemplatedControl.FontSizeProperty, 14.0),
            },
        });
        // "primary": the lime button (main button, Send); "warn": rollback and failures; "ghost": framed secondary
        Look(styles, "primary", Accent, Accent, OnAccent, AccentHover, AccentHover, OnAccent, AccentPressed);
        Look(styles, "busy", Inactive, Track, Text2, Inactive, Track, Text2, Inactive);
        Look(styles, "warn", Colors.Transparent, WarnFrame, WarnText, WarnFill, WarnText, WarnText, WarnFill);
        Look(styles, "warnfill", WarnFill, WarnFrame, WarnText, WarnFill, WarnText, WarnText, WarnFill);
        Look(styles, "link", Colors.Transparent, Colors.Transparent, Accent, Colors.Transparent, Colors.Transparent, AccentHover, Colors.Transparent);
        Look(styles, "nav", Colors.Transparent, Colors.Transparent, Muted, Hover, Colors.Transparent, Text, Pressed);
        Look(styles, "chip", Colors.Transparent, Track, Text2, Hover, FrameInner, Text, Pressed);
        Look(styles, "card", Fill, FrameInner, Text, Hover, Accent, Text, Pressed);
        // selected states come after their base classes: the later style wins
        Look(styles, "nav.on", Hover, Accent, Text, Hover, Accent, Text, Pressed);
        Look(styles, "chip.on", Accent, Accent, OnAccent, AccentHover, AccentHover, OnAccent, AccentPressed);
        styles.Add(new Style(x => x.OfType<Button>().Class("link"))
        {
            Setters = { new Setter(TemplatedControl.PaddingProperty, new Thickness(0)), new Setter(TemplatedControl.BorderThicknessProperty, new Thickness(0)) },
        });
    }

    /// <summary>
    /// One button look: the button's own colours plus the template overrides for hover, press and
    /// disabled, which Fluent otherwise paints from its own resources.
    /// </summary>
    static void Look(Styles styles, string cls, Color bg, Color border, Color fg, Color hoverBg, Color hoverBorder, Color hoverFg, Color pressedBg)
    {
        Selector Btn(Selector? x)
        {
            var s = x.OfType<Button>();
            foreach (var c in cls.Split('.')) s = s.Class(c);
            return s;
        }
        styles.Add(new Style(x => Btn(x))
        {
            Setters =
            {
                new Setter(TemplatedControl.BackgroundProperty, B(bg)),
                new Setter(TemplatedControl.BorderBrushProperty, B(border)),
                new Setter(TemplatedControl.ForegroundProperty, B(fg)),
            },
        });
        foreach (var (state, b, br, f) in new[] { (":pointerover", hoverBg, hoverBorder, hoverFg), (":pressed", pressedBg, hoverBorder, hoverFg) })
            styles.Add(new Style(x => Btn(x).Class(state).Template().OfType<ContentPresenter>().Name("PART_ContentPresenter"))
            {
                Setters =
                {
                    new Setter(ContentPresenter.BackgroundProperty, B(b)),
                    new Setter(ContentPresenter.BorderBrushProperty, B(br)),
                    new Setter(ContentPresenter.ForegroundProperty, B(f)),
                },
            });
        bool filled = bg.A > 0;
        styles.Add(new Style(x => Btn(x).Class(":disabled").Template().OfType<ContentPresenter>().Name("PART_ContentPresenter"))
        {
            Setters =
            {
                new Setter(ContentPresenter.BackgroundProperty, B(filled ? Inactive : Colors.Transparent)),
                new Setter(ContentPresenter.BorderBrushProperty, B(filled || border.A > 0 ? Track : Colors.Transparent)),
                new Setter(ContentPresenter.ForegroundProperty, B(Dim)),
            },
        });
    }

    // ------------------------------------------------------------- building blocks

    /// <summary>A game window: dark green fill, the double frame of the geoscape windows.</summary>
    public static Border Panel(Control child, Thickness? padding = null) => new()
    {
        Background = B(Fill),
        BorderBrush = B(FrameOuter),
        BorderThickness = new Thickness(2),
        CornerRadius = new CornerRadius(3),
        Child = new Border
        {
            BorderBrush = B(FrameInner),
            BorderThickness = new Thickness(2),
            CornerRadius = new CornerRadius(1),
            Padding = padding ?? new Thickness(16),
            Child = child,
        },
    };

    public static TextBlock H1(string text) => new()
    {
        Text = text, FontFamily = Medium, FontWeight = FontWeight.Bold, FontSize = 28, Foreground = B(Text),
    };

    /// <summary>Small caps heading of a settings group.</summary>
    public static TextBlock H2(string text) => new()
    {
        Text = text.ToUpperInvariant(), FontFamily = Medium, FontSize = 13, LetterSpacing = 0.6, Foreground = B(Muted),
    };

    public static TextBlock Note(string text, double size = 13, Color? color = null) => new()
    {
        Text = text, FontSize = size, Foreground = B(color ?? Muted), TextWrapping = TextWrapping.Wrap, LineHeight = size * 1.45,
    };

    public static Button Btn(string text, string? cls = null, double height = 36)
    {
        var b = new Button
        {
            Content = text,
            MinHeight = height,
            Padding = new Thickness(14, 0),
            VerticalContentAlignment = VerticalAlignment.Center,
            FontSize = 13,
        };
        if (cls is not null) foreach (var c in cls.Split(' ')) b.Classes.Add(c);
        return b;
    }

    public static Button Link(string text, Action onClick, double size = 13)
    {
        var b = new Button { Content = new TextBlock { Text = text, TextDecorations = TextDecorations.Underline }, FontSize = size, Cursor = new Avalonia.Input.Cursor(Avalonia.Input.StandardCursorType.Hand) };
        b.Classes.Add("link");
        b.Click += (_, _) => onClick();
        return b;
    }

    /// <summary>A stroked 24x24 icon, drawn in the colour of the button it sits in.</summary>
    public static Path Icon(string data, Control? colourOf, double size = 20)
    {
        var p = new Path
        {
            Data = Geometry.Parse(data),
            Width = size, Height = size,
            Stretch = Stretch.Uniform,
            StrokeThickness = 1.8,
            StrokeLineCap = PenLineCap.Round,
            StrokeJoin = PenLineJoin.Round,
        };
        if (colourOf is not null) p[!Shape.StrokeProperty] = colourOf[!TemplatedControl.ForegroundProperty];
        return p;
    }

    public const string IconHome = "M3,10.5 L12,3 L21,10.5 L21,21 L15,21 L15,15 L9,15 L9,21 L3,21 Z";
    public const string IconReports = "M14,3 L5,3 L5,21 L19,21 L19,8 Z M14,3 L14,8 L19,8 M8,13 L16,13 M8,17 L13,17";
    public const string IconHeart = "M12,20 C12,20 5,15.6 5,10 C5,6.5 9.5,5 12,8 C14.5,5 19,6.5 19,10 C19,15.6 12,20 12,20 Z";
    public const string IconSettings = "M4,6 L13,6 M17,6 L20,6 M4,12 L7,12 M11,12 L20,12 M4,18 L15,18 M19,18 L20,18 M13,6 A2,2 0 1 1 17,6 A2,2 0 1 1 13,6 M7,12 A2,2 0 1 1 11,12 A2,2 0 1 1 7,12 M15,18 A2,2 0 1 1 19,18 A2,2 0 1 1 15,18";
    public const string IconGlobe = "M3,12 A9,9 0 1 1 21,12 A9,9 0 1 1 3,12 M3,12 L21,12 M12,3 C16,7 16,17 12,21 M12,3 C8,7 8,17 12,21";
    public const string IconDownload = "M12,4 L12,15 M7,10 L12,15 L17,10 M5,20 L19,20";
    public const string IconPlay = "M7,4 L19,12 L7,20 Z";
    public const string IconMessage = "M21,12 C21,16.4 17.4,20 13,20 C11.6,20 10.4,19.7 9.4,19.2 L4,21 L5.8,15.6 C5.3,14.5 5,13.3 5,12 C5,7.6 8.6,4 13,4 C17.4,4 21,7.6 21,12 Z";
    public const string IconCheck = "M3,12 A9,9 0 1 1 21,12 A9,9 0 1 1 3,12 M8,12.5 L11,15.5 L16,9.5";
    // дверь со стрелкой наружу: выйти из приложения
    public const string IconQuit = "M14,4 L5,4 L5,20 L14,20 M11,12 L20,12 M16,8 L20,12 L16,16";
}
