"""TREE_RENDER_V2: исправление V1 по решению специалиста 09.10 - только четыре места, остальное из V1.

  * LAYER CANONICAL: один номер кадра - одна картинка. Кадр берётся из того состояния, где верна его
    собственная верхняя граница или срез, и дальше не меняется:
      42-47 и 53-55 - FULL (MAIN; 53-55 с места на этаже 2, в классике у них среза нет),
      48-52, 56     - Z1_EXPOSED (вид без этажа 2),
      57            - Z0_EXPOSED (вид без этажей 1-2).
    TREE_FULL / TREE_Z1_EXPOSED / TREE_Z0_EXPOSED - только источники, в игру не идут.
  * Срез z1 (FOREST и WASTE) перерисован ТЕМ ЖЕ промптом и сидом V1, но со структурным замком: в свободном
    месте до сигмы release латенты - зашумлённое условие, а в условии там классика вида z<=1 (число, место,
    размер и высота спилов - из классики, модель улучшает только материал). Кадры 53-55 на этаже 1 в замке
    - их канонические картинки, срез рисуется вокруг них.
  * Шов ствола z0 - без генерации: срез ствола V1 переносится по строкам в профиль ствола классики, у шва
    профиль и цвет сходятся к корням MAIN; корни - кадра 57, вторых корней и юбки нет, отрывков рядом нет.
  * Цвет ствола FOREST: сдвиг a*b* (Lab) к красно-бурому классики 57, форма и яркость не меняются.

  tree_render_v2.py --mask-only        холсты замка z1 и лист шва z0, без модели
  tree_render_v2.py [--max-renders 4]  рендер срезов z1 (только через gpuq)
  tree_render_v2.py --assemble         кадры, сборки T1/T1b/T2/T3, листы, ворота, без модели
  --dry                                вместо ответа модели взять условие (контроль тождества, R-299)

Ответы MAIN и CUT_Z0 - из V1 (--v1), не перерисовываются.
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
for p in (HERE, os.path.dirname(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np                                  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter       # noqa: E402
import cv2                                          # noqa: E402
import probe_object as po                           # noqa: E402
import map_mockup as mm                             # noqa: E402
import tree_render as tr                            # noqa: E402

ENC = "utf-8-sig"
OUT = "census/trees/forest42/render_v2"
V1 = "census/trees/forest42/render_v1"
FULL_FRAMES = (42, 43, 44, 45, 46, 47, 53, 54, 55)
Z1_FRAMES = (48, 49, 50, 51, 52, 56)
LOCK_Z1 = (53, 54, 55)                 # на этаже 1 - канон FULL, срез вокруг них
CUT_SPOT_FRAMES = (48, 50, 51)
SPECK_MAX = 1.5      # пикс k=1: пятно меры spots_lab меньше - крапина, не спил (spot_gate)
# цепочка переходного серого снег|хвоя (SNOW после матта по контуру, 13.10): заполненность рамки 0.20-0.36, толщина
# 1.9-3.8 пикс x4; настоящие спилы пяти наборов - от 0.49 и 2.7, синтетический лишний спил r4-r8 - от 0.46 и 8.2
CHAIN_FILL = 0.4
CHAIN_THICK = 1.0    # пикс k=1
BLEND = 40                             # строк x4 над швом, где профиль ствола сходится к корням MAIN
TONE_DECAY = 48                        # строк x4 затухания поправки цвета над швом
TOP_FLAT = 4                           # строк k=1 под спилом, ширина которых держит верх ствола
NARROW_CUT = 0.8                       # срез V1 уже этой доли своей ширины - торец, источник ствола кончается выше
NARROW_BACK = 3                        # строк x4 выше начала сужения: закругление начинается раньше заметного
THIN_BAND = 8                          # строк x4 над и под швом z<=0, где ищутся тонкие обрывки вне ствола
THIN_MAX = 3                           # обрывок не толще стольких строк x4 по столбцу
THIN_LEN = 4                           # и не короче стольких столбцов: отдельный пиксель края - не штрих
SEAM_SOFT = 4                         # строк над и под швом z<=0, где волокна ствола размываются в корни
# составной срез z1 (--z1-composite): сдвиги клона тела яруса MAIN (x4) и материал крышек - пень FOREST:58 s2712
CLONE_SHIFTS = ((16, 0), (32, 0), (16, 16), (16, -16), (48, 0), (32, 32), (32, -32), (64, 0))
STUMP_SRC = "census/trees/forest42/render_v1/s2712/stumps/FOREST.PCK/58.png"
# просветы внутри кроны (решение 12.10): MAIN мёртвого дерева сквозит между ветками, на сборке это квадраты пола.
# Только набор из списка (канон FOREST не трогается), только дыры в глубине кроны (оболочка HOLE_HULL x4 минус
# полоса HOLE_MARGIN у края: кромка из веток - силуэт, её не трогаем), заливка ПОД существующим - клон MAIN
# того же дерева со сдвигом; непрозрачное, силуэт и спилы не меняются
HOLE_FILL_SETS = ("FOREST_WASTE",)
# производные деревья (решение 12.10): FORESTRED, BLACKFOREST, FOREST_SNOW - той же архитектурой, что FOREST. Альфа
# кадров 42-57 у них та же, что у FOREST, а цвета свои: маски по цвету классики (ствол, хвоя веток, торец, спилы)
# строятся по спрайту FOREST, средние цвета и материал - по классике своего набора; пень - свой канон, если есть
GEOM_FROM = {S: "FOREST" for S in tr.DERIVED}
STUMP_OWN = {"BLACKFOREST": "census/trees/forest42/render_v1/s2712/stumps/BLACKFOREST.PCK/58.png"}
# кора кадра 57 по положению, а не по цвету: у RED хвоя рыжая, как кора, у BLACK чёрная, как тень коры - needles_hd
# считал тень ствола хвоей, и сдвиг её не трогал (BLACK L 10 против 15.5). На z<=0 в рамке 57 только ствол и корни
# (ветки дорисованы позже), поэтому там кора - всё непрозрачное. У SNOW хвоя зелёная, а на корнях снег - по цвету
POS_BARK = ("FORESTRED", "BLACKFOREST")
# кадр 57 канона геометрии (FOREST s2712): пятна классики, побайтно равные FOREST, берутся из него
GEOM_F57 = "census/trees/forest42/render_v2/s2712/%s/comp/frames/%s.PCK/57.png"


def geom(S):
    return GEOM_FROM.get(S, S)


def stump_src(S):
    return STUMP_OWN.get(S, STUMP_SRC)
HOLE_HULL = 15
HOLE_MARGIN = 12
HOLE_SHIFTS = CLONE_SHIFTS + ((-16, 0), (-32, 0), (0, 16), (0, -16), (-16, 16), (-16, -16), (0, 32), (0, -32),
                              (48, 48), (48, -48), (-32, 32), (-32, -32), (96, 0), (0, 64), (0, -64))
def _js(o):
    """numpy-скаляры (bool_, float32) в json."""
    return o.item() if hasattr(o, "item") else str(o)


STRAY_MAX = 400                       # оторванные от ствола куски в кадре 57 меньше этого (пикс x4) - прочь


# ---------------------------------------------------------------- общее

def untone(img, p, amount):
    """Обратное tr.apply_tone: вид (тон MAIN) -> цвета ответа модели, чтобы класть в холст замка."""
    ms, gain, mo = p
    c = np.asarray(img, np.float32).copy()
    k = 1.0 - amount + amount * gain
    c[..., :3] = np.clip((c[..., :3] - amount * (mo - ms * gain)) / k, 0, 255)
    return Image.fromarray(c.astype(np.uint8), "RGBA")


def pos_box(q):
    x, y = q["at"]
    return (x * 4, y * 4, x * 4 + 128, y * 4 + 160)


def frame_from(view, q, extra=None):
    """Кадр x4: вид под маской рисования куска на его месте; extra - добавка к маске x4 (0..1) в координатах кадра."""
    v = np.asarray(view, np.uint8).copy()
    d = tr.rep4(q["draw"]).astype(np.float32)
    if extra is not None:
        x0, y0, x1, y1 = pos_box(q)
        d[y0:y1, x0:x1] = np.maximum(d[y0:y1, x0:x1], extra)
    v[..., 3] = np.round(v[..., 3] * d).astype(np.uint8)
    return Image.fromarray(v).crop(pos_box(q))


def draw_extra(t, q, view):
    """Добавка к маске кадра q (x4, его координаты, 0..1): кайма других экземпляров того же кадра. У экземпляра
    нижнего этажа соседей меньше и кайма шире - на срезе z<=1 кадр, вырезанный по верхнему экземпляру, оставлял
    квадратные просветы. Только в глубине кроны (crown_interior) и на срезе экземпляра, и на полном виде; край
    добавки - мягкий, пучками хвои вида (_soft), а не прямой срез по оболочке."""
    deep = {}

    def interior(z):
        if z not in deep:
            u = np.zeros_like(q["draw"])
            for p in t.pcs:
                if p["z"] <= z:
                    u |= p["draw"]
            deep[z] = crown_interior(tr.rep4(u).astype(np.float32) * 255.0)
        return deep[z]

    def win(m, p):
        x0, y0, x1, y1 = pos_box(p)
        return m[y0:y1, x0:x1]

    ext = np.zeros((160, 128), bool)
    for p in t.pcs:
        if p["f"] == q["f"] and p is not q:
            ext |= win(tr.rep4(p["draw"]), p) & win(interior(p["z"]), p)
    own = win(tr.rep4(q["draw"]), q)
    ext &= win(interior(t.top), q) & ~own
    if not ext.any():
        return None
    eb = ext.reshape(40, 4, 32, 4).mean((1, 3)) > 0.5
    x, y = q["at"]
    v = np.asarray(Image.fromarray(np.asarray(view, np.uint8)).crop(pos_box(q)), np.float32)
    Y = v[..., :3].mean(-1)
    c = dict(tn=np.clip((cv2.GaussianBlur(Y, (0, 0), 1.5) - cv2.GaussianBlur(Y, (0, 0), 6)) / 14.0, -1, 1))
    soft = _soft(c, eb | q["draw"][y:y + 40, x:x + 32])
    near = cv2.dilate(ext.astype(np.uint8), np.ones((2 * EDGE_R + 1, 2 * EDGE_R + 1), np.uint8)) > 0
    return np.where(near & ~own, soft, 0).astype(np.float32)


def frame_filled(view0, view, q, extra=None):
    """Кадр из вида с залитыми просветами (fill_crown_holes): под маской рисования - залитый вид, вне её RGB
    незалитого view0 (кромка edge_rule берёт продолжение оттуда - край и обрезы кадра прежние)."""
    a = np.asarray(frame_from(view, q, extra)).copy()
    b = np.asarray(frame_from(view0, q))
    out = a[..., 3] == 0
    a[out] = b[out]
    return Image.fromarray(a)


# ---------------------------------------------------------------- кромка кадра по всем раскладкам
# Один номер кадра - одна картинка, а соседи у кадра в раскладках разные (T1/T1b/T2/T3/clump, этажи z<=1,
# z<=2, все). Край кадра, вырезанный по маске рисования, в T1 закрыт соседом из того же вида, а в другой
# раскладке открывается: лесенка базы поверх чужого соседа или прямой срез рамкой кадра поверх фона.
# Правило общее, без списка кадров: (1) у кадра ищем места, где хотя бы в одной раскладке виден не тот сосед,
# что в T1 (или фон); (2) там - мягкая кромка наружу из того же вида (продолжение того же дерева, форма -
# гладкий силуэт ядра плюс пучки хвои); у рамки кадра, где она режет крону поверх фона, - затухание внутрь,
# RGB не меняется; (3) в T1 кромка не меняет картинку: где меняет больше EDGE_TOL - запрещена.

EDGE_R = 8          # x4: кромка наружу от ядра кадра (как прежняя верхняя кромка: силуэт +2 пикс базы)
EDGE_IN = 12        # x4: полоса затухания внутрь у рамки кадра
EDGE_TOL = 6        # изменение T1 на полу сверх этого (из 255, макс. канала) - кромка там запрещена
EDGE_FRAMES = tuple(range(42, 57))   # 57 (ствол z<=0) не трогаем


def _lay_rows(world, S, sig, zmax):
    rows = []
    for f, p, x, y, z in sig:
        if z <= zmax:
            rows.append(((z, y, x, p), f, (x - y) * 64, ((x + y) * 8 - z * 24 - tr.plevel(world, S, f)) * 4))
    rows.sort()
    return rows


def _compose(rows, get, M=16):
    """Сборка x4 из массивов кадров (160x128x4, float 0..1): rgb на полу, альфа, владелец (последний с альфой
    >= 0.5), начало холста."""
    x0 = min(r[2] for r in rows) - M
    y0 = min(r[3] for r in rows) - M
    W = max(r[2] for r in rows) - x0 + 128 + M
    H = max(r[3] for r in rows) - y0 + 160 + M
    pm = np.zeros((H, W, 3), np.float32)
    al = np.zeros((H, W), np.float32)
    own = np.full((H, W), -1, np.int32)
    for i, (_k, f, sx, sy) in enumerate(rows):
        a = get(i, f)
        ox, oy = sx - x0, sy - y0
        sa = a[..., 3]
        sl = (slice(oy, oy + 160), slice(ox, ox + 128))
        pm[sl] = a[..., :3] * sa[..., None] + pm[sl] * (1 - sa[..., None])
        al[sl] = sa + al[sl] * (1 - sa)
        own[sl][sa >= 0.5] = i
    fl = np.array(tr.FLOOR, np.float32) / 255.0
    return pm + fl * (1 - al[..., None]), al, own, (x0, y0)


def _rel_code(rows, i, own):
    """Кто виден под местом i: код соседа (номер кадра и сдвиг клетки), 0 - фон, -2 - закрыто позже, -3 - сам."""
    (z, y, x, _p), _f, _sx, _sy = rows[i]
    code = np.zeros(own.shape, np.int64)
    for g in np.unique(own):
        if g < 0:
            continue
        m = own == g
        if g == i:
            code[m] = -3
        elif g > i:
            code[m] = -2
        else:
            (zg, yg, xg, _pg), fg, _a, _b = rows[g]
            code[m] = fg * 1000000 + (zg - z + 50) * 10000 + (yg - y + 50) * 100 + (xg - x + 50)
    return code


def _local(arr, org, rows, i, M=0):
    x0, y0 = org
    _k, _f, sx, sy = rows[i]
    ox, oy = sx - x0, sy - y0
    return arr[oy - M:oy + 160 + M, ox - M:ox + 128 + M]


def _layouts(world, CL, S):
    out, seen = [], set()
    for name, li in tr.LAYOUTS[S]:
        sig = CL[S]["sigs"][li]["sig"]
        for zmax in (1, 2, 99):
            rows = _lay_rows(world, S, sig, zmax)
            key = (name, tuple(r[:2] for r in rows))
            if key in seen:
                continue
            seen.add(key)
            out.append((name, zmax, rows))
    return out


def _soft(ch, draw_loc):
    """Мягкая кромка наружу: альфа 0..1 по гладкому силуэту ядра (+EDGE_R) и пучкам хвои вида, как у прежней
    верхней кромки; у рамки кадра сходит на нет."""
    base = Image.fromarray((draw_loc * 255).astype(np.uint8), "L")
    S4 = np.asarray(po.smooth_silhouette(base, 4), np.float32) / 255.0
    inside = (S4 > 0.5).astype(np.uint8)
    sd = cv2.distanceTransform(inside, cv2.DIST_L2, 5) - cv2.distanceTransform(1 - inside, cv2.DIST_L2, 5)
    sd = cv2.GaussianBlur(sd.astype(np.float32), (0, 0), 4.0)
    soft = np.clip((sd + EDGE_R + 2.5 * ch["tn"]) / 1.6 + 0.5, 0, 1)
    yy, xx = np.mgrid[0:160, 0:128].astype(np.float32)
    wbox = np.clip(np.minimum(xx, 127 - xx) / 12.0, 0, 1) * np.clip(np.minimum(yy, 159 - yy) / 6.0, 0, 1)
    return soft * wbox


def _fade(ch, side):
    """Вес затухания у рамки кадра на стороне side: 0 на самой рамке, 1 глубже EDGE_IN, край - по пучкам хвои."""
    yy, xx = np.mgrid[0:160, 0:128].astype(np.float32)
    db = {"L": xx, "R": 127 - xx, "T": yy, "B": 159 - yy}[side]
    return np.clip((db - EDGE_IN / 2 + 2.5 * ch["tn"]) / 1.6 + 0.5, 0, 1)


def _smooth1(m):
    """Отрезки рамки, где она режет крону поверх фона, -> вес 0..1 вдоль рамки с плавным сходом."""
    d = np.convolve(m.astype(np.float32), np.ones(9, np.float32), "same") > 0
    k = np.exp(-0.5 * (np.arange(-12, 13) / 4.0) ** 2)
    return np.clip(np.convolve(d.astype(np.float32), k / k.sum(), "same") * 1.5, 0, 1)


def edge_rule(world, CL, S, frames, srcs, fam):
    """frames: {f: кадр ядра (вырез по маске рисования)}, srcs: {f: (вид x4, q)} - откуда кадр вырезан
    (RGB кадра во всей рамке - RGB вида), fam: {f: источник (FULL, Z1_EXPOSED, Z0_EXPOSED)}.
    Возвращает кадры с кромкой и сводку по кадрам."""
    core = {f: np.asarray(frames[f], np.float32) / 255.0 for f in frames}
    built = []
    for name, zmax, rows in _layouts(world, CL, S):
        rgb, al, own, org = _compose(rows, lambda i, f: core[f])
        built.append((name, rows, rgb, al, own, org))
    out, info = dict(frames), {}
    for f in EDGE_FRAMES:
        view, q = srcs[f]
        v = np.asarray(Image.fromarray(np.asarray(view, np.uint8)).crop(pos_box(q)), np.float32)
        Y = v[..., :3].mean(-1)
        tuft = cv2.GaussianBlur(Y, (0, 0), 1.5) - cv2.GaussianBlur(Y, (0, 0), 6)
        x, y = q["at"]
        c = dict(tn=np.clip(tuft / 14.0, -1, 1))
        ring = core[f][..., 3] < 0.5
        t1, cand = [], []
        cut = {s: np.zeros(160 if s in "LR" else 128, bool) for s in "LRTB"}
        for name, rows, rgb, al, own, org in built:
            for i in [i for i, r in enumerate(rows) if r[1] == f]:
                ow = _local(own, org, rows, i)
                (t1 if name == "T1" else cand).append(_rel_code(rows, i, ow))
                big = _local(al, org, rows, i, 1)
                for s, inn, outv in (("L", ow[:, 0], big[1:-1, 0]), ("R", ow[:, -1], big[1:-1, -1]),
                                     ("T", ow[0, :], big[0, 1:-1]), ("B", ow[-1, :], big[-1, 1:-1])):
                    cut[s] |= (inn == i) & (outv < 0.125)
        # открыто: хотя бы в одной раскладке под краем виден не тот сосед, что в T1 (или фон)
        exp = np.zeros((160, 128), bool)
        for code in cand:
            exp |= (code != -2) & (code != -3) & ring & np.all([code != k for k in t1], 0)
        Ez = cv2.GaussianBlur(cv2.dilate(exp.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(np.float32),
                              (0, 0), 3.0)
        skirt = (v[..., 3] / 255.0) * _soft(c, q["draw"][y:y + 40, x:x + 32]) * np.clip(Ez * 1.5, 0, 1)
        fade = np.ones((160, 128), np.float32)
        for s, m in cut.items():
            if m.any():
                e = _smooth1(m)
                fade *= 1 - (e[:, None] if s in "LR" else e[None, :]) * (1 - _fade(c, s))
        # в T1 кромка не меняет картинку: где меняет - запрещена (с плавным сходом рядом). Исключение - пиксель,
        # где в T1 под кадром уже виден раньше нарисованный кусок ДРУГОГО источника: там шов двух видов есть и в
        # T1, кромка его сглаживает, а не добавляет новое; и пиксель, который в T1 закрыт ПОЗЖЕ нарисованным кадром
        # (кромка видна только сквозь его мягкий край). Фон и раньше нарисованные куски своего источника защищены
        allowed = np.ones((160, 128), np.float32)
        gated, t1_seam = 0, np.zeros((160, 128), bool)
        for _it in range(4):
            a = core[f].copy()
            a[..., 3] = np.maximum(core[f][..., 3] * (1 - (1 - fade) * allowed), skirt * allowed)
            bad = np.zeros((160, 128), bool)
            for name, rows, rgb, al, own, org in built:
                if name != "T1":
                    continue
                other = np.array([fam[r[1]] != fam[f] for r in rows] + [False])
                for i in [i for i, r in enumerate(rows) if r[1] == f]:
                    rgb2 = _compose(rows, lambda j, g, i=i, a=a: a if j == i else core[g])[0]
                    ow = _local(own, org, rows, i)
                    seam = ((ow >= 0) & (ow < i) & other[ow]) | (ow > i)
                    ch = _local(np.abs(rgb2 - rgb).max(-1) * 255.0, org, rows, i) > EDGE_TOL
                    bad |= ch & ~seam
                    t1_seam |= ch & seam
            if not bad.any():
                break
            gated += int(bad.sum())
            forbid = cv2.dilate(bad.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(np.float32)
            allowed = np.minimum(allowed, 1 - np.clip(cv2.GaussianBlur(forbid, (0, 0), 2.0) * 2.0, 0, 1))
            allowed[forbid > 0] = 0
        else:
            a[..., 3][bad] = core[f][..., 3][bad]       # последнее средство: в T1 как было
        out[f] = Image.fromarray(np.clip(np.round(a * 255), 0, 255).astype(np.uint8), "RGBA")
        a8 = np.asarray(out[f])[..., 3].astype(int)
        c8 = np.asarray(frames[f])[..., 3].astype(int)
        info[str(f)] = dict(exposed_px=int(exp.sum()), skirt_px=int(((a8 > 0) & (c8 == 0)).sum()),
                            fade_px=int((a8 < c8).sum()), cut_sides="".join(s for s, m in cut.items() if m.any()),
                            t1_gated_px=gated, t1_seam_px=int(t1_seam.sum()))
    return out, info


def crown_interior(alpha):
    """Глубина кроны: оболочка (замыкание HOLE_HULL и заливка закрытого) минус полоса HOLE_MARGIN x4 у её края.
    Кружевная кромка и ступени нижнего края - это силуэт, в глубину они не входят."""
    solid = (alpha >= 128).astype(np.uint8)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (HOLE_HULL, HOLE_HULL))
    cl = cv2.morphologyEx(solid, cv2.MORPH_CLOSE, k)
    H, W = alpha.shape
    pad = np.pad(1 - cl, 1, constant_values=1)
    mk = np.zeros((H + 4, W + 4), np.uint8)
    cv2.floodFill(pad, mk, (0, 0), 2)
    hull = (pad[1:-1, 1:-1] != 2).astype(np.uint8)
    e = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * HOLE_MARGIN + 1, 2 * HOLE_MARGIN + 1))
    return cv2.erode(hull, e) > 0


ENV_HULL = 31


def envelope_gate(world, CL, S, frames, ref):
    """Заливка просветов не выходит за прежний наружный силуэт: добавленное к ref (альфа выше прежней)
    допускается только там, где место кадра во ВСЕХ раскладках и этажах лежит внутри оболочки сборки из ref
    (замыкание ENV_HULL x4 и заливка закрытого); у края допуска - мягкий сход. Возвращает кадры и число
    срезанных пикселей."""
    core = {f: np.asarray(ref[f], np.float32) / 255.0 for f in ref}
    allow = {f: np.ones((160, 128), bool) for f in frames}
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ENV_HULL, ENV_HULL))
    for _name, _zmax, rows in _layouts(world, CL, S):
        _rgb, al, _own, org = _compose(rows, lambda i, f: core[f])
        solid = np.pad((al >= 0.5).astype(np.uint8), ENV_HULL)
        cl = cv2.morphologyEx(solid, cv2.MORPH_CLOSE, k)
        pad = np.pad(1 - cl, 1, constant_values=1)
        mk = np.zeros((pad.shape[0] + 2, pad.shape[1] + 2), np.uint8)
        cv2.floodFill(pad, mk, (0, 0), 2)
        hull = (pad[1:-1, 1:-1] != 2)[ENV_HULL:-ENV_HULL, ENV_HULL:-ENV_HULL]
        for i, r in enumerate(rows):
            if r[1] in allow:
                allow[r[1]] &= _local(hull, org, rows, i)
    out, cut = dict(frames), 0
    for f in frames:
        a = np.asarray(frames[f]).copy()
        r = np.asarray(ref[f])
        add = a[..., 3] > r[..., 3]
        if not (add & ~allow[f]).any():
            continue
        w = cv2.GaussianBlur(cv2.erode(allow[f].astype(np.uint8), np.ones((3, 3), np.uint8)).astype(np.float32),
                             (0, 0), 1.5) * allow[f]
        lim = np.maximum(r[..., 3].astype(np.float32), a[..., 3] * w)
        cut += int((add & (a[..., 3] >= 128) & (lim < 128)).sum())
        a[..., 3] = np.where(add, np.minimum(a[..., 3], np.round(lim)), a[..., 3]).astype(np.uint8)
        out[f] = Image.fromarray(a, "RGBA")
    return out, cut


def crown_holes(alpha):
    """Просветы внутри кроны: прозрачное (< 128) в глубине кроны (crown_interior)."""
    return crown_interior(alpha) & (alpha < 128)


def fill_crown_holes(view, main):
    """Вид x4 с залитыми просветами кроны: под существующим (вид поверх заливки) - клон MAIN того же дерева
    со сдвигом (первый сдвиг, где MAIN плотный). Непрозрачные пиксели вида не меняются; вне просветов и их
    каймы 2 пикс вид не меняется вовсе. Возвращает вид и число залитых пикселей."""
    v = np.asarray(view, np.float32)
    m = np.asarray(main, np.float32)
    holes = crown_holes(v[..., 3])
    zone = cv2.dilate(holes.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    fcol = np.zeros(v.shape[:2] + (3,), np.float32)
    have = np.zeros(v.shape[:2], bool)
    for dy, dx in HOLE_SHIFTS:
        sh = np.roll(np.roll(m, -dy, 0), -dx, 1)
        ok = zone & ~have & (sh[..., 3] > 230)
        fcol[ok] = sh[..., :3][ok]
        have |= ok
    a = v[..., 3:] / 255.0
    out = v.copy()
    w = have[..., None]
    out[..., :3] = np.where(w, v[..., :3] * a + fcol * (1 - a), v[..., :3])
    out[..., 3] = np.where(have, 255.0, v[..., 3])
    left = int((holes & ~have).sum())
    return Image.fromarray(np.clip(np.round(out), 0, 255).astype(np.uint8), "RGBA"), \
        dict(holes_px=int(holes.sum()), filled_px=int((have & (v[..., 3] < 255)).sum()), left_px=left)


def place(t, frame, q):
    c = Image.new("RGBA", (t.W * 4, t.H * 4), (0, 0, 0, 0))
    c.paste(frame, pos_box(q)[:2])
    return c


def runs(row):
    out, x, n = [], 0, len(row)
    while x < n:
        if row[x]:
            s = x
            while x < n and row[x]:
                x += 1
            out.append((s, x))
        else:
            x += 1
    return out


def run_at(row, cx):
    """Отрезок строки, содержащий cx или ближайший к нему: (x0, x1) или None."""
    best, bd = None, 1e9
    for a, b in runs(row):
        d = 0 if a <= cx < b else min(abs(cx - a), abs(cx - b + 1))
        if d < bd:
            best, bd = (a, b), d
    return best if bd <= 6 else None


def medfilt(v, k):
    v = np.asarray(v, np.float64)
    h = k // 2
    out = v.copy()
    for i in range(len(v)):
        w = v[max(0, i - h):i + h + 1]
        w = w[~np.isnan(w)]
        out[i] = np.median(w) if len(w) else np.nan
    return out


# ---------------------------------------------------------------- шов ствола z0 (без модели)

def classic_trunk(world, S):
    """Профиль ствола классики 57 в строках x4: x0, x1 (сглажено), верх ствола."""
    a = np.asarray(tr.sprite(world, geom(S), 57), np.int16)
    r, g, al = a[..., 0], a[..., 1], a[..., 3]
    m = (al > 0) & ~(g > r + 8)
    cols = np.where(m.any(0))[0]
    cx = int(round(cols.mean()))
    x0 = np.full(40, np.nan)
    x1 = np.full(40, np.nan)
    for y in range(40):
        rr = run_at(m[y], cx)
        if rr:
            x0[y], x1[y] = rr
    x0, x1 = medfilt(x0, 7), medfilt(x1, 7)
    top = int(np.where(~np.isnan(x0))[0][0])
    ref = top + TOP_FLAT                # спил сверху уже ствола на пиксель-два: в HD это «губа», держим ширину
    x0[top:ref] = np.minimum(x0[top:ref], x0[ref])
    x1[top:ref] = np.maximum(x1[top:ref], x1[ref])
    X0 = np.repeat(x0, 4) * 4
    X1 = np.repeat(x1, 4) * 4
    return X0, X1, top * 4, cx * 4 + 2


def classic_needle_bark(world, S):
    """Lab (шкала cv2) хвои и коры классики 57 своего набора; какие пиксели хвоя - по маске FOREST (g > r+8).
    Снег на хвое классики (светлее L 50, хрома меньше 12) в образец хвои не входит: у SNOW он поднимал L хвои
    с ~18 до 29, и тёмная хвоя в тени оказывалась ближе к коре. У RED и BLACK таких пикселей нет."""
    a = np.asarray(tr.sprite(world, S, 57), np.float32)
    ag = np.asarray(tr.sprite(world, geom(S), 57), np.int16)
    nm = (ag[..., 3] > 0) & (ag[..., 1] > ag[..., 0] + 8)
    bm = (ag[..., 3] > 0) & ~nm
    ln = _lab8(a[..., :3][nm])
    sn = (ln[:, 0] > 128) & (np.hypot(ln[:, 1] - 128, ln[:, 2] - 128) < 12)
    return ln[~sn].mean(0), _lab8(a[..., :3][bm]).mean(0), float(sn.mean())


def needles_hd(world, S, rgba):
    """Хвоя на HD производного дерева: пиксель ближе (Lab) к хвое классики 57 своего набора, чем к её коре."""
    cn, cb, _s = classic_needle_bark(world, S)
    rgba = np.asarray(rgba, np.float32)
    L = _lab8(rgba[..., :3].reshape(-1, 3)).reshape(rgba.shape[:2] + (3,))
    return np.linalg.norm(L - cn, axis=-1) < np.linalg.norm(L - cb, axis=-1)


def snow_hd(world, S, rgba):
    """Снег на кроне HD: светлее и хвои, и коры классики 57 своего набора на 20+ по L (0-100) и почти без цвета.
    Снег на хвое - материал кроны (FOREST_SNOW), поэтому пятно для клона хвои его не отвергает. Только у набора,
    где снег есть на хвое классики (доля от 2 процентов): у RED и BLACK серый блик снегом не станет."""
    cn, cb, sf = classic_needle_bark(world, S)
    top = max(cn[0], cb[0])
    rgba = np.asarray(rgba, np.float32)
    if sf < 0.02:
        return np.zeros(rgba.shape[:2], bool)
    L = _lab8(rgba[..., :3].reshape(-1, 3)).reshape(rgba.shape[:2] + (3,))
    return (L[..., 0] > top + 51) & (np.hypot(L[..., 1] - 128, L[..., 2] - 128) < 12)


def z0_trunk(job, world, v0, v2):
    """v0, v2 - виды x4 холста (V1 z<=0 и MAIN). Возвращает новый v0 и числа шва."""
    t = job.tree
    i57 = next(i for i, q in enumerate(t.pcs) if q["f"] == 57)
    q = t.pcs[i57]
    bx = pos_box(q)
    U, own, _F = job.masks(0)
    R = (tr.rep4(U) & (tr.rep4(own) == 0))[bx[1]:bx[3], bx[0]:bx[2]]
    c0 = np.asarray(v0, np.float32)[bx[1]:bx[3], bx[0]:bx[2]].copy()
    c2 = np.asarray(v2, np.float32)[bx[1]:bx[3], bx[0]:bx[2]]
    X0, X1, Tc, cx = classic_trunk(world, job.S)
    tcols = [x for x in range(128) if np.nanmin(X0) <= x < np.nanmax(X1)]
    seamcol = np.array([np.where(R[:, x])[0].max() if R[:, x].any() else -1 for x in range(128)])
    Ys = int(np.median([seamcol[x] for x in tcols if seamcol[x] >= 0]))
    # корни MAIN под швом
    ms = []
    # первые две строки: корни сразу расходятся, среднее по шести давало ствол шире корней - заплечик
    for y in range(Ys + 1, min(160, Ys + 3)):
        rr = run_at(c2[y, :, 3] > 128, cx)
        if rr:
            ms.append(rr)
    m0, m1 = np.mean([a for a, _ in ms]), np.mean([b for _, b in ms])
    # источник: срез ствола V1, только чистая часть (без юбки у корней)
    sx0 = np.full(160, np.nan)
    sx1 = np.full(160, np.nan)
    for y in range(0, Ys + 1):
        if not R[y].any():
            continue
        rr = run_at(c0[y, :, 3] > 128, (m0 + m1) / 2 if y > Ys - 8 else cx)
        if rr and rr[1] - rr[0] >= 10:
            sx0[y], sx1[y] = rr
    have = np.where(~np.isnan(sx0))[0]
    # источник - самый длинный непрерывный участок ствола V1 (разрыв до 3 строк): у срезов с зазором над
    # корнями перенос иначе тянет пустые строки зазора (разрыв ствол|корни), а у срезов с веточками на спиле
    # (FORESTRED: строки 21-29 - веточка у cx) верхний обрывок дал бы источник в две строки
    parts, s0 = [], int(have[0])
    for a_, b_ in zip(have[:-1], have[1:]):
        if b_ - a_ > 3:
            parts.append((s0, int(a_)))
            s0 = int(b_)
    parts.append((s0, int(have[-1])))
    Tcut, last = max(parts, key=lambda p: p[1] - p[0])
    sx0[:Tcut] = np.nan
    sx1[:Tcut] = np.nan
    wraw = sx1 - sx0
    sx0, sx1 = medfilt(sx0, 9), medfilt(sx1, 9)
    wid = sx1 - sx0
    mid = Tcut + (Ys - Tcut) // 2
    wmed = float(np.nanmedian(wid[Tcut + 4:mid]))
    Bcut = min(Ys, last)
    for y in range(int(Tcut + 0.4 * (Ys - Tcut)), Bcut + 1):
        if not np.isnan(wid[y]) and wid[y] > 1.25 * wmed:
            Bcut = y - 1
            break
        # срез V1 кончается закруглённым торцом над корнями (FORESTRED: 22 -> 11 пикс за три строки), медиана
        # по 9 строкам его прячет - сырая ширина; иначе перенос растягивает закругление в шейку у шва
        if not np.isnan(wraw[y]) and wraw[y] < NARROW_CUT * wmed:
            Bcut = y - NARROW_BACK
            break
    # края источника - прямая (устойчиво, без выбросов): скачок края у основания сучка
    # иначе сдвигает фактуру строк и даёт ступень поперёк ствола
    yy = np.arange(Tcut, Bcut + 1)
    for arr in (sx0, sx1):
        ok = ~np.isnan(arr[yy])
        ya, va = yy[ok], arr[yy][ok]
        for _ in range(3):
            p = np.polyfit(ya, va, 1)
            r = np.abs(np.polyval(p, ya) - va)
            sel = r <= max(2.0, 2.5 * float(np.median(r)))
            ya, va = ya[sel], va[sel]
        arr[yy] = np.polyval(p, yy)
    # карта переноса: строка цели -> строка источника, x цели -> x источника
    # только до шва: ниже Ys - корни MAIN (копия строки шва вниз дала плоскую полосу-ступеньку)
    mapx = np.full((160, 128), -1, np.float32)
    mapy = np.full((160, 128), -1, np.float32)
    tx0s, tx1s = np.full(160, np.nan), np.full(160, np.nan)
    for y in range(Tc, Ys + 1):
        yc = y
        wb = np.clip((yc - (Ys - BLEND)) / BLEND, 0.0, 1.0)
        tx0 = (1 - wb) * X0[yc] + wb * m0
        tx1 = (1 - wb) * X1[yc] + wb * m1
        if np.isnan(X0[yc]) or np.isnan(X1[yc]):
            continue
        ysrc = Tcut + (yc - Tc) * (Bcut - Tcut) / max(1, Ys - Tc)
        yi = int(round(ysrc))
        a, b = sx0[yi], sx1[yi]
        if np.isnan(a):
            continue
        tx0s[y], tx1s[y] = tx0, tx1
        xs = np.arange(128, dtype=np.float32)
        mapx[y] = a + (xs - tx0) * (b - a) / (tx1 - tx0)
        mapy[y] = ysrc
    pm = c0.copy()
    # источник - только сам ствол в строке (sx0..sx1 с полутора пикселями мягкого края):
    # основания веток V1 левее и правее перенос иначе вытягивает за край нового ствола
    xs1 = np.arange(128, dtype=np.float32)
    for y in range(160):
        if np.isnan(sx0[y]):
            continue
        d = np.maximum(sx0[y] - xs1, xs1 - sx1[y])
        pm[y, :, 3] *= np.clip(1.5 - d, 0.0, 1.0)
    pm[..., :3] *= pm[..., 3:4] / 255.0
    warped = cv2.remap(pm, mapx, mapy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    valid = mapx >= 0
    warped[~valid] = 0
    # только то, что связано со стволом: обрывки рядом - прочь
    core = np.zeros((160, 128), bool)
    for y in range(160):
        if not np.isnan(tx0s[y]):
            core[y, int(tx0s[y]) + 2:int(tx1s[y]) - 2] = True
    n, lab = cv2.connectedComponents((warped[..., 3] > 32).astype(np.uint8), connectivity=8)
    keep = np.zeros(n, bool)
    keep[np.unique(lab[core & (warped[..., 3] > 32)])] = True
    keep[0] = False
    warped[~keep[lab]] = 0
    al = warped[..., 3:4]
    rgb = np.where(al > 0, warped[..., :3] / np.maximum(al, 1e-3) * 255.0, 0)
    # цвет у шва - к корням MAIN, затухает вверх
    up = np.zeros((160, 128), bool)
    dn = np.zeros((160, 128), bool)
    for y in range(Ys - 8, Ys + 1):
        if not np.isnan(tx0s[y]):
            up[y, int(tx0s[y]) + 4:int(tx1s[y]) - 4] = True
    for y in range(Ys + 1, min(160, Ys + 9)):
        dn[y, int(m0) + 4:int(m1) - 4] = True
    up &= al[..., 0] > 200
    dn &= c2[..., 3] > 200
    off = c2[..., :3][dn].mean(0) - rgb[up].mean(0) if up.any() and dn.any() else np.zeros(3)
    yy = np.arange(160, dtype=np.float32)[:, None, None]
    w = np.clip(1.0 - (Ys - yy) / TONE_DECAY, 0.0, 1.0)
    rgb = rgb + off * w
    # у самого шва - плавно в строку корней ниже
    row = c2[min(159, Ys + 1)]
    for y in range(Ys - 5, Ys + 1):
        k = 0.5 * (y - (Ys - 6)) / 6.0
        ok = (row[:, 3] > 128) & (al[y, :, 0] > 128)
        rgb[y][ok] = rgb[y][ok] * (1 - k) + row[:, :3][ok] * k
    out = c0.copy()
    # полоса ствола целиком (не только R): иначе выше R остаётся край среза V1 - ступенька под спилом.
    # зелёное V1 (сучок) вне нового ствола оставляем
    Rb = R.copy()
    for y in range(160):
        if not np.isnan(tx0s[y]):
            Rb[y, max(0, int(tx0s[y]) - 8):min(128, int(tx1s[y]) + 8)] = True
    # только яркая листва: оливковый край ствола V1 (g чуть больше r) - не сучок, иначе нитка вдоль ствола
    if job.S in tr.DERIVED:
        green = needles_hd(world, job.S, c0) & (c0[..., 3] > 32) & (al[..., 0] <= 32)
    else:
        green = (c0[..., 1] > c0[..., 0] + 30) & (c0[..., 1] > c0[..., 2] + 20) & (c0[..., 3] > 32) & (al[..., 0] <= 32)
    Rb &= ~green
    out[Rb] = 0
    newp = np.concatenate([np.clip(rgb, 0, 255), al], -1)
    out[Rb] = newp[Rb]
    # ниже шва область среза V1 - корни кадра 57 из MAIN как есть
    below = R.copy()
    below[:Ys + 1] = False
    out[below] = c2[below]
    # у шва вне нового ствола - тонкие горизонтальные обрывки верха корней V1 (FORESTRED: рыжие штрихи
    # в две строки, торчат из шейки влево и вправо; для производных они ещё и «хвоя» по цвету) - прочь.
    # толщину меряем по столбцу всего кадра: юбка, сросшаяся с корнями MAIN ниже, толстая и остаётся.
    # ниже шва - то же у корней MAIN (FORESTRED: штрих на строке Ys+1 левее корней)
    ab = out[..., 3] > 32
    thin = np.zeros((160, 128), bool)
    for x in range(128):
        col = ab[:, x]
        y = Ys - THIN_BAND
        while y <= min(159, Ys + THIN_BAND):
            if col[y]:
                y0 = y
                while y0 > 0 and col[y0 - 1]:
                    y0 -= 1
                y1 = y
                while y1 < 159 and col[y1 + 1]:
                    y1 += 1
                if y1 - y0 + 1 <= THIN_MAX:
                    thin[y0:y1 + 1, x] = True
                y = y1 + 1
            else:
                y += 1
    for y in range(Ys - THIN_BAND, Ys + 1):
        if not np.isnan(tx0s[y]):
            thin[y, max(0, int(tx0s[y])):min(128, int(tx1s[y]) + 1)] = False
    # не только в R: штрихи FORESTRED лежат и вне него (верх корней V1 справа, корни MAIN под швом слева)
    n, lab, st, _c = cv2.connectedComponentsWithStats(thin.astype(np.uint8), connectivity=8)
    for j in range(1, n):
        if st[j, cv2.CC_STAT_WIDTH] < THIN_LEN:
            thin[lab == j] = False
    out[thin] = 0
    # сам шов: волокна ствола обрываются на строке Ys - размыть по вертикали +-SEAM_SOFT строк, только внутри ствола
    lo, hi = Ys - SEAM_SOFT, min(159, Ys + SEAM_SOFT + 1)
    band = out[lo - 3:hi + 4].copy()
    sm = cv2.GaussianBlur(band, (1, 7), sigmaX=0.1, sigmaY=1.5)
    for y in range(lo, hi + 1):
        j = y - (lo - 3)
        w = 1.0 - abs(y - Ys - 0.5) / (SEAM_SOFT + 1)
        ok = (out[y, :, 3] > 200) & (out[max(0, y - 1), :, 3] > 200) & (out[min(159, y + 1), :, 3] > 200)
        out[y, ok, :3] = out[y, ok, :3] * (1 - w) + sm[j, ok, :3] * w
    # оторванные обрывки во всём кадре 57 (не только в R): кусок, не связанный со стволом и корнями, - прочь
    n, lab, st, _c = cv2.connectedComponentsWithStats((out[..., 3] > 32).astype(np.uint8), connectivity=8)
    stray = 0
    if n > 2:
        big = 1 + int(np.argmax(st[1:, 4]))
        for j in range(1, n):
            if j != big and st[j, 4] < STRAY_MAX:
                out[lab == j] = 0
                stray += int(st[j, 4])
    v = np.asarray(v0, np.uint8).copy()
    v[bx[1]:bx[3], bx[0]:bx[2]] = out.astype(np.uint8)
    info = dict(seam_row=Ys, classic_top=Tc, cut_top=Tcut, cut_clean_bottom=Bcut,
                main_at_seam=[round(m0, 1), round(m1, 1)], classic_cx=cx, stray_px_removed=stray, colour_offset=[round(float(o), 1) for o in off])
    return Image.fromarray(v), info


def even_rows(world, S, view, q, Ys, sigma=10.0):
    """Полосы поперёк ствола z<=0: перенос растягивает строки V1 (основание сучка) в полосу цвета.
    Средний цвет середины ствола по строкам сводится к сглаженному (гаусс по строкам), прибавкой -
    фактура остаётся. Только от верха ствола до BLEND над швом: ниже цвет уже ведётся к корням MAIN.
    Возвращает вид и наибольшую снятую поправку (по каналу)."""
    X0, X1, Tc, _cx = classic_trunk(world, S)
    bx = pos_box(q)
    v = np.asarray(view, np.float32).copy()
    c = v[bx[1]:bx[3], bx[0]:bx[2]]
    nd = needles_hd(world, S, c) if S in tr.DERIVED else (c[..., 1] > c[..., 0] + 30)
    y1 = Ys - BLEND // 2
    ys = np.arange(Tc, y1 + 1)
    means = np.full((len(ys), 3), np.nan)
    for i, y in enumerate(ys):
        a, b = int(X0[y]) + 4, int(X1[y]) - 4
        seg = c[y, a:b]
        ok = (seg[:, 3] > 200) & ~nd[y, a:b]
        if ok.sum() > 8:
            means[i] = seg[ok, :3].mean(0)
    good = ~np.isnan(means[:, 0])
    if good.sum() < 10:
        return view, 0.0
    for ch in range(3):
        means[~good, ch] = np.interp(ys[~good], ys[good], means[good, ch])
    # гаусс ступень только размазывает (половина остаётся у самой ступени) - ведём к кубике по строкам
    smooth = np.stack([np.polyval(np.polyfit(ys[good], means[good, ch], 3), ys) for ch in range(3)], 1)
    off = smooth - means
    # к низу поправка затухает до нуля, чтобы не ломать подход цвета к корням
    fade = np.clip((y1 - ys) / 12.0, 0.0, 1.0)[:, None]
    off *= fade
    for i, y in enumerate(ys):
        m = (c[y, :, 3] > 0) & ~nd[y]
        c[y, m, :3] = np.clip(c[y, m, :3] + off[i], 0, 255)
    v[bx[1]:bx[3], bx[0]:bx[2]] = c
    return Image.fromarray(v.astype(np.uint8), "RGBA"), round(float(np.abs(off).max()), 1)


def seam_numbers(view, q, Ys, cx):
    """Ствол у шва в виде z<=0: скачок ширины и цвета между 4 строками над швом и 4 под ним."""
    c = np.asarray(view, np.float32)[pos_box(q)[1]:pos_box(q)[3], pos_box(q)[0]:pos_box(q)[2]]

    def band(ys):
        ws, cols = [], []
        for y in ys:
            rr = run_at(c[y, :, 3] > 128, cx)
            if rr:
                ws.append(rr[1] - rr[0])
                cols.append(c[y, rr[0] + 3:rr[1] - 3, :3].mean(0))
        return (np.mean(ws), np.mean(cols, 0)) if ws else (np.nan, np.full(3, np.nan))
    wa, ca = band(range(Ys - 3, Ys + 1))
    wb, cb = band(range(Ys + 1, Ys + 5))
    return dict(width_above=round(float(wa), 1), width_below=round(float(wb), 1),
                width_jump=round(float(abs(wa - wb)), 1), colour_step=round(float(np.abs(ca - cb).max()), 1))


# ---------------------------------------------------------------- цвет ствола FOREST

def trunk_weight(rgb):
    r, g = rgb[..., 0], rgb[..., 1]
    return np.clip(1.0 - (g - r + 4.0) / 12.0, 0.0, 1.0)     # 1 там, где g <= r-4, 0 при g >= r+8


def lab_of(rgb):
    return cv2.cvtColor((rgb / 255.0).astype(np.float32)[None], cv2.COLOR_RGB2LAB)[0]


def bark_weight(rgb, world=None, S=None):
    """Вес коры: FOREST и WASTE - trunk_weight (кора не зелёная); у производных хвоя не зелёная (красная, чёрная),
    там кора - всё, что не хвоя по Lab классики своего набора (needles_hd)."""
    if S not in tr.DERIVED:
        return trunk_weight(rgb)
    px = np.asarray(rgb, np.float32).reshape(-1, 3)
    rgba = np.concatenate([px, np.full((len(px), 1), 255.0, np.float32)], 1)[:, None, :]
    return (~needles_hd(world, S, rgba)[:, 0]).astype(np.float32)


def trunk_shift(world, S, v0, q):
    """Сдвиг a*b* (Lab): классика 57 (не зелёное) минус ствол HD в кадре 57 вида z<=0.
    У производных - сдвиг L*a*b*: их HD-ствол уходит от классики и по светлоте (BLACK темнее вдвое)."""
    a = np.asarray(tr.sprite(world, S, 57), np.float32)
    ag = np.asarray(tr.sprite(world, geom(S), 57), np.float32)
    m = (ag[..., 3] > 0) & ~(ag[..., 1] > ag[..., 0] + 8)
    k = 0 if S in tr.DERIVED else 1
    lc = lab_of(a[..., :3][m])
    c = np.asarray(v0, np.float32)[pos_box(q)[1]:pos_box(q)[3], pos_box(q)[0]:pos_box(q)[2]]
    sel = c[..., 3] > 200
    rgb = c[..., :3][sel]
    w = np.ones(len(rgb), np.float32) if S in POS_BARK else bark_weight(rgb, world, S)
    lh = lab_of(rgb)
    mh = (lh[:, k:] * w[:, None]).sum(0) / max(w.sum(), 1e-3)
    return lc[:, k:].mean(0) - mh, dict(classic_ab=[round(float(v), 1) for v in lc[:, k:].mean(0)],
                                       hd_ab=[round(float(v), 1) for v in mh])


def recolour(view, mask4, d_ab, world=None, S=None, pos=False):
    """pos - в маске только ствол и корни (рамка 57 вида z<=0): у POS_BARK вес коры 1 всем пикселям."""
    v = np.asarray(view, np.float32).copy()
    sel = mask4 & (v[..., 3] > 0)
    rgb = v[..., :3][sel]
    lab = lab_of(rgb)
    w = np.ones(len(rgb), np.float32) if pos and S in POS_BARK else bark_weight(rgb, world, S)
    lab[:, 3 - len(d_ab):] += d_ab[None] * w[:, None]
    back = cv2.cvtColor(lab[None], cv2.COLOR_LAB2RGB)[0] * 255.0
    v[..., :3][sel] = np.clip(back, 0, 255)
    return Image.fromarray(v.astype(np.uint8), "RGBA")


# ---------------------------------------------------------------- модель: замок со структурой

def paint_locked2(painter, args, known, cond, free, what, seed, release):
    """tr.paint_locked плюс структурный замок: в свободном месте, пока сигма выше release, латенты - зашумлённое
    условие (классика вида), дальше модель свободна; вне free - как V1, зашумлённый известный холст."""
    torch = painter.torch
    pipe = painter.pipe
    dev = pipe._execution_device
    W, H = known.size
    hl, wl = H // 16, W // 16

    def enc(img):
        with torch.no_grad():
            t = pipe.image_processor.preprocess(img.convert("RGBA"), H, W).unsqueeze(2).to(dev, pipe.vae.dtype)
            lat = pipe._encode_vae_image(t, generator=None)
            return pipe._pack_latents(lat, 1, lat.shape[1], lat.shape[3], lat.shape[4]).to(torch.bfloat16)
    init = enc(known)
    clat = enc(cond)
    if init.shape[1] != hl * wl:
        raise SystemExit("латентов %d, маска %d (%dx%d)" % (init.shape[1], hl * wl, wl, hl))
    g = torch.Generator("cuda").manual_seed(seed + 1)
    noise = torch.randn(init.shape, generator=g, device=dev, dtype=torch.float32).to(init.dtype)
    m = torch.from_numpy(free.reshape(1, -1, 1).astype(np.float32)).to(dev, init.dtype)

    def cb(pp, i, _t, kw):
        x = kw["latents"]
        sg = float(pp.scheduler.sigmas[i + 1])
        noised = sg * noise + (1.0 - sg) * init
        fr = x.to(init.dtype)
        if sg > release:
            fr = sg * noise + (1.0 - sg) * clat
        return {"latents": (m * fr + (1.0 - m) * noised).to(x.dtype)}

    kw = {"prompt": po.STYLE["strict"].replace("{what}", what), "num_inference_steps": args.steps,
          "image": cond, "generator": torch.Generator("cuda").manual_seed(seed),
          "negative_prompt": po.gen_fire.NEGATIVE, "true_cfg_scale": args.cfg, "width": W, "height": H,
          "callback_on_step_end": cb, "callback_on_step_end_tensor_inputs": ["latents"]}
    miss = [k for k in ("image", "negative_prompt", "true_cfg_scale", "callback_on_step_end")
            if k not in painter.accepts]
    if miss:
        raise SystemExit("конвейер не принимает %s" % miss)
    with torch.no_grad():
        return pipe(**kw).images[0].convert("RGB")


# ---------------------------------------------------------------- одно дерево

class Job2(tr.Job):
    def __init__(self, world, CL, hints, S, seed, args):
        a1 = argparse.Namespace(**vars(args))
        a1.out = args.v1
        super().__init__(world, CL, hints, S, seed, a1)
        self.args = args
        self.world = world
        self.d2 = os.path.join(args.out, "s%d" % seed, S)
        os.makedirs(self.d2, exist_ok=True)
        # дерево того же устройства в цветах FOREST: по нему маски спилов классики (альфа та же)
        self.gtree = tr.Tree(world, geom(S), CL[geom(S)]["sigs"][0]["sig"], args.grow) if S in GEOM_FROM else None

    def raw_z1(self, rel):
        return os.path.join(self.d2, "raw_cut_z1_r%02d.png" % round(rel * 100))

    def base(self):
        """MAIN, вид z<=0 (V1 срез -> шов), перекраска ствола, канон FULL и Z0. Без модели."""
        t, b, args = self.tree, self.box, self.args
        hd, g, tp, main = self.main_cut()
        self._g, self._hd, self._tp = g, hd, tp
        canvas = lambda body: tr.paste4(body, b, t)       # noqa: E731
        v2 = canvas(main)
        raw0 = Image.open(self.raw_cut(0)).convert("RGB")
        cut0 = tr.apply_tone(tr.limit_alpha(tr.to_body(raw0, g), self.frame_z(0), args.grow), tp, args.tone)
        cut0 = np.asarray(canvas(cut0), np.uint8)
        U0, own0, _F = self.masks(0)
        U4, own4 = tr.rep4(U0), tr.rep4(own0)
        v = np.asarray(v2, np.uint8).copy()
        v[U4 & (own4 == 0)] = cut0[U4 & (own4 == 0)]
        v[U4 & (own4 < 0)] = 0
        v0_v1 = Image.fromarray(v)
        v0, zinfo = z0_trunk(self, self.world, v0_v1, v2)
        i57 = next(i for i, q in enumerate(t.pcs) if q["f"] == 57)
        q57 = t.pcs[i57]
        info = dict(z0=zinfo)
        info["z0"]["seam_v1"] = seam_numbers(v0_v1, q57, zinfo["seam_row"], zinfo["classic_cx"])
        if self.S == "FOREST" and args.recolour:
            d_ab, cinfo = trunk_shift(self.world, self.S, v0, q57)
            cinfo["shift_ab"] = [round(float(x), 1) for x in d_ab]
            info["trunk_colour"] = cinfo
            # z<=0: в рамке только кадр 57 - красим всю рамку (силуэт классики ниже верха HD-ствола: полоса цвета)
            m57 = np.zeros((v0.height, v0.width), bool)
            b57 = pos_box(q57)
            m57[b57[1]:b57[3], b57[0]:b57[2]] = True
            v0 = recolour(v0, m57, d_ab)
            v2 = recolour(v2, tr.rep4(t.lab[2] == i57), d_ab)
        v0, info["z0"]["row_band_max"] = even_rows(self.world, self.S, v0, q57, zinfo["seam_row"])
        if (self.S in ("FOREST", "FOREST_WASTE") or self.S in tr.DERIVED) and args.recolour:
            v0, v2, info["f57"] = f57_details(self, v0, v2, q57, i57,
                                               shift=self.S == "FOREST" or self.S in tr.DERIVED)
        info["z0"]["seam_v2"] = seam_numbers(v0, q57, zinfo["seam_row"], zinfo["classic_cx"])
        v2n = v2                                          # без заливки: из него кромка edge_rule
        if self.S in HOLE_FILL_SETS:                      # просветы кроны: под существующим - клон MAIN
            v2, info["holes_v2"] = fill_crown_holes(v2, v2)
        frames, src = {}, {}
        self.views = {}                                   # откуда вырезан кадр - для кромки (edge_rule)
        self.frames_ref = {}                              # кадры без заливки просветов - для envelope_gate
        for q in t.pcs:
            f = q["f"]
            if f in FULL_FRAMES and q["z"] == t.top:
                ext = draw_extra(t, q, v2) if self.S in HOLE_FILL_SETS else None
                frames[f], src[f] = frame_filled(v2n, v2, q, ext), "FULL"
                self.views[f] = (v2n, q)
                self.frames_ref[f] = frame_from(v2n, q)
            elif f == 57:
                frames[f], src[f] = frame_from(v0, q), "Z0_EXPOSED"
                self.views[f] = (v0, q)
                self.frames_ref[f] = frames[f]
        self.v0, self.v2, self.q57 = v0, v2, q57
        return frames, src, info

    def lock_z1(self, frames):
        """Холст x4: канон 53-55 на их местах этажа 1 (там, где в виде z<=1 владеют они) и маска замка."""
        t = self.tree
        c = np.zeros((t.H * 4, t.W * 4, 4), np.uint8)
        for j, q in enumerate(t.pcs):
            if q["z"] == 1 and q["f"] in LOCK_Z1:
                own = tr.rep4(t.lab[1] == j)
                p = np.asarray(place(t, frames[q["f"]], q), np.uint8)
                c[own] = p[own]
        return c, c[..., 3] >= 128

    def canvases1(self, frames):
        """Холст замка, условие и свободные клетки для CUT_Z1 (холст ответа MAIN)."""
        t, b, g, tp, hd, args = self.tree, self.box, self._g, self._tp, self._hd, self.args
        U, own, F = self.masks(1)
        lockc, lock4 = self.lock_z1(frames)

        def body(m4):
            return m4[b[1] * 4:b[3] * 4, b[0] * 4:b[2] * 4]
        bg = np.array([round(v) for v in g["bg"]], np.uint8)

        def to_raw(view4):
            """вид x4 (тон MAIN) -> холст ответа, подложка там, где прозрачно."""
            im = untone(Image.fromarray(body(np.asarray(view4, np.uint8))), tp, args.tone)
            flat = Image.new("RGBA", im.size, tuple(int(v) for v in bg) + (255,))
            flat.alpha_composite(im)
            return np.asarray(tr.body_to_raw(flat, g, Image.LANCZOS).convert("RGB"))
        U_r = tr.mask_raw(self.body4(U), g)
        known = np.asarray(hd, np.uint8).copy()
        known[U_r] = bg
        m0 = tr.mask_raw(self.body4(U & (own == 0)), g)
        known[m0] = to_raw(self.v0)[m0]
        L_r = tr.mask_raw(body(lock4), g)
        known[L_r] = to_raw(lockc)[L_r]
        cls = tr.xbrz(self.frame_z(1))
        flat = Image.new("RGBA", cls.size, tuple(int(v) for v in bg) + (255,))
        flat.alpha_composite(cls)
        cls_r = np.asarray(tr.body_to_raw(flat, g, Image.LANCZOS).convert("RGB"))
        F_r = tr.mask_raw(self.body4(F), g) & ~L_r
        cond = known.copy()
        cond[F_r] = cls_r[F_r]
        W, H = hd.size
        hl, wl = H // 16, W // 16
        f = cv2.resize(F_r.astype(np.float32), (wl, hl), interpolation=cv2.INTER_AREA) > 0
        lk = cv2.resize(L_r.astype(np.float32), (wl, hl), interpolation=cv2.INTER_AREA) > 0.5
        free = (cv2.dilate(f.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0) & ~lk
        return Image.fromarray(known), Image.fromarray(cond), free, F_r, lockc, lock4

    def view1(self, raw1, lockc, lock4):
        """Вид z<=1 x4: MAIN; на U_1 срез (куски этажа 1), вид z<=0 (кусок 57); канон 53-55 везде, где владеют."""
        t, b, g, tp, args = self.tree, self.box, self._g, self._tp, self.args
        cut = tr.apply_tone(tr.limit_alpha(tr.to_body(raw1, g), self.frame_z(1), args.grow), tp, args.tone)
        cut4 = np.asarray(tr.paste4(cut, b, t), np.uint8)
        U, own, _F = self.masks(1)
        U4, own4 = tr.rep4(U), tr.rep4(own)
        own53 = np.zeros_like(U4)
        for j, q in enumerate(t.pcs):
            if q["z"] == 1 and q["f"] in LOCK_Z1:
                own53 |= tr.rep4(t.lab[1] == j)
        v = np.asarray(self.v2, np.uint8).copy()
        m = U4 & (own4 == 1) & ~own53
        v[m] = cut4[m]
        m = U4 & (own4 == 0)
        v[m] = np.asarray(self.v0, np.uint8)[m]
        v[U4 & (own4 < 0)] = 0
        v[own53] = lockc[own53]
        return Image.fromarray(v), cut4

    def own53(self):
        t = self.tree
        m = np.zeros((t.H * 4, t.W * 4), bool)
        for j, q in enumerate(t.pcs):
            if q["z"] == 1 and q["f"] in LOCK_Z1:
                m |= tr.rep4(t.lab[1] == j)
        return m

    def z1_composite(self, seed_noise=7):
        """Срез z<=1 без модели (решение 09.10): хвоя и ветки - из MAIN, классика - только маска и места спилов.

        Земля кадров Z1_EXPOSED (под верхом и вне его): MAIN без ограничения силуэтом полного кадра, дыры
        внутри силуэта зоны - клон тела яруса MAIN со сдвигом вниз; альфа - гладкий силуэт классики z<=1,
        кромка растворяется пучками хвои; крышки спилов - по пятнам классики (число, место, размер),
        материал - древесина пня HD и кора ствола HD, RGB классики в срез не идёт. Возвращает x4 RGBA и землю.
        """
        t, b = self.tree, self.box
        U, own, F = self.masks(1)
        U4, own4 = tr.rep4(U), tr.rep4(own)
        main = np.asarray(self.v2, np.float32)
        H, W = main.shape[:2]
        sil = np.asarray(tr.sil_limit(self.frame_z(1), 2), np.float32)
        S4 = np.zeros((H, W), np.float32)
        S4[b[1] * 4:b[3] * 4, b[0] * 4:b[2] * 4] = sil
        zone = U4 & (own4 == 1)
        z1e = [j for j, q in enumerate(t.pcs) if q["z"] == 1 and q["f"] not in LOCK_Z1]
        terr = tr.rep4(np.isin(t.lab[1], z1e) | (t.lab[1] < 0)) & ~(U4 & (own4 < 0))
        # 1) хвоя: MAIN без limit_alpha (квадратная кайма MaxFilter давала прямоугольные вырезы)
        raw = tr.apply_tone(tr.to_body(self._hd, self._g), self._tp, self.args.tone)
        mraw = np.asarray(tr.paste4(raw, b, t), np.float32)
        col = np.where(terr[..., None], mraw[..., :3], main[..., :3])
        asrc = np.where(terr, mraw[..., 3], main[..., 3]) / 255.0
        fcol, fa = col.copy(), asrc.copy()
        have = (asrc > 0.8) | ~terr
        for dy, dx in CLONE_SHIFTS:
            sh = np.roll(np.roll(main, -dy, 0), -dx, 1)
            ok = (~have) & (sh[..., 3] > 230)
            fcol[ok] = sh[..., :3][ok]
            fa[ok] = sh[..., 3][ok] / 255.0
            have |= ok
        # заплатка только в зоне среза, вес плавный: граница зоны - блоки 4x4
        wf = np.clip((cv2.GaussianBlur(zone.astype(np.float32), (0, 0), 6.0) - 0.25) / 0.5, 0, 1)
        col = col + (fcol - col) * wf[..., None]
        asrc = asrc + (fa - asrc) * wf
        # слабая альфа ответа - подложка, а не хвоя (R-089)
        asrc = np.where(terr, np.clip((asrc - 0.35) / 0.5, 0, 1), asrc)
        # цвет полупрозрачной кромки - с плотных соседей (светлый пунктир - подложка в краю ответа)
        dense = asrc > 0.95
        for _ in range(6):
            cnt = cv2.blur(dense.astype(np.float32), (3, 3))
            acc = np.stack([cv2.blur(np.where(dense, col[..., c], 0).astype(np.float32), (3, 3))
                            for c in range(3)], -1)
            add = (~dense) & (cnt > 0)
            col[add] = acc[add] / cnt[add][:, None]
            dense = dense | add
        Y = col.mean(-1)
        # 2) альфа: знаковое расстояние до силуэта классики z<=1, сдвиг +-2.5 пикс по пучкам хвои
        inside = (S4 > 0.5).astype(np.uint8)
        sd = cv2.distanceTransform(inside, cv2.DIST_L2, 5) - cv2.distanceTransform(1 - inside, cv2.DIST_L2, 5)
        sd = cv2.GaussianBlur(sd.astype(np.float32), (0, 0), 4.0)
        tuft = cv2.GaussianBlur(Y, (0, 0), 1.5) - cv2.GaussianBlur(Y, (0, 0), 6)
        alpha = asrc * np.clip((sd + 2.5 * np.clip(tuft / 14.0, -1, 1)) / 1.6 + 0.5, 0, 1)
        # оторванные клочки прочь: на земле Z1 - только связное с телом дерева
        solid = ((alpha > 0.35) & terr) | ((main[..., 3] > 128) & ~terr)
        n, lb, stt, _c = cv2.connectedComponentsWithStats(solid.astype(np.uint8), 8)
        scraps = 0
        if n > 1:
            big = 1 + int(np.argmax(stt[1:, 4]))
            keep = cv2.dilate((lb == big).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
            scraps = int((terr & ~keep & (alpha > 0.5)).sum())
            alpha[terr & ~keep] = 0
        alpha[~terr] = main[..., 3][~terr] / 255.0
        # 3) свет верха среза - скалярный множитель к классике, к границе зоны 1
        cl4 = np.asarray(t.compose(1, 4), np.float32)
        inner = zone & (S4 > 0.5)
        yc = cl4[..., :3].mean(-1)[inner & (cl4[..., 3] > 128)].mean()
        gain = float(np.clip(yc / max(Y[inner].mean(), 1), 0.85, 1.35))
        wg = np.clip(cv2.distanceTransform(zone.astype(np.uint8), cv2.DIST_L2, 3) / 24.0, 0, 1)
        col = col * (1 + (gain - 1) * wg)[..., None]
        # 4) крышки спилов: место и размер - пятна классики, материал - пень и кора HD
        st = np.asarray(Image.open(stump_src(self.S)).convert("RGBA"), np.float32)
        wood = _lab8(st[(st[..., 3] > 200) & (st[..., :3].mean(-1) > 60)][:, :3])
        bx = pos_box(self.q57)
        tr57 = np.asarray(self.v0, np.float32)[bx[1]:bx[1] + 120, bx[0]:bx[2]]
        if self.S in tr.DERIVED:
            tm = (tr57[..., 3] > 200) & ~needles_hd(self.world, self.S, tr57)
        else:
            tm = (tr57[..., 3] > 200) & (np.abs(tr57[..., 1] - tr57[..., 0]) < 40) & (tr57[..., 0] >= tr57[..., 1])
        bm = _lab8(tr57[tm][:, :3]).mean(0)
        rng = np.random.default_rng(seed_noise)
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        L0 = float(np.percentile(wood[:, 0], 60))
        caps = []
        out0 = np.concatenate([np.clip(col, 0, 255), (np.clip(alpha, 0, 1) * 255)[..., None]], -1).astype(np.uint8)
        capown = np.full((H, W), -1, np.int32)      # чья крышка: кусок яруса, где центр пятна классики
        for s in classic_spots(self):
            tgt = _lab8(s["mean"][None])[0]
            cx, cy = s["c"][0] * 4 + 2, s["c"][1] * 4 + 2
            rx, ry = max(s["w"] * 1.9, 3.5), max(s["h"] * 1.9, 2.5)
            box, crgb, wcap, rr = wood_face(xx, yy, cx, cy, rx, ry, L0, tgt[1:], bm, rng,
                                            self.S == "FOREST_WASTE")
            # иглы MAIN перекрывают внешний край крышки там, где у хвои светлый пучок
            wcap = wcap * (1 - np.clip((tuft - 2.0) / 6.0, 0, 1) * np.clip((rr - 0.72) / 0.28, 0, 1))
            wb = wcap[box][..., None]
            col[box] = col[box] * (1 - wb) + crgb * wb
            alpha[box] = np.maximum(alpha[box], wcap[box])
            j = int(t.lab[1][int(round(s["c"][1])), int(round(s["c"][0]))])
            capown[box & (wcap > 0)] = j
            caps.append([s["x"], s["y"], s["w"], s["h"], s["area"], j])
        out = np.concatenate([np.clip(col, 0, 255), (np.clip(alpha, 0, 1) * 255)[..., None]], -1).astype(np.uint8)
        return out, terr, dict(light_gain=round(gain, 3), caps_classic=caps, scraps_cut=scraps), out0, capown

    def view1_comp(self, comp, terr, lockc):
        """Вид z<=1 x4 по составному срезу: земля Z1 - срез, кусок 57 - вид z<=0, канон 53-55 на месте."""
        U, own, _F = self.masks(1)
        U4, own4 = tr.rep4(U), tr.rep4(own)
        v = np.asarray(self.v2, np.uint8).copy()
        v[terr] = comp[terr]
        m = U4 & (own4 == 0)
        v[m] = np.asarray(self.v0, np.uint8)[m]
        v[U4 & (own4 < 0)] = 0
        o53 = self.own53()
        v[o53] = lockc[o53]
        return Image.fromarray(v)


def f57_details(job, v0, v2, q57, i57, iters=3, shift=True):
    """Кадр 57 без модели (решение 09.10): ствол FOREST к пурпурно-бурому классики (остаток сдвига a*b* дожат),
    торец спила на верху HD-ствола (древесина пня HD, оттенок - торец классики), ветки - линии корой по
    пикселям веток классики (вне HD-ствола, выше корней), у FOREST на них хвоя MAIN по зелёным пятнам
    классики. Силуэт ствола и корней не меняется: торец только внутри непрозрачного, ветки только снаружи."""
    t = job.tree
    b57 = pos_box(q57)
    m57 = np.zeros((v0.height, v0.width), bool)
    m57[b57[1]:b57[3], b57[0]:b57[2]] = True
    own2 = tr.rep4(t.lab[2] == i57)
    res = []
    for _ in range(iters if shift else 0):      # вес trunk_weight < 1 недодаёт сдвиг - дожать остаток
        d_ab, ci = trunk_shift(job.world, job.S, v0, q57)
        res.append(ci["hd_ab"])
        if float(np.linalg.norm(d_ab)) < 0.5:
            break
        v0 = recolour(v0, m57, d_ab, job.world, job.S, pos=True)
        v2 = recolour(v2, own2, d_ab, job.world, job.S)
    _d, ci = trunk_shift(job.world, job.S, v0, q57)
    out = dict(trunk_ab_iter=res, trunk_ab_final=ci["hd_ab"], classic_ab=ci["classic_ab"])
    v = np.asarray(v0, np.float32).copy()
    fr = v[b57[1]:b57[3], b57[0]:b57[2]]        # вид, не копия: правки идут в v
    cl = np.asarray(tr.sprite(job.world, job.S, 57), np.int16)
    cg = np.asarray(tr.sprite(job.world, geom(job.S), 57), np.int16)     # маски по цвету - по геометрии
    # торец: верх HD-ствола, ширина - ствол на 8 строк ниже верха
    a = fr[..., 3]
    rows = np.where((a > 200).sum(1) >= 8)[0]
    ht = int(rows[0])
    xs = np.where(a[ht + 8] > 200)[0]
    mid = int(np.median(xs))
    run = xs[np.abs(xs - mid) <= 64]
    x0, x1 = int(run.min()), int(run.max())
    clt = int(np.where(cl[..., 3].any(1))[0][0])
    top = cl[clt:clt + 4]
    topg = cg[clt:clt + 4]
    om = (top[..., 3] > 0) & (topg[..., 0] > topg[..., 1] + 25)
    face_lab = _lab8(top[..., :3][om].astype(np.float32)).mean(0)
    st = np.asarray(Image.open(stump_src(job.S)).convert("RGBA"), np.float32)
    wood = _lab8(st[(st[..., 3] > 200) & (st[..., :3].mean(-1) > 60)][:, :3])
    L0 = float(np.percentile(wood[:, 0], 60))
    if job.S in tr.DERIVED:
        tm = (a > 200) & ~needles_hd(job.world, job.S, fr)
    else:
        tm = (a > 200) & (fr[..., 0] >= fr[..., 1])
    bm = _lab8(fr[..., :3][tm]).mean(0)
    rx = (x1 - x0) / 2.0 - 2.0
    ry = max(rx * 0.32, 5.0)
    cx, cy = (x0 + x1) / 2.0, ht + ry + 1.0
    yy, xx = np.mgrid[0:fr.shape[0], 0:fr.shape[1]].astype(np.float32)
    rng = np.random.default_rng(57)
    box, crgb, wcap, _rr = wood_face(xx, yy, cx, cy, rx, ry, L0, face_lab[1:], bm, rng)
    wcap = wcap * np.clip((a - 200) / 55.0, 0, 1)          # только внутри непрозрачного: силуэт прежний
    wb = wcap[box][..., None]
    fr[..., :3][box] = fr[..., :3][box] * (1 - wb) + crgb * wb
    out["cut_face"] = dict(top_row_x4=ht, x=[x0, x1], rx=round(rx, 1), ry=round(ry, 1),
                           ab=[round(float(face_lab[1] - 128), 1), round(float(face_lab[2] - 128), 1)])
    # веточки: зелёные пятна классики x4 (мягкий край), хвоя - клон MAIN с лучшим сдвигом
    gm = (cg[..., 3] > 0) & (cg[..., 1] > cg[..., 0] + 8)
    n, lb, sts, cen = cv2.connectedComponentsWithStats(gm.astype(np.uint8), 8)
    # ветки: пиксели классики, отстоящие от HD-ствола на 2+ пикс базы (ближе - край ствола классики, он у HD
    # шире или сдвинут), выше корней, вместе с хвоей (хвоя потом ложится клоном MAIN поверх). Внутри пятна -
    # остовное дерево соседей (без треугольников: полоса в 2 пикс не становится толстой лентой), рёбра -
    # тонкие отрезки корой между центрами пикселей x4 (лесенка классики становится прямой); ближний пиксель
    # пятна соединён отрезком с ближним пикселем ствола - ветка растёт из ствола
    smask = np.zeros(a.shape, np.float32)
    tr_on = a > 200
    hb, wb_ = cl.shape[:2]
    tr_cl = tr_on[:hb * 4, :wb_ * 4].reshape(hb, 4, wb_, 4).mean((1, 3)) >= 0.5
    tpts = np.argwhere(tr_cl)
    dist = cv2.distanceTransform((~tr_cl).astype(np.uint8), cv2.DIST_L2, 5)
    br = (cl[..., 3] > 0) & (dist >= 2)            # хвоя тоже: ветка идёт под ней, иначе рвётся на штрихи
    br[28:] = False
    br[:clt + 2] = False
    nb, lbb = cv2.connectedComponents(br.astype(np.uint8), connectivity=8)

    def seg(p0, p1, th):
        cv2.line(smask, (int(p0[1] * 16 + 8), int(p0[0] * 16 + 8)), (int(p1[1] * 16 + 8), int(p1[0] * 16 + 8)),
                 1.0, thickness=th, lineType=cv2.LINE_AA, shift=2)
    stems = []
    for j in range(1, nb):
        pts = np.argwhere(lbb == j)
        if len(pts) < 2:
            continue
        dd = np.hypot(*(pts[:, None, :] - pts[None, :, :]).transpose(2, 0, 1))
        dd[dd > 1.5] = np.inf                                  # только соседи по 8 направлениям
        r0i = int(np.argmin(dist[pts[:, 0], pts[:, 1]]))
        inn = np.zeros(len(pts), bool)
        inn[r0i] = True
        best = dd[r0i].copy()
        par = np.full(len(pts), r0i)
        ne = 0
        while True:                                            # Прим от пикселя у ствола
            c_ = np.where(~inn & np.isfinite(best))[0]
            if not len(c_):
                break
            k = c_[np.argmin(best[c_])]
            inn[k] = True
            ne += 1
            upd = ~inn & (dd[k] < best)
            best[upd] = dd[k][upd]
            par[upd] = k
        # остов -> цепочки между развилками и концами, каждая спрямлена (Дуглас-Пекер 0.8 пикс базы):
        # лесенка пикселей классики становится прямой или плавным изломом, а не ступенями
        par[r0i] = -1
        deg = np.zeros(len(pts), int)
        for k in range(len(pts)):
            if par[k] >= 0:
                deg[k] += 1
                deg[par[k]] += 1
        for k in range(len(pts)):
            if par[k] < 0 or deg[k] == 2:
                continue
            ch = [k]                                        # от конца или развилки вверх по остову
            while par[ch[-1]] >= 0:
                ch.append(par[ch[-1]])
                if deg[ch[-1]] != 2:
                    break
            poly = cv2.approxPolyDP(pts[ch][:, ::-1].astype(np.float32).reshape(-1, 1, 2), 0.8, False)
            poly = poly.reshape(-1, 2)[:, ::-1]
            for p0, p1 in zip(poly[:-1], poly[1:]):
                seg(p0, p1, 3)
        r0 = pts[r0i]
        t0 = tpts[np.argmin(((tpts - r0) ** 2).sum(1))]
        seg(r0, t0, 5)
        stems.append([int(len(pts)), ne, [int(r0[0]), int(r0[1])]])
    ssoft = np.clip(cv2.GaussianBlur(smask, (0, 0), 0.5), 0, 1) * (~tr_on)
    sy, sx = np.where(ssoft > 0.02)
    if len(sy):
        nz = cv2.GaussianBlur(rng.normal(0, 6, a.shape).astype(np.float32), (0, 0), 1.0)
        gb = cv2.GaussianBlur(smask, (0, 0), 1.2)
        lit = np.zeros_like(gb)
        lit[1:-1] = gb[2:] - gb[:-2]                   # верхняя кромка ветки светлее (свет сверху), нижняя темнее
        slab = np.stack([bm[0] - 8 + nz[sy, sx] + 14 * np.clip(lit[sy, sx], -1, 1),
                         np.full(len(sy), bm[1]), np.full(len(sy), bm[2])], -1)
        w = ssoft[sy, sx]
        fr[sy, sx, :3] = fr[sy, sx, :3] * (1 - w[:, None]) + _rgb8(slab) * w[:, None]
        fr[sy, sx, 3] = np.maximum(fr[sy, sx, 3], w * 255)
    out["stems"] = stems
    mv = np.asarray(v2, np.float32)
    if job.S in tr.DERIVED:                       # хвоя производного дерева - не по зелёному: весь MAIN вне 57
        # тёмные нейтральные щели между лапами в тени по Lab чуть ближе к коре - это крона, а не ствол: закрыть
        nd = (needles_hd(job.world, job.S, mv) | snow_hd(job.world, job.S, mv)).astype(np.uint8)
        nd = cv2.morphologyEx(nd, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))) > 0
        # у SNOW тёмная кайма снега близка к серой подложке ответа и после ключа полупрозрачна (линии по всей
        # кроне, на полу читаются контуром): плотной считать хвою с альфой от половины, иначе ни одно место не плотное
        dense = (mv[..., 3] > 128) & ~own2 & nd
        cf = np.asarray(tr.sprite(job.world, geom(job.S), 57).convert("RGBA"), np.int16)
        hf = np.asarray(Image.open(GEOM_F57 % ((geom(job.S),) * 2)).convert("RGBA"), np.float32)
    else:
        dense = (mv[..., 3] > 235) & (mv[..., 1] > mv[..., 0] + 6) & ~own2
    twigs = []
    for j in range(1, n):
        if sts[j, 4] < 2:
            continue
        m4 = np.kron((lb == j).astype(np.float32), np.ones((4, 4), np.float32))
        soft = np.clip((cv2.GaussianBlur(m4, (0, 0), 1.6) - 0.3) / 0.4, 0, 1)
        ys, xs_ = np.where(soft > 0)
        gy, gx = ys + b57[1], xs_ + b57[0]
        if job.S in tr.DERIVED and (cl[lb == j] == cf[lb == j]).all():
            # пятно классики побайтно как у FOREST (трава у корней) - тот же HD, что в каноне FOREST
            src = hf[ys, xs_]
            w = soft[ys, xs_] * src[:, 3] / 255.0
            cur = fr[ys, xs_]
            fr[ys, xs_, :3] = cur[:, :3] * (1 - w[:, None]) + src[:, :3] * w[:, None]
            fr[ys, xs_, 3] = np.maximum(cur[:, 3], w * 255)
            twigs.append([int(sts[j, 0]), int(sts[j, 1]), int(sts[j, 4]), "geom"])
            continue
        best = None
        top_cov = 0.0
        for dy in range(-480, 1, 4):            # хвоя яруса выше: сдвиг вверх (у SNOW нижний ярус рваный -
            for dx in range(-240, 241, 4):      # сплошная хвоя дальше 240); берётся ближайший, канон прежний
                yy2, xx2 = gy + dy, gx + dx
                if yy2.min() < 0 or xx2.min() < 0 or yy2.max() >= dense.shape[0] or xx2.max() >= dense.shape[1]:
                    continue
                cov = dense[yy2, xx2].mean()
                top_cov = max(top_cov, float(cov))
                if cov >= 0.97 and (best is None or abs(dy) + abs(dx) < best[0]):
                    best = (abs(dy) + abs(dx), dy, dx)
        if best is None:
            twigs.append([int(sts[j, 0]), int(sts[j, 1]), int(sts[j, 4]), None, round(top_cov, 3)])
            continue
        _s, dy, dx = best
        src = mv[gy + dy, gx + dx]
        w = soft[ys, xs_] * src[:, 3] / 255.0
        cur = fr[ys, xs_]
        fr[ys, xs_, :3] = cur[:, :3] * (1 - w[:, None]) + src[:, :3] * w[:, None]
        fr[ys, xs_, 3] = np.maximum(cur[:, 3], w * 255)
        twigs.append([int(sts[j, 0]), int(sts[j, 1]), int(sts[j, 4]), [int(dy), int(dx)]])
    out["twigs"] = twigs
    return Image.fromarray(np.clip(v, 0, 255).astype(np.uint8), "RGBA"), v2, out


def wood_face(xx, yy, cx, cy, rx, ry, L0, ab, bark_lab, rng, charred=False):
    """Торец спила x4: древесина (кольца, свет сверху-слева, сердцевина) и обод коры 1.5 пикс.
    Яркость - от древесины пня HD (L0), a*b* - ab, кора - bark_lab. Возвращает рамку, RGB рамки, вес, rr."""
    rr = np.sqrt(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2)
    rimw = 1.5 / min(rx, ry)
    box = rr <= 1.0 + 2.5 * rimw
    face = rr <= 1.0
    nz = cv2.GaussianBlur(rng.normal(0, 4, rr.shape).astype(np.float32), (0, 0), 0.8)
    Lw = L0 + 5 * np.cos(rr * np.pi * max(2.0, rx / 4)) + nz              # годовые кольца
    Lw = Lw + 10 * ((xx - cx) * -0.5 + (yy - cy) * -1.0) / (rx + ry)      # свет сверху-слева
    Lw = Lw - 25 * np.clip(1 - rr / 0.12, 0, 1)                            # сердцевина
    if charred:
        Lw = Lw - 12 - 45 * np.clip((0.62 - rr) / 0.25, 0, 1)              # обугленная середина
    f_lab = np.stack([Lw, np.full_like(Lw, ab[0]), np.full_like(Lw, ab[1])], -1)
    Lb = bark_lab[0] - 8 + cv2.GaussianBlur(rng.normal(0, 5, rr.shape).astype(np.float32), (0, 0), 1.0)
    b_lab = np.stack([Lb, np.full_like(Lb, bark_lab[1]), np.full_like(Lb, bark_lab[2])], -1)
    crgb = _rgb8(np.where(face[..., None], f_lab, b_lab)[box])
    wcap = np.clip((1.0 + 2.5 * rimw - rr) / (1.2 * rimw), 0, 1)
    wcap = np.clip(wcap + 0.35 * nz / 4, 0, 1)
    return box, crgb, wcap, rr


def _lab8(rgb):
    return cv2.cvtColor(np.clip(rgb, 0, 255).astype(np.uint8)[None], cv2.COLOR_RGB2LAB)[0].astype(np.float32)


def _rgb8(lab):
    return cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8)[None], cv2.COLOR_LAB2RGB)[0].astype(np.float32)


def classic_spots(job):
    """Пятна спилов классики вида z<=1 в свободной зоне F (k=1): место, размер, средний цвет."""
    c1 = np.asarray(job.tree.compose(1), np.int16)
    g1 = np.asarray(job.gtree.compose(1), np.int16) if job.gtree is not None else c1    # место - по геометрии
    r, g, al = g1[..., 0], g1[..., 1], g1[..., 3]
    thr = 90 if geom(job.S) == "FOREST" else 70
    m = (al > 128) & (r > g + 15) & (r > thr)
    n, lb, st, cen = cv2.connectedComponentsWithStats(m.astype(np.uint8), 8)
    _U, _own, F = job.masks(1)
    out = []
    for j in range(1, n):
        x, y, w, h, ar = st[j]
        if F[int(round(cen[j][1])), int(round(cen[j][0]))]:
            out.append(dict(x=int(x), y=int(y), w=int(w), h=int(h), area=int(ar),
                            c=(float(cen[j][0]), float(cen[j][1])), mean=c1[lb == j][:, :3].mean(0)))
    return out


# ---------------------------------------------------------------- ворота

def spots(rgba, S, scale):
    """Спилы по правилу цвета (как у классики): [(площадь в пикс k=1, центр k=1, высота k=1)]."""
    a = np.asarray(rgba, np.int16)
    r, g, al = a[..., 0], a[..., 1], a[..., 3]
    thr = 90 if S == "FOREST" else 70
    m = (al > 128) & (r > g + 15) & (r > thr)
    n, _lb, st, cen = cv2.connectedComponentsWithStats(m.astype(np.uint8), 8)
    minpx = 2 if scale == 1 else 8
    out = []
    for j in range(1, n):
        if st[j, 4] >= minpx:
            out.append((st[j, 4] / scale ** 2, (cen[j][0] / scale, cen[j][1] / scale), st[j, 3] / scale))
    return out


def spot_ref(world, S):
    """Цвета классики своего набора (Lab) кадров 48/50/51: спилы и остальное, маска спилов - по геометрии."""
    sp, rest = [], []
    for f in CUT_SPOT_FRAMES:
        a = np.asarray(tr.sprite(world, S, f), np.float32)
        ag = np.asarray(tr.sprite(world, geom(S), f), np.int16)
        thr = 90 if geom(S) == "FOREST" else 70
        m = (ag[..., 3] > 128) & (ag[..., 0] > ag[..., 1] + 15) & (ag[..., 0] > thr)
        sp.append(a[..., :3][m])
        rest.append(a[..., :3][(ag[..., 3] > 128) & ~m])
    sp, rest = np.concatenate(sp), np.concatenate(rest)
    # палитра классики: цвет - спил, если в маске спилов он встречается чаще, чем вне её
    cols, inv = np.unique(np.concatenate([sp, rest]).astype(np.uint8), axis=0, return_inverse=True)
    inv = inv.reshape(-1)
    n_sp = np.bincount(inv[:len(sp)], minlength=len(cols))
    n_rest = np.bincount(inv[len(sp):], minlength=len(cols))
    return _lab8(sp).mean(0), _lab8(rest).mean(0), _lab8(cols.astype(np.float32)), n_sp > n_rest


def spots_lab(rgba, ref, scale, chains=None):
    """Спилы HD производного дерева: непрозрачное, у которого ближайший (Lab) цвет классики 48/50/51 своего
    набора - цвет спила. Сравнение со средним «остального» не годится: у RED рыжая хвоя ближе к спилу, чем
    к среднему кроны, у SNOW среднее серое от снега и тёмная хвоя ушла в спилы (41 и 25 ложных пятен).
    Мера другая, чем у FOREST (там правило цвета r > g+15): проверяется контролем на каноне FOREST.
    chains (список) - тонкие цепочки переходного серого по краю снега (заполненность рамки < CHAIN_FILL и
    толщина < CHAIN_THICK пикс базы) пишутся туда и спилом не считаются."""
    a = np.asarray(rgba, np.float32)
    L = _lab8(a[..., :3].reshape(-1, 3))
    pal, is_sp = ref[2], ref[3]
    near = np.empty(len(L), np.int64)
    for i in range(0, len(L), 4096):
        near[i:i + 4096] = np.linalg.norm(L[i:i + 4096, None, :] - pal[None], axis=-1).argmin(1)
    m = (a[..., 3] > 128) & is_sp[near].reshape(a.shape[:2])
    n, lb, st, cen = cv2.connectedComponentsWithStats(m.astype(np.uint8), 8)
    minpx = 2 if scale == 1 else 8
    out = []
    for j in range(1, n):
        if st[j, 4] < minpx:
            continue
        if scale > 1 and chains is not None:
            fill = st[j, 4] / float(st[j, 2] * st[j, 3])
            thick = 2 * float(cv2.distanceTransform(np.pad((lb == j).astype(np.uint8), 1), cv2.DIST_L2, 3).max())
            if fill < CHAIN_FILL and thick < CHAIN_THICK * scale:
                chains.append([round(st[j, 4] / scale ** 2, 1), round(fill, 2), round(thick / scale, 2)])
                continue
        out.append((st[j, 4] / scale ** 2, (cen[j][0] / scale, cen[j][1] / scale), st[j, 3] / scale))
    return out


def spot_gate(world, S, frames, lab_measure=None):
    """Число, место, размер, высота спилов кадров 48/50/51 против классики. Производное дерево (или
    lab_measure=True, контроль на FOREST) - HD по мере spots_lab, классика - правилом цвета по геометрии."""
    rep = {}
    ok = True
    der = (S in tr.DERIVED) if lab_measure is None else lab_measure
    ref = spot_ref(world, S) if der else None
    if der:
        rep["measure"] = "spots_lab: Lab nearest classic colour, %d of %d spot colours (spot mean %s)" % (
            int(ref[3].sum()), len(ref[3]), [round(float(v), 1) for v in ref[0]])
    for f in CUT_SPOT_FRAMES:
        cl = spots(tr.sprite(world, geom(S), f), geom(S), 1)
        chains = []
        hd = spots_lab(frames[f], ref, 4, chains) if der else spots(frames[f], S, 4)
        if der:
            rep.setdefault("chains", {})[f] = chains
            # спил классики - связное пятно от 2 пикселей; меньше SPECK_MAX - крапина края снега или блик хвои
            # (замер 12.10: лишние у RED, BLACK, SNOW 0.5-1.2, настоящие спилы от 1.8, синтетический лишний ~3)
            rep.setdefault("specks", {})[f] = [round(h[0], 1) for h in hd if h[0] < SPECK_MAX]
            hd = [h for h in hd if h[0] >= SPECK_MAX]
        rows = []
        used = set()
        for ac, cc, hc in cl:
            best, bd = None, 1e9
            for j, (ah, ch, hh) in enumerate(hd):
                d = np.hypot(cc[0] - ch[0], cc[1] - ch[1])
                if j not in used and d < bd:
                    best, bd = j, d
            if best is None:
                rows.append(dict(classic=[round(ac), [round(v, 1) for v in cc]], hd=None, ok=False))
                ok = False
                continue
            used.add(best)
            ah, ch, hh = hd[best]
            good = bd <= 1.5 and 0.5 <= ah / ac <= 2.0 and hh <= hc + 2
            ok &= good
            rows.append(dict(classic=[round(ac), [round(v, 1) for v in cc], hc],
                             hd=[round(ah, 1), [round(v, 1) for v in ch], round(hh, 1)],
                             dist=round(float(bd), 2), area_ratio=round(ah / ac, 2), ok=bool(good)))
        extra = [dict(area=round(hd[j][0], 1), at=[round(v, 1) for v in hd[j][1]], h=round(hd[j][2], 1))
                 for j in range(len(hd)) if j not in used]
        if extra:
            ok = False
        rep[f] = dict(classic_n=len(cl), hd_n=len(hd), match=rows, extra=extra)
    return ok, rep


def z1_gates(job, raw1, cond, F_r, cut4):
    """Копия условия (R-219) и подложка внутри силуэта среза."""
    d = np.abs(np.asarray(raw1, np.int16) - np.asarray(cond, np.int16)).max(-1)
    copy = float(d[F_r].mean()) if F_r.any() else -1.0
    U, own, F = job.masks(1)
    sil = np.asarray(tr.xbrz(job.frame_z(1)))[..., 3] > 128
    b = job.box
    full = np.zeros((job.tree.H * 4, job.tree.W * 4), bool)
    full[b[1] * 4:b[3] * 4, b[0] * 4:b[2] * 4] = sil
    zone = full & tr.rep4(F)
    panel = float((cut4[..., 3][zone] < 128).mean()) if zone.any() else -1.0
    return dict(free_mean_abs_vs_cond=round(copy, 1), copy=bool(0 <= copy < 15),
                panel_in_silhouette=round(panel, 3))


def comp_gates(job, comp, v1):
    """Составной срез: подложка внутри силуэта классики, НЕ копия RGB классики, вид z<=1 против MAIN вне U."""
    U, own, F = job.masks(1)
    b = job.box
    sil = np.asarray(tr.xbrz(job.frame_z(1)))[..., 3] > 128
    full = np.zeros((job.tree.H * 4, job.tree.W * 4), bool)
    full[b[1] * 4:b[3] * 4, b[0] * 4:b[2] * 4] = sil
    zone = full & tr.rep4(F)
    panel = float((comp[..., 3][zone] < 128).mean()) if zone.any() else -1.0
    cls = np.asarray(tr.xbrz(job.frame_z(1)), np.int16)
    cl4 = np.zeros((job.tree.H * 4, job.tree.W * 4, 4), np.int16)
    cl4[b[1] * 4:b[3] * 4, b[0] * 4:b[2] * 4] = cls
    d = np.abs(comp[..., :3].astype(np.int16) - cl4[..., :3]).max(-1)
    vs_cls = float(d[zone].mean()) if zone.any() else -1.0
    out_u = ~tr.rep4(U)
    dv = tr.diff(Image.fromarray(np.where(out_u[..., None], np.asarray(v1), 0).astype(np.uint8)),
                 Image.fromarray(np.where(out_u[..., None], np.asarray(job.v2), 0).astype(np.uint8)))
    return dict(panel_in_silhouette=round(panel, 3), zone_mean_abs_vs_classic=round(vs_cls, 1),
                classic_copy=bool(0 <= vs_cls < 15), z1_view_vs_main_outside_U=dv)


# ---------------------------------------------------------------- рендер

def do_render(args, world, CL, hints):
    painter = None
    done = 0
    t0 = time.time()
    for seed in args.seeds:
        for S in args.sets:
            job = Job2(world, CL, hints, S, seed, args)
            for rel in args.release:
                p = job.raw_z1(rel)
                if os.path.exists(p):
                    continue
                if args.max_renders and done >= args.max_renders:
                    print("предел рендеров на процесс %d - выход (R-215)" % args.max_renders, flush=True)
                    return
                if not hasattr(job, "_hd"):
                    frames, _src, _info = job.base()
                    known, cond, free, _F_r, _lc, _l4 = job.canvases1(frames)
                if painter is None:
                    painter = tr.painter_new(args)
                cut = paint_locked2(painter, args, known, cond, free, tr.CUT_WHAT[(S, 1)],
                                    seed + tr.CUT_SEED[1], rel)
                po.gen_hd.save_png(cut, p)
                done += 1
                tr.check_shared("%s CUT_Z1 r%.2f s%d" % (S, rel, seed))
                print("  %s CUT_Z1 r%.2f s%d готов, свободно %.3f (%d за %.0f с)"
                      % (S, rel, seed, free.mean(), done, time.time() - t0), flush=True)
    print("рендер: всё на месте, новых %d" % done, flush=True)


# ---------------------------------------------------------------- сборка

def do_masks(args, world, CL, hints):
    for S in args.sets:
        for seed in args.seeds:
            job = Job2(world, CL, hints, S, seed, args)
            frames, src, info = job.base()
            known, cond, free, F_r, lockc, lock4 = job.canvases1(frames)
            known.save(os.path.join(job.d2, "known_z1.png"))
            cond.save(os.path.join(job.d2, "cond_z1.png"))
            tr.mask_sheet(os.path.join(job.d2, "mask_z1.png"), cond, known, free,
                          "%s CUT_Z1 s%d: free %.3f, locked 53-55 + z0" % (S, seed, free.mean()))
            z0_sheet(job, os.path.join(job.d2, "z0_seam.png"))
            print("  %s s%d: %s" % (S, seed, json.dumps(info, ensure_ascii=False)), flush=True)


def z0_sheet(job, path):
    """Кадр 57 крупно: классика | V1 z<=0 | V2 z<=0 | MAIN; и полоса шва x3."""
    t, q = job.tree, job.q57
    bx = pos_box(q)
    v1 = Image.open(os.path.join(job.d, "frames", job.S + ".PCK", "57.png")).convert("RGBA") \
        if os.path.exists(os.path.join(job.d, "frames", job.S + ".PCK", "57.png")) else Image.new("RGBA", (128, 160))
    ims = [tr.sprite(job.world, job.S, 57).resize((128, 160), Image.NEAREST), v1,
           job.v0.crop(bx), job.v2.crop(bx)]
    sh = Image.new("RGB", (4 * 136, 176), (30, 30, 34))
    dr = ImageDraw.Draw(sh)
    for j, (im, n) in enumerate(zip(ims, ("classic", "V1 57", "V2 z<=0", "MAIN"))):
        sh.paste(tr.on_floor(im), (j * 136, 16))
        dr.text((j * 136 + 2, 2), n, fill=(255, 255, 0))
    sh.resize((sh.width * 2, sh.height * 2), Image.NEAREST).save(path)


def do_assemble(args, world, CL, hints):
    over = {S: [] for S in args.sets}
    suf = "_comp" if args.z1_composite else ""        # сводка V2 не затирается
    sp = os.path.join(args.out, "summary%s.json" % suf)
    summary = json.load(open(sp, encoding=ENC)) if os.path.exists(sp) else {}    # другие наборы не затираются
    for seed in args.seeds:
        for S in args.sets:
            job = Job2(world, CL, hints, S, seed, args)
            frames0, src0, info = job.base()
            t = job.tree
            sig0 = CL[S]["sigs"][0]["sig"]
            olds = tr.old_frames(S)
            for rel in ([None] if args.z1_composite else args.release):
                if rel is None:                       # срез без модели: хвоя MAIN, крышки по пятнам классики
                    lockc, _lock4 = job.lock_z1(frames0)
                    comp, terr, cinfo, comp0, capown = job.z1_composite()
                    v1 = job.view1_comp(comp, terr, lockc)
                    v1n = job.view1_comp(comp0, terr, lockc)
                    v1_0, v1n_0 = v1, np.asarray(v1n, np.uint8)
                    if S in HOLE_FILL_SETS:
                        v1, info["holes_v1"] = fill_crown_holes(v1, job.v2)
                        v1n, _hn = fill_crown_holes(v1n, job.v2)
                    v1n = np.asarray(v1n, np.uint8)
                    tag = "comp"
                else:
                    p = job.raw_z1(rel)
                    known, cond, free, F_r, lockc, lock4 = job.canvases1(frames0)
                    if os.path.exists(p):
                        raw1 = Image.open(p).convert("RGB")
                        tag = "r%02d" % round(rel * 100)
                    elif args.dry:
                        raw1 = cond
                        tag = "dry"
                    else:
                        print("  %s s%d r%.2f: ответа нет - пропуск" % (S, seed, rel))
                        continue
                    v1, cut4 = job.view1(raw1, lockc, lock4)
                    v1_0 = v1
                frames, src = dict(frames0), dict(src0)
                views = dict(job.views)
                ref = dict(job.frames_ref)
                for j, q in enumerate(t.pcs):
                    if q["f"] in Z1_FRAMES:
                        vq, vq0 = v1, v1_0
                        if rel is None:     # крышка чужого куска в кадр не идёт: в T2 48 и 50 меняются местами
                            alien = (capown >= 0) & (capown != j)
                            if alien.any():
                                a = np.asarray(v1, np.uint8).copy()
                                a[alien] = v1n[alien]
                                vq = Image.fromarray(a)
                                a = np.asarray(v1_0, np.uint8).copy()
                                a[alien] = v1n_0[alien]
                                vq0 = Image.fromarray(a)
                        frames[q["f"]] = frame_filled(vq0, vq, q)
                        views[q["f"]] = (vq0, q)
                        ref[q["f"]] = frame_from(vq0, q)
                        src[q["f"]] = "Z1_EXPOSED"
                miss = [f for f in range(42, 58) if f not in frames]
                if miss:
                    raise SystemExit("нет канона кадров %s" % miss)
                if S in HOLE_FILL_SETS:
                    frames, info["envelope_cut_px"] = envelope_gate(world, CL, S, frames, ref)
                frames, edge = edge_rule(world, CL, S, frames, views, src)
                od = os.path.join(job.d2, tag)
                fd = os.path.join(od, "frames", S + ".PCK")
                os.makedirs(fd, exist_ok=True)
                for f, im in frames.items():
                    po.gen_hd.save_png(im, os.path.join(fd, "%d.png" % f))
                V = {2: job.v2, 1: v1, 0: job.v0}
                st = dict(info)
                st["frame_source"] = {str(f): src[f] for f in sorted(src)}
                st["edge"] = edge
                st["T1_assembled_vs_source"] = {"z<=%d" % z: tr.diff(tr.assemble(world, S, sig0, frames, z), V[z])
                                                for z in (2, 1, 0)}
                if rel is None:
                    st["z1"] = dict(cinfo, **comp_gates(job, comp, v1))
                else:
                    st["z1"] = z1_gates(job, raw1, cond, F_r, cut4)
                ok, sp = spot_gate(world, S, frames)
                st["cut_spots_ok"] = bool(ok)
                st["cut_spots"] = sp
                a0 = tr.assemble(world, S, sig0, frames, 0)
                Ys, cx = info["z0"]["seam_row"], info["z0"]["classic_cx"]
                st["z0"]["seam_assembled"] = seam_numbers(a0, job.q57, Ys, cx)
                summary["%s s%d %s" % (S, seed, tag)] = st
                # листы
                tr.grid([("whole", [("classic x4", job.whole.resize((t.W * 4, t.H * 4), Image.NEAREST)),
                                    ("old HD", tr.assemble(world, S, sig0, olds, 99)),
                                    ("MAIN (source)", job.v2),
                                    ("T1 from frames", tr.assemble(world, S, sig0, frames, 99))])],
                        os.path.join(od, "%s_whole.png" % S), "%s s%d %s: whole tree" % (S, seed, tag))
                rows = []
                for name, i in tr.LAYOUTS[S]:
                    sig = CL[S]["sigs"][i]["sig"]
                    ztop = max(e[4] for e in sig)
                    for kind, fr in (("classic", None), ("old", olds), ("new", frames)):
                        rows.append(("%s %s" % (name, kind),
                                     [("z<=%d" % z, tr.assemble(world, S, sig, fr, z)) for z in range(ztop, -1, -1)]))
                tr.grid(rows, os.path.join(od, "%s_layouts.png" % S),
                        "%s s%d %s: T1/T1b/T2/T3 from the SAME 16 frames; columns = all floors, upper hidden"
                        % (S, seed, tag), scale=0.5)
                frow = []
                for f in range(42, 58):
                    frow.append(("%d %s" % (f, src[f]), [("classic", tr.sprite(world, S, f).resize((128, 160),
                                                                                                Image.NEAREST)),
                                                         ("old", olds.get(f, Image.new("RGBA", (128, 160)))),
                                                         ("new", frames[f])]))
                half = (len(frow) + 1) // 2
                tr.grid([(a[0] + " | " + b[0], a[1] + b[1]) for a, b in zip(frow[:half], frow[half:])],
                        os.path.join(od, "%s_frames.png" % S), "%s s%d %s: frames classic | old | new" % (S, seed, tag))
                z0_sheet(job, os.path.join(od, "%s_z0.png" % S))
                over[S].append(("s%d %s" % (seed, tag),
                                [("z<=%d" % z, tr.assemble(world, S, sig0, frames, z)) for z in (2, 1, 0)]))
                print("  %s s%d %s: собрано, %s" % (S, seed, tag, json.dumps(st, ensure_ascii=False, default=_js))[:1500],
                      flush=True)
    for S, rows in over.items():
        if rows:
            sig0 = CL[S]["sigs"][0]["sig"]
            rows = [("classic", [("z<=%d" % z, tr.assemble(world, S, sig0, None, z)) for z in (2, 1, 0)]),
                    ("old", [("z<=%d" % z, tr.assemble(world, S, sig0, tr.old_frames(S), z)) for z in (2, 1, 0)])] + rows
            tr.grid(rows, os.path.join(args.out, "%s_T1_overview%s.png" % (S, suf)), "%s T1: all variants" % S, scale=0.5)
    stumps_common(args, world)
    with open(os.path.join(args.out, "summary%s.json" % suf), "w", encoding=ENC) as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1, default=_js)
    print("сборка: %s" % os.path.join(args.out, "summary%s.json" % suf))


def stumps_common(args, world):
    """Общий лист пней V1 (обе затравки рядом): классика | старый HD | s2711 | s2712."""
    rows = []
    for (S, f) in tr.STUMPS:
        spr = tr.sprite(world, S, f)
        old = os.path.join(tr.OLD, S + ".PCK", "%d.png" % f)
        r = [("classic", spr.resize((128, 160), Image.NEAREST)),
             ("old", Image.open(old).convert("RGBA") if os.path.exists(old) else Image.new("RGBA", (128, 160)))]
        for seed in (2711, 2712):
            p = os.path.join(args.v1, "s%d" % seed, "stumps", S + ".PCK", "%d.png" % f)
            if os.path.exists(p):
                r.append(("s%d" % seed, Image.open(p).convert("RGBA")))
        rows.append(("%s:%d" % (S, f), r))
    tr.grid(rows, os.path.join(args.out, "stumps_common.png"), "stumps: classic | old | s2711 | s2712")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--v1", default=V1)
    ap.add_argument("--seeds", default="2711,2712")
    ap.add_argument("--sets", default=",".join(tr.SETS), help="наборы через запятую (производные: %s)"
                    % ",".join(tr.DERIVED))
    ap.add_argument("--release", default="0.85,0.7", help="сигмы, до которых свободное держится классикой")
    ap.add_argument("--steps", type=int, default=40)
    ap.add_argument("--cfg", type=float, default=4.0)
    ap.add_argument("--mp", type=float, default=1.0)
    ap.add_argument("--zoom", type=int, default=16)
    ap.add_argument("--grow", type=int, default=2)
    ap.add_argument("--soft", type=int, default=40)
    ap.add_argument("--pad", type=int, default=3)
    ap.add_argument("--tone", type=float, default=0.7)
    ap.add_argument("--no-recolour", action="store_false", dest="recolour")
    ap.add_argument("--max-renders", type=int, default=4, dest="max_renders")
    ap.add_argument("--mask-only", action="store_true", dest="mask_only")
    ap.add_argument("--assemble", action="store_true")
    ap.add_argument("--dry", action="store_true", help="сборка с условием вместо ответа (контроль тождества)")
    ap.add_argument("--z1-composite", action="store_true", dest="z1_composite",
                    help="срез z1 без модели: хвоя из MAIN, классика - только маска и места спилов (папка comp)")
    args = ap.parse_args()
    args.seeds = [int(s) for s in args.seeds.split(",")]
    args.release = [float(s) for s in args.release.split(",")]
    args.sets = [s for s in args.sets.split(",") if s]
    bad = [s for s in args.sets if s not in tr.SETS + tr.DERIVED]
    if bad:
        raise SystemExit("неизвестные наборы %s" % bad)
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(args.out, exist_ok=True)
    world = mm.World()
    CL = json.load(open(tr.CLUSTERS, encoding=ENC))
    hints = json.load(open(tr.HINTS, encoding=ENC))
    if args.mask_only:
        do_masks(args, world, CL, hints)
    elif args.assemble:
        do_assemble(args, world, CL, hints)
    else:
        do_render(args, world, CL, hints)


if __name__ == "__main__":
    main()
