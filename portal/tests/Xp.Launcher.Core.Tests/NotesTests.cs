using Xp.Manifest;
using Xp.ReleaseBuilder;

namespace Xp.Launcher.Core.Tests;

/// <summary>
/// The signed history of a channel (channels/&lt;channel&gt;.notes.json): what the launcher's
/// «Обновления» page and the site's /releases and /roadmap read.
/// </summary>
public sealed class NotesTests : IDisposable
{
    readonly Fixture f = new();
    readonly RepoClient _repo;

    public NotesTests()
    {
        _repo = new RepoClient(new HttpClient(f.Server), new Uri("http://repo.test/"), new TrustedKeys([Convert.ToBase64String(f.PublicKey)]));
        f.StageV1();
    }

    public void Dispose() => f.Dispose();

    void Release(string id, string ru, string? en = null)
    {
        var o = new BuildOptions { StageDir = f.Stage, Id = id, Version = id, Channel = "stable", Launch = "openxcom_hd.exe" };
        o.Changelog["ru"] = ru;
        if (en is not null) o.Changelog["en"] = en;
        f.Repo.Build(o, f.Key);
        f.Repo.Publish("stable", id, f.Key);
    }

    [Fact]
    public async Task Every_published_release_is_in_the_history_newest_first_with_its_texts()
    {
        Release("r1", "— первое", "- first");
        f.StageV2();
        Release("r2", "— второе");

        var notes = await _repo.GetNotesAsync("stable", default);
        Assert.Equal(["r2", "r1"], notes.Releases.Select(r => r.Id));
        Assert.Equal("— первое", notes.Releases[1].Changelog["ru"]);
        Assert.Equal("- first", notes.Releases[1].Changelog["en"]);
        Assert.False(notes.Releases[0].Changelog.ContainsKey("en"));
    }

    [Fact]
    public async Task A_revoked_release_leaves_the_history_and_a_rollback_does_not_repeat_one()
    {
        Release("r1", "— первое");
        f.StageV2();
        Release("r2", "— второе");
        f.Repo.Revoke("stable", "r2", f.Key);   // the channel goes back to r1

        var notes = await _repo.GetNotesAsync("stable", default);
        Assert.Equal(["r1"], notes.Releases.Select(r => r.Id));
    }

    [Fact]
    public async Task The_roadmap_survives_the_next_release_until_a_new_one_is_given()
    {
        Release("r1", "— первое");
        f.Repo.WriteNotes("stable", f.Key, new() { ["ru"] = "## Сейчас\n- стены", ["en"] = "## Now\n- walls" });
        f.StageV2();
        Release("r2", "— второе");

        var notes = await _repo.GetNotesAsync("stable", default);
        Assert.Equal("## Сейчас\n- стены", notes.Roadmap["ru"]);
        Assert.Equal(2, notes.Releases.Count);
        // the sequence grows with every rewrite: publish, the roadmap, publish
        Assert.Equal(3, notes.Sequence);
    }

    [Fact]
    public async Task A_history_that_does_not_match_its_signature_is_refused()
    {
        Release("r1", "— первое");
        var path = Path.Combine(f.RepoDir, "channels", "stable.notes.json");
        var text = File.ReadAllText(path);
        Assert.Contains("\"sequence\":1,", text);   // control: the tamper below really changes the file
        File.WriteAllText(path, text.Replace("\"sequence\":1,", "\"sequence\":9,"));
        await Assert.ThrowsAsync<TrustException>(() => _repo.GetNotesAsync("stable", default));
    }

    [Fact]
    public async Task A_repository_from_before_the_history_answers_not_found()
    {
        await Assert.ThrowsAsync<FileNotFoundException>(() => _repo.GetNotesAsync("stable", default));
    }

    [Fact]
    public void The_little_markdown_reads_headings_items_and_paragraphs()
    {
        var blocks = NoteText.Parse("""
            # Дорожная карта
            ## Готово
            — Стены: ровный край
              по силуэту оригинала
            - Полы
              * вода
            1. Сначала инвентарь

            Простой абзац,
            в две строки.
            """);
        Assert.Equal(
        [
            new NoteBlock(NoteKind.Heading, 1, "Дорожная карта"),
            new NoteBlock(NoteKind.Heading, 2, "Готово"),
            new NoteBlock(NoteKind.Bullet, 0, "Стены: ровный край по силуэту оригинала"),
            new NoteBlock(NoteKind.Bullet, 0, "Полы"),
            new NoteBlock(NoteKind.Bullet, 1, "вода"),
            new NoteBlock(NoteKind.Bullet, 0, "1. Сначала инвентарь"),
            new NoteBlock(NoteKind.Paragraph, 0, "Простой абзац, в две строки."),
        ], blocks);
    }

    [Fact]
    public void Bold_runs_split_and_an_unclosed_marker_stays_as_written()
    {
        Assert.Equal([("Сейчас: ", false), ("стены", true), (" и полы", false)], NoteText.Runs("Сейчас: **стены** и полы"));
        Assert.Equal([("a ** b", false)], NoteText.Runs("a ** b"));
    }

    [Fact]
    public void The_text_falls_back_to_russian_then_to_anything()
    {
        Assert.Equal("ru", NoteText.Pick(new Dictionary<string, string> { ["ru"] = "ru", ["en"] = " " }, "en"));
        Assert.Equal("de", NoteText.Pick(new Dictionary<string, string> { ["de"] = "de" }, "en"));
        Assert.Equal("", NoteText.Pick(new Dictionary<string, string>(), "en"));
    }
}
