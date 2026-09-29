using System.Runtime.InteropServices;

namespace Xp.Voice;

/// <summary>
/// Windows 11 slows a process whose windows are all minimized or hidden: timer requests are ignored
/// (sleeps round to 15.6 ms) and threads may be put on efficiency cores (EcoQoS). The voice keeps
/// 10 ms pacing inside the LiveKit runtime, so while a room is open the process opts out of both.
/// </summary>
static partial class Pace
{
    [StructLayout(LayoutKind.Sequential)]
    struct PowerThrottlingState
    {
        public uint Version, ControlMask, StateMask;
    }

    const int ProcessPowerThrottling = 4;
    const uint ExecutionSpeed = 0x1, IgnoreTimerResolution = 0x4;

    [LibraryImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static partial bool SetProcessInformation(nint process, int infoClass, ref PowerThrottlingState info, uint size);

    [LibraryImport("kernel32.dll")]
    private static partial nint GetCurrentProcess();

    [LibraryImport("winmm.dll")]
    private static partial uint timeBeginPeriod(uint ms);

    [LibraryImport("winmm.dll")]
    private static partial uint timeEndPeriod(uint ms);

    /// <returns>a line for the log</returns>
    public static string Hold()
    {
        // ControlMask names the policies we decide, StateMask 0 means "off" for each of them
        var s = new PowerThrottlingState { Version = 1, ControlMask = ExecutionSpeed | IgnoreTimerResolution, StateMask = 0 };
        bool ok = SetProcessInformation(GetCurrentProcess(), ProcessPowerThrottling, ref s, (uint)Marshal.SizeOf<PowerThrottlingState>());
        uint t = timeBeginPeriod(1);
        return $"pace: no EcoQoS, timer honoured when hidden: {(ok ? "yes" : "no, error " + Marshal.GetLastPInvokeError())}; 1 ms timer: {(t == 0 ? "yes" : "no")}";
    }

    public static void Release() => timeEndPeriod(1);
}
