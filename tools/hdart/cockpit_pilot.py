#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Пилот «салон за стеклом кабины» (просьба игроков 20.10, слово Vitali «делай всё»).

За стеклом кабины корабля в кадре ничего нет: нос и капот - один кадр-объект, клетки салона стоят позади
(glass_probe_map.py), поэтому прозрачность glass_alpha покажет землю под кораблём - дыру. Здесь стекло
остаётся непрозрачным, а салон дорисовывает Qwen-Image-Edit-2511: вырез вокруг стекла из HD-кадра игры на
серой подложке, ракурс и свет - battle_view.prompt_block("object"); в кадр возвращается ТОЛЬКО область
стекла (glass_alpha.object_mask), поверх - блик прежнего стекла. Корпус и альфа кадра не меняются.

В пак НЕ идёт: art/_review/glass/cockpit/<НАБОР>_<кадр>_sheet.png (было | варианты) и
<НАБОР>.PCK/<кадр>_s<зерно>.png - показать Vitali (память «Арт - сначала показать»).

    py -3 tools/gpuq.py add --name cockpit-pilot -- E:/OpenXCom/tools/hdart/.venv/Scripts/python.exe E:/OpenXCom/tools/hdart/cockpit_pilot.py --frames KITSUNE:7
"""
import argparse
import os
import sys
import time

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import battle_view  # noqa: E402
import glass_alpha as ga  # noqa: E402
import photo_ui  # noqa: E402

OUT = os.path.join(ga.REVIEW, "cockpit")
PANEL = (96, 96, 102)
PAD = 18
# сколько от прежнего стекла остаётся поверх салона: тон стекла и блики
TINT = 0.3
TINT_HL = 0.6

ASK = (
    "Edit only the bluish glass window of the craft in <image1>. Make it clear, slightly blue tinted glass "
    "that you can see through: behind it is the small cockpit inside the craft - a padded pilot seat, an "
    "instrument panel with tiny glowing screens and lights, a control stick, all small and seen from above "
    "through the glass at the same angle as the hull. The cockpit is empty, no person. Keep everything "
    "outside the window exactly as it is: the hull, its shape, panels, colours and the plain grey "
    "background. %s")
NEG = "opaque blue screen, flat painted glass, mirror, person, pilot, face, text, letters, frame, %s"


def crop_box(mask, w, h):
    ys, xs = np.nonzero(mask)
    return (max(0, xs.min() - PAD), max(0, ys.min() - PAD), min(w, xs.max() + 1 + PAD), min(h, ys.max() + 1 + PAD))


def install(picks, approval, yes):
    """НАБОР:кадр=зерно -> выбранный вариант в пак через манифест (обе копии). Модель не грузит. Кадр пака
    с пилота не должен был измениться: вне стекла вариант обязан совпасть с ним пиксель в пиксель."""
    import hashlib
    import io
    import build_hd_pack as bp
    man = bp.load()
    staged = []
    for pick in picks:
        key, _, seed = pick.partition("=")
        s, f = key.rsplit(":", 1)
        s = s.upper()
        rel = "TERRAIN/%s.PCK/%s.png" % (s, f)
        cur = np.array(Image.open(os.path.join(ga.GAME, rel)).convert("RGBA"))
        new = np.array(Image.open(os.path.join(OUT, s + ".PCK", "%s_s%s.png" % (f, seed))).convert("RGBA"))
        g, _lum = ga.object_mask(cur)
        if cur.shape != new.shape or (cur[~g] != new[~g]).any() or (cur[..., 3] != new[..., 3]).any():
            raise SystemExit("%s: кадр пака изменился после пилота - перегенерировать" % key)
        buf = io.BytesIO()
        Image.fromarray(new, "RGBA").save(buf, "PNG", optimize=True)
        staged.append((rel, buf.getvalue(), key, seed, int(g.sum())))
    print("кадров к записи:", len(staged))
    if not yes:
        raise SystemExit("сухой прогон; --yes - записать")
    rels = []
    for rel, data, key, seed, n in staged:
        entry = man["files"].get(rel)
        old = entry.get("sha256") if entry else None
        bp.stage(man, rel, data, generator="cockpit_pilot", generator_version="cockpit_pilot.py 20.10 v1",
                 source_path=None, approved=True, approval=approval, derived_from=old, source_frame=key,
                 note="салон за стеклом кабины: зерно %s, %d пикселей стекла" % (seed, n))
        if old:
            man["files"][rel]["replaced"] = old
        rels.append(rel)
    bp.save(man, why="cockpit_pilot: %d кадров кабин" % len(rels))
    print("game:", bp.install(man, "game", only=rels))
    print("repo:", bp.install(man, "repo", only=rels))
    bad = 0
    for r in rels:
        for root in (bp.TARGETS["game"], bp.TARGETS["repo"]):
            p = os.path.join(root, r)
            if not os.path.exists(p) or hashlib.sha256(open(p, "rb").read()).hexdigest() != man["files"][r]["sha256"]:
                print("РАСХОДИТСЯ", root, r)
                bad += 1
    print("сверка копий:", "OK" if not bad else "РАСХОДИТСЯ %d" % bad)
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", nargs="+", help="НАБОР:кадр[@с-по] - строки кадра со стеклом")
    ap.add_argument("--install", nargs="+", help="НАБОР:кадр=зерно - выбранный Vitali вариант в пак")
    ap.add_argument("--approval", default="Vitali 20.10: «s7302 Идеально»")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--seeds", type=int, default=4)
    ap.add_argument("--seed", type=int, default=7301)
    ap.add_argument("--steps", type=int, default=8)
    ap.add_argument("--mp", type=float, default=0.6)
    ap.add_argument("--models", default=os.environ.get("HD_MODELS", "E:\\models"))
    a = ap.parse_args()
    os.chdir(ga.ROOT)
    sys.stdout.reconfigure(encoding="utf-8")
    if a.install:
        return install(a.install, a.approval, a.yes)
    if not a.frames:
        ap.error("--frames или --install")
    view =battle_view.prompt_block("object")
    prompt, neg = ASK % view["positive"], NEG % view["negative"]
    painter = None
    for spec in a.frames:
        key, _, rows = spec.partition("@")
        s, f = key.rsplit(":", 1)
        rows = tuple(int(v) for v in rows.split("-")) if rows else None
        src = os.path.join(ga.GAME, "TERRAIN", s.upper() + ".PCK", "%s.png" % f)
        hd = np.array(Image.open(src).convert("RGBA"))
        g, lum = ga.object_mask(hd, rows)
        if not g.any():
            print(key, "стекла нет - пропуск", flush=True)
            continue
        h, w = g.shape
        x0, y0, x1, y1 = crop_box(g, w, h)
        bg = np.zeros_like(hd)
        bg[..., :3] = PANEL
        bg[..., 3] = 255
        flat = Image.alpha_composite(Image.fromarray(bg), Image.fromarray(hd)).convert("RGB").crop((x0, y0, x1, y1))
        W, H = photo_ui.target_size(x1 - x0, y1 - y0, a.mp)
        odir = os.path.join(OUT, s.upper() + ".PCK")
        os.makedirs(odir, exist_ok=True)
        med = np.median(lum[g])
        keep = np.where(lum > med + ga.BRIGHT, TINT_HL, TINT)[..., None]
        tiles = [("before", hd)]  # шрифт PIL по умолчанию без кириллицы
        for seed in range(a.seed, a.seed + a.seeds):
            if painter is None:
                painter = photo_ui.Painter(a.models, True, a.steps, photoreal=False)
            t0 = time.time()
            rgb = painter.edit([flat.resize((W, H), Image.LANCZOS)], prompt, neg, seed, a.steps, 1.0, W, H)
            gen = np.array(Image.fromarray(rgb).resize((x1 - x0, y1 - y0), Image.LANCZOS)).astype(np.float32)
            out = hd.copy()
            reg = out[y0:y1, x0:x1, :3].astype(np.float32)
            gm = g[y0:y1, x0:x1]
            mix = gen * (1 - keep[y0:y1, x0:x1]) + reg * keep[y0:y1, x0:x1]
            reg[gm] = mix[gm]
            out[y0:y1, x0:x1, :3] = np.clip(np.round(reg), 0, 255).astype(np.uint8)
            Image.fromarray(out, "RGBA").save(os.path.join(odir, "%s_s%d.png" % (f, seed)))
            tiles.append(("s%d" % seed, out))
            print("%s зерно %d: %.0f с" % (key, seed, time.time() - t0), flush=True)
        z = 3
        sheet = Image.new("RGB", (len(tiles) * (w * z + 6), h * z + 22), (16, 16, 16))
        d = ImageDraw.Draw(sheet)
        for i, (name, im) in enumerate(tiles):
            x = i * (w * z + 6)
            tile = Image.fromarray(ga.over(im, ga.checker(w, h))).resize((w * z, h * z), Image.NEAREST)
            sheet.paste(tile, (x, 20))
            d.text((x + 4, 4), name, fill=(230, 230, 230))
        p = os.path.join(OUT, "%s_%s_sheet.png" % (s.upper(), f))
        sheet.save(p)
        print("лист:", p, flush=True)


if __name__ == "__main__":
    sys.exit(main())
