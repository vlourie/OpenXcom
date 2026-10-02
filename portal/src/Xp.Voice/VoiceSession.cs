using System.Collections.Concurrent;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Threading.Channels;
using LiveKit.Proto;

namespace Xp.Voice;

public sealed class VoiceOptions
{
    public required string Url { get; init; }
    public required string Token { get; init; }
    /// <summary>false: the microphone is not opened at all (listen only).</summary>
    public bool Microphone { get; init; } = true;
    /// <summary>0 plays nothing - automatic tests must not sound on the speakers of the machine.</summary>
    public float OutputGain { get; init; } = 1f;
    /// <summary>A reconnection longer than this is given up and the room is joined anew (R-142).</summary>
    public int HangMs { get; init; } = 20000;
    /// <summary>The SDK's send queue. It fills up when the sound card's clock runs ahead of the SDK's
    /// 10 ms pace, and a full queue is that much extra delay: 50 ms gave 120-130 ms one way on one
    /// machine and "failed to capture frame" every ~15 s, 0 gave 70-80 ms and no losses (29.09).</summary>
    public int SendQueueMs { get; init; }
    /// <summary>Safe diagnostics of the sound, for looking into a failure: <see cref="VoiceSession.Line"/>
    /// gets numbers and names only - device formats and channels, what WASAPI gave, the device's events,
    /// every <see cref="DiagnosticsEverySec"/> a stats line (microphone level, buffers, underruns, frames,
    /// time in the device callback, the network), and LiveKit's info lines. Never samples, never a file
    /// of sound. Off: rare lines about states only (joined, reconnecting, the device went away).</summary>
    public bool Diagnostics { get; init; }
    public int DiagnosticsEverySec { get; init; } = 5;
    /// <summary>Output / microphone chosen by a part of the name; null - the Windows default.</summary>
    public string? Output { get; init; }
    public string? Input { get; init; }
}

public enum VoiceState { Connecting, Connected, Reconnecting, Disconnected, Stopped }

/// <summary>LevelDb is what is played (-90 while the jitter ring primes), ReceivedDb what arrives from the
/// network; SilenceMs - how long the arriving frames have been digital silence (below -80 dBFS);
/// SinceFrameMs - since the last frame arrived, -1 before the first.</summary>
public sealed record PeerView(string Identity, double LevelDb, bool Speaking, bool Muted, long Frames, int BufferedMs, int Underruns,
    double ReceivedDb, int SilenceMs, int SinceFrameMs);

/// <summary>
/// One voice room: the microphone is published as a LiveKit audio track, every other participant is
/// mixed into the speakers. Three threads meet here: the sound card (mix out, microphone in), the pump
/// (echo canceller and sending, 10 ms frames) and the room loop (room events, reconnection), plus the
/// LiveKit threads that deliver incoming frames.
/// </summary>
public sealed class VoiceSession : IAsyncDisposable
{
    const int Frame = AudioDevice.Period;               // 10 ms at 48 kHz
    const int PrimeSamples = Frame * 3;                 // start playing a speaker at 30 ms buffered
    const int MaxBufferedSamples = Frame * 12;          // above 120 ms cut back ...
    const int TrimToSamples = Frame * 4;                // ... to 40 ms

    readonly VoiceOptions _opt;
    readonly Channel<object> _loop = Channel.CreateUnbounded<object>(new UnboundedChannelOptions { SingleReader = true });
    readonly ConcurrentDictionary<string, Peer> _peers = new();
    readonly ConcurrentDictionary<ulong, Peer> _streams = new();
    readonly ConcurrentDictionary<ulong, nint> _captures = new();
    readonly Lock _captureOrderLock = new();
    ulong _lastCaptured;
    int _outOfOrder;
    readonly ConcurrentQueue<string> _notes = new();
    readonly SampleRing _mic = new(AudioDevice.Rate);
    readonly SampleRing _played = new(AudioDevice.Rate);
    readonly AutoResetEvent _wake = new(false);
    volatile Peer[] _mix = [];
    volatile bool _stopping;
    volatile bool _muted;
    volatile bool _apmOn = true;
    bool _micOpen;
    Room? _room;
    string _token;
    ulong _apm;
    Thread? _pump;
    Task? _loopTask;
    long _breakAt;                                      // Stopwatch timestamp of the first sign of a break, 0 = none
    int _retry;
    // counters, read by the pump for the 5 s line
    long _sent, _sendDropped, _callbacks;
    double _maxGapMs, _maxBusyMs, _micDb = -90;
    long _oddCalls;
    long _lastCallback;
    // the sound device went away (the friend's log 02.10: "device stopped" at 00:48, then 74 min of a
    // launcher that sent nothing and played nothing while the window said "in the room"); the pump
    // reopens it every 2 s. Timestamp of the stop, 0 = running; set by the device thread or the watchdog
    long _deviceStoppedAt, _deviceRetryAt;
    int _deviceRetries;
    volatile bool _deviceDead;                          // a "stopped" note since the last open attempt
    volatile bool _closingDevice;                       // our own Close of a running device fires "stopped" too: not a loss
    long _startedAt, _micRetryAt;                       // a wanted microphone that is missing is looked for again
    int _micRetryMs = 10000;                            // ... and after a failed attempt not at once: 10 s, 20 s, ... 60 s

    public event Action<string>? Line;
    public VoiceState State { get; private set; } = VoiceState.Connecting;
    public string Identity { get; private set; } = "";
    public double MicDb => _micDb;
    /// <summary>The microphone was asked for and did not open: speakers only, nothing is published.</summary>
    public bool MicrophoneMissing => MicWanted && !_micOpen;
    bool MicWanted => _opt.Microphone;
    /// <summary>The sound device stopped and is being reopened: nothing is heard or sent meanwhile.</summary>
    public bool DeviceDown => Interlocked.Read(ref _deviceStoppedAt) != 0;
    public int DeviceDownSeconds
    {
        get { long t = Interlocked.Read(ref _deviceStoppedAt); return t == 0 ? 0 : (int)Stopwatch.GetElapsedTime(t).TotalSeconds; }
    }
    /// <summary>What the published track's mute must be: the user's choice, or a microphone that is
    /// not there (after a device change it may fail to come back while the track lives on).</summary>
    bool TrackMuted => _muted || MicrophoneMissing;

    public bool Muted
    {
        get => _muted;
        set
        {
            _muted = value;
            _loop.Writer.TryWrite(Command.Mute);
        }
    }

    /// <summary>Whether the echo canceller exists at all (off for listen-only).</summary>
    public bool HasEchoCanceller => _apm != 0;

    /// <summary>The echo canceller, noise suppressor and gain control, switched live: an A/B test in a real conversation.</summary>
    public bool EchoCanceller
    {
        get => _apmOn;
        set
        {
            if (_apmOn == value) return;
            _apmOn = value;
            _notes.Enqueue(value ? "echo canceller on" : "echo canceller off");
        }
    }

    public VoiceSession(VoiceOptions opt)
    {
        _opt = opt;
        _token = opt.Token;
    }

    /// <summary>Releases the LiveKit runtime: once, at process exit, after every session is disposed.</summary>
    public static void ShutdownRuntime() => Ffi.Shutdown();

    public IReadOnlyList<PeerView> Peers() =>
        _peers.Values.OrderBy(p => p.Identity, StringComparer.Ordinal).Select(p => p.View()).ToList();

    public void Start()
    {
        Diag(Pace.Hold());
        Ffi.Verbose = _opt.Diagnostics;
        Ffi.Log += Log;
        Ffi.Events += OnFfiEvent;
        Ffi.Init();
        bool apm = _opt.Microphone;
        if (apm)
        {
            var r = Ffi.Request(new FfiRequest
            {
                NewApm = new NewApmRequest { EchoCancellerEnabled = true, GainControllerEnabled = true, HighPassFilterEnabled = true, NoiseSuppressionEnabled = true },
            });
            _apm = r.NewApm.Apm.Handle.Id;
        }
        _startedAt = Stopwatch.GetTimestamp();
        _micRetryAt = _startedAt + 3 * Stopwatch.Frequency;  // a microphone missing at the start is looked for from 3 s on, not at once
        AudioDevice.SetOptions(_opt.Output, _opt.Input);
        Diag($"audio: period {AudioDevice.Period * 1000 / AudioDevice.Rate} ms, output {_opt.Output ?? "default"}, microphone {_opt.Input ?? "default"}");
        Diag("devices: " + AudioDevice.Devices());
        var dev = AudioDevice.Open(MicWanted, OnAudio, OnDeviceNote, out _micOpen);
        Log($"sound: {dev}; echo canceller {(apm ? "on" : "off")}, output gain {_opt.OutputGain:0.##}");
        LogDevice();
        _pump = new Thread(Pump) { IsBackground = true, Name = "voice pump", Priority = ThreadPriority.AboveNormal };
        _pump.Start();
        _loopTask = Task.Run(RoomLoop);
        _loop.Writer.TryWrite(Command.Join);
    }

    public async ValueTask DisposeAsync()
    {
        if (_stopping) return;
        _stopping = true;
        _loop.Writer.TryWrite(Command.Stop);
        if (_loopTask is not null) await _loopTask.WaitAsync(TimeSpan.FromSeconds(8)).ConfigureAwait(false);
        _wake.Set();
        _pump?.Join(2000);
        AudioDevice.Close();   // after the pump: it reopens the device itself
        if (_apm != 0) Ffi.Drop(_apm);
        Ffi.Events -= OnFfiEvent;
        Ffi.Log -= Log;
        Pace.Release();
        State = VoiceState.Stopped;
        Log("voice stopped");
    }

    // ---------------------------------------------------------------- sound card thread

    void OnAudio(ReadOnlySpan<short> input, Span<short> output)
    {
        long now = Stopwatch.GetTimestamp();
        if (_lastCallback != 0)
        {
            double gap = Stopwatch.GetElapsedTime(_lastCallback, now).TotalMilliseconds;
            if (gap > _maxGapMs) _maxGapMs = gap;
        }
        _lastCallback = now;
        _callbacks++;
        if (output.Length != AudioDevice.Period) _oddCalls++;
        try { Render(input, output); }
        finally
        {
            double busy = Stopwatch.GetElapsedTime(now).TotalMilliseconds;
            if (busy > _maxBusyMs) _maxBusyMs = busy;
        }
    }

    void Render(ReadOnlySpan<short> input, Span<short> output)
    {
        int n = output.Length;
        Span<int> acc = n <= 4096 ? stackalloc int[n] : new int[n];
        Span<short> tmp = n <= 4096 ? stackalloc short[n] : new short[n];
        acc.Clear();
        foreach (var p in _mix)
        {
            if (!p.Pull(tmp)) continue;
            for (int i = 0; i < n; i++) acc[i] += tmp[i];
        }
        float g = _opt.OutputGain;
        for (int i = 0; i < n; i++) output[i] = (short)Math.Clamp((int)(acc[i] * g), short.MinValue, short.MaxValue);
        _played.Write(output);

        if (input.Length == n) input.CopyTo(tmp);
        else tmp.Clear();
        _mic.Write(tmp);
        _wake.Set();
    }

    // ---------------------------------------------------------------- pump thread

    unsafe void Pump()
    {
        var frame = new short[Frame];
        long lastStats = Stopwatch.GetTimestamp();
        while (!_stopping)
        {
            _wake.WaitOne(50);
            if (Interlocked.Read(ref _deviceStoppedAt) == 0)
            {
                // watchdog for a device that died without a "stopped" note (miniaudio skips the note
                // when the backend's own stop fails, which an unplugged card can make it do)
                long lc = _lastCallback;
                if (lc != 0 && Stopwatch.GetElapsedTime(lc).TotalSeconds > 3) DeviceLost("no device callback for 3 s");
                else if (MicrophoneMissing && Stopwatch.GetTimestamp() >= _micRetryAt) RetryMicrophone();
            }
            else if (Stopwatch.GetTimestamp() >= _deviceRetryAt) ReopenDevice();
            while (_played.Count >= Frame)
            {
                _played.Read(frame);
                if (_apm != 0) Apm(frame, reverse: true);
            }
            while (_mic.Count >= Frame)
            {
                _mic.Read(frame);
                if (_apm != 0 && _apmOn) Apm(frame, reverse: false);
                _micDb = Db(frame);
                Send(frame);
            }
            while (_notes.TryDequeue(out var note)) Log(note);
            LogMiniaudio();
            if (Stopwatch.GetElapsedTime(lastStats).TotalSeconds >= Math.Max(1, _opt.DiagnosticsEverySec))
            {
                lastStats = Stopwatch.GetTimestamp();
                Stats();
            }
        }
    }

    /// <summary>Diagnostics: what WASAPI really gave each stream, after every open - one line per stream.</summary>
    void LogDevice()
    {
        LogMiniaudio();
        if (!_opt.Diagnostics) return;
        foreach (var line in AudioDevice.Detail().Split('\n', StringSplitOptions.RemoveEmptyEntries)) Log("device " + line);
    }

    /// <summary>miniaudio's own lines ("[WASAPI] Using IAudioClient3", the formats it chose) - any thread.
    /// Errors always (rare, and about the device), the rest with diagnostics only.</summary>
    void LogMiniaudio()
    {
        var text = AudioDevice.TakeLog();
        if (text.Length == 0) return;
        foreach (var line in text.Split('\n', StringSplitOptions.RemoveEmptyEntries))
        {
            if (line.StartsWith("debug: Loading ", StringComparison.Ordinal)) continue;   // 21 lines of DLLs and symbols, nothing about sound
            if (_opt.Diagnostics || line.StartsWith("error: ", StringComparison.Ordinal)) Log("miniaudio " + line);
        }
    }

    // ---------------------------------------------------------------- the sound device going away

    /// <summary>Device thread: miniaudio's notes. "stopped" is the device going away - Windows took the
    /// card, the driver reset, a USB headset unplugged; the callback has ended and nothing is heard or
    /// sent until the device is opened anew.</summary>
    void OnDeviceNote(string note)
    {
        Diag(note);
        if (note == "device stopped") DeviceLost(note);
    }

    void DeviceLost(string why)
    {
        if (_stopping || _closingDevice) return;
        _deviceDead = true;
        long now = Stopwatch.GetTimestamp();
        if (Interlocked.CompareExchange(ref _deviceStoppedAt, now, 0) == 0)
        {
            _deviceRetries = 0;
            _deviceRetryAt = now + Stopwatch.Frequency;       // first try in 1 s, then every 2 s
            _micDb = -90;
            Log($"sound device down ({why}): reopening it every 2 s; until then this machine hears nothing and sends nothing");
        }
        _wake.Set();
    }

    /// <summary>Pump thread, every 2 s while the device is down: close what is left of the old device
    /// (xpaudio keeps one device per process, so there is never a second one) and open anew. After a
    /// success the others' rings are cleared - what piled up while nothing was played is half a second
    /// of stale sound - and the room loop puts the track in step with the microphone that came back.</summary>
    void ReopenDevice()
    {
        _deviceRetries++;
        _deviceRetryAt = Stopwatch.GetTimestamp() + 2 * Stopwatch.Frequency;
        bool micBefore = _micOpen;
        _closingDevice = true;
        AudioDevice.Close();
        _closingDevice = false;
        _deviceDead = false;                                  // after Close: a last note of the old device is not a new stop
        string dev;
        try { dev = AudioDevice.Open(MicWanted, OnAudio, OnDeviceNote, out _micOpen); }
        catch (Exception e)
        {
            if (_deviceRetries == 1 || _deviceRetries % 15 == 0)
                Log($"sound device still down after {DeviceDownSeconds} s (try {_deviceRetries}): {e.Message}");
            return;
        }
        if (_deviceDead) return;                              // stopped again at once: next try in 2 s
        int down = DeviceDownSeconds;
        _lastCallback = Stopwatch.GetTimestamp();             // the watchdog counts from here, not from before the stop
        Interlocked.Exchange(ref _deviceStoppedAt, 0);
        foreach (var p in _mix) p.Reset();
        Log($"sound device back after {down} s (try {_deviceRetries}): {dev}; playback buffers cleared" +
            (micBefore == _micOpen ? "" : _micOpen ? "; the microphone is back" : "; the microphone did not come back: nothing is sent, looking for it"));
        LogDevice();
        _loop.Writer.TryWrite(Command.Device);
    }

    /// <summary>Pump thread, while a wanted microphone is missing (not there at the start, or not back
    /// with the device): every 3 s asks Windows whether it lists a capture device at all, and only then
    /// opens the device anew as duplex - a reopening is a short gap in what is played, so one that
    /// cannot find a microphone is not tried. An attempt that still leaves the microphone missing
    /// (listed but not openable: busy, denied in the privacy settings) backs off, 10 s up to 60 s.</summary>
    void RetryMicrophone()
    {
        long now = Stopwatch.GetTimestamp();
        _micRetryAt = now + 3 * Stopwatch.Frequency;
        int listed = AudioDevice.CaptureDevices();
        if (listed <= 0) { _micRetryMs = 10000; return; }
        int wait = _micRetryMs;
        _micRetryAt = now + wait * (Stopwatch.Frequency / 1000);
        _micRetryMs = Math.Min(60000, wait * 2);
        _closingDevice = true;
        AudioDevice.Close();                                  // a running device: its "stopped" note is ours, not a loss
        _closingDevice = false;
        _deviceDead = false;
        string dev;
        try { dev = AudioDevice.Open(MicWanted, OnAudio, OnDeviceNote, out _micOpen); }
        catch (Exception e) { DeviceLost("reopening for the microphone failed: " + e.Message); return; }
        _lastCallback = Stopwatch.GetTimestamp();
        foreach (var p in _mix) p.Reset();
        if (_micOpen)
        {
            _micRetryMs = 10000;
            Log($"the microphone is back: {dev}");
            _loop.Writer.TryWrite(Command.Device);
        }
        else Log($"microphone still missing ({listed} capture device(s) listed): {dev}; next try in {wait / 1000} s");
        LogDevice();
    }

    unsafe void Apm(short[] frame, bool reverse)
    {
        fixed (short* p = frame)
        {
            ulong ptr = (ulong)p;
            uint size = (uint)(frame.Length * 2);
            var req = reverse
                ? new FfiRequest { ApmProcessReverseStream = new ApmProcessReverseStreamRequest { ApmHandle = _apm, DataPtr = ptr, Size = size, SampleRate = AudioDevice.Rate, NumChannels = 1 } }
                : new FfiRequest { ApmProcessStream = new ApmProcessStreamRequest { ApmHandle = _apm, DataPtr = ptr, Size = size, SampleRate = AudioDevice.Rate, NumChannels = 1 } };
            var r = Ffi.Request(req);
            var err = reverse ? r.ApmProcessReverseStream.Error : r.ApmProcessStream.Error;
            if (!string.IsNullOrEmpty(err)) Diag("echo canceller: " + err);
        }
    }

    unsafe void Send(short[] frame)
    {
        var room = _room;
        if (room is null || room.Source == 0 || TrackMuted || State != VoiceState.Connected) return;
        // the SDK answers each frame with a callback; frames it has not taken yet stay ours
        if (_captures.Count > 20) { _sendDropped++; return; }
        nint buf = (nint)NativeMemory.Alloc((nuint)(Frame * 2));
        frame.AsSpan().CopyTo(new Span<short>((void*)buf, Frame));
        ulong id = Ffi.NextAsyncId();
        _captures[id] = buf;
        try
        {
            Ffi.Request(new FfiRequest
            {
                CaptureAudioFrame = new CaptureAudioFrameRequest
                {
                    SourceHandle = room.Source,
                    RequestAsyncId = id,
                    Buffer = new AudioFrameBufferInfo { DataPtr = (ulong)buf, NumChannels = 1, SampleRate = AudioDevice.Rate, SamplesPerChannel = Frame },
                },
            });
            _sent++;
        }
        catch (Exception e)
        {
            if (_captures.TryRemove(id, out var b)) NativeMemory.Free((void*)b);
            Diag("send failed: " + e.Message);
        }
    }

    /// <summary>Every DiagnosticsEverySec: the counters start over (the window's underruns are per
    /// period too), the line goes to the log with diagnostics only. Numbers, no sound.</summary>
    void Stats()
    {
        var peers = string.Join("; ", _mix.Select(p => p.StatsLine()));
        string line = $"stats: {State} sent {Interlocked.Exchange(ref _sent, 0)} frames/{Math.Max(1, _opt.DiagnosticsEverySec)}s, dropped {Interlocked.Exchange(ref _sendDropped, 0)}, " +
            $"out of order {Interlocked.Exchange(ref _outOfOrder, 0)}, " +
            $"mic {_micDb:0} dB{(_muted ? " (muted)" : "")}{(MicrophoneMissing ? " (not opened)" : "")}{(_apm != 0 && !_apmOn ? " (echo canceller off)" : "")}, device {Interlocked.Exchange(ref _callbacks, 0)} calls{(_oddCalls > 0 ? $" ({Interlocked.Exchange(ref _oddCalls, 0)} not {AudioDevice.Period * 1000 / AudioDevice.Rate} ms)" : "")}{(DeviceDown ? $" (stopped {DeviceDownSeconds} s ago, {_deviceRetries} tries)" : "")}, max gap {_maxGapMs:0} ms, max busy {_maxBusyMs:0.0} ms | {(peers.Length > 0 ? peers : "nobody")}";
        _maxGapMs = 0;
        _maxBusyMs = 0;
        Diag(line);
    }

    static double Db(ReadOnlySpan<short> s)
    {
        double sum = 0;
        foreach (var v in s) sum += (double)v * v;
        double rms = Math.Sqrt(sum / Math.Max(1, s.Length));
        return rms < 1 ? -90 : 20 * Math.Log10(rms / 32768);
    }

    // ---------------------------------------------------------------- LiveKit threads

    void OnFfiEvent(FfiEvent e)
    {
        switch (e.MessageCase)
        {
            case FfiEvent.MessageOneofCase.AudioStreamEvent:
                var ae = e.AudioStreamEvent;
                if (ae.MessageCase == AudioStreamEvent.MessageOneofCase.FrameReceived)
                {
                    var f = ae.FrameReceived.Frame;
                    try
                    {
                        if (_streams.TryGetValue(ae.StreamHandle, out var peer)) peer.Push(Ffi.Samples(f.Info));
                    }
                    finally { Ffi.Drop(f.Handle.Id); }
                }
                else if (ae.MessageCase == AudioStreamEvent.MessageOneofCase.Eos && _opt.Diagnostics && _streams.TryGetValue(ae.StreamHandle, out var gone))
                    _notes.Enqueue($"stream of {gone.Identity} ended");
                return;
            case FfiEvent.MessageOneofCase.CaptureAudioFrame:
                unsafe
                {
                    if (_captures.TryRemove(e.CaptureAudioFrame.AsyncId, out var buf)) NativeMemory.Free((void*)buf);
                }
                // the SDK takes each frame in its own task: an answer older than the last one means
                // two frames were handed to the encoder the other way round
                lock (_captureOrderLock)
                {
                    if (e.CaptureAudioFrame.AsyncId < _lastCaptured) _outOfOrder++;
                    else _lastCaptured = e.CaptureAudioFrame.AsyncId;
                }
                if (_opt.Diagnostics && e.CaptureAudioFrame.HasError && e.CaptureAudioFrame.Error.Length > 0) _notes.Enqueue("send: " + e.CaptureAudioFrame.Error);
                return;
            case FfiEvent.MessageOneofCase.RoomEvent:
                _loop.Writer.TryWrite(e.RoomEvent);
                return;
        }
    }

    // ---------------------------------------------------------------- room loop

    enum Command { Join, Mute, Hang, Net, Stop, Device }

    sealed class Room(ulong handle, ulong local)
    {
        public readonly ulong Handle = handle, Local = local;
        public ulong Source, Track;
        public readonly List<ulong> Owned = [];
        public readonly Dictionary<string, (ulong Track, ulong Stream)> Remote = [];
        /// <summary>track sid -> participant identity, for the net line</summary>
        public readonly Dictionary<string, string> Who = [];
    }

    async Task RoomLoop()
    {
        using var hang = new Timer(_ => { if (_breakAt != 0 && Stopwatch.GetElapsedTime(_breakAt).TotalMilliseconds > _opt.HangMs) _loop.Writer.TryWrite(Command.Hang); },
            null, 1000, 1000);
        int netMs = Math.Max(1, _opt.DiagnosticsEverySec) * 1000;
        using var net = new Timer(_ => _loop.Writer.TryWrite(Command.Net), null, netMs, netMs);
        await foreach (var item in _loop.Reader.ReadAllAsync().ConfigureAwait(false))
        {
            try
            {
                switch (item)
                {
                    case Command.Join:
                        if (_room is null && !_stopping) await Join().ConfigureAwait(false);
                        break;
                    case Command.Mute:
                        if (_room is { Track: not 0 } r)
                            Ffi.Request(new FfiRequest { LocalTrackMute = new LocalTrackMuteRequest { TrackHandle = r.Track, Mute = TrackMuted } });
                        Log(_muted ? "microphone muted" : "microphone on");
                        break;
                    case Command.Device:
                        // the sound device came back: publish only if the microphone exists only now (the track
                        // outlives the device - never a second publication), else put its mute in step with it
                        if (_room is { } dr && State == VoiceState.Connected)
                        {
                            if (dr.Track != 0) Ffi.Request(new FfiRequest { LocalTrackMute = new LocalTrackMuteRequest { TrackHandle = dr.Track, Mute = TrackMuted } });
                            else if (_opt.Microphone && _micOpen) await Publish(dr).ConfigureAwait(false);
                        }
                        break;
                    case Command.Hang:
                        // only a room stuck in the SDK's own reconnection; a lost room is retried by Retry
                        if (_breakAt == 0 || _room is null) break;
                        Log($"reconnection hangs longer than {_opt.HangMs / 1000} s - joining anew");
                        await Leave(DisconnectReason.ClientInitiated).ConfigureAwait(false);
                        await Join().ConfigureAwait(false);
                        break;
                    case Command.Net:
                        // not awaited: the answer comes as an event, the loop must not wait for it
                        if (_opt.Diagnostics && _room is { } nr && State == VoiceState.Connected) _ = NetStats(nr);
                        break;
                    case Command.Stop:
                        await Leave(DisconnectReason.ClientInitiated).ConfigureAwait(false);
                        return;
                    case RoomEvent re when _room is { } room && re.RoomHandle == room.Handle:
                        await OnRoomEvent(room, re).ConfigureAwait(false);
                        break;
                }
            }
            catch (Exception ex)
            {
                Log($"room loop: {ex.GetType().Name}: {ex.Message}");
            }
        }
    }

    async Task Join()
    {
        State = _breakAt != 0 ? VoiceState.Reconnecting : VoiceState.Connecting;
        long started = Stopwatch.GetTimestamp();
        ulong id = Ffi.NextAsyncId();
        FfiEvent e;
        try
        {
            e = await Ffi.RequestAsync(new FfiRequest
            {
                Connect = new ConnectRequest
                {
                    Url = _opt.Url,
                    Token = _token,
                    RequestAsyncId = id,
                    Options = new RoomOptions { AutoSubscribe = true, AdaptiveStream = false, Dynacast = false, JoinRetries = 1, ConnectTimeoutMs = 5000 },
                },
            }, id, TimeSpan.FromSeconds(20)).ConfigureAwait(false);
        }
        catch (TimeoutException)
        {
            Retry("connect: no answer in 20 s");
            return;
        }
        if (e.Connect.MessageCase != ConnectCallback.MessageOneofCase.Result)
        {
            Retry("connect: " + e.Connect.Error);
            return;
        }
        var res = e.Connect.Result;
        var room = new Room(res.Room.Handle.Id, res.LocalParticipant.Handle.Id);
        Identity = res.LocalParticipant.Info.Identity;
        foreach (var p in res.Participants)
        {
            room.Owned.Add(p.Participant.Handle.Id);
            foreach (var pub in p.Publications) room.Owned.Add(pub.Handle.Id);
            PeerOf(p.Participant.Info.Identity);
        }
        _room = room;
        Ffi.Request(new FfiRequest { ReadyForRoomEvent = new ReadyForRoomEventRequest { RoomHandle = room.Handle } });

        double joinMs = Stopwatch.GetElapsedTime(started).TotalMilliseconds;
        string others = res.Participants.Count == 0 ? "nobody else" : string.Join(", ", res.Participants.Select(p => p.Participant.Info.Identity));
        if (_breakAt != 0 && State == VoiceState.Reconnecting)
            Log($"joined anew as {Identity} in {joinMs:0} ms, {Stopwatch.GetElapsedTime(_breakAt).TotalMilliseconds:0} ms after the break; in the room: {others}");
        else
            Log($"joined {res.Room.Info.Name} as {Identity} in {joinMs:0} ms; in the room: {others}");
        _breakAt = 0;
        _retry = 0;
        State = VoiceState.Connected;

        // a microphone that did not open has nothing to publish: an empty track would send the others
        // exact zeros and look, from their side, like a working microphone
        if (_opt.Microphone && _micOpen) await Publish(room).ConfigureAwait(false);
        else if (_opt.Microphone) Log("microphone not opened: nothing published, the others cannot hear this machine");
    }

    void Retry(string why)
    {
        int delay = Math.Min(10000, 1000 << Math.Min(_retry++, 4));
        State = VoiceState.Disconnected;
        Log($"{why}; next try in {delay / 1000} s");
        _ = Task.Delay(delay).ContinueWith(_ => _loop.Writer.TryWrite(Command.Join), TaskScheduler.Default);
    }

    async Task Publish(Room room)
    {
        var src = Ffi.Request(new FfiRequest
        {
            NewAudioSource = new NewAudioSourceRequest { Type = AudioSourceType.AudioSourceNative, SampleRate = AudioDevice.Rate, NumChannels = 1, QueueSizeMs = (uint)_opt.SendQueueMs },
        });
        room.Source = src.NewAudioSource.Source.Handle.Id;
        var tr = Ffi.Request(new FfiRequest { CreateAudioTrack = new CreateAudioTrackRequest { Name = "microphone", SourceHandle = room.Source } });
        room.Track = tr.CreateAudioTrack.Track.Handle.Id;
        ulong id = Ffi.NextAsyncId();
        var e = await Ffi.RequestAsync(new FfiRequest
        {
            PublishTrack = new PublishTrackRequest
            {
                LocalParticipantHandle = room.Local,
                TrackHandle = room.Track,
                RequestAsyncId = id,
                Options = new TrackPublishOptions { Source = TrackSource.SourceMicrophone, Dtx = true, Red = true },
            },
        }, id, TimeSpan.FromSeconds(15)).ConfigureAwait(false);
        if (e.PublishTrack.MessageCase == PublishTrackCallback.MessageOneofCase.Publication)
        {
            room.Owned.Add(e.PublishTrack.Publication.Handle.Id);
            Log($"microphone published, send queue {_opt.SendQueueMs} ms" + (_muted ? " (muted)" : ""));
            if (_muted) Ffi.Request(new FfiRequest { LocalTrackMute = new LocalTrackMuteRequest { TrackHandle = room.Track, Mute = true } });
        }
        else Log("publish failed: " + e.PublishTrack.Error);
    }

    async Task Leave(DisconnectReason reason)
    {
        var room = _room;
        if (room is null) return;
        _room = null;
        ulong id = Ffi.NextAsyncId();
        try
        {
            await Ffi.RequestAsync(new FfiRequest { Disconnect = new DisconnectRequest { RoomHandle = room.Handle, RequestAsyncId = id, Reason = reason } },
                id, TimeSpan.FromSeconds(3)).ConfigureAwait(false);
        }
        catch (TimeoutException) { Log("leave: no answer in 3 s, dropping the room anyway"); }
        foreach (var (track, stream) in room.Remote.Values)
        {
            _streams.TryRemove(stream, out _);
            Ffi.Drop(stream);
            Ffi.Drop(track);
        }
        foreach (var h in room.Owned) Ffi.Drop(h);
        Ffi.Drop(room.Track);
        Ffi.Drop(room.Source);
        Ffi.Drop(room.Local);
        Ffi.Drop(room.Handle);
        _peers.Clear();
        _mix = [];
    }

    async Task OnRoomEvent(Room room, RoomEvent re)
    {
        switch (re.MessageCase)
        {
            case RoomEvent.MessageOneofCase.ParticipantConnected:
                room.Owned.Add(re.ParticipantConnected.Info.Handle.Id);
                PeerOf(re.ParticipantConnected.Info.Info.Identity);
                Log($"{re.ParticipantConnected.Info.Info.Identity} joined");
                break;
            case RoomEvent.MessageOneofCase.ParticipantDisconnected:
                var who = re.ParticipantDisconnected.ParticipantIdentity;
                _peers.TryRemove(who, out _);
                _mix = [.. _peers.Values];
                Log($"{who} left ({re.ParticipantDisconnected.DisconnectReason})");
                break;
            case RoomEvent.MessageOneofCase.TrackPublished:
                room.Owned.Add(re.TrackPublished.Publication.Handle.Id);
                break;
            case RoomEvent.MessageOneofCase.TrackSubscribed:
                var ts = re.TrackSubscribed;
                if (ts.Track.Info.Kind != TrackKind.KindAudio) { room.Owned.Add(ts.Track.Handle.Id); break; }
                var s = Ffi.Request(new FfiRequest
                {
                    NewAudioStream = new NewAudioStreamRequest
                    {
                        TrackHandle = ts.Track.Handle.Id, Type = AudioStreamType.AudioStreamNative,
                        SampleRate = AudioDevice.Rate, NumChannels = 1, FrameSizeMs = 10,
                    },
                });
                ulong stream = s.NewAudioStream.Stream.Handle.Id;
                var peer = PeerOf(ts.ParticipantIdentity);
                peer.Reset();
                room.Remote[ts.Track.Info.Sid] = (ts.Track.Handle.Id, stream);
                room.Who[ts.Track.Info.Sid] = ts.ParticipantIdentity;
                _streams[stream] = peer;
                Log($"hearing {ts.ParticipantIdentity}");
                break;
            case RoomEvent.MessageOneofCase.TrackUnsubscribed:
                if (room.Remote.Remove(re.TrackUnsubscribed.TrackSid, out var rt))
                {
                    _streams.TryRemove(rt.Stream, out _);
                    Ffi.Drop(rt.Stream);
                    Ffi.Drop(rt.Track);
                    Log($"no longer hearing {re.TrackUnsubscribed.ParticipantIdentity}");
                }
                break;
            case RoomEvent.MessageOneofCase.TrackMuted:
                if (_peers.TryGetValue(re.TrackMuted.ParticipantIdentity, out var pm)) pm.Muted = true;
                break;
            case RoomEvent.MessageOneofCase.TrackUnmuted:
                if (_peers.TryGetValue(re.TrackUnmuted.ParticipantIdentity, out var pu)) pu.Muted = false;
                break;
            case RoomEvent.MessageOneofCase.LocalTrackRepublished:
                room.Owned.Add(re.LocalTrackRepublished.PublicationHandle);
                Log("microphone published again after the reconnection");
                break;
            case RoomEvent.MessageOneofCase.ConnectionStateChanged:
                if (re.ConnectionStateChanged.State == ConnectionState.ConnReconnecting) BreakStarts("connection state: reconnecting");
                break;
            case RoomEvent.MessageOneofCase.Reconnecting:
                BreakStarts("reconnecting");
                break;
            case RoomEvent.MessageOneofCase.Reconnected:
                if (_breakAt != 0) Log($"reconnected in {Stopwatch.GetElapsedTime(_breakAt).TotalMilliseconds:0} ms from the break");
                _breakAt = 0;
                State = VoiceState.Connected;
                break;
            case RoomEvent.MessageOneofCase.TokenRefreshed:
                _token = re.TokenRefreshed.Token;
                break;
            case RoomEvent.MessageOneofCase.Disconnected:
                Log($"disconnected by the server: {re.Disconnected.Reason}");
                _breakAt = _breakAt == 0 ? Stopwatch.GetTimestamp() : _breakAt;
                await Leave(DisconnectReason.ClientInitiated).ConfigureAwait(false);
                if (re.Disconnected.Reason is DisconnectReason.DuplicateIdentity or DisconnectReason.ParticipantRemoved or DisconnectReason.RoomDeleted)
                {
                    // someone decided it: coming back on our own would undo a kick or fight a second copy
                    _breakAt = 0;
                    State = VoiceState.Disconnected;
                    Log("not rejoining: the room or the server sent us away");
                }
                else Retry("rejoining");
                break;
            case RoomEvent.MessageOneofCase.Eos:
                Log("room event stream ended");
                break;
        }
    }

    // ---------------------------------------------------------------- network stats

    // previous cumulative counters per RTC stats id, for the deltas of one stats period
    readonly ConcurrentDictionary<string, RtcStats> _netPrev = new();
    int _netBusy;

    /// <summary>
    /// Diagnostics: what WebRTC itself knows about the network, every stats period. Our own counters cannot see a lost packet:
    /// the decoder conceals it and still hands over a full 10 ms frame, so "robot" voice is only visible
    /// here - concealed samples and jitter buffer stretching on the receiving side, loss reported by
    /// the server on the sending side, and which path (udp/tcp, host/srflx/relay) the media takes.
    /// </summary>
    async Task NetStats(Room room)
    {
        if (Interlocked.Exchange(ref _netBusy, 1) == 1) return;
        // taken on the room loop, before the first await: Remote is only touched there
        var remote = room.Remote.Select(r => (Who: room.Who.TryGetValue(r.Key, out var w) ? w : r.Key, r.Value.Track)).ToList();
        try
        {
            ulong id = Ffi.NextAsyncId();
            var e = await Ffi.RequestAsync(new FfiRequest { GetSessionStats = new GetSessionStatsRequest { RoomHandle = room.Handle, RequestAsyncId = id } },
                id, TimeSpan.FromSeconds(3)).ConfigureAwait(false);
            var cb = e.GetSessionStats;
            if (cb.MessageCase != GetSessionStatsCallback.MessageOneofCase.Result) { Log("net: " + cb.Error); return; }
            Log($"net up: {NetSide(cb.Result.PublisherStats, up: true)}");
            // the session's subscriber list is empty when the server carries both ways on one
            // connection, so receiving is asked per remote track
            foreach (var (who, track) in remote)
            {
                ulong tid = Ffi.NextAsyncId();
                var te = await Ffi.RequestAsync(new FfiRequest { GetStats = new GetStatsRequest { TrackHandle = track, RequestAsyncId = tid } },
                    tid, TimeSpan.FromSeconds(3)).ConfigureAwait(false);
                if (te.GetStats.HasError) Log($"net down {who}: {te.GetStats.Error}");
                else Log($"net down {who}: {NetSide(te.GetStats.Stats, up: false)}");
            }
        }
        catch (TimeoutException) { Log("net: no stats in 3 s"); }
        catch (Exception ex) { Log($"net: {ex.GetType().Name}: {ex.Message}"); }
        finally { Volatile.Write(ref _netBusy, 0); }
    }

    string NetSide(IEnumerable<RtcStats> stats, bool up)
    {
        var all = stats.ToList();
        var cand = new Dictionary<string, IceCandidateStats>();
        foreach (var s in all)
        {
            if (s.StatsCase == RtcStats.StatsOneofCase.LocalCandidate) cand[s.LocalCandidate.Rtc.Id] = s.LocalCandidate.Candidate;
            else if (s.StatsCase == RtcStats.StatsOneofCase.RemoteCandidate) cand[s.RemoteCandidate.Rtc.Id] = s.RemoteCandidate.Candidate;
        }
        var parts = new List<string>();
        var pair = all.Where(s => s.StatsCase == RtcStats.StatsOneofCase.CandidatePair).Select(s => s.CandidatePair.CandidatePair_)
            .FirstOrDefault(p => p.Nominated && p.State == IceCandidatePairState.PairSucceeded);
        if (pair is null) parts.Add("no path yet");
        else
        {
            cand.TryGetValue(pair.LocalCandidateId, out var l);
            cand.TryGetValue(pair.RemoteCandidateId, out var r);
            parts.Add($"{l?.Protocol ?? "?"} {(l is { HasCandidateType: true } ? l.CandidateType.ToString().ToLowerInvariant() : "?")} -> {r?.Address}:{r?.Port}, rtt {pair.CurrentRoundTripTime * 1000:0} ms");
        }
        foreach (var s in all)
        {
            switch (s.StatsCase)
            {
                case RtcStats.StatsOneofCase.OutboundRtp when up && s.OutboundRtp.Stream.Kind == "audio":
                {
                    var o = s.OutboundRtp;
                    var p = Prev(o.Rtc.Id, s)?.OutboundRtp;
                    parts.Add($"sent {o.Sent.PacketsSent - (p?.Sent.PacketsSent ?? 0)} pkts, {(o.Sent.BytesSent - (p?.Sent.BytesSent ?? 0)) * 8 / (Math.Max(1, _opt.DiagnosticsEverySec) * 1000.0):0.0} kbit/s, " +
                        $"resent {o.Outbound.RetransmittedPacketsSent - (p?.Outbound.RetransmittedPacketsSent ?? 0)}, target {o.Outbound.TargetBitrate / 1000:0} kbit/s");
                    break;
                }
                case RtcStats.StatsOneofCase.RemoteInboundRtp when up && s.RemoteInboundRtp.Stream.Kind == "audio":
                {
                    var ri = s.RemoteInboundRtp;
                    var p = Prev(ri.Rtc.Id, s)?.RemoteInboundRtp;
                    parts.Add($"server got: lost {ri.Received.PacketsLost - (p?.Received.PacketsLost ?? 0)} ({ri.RemoteInbound.FractionLost * 100:0.#}%), jitter {ri.Received.Jitter * 1000:0} ms, rtt {ri.RemoteInbound.RoundTripTime * 1000:0} ms");
                    break;
                }
                case RtcStats.StatsOneofCase.InboundRtp when !up && s.InboundRtp.Stream.Kind == "audio":
                {
                    var i = s.InboundRtp;
                    var p = Prev(i.Rtc.Id, s)?.InboundRtp;
                    ulong samples = i.Inbound.TotalSamplesReceived - (p?.Inbound.TotalSamplesReceived ?? 0);
                    ulong concealed = i.Inbound.ConcealedSamples - (p?.Inbound.ConcealedSamples ?? 0);
                    ulong silent = i.Inbound.SilentConcealedSamples - (p?.Inbound.SilentConcealedSamples ?? 0);
                    ulong emitted = i.Inbound.JitterBufferEmittedCount - (p?.Inbound.JitterBufferEmittedCount ?? 0);
                    double jbDelay = i.Inbound.JitterBufferDelay - (p?.Inbound.JitterBufferDelay ?? 0);
                    // silent concealment is DTX (the speaker is quiet), not loss
                    double lossy = samples == 0 ? 0 : 100.0 * (concealed - Math.Min(silent, concealed)) / samples;
                    parts.Add($"got {i.Received.PacketsReceived - (p?.Received.PacketsReceived ?? 0)} pkts, lost {i.Received.PacketsLost - (p?.Received.PacketsLost ?? 0)}, " +
                        $"jitter {i.Received.Jitter * 1000:0} ms, concealed {lossy:0.#}% ({i.Inbound.ConcealmentEvents - (p?.Inbound.ConcealmentEvents ?? 0)} events), " +
                        $"stretched +{(i.Inbound.InsertedSamplesForDeceleration - (p?.Inbound.InsertedSamplesForDeceleration ?? 0)) * 1000 / AudioDevice.Rate} " +
                        $"-{(i.Inbound.RemovedSamplesForAcceleration - (p?.Inbound.RemovedSamplesForAcceleration ?? 0)) * 1000 / AudioDevice.Rate} ms, " +
                        $"jitter buffer {(emitted == 0 ? 0 : jbDelay / emitted * 1000):0} ms, nack {i.Inbound.NackCount - (p?.Inbound.NackCount ?? 0)}");
                    break;
                }
            }
        }
        return string.Join("; ", parts);
    }

    RtcStats? Prev(string id, RtcStats now)
    {
        _netPrev.TryGetValue(id, out var prev);
        _netPrev[id] = now;
        return prev;
    }

    void BreakStarts(string why)
    {
        if (_breakAt != 0) return;
        _breakAt = Stopwatch.GetTimestamp();
        State = VoiceState.Reconnecting;
        Log($"connection broke ({why})");
    }

    Peer PeerOf(string identity)
    {
        var p = _peers.GetOrAdd(identity, id => new Peer(id, _opt.Diagnostics ? _notes : null));
        _mix = [.. _peers.Values];
        return p;
    }

    void Log(string s)
    {
        try { Line?.Invoke(s); } catch { }
    }

    /// <summary>A line of the safe diagnostics: numbers and names, only when it is switched on.</summary>
    void Diag(string s)
    {
        if (_opt.Diagnostics) Log(s);
    }

    /// <summary>One remote speaker: its jitter ring and what the log and the window show about it.
    /// notes: null without diagnostics.</summary>
    sealed class Peer(string identity, ConcurrentQueue<string>? notes)
    {
        public readonly string Identity = identity;
        readonly SampleRing _ring = new(AudioDevice.Rate / 2);
        volatile bool _primed;
        public volatile bool Muted;
        long _frames, _framesTotal;
        int _underruns, _trimmed, _pushDropped;
        double _db = -90;
        // what arrives from the network, before the jitter ring: the level (300 ms peak hold for the
        // window, 5 s peak for the log) and runs of digital silence - the other side's gate or an empty
        // track, which a level alone shows as "quiet". Silence is below -80 dBFS, not exact zeros only:
        // after ~1 s of zeros the sender's DTX stops the packets and the decoder fills in comfort noise
        // of +-1 LSB (local test 02.10: a 6 s gap of zeros arrived as 150 ms of zeros and 5.8 s of noise)
        double _rxHoldDb = -90, _rxPeakDb = -90;
        long _rxHoldAt, _rxAt;                        // Stopwatch timestamps; _rxAt 0 = no frame yet
        int _voiced;                                  // frames above -45 dB since the last stats line
        long _silentRun, _silentMs, _silentLongest;   // samples of the run in progress; ms since the last stats line
        int _silentRuns;
        const double SilentDb = -80;

        public void Reset()
        {
            _ring.Clear();
            _primed = false;
        }

        public void Push(ReadOnlySpan<short> samples)
        {
            _pushDropped += _ring.Write(samples);
            Interlocked.Increment(ref _frames);
            Interlocked.Increment(ref _framesTotal);
            long now = Stopwatch.GetTimestamp();
            _rxAt = now;
            double db = Db(samples);
            if (db > _rxPeakDb) _rxPeakDb = db;
            if (db >= _rxHoldDb || Stopwatch.GetElapsedTime(_rxHoldAt, now).TotalMilliseconds > 300) { _rxHoldDb = db; _rxHoldAt = now; }
            if (db > -45) _voiced++;
            if (db <= SilentDb) _silentRun += samples.Length;
            else if (_silentRun > 0) SilentRunEnds();
        }

        void SilentRunEnds()
        {
            long ms = _silentRun * 1000 / AudioDevice.Rate;
            _silentRun = 0;
            _silentMs += ms;
            if (ms < 100) return;
            _silentRuns++;
            if (ms > _silentLongest) _silentLongest = ms;
            if (ms >= 2000) notes?.Enqueue($"{Identity}: {ms / 1000.0:0.0} s of digital silence received (below {SilentDb} dBFS)");
        }

        /// <returns>false when there was nothing to play</returns>
        public bool Pull(Span<short> dst)
        {
            if (!_primed)
            {
                if (_ring.Count < PrimeSamples) { dst.Clear(); _db = -90; return false; }
                _primed = true;
            }
            int got = _ring.Read(dst);
            if (got < dst.Length) { _underruns++; _primed = false; }
            if (_ring.Count > MaxBufferedSamples) _trimmed += _ring.TrimTo(TrimToSamples);
            _db = Db(dst);
            return got > 0;
        }

        public PeerView View() => new(Identity, _db, _db > -45, Muted, Interlocked.Read(ref _framesTotal), _ring.Count * 1000 / AudioDevice.Rate, _underruns,
            _rxHoldDb, (int)(_silentRun * 1000 / AudioDevice.Rate), _rxAt == 0 ? -1 : (int)Stopwatch.GetElapsedTime(_rxAt).TotalMilliseconds);

        public string StatsLine()
        {
            long f = Interlocked.Exchange(ref _frames, 0);
            string s = $"{Identity}: got {f} frames" +
                (f == 0 ? "" : $", peak {_rxPeakDb:0} dB, voiced {_voiced * 100 / f}%, silent {_silentMs} ms{(_silentRuns > 0 ? $" ({_silentRuns} runs >= 100 ms, longest {_silentLongest} ms)" : "")}") +
                (_silentRun >= AudioDevice.Rate ? $", silence now {_silentRun / AudioDevice.Rate} s" : "") +
                $", buffered {_ring.Count * 1000 / AudioDevice.Rate} ms, underruns {_underruns}, cut {_trimmed * 1000 / AudioDevice.Rate} ms";
            if (_pushDropped > 0) s += $", overflow {_pushDropped * 1000 / AudioDevice.Rate} ms";
            _underruns = 0;
            _trimmed = 0;
            _pushDropped = 0;
            _rxPeakDb = -90;
            _voiced = 0;
            _silentMs = 0;
            _silentRuns = 0;
            _silentLongest = 0;
            return s;
        }
    }
}
