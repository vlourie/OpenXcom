using System.IO.Compression;
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
    public long MaxFileBytes { get; set; } = 50L * 1024 * 1024;
    public long MaxZipBytes { get; set; } = 100L * 1024 * 1024;
    /// <summary>A zip is read entry by entry to check what is inside, never unpacked to disk: at most this much, in at most this many files.</summary>
    public long MaxZipUnpackedBytes { get; set; } = 512L * 1024 * 1024;
    public int MaxZipEntries { get; set; } = 20;
    public int MaxFilesPerTicket { get; set; } = 10;
    public long MaxBytesPerTicket { get; set; } = 200L * 1024 * 1024;
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
        FileKind.Text => head.IndexOf((byte)0) < 0 && LooksUtf8(head),
        FileKind.Save => head.IndexOf((byte)0) < 0 && LooksUtf8(head) && SaveHeader(head),
        _ => false,
    };

    /// <summary>
    /// An OpenXcom save opens with its header document: "name:" on the first line, "version:" soon
    /// after (SavedGame::save). Normal saves, auto- and quick-saves all have it.
    /// </summary>
    public static bool SaveHeader(ReadOnlySpan<byte> head)
    {
        if (head.StartsWith((ReadOnlySpan<byte>)[0xEF, 0xBB, 0xBF])) head = head[3..];
        return head.StartsWith("name:"u8) && head.IndexOf("\nversion:"u8) > 0;
    }

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

/// <summary>
/// Checks a file as it streams in, not only its head: a log or a save must be UTF-8 text without NUL
/// bytes all the way through, a save must also start with the save header, a picture with its magic.
/// </summary>
public sealed class ContentCheck(FileKind kind)
{
    readonly Decoder? _utf8 = kind is FileKind.Text or FileKind.Save ? new UTF8Encoding(false, throwOnInvalidBytes: true).GetDecoder() : null;
    readonly byte[] _head = new byte[8192];
    int _headLen;
    bool _headChecked;
    char[] _chars = [];

    /// <summary>The reason the file is refused (a key of Strings/*.json), or null while it looks right.</summary>
    public string? Error { get; private set; }

    public void Feed(ReadOnlySpan<byte> chunk)
    {
        if (Error is not null) return;
        if (_headLen < _head.Length)
        {
            var take = Math.Min(chunk.Length, _head.Length - _headLen);
            chunk[..take].CopyTo(_head.AsSpan(_headLen));
            _headLen += take;
            // decide as soon as the head is complete, before storing megabytes of a fake file
            if (_headLen == _head.Length) CheckHead();
        }
        if (_utf8 is null || Error is not null) return;
        if (chunk.IndexOf((byte)0) >= 0) { Error = "file_not_text"; return; }
        if (_chars.Length < chunk.Length + 4) _chars = new char[chunk.Length + 4];
        try { _utf8.GetChars(chunk, _chars, flush: false); }
        catch (DecoderFallbackException) { Error = "file_not_text"; }
    }

    /// <summary>After the last chunk: the head of a short file is checked here.</summary>
    public string? Finish()
    {
        if (!_headChecked && Error is null) CheckHead();
        return Error;
    }

    void CheckHead()
    {
        _headChecked = true;
        var head = _head.AsSpan(0, _headLen);
        if (FileRules.HeadMatches(kind, head)) return;
        Error = kind switch
        {
            FileKind.Save when head.IndexOf((byte)0) < 0 && !FileRules.SaveHeader(head) => "file_not_save",
            FileKind.Text or FileKind.Save => "file_not_text",
            _ => "file_content_mismatch",
        };
    }
}

/// <summary>
/// A zip is only a wrapper for what could be attached on its own: every entry is read through the
/// same ContentCheck, nothing is written out. Another archive inside is refused.
/// </summary>
public static class ZipCheck
{
    public static async Task<string?> CheckAsync(Stream file, AttachmentOptions o, CancellationToken ct)
    {
        try
        {
            using var zip = new ZipArchive(file, ZipArchiveMode.Read, leaveOpen: true);
            if (zip.Entries.Count > o.MaxZipEntries) return "zip_content_not_allowed";
            long unpacked = 0;
            int files = 0;
            var buf = new byte[81920];
            foreach (var e in zip.Entries)
            {
                if (e.FullName.EndsWith('/')) continue;
                if (FileRules.KindOf(e.Name) is not { } kind || kind == FileKind.Zip) return "zip_content_not_allowed";
                files++;
                var check = new ContentCheck(kind);
                await using var s = e.Open();
                int n;
                while ((n = await s.ReadAsync(buf, ct)) > 0)
                {
                    unpacked += n;
                    if (unpacked > o.MaxZipUnpackedBytes) return "file_too_large";
                    check.Feed(buf.AsSpan(0, n));
                    if (check.Error is not null) return check.Error;
                }
                if (check.Finish() is { } err) return err;
            }
            return files == 0 ? "file_empty" : null;
        }
        catch (InvalidDataException) { return "file_content_mismatch"; }
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
                var check = new ContentCheck(kind);
                int n;
                while ((n = await body.ReadAsync(buf, ct)) > 0)
                {
                    size += n;
                    if (size > limit) throw new TicketException("file_too_large", "the file is too large");
                    if (size > roomLeft) throw new TicketException("ticket_files_too_large", "the ticket's files are too large in total");
                    check.Feed(buf.AsSpan(0, n));
                    if (check.Error is { } midway) throw new TicketException(midway, "the file content does not match its type");
                    sha.AppendData(buf, 0, n);
                    await dst.WriteAsync(buf.AsMemory(0, n), ct);
                }
                if (size == 0) throw new TicketException("file_empty", "the file is empty");
                if (check.Finish() is { } bad) throw new TicketException(bad, "the file content does not match its type");
            }
            if (kind == FileKind.Zip)
            {
                await using var stored = store.OpenRead(key);
                if (await ZipCheck.CheckAsync(stored, o, ct) is { } inside) throw new TicketException(inside, "the archive holds something that may not be attached");
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
