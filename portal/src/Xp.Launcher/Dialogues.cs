using Xp.Launcher.Core;

namespace Xp.Launcher;

/// <summary>
/// Private messages (ticket XP-000476) as dialogues in the left column of the chat page (docs/portal/VOICE_IRC.md §3, the
/// "query" of IRC): the conversations of the linked account, one dialogue as lines, a reply, a new message by name, block
/// and complaint. The same mailbox as the site's /me/messages and the same <see cref="PortalClient"/> calls as before; the
/// site owns every rule (limits, blocks, length) and this class passes on the reason it gives. It draws nothing: the page
/// reads the state and listens to the events. Text is text: a message is shown as it was typed.
/// </summary>
public sealed class Dialogues(Settings settings)
{
    static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(30) };

    readonly DeviceStore _store = new(Path.Combine(Settings.Dir, "device.json"));
    readonly MessageWatch _watch = new();
    readonly List<MessageBubble> _bubbles = [];
    int _total, _pages;
    bool _inboxBusy, _threadBusy, _busy;

    /// <summary>The count of unread messages changed (the rail counter and the home notice follow it).</summary>
    public event Action? UnreadChanged;
    /// <summary>The inbox or the open dialogue changed: the page draws it again. The flag: the lines are new, scroll to the end.</summary>
    public event Action<bool>? Changed;
    /// <summary>A line for the page's status row (text, is it a warning).</summary>
    public Action<string?, bool> Status { get; set; } = (_, _) => { };
    /// <summary>The dialogue is in front of the person (the page is on screen): only then what the other wrote is read.</summary>
    public Func<bool> InFront { get; set; } = () => true;
    /// <summary>Who tells the running game about a new private message; null in tests that do not care.</summary>
    public ChatNoticer? Noticer { get; set; }

    public int Unread => _watch.Unread;
    public bool Linked => _store.Load() is not null;
    public List<MessageDialogue> Inbox { get; private set; } = [];
    public Guid? Current { get; private set; }
    public string CurrentName { get; private set; } = "";
    public IReadOnlyList<MessageBubble> Bubbles => _bubbles;
    public int Total => _total;
    public bool IBlocked { get; private set; }
    public bool HasOlder => _bubbles.Count < _total;

    Uri? Portal()
    {
        var url = settings.PortalUrl ?? BuiltIn.Defaults.PortalUrl;
        return Uri.TryCreate(url, UriKind.Absolute, out var uri) ? uri : null;
    }

    /// <summary>The site's page of the open dialogue (or of the mailbox).</summary>
    public string? SiteUrl()
    {
        if (Portal() is not { } p) return null;
        var root = p.AbsoluteUri.TrimEnd('/') + "/me/messages";
        return Current is { } id ? $"{root}/{id}" : root;
    }

    public static string Reason(Exception e) => e switch
    {
        PortalException p when p.Status == 401 => L.T("voice.state.device_unknown"),
        PortalException p when L.Has("msgs.err." + p.Code) => L.T("msgs.err." + p.Code),
        PortalException p when p.Status == 429 => L.T("voice.busy"),
        PortalException p when L.Has("voice.err." + p.Code) => L.T("voice.err." + p.Code),
        PortalException p => L.T("account.error", p.Code),
        _ => L.T("account.offline"),
    };

    public static bool Failed(Exception e) => e is HttpRequestException or TaskCanceledException or PortalException;

    /// <summary>The device key and the client, or null when this launcher is not linked (the chat page says so).</summary>
    (PortalClient Client, string Token)? Site()
    {
        if (_store.Load() is not { } account || Portal() is not { } portal) return null;
        return (new PortalClient(Http, portal), account.Token);
    }

    // ------------------------------------------------------------------ the counter

    /// <summary>
    /// The launcher asks about the unread messages together with the tickets (MainWindow), not on a timer of its own.
    /// True when there are more of them than at the last look. A dead network is silence.
    /// </summary>
    public async Task<bool> LookAsync()
    {
        if (Site() is not { } s)
        {
            Forget();
            return false;
        }
        try
        {
            int n = await s.Client.MessagesUnreadAsync(s.Token, CancellationToken.None);
            bool grew = _watch.Update(n);
            UnreadChanged?.Invoke();
            return grew;
        }
        catch (Exception e) when (Failed(e)) { return false; }
    }

    /// <summary>Not linked or unlinked: no counter, no open dialogue, and everything is a first look again.</summary>
    public void Forget()
    {
        Noticer?.Reset();
        if (Current is not null || Inbox.Count > 0)
        {
            Current = null;
            Inbox = [];
            _bubbles.Clear();
            Changed?.Invoke(false);
        }
        if (_watch.Unread == 0) { _watch.Reset(); return; }
        _watch.Reset();
        UnreadChanged?.Invoke();
    }

    // ------------------------------------------------------------------ the inbox

    public async Task LoadInboxAsync()
    {
        if (_inboxBusy || Site() is not { } s) return;
        _inboxBusy = true;
        try
        {
            var inbox = await s.Client.MessageInboxAsync(s.Token, CancellationToken.None);
            Inbox = inbox.Dialogues;
            _watch.Update(inbox.Unread);
            Noticer?.Inbox(inbox);
            UnreadChanged?.Invoke();
            Changed?.Invoke(false);
            Status(null, false);
        }
        catch (Exception e) when (Failed(e)) { Status(Reason(e), true); }
        finally { _inboxBusy = false; }
    }

    // ------------------------------------------------------------------ one dialogue

    /// <summary>Opens a dialogue (from the list, or after a new message was sent).</summary>
    public async Task OpenAsync(Guid id, string name)
    {
        Current = id;
        CurrentName = name;
        _bubbles.Clear();
        _total = _pages = 0;
        IBlocked = false;
        Changed?.Invoke(true);
        await LoadThreadAsync(merge: false);
    }

    public void Close()
    {
        Current = null;
        _bubbles.Clear();
        Changed?.Invoke(false);
    }

    /// <summary>
    /// Page 1 of the dialogue (the end of the conversation). merge: what is already on screen stays, with only the new
    /// messages added - the page is refreshed under a person who reads further up or types an answer.
    /// </summary>
    public async Task LoadThreadAsync(bool merge)
    {
        if (_threadBusy || Current is not { } id || Site() is not { } s) return;
        _threadBusy = true;
        try
        {
            var t = await s.Client.MessageThreadAsync(s.Token, id, 1, CancellationToken.None);
            if (Current != id) return;
            if (!merge) { _bubbles.Clear(); _pages = 1; }
            bool fresh = Merge(t.Messages);
            _total = t.Total;
            IBlocked = t.IBlocked;
            _pages = Math.Max(_pages, 1);
            CurrentName = t.Person.Name;
            Changed?.Invoke(!merge || fresh);
            await MarkReadAsync(s, id);
        }
        catch (Exception e) when (Failed(e)) { Status(Reason(e), true); }
        finally { _threadBusy = false; }
    }

    public async Task LoadOlderAsync()
    {
        if (_threadBusy || Current is not { } id || Site() is not { } s) return;
        _threadBusy = true;
        try
        {
            var t = await s.Client.MessageThreadAsync(s.Token, id, _pages + 1, CancellationToken.None);
            if (Current != id) return;
            _pages++;
            Merge(t.Messages);
            _total = t.Total;
            Changed?.Invoke(false);
        }
        catch (Exception e) when (Failed(e)) { Status(Reason(e), true); }
        finally { _threadBusy = false; }
    }

    /// <summary>Adds the messages not yet shown and refreshes the read marks; true when something was new.</summary>
    bool Merge(IEnumerable<MessageBubble> got)
    {
        bool added = false;
        foreach (var b in got)
        {
            int i = _bubbles.FindIndex(x => x.Id == b.Id);
            if (i >= 0) _bubbles[i] = b;
            else { _bubbles.Add(b); added = true; }
        }
        // OrderBy is stable: messages of the same second keep the order the site gave them
        var ordered = _bubbles.OrderBy(b => b.At).ToList();
        _bubbles.Clear();
        _bubbles.AddRange(ordered);
        return added;
    }

    /// <summary>The dialogue is in front of the person: what the other wrote is read (the site marks nothing by itself).</summary>
    async Task MarkReadAsync((PortalClient Client, string Token) s, Guid id)
    {
        if (!InFront()) return;
        int waiting = Inbox.FirstOrDefault(d => d.Person.Id == id)?.Unread ?? 0;
        if (waiting == 0 && !_bubbles.Any(b => !b.Mine && !b.Read)) return;
        try
        {
            await s.Client.MessagesReadAsync(s.Token, id, CancellationToken.None);
            _watch.Read(waiting);
            int i = Inbox.FindIndex(d => d.Person.Id == id);
            if (i >= 0) Inbox[i] = Inbox[i] with { Unread = 0 };
            for (int k = 0; k < _bubbles.Count; k++)
                if (!_bubbles[k].Mine) _bubbles[k] = _bubbles[k] with { Read = true };
            Changed?.Invoke(false);
            UnreadChanged?.Invoke();
        }
        catch (Exception e) when (Failed(e)) { }   // the next look tries again
    }

    /// <summary>A line to the open dialogue. False when it was not sent (the reason is in the status).</summary>
    public async Task<bool> SendAsync(string body)
    {
        if (_busy || IBlocked || Current is not { } id || Site() is not { } s || body.Trim().Length == 0) return false;
        _busy = true;
        try
        {
            await s.Client.SendMessageAsync(s.Token, id, body, CancellationToken.None);
            Status(null, false);
        }
        catch (Exception e) when (Failed(e))
        {
            Status(Reason(e), true);
            return false;
        }
        finally { _busy = false; }
        await LoadThreadAsync(merge: true);
        await LoadInboxAsync();
        return true;
    }

    /// <summary>A new message by name (or a profile link): opens the dialogue it started.</summary>
    public async Task<bool> SendToAsync(string who, string body)
    {
        who = who.Trim();
        if (_busy || Site() is not { } s || who.Length == 0 || body.Trim().Length == 0) return false;
        _busy = true;
        MessageSent made;
        try { made = await s.Client.SendMessageToAsync(s.Token, who, body, CancellationToken.None); }
        catch (Exception e) when (Failed(e))
        {
            Status(Reason(e), true);
            return false;
        }
        finally { _busy = false; }
        Status(null, false);
        await OpenAsync(made.To.Id, made.To.Name);
        await LoadInboxAsync();
        return true;
    }

    public async Task SetBlockedAsync(bool block)
    {
        if (Current is not { } id || Site() is not { } s) return;
        try
        {
            if (block)
            {
                await s.Client.BlockPersonAsync(s.Token, id, CancellationToken.None);
                Status(L.T("msgs.blocked", CurrentName), false);
            }
            else
            {
                await s.Client.UnblockPersonAsync(s.Token, id, CancellationToken.None);
                Status(L.T("msgs.unblocked"), false);
            }
        }
        catch (Exception e) when (Failed(e)) { Status(Reason(e), true); return; }
        await LoadThreadAsync(merge: true);
    }

    public async Task ComplainAsync(string text)
    {
        if (Current is not { } id || Site() is not { } s) return;
        try
        {
            var c = await s.Client.ComplainAboutMessagesAsync(s.Token, id, null, text, CancellationToken.None);
            Status(L.T("msgs.complained", c.DisplayNumber), false);
        }
        catch (Exception e) when (Failed(e)) { Status(Reason(e), true); }
    }
}
