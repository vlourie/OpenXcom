using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Documents;
using Avalonia.Controls.Primitives;
using Avalonia.Input;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Threading;
using Xp.Launcher.Core;
using Xp.Voice;

namespace Xp.Launcher;

/// <summary>
/// The "Chat" section (docs/portal/VOICE_IRC.md §3, §5): three columns like IRC. On the left the public channels, my rooms and
/// the private dialogues with their counters; in the middle the topic, the feed as "12:34 &lt;nick&gt; text" lines and one input
/// line; on the right who is here, marked @ (owner or staff) and + (in voice now). Voice is a button of the channel: "Join
/// voice" under the feed, the microphone, the talk key and the sound settings beside it. The logic of the voice session
/// (push-to-talk by default, a pass for every entry) is the same as before; who may come in, read, write or moderate is
/// the site's business. The old voice lobby (open rooms, knocks, who is online) is the "Rooms and people" entry on the left.
/// Text is drawn as text: nothing in a line is a link.
/// </summary>
public sealed class VoicePage : UserControl
{
    static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(30) };

    /// <summary>How often the open feed is asked for, while the section is on screen and the window is not minimized.</summary>
    public static readonly TimeSpan FeedEvery = TimeSpan.FromSeconds(3);

    readonly Settings _settings;
    readonly DeviceStore _store = new(Path.Combine(Settings.Dir, "device.json"));
    readonly AccountPanel _account;
    readonly Func<BuildStore?> _builds;

    readonly TextBlock _status = new() { FontSize = 13, TextWrapping = TextWrapping.Wrap, IsVisible = false };
    readonly StackPanel _unlinked = new() { Spacing = 12, IsVisible = false };

    // the lobby: everybody's open rooms, the knocks at my doors, who is online
    readonly StackPanel _lobby = new() { Spacing = 12 };
    readonly StackPanel _owned = new() { Spacing = 8 }, _invited = new() { Spacing = 8 };
    readonly StackPanel _catalog = new() { Spacing = 8 };
    readonly StackPanel _requests = new() { Spacing = 8 };
    readonly Border _requestsBox;
    readonly StackPanel _online = new() { Spacing = 6 };
    readonly TextBlock _onlineTitle = Skin.H2(L.T("voice.online", 0));
    readonly Border _side;
    readonly Border _soundPanel;
    readonly Button _settingsButton;
    int _knocks;

    // the three columns
    readonly Grid _body;
    readonly ColumnDefinition _leftColumn = new(230, GridUnitType.Pixel), _rightColumn = new(250, GridUnitType.Pixel);
    readonly Border _leftPanel, _rightPanel;
    readonly StackPanel _channelList = new() { Spacing = 2 }, _roomList = new() { Spacing = 2 }, _dialogueList = new() { Spacing = 2 };
    readonly TextBlock _roomsTitle = Skin.H2(L.T("chat.rooms"));
    readonly Button _lobbyButton;
    readonly Grid _middle;
    readonly TextBlock _topicTitle = new() { FontFamily = Skin.Medium, FontSize = 16, VerticalAlignment = VerticalAlignment.Center };
    readonly TextBlock _topicText = new() { FontSize = 13, Foreground = Skin.B(Skin.Text2), VerticalAlignment = VerticalAlignment.Center, TextTrimming = TextTrimming.CharacterEllipsis };
    readonly StackPanel _topicActions = new() { Orientation = Orientation.Horizontal, Spacing = 8, VerticalAlignment = VerticalAlignment.Center };
    readonly Button _block, _complain, _site, _peopleButton, _peopleBack;
    readonly StackPanel _feed = new() { Spacing = 1 };
    readonly ScrollViewer _scroll;
    readonly Border _feedBox;
    readonly Button _older;
    readonly TextBlock _empty = Skin.Note(L.T("chat.pick"), 14);
    readonly ScrollViewer _lobbyScroll;
    readonly Grid _inputRow;
    readonly TextBox _input = new() { MaxLength = ChatRules.LineMax, FontSize = 14, AcceptsReturn = false };
    readonly Button _send;
    readonly TextBlock _attendeesTitle = Skin.H2(L.T("chat.here", 0));
    readonly StackPanel _attendees = new() { Spacing = 1 };
    readonly Border _voiceBox;

    enum Pane { None, Channel, Dialogue, Lobby }
    Pane _pane;
    string? _channelId;
    ChatChannels _list = new([], []);
    ChatFeed? _lastFeed;
    readonly ChatBuffer _buffer = new();
    readonly List<ChatLine> _info = [];
    long _infoId;
    string? _newTo;                         // a new private message: the name typed, nothing sent yet
    bool _narrow, _peopleOpen, _feedBusy, _channelsBusy, _backgroundBusy, _autoPicked;
    DateTimeOffset _shownAt;

    /// <summary>The game folder and whether a game runs in it: set by the window. A running game is told by <see cref="ChatNotice"/>.</summary>
    public Func<GamePaths?>? GameFolder { get; set; }
    public Func<bool>? GameRunning { get; set; }
    public ChatNoticer Noticer { get; }

    /// <summary>The private messages of the same account: the counter on the rail follows it.</summary>
    public Dialogues Messages { get; }
    List<VoiceRoom> _mine = [];
    readonly DispatcherTimer _beat = new() { Interval = TimeSpan.FromSeconds(20) };
    readonly DispatcherTimer _poll = new() { Interval = FeedEvery };
    int _beats;
    bool _lobbyBusy;

    // voice, under the feed
    readonly Border _voiceBar;
    readonly Button _voiceJoin, _voiceLeave;
    readonly TextBlock _connection = new() { FontSize = 13, TextWrapping = TextWrapping.Wrap };
    readonly TextBlock _micNote = new() { FontSize = 13, TextWrapping = TextWrapping.Wrap };
    readonly ProgressBar _micLevel = new() { Minimum = -60, Maximum = 0, Height = 8, Width = 120, VerticalAlignment = VerticalAlignment.Center };
    readonly Button _micToggle;
    readonly StackPanel _people = new() { Spacing = 8 };
    readonly TextBlock _alone = Skin.Note(L.T("voice.alone"));
    readonly Dictionary<string, PeerRow> _rows = new(StringComparer.Ordinal);

    // sound and key
    readonly ComboBox _inputDevice = new() { HorizontalAlignment = HorizontalAlignment.Stretch, FontSize = 13 };
    readonly ComboBox _output = new() { HorizontalAlignment = HorizontalAlignment.Stretch, FontSize = 13 };
    readonly TextBlock _deviceNote = new() { FontSize = 12, Foreground = Skin.B(Skin.Muted), TextWrapping = TextWrapping.Wrap };
    readonly Slider _volume = new() { Minimum = 0, Maximum = 200, MinWidth = 220 };
    readonly Button _check;
    readonly ProgressBar _checkLevel = new() { Minimum = -60, Maximum = 0, Height = 8, MinWidth = 220, VerticalAlignment = VerticalAlignment.Center };
    readonly TextBlock _checkNote = new() { FontSize = 12, Foreground = Skin.B(Skin.Muted), TextWrapping = TextWrapping.Wrap };
    readonly RadioButton _modePtt = new() { Content = L.T("voice.modePtt"), GroupName = "voiceMode" };
    readonly RadioButton _modeOpen = new() { Content = L.T("voice.modeOpen"), GroupName = "voiceMode" };
    readonly TextBlock _keyName = new() { FontSize = 13, VerticalAlignment = VerticalAlignment.Center };
    readonly Button _assign;
    readonly TextBlock _keyNote = new() { FontSize = 12, TextWrapping = TextWrapping.Wrap };

    readonly DispatcherTimer _timer = new() { Interval = TimeSpan.FromMilliseconds(200) };

    VoiceSession? _session;
    VoiceRoom? _room;
    string _token = "";
    volatile string _me = "";                // set by the pass, on the session's room loop
    volatile bool _canPublish = true;
    volatile bool _unavailable;              // the last pass was 503 voice_unavailable, not a network failure
    volatile bool _voiceModerator;           // may mute, kick and ban in the room I am in (its owner, or staff in a public channel)
    Dictionary<string, VoiceLive> _live = new(StringComparer.Ordinal);
    int _ticks;
    bool _liveBusy, _loading, _filling, _devicesFilled;
    MicCheck? _micCheck;
    string? _wanted;                        // the room of an xpiratez:// link, opened as soon as the list is here
    bool _hookFailed;

    /// <summary>Entered or left a room: the window decides about the tray by it.</summary>
    public event Action? RoomChanged;
    public bool InRoom => _session is not null;
    /// <summary>The launcher is linked to an account: it shows up online and has something to say on closing.</summary>
    public bool Linked => _store.Load() is not null;
    public string? RoomTitle => _room?.Title;

    public VoicePage(Settings settings, AccountPanel account, Func<BuildStore?> builds, Action openSettings)
    {
        _settings = settings;
        _account = account;
        _builds = builds;
        Noticer = new ChatNoticer(() => GameFolder?.Invoke(), () => GameRunning?.Invoke() == true, () => _settings.ChatNoticeAll);
        Messages = new Dialogues(settings) { Noticer = Noticer, InFront = () => Active() && _pane == Pane.Dialogue };
        Messages.Status = (text, warn) => Status(text, warn);
        Messages.Changed += OnDialoguesChanged;
        Messages.UnreadChanged += ShowLeft;
        _account.Changed += () => RefreshAll();

        // --- not linked
        _unlinked.Children.Add(Skin.Note(L.T("voice.unlinked"), 14, Skin.Text2));
        var toSettings = Skin.Btn(L.T("voice.toSettings"), "primary");
        toSettings.Click += (_, _) => openSettings();
        _unlinked.Children.Add(toSettings);

        // --- the lobby ("Rooms and people"): the same lists as before, in the middle column
        var create = Skin.Btn(L.T("voice.create"), "primary");
        create.Click += async (_, _) => await CreateAsync();
        var refresh = Skin.Btn(L.T("voice.refresh"), "ghost");
        refresh.Click += async (_, _) => await LoadAsync();
        var actions = new WrapPanel { Orientation = Orientation.Horizontal };
        create.Margin = refresh.Margin = new Thickness(0, 0, 10, 6);
        actions.Children.Add(create);
        actions.Children.Add(refresh);
        var friendsSite = Skin.Link(L.T("voice.friendsSite") + "  ↗", () => { if (SiteVoiceUrl() is { } u) ReportWindow.OpenUrl(u); });
        friendsSite.VerticalAlignment = VerticalAlignment.Center;
        actions.Children.Add(friendsSite);
        _lobby.Children.Add(actions);
        _lobby.Children.Add(Skin.H2(L.T("voice.mine")));
        _lobby.Children.Add(Skin.Note(L.T("voice.adminHint")));
        _lobby.Children.Add(_owned);
        _lobby.Children.Add(Skin.H2(L.T("voice.invited")));
        _lobby.Children.Add(_invited);
        _lobby.Children.Add(Skin.H2(L.T("voice.all")));
        _lobby.Children.Add(_catalog);

        // --- knocks at my doors
        var knocks = new StackPanel { Spacing = 8 };
        knocks.Children.Add(Skin.H2(L.T("voice.requests")));
        knocks.Children.Add(_requests);
        _requestsBox = Skin.Panel(knocks);
        _requestsBox.IsVisible = false;

        // --- who is online
        var side = new StackPanel { Spacing = 8 };
        side.Children.Add(_onlineTitle);
        side.Children.Add(_online);
        _side = Skin.Panel(side);
        _side.IsVisible = false;

        var lobbyStack = new StackPanel { Spacing = 14, Margin = new Thickness(0, 0, 12, 0) };
        lobbyStack.Children.Add(_requestsBox);
        lobbyStack.Children.Add(_lobby);
        lobbyStack.Children.Add(_side);
        _lobbyScroll = new ScrollViewer { Content = lobbyStack, IsVisible = false, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled };

        // --- sound and the key: behind a button of the voice bar
        _check = Skin.Btn(L.T("voice.check"));
        _check.Click += (_, _) => ToggleCheck();
        _assign = Skin.Btn(L.T("voice.assign"), "ghost", 30);
        _assign.Click += (_, _) => Assign();
        _volume.Value = Math.Clamp(_settings.VoiceVolume, 0, 2) * 100;
        _volume.ValueChanged += (_, _) =>
        {
            _settings.VoiceVolume = _volume.Value / 100;
            if (_session is { } s) s.Volume = (float)_settings.VoiceVolume;
            SaveSoon();
        };
        _inputDevice.SelectionChanged += (_, _) => DeviceChosen(_inputDevice, capture: true);
        _output.SelectionChanged += (_, _) => DeviceChosen(_output, capture: false);
        (_settings.VoiceOpenMic ? _modeOpen : _modePtt).IsChecked = true;
        _modePtt.IsCheckedChanged += (_, _) => ModeChanged();

        var sound = new StackPanel { Spacing = 10 };
        sound.Children.Add(Skin.H2(L.T("voice.sound")));
        sound.Children.Add(Labeled("voice.input", _inputDevice));
        sound.Children.Add(Labeled("voice.output", _output));
        sound.Children.Add(_deviceNote);
        var volRow = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 12 };
        volRow.Children.Add(new TextBlock { Text = L.T("voice.volume"), FontSize = 13, VerticalAlignment = VerticalAlignment.Center, MinWidth = 110 });
        volRow.Children.Add(_volume);
        sound.Children.Add(volRow);
        var checkRow = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 12 };
        checkRow.Children.Add(_check);
        checkRow.Children.Add(_checkLevel);
        sound.Children.Add(checkRow);
        sound.Children.Add(_checkNote);
        sound.Children.Add(_modePtt);
        sound.Children.Add(_modeOpen);
        _soundPanel = Skin.Panel(new ScrollViewer { Content = sound, MaxHeight = 330 });
        _soundPanel.IsVisible = false;
        _soundPanel.Margin = new Thickness(0, 0, 0, 8);
        _settingsButton = Skin.Btn(L.T("voice.settings"), "ghost", 30);
        _settingsButton.Click += (_, _) => ShowSettings(!_soundPanel.IsVisible);

        // --- the voice bar under the feed
        _voiceJoin = Skin.Btn(L.T("chat.voiceJoin"), "ghost", 30);
        _voiceJoin.Click += async (_, _) => await JoinVoiceHereAsync();
        _voiceLeave = Skin.Btn(L.T("voice.leave"), "warn", 30);
        _voiceLeave.Click += async (_, _) => await LeaveAsync();
        _micToggle = Skin.Btn(L.T("voice.micMute"), "ghost", 30);
        _micToggle.Click += (_, _) =>
        {
            if (_session is not { } s) return;
            s.Muted = !s.Muted;
            ShowMicToggle();
        };
        var barRow = new WrapPanel { Orientation = Orientation.Horizontal };
        foreach (Control c in new Control[] { _voiceJoin, _voiceLeave, _micToggle, _micLevel, _keyName, _assign, _settingsButton })
        {
            c.Margin = new Thickness(0, 0, 10, 4);
            barRow.Children.Add(c);
        }
        var barText = new StackPanel { Spacing = 2 };
        barText.Children.Add(_connection);
        barText.Children.Add(_micNote);
        barText.Children.Add(_keyNote);
        var barBody = new StackPanel { Spacing = 2 };
        barBody.Children.Add(barRow);
        barBody.Children.Add(barText);
        _voiceBar = Skin.Panel(barBody, new Thickness(12, 8, 12, 6));
        _voiceBar.Margin = new Thickness(0, 8, 0, 0);

        // --- the left column
        _lobbyButton = Skin.Btn(L.T("chat.lobby"), "tab");
        _lobbyButton.HorizontalAlignment = HorizontalAlignment.Stretch;
        _lobbyButton.HorizontalContentAlignment = HorizontalAlignment.Left;
        _lobbyButton.Padding = new Thickness(8, 0);
        _lobbyButton.Click += async (_, _) => await OpenLobbyAsync();
        var write = Skin.Btn(L.T("msgs.new"), "ghost", 30);
        write.HorizontalAlignment = HorizontalAlignment.Stretch;
        write.Click += async (_, _) => await WriteNewAsync();
        var left = new StackPanel { Spacing = 6 };
        left.Children.Add(_lobbyButton);
        left.Children.Add(Skin.H2(L.T("chat.channels")));
        left.Children.Add(_channelList);
        left.Children.Add(_roomsTitle);
        left.Children.Add(_roomList);
        left.Children.Add(Skin.H2(L.T("chat.private")));
        left.Children.Add(_dialogueList);
        left.Children.Add(write);
        _leftPanel = Skin.Panel(new ScrollViewer { Content = left, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled }, new Thickness(10));
        _leftPanel.Margin = new Thickness(0, 0, 12, 0);

        // --- the middle: the topic, the feed, the input
        _block = Skin.Btn(L.T("msgs.block"), "ghost", 30);
        _block.Click += async (_, _) => await BlockAsync();
        _complain = Skin.Btn(L.T("msgs.complain"), "ghost", 30);
        _complain.Click += async (_, _) => await ComplainDialogueAsync();
        _site = Skin.Btn(L.T("chat.site") + " ↗", "quiet", 30);
        _site.Click += (_, _) => { if (SiteUrl() is { } u) ReportWindow.OpenUrl(u); };
        _peopleButton = Skin.Btn(L.T("chat.people"), "ghost", 30);
        _peopleButton.Click += (_, _) => { _peopleOpen = !_peopleOpen; ShowPane(); };
        foreach (var b in new[] { _peopleButton, _block, _complain, _site }) _topicActions.Children.Add(b);
        var topic = new DockPanel { LastChildFill = true };
        DockPanel.SetDock(_topicActions, Dock.Right);
        topic.Children.Add(_topicActions);
        var topicTexts = new Grid { ColumnDefinitions = new ColumnDefinitions("Auto,*"), VerticalAlignment = VerticalAlignment.Center };
        _topicTitle.Margin = new Thickness(0, 0, 12, 0);
        topicTexts.Children.Add(_topicTitle);
        Grid.SetColumn(_topicText, 1);
        topicTexts.Children.Add(_topicText);
        topic.Children.Add(topicTexts);
        var topicBar = Skin.Panel(topic, new Thickness(14, 6));
        topicBar.Margin = new Thickness(0, 0, 0, 8);

        _older = Skin.Btn("", "quiet", 28);
        _older.HorizontalAlignment = HorizontalAlignment.Center;
        _older.Click += async (_, _) => await Messages.LoadOlderAsync();
        var feedBody = new StackPanel();
        feedBody.Children.Add(_older);
        feedBody.Children.Add(_feed);
        _scroll = new ScrollViewer { Content = feedBody, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled, Padding = new Thickness(0, 0, 10, 0) };
        _feedBox = new Border { Background = Skin.B(Skin.Field), CornerRadius = Skin.Radius, Padding = new Thickness(12, 8, 2, 8), Child = _scroll, ClipToBounds = true };

        _input.Watermark = L.T("chat.inputHint");
        _input.KeyDown += (_, e) =>
        {
            if (e.Key != Avalonia.Input.Key.Enter) return;
            e.Handled = true;
            _ = SubmitAsync();
        };
        _send = Skin.Btn(L.T("msgs.send"), "primary");
        _send.Click += async (_, _) => await SubmitAsync();
        _inputRow = new Grid { ColumnDefinitions = new ColumnDefinitions("*,Auto"), Margin = new Thickness(0, 8, 0, 0) };
        _inputRow.Children.Add(_input);
        _send.Margin = new Thickness(8, 0, 0, 0);
        Grid.SetColumn(_send, 1);
        _inputRow.Children.Add(_send);

        _middle = new Grid { RowDefinitions = new RowDefinitions("Auto,Auto,*,Auto,Auto") };
        _middle.Children.Add(topicBar);
        Grid.SetRow(_soundPanel, 1);
        _middle.Children.Add(_soundPanel);
        var stage = new Grid();
        stage.Children.Add(_feedBox);
        stage.Children.Add(_lobbyScroll);
        stage.Children.Add(_empty);
        _empty.Margin = new Thickness(12);
        Grid.SetRow(stage, 2);
        _middle.Children.Add(stage);
        Grid.SetRow(_voiceBar, 3);
        _middle.Children.Add(_voiceBar);
        Grid.SetRow(_inputRow, 4);
        _middle.Children.Add(_inputRow);

        // --- the right column: who is here, and the people of the voice room
        var right = new StackPanel { Spacing = 6 };
        // the narrow page of the people hides the middle column with its own button: the way back is here
        _peopleBack = Skin.Btn(L.T("chat.back"), "ghost", 30);
        _peopleBack.HorizontalAlignment = HorizontalAlignment.Left;
        _peopleBack.IsVisible = false;
        _peopleBack.Click += (_, _) => { _peopleOpen = false; ShowPane(); };
        right.Children.Add(_peopleBack);
        right.Children.Add(_attendeesTitle);
        right.Children.Add(_attendees);
        var voicePeople = new StackPanel { Spacing = 8 };
        voicePeople.Children.Add(Skin.H2(L.T("voice.people")));
        voicePeople.Children.Add(_alone);
        voicePeople.Children.Add(_people);
        _voiceBox = new Border { Child = voicePeople, Margin = new Thickness(0, 10, 0, 0), IsVisible = false };
        right.Children.Add(_voiceBox);
        _rightPanel = Skin.Panel(new ScrollViewer { Content = right, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled }, new Thickness(10));
        _rightPanel.Margin = new Thickness(12, 0, 0, 0);

        _body = new Grid { IsVisible = false };
        _body.ColumnDefinitions.Add(_leftColumn);
        _body.ColumnDefinitions.Add(new ColumnDefinition(1, GridUnitType.Star) { MinWidth = 260 });
        _body.ColumnDefinitions.Add(_rightColumn);
        _body.Children.Add(_leftPanel);
        Grid.SetColumn(_middle, 1);
        _body.Children.Add(_middle);
        Grid.SetColumn(_rightPanel, 2);
        _body.Children.Add(_rightPanel);

        var top = new DockPanel { Margin = new Thickness(0, 0, 0, 12) };
        top.Children.Add(Skin.H1(L.T("voice.title")));
        var root = new Grid { RowDefinitions = new RowDefinitions("Auto,Auto,*"), Margin = new Thickness(28, 22, 28, 22) };
        root.Children.Add(top);
        var warn = new StackPanel { Spacing = 8 };
        warn.Children.Add(_status);
        warn.Children.Add(_unlinked);
        Grid.SetRow(warn, 1);
        root.Children.Add(warn);
        Grid.SetRow(_body, 2);
        root.Children.Add(_body);
        Content = root;
        SizeChanged += (_, e) => Narrow(e.NewSize.Width < 760);

        _timer.Tick += (_, _) => Tick();
        _beat.Tick += (_, _) => Beat();
        _poll.Tick += async (_, _) => await PollAsync();
        _beat.Start();
        _poll.Start();
        Dispatcher.UIThread.Post(Beat);
        ShowKey();
        ShowCheck();
        ShowPane();
    }

    void ShowSettings(bool on)
    {
        _soundPanel.IsVisible = on;
        _settingsButton.Content = L.T(on ? "voice.settingsHide" : "voice.settings");
        if (on) FillDevices();
        if (!on) StopCheck();
    }

    static Control Labeled(string key, Control c)
    {
        var g = new Grid { ColumnDefinitions = new ColumnDefinitions("170,*") };
        var t = new TextBlock { Text = L.T(key), FontSize = 13, VerticalAlignment = VerticalAlignment.Center };
        g.Children.Add(t);
        Grid.SetColumn(c, 1);
        g.Children.Add(c);
        return g;
    }

    Uri? Portal()
    {
        var url = _settings.PortalUrl ?? BuiltIn.Defaults.PortalUrl;
        return Uri.TryCreate(url, UriKind.Absolute, out var uri) ? uri : null;
    }

    string? SiteVoiceUrl() => Portal() is { } p ? p.AbsoluteUri.TrimEnd('/') + "/voice" : null;

    /// <summary>The site's page of what is open: the channel (its management for my own room), the dialogue.</summary>
    string? SiteUrl()
    {
        if (Portal() is not { } p) return null;
        var root = p.AbsoluteUri.TrimEnd('/');
        if (_pane == Pane.Dialogue) return Messages.SiteUrl();
        if (_pane == Pane.Channel && _channelId is { } id)
            return $"{root}/voice/rooms/{Uri.EscapeDataString(id)}" + (OpenChannel() is { Mine: true, IsPublic: false } ? "/manage" : "");
        return SiteVoiceUrl();
    }

    void Save()
    {
        _saveSoon?.Stop();
        try { _settings.Save(); } catch (IOException) { }
    }

    DispatcherTimer? _saveSoon;

    /// <summary>A slider moves in many small steps: the file is written once it stops.</summary>
    void SaveSoon()
    {
        if (_saveSoon is null)
        {
            _saveSoon = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1) };
            _saveSoon.Tick += (_, _) => Save();
        }
        _saveSoon.Stop();
        _saveSoon.Start();
    }

    void Status(string? text, bool warn = true)
    {
        _status.IsVisible = text is not null;
        _status.Text = text ?? "";
        _status.Foreground = Skin.B(warn ? Skin.WarnText : Skin.Text2);
    }

    /// <summary>The section is on screen and the window is not minimized or hidden: only then the feed is asked for.</summary>
    bool Active() => IsEffectivelyVisible && TopLevel.GetTopLevel(this) is Window { IsVisible: true } w && w.WindowState != WindowState.Minimized;

    (PortalClient Client, string Token)? Site()
    {
        if (_store.Load() is not { } account || Portal() is not { } portal) return null;
        return (new PortalClient(Http, portal), account.Token);
    }

    string MyName => _store.Load()?.Account ?? "";

    // ------------------------------------------------------------------ the section

    /// <summary>The page was opened: the devices once, the lists every time (they change on the site and in the other launcher).</summary>
    public void Shown()
    {
        FillDevices();
        ShowKey();
        _shownAt = DateTimeOffset.UtcNow;
        RefreshAll();
    }

    void RefreshAll()
    {
        bool linked = Linked;
        _unlinked.IsVisible = !linked;
        _body.IsVisible = linked;
        if (!linked)
        {
            Status(null);
            Messages.Forget();
            _list = new([], []);
            _channelId = null;
            _pane = Pane.None;
            _autoPicked = false;
            ShowPane();
            return;
        }
        _ = BackgroundAsync();
        if (_pane == Pane.Lobby) _ = LoadAsync();
        if (_pane == Pane.Dialogue && Messages.Current is not null) _ = Messages.LoadThreadAsync(merge: true);
    }

    /// <summary>The page is narrow: the right column becomes a page of its own behind a button.</summary>
    void Narrow(bool narrow)
    {
        if (_narrow == narrow) return;
        _narrow = narrow;
        _leftColumn.Width = new GridLength(narrow ? 180 : 230);
        _peopleOpen = false;
        ShowPane();
    }

    void ShowPane()
    {
        bool chat = _pane is Pane.Channel or Pane.Dialogue;
        bool people = _narrow && _peopleOpen && (chat || InRoom);
        _middle.IsVisible = !people;
        _feedBox.IsVisible = chat;
        _inputRow.IsVisible = chat;
        _lobbyScroll.IsVisible = _pane == Pane.Lobby;
        _empty.IsVisible = _pane == Pane.None;
        _voiceBar.IsVisible = _pane == Pane.Channel || InRoom;
        bool rightWanted = chat || InRoom;
        _rightPanel.IsVisible = rightWanted && (!_narrow || people);
        if (_narrow && people) { Grid.SetColumn(_rightPanel, 1); Grid.SetColumnSpan(_rightPanel, 2); _rightPanel.Margin = new Thickness(0); }
        else { Grid.SetColumn(_rightPanel, 2); Grid.SetColumnSpan(_rightPanel, 1); _rightPanel.Margin = new Thickness(12, 0, 0, 0); }
        _rightColumn.Width = new GridLength(rightWanted && !_narrow ? 250 : 0);
        _voiceBox.IsVisible = InRoom;
        _peopleButton.IsVisible = _narrow && (chat || InRoom);
        _peopleButton.Content = L.T("chat.people");
        _peopleBack.IsVisible = people;
        ShowTopic();
        ShowVoiceBar();
        ShowLeft();
        ShowAttendees();
    }

    void ShowTopic()
    {
        var channel = OpenChannel();
        switch (_pane)
        {
            case Pane.Channel when channel is not null:
                _topicTitle.Text = ChatFormat.Title(channel);
                _topicText.Text = _lastFeed?.Topic ?? channel.Topic ?? "";
                ToolTip.SetTip(_topicText, _topicText.Text);
                break;
            case Pane.Dialogue:
                _topicTitle.Text = Messages.Current is not null ? Messages.CurrentName : _newTo ?? "";
                _topicText.Text = Messages.Current is not null ? L.T("chat.dialogue") : L.T("chat.newDialogue");
                break;
            case Pane.Lobby:
                _topicTitle.Text = L.T("chat.lobby");
                _topicText.Text = L.T("chat.lobbyHint");
                break;
            default:
                _topicTitle.Text = L.T("voice.title");
                _topicText.Text = "";
                break;
        }
        bool dialogue = _pane == Pane.Dialogue && Messages.Current is not null;
        _block.IsVisible = _complain.IsVisible = dialogue;
        _block.Content = L.T(Messages.IBlocked ? "msgs.unblock" : "msgs.block");
        _site.IsVisible = _pane is Pane.Channel or Pane.Dialogue && (_pane == Pane.Channel || dialogue);
        _topicActions.IsVisible = _pane != Pane.None;
    }

    ChatChannel? OpenChannel() =>
        _channelId is null ? null : _list.Channels.Concat(_list.Rooms).FirstOrDefault(c => c.Room == _channelId);

    // ------------------------------------------------------------------ polling

    /// <summary>Every 3 s while the section is on screen and the window is up: the open feed or the open dialogue.</summary>
    async Task PollAsync()
    {
        if (!Linked || !Active()) return;
        if (_pane == Pane.Channel) await RefreshFeedAsync();
        else if (_pane == Pane.Dialogue && Messages.Current is not null) await Messages.LoadThreadAsync(merge: true);
    }

    /// <summary>Once a minute, seen or not: the list of channels with its counters, the private dialogues, the knocks.</summary>
    async Task BackgroundAsync()
    {
        if (_backgroundBusy || Site() is null) return;
        _backgroundBusy = true;
        try
        {
            await ChannelsAsync();
            await Messages.LoadInboxAsync();
            await LobbyAsync();
        }
        finally { _backgroundBusy = false; }
    }

    async Task ChannelsAsync()
    {
        if (_channelsBusy || Site() is not { } s) return;
        _channelsBusy = true;
        try
        {
            var list = await s.Client.ChatChannelsAsync(s.Token, CancellationToken.None);
            _list = list;
            Noticer.Channels(list, L.T("chat.plate.mention"), n => L.T("chat.plate.new", n));
            ShowLeft();
            ShowTopic();
            if (_pane == Pane.None && !_autoPicked)
            {
                _autoPicked = true;
                var pick = _wanted is { } w ? list.Channels.Concat(list.Rooms).FirstOrDefault(c => c.Room == w) : list.Channels.FirstOrDefault();
                if (pick is not null) { _wanted = null; _ = OpenChannelAsync(pick, join: false); }
            }
            else if (_wanted is { } wanted)
            {
                var pick = list.Channels.Concat(list.Rooms).FirstOrDefault(c => c.Room == wanted);
                _wanted = null;
                if (pick is not null) _ = OpenChannelAsync(pick, join: false);
                else Status(L.T("voice.linkMissing"));
            }
        }
        catch (PortalException e) when (e.Status == 401)
        {
            await _account.CheckAsync();
            RefreshAll();
            Status(L.T("voice.state.device_unknown"));
        }
        catch (Exception e) when (Dialogues.Failed(e)) { if (Active()) Status(ChatReason(e)); }
        finally { _channelsBusy = false; }
    }

    // ------------------------------------------------------------------ the left column

    void ShowLeft()
    {
        _channelList.Children.Clear();
        foreach (var c in _list.Channels) _channelList.Children.Add(ChannelRow(c));
        _roomList.Children.Clear();
        foreach (var c in _list.Rooms) _roomList.Children.Add(ChannelRow(c));
        _roomsTitle.IsVisible = _list.Rooms.Count > 0;
        _dialogueList.Children.Clear();
        if (Messages.Inbox.Count == 0) _dialogueList.Children.Add(Skin.Note(L.T("chat.noDialogues"), 12));
        foreach (var d in Messages.Inbox) _dialogueList.Children.Add(DialogueRow(d));
        _lobbyButton.Content = _knocks > 0 ? L.T("chat.lobbyN", _knocks) : L.T("chat.lobby");
        _lobbyButton.Classes.Set("on", _pane == Pane.Lobby);
    }

    Border ListRow(bool selected, Control inner, Action click)
    {
        var row = new Border
        {
            Background = selected ? Skin.B(Skin.Selected) : Brushes.Transparent,
            CornerRadius = new CornerRadius(6), Padding = new Thickness(8, 5), Cursor = new Cursor(StandardCursorType.Hand), Child = inner,
        };
        row.PointerPressed += (_, e) =>
        {
            if (e.GetCurrentPoint(row).Properties.IsLeftButtonPressed) click();
        };
        row.PointerEntered += (_, _) => { if (!selected) row.Background = Skin.B(Skin.Hover); };
        row.PointerExited += (_, _) => { if (!selected) row.Background = Brushes.Transparent; };
        return row;
    }

    Control ChannelRow(ChatChannel c)
    {
        bool open = _pane == Pane.Channel && _channelId == c.Room;
        var dock = new DockPanel();
        if (c.Mentions > 0 || c.Unread > 0)
        {
            var pills = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 4, VerticalAlignment = VerticalAlignment.Center };
            if (c.Mentions > 0) pills.Children.Add(Skin.Tag("@" + c.Mentions, Skin.Teal, Skin.OnAccent));
            if (c.Unread > 0) pills.Children.Add(Skin.Tag(c.Unread.ToString(), Skin.Accent, Skin.OnAccent));
            DockPanel.SetDock(pills, Dock.Right);
            dock.Children.Add(pills);
        }
        dock.Children.Add(new TextBlock
        {
            Text = ChatFormat.Title(c), FontSize = 14, TextTrimming = TextTrimming.CharacterEllipsis,
            FontFamily = c.Unread > 0 || open ? Skin.Medium : Skin.Regular,
            Foreground = Skin.B(open || c.Joined || c.Unread > 0 ? Skin.Text : Skin.Text2),
        });
        var row = ListRow(open, dock, () => _ = OpenChannelAsync(c, join: true));
        ToolTip.SetTip(row, string.IsNullOrEmpty(c.Topic) ? ChatFormat.Title(c) : c.Topic);
        return row;
    }

    Control DialogueRow(MessageDialogue d)
    {
        bool open = _pane == Pane.Dialogue && Messages.Current == d.Person.Id;
        var dock = new DockPanel();
        if (d.Unread > 0)
        {
            var pill = Skin.Tag(d.Unread.ToString(), Skin.Accent, Skin.OnAccent);
            pill.VerticalAlignment = VerticalAlignment.Center;
            ToolTip.SetTip(pill, L.T("msgs.unread", d.Unread));
            DockPanel.SetDock(pill, Dock.Right);
            dock.Children.Add(pill);
        }
        dock.Children.Add(new TextBlock
        {
            Text = d.Person.Name, FontSize = 14, TextTrimming = TextTrimming.CharacterEllipsis,
            FontFamily = d.Unread > 0 || open ? Skin.Medium : Skin.Regular, Foreground = Skin.B(Skin.Text),
        });
        var row = ListRow(open, dock, () => _ = OpenDialogueAsync(d.Person.Id, d.Person.Name));
        ToolTip.SetTip(row, (d.LastMine ? L.T("msgs.you", d.Preview) : d.Preview));
        return row;
    }

    // ------------------------------------------------------------------ a channel

    async Task OpenChannelAsync(ChatChannel c, bool join)
    {
        _pane = Pane.Channel;
        _channelId = c.Room;
        _newTo = null;
        _peopleOpen = false;
        _buffer.Reset();
        _info.Clear();
        _lastFeed = null;
        Messages.Close();
        Noticer.Forget(c.Room);
        ShowPane();
        RenderFeed(toEnd: true);
        _input.Focus();
        if (join && !c.Joined && c.CanEnter && Site() is { } s)
        {
            try { await s.Client.ChatJoinAsync(s.Token, c.Room, CancellationToken.None); }
            catch (Exception e) when (Dialogues.Failed(e)) { Status(ChatReason(e)); }
        }
        await RefreshFeedAsync(toEnd: true);
        await ChannelsAsync();
    }

    async Task RefreshFeedAsync(bool toEnd = false)
    {
        if (_feedBusy || _channelId is not { } id || Site() is not { } s) return;
        _feedBusy = true;
        try
        {
            var feed = await s.Client.ChatFeedAsync(s.Token, id, _buffer.Cursor, _buffer.Cursor is null ? ChatRules.HistoryDefault : 200, CancellationToken.None);
            if (_channelId != id || _pane != Pane.Channel) return;
            var fresh = _buffer.Add(feed);
            Noticer.Feed(id, feed.Lines);
            _lastFeed = feed;
            if (_room is { } voiced && voiced.PublicId == feed.Room) _voiceModerator = voiced.Mine || feed.CanModerate;
            RenderFeed(toEnd || fresh.Count > 0 || feed.Removed.Count > 0);
            ShowTopic();
            ShowAttendees();
        }
        catch (PortalException e) when (e.Status == 401)
        {
            await _account.CheckAsync();
            RefreshAll();
            Status(L.T("voice.state.device_unknown"));
        }
        catch (Exception e) when (Dialogues.Failed(e)) { if (Active()) Status(ChatReason(e)); }
        finally { _feedBusy = false; }
    }

    // ------------------------------------------------------------------ the feed on screen

    /// <summary>One line of the feed: time, &lt;nick&gt;, text. Plain text; a service line is grey; a mention has the "selected" fill.</summary>
    Control LineControl(ChatLine l)
    {
        var t = new SelectableTextBlock { TextWrapping = TextWrapping.Wrap, FontSize = 14, LineHeight = 20 };
        var stamp = ChatFormat.Stamp(l.At, DateTimeOffset.Now) + " ";
        t.Inlines!.Add(new Run(stamp) { Foreground = Skin.B(Skin.Dim), FontSize = 12 });
        switch (l.Kind)
        {
            case "system":
                t.Inlines.Add(new Run("-- " + SystemText(l)) { Foreground = Skin.B(Skin.Dim) });
                break;
            case "action":
                t.Inlines.Add(new Run("* " + l.Author.Name + " ") { Foreground = Skin.B(Skin.Teal), FontStyle = FontStyle.Italic });
                t.Inlines.Add(new Run(l.Body) { Foreground = Skin.B(Skin.Text), FontStyle = FontStyle.Italic });
                break;
            default:
                t.Inlines.Add(new Run("<" + l.Author.Name + ">") { Foreground = Skin.B(l.Mine ? Skin.Accent : Skin.Teal), FontFamily = Skin.Medium });
                t.Inlines.Add(new Run(" " + l.Body) { Foreground = Skin.B(Skin.Text) });
                break;
        }
        return new Border { Background = l.Mention ? Skin.B(Skin.Selected) : Brushes.Transparent, CornerRadius = new CornerRadius(4), Padding = new Thickness(4, 1), Child = t };
    }

    static string SystemText(ChatLine l)
    {
        var who = l.Author.Name;
        return l.Event switch
        {
            "info" => l.Body,
            "join" => L.T("chat.ev.join", who),
            "part" => L.T("chat.ev.part", who),
            "topic" => l.Body.Length == 0 ? L.T("chat.ev.topicClear", who) : L.T("chat.ev.topic", who, l.Body),
            "kick" or "ban" or "unban" or "mute" or "unmute" => L.T("chat.ev." + l.Event, who, l.Body),
            _ => L.T("chat.ev.other", who, l.Event ?? "", l.Body).Trim(),
        };
    }

    /// <summary>The feed of the open channel: the lines of the site and, among them by time, the hints this launcher gave.</summary>
    void RenderFeed(bool toEnd)
    {
        var lines = _buffer.Lines.Concat(_info).OrderBy(l => l.At).ToList();
        DrawFeed(lines, toEnd, olderText: null);
    }

    void DrawFeed(IReadOnlyList<ChatLine> lines, bool toEnd, string? olderText)
    {
        bool atEnd = _scroll.Offset.Y + _scroll.Viewport.Height >= _scroll.Extent.Height - 8;
        _older.IsVisible = olderText is not null;
        _older.Content = olderText ?? "";
        _feed.Children.Clear();
        foreach (var l in lines) _feed.Children.Add(LineControl(l));
        if (toEnd || atEnd) Dispatcher.UIThread.Post(() => _scroll.ScrollToEnd(), DispatcherPriority.Background);
    }

    void Info(string text)
    {
        foreach (var part in text.Split('\n'))
            _info.Add(new ChatLine(--_infoId, "system", "info", new VoicePerson(Guid.Empty, ""), part, DateTimeOffset.Now, true, false));
        if (_pane == Pane.Channel) RenderFeed(toEnd: true);
        else if (_pane == Pane.Dialogue) RenderDialogue(toEnd: true);
    }

    // ------------------------------------------------------------------ who is here

    bool IsMe(VoicePerson p) =>
        _buffer.Lines.Any(l => l.Mine && l.Author.Id == p.Id) || (p.Name.Length > 0 && string.Equals(p.Name, MyName, StringComparison.OrdinalIgnoreCase));

    void ShowAttendees()
    {
        _attendees.Children.Clear();
        List<ChatAttendee> list;
        if (_pane == Pane.Channel) list = _lastFeed?.Attendees ?? [];
        else if (_pane == Pane.Dialogue && Messages.Current is { } id)
            list = [new ChatAttendee(new VoicePerson(Guid.Empty, MyName), false, false, false), new ChatAttendee(new VoicePerson(id, Messages.CurrentName), false, false, false)];
        else list = [];
        _attendeesTitle.Text = L.T("chat.here", list.Count).ToUpperInvariant();
        foreach (var a in list) _attendees.Children.Add(AttendeeRow(a));
    }

    Control AttendeeRow(ChatAttendee a)
    {
        var marks = new StackPanel { Orientation = Orientation.Horizontal, Width = 26 };
        marks.Children.Add(new TextBlock { Text = a.Operator ? "@" : " ", Width = 13, Foreground = Skin.B(Skin.Teal), FontFamily = Skin.Medium, FontSize = 14 });
        marks.Children.Add(new TextBlock
        {
            Text = a.Muted ? "−" : a.Voice ? "+" : " ", Width = 13, FontFamily = Skin.Medium, FontSize = 14,
            Foreground = Skin.B(a.Muted ? Skin.WarnText : Skin.Accent),
        });
        var row = new DockPanel();
        DockPanel.SetDock(marks, Dock.Left);
        row.Children.Add(marks);
        row.Children.Add(new TextBlock { Text = a.Person.Name, FontSize = 14, TextTrimming = TextTrimming.CharacterEllipsis, Foreground = Skin.B(Skin.Text) });
        var tip = new List<string>();
        if (a.Operator) tip.Add(L.T("chat.mark.op"));
        if (a.Voice) tip.Add(L.T("chat.mark.voice"));
        if (a.Muted) tip.Add(L.T("chat.mark.muted"));
        var b = Skin.Btn("", "quiet", 28);
        b.Padding = new Thickness(4, 0);
        b.HorizontalAlignment = HorizontalAlignment.Stretch;
        b.HorizontalContentAlignment = HorizontalAlignment.Left;
        b.Content = row;
        if (tip.Count > 0) ToolTip.SetTip(b, string.Join(", ", tip));
        if (a.Person.Id != Guid.Empty && !IsMe(a.Person) && _pane == Pane.Channel) b.Flyout = AttendeeMenu(a);
        return b;
    }

    /// <summary>What can be done with a person of the channel: write to them, complain, and for those who keep the order — the same as the buttons of a room.</summary>
    MenuFlyout AttendeeMenu(ChatAttendee a)
    {
        var menu = new MenuFlyout();
        MenuItem Item(string key, Func<Task> run)
        {
            var i = new MenuItem { Header = L.T(key) };
            i.Click += async (_, _) => await run();
            return i;
        }
        menu.Items.Add(Item("chat.write", () => OpenDialogueAsync(a.Person.Id, a.Person.Name)));
        if (_channelId is { } room)
        {
            menu.Items.Add(Item("voice.complain", () => ModerateAsync(room, a.Person.Id, a.Person.Name, "complain")));
            if (_lastFeed?.CanModerate == true)
            {
                menu.Items.Add(Item(a.Muted ? "voice.unmute" : "voice.mute", () => ModerateAsync(room, a.Person.Id, a.Person.Name, a.Muted ? "unmute" : "mute")));
                menu.Items.Add(Item("voice.kick", () => ModerateAsync(room, a.Person.Id, a.Person.Name, "kick")));
                menu.Items.Add(Item("voice.ban", () => ModerateAsync(room, a.Person.Id, a.Person.Name, "ban")));
            }
        }
        return menu;
    }

    // ------------------------------------------------------------------ the input

    async Task SubmitAsync()
    {
        var typed = ChatInput.Parse(_input.Text);
        if (typed.Kind == ChatInputKind.Empty) return;
        bool done = _pane switch
        {
            Pane.Channel => await SubmitToChannelAsync(typed),
            Pane.Dialogue => await SubmitToDialogueAsync(typed),
            _ => false,
        };
        if (done) _input.Text = "";
    }

    /// <summary>A line or a command for the open channel. False: nothing was done, the text stays in the box.</summary>
    async Task<bool> SubmitToChannelAsync(ChatInput typed)
    {
        if (typed.Kind == ChatInputKind.Client) return await ClientCommandAsync(typed);
        if (_channelId is not { } room || Site() is not { } s) return false;
        ChatPosted posted;
        try { posted = await s.Client.ChatSayAsync(s.Token, room, typed.Text, CancellationToken.None); }
        catch (Exception e) when (Dialogues.Failed(e))
        {
            Status(ChatReason(e));
            return false;
        }
        Status(null);
        switch (posted.Result)
        {
            case "posted" when posted.Line is { } line:
                _buffer.Add(line);
                RenderFeed(toEnd: true);
                break;
            case "private":
                Info(L.T("chat.sentPrivate", posted.Person?.Name ?? ""));
                _ = Messages.LoadInboxAsync();
                break;
            case "topic":
                Info(string.IsNullOrEmpty(posted.Text) ? L.T("chat.topicNone") : L.T("chat.topicIs", posted.Text));
                break;
            case "client":
                return await ClientCommandAsync(ChatInput.Parse("/" + posted.Command + " " + typed.Argument));
            case "unknown":
                // the site did not take it for a line: only the hint is shown
                Info(L.T("chat.unknown", posted.Command ?? typed.Command));
                break;
            default:
                await RefreshFeedAsync(toEnd: true);
                break;
        }
        return true;
    }

    /// <summary>/join /part /who /help: done here, the site is not asked.</summary>
    async Task<bool> ClientCommandAsync(ChatInput typed)
    {
        switch (typed.Command)
        {
            case "join":
            {
                if (typed.Argument.Length == 0) { Info(L.T("chat.joinUsage")); return true; }
                var want = typed.Argument.Trim();
                var all = _list.Channels.Concat(_list.Rooms).ToList();
                var found = all.FirstOrDefault(c => string.Equals(ChatFormat.Title(c), want.StartsWith('#') ? want : "#" + want, StringComparison.CurrentCultureIgnoreCase)
                                                    || string.Equals(c.Title, want, StringComparison.CurrentCultureIgnoreCase)
                                                    || string.Equals(c.Room, want, StringComparison.OrdinalIgnoreCase));
                if (found is null) { Info(L.T("chat.noChannel", want)); return true; }
                await OpenChannelAsync(found, join: true);
                return true;
            }
            case "part":
            {
                if (_pane != Pane.Channel || _channelId is not { } room || Site() is not { } s) { Info(L.T("chat.partNone")); return true; }
                try { await s.Client.ChatPartAsync(s.Token, room, CancellationToken.None); }
                catch (Exception e) when (Dialogues.Failed(e)) { Status(ChatReason(e)); return false; }
                Info(L.T("chat.parted", OpenChannel() is { } c ? ChatFormat.Title(c) : room));
                await ChannelsAsync();
                return true;
            }
            case "who":
            {
                var people = _pane == Pane.Channel ? _lastFeed?.Attendees ?? [] : [];
                Info(people.Count == 0 ? L.T("chat.whoNone")
                    : L.T("chat.who", people.Count, string.Join(", ", people.Select(p => (p.Operator ? "@" : "") + (p.Muted ? "-" : p.Voice ? "+" : "") + p.Person.Name))));
                return true;
            }
            default:
                Info(L.T("chat.help"));
                return true;
        }
    }

    async Task<bool> SubmitToDialogueAsync(ChatInput typed)
    {
        switch (typed.Kind)
        {
            case ChatInputKind.Client:
                return await ClientCommandAsync(typed);
            case ChatInputKind.Server when typed.Command == "msg":
            {
                var space = typed.Argument.IndexOf(' ');
                var who = (space < 0 ? typed.Argument : typed.Argument[..space]).TrimStart('@');
                var text = space < 0 ? "" : typed.Argument[(space + 1)..].Trim();
                if (who.Length == 0 || text.Length == 0) { Info(L.T("chat.msgUsage")); return true; }
                return await Messages.SendToAsync(who, text);
            }
            case ChatInputKind.Server:
                // a slash line is never a message: here only /msg is the site's, the rest is channel business
                Info(L.T("chat.dialogueCommand", typed.Command));
                return true;
        }
        if (Messages.Current is not null) return await Messages.SendAsync(typed.Text);
        if (_newTo is { } to) return await Messages.SendToAsync(to, typed.Text);
        return false;
    }

    // ------------------------------------------------------------------ a dialogue

    async Task OpenDialogueAsync(Guid id, string name)
    {
        _pane = Pane.Dialogue;
        _channelId = null;
        _newTo = null;
        _peopleOpen = false;
        _info.Clear();
        ShowPane();
        _input.Focus();
        await Messages.OpenAsync(id, name);
        await Messages.LoadInboxAsync();
    }

    /// <summary>"Write": asks for a name, then the dialogue is empty until the first line is sent.</summary>
    async Task WriteNewAsync()
    {
        if (TopLevel.GetTopLevel(this) as Window is not { } owner) return;
        var who = await new TextDialog(L.T("msgs.to"), "", 256).ShowDialog<string?>(owner);
        if (string.IsNullOrWhiteSpace(who)) return;
        _pane = Pane.Dialogue;
        _channelId = null;
        _info.Clear();
        Messages.Close();
        _newTo = who.Trim();
        ShowPane();
        RenderDialogue(toEnd: true);
        _input.Focus();
    }

    void OnDialoguesChanged(bool toEnd)
    {
        ShowLeft();
        if (_pane != Pane.Dialogue) return;
        ShowTopic();
        ShowAttendees();
        RenderDialogue(toEnd);
    }

    /// <summary>The open dialogue as lines, in the same form as a channel: time, &lt;nick&gt;, text.</summary>
    void RenderDialogue(bool toEnd)
    {
        var me = new VoicePerson(Guid.Empty, MyName);
        var them = new VoicePerson(Messages.Current ?? Guid.Empty, Messages.Current is not null ? Messages.CurrentName : _newTo ?? "");
        var lines = Messages.Bubbles.Select(b => new ChatLine(0, "text", null, b.Mine ? me : them,
            b.Body + (b.Mine && b.Read ? "  · " + L.T("msgs.readMark") : ""), b.At, b.Mine, false)).Concat(_info).OrderBy(l => l.At).ToList();
        if (Messages.IBlocked) lines.Add(new ChatLine(--_infoId, "system", "info", me, L.T("msgs.youBlocked"), DateTimeOffset.Now, true, false));
        _input.IsEnabled = _send.IsEnabled = !Messages.IBlocked;
        DrawFeed(lines, toEnd, Messages.HasOlder ? L.T("msgs.older", Messages.Bubbles.Count, Messages.Total) : null);
        ShowTopic();
    }

    async Task BlockAsync()
    {
        if (Messages.Current is null || TopLevel.GetTopLevel(this) as Window is not { } owner) return;
        if (!Messages.IBlocked && !await new MessageDialog(L.T("msgs.blockConfirm", Messages.CurrentName), withNo: true).ShowDialog<bool>(owner)) return;
        await Messages.SetBlockedAsync(!Messages.IBlocked);
    }

    async Task ComplainDialogueAsync()
    {
        if (Messages.Current is null || TopLevel.GetTopLevel(this) as Window is not { } owner) return;
        var text = await new TextDialog(L.T("msgs.complainPrompt", Messages.CurrentName), "", MessageRules.ComplaintMax).ShowDialog<string?>(owner);
        if (text is null) return;
        await Messages.ComplainAsync(text);
    }

    /// <summary>From the notice on the home page: the dialogue with the unread messages is opened.</summary>
    public void OpenUnread()
    {
        RefreshAll();
        _ = OpenUnreadAsync();
    }

    async Task OpenUnreadAsync()
    {
        await Messages.LoadInboxAsync();
        var d = Messages.Inbox.FirstOrDefault(x => x.Unread > 0) ?? Messages.Inbox.FirstOrDefault();
        if (d is not null) await OpenDialogueAsync(d.Person.Id, d.Person.Name);
    }

    // ------------------------------------------------------------------ the lobby ("Rooms and people")

    async Task OpenLobbyAsync()
    {
        _pane = Pane.Lobby;
        _channelId = null;
        Messages.Close();
        ShowPane();
        await LoadAsync();
    }

    /// <summary>An xpiratez://voice link: the channel or room opens. Entering its voice is the player's click, never the link's:
    /// a web page must not be able to open the microphone.</summary>
    public void OpenRoom(string publicId)
    {
        _wanted = publicId;
        _autoPicked = true;
        RefreshAll();
        _ = ChannelsAsync();
    }

    static string ChatReason(Exception e)
    {
        if (e is PortalException p)
        {
            if (L.Has("chat.err." + p.Code)) return L.T("chat.err." + p.Code);
            // /msg runs through the private messages and keeps their rules: "msg_limit_unanswered" is theirs
            if (p.Code.StartsWith("msg_", StringComparison.Ordinal) && L.Has("msgs.err." + p.Code[4..])) return L.T("msgs.err." + p.Code[4..]);
        }
        return Dialogues.Reason(e);
    }

    /// <summary>The rooms of the lobby list (mine, invited): they change on the site, so they are asked for each time the lobby opens.</summary>
    async Task LoadAsync()
    {
        if (_loading) return;
        var account = _store.Load();
        if (account is null) return;
        if (Portal() is not { } portal) { Status(L.T("account.noPortal")); return; }
        _token = account.Token;
        _loading = true;
        try
        {
            var client = new PortalClient(Http, portal);
            var rooms = await client.VoiceRoomsAsync(_token, CancellationToken.None);
            _mine = rooms.Owned;
            Fill(_owned, rooms.Owned, "voice.noneMine");
            Fill(_invited, rooms.Invited, "voice.noneInvited");
            Status(null);
            _loading = false;
            await LobbyAsync();
        }
        catch (PortalException e) when (e.Status == 401)
        {
            await _account.CheckAsync();
            RefreshAll();
            Status(L.T("voice.state.device_unknown"));
        }
        catch (Exception e) when (e is HttpRequestException or TaskCanceledException or PortalException)
        {
            Status(Reason(e));
        }
        finally { _loading = false; }
    }

    void Fill(StackPanel list, List<VoiceRoom> rooms, string emptyKey)
    {
        list.Children.Clear();
        if (rooms.Count == 0) list.Children.Add(Skin.Note(L.T(emptyKey)));
        foreach (var r in rooms) list.Children.Add(RoomRow(r));
    }

    Control RoomRow(VoiceRoom r)
    {
        var state = r.InviteDeclined && r.State == "ok" ? L.T("voice.declined") : StateText(r.State == "ok" && r.Status != "open" ? "room_closed" : r.State);
        var line = !r.Mine ? L.T("voice.owner", r.Owner.Name) + " · " + state
            : r.CanJoin ? L.T("voice.youAdmin") : L.T("voice.youAdmin") + " · " + state;

        var buttons = Buttons();
        var join = Skin.Btn(L.T(r.Mine ? "voice.openAdmin" : "voice.join"), "primary");
        join.IsEnabled = r.CanJoin;
        join.Click += async (_, _) => await JoinAsync(r);
        buttons.Children.Add(join);
        if (r.Mine && r.Status != "open")
        {
            var reopen = Skin.Btn(L.T("voice.reopen"));
            reopen.Click += async (_, _) => await Act(c => c.ReopenVoiceRoomAsync(_token, r.PublicId, CancellationToken.None), null);
            buttons.Children.Add(reopen);
        }
        if (!r.Mine && !r.InviteDeclined && r.State is "ok" or "not_friends")
        {
            var decline = Skin.Btn(L.T("voice.decline"), "ghost");
            decline.Click += async (_, _) => await DeclineAsync(r);
            buttons.Children.Add(decline);
        }
        // shut out by a kick or a lost friendship: the owner may still say yes at the door
        if (!r.Mine && r.Status == "open" && r.State is "invite_revoked" or "not_friends")
        {
            var ask = Skin.Btn(L.T("voice.ask"));
            ask.Click += async (_, _) => await AskAsync(r.PublicId);
            buttons.Children.Add(ask);
        }
        return Row(r.Title, line, !r.CanJoin, buttons);
    }

    static StackPanel Buttons(double spacing = 8) =>
        new() { Orientation = Orientation.Horizontal, Spacing = spacing, VerticalAlignment = VerticalAlignment.Center };

    /// <summary>One line of a list: a title and a note under it, the buttons on the right.</summary>
    static Control Row(string title, string line, bool warn, StackPanel buttons, double titleSize = 15)
    {
        var text = new StackPanel { Spacing = 2, VerticalAlignment = VerticalAlignment.Center };
        text.Children.Add(new TextBlock { Text = title, FontSize = titleSize, FontFamily = Skin.Medium, TextWrapping = TextWrapping.Wrap });
        if (line.Length > 0)
            text.Children.Add(new TextBlock { Text = line, FontSize = 12, Foreground = Skin.B(warn ? Skin.WarnText : Skin.Muted), TextWrapping = TextWrapping.Wrap });
        var row = new DockPanel();
        DockPanel.SetDock(buttons, Dock.Right);
        row.Children.Add(buttons);
        row.Children.Add(text);
        return new Border { Background = Skin.B(Skin.Inactive), CornerRadius = new CornerRadius(2), Padding = new Thickness(12, 8), Child = row };
    }

    // ------------------------------------------------------------------ the lobby: open rooms, knocks, who is online

    /// <summary>Every 20 s: "here" to the site once a minute while linked, and a fresh lobby while the page is seen.</summary>
    void Beat()
    {
        if (_store.Load() is not { } account || Portal() is not { } portal) return;
        _token = account.Token;
        // once a minute, seen or not: "here", the list of channels with its counters, the dialogues, the knocks
        if (_beats++ % 3 == 0)
        {
            _ = HereAsync(portal, account.Token);
            _ = BackgroundAsync();
        }
        if (!Active()) return;
        if (_pane == Pane.Lobby) _ = LoadAsync();
        else if (InRoom) _ = LobbyAsync();
    }

    static async Task HereAsync(Uri portal, string token)
    {
        try { await new PortalClient(Http, portal).VoiceHereAsync(token, CancellationToken.None); }
        catch (Exception e) when (e is HttpRequestException or TaskCanceledException or PortalException) { }
    }

    /// <summary>The launcher is closing: off the online list now rather than in two minutes. A second at most.</summary>
    public async Task GoneAsync()
    {
        _beat.Stop();
        if (_store.Load() is not { } account || Portal() is not { } portal) return;
        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(1));
        try { await new PortalClient(Http, portal).VoiceGoneAsync(account.Token, cts.Token); }
        catch (Exception e) when (e is HttpRequestException or TaskCanceledException or OperationCanceledException or PortalException) { }
    }

    async Task LobbyAsync()
    {
        if (_lobbyBusy || _token.Length == 0 || Portal() is not { } portal) return;
        _lobbyBusy = true;
        try
        {
            var lobby = await new PortalClient(Http, portal).VoiceLobbyAsync(_token, CancellationToken.None);
            FillCatalog(lobby.Rooms);
            FillRequests(lobby.Requests);
            FillOnline(lobby.Online);
            _side.IsVisible = true;
        }
        // the rooms' answer already tells what is wrong; a lobby that did not come keeps the last one
        catch (Exception e) when (e is HttpRequestException or TaskCanceledException or PortalException) { }
        finally { _lobbyBusy = false; }
    }

    void FillCatalog(List<VoiceCatalogRoom> rooms)
    {
        _catalog.Children.Clear();
        if (rooms.Count == 0) _catalog.Children.Add(Skin.Note(L.T("voice.noneAll")));
        foreach (var r in rooms)
        {
            var buttons = Buttons();
            var line = L.T("voice.owner", r.Owner.Name);
            if (r.State == "request")
            {
                var ask = Skin.Btn(L.T("voice.ask"), "primary");
                ask.Click += async (_, _) => await AskAsync(r.PublicId);
                buttons.Children.Add(ask);
            }
            else if (r.State == "requested")
            {
                line += " · " + L.T("voice.requested");
                var cancel = Skin.Btn(L.T("voice.askCancel"), "ghost");
                cancel.Click += async (_, _) => await Act(c => c.CancelVoiceRequestAsync(_token, r.PublicId, CancellationToken.None), null);
                buttons.Children.Add(cancel);
            }
            else line += " · " + StateText(r.State);
            _catalog.Children.Add(Row(r.Title, line, r.State == "banned", buttons));
        }
    }

    void FillRequests(List<VoiceJoinRequest> knocks)
    {
        _requests.Children.Clear();
        foreach (var q in knocks)
        {
            var buttons = Buttons();
            var accept = Skin.Btn(L.T("voice.letIn"), "primary", 30);
            accept.Click += async (_, _) => await Act(c => c.AcceptVoiceRequestAsync(_token, q.Room, q.Person.Id, CancellationToken.None),
                L.T("voice.letInDone", q.Person.Name, q.RoomTitle));
            var refuse = Skin.Btn(L.T("voice.refuse"), "ghost", 30);
            refuse.Click += async (_, _) => await Act(c => c.DeclineVoiceRequestAsync(_token, q.Room, q.Person.Id, CancellationToken.None), null);
            var ban = Skin.Btn(L.T("voice.ban"), "warn", 30);
            ban.Click += async (_, _) =>
            {
                if (Owner() is not { } owner) return;
                var reason = await new TextDialog(L.T("voice.banPrompt", q.Person.Name), "", VoiceRules.ReasonMax, allowEmpty: true).ShowDialog<string?>(owner);
                if (reason is null) return;
                await Act(c => c.BanFromVoiceRoomAsync(_token, q.Room, q.Person.Id, reason, CancellationToken.None), null);
            };
            buttons.Children.Add(accept);
            buttons.Children.Add(refuse);
            buttons.Children.Add(ban);
            _requests.Children.Add(Row(q.Person.Name, L.T("voice.knocks", q.RoomTitle), false, buttons, 14));
        }
        _requestsBox.IsVisible = knocks.Count > 0;
        if (_knocks != knocks.Count) { _knocks = knocks.Count; ShowLeft(); }
    }

    void FillOnline(List<VoiceOnline> people)
    {
        _onlineTitle.Text = L.T("voice.online", people.Count);
        _online.Children.Clear();
        if (people.Count == 0) _online.Children.Add(Skin.Note(L.T("voice.nobodyOnline")));
        // where "Invite" takes a friend: the own room I am in, else every open room of mine
        var targets = InRoom && _room is { Mine: true } here ? [here] : _mine.Where(r => r.Status == "open").ToList();
        foreach (var p in people)
        {
            var name = new TextBlock
            {
                Text = "● " + p.Person.Name, FontSize = 14, Foreground = Skin.B(Skin.Accent),
                TextTrimming = TextTrimming.CharacterEllipsis,
            };
            var body = new StackPanel { Spacing = 4 };
            body.Children.Add(name);
            if (p.Friend || p.Asked) body.Children.Add(Skin.Note(L.T(p.Friend ? "voice.friend" : "voice.friendAsked"), 12, Skin.Muted));
            var buttons = Buttons(6);
            if (!p.Friend && !p.Asked)
            {
                var befriend = Skin.Btn(L.T("voice.befriend"), "ghost", 28);
                befriend.Click += async (_, _) => await BefriendAsync(p);
                buttons.Children.Add(befriend);
            }
            if (p.Friend && targets.Count > 0)
            {
                var invite = Skin.Btn(L.T("voice.invite"), "ghost", 28);
                if (targets.Count == 1) invite.Click += async (_, _) => await InviteAsync(p.Person, targets[0]);
                else
                {
                    var menu = new MenuFlyout();
                    foreach (var t in targets)
                    {
                        var item = new MenuItem { Header = t.Title };
                        item.Click += async (_, _) => await InviteAsync(p.Person, t);
                        menu.Items.Add(item);
                    }
                    invite.Flyout = menu;
                }
                buttons.Children.Add(invite);
            }
            if (buttons.Children.Count > 0) body.Children.Add(buttons);
            _online.Children.Add(new Border { Background = Skin.B(Skin.Inactive), CornerRadius = new CornerRadius(2), Padding = new Thickness(10, 6), Child = body });
        }
    }

    /// <summary>One call to the site from a button, then the lists again; a refusal is read in the status line.</summary>
    async Task Act(Func<PortalClient, Task> call, string? done)
    {
        if (Portal() is not { } portal) return;
        try
        {
            await call(new PortalClient(Http, portal));
            Status(done, warn: false);
        }
        catch (Exception e) when (e is HttpRequestException or TaskCanceledException or PortalException) { Status(Reason(e)); }
        await LoadAsync();
        if (InRoom) await LiveAsync();
    }

    Task AskAsync(string publicId) => Act(async c =>
    {
        var r = await c.AskToEnterVoiceRoomAsync(_token, publicId, CancellationToken.None);
        Status(L.T(r == "already" ? "voice.askAlready" : "voice.asked"), warn: false);
    }, null);

    Task BefriendAsync(VoiceOnline p) => Act(async c =>
    {
        var r = await c.RequestFriendAsync(_token, p.Person.Id.ToString(), CancellationToken.None);
        Status(L.T(r == "accepted" ? "voice.friendsNow" : "voice.friendSent", p.Person.Name), warn: false);
    }, null);

    Task InviteAsync(VoicePerson who, VoiceRoom room) =>
        Act(c => c.InviteToVoiceRoomAsync(_token, room.PublicId, who.Id, CancellationToken.None), L.T("voice.invitedDone", who.Name, room.Title));

    static string StateText(string state) =>
        L.Has("voice.state." + state) ? L.T("voice.state." + state) : L.T("voice.state.other", state);

    static string Reason(Exception e) => e switch
    {
        PortalException p when p.Status == 429 => L.T("voice.busy"),
        PortalException p when p.Code == "voice_unavailable" => L.T("voice.unavailable"),
        PortalException p => L.Has("voice.err." + p.Code) ? L.T("voice.err." + p.Code) : L.T("account.error", p.Code),
        _ => L.T("account.offline"),
    };

    async Task CreateAsync()
    {
        if (Portal() is not { } portal || Owner() is not { } owner) return;
        var title = await new TextDialog(L.T("voice.createPrompt"), "", VoiceRules.TitleMax).ShowDialog<string?>(owner);
        if (title is null) return;
        try
        {
            // "open your room": made and entered at once, the owner is its admin
            var room = await new PortalClient(Http, portal).CreateVoiceRoomAsync(_token, title, CancellationToken.None);
            await ChannelsAsync();
            if (_list.Rooms.FirstOrDefault(r => r.Room == room.PublicId) is { } row) await OpenChannelAsync(row, join: true);
            Status(L.T("voice.created", room.Title), warn: false);
            await JoinAsync(room);
        }
        catch (Exception e) when (e is HttpRequestException or TaskCanceledException or PortalException) { Status(Reason(e)); }
    }

    async Task DeclineAsync(VoiceRoom r)
    {
        if (Portal() is not { } portal) return;
        try
        {
            await new PortalClient(Http, portal).DeclineVoiceInviteAsync(_token, r.PublicId, CancellationToken.None);
            if (_wanted == r.PublicId) _wanted = null;
            await LoadAsync();
        }
        catch (Exception e) when (e is HttpRequestException or TaskCanceledException or PortalException) { Status(Reason(e)); }
    }

    Window? Owner() => TopLevel.GetTopLevel(this) as Window;

    // ------------------------------------------------------------------ the room

    async Task JoinAsync(VoiceRoom room)
    {
        if (Portal() is not { } portal || _store.Load() is not { } account) return;
        if (InRoom) await LeaveAsync();
        StopCheck();
        _token = account.Token;
        var client = new PortalClient(Http, portal);
        string publicId = room.PublicId;
        var opt = new VoiceOptions
        {
            // a pass for every entry, the reconnections included: a ban or a taken right to speak holds
            // from the next one on, and nothing that lets anybody in is kept on this machine
            Pass = async ct =>
            {
                try
                {
                    var p = await client.VoicePassAsync(_token, publicId, ct);
                    _unavailable = false;
                    _canPublish = p.CanPublish;
                    _me = p.Identity;
                    return new VoicePass(p.Url, p.Token);
                }
                catch (VoicePassRefusedException e) { throw new VoiceDeniedException(e.Code); }
                catch (Exception e)
                {
                    // the session asks again either way; the person reads why: the station's probe gives passes
                    // to its testers only, and a media server that is down answers the same 503 - not "no connection"
                    _unavailable = e is PortalException { Code: "voice_unavailable" };
                    throw;
                }
            },
            OutputGain = (float)Math.Clamp(_settings.VoiceVolume, 0, 2),
            InputId = _settings.VoiceInputId, InputName = _settings.VoiceInputName,
            OutputId = _settings.VoiceOutputId, OutputName = _settings.VoiceOutputName,
        };
        _unavailable = false;                // before Start: the first pass may come back before the lines below
        var s = new VoiceSession(opt);
        s.Denied += reason => Dispatcher.UIThread.Post(() => _ = EndAsync(s, StateText(reason), reason == VoiceDeniedException.DeviceUnknown));
        s.SentAway += why => Dispatcher.UIThread.Post(() => _ = EndAsync(s, L.Has("voice.away." + why) ? L.T("voice.away." + why) : L.T("voice.away.other"), false));
        foreach (var (id, v) in _settings.VoicePeerVolume) s.SetPeerVolume(id, (float)v);
        s.Muted = !_settings.VoiceOpenMic;
        // anything at all: the sound card, the native parts, the LiveKit runtime - a click handler that
        // throws would take the whole launcher down, and voice failing must only fail voice
        try { s.Start(); }
        catch (Exception e)
        {
            await Dispose(s);
            Status(L.T("voice.noSound", e.Message));
            return;
        }
        _session = s;
        _room = room;
        _canPublish = true;
        _me = "";
        _live = new(StringComparer.Ordinal);
        _wanted = null;
        _rows.Clear();
        _people.Children.Clear();
        _voiceModerator = room.Mine || (_lastFeed is { } f && f.Room == room.PublicId && f.CanModerate);
        Status(null);
        FollowKey();
        ShowMicToggle();
        ShowCheck();
        ShowDeviceNote();
        ShowPane();
        _ticks = 0;
        _timer.Start();
        Tick();
        RoomChanged?.Invoke();
    }

    /// <summary>Leaves the room and gives the microphone back. Safe to call when not in a room.</summary>
    public Task LeaveAsync() => _session is { } s ? EndAsync(s, null, false) : Task.CompletedTask;

    async Task EndAsync(VoiceSession s, string? why, bool unlinked)
    {
        if (!ReferenceEquals(_session, s)) return;   // a Denied after the player already left
        _session = null;
        TalkHook.StopFollowing();
        if (_micCheck is null) _timer.Stop();
        RoomChanged?.Invoke();
        await Dispose(s);
        _room = null;
        _voiceModerator = false;
        foreach (var r in _rows.Values) _people.Children.Remove(r.Root);
        _rows.Clear();
        ShowCheck();
        ShowDeviceNote();
        ShowPane();
        if (unlinked) await _account.CheckAsync();
        RefreshAll();
        if (why is not null) Status(why);
    }

    /// <summary>The session waits up to 8 s for its room loop; a loop that hangs past that must not stop the leaving.</summary>
    static async Task Dispose(VoiceSession s)
    {
        try { await s.DisposeAsync(); }
        catch (TimeoutException) { }
    }

    void Tick()
    {
        if (_micCheck is { } check)
        {
            _checkLevel.Value = Math.Max(-60, check.LevelDb);
            return;
        }
        if (_session is not { } s) return;
        bool down = s.DeviceDown;
        var state = down ? L.T("voice.conn.device", s.DeviceDownSeconds) : s.State switch
        {
            VoiceState.Connecting => L.T("voice.conn.connecting"),
            VoiceState.Connected => L.T("voice.conn.connected"),
            VoiceState.Reconnecting => L.T("voice.conn.reconnecting"),
            _ => L.T(_unavailable ? "voice.conn.unavailable" : "voice.conn.disconnected"),
        };
        _connection.Text = _room is { } at ? at.Title + " · " + state : state;
        _connection.Foreground = Skin.B(s.State == VoiceState.Connected && !down ? Skin.Accent : Skin.WarnText);
        _micLevel.Value = s.Muted ? -60 : Math.Max(-60, s.MicDb);
        ShowMicNote(s);

        var peers = s.Peers();
        var seen = new HashSet<string>(StringComparer.Ordinal);
        foreach (var p in peers)
        {
            if (p.Identity == _me) continue;
            seen.Add(p.Identity);
            Row(p.Identity).Update(p, _live.GetValueOrDefault(p.Identity));
        }
        // somebody the site lists in the room before their sound arrives
        if (_me.Length > 0)
            foreach (var (id, l) in _live)
                if (id != _me && seen.Add(id)) Row(id).Update(null, l);
        foreach (var gone in _rows.Keys.Where(k => !seen.Contains(k)).ToList())
        {
            _people.Children.Remove(_rows[gone].Root);
            _rows.Remove(gone);
        }
        _alone.IsVisible = _rows.Count == 0;

        if (_ticks++ % 25 == 0) _ = LiveAsync();
    }

    PeerRow Row(string identity)
    {
        if (_rows.TryGetValue(identity, out var r)) return r;
        r = new PeerRow(this, identity);
        _rows[identity] = r;
        _people.Children.Add(r.Root);
        return r;
    }

    /// <summary>Names and rights of who is in the room, every 5 s: the media server knows ids only.</summary>
    async Task LiveAsync()
    {
        if (_liveBusy || _room is not { } room || Portal() is not { } portal) return;
        _liveBusy = true;
        try
        {
            var live = await new PortalClient(Http, portal).VoiceLiveAsync(_token, room.PublicId, CancellationToken.None);
            if (ReferenceEquals(room, _room)) _live = live.ToDictionary(l => l.Person.Id.ToString(), StringComparer.Ordinal);
        }
        catch (Exception e) when (e is HttpRequestException or TaskCanceledException or PortalException) { }
        finally { _liveBusy = false; }
    }

    void ShowMicNote(VoiceSession s)
    {
        string text;
        bool warn = true;
        if (!_canPublish) text = L.T("voice.cantSpeak");
        else if (s.MicrophoneMissing) text = L.T("voice.micMissing");
        else if (_hookFailed && !_settings.VoiceOpenMic) text = L.T("voice.hookFailed");
        else if (!_settings.VoiceOpenMic)
        {
            warn = false;
            text = s.Muted ? L.T("voice.pttHold", TalkHook.Name(Key())) : L.T("voice.talking");
        }
        else { warn = false; text = s.Muted ? L.T("voice.silent") : L.T("voice.talking"); }
        _micNote.Text = text;
        _micNote.Foreground = Skin.B(warn ? Skin.WarnText : !s.Muted ? Skin.Accent : Skin.Text2);
    }

    /// <summary>Voice is a button of the channel: "Join voice" under its feed. In a room the bar also has the way out, the microphone and the state.</summary>
    void ShowVoiceBar()
    {
        bool inRoom = InRoom;
        var channel = _pane == Pane.Channel ? OpenChannel() : null;
        _voiceJoin.IsVisible = channel is not null && (!inRoom || _room?.PublicId != channel.Room);
        _voiceJoin.IsEnabled = channel is { CanEnter: true };
        _voiceJoin.Content = L.T(inRoom ? "chat.voiceSwitch" : "chat.voiceJoin");
        _voiceLeave.IsVisible = _connection.IsVisible = _micLevel.IsVisible = _micNote.IsVisible = inRoom;
        ShowMicToggle();
    }

    async Task JoinVoiceHereAsync()
    {
        if (OpenChannel() is not { } c) return;
        await JoinAsync(new VoiceRoom(c.Room, ChatFormat.Title(c), c.Owner, c.Mine, "open", c.State, false, 0, DateTimeOffset.UtcNow));
    }

    void ShowMicToggle()
    {
        _micToggle.IsVisible = _settings.VoiceOpenMic && InRoom;
        _micToggle.Content = L.T(_session?.Muted == true ? "voice.micUnmute" : "voice.micMute");
    }

    // ------------------------------------------------------------------ the people in the room

    /// <summary>A person of the voice room (the peer rows): the same actions as for a person of the text channel.</summary>
    Task ModerateAsync(string identity, string kind) =>
        _room is { } room && Guid.TryParse(identity, out var user) ? ModerateAsync(room.PublicId, user, NameOf(identity), kind) : Task.CompletedTask;

    /// <summary>Mute, unmute, kick, ban and complain: for a room I own, or in a public channel for staff. The site checks the right again.</summary>
    async Task ModerateAsync(string roomId, Guid user, string name, string kind)
    {
        if (Site() is not { } s || Owner() is not { } owner) return;
        var client = s.Client;
        var token = s.Token;
        try
        {
            switch (kind)
            {
                case "unmute":
                    await client.SetVoiceSpeakingAsync(token, roomId, user, true, null, CancellationToken.None);
                    break;
                case "complain":
                    var text = await new TextDialog(L.T("voice.complainPrompt", name), "", VoiceRules.ComplaintMax).ShowDialog<string?>(owner);
                    if (text is null) return;
                    var c = await client.ComplainInVoiceRoomAsync(token, roomId, user, text, CancellationToken.None);
                    Status(L.T("voice.complained", c.DisplayNumber), warn: false);
                    return;
                default:
                    var reason = await new TextDialog(L.T("voice." + kind + "Prompt", name), "", VoiceRules.ReasonMax, allowEmpty: true).ShowDialog<string?>(owner);
                    if (reason is null) return;
                    if (kind == "mute") await client.SetVoiceSpeakingAsync(token, roomId, user, false, reason, CancellationToken.None);
                    else if (kind == "kick") await client.KickFromVoiceRoomAsync(token, roomId, user, reason, CancellationToken.None);
                    else await client.BanFromVoiceRoomAsync(token, roomId, user, reason, CancellationToken.None);
                    break;
            }
            Status(null);
            if (InRoom) await LiveAsync();
            await RefreshFeedAsync(toEnd: true);
        }
        catch (Exception e) when (e is HttpRequestException or TaskCanceledException or PortalException) { Status(Reason(e)); }
    }

    string NameOf(string identity) =>
        _live.TryGetValue(identity, out var l) ? l.Person.Name : L.T("voice.someone");

    void PeerVolume(string identity, double gain)
    {
        _session?.SetPeerVolume(identity, (float)gain);
        if (Math.Abs(gain - 1) < 0.001) _settings.VoicePeerVolume.Remove(identity);
        else _settings.VoicePeerVolume[identity] = gain;
    }

    /// <summary>One person in the room: built once and updated in place, so a slider being dragged survives the refresh.</summary>
    sealed class PeerRow
    {
        public readonly Border Root;
        readonly VoicePage _page;
        readonly string _id;
        readonly TextBlock _name = new() { FontSize = 14, VerticalAlignment = VerticalAlignment.Center, TextTrimming = TextTrimming.CharacterEllipsis };
        readonly TextBlock _state = new() { FontSize = 12, Foreground = Skin.B(Skin.Muted), VerticalAlignment = VerticalAlignment.Center };
        readonly Slider _gain = new() { Minimum = 0, Maximum = 200, Width = 140, VerticalAlignment = VerticalAlignment.Center };
        readonly Button _off, _speak, _kick, _ban, _complain;
        bool _canPublish = true;
        double _back = 100;

        public PeerRow(VoicePage page, string id)
        {
            _page = page;
            _id = id;
            double g = page._settings.VoicePeerVolume.GetValueOrDefault(id, 1);
            _gain.Value = Math.Clamp(g, 0, 2) * 100;
            _gain.ValueChanged += (_, _) =>
            {
                page.PeerVolume(id, _gain.Value / 100);
                ShowOff();
                page.SaveSoon();
            };
            _off = Skin.Btn("", "ghost", 30);
            _off.Click += (_, _) =>
            {
                // switched off at this machine only (nobody is told): the volume goes to 0 and is kept so
                // for the next time; back on is as loud as it was before
                if (_gain.Value > 0) { _back = _gain.Value; _gain.Value = 0; }
                else _gain.Value = _back > 0 ? _back : 100;
            };
            _speak = Skin.Btn("", "ghost", 30);
            _speak.Click += async (_, _) => await page.ModerateAsync(id, _canPublish ? "mute" : "unmute");
            _kick = Skin.Btn(L.T("voice.kick"), "ghost", 30);
            _kick.Click += async (_, _) => await page.ModerateAsync(id, "kick");
            _ban = Skin.Btn(L.T("voice.ban"), "warn", 30);
            _ban.Click += async (_, _) => await page.ModerateAsync(id, "ban");
            _complain = Skin.Btn(L.T("voice.complain"), "ghost", 30);
            _complain.Click += async (_, _) => await page.ModerateAsync(id, "complain");
            Moderation();

            // three short lines: the right column is narrow
            var who = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8 };
            who.Children.Add(_name);
            who.Children.Add(_state);
            _gain.Width = double.NaN;
            _gain.HorizontalAlignment = HorizontalAlignment.Stretch;
            var vol = new Grid { ColumnDefinitions = new ColumnDefinitions("*,Auto") };
            vol.Children.Add(_gain);
            _off.Margin = new Thickness(6, 0, 0, 0);
            Grid.SetColumn(_off, 1);
            vol.Children.Add(_off);
            var acts = new WrapPanel { Orientation = Orientation.Horizontal };
            foreach (var b in new[] { _speak, _kick, _ban, _complain })
            {
                b.Margin = new Thickness(0, 0, 6, 4);
                acts.Children.Add(b);
            }
            var body = new StackPanel { Spacing = 4 };
            body.Children.Add(who);
            body.Children.Add(vol);
            body.Children.Add(acts);
            Root = new Border { Background = Skin.B(Skin.Hover), CornerRadius = new CornerRadius(6), Padding = new Thickness(10, 6), Child = body };
            ShowOff();
        }

        void ShowOff() => _off.Content = L.T(_gain.Value > 0 ? "voice.peerOff" : "voice.peerOn");

        /// <summary>Mute, kick and ban for whoever keeps the order of the room (its owner, or staff in a public channel); a complaint for the rest.</summary>
        void Moderation()
        {
            bool keeper = _page._voiceModerator;
            _speak.IsVisible = _kick.IsVisible = _ban.IsVisible = keeper;
            _complain.IsVisible = !keeper;
        }

        public void Update(PeerView? p, VoiceLive? live)
        {
            Moderation();
            bool speaking = p?.Speaking == true && _gain.Value > 0;
            _name.Text = (speaking ? "● " : "○ ") + (live?.Person.Name ?? _page.NameOf(_id));
            _name.Foreground = Skin.B(speaking ? Skin.Accent : Skin.Text);
            _canPublish = live?.CanPublish ?? true;
            var notes = new List<string>();
            if (!_canPublish) notes.Add(L.T("voice.noRight"));
            else if (p?.Muted == true) notes.Add(L.T("voice.micOff"));
            if (_gain.Value <= 0) notes.Add(L.T("voice.offHere"));
            _state.Text = string.Join(" · ", notes);
            _speak.Content = L.T(_canPublish ? "voice.mute" : "voice.unmute");
        }
    }

    // ------------------------------------------------------------------ sound and the key

    void FillDevices()
    {
        if (_devicesFilled) return;
        IReadOnlyList<AudioDeviceInfo> list;
        try { list = AudioDevice.List(); }
        catch (Exception e) when (e is DllNotFoundException or EntryPointNotFoundException or IOException)
        {
            _deviceNote.Text = L.T("voice.noSound", e.Message);
            return;
        }
        _devicesFilled = true;
        _filling = true;
        FillBox(_inputDevice, list.Where(d => d.IsCapture), _settings.VoiceInputId, _settings.VoiceInputName);
        FillBox(_output, list.Where(d => !d.IsCapture), _settings.VoiceOutputId, _settings.VoiceOutputName);
        _filling = false;

        static void FillBox(ComboBox box, IEnumerable<AudioDeviceInfo> devices, string? id, string? name)
        {
            box.Items.Clear();
            box.Items.Add(new ComboBoxItem { Content = L.T("voice.default"), Tag = null });
            int pick = 0;
            foreach (var d in devices)
            {
                box.Items.Add(new ComboBoxItem { Content = d.Name, Tag = d });
                if ((id is not null && d.Id == id) || (pick == 0 && name is not null && d.Name == name)) pick = box.Items.Count - 1;
            }
            // a chosen device that is gone now: kept in the settings (it may come back), shown as itself
            if (pick == 0 && (id ?? name) is not null)
            {
                box.Items.Add(new ComboBoxItem { Content = L.T("voice.absent", name ?? id!), Tag = "absent" });
                pick = box.Items.Count - 1;
            }
            box.SelectedIndex = pick;
        }
    }

    void DeviceChosen(ComboBox box, bool capture)
    {
        if (_filling || box.SelectedItem is not ComboBoxItem item || item.Tag is "absent") return;
        var d = item.Tag as AudioDeviceInfo;
        if (capture) { _settings.VoiceInputId = d?.Id; _settings.VoiceInputName = d?.Name; }
        else { _settings.VoiceOutputId = d?.Id; _settings.VoiceOutputName = d?.Name; }
        Save();
        ShowDeviceNote();
        if (_micCheck is not null) { StopCheck(); ToggleCheck(); }
    }

    void ShowDeviceNote()
    {
        if (!_devicesFilled) return;
        _deviceNote.Text = InRoom ? L.T("voice.nextEntry") : "";
        _deviceNote.IsVisible = _deviceNote.Text.Length > 0;
    }

    void ToggleCheck()
    {
        if (_micCheck is not null) { StopCheck(); return; }
        if (InRoom) return;
        var c = new MicCheck();
        try { c.Start(_settings.VoiceInputId, _settings.VoiceInputName, _settings.VoiceOutputId, _settings.VoiceOutputName); }
        catch (Exception e) when (e is IOException or DllNotFoundException or EntryPointNotFoundException)
        {
            c.Dispose();
            _checkNote.Text = L.T("voice.noSound", e.Message);
            return;
        }
        _micCheck = c;
        _timer.Start();
        ShowCheck();
    }

    void StopCheck()
    {
        if (_micCheck is not { } c) return;
        _micCheck = null;
        c.Dispose();
        if (!InRoom) _timer.Stop();
        _checkLevel.Value = -60;
        ShowCheck();
    }

    void ShowCheck()
    {
        _check.IsEnabled = !InRoom;
        _check.Content = L.T(_micCheck is null ? "voice.check" : "voice.checkStop");
        _checkLevel.IsVisible = _micCheck is not null;
        _checkNote.Text = InRoom ? L.T("voice.checkBusy")
            : _micCheck is { MicrophoneMissing: true } ? L.T("voice.micMissingCheck")
            : _micCheck is not null ? L.T("voice.checkHint") : "";
        _checkNote.IsVisible = _checkNote.Text.Length > 0;
    }

    /// <summary>Called when the page is left or the window goes to the tray: the check must not hold the microphone.</summary>
    public void Hidden() => StopCheck();

    TalkKey Key() => TalkKey.Parse(_settings.VoiceKey) ?? TalkKey.Default;

    void ModeChanged()
    {
        _settings.VoiceOpenMic = _modeOpen.IsChecked == true;
        Save();
        if (_session is { } s)
        {
            // open microphone: on until switched off; push-to-talk: off until the key is held
            s.Muted = !_settings.VoiceOpenMic;
            FollowKey();
            ShowMicToggle();
        }
        ShowKey();
    }

    void FollowKey()
    {
        TalkHook.StopFollowing();
        _hookFailed = false;
        if (_session is null || _settings.VoiceOpenMic) return;
        _hookFailed = !TalkHook.Follow(Key(), down =>
        {
            if (_session is { } s) s.Muted = !down;
        });
    }

    void Assign()
    {
        _assign.IsEnabled = false;
        _keyName.Text = L.T("voice.assignWait");
        TalkHook.StopFollowing();
        bool ok = TalkHook.Capture(key =>
        {
            if (key is { } k)
            {
                _settings.VoiceKey = k.ToString();
                Save();
            }
            _assign.IsEnabled = true;
            ShowKey();
            FollowKey();
        });
        if (ok) return;
        TalkHook.CancelCapture();
        _assign.IsEnabled = true;
        _hookFailed = true;
        ShowKey();
        FollowKey();
    }

    void ShowKey()
    {
        var key = Key();
        _keyName.Text = L.T("voice.key", TalkHook.Name(key));
        bool ptt = !_settings.VoiceOpenMic;
        _keyName.Opacity = _assign.Opacity = ptt ? 1 : 0.5;
        if (_hookFailed) { _keyNote.Text = L.T("voice.hookFailed"); _keyNote.Foreground = Skin.B(Skin.WarnText); }
        else
        {
            var taken = _builds() is { } b ? GameKeys.Conflicts(key, b) : GameKeys.Conflicts(key, (string?)null);
            _keyNote.Text = taken.Count > 0 ? L.T("voice.conflict", string.Join(", ", taken)) : "";
            _keyNote.Foreground = Skin.B(Skin.WarnText);
        }
        _keyNote.IsVisible = ptt && _keyNote.Text.Length > 0;
    }
}
