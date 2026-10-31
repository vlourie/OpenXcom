using System.Text;

namespace Xp.Launcher.Core;

/// <summary>
/// The launcher's word to a running game: a newer release is out. One line, the release, in
/// launcher/update.txt of the game folder; the game looks at the file now and then and shows a small plate
/// "a new update is available" in the top left corner while it is there (option oxceHdUpdateNotice,
/// src/Engine/HdUpdateNotice.h). The file is the launcher's own, in its state folder: the game only reads it,
/// so writing it under a running game touches nothing the game writes (R-179).
/// </summary>
public static class UpdateNotice
{
    public static string PathIn(GamePaths p) => Path.Combine(p.StateDir, "update.txt");

    /// <summary>A newer release than the installed one: the game is told which. The same release again writes nothing.</summary>
    public static void Raise(GamePaths p, string release)
    {
        release = release.Trim();
        if (release.Length == 0) return;
        var path = PathIn(p);
        try
        {
            if (File.Exists(path) && File.ReadAllText(path, Encoding.UTF8).Trim() == release) return;
            FileUtil.WriteAtomic(path, Encoding.UTF8.GetBytes(release + "\n"));
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { }
    }

    /// <summary>Nothing newer (the check found the game up to date, or the update was just installed).</summary>
    public static void Clear(GamePaths p)
    {
        try { File.Delete(PathIn(p)); }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { }
    }

    /// <summary>The release the game is told about, or null.</summary>
    public static string? Read(GamePaths p)
    {
        try { return File.Exists(PathIn(p)) ? File.ReadAllText(PathIn(p), Encoding.UTF8).Trim() : null; }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { return null; }
    }
}
