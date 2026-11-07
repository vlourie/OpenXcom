using Microsoft.AspNetCore.Mvc;

namespace Xp.Portal.Packs;

/// <summary>
/// The launcher asks for the update from its release in one file (<see cref="PackService"/>): 200 the pack is ready,
/// 202 it is being made (ask again), 204 nothing to pack, 404 no such release here, 503 too many packs in the making.
/// Anything but 200 means the launcher fetches the files one by one, as it did before.
/// </summary>
public static class PackApi
{
    /// <summary>A request is two release names and a few component ids.</summary>
    public const long BodyLimit = 4096;

    public static void Map(IEndpointRouteBuilder app)
    {
        var api = app.MapGroup("/api/v1").WithTags("packs").DisableAntiforgery();
        api.MapPost("/packs", Ask).RequireRateLimiting("packs")
            .WithMetadata(new RequestSizeLimitAttribute(BodyLimit))
            .Produces<PackOffer>()
            .Produces<PackPending>(StatusCodes.Status202Accepted)
            .Produces(StatusCodes.Status204NoContent)
            .ProducesProblem(StatusCodes.Status400BadRequest)
            .ProducesProblem(StatusCodes.Status404NotFound)
            .ProducesProblem(StatusCodes.Status413PayloadTooLarge)
            .ProducesProblem(StatusCodes.Status429TooManyRequests)
            .ProducesProblem(StatusCodes.Status503ServiceUnavailable);
    }

    static IResult Ask(PackRequest? request, PackService packs, HttpContext http)
    {
        if (!packs.Enabled) return Problem(StatusCodes.Status404NotFound, "packs_off", "this server makes no packs");
        if (request is null) return Problem(StatusCodes.Status400BadRequest, "pack_invalid", "no request");
        PackAnswer answer;
        try { answer = packs.Ask(request); }
        catch (ArgumentException e) { return Problem(StatusCodes.Status400BadRequest, "pack_invalid", e.Message); }
        switch (answer.State)
        {
            case PackState.Ready:
                return Results.Ok(answer.Offer);
            case PackState.Building:
                http.Response.Headers.RetryAfter = PackService.RetryAfterSeconds.ToString();
                return Results.Accepted(value: new PackPending(PackService.RetryAfterSeconds));
            case PackState.Empty:
                return Results.NoContent();
            case PackState.Busy:
                return Problem(StatusCodes.Status503ServiceUnavailable, "pack_busy", "too many packs in the making");
            default:
                return Problem(StatusCodes.Status404NotFound, "pack_unknown_release", "no such release in the channel");
        }
    }

    static IResult Problem(int status, string code, string detail) =>
        Results.Problem(detail: detail, statusCode: status, extensions: new Dictionary<string, object?> { ["code"] = code });
}
