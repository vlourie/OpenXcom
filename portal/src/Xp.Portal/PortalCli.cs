using Microsoft.AspNetCore.Identity;
using Microsoft.EntityFrameworkCore;
using Xp.Portal.Auth;
using Xp.Portal.Data;
using Xp.Portal.Review;
using Xp.Portal.Site;
using Xp.Portal.Voice;

namespace Xp.Portal;

/// <summary>
/// Xp.Portal migrate                                   apply database migrations, create the roles
/// Xp.Portal admin create --email E [--name N]         first SuperAdmin; password from XP_ADMIN_PASSWORD or stdin
/// Xp.Portal admin reset-2fa --email E                 lost authenticator: turn the second factor off
/// Xp.Portal seed --file F                             mods and forum boards from a catalogue file
/// Xp.Portal packs --file F                            the sets of the game to review, from the census
/// Xp.Portal wiki import --file F                      wiki pages built from a mod's rulesets
/// Xp.Portal mail test --to E                          one letter through the configured SMTP; fails loudly
/// Xp.Portal voice check                               the media server answers with these keys
/// A SuperAdmin is never created from the web: whoever runs these already controls the server.
/// </summary>
public static class PortalCli
{
    public static async Task<int> RunAsync(string[] args)
    {
        var builder = WebApplication.CreateBuilder(new WebApplicationOptions { Args = [] });
        builder.Configuration.AddCommandLine([]);
        builder.Configuration["Workers:Enabled"] = "false";
        PortalApp.AddServices(builder);
        await using var app = builder.Build();
        using var scope = app.Services.CreateScope();
        var sp = scope.ServiceProvider;
        try
        {
            return args switch
            {
                ["migrate"] => await MigrateAsync(sp),
                ["admin", "create", .. var rest] => await CreateAdminAsync(sp, Opt(rest, "--email"), Opt(rest, "--name")),
                ["admin", "reset-2fa", .. var rest] => await Reset2faAsync(sp, Opt(rest, "--email")),
                ["seed", .. var rest] => await SeedAsync(sp, Opt(rest, "--file")),
                ["packs", .. var rest] => await PacksAsync(sp, Opt(rest, "--file")),
                ["wiki", "import", .. var rest] => await WikiImportAsync(sp, Opt(rest, "--file")),
                ["mail", "test", .. var rest] => await MailTestAsync(sp, Opt(rest, "--to")),
                ["voice", "check"] => await VoiceCheckAsync(sp),
                _ => Usage(),
            };
        }
        catch (ArgumentException e)
        {
            Console.Error.WriteLine(e.Message);
            return 2;
        }
    }

    static int Usage()
    {
        Console.Error.WriteLine("usage: Xp.Portal migrate | admin create --email E [--name N] | admin reset-2fa --email E"
            + " | seed --file F | packs --file F | wiki import --file F | mail test --to E | voice check");
        return 2;
    }

    /// <summary>
    /// One harmless call to the media server with the site's own keys: a wrong secret, a wrong
    /// address and a closed port each show here instead of as a launcher that cannot join a room.
    /// </summary>
    static async Task<int> VoiceCheckAsync(IServiceProvider sp)
    {
        var o = sp.GetRequiredService<Microsoft.Extensions.Options.IOptions<LiveKitOptions>>().Value;
        var secret = o.ApiSecret.Length == 0 ? "EMPTY" : o.ApiSecret.Length < 32 ? "TOO SHORT (LiveKit wants 32 characters or more)" : "set";
        Console.WriteLine($"signalling '{o.Url}', API '{o.ApiUrl}', key '{o.ApiKey}', secret {secret}");
        if (!o.Enabled) throw new ArgumentException("LiveKit__Url, LiveKit__ApiUrl, LiveKit__ApiKey and LiveKit__ApiSecret are all needed");
        if (!o.Url.StartsWith("wss://", StringComparison.Ordinal))
            Console.WriteLine("warning: the launcher gets a signalling address that is not wss:// - fine for a test, not for players");
        try
        {
            var rooms = await sp.GetRequiredService<IVoiceServer>().RoomsAsync(CancellationToken.None);
            Console.WriteLine($"the media server answers: {rooms.Count} room(s) open");
            return 0;
        }
        catch (VoiceServerException e)
        {
            Console.Error.WriteLine("FAILED: " + e.Message);
            return 1;
        }
    }

    /// <summary>
    /// The site swallows mail failures so a page never breaks on them; this is where they show.
    /// Prints the setup it used, never the password.
    /// </summary>
    static async Task<int> MailTestAsync(IServiceProvider sp, string? to)
    {
        if (string.IsNullOrWhiteSpace(to) || !to.Contains('@')) throw new ArgumentException("--to ADDRESS is required");
        var o = sp.GetRequiredService<Microsoft.Extensions.Options.IOptions<EmailOptions>>().Value;
        Console.WriteLine(string.IsNullOrWhiteSpace(o.SmtpHost)
            ? $"no SMTP host: the letter goes to {Path.GetFullPath(o.PickupDir)} as an .eml file"
            : $"SMTP {o.SmtpHost}:{o.SmtpPort} STARTTLS, user '{o.SmtpUser}', password {(o.SmtpPassword.Length > 0 ? "set" : "EMPTY")}, from {o.From}");
        if (o.SmtpPort == 465) throw new ArgumentException("port 465 is implicit TLS, which the site cannot speak: use 587");
        var mail = (EmailSender)sp.GetRequiredService<IEmailSender<PortalUser>>();
        try { await mail.SendTestAsync(to.Trim()); }
        catch (Exception e)
        {
            Console.Error.WriteLine($"FAILED: {e.GetType().Name}: {e.Message}" + (e.InnerException is { } i ? $" ({i.Message})" : ""));
            return 1;
        }
        Console.WriteLine($"sent to {to.Trim()}: check the inbox and the spam folder");
        return 0;
    }

    static string? Opt(string[] a, string name)
    {
        var i = Array.IndexOf(a, name);
        return i >= 0 && i + 1 < a.Length ? a[i + 1] : null;
    }

    public static async Task<int> MigrateAsync(IServiceProvider sp)
    {
        await sp.GetRequiredService<PortalDb>().Database.MigrateAsync();
        await EnsureRolesAsync(sp);
        Console.WriteLine("database is up to date");
        return 0;
    }

    public static async Task EnsureRolesAsync(IServiceProvider sp)
    {
        var roles = sp.GetRequiredService<RoleManager<IdentityRole<Guid>>>();
        foreach (var r in Roles.All)
            if (!await roles.RoleExistsAsync(r)) await roles.CreateAsync(new IdentityRole<Guid>(r));
    }

    static async Task<int> CreateAdminAsync(IServiceProvider sp, string? email, string? name)
    {
        if (string.IsNullOrWhiteSpace(email)) throw new ArgumentException("--email is required");
        var password = Environment.GetEnvironmentVariable("XP_ADMIN_PASSWORD");
        if (string.IsNullOrEmpty(password))
        {
            Console.Error.Write("password: ");
            password = ReadSecret();
        }
        if (string.IsNullOrEmpty(password)) throw new ArgumentException("no password given");
        await EnsureRolesAsync(sp);
        var users = sp.GetRequiredService<UserManager<PortalUser>>();
        if (await users.FindByEmailAsync(email) is not null) throw new ArgumentException($"{email} already exists");
        var u = new PortalUser { UserName = email, Email = email, EmailConfirmed = true, DisplayName = name ?? email.Split('@')[0] };
        var r = await users.CreateAsync(u, password);
        if (!r.Succeeded) throw new ArgumentException(string.Join("; ", r.Errors.Select(e => e.Description)));
        await users.AddToRoleAsync(u, Roles.SuperAdmin);
        var audit = sp.GetRequiredService<Audit>();
        audit.Add(null, "superadmin.create.cli", email);
        await sp.GetRequiredService<PortalDb>().SaveChangesAsync();
        Console.WriteLine($"SuperAdmin {email} created. Sign in and set up the authenticator: staff pages open only with it.");
        return 0;
    }

    /// <summary>Reads a line without echoing it when typed at a terminal; piped input is read as is.</summary>
    static string? ReadSecret()
    {
        if (Console.IsInputRedirected) return Console.ReadLine();
        var sb = new System.Text.StringBuilder();
        while (true)
        {
            var k = Console.ReadKey(intercept: true);
            if (k.Key == ConsoleKey.Enter) break;
            if (k.Key == ConsoleKey.Backspace) { if (sb.Length > 0) sb.Length--; }
            else if (!char.IsControl(k.KeyChar)) sb.Append(k.KeyChar);
        }
        Console.Error.WriteLine();
        return sb.ToString();
    }

    static async Task<int> SeedAsync(IServiceProvider sp, string? path)
    {
        if (string.IsNullOrWhiteSpace(path)) throw new ArgumentException("--file is required");
        if (!File.Exists(path)) throw new ArgumentException($"no file {path}");
        var file = CommunitySeed.Read(path);
        var r = await sp.GetRequiredService<CommunitySeed>().ApplyAsync(file, CancellationToken.None);
        Console.WriteLine($"mods: {r.ModsAdded} added, {r.ModsUpdated} updated; boards: {r.SectionsAdded} added, {r.SectionsUpdated} updated");
        return 0;
    }

    static async Task<int> PacksAsync(IServiceProvider sp, string? path)
    {
        if (string.IsNullOrWhiteSpace(path)) throw new ArgumentException("--file is required");
        if (!File.Exists(path)) throw new ArgumentException($"no file {path}");
        var file = PackSeed.Read(path);
        var r = await sp.GetRequiredService<PackSeed>().ApplyAsync(file, CancellationToken.None);
        Console.WriteLine($"packs: {r.Added} added, {r.Updated} updated");
        return 0;
    }

    static async Task<int> WikiImportAsync(IServiceProvider sp, string? path)
    {
        if (string.IsNullOrWhiteSpace(path)) throw new ArgumentException("--file is required");
        if (!File.Exists(path)) throw new ArgumentException($"no file {path}");
        var file = WikiImport.Read(path);
        Console.WriteLine($"{file.Mod} {file.Version}: {file.Pages.Count} pages built {file.Generated}");
        var started = DateTimeOffset.UtcNow;
        var r = await sp.GetRequiredService<WikiImport>().ApplyAsync(file, CancellationToken.None);
        Console.WriteLine($"written {r.Written}, removed {r.Removed}, left alone as hand-written {r.KeptByHand}, "
            + $"skipped {r.Skipped}, in {(DateTimeOffset.UtcNow - started).TotalSeconds:0.0} s");
        return 0;
    }

    static async Task<int> Reset2faAsync(IServiceProvider sp, string? email)
    {
        var users = sp.GetRequiredService<UserManager<PortalUser>>();
        var u = await users.FindByEmailAsync(email ?? "") ?? throw new ArgumentException($"no user {email}");
        await users.SetTwoFactorEnabledAsync(u, false);
        await users.ResetAuthenticatorKeyAsync(u);
        await users.UpdateSecurityStampAsync(u);   // signs the user out everywhere
        sp.GetRequiredService<Audit>().Add(null, "2fa.reset.cli", email!);
        await sp.GetRequiredService<PortalDb>().SaveChangesAsync();
        Console.WriteLine($"second factor of {email} is off; they must set it up again");
        return 0;
    }
}
