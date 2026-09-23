using System.IO.Compression;
using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;

namespace Xp.Launcher.Core;

/// <summary>What the game wrote into context.json on F8 (src/Engine/Feedback.cpp). Paths are local only.</summary>
public sealed class GameContext
{
    public int Format { get; set; }
    public string Id { get; set; } = "";
    public string Session { get; set; } = "";
    public string CreatedAt { get; set; } = "";
    public string Engine { get; set; } = "";
    public string Master { get; set; } = "";
    public List<ModRef> Mods { get; set; } = new();
    public string Os { get; set; } = "";
    public string Language { get; set; } = "";
    public string State { get; set; } = "";
    public bool Battle { get; set; }
    public int ScreenWidth { get; set; }
    public int ScreenHeight { get; set; }
    public bool Fullscreen { get; set; }
    public bool Borderless { get; set; }
    public bool OpenGL { get; set; }
    public int HdMode { get; set; }
    public int HdScale { get; set; }
    public string Shot { get; set; } = "";
    public string Log { get; set; } = "";
    public string SaveDir { get; set; } = "";
    /// <summary>The game as it was at F8, written by the engine into the report folder; empty in ironman or with no game loaded.</summary>
    public string Save { get; set; } = "";
    public string GameDir { get; set; } = "";
}

public sealed class ModRef
{
    public string Id { get; set; } = "";
    public string Version { get; set; } = "";
}

public enum ReportStatus { Draft, Queued, Sent }

/// <summary>The report form's state, report.json next to the game's files. Stays on this machine.</summary>
public sealed class ReportDraft
{
    public string Id { get; set; } = "";
    /// <summary>bug, graphics, suggestion, balance, translation, other — see <see cref="ReportKinds"/>.</summary>
    public string Kind { get; set; } = ReportKinds.Bug;
    public string Title { get; set; } = "";
    public string Description { get; set; } = "";
    public string Steps { get; set; } = "";
    public string Expected { get; set; } = "";
    public string Actual { get; set; } = "";
    public bool AttachShot { get; set; } = true;
    public bool AttachLog { get; set; }
    /// <summary>Full path of the save the player chose to attach, or null.</summary>
    public string? SavePath { get; set; }
    public ReportStatus Status { get; set; } = ReportStatus.Draft;
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
    public DateTimeOffset UpdatedAt { get; set; } = DateTimeOffset.UtcNow;
    public long? TicketNumber { get; set; }
    public string? DisplayNumber { get; set; }
    /// <summary>The player's own secret link to the ticket. Never written to the launcher log.</summary>
    public string? TicketUrl { get; set; }
    public string? Token { get; set; }
    public List<string> Uploaded { get; set; } = new();
    public List<SkippedFile> Skipped { get; set; } = new();
    public string? LastError { get; set; }
}

public sealed class SkippedFile
{
    public string Name { get; set; } = "";
    public string Reason { get; set; } = "";
}

public static class ReportKinds
{
    public const string Bug = "bug";
    public static readonly string[] All = [Bug, "graphics", "suggestion", "balance", "translation", "other"];

    /// <summary>The portal's ticket category (Auth/Access.cs Categories) for a kind of report.</summary>
    public static string Category(string kind) => kind switch
    {
        "graphics" => "graphics",
        "balance" => "balance",
        "translation" => "translation",
        "suggestion" or "other" => "general",
        _ => "code",
    };
}

public sealed record SaveFile(string Path, string Name, long Size, DateTime Modified, bool Snapshot = false);

/// <summary>A file about to be sent, as the form shows it: name and size.</summary>
public sealed record PlannedFile(string Name, string Source, long Size, string Role);

public sealed class ReportLimits
{
    /// <summary>Must not exceed the portal's Attachments:MaxFileBytes; a larger save is zipped first.</summary>
    public long MaxFileBytes { get; set; } = 50L * 1024 * 1024;
    /// <summary>Only the end of a long log is sent: the part about the moment of F8.</summary>
    public long MaxLogBytes { get; set; } = 4L * 1024 * 1024;
    /// <summary>Sent reports kept for their ticket links; older ones are deleted.</summary>
    public int KeepSent { get; set; } = 20;
}

/// <summary>One report folder: user/reports/&lt;id&gt;/ with shot.png, context.json and report.json.</summary>
public sealed class Report
{
    public const string ContextFile = "context.json";
    public const string DraftFile = "report.json";

    Report(string dir, GameContext? context, ReportDraft draft)
    {
        Dir = dir;
        Context = context;
        Draft = draft;
    }

    public string Dir { get; }
    public GameContext? Context { get; }
    public ReportDraft Draft { get; }
    public string ShotPath => System.IO.Path.Combine(Dir, string.IsNullOrEmpty(Context?.Shot) ? "shot.png" : System.IO.Path.GetFileName(Context.Shot));

    /// <summary>A folder is a report when its name is a GUID and it holds the game's context or our draft.</summary>
    public static bool IsReportDir(string dir) =>
        Guid.TryParse(System.IO.Path.GetFileName(dir.TrimEnd('/', '\\')), out _)
        && (File.Exists(System.IO.Path.Combine(dir, ContextFile)) || File.Exists(System.IO.Path.Combine(dir, DraftFile)));

    public static Report Open(string dir)
    {
        dir = System.IO.Path.GetFullPath(dir);
        if (!IsReportDir(dir)) throw new InvalidDataException("not a report folder");
        var context = ReadJson(System.IO.Path.Combine(dir, ContextFile), ReportJson.Default.GameContext);
        var draft = ReadJson(System.IO.Path.Combine(dir, DraftFile), ReportJson.Default.ReportDraft)
                    ?? new ReportDraft { Id = System.IO.Path.GetFileName(dir) };
        if (context is not null && DateTimeOffset.TryParse(context.CreatedAt, out var created) && !File.Exists(System.IO.Path.Combine(dir, DraftFile)))
            draft.CreatedAt = created;
        return new Report(dir, context, draft);
    }

    static T? ReadJson<T>(string path, System.Text.Json.Serialization.Metadata.JsonTypeInfo<T> type) where T : class
    {
        if (!File.Exists(path)) return null;
        try { return JsonSerializer.Deserialize(File.ReadAllBytes(path), type); }
        catch (JsonException) { return null; }
    }

    public void Save()
    {
        Draft.UpdatedAt = DateTimeOffset.UtcNow;
        FileUtil.WriteAtomic(System.IO.Path.Combine(Dir, DraftFile), JsonSerializer.SerializeToUtf8Bytes(Draft, ReportJson.Default.ReportDraft));
    }

    /// <summary>Deletes the whole report: Cancel in the form, Delete in the list.</summary>
    public void Discard()
    {
        if (IsReportDir(Dir)) Directory.Delete(Dir, recursive: true);
    }

    /// <summary>After sending only report.json stays, for the ticket link.</summary>
    public void TrimSent()
    {
        foreach (var f in Directory.EnumerateFiles(Dir))
            if (!string.Equals(System.IO.Path.GetFileName(f), DraftFile, StringComparison.OrdinalIgnoreCase))
                File.Delete(f);
    }

    /// <summary>The engine's snapshot of the game at F8, when it wrote one.</summary>
    public string? SnapshotPath =>
        !string.IsNullOrEmpty(Context?.Save) && File.Exists(System.IO.Path.Combine(Dir, System.IO.Path.GetFileName(Context.Save)))
            ? System.IO.Path.Combine(Dir, System.IO.Path.GetFileName(Context.Save)) : null;

    /// <summary>
    /// What can go as the save: the snapshot of this very game first, then recent saves of the master
    /// mod, newest first. A file that does not start like a save is not offered at all.
    /// </summary>
    public IReadOnlyList<SaveFile> RecentSaves(int max = 15)
    {
        var list = new List<SaveFile>();
        if (SnapshotPath is { } snap)
        {
            var fi = new FileInfo(snap);
            list.Add(new SaveFile(fi.FullName, fi.Name, fi.Length, fi.LastWriteTime, Snapshot: true));
        }
        var dir = Context?.SaveDir;
        if (string.IsNullOrEmpty(dir) || !Directory.Exists(dir)) return list;
        list.AddRange(new DirectoryInfo(dir).EnumerateFiles()
            .Where(f => f.Extension.Equals(".sav", StringComparison.OrdinalIgnoreCase) || f.Extension.Equals(".asav", StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(f => f.LastWriteTimeUtc)
            .Where(f => TextFiles.StartsLikeSave(f.FullName)).Take(max)
            .Select(f => new SaveFile(f.FullName, f.Name, f.Length, f.LastWriteTime)));
        return list;
    }

    /// <summary>What goes with the report, in the order it is sent. Each needs its checkbox.</summary>
    public IReadOnlyList<PlannedFile> PlannedFiles()
    {
        var list = new List<PlannedFile>();
        if (Draft.AttachShot && File.Exists(ShotPath)) list.Add(new PlannedFile("shot.png", ShotPath, new FileInfo(ShotPath).Length, "shot"));
        if (Draft.AttachLog && LogPath is { } log) list.Add(new PlannedFile("openxcom.log", log, new FileInfo(log).Length, "log"));
        if (Draft.SavePath is { } save && File.Exists(save)) list.Add(new PlannedFile(System.IO.Path.GetFileName(save), save, new FileInfo(save).Length, "save"));
        return list;
    }

    public string? LogPath => !string.IsNullOrEmpty(Context?.Log) && File.Exists(Context.Log) ? Context.Log : null;

    /// <summary>The technical block of the ticket: versions and settings, no paths and no names.</summary>
    public string ContextText(string launcherVersion)
    {
        var c = Context;
        var sb = new StringBuilder();
        if (c is not null)
        {
            sb.Append("engine: ").AppendLine(c.Engine);
            sb.Append("master: ").AppendLine(c.Master);
            sb.Append("mods: ").AppendLine(string.Join(", ", c.Mods.Select(m => string.IsNullOrEmpty(m.Version) ? m.Id : $"{m.Id} {m.Version}")));
            sb.Append("os: ").AppendLine(c.Os);
            sb.Append("language: ").AppendLine(c.Language);
            sb.Append("screen: ").Append(c.State).AppendLine(c.Battle ? " (battle)" : "");
            sb.Append("display: ").Append(c.ScreenWidth).Append('x').Append(c.ScreenHeight)
              .Append(c.Fullscreen ? " fullscreen" : c.Borderless ? " borderless" : " windowed")
              .AppendLine(c.OpenGL ? ", OpenGL" : ", SDL");
            sb.Append("hd: mode ").Append(c.HdMode).Append(", scale ").AppendLine(c.HdScale.ToString(System.Globalization.CultureInfo.InvariantCulture));
            sb.Append("taken: ").AppendLine(c.CreatedAt);
            sb.Append("session: ").AppendLine(c.Session);
        }
        sb.Append("launcher: ").AppendLine(launcherVersion);
        sb.Append("report: ").Append(Draft.Id);
        return sb.ToString();
    }

    public string? ModVersion()
    {
        var c = Context;
        if (c is null) return null;
        var master = c.Mods.FirstOrDefault(m => string.Equals(m.Id, c.Master, StringComparison.OrdinalIgnoreCase));
        return master is null ? c.Master : $"{master.Id} {master.Version}".Trim();
    }
}

/// <summary>
/// Cleans a log before it leaves the machine: the game and profile folders, the Windows user name,
/// e-mail addresses and anything that looks like a secret.
/// </summary>
public sealed partial class Redactor(string? gameDir, string? profileDir, string? userName)
{
    public static Redactor ForThisMachine(string? gameDir) =>
        new(gameDir, Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), Environment.UserName);

    public string Redact(string text)
    {
        text = ReplacePath(text, gameDir, "<game>");
        text = ReplacePath(text, profileDir, "<profile>");
        text = UsersFolder().Replace(text, "$1<user>");
        text = Email().Replace(text, "<email>");
        text = Bearer().Replace(text, "$1 <hidden>");
        text = Secret().Replace(text, "$1=<hidden>");
        if (userName is { Length: >= 3 })
            text = Regex.Replace(text, @"(?<![\p{L}\p{N}_])" + Regex.Escape(userName) + @"(?![\p{L}\p{N}_])", "<user>", RegexOptions.IgnoreCase);
        return text;
    }

    static string ReplacePath(string text, string? path, string mask)
    {
        if (string.IsNullOrEmpty(path) || path.Length < 4) return text;
        var p = path.TrimEnd('/', '\\');
        // the game writes forward slashes, Windows back slashes: both spellings of the same folder
        foreach (var variant in new[] { p, p.Replace('\\', '/'), p.Replace('/', '\\') }.Distinct())
            text = text.Replace(variant, mask, StringComparison.OrdinalIgnoreCase);
        return text;
    }

    [GeneratedRegex(@"([A-Za-z]:[\\/](?:Users|Documents and Settings)[\\/])[^\\/\r\n""<>|]+", RegexOptions.IgnoreCase)]
    private static partial Regex UsersFolder();

    [GeneratedRegex(@"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")]
    private static partial Regex Email();

    [GeneratedRegex(@"(?i)\b(token|password|passwd|pwd|secret|api[_-]?key|cookie|authorization|session[_-]?id)\s*[:=]\s*[^\s,;]+")]
    private static partial Regex Secret();

    [GeneratedRegex(@"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}")]
    private static partial Regex Bearer();
}

public sealed record CreateTicketRequest(
    string Category, string Title, string Description, string? Steps, string? Expected, string? Actual,
    string? GameVersion, string? ModVersion, string? LauncherVersion, string? Email, bool ConsentToFiles, string? Source, string? Context,
    string? Language = null);

public sealed record CreateTicketResponse(long Number, string DisplayNumber, string? Token, string Url);
public sealed record TicketAttachmentView(Guid Id, string FileName, long Size, string Scan);
public sealed record TicketView(long Number, string DisplayNumber, string Category, string Status, string Title, string Description,
    DateTimeOffset CreatedAt, DateTimeOffset UpdatedAt, List<TicketAttachmentView> Attachments);

/// <summary>The portal said no: a machine-readable code (file_too_large, consent_required, …) and its HTTP status.</summary>
public sealed class PortalException(int status, string code, string message) : Exception(message)
{
    public int Status { get; } = status;
    public string Code { get; } = code;
    /// <summary>Worth trying again later: the server is overloaded or down, not refusing this request.</summary>
    public bool Transient => Status is 408 or 429 or >= 500;
}

/// <summary>/api/v1 of the portal, the part the launcher uses. A guest proves access with the ticket token.</summary>
public sealed class PortalClient(HttpClient http, Uri baseUri)
{
    public Uri BaseUri { get; } = baseUri.AbsoluteUri.EndsWith('/') ? baseUri : new Uri(baseUri.AbsoluteUri + "/");

    public async Task<CreateTicketResponse> CreateAsync(CreateTicketRequest request, string idempotencyKey, CancellationToken ct)
    {
        using var msg = new HttpRequestMessage(HttpMethod.Post, new Uri(BaseUri, "api/v1/tickets"))
        {
            Content = JsonContent.Create(request, ReportJson.Default.CreateTicketRequest),
        };
        msg.Headers.Add("Idempotency-Key", idempotencyKey);
        using var resp = await http.SendAsync(msg, ct);
        await ThrowIfFailedAsync(resp, ct);
        return await resp.Content.ReadFromJsonAsync(ReportJson.Default.CreateTicketResponse, ct)
               ?? throw new PortalException((int)resp.StatusCode, "bad_response", "empty answer");
    }

    public async Task<TicketView?> GetAsync(long number, string token, CancellationToken ct)
    {
        using var msg = new HttpRequestMessage(HttpMethod.Get, new Uri(BaseUri, $"api/v1/tickets/{number}"));
        msg.Headers.Add("X-Ticket-Token", token);
        using var resp = await http.SendAsync(msg, ct);
        if (resp.StatusCode == HttpStatusCode.NotFound) return null;
        await ThrowIfFailedAsync(resp, ct);
        return await resp.Content.ReadFromJsonAsync(ReportJson.Default.TicketView, ct);
    }

    public async Task UploadAsync(long number, string token, string fileName, Stream content, CancellationToken ct)
    {
        using var form = new MultipartFormDataContent();
        var part = new StreamContent(content);
        part.Headers.ContentType = new MediaTypeHeaderValue("application/octet-stream");
        form.Add(part, "file", fileName);
        using var msg = new HttpRequestMessage(HttpMethod.Post, new Uri(BaseUri, $"api/v1/tickets/{number}/attachments")) { Content = form };
        msg.Headers.Add("X-Ticket-Token", token);
        using var resp = await http.SendAsync(msg, ct);
        await ThrowIfFailedAsync(resp, ct);
    }

    static async Task ThrowIfFailedAsync(HttpResponseMessage resp, CancellationToken ct)
    {
        if (resp.IsSuccessStatusCode) return;
        string code = "http_" + (int)resp.StatusCode, detail = resp.ReasonPhrase ?? "";
        try
        {
            var body = await resp.Content.ReadAsStringAsync(ct);
            using var doc = JsonDocument.Parse(body);
            if (doc.RootElement.TryGetProperty("code", out var c) && c.ValueKind == JsonValueKind.String) code = c.GetString()!;
            if (doc.RootElement.TryGetProperty("detail", out var d) && d.ValueKind == JsonValueKind.String) detail = d.GetString()!;
        }
        catch (JsonException) { }
        // Kestrel itself refuses an oversized body before our code sees it: no JSON then
        if (resp.StatusCode == HttpStatusCode.RequestEntityTooLarge && code.StartsWith("http_")) code = "file_too_large";
        throw new PortalException((int)resp.StatusCode, code, detail);
    }
}

/// <summary>The network is gone or the server is down: the report stays queued and is offered again later.</summary>
public sealed class ReportQueuedException(string message, Exception inner) : Exception(message, inner);

/// <summary>
/// Sends a report step by step and writes down every step, so a retry after a lost connection
/// continues where it stopped: the ticket is created once (the Idempotency-Key is the report id),
/// a file that already arrived is not sent again.
/// </summary>
public sealed class ReportSender(PortalClient portal, ReportLimits limits, Redactor redactor, string launcherVersion)
{
    public async Task SendAsync(Report report, CancellationToken ct)
    {
        var d = report.Draft;
        if (d.Status == ReportStatus.Sent) return;
        d.Status = ReportStatus.Queued;
        d.LastError = null;
        report.Save();
        try
        {
            if (d.TicketNumber is null)
            {
                var files = report.PlannedFiles();
                var req = new CreateTicketRequest(
                    ReportKinds.Category(d.Kind), d.Title.Trim(), d.Description.Trim(), Blank(d.Steps), Blank(d.Expected), Blank(d.Actual),
                    Cap(report.Context?.Engine, 64), Cap(report.ModVersion(), 64), launcherVersion, Email: null,
                    ConsentToFiles: files.Any(f => f.Role is "log" or "save"), Source: "f8", Context: report.ContextText(launcherVersion),
                    Language: Blank(report.Context?.Language ?? ""));
                var created = await portal.CreateAsync(req, d.Id, ct);
                d.TicketNumber = created.Number;
                d.DisplayNumber = created.DisplayNumber;
                d.Token = created.Token;
                d.TicketUrl = created.Url;
                report.Save();
            }

            var already = d.Token is null ? null : await portal.GetAsync(d.TicketNumber.Value, d.Token, ct);
            foreach (var f in report.PlannedFiles())
            {
                if (d.Uploaded.Contains(f.Name) || d.Skipped.Any(s => s.Name == f.Name)) continue;
                // the site refuses these too; saying so here keeps the reason in the player's language
                if (f.Role == "save" && TextFiles.CheckSave(f.Source) is { } notSave)
                {
                    d.Skipped.Add(new SkippedFile { Name = f.Name, Reason = notSave });
                    report.Save();
                    continue;
                }
                var (name, bytes, stream) = await PrepareAsync(f, ct);
                await using (stream)
                {
                    long size = bytes?.LongLength ?? stream!.Length;
                    // an earlier try may have delivered the file and lost only the answer
                    if (already?.Attachments.Any(a => a.FileName == name && a.Size == size) == true)
                    {
                        d.Uploaded.Add(f.Name);
                        report.Save();
                        continue;
                    }
                    if (size > limits.MaxFileBytes)
                    {
                        d.Skipped.Add(new SkippedFile { Name = f.Name, Reason = "file_too_large" });
                        report.Save();
                        continue;
                    }
                    try
                    {
                        await portal.UploadAsync(d.TicketNumber.Value, d.Token!, name, bytes is not null ? new MemoryStream(bytes) : stream!, ct);
                        d.Uploaded.Add(f.Name);
                    }
                    catch (PortalException e) when (!e.Transient)
                    {
                        // the ticket is there; a refused file is named in the result, not a reason to stop
                        d.Skipped.Add(new SkippedFile { Name = f.Name, Reason = e.Code });
                    }
                    report.Save();
                }
            }
            d.Status = ReportStatus.Sent;
            d.LastError = null;
            report.Save();
        }
        catch (Exception e) when (e is HttpRequestException or TaskCanceledException { InnerException: TimeoutException } || e is PortalException { Transient: true })
        {
            d.Status = ReportStatus.Queued;
            d.LastError = e is PortalException pe ? pe.Code : "network";
            report.Save();
            throw new ReportQueuedException(e.Message, e);
        }
        catch (PortalException e)
        {
            // refused as a whole (bad text, reused key): back to the form, the player can fix it
            d.Status = ReportStatus.Draft;
            d.LastError = e.Code;
            report.Save();
            throw;
        }
    }

    /// <summary>The log goes cleaned and cut to its end; a save that is too big goes zipped; the rest as is.</summary>
    async Task<(string Name, byte[]? Bytes, Stream? Stream)> PrepareAsync(PlannedFile f, CancellationToken ct)
    {
        switch (f.Role)
        {
            case "log":
                // decoding already turned broken bytes into U+FFFD; a NUL would still make the site refuse the log
                return (f.Name, Encoding.UTF8.GetBytes(redactor.Redact(await ReadTailAsync(f.Source, limits.MaxLogBytes, ct)).Replace("\0", "")), null);
            case "save" when f.Size > limits.MaxFileBytes:
                var ms = new MemoryStream();
                using (var zip = new ZipArchive(ms, ZipArchiveMode.Create, leaveOpen: true))
                {
                    var entry = zip.CreateEntry(f.Name, CompressionLevel.SmallestSize);
                    await using var src = OpenShared(f.Source);
                    await using var dst = entry.Open();
                    await src.CopyToAsync(dst, ct);
                }
                return (Path.ChangeExtension(f.Name, ".zip"), ms.ToArray(), null);
            default:
                return (f.Name, null, OpenShared(f.Source));
        }
    }

    /// <summary>The game keeps its log open for writing; read it anyway, and only the last <paramref name="max"/> bytes.</summary>
    internal static async Task<string> ReadTailAsync(string path, long max, CancellationToken ct)
    {
        await using var s = OpenShared(path);
        if (s.Length > max) s.Seek(-max, SeekOrigin.End);
        using var r = new StreamReader(s, Encoding.UTF8, detectEncodingFromByteOrderMarks: true);
        var text = await r.ReadToEndAsync(ct);
        // the cut may have landed inside a line: start from the next whole one
        if (s.Length > max && text.IndexOf('\n') is var nl and >= 0) text = text[(nl + 1)..];
        return text;
    }

    static FileStream OpenShared(string path) => new(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);

    static string? Blank(string s) => string.IsNullOrWhiteSpace(s) ? null : s.Trim();
    static string? Cap(string? s, int max) => s is null ? null : s.Length <= max ? s : s[..max];
}

/// <summary>All reports on this machine: the game's user/reports and any folder a report came from.</summary>
public static class ReportStore
{
    public static IReadOnlyList<Report> List(IEnumerable<string> roots)
    {
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var list = new List<Report>();
        foreach (var root in roots)
        {
            if (!Directory.Exists(root)) continue;
            foreach (var dir in Directory.EnumerateDirectories(root))
            {
                if (!Report.IsReportDir(dir) || !seen.Add(Path.GetFullPath(dir))) continue;
                try { list.Add(Report.Open(dir)); }
                catch (Exception e) when (e is IOException or UnauthorizedAccessException or InvalidDataException) { }
            }
        }
        return list.OrderByDescending(r => r.Draft.CreatedAt).ToList();
    }

    /// <summary>Keeps the newest <paramref name="keep"/> sent reports; they are only links by then.</summary>
    public static void Rotate(IEnumerable<Report> reports, int keep)
    {
        foreach (var r in reports.Where(r => r.Draft.Status == ReportStatus.Sent).OrderByDescending(r => r.Draft.UpdatedAt).Skip(keep))
        {
            try { r.Discard(); }
            catch (Exception e) when (e is IOException or UnauthorizedAccessException) { }
        }
    }
}

[JsonSourceGenerationOptions(WriteIndented = true, PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase,
    PropertyNameCaseInsensitive = true, UseStringEnumConverter = true)]
[JsonSerializable(typeof(GameContext))]
[JsonSerializable(typeof(ReportDraft))]
[JsonSerializable(typeof(CreateTicketRequest))]
[JsonSerializable(typeof(CreateTicketResponse))]
[JsonSerializable(typeof(TicketView))]
internal sealed partial class ReportJson : JsonSerializerContext
{
}

/// <summary>
/// The same rule the site applies to logs and saves (Xp.Portal FileRules/ContentCheck): UTF-8 text
/// without NUL bytes all the way through, and a save opens with its "name:" / "version:" header.
/// </summary>
public static class TextFiles
{
    const int HeadBytes = 8192;

    public static bool SaveHeader(ReadOnlySpan<byte> head)
    {
        if (head.StartsWith((ReadOnlySpan<byte>)[0xEF, 0xBB, 0xBF])) head = head[3..];
        return head.StartsWith("name:"u8) && head.IndexOf("\nversion:"u8) > 0;
    }

    /// <summary>Quick look for the list of saves: only the header.</summary>
    public static bool StartsLikeSave(string path)
    {
        try
        {
            using var s = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
            var head = new byte[HeadBytes];
            int n = s.ReadAtLeast(head, head.Length, throwOnEndOfStream: false);
            return SaveHeader(head.AsSpan(0, n));
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { return false; }
    }

    /// <summary>The whole file, before it is sent: null when it is a save, else the reason (a key shared with the site).</summary>
    public static string? CheckSave(string path)
    {
        using var s = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
        var dec = new UTF8Encoding(false, throwOnInvalidBytes: true).GetDecoder();
        var buf = new byte[81920];
        var chars = new char[buf.Length + 4];
        var head = new byte[HeadBytes];
        int headLen = 0, n;
        while ((n = s.Read(buf, 0, buf.Length)) > 0)
        {
            var chunk = buf.AsSpan(0, n);
            if (headLen < head.Length)
            {
                var take = Math.Min(n, head.Length - headLen);
                chunk[..take].CopyTo(head.AsSpan(headLen));
                headLen += take;
            }
            if (chunk.IndexOf((byte)0) >= 0) return "file_not_text";
            try { dec.GetChars(chunk, chars, flush: false); }
            catch (DecoderFallbackException) { return "file_not_text"; }
        }
        return SaveHeader(head.AsSpan(0, headLen)) ? null : "file_not_save";
    }
}
