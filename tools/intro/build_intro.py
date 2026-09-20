#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Вступление из твоих картинок и твоего голоса - без единой правки движка.

  1. сцены берёт из tools/intro/scenes.json (его пишет make_script.py);
  2. на каждую сцену берёт твою картинку и твой файл голоса;
  3. длительность слайда ставит ПО ДЛИНЕ ГОЛОСА, а не на глаз;
  4. склеивает голос в одну дорожку (музыка тише голоса) -> SOUND/intro_voice.ogg;
  5. картинку кладёт дважды: 320x200 с палитрой - классическому слою,
     ровно k x 320x200 - в hd/UI, HD-слой находит её по содержимому базовой;
  6. пишет рулсет, который перекрывает катсцену intro.

Что готовишь ты:
    <вход>/photo/01.png ... 16.png   картинки, лучше 4:2.5 (1280x800 и крупнее)
    <вход>/voice/01.wav ... 16.wav   голос на каждую сцену (wav, mp3, ogg - всё равно)
    <вход>/music.ogg                 подложка, необязательно

  python tools/intro/build_intro.py --in E:/intro --mod user/mods/hd
"""

import argparse
import io
import json
import os
import shutil
import subprocess
import sys

ENC = "utf-8-sig"
BASE_W, BASE_H = 320, 200
PHOTO_COLORS = 239          # цвета картинки живут в индексах 1..239
TEXT_BASE = 240             # подпись: движок рисует буквы в TEXT_BASE+1 .. +5
TEXT_RAMP = [(255, 255, 255), (214, 214, 214), (160, 160, 160), (96, 96, 96), (16, 16, 16)]

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def with_pillow():
    """PIL живёт в окружении генерации арта - уходим туда, если в этом его нет."""
    try:
        import PIL  # noqa: F401
        return
    except ImportError:
        pass
    venv = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "hdart", ".venv", "Scripts", "python.exe")
    venv = os.path.normpath(venv)
    if not os.path.exists(venv) or os.path.normcase(venv) == os.path.normcase(sys.executable):
        raise SystemExit("нет Pillow. Поставь его или запусти через " + venv)
    sys.exit(subprocess.call([venv, os.path.abspath(__file__)] + sys.argv[1:]))


def need(tool):
    path = shutil.which(tool)
    if not path:
        raise SystemExit("нет в PATH: " + tool)
    return path


def duration(ffprobe, path):
    out = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", path],
                         capture_output=True, text=True).stdout.strip()
    return float(out) if out else 0.0


def find_one(folder, stem):
    """Файл сцены по номеру, расширение любое."""
    if not os.path.isdir(folder):
        return None
    for name in sorted(os.listdir(folder)):
        base = name.rsplit(".", 1)[0]
        if base == stem:
            return os.path.join(folder, name)
    return None


def make_slide(src, base_png, hd_png, k):
    """Классический кадр 320x200 с палитрой и HD-кадр ровно в k раз больше.

    Индекс 0 картинкой не занят: движок считает его прозрачным. Хвост палитры -
    лесенка для подписи, иначе цвет подписи попал бы в цвет фотографии."""
    from PIL import Image, ImageOps
    import numpy as np

    photo = Image.open(src).convert("RGB")
    hd = ImageOps.fit(photo, (BASE_W * k, BASE_H * k), Image.LANCZOS)
    hd.save(hd_png)

    small = hd.resize((BASE_W, BASE_H), Image.LANCZOS)
    q = small.quantize(colors=PHOTO_COLORS, method=Image.MEDIANCUT, dither=Image.FLOYDSTEINBERG)
    idx = np.asarray(q, dtype=np.uint8) + 1

    pal = [0, 0, 0] + q.getpalette()[: PHOTO_COLORS * 3]
    pal += [0, 0, 0] * (TEXT_BASE - len(pal) // 3)      # промежуток и сам TEXT_BASE
    for c in TEXT_RAMP:
        pal += list(c)
    pal += [0, 0, 0] * (256 - len(pal) // 3)

    out = Image.frombytes("P", (BASE_W, BASE_H), idx.tobytes())
    out.putpalette(pal)
    out.save(base_png, optimize=True)


def build_track(ffmpeg, parts, total, music, music_db, out):
    """Голос по своим местам, музыка под ним - одна дорожка на всё вступление."""
    cmd = [ffmpeg, "-y", "-v", "error"]
    for _, f in parts:
        cmd += ["-i", f]
    if music:
        cmd += ["-stream_loop", "-1", "-i", music]
    chains, names = [], []
    for i, (start, _) in enumerate(parts):
        chains.append("[%d:a]aformat=sample_rates=44100:channel_layouts=stereo,"
                      "adelay=%d:all=1[v%d]" % (i, int(start * 1000), i))
        names.append("[v%d]" % i)
    graph = ";".join(chains) + ";" + "".join(names) + \
        "amix=inputs=%d:normalize=0:duration=longest[voice]" % len(names)
    if music:
        graph += (";[%d:a]aformat=sample_rates=44100:channel_layouts=stereo,"
                  "volume=%.1fdB,atrim=0:%.2f[bed];"
                  "[voice][bed]amix=inputs=2:normalize=0:duration=longest[out]"
                  % (len(parts), music_db, total))
        tap = "[out]"
    else:
        tap = "[voice]"
    cmd += ["-filter_complex", graph, "-map", tap, "-t", "%.2f" % total,
            "-c:a", "libvorbis", "-q:a", "5", out]
    subprocess.run(cmd, check=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="src", required=True, help="папка с photo/ и voice/")
    p.add_argument("--mod", default="user/mods/hd", help="куда класть - наш HD-мод")
    p.add_argument("--scenes", default="tools/intro/scenes.json", help="сцены от make_script.py")
    p.add_argument("--scale", type=int, default=4, help="во сколько раз HD-кадр больше базы")
    p.add_argument("--pause", type=float, default=1.2, help="тишина после голоса, секунд")
    p.add_argument("--music-db", type=float, default=-16.0, help="насколько тише голоса подложка")
    p.add_argument("--no-captions", action="store_true", help="без подписей, только голос")
    p.add_argument("--dry", action="store_true", help="только посчитать, ничего не писать")
    args = p.parse_args()

    ffmpeg, ffprobe = need("ffmpeg"), need("ffprobe")
    scenes = json.loads(io.open(args.scenes, encoding=ENC).read())

    plan, missing = [], []
    for i, sc in enumerate(scenes, 1):
        stem = "%02d" % i
        photo = find_one(os.path.join(args.src, "photo"), stem)
        voice = find_one(os.path.join(args.src, "voice"), stem)
        if not photo:
            missing.append("photo/%s.*" % stem)
        secs = duration(ffprobe, voice) if voice else 0.0
        plan.append({"n": i, "photo": photo, "voice": voice, "secs": secs,
                     "caption": sc.get("caption", ""), "text": sc.get("text", "")})
    if missing:
        raise SystemExit("нет файлов: " + ", ".join(missing))

    total = 0
    print("%-3s %-24s %7s  %s" % ("#", "картинка", "секунд", "голос"))
    for s in plan:
        s["hold"] = int(round(max(3.0, s["secs"] + args.pause))) if s["voice"] else 4
        total += s["hold"]
        print("%-3d %-24s %7d  %s" % (s["n"], os.path.basename(s["photo"]), s["hold"],
                                      os.path.basename(s["voice"]) if s["voice"] else "-"))
    print("всего %d:%02d" % (total // 60, total % 60))
    if args.dry:
        return

    mod = os.path.abspath(args.mod)
    res = os.path.join(mod, "Resources", "Intro")
    hdui = os.path.join(mod, "hd", "UI")
    sound = os.path.join(mod, "SOUND")
    rules = os.path.join(mod, "Ruleset")
    for d in (res, hdui, sound, rules):
        os.makedirs(d, exist_ok=True)

    for s in plan:
        stem = "intro_%02d" % s["n"]
        make_slide(s["photo"], os.path.join(res, stem + ".png"),
                   os.path.join(hdui, stem + ".png"), args.scale)

    parts, at = [], 0
    for s in plan:
        if s["voice"]:
            parts.append((float(at), s["voice"]))
        at += s["hold"]
    track = os.path.join(sound, "intro_voice.ogg")
    music = os.path.join(args.src, "music.ogg")
    if parts:
        build_track(ffmpeg, parts, float(total), music if os.path.exists(music) else "",
                    args.music_db, track)

    lines = ["# Сделано tools/intro/build_intro.py - руками не править", "",
             "extraSprites:"]
    for s in plan:
        stem = "intro_%02d" % s["n"]
        # _CPAL в имени: без него движок кладёт на картинку палитру состояния
        # (Mod::loadExtraSprite), и HD-снимок сверяется с чужими цветами
        lines += ["  - type: %s_CPAL" % stem.upper(),
                  "    singleImage: true",
                  "    width: %d" % BASE_W,
                  "    height: %d" % BASE_H,
                  "    files:",
                  "      0: Resources/Intro/%s.png" % stem]
    lines += ["", "musics:", "  - type: INTRO_VOICE", "",
              "cutscenes:",
              "  # без delete слайды не заменяются, а ДОПИСЫВАЮТСЯ к чужим (RuleVideo::load)",
              "  - delete: intro",
              "  - type: intro", "    slideshow:",
              "      transitionSeconds: 8",
              "      musicId: INTRO_VOICE",
              "      slides:"]
    for s in plan:
        lines.append("        - imagePath: Resources/Intro/intro_%02d.png" % s["n"])
        lines.append("          transitionSeconds: %d" % s["hold"])
        if s["caption"] and not args.no_captions:
            lines += ["          caption: %s" % s["caption"],
                      "          captionPos: [10, 148]",
                      "          captionSize: [300, 46]",
                      "          captionColor: %d" % TEXT_BASE,
                      "          captionAlign: 1",       # 0 слева, 1 по центру, 2 справа
                      "          captionVerticalAlign: 2"]  # 0 верх, 1 середина, 2 низ
    rul = os.path.join(rules, "intro.rul")
    io.open(rul, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
    print("рулсет: ", rul)
    print("дорожка:", track if parts else "голоса нет - дорожку не делал")


if __name__ == "__main__":
    with_pillow()
    main()
