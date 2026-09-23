using System.Security.Cryptography;
using System.Text;
using Microsoft.AspNetCore.WebUtilities;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;
using Xp.Portal.Data;
using Xp.Portal.Tickets;

namespace Xp.Portal.Files;

public sealed class AttachmentOptions
{
    public const string Section = "Attachments";
    /// <summary>Folder for uploaded files. Must be outside wwwroot; checked at start-up.</summary>
    public string StorageRoot { get; set; } = "";
    public long MaxFileBytes { get; set; } = 32L * 1024 * 1024;
    public long MaxZipBytes { get; set; } = 64L * 1024 * 1024;
    public int MaxFilesPerTicket { get; set; } = 10;
    public long MaxBytesPerTicket { get; set; } = 128L * 1024 * 1024;
    /// <summary>clamd address "host:port"; empty = no scanning, files are marked Unscanned.</summary>
    public string ClamdAddress { get; set; } = "";
    public int SignedUrlMinutes { get; set; } = 5;
}

public enum FileKind { Png, Jpeg, Webp, Text, Save, Zip }

/// <summary>What may be attached. The extension picks the rule, the first bytes must then agree with it.</summary>
public static class FileRules
{
    static readonly Dictionary<string, FileKind> ByExt = new(StringComparer.OrdinalIgnoreCase)
    {
        [".png"] = FileKind.Png, [".jpg"] = FileKind.Jpeg, [".jpeg"] = FileKind.Jpeg, [".webp"] = FileKind.Webp,
        [".txt"] = FileKind.Text, [".log"] = FileKind.Text,
        // OpenXcom saves are YAML text: normal, auto- and quick-saves
        [".sav"] = FileKind.Save, [".asav"] = FileKind.Save,
        [".zip"] = FileKind.Zip,
    };

    public static IEnumerable<string> Extensions => ByExt.Keys;

    public static FileKind? KindOf(string fileName) => ByExt.TryGetValue(Path.GetExtension(fileName), out var k) ? k : null;

    public static string ContentType(FileKind k) => k switch
    {
        FileKind.Png => "image/png",
        FileKind.Jpeg => "image/jpeg",
        FileKind.Webp => "image/webp",
        FileKind.Text or FileKind.Save => "text/plain",
        FileKind.Zip => "application/zip",
        _ => "application/octet-stream",
    };

    public static bool IsImage(FileKind k) => k is FileKind.Png or FileKind.Jpeg or FileKind.Webp;

    /// <summary>Checks the head of the file (up to 8 KiB) against the declared kind.</summary>
    public static bool HeadMatches(FileKind k, ReadOnlySpan<byte> head) => k switch
    {
        FileKind.Png => head.StartsWith((ReadOnlySpan<byte>)[0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]),
        FileKind.Jpeg => head.StartsWith((ReadOnlySpan<byte>)[0xFF, 0xD8, 0xFF]),
        FileKind.Webp => head.Length >= 12 && head[..4].SequenceEqual("RIFF"u8) && head[8..12].SequenceEqual("WEBP"u8),
        FileKind.Zip => head.StartsWith("PK\x03\x04"u8) || head.StartsWith("PK\x05\x06"u8),
        // text: no NUL bytes and valid UTF-8 (a cut multi-byte sequence at the very end is fine)
        FileKind.Text or FileKind.Save => head.IndexOf((byte)0) < 0 && LooksUtf8(head),
        _ => false,
    };

    static bool LooksUtf8(ReadOnlySpan<byte> b)
    {
        var dec = new UTF8Encoding(false, throwOnInvalidBytes: true).GetDecoder();
        try { dec.GetCharCount(b, flush: false); return true; }
        catch (DecoderFallbackException) { return false; }
    }

    /// <summary>Keeps letters, digits, space, dot, dash and underscore; the result is for display only.</summary>
    public static string SafeName(string name)
    {
        name = Path.GetFileName(name.Replace('\\', '/'));
        var sb = new StringBuilder();
        foreach (var ch in name)
            sb.Append(char.IsLetterOrDigit(ch) || ch is '.' or '-' or '_' or ' ' ? ch : '_');
        var s = sb.ToString().Trim(' ', '.');
        if (s.Length == 0) s = "file";
        if (s.Length > Limits.FileNameMax)
        {
            var ext = Path.GetExtension(s);
            s = s[..(Limits.FileNameMax - ext.Length)] + ext;
        }
        return s;
    }
}

/// <summary>Files live under generated keys in a folder outside the web root; nothing there is ever served directly.</summary>
public sealed class ObjectStore(IOptions<AttachmentOptions> options)
{
    string Root => options.Value.StorageRoot;

    public static string NewKey() => Convert.ToHexStringLower(RandomNumberGenerator.GetBytes(16));

    string PathOf(string key)
    {
        if (key.Length != 32 || !key.All(Uri.IsHexDigit)) throw new ArgumentException("bad object key");
        return Path.Combine(Root, key[..2], key);
    }

    public Stream Create(string key)
    {
        var p = PathOf(key);
        Directory.CreateDirectory(Path.GetDirectoryName(p)!);
        return new FileStream(p, FileMode.CreateNew, FileAccess.Write, FileShare.None, 81920, FileOptions.Asynchronous);
    }

    public Stream OpenRead(string key) => new FileStream(PathOf(key), FileMode.Open, FileAccess.Read, FileShare.Read, 81920, FileOptions.Asynchronous);

    public void Delete(string key)
    {
        try { File.Delete(PathOf(key)); } catch (IOException) { }
    }
}

public sealed class AttachmentService(PortalDb db, ObjectStore store, IOptions<AttachmentOptions> options, TimeProvider clock)
{
    /// <summary>
    /// Streams one file into storage: the body is never held in memory, the size is counted as it
    /// arrives and the upload is cut off at the limit, the head is checked against the extension.
    /// </summary>
    public async Task<TicketAttachment> AddAsync(Ticket t, string fileName, Stream body, CancellationToken ct)
    {
        var o = options.Value;
        var kind = FileRules.KindOf(fileName) ?? throw new TicketException("file_type_not_allowed", "this file type is not allowed");
        var limit = kind == FileKind.Zip ? o.MaxZipBytes : o.MaxFileBytes;
        var existing = await db.TicketAttachments.Where(a => a.TicketId == t.Id).GroupBy(_ => 1)
            .Select(g => new { N = g.Count(), Bytes = g.Sum(a => a.Size) }).FirstOrDefaultAsync(ct);
        if ((existing?.N ?? 0) >= o.MaxFilesPerTicket) throw new TicketException("too_many_files", "too many files on this ticket");
        var roomLeft = o.MaxBytesPerTicket - (existing?.Bytes ?? 0);

        var key = ObjectStore.NewKey();
        long size = 0;
        using var sha = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        try
        {
            await using (var dst = store.Create(key))
            {
                var buf = new byte[81920];
                var head = new byte[8192];
                int headLen = 0;
                int n;
                while ((n = await body.ReadAsync(buf, ct)) > 0)
                {
                    size += n;
                    if (size > limit) throw new TicketException("file_too_large", "the file is too large");
                    if (size > roomLeft) throw new TicketException("ticket_files_too_large", "the ticket's files are too large in total");
                    if (headLen < head.Length)
                    {
                        var take = Math.Min(n, head.Length - headLen);
                        Array.Copy(buf, 0, head, headLen, take);
                        headLen += take;
                        // decide as soon as the head is complete, before storing megabytes of a fake file
                        if (headLen == head.Length && !FileRules.HeadMatches(kind, head))
                            throw new TicketException("file_content_mismatch", "the file content does not match its type");
                    }
                    sha.AppendData(buf, 0, n);
                    await dst.WriteAsync(buf.AsMemory(0, n), ct);
                }
                if (size == 0) throw new TicketException("file_empty", "the file is empty");
                if (headLen < head.Length && !FileRules.HeadMatches(kind, head.AsSpan(0, headLen)))
                    throw new TicketException("file_content_mismatch", "the file content does not match its type");
            }
        }
        catch
        {
            store.Delete(key);
            throw;
        }

        var a = new TicketAttachment
        {
            TicketId = t.Id,
            ObjectKey = key,
            FileName = FileRules.SafeName(fileName),
            ContentType = FileRules.ContentType(kind),
            Size = size,
            Sha256 = Convert.ToHexStringLower(sha.GetHashAndReset()),
            Scan = ScanStatus.Pending,
            CreatedAt = clock.GetUtcNow(),
        };
        db.TicketAttachments.Add(a);
        db.TicketHistory.Add(new TicketHistory { TicketId = t.Id, Action = "attachment", To = a.FileName, At = a.CreatedAt });
        t.UpdatedAt = a.CreatedAt;
        await db.SaveChangesAsync(ct);
        return a;
    }
}

/// <summary>Short-lived links to one attachment. The file endpoint still re-checks who is asking.</summary>
public sealed class SignedUrls(IOptions<PortalOptions> portal, IOptions<AttachmentOptions> files, TimeProvider clock)
{
    public string For(TicketAttachment a)
    {
        var exp = clock.GetUtcNow().AddMinutes(files.Value.SignedUrlMinutes).ToUnixTimeSeconds();
        return $"/files/{a.Id}?exp={exp}&sig={Sign(a.Id, exp)}";
    }

    public bool Valid(Guid id, long exp, string? sig)
    {
        if (sig is null || exp < clock.GetUtcNow().ToUnixTimeSeconds()) return false;
        return CryptographicOperations.FixedTimeEquals(Encoding.ASCII.GetBytes(Sign(id, exp)), Encoding.ASCII.GetBytes(sig));
    }

    string Sign(Guid id, long exp) =>
        WebEncoders.Base64UrlEncode(HMACSHA256.HashData(portal.Value.SecretBytes(), Encoding.UTF8.GetBytes($"file:{id}:{exp}")));
}
