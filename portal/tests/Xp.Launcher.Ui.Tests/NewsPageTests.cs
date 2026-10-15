using System.Diagnostics;
using System.Net;
using System.Text.Json;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Headless;
using Avalonia.Headless.XUnit;
using Avalonia.Input;
using Avalonia.LogicalTree;
using Avalonia.Threading;
using Xp.Launcher;
using Xp.Manifest;
using Xunit.Abstractions;

namespace Xp.Launcher.Ui.Tests;

/// <summary>
/// The «Обновления» page: every update of the channel newest first, and the roadmap, both from the signed history
/// in the release repository. The repository is in memory; the texts are the real ones from Выпуск/ when the tests
/// run inside the repository. Frames go to XP_UI_SHOTS when it is set.
/// </summary>
public sealed class NewsPageTests
{
    readonly ITestOutputHelper _out;
    readonly string _shots;
    readonly Dictionary<string, byte[]> _blobs = new();
    readonly RepoClient _repo;

    public NewsPageTests(ITestOutputHelper output)
    {
        _out = output;
        _shots = Environment.GetEnvironmentVariable("XP_UI_SHOTS") is { Length: > 0 } s ? s : Path.Combine(Path.GetTempPath(), "xp-ui-tests", "news");
        Directory.CreateDirectory(_shots);
        var (key, pub) = Signing.CreateKeyPair();
        var notes = new ChannelNotes { Channel = "stable", Sequence = 1, Roadmap = { ["ru"] = Real("roadmap.ru.md") ?? "## Сейчас в работе\n\n- **Инвентарь**: 1205 картинок" } };
        var day = new DateTimeOffset(2026, 10, 15, 15, 40, 0, TimeSpan.Zero);
        foreach (var (id, i) in new[] { "2026.10.15-8", "2026.10.15-7", "2026.10.15-6" }.Select((x, i) => (x, i)))
            notes.Releases.Add(new ReleaseNote
            {
                Id = id, Version = id.Replace('-', '.'), Published = day.AddHours(-2 * i),
                Changelog = { ["ru"] = RealNotes(id) ?? $"— Изменение номер {i + 1}: стены в HD получили ровный край." },
            });
        notes.Releases.Add(new ReleaseNote { Id = "2026.09.27-5", Version = "2026.9.27.5", Published = day.AddDays(-18) });   // one without a text
        var bytes = JsonSerializer.SerializeToUtf8Bytes(notes, ManifestJson.Default.ChannelNotes);
        _blobs[BlobKeys.Notes("stable")] = bytes;
        _blobs[BlobKeys.Sig(BlobKeys.Notes("stable"))] = Signing.SerializeSignature(Signing.Sign(key, bytes));
        _repo = new RepoClient(new HttpClient(new Repo(_blobs)), new Uri("http://repo.test/"), new TrustedKeys([Convert.ToBase64String(pub)]));
    }

    [AvaloniaFact]
    public void The_history_lists_every_update_newest_first_and_the_roadmap_is_one_click_away()
    {
        L.Use("ru");
        var page = new NewsPage(() => _repo, () => "stable");
        var w = new Window { Width = 1100, Height = 900, Content = page, Background = Skin.B(Skin.Bg) };
        w.Show();
        page.Shown(roadmap: false);
        Pump(() => Texts(page).Any(t => t.StartsWith("2026.10.15.8")), "the history to load");

        var titles = Texts(page).Where(t => t.StartsWith("2026.")).ToList();
        Assert.Equal(["2026.10.15.8", "2026.10.15.7", "2026.10.15.6", "2026.9.27.5"], titles.Select(t => t.Split(' ')[0]));
        Assert.Contains(L.T("news.empty"), Texts(page));
        Shot(w, "news-history");

        Click(page.GetLogicalDescendants().OfType<Button>().First(b => b.Content as string == L.T("news.roadmap")));
        Assert.DoesNotContain(Texts(page), t => t.StartsWith("2026.10.15.8"));
        Assert.Contains(Texts(page), t => t.Contains("Сейчас в работе"));
        Shot(w, "news-roadmap");
        w.Close();
    }

    [AvaloniaFact]
    public void A_repository_without_a_history_says_so_instead_of_an_error()
    {
        L.Use("ru");
        _blobs.Clear();
        var page = new NewsPage(() => _repo, () => "stable");
        var w = new Window { Width = 900, Height = 500, Content = page };
        w.Show();
        page.Shown(roadmap: false);
        Pump(() => Texts(page).Contains(L.T("news.none")), "the 'no history' line");
        w.Close();
    }

    /// <summary>Every text on the page, a TextBlock's runs joined.</summary>
    static List<string> Texts(Control root) =>
        root.GetLogicalDescendants().OfType<TextBlock>().Where(t => t.IsEffectivelyVisible)
            .Select(t => t.Inlines is { Count: > 0 } runs ? string.Concat(runs.OfType<Avalonia.Controls.Documents.Run>().Select(r => r.Text)) : t.Text ?? "")
            .ToList();

    static string? Real(string name)
    {
        for (var d = new DirectoryInfo(AppContext.BaseDirectory); d is not null; d = d.Parent)
            if (File.Exists(Path.Combine(d.FullName, "Выпуск", name))) return File.ReadAllText(Path.Combine(d.FullName, "Выпуск", name));
        return null;
    }

    static string? RealNotes(string id) => Real(Path.Combine("notes", id + ".ru.txt"));

    static void Pump(Func<bool> until, string what, int ms = 20000)
    {
        var sw = Stopwatch.StartNew();
        while (!until())
        {
            Dispatcher.UIThread.RunJobs();
            AvaloniaHeadlessPlatform.ForceRenderTimerTick();
            if (sw.ElapsedMilliseconds > ms) throw new TimeoutException("waited for " + what);
            Thread.Sleep(10);
        }
        Dispatcher.UIThread.RunJobs();
    }

    static void Settle()
    {
        for (int i = 0; i < 5; i++) { Dispatcher.UIThread.RunJobs(); AvaloniaHeadlessPlatform.ForceRenderTimerTick(); }
    }

    static void Click(Control c)
    {
        Settle();
        var top = TopLevel.GetTopLevel(c)!;
        var p = c.TranslatePoint(new Point(c.Bounds.Width / 2, c.Bounds.Height / 2), top)!.Value;
        top.MouseMove(p, RawInputModifiers.None);
        top.MouseDown(p, MouseButton.Left, RawInputModifiers.None);
        top.MouseUp(p, MouseButton.Left, RawInputModifiers.None);
        Settle();
    }

    void Shot(TopLevel top, string name)
    {
        Settle();
        var frame = top.CaptureRenderedFrame();
        if (frame is null) { _out.WriteLine("no frame for " + name); return; }
        var path = Path.Combine(_shots, name + ".png");
        frame.Save(path);
        _out.WriteLine("frame: " + path);
    }

    sealed class Repo(Dictionary<string, byte[]> blobs) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct) =>
            Task.FromResult(blobs.TryGetValue(request.RequestUri!.AbsolutePath.TrimStart('/'), out var body)
                ? new HttpResponseMessage(HttpStatusCode.OK) { Content = new ByteArrayContent(body) }
                : new HttpResponseMessage(HttpStatusCode.NotFound));
    }
}
