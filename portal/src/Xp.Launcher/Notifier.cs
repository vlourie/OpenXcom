using System.Runtime.InteropServices;
using Avalonia.Controls;

namespace Xp.Launcher;

/// <summary>
/// A Windows notification from the launcher: a notify icon of its own with a balloon, which Windows 10 and 11
/// show as a toast and keep in the notification centre. Avalonia's tray icon has no balloons, and it lives
/// only in a voice room or under the game. The icon stays as a reminder until the player clicks it or the
/// balloon (both open the launcher) or the window comes forward by itself.
/// The callbacks come through the main window's message loop: its handle lives while the window is hidden too.
/// </summary>
sealed unsafe partial class Notifier(Window window, Action clicked) : IDisposable
{
    const uint Callback = 0x8000 + 0x58;   // WM_APP + "X"
    const uint Id = 0x5850;
    const uint NIM_ADD = 0, NIM_MODIFY = 1, NIM_DELETE = 2;
    const uint NIF_MESSAGE = 0x1, NIF_ICON = 0x2, NIF_TIP = 0x4, NIF_INFO = 0x10;
    const uint NIIF_USER = 0x4, NIIF_LARGE_ICON = 0x20;
    const int NIN_BALLOONHIDE = 0x403, NIN_BALLOONTIMEOUT = 0x404, NIN_BALLOONUSERCLICK = 0x405, WM_LBUTTONUP = 0x202;

    [StructLayout(LayoutKind.Sequential)]
    struct NotifyIconData
    {
        public uint Size;
        public nint Wnd;
        public uint Id, Flags, CallbackMessage;
        public nint Icon;
        public fixed char Tip[128];
        public uint State, StateMask;
        public fixed char Info[256];
        public uint TimeoutOrVersion;
        public fixed char InfoTitle[64];
        public uint InfoFlags;
        public Guid Item;
        public nint BalloonIcon;
    }

    [LibraryImport("shell32.dll", EntryPoint = "Shell_NotifyIconW")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static partial bool Shell_NotifyIcon(uint message, NotifyIconData* data);

    [LibraryImport("shell32.dll", EntryPoint = "ExtractIconExW", StringMarshalling = StringMarshalling.Utf16)]
    private static partial uint ExtractIconEx(string file, int index, nint* large, nint* small, uint count);

    [LibraryImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static partial bool DestroyIcon(nint icon);

    nint _wnd, _large, _small;
    bool _shown, _stay;
    Win32Properties.CustomWndProcHookCallback? _hook;

    public bool Shown => _shown;

    /// <summary>
    /// Shows the balloon (the icon first, if it is not there yet). With <paramref name="stay"/> off the icon goes
    /// with the balloon - a hint, not news. Quietly nothing off Windows.
    /// </summary>
    public void Show(string title, string text, bool stay = true)
    {
        _stay = stay || (_shown && _stay);   // news already waiting keeps its icon
        if (!OperatingSystem.IsWindows()) return;
        if (_wnd == 0) _wnd = window.TryGetPlatformHandle()?.Handle ?? 0;
        if (_wnd == 0) return;
        if (_hook is null)
        {
            _hook = Hook;
            Win32Properties.AddWndProcHookCallback(window, _hook);
        }
        if (_small == 0 && Environment.ProcessPath is { } exe)
        {
            nint large, small;
            if (ExtractIconEx(exe, 0, &large, &small, 1) > 0) (_large, _small) = (large, small);
        }
        var d = Data();
        d.Flags = NIF_MESSAGE | NIF_ICON | NIF_TIP;
        Put(d.Tip, 128, title);
        if (!_shown) _shown = Shell_NotifyIcon(NIM_ADD, &d);
        else Shell_NotifyIcon(NIM_MODIFY, &d);
        if (!_shown) return;
        d.Flags = NIF_INFO;
        Put(d.Info, 256, text);
        Put(d.InfoTitle, 64, title);
        d.InfoFlags = NIIF_USER | (_large != 0 ? NIIF_LARGE_ICON : 0);
        d.BalloonIcon = _large;
        Shell_NotifyIcon(NIM_MODIFY, &d);
    }

    /// <summary>The icon away, and with it the toast in the notification centre.</summary>
    public void Hide()
    {
        if (!_shown) return;
        var d = Data();
        Shell_NotifyIcon(NIM_DELETE, &d);
        _shown = false;
    }

    NotifyIconData Data() => new()
    {
        Size = (uint)sizeof(NotifyIconData), Wnd = _wnd, Id = Id, CallbackMessage = Callback, Icon = _small,
    };

    static void Put(char* to, int capacity, string text)
    {
        var n = Math.Min(text.Length, capacity - 1);
        for (int i = 0; i < n; i++) to[i] = text[i];
        to[n] = '\0';
    }

    nint Hook(nint wnd, uint message, nint wParam, nint lParam, ref bool handled)
    {
        if (message != Callback || (uint)wParam != Id) return 0;
        handled = true;
        switch ((int)(lParam & 0xFFFF))
        {
            case NIN_BALLOONUSERCLICK or WM_LBUTTONUP:
                Hide();
                clicked();
                break;
            case NIN_BALLOONTIMEOUT or NIN_BALLOONHIDE when !_stay:
                Hide();
                break;
        }
        return 0;
    }

    public void Dispose()
    {
        Hide();
        if (_hook is not null) Win32Properties.RemoveWndProcHookCallback(window, _hook);
        _hook = null;
        if (_large != 0) DestroyIcon(_large);
        if (_small != 0) DestroyIcon(_small);
        _large = _small = 0;
    }
}
