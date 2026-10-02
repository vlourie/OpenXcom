"""Local patches of the pinned miniaudio 0.11.25: the duplex-loop fix of the "robot" (DUPLEX_EDITS, below)
and a runtime switch for IAudioClient3 low-latency shared mode (EDITS).

miniaudio can only turn that mode off at compile time (MA_WASAPI_NO_LOW_LATENCY_SHARED_MODE). The
"robot" at the far end of the launcher voice (docs/research/voice-robot-2026-10-02.md) needs it as one
of the switches tried one at a time in one build, so this adds, modelled on wasapi.noHardwareOffloading:
    ma_device_config.wasapi.noLowLatencySharedMode   - set to 1: plain IAudioClient::Initialize
    ma_device.wasapi.noLowLatencySharedMode          - the copy the device keeps (also for rerouting)
    ma_device.wasapi.usingAudioClient3Playback/Capture - how each stream was really initialized
Nothing changes while the new field is 0: the patched condition is the original one behind an
"if (!noLowLatencySharedMode)".

Applied by tools/voice_deps.py --audio before compiling xpaudio.c; idempotent. miniaudio.h is not in
git (portal/.gitignore), so the patch lives here as exact-text replacements, each anchor checked to
occur exactly the expected number of times in the pristine file.
    py -3.13 tools/voice_ma_patch.py            apply to portal/third_party/voice/miniaudio.h
    py -3.13 tools/voice_ma_patch.py --check    0 if all applied, 1 if some pristine, 2 if a patch fits neither
"""
import pathlib
import sys

sys.stdout.reconfigure(encoding="utf-8")
TARGET = pathlib.Path(__file__).resolve().parent.parent / "portal" / "third_party" / "voice" / "miniaudio.h"
MARK = "noLowLatencySharedMode"

# (anchor, replacement, expected count in the pristine file)
EDITS = [
    # ma_device_config.wasapi
    ("        ma_bool8 noHardwareOffloading;      /* Disables WASAPI's hardware offloading feature. */\n",
     "        ma_bool8 noHardwareOffloading;      /* Disables WASAPI's hardware offloading feature. */\n"
     "        ma_bool8 noLowLatencySharedMode;    /* xp: when set to true, does not try IAudioClient3 low-latency shared mode (plain IAudioClient::Initialize). */\n", 1),
    # ma_device.wasapi
    ("            ma_bool8 noHardwareOffloading;\n"
     "            ma_bool8 allowCaptureAutoStreamRouting;\n",
     "            ma_bool8 noHardwareOffloading;\n"
     "            ma_bool8 noLowLatencySharedMode;                        /* xp */\n"
     "            ma_bool8 usingAudioClient3Playback;                     /* xp: the playback stream was initialized through IAudioClient3 */\n"
     "            ma_bool8 usingAudioClient3Capture;                      /* xp: same for capture / loopback */\n"
     "            ma_bool8 allowCaptureAutoStreamRouting;\n", 1),
    # ma_device_init_internal_data__wasapi
    ("    ma_bool32 noHardwareOffloading;\n"
     "    ma_uint32 loopbackProcessID;\n"
     "    ma_bool32 loopbackProcessExclude;\n"
     "\n"
     "    /* Output. */\n",
     "    ma_bool32 noHardwareOffloading;\n"
     "    ma_bool32 noLowLatencySharedMode;   /* xp */\n"
     "    ma_uint32 loopbackProcessID;\n"
     "    ma_bool32 loopbackProcessExclude;\n"
     "\n"
     "    /* Output. */\n", 1),
    # the condition that chooses IAudioClient3
    ("            if ((streamFlags & MA_AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM) == 0 || nativeSampleRate == wf.nSamplesPerSec) {\n",
     "            if (pData->noLowLatencySharedMode) {   /* xp */\n"
     "                ma_log_postf(ma_context_get_log(pContext), MA_LOG_LEVEL_DEBUG, \"[WASAPI] Not using IAudioClient3 because noLowLatencySharedMode is set.\\n\");\n"
     "            } else\n"
     "            if ((streamFlags & MA_AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM) == 0 || nativeSampleRate == wf.nSamplesPerSec) {\n", 1),
    # reinit (rerouting): config copy and the result
    ("    data.noHardwareOffloading       = pDevice->wasapi.noHardwareOffloading;\n",
     "    data.noHardwareOffloading       = pDevice->wasapi.noHardwareOffloading;\n"
     "    data.noLowLatencySharedMode     = pDevice->wasapi.noLowLatencySharedMode;   /* xp */\n", 1),
    ("        pDevice->wasapi.pAudioClientCapture         = data.pAudioClient;\n"
     "        pDevice->wasapi.pCaptureClient              = data.pCaptureClient;\n",
     "        pDevice->wasapi.pAudioClientCapture         = data.pAudioClient;\n"
     "        pDevice->wasapi.pCaptureClient              = data.pCaptureClient;\n"
     "        pDevice->wasapi.usingAudioClient3Capture    = (ma_bool8)data.usingAudioClient3;   /* xp */\n", 1),
    ("        pDevice->wasapi.pAudioClientPlayback         = data.pAudioClient;\n"
     "        pDevice->wasapi.pRenderClient                = data.pRenderClient;\n",
     "        pDevice->wasapi.pAudioClientPlayback         = data.pAudioClient;\n"
     "        pDevice->wasapi.pRenderClient                = data.pRenderClient;\n"
     "        pDevice->wasapi.usingAudioClient3Playback    = (ma_bool8)data.usingAudioClient3;   /* xp */\n", 1),
    # init: config copies (device, then the capture and playback halves) and the results
    ("    pDevice->wasapi.noHardwareOffloading   = pConfig->wasapi.noHardwareOffloading;\n",
     "    pDevice->wasapi.noHardwareOffloading   = pConfig->wasapi.noHardwareOffloading;\n"
     "    pDevice->wasapi.noLowLatencySharedMode = pConfig->wasapi.noLowLatencySharedMode;   /* xp */\n", 1),
    ("        data.noHardwareOffloading       = pConfig->wasapi.noHardwareOffloading;\n",
     "        data.noHardwareOffloading       = pConfig->wasapi.noHardwareOffloading;\n"
     "        data.noLowLatencySharedMode     = pConfig->wasapi.noLowLatencySharedMode;   /* xp */\n", 2),
    ("        pDevice->wasapi.pAudioClientCapture              = data.pAudioClient;\n"
     "        pDevice->wasapi.pCaptureClient                   = data.pCaptureClient;\n",
     "        pDevice->wasapi.pAudioClientCapture              = data.pAudioClient;\n"
     "        pDevice->wasapi.pCaptureClient                   = data.pCaptureClient;\n"
     "        pDevice->wasapi.usingAudioClient3Capture         = (ma_bool8)data.usingAudioClient3;   /* xp */\n", 1),
    ("        pDevice->wasapi.pAudioClientPlayback             = data.pAudioClient;\n"
     "        pDevice->wasapi.pRenderClient                    = data.pRenderClient;\n",
     "        pDevice->wasapi.pAudioClientPlayback             = data.pAudioClient;\n"
     "        pDevice->wasapi.pRenderClient                    = data.pRenderClient;\n"
     "        pDevice->wasapi.usingAudioClient3Playback        = (ma_bool8)data.usingAudioClient3;   /* xp */\n", 1),
]

# The "robot" itself (03.10): in the duplex loop of ma_device_audio_thread__default_read_write (WASAPI uses it)
# the output of one callback is converted to the device format in pieces of playbackDeviceData - 4096 bytes,
# that is 4096 / bytes per device frame - and every piece is converted from the START of playbackClientData.
# At f32 x 2 ch a piece holds 512 frames, more than our 480, and nothing happens; at a 5.1 mix (f32 x 6 ch,
# Creative SB X-Fi) it holds 170 frames, and each 10 ms plays its first 170 frames, those again and its
# first 140. The fix advances the client pointer by the frames the converter took.
MARK_DUPLEX = "pRunningPlaybackClientData"
DUPLEX_EDITS = [
    ("                        ma_uint8* pRunningCapturedDeviceFrames = ma_offset_ptr(capturedDeviceData, capturedDeviceFramesProcessed * ma_get_bytes_per_frame(pDevice->capture.internalFormat,  pDevice->capture.internalChannels));\n",
     "                        ma_uint8* pRunningCapturedDeviceFrames = ma_offset_ptr(capturedDeviceData, capturedDeviceFramesProcessed * ma_get_bytes_per_frame(pDevice->capture.internalFormat,  pDevice->capture.internalChannels));\n"
     "                        ma_uint8* pRunningPlaybackClientData = playbackClientData;   /* xp: where the next piece for the device starts */\n", 1),
    ("                            result = ma_data_converter_process_pcm_frames(&pDevice->playback.converter, playbackClientData, &convertedClientFrameCount, playbackDeviceData, &convertedDeviceFrameCount);\n",
     "                            result = ma_data_converter_process_pcm_frames(&pDevice->playback.converter, pRunningPlaybackClientData, &convertedClientFrameCount, playbackDeviceData, &convertedDeviceFrameCount);   /* xp */\n", 1),
    ("                            capturedClientFramesToProcessThisIteration -= (ma_uint32)convertedClientFrameCount;  /* Safe cast. */\n"
     "                            if (capturedClientFramesToProcessThisIteration == 0) {\n"
     "                                break;\n"
     "                            }\n",
     "                            capturedClientFramesToProcessThisIteration -= (ma_uint32)convertedClientFrameCount;  /* Safe cast. */\n"
     "                            if (capturedClientFramesToProcessThisIteration == 0) {\n"
     "                                break;\n"
     "                            }\n"
     "                            pRunningPlaybackClientData = ma_offset_ptr(pRunningPlaybackClientData, convertedClientFrameCount * ma_get_bytes_per_frame(pDevice->playback.format, pDevice->playback.channels));   /* xp */\n", 1),
]

PATCHES = [(MARK, EDITS), (MARK_DUPLEX, DUPLEX_EDITS)]


def state(text: str, mark: str = MARK, edits: list = EDITS) -> str:
    """'applied', 'pristine' or 'unknown' (neither the marker nor every anchor) - of one patch."""
    if mark in text:
        return "applied"
    return "pristine" if all(text.count(a) == n for a, _, n in edits) else "unknown"


def apply(path: pathlib.Path = TARGET) -> bool:
    """Applies every patch not yet in the file; returns True if it changed, False if all were already there."""
    text = path.read_text(encoding="utf-8")
    changed = False
    for mark, edits in PATCHES:
        s = state(text, mark, edits)
        if s == "applied":
            continue
        if s == "unknown":
            bad = [a.splitlines()[0] for a, _, n in edits if text.count(a) != n]
            raise SystemExit(f"{path}: not the pinned miniaudio 0.11.25 - anchors missing or doubled: {bad}")
        for anchor, repl, _ in edits:
            text = text.replace(anchor, repl)
        assert state(text, mark, edits) == "applied"
        changed = True
    if changed:
        path.write_text(text, encoding="utf-8", newline="\n")
    return changed


def main() -> None:
    if "--check" in sys.argv:
        text = TARGET.read_text(encoding="utf-8")
        states = [state(text, m, e) for m, e in PATCHES]
        print(f"{TARGET.name}: " + ", ".join(f"{m} {s}" for (m, _), s in zip(PATCHES, states)))
        sys.exit(0 if all(s == "applied" for s in states) else 2 if "unknown" in states else 1)
    changed = apply()
    print(f"{TARGET.name}: {'patched' if changed else 'already patched'} ({', '.join(m for m, _ in PATCHES)})")


if __name__ == "__main__":
    main()
