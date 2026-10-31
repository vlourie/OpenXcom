namespace Xp.Voice;

/// <summary>
/// The microphone check outside a room: opens the chosen microphone and reports its level, nothing is
/// sent anywhere and nothing is played (the output is filled with silence). Shares the one sound device
/// of the process with <see cref="VoiceSession"/> - stop the check before a session starts.
/// </summary>
public sealed class MicCheck : IDisposable
{
    volatile float _db = -90;
    bool _open;

    /// <summary>The level of the last 10 ms, dBFS; -90 for silence or no microphone.</summary>
    public double LevelDb => _db;
    /// <summary>The device opened, but without a microphone: Windows has none or refused it.</summary>
    public bool MicrophoneMissing { get; private set; }

    /// <summary>Throws <see cref="IOException"/> when the sound device does not open at all.</summary>
    public void Start(string? inputId, string? inputName, string? outputId, string? outputName)
    {
        AudioDevice.Choose(outputId, outputName, inputId, inputName);
        AudioDevice.Open(true, OnAudio, _ => { }, out bool mic);
        _open = true;
        MicrophoneMissing = !mic;
    }

    void OnAudio(ReadOnlySpan<short> input, Span<short> output)
    {
        output.Clear();
        if (input.IsEmpty) { _db = -90; return; }
        double sum = 0;
        foreach (var v in input) sum += (double)v * v;
        double rms = Math.Sqrt(sum / input.Length);
        _db = rms < 1 ? -90 : (float)(20 * Math.Log10(rms / 32768));
    }

    public void Dispose()
    {
        if (!_open) return;
        _open = false;
        AudioDevice.Close();
        _db = -90;
    }
}
