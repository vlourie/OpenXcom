"""A runtime switch for IAudioClient3 low-latency shared mode in the pinned miniaudio 0.11.25.

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
    py -3.13 tools/voice_ma_patch.py --check    0 if applied, 1 if pristine, 2 if neither
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


def state(text: str) -> str:
    """'applied', 'pristine' or 'unknown' (neither the marker nor every anchor)."""
    if MARK in text:
        return "applied"
    return "pristine" if all(text.count(a) == n for a, _, n in EDITS) else "unknown"


def apply(path: pathlib.Path = TARGET) -> bool:
    """Patches the file in place; returns True if it changed, False if it was already patched."""
    text = path.read_text(encoding="utf-8")
    s = state(text)
    if s == "applied":
        return False
    if s == "unknown":
        bad = [a.splitlines()[0] for a, _, n in EDITS if text.count(a) != n]
        raise SystemExit(f"{path}: not the pinned miniaudio 0.11.25 - anchors missing or doubled: {bad}")
    for anchor, repl, _ in EDITS:
        text = text.replace(anchor, repl)
    assert state(text) == "applied"
    path.write_text(text, encoding="utf-8", newline="\n")
    return True


def main() -> None:
    if "--check" in sys.argv:
        s = state(TARGET.read_text(encoding="utf-8"))
        print(f"{TARGET.name}: {s}")
        sys.exit({"applied": 0, "pristine": 1}.get(s, 2))
    changed = apply()
    print(f"{TARGET.name}: {'patched' if changed else 'already patched'} ({MARK})")


if __name__ == "__main__":
    main()
