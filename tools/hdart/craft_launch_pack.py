#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Вылет корабля, механизм 3: одобренные ролики -> файлы игры. MPEG-1 960x576 (декодер pl_mpeg в движке,
src/Engine/HdVideo), среднее качество (-q:v 8, ~1,6 МБ на 7 с - замер 22.10), без звука: звук взлёта играет
сама игра (takeoffSound корабля). Посадка - тот же ролик задом наперёд, отдельным файлом (дешевле, чем
ролик из одних опорных кадров: 1,5 + 1,5 МБ против 5,5). В начале и в конце - короткий переход из чёрного
и в чёрный.

    py -3.13 tools/hdart/craft_launch_pack.py            # перегнать в art/craft_launch/pack/LAUNCH/
    py -3.13 tools/hdart/craft_launch_pack.py --install --yes   # + в мод hd через манифест (обе копии)

В моде: hd/LAUNCH/<тип корабля>.mpg (вылет) и hd/LAUNCH/<тип корабля>.land.mpg (посадка).
Проект: docs/research/craft-launch-2026-10-22.md."""
import argparse
import hashlib
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

VIDEO = os.path.join(ROOT, "art", "craft_launch", "video")
OUT = os.path.join(ROOT, "art", "craft_launch", "pack", "LAUNCH")
SIZE, Q, FADE = "960x576", "8", 0.3
START_SRC_REL = "Пиратки/Dioxine_XPiratez/user/mods/Piratez/Resources/Sounds/alert.wav"
START_SRC = os.path.join(ROOT, START_SRC_REL)

# тип корабля в рулсете -> одобренный ролик (слово Vitali 22.10)
CLIPS = {
    "STR_MBT": ("LAUNCH_MBT_chosen.mp4", "Vitali 22.10: МБТ - s2 второго прохода (разворот дулом к туннелю)"),
    "STR_DRAKKAR": ("LAUNCH_DRAKKAR_chosen.mp4", "Vitali 22.10: Drakkar - ltx_s1 второго прохода"),
    "STR_HUEY": ("LAUNCH_HUEY_chosen.mp4", "Vitali 22.10: вертолёт - ltx_s1 второго прохода"),
}


def ffmpeg():
    exe = shutil.which("ffmpeg")
    if not exe:
        raise SystemExit("нет ffmpeg в PATH")
    return exe


def duration(path):
    r = subprocess.run([shutil.which("ffprobe") or "ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", path], capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def encode(src, dst, reverse):
    d = duration(src)
    vf = ("reverse," if reverse else "") + "scale=%s:flags=lanczos,fade=t=in:st=0:d=%.2f,fade=t=out:st=%.2f:d=%.2f" % (
        SIZE.replace("x", ":"), FADE, d - FADE, FADE)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + ".tmp.mpg"
    subprocess.run([ffmpeg(), "-loglevel", "error", "-y", "-i", src, "-vf", vf, "-an", "-c:v", "mpeg1video",
                    "-q:v", Q, "-f", "mpeg", tmp], check=True)
    os.replace(tmp, dst)
    return os.path.getsize(dst)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", action="store_true", help="в мод hd через манифест build_hd_pack")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    os.chdir(ROOT)
    sys.stdout.reconfigure(encoding="utf-8")
    plan = []
    for craft, (clip, approval) in CLIPS.items():
        src = os.path.join(VIDEO, clip)
        for suffix, rev in ((".mpg", False), (".land.mpg", True)):
            dst = os.path.join(OUT, craft + suffix)
            n = encode(src, dst, rev)
            print("  %s%s: %.2f МБ" % (craft, suffix, n / 1e6))
            plan.append(("LAUNCH/" + craft + suffix, dst, clip, approval))
    # механизм 2, команда на старт: тревога над ангаром и её звук - сирена из Пираток (huntAlertSound)
    shutil.copyfile(START_SRC, os.path.join(OUT, "start.wav"))
    plan.append(("LAUNCH/start.wav", os.path.join(OUT, "start.wav"), START_SRC_REL, "Vitali 22.10: «делай» - тревога и сирена перед стартом"))
    print("всего %.1f МБ" % (sum(os.path.getsize(p) for _r, p, _c, _a in plan) / 1e6))
    if not a.install:
        return 0
    if not a.yes:
        raise SystemExit("сухой прогон; --yes - записать в мод")
    import build_hd_pack as bp
    man = bp.load()
    for rel, p, clip, approval in plan:
        bp.stage(man, rel, p, generator="craft_launch", generator_version="craft_launch_pack.py 22.10 q%s %s" % (Q, SIZE),
                 source_path=(clip if clip.startswith("Пиратки/") else "art/craft_launch/video/" + clip), approved=True, approval=approval,
                 source_frame="LAUNCH:" + rel.split("/")[1])
    rels = [r for r, _p, _c, _a in plan]
    bp.save(man, why="craft_launch: %d роликов вылета и посадки" % len(rels))
    print("game:", bp.install(man, "game", only=rels))
    print("repo:", bp.install(man, "repo", only=rels))
    for r in rels:
        for root in bp.TARGETS.values():
            with open(os.path.join(root, r), "rb") as f:
                if hashlib.sha256(f.read()).hexdigest() != man["files"][r]["sha256"]:
                    raise SystemExit("РАСХОДИТСЯ %s %s" % (root, r))
    print("сверено: %d файлов в обеих копиях" % len(rels))
    return 0


if __name__ == "__main__":
    sys.exit(main())
