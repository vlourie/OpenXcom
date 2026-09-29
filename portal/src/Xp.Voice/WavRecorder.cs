namespace Xp.Voice;

/// <summary>
/// 48 kHz mono 16-bit WAV, written from the pump thread: what was sent and what was played, to
/// hear where a defect comes in when the counters say every packet arrived. The header is patched
/// every few seconds, so a killed process still leaves a playable file.
/// </summary>
sealed class WavRecorder : IDisposable
{
    readonly FileStream _f;
    readonly long _limit;
    long _bytes;

    public WavRecorder(string path, int maxSeconds)
    {
        _f = new FileStream(path, FileMode.Create, FileAccess.Write, FileShare.Read);
        _limit = (long)maxSeconds * AudioDevice.Rate * 2;
        _f.Write(new byte[44]);
        Patch();
    }

    public void Write(ReadOnlySpan<short> s)
    {
        if (_bytes >= _limit) return;
        var b = System.Runtime.InteropServices.MemoryMarshal.AsBytes(s);
        _f.Write(b);
        _bytes += b.Length;
    }

    public void Patch()
    {
        long at = _f.Position;
        Span<byte> h = stackalloc byte[44];
        "RIFF"u8.CopyTo(h);
        BitConverter.TryWriteBytes(h[4..], (int)(36 + _bytes));
        "WAVEfmt "u8.CopyTo(h[8..]);
        BitConverter.TryWriteBytes(h[16..], 16);
        BitConverter.TryWriteBytes(h[20..], (short)1);
        BitConverter.TryWriteBytes(h[22..], (short)1);
        BitConverter.TryWriteBytes(h[24..], AudioDevice.Rate);
        BitConverter.TryWriteBytes(h[28..], AudioDevice.Rate * 2);
        BitConverter.TryWriteBytes(h[32..], (short)2);
        BitConverter.TryWriteBytes(h[34..], (short)16);
        "data"u8.CopyTo(h[36..]);
        BitConverter.TryWriteBytes(h[40..], (int)_bytes);
        _f.Position = 0;
        _f.Write(h);
        _f.Position = at;
        _f.Flush();
    }

    public void Dispose()
    {
        Patch();
        _f.Dispose();
    }
}
