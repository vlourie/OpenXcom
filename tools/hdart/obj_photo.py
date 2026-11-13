#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Предметы фотореалистично: перерисовка отбракованных кадров серии (Vitali 27.09: «цель фотореалистика»).

Серия obj_series рисует стилем strict - «hand-painted game artwork», в негативе photo; вышло рисованно.
Здесь тот же Qwen-Image-2.1 из шума, те же cfg 4, 40 шагов, 1 Мп, зум 16, вырез по силуэту оригинала
(grow 2) и тон 0.7 - другой только промпт: фотография настоящей вещи, рисунок в негатив.

Задания - art/objects/photo_jobs.json, список:
  {"name": ..., "map": "ТЕРРЕЙН/КАРТА", "at": [[x, y, z], ...], "what": ..., "take": ["НАБОР:кадр@i", ...]}
      составной по местам на карте: куски part 3, стоящие в экранных точках layout (x, y, z), рисуются
      одной картинкой и режутся по клеткам (obj_series.split); кадр берётся из i-го куска. Один кадр
      может стоять в предмете дважды (ствол трубы) - поэтому место, а не ключ.
  {"name": ..., "anim": "НАБОР:кадр,кадр,...", "what": ...}
      анимация (R-071): все кадры одним описанием и одним зерном; корпус - из первого кадра, из
      остальных - только то, что у оригинала меняется (вода в бочке), с запасом в пиксель.
Задание партии из замороженного снимка (acceptance_run.py compile, P1-B 30.09) несёт ещё:
  "seed" - своё зерно (а не --seed + номер в списке); "prompt" - готовый текст целиком (только
  --engine turbo --rgba); "reference": {"raw": "raw/<имя>.png"} - готовый ответ другого задания второй
  картинкой <image2> (второй бок multiview-группы); "batch_id" - такие задания идут только с --batch <id>,
  и перед загрузкой модели снимок сверяется (BATCH_STALE - стоп) и задания сверяются с ним по хэшу.
--engine turbo грузит модель и LoRA по замку art/models/qwen21_turbo_rgba.lock.json (R-145, model_lock.py):
коммиты из замка, без сети; файлы слепка и версии библиотек сверяются с замком до загрузки.

    tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\obj_photo.py --jobs art/objects/photo_jobs.json

Кладёт в art/objects/photo/: raw/<name>*.png (ответ модели), <НАБОР>.PCK/<кадр>.png, sheet.png
(оригинал x4 | прежний пак | серия strict | фото). В пак НЕ идёт.
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np                                  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter       # noqa: E402

import map_mockup as mm                             # noqa: E402
import map_paint as mp_                             # noqa: E402
import model_lock                                   # noqa: E402
import obj_series as osr                            # noqa: E402
import probe_object as po                           # noqa: E402

ENC = "utf-8-sig"
PHOTO = (
    "<image1> is the low-resolution original sprite of {what}, shown on a flat grey preview panel. "
    "The panel is background, not part of the object. "
    "Make a photorealistic picture of this same real object: {what}. It must look like a real "
    "photograph of a real thing, physically correct materials and light, seen from above at 30 "
    "degrees in isometric view exactly like the sprite. Keep the position, the size, the silhouette "
    "and the colours of <image1>. Real surface detail of each material, natural wear and dirt, "
    "soft daylight from the upper left, sharp focus. "
    "Output one isolated object on the same flat panel. No ground, no floor, no other objects, "
    "no frame, no text.")
# --engine edit (Vitali 28.09: «пользуйся быстрой моделью»): Qwen-Image-Edit-2511 + Lightning + LoRA
# Anime-to-Photoreal ПРАВИТ оригинал, а не рисует из шума: форма, цвет, число ступеней, полок и ящиков
# остаются от оригинала (партия 1 из шума: лестница с лишними ступенями, ёлки шарами, R-125).
EDIT = (
    "Turn <image1> into a real sharp photograph of the same object: {what}. Keep exactly the shape, "
    "the silhouette, the proportions, the position and the colours of <image1>, and every part of it: "
    "the same number of steps, shelves, drawers, doors, legs and panels, nothing added and nothing "
    "removed. Isometric view from above at 30 degrees, orthographic, no perspective. Real materials with "
    "natural surface detail and light wear, soft daylight from the upper left, sharp focus. "
    "Keep the flat plain background of <image1> exactly as it is, plain and even. No shadow on the "
    "background, no floor, no other objects, no frame, no text.")
# подложки правки: серые и две цветные - серый предмет на серой подложке контуром не отделить (R-089)
EDIT_PANELS = [(38, 38, 42), (96, 96, 102), (176, 176, 182), (60, 150, 80), (70, 90, 200)]
# --rgba (28.09): родная прозрачность 2.1 - VAE на 4 канала, включается официальной фразой карточки.
# Оригинал подаётся без подложки (прозрачный), альфа берётся из ответа, а не вырезается по фону (R-089)
RGBA_HEAD = "This is an RGBA image with transparency. "
RGBA_TAIL = " The image has alpha channel and the background is transparent."
PHOTO_RGBA = (
    "<image1> is the low-resolution original sprite of {what}, on a transparent background. "
    "Make a photorealistic picture of this same real object: {what}. It must look like a real "
    "photograph of a real thing, physically correct materials and light, seen from above at 30 "
    "degrees in isometric view exactly like the sprite. Keep the position, the size, the silhouette, "
    "the colours and every part of <image1>: the same number of steps, shelves, drawers and doors. "
    "Real surface detail of each material, natural wear, soft daylight from the upper left, sharp "
    "focus. One isolated object, no ground, no floor, no shadow, no other objects, no text.")
# --engine control: оригинал модель не видит, только карту контура - всё про цвет и материал в словах
CONTROL = (
    "A real photograph of {what}, one isolated object, seen from above at 30 degrees in isometric "
    "view, orthographic, no perspective. Physically correct materials and light, real surface "
    "detail of each material, natural wear, soft daylight from the upper left, sharp focus. "
    "No ground, no floor, no other objects, no text.")
TURBO_SIGMAS = [1.0, 0.9375, 0.875, 0.75, 0.5, 0.25]     # карточка Viggle v0.2.1: 6 шагов, без CFG
TURBO_REPO = "Viggle/Qwen-Image-2.1-viggle-turbo"
TURBO_FILE = "Qwen-Image-2.1-viggle-turbo-v0.2.1-6step-lora-r128.safetensors"


def own_alpha(im, share=0.05):
    """Альфа ответа, если модель правда отдала прозрачность (доля почти прозрачного больше share)."""
    if im.mode != "RGBA":
        return None
    al = np.asarray(im.split()[3], np.float32) / 255.0
    return al if (al < 0.5).mean() > share else None


def pick_panel(frame, panels):
    a = np.asarray(frame.convert("RGBA"), np.float64)
    px = a[..., :3][a[..., 3] > 128]
    if len(px) == 0:
        return panels[0]
    return max(panels, key=lambda bg: float(np.percentile(np.abs(px - np.array(bg)).max(-1), 10)))


NEGATIVE = ("pixel art, pixelated, blocky, jagged stair-stepped edges, dithering, blurry, smudged, "
            "blob, noise, low detail, painting, illustration, drawing, cartoon, stylized, game art, "
            "hand-painted, cel shading, flat colours, plastic, toy, "
            "ground, grass tile, floor, panel frame, border, drop shadow, text, watermark")


def local_std(x, r):
    """Разброс яркости в окне (2r+1)^2 - через суммы по префиксам."""
    p = np.pad(x, r, mode="edge").astype(np.float64)
    n = 2 * r + 1

    def box(v):
        c = np.cumsum(np.cumsum(np.pad(v, ((1, 0), (1, 0))), 0), 1)
        return (c[n:, n:] - c[:-n, n:] - c[n:, :-n] + c[:-n, :-n]) / (n * n)
    m = box(p)
    return np.sqrt(np.maximum(box(p * p) - m * m, 0))


def drop_shadow(hd, chroma_max=18.0, std_max=5.0):
    """Тень предмета на подложке -> цвет подложки. Фотореалистичный ответ кладёт под предмет тень; она
    далеко от цвета подложки, cut_out считает её телом, габарит ответа растёт, и при вписывании в силуэт
    тень садится в нижние пиксели светлой каймой (27.09, камин и ствол трубы). Тень: почти бесцветная
    (тень холодная, цветность до 18), не светлее подложки, гладкая и связана с подложкой. Серый камень
    той же цветности отделяет только гладкость: разброс в окне 7x7 у гранита 10+, у тени меньше 5."""
    a = np.asarray(hd.convert("RGB"), np.float32)
    edge = np.concatenate([a[:8].reshape(-1, 3), a[-8:].reshape(-1, 3), a[:, :8].reshape(-1, 3), a[:, -8:].reshape(-1, 3)])
    bg = np.median(edge, 0)
    lum = a.mean(-1)
    chroma = a.max(-1) - a.min(-1)
    near_bg = np.abs(a - bg).max(-1) < 16
    grey = (chroma < chroma_max) & (lum <= bg.mean() + 12)
    cand = grey & (lum > 0.25 * bg.mean()) & (local_std(lum, 3) < std_max)
    ok = cand | near_bg
    cur = np.zeros_like(ok)
    cur[0], cur[-1], cur[:, 0], cur[:, -1] = ok[0], ok[-1], ok[:, 0], ok[:, -1]
    while True:
        nxt = cur.copy()
        nxt[1:] |= cur[:-1]; nxt[:-1] |= cur[1:]; nxt[:, 1:] |= cur[:, :-1]; nxt[:, :-1] |= cur[:, 1:]
        nxt &= ok
        if (nxt == cur).all():
            break
        cur = nxt
    out = a.copy()
    out[cur & cand] = bg
    return Image.fromarray(out.clip(0, 255).astype(np.uint8), "RGB")


def grad(hd, blur=1.2):
    """Перепад цвета (Собель по размытому, худший из каналов) - на единицу яркости за пиксель."""
    b = np.asarray(hd.convert("RGB").filter(ImageFilter.GaussianBlur(blur)), np.float32)
    p = np.pad(b, ((1, 1), (1, 1), (0, 0)), mode="edge")
    gx = (p[1:-1, 2:] - p[1:-1, :-2]) * 2 + (p[:-2, 2:] - p[:-2, :-2]) + (p[2:, 2:] - p[2:, :-2])
    gy = (p[2:, 1:-1] - p[:-2, 1:-1]) * 2 + (p[2:, :-2] - p[:-2, :-2]) + (p[2:, 2:] - p[:-2, 2:])
    return (np.hypot(gx, gy) / 8.0).max(-1)


def from_border(ok):
    """Связное с краем кадра подмножество ok (4-соседство)."""
    cur = np.zeros_like(ok)
    cur[0], cur[-1], cur[:, 0], cur[:, -1] = ok[0], ok[-1], ok[:, 0], ok[:, -1]
    while True:
        nxt = cur.copy()
        for _ in range(8):
            nxt[1:] |= nxt[:-1]; nxt[:-1] |= nxt[1:]; nxt[:, 1:] |= nxt[:, :-1]; nxt[:, :-1] |= nxt[:, 1:]
            nxt &= ok
        if (nxt == cur).all():
            return cur
        cur = nxt


def small_parts(mask, max_px):
    """Связные куски mask (4-соседство) не больше max_px пикселей."""
    h, w = mask.shape
    seen = np.zeros_like(mask)
    out = np.zeros_like(mask)
    for y0, x0 in zip(*np.nonzero(mask)):
        if seen[y0, x0]:
            continue
        comp, stack = [], [(y0, x0)]
        seen[y0, x0] = True
        while stack:
            y, x = stack.pop()
            comp.append((y, x))
            for yy, xx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= yy < h and 0 <= xx < w and mask[yy, xx] and not seen[yy, xx]:
                    seen[yy, xx] = True
                    stack.append((yy, xx))
        if len(comp) <= max_px:
            ys, xs = zip(*comp)
            out[list(ys), list(xs)] = True
    return out


def edge_matte(hd, g_thr=5.0, d_max=70.0, gap=6, pocket=10.0, pocket_share=0.015):
    """Альфа ответа модели: подложка - то, что гладко, близко к её цвету и связано с краем кадра;
    заливка останавливается на КОНТУРЕ предмета, а не на цвете (28.09: серый стол, холодильник, пульт
    на серой подложке - ключ по цвету съедал тело, semi до 0.47, R-089). Мягкая тень гладкая и
    подложке близка - уходит вместе с ней (drop_shadow не нужен). Щели контура до 2*gap пикселей
    закрываются: заливка по сжатой маске, край назад только по гладкому. Закрытые карманы подложки
    (между планками спинки) - только мелкие и почти ровно её цвета: крупный такой кусок - это тело
    цвета подложки (столешница), его ключом не отделить, кадр перерисовывать на другой подложке."""
    a = np.asarray(hd.convert("RGB"), np.float32)
    edge = np.concatenate([a[:8].reshape(-1, 3), a[-8:].reshape(-1, 3), a[:, :8].reshape(-1, 3), a[:, -8:].reshape(-1, 3)])
    bg = np.median(edge, 0)
    g = grad(hd)
    dist = np.abs(a - bg).max(-1)
    ok = (g < g_thr) & (dist < d_max)
    k = 2 * gap + 1
    ok_e = np.asarray(Image.fromarray(ok.astype(np.uint8) * 255, "L").filter(ImageFilter.MinFilter(k))) > 0
    grown = Image.fromarray(from_border(ok_e).astype(np.uint8) * 255, "L").filter(ImageFilter.MaxFilter(k))
    bgm = (np.asarray(grown) > 0) & ok
    pk = (g < g_thr * 0.6) & (dist < pocket) & ~bgm
    pk = np.asarray(Image.fromarray(pk.astype(np.uint8) * 255, "L").filter(ImageFilter.MinFilter(5))
                    .filter(ImageFilter.MaxFilter(5))) > 0
    bgm |= small_parts(pk, int(pocket_share * pk.size))
    body = Image.fromarray((~bgm).astype(np.uint8) * 255, "L")
    body = body.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))      # крошки прочь
    body = body.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))      # щели контура
    return np.asarray(body.filter(ImageFilter.GaussianBlur(0.8)), np.float32) / 255.0


def parse_key(text):
    s, f = text.rsplit(":", 1)
    return s.upper(), int(f)


def pieces_at(world, tb, at):
    """Составной по местам: {"members": [((набор, кадр, i), (x, y, z))], "spr", "pl"} для osr.compose."""
    t, b = tb.split("/")
    _im, _o, inst = mp_.layout(world, t, b)
    members, spr, pl = [], {}, {}
    for i, (x, y, z) in enumerate(at):
        hit = [d for d in inst if d["part"] == 3 and d["x"] == x and d["y"] == y and d["z"] == z]
        if len(hit) != 1:
            raise SystemExit("%s: в точке %s предметов %d, нужен один" % (tb, (x, y, z), len(hit)))
        d = hit[0]
        key = (d["set"].upper(), d["frame"], i)
        members.append((key, (x, y, z)))
        spr[key] = d["spr"].convert("RGBA")
        pl[key] = 0                                 # y из layout - уже место рисования
    return {"members": members, "spr": spr, "pl": pl}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jobs", default="art/objects/photo_jobs.json")
    ap.add_argument("--out", default="art/objects/photo")
    ap.add_argument("--old", default=po.MOD_TERRAIN)
    ap.add_argument("--series", default="art/objects/series")
    ap.add_argument("--only", default="", help="имена заданий через запятую")
    ap.add_argument("--seed", type=int, default=2713)
    ap.add_argument("--steps", type=int, default=40)
    ap.add_argument("--cfg", type=float, default=4.0)
    ap.add_argument("--mp", type=float, default=1.0)
    ap.add_argument("--zoom", type=int, default=16)
    ap.add_argument("--grow", type=int, default=2)
    ap.add_argument("--soft", type=int, default=40)
    ap.add_argument("--pad", type=int, default=3)
    ap.add_argument("--engine", default="qwen21", choices=["qwen21", "edit", "turbo", "control"],
                    help="qwen21 - из шума по описанию; edit - правка оригинала Edit-2511 + Lightning (28.09); "
                         "turbo - 2.1 + LoRA Viggle, 6 шагов без CFG; control - 2.1 + ControlNet Union по контуру")
    ap.add_argument("--rgba", action="store_true",
                    help="родная прозрачность 2.1: официальная фраза, оригинал без подложки, альфа из ответа")
    ap.add_argument("--control", default="canny", choices=["canny", "gray"], help="карта контроля --engine control")
    ap.add_argument("--control-scale", type=float, default=1.0, dest="control_scale")
    ap.add_argument("--edit-steps", type=int, default=8, dest="edit_steps")
    ap.add_argument("--recut", action="store_true",
                    help="без видеокарты: только перевырезка готовых raw/*.png, нет ответа - стоп (GPUQ_BYPASS=1 - только с ним)")
    ap.add_argument("--lora", type=float, default=1.0, help="вес Anime-to-Photoreal при --engine edit")
    ap.add_argument("--matte", default="edge", choices=["edge", "key"],
                    help="альфа ответа: edge - заливка подложки по контуру (28.09), key - по цвету подложки")
    ap.add_argument("--tone", type=float, default=0.7)
    ap.add_argument("--models", default=None)
    ap.add_argument("--model", default="")
    ap.add_argument("--offload", default="model", choices=["model", "seq", "none"])
    ap.add_argument("--dry-run", action="store_true", dest="dry_run")
    ap.add_argument("--batch", default="", help="партия из замороженного снимка: acceptance_batch_id")
    ap.add_argument("--lock", default=model_lock.LOCK,
                    help="замок модели --engine turbo (R-145): коммиты, sha256 файлов, версии библиотек")
    args = ap.parse_args()

    with open(args.jobs, encoding=ENC) as f:
        jobs = [j for j in json.load(f) if not j.get("_skip")]
    batched = {j.get("batch_id") for j in jobs if j.get("batch_id")}
    arun = None
    if batched or args.batch:
        # заморозили одно - видеокарта получает то же самое (R-087): снимок свежий, задания - его, до байта
        import acceptance_run as arun
        if batched != {args.batch}:
            raise SystemExit("задания партии %s, а --batch %r - не запускаю" % (sorted(batched), args.batch))
        arun.verify_for_gpu(args.batch, jobs)
        if args.engine != "turbo" or not args.rgba:
            raise SystemExit("партия снимка рисуется только --engine turbo --rgba (готовый промпт под него)")
        if any("at" not in j for j in jobs):
            raise SystemExit("задание партии без мест на карте (at) - не запускаю")
    if args.only:
        names = set(args.only.split(","))
        jobs = [j for j in jobs if j["name"] in names]
    for n, j in enumerate(jobs):
        ref = j.get("reference")
        if ref and not any(o["name"] == ref["job_name"] for o in jobs[:n]) \
                and not os.path.exists(os.path.join(args.out, ref["raw"])):
            raise SystemExit("%s: опорной картинки %s нет и её задание не стоит раньше" % (j["name"], ref["raw"]))
    world = mm.World()
    raw_dir = os.path.join(args.out, "raw")
    os.makedirs(raw_dir, exist_ok=True)

    # план и проверка мест - до загрузки модели
    plan = []
    for j in jobs:
        if "at" in j:
            comp = pieces_at(world, j["map"], j["at"])
            print("%s: составной из %d: %s" % (j["name"], len(comp["members"]),
                                              ", ".join("%s:%d" % k[:2] for k, _o in comp["members"])), flush=True)
            plan.append((j, comp))
        else:
            s, frames = j["anim"].split(":")
            fr = [int(v) for v in frames.split(",")]
            print("%s: анимация %s %s" % (j["name"], s, fr), flush=True)
            plan.append((j, (s.upper(), fr)))
    # R-145: turbo рисует ровно тем, что в замке - коммит модели и LoRA, без сети; расхождение файлов
    # или библиотек с замком - стоп до загрузки модели (--recut модель не грузит, ему замок не нужен)
    # полный qwen21 --rgba (проба детали 30.09) - та же модель по тому же замку, без LoRA
    pinned = None
    if (args.engine == "turbo" or (args.engine == "qwen21" and args.rgba)) and not args.recut and not args.model:
        lock = model_lock.load(args.lock)
        if lock is None:
            raise SystemExit("нет замка модели %s - снять: model_lock.py make" % args.lock)
        pinned = model_lock.pin(lock)
        if args.engine == "turbo" and (pinned["lora_repo"], pinned["lora_file"]) != (TURBO_REPO, TURBO_FILE):
            raise SystemExit("LoRA в замке %s/%s, а в obj_photo %s/%s" % (
                pinned["lora_repo"], pinned["lora_file"], TURBO_REPO, TURBO_FILE))
        bad = model_lock.check_runtime(lock)
        for b in bad:
            print("   замок:", b, flush=True)
        if bad:
            raise SystemExit("расхождений с замком %d - не рисую" % len(bad))
        print("замок модели: %s@%s, LoRA @%s - совпадает" % (
            pinned["model_repo"], pinned["model_revision"][:8], pinned["lora_revision"][:8]), flush=True)
    if args.dry_run:
        return

    ns = argparse.Namespace(models=args.models or po.gen_hd.DEFAULT_MODELS_DIR, qwen21_model=args.model,
                            qwen21_steps=args.steps, qwen21_cfg=args.cfg, qwen21_mp=args.mp,
                            qwen21_strength=0.0, qwen21_offload=args.offload, qwen21_thrifty=False,
                            qwen21_ref="", qwen21_ref_mp=1.0, qwen21_prompt="strict",
                            qwen21_hint="off", qwen21_ref_order="ref-first",
                            qwen21_revision=pinned["model_revision"] if pinned else None,
                            qwen21_local_only=bool(pinned and pinned["local_files_only"]))
    lora_pin = {"revision": pinned["lora_revision"], "local_files_only": pinned["local_files_only"]} if pinned else {}
    painter = None                                  # модель грузится, только если нужен новый ответ
    po.gen_fire.NEGATIVE = NEGATIVE

    def paint(full, what, seed, raw_path, text_override=None, extra=()):
        """Как obj_series.paint, промпт PHOTO. full k=1 -> x4 RGBA того же размера.
        text_override - готовый промпт задания снимка; extra - пути опорных картинок (<image2>...)."""
        nonlocal painter
        bb = full.split()[3].getbbox()
        box = (max(0, bb[0] - args.pad), max(0, bb[1] - args.pad),
               min(full.width, bb[2] + args.pad), min(full.height, bb[3] + args.pad))
        frame = full.crop(box)
        panel = pick_panel(frame, EDIT_PANELS) if args.engine == "edit" else po.pick_background(frame)
        src = frame.resize((frame.width * args.zoom, frame.height * args.zoom), Image.BICUBIC)
        flat = Image.new("RGBA", src.size, tuple(panel) + (255,))
        flat.alpha_composite(src)
        if os.path.exists(raw_path):                # готовый ответ не заказывать заново
            hd = Image.open(raw_path)
            hd = hd.convert("RGBA" if hd.mode in ("RGBA", "LA", "P") else "RGB")
        elif args.recut:                            # без видеокарты - ни одного нового ответа
            raise SystemExit("нет %s, а --recut" % raw_path)
        elif args.engine == "edit":
            if painter is None:
                import photo_ui as pu
                painter = pu.Painter(args.models or po.gen_hd.DEFAULT_MODELS_DIR, fast=True,
                                     steps=args.edit_steps, photoreal=args.lora > 0)
            W, H = po.gen_hd.qwen21_size(flat.width, flat.height, args.mp)
            out = painter.edit([flat.convert("RGB").resize((W, H), Image.LANCZOS)], EDIT.replace("{what}", what),
                               NEGATIVE, seed, args.edit_steps, 1.0, W, H, photoreal=args.lora)
            hd = Image.fromarray(out)
            po.gen_hd.save_png(hd, raw_path)
        elif args.engine == "control":
            if painter is None:
                import vx_control as vc
                painter = vc.ControlPainter(args.offload if args.offload == "none" else "model")
                painter.map = vc.control_map
            W, H = po.gen_hd.qwen21_size(src.width, src.height, args.mp, 16)
            ctl = painter.map(frame, args.zoom, args.control)
            po.gen_hd.save_png(ctl, raw_path[:-4] + ".ctl.png")
            text = CONTROL.replace("{what}", what)
            if args.rgba:
                text = RGBA_HEAD + text + RGBA_TAIL
            hd = painter.run(text, ctl, W, H, args.steps, args.cfg, seed, args.control_scale, NEGATIVE)
            po.gen_hd.save_png(hd, raw_path)
        elif args.rgba or args.engine == "turbo":
            if painter is None:
                painter = po.gen_hd.Qwen21Painter(ns, {"ground": ("", "")})
                if args.engine == "turbo":
                    from diffusers import FlowMatchEulerDiscreteScheduler
                    painter.pipe.load_lora_weights(TURBO_REPO, weight_name=TURBO_FILE, **lora_pin)
                    painter.pipe.scheduler = FlowMatchEulerDiscreteScheduler.from_pretrained(
                        TURBO_REPO, subfolder="scheduler", **lora_pin)
                    print("   LoRA Viggle turbo: %s, шагов %d" % (TURBO_FILE, len(TURBO_SIGMAS)), flush=True)
            W, H = po.gen_hd.qwen21_size(src.width, src.height, args.mp)
            if args.rgba:                           # оригинал без подложки: прозрачное - это фон
                # бикубика x16 оставляет ступени пикселей, и с RGBA модель их копирует (R-004, 28.09)
                import vx_control as vc
                ref = vc.smooth_ref(frame, args.zoom)
                text = text_override or (RGBA_HEAD + PHOTO_RGBA.replace("{what}", what) + RGBA_TAIL)
            else:
                ref, text = flat.convert("RGB"), PHOTO.replace("{what}", what)
            images = [ref.resize((W, H), Image.LANCZOS)]
            for p in extra:                         # готовый первый бок - второй картинкой (<image2>)
                im2 = Image.open(p).convert(ref.mode)
                rw, rh = po.gen_hd.qwen21_size(im2.width, im2.height, 1.0)
                images.append(im2.resize((rw, rh), Image.LANCZOS))
                print("   опора: %s" % p, flush=True)
            kw = {"prompt": text, "image": images, "width": W, "height": H,
                  "output_resolution": 32 * round((W * H) ** 0.5 / 32),
                  "generator": painter.torch.Generator("cuda").manual_seed(seed)}
            if args.engine == "turbo":              # без CFG негатив не действует (R-040) - не подаём
                kw.update(num_inference_steps=len(TURBO_SIGMAS), sigmas=TURBO_SIGMAS, true_cfg_scale=1.0)
            else:
                kw.update(num_inference_steps=args.steps, true_cfg_scale=args.cfg, negative_prompt=NEGATIVE)
            hd = painter.pipe(**kw).images[0]
            po.gen_hd.save_png(hd, raw_path)
        else:
            if painter is None:
                painter = po.gen_hd.Qwen21Painter(ns, {"ground": ("", "")})
            hd = po.gen_fire.run_pass(painter, args, PHOTO.replace("{what}", what), flat.convert("RGB"), seed)
            po.gen_hd.save_png(hd, raw_path)
        al = own_alpha(hd)
        print("   %s: альфа %s" % (os.path.basename(raw_path), "из ответа" if al is not None else args.matte),
              flush=True)
        if al is not None:                          # модель сама отдала прозрачность
            cut0 = po.cut_out(hd, frame, args.grow, args.soft, matte=al)
        elif args.matte == "edge":
            hd = hd.convert("RGB")
            cut0 = po.cut_out(hd, frame, args.grow, args.soft, matte=edge_matte(hd))
        else:                                       # прежний ключ по цвету подложки (сверка)
            cut0 = po.cut_out(drop_shadow(hd), frame, args.grow, args.soft)
        part = po.match_tone(cut0, frame, args.tone)
        cut = Image.new("RGBA", (full.width * 4, full.height * 4), (0, 0, 0, 0))
        cut.paste(part, (box[0] * 4, box[1] * 4))
        return cut

    def save(im, s, fr):
        d = os.path.join(args.out, s + ".PCK")
        os.makedirs(d, exist_ok=True)
        po.gen_hd.save_png(im, os.path.join(d, "%d.png" % fr))

    t0, made = time.time(), []
    for n, (j, what) in enumerate(plan, 1):
        seed = j.get("seed", args.seed + n)
        extra = [os.path.join(args.out, j["reference"]["raw"])] if j.get("reference") else []
        if isinstance(what, dict):
            comp = what
            whole, at = osr.compose(comp)
            raw = os.path.join(raw_dir, j["name"] + ".png")
            ref = None
            if arun:
                # партия: готовый raw - только свой записанный; опора B - ответ A этой партии по sha256
                arun.check_raw(args.out, j, raw)
                if j.get("reference"):
                    ref = arun.check_reference(args.out, j)
            cut = paint(whole, j["what"], seed, raw, j.get("prompt"), extra)
            pieces = osr.split(cut, comp, at, args.grow)
            keys = [k for k, _o in comp["members"]]
            saved = []
            for t in j["take"]:
                kk, i = t.split("@")
                s, fr = parse_key(kk)
                key = keys[int(i)]
                if key[:2] != (s, fr):
                    raise SystemExit("%s: кусок %s - это %s:%d, не %s" % (j["name"], i, key[0], key[1], kk))
                save(pieces[key], s, fr)
                made.append((s, fr))
                saved.append(os.path.join(args.out, s + ".PCK", "%d.png" % fr))
            if arun:
                arun.record_output(args.out, j, raw, saved, ref)
        else:
            s, frs = what
            sprs = [world.sprite(s, f, None).convert("RGBA") for f in frs]
            cuts = [paint(sp, j["what"], seed, os.path.join(raw_dir, "%s_%d.png" % (j["name"], f)),
                          j.get("prompt"), extra) for sp, f in zip(sprs, frs)]
            a0 = np.asarray(sprs[0], np.int16)
            for sp, c, f in zip(sprs, cuts, frs):
                diff = (np.abs(np.asarray(sp, np.int16) - a0).sum(-1) > 0).astype(np.uint8) * 255
                m = Image.fromarray(diff, "L").filter(ImageFilter.MaxFilter(3))
                m = m.resize((sp.width * 4, sp.height * 4), Image.NEAREST).filter(ImageFilter.GaussianBlur(2))
                mt = np.asarray(m, np.float32)[..., None] / 255.0
                im = np.asarray(cuts[0], np.float32) * (1 - mt) + np.asarray(c, np.float32) * mt
                save(Image.fromarray(im.clip(0, 255).astype(np.uint8), "RGBA"), s, f)
                made.append((s, f))
        print("[%d/%d] %s готово, %s" % (n, len(plan), j["name"], po.gen_hd.human_time(time.time() - t0)), flush=True)

    # лист: оригинал x4 | прежний пак | серия strict | фото, на тёмном полу боя
    cw, ch = 128, 160
    sheet = Image.new("RGB", (4 * (cw + 4), len(made) * (ch + 18)), (32, 32, 36))
    d = ImageDraw.Draw(sheet)
    for r, (s, fr) in enumerate(made):
        cells = [world.sprite(s, fr, None).convert("RGBA").resize((cw, ch), Image.NEAREST)]
        for root in (args.old, args.series, args.out):
            p = os.path.join(root, s + ".PCK", "%d.png" % fr)
            cells.append(Image.open(p).convert("RGBA") if os.path.exists(p) else None)
        for c, im in enumerate(cells):
            if im is not None:
                sheet.paste(osr.on_floor(im, (cw, ch)), (c * (cw + 4), r * (ch + 18) + 16))
        d.text((2, r * (ch + 18) + 2), "%s %d  orig | old pack | strict | photo" % (s, fr), fill=(255, 255, 0))
    po.gen_hd.save_png(sheet, os.path.join(args.out, "sheet.png"))
    print("ЛИСТ %s" % os.path.join(args.out, "sheet.png"), flush=True)


if __name__ == "__main__":
    main()
