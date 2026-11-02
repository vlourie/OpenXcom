using Avalonia;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Threading;
using Xp.Launcher.Core;

namespace Xp.Launcher;

/// <summary>
/// Private messages (ticket XP-000476), the "Messages" tab of the chat page: the conversations of the linked account,
/// one dialogue as a feed, a reply, a new message to a friend or by name, block and complaint. The same mailbox as the
/// site's /me/messages; the site owns every rule (limits, blocks, length) and this page shows the reason it gives.
/// Text is text: a message is drawn as it was typed, nothing in it is a link or markup.
/// </summary>
public sealed class MessagesPage : UserControl
{
    static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(30) };

    readonly Settings _settings;
    readonly DeviceStore _store = new(Path.Combine(Settings.Dir, "device.json"));
    readonly MessageWatch _watch = new();
    readonly DispatcherTimer _beat = new() { Interval = TimeSpan.FromSeconds(30) };

    readonly TextBlock _status = new() { FontSize = 13, TextWrapping = TextWrapping.Wrap, IsVisible = false };
    readonly StackPanel _list = new() { Spacing = 6 };
    readonly StackPanel _right = new() { Spacing = 10 };

    // the open dialogue
    readonly StackPanel _threadBox = new() { Spacing = 10, IsVisible = false };
    readonly TextBlock _who = new() { FontFamily = Skin.Medium, FontSize = 20, TextWrapping = TextWrapping.Wrap };
    readonly Button _block, _complain;
    readonly StackPanel _feed = new() { Spacing = 8 };
    readonly ScrollViewer _scroll;
    readonly TextBlock _blockedNote = Skin.Note(L.T("msgs.youBlocked"), 13, Skin.WarnText);
    readonly TextBox _reply = new() { AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, MinHeight = 70, MaxLength = MessageRules.BodyMax, FontSize = 14, Watermark = L.T("msgs.replyHint") };
    readonly Button _send;
    readonly Button _older;
    readonly StackPanel _replyBox = new() { Spacing = 8 };

    // a new message
    readonly StackPanel _composeBox = new() { Spacing = 10, IsVisible = false };
    readonly TextBox _to = new() { FontSize = 14, MaxLength = 256 };
    readonly TextBox _text = new() { AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, MinHeight = 110, MaxLength = MessageRules.BodyMax, FontSize = 14 };
    readonly WrapPanel _friends = new() { Orientation = Orientation.Horizontal };
    readonly TextBlock _friendsNote = Skin.Note(L.T("msgs.noFriends"));
    bool _friendsLoaded;

    List<MessageDialogue> _dialogues = [];
    Guid? _current;
    string _currentName = "";
    readonly List<MessageBubble> _bubbles = [];
    int _total, _pages;
    bool _iBlocked, _busy, _inboxBusy, _threadBusy;

    /// <summary>The count of unread messages changed (the rail counter and the home notice follow it).</summary>
    public event Action? UnreadChanged;
    public int Unread => _watch.Unread;
    public bool Linked => _store.Load() is not null;

    public MessagesPage(Settings settings)
    {
        _settings = settings;

        // --- left: the conversations
        var newMessage = Skin.Btn(L.T("msgs.new"), "primary");
        newMessage.Click += async (_, _) => await StartComposeAsync();
        var refresh = Skin.Btn(L.T("voice.refresh"), "ghost");
        refresh.Click += async (_, _) => { await LoadInboxAsync(); if (_current is not null) await LoadThreadAsync(merge: true); };
        var site = Skin.Link(L.T("msgs.site") + "  ↗", () => { if (SiteUrl() is { } u) ReportWindow.OpenUrl(u); });
        site.VerticalAlignment = VerticalAlignment.Center;
        var actions = new WrapPanel { Orientation = Orientation.Horizontal };
        newMessage.Margin = new Thickness(0, 0, 10, 6);
        refresh.Margin = new Thickness(0, 0, 10, 6);
        actions.Children.Add(newMessage);
        actions.Children.Add(refresh);
        actions.Children.Add(site);
        var left = new StackPanel { Spacing = 10 };
        left.Children.Add(actions);
        left.Children.Add(Skin.H2(L.T("msgs.inbox")));
        left.Children.Add(_list);

        // --- right: the dialogue
        _block = Skin.Btn(L.T("msgs.block"), "ghost");
        _block.Click += async (_, _) => await BlockAsync();
        _complain = Skin.Btn(L.T("msgs.complain"), "ghost");
        _complain.Click += async (_, _) => await ComplainAsync();
        var buttons = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8, VerticalAlignment = VerticalAlignment.Center };
        buttons.Children.Add(_block);
        buttons.Children.Add(_complain);
        var head = new DockPanel();
        DockPanel.SetDock(buttons, Dock.Right);
        head.Children.Add(buttons);
        head.Children.Add(_who);
        _older = Skin.Btn("", "ghost");
        _older.HorizontalAlignment = HorizontalAlignment.Center;
        _older.Click += async (_, _) => await LoadOlderAsync();
        var feedBox = new StackPanel { Spacing = 8 };
        feedBox.Children.Add(_older);
        feedBox.Children.Add(_feed);
        _scroll = new ScrollViewer { Content = feedBox, MaxHeight = 440, HorizontalScrollBarVisibility = Avalonia.Controls.Primitives.ScrollBarVisibility.Disabled };
        _send = Skin.Btn(L.T("msgs.send"), "primary");
        _send.HorizontalAlignment = HorizontalAlignment.Right;
        _send.Click += async (_, _) => await SendReplyAsync();
        // Ctrl+Enter sends; the box itself keeps Enter for a new line (tunnelled: the TextBox would take the key first)
        _reply.AddHandler(KeyDownEvent, async (object? _, KeyEventArgs e) =>
        {
            if (e.Key == Key.Enter && e.KeyModifiers.HasFlag(KeyModifiers.Control)) { e.Handled = true; await SendReplyAsync(); }
        }, Avalonia.Interactivity.RoutingStrategies.Tunnel);
        _replyBox.Children.Add(_blockedNote);
        _replyBox.Children.Add(_reply);
        _replyBox.Children.Add(_send);
        _threadBox.Children.Add(head);
        _threadBox.Children.Add(_scroll);
        _threadBox.Children.Add(_replyBox);

        // --- right: a new message
        var cancel = Skin.Btn(L.T("cancel"), "ghost");
        cancel.Click += (_, _) => { _composeBox.IsVisible = false; Pick(); };
        var sendNew = Skin.Btn(L.T("msgs.send"), "primary");
        sendNew.Click += async (_, _) => await SendNewAsync();
        var row = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8, HorizontalAlignment = HorizontalAlignment.Right };
        row.Children.Add(cancel);
        row.Children.Add(sendNew);
        _composeBox.Children.Add(Skin.H2(L.T("msgs.new")));
        _composeBox.Children.Add(new TextBlock { Text = L.T("msgs.to"), FontSize = 13 });
        _composeBox.Children.Add(_to);
        _composeBox.Children.Add(Skin.H2(L.T("msgs.friends")));
        _composeBox.Children.Add(_friendsNote);
        _composeBox.Children.Add(_friends);
        _composeBox.Children.Add(new TextBlock { Text = L.T("msgs.text"), FontSize = 13 });
        _composeBox.Children.Add(_text);
        _composeBox.Children.Add(Skin.Note(L.T("msgs.newHint", MessageRules.BodyMax)));
        _composeBox.Children.Add(row);

        var pick = Skin.Note(L.T("msgs.pick"));
        pick.Name = "pick";
        _right.Children.Add(pick);
        _right.Children.Add(_threadBox);
        _right.Children.Add(_composeBox);

        var columns = new Grid { ColumnDefinitions = new ColumnDefinitions("320,20,*") };
        columns.Children.Add(left);
        var rightPanel = Skin.Panel(_right);
        rightPanel.VerticalAlignment = VerticalAlignment.Top;
        Grid.SetColumn(rightPanel, 2);
        columns.Children.Add(rightPanel);

        var body = new StackPanel { Spacing = 12 };
        body.Children.Add(Skin.Note(L.T("msgs.hint"), 14, Skin.Text2));
        body.Children.Add(_status);
        body.Children.Add(columns);
        Content = body;

        _beat.Tick += async (_, _) => await BeatAsync();
        _beat.Start();
    }

    // ------------------------------------------------------------------ the site, the account

    Uri? Portal()
    {
        var url = _settings.PortalUrl ?? BuiltIn.Defaults.PortalUrl;
        return Uri.TryCreate(url, UriKind.Absolute, out var uri) ? uri : null;
    }

    string? SiteUrl()
    {
        if (Portal() is not { } p) return null;
        var root = p.AbsoluteUri.TrimEnd('/') + "/me/messages";
        return _current is { } id && _threadBox.IsVisible ? $"{root}/{id}" : root;
    }

    Window? Owner() => TopLevel.GetTopLevel(this) as Window;

    void Status(string? text, bool warn = true)
    {
        _status.IsVisible = text is not null;
        _status.Text = text ?? "";
        _status.Foreground = Skin.B(warn ? Skin.WarnText : Skin.Text2);
    }

    static string Reason(Exception e) => e switch
    {
        PortalException p when p.Status == 401 => L.T("voice.state.device_unknown"),
        PortalException p when L.Has("msgs.err." + p.Code) => L.T("msgs.err." + p.Code),
        PortalException p when p.Status == 429 => L.T("voice.busy"),
        PortalException p when L.Has("voice.err." + p.Code) => L.T("voice.err." + p.Code),
        PortalException p => L.T("account.error", p.Code),
        _ => L.T("account.offline"),
    };

    static bool Failed(Exception e) => e is HttpRequestException or TaskCanceledException or PortalException;

    /// <summary>The device key and the client, or null when this launcher is not linked (the chat page says so).</summary>
    (PortalClient Client, string Token)? Site()
    {
        if (_store.Load() is not { } account || Portal() is not { } portal) return null;
        return (new PortalClient(Http, portal), account.Token);
    }

    // ------------------------------------------------------------------ the counter

    /// <summary>
    /// The launcher asks about the unread messages together with the tickets (MainWindow), not on a timer of its own.
    /// True when there are more of them than at the last look. A dead network is silence.
    /// </summary>
    public async Task<bool> LookAsync()
    {
        if (Site() is not { } s)
        {
            Forget();
            return false;
        }
        try
        {
            int n = await s.Client.MessagesUnreadAsync(s.Token, CancellationToken.None);
            bool grew = _watch.Update(n);
            UnreadChanged?.Invoke();
            return grew;
        }
        catch (Exception e) when (Failed(e)) { return false; }
    }

    void Forget()
    {
        if (_watch.Unread == 0) { _watch.Reset(); return; }
        _watch.Reset();
        UnreadChanged?.Invoke();
    }

    // ------------------------------------------------------------------ the page

    /// <summary>The tab was opened: the conversations again (they change on the site and in the other launcher).</summary>
    public async void Shown()
    {
        if (!Linked) { Forget(); return; }
        await LoadInboxAsync();
        if (_current is not null) await LoadThreadAsync(merge: true);
    }

    async Task BeatAsync()
    {
        if (_busy || TopLevel.GetTopLevel(this) is null || !IsEffectivelyVisible || !Linked) return;
        await LoadInboxAsync();
        if (_current is not null && _threadBox.IsVisible) await LoadThreadAsync(merge: true);
    }

    async Task LoadInboxAsync()
    {
        if (_inboxBusy || Site() is not { } s) return;
        _inboxBusy = true;
        try
        {
            var inbox = await s.Client.MessageInboxAsync(s.Token, CancellationToken.None);
            _dialogues = inbox.Dialogues;
            _watch.Update(inbox.Unread);
            UnreadChanged?.Invoke();
            ShowList();
            Status(null);
        }
        catch (Exception e) when (Failed(e)) { Status(Reason(e)); }
        finally { _inboxBusy = false; }
    }

    void ShowList()
    {
        _list.Children.Clear();
        if (_dialogues.Count == 0) _list.Children.Add(Skin.Note(L.T("msgs.none")));
        foreach (var d in _dialogues) _list.Children.Add(DialogueRow(d));
    }

    Control DialogueRow(MessageDialogue d)
    {
        bool open = _current == d.Person.Id && !_composeBox.IsVisible;
        var name = new TextBlock { Text = d.Person.Name, FontSize = 15, FontFamily = d.Unread > 0 ? Skin.Medium : Skin.Regular, Foreground = Skin.B(d.Unread > 0 ? Skin.Accent : Skin.Text), TextTrimming = TextTrimming.CharacterEllipsis };
        var preview = (d.LastMine ? L.T("msgs.you", d.Preview) : d.Preview);
        var line = new TextBlock { Text = preview, FontSize = 12, Foreground = Skin.B(Skin.Muted), TextTrimming = TextTrimming.CharacterEllipsis, MaxLines = 1 };
        var time = new TextBlock { Text = d.At.ToLocalTime().ToString("dd.MM HH:mm"), FontSize = 11, Foreground = Skin.B(Skin.Dim) };
        var text = new StackPanel { Spacing = 2 };
        text.Children.Add(name);
        text.Children.Add(line);
        text.Children.Add(time);
        var dock = new DockPanel();
        if (d.Unread > 0)
        {
            var badge = new Border
            {
                Background = Skin.B(Skin.Accent), CornerRadius = new CornerRadius(2), Padding = new Thickness(6, 1), VerticalAlignment = VerticalAlignment.Center,
                Child = new TextBlock { Text = d.Unread.ToString(), Foreground = Skin.B(Skin.OnAccent), FontSize = 12, FontFamily = Skin.Medium },
            };
            ToolTip.SetTip(badge, L.T("msgs.unread", d.Unread));
            DockPanel.SetDock(badge, Dock.Right);
            dock.Children.Add(badge);
        }
        dock.Children.Add(text);
        var row = new Border
        {
            Background = Skin.B(open ? Skin.Pressed : Skin.Inactive),
            BorderBrush = Skin.B(open || d.Unread > 0 ? Skin.Accent : Skin.Inactive),
            BorderThickness = new Thickness(open || d.Unread > 0 ? 3 : 0, 0, 0, 0),
            CornerRadius = new CornerRadius(2), Padding = new Thickness(12, 8), Cursor = new Cursor(StandardCursorType.Hand), Child = dock,
        };
        row.PointerPressed += async (_, e) =>
        {
            if (e.GetCurrentPoint(row).Properties.IsLeftButtonPressed) await OpenAsync(d.Person.Id, d.Person.Name);
        };
        return row;
    }

    /// <summary>Opens a dialogue (from the list, or after a new message was sent).</summary>
    public async Task OpenAsync(Guid id, string name)
    {
        _composeBox.IsVisible = false;
        _current = id;
        _currentName = name;
        _bubbles.Clear();
        _total = _pages = 0;
        _who.Text = name;
        _reply.Text = "";
        ShowThread();
        await LoadThreadAsync(merge: false);
        ShowList();
    }

    void Pick()
    {
        ShowThread();
        ShowList();
    }

    void ShowThread()
    {
        _threadBox.IsVisible = _current is not null && !_composeBox.IsVisible;
        foreach (var c in _right.Children.OfType<TextBlock>().Where(t => t.Name == "pick")) c.IsVisible = !_threadBox.IsVisible && !_composeBox.IsVisible;
    }

    // ------------------------------------------------------------------ one dialogue

    /// <summary>
    /// Page 1 of the dialogue (the end of the conversation). merge: what is already on screen stays, with only the new
    /// messages added - the page is refreshed under a person who reads further up or types an answer.
    /// </summary>
    async Task LoadThreadAsync(bool merge)
    {
        if (_threadBusy || _current is not { } id || Site() is not { } s) return;
        _threadBusy = true;
        try
        {
            var t = await s.Client.MessageThreadAsync(s.Token, id, 1, CancellationToken.None);
            if (_current != id) return;
            if (!merge) { _bubbles.Clear(); _pages = 1; }
            bool fresh = Merge(t.Messages);
            _total = t.Total;
            _iBlocked = t.IBlocked;
            _pages = Math.Max(_pages, 1);
            _who.Text = _currentName = t.Person.Name;
            ShowBubbles(toEnd: !merge || fresh);
            await MarkReadAsync(s, id);
        }
        catch (Exception e) when (Failed(e)) { Status(Reason(e)); }
        finally { _threadBusy = false; }
    }

    async Task LoadOlderAsync()
    {
        if (_threadBusy || _current is not { } id || Site() is not { } s) return;
        _threadBusy = true;
        try
        {
            var t = await s.Client.MessageThreadAsync(s.Token, id, _pages + 1, CancellationToken.None);
            if (_current != id) return;
            _pages++;
            Merge(t.Messages);
            _total = t.Total;
            ShowBubbles(toEnd: false);
        }
        catch (Exception e) when (Failed(e)) { Status(Reason(e)); }
        finally { _threadBusy = false; }
    }

    /// <summary>Adds the messages not yet shown and refreshes the read marks; true when something was new.</summary>
    bool Merge(IEnumerable<MessageBubble> got)
    {
        bool added = false;
        foreach (var b in got)
        {
            int i = _bubbles.FindIndex(x => x.Id == b.Id);
            if (i >= 0) _bubbles[i] = b;
            else { _bubbles.Add(b); added = true; }
        }
        // OrderBy is stable: messages of the same second keep the order the site gave them
        var ordered = _bubbles.OrderBy(b => b.At).ToList();
        _bubbles.Clear();
        _bubbles.AddRange(ordered);
        return added;
    }

    void ShowBubbles(bool toEnd)
    {
        ShowThread();
        _older.IsVisible = _bubbles.Count < _total;
        _older.Content = L.T("msgs.older", _bubbles.Count, _total);
        _feed.Children.Clear();
        foreach (var b in _bubbles) _feed.Children.Add(Bubble(b));
        _block.Content = L.T(_iBlocked ? "msgs.unblock" : "msgs.block");
        _blockedNote.IsVisible = _iBlocked;
        _reply.IsEnabled = _send.IsEnabled = !_iBlocked;
        if (toEnd) Dispatcher.UIThread.Post(() => _scroll.ScrollToEnd(), DispatcherPriority.Background);
    }

    static Control Bubble(MessageBubble b)
    {
        // SelectableTextBlock: the text can be copied, and it is only text - no link in it opens
        var text = new SelectableTextBlock { Text = b.Body, FontSize = 14, TextWrapping = TextWrapping.Wrap, Foreground = Skin.B(Skin.Text) };
        var meta = $"{b.At.ToLocalTime():dd.MM.yyyy HH:mm}" + (b.Mine && b.Read ? " · " + L.T("msgs.readMark") : "");
        var stack = new StackPanel { Spacing = 3 };
        stack.Children.Add(text);
        stack.Children.Add(new TextBlock { Text = meta, FontSize = 11, Foreground = Skin.B(Skin.Dim), HorizontalAlignment = b.Mine ? HorizontalAlignment.Right : HorizontalAlignment.Left });
        return new Border
        {
            Background = Skin.B(b.Mine ? Skin.Pressed : Skin.Inactive),
            BorderBrush = Skin.B(b.Mine ? Skin.FrameInner : Skin.Track),
            BorderThickness = new Thickness(1),
            CornerRadius = new CornerRadius(3),
            Padding = new Thickness(12, 8),
            MaxWidth = 560,
            Margin = b.Mine ? new Thickness(60, 0, 0, 0) : new Thickness(0, 0, 60, 0),
            HorizontalAlignment = b.Mine ? HorizontalAlignment.Right : HorizontalAlignment.Left,
            Child = stack,
        };
    }

    /// <summary>The dialogue is in front of the person: what the other wrote is read (the site marks nothing by itself).</summary>
    async Task MarkReadAsync((PortalClient Client, string Token) s, Guid id)
    {
        if (TopLevel.GetTopLevel(this) is null || !IsEffectivelyVisible) return;
        int waiting = _dialogues.FirstOrDefault(d => d.Person.Id == id)?.Unread ?? 0;
        if (waiting == 0 && !_bubbles.Any(b => !b.Mine && !b.Read)) return;
        try
        {
            await s.Client.MessagesReadAsync(s.Token, id, CancellationToken.None);
            _watch.Read(waiting);
            int i = _dialogues.FindIndex(d => d.Person.Id == id);
            if (i >= 0) _dialogues[i] = _dialogues[i] with { Unread = 0 };
            for (int k = 0; k < _bubbles.Count; k++)
                if (!_bubbles[k].Mine) _bubbles[k] = _bubbles[k] with { Read = true };
            ShowList();
            UnreadChanged?.Invoke();
        }
        catch (Exception e) when (Failed(e)) { }   // the next look tries again
    }

    async Task SendReplyAsync()
    {
        if (_busy || !_send.IsEnabled || _current is not { } id || Site() is not { } s) return;
        var body = _reply.Text ?? "";
        if (body.Trim().Length == 0) return;
        _busy = _send.IsEnabled = false;
        try
        {
            await s.Client.SendMessageAsync(s.Token, id, body, CancellationToken.None);
            _reply.Text = "";
            Status(null);
        }
        catch (Exception e) when (Failed(e))
        {
            Status(Reason(e));
            return;
        }
        finally { _busy = false; _send.IsEnabled = !_iBlocked; }
        await LoadThreadAsync(merge: true);
        await LoadInboxAsync();
    }

    async Task BlockAsync()
    {
        if (_current is not { } id || Site() is not { } s || Owner() is not { } owner) return;
        try
        {
            if (_iBlocked)
            {
                await s.Client.UnblockPersonAsync(s.Token, id, CancellationToken.None);
                Status(L.T("msgs.unblocked"), warn: false);
            }
            else
            {
                if (!await new MessageDialog(L.T("msgs.blockConfirm", _currentName), withNo: true).ShowDialog<bool>(owner)) return;
                await s.Client.BlockPersonAsync(s.Token, id, CancellationToken.None);
                Status(L.T("msgs.blocked", _currentName), warn: false);
            }
        }
        catch (Exception e) when (Failed(e)) { Status(Reason(e)); return; }
        await LoadThreadAsync(merge: true);
    }

    async Task ComplainAsync()
    {
        if (_current is not { } id || Site() is not { } s || Owner() is not { } owner) return;
        var text = await new TextDialog(L.T("msgs.complainPrompt", _currentName), "", MessageRules.ComplaintMax).ShowDialog<string?>(owner);
        if (text is null) return;
        try
        {
            var c = await s.Client.ComplainAboutMessagesAsync(s.Token, id, null, text, CancellationToken.None);
            Status(L.T("msgs.complained", c.DisplayNumber), warn: false);
        }
        catch (Exception e) when (Failed(e)) { Status(Reason(e)); }
    }

    // ------------------------------------------------------------------ a new message

    async Task StartComposeAsync()
    {
        _composeBox.IsVisible = true;
        _threadBox.IsVisible = false;
        ShowThread();
        ShowList();
        _to.Focus();
        if (_friendsLoaded || Site() is not { } s) return;
        try
        {
            var friends = await s.Client.FriendsAsync(s.Token, 1, CancellationToken.None);
            _friends.Children.Clear();
            foreach (var f in friends.Friends)
            {
                var chip = Skin.Btn(f.Name, "ghost", 30);
                chip.Margin = new Thickness(0, 0, 6, 6);
                chip.Click += (_, _) => { _to.Text = f.Name; _text.Focus(); };
                _friends.Children.Add(chip);
            }
            _friendsNote.IsVisible = friends.Friends.Count == 0;
            _friendsLoaded = true;
        }
        catch (Exception e) when (Failed(e)) { Status(Reason(e)); }
    }

    async Task SendNewAsync()
    {
        if (_busy || Site() is not { } s) return;
        var who = (_to.Text ?? "").Trim();
        var body = _text.Text ?? "";
        if (who.Length == 0 || body.Trim().Length == 0) return;
        _busy = true;
        MessageSent made;
        try { made = await s.Client.SendMessageToAsync(s.Token, who, body, CancellationToken.None); }
        catch (Exception e) when (Failed(e))
        {
            Status(Reason(e));
            return;
        }
        finally { _busy = false; }
        Status(null);
        _to.Text = _text.Text = "";
        await OpenAsync(made.To.Id, made.To.Name);
        await LoadInboxAsync();
    }
}
