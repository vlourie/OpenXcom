r"""Приёмка связанного участка пола по НАСТОЯЩЕМУ кадру движка (дамп Ctrl+F8), а не по отдельным кадрам пака.

Зачем: проверка 28 краёв пробы тротуара сравнивала кадры с выбранным эталоном и не увидела того, что видно в игре:
сетку клеток асфальта, прямоугольные заплатки под разметкой, разметку то широкую, то ниткой (FAIL 07.10).
Здесь мерится то, что нарисовал движок: каждый пиксель карты дампа (k=4) привязан к клетке, части и кадру по
раскладке сейва (map_screen_check.render - классика восстанавливается из сейва до пикселя), а для пола - к точке
внутри клетки (gu, gv: целая часть - клетка, дробная - место в ромбе). Камера и свет - из json дампа.

Материал пикселя - по геометрии классики (label_uv): тротуар, камень бордюра (полосы вдоль краёв, ширины по
кадрам 1-4: передний бордюр 88/256, задний 41/256), асфальт, разметка (полоса 0.125 вдоль края кадров 10-12),
светлое пятно кадра 13 (по пикселям классики). Шов меряется только между пикселями ОДНОГО материала: граница
тротуар | камень | асфальт - настоящая, её ступень не шов.

Меры (по яркости Y кадра игры, только пол участка ROADS 0-13, без юнитов, предметов, пара заморозки дампа):
  step    ступень на стыке клеток: средняя Y полосы 0.06 клетки по одну сторону общего края против полосы по
          другую (один отрезок края, один материал по обе стороны); то же на линии посередине клетки (u = 0.5) -
          у сплошного покрытия они равны. Отношение медиан и худшие отрезки с клетками, кадрами и вариантами;
  line    линия по стыку: Y полосы |дробная часть| < 0.03 у края против полос 0.05-0.12 по обе стороны;
  grid    узор с периодом клетки, который видно: Y, размытая на 2 пикселя базы, по месту в ромбе (16 x 16 ячеек)
          отдельно для двух половин клеток; общее у половин (ковариация карт) - узор, шум расходится. Корень -
          амплитуда в единицах Y;
  mark    разметка: маска классики (индекс 240 кадров 10-12) x4 против светлого в HD (Y выше медианы асфальта на
          --mark-dy): доля HD-разметки вне маски (запас 1 пиксель базы), доля маски, которую HD закрыл; по каждому
          штриху - толщина (площадь на площадь классики), сдвиг средней линии и доля длины штриха с краской;
  patch   заплатка: Y и разброс зерна асфальта клеток с разметкой (без разметки и запаса) против обычного.
Пороги - PASS ниже; это диагностика к листу, принимает человек глазами.

    py -3.13 tools/hdart/crossing_check.py --save <сейв> --dump <префикс дампа> --out <папка> [--name метка]
        [--pack <папка ROADS.PCK, из которой рисовал дамп - число вариантов для списка швов>]
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ground_field as gf             # noqa: E402
import map_screen_check as msc        # noqa: E402
import xcom_sprites as xs              # noqa: E402

ENC = "utf-8-sig"
PAL_DIR = Path(__file__).resolve().parents[2] / "Пиратки/Dioxine_XPiratez/user/mods/Piratez/Resources/Pals"
LUMA = np.array([0.299, 0.587, 0.114], np.float32)
# ---- геометрия классики ROADS (кадры 32x40, ромб пола - квадрат u, v в [0, 1))
W_FRONT = 88 / 256        # передний бордюр (виден торец): кадры 1, 2 - 88 пикселей камня из 256
W_BACK = 41 / 256         # задний бордюр (только верх): кадры 3, 4 - 41 из 256
MARK_W = 0.125            # разметка: один косой ряд пикселей вдоль края, 32 пикселя (кадры 10, 11)
KERB_SIDES = {1: {"+u": W_FRONT}, 2: {"+v": W_FRONT}, 3: {"-v": W_BACK}, 4: {"-u": W_BACK},
              5: {"+u": W_FRONT, "-v": W_BACK}, 6: {"+v": W_FRONT, "-u": W_BACK},
              7: {"+u": W_FRONT, "+v": W_FRONT}, 8: {"-u": W_BACK, "-v": W_BACK}}
MARK_EDGES = {10: ("-u",), 11: ("-v",), 12: ("-u", "-v")}
WALK_FRAMES = (0,) + tuple(KERB_SIDES)
ROAD_FRAMES = (9, 10, 11, 12, 13)
L_NONE, L_WALK, L_STONE, L_ASPH, L_MARK, L_BLOB = 0, 1, 2, 3, 4, 5
LABELS = {L_WALK: "walk", L_STONE: "stone", L_ASPH: "asphalt", L_MARK: "mark", L_BLOB: "blob"}
PASS = dict(step_ratio=1.25, step_p90=1.6, line=3.0, grid=2.0, mark_outside=0.05, mark_cover=0.85,
            mark_width=(0.75, 1.35), mark_shift=0.02, mark_len=0.9, patch_dy=2.0, patch_grain=1.2, mark_rag=0.75, kerb_edge=3.0)


def side_depth(side, u, v, w):
    """Глубина в полосе бордюра стороны side шириной w: 0 у внутренней линии, 1 у края клетки, < 0 вне полосы."""
    t = {"+u": u - (1 - w), "-u": w - u, "+v": v - (1 - w), "-v": w - v}[side]
    return t / w


def kerb_side(frame, u, v):
    """Сторона бордюра пикселя кадра frame (str) или "" - тротуар. У угла - сторона с большей глубиной (стык
    по линии равной глубины: у 7 - диагональ u = v)."""
    best = np.full(np.shape(u), -1.0)
    side = np.full(np.shape(u), "", dtype=object)
    for s, w in KERB_SIDES.get(frame, {}).items():
        d = side_depth(s, u, v, w)
        take = (d >= 0) & (d > best)
        side[take] = s
        best = np.where(take, d, best)
    return side, best


def mark_band(frame, u, v):
    m = np.zeros(np.shape(u), bool)
    for e in MARK_EDGES.get(frame, ()):
        m |= (u if e == "-u" else v) < MARK_W
    return m


def label_uv(FR, fu, fv, blob=None):
    """Материал каждого пикселя по кадру и месту в ромбе. blob - маска светлого пятна кадра 13 (по классике)."""
    L = np.zeros(FR.shape, np.int8)
    for f in WALK_FRAMES:
        sel = FR == f
        if not sel.any():
            continue
        side, _d = kerb_side(f, fu[sel], fv[sel])
        L[sel] = np.where(side != "", L_STONE, L_WALK)
    for f in ROAD_FRAMES:
        sel = FR == f
        if not sel.any():
            continue
        L[sel] = np.where(mark_band(f, fu[sel], fv[sel]), L_MARK, L_ASPH)
    if blob is not None:
        L[(FR == 13) & blob] = L_BLOB
    return L


def owners(save, js_dump):
    k = int(js_dump["k"])
    W, H = int(js_dump["mapSurfaceWidth"]) // k, int(js_dump["mapSurfaceHeight"]) // k
    cam = (int(js_dump["cameraOffsetX"]) // k, int(js_dump["cameraOffsetY"]) // k, int(js_dump["cameraOffsetZ"]))
    bt = msc.mt.Battle(save)
    data = msc.mt.Data(bt.mods)
    img, owner = msc.render(bt, data, cam, W, H)
    return bt, data, k, W, H, cam, img, owner


def cover_masks(save, bt, cam, W, H):
    """Что игра рисует поверх пола и чего нет в раскладке: юниты, предметы, дым и огонь, пар заморозки дампа."""
    m = np.zeros((H, W), bool)

    def box(x, y, z, l, t, r, b):
        px = x * 16 - y * 16 + cam[0]
        py = x * 8 + y * 8 - z * 24 + cam[1]
        m[max(0, py + t):max(0, min(H, py + b)), max(0, px + l):max(0, min(W, px + r))] = True
    st = msc.unit_status(save)
    us, _sel = msc.units(save)
    for uid, (x, y, z), _f in us:
        if x < 0 or st.get(uid, 0) in (6, 7) or z > cam[2]:
            continue
        for dx in (0, 1):
            for dy in (0, 1):
                box(x - dx, y - dy, z, -8, -32, 40, 44)
    for x, y, z in msc.floor_items(save):
        if z <= cam[2]:
            box(x, y, z, 0, -8, 32, 44)
    for z, y, x in zip(*np.nonzero((bt.smoke > 0) | (bt.fire > 0))):
        if z <= cam[2]:
            box(x, y, z, -4, -16, 36, 44)
    for y in range(bt.Y):
        for x in range(bt.X):
            if (x + 2 * y) % 3 == 0:
                for n in range(16):
                    vx, vy, vz = 2 + 4 * (n % 4), 2 + 4 * (n // 4), 4 + 6 * (n % 3)
                    ox, oy = 16 + vx - vy, 24 + vx // 2 + vy // 2 - vz
                    box(x, y, cam[2], ox, oy, ox + 2, oy + 2)
    return m


def battle_seed(save, bt):
    """Зерно узора вариантов боя (Map::groundSeed) - имена блоков из сейва."""
    txt = Path(save).read_text(encoding="utf-8")
    i = txt.index("\n  flattenedMapBlockNames:\n") + len("\n  flattenedMapBlockNames:\n")
    cols, cur = [], None
    for line in txt[i:].splitlines():
        if line.startswith("    - - "):
            cur = [line[8:].strip()]
            cols.append(cur)
        elif line.startswith("      - "):
            cur.append(line[8:].strip())
        else:
            break
    return gf.battle_seed(bt.X, bt.Y, bt.Z, cols)


def variant_counts(pack):
    """{кадр: число картинок в шкале} - основная плюс .v1.. подряд."""
    out = {}
    if not pack:
        return out
    p = Path(pack)
    for f in range(14):
        n = 1
        while (p / ("%d.v%d.png" % (f, n))).exists():
            n += 1
        out[f] = n
    return out


def variant_name(f, x, y, counts, seed):
    n = counts.get(f, 1)
    if n < 2:
        return "%d (без вариантов)" % f
    order = [0] + list(range(1, n))
    mid = n // 2
    scale = [None] * n
    scale[mid] = 0
    for j in range(1, n):
        scale[mid - (j + 1) // 2 if j % 2 else mid + j // 2] = order[j]
    p = gf.pick(n, x, y, 0, seed)
    if p < 0:
        return "%d смешение вариантов" % f
    j = scale[p]
    return "%d" % f + ("" if j == 0 else ".v%d" % j)


def tile_shade(classic, img, floor0, xc, yc, k):
    """{(x, y): тень} по дампу классики (режим 0) того же сейва: индекс палитры дампа минус индекс кадра в той же
    рампе. Палитра - та из двух, с которой совпало больше пикселей пола (кислотный бой рисуется своей)."""
    pals = {}
    for n in ("delicious_regular", "dgoodpal_grinder"):
        p = PAL_DIR / (n + ".pal")
        if p.exists():
            pals[n] = np.array(xs.load_palette_file(str(p)), np.int32).reshape(-1, 3)[:256]
    dump = np.asarray(Image.open(classic + "_map.png").convert("RGB"), np.int32)[::k, ::k][:img.shape[0], :img.shape[1]]
    key = dump[..., 0] * 65536 + dump[..., 1] * 256 + dump[..., 2]
    best = None
    for n, p in pals.items():
        lut = {}
        for i in range(255, 0, -1):
            lut[int(p[i, 0] * 65536 + p[i, 1] * 256 + p[i, 2])] = i
        uk, inv = np.unique(key[floor0], return_inverse=True)
        idx = np.array([lut.get(int(u), -1) for u in uk])[inv]
        hit = float((idx >= 0).mean())
        if best is None or hit > best[0]:
            best = (hit, n, idx)
    hit, n, idx = best
    base = img[floor0].astype(np.int64)
    ok = (idx >= 0) & (idx // 16 == base // 16) & (base > 0)
    sh = idx - base
    out = defaultdict(Counter)
    for x, y, s in zip(xc[floor0][ok].tolist(), yc[floor0][ok].tolist(), sh[ok].tolist()):
        out[(x, y)][s] += 1
    print("тень клеток по дампу классики: палитра %s, совпало %.3f пикселей пола" % (n, hit))
    return {t: c.most_common(1)[0][0] for t, c in out.items()}


def box_blur(a, r):
    c = np.cumsum(np.cumsum(np.pad(a, ((r + 1, r), (r + 1, r)), mode="edge"), 0), 1)
    s = c[2 * r + 1:, 2 * r + 1:] - c[:-2 * r - 1, 2 * r + 1:] - c[2 * r + 1:, :-2 * r - 1] + c[:-2 * r - 1, :-2 * r - 1]
    return s / (2 * r + 1) ** 2


def analyse(save, prefix, out, name, mark_dy=25.0, pack=None, classic=None):
    js_dump = json.loads(Path(prefix + ".json").read_text(encoding=ENC))
    bt, data, k, W, H, cam, img, owner = owners(save, js_dump)
    hd = np.asarray(Image.open(prefix + "_map.png").convert("RGB"))[:H * k, :W * k].astype(np.float32)
    Y = hd @ LUMA
    covered = cover_masks(save, bt, cam, W, H)
    seed = battle_seed(save, bt)
    counts = variant_counts(pack)
    # клетка и кадр пола каждого пикселя базы
    t = owner - 1
    part = np.where(owner > 0, t % 4, -1)
    q = t // 4
    zc, r = np.divmod(q, bt.X * bt.Y)
    yc, xc = np.divmod(r, bt.X)
    fr_of = {}
    frame = np.full((H, W), -1, np.int32)
    floor0 = (part == 0) & (zc == 0) & ~covered
    for key in np.unique(q[floor0]):
        z, rr = divmod(int(key), bt.X * bt.Y)
        y, x = divmod(rr, bt.X)
        cur = bt.part(z, y, x, 0)
        f = -1
        if cur is not None and bt.sets[cur[0]] == "ROADS":
            f = data.mcd("ROADS")[cur[1]]["frames"][0]
        fr_of[(x, y)] = f
        frame[floor0 & (q == key)] = f
    rep = lambda a: np.repeat(np.repeat(a, k, 0), k, 1)
    FR = rep(frame)
    OK = FR >= 0
    TX = rep(np.where(frame >= 0, xc, -1))
    TY = rep(np.where(frame >= 0, yc, -1))
    # точка пола в координатах карты: gu, gv (этаж 0)
    Yi, Xi = np.mgrid[0:H * k, 0:W * k].astype(np.float32)
    sx, sy = (Xi + 0.5) / k - cam[0] - 16, (Yi + 0.5) / k - cam[1] - 24
    gu = (sx / 16 + sy / 8) / 2
    gv = (sy / 8 - sx / 16) / 2
    # место в ромбе - от клетки раскладки: пиксель-арт пола выходит за математический ромб на долю пикселя базы
    # (нижняя половина, строки 32-39 кадра), такие пиксели принадлежат своей клетке, а не соседней
    fu, fv = np.where(OK, gu - TX, 0), np.where(OK, gv - TY, 0)
    agree = float(((fu >= 0) & (fu < 1) & (fv >= 0) & (fv < 1))[OK].mean())
    spill = float(np.maximum(np.maximum(-fu, fu - 1), np.maximum(-fv, fv - 1))[OK].max())
    if spill > 1.5 / 16:
        raise SystemExit("пол вышел за ромб клетки на %.3f клетки - камера или формула" % spill)
    fu, fv = np.clip(fu, 0, 0.9999), np.clip(fv, 0, 0.9999)
    blob = rep((img >= 11) & (img <= 13) & (frame == 13))
    L = label_uv(FR, fu, fv, blob)
    L[~OK] = L_NONE
    # тень клетки от движка (солнце под крышей, свет): из дампа классики того же сейва, индекс дампа минус индекс
    # кадра. Стык клеток с разной тенью - граница света, а не шов; такие стыки не мерятся и пишутся отдельно.
    shade_of = tile_shade(classic, img, floor0, xc, yc, k) if classic else {}
    main_shade = Counter(shade_of.values()).most_common(1)[0][0] if shade_of else 0
    # чистые пиксели: тот же материал в радиусе 3 пикселей (граница материалов и край участка не мерятся)
    clean = OK.copy()
    for dy in range(-3, 4):
        for dx in range(-3, 4):
            clean &= np.roll(np.roll(L, dy, 0), dx, 1) == L
    res = dict(name=name, dump=prefix, camera=cam, k=k, hdMode=js_dump.get("hdMode"), seed=seed,
               globalShade=js_dump.get("globalShade"), point_agree=round(agree, 4), spill=round(spill, 4),
               variant_counts={str(a): b for a, b in counts.items()},
               tiles={str(a): b for a, b in sorted(Counter(v for v in fr_of.values() if v >= 0).items())})

    # ---------- step: стороны одного отрезка края, один материал по обе стороны. Отрезок края u между клетками
    # (n-1, c) и (n, c): сторона a - полоса fu 0.93..0.99 клетки n-1, сторона b - fu 0.01..0.07 клетки n.
    # Линия посередине: полосы 0.43..0.49 и 0.51..0.57 той же клетки (n = TX).
    NB = 128
    segs = {}
    for axis, loc, own, oth in (("u", fu, TX, TY), ("v", fv, TY, TX)):
        for lab, ra, rb, shift in (("edge", (0.93, 0.99), (0.01, 0.07), 1), ("mid", (0.43, 0.49), (0.51, 0.57), 0)):
            for side, (lo, hi), add in (("a", ra, shift), ("b", rb, 0)):
                sel = clean & (loc > lo) & (loc < hi)
                key = ((own[sel] + add) * NB + oth[sel]) * 8 + L[sel]
                segs[(axis, lab, side)] = (np.bincount(key, Y[sel], minlength=NB * NB * 8),
                                           np.bincount(key, minlength=NB * NB * 8))
    steps = defaultdict(lambda: {"edge": [], "mid": []})
    worst, light_edges = [], []
    for axis in ("u", "v"):
        for lab in ("edge", "mid"):
            (sa, na), (sb, nb) = segs[(axis, lab, "a")], segs[(axis, lab, "b")]
            for kk in np.nonzero((na > 40) & (nb > 40))[0].tolist():
                st = abs(sa[kk] / na[kk] - sb[kk] / nb[kk])
                l = kk % 8
                c = (kk // 8) % NB
                n = kk // 8 // NB
                if lab == "edge":
                    t1, t2 = ((n - 1, c), (n, c)) if axis == "u" else ((c, n - 1), (c, n))
                    if shade_of.get(t1, main_shade) != shade_of.get(t2, main_shade):
                        light_edges.append([list(t1), list(t2), shade_of.get(t1), shade_of.get(t2), round(st, 2)])
                        continue
                    worst.append((st, axis, l, t1, t2))
                steps[l][lab].append(st)
    res["light_edges"] = light_edges
    res["steps"] = {}
    for l, s in steps.items():
        if not s["edge"] or not s["mid"]:
            continue
        me, mm = float(np.median(s["edge"])), float(np.median(s["mid"]))
        res["steps"][LABELS[l]] = dict(edge_median=me, mid_median=mm, ratio=me / max(mm, 1e-6),
                                       edge_p90=float(np.percentile(s["edge"], 90)),
                                       mid_p90=float(np.percentile(s["mid"], 90)),
                                       p90_ratio=float(np.percentile(s["edge"], 90) / max(np.percentile(s["mid"], 90), 1e-6)),
                                       n_edge=len(s["edge"]), n_mid=len(s["mid"]))
    worst.sort(key=lambda w: -w[0])
    base = {LABELS[l]: float(np.percentile(s["mid"], 90)) for l, s in steps.items() if s["mid"]}
    res["worst_seams"] = []
    for st, axis, l, t1, t2 in worst[:25]:
        f1, f2 = fr_of.get(t1, -1), fr_of.get(t2, -1)
        res["worst_seams"].append(dict(step=round(st, 2), mid_p90=round(base.get(LABELS[l], 0), 2), material=LABELS[l],
                                       edge=axis, tiles=[list(t1), list(t2)], frames=[f1, f2],
                                       slots=["ROADS:%s" % variant_name(f1, *t1, counts, seed) if f1 >= 0 else "-",
                                              "ROADS:%s" % variant_name(f2, *t2, counts, seed) if f2 >= 0 else "-"]))

    # ---------- line: тёмная или светлая нитка по самому стыку
    def line_score(loc, sel):
        d = np.minimum(loc, 1 - loc)
        on = clean & sel & (d < 0.03)
        near = clean & sel & (d > 0.05) & (d < 0.12)
        if on.sum() < 50 or near.sum() < 50:
            return None
        return float(Y[on].mean() - Y[near].mean())
    res["line"] = {LABELS[l]: dict(u=line_score(fu, L == l), v=line_score(fv, L == l))
                   for l in (L_WALK, L_STONE, L_ASPH)}

    # ---------- jump: скачок соседних пикселей ПОПЕРЁК линии стыка против скачка поперёк параллельной линии
    # посередине клетки (те же диагонали, та же доля пар). Ступень по полосам (step) усредняет полосу вдоль всего
    # края и разрыв зерна не видит: контроль crop (вырезы без складки) давал те же числа, что сплошное поле.
    # Пара - соседи по x или по y; стык - сменилась клетка геометрии (floor gu или gv), середина - сменилось
    # floor(gu + 0.5) или floor(gv + 0.5) при той же клетке. Точки пара hdTestFreeze (R-243) - ярче местного
    # среднего на 25 - не мерятся
    px_shade = np.full((H, W), main_shade, np.int32)
    for (x, y), s in shade_of.items():
        px_shade[floor0 & (xc == x) & (yc == y)] = s
    px_shade = rep(px_shade)
    ok_j = clean & (np.abs(Y - box_blur(Y, 2 * k)) < 25)
    cu, cv = np.floor(gu), np.floor(gv)
    mu, mv = np.floor(gu + 0.5), np.floor(gv + 0.5)
    res["jump"] = {}
    acc = {l: dict(edge=[], mid=[], seg_e=defaultdict(list), seg_m=defaultdict(list)) for l in (L_WALK, L_STONE, L_ASPH)}
    for dy, dx in ((0, 1), (1, 0)):
        sl_a = (slice(0, H * k - dy), slice(0, W * k - dx))
        sl_b = (slice(dy, H * k), slice(dx, W * k))
        both = ok_j[sl_a] & ok_j[sl_b] & (L[sl_a] == L[sl_b]) & (px_shade[sl_a] == px_shade[sl_b])
        dY = np.abs(Y[sl_a] - Y[sl_b])
        edge = both & ((cu[sl_a] != cu[sl_b]) | (cv[sl_a] != cv[sl_b]))
        mid = both & ~edge & ((mu[sl_a] != mu[sl_b]) | (mv[sl_a] != mv[sl_b]))
        la = L[sl_a]
        ta, tb = TX[sl_a] * 1000 + TY[sl_a], TX[sl_b] * 1000 + TY[sl_b]
        for l in acc:
            e, m = edge & (la == l), mid & (la == l)
            acc[l]["edge"].append(dY[e])
            acc[l]["mid"].append(dY[m])
            for key, d in zip((np.minimum(ta[e], tb[e]) * 1000003 + np.maximum(ta[e], tb[e])).tolist(), dY[e].tolist()):
                acc[l]["seg_e"][key].append(d)
            for key, d in zip(ta[m].tolist(), dY[m].tolist()):
                acc[l]["seg_m"][key].append(d)
    for l, s in acc.items():
        e, m = np.concatenate(s["edge"]), np.concatenate(s["mid"])
        if e.size < 200 or m.size < 200:
            continue
        se = [float(np.mean(v)) for v in s["seg_e"].values() if len(v) >= 40]
        sm = [float(np.mean(v)) for v in s["seg_m"].values() if len(v) >= 40]
        r = dict(edge_mean=float(e.mean()), mid_mean=float(m.mean()), ratio=float(e.mean() / max(m.mean(), 1e-6)),
                 n_edge=int(e.size), n_mid=int(m.size))
        if len(se) >= 5 and len(sm) >= 5:
            r["seg_p90_ratio"] = float(np.percentile(se, 90) / max(np.percentile(sm, 90), 1e-6))
            r["seg_max"] = float(max(se))
            r["n_seg"] = len(se)
        res["jump"][LABELS[l]] = r

    # ---------- grid: узор с периодом клетки, общий у двух половин клеток (шум между половинами расходится)
    Yl = box_blur(Y, 2 * k)
    half = ((TX * 7 + TY * 13) % 2) == 0
    res["grid"] = {}
    same_light = np.ones(L.shape, bool)
    if shade_of:
        st_map = np.full((H, W), main_shade, np.int32)
        for (x, y), s in shade_of.items():
            st_map[floor0 & (xc == x) & (yc == y)] = s
        same_light = rep(st_map == main_shade)
    for l in (L_WALK, L_ASPH, L_STONE):
        sel0 = clean & (L == l) & same_light
        maps = []
        for h in (half, ~half):
            sel = sel0 & h
            if sel.sum() < 4000:
                break
            b = np.clip((fu[sel] * 16).astype(int), 0, 15) * 16 + np.clip((fv[sel] * 16).astype(int), 0, 15)
            cnt = np.bincount(b, minlength=256)
            s = np.bincount(b, Yl[sel], minlength=256)
            maps.append((s, cnt))
        if len(maps) < 2:
            continue
        have = (maps[0][1] > 30) & (maps[1][1] > 30)
        if have.sum() < 30:
            continue
        ma, mb = maps[0][0][have] / maps[0][1][have], maps[1][0][have] / maps[1][1][have]
        cov = float(np.mean((ma - ma.mean()) * (mb - mb.mean())))
        res["grid"][LABELS[l]] = dict(amp=float(np.sqrt(max(cov, 0.0))), lowpass_std=float(Yl[sel0].std()),
                                      cells=int(have.sum()))

    # ---------- разметка: классика (индекс 240 кадров 10-12) против светлого HD
    cl_mark = rep((img == 240) & np.isin(frame, (10, 11, 12)))
    zone = cl_mark.copy()
    for dy in range(-k, k + 1):
        for dx in range(-k, k + 1):
            zone |= np.roll(np.roll(cl_mark, dy, 0), dx, 1)
    road = OK & np.isin(FR, ROAD_FRAMES)
    asph = road & ~zone & (L == L_ASPH)
    med = float(np.median(Y[asph])) if asph.any() else 0.0
    hd_mark = road & (Y > med + mark_dy)
    # клубки пара hdTestFreeze (R-243) - насыщенные пятна на сером покрытии; в дампе классики покрытие само цветное
    # (палитра кислотного дождя), там пар - то, что насыщеннее покрытия на 30, кроме разметки классики
    chroma = hd.max(2) - hd.min(2)
    c0 = float(np.median(chroma[OK]))
    vap = chroma > c0 + 30
    if c0 > 15:
        vap &= ~cl_mark
    outside = hd_mark & ~zone
    per_tile = Counter()
    for x, y in zip(TX[outside].tolist(), TY[outside].tolist()):
        per_tile[(x, y, fr_of.get((x, y)))] += 1
    dashes = []
    for (x, y), f in sorted(fr_of.items()):
        if f not in (10, 11):
            continue
        sel_t = (TX == x) & (TY == y)
        cl_n = int((cl_mark & sel_t).sum())
        if cl_n < 64:
            continue
        across, along = (fu, fv) if f == 10 else (fv, fu)
        m = hd_mark & zone & sel_t
        n = int(m.sum())
        bins = np.zeros(16, bool)
        if n:
            bins[np.clip((along[m] * 16).astype(int), 0, 15)] = True
        cbins = np.zeros(16, bool)
        cm = cl_mark & sel_t
        cbins[np.clip((along[cm] * 16).astype(int), 0, 15)] = True
        # лесенка края штриха: в координатах клетки край краски - прямая across = const. По 48 отрезкам вдоль
        # штриха (концы 10 процентов не берутся) - внешний и внутренний край краски; отклонение от медианы в
        # пикселях экрана по вертикали (единица across - 16k пикселей), 80-й процентиль. Лесенка базы x4 - около
        # 1.6, прямой край - около 0.5. Краска берётся без хозяина клетки (рядом с разметкой классики этой клетки,
        # координаты - геометрия карты): лесенку даёт как раз соседняя клетка, чей силуэт закрывает край штриха,
        # и по хозяину классики эти пиксели выпадали
        rag, edges_dbg = None, None
        ys_c, xs_c = np.nonzero(cm)
        y0, y1 = max(ys_c.min() - 2 * k, 0), ys_c.max() + 2 * k + 1
        x0, x1 = max(xs_c.min() - 2 * k, 0), xs_c.max() + 2 * k + 1
        cmb = cm[y0:y1, x0:x1]
        near = cmb.copy()
        for dy in range(-k, k + 1):
            for dx in range(-k, k + 1):
                near |= np.roll(np.roll(cmb, dy, 0), dx, 1)
        ga, gb = gu[y0:y1, x0:x1] - x, gv[y0:y1, x0:x1] - y
        g_ac, g_al = (ga, gb) if f == 10 else (gb, ga)
        mg = hd_mark[y0:y1, x0:x1] & near & (g_al >= 0) & (g_al < 1)
        if mg.sum() >= 50:
            ac, al = g_ac[mg], g_al[mg]
            b48 = np.clip((al * 48).astype(int), 0, 47)
            # отрезки, где у края штриха клубок пара hdTestFreeze (R-243), не берутся: он закрывает край
            vb = vap[y0:y1, x0:x1] & near & (g_al >= 0) & (g_al < 1)
            vap_bins = set(np.clip((g_al[vb] * 48).astype(int), 0, 47).tolist())
            lo_e, hi_e = [], []
            for b in range(5, 43):
                s_b = b48 == b
                if s_b.sum() >= 3 and not ({b - 1, b, b + 1} & vap_bins):
                    lo_e.append(float(ac[s_b].min()))
                    hi_e.append(float(ac[s_b].max()))
            if len(lo_e) >= 12:
                # отклонение от скользящей медианы по 9 отрезкам, а не от одной медианы: у конца штриха и на изломе
                # V край законно идёт под углом (у классики там 2-2.5), а ступень лесенки - короче трёх отрезков
                def jag(e):
                    e = np.array(e)
                    tr = np.array([np.median(e[max(i - 4, 0):i + 5]) for i in range(len(e))])
                    return float(np.percentile(np.abs(e - tr), 80))
                rag = round(max(jag(lo_e), jag(hi_e)) * 16 * k, 2)
                edges_dbg = [[round(v * 16 * k, 2) for v in e] for e in (lo_e, hi_e)]
        dashes.append(dict(tile=[x, y], frame=f, width=round(n / cl_n, 2), edge_rag=rag, edges=edges_dbg,
                           centre=round(float(across[m].mean()), 4) if n else None,
                           centre_classic=round(float(across[cl_mark & sel_t].mean()), 4),
                           length=round(float((bins & cbins).sum() / max(cbins.sum(), 1)), 3),
                           length_extra=round(float((bins & ~cbins).sum() / 16), 3)))
    res["mark"] = dict(asphalt_median=med, threshold=med + mark_dy, classic_px=int(cl_mark.sum()),
                       hd_px=int(hd_mark.sum()), outside_px=int(outside.sum()),
                       outside_share=float(outside.sum() / max(hd_mark.sum(), 1)),
                       cover=float((hd_mark & cl_mark).sum() / max(cl_mark.sum(), 1)),
                       dashes=dashes, outside_tiles=[[*kk, n] for kk, n in per_tile.most_common(20)])

    # ---------- заплатка: асфальт клеток с разметкой без самой разметки против обычного
    def grain(sel):
        hp = Y - box_blur(Y, 3 * k)
        return float(hp[sel].std())
    plain = clean & (FR == 9) & (L == L_ASPH) & ~zone
    marked_base = clean & np.isin(FR, (10, 11, 12)) & (L == L_ASPH) & ~zone
    if plain.sum() > 1000 and marked_base.sum() > 1000:
        res["patch"] = dict(plain_mean=float(Y[plain].mean()), marked_mean=float(Y[marked_base].mean()),
                            dy=float(Y[marked_base].mean() - Y[plain].mean()),
                            grain_plain=grain(plain), grain_marked=grain(marked_base))
        res["patch"]["grain_ratio"] = res["patch"]["grain_marked"] / max(res["patch"]["grain_plain"], 1e-6)

    # ---------- край бордюра у асфальта: полоса 1/16 клетки асфальта (кадр 9) вдоль стороны бордюра, по ГЕОМЕТРИИ
    # карты (клетка floor(gu), floor(gv)), а не по хозяину классики. В клине у верхней вершины асфальта альфа -
    # силуэт классики, сквозь него виден выступ кадра бордюра; хозяин классики там тоже бордюр, и меры выше этот
    # выступ считали камнем. Отрезки вдоль края - 16, 0 у вершины асфальта на стороне +u/+v; dY - средний Y отрезка
    # минус медиана середины той же клетки, сумма по всем сторонам одного направления. Ступенька у каждой вершины
    # (контроль wedge) - 10 и больше, зубцы классики - 15-20 через отрезок
    cxg, cyg = np.floor(gu).astype(np.int32), np.floor(gv).astype(np.int32)
    gfu, gfv = gu - cxg, gv - cyg
    # объекты на клетке (столб на бордюре - part 3 у хозяина классики) - с запасом 2 пикселя базы: HD-кадр объекта
    # шире классического
    obj = (owner > 0) & (part != 0)
    obj_d = obj.copy()
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            obj_d |= np.roll(np.roll(obj, dy, 0), dx, 1)
    good_px = ~rep(covered) & ~vap & ~rep(obj_d)
    side_bins = defaultdict(lambda: np.zeros((2, 16)))
    kerb_edges = []
    for (x, y), f in sorted(fr_of.items()):
        for s in KERB_SIDES.get(f, {}):
            nx, ny = {"+u": (x + 1, y), "-u": (x - 1, y), "+v": (x, y + 1), "-v": (x, y - 1)}[s]
            if fr_of.get((nx, ny)) != 9:
                continue
            cell = good_px & (cxg == nx) & (cyg == ny)
            mid = cell & (gfu > 0.25) & (gfu < 0.75) & (gfv > 0.25) & (gfv < 0.75)
            if mid.sum() < 200:
                continue
            ref = float(np.median(Y[mid]))
            dist = {"+u": gfu, "-u": 1 - gfu, "+v": gfv, "-v": 1 - gfv}[s]
            along = gfv if s in ("+u", "-u") else gfu
            strip = cell & (dist < 1 / 16)
            b = np.clip((along[strip] * 16).astype(int), 0, 15)
            sm = np.bincount(b, Y[strip] - ref, minlength=16)
            n = np.bincount(b, minlength=16)
            side_bins[s] += np.stack([sm, n])
            dy = np.where(n >= 8, sm / np.maximum(n, 1), 0)
            kerb_edges.append(dict(kerb=[x, y], frame=f, side=s, road=[nx, ny], worst_dy=round(float(np.abs(dy).max()), 2),
                                   worst_bin=int(np.abs(dy).argmax())))
    if kerb_edges:
        prof = {s: np.where(bn[1] >= 30, bn[0] / np.maximum(bn[1], 1), 0) for s, bn in side_bins.items()}
        worst = max((float(np.abs(p).max()), s, int(np.abs(p).argmax())) for s, p in prof.items())
        res["kerb_edge"] = dict(worst_dy=round(worst[0], 2), worst_side=worst[1], worst_bin=worst[2],
                                profile={s: [round(float(q), 2) for q in p] for s, p in prof.items()},
                                edges=sorted(kerb_edges, key=lambda e: -e["worst_dy"])[:12])

    # ---------- цвет по материалам: HD и классика (индексы раскладки в обычной палитре боя)
    res["colour"] = {LABELS[l]: [round(float(c), 1) for c in hd[clean & (L == l)].mean(0)]
                     for l in LABELS if (clean & (L == l)).sum() > 500}

    res["verdict"] = verdict(res)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / ("check_%s.json" % name)).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding=ENC)
    # карта: светлое вне разметки - красным, край маски классики - зелёным, худшие швы - пурпурные полосы сторон
    vis = hd.copy()
    vis[outside] = (255, 0, 64)
    edge_cl = cl_mark & ~np.roll(cl_mark, 1, 0)
    vis[edge_cl] = (0, 255, 0)
    for w in res["worst_seams"][:12]:
        (x1, y1), (x2, y2) = w["tiles"]
        if w["edge"] == "u":
            m = (TX == x2) & (TY == y2) & (fu < 0.02)
        else:
            m = (TX == x2) & (TY == y2) & (fv < 0.02)
        vis[m & OK] = (255, 0, 255)
    Image.fromarray(np.clip(vis, 0, 255).astype(np.uint8)).save(out / ("diag_%s.png" % name))
    return res


def verdict(res):
    """Меры приёмки и диагностика (статус DIAG, в итог не идёт). В диагностику ушли меры, которые на дампах 07.10
    (_dumps/_check, перекрёсток corner.sav) не отделяют брак от нормы: медиану ступени шва проваливает сама
    классика (тротуар 1.33) и все сборки поровну (новое 1.55, отклонённый пак 1.63), а полосы старых соседей
    ловит 90-й процентиль (старые соседи 13.6, отклонённый пак 22.3, новое 1.42); нитка по стыку камня - профиль
    глубины бордюра, у классики -8.0. Порог сетки 2.0 - уровень ковра классики этого сейва (1.61-1.93); старые
    соседи 2.66, отклонённый пак 5.96. Каждая мера приёмки проверена контролем, который обязан её провалить:
    crop - лесенка края штриха, patch - заплатка, old - ступень p90 тротуара и асфальта.
    Три класса: согласованность (швы, сетка, заплатка, разметка по маске классики) - классика её проходит, это
    калибровка; требование HD (статус hd: прямой край штриха и бордюра) - классика по природе пиксельная
    лесенка, её провал здесь не брак, а эталон того, что HD убирает (failed(..., reference=True) его не
    считает); диагностика (diag) - в итог не идёт ни у кого."""
    v, diag, hd = {}, set(), set()
    for mat, st in res["steps"].items():
        if mat in ("walk", "stone", "asphalt"):
            kk = "шов %s: ступень на стыке / посередине (медиана)" % mat
            v[kk] = (round(st["ratio"], 2), st["ratio"] <= PASS["step_ratio"])
            diag.add(kk)
            v["шов %s: то же, 90-й процентиль" % mat] = (round(st["p90_ratio"], 2), st["p90_ratio"] <= PASS["step_p90"])
    for mat, ln in res["line"].items():
        for ax in ("u", "v"):
            if ln[ax] is not None:
                kk = "нитка по стыку %s %s, dY" % (mat, ax)
                v[kk] = (round(ln[ax], 2), abs(ln[ax]) <= PASS["line"])
                if mat == "stone":
                    diag.add(kk)
    for mat, g in res["grid"].items():
        if mat == "stone":      # у камня профиль глубины бордюра - узор с периодом клетки по замыслу; в отчёте
            continue
        v["сетка клеток %s, амплитуда Y" % mat] = (round(g["amp"], 2), g["amp"] <= PASS["grid"])
    m = res["mark"]
    if m["classic_px"]:
        v["светлое вне разметки, доля"] = (round(m["outside_share"], 3), m["outside_share"] <= PASS["mark_outside"])
        v["разметка закрыта, доля маски классики"] = (round(m["cover"], 3), m["cover"] >= PASS["mark_cover"])
        ws = [d["width"] for d in m["dashes"]]
        if ws:
            lo, hi = PASS["mark_width"]
            v["толщина штрихов (худший)"] = ("%.2f..%.2f" % (min(ws), max(ws)), lo <= min(ws) and max(ws) <= hi)
            sh = [abs(d["centre"] - d["centre_classic"]) for d in m["dashes"] if d["centre"] is not None]
            if sh:
                v["сдвиг средней линии штриха, доли клетки"] = (round(max(sh), 3), max(sh) <= PASS["mark_shift"])
            rg = [d["edge_rag"] for d in m["dashes"] if d.get("edge_rag") is not None]
            if rg:
                v["лесенка края штриха, пикс x4 (худший)"] = (max(rg), max(rg) <= PASS["mark_rag"])
                hd.add("лесенка края штриха, пикс x4 (худший)")
            ln = [d["length"] for d in m["dashes"]]
            v["длина штриха с краской / длина у классики (худший)"] = (round(min(ln), 2), min(ln) >= PASS["mark_len"])
    if "patch" in res:
        p = res["patch"]
        v["заплатка: dY асфальта под разметкой"] = (round(p["dy"], 2), abs(p["dy"]) <= PASS["patch_dy"])
        v["заплатка: зерно под разметкой / обычное"] = (round(p["grain_ratio"], 2),
                                                       1 / PASS["patch_grain"] <= p["grain_ratio"] <= PASS["patch_grain"])
    if "kerb_edge" in res:
        ke = res["kerb_edge"]
        v["край бордюра: чужое в полосе асфальта, dY (худший отрезок)"] = (ke["worst_dy"], ke["worst_dy"] <= PASS["kerb_edge"])
        hd.add("край бордюра: чужое в полосе асфальта, dY (худший отрезок)")
    return {kk: [a, ("diag " if kk in diag else "hd " if kk in hd else "") + ("PASS" if b else "FAIL")]
            for kk, (a, b) in v.items()}


def failed(verdict_, reference=False):
    """Проваленные меры приёмки: согласованность всегда, требования HD - кроме эталона классики (reference)."""
    return [kk for kk, x in verdict_.items() if x[1] == "FAIL" or (x[1] == "hd FAIL" and not reference)]


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--save", required=True)
    ap.add_argument("--dump", required=True, help="префикс дампа Ctrl+F8 (без _map.png / .json)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", default="")
    ap.add_argument("--pack", default="", help="папка ROADS.PCK, из которой рисовал дамп (варианты в списке швов)")
    ap.add_argument("--classic", default="", help="префикс дампа классики (режим 0) того же сейва и камеры - тень клеток")
    ap.add_argument("--mark-dy", type=float, default=25.0)
    a = ap.parse_args(argv)
    r = analyse(a.save, a.dump, a.out, a.name or Path(a.dump).parent.name, a.mark_dy, a.pack, a.classic or None)
    print("%s: hdMode %s, камера %s, клеток участка %s" % (r["name"], r["hdMode"], r["camera"], r["tiles"]))
    for kk, vv in r["verdict"].items():
        print("  %-52s %10s  %s" % (kk, vv[0], vv[1]))
    reference = r["name"].startswith("classic")
    nfail = len(failed(r["verdict"], reference))
    print("  цвет:", r["colour"])
    print("  худшие швы:")
    for w in r["worst_seams"][:8]:
        print("    %5.2f (посередине p90 %.2f) %-7s край %s: %s %s | %s %s" % (
            w["step"], w["mid_p90"], w["material"], w["edge"], w["tiles"][0], w["slots"][0], w["tiles"][1],
            w["slots"][1]))
    print("ИТОГ%s: %s (провалено мер %d)" % (" (эталон классики: требования HD не считаются)" if reference else "",
                                         "FAIL" if nfail else "PASS", nfail))
    return 1 if nfail else 0


if __name__ == "__main__":
    sys.exit(main())
