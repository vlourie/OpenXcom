using System.Net.Http.Json;
using System.Text.Json.Serialization;

namespace Xp.Launcher.Core;

// Private messages (ticket XP-000476): the launcher half of portal/src/Xp.Portal/Messages/MessageApi.cs.
// Same device key as the voice calls; the rules (limits, blocks, length) are the site's, the launcher only shows
// the reason it gives. Text is text: nothing in a message is a link or markup.

public sealed record MessageBubble(Guid Id, bool Mine, string Body, DateTimeOffset At, bool Read);

/// <summary>One person written to or by, with what was said last and how much of it is still unread.</summary>
public sealed record MessageDialogue(VoicePerson Person, string Preview, bool LastMine, DateTimeOffset At, int Unread);

public sealed record MessageInbox(int Unread, List<MessageDialogue> Dialogues);

/// <summary>One page of a dialogue, in reading order; page 1 is the end of the conversation.</summary>
public sealed record MessageThread(VoicePerson Person, List<MessageBubble> Messages, int Total, int Page, int PerPage, bool IBlocked, bool Friend)
{
    public int Pages => Math.Max(1, (Total + Math.Max(1, PerPage) - 1) / Math.Max(1, PerPage));
}

public sealed record MessageSent(Guid Id, VoicePerson To, DateTimeOffset At);

/// <summary>The site's limits on what a person types (Xp.Portal MessageLimits): longer is refused there.</summary>
public static class MessageRules
{
    public const int BodyMax = 4000;
    public const int ComplaintMax = 2000;
}

internal sealed record MessageUnreadAnswer(int Unread);
internal sealed record MessageSendBody(string Who, string Body);
internal sealed record MessageReplyBody(string Body);
internal sealed record MessageComplaintBody(Guid? Message, string Text);

public sealed partial class PortalClient
{
    const string Messages = "api/v1/messages";

    /// <summary>How many messages wait unread: one small answer, for the counter on the rail.</summary>
    public async Task<int> MessagesUnreadAsync(string deviceToken, CancellationToken ct) =>
        (await AskAsync(DeviceRequest(HttpMethod.Get, Messages + "/unread", deviceToken), MessageJson.Default.MessageUnreadAnswer, ct)).Unread;

    public Task<MessageInbox> MessageInboxAsync(string deviceToken, CancellationToken ct) =>
        AskAsync(DeviceRequest(HttpMethod.Get, Messages, deviceToken), MessageJson.Default.MessageInbox, ct);

    /// <summary>Reading does not mark anything: call <see cref="MessagesReadAsync"/> once the dialogue is in front of the person.</summary>
    public Task<MessageThread> MessageThreadAsync(string deviceToken, Guid user, int page, CancellationToken ct) =>
        AskAsync(DeviceRequest(HttpMethod.Get, $"{Messages}/{user}?page={Math.Max(1, page)}", deviceToken), MessageJson.Default.MessageThread, ct);

    public Task MessagesReadAsync(string deviceToken, Guid user, CancellationToken ct) =>
        DoAsync(DeviceRequest(HttpMethod.Post, $"{Messages}/{user}/read", deviceToken), ct);

    /// <summary>A message to somebody already in front of the person (a dialogue, a friend).</summary>
    public Task<MessageSent> SendMessageAsync(string deviceToken, Guid user, string body, CancellationToken ct) =>
        AskAsync(DeviceRequest(HttpMethod.Post, $"{Messages}/{user}", deviceToken,
            JsonContent.Create(new MessageReplyBody(body), MessageJson.Default.MessageReplyBody)), MessageJson.Default.MessageSent, ct);

    /// <summary>A new message by profile name (or a profile link or id), the way the site's form takes it.</summary>
    public Task<MessageSent> SendMessageToAsync(string deviceToken, string who, string body, CancellationToken ct) =>
        AskAsync(DeviceRequest(HttpMethod.Post, Messages, deviceToken,
            JsonContent.Create(new MessageSendBody(who.Trim(), body), MessageJson.Default.MessageSendBody)), MessageJson.Default.MessageSent, ct);

    /// <summary>A complaint about somebody's messages: a ticket of the voice category on the site, with a copy of the dialogue.</summary>
    public Task<VoiceComplaint> ComplainAboutMessagesAsync(string deviceToken, Guid user, Guid? message, string text, CancellationToken ct) =>
        AskAsync(DeviceRequest(HttpMethod.Post, $"{Messages}/{user}/complaints", deviceToken,
            JsonContent.Create(new MessageComplaintBody(message, text.Trim()), MessageJson.Default.MessageComplaintBody)), VoiceJson.Default.VoiceComplaint, ct);

    /// <summary>The site's one block (the same as for friends and voice): neither side can write after it.</summary>
    public Task BlockPersonAsync(string deviceToken, Guid user, CancellationToken ct) =>
        DoAsync(DeviceRequest(HttpMethod.Put, $"api/v1/blocks/{user}", deviceToken), ct);

    public Task UnblockPersonAsync(string deviceToken, Guid user, CancellationToken ct) =>
        DoAsync(DeviceRequest(HttpMethod.Delete, $"api/v1/blocks/{user}", deviceToken), ct);
}

[JsonSourceGenerationOptions(PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase, PropertyNameCaseInsensitive = true)]
[JsonSerializable(typeof(MessageUnreadAnswer))]
[JsonSerializable(typeof(MessageInbox))]
[JsonSerializable(typeof(MessageThread))]
[JsonSerializable(typeof(MessageSent))]
[JsonSerializable(typeof(MessageSendBody))]
[JsonSerializable(typeof(MessageReplyBody))]
[JsonSerializable(typeof(MessageComplaintBody))]
internal sealed partial class MessageJson : JsonSerializerContext
{
}
