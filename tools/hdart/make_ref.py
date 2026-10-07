#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Эталон материала для покраски полов: Qwen-Image-2.1 рисует несколько образцов грунта
с нуля (по тексту, без входной картинки - ей ничего не мешает), ты смотришь лист и тычешь
в лучший. Выбранный ложится в <sheets>\<набор>\ref.png и дальше сам подхватывается
gen_hd.py --painter qwen21: все полы набора красятся "как здесь".

Зачем: по одной клетке 32x40 модель не может понять, каким должен быть НАШ песок - она
достаёт песок из своей головы, и у каждого пола он свой. Эталон - это тот самый вопрос
"а как надо", заданный один раз на вид грунта, а не 17 раз молча.

    (окружение то же, что у --painter qwen21)
    tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\make_ref.py ^
        --sheets art/TERRAIN --set DESERT.PCK --what "yellow desert sand" --count 6
    -> art/TERRAIN\DESERT.PCK\refs\ref_1.png ... ref_6.png и refs\sheet.png (лист с номерами)

    tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\make_ref.py ^
        --sheets art/TERRAIN --set DESERT.PCK --pick 3
    -> art/TERRAIN\DESERT.PCK\ref.png

`--what` можно не писать: тогда берётся тема грунта набора (та же, что у gen_hd).
`--mp` - размер образца (2.0 - родные 2K модели), `--steps`/`--cfg` - как у gen_hd.
"""
import argparse
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import gen_hd                                      # noqa: E402  (он же ставит HF_HOME)
from PIL import Image, ImageDraw                   # noqa: E402

# образец материала, а не картинка: ровный свет, никаких предметов, земля во весь кадр
REF_STYLE = ("Hand-painted top-down game terrain material: {what}. Seen straight from above, "
             "flat even daylight, matte surface, fine natural grain, muted natural colors, "
             "continuous ground filling the whole frame, no objects, no props, no shadows, "
             "no horizon, sharp readable texture, consistent X-COM game asset style.")
REF_NEGATIVE = ("objects, props, plants, rocks, bones, skulls, buildings, characters, border, frame, "
                "text, watermark, vignette, perspective, horizon, sky, tiles, grid, seamless pattern, "
                "ornament, 3d render, cgi, glossy, wet look, photograph, depth of field, blurry")


def subject_of(set_dir, set_name):
    """Чем описать материал. Сначала - подсказка самого первого пола набора: она конкретнее всего
    («yellow desert sand»), её писали руками и она же идёт в промпт покраски. Если подсказок нет,
    берётся голова темы набора («desert») - но это уже грубо, лучше написать --what самому."""
    hints = os.path.join(set_dir, "hints.json")
    if os.path.exists(hints):
        import json
        try:
            with open(hints, encoding="utf-8-sig") as f:
                table = json.load(f)
        except ValueError:
            table = {}
        keys = sorted((int(k) for k in table if str(k).lstrip("-").isdigit()))
        for k in keys:
            hint = (table.get(str(k)) or "").strip()
            if hint:
                return hint
    if set_name in gen_hd.SUBJECTS:
        subject = gen_hd.SUBJECTS[set_name]
    else:
        import subjects_terrain
        subject, _ = subjects_terrain.subject_for_set(set_name)
    if not subject:
        return ""
    ground = subject.partition("|")[0].strip().rstrip(",")
    return ground.split(":")[0].strip()


def painter_for(args):
    """Тот же художник, что и у gen_hd --painter qwen21, но без кадра на входе."""
    ns = argparse.Namespace(models=args.models, qwen21_model=args.model, qwen21_steps=args.steps,
                            qwen21_cfg=args.cfg, qwen21_mp=args.mp, qwen21_strength=0.0,
                            qwen21_offload=args.offload, qwen21_thrifty=False,
                            qwen21_ref="", qwen21_ref_mp=1.0)
    return gen_hd.Qwen21Painter(ns, {"ground": ("", "")})


def draw_sheet(paths, out, per_row=3, width=640):
    """Лист с номерами: по нему и выбирается образец."""
    ims = [Image.open(p).convert("RGB") for p in paths]
    h = max(1, round(width * ims[0].height / ims[0].width))
    ims = [im.resize((width, h), Image.LANCZOS) for im in ims]
    rows = (len(ims) + per_row - 1) // per_row
    cols = min(per_row, len(ims))
    pad = 10
    sheet = Image.new("RGB", (cols * width + (cols + 1) * pad, rows * h + (rows + 1) * pad), (25, 25, 25))
    d = ImageDraw.Draw(sheet)
    for n, im in enumerate(ims):
        x = pad + (n % per_row) * (width + pad)
        y = pad + (n // per_row) * (h + pad)
        sheet.paste(im, (x, y))
        d.rectangle((x, y, x + 54, y + 30), fill=(0, 0, 0))
        d.text((x + 8, y + 8), "# %d" % (n + 1), fill=(255, 220, 0))
    sheet.save(out)
    return sheet.size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=gen_hd.DEFAULT_MODELS_DIR)
    ap.add_argument("--sheets", default="art/TERRAIN")
    ap.add_argument("--set", dest="set_name", default="", help="например DESERT.PCK")
    ap.add_argument("--what", default="", help="что за грунт словами (по умолчанию - подсказка первого пола набора, например «yellow desert sand»)")
    ap.add_argument("--count", type=int, default=6, help="сколько образцов нарисовать")
    ap.add_argument("--pick", type=int, default=0, help="взять образец N как эталон набора (ref.png) и выйти")
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--steps", type=int, default=40)
    ap.add_argument("--cfg", type=float, default=4.0)
    ap.add_argument("--mp", type=float, default=2.0, help="мегапикселей на образец (2.0 - родные 2K)")
    ap.add_argument("--aspect", default="4:3", help="стороны образца, например 4:3 или 1:1")
    ap.add_argument("--model", default="")
    ap.add_argument("--offload", default="model", choices=["model", "seq", "none"])
    ap.add_argument("--out", default="", help="куда класть образцы (по умолчанию <sheets>\\<набор>\\refs)")
    args = ap.parse_args()

    if not args.set_name:
        raise SystemExit("нужен --set, например --set DESERT.PCK")
    set_dir = os.path.join(args.sheets, args.set_name)
    if not os.path.isdir(set_dir):
        raise SystemExit("нет папки набора: %s" % set_dir)
    ref_dir = args.out or os.path.join(set_dir, "refs")

    # --pick: только выбрать из уже нарисованного, модель не поднимаем
    if args.pick:
        src = os.path.join(ref_dir, "ref_%d.png" % args.pick)
        if not os.path.exists(src):
            raise SystemExit("нет образца %s - сначала нарисуй их без --pick" % src)
        dst = os.path.join(set_dir, "ref.png")
        shutil.copyfile(src, dst)
        print("эталон набора: %s (из образца %d)" % (dst, args.pick))
        print("теперь gen_hd.py --painter qwen21 подхватит его сам")
        return

    what = args.what or subject_of(set_dir, args.set_name)
    if not what:
        raise SystemExit("тема грунта набора не известна - напиши её сам: --what \"yellow desert sand\"")
    prompt = REF_STYLE.replace("{what}", what)
    print("материал:", what)
    print("prompt:", prompt)
    print("negative:", REF_NEGATIVE)

    aw, _, ah = args.aspect.partition(":")
    aw, ah = float(aw or 4), float(ah or 3)
    W, H = gen_hd.qwen21_size(int(aw * 100), int(ah * 100), args.mp)
    print("размер образца: %dx%d" % (W, H))

    os.makedirs(ref_dir, exist_ok=True)
    painter = painter_for(args)
    torch = painter.torch
    paths, t0 = [], time.time()
    for n in range(args.count):
        seed = args.seed + n * 1009
        kw = {"prompt": prompt, "num_inference_steps": args.steps,
              "generator": torch.Generator("cuda").manual_seed(seed)}
        if "negative_prompt" in painter.accepts:
            kw["negative_prompt"] = REF_NEGATIVE
        if "true_cfg_scale" in painter.accepts:
            kw["true_cfg_scale"] = args.cfg
        elif "guidance_scale" in painter.accepts:
            kw["guidance_scale"] = args.cfg
        if "width" in painter.accepts:
            kw["width"], kw["height"] = W, H
        out = painter.pipe(**kw).images[0]
        if out.mode == "RGBA":
            flat = Image.new("RGB", out.size, (128, 128, 128))
            flat.paste(out, (0, 0), out)
            out = flat
        path = os.path.join(ref_dir, "ref_%d.png" % (n + 1))
        out.convert("RGB").save(path)
        paths.append(path)
        el = time.time() - t0
        print("  [%d/%d] %s | %s, осталось ~%s" % (
            n + 1, args.count, os.path.basename(path), gen_hd.human_time(el),
            gen_hd.human_time(el / (n + 1) * (args.count - n - 1))), flush=True)

    sheet = os.path.join(ref_dir, "sheet.png")
    size = draw_sheet(paths, sheet)
    print("")
    print("лист образцов: %s (%dx%d)" % (sheet, size[0], size[1]))
    print("выбери номер и закрепи его за набором:")
    print("  %s tools\\hdart\\make_ref.py --sheets %s --set %s --pick <номер>"
          % (sys.executable, args.sheets, args.set_name))


if __name__ == "__main__":
    main()
