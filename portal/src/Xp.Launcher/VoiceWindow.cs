using System.Text;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Threading;
using Xp.Voice;

namespace Xp.Launcher;

/// <summary>
/// The voice prototype (docs/portal/VOICE_CHAT.md, part B): one test room, no site, no friends yet.
///   XPiratezLauncher.exe --voice wss://host token|@token-file [--silent] [--listen] [--diagnostics]
///                        [--minimized] [--log file] [--quit-after seconds] [--queue-ms n]
///                        [--output id|name-part] [--input id|name-part]
/// --silent plays nothing, --listen opens no microphone, --diagnostics writes the safe diagnostics of
/// the sound to the log (numbers and names, no sound), --output and --input pick the output /
/// microphone by its id or a part of the name instead of the Windows default.
/// Several copies may run at once - two of them on one machine are the local test.
/// </summary>
public sealed class VoiceWindow : Window
{
    readonly VoiceSession _session;
    readonly VoiceOptions _opt;
    readonly StreamWriter? _file;
    readonly TextBlock _state = new() { FontSize = 16, FontWeight = FontWeight.SemiBold };
    readonly TextBlock _micLabel = new() { VerticalAlignment = VerticalAlignment.Center, FontSize = 13 };
    readonly ProgressBar _mic = new() { Minimum = -60, Maximum = 0, Height = 8, MinWidth = 200 };
    readonly StackPanel _peers = new() { Spacing = 6 };
    readonly TextBox _log = new() { IsReadOnly = true, AcceptsReturn = true, TextWrapping = TextWrapping.NoWrap, FontFamily = new FontFamily("Consolas"), FontSize = 12 };
    readonly Button _mute = Skin.Btn("Выключить микрофон");
    readonly Button _apm = Skin.Btn("Выключить эхоподавитель");
    readonly Queue<string> _lines = new();
    readonly Lock _linesLock = new();
    bool _linesDirty;
    bool _closing;
    bool _micMissingShown;

    public VoiceWindow(VoiceOptions opt, string url, string? logPath, bool minimized, int quitAfter)
    {
        Title = "X-Piratez - голос (проба)";
        Width = 760; Height = 560; MinWidth = 520; MinHeight = 380;
        WindowStartupLocation = WindowStartupLocation.CenterScreen;
        if (minimized) WindowState = WindowState.Minimized;

        if (logPath is not null)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(logPath))!);
            _file = new StreamWriter(logPath, append: false, new UTF8Encoding(true)) { AutoFlush = true };
        }
        _opt = opt;
        _session = new VoiceSession(opt);
        _session.Line += Add;

        _mute.Click += (_, _) =>
        {
            _session.Muted = !_session.Muted;
            _mute.Content = _session.Muted ? "Включить микрофон" : "Выключить микрофон";
        };
        _mute.IsEnabled = opt.Microphone;
        // A/B in a real conversation: is the "robot" voice the echo canceller or the network?
        _apm.Click += (_, _) =>
        {
            _session.EchoCanceller = !_session.EchoCanceller;
            _apm.Content = _session.EchoCanceller ? "Выключить эхоподавитель" : "Включить эхоподавитель";
        };
        _apm.IsVisible = false;

        var top = new StackPanel { Spacing = 10 };
        top.Children.Add(_state);
        var micRow = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 12 };
        _micLabel.Text = "микрофон";
        micRow.Children.Add(_micLabel);
        micRow.Children.Add(_mic);
        micRow.Children.Add(_mute);
        micRow.Children.Add(_apm);
        top.Children.Add(micRow);
        top.Children.Add(Skin.H2("в комнате"));
        top.Children.Add(_peers);

        var grid = new Grid { RowDefinitions = new RowDefinitions("Auto,*"), Margin = new Thickness(16) };
        grid.Children.Add(top);
        var logBox = new Border { Child = _log, Margin = new Thickness(0, 14, 0, 0) };
        Grid.SetRow(logBox, 1);
        grid.Children.Add(logBox);
        Content = grid;

        var timer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(200) };
        timer.Tick += (_, _) => Refresh();
        timer.Start();
        Opened += (_, _) =>
        {
            Add($"launcher {typeof(VoiceWindow).Assembly.GetName().Version}, pid {Environment.ProcessId}, {url}");
            try { _session.Start(); }
            catch (Exception e) { Add("voice did not start: " + e.Message); }
            _apm.IsVisible = _session.HasEchoCanceller;
            if (quitAfter > 0) DispatcherTimer.RunOnce(Close, TimeSpan.FromSeconds(quitAfter));
        };
        Closing += async (_, e) =>
        {
            if (_closing) return;
            e.Cancel = true;
            _closing = true;
            await _session.DisposeAsync();
            Add("window closed");
            _file?.Dispose();
            Close();
        };
    }

    void Add(string line)
    {
        var s = $"{DateTime.Now:HH:mm:ss.fff} {line}";
        lock (_linesLock)
        {
            try { _file?.WriteLine(s); } catch (ObjectDisposedException) { }
            _lines.Enqueue(s);
            while (_lines.Count > 400) _lines.Dequeue();
            _linesDirty = true;
        }
    }

    void Refresh()
    {
        bool deviceDown = _session.DeviceDown;
        _state.Text = deviceDown ? $"звук остановился, переоткрываю устройство ({_session.DeviceDownSeconds} с)…" : _session.State switch
        {
            VoiceState.Connecting => "подключаюсь…",
            VoiceState.Connected => "в комнате" + (_session.Identity.Length > 0 ? " как " + _session.Identity : ""),
            VoiceState.Reconnecting => "связь прервалась, восстанавливаю…",
            VoiceState.Disconnected => "нет связи, пробую снова",
            _ => _session.DeniedReason is { } why ? $"вход закрыт ({why})" : "выключено",
        };
        _state.Foreground = Skin.B(_session.State == VoiceState.Connected && !deviceDown ? Skin.Accent : Skin.WarnText);
        _mic.Value = Math.Max(-60, _session.MicDb);
        // live, not once at the start: the microphone can go with a device change and come back
        bool micMissing = _session.MicrophoneMissing;
        if (micMissing != _micMissingShown)
        {
            _micMissingShown = micMissing;
            _micLabel.Text = micMissing ? "микрофон не открылся: вас никто не слышит, ищу его" : "микрофон";
            if (micMissing) _micLabel.Foreground = Skin.B(Skin.WarnText);
            else _micLabel.ClearValue(ForegroundProperty);
            _mute.IsEnabled = !micMissing && _opt.Microphone;
        }

        _peers.Children.Clear();
        var peers = _session.Peers();
        if (peers.Count == 0) _peers.Children.Add(Skin.Note("никого, кроме вас"));
        foreach (var p in peers)
        {
            var row = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 12 };
            row.Children.Add(new TextBlock
            {
                Text = (p.Speaking ? "● " : "○ ") + p.Identity + (p.Muted ? " (микрофон выключен)" : ""),
                Foreground = Skin.B(p.Speaking ? Skin.Accent : Skin.Text2), FontSize = 14, MinWidth = 260,
            });
            // the bar is what arrives from the network, not what is played: a silent bar with frames
            // coming in means the other side sends silence, no frames means the path is down
            row.Children.Add(new ProgressBar { Minimum = -60, Maximum = 0, Value = Math.Max(-60, p.ReceivedDb), Height = 6, Width = 140, VerticalAlignment = VerticalAlignment.Center });
            string arriving = p.SinceFrameMs < 0 ? "звука ещё не было"
                : p.SinceFrameMs > 1000 ? $"нет пакетов {p.SinceFrameMs / 1000} с"
                : p.SilenceMs >= 1000 ? $"цифровая тишина {p.SilenceMs / 1000} с"
                : $"принято {p.ReceivedDb:0} дБ";
            bool warn = p.SinceFrameMs > 1000 || p.SilenceMs >= 1000;
            row.Children.Add(new TextBlock { Text = $"{arriving}, буфер {p.BufferedMs} мс", FontSize = 12, Foreground = Skin.B(warn ? Skin.WarnText : Skin.Muted), VerticalAlignment = VerticalAlignment.Center });
            _peers.Children.Add(row);
        }

        lock (_linesLock)
        {
            if (!_linesDirty) return;
            _linesDirty = false;
            _log.Text = string.Join('\n', _lines);
        }
        _log.CaretIndex = _log.Text?.Length ?? 0;
    }

    /// <summary>--voice mode: parse, run the window, release the LiveKit runtime at the end.</summary>
    public static int Run(string[] args, Func<AppBuilder> build)
    {
        if (args.Length < 3) return 2;
        string url = args[1], tokenArg = args[2];
        if (tokenArg.StartsWith('@') && !File.Exists(tokenArg[1..])) return 2;
        string? log = null, output = null, input = null;
        int quit = 0, queue = 0;
        for (int i = 3; i < args.Length; i++)
        {
            if (args[i] == "--log" && i + 1 < args.Length) log = args[++i];
            else if (args[i] == "--quit-after" && i + 1 < args.Length) quit = int.Parse(args[++i], System.Globalization.CultureInfo.InvariantCulture);
            else if (args[i] == "--queue-ms" && i + 1 < args.Length) queue = int.Parse(args[++i], System.Globalization.CultureInfo.InvariantCulture);
            else if (args[i] == "--output" && i + 1 < args.Length) output = args[++i];
            else if (args[i] == "--input" && i + 1 < args.Length) input = args[++i];
        }
        log ??= Path.Combine(Settings.Dir, "voice.log");
        // --output / --input take an id (the diagnostics list them in braces) or a part of the name
        IReadOnlyList<AudioDeviceInfo> devices = output is null && input is null ? [] : AudioDevice.List();
        var outDev = devices.FirstOrDefault(d => !d.IsCapture && d.Id == output);
        var inDev = devices.FirstOrDefault(d => d.IsCapture && d.Id == input);
        var opt = new VoiceOptions
        {
            // the prototype's pass: the token from the command line; @file is read again on every
            // entry, so a fresh token written there is picked up after a break
            Pass = _ => Task.FromResult(new VoicePass(url,
                tokenArg.StartsWith('@') ? File.ReadAllText(tokenArg[1..]).Trim() : tokenArg)),
            Microphone = !args.Contains("--listen"),
            OutputGain = args.Contains("--silent") ? 0f : 1f,
            SendQueueMs = queue,
            Diagnostics = args.Contains("--diagnostics"),
            OutputId = outDev?.Id,
            OutputName = outDev?.Name ?? (string.IsNullOrWhiteSpace(output) ? null : output),
            InputId = inDev?.Id,
            InputName = inDev?.Name ?? (string.IsNullOrWhiteSpace(input) ? null : input),
        };
        App.Voice = () => new VoiceWindow(opt, url, log, args.Contains("--minimized"), quit);
        try { return build().StartWithClassicDesktopLifetime([]); }
        finally { VoiceSession.ShutdownRuntime(); }
    }
}
