using Avalonia;
using Avalonia.Controls;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Threading;
using Xp.Launcher.Core;
using Xp.Voice;

namespace Xp.Launcher;

/// <summary>
/// Voice rooms (docs/portal/VOICE_CHAT.md §5): the rooms of the linked account, one room at a time,
/// push-to-talk by default. Who may come in is the site's business: the launcher asks it for a pass at
/// every entry and keeps nothing. Friends and invitations are managed on the site.
/// </summary>
public sealed class VoicePage : UserControl
{
    static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(30) };

    readonly Settings _settings;
    readonly DeviceStore _store = new(Path.Combine(Settings.Dir, "device.json"));
    readonly AccountPanel _account;
    readonly Func<BuildStore?> _builds;

    readonly TextBlock _status = new() { FontSize = 13, TextWrapping = TextWrapping.Wrap, IsVisible = false };
    readonly StackPanel _unlinked = new() { Spacing = 12, IsVisible = false };
    readonly StackPanel _lobby = new() { Spacing = 12, IsVisible = false };
    readonly StackPanel _roomPanel = new() { Spacing = 12, IsVisible = false };
    readonly StackPanel _owned = new() { Spacing = 8 }, _invited = new() { Spacing = 8 };
    readonly Border _linked;
    readonly StackPanel _linkedBody = new() { Spacing = 8 };

    // in the room
    readonly TextBlock _roomTitle = new() { FontFamily = Skin.Medium, FontSize = 20, TextWrapping = TextWrapping.Wrap };
    readonly TextBlock _connection = new() { FontSize = 13 };
    readonly TextBlock _micNote = new() { FontSize = 13, TextWrapping = TextWrapping.Wrap };
    readonly ProgressBar _micLevel = new() { Minimum = -60, Maximum = 0, Height = 8, MinWidth = 220, VerticalAlignment = VerticalAlignment.Center };
    readonly Button _micToggle;
    readonly StackPanel _people = new() { Spacing = 8 };
    readonly TextBlock _alone = Skin.Note(L.T("voice.alone"));
    readonly Dictionary<string, PeerRow> _rows = new(StringComparer.Ordinal);

    // sound and key
    readonly ComboBox _input = new() { HorizontalAlignment = HorizontalAlignment.Stretch, FontSize = 13 };
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
    Dictionary<string, VoiceLive> _live = new(StringComparer.Ordinal);
    int _ticks;
    bool _liveBusy, _loading, _filling, _devicesFilled;
    MicCheck? _micCheck;
    string? _wanted;                        // the room of an xpiratez:// link, shown on top until entered
    bool _hookFailed;

    /// <summary>Entered or left a room: the window decides about the tray by it.</summary>
    public event Action? RoomChanged;
    public bool InRoom => _session is not null;
    public string? RoomTitle => _room?.Title;

    public VoicePage(Settings settings, AccountPanel account, Func<BuildStore?> builds, Action openSettings)
    {
        _settings = settings;
        _account = account;
        _builds = builds;
        _account.Changed += () => { if (IsVisible && !InRoom) _ = LoadAsync(); };

        // --- not linked
        _unlinked.Children.Add(Skin.Note(L.T("voice.unlinked"), 14, Skin.Text2));
        var toSettings = Skin.Btn(L.T("voice.toSettings"), "primary");
        toSettings.Click += (_, _) => openSettings();
        _unlinked.Children.Add(toSettings);

        // --- the lobby
        var create = Skin.Btn(L.T("voice.create"), "primary");
        create.Click += async (_, _) => await CreateAsync();
        var refresh = Skin.Btn(L.T("voice.refresh"), "ghost");
        refresh.Click += async (_, _) => await LoadAsync();
        var actions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 10 };
        actions.Children.Add(create);
        actions.Children.Add(refresh);
        actions.Children.Add(Skin.Link(L.T("voice.friendsSite") + "  ↗", () => { if (SiteVoiceUrl() is { } u) ReportWindow.OpenUrl(u); }));
        _lobby.Children.Add(actions);
        _linked = Skin.Panel(_linkedBody);
        _linked.IsVisible = false;
        _lobby.Children.Add(_linked);
        _lobby.Children.Add(Skin.H2(L.T("voice.mine")));
        _lobby.Children.Add(_owned);
        _lobby.Children.Add(Skin.H2(L.T("voice.invited")));
        _lobby.Children.Add(_invited);

        // --- in the room
        var leave = Skin.Btn(L.T("voice.leave"), "warn");
        leave.Click += async (_, _) => await LeaveAsync();
        var head = new DockPanel();
        DockPanel.SetDock(leave, Dock.Right);
        head.Children.Add(leave);
        var titles = new StackPanel { Spacing = 2 };
        titles.Children.Add(_roomTitle);
        titles.Children.Add(_connection);
        head.Children.Add(titles);
        _micToggle = Skin.Btn(L.T("voice.micMute"));
        _micToggle.Click += (_, _) =>
        {
            if (_session is not { } s) return;
            s.Muted = !s.Muted;
            ShowMicToggle();
        };
        var micRow = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 12 };
        micRow.Children.Add(_micLevel);
        micRow.Children.Add(_micToggle);
        var roomBody = new StackPanel { Spacing = 12 };
        roomBody.Children.Add(head);
        roomBody.Children.Add(micRow);
        roomBody.Children.Add(_micNote);
        roomBody.Children.Add(Skin.H2(L.T("voice.people")));
        roomBody.Children.Add(_alone);
        roomBody.Children.Add(_people);
        _roomPanel.Children.Add(Skin.Panel(roomBody));

        // --- sound and the key: in the lobby and in the room
        _check = Skin.Btn(L.T("voice.check"));
        _check.Click += (_, _) => ToggleCheck();
        _assign = Skin.Btn(L.T("voice.assign"));
        _assign.Click += (_, _) => Assign();
        _volume.Value = Math.Clamp(_settings.VoiceVolume, 0, 2) * 100;
        _volume.ValueChanged += (_, _) =>
        {
            _settings.VoiceVolume = _volume.Value / 100;
            if (_session is { } s) s.Volume = (float)_settings.VoiceVolume;
            SaveSoon();
        };
        _input.SelectionChanged += (_, _) => DeviceChosen(_input, capture: true);
        _output.SelectionChanged += (_, _) => DeviceChosen(_output, capture: false);
        (_settings.VoiceOpenMic ? _modeOpen : _modePtt).IsChecked = true;
        _modePtt.IsCheckedChanged += (_, _) => ModeChanged();

        var sound = new StackPanel { Spacing = 10 };
        sound.Children.Add(Skin.H2(L.T("voice.sound")));
        sound.Children.Add(Labeled("voice.input", _input));
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
        var keyRow = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 12, Margin = new Thickness(28, 0, 0, 0) };
        keyRow.Children.Add(_keyName);
        keyRow.Children.Add(_assign);
        sound.Children.Add(keyRow);
        sound.Children.Add(_keyNote);
        sound.Children.Add(_modeOpen);

        var panel = new StackPanel { Spacing = 14, Margin = new Thickness(28, 24, 28, 28), MaxWidth = 820, HorizontalAlignment = HorizontalAlignment.Left };
        panel.Children.Add(Skin.H1(L.T("voice.title")));
        panel.Children.Add(Skin.Note(L.T("voice.hint"), 14, Skin.Text2));
        panel.Children.Add(_status);
        panel.Children.Add(_unlinked);
        panel.Children.Add(_lobby);
        panel.Children.Add(_roomPanel);
        var soundPanel = Skin.Panel(sound);
        panel.Children.Add(soundPanel);
        Content = new ScrollViewer { Content = panel };

        _timer.Tick += (_, _) => Tick();
        ShowKey();
        ShowCheck();
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

    // ------------------------------------------------------------------ the lobby

    /// <summary>The page was opened: the devices once, the rooms every time (they change on the site).</summary>
    public void Shown()
    {
        FillDevices();
        ShowKey();
        if (!InRoom) _ = LoadAsync();
    }

    /// <summary>An xpiratez://voice link: the room goes on top of the lobby with its "Join". Entering is
    /// the player's click, never the link's: a web page must not be able to open the microphone.</summary>
    public void OpenRoom(string publicId)
    {
        _wanted = publicId;
        if (!InRoom) _ = LoadAsync();
        else Status(L.T("voice.linkWhileIn"), warn: false);
    }

    async Task LoadAsync()
    {
        if (_loading || InRoom) return;
        var account = _store.Load();
        _unlinked.IsVisible = account is null;
        _lobby.IsVisible = account is not null;
        _roomPanel.IsVisible = false;
        if (account is null) return;
        if (Portal() is not { } portal) { Status(L.T("account.noPortal")); return; }
        _token = account.Token;
        _loading = true;
        try
        {
            var client = new PortalClient(Http, portal);
            var rooms = await client.VoiceRoomsAsync(_token, CancellationToken.None);
            Fill(_owned, rooms.Owned, "voice.noneMine");
            Fill(_invited, rooms.Invited, "voice.noneInvited");
            _linked.IsVisible = false;
            if (_wanted is { } id)
            {
                var known = rooms.Owned.Concat(rooms.Invited).FirstOrDefault(r => r.PublicId == id);
                VoiceRoom? room = known;
                if (room is null)
                    try { room = (await client.VoiceRoomAsync(_token, id, CancellationToken.None)).Room; }
                    catch (PortalException e) when (e.Status == 404) { }
                _linkedBody.Children.Clear();
                _linkedBody.Children.Add(Skin.H2(L.T("voice.linkRoom")));
                if (room is null) _linkedBody.Children.Add(Skin.Note(L.T("voice.linkMissing"), 13, Skin.WarnText));
                else _linkedBody.Children.Add(RoomRow(room));
                _linked.IsVisible = true;
            }
            Status(null);
        }
        catch (PortalException e) when (e.Status == 401)
        {
            await _account.CheckAsync();
            _unlinked.IsVisible = true;
            _lobby.IsVisible = false;
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
        var text = new StackPanel { Spacing = 2, VerticalAlignment = VerticalAlignment.Center };
        text.Children.Add(new TextBlock { Text = r.Title, FontSize = 15, FontFamily = Skin.Medium, TextWrapping = TextWrapping.Wrap });
        var line = r.Mine ? "" : L.T("voice.owner", r.Owner.Name) + " · ";
        line += r.InviteDeclined && r.State == "ok" ? L.T("voice.declined") : StateText(r.State == "ok" && r.Status != "open" ? "room_closed" : r.State);
        text.Children.Add(new TextBlock { Text = line, FontSize = 12, Foreground = Skin.B(r.CanJoin ? Skin.Muted : Skin.WarnText), TextWrapping = TextWrapping.Wrap });

        var buttons = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8, VerticalAlignment = VerticalAlignment.Center };
        var join = Skin.Btn(L.T("voice.join"), "primary");
        join.IsEnabled = r.CanJoin;
        join.Click += async (_, _) => await JoinAsync(r);
        buttons.Children.Add(join);
        if (!r.Mine && !r.InviteDeclined && r.State is "ok" or "not_friends")
        {
            var decline = Skin.Btn(L.T("voice.decline"), "ghost");
            decline.Click += async (_, _) => await DeclineAsync(r);
            buttons.Children.Add(decline);
        }
        var row = new DockPanel();
        DockPanel.SetDock(buttons, Dock.Right);
        row.Children.Add(buttons);
        row.Children.Add(text);
        return new Border { Background = Skin.B(Skin.Inactive), CornerRadius = new CornerRadius(2), Padding = new Thickness(12, 8), Child = row };
    }

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
            var room = await new PortalClient(Http, portal).CreateVoiceRoomAsync(_token, title, CancellationToken.None);
            await LoadAsync();
            Status(L.T("voice.created", room.Title), warn: false);
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
                    _canPublish = p.CanPublish;
                    _me = p.Identity;
                    return new VoicePass(p.Url, p.Token);
                }
                catch (VoicePassRefusedException e) { throw new VoiceDeniedException(e.Code); }
            },
            OutputGain = (float)Math.Clamp(_settings.VoiceVolume, 0, 2),
            InputId = _settings.VoiceInputId, InputName = _settings.VoiceInputName,
            OutputId = _settings.VoiceOutputId, OutputName = _settings.VoiceOutputName,
        };
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
        _roomTitle.Text = room.Title;
        _unlinked.IsVisible = false;
        _lobby.IsVisible = false;
        _roomPanel.IsVisible = true;
        Status(null);
        FollowKey();
        ShowMicToggle();
        ShowCheck();
        ShowDeviceNote();
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
        _roomPanel.IsVisible = false;
        RoomChanged?.Invoke();
        await Dispose(s);
        _room = null;
        ShowCheck();
        ShowDeviceNote();
        if (unlinked) await _account.CheckAsync();
        await LoadAsync();
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
        _connection.Text = down ? L.T("voice.conn.device", s.DeviceDownSeconds) : s.State switch
        {
            VoiceState.Connecting => L.T("voice.conn.connecting"),
            VoiceState.Connected => L.T("voice.conn.connected"),
            VoiceState.Reconnecting => L.T("voice.conn.reconnecting"),
            _ => L.T("voice.conn.disconnected"),
        };
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

    void ShowMicToggle()
    {
        _micToggle.IsVisible = _settings.VoiceOpenMic;
        _micToggle.Content = L.T(_session?.Muted == true ? "voice.micUnmute" : "voice.micMute");
    }

    // ------------------------------------------------------------------ the people in the room

    async Task ModerateAsync(string identity, string kind)
    {
        if (_room is not { } room || Portal() is not { } portal || Owner() is not { } owner || !Guid.TryParse(identity, out var user)) return;
        string name = NameOf(identity);
        var client = new PortalClient(Http, portal);
        try
        {
            switch (kind)
            {
                case "unmute":
                    await client.SetVoiceSpeakingAsync(_token, room.PublicId, user, true, null, CancellationToken.None);
                    break;
                case "complain":
                    var text = await new TextDialog(L.T("voice.complainPrompt", name), "", VoiceRules.ComplaintMax).ShowDialog<string?>(owner);
                    if (text is null) return;
                    var c = await client.ComplainInVoiceRoomAsync(_token, room.PublicId, user, text, CancellationToken.None);
                    Status(L.T("voice.complained", c.DisplayNumber), warn: false);
                    return;
                default:
                    var reason = await new TextDialog(L.T("voice." + kind + "Prompt", name), "", VoiceRules.ReasonMax, allowEmpty: true).ShowDialog<string?>(owner);
                    if (reason is null) return;
                    if (kind == "mute") await client.SetVoiceSpeakingAsync(_token, room.PublicId, user, false, reason, CancellationToken.None);
                    else if (kind == "kick") await client.KickFromVoiceRoomAsync(_token, room.PublicId, user, reason, CancellationToken.None);
                    else await client.BanFromVoiceRoomAsync(_token, room.PublicId, user, reason, CancellationToken.None);
                    break;
            }
            Status(null);
            await LiveAsync();
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
            bool owner = page._room?.Mine == true;
            _speak.IsVisible = _kick.IsVisible = _ban.IsVisible = owner;
            _complain.IsVisible = !owner;

            var top = new DockPanel();
            var who = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 10 };
            who.Children.Add(_name);
            who.Children.Add(_state);
            var vol = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8 };
            vol.Children.Add(_gain);
            vol.Children.Add(_off);
            DockPanel.SetDock(vol, Dock.Right);
            top.Children.Add(vol);
            top.Children.Add(who);
            var acts = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8 };
            acts.Children.Add(_speak);
            acts.Children.Add(_kick);
            acts.Children.Add(_ban);
            acts.Children.Add(_complain);
            var body = new StackPanel { Spacing = 6 };
            body.Children.Add(top);
            body.Children.Add(acts);
            Root = new Border { Background = Skin.B(Skin.Inactive), CornerRadius = new CornerRadius(2), Padding = new Thickness(12, 8), Child = body };
            ShowOff();
        }

        void ShowOff() => _off.Content = L.T(_gain.Value > 0 ? "voice.peerOff" : "voice.peerOn");

        public void Update(PeerView? p, VoiceLive? live)
        {
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
        FillBox(_input, list.Where(d => d.IsCapture), _settings.VoiceInputId, _settings.VoiceInputName);
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
