using Avalonia;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Themes.Fluent;

namespace Xp.Launcher;

public sealed class App : Application
{
    public static string[] Args { get; set; } = [];

    public override void Initialize() => Styles.Add(new FluentTheme());

    public override void OnFrameworkInitializationCompleted()
    {
        if (ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop)
            desktop.MainWindow = new MainWindow(Args);
        base.OnFrameworkInitializationCompleted();
    }
}

static class Program
{
    [STAThread]
    static int Main(string[] args)
    {
        // one launcher per user: two would fight over the same staging directory
        using var mutex = new Mutex(true, @"Local\XPiratezLauncher", out bool first);
        if (!first) return 0;

        if (args.Contains("--updated")) SelfUpdate.ConfirmStarted();
        var settings = Settings.Load();
        L.Use(settings.Language);
        if (args.Length > 0 && args[0] == "--headless") return Headless.Run(args, settings);
        App.Args = args;
        return AppBuilder.Configure<App>()
            .UsePlatformDetect()
            // no ANGLE: WGL or software is enough for a launcher and saves 5 MB
            .With(new Win32PlatformOptions { RenderingMode = [Win32RenderingMode.Wgl, Win32RenderingMode.Software] })
            .StartWithClassicDesktopLifetime(args);
    }
}
