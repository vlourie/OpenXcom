using Microsoft.AspNetCore.Identity;
using Microsoft.EntityFrameworkCore;
using Xp.Portal.Auth;
using Xp.Portal.Data;
using Xp.Portal.Site;

namespace Xp.Portal;

/// <summary>
/// Xp.Portal migrate                                   apply database migrations, create the roles
/// Xp.Portal admin create --email E [--name N]         first SuperAdmin; password from XP_ADMIN_PASSWORD or stdin
/// Xp.Portal admin reset-2fa --email E                 lost authenticator: turn the second factor off
/// Xp.Portal seed --file F                             mods and forum boards from a catalogue file
/// Xp.Portal wiki import --file F                      wiki pages built from a mod's rulesets
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
                ["wiki", "import", .. var rest] => await WikiImportAsync(sp, Opt(rest, "--file")),
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
            + " | seed --file F | wiki import --file F");
        return 2;
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
