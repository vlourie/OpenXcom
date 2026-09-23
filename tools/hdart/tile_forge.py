#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Кузница плиток: нарисованная картинка -> клетка игрового пака.

Смысл в разделении обязанностей. Художник (GPT, Qwen, человек в фотошопе) рисует КРАСОТУ и
больше ни за что не отвечает. Форма ромба, положение предмета, проходимость и стыки задаются
здесь арифметикой по оригиналу - их нельзя выпросить у модели, но можно посчитать.

Почему так: у Qwen-Image-2.1 нет ни strength, ни маски, ни ControlNet, и её входная картинка -
это условие, а не холст (модель всегда стартует из шума). Значит сохранение геометрии у неё не
гарантируется архитектурой, только выучено. У GPT то же самое. Поэтому геометрию мы не просим,
а навязываем.

    ===== fit: из папки нарисованных плиток собрать пак =====

    py -3 tools\hdart\tile_forge.py fit --sheets art/TERRAIN --set DESERT.PCK ^
        --in gpt_desert\return --mod "Пиратки\Dioxine_XPiratez\user\mods\hd_gpt"

    Номер кадра берётся из имени файла (первое число: 45.png, frame_45.png, 45_skull_v2.png).
    Для каждой плитки: обрезается тёмный ободок (доля подбирается по замеру), картинка
    вписывается в след оригинала и режется по его альфе. Пишется <mod>\hd\TERRAIN\<набор>\<N>.png
    и отчёт forge\<набор>\ - лист «оригинал | вписано | поле» и forge.tsv с цифрами.

    ===== material / object / assemble: нарисовать своё (нужен .venv-qwen21) =====

    material  - полотно грунта 2K по описанию (один раз на вид грунта)
    object    - предмет на прозрачном фоне по подсказке кадра
    assemble  - ромб из материала + предмет на место из оригинала -> клетка пака

Ключевая мера качества - КРАЙ ПРОТИВ СЕРЕДИНЫ. Если пиксели у границы ромба темнее, чем
внутри, при укладке появляется тёмная решётка по стыкам. У оригиналов X-COM край светлее
середины (у DESERT +9.1). Этого и добиваемся.
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                                  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter       # noqa: E402

REPORT_IN_SET = "report"
ENC = "utf-8-sig"


# ------------------------------------------------------------------ набор и кадры

class Sheet:
    """Лист оригинала и всё, что из него нужно знать про кадр."""

    def __init__(self, sheets, set_name):
        self.dir = os.path.join(sheets, set_name)
        self.name = set_name
        with open(os.path.join(self.dir, "layout.json"), encoding=ENC) as f:
            self.lay = json.load(f)
        self.fw = self.lay["frame_w"]
        self.fh = self.lay["frame_h"]
        self.m = self.lay["margin"]
        self.cols = self.lay["columns"]
        self.scale = self.lay.get("scale", 4)
        self.img = Image.open(os.path.join(self.dir, "original.png")).convert("RGBA")
        self.hints = {}
        hp = os.path.join(self.dir, "hints.json")
        if os.path.exists(hp):
            with open(hp, encoding=ENC) as f:
                self.hints = {int(k): v for k, v in json.load(f).items()}

    def frame(self, i):
        r, c = divmod(i, self.cols)
        x = self.m + c * (self.fw + 2 * self.m)
        y = self.m + r * (self.fh + 2 * self.m)
        return self.img.crop((x, y, x + self.fw, y + self.fh))

    def frames(self):
        return range(self.lay["count"])


def alpha_box(im, thr=128):
    """Прямоугольник непрозрачного, или None."""
    a = np.asarray(im.convert("RGBA"))[..., 3]
    ys, xs = np.nonzero(a > thr)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def content_box(im, thr=100):
    """Прямоугольник содержимого. У рисованной плитки край альфы мягкий, и эти полупрозрачные
    пиксели темнее тела - если взять их в работу, при переводе в RGB они станут тёмной каймой,
    а в укладке - решёткой по стыкам. Поэтому берём только ПЛОТНОЕ (альфа почти 255)."""
    a = np.asarray(im.convert("RGBA"))[..., 3]
    if a.min() < 250:
        ys, xs = np.nonzero(a > 250)
        if len(xs):
            return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
        box = alpha_box(im)
        if box is not None:
            return box
    a = np.asarray(im.convert("RGB"), np.float64)
    corners = np.concatenate([a[:15, :15].reshape(-1, 3), a[:15, -15:].reshape(-1, 3),
                              a[-15:, :15].reshape(-1, 3), a[-15:, -15:].reshape(-1, 3)])
    bg = np.median(corners, axis=0)
    mask = np.abs(a - bg).sum(-1) > thr
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


# ------------------------------------------------------------------ край против середины

def rim_masks(alpha_big, band=3):
    """(кольцо у края, внутренность) по маске клетки."""
    mk = np.asarray(alpha_big) > 128
    inner = mk.copy()
    for d in range(1, band + 1):
        inner = (inner & np.roll(mk, d, 0) & np.roll(mk, -d, 0)
                 & np.roll(mk, d, 1) & np.roll(mk, -d, 1))
    return mk & ~inner, inner


def rim_delta(cell, rim, inner):
    """Насколько край светлее середины. Отрицательное - будет тёмная решётка по стыкам."""
    a = np.asarray(cell.convert("RGB"), np.float64).mean(-1)
    if rim.sum() < 4 or inner.sum() < 4:
        return 0.0
    return float(a[rim].mean() - a[inner].mean())


def flatten_gradient(cell, alpha_big, blur=None, amount=1.0):
    """Снять плавный перепад яркости по плитке: делим на собственное размытие, нормируем обратно.
    Размывается ПРЕМУЛЬТИПЛИЦИРОВАННАЯ яркость вместе с покрытием - иначе прозрачные окрестности
    затягивают края в чёрное (те же грабли, что были у chroma_lock)."""
    rgba = np.asarray(cell.convert("RGBA"), np.float64)
    cov = (np.asarray(alpha_big, np.float64) > 128).astype(np.float64)
    if cov.sum() < 16:
        return cell
    lum = rgba[..., :3].mean(-1)
    r = blur or max(cell.width, cell.height) / 6.0
    prem = Image.fromarray(np.clip(lum * cov, 0, 255).astype(np.uint8), "L")
    cvr = Image.fromarray((cov * 255).astype(np.uint8), "L")
    pb = np.asarray(prem.filter(ImageFilter.GaussianBlur(r)), np.float64)
    cb = np.asarray(cvr.filter(ImageFilter.GaussianBlur(r)), np.float64) / 255.0
    field = np.where(cb > 1e-3, pb / np.maximum(cb, 1e-3), lum)
    mean = lum[cov > 0.5].mean()
    gain = np.where(field > 1e-3, mean / np.maximum(field, 1e-3), 1.0)
    gain = 1.0 + amount * (gain - 1.0)
    out = np.clip(rgba[..., :3] * gain[..., None], 0, 255)
    return Image.fromarray(np.concatenate([out, rgba[..., 3:4]], -1).astype(np.uint8), "RGBA")


# ------------------------------------------------------------------ вписывание в след

MCD_FLOOR = 0


def is_floor(sh, i):
    """Пол или предмет. Берём из MCD (layout.json пишет тип каждого кадра): 0 - пол, 3 - объект.
    Это надёжнее любой догадки по силуэту: низкий плоский камень по виду не отличить от пола,
    а режутся они по-разному."""
    types = sh.lay.get("types")
    if types and i < len(types):
        return types[i] == MCD_FLOOR
    box = alpha_box(sh.frame(i))
    if box is None:
        return False
    return (box[3] - box[1]) <= sh.fh * 0.45 and box[3] >= sh.fh - 1


def fit_object(drawn, frame, scale, alpha_mode="drawn", grow=1):
    """Предмет: растянуть нарисованное в габарит оригинала и взять ЕГО СОБСТВЕННУЮ прозрачность.
    Резать кактус по грубому силуэту оригинала нельзя - от веток останутся обрубки. Габарит при
    этом остаётся оригинальным, так что предмет занимает ту же клетку и не лезет на соседей."""
    fb = alpha_box(frame)
    db = content_box(drawn)
    if fb is None or db is None:
        return None
    bx0, by0, bx1, by1 = fb
    body = drawn.convert("RGBA").crop(db)
    tw, th = max(1, (bx1 - bx0) * scale), max(1, (by1 - by0) * scale)
    body = body.resize((tw, th), Image.LANCZOS)
    cw, ch = frame.width * scale, frame.height * scale
    out = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    out.alpha_composite(body, (bx0 * scale, by0 * scale))
    if alpha_mode in ("original", "both"):
        keep = frame.split()[3].resize((cw, ch), Image.NEAREST)
        if grow > 0:
            keep = keep.filter(ImageFilter.MaxFilter(2 * grow * scale + 1))
        a = np.asarray(out)[..., 3].astype(np.float64)
        k = np.asarray(keep).astype(np.float64)
        a = a * (k / 255.0) if alpha_mode == "both" else np.minimum(a, k)
        arr = np.asarray(out).copy()
        arr[..., 3] = np.clip(a, 0, 255).astype(np.uint8)
        out = Image.fromarray(arr, "RGBA")
    return out


def opaque_rgb(im):
    """RGB без чёрного следа от прозрачности: полупрозрачные и пустые пиксели заменяются средним
    цветом плотной части. Тогда край плитки не темнеет от самого факта перевода в RGB."""
    rgba = np.asarray(im.convert("RGBA"), np.float64)
    solid = rgba[..., 3] > 250
    if solid.sum() < 16:
        return im.convert("RGB")
    fill = rgba[..., :3][solid].mean(0)
    out = np.where(solid[..., None], rgba[..., :3], fill[None, None, :])
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB")


def to_footprint(drawn, frame, scale, inset=0.0):
    """Нарисованное -> клетка пака: растянуть содержимое в след ромба и обрезать по альфе оригинала.
    inset - какую долю периметра выбросить (там у рисованных плиток тёмный ободок)."""
    box = content_box(drawn)
    if box is None:
        return None
    X0, Y0, X1, Y1 = box
    dw = int((X1 - X0) * inset / 2)
    dh = int((Y1 - Y0) * inset / 2)
    body = opaque_rgb(drawn).crop((X0 + dw, Y0 + dh, max(X0 + dw + 1, X1 - dw),
                                   max(Y0 + dh + 1, Y1 - dh)))
    fb = alpha_box(frame)
    if fb is None:
        return None
    bx0, by0, bx1, by1 = fb
    tw, th = (bx1 - bx0) * scale, (by1 - by0) * scale
    body = body.resize((max(1, tw), max(1, th)), Image.LANCZOS)
    cw, ch = frame.width * scale, frame.height * scale
    cell = Image.new("RGB", (cw, ch), (0, 0, 0))
    cell.paste(body, (bx0 * scale, by0 * scale))
    mask = frame.split()[3].resize((cw, ch), Image.NEAREST)
    out = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    out.paste(cell, (0, 0), mask)
    return out


def best_fit(drawn, frame, scale, target, max_inset=0.20, step=0.01, flatten="auto"):
    """Подобрать обрезку периметра так, чтобы край стал не темнее середины. Если не выходит -
    выровнять перепад по плитке. Возвращает (клетка, доля обрезки, край до, край после, что делали)."""
    mask = frame.split()[3].resize((frame.width * scale, frame.height * scale), Image.NEAREST)
    rim, inner = rim_masks(mask)
    first = to_footprint(drawn, frame, scale, 0.0)
    if first is None:
        return None, 0.0, 0.0, 0.0, "пусто"
    before = rim_delta(first, rim, inner)
    best = (first, 0.0, before)
    n = int(round(max_inset / step))
    for k in range(n + 1):
        ins = k * step
        cell = to_footprint(drawn, frame, scale, ins)
        d = rim_delta(cell, rim, inner)
        if d > best[2]:
            best = (cell, ins, d)
        if d >= target:
            return cell, ins, before, d, "обрезка %d%%" % round(ins * 100)
    cell, ins, d = best
    if flatten == "off":
        return cell, ins, before, d, "обрезка %d%% (край всё ещё тёмный)" % round(ins * 100)
    # обрезка не помогла - значит это не ободок, а плавный перепад по всей плитке (светлая
    # середина, тёмные углы). Его снимает деление на собственное размытие; перебираем силу
    # и радиус, берём лучшее
    side = max(cell.width, cell.height)
    tries = [(cell, ins, d, "обрезка %d%%" % round(ins * 100))]
    for amount in (0.6, 1.0):
        for rad in (side / 8.0, side / 5.0, side / 3.0):
            f = flatten_gradient(cell, mask, blur=rad, amount=amount)
            tries.append((f, ins, rim_delta(f, rim, inner),
                          "обрезка %d%% + выравнивание %.0f%%" % (round(ins * 100), amount * 100)))
    cell, ins, d, how = max(tries, key=lambda t: t[2])
    if d < target:
        how += " (не дотянул)"
    return cell, ins, before, d, how


# ------------------------------------------------------------------ картинки для глаз

def checker(im, step=12):
    bg = Image.new("RGB", im.size, (104, 104, 110))
    d = ImageDraw.Draw(bg)
    for y in range(0, im.height, step):
        for x in range(0, im.width, step):
            if (x // step + y // step) % 2 == 0:
                d.rectangle((x, y, x + step - 1, y + step - 1), fill=(132, 132, 138))
    im = im.convert("RGBA")
    bg.paste(im, (0, 0), im)
    return bg


def field_of(cell, fw, fh, scale, n=5):
    """Клетки на изосетке, как их кладёт движок: шаг 16 на 8 в исходных пикселях."""
    sx, sy = 16 * scale, 8 * scale
    W, H = (2 * n + 1) * sx + fw * scale, (2 * n + 1) * sy + fh * scale
    ox, oy = n * sx, n * sy
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pts = {(ox + sx * (i - j), oy + sy * (i + j))
           for i in range(-n, n + 1) for j in range(-n, n + 1)}
    for x, y in sorted(pts, key=lambda p: (p[1], p[0])):
        out.alpha_composite(cell, (x, y))
    return out


def middle(im, w, h):
    cx, cy = im.width // 2, im.height // 2
    return im.crop((max(0, cx - w // 2), max(0, cy - h // 2), cx + w // 2, cy + h // 2))


def label(im, text):
    out = im.convert("RGB").copy()
    d = ImageDraw.Draw(out)
    d.rectangle((0, 0, 8 + 7 * len(text), 16), fill=(0, 0, 0))
    d.text((4, 2), text, fill=(255, 220, 0))
    return out


# ------------------------------------------------------------------ fit

FRAME_PATTERNS = (r"^(\d+)(?:\D|$)", r"frame[ _-]?(\d+)", r"кадр[ _-]?(\d+)", r"#(\d+)")


def frame_number(name):
    """Номер кадра из имени файла. Нарочно НЕ «первое число в имени»: у выгрузки из чата имена
    вида «ChatGPT Image Sep 21, 2026, 06_37_35 AM (1).png», и первое число там - день месяца.
    Тихо посадить плитку не в тот кадр хуже, чем отказаться: берём только явные формы."""
    base = os.path.splitext(os.path.basename(name))[0]
    for pat in FRAME_PATTERNS:
        m = re.search(pat, base, re.IGNORECASE)
        if m:
            return int(m.group(1))
    return None


def cmd_fit(args):
    sh = Sheet(args.sheets, args.set_name)
    scale = args.scale or sh.scale
    files = {}
    for f in sorted(os.listdir(args.in_dir)):
        if not f.lower().endswith((".png", ".webp")):
            continue
        i = frame_number(f)
        if i is None:
            print("  пропуск: в имени «%s» нет явного номера кадра. Нужна форма 45.png, "
                  "frame_45.png или 45_что-угодно.png" % f, file=sys.stderr)
            continue
        files.setdefault(i, []).append(f)
    if not files:
        raise SystemExit("в %s нет картинок с номером кадра в имени" % args.in_dir)

    out_dir = os.path.join(args.mod, "hd", args.pack_path, sh.name) if args.mod else ""
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    # Отчёт лежит внутри своего набора: art\TERRAIN\<НАБОР>.PCK\report. Отдельная
    # папка forge на корне разводила набор и его сверку по разным местам, и через
    # неделю уже не понять, к какому прогону отчёт относится.
    rep_dir = (os.path.join(args.sheets, sh.name, args.report)
               if args.report == REPORT_IN_SET else os.path.join(args.report, sh.name))
    os.makedirs(rep_dir, exist_ok=True)

    # к чему стремимся: у самого оригинала край обычно светлее середины
    rows, panels = [], []
    print("%-5s %-30s %-8s %-7s %-8s %-8s %s"
          % ("кадр", "файл", "стороны", "ориг", "до", "после", "что сделали"))
    for i in sorted(files):
        name = files[i][0]
        if len(files[i]) > 1:
            print("  кадр %d: файлов несколько, беру %s" % (i, name), file=sys.stderr)
        if i not in list(sh.frames()):
            print("  кадр %d: в наборе такого нет, пропуск" % i, file=sys.stderr)
            continue
        frame = sh.frame(i)
        fb = alpha_box(frame)
        if fb is None:
            print("  кадр %d: в оригинале пусто, пропуск" % i, file=sys.stderr)
            continue
        mask = frame.split()[3].resize((frame.width * scale, frame.height * scale), Image.NEAREST)
        rim, inner = rim_masks(mask)
        orig_big = frame.resize((frame.width * scale, frame.height * scale), Image.NEAREST)
        # цель - лишь бы край не был ТЕМНЕЕ середины: решётка появляется именно от этого.
        # Гнаться за числом оригинала незачем, это стоило бы выброшенных процентов рисунка
        own = rim_delta(orig_big, rim, inner)
        # мерило - сам оригинал. У #42 и #44 в DESERT край и так темнее середины (-6), так что
        # требовать от рисунка плюса там бессмысленно: достаточно «не хуже, чем было»
        target = args.rim if args.rim is not None else min(2.0, own)

        drawn = Image.open(os.path.join(args.in_dir, name)).convert("RGBA")
        cb = content_box(drawn)
        ratio = (cb[2] - cb[0]) / max(1, cb[3] - cb[1]) if cb else 0
        want = (fb[2] - fb[0]) / max(1, fb[3] - fb[1])
        kind = args.kind if args.kind != "auto" else ("floor" if is_floor(sh, i) else "object")
        if kind == "object":
            # предмету решётка по стыкам не грозит: он не выкладывается полем
            cell = fit_object(drawn, frame, scale, args.alpha, args.grow)
            ins, before, after, how = 0.0, 0.0, 0.0, "предмет, своя прозрачность"
            if args.alpha != "drawn":
                how = "предмет, прозрачность %s" % args.alpha
        else:
            cell, ins, before, after, how = best_fit(drawn, frame, scale, target,
                                                     args.max_inset, 0.01, args.flatten)
        if cell is None:
            print("  кадр %d: картинка пустая, пропуск" % i, file=sys.stderr)
            continue
        if out_dir:
            cell.save(os.path.join(out_dir, "%d.png" % i))
        rows.append((i, name, ratio, want, ins, before, after, how, sh.hints.get(i, ""), own, kind))
        print("%-5d %-30s %-8s %+7.1f %+8.1f %+8.1f  %s"
              % (i, name[:28], "%.2f:1" % ratio, own, before, after, how))
        if len(panels) < args.preview:
            fpv = middle(field_of(cell, sh.fw, sh.fh, scale), 560, 380)
            panels.append((i, orig_big, cell, fpv))

    with open(os.path.join(rep_dir, "forge.tsv"), "w", encoding=ENC, newline="") as f:
        f.write("кадр\tфайл\tстороны\tнужно\tобрезка\tкрай оригинала\tкрай до\tкрай после\t"
                "что сделали\tвид\tподсказка\n")
        for r in rows:
            f.write("%d\t%s\t%.2f\t%.2f\t%.0f%%\t%.1f\t%.1f\t%.1f\t%s\t%s\t%s\n"
                    % (r[0], r[1], r[2], r[3], r[4] * 100, r[9], r[5], r[6], r[7], r[10], r[8]))

    if panels:
        W, H = 230, 290
        FW, FH = 460, 310
        out = Image.new("RGB", (10 + len(panels) * (2 * W + FW + 40), FH + 46), (26, 26, 30))
        d = ImageDraw.Draw(out)
        for k, (i, o, c, fv) in enumerate(panels):
            x = 10 + k * (2 * W + FW + 40)
            out.paste(checker(o.resize((W, H), Image.NEAREST)), (x, 30))
            out.paste(checker(c.resize((W, H), Image.NEAREST)), (x + W + 6, 30))
            bg = Image.alpha_composite(Image.new("RGBA", fv.size, (38, 38, 42, 255)), fv)
            out.paste(bg.convert("RGB").resize((FW, FH), Image.LANCZOS), (x + 2 * W + 16, 30))
            d.text((x, 8), "#%d  оригинал | вписано | поле" % i, fill=(255, 220, 0))
        out.save(os.path.join(rep_dir, "forge.png"))

    bad = [r for r in rows if r[10] == "floor" and r[6] < min(0.0, r[9]) - 0.5]
    print("")
    print("клеток собрано: %d" % len(rows))
    if out_dir:
        print("пак: %s" % out_dir)
    print("отчёт: %s (forge.tsv, forge.png)" % rep_dir)
    if bad:
        print("край хуже, чем у оригинала, у %d клеток: %s - будет решётка по стыкам"
              % (len(bad), " ".join(str(r[0]) for r in bad)), file=sys.stderr)
    missing = [i for i in sh.frames() if i not in files]
    if missing and args.list_missing:
        print("кадров без картинки: %d (%s)"
              % (len(missing), " ".join(str(i) for i in missing[:40])))


def build_parser():
    ap = argparse.ArgumentParser(description="нарисованные плитки -> клетки игрового пака")
    sub = ap.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fit", help="собрать пак из папки нарисованных плиток")
    f.add_argument("--sheets", default="art/TERRAIN")
    f.add_argument("--set", dest="set_name", required=True)
    f.add_argument("--in", dest="in_dir", required=True, help="папка с нарисованными плитками")
    f.add_argument("--mod", default="", help="куда писать пак (пусто - только отчёт)")
    f.add_argument("--pack-path", default="TERRAIN", dest="pack_path")
    f.add_argument("--scale", type=int, default=0, help="масштаб пака (0 - как в layout.json)")
    f.add_argument("--rim", type=float, default=None,
                   help="какой край считать хорошим (по умолчанию - половина от края оригинала)")
    f.add_argument("--max-inset", type=float, default=0.20, dest="max_inset",
                   help="максимум, сколько периметра можно выбросить")
    f.add_argument("--kind", choices=["auto", "floor", "object"], default="auto",
                   help="как резать: floor - вписать в ромб и обрезать по альфе оригинала; "
                        "object - взять собственную прозрачность рисунка в габарите оригинала; "
                        "auto - решать по кадру")
    f.add_argument("--alpha", choices=["drawn", "original", "both"], default="drawn",
                   help="прозрачность предмета: своя (по умолчанию), по оригиналу или произведение")
    f.add_argument("--grow", type=int, default=1,
                   help="на сколько исходных пикселей расширить силуэт оригинала при --alpha "
                        "original/both (чтобы не срезать ветки)")
    f.add_argument("--flatten", choices=["auto", "off"], default="auto",
                   help="выравнивать перепад яркости по плитке, если обрезка не помогла")
    f.add_argument("--report", default=REPORT_IN_SET,
                   help="папка отчёта; по умолчанию report внутри набора")
    f.add_argument("--preview", type=int, default=6, help="сколько клеток положить на лист")
    f.add_argument("--list-missing", action="store_true", dest="list_missing")
    f.set_defaults(func=cmd_fit)
    return ap


def main():
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
