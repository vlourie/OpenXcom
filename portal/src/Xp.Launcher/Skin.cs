using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Presenters;
using Avalonia.Controls.Primitives;
using Avalonia.Controls.Shapes;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Platform;
using Avalonia.Styling;
using Avalonia.Themes.Fluent;
using Path = Avalonia.Controls.Shapes.Path;

namespace Xp.Launcher;

/// <summary>
/// The launcher's look, variant A of docs/portal/VOICE_IRC.md §8: the familiar space-violet and acid-lime colours, flat
/// panels with no frames, corners of 8 px, the accent only on the main action. Everything is code: the launcher has no XAML.
/// Four kinds of button (class on the button): "primary" - the main one, at most one to a screen; none or "ghost" - the
/// ordinary one; "quiet" (also "nav", "link", "tab") - no fill; "warn" - the dangerous one. Each has hover, press, keyboard
/// focus (a ring) and disabled. No shadows, no blur: NativeAOT and a slow machine come before decoration.
/// </summary>
public static class Skin
{
    // ----- the table of VOICE_IRC.md §8
    public static readonly Color Bg = Color.Parse("#120A18");          // under the pages
    public static readonly Color Rail = Color.Parse("#0B0610");        // the left column of sections
    public static readonly Color Fill = Color.Parse("#170F20");        // panel: side columns, cards
    public static readonly Color Line = Color.Parse("#2C2138");        // dividers
    public static readonly Color Text = Color.Parse("#E4ECDF");
    public static readonly Color Text2 = Color.Parse("#B5C4B8");
    public static readonly Color Muted = Color.Parse("#8E86A6");       // captions, time
    public static readonly Color Accent = Color.Parse("#80D000");
    public static readonly Color OnAccent = Color.Parse("#0A1400");
    public static readonly Color Teal = Color.Parse("#00C8B8");
    public static readonly Color Selected = Color.Parse("#26183A");    // the chosen row, a mention
    public static readonly Color Field = Color.Parse("#0E0814");       // input fields
    public static readonly Color Button = Color.Parse("#261C33");      // the ordinary button

    // ----- states and what the table has no word for (every text pair is checked at 4.5:1, docs/portal/LAUNCHER_UI.md §9)
    public static readonly Color AccentHover = Color.Parse("#A8F030");
    public static readonly Color AccentPressed = Color.Parse("#6AB000");
    public static readonly Color ButtonHover = Color.Parse("#32243F");
    public static readonly Color ButtonPressed = Color.Parse("#1D1428");
    public static readonly Color Hover = Color.Parse("#1F1529");       // a quiet button or a list row under the pointer
    public static readonly Color Inactive = Color.Parse("#1C1426");    // fill of a disabled or busy button, a quiet row
    public static readonly Color Dim = Color.Parse("#8A829F");         // small remarks; 4.5:1 on every fill above
    public static readonly Color Disabled = Color.Parse("#6B6382");    // text of a disabled control (exempt from contrast)
    public static readonly Color Thumb = Color.Parse("#4A3C5E");       // scroll bar thumb
    public static readonly Color ThumbHover = Color.Parse("#6C5C86");
    public static readonly Color WarnText = Color.Parse("#F080E0");
    public static readonly Color WarnFill = Color.Parse("#2A1030");
    public static readonly Color WarnHover = Color.Parse("#3C1745");
    public static readonly Color WarnPressed = Color.Parse("#220C28");
    public static readonly Color AccentTint = Color.Parse("#1F2E10");  // a tag in the accent's family
    public static readonly Color TealTint = Color.Parse("#0B2A2A");
    // the old names: the frames are gone, what still asks for them gets the divider
    public static readonly Color FrameOuter = Line;
    public static readonly Color FrameInner = Line;
    public static readonly Color Track = Line;
    public static readonly Color Pressed = Selected;
    public static readonly Color WarnFrame = Color.Parse("#5A2A62");
    // the home card's picture: the indigo toning of the heroines' art and the glows over it
    public static readonly Color HeroTop = Color.Parse("#181868");
    public static readonly Color HeroBottom = Color.Parse("#180810");
    public const string HeroGlowA = "#8C185888";
    public const string HeroGlowB = "#CC181868";

    // ----- one measure for everything
    public const double RadiusPx = 8;
    public static readonly CornerRadius Radius = new(RadiusPx);
    public static readonly CornerRadius Pill = new(12);        // counters and tags
    public static readonly CornerRadius BarRadius = new(2);    // progress bars
    public const double ControlHeight = 36;                    // buttons, fields, drop-downs
    public const double IconSize = 20;                         // every rail and button icon
    public static readonly Thickness PanelPadding = new(16);

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
                BaseLow = Line,
                ChromeAltLow = Text2,
                ChromeBlackHigh = Rail,
                ChromeBlackMedium = Rail,
                ChromeBlackMediumLow = Rail,
                ChromeBlackLow = Line,
                ChromeDisabledHigh = Line,
                ChromeDisabledLow = Disabled,
                ChromeHigh = Line,
                ChromeLow = Fill,
                ChromeMedium = Fill,
                ChromeMediumLow = Fill,
                ChromeWhite = Text,
                ListLow = Hover,
                ListMedium = Selected,
                ErrorText = WarnText,
            },
        },
    };

    /// <summary>Fluent brushes the palette alone does not reach: buttons, inputs, lists, menus, tips, scroll bars.</summary>
    public static void AddResources(IResourceDictionary r)
    {
        void Set(string key, Color c) => r[key] = B(c);
        r["ControlCornerRadius"] = Radius;
        r["OverlayCornerRadius"] = Radius;
        r["ButtonBorderThemeThickness"] = new Thickness(2);   // a transparent ring that the keyboard focus lights up

        // the ordinary button; the other kinds are classes (AddStyles)
        Set("ButtonBackground", Button);
        Set("ButtonBackgroundPointerOver", ButtonHover);
        Set("ButtonBackgroundPressed", ButtonPressed);
        Set("ButtonBackgroundDisabled", Inactive);
        foreach (var s in new[] { "", "PointerOver", "Pressed", "Disabled" }) Set("ButtonBorderBrush" + s, Colors.Transparent);
        Set("ButtonForeground", Text);
        Set("ButtonForegroundPointerOver", Text);
        Set("ButtonForegroundPressed", Text);
        Set("ButtonForegroundDisabled", Disabled);

        // fields: a dark well in the panel, the border only when the pointer or the keyboard is on it
        r["TextControlBorderThemeThickness"] = new Thickness(1);
        r["TextControlBorderThemeThicknessFocused"] = new Thickness(1);
        foreach (var s in new[] { "", "PointerOver", "Focused", "Disabled" })
            Set("TextControlBackground" + s, Field);
        foreach (var s in new[] { "", "PointerOver", "Focused" }) Set("TextControlForeground" + s, Text);
        // a hairline keeps a field readable on the window colour, where the dark well alone nearly vanishes
        Set("TextControlBorderBrush", Line);
        Set("TextControlBorderBrushPointerOver", Thumb);
        Set("TextControlBorderBrushFocused", Accent);
        Set("TextControlBorderBrushDisabled", Line);
        Set("TextControlForegroundDisabled", Muted);
        Set("TextControlPlaceholderForeground", Dim);
        Set("TextControlPlaceholderForegroundPointerOver", Dim);
        Set("TextControlPlaceholderForegroundFocused", Dim);
        Set("TextControlSelectionHighlightColor", Selected);

        Set("ComboBoxBackground", Field);
        Set("ComboBoxBackgroundPointerOver", Field);
        Set("ComboBoxBackgroundPressed", Field);
        Set("ComboBoxBackgroundDisabled", Field);
        Set("ComboBoxBackgroundFocused", Field);
        Set("ComboBoxBackgroundFocusedPressed", Field);
        Set("ComboBoxBorderBrush", Line);
        Set("ComboBoxBorderBrushPointerOver", Thumb);
        Set("ComboBoxBorderBrushPressed", Accent);
        Set("ComboBoxBorderBrushFocused", Accent);
        Set("ComboBoxBorderBrushDisabled", Line);
        Set("ComboBoxForeground", Text);
        Set("ComboBoxForegroundDisabled", Muted);
        Set("ComboBoxDropDownBackground", Selected);
        Set("ComboBoxDropDownBorderBrush", Line);
        Set("ComboBoxItemBackgroundPointerOver", Hover);
        Set("ComboBoxItemBackgroundPressed", Hover);
        Set("ComboBoxItemBackgroundSelected", Fill);
        Set("ComboBoxItemBackgroundSelectedPointerOver", Hover);
        Set("ComboBoxItemBackgroundSelectedPressed", Hover);
        Set("ComboBoxItemForeground", Text);
        Set("ComboBoxItemForegroundPointerOver", Text);
        Set("ComboBoxItemForegroundSelected", Accent);
        Set("ComboBoxItemForegroundSelectedPointerOver", Accent);

        // context menus (the text boxes' cut / copy / paste) and flyouts
        foreach (var k in new[] { "MenuFlyoutPresenter", "ContextMenu", "MenuFlyout" })
        {
            Set(k + "Background", Selected);
            Set(k + "BorderBrush", Line);
        }
        Set("MenuFlyoutItemBackground", Colors.Transparent);
        Set("MenuFlyoutItemBackgroundPointerOver", Hover);
        Set("MenuFlyoutItemBackgroundPressed", Hover);
        Set("MenuFlyoutItemBackgroundDisabled", Colors.Transparent);
        Set("MenuFlyoutItemForeground", Text);
        Set("MenuFlyoutItemForegroundPointerOver", Text);
        Set("MenuFlyoutItemForegroundPressed", Text);
        Set("MenuFlyoutItemForegroundDisabled", Disabled);
        Set("MenuFlyoutSeparatorBackground", Line);

        // tips
        Set("ToolTipBackground", Selected);
        Set("ToolTipBorderBrush", Line);
        Set("ToolTipForeground", Text);
        r["ToolTipBorderThemePadding"] = new Thickness(10, 6);

        // scroll bars: thin, the thumb only
        Set("ScrollBarBackground", Colors.Transparent);
        Set("ScrollBarBackgroundPointerOver", Colors.Transparent);
        Set("ScrollBarTrackFill", Colors.Transparent);
        Set("ScrollBarTrackFillPointerOver", Colors.Transparent);
        Set("ScrollBarThumbFill", Thumb);
        Set("ScrollBarThumbFillPointerOver", ThumbHover);
        Set("ScrollBarThumbFillPressed", Muted);
        Set("ScrollBarThumbFillDisabled", Line);
        Set("ScrollBarPanningThumbBackground", Thumb);
        Set("ScrollBarBorderBrush", Colors.Transparent);

        // check boxes, radio buttons, sliders, tabs
        Set("CheckBoxCheckBackgroundFillUnchecked", Field);
        Set("CheckBoxCheckBackgroundFillUncheckedPointerOver", Field);
        Set("CheckBoxCheckBackgroundFillUncheckedPressed", Field);
        Set("CheckBoxCheckBackgroundFillChecked", Accent);
        Set("CheckBoxCheckBackgroundFillCheckedPointerOver", AccentHover);
        Set("CheckBoxCheckBackgroundFillCheckedPressed", AccentPressed);
        Set("CheckBoxCheckBackgroundStrokeChecked", Accent);
        Set("CheckBoxCheckBackgroundStrokeCheckedPointerOver", AccentHover);
        Set("CheckBoxCheckBackgroundStrokeCheckedPressed", AccentPressed);
        Set("CheckBoxCheckGlyphForegroundChecked", OnAccent);
        Set("CheckBoxCheckGlyphForegroundCheckedPointerOver", OnAccent);
        Set("CheckBoxCheckGlyphForegroundCheckedPressed", OnAccent);
        Set("CheckBoxCheckBackgroundStrokeUnchecked", Muted);
        Set("CheckBoxCheckBackgroundStrokeUncheckedPointerOver", Text2);
        Set("CheckBoxCheckBackgroundStrokeUncheckedPressed", Accent);
        Set("RadioButtonOuterEllipseStroke", Muted);
        Set("RadioButtonOuterEllipseStrokePointerOver", Text2);
        Set("RadioButtonOuterEllipseStrokePressed", Accent);
        Set("RadioButtonOuterEllipseFill", Field);
        Set("RadioButtonOuterEllipseFillPointerOver", Field);
        Set("RadioButtonOuterEllipseFillPressed", Field);
        Set("RadioButtonOuterEllipseCheckedFill", Accent);
        Set("RadioButtonOuterEllipseCheckedFillPointerOver", AccentHover);
        Set("RadioButtonOuterEllipseCheckedStroke", Accent);
        Set("RadioButtonOuterEllipseCheckedStrokePointerOver", AccentHover);
        Set("RadioButtonCheckGlyphFill", OnAccent);
        Set("RadioButtonCheckGlyphFillPointerOver", OnAccent);
        Set("RadioButtonCheckGlyphStroke", OnAccent);
        Set("RadioButtonCheckGlyphStrokePointerOver", OnAccent);
        Set("SliderTrackFill", Line);
        Set("SliderTrackFillPointerOver", Line);
        Set("SliderTrackValueFill", Accent);
        Set("SliderTrackValueFillPointerOver", AccentHover);
        Set("SliderThumbBackground", Accent);
        Set("SliderThumbBackgroundPointerOver", AccentHover);
        Set("SliderThumbBackgroundPressed", AccentPressed);
        Set("TabItemHeaderForegroundUnselected", Muted);
        Set("TabItemHeaderForegroundUnselectedPointerOver", Text2);
        Set("TabItemHeaderForegroundSelected", Text);
        Set("TabItemHeaderForegroundSelectedPointerOver", Text);
        Set("TabItemHeaderBackgroundUnselected", Colors.Transparent);
        Set("TabItemHeaderBackgroundSelected", Colors.Transparent);

        Set("ProgressBarBackground", Line);
        Set("ProgressBarForeground", Accent);
        Set("ExpanderHeaderBackground", Fill);
        Set("ExpanderHeaderBackgroundPointerOver", Hover);
        Set("ExpanderHeaderBackgroundPressed", Selected);
        Set("ExpanderHeaderBorderBrush", Fill);
        Set("ExpanderHeaderBorderBrushPointerOver", Hover);
        Set("ExpanderContentBackground", Fill);
        Set("ExpanderContentBorderBrush", Fill);
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
                // the same picture as the exe icon: tools/launcher_icon.py ico oxce_globe
                new Setter(Window.IconProperty, new WindowIcon(AssetLoader.Open(new Uri("avares://XPiratezLauncher/Assets/app.ico")))),
            },
        });
        // the button's keyboard-focus ring is its own rounded ring (Look), not Fluent's square adorner
        styles.Add(new Style(x => x.OfType<Button>()) { Setters = { new Setter(Control.FocusAdornerProperty, (ITemplate<Control>?)null) } });
        // fields and drop-downs are as tall as the ordinary button
        styles.Add(new Style(x => x.OfType<TextBox>()) { Setters = { new Setter(Layoutable.MinHeightProperty, ControlHeight), new Setter(TemplatedControl.PaddingProperty, new Thickness(10, 7)) } });
        styles.Add(new Style(x => x.OfType<ComboBox>()) { Setters = { new Setter(Layoutable.MinHeightProperty, ControlHeight) } });
        styles.Add(new Style(x => x.OfType<CheckBox>()) { Setters = { new Setter(TemplatedControl.CornerRadiusProperty, new CornerRadius(4)) } });
        styles.Add(new Style(x => x.OfType<ToolTip>())
        {
            Setters = { new Setter(TemplatedControl.CornerRadiusProperty, Radius), new Setter(TemplatedControl.FontSizeProperty, 13.0) },
        });

        //            class         fill          text    hover fill    hover text  pressed fill   disabled fill
        Look(styles, "primary", Accent, OnAccent, AccentHover, OnAccent, AccentPressed, Inactive);
        Look(styles, "busy", Inactive, Text2, Inactive, Text2, Inactive, Inactive);
        Look(styles, "warn", WarnFill, WarnText, WarnHover, WarnText, WarnPressed, Inactive);
        Look(styles, "warnfill", WarnFill, WarnText, WarnFill, WarnText, WarnFill, Inactive);
        Look(styles, "ghost", Button, Text, ButtonHover, Text, ButtonPressed, Inactive);
        Look(styles, "chip", Button, Text2, ButtonHover, Text, ButtonPressed, Inactive);
        Look(styles, "card", Fill, Text, Hover, Text, Selected, Inactive);
        Look(styles, "quiet", Colors.Transparent, Text2, Hover, Text, Selected, Colors.Transparent);
        Look(styles, "link", Colors.Transparent, Accent, Colors.Transparent, AccentHover, Colors.Transparent, Colors.Transparent);
        Look(styles, "nav", Colors.Transparent, Text2, Hover, Text, Selected, Colors.Transparent);
        Look(styles, "tab", Colors.Transparent, Text2, Hover, Text, Selected, Colors.Transparent);
        // selected states come after their base classes: the later style wins
        Look(styles, "nav.on", Accent, OnAccent, AccentHover, OnAccent, AccentPressed, Inactive);
        Look(styles, "chip.on", Selected, Accent, Selected, AccentHover, Selected, Inactive);
        Look(styles, "tab.on", Selected, Text, Selected, Text, Selected, Inactive);
        styles.Add(new Style(x => x.OfType<Button>().Class("link"))
        {
            Setters = { new Setter(TemplatedControl.PaddingProperty, new Thickness(0)), new Setter(TemplatedControl.BorderThicknessProperty, new Thickness(0)) },
        });

        // counters on the rail: accent on the dark rail, dark on the accent of the chosen section
        styles.Add(new Style(x => x.OfType<Border>().Class("badge"))
        {
            Setters = { new Setter(Border.BackgroundProperty, B(Accent)), new Setter(Border.CornerRadiusProperty, Pill) },
        });
        styles.Add(new Style(x => x.OfType<TextBlock>().Class("badgeText")) { Setters = { new Setter(TextBlock.ForegroundProperty, B(OnAccent)) } });
        styles.Add(new Style(x => x.OfType<Button>().Class("nav").Class("on").Descendant().OfType<Border>().Class("badge")) { Setters = { new Setter(Border.BackgroundProperty, B(OnAccent)) } });
        styles.Add(new Style(x => x.OfType<Button>().Class("nav").Class("on").Descendant().OfType<TextBlock>().Class("badgeText")) { Setters = { new Setter(TextBlock.ForegroundProperty, B(Accent)) } });
    }

    /// <summary>
    /// One button kind: its own colours, the template overrides for hover, press, keyboard focus and disabled (which Fluent
    /// otherwise paints from its own resources). The border is a transparent ring; only the keyboard focus colours it.
    /// </summary>
    static void Look(Styles styles, string cls, Color bg, Color fg, Color hoverBg, Color hoverFg, Color pressedBg, Color disabledBg)
    {
        Selector Btn(Selector? x)
        {
            var s = x.OfType<Button>();
            foreach (var c in cls.Split('.')) s = s.Class(c);
            return s;
        }
        Selector Presenter(Selector? x, string state) => Btn(x).Class(state).Template().OfType<ContentPresenter>().Name("PART_ContentPresenter");

        styles.Add(new Style(x => Btn(x))
        {
            Setters =
            {
                new Setter(TemplatedControl.BackgroundProperty, B(bg)),
                new Setter(TemplatedControl.BorderBrushProperty, B(Colors.Transparent)),
                new Setter(TemplatedControl.ForegroundProperty, B(fg)),
            },
        });
        foreach (var (state, b, f) in new[] { (":pointerover", hoverBg, hoverFg), (":pressed", pressedBg, hoverFg) })
        {
            styles.Add(new Style(x => Presenter(x, state))
            {
                Setters =
                {
                    new Setter(ContentPresenter.BackgroundProperty, B(b)),
                    new Setter(ContentPresenter.ForegroundProperty, B(f)),
                },
            });
            // the rail icons take the colour of the button itself, not of its presenter
            styles.Add(new Style(x => Btn(x).Class(state)) { Setters = { new Setter(TemplatedControl.ForegroundProperty, B(f)) } });
        }
        styles.Add(new Style(x => Presenter(x, ":focus-visible")) { Setters = { new Setter(ContentPresenter.BorderBrushProperty, B(Text)) } });
        styles.Add(new Style(x => Presenter(x, ":disabled"))
        {
            Setters =
            {
                new Setter(ContentPresenter.BackgroundProperty, B(disabledBg)),
                new Setter(ContentPresenter.BorderBrushProperty, B(Colors.Transparent)),
                new Setter(ContentPresenter.ForegroundProperty, B(Disabled)),
            },
        });
        styles.Add(new Style(x => Btn(x).Class(":disabled")) { Setters = { new Setter(TemplatedControl.ForegroundProperty, B(Disabled)) } });
    }

    // ------------------------------------------------------------- building blocks

    /// <summary>A flat panel: the panel colour, corners of 8, no frame.</summary>
    public static Border Panel(Control child, Thickness? padding = null) => new()
    {
        Background = B(Fill),
        CornerRadius = Radius,
        ClipToBounds = true,
        Padding = padding ?? PanelPadding,
        Child = child,
    };

    /// <summary>The counter on a rail button: a filled pill, restyled by the chosen button (AddStyles).</summary>
    public static Border Badge(TextBlock count)
    {
        count.FontSize = 12;
        count.FontFamily = Medium;
        count.Classes.Add("badgeText");
        var b = new Border { Padding = new Thickness(7, 1), IsVisible = false, VerticalAlignment = VerticalAlignment.Center, Child = count };
        b.Classes.Add("badge");
        return b;
    }

    /// <summary>A small coloured label (ticket stage, state).</summary>
    public static Border Tag(string text, Color bg, Color fg) => new()
    {
        Background = B(bg), CornerRadius = Pill, Padding = new Thickness(9, 2),
        Child = new TextBlock { Text = text, FontSize = 12, FontFamily = Medium, Foreground = B(fg) },
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

    public static Button Btn(string text, string? cls = null, double height = ControlHeight)
    {
        var b = new Button
        {
            Content = text,
            MinHeight = height,
            Padding = new Thickness(12, 0),
            HorizontalContentAlignment = HorizontalAlignment.Center,
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
    public static Path Icon(string data, Control? colourOf, double size = IconSize)
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
    // газетный лист: обновления и планы
    public const string IconNews = "M5,4 L19,4 L19,20 L5,20 Z M8,8 L16,8 M8,12 L16,12 M8,16 L13,16";
    public const string IconCheck ="M3,12 A9,9 0 1 1 21,12 A9,9 0 1 1 3,12 M8,12.5 L11,15.5 L16,9.5";
    // микрофон на стойке: голосовые комнаты
    public const string IconVoice = "M9,4 A3,3 0 0 1 15,4 L15,11 A3,3 0 0 1 9,11 Z M5,10 C5,14 8,17 12,17 C16,17 19,14 19,10 M12,17 L12,21 M8,21 L16,21";
    // дверь со стрелкой наружу: выйти из приложения
    public const string IconQuit = "M14,4 L5,4 L5,20 L14,20 M11,12 L20,12 M16,8 L20,12 L16,16";
}
