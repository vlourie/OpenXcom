using System.Security.Claims;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.AspNetCore.RateLimiting;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;
using Xp.Portal.Data;
using Xp.Portal.Devices;
using Xp.Portal.Site;
using Xp.Portal.Voice;

namespace Xp.Portal.Pages.Voice;

/// <summary>
/// What every voice page shares: who is asking, and a refusal of <see cref="VoiceService"/> turned into
/// a line on the page. The rules are all in the service; a page only shows them and sends its forms,
/// which carry the antiforgery token the API cannot check for a browser.
/// </summary>
public abstract class VoicePage : PageModel
{
    public List<string> Errors { get; } = new();

    protected Guid Me => Guid.Parse(User.FindFirstValue(ClaimTypes.NameIdentifier)!);

    /// <summary>The text key of a refusal: voice.err.&lt;code&gt; in Strings.</summary>
    public static string ErrorKey(string code) => "voice.err." + code;

    /// <summary>Runs a change; on success shows <paramref name="flash"/> on the page it goes back to, on refusal stays with the reason.</summary>
    protected async Task<IActionResult> ChangeAsync(Func<Task> act, string flash, Func<Task> reload, string back)
    {
        try { await act(); }
        catch (VoiceException e)
        {
            Errors.Add(ErrorKey(e.Code));
            await reload();
            return Page();
        }
        TempData["flash"] = flash;
        return LocalRedirect(back);
    }

    /// <summary>A room link or a bare code: the code is what follows the last slash.</summary>
    public static string RoomCode(string? linkOrCode)
    {
        var s = (linkOrCode ?? "").Trim().TrimEnd('/');
        return s[(s.LastIndexOf('/') + 1)..];
    }
}

/// <summary>
/// Friends: requests both ways, the list, blocks. /me/friends/{id} is a person's own link to hand out:
/// whoever opens it is offered to send that person a request, nothing is sent by opening it.
/// </summary>
[EnableRateLimiting("voice-write")]
public sealed class FriendsModel(VoiceService voice, IOptions<PortalOptions> portal) : VoicePage
{
    public const int PerPage = 100;

    [BindProperty(SupportsGet = true)] public Guid? Add { get; set; }
    [BindProperty(SupportsGet = true)] public int P { get; set; } = 1;
    public FriendsView View { get; private set; } = new([], 0, [], [], []);
    public PersonView? Candidate { get; private set; }
    public string ShareLink { get; private set; } = "";
    public int Pages => Math.Max(1, (View.FriendsTotal + PerPage - 1) / PerPage);

    async Task LoadAsync(CancellationToken ct)
    {
        P = Math.Max(1, P);
        View = await voice.FriendsAsync(Me, P, PerPage, ct);
        ShareLink = $"{portal.Value.PublicUrl.TrimEnd('/')}/me/friends/{Me}";
        if (Add is { } add && add != Me)
        {
            try { Candidate = await voice.PersonAsync(add, ct); }
            catch (VoiceException e) { Errors.Add(ErrorKey(e.Code)); }
        }
    }

    public async Task OnGetAsync(CancellationToken ct) => await LoadAsync(ct);

    public async Task<IActionResult> OnPostRequestAsync(string? who, CancellationToken ct)
    {
        try
        {
            var answer = await voice.RequestAsync(Me, await voice.FindPersonAsync(who, ct), ct);
            TempData["flash"] = answer == "accepted" ? "friends.flash.accepted" : "friends.flash.sent";
            return LocalRedirect("/me/friends");
        }
        catch (VoiceException e)
        {
            Errors.Add(ErrorKey(e.Code));
            await LoadAsync(ct);
            return Page();
        }
    }

    public Task<IActionResult> OnPostAcceptAsync(Guid id, CancellationToken ct) =>
        ChangeAsync(() => voice.AcceptAsync(Me, id, ct), "friends.flash.accepted", () => LoadAsync(ct), "/me/friends");

    public Task<IActionResult> OnPostDeclineAsync(Guid id, CancellationToken ct) =>
        ChangeAsync(() => voice.DeclineAsync(Me, id, ct), "friends.flash.declined", () => LoadAsync(ct), "/me/friends");

    public Task<IActionResult> OnPostCancelAsync(Guid id, CancellationToken ct) =>
        ChangeAsync(() => voice.CancelRequestAsync(Me, id, ct), "friends.flash.cancelled", () => LoadAsync(ct), "/me/friends");

    public Task<IActionResult> OnPostRemoveAsync(Guid user, CancellationToken ct) =>
        ChangeAsync(() => voice.UnfriendAsync(Me, user, ct), "friends.flash.removed", () => LoadAsync(ct), "/me/friends");

    public Task<IActionResult> OnPostBlockAsync(Guid user, CancellationToken ct) =>
        ChangeAsync(() => voice.BlockAsync(Me, user, ct), "friends.flash.blocked", () => LoadAsync(ct), "/me/friends");

    public Task<IActionResult> OnPostUnblockAsync(Guid user, CancellationToken ct) =>
        ChangeAsync(() => voice.UnblockAsync(Me, user, ct), "friends.flash.unblocked", () => LoadAsync(ct), "/me/friends");
}

/// <summary>My rooms and the rooms I am invited to; a new room is made here.</summary>
[EnableRateLimiting("voice-write")]
public sealed class RoomsModel(VoiceService voice) : VoicePage
{
    public IReadOnlyList<RoomSummary> Owned { get; private set; } = [];
    public IReadOnlyList<RoomSummary> Invited { get; private set; } = [];
    public int Incoming { get; private set; }

    async Task LoadAsync(CancellationToken ct)
    {
        (Owned, Invited) = await voice.RoomsAsync(Me, ct);
        Incoming = (await voice.FriendsAsync(Me, 1, 1, ct)).Incoming.Count;
    }

    public async Task OnGetAsync(CancellationToken ct) => await LoadAsync(ct);

    public async Task<IActionResult> OnPostCreateAsync(string? title, CancellationToken ct)
    {
        try
        {
            var room = await voice.CreateRoomAsync(Me, title, ct);
            TempData["flash"] = "voice.flash.created";
            return LocalRedirect($"/voice/rooms/{room.PublicId}");
        }
        catch (VoiceException e)
        {
            Errors.Add(ErrorKey(e.Code));
            await LoadAsync(ct);
            return Page();
        }
    }

    public Task<IActionResult> OnPostDeclineAsync(string? room, CancellationToken ct) =>
        ChangeAsync(() => voice.DeclineInviteAsync(Me, room, ct), "voice.flash.declined", () => LoadAsync(ct), "/voice");
}

/// <summary>
/// One room. An outsider and a room that does not exist get the same 404 page. The owner sees the
/// members and every action on them; a guest sees where they stand, the button that opens the
/// launcher, and the complaint form. Who is inside right now is asked of the media server briefly:
/// a server that does not answer does not hold the page.
/// </summary>
[EnableRateLimiting("voice-write")]
public sealed class RoomModel(VoiceService voice, IOptions<PortalOptions> portal) : VoicePage
{
    static readonly TimeSpan LiveWait = TimeSpan.FromSeconds(3);

    [BindProperty(SupportsGet = true)] public string Room { get; set; } = "";
    public RoomView? View { get; private set; }
    public IReadOnlyList<LiveView> Live { get; private set; } = [];
    public bool LiveDown { get; private set; }
    /// <summary>The owner's friends who have no active invite yet: whom the invite form offers.</summary>
    public List<FriendView> Invitable { get; private set; } = new();
    /// <summary>Whom a complaint can be about: members for the owner, the owner and those inside for a guest.</summary>
    public List<PersonView> Reportable { get; private set; } = new();
    public string Link => $"{portal.Value.PublicUrl.TrimEnd('/')}/voice/rooms/{Room}";
    public string LauncherLink => $"xpiratez://voice/{Room}";
    public Guid MeId => Me;

    async Task LoadAsync(CancellationToken ct)
    {
        // a stranger gets the same 404 on a look and on a change: nothing tells a room from no room
        try { View = await voice.RoomViewAsync(Me, Room, ct); }
        catch (VoiceException)
        {
            View = null;
            Response.StatusCode = StatusCodes.Status404NotFound;
            return;
        }
        if (View.Room.State == "ok")
        {
            using var wait = CancellationTokenSource.CreateLinkedTokenSource(ct);
            wait.CancelAfter(LiveWait);
            try { Live = await voice.LiveAsync(Me, Room, wait.Token); }
            catch (VoiceException) { LiveDown = true; }
            catch (OperationCanceledException) when (!ct.IsCancellationRequested) { LiveDown = true; }
        }
        if (View.Members is { } members)
        {
            var active = members.Where(m => m.Invite == "active").Select(m => m.Person.Id).ToHashSet();
            var friends = await voice.FriendsAsync(Me, 1, VoiceLimits.Friends, ct);
            Invitable = friends.Friends.Where(x => !active.Contains(x.Id)).ToList();
            Reportable = members.Select(m => m.Person).ToList();
        }
        else
        {
            Reportable = Live.Select(l => l.Person).Prepend(View.Room.Owner)
                .Where(p => p.Id != Me).DistinctBy(p => p.Id).ToList();
        }
    }

    public async Task<IActionResult> OnGetAsync(CancellationToken ct)
    {
        await LoadAsync(ct);
        return Page();
    }

    string Back => $"/voice/rooms/{Uri.EscapeDataString(Room)}";

    Task<IActionResult> Do(Func<Task> act, string flash, CancellationToken ct) =>
        ChangeAsync(act, flash, () => LoadAsync(ct), Back);

    public Task<IActionResult> OnPostInviteAsync(Guid user, CancellationToken ct) =>
        Do(() => voice.InviteAsync(Me, Room, user, ct), "voice.flash.invited", ct);

    public Task<IActionResult> OnPostRevokeAsync(Guid user, string? reason, CancellationToken ct) =>
        Do(() => voice.RevokeAsync(Me, Room, user, reason, ct), "voice.flash.revoked", ct);

    public Task<IActionResult> OnPostKickAsync(Guid user, string? reason, CancellationToken ct) =>
        Do(() => voice.KickAsync(Me, Room, user, reason, ct), "voice.flash.kicked", ct);

    public Task<IActionResult> OnPostBanAsync(Guid user, string? reason, CancellationToken ct) =>
        Do(() => voice.BanAsync(Me, Room, user, reason, ct), "voice.flash.banned", ct);

    public Task<IActionResult> OnPostUnbanAsync(Guid user, CancellationToken ct) =>
        Do(() => voice.UnbanAsync(Me, Room, user, ct), "voice.flash.unbanned", ct);

    public Task<IActionResult> OnPostSpeakingAsync(Guid user, bool allowed, string? reason, CancellationToken ct) =>
        Do(() => voice.SetSpeakingAsync(Me, Room, user, allowed, reason, ct), allowed ? "voice.flash.unmuted" : "voice.flash.muted", ct);

    public Task<IActionResult> OnPostCloseAsync(string? reason, CancellationToken ct) =>
        Do(() => voice.CloseRoomAsync(Me, Room, reason, staff: false, ct), "voice.flash.closed", ct);

    public Task<IActionResult> OnPostReopenAsync(CancellationToken ct) =>
        Do(() => voice.ReopenRoomAsync(Me, Room, staff: false, ct), "voice.flash.reopened", ct);

    public async Task<IActionResult> OnPostDeleteAsync(bool sure, CancellationToken ct)
    {
        if (!sure)
        {
            Errors.Add("voice.delete.unsure");
            await LoadAsync(ct);
            return Page();
        }
        return await ChangeAsync(() => voice.DeleteRoomAsync(Me, Room, ct), "voice.flash.deleted", () => LoadAsync(ct), "/voice");
    }

    public Task<IActionResult> OnPostDeclineAsync(CancellationToken ct) =>
        ChangeAsync(() => voice.DeclineInviteAsync(Me, Room, ct), "voice.flash.declined", () => LoadAsync(ct), "/voice");

    public Task<IActionResult> OnPostComplainAsync(Guid user, string? text, CancellationToken ct) =>
        Do(() => voice.ComplainAsync(Me, Room, user, text, ct), "voice.flash.complained", ct);
}

public sealed record AccountBanRow(VoiceAccountBan Ban, string Name, string? Email, string? By);
public sealed record StaffClosedRow(VoiceRoom Room, string Owner, string? By);

/// <summary>
/// The SuperAdmin's voice powers (VOICE_CHAT.md §3): no voice for an account anywhere, and closing any
/// room. Each takes a reason, lands in the room log (VoiceEvent) and in the site's audit.
/// </summary>
public sealed class SuperVoiceModel(PortalDb db, VoiceService voice, Audit audit) : VoicePage
{
    [BindProperty(SupportsGet = true)] public string? Q { get; set; }
    public List<(PortalUser User, bool Banned)> Found { get; } = new();
    public List<AccountBanRow> Bans { get; private set; } = new();
    public List<StaffClosedRow> Closed { get; private set; } = new();

    async Task LoadAsync(CancellationToken ct)
    {
        var bans = await db.VoiceAccountBans.AsNoTracking().Where(b => b.LiftedAt == null).OrderByDescending(b => b.CreatedAt).Take(200).ToListAsync(ct);
        var rooms = await db.VoiceRooms.AsNoTracking().Where(r => r.Status == VoiceRoomStatus.Closed && r.ClosedById != null && r.ClosedById != r.OwnerId)
            .OrderByDescending(r => r.ClosedAt).Take(200).ToListAsync(ct);
        var ids = bans.Select(b => b.UserId).Concat(bans.Where(b => b.ById != null).Select(b => b.ById!.Value))
            .Concat(rooms.Select(r => r.OwnerId)).Concat(rooms.Select(r => r.ClosedById!.Value)).Distinct().ToList();
        var people = await db.Users.AsNoTracking().Where(u => ids.Contains(u.Id)).ToDictionaryAsync(u => u.Id, ct);
        string Name(Guid id) => people.TryGetValue(id, out var u) ? DeviceApi.Display(u) : id.ToString();
        string? Email(Guid id) => people.TryGetValue(id, out var u) ? u.Email : null;
        Bans = bans.Select(b => new AccountBanRow(b, Name(b.UserId), Email(b.UserId), b.ById is { } by ? Email(by) ?? Name(by) : null)).ToList();
        Closed = rooms.Select(r => new StaffClosedRow(r, Name(r.OwnerId), Email(r.ClosedById!.Value))).ToList();

        Found.Clear();
        if (string.IsNullOrWhiteSpace(Q)) return;
        var s = "%" + Q.Trim().Replace("\\", "\\\\").Replace("%", "\\%").Replace("_", "\\_") + "%";
        var users = await db.Users.AsNoTracking().Where(u => EF.Functions.ILike(u.Email!, s) || EF.Functions.ILike(u.DisplayName, s))
            .OrderBy(u => u.Email).Take(50).ToListAsync(ct);
        var banned = bans.Select(b => b.UserId).ToHashSet();
        Found.AddRange(users.Select(u => (u, banned.Contains(u.Id))));
    }

    public async Task OnGetAsync(CancellationToken ct) => await LoadAsync(ct);

    string Back => "/admin/super/voice" + (string.IsNullOrWhiteSpace(Q) ? "" : "?Q=" + Uri.EscapeDataString(Q));

    async Task<string> WhoAsync(Guid user, CancellationToken ct) =>
        await db.Users.Where(u => u.Id == user).Select(u => u.Email).FirstOrDefaultAsync(ct) ?? user.ToString();

    public Task<IActionResult> OnPostBanAsync(Guid user, string? reason, CancellationToken ct) =>
        ChangeAsync(async () =>
        {
            await voice.AccountBanAsync(Me, user, reason, ct);
            audit.Add(Me, "voice.account.ban", await WhoAsync(user, ct), reason);
            await db.SaveChangesAsync(ct);
        }, "super.voice.flash.banned", () => LoadAsync(ct), Back);

    public Task<IActionResult> OnPostLiftAsync(Guid user, CancellationToken ct) =>
        ChangeAsync(async () =>
        {
            await voice.AccountUnbanAsync(Me, user, ct);
            audit.Add(Me, "voice.account.unban", await WhoAsync(user, ct));
            await db.SaveChangesAsync(ct);
        }, "super.voice.flash.lifted", () => LoadAsync(ct), Back);

    public Task<IActionResult> OnPostCloseAsync(string? room, string? reason, CancellationToken ct) =>
        ChangeAsync(async () =>
        {
            var code = RoomCode(room);
            await voice.CloseRoomAsync(Me, code, reason, staff: true, ct);
            audit.Add(Me, "voice.room.close", code, reason);
            await db.SaveChangesAsync(ct);
        }, "super.voice.flash.closed", () => LoadAsync(ct), Back);

    public Task<IActionResult> OnPostReopenAsync(string? room, CancellationToken ct) =>
        ChangeAsync(async () =>
        {
            var code = RoomCode(room);
            await voice.ReopenRoomAsync(Me, code, staff: true, ct);
            audit.Add(Me, "voice.room.reopen", code);
            await db.SaveChangesAsync(ct);
        }, "super.voice.flash.reopened", () => LoadAsync(ct), Back);
}
