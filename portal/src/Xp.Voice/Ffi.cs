using System.Collections.Concurrent;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using Google.Protobuf;
using LiveKit.Proto;

namespace Xp.Voice;

/// <summary>
/// livekit_ffi.dll: the LiveKit Rust SDK behind a C ABI. Every call is a protobuf FfiRequest answered
/// at once with an FfiResponse; long work (connect, publish, capture) answers later with an FfiEvent
/// carrying the async id the request was given. Events arrive on the SDK's own threads.
/// The library is process-wide: one initialize, one dispose at exit.
/// </summary>
static partial class Ffi
{
    const string Lib = "livekit_ffi";

    [LibraryImport(Lib)]
    private static unsafe partial void livekit_ffi_initialize(delegate* unmanaged[Cdecl]<byte*, nuint, void> callback,
        [MarshalAs(UnmanagedType.U1)] bool captureLogs, byte* sdk, byte* sdkVersion);

    [LibraryImport(Lib)]
    private static unsafe partial ulong livekit_ffi_request(byte* data, nuint len, byte** resPtr, nuint* resLen);

    [LibraryImport(Lib)]
    [return: MarshalAs(UnmanagedType.U1)]
    private static partial bool livekit_ffi_drop_handle(ulong handle);

    [LibraryImport(Lib)]
    private static partial void livekit_ffi_dispose();

    static readonly Lock InitLock = new();
    static bool _ready;
    static long _nextAsync;
    static readonly ConcurrentDictionary<ulong, TaskCompletionSource<FfiEvent>> Pending = new();

    /// <summary>Room and audio stream events, called on the SDK's thread: handlers must be quick.</summary>
    public static event Action<FfiEvent>? Events;
    /// <summary>The SDK's own log lines (info and above) and panics.</summary>
    public static event Action<string>? Log;

    public static unsafe void Init()
    {
        lock (InitLock)
        {
            if (_ready) return;
            byte* sdk = stackalloc byte[] { (byte)'x', (byte)'p', 0 };
            byte* ver = stackalloc byte[] { (byte)'0', (byte)'.', (byte)'1', 0 };
            livekit_ffi_initialize(&OnEvent, true, sdk, ver);
            _ready = true;
        }
    }

    public static void Shutdown()
    {
        lock (InitLock)
        {
            if (!_ready) return;
            livekit_ffi_dispose();
            _ready = false;
        }
    }

    public static ulong NextAsyncId() => (ulong)Interlocked.Increment(ref _nextAsync);

    public static unsafe FfiResponse Request(FfiRequest req)
    {
        var data = req.ToByteArray();
        byte* res;
        nuint len;
        ulong handle;
        fixed (byte* p = data)
            handle = livekit_ffi_request(p, (nuint)data.Length, &res, &len);
        if (handle == 0) throw new InvalidOperationException($"livekit_ffi_request refused {req.MessageCase}");
        try { return FfiResponse.Parser.ParseFrom(new ReadOnlySpan<byte>(res, (int)len)); }
        finally { livekit_ffi_drop_handle(handle); }
    }

    /// <summary>
    /// A request whose answer comes as an event. The waiter is registered before the request is sent,
    /// so a callback that beats the response is not lost.
    /// </summary>
    public static async Task<FfiEvent> RequestAsync(FfiRequest req, ulong asyncId, TimeSpan timeout)
    {
        var tcs = new TaskCompletionSource<FfiEvent>(TaskCreationOptions.RunContinuationsAsynchronously);
        Pending[asyncId] = tcs;
        try
        {
            Request(req);
            return await tcs.Task.WaitAsync(timeout).ConfigureAwait(false);
        }
        finally { Pending.TryRemove(asyncId, out _); }
    }

    public static void Drop(ulong handle)
    {
        if (handle != 0) livekit_ffi_drop_handle(handle);
    }

    /// <summary>The samples of an owned frame: valid only until its handle is dropped.</summary>
    public static unsafe ReadOnlySpan<short> Samples(AudioFrameBufferInfo info) =>
        new((void*)info.DataPtr, (int)(info.SamplesPerChannel * info.NumChannels));

    static ulong AsyncIdOf(FfiEvent e) => e.MessageCase switch
    {
        FfiEvent.MessageOneofCase.Connect => e.Connect.AsyncId,
        FfiEvent.MessageOneofCase.Disconnect => e.Disconnect.AsyncId,
        FfiEvent.MessageOneofCase.PublishTrack => e.PublishTrack.AsyncId,
        FfiEvent.MessageOneofCase.UnpublishTrack => e.UnpublishTrack.AsyncId,
        FfiEvent.MessageOneofCase.CaptureAudioFrame => e.CaptureAudioFrame.AsyncId,
        FfiEvent.MessageOneofCase.GetStats => e.GetStats.AsyncId,
        FfiEvent.MessageOneofCase.GetSessionStats => e.GetSessionStats.AsyncId,
        _ => 0,
    };

    [UnmanagedCallersOnly(CallConvs = [typeof(CallConvCdecl)])]
    static unsafe void OnEvent(byte* data, nuint len)
    {
        // an exception must never cross back into Rust
        try
        {
            var e = FfiEvent.Parser.ParseFrom(new ReadOnlySpan<byte>(data, (int)len));
            switch (e.MessageCase)
            {
                case FfiEvent.MessageOneofCase.Logs:
                    foreach (var r in e.Logs.Records)
                        if (r.Level <= LogLevel.LogInfo && !(r.Level == LogLevel.LogInfo && r.Target == "libwebrtc"))
                            Log?.Invoke($"lk {r.Level switch { LogLevel.LogError => "ERROR", LogLevel.LogWarn => "warn", _ => "info" }} {r.Target}: {r.Message}");
                    return;
                case FfiEvent.MessageOneofCase.Panic:
                    Log?.Invoke("lk PANIC: " + e.Panic.Message);
                    return;
            }
            var id = AsyncIdOf(e);
            if (id != 0 && Pending.TryRemove(id, out var tcs)) { tcs.TrySetResult(e); return; }
            Events?.Invoke(e);
        }
        catch (Exception ex)
        {
            try { Log?.Invoke("ffi event handler failed: " + ex); } catch { }
        }
    }
}
