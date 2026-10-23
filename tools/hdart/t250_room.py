#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Тикет XP-000250: комната дома (URBANWASTE37/41) - шкафы, стулья, прожжённый пол. Без генерации.

Что не так (по тикету и по листу классика | сейчас):
  1. Шкафы. MADDECOR_WASTE 38 -> FRNITURE_WASTE 6 (зеркало с перекраской) и MADDECOR_WASTE 54 -> FRNITURE_WASTE 23
     поставлены 22.10 (ecc229854, STRICT, тикет 221): чистое новое дерево. Классика: старое, грязное, у 6/38 - верхняя
     полочка и большая выломанная доска внизу, у 23/54 - доска и обломки. HD у 6/38 только верхняя полочка и голый низ.
     Лечение (процедурно): (а) у 6/38 нижняя выломанная доска берётся с 23/54 (те же коробка и проём, один силуэт),
     верхняя полочка остаётся своя; (б) состаривание всех четырёх - тон и разброс в Lab к классике, пятна классики
     (низкие частоты яркости), грязь по краям и к низу, продольные потёки; зерно дерева HD сохраняется.
     Основы MADDECOR 38 и 54, FRNITURE 6 и 23 - их зеркало с переносом среднего Lab прежних кадров (R-457, одна основа
     на семью, R-136).
  2. Стулья FRNITURE_WASTE 2 и 3 (3 - зеркало 2; sdxl_legacy 21.09, ни одного одобрения): на сиденье нарисована
     ёлочка (шеврон) вместо ровного сиденья классики; ножки и спинка мутные. Сиденье - ромб по классике (рампа 162-163
     в центре кадра) закрашивается плавным тоном классики (размыт) с редкими продольными досками; контур, ножки и
     спинка остаются, на весь кадр - небольшое повышение резкости.
  3. Прожжённый пол URBAN_WASTE 26 (и побайтные копии классики: URBAN_WASTE_WALLS 26) - светлые разводы вокруг воронки.
     Классика: тёмная воронка с красноватой каймой по бурому полу. Воронка и кайма - маской классики x4 (мягкой), пол -
     HD URBAN_WASTE 25 (ровный пол комнаты, тот же набор), светлые разводы HD уходят.
  Прежнее поколение шкафов (sdxl_legacy, 511426f7 и aa1f050f) на листе для сравнения; оно держит силуэт классики лесенкой и
  мутное, поэтому в правку не взято (R-357: материал не лучше).

    py -3.13 tools/hdart/t250_room.py                  # кадры в art/tickets/t250/out/TERRAIN/...
    py -3.13 tools/hdart/t250_room.py --sheet          # листы в art/_review/tickets_2026-10-23/
    py -3.13 tools/hdart/t250_room.py --install --yes  # + в мод hd через манифест (по слову Vitali, под очередью правок)
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
import ground_seam as gs            # noqa: E402
import ticket_scene as ts           # noqa: E402
import water_build as wb            # noqa: E402

OUT = ROOT / "art" / "tickets" / "t250" / "out"
REVIEW = ROOT / "art" / "_review" / "tickets_2026-10-23"
PAL = wb.palette()
LUMA = gs.LUMA
SC = None


def scene():
    global SC
    if SC is None:
        SC = ts.Scene()
    return SC


def hd(s, f):
    return np.asarray(scene().hd(s, f)).astype(np.float32)


def classic(s, f):
    return wb.read_set(s)[f]


def lab(rgb):
    return cv2.cvtColor(np.clip(rgb, 0, 255).astype(np.float32) / 255, cv2.COLOR_RGB2Lab)


def unlab(x):
    return np.clip(cv2.cvtColor(x.astype(np.float32), cv2.COLOR_Lab2RGB) * 255, 0, 255)


def mirror(p):
    return np.asarray(ImageOps.mirror(Image.fromarray(p.astype(np.uint8)))).astype(np.float32)


def up_nearest(a):
    return np.kron(a, np.ones((4, 4), a.dtype))


def fbm(shape, rng, sig=(2.5, 6.0, 14.0), w=(0.45, 0.35, 0.2), aniso=None):
    n = np.zeros(shape, np.float32)
    for s, k in zip(sig, w):
        g = rng.standard_normal(shape).astype(np.float32)
        sy, sx = (s, s) if aniso is None else (s * aniso[0], s * aniso[1])
        g = ndi.gaussian_filter(g, (sy, sx), mode="wrap")
        n += k * g / (g.std() + 1e-6)
    return n / (n.std() + 1e-6)


# ------------------------------------------------------------------ шкафы

BOARD = (61, 76, 112, 127)        # x0, y0, x1, y1: нижняя доска у 23/54 в ориентации "проём вправо" (как FRNITURE 6/23)


def transplant_board(base_r, donor_r):
    """base_r, donor_r - RGBA в ориентации «проём вправо». Нижняя доска донора ложится в проём базы."""
    x0, y0, x1, y1 = BOARD
    m = np.zeros(base_r.shape[:2], np.float32)
    m[y0:y1, x0:x1] = 1
    m = ndi.gaussian_filter(m, 1.6)
    # только внутри проёма: тёмный интерьер у донора и базы (боковые стойки светлее)
    l_b = base_r[..., :3] @ LUMA
    l_d = donor_r[..., :3] @ LUMA
    inner = ((l_b < 150) & (l_d < 170)).astype(np.float32)
    inner = ndi.gaussian_filter(inner, 1.2)
    m = m * inner
    out = base_r.copy()
    out[..., :3] = base_r[..., :3] * (1 - m[..., None]) + donor_r[..., :3] * m[..., None]
    return out


def age(p, a, rng, tone=0.9, stain=1.2, grime=0.16, edge=0.20, bottom=0.15, streak=0.08, crackk=1.0):
    """Состарить кадр p (RGBA float) по классике a: тон, пятна, грязь."""
    al = p[..., 3] > 127
    cl = PAL[a][..., :3].astype(np.float32)
    clu = np.asarray(Image.fromarray(cl.astype(np.uint8)).resize((128, 160), Image.NEAREST)).astype(np.float32)
    cm = np.asarray(Image.fromarray(((a > 0) * 255).astype(np.uint8)).resize((128, 160), Image.NEAREST)) > 127
    mm = al & cm
    L_h, L_c = lab(p[..., :3]), lab(clu)
    mh, sh = L_h[mm].mean(0), L_h[mm].std(0)
    mc, sc_ = L_c[mm].mean(0), L_c[mm].std(0)
    out = np.empty_like(L_h)
    for ch in range(3):
        k = sh[ch] * (1 - tone) + sc_[ch] * tone
        out[..., ch] = (L_h[..., ch] - mh[ch]) / (sh[ch] + 1e-6) * k + mh[ch] * (1 - tone) + mc[ch] * tone
    rgb = unlab(out)
    # пятна классики: местная яркость к яркости рядом (низкие частоты)
    w = (a > 0).astype(np.float32)
    lum = (cl @ LUMA) * w
    lo = wb.gauss(lum, 1.2) / np.maximum(wb.gauss(w, 1.2), 1e-3)
    hi = wb.gauss(lum, 5.0) / np.maximum(wb.gauss(w, 5.0), 1e-3)
    r = 1 + (np.clip(lo / np.maximum(hi, 1), 0.5, 1.0) - 1) * stain
    rgb = rgb * np.asarray(Image.fromarray(r.astype(np.float32), "F").resize((128, 160), Image.BICUBIC))[..., None]
    # грязь: пятна, потёки, затемнение у кромки и к низу
    n = fbm(al.shape, rng, sig=(3.5, 8.0, 18.0))
    blot = 1 - grime * np.clip(n * 0.7 + 0.3, 0, 1.4)
    st = fbm(al.shape, rng, sig=(2.0, 5.0, 9.0), aniso=(7.0, 1.0))
    streaks = 1 - streak * np.clip(st * 0.8, -0.3, 1.5)
    dist = ndi.distance_transform_edt(al)
    ao = 1 - edge * np.exp(-dist / 5.0)
    yy = np.arange(160, dtype=np.float32)[:, None] * np.ones((1, 128), np.float32)
    bt = 1 - bottom * np.clip((yy - 80) / 70, 0, 1)
    f = (blot * streaks * ao * bt)[..., None]
    tint = np.array([1.0, 0.97, 0.92], np.float32)            # грязь теплее
    mix = np.clip((1 - f[..., 0]) * 2.5, 0, 1)[..., None]
    rgb = rgb * np.concatenate([f, f ** 1.12, f ** 1.3], axis=-1)           # грязь - тёмно-бурая, не жёлтая
    # трещины и царапины вдоль волокна: тонкие тёмные штрихи (ridged-шум, вытянут по вертикали)
    rd = 1 - np.abs(fbm(al.shape, rng, sig=(1.0, 2.0, 4.0), aniso=(6.0, 1.0)))
    crack = np.clip((rd - 0.94) * 14.0, 0, 1) * crackk
    rgb = rgb * (1 - 0.35 * crack)[..., None]
    return np.dstack([np.clip(rgb, 0, 255), p[..., 3]])


def lab_shift(src_new, ref_old, ref_base_mirror):
    """Перекраска: у src_new средний Lab сдвинут на разницу прежнего производного и зеркала прежней основы."""
    a = (ref_old[..., 3] > 127) & (ref_base_mirror[..., 3] > 127)
    d = lab(ref_old[..., :3])[a].mean(0) - lab(ref_base_mirror[..., :3])[a].mean(0)
    L = lab(src_new[..., :3]) + d
    out = src_new.copy()
    out[..., :3] = unlab(L)
    return out


def cabinets():
    cur = {k: hd(*k) for k in [("MADDECOR_WASTE", 38), ("MADDECOR_WASTE", 54), ("FRNITURE_WASTE", 6), ("FRNITURE_WASTE", 23)]}
    # ориентация «проём вправо» = FRNITURE 6/23; основы MADDECOR 38/54 - зеркало
    r38 = mirror(cur[("MADDECOR_WASTE", 38)])
    r54 = mirror(cur[("MADDECOR_WASTE", 54)])
    r38 = transplant_board(r38, r54)                  # у 6/38: нижняя выломанная доска с 23/54
    base38 = mirror(r38)
    base54 = cur[("MADDECOR_WASTE", 54)]
    new38 = age(base38, classic("MADDECOR_WASTE", 38), np.random.default_rng(3801))
    new54 = age(base54, classic("MADDECOR_WASTE", 54), np.random.default_rng(5401))
    new6 = lab_shift(mirror(new38), cur[("FRNITURE_WASTE", 6)], mirror(cur[("MADDECOR_WASTE", 38)]))
    new23 = lab_shift(mirror(new54), cur[("FRNITURE_WASTE", 23)], mirror(cur[("MADDECOR_WASTE", 54)]))
    res = {("MADDECOR_WASTE", 38): new38, ("MADDECOR_WASTE", 54): new54,
           ("FRNITURE_WASTE", 6): new6, ("FRNITURE_WASTE", 23): new23}
    return res


# ------------------------------------------------------------------ стулья

SEAT_CX, SEAT_CY = 58.0, 95.5       # центр сиденья в пикселях кадра 128x160
SEAT_HX, SEAT_HY = 38.0, 18.0


def chair(f):
    p = hd("FRNITURE_WASTE", f)
    a = classic("FRNITURE_WASTE", f)
    flip = f == 3
    if flip:                                           # считаем в ориентации кадра 2
        p = mirror(p)
        a = a[:, ::-1]
    yy, xx = np.mgrid[0:160, 0:128].astype(np.float32)
    cx, cy = SEAT_CX, SEAT_CY
    dm = np.abs(xx - cx) / SEAT_HX + np.abs(yy - cy) / SEAT_HY
    # сиденье: ромб, где классика - светлая рампа сиденья (162-163 и соседние) - по ней мягко
    seat_cl = ((a >= 162) & (a <= 165)).astype(np.float32)
    seat_cl = np.asarray(Image.fromarray((seat_cl * 255).astype(np.uint8)).resize((128, 160), Image.NEAREST)) / 255.0
    m = np.clip((1.04 - dm) * 8, 0, 1)
    m = ndi.gaussian_filter(m.astype(np.float32), 0.8) * (p[..., 3] > 127)
    # цвет сиденья: размытая классика (дизеринг ушёл) плюс продольные доски
    cl = PAL[a][..., :3].astype(np.float32) * (a > 0)[..., None]
    w = (a > 0).astype(np.float32)
    blur = np.dstack([wb.gauss(cl[..., i], 1.4) for i in range(3)]) / np.maximum(wb.gauss(w, 1.4), 1e-3)[..., None]
    seat = np.dstack([np.asarray(Image.fromarray(blur[..., i].astype(np.float32), "F").resize((128, 160), Image.BICUBIC))
                      for i in range(3)])
    u = (xx - cx) / SEAT_HX * 0.5 + (yy - cy) / SEAT_HY * 0.5       # вдоль одной оси ромба
    rng = np.random.default_rng(250 + f)
    wob = ndi.gaussian_filter(rng.standard_normal((160, 128)).astype(np.float32), 3.0) * 0.6
    boards = np.sin((u * 7.0 + wob) * np.pi)
    seat = seat * (1 + 0.055 * boards)[..., None]
    seat = seat * (1 + 0.04 * ndi.gaussian_filter(rng.standard_normal((160, 128)).astype(np.float32), 1.0))[..., None]
    out = p.copy()
    out[..., :3] = p[..., :3] * (1 - m[..., None]) + seat * m[..., None]
    # резкость по всему кадру (HD мутный): unsharp по цвету с учётом альфы
    al = (out[..., 3] / 255.0)
    pm = out[..., :3] * al[..., None]
    blurp = np.dstack([ndi.gaussian_filter(pm[..., i], 1.6) for i in range(3)])
    blura = np.maximum(ndi.gaussian_filter(al, 1.6), 1e-3)[..., None]
    sharp = out[..., :3] + 0.9 * (out[..., :3] - blurp / blura)
    out[..., :3] = np.clip(sharp, 0, 255)
    if flip:
        out = mirror(out)
    return out


# ------------------------------------------------------------------ пол

def burnt_floor(sset="URBAN_WASTE", ff=26, base_f=25):
    """Прожжённый пол: воронка и кайма - по классике, пол - HD соседней целой плитки того же набора."""
    a = classic(sset, ff)
    base = hd(sset, base_f).copy()
    # чёрные точки целого пола (одна у классики 25) в воронку не тащим: закраска медианой
    bl = base[..., :3] @ LUMA
    med = ndi.median_filter(bl, size=9)
    dot = ndi.binary_dilation(bl < med * 0.5, iterations=2)
    for i in range(3):
        base[..., i] = np.where(dot, ndi.median_filter(base[..., i], size=9), base[..., i])
    m = a > 0
    cl = PAL[a][..., :3].astype(np.float32)
    lum = cl @ LUMA
    w = m.astype(np.float32)
    # цвет и яркость классики, размытые по плитке (дизеринг и ступени пикселей уходят)
    def soft(x, sg):
        num = wb.gauss(x * w, sg)
        return num / np.maximum(wb.gauss(w, sg), 1e-3)
    lum_s = soft(lum, 1.1)
    floor_lum = np.percentile(lum[m], 75)                         # ровный пол вокруг воронки
    r = np.clip(lum_s / max(floor_lum, 1.0), 0.0, 1.15)
    up = lambda x: np.asarray(Image.fromarray(x.astype(np.float32), "F").resize((128, 160), Image.BICUBIC))
    r4 = up(r)
    col_s = np.dstack([up(soft(cl[..., i], 1.1)) for i in range(3)])
    crater = np.clip((1.0 - r4) * 4.0, 0, 1)                      # 0 - целый пол, 1 - воронка
    rgb = base[..., :3] * np.clip(r4, 0, 1.1)[..., None]
    # в воронке и кайме - цвет классики (красноватая кайма, чёрная воронка), фактура пола остаётся
    tex = base[..., :3] / np.maximum(ndi.gaussian_filter(base[..., :3], (6, 6, 0)), 1.0)
    rgb = rgb * (1 - crater[..., None]) + col_s * np.clip(1.0 + (tex - 1.0) * 0.7, 0.6, 1.4) * crater[..., None]
    out = np.dstack([np.clip(rgb, 0, 255), base[..., 3]])          # альфа - как у соседней целой плитки (R-247)
    return out


# ------------------------------------------------------------------ сборка

def build_all():
    res = {}
    for k, v in cabinets().items():
        res[k] = v
    for f in (2, 3):
        res[("FRNITURE_WASTE", f)] = chair(f)
    fl = burnt_floor()
    res[("URBAN_WASTE", 26)] = fl
    res[("URBAN_WASTE_WALLS", 26)] = fl
    return res


def save_all(res):
    paths = {}
    for (s, f), p in res.items():
        d = OUT / "TERRAIN" / (s + ".PCK")
        d.mkdir(parents=True, exist_ok=True)
        q = d / ("%d.png" % f)
        Image.fromarray(np.clip(p, 0, 255).round().astype(np.uint8), "RGBA").save(q)
        paths["TERRAIN/%s.PCK/%d.png" % (s, f)] = q
    return paths


def make_sheet(res):
    sc = scene()
    over = {(s.upper(), f): Image.fromarray(np.clip(p, 0, 255).round().astype(np.uint8), "RGBA") for (s, f), p in res.items()}
    terr, block = "URBAN_WASTE", "URBANWASTE37"
    cls, _ = sc.render(terr, block, "classic", k=4, maxz=0)
    now, _ = sc.render(terr, block, "hd", k=4, maxz=0)
    new, _ = sc.render(terr, block, "hd", override=over, k=4, maxz=0)
    shot = Image.open(ROOT / "census" / "tickets" / "XP-000250" / "files" / "01_shot.png").convert("RGBA")
    sh = shot.crop((230, 200, 1900, 1150))
    box = (160, 360, 1000, 930)
    panels = [("скриншот игрока (XP-250)", sh), ("классика", ts.crop_pad(cls, box)),
              ("HD сейчас", ts.crop_pad(now, box)), ("HD новое", ts.crop_pad(new, box))]
    ts.sheet(panels, REVIEW / "t250_after.png", cols=2, width=1100)
    fr = []
    for (s, f), im in sorted(res.items()):
        if (s, f) == ("URBAN_WASTE_WALLS", 26):
            continue
        col = Image.new("RGBA", (128, 3 * 160 + 8), (26, 26, 30, 255))
        n = Image.fromarray(np.clip(im, 0, 255).round().astype(np.uint8), "RGBA")
        for j, x in enumerate((sc.classic(s, f), sc.hd(s, f), n)):
            col.alpha_composite(x, (0, j * 164))
        fr.append(("%s %d" % (s, f), col))
    ts.sheet(fr, REVIEW / "t250_frames.png", cols=len(fr))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sheet", action="store_true")
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    res = build_all()
    paths = save_all(res)
    print("кадров: %d -> %s" % (len(res), OUT))
    if a.sheet:
        make_sheet(res)
        print("лист:", REVIEW / "t250_after.png")
    if a.install:
        if not a.yes:
            raise SystemExit("сухой прогон; --install --yes - записать в мод (только по слову Vitali)")
        ts.install_files(paths, "t250_room", "t250_room.py 23.10 состаривание шкафов, сиденье стульев, воронка по классике",
                         "Vitali 23.10 «чини все» (XP-000250); лист art/_review/tickets_2026-10-23/t250_after.png",
                         "t250: шкафы, стулья, прожжённый пол")
    return 0


if __name__ == "__main__":
    sys.exit(main())
