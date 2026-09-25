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
    /// The box a picture starts in, in points, until the page knows its own size. The box follows
    /// the WINDOW and never the picture: a floor shown as a field is four times wider than a single
    /// object, and a box that followed the frame would make the page jump under the hand and two
    /// frames in a row incomparable by eye. See <see cref="Box"/>.
    /// </summary>
    const int BoxW = 544, BoxH = 448;

    /// <summary>A send is a few hundred kilobytes of text: one client, one minute, no ceremony.</summary>
    static readonly HttpClient Http = new() { Timeout = TimeSpan.FromMinutes(1) };

    readonly Settings _settings;
    readonly Func<string?> _gameDir;

    readonly ComboBox _sets = new() { MinWidth = 220, FontSize = 13 };
    readonly TextBlock _status = new() { FontSize = 13, Foreground = Skin.B(Skin.Text2), TextWrapping = TextWrapping.Wrap };
    readonly TextBlock _position = new() { FontSize = 13, Foreground = Skin.B(Skin.Muted), VerticalAlignment = VerticalAlignment.Center };
    readonly TextBlock _caption = new() { FontSize = 13, Foreground = Skin.B(Skin.Muted), TextWrapping = TextWrapping.Wrap };
    // Stretch.None on purpose: any stretching here is done to PIXELS OF A SPRITE. Uniform would
    // shrink the picture by whatever fraction the window happens to leave, and rows of the frame
    // would drop out or double — the pack would then be judged by an artefact of the layout.
    readonly Image _left = new() { Stretch = Stretch.None };
    readonly Image _right = new() { Stretch = Stretch.None };
    readonly StackPanel _verdicts = new() { Orientation = Orientation.Horizontal, Spacing = 8 };
    readonly WrapPanel _reasons = new() { Orientation = Orientation.Horizontal };
    readonly TextBlock _done = new() { FontSize = 13, Foreground = Skin.B(Skin.Muted), VerticalAlignment = VerticalAlignment.Center };
    readonly TextBox _note = new() { AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, Height = 62, MaxLength = 2000, FontSize = 13 };
    readonly Button _send;
    readonly Dictionary<string, Button> _verdictButtons = new();
    readonly Dictionary<string, Button> _reasonButtons = new();

    Panel? _leftHost;
    (int W, int H, double Scaling) _drawnBox;

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
        SizeChanged += OnBoxChanged;

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

        var panes = new Grid { ColumnDefinitions = new ColumnDefinitions("*,16,*") };
        panes.Children.Add(Pane(_left, L.T("review.original"), out _leftHost));
        var right = Pane(_right, L.T("review.pack.side"), out _);
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

    /// <summary>
    /// One side: a caption, and under it all the room that is left. The picture is built to the size
    /// of that room, measured by the layout itself — guessing it from the sum of the paddings is how
    /// a picture ends up hanging over the frame it is supposed to sit in.
    /// </summary>
    static Control Pane(Image image, string title, out Panel host)
    {
        host = new Panel { ClipToBounds = true };
        host.Children.Add(image);
        var caption = new TextBlock
        {
            Text = title, FontSize = 12, Foreground = Skin.B(Skin.Muted),
            HorizontalAlignment = HorizontalAlignment.Center, Margin = new Thickness(0, 0, 0, 8),
        };
        var dock = new DockPanel();
        DockPanel.SetDock(caption, Dock.Top);
        dock.Children.Add(caption);
        dock.Children.Add(host);
        var pane = Skin.Panel(dock, new Thickness(12));
        pane.MinHeight = BoxH + 48;    // the pane keeps its place while a set is still being read
        return pane;
    }

    /// <summary>
    /// The window itself hands over the keys and tells about the screen. Hooked on attachment and
    /// not only when the page is opened: at the moment a page is chosen from code there may be no
    /// window over it yet, and then the arrows would never arrive.
    /// </summary>
    protected override void OnAttachedToVisualTree(VisualTreeAttachmentEventArgs e)
    {
        base.OnAttachedToVisualTree(e);
        Hook();
    }

    void Hook()
    {
        if (TopLevel.GetTopLevel(this) is not Window w) return;
        // tunnelling: otherwise the focused pack combo eats the arrows before the page sees them
        w.RemoveHandler(InputElement.KeyDownEvent, OnKey);
        w.AddHandler(InputElement.KeyDownEvent, OnKey, RoutingStrategies.Tunnel);
        // the window is resized and moved between screens of different scaling: the picture is
        // rebuilt only when the box really becomes another one, or laying out the new picture
        // would ask for a redraw of its own and the two would chase each other
        w.ScalingChanged -= OnBoxChanged;
        w.ScalingChanged += OnBoxChanged;
    }

    /// <summary>The page was opened: find the mods once, then show the pack list.</summary>
    public void Shown()
    {
        Hook();
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
        // the row of reasons keeps its place whatever the verdict. Made to appear and vanish, it
        // changed the height of everything under the pictures — and the pictures with it — at the
        // very moment a verdict was given, which is the moment one wants them to hold still
        var bad = frame?.Verdict == "bad";
        _reasons.IsEnabled = bad;
        _reasons.Opacity = bad ? 1 : 0.3;
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
            _drawnBox = Box();
            var (bw, bh, scaling) = _drawnBox;
            _left.Source = Bitmap(left.Fit(bw, bh, Review.Floor), scaling);
            _right.Source = Bitmap(right.Fit(bw, bh, Review.Floor), scaling);
        }
        catch (Exception e) when (e is ReviewException or PngException or IOException)
        {
            _status.Text = L.T("err.generic", e.Message);
        }
    }

    void OnBoxChanged(object? sender, EventArgs e)
    {
        if (Box() != _drawnBox) Draw();
    }

    /// <summary>
    /// The box for one picture, in pixels of the glass, and the screen's scaling next to it.
    /// A point is not a pixel: at 150 per cent one point is a pixel and a half, so a picture built
    /// in points is magnified by that fraction on its way to the screen — every second row of the
    /// sprite doubles while its neighbour does not, and the pack ends up judged by an artefact of
    /// the display. Building it in pixels instead costs nothing and shows more of the frame the
    /// finer the screen.
    /// </summary>
    (int W, int H, double Scaling) Box()
    {
        var scaling = TopLevel.GetTopLevel(this)?.RenderScaling ?? 1.0;
        var w = BoxW;
        var h = BoxH;
        // the room left for one picture, as the layout arranged it. Both sides of it come from the
        // window: the column is star-sized and the host fills what the caption leaves, so neither
        // depends on the picture — which is what keeps this from chasing its own tail
        if (_leftHost is { Bounds.Width: > 120, Bounds.Height: > 120 })
        {
            w = (int)_leftHost.Bounds.Width;
            h = (int)_leftHost.Bounds.Height;
        }
        return ((int)(w * scaling), (int)(h * scaling), scaling);
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
    /// The marks go to the site under the launcher's own key. Without a linked account there is
    /// nowhere to send them, and the file is saved instead — it is already the body of the request.
    /// Marks are never dropped after sending: a send that the site did not take must not cost an
    /// evening of work, and a repeat carries the same key, so nothing is counted twice.
    /// </summary>
    async Task SendAsync()
    {
        Commit();
        var envelope = ReviewStore.Envelope(ReviewStore.All());
        if (envelope.Packs.Count == 0) { _status.Text = L.T("review.nothing"); return; }

        if (Account() is { } account && Portal() is { } portal)
        {
            _send.IsEnabled = false;
            _status.Text = L.T("review.sending");
            try
            {
                var taken = await new PortalClient(Http, portal).SendReviewAsync(envelope, account.Token, SendKey(envelope), CancellationToken.None);
                _status.Text = L.T("review.sent", taken.Packs, taken.Frames);
            }
            catch (Exception e) when (e is PortalException or HttpRequestException or TaskCanceledException)
            {
                _status.Text = L.T("review.sendFailed", e.Message);
            }
            finally { _send.IsEnabled = true; }
            return;
        }

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
            await stream.WriteAsync(ReviewStore.Serialize(envelope));
            _status.Text = L.T("review.saved", file.Name);
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException)
        {
            _status.Text = L.T("err.generic", e.Message);
        }
    }

    DeviceAccount? Account() => new DeviceStore(Path.Combine(Settings.Dir, "device.json")).Load();

    Uri? Portal()
    {
        var url = _settings.PortalUrl ?? BuiltIn.Defaults.PortalUrl;
        return Uri.TryCreate(url, UriKind.Absolute, out var uri) ? uri : null;
    }

    /// <summary>
    /// The key of this send: the marks themselves, not the clock. Pressing "send" twice on the same
    /// marks is one send; a mark changed in between makes it a different one.
    /// </summary>
    static string SendKey(VerdictFile envelope)
    {
        var bytes = System.Text.Encoding.UTF8.GetBytes(string.Join('\n', envelope.Packs.Select(p =>
            $"{p.Section}/{p.Set}/{p.ModVersion}/" + string.Join(',', p.Frames.Select(f => $"{f.Frame}:{f.Hd}:{f.Verdict}:{string.Join('+', f.Reasons)}:{f.Note}")))));
        return Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(bytes))[..32].ToLowerInvariant();
    }

    /// <summary>
    /// Avalonia draws BGRA; our pictures are RGBA, so the two colour channels swap. The bitmap is
    /// given the screen's own dpi (96 is one point per pixel), which is what makes one pixel of the
    /// picture land on exactly one pixel of the glass instead of being stretched by the scaling.
    /// </summary>
    static WriteableBitmap Bitmap(Image32 picture, double scaling)
    {
        var dpi = 96 * scaling;
        var bmp = new WriteableBitmap(new PixelSize(picture.Width, picture.Height), new Vector(dpi, dpi), PixelFormat.Bgra8888, AlphaFormat.Unpremul);
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
