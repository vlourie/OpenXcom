"""Вода семейства SEAURBAN: процедурная сборка HD-кадров из классики, без генерации (07.10).

Наборы и что с ними делается:
  SEAURBAN (144 кадра, 18 записей по 8 фаз) - море. Одна текстура на 3x3 клетки: запись по (x%3, y%3) = ARR
    (так стоят CARGO00, LINERT00), записи 9..17 - та же раскладка в тёмной гамме. Для каждой фазы и гаммы
    собирается периодическое поле классики (порядок рисования y, потом x), поле мягко увеличивается x4
    целиком, и кадр каждой записи берёт цвет из поля там, где стоит. Соседние клетки дают один цвет
    в любой точке - стыков и ромбов нет, рябь идёт через границы клеток, фазы замыкаются как в классике.
    Силуэт: на силуэте классики непрозрачен, гладкая кромка наружу; низ (строки 32..39 базы, юбка 143) -
    лесенка классики x4 как есть (геометрия берега и края карты).
  SEABITS (3 кадра) - статичная вода, плоский ромб. Поле: кадр в середине, вокруг одна и та же смесь трёх
    кадров, мягкое x4; край кадра из общего окружения, поэтому разные кадры стыкуются по тону.
  CARGO2_IND 31..46 (записи 7 и 8) - пена у борта. Premultiplied: бикубика плюс гаусс над цветом,
    умноженным на альфу, и над альфой, потом деление; альфа поднята (gain), чтобы капля в один пиксель
    классики осталась каплей. Корпус и остальные кадры набора не трогаются.

  POLAR 63..122 (записи 63..80, 4 фазы) - полярная вода и берега льда. Раскладка воды на карте случайная
    (записи 68, 78, 79, 80 - одна вода со сдвигом фазы), поэтому общей текстуры на несколько клеток нет:
    вода каждого кадра (индексы 128..143) - кадр сам с собой на изорешётке, мягкое x4; мелкий дизеринг
    классики стыкуется с любым соседом без видимого шва. Общая кромка (полоса у края ромба из одного поля
    на все кадры) пробовалась и отвергнута: на поле проступает решётка тонких линий. Берег: белый снег
    (индексы 1..3) - фактура снега пака (кадр 32, сам с собой), чтобы берег продолжал соседний снег;
    лиловый склон и льдины - premultiplied мягкое x4 классики; слои смешаны по плотности, за силуэтом цвет
    крайнего слоя. Альфа как у SEABITS. Ступени берега - геометрия классики, не трогаются.
  FORESTSWAMP, _SNOW, _WASTE, FORESTSWAMPSTYX 51..110 - болота, раскладка POLAR (записи 63..80, открытая вода
    56, 71, 86, 101). Вода - как у POLAR, своя рампа (SWAMP_RAMP). Суша берега - фактура пака пола-соседа
    (SWAMP_LAND, кадр 0 сам с собой), умноженная на отношение яркости суши классики к яркости соседа: трава
    и снег берега продолжают траву и снег соседних клеток. Суша темнее соседа больше чем вдвое (тень сугроба
    на воде) остаётся цветом классики.
  IDT_FARM_WATER (28 кадров с водой 112..127) - рисовые чеки, статичная вода. Вода - как у POLAR (кадр сам
    с собой, мягкое x4, средний цвет кадра 64); вал и земля берега - premultiplied мягкое x4 классики,
    слои по плотности. Стебли риса кадра 83 (рампы 48..79) - из прежнего пака
    (art/water/src/IDT_FARM_WATER_83_pack.png) поверх воды: в классике это точки, в паке нарисованы.

    py -3.13 tools/hdart/water_build.py --out <папка>/TERRAIN [--sets SEAURBAN,SEABITS,CARGO2_IND,POLAR,FORESTSWAMP,...]
Проверка - игровой кадр (море у борта пиратского круиза, полярные пруды STR_LOC_ACADEMY_TOWN_COLD,
болото STR_LOC_MONSTER_HUNT_PRIMAL_WEREWOLF, рисовая ферма RICE_FARM), а не лист кадров.
POLAR берёт снег из пака установки - пересобирать после замены снега POLAR 32; болота - после замены
кадра 0 FOREST, FOREST_SNOW, FOREST_WASTE, FORESTJUNGLESTYX.
"""
import argparse
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
import pck_census as pc          # noqa: E402
import xcom_sprites as xs        # noqa: E402
import link_frames as lf         # noqa: E402

INST = ROOT / "Пиратки" / "Dioxine_XPiratez"
PAL = INST / "user" / "mods" / "Piratez" / "Resources" / "Pals" / "delicious_regular.pal"
K = 4
ARR = {(0, 0): 0, (1, 0): 2, (2, 0): 5, (0, 1): 1, (1, 1): 4, (2, 1): 7, (0, 2): 3, (1, 2): 6, (2, 2): 8}
SKIRT = 143
FOAM = range(31, 47)
POLAR_WATER = np.zeros(256, bool)
POLAR_WATER[128:144] = True             # бирюзовая рампа воды POLAR
POLAR_SNOW_IDX = [1, 2, 3]              # белый снег, как у кадра снега 32
POLAR_SNOW = INST / "user" / "mods" / "hd" / "hd" / "TERRAIN" / "POLAR.PCK" / "32.png"
# семья FORESTSWAMP: та же раскладка (записи 63..80, кадры 51..110, открытая вода - запись 68), своя рампа воды
SWAMP_RAMP = {"FORESTSWAMP": 128, "FORESTSWAMP_SNOW": 128, "FORESTSWAMP_WASTE": 48, "FORESTSWAMPSTYX": 0}
# пол-сосед берегов на картах (набор террейна, кадр 0 - чаще всего у воды): фактура суши берега берётся у его пака
SWAMP_LAND = {"FORESTSWAMP": "FOREST", "FORESTSWAMP_SNOW": "FOREST_SNOW", "FORESTSWAMP_WASTE": "FOREST_WASTE",
              "FORESTSWAMPSTYX": "FORESTJUNGLESTYX"}
# откуда брать кадр 0 пола-соседа: по умолчанию пак установки; --land-dir - новые полы до установки
LAND_DIR = INST / "user" / "mods" / "hd" / "hd" / "TERRAIN"


def palette():
    return np.array(xs.load_palette_file(str(PAL)), dtype=np.uint8)[:256]


def read_set(s):
    files = pc.Files([str(INST / "user" / "mods" / "Piratez"), str(INST / "standard" / "xcom1"), str(INST / "UFO")])
    frames, _ = pc.read_set(files, os.path.join("TERRAIN", s + ".PCK"))
    return [np.asarray(f) for f in frames]


def records(s):
    mcd = lf.find_mcd([str(INST / "user" / "mods" / "Piratez" / "TERRAIN"), str(INST / "UFO" / "TERRAIN")], s)
    data = open(mcd, "rb").read()
    return [list(data[i:i + 8]) for i in range(0, len(data) - 61, 62)], [data[i + 49] for i in range(0, len(data) - 61, 62)]


def up_smooth(img, blur):
    """Мягкое увеличение x4: бикубика плюс гаусс (в пикселях HD)."""
    im = Image.fromarray(img).resize((img.shape[1] * K, img.shape[0] * K), Image.BICUBIC)
    if blur > 0:
        im = im.filter(ImageFilter.GaussianBlur(blur))
    return np.asarray(im).astype(np.float32)


def soft_mask(m, blur=1.2):
    """Гладкая маска x4 с краем в полтора пикселя HD."""
    f = up_smooth((m * 255).astype(np.uint8), blur) / 255.0
    return np.clip((f - 0.5) * 2.2 + 0.5, 0, 1)


def blk(m):
    return np.kron(m.astype(np.float32), np.ones((K, K), np.float32))


def iso_field(span, pick):
    """Поле классики: pick(x, y) -> кадр; -> индексы и функция начала клетки на поле."""
    n = len(span)
    ox, oy = n * 16 + 8, 8
    idx = np.zeros((2 * n * 8 + 64, 2 * n * 16 + 64), np.uint8)
    org = lambda x, y: (ox + (x - y) * 16, oy + (x - span[0] + y - span[0]) * 8)   # noqa: E731
    for y in span:
        for x in span:
            a = pick(x, y)
            px, py = org(x, y)
            m = a != 0
            idx[py:py + 40, px:px + 32][m] = a[m]
    return idx, org


def save(o, out, s, f):
    p = Path(out) / (s + ".PCK") / ("%d.png" % f)
    p.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(o, "RGBA").save(p)


def build_seaurban(pal, out, blur=1.6):
    s = "SEAURBAN"
    frames = read_set(s)
    recs, plev = records(s)
    assert len(frames) == 144 and all(recs[r] == list(range(r * 8, r * 8 + 8)) for r in range(18)), "не та раскладка"
    assert all(p == 0 for p in plev), plev
    skirt = pal[SKIRT].astype(np.float32)
    span = range(-6, 9)
    n = 0
    for group in (0, 9):
        for phase in range(8):
            idx, org = iso_field(span, lambda x, y: frames[recs[group + ARR[(x % 3, y % 3)]][phase]])
            cx, cy = org(0, 0)
            core = idx[cy + 8:cy + 56, cx - 32:cx + 64]
            assert not ((core == SKIRT) | (core == 0)).any(), "раскладка 3x3 не закрывает середину поля"
            hd = up_smooth(pal[idx], blur)
            for (dx, dy), r in ARR.items():
                f = recs[group + r][phase]
                a = frames[f]
                px, py = org(dx, dy)
                col = hd[py * K:(py + 40) * K, px * K:(px + 32) * K]
                surf = (a != 0) & (a != SKIRT)
                # на силуэте классики непрозрачен целиком (иначе сквозь кромку видна юбка заднего соседа)
                sm = np.minimum(np.maximum(soft_mask(surf), blk(surf)), 1)
                low = blk(a != 0)
                allm = np.maximum(soft_mask(a != 0), low)
                allm[32 * K:] = low[32 * K:]
                sm = np.minimum(sm, allm)
                # поверхность - цвет поля, к юбке переход только там, где поверхность встречает юбку
                t = np.where(allm > 1e-3, sm / np.maximum(allm, 1e-3), 0)
                c = col * t[..., None] + skirt * (1 - t[..., None])
                save(np.dstack([np.clip(c, 0, 255), allm * 255]).round().astype(np.uint8), out, s, f)
                n += 1
    return n


def build_seabits(pal, out, blur=1.6):
    s = "SEABITS"
    frames = read_set(s)
    span = range(-4, 5)
    rng = np.random.default_rng(5)
    mix = {(x, y): int(rng.integers(len(frames))) for x in span for y in span}
    for f in range(len(frames)):
        idx, org = iso_field(span, lambda x, y: frames[f if (x, y) == (0, 0) else mix[(x, y)]])
        px, py = org(0, 0)
        col = up_smooth(pal[idx], blur)[py * K:(py + 40) * K, px * K:(px + 32) * K]
        a = frames[f]
        alpha = np.maximum(soft_mask(a != 0), blk(a != 0))
        save(np.dstack([np.clip(col, 0, 255), alpha * 255]).round().astype(np.uint8), out, s, f)
    return len(frames)


def gauss(a, sg):
    r = int(np.ceil(3 * sg))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sg) ** 2)
    k /= k.sum()
    p = np.pad(a, r, mode="edge")
    p = np.apply_along_axis(lambda v: np.convolve(v, k, "valid"), 0, p)
    return np.apply_along_axis(lambda v: np.convolve(v, k, "valid"), 1, p)


def up_float(img, blur):
    h, w = img.shape[:2]
    out = []
    for c in range(img.shape[2]):
        im = np.asarray(Image.fromarray(img[..., c].astype(np.float32), "F").resize((w * K, h * K), Image.BICUBIC))
        out.append(gauss(im, blur) if blur > 0 else im)
    return np.dstack(out)


def build_foam(pal, out, blur=1.0, gain=1.6):
    s = "CARGO2_IND"
    frames = read_set(s)
    recs, _ = records(s)
    assert recs[7] == list(range(31, 39)) and recs[8] == list(range(39, 47)), (recs[7], recs[8])
    for f in FOAM:
        a = frames[f]
        al = (a != 0).astype(np.float32)
        pre = np.dstack([pal[a].astype(np.float32) * al[..., None], al[..., None]])
        u = up_float(np.pad(pre, ((2, 2), (2, 2), (0, 0))), blur)[2 * K:-2 * K, 2 * K:-2 * K]
        A = np.clip(u[..., 3], 0, 1)
        col = u[..., :3] / np.maximum(A[..., None], 1e-3)
        alpha = np.clip(A * gain, 0, 1)
        alpha[alpha < 0.04] = 0
        save(np.dstack([np.clip(col, 0, 255), alpha * 255]).round().astype(np.uint8), out, s, f)
    return len(FOAM)


def polar_water(frame, pal, mean, blur, water=POLAR_WATER):
    """Вода кадра берега: кадр сам с собой на изорешётке, не-вода - средний цвет воды; мягкое x4 клетки кадра."""
    col = pal[frame].astype(np.float32)
    col[~(water[frame] & (frame != 0))] = mean
    span = range(-2, 3)
    n = len(span)
    ox, oy = n * 16 + 8, 8
    img = np.zeros((2 * n * 8 + 64, 2 * n * 16 + 64, 3), np.float32)
    have = np.zeros(img.shape[:2], bool)
    org = lambda x, y: (ox + (x - y) * 16, oy + (x - span[0] + y - span[0]) * 8)   # noqa: E731
    m = frame != 0
    for y in span:
        for x in span:
            px, py = org(x, y)
            img[py:py + 40, px:px + 32][m] = col[m]
            have[py:py + 40, px:px + 32] |= m
    img[~have] = mean
    hd = up_smooth(np.clip(img, 0, 255).round().astype(np.uint8), blur)
    px, py = org(0, 0)
    return hd[py * K:(py + 40) * K, px * K:(px + 32) * K]


def polar_snow(png=POLAR_SNOW):
    """Снег пака установки (POLAR 32) на изорешётке сам с собой, клетка в середине: за ромбом - то, что
    покажет соседний снег."""
    s = np.asarray(Image.open(png).convert("RGBA")).astype(np.float32)
    h, w = 40 * K, 32 * K
    big = np.zeros((h * 3, w * 3, 4), np.float32)
    for y in range(-2, 3):
        for x in range(-2, 3):
            px, py = w + (x - y) * 16 * K, h + (x + y) * 8 * K
            x0, y0, x1, y1 = max(px, 0), max(py, 0), min(px + w, 3 * w), min(py + h, 3 * h)
            if x1 > x0 and y1 > y0:
                src = s[y0 - py:y1 - py, x0 - px:x1 - px]
                big[y0:y1, x0:x1] = np.where(src[..., 3:] > 127, src, big[y0:y1, x0:x1])
    return big[h:2 * h, w:2 * w, :3]


def build_polar(pal, out, blur=1.6):
    s = "POLAR"
    recs, _ = records(s)
    assert recs[68] == [68, 83, 98, 113] * 2 and recs[78] == [113, 68, 83, 98] * 2, (recs[68], recs[78])
    return build_shore(pal, out, s, POLAR_WATER, (68, 83, 98, 113), range(63, 123), POLAR_SNOW_IDX, POLAR_SNOW, blur)


def build_swamp(s):
    def run(pal, out, blur=1.6):
        recs, _ = records(s)
        assert recs[68] == [56, 71, 86, 101] * 2 and recs[78] == [101, 56, 71, 86] * 2, (recs[68], recs[78])
        water = np.zeros(256, bool)
        water[SWAMP_RAMP[s]:SWAMP_RAMP[s] + 16] = True
        nb = SWAMP_LAND[s]
        a0 = read_set(nb)[0]
        land = (nb, LAND_DIR / (nb + ".PCK") / "0.png", luma(pal[a0[a0 != 0]]).mean())
        return build_shore(pal, out, s, water, (56, 71, 86, 101), range(51, 111), blur=blur, land=land)
    return run


def luma(c):
    return c[..., 0] * 0.299 + c[..., 1] * 0.587 + c[..., 2] * 0.114


def build_shore(pal, out, s, water, open_frames, anim_range, snow_idx=(), snow_png=None, blur=1.6, land=None):
    """Анимированная вода с берегами (POLAR, семья FORESTSWAMP): вода кадра - сам с собой на изорешётке;
    суша - premultiplied мягкое x4 своих цветов; snow_idx - пиксели, которые берут фактуру пака snow_png.
    land = (набор, png пака, яркость классики) пола-соседа: суша - его фактура на изорешётке, умноженная на
    отношение яркости своей суши классики к яркости пола-соседа (скаляр, тон не уводит - R-030)."""
    frames = read_set(s)
    recs, _ = records(s)
    anim = sorted({f for r in recs if len(set(r)) > 1 for f in r})
    assert anim == list(anim_range), anim
    mean = np.concatenate([pal[frames[f][water[frames[f]] & (frames[f] != 0)]] for f in open_frames])
    mean = mean.astype(np.float32).mean(0)
    snow = polar_snow(snow_png) if snow_png is not None else 0.0
    ltex = polar_snow(land[1]) if land is not None else None

    def dens(m, col=None):
        ch = [m.astype(np.float32)[..., None]] if col is None else [col * m[..., None], m.astype(np.float32)[..., None]]
        return up_float(np.pad(np.dstack(ch), ((2, 2), (2, 2), (0, 0))), 1.2)[2 * K:-2 * K, 2 * K:-2 * K]

    for f in anim:
        a = frames[f]
        nz = a != 0
        wm = nz & water[a]
        sm = nz & np.isin(a, list(snow_idx))
        im = nz & ~wm & ~sm
        wat = polar_water(a, pal, mean, blur, water)
        ui = dens(im, pal[a].astype(np.float32))
        d_i = np.clip(ui[..., 3], 0, None)
        icol = ui[..., :3] / np.maximum(d_i[..., None], 1e-3)
        if land is not None:
            # суша темнее пола-соседа больше чем вдвое - это рисунок берега (тень сугроба на воде), а не трава
            # или снег: остаётся цветом классики, переход между 0.45 и 0.7 отношения
            r = luma(icol) / land[2]
            t = np.clip((r - 0.45) / 0.25, 0, 1)[..., None]
            icol = ltex * np.clip(r, 0.5, 2.0)[..., None] * t + icol * (1 - t)
        d_s = np.clip(dens(sm)[..., 0], 0, None)
        d_w = np.clip(dens(wm)[..., 0], 0, None)
        tot = np.maximum(d_i + d_s + d_w, 1e-4)
        # доли слоёв по плотности: за силуэтом цвет того слоя, что у края (иначе кромка ромба цвета воды)
        lw = np.clip(((d_i + d_s) / tot - 0.5) * 2.2 + 0.5, 0, 1)[..., None]
        ls = (d_s / np.maximum(d_i + d_s, 1e-4))[..., None]
        col = (icol * (1 - ls) + snow * ls) * lw + wat * (1 - lw)
        alpha = np.maximum(soft_mask(nz), blk(nz))
        save(np.dstack([np.clip(col, 0, 255), alpha * 255]).round().astype(np.uint8), out, s, f)
    return len(anim)


FARM_WATER = np.zeros(256, bool)
FARM_WATER[112:128] = True
FARM_PLANT = np.zeros(256, bool)
FARM_PLANT[48:80] = True                  # рис кадра 83 (рампы 48 и 64)
FARM_PLANTS_PNG = ROOT / "art" / "water" / "src" / "IDT_FARM_WATER_83_pack.png"


def build_farm_water(pal, out, blur=1.6):
    """Рисовые чеки IDT_FARM_WATER (07.10): статичная вода, у каждой записи один кадр. Кадры записей, где есть
    вода (индексы 112..127): вода - кадр сам с собой на изорешётке, мягкое x4 (как POLAR); вал и островки -
    premultiplied мягкое x4 своих цветов классики; слои по плотности, как build_shore. Рис кадра 83 - стебли
    прежнего пака (FARM_PLANTS_PNG, сохранённая копия; маска по зелени), под ними новая вода: у прежнего
    пака на 83 и 64 бурый затёк у левой вершины - на поле метка в каждой клетке."""
    s = "IDT_FARM_WATER"
    frames = read_set(s)
    recs, _ = records(s)
    used = sorted({r[0] for r in recs if (FARM_WATER[frames[r[0]]] & (frames[r[0]] != 0)).any()})
    mean = pal[frames[64][FARM_WATER[frames[64]] & (frames[64] != 0)]].astype(np.float32).mean(0)

    def dens(m, col=None):
        ch = [m.astype(np.float32)[..., None]] if col is None else [col * m[..., None], m.astype(np.float32)[..., None]]
        return up_float(np.pad(np.dstack(ch), ((2, 2), (2, 2), (0, 0))), 1.2)[2 * K:-2 * K, 2 * K:-2 * K]

    for f in used:
        a = frames[f]
        nz = a != 0
        pm = nz & FARM_PLANT[a]
        wm = nz & (FARM_WATER[a] | pm)          # под стеблями - вода
        im = nz & ~wm
        wa = a.copy()
        wa[pm] = 0                               # стебли не красят воду: там средний цвет воды
        wat = polar_water(wa, pal, mean, blur, FARM_WATER)
        ui = dens(im, pal[a].astype(np.float32))
        d_i = np.clip(ui[..., 3], 0, None)
        icol = ui[..., :3] / np.maximum(d_i[..., None], 1e-3)
        d_w = np.clip(dens(wm)[..., 0], 0, None)
        lw = np.clip((d_i / np.maximum(d_i + d_w, 1e-4) - 0.5) * 2.2 + 0.5, 0, 1)[..., None]
        col = icol * lw + wat * (1 - lw)
        alpha = np.maximum(soft_mask(nz), blk(nz))
        if pm.any():
            p = np.asarray(Image.open(FARM_PLANTS_PNG).convert("RGBA")).astype(np.float32)
            g = p[..., 1] - np.maximum(p[..., 0], p[..., 2])
            m = (np.clip((g - 4) / 16, 0, 1) * p[..., 3] / 255)[..., None]
            col = p[..., :3] * m + col * (1 - m)
            alpha = np.maximum(alpha, m[..., 0])
        save(np.dstack([np.clip(col, 0, 255), alpha * 255]).round().astype(np.uint8), out, s, f)
    print("  кадры:", used)
    return len(used)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--sets", default="SEAURBAN,SEABITS,CARGO2_IND,POLAR")
    ap.add_argument("--land-dir", default="", help="папка TERRAIN с кадром 0 пола-соседа болот (вместо установки)")
    a = ap.parse_args()
    if a.land_dir:
        global LAND_DIR
        LAND_DIR = Path(a.land_dir)
    pal = palette()
    fn = {"SEAURBAN": build_seaurban, "SEABITS": build_seabits, "CARGO2_IND": build_foam, "POLAR": build_polar}
    fn.update({s: build_swamp(s) for s in SWAMP_RAMP})
    fn["IDT_FARM_WATER"] = build_farm_water
    for s in a.sets.split(","):
        print(s, "кадров", fn[s](pal, a.out), "->", Path(a.out) / (s + ".PCK"))


if __name__ == "__main__":
    main()
