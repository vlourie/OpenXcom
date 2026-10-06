r"""Лист первого задания графического пилота карт (асфальт и бордюр) - до генерации, для выбора модели (07.10).

Что на листе:
  1. кадры задания: классика x4 (боевая палитра delicious_regular, тень 0) | нынешний HD (копия мода hd в
     установке Пираток - её читает игра, R-087) | разметка защищённых деталей; варианты 0.v1..v3 отдельно;
  2. собранный участок: настоящий бой STR_ERIDIAN_TERROR_139 (census/maps/pilot2/refs/asphalt_corner/site.sav),
     угол перекрёстка URBAN02 у полос тротуара соседнего блока - тротуар ROADS:0, бордюр 1, 2, угол 7,
     асфальт 9, разметка 11 - классика | нынешний HD | разметка; клетки раскладываются как Map::drawTerrain
     (x = (cx - cy) * 16, y = (cx + cy) * 8), только пол, без предметов и стен;
  3. контроль URBAN:52 - на своём настоящем месте: крыша этажа 2 блока MADURBAN35;
  4. описание планируемого материала.
Разметка: красное - граница тротуара (рампа 0) и асфальта с бордюром (рампа 15); оранжевое - тёмная полоса
бордюра (индексы 249..252 в кадрах 1..8); голубое - светлая разметка (индекс 240 в 10..13, 242..243 в URBAN:52);
жёлтое - границы клеток.

  py -3.13 pilot2_job_sheet.py [--out census/maps/pilot2/sheets/job1_asphalt.png]
"""
import argparse, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import geom_mask as gm
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "census" / "maps" / "pilot2" / "sheets" / "job1_asphalt.png"))
    a = ap.parse_args()
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    f_t = ImageFont.truetype(FONT_B, 22)
    f_h = ImageFont.truetype(FONT_B, 16)
    f_s = ImageFont.truetype(FONT, 14)

    blocks = Blocks()
    corner = Blocks.battle_floor(CORNER, *CORNER_AT)
    roof_all = blocks.floors("MADURBAN35")
    roof = {(x, y): roof_all[(2, y, x)] for x in range(3, 7) for y in range(3, 7) if (2, y, x) in roof_all}
    used = sorted(set(corner.values()))
    print("угол URBAN02:", used)
    print("крыша MADURBAN35 этаж 2:", sorted(set(roof.values())))

    WIDTH = 1640
    sheet = Image.new("RGB", (WIDTH, 2400), BG)
    d = ImageDraw.Draw(sheet)
    y = 10
    d.text((14, y), "Пилот карт, задание 1: тротуар ROADS:0 с бордюром ROADS:1, 7 - лист до генерации (ничего не сгенерировано)",
           font=f_t, fill=(255, 255, 255))
    y += 34
    d.text((14, y), "классика x4 - боевая палитра delicious_regular, тень 0; нынешний HD - мод hd в установке Пираток (его читает игра; "
           "копия в репозитории расходится в 17 кадрах ROADS)", font=f_s, fill=(235, 235, 235))
    y += 26

    # 1. кадры
    d.text((14, y), "1. Кадры (пол - нижние 64 строки кадра x4, показ x2)", font=f_h, fill=(255, 255, 0))
    y += 24
    frames = [("ROADS", 0, "тротуар 0"), ("ROADS", 1, "бордюр 1"), ("ROADS", 7, "угол 7 (сводит 1 и 2)"),
              ("ROADS", 2, "бордюр 2 (соседний)"), ("ROADS", 9, "асфальт 9 (сосед)"), ("URBAN", 52, "URBAN:52 (крыша)")]
    crop = (0, 96, 128, 160)
    cw = 262
    rows = ("классика x4", "HD сейчас", "защищено")
    for j, lbl in enumerate(rows):
        d.text((14, y + 20 + j * 136 + 54), lbl, font=f_s, fill=(255, 255, 255))
    for i, (s, f, lbl) in enumerate(frames):
        x0 = 110 + i * cw
        d.text((x0, y), lbl, font=f_s, fill=(255, 255, 255))
        i4 = classic_idx(s, f)
        rc = rgba_classic(i4)
        paste(sheet, rc, (x0, y + 20), crop, 2)
        paste(sheet, rgba_hd(s, str(f)), (x0, y + 20 + 136), crop, 2)
        e, kk, m = protect(s, f, i4)
        paste(sheet, markup(rc[..., :3], e, kk, m, rc[..., 3]), (x0, y + 20 + 272), crop, 2)
    y += 20 + 3 * 136 + 4
    d.text((14, y), "Варианты пола ROADS:0 в нынешнем паке - движок раскладывает их узором по всему тротуару; "
           "перерисовываются вместе с 0.png, иначе старые останутся в узоре:", font=f_s, fill=(255, 255, 255))
    y += 22
    for i, nm in enumerate(("0", "0.v1", "0.v2", "0.v3")):
        x0 = 110 + i * cw
        paste(sheet, rgba_hd("ROADS", nm), (x0, y + 18), crop, 2)
        d.text((x0, y), "ROADS %s%s" % (nm, "  - борозды («пашня»)" if nm == "0.v1" else ""), font=f_s, fill=(255, 255, 255))
    y += 18 + 132 + 10

    # 2. собранный участок
    cx, cy, n = CORNER_AT
    d.text((14, y), "2. Собранный участок: бой STR_ERIDIAN_TERROR_139, угол перекрёстка URBAN02 у тротуара соседнего блока "
           "(этаж 0, клетки x %d..%d, y %d..%d) - только пол" % (cx, cx + n - 1, cy, cy + n - 1), font=f_h, fill=(255, 255, 0))
    y += 24
    # пятна по 2 x 2 клетки в порядке шкалы движка (v3, v1, 0, v2 - HdCanvas groundFrameFor); в игре узор свой
    var_names = ("0.v3", "0.v1", "0", "0.v2")
    cl_rgba, idx, ed, kb, mk, grid = assemble(corner, lambda s, f, x, yy: rgba_classic(classic_idx(s, f)))
    hd_rgba, *_ = assemble(corner, lambda s, f, x, yy: rgba_hd(s, var_names[(x // 2 + 2 * (yy // 2)) % 4] if (s, f) == ("ROADS", 0) else str(f)))
    H, W = cl_rgba.shape[:2]
    top = 96          # строки выше ромбов верхнего ряда пусты
    sec = (0, top, W, H)
    sc = 1
    mkp = markup(cl_rgba[..., :3], ed, kb, mk, cl_rgba[..., 3])
    mkp[grid & (cl_rgba[..., 3] > 0) & ~ed & ~kb & ~mk] = (255, 230, 0, 255)
    gap = 14
    xs = [14, 14 + W + gap]
    d.text((xs[0], y), "классика x4", font=f_s, fill=(255, 255, 255))
    d.text((xs[1], y), "HD сейчас (0, 0.v1-v3 - пятнами 2x2 условно; в игре узор groundFrameFor со смешением на краях)", font=f_s, fill=(255, 255, 255))
    paste(sheet, cl_rgba, (xs[0], y + 18), sec, sc)
    paste(sheet, hd_rgba, (xs[1], y + 18), sec, sc)
    y += 18 + (H - top) + 12
    d.text((14, y), "защищено на участке: красное - край тротуара (рампа 0 | рампа 15), оранжевое - тёмная полоса бордюра, "
           "голубое - разметка асфальта, жёлтое - границы клеток", font=f_s, fill=(255, 255, 255))
    y += 20
    paste(sheet, mkp, (14, y), sec, sc)
    # 3. контроль URBAN:52 справа от разметки
    rx = 14 + W + gap
    d.text((rx, y), "3. Контроль URBAN:52 на своём месте - крыша этажа 2 блока MADURBAN35", font=f_h, fill=(255, 255, 0))
    r_cl, r_idx, r_ed, r_kb, r_mk, r_grid = assemble(roof, lambda s, f, x, yy: rgba_classic(classic_idx(s, f)))
    r_hd, *_ = assemble(roof, lambda s, f, x, yy: rgba_hd(s, str(f)))
    rh, rw = r_cl.shape[:2]
    rmk = markup(r_cl[..., :3], r_ed, r_kb, r_mk, r_cl[..., 3])
    rsec = (0, 96, rw, rh)
    paste(sheet, r_cl, (rx, y + 44), rsec, 1)
    paste(sheet, r_hd, (rx + rw + 10, y + 44), rsec, 1)
    d.text((rx, y + 26), "классика x4", font=f_s, fill=(255, 255, 255))
    d.text((rx + rw + 10, y + 26), "HD сейчас", font=f_s, fill=(255, 255, 255))
    paste(sheet, rmk, (rx, y + 44 + (rh - 96) + 26), rsec, 1)
    d.text((rx, y + 44 + (rh - 96) + 8), "голубое - светлые полосы (индексы 242-243)", font=f_s, fill=(255, 255, 255))
    y += max(H - top, 44 + 2 * (rh - 96) + 30) + 16

    # 4. материал
    L = lab(PAL[classic_idx("ROADS", 0)[classic_idx("ROADS", 0) > 0]]).mean(0)
    i1 = classic_idx("ROADS", 1)
    Lk = lab(PAL[i1[(i1 >= 249) & (i1 <= 252)]]).mean(0)
    L9 = lab(PAL[classic_idx("ROADS", 9)[classic_idx("ROADS", 9) > 0]]).mean(0)
    d.text((14, y), "4. Планируемый материал (описание задания, не промпт)", font=f_h, fill=(255, 255, 0))
    y += 24
    text = [
        "Тротуар ROADS:0 - ровный серый бетон-асфальт тротуара, вид строго сверху. Цвет - средний цвет классики: L %.0f, a %.1f, b %.1f "
        "(тёмно-серый, чуть холодный)." % tuple(L),
        "Зерно мелкое, порядка базового пикселя (x4 - 3-5 пикселей), как крап классики из трёх оттенков; поверхность ровная: без плит, "
        "кирпича, швов, борозд и бугров. Допустимы слабые пятна износа и блики - не воспроизводить пиксельный шум классики.",
        "Бордюр (1, 7, и 2 у угла): тёмная полоса вдоль края асфальта, L %.0f; положение и ширина - по классике (красная и оранжевая "
        "разметка), край тротуара прямой, без лесенки. Фактура бордюра - та же, что у тротуара." % Lk[0],
        "Асфальт ROADS:9 (L %.0f) и разметка 10/11 в задание не входят: они - соседи, по ним проверяется стык. "
        "URBAN:52 - покрытие крыши этажа 2 (322 клетки на блок): контроль сохранения полос, а не дорога." % L9[0],
        "Способ: одна бесшовная текстура материала сверху -> перенос в ромб по мировым координатам клетки -> кадры 0, 0.v1-v3, 1, 7 "
        "из разных участков той же текстуры; маска - силуэт классики, граница тротуара и бордюра - по красной линии.",
        "Приёмка: этот же участок боя собранным, классика | новое, при одном свете; числа dE, контраст, направленность - диагностика, "
        "не ворота. Модель выбирается по одному пробному результату; все 11 заданий не запускаются.",
        "Вопросы до пробы: (1) бордюр 2 - в задание? Угол 7 сводит бордюры 1 и 2; без 2 стык угла с соседом останется старым. "
        "(2) Что за светлые полосы URBAN:52 - рёбра кровли или разметка парковки? По кадру 32x40 не опознать (R-071).",
    ]
    for t in text:
        # перенос по ширине
        words, line = t.split(" "), ""
        for w in words:
            if d.textlength(line + " " + w, font=f_s) > WIDTH - 40:
                d.text((14, y), line, font=f_s, fill=(240, 240, 240))
                y += 19
                line = w
            else:
                line = (line + " " + w).strip()
        d.text((14, y), line, font=f_s, fill=(240, 240, 240))
        y += 25
    sheet = sheet.crop((0, 0, WIDTH, y + 6))
    sheet.save(out)
    print("лист:", out, sheet.size)
    print("Lab тротуар %.1f %.1f %.1f, бордюр %.1f, асфальт %.1f" % (L[0], L[1], L[2], Lk[0], L9[0]))


if __name__ == "__main__":
    main()
