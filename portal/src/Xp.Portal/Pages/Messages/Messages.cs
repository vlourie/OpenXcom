using System.Security.Claims;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.AspNetCore.RateLimiting;
using Xp.Portal.Data;
using Xp.Portal.Messages;
using Xp.Portal.Voice;

namespace Xp.Portal.Pages.Messages;

/// <summary>
/// What the message pages share: who is asking, and a refusal turned into a line on the page. The
/// rules are all in <see cref="MessageService"/>; the forms carry the antiforgery token.
/// </summary>
public abstract class MessagePage : PageModel
{
    public List<string> Errors { get; } = new();

    protected Guid Me => Guid.Parse(User.FindFirstValue(ClaimTypes.NameIdentifier)!);

    /// <summary>The text key of a refusal: msg.err.&lt;code&gt; in Strings.</summary>
    public static string ErrorKey(string code) => "msg.err." + code;

    /// <summary>Friends and blocks are the voice service's: its refusals keep their own texts.</summary>
    public static string VoiceErrorKey(string code) => "voice.err." + code;
}

/// <summary>My dialogues, the unread count, a new message to anybody (by name or profile link), and the e-mail setting.</summary>
[EnableRateLimiting("messages-write")]
public sealed class InboxModel(MessageService messages, VoiceService voice) : MessagePage
{
    public IReadOnlyList<DialogueRow> Dialogues { get; private set; } = [];
    public IReadOnlyList<FriendView> Friends { get; private set; } = [];
    public bool EmailNotice { get; private set; }
    public string? Who { get; private set; }
    public string? Draft { get; private set; }

    async Task LoadAsync(CancellationToken ct)
    {
        Dialogues = await messages.InboxAsync(Me, ct);
        Friends = (await voice.FriendsAsync(Me, 1, VoiceLimits.Friends, ct)).Friends;
        EmailNotice = await messages.EmailNoticeAsync(Me, ct);
    }

    public async Task OnGetAsync(CancellationToken ct) => await LoadAsync(ct);

    public async Task<IActionResult> OnPostSendAsync(string? who, string? body, CancellationToken ct)
    {
        try
        {
            var to = await voice.FindPersonAsync(who, ct);
            await messages.SendAsync(Me, to, body, ct);
            return LocalRedirect($"/me/messages/{to}");
        }
        catch (VoiceException e) { Errors.Add(VoiceErrorKey(e.Code)); }
        catch (MessageException e) { Errors.Add(ErrorKey(e.Code)); }
        Who = who;
        Draft = body;
        await LoadAsync(ct);
        return Page();
    }

    public async Task<IActionResult> OnPostNoticeAsync(bool on, CancellationToken ct)
    {
        await messages.SetEmailNoticeAsync(Me, on, ct);
        TempData["flash"] = on ? "msg.flash.notice_on" : "msg.flash.notice_off";
        return LocalRedirect("/me/messages");
    }
}

/// <summary>One dialogue as a feed. A stranger's id and an id that is no user get the same 404.</summary>
[EnableRateLimiting("messages-write")]
public sealed class ThreadModel(MessageService messages, VoiceService voice) : MessagePage
{
    public Guid Id { get; private set; }
    public int P { get; private set; } = 1;
    public ThreadView? View { get; private set; }
    public string? Draft { get; private set; }
    public int Pages => View is null ? 1 : Math.Max(1, (View.Total + MessageLimits.PerPage - 1) / MessageLimits.PerPage);

    async Task<bool> LoadAsync(Guid id, int p, CancellationToken ct)
    {
        Id = id;
        P = Math.Max(1, p);
        if (id == Me) return false;
        try { View = await messages.ThreadAsync(Me, id, P, ct); }
        catch (MessageException) { return false; }
        return true;
    }

    public async Task<IActionResult> OnGetAsync(Guid id, int p, CancellationToken ct) =>
        await LoadAsync(id, p, ct) ? Page() : NotFound();

    /// <summary>Runs a change; on success goes back to the dialogue with a flash, on refusal stays with the reason.</summary>
    async Task<IActionResult> ChangeAsync(Guid id, Func<Task> act, string flash, string? draft, CancellationToken ct)
    {
        try
        {
            await act();
            if (flash.Length > 0) TempData["flash"] = flash;
            return LocalRedirect($"/me/messages/{id}");
        }
        catch (MessageException e) { Errors.Add(ErrorKey(e.Code)); }
        catch (VoiceException e) { Errors.Add(VoiceErrorKey(e.Code)); }
        if (!await LoadAsync(id, 1, ct)) return NotFound();
        Draft = draft;
        return Page();
    }

    public Task<IActionResult> OnPostSendAsync(Guid id, string? body, CancellationToken ct) =>
        ChangeAsync(id, () => messages.SendAsync(Me, id, body, ct), "", body, ct);

    public Task<IActionResult> OnPostDeleteAsync(Guid id, Guid message, CancellationToken ct) =>
        ChangeAsync(id, () => messages.DeleteAsync(Me, message, ct), "msg.flash.deleted", null, ct);

    public Task<IActionResult> OnPostBlockAsync(Guid id, CancellationToken ct) =>
        ChangeAsync(id, () => voice.BlockAsync(Me, id, ct), "msg.flash.blocked", null, ct);

    public Task<IActionResult> OnPostUnblockAsync(Guid id, CancellationToken ct) =>
        ChangeAsync(id, () => voice.UnblockAsync(Me, id, ct), "msg.flash.unblocked", null, ct);

    public Task<IActionResult> OnPostComplainAsync(Guid id, Guid? message, string? text, CancellationToken ct) =>
        ChangeAsync(id, () => messages.ComplainAsync(Me, id, message, text, ct), "msg.flash.complained", null, ct);
}

/// <summary>
/// The link at the bottom of the letter. It works without signing in (the signature in it is the proof)
/// and does the one thing it says. Asking is enough: a letter-reader that opens links ahead of time can
/// only turn off letters that a person asked to stop, never turn anything on.
/// </summary>
public sealed class UnsubscribeModel(MessageService messages) : PageModel
{
    public bool Done { get; private set; }

    public async Task OnGetAsync(Guid u, string? sig, CancellationToken ct) => Done = await messages.UnsubscribeAsync(u, sig, ct);
}
