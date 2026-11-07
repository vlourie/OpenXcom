"""Земля с рельефом: рисуется в экранном виде (камера боя сверху под углом), а не разверткой сверху.

Прежний путь (floor_group) рисовал квадрат-развертку вида строго сверху и сжимал его в ромб: трава
выходила плоской фактурой, у кустика нет ни высоты, ни тени (Vitali 28.09: «не может быть, чтобы ты
рельеф не понимал»). Здесь модель видит поле ромбов так, как его видит игрок: кустик торчит вверх
по экрану, тень под ним. Экран и развертка клетки связаны аффинно (probe_floor.uv_to_screen), поэтому
ответ разворачивается обратно в квадрат клетки, сшивается по краю (floor_group.periodic_seam) и
режется в ромб кадра (probe_floor.cell) - вид на карте тот же, что в ответе.

Модель - Qwen-Image-Edit-2511 (photo_ui.Painter), стили:
  paint - рисованная игровая земля с объёмом и светотенью (образец Vitali - Graveyard Keeper);
  photo - фотография с LoRA Anime-to-Photoreal.
Поросль поверх основы (over) - та же картинка основы, куда в пятна доливается трава.

Запуск только через очередь (tools/gpuq.py), интерпретатор tools/hdart/.venv.
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
from PIL import Image                               # noqa: E402

import gen_hd                                       # noqa: E402
import map_mockup as mm                             # noqa: E402
import probe_floor as pf                            # noqa: E402
import floor_group as fg                            # noqa: E402

SIDE = 1024                                         # экранная картинка модели, ~1 Мп
S = 8                                               # пикселей ответа на пиксель кадра k=1 (ромб 256x128)

STYLE = {
    "paint": dict(lora=0.0, text=(
        "Repaint the whole of <image1> as a detailed hand-painted ground texture for a 2D top-down "
        "adventure game, rich painterly game art like Graveyard Keeper or Stardew Valley but painted at "
        "high resolution, with no pixel stairs: {what}. " + "{view}" + "The ground has real relief and "
        "volume: {detail}. Light comes from the upper left: every raised thing has a bright lit top edge "
        "and a soft dark shadow at its lower right base, so the surface reads as bumpy and three-dimensional. "
        "Warm natural colours with strong but soft light and shade. Keep the overall colours and "
        "brightness of <image1>. "
        "Fill the whole image edge to edge, evenly, with the same kind of ground everywhere. "
        "No objects, no buildings, no fences, no paths, no people, no frame, no text."),
        neg=("perspective, vanishing point, rows, planted rows, crop field, "
             "pixel art, pixelated, blocky, jagged stair-stepped edges, dithering, flat texture, flat "
             "lighting, blurry, smudged, horizon, sky, side view, depth of field, bokeh, vignette, border, "
             "frame, grid lines, seams, tiles, text, watermark, photograph")),
    "photo": dict(lora=1.0, text=(
        "Turn the whole of <image1> into a real sharp photograph of {what}. " + "{view}" + "Real relief and "
        "volume: {detail}. Late afternoon sunlight from the upper left: everything that stands up casts a "
        "small crisp shadow to the lower right, so the ground reads three-dimensional. Everything in sharp "
        "focus from edge to edge. Keep the overall colours and brightness of <image1>. "
        "Fill the whole image edge to edge, evenly, with the same "
        "kind of ground everywhere. No objects, no buildings, no fences, no paths, no people, no frame, "
        "no text."),
        neg=("perspective, vanishing point, rows, planted rows, crop field, "
             "anime, cartoon, illustration, drawing, painting, pixel art, pixelated, dithering, flat "
             "texture, blurry, depth of field, bokeh, tilt shift, horizon, sky, side view, vignette, border, "
             "frame, grid lines, seams, tiles, text, watermark")),
}
# вид: орто, без перспективы; разметка <image1> - где стоит каждая вещь
VIEW = ("Orthographic isometric view from above, exactly like a classic isometric strategy game: no "
        "perspective, no vanishing point, no horizon, everything is the same size at the top and at the "
        "bottom of the image. <image1> marks where every {thing} is: each small light blob with a dark "
        "shadow under it in <image1> becomes exactly one {thing} at that place and of that size. They are "
        "scattered at random, never in rows or lines. ")
OVER = (
    "Keep <image1> exactly as it is everywhere, the same ground in the same style and light, except in "
    "the flat green patches: there {moss}, growing out of the ground with real volume, lit tops and "
    "dark shadows at the base, soft ragged edges where it thins out into the ground around it. The green "
    "patches cover about {cover} percent of the image; outside them nothing changes.")


def screen_uv(shape):
    """Точки экранной картинки -> (u, v) в клетках, центр картинки = середина окна 3x3 клеток."""
    h, w = shape
    X, Y = np.meshgrid(np.arange(w) + 0.5 - w / 2, np.arange(h) + 0.5 - h / 2)
    sx, sy = X / S, Y / S                           # пиксели кадра k=1 от центра
    return sx / 32.0 + sy / 16.0 + 1.5, -sx / 32.0 + sy / 16.0 + 1.5


def to_screen(tex_uv, p):
    """Периодический квадрат клетки -> экранная картинка SIDE x SIDE (поле ромбов)."""
    u, v = screen_uv((SIDE, SIDE))
    return pf.bilinear(tex_uv, (u % 1.0) * p, (v % 1.0) * p, wrap=True)


def to_uv(scr, p, off=(0, 0)):
    """Экранный ответ -> квадрат 3p x 3p развертки (окно 3x3 клеток вокруг центра + off, пикс. ответа)."""
    a = (np.arange(3 * p) + 0.5) / p
    u, v = np.meshgrid(a, a)
    du, dv = u - 1.5, v - 1.5
    X = SIDE / 2 + off[0] + (du - dv) * 16 * S
    Y = SIDE / 2 + off[1] + (du + dv) * 8 * S
    return pf.bilinear(scr, X, Y, wrap=False)


def regions(per):
    """Центры окон 3x3 клеток в одном ответе: окно - ромб 96S x 48S, окна не перекрываются."""
    if per == 1:
        return [(0, 0)]
    d = 48 * S                                      # полширины окна по x
    return [(-d, -d), (d, -d), (-d, d), (d, d)][:per]


def blob_sketch(cols, seed, per_tile, radius, base=None, mask=None, shadow=0.45):
    """Разметка: где стоит каждая вещь (кустик, камень) - светлое пятно с тенью справа-снизу, в случайных
    местах, одного масштаба по всей картинке. Без неё модель сажала траву рядами и рисовала перспективу
    (проба #224, 28.09). Цвет пятна - случайный пиксель оригинала: пестрота гравия - его."""
    rng = np.random.default_rng(seed)
    img =(np.broadcast_to(cols.mean(0), (SIDE, SIDE, 3)) if base is None else base).astype(np.float32).copy()
    tile_px = 32 * S * 16 * S / 2.0                 # площадь ромба клетки в пикселях ответа
    n = int(per_tile * SIDE * SIDE / tile_px)
    yy, xx = np.mgrid[0:SIDE, 0:SIDE]
    r0 = radius * S
    for _ in range(n):
        x, y = rng.uniform(0, SIDE, 2)
        if mask is not None and mask[int(y), int(x)] < 0.5:
            continue
        r = r0 * rng.uniform(0.6, 1.3)
        c = cols[rng.integers(len(cols))]
        x0, x1, y0, y1 = int(max(0, x - 2 * r)), int(min(SIDE, x + 2 * r)), int(max(0, y - 2 * r)), int(min(SIDE, y + 2 * r))
        X, Y = xx[y0:y1, x0:x1], yy[y0:y1, x0:x1]
        sh = np.clip(1 - (((X - x - 0.35 * r) / (1.1 * r)) ** 2 + ((Y - y - 0.45 * r) / (0.6 * r)) ** 2), 0, 1)
        img[y0:y1, x0:x1] *= (1 - shadow * sh)[..., None]
        body = np.clip(1.5 * (1 - (((X - x) / r) ** 2 + ((Y - y) / (0.8 * r)) ** 2)), 0, 1)[..., None]
        lit = np.clip(1 - (Y - (y - 0.5 * r)) / (1.3 * r), 0.7, 1.25)[..., None]
        img[y0:y1, x0:x1] = img[y0:y1, x0:x1] * (1 - body) + np.clip(c * lit, 0, 255) * body
    return img


def mix_over(grass, ground, ref, p, g, seed, n_var):
    """Поросль без модели: готовая трава поверх готовой основы по мелкой маске с долей зелени оригинала.
    Модель на OVER заливала клетку сплошной тёмной травой, темнее кадра 0, и кадры 1-2, стоящие на карте
    шахматкой, читались блоками (#226, 28.09). Здесь тон травы и основы - те же, что у соседних кадров."""
    cover = float(fg.green_mask(ref, 4.0).mean())
    grain = p / float(g.get("mix_grain", 14))
    out = []
    for j in range(n_var):
        rng = np.random.default_rng(seed + j)
        nz = pf.blur_wrap(rng.standard_normal((p, p, 1)), grain)[..., 0]
        nz += 0.4 * pf.blur_wrap(rng.standard_normal((p, p, 1)), grain / 3.0)[..., 0]
        th = np.quantile(nz, 1.0 - cover)
        gr = grass[j % len(grass)]
        lum = gr.mean(-1)
        # край пятна рваный: светлые стебли выходят на гравий, тёмные ямки уходят под него
        m = np.clip((nz - th) / (0.12 * nz.std()) + 0.5 + 0.9 * (lum - lum.mean()) / (lum.std() + 1e-3), 0, 1)
        d = max(2, p // 64)                         # тень травы вниз по экрану = +u и +v
        sh = np.clip(np.roll(m, (d, d), axis=(0, 1)) - m, 0, 1)
        base = ground[j % len(ground)] * (1 - 0.35 * sh)[..., None]
        out.append(np.clip(base * (1 - m[..., None]) + gr * m[..., None], 0, 255))
    return out, cover


def screen_noise(seed, sigma):
    rng = np.random.default_rng(seed)
    n = pf.blur_wrap(rng.standard_normal((SIDE, SIDE, 1)), sigma)[..., 0]
    return n / (np.abs(n).max() + 1e-6)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--groups", required=True, help="json: [{name, base, over, what, detail, moss}]")
    ap.add_argument("--styles", default="paint,photo")
    ap.add_argument("--out", default="art/floor_group")
    ap.add_argument("--prefix", default="relief_", help="папка группы: <out>/<prefix><стиль>_<name>")
    ap.add_argument("--period", type=int, default=256)
    ap.add_argument("--variants", type=int, default=2)
    ap.add_argument("--scale", type=int, default=8, help="пикселей ответа на пиксель кадра k=1 (4 = ровно HD x4)")
    ap.add_argument("--per-image", type=int, default=1, help="вариантов из одного ответа (разные окна), до 4 при --scale 4")
    ap.add_argument("--seed", type=int, default=2809)
    ap.add_argument("--steps", type=int, default=40)
    ap.add_argument("--cfg", type=float, default=4.0)
    ap.add_argument("--models", default=os.environ.get("HD_MODELS", "E:\\models"))
    ap.add_argument("--recut", action="store_true", help="без видеокарты: из готовых *_screen.png")
    args = ap.parse_args()

    with open(args.groups, encoding="utf-8-sig") as f:
        groups = [g for g in json.load(f) if not g.get("_skip")]
    styles = [s for s in args.styles.split(",") if s]
    world = mm.World()
    p = args.period
    painter = None

    def paint(img, prompt, neg, seed, lora, path):
        nonlocal painter
        if os.path.exists(path):                    # готовый ответ не заказывать заново
            return np.asarray(Image.open(path).convert("RGB").resize((SIDE, SIDE), Image.LANCZOS)).astype(np.float32)
        if args.recut:
            raise SystemExit("нет %s, а --recut" % path)
        if painter is None:
            import photo_ui as pu
            painter = pu.Painter(args.models, fast=False, steps=args.steps, photoreal=True)
        src = Image.fromarray(img.clip(0, 255).astype(np.uint8), "RGB")
        out = painter.edit([src], prompt, neg, seed, args.steps, args.cfg, SIDE, SIDE, photoreal=lora)
        gen_hd.save_png(Image.fromarray(out), path)
        return np.asarray(Image.fromarray(out).resize((SIDE, SIDE), Image.LANCZOS)).astype(np.float32)

    global S
    S = args.scale
    per_img = max(1, args.per_image)
    offs = regions(per_img)
    if per_img > 1 and 96 * S > SIDE / 2:
        raise SystemExit("--per-image %d не помещается при --scale %d: окна 3x3 клеток перекроются" % (per_img, S))
    n_img = -(-args.variants // per_img)
    total = sum(len(styles) * n_img * (1 + (0 if g.get("mix") else len([t for t in g.get("over", "").split(",")
                                                                         if t.strip()])))
                for g in groups)
    textures = {}                                   # (стиль, набор, кадр) -> текстуры клетки, для "mix"
    done = 0
    t0 = time.time()
    for st in styles:
        sty = STYLE[st]
        for g in groups:
            base = fg.parse_key(g["base"])
            overs = [fg.parse_key(t) for t in g.get("over", "").split(",") if t.strip()]
            out_dir = os.path.join(args.out, "%s%s_%s" % (args.prefix, st, g["name"]))
            os.makedirs(out_dir, exist_ok=True)
            print("=== %s: %s%s" % (out_dir, g["base"], (" + " + g["over"]) if overs else ""), flush=True)
            base_scr, base_shift = [], []
            for n, (s, f) in enumerate([base] + overs):
                spr = world.sprite(s, f, None)
                ref = pf.unroll(spr, p)
                var = []
                if n > 0 and g.get("mix"):
                    var, cov = mix_over(textures[(st,) + fg.parse_key(g["mix"])], textures[(st,) + base], ref, p, g,
                                        args.seed + 1000 * n, args.variants)
                    print("[смесь] %s %s %d - поросль %d%%, без модели" % (st, s, f, round(100 * cov)), flush=True)
                for i in range(0 if (n > 0 and g.get("mix")) else n_img):
                    seed = args.seed + 100 * i + n
                    if n == 0:
                        # эскиз - средний цвет оригинала и свой шум, без ЕГО пятен: пятна повторяются с периодом
                        # клетки, и модель ставила по камню и кусту на каждое - гравий вышел ровной решёткой
                        # (проба #223, 28.09)
                        sketch = blob_sketch(ref.reshape(-1, 3), seed, g.get("per_tile", 5), g.get("radius", 4.0),
                                             shadow=g.get("shadow", 0.45))
                        prompt = (sty["text"].replace("{view}", VIEW).replace("{thing}", g.get("thing", "tuft"))
                                  .replace("{what}", g["what"]).replace("{detail}", g["detail"]))
                        cover = 0
                    else:
                        cover = float(fg.green_mask(ref, 4.0).mean())
                        # крупные пятна зелени (SIDE/24) на карте легли ромбами клеток: 1 и 2 стоят шахматкой
                        # (#225, 28.09) - over_grain мельче даёт густоту, а не блок
                        gr_ = float(g.get("over_grain", 24))
                        nz = screen_noise(seed, SIDE / gr_) + 0.35 * screen_noise(seed + 1, SIDE / (gr_ * 2.7))
                        th = np.quantile(nz, 1.0 - cover) if cover > 0 else nz.max() + 1
                        m = pf.blur_wrap((nz > th).astype(np.float32)[..., None], 4.0)
                        gm = fg.green_mask(ref, 1.0)
                        greens = ref[gm > 0.5] if (gm > 0.5).any() else ref.reshape(-1, 3)
                        # под кусты - пятно зелени по маске, по нему частые кустики той же разметки
                        sketch = base_scr[i] * (1 - m) + greens.mean(0) * m
                        sketch = blob_sketch(greens, seed, g.get("over_per_tile", 6), g.get("over_radius", 3.5),
                                             base=sketch, mask=m[..., 0], shadow=g.get("shadow", 0.45))
                        prompt = (OVER.replace("{moss}", g["moss"])
                                  .replace("{cover}", str(max(5, int(round(100 * cover))))))
                    if i == 0:
                        gen_hd.save_png(Image.fromarray(sketch.clip(0, 255).astype(np.uint8)),
                                        os.path.join(out_dir, "%s_%d_sketch.png" % (s, f)))
                    done += 1
                    print("[%d/%d] %s %s %d ответ %d%s" % (done, total, st, s, f, i,
                                                           "" if n == 0 else " - поросль %d%%" % round(100 * cover)),
                          flush=True)
                    scr = paint(sketch, prompt, sty["neg"], seed, sty["lora"],
                                os.path.join(out_dir, "%s_%d_v%d_screen.png" % (s, f, i)))
                    if n == 0:
                        base_scr.append(scr)
                    # варианты - разные окна одного ответа: поросль j лежит в том же окне, что основа j
                    for r, off in enumerate(offs):
                        j = i * per_img + r
                        if j >= args.variants:
                            break
                        per = fg.periodic_seam(to_uv(scr, p, off), p, int(1.5 * p), int(1.5 * p), p // 8)
                        if n == 0:
                            var.append(pf.tone_low(per, ref, p / 6.0))
                            base_shift.append(var[-1] - per)
                        else:                       # поправка тона основы j: земля под травой = голая
                            var.append(np.clip(per + base_shift[j], 0, 255))
                    el = time.time() - t0
                    print("  %s, осталось ~%s" % (gen_hd.human_time(el), gen_hd.human_time(el / done * (total - done))),
                          flush=True)
                textures[(st, s, f)] = var
                d = os.path.join(out_dir, s + ".PCK")
                os.makedirs(d, exist_ok=True)
                for j, tx in enumerate(var):
                    gen_hd.save_png(pf.cell(spr, tx), os.path.join(d, "%d.png" % f if j == 0 else "%d.v%d.png" % (f, j)))
            print("ГОТОВО %s" % out_dir, flush=True)
    print("готово за %s" % gen_hd.human_time(time.time() - t0), flush=True)


if __name__ == "__main__":
    main()
