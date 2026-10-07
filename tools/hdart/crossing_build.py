r"""Сборка связанного участка перекрёстка ROADS 0-13 без новой генерации (тротуар - ответ модели s7101, асфальт и
камень - процедурные фактуры, видеокарта не нужна).

История: FAIL визуальной приёмки 07.10 (сетка асфальта, заплатки под разметкой) - собран весь участок из одного
поля; второе замечание специалиста 07.10 (чистые кадры): ступеньки профиля во внутренних углах бордюров, выступ
в вершине V, заострённые концы штрихов, решётка крупнее и контрастнее классики, бордюр читается тёмной канавкой,
одна перекрашенная фактура тротуара на все материалы. Эта сборка - доводка по нему.

Материалы (у каждого кадра 4 картинки <N>.png, <N>.v1-v3.png; вариант j всех кадров из одних клеток j - движок
сшивает варианты сам, groundFrameFor):
  тротуар  - клетки вариантов из ответа модели (sidewalk_probe.make_cells), тон и зерно классики ROADS:0; кладки
             нет (ориентир - ровное крапчатое серое покрытие оригинала);
  асфальт  - ПРОЦЕДУРНАЯ фактура заполнителя (aggregate_cells): мелкий крап связующего плюс зёрна щебня
             2-7 пикселей текстуры, светлые и тёмные, с бликом от света сверху-слева; периодическая клетка, тон и
             разброс яркости классики ROADS:9. Одни и те же клетки во всех кадрах 9-13 и в выступах кадров
             бордюра - под разметкой и решёткой тот же асфальт;
  камень   - ПРОЦЕДУРНАЯ поверхность (stone_cells): гранитный крап и слабые пятна - множитель к профилю бордюра;
  бордюр   - кадры 1-8, стороны KERB_SIDES (crossing_check): +u, +v - передний 88/256 (виден торец), -u, -v -
             задний 41/256 (только верх). Профиль поперёк полосы - ПИКСЕЛИ строки классики (row_profile: строки
             кадра своей стороны, где камень идёт подряд ровно на ширину полосы, 11 или 5 пикселей), без размытия:
             у переднего шов, блик кромки, верхняя грань 4 пикселя, ребро, боковая грань 4 пикселя (у +v
             освещённая, у +u в тени); у заднего верх 2, дальнее ребро 1 и кромка у асфальта 2. Тон граней -
             stone_profile: у классики верхняя грань по яркости равна асфальту (Y 21-28 при 23), и в HD полоса
             читалась тёмной канавкой; оттенок камня один (средний верхней грани классики), яркость по грани -
             верх 46, дальнее ребро 58 (блик), ближнее 52, шов 30, у заднего тень у асфальта 30/16; боковая грань
             переднего - цвет классики. Внутри грани - интерполяция между
             центрами пикселей, между гранями - ступень (прежняя сборка размывала профиль гауссом по 24 ячейкам,
             и грани сливались в тёмную канавку). Владение у угла (kerb_owner): сначала боковая грань переднего
             бордюра (до ребра), у двух передних - ближайшая к краю (угол 7 - по u = v); остальное - сторона, где
             точка дальше по своей верхней грани в долях её ширины. Так верхние грани стыкуются по линии от
             внутреннего угла к внешнему углу верхней грани (углы 5, 6), а не по линии равной доли всей полосы,
             давшей ступеньку профиля (замечание 07.10); покрытие по 16 подточкам пикселя x4;
  разметка - кадры 10-12: полоса классики u (v) от 1/32 до 5/32 вдоль края -u (10), -v (11) или обоих (12).
             Верхний конец (у верхней вершины) на карте перекрёстка всегда свободный - срез ПОПЕРЁК полосы, по
             ребру клетки (v = 0 у 10, u = 0 у 11). Боковой конец (левая вершина у 10, правая у 11) срезан
             ВЕРТИКАЛЬЮ ЭКРАНА через вершину: v - u до 1 у 10, u - v до 1 у 11. В узле (55,12) боковые концы
             штриха 10 клетки сверху и штриха 11 клетки слева сходятся в V, и V - точный стык по вертикали без
             выступа. Поперечный боковой конец вместе с точным V невозможен: картинка кадра шириной ровно в клетку,
             острие V лежит в клине клетки под узлом, правую его половину рисует только сосед сверху, левую -
             только сосед слева, а кадр один на V и на свободные боковые концы. Свободный боковой конец поэтому под
             63 градуса к полосе на экране (45 в мире). Кадр 12 (на карте нет) - угол Λ вертикалью;
  решётка 13 - пластина по крайним пикселям прутьев классики (11-13) с запасом 1/64; прутья вдоль u, шаг -
             сильнейшая гармоника; цвет - непрерывный профиль по фазе шага (12 ячеек средних классики, без деления
             на пруток и прорезь - контраст классики, а не двух крайних тонов); рамка по пикселям классики:
             снаружи кольцо 1/32 цвета 250 (Y 14) по -u, -v и +u, по +v кольца нет; тёмные 251/252 (Y 7-11) -
             внутри пластины полосой 1/16 вдоль -u и +v, тень в углублении стока (прежняя сборка ставила тёмную
             кромку снаружи со всех сторон - решётка читалась крупнее и контрастнее, замечание 07.10).
Альфа: силуэт классики x4, точный ромб x4 (центр пикселя в [0, 1)^2) и выступы в клин соседей - Ru (u от 1 до
1 + 3/16 + 1/32, v до 3/16 + 1/32: левая половина клина клетки справа) и Rv (то же с v): там все кадры рисуют
асфальт поля и продолжение своей разметки. У асфальта (9-13) в своём клине (u, v < 3/16) альфа - только своя
разметка: клин рисуют выступы соседей (асфальт и концы их штрихов), поверх - свой штрих. Выступ кадра бордюра
за стороной к асфальту - асфальт того же поля (R-248). У края карты клин асфальта без соседа сверху или слева
пуст (выемка у края карты).

Контроли (обязаны ПРОВАЛИТЬ crossing_check по дампу игры):
  --control crop   клетки без периодичности (тротуар - вырезы ответа, асфальт и камень - кусок поля вдвое
                   больше клетки), альфа - только силуэт классики: лесенка у края разметки и бордюра;
  --control patch  асфальт кадров 10-12 - другая клетка (другое зерно), на 15 процентов светлее и крупнее зерном:
                   заплатки под разметкой;
  --control old    кадры 2, 4, 9, 12 остаются картинками установки без вариантов - старые соседи;
  --control wedge  выступ кадров бордюра за стороной к асфальту и в клин соседа - внешний цвет камня: ступенька
                   края бордюра в клине у верхней вершины асфальта.

    py -3.13 tools/hdart/crossing_build.py build [--tag new] [--control crop|patch|old|wedge]
    py -3.13 tools/hdart/crossing_build.py preview --tag new        # участок без игры, раскладкой движка
    py -3.13 tools/hdart/crossing_build.py mods --tag new           # дерево модов для невидимого прогона
    py -3.13 tools/hdart/crossing_build.py sheet [--main new]       # лист по дампам игры _dumps/<метка>/dump
                                     (классика, HD сейчас, новое, контроли, без дождя - что из этого снято)

Кладёт в census/maps/pilot2/probe_crossing/<метка>/: ROADS.PCK/<кадр>.png, build.json, preview.png; дерево модов
в _mods/<метка> (соединения на установку, своя только hd/TERRAIN/ROADS.PCK - установку не трогает; снимать
соединения только rmdir, R-047). В пак мода НЕ идёт.
"""
import argparse
import json
import math
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crossing_check as cc           # noqa: E402
import ground_field as gf             # noqa: E402
import pilot2_job_sheet as js         # noqa: E402
import sidewalk_probe as sp           # noqa: E402

ROOT = js.ROOT
OUT = ROOT / "census" / "maps" / "pilot2" / "probe_crossing"
RAW = ROOT / "census" / "maps" / "pilot2" / "probe_sidewalk" / "raw_s7101.png"
ENC = "utf-8-sig"
K = js.K
LUMA = sp.LUMA
SUFFIX = ("", ".v1", ".v2", ".v3")
FRAMES = tuple(range(14))
OLD_FRAMES = (2, 4, 9, 12)                             # контроль old: кадры установки остаются как есть
SIDE_FRAME = {"+u": 1, "+v": 2, "-v": 3, "-u": 4}      # кадр классики, где эта сторона бордюра одна
FRONT = ("+u", "+v")
KERB_N = {"+u": 11, "+v": 11, "-u": 5, "-v": 5}        # пикселей камня в строке классики поперёк полосы
# грани профиля (пиксели от внутренней линии к краю, включительно): у переднего шов, блик кромки, верх, ребро,
# боковая грань; у заднего верх, дальнее ребро и кромка у асфальта. Внешняя часть - всё за верхней гранью: доля OUTER ширины полосы
FACES = {"front": ((0, 0), (1, 1), (2, 5), (6, 6), (7, 10)), "back": ((0, 1), (2, 2), (3, 4))}
OUTER = {"front": 4 / 11, "back": 3 / 5}
MARK_LO, MARK_HI = 1 / 32, 5 / 32                      # полоса разметки классики (пиксели индекса 240)
MARK_SIDE_END = 1.125                                   # боковой конец классики: низ строки 32 базы, u + v (горизонталь)
MARK_INDEX = 240
WEDGE = 3 / 16                                         # клин у верхней вершины асфальта
REACH = WEDGE + 1 / 32                                 # выступ в клин соседа - с запасом
LIGHT = np.array([-3.0, -1.0]) / math.sqrt(10.0)       # к свету в осях (u, v): экран сверху-слева


def kind(side):
    return "front" if side in FRONT else "back"


# ------------------------------------------------------------------ классика

def classic_tone(f, sel):
    """Средний цвет и разброс яркости пикселей кадра f классики, отобранных sel(idx)."""
    idx, _ = js.gm.classic("ROADS", f)
    px = js.PAL[idx[sel(idx)]].astype(np.float32)
    return px.mean(0), float((px @ LUMA).std())


def row_profile(side):
    """Профиль камня поперёк полосы стороны side по пикселям классики: строки кадра SIDE_FRAME[side], где от края
    (правый конец строки у +u и -v, левый у +v и -u) подряд идут ровно KERB_N пикселей рампы 15 (240+); средний
    цвет каждой позиции, от внутренней линии к краю. Возвращает (n, 3) и число строк."""
    f, n = SIDE_FRAME[side], KERB_N[side]
    idx, _ = js.gm.classic("ROADS", f)
    runs = []
    for row in idx:
        nz = np.nonzero(row)[0]
        if not len(nz):
            continue
        seq = row[nz[0]:nz[-1] + 1]
        if side in ("+u", "-v"):
            seq = seq[::-1]
        k = 0
        while k < len(seq) and seq[k] >= 240:
            k += 1
        if k == n:
            runs.append(seq[:n][::-1])
    if len(runs) < 3:
        raise SystemExit("у кадра %d мало строк с камнем ровно в %d пикселей (%d)" % (f, n, len(runs)))
    runs = np.array(runs)
    return js.PAL[runs].astype(np.float64).mean(0), len(runs), runs


def stone_profile(prof, side, a):
    """Тон камня по граням поверх цветов классики: у классики верхняя грань бордюра по яркости равна асфальту
    (Y 21-28 при асфальте 23 и тротуаре 65), и в HD полоса читается тёмной канавкой (замечание 07.10). Цвет
    пикселя классики сохраняет оттенок, яркость ставится по грани: шов a.kerb_seam, ближнее ребро a.kerb_near,
    верх a.kerb_top, дальнее ребро a.kerb_arris; боковая грань переднего - как у классики (+v освещена, +u в
    тени); у заднего за дальним ребром - узкая тень у асфальта a.kerb_edge (две позиции)."""
    out = prof.copy()
    if kind(side) == "front":
        target = {0: a.kerb_seam, 1: a.kerb_near, 2: a.kerb_top, 3: a.kerb_top, 4: a.kerb_top, 5: a.kerb_top,
                  6: a.kerb_arris}
        hue = prof[2:6].mean(0)
    else:
        e = [float(x) for x in a.kerb_edge.split(",")]
        target = {0: a.kerb_top, 1: a.kerb_top, 2: a.kerb_arris, 3: e[0], 4: e[1]}
        hue = prof[0:2].mean(0)
    # оттенок - один на камень (верхняя грань классики): у 250-252 он лиловый, и при подъёме яркости ребро
    # выходило фиолетовым
    for i, y in target.items():
        out[i] = hue * (y / max(float(hue @ LUMA), 1.0))
    return np.clip(out, 0, 255)


def profile_at(prof, faces, x):
    """Цвет профиля в позиции x (пиксели от внутренней линии, 0..n): внутри грани - линейно между центрами
    пикселей, между гранями - ступень."""
    n = len(prof)
    i = np.clip(np.floor(x).astype(np.int64), 0, n - 1)
    out = np.empty(np.shape(x) + (3,))
    for a, b in faces:
        m = (i >= a) & (i <= b)
        if a == b:
            out[m] = prof[a]
            continue
        t = np.clip(x[m] - 0.5, a, b)
        xs = np.arange(a, b + 1)
        out[m] = np.stack([np.interp(t, xs, prof[a:b + 1, c]) for c in range(3)], -1)
    return out


def kerb_owner(f, us, vs):
    """Владение подточек кадра бордюра f: (сторона-владелец: индекс в списке сторон или -1 - тротуар, позиция в
    профиле, за стороной). Сначала боковая грань переднего бордюра (расстояние до края меньше внешней части; у
    двух - ближайшая к краю), потом сторона с наибольшей долей по своей верхней грани (w - e) / (w - o)."""
    sides = list(cc.KERB_SIDES[f].items())
    E = [{"+u": 1 - us, "+v": 1 - vs, "-u": us, "-v": vs}[s] for s, _ in sides]
    owner = np.full(us.shape, -1, np.int64)
    best = np.full(us.shape, np.inf)
    for k, (s, w) in enumerate(sides):
        if kind(s) == "front":
            o = w * OUTER["front"]
            m = (E[k] >= 0) & (E[k] < o) & (E[k] < best)
            owner[m] = k
            best[m] = E[k][m]
    free = owner < 0
    bn = np.full(us.shape, -np.inf)
    for k, (s, w) in enumerate(sides):
        o = w * OUTER[kind(s)]
        nn = (w - E[k]) / (w - o)
        m = free & (E[k] >= 0) & (E[k] < w) & (nn > bn)
        owner[m] = k
        bn[m] = nn[m]
    x = np.zeros(us.shape)
    for k, (s, w) in enumerate(sides):
        m = owner == k
        x[m] = (w - E[k][m]) / w * KERB_N[s]
    beyond = np.zeros(us.shape, bool)
    for k in range(len(sides)):
        beyond |= E[k] < 0
    return sides, owner, x, beyond


def gauss(a, s):
    t = np.arange(-int(3 * s) - 1, int(3 * s) + 2)
    k = np.exp(-t * t / (2 * s * s))
    k /= k.sum()
    pad = len(t) // 2
    b = np.pad(a, ((pad, pad), (pad, pad)), mode="edge")
    b = np.apply_along_axis(lambda r: np.convolve(r, k, "valid"), 1, b)
    return np.apply_along_axis(lambda r: np.convolve(r, k, "valid"), 0, b)


def grate_layer(us, vs):
    """Решётка стока кадра 13 по пикселям классики (подточки us, vs кадра x4). Пластина - по крайним пикселям
    прутьев (11-13) с запасом 1/64; прутья вдоль u, шаг - сильнейшая гармоника яркости по v; цвет - профиль по
    фазе шага (12 ячеек средних цветов классики, периодическая интерполяция по подточке). Рамка как у классики:
    кольцо 1/32 цвета 250 снаружи по -u, -v и +u (по +v нет), тень 251-252 внутри пластины полосой 1/16 вдоль -u
    и +v. Возвращает цвет пластины и кромки,
    уже умноженные на покрытие (сумма по подточкам / 16), их покрытия и описание."""
    idx, _ = js.gm.classic("ROADS", 13)
    yy, xx = np.mgrid[0:idx.shape[0], 0:idx.shape[1]].astype(np.float64)
    U, V = sp.screen_to_uv(xx + 0.5, yy + 0.5)
    rgb = js.PAL[idx].astype(np.float64)
    g = (idx >= 11) & (idx <= 13)
    lum = rgb @ LUMA
    best = max((abs(((lum[g] - lum[g].mean()) * np.exp(2j * np.pi * V[g] / p)).sum()), p)
               for p in np.arange(0.14, 0.21, 0.0025))
    step = float(best[1])
    nb = 12
    b = np.floor((V[g] / step) % 1 * nb).astype(int) % nb
    cnt = np.bincount(b, minlength=nb).astype(float)
    prof = np.stack([np.bincount(b, rgb[g][:, c], minlength=nb) for c in range(3)], -1)
    have = cnt > 0
    prof[have] /= cnt[have, None]
    xs = np.arange(nb)
    for c in range(3):
        prof[:, c] = np.interp(xs, xs[have], prof[have, c], period=nb)
    h = 1 / 64
    u0, u1 = U[g].min() - h, U[g].max() + h
    v0, v1 = V[g].min() - h, V[g].max() + h
    near = (U > u0 - 0.1) & (U < u1 + 0.1) & (V > v0 - 0.1) & (V < v1 + 0.1)
    dark = rgb[(idx >= 251) & (idx <= 252) & near]
    light = rgb[(idx == 250) & near]
    dark_rgb, light_rgb = dark.mean(0), light.mean(0)
    r, s = 1 / 32, 1 / 16
    plate = (us >= u0) & (us < u1) & (vs >= v0) & (vs < v1)
    ring = (us >= u0 - r) & (us < u1 + r) & (vs >= v0 - r) & (vs < v1 + r) & ~plate
    # как у классики (замечание 07.10: «рамка оригинала»): снаружи кольцо 250 по -u, -v и +u, по +v кольца нет -
    # там асфальт; тёмные 251-252 лежат ВНУТРИ пластины полосой 1/16 вдоль -u и +v - тень в углублении стока
    ring = ring & ~((vs >= v1) & (us < u1))
    shadow = plate & ((us < u0 + s) | (vs >= v1 - s))
    ph = (vs / step) % 1 * nb - 0.5
    col = np.stack([np.interp(ph, xs, prof[:, c], period=nb) for c in range(3)], -1)
    plate_rgb = (col * (plate & ~shadow)[..., None] + dark_rgb * shadow[..., None]).mean(-2)
    rim_rgb = (light_rgb * ring[..., None]).mean(-2)
    info = dict(step=round(step, 4), plate_u=[round(float(u0), 4), round(float(u1), 4)],
                plate_v=[round(float(v0), 4), round(float(v1), 4)], phase_profile=np.round(prof, 1).tolist(),
                rim_dark_rgb=np.round(dark_rgb, 1).tolist(), rim_light_rgb=np.round(light_rgb, 1).tolist(),
                rim_width=r, shadow_width=s, rim_dark_px=int(len(dark)), rim_light_px=int(len(light)))
    return plate_rgb, plate.mean(-1), rim_rgb, ring.mean(-1), info


# ------------------------------------------------------------------ материал

def cells_of(tex, mean_rgb, grain_std, a, control_crop=False):
    """Клетки тротуара 4 вариантов из ответа модели (независимых: движок сам сшивает варианты)."""
    ns = argparse.Namespace(period=a.period, sigma_low=a.sigma_low, wear_center=True, edge_band=1e-6,
                            wear_std=a.wear_std * float(mean_rgb @ LUMA) / a.walk_l, wear_max=a.wear_max)
    cells, grains, wears, diag = sp.make_cells(tex, ns, mean_rgb, grain_std)
    if control_crop:
        # контроль: простые вырезы без складки - клетка не периодична, край клетки не продолжает соседа
        p = a.period
        lum = tex @ LUMA
        low = sp.blur_wrap(lum, a.sigma_low)
        m_l = float(mean_rgb @ LUMA)
        g_src, w_src = lum - low, low - low.mean()
        for j, (cx, cy) in enumerate(sp.CENTRES):
            g = g_src[cy - p // 2:cy + p // 2, cx - p // 2:cx + p // 2]
            w = w_src[cy - p // 2:cy + p // 2, cx - p // 2:cx + p // 2]
            g = g * (float(grains[j].std()) / max(float(g.std()), 1e-6))
            w = np.clip((w - w.mean()) * (float(wears[j].std()) / max(float(w.std()), 1e-6)), -a.wear_max, a.wear_max)
            grains[j], wears[j] = g, w
            cells[j] = np.clip(mean_rgb[None, None, :] * ((m_l + g + w) / m_l)[..., None], 0, 255)
    return cells, grains, wears, diag


def unit(f):
    f = f - f.mean()
    return f / max(float(f.std()), 1e-9)


def stones(rng, n, density, rmin, rmax, wrap):
    """Зёрна щебня в поле n x n (столбец - u, строка - v): эллипсы радиуса rmin..rmax пикселей текстуры (мелких
    больше), светлые и тёмные; возвращает тон зёрен и блик (освещённость купола светом LIGHT), оба в [-1, 1]."""
    tone = np.zeros((n, n))
    shade = np.zeros((n, n))
    mean_area = math.pi * ((rmin + rmax) / 2) ** 2 * 0.6
    count = int(density * n * n / mean_area)
    for _ in range(count):
        cx, cy = rng.uniform(0, n, 2)
        r = rmin * (rmax / rmin) ** (rng.random() ** 1.6)
        asp = rng.uniform(0.6, 1.0)
        th = rng.uniform(0, math.pi)
        t = (1 if rng.random() < 0.55 else -1) * rng.uniform(0.5, 1.3)
        R = int(r) + 2
        ix = np.arange(int(cx) - R, int(cx) + R + 1)
        iy = np.arange(int(cy) - R, int(cy) + R + 1)
        if not wrap:
            ix, iy = ix[(ix >= 0) & (ix < n)], iy[(iy >= 0) & (iy < n)]
            if not len(ix) or not len(iy):
                continue
        dx = (ix + 0.5 - cx)[None, :]
        dy = (iy + 0.5 - cy)[:, None]
        c, s = math.cos(th), math.sin(th)
        a1 = dx * c + dy * s
        a2 = -dx * s + dy * c
        rb = r * asp
        d2 = (a1 / r) ** 2 + (a2 / rb) ** 2
        hgt = np.clip(1 - d2, 0, 1)
        edge = np.clip((1 - d2) / 0.25, 0, 1)
        # купол h = 1 - d2: grad h = -(2 a1 / r^2 * (c, s) + 2 a2 / rb^2 * (-s, c)); блик = -grad h . LIGHT
        gu = -(2 * a1 / r ** 2 * c - 2 * a2 / rb ** 2 * s)
        gv = -(2 * a1 / r ** 2 * s + 2 * a2 / rb ** 2 * c)
        lit = -(gu * LIGHT[0] + gv * LIGHT[1]) * r / 2 * (hgt > 0)
        sl = np.ix_(iy % n, ix % n)
        tone[sl] += t * edge
        shade[sl] += lit * edge
    return tone, shade


def aggregate_cells(seed, mean_rgb, grain_std, a, wrap=True):
    """Асфальт: процедурная фактура заполнителя, 4 независимые периодические клетки a.period. Связующее - мелкий
    крап (шум, размытый на a.agg_speck пикселей текстуры), щебень - stones(); слабые пятна a.agg_low. Яркость
    нормирована к тону и разбросу классики. Возвращает (rgb[4], отклонение яркости[4], диагностика)."""
    p = a.period
    n = p if wrap else 2 * p
    m_l = float(mean_rgb @ LUMA)
    cells, grains, diag = [], [], dict(cell_pattern=[], coherence=[], grain_std=grain_std, stones=[])
    for j in range(4):
        rng = np.random.default_rng(seed * 10 + j)
        speck = unit(sp.blur_wrap(rng.normal(0, 1, (n, n)), a.agg_speck))
        tone, shade = stones(rng, n, a.agg_density, a.agg_rmin, a.agg_rmax, wrap)
        low = unit(sp.blur_wrap(rng.normal(0, 1, (n, n)), 20.0))
        f = a.agg_speck_amp * speck + a.agg_tone * tone + a.agg_shade * shade + a.agg_low * low
        f = sp.blur_wrap(f, 0.6)
        if not wrap:
            f = f[:p, :p]
        g = unit(f) * grain_std
        cells.append(np.clip(mean_rgb[None, None, :] * ((m_l + g) / m_l)[..., None], 0, 255))
        grains.append(g)
        diag["cell_pattern"].append(round(sp.cell_pattern(np.tile(g, (4, 4))), 3))
        diag["coherence"].append(round(sp.coherence(g), 3))
    return cells, grains, diag


def stone_cells(seed, a, wrap=True):
    """Камень бордюра: множитель к профилю - гранитный крап (мелкий шум плюс редкие светлые и тёмные зёрна около
    пикселя текстуры) и слабые пятна. 4 клетки a.period, среднее 1."""
    p = a.period
    n = p if wrap else 2 * p
    out = []
    for j in range(4):
        rng = np.random.default_rng(seed * 10 + 5 + j)
        fine = unit(sp.blur_wrap(rng.normal(0, 1, (n, n)), 0.7))
        fl = unit(sp.blur_wrap(rng.normal(0, 1, (n, n)), 1.1))
        fleck = np.where(fl > 1.7, fl - 1.7, 0) - np.where(fl < -1.9, -1.9 - fl, 0)
        fleck = fleck / max(float(np.abs(fleck).max()), 1e-6)    # в [-1, 1]: без чёрных точек-дыр
        mot = unit(sp.blur_wrap(rng.normal(0, 1, (n, n)), 14.0))
        f = 1 + a.stone_grain * fine + a.stone_fleck * fleck + a.stone_mottle * mot
        out.append(f[:p, :p] if not wrap else f)
    return out


def band_cover(f, us, vs):
    """Разметка кадра f по подточкам: полоса классики вдоль края. Верхний конец (у верхней вершины) на карте всегда
    свободный - срез поперёк, по ребру клетки. Боковой конец (левая вершина у -u, правая у -v) - как в классике:
    снизу горизонталь экрана по низу строки 32 базы (u + v = 1.125), сбоку край картинки 32x40 (вертикаль через
    вершину); в узле (55,12) два таких конца дают V с плоским низом, как у классики (специалист 07.10). Кадр с двумя
    полосами (12, на карте нет) - угол вертикалью."""
    m = np.zeros(us.shape, bool)
    both = len(cc.MARK_EDGES[f]) > 1
    for e in cc.MARK_EDGES[f]:
        if e == "-u":
            top = (vs - us >= 0) if both else (vs >= 0)
            m |= (us >= MARK_LO) & (us < MARK_HI) & top & (vs - us <= 1) & (us + vs <= MARK_SIDE_END)
        else:
            top = (us - vs >= 0) if both else (us >= 0)
            m |= (vs >= MARK_LO) & (vs < MARK_HI) & top & (us - vs <= 1) & (us + vs <= MARK_SIDE_END)
    return m.mean(-1)


def build(a):
    raw = Path(a.raw)
    tex = np.asarray(Image.open(raw).convert("RGB").resize((sp.SIDE, sp.SIDE), Image.LANCZOS)).astype(np.float32)
    walk_rgb, walk_std = classic_tone(0, lambda i: i > 0)
    asph_rgb, asph_std = classic_tone(9, lambda i: i >= 240)
    a.walk_l = float(walk_rgb @ LUMA)
    asph_l = float(asph_rgb @ LUMA)
    crop = a.control == "crop"
    W = cells_of(tex, walk_rgb, walk_std * a.grain, a, crop)
    A = aggregate_cells(a.seed, asph_rgb, asph_std * a.grain, a, wrap=not crop)
    if a.control == "patch":
        # контроль: под разметкой другой асфальт - другая клетка, светлее на 15 процентов и крупнее зерном
        P = aggregate_cells(a.seed + 100, asph_rgb * 1.15, asph_std * 1.6, a)
    Sx = stone_cells(a.seed, a, wrap=not crop)
    mark_rgb = js.PAL[MARK_INDEX].astype(np.float64)
    prof = {}
    for s in SIDE_FRAME:
        p0, nrows, runs = row_profile(s)
        prof[s] = stone_profile(p0, s, a)
        print("профиль %s: %d строк, индексы по средней строке %s, Y классики %s -> %s" % (
            s, nrows, [int(round(x)) for x in np.median(runs, 0)], [int(round(x)) for x in p0 @ LUMA],
            [int(round(x)) for x in prof[s] @ LUMA]))
    u, v = sp.frame_uv(1)
    us, vs = sp.frame_uv(4)
    gr_rgb, gr_cov, rim_rgb, rim_cov, grate_info = grate_layer(us, vs)

    p = a.period
    su, sv = (u % 1.0) * p, (v % 1.0) * p
    if crop:
        su, sv = np.clip(u, 0, 0.9999) * p, np.clip(v, 0, 0.9999) * p     # вырез не заворачивается
    samp = (lambda c: sp.bilinear_wrap(c, su, sv))
    if crop:
        diamond = np.zeros(u.shape, bool)
        over = np.zeros(u.shape, bool)
    else:
        diamond = (u >= 0) & (u < 1) & (v >= 0) & (v < 1)
        over = ((u >= 1) & (u < 1 + REACH) & (v < REACH)) | ((v >= 1) & (v < 1 + REACH) & (u < REACH))
    wedge = (u >= 0) & (v >= 0) & (u < WEDGE) & (v < WEDGE)
    d = OUT / a.tag / "ROADS.PCK"
    d.mkdir(parents=True, exist_ok=True)
    info = dict(tag=a.tag, control=a.control or "", source=raw.resolve().relative_to(ROOT).as_posix(),
                period=a.period, sigma_low=a.sigma_low, grain=a.grain, wear_std=a.wear_std, wear_max=a.wear_max,
                seed=a.seed, aggregate=dict(speck=a.agg_speck, speck_amp=a.agg_speck_amp, density=a.agg_density,
                                            rmin=a.agg_rmin, rmax=a.agg_rmax, tone=a.agg_tone, shade=a.agg_shade,
                                            low=a.agg_low),
                stone=dict(grain=a.stone_grain, fleck=a.stone_fleck, mottle=a.stone_mottle),
                mark_grain=a.mark_grain, wedge=WEDGE, reach=REACH,
                walk_rgb=[round(float(x), 2) for x in walk_rgb], walk_std=round(walk_std, 2),
                asphalt_rgb=[round(float(x), 2) for x in asph_rgb], asphalt_std=round(asph_std, 2),
                mark_rgb=mark_rgb.tolist(), mark_band=[MARK_LO, MARK_HI], mark_ends="top: transverse along cell edge; side: classic - horizontal u+v<=%.3f, vertical through vertex" % MARK_SIDE_END,
                edge_over="own edge material (kerb_owner: beyond kerb side - asphalt, sidewalk side - sidewalk)",
                kerb_profiles={s: np.round(prof[s], 1).tolist() for s in prof},
                walk_diag={k: (np.round(v, 3).tolist() if isinstance(v, list) else v) for k, v in W[3].items()
                           if k in ("grain_raw", "grain_std", "wear_std_out", "coherence", "cell_pattern")},
                asphalt_diag=A[2], grate=grate_info)
    # бордюр: владение и цвет профиля по подточкам, в пиксель - среднее
    over_s = ((us >= 1) & (us < 1 + REACH) & (vs < REACH)) | ((vs >= 1) & (vs < 1 + REACH) & (us < REACH))
    kerb = {}
    for f in range(1, 9):
        sides, owner, x, beyond = kerb_owner(f, us, vs)
        # зубцы силуэта за стороной бордюра вне клина соседа: внутри карты их закрывает ромб соседа, на краю карты
        # они видны - лицо камня этой стороны, как у зубцов классики; асфальт за стороной только в over, где он
        # заполняет клин асфальта соседа (R-248)
        tooth = beyond & ~over_s
        for k, (s, w) in enumerate(sides):
            E = {"+u": 1 - us, "+v": 1 - vs, "-u": us, "-v": vs}[s]
            m = tooth & (E < 0)
            owner[m] = k
            x[m] = KERB_N[s]
        beyond = beyond & ~tooth
        col = np.zeros(us.shape + (3,))
        stone_m = np.zeros(us.shape, bool)
        for k, (s, w) in enumerate(sides):
            m = (owner == k) & ~beyond
            col[m] = profile_at(prof[s], FACES[kind(s)], x[m])
            stone_m |= m
        wedge_col = np.zeros(us.shape + (3,))
        if a.control == "wedge":
            # контроль: за стороной - внешний цвет камня этой стороны
            E = {"+u": 1 - us, "+v": 1 - vs, "-u": us, "-v": vs}
            for s, w in sides:
                m = (E[s] < 0) & ~(wedge_col.any(-1))
                wedge_col[m] = prof[s][-1]
        kerb[f] = (col.mean(-2), stone_m.mean(-1), beyond.mean(-1), wedge_col.mean(-2))
    mark_cover = {f: band_cover(f, us, vs) for f in cc.MARK_EDGES}
    for j, suf in enumerate(SUFFIX):
        walk = samp(W[0][j])
        stone = samp(Sx[j])
        asph = samp(A[0][j])
        ga = samp(A[1][j])
        under = samp(P[0][j]) if a.control == "patch" else asph
        for f in FRAMES:
            alpha = np.where((js.classic_idx("ROADS", f) > 0) | diamond | over, 255.0, 0.0)
            # выступ за ромбом (over и зубцы силуэта) - материал края своей клетки: внутри карты его закрывает сосед
            # или он попадает в клин асфальта только за стороной бордюра (там kerb_owner даёт асфальт), а на краю
            # карты он виден и обязан быть в тон краю (специалист 07.10); у тротуара 0 - тротуар
            if f == 0:
                rgb = walk
            elif f <= 8:
                kc, kcov, bcov, wcol = kerb[f]
                wcov = np.clip(1 - kcov - bcov, 0, 1)
                if a.control == "wedge":
                    rgb = kc * stone[..., None] + walk * wcov[..., None] + wcol
                else:
                    rgb = kc * stone[..., None] + walk * wcov[..., None] + asph * bcov[..., None]
            elif f == 9:
                rgb = asph
            elif f in mark_cover:
                c = mark_cover[f]
                paint = mark_rgb[None, None, :] * (1 + a.mark_grain * ga / asph_l)[..., None]
                rgb = under * (1 - c[..., None]) + paint * c[..., None]
                rgb = np.where(wedge[..., None], paint, rgb)
                alpha = np.where(wedge, 255.0 * c, alpha)
            else:
                metal = 1 + 0.2 * ga / asph_l
                rgb = under * (1 - gr_cov - rim_cov)[..., None] + gr_rgb * metal[..., None] + rim_rgb
            if f in (9, 13):
                alpha = np.where(wedge, 0.0, alpha)
            if crop:
                alpha = np.where(js.classic_idx("ROADS", f) > 0, 255.0, 0.0)
            fr = np.dstack([np.clip(rgb, 0, 255), alpha]).round().astype(np.uint8)
            Image.fromarray(fr, "RGBA").save(d / ("%d%s.png" % (f, suf)))
    if a.control == "old":
        # контроль: старые соседи - кадры 2, 4, 9, 12 не заменяются, в моде остаются картинки установки (одна на
        # кадр, без вариантов), как в отклонённом кадре 07.10
        for f in OLD_FRAMES:
            for pth in list(d.glob("%d.png" % f)) + list(d.glob("%d.v*.png" % f)):
                pth.unlink()
    (OUT / a.tag / "build.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding=ENC)
    print("кадры: %s (%d файлов)" % (d, len(list(d.glob("*.png")))))
    print("тротуар %s зерно %.2f; асфальт %s зерно %.2f; разметка %s, полоса %.4f..%.4f" % (
        info["walk_rgb"], walk_std, info["asphalt_rgb"], asph_std, mark_rgb.tolist(), MARK_LO, MARK_HI))
    print("узор клетки тротуара %s, асфальта %s (шум без узора ~0.125)" % (
        info["walk_diag"]["cell_pattern"], A[2]["cell_pattern"]))
    print("решётка: шаг %.4f, пластина u %s v %s, кромка %s / %s" % (
        grate_info["step"], grate_info["plate_u"], grate_info["plate_v"], grate_info["rim_dark_rgb"],
        grate_info["rim_light_rgb"]))


# ------------------------------------------------------------------ просмотр без игры

def load(tag):
    d = OUT / tag / "ROADS.PCK"
    return {f: [np.asarray(Image.open(d / ("%d%s.png" % (f, s))).convert("RGBA")) for s in SUFFIX] for f in FRAMES}


WINDOW = (47, 7, 14)        # x 47..60, y 7..20: тротуар, бордюры x 51/58, y 11/18, асфальт 52..57, разметка


def preview(a):
    fr = load(a.tag)
    bt = js.mt.Battle(js.CORNER)
    seed = gf.battle_seed(bt.X, bt.Y, bt.Z, bt.blocks)
    cx, cy, n = WINDOW
    cells = js.Blocks.battle_floor(js.CORNER, cx, cy, n)

    def pick(s, f, x, y):
        if s == "ROADS" and f in fr:
            return gf.frame_for(fr[f], cx + x, cy + y, 0, seed, K)
        return js.rgba_hd(s, str(f))
    img, *_ = js.assemble(cells, pick)
    Image.fromarray(img).save(OUT / a.tag / "preview.png")
    print("просмотр:", OUT / a.tag / "preview.png", img.shape)


# ------------------------------------------------------------------ дерево модов

def mods(tag):
    """_mods/<метка>: соединения на моды установки, hd - своя папка из соединений, кроме hd/TERRAIN/ROADS.PCK -
    копии пака установки, где кадры 0-13 и их варианты заменены сборкой."""
    root = OUT / "_mods" / tag
    frames = OUT / tag / "ROADS.PCK"
    dst = root / "hd" / "hd" / "TERRAIN" / "ROADS.PCK"
    if not root.exists():
        root.mkdir(parents=True)
        for m in sp.GAME_MODS.iterdir():
            if m.name != "hd":
                sp.junction(root / m.name, m)
        src_hd = sp.GAME_MODS / "hd"
        for sub_src, sub_dst, keep in ((src_hd, root / "hd", "hd"), (src_hd / "hd", root / "hd" / "hd", "TERRAIN"),
                                       (src_hd / "hd" / "TERRAIN", root / "hd" / "hd" / "TERRAIN", "ROADS.PCK")):
            sub_dst.mkdir(parents=True, exist_ok=True)
            for e in sub_src.iterdir():
                if e.name == keep:
                    continue
                if e.is_dir():
                    sp.junction(sub_dst / e.name, e)
                else:
                    shutil.copy2(e, sub_dst / e.name)
        shutil.copytree(src_hd / "hd" / "TERRAIN" / "ROADS.PCK", dst)
    for f in FRAMES:                       # прежние варианты кадров участка убрать: число вариантов - наше
        for old in list(dst.glob("%d.v*.png" % f)):
            old.unlink()
    n = 0
    for pth in frames.glob("*.png"):
        shutil.copy2(pth, dst / pth.name)
        n += 1
    print("моды: %s (кадров заменено %d)" % (root, n))
    return root


# ------------------------------------------------------------------ лист по дампам игры

# крупные фрагменты: узел сетки мира (gx, gy) в центре выреза, подпись
CLOSE = [((55, 12), "вершина V: штрих по -v клетки 54,12 (кадр 11) встречает штрих по -u клетки 55,11 (кадр 10)"),
         ((55, 8), "конец штриха кадра 10 (55,7) у вершины следующей клетки асфальта"),
         ((56, 14), "простой асфальт: узел четырёх клеток кадра 9 (55..56, 13..14) - сетка клеток"),
         ((52, 12), "внутренний угол бордюра 7 (51,11) и асфальт"),
         ((52, 9.5), "передний бордюр 1 (51,9) | асфальт 9 (52,9)"),
         ((49, 12), "передний бордюр 2 (49,11) | асфальт"),
         ((50, 18), "задний бордюр 3 (50,18) | асфальт"),
         ((52.5, 7.5), "решётка стока кадра 13 (52,7)"),
         ((50, 12), "вершина асфальта (50,12) под передним бордюром 2: клин у верхней вершины, край бордюра"),
         ((58, 9), "задний бордюр 4 (58,9) | асфальт 9 (57,9), вершина бордюра")]


def dump_of(tag):
    p = OUT / "_dumps" / tag / "dump"
    js_d = json.loads(Path(str(p) + ".json").read_text(encoding=ENC))
    k = int(js_d["k"])
    cam = (int(js_d["cameraOffsetX"]) // k, int(js_d["cameraOffsetY"]) // k, int(js_d["cameraOffsetZ"]))
    return Image.open(str(p) + "_map.png").convert("RGB"), k, cam, js_d


def grid_xy(gx, gy, k, cam):
    """Пиксель дампа узла сетки мира (этаж 0): обратное к sx = X/k - camX - 16, gu - gv = sx/16, gu + gv = sy/8."""
    return (16 * (gx - gy) + cam[0] + 16) * k, (8 * (gx + gy) + cam[1] + 24) * k


def sheet(a):
    tags = [t for t in a.tags.split(",") if (OUT / "_dumps" / t / "dump_map.png").exists()]
    D = {t: dump_of(t) for t in tags}
    cams = {t: D[t][2] for t in tags}
    k = D[tags[0]][1]
    sh = sp.Sheet(2400, "Перекрёсток ROADS целиком (кадры 0-13), метка %s - дампы игры Ctrl+F8, k=%d, одна камера и "
                  "свет" % (a.main, k), False)
    sh.para("Камера дампов (база): " + ";  ".join("%s %s" % (t, c) for t, c in cams.items()) +
            ("" if len(set(cams.values())) == 1 else "   !! КАМЕРЫ РАЗНЫЕ - сравнение не годится"),
            fill=(180, 220, 255) if len(set(cams.values())) == 1 else (255, 120, 120))
    cmp3 = [t for t in ("classic", "hd_now", a.main) if t in D]
    names = dict(classic="классика (режим 0)", hd_now="HD сейчас (пак установки)", classic_na="классика без дождя",
                 ctl_crop="контроль crop", ctl_patch="контроль patch", ctl_old="контроль old",
                 ctl_wedge="контроль wedge")
    names[a.main] = "новое (%s)" % a.main
    names[a.main + "_na"] = "новое без дождя"
    cx, cy, n = WINDOW
    corners = [grid_xy(gx, gy, k, cams[tags[0]]) for gx, gy in ((cx, cy), (cx + n, cy), (cx, cy + n), (cx + n, cy + n))]
    iw, ih = D[tags[0]][0].size
    box = (max(0, min(c[0] for c in corners)), max(0, min(c[1] for c in corners)), min(iw, max(c[0] for c in corners)),
           min(ih, max(c[1] for c in corners)))
    sh.para("Цветные точки по всей карте во всех дампах - пар заморозки дампа (hdTestFreeze, Map.cpp), не пол; "
            "crossing_check их исключает маской.", fill=(200, 200, 200))
    sc = (2400 - 60) / 3 / (box[2] - box[0])
    sh.head("1. Общий вид участка 14 x 14 клеток (x %d..%d, y %d..%d), уменьшено в %.1f раза" % (
        cx, cx + n - 1, cy, cy + n - 1, 1 / sc))
    ov = lambda t: D[t][0].crop(box).resize((int((box[2] - box[0]) * sc), int((box[3] - box[1]) * sc)), Image.LANCZOS)
    sh.row([(names[t], ov(t)) for t in cmp3])
    sh.head("2. Крупно, пиксели дампа x2 (один пиксель базы = %d x %d)" % (2 * k, 2 * k))
    hw, hh = 128, 64
    for (gx, gy), lbl in CLOSE:
        X, Y = grid_xy(gx, gy, k, cams[tags[0]])
        b = (int(X - hw), int(Y - hh), int(X + hw), int(Y + hh))
        sh.para(lbl)
        sh.row([(names[t], D[t][0].crop(b).resize((4 * hw, 4 * hh), Image.NEAREST)) for t in cmp3])
    # контроль - на месте своего дефекта: crop - лесенка края штриха у вершины V, patch - асфальт под штрихом,
    # old - стык тротуара со старым бордюром без вариантов, wedge - ступенька края бордюра в клине асфальта
    ctl = [(t, c) for t, c in (("ctl_crop", CLOSE[0]), ("ctl_patch", CLOSE[1]), ("ctl_old", CLOSE[3]),
                               ("ctl_wedge", CLOSE[8])) if t in D]
    if ctl:
        sh.head("3. Контроли (каждый обязан провалить crossing_check на своей мере): новое | контроль, x2 "
                "(wedge - x6: ступенька в 2 пикселя базы)")
        for t, ((gx, gy), lbl) in ctl:
            z = 6 if t == "ctl_wedge" else 2
            w2, h2 = 2 * hw // z, 2 * hh // z
            X, Y = grid_xy(gx, gy, k, cams[tags[0]])
            b = (int(X - w2), int(Y - h2), int(X + w2), int(Y + h2))
            sh.para("%s: %s, x%d" % (names[t], lbl, z))
            sh.row([(names[u], D[u][0].crop(b).resize((2 * w2 * z, 2 * h2 * z), Image.NEAREST)) for u in (a.main, t)])
    na = [t for t in ("classic", "classic_na", a.main, a.main + "_na") if t in D]
    if len(na) > 2:
        sh.head("4. Палитра: бой идёт под кислотным дождём (enviroEffectsType STR_ENVIRO_ACID_RAIN) - классика рисуется "
                "палитрой dgoodpal_grinder (зелёная), HD-слой берёт RGB пака. Копия сейва без дождя - классика "
                "в палитре боя delicious_regular")
        sc2 = (2400 - 70) / 4 / (box[2] - box[0])
        sh.row([(names[t], D[t][0].crop(box).resize((int((box[2] - box[0]) * sc2), int((box[3] - box[1]) * sc2)),
                                                     Image.LANCZOS)) for t in na], gap=12)
    chk = OUT / "_dumps" / "_check"
    rows = [t for t in tags if (chk / ("check_%s.json" % t)).exists()]
    if rows:
        sh.head("5. Меры crossing_check по дампу движка - диагностика; приёмка - глазами по листу. "
                "diag - мера не отделяет брак от нормы (проваливает и классика), в итог не идёт")
        for t in rows:
            r = json.loads((chk / ("check_%s.json" % t)).read_text(encoding=ENC))
            v = r["verdict"]
            ref = t.startswith("classic")
            bad = cc.failed(v, ref)
            nf = len(bad)
            sh.para("%s: %s, провалено мер %d%s" % (
                names.get(t, t), "FAIL" if nf else "PASS", nf,
                ": " + ", ".join(bad) if nf else ("  (эталон: требования HD - край штриха и бордюра - "
                "классика по природе не проходит, не считаются)" if ref else "")),
                fill=(255, 120, 120) if nf else (140, 255, 140))
            sh.para("     " + ";  ".join("%s %s %s" % (kk, x[0], "" if x[1] == "PASS" else x[1])
                                         for kk, x in v.items()), fill=(200, 200, 200), step=18)
    sh.save(OUT / ("sheet_%s.png" % a.main))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--raw", default=str(RAW))
    b.add_argument("--tag", default="new")
    b.add_argument("--control", default="", choices=("", "crop", "patch", "old", "wedge"))
    b.add_argument("--period", type=int, default=160)
    b.add_argument("--sigma-low", type=float, default=12.0)
    b.add_argument("--grain", type=float, default=1.0)
    b.add_argument("--wear-std", type=float, default=1.0, help="износ тротуара; у асфальта - пропорционально тону")
    b.add_argument("--wear-max", type=float, default=3.0)
    b.add_argument("--seed", type=int, default=7101, help="зерно процедурных фактур асфальта и камня")
    b.add_argument("--agg-speck", type=float, default=1.2, help="крап связующего: размытие, пикселей текстуры")
    b.add_argument("--agg-speck-amp", type=float, default=0.7)
    b.add_argument("--agg-density", type=float, default=0.35, help="доля площади под щебнем")
    b.add_argument("--agg-rmin", type=float, default=2.0)
    b.add_argument("--agg-rmax", type=float, default=7.0)
    b.add_argument("--agg-tone", type=float, default=1.0, help="тон зёрен (светлые и тёмные)")
    b.add_argument("--agg-shade", type=float, default=0.6, help="блик зёрен от света сверху-слева")
    b.add_argument("--agg-low", type=float, default=0.15, help="слабые пятна асфальта")
    b.add_argument("--stone-grain", type=float, default=0.05, help="камень: мелкий крап, доля тона")
    b.add_argument("--stone-fleck", type=float, default=0.12, help="камень: редкие зёрна, наибольшая доля тона")
    b.add_argument("--kerb-top", type=float, default=46.0, help="яркость Y верхней грани камня (классика 21-28)")
    b.add_argument("--kerb-arris", type=float, default=58.0, help="дальнее ребро верхней грани, блик")
    b.add_argument("--kerb-near", type=float, default=52.0, help="ближнее к тротуару ребро переднего")
    b.add_argument("--kerb-seam", type=float, default=30.0, help="шов тротуара и камня")
    b.add_argument("--kerb-edge", default="30,16", help="задний: тень у асфальта за дальним ребром, две позиции")
    b.add_argument("--stone-mottle", type=float, default=0.035, help="камень: слабые пятна")
    b.add_argument("--mark-grain", type=float, default=0.3, help="зерно асфальта на краске, доля")
    pv = sub.add_parser("preview")
    pv.add_argument("--tag", default="new")
    mo = sub.add_parser("mods")
    mo.add_argument("--tag", default="new")
    st = sub.add_parser("sheet", help="лист по дампам игры _dumps/<метка>/dump: классика | HD сейчас | новое")
    st.add_argument("--main", default="new")
    st.add_argument("--tags", default="classic,hd_now,new,ctl_crop,ctl_patch,ctl_old,ctl_wedge,classic_na,new_na")
    a = ap.parse_args()
    if a.cmd == "build":
        build(a)
    elif a.cmd == "preview":
        preview(a)
    elif a.cmd == "sheet":
        sheet(a)
    else:
        mods(a.tag)


if __name__ == "__main__":
    main()
