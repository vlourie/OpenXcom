#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Вылет корабля, механизм 3: видео взлёта (выезда) по одобренному начальному кадру. Видеомодель студии интро
(F:\AIStudio\Escape\gen_video.py: WanGP, LTX-2.5 22B distilled, 1280x800, 121 кадр ≈ 5 с): записи VIDEOS
студии не трогаем - свои клипы добавляются сюда и уходят в generate() студии. Проект:
docs/research/craft-launch-2026-10-22.md.

Только через очередь:
    py -3.13 tools/gpuq.py add --name craft-launch-video --prio 1 --cwd F:/AIStudio/WanGP -- \
        F:/AIStudio/runtime/env/Scripts/python.exe -u E:/OpenXCom/tools/hdart/craft_launch_video.py LAUNCH_MBT ltx
Выход art/craft_launch/video/<клип>/<модель>_s<N>.mp4 (+ .json). Подключать - только после выбора Vitali."""
import argparse
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STUDIO = Path(r"F:\AIStudio\Escape")
sys.path.insert(0, str(STUDIO))
import gen_cast as gc           # noqa: E402
import gen_video as gv          # noqa: E402

FRAMES = ROOT / "art" / "craft_launch" / "frames"
OUT = ROOT / "art" / "craft_launch" / "video"

NEG = ("people, person, crew, soldier, driver visible, open hatch, tracks, caterpillar tracks, wheels, tank rolling on "
       "the ground, second vehicle, explosion, gunfire, shooting, cut, scene change, text, subtitles, logo, watermark, "
       "morphing hull, melting metal, warped garage, camera shake")

CLIPS = {
    # выбор Vitali 22.10: «сид42 старт 1,0» (craft_launch_swap.py)
    "LAUNCH_MBT": dict(start=FRAMES / "STR_MBT_chosen.png", negative=NEG, prompt=(
        "Cinematic shot inside a gritty underground pirate base garage. A pale sand-coloured hover tank with a long gun "
        "floats half a metre above a big round brass turntable on a cushion of blue glowing air, all hatches closed. "
        "Amber warning beacons on the walls start to flash and spin. The brass turntable slowly rotates and turns the "
        "hovering tank to the right until its front faces the open arch with the lit concrete tunnel. The blue glow under "
        "the tank grows brighter, dust and steam swirl on the floor, and the hover tank glides smoothly off the turntable, "
        "floating above the floor without touching it, into the tunnel and up the smooth sloped ramp, getting smaller "
        "until it disappears into the tunnel. The camera stays still. Heavy engine hum, deep rumble.")),
    # 22.10 Vitali про LAUNCH_MBT: «он жопкой уезжает, а должен поворачиваться дулом туда и потом улетать» -
    # разворот на круге отдельным тактом, 7 с вместо 5, задний ход в негатив
    "LAUNCH_MBT2": dict(start=FRAMES / "STR_MBT_chosen.png", length=169, negative=NEG + (
        ", moving backwards, reversing, rear first, driving in reverse, sliding sideways, gun pointing away from the "
        "tunnel while moving, flying off before turning"), prompt=(
        "Cinematic shot inside a gritty underground pirate base garage, the camera is locked off and does not move. "
        "A pale sand-coloured hover tank with a long gun floats half a metre above a big round brass turntable on a "
        "cushion of blue glowing air, all hatches closed; its gun points to the left, away from the open tunnel arch "
        "on the right. Amber warning beacons on the walls start to flash. "
        "First the brass turntable slowly rotates a full half turn and carries the hovering tank around with it, "
        "the tank stays above the centre of the turntable while it turns, until the long gun points to the right, "
        "straight at the lit concrete tunnel, and we see the side and the back of the tank. "
        "Only then the turntable stops, the blue glow under the tank flares brighter, dust and steam swirl on the "
        "floor, and the hover tank moves forward, gun first, nose first, glides off the turntable into the tunnel and "
        "up the smooth sloped ramp, getting smaller until it disappears. Heavy engine hum, deep rumble.")),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clip", choices=sorted(CLIPS))
    ap.add_argument("model", choices=sorted(gv.MODELS))
    ap.add_argument("--seeds", type=int, default=2)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    gv.VIDEOS.update(CLIPS)
    out = OUT / a.clip
    todo = [(n, out / ("%s_s%d.mp4" % (a.model, n))) for n in range(1, a.seeds + 1)]
    if a.dry:
        print(CLIPS[a.clip]["prompt"])
        print([str(t) for _, t in todo])
        return
    out.mkdir(parents=True, exist_ok=True)
    todo = [x for x in todo if not x[1].is_file()]
    if not todo:
        print("[SKIP] всё готово")
        return
    api = gc.session("launch_" + a.clip + "_" + a.model)
    try:
        for n, t in todo:
            gv.generate(api, a.clip, a.model, n, t)
    finally:
        api.close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
