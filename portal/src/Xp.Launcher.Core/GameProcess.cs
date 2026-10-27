using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;

namespace Xp.Launcher.Core;

public static partial class GameProcess
{
    /// <summary>True if any running process has its executable inside <paramref name="gameDir"/>.</summary>
    public static bool IsRunningIn(string gameDir)
    {
        var root = Path.GetFullPath(gameDir).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        var self = Environment.ProcessId;
        foreach (var p in Process.GetProcesses())
        {
            using (p)
            {
                if (p.Id == self) continue;
                var exe = ImagePath(p);
                if (exe is not null && exe.StartsWith(root, StringComparison.OrdinalIgnoreCase)
                    && !exe.StartsWith(root + "launcher" + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                    return true;
            }
        }
        return false;
    }

    /// <summary>
    /// The exe of a live process, null for an exited one or one closed to us. On Windows one query with the least
    /// access: MainModule reads the whole module list of each process, about a second for all of them (code audit 27.10).
    /// </summary>
    static string? ImagePath(Process p)
    {
        if (OperatingSystem.IsWindows())
        {
            var h = OpenProcess(ProcessQueryLimitedInformation, false, p.Id);
            if (h == 0) return null;
            try
            {
                // an exited process stays in the list while anyone holds its handle
                if (GetExitCodeProcess(h, out var code) && code != StillActive) return null;
                return ImageName(h);
            }
            finally { CloseHandle(h); }
        }
        try { return p.HasExited ? null : p.MainModule?.FileName; }
        catch (Exception e) when (e is Win32Exception or InvalidOperationException or NotSupportedException) { return null; }
    }

    static unsafe string? ImageName(nint process)
    {
        var buf = new char[1024];
        int n = buf.Length;
        fixed (char* p = buf)
            return QueryFullProcessImageNameW(process, 0, p, ref n) ? new string(buf, 0, n) : null;
    }

    const uint ProcessQueryLimitedInformation = 0x1000;
    const uint StillActive = 259;

    [LibraryImport("kernel32.dll")]
    private static partial nint OpenProcess(uint access, [MarshalAs(UnmanagedType.Bool)] bool inherit, int pid);

    [LibraryImport("kernel32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static partial bool GetExitCodeProcess(nint process, out uint code);

    [LibraryImport("kernel32.dll", EntryPoint = "QueryFullProcessImageNameW")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static unsafe partial bool QueryFullProcessImageNameW(nint process, uint flags, char* name, ref int size);

    [LibraryImport("kernel32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static partial bool CloseHandle(nint handle);

    /// <summary>Starts the game from its own directory and returns the process, for exit-code tracking.</summary>
    public static Process Start(GamePaths paths, string launchRelative, IEnumerable<string>? args = null)
    {
        var exe = paths.Full(launchRelative);
        if (!File.Exists(exe)) throw new FileNotFoundException("game executable not found", launchRelative);
        var psi = new ProcessStartInfo(exe) { WorkingDirectory = paths.GameDir, UseShellExecute = false };
        foreach (var a in args ?? []) psi.ArgumentList.Add(a);
        // F8 in the game starts this exe with --report (src/Engine/Feedback.cpp, findLauncher)
        if (Environment.ProcessPath is { } self) psi.Environment["XP_LAUNCHER"] = self;
        return Process.Start(psi) ?? throw new InvalidOperationException("the game did not start");
    }
}

public interface ILauncherLog
{
    void Info(string message);
    void Error(string message);
}

/// <summary>
/// Local log without secrets or personal data: absolute paths are written relative to the
/// game directory, the user profile path is masked. Rotates at 5 MB, keeps 10 files.
/// </summary>
public sealed class FileLog : ILauncherLog
{
    const long MaxBytes = 5L * 1024 * 1024;
    const int Keep = 10;
    readonly string _dir;
    readonly string _file;
    readonly string _game;
    readonly string _profile = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
    readonly object _lock = new();

    public FileLog(GamePaths paths)
    {
        _dir = paths.Logs;
        _file = Path.Combine(_dir, "launcher.log");
        _game = paths.GameDir;
        Directory.CreateDirectory(_dir);
    }

    public event Action<string>? Written;

    public void Info(string message) => Write("INFO ", message);
    public void Error(string message) => Write("ERROR", message);

    public string Mask(string s)
    {
        if (_game.Length > 0) s = s.Replace(_game, "<game>", StringComparison.OrdinalIgnoreCase);
        if (_profile.Length > 3) s = s.Replace(_profile, "<profile>", StringComparison.OrdinalIgnoreCase);
        return s;
    }

    void Write(string level, string message)
    {
        var line = $"{DateTimeOffset.Now:yyyy-MM-dd HH:mm:ss} {level} {Mask(message)}";
        lock (_lock)
        {
            try
            {
                if (File.Exists(_file) && new FileInfo(_file).Length > MaxBytes) Rotate();
                File.AppendAllText(_file, line + Environment.NewLine, Encoding.UTF8);
            }
            catch (IOException) { /* the log must never break an update */ }
        }
        Written?.Invoke(line);
    }

    void Rotate()
    {
        for (int i = Keep - 1; i >= 1; i--)
        {
            var from = Path.Combine(_dir, $"launcher.{i}.log");
            if (File.Exists(from)) File.Move(from, Path.Combine(_dir, $"launcher.{i + 1}.log"), overwrite: true);
        }
        File.Move(_file, Path.Combine(_dir, "launcher.1.log"), overwrite: true);
        var oldest = Path.Combine(_dir, $"launcher.{Keep + 1}.log");
        if (File.Exists(oldest)) File.Delete(oldest);
    }
}
