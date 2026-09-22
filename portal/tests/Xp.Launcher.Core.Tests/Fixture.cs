using System.Net;
using System.Text;
using Xp.Launcher.Core;
using Xp.Manifest;
using Xp.ReleaseBuilder;

namespace Xp.Launcher.Core.Tests;

/// <summary>A game directory, a stage directory, a release repository and a fake HTTP server over it.</summary>
public sealed class Fixture : IDisposable
{
    public string Root { get; } = Path.Combine(Path.GetTempPath(), "xp-tests", Guid.NewGuid().ToString("N"));
    public string RepoDir => Path.Combine(Root, "repo");
    public string Stage => Path.Combine(Root, "stage");
    public string Game => Path.Combine(Root, "game");
    public byte[] Key { get; }
    public byte[] PublicKey { get; }
    public ReleaseRepo Repo { get; }
    public RepoHandler Server { get; }
    public TestLog Log { get; } = new();
    public Updater Updater { get; }

    public Fixture()
    {
        Directory.CreateDirectory(Root);
        (Key, PublicKey) = Signing.CreateKeyPair();
        Repo = new ReleaseRepo(RepoDir);
        Server = new RepoHandler(RepoDir);
        var client = new RepoClient(new HttpClient(Server), new Uri("http://repo.test/"), new TrustedKeys([Convert.ToBase64String(PublicKey)]));
        Updater = new Updater(new GamePaths(Game), client, Log) { IsGameRunning = _ => false, FreeSpace = _ => long.MaxValue };

        // the player's installation: engine data, saves, options, somebody else's mod
        Write(Game, "common/Language/en-US.yml", "old strings");
        Write(Game, "OpenXcomEx.exe", "original engine");
        Write(Game, "user/options.cfg", "options: mine");
        Write(Game, "user/piratez/save1.sav", "my precious save");
        Write(Game, "user/mods/Piratez/metadata.yml", "id: Piratez");
    }

    public static void Write(string dir, string rel, string text) => Write(dir, rel, Encoding.UTF8.GetBytes(text));

    public static void Write(string dir, string rel, byte[] data)
    {
        var p = Path.Combine(dir, rel.Replace('/', Path.DirectorySeparatorChar));
        Directory.CreateDirectory(Path.GetDirectoryName(p)!);
        File.WriteAllBytes(p, data);
    }

    public string ReadGame(string rel) => File.ReadAllText(Path.Combine(Game, rel));
    public bool GameHas(string rel) => File.Exists(Path.Combine(Game, rel));

    /// <summary>Stage v1: exe, engine data, the hd mod with a large file (for resume tests).</summary>
    public void StageV1()
    {
        Write(Stage, "openxcom_hd.exe", "engine v1");
        Write(Stage, "common/Language/en-US.yml", "strings v1");
        Write(Stage, "user/mods/hd/metadata.yml", "id: hd");
        Write(Stage, "user/mods/hd/hd/TERRAIN/DESERT.PCK/0.png", "desert 0 v1");
        Write(Stage, "user/mods/hd/hd/TERRAIN/DESERT.PCK/1.png", "desert 0 v1");     // same content: one blob
        Write(Stage, "user/mods/hd/hd/UI/old.png", "to be dropped in v2");
        var big = new byte[300_000];
        new Random(1).NextBytes(big);
        Write(Stage, "user/mods/hd/hd/UI/big.png", big);
    }

    /// <summary>v2: changes one file, drops one, adds one.</summary>
    public void StageV2()
    {
        Write(Stage, "openxcom_hd.exe", "engine v2");
        Write(Stage, "user/mods/hd/hd/TERRAIN/DESERT.PCK/0.png", "desert 0 v2");
        File.Delete(Path.Combine(Stage, "user/mods/hd/hd/UI/old.png"));
        Write(Stage, "user/mods/hd/hd/UI/new.png", "new in v2");
    }

    public void BuildAndPublish(string id, string channel = "stable")
    {
        Repo.Build(new BuildOptions { StageDir = Stage, Id = id, Version = id, Channel = channel, Launch = "openxcom_hd.exe" }, Key);
        Repo.Publish(channel, id, Key);
    }

    /// <summary>The whole happy path, as the UI drives it; returns the plan that was installed.</summary>
    public async Task<UpdatePlan> UpdateAsync(bool full = false, ISet<string>? replace = null)
    {
        var state = Updater.LoadState();
        var latest = await Updater.CheckAsync(state, default);
        var plan = Updater.Scan(state, latest.Manifest, full, null, default);
        if (plan.PlayerModified.Any()) plan = Updater.Resolve(state, plan, replace ?? new HashSet<string>());
        await Updater.DownloadAsync(plan, null, default);
        Updater.Install(state, plan, null);
        return plan;
    }

    /// <summary>Hash of every file of the game directory except the launcher's own state.</summary>
    public Dictionary<string, string> Snapshot() =>
        Directory.EnumerateFiles(Game, "*", SearchOption.AllDirectories)
            .Select(f => SafePath.ToRelative(Game, f))
            .Where(r => !r.StartsWith("launcher/", StringComparison.OrdinalIgnoreCase))
            .ToDictionary(r => r, r => Hashing.FileSha256(Path.Combine(Game, r)));

    public void AssertPlayerDataIntact()
    {
        Assert.Equal("options: mine", ReadGame("user/options.cfg"));
        Assert.Equal("my precious save", ReadGame("user/piratez/save1.sav"));
        Assert.Equal("id: Piratez", ReadGame("user/mods/Piratez/metadata.yml"));
    }

    public void Dispose()
    {
        try { Directory.Delete(Root, recursive: true); } catch (IOException) { } catch (UnauthorizedAccessException) { }
    }
}

public sealed class TestLog : ILauncherLog
{
    public List<string> Lines { get; } = new();
    public void Info(string message) { lock (Lines) Lines.Add(message); }
    public void Error(string message) { lock (Lines) Lines.Add("ERROR " + message); }
}

/// <summary>Serves the repository directory like a static web server, with injectable faults.</summary>
public sealed class RepoHandler(string root) : HttpMessageHandler
{
    public List<(string Key, long? From)> Requests { get; } = new();
    /// <summary>Key -> bytes to serve instead of the file (tampering).</summary>
    public Dictionary<string, byte[]> Overrides { get; } = new();
    /// <summary>First response for each blob breaks off after this many bytes.</summary>
    public int CutBlobsAfter { get; set; } = -1;
    public bool IgnoreRange { get; set; }
    readonly HashSet<string> _cut = new();

    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
    {
        var key = Uri.UnescapeDataString(request.RequestUri!.AbsolutePath.TrimStart('/'));
        long? from = request.Headers.Range?.Ranges.FirstOrDefault()?.From;
        lock (Requests) Requests.Add((key, from));

        byte[]? data;
        lock (Overrides) data = Overrides.TryGetValue(key, out var o) ? o : null;
        var path = Path.Combine(root, key.Replace('/', Path.DirectorySeparatorChar));
        if (data is null && File.Exists(path)) data = File.ReadAllBytes(path);
        if (data is null) return Task.FromResult(new HttpResponseMessage(HttpStatusCode.NotFound));

        var status = HttpStatusCode.OK;
        if (from is > 0 && !IgnoreRange) { data = data[(int)from.Value..]; status = HttpStatusCode.PartialContent; }
        Stream body = new MemoryStream(data);
        bool cut;
        lock (_cut) cut = CutBlobsAfter >= 0 && key.StartsWith("blobs/") && data.Length > CutBlobsAfter && _cut.Add(key);
        if (cut) body = new BreakingStream(data, CutBlobsAfter);
        var resp = new HttpResponseMessage(status) { Content = new StreamContent(body) };
        resp.Content.Headers.ContentLength = data.Length;
        return Task.FromResult(resp);
    }
}

/// <summary>Gives the first N bytes, then fails like a dropped connection.</summary>
sealed class BreakingStream(byte[] data, int cutAfter) : Stream
{
    int _pos;
    public override int Read(byte[] buffer, int offset, int count)
    {
        if (_pos >= cutAfter) throw new IOException("connection reset (test)");
        int n = Math.Min(count, cutAfter - _pos);
        Array.Copy(data, _pos, buffer, offset, n);
        _pos += n;
        return n;
    }
    public override bool CanRead => true;
    public override bool CanSeek => false;
    public override bool CanWrite => false;
    public override long Length => data.Length;
    public override long Position { get => _pos; set => throw new NotSupportedException(); }
    public override void Flush() { }
    public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
    public override void SetLength(long value) => throw new NotSupportedException();
    public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
}
