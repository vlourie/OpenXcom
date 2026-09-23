using System.Security.Claims;
using Xp.Portal.Data;

namespace Xp.Portal.Auth;

public static class Roles
{
    public const string User = "User";
    public const string Admin = "Admin";
    public const string SuperAdmin = "SuperAdmin";
    public static readonly string[] All = [User, Admin, SuperAdmin];
}

public static class Categories
{
    public const string Code = "code";
    public const string Graphics = "graphics";
    public const string Balance = "balance";
    public const string Translation = "translation";
    public const string General = "general";
    /// <summary>Order of the form's list. Crash tickets (stage 4) arrive as "code".</summary>
    public static readonly string[] All = [Code, Graphics, Balance, Translation, General];
    public static bool IsValid(string? c) => c is not null && All.Contains(c);
}

public static class Permissions
{
    public const string ClaimType = "xp:perm";
    public const string DocsEdit = "docs.edit";
    public const string RoadmapEdit = "roadmap.edit";
    public const string ReleasesPublish = "releases.publish";
    /// <summary>May write and rename wiki articles, and publish or hide them.</summary>
    public const string WikiEdit = "wiki.edit";
    /// <summary>May pin, lock, move and hide on the forum, and edit somebody else's post.</summary>
    public const string ForumModerate = "forum.moderate";

    public static string ForCategory(string category) => "tickets." + category;
    public static readonly string[] All = [.. Categories.All.Select(ForCategory), DocsEdit, RoadmapEdit, ReleasesPublish, WikiEdit, ForumModerate];
    public static bool IsValid(string p) => All.Contains(p);
}

public static class Policies
{
    /// <summary>Any staff page: Admin or SuperAdmin, signed in with a second factor.</summary>
    public const string Staff = "Staff";
    public const string SuperAdmin = "SuperAdmin";
}

/// <summary>
/// The one place that answers "may this person see / change this ticket". Pages and API both go
/// through it, and queries filter by <see cref="VisibleCategories"/> so a code admin never even
/// loads graphics tickets.
/// </summary>
public sealed class Viewer
{
    public Guid? UserId { get; }
    public bool IsSuperAdmin { get; }
    public bool IsAdmin { get; }
    public IReadOnlySet<string> TicketCategories { get; }

    public Viewer(ClaimsPrincipal p)
    {
        if (p.Identity?.IsAuthenticated == true && Guid.TryParse(p.FindFirstValue(ClaimTypes.NameIdentifier), out var id))
            UserId = id;
        IsSuperAdmin = p.IsInRole(Roles.SuperAdmin);
        IsAdmin = IsSuperAdmin || p.IsInRole(Roles.Admin);
        TicketCategories = IsSuperAdmin
            ? Categories.All.ToHashSet()
            : IsAdmin
                ? Categories.All.Where(c => p.HasClaim(Permissions.ClaimType, Permissions.ForCategory(c))).ToHashSet()
                : new HashSet<string>();
        CanEditWiki = IsSuperAdmin || p.HasClaim(Permissions.ClaimType, Permissions.WikiEdit);
        CanModerateForum = IsSuperAdmin || p.HasClaim(Permissions.ClaimType, Permissions.ForumModerate);
    }

    /// <summary>Wiki and forum rights. A SuperAdmin has them without being granted them one by one.</summary>
    public bool CanEditWiki { get; private init; }
    public bool CanModerateForum { get; private init; }

    public bool IsStaffFor(Ticket t) => TicketCategories.Contains(t.Category);
    public bool IsOwner(Ticket t) => UserId is { } u && t.AuthorId == u;

    /// <summary>Owner, staff of the category, or a guest holding the right secret token.</summary>
    public bool CanRead(Ticket t, string? guestToken) =>
        IsOwner(t) || IsStaffFor(t) || (guestToken is not null && t.GuestTokenHash is not null && GuestTokens.Matches(guestToken, t.GuestTokenHash));

    public IQueryable<Ticket> VisibleToStaff(IQueryable<Ticket> q)
    {
        var cats = TicketCategories.ToArray();
        return q.Where(t => cats.Contains(t.Category));
    }
}
