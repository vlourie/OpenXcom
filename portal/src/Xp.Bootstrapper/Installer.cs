using System.Diagnostics;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.Marshalling;
using System.Text;
using System.Text.Json;
using Xp.Launcher.Core;
using Xp.Manifest;

namespace Xp.Bootstrapper;

/// <summary>
/// xp-bootstrap started with no arguments is the file the site hands out as XPiratezHD-Setup-&lt;v&gt;.exe:
/// it fetches the launcher from the launcher channel, verifies it like the launcher verifies
/// everything (signed pointer and manifest, SHA-256 of each file), installs it into
/// %LOCALAPPDATA%\Programs\XPiratezHD, makes shortcuts and starts it. Before this the no-argument
/// start logged "incomplete arguments" and exited, and the player saw nothing at all.
/// </summary>
static class Installer
{
    const string LauncherExe = "XPiratezLauncher.exe";
    const string ProductName = "X-Piratez HD";

    public static string InstallDir => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "XPiratezHD");

    static bool Ru => (GetUserDefaultUILanguage() & 0x3FF) == 0x19;
    static string T(string ru, string en) => Ru ? ru : en;

    public static int Run(Action<string> log)
    {
        AllocConsole();
        Console.OutputEncoding = Encoding.UTF8;
        Console.Title = ProductName;
        try
        {
            var exe = InstallAsync(log).GetAwaiter().GetResult();
            MakeShortcuts(exe, log);
            Say(T("Запускаю лаунчер...", "Starting the launcher..."));
            Process.Start(new ProcessStartInfo(exe) { WorkingDirectory = InstallDir, UseShellExecute = true });
            log("install done: " + exe);
            Thread.Sleep(1500);
            return 0;
        }
        catch (Exception e)
        {
            log("install FAILED " + e.GetType().Name + ": " + e.Message);
            Console.WriteLine();
            Say(T("Установка не удалась: ", "Install failed: ") + e.Message);
            Say(T("Подробности: ", "Details: ") + Path.Combine(LogDir, "bootstrap.log"));
            Say(T("Нажмите Enter, чтобы закрыть окно.", "Press Enter to close this window."));
            Console.ReadLine();
            return 5;
        }
    }

    public static string LogDir => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "XPiratezLauncher");

    static void Say(string s) => Console.WriteLine(s);

    static async Task<string> InstallAsync(Action<string> log)
    {
        Say(ProductName + " — " + T("установка лаунчера", "launcher setup"));
        Say(T("Папка: ", "Folder: ") + InstallDir);
        LoadSodium(log);

        var (repoUrl, channel) = Config();
        log($"install: {repoUrl} channel {channel} into {InstallDir}");
        using var http = RepoClient.NewHttpClient();
        var repo = new RepoClient(http, new Uri(repoUrl), Keys());

        Say(T("Спрашиваю у сервера последнюю версию...", "Asking the server for the latest version..."));
        LatestRelease latest;
        try { latest = await repo.GetLatestAsync(channel, 0, CancellationToken.None); }
        catch (Exception e) when (e is HttpRequestException or TaskCanceledException or IOException)
        {
            var have = Path.Combine(InstallDir, LauncherExe);
            if (!File.Exists(have)) throw new IOException(T("сервер недоступен: ", "server unreachable: ") + e.Message, e);
            log("install: server unreachable, starting the installed launcher: " + e.Message);
            Say(T("Сервер недоступен, запускаю уже установленный лаунчер.", "Server unreachable, starting the installed launcher."));
            return have;
        }
        var m = latest.Manifest;
        if (!m.Files.Any(f => f.Path.Equals(LauncherExe, StringComparison.OrdinalIgnoreCase)))
            throw new ManifestException($"launcher release {m.Release.Id} has no {LauncherExe}");
        Say(T("Версия ", "Version ") + m.Release.Version);

        long total = m.Files.Sum(f => f.Size), done = 0;
        foreach (var f in m.Files)
        {
            var target = SafePath.Resolve(InstallDir, f.Path);
            if (!(File.Exists(target) && new FileInfo(target).Length == f.Size && Hashing.FileSha256(target) == f.Sha256))
            {
                // downloaded next to the target and moved in only after the hash matched (RepoClient)
                await repo.DownloadBlobAsync(f.Sha256, f.Size, target + ".xp-new",
                    n => { done += n; Progress(done, total); }, CancellationToken.None);
                File.Move(target + ".xp-new", target, overwrite: true);
            }
            else done += f.Size;
            Progress(done, total);
        }
        Console.WriteLine();
        log($"install: launcher {m.Release.Version} ({m.Files.Count} files)");

        return Path.Combine(InstallDir, LauncherExe);
    }

    static long _shown = -1;

    static void Progress(long done, long total)
    {
        var pct = total > 0 ? done * 100 / total : 100;
        if (pct == _shown) return;
        _shown = pct;
        Console.Write($"\r{T("Скачано", "Downloaded")} {done / 1048576.0,6:F1} / {total / 1048576.0:F1} MB ({pct,3}%)");
    }

    static (string RepoUrl, string Channel) Config()
    {
        using var d = JsonDocument.Parse(Resource("defaults.json"));
        var repo = d.RootElement.GetProperty("repoUrl").GetString() ?? "";
        var ch = d.RootElement.TryGetProperty("channels", out var c) && c.GetArrayLength() > 0 ? c[0].GetString() ?? "stable" : "stable";
        // the launcher's own override of the server (development, own station) applies here too
        var settings = Path.Combine(LogDir, "settings.json");
        if (File.Exists(settings))
        {
            try
            {
                using var s = JsonDocument.Parse(File.ReadAllBytes(settings));
                if (s.RootElement.TryGetProperty("repoUrl", out var r) && r.GetString() is { Length: > 0 } own) repo = own;
            }
            catch (JsonException) { }
        }
        if (repo.Length == 0) throw new InvalidOperationException("no release server compiled in");
        return (repo, "launcher-" + ch);
    }

    /// <summary>Same rule as the launcher (BuiltIn.LoadKeys): only "prod" keys, "dev" in Debug or with AllowDevKeys.</summary>
    static TrustedKeys Keys()
    {
        var keys = new List<string>();
        foreach (var raw in Encoding.UTF8.GetString(Resource("release-keys.txt")).Split('\n'))
        {
            var line = raw.Trim();
            if (line.Length == 0 || line.StartsWith('#')) continue;
            var parts = line.Split(' ', 2, StringSplitOptions.TrimEntries);
            if (parts.Length != 2) continue;
            if (parts[0] == "prod") keys.Add(parts[1]);
#if ALLOW_DEV_KEYS
            else if (parts[0] == "dev") keys.Add(parts[1]);
#endif
        }
        return new TrustedKeys(keys);
    }

    static byte[] Resource(string name)
    {
        using var s = Assembly.GetExecutingAssembly().GetManifestResourceStream(name)
                      ?? throw new InvalidOperationException($"missing resource {name}");
        using var ms = new MemoryStream();
        s.CopyTo(ms);
        var b = ms.ToArray();
        return b.Length >= 3 && b[0] == 0xEF && b[1] == 0xBB && b[2] == 0xBF ? b[3..] : b;
    }

    /// <summary>
    /// Signatures go through NSec, which needs libsodium.dll. The setup is downloaded as a single
    /// file, so the library travels inside it and is loaded before the first signature check;
    /// a module already loaded under that name is what the P/Invoke then binds to.
    /// </summary>
    static void LoadSodium(Action<string> log)
    {
        var beside = Path.Combine(AppContext.BaseDirectory, "libsodium.dll");
        if (File.Exists(beside)) { NativeLibrary.Load(beside); return; }
        var dir = Path.Combine(Path.GetTempPath(), "xp-setup-" + Environment.ProcessId);
        Directory.CreateDirectory(dir);
        var path = Path.Combine(dir, "libsodium.dll");
        File.WriteAllBytes(path, Resource("libsodium.dll"));
        NativeLibrary.Load(path);
        log("install: libsodium from " + path);
    }

    static void MakeShortcuts(string exe, Action<string> log)
    {
        foreach (var folder in new[] { Environment.SpecialFolder.DesktopDirectory, Environment.SpecialFolder.Programs })
        {
            var lnk = Path.Combine(Environment.GetFolderPath(folder), ProductName + ".lnk");
            try { Shortcut(lnk, exe); log("install: shortcut " + lnk); }
            catch (Exception e) { log($"install: shortcut {lnk} failed: {e.GetType().Name} 0x{e.HResult:X8}"); }   // not worth failing the install
        }
    }

    static void Shortcut(string lnk, string exe)
    {
        var clsid = new Guid("00021401-0000-0000-C000-000000000046");   // CLSID_ShellLink
        var iid = typeof(IShellLinkW).GUID;
        // .NET has already put the main thread into the MTA, and asking for STA fails (0x80010106);
        // the shell link object lives in either apartment
        CoInitializeEx(IntPtr.Zero, 0);
        Marshal.ThrowExceptionForHR(CoCreateInstance(ref clsid, IntPtr.Zero, 1, ref iid, out var ptr));
        try
        {
            var cw = new StrategyBasedComWrappers();
            var obj = cw.GetOrCreateObjectForComInstance(ptr, CreateObjectFlags.None);
            var link = (IShellLinkW)obj;
            link.SetPath(exe);
            link.SetWorkingDirectory(Path.GetDirectoryName(exe)!);
            link.SetIconLocation(exe, 0);
            ((IPersistFile)obj).Save(lnk, true);
        }
        finally { Marshal.Release(ptr); }
    }

    [DllImport("kernel32.dll")] static extern bool AllocConsole();
    [DllImport("kernel32.dll")] static extern ushort GetUserDefaultUILanguage();
    [DllImport("ole32.dll")] static extern int CoInitializeEx(IntPtr reserved, uint coInit);
    [DllImport("ole32.dll")] static extern int CoCreateInstance(ref Guid clsid, IntPtr outer, uint ctx, ref Guid iid, out IntPtr obj);
}

[GeneratedComInterface, Guid("000214F9-0000-0000-C000-000000000046")]
partial interface IShellLinkW
{
    void GetPath(IntPtr file, int cch, IntPtr fd, uint flags);
    void GetIDList(out IntPtr pidl);
    void SetIDList(IntPtr pidl);
    void GetDescription(IntPtr name, int cch);
    void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string name);
    void GetWorkingDirectory(IntPtr dir, int cch);
    void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string dir);
    void GetArguments(IntPtr args, int cch);
    void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string args);
    void GetHotkey(out ushort hotkey);
    void SetHotkey(ushort hotkey);
    void GetShowCmd(out int show);
    void SetShowCmd(int show);
    void GetIconLocation(IntPtr path, int cch, out int icon);
    void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string path, int icon);
    void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string path, uint reserved);
    void Resolve(IntPtr hwnd, uint flags);
    void SetPath([MarshalAs(UnmanagedType.LPWStr)] string file);
}

[GeneratedComInterface, Guid("0000010B-0000-0000-C000-000000000046")]
partial interface IPersistFile
{
    void GetClassID(out Guid clsid);
    [PreserveSig] int IsDirty();
    void Load([MarshalAs(UnmanagedType.LPWStr)] string file, uint mode);
    void Save([MarshalAs(UnmanagedType.LPWStr)] string file, [MarshalAs(UnmanagedType.Bool)] bool remember);
    void SaveCompleted([MarshalAs(UnmanagedType.LPWStr)] string file);
    void GetCurFile(out IntPtr file);
}
