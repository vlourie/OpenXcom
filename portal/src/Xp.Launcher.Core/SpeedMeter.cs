using System.Diagnostics;
using System.Security.Cryptography;

namespace Xp.Launcher.Core;

/// <summary>Speed over a sliding window, for the progress line.</summary>
public sealed class SpeedMeter
{
    readonly Stopwatch _sw = Stopwatch.StartNew();
    readonly Queue<(double T, long Bytes)> _window = new();
    long _total;

    public void Add(long bytes)
    {
        lock (_window)
        {
            _total += bytes;
            var t = _sw.Elapsed.TotalSeconds;
            _window.Enqueue((t, _total));
            while (_window.Count > 2 && t - _window.Peek().T > 3) _window.Dequeue();
        }
    }

    public double BytesPerSecond
    {
        get
        {
            lock (_window)
            {
                if (_window.Count < 2) return 0;
                var first = _window.Peek();
                var dt = _sw.Elapsed.TotalSeconds - first.T;
                return dt <= 0 ? 0 : Math.Max(0, (_total - first.Bytes) / dt);
            }
        }
    }
}

internal static class RandomId
{
    public static string New() => Convert.ToHexStringLower(RandomNumberGenerator.GetBytes(8));
}
