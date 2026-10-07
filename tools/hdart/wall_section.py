#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Участок стены одним рисунком (WALL_RENDER_V1, метод утверждён 07.10).

Стену нельзя рисовать отдельным кадром: у каждого края клетки модель рисует свой торец, и на карте стена
собрана из кубиков (R-121, R-122). Здесь берётся окно карты (до 8x8 клеток одного этажа) так, как оно
стоит в игре: западные и северные стены, встроенные детали (WALL_EMBEDDED из плана), двери - контекстом.
Участок рисуется одной картинкой (Qwen-Image-2.1 strict), режется по клеткам и сводится в кадры:

  * вход - xBRZ x4 и бикубика, без заливки дыр (long_object.model_input заливает - проёмы бы закрылись);
  * альфа кадра - силуэт оригинала x4 (xBRZ по маске, без заливки дыр, R-089), цвет - из ответа;
    где модель под силуэтом оставила подложку - цвет соседей (inpaint), и это число в отчёте;
  * один кадр стоит во многих местах: кадр собирается из своих мест по видимости (то, что закрыто
    стеной спереди или срезано полустеной, берётся у другого места; не видно нигде - xBRZ оригинала);
  * полосы у прямых стыков (северная вдоль x, западная вдоль y) - у одной эталонной пары, как в
    long_object.unify: любые две клетки встают встык так же, как она;
  * двери не рисуются: при обратной сборке ставится HD-кадр двери из мода, который читает игра (R-087).

Проверки после вырезки (report.json и verdict.md): шов на каждом стыке (ступень яркости поперёк стыка
в сборке против той же в целом рисунке), проёмы (прозрачное у оригинала - в ответе модели и в кадре),
край кадра по строкам против оригинала, доля невидимого, строение внутри силуэта (яркость и грани
уменьшенного кадра против оригинала, R-210), подложка под силуэтом и краска вне его в ответе.

    E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/wall_section.py ^
        --terrain INDUSTRIALSLUM_ESCAPE_TOWER --block INDUSTRIALSLUMHUGE02 --z 0 --x0 22 --y0 8 ^
        --hints census/walls/method_check/hints.json --hint-key C3 --seeds 2711,2712 ^
        --out census/walls/method_check/C3

--state die / rubble - те же места, но стены участка заменены записью die (повреждение) или die от die
(обломки): проверка повреждённого и разрушенного состояния. В пак не идёт ничего.
"""
import argparse
import csv
import json
import os
import sys
import time
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
for p in (HERE, os.path.dirname(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np                                  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter       # noqa: E402
import cv2                                          # noqa: E402
import probe_object as po                           # noqa: E402  (он же ставит HF_HOME)
import long_object as lo                            # noqa: E402
import map_mockup as mm                             # noqa: E402
import pck_census as pc                             # noqa: E402
import sprite_scale as ss                           # noqa: E402
import battle_view as bv                            # noqa: E402

ENC = "utf-8-sig"
TAB = chr(9)
REC = 62
PLAN = "census/walls/wall_render_plan.tsv"
# Решения специалиста 07.10: вне первой партии, чужие кадры, пол в слоте стены (G043)
SKIP = {"PORTURBITS:60", "PORTURBITS:62"}
OWNED = {"ROADS:0", "ROADSLUX:0", "TAVERN:14", "TAVERN:16", "CATACDECOR_CONC:21"}
NOT_WALL = {"NUKE2:0"}
SUB = {
    "окно_рама": ("окно_частично",),
    "окно_стекло": ("окно_рисованное_стекло", "стекло_непробиваемое"),
    "проём": ("окно_прозрачное", "проём_до_пола", "декор_прозрачная_вставка"),
}
CASES = ["прямая", "угол_внешний", "угол_внутренний", "T_X", "торец", "окно_рама", "окно_стекло", "проём",
         "стык_раздвижной", "косяк", "strict", "повреждение", "обломки", "встроенная", "тёмная", "яркая"]
# Пороги приёмки (подобраны до прогона, не под результат)
SEAM_MAX = 8.0          # лишняя ступень яркости поперёк стыка, 0..255
OPEN_RAW_MAX = 0.25     # доля проёма, закрашенная в ответе модели
OPEN_FIN_MAX = 0.02     # доля проёма, непрозрачная в готовом кадре
UNSEEN_MAX = 0.10       # доля силуэта кадра, не видная ни в одном месте участка
EDGE_MAX = 1            # край кадра по строкам против оригинала, пикселей базы
PANEL_STD_MAX = 2.5     # подложка ответа ровная: разброс яркости в окне 5x5 (у края ответа 0.2-0.5)
PANEL_HOLE_MIN = 64 * 64  # ровный кусок цвета подложки внутри стен - подложка, если больше 16x16 пикселей базы
PANEL_OPEN_SHARE = 0.3  # ...или если лежит на сквозном проёме оригинала хотя бы такой долей (окно, щели досок)
LAYOUT_PANEL_MAX = 0.15 # раскладка ответа: доля силуэта, где в ответе подложка (C3: 0.03-0.06)
LAYOUT_SHIFT_MAX = 12   # раскладка ответа: сдвиг ответа против входа, пикселей x4

STYLE = (
    "<image1> is the low-resolution original of a connected section of walls from an X-COM-style isometric "
    "strategy game map: {what}. It is shown on a flat preview panel; the panel is interface, not part of the "
    "walls. Use case: sketch-to-render. Asset type: polished 4x HD wall tiles. "
    "Redraw this same wall section as detailed hand-painted game artwork. Keep exactly the position, the "
    "height, the thickness, the ends, the corners and the joints of every wall, every window, frame and "
    "opening of <image1>, and its colours and materials. Where <image1> shows the panel through a wall, the "
    "opening stays open; painted window glass stays glass with its colour and highlight. {view}. "
    "Clear readable shapes, crisp straight edges, fine painted detail. "
    "Output only these walls on the same flat panel. No ground, no floor, no roof, no other objects, "
    "no frame, no text.")


def tsv(p):
    with open(p, encoding=ENC) as f:
        return list(csv.DictReader(f, delimiter=TAB, quoting=csv.QUOTE_NONE))


class Raw:
    """MCD целиком, 62 байта на запись (map_mockup.World.records не отдаёт дверь и Big_Wall)."""
    def __init__(self, world):
        self.world, self.data = world, {}

    def __call__(self, s):
        if s not in self.data:
            p = self.world.files.find(os.path.join("TERRAIN", s + ".MCD"))
            d = open(p, "rb").read() if p else b""
            self.data[s] = [d[i:i + REC] for i in range(0, len(d) - REC + 1, REC)]
        return self.data[s]


def clip_half(im):
    """Северная стена при западной в той же клетке рисуется только правой половиной (Map.cpp, half)."""
    im = im.copy()
    im.paste((0, 0, 0, 0), (0, 0, im.width // 2, im.height))
    return im


def members_of(world, raw, plan, terrain, block, z, x0, y0, win, state):
    """Части окна карты в порядке рисования игры (y, x, west/north/object).
    role: paint - рисуется и режется; ctx - дверь и чужое, во входе и в сборке, не режется."""
    sets = world.sets_of(terrain)
    sizes = {s: len(raw(s)) for s in sets}
    _sx, _sy, _sz, cells = mm.read_block(world, block)
    out, notes = [], []
    for y in range(y0, y0 + win):
        for x in range(x0, x0 + win):
            cell = cells.get((x, y, z))
            if not cell:
                continue
            west_here = False
            for part in (1, 2, 3):
                v = cell[part]
                if not v:
                    continue
                s, rec = pc.resolve(v, sets, sizes)
                if s is None or rec >= len(raw(s)):
                    continue
                r = raw(s)[rec]
                k = ("%s:%d" % (s, rec)).upper()
                p = plan.get(k)
                door = bool(r[30] or r[35])
                if part == 3:
                    if p and p["класс"] == "WALL_EMBEDDED" and k not in SKIP:
                        role = "paint"
                    else:
                        continue                     # предметы в участок стены не входят
                elif door:
                    role = "ctx"
                elif p and p["класс"] == "WALL" and k not in SKIP | OWNED | NOT_WALL:
                    role = "paint"
                else:
                    role = "ctx"
                orig_k = k
                if role == "paint" and state:
                    steps = {"die": 1, "rubble": 2}[state]
                    for _ in range(steps):
                        d = raw(s)[rec][44]
                        if not d or d >= len(raw(s)):
                            break
                        rec = d
                    r = raw(s)[rec]
                    k = ("%s:%d" % (s, rec)).upper()
                if len(set(r[0:8])) > 1 and role == "paint":
                    notes.append("%s анимирована (кадры %s): режется только кадр 0" % (k, list(r[0:8])))
                spr = world.sprite(s, r[0], None)
                if spr is None:
                    continue
                spr = spr.convert("RGBA")
                half = part == 2 and west_here
                if part == 1:
                    west_here = True
                out.append(dict(key=(s.upper(), r[0], x, y, part), set=s, frame=r[0], rec=k, orig_rec=orig_k,
                                x=x, y=y, part=part, role=role, door=bool(r[30]), raw=r, half=half,
                                full=spr, spr=clip_half(spr) if half else spr,
                                dx=(x - y) * 16, dy=(x + y) * 8 - z * 24 - r[49]))
    return out, notes


def layout(mem):
    mx, my = min(m["dx"] for m in mem), min(m["dy"] for m in mem)
    size = (max(m["dx"] for m in mem) - mx + 32, max(m["dy"] for m in mem) - my + 40)
    return size, [(m["dx"] - mx, m["dy"] - my) for m in mem]


def compose(mem, at, size, imgs=None, k=1):
    im = Image.new("RGBA", (size[0] * k, size[1] * k), (0, 0, 0, 0))
    for i, m in enumerate(mem):
        spr = m["spr"] if imgs is None else imgs[i]
        if spr is None:
            continue
        if imgs is not None and m["half"]:
            spr = clip_half(spr)
        im.alpha_composite(spr, (at[i][0] * k, at[i][1] * k))
    return im


def label_map(mem, at, size):
    lab = np.full((size[1], size[0]), -1, np.int32)
    for i, m in enumerate(mem):
        x, y = at[i]
        a = np.asarray(m["spr"])[..., 3] > 0
        lab[y:y + 40, x:x + 32][a] = i
    return lab


def xbrz(img, k=4):
    up = ss.xbrz_scale(np.asarray(img.convert("RGBA"), np.float32)[None], k)[0]
    return Image.fromarray(np.clip(up, 0, 255).astype(np.uint8), "RGBA")


def sil4(mask):
    """Маска k=1 (bool) -> силуэт x4 линиями (xBRZ по маске, как po.smooth_silhouette), БЕЗ заливки дыр:
    окно в стене остаётся окном. 0..1 float."""
    a = mask.astype(np.float32) * 255
    rgba = np.stack([a, a, a, np.full_like(a, 255.0)], -1)[None]
    up = ss.xbrz_scale(rgba, 4)[0][..., 0]
    im = Image.fromarray(np.clip(up, 0, 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(0.7))
    return np.asarray(im, np.float32) / 255.0


def sil4_frame(mask):
    """sil4 для кадра: на вертикальном отрезке силуэта (2+ пикселя базы подряд) перо вынесено наружу. Стык
    двух кадров стены на карте вертикальный, и у обоих мягкий край давал альфу ~0.5 с каждой стороны:
    сквозь стык просвечивал пол тёмной ниткой (C6p, кирпич). Жёсткий край NEAREST лечит стык, но на
    внешнем контуре (торцы цоколя, концы стен) даёт лесенку (C4) - поэтому сдвиг пера, а не отказ от него;
    переход к обычному перу плавный по размытой полосе."""
    s = sil4(mask)
    t = mask[:, :-1] != mask[:, 1:]                   # переход между столбцами x и x+1
    same = mask[1:, :-1] == mask[:-1, :-1]
    v = np.zeros_like(t)
    v[1:] |= t[1:] & t[:-1] & same
    v[:-1] |= t[:-1] & t[1:] & same
    if not v.any():
        return s
    band = np.zeros_like(s)
    for y, x in zip(*np.nonzero(v)):
        c = x * 4 + 4                                 # граница столбцов x4
        band[y * 4:y * 4 + 4, c - 4:c + 4] = 1.0
    w = np.clip(cv2.GaussianBlur(band, (0, 0), 2.0) * 1.5, 0.0, 1.0)
    out = cv2.dilate(s, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    return s + w * (out - s)


def openings(mask):
    """Проёмы кадра k=1: прозрачные пиксели между непрозрачными в той же строке (окно, просвет в заборе,
    проём до пола). Наружный фон сюда не попадает."""
    op = np.zeros_like(mask)
    for r in range(mask.shape[0]):
        xs = np.nonzero(mask[r])[0]
        if len(xs) >= 2:
            op[r, xs[0]:xs[-1] + 1] = ~mask[r, xs[0]:xs[-1] + 1]
    return op


def model_input(frame, zoom):
    panel = po.pick_background(frame)
    big = xbrz(frame).resize((frame.width * zoom, frame.height * zoom), Image.BICUBIC)
    flat = Image.new("RGBA", big.size, tuple(panel) + (255,))
    flat.alpha_composite(big)
    return flat.convert("RGB")


def cut_section(hd, frame, soft, floor=0.30, own=None):
    """Ответ модели -> участок x4: цвет из ответа, альфа - силуэт оригинала x4. Габарит НЕ растягивается
    (R-156): ответ того же кадра, что и вход, - только сдвиг, найденный по маскам, и он в отчёте.
    own - маска k=1 пикселей своих кадров (не контекст): подложка под силуэтом меряется только по ним -
    серая дверь контекста на серой подложке ответа (C4: 0.29 при верной раскладке) не наша."""
    cw, ch = frame.width * 4, frame.height * 4
    a = np.asarray(hd.convert("RGB").resize((cw, ch), Image.LANCZOS), np.float32)
    edge = np.concatenate([a[:8].reshape(-1, 3), a[-8:].reshape(-1, 3),
                           a[:, :8].reshape(-1, 3), a[:, -8:].reshape(-1, 3)])
    bg = tuple(float(v) for v in np.median(edge, axis=0))
    un = po.gen_fire.unpanel(Image.fromarray(a.astype(np.uint8), "RGB"), bg, soft)
    al = np.asarray(un.split()[3], np.float32) / 255.0
    al = np.clip((al - floor) / (1.0 - floor), 0.0, 1.0)
    rgb = np.asarray(un.convert("RGB"), np.float32)
    # подложка - только ровное и связное с краем ответа: теневая грань стены того же серого, что подложка
    # (R-157, C4: подложка 163, тень 150-175), но с фактурой и окружена телом. Её не снимать и не замазывать,
    # цвет брать как есть; обратное смешивание - только в кромке у настоящей подложки
    L = a @ np.float32([0.299, 0.587, 0.114])
    mu = cv2.blur(L, (5, 5))
    sd = np.sqrt(np.maximum(cv2.blur(L * L, (5, 5)) - mu * mu, 0.0))
    flat = (al < 0.5) & (sd < PANEL_STD_MAX)
    n_, cc, st_, _c = cv2.connectedComponentsWithStats(flat.astype(np.uint8), connectivity=4)
    brd = set(np.unique(np.concatenate([cc[0], cc[-1], cc[:, 0], cc[:, -1]]).tolist())) - {0}
    # и подложка внутри замкнутой комнаты (C5): ровный кусок больше 16x16 пикселей базы; стекло окна меньше
    brd |= {k for k in range(1, n_) if st_[k, cv2.CC_STAT_AREA] >= PANEL_HOLE_MIN}
    # и подложка, видная сквозь проём оригинала (окно, щели досок): модель рисует проём шире, и подложка
    # вокруг дыры оставалась телом - бежевые пятна в раме (C6p, C7). Кусок лежит на сквозных пикселях
    # оригинала хотя бы на 30 процентов; теневая грань стоит на непрозрачных и сюда не попадает
    op4 = sil4(openings(np.asarray(frame)[..., 3] > 0)) > 0.5
    op4 = cv2.dilate(op4.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
    hit = np.bincount(cc[op4].ravel(), minlength=n_)
    brd |= {k for k in range(1, n_) if hit[k] >= PANEL_OPEN_SHARE * st_[k, cv2.CC_STAT_AREA]}
    panel = np.isin(cc, sorted(brd))
    rim = (cv2.dilate(panel.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0) & ~panel
    # полупрозрачное в 8 пикселях от подложки - переход в неё (белый блик под концами досок C6p, шире кромки
    # 5x5), а не тело: альфу не поднимать, цвет - от тела. Только светлее подложки: теневая грань того же
    # серого (C4, R-286) темнее неё и остаётся телом
    lbg = float(np.float32(bg) @ np.float32([0.299, 0.587, 0.114]))
    rim |= ((cv2.dilate(panel.astype(np.uint8), np.ones((17, 17), np.uint8)) > 0) & ~panel & (al < 0.5)
            & (L > lbg + 3.0))
    keep = ~panel & ~rim
    rgb[keep] = a[keep]
    # телом становится только то, что не касается подложки: полупрозрачная кромка у подложки (не ровная -
    # переход) с альфой 1 давала бежевую кайму по низу забора C6p и в вырезах досок; она залечивается ниже
    al[keep & (al < 0.5)] = 1.0
    orig = np.asarray(frame)[..., 3] > 0
    sil = sil4(orig)
    # сдвиг ответа против силуэта: фазовая корреляция масок
    (sx, sy), _resp = cv2.phaseCorrelate(sil.astype(np.float64), (al > 0.5).astype(np.float64))
    shift = (int(round(sx)), int(round(sy)))
    if max(abs(shift[0]), abs(shift[1])) <= 12 and shift != (0, 0):
        M = np.float32([[1, 0, -shift[0]], [0, 1, -shift[1]]])
        rgb = cv2.warpAffine(rgb, M, (cw, ch), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        al = cv2.warpAffine(al, M, (cw, ch), flags=cv2.INTER_LINEAR, borderValue=0)
        rim = cv2.warpAffine(rim.astype(np.uint8), M, (cw, ch), flags=cv2.INTER_NEAREST, borderValue=0) > 0
    inside = sil > 0.5
    near = cv2.dilate(inside.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    ring = cv2.dilate(inside.astype(np.uint8), np.ones((17, 17), np.uint8)) > 0
    mine = inside if own is None else inside & (sil4(own) > 0.5)
    raw_m = dict(
        shift=list(shift),
        panel_in=float(((al < 0.5) & mine).sum() / max(1, mine.sum())),
        panel_in_all=float(((al < 0.5) & inside).sum() / max(1, inside.sum())),
        spill=float(((al > 0.5) & ~near).sum() / max(1, inside.sum())),
        spill_near=float(((al > 0.5) & ring & ~near).sum() / max(1, inside.sum())))
    # неизвестна ВСЯ подложка: если известна хоть её часть за силуэтом, inpaint тянет её белый цвет в вырезы
    # силуэта (низ забора C6p - модель нарисовала концы досок выше оригинала, вырез залит кремовым)
    # и кромка у подложки: обратное смешивание оставляет смесь доски с белым розово-белой, и как известный
    # пиксель она тянет этот цвет в вырез силуэта; цвет кромки и выреза - от чистого тела
    hole = (al < 0.5) | rim
    # и пиксель тела на самой границе с неизвестным: LANCZOS смешал его с подложкой (C6p: 172,149,148 при
    # альфе 1 над белым), и как известный он один задавал цвет всего выреза под собой
    hole = cv2.dilate(hole.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    if hole.any():
        rgb = cv2.inpaint(np.clip(rgb, 0, 255).astype(np.uint8), hole.astype(np.uint8), 3,
                          cv2.INPAINT_TELEA).astype(np.float32)
    out = np.dstack([rgb, sil * 255]).astype(np.uint8)
    return Image.fromarray(out, "RGBA"), al, raw_m


def lum(a):
    return a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114


def on_floor_arr(img):
    a = np.asarray(img, np.float32)
    f = np.array(po.FLOOR, np.float32)
    return a[..., :3] * (a[..., 3:4] / 255.0) + f * (1 - a[..., 3:4] / 255.0)


def struct_fid(hd, orig):
    """Строение внутри силуэта (R-210): кадр x4 уменьшен до k=1 против оригинала - корреляция яркости и
    граней по непрозрачному оригиналу."""
    a = np.asarray(hd, np.float32)
    al = a[..., 3:4] / 255.0
    pm = (a[..., :3] * al).reshape(40, 4, 32, 4, 3).mean((1, 3))
    am = al.reshape(40, 4, 32, 4, 1).mean((1, 3))
    small = pm / np.maximum(am, 1e-3)
    o = np.asarray(orig, np.float32)
    m = o[..., 3] > 0
    if m.sum() < 12:
        return None, None, None
    l1, l2 = lum(small), lum(o)
    c = float(np.corrcoef(l1[m], l2[m])[0, 1]) if l1[m].std() > 1e-3 and l2[m].std() > 1e-3 else None

    def grad(l):
        gx = cv2.Sobel(l.astype(np.float32), cv2.CV_32F, 1, 0)
        gy = cv2.Sobel(l.astype(np.float32), cv2.CV_32F, 0, 1)
        return np.hypot(gx, gy)
    g1, g2 = grad(l1), grad(l2)
    e = float(np.corrcoef(g1[m], g2[m])[0, 1]) if g1[m].std() > 1e-3 and g2[m].std() > 1e-3 else None
    dc = float(np.abs(small[m] - o[..., :3][m]).mean())
    return c, e, dc


def row_edges(mask):
    rows = {}
    for r in range(mask.shape[0]):
        xs = np.nonzero(mask[r])[0]
        if len(xs):
            rows[r] = (xs[0], xs[-1])
    return rows


def edge_diff(hd, orig):
    """Край кадра по строкам, верх и низ - против оригинала, в пикселях базы."""
    a = np.asarray(hd, np.float32)[..., 3].reshape(40, 4, 32, 4).mean((1, 3)) > 127
    o = np.asarray(orig)[..., 3] > 0
    ra, ro = row_edges(a), row_edges(o)
    if not ro:
        return 0
    if not ra:
        return 99
    d = abs(min(ra) - min(ro)) + 0
    d = max(d, abs(max(ra) - max(ro)))
    for r in set(ra) & set(ro):
        d = max(d, abs(int(ra[r][0]) - int(ro[r][0])), abs(int(ra[r][1]) - int(ro[r][1])))
    return int(d)


def vertices(mem):
    """Вершины сетки: N(x,y) - ребро (x,y)-(x+1,y), W(x,y) - (x,y)-(x,y+1). -> {(vx,vy): [(метка, i)]}"""
    inc = defaultdict(list)
    for i, m in enumerate(mem):
        x, y = m["x"], m["y"]
        if m["part"] == 2:
            inc[(x, y)].append(("Ne", i))
            inc[(x + 1, y)].append(("Nw", i))
        elif m["part"] == 1:
            inc[(x, y)].append(("Ws", i))
            inc[(x, y + 1)].append(("Wn", i))
    return inc


def vclass(labels):
    s = set(labels)
    if len(labels) == 1:
        return "торец"
    if len(labels) >= 3:
        return "T_X"
    if s == {"Ne", "Ws"}:
        return "угол_внутренний"
    if s == {"Nw", "Wn"}:
        return "угол_внешний"
    return "прямая"


def seams(lab4, built, whole, pairs_only=None):
    """Ступень яркости поперёк стыка двух частей: сборка из кадров против целого рисунка.
    -> {(i, j): (пикселей, ступень сборки, ступень целого, лишняя)}"""
    lb, lw = lum(on_floor_arr(built)), lum(on_floor_arr(whole))
    acc = defaultdict(lambda: [0, 0.0, 0.0])
    for dy, dx in ((0, 1), (1, 0)):
        a = lab4[:lab4.shape[0] - dy, :lab4.shape[1] - dx]
        b = lab4[dy:, dx:]
        m = (a >= 0) & (b >= 0) & (a != b)
        if not m.any():
            continue
        ys, xs = np.nonzero(m)
        sb = np.abs(lb[ys, xs] - lb[ys + dy, xs + dx])
        sw = np.abs(lw[ys, xs] - lw[ys + dy, xs + dx])
        ia, ib = a[ys, xs], b[ys, xs]
        lo_, hi_ = np.minimum(ia, ib), np.maximum(ia, ib)
        for u, v, x1, x2 in zip(lo_, hi_, sb, sw):
            r = acc[(int(u), int(v))]
            r[0] += 1
            r[1] += float(x1)
            r[2] += float(x2)
    out = {}
    for k, (n, s1, s2) in acc.items():
        if n >= 12 and (pairs_only is None or k in pairs_only):
            out[k] = (n, s1 / n, s2 / n, s1 / n - s2 / n)
    return out


def ctx_frame(m):
    p = os.path.join(po.MOD_TERRAIN, m["set"].upper() + ".PCK", "%d.png" % m["frame"])
    if os.path.exists(p):
        im = Image.open(p).convert("RGBA")
        return im if im.size == (128, 160) else im.resize((128, 160), Image.LANCZOS), "pack"
    return xbrz(m["full"]), "xbrz"


def lumsat(spr):
    a = np.asarray(spr, np.float32)
    m = a[..., 3] > 0
    if m.sum() < 20:
        return None, None
    rgb = a[..., :3][m] / 255.0
    mx, mn = rgb.max(1), rgb.min(1)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    return float(lum(rgb * 255).mean()), float(sat.mean())


def cut_weight(w, body, joint, band):
    """Полоса стыка не смешиванием, а резом по линии наименьшей разницы (как сшивка лоскутов): у кадра
    тело с одного места, полоса с другого, кирпич у них в разной фазе, и линейное смешение 0..band даёт
    двойной шов посередине полосы. Глубина реза d_y своя в каждой строке (|d_y - d_y-1| <= 1), стоимость -
    разница тела и полосы на линии реза; по обе стороны линии перо в 1.5 пикселя."""
    reg = w > 0
    if not reg.any():
        return w
    d = band * (1.0 - w)
    diff = np.abs(cv2.GaussianBlur(body, (0, 0), 1.0) - cv2.GaussianBlur(joint, (0, 0), 1.0)).sum(-1)
    lo_, hi_ = 3, max(4, band - 3)
    D = np.arange(lo_, hi_ + 1)
    rows = [y for y in range(w.shape[0]) if reg[y].any()]
    cost = np.zeros((len(rows), len(D)), np.float32)
    for r, y in enumerate(rows):
        dy, fy = d[y][reg[y]], diff[y][reg[y]]
        for k, dd in enumerate(D):
            on = np.abs(dy - dd) <= 1.0
            cost[r, k] = fy[on].mean() if on.any() else 0.0
    acc = cost.copy()
    back = np.zeros(cost.shape, np.int32)
    for r in range(1, len(rows)):
        for k in range(len(D)):
            ks = range(max(0, k - 1), min(len(D), k + 2))
            j = min(ks, key=lambda j_: acc[r - 1, j_])
            back[r, k] = j
            acc[r, k] += acc[r - 1, j]
    k = int(np.argmin(acc[-1]))
    cutd = np.zeros(w.shape[0], np.float32)
    for r in range(len(rows) - 1, -1, -1):
        cutd[rows[r]] = D[k]
        k = back[r, k]
    out = np.clip((cutd[:, None] - d + 1.5) / 3.0, 0.0, 1.0) * reg
    return out.astype(np.float32)


def assemble(mem, at, size, lab, cut, band):
    """Участок x4 -> кадры {(НАБОР, кадр): RGBA 128x160} и сведения по кадрам."""
    lab4 = np.repeat(np.repeat(lab, 4, 0), 4, 1)
    cutA = np.asarray(cut, np.float32)
    paint = [i for i, m in enumerate(mem) if m["role"] == "paint"]
    piece, vis = {}, {}
    for i in paint:
        x, y = at[i]
        piece[i] = cutA[y * 4:y * 4 + 160, x * 4:x * 4 + 128]
        v = (lab4[y * 4:y * 4 + 160, x * 4:x * 4 + 128] == i).astype(np.float32)
        # перо в пиксель базы: соседние места кадра сходятся без резкого шва
        vis[i] = cv2.GaussianBlur(cv2.erode(v, np.ones((3, 3), np.uint8)), (0, 0), 1.5) * v
    frames = defaultdict(list)
    for i in paint:
        frames[(mem[i]["set"].upper(), mem[i]["frame"])].append(i)
    out, info = {}, {}
    for f, inst in frames.items():
        own = np.asarray(mem[inst[0]]["full"])[..., 3] > 0
        sil = sil4_frame(own)
        order = sorted(inst, key=lambda i: -vis[i].sum())
        acc = np.zeros((160, 128, 3), np.float32)
        cover = np.zeros((160, 128), np.float32)
        for i in order:
            w = vis[i] * (1.0 - cover)
            acc += piece[i][..., :3] * w[..., None]
            cover += w
        fb = np.asarray(xbrz(mem[inst[0]]["full"]), np.float32)[..., :3]
        rgb = acc + fb * (1.0 - cover)[..., None]
        unseen = float(((1.0 - cover) * (sil > 0.5)).sum() / max(1, (sil > 0.5).sum()))
        img = np.dstack([rgb, sil * 255])
        out[f] = img
        info[f] = dict(places=len(inst), base="%d,%d" % (mem[order[0]]["x"], mem[order[0]]["y"]),
                       unseen=round(unseen, 3))
    # стыки: у КАЖДОГО кадра на КАЖДОМ его конце своя эталонная вершина (long_object.unify, но не одна пара
    # на ось: иначе второй повторяющийся кадр оси остаётся без сводки - шов на каждой клетке). Конфигурация
    # конца - что стоит в вершине рядом (прямая, угол, T); берётся самая частая у этого кадра, полоса у
    # стыка - из рисунка на эталонном месте этой конфигурации.
    fo = lambda i: (mem[i]["set"].upper(), mem[i]["frame"])          # noqa: E731
    ends = defaultdict(lambda: defaultdict(list))     # f -> конец -> [(конфигурация, i, соседи)]
    for _v, lst in vertices(mem).items():
        for lab_, i in lst:
            if mem[i]["role"] != "paint" or mem[i]["part"] == 3:
                continue
            nb = [j for l_, j in lst if j != i]
            if not nb:
                continue
            conf = tuple(sorted((l_, fo(j)) for l_, j in lst if j != i))
            ends[fo(i)][lab_].append((conf, i, nb))
    refs, chosen = {}, []
    for f, by_end in ends.items():
        for end, lst in sorted(by_end.items()):
            cnt = defaultdict(int)
            for conf, _i, _nb in lst:
                cnt[conf] += 1
            best = max(cnt, key=lambda c_: (cnt[c_], any(fr == f for _l, fr in c_)))
            pool = [(i, nb) for conf, i, nb in lst if conf == best]
            # стык двух кадров сводится с ОДНОЙ пары мест с обеих сторон: если другой конец уже взял пару,
            # где мы его сосед, берём её же (кадр сам за собой - правая и левая полосы с одного стыка)
            pair = [(i, nb) for i, nb in pool if any(i in nb2 and me2 in nb for me2, nb2 in chosen)]
            me, nb = (pair or pool)[len(pair or pool) // 2]
            chosen.append((me, nb))
            w = np.zeros((160, 128), np.float32)
            for other in nb:
                w = np.maximum(w, lo.joint_weight(lab4, me, other, at[me], band))
            w = cut_weight(w, out[f][..., :3], piece[me][..., :3], band)
            out[f][..., :3] = out[f][..., :3] * (1 - w[..., None]) + piece[me][..., :3] * w[..., None]
            refs["%s:%d %s" % (f[0], f[1], end)] = (me, nb[0], cnt[best], len(lst))
    # мягкая кромка sil4 выходит за силуэт x4 на 1-3 пикселя, а цвет там чёрный (у вырезки и у xBRZ
    # классики за силуэтом пусто): на карте полупрозрачная чёрная кромка ложится на соседа ниткой.
    # Цвет кромки - от ближайших пикселей тела кадра.
    for f, v in out.items():
        own = np.asarray(mem[frames[f][0]]["full"])[..., 3] > 0
        ok = np.repeat(np.repeat(own, 4, 0), 4, 1).astype(np.float32)
        rgb = v[..., :3] * ok[..., None]
        for _ in range(6):
            need = (v[..., 3] > 0) & (ok < 0.5)
            if not need.any():
                break
            s = cv2.blur(rgb, (3, 3))
            n = cv2.blur(ok, (3, 3))
            grow = need & (n > 0)
            rgb[grow] = s[grow] / n[grow][:, None]
            ok[grow] = 1.0
        v[..., :3] = rgb
    res = {f: Image.fromarray(np.clip(v, 0, 255).astype(np.uint8), "RGBA") for f, v in out.items()}
    return res, info, refs, lab4


def case_feats(m, plan, state):
    p = plan.get(m["orig_rec"])
    c = set()
    if not p:
        return c
    for name, subs in SUB.items():
        if p["подкласс"] in subs:
            c.add(name)
    if p["косяк"]:
        c.add("косяк")
    if p["strict"]:
        c.add("strict")
    if p["класс"] == "WALL_EMBEDDED":
        c.add("встроенная")
    if state == "die" and m["rec"] != m["orig_rec"]:
        c.add("повреждение")
    if state == "rubble" and m["rec"] != m["orig_rec"]:
        c.add("обломки")
    lm, sat = lumsat(m["full"])
    if lm is not None and lm < 55:
        c.add("тёмная")
    if lm is not None and (sat > 0.45 or lm > 165):
        c.add("яркая")
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--terrain", required=True)
    ap.add_argument("--block", required=True)
    ap.add_argument("--z", type=int, default=0)
    ap.add_argument("--x0", type=int, required=True)
    ap.add_argument("--y0", type=int, required=True)
    ap.add_argument("--win", type=int, default=8)
    ap.add_argument("--state", default="", choices=["", "die", "rubble"])
    ap.add_argument("--hint", default="")
    ap.add_argument("--hint-key", default="", dest="hint_key")
    ap.add_argument("--hints", default="census/walls/method_check/hints.json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--seeds", default="2711")
    ap.add_argument("--dry-run", action="store_true", dest="dry_run")
    ap.add_argument("--recut", action="store_true", help="нарезать заново из сохранённых raw.png, без модели")
    ap.add_argument("--steps", type=int, default=40)
    ap.add_argument("--cfg", type=float, default=4.0)
    ap.add_argument("--mp", type=float, default=2.0)
    ap.add_argument("--zoom", type=int, default=16)
    ap.add_argument("--soft", type=int, default=40)
    ap.add_argument("--pad", type=int, default=3)
    ap.add_argument("--tone", type=float, default=0.7)
    ap.add_argument("--band", type=int, default=24)
    ap.add_argument("--models", default=None)
    ap.add_argument("--model", default="")
    ap.add_argument("--offload", default="model", choices=["model", "seq", "none"])
    args = ap.parse_args()

    what = args.hint
    if not what and args.hint_key:
        with open(args.hints, encoding=ENC) as f:
            what = json.load(f).get(args.hint_key, "")
    if not what and not args.dry_run:
        raise SystemExit("нет описания участка (--hint или --hint-key в %s) - R-007" % args.hints)
    plan = {r["запись"].upper(): r for r in tsv(PLAN)}
    world = mm.World()
    raw = Raw(world)
    mem, notes = members_of(world, raw, plan, args.terrain, args.block, args.z, args.x0, args.y0, args.win,
                            args.state)
    paint = [i for i, m in enumerate(mem) if m["role"] == "paint"]
    if not paint:
        raise SystemExit("в окне нет стен плана")
    size, at = layout(mem)
    whole1 = compose(mem, at, size)
    lab = label_map(mem, at, size)
    bb = whole1.split()[3].getbbox()
    # поле pad вокруг участка - всегда, и за краем холста (crop дополняет прозрачным): стена у края входа
    # без поля - и модель перекраивает раскладку (C6 s2711: сдвиг -170, подложка под силуэтом 0.43).
    # Ответы, нарисованные прежде по входу, обрезанному краем холста, перевырезаются с тем же габаритом.
    box = (bb[0] - args.pad, bb[1] - args.pad, bb[2] + args.pad, bb[3] + args.pad)
    old = (max(0, box[0]), max(0, box[1]), min(whole1.width, box[2]), min(whole1.height, box[3]))
    inp = os.path.join(args.out, "input.png")
    if args.recut and old != box and os.path.exists(inp) and Image.open(inp).size == (
            (old[2] - old[0]) * args.zoom, (old[3] - old[1]) * args.zoom):
        box = old
        print("  габарит входа прежний, обрезанный краем холста: %s" % (box,), flush=True)
    frame = whole1.crop(box)
    os.makedirs(args.out, exist_ok=True)
    whole1.resize((whole1.width * 4, whole1.height * 4), Image.NEAREST).save(os.path.join(args.out, "orig_x4.png"))
    model_input(frame, args.zoom).save(os.path.join(args.out, "input.png"))
    frames = sorted({(m["set"].upper(), m["frame"]) for m in mem if m["role"] == "paint"})
    print("участок %dx%d (k=1): частей %d, рисуется %d (кадров %d), контекст %d; %s" % (
        size[0], size[1], len(mem), len(paint), len(frames), len(mem) - len(paint), what[:100]), flush=True)
    for n in notes:
        print("  " + n, flush=True)
    # сквозные проёмы оригинала: подсказка не должна звать их стеклом (C7 IDT_FARM:8 - застеклён по подсказке)
    seen_op = set()
    for m in mem:
        f = (m["set"].upper(), m["frame"])
        if m["role"] == "paint" and f not in seen_op:
            seen_op.add(f)
            n_op = int(openings(np.asarray(m["full"])[..., 3] > 0).sum())
            if n_op:
                print("  сквозной проём: %s:%d - %d пикс k=1" % (f[0], f[1], n_op), flush=True)
    for m in mem:
        if m["role"] == "ctx":
            print("  контекст: %s %d,%d %s%s" % (m["rec"], m["x"], m["y"], "WNO"[m["part"] - 1],
                                                " дверь" if m["door"] else ""), flush=True)
    if args.dry_run:
        return

    vb = bv.prompt_block("wall")
    prompt = STYLE.replace("{what}", what).replace("{view}", vb["positive"])
    po.gen_fire.NEGATIVE = po.NEGATIVE + ", " + vb["negative"]
    painter = None
    if not args.recut:
        ns = argparse.Namespace(models=args.models or po.gen_hd.DEFAULT_MODELS_DIR, qwen21_model=args.model,
                                qwen21_steps=args.steps, qwen21_cfg=args.cfg, qwen21_mp=args.mp,
                                qwen21_strength=0.0, qwen21_offload=args.offload, qwen21_thrifty=False,
                                qwen21_ref="", qwen21_ref_mp=1.0, qwen21_prompt="strict",
                                qwen21_hint="off", qwen21_ref_order="ref-first")
        painter = po.gen_hd.Qwen21Painter(ns, {"ground": ("", "")})
    with open(os.path.join(args.out, "prompt.txt"), "w", encoding=ENC) as f:
        f.write(prompt + "\n\nNEGATIVE: " + po.gen_fire.NEGATIVE + "\n")

    ctx_img, ctx_src = {}, {}
    for i, m in enumerate(mem):
        if m["role"] == "ctx":
            ctx_img[i], ctx_src[i] = ctx_frame(m)
    inc = vertices(mem)
    feats = {i: case_feats(mem[i], plan, args.state) for i in paint}

    for seed in [int(v) for v in args.seeds.split(",") if v]:
        t0 = time.time()
        d = os.path.join(args.out, "s%d" % seed)
        os.makedirs(d, exist_ok=True)
        if painter is None:
            hd = Image.open(os.path.join(d, "raw.png")).convert("RGB")
        else:
            hd = po.gen_fire.run_pass(painter, args, prompt, model_input(frame, args.zoom), seed)
            po.gen_hd.save_png(hd, os.path.join(d, "raw.png"))
        own = np.zeros((frame.height, frame.width), bool)
        ox_, oy_ = max(0, -box[0]), max(0, -box[1])
        sub = np.isin(lab, paint)[max(0, box[1]):box[3], max(0, box[0]):box[2]]
        own[oy_:oy_ + sub.shape[0], ox_:ox_ + sub.shape[1]] = sub
        part, al_raw, raw_m = cut_section(hd, frame, args.soft, own=own)
        part = po.match_tone(part, frame, args.tone)
        cut = Image.new("RGBA", (size[0] * 4, size[1] * 4), (0, 0, 0, 0))
        cut.paste(part, (box[0] * 4, box[1] * 4))
        alr = np.zeros((size[1] * 4, size[0] * 4), np.float32)
        y0_, x0_ = box[1] * 4, box[0] * 4
        sy_, sx_ = max(0, -y0_), max(0, -x0_)
        h_ = min(al_raw.shape[0], alr.shape[0] - y0_) - sy_
        w_ = min(al_raw.shape[1], alr.shape[1] - x0_) - sx_
        alr[y0_ + sy_:y0_ + sy_ + h_, x0_ + sx_:x0_ + sx_ + w_] = al_raw[sy_:sy_ + h_, sx_:sx_ + w_]
        out, info, refs, lab4 = assemble(mem, at, size, lab, cut, args.band)
        for (s, f), im in out.items():
            os.makedirs(os.path.join(d, "series", s + ".PCK"), exist_ok=True)
            po.gen_hd.save_png(im, os.path.join(d, "series", s + ".PCK", "%d.png" % f))
        imgs = [out[(m["set"].upper(), m["frame"])] if m["role"] == "paint" else ctx_img[i]
                for i, m in enumerate(mem)]
        built = compose(mem, at, size, imgs, 4)
        # проверки по кадрам
        fr_rep = {}
        for f, im in out.items():
            inst = [i for i in paint if (mem[i]["set"].upper(), mem[i]["frame"]) == f]
            orig = mem[inst[0]]["full"]
            om = np.asarray(orig)[..., 3] > 0
            op = openings(om)
            op4 = np.repeat(np.repeat(op, 4, 0), 4, 1)
            # закрыт ли проём в итоге - по внутренности проёма: кромка в 1 пиксель x4 - сглаживание силуэта
            # (sil4, xBRZ + размытие 0.7), а не закрытый проём; просвет доски в 1 пиксель базы сохраняет 2
            op4i = cv2.erode(op4.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
            fa = np.asarray(im)[..., 3] > 127
            raw_closed = []
            for i in inst:
                x, y = at[i]
                v = (lab4[y * 4:y * 4 + 160, x * 4:x * 4 + 128] == -1) & op4
                if v.sum() >= 16:       # проём виден здесь (не закрыт другой стеной)
                    raw_closed.append(float((alr[y * 4:y * 4 + 160, x * 4:x * 4 + 128][v] > 0.5).mean()))
            c, e, dc = struct_fid(im, orig)
            fr_rep["%s:%d" % f] = dict(
                info[f], records=sorted({mem[i]["rec"] for i in inst}),
                edge=edge_diff(im, orig), open_px=int(op.sum()),
                open_raw=round(max(raw_closed), 3) if raw_closed else None,
                open_fin=round(float(fa[op4i].mean()), 3) if op4i.any() else None,
                lum_corr=None if c is None else round(c, 3), edge_corr=None if e is None else round(e, 3),
                col_diff=None if dc is None else round(dc, 1))
        sm = seams(lab4, built, cut)
        # случаи
        cases = {c: dict(frames=set(), pairs=set(), where=[]) for c in CASES}
        for i in paint:
            for c in feats[i]:
                cases[c]["frames"].add("%s:%d" % (mem[i]["set"].upper(), mem[i]["frame"]))
                cases[c]["where"].append("%d,%d%s" % (mem[i]["x"], mem[i]["y"], "WNO"[mem[i]["part"] - 1]))
        for (vx, vy), lst in inc.items():
            ids = [i for _l, i in lst]
            if not any(mem[i]["role"] == "paint" for i in ids):
                continue
            vc = vclass([l_ for l_, _i in lst])
            prs = {(min(a, b), max(a, b)) for a in ids for b in ids if a < b}
            cases[vc]["pairs"] |= prs
            cases[vc]["where"].append("v%d,%d" % (vx, vy))
            for i in ids:
                if mem[i]["role"] == "paint":
                    cases[vc]["frames"].add("%s:%d" % (mem[i]["set"].upper(), mem[i]["frame"]))
            if any(mem[i]["door"] for i in ids) and any(mem[i]["role"] == "paint" for i in ids):
                cases["стык_раздвижной"]["pairs"] |= {p_ for p_ in prs if mem[p_[0]]["door"] or mem[p_[1]]["door"]}
                cases["стык_раздвижной"]["where"].append("v%d,%d" % (vx, vy))
        emb = [i for i in paint if mem[i]["part"] == 3]
        for i in emb:
            cases["встроенная"]["pairs"] |= {k_ for k_ in sm if i in k_}
        verdict = {}
        for c, v in cases.items():
            if not v["frames"] and not v["pairs"]:
                verdict[c] = dict(verdict="нет в участке")
                continue
            bad, info_ = [], []
            for f in sorted(v["frames"]):
                r = fr_rep[f]
                if r["edge"] > EDGE_MAX:
                    bad.append("%s край %d" % (f, r["edge"]))
                if r["unseen"] > UNSEEN_MAX:
                    bad.append("%s невидимо %.2f" % (f, r["unseen"]))
                if r["open_fin"] is not None and r["open_fin"] > OPEN_FIN_MAX:
                    bad.append("%s проём закрыт в кадре %.2f" % (f, r["open_fin"]))
                if r["open_raw"] is not None and r["open_raw"] > OPEN_RAW_MAX:
                    # альфа кадра - силуэт оригинала, проём открыт (open_fin), но в раме остаются куски того,
                    # чем модель его закрыла (C7 IDT_FARM:8: стекло рваными пятнами) - на лист человеку
                    bad.append("%s модель закрыла проём %.2f" % (f, r["open_raw"]))
            measured = [sm[p_] for p_ in v["pairs"] if p_ in sm]
            worst = max((x[3] for x in measured), default=None)
            for p_ in v["pairs"]:
                if p_ in sm and sm[p_][3] > SEAM_MAX:
                    a, b = mem[p_[0]], mem[p_[1]]
                    bad.append("шов %s %d,%d%s|%s %d,%d%s +%.1f" % (
                        a["rec"], a["x"], a["y"], "WNO"[a["part"] - 1], b["rec"], b["x"], b["y"],
                        "WNO"[b["part"] - 1], sm[p_][3]))
            verdict[c] = dict(verdict="PASS" if not bad else "REVIEW", frames=sorted(v["frames"]),
                              joints=len(measured), worst_seam=None if worst is None else round(worst, 1),
                              where=v["where"][:12], problems=bad[:12], info=info_[:12])
        # раскладка ответа не та (модель уменьшила, сдвинула, перекроила участок): вырезка по силуэту
        # оригинала даёт мусор, швы и края ничего не значат - весь участок на перерисовку
        lay = []
        if raw_m["panel_in"] > LAYOUT_PANEL_MAX:
            lay.append("подложка под силуэтом %.2f" % raw_m["panel_in"])
        if max(abs(raw_m["shift"][0]), abs(raw_m["shift"][1])) > LAYOUT_SHIFT_MAX:
            lay.append("сдвиг ответа %s" % raw_m["shift"])
        if lay:
            for v in verdict.values():
                if v["verdict"] != "нет в участке":
                    v["verdict"] = "RERENDER"
                    v["problems"] = ["раскладка ответа не совпала с входом: " + ", ".join(lay)]
        rep = dict(terrain=args.terrain, block=args.block, z=args.z, x0=args.x0, y0=args.y0, state=args.state,
                   seed=seed, what=what, raw=raw_m, frames=fr_rep,
                   refs={k_: ["%d,%d%s" % (mem[a]["x"], mem[a]["y"], "WNO"[mem[a]["part"] - 1]),
                              "%d,%d%s" % (mem[b]["x"], mem[b]["y"], "WNO"[mem[b]["part"] - 1]),
                              "%d из %d" % (n_, t_)]
                         for k_, (a, b, n_, t_) in refs.items()},
                   ctx={"%s %d,%d%s" % (mem[i]["rec"], mem[i]["x"], mem[i]["y"], "WNO"[mem[i]["part"] - 1]): s_
                        for i, s_ in ctx_src.items()},
                   seams={"%d,%d%s|%d,%d%s" % (mem[a]["x"], mem[a]["y"], "WNO"[mem[a]["part"] - 1],
                                               mem[b]["x"], mem[b]["y"], "WNO"[mem[b]["part"] - 1]):
                          [n, round(s1, 1), round(s2, 1), round(ex, 1)] for (a, b), (n, s1, s2, ex) in sm.items()},
                   cases=verdict, notes=notes)
        with open(os.path.join(d, "report.json"), "w", encoding=ENC) as f:
            json.dump(rep, f, ensure_ascii=False, indent=1)
        # листы: оригинал x4 | целиком | из кадров | разница; кадры отдельно
        o4 = whole1.resize((whole1.width * 4, whole1.height * 4), Image.NEAREST)
        diff = np.abs(on_floor_arr(built) - on_floor_arr(cut)).max(-1) > 24
        dimg = Image.fromarray(on_floor_arr(built).astype(np.uint8), "RGB")
        da = np.asarray(dimg).copy()
        da[diff] = (255, 0, 255)
        W, H = o4.width, o4.height
        sheet = Image.new("RGB", (W * 2 + 8, H * 2 + 40), (30, 30, 34))
        dr = ImageDraw.Draw(sheet)
        for j, (im, t) in enumerate(((lo.on_floor(o4), "original x4"), (lo.on_floor(cut), "painted as one section"),
                                     (lo.on_floor(built), "assembled from frames (doors: game pack)"),
                                     (Image.fromarray(da), "built vs painted: magenta > 24"))):
            x, y = (j % 2) * (W + 8), (j // 2) * (H + 20)
            dr.text((x + 4, y + 2), t, fill=(255, 255, 0))
            sheet.paste(im, (x, y + 16))
        sheet.save(os.path.join(d, "sheet.png"))
        keys = sorted(out)
        fs = Image.new("RGB", (len(keys) * 272 + 8, 200), (30, 30, 34))
        dr = ImageDraw.Draw(fs)
        for j, f in enumerate(keys):
            inst = [i for i in paint if (mem[i]["set"].upper(), mem[i]["frame"]) == f]
            fs.paste(lo.on_floor(mem[inst[0]]["full"].resize((128, 160), Image.NEAREST)), (j * 272 + 4, 30))
            fs.paste(lo.on_floor(out[f]), (j * 272 + 136, 30))
            dr.text((j * 272 + 4, 4), "%s:%d" % f, fill=(255, 255, 0))
            r = fr_rep["%s:%d" % f]
            dr.text((j * 272 + 4, 16), "x%d unseen %.2f lc %s" % (r["places"], r["unseen"], r["lum_corr"]),
                    fill=(200, 200, 200))
        fs.save(os.path.join(d, "frames.png"))
        npass = sum(1 for v in verdict.values() if v["verdict"] == "PASS")
        nrev = sum(1 for v in verdict.values() if v["verdict"] == "REVIEW")
        nrr = sum(1 for v in verdict.values() if v["verdict"] == "RERENDER")
        print("s%d: кадров %d, случаи PASS %d REVIEW %d RERENDER %d; сдвиг ответа %s, подложка под силуэтом %.3f, "
              "краска вне %.3f; %s" % (seed, len(out), npass, nrev, nrr, raw_m["shift"], raw_m["panel_in"], raw_m["spill"],
                            po.gen_hd.human_time(time.time() - t0)), flush=True)


if __name__ == "__main__":
    main()
