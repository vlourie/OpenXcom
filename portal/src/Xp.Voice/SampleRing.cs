namespace Xp.Voice;

/// <summary>
/// A bounded ring of samples between two threads. Writing past the capacity drops the oldest samples
/// (latency must not grow without end), reading past the end fills silence and reports the shortfall.
/// A lock is enough: both sides touch it a hundred times a second.
/// </summary>
sealed class SampleRing(int capacity)
{
    readonly short[] _buf = new short[capacity];
    readonly Lock _lock = new();
    int _head, _count;

    public int Count { get { lock (_lock) return _count; } }

    /// <returns>how many old samples were dropped to make room</returns>
    public int Write(ReadOnlySpan<short> src)
    {
        lock (_lock)
        {
            int dropped = 0;
            if (src.Length > _buf.Length) { dropped += src.Length - _buf.Length; src = src[^_buf.Length..]; }
            int over = _count + src.Length - _buf.Length;
            if (over > 0) { Skip(over); dropped += over; }
            int tail = (_head + _count) % _buf.Length;
            int first = Math.Min(src.Length, _buf.Length - tail);
            src[..first].CopyTo(_buf.AsSpan(tail));
            src[first..].CopyTo(_buf);
            _count += src.Length;
            return dropped;
        }
    }

    /// <returns>how many samples were really read; the rest of dst is zeroed</returns>
    public int Read(Span<short> dst)
    {
        lock (_lock)
        {
            int n = Math.Min(dst.Length, _count);
            int first = Math.Min(n, _buf.Length - _head);
            _buf.AsSpan(_head, first).CopyTo(dst);
            _buf.AsSpan(0, n - first).CopyTo(dst[first..]);
            dst[n..].Clear();
            _head = (_head + n) % _buf.Length;
            _count -= n;
            return n;
        }
    }

    /// <summary>Keeps only the newest keep samples.</summary>
    public int TrimTo(int keep)
    {
        lock (_lock)
        {
            int over = _count - keep;
            if (over <= 0) return 0;
            Skip(over);
            return over;
        }
    }

    public void Clear() { lock (_lock) { _head = 0; _count = 0; } }

    void Skip(int n)
    {
        _head = (_head + n) % _buf.Length;
        _count -= n;
    }
}
