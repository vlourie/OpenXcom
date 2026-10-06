r"""Лист первого задания графического пилота карт «тротуар ROADS с бордюрами» - до генерации (07.10).

Состав задания: тротуар ROADS:0 вместе с вариантами 0.v1..v3 и бордюры ROADS:1, 2, 7 - один связанный участок
(угол 7 сводит 1 и 2; без 2 угол остался бы соединён со старой клеткой). Асфальт ROADS:9..13 - отдельное
задание road_asphalt; URBAN:52 до опознания не входит ни в одно задание покрытия.

Что на листе:
  1. кадры задания: классика x4 (боевая палитра delicious_regular, тень 0) | нынешний HD (копия мода hd в
     установке Пираток - её читает игра, R-087) | разметка защищённых деталей; варианты 0.v1..v3 отдельно,
     со средней светлотой каждого (диагностика тёмных клеток);
  2. собранный участок: настоящий бой STR_ERIDIAN_TERROR_139 (census/maps/pilot2/refs/asphalt_corner/site.sav),
     угол перекрёстка URBAN02 у полос тротуара соседнего блока - классика | нынешний HD | разметка; клетки
     раскладываются как Map::drawTerrain, только пол; варианты ROADS:0 - точной раскладкой движка
     (ground_field.py, порт Canvas32::groundFrameFor с зерном боя Map::groundSeed, смешение на краях пятен);
  3. поле 9 x 9 одного тротуара ROADS:0 на клетках того же боя - классика | нынешний HD с вариантами и карта
     вариантов: здесь видны «пашня», тёмные клетки и разрывы цвета;
  4. описание планируемого материала.
Разметка: красное - граница тротуара (рампа 0) и асфальта с бордюром (рампа 15); оранжевое - тёмная полоса
бордюра (индексы 249..252 в кадрах 1..8); голубое - светлая разметка асфальта (индекс 240 в 10..13);
жёлтое - границы клеток.

  py -3.13 pilot2_job_sheet.py [--out census/maps/pilot2/sheets/job1_sidewalk.png]
"""
import argparse, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import geom_mask as gm
import ground_field as gf
import map_truth as mt

ROOT = mt.ROOT
INST = ROOT / "Пиратки" / "Dioxine_XPiratez"
HD = INST / "user" / "mods" / "hd" / "hd" / "TERRAIN"
PAL_FILE = INST / "user" / "mods" / "Piratez" / "Resources" / "Pals" / "delicious_regular.pal"
SITE = ROOT / "census" / "maps" / "pilot2" / "refs" / "asphalt" / "site.sav"
# настоящий бой, где угол перекрёстка URBAN02 (ROADS:7 в клетке 51,11) примыкает к длинным полосам тротуара
CORNER = ROOT / "census" / "maps" / "pilot2" / "refs" / "asphalt_corner" / "site.sav"   # STR_ERIDIAN_TERROR_139
CORNER_AT = (47, 7, 6)   # окно 6 x 6: тротуар x 47..50, y 7..10; бордюр 1 - x 51; бордюр 2 - y 11; асфальт 9/11
K = 4
FW, FH = 32 * K, 40 * K
FONT = "C:/Windows/Fonts/arial.ttf"
FONT_B = "C:/Windows/Fonts/arialbd.ttf"
BG = (118, 118, 122)


def palette():
    v = PAL_FILE.read_text(encoding="utf-8", errors="replace").split()
    return np.array([int(t) for t in v[3:3 + 768]], np.uint8).reshape(-1, 3)


PAL = palette()


def lab(rgb):
    c = rgb.astype(float) / 255
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    xyz = c @ np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]]).T
    xyz /= np.array([0.9505, 1.0, 1.089])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def classic_idx(s, f):
    """Индексы кадра x4 (повтор пикселя - только для показа и разметки, не вход генерации)."""
    idx, _ = gm.classic(s, f)
    return np.repeat(np.repeat(idx, K, 0), K, 1)


def rgba_classic(idx4):
    return np.dstack([PAL[idx4], np.where(idx4 > 0, 255, 0).astype(np.uint8)])


def rgba_hd(s, name):
    p = HD / (s + ".PCK") / (name + ".png")
    return np.asarray(Image.open(p).convert("RGBA")) if p.exists() else np.zeros((FH, FW, 4), np.uint8)


def protect(s, f, idx4):
    """Маски защищённых деталей кадра x4: граница рамп 0|15, полоса бордюра, светлая разметка."""
    rp = np.where(idx4 > 0, idx4 // 16, -1)
    edge = np.zeros(idx4.shape, bool)
    for a, b in ((rp[:, 1:], rp[:, :-1]), (rp[1:, :], rp[:-1, :])):
        e = ((a == 0) & (b == 15)) | ((a == 15) & (b == 0))
        if a.shape[1] != rp.shape[1]:
            edge[:, 1:] |= e
            edge[:, :-1] |= e
        else:
            edge[1:, :] |= e
            edge[:-1, :] |= e
    kerb = np.zeros(idx4.shape, bool)
    mark = np.zeros(idx4.shape, bool)
    if s == "ROADS" and 1 <= f <= 8:
        kerb = (idx4 >= 249) & (idx4 <= 252)
    if s == "ROADS" and 10 <= f <= 13:
        mark = idx4 == 240
    if s == "URBAN" and f == 52:
        mark = (idx4 >= 242) & (idx4 <= 243)
    return edge, kerb, mark


def markup(rgb, edge, kerb, mark, alpha):
    """Классика приглушена, детали цветом поверх."""
    out = (rgb.astype(float) * 0.45 + 60).astype(np.uint8)
    out[kerb] = (255, 150, 30)
    out[mark] = (60, 220, 255)
    out[edge] = (255, 40, 40)
    return np.dstack([out, alpha])


def paste(sheet, arr, xy, crop=None, scale=1):
    im = Image.fromarray(arr, "RGBA")
    if crop:
        im = im.crop(crop)
    if scale != 1:
        im = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
    sheet.paste(im, xy, im)
    return im.size


# ------------------------------------------------------------------ блоки

class Blocks:
    def __init__(self):
        bt = mt.Battle(SITE)
        self.data = mt.Data(bt.mods)

    @staticmethod
    def battle_floor(sav, x0, y0, n):
        """Пол этажа 0 настоящего боя, окно n x n с угла (x0, y0): {(x, y): (набор, кадр)} - только пол."""
        bt = mt.Battle(sav)
        data = mt.Data(bt.mods)
        out = {}
        for y in range(y0, y0 + n):
            for x in range(x0, x0 + n):
                f = bt.part(0, y, x, 0)
                if f is not None:
                    s = bt.sets[f[0]]
                    out[(x - x0, y - y0)] = (s, data.mcd(s)[f[1]]["frames"][0])
        return out

    def floors(self, block, terrain="URBAN"):
        """{(z, y, x): (набор, кадр)} пола блока - сквозной номер по наборам террейна, как RuleTerrain::getMapData."""
        sets = self.data.terrains[terrain]["mapDataSets"]
        if not any(b.get("name") == block for b in self.data.terrains[terrain]["mapBlocks"]):
            raise SystemExit("блока %s нет в террейне %s" % (block, terrain))
        sizes = [len(self.data.mcd(s)) for s in sets]
        sy, sx, sz, body = self.data.map_file(block)
        out = {}
        x = y = 0
        z = sz - 1
        for k in range(0, len(body) - 3, 4):
            v = body[k]
            if v > 0:
                mid, si = v, 0
                while si < len(sets) and mid >= sizes[si]:
                    mid -= sizes[si]
                    si += 1
                if si < len(sets):
                    out[(z, y, x)] = (sets[si], self.data.mcd(sets[si])[mid]["frames"][0])
            x += 1
            if x == sx:
                x, y = 0, y + 1
            if y == sy:
                y, z = 0, z - 1
        return out


def assemble(cells, pick):
    """Пол из клеток {(x, y): (набор, кадр)} в порядке Map::drawTerrain. pick(s, f, x, y) -> RGBA x4.
    Возвращает RGBA, индексы классики, маски деталей, границы клеток."""
    xs = [c[0] for c in cells]
    ys = [c[1] for c in cells]
    ox = -min(x - y for x, y in cells) * 16 * K
    oy = -min(x + y for x, y in cells) * 8 * K
    W = (max(x - y for x, y in cells) - min(x - y for x, y in cells)) * 16 * K + FW
    H = (max(x + y for x, y in cells) - min(x + y for x, y in cells)) * 8 * K + FH
    rgba = np.zeros((H, W, 4), np.uint8)
    idx = np.zeros((H, W), np.int32)
    ed, kb, mk = (np.zeros((H, W), bool) for _ in range(3))
    grid = np.zeros((H, W), bool)
    for (x, y) in sorted(cells, key=lambda c: (c[0] + c[1], c[0])):
        s, f = cells[(x, y)]
        sx, sy = ox + (x - y) * 16 * K, oy + (x + y) * 8 * K
        src = pick(s, f, x, y)
        a = src[..., 3] > 0
        sl = (slice(sy, sy + FH), slice(sx, sx + FW))
        rgba[sl][a] = src[a]
        i4 = classic_idx(s, f)
        ci = i4 > 0
        idx[sl][ci] = i4[ci]
        e, kk, m = protect(s, f, i4)
        ed[sl] |= e
        kb[sl] |= kk
        mk[sl] |= m
        # граница клетки: край ромба пола (кадр x4, ромб 128x64 с верхом в строке 96)
        yy, xx = np.mgrid[0:FH, 0:FW]
        d = np.abs(xx + 0.5 - 64) / 64 + np.abs(yy + 0.5 - 128) / 32
        grid[sl] |= (np.abs(d - 1) < 0.02)
    return rgba, idx, ed, kb, mk, grid


def ground_pick(seed, wx, wy, found):
    """Кадр пола в мировой клетке: ROADS:0 с вариантами - раскладка движка, остальное - свой кадр пака."""
    def pick(s, f, x, y):
        if (s, f) == ("ROADS", 0):
            return gf.frame_for(found, wx + x, wy + y, 0, seed, K)
        return rgba_hd(s, str(f))
    return pick


def walk_light(f):
    """L* поверхности тротуара (рампа 0 классики) внутри кадра ROADS: классика и нынешний HD на тех же пикселях."""
    i4 = classic_idx("ROADS", f)
    m = (i4 > 0) & (i4 < 16)
    m[:96] = False
    hd = rgba_hd("ROADS", str(f))
    m_hd = m & (hd[..., 3] > 0)
    return float(lab(PAL[i4[m]]).mean(0)[0]), float(lab(hd[..., :3][m_hd]).mean(0)[0])


def light(rgba):
    """Средняя светлота L* пола кадра (нижние 64 строки x4, непрозрачное)."""
    fl = rgba[96:]
    a = fl[..., 3] > 0
    return float(lab(fl[..., :3][a]).mean(0)[0]) if a.any() else float("nan")


VCOL = {"0.v3": (70, 110, 200), "0.v1": (170, 110, 60), "0": (150, 150, 150), "0.v2": (80, 170, 90)}


def variant_map(seed, wx, wy, n, scale_names, cw=36):
    """Карта вариантов поля n x n в той же изометрии: цвет - вариант в центре клетки, толстая рамка - клетка
    целиком одного варианта (рисуется кадром как есть), без рамки - смешение двух соседних по рваной линии."""
    W, H = n * cw, n * cw // 2 + 4
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    count = len(scale_names)
    for yy in range(n):
        for xx in range(n):
            lv = float(gf.ground_level(seed, np.float32(wx + xx + 0.5), np.float32(wy + yy + 0.5), 0, count))
            nm = scale_names[int(min(count - 1, max(0, round(lv))))]
            cx = (xx - yy) * cw // 2 + (n - 1) * cw // 2 + cw // 2
            cy = (xx + yy) * cw // 4 + cw // 4
            poly = [(cx, cy - cw // 4), (cx + cw // 2, cy), (cx, cy + cw // 4), (cx - cw // 2, cy)]
            pure = gf.pick(count, wx + xx, wy + yy, 0, seed) >= 0
            d.polygon(poly, fill=VCOL[nm] + (255,), outline=(255, 255, 255, 255) if pure else (40, 40, 40, 255),
                      width=3 if pure else 1)
    return im


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "census" / "maps" / "pilot2" / "sheets" / "job1_sidewalk.png"))
    a = ap.parse_args()
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    f_t = ImageFont.truetype(FONT_B, 22)
    f_h = ImageFont.truetype(FONT_B, 16)
    f_s = ImageFont.truetype(FONT, 14)

    bt = mt.Battle(CORNER)
    seed = gf.battle_seed(bt.X, bt.Y, bt.Z, bt.blocks)
    corner = Blocks.battle_floor(CORNER, *CORNER_AT)
    used = sorted(set(corner.values()))
    print("угол URBAN02:", used, "зерно узора", seed)
    found = [rgba_hd("ROADS", nm) for nm in ("0", "0.v1", "0.v2", "0.v3")]
    # шкала движка: [v3, v1, 0, v2]
    order = gf.scale_order(list(range(4)))
    scale_names = [("0", "0.v1", "0.v2", "0.v3")[j] for j in order]

    WIDTH = 1800
    sheet = Image.new("RGB", (WIDTH, 3000), BG)
    d = ImageDraw.Draw(sheet)

    def para(t, y, font=f_s, fill=(240, 240, 240), step=19):
        words, line = t.split(" "), ""
        for w in words:
            if d.textlength(line + " " + w, font=font) > WIDTH - 40:
                d.text((14, y), line, font=font, fill=fill)
                y += step
                line = w
            else:
                line = (line + " " + w).strip()
        d.text((14, y), line, font=font, fill=fill)
        return y + step

    y = 10
    d.text((14, y), "Пилот карт, задание 1: тротуар ROADS с бордюрами - ROADS:0 с вариантами 0.v1-v3 и бордюры 1, 2, 7. "
           "Лист до генерации (ничего не сгенерировано)", font=f_t, fill=(255, 255, 255))
    y += 34
    y = para("классика x4 - боевая палитра delicious_regular, тень 0; нынешний HD - мод hd в установке Пираток (его читает игра). "
             "Асфальт ROADS:9-13 - отдельное задание road_asphalt; URBAN:52 до опознания не входит ни в одно задание покрытия.", y)
    y += 6

    # 1. кадры
    d.text((14, y), "1. Кадры (пол - нижние 64 строки кадра x4, показ x2)", font=f_h, fill=(255, 255, 0))
    y += 24
    frames = [("ROADS", 0, "тротуар 0"), ("ROADS", 1, "бордюр 1"), ("ROADS", 2, "бордюр 2"),
              ("ROADS", 7, "угол 7 (сводит 1 и 2)"), ("ROADS", 9, "асфальт 9 - сосед, старый"),
              ("ROADS", 3, "бордюр 3 - сосед, старый")]
    crop = (0, 96, 128, 160)
    cw = 262
    for j, lbl in enumerate(("классика x4", "HD сейчас", "защищено")):
        d.text((14, y + 20 + j * 136 + 54), lbl, font=f_s, fill=(255, 255, 255))
    for i, (s, f, lbl) in enumerate(frames):
        x0 = 110 + i * cw
        d.text((x0, y), lbl, font=f_s, fill=(255, 255, 255) if i < 4 else (200, 200, 200))
        i4 = classic_idx(s, f)
        rc = rgba_classic(i4)
        paste(sheet, rc, (x0, y + 20), crop, 2)
        paste(sheet, rgba_hd(s, str(f)), (x0, y + 20 + 136), crop, 2)
        e, kk, m = protect(s, f, i4)
        paste(sheet, markup(rc[..., :3], e, kk, m, rc[..., 3]), (x0, y + 20 + 272), crop, 2)
    y += 20 + 3 * 136 + 4
    Lc = light(rgba_classic(classic_idx("ROADS", 0)))
    Ls = {nm: light(fr) for nm, fr in zip(("0", "0.v1", "0.v2", "0.v3"), found)}
    y = para("Варианты пола ROADS:0 в нынешнем паке - перерисовываются вместе с 0.png из того же материала, иначе старые "
             "останутся в узоре; у всех четырёх - диагональные борозды («пашня»). Средняя светлота L*: классика %.1f; %s." %
             (Lc, ", ".join("%s %.1f" % (k, v) for k, v in Ls.items())), y, fill=(255, 255, 255))
    for i, nm in enumerate(("0", "0.v1", "0.v2", "0.v3")):
        x0 = 110 + i * cw
        paste(sheet, found[i], (x0, y + 18), crop, 2)
        d.rectangle((x0, y + 3, x0 + 12, y + 15), fill=VCOL[nm])
        d.text((x0 + 18, y), "ROADS %s  L* %.1f" % (nm, Ls[nm]),
               font=f_s, fill=(255, 255, 255))
    y += 18 + 132 + 8
    wl = {f: walk_light(f) for f in (0, 1, 2, 7)}
    y = para("Тротуар внутри бордюрных кадров, L* на пикселях рампы 0 классики (классика -> HD сейчас): " +
             "; ".join("%d: %.1f -> %.1f" % (f, c, h) for f, (c, h) in wl.items()) +
             ". В классике тротуар у бордюра того же тона, что в кадре 0; в нынешнем HD бордюрные кадры целиком тёмные - "
             "отсюда тёмная полоса клеток вдоль края тротуара.", y, fill=(255, 220, 160))
    y += 8

    # 2. собранный участок
    cx, cy, n = CORNER_AT
    d.text((14, y), "2. Собранный участок: бой STR_ERIDIAN_TERROR_139, угол перекрёстка URBAN02 у тротуара соседнего блока "
           "(этаж 0, клетки x %d..%d, y %d..%d) - только пол" % (cx, cx + n - 1, cy, cy + n - 1), font=f_h, fill=(255, 255, 0))
    y += 24
    cl_rgba, idx, ed, kb, mk, grid = assemble(corner, lambda s, f, x, yy: rgba_classic(classic_idx(s, f)))
    hd_rgba, *_ = assemble(corner, ground_pick(seed, cx, cy, found))
    H, W = cl_rgba.shape[:2]
    top = 96
    sec = (0, top, W, H)
    mkp = markup(cl_rgba[..., :3], ed, kb, mk, cl_rgba[..., 3])
    mkp[grid & (cl_rgba[..., 3] > 0) & ~ed & ~kb & ~mk] = (255, 230, 0, 255)
    gap = 14
    xs = [14, 14 + W + gap, 14]
    d.text((xs[0], y), "классика x4", font=f_s, fill=(255, 255, 255))
    d.text((xs[1], y), "HD сейчас - варианты раскладкой движка", font=f_s, fill=(255, 255, 255))
    paste(sheet, cl_rgba, (xs[0], y + 18), sec)
    paste(sheet, hd_rgba, (xs[1], y + 18), sec)
    y += 18 + (H - top) + 8
    d.text((xs[2], y), "защищено", font=f_s, fill=(255, 255, 255))
    paste(sheet, mkp, (xs[2], y + 18), sec)
    y += 18 + (H - top) + 4
    y = para("красное - край тротуара (рампа 0 | рампа 15), оранжевое - тёмная полоса бордюра, голубое - разметка асфальта, "
             "жёлтое - границы клеток. Асфальт 9 и разметка 11 на участке - соседи стыка, остаются старыми.", y,
             fill=(255, 255, 255))
    y += 8

    # 3. поле 9 x 9
    N = 9
    fx0, fy0 = cx - 4, cy - 4
    d.text((14, y), "3. Поле 9 x 9 одного тротуара ROADS:0 - клетки x %d..%d, y %d..%d того же боя (зерно узора %d), "
           "как если бы там лежал только тротуар" % (fx0, fx0 + N - 1, fy0, fy0 + N - 1, seed), font=f_h, fill=(255, 255, 0))
    y += 24
    hd_field, picks = gf.field(found, n=N, seed=seed, x0=fx0, y0=fy0, k=K, bg=BG)
    cl_field, _ = gf.field([rgba_classic(classic_idx("ROADS", 0))], n=N, seed=seed, x0=fx0, y0=fy0, k=K, bg=BG)
    fh, fw = hd_field.shape[:2]
    fsec = (0, top, fw, fh)
    d.text((14, y), "HD сейчас - 0 и 0.v1-v3 раскладкой движка (Canvas32::groundFrameFor), x4 в натуральную величину",
           font=f_s, fill=(255, 255, 255))
    paste(sheet, hd_field, (14, y + 18), fsec)
    rx = 14 + fw + gap
    half = Image.fromarray(cl_field).crop(fsec)
    half = half.resize((half.width // 2, half.height // 2), Image.LANCZOS)
    d.text((rx, y), "классика (один кадр), уменьшено вдвое", font=f_s, fill=(255, 255, 255))
    sheet.paste(half, (rx, y + 18))
    vy = y + 18 + half.height + 16
    d.text((rx, vy), "карта вариантов (вариант в центре клетки):", font=f_s, fill=(255, 255, 255))
    vm = variant_map(seed, fx0, fy0, N, scale_names)
    sheet.paste(vm, (rx, vy + 20), vm)
    ly = vy + 20 + vm.height + 8
    for nm in scale_names:
        d.rectangle((rx, ly + 2, rx + 14, ly + 14), fill=VCOL[nm])
        d.text((rx + 20, ly), "%s (L* %.1f)" % (nm, Ls[nm]), font=f_s, fill=(255, 255, 255))
        ly += 19
    pure = sum(1 for v in picks.values() if v >= 0)
    ly = para("", ly)
    for t in ("шкала движка v3 - v1 - 0 - v2: соседние по шкале", "смешиваются по рваной линии; белая рамка -",
              "клетка целиком одного варианта (%d из %d)," % (pure, N * N), "остальные - смешение двух соседних."):
        d.text((rx, ly), t, font=f_s, fill=(235, 235, 235))
        ly += 18
    y = max(y + 18 + (fh - top), ly) + 12

    # 4. материал
    L = lab(PAL[classic_idx("ROADS", 0)[classic_idx("ROADS", 0) > 0]]).mean(0)
    i1 = classic_idx("ROADS", 1)
    Lk = lab(PAL[i1[(i1 >= 249) & (i1 <= 252)]]).mean(0)
    d.text((14, y), "4. Планируемый материал (описание задания, не промпт)", font=f_h, fill=(255, 255, 0))
    y += 24
    text = [
        "Один общий материал тротуара - ровный серый бетон-асфальт, вид строго сверху. Цвет - средний цвет классики: L %.0f, "
        "a %.1f, b %.1f (тёмно-серый, чуть холодный). Из него получаются: основа 0, варианты 0.v1-v3 и поверхность тротуара "
        "в бордюрных кадрах 1, 2, 7 - одна фактура, один цвет, без разрывов на стыке клеток и вариантов." % tuple(L),
        "Зерно мелкое, порядка базового пикселя (x4 - 3-5 пикселей), как крап классики; поверхность ровная: без плит, кирпича, "
        "швов, борозд и бугров. Варианты отличаются слабым износом и пятнами при той же светлоте (разброс L* вариантов - "
        "в пределах 2-3 единиц, сейчас %.1f..%.1f). Допустимы блики; пиксельный шум классики не воспроизводится." %
        (min(Ls.values()), max(Ls.values())),
        "Бордюры 1, 2, 7: тёмная полоса L %.0f; положение, ширина и силуэт - точно по классике (красная и оранжевая "
        "разметка), край тротуара прямой, без лесенки. Новое у бордюра - только материал: камень бордюра и тот же тротуар." % Lk[0],
        "Способ: одна бесшовная текстура материала сверху -> перенос в ромб по мировым координатам клетки -> кадры 0, "
        "0.v1-v3, 1, 2, 7 из разных участков той же текстуры; маска - силуэт классики, граница тротуара и бордюра - по "
        "красной линии.",
        "Приёмка: участок 2 и поле 3 собранными, классика | новое, при одном свете. На поле должны исчезнуть «пашня», тёмные "
        "клетки и разрывы цвета; на участке - тёмная клетка у угла и разрыв на стыке с бордюром. Числа dE, контраст, "
        "направленность - диагностика, не ворота. Модель выбирается по одному пробному результату; остальные задания не "
        "запускаются.",
    ]
    for t in text:
        y = para(t, y) + 6
    sheet = sheet.crop((0, 0, WIDTH, y + 6))
    sheet.save(out)
    print("лист:", out, sheet.size)
    print("Lab тротуар %.1f %.1f %.1f, бордюр %.1f; L* вариантов %s; чистых клеток поля %d из %d"
          % (L[0], L[1], L[2], Lk[0], {k: round(v, 1) for k, v in Ls.items()}, pure, N * N))


if __name__ == "__main__":
    main()
