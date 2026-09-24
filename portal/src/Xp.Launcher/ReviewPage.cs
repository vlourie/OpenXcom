using Avalonia;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Interactivity;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Media.Imaging;
using Avalonia.Platform;
using Avalonia.Platform.Storage;
using Avalonia.Threading;
using Xp.Launcher.Core;

namespace Xp.Launcher;

/// <summary>
/// Reviewing an HD pack: the original the game draws without the pack, next to the picture from the
/// pack, frame by frame. A floor is shown as a field of map cells and never as a single diamond —
/// one tile can look fine while the field of it is a lattice. Marks stay on this machine until they
/// are sent, so an evening of work survives closing the launcher.
/// </summary>
public sealed class ReviewPage : UserControl
{
    /// <summary>
    /// The box a picture is shown in, in points. Fixed for every frame: a floor shown as a field is
    /// four times wider than a single object, and a box that follows the picture makes the page jump
    /// under the hand and two frames in a row incomparable by eye.
    /// </summary>
    const int BoxW = 544, BoxH = 448;

    readonly Settings _settings;
    readonly Func<string?> _gameDir;

    readonly ComboBox _sets = new() { MinWidth = 220, FontSize = 13 };
    readonly TextBlock _status = new() { FontSize = 13, Foreground = Skin.B(Skin.Text2), TextWrapping = TextWrapping.Wrap };
    readonly TextBlock _position = new() { FontSize = 13, Foreground = Skin.B(Skin.Muted), VerticalAlignment = VerticalAlignment.Center };
    readonly TextBlock _caption = new() { FontSize = 13, Foreground = Skin.B(Skin.Muted), TextWrapping = TextWrapping.Wrap };
    readonly Image _left = new() { Stretch = Stretch.Uniform, StretchDirection = StretchDirection.DownOnly };
    readonly Image _right = new() { Stretch = Stretch.Uniform, StretchDirection = StretchDirection.DownOnly };
    readonly StackPanel _verdicts = new() { Orientation = Orientation.Horizontal, Spacing = 8 };
    readonly WrapPanel _reasons = new() { Orientation = Orientation.Horizontal };
    readonly TextBlock _done = new() { FontSize = 13, Foreground = Skin.B(Skin.Muted), VerticalAlignment = VerticalAlignment.Center };
    readonly TextBox _note = new() { AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, Height = 62, MaxLength = 2000, FontSize = 13 };
    readonly Button _send;
    readonly Dictionary<string, Button> _verdictButtons = new();
    readonly Dictionary<string, Button> _reasonButtons = new();

    string? _data, _mod;
    Rgb[]? _palette;
    ReviewPlan? _plan;
    HdPack? _pack;
    SpriteSet? _sprites;
    int _at;
    bool _loading, _filled;

    /// <summary>The verdicts a person has made: the rail shows the count, like the reports one.</summary>
    public event Action? Changed;

    public ReviewPage(Settings settings, Func<string?> gameDir)
    {
        _settings = settings;
        _gameDir = gameDir;

        _sets.SelectionChanged += (_, _) => { if (!_loading) LoadSet(); };
        _send = Skin.Btn(L.T("review.send"), "primary", 40);
        _send.FontFamily = Skin.Medium;
        _send.FontSize = 14;
        _send.Click += async (_, _) => await SendAsync();
        // the button stays on the page always: hidden until the first verdict, it looked as if there were none
        _note.Watermark = L.T("review.note");
        _note.LostFocus += (_, _) => Commit();
        // the page is driven from the keyboard; Esc is the way out of the box back to the arrows
        _note.KeyDown += (_, e) =>
        {
            if (e.Key is not Key.Escape) return;
            Commit();
            Focus();
            e.Handled = true;
        };
        Focusable = true;

        foreach (var (verdict, key) in new[] { ("ok", "review.ok"), ("bad", "review.bad"), ("doubt", "review.doubt"), ("", "review.clear") })
        {
            var b = Skin.Btn(L.T(key), "chip");
            b.Click += (_, _) => Mark(verdict);
            _verdictButtons[verdict] = b;
            _verdicts.Children.Add(b);
        }
        foreach (var reason in Review.Reasons)
        {
            var b = Skin.Btn(L.T("review.reason." + reason), "chip", 32);
            b.Margin = new Thickness(0, 0, 8, 8);
            b.Click += (_, _) => { Reason(reason, !(Current?.Reasons.Contains(reason) ?? false)); Draw(); };
            _reasonButtons[reason] = b;
            _reasons.Children.Add(b);
        }

        var head = new DockPanel();
        DockPanel.SetDock(_send, Dock.Right);
        DockPanel.SetDock(_done, Dock.Right);
        _done.Margin = new Thickness(0, 0, 16, 0);
        head.Children.Add(_send);
        head.Children.Add(_done);
        head.Children.Add(Skin.H1(L.T("review.title")));

        var pick = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 10 };
        pick.Children.Add(new TextBlock { Text = L.T("review.pack"), FontSize = 13, Foreground = Skin.B(Skin.Muted), VerticalAlignment = VerticalAlignment.Center });
        pick.Children.Add(_sets);
        pick.Children.Add(_position);

        var top = new StackPanel { Spacing = 10, Margin = new Thickness(0, 0, 0, 14) };
        top.Children.Add(head);
        top.Children.Add(Skin.Note(L.T("review.hint")));
        top.Children.Add(pick);
        top.Children.Add(_status);

        // nearest neighbour on both sides: a smoothed original would be judged instead of the pack
        RenderOptions.SetBitmapInterpolationMode(_left, BitmapInterpolationMode.None);
        RenderOptions.SetBitmapInterpolationMode(_right, BitmapInterpolationMode.None);

        var panes = new Grid { ColumnDefinitions = new ColumnDefinitions("*,16,*"), VerticalAlignment = VerticalAlignment.Center };
        panes.Children.Add(Pane(_left, L.T("review.original")));
        var right = Pane(_right, L.T("review.pack.side"));
        Grid.SetColumn(right, 2);
        panes.Children.Add(right);

        var bottom = new StackPanel { Spacing = 10, Margin = new Thickness(0, 14, 0, 0) };
        bottom.Children.Add(_caption);
        bottom.Children.Add(_verdicts);
        bottom.Children.Add(_reasons);
        bottom.Children.Add(_note);
        bottom.Children.Add(Skin.Note(L.T("review.keys"), 12));

        var root = new DockPanel { Margin = new Thickness(28, 24, 28, 24) };
        DockPanel.SetDock(top, Dock.Top);
        DockPanel.SetDock(bottom, Dock.Bottom);
        root.Children.Add(top);
        root.Children.Add(bottom);
        root.Children.Add(panes);
        Content = root;
    }

    static Control Pane(Image image, string title)
    {
        var stack = new StackPanel { Spacing = 8 };
        stack.Children.Add(new TextBlock { Text = title, FontSize = 12, Foreground = Skin.B(Skin.Muted), HorizontalAlignment = HorizontalAlignment.Center });
        stack.Children.Add(image);
        var pane = Skin.Panel(stack, new Thickness(12));
        pane.MinHeight = BoxH + 48;    // the pane keeps its place while a set is still being read
        return pane;
    }

    /// <summary>The page was opened: find the mods once, then show the pack list.</summary>
    public void Shown()
    {
        if (TopLevel.GetTopLevel(this) is Window w)
        {
            // tunnelling: otherwise the focused pack combo eats the arrows before the page sees them
            w.RemoveHandler(InputElement.KeyDownEvent, OnKey);
            w.AddHandler(InputElement.KeyDownEvent, OnKey, RoutingStrategies.Tunnel);
        }
        // the page takes the keyboard itself: otherwise the first arrow lands in the description box
        Dispatcher.UIThread.Post(() => Focus());
        if (_filled) return;
        // filled only once it worked: the game folder may still be opening when the page first shows
        var dir = _gameDir();
        if (dir is null) { _status.Text = L.T("review.noGame"); return; }
        (_data, _mod) = Review.FindMods(dir);
        if (_data is null || _mod is null) { _status.Text = L.T("review.noPack"); return; }

        List<string> sets;
        try
        {
            _palette = Review.FindPalette(_data);
            sets = Review.SetsWithPack(_mod, "TERRAIN");
        }
        catch (Exception e) when (e is ReviewException or IOException or UnauthorizedAccessException)
        {
            _status.Text = L.T("err.generic", e.Message);
            return;
        }
        if (sets.Count == 0) { _status.Text = L.T("review.noPack"); return; }

        _filled = true;
        _loading = true;
        _sets.ItemsSource = sets;
        _sets.SelectedIndex = 0;
        _loading = false;
        LoadSet();
    }

    async void LoadSet()
    {
        if (_sets.SelectedItem is not string set || _data is null || _mod is null || _palette is null) return;
        Commit();
        _status.Text = L.T("review.reading", set);
        _left.Source = _right.Source = null;
        _pack?.Dispose();
        _pack = null;
        _plan = null;

        string data = _data, mod = _mod;
        var palette = _palette;
        try
        {
            var (plan, pack, sprites) = await Task.Run(() =>
            {
                var p = new HdPack(mod, "TERRAIN", set);
                var built = Review.Build(data, "TERRAIN", set, p, palette);
                built.ModVersion = ModInfo.Version(mod);
                // the set is read once per pack, not once per frame: a big PCK is megabytes
                return (built, p, Pck.ReadSet(Pck.Find(Path.Combine(data, "TERRAIN"), set)!));
            });
            _plan = plan;
            _pack = pack;
            _sprites = sprites;
        }
        catch (Exception e) when (e is ReviewException or PngException or IOException or UnauthorizedAccessException)
        {
            _status.Text = L.T("err.generic", e.Message);
            return;
        }

        var back = ReviewStore.Restore(_plan, ReviewStore.Load(_plan.Section, _plan.Set));
        _status.Text = L.T("review.loaded", _plan.Frames.Count, _plan.Orphans, _plan.Skipped.Count) +
                       (back > 0 ? " " + L.T("review.restored", back) : "");
        _at = 0;
        Draw();
    }

    void Draw()
    {
        var frame = Current;
        _position.Text = _plan is null || frame is null ? "" : L.T("review.position", _at + 1, _plan.Frames.Count);
        _done.Text = _plan is null ? "" : L.T("review.marked", _plan.Frames.Count(f => f.Verdict.Length > 0), _plan.Frames.Count);
        _send.IsEnabled = ReviewStore.All().Sum(p => p.Frames.Count) > 0;
        _note.IsEnabled = frame is not null;
        _note.Text = frame?.Note ?? "";
        foreach (var (verdict, b) in _verdictButtons) b.Classes.Set("on", frame is not null && frame.Verdict == verdict && verdict.Length > 0);
        _reasons.IsVisible = frame?.Verdict == "bad";
        foreach (var (reason, b) in _reasonButtons) b.Classes.Set("on", frame?.Reasons.Contains(reason) == true);
        if (frame is null || _pack is null || _plan is null || _data is null || _palette is null || _sprites is null) return;

        var kind = frame.Ground ? "ground" : frame.Type switch { Pck.WestWallType or Pck.NorthWallType => "wall", Pck.FloorType => "floor", _ => "object" };
        _caption.Text = L.T("review.caption", frame.Frame, frame.Error < 0 ? "—" : frame.Error.ToString("0.0"), L.T("review.kind." + kind)) +
                        (frame.Variants > 0 ? " " + L.T("review.variants", frame.Variants) : "");

        try
        {
            var sprites = _sprites;
            var original = Image32.FromIndices(sprites.Frames[frame.Frame]!, sprites.Width, sprites.Height, _palette);
            var hd = Image32.FromPng(_pack.Frame(frame.Frame).Png!);
            var k = Math.Max(1, hd.Width / sprites.Width);
            var big = original.ScaleNearest(k);
            Image32 left, right;
            if (frame.Ground)
            {
                left = big.Field(4, k).OnFloor(Review.Floor, 0);
                right = hd.Field(4, k).OnFloor(Review.Floor, 0);
            }
            else
            {
                left = big.OnFloor(Review.Floor);
                right = hd.OnFloor(Review.Floor);
            }
            // both sides into the same fixed box: a single sprite at k=1 is 32x40 and nothing is
            // visible in it, a field of a floor is 512 wide, and the two must still look like a pair
            _left.Source = Bitmap(left.Fit(BoxW, BoxH, Review.Floor));
            _right.Source = Bitmap(right.Fit(BoxW, BoxH, Review.Floor));
        }
        catch (Exception e) when (e is ReviewException or PngException or IOException)
        {
            _status.Text = L.T("err.generic", e.Message);
        }
    }

    ReviewFrame? Current => _plan is not null && _at >= 0 && _at < _plan.Frames.Count ? _plan.Frames[_at] : null;

    void Go(int delta)
    {
        if (_plan is null || _plan.Frames.Count == 0) return;
        Commit();
        _at = Math.Clamp(_at + delta, 0, _plan.Frames.Count - 1);
        Draw();
    }

    /// <summary>What is typed in the box belongs to the frame on screen: put it there before anything moves.</summary>
    void Commit()
    {
        if (Current is not { } frame) return;
        var text = (_note.Text ?? "").Trim();
        if (text == frame.Note) return;
        frame.Note = text;
        Save();
    }

    void Mark(string verdict)
    {
        if (Current is not { } frame || _plan is null) return;
        Commit();
        frame.Verdict = verdict;
        if (verdict != "bad") frame.Reasons.Clear();
        Save();
        if (verdict.Length > 0 && verdict != "bad" && _at < _plan.Frames.Count - 1) _at++;    // a judged frame steps on by itself
        Draw();
    }

    void Reason(string reason, bool on)
    {
        if (Current is not { } frame) return;
        frame.Reasons.Remove(reason);
        if (on) frame.Reasons.Add(reason);
        Save();
    }

    void Save()
    {
        if (_plan is null) return;
        try { ReviewStore.Save(_plan); }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { _status.Text = L.T("err.generic", e.Message); }
        Changed?.Invoke();
    }

    void OnKey(object? sender, KeyEventArgs e)
    {
        if (!IsVisible || _plan is null) return;
        // while the description is being typed, 1 2 3 are digits and the arrows move the caret
        if (TopLevel.GetTopLevel(this)?.FocusManager?.GetFocusedElement() is TextBox) return;
        switch (e.Key)
        {
            case Key.Left or Key.PageUp: Go(-1); break;
            case Key.Right or Key.PageDown or Key.Space: Go(1); break;
            case Key.D1 or Key.NumPad1: Mark("ok"); break;
            case Key.D2 or Key.NumPad2: Mark("bad"); break;
            case Key.D3 or Key.NumPad3: Mark("doubt"); break;
            case Key.D0 or Key.NumPad0: Mark(""); break;
            case Key.Q or Key.W or Key.E or Key.R or Key.T or Key.Y:
                var i = Array.IndexOf(new[] { Key.Q, Key.W, Key.E, Key.R, Key.T, Key.Y }, e.Key);
                if (Current is { Verdict: "bad" } f && i < Review.Reasons.Length)
                {
                    var reason = Review.Reasons[i];
                    Reason(reason, !f.Reasons.Contains(reason));
                    Draw();
                }
                break;
            default: return;
        }
        e.Handled = true;
    }

    /// <summary>
    /// Until an account is linked to the launcher there is nowhere to send this: the file is saved,
    /// and it is already the body of the request the site will take.
    /// </summary>
    async Task SendAsync()
    {
        Commit();
        if (TopLevel.GetTopLevel(this) is not { } top) return;
        var file = await top.StorageProvider.SaveFilePickerAsync(new FilePickerSaveOptions
        {
            Title = L.T("review.send"),
            SuggestedFileName = "verdicts.json",
            DefaultExtension = "json",
        });
        if (file is null) return;
        try
        {
            await using var stream = await file.OpenWriteAsync();
            await stream.WriteAsync(ReviewStore.Serialize(ReviewStore.Envelope(ReviewStore.All())));
            _status.Text = L.T("review.saved", file.Name);
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException)
        {
            _status.Text = L.T("err.generic", e.Message);
        }
    }

    /// <summary>Avalonia draws BGRA; our pictures are RGBA, so the two colour channels swap.</summary>
    static WriteableBitmap Bitmap(Image32 picture)
    {
        var bmp = new WriteableBitmap(new PixelSize(picture.Width, picture.Height), new Vector(96, 96), PixelFormat.Bgra8888, AlphaFormat.Unpremul);
        using var buffer = bmp.Lock();
        var row = new byte[picture.Width * 4];
        for (var y = 0; y < picture.Height; y++)
        {
            for (var x = 0; x < picture.Width; x++)
            {
                var s = (y * picture.Width + x) * 4;
                row[x * 4] = picture.Rgba[s + 2];
                row[x * 4 + 1] = picture.Rgba[s + 1];
                row[x * 4 + 2] = picture.Rgba[s];
                row[x * 4 + 3] = picture.Rgba[s + 3];
            }
            System.Runtime.InteropServices.Marshal.Copy(row, 0, buffer.Address + y * buffer.RowBytes, row.Length);
        }
        return bmp;
    }
}
