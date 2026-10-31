using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Xp.Launcher.Core;

/// <summary>What the launcher shows the person while they walk over to the site.</summary>
public sealed record LinkStart(string Code, Guid DeviceId, int ExpiresIn);

/// <summary>Was it confirmed yet: pending, linked or expired. The token comes once, on the first ask after a yes.</summary>
public sealed record LinkStatus(string Status, string? Token, string? Account);

/// <summary>Who the site says this launcher is.</summary>
public sealed record DeviceView(string Account, string Name, DateTimeOffset LinkedAt);

internal sealed record LinkRequestBody(string Name);

/// <summary>The account this launcher works for, and the key it does that with.</summary>
public sealed class DeviceAccount
{
    public string Token { get; set; } = "";
    /// <summary>The name the site shows for the person, so the launcher can say whose it is without asking.</summary>
    public string Account { get; set; } = "";
    /// <summary>What this launcher called itself when it asked to be linked.</summary>
    public string Name { get; set; } = "";
    public DateTimeOffset LinkedAt { get; set; }
}

/// <summary>
/// Where the device token lives: a file of its own, never settings.json. Settings are ordinary
/// preferences a person may copy between machines or show in a screenshot; this one is a key, and a
/// key that travels is a key given away. Losing the file costs one link, not the account.
/// </summary>
public sealed class DeviceStore(string path)
{
    public string Path { get; } = path;

    public DeviceAccount? Load()
    {
        try
        {
            if (!File.Exists(Path)) return null;
            var a = JsonSerializer.Deserialize(File.ReadAllBytes(Path), DeviceJson.Default.DeviceAccount);
            return a is { Token.Length: > 0 } ? a : null;
        }
        catch (Exception e) when (e is JsonException or IOException or UnauthorizedAccessException) { return null; }
    }

    public void Save(DeviceAccount account) =>
        FileUtil.WriteAtomic(Path, JsonSerializer.SerializeToUtf8Bytes(account, DeviceJson.Default.DeviceAccount));

    public void Clear()
    {
        try { File.Delete(Path); }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { }
    }
}

/// <summary>The device half of the portal API: link, wait for the yes, ask who we are, forget ourselves.</summary>
public sealed partial class PortalClient
{
    public const string DeviceTokenHeader = "X-Device-Token";

    /// <summary>Asks for a code to show. Nothing is linked yet: the person has to confirm it on the site.</summary>
    public async Task<LinkStart> StartLinkAsync(string name, CancellationToken ct)
    {
        using var msg = new HttpRequestMessage(HttpMethod.Post, new Uri(BaseUri, "api/v1/devices/link"))
        {
            Content = JsonContent.Create(new LinkRequestBody(name), DeviceJson.Default.LinkRequestBody),
        };
        using var resp = await Http.SendAsync(msg, ct);
        await ThrowIfFailedAsync(resp, ct);
        return await resp.Content.ReadFromJsonAsync(DeviceJson.Default.LinkStart, ct)
               ?? throw new PortalException((int)resp.StatusCode, "bad_response", "empty answer");
    }

    public async Task<LinkStatus> LinkStatusAsync(Guid deviceId, CancellationToken ct)
    {
        using var msg = new HttpRequestMessage(HttpMethod.Get, new Uri(BaseUri, $"api/v1/devices/{deviceId}"));
        using var resp = await Http.SendAsync(msg, ct);
        await ThrowIfFailedAsync(resp, ct);
        return await resp.Content.ReadFromJsonAsync(DeviceJson.Default.LinkStatus, ct)
               ?? throw new PortalException((int)resp.StatusCode, "bad_response", "empty answer");
    }

    /// <summary>Null when the site no longer knows this token: the person took the link away.</summary>
    public async Task<DeviceView?> WhoAmIAsync(string token, CancellationToken ct)
    {
        using var msg = new HttpRequestMessage(HttpMethod.Get, new Uri(BaseUri, "api/v1/devices/me"));
        msg.Headers.Add(DeviceTokenHeader, token);
        using var resp = await Http.SendAsync(msg, ct);
        if (resp.StatusCode == HttpStatusCode.Unauthorized) return null;
        await ThrowIfFailedAsync(resp, ct);
        return await resp.Content.ReadFromJsonAsync(DeviceJson.Default.DeviceView, ct);
    }

    /// <summary>Gives the key back. A token the site has already forgotten counts as forgotten.</summary>
    public async Task ForgetAsync(string token, CancellationToken ct)
    {
        using var msg = new HttpRequestMessage(HttpMethod.Delete, new Uri(BaseUri, "api/v1/devices/me"));
        msg.Headers.Add(DeviceTokenHeader, token);
        using var resp = await Http.SendAsync(msg, ct);
        if (resp.StatusCode == HttpStatusCode.Unauthorized) return;
        await ThrowIfFailedAsync(resp, ct);
    }
}

[JsonSourceGenerationOptions(WriteIndented = true, PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase,
    PropertyNameCaseInsensitive = true)]
[JsonSerializable(typeof(LinkRequestBody))]
[JsonSerializable(typeof(LinkStart))]
[JsonSerializable(typeof(LinkStatus))]
[JsonSerializable(typeof(DeviceView))]
[JsonSerializable(typeof(DeviceAccount))]
internal sealed partial class DeviceJson : JsonSerializerContext
{
}
