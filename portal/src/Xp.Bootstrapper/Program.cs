using System.Diagnostics;
using Xp.Manifest;

// xp-bootstrap — replaces the launcher's files after the launcher has exited.
// The files were already verified (signature + SHA-256) by the launcher; this program only
// swaps them, starts the new launcher and puts the old one back if the new one does not confirm.
// Started with no arguments it is the setup a new player downloads from the site: Installer.cs.

namespace Xp.Bootstrapper;

static class Program
{
    static readonly TimeSpan ExitWait = TimeSpan.FromSeconds(60);
    static readonly TimeSpan ConfirmWait = TimeSpan.FromSeconds(30);
    static StreamWriter? _log;

    static int Main(string[] args)
    {
        var logDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "XPiratezLauncher");
        Directory.CreateDirectory(logDir);
        using (_log = new StreamWriter(Path.Combine(logDir, "bootstrap.log"), append: true) { AutoFlush = true })
        {
            // no arguments: a player ran the file the site gave them (XPiratezHD-Setup-<v>.exe)
            if (args.Length == 0) return Installer.Run(Log);
            try { return Run(Parse(args)); }
            catch (Exception e)
            {
                Log("FATAL " + e.Message);
                return 1;
            }
        }
    }

    sealed record Job(int Pid, string Source, string Target, string Exe, List<string> Files);

    static Job Parse(string[] args)
    {
        int pid = 0; string? source = null, target = null, exe = null;
        var files = new List<string>();
        for (int i = 0; i + 1 < args.Length; i += 2)
        {
            switch (args[i])
            {
                case "--pid": pid = int.Parse(args[i + 1]); break;
                case "--source": source = args[i + 1]; break;
                case "--target": target = args[i + 1]; break;
                case "--exe": exe = args[i + 1]; break;
                case "--file": files.Add(args[i + 1]); break;
                default: throw new ArgumentException("unknown argument " + args[i]);
            }
        }
        if (source is null || target is null || exe is null || files.Count == 0) throw new ArgumentException("incomplete arguments");
        foreach (var f in files.Append(exe))
            if (SafePath.Validate(f) is { } why) throw new UnsafePathException(f, why);
        if (!files.Contains(exe, StringComparer.OrdinalIgnoreCase)) throw new ArgumentException("the launcher exe is not among the files");
        return new Job(pid, Path.GetFullPath(source), Path.GetFullPath(target), exe, files);
    }

    static int Run(Job job)
    {
        Log($"update: {job.Files.Count} files into {job.Target}");
        if (!WaitForExit(job.Pid)) { Log("launcher did not exit, nothing changed"); return 2; }

        var backup = Path.Combine(job.Target, ".old-" + DateTime.UtcNow.ToString("yyyyMMddHHmmss"));
        var replaced = new List<string>();
        try
        {
            foreach (var f in job.Files)
            {
                var src = SafePath.Resolve(job.Source, f);
                var dst = SafePath.Resolve(job.Target, f);
                if (!File.Exists(src)) throw new FileNotFoundException("prepared file missing", f);
                if (File.Exists(dst)) Move(dst, SafePath.Resolve(backup, f));
                replaced.Add(f);
                Directory.CreateDirectory(Path.GetDirectoryName(dst)!);
                File.Copy(src, dst + ".xp-new", overwrite: true);
                File.Move(dst + ".xp-new", dst, overwrite: true);
            }
        }
        catch (Exception e)
        {
            Log("swap failed: " + e.Message + " - restoring");
            Restore(job, backup, replaced);
            Start(job, updated: false);
            return 3;
        }

        var marker = Path.Combine(job.Target, ".update-ok");
        if (File.Exists(marker)) File.Delete(marker);
        var started = Start(job, updated: true);
        var sw = Stopwatch.StartNew();
        while (sw.Elapsed < ConfirmWait && !File.Exists(marker))
        {
            if (started is { HasExited: true } && started.ExitCode != 0) break;
            Thread.Sleep(250);
        }
        if (!File.Exists(marker))
        {
            Log("new launcher did not confirm start - rolling back");
            try { if (started is { HasExited: false }) { started.Kill(); started.WaitForExit(5000); } }
            catch (InvalidOperationException) { }
            Restore(job, backup, replaced);
            Start(job, updated: false);
            return 4;
        }

        File.Delete(marker);
        TryDelete(backup);
        TryDelete(job.Source);
        Log("update done");
        return 0;
    }

    static bool WaitForExit(int pid)
    {
        if (pid <= 0) return true;
        try
        {
            using var p = Process.GetProcessById(pid);
            return p.WaitForExit(ExitWait);
        }
        catch (ArgumentException) { return true; }   // already gone
    }

    static void Restore(Job job, string backup, List<string> replaced)
    {
        foreach (var f in Enumerable.Reverse(replaced))
        {
            var dst = SafePath.Resolve(job.Target, f);
            var old = SafePath.Resolve(backup, f);
            try
            {
                if (File.Exists(old)) Move(old, dst);
                else if (File.Exists(dst)) File.Delete(dst);   // was new in this update
            }
            catch (IOException e) { Log($"restore {f}: {e.Message}"); }
        }
        TryDelete(backup);
    }

    static Process? Start(Job job, bool updated)
    {
        var exe = SafePath.Resolve(job.Target, job.Exe);
        var psi = new ProcessStartInfo(exe) { WorkingDirectory = job.Target, UseShellExecute = true };
        if (updated) psi.ArgumentList.Add("--updated");
        try { return Process.Start(psi); }
        catch (Exception e) when (e is System.ComponentModel.Win32Exception or IOException)
        {
            Log("cannot start launcher: " + e.Message);
            return null;
        }
    }

    static void Move(string from, string to)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(to)!);
        File.Move(from, to, overwrite: true);
    }

    static void TryDelete(string dir)
    {
        try { if (Directory.Exists(dir)) Directory.Delete(dir, recursive: true); }
        catch (IOException) { }
        catch (UnauthorizedAccessException) { }
    }

    static void Log(string s) => _log?.WriteLine($"{DateTime.Now:yyyy-MM-dd HH:mm:ss} {s}");
}
