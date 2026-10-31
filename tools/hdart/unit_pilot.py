#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Художественный пилот юнитов (docs/HD_UNITS.md §7, решение рецензента 03.10): GOV_4 в существующих позах.

Фигура собирается из частей ТАК ЖЕ, как движок (UnitSprite::drawRoutine0, src/Battlescape/UnitSprite.cpp:293-650):
номера кадров частей, покачивание торса при ходьбе, смещения предмета, порядок наложения по направлению.
Направления - Pathfinding::dir_x/dir_y (R-084): 0 вверх-вправо, 2 вниз-вправо, 3 вниз (к зрителю), 4 вниз-влево.
Предмет в руке - HANDOB кадр handSprite + dir (AK: 352, Resources/HANDOB/AK.png); тело - лист брони, номер кадра
в паке = номер в листе (сдвига 1000 у тел нет, units-engine.md §1.6). Пол врага - мужской торс 32 + dir
(BattleUnit.cpp:492). Скрипты SelectUnitSprite мода не исполняются - для GOV_4 их нет (проверять при переносе).

Источники читаются как их читает движок (R-043): индексы, 0 прозрачный, боевая палитра delicious_regular.pal.
Нынешний HD - pack.hdp мода hd в установке (как HdSprites::loadPack), у HANDOB HD-пака нет - предмет nearest.

    py -3.13 tools/hdart/unit_pilot.py poses [--dir 3]      # лист: оригинал x4 | нынешний пак | x1, по позам
Выход: art/units/pilot-gov4/.

Рендер фигуры целиком (метод (а) U7: целая фигура, потом части по маскам оригинала) - путь предметов как есть:
struct_probe.Render (Qwen-Image-2.1 по замку, RENDER_V1: 40 шагов, cfg 4, 1 Мп), вход C - эскиз struct_guide
первой картинкой, оригинал bicubic второй (R-160); D - то же плюс кукла инвентаря третьей картинкой (только
одежда, U4). Вырезка - item_photo.cut_fixed: ответ на холст одним известным преобразованием, без подгонки по
содержимому (R-156), альфа из силуэта оригинала (R-089), тон к оригиналу выключен. Один seed на всю фигуру (R-071).
Модель - только через очередь, под render_chunks.py:
    py -3.13 tools/gpuq.py add --name unit_pilot_gov4 --prio 1 --cwd E:/OpenXCom -- \
        E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/render_chunks.py \
        --out art/units/pilot-gov4/render --max-renders 4 -- \
        E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/unit_pilot.py render
Без модели: render --dry-run (эскизы, входы, промпты), render --recut (готовые ответы; нет ответа - стоп, R-127).
"""
import argparse
import io
import json
import os
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(HERE))
PZ = os.path.join(ROOT, "Пиратки", "Dioxine_XPiratez", "user", "mods")
SHEET = os.path.join(PZ, "Piratez", "Resources", "Sprites", "GOV_4.png")
HANDOB_AK = os.path.join(PZ, "Piratez", "Resources", "HANDOB", "AK.png")    # кадры 352..359
DOLL = os.path.join(PZ, "Piratez", "Resources", "Body_X", "Govt_Pilot.png")  # GovtPilotInventoryImage
PAL = os.path.join(PZ, "Piratez", "Resources", "Pals", "delicious_regular.pal")
PACK = os.path.join(PZ, "hd", "hd", "GOV_4.PCK", "pack.hdp")
OUT = os.path.join(ROOT, "art", "units", "pilot-gov4")
W, H = 32, 40
K = 4
PAD = 8                                 # поле холста вокруг клетки, пикселей базы: части со смещением видны целиком

# drawRoutine0, ветка _drawingRoutine <= 10 (GOV_4 - процедура 0)
LEGS_STAND, LEGS_KNEEL, LEGS_WALK = 16, 24, 56
LARM_STAND, RARM_STAND, LARM_WALK, RARM_WALK = 0, 8, 40, 48
TORSO_MALE, DIE = 32, 264
RARM_1H, LARM_2H, RARM_2H, RARM_SHOOT = 232, 240, 248, 256
YOFF_WALK = (1, 0, -1, 0, 1, 0, -1, 0)
OFF_X = (8, 10, 7, 4, -9, -11, -7, -3)  # двуручное в прицеливании
OFF_Y = (-6, -3, 0, 2, 0, -4, -7, -9)
OFF_Y_KNEEL = 4
SOLDIER_HEIGHT = 22


def load_palette():
    v = open(PAL, encoding="ascii").read().split()
    return np.array([int(x) for x in v[3:3 + 768]], np.uint8).reshape(256, 3)


def load_frames(path):
    """Кадры листа 32x40 по строкам, индексы uint8 (как SurfaceSet: слева направо, сверху вниз)."""
    a = np.array(Image.open(path))
    cols = a.shape[1] // W
    return [a[y:y + H, x:x + W] for y in range(0, a.shape[0] - H + 1, H) for x in range(0, cols * W, W)]


def rgba(idx, pal):
    out = np.zeros(idx.shape + (4,), np.uint8)
    out[..., :3] = pal[idx]
    out[..., 3] = np.where(idx == 0, 0, 255)
    return Image.fromarray(out)


def load_pack(path):
    """pack.hdp (HdSprites::loadPack): OXHDPCK1, scale, база WxH, n, таблица (кадр, смещение, размер) -> {кадр: RGBA}."""
    out = {}
    with open(path, "rb") as f:
        head = f.read(24)
        if head[:8] != b"OXHDPCK1":
            raise SystemExit("не pack.hdp: %s" % path)
        scale, bw, bh, n = struct.unpack("<IIII", head[8:24])
        table = f.read(n * 12)
        for i in range(n):
            a, o, s = struct.unpack_from("<III", table, i * 12)
            if s:
                f.seek(o)
                out[a] = Image.open(io.BytesIO(f.read(s))).convert("RGBA")
    return scale, out


def parts(status, d, phase=0, item=None, kneel=False, stand_height=SOLDIER_HEIGHT):
    """Части в порядке наложения: [(часть, ('unit'|'item', кадр), offX, offY)] - drawRoutine0 для одного
    предмета в правой руке (двуручного или нет) или без предмета. status: stand | walk | aim | die."""
    if status == "die":
        return [("die", ("unit", DIE + phase), 0, 0)]
    torso = ["torso", ("unit", TORSO_MALE + d), 0, 0]
    y = 0
    if status == "walk":
        y = YOFF_WALK[phase]
        torso[3] = y
        legs = ["legs", ("unit", LEGS_WALK + 24 * d + phase), 0, 0]
        larm = ["larm", ("unit", LARM_WALK + 24 * d + phase), 0, 0]
        rarm = ["rarm", ("unit", RARM_WALK + 24 * d + phase), 0, 0]
    else:
        legs = ["legs", ("unit", (LEGS_KNEEL if kneel else LEGS_STAND) + d), 0, 0]
        larm = ["larm", ("unit", LARM_STAND + d), 0, 0]
        rarm = ["rarm", ("unit", RARM_STAND + d), 0, 0]
    itemR = None
    two = bool(item and item[1])
    if item:
        if status == "aim" and two:
            itemR = ["item", ("item", item[0] + (d + 2) % 8), OFF_X[d], OFF_Y[d]]
        else:
            itemR = ["item", ("item", item[0] + d), 0, 0]
        if two:
            larm[1] = ("unit", LARM_2H + d)
            rarm[1] = ("unit", (RARM_SHOOT if status == "aim" else RARM_2H) + d)
        else:
            rarm[1] = ("unit", RARM_1H + d)
        if status == "walk":
            itemR[3] += y
            rarm[3] = y
            if two:
                larm[3] = y
    if kneel:
        for p in (larm, rarm, torso):
            p[3] = OFF_Y_KNEEL
        if itemR:
            itemR[3] += OFF_Y_KNEEL
    elif status != "walk":
        larm[3] = rarm[3] = torso[3] = 0
    if itemR:
        itemR[3] += SOLDIER_HEIGHT - stand_height
    P = {"torso": torso, "legs": legs, "larm": larm, "rarm": rarm, "item": itemR}
    aiming = status == "aim"
    order = {
        0: ["item", "larm", "legs", "torso", "rarm"],
        1: ["larm", "legs", "torso", "item", "rarm"],
        2: ["larm", "legs", "torso", "item", "rarm"],
        3: (["legs", "torso", "larm", "item", "rarm"] if not aiming and two
            else ["legs", "torso", "larm", "rarm", "item"]),
        4: ["legs", "rarm", "torso", "larm", "item"],
        5: (["rarm", "legs", "torso", "larm", "item"] if not aiming and two
            else ["rarm", "legs", "item", "torso", "larm"]),
        6: ["rarm", "item", "legs", "torso", "larm"],
        7: (["rarm", "item", "larm", "legs", "torso"] if not aiming and two
            else ["item", "larm", "rarm", "legs", "torso"]),
    }[d]
    return [tuple(P[n]) for n in order if P[n] is not None]


def compose(layers, get, k):
    """Холст (W+2PAD)k x (H+2PAD)k: части по порядку, альфа-наложение как blit (пиксель части закрывает),
    плюс карта владельцев (номер слоя + 1, 0 - пусто)."""
    cw, ch = (W + 2 * PAD) * k, (H + 2 * PAD) * k
    canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    owner = np.zeros((ch, cw), np.uint8)
    for i, (_name, src, ox, oy) in enumerate(layers):
        im = get(src, k)
        if im is None:
            continue
        x, y = (PAD + ox) * k, (PAD + oy) * k
        canvas.alpha_composite(im, (x, y))
        a = np.asarray(im)[..., 3] > 0
        owner[y:y + im.height, x:x + im.width][a] = i + 1
    return canvas, owner


POSES = [  # (подпись, status, phase, предмет, на колене)
    ("стоит", "stand", 0, None, False),
    ("стоит, AK", "stand", 0, "ak", False),
    ("целится, AK", "aim", 0, "ak", False),
    ("на колене, AK", "stand", 0, "ak", True),
    ("шаг 0, AK", "walk", 0, "ak", False),
    ("шаг 2, AK", "walk", 2, "ak", False),
    ("шаг 4, AK", "walk", 4, "ak", False),
    ("шаг 6, AK", "walk", 6, "ak", False),
]
ITEMS = {"ak": (0, True)}               # (первый кадр в листе AK.png, двуручное) - HANDOB 352..359


class Sources:
    def __init__(self):
        self.pal = load_palette()
        self.unit = load_frames(SHEET)
        self.ak = load_frames(HANDOB_AK)
        self.scale, self.pack = load_pack(PACK)

    def classic(self, src, k):
        kind, n = src
        idx = (self.unit if kind == "unit" else self.ak)[n]
        if not idx.any():
            return None
        return rgba(idx, self.pal).resize((W * k, H * k), Image.NEAREST)

    def current(self, src, k):
        """Нынешний HD: кадр пака тела; предмета в HD нет - nearest, как без пака HANDOB."""
        kind, n = src
        if kind == "unit" and n in self.pack:
            im = self.pack[n]
            return im if im.size == (W * k, H * k) else im.resize((W * k, H * k), Image.LANCZOS)
        return self.classic(src, k)

    def layers(self, pose, d):
        _t, status, phase, item, kneel = pose
        return parts(status, d, phase, ITEMS[item] if item else None, kneel)


def bg_tile(w, h):
    """Подложка как пол боя: тёмная, чтобы не путать прозрачное с серым телом (R-089)."""
    return Image.new("RGBA", (w, h), (34, 38, 30, 255))


def font(size=14):
    try:
        return ImageFont.truetype("C:/Windows/Fonts/arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def cmd_poses(a):
    s = Sources()
    os.makedirs(OUT, exist_ok=True)
    cw, ch = (W + 2 * PAD) * K, (H + 2 * PAD) * K
    cols = [("оригинал x4 (nearest)", s.classic), ("нынешний пак (RealESRGAN, цвет файла)", s.current)]
    lab = 22
    sheet = Image.new("RGBA", (len(POSES) * (cw + 8) + 8, lab + len(cols) * (ch + lab) + ch // K + lab + 8),
                      (24, 24, 24, 255))
    d, fn = ImageDraw.Draw(sheet), font()
    for i, pose in enumerate(POSES):
        x = 8 + i * (cw + 8)
        d.text((x, 4), pose[0], fill=(255, 230, 120, 255), font=fn)
        L = s.layers(pose, a.dir)
        for r, (name, get) in enumerate(cols):
            y = lab + r * (ch + lab)
            if i == 0:
                d.text((x, y + ch + 2), name, fill=(200, 200, 200, 255), font=fn)
            im, _o = compose(L, get, K)
            t = bg_tile(cw, ch)
            t.alpha_composite(im)
            sheet.alpha_composite(t, (x, y))
        y = lab + len(cols) * (ch + lab)
        im, _o = compose(L, s.classic, 1)
        t = bg_tile(im.width, im.height)
        t.alpha_composite(im)
        sheet.alpha_composite(t, (x, y))
    d.text((8, sheet.height - lab), "x1 - как в игре при k=1; направление %d" % a.dir, fill=(200, 200, 200, 255),
           font=fn)
    p = os.path.join(OUT, "poses_dir%d.png" % a.dir)
    sheet.save(p)
    print("лист:", p, sheet.size)


# ------------------------------------------------------------------ рендер фигуры целиком

RENDER_OUT = os.path.join("art", "units", "pilot-gov4", "render")
SEED = 5200                             # один на всю фигуру GOV_4 (R-071): личность не скачет от позы к позе
RENDER_DIR = 3                          # к зрителю: лицо, грудь, оружие видны
# облик - по боевому листу (U4: боевой лист задаёт позу и сборку, кукла - только одежду): светлые короткие
# волосы (рампа 146-152), тёмная полоса на уровне глаз - очки-авиаторы (244-252), кожа (98-101), костюм в боевой
# палитре почти чёрный, красная нашивка на левой груди и на левом плече; у куклы шлем с очками - его не берём
WHO = ("a female government pilot with short blond hair and dark aviator sunglasses, bare hands, wearing a "
       "black one-piece flight coverall with a front zipper, chest and thigh pockets, a small red patch on the left "
       "chest and a red patch on the left shoulder, and black boots")
GUN = ", holding an old Kalashnikov-pattern assault rifle with dark steel and a brown wooden handguard and grip"
UNIT = ("<image1> is a clean shape sketch of a small figure from a tactical game: {what}. It is seen from above "
        "at the fixed isometric camera of the game and shown on a flat preview panel of colour RGB({r}, {g}, {b}). "
        "The panel is background, not part of the figure. "
        "Make a photorealistic render of this same real person: a real human body with natural anatomy and real "
        "clothing materials, the same camera from above, the light from the upper left. The person stands in "
        "exactly the pose, position, size and orientation of <image1>: the head, the arms, the hands, the legs, "
        "the feet and the rifle exactly where <image1> has them, the same silhouette and proportions, the same "
        "colour areas. Output one isolated figure on the same flat panel. No ground, no floor, no shadow outside "
        "the figure, no other people, no frame, no text.")
NEGATIVE_EXTRA = (", cartoon, toy, plastic figurine, doll, chibi, big head, helmet, extra limbs, extra fingers, "
                  "second person, floor, ground shadow, perspective distortion")
DOLL_TEXT = (" <image3> shows the same person's clothing from the front at a larger size: use it only for the cut "
             "of the flight suit, its pockets, zipper, seams and red patches. Ignore its helmet and goggles, its "
             "pose and its camera; the pose, the camera and the size come only from <image1>.")
CODE = (("unit_pilot.py", ("WHO", "GUN", "UNIT", "NEGATIVE_EXTRA", "DOLL_TEXT", "parts", "compose", "doll_input")),
        ("item_photo.py", ("crop_job", "canvas_map", "cut_fixed", "model_geometry", "model_holes")))


def unit_prompt(what, name, rgb):
    import photo_render as pr
    r, g, b = [int(v) for v in rgb]
    kind = "neutral " if name.startswith("grey") else ""
    return UNIT.format(what=what, r=r, g=g, b=b) + " " + pr.PANEL_TEXT.format(kind=kind, r=r, g=g, b=b)


def doll_input(crop, rgb, zoom):
    """Кукла инвентаря -> картинка размером кроп x zoom на той же подложке: фигура куклы по высоте габарита
    фигуры кропа, по центру его. Позу и камеру кукла не задаёт - только одежду (текст DOLL_TEXT)."""
    import item_photo as ip
    doll = Image.open(DOLL).convert("RGBA")
    bb = doll.split()[3].getbbox()
    fig = doll.crop(bb)
    ob = ip.main_bbox(np.asarray(crop)[..., 3] > 0, 4)
    th = (ob[3] - ob[1]) * zoom
    tw = max(1, round(fig.width * th / fig.height))
    fig = fig.resize((tw, th), Image.LANCZOS)
    flat = Image.new("RGBA", (crop.width * zoom, crop.height * zoom), tuple(int(v) for v in rgb) + (255,))
    cx = (ob[0] + ob[2]) * zoom // 2
    flat.alpha_composite(fig, (max(0, cx - tw // 2), ob[1] * zoom))
    return flat.convert("RGB")


def render_jobs(s, d, variants=("C", "D")):
    import item_photo as ip
    jobs = []
    for n, pose in enumerate(POSES):
        full, _o = compose(s.layers(pose, d), s.classic, 1)
        crop, box = ip.crop_job(full)
        tag = "d%d_p%d" % (d, n)
        what = WHO + (GUN if pose[3] else "")
        for v in [v for v in (("C", "D") if n in (0, 1) else ("C",)) if v in variants]:
            jobs.append({"asset_id": "GOV_4:%s:%s" % (tag, v), "name": "%s.%s" % (tag, v), "variant": v,
                         "pose": pose[0], "pose_n": n, "dir": d, "what": what, "seed": SEED,
                         "full": full, "crop": crop, "box": box})
    return jobs


def place(cut4, box, full):
    """Вырезка x4 кропа -> холст фигуры x4 ((W+2PAD) x (H+2PAD) базы): кроп сделан с полями ip.PAD."""
    import item_photo as ip
    big = Image.new("RGBA", ((full.width + 2 * ip.PAD) * K, (full.height + 2 * ip.PAD) * K), (0, 0, 0, 0))
    big.paste(cut4, (box[0] * K, box[1] * K))
    return big.crop((ip.PAD * K, ip.PAD * K, (ip.PAD + full.width) * K, (ip.PAD + full.height) * K))


def cmd_render(a):
    import asset_rev as ar
    import gen_fire
    import item_photo as ip
    import obj_gen_spec as ogs
    import obj_photo as op
    import photo_base as pb
    import photo_render as pr
    import struct_guide as sg
    import struct_probe as sp
    os.chdir(ROOT)
    s = Sources()
    jobs = render_jobs(s, a.dir, a.variants.split(","))
    R = sp.Render(a.out, a.models, a.max_renders, a.recut)
    neg = op.NEGATIVE + NEGATIVE_EXTRA
    gen_fire.NEGATIVE = R.po.gen_fire.NEGATIVE = neg
    base_inputs = sp.inputs

    def inputs(variant, frame, rgb):           # Render.job зовёт sp.inputs: D - вход C плюс кукла
        ims, extra, rep = base_inputs("C", frame, rgb)
        if variant == "D":
            return ims + [doll_input(frame, rgb, pr.RENDER_V1["zoom"])], extra + DOLL_TEXT, rep
        return ims, extra, rep
    sp.inputs = inputs
    pr.prompt_for = unit_prompt
    pb.cut = ip.cut_fixed
    R.grev = ar.h12({"params": pr.RENDER_V1, "prompt": UNIT, "who": WHO, "gun": GUN, "doll": DOLL_TEXT,
                     "negative_extra": NEGATIVE_EXTRA, "c_text": sp.C_TEXT, "seed": SEED,
                     "lock_rev": ogs.lock_rev(R.lock), "code": ogs.code_parts(pr.CODE + CODE)})
    print("unit_pilot GOV_4: generator_rev %s, guide_rev %s, заданий %d" % (R.grev, R.guide_rev, len(jobs)),
          flush=True)
    gd, raw_dir, meta_dir, fig_dir = (os.path.join(a.out, x) for x in ("guide", "raw", "meta", "figure"))
    for x in (gd, raw_dir, meta_dir, fig_dir):
        os.makedirs(x, exist_ok=True)
    plan = []
    for j in jobs:
        panels = pr.panels_by_margin(j["crop"])
        ims, extra, grep_ = inputs(j["variant"], j["crop"], panels[0][1])
        for i, im in enumerate(ims):
            im.save(os.path.join(gd, "%s.in%d.png" % (j["name"], i + 1)))
        plan.append((j, panels))
        print("%-12s %-14s seed %d подложка %s guide %s" % (j["name"], j["pose"], j["seed"], panels[0][0], grep_),
              flush=True)
    if a.dry_run:
        with open(os.path.join(a.out, "plan.md"), "w", encoding="utf-8-sig") as f:
            f.write("# unit_pilot GOV_4 - план (generator_rev %s)\n\nnegative: %s\n\n" % (R.grev, neg))
            for j, panels in plan:
                f.write("## %s - %s\n\n%s%s%s\n\n" % (j["name"], j["pose"], unit_prompt(j["what"], *panels[0][:2]),
                                                    " " + sp.C_TEXT, DOLL_TEXT if j["variant"] == "D" else ""))
        print("план:", os.path.join(a.out, "plan.md"))
        return
    missing = [j["name"] for j, _p in plan if not os.path.exists(os.path.join(raw_dir, j["name"] + ".a0.png"))]
    if a.recut and missing:                     # R-127
        raise SystemExit("--recut, а ответа нет у %d: %s" % (len(missing), missing[:5]))
    if missing:
        R.check_lock()
    t0 = time.time()
    try:
        for n, (j, panels) in enumerate(plan, 1):
            final, attempts = R.job(j["variant"], j, j["crop"], panels, raw_dir)
            if final is None:
                print("%-12s нет ответа (--recut)" % j["name"], flush=True)
                continue
            im, rep, _g, _m, c, verdict = final
            fig = place(im, j["box"], j["full"])
            fp = os.path.join(fig_dir, j["name"] + ".png")
            fig.save(fp)
            mg = rep["model"]
            meta = {"asset_id": j["asset_id"], "pose": j["pose"], "dir": j["dir"], "variant": j["variant"],
                    "what": j["what"], "generator_rev": R.grev, "guide_rev": R.guide_rev, "attempts": attempts,
                    "report": rep, "checks": {x: list(c[x]) for x in sp.pa.MACHINE_CHECKS}, "machine": verdict,
                    "figure": fp.replace("\\", "/"), "negative": neg, "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
            with open(os.path.join(meta_dir, j["name"] + ".json"), "w", encoding="utf-8-sig") as f:
                json.dump(meta, f, ensure_ascii=False, indent=1)
            print("%-12s %-14s %-8s модель %s / %s, края %s | готово %d из %d, прошло %.0f мин" % (
                j["name"], j["pose"], verdict, mg.get("dw_pct"), mg.get("dh_pct"), mg.get("edges"), n, len(plan),
                (time.time() - t0) / 60), flush=True)
    except sp.Budget:
        print("лимит процесса: новых рендеров %d из %d - выхожу, продолжит новый процесс" % (R.renders, R.max),
              flush=True)
        sys.exit(sp.EXIT_MORE)
    print("готово: заданий %d, новых рендеров в этом процессе %d" % (len(plan), R.renders), flush=True)


# ------------------------------------------------------------------ разрезка и сборка движком

def owners_grown(owner, alpha, steps=2 * K):
    """Пиксели ответа вне силуэтов частей (кромка до 1 пикс. базы) - ближайшей части: наращивание меток."""
    o = owner.copy()
    need = (alpha > 0) & (o == 0)
    for _ in range(steps):
        if not need.any():
            break
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            sh = np.zeros_like(o)
            ys = slice(max(dy, 0), o.shape[0] + min(dy, 0))
            yd = slice(max(-dy, 0), o.shape[0] + min(-dy, 0))
            xs = slice(max(dx, 0), o.shape[1] + min(dx, 0))
            xd = slice(max(-dx, 0), o.shape[1] + min(-dx, 0))
            sh[yd, xd] = o[ys, xs]
            take = need & (o == 0) & (sh > 0)
            o[take] = sh[take]
        need = (alpha > 0) & (o == 0)
    return o


def frame_name(src):
    """('unit', 35) -> 'GOV_4 35'; ('item', 3) -> 'HANDOB 355' (номер в листе мода, AK.png с 352)."""
    kind, n = src
    return "GOV_4 %d" % n if kind == "unit" else "HANDOB %d" % (352 + n)


def cut_parts(fig, layers, s):
    """Целая HD-фигура (холст x4) -> {('unit'|'item', кадр): RGBA 128x160}: пиксель отдаётся части, которая
    его рисует сверху в классике (карта владельцев compose x4 nearest), кромка - ближайшей части."""
    _c, owner = compose(layers, s.classic, K)
    a = np.asarray(fig)
    own = owners_grown(owner, a[..., 3])
    out = {}
    for i, (_name, src, ox, oy) in enumerate(layers):
        x, y = (PAD + ox) * K, (PAD + oy) * K
        piece = a[y:y + H * K, x:x + W * K].copy()
        mine = own[y:y + H * K, x:x + W * K] == i + 1
        piece[..., 3] = np.where(mine, piece[..., 3], 0)
        out[src] = piece
    return out


def cmd_assemble(a):
    """Один HD-кадр на номер (источник - первая поза в SOURCE_ORDER, где кадр есть), скрытое в ней - из других
    поз, где оно открыто, остаток - из нынешнего пака (помечено). Затем все позы собираются из ЭТИХ кадров так же,
    как движок, и сравниваются с целым рендером позы."""
    os.chdir(ROOT)
    s = Sources()
    fig_dir = os.path.join(a.out, "figure")
    poses = [(n, p) for n, p in enumerate(POSES)
             if os.path.exists(os.path.join(fig_dir, "d%d_p%d.%s.png" % (a.dir, n, a.variant)))]
    if not poses:
        raise SystemExit("нет готовых фигур в %s" % fig_dir)
    figs = {n: Image.open(os.path.join(fig_dir, "d%d_p%d.%s.png" % (a.dir, n, a.variant))).convert("RGBA")
            for n, _p in poses}
    cuts = {n: cut_parts(figs[n], s.layers(p, a.dir), s) for n, p in poses}
    order = [1] + [n for n, _p in poses if n != 1]          # «стоит, AK» - основной источник
    order = [n for n in order if n in cuts]
    frames, report = {}, {}
    for n in order:
        for src in cuts[n]:
            if src in frames:
                continue
            cls = s.classic(src, K)
            need = np.asarray(cls)[..., 3] > 0 if cls is not None else None
            out = np.zeros((H * K, W * K, 4), np.uint8)
            got = np.zeros((H * K, W * K), bool)
            used = []
            # оружие в других позах лежит в другом месте кадра - добор из них даёт обрывки второго автомата
            for m in [n] + ([x for x in order if x != n] if src[0] == "unit" else []):
                c = cuts[m].get(src)
                if c is None:
                    continue
                take = (c[..., 3] > 0) & ~got
                if take.any():
                    out[take] = c[take]
                    got |= take
                    used.append((m, int(take.sum())))
            fb = 0
            if need is not None:
                rest = need & ~got
                fb = int(rest.sum())
                if getattr(a, "fallback", "none") == "pack":
                    out[rest] = np.asarray(s.current(src, K))[rest]
            frames[src] = Image.fromarray(out, "RGBA")
            report[frame_name(src)] = {"from_poses": used, "fallback_pack_px": fb, "fallback": a.fallback,
                                     "need_px": int(need.sum()) if need is not None else 0}
    os.makedirs(os.path.join(a.out, "frames"), exist_ok=True)
    for src, im in frames.items():
        im.save(os.path.join(a.out, "frames", frame_name(src).replace(" ", "_") + ".png"))

    def hd(src, k):
        return frames.get(src) or s.current(src, k)

    cw, ch = (W + 2 * PAD) * K, (H + 2 * PAD) * K
    rows = [("оригинал x4", None), ("нынешний пак", None), ("целый рендер", None), ("собрано движком", None),
            ("разница", None)]
    lab = 22
    sheet = Image.new("RGBA", (len(poses) * (cw + 8) + 8, lab + len(rows) * (ch + lab) + 2 * (ch // K) + lab + 16),
                      (24, 24, 24, 255))
    d, fn = ImageDraw.Draw(sheet), font()
    diffs = {}
    for i, (n, p) in enumerate(poses):
        L = s.layers(p, a.dir)
        x = 8 + i * (cw + 8)
        d.text((x, 4), p[0], fill=(255, 230, 120, 255), font=fn)
        built, _o = compose(L, hd, K)
        whole = figs[n]
        wa, ba = np.asarray(whole).astype(int), np.asarray(built).astype(int)
        dm = (np.abs(wa - ba).max(-1) > 24) & ((wa[..., 3] > 0) | (ba[..., 3] > 0))
        diffs[p[0]] = int(dm.sum())
        dv = np.asarray(built).copy()
        dv[dm] = (255, 0, 255, 255)
        cells = [compose(L, s.classic, K)[0], compose(L, s.current, K)[0], whole, built, Image.fromarray(dv)]
        for r, im in enumerate(cells):
            y = lab + r * (ch + lab)
            t = bg_tile(cw, ch)
            t.alpha_composite(im)
            sheet.alpha_composite(t, (x, y))
            if i == 0:
                d.text((x, y + ch + 2), rows[r][0], fill=(200, 200, 200, 255), font=fn)
        y = lab + len(rows) * (ch + lab)
        for j, im in enumerate((compose(L, s.classic, 1)[0], built.resize((cw // K, ch // K), Image.BOX))):
            t = bg_tile(cw // K, ch // K)
            t.alpha_composite(im)
            sheet.alpha_composite(t, (x + j * (cw // K + 8), y))
    d.text((8, sheet.height - lab), "x1: оригинал | собрано (k=1, уменьшение)    направление %d, вариант %s" % (
        a.dir, a.variant), fill=(200, 200, 200, 255), font=fn)
    sp_ = os.path.join(a.out, "assemble_d%d_%s.png" % (a.dir, a.variant))
    sheet.save(sp_)
    with open(os.path.join(a.out, "assemble_d%d_%s.json" % (a.dir, a.variant)), "w", encoding="utf-8-sig") as f:
        json.dump({"frames": report, "diff_px": diffs}, f, ensure_ascii=False, indent=1)
    print("лист:", sp_)
    for k_, v in report.items():
        print("  %-10s из поз %s, из пака %d из %d" % (k_, v["from_poses"], v["fallback_pack_px"], v["need_px"]))
    print("  разница целое/собранное, пикс. HD:", diffs)


def cmd_compare(a):
    """Оригинал и новое в одном игровом масштабе: k=4 (128x160 на клетку) и k=1, все варианты рендера."""
    os.chdir(ROOT)
    s = Sources()
    fig_dir = os.path.join(a.out, "figure")
    cw, ch = (W + 2 * PAD) * K, (H + 2 * PAD) * K
    cols = []
    for n, p in enumerate(POSES):
        for v in ("C", "D"):
            f = os.path.join(fig_dir, "d%d_p%d.%s.png" % (a.dir, n, v))
            if os.path.exists(f):
                cols.append((n, p, v, Image.open(f).convert("RGBA")))
    if not cols:
        raise SystemExit("нет готовых фигур в %s" % fig_dir)
    lab = 22
    sheet = Image.new("RGBA", (len(cols) * (cw + 8) + 8, lab + 3 * (ch + lab) + ch // K + lab + 16),
                      (24, 24, 24, 255))
    d, fn = ImageDraw.Draw(sheet), font()
    for i, (n, p, v, fig) in enumerate(cols):
        L = s.layers(p, a.dir)
        x = 8 + i * (cw + 8)
        d.text((x, 4), "%s (%s)" % (p[0], v), fill=(255, 230, 120, 255), font=fn)
        for r, (name, im) in enumerate((("оригинал x4", compose(L, s.classic, K)[0]),
                                        ("нынешний пак", compose(L, s.current, K)[0]), ("новый", fig))):
            y = lab + r * (ch + lab)
            t = bg_tile(cw, ch)
            t.alpha_composite(im)
            sheet.alpha_composite(t, (x, y))
            if i == 0:
                d.text((x, y + ch + 2), name, fill=(200, 200, 200, 255), font=fn)
        y = lab + 3 * (ch + lab)
        for j, im in enumerate((compose(L, s.classic, 1)[0], fig.resize((cw // K, ch // K), Image.BOX))):
            t = bg_tile(cw // K, ch // K)
            t.alpha_composite(im)
            sheet.alpha_composite(t, (x + j * (cw // K + 8), y))
    d.text((8, sheet.height - lab), "x1: оригинал | новый; направление %d; C - эскиз+оригинал, D - плюс кукла" % a.dir,
           fill=(200, 200, 200, 255), font=fn)
    p_ = os.path.join(a.out, "compare_d%d.png" % a.dir)
    sheet.save(p_)
    print("лист:", p_)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("poses")
    p.add_argument("--dir", type=int, default=3)
    p = sub.add_parser("render")
    p.add_argument("--dir", type=int, default=RENDER_DIR)
    p.add_argument("--out", default=RENDER_OUT)
    p.add_argument("--dry-run", action="store_true", dest="dry_run")
    p.add_argument("--recut", action="store_true")
    p.add_argument("--models", default=None)
    p.add_argument("--max-renders", type=int, default=0, dest="max_renders")
    # D (третья картинка - кукла) на 5090 не влезает: ~31 ГБ, уходит в общую память, 65 с/шаг против 1.3 у C
    p.add_argument("--variants", default="C")
    for name in ("compare", "assemble"):
        p = sub.add_parser(name)
        p.add_argument("--dir", type=int, default=RENDER_DIR)
        p.add_argument("--out", default=RENDER_OUT)
        p.add_argument("--variant", default="C")
        # pack: незакрытое моделью место классического силуэта - из нынешнего пака (бахрома, второй автомат)
        p.add_argument("--fallback", choices=("none", "pack"), default="none")
    a = ap.parse_args()
    if a.cmd == "render":                   # явный вызов: граф test_gpu_scripts видит загрузку модели
        cmd_render(a)
    else:
        {"poses": cmd_poses, "compare": cmd_compare, "assemble": cmd_assemble}[a.cmd](a)


if __name__ == "__main__":
    main()
