#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Проба качества предметов террейна: Qwen-Image-2.1 рисует предмет заново, отдельно, по описанию.

Зачем: map_paint (SDXL + tile + canny по сглаженному оригиналу) даёт «кубики» - модель повторяет
пятна 32x40, дерево выходит кляксой (Vitali 27.09). Здесь модель стартует из шума и видит оригинал
только как эскиз формы и палитры, поэтому пиксельную сетку не копирует (R-066 - у правки почти
побайтно, у 2.1 из шума - нет).

Два стиля промпта (--styles):
    strict  - тот же предмет, то же положение и размер, детальная прорисовка
    free    - оригинал только эскиз: силуэт, поза, палитра; рисунок целиком свой

Альфа: снятие подложки (gen_fire.unpanel) и обрезка габаритом оригинала с запасом --grow (R-089).
Подложка - нейтральный цвет, самый далёкий от тела кадра (attic/paint3.pick_background).

Лист на тёмном полу, в полный размер x4 и крупно x2 (R-088 - судить глазами, не мерками):
    оригинал x4 | прежний пак (мод hd) | map_paint (серия) | strict | free

    tools\hdart\.venv-qwen21\Scripts\python.exe tools\hdart\probe_object.py ^
        --set JUNGLEBITS.PCK --frame 3,4,5 --hints art/maps/paint/hints_MUJUNGLE.json

Кладёт в art/probe/<набор>/: <кадр>_<стиль>_1hd.png (ответ модели), <кадр>_<стиль>_cut.png (x4 RGBA),
sheet.png. В пак НЕ идёт.
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
import gen_fire                                     # noqa: E402
import numpy as np                                  # noqa: E402
from PIL import Image                               # noqa: E402

BACKGROUNDS = [(38, 38, 42), (96, 96, 102), (176, 176, 182)]   # как attic/paint3.py
FLOOR = (24, 20, 18)                                # тёмный пол боя - на нём видна кайма
MOD_TERRAIN = "Пиратки/Dioxine_XPiratez/user/mods/hd/hd/TERRAIN"   # копия, которую читает игра (R-087)
SERIES = "art/maps/paint/series"

STYLE = {
    "strict": (
        "<image1> is the low-resolution original sprite of {what}, shown on a flat grey preview panel. "
        "The panel is interface, not part of the sprite. "
        "Use case: sketch-to-render. Asset type: polished 4x HD object sprite for an X-COM-style "
        "isometric strategy game, seen from above at 30 degrees. "
        "Redraw this same object as detailed hand-painted game artwork: {what}. Keep the position, "
        "the size, the silhouette and the palette of <image1>. Clear readable shapes, crisp edges, "
        "fine painted detail, soft light from the upper left. "
        "Output one isolated object on the same flat panel. No ground, no tile, no other objects, "
        "no frame, no text."),
    "free": (
        "<image1> is only a rough colour sketch of {what}: use it for the silhouette, the pose, the "
        "size and the colours, nothing else. The flat panel is background. "
        "Paint a new high-detail illustration of {what} for an isometric strategy game, seen from "
        "above at 30 degrees: every part clearly drawn and readable, rich natural texture, crisp "
        "edges, soft light from the upper left, painted game art like a classic isometric RPG. "
        "One isolated object, same size and placement as the sketch, on the same flat panel. "
        "No ground, no tile, no other objects, no frame, no text."),
}
NEGATIVE = ("pixel art, pixelated, blocky, jagged stair-stepped edges, dithering, blurry, smudged, "
            "blob, noise, low detail, ground, grass tile, floor, panel frame, border, drop shadow, "
            "text, watermark, photo")


def pick_background(frame):
    a = np.asarray(frame.convert("RGBA"), np.float64)
    px = a[..., :3][a[..., 3] > 128]
    if len(px) == 0:
        return BACKGROUNDS[0]
    return max(BACKGROUNDS, key=lambda bg: float(np.percentile(np.abs(px - np.array(bg)).max(-1), 10)))


SMOOTH_SILHOUETTE = True      # False - прежняя маска NEAREST x4 (obj_series --recut --old-mask, сверка)


def fill_holes(mask, max_area=48):
    """Маска k=1 (L 0/255) -> та же с залитыми внутренними дырами не больше max_area пикселей.
    У оригинала внутри предмета бывают прозрачные пиксели (тёмная бутылка на стойке BRICKBAR 14 - индекс 0),
    и вырезка по ним пробивала в нарисованной столешнице дыру."""
    m = np.asarray(mask) > 0
    h, w = m.shape
    seen = np.zeros_like(m)
    for y0 in range(h):
        for x0 in range(w):
            if m[y0, x0] or seen[y0, x0]:
                continue
            comp, stack, edge = [], [(y0, x0)], False      # связная область пустоты (4-соседство)
            seen[y0, x0] = True
            while stack:
                y, x = stack.pop()
                comp.append((y, x))
                edge |= y == 0 or x == 0 or y == h - 1 or x == w - 1
                for yy, xx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                    if 0 <= yy < h and 0 <= xx < w and not m[yy, xx] and not seen[yy, xx]:
                        seen[yy, xx] = True
                        stack.append((yy, xx))
            if not edge and len(comp) <= max_area:        # дыра внутри, мелкая - залить
                ys, xs = zip(*comp)
                m[list(ys), list(xs)] = True
    return Image.fromarray(m.astype(np.uint8) * 255, "L")


def smooth_silhouette(mask, k=4):
    """Силуэт k=1 (L 0/255) -> x k линиями, а не лесенкой (R-121): xBRZ по чёрно-белой маске спрямляет
    косые края (изо-наклон 2:1) и оставляет углы и тонкие штрихи; внутренние дыры оригинала залиты;
    лёгкое размытие - сглаживание края в долю пикселя, не расплывание."""
    from PIL import ImageFilter
    import sprite_scale
    a = np.asarray(fill_holes(mask), np.float32)
    rgba = np.stack([a, a, a, np.full_like(a, 255.0)], -1)[None]
    up = sprite_scale.xbrz_scale(rgba, k)[0][..., 0]
    return Image.fromarray(np.clip(up, 0, 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(0.7))


def cut_out(hd, frame, grow, soft, floor=0.30, max_aspect=1.3, matte=None):
    """Ответ модели -> кадр x4 с альфой (R-089). Фон модель перерисовывает не тем цветом, что задан
    (заказ 176 - вышло ~196), поэтому подложку берём по краю ответа, а не по заказу. Остаток
    подложки ниже floor режем, силуэт ограничиваем маской оригинала, расширенной на grow пикселей.
    matte - готовая альфа ответа (float 0..1, obj_photo.edge_matte) вместо ключа по цвету подложки."""
    from PIL import ImageFilter
    if matte is not None:
        al = np.asarray(matte, np.float32)
        rgba = hd.convert("RGBA")
    else:
        a = np.asarray(hd.convert("RGB"), np.float32)
        edge = np.concatenate([a[:8].reshape(-1, 3), a[-8:].reshape(-1, 3),
                               a[:, :8].reshape(-1, 3), a[:, -8:].reshape(-1, 3)])
        bg = tuple(float(v) for v in np.median(edge, axis=0))
        rgba = gen_fire.unpanel(hd, bg, soft)
        al = np.asarray(rgba.split()[3], np.float32) / 255.0
        al = np.clip((al - floor) / (1.0 - floor), 0.0, 1.0)
    rgba.putalpha(Image.fromarray((al * 255).astype(np.uint8), "L"))
    cw, ch = frame.width * 4, frame.height * 4
    # модель оставляет вокруг предмета поля (куст 2 - шарик в половину холста): габарит ответа
    # растягиваем на габарит оригинала, форму правим не больше чем на max_aspect
    ob = frame.split()[3].getbbox()
    # сужение 5x5 убирает одиночные крошки подложки, иначе они раздувают габарит ответа
    ab = Image.fromarray((al > 0.5).astype(np.uint8) * 255, "L").filter(ImageFilter.MinFilter(5)).getbbox()
    if ab:
        ab = (max(0, ab[0] - 2), max(0, ab[1] - 2), min(hd.width, ab[2] + 2), min(hd.height, ab[3] + 2))
    if ob and ab:
        ox0, oy0, ox1, oy1 = [v * 4 for v in ob]
        sw, sh = (ox1 - ox0) / (ab[2] - ab[0]), (oy1 - oy0) / (ab[3] - ab[1])
        s = (sw * sh) ** 0.5
        sw = min(max(sw, s / max_aspect), s * max_aspect)
        sh = min(max(sh, s / max_aspect), s * max_aspect)
        piece = rgba.crop(ab)
        piece = piece.resize((max(1, round(piece.width * sw)), max(1, round(piece.height * sh))), Image.LANCZOS)
        # по центру габарита оригинала по ширине, низ к низу: предмет стоит на полу. Холст с запасом M -
        # alpha_composite не берёт отрицательный сдвиг, а paste с маской возвёл бы альфу в квадрат
        M = max(piece.width, piece.height)
        big = Image.new("RGBA", (cw + 2 * M, ch + 2 * M), (0, 0, 0, 0))
        big.alpha_composite(piece, (M + round((ox0 + ox1 - piece.width) / 2), M + oy1 - piece.height))
        body = big.crop((M, M, M + cw, M + ch))
    else:
        body = rgba.resize((cw, ch), Image.LANCZOS)
    sil = frame.split()[3].point(lambda v: 255 if v > 0 else 0)
    if grow > 0:
        sil = sil.filter(ImageFilter.MaxFilter(2 * grow + 1))
    if SMOOTH_SILHOUETTE:
        sil = smooth_silhouette(sil, 4)
    else:                                           # прежний силуэт - лесенка (для сверки перевырезки)
        sil = sil.resize((cw, ch), Image.NEAREST).filter(ImageFilter.GaussianBlur(2))
    m = np.asarray(body.split()[3], np.float32) * np.asarray(sil, np.float32) / 255.0
    body.putalpha(Image.fromarray(m.astype(np.uint8), "L"))
    return body


def match_tone(cut, frame, amount):
    """Тон и яркость - к оригиналу (DECISIONS 2026-09-18: цвет задаёт оригинал, яркость - художник).
    Деревья 5-7 модель рисует темнее и синее: сдвигаем среднее и разброс каждого канала непрозрачной
    части к оригиналу на долю amount. Рисунок (перепады внутри) не трогаем - только общий тон."""
    if amount <= 0:
        return cut
    o = np.asarray(frame.convert("RGBA"), np.float32)
    o = o[..., :3][o[..., 3] > 128]
    c = np.asarray(cut, np.float32)
    body = c[..., 3] > 128
    if len(o) == 0 or body.sum() == 0:
        return cut
    src = c[..., :3][body]
    ms, ss = src.mean(0), src.std(0) + 1e-3
    mo, so = o.mean(0), o.std(0) + 1e-3
    # разброс не раздуваем выше своего: у оригинала он от лесенки пикселей, а не от рисунка
    gain = np.minimum(so / ss, 1.0)
    rgb = c[..., :3]
    toned = (rgb - ms) * gain + mo
    c[..., :3] = np.clip(rgb + (toned - rgb) * amount, 0, 255)
    return Image.fromarray(c.astype(np.uint8), "RGBA")


def on_floor(rgba):
    bg = Image.new("RGBA", rgba.size, FLOOR + (255,))
    bg.alpha_composite(rgba)
    return bg.convert("RGB")


def load_png(path):
    return Image.open(path).convert("RGBA") if os.path.exists(path) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=gen_hd.DEFAULT_MODELS_DIR)
    ap.add_argument("--sheets", default="art/TERRAIN")
    ap.add_argument("--set", dest="set_name", default="JUNGLEBITS.PCK")
    ap.add_argument("--frame", default="3,4,5,6,7,8,10,28,29,2")
    ap.add_argument("--hints", default="art/maps/paint/hints_MUJUNGLE.json",
                    help="подсказки карты (ключ НАБОР:кадр); без них - hints.json набора")
    ap.add_argument("--styles", default="strict,free")
    ap.add_argument("--seed", type=int, default=2711)
    ap.add_argument("--steps", type=int, default=40)
    ap.add_argument("--cfg", type=float, default=4.0, help="при 1.0 негатив не действует (R-040)")
    ap.add_argument("--mp", type=float, default=1.0)
    ap.add_argument("--zoom", type=int, default=16)
    ap.add_argument("--grow", type=int, default=2, help="запас за габаритом оригинала, исходных пикселей")
    ap.add_argument("--soft", type=int, default=40)
    ap.add_argument("--out", default="art/probe")
    ap.add_argument("--model", default="")
    ap.add_argument("--offload", default="model", choices=["model", "seq", "none"])
    ap.add_argument("--pad", type=int, default=3,
                    help="запас вокруг предмета, исходных пикселей; -1 - вся клетка (так нарисована проба 27.09)")
    ap.add_argument("--tone", type=float, default=0.7,
                    help="доля подгонки тона к оригиналу, 0 - как нарисовала модель")
    ap.add_argument("--recut", action="store_true",
                    help="без видеокарты: вырезать заново из готовых <кадр>_<стиль>_1hd.png и собрать лист")
    args = ap.parse_args()

    set_dir, lay, set_hints, sheet = gen_fire.load_set(args.sheets, args.set_name)
    base = args.set_name[:-4] if args.set_name.upper().endswith(".PCK") else args.set_name
    hints = {}
    if args.hints and os.path.exists(args.hints):
        with open(args.hints, encoding="utf-8-sig") as f:
            hints = {int(k.split(":")[1]): v for k, v in json.load(f).items()
                     if k.split(":")[0].upper() == base.upper()}
    frames = [int(v) for v in args.frame.split(",") if v.strip()]
    styles = [s for s in args.styles.split(",") if s in STYLE]
    out_dir = os.path.join(args.out, args.set_name)
    os.makedirs(out_dir, exist_ok=True)

    ns = argparse.Namespace(models=args.models, qwen21_model=args.model, qwen21_steps=args.steps,
                            qwen21_cfg=args.cfg, qwen21_mp=args.mp, qwen21_strength=0.0,
                            qwen21_offload=args.offload, qwen21_thrifty=False,
                            qwen21_ref="", qwen21_ref_mp=1.0, qwen21_prompt="strict",
                            qwen21_hint="off", qwen21_ref_order="ref-first")
    painter = None if args.recut else gen_hd.Qwen21Painter(ns, {"ground": ("", "")})
    gen_fire.NEGATIVE = NEGATIVE                    # run_pass берёт негатив из модуля gen_fire

    t0, done, total = time.time(), 0, len(frames) * len(styles)
    rows = []
    for i in frames:
        full = gen_fire.frame_of(sheet, lay, i)
        # мелкий предмет (куст 2 - четверть клетки) модель на всю клетку рисует ещё мельче: отдаём ей
        # только габарит предмета с запасом --pad и ставим ответ обратно на его место в клетке
        box = (0, 0, full.width, full.height)
        bb = full.split()[3].getbbox()
        if args.pad >= 0 and bb:
            box = (max(0, bb[0] - args.pad), max(0, bb[1] - args.pad),
                   min(full.width, bb[2] + args.pad), min(full.height, bb[3] + args.pad))
        frame = full.crop(box)
        what = hints.get(i) or set_hints.get(i) or "a terrain object"
        panel = pick_background(frame)
        # вход гладкий, не nearest: лесенку модель рисует как содержание (R-004)
        src = frame.resize((frame.width * args.zoom, frame.height * args.zoom), Image.BICUBIC)
        flat = Image.new("RGBA", src.size, tuple(panel) + (255,))
        flat.alpha_composite(src)
        src = flat.convert("RGB")
        x4 = full.resize((full.width * 4, full.height * 4), Image.NEAREST)
        # подписи латиницей: у шрифта PIL по умолчанию нет кириллицы
        cells = [("orig x4", x4),
                 ("old pack", load_png(os.path.join(MOD_TERRAIN, args.set_name, "%d.png" % i))),
                 ("map_paint", load_png(os.path.join(SERIES, args.set_name, "%d.png" % i)))]
        for st in styles:
            prompt = STYLE[st].replace("{what}", what)
            print("кадр %d %s: %s | подложка %s" % (i, st, what, panel), flush=True)
            hd_path = os.path.join(out_dir, "%d_%s_1hd.png" % (i, st))
            if args.recut:
                if not os.path.exists(hd_path):
                    continue
                hd = Image.open(hd_path).convert("RGB")
            else:
                hd = gen_fire.run_pass(painter, args, prompt, src, args.seed + i)
                gen_hd.save_png(hd, hd_path)
            part = match_tone(cut_out(hd, frame, args.grow, args.soft), frame, args.tone)
            cut = Image.new("RGBA", (full.width * 4, full.height * 4), (0, 0, 0, 0))
            cut.paste(part, (box[0] * 4, box[1] * 4))
            gen_hd.save_png(cut, os.path.join(out_dir, "%d_%s_cut.png" % (i, st)))
            cells.append((st, cut))
            done += 1
            el = time.time() - t0
            print("  %s, осталось ~%s" % (gen_hd.human_time(el),
                                          gen_hd.human_time(el / done * (total - done))), flush=True)
        # x2 от пака: 256x320 на ячейку, без сглаживания - видно то, что увидит игрок
        row = [gen_hd.label(on_floor(c).resize((c.width * 2, c.height * 2), Image.NEAREST),
                            "%d %s" % (i, name))
               for name, c in cells if c is not None]
        rows.append(gen_hd.side_by_side(row))
    board = Image.new("RGB", (max(r.width for r in rows), sum(r.height + 8 for r in rows)), (32, 32, 36))
    y = 0
    for r in rows:
        board.paste(r, (0, y))
        y += r.height + 8
    path = os.path.join(out_dir, "sheet.png")
    gen_hd.save_png(board, path)
    print("лист: %s\nготово за %s" % (path, gen_hd.human_time(time.time() - t0)))


if __name__ == "__main__":
    main()
