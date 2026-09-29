/* Microphone and speakers of the launcher voice: a thin C layer over miniaudio (public domain).
 *
 * One duplex device on WASAPI: capture and playback share one callback, so the echo canceller sees
 * what is being played in step with what the microphone hears. 48 kHz mono s16, a 10 ms period -
 * the frame the LiveKit audio source and the echo canceller both expect. miniaudio converts to the
 * device's own rate and channel count and follows the default device when Windows switches it.
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

#include <stdint.h>
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
    return ma_device_init(NULL, &c, &g_device);
}

/* Returns 1 - microphone and speakers, 2 - speakers only (no microphone could be opened), <0 - error. */
XPA_API int xpa_open(uint32_t rate, uint32_t period, xpa_data_cb data, xpa_note_cb note, void *user, int capture)
{
    if (g_open) return -1;
    g_data = data; g_note = note; g_user = user;
    g_error[0] = 0;
    int mode = 2;
    ma_result r = MA_ERROR;
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
