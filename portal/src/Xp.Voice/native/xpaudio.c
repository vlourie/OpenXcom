/* Microphone and speakers of the launcher voice: a thin C layer over miniaudio (public domain).
 *
 * One duplex device on WASAPI: capture and playback share one callback, so the echo canceller sees
 * what is being played in step with what the microphone hears. 48 kHz mono s16, a 10 ms period -
 * the frame the LiveKit audio source and the echo canceller both expect. miniaudio converts to the
 * device's own rate and channel count and follows the default device when Windows switches it.
 *
 * xpa_set_options chooses an output / input device by a part of its name. Diagnostics give numbers
 * and names only, never sound: xpa_detail tells what WASAPI really gave each stream, xpa_take_log
 * hands over miniaudio's own log lines. miniaudio.h carries a local fix of its duplex loop
 * (tools/voice_ma_patch.py, R-190).
 *
 * Build: py -3.13 tools/voice_deps.py --audio (MinGW gcc, static, no runtime DLLs).
 */
#define MINIAUDIO_IMPLEMENTATION
#define MA_NO_DECODING
#define MA_NO_ENCODING
#define MA_NO_GENERATION
#define MA_NO_RESOURCE_MANAGER
#define MA_NO_NODE_GRAPH
#define MA_NO_ENGINE
#define MA_ENABLE_ONLY_SPECIFIC_BACKENDS
#define MA_ENABLE_WASAPI
#include "miniaudio.h"

#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define XPA_API __declspec(dllexport)

/* input is NULL when there is no microphone; output always has frames samples to fill */
typedef void (*xpa_data_cb)(void *user, const int16_t *input, int16_t *output, uint32_t frames);
/* kind: miniaudio's ma_device_notification_type (0 started, 1 stopped, 2 rerouted, 3/4 interruption, 5 unlocked) */
typedef void (*xpa_note_cb)(void *user, int kind);

static ma_device g_device;
static int g_open = 0;
static xpa_data_cb g_data;
static xpa_note_cb g_note;
static void *g_user;
static char g_error[256];

/* ---------------------------------------------------------------- one context for the process, with miniaudio's log kept */

static ma_log g_log;
static ma_context g_ctx;
static int g_ctxOpen = 0;
static ma_mutex g_logLock;
static char g_logBuf[16384];
static size_t g_logLen;

/* miniaudio's log callback: every level, one line per message, for xpa_take_log. The debug lines are
 * the ones that matter ("[WASAPI] Using IAudioClient3", the engine periods) - miniaudio posts them to
 * every registered callback whatever the level. */
static void on_ma_log(void *user, ma_uint32 level, const char *msg)
{
    static const char *names[] = { "?", "error", "warning", "info", "debug" };
    char head[16];
    size_t n = strlen(msg);
    (void)user;
    while (n > 0 && (msg[n - 1] == '\n' || msg[n - 1] == '\r')) n--;
    int hn = snprintf(head, sizeof head, "%s: ", level <= 4 ? names[level] : "?");
    ma_mutex_lock(&g_logLock);
    if (g_logLen + (size_t)hn + n + 2 <= sizeof g_logBuf) {
        memcpy(g_logBuf + g_logLen, head, (size_t)hn); g_logLen += (size_t)hn;
        memcpy(g_logBuf + g_logLen, msg, n); g_logLen += n;
        g_logBuf[g_logLen++] = '\n';
        g_logBuf[g_logLen] = 0;
    }
    ma_mutex_unlock(&g_logLock);
}

static ma_result ctx_open(void)
{
    if (g_ctxOpen) return MA_SUCCESS;
    ma_result r = ma_mutex_init(&g_logLock);
    if (r != MA_SUCCESS) return r;
    r = ma_log_init(NULL, &g_log);
    if (r != MA_SUCCESS) { ma_mutex_uninit(&g_logLock); return r; }
    ma_log_register_callback(&g_log, ma_log_callback_init(on_ma_log, NULL));
    ma_context_config cc = ma_context_config_init();
    cc.pLog = &g_log;
    ma_backend be = ma_backend_wasapi;
    r = ma_context_init(&be, 1, &cc, &g_ctx);
    if (r != MA_SUCCESS) { ma_log_uninit(&g_log); ma_mutex_uninit(&g_logLock); return r; }
    g_ctxOpen = 1;
    return MA_SUCCESS;
}

/* Copies miniaudio's log lines gathered since the last call ("level: text", one per line) into dst and
 * forgets them; returns the length. */
XPA_API int xpa_take_log(char *dst, uint32_t cap)
{
    if (!g_ctxOpen || cap == 0) return 0;
    ma_mutex_lock(&g_logLock);
    size_t n = g_logLen < cap - 1 ? g_logLen : cap - 1;
    memcpy(dst, g_logBuf, n);
    dst[n] = 0;
    g_logLen = 0;
    g_logBuf[0] = 0;
    ma_mutex_unlock(&g_logLock);
    return (int)n;
}

/* ---------------------------------------------------------------- device choice */

static char g_outPick[128], g_inPick[128];   /* parts of device names, ASCII case-insensitive; empty = the Windows default */
static ma_device_id g_outId, g_inId;         /* the ids behind the picks, valid while the picks are */
static char g_outName[256], g_inName[256];   /* the names found, empty = default used */

/* Before xpa_open; kept for every later open (the launcher reopens the device after Windows takes it away). */
XPA_API void xpa_set_options(const char *output, const char *input)
{
    snprintf(g_outPick, sizeof g_outPick, "%s", output ? output : "");
    snprintf(g_inPick, sizeof g_inPick, "%s", input ? input : "");
}

static int lower_ascii(int c) { return c >= 'A' && c <= 'Z' ? c + 32 : c; }

static int contains_ci(const char *hay, const char *needle)
{
    size_t n = strlen(needle);
    if (n == 0) return 0;
    for (; *hay; hay++) {
        size_t i = 0;
        while (i < n && hay[i] && lower_ascii((unsigned char)hay[i]) == lower_ascii((unsigned char)needle[i])) i++;
        if (i == n) return 1;
    }
    return 0;
}

/* The first device of the type whose name contains pick: 1 with *id and name filled, 0 = none (default then). */
static int pick_device(ma_device_type type, const char *pick, ma_device_id *id, char *name, size_t cap)
{
    ma_device_info *pb, *cp;
    ma_uint32 npb = 0, ncp = 0;
    name[0] = 0;
    if (!pick[0] || ma_context_get_devices(&g_ctx, &pb, &npb, &cp, &ncp) != MA_SUCCESS) return 0;
    ma_device_info *list = type == ma_device_type_capture ? cp : pb;
    ma_uint32 n = type == ma_device_type_capture ? ncp : npb;
    for (ma_uint32 i = 0; i < n; i++) {
        if (contains_ci(list[i].name, pick)) {
            *id = list[i].id;
            snprintf(name, cap, "%s", list[i].name);
            return 1;
        }
    }
    return 0;
}

static void app(char *s, size_t cap, size_t *at, const char *fmt, ...)
{
    if (*at >= cap - 1) return;
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(s + *at, cap - *at, fmt, ap);
    va_end(ap);
    if (n < 0) return;
    *at += (size_t)n;
    if (*at > cap - 1) *at = cap - 1;
}

/* "playback: [*] name; name | capture: [*] name" - what Windows lists, [*] its default; for the log. */
XPA_API const char *xpa_devices(void)
{
    static char s[2048];
    ma_device_info *pb, *cp;
    ma_uint32 npb = 0, ncp = 0;
    size_t at = 0;
    s[0] = 0;
    if (ctx_open() != MA_SUCCESS || ma_context_get_devices(&g_ctx, &pb, &npb, &cp, &ncp) != MA_SUCCESS) return "?";
    app(s, sizeof s, &at, "playback:");
    for (ma_uint32 i = 0; i < npb; i++) app(s, sizeof s, &at, "%s %s%s", i ? ";" : "", pb[i].isDefault ? "[*] " : "", pb[i].name);
    app(s, sizeof s, &at, " | capture:");
    for (ma_uint32 i = 0; i < ncp; i++) app(s, sizeof s, &at, "%s %s%s", i ? ";" : "", cp[i].isDefault ? "[*] " : "", cp[i].name);
    return s;
}

/* ---------------------------------------------------------------- the duplex device */

static void on_data(ma_device *dev, void *output, const void *input, ma_uint32 frames)
{
    (void)dev;
    g_data(g_user, (const int16_t *)input, (int16_t *)output, frames);
}

static void on_note(const ma_device_notification *n)
{
    if (g_note) g_note(g_user, (int)n->type);
}

static ma_result try_open(ma_device_type type, uint32_t rate, uint32_t period)
{
    ma_device_config c = ma_device_config_init(type);
    c.sampleRate = rate;
    c.periodSizeInFrames = period;
    c.performanceProfile = ma_performance_profile_low_latency;
    c.playback.format = ma_format_s16;
    c.playback.channels = 1;
    c.capture.format = ma_format_s16;
    c.capture.channels = 1;
    c.dataCallback = on_data;
    c.notificationCallback = on_note;
    if (pick_device(ma_device_type_playback, g_outPick, &g_outId, g_outName, sizeof g_outName)) c.playback.pDeviceID = &g_outId;
    if (type == ma_device_type_duplex && pick_device(ma_device_type_capture, g_inPick, &g_inId, g_inName, sizeof g_inName)) c.capture.pDeviceID = &g_inId;
    return ma_device_init(&g_ctx, &c, &g_device);
}

/* Returns 1 - microphone and speakers, 2 - speakers only (no microphone could be opened), <0 - error. */
XPA_API int xpa_open(uint32_t rate, uint32_t period, xpa_data_cb data, xpa_note_cb note, void *user, int capture)
{
    if (g_open) return -1;
    g_data = data; g_note = note; g_user = user;
    g_error[0] = 0;
    ma_result r = ctx_open();
    if (r != MA_SUCCESS) {
        snprintf(g_error, sizeof g_error, "context: %s", ma_result_description(r));
        return -4;
    }
    int mode = 2;
    r = MA_ERROR;
    if (capture) {
        r = try_open(ma_device_type_duplex, rate, period);
        if (r == MA_SUCCESS) mode = 1;
        else snprintf(g_error, sizeof g_error, "microphone: %s", ma_result_description(r));
    }
    if (r != MA_SUCCESS) {
        r = try_open(ma_device_type_playback, rate, period);
        if (r != MA_SUCCESS) {
            snprintf(g_error, sizeof g_error, "speakers: %s", ma_result_description(r));
            return -2;
        }
    }
    r = ma_device_start(&g_device);
    if (r != MA_SUCCESS) {
        snprintf(g_error, sizeof g_error, "start: %s", ma_result_description(r));
        ma_device_uninit(&g_device);
        return -3;
    }
    g_open = 1;
    return mode;
}

/* ---------------------------------------------------------------- the rest */

/* How many capture devices Windows lists right now; -1 when not open or the query failed. The launcher
 * asks before reopening for a missing microphone: a reopening is a gap in what is played, so one that
 * cannot find a microphone is not tried. Called from one thread at a time (the pump). */
XPA_API int xpa_capture_count(void)
{
    ma_device_info *pb, *cap;
    ma_uint32 npb = 0, ncap = 0;
    if (!g_open) return -1;
    if (ma_context_get_devices(&g_ctx, &pb, &npb, &cap, &ncap) != MA_SUCCESS) return -1;
    return (int)ncap;
}

XPA_API void xpa_close(void)
{
    if (!g_open) return;
    ma_device_uninit(&g_device);   /* waits for the callback to finish */
    g_open = 0;
}

/* The last error text, or an empty string. */
XPA_API const char *xpa_error(void) { return g_error; }

/* What the device really runs at - for the log: "<capture name> | <playback name> | <rate> Hz" */
XPA_API const char *xpa_describe(void)
{
    static char s[600];
    if (!g_open) return "";
    snprintf(s, sizeof s, "%s | %s | %u Hz",
             g_device.type == ma_device_type_duplex ? g_device.capture.name : "-",
             g_device.playback.name, g_device.playback.internalSampleRate);
    return s;
}

/* ---------------------------------------------------------------- what WASAPI really gave each stream */

static void wf_describe(const MA_WAVEFORMATEX *wf, char *s, size_t cap, size_t *at)
{
    /* 3 = WAVE_FORMAT_IEEE_FLOAT (not among miniaudio's defines) */
    app(s, cap, at, "%s", wf->wFormatTag == WAVE_FORMAT_PCM ? "PCM" : wf->wFormatTag == 3 ? "IEEE_FLOAT" : wf->wFormatTag == WAVE_FORMAT_EXTENSIBLE ? "EXTENSIBLE" : "tag?");
    if (wf->wFormatTag == WAVE_FORMAT_EXTENSIBLE && wf->cbSize >= 22) {
        const MA_WAVEFORMATEXTENSIBLE *x = (const MA_WAVEFORMATEXTENSIBLE *)wf;
        app(s, cap, at, "/%s valid %u mask 0x%lx",
            ma_is_guid_equal(&x->SubFormat, &MA_GUID_KSDATAFORMAT_SUBTYPE_PCM) ? "PCM" :
            ma_is_guid_equal(&x->SubFormat, &MA_GUID_KSDATAFORMAT_SUBTYPE_IEEE_FLOAT) ? "FLOAT" : "sub?",
            (unsigned)x->Samples.wValidBitsPerSample, (unsigned long)x->dwChannelMask);
    }
    app(s, cap, at, " %u bit %u ch %lu Hz", (unsigned)wf->wBitsPerSample, (unsigned)wf->nChannels, (unsigned long)wf->nSamplesPerSec);
}

/* The engine's side of an initialized stream, read from its IAudioClient: the mix format (what the
 * engine really runs in), the device periods, the buffer and latency it reports, whether the endpoint
 * offers hardware offload, and the engine period IAudioClient3 says is current. Queries only. */
static void client_describe(ma_IAudioClient *ac, char *s, size_t cap, size_t *at)
{
    MA_WAVEFORMATEX *mix = NULL;
    MA_REFERENCE_TIME def = 0, min = 0, lat = 0;
    ma_uint32 buf = 0;
    ma_IAudioClient2 *ac2 = NULL;
    ma_IAudioClient3 *ac3 = NULL;
    ma_context *ctx = &g_ctx;   /* ma_CoTaskMemFree is a macro on a context pointer */
    if (!ac) { app(s, cap, at, " | no audio client"); return; }
    if (SUCCEEDED(ma_IAudioClient_GetMixFormat(ac, &mix)) && mix) {
        app(s, cap, at, " | mix ");
        wf_describe(mix, s, cap, at);
        ma_CoTaskMemFree(ctx, mix);
    }
    if (SUCCEEDED(ma_IAudioClient_GetDevicePeriod(ac, &def, &min))) app(s, cap, at, " | device period %.1f ms (min %.1f)", def / 10000.0, min / 10000.0);
    if (SUCCEEDED(ma_IAudioClient_GetBufferSize(ac, &buf))) app(s, cap, at, " | buffer %u frames", buf);
    if (SUCCEEDED(ma_IAudioClient_GetStreamLatency(ac, &lat))) app(s, cap, at, " | latency %.1f ms", lat / 10000.0);
    if (SUCCEEDED(ma_IAudioClient_QueryInterface(ac, &MA_IID_IAudioClient2, (void **)&ac2)) && ac2) {
        BOOL offload = 0;
        if (SUCCEEDED(ma_IAudioClient2_IsOffloadCapable(ac2, MA_AudioCategory_Other, &offload))) app(s, cap, at, " | offload capable %s", offload ? "yes" : "no");
        ma_IAudioClient2_Release(ac2);
    }
    if (SUCCEEDED(ma_IAudioClient_QueryInterface(ac, &MA_IID_IAudioClient3, (void **)&ac3)) && ac3) {
        MA_WAVEFORMATEX *ef = NULL;
        ma_uint32 per = 0;
        if (SUCCEEDED(ma_IAudioClient3_GetCurrentSharedModeEnginePeriod(ac3, &ef, &per))) {
            app(s, cap, at, " | engine period %u frames", per);
            if (ef) { app(s, cap, at, " at "); wf_describe(ef, s, cap, at); ma_CoTaskMemFree(ctx, ef); }
        }
        ma_IAudioClient3_Release(ac3);
    }
}

static void stream_line(char *s, size_t cap, size_t *at, const char *what, ma_device *d, int playback)
{
    ma_format fmt = playback ? d->playback.format : d->capture.format;
    ma_uint32 ch = playback ? d->playback.channels : d->capture.channels;
    app(s, cap, at, "%s: %s | asked %s %u ch %u Hz, period %u frames | got %s %u ch %u Hz, period %u frames x %u (buffer %u) | IAudioClient3 %s",
        what, playback ? d->playback.name : d->capture.name,
        ma_get_format_name(fmt), ch, d->sampleRate, d->wasapi.originalPeriodSizeInFrames,
        ma_get_format_name(playback ? d->playback.internalFormat : d->capture.internalFormat),
        playback ? d->playback.internalChannels : d->capture.internalChannels,
        playback ? d->playback.internalSampleRate : d->capture.internalSampleRate,
        playback ? d->playback.internalPeriodSizeInFrames : d->capture.internalPeriodSizeInFrames,
        playback ? d->playback.internalPeriods : d->capture.internalPeriods,
        playback ? d->wasapi.actualBufferSizeInFramesPlayback : d->wasapi.actualBufferSizeInFramesCapture,
        (playback ? d->wasapi.usingAudioClient3Playback : d->wasapi.usingAudioClient3Capture) ? "yes" : "no");
    client_describe((ma_IAudioClient *)(playback ? d->wasapi.pAudioClientPlayback : d->wasapi.pAudioClientCapture), s, cap, at);
    app(s, cap, at, "\n");
}

/* For the log, one line per open stream (playback, capture), after a first line with the device picks
 * in force. "asked" is what the launcher requested, "got" what miniaudio initialized the stream with
 * (with AUTOCONVERTPCM the rate is the requested one and the engine converts; "mix" is the engine's
 * own format either way). Formats and names only, no sound. */
XPA_API const char *xpa_detail(void)
{
    static char s[4096];
    size_t at = 0;
    s[0] = 0;
    app(s, sizeof s, &at, "output pick \"%s\"%s%s | input pick \"%s\"%s%s\n",
        g_outPick, g_outName[0] ? " -> " : g_outPick[0] ? " -> not found, default used" : " (default)", g_outName,
        g_inPick, g_inName[0] ? " -> " : g_inPick[0] ? " -> not found, default used" : " (default)", g_inName);
    if (g_open) {
        stream_line(s, sizeof s, &at, "playback", &g_device, 1);
        if (g_device.type == ma_device_type_duplex) stream_line(s, sizeof s, &at, "capture", &g_device, 0);
    }
    return s;
}
