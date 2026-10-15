#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проба генератора ChatGPT (встроенный image_gen Codex CLI под ChatGPT-аккаунтом) на оружии без эталона (05.10).

Видеокарту не трогает: картинку рисует сервис OpenAI, сюда приходит готовый PNG. Поэтому без gpuq.

prep  - входы: оригинал 32x48 крупно nearest (раскладка, размер, цвета, дуло) и эталон Vitali (только манера).
run   - codex exec с входами (-i), промпт из файла inputs/<тип>.prompt.txt; ответ копируется в raw/<тип>.cgN.png.
После run результат обрабатывается weapon_from_ref.py --ref raw/... (матт, равномерный масштаб, без подгонки)
и проверяется weapon_fit.py --synth.
Запуск: py -3.13 tools/hdart/weapons_chatgpt.py prep --only W-015; ... run --only W-015
edit  - локальная правка готового ответа (указание 05.10): картинка 1 - ответ (--base), картинка 2 - оригинал
        для геометрии, образца манеры нет; промпт - inputs/<тип>.edit.prompt.txt, ответ raw/<тип>.cgN.png.
"""
import argparse
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)

from PIL import Image                   # noqa: E402

import item_photo as ip                 # noqa: E402
import weapon_fit as wf                 # noqa: E402

ENC = "utf-8-sig"
OUT = "art/items/weapons-chatgpt-v1"
STYLE_REF = "art/items/refs/vitali/street_sweeper.webp"
GEN_DIR = os.path.expanduser("~/.codex/generated_images")

PROMPT = """Image 1 is the original low-resolution game sprite of a weapon (32x48 pixels, enlarged with hard pixels). \
It is the ONLY source of the design. Image 2 is a style example only: a different weapon that shows the wanted \
rendering quality. Do not copy any part, shape or color of image 2.

Redraw the weapon of image 1 as a high-quality detailed inventory sprite, in the same rendering style as image 2: \
crisp painted game art, clean continuous edges, convincing steel and wood, readable small details.

Keep exactly from image 1:
- vertical orientation, muzzle at the top, the same placement in the frame;
- overall width and height of the weapon relative to the frame, within 3 percent;
- every part in its place and of its size: {parts};
- the colors of each region as in image 1 (only cleaner);
- nothing added, nothing removed, no text, no labels.

Fill the whole 2:3 portrait canvas exactly like image 1 fills its frame. Transparent background."""

# --solo: без образца манеры - в первой пробе (cg0) генератор взял у образца второй ствол и оранжевую метку
SOLO_HEAD = """Image 1 is the original low-resolution game sprite of a weapon (32x48 pixels, enlarged with hard pixels). \
It is the ONLY source of the design.

Redraw the weapon of image 1 as a high-quality detailed inventory sprite: crisp painted game art in the style of a \
modern tactical game inventory icon, clean continuous edges, convincing steel and wood, readable small details. \
One single barrel exactly as drawn; do not add barrels, lights, markers or parts that image 1 does not show."""


# --v2 (05.10, проверочный набор после карточек боеприпасов): описание из describe/what_v2.tsv, ориентация и
# материалы - свои у предмета, а не «vertical, muzzle at the top» и «steel and wood» на всех (R-221)
OUT2 = "art/items/weapons-chatgpt-v2"
WHAT2 = "art/items/weapons100-v1/describe/what_v2.tsv"
PROMPT2 = """Image 1 is the original low-resolution game sprite of a weapon (32x48 pixels, enlarged with hard pixels). \
It is the ONLY source of the design. Image 2 is a style example only: a different weapon that shows the wanted \
rendering quality. Do not copy any part, shape or color of image 2.

Redraw the weapon of image 1 as a high-quality detailed inventory sprite, in the same rendering style as image 2: \
crisp painted game art, clean continuous edges, convincing materials, readable small details.

What the weapon is: {what}

Keep exactly from image 1:
- the orientation and placement in the frame exactly as in image 1;
- overall width and height of the weapon relative to the frame, within 3 percent;
- every part in its place and of its size{feed};
- the colors of each region as in image 1 (only cleaner);
- nothing added, nothing removed, no text, no labels.

Fill the whole 2:3 portrait canvas exactly like image 1 fills its frame. Transparent background."""


def what2(master):
    import csv
    with open(WHAT2, encoding=ENC) as f:
        for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            if r["master"] == master:
                return r
    raise SystemExit("нет строки %s в %s" % (master, WHAT2))


def prompt_text(parts, solo):
    if not solo:
        return PROMPT.format(parts=parts)
    return SOLO_HEAD + PROMPT.format(parts=parts)[PROMPT.index("\n\nKeep exactly"):]


def rows_for(only):
    want = set(only.split(","))
    lrows = wf.list_rows()
    out = []
    for k in range(1, 6):
        for r in wf.batch_rows(k):
            if r["master"] in want:
                out.append((r, lrows[r["master"]]))
    if not out:
        raise SystemExit("нет строк опознания для %s" % only)
    return out


def prep(row, lrow, solo=False):
    t = row["type"]
    ip.CARDS = "art/items/weapons100-v1/cards"
    full, _src = ip.load_frame(t, int(lrow["frame"]))
    bg = Image.new("RGBA", full.size, (16, 18, 26, 255))
    bg.alpha_composite(full)
    p1 = os.path.join(OUT, "inputs", t + ".in1_sprite.png")
    bg.convert("RGB").resize((full.width * 32, full.height * 32), Image.NEAREST).save(p1)
    p2 = os.path.join(OUT, "inputs", t + ".in2_style.png")
    Image.open(STYLE_REF).convert("RGB").save(p2)
    parts = (row.get("details") or "").strip() or "all parts as drawn"
    pt = os.path.join(OUT, "inputs", t + (".solo" if solo else "") + ".prompt.txt")
    if OUT == OUT2:
        if solo:
            raise SystemExit("--v2 без --solo: проверочный набор идёт со входом манеры")
        w2 = what2(row["master"])
        # магазин называется только у того, у кого он есть на кадре; холодному и луку - ни слова (R-221)
        feed = "" if w2["magazine"].strip().startswith("нет") else \
            ", including the magazine or feed part exactly in the shape drawn in image 1"
        text = PROMPT2.format(what=w2["what_v2"].strip(), feed=feed)
    else:
        text = prompt_text(parts, solo)
    with open(pt, "w", encoding=ENC) as f:
        f.write(text)
    print("%s входы: %s, %s, %s" % (row["master"], p1, p2, pt))


EDIT_PROMPT = """Edit image 1. It is a finished high-quality drawing of {head}. \
Do not redraw the weapon and do not copy the pixel look of image 2.

Make exactly these changes and nothing else:
{changes}

Everything else stays exactly as in image 1: {keep}; the same colors, lighting, painted rendering, scale, position \
in the frame and canvas size. Nothing added. Keep the same flat {bg} background as image 1."""

# начало промпта правки и фон по типу; по умолчанию - дробовик (первые правки 05.10)
EDIT_HEAD = {
    "STR_COMBAT_SHOTGUN": ("a vertical shotgun (muzzle at the top). Image 2 is the original low-resolution game "
                           "sprite of the same weapon, given only as the reference for the geometry: it has ONE barrel",
                           "dark"),
    # револьвер (специалист 05.10): выступ оригинала строки 23-28, столбцы 1-4 - спица курка и задний край рамки
    "STR_REVOLVER": ("a single-action revolver standing vertically: the muzzle at the top, the cylinder in the middle, "
                     "the trigger guard on the right, the wooden grip at the bottom going down to the right; so the "
                     "left side of the picture is the top of the gun and downwards is towards its rear. Image 2 is "
                     "the original low-resolution game sprite of the same revolver, given only as the reference for "
                     "the geometry",
                     "green"),
}

EDIT_CHANGES = {
    "STR_COMBAT_SHOTGUN": (
        "1. Remove the second, shorter barrel tube on the right side of the upper part - from its muzzle cap down to "
        "the receiver block above the side magazine. The weapon has a single barrel: the long left one. Where the "
        "removed tube was, show only the flat dark background. The clamp on the left barrel stays, sized for one barrel.\n"
        "2. Replace the orange band near the muzzle of the left barrel with plain dark steel like the rest of the barrel.",
        "the side box magazine sticking out to the right with its slots, the steel receiver blocks, the wooden forend, "
        "the trigger guard and trigger, the small brackets on the left, the wooden stock with its steel butt plate"),
    # конструкция магазина (специалист 05.10): в cg2 магазин - цилиндр с прорезями, похожий на фильтр. Кадр ствола
    # (строки 12-17, столбцы 6-12) и кадр боеприпаса STR_COMBAT_SHOTGUN_DRUM (BIGOBS 1234, 9x9, прямые углы) - коробка
    "STR_COMBAT_SHOTGUN.mag": (
        "1. Replace the round ribbed cylinder with slots that sticks out to the right below the barrel (it looks like a "
        "filter) with a detachable BOX magazine for shotgun shells, as on magazine-fed pump shotguns: a straight "
        "rectangular box with flat parallel sides, sharp square corners and a flat square floor plate at its outer "
        "right end; dark grey steel, two shallow raised ribs running along its length. No round shapes, no end cap, no "
        "slots, no holes, no visible shells. It enters the receiver block where the cylinder did, at the same height, "
        "with the same length and the same thickness as the cylinder.",
        "the single barrel with its muzzle; the clamp holding the barrel below the muzzle - a separate part at exactly "
        "its place; the steel receiver blocks; the wooden forend; the trigger guard and trigger; the small brackets on "
        "the left; the wooden stock - keep its shape, its brown color and its wood grain - with its steel butt plate"),
    # размер коробки (специалист 05.10): у cg3 коробка длиннее и тоньше оригинала. Границы - кадр 1233, строки 12-17,
    # столбцы 9-13 (7-8 - место крепления, кольцо cg3 x 273-318), пересчёт по неизменным частям: 30,19 пикс на строку,
    # 31,33 на столбец -> x 320..484, y 395..576 в картинке 1 (1024x1536). Вклеивается только --region
    "STR_COMBAT_SHOTGUN.mag2": (
        "1. Resize only the box magazine that sticks out to the right below the barrel. In image 1 (1024 x 1536 "
        "pixels) it now spans x 318 to 521 and y 400 to 536: too long and too thin. Redraw it to span exactly x 320 "
        "to 484 and y 395 to 576: shorter, its flat end plate at x 484, and thicker, top edge at y 395 and bottom "
        "edge at y 576. It stays a closed dark grey steel box with flat sides, sharp square corners, the two shallow "
        "raised ribs along its length and the flat end plate. No slots, no holes, no round shapes. Its inner end "
        "still enters the bright steel ring at x 273 to 318, which stays exactly as it is. Where the old box was "
        "longer than x 484, show only the flat dark background.",
        "the muzzle; the clamp holding the barrel below the muzzle; the bright steel ring where the magazine is "
        "attached; the steel receiver blocks; the wooden forend; the trigger guard and trigger; the small brackets "
        "on the left; the wooden stock with its shape, brown color and wood grain, and its steel butt plate"),
}
EDIT_CHANGES["STR_REVOLVER"] = (
    # координаты - пересчёт строк и столбцов оригинала по рамке measure_STR_REVOLVER.json (50,9 пикс на столбец,
    # 51,0 на строку): металл строк 23-25 - x 72..327, y 1150..1303; спица строк 26-28 - x 123..275, y 1303..1456
    "1. The hammer is too high. In image 1 (1024 x 1536 pixels) the hammer with its checkered spur sits right behind "
    "the cylinder at x 80 to 240, y 960 to 1130. In image 2 it sits much lower, behind the top of the wooden grip. "
    "Move it there. The steel frame behind the cylinder continues downwards as one solid piece of the same dark "
    "steel: its left edge at x 120 from y 960 down to y 1150, then at x 75 from y 1150 down to y 1300; on the right "
    "it joins the steel backstrap that runs along the top of the wooden grip at x 290 to 330.\n"
    "2. The hammer sits in the lower part of this frame, its body at y 1150 to 1300. Its curved checkered spur sticks "
    "out of the frame downwards and to the left: it starts at x 170 to 275 at y 1300 and ends in a rounded tip at x "
    "125 to 175, y 1450.\n"
    "3. Where the old hammer spur stuck out to the left above y 1150 and left of x 120, show only the flat green "
    "background.",
    "the barrel and front sight, the cylinder, the frame around the cylinder, the trigger guard and the trigger, the "
    "two round screws on the frame, the wooden grip with its color, wood grain and its screw")
# cg1 по тексту выше сдвинул курок лишь на ~50 пикс: перестройку словами генератор не делает. Поэтому курок перенесён
# целиком жёстким сдвигом (0, 230), под ним ровная заготовка рамки по строкам 20-25 оригинала (scratchpad rv_paste.py,
# inputs/STR_REVOLVER.paste1.log.json), а генератор только дорисовывает металл в заготовке и стыки
EDIT_CHANGES["STR_REVOLVER.paste"] = (
    "1. Image 1 is not finished in one place: below the cylinder on the left there is a flat, plain dark grey area "
    "with a black outline (x 75 to 300, y 990 to 1340 in the 1024 x 1536 picture). It is the rear part of the steel "
    "frame, not yet painted. Paint it as the same dark blued steel as the rest of the frame - the same texture, wear, "
    "highlights and black outline - keeping its outline exactly: the frame continues straight down from the frame "
    "around the cylinder, joins the steel backstrap along the top of the wooden grip on the right, and its lower "
    "left part holds the hammer. Its left edge is one straight slanted line and its lower corners are rounded, like "
    "a cast revolver frame: no steps, no notches, no boxy blocks; where it meets the existing frame below the "
    "cylinder, it continues it seamlessly.\n"
    "2. The hammer with its checkered spur now sits at the lower left of this frame (spur tip at about x 90, y 1355). "
    "Keep its shape, size and place; only make its joins with the frame clean and natural, as a hammer seated in a "
    "revolver frame. Remove the small loose sliver of steel to the right of the hammer at about x 180 to 250, y 1240 "
    "to 1260.",
    "the barrel and front sight, the cylinder, the frame around the cylinder, the trigger guard and the trigger, the "
    "two round screws on the frame, the wooden grip with its color, wood grain and its screw")
REGION = {"STR_COMBAT_SHOTGUN.mag2": (318, 385, 532, 590),
          "STR_REVOLVER": (30, 945, 340, 1490),
          "STR_REVOLVER.paste": (30, 945, 340, 1490)}   # x0, y0, x1, y1: правка вклеивается только сюда


def region_paste(base, ans, rect, feather=4):
    """Ответ вклеивается в основу только внутри rect (край смягчён на feather пикселей внутрь). Печатает, что ответ
    менял вне rect: это и есть то, что вклейка отбросила."""
    import numpy as np
    a = np.asarray(Image.open(base).convert("RGB")).astype(np.float32)
    b = np.asarray(Image.open(ans).convert("RGB")).astype(np.float32)
    if a.shape != b.shape:
        raise SystemExit("размер ответа %s не равен основе %s - вклейка невозможна" % (b.shape, a.shape))
    x0, y0, x1, y1 = rect
    m = np.zeros(a.shape[:2], np.float32)
    m[y0:y1, x0:x1] = 1
    if feather:
        yy, xx = np.mgrid[0:a.shape[0], 0:a.shape[1]]
        dist = np.minimum.reduce([xx - x0, x1 - 1 - xx, yy - y0, y1 - 1 - yy]).astype(np.float32)
        m = np.where(m > 0, np.clip((dist + 1) / float(feather), 0, 1), 0)
    d = np.abs(a - b).max(2)
    out = m == 0
    print("  ответ вне области: средняя разница %.1f, больше 64 - %.4f пикселей (отброшено вклейкой)" % (
        d[out].mean(), (d[out] > 64).mean()))
    c = a * (1 - m[..., None]) + b * m[..., None]
    p = ans[:-4] + ".region.png"
    Image.fromarray(np.clip(np.round(c), 0, 255).astype(np.uint8), "RGB").save(p)
    dc = np.abs(c - a).max(2)
    print("  вклейка %s: вне области разница с основой %.1f (обязана быть 0)" % (p, dc[out].max()))
    return p


def edit(row, lrow, base, step=""):
    """Локальная правка готового ответа: картинка 1 - ответ, картинка 2 - оригинал (только геометрия).
    step - вторая и следующие правки того же предмета (ключ <тип>.<step> в EDIT_CHANGES)."""
    t = row["type"]
    key = t + ("." + step if step else "")
    if key not in EDIT_CHANGES:
        raise SystemExit("%s: правка не описана в EDIT_CHANGES" % key)
    if not os.path.exists(base):
        raise SystemExit("нет %s" % base)
    ch, keep = EDIT_CHANGES[key]
    head, bg = EDIT_HEAD.get(t, EDIT_HEAD["STR_COMBAT_SHOTGUN"])
    prompt = EDIT_PROMPT.format(head=head, bg=bg, changes=ch, keep=keep)
    with open(os.path.join(OUT, "inputs", key + ".edit.prompt.txt"), "w", encoding=ENC) as f:
        f.write(prompt)
    dst = call(row, [base, os.path.join(OUT, "inputs", t + ".in1_sprite.png")], prompt,
               "edit image 1 with your built-in image tool (image 2 is a reference input)")
    if dst and key in REGION:
        region_paste(base, dst, REGION[key])


def run(row, lrow, solo=False):
    t = row["type"]
    p1 = os.path.join(OUT, "inputs", t + ".in1_sprite.png")
    p2 = os.path.join(OUT, "inputs", t + ".in2_style.png")
    imgs = [p1] if solo else [p1, p2]
    with open(os.path.join(OUT, "inputs", t + (".solo" if solo else "") + ".prompt.txt"), encoding=ENC) as f:
        prompt = f.read()
    call(row, imgs, prompt)


def call(row, imgs, prompt, how="use your built-in image generation tool"):
    t = row["type"]
    n = 0
    while os.path.exists(os.path.join(OUT, "raw", "%s.cg%d.png" % (t, n))):
        n += 1
    dst = os.path.abspath(os.path.join(OUT, "raw", "%s.cg%d.png" % (t, n)))
    task = ("Exactly once, %s. Input images: %s. "
            "Prompt for the image tool:\n\n%s\n\nAfter generating, copy the generated PNG to %s and print that path. "
            "Do not edit the image yourself, do not run any other tools on it."
            % (how, ", ".join("image %d = %s" % (i + 1, q) for i, q in enumerate(imgs)), prompt, dst))
    before = set()
    for d, _s, fs in os.walk(GEN_DIR):
        before |= {os.path.join(d, f) for f in fs}
    t0 = time.time()
    log = os.path.join(OUT, "raw", "%s.cg%d.log" % (t, n))
    # задание - через stdin ("-"): codex.cmd на Windows режет аргумент на первом переводе строки, и cg0/cg1
    # ушли без промпта (05.10) - генератор рисовал по своей формулировке
    with open(log, "w", encoding="utf-8") as lf:
        pr = subprocess.run([shutil.which("codex") or "codex", "exec", "--skip-git-repo-check", "-s", "workspace-write",
                             "-c", "model_reasoning_effort=low"] + sum([["-i", q] for q in imgs], []) + ["-"],
                            cwd=ROOT, stdout=lf, stderr=subprocess.STDOUT, input=task.encode("utf-8"))
        rc = pr.returncode
    with open(log, encoding="utf-8", errors="replace") as lf:
        got = prompt.splitlines()[-1].strip()[:60] in lf.read()
    print("  промпт дошёл до codex целиком: %s" % ("да" if got else "НЕТ"))
    if not os.path.exists(dst):
        new = []
        for d, _s, fs in os.walk(GEN_DIR):
            new += [os.path.join(d, f) for f in fs if os.path.join(d, f) not in before]
        if new:
            shutil.copy(max(new, key=os.path.getmtime), dst)
    ok = os.path.exists(dst)
    print("%s %s код %d, %.0f с, ответ %s" % (row["master"], t, rc, time.time() - t0, dst if ok else "НЕТ (см. %s)" % log))
    if ok:
        im = Image.open(dst)
        print("  размер %dx%d, режим %s" % (im.width, im.height, im.mode))
    return dst if ok else None


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["prep", "run", "edit"])
    ap.add_argument("--only", required=True)
    ap.add_argument("--solo", action="store_true", help="без образца манеры, только спрайт")
    ap.add_argument("--base", default="", help="edit: готовый ответ, который правится")
    ap.add_argument("--step", default="", help="edit: следующая правка того же предмета, ключ <тип>.<step> (mag)")
    ap.add_argument("--v2", action="store_true", help="описание из describe/what_v2.tsv, папка weapons-chatgpt-v2")
    a = ap.parse_args()
    os.chdir(ROOT)
    if a.v2:
        global OUT
        OUT = OUT2
    for sub in ("inputs", "raw"):
        os.makedirs(os.path.join(OUT, sub), exist_ok=True)
    for row, lrow in rows_for(a.only):
        if a.cmd == "edit":
            edit(row, lrow, a.base, a.step)
        else:
            (prep if a.cmd == "prep" else run)(row, lrow, a.solo)


if __name__ == "__main__":
    main()
