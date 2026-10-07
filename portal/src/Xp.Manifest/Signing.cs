using System.Security.Cryptography;
using System.Text.Json;
using NSec.Cryptography;

namespace Xp.Manifest;

/// <summary>Ed25519 over the exact bytes of a file. The private key never reaches the launcher.</summary>
public static class Signing
{
    static readonly SignatureAlgorithm Alg = SignatureAlgorithm.Ed25519;

    /// <summary>Short id of a public key: first 16 hex chars of its SHA-256.</summary>
    public static string KeyId(ReadOnlySpan<byte> publicKey) =>
        Convert.ToHexStringLower(SHA256.HashData(publicKey))[..16];

    /// <summary>New key pair: (32-byte private seed, 32-byte public key).</summary>
    public static (byte[] PrivateSeed, byte[] PublicKey) CreateKeyPair()
    {
        using var key = Key.Create(Alg, new KeyCreationParameters { ExportPolicy = KeyExportPolicies.AllowPlaintextExport });
        return (key.Export(KeyBlobFormat.RawPrivateKey), key.PublicKey.Export(KeyBlobFormat.RawPublicKey));
    }

    public static byte[] PublicKeyOf(byte[] privateSeed)
    {
        using var key = Key.Import(Alg, privateSeed, KeyBlobFormat.RawPrivateKey);
        return key.PublicKey.Export(KeyBlobFormat.RawPublicKey);
    }

    public static SignatureFile Sign(byte[] privateSeed, ReadOnlySpan<byte> data)
    {
        using var key = Key.Import(Alg, privateSeed, KeyBlobFormat.RawPrivateKey);
        var sig = Alg.Sign(key, data);
        return new SignatureFile
        {
            KeyId = KeyId(key.PublicKey.Export(KeyBlobFormat.RawPublicKey)),
            Signature = Convert.ToBase64String(sig),
        };
    }

    public static byte[] SerializeSignature(SignatureFile sig) =>
        JsonSerializer.SerializeToUtf8Bytes(sig, ManifestJson.Default.SignatureFile);
}

/// <summary>The set of public keys a launcher trusts (current and next, for rotation).</summary>
public sealed class TrustedKeys
{
    readonly Dictionary<string, PublicKey> _keys = new(StringComparer.Ordinal);

    public TrustedKeys(IEnumerable<string> base64PublicKeys)
    {
        foreach (var b64 in base64PublicKeys)
        {
            var raw = Convert.FromBase64String(b64.Trim());
            _keys[Signing.KeyId(raw)] = PublicKey.Import(SignatureAlgorithm.Ed25519, raw, KeyBlobFormat.RawPublicKey);
        }
        if (_keys.Count == 0) throw new ArgumentException("no trusted keys");
    }

    public IReadOnlyCollection<string> KeyIds => _keys.Keys;

    /// <summary>True only for a well-formed signature by one of the trusted keys over exactly <paramref name="data"/>.</summary>
    public bool Verify(ReadOnlySpan<byte> data, ReadOnlySpan<byte> signatureFileBytes)
    {
        SignatureFile? sig;
        try { sig = JsonSerializer.Deserialize(signatureFileBytes, ManifestJson.Default.SignatureFile); }
        catch (JsonException) { return false; }
        if (sig is null || sig.Algorithm != "ed25519") return false;
        if (!_keys.TryGetValue(sig.KeyId, out var key)) return false;
        byte[] raw;
        try { raw = Convert.FromBase64String(sig.Signature); }
        catch (FormatException) { return false; }
        if (raw.Length != SignatureAlgorithm.Ed25519.SignatureSize) return false;
        return SignatureAlgorithm.Ed25519.Verify(key, data, raw);
    }
}
