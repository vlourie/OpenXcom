#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Полы группой одного материала: одна кладка на все кадры группы, мох и поросль - поверх неё.

Проба probe_floor.py рисовала каждый пол сам по себе, по размытому пятну цвета и описанию кадра, -
Vitali 27.09: «пол может быть в джунглях, на улице, на крыше - надо сравнивать с объектами на
карте, а не пиксели выпрямлять». Опознание по картам (floor_context.py) показало, что полы набора -
это ступени одного материала: MUJUNGLE_2 2 (булыжник храма), 13, 14, 15 - та же мостовая, всё
сильнее заросшая мхом, и сетка камней у них общая.

Способ:
  1. основа (--base): ромб оригинала развёрнут в квадрат вида сверху (probe_floor.unroll), слегка
     размыт (--sketch-sigma: форма камней остаётся, пиксели уходят), повторён 4x4; описание - по
     месту на картах (--what), а не по пикселям кадра;
  2. каждый кадр поверх (--over): эскиз - ОТВЕТ модели для основы, а где у оригинала кадра зелень -
     её цвет; модель рисует те же камни и тот же мох там, где он в оригинале. Сетка камней одна на
     всю группу - соседние кадры разных ступеней стыкуются швом в шов;
  3. клетка периода и тон - как в probe_floor (окно cos^2, низкие частоты из оригинала);
     варианты <N>.png, .v1..v3 (R-039) - отдельные заказы со своим зерном (--variants), иначе
     они почти одинаковы и на карте читается решётка; стиль - фотография материала, не рисунок
     (Vitali: «нужно больше фотореализма»);
  4. проверка - на картах (--maps): те же места со стенами и предметами, оригинал x4 | прежний
     пак | новое, плюс поле группы вперемешку (стык кадров друг с другом).

    tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\floor_group.py

Кладёт в art/floor_group/<имя>/. В пак НЕ идёт.
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

import gen_hd                                       # noqa: E402  (он же ставит HF_HOME)
import numpy as np                                  # noqa: E402
from PIL import Image                               # noqa: E402

import floor_context as fc                          # noqa: E402
import map_mockup as mm                             # noqa: E402
import probe_floor as pf                            # noqa: E402

K = pf.K
# Vitali 27.09 на первой пробе: «нужно больше фотореализма» - описание как у фотографии, рисунок в негатив
NEGATIVE = ("pixel art, pixelated, blocky, jagged stair-stepped edges, dithering, noise, blurry, smudged, "
            "painting, illustration, drawing, cartoon, stylized, game art, flat colours, plastic, cgi render, "
            "perspective, horizon, sky, side view, walls, tall objects, border, frame, vignette, "
            "grid lines, seams, text, watermark")
# описания - по месту на картах (art/floor_context/MUJUNGLE14/опознание.md), не по пикселям кадра
WHAT = ("old worn tan sandstone cobblestones paving the courtyard of an ancient ruined temple city in "
        "the jungle: rounded, roughly square hand-cut stones of slightly different sizes, about three "
        "stones across each square, set in narrow dark earthy joints, weathered chipped edges, a "
        "little grey grit, humid tropical climate")
PROMPT_BASE = (
    "<image1> is a soft colour map of a repeating floor texture seen from directly above, the same "
    "square tile repeated 4 x 4. It gives the layout of the stones and the colours, not the detail. "
    "Make a photorealistic seamless top-down photograph of real ground, a material scan texture: "
    "{what}. Keep every stone, board and patch where <image1> has it and keep the 4 x 4 repetition; "
    "everything else is real photographic detail: {detail}. Soft overcast daylight straight from "
    "above, no perspective, sharp focus. Fill the whole image edge to edge. No standing objects, "
    "no frame, no grid lines, no text.")
PROMPT_OVER = (
    "<image1> is a seamless top-down photograph of ground repeated 4 x 4: {what}. The soft green "
    "patches on it mark where moss grows. Make the same photograph again with the same stones in "
    "exactly the same places, and cover the green patches with {moss}. About {cover} percent of the "
    "floor is covered; where <image1> has no green, the stones stay bare. Keep the 4 x 4 "
    "repetition. Photorealistic material scan, real photographic detail, soft overcast daylight "
    "straight from above, no perspective, sharp focus. Fill the whole image edge to edge. No "
    "standing objects, no frame, no grid lines, no text.")
# "layout": "free" - земля под открытым небом (трава, гравий, песок): у оригинала в клетке мелкий
# повторяющийся узор пикселей, и способ «камень где камень» возвращал его чешуёй (Vitali 28.09:
# «полы вне зданий - пиксельное»). Эскиз - только средний цвет и мягкие пятна своего зерна
PROMPT_FREE = (
    "<image1> is only a soft colour guide for a ground texture seen from directly above: follow its "
    "average colours and its large soft light and dark areas, but not any small shapes. Make a "
    "photorealistic seamless top-down photograph of real ground, a material scan texture: {what}. "
    "Natural random detail with no repeating pattern: {detail}. Soft overcast daylight straight from "
    "above, no perspective, sharp focus. Fill the whole image edge to edge. No standing objects, no "
    "frame, no grid lines, no text.")
PROMPT_FREE_OVER = (
    "<image1> is a seamless top-down photograph of ground: {what}. The soft green patches on it mark "
    "where grass grows. Make the same photograph again with the same ground, and cover the green "
    "patches with {moss}. About {cover} percent of the ground is covered, in natural irregular "
    "clumps; where <image1> has no green, the ground stays bare. Photorealistic material scan, real "
    "photographic detail, soft overcast daylight straight from above, no perspective, sharp focus. "
    "Fill the whole image edge to edge. No standing objects, no frame, no grid lines, no text.")
DETAIL = ("natural stone grain, pores, cracks, chips, worn tops, dust and grit in the joints, "
          "subtle natural colour variation")
MOSS = ("real living cushion moss as in a macro photograph: dense tiny green fronds, darker and damp "
        "in the joints, lighter where it catches the light, a few small leafy seedlings")


def green_mask(ref, sigma):
    """Где у оригинала зелень: G заметно выше R и B. Мягкая маска 0..1, периодическая."""
    g = ref[..., 1] - np.maximum(ref[..., 0], ref[..., 2])
    m = np.clip((g - 6.0) / 18.0, 0, 1)[..., None]
    return np.clip(pf.blur_wrap(m, sigma)[..., 0], 0, 1)


def soft_noise(size, sigma, seed):
    """Периодические мягкие пятна: нормальный шум, размытый по кругу, приведён к -1..1."""
    rng = np.random.default_rng(seed)
    n = pf.blur_wrap(rng.standard_normal((size, size, 1)), sigma)[..., 0]
    return n / (np.abs(n).max() + 1e-6)


def free_sketch(ref, p, seed):
    """Эскиз свободной земли: цвет оригинала без узора (размыт на шестую клетки) плюс свои пятна."""
    base = pf.blur_wrap(ref, p / 6.0)
    return np.clip(base + 14.0 * soft_noise(p, p / 10.0, seed)[..., None], 0, 255)


def free_mask(ref, p, seed):
    """Где трава в свободном режиме: доля - как у оригинала, пятна - свои, неправильные."""
    cover = float(green_mask(ref, 4.0).mean())
    n = soft_noise(p, p / 16.0, seed) + 0.35 * soft_noise(p, p / 40.0, seed + 1)
    th = np.quantile(n, 1.0 - cover) if cover > 0 else n.max() + 1
    m = (n > th).astype(np.float32)[..., None]
    return np.clip(pf.blur_wrap(m, 3.0)[..., 0], 0, 1), cover


def periodic_seam(img, p, cx, cy, band):
    """Клетка p x p без смешивания всей площади: берётся кусок ответа (p+band)^2, и только полоса
    band у краёв сводится с продолжением рисунка за краем. pf.periodic складывает четыре места
    ответа окном cos^2 - годится, пока ответ повторяет эскиз 4x4; у свободной земли ответ не
    повторяется, и пучки травы двоились в мутные пятна (28.09)."""
    y0, x0 = cy - p // 2, cx - p // 2
    blk = img[y0:y0 + p + band, x0:x0 + p + band].astype(np.float32)
    w = 0.5 - 0.5 * np.cos(np.pi * (np.arange(band) + 0.5) / band)      # 0 -> 1
    top = blk[:band] * w[:, None, None] + blk[p:p + band] * (1 - w)[:, None, None]
    blk = np.concatenate([top, blk[band:p]], 0)
    left = blk[:, :band] * w[None, :, None] + blk[:, p:p + band] * (1 - w)[None, :, None]
    out = np.concatenate([left, blk[:, band:p]], 1)
    return np.roll(out, (y0 % p, x0 % p), axis=(0, 1))


def parse_key(text):
    s, f = text.split(":")
    return s.upper(), int(f)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", default="temple_cobbles")
    ap.add_argument("--base", default="MUJUNGLE_2:2")
    ap.add_argument("--over", default="MUJUNGLE_2:13,MUJUNGLE_2:14,MUJUNGLE_2:15")
    ap.add_argument("--what", default=WHAT)
    ap.add_argument("--moss", default=MOSS)
    ap.add_argument("--maps", default="CATACOMBS_JUNGLE_2/CATACOMBS_34,CITY_OF_THE_DEAD/DEATHCITY01",
                    help="террейн/карта через запятую - проверка на месте")
    ap.add_argument("--out", default="art/floor_group")
    ap.add_argument("--period", type=int, default=256)
    ap.add_argument("--variants", type=int, default=4, help="вариантов клетки (<N>.png, .v1..): заказ на каждый")
    ap.add_argument("--sketch-sigma", type=float, default=10.0,
                    help="размытие эскиза основы, пикс. квадрата (~11 на пиксель оригинала)")
    ap.add_argument("--sigma", type=float, default=24.0, help="тон: низкие частоты из оригинала")
    ap.add_argument("--seed", type=int, default=2712)
    ap.add_argument("--steps", type=int, default=40)
    ap.add_argument("--cfg", type=float, default=4.0)
    ap.add_argument("--mp", type=float, default=1.0)
    ap.add_argument("--model", default="")
    ap.add_argument("--models", default=gen_hd.DEFAULT_MODELS_DIR)
    ap.add_argument("--offload", default="model", choices=["model", "seq", "none"])
    ap.add_argument("--recut", action="store_true", help="без видеокарты: из готовых *_1hd.png")
    ap.add_argument("--groups", default="", help="json-список групп {name, base, over, what, detail, moss, maps}")
    ap.add_argument("--only", default="", help="только эти группы из --groups, через запятую")
    args = ap.parse_args()

    world = mm.World()
    p = args.period
    side = p * pf.N_REP

    painter = None

    def paint(prompt, sketch, seed, path):
        nonlocal painter
        if os.path.exists(path):                    # готовый ответ не заказывать заново
            return Image.open(path).convert("RGB")
        if args.recut:
            raise SystemExit("нет %s, а --recut" % path)
        if painter is None:
            import gen_fire
            ns = argparse.Namespace(models=args.models, qwen21_model=args.model, qwen21_steps=args.steps,
                                    qwen21_cfg=args.cfg, qwen21_mp=args.mp, qwen21_strength=0.0,
                                    qwen21_offload=args.offload, qwen21_thrifty=False,
                                    qwen21_ref="", qwen21_ref_mp=1.0, qwen21_prompt="strict",
                                    qwen21_hint="off", qwen21_ref_order="ref-first")
            painter = gen_hd.Qwen21Painter(ns, {"ground": ("", "")})
            gen_fire.NEGATIVE = NEGATIVE
        import gen_fire
        hd = gen_fire.run_pass(painter, args, prompt, sketch, seed).convert("RGB")
        gen_hd.save_png(hd, path)
        return hd

    def run_group(g):
        what, moss = g.get("what", args.what), g.get("moss", args.moss)
        detail = g.get("detail", DETAIL)
        free = g.get("layout") == "free"
        base = parse_key(g["base"])
        overs = [parse_key(t) for t in g.get("over", "").split(",") if t.strip()]
        out_dir = os.path.join(args.out, g["name"])
        os.makedirs(out_dir, exist_ok=True)
        print("=== группа %s: %s%s" % (g["name"], g["base"], (" + " + g["over"]) if overs else ""), flush=True)
        t0 = time.time()
        keys = [base] + overs
        texs = {}
        base_arrs = []                                  # ответ основы на каждый вариант
        base_shift = []                                 # свободная земля: поправка тона основы j
        total = len(keys) * args.variants
        done = 0
        for n, (s, f) in enumerate(keys):
            spr = world.sprite(s, f, None)
            ref = pf.unroll(spr, p)
            var = []
            # варианты - отдельные заказы со своим зерном: клетки из одного ответа 4x4 выходили почти
            # одинаковыми, и на карте читалась решётка (первая проба 27.09); мох j-го - поверх основы j
            for j in range(args.variants):
                if n == 0:
                    soft = free_sketch(ref, p, args.seed + 100 * j) if free else pf.blur_wrap(ref, args.sketch_sigma)
                    sketch = Image.fromarray(np.tile(soft, (pf.N_REP, pf.N_REP, 1)).clip(0, 255).astype(np.uint8), "RGB")
                    prompt = (PROMPT_FREE if free else PROMPT_BASE).replace("{what}", what).replace("{detail}", detail)
                    cover = 0
                else:
                    if free:                            # доля травы - оригинала, пятна - свои, цвет - средний зелёный
                        m, c = free_mask(ref, p, args.seed + 100 * j + n)
                        cover = int(round(100 * c))
                        g_m = green_mask(ref, 1.0)[..., None]
                        moss_col = np.broadcast_to((ref * g_m).sum((0, 1)) / (g_m.sum() + 1e-6), ref.shape)
                    else:
                        m = green_mask(ref, 4.0)
                        cover = int(round(100 * m.mean()))
                        moss_col = pf.blur_wrap(ref, 3.0)
                    mt = np.tile(m, (pf.N_REP, pf.N_REP))[..., None]
                    ct = np.tile(moss_col, (pf.N_REP, pf.N_REP, 1))
                    sk = base_arrs[j] * (1 - mt) + ct * mt
                    sketch = Image.fromarray(sk.clip(0, 255).astype(np.uint8), "RGB")
                    prompt = ((PROMPT_FREE_OVER if free else PROMPT_OVER).replace("{what}", what)
                              .replace("{moss}", moss).replace("{cover}", str(max(5, cover))))
                if j == 0:
                    gen_hd.save_png(sketch, os.path.join(out_dir, "%s_%d_sketch.png" % (s, f)))
                done += 1
                print("[%d/%d] %s %d вариант %d%s" % (done, total, s, f, j, "" if n == 0 else " - мох %d%%" % cover),
                      flush=True)
                hd = paint(prompt, sketch, args.seed + 100 * j + n,
                           os.path.join(out_dir, "%s_%d_v%d_1hd.png" % (s, f, j)))
                arr = np.asarray(hd.resize((side, side), Image.LANCZOS)).astype(np.float32)
                if n == 0:
                    base_arrs.append(arr)
                if not free:
                    per = pf.periodic(arr, p, int(1.5 * p), int(1.5 * p))
                    var.append(pf.tone_low(per, ref, args.sigma))
                elif n == 0:
                    # свободная земля: от оригинала только общий тон, иначе его узор вернётся пятнами
                    per = periodic_seam(arr, p, int(1.5 * p), int(1.5 * p), p // 8)
                    var.append(pf.tone_low(per, ref, p / 6.0))
                    base_shift.append(var[-1] - per)
                else:
                    # поросль - та же поправка тона, что у основы j: гравий под травой = голый гравий
                    per = periodic_seam(arr, p, int(1.5 * p), int(1.5 * p), p // 8)
                    var.append(np.clip(per + base_shift[j], 0, 255))
                el = time.time() - t0
                print("  %s, осталось ~%s" % (gen_hd.human_time(el), gen_hd.human_time(el / done * (total - done))),
                      flush=True)
            texs[(s, f)] = var
            d = os.path.join(out_dir, s + ".PCK")
            os.makedirs(d, exist_ok=True)
            cells = [pf.cell(spr, tx) for tx in var]
            for j, c in enumerate(cells):
                gen_hd.save_png(c, os.path.join(d, "%d.png" % f if j == 0 else "%d.v%d.png" % (f, j)))

        # --- лист кадров: поле 5x5, оригинал | прежний пак | новое
        rows = []
        for s, f in keys:
            spr = world.sprite(s, f, None)
            x4 = spr.resize((spr.width * K, spr.height * K), Image.NEAREST)
            old = pf.load_png(os.path.join(pf.MOD_TERRAIN, s + ".PCK", "%d.png" % f))
            order = pf.engine_order(texs[(s, f)])
            row = [pf.label(pf.field_sheet(spr, lambda gx, gy: x4), "%s %d orig x4" % (s, f))]
            if old is not None:
                row.append(pf.label(pf.field_sheet(spr, lambda gx, gy: old), "old pack"))
            row.append(pf.label(pf.field_sheet(spr, lambda gx, gy, o=order: pf.cell_at(spr, o, gx, gy)), "new"))
            rows.append(row)
        gen_hd.save_png(pf.board(rows), os.path.join(out_dir, "sheet_frames.png"))

        # --- поле группы вперемешку: стык разных кадров друг с другом
        n = 7
        orders = {k: pf.engine_order(texs[k]) for k in keys}
        sprs = {k: world.sprite(k[0], k[1], None) for k in keys}

        def pick(gx, gy):
            lev = pf.ground_level(np.array([[gx + 0.5]]), np.array([[gy + 0.5]]), len(keys), seed=3, scale=2.0)
            return keys[int(round(float(lev[0, 0])))]

        mix_new = pf.field_sheet(sprs[base], lambda gx, gy: pf.cell_at(sprs[pick(gx, gy)], orders[pick(gx, gy)], gx, gy), n)
        mix_orig = pf.field_sheet(sprs[base], lambda gx, gy: sprs[pick(gx, gy)].resize((32 * K, 40 * K), Image.NEAREST), n)
        gen_hd.save_png(pf.board([[pf.label(mix_orig, "group mixed: orig x4"), pf.label(mix_new, "new")]]),
                        os.path.join(out_dir, "sheet_mixed.png"))

        # --- на картах: оригинал x4 | прежний пак | новое, со стенами и предметами
        boards = []
        for tb in [t for t in g.get("maps", args.maps).split(",") if t.strip()]:
            t, b = tb.split("/")
            try:
                _dims, cells = fc.cell_keys(world, t, b)
            except SystemExit as e:
                print("карта %s: %s" % (tb, e), flush=True)
                continue
            where = [(x, y, z) for (x, y, z), kk in cells.items() if kk[0] in texs]
            if not where:
                print("карта %s: полов группы нет" % tb, flush=True)
                continue
            zs = {}
            for x, y, z in where:
                zs[z] = zs.get(z, 0) + 1
            z = max(zs, key=zs.get)
            pts = [(x, y) for x, y, zz in where if zz == z]
            mx = sum(x for x, _y in pts) / len(pts)
            my = sum(y for _x, y in pts) / len(pts)
            _sx, sy, sz, _c = mm.read_block(world, b)
            cx = (sy * 16 + (mx - my) * 16 + 16) * K
            cy = (sz * 24 + 8 + (mx + my) * 8 - z * 24 + 32) * K
            box = (int(cx - 800), int(cy - 480), int(cx + 800), int(cy + 480))
            ims = []
            im, _m = mm.render(world, t, b, None, K, None, maxz=z)
            ims.append(("orig x4", im))
            im, _m = mm.render(world, t, b, pf.MOD_TERRAIN, K, None, maxz=z)
            ims.append(("old pack", im))
            # новое: прежний пак, а полы группы - свои (с вариантами)
            for (s, f) in keys:
                vs = texs[(s, f)]
                world.hd[(pf.MOD_TERRAIN, s, f)] = pf.cell(sprs[(s, f)], vs[0])
                for j in range(1, len(vs)):
                    world.hd[(pf.MOD_TERRAIN, s, f, j)] = pf.cell(sprs[(s, f)], vs[j])
                world.hd[(pf.MOD_TERRAIN, s, f, len(vs))] = None
            im, _m = mm.render(world, t, b, pf.MOD_TERRAIN, K, None, maxz=z)
            ims.append(("new", im))
            for (s, f) in keys:                         # вернуть кэш - следующей карте прежний пак
                for kk in [k for k in world.hd if k[:3] == (pf.MOD_TERRAIN, s, f)]:
                    del world.hd[kk]
            boards.append([pf.label(i.crop(box), "%s z%d - %s" % (b, z, name)) for name, i in ims])
            print("карта %s: полов группы %d, этаж %d" % (tb, len(where), z), flush=True)
        if boards:
            gen_hd.save_png(pf.board(boards), os.path.join(out_dir, "sheet_maps.png"))
        print("ЛИСТ %s" % os.path.join(out_dir, "sheet_maps.png"), flush=True)
        print("готово за %s" % gen_hd.human_time(time.time() - t0), flush=True)

    if args.groups:
        with open(args.groups, encoding="utf-8-sig") as f:
            groups = [g for g in json.load(f) if not g.get("_skip")]
    else:
        groups = [{"name": args.name, "base": args.base, "over": args.over, "maps": args.maps}]
    if args.only:
        groups = [g for g in groups if g["name"] in args.only.split(",")]
    for g in groups:
        run_group(g)


if __name__ == "__main__":
    main()
