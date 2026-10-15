#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Пилот хвата: одна проба - Томпсон, кадр HANDOB 1642, генератор изображений Codex (06.10).

Указание специалиста 06.10 после прогона #418 (Edit-2511 отклонён на всех шести): сократить пробу до одного
кадра Томпсона 1642, генератор ChatGPT/Codex - ТОЛЬКО после разрешения Vitali на этот конкретный запуск
(CLAUDE.md, правило 10). Остальные пять кадров не рисуются, пока этот не даст нужное качество и конструкцию.

Два входа, холст 2:3 (1024x1536, как отдаёт генератор; кадр 4:5 по центру, поля сверху и снизу по 128):
  1 - кадр HANDOB 1642 x32 nearest (замороженный codex/inputs/...in1_handob.png), чистый, без пометок:
      ракурс и размещение;
  2 - образец конструкции и материалов: weapons-chatgpt-v2/raw/STR_TOMMYGUN.cg0.png, сверен с BIGOBS 1279
      и боеприпасом 1280 (лист ref_check.png) - перечень и порядок деталей, материалы, не ориентация.
Схема зон модели НЕ подаётся (R-204: метки входа модель переносит в рисунок); места деталей - словами в промпте,
схема - только на проверочном листе (scheme_check.png, check_sheet.png).

Целевые места - target_zones.json (заморожено до генерации) с редакцией 2 target_zones_rev2.json, обе не
двигаются после ответа:
  рукоять        - zones.grip (target_zones.json);
  передняя рук.  - редакция 2: support = pose_hands.support.bbox_x4 (опорная кисть согласованной позы, 0.28 длины
                   от дула; передняя рукоять BIGOBS 0.26-0.35). Прежняя zones.support (0.56, на магазине)
                   сохранена в редакции как ошибочная;
  дуло           - muzzle_x4 (центр базового пикселя дула (25,14)).

prep     - входы, промпт, схема для листа, лист сверки образца; plan.json с хэшами. Видеокарту не трогает.
run      - codex exec по plan.json; нужен --approved "<слово Vitali на этот запуск>", пишется в plan.
check    - сырой ответ до обрезки (цвета пометок, фон, кайма) и итоговый PNG 128x160: один масштаб всего
           холста 1/8 и срез полей 2:3 -> 4:5 (без растяжки, без подгонки под рамку и зоны, R-208); сверка с
           замороженными рамкой, дулом и зонами - только числа и лист, в кадр ничего не вносится.
selftest - контроль меры: check на самом входе 1 обязан дать размер 0/0 и дуло 0, на входе со сдвигом на
           базовый пиксель вправо - дуло 4 x4 и размер 0/0; итоги в tommy1642/selftest/.

    py -3.13 tools/hdart/handob_tommy.py prep
    py -3.13 tools/hdart/handob_tommy.py selftest
    py -3.13 tools/hdart/handob_tommy.py run --approved "..."
    py -3.13 tools/hdart/handob_tommy.py check
"""
import argparse
import datetime
import hashlib
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)

import battle_view as bv                # noqa: E402
import grip_matrix as gm                # noqa: E402

ENC = "utf-8-sig"
PILOT = "art/items/weapons100-v1/grip_pilot"
OUT = os.path.join(PILOT, "tommy1642")
FREEZE = os.path.join(PILOT, "target_zones.json")
REV2 = os.path.join(PILOT, "target_zones_rev2.json")
KEY = "STR_TOMMYGUN.1642"
FRAME = 1642
IN1_FROZEN = os.path.join(PILOT, "codex", "inputs", KEY + ".in1_handob.png")
REF = "art/items/weapons-chatgpt-v2/raw/STR_TOMMYGUN.cg0.png"
BIGOBS = "art/items/weapons100-v1/cards/originals/STR_TOMMYGUN/BIGOBS_1279__export.png"
AMMO = 1280
BG_FROZEN = (16, 18, 26)                # фон замороженного входа HANDOB
# фон генерации: ровный зелёный, которого у Томпсона нет. На тёмном фоне тёмная сталь и приклад уходят в фон
# при вырезке (R-089: самопроверка на самом HANDOB дала высоту -10 %)
BG = (0, 190, 0)
W, H = 1024, 1536                       # холст генератора 2:3
PAD_Y = (H - 1280) // 2                 # кадр 32x40 x32 = 1024x1280 по центру
S = 32                                  # пикселей холста на пиксель базы
# цвета схемы - их нет у Томпсона (сталь, коричневое дерево) и они далеко от зелёного фона; по ним же ищутся
# скопированные метки
COL = {"grip": (0, 230, 255), "front": (255, 230, 0), "muzzle": (255, 0, 210)}

PROMPT = """Use exactly two input images.

Image 1 is the original low-resolution battle sprite of a Thompson submachine gun held by a soldier (32x40 pixels, \
enlarged with hard pixels, on a flat pure green background; the soldier and the hands are not part of it). It is the ONLY \
source of the view, the angle, the placement on the canvas, the length and the muzzle position. In image 1 the muzzle is \
the upper right end of the weapon and the butt is the lower left end.

Image 2 is a high-quality painting of the same Thompson submachine gun, seen in another view (standing upright, \
muzzle at the top). Take from it the construction, the list and the order of the parts, the materials and the \
quality of the painting. Do not take its orientation, its view, its proportions or its dark red glow from it.

Where the parts are along the weapon of image 1, counted from the muzzle to the butt:
- the brown wooden vertical front grip hangs under the barrel at about one quarter to one third of the length;
- the straight box magazine hangs under the receiver at about one half of the length;
- the brown wooden pistol grip with the trigger hangs under the weapon at about two thirds of the length, right \
behind the magazine;
- the wooden butt stock ends at the lower left end of image 1.

Draw the weapon of image 1 as a high-quality detailed game sprite with the construction, materials and painting \
quality of image 2: crisp painted game art, clean continuous edges, convincing dark steel and reddish-brown wood, \
readable small details.

Parts of the weapon, from the muzzle back to the butt (as in image 2): a small front sight at the muzzle end, a \
ribbed light grey cooling section on the barrel, the dark steel barrel, the brown wooden vertical front grip under \
the barrel, the dark steel receiver, a straight dark grey box magazine under the receiver in front of the trigger \
(a straight box, not a drum), the trigger guard, the brown wooden pistol grip, the brown wooden butt stock. Keep \
the vertical front grip: it is a real part of this weapon and must be clearly visible.

View: {view} The weapon is seen exactly as in image 1.

Keep exactly from image 1:
- the same angle and direction of the barrel and the same placement on the canvas;
- the muzzle at the upper right end and the butt end at the lower left end, exactly where image 1 has them; overall \
width and height of the weapon equal to image 1 within 3 percent;
- the magazine only where image 1 draws it under the receiver and of the size drawn there;
- no hands, no arms, no soldier, no shadow, no ground, no glow, no vignette, no text, no labels.

Avoid: {neg}, markers, crosses, outlines, frames, green edges, green reflections, red glow, drum magazine, missing \
front grip.

Output a portrait canvas with the 2:3 proportions of image 1 (1024x1536). Fill it exactly like image 1 fills it: the \
weapon at the same place and of the same size; everything else is the flat pure green background RGB 0,190,0 of image 1, \
no gradient, no green tint on the weapon."""


def sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def frozen_frame():
    with open(FREEZE, encoding=ENC) as f:
        fz = json.load(f)
    if sha(os.path.join(PILOT, "zones.json")) != fz["zones_json_sha256"]:
        raise SystemExit("zones.json изменён после заморозки - зоны не двигаются")
    fr = fz["frames"][KEY]
    if sha(IN1_FROZEN) != fr["inputs_sha256"]["in1"]:
        raise SystemExit("замороженный вход HANDOB 1642 изменён")
    with open(REV2, encoding=ENC) as f:
        rv = json.load(f)
    if rv["base_sha256"] != sha(FREEZE):
        raise SystemExit("target_zones.json изменён после редакции 2")
    return fz, dict(fr, rev2=rv["frames"][KEY])


def targets(fr):
    """Целевые места x4 (кадр 128x160): замороженные величины, передняя рукоять - по редакции 2."""
    rv = fr["rev2"]
    return {"grip": fr["zones"]["grip"][0], "front": rv["support"][0],
            "muzzle": fr["muzzle_x4"][:2], "bbox": fr["bbox_x4"],
            "support_rev1_erroneous": rv["support_rev1_erroneous"][0]}


def axis_fraction(fr, pts_x4):
    """Доля длины от дула вдоль оси кадра (дуло -> дальний от него пиксель силуэта), база."""
    idx = gm.hob(FRAME)
    ys, xs = np.nonzero(idx)
    mx, my = fr["muzzle_x4"][0] / 4.0, fr["muzzle_x4"][1] / 4.0
    d = np.hypot(xs + 0.5 - mx, ys + 0.5 - my)
    bx, by = xs[d.argmax()] + 0.5, ys[d.argmax()] + 0.5
    ax, ay = bx - mx, by - my
    L2 = ax * ax + ay * ay
    return {k: round(float(((x / 4.0 - mx) * ax + (y / 4.0 - my) * ay) / L2), 2) for k, (x, y) in pts_x4.items()}, \
        [round(float(bx), 1), round(float(by), 1)]


def center(b):
    return ((b[0] + b[2] + 1) / 2.0, (b[1] + b[3] + 1) / 2.0)


def wood_runs_bigobs():
    """Участки дерева и магазин BIGOBS 1279 по строкам (дулом вверх): доли длины от дула."""
    im = Image.open(BIGOBS)
    idx = np.asarray(im)
    pal = np.asarray(im.getpalette()[:768], np.uint8).reshape(-1, 3).astype(int)
    rgb, a = pal[idx], idx > 0
    ys, _ = np.nonzero(a)
    y0, y1 = ys.min(), ys.max()
    L = y1 - y0 + 1
    wood = a & (rgb[..., 0] > rgb[..., 1] + 25) & (rgb[..., 0] > rgb[..., 2] + 25) & (rgb[..., 0] > 60)
    rows = [y for y in range(y0, y1 + 1) if wood[y].sum() >= 2]
    runs, s = [], None
    for y in range(y0, y1 + 2):
        on = y in rows
        if on and s is None:
            s = y
        if not on and s is not None:
            runs.append((round(float(s - y0) / L, 2), round(float(y - y0) / L, 2)))
            s = None
    # магазин - первый сплошной ряд строк, где сталь уходит вбок во всю ширину (дальше - приклад)
    mag = []
    for y in range(y0, y1 + 1):
        if a[y, 8:].sum() >= 7 and not wood[y].any():
            mag.append(y)
        elif mag:
            break
    return {"wood": runs, "magazine": [round(float(min(mag) - y0) / L, 2), round(float(max(mag) - y0 + 1) / L, 2)]
            if mag else None}


# участки образца cg0 (1024x1536, дулом вверх, предмет по строкам 18..1500), сняты tommy_parts 06.10 и по листу
REF_PARTS = {"front_sight": [0.00, 0.03], "cooling_fins": [0.08, 0.21], "front_grip": [0.22, 0.35],
             "magazine": [0.41, 0.52], "pistol_grip": [0.58, 0.68], "stock": [0.68, 0.97]}


def input_files():
    """Входы модели: чистый HANDOB, образец конструкции, промпт. Схемы зон среди них нет."""
    d = os.path.join(OUT, "inputs")
    return {"in1": os.path.join(d, "in1_handob.png"), "in2": os.path.join(d, "in2_construction.png"),
            "prompt": os.path.join(d, "prompt.txt")}


def canvas_in1():
    im = Image.open(IN1_FROZEN).convert("RGB")
    if im.size != (1024, 1280):
        raise SystemExit("вход HANDOB: ждал 1024x1280, %s" % (im.size,))
    a = np.asarray(im).copy()
    bg = (a == np.array(BG_FROZEN)).all(axis=2)
    # фон - ровно там, где у кадра индекс 0 (кадр x32 nearest); иначе в кадре есть цвет фона
    want = np.repeat(np.repeat(gm.hob(FRAME) == 0, S, axis=0), S, axis=1)
    if not (bg == want).all():
        raise SystemExit("вход HANDOB: фон не совпал с прозрачными пикселями кадра (%d расхождений)" % (bg != want).sum())
    a[bg] = BG
    c = Image.new("RGB", (W, H), BG)
    c.paste(Image.fromarray(a), (0, PAD_Y))
    return c


def scheme(t):
    """Схема: силуэт кадра 1 серым контуром, рамки рукоятей и крест дула. Без надписей."""
    idx = gm.hob(FRAME)
    m = idx > 0
    c = Image.new("RGB", (W, H), BG)
    sil = Image.fromarray(np.where(m, 70, 0).astype(np.uint8)).resize((1024, 1280), Image.NEAREST)
    c.paste(Image.new("RGB", (1024, 1280), (70, 72, 80)), (0, PAD_Y), sil)
    d = ImageDraw.Draw(c)
    k = S / 4.0                          # x4 -> холст

    def box(b, col):
        x0, y0, x1, y1 = b[0] * k, b[1] * k + PAD_Y, (b[2] + 1) * k - 1, (b[3] + 1) * k - 1 + PAD_Y
        d.rectangle([x0, y0, x1, y1], outline=col, width=10)
    box(t["grip"], COL["grip"])
    box(t["front"], COL["front"])
    mx, my = (t["muzzle"][0] + 0.5) * k, (t["muzzle"][1] + 0.5) * k + PAD_Y
    d.line([mx - 40, my, mx + 40, my], fill=COL["muzzle"], width=10)
    d.line([mx, my - 40, mx, my + 40], fill=COL["muzzle"], width=10)
    return c


def indexed_rgba(path):
    """Кадр игры по индексам, 0 прозрачный (R-043), палитра своего файла."""
    im = Image.open(path)
    if im.mode != "P":
        raise SystemExit("%s: режим %s, ждал P" % (path, im.mode))
    idx = np.asarray(im)
    pal = np.asarray(im.getpalette()[:768], np.uint8).reshape(-1, 3)
    return Image.fromarray(np.dstack([pal[idx], np.where(idx == 0, 0, 255).astype(np.uint8)]), "RGBA")


def ref_check(fr, t, fracs):
    """Лист сверки образца: BIGOBS 1279, боеприпас 1280, образец cg0 одной высоты; доли деталей."""
    font = ImageFont.truetype("arial.ttf", 18)
    big = indexed_rgba(BIGOBS)
    bgb = Image.new("RGBA", big.size, BG_FROZEN + (255,))
    bgb.alpha_composite(big)
    bigx = bgb.convert("RGB").resize((big.width * 24, big.height * 24), Image.NEAREST)
    ref = Image.open(REF).convert("RGB")
    ref = ref.resize((int(ref.width * bigx.height / ref.height), bigx.height), Image.LANCZOS)
    ammo = None
    for root in ("art/items/weapons100-v1/cards/originals", "art/items/weapons100-v2-drawn/cards/originals"):
        for dp, _dn, fs in os.walk(root):
            for f_ in fs:
                if f_.startswith("BIGOBS_%d__" % AMMO):
                    ammo = os.path.join(dp, f_)
    pad = 20
    out = Image.new("RGB", (bigx.width + ref.width + 900 + 4 * pad, bigx.height + 140), (20, 22, 30))
    d = ImageDraw.Draw(out)
    d.text((pad, 8), "W-014 Томпсон: образец конструкции cg0 против BIGOBS 1279 и боеприпаса 1280; доли длины от дула",
           fill=(230, 230, 230), font=font)
    out.paste(bigx, (pad, 40))
    out.paste(ref, (2 * pad + bigx.width, 40))
    bo = wood_runs_bigobs()
    x = 3 * pad + bigx.width + ref.width
    y = 40
    lines = ["BIGOBS 1279 (дулом вверх):",
             "  дерево по длине: " + ", ".join("%.2f-%.2f" % r for r in bo["wood"]),
             "  магазин (сталь во всю ширину): %s" % ("%.2f-%.2f" % tuple(bo["magazine"]) if bo["magazine"] else "-"),
             "образец cg0:"] + ["  %s: %.2f-%.2f" % (k_, a, b) for k_, (a, b) in REF_PARTS.items()] + [
             "HANDOB 1642, проекция на ось дуло -> приклад:",
             "  рукоять (zones.grip): %.2f" % fracs["grip"],
             "  передняя рукоять (редакция 2, кисть позы): %.2f" % fracs["front"],
             "  zones.support ред. 1 (ошибочная, магазин): %.2f" % fracs["support_rev1_erroneous"],
             "",
             "Порядок деталей совпадает: передняя рукоять,",
             "магазин, рукоять, приклад. Расхождения образца:",
             "мушка у самого дула (у BIGOBS ствол на 0.11",
             "дальше мушки), магазин толще. Образец даёт",
             "перечень и материалы; места - кадр 1 и текст."]
    for ln in lines:
        d.text((x, y), ln, fill=(210, 210, 220), font=font)
        y += 26
    if ammo:
        am = indexed_rgba(ammo)
        bga = Image.new("RGBA", am.size, BG_FROZEN + (255,))
        bga.alpha_composite(am)
        amx = bga.convert("RGB").resize((am.width * 12, am.height * 12), Image.NEAREST)
        out.paste(amx, (x, y + 10))
        d.text((x, y + 20 + amx.height), "боеприпас 1280 «Барабан Томми»: кадр - прямая коробка", fill=(210, 210, 220),
               font=font)
    return out, bo


def prep():
    _fz, fr = frozen_frame()
    os.makedirs(os.path.join(OUT, "inputs"), exist_ok=True)
    t = targets(fr)
    fr_ax, butt = axis_fraction(fr, {"grip": center(t["grip"]), "front": center(t["front"]),
                                     "support_rev1_erroneous": center(t["support_rev1_erroneous"])})
    files = input_files()
    stale = os.path.join(OUT, "inputs", "in3_scheme.png")
    if os.path.exists(stale):              # схема модели больше не подаётся - во входах её быть не должно
        os.remove(stale)
    canvas_in1().save(files["in1"])
    ref = Image.open(REF).convert("RGB")
    if ref.size != (W, H):
        raise SystemExit("образец: ждал %dx%d, %s" % (W, H, ref.size))
    ref.save(files["in2"])
    scheme(t).save(os.path.join(OUT, "scheme_check.png"))
    pb = bv.prompt_block("hand_item")
    with open(files["prompt"], "w", encoding=ENC) as f:
        f.write(PROMPT.format(view=pb["positive"], neg=pb["negative"]))
    sheet, bo = ref_check(fr, t, fr_ax)
    sheet.save(os.path.join(OUT, "ref_check.png"))
    prev = Image.new("RGB", (2 * 512 + 30, 768 + 20), (20, 22, 30))
    for i, n in enumerate(("in1", "in2")):
        prev.paste(Image.open(files[n]).convert("RGB").resize((512, 768), Image.LANCZOS), (10 + i * 522, 10))
    prev.save(os.path.join(OUT, "inputs_preview.png"))
    plan = {"_note": "Одна проба: Томпсон HANDOB 1642, генератор Codex. Запуск только по слову Vitali на этот запуск "
                     "(CLAUDE.md, правило 10). Целевые места - target_zones.json и редакция 2, не двигаются. "
                     "Модели подаются два входа, схема зон - только на проверочном листе.",
            "prepared_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "frozen_in1_sha256": sha(IN1_FROZEN), "construction_ref": REF, "construction_ref_sha256": sha(REF),
            "zones_rev2": REV2, "zones_rev2_sha256": sha(REV2),
            "targets_x4": t, "axis_fraction_from_muzzle": fr_ax, "butt_base": butt,
            "bigobs_parts": bo, "ref_parts": REF_PARTS, "canvas": [W, H], "pad_y": PAD_Y,
            "front_grip_target": "редакция 2: pose_hands.support.bbox_x4 (опорная кисть позы, 0.28) - указание "
                                 "специалиста 06.10; прежняя zones.support (0.56) - ошибочная",
            "inputs_sha256": {n: sha(p) for n, p in files.items()}, "runs": []}
    with open(os.path.join(OUT, "plan.json"), "w", encoding=ENC) as f:
        json.dump(plan, f, ensure_ascii=False, indent=1)
    print("входы:", ", ".join(files.values()))
    print("доли длины от дула на 1642:", fr_ax, "приклад (база):", butt)
    print("BIGOBS 1279:", bo)
    print("план:", os.path.join(OUT, "plan.json"))


def run(approved):
    if not approved.strip():
        raise SystemExit("run: нужен --approved с разрешением Vitali на этот запуск (CLAUDE.md, правило 10)")
    import weapons_chatgpt as wc
    frozen_frame()
    with open(os.path.join(OUT, "plan.json"), encoding=ENC) as f:
        plan = json.load(f)
    files = input_files()
    bad = [n for n, p in files.items() if sha(p) != plan["inputs_sha256"].get(n)]
    if bad or set(plan["inputs_sha256"]) != set(files):
        raise SystemExit("входы изменены после prep: %s" % (bad or sorted(plan["inputs_sha256"])))
    if sha(REV2) != plan.get("zones_rev2_sha256"):
        raise SystemExit("редакция 2 зон изменена после prep")
    with open(files["prompt"], encoding=ENC) as f:
        prompt = f.read()
    wc.OUT = OUT
    os.makedirs(os.path.join(OUT, "raw"), exist_ok=True)
    dst = wc.call({"type": KEY, "master": "W-014"}, [files["in1"], files["in2"]], prompt)
    plan["runs"].append({"at": datetime.datetime.now().isoformat(timespec="seconds"), "approved": approved,
                         "raw": dst})
    with open(os.path.join(OUT, "plan.json"), "w", encoding=ENC) as f:
        json.dump(plan, f, ensure_ascii=False, indent=1)


def check(raw_path, out=OUT):
    _fz, fr = frozen_frame()
    with open(os.path.join(OUT, "plan.json"), encoding=ENC) as f:
        plan = json.load(f)
    t = plan["targets_x4"]
    if not raw_path:
        runs = [r for r in plan["runs"] if r.get("raw")]
        if not runs:
            raise SystemExit("нет ответа: run ещё не запускался")
        raw_path = runs[-1]["raw"]
    raw = Image.open(raw_path)
    rep = {"raw": raw_path, "raw_size": list(raw.size), "raw_mode": raw.mode}
    rgba = np.asarray(raw.convert("RGBA")).astype(int)
    rgb = rgba[..., :3]
    # 1. сырой ответ: метки схемы, фон, предмет
    marks = {}
    for k, c in COL.items():
        dist = np.abs(rgb - np.array(c)).sum(axis=2)
        marks[k] = int((dist < 90).sum())
    rep["scheme_colour_pixels"] = marks
    if raw.size != (W, H):
        rep["verdict_raw"] = "FAIL: холст %s, ждал %dx%d - масштаб кадра не определён, обрезать нельзя" % (raw.size, W, H)
        print(json.dumps(rep, ensure_ascii=False, indent=1))
        return
    has_alpha = raw.mode == "RGBA" and (rgba[..., 3] < 250).mean() > 0.2
    if has_alpha:
        fg = rgba[..., 3] > 127
        rep["background"] = "прозрачный в ответе"
    else:
        dist_bg = np.abs(rgb - np.array(BG)).sum(axis=2)
        edge = np.concatenate([dist_bg[:40].ravel(), dist_bg[-40:].ravel(), dist_bg[:, :40].ravel(), dist_bg[:, -40:].ravel()])
        rep["background_edge_median_diff"] = float(np.median(edge))
        fg = dist_bg > 60
        rep["background"] = "ровный зелёный RGB 0,190,0" if np.median(edge) < 20 else "НЕ ровный - фон отличается от заданного"
    # зелёная кайма: пиксели предмета у края силуэта, где зелёный перебивает красный и синий (R-157)
    r_, g_, b_ = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    inner = np.zeros_like(fg)
    inner[2:-2, 2:-2] = fg[2:-2, 2:-2] & fg[:-4, 2:-2] & fg[4:, 2:-2] & fg[2:-2, :-4] & fg[2:-2, 4:]
    rim = fg & ~inner
    tinted = (g_ > r_ + 30) & (g_ > b_ + 30)
    rep["green_rim_share"] = round(float((rim & tinted).sum()) / max(1, int(rim.sum())), 3)
    rep["green_body_share"] = round(float((inner & tinted).sum()) / max(1, int(inner.sum())), 3)
    ys, xs = np.nonzero(fg)
    rep["raw_bbox_canvas"] = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())] if len(xs) else None
    if len(xs):
        # конец ствола в сыром ответе, до обрезки и уменьшения: та же ось приклад -> дуло, холст = база x32 со сдвигом
        # полей; ошибка - до квадрата 32x32 базового пикселя дула оригинала
        mbx, mby = t["muzzle"][0] // 4, t["muzzle"][1] // 4
        ax_, ay_ = (mbx + 0.5 - plan["butt_base"][0]) * S, (mby + 0.5 - plan["butt_base"][1]) * S
        k_ = np.argmax((xs + 0.5) * ax_ + (ys + 0.5) * ay_)
        rx, ry = int(xs[k_]), int(ys[k_])
        q0x, q0y = mbx * S, mby * S + PAD_Y
        ddx = max(q0x - rx, 0, rx - (q0x + S - 1))
        ddy = max(q0y - ry, 0, ry - (q0y + S - 1))
        rep["raw_far_end_canvas"] = [rx, ry]
        rep["raw_far_end_base"] = [rx // S, (ry - PAD_Y) // S]
        rep["raw_muzzle_err_base"] = round(float(np.hypot(ddx, ddy)) / S, 2)
    # 2. итоговый PNG: один масштаб всего холста, срез полей 2:3 -> 4:5; альфа - по фону ответа
    small_rgb = Image.fromarray(rgb.astype(np.uint8)).resize((W // 8, H // 8), Image.LANCZOS)
    small_a = Image.fromarray((fg * 255).astype(np.uint8)).resize((W // 8, H // 8), Image.BOX)
    top = PAD_Y // 8
    hd = Image.merge("RGBA", small_rgb.split() + (small_a,)).crop((0, top, 128, top + 160))
    os.makedirs(os.path.join(out, "hd"), exist_ok=True)
    hd_path = os.path.join(out, "hd", "%d.png" % FRAME)
    hd.save(hd_path)
    a = np.asarray(hd)[..., 3] > 127
    ys, xs = np.nonzero(a)
    bb = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())] if len(xs) else None
    tb = t["bbox"]
    rep["hd"] = hd_path
    rep["hd_bbox_x4"] = bb
    rep["target_bbox_x4"] = tb
    if bb:
        rep["size_pct"] = [round(100.0 * ((bb[2] - bb[0] + 1) / (tb[2] - tb[0] + 1) - 1), 1),
                           round(100.0 * ((bb[3] - bb[1] + 1) / (tb[3] - tb[1] + 1) - 1), 1)]
        # дуло: самый дальний пиксель итога по замороженной оси приклад -> дуло (не по углу рамки). Цель - базовый
        # пиксель дула, то есть блок 4x4 в x4 (muzzle_x4 - его центр); ошибка - расстояние от дальнего пикселя до
        # этого блока, 0 внутри него. Прежняя мера брала расстояние до центра блока: у самого кадра дальний пиксель
        # (103,56) - угол того же базового пикселя (25,14), и выходило 2.2 при нулевой ошибке
        mx, my = t["muzzle"]
        bx, by = plan["butt_base"][0] * 4.0, plan["butt_base"][1] * 4.0
        ax, ay = mx + 0.5 - bx, my + 0.5 - by
        far = np.argmax((xs + 0.5) * ax + (ys + 0.5) * ay)
        fx, fy = int(xs[far]), int(ys[far])
        b0x, b0y = (mx // 4) * 4, (my // 4) * 4
        dx = max(b0x - fx, 0, fx - (b0x + 3))
        dy = max(b0y - fy, 0, fy - (b0y + 3))
        rep["hd_far_end_x4"] = [fx, fy]
        rep["hd_far_end_base"] = [fx // 4, fy // 4]
        rep["muzzle_base"] = [mx // 4, my // 4]
        rep["muzzle_err_x4"] = round(float(np.hypot(dx, dy)), 1)
        rep["muzzle_err_base"] = round(float(np.hypot(dx, dy)) / 4.0, 2)
        rep["muzzle_to_centre_x4"] = round(float(np.hypot(fx + 0.5 - (mx + 0.5), fy + 0.5 - (my + 0.5))), 1)
        rep["muzzle_ok"] = rep["muzzle_err_x4"] <= fr["muzzle_tolerance_px_x4"]
        rep["muzzle_note"] = ("ошибка 0 - конец ствола внутри базового пикселя дула оригинала, то есть в его области "
                              "неопределённости (квадрат 4x4 в x4), а не точное совпадение координат")
        rep["muzzle_nearest_px_x4"] = round(float(np.hypot(xs - mx, ys - my).min()), 1)
    for k in ("grip", "front"):
        b = t[k]
        rep["fill_%s" % k] = round(float(a[b[1]:b[3] + 1, b[0]:b[2] + 1].mean()), 2)
    # лист: сырой ответ целиком, итог на полу боя x6, итог с целевыми местами (только на листе)
    font = ImageFont.truetype("arial.ttf", 16)
    rawv = raw.convert("RGB").resize((512, 768), Image.LANCZOS)
    floor = Image.new("RGBA", (128, 160), (58, 60, 66, 255))
    floor.alpha_composite(hd)
    f6 = floor.convert("RGB").resize((768, 960), Image.LANCZOS)
    f6m = f6.copy()
    dm = ImageDraw.Draw(f6m)
    for k, c in (("grip", COL["grip"]), ("front", COL["front"])):
        b = t[k]
        dm.rectangle([b[0] * 6, b[1] * 6, (b[2] + 1) * 6 - 1, (b[3] + 1) * 6 - 1], outline=c, width=2)
    mx, my = t["muzzle"]
    dm.line([mx * 6 - 14, my * 6 + 3, mx * 6 + 20, my * 6 + 3], fill=COL["muzzle"], width=2)
    dm.line([mx * 6 + 3, my * 6 - 14, mx * 6 + 3, my * 6 + 20], fill=COL["muzzle"], width=2)
    dm.rectangle([tb[0] * 6, tb[1] * 6, (tb[2] + 1) * 6 - 1, (tb[3] + 1) * 6 - 1], outline=(255, 255, 255), width=1)
    sheet = Image.new("RGB", (512 + 2 * 768 + 40, 1000), (20, 22, 30))
    sheet.paste(rawv, (10, 30))
    sheet.paste(f6, (532, 30))
    sheet.paste(f6m, (1310, 30))
    d = ImageDraw.Draw(sheet)
    d.text((10, 6), "сырой ответ (до обрезки)", fill=(230, 230, 230), font=font)
    d.text((532, 6), "итог 128x160 на полу боя x6", fill=(230, 230, 230), font=font)
    d.text((1310, 6), "места (только на листе): белая - рамка, голубая - рукоять,", fill=(230, 230, 230), font=font)
    d.text((1310, 994 - 30), "жёлтая - передняя рукоять (ред. 2), крест - дуло", fill=(230, 230, 230), font=font)
    sheet.save(os.path.join(out, "check_sheet.png"))
    with open(os.path.join(out, "check.json"), "w", encoding=ENC) as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    print("лист:", os.path.join(out, "check_sheet.png"))
    return rep


def selftest():
    """Контроль меры: сам вход 1 вместо ответа - размер 0/0, дуло 0; вход со сдвигом на базовый пиксель вправо
    (32 пикселя холста) - размер 0/0, дуло 4 x4 (ровно один базовый пиксель)."""
    base = os.path.join(OUT, "selftest")
    src = input_files()["in1"]
    shifted = os.path.join(base, "in1_shift_right_1.png")
    os.makedirs(base, exist_ok=True)
    a = np.asarray(Image.open(src).convert("RGB"))
    b = np.empty_like(a)
    b[:] = BG
    b[:, S:] = a[:, :-S]
    Image.fromarray(b).save(shifted)
    res = {}
    for name, p, want in (("identity", src, 0.0), ("shift_right_1", shifted, 4.0)):
        r = check(p, os.path.join(base, name))
        ok = (r.get("size_pct") == [0.0, 0.0] and r.get("muzzle_err_x4") == want
              and r.get("raw_muzzle_err_base") == want / 4.0)
        res[name] = {"size_pct": r.get("size_pct"), "muzzle_err_x4": r.get("muzzle_err_x4"),
                     "muzzle_to_centre_x4": r.get("muzzle_to_centre_x4"), "want_muzzle_err_x4": want,
                     "raw_muzzle_err_base": r.get("raw_muzzle_err_base"), "want_raw_muzzle_err_base": want / 4.0,
                     "pass": ok}
    with open(os.path.join(base, "selftest.json"), "w", encoding=ENC) as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    if not all(v["pass"] for v in res.values()):
        raise SystemExit("самопроверка меры НЕ прошла")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["prep", "run", "check", "selftest"])
    ap.add_argument("--approved", default="", help="run: слово Vitali на этот запуск")
    ap.add_argument("--raw", default="", help="check: путь ответа (по умолчанию последний run)")
    a = ap.parse_args()
    os.chdir(ROOT)
    if a.cmd == "prep":
        prep()
    elif a.cmd == "run":
        run(a.approved)
    elif a.cmd == "selftest":
        selftest()
    else:
        check(a.raw)


if __name__ == "__main__":
    main()
