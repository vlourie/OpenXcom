using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;

namespace Xp.Voice;

/// <summary>An output or a microphone Windows lists. Id is opaque (the WASAPI endpoint id): keep it to
/// open the same device next time; keep Name too - it finds the device if the id has changed.</summary>
public sealed record AudioDeviceInfo(string Id, string Name, bool IsDefault, bool IsCapture);

/// <summary>
/// The sound card through xpaudio.dll (miniaudio, WASAPI shared mode): one duplex device, 48 kHz mono,
/// 10 ms periods. The callback runs on the device's own thread, which Windows drives by the card's
/// clock - it keeps its pace with the window minimized and a game in front, unlike a timer.
/// One device per process.
/// </summary>
public static unsafe partial class AudioDevice
{
    public const int Rate = 48000;
    public const int Period = Rate / 100;

    /// <summary>input is empty when there is no microphone; output must be filled completely.</summary>
    public delegate void DataHandler(ReadOnlySpan<short> input, Span<short> output);

    const string Lib = "xpaudio";

    [LibraryImport(Lib, StringMarshalling = StringMarshalling.Utf8)]
    private static partial int xpa_open(uint rate, uint period, delegate* unmanaged[Cdecl]<nint, short*, short*, uint, void> data,
        delegate* unmanaged[Cdecl]<nint, int, void> note, nint user, int capture, string outId, string inId);

    [LibraryImport(Lib)]
    private static partial void xpa_close();

    [LibraryImport(Lib)]
    private static partial int xpa_capture_count();

    /// <summary>One lock for every call that asks Windows for its devices or opens and closes ours: the
    /// window lists devices on its thread while the pump may be reopening, and miniaudio's device list is
    /// one array per context.</summary>
    static readonly Lock Native = new();

    /// <summary>How many capture devices Windows lists now (-1: not open or unknown) - whether a
    /// missing microphone is worth a reopening.</summary>
    public static int CaptureDevices()
    {
        lock (Native) return xpa_capture_count();
    }

    [LibraryImport(Lib)]
    private static partial nint xpa_error();

    [LibraryImport(Lib)]
    private static partial nint xpa_describe();

    [LibraryImport(Lib)]
    private static partial int xpa_list_devices(byte* dst, uint cap);

    [LibraryImport(Lib)]
    private static partial nint xpa_detail();

    [LibraryImport(Lib)]
    private static partial int xpa_take_log(byte* dst, uint cap);

    /// <summary>The outputs and microphones Windows lists now. Empty when Windows could not be asked.</summary>
    public static IReadOnlyList<AudioDeviceInfo> List()
    {
        var buf = new byte[65536];
        int n;
        lock (Native)
            fixed (byte* p = buf) n = xpa_list_devices(p, (uint)buf.Length);
        var list = new List<AudioDeviceInfo>();
        if (n <= 0) return list;
        foreach (var line in System.Text.Encoding.UTF8.GetString(buf, 0, n).Split('\n', StringSplitOptions.RemoveEmptyEntries))
        {
            var f = line.Split('\t', 4);
            if (f.Length == 4 && f[2].Length > 0) list.Add(new AudioDeviceInfo(f[2], f[3], f[1] == "1", f[0] == "c"));
        }
        return list;
    }

    /// <summary>The device to open: by <paramref name="id"/> first; if Windows no longer lists it (the
    /// headset is unplugged, the driver was reinstalled and the id changed), by <paramref name="name"/> -
    /// the same name, then a part of it, case-insensitive. Null - the Windows default.</summary>
    public static AudioDeviceInfo? Find(IEnumerable<AudioDeviceInfo> devices, bool capture, string? id, string? name)
    {
        var kind = devices.Where(d => d.IsCapture == capture).ToList();
        if (!string.IsNullOrEmpty(id) && kind.Find(d => d.Id == id) is { } byId) return byId;
        if (string.IsNullOrWhiteSpace(name)) return null;
        return kind.Find(d => string.Equals(d.Name, name, StringComparison.OrdinalIgnoreCase))
            ?? kind.Find(d => d.Name.Contains(name, StringComparison.OrdinalIgnoreCase));
    }

    static string? _outId, _outName, _inId, _inName;

    /// <summary>Before Open, kept for every later Open (each one looks the device up again: it may have
    /// gone or come back): the output and the microphone by id, with the name as the fallback; all
    /// null - the Windows default.</summary>
    public static void Choose(string? outputId, string? outputName, string? inputId, string? inputName)
    {
        _outId = outputId; _outName = outputName; _inId = inputId; _inName = inputName;
    }

    /// <summary>How the last Open found the devices, for the log; Fallback - a chosen device was not
    /// found by its id.</summary>
    public static string Choice { get; private set; } = "";
    public static bool Fallback { get; private set; }

    /// <summary>The output and capture devices Windows lists, its defaults marked [*], with their ids.</summary>
    public static string Devices()
    {
        var all = List();
        string Of(bool capture) => string.Join("; ", all.Where(d => d.IsCapture == capture).Select(d => $"{(d.IsDefault ? "[*] " : "")}{d.Name} {{{d.Id}}}"));
        return $"playback: {Of(false)} | capture: {Of(true)}";
    }

    static string Pick(IReadOnlyList<AudioDeviceInfo> all, bool capture, string? id, string? name, out AudioDeviceInfo? found, ref bool fallback)
    {
        found = Find(all, capture, id, name);
        bool byId = !string.IsNullOrEmpty(id);
        if (!byId && string.IsNullOrWhiteSpace(name)) return "default";
        if (found is not null && byId && found.Id == id) return found.Name;
        if (found is not null && !byId) return found.Name + " (by name)";
        fallback = true;
        return found is not null ? $"{found.Name} (by name, the chosen id is not listed)" : "default (the chosen device is not listed)";
    }

    /// <summary>Diagnostics, numbers and names only: one line per open stream - what was asked, what
    /// WASAPI gave (format, channels, rate, period, buffer, IAudioClient3 or not), the engine's mix
    /// format, latency, offload capability.</summary>
    public static string Detail() => Marshal.PtrToStringUTF8(xpa_detail()) ?? "";

    static readonly byte[] _logBuf = new byte[16384];

    /// <summary>miniaudio's own log lines since the last call ("level: text" per line), or "".</summary>
    public static string TakeLog()
    {
        lock (_logBuf)
        {
            int n;
            fixed (byte* p = _logBuf) n = xpa_take_log(p, (uint)_logBuf.Length);
            return n > 0 ? System.Text.Encoding.UTF8.GetString(_logBuf, 0, n) : "";
        }
    }

    static DataHandler? _handler;
    static Action<string>? _note;

    /// <summary>Opens microphone and speakers (or speakers only). Returns what was opened, for the log;
    /// <paramref name="microphoneOpened"/> says whether the microphone is among it.</summary>
    public static string Open(bool microphone, DataHandler handler, Action<string> note, out bool microphoneOpened)
    {
        var all = List();
        bool fallback = false;
        string outText = Pick(all, false, _outId, _outName, out var output, ref fallback);
        AudioDeviceInfo? input = null;
        string inText = microphone ? Pick(all, true, _inId, _inName, out input, ref fallback) : "none";
        Choice = $"output {outText}, microphone {inText}";
        Fallback = fallback;
        int r;
        string? err, what;
        lock (Native)
        {
            _handler = handler;
            _note = note;
            r = xpa_open(Rate, Period, &OnData, &OnNote, 0, microphone ? 1 : 0, output?.Id ?? "", input?.Id ?? "");
            err = Marshal.PtrToStringUTF8(xpa_error());
            what = Marshal.PtrToStringUTF8(xpa_describe()) ?? "";
        }
        if (r < 0) throw new IOException("sound device: " + err);
        microphoneOpened = r == 1;
        return r == 1 || !microphone ? what : $"{what} (no microphone: {err})";
    }

    public static void Close()
    {
        lock (Native)
        {
            xpa_close();
            _handler = null;
        }
    }

    [UnmanagedCallersOnly(CallConvs = [typeof(CallConvCdecl)])]
    static void OnData(nint user, short* input, short* output, uint frames)
    {
        var outSpan = new Span<short>(output, (int)frames);
        try
        {
            _handler!(input == null ? default : new ReadOnlySpan<short>(input, (int)frames), outSpan);
        }
        catch
        {
            outSpan.Clear();
        }
    }

    static readonly string[] Notes = ["started", "stopped", "rerouted", "interruption began", "interruption ended", "unlocked"];

    [UnmanagedCallersOnly(CallConvs = [typeof(CallConvCdecl)])]
    static void OnNote(nint user, int kind)
    {
        try { _note?.Invoke("device " + (kind >= 0 && kind < Notes.Length ? Notes[kind] : kind.ToString())); }
        catch { }
    }
}
