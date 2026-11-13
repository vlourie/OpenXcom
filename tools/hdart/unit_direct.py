#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Прямой пробный рендер одной позы GOV_4 (специалист 03.10, после отказа от unit_refit и unit_ref): без растяжек,
склеек и самодельной анатомии. Позу, ракурс, габариты и положение частей задаёт оригинальный спрайт (кадр,
собранный как движок - unit_pilot.compose, с AK в руках), облик и одежду - кукла инвентаря Govt_Pilot.png.

Модель - Qwen-Image-Edit-2511 + Lightning 8 шагов (item_photo.EditPainter): она ПРАВИТ первую картинку, поэтому
держит её геометрию лучше свободного рендера. Входов два (R-205): <image1> - оригинал bicubic x16 на подложке,
<image2> - кукла на той же подложке. Меток во входе нет (R-204). Один seed (unit_pilot.SEED).
Ответ - как есть, без вырезки и подгонки: это художественная проба, не игровой ассет. Не выдержала модель позу
или размеры - так и записать, цепочкой деформаций не чинить (R-208).

Без модели (входы, промпт, лист без ответа):
    py -3.13 tools/hdart/unit_direct.py --dry-run
С моделью - только через очередь:
    py -3 tools/gpuq.py add --name gov4_direct_p1 --prio 1 --cwd E:/OpenXCom -- \
        E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/unit_direct.py
Выход art/units/pilot-gov4/direct/d<d>_p<n>/: in1.png, in2.png, prompt.txt, raw.s<seed>.png (ответ модели),
sheet.s<seed>.png (оригинал x16 nearest | ответ в том же масштабе), meta.s<seed>.json."""
import os

os.environ["HF_HUB_OFFLINE"] = "1"      # до импорта diffusers (R-145, R-207)

import argparse                         # noqa: E402
import json                             # noqa: E402
import sys                              # noqa: E402
import time                             # noqa: E402

from PIL import Image, ImageDraw        # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import item_photo as ip                 # noqa: E402
import unit_pilot as up                 # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
ENC = "utf-8-sig"
OUT = os.path.join("art", "units", "pilot-gov4", "direct")
ZOOM = 16
SIZE = (896, 1120)                      # как рендер unit_pilot: кроп 27x33 базы при 1 Мп, кратно 32
PANEL = (176, 176, 182)                 # grey_light, как у прежнего рендера этой позы
PROMPT = ("<image1> is a tiny low-resolution pixel sprite of one person from a tactical game, enlarged, seen from "
          "above at the fixed isometric camera of the game, on a flat panel of colour RGB({r}, {g}, {b}). Turn "
          "<image1> into a high-quality photograph of the same real person: {what}. Keep exactly the pose, the "
          "position, the size and the orientation of <image1>: the head, both arms and the hands holding the "
          "rifle, the rifle itself, the legs and the feet stay exactly where they are, with the same silhouette, "
          "the same proportions and the same camera from above; the light from the upper left. Natural human "
          "anatomy, real fabric, steel and wood. <image2> shows the same person's clothing from the front at a "
          "larger size: use it only for the cut of the flight suit, its pockets, zipper, seams and red patches; "
          "ignore its helmet and goggles, its pose and its camera. Keep the flat plain panel of colour "
          "RGB({r}, {g}, {b}): no floor, no shadow on the panel, no other objects, no frame, no text.")


# --ref: второй картинкой - эталон Vitali (готовый рисунок той же героини в другой позе) вместо куклы:
# облик, одежда, оружие и манера письма - с эталона, поза, размер и камера - с оригинала
REF_PROMPT = ("<image1> is a tiny low-resolution pixel sprite of one person from a tactical game, enlarged, seen "
              "from above at the fixed isometric camera of the game, on a flat panel of colour RGB({r}, {g}, {b}). "
              "<image2> is the finished artwork of this same person in another pose. Redraw <image1> as a "
              "finished artwork of the same quality: exactly the same person as <image2> - the face, the hair, the "
              "sunglasses, the black flight coverall with its pockets, zipper, seams and red patches, the boots, "
              "the rifle and the painting style of <image2>. Take the pose, the position, the size, the "
              "orientation and the camera only from <image1>: the head, both arms and the hands, the rifle, the "
              "legs and the feet stay exactly where <image1> has them, with the same silhouette. Natural human "
              "anatomy. Keep the flat plain panel of colour RGB({r}, {g}, {b}): no floor, no shadow on the panel, "
              "no other objects, no frame, no text.")


# --ref-box: от эталона - только голова и верх груди (без рук, оружия и стойки), чтобы его поза не переносилась
# (специалист 03.10 после d3_p2_ref); поза прицеливания - словами, красное - только существующие нашивки
HEAD_PROMPT = ("<image1> is a tiny low-resolution pixel sprite of one person from a tactical game, enlarged, seen "
               "from above at the fixed isometric camera of the game, on a flat panel of colour RGB({r}, {g}, {b}). "
               "<image2> is a close-up of the finished artwork of this same person: her head and upper chest. "
               "Redraw <image1> as a full-figure finished artwork of the same quality and the same painting style "
               "as <image2>: the same face, short blond hair and dark aviator sunglasses as <image2>, {what}. "
               "Take the pose, the position, the size, the orientation and the camera only from <image1>: she is "
               "aiming the rifle at the viewer - the rifle stock is pressed to her shoulder, both arms are extended "
               "forward towards the viewer, the barrel points straight at the viewer and is strongly foreshortened "
               "by perspective, the muzzle is the nearest point to the viewer; the rifle is not held across the "
               "waist. The head, the hands, the legs and the feet stay exactly where <image1> has them, with the "
               "same silhouette. Natural human anatomy. The only red on her are the existing small red patch on the "
               "left chest and the red patch on the left shoulder: no red stitching, no red piping, no other red "
               "details. Keep the flat plain panel of colour RGB({r}, {g}, {b}): no floor, no shadow on the panel, "
               "no other objects, no frame, no text.")


def ref_box_input(path, box, size):
    """Вырезка эталона box (x0,y0,x1,y1 в пикселях эталона) на подложке, вписана в size по центру."""
    ref = Image.open(path).convert("RGBA")
    bg = Image.new("RGBA", ref.size, PANEL + (255,))
    bg.alpha_composite(ref)
    part = bg.crop(box)
    k = min(size[0] * 0.9 / part.width, size[1] * 0.9 / part.height)
    part = part.resize((round(part.width * k), round(part.height * k)), Image.LANCZOS)
    flat = Image.new("RGBA", size, PANEL + (255,))
    flat.paste(part, ((size[0] - part.width) // 2, (size[1] - part.height) // 2))
    return flat.convert("RGB")


def ref_input(path, crop):
    """Эталон -> картинка размером кроп x ZOOM на подложке: фигура по высоте габарита фигуры кропа, по центру."""
    ref = Image.open(path).convert("RGBA")
    fig = ref.crop(ref.split()[3].point(lambda v: 255 if v > 128 else 0).getbbox())
    ob = crop.split()[3].getbbox()
    th = (ob[3] - ob[1]) * ZOOM
    tw = max(1, round(fig.width * th / fig.height))
    fig = fig.resize((tw, th), Image.LANCZOS)
    flat = Image.new("RGBA", (crop.width * ZOOM, crop.height * ZOOM), PANEL + (255,))
    lay = Image.new("RGBA", flat.size, (0, 0, 0, 0))
    lay.paste(fig, ((ob[0] + ob[2]) * ZOOM // 2 - tw // 2, ob[1] * ZOOM))
    flat.alpha_composite(lay)
    return flat.convert("RGB")


def build(pose_n, d, ref=None, ref_box=None):
    s = up.Sources()
    pose = up.POSES[pose_n]
    full, _o = up.compose(s.layers(pose, d), s.classic, 1)
    crop, _box = ip.crop_job(full)
    what = up.WHO + (up.GUN if pose[3] else "")
    in1 = Image.new("RGBA", (crop.width * ZOOM, crop.height * ZOOM), PANEL + (255,))
    in1.alpha_composite(crop.resize(in1.size, Image.BICUBIC))
    if ref and ref_box:
        in2 = ref_box_input(ref, ref_box, in1.size)
        prompt = HEAD_PROMPT.format(r=PANEL[0], g=PANEL[1], b=PANEL[2], what=up.WHO.split(", ", 1)[1] + up.GUN)
    elif ref:
        in2 = ref_input(ref, crop)
        prompt = REF_PROMPT.format(r=PANEL[0], g=PANEL[1], b=PANEL[2])
    else:
        in2 = up.doll_input(crop, PANEL, ZOOM)
        prompt = PROMPT.format(r=PANEL[0], g=PANEL[1], b=PANEL[2], what=what)
    return pose, crop, in1.convert("RGB"), in2, prompt


def sheet(crop, raw, path, title):
    """Оригинал x16 nearest на подложке | ответ модели в том же масштабе (кроп x16), без правок."""
    w, h = crop.width * ZOOM, crop.height * ZOOM
    orig = Image.new("RGBA", (w, h), PANEL + (255,))
    orig.alpha_composite(crop.resize((w, h), Image.NEAREST))
    panes = [("оригинал x16", orig.convert("RGB"))]
    if raw is not None:
        panes.append(("ответ модели, тот же масштаб", raw.resize((w, h), Image.LANCZOS)))
    gap, top = 12, 28
    out = Image.new("RGB", (len(panes) * w + (len(panes) + 1) * gap, h + top + gap), (24, 24, 24))
    dr = ImageDraw.Draw(out)
    f = up.font(15)
    dr.text((gap, 6), title, fill=(230, 230, 230), font=f)
    for i, (t, im) in enumerate(panes):
        x = gap + i * (w + gap)
        out.paste(im, (x, top))
        dr.text((x + 4, top + h - 20), t, fill=(20, 20, 20), font=f)
    out.save(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pose", type=int, default=1)
    ap.add_argument("--dir", type=int, default=up.RENDER_DIR)
    ap.add_argument("--seed", type=int, default=up.SEED)
    ap.add_argument("--models", default=None)
    ap.add_argument("--ref", default="", help="эталон второй картинкой вместо куклы (облик и манера письма)")
    ap.add_argument("--ref-box", default="", help="x0,y0,x1,y1: от эталона только эта вырезка (голова, верх груди)")
    ap.add_argument("--dry-run", action="store_true", help="входы, промпт и лист без ответа; модель не грузится")
    a = ap.parse_args()
    os.chdir(ROOT)
    box = tuple(int(v) for v in a.ref_box.split(",")) if a.ref_box else None
    pose, crop, in1, in2, prompt = build(a.pose, a.dir, a.ref, box)
    od = os.path.join(OUT, "d%d_p%d%s" % (a.dir, a.pose, ("_refhead" if box else "_ref") if a.ref else ""))
    os.makedirs(od, exist_ok=True)
    in1.save(os.path.join(od, "in1.png"))
    in2.save(os.path.join(od, "in2.png"))
    with open(os.path.join(od, "prompt.txt"), "w", encoding=ENC) as f:
        f.write(prompt + "\n")
    title = "GOV_4, направление %d, поза %d (%s), seed %d - Edit-2511, прямой рендер без правок%s" % (
        a.dir, a.pose, pose[0], a.seed, ", вход 2 - эталон" if a.ref else "")
    print("поза %d (%s), направление %d: кроп %dx%d базы, входы %s и %s, рендер %dx%d" % (
        a.pose, pose[0], a.dir, crop.width, crop.height, in1.size, in2.size, SIZE[0], SIZE[1]), flush=True)
    if a.dry_run:
        sheet(crop, None, os.path.join(od, "sheet.dry.png"), title)
        print("dry-run: модель не грузилась ->", od)
        return
    import gen_hd
    models = a.models or gen_hd.DEFAULT_MODELS_DIR
    ip.edit_model_check(models)
    painter = ip.EditPainter(models)
    import torch
    t0 = time.time()
    res = painter.pipe(prompt=prompt, image=[in1, in2], num_inference_steps=ip.EDIT_RUN["steps"],
                       generator=torch.Generator("cpu").manual_seed(a.seed), true_cfg_scale=ip.EDIT_RUN["cfg"],
                       width=SIZE[0], height=SIZE[1])
    raw = res.images[0].convert("RGB")
    dt = time.time() - t0
    raw.save(os.path.join(od, "raw.s%d.png" % a.seed))
    sheet(crop, raw, os.path.join(od, "sheet.s%d.png" % a.seed), title)
    meta = {"pose": a.pose, "pose_name": pose[0], "dir": a.dir, "seed": a.seed, "size": SIZE, "zoom": ZOOM,
            "panel": PANEL, "run": ip.EDIT_RUN, "model_rev": ip.EDIT_MODEL_REV, "prompt": prompt,
            "inputs": ["in1.png: оригинал bicubic x16 на подложке", "in2.png: " + (("эталон " + a.ref) if a.ref else "кукла Govt_Pilot.png") + " на подложке"],
            "seconds": round(dt, 1), "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
    with open(os.path.join(od, "meta.s%d.json" % a.seed), "w", encoding=ENC) as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    if torch.cuda.is_available():
        print("пик памяти карты %.1f ГБ" % (torch.cuda.max_memory_allocated() / 2 ** 30), flush=True)
    print("готово за %.0f с (с загрузкой модели) -> %s" % (dt, od), flush=True)


if __name__ == "__main__":
    main()
