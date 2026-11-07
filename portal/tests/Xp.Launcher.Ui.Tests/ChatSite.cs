using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Text.RegularExpressions;

namespace Xp.Launcher.Ui.Tests;

/// <summary>
/// The site for the chat section: a listener on localhost that answers from a script (channels, a feed, private messages, the
/// voice lobby) and writes down every call. What the tests change while it runs are the public fields.
/// </summary>
public sealed class ChatSite : IDisposable
{
    public static readonly Guid Ann = Guid.Parse("11111111-1111-1111-1111-111111111111");
    public static readonly Guid Bob = Guid.Parse("22222222-2222-2222-2222-222222222222");
    public static readonly Guid Cat = Guid.Parse("33333333-3333-3333-3333-333333333333");
    public static readonly Guid Me = Guid.Parse("99999999-9999-9999-9999-999999999999");

    public const string Evil = "Привет <b>всем</b> https://evil.test/x";

    readonly HttpListener _site = new();
    readonly List<string> _calls = [];

    public string Url { get; }
    public volatile int Unread = 2;
    public volatile bool More;                 // the feed of #общий has a new line after the cursor
    public volatile int LineId = 13;           // its number: a feed asked after it gives the line only if the cursor is below
    public volatile bool MoreMention;          // the new line names the player
    public volatile int GeneralMentions = 1;
    public volatile int GeneralUnread = 2;
    public volatile bool NewPrivate;           // Anna wrote once more
    public volatile bool Blocked;              // I blocked Boris

    public ChatSite()
    {
        var probe = new TcpListener(IPAddress.Loopback, 0);
        probe.Start();
        int port = ((IPEndPoint)probe.LocalEndpoint).Port;
        probe.Stop();
        Url = $"http://localhost:{port}/";
        _site.Prefixes.Add(Url);
        _site.Start();
        _ = Task.Run(Serve);
    }

    public void Dispose()
    {
        try { _site.Stop(); } catch (ObjectDisposedException) { }
    }

    public string[] Calls { get { lock (_calls) return [.. _calls]; } }

    /// <summary>A call that starts so (the sent body compared with its \u escapes read).</summary>
    public bool Called(string call) { lock (_calls) return _calls.Any(c => Regex.Unescape(c).StartsWith(call, StringComparison.Ordinal)); }

    public int Count(string call) { lock (_calls) return _calls.Count(c => Regex.Unescape(c).StartsWith(call, StringComparison.Ordinal)); }

    static string Person(Guid id, string name) => $"{{\"id\":\"{id}\",\"name\":\"{name}\"}}";
    static string Json(string s) => System.Text.Json.JsonSerializer.Serialize(s);
    static string Now(int minutes = 0) => DateTime.UtcNow.AddMinutes(minutes).ToString("o");

    string Channels() =>
        "{\"channels\":[" +
        $"{{\"room\":\"ch-general\",\"title\":\"#общий\",\"topic\":\"Общий разговор об X-Piratez. Будьте вежливы.\",\"isPublic\":true,\"mine\":false,\"owner\":{Person(Me, "X-Piratez")},\"state\":\"ok\",\"joined\":true,\"here\":3,\"unread\":{GeneralUnread},\"mentions\":{GeneralMentions},\"lastId\":12}}," +
        $"{{\"room\":\"ch-english\",\"title\":\"#english\",\"topic\":\"General chat\",\"isPublic\":true,\"mine\":false,\"owner\":{Person(Me, "X-Piratez")},\"state\":\"ok\",\"joined\":false,\"here\":0,\"unread\":0,\"mentions\":0,\"lastId\":0}}," +
        $"{{\"room\":\"ch-pomosch\",\"title\":\"#помощь\",\"topic\":null,\"isPublic\":true,\"mine\":false,\"owner\":{Person(Me, "X-Piratez")},\"state\":\"ok\",\"joined\":false,\"here\":0,\"unread\":0,\"mentions\":0,\"lastId\":0}}]," +
        $"\"rooms\":[{{\"room\":\"cabin\",\"title\":\"Моя каюта\",\"topic\":null,\"isPublic\":false,\"mine\":true,\"owner\":{Person(Me, "Капитан")},\"state\":\"ok\",\"joined\":true,\"here\":1,\"unread\":0,\"mentions\":0,\"lastId\":0}}]}}";

    string Feed(string query)
    {
        var m = Regex.Match(query, @"after=(\d+)");
        bool after = m.Success;
        bool fresh = after && More && LineId > long.Parse(m.Groups[1].Value);
        var lines = after
            ? (fresh ? $"{{\"id\":{LineId},\"kind\":\"text\",\"event\":null,\"author\":{Person(Bob, "Борис")},\"body\":\"новая строка\",\"at\":\"{Now()}\",\"mine\":false,\"mention\":{(MoreMention ? "true" : "false")}}}" : "")
            : $"{{\"id\":10,\"kind\":\"text\",\"event\":null,\"author\":{Person(Ann, "Анна")},\"body\":{Json(Evil)},\"at\":\"{Now(-5)}\",\"mine\":false,\"mention\":true}}," +
              $"{{\"id\":11,\"kind\":\"system\",\"event\":\"join\",\"author\":{Person(Bob, "Борис")},\"body\":\"\",\"at\":\"{Now(-4)}\",\"mine\":false,\"mention\":false}}," +
              $"{{\"id\":12,\"kind\":\"action\",\"event\":null,\"author\":{Person(Bob, "Борис")},\"body\":\"машет рукой\",\"at\":\"{Now(-3)}\",\"mine\":false,\"mention\":false}}";
        long last = fresh ? LineId : after ? long.Parse(m.Groups[1].Value) : 12;
        return $"{{\"room\":\"ch-general\",\"title\":\"#общий\",\"topic\":\"Общий разговор об X-Piratez. Будьте вежливы.\",\"isPublic\":true,\"canModerate\":false,\"canTalk\":true,\"last\":{last}," +
               $"\"lines\":[{lines}],\"removed\":[],\"attendees\":[" +
               $"{{\"person\":{Person(Ann, "Анна")},\"operator\":true,\"voice\":false,\"muted\":false}}," +
               $"{{\"person\":{Person(Bob, "Борис")},\"operator\":false,\"voice\":true,\"muted\":false}}," +
               $"{{\"person\":{Person(Cat, "Катя")},\"operator\":false,\"voice\":false,\"muted\":true}}]}}";
    }

    static string EmptyFeed(string room, string title) =>
        $"{{\"room\":\"{room}\",\"title\":\"{title}\",\"topic\":\"General chat\",\"isPublic\":true,\"canModerate\":false,\"canTalk\":true,\"last\":0,\"lines\":[],\"removed\":[],\"attendees\":[]}}";

    string Inbox()
    {
        var annAt = NewPrivate ? Now(1) : "2026-11-02T10:00:00Z";
        var annPreview = NewPrivate ? "Новое сообщение" : "Привет <b>там</b> https://evil.test/x";
        int unread = NewPrivate ? Unread : Unread;
        return $"{{\"unread\":{unread},\"dialogues\":[" +
               $"{{\"person\":{Person(Ann, "Анна")},\"preview\":{Json(annPreview)},\"lastMine\":false,\"at\":\"{annAt}\",\"unread\":{unread}}}," +
               $"{{\"person\":{Person(Bob, "Борис")},\"preview\":\"Ладно\",\"lastMine\":true,\"at\":\"2026-11-01T10:00:00Z\",\"unread\":0}}]}}";
    }

    string Thread(Guid id, string name, bool blocked) =>
        $"{{\"person\":{Person(id, name)},\"total\":2,\"page\":1,\"perPage\":50,\"iBlocked\":{(blocked ? "true" : "false")},\"friend\":true,\"messages\":[" +
        $"{{\"id\":\"aaaaaaaa-0000-0000-0000-000000000001\",\"mine\":true,\"body\":\"Здравствуй\",\"at\":\"2026-11-02T09:00:00Z\",\"read\":true}}," +
        $"{{\"id\":\"aaaaaaaa-0000-0000-0000-000000000002\",\"mine\":false,\"body\":{Json(Evil)},\"at\":\"2026-11-02T10:00:00Z\",\"read\":false}}]}}";

    const string Sent = "{\"id\":\"bbbbbbbb-0000-0000-0000-000000000001\",\"to\":{\"id\":\"11111111-1111-1111-1111-111111111111\",\"name\":\"Анна\"},\"at\":\"2026-11-02T11:00:00Z\"}";

    async Task Serve()
    {
        while (_site.IsListening)
        {
            HttpListenerContext ctx;
            try { ctx = await _site.GetContextAsync(); } catch (Exception) { return; }
            var path = ctx.Request.Url!.AbsolutePath;
            var query = ctx.Request.Url.Query;
            var method = ctx.Request.HttpMethod;
            string sent = new StreamReader(ctx.Request.InputStream).ReadToEnd();
            lock (_calls) _calls.Add($"{method} {path}{query} {sent}".TrimEnd());
            string body = ""; int status = 204;
            var text = sent.Length > 0 ? Regex.Unescape(sent) : "";
            if (ctx.Request.Headers["X-Device-Token"] != "tok-v") { status = 401; body = "{\"error\":\"device_unknown\"}"; }
            else if (method == "GET" && path == "/api/v1/voice/channels") (status, body) = (200, Channels());
            else if (method == "GET" && path == "/api/v1/voice/rooms/ch-general/messages") (status, body) = (200, Feed(query));
            else if (method == "GET" && path == "/api/v1/voice/rooms/ch-english/messages") (status, body) = (200, EmptyFeed("ch-english", "#english"));
            else if (method == "GET" && path == "/api/v1/voice/rooms/cabin/messages") (status, body) = (200, EmptyFeed("cabin", "Моя каюта"));
            else if (method == "POST" && path == "/api/v1/voice/rooms/ch-general/messages")
            {
                // what the site does with a line: a command it knows is done, one it does not is "unknown" and is not a message
                if (text.Contains("\"text\":\"/dance"))
                    (status, body) = (200, "{\"result\":\"unknown\",\"line\":null,\"command\":\"/dance\",\"person\":null,\"text\":null}");
                else if (text.Contains("\"text\":\"/msg"))
                    (status, body) = (200, $"{{\"result\":\"private\",\"line\":null,\"command\":\"msg\",\"person\":{Person(Bob, "Борис")},\"text\":null}}");
                else
                {
                    var typed = System.Text.Json.JsonDocument.Parse(sent).RootElement.GetProperty("text").GetString() ?? "";
                    (status, body) = (200, $"{{\"result\":\"posted\",\"line\":{{\"id\":14,\"kind\":\"text\",\"event\":null,\"author\":{Person(Me, "Капитан")},\"body\":{Json(typed)},\"at\":\"{Now()}\",\"mine\":true,\"mention\":false}},\"command\":null,\"person\":null,\"text\":null}}");
                }
            }
            else if (method == "POST" && path.StartsWith("/api/v1/voice/rooms/") && (path.EndsWith("/join") || path.EndsWith("/part"))) { }
            else if (method == "GET" && path == "/api/v1/messages/unread") (status, body) = (200, $"{{\"unread\":{Unread}}}");
            else if (method == "GET" && path == "/api/v1/messages") (status, body) = (200, Inbox());
            else if (method == "GET" && path == $"/api/v1/messages/{Ann}") (status, body) = (200, Thread(Ann, "Анна", false));
            else if (method == "GET" && path == $"/api/v1/messages/{Bob}") (status, body) = (200, Thread(Bob, "Борис", Blocked));
            else if (method == "POST" && path == $"/api/v1/messages/{Ann}/read") Unread = 0;
            else if (method == "POST" && (path == $"/api/v1/messages/{Ann}" || path == "/api/v1/messages")) (status, body) = (201, Sent);
            else if (method == "PUT" && path == $"/api/v1/blocks/{Bob}") Blocked = true;
            else if (method == "DELETE" && path == $"/api/v1/blocks/{Bob}") Blocked = false;
            else if (method == "GET" && path == "/api/v1/voice/rooms") (status, body) = (200, "{\"owned\":[],\"invited\":[]}");
            else if (method == "GET" && path == "/api/v1/voice/lobby") (status, body) = (200, "{\"online\":[],\"rooms\":[],\"requests\":[]}");
            else if (path is "/api/v1/voice/presence") { }
            else { status = 404; body = "{\"error\":\"not_found\"}"; }
            var bytes = Encoding.UTF8.GetBytes(body);
            ctx.Response.StatusCode = status;
            if (bytes.Length > 0) ctx.Response.ContentType = "application/json";
            await ctx.Response.OutputStream.WriteAsync(bytes);
            ctx.Response.Close();
        }
    }
}
