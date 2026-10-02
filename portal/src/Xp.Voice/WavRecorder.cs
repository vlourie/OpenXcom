namespace Xp.Voice;

/// <summary>
/// 48 kHz mono 16-bit WAV, written from the pump thread: what was sent and what was played, to
/// hear where a defect comes in when the counters say every packet arrived. The header is patched
/// every few seconds, so a killed process still leaves a playable file. The second constructor takes
/// any PCM or float format - the raw loopback, written as Windows hands it over.
/// </summary>
sealed class WavRecorder : IDisposable
{
    readonly FileStream _f;
    readonly long _limit;
    readonly short _tag, _channels, _bits;
    readonly int _rate;
    long _bytes;

    public WavRecorder(string path, int maxSeconds) : this(path, maxSeconds, 1, 1, AudioDevice.Rate, 16) { }

    /// <summary>tag: 1 PCM, 3 IEEE float.</summary>
    public WavRecorder(string path, int maxSeconds, short tag, int channels, int rate, short bits)
    {
        _tag = tag; _channels = (short)channels; _rate = rate; _bits = bits;
        _f = new FileStream(path, FileMode.Create, FileAccess.Write, FileShare.Read);
        _limit = (long)maxSeconds * rate * channels * (bits / 8);
        _f.Write(new byte[44]);
        Patch();
    }

    public void Write(ReadOnlySpan<short> s) => Write(System.Runtime.InteropServices.MemoryMarshal.AsBytes(s));

    public void Write(ReadOnlySpan<byte> b)
    {
        if (_bytes >= _limit) return;
        int block = _channels * (_bits / 8);
        int n = (int)Math.Min(b.Length, (_limit - _bytes) / block * block);
        _f.Write(b[..n]);
        _bytes += n;
    }

    public void Patch()
    {
        long at = _f.Position;
        int block = _channels * (_bits / 8);
        Span<byte> h = stackalloc byte[44];
        "RIFF"u8.CopyTo(h);
        BitConverter.TryWriteBytes(h[4..], (int)(36 + _bytes));
        "WAVEfmt "u8.CopyTo(h[8..]);
        BitConverter.TryWriteBytes(h[16..], 16);
        BitConverter.TryWriteBytes(h[20..], _tag);
        BitConverter.TryWriteBytes(h[22..], _channels);
        BitConverter.TryWriteBytes(h[24..], _rate);
        BitConverter.TryWriteBytes(h[28..], _rate * block);
        BitConverter.TryWriteBytes(h[32..], (short)block);
        BitConverter.TryWriteBytes(h[34..], _bits);
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
