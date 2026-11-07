namespace Xp.Portal.Site;

/// <summary>
/// How text is compared when somebody searches.
///
/// PostgreSQL folds case by the collation of the column, and a database created in the C locale
/// folds ASCII and nothing else: there "альф" does not find "Альфа" while "alf" finds "Alfa", so the
/// search looks broken in Russian and fine in English. The ICU collation below folds every language
/// the same way, whatever locale the server happened to be set up in.
/// </summary>
public static class Search
{
    /// <summary>ICU, language-neutral. PostgreSQL ships it in every database built with ICU.</summary>
    public const string Collation = "und-x-icu";
}
