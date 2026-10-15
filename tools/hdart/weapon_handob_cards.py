"""Карточки «оружие в руке» для сотни W-001..W-100: восемь кадров HANDOB и точка, куда HD-слой ставит вспышку.

Часть опознания до генерации (указание специалиста 05.10). Ракурс, хват и дуло боевого кадра берутся отсюда,
внешний вид - из инвентарного BIGOBS.

Кадр в руке (UnitSprite.cpp, Part itemR):
  - юнит смотрит в направлении d, не целится - кадр handSprite + d;
  - целится двуручным - кадр handSprite + (d + 2) % 8 (UnitSprite.cpp:477), одноручным - handSprite + d.
Номер кадра: handSprite из рулсета, при значении не меньше maxSharedFrames HANDOB (128) плюс 1000 (сдвиг мастер-мода).

Точка вспышки - точная копия HdFx::noteTip (src/Engine/HdFx.cpp): по направлению ЮНИТА d (не по номеру кадра)
берётся самый дальний непрозрачный пиксель классического кадра вдоль взгляда на экране, затем среднее пикселей
в полосе 0.75 пикселя от него. Это крайняя точка рисунка, а не обязательно дуло: мушка, штык, магазин, приклад
на диагонали - всё, что выступает дальше ствола, заберёт вспышку. Карточка показывает это глазу.

Запуск: py -3.13 tools/hdart/weapon_handob_cards.py [--only W-053]. Видеокарта не нужна.
"""
import argparse
import csv
import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import weapon_ammo_cards as wac  # noqa: E402

ROOT = wac.ROOT
ENC = "utf-8-sig"
LIST = "art/items/weapons100-v1/list.tsv"
OUT = "art/items/weapons100-v1/handob_cards"
AMMO = "art/items/weapons100-v1/ammo_cards"
HANDOB = "census/items/export/exp_piratez/HANDOB.PCK.png"
HANDOB_FRAMES = "census/items/handob_frames.tsv"
SHARED = 128      # maxSharedFrames HANDOB.PCK у ванили
OFFSET = 1000     # сдвиг мастер-мода (Mod::getOffset)
FW, FH = 32, 40
S = 5             # масштаб кадра на карточке
BG = wac.BG

# HdFx::noteTip: направление на экране, как Pathfinding::dir_x / dir_y через изометрию
DIRX = (0, 1, 1, 1, 0, -1, -1, -1)
DIRY = (-1, -1, 0, 1, 1, 1, 0, -1)


def lround(v):
    """std::lround: половина - от нуля."""
    return int(math.floor(abs(v) + 0.5)) * (1 if v >= 0 else -1)


def note_tip(idx, direction):
    """Копия HdFx::noteTip по классическому кадру (индексы, 0 - прозрачно).
    Возвращает (tipX, tipY) в пикселях кадра, как l.tipX - x, и маску пикселей полосы; None для пустого кадра."""
    sx = DIRX[direction] - DIRY[direction]
    sy = (DIRX[direction] + DIRY[direction]) * 0.5
    ys, xs = np.nonzero(idx)
    if not len(xs):
        return None
    proj = xs * sx + ys * sy
    best = proj.max()
    band = 0.75 * idx.shape[1] / 32.0
    sel = proj >= best - band
    mx, my = xs[sel].mean(), ys[sel].mean()
    m = np.zeros(idx.shape, bool)
    m[ys[sel], xs[sel]] = True
    return lround(mx + 0.5), lround(my + 0.5), m, (sx, sy)


def shape_flags(idx, tip):
    """Подсказки глазу, не вердикт. cross - длинная ось рисунка поперёк взгляда (|cos| < 0.5): крайней точкой
    становится край широкой вещи (плечо лука, лезвие плашмя), а не конец ствола. spread - разброс пикселей полосы
    в пикселях кадра: больше 1.5 - передний край широкий, точка - среднее нескольких выступов."""
    ys, xs = np.nonzero(idx)
    sx, sy = tip[3]
    cos = 1.0
    if len(xs) >= 3:
        c = np.cov(np.vstack([xs, ys]))
        w, v = np.linalg.eigh(c)
        if w[1] > 1.5 * max(w[0], 1e-6):
            ax = v[:, 1]
            cos = abs(ax[0] * sx + ax[1] * sy) / math.hypot(sx, sy)
    by, bx = np.nonzero(tip[2])
    spread = float(math.hypot(bx.max() - bx.min(), by.max() - by.min()))
    # куски полосы по 8-связности: два и больше - среднее может лечь мимо рисунка (лук: два плеча)
    pts = set(zip(bx.tolist(), by.tolist()))
    parts = 0
    while pts:
        parts += 1
        stack = [pts.pop()]
        while stack:
            px, py = stack.pop()
            for q in ((px + a, py + b) for a in (-1, 0, 1) for b in (-1, 0, 1)):
                if q in pts:
                    pts.remove(q)
                    stack.append(q)
    on = bool(idx[min(max(tip[1], 0), idx.shape[0] - 1), min(max(tip[0], 0), idx.shape[1] - 1)] or
              idx[min(max(tip[1] - 1, 0), idx.shape[0] - 1), min(max(tip[0] - 1, 0), idx.shape[1] - 1)])
    return {"axis_cos": round(float(cos), 2), "cross": bool(cos < 0.5), "spread": round(spread, 2),
            "wide": bool(spread > 1.5), "parts": parts, "split": parts > 1, "on_drawing": on}


def frame_no(rul):
    return rul + OFFSET if rul >= SHARED else rul


def load_users():
    """кадр HANDOB -> (типы#k, сколько ещё не показано) из переписи; список users там обрезан до 20."""
    out = {}
    with open(HANDOB_FRAMES, encoding=ENC, newline="") as f:
        rd = csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
        head = next(rd)
        for r in rd:
            d = dict(zip(head, r))
            u = d.get("users", "")
            more = 0
            if "]+" in u:
                u, more = u.rsplit("+", 1)
                more = int(more)
            out[int(d["frame"])] = (wac.jv(u.replace("\\\"", "\"")) or [], more)
    return out


def handob_img(sheet, pal, n):
    cols = sheet.shape[1] // FW
    r, c = divmod(n, cols)
    if (r + 1) * FH > sheet.shape[0]:
        return None
    idx = sheet[r * FH:(r + 1) * FH, c * FW:(c + 1) * FW]
    return idx


def rgba(idx, pal):
    return Image.fromarray(np.dstack([pal[idx], np.where(idx == 0, 0, 255).astype(np.uint8)]), "RGBA")


def cell(idx, pal, tip=None, d=None):
    im = wac.on_bg(rgba(idx, pal), S)
    if tip is None:
        return im
    tx, ty, band, (sx, sy) = tip
    dr = ImageDraw.Draw(im, "RGBA")
    # пиксели полосы, которые усредняет noteTip - жёлтая рамка
    for y, x in zip(*np.nonzero(band)):
        dr.rectangle([x * S, y * S, x * S + S - 1, y * S + S - 1], outline=(255, 220, 0, 255))
    # направление взгляда юнита d из центра кадра
    cx, cy = FW * S / 2, FH * S / 2
    L = 22 / math.hypot(sx, sy)
    dr.line([cx, cy, cx + sx * L, cy + sy * L], fill=(80, 200, 255, 200), width=2)
    dr.ellipse([cx + sx * L - 3, cy + sy * L - 3, cx + sx * L + 3, cy + sy * L + 3], fill=(80, 200, 255, 200))
    # точка вспышки: tipX, tipY - угол пикселя (среднее + 0.5, округлено)
    px, py = tx * S, ty * S
    dr.line([px - 9, py, px + 9, py], fill=(255, 40, 40, 255), width=2)
    dr.line([px, py - 9, px, py + 9], fill=(255, 40, 40, 255), width=2)
    return im


def build(row, items, users, sheet, pal, bsheet, bpal, fonts):
    F, FB, FS = fonts
    t = row["type"]
    it = items.get(t, {})
    rul = it.get("handSprite")
    two = bool(it.get("twoHanded"))
    info = {"master": row["master"], "type": t, "handSprite_rul": rul, "twoHanded": two, "frames": [], "shots": [],
            "problems": []}
    if rul is None:
        rul = 120     # RuleItem: _handSprite(120) по умолчанию
        info["problems"].append("handSprite не задан - по умолчанию движка 120")
        info["handSprite_rul"] = "120 (default)"
    pad, gap = 10, 8
    cw, ch = FW * S, FH * S
    big, _ = wac.frame_img(bsheet, bpal, int(row["frame"]))
    big = wac.on_bg(big, 4)
    W = pad + big.width + 16 + 8 * (cw + gap) + pad
    ammo_p = os.path.join(AMMO, "%s.%s.png" % (row["master"], t))
    ammo = Image.open(ammo_p).convert("RGB") if os.path.exists(ammo_p) else None
    H = 34 + 2 * (ch + 40) + 12 + (ammo.height + 8 if ammo else 0)
    W = max(W, ammo.width + 2 * pad if ammo else 0)
    card = Image.new("RGB", (W, H), (24, 24, 27))
    dr = ImageDraw.Draw(card)
    if not isinstance(rul, int):
        info["problems"].append("нет handSprite")
        dr.text((pad, 8), "%s  %s  - нет handSprite в рулсете" % (row["master"], t), font=FB, fill=(255, 120, 120))
        return card, info
    base = frame_no(rul)
    dr.text((pad, 8), "%s  %s  -  %s   HANDOB handSprite %d -> кадры %d..%d, %s" % (
        row["master"], t, row["ru"], rul, base, base + 7, "двуручное" if two else "одноручное"),
        font=FB, fill=(235, 235, 235))
    card.paste(big, (pad, 34))
    dr.text((pad, 34 + big.height + 4), "BIGOBS %s" % row["frame"], font=FS, fill=(200, 200, 120))
    x0 = pad + big.width + 16
    y1, y2 = 34, 34 + ch + 40
    for k in range(8):
        n = base + k
        idx = handob_img(sheet, pal, n)
        us, more = users.get(n, ([], 0))
        mine = "%s#%d" % (t, k) in us
        known = mine or (more and not us)
        rec = {"k": k, "frame": n, "empty": idx is None or not idx.any(),
               "census_user": True if mine else ("?" if more else False)}
        info["frames"].append(rec)
        x = x0 + k * (cw + gap)
        if rec["empty"]:
            info["problems"].append("кадр %d пуст в выгрузке" % n)
            dr.rectangle([x, y1, x + cw - 1, y1 + ch - 1], outline=(255, 90, 90))
            dr.text((x + 6, y1 + 6), "пусто", font=FS, fill=(255, 90, 90))
        else:
            card.paste(cell(idx, pal), (x, y1))
        if not mine and not more:
            info["problems"].append("кадр %d: в переписи нет %s#%d" % (n, t, k))
        col = (200, 200, 200) if mine else ((200, 200, 120) if more else (255, 120, 120))
        dr.text((x, y1 + ch + 3), "%d (+%d)%s" % (n, k, "" if mine else (" ?" if more else " не наш")),
                font=FS, fill=col)
        # выстрел: юнит смотрит в d=k, целится; кадр (d+2)%8 у двуручного
        d = k
        kk = (d + 2) % 8 if two else d
        idx2 = handob_img(sheet, pal, base + kk)
        tip = note_tip(idx2, d) if idx2 is not None else None
        if tip is None:
            dr.text((x + 6, y2 + 6), "нет кадра", font=FS, fill=(255, 90, 90))
            info["shots"].append({"d": d, "frame": base + kk, "tip": None})
        else:
            card.paste(cell(idx2, pal, tip, d), (x, y2))
            info["shots"].append({"d": d, "frame": base + kk, "tipX": tip[0], "tipY": tip[1],
                                  "band_px": int(tip[2].sum()), **shape_flags(idx2, tip)})
            dr.text((x, y2 + ch + 3), "взгляд %d: +%d  точка %d,%d" % (d, kk, tip[0], tip[1]),
                    font=FS, fill=(200, 200, 200))
        _ = known
    dr.text((x0, y2 - 18), "выстрел (целится): синяя - взгляд юнита, жёлтые - пиксели полосы noteTip, красный крест - точка вспышки",
            font=FS, fill=(150, 200, 255))
    if ammo:
        card.paste(ammo, (pad, y2 + ch + 28))
    return card, info


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="мастера через запятую, W-053")
    a = ap.parse_args()
    os.chdir(ROOT)
    with open(LIST, encoding=ENC, newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))
    if a.only:
        want = set(a.only.split(","))
        rows = [r for r in rows if r["master"] in want]
    items, _ = wac.load_rules()
    users = load_users()
    sh = Image.open(HANDOB)
    bs = Image.open(wac.EXPORT)
    if sh.mode != "P" or bs.mode != "P":
        raise SystemExit("выгрузка не в индексах: %s %s" % (sh.mode, bs.mode))
    pal = np.asarray(sh.getpalette()[:768], np.uint8).reshape(-1, 3)
    bpal = np.asarray(bs.getpalette()[:768], np.uint8).reshape(-1, 3)
    fonts = (ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 15), ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 17),
             ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 13))
    os.makedirs(OUT, exist_ok=True)
    infos, pngs = [], []
    sheet, bsheet = np.asarray(sh), np.asarray(bs)
    for r in rows:
        card, info = build(r, items, users, sheet, pal, bsheet, bpal, fonts)
        p = os.path.join(OUT, "%s.%s.png" % (r["master"], r["type"]))
        card.save(p)
        pngs.append(p)
        infos.append(info)
        if info["problems"]:
            print("  %s %s: %s" % (r["master"], r["type"], "; ".join(info["problems"][:4])))
    tag = "_only" if a.only else ""
    with open(os.path.join(OUT, "handob%s.json" % tag), "w", encoding=ENC) as f:
        json.dump(infos, f, ensure_ascii=False, indent=1)
    with open(os.path.join(OUT, "tips%s.tsv" % tag), "w", encoding=ENC, newline="") as f:
        w = csv.writer(f, delimiter="\t")
        cols = ("tipX", "tipY", "band_px", "axis_cos", "cross", "spread", "wide", "parts", "split", "on_drawing")
        w.writerow(["master", "type", "twoHanded", "look_d", "frame"] + list(cols))
        for i in infos:
            for s in i["shots"]:
                w.writerow([i["master"], i["type"], i["twoHanded"], s["d"], s["frame"]] + [s.get(k, "") for k in cols])
    flag = {}
    for i in infos:
        n = [sum(1 for s in i["shots"] if s.get(k)) for k in ("cross", "wide", "split")]
        if any(n):
            flag[i["master"]] = (i["type"], *n)
    print("подсказки глазу (из 8 направлений): поперёк взгляда / широкий передний край / полоса из кусков")
    for m, (t, nc, nw, ns) in sorted(flag.items()):
        print("  %s %-24s %d / %d / %d" % (m, t, nc, nw, ns))
    print("итог подсказок: поперёк %d предметов, широкий край %d, полоса из кусков %d" % tuple(
        sum(1 for v in flag.values() if v[j]) for j in (1, 2, 3)))
    if not a.only:
        wac.sheets(pngs, OUT)
    bad = sum(1 for i in infos if i["problems"])
    print("итог: карточек %d, с замечаниями %d, двуручных %d" % (len(infos), bad, sum(i["twoHanded"] for i in infos)))


if __name__ == "__main__":
    main()
