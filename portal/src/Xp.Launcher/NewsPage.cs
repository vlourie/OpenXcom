using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Documents;
using Avalonia.Layout;
using Avalonia.Media;
using Xp.Launcher.Core;
using Xp.Manifest;

namespace Xp.Launcher;

/// <summary>
/// Updates and plans: every update the channel has carried with its "What's new", newest first, and
/// the roadmap — what is being done and what comes next. Both come from the signed history of the
/// channel in the release repository (channels/&lt;channel&gt;.notes.json), the same file the site
/// shows, so the launcher and the site never tell a player different things. The history is kept on disk
/// (NotesCache): the page shows it at once and asks the server only after a new release, once a day or on "Reload".
/// </summary>
public sealed class NewsPage : UserControl
{
    static readonly TimeSpan Fresh = TimeSpan.FromMinutes(5);

    readonly Func<RepoClient?> _repo;
    readonly Func<string> _channel;
    readonly Func<NotesCache?> _cache;
    readonly Func<string?> _latest;
    readonly Button _historyTab, _roadmapTab, _reload;
    readonly StackPanel _body = new() { Spacing = 12 };
    readonly TextBlock _state = Skin.Note("", 13);
    readonly ScrollViewer _scroll;
    ChannelNotes? _notes;
    DateTime _loadedAt;
    /// <summary>The kept file's time when the page read it: the home page's "What's new" may have fetched a newer one since.</summary>
    DateTime _keptAt;
    bool _loading;
    bool _roadmap;

    /// <param name="latest">The release the channel points to, from the update check; null - not known yet.</param>
    public NewsPage(Func<RepoClient?> repo, Func<string> channel, Func<NotesCache?> cache, Func<string?> latest)
    {
        _repo = repo;
        _channel = channel;
        _cache = cache;
        _latest = latest;
        _historyTab = Skin.Btn(L.T("news.history"));
        _historyTab.Click += (_, _) => Show(roadmap: false);
        _roadmapTab = Skin.Btn(L.T("news.roadmap"));
        _roadmapTab.Click += (_, _) => Show(roadmap: true);
        _reload = Skin.Btn(L.T("news.reload"), "ghost");
        _reload.Click += async (_, _) => await LoadAsync(force: true);

        var tabs = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8 };
        tabs.Children.Add(_historyTab);
        tabs.Children.Add(_roadmapTab);
        tabs.Children.Add(_reload);

        var head = new StackPanel { Spacing = 12, Margin = new Thickness(28, 24, 28, 12) };
        head.Children.Add(Skin.H1(L.T("news.title")));
        head.Children.Add(Skin.Note(L.T("news.hint"), 14, Skin.Text2));
        head.Children.Add(tabs);
        head.Children.Add(_state);

        _body.MaxWidth = 900;
        _body.HorizontalAlignment = HorizontalAlignment.Left;
        _body.Margin = new Thickness(28, 0, 28, 28);
        _scroll = new ScrollViewer { Content = _body };

        var dock = new DockPanel();
        DockPanel.SetDock(head, Dock.Top);
        dock.Children.Add(head);
        dock.Children.Add(_scroll);
        Content = dock;
        Mark();
    }

    /// <summary>The page came on screen: the kept history at once, the server's when it is due.</summary>
    public async void Shown(bool roadmap)
    {
        Show(roadmap);
        await LoadAsync(force: false);
    }

    void Show(bool roadmap)
    {
        _roadmap = roadmap;
        Mark();
        Fill();
        _scroll.Offset = default;
    }

    void Mark()
    {
        _historyTab.Classes.Set("primary", !_roadmap);
        _roadmapTab.Classes.Set("primary", _roadmap);
    }

    async Task LoadAsync(bool force)
    {
        if (_loading) return;
        if (_repo() is not { } repo) { _state.Text = L.T("news.offline"); return; }
        var channel = _channel();
        var cache = _cache();
        if (cache is not null && !force)
        {
            var at = KeptAt(cache, channel);
            if (at != default && at != _keptAt && await Task.Run(() => cache.Load(repo, channel)) is { } kept)
            {
                _notes = kept;
                _keptAt = at;
                _state.Text = "";
                Fill();
            }
            if (_notes is not null && !cache.Due(channel, _latest(), DateTime.UtcNow)) return;
        }
        else if (!force && _notes is not null && DateTime.UtcNow - _loadedAt < Fresh) return;
        _loading = true;
        _reload.IsEnabled = false;
        if (_notes is null) _state.Text = L.T("news.loading");
        try
        {
            _notes = cache is not null
                ? await cache.FetchAsync(repo, channel, _latest(), CancellationToken.None)
                : await repo.GetNotesAsync(channel, CancellationToken.None);
            _loadedAt = DateTime.UtcNow;
            if (cache is not null) _keptAt = KeptAt(cache, channel);
            _state.Text = "";
        }
        catch (FileNotFoundException) { _state.Text = L.T("news.none"); }
        catch (Exception e) when (e is HttpRequestException or IOException or TrustException or TaskCanceledException or ArgumentException)
        {
            _state.Text = L.T("news.failed", e.Message);
        }
        finally
        {
            _loading = false;
            _reload.IsEnabled = true;
        }
        Fill();
    }

    static DateTime KeptAt(NotesCache cache, string channel)
    {
        try { return File.Exists(cache.FilePath(channel)) ? File.GetLastWriteTimeUtc(cache.FilePath(channel)) : default; }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or ArgumentException) { return default; }
    }

    void Fill()
    {
        _body.Children.Clear();
        if (_notes is null) return;
        if (_roadmap)
        {
            var text = NoteText.Pick(_notes.Roadmap, L.Language);
            if (text.Length == 0) { _body.Children.Add(Skin.Note(L.T("news.noRoadmap"), 14)); return; }
            var plan = new StackPanel { Spacing = 8 };
            AddBlocks(plan, text, roadmap: true);
            _body.Children.Add(Skin.Panel(plan, new Thickness(24, 20)));
            return;
        }
        if (_notes.Releases.Count == 0) { _body.Children.Add(Skin.Note(L.T("news.none"), 14)); return; }
        foreach (var r in _notes.Releases) _body.Children.Add(Entry(r));
    }

    static Control Entry(ReleaseNote r)
    {
        var box = new StackPanel { Spacing = 6 };
        var title = new TextBlock { FontFamily = Skin.Medium, FontSize = 18, Foreground = Skin.B(Skin.Text) };
        title.Inlines!.Add(new Run(r.Version));
        title.Inlines.Add(new Run("   " + r.Published.ToLocalTime().ToString("dd.MM.yyyy")) { FontSize = 13, Foreground = Skin.B(Skin.Muted), FontFamily = Skin.Regular });
        box.Children.Add(title);
        var text = NoteText.Pick(r.Changelog, L.Language);
        if (text.Trim().Length == 0) box.Children.Add(Skin.Note(L.T("news.empty"), 13, Skin.Dim));
        else AddBlocks(box, text, roadmap: false);
        return Skin.Panel(box, new Thickness(18, 14));
    }

    /// <summary>Headings, list items and paragraphs of the little Markdown the notes are written in.</summary>
    static void AddBlocks(StackPanel into, string text, bool roadmap)
    {
        foreach (var b in NoteText.Parse(text))
        {
            switch (b.Kind)
            {
                case NoteKind.Heading:
                    var h = Line(b.Text, b.Level <= 1 ? 22 : b.Level == 2 ? (roadmap ? 18 : 15) : 14, b.Level <= 2 ? Skin.Accent : Skin.Text);
                    h.FontFamily = Skin.Medium;
                    h.Margin = new Thickness(0, into.Children.Count == 0 ? 0 : b.Level <= 2 ? 12 : 6, 0, 0);
                    into.Children.Add(h);
                    break;
                case NoteKind.Bullet:
                    var row = new DockPanel { Margin = new Thickness(b.Level * 20, 0, 0, 0) };
                    var dot = new TextBlock { Text = "—", FontSize = 13, Foreground = Skin.B(Skin.Accent), Margin = new Thickness(0, 0, 10, 0) };
                    DockPanel.SetDock(dot, Dock.Left);
                    row.Children.Add(dot);
                    row.Children.Add(Line(b.Text, 13, Skin.Text2));
                    into.Children.Add(row);
                    break;
                default:
                    into.Children.Add(Line(b.Text, 13, Skin.Text2));
                    break;
            }
        }
    }

    static TextBlock Line(string text, double size, Color color)
    {
        var t = new TextBlock { FontSize = size, LineHeight = size * 1.45, Foreground = Skin.B(color), TextWrapping = TextWrapping.Wrap };
        foreach (var (run, bold) in NoteText.Runs(text))
        {
            var r = new Run(run);
            if (bold) { r.FontFamily = Skin.Medium; r.Foreground = Skin.B(Skin.Text); }
            t.Inlines!.Add(r);
        }
        return t;
    }
}
