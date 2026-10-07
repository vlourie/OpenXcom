using Xp.Manifest;
using Xp.ReleaseBuilder;

// xp-release — prepares, signs and publishes releases into a static release repository.
// The private key comes from --key <file> or the XP_RELEASE_KEY environment variable (base64 seed);
// it is never written into the repository and never printed.

const string Usage = """
xp-release <command> [options]

  keygen   --out <dir>                      new Ed25519 key pair: release.key (secret) + release.pub
  build    --repo <dir> --id <id> --version <v> [--channel stable]
           [--stage <dir>] [--add <dest>=<src>]... [--launch openxcom_hd.exe]
           [--min-launcher 1.0.0] [--mandatory] [--changelog-ru <file>] [--changelog-en <file>]
           [--line oxce-hd] [--engine-name OXCE-HD]... [--map <prefix>=<component>]...
           [--component engine=<version>]... [--keep-hd18-copies]
           [--root <root>]... [--launcher-kind] --key <file>
                                             hash, store blobs, write a signed manifest (draft);
                                             files are split into components by docs/portal/EDITIONS.md
  catalog  --repo <dir> --in <catalog.json> --key <file>
                                             check presets against the channels, sign catalog.json
  publish  --repo <dir> --channel <ch> --id <id> --key <file>
  revoke   --repo <dir> --channel <ch> --id <id> --key <file>
  verify   --repo <dir> --channel <ch> --pub <file> [--deep]
  list     --repo <dir>
  serve    --repo <dir> [--port 8787]          development server on localhost, with Range support
""";

try
{
    if (args.Length == 0 || args[0] is "-h" or "--help") { Console.WriteLine(Usage); return 0; }
    var cmd = args[0];
    var opt = Options.Parse(args.AsSpan(1));
    var repo = cmd == "keygen" ? null : new ReleaseRepo(opt.Required("repo"), Console.WriteLine);

    switch (cmd)
    {
        case "keygen":
        {
            var dir = opt.Required("out");
            Directory.CreateDirectory(dir);
            var keyPath = Path.Combine(dir, "release.key");
            if (File.Exists(keyPath)) throw new InvalidOperationException($"{keyPath} already exists, refusing to overwrite");
            var (seed, pub) = Signing.CreateKeyPair();
            File.WriteAllText(keyPath, Convert.ToBase64String(seed));
            File.WriteAllText(Path.Combine(dir, "release.pub"), Convert.ToBase64String(pub));
            Console.WriteLine($"key id {Signing.KeyId(pub)}");
            Console.WriteLine($"public key -> {Path.Combine(dir, "release.pub")}");
            Console.WriteLine("release.key is SECRET: keep it off the repository and off any shared disk.");
            return 0;
        }
        case "build":
        {
            var o = new BuildOptions
            {
                StageDir = opt.Get("stage"),
                Id = opt.Required("id"),
                Version = opt.Required("version"),
                Channel = opt.Get("channel") ?? "stable",
                Launch = opt.Get("launch") ?? "",
                MinLauncher = opt.Get("min-launcher") ?? "0.0.0",
                Mandatory = opt.Flag("mandatory"),
                LauncherKind = opt.Flag("launcher-kind"),
                Line = opt.Get("line") ?? "",
                KeepHd18Copies = opt.Flag("keep-hd18-copies"),
            };
            o.Engines.AddRange(opt.All("engine-name"));
            foreach (var m in opt.All("map")) { var (prefix, id) = Options.Pair(m); o.Maps[prefix.Replace('\\', '/')] = id; }
            foreach (var a in opt.All("add")) { var (d, s) = Options.Pair(a); o.Adds[d] = s; }
            foreach (var c in opt.All("component")) { var (n, v) = Options.Pair(c); o.Components[n] = v; }
            var roots = opt.All("root").ToList();
            if (roots.Count > 0) o.Roots = roots;
            foreach (var lang in new[] { "ru", "en" })
                if (opt.Get("changelog-" + lang) is { } f) o.Changelog[lang] = File.ReadAllText(f);
            repo!.Build(o, LoadKey(opt));
            return 0;
        }
        case "catalog":
        {
            var input = ManifestValidator.ParseCatalog(File.ReadAllBytes(opt.Required("in")));
            repo!.PublishCatalog(input, LoadKey(opt));
            return 0;
        }
        case "publish":
            repo!.Publish(opt.Required("channel"), opt.Required("id"), LoadKey(opt));
            return 0;
        case "revoke":
            if (repo!.Revoke(opt.Required("channel"), opt.Required("id"), LoadKey(opt)) is null)
                Console.WriteLine("revoked; the channel did not point at it, pointer unchanged");
            return 0;
        case "verify":
        {
            var keys = new TrustedKeys(File.ReadAllLines(opt.Required("pub")).Where(l => l.Trim().Length > 0));
            var problems = repo!.Verify(opt.Required("channel"), keys, opt.Flag("deep"));
            foreach (var p in problems) Console.WriteLine("PROBLEM: " + p);
            Console.WriteLine(problems.Count == 0 ? "OK" : $"{problems.Count} problem(s)");
            return problems.Count == 0 ? 0 : 1;
        }
        case "list":
            foreach (var r in repo!.List())
                Console.WriteLine($"{r.Id,-28} {r.Channel,-10} {r.Status,-10} {r.Files,7} files {r.Bytes / (1024.0 * 1024),9:F1} MiB  {r.Created.ToLocalTime():yyyy-MM-dd HH:mm}");
            return 0;
        case "serve":
        {
            using var cts = new CancellationTokenSource();
            Console.CancelKeyPress += (_, e) => { e.Cancel = true; cts.Cancel(); };
            await DevServer.RunAsync(repo!.Root, int.Parse(opt.Get("port") ?? "8787"), cts.Token);
            return 0;
        }
        default:
            Console.Error.WriteLine($"unknown command '{cmd}'\n\n{Usage}");
            return 2;
    }
}
catch (Exception e) when (e is IOException or InvalidOperationException or ArgumentException or ManifestException or UnauthorizedAccessException or FormatException)
{
    Console.Error.WriteLine("error: " + e.Message);
    return 1;
}

static byte[] LoadKey(Options opt)
{
    var b64 = opt.Get("key") is { } path ? File.ReadAllText(path) : Environment.GetEnvironmentVariable("XP_RELEASE_KEY");
    if (string.IsNullOrWhiteSpace(b64)) throw new ArgumentException("no signing key: pass --key <file> or set XP_RELEASE_KEY");
    var seed = Convert.FromBase64String(b64.Trim());
    if (seed.Length != 32) throw new ArgumentException("signing key must be a 32-byte Ed25519 seed");
    return seed;
}

sealed class Options
{
    readonly List<(string Name, string? Value)> _items = new();

    public static Options Parse(ReadOnlySpan<string> args)
    {
        var o = new Options();
        for (int i = 0; i < args.Length; i++)
        {
            if (!args[i].StartsWith("--")) throw new ArgumentException($"unexpected argument '{args[i]}'");
            var name = args[i][2..];
            string? value = i + 1 < args.Length && !args[i + 1].StartsWith("--") ? args[++i] : null;
            o._items.Add((name, value));
        }
        return o;
    }

    public string? Get(string name) => _items.LastOrDefault(x => x.Name == name).Value;
    public string Required(string name) => Get(name) ?? throw new ArgumentException($"--{name} is required");
    public bool Flag(string name) => _items.Any(x => x.Name == name);
    public IEnumerable<string> All(string name) => _items.Where(x => x.Name == name && x.Value is not null).Select(x => x.Value!);

    public static (string, string) Pair(string s)
    {
        int eq = s.IndexOf('=');
        if (eq <= 0) throw new ArgumentException($"expected name=value, got '{s}'");
        return (s[..eq], s[(eq + 1)..]);
    }
}
