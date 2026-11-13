#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Огонь целиком: четыре фазы одной петли за один запуск Qwen-Image-2.1.

Чем отличается от gen_tile.py, ради чего отдельный скрипт:

    1. Нет ромба. Огонь - не пол и не предмет на полу, а накладка поверх клетки.
       Значит нет ни прохода «плоскость», ни обрезки по альфе оригинала: силуэт
       пламени рисует художник, а не MCD.
    2. Четыре кадра - ОДИН огонь в четырёх фазах. Поэтому у всех кадров одной
       попытки одно зерно и один промпт: меняется только картинка на входе.
       Разное зерно на кадр даёт четыре разных костра, и в игре это дёргается.
    3. Движок рисует огонь без затенения клетки (Map.cpp, shade = 0) - свет несёт
       сама картинка. Промпт просит белое ядро и светящийся край, негатив гасит
       тёмные примеси.
    4. Прозрачность. Модель почти всегда возвращает фон цветом, а не альфой,
       поэтому серая подложка снимается арифметикой: альфа по удалению цвета от
       подложки, цвет - обратное смешивание. На RGBA от модели не рассчитываем
       (--alpha keep, если вдруг отдала).

Приёмка у огня одна - петля, а не отдельный кадр. Скрипт сразу кладёт рядом
fire_loop_t<n>.gif: если в нём дёргается, кадры не годятся, как бы ни были красивы.

    tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\gen_fire.py ^
        --set SMOKE.PCK --frame 0,1,2,3 --tries 2

Кладёт в <sheets>\<набор>\fire\:
    fire_<кадр>_t<n>_1hd.png   что вышло из модели (как есть, 2K)
    fire_<кадр>_t<n>_cut.png   снятая подложка, игровой габарит, RGBA
    fire_sheet_t<n>.png        лист: оригиналы сверху, результат снизу
    fire_loop_t<n>.gif         петля из четырёх кадров - главная проверка

В пак это пока НЕ идёт: сначала смотрим глазами.
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import gen_hd                                       # noqa: E402  (он же ставит HF_HOME)
from PIL import Image, ImageDraw                    # noqa: E402

# Промпт короткий намеренно: доктрина Qwen-Image-2.1 читает длинный список «сохрани то-то»
# как задание это нарисовать (docs, разбор 2.1). На картинку ссылаемся тегом <image1>:
# «Picture 1» и «the first image» её системный промпт называет запрещёнными формами (R-045).
PROMPT_FIRE = (
    "<image1> is the low-resolution original of one animation phase of a burning fire, shown on a "
    "flat grey preview panel. The panel is interface, not part of the sprite. "
    "Use case: sketch-to-render. Asset type: polished 4x HD fire sprite for an X-COM-style isometric "
    "strategy game. "
    "Redraw this same flame in clean high-detail game artwork: white-hot core, yellow body, orange "
    "tips, soft glowing edges, fine flickering tongues. Keep the position, the height, the width and "
    "the yellow-orange palette of <image1>. "
    "The fire is drawn unshaded in the game, so the sprite itself carries all the light: bright, "
    "luminous, no dark muddy areas. "
    "Output one isolated flame, centered as in <image1>, on a fully transparent RGBA background. "
    "No smoke, no ground, no tile, no objects, no panel, no frame, no text, no watermark.")

# Второй проход - только если первый принёс мусор вокруг пламени (--pass2)
PROMPT_CLEAN = (
    "<image1> is an HD fire sprite. Keep the flame exactly as it is: same shape, same size, same "
    "position, same colors, same brightness. "
    "Remove everything that is not the flame itself: background fill, panel, haze, smoke, ground, "
    "shadow, outline, frame. "
    "Output the same flame alone on a fully transparent RGBA background.")

PHASE = " This is phase {n} of 4 of the loop."

NEGATIVE = ("smoke, dark smoke, soot, dark muddy colors, black areas, grey background, colored "
            "background, opaque background, panel, frame, border, outline, drop shadow, ground, "
            "terrain, tile, objects, sparks flying away, changed position, changed size, changed "
            "palette, cartoon, anime, vector art, photorealism, 3D render, blur, text, watermark")


def load_set(sheets, set_name):
    set_dir = os.path.join(sheets, set_name)
    with open(os.path.join(set_dir, "layout.json"), encoding="utf-8-sig") as f:
        lay = json.load(f)
    hints = {}
    hp = os.path.join(set_dir, "hints.json")
    if os.path.exists(hp):
        with open(hp, encoding="utf-8-sig") as f:
            hints = {int(k): v for k, v in json.load(f).items()}
    sheet = Image.open(os.path.join(set_dir, "original.png")).convert("RGBA")
    return set_dir, lay, hints, sheet


def frame_of(sheet, lay, i):
    """Кадр i из листа, в исходных пикселях, с прозрачностью."""
    fw, fh, m, cols = lay["frame_w"], lay["frame_h"], lay["margin"], lay["columns"]
    r, c = divmod(i, cols)
    x, y = m + c * (fw + 2 * m), m + r * (fh + 2 * m)
    return sheet.crop((x, y, x + fw, y + fh))


def on_panel(frame, zoom, panel):
    """Кадр один, крупно, на ровной серой подложке - ровно то, что человек кидает в чат."""
    big = frame.resize((frame.width * zoom, frame.height * zoom), Image.NEAREST)
    out = Image.new("RGBA", big.size, tuple(panel) + (255,))
    out.alpha_composite(big)
    return out.convert("RGB")


def run_pass(painter, args, prompt, image, seed):
    torch = painter.torch
    W, H = gen_hd.qwen21_size(image.width, image.height, args.mp)
    src = image.convert("RGB").resize((W, H), Image.LANCZOS)
    kw = {"prompt": prompt, "num_inference_steps": args.steps,
          "generator": torch.Generator("cuda").manual_seed(seed)}
    if "image" in painter.accepts:
        kw["image"] = src
    elif "images" in painter.accepts:
        kw["images"] = [src]
    if "negative_prompt" in painter.accepts:
        kw["negative_prompt"] = NEGATIVE
    if "true_cfg_scale" in painter.accepts:
        kw["true_cfg_scale"] = args.cfg
    elif "guidance_scale" in painter.accepts:
        kw["guidance_scale"] = args.cfg
    if "width" in painter.accepts:
        kw["width"], kw["height"] = W, H
    return painter.pipe(**kw).images[0]


def unpanel(painted, panel, soft):
    """Снять ровную подложку: альфа - по удалению цвета от неё, цвет - обратным смешиванием.
    Полупрозрачную кайму нельзя просто оставить смешанной с серым: в игре она сядет на тёмный
    пол и нарисует серый ореол вокруг пламени (те же грабли, что с каймой плиток)."""
    import numpy as np
    a = np.asarray(painted.convert("RGB"), dtype=np.float32)
    p = np.asarray(panel, dtype=np.float32)
    d = np.abs(a - p).max(axis=2)
    alpha = np.clip(d / float(soft), 0.0, 1.0)
    k = np.maximum(alpha, 1e-3)[..., None]
    rgb = np.clip(p + (a - p) / k, 0, 255)
    out = np.dstack([rgb, alpha[..., None] * 255.0]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def to_footprint(rgba, frame, scale, grow):
    """Игровой габарит: кадр * scale. Силуэт пламени - свой, но за габарит оригинала,
    расширенный на grow исходных пикселей, не выпускаем: иначе огонь полезет на соседей."""
    cw, ch = frame.width * scale, frame.height * scale
    body = rgba.resize((cw, ch), Image.LANCZOS)
    box = frame.split()[3].point(lambda v: 255 if v > 0 else 0).getbbox()
    if box is None:
        return body
    x0, y0, x1, y1 = box
    x0, y0 = max(0, x0 - grow), max(0, y0 - grow)
    x1, y1 = min(frame.width, x1 + grow), min(frame.height, y1 + grow)
    mask = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(mask).rectangle((x0 * scale, y0 * scale, x1 * scale - 1, y1 * scale - 1), fill=255)
    out = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    out.paste(body, (0, 0), mask)
    return out


def checker(im, step=16):
    """Прозрачность на шахматке - иначе на чёрном фоне ничего не понять."""
    bg = Image.new("RGB", im.size, (110, 110, 110))
    d = ImageDraw.Draw(bg)
    for y in range(0, im.height, step):
        for x in range(0, im.width, step):
            if (x // step + y // step) % 2 == 0:
                d.rectangle((x, y, x + step - 1, y + step - 1), fill=(140, 140, 140))
    bg.paste(im.convert("RGBA"), (0, 0), im.convert("RGBA"))
    return bg


def save_loop(cuts, path, zoom, ms):
    """Петля так, как её крутит игра: на тёмном полу, без затенения."""
    frames = []
    for c in cuts:
        bg = Image.new("RGBA", c.size, (24, 20, 18, 255))
        bg.alpha_composite(c)
        frames.append(bg.convert("RGB").resize((c.width * zoom, c.height * zoom), Image.NEAREST))
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=ms, loop=0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=gen_hd.DEFAULT_MODELS_DIR)
    ap.add_argument("--sheets", default="art/TERRAIN")
    ap.add_argument("--set", dest="set_name", default="SMOKE.PCK")
    ap.add_argument("--frame", default="0,1,2,3", help="кадры петли через запятую")
    ap.add_argument("--tries", type=int, default=1, help="сколько раз нарисовать всю петлю")
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--steps", type=int, default=40)
    ap.add_argument("--cfg", type=float, default=1.0, help="2.1 рассчитана рисовать без направляющей")
    ap.add_argument("--mp", type=float, default=2.0, help="мегапикселей на проход (2.0 - родные 2K)")
    ap.add_argument("--zoom", type=int, default=24, help="во сколько раз увеличить кадр на входе")
    ap.add_argument("--scale", type=int, default=4, help="масштаб пака для готового кадра")
    ap.add_argument("--grow", type=int, default=3, help="на сколько исходных пикселей можно выйти за габарит")
    ap.add_argument("--soft", type=int, default=48, help="порог снятия подложки (меньше - мягче край)")
    ap.add_argument("--panel", default="90,90,96", help="цвет подложки")
    ap.add_argument("--alpha", default="unpanel", choices=["unpanel", "keep"],
                    help="unpanel - снять подложку арифметикой; keep - модель вернула RGBA")
    ap.add_argument("--gif-ms", type=int, default=125, dest="gif_ms")
    ap.add_argument("--pass2", action="store_true", help="второй проход: добить фон и мусор")
    ap.add_argument("--no-phase", action="store_true", dest="no_phase",
                    help="не дописывать к промпту номер фазы")
    ap.add_argument("--model", default="")
    ap.add_argument("--offload", default="model", choices=["model", "seq", "none"])
    args = ap.parse_args()

    panel = tuple(int(v) for v in args.panel.split(","))
    set_dir, lay, hints, sheet = load_set(args.sheets, args.set_name)
    frames = [int(v) for v in args.frame.split(",") if v.strip()]
    if not frames:
        raise SystemExit("нечего рисовать: --frame пуст")
    out_dir = os.path.join(set_dir, "fire")
    os.makedirs(out_dir, exist_ok=True)

    ns = argparse.Namespace(models=args.models, qwen21_model=args.model, qwen21_steps=args.steps,
                            qwen21_cfg=args.cfg, qwen21_mp=args.mp, qwen21_strength=0.0,
                            qwen21_offload=args.offload, qwen21_thrifty=False,
                            qwen21_ref="", qwen21_ref_mp=1.0, qwen21_prompt="strict",
                            qwen21_hint="off", qwen21_ref_order="ref-first")
    painter = gen_hd.Qwen21Painter(ns, {"ground": ("", "")})

    t0 = time.time()
    total = len(frames) * args.tries
    done = 0
    for t in range(args.tries):
        seed = args.seed + t * 7919          # одно зерно на всю петлю - кадры должны быть роднёй
        cuts, tops, bottoms = [], [], []
        for n, i in enumerate(frames, 1):
            frame = frame_of(sheet, lay, i)
            src = on_panel(frame, args.zoom, panel)
            prompt = PROMPT_FIRE + ("" if args.no_phase else PHASE.replace("{n}", str(n)))
            print("попытка %d/%d, кадр %d (%s) | вход %dx%d, зерно %d"
                  % (t + 1, args.tries, i, hints.get(i, "без подсказки"),
                     src.width, src.height, seed), flush=True)
            hd = run_pass(painter, args, prompt, src, seed)
            gen_hd.save_png(hd, os.path.join(out_dir, "fire_%d_t%d_1hd.png" % (i, t + 1)))
            if args.pass2:
                hd = run_pass(painter, args, PROMPT_CLEAN, hd, seed + 101)
                gen_hd.save_png(hd, os.path.join(out_dir, "fire_%d_t%d_2clean.png" % (i, t + 1)))
            rgba = hd.convert("RGBA") if args.alpha == "keep" else unpanel(hd, panel, args.soft)
            cut = to_footprint(rgba, frame, args.scale, args.grow)
            gen_hd.save_png(cut, os.path.join(out_dir, "fire_%d_t%d_cut.png" % (i, t + 1)))
            cuts.append(cut)
            tops.append(gen_hd.label(checker(frame.resize(src.size, Image.NEAREST)), "оригинал %d" % i))
            bottoms.append(gen_hd.label(checker(cut.resize(src.size, Image.NEAREST)), "кадр %d" % i))
            done += 1
            el = time.time() - t0
            print("  %s, осталось ~%s" % (gen_hd.human_time(el),
                                          gen_hd.human_time(el / done * (total - done))), flush=True)
        h = 360
        fit = lambda ps: [p.resize((max(1, round(h * p.width / p.height)), h), Image.LANCZOS) for p in ps]
        rows = [gen_hd.side_by_side(fit(tops)), gen_hd.side_by_side(fit(bottoms))]
        board = Image.new("RGB", (max(r.width for r in rows), sum(r.height for r in rows) + 8),
                          (32, 32, 36))
        y = 0
        for r in rows:
            board.paste(r, (0, y)); y += r.height + 8
        sheet_path = os.path.join(out_dir, "fire_sheet_t%d.png" % (t + 1))
        gif_path = os.path.join(out_dir, "fire_loop_t%d.gif" % (t + 1))
        gen_hd.save_png(board, sheet_path)
        save_loop(cuts, gif_path, max(1, 8 // args.scale * 2), args.gif_ms)
        print("  лист: %s" % sheet_path)
        print("  петля: %s  <- смотреть в первую очередь" % gif_path)

    print("готово за %s" % gen_hd.human_time(time.time() - t0))


if __name__ == "__main__":
    main()
