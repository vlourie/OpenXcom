using System.Runtime.InteropServices;
using Avalonia.Threading;
using Xp.Launcher.Core;

namespace Xp.Launcher;

/// <summary>
/// Push-to-talk over the whole system, the game in front included: low-level keyboard and mouse hooks
/// (WH_KEYBOARD_LL, WH_MOUSE_LL). They only look: every event goes on to the next hook and to the game
/// unchanged (CallNextHookEx always). Installed while the player is in a room or assigning the button,
/// removed right after. The callbacks come on the thread that installed the hooks, through its message
/// loop - the UI thread here - so they must return at once: Windows drops a hook that is slow.
/// </summary>
static unsafe partial class TalkHook
{
    const int WH_KEYBOARD_LL = 13, WH_MOUSE_LL = 14;
    const int WM_KEYDOWN = 0x100, WM_KEYUP = 0x101, WM_SYSKEYDOWN = 0x104, WM_SYSKEYUP = 0x105;
    const int WM_XBUTTONDOWN = 0x20B, WM_XBUTTONUP = 0x20C;
    const uint LLKHF_EXTENDED = 0x01;
    const int VK_RETURN = 0x0D, VK_ESCAPE = 0x1B, VK_XBUTTON1 = 0x05, VK_XBUTTON2 = 0x06;

    [StructLayout(LayoutKind.Sequential)]
    struct KbdLl { public uint VkCode, ScanCode, Flags, Time; public nuint ExtraInfo; }

    [StructLayout(LayoutKind.Sequential)]
    struct MouseLl { public int X, Y; public uint MouseData, Flags, Time; public nuint ExtraInfo; }

    [LibraryImport("user32.dll", EntryPoint = "SetWindowsHookExW", SetLastError = true)]
    private static partial nint SetWindowsHookEx(int idHook, delegate* unmanaged<int, nint, nint, nint> fn, nint module, uint threadId);

    [LibraryImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static partial bool UnhookWindowsHookEx(nint hook);

    [LibraryImport("user32.dll")]
    private static partial nint CallNextHookEx(nint hook, int code, nint wParam, nint lParam);

    [LibraryImport("user32.dll")]
    private static partial short GetAsyncKeyState(int vk);

    [LibraryImport("user32.dll", EntryPoint = "MapVirtualKeyW")]
    private static partial uint MapVirtualKey(uint code, uint mapType);

    [LibraryImport("user32.dll", EntryPoint = "GetKeyNameTextW")]
    private static partial int GetKeyNameText(int lParam, char* buffer, int size);

    [LibraryImport("kernel32.dll", EntryPoint = "GetModuleHandleW", StringMarshalling = StringMarshalling.Utf16)]
    private static partial nint GetModuleHandle(string? name);

    static nint _kbd, _mouse;
    static TalkKey _key;
    static bool _down;
    static Action<bool>? _talk;
    static Action<TalkKey?>? _capture;
    static DispatcherTimer? _watch;

    public static bool Pressed => _down;

    /// <summary>Starts following the button: talk(true) when it goes down, talk(false) when it comes up.</summary>
    public static bool Follow(TalkKey key, Action<bool> talk)
    {
        _key = key;
        _talk = talk;
        _down = false;
        return Install();
    }

    public static void StopFollowing()
    {
        if (_down) { _down = false; _talk?.Invoke(false); }
        _talk = null;
        UninstallIfIdle();
    }

    /// <summary>The next key or side mouse button pressed anywhere is the new button; Escape gives null (cancel).</summary>
    public static bool Capture(Action<TalkKey?> done)
    {
        _capture = done;
        if (Install()) return true;
        _capture = null;
        return false;
    }

    public static void CancelCapture()
    {
        if (_capture is null) return;
        _capture = null;
        UninstallIfIdle();
    }

    static bool Install()
    {
        if (!OperatingSystem.IsWindows()) return false;
        nint module = GetModuleHandle(null);
        if (_kbd == 0) _kbd = SetWindowsHookEx(WH_KEYBOARD_LL, &OnKeyboard, module, 0);
        if (_mouse == 0) _mouse = SetWindowsHookEx(WH_MOUSE_LL, &OnMouse, module, 0);
        if (_watch is null)
        {
            // a key-up the hook never saw (Windows dropped the hook, a secure desktop came up) must not
            // leave the microphone open: the real state of the button is checked a few times a second
            _watch = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(250) };
            _watch.Tick += (_, _) =>
            {
                if (!_down || IsHeld(_key)) return;
                _down = false;
                _talk?.Invoke(false);
            };
            _watch.Start();
        }
        return _kbd != 0 && _mouse != 0;
    }

    static void UninstallIfIdle()
    {
        if (_talk is not null || _capture is not null) return;
        if (_kbd != 0) { UnhookWindowsHookEx(_kbd); _kbd = 0; }
        if (_mouse != 0) { UnhookWindowsHookEx(_mouse); _mouse = 0; }
        _watch?.Stop();
        _watch = null;
    }

    static bool IsHeld(TalkKey k) =>
        (GetAsyncKeyState(k.Mouse ? (k.Code == 1 ? VK_XBUTTON1 : VK_XBUTTON2) : k.Code) & 0x8000) != 0;

    [UnmanagedCallersOnly]
    static nint OnKeyboard(int code, nint wParam, nint lParam)
    {
        if (code >= 0)
        {
            var k = (KbdLl*)lParam;
            int msg = (int)wParam;
            bool down = msg is WM_KEYDOWN or WM_SYSKEYDOWN, up = msg is WM_KEYUP or WM_SYSKEYUP;
            int vk = (int)k->VkCode;
            bool ext = (k->Flags & LLKHF_EXTENDED) != 0;
            if (down && _capture is { } done)
            {
                _capture = null;
                // only Enter has two SDL keys by the extended bit; for the rest it is noise
                var key = vk == VK_ESCAPE ? (TalkKey?)null : new TalkKey(false, vk, vk == VK_RETURN && ext);
                Dispatcher.UIThread.Post(() => { done(key); UninstallIfIdle(); });
            }
            else if (_talk is not null && !_key.Mouse && vk == _key.Code && (vk != VK_RETURN || ext == _key.Extended))
                Change(down ? true : up ? false : _down);
        }
        return CallNextHookEx(0, code, wParam, lParam);
    }

    [UnmanagedCallersOnly]
    static nint OnMouse(int code, nint wParam, nint lParam)
    {
        if (code >= 0 && (int)wParam is WM_XBUTTONDOWN or WM_XBUTTONUP)
        {
            var m = (MouseLl*)lParam;
            int button = (int)(m->MouseData >> 16);
            bool down = (int)wParam == WM_XBUTTONDOWN;
            if (down && _capture is { } done && button is 1 or 2)
            {
                _capture = null;
                var key = new TalkKey(true, button);
                Dispatcher.UIThread.Post(() => { done(key); UninstallIfIdle(); });
            }
            else if (_talk is not null && _key.Mouse && button == _key.Code)
                Change(down);
        }
        return CallNextHookEx(0, code, wParam, lParam);
    }

    static void Change(bool down)
    {
        // a held key repeats its key-down: only the edges count
        if (down == _down) return;
        _down = down;
        _talk?.Invoke(down);
    }

    /// <summary>The button as the keyboard layout names it ("Ё", "F5", "Пробел"), or the side mouse button.</summary>
    public static string Name(TalkKey key)
    {
        if (key.Mouse) return L.T(key.Code == 1 ? "voice.mouse4" : "voice.mouse5");
        if (OperatingSystem.IsWindows())
        {
            uint scan = MapVirtualKey((uint)key.Code, 0 /* MAPVK_VK_TO_VSC */);
            // the arrows, Insert/Delete, Home/End, PageUp/Down and the right modifiers are "extended" keys:
            // without the bit GetKeyNameText names their keypad twins
            bool ext = key.Extended || key.Code is >= 0x21 and <= 0x2E or 0x5B or 0x5C or 0x5D or 0xA3 or 0xA5 or 0x6F or 0x90;
            int lParam = (int)(scan << 16) | (ext ? 1 << 24 : 0);
            var buf = stackalloc char[64];
            int n = scan == 0 ? 0 : GetKeyNameText(lParam, buf, 64);
            if (n > 0) return new string(buf, 0, n);
        }
        return $"VK {key.Code}";
    }
}
