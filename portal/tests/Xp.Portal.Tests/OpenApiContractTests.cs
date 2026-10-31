using System.Text.Json;
using System.Text.Json.Nodes;

namespace Xp.Portal.Tests;

/// <summary>
/// The API is called by the game (F8) and by crash reports: a change to it is a change for clients
/// already out there. The description is pinned in docs/portal/openapi-v1.json; an intended change is
/// taken with XP_UPDATE_OPENAPI=1 and reviewed in the diff.
/// </summary>
public sealed class OpenApiContractTests(PortalFactory f) : IClassFixture<PortalFactory>
{
    static string Snapshot => Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "../../../../../../docs/portal/openapi-v1.json"));

    async Task<JsonNode> CurrentAsync()
    {
        var doc = JsonNode.Parse(await f.CreateClient().GetStringAsync("/openapi/v1.json"))!;
        doc.AsObject().Remove("servers");   // the test host's address, not part of the contract
        return doc;
    }

    [Fact]
    public async Task Api_matches_the_pinned_description()
    {
        var now = (await CurrentAsync()).ToJsonString(new JsonSerializerOptions { WriteIndented = true }).ReplaceLineEndings("\n") + "\n";
        if (Environment.GetEnvironmentVariable("XP_UPDATE_OPENAPI") == "1")
        {
            Directory.CreateDirectory(Path.GetDirectoryName(Snapshot)!);
            await File.WriteAllTextAsync(Snapshot, now);
        }
        Assert.True(File.Exists(Snapshot), $"no snapshot at {Snapshot}; run the tests once with XP_UPDATE_OPENAPI=1");
        var pinned = (await File.ReadAllTextAsync(Snapshot)).ReplaceLineEndings("\n");
        Assert.Equal(pinned, now);
    }

    [Fact]
    public async Task Guest_operations_declare_the_token_header_and_site_routes_stay_out()
    {
        var doc = await CurrentAsync();
        var paths = doc["paths"]!.AsObject();
        Assert.All(paths.Select(p => p.Key), p => Assert.StartsWith("/api/v1/", p));
        foreach (var (path, method) in new[] { ("/api/v1/tickets/{number}", "get"), ("/api/v1/tickets/{number}/messages", "post"), ("/api/v1/tickets/{number}/attachments", "post") })
        {
            var names = paths[path]![method]!["parameters"]!.AsArray().Select(p => p!["name"]!.GetValue<string>());
            Assert.Contains("X-Ticket-Token", names);
        }
        var create = paths["/api/v1/tickets"]!["post"]!;
        Assert.Contains("Idempotency-Key", create["parameters"]!.AsArray().Select(p => p!["name"]!.GetValue<string>()));
        Assert.Equal(["200", "201", "400", "409", "429"], create["responses"]!.AsObject().Select(r => r.Key).Order());
    }
}
