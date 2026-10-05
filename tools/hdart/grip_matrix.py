"""Контракт хвата: одни руки на вид хвата, оружие - отдельным слоем. Проверочная матрица по всему оружию Пираток.

Движок (UnitSprite::drawRoutine0) берёт кадры рук только по виду хвата, а не по предмету:
  ONE          одноручное в правой:   правая rarm1H 232+d, левая larmStand 0+d,  кадр handSprite+d,        сдвиг (0,0)
  TWO_STAND    двуручное, стоит:      правая rarm2H 248+d, левая larm2H 240+d,   кадр handSprite+d,        сдвиг (0,0)
  TWO_AIM      двуручное, прицел:     правая rarmShoot 256+d, левая 240+d,       кадр handSprite+(d+2)%8,  offX/offY[d]
  LEFT_ONE     одноручное в левой:    левая 240+d,                               кадр handSprite+d,        offX2/offY2[d]
  LEFT_TWO_AIM двуручное в левой, прицел: правая 256+d, левая 240+d,             кадр handSprite+(d+2)%8,  offX6/offY6[d]
На колене и при ходьбе руки и предмет сдвигаются одинаково (offYKneel, YoffWalk) - взаимное положение то же.
Одноручное при прицеле: кадр и руки те же, что стоя. Двуручное в левой стоя - те же кадры и сдвиг, что TWO_STAND.

Точка кисти - центр пикселей кожи (индексы 96..111) в классическом кадре руки GOV_1 (агент). Для каждого
handSprite огнестрела и холодного (census/items/items.tsv, свой кадр) меряется касание кисти и оружия:
  touch - наименьшее расстояние от пикселя кисти до пикселя оружия (база), 0 - кисть лежит на оружии;
  держит <= 1, рядом <= 3, мимо > 3. Кисть, которую закрыли слои поверх (порядок слоёв по направлению), - «не видна».

Касание - предварительный фильтр: чей пиксель под кистью (рукоять, магазин, ствол), он не знает.

  py -3.13 tools/hdart/grip_matrix.py            -> art/units/grip-contract/: grip_matrix.tsv, grip_summary.tsv,
                                                    compare_d2.png (одни руки x разное оружие), all_d2_NN.png,
                                                    aim_support.png/.tsv (цевьё при прицеле), hd_weapons.tsv
  py -3.13 tools/hdart/grip_matrix.py --contexts -> процедуры 0, 10, 1, 6, 4 x все случаи двух рук (emulate):
                                                    grip_contexts.tsv (что рисует движок, кто чем держит),
                                                    grip_routines.tsv, grip_routines_summary.tsv (фильтр касания),
                                                    grip_r4_drift.tsv (routine 4: уход двуручного в прицеле)
Разбор и таблица видов хвата - docs/research/grip-contract.md.
HD-кадры: руки пилота art/units/pilot-agent/full/pose/pack (без 242.v1 - она подогнана под AK, отдельная колонка),
оружие - HANDOB.PCK пилота (только AK 1352+). Чего нет в HD - классика x4 nearest с красной подписью «HD нет».
Видеокарта не нужна."""
import csv
import json
import os
import sys
from collections import Counter, defaultdict

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GOV = os.path.join(ROOT, "Пиратки", "Dioxine_XPiratez", "user", "mods", "Piratez", "Resources", "Sprites", "GOV_1.png")
HANDOB = os.path.join(ROOT, "census", "items", "export", "exp_piratez", "HANDOB.PCK.png")
ITEMS = os.path.join(ROOT, "census", "items", "items.tsv")
WEAP = os.path.join(ROOT, "docs", "research", "piratez-weapons.tsv")
HD = os.path.join(ROOT, "art", "units", "pilot-agent", "full", "pose", "pack")
OUT = os.path.join(ROOT, "art", "units", "grip-contract")
FONT = "C:/Windows/Fonts/arial.ttf"
ENC = "utf-8-sig"
SKIN = range(96, 112)
K = 4

# UnitSprite::drawRoutine0, routine 0
OFF = {"ONE": ([0] * 8, [0] * 8), "TWO_STAND": ([0] * 8, [0] * 8),
       "TWO_AIM": ([8, 10, 7, 4, -9, -11, -7, -3], [-6, -3, 0, 2, 0, -4, -7, -9]),
       "LEFT_ONE": ([-8, 3, 5, 12, 6, -1, -5, -13], [1, -4, -2, 0, 3, 3, 5, 0]),
       "LEFT_TWO_AIM": ([0, 6, 6, 12, -4, -5, -5, -13], [-4, -4, -1, 0, 5, 0, 1, 0])}
# (левая рука, правая рука, сдвиг кадра предмета, рука предмета, какие кисти держат)
CASES = {"ONE": (0, 232, 0, "R", ("near",)),
         "TWO_STAND": (240, 248, 0, "R", ("near", "far")),
         "TWO_AIM": (240, 256, 2, "R", ("near", "far")),
         "LEFT_ONE": (240, 8, 0, "L", ("far",)),
         "LEFT_TWO_AIM": (240, 256, 2, "L", ("near", "far"))}
ONE_H = ("ONE", "LEFT_ONE")
TWO_H = ("TWO_STAND", "TWO_AIM", "LEFT_TWO_AIM")


def order(d, aiming, two):
    """Порядок слоёв routine 0 (UnitSprite.cpp, switch (unitDir)); первое - самое дальнее."""
    alt = (not aiming) and two
    return {0: "iR iL la lg to ra", 1: "la lg iL to iR ra", 2: "la lg to iL iR ra",
            3: "lg to la iR iL ra" if alt else "lg to la ra iR iL", 4: "lg ra to la iR iL",
            5: "ra lg to la iR iL" if alt else "ra lg iR iL to la", 6: "ra iR iL lg to la",
            7: "ra iR iL la lg to" if alt else "iR iL la ra lg to"}[d].split()


def sheet(path, cols=16, w=32, h=40):
    im = Image.open(path)
    pal = np.array(im.getpalette()[:768], np.uint8).reshape(256, 3)
    idx = np.asarray(im)

    def frame(n):
        r, c = divmod(n, cols)
        return idx[r * h:(r + 1) * h, c * w:(c + 1) * w]
    return frame, pal


gov, gpal = sheet(GOV)
hob, hpal = sheet(HANDOB)


def shifted(m, dx, dy):
    o = np.zeros_like(m)
    h, w = m.shape
    ys, xs = slice(max(dy, 0), min(h, h + dy)), slice(max(dx, 0), min(w, w + dx))
    yd, xd = slice(max(-dy, 0), min(h, h - dy)), slice(max(-dx, 0), min(w, w - dx))
    o[ys, xs] = m[yd, xd]
    return o


def touch(hand, weap):
    """Наименьшее расстояние между пикселем кисти и пикселем оружия (база)."""
    hy, hx = np.nonzero(hand)
    wy, wx = np.nonzero(weap)
    if not len(hy) or not len(wy):
        return None
    d = np.sqrt((hy[:, None] - wy[None, :]) ** 2 + (hx[:, None] - wx[None, :]) ** 2)
    return float(d.min())


def verdict(t, vis):
    if t is None:
        return "нет кисти"
    v = "держит" if t <= 1.0 else ("рядом" if t <= 3.0 else "мимо")
    return v if vis else v + ", не видна"


def measure(hs, case, d, legs=16):
    la, ra, rot, side, who = CASES[case]
    f_item = hob(hs + (d + rot) % 8)
    ox, oy = OFF[case][0][d], OFF[case][1][d]
    weap = shifted(f_item > 0, ox, oy)
    layers = {"la": gov(la + d) > 0, "ra": gov(ra + d) > 0, "lg": gov(legs + d) > 0, "to": gov(32 + d) > 0,
              "iR": weap if side == "R" else np.zeros_like(weap), "iL": weap if side == "L" else np.zeros_like(weap)}
    seq = order(d, case.endswith("AIM"), case in TWO_H)
    res = {}
    for h in who:
        key, fr = ("ra", ra) if h == "near" else ("la", la)
        hand = np.isin(gov(fr + d), SKIN)
        above = np.zeros_like(hand)
        for name in seq[seq.index(key) + 1:]:
            above |= layers[name]
        vis = bool((hand & ~above).sum() >= max(1, hand.sum() // 3))
        t = touch(hand, weap)
        res[h] = (t, vis, verdict(t, vis))
    return res


def load_items():
    cls = {}
    with open(WEAP, encoding=ENC) as f:
        for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            cls[r["оружие_id"]] = (r["класс"], r["класс_название"], r["ёмкость"], r["оружие"])
    by = defaultdict(list)
    with open(ITEMS, encoding=ENC) as f:
        for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            if r["class"] in ("firearm", "melee") and r["hand_default"] == "False" and r["hand_frames"] == "8":
                by[int(r["handSprite"])].append(r)
    return by, cls


def rgba_classic(frame, pal):
    rgb = pal[frame].astype(np.float32)
    a = (frame > 0).astype(np.float32)
    return np.repeat(np.repeat(rgb, K, 0), K, 1), np.repeat(np.repeat(a, K, 0), K, 1)


def ld(p):
    a = np.asarray(Image.open(p).convert("RGBA")).astype(np.float32)
    return a[..., :3], a[..., 3] / 255.0


def hd_or(set_, n, frame, pal):
    p = os.path.join(HD, set_, "%s.png" % n)
    if os.path.exists(p):
        return ld(p), True
    return rgba_classic(frame, pal), False


def place(l, dx, dy):
    r, a = l
    return (np.roll(np.roll(r, dy * K, 0), dx * K, 1), np.roll(np.roll(a, dy * K, 0), dx * K, 1))


def stack(layers):
    r = np.zeros((40 * K, 32 * K, 3), np.float32)
    a = np.zeros((40 * K, 32 * K), np.float32)
    for lr, la in layers:
        r = lr * la[..., None] + r * (1 - la[..., None])
        a = la + a * (1 - la)
    return r, a


def floor():
    return np.zeros((40 * K, 32 * K, 3), np.float32) + (np.indices((40 * K, 32 * K)).sum(0) // 8 % 2)[..., None] * 10 + 58


def pic(layers):
    r, a = stack(layers)
    return Image.fromarray(np.clip(r * a[..., None] + floor() * (1 - a[..., None]), 0, 255).astype(np.uint8))


def compose(hs, case, d, hd, far_v1=False):
    """Кадр юнита routine 0. hd - руки и тело пилота там, где они есть; оружие - HD пака пилота или классика."""
    la, ra, rot, side, _ = CASES[case]
    miss = []

    def body(n):
        if not hd:
            return rgba_classic(gov(n), gpal)
        name = "242.v1" if (far_v1 and n == 242) else n
        l, ok = hd_or("GOV_1.PCK", name, gov(n), gpal)
        if not ok:
            miss.append(str(n))
        return l
    fi = hs + (d + rot) % 8
    if hd:
        item, ok = hd_or("HANDOB.PCK", fi, hob(fi), hpal)
        if not ok:
            miss.append("оружие %d" % fi)
    else:
        item = rgba_classic(hob(fi), hpal)
    item = place(item, OFF[case][0][d], OFF[case][1][d])
    L = {"la": body(la + d), "ra": body(ra + d), "lg": body(16 + d), "to": body(32 + d)}
    L["iR" if side == "R" else "iL"] = item
    seq = [n for n in order(d, case.endswith("AIM"), case in TWO_H) if n in L]
    return pic([L[n] for n in seq]), miss


def hand_marks(img, case, d):
    la, ra, _, _, who = CASES[case]
    dr = ImageDraw.Draw(img)
    for h in who:
        fr = ra if h == "near" else la
        ys, xs = np.nonzero(np.isin(gov(fr + d), SKIN))
        if len(xs):
            cx, cy = (xs.mean() + 0.5) * K, (ys.mean() + 0.5) * K
            dr.line([(cx - 5, cy), (cx + 5, cy)], fill=(0, 230, 255))
            dr.line([(cx, cy - 5), (cx, cy + 5)], fill=(0, 230, 255))
    return img


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(OUT, exist_ok=True)
    by, cls = load_items()
    rows, per = [], {}
    for hs in sorted(by):
        its = by[hs]
        two = Counter(r["twoHanded"] for r in its).most_common(1)[0][0] == "True"
        mixed = len({r["twoHanded"] for r in its}) > 1
        c = Counter(cls.get(r["type"], ("?", "не в классах", "", ""))[1] for r in its).most_common(1)[0][0]
        cases = TWO_H if two else ONE_H
        per[hs] = {"two": two, "class": c, "items": its}
        for case in cases:
            for d in range(8):
                for h, (t, vis, v) in measure(hs, case, d).items():
                    rows.append({"handSprite": hs, "class": c, "twoHanded": two, "mixed": mixed, "case": case, "dir": d,
                                 "hand": h, "touch": "" if t is None else "%.2f" % t, "visible": vis, "verdict": v,
                                 "items": len(its), "example": its[0]["type"]})
    with open(os.path.join(OUT, "grip_matrix.tsv"), "w", encoding=ENC, newline="") as f:
        w = csv.DictWriter(f, list(rows[0]), delimiter="\t")
        w.writeheader()
        w.writerows(rows)
    # сводка: вид хвата x направление x кисть - сколько кадров держит/рядом/мимо, только видимые кисти
    summ = defaultdict(Counter)
    for r in rows:
        summ[(r["case"], r["dir"], r["hand"])][r["verdict"]] += 1
    keys = ["держит", "рядом", "мимо", "держит, не видна", "рядом, не видна", "мимо, не видна", "нет кисти"]
    with open(os.path.join(OUT, "grip_summary.tsv"), "w", encoding=ENC, newline="") as f:
        f.write("case\tdir\thand\t" + "\t".join(keys) + "\n")
        for k in sorted(summ):
            f.write("%s\t%d\t%s\t" % k + "\t".join(str(summ[k][x]) for x in keys) + "\n")
    print("кадров HANDOB:", len(per), "(двуручных %d, одноручных %d)" % (sum(p["two"] for p in per.values()),
                                                                         sum(not p["two"] for p in per.values())))
    print("предметов:", sum(len(p["items"]) for p in per.values()))
    for case in ("ONE", "TWO_STAND", "TWO_AIM", "LEFT_ONE"):
        for h in ("near", "far"):
            c = summ.get((case, 2, h))
            if c:
                print("d2 %-10s %-4s" % (case, h), dict(c))
    hd_check(per)
    support_heat(per)
    sel = pick(per, rows, cls)
    json.dump(sel, open(os.path.join(OUT, "compare_pick.json"), "w", encoding=ENC), ensure_ascii=False, indent=1)
    compare_sheet(sel, per, 2)
    all_pages(per, rows, 2)


# Представители по конструкциям (предмет -> его handSprite из переписи); AK - единственный с HD-кадрами
def support_heat(per):
    """Где цевьё при прицеле. Движок рисует опорную руку 240+d и стоя, и при прицеле (TWO_AIM), а оружие при прицеле -
    кадр (d+2)%8 со сдвигом offX/offY. Для каждого направления: доля двуручных стволов, покрывающих пиксель (база);
    точка кисти 240 стоя, её покрытие; лучшая точка опоры при прицеле - покрытие >= 0.8 ближе всего к кисти 240,
    не ближе 3 пикс к кисти 256 (иначе это та же рука). Пишет aim_support.tsv и aim_support.png."""
    two = [hs for hs, p in per.items() if p["two"]]
    out, tiles = [], []
    for d in range(8):
        acc = np.zeros((40, 32), np.float32)
        acc_st = np.zeros((40, 32), np.float32)
        for hs in two:
            acc += shifted(hob(hs + (d + 2) % 8) > 0, OFF["TWO_AIM"][0][d], OFF["TWO_AIM"][1][d])
            acc_st += hob(hs + d) > 0
        acc /= len(two)
        acc_st /= len(two)
        def pt(fr):
            ys, xs = np.nonzero(np.isin(gov(fr + d), SKIN))
            return (xs.mean(), ys.mean()) if len(xs) else None
        far, near = pt(240), pt(256)
        cov_far = acc[int(round(far[1])), int(round(far[0]))] if far else 0.0
        cov_far_st = acc_st[int(round(far[1])), int(round(far[0]))] if far else 0.0
        ys, xs = np.nonzero(acc >= 0.8)
        best = None
        for y, x in zip(ys, xs):
            if near and np.hypot(x - near[0], y - near[1]) < 3:
                continue
            dist = np.hypot(x - far[0], y - far[1]) if far else 0
            if best is None or dist < best[2]:
                best = (int(x), int(y), float(dist), float(acc[y, x]))
        out.append({"dir": d, "far240_x": "%.1f" % far[0], "far240_y": "%.1f" % far[1],
                    "cover_stand": "%.2f" % cov_far_st, "cover_aim": "%.2f" % cov_far,
                    "near256_x": "%.1f" % near[0] if near else "", "near256_y": "%.1f" % near[1] if near else "",
                    "aim_support_x": best[0] if best else "", "aim_support_y": best[1] if best else "",
                    "shift_px": "%.1f" % best[2] if best else "", "support_cover": "%.2f" % best[3] if best else ""})
        S = 8
        rgb = np.zeros((40, 32, 3), np.uint8)
        rgb[..., 1] = (acc * 200).astype(np.uint8)
        rgb[..., 0] = (acc_st * 120).astype(np.uint8)
        im = Image.fromarray(rgb).resize((32 * S, 40 * S), Image.NEAREST)
        dr = ImageDraw.Draw(im)
        def cross(p, c):
            cx, cy = (p[0] + 0.5) * S, (p[1] + 0.5) * S
            dr.line([(cx - 8, cy), (cx + 8, cy)], fill=c, width=2)
            dr.line([(cx, cy - 8), (cx, cy + 8)], fill=c, width=2)
        if far:
            cross(far, (0, 230, 255))
        if near:
            cross(near, (255, 255, 255))
        if best:
            cross(best, (255, 200, 0))
        dr.text((4, 4), "dir %d" % d, fill=(255, 255, 255), font=ImageFont.truetype(FONT, 16))
        tiles.append(im)
    sheet_ = Image.new("RGB", (8 * (32 * 8 + 6), 40 * 8 + 60), (20, 20, 20))
    for i, t in enumerate(tiles):
        sheet_.paste(t, (i * (32 * 8 + 6), 0))
    ImageDraw.Draw(sheet_).text((4, 40 * 8 + 8), "зелёное - доля двуручных стволов при прицеле, красное - стоя; голубой крест - кисть 240 (общая стоя и в прицеле), "
                                "белый - кисть 256, жёлтый - общая точка цевья при прицеле (покрытие >= 0.8)", fill=(220, 220, 220), font=ImageFont.truetype(FONT, 13))
    sheet_.save(os.path.join(OUT, "aim_support.png"))
    with open(os.path.join(OUT, "aim_support.tsv"), "w", encoding=ENC, newline="") as f:
        w = csv.DictWriter(f, list(out[0]), delimiter="\t")
        w.writeheader()
        w.writerows(out)
    for r in out:
        print("опора прицела", r)


def hd_check(per):
    """HD-кадры оружия против контракта: силуэт x4 -> база (доля альфы 4x4 > 0.5) против классики того же кадра,
    касание точек кистей классики, сдвиг средней линии по столбцам (dy > 0 - HD ниже классики)."""
    out = []
    two_by_hs = {hs: p["two"] for hs, p in per.items()}
    d0 = os.path.join(HD, "HANDOB.PCK")
    for fn in sorted(os.listdir(d0)) if os.path.isdir(d0) else []:
        if not fn[:-4].isdigit() or not fn.endswith(".png"):
            continue
        fi = int(fn[:-4])
        _, a = ld(os.path.join(d0, fn))
        hdm = a.reshape(40, K, 32, K).mean((1, 3)) > 0.5
        clm = hob(fi) > 0
        iou = (hdm & clm).sum() / max(1, (hdm | clm).sum())
        cols = [x for x in range(32) if hdm[:, x].any() and clm[:, x].any()]
        dy = np.mean([np.nonzero(hdm[:, x])[0].mean() - np.nonzero(clm[:, x])[0].mean() for x in cols]) if cols else 0.0
        hs = fi - fi % 8                     # handSprite кратен 8: кадр = handSprite + направление
        two = hs in two_by_hs and two_by_hs[hs]
        for case, (la, ra, rot, side, who) in CASES.items():
            if side != "R" or (case in TWO_H) != two:
                continue
            for d in range(8):
                if (d + rot) % 8 != fi % 8:
                    continue
                ox, oy = OFF[case][0][d], OFF[case][1][d]
                tt = {}
                for h in who:
                    hand = np.isin(gov((ra if h == "near" else la) + d), SKIN)
                    tt[h] = (touch(hand, shifted(clm, ox, oy)), touch(hand, shifted(hdm, ox, oy)))
                out.append({"frame": fi, "case": case, "dir": d, "iou_base": "%.3f" % iou, "line_dy": "%+.2f" % dy,
                            **{"%s_classic" % h: "%.2f" % v[0] for h, v in tt.items()},
                            **{"%s_hd" % h: "%.2f" % v[1] for h, v in tt.items()}})
    if out:
        with open(os.path.join(OUT, "hd_weapons.tsv"), "w", encoding=ENC, newline="") as f:
            w = csv.DictWriter(f, list(out[0]), delimiter="\t")
            w.writeheader()
            w.writerows(out)
    for r in out:
        print("HD оружие", r)


# --- Процедуры 1, 4, 6, 10 и две занятые руки -------------------------------------------------------------
# Перенос выбора кадров из UnitSprite.cpp: sortRifles (:1536), drawRoutine0 (:324, routine 10 там же),
# drawRoutine1 (:687), drawRoutine4 (:959), drawRoutine6 (:1112). Только стоя и в прицеле: ходьба и колено
# сдвигают руки и предмет на одну величину везде, кроме routine 6 (xoffWalk у рук, у предмета нет).
SPR = os.path.join(ROOT, "Пиратки", "Dioxine_XPiratez", "user", "mods", "Piratez", "Resources", "Sprites")
_X2 = ([-8, 3, 5, 12, 6, -1, -5, -13], [1, -4, -2, 0, 3, 3, 5, 0])
_X6 = ([0, 6, 6, 12, -4, -5, -5, -13], [-4, -4, -1, 0, 5, 0, 1, 0])
_Z = ([0] * 8, [0] * 8)
ROUT = {
    0: dict(sheet="GOV_1", la=0, ra=8, r1H=232, l2H=240, r2H=248, rShoot=256, torso=32, legs=16,
            aim=OFF["TWO_AIM"], l1=_X2, l2aim=_X6, r1=_Z, r2=_Z, r1H_arm="r1H",
            order={0: "iR iL la lg to ra", 1: "la lg iL to iR ra", 2: "la lg to iL iR ra", 3: ("lg to la iR iL ra", "lg to la ra iR iL"),
                   4: "lg ra to la iR iL", 5: ("ra lg to la iR iL", "ra lg iR iL to la"), 6: "ra iR iL lg to la",
                   7: ("ra iR iL la lg to", "iR iL la ra lg to")}),
    10: dict(sheet="MRC_4", la=0, ra=8, r1H=232, l2H=240, r2H=248, rShoot=256, torso=32, legs=16,
             aim=OFF["TWO_AIM"], l1=([-8, 2, 7, 14, 7, -2, -4, -8], [-3, -3, -1, 0, 3, 3, 0, 1]),
             l2aim=([0, 6, 8, 12, 2, -5, -5, -13], [-4, -6, -1, 0, 3, 0, 1, 0]),
             r1=([-1, 1, 1, 2, 0, -1, 0, 0], [1, -1, -1, -1, -1, -1, -3, 0]),
             r2=([0, 0, 2, 2, 0, 0, 0, 0], [-3, -3, -1, -1, -1, -3, -3, -2]), r1H_arm="r2H", order=None),
    1: dict(sheet="COS_7", la=8, ra=0, r1H=91, l2H=67, r2H=75, rShoot=83, torso=16, legs=None,
            aim=OFF["TWO_AIM"], l1=([-8, 3, 7, 13, 6, -3, -5, -13], [1, -4, -1, 0, 3, 3, 5, 0]), l2aim=_X6, r1=_Z, r2=_Z,
            r1H_arm="r1H",
            order={0: "iR iL la to ra", 1: "la to ra iR iL", 2: "la to ra iR iL", 3: "to la ra iR iL", 4: "to la ra iR iL",
                   5: "ra to la iR iL", 6: "ra iR iL to la", 7: "ra iR iL la to"}),
    6: dict(sheet="REB_4", la=0, ra=8, r1H=99, l2H=107, r2H=115, rShoot=123, torso=24, legs=16,
            aim=([8, 10, 5, 2, -8, -10, -5, -2], [-6, -3, 0, 0, 2, -3, -7, -9]),
            l1=([-8, 2, 7, 13, 7, 0, -3, -15], [1, -4, -2, 0, 3, 3, 5, 0]), l2aim=_X6,
            r1=([0] * 8, [2, 1, 1, 0, 0, 0, 0, 0]), r2=_Z, r1H_arm="r1H",
            order={0: "iR iL la lg to ra", 1: "la lg iL to iR ra", 2: "la lg to ra iR iL", 3: "lg to la ra iR iL",
                   4: "ra lg to la iR iL", 5: "ra lg to la iR iL", 6: "ra lg iR iL to la", 7: "iR iL la ra lg to"}),
    4: dict(sheet="PIR_360", body=0, aim=OFF["TWO_AIM"], l1=_X2, l2aim=_X6, r1=_Z, r2=_Z,
            order={0: "iL iR to", 1: "iL to iR", 2: "to iL iR", 3: "to iR iL", 4: "to iR iL", 5: "iR to iL",
                   6: "iR to iL", 7: "iR iL to"}),
}
ROUT[10]["order"] = ROUT[0]["order"]
ROUT_WHO = {0: "люди-солдаты, 724 брони (GOV_1)", 10: "мутоны и громилы, 10 бронь (MRC_4)",
            1: "плавуны, жрецы, 7 бронь (COS_7)", 6: "змеелюди и ламии, 27 бронь (REB_4)",
            4: "цельный кадр без рук, 75 бронь (PIR_360)"}
# Случаи «что в руках»: (правая, левая) - None / "1" одноручное / "2" двуручное
HELD = [("1", None), ("2", None), (None, "1"), (None, "2"), ("1", "1"), ("2", "1"), ("1", "2"), ("2", "2")]


def emulate(r, R, L, aiming):
    """Что рисует процедура r: кадры рук, кадр и сдвиг каждого предмета, кто какой рукой держит.
    Возвращает dict: la/ra - база кадра руки (None у routine 4), items {"iR"/"iL": (kind, rot, offx[8], offy[8], слот)},
    hold {"ra"/"la": "iR"/"iL"/None}, alt - порядок слоёв «двуручное и не целится», drop - что движок не рисует."""
    P = ROUT[r]
    drop = []
    # sortRifles
    if R == "2":
        if L == "2":
            drop.append("левое двуручное (рисуется одно, активное - здесь правое)")
            L = None
        elif L and not aiming:
            drop.append("левое одноручное (двуручное в правой, не целится)")
            L = None
    elif L == "2" and R and not aiming:
        drop.append("правое одноручное (двуручное в левой, не целится)")
        R = None
    la, ra = P.get("la"), P.get("ra")
    items, hold = {}, {"ra": None, "la": None}
    if R:
        if aiming and R == "2":
            items["iR"] = (R, 2, *P["aim"], "R")
        else:
            items["iR"] = (R, 0, *(P["r2"] if R == "2" else P["r1"]), "R")
        if r != 4:
            if R == "2":
                la = P["l2H"]
                ra = P["rShoot"] if aiming else P["r2H"]
                hold.update(ra="iR", la="iR")
            else:
                ra = P[P["r1H_arm"]]
                hold["ra"] = "iR"
    if L:
        if L == "1":
            items["iL"] = (L, 0, *P["l1"], "L")
        else:
            items["iL"] = (L, 0, *_Z, "L")
        if r != 4:
            la = P["l2H"]
            hold["la"] = "iL"
            if L == "2":
                ra = P["r2H"]
                if hold["ra"] is None:
                    hold["ra"] = "iL"
        if aiming and L == "2":
            items["iL"] = (L, 2, *P["l2aim"], "L")
            if r != 4:
                ra = P["rShoot"]
    if r == 4:
        la = ra = None
    two = (R == "2") or (L == "2")
    return dict(la=la, ra=ra, items=items, hold=hold, alt=(not aiming) and two, drop=drop, R=R, L=L)


def layer_order(r, d, alt):
    o = ROUT[r]["order"][d]
    if isinstance(o, tuple):
        o = o[0] if alt else o[1]
    return o.split()


_sheets = {}


def body_sheet(r):
    n = ROUT[r]["sheet"]
    if n not in _sheets:
        p = GOV if n == "GOV_1" else os.path.join(SPR, n + ".png")
        im = Image.open(p)
        _sheets[n] = sheet(p, cols=im.size[0] // 32)
    return _sheets[n][0]


def arm_end(m):
    """Дальний конец руки: плечо - середина трёх верхних строк руки, конец - точка руки, дальняя от плеча.
    (Прежнее «ближайшая к центру торса» на балахоне COS_7 давало плечо вместо кисти: центр торса там низко.)"""
    ys, xs = np.nonzero(m)
    top = ys <= ys.min() + 2
    sy, sx = ys[top].mean(), xs[top].mean()
    i1 = np.argmax((ys - sy) ** 2 + (xs - sx) ** 2)
    return ys, xs, i1


def components(mask):
    """Связные области маски (8 соседей), списки (y, x)."""
    seen = np.zeros_like(mask, bool)
    out = []
    h, w = mask.shape
    for y0, x0 in zip(*np.nonzero(mask)):
        if seen[y0, x0]:
            continue
        stack, comp = [(y0, x0)], []
        seen[y0, x0] = True
        while stack:
            y, x = stack.pop()
            comp.append((y, x))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    yy, xx = y + dy, x + dx
                    if 0 <= yy < h and 0 <= xx < w and mask[yy, xx] and not seen[yy, xx]:
                        seen[yy, xx] = True
                        stack.append((yy, xx))
        out.append(comp)
    return out


def hand_mask(arm):
    """Кисть в кадре руки. Рукав (кожи меньше 60% руки): связная область кожи, ближайшая к дальнему концу руки
    (arm_end) - у GOV_1 это вся кожа, как в прежнем контракте, а у MRC_4 кисть, а не наплечник (рампа 96-111 там
    ещё и цвет брони). Кожа - вся рука (COS_7, REB_4) или её нет: конец руки и всё в 2.5 пикс от него."""
    m = arm > 0
    if not m.any():
        return m, "нет руки"
    ys, xs, i1 = arm_end(m)
    sk = np.isin(arm, SKIN)
    if sk.any() and sk.sum() < 0.6 * m.sum():
        comps = components(sk)
        best = min(comps, key=lambda c: min((y - ys[i1]) ** 2 + (x - xs[i1]) ** 2 for y, x in c))
        hm = np.zeros_like(m)
        for y, x in best:
            hm[y, x] = True
        return hm, "кожа"
    near = (ys - ys[i1]) ** 2 + (xs - xs[i1]) ** 2 <= 2.5 ** 2
    hm = np.zeros_like(m)
    hm[ys[near], xs[near]] = True
    return hm, "конец руки"


def measure_ctx(r, e, d, frames):
    """frames {"iR": hs, "iL": hs}. Касание каждой руки с предметом, который она держит по emulate."""
    fr = body_sheet(r)
    P = ROUT[r]
    layers, masks = {}, {}
    for slot, (kind, rot, ox, oy, _) in e["items"].items():
        m = shifted(hob(frames[slot] + (d + rot) % 8) > 0, ox[d], oy[d])
        layers[slot] = m
    if r == 4:
        layers["to"] = fr(P["body"] + d) > 0
        return {}, layers
    layers["la"] = fr(e["la"] + d) > 0
    layers["ra"] = fr(e["ra"] + d) > 0
    layers["to"] = fr(P["torso"] + d) > 0
    if P["legs"] is not None:
        layers["lg"] = fr(P["legs"] + d) > 0
    seq = [n for n in layer_order(r, d, e["alt"]) if n in layers]
    res = {}
    for arm in ("ra", "la"):
        slot = e["hold"][arm]
        if slot is None or slot not in layers:
            continue
        hand, how = hand_mask(fr(e[arm] + d))
        above = np.zeros_like(hand)
        for n in seq[seq.index(arm) + 1:]:
            above |= layers[n]
        vis = bool((hand & ~above).sum() >= max(1, hand.sum() // 3))
        t = touch(hand, layers[slot])
        res[arm] = (slot, t, vis, verdict(t, vis), how)
    return res, layers


def ctx_name(R, L, aiming):
    s = {None: "-", "1": "1р", "2": "2р"}
    return "П:%s Л:%s %s" % (s[R], s[L], "прицел" if aiming else "стоя")


def routines_check(per):
    """Контракт по всем процедурам с оружием и всем случаям двух рук: grip_contexts.tsv (что рисует движок),
    grip_routines.tsv (касание - предварительный фильтр, не доказательство хвата), grip_routines_summary.tsv.
    Контроль: для routine 0 emulate обязан совпасть с CASES, а кисть «конец руки» на GOV_1 - лечь рядом с кистью «кожа»."""
    by_type = {r["type"]: hs for hs, p in per.items() for r in p["items"]}
    partner = {"1": by_type["STR_PISTOL"], "2": by_type["STR_RIFLE_AK"]}
    # контроль 1: emulate(0) против прежней таблицы CASES
    for case, R, L, aim in (("ONE", "1", None, False), ("TWO_STAND", "2", None, False), ("TWO_AIM", "2", None, True),
                            ("LEFT_ONE", None, "1", False), ("LEFT_TWO_AIM", None, "2", True)):
        e = emulate(0, R, L, aim)
        la, ra, rot, side, _ = CASES[case]
        it = e["items"]["i" + side]
        assert e["la"] == la and e["ra"] == ra, (case, e["la"], e["ra"], la, ra)
        assert it[1] == rot and list(it[2]) == OFF[case][0] and list(it[3]) == OFF[case][1], case
    print("контроль: emulate(routine 0) совпал с CASES на 5 видах")
    # контроль 2: кисть «конец руки» против «кожи» на GOV_1 (там рукав, кожа - кисть)
    dd = []
    for base in (232, 240, 248, 256):
        for d in range(8):
            arm = gov(base + d)
            sk = np.isin(arm, SKIN)
            if not sk.any():
                continue
            ys, xs, i1 = arm_end(arm > 0)
            sy, sx = np.nonzero(sk)
            dd.append(float(np.hypot(ys[i1] - sy.mean(), xs[i1] - sx.mean())))
    print("контроль: кисть «конец руки» от центра кожи на GOV_1, пикс базы: медиана %.1f, 90%% %.1f, макс %.1f (n=%d)"
          % (np.median(dd), np.percentile(dd, 90), max(dd), len(dd)))
    same = sum(bool((hand_mask(gov(b + d))[0] == np.isin(gov(b + d), SKIN)).all())
               for b in (232, 240, 248, 256) for d in range(8))
    print("контроль: на GOV_1 кисть совпала с прежней (вся кожа кадра) в %d кадрах из 32" % same)
    ctx_rows, rows = [], []
    for r in (0, 10, 1, 6, 4):
        P = ROUT[r]
        for R, L in HELD:
            for aiming in (False, True):
                e = emulate(r, R, L, aiming)
                def item_txt(slot):
                    if slot not in e["items"]:
                        return "-"
                    kind, rot, ox, oy, _ = e["items"][slot]
                    return "%sр hs+%s %s" % (kind, "(d+2)%8" if rot else "d", "0" if not any(ox) and not any(oy) else
                                             "(%s / %s)" % (",".join(map(str, ox)), ",".join(map(str, oy))))
                need = ""
                two_slots = [s for s, v in e["items"].items() if v[0] == "2"]
                if two_slots and r != 4:
                    s2 = two_slots[0]
                    sup = [a for a in ("ra", "la") if e["hold"][a] == s2]
                    if len(sup) < 2:
                        need = "опоры нет: вторая рука держит одноручное"
                ctx_rows.append({"routine": r, "held": ctx_name(R, L, aiming), "drawn": ctx_name(e["R"], e["L"], aiming),
                                 "left_arm": "" if e["la"] is None else e["la"], "right_arm": "" if e["ra"] is None else e["ra"],
                                 "item_right": item_txt("iR"), "item_left": item_txt("iL"),
                                 "right_holds": e["hold"]["ra"] or "", "left_holds": e["hold"]["la"] or "",
                                 "order_alt": e["alt"], "not_drawn": "; ".join(e["drop"]), "note": need})
                if r == 4:
                    continue
                for slot, (kind, *_rest) in e["items"].items():
                    other = "iL" if slot == "iR" else "iR"
                    for hs, p in per.items():
                        if p["two"] != (kind == "2"):
                            continue
                        frames = {slot: hs}
                        if other in e["items"]:
                            frames[other] = partner[e["items"][other][0]]
                        for d in range(8):
                            res, _ = measure_ctx(r, e, d, frames)
                            for arm, (s, t, vis, v, how) in res.items():
                                if s != slot:
                                    continue
                                rows.append({"routine": r, "held": ctx_name(R, L, aiming), "slot": slot, "arm": arm,
                                             "dir": d, "handSprite": hs, "touch": "" if t is None else "%.2f" % t,
                                             "visible": vis, "verdict": v, "hand_by": how})
    with open(os.path.join(OUT, "grip_contexts.tsv"), "w", encoding=ENC, newline="") as f:
        w = csv.DictWriter(f, list(ctx_rows[0]), delimiter="\t")
        w.writeheader()
        w.writerows(ctx_rows)
    with open(os.path.join(OUT, "grip_routines.tsv"), "w", encoding=ENC, newline="") as f:
        w = csv.DictWriter(f, list(rows[0]), delimiter="\t")
        w.writeheader()
        w.writerows(rows)
    summ = defaultdict(Counter)
    for x in rows:
        v = x["verdict"]
        k = "закрыта" if "не видна" in v else v
        summ[(x["routine"], x["held"], x["slot"], x["arm"], x["hand_by"])][k] += 1
    out = []
    for k in sorted(summ, key=lambda k: (str(k[0]), k[1], k[2], k[3])):
        c = summ[k]
        n = sum(c.values())
        out.append({"routine": k[0], "held": k[1], "item": k[2], "arm": k[3], "hand_by": k[4], "n": n,
                    **{x: "%.1f" % (100 * c[x] / n) for x in ("держит", "рядом", "мимо", "закрыта", "нет кисти")}})
    with open(os.path.join(OUT, "grip_routines_summary.tsv"), "w", encoding=ENC, newline="") as f:
        w = csv.DictWriter(f, list(out[0]), delimiter="\t")
        w.writeheader()
        w.writerows(out)
    for o in out:
        print("%-3s %-22s %s %s %-10s n=%5d держит %5s рядом %5s мимо %5s закрыта %5s" %
              (o["routine"], o["held"], o["item"], o["arm"], o["hand_by"], o["n"], o["держит"], o["рядом"], o["мимо"], o["закрыта"]))
    r4_drift(per)


def r4_drift(per):
    """Routine 4: рук нет, тело - один кадр и стоя, и в прицеле. Насколько при прицеле двуручное уходит с места,
    где оно было стоя (там его держат запечённые в тело руки): сдвиг центра и доля общей площади, по направлениям."""
    two = [hs for hs, p in per.items() if p["two"]]
    out = []
    for d in range(8):
        sh, io = [], []
        for hs in two:
            a = hob(hs + d) > 0
            b = shifted(hob(hs + (d + 2) % 8) > 0, OFF["TWO_AIM"][0][d], OFF["TWO_AIM"][1][d])
            if not a.any() or not b.any():
                continue
            ya, xa = np.nonzero(a)
            yb, xb = np.nonzero(b)
            sh.append(float(np.hypot(ya.mean() - yb.mean(), xa.mean() - xb.mean())))
            io.append((a & b).sum() / (a | b).sum())
        out.append({"dir": d, "n": len(sh), "shift_median": "%.1f" % np.median(sh), "iou_median": "%.2f" % np.median(io)})
    with open(os.path.join(OUT, "grip_r4_drift.tsv"), "w", encoding=ENC, newline="") as f:
        w = csv.DictWriter(f, list(out[0]), delimiter="\t")
        w.writeheader()
        w.writerows(out)
    for o in out:
        print("routine 4: двуручное стоя -> прицел", o)


REPS = [("STR_RIFLE_AK", "автомат AK (HD есть)"),("STR_PISTOL", "пистолет"), ("STR_SMG", "ПП одноручный"),
        ("STR_SMG_BM_K", "короткий автомат, двуручный"), ("STR_BATTLE_RIFLE", "боевая винтовка"),
        ("STR_SNIPER_RIFLE", "длинная винтовка"), ("STR_SHOTGUN", "дробовик"), ("STR_LMG", "пулемёт, большой магазин"),
        ("STR_MINIGUN", "миниган, лента 300"), ("STR_ROCKET_LAUNCHER", "тяжёлое: ракетомёт"),
        ("STR_AUTO_CANNON", "тяжёлое: автопушка"), ("STR_MEGA_CANNON", "тяжёлое, но одноручное"),
        ("STR_CHITIN_KNIFE", "холодное одноручное"), ("STR_BARBARIAN_AX", "холодное двуручное")]


def pick(per, rows, cls):
    """Представители REPS плюс худший по касанию на d=2 в каждом классе, где касание хуже 3 пикселей."""
    worst = defaultdict(float)
    for r in rows:
        if r["dir"] == 2 and r["touch"] != "" and r["case"] in ("ONE", "TWO_STAND", "TWO_AIM"):
            worst[r["handSprite"]] = max(worst[r["handSprite"]], float(r["touch"]))
    by_type = {r["type"]: hs for hs, p in per.items() for r in p["items"]}
    sel, seen = [], set()
    for t, why in REPS:
        hs = by_type.get(t)
        if hs is None:
            print("нет кадра в руке:", t)
            continue
        if hs not in seen:
            sel.append({"hs": hs, "why": why, "class": per[hs]["class"]})
            seen.add(hs)
    for cname in sorted({p["class"] for p in per.values()}):
        hss = [hs for hs, p in per.items() if p["class"] == cname and hs not in seen]
        if not hss:
            continue
        bad = max(hss, key=lambda hs: worst.get(hs, 0))
        if worst.get(bad, 0) > 3:
            sel.append({"hs": bad, "why": "худшее касание в классе: %.1f" % worst[bad], "class": cname})
            seen.add(bad)
    for s in sel:
        p = per[s["hs"]]
        s["two"] = p["two"]
        s["items"] = [r["type"] for r in p["items"]][:4]
        s["n_items"] = len(p["items"])
    return sel


CROP = (2, 4, 30, 34)      # база: область рук и оружия на сравнительном листе
ZOOM = 2


def compare_sheet(sel, per, d):
    fnt = ImageFont.truetype(FONT, 15)
    sm = ImageFont.truetype(FONT, 12)
    cols = ["классика: стоя", "HD-руки: стоя", "классика: прицел", "HD-руки: прицел", "HD-руки: прицел, 242.v1 (опыт AK)"]
    box = tuple(v * K for v in CROP)
    cw, ch = (box[2] - box[0]) * ZOOM, (box[3] - box[1]) * ZOOM
    head = 40
    W = 16 + 250 + len(cols) * (cw + 12)
    H = head + len(sel) * (ch + 50) + 10
    out = Image.new("RGB", (W, H), (22, 22, 24))
    dr = ImageDraw.Draw(out)
    dr.text((16, 8), "Одни и те же руки x разное оружие, направление %d. Голубой крест - кисть классики; "
            "красное - кадра нет в HD (взята классика x4)" % d, fill=(235, 235, 235), font=fnt)
    for i, t in enumerate(cols):
        dr.text((16 + 250 + i * (cw + 12), head - 14), t, fill=(200, 200, 200), font=sm)
    for j, s in enumerate(sel):
        y = head + 8 + j * (ch + 50)
        hs, two = s["hs"], s["two"]
        dr.text((16, y), "HANDOB %d  %s" % (hs, "двуручное" if two else "одноручное"), fill=(235, 235, 235), font=fnt)
        dr.text((16, y + 20), s["why"], fill=(200, 200, 160), font=sm)
        dr.text((16, y + 38), ", ".join(s["items"][:3]) + (" +%d" % (s["n_items"] - 3) if s["n_items"] > 3 else ""),
                fill=(160, 160, 160), font=sm)
        stand = "TWO_STAND" if two else "ONE"
        aim = "TWO_AIM" if two else "ONE"
        cells = [(stand, False, False), (stand, True, False), (aim, False, False), (aim, True, False), (aim, True, True)]
        for i, (case, hd, v1) in enumerate(cells):
            x = 16 + 250 + i * (cw + 12)
            if v1 and not two:
                dr.text((x, y + 60), "одноручное:\nприцел = стоя\n(движок)", fill=(150, 150, 150), font=sm)
                continue
            img, miss = compose(hs, case, d, hd, v1)
            img = hand_marks(img, case, d).crop(box)
            out.paste(img.resize((cw, ch), Image.NEAREST), (x, y))
            if hd and miss:
                dr.text((x, y + ch + 2), "HD нет: " + ", ".join(miss), fill=(255, 80, 80), font=sm)
            elif not two and i == 2:
                dr.text((x, y + ch + 2), "кадр и руки как стоя", fill=(150, 150, 150), font=sm)
            m = measure(hs, case, d)
            txt = "  ".join("%s: %s %s" % ("ближн" if h == "near" else "дальн", v[2].replace(", не видна", " (закрыта)"),
                                           "" if v[0] is None else "%.1f" % v[0]) for h, v in m.items())
            dr.text((x, y + ch + 16), txt,
                    fill=(180, 220, 180) if all(v[2].startswith("держит") for v in m.values()) else (240, 190, 120), font=sm)
    p = os.path.join(OUT, "compare_d%d.png" % d)
    out.save(p)
    print(p, out.size)


def all_pages(per, rows, d, per_page=48):
    """Всё оружие: HD-руки пилота стоя и в прицеле, кадр 26x28 базы у кисти, подпись - вердикт."""
    sm = ImageFont.truetype(FONT, 11)
    v = {(r["handSprite"], r["case"], r["hand"]): r["verdict"] for r in rows if r["dir"] == d}
    hss = sorted(per, key=lambda hs: (not per[hs]["two"], per[hs]["class"], hs))
    crop = (2 * K, 6 * K, 30 * K, 34 * K)
    tw, th = crop[2] - crop[0], crop[3] - crop[1]
    cols = 6
    for pg in range(0, len(hss), per_page):
        chunk = hss[pg:pg + per_page]
        rowsn = (len(chunk) + cols - 1) // cols
        out = Image.new("RGB", (cols * (2 * tw + 18), rowsn * (th + 46) + 8), (22, 22, 24))
        dr = ImageDraw.Draw(out)
        for i, hs in enumerate(chunk):
            x, y = (i % cols) * (2 * tw + 18) + 6, (i // cols) * (th + 46) + 6
            two = per[hs]["two"]
            cases = ("TWO_STAND", "TWO_AIM") if two else ("ONE", None)
            for k, case in enumerate(cases):
                if case is None:
                    continue
                img, _ = compose(hs, case, d, True)
                out.paste(hand_marks(img, case, d).crop(crop), (x + k * (tw + 4), y))
            bad = [c[0] + ":" + c[1] for c in ((case, h) for case in cases if case for h in ("near", "far"))
                   if v.get((hs, c[0], c[1]), "держит") not in ("держит", "держит, не видна")]
            dr.text((x, y + th + 2), "%d %s %s" % (hs, "2р" if two else "1р", per[hs]["class"][:26]), fill=(220, 220, 220), font=sm)
            dr.text((x, y + th + 16), per[hs]["items"][0]["type"][:34], fill=(150, 150, 150), font=sm)
            dr.text((x, y + th + 30), ("мимо/рядом: " + ", ".join(bad)) if bad else "держит",
                    fill=(240, 150, 110) if bad else (150, 220, 150), font=sm)
        p = os.path.join(OUT, "all_d%d_%02d.png" % (d, pg // per_page + 1))
        out.save(p)
    print("листов всего оружия:", (len(hss) + per_page - 1) // per_page)


if __name__ == "__main__":
    if "--contexts" in sys.argv:            # только процедуры 1, 4, 6, 10 и две занятые руки
        sys.stdout.reconfigure(encoding="utf-8")
        os.makedirs(OUT, exist_ok=True)
        by_, _ = load_items()
        per_ = {hs: {"two": Counter(r["twoHanded"] for r in its).most_common(1)[0][0] == "True", "items": its}
                for hs, its in by_.items()}
        routines_check(per_)
    else:
        main()
