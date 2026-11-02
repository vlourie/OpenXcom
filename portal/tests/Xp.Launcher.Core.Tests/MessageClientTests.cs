using System.Net;
using System.Text.Json;

namespace Xp.Launcher.Core.Tests;

/// <summary>The launcher's calls for private messages (ticket XP-000476) against a fake site, and the unread counter.</summary>
public sealed class MessageClientTests
{
    const string Token = "device-token-0123456789";
    static readonly Guid Ann = Guid.Parse("11111111-1111-1111-1111-111111111111");
    readonly FakeVoiceSite _site = new();
    readonly PortalClient _portal;

    public MessageClientTests() => _portal = new PortalClient(new HttpClient(_site), new Uri("https://portal.test"));

    [Fact]
    public async Task The_counter_and_the_inbox_are_read_under_the_device_key()
    {
        _site.Answers["GET /api/v1/messages/unread"] = (HttpStatusCode.OK, """{"unread":3}""");
        _site.Answers["GET /api/v1/messages"] = (HttpStatusCode.OK, """
            {"unread":3,"dialogues":[{"person":{"id":"11111111-1111-1111-1111-111111111111","name":"Анна"},
              "preview":"Привет <b>там</b>","lastMine":false,"at":"2026-11-02T10:00:00+00:00","unread":3}]}
            """);

        Assert.Equal(3, await _portal.MessagesUnreadAsync(Token, default));
        var inbox = await _portal.MessageInboxAsync(Token, default);

        Assert.Equal(3, inbox.Unread);
        var d = Assert.Single(inbox.Dialogues);
        Assert.Equal(Ann, d.Person.Id);
        Assert.Equal("Анна", d.Person.Name);
        Assert.Equal("Привет <b>там</b>", d.Preview);   // as typed: the launcher draws text, never markup
        Assert.Equal(3, d.Unread);
        Assert.All(_site.Seen, s => Assert.Equal(Token, s.Token));
    }

    [Fact]
    public async Task A_thread_page_is_read_without_marking_and_reading_is_a_call_of_its_own()
    {
        _site.Answers[$"GET /api/v1/messages/{Ann}?page=2"] = (HttpStatusCode.OK, """
            {"person":{"id":"11111111-1111-1111-1111-111111111111","name":"Анна"},"total":60,"page":2,"perPage":50,"iBlocked":true,"friend":true,
             "messages":[{"id":"22222222-2222-2222-2222-222222222222","mine":true,"body":"первое","at":"2026-11-01T10:00:00Z","read":true}]}
            """);
        _site.Answers[$"POST /api/v1/messages/{Ann}/read"] = (HttpStatusCode.NoContent, "");

        var t = await _portal.MessageThreadAsync(Token, Ann, 2, default);
        await _portal.MessagesReadAsync(Token, Ann, default);

        Assert.Equal(2, t.Pages);
        Assert.True(t.IBlocked);
        Assert.True(t.Friend);
        Assert.True(Assert.Single(t.Messages).Mine);
        Assert.Equal(2, _site.Seen.Count);
        Assert.DoesNotContain(_site.Seen, s => s.Line.EndsWith("page=1") && s.Line.StartsWith("POST"));
    }

    [Fact]
    public async Task Sending_goes_by_id_or_by_name_and_the_text_is_not_touched()
    {
        var sent = """{"id":"33333333-3333-3333-3333-333333333333","to":{"id":"11111111-1111-1111-1111-111111111111","name":"Анна"},"at":"2026-11-02T10:00:00Z"}""";
        _site.Answers[$"POST /api/v1/messages/{Ann}"] = (HttpStatusCode.Created, sent);
        _site.Answers["POST /api/v1/messages"] = (HttpStatusCode.Created, sent);

        var a = await _portal.SendMessageAsync(Token, Ann, "строка 1\nстрока 2 https://x.test", default);
        var b = await _portal.SendMessageToAsync(Token, "  Анна ", "привет", default);

        Assert.Equal("Анна", a.To.Name);
        Assert.Equal(Ann, b.To.Id);
        Assert.Equal("строка 1\nстрока 2 https://x.test", JsonDocument.Parse(_site.Seen[0].Body!).RootElement.GetProperty("body").GetString());
        var by = JsonDocument.Parse(_site.Seen[1].Body!).RootElement;
        Assert.Equal("Анна", by.GetProperty("who").GetString());
        Assert.Equal("привет", by.GetProperty("body").GetString());
    }

    [Fact]
    public async Task A_refusal_carries_the_sites_reason_and_the_limits_are_429()
    {
        _site.Problem($"POST /api/v1/messages/{Ann}", HttpStatusCode.TooManyRequests, "limit_unanswered");
        var e = await Assert.ThrowsAsync<PortalException>(() => _portal.SendMessageAsync(Token, Ann, "ещё", default));
        Assert.Equal("limit_unanswered", e.Code);
        Assert.Equal(429, e.Status);
    }

    [Fact]
    public async Task Complaint_and_block_use_the_sites_routes()
    {
        _site.Answers[$"POST /api/v1/messages/{Ann}/complaints"] = (HttpStatusCode.Created, """{"number":42,"displayNumber":"XP-000042"}""");
        _site.Answers[$"PUT /api/v1/blocks/{Ann}"] = (HttpStatusCode.NoContent, "");
        _site.Answers[$"DELETE /api/v1/blocks/{Ann}"] = (HttpStatusCode.NoContent, "");
        var message = Guid.NewGuid();

        var c = await _portal.ComplainAboutMessagesAsync(Token, Ann, message, " оскорбляет ", default);
        await _portal.BlockPersonAsync(Token, Ann, default);
        await _portal.UnblockPersonAsync(Token, Ann, default);

        Assert.Equal("XP-000042", c.DisplayNumber);
        var body = JsonDocument.Parse(_site.Seen[0].Body!).RootElement;
        Assert.Equal(message, body.GetProperty("message").GetGuid());
        Assert.Equal("оскорбляет", body.GetProperty("text").GetString());
        Assert.Equal(3, _site.Seen.Count);
    }

    [Fact]
    public void The_counter_calls_for_a_notice_only_when_it_grew_after_the_first_look()
    {
        var w = new MessageWatch();
        Assert.False(w.Update(5));           // what waited at the start is on the button, not news
        Assert.Equal(5, w.Unread);
        Assert.False(w.Update(5));
        Assert.True(w.Update(6));
        Assert.False(w.Update(2));           // read on the site
        Assert.True(w.Update(3));

        w.Read(2);                            // read here: down at once, and the next answer is compared with that
        Assert.Equal(1, w.Unread);
        Assert.False(w.Update(1));
        Assert.True(w.Update(2));

        w.Reset();                            // unlinked
        Assert.Equal(0, w.Unread);
        Assert.False(w.Update(9));
        Assert.False(w.Update(-4));
        Assert.Equal(0, w.Unread);
    }
}
