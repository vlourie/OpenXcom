/* Duplex loop of miniaudio against a fake device whose mix format is the friend's Creative SB X-Fi:
 * playback f32 x 6 ch (5.1), 48 kHz; capture f32 mono. The client is ours: s16 mono, period 480, as in
 * xpaudio.c. The data callback writes a ramp 1, 2, 3, ... into the output; the fake device keeps what
 * miniaudio hands to onDeviceWrite. Right: channel 0 of what was written is the same ramp, 1, 2, 3, ...
 * Wrong (miniaudio.h 0.11.25, the duplex inner loop does not advance playbackClientData): every chunk
 * plays its first 4096 / 24 = 170 frames, then those again, then its first 140 - the "robot".
 *   voice_duplex_test.exe [channels] [playback period] [capture channels]   exit 0 - ramp intact, 1 - broken
 * Built and run by tools/test_voice_duplex.py against portal/third_party/voice/miniaudio.h.
 */
#define MINIAUDIO_IMPLEMENTATION
#define MA_ENABLE_ONLY_SPECIFIC_BACKENDS
#define MA_ENABLE_CUSTOM
#include "miniaudio.h"
#include <stdio.h>
#include <stdlib.h>

#define WANT 48000                       /* frames to collect: 1 s */
static float   g_out[WANT * 8];
static volatile ma_uint32 g_got;
static ma_uint32 g_ch = 6, g_period = 512, g_capCh = 1;
static ma_int16  g_ramp;

static ma_result ctx_init(ma_context *c, const ma_context_config *cfg, ma_backend_callbacks *cb) { (void)c; (void)cfg; (void)cb; return MA_SUCCESS; }
static ma_result ctx_uninit(ma_context *c) { (void)c; return MA_SUCCESS; }
static ma_result dev_init(ma_device *d, const ma_device_config *cfg, ma_device_descriptor *pb, ma_device_descriptor *cp)
{
    (void)d; (void)cfg;
    pb->format = ma_format_f32; pb->channels = g_ch; pb->sampleRate = 48000;
    ma_channel_map_init_standard(ma_standard_channel_map_microsoft, pb->channelMap, MA_MAX_CHANNELS, g_ch);
    pb->periodSizeInFrames = g_period; pb->periodCount = 3;
    cp->format = ma_format_f32; cp->channels = g_capCh; cp->sampleRate = 48000;
    ma_channel_map_init_standard(ma_standard_channel_map_microsoft, cp->channelMap, MA_MAX_CHANNELS, g_capCh);
    cp->periodSizeInFrames = 480; cp->periodCount = 3;
    return MA_SUCCESS;
}
static ma_result dev_uninit(ma_device *d) { (void)d; return MA_SUCCESS; }
static ma_result dev_start(ma_device *d) { (void)d; return MA_SUCCESS; }
static ma_result dev_stop(ma_device *d) { (void)d; return MA_SUCCESS; }
static ma_result dev_read(ma_device *d, void *frames, ma_uint32 n, ma_uint32 *got)
{
    memset(frames, 0, (size_t)n * 4 * g_capCh);
    if (g_got >= WANT) ma_sleep(1);
    *got = n;
    (void)d;
    return MA_SUCCESS;
}
static ma_result dev_write(ma_device *d, const void *frames, ma_uint32 n, ma_uint32 *put)
{
    const float *f = (const float *)frames;
    for (ma_uint32 i = 0; i < n && g_got < WANT; i++) g_out[g_got++] = f[i * g_ch];
    if (put) *put = n;
    (void)d;
    return MA_SUCCESS;
}
static void on_data(ma_device *d, void *out, const void *in, ma_uint32 n)
{
    ma_int16 *o = (ma_int16 *)out;
    for (ma_uint32 i = 0; i < n; i++) { g_ramp = (ma_int16)(g_ramp % 30000 + 1); o[i] = g_ramp; }
    (void)d; (void)in;
}

int main(int argc, char **argv)
{
    if (argc > 1) g_ch = (ma_uint32)atoi(argv[1]);
    if (argc > 2) g_period = (ma_uint32)atoi(argv[2]);
    if (argc > 3) g_capCh = (ma_uint32)atoi(argv[3]);
    ma_context_config cc = ma_context_config_init();
    cc.custom.onContextInit = ctx_init;
    cc.custom.onContextUninit = ctx_uninit;
    cc.custom.onDeviceInit = dev_init;
    cc.custom.onDeviceUninit = dev_uninit;
    cc.custom.onDeviceStart = dev_start;
    cc.custom.onDeviceStop = dev_stop;
    cc.custom.onDeviceRead = dev_read;
    cc.custom.onDeviceWrite = dev_write;
    ma_backend backends[] = { ma_backend_custom };
    ma_context ctx;
    if (ma_context_init(backends, 1, &cc, &ctx) != MA_SUCCESS) { puts("context init failed"); return 2; }
    ma_device_config c = ma_device_config_init(ma_device_type_duplex);
    c.sampleRate = 48000;
    c.periodSizeInFrames = 480;
    c.playback.format = ma_format_s16; c.playback.channels = 1;
    c.capture.format = ma_format_s16;  c.capture.channels = 1;
    c.dataCallback = on_data;
    ma_device dev;
    if (ma_device_init(&ctx, &c, &dev) != MA_SUCCESS) { puts("device init failed"); return 2; }
    ma_device_start(&dev);
    while (g_got < WANT) ma_sleep(5);
    ma_device_uninit(&dev);
    ma_context_uninit(&ctx);

    /* the ramp: each sample is the previous + 1 (wrapping 30000 -> 1); count the breaks */
    ma_uint32 breaks = 0, first = 0, start = 0;
    while (start < WANT && g_out[start] == 0) start++;          /* silence before the first callback */
    for (ma_uint32 i = start + 1; i < WANT; i++) {
        int a = (int)lrintf(g_out[i - 1] * 32768.0f), b = (int)lrintf(g_out[i] * 32768.0f);
        if (!(b == a + 1 || (a == 30000 && b == 1))) { if (!breaks) first = i; breaks++; }
    }
    printf("playback f32 x %u ch, period %u, capture %u ch: %u frames written, %u breaks in the ramp", g_ch, g_period, g_capCh, WANT - start, breaks);
    if (breaks) {
        printf(", first at %u:", first);
        for (ma_uint32 i = first - 3; i < first + 3; i++) printf(" %d", (int)lrintf(g_out[i] * 32768.0f));
    }
    printf("\n");
    return breaks ? 1 : 0;
}
