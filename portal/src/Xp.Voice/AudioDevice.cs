using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;

namespace Xp.Voice;

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

    [LibraryImport(Lib)]
    private static partial int xpa_open(uint rate, uint period, delegate* unmanaged[Cdecl]<nint, short*, short*, uint, void> data,
        delegate* unmanaged[Cdecl]<nint, int, void> note, nint user, int capture);

    [LibraryImport(Lib)]
    private static partial void xpa_close();

    [LibraryImport(Lib)]
    private static partial void xpa_stop();

    [LibraryImport(Lib)]
    private static partial int xpa_capture_count();

    /// <summary>How many capture devices Windows lists now (-1: not open or unknown) - whether a
    /// missing microphone is worth a reopening.</summary>
    public static int CaptureDevices() => xpa_capture_count();

    [LibraryImport(Lib)]
    private static partial nint xpa_error();

    [LibraryImport(Lib)]
    private static partial nint xpa_describe();

    [LibraryImport(Lib)]
    private static partial int xpa_loopback_start(uint rate);

    [LibraryImport(Lib)]
    private static partial int xpa_loopback_read(short* dst, uint max);

    /// <summary>Diagnostics: starts recording what Windows renders on the output the voice plays on (the
    /// default one unless --output chose another; every app's sound after the system mix), converted to
    /// 48 kHz mono 16-bit. Returns null or the error text.</summary>
    public static string? StartLoopback() =>
        xpa_loopback_start(Rate) == 0 ? null : Marshal.PtrToStringUTF8(xpa_error());

    /// <summary>Takes up to dst.Length loopback samples recorded since the last call.</summary>
    public static int ReadLoopback(Span<short> dst)
    {
        fixed (short* p = dst) return xpa_loopback_read(p, (uint)dst.Length);
    }

    // ---------------------------------------------------------------- diagnostics of the "robot" (docs/research/voice-robot-2026-10-02.md)

    /// <summary>WASAPI switches tried one at a time against the default (None, the control). The first
    /// three are miniaudio's (NoAc3 through tools/voice_ma_patch.py); Period20 opens the device with a
    /// 20 ms period instead of 10 ms.</summary>
    [Flags]
    public enum Switches { None = 0, NoOffload = 1, NoConvert = 2, NoAc3 = 4, Period20 = 8 }

    static readonly (string Name, Switches Flag)[] SwitchNames =
        [("nooffload", Switches.NoOffload), ("noconvert", Switches.NoConvert), ("noac3", Switches.NoAc3), ("period20", Switches.Period20)];

    /// <summary>"noac3,nooffload" -> the flags; "none" and "" are the default. Names it does not know
    /// go to <paramref name="unknown"/> for the log.</summary>
    public static Switches ParseSwitches(string list, out string unknown)
    {
        var s = Switches.None;
        var bad = new List<string>();
        foreach (var part in list.Split([',', ' ', '+'], StringSplitOptions.RemoveEmptyEntries))
        {
            var name = part.ToLowerInvariant();
            if (name == "none") continue;
            var hit = Array.Find(SwitchNames, n => n.Name == name);
            if (hit.Name is null) bad.Add(part);
            else s |= hit.Flag;
        }
        unknown = string.Join(",", bad);
        return s;
    }

    public static string SwitchText(Switches s) =>
        s == Switches.None ? "none (control)" : string.Join(",", SwitchNames.Where(n => (s & n.Flag) != 0).Select(n => n.Name));

    [LibraryImport(Lib, StringMarshalling = StringMarshalling.Utf8)]
    private static partial void xpa_set_options(uint flags, string output, string input);

    [LibraryImport(Lib)]
    private static partial nint xpa_devices();

    [LibraryImport(Lib)]
    private static partial nint xpa_detail();

    [LibraryImport(Lib)]
    private static partial int xpa_take_log(byte* dst, uint cap);

    static Switches _switches;

    /// <summary>Before Open, kept for every later Open: the switches and the output / input chosen by a
    /// part of the name (case-insensitive; null or empty - the Windows default).</summary>
    public static void SetOptions(Switches switches, string? output, string? input)
    {
        _switches = switches;
        xpa_set_options((uint)(switches & ~Switches.Period20), output ?? "", input ?? "");
    }

    /// <summary>Frames per device callback: 10 ms, or 20 ms with Period20.</summary>
    public static int DevicePeriod => (_switches & Switches.Period20) != 0 ? Rate / 50 : Period;

    /// <summary>The output and capture devices Windows lists, its defaults marked [*].</summary>
    public static string Devices() => Marshal.PtrToStringUTF8(xpa_devices()) ?? "";

    /// <summary>One line per open stream: what was asked, what WASAPI gave (format, channels, rate,
    /// period, buffer, IAudioClient3 or not), the engine's mix format, latency, offload capability.</summary>
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

    [LibraryImport(Lib)]
    private static partial int xpa_loopback_raw_start();

    [LibraryImport(Lib)]
    private static partial int xpa_loopback_raw_format(int* format, uint* channels, uint* rate);

    [LibraryImport(Lib)]
    private static partial int xpa_loopback_raw_read(byte* dst, uint max);

    /// <summary>The engine's own format of the raw loopback: miniaudio's ma_format (1 u8, 2 s16, 3 s24,
    /// 4 s32, 5 f32), with the matching WAV format tag and bits.</summary>
    public readonly record struct RawFormat(int Format, int Channels, int Rate)
    {
        public short Tag => (short)(Format == 5 ? 3 : 1);
        public short Bits => (short)(Format switch { 1 => 8, 2 => 16, 3 => 24, _ => 32 });
        public override string ToString() =>
            $"{(Format switch { 1 => "u8", 2 => "s16", 3 => "s24", 4 => "s32", 5 => "f32", _ => "?" })} {Channels} ch {Rate} Hz";
    }

    /// <summary>Diagnostics: the same loopback raw - opened in the engine's mix format, the bytes as
    /// Windows hands them over, nothing converted. Returns null or the error text.</summary>
    public static string? StartRawLoopback(out RawFormat format)
    {
        format = default;
        if (xpa_loopback_raw_start() != 0) return Marshal.PtrToStringUTF8(xpa_error());
        int f; uint ch, rate;
        if (xpa_loopback_raw_format(&f, &ch, &rate) != 0) return "raw loopback: no format";
        format = new RawFormat(f, (int)ch, (int)rate);
        return null;
    }

    /// <summary>Takes up to dst.Length bytes of the raw loopback recorded since the last call.</summary>
    public static int ReadRawLoopback(Span<byte> dst)
    {
        fixed (byte* p = dst) return xpa_loopback_raw_read(p, (uint)dst.Length);
    }

    static DataHandler? _handler;
    static Action<string>? _note;

    /// <summary>Opens microphone and speakers (or speakers only). Returns what was opened, for the log;
    /// <paramref name="microphoneOpened"/> says whether the microphone is among it.</summary>
    public static string Open(bool microphone, DataHandler handler, Action<string> note, out bool microphoneOpened)
    {
        _handler = handler;
        _note = note;
        int r = xpa_open(Rate, (uint)DevicePeriod, &OnData, &OnNote, 0, microphone ? 1 : 0);
        if (r < 0) throw new IOException("sound device: " + Marshal.PtrToStringUTF8(xpa_error()));
        var err = Marshal.PtrToStringUTF8(xpa_error());
        var what = Marshal.PtrToStringUTF8(xpa_describe()) ?? "";
        microphoneOpened = r == 1;
        return r == 1 ? what : $"{what} (no microphone: {err})";
    }

    public static void Close()
    {
        xpa_close();
        _handler = null;
    }

    /// <summary>Test only: stops the device as Windows does when it takes the card away (the callback
    /// ends, the "stopped" note fires). Close and Open again to recover, as after a real stop.</summary>
    public static void Stop() => xpa_stop();

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
