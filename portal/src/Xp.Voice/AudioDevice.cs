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
    private static partial int xpa_capture_count();

    /// <summary>How many capture devices Windows lists now (-1: not open or unknown) - whether a
    /// missing microphone is worth a reopening.</summary>
    public static int CaptureDevices() => xpa_capture_count();

    [LibraryImport(Lib)]
    private static partial nint xpa_error();

    [LibraryImport(Lib)]
    private static partial nint xpa_describe();

    [LibraryImport(Lib, StringMarshalling = StringMarshalling.Utf8)]
    private static partial void xpa_set_options(string output, string input);

    [LibraryImport(Lib)]
    private static partial nint xpa_devices();

    [LibraryImport(Lib)]
    private static partial nint xpa_detail();

    [LibraryImport(Lib)]
    private static partial int xpa_take_log(byte* dst, uint cap);

    /// <summary>Before Open, kept for every later Open: the output / input chosen by a part of the name
    /// (case-insensitive; null or empty - the Windows default).</summary>
    public static void SetOptions(string? output, string? input) => xpa_set_options(output ?? "", input ?? "");

    /// <summary>The output and capture devices Windows lists, its defaults marked [*].</summary>
    public static string Devices() => Marshal.PtrToStringUTF8(xpa_devices()) ?? "";

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
        _handler = handler;
        _note = note;
        int r = xpa_open(Rate, Period, &OnData, &OnNote, 0, microphone ? 1 : 0);
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
