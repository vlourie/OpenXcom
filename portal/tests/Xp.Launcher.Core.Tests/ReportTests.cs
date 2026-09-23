using System.Net;
using System.Text;
using System.Text.Json;

namespace Xp.Launcher.Core.Tests;

/// <summary>A fake portal: counts calls, can drop the network, can refuse files.</summary>
public sealed class FakePortal : HttpMessageHandler
{
    public int Creates, Uploads;
    public bool Offline;
    /// <summary>The answer to a create is lost on the way back after the server did the work.</summary>
    public bool LoseCreateAnswer;
    public Func<string, (HttpStatusCode, string)?>? RefuseFile;
    public readonly List<(string Name, long Size)> Files = new();
    public readonly List<JsonElement> Created = new();
    public readonly HashSet<string> Keys = new();

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage req, CancellationToken ct)
    {
        if (Offline) throw new HttpRequestException("no route to host");
        var path = req.RequestUri!.AbsolutePath;
        if (req.Method == HttpMethod.Post && path == "/api/v1/tickets")
        {
            var key = req.Headers.GetValues("Idempotency-Key").Single();
            if (Keys.Add(key))
            {
                Creates++;
                Created.Add(JsonDocument.Parse(await req.Content!.ReadAsStringAsync(ct)).RootElement.Clone());
            }
            if (LoseCreateAnswer) { LoseCreateAnswer = false; throw new HttpRequestException("connection reset"); }
            return Json(HttpStatusCode.Created, """{"number":7,"displayNumber":"XP-000007","token":"tok","url":"https://p.test/t/7?k=tok"}""");
        }
        if (req.Method == HttpMethod.Get && path == "/api/v1/tickets/7")
        {
            var files = string.Join(",", Files.Select(f => $$"""{"id":"{{Guid.NewGuid()}}","fileName":"{{f.Name}}","size":{{f.Size}},"scan":"Clean"}"""));
            return Json(HttpStatusCode.OK, $$"""{"number":7,"displayNumber":"XP-000007","category":"code","status":"New","title":"t","description":"d","createdAt":"2026-09-23T00:00:00Z","updatedAt":"2026-09-23T00:00:00Z","messages":[],"attachments":[{{files}}]}""");
        }
        if (req.Method == HttpMethod.Post && path == "/api/v1/tickets/7/attachments")
        {
            Assert.Equal("tok", req.Headers.GetValues("X-Ticket-Token").Single());
            var form = (MultipartFormDataContent)req.Content!;
            var part = form.Single();
            var name = part.Headers.ContentDisposition!.FileNameStar ?? part.Headers.ContentDisposition.FileName!.Trim('"');
            var bytes = await part.ReadAsByteArrayAsync(ct);
            if (RefuseFile?.Invoke(name) is { } refusal) return Json(refusal.Item1, refusal.Item2);
            Uploads++;
            Files.Add((name, bytes.Length));
            LastBodies[name] = bytes;
            return Json(HttpStatusCode.Created, "{}");
        }
        return new HttpResponseMessage(HttpStatusCode.NotFound);
    }

    public readonly Dictionary<string, byte[]> LastBodies = new();

    static HttpResponseMessage Json(HttpStatusCode code, string body) =>
        new(code) { Content = new StringContent(body, Encoding.UTF8, "application/json") };
}

public sealed class ReportTests : IDisposable
{
    readonly string _root = Path.Combine(Path.GetTempPath(), "xp-tests", Guid.NewGuid().ToString("N"));
    readonly FakePortal _portal = new();

    string Reports => Path.Combine(_root, "game", "user", "reports");
    string SaveDir => Path.Combine(_root, "game", "user", "piratez");
    string LogFile => Path.Combine(_root, "game", "user", "openxcom.log");

    public void Dispose()
    {
        try { Directory.Delete(_root, true); } catch (IOException) { }
    }

    /// <summary>What the game leaves on F8: shot.png and context.json, paths with forward slashes.</summary>
    Report NewReport(string? log = null, string? snapshot = null)
    {
        var id = Guid.NewGuid().ToString();
        var dir = Path.Combine(Reports, id);
        Directory.CreateDirectory(dir);
        Directory.CreateDirectory(SaveDir);
        File.WriteAllBytes(Path.Combine(dir, "shot.png"), [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 1, 2, 3]);
        File.WriteAllText(LogFile, log ?? "[INFO] started\n[INFO] Feedback: report written\n");
        File.WriteAllText(Path.Combine(SaveDir, "battle.sav"), "name: my battle\nversion: Extended 8.7.1\n");
        File.WriteAllText(Path.Combine(SaveDir, "_autogeo_.asav"), "name: auto\nversion: Extended 8.7.1\n");
        // written in the same tick as battle.sav, which would leave the newest-first order to chance
        File.SetLastWriteTimeUtc(Path.Combine(SaveDir, "_autogeo_.asav"), DateTime.UtcNow.AddHours(-1));
        if (snapshot is not null) File.WriteAllText(Path.Combine(dir, "snapshot.sav"), snapshot);
        var fwd = (string p) => p.Replace('\\', '/');
        File.WriteAllText(Path.Combine(dir, "context.json"), $$"""
            {
              "format": 1,
              "id": "{{id}}",
              "session": "5e7c",
              "createdAt": "2026-09-23T01:02:03Z",
              "engine": "Extended 8.7.1 (vlourie + MuRuCoN)",
              "master": "piratez",
              "mods": [{"id": "Piratez", "version": "0.99N"}, {"id": "hd", "version": ""}],
              "os": "Windows 10.0.26200",
              "language": "ru",
              "state": "GeoscapeState",
              "battle": false,
              "screenWidth": 2560, "screenHeight": 1440,
              "fullscreen": true, "borderless": false, "openGL": false,
              "hdMode": 2, "hdScale": 4,
              "shot": "shot.png",
              "log": "{{fwd(LogFile)}}",
              "saveDir": "{{fwd(SaveDir)}}/",
              "save": "{{(snapshot is null ? "" : "snapshot.sav")}}",
              "gameDir": "{{fwd(Path.Combine(_root, "game"))}}/"
            }
            """);
        var r = Report.Open(dir);
        r.Draft.Title = "Globe goes black";
        r.Draft.Description = "After zooming in the globe is black";
        return r;
    }

    ReportSender Sender(ReportLimits? limits = null) =>
        new(new PortalClient(new HttpClient(_portal), new Uri("https://p.test/")), limits ?? new ReportLimits(),
            new Redactor(Path.Combine(_root, "game"), @"C:\Users\vasya", "vasya"), "0.2.0");

    [Fact]
    public void Game_context_is_read_and_technical_block_has_no_paths()
    {
        var r = NewReport();
        Assert.Equal("GeoscapeState", r.Context!.State);
        Assert.Equal(2560, r.Context.ScreenWidth);
        Assert.True(r.Context.Fullscreen);
        var text = r.ContextText("0.2.0");
        Assert.Contains("mods: Piratez 0.99N, hd", text);
        Assert.Contains("display: 2560x1440 fullscreen, SDL", text);
        Assert.Contains("screen: GeoscapeState", text);
        Assert.DoesNotContain(_root.Replace('\\', '/'), text);
        Assert.DoesNotContain(_root, text);
        Assert.Equal("Piratez 0.99N", r.ModVersion());
    }

    [Fact]
    public void Only_checked_files_are_planned_and_saves_are_listed_newest_first()
    {
        var r = NewReport();
        Assert.Equal(["shot.png"], r.PlannedFiles().Select(f => f.Name));
        r.Draft.AttachShot = false;
        Assert.Empty(r.PlannedFiles());
        File.SetLastWriteTimeUtc(Path.Combine(SaveDir, "battle.sav"), DateTime.UtcNow);
        File.SetLastWriteTimeUtc(Path.Combine(SaveDir, "_autogeo_.asav"), DateTime.UtcNow.AddHours(-1));
        var saves = r.RecentSaves();
        Assert.Equal(["battle.sav", "_autogeo_.asav"], saves.Select(s => s.Name));
        r.Draft.AttachLog = true;
        r.Draft.SavePath = saves[0].Path;
        Assert.Equal(["openxcom.log", "battle.sav"], r.PlannedFiles().Select(f => f.Name));
    }

    [Fact]
    public void Redactor_removes_paths_names_mails_and_secrets()
    {
        var red = new Redactor(@"D:\Games\XPiratez", @"C:\Users\vasya", "vasya");
        var log = """
            [INFO] Data folder is: D:/Games/XPiratez/
            [INFO] User folder is: C:\Users\vasya\Documents\OpenXcom\
            [INFO] other profile C:\Users\Petya Ivanov\AppData\x.cfg
            [INFO] mail me: vasya.pupkin@example.com
            [INFO] url?token=abc123secret&x=1  password: hunter2
            [INFO] Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload
            [INFO] hello vasya, vasyan stays
            """;
        var clean = red.Redact(log);
        Assert.Contains("Data folder is: <game>/", clean);
        Assert.Contains(@"User folder is: <profile>\Documents", clean);
        Assert.Contains(@"C:\Users\<user>\AppData", clean);
        Assert.Contains("<email>", clean);
        Assert.DoesNotContain("abc123secret", clean);
        Assert.DoesNotContain("hunter2", clean);
        Assert.DoesNotContain("eyJhbGciOiJIUzI1NiJ9", clean);
        Assert.Contains("hello <user>, vasyan stays", clean);
    }

    [Fact]
    public async Task Report_is_sent_with_its_files_and_the_log_is_cleaned()
    {
        var r = NewReport(log: $"[INFO] user folder {_root.Replace('\\', '/')}/game/user\n[INFO] mail a@b.cd\n");
        r.Draft.Kind = "graphics";
        r.Draft.AttachLog = true;
        r.Draft.SavePath = r.RecentSaves()[0].Path;
        await Sender().SendAsync(r, CancellationToken.None);

        Assert.Equal(ReportStatus.Sent, r.Draft.Status);
        Assert.Equal("XP-000007", r.Draft.DisplayNumber);
        Assert.Equal(1, _portal.Creates);
        var body = _portal.Created.Single();
        Assert.Equal("graphics", body.GetProperty("category").GetString());
        Assert.Equal("f8", body.GetProperty("source").GetString());
        Assert.True(body.GetProperty("consentToFiles").GetBoolean());
        Assert.Contains("hd: mode 2, scale 4", body.GetProperty("context").GetString());
        Assert.Equal(3, _portal.Uploads);
        var sentLog = Encoding.UTF8.GetString(_portal.LastBodies["openxcom.log"]);
        Assert.Contains("<game>/user", sentLog);
        Assert.DoesNotContain("a@b.cd", sentLog);

        // what is on disk says the same, and survives reopening
        var again = Report.Open(r.Dir);
        Assert.Equal(ReportStatus.Sent, again.Draft.Status);
        Assert.Equal(["shot.png", "openxcom.log", "battle.sav"], again.Draft.Uploaded);
    }

    [Fact]
    public async Task Snapshot_of_this_game_comes_first_and_the_game_language_is_sent()
    {
        var r = NewReport(snapshot: "name: \nversion: Extended 8.7.1\n---\ndifficulty: 1\n");
        File.WriteAllText(Path.Combine(SaveDir, "notes.sav"), "just some text");
        var saves = r.RecentSaves();
        Assert.True(saves[0].Snapshot);
        Assert.Equal(["snapshot.sav", "battle.sav", "_autogeo_.asav"], saves.Select(s => s.Name));   // notes.sav is not a save
        r.Draft.SavePath = saves[0].Path;
        await Sender().SendAsync(r, CancellationToken.None);
        Assert.Equal("ru", _portal.Created.Single().GetProperty("language").GetString());
        Assert.Contains("snapshot.sav", r.Draft.Uploaded);
    }

    [Fact]
    public async Task A_save_that_is_not_a_save_is_named_and_not_sent()
    {
        var r = NewReport();
        var fake = Path.Combine(SaveDir, "battle.sav");
        File.WriteAllBytes(fake, [.. "name: x\nversion: 1\n"u8, 0, 1, 2]);
        r.Draft.SavePath = fake;
        await Sender().SendAsync(r, CancellationToken.None);
        Assert.Equal(ReportStatus.Sent, r.Draft.Status);
        Assert.Equal("file_not_text", r.Draft.Skipped.Single(x => x.Name == "battle.sav").Reason);
        Assert.Null(TextFiles.CheckSave(Path.Combine(SaveDir, "_autogeo_.asav")));
    }

    [Fact]
    public async Task Without_logs_and_saves_there_is_no_consent()
    {
        var r = NewReport();
        await Sender().SendAsync(r, CancellationToken.None);
        Assert.False(_portal.Created.Single().GetProperty("consentToFiles").GetBoolean());
        Assert.Equal("code", _portal.Created.Single().GetProperty("category").GetString());
    }

    [Fact]
    public async Task Offline_report_is_queued_and_a_retry_does_not_duplicate_anything()
    {
        var r = NewReport();
        _portal.Offline = true;
        await Assert.ThrowsAsync<ReportQueuedException>(() => Sender().SendAsync(r, CancellationToken.None));
        Assert.Equal(ReportStatus.Queued, Report.Open(r.Dir).Draft.Status);
        Assert.Equal("network", Report.Open(r.Dir).Draft.LastError);

        // the connection comes back, but the first answer is lost after the ticket was made
        _portal.Offline = false;
        _portal.LoseCreateAnswer = true;
        await Assert.ThrowsAsync<ReportQueuedException>(() => Sender().SendAsync(Report.Open(r.Dir), CancellationToken.None));
        var reopened = Report.Open(r.Dir);
        await Sender().SendAsync(reopened, CancellationToken.None);

        Assert.Equal(ReportStatus.Sent, reopened.Draft.Status);
        Assert.Equal(1, _portal.Creates);   // one ticket: the Idempotency-Key is the report id
        Assert.Equal(1, _portal.Uploads);
    }

    [Fact]
    public async Task A_file_that_arrived_before_the_connection_broke_is_not_sent_twice()
    {
        var r = NewReport();
        r.Draft.TicketNumber = 7;
        r.Draft.Token = "tok";
        r.Save();
        _portal.Files.Add(("shot.png", new FileInfo(r.ShotPath).Length));
        await Sender().SendAsync(r, CancellationToken.None);
        Assert.Equal(0, _portal.Uploads);
        Assert.Equal(["shot.png"], r.Draft.Uploaded);
    }

    [Fact]
    public async Task A_refused_or_oversized_file_is_named_and_the_ticket_still_goes()
    {
        var r = NewReport();
        r.Draft.AttachLog = true;
        var save = Path.Combine(SaveDir, "battle.sav");
        File.WriteAllText(save, "name: battle\nversion: Extended 8.7.1\n" + Convert.ToBase64String(System.Security.Cryptography.RandomNumberGenerator.GetBytes(300)));
        r.Draft.SavePath = save;
        _portal.RefuseFile = name => name == "openxcom.log" ? (HttpStatusCode.Forbidden, """{"code":"consent_required"}""") : null;
        await Sender(new ReportLimits { MaxFileBytes = 100 }).SendAsync(r, CancellationToken.None);

        Assert.Equal(ReportStatus.Sent, r.Draft.Status);
        Assert.Equal(["shot.png"], r.Draft.Uploaded);
        Assert.Equal([("openxcom.log", "consent_required"), ("battle.sav", "file_too_large")],
            r.Draft.Skipped.Select(s => (s.Name, s.Reason)));
    }

    [Fact]
    public async Task A_save_over_the_limit_goes_zipped()
    {
        var r = NewReport();
        var big = Path.Combine(SaveDir, "huge.sav");
        File.WriteAllText(big, "name: huge\nversion: Extended 8.7.1\n" + string.Concat(Enumerable.Repeat("soldiers:\n  - name: Fishface\n", 4000)));
        r.Draft.AttachShot = false;
        r.Draft.SavePath = big;
        await Sender(new ReportLimits { MaxFileBytes = 64 * 1024 }).SendAsync(r, CancellationToken.None);
        Assert.Equal("huge.zip", _portal.Files.Single().Name);
        Assert.True(_portal.Files.Single().Size < 64 * 1024);
    }

    [Fact]
    public async Task A_refused_ticket_goes_back_to_the_form()
    {
        var r = NewReport();
        r.Draft.Title = "";
        var handler = new RefusingPortal();
        var sender = new ReportSender(new PortalClient(new HttpClient(handler), new Uri("https://p.test/")), new ReportLimits(), new Redactor(null, null, null), "0.2.0");
        var e = await Assert.ThrowsAsync<PortalException>(() => sender.SendAsync(r, CancellationToken.None));
        Assert.Equal("title_required", e.Code);
        Assert.Equal(ReportStatus.Draft, Report.Open(r.Dir).Draft.Status);
    }

    sealed class RefusingPortal : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct) =>
            Task.FromResult(new HttpResponseMessage(HttpStatusCode.BadRequest)
            { Content = new StringContent("""{"status":400,"detail":"title is required","code":"title_required"}""", Encoding.UTF8, "application/problem+json") });
    }

    [Fact]
    public void Store_lists_reports_and_rotation_keeps_the_newest_sent()
    {
        var a = NewReport(); a.Draft.Status = ReportStatus.Sent; a.Save();
        Thread.Sleep(20);
        var b = NewReport(); b.Draft.Status = ReportStatus.Sent; b.Save();
        var c = NewReport(); c.Save();
        Directory.CreateDirectory(Path.Combine(Reports, "not-a-report"));

        var all = ReportStore.List([Reports, Reports]);
        Assert.Equal(3, all.Count);
        ReportStore.Rotate(all, keep: 1);
        var left = ReportStore.List([Reports]).Select(r => r.Draft.Id).ToHashSet();
        Assert.Equal(new[] { b.Draft.Id, c.Draft.Id }.Order(), left.Order());   // ids are random: compare as sets
        Assert.True(Directory.Exists(Path.Combine(Reports, "not-a-report")));
    }

    [Fact]
    public async Task Log_tail_starts_at_a_whole_line()
    {
        Directory.CreateDirectory(_root);
        var p = Path.Combine(_root, "long.log");
        File.WriteAllText(p, string.Concat(Enumerable.Range(0, 1000).Select(i => $"line {i:D4}\n")));
        var tail = await ReportSender.ReadTailAsync(p, 100, CancellationToken.None);
        Assert.StartsWith("line ", tail);
        Assert.EndsWith("line 0999\n", tail);
        Assert.True(tail.Length <= 100);
    }

    [Fact]
    public void Discard_refuses_a_folder_that_is_not_a_report()
    {
        var r = NewReport();
        r.Discard();
        Assert.False(Directory.Exists(r.Dir));
        Assert.Throws<InvalidDataException>(() => Report.Open(Path.Combine(_root, "game", "user")));
    }
}
