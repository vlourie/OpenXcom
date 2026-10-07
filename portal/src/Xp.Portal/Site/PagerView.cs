namespace Xp.Portal.Site;

/// <summary>
/// Page numbers of a long list. Built from the total and the page size so a page never has to do the
/// arithmetic itself, and it shows a window around the current page instead of a thousand links.
/// </summary>
public sealed record PagerView(string BasePath, int Page, int Pages)
{
    public static PagerView Of(string basePath, int page, int total, int perPage) =>
        new(basePath, Math.Max(1, page), Math.Max(1, (total + perPage - 1) / perPage));

    /// <summary>The base path may already carry a query (the chosen wiki group does), hence the check.</summary>
    public string Url(int n) => n <= 1 ? BasePath : $"{BasePath}{(BasePath.Contains('?') ? '&' : '?')}p={n}";

    /// <summary>At most nine numbers, centred on the one being read.</summary>
    public IEnumerable<int> Numbers()
    {
        var from = Math.Max(1, Page - 4);
        var to = Math.Min(Pages, from + 8);
        from = Math.Max(1, to - 8);
        for (var n = from; n <= to; n++) yield return n;
    }
}
