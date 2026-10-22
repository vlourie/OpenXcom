"""Свой набор завала COLLAPSE_DEBRIS, этап B (docs/research/collapse-debris-mechanics-2026-10-21.md).

Ярусы цепочки лежат в одном наборе: у MCD Die_MCD указывает в тот же набор. Глыба -> куча -> крошка -> пусто.

    py -3.13 tools/collapse_debris_set.py sketch
        эскизы классики 32x40 в палитре боя: куча и глыба - по карте высот, фактура из кадров-доноров, тень
        сдвигом по рампе палитры; крошка - копия кадра-донора. -> art/TERRAIN/COLLAPSE_DEBRIS.PCK/ (original.png,
        original_x4.png, layout.json, hints.json) - вход probe_object.py (strict, через gpuq).
    py -3.13 tools/collapse_debris_set.py install --hd <папка с <кадр>_strict_cut.png>
        MCD, PCK, TAB в user/mods/hd/TERRAIN и HD-кадры в user/mods/hd/hd/TERRAIN/COLLAPSE_DEBRIS.PCK - в обе копии
        мода hd (репозиторий и установка Пираток). Крошка берёт HD-кадр донора.
Записи MCD - копия записи-донора с правкой кадра, слоёв LOFT, хода, брони, Die_MCD и T_Level (смещения -
MapDataSet::loadData)."""
import argparse
import json
import os
import random
import shutil
import struct
import sys

from PIL import Image

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import collapse_census as cc   # noqa: E402
import collapse_v2 as V        # noqa: E402

NAME = "COLLAPSE_DEBRIS"
SHEET = "art/TERRAIN/%s.PCK" % NAME
MODS = ["user/mods/hd", "Пиратки/Dioxine_XPiratez/user/mods/hd"]
FW, FH, MARGIN, COLS = 32, 40, 4, 8

# кадр: (имя, как, донор фактуры, донор записи MCD, подсказка модели)
#   copy  - кадр донора как есть (крошка)
#   heap  - куча: холм по карте высот, высота HEAP_H пикселей
#   slab  - глыба-плита: наклонный брус
#   chunk - глыба-кладка: несколько блоков
FRAMES = [
    ("crumble_concrete", "copy", "URBAN:50", "URBAN:50", ""),
    ("crumble_earth", "copy", "MOUNTGRASS:8", "MOUNTGRASS:8", ""),
    ("crumble_snow", "copy", "MOUNTSNOW2:8", "MOUNTSNOW2:8", ""),
    ("crumble_sand", "copy", "SIETCH:36", "SIETCH:36", ""),
    ("heap_concrete_a", "heap", "URBAN:50", "INDUSLUM:57",
     "a waist-high pile of broken grey concrete chunks, crushed bricks, dust and a few bent rebar rods"),
    ("heap_concrete_b", "heap", "URBAN:57", "INDUSLUM:57",
     "a waist-high heap of shattered grey concrete blocks and plaster rubble with dust"),
    ("heap_earth_a", "heap", "MOUNTGRASS:8", "INDUSLUM:57",
     "a waist-high mound of dark earth, broken stones and splintered planks"),
    ("heap_earth_b", "heap", "MOUNTMUD:8", "INDUSLUM:57",
     "a waist-high heap of brown soil, rocks and broken masonry stones"),
    ("heap_snow", "heap", "MOUNTSNOW2:8", "INDUSLUM:57",
     "a waist-high pile of broken grey stones half covered with snow"),
    ("heap_sand", "heap", "SIETCH:36", "INDUSLUM:57",
     "a waist-high heap of broken sandstone blocks and sand"),
    ("slab_a", "slab", "URBAN:57", "MOUNTROCK:69",   # URBAN:50 давал модели шестигранные пятна (#819, #832, #833)
     "a large broken slab of grey reinforced concrete lying tilted on the ground, rebar sticking out of the broken edge"),
    ("slab_b", "slab", "URBAN:57", "MOUNTROCK:69",
     "a big tilted chunk of grey concrete floor slab, cracked, with bent rebar"),
    ("chunk_a", "chunk", "MOUNTROCK:69", "MOUNTROCK:69",
     "a big broken chunk of grey stone masonry wall lying on the ground, mortar joints visible"),
    ("chunk_b", "chunk", "MOUNTROCK:70", "MOUNTROCK:69",
     "a heap of large fallen grey stone wall blocks, cracked and chipped"),
]
HEAP_H, SLAB_H = 12, 20

# записи MCD: (имя кадра, ход, броня, слои LOFT или None - как у донора, T_Level, во что разрушается)
RECORDS = [
    ("crumble_concrete", None, None, None, None, None),   # 0 - заглушка: Die_MCD 0 значит «ничего»
    ("crumble_concrete", None, None, None, None, None),   # 1
    ("crumble_earth", None, None, None, None, None),      # 2
    ("crumble_snow", None, None, None, None, None),       # 3
    ("crumble_sand", None, None, None, None, None),       # 4
    ("heap_concrete_a", 6, 40, [6, 6, 5, 5, 4, 3], -8, 1),   # 5
    ("heap_concrete_b", 6, 40, [6, 6, 5, 5, 4, 3], -8, 1),   # 6
    ("heap_earth_a", 6, 40, [6, 6, 5, 5, 4, 3], -8, 2),      # 7
    ("heap_earth_b", 6, 40, [6, 6, 5, 5, 4, 3], -8, 2),      # 8
    ("heap_snow", 6, 40, [6, 6, 5, 5, 4, 3], -8, 3),         # 9
    ("heap_sand", 6, 40, [6, 6, 5, 5, 4, 3], -8, 4),         # 10
    ("slab_a", 255, 60, [6, 6, 6, 6, 5, 5, 5, 5, 4, 4], 0, 5),   # 11
    ("slab_b", 255, 60, [6, 6, 6, 6, 5, 5, 5, 5, 4, 4], 0, 6),   # 12
    ("chunk_a", 255, 60, [6, 6, 6, 6, 5, 5, 5, 5, 4, 4], 0, 7),  # 13
    ("chunk_b", 255, 60, [6, 6, 6, 6, 5, 5, 5, 5, 4, 4], 0, 8),  # 14
    # те же глыбы снега и пустыни: сбитые, ложатся кучей своего края
    ("chunk_a", 255, 60, [6, 6, 6, 6, 5, 5, 5, 5, 4, 4], 0, 9),  # 15
    ("chunk_b", 255, 60, [6, 6, 6, 6, 5, 5, 5, 5, 4, 4], 0, 9),  # 16
    ("chunk_a", 255, 60, [6, 6, 6, 6, 5, 5, 5, 5, 4, 4], 0, 10),  # 17
    ("chunk_b", 255, 60, [6, 6, 6, 6, 5, 5, 5, 5, 4, 4], 0, 10),  # 18
]


def data():
    mod_dir, files, loft_path, loft_occ = cc.open_data(V.game_args())
    return files, loft_occ


def mcd_record(files, rec):
    s, i = rec.split(":")
    raw = open(files.find(os.path.join("TERRAIN", s + ".MCD")), "rb").read()
    return bytearray(raw[int(i) * cc.REC:(int(i) + 1) * cc.REC])


def sheet_frame(s, i):
    d = "art/TERRAIN/%s.PCK" % s
    lay = json.load(open(d + "/layout.json", encoding="utf-8-sig"))
    sh = Image.open(d + "/original.png")
    fw, fh, m, cols = lay["frame_w"], lay["frame_h"], lay["margin"], lay["columns"]
    r, c = divmod(i, cols)
    x, y = m + c * (fw + 2 * m), m + r * (fh + 2 * m)
    return sh.crop((x, y, x + fw, y + fh)), sh.getpalette()


def donor_frame(files, rec):
    """Кадр записи-донора: индексы палитры 32x40 и палитра листа."""
    b = mcd_record(files, rec)
    im, pal = sheet_frame(rec.split(":")[0], b[0])
    px = list(im.getdata())
    return [px[y * FW:(y + 1) * FW] for y in range(FH)], pal


def filled(frame):
    """Прозрачное - ближайшим непрозрачным (фактура на всю клетку)."""
    out = [row[:] for row in frame]
    todo = [(x, y) for y in range(FH) for x in range(FW) if out[y][x]]
    seen = {p for p in todo}
    while todo:
        nxt = []
        for x, y in todo:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                q = (x + dx, y + dy)
                if 0 <= q[0] < FW and 0 <= q[1] < FH and q not in seen:
                    seen.add(q)
                    out[q[1]][q[0]] = out[y][x]
                    nxt.append(q)
        todo = nxt
    return out


class Ramps:
    """Тень сдвигом внутри рампы палитры (16 цветов): к цвету той же рампы, светлее или темнее по яркости."""

    def __init__(self, pal):
        self.rgb = [tuple(pal[i * 3:i * 3 + 3]) for i in range(256)]
        self.order = {}
        for r in range(16):
            idx = list(range(r * 16, r * 16 + 16))
            idx = [i for i in idx if 0 < i < 0xFE]      # 0xFE и 0xFF в PCK - пропуск и конец кадра
            idx.sort(key=lambda i: sum(self.rgb[i]))
            for n, i in enumerate(idx):
                self.order[i] = (idx, n)

    def shade(self, i, step):
        if not i or i not in self.order:
            return i
        idx, n = self.order[i]
        return idx[max(0, min(len(idx) - 1, n + step))]


def render(height, tex, ramps, side_step=-3):
    """Карта высот на ромбе клетки -> кадр: точки земли сзади вперёд, у каждой столбик от верха до земли;
    верх - фактура со светом по уклону (свет сверху слева), бок - темнее."""
    img = [[0] * FW for _ in range(FH)]
    N = 64
    pts = []
    for a in range(N + 1):
        for b in range(N + 1):
            u, v = a / N * 2 - 1, b / N * 2 - 1    # оси клетки: u - на восток (вправо вниз), v - на юг (влево вниз)
            h = height(u, v)
            if h <= 0:
                continue
            pts.append((u + v, u, v, h))
    pts.sort()
    for _, u, v, h in pts:
        x = 16 + (u - v) * 16 / 2 * 1.0
        yg = 32 + (u + v) * 8 / 2 * 1.0
        e = 0.06
        gx = (height(u + e, v) - height(u - e, v)) / (2 * e)
        gy = (height(u, v + e) - height(u, v - e)) / (2 * e)
        # свет сверху слева экрана - со стороны -u (ребро клетки слева сверху) и немного -v: склон, что растёт
        # по u (смотрит на -u), светлее
        lit = (gx + 0.4 * gy) / 10.0
        step = int(round(max(-3, min(2, lit * 1.5))))
        # куски: грани по сетке 1/4 клетки, каждая своего тона - эскиз читается как обломки, а не гладкий холм
        step += (hash((int((u + 1) * 4), int((v + 1) * 4), int(h // 3))) % 3) - 1
        xi = int(round(x))
        top = int(round(yg - h))
        bot = int(round(yg))
        if not (0 <= xi < FW):
            continue
        for y in range(max(0, top), min(FH, bot + 1)):
            t = tex[min(FH - 1, max(0, bot - (y - top) // 2))][xi]
            img[y][xi] = ramps.shade(t, step if y == top else side_step)
    return img


def heap_height(seed):
    rnd = random.Random(seed)
    lumps = [(rnd.uniform(-0.5, 0.5), rnd.uniform(-0.5, 0.5), rnd.uniform(0.25, 0.45), rnd.uniform(2, 5)) for _ in range(9)]

    def h(u, v):                                  # клетка - квадрат u, v в [-1, 1]; куча - круглая
        r = (u * u + v * v) ** 0.5 / 1.18
        if r > 1 or max(abs(u), abs(v)) > 0.97:
            return 0
        base = HEAP_H * (1 - r * r) ** 0.8
        for cu, cv, w, a in lumps:
            d = ((u - cu) ** 2 + (v - cv) ** 2) ** 0.5
            if d < w:
                base += a * (1 - d / w) * 0.5
        return max(0.0, min(HEAP_H + 2, base))
    return h


def slab_height(seed):
    rnd = random.Random(seed)
    tilt = rnd.choice((1, -1))

    def h(u, v):
        a, b = (u, v) if tilt > 0 else (v, u)
        if abs(b) > 0.6 or abs(a) > 0.9:
            return 0
        top = 4 + (a + 0.9) / 1.8 * (SLAB_H - 4)
        if abs(b) > 0.52:                         # скос кромки
            top *= 0.8
        return top
    return h


def chunk_height(seed):
    rnd = random.Random(seed)
    blocks = [(rnd.uniform(-0.85, 0.1), rnd.uniform(-0.85, 0.1), rnd.uniform(0.6, 0.9), rnd.uniform(0.6, 0.9),
               rnd.uniform(8, SLAB_H)) for _ in range(5)]

    def h(u, v):
        best = 0
        for cu, cv, wu, wv, hh in blocks:
            if cu <= u <= cu + wu and cv <= v <= cv + wv:
                best = max(best, hh)
        return best if max(abs(u), abs(v)) <= 0.9 else 0
    return h


def sketch(args):
    files, _ = data()
    frames, pal = [], None
    for n, (name, how, tex_rec, _, hint) in enumerate(FRAMES):
        fr, p = donor_frame(files, tex_rec)
        pal = pal or p
        if how == "copy":
            frames.append(fr)
            continue
        ramps = Ramps(p)
        tex = filled(fr)
        h = {"heap": heap_height, "slab": slab_height, "chunk": chunk_height}[how](1000 + n)
        frames.append(render(h, tex, ramps))
    os.makedirs(SHEET, exist_ok=True)
    rows = (len(frames) + COLS - 1) // COLS
    W, H = COLS * (FW + 2 * MARGIN), rows * (FH + 2 * MARGIN)
    sheet = Image.new("P", (W, H), 0)
    sheet.putpalette(pal)
    for i, fr in enumerate(frames):
        r, c = divmod(i, COLS)
        im = Image.new("P", (FW, FH), 0)
        im.putpalette(pal)
        im.putdata([v for row in fr for v in row])
        sheet.paste(im, (MARGIN + c * (FW + 2 * MARGIN), MARGIN + r * (FH + 2 * MARGIN)))
    sheet.info["transparency"] = 0
    sheet.save(os.path.join(SHEET, "original.png"), transparency=0)
    sheet.convert("RGBA").resize((W * 4, H * 4), Image.NEAREST).save(os.path.join(SHEET, "original_x4.png"))
    lay = dict(frame_w=FW, frame_h=FH, count=len(frames), columns=COLS, margin=MARGIN, rows=rows, set=NAME + ".PCK",
               source="tools/collapse_debris_set.py", scale=4, sheet_w=W * 4, sheet_h=H * 4,
               types=[3] * len(frames), names=[f[0] for f in FRAMES])
    with open(os.path.join(SHEET, "layout.json"), "w", encoding="utf-8-sig") as f:
        json.dump(lay, f, ensure_ascii=False, indent=1)
    with open(os.path.join(SHEET, "hints.json"), "w", encoding="utf-8-sig") as f:
        json.dump({str(i): fr[4] for i, fr in enumerate(FRAMES) if fr[4]}, f, ensure_ascii=False, indent=1)
    print(SHEET, "кадров", len(frames), "рисовать:", ",".join(str(i) for i, fr in enumerate(FRAMES) if fr[1] != "copy"))


def encode_pck(frames):
    """Кадры (строки индексов) -> PCK и TAB UFO: первый байт - пустые строки сверху, 0xFE n - n прозрачных,
    0xFF - конец кадра (как читает SurfaceSet::loadPck)."""
    pck, tab = bytearray(), bytearray()
    for fr in frames:
        tab += struct.pack("<H", len(pck))
        flat = [v for row in fr for v in row]
        top = 0
        while top < FH and not any(fr[top]):
            top += 1
        pck.append(top)
        i, n = top * FW, len(flat)
        last = max([k for k, v in enumerate(flat) if v] or [i - 1]) + 1
        while i < last:
            if flat[i] == 0:
                run = 0
                while i < last and flat[i] == 0 and run < 255:
                    run += 1
                    i += 1
                pck += bytes((0xFE, run))
            else:
                pck.append(flat[i])
                i += 1
        pck.append(0xFF)
    return bytes(pck), bytes(tab)


def check_pck(pck, tab, frames):
    """Обратное чтение так, как читает игра (xcom_sprites.read_pck): кадр в кадр (R-443)."""
    import tempfile
    sys.path.insert(0, os.path.join(ROOT, "tools", "hdart"))
    import xcom_sprites as XS
    with tempfile.TemporaryDirectory() as d:
        p, t = os.path.join(d, "x.PCK"), os.path.join(d, "x.TAB")
        open(p, "wb").write(pck)
        open(t, "wb").write(tab)
        back = XS.read_pck(p, t)
    bad = [i for i, (a, b) in enumerate(zip(frames, back)) if a != b]
    if bad or len(back) != len(frames):
        sys.exit("PCK не читается обратно: кадры %s" % bad)


def install(args):
    files, _ = data()
    lay = json.load(open(os.path.join(SHEET, "layout.json"), encoding="utf-8-sig"))
    sheet = Image.open(os.path.join(SHEET, "original.png"))
    names = [f[0] for f in FRAMES]
    frames = []
    for i in range(len(FRAMES)):
        r, c = divmod(i, COLS)
        x, y = MARGIN + c * (FW + 2 * MARGIN), MARGIN + r * (FH + 2 * MARGIN)
        px = list(sheet.crop((x, y, x + FW, y + FH)).getdata())
        frames.append([px[k * FW:(k + 1) * FW] for k in range(FH)])
    pck, tab = encode_pck(frames)
    check_pck(pck, tab, frames)
    mcd = bytearray()
    for name, tu, armor, loft, tlev, die in RECORDS:
        fi = names.index(name)
        b = mcd_record(files, FRAMES[fi][3])
        for k in range(8):
            b[k] = fi
        if loft is not None:
            for k in range(12):
                b[8 + k] = loft[k] if k < len(loft) else 0
        if tu is not None:
            b[39] = b[40] = b[41] = tu
        if armor is not None:
            b[42] = armor
        b[44] = die or 0                            # Die_MCD
        b[46] = 0                                   # Alt_MCD
        if tlev is not None:
            b[48] = tlev & 0xFF                     # T_Level
        b[45], b[57] = 255, 0                       # Flammable, Fuel: камень не горит
        b[53] = 3                                   # Tile_Type: объект
        b[30] = b[35] = b[34] = 0                   # UFO_Door, Door, Gravlift
        b[59] = b[58] = 0                           # Target_Type, Light_Source
        mcd += b
    hd_src = {}
    for i, (name, how, tex_rec, _, _) in enumerate(FRAMES):
        if how == "copy":
            b = mcd_record(files, tex_rec)
            s = tex_rec.split(":")[0]
            hd_src[i] = os.path.join("user/mods/hd/hd/TERRAIN", s + ".PCK", "%d.png" % b[0])
        elif not args.classic:
            hd_src[i] = os.path.join(args.hd, "%d_strict_cut.png" % i)
    miss = [p for p in hd_src.values() if not os.path.exists(p)]
    if miss:
        sys.exit("нет HD-кадров: " + ", ".join(miss))
    for root in MODS:
        t = os.path.join(root, "TERRAIN")
        os.makedirs(t, exist_ok=True)
        for ext, blob in ((".MCD", bytes(mcd)), (".PCK", pck), (".TAB", tab)):
            with open(os.path.join(t, NAME + ext), "wb") as f:
                f.write(blob)
        hd = os.path.join(root, "hd", "TERRAIN", NAME + ".PCK")
        os.makedirs(hd, exist_ok=True)
        for i in range(len(FRAMES)):  # --classic: рисованных кадров нет, игра берёт классику x4
            if i not in hd_src and os.path.exists(os.path.join(hd, "%d.png" % i)):
                os.remove(os.path.join(hd, "%d.png" % i))
        for i, src in hd_src.items():
            shutil.copyfile(src, os.path.join(hd, "%d.png" % i))
        print(root, "MCD", len(RECORDS), "записей, PCK", len(frames), "кадров, HD", len(hd_src))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sketch")
    p = sub.add_parser("install")
    p.add_argument("--hd", default="art/probe/%s.PCK" % NAME)
    p.add_argument("--classic", action="store_true", help="без рисованных HD-кадров (до генерации)")
    args = ap.parse_args()
    {"sketch": sketch, "install": install}[args.cmd](args)


if __name__ == "__main__":
    main()
