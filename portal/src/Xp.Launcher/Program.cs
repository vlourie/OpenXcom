using Avalonia;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Styling;
using Xp.Launcher.Core;

namespace Xp.Launcher;

public sealed class App : Application
{
    public static string[] Args { get; set; } = [];
    /// <summary>Set in report mode: the form is the only window.</summary>
    public static (Report Report, Settings Settings)? Report { get; set; }

    public override void Initialize()
    {
        RequestedThemeVariant = ThemeVariant.Dark;
        Styles.Add(Skin.Fluent());
        Skin.AddResources(Resources);
        Skin.AddStyles(Styles);
    }

    public override void OnFrameworkInitializationCompleted()
    {
        if (ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop)
            desktop.MainWindow = Report is { } r ? new ReportWindow(r.Report, r.Settings) { Topmost = true } : new MainWindow(Args);
        base.OnFrameworkInitializationCompleted();
    }
}

static class Program
{
    [STAThread]
    static int Main(string[] args)
    {
        // F8 from the game: only the report form, next to a launcher window that may already be open
        if (args.Length >= 2 && args[0] == "--report") return RunReport(args[1]);
        // the game's "My reports" list: ticket statuses into report.json, no window, next to anything else open
        if (args.Length >= 1 && args[0] == "--refresh") return RunRefresh(args.Length >= 2 ? args[1] : null);

        // one launcher per user: two would fight over the same staging directory
        using var mutex = new Mutex(true, @"Local\XPiratezLauncher", out bool first);
        if (!first) return 0;

        if (args.Contains("--updated")) SelfUpdate.ConfirmStarted();
        var settings = Settings.Load();
        L.Use(settings.Language);
        if (args.Length > 0 && args[0] == "--headless") return Headless.Run(args, settings);
        App.Args = args;
        return Build().StartWithClassicDesktopLifetime(args);
    }

    static AppBuilder Build() => AppBuilder.Configure<App>()
        .UsePlatformDetect()
        // no ANGLE: WGL or software is enough for a launcher and saves 5 MB
        .With(new Win32PlatformOptions { RenderingMode = [Win32RenderingMode.Wgl, Win32RenderingMode.Software] });

    /// <summary>
    /// Exit codes for the game: 0 statuses fresh, 1 no portal configured, 3 the portal could not be asked
    /// (the list then shows what was known before, with its "checked at").
    /// </summary>
    static int RunRefresh(string? root)
    {
        var settings = Settings.Load();
        var roots = new List<string>();
        if (!string.IsNullOrEmpty(root)) roots.Add(root);
        roots.AddRange(settings.ReportRoots);
        var portalUrl = settings.PortalUrl ?? BuiltIn.Defaults.PortalUrl;
        if (string.IsNullOrWhiteSpace(portalUrl) || !Uri.TryCreate(portalUrl, UriKind.Absolute, out var baseUri)) return 1;

        using var mutex = new Mutex(true, @"Local\XPiratezLauncher.refresh", out bool first);
        if (!first) return 0;
        try
        {
            ReportFlow.RefreshAsync(roots, baseUri, CancellationToken.None).GetAwaiter().GetResult();
            return 0;
        }
        catch (Exception e) when (e is HttpRequestException or OperationCanceledException or PortalException or IOException or UnauthorizedAccessException or System.Text.Json.JsonException)
        {
            return 3;
        }
    }

    /// <summary>
    /// The game waits (paused) until this process exits, so every path out of here must end it:
    /// a bad folder, a second F8 on the same report, a closed window.
    /// </summary>
    static int RunReport(string dir)
    {
        var settings = Settings.Load();
        Report report;
        try { report = Report.Open(dir); }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or InvalidDataException or ArgumentException) { return 2; }
        // no language chosen in the launcher yet: speak the game's
        L.Use(settings.Language ?? (report.Context?.Language.StartsWith("ru", StringComparison.OrdinalIgnoreCase) == true ? "ru" : "en"));

        using var mutex = new Mutex(true, @"Local\XPiratezLauncher.report." + report.Draft.Id, out bool first);
        if (!first) return 0;

        // remember where the game keeps its reports, so the launcher's list finds them later
        var root = Path.GetDirectoryName(report.Dir.TrimEnd('/', '\\'));
        if (root is not null && !settings.ReportRoots.Contains(root, StringComparer.OrdinalIgnoreCase))
        {
            settings.ReportRoots.Add(root);
            try { settings.Save(); } catch (IOException) { }
        }
        App.Report = (report, settings);
        return Build().StartWithClassicDesktopLifetime([]);
    }
}
