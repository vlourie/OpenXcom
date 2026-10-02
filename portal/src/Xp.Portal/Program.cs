using System.Globalization;
using System.Net;
using System.Security.Claims;
using System.Threading.RateLimiting;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.HttpOverrides;
using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.Localization;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;
using Xp.Portal;
using Xp.Portal.Auth;
using Xp.Portal.Data;
using Xp.Portal.Devices;
using Xp.Portal.Files;
using Xp.Portal.Notifications;
using Xp.Portal.Review;
using Xp.Portal.Site;
using Xp.Portal.Tickets;
using Xp.Portal.Voice;

// a word the command line knows means the command line, not the web server: an unknown word starting
// the site by mistake is how a typo in a deployment script turns into a container that never exits
if (args.Length > 0 && args[0] is "admin" or "migrate" or "seed" or "packs" or "wiki" or "mail" or "voice")
    return await PortalCli.RunAsync(args);

var app = PortalApp.Build(args);
await app.RunAsync();
return 0;

public static class PortalApp
{
    public static WebApplication Build(string[] args, Action<WebApplicationBuilder>? configure = null)
    {
        var builder = WebApplication.CreateBuilder(args);
        configure?.Invoke(builder);
        AddServices(builder);
        var app = builder.Build();
        Use(app);
        return app;
    }

    public static void AddServices(WebApplicationBuilder builder)
    {
        var s = builder.Services;
        var cfg = builder.Configuration;
        s.Configure<PortalOptions>(cfg.GetSection(PortalOptions.Section));
        s.Configure<AttachmentOptions>(cfg.GetSection(AttachmentOptions.Section));
        s.Configure<TelegramOptions>(cfg.GetSection(TelegramOptions.Section));
        s.Configure<UpstreamOptions>(cfg.GetSection(UpstreamOptions.Section));
        s.Configure<EmailOptions>(cfg.GetSection(EmailOptions.Section));
        s.Configure<Argon2Options>(cfg.GetSection("Argon2"));
        s.Configure<LiveKitOptions>(cfg.GetSection(LiveKitOptions.Section));
        s.AddSingleton(TimeProvider.System);

        s.AddDbContext<PortalDb>(o => o.UseNpgsql(cfg.GetConnectionString("Portal")
            ?? throw new InvalidOperationException("ConnectionStrings:Portal is not set")));

        s.AddIdentity<PortalUser, IdentityRole<Guid>>(o =>
            {
                o.Password.RequiredLength = 10;
                o.Password.RequireNonAlphanumeric = false;
                o.Password.RequireUppercase = false;
                o.Lockout.MaxFailedAccessAttempts = 5;
                o.Lockout.DefaultLockoutTimeSpan = TimeSpan.FromMinutes(15);
                o.User.RequireUniqueEmail = true;
                o.SignIn.RequireConfirmedEmail = true;
            })
            .AddEntityFrameworkStores<PortalDb>()
            .AddDefaultTokenProviders()
            .AddClaimsPrincipalFactory<PortalClaimsFactory>();
        s.AddScoped<IPasswordHasher<PortalUser>, Argon2PasswordHasher>();
        // role and permission changes reach existing sessions within a minute, not at the next login
        s.Configure<SecurityStampValidatorOptions>(o =>
        {
            o.ValidationInterval = TimeSpan.FromMinutes(1);
            // the refreshed principal is built from the database and forgets how the user signed in:
            // carry the second-factor mark over, or staff would lose their pages a minute after signing in
            o.OnRefreshingPrincipal = c =>
            {
                if (c.CurrentPrincipal?.HasClaim("amr", "mfa") == true && c.NewPrincipal?.Identity is ClaimsIdentity id && !id.HasClaim("amr", "mfa"))
                    id.AddClaim(new Claim("amr", "mfa"));
                return Task.CompletedTask;
            };
        });

        s.ConfigureApplicationCookie(o =>
        {
            o.Cookie.Name = "xp.auth";
            o.Cookie.HttpOnly = true;
            o.Cookie.SameSite = SameSiteMode.Lax;
            o.Cookie.SecurePolicy = builder.Environment.IsDevelopment() ? CookieSecurePolicy.SameAsRequest : CookieSecurePolicy.Always;
            o.LoginPath = "/account/login";
            o.LogoutPath = "/account/logout";
            o.AccessDeniedPath = "/account/denied";
            o.ExpireTimeSpan = TimeSpan.FromDays(14);
            o.SlidingExpiration = true;
            // the API never redirects to a login page
            o.Events.OnRedirectToLogin = c => ApiAware(c, 401);
            o.Events.OnRedirectToAccessDenied = c => ApiAware(c, 403);
        });
        s.AddAntiforgery(o =>
        {
            o.Cookie.Name = "xp.af";
            o.Cookie.SecurePolicy = builder.Environment.IsDevelopment() ? CookieSecurePolicy.SameAsRequest : CookieSecurePolicy.Always;
        });

        s.AddAuthorizationBuilder()
            // staff pages need the role AND a sign-in with the second factor (amr=mfa)
            .AddPolicy(Policies.Staff, p => p.RequireRole(Roles.Admin, Roles.SuperAdmin).RequireClaim("amr", "mfa"))
            .AddPolicy(Policies.SuperAdmin, p => p.RequireRole(Roles.SuperAdmin).RequireClaim("amr", "mfa"));

        s.AddRazorPages(o =>
        {
            o.Conventions.AuthorizeFolder("/Admin", Policies.Staff);
            o.Conventions.AuthorizeFolder("/Admin/Super", Policies.SuperAdmin);
            o.Conventions.AuthorizeFolder("/Me");
            o.Conventions.AuthorizeFolder("/Voice");
            // reading the forum and the wiki needs no account; writing does
            o.Conventions.AuthorizePage("/Forum/New");
            o.Conventions.AuthorizePage("/Wiki/Edit");
        });
        // Razor escapes markup either way; without this it also turns every Cyrillic letter into &#x...;
        s.Configure<Microsoft.Extensions.WebEncoders.WebEncoderOptions>(o =>
            o.TextEncoderSettings = new System.Text.Encodings.Web.TextEncoderSettings(System.Text.Unicode.UnicodeRanges.All));
        s.AddProblemDetails(o => o.CustomizeProblemDetails = c => c.ProblemDetails.Extensions["traceId"] = c.HttpContext.TraceIdentifier);
        s.AddOpenApi("v1");
        s.AddMemoryCache();
        s.AddHttpClient("telegram", c => c.Timeout = TimeSpan.FromSeconds(20));
        s.AddHttpClient("releases", c => c.Timeout = TimeSpan.FromSeconds(20));
        // a pass waits on this: a media server that does not answer in seconds is down
        s.AddHttpClient("livekit", c => c.Timeout = TimeSpan.FromSeconds(8));
        // an honest name: ModDB and GitHub serve it as is
        s.AddHttpClient("upstream", c =>
        {
            c.Timeout = TimeSpan.FromSeconds(30);
            c.DefaultRequestHeaders.UserAgent.ParseAdd("XPiratezPortal/1.0 (+https://x-piratez.mywire.org:8443/)");
        });
        s.AddHealthChecks().AddDbContextCheck<PortalDb>("db", tags: ["ready"]);

        s.AddScoped<TicketService>();
        s.AddScoped<TelegramNotices>();
        s.AddScoped<UpstreamCheck>();
        s.AddScoped<AttachmentService>();
        s.AddScoped<Audit>();
        s.AddSingleton<ObjectStore>();
        s.AddSingleton<SignedUrls>();
        s.AddSingleton<ClamdScanner>();
        s.AddSingleton<ReleaseFeed>();
        s.AddSingleton<Text>();
        s.AddSingleton<Art>();
        s.AddSingleton<Markup>();
        s.AddScoped<Roadmap>();
        s.AddScoped<PackSeed>();
        s.AddScoped<CommunityService>();
        s.AddScoped<CommunitySeed>();
        s.AddScoped<WikiImport>();
        s.AddSingleton<IEmailSender<PortalUser>, EmailSender>();
        s.AddSingleton<LiveKitTokens>();
        s.AddSingleton<IVoiceServer, LiveKitServer>();
        s.AddScoped<VoiceService>();
        if (cfg.GetValue("Workers:Enabled", true))
        {
            s.AddHostedService<TelegramWorker>();
            s.AddHostedService<ScanWorker>();
            s.AddHostedService<UpstreamWorker>();
            s.AddHostedService<VoiceWorker>();
        }

        s.Configure<RequestLocalizationOptions>(o =>
        {
            o.SetDefaultCulture("ru");
            o.AddSupportedCultures("ru", "en").AddSupportedUICultures("ru", "en");
            o.RequestCultureProviders = [new QueryStringRequestCultureProvider(), new CookieRequestCultureProvider(), new AcceptLanguageHeaderRequestCultureProvider()];
        });

        // cookies, antiforgery and e-mail links are sealed with these keys: in a container they must
        // outlive the container, or every restart signs everyone out and voids the links in the mail
        if (cfg["DataProtection:KeysDir"] is { Length: > 0 } keysDir)
            s.AddDataProtection().PersistKeysToFileSystem(new DirectoryInfo(keysDir)).SetApplicationName("xp-portal");

        var proxies = cfg.GetSection("Portal:TrustedProxies").Get<string[]>() ?? [];
        var proxyNets = cfg.GetSection("Portal:TrustedNetworks").Get<string[]>() ?? [];
        s.Configure<ForwardedHeadersOptions>(o =>
        {
            o.ForwardedHeaders = ForwardedHeaders.XForwardedFor | ForwardedHeaders.XForwardedProto;
            o.KnownProxies.Clear();
            o.KnownIPNetworks.Clear();
            foreach (var p in proxies) o.KnownProxies.Add(IPAddress.Parse(p));
            // a proxy in a container has no fixed address, only a fixed subnet
            foreach (var n in proxyNets) o.KnownIPNetworks.Add(System.Net.IPNetwork.Parse(n));
        });

        s.AddRateLimiter(o =>
        {
            o.RejectionStatusCode = StatusCodes.Status429TooManyRequests;
            // pages carry their policy on GET too: only the POST that does the work is counted
            o.AddPolicy("tickets-create", c => WritesByIp(c, cfg.GetValue("RateLimits:TicketsPer10Min", 5), TimeSpan.FromMinutes(10)));
            o.AddPolicy("tickets-write", c => WritesByIp(c, cfg.GetValue("RateLimits:WritesPer10Min", 60), TimeSpan.FromMinutes(10)));
            o.AddPolicy("api-read", c => ByIp(c, 120, TimeSpan.FromMinutes(1)));
            // posting on the forum: enough for a conversation, not enough for a flood
            o.AddPolicy("forum-write", c => WritesByIp(c, cfg.GetValue("RateLimits:ForumPer10Min", 20), TimeSpan.FromMinutes(10)));
            o.AddPolicy("login", c => WritesByIp(c, cfg.GetValue("RateLimits:LoginPer5Min", 10), TimeSpan.FromMinutes(5)));
            // linking a launcher: a person does it once, so a low limit also caps guessing at the codes
            o.AddPolicy("devices", c => WritesByIp(c, cfg.GetValue("RateLimits:DevicesPer10Min", 20), TimeSpan.FromMinutes(10)));
            // an evening of reviewing is a few sends, not a few hundred: a set at a time, plus retries
            o.AddPolicy("review-write", c => WritesByIp(c, cfg.GetValue("RateLimits:ReviewPer10Min", 60), TimeSpan.FromMinutes(10)));
            // friends, rooms, invites and an owner's moderation: an evening's worth, not a script's
            o.AddPolicy("voice-write", c => WritesByIp(c, cfg.GetValue("RateLimits:VoicePer10Min", 120), TimeSpan.FromMinutes(10)));
            // a pass per connection and per reconnect; a launcher that loops is stopped here, not at the media server
            o.AddPolicy("voice-pass", c => WritesByIp(c, cfg.GetValue("RateLimits:VoicePassPerMin", 20), TimeSpan.FromMinutes(1)));
        });
    }

    static RateLimitPartition<string> WritesByIp(HttpContext c, int permits, TimeSpan window) =>
        HttpMethods.IsGet(c.Request.Method) || HttpMethods.IsHead(c.Request.Method)
            ? RateLimitPartition.GetNoLimiter("read")
            : ByIp(c, permits, window);

    static RateLimitPartition<string> ByIp(HttpContext c, int permits, TimeSpan window) =>
        RateLimitPartition.GetFixedWindowLimiter(c.Connection.RemoteIpAddress?.ToString() ?? "?",
            _ => new FixedWindowRateLimiterOptions { PermitLimit = permits, Window = window, QueueLimit = 0 });

    static Task ApiAware(Microsoft.AspNetCore.Authentication.RedirectContext<Microsoft.AspNetCore.Authentication.Cookies.CookieAuthenticationOptions> c, int status)
    {
        if (c.Request.Path.StartsWithSegments("/api")) { c.Response.StatusCode = status; return Task.CompletedTask; }
        c.Response.Redirect(c.RedirectUri);
        return Task.CompletedTask;
    }

    public static void Use(WebApplication app)
    {
        CheckConfig(app);
        app.UseForwardedHeaders();
        if (!app.Environment.IsDevelopment())
        {
            app.UseHsts();
            app.UseHttpsRedirection();
        }
        app.UseExceptionHandler();
        app.UseStatusCodePages();
        app.Use(SecurityHeaders);
        app.UseRequestLocalization();
        app.UseStaticFiles();
        app.UseRouting();
        app.UseRateLimiter();
        app.UseAuthentication();
        app.UseAuthorization();
        app.UseAntiforgery();

        app.MapHealthChecks("/health", new() { Predicate = _ => false });
        app.MapHealthChecks("/ready", new() { Predicate = c => c.Tags.Contains("ready") });
        app.MapOpenApi("/openapi/{documentName}.json");
        TicketApi.Map(app);
        DeviceApi.Map(app);
        ReviewApi.Map(app);
        VoiceApi.Map(app);
        app.MapGet("/files/{id:guid}", ServeFileAsync).ExcludeFromDescription();
        // HEAD too: download managers ask the name and size first, and 405 made them give up
        app.MapMethods("/download/launcher", ["GET", "HEAD"], DownloadLauncherAsync).ExcludeFromDescription();
        app.MapGet("/lang/{lang}", (string lang, string? back, HttpContext http) =>
        {
            if (Text.Languages.Contains(lang))
                http.Response.Cookies.Append(CookieRequestCultureProvider.DefaultCookieName,
                    CookieRequestCultureProvider.MakeCookieValue(new RequestCulture(lang)),
                    new CookieOptions { MaxAge = TimeSpan.FromDays(365), HttpOnly = true, SameSite = SameSiteMode.Lax, IsEssential = true });
            // only a local path: no open redirect through ?back=
            return Results.LocalRedirect(back is { Length: > 0 } && back.StartsWith('/') && !back.StartsWith("//") && !back.StartsWith("/\\") ? back : "/");
        }).ExcludeFromDescription();
        app.MapRazorPages();
    }

    static void CheckConfig(WebApplication app)
    {
        var p = app.Services.GetRequiredService<IOptions<PortalOptions>>().Value;
        var secret = p.SecretBytes();   // throws if missing or short
        if (!app.Environment.IsDevelopment() && System.Text.Encoding.ASCII.GetString(secret).StartsWith("DEV-ONLY"))
            throw new InvalidOperationException("Portal:Secret is the development value; set a real one (Portal__Secret)");
        var a = app.Services.GetRequiredService<IOptions<AttachmentOptions>>().Value;
        if (string.IsNullOrWhiteSpace(a.StorageRoot)) throw new InvalidOperationException("Attachments:StorageRoot is not set");
        var root = Path.GetFullPath(a.StorageRoot);
        var web = Path.GetFullPath(app.Environment.WebRootPath ?? Path.Combine(app.Environment.ContentRootPath, "wwwroot"));
        if (root.StartsWith(web, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("Attachments:StorageRoot must be outside wwwroot");
        // voice may be off (no LiveKit:* at all); half a configuration, or a guessable secret, is a mistake
        var v = app.Services.GetRequiredService<IOptions<LiveKitOptions>>().Value;
        string[] set = [v.Url, v.ApiUrl, v.ApiKey, v.ApiSecret];
        if (set.Any(x => x.Length > 0) && !v.Enabled)
            throw new InvalidOperationException("LiveKit: set all of Url, ApiUrl, ApiKey and ApiSecret, or none");
        if (v.Enabled)
        {
            if (v.ApiSecret.Length < 32) throw new InvalidOperationException("LiveKit:ApiSecret is shorter than 32 characters");
            if (!app.Environment.IsDevelopment() && (v.ApiKey.StartsWith("devkey") || v.ApiSecret.Contains("secret", StringComparison.OrdinalIgnoreCase)))
                throw new InvalidOperationException("LiveKit: the development key is set; put the production key in portal.env");
            if (!app.Environment.IsDevelopment() && !v.Url.StartsWith("wss://"))
                throw new InvalidOperationException("LiveKit:Url must be wss:// outside development");
        }
    }

    static async Task SecurityHeaders(HttpContext c, Func<Task> next)
    {
        var h = c.Response.Headers;
        h.XContentTypeOptions = "nosniff";
        h["Referrer-Policy"] = "no-referrer";   // the guest's secret link must never leave in a Referer
        h.XFrameOptions = "DENY";
        h["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()";
        h.ContentSecurityPolicy = "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'";
        await next();
    }

    /// <summary>
    /// The launcher, straight from the release repository the site already reads. One address that
    /// always works and needs nothing set by hand: the blob is named by its own SHA-256 inside the
    /// repository, and its name here carries the version instead, so the player sees what they got.
    /// </summary>
    static async Task<IResult> DownloadLauncherAsync(ReleaseFeed feed, IOptions<PortalOptions> options, IHttpClientFactory http,
        ILogger<ReleaseFeed> log, CancellationToken ct)
    {
        var o = options.Value;
        if (o.LauncherDownloadUrl is { Length: > 0 } elsewhere) return Results.Redirect(elsewhere);
        var launcher = await feed.LauncherAsync(ct);
        if (launcher is null) return Results.NotFound();
        if (launcher.Size > MaxLauncherBytes)
        {
            log.LogError("launcher {Version}: {Size} bytes in the manifest, more than the site hands out ({Max})", launcher.Version, launcher.Size, MaxLauncherBytes);
            return Results.StatusCode(StatusCodes.Status500InternalServerError);
        }
        var client = http.CreateClient("releases");
        var url = new Uri(new Uri(o.ReleaseRepo.EndsWith('/') ? o.ReleaseRepo : o.ReleaseRepo + "/"), Xp.Manifest.BlobKeys.For(launcher.Sha256));
        using var resp = await client.GetAsync(url, HttpCompletionOption.ResponseHeadersRead, ct);
        if (!resp.IsSuccessStatusCode) return Results.NotFound();

        // checked against the signed manifest before the first byte goes out: whoever downloads this has
        // nothing yet to check it with, and a file already sent cannot be taken back. It is small (the
        // setup fetches the launcher itself), so it is read whole rather than streamed
        await using var body = await resp.Content.ReadAsStreamAsync(ct);
        using var ms = new MemoryStream((int)launcher.Size);
        var buf = new byte[81920];
        int n;
        while ((n = await body.ReadAsync(buf, ct)) > 0 && ms.Length <= launcher.Size) ms.Write(buf, 0, n);
        var bytes = ms.ToArray();
        var sha = Xp.Manifest.Hashing.Sha256Hex(bytes);
        if (bytes.Length != launcher.Size || sha != launcher.Sha256)
        {
            log.LogError("launcher {Version}: the repository's file does not match the signed manifest ({Got} bytes, SHA-256 {Sha}; manifest {Size} bytes, {Want}) - not handed out",
                launcher.Version, bytes.Length, sha, launcher.Size, launcher.Sha256);
            return Results.StatusCode(StatusCodes.Status500InternalServerError);
        }
        return Results.File(bytes, "application/octet-stream", launcher.FileName);
    }

    /// <summary>The setup is about 2 MB; this is only a ceiling on what one request may hold in memory.</summary>
    const long MaxLauncherBytes = 64L * 1024 * 1024;

    /// <summary>
    /// An attachment by signed link. The signature limits the link's life; the viewer's rights are
    /// checked again, and a file still pending or quarantined is never handed out.
    /// </summary>
    static async Task<IResult> ServeFileAsync(Guid id, long exp, string? sig, HttpContext http, SignedUrls urls, PortalDb db, ObjectStore store, CancellationToken ct)
    {
        if (!urls.Valid(id, exp, sig)) return Results.NotFound();
        var a = await db.TicketAttachments.FirstOrDefaultAsync(x => x.Id == id, ct);
        if (a is null) return Results.NotFound();
        var t = await db.Tickets.FirstAsync(x => x.Id == a.TicketId, ct);
        var viewer = new Viewer(http.User);
        var staff = viewer.IsStaffFor(t) && http.User.HasClaim("amr", "mfa");
        if (!staff && !viewer.IsOwner(t)) return Results.NotFound();
        if (a.Scan is ScanStatus.Pending or ScanStatus.Quarantined) return Results.NotFound();
        var kind = FileRules.KindOf(a.FileName);
        http.Response.Headers.CacheControl = "private, no-store";
        // images open in the browser, but sandboxed; everything else is a download
        if (kind is { } k && FileRules.IsImage(k))
        {
            http.Response.Headers.ContentSecurityPolicy = "sandbox; default-src 'none'";
            return Results.Stream(store.OpenRead(a.ObjectKey), a.ContentType, enableRangeProcessing: false);
        }
        return Results.Stream(store.OpenRead(a.ObjectKey), "application/octet-stream", a.FileName);
    }
}
