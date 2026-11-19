"""Прозрачное стекло окон в HD-паке террейна (просьба игроков 20.10, слово Vitali «делай всё»).

Окно-стена рисуется после комнаты за ним (Map::drawTerrain: клетки сзади вперёд), а HD-блит честно смешивает
полупрозрачные пиксели (HdCanvas hdRow, a != 255) - значит, полупрозрачное стекло в кадре пака показывает
интерьер без правки движка. Классика (режим 0, k = 1) не участвует.

Какие кадры: перепись стен census/walls - подклассы окон и стекла (wall_classes.tsv), их кадры
(wall_records.tsv, столбец «кадры»). Кадр, который хоть одна запись с MCD stop_los = 1 рисует, не трогаем:
бойцы сквозь такое стекло не видят, и прозрачная картинка показала бы пустую комнату там, где враг может стоять.
Кадры разрушения (die) не трогаем: битое стекло остаётся как нарисовано.

Маска стекла - по классике, а не по цвету HD (кадр пака попиксельно не совпадает с оригиналом, R-284):
  1. лист набора art/TERRAIN/<НАБОР>.PCK/original.png читается индексами (R-043): индекс 0 и tRNS прозрачны;
  2. индексы стекла кадра - те, что в наборе встречаются в основном в кадрах окон (доля >= SHARE), а не
     в глухих стенах; плюс внутри проёма (с материалом слева и справа в строке и сверху и снизу в столбце);
  3. маска x k, сжатая на ERODE пикселей HD от рамы;
  4. в HD внутри маски пиксель - стекло, если по цвету он ближе к цветам стекла классики этого кадра,
     чем к цветам материала (рама, переплёт остаются плотными); блик (ярче стекла на BRIGHT) - плотнее.
Альфа стекла - ALPHA (почти прозрачно), блика - ALPHA_HL; существующая альфа HD умножается.

  glass_alpha.py review [--only НАБОР:кадр ...]    листы до/после в art/_review/glass/ (ничего не пишет в мод)
  glass_alpha.py install --yes                      манифест (build_hd_pack.stage) и обе копии мода hd
Файлы мода - файлы игры: install только держа очередь правок (py -3 tools/editq.py wait).
"""
import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
from collections import Counter, defaultdict

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

import xcom_sprites as xs  # noqa: E402

TAB = "\t"
ENC = "utf-8-sig"
WALLS = os.path.join("census", "walls")
SHEETS = os.path.join("art", "TERRAIN")
GAME = os.path.join("Пиратки", "Dioxine_XPiratez", "user", "mods", "hd", "hd")
REVIEW = os.path.join("art", "_review", "glass")
OVERRIDES = os.path.join("tools", "hdart", "glass_alpha_skip.txt")
OBJECTS = os.path.join("tools", "hdart", "glass_alpha_objects.txt")
GLASS_SUB = ("окно_частично", "окно_рисованное_стекло", "стекло_непробиваемое", "окно_прозрачное")
SHARE = 0.6        # индекс - стекло, если в наборе он в кадрах окон не реже этой доли
ALPHA = 0.28       # непрозрачность стекла (0 - нет стекла, 1 - как было)
ALPHA_HL = 0.6     # непрозрачность блика
BRIGHT = 45        # блик: яркость выше медианы стекла на столько
ERODE = 1          # отступ маски от рамы, пикселей HD
COOL = 30          # холодный цвет классики (стекло любого набора): b - r и (g + b)/2 - r не меньше
OBJ_COOL = 12      # объект из списка: стекло HD - синий выше красного хотя бы на столько...
OBJ_DARK = 45      # ...и не темнее (шины и тени кабины остаются)
OBJ_PART = 40      # ...и куском не меньше стольких пикселей HD
GLASS_PART = 40    # стекло окна - связными кусками не меньше стольких пикселей HD, мельче - кладка (21.10)
GLASS_DOTS = {"FREIGHTER_AGRARIAN:13"}  # стекло шахматкой в самом HD-кадре: точки и есть стекло, без отбора кусков
VERSION = "glass_alpha.py 21.10 v2"


def tsv(name):
    with open(os.path.join(WALLS, name), encoding=ENC) as f:
        return list(csv.DictReader(f, delimiter=TAB))


def targets():
    """{(набор, кадр): {"sub": подкласс, "los": есть ли stop_los=1, "places": мест}} и кадры окон по наборам."""
    rec = {(r["запись"], r["часть"]): r for r in tsv("wall_records.tsv")}
    out = {}
    for r in tsv("wall_classes.tsv"):
        if r["подкласс"] not in GLASS_SUB:
            continue
        rr = rec[(r["запись"], r["часть"])]
        s = r["запись"].split(":")[0]
        for f in set(rr["кадры"].split()):
            t = out.setdefault((s, int(f)), {"sub": r["подкласс"], "los": False, "places": 0, "records": []})
            t["los"] |= rr["stop_los"] == "1"
            t["places"] += int(r["мест"])
            t["records"].append(r["запись"] + "/" + r["часть"])
    # кадр, который рисует и запись вне окон с stop_los = 1, тоже закрыт для взгляда
    for (rk, part), rr in rec.items():
        s = rk.split(":")[0]
        for f in set(rr["кадры"].split()):
            if (s, int(f)) in out and rr["stop_los"] == "1":
                out[(s, int(f))]["los"] = True
    return out


class SetSheet:
    """Классика набора по индексам (R-043): кадры - массивы индексов, 0 и tRNS прозрачны."""

    def __init__(self, s):
        d = os.path.join(SHEETS, s + ".PCK")
        lay = json.load(open(os.path.join(d, "layout.json"), encoding=ENC))
        self.sheet = xs.Sheet(lay["frame_w"], lay["frame_h"], lay["count"], lay["columns"], lay["margin"])
        im = Image.open(os.path.join(d, "original.png"))
        if im.mode != "P":
            raise SystemExit("лист не в индексах: %s" % d)
        self.idx = np.array(im)
        pal = im.getpalette() or []
        pal = pal + [0] * (768 - len(pal))
        self.pal = np.array(pal[:768], dtype=np.int32).reshape(256, 3)
        self.clear = {0}
        t = im.info.get("transparency")
        if isinstance(t, int):
            self.clear.add(t)
        elif isinstance(t, (bytes, bytearray)):
            self.clear |= {i for i, a in enumerate(t) if a == 0}
        self.count = lay["count"]
        # холодный цвет - синее, бирюзовое, зелёно-бирюзовое стекло: синий заметно выше красного
        r, g, b = self.pal[:, 0], self.pal[:, 1], self.pal[:, 2]
        self.cool = (b >= r + COOL) & (g + b >= 2 * r + COOL)

    def frame(self, f):
        x, y, w, h = self.sheet.cell(f)
        return self.idx[y:y + h, x:x + w]

    def opaque(self, fr):
        return ~np.isin(fr, list(self.clear))


def inside(mat):
    """Пиксели проёма: материал есть и слева и справа в строке, и сверху и снизу в столбце."""
    left = np.maximum.accumulate(mat, axis=1)
    right = np.maximum.accumulate(mat[:, ::-1], axis=1)[:, ::-1]
    up = np.maximum.accumulate(mat, axis=0)
    down = np.maximum.accumulate(mat[::-1], axis=0)[::-1]
    return left & right & up & down


def glass_indices(ss, window_frames):
    """Индексы, которые в наборе живут в основном в кадрах окон."""
    inwin, total = Counter(), Counter()
    for f in range(ss.count):
        fr = ss.frame(f)
        c = Counter(fr[ss.opaque(fr)].tolist())
        total.update(c)
        if f in window_frames:
            inwin.update(c)
    return {i for i, n in inwin.items() if n >= SHARE * total[i]}


def classic_mask(ss, f, gidx):
    """-> (кадр, маска стекла, материал, растр). Стекло - проём рамы: индексы стекла и прозрачные пиксели
    между материалом (классика рисует стекло растром с дырками - индекс 0 через пиксель)."""
    fr = ss.frame(f)
    op = ss.opaque(fr)
    gi = op & (np.isin(fr, list(gidx)) | ss.cool[fr])
    mat = op & ~gi
    ins = inside(mat) & ~mat
    holes = ins & ~op
    g = ins & (gi | holes)
    # растр: дырки стекла чередуются с пикселями стекла; одиночный пустой проём - не стекло
    dither = bool(holes.any()) and gi[ins].sum() >= 0.25 * holes.sum()
    if dither:
        g = ins     # растр: весь проём рамы, а плотное от стекла в HD отделит цвет (apply)
    else:
        g = ins & gi
    return fr, g, mat, dither


def erode(m, n):
    for _ in range(n):
        e = m.copy()
        e[1:, :] &= m[:-1, :]
        e[:-1, :] &= m[1:, :]
        e[:, 1:] &= m[:, :-1]
        e[:, :-1] &= m[:, 1:]
        m = e
    return m


def apply(hd, ss, fr, g, mat, dither=False, least=GLASS_PART):
    """-> (новый RGBA-массив, число пикселей стекла). hd - RGBA uint8 HxWx4 кадра пака."""
    k = hd.shape[1] // fr.shape[1]
    if k < 1 or hd.shape[0] != fr.shape[0] * k:
        return None, 0
    if not g.any():
        return hd, 0
    gm = erode(np.kron(g, np.ones((k, k), dtype=bool)), ERODE)
    rgb = hd[..., :3].astype(np.float32)
    a = hd[..., 3].astype(np.float32)
    sel = gm & (a > 0)
    if not sel.any():
        return hd, 0
    px = rgb[sel]
    gcol = ss.pal[np.unique(fr[g & ss.opaque(fr)])].astype(np.float32).reshape(-1, 3)
    if dither or not len(gcol):
        # растровое стекло: классика даёт мало цвета - образец стекла берётся из самого HD-проёма
        gcol = np.vstack([gcol, np.median(px, axis=0)[None]])
    mcol = ss.pal[np.unique(fr[mat])].astype(np.float32) if mat.any() else np.zeros((0, 3), np.float32)
    dg = np.min(((px[:, None, :] - gcol[None]) ** 2).sum(-1), axis=1)
    dm = np.min(((px[:, None, :] - mcol[None]) ** 2).sum(-1), axis=1) if len(mcol) else np.full(len(px), 1e12)
    isg = dg <= dm
    # тёмный кадр: точки кладки ближе к стеклу, чем к раме, - россыпь дыр сквозь стену (XP-000211, BARN_JUNK 13)
    full = np.zeros(sel.shape, dtype=bool)
    full[sel] = isg
    isg = big_parts(full, least)[sel]
    lum = px @ np.array([0.299, 0.587, 0.114], np.float32)
    med = np.median(lum[isg]) if isg.any() else 0
    mul = np.where(isg, np.where(lum > med + BRIGHT, ALPHA_HL, ALPHA), 1.0)
    out = hd.copy()
    na = a[sel] * mul
    out[..., 3][sel] = np.clip(np.round(na), 0, 255).astype(np.uint8)
    return out, int(isg.sum())


def big_parts(m, least):
    """Маска без связных пятен меньше least пикселей (одиночные холодные пиксели на ободе, в тени).
    Связность 4 соседа (как ndimage.label); обход очередью - без scipy, его нет в .venv генерации."""
    h, w = m.shape
    out = np.zeros_like(m, dtype=bool)
    seen = np.zeros_like(m, dtype=bool)
    for y0, x0 in zip(*np.nonzero(m)):
        if seen[y0, x0]:
            continue
        seen[y0, x0] = True
        part, i = [(y0, x0)], 0
        while i < len(part):
            y, x = part[i]
            i += 1
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= ny < h and 0 <= nx < w and m[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    part.append((ny, nx))
        if len(part) >= least:
            ys, xs = zip(*part)
            out[list(ys), list(xs)] = True
    return out


def object_mask(hd, rows=None):
    """Объект из списка (кабина): HD-кадр не повторяет форму классики (трактор нарисован заново), поэтому
    стекло - по цвету самого кадра: холодный оттенок (синий выше красного на OBJ_COOL), не тёмная шина;
    связные куски не меньше OBJ_PART пикселей; rows - (с, по) строки кадра, где стекло (без корпуса ниже)."""
    rgb = hd[..., :3].astype(np.int32)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    isg = (hd[..., 3] > 0) & (b >= r + OBJ_COOL) & (b >= g) & (lum >= OBJ_DARK)
    if rows:
        band = np.zeros_like(isg)
        band[rows[0]:rows[1]] = True
        isg &= band
    return big_parts(isg, OBJ_PART), lum


def apply_object(hd, rows=None):
    isg, lum = object_mask(hd, rows)
    a = hd[..., 3].astype(np.float32)
    if not isg.any():
        return hd, 0
    med = np.median(lum[isg])
    mul = np.where(lum > med + BRIGHT, ALPHA_HL, ALPHA)
    out = hd.copy()
    out[..., 3][isg] = np.clip(np.round(a[isg] * mul[isg]), 0, 255).astype(np.uint8)
    return out, int(isg.sum())


def apply_item(hd, it):
    if it.get("object"):
        return apply_object(hd, it.get("rows"))
    return apply(hd, it["ss"], it["fr"], it["g"], it["mat"], it["dither"],
                 1 if it["key"] in GLASS_DOTS else GLASS_PART)


def hd_files(s, f):
    d = os.path.join(GAME, "TERRAIN", s + ".PCK")
    pat = re.compile(r"^%d(\.v\d+)?\.png$" % f)
    return sorted(os.path.join(d, n) for n in os.listdir(d) if pat.match(n)) if os.path.isdir(d) else []


def load_skip():
    if not os.path.exists(OVERRIDES):
        return set()
    out = set()
    for line in open(OVERRIDES, encoding=ENC):
        line = line.split("#")[0].strip()
        if line:
            out.add(line)
    return out


def load_objects():
    """Объекты со стеклом, выбранные человеком (кабины): {(набор, кадр): строки или None}; «НАБОР:кадр
    [rows=с-по]». Правило stop_los к ним не применяется."""
    out = {}
    if os.path.exists(OBJECTS):
        for line in open(OBJECTS, encoding=ENC):
            line = line.split("#")[0].strip()
            if line:
                head, *opts = line.split()
                s, f = head.rsplit(":", 1)
                rows = None
                for o in opts:
                    if o.startswith("rows="):
                        lo, hi = o[5:].split("-")
                        rows = (int(lo), int(hi))
                out[(s, int(f))] = rows
    return out


def plan(only=None, missed=False):
    tg = targets()
    objects = load_objects()
    for s, f in objects:
        tg[(s, f)] = {"sub": "объект_список", "los": False, "places": 0, "records": []}
    skip = load_skip()
    bysets = defaultdict(set)
    for (s, f) in tg:
        bysets[s].add(f)
    res, why = [], Counter()
    for s in sorted(bysets):
        if not os.path.isdir(os.path.join(SHEETS, s + ".PCK")):
            why["нет листа классики"] += len(bysets[s])
            continue
        ss = SetSheet(s)
        gidx = glass_indices(ss, bysets[s])
        for f in sorted(bysets[s]):
            key = "%s:%d" % (s, f)
            t = tg[(s, f)]
            if only and key not in only:
                continue
            if t["los"]:
                why["stop_los = 1"] += 1
                continue
            if key in skip:
                why["в списке пропуска"] += 1
                continue
            files = hd_files(s, f)
            if not files:
                why["нет HD-кадра"] += 1
                continue
            if (s, f) in objects:
                if not missed:
                    res.append({"key": key, "set": s, "frame": f, "files": files, "ss": ss, "fr": ss.frame(f),
                                "g": None, "mat": None, "dither": False, "object": True, "rows": objects[(s, f)],
                                "t": t})
                continue
            fr, g, mat, dither = classic_mask(ss, f, gidx)
            if not g.any():
                why["стекла в классике нет"] += 1
                if not missed:
                    continue
            elif missed:
                continue
            res.append({"key": key, "set": s, "frame": f, "files": files, "ss": ss, "fr": fr, "g": g, "mat": mat,
                        "dither": dither, "t": t})
    return res, why


def checker(w, h, cell=8):
    """Фон листа - «интерьер»: жёлтые и тёмные косые полосы, ни на одно стекло не похожи."""
    y, x = np.mgrid[0:h, 0:w]
    c = (((x + y) // cell) % 2).astype(bool)
    im = np.zeros((h, w, 3), np.uint8)
    im[c] = (235, 200, 40)
    im[~c] = (50, 40, 30)
    return im


def over(rgba, bg):
    a = rgba[..., 3:4].astype(np.float32) / 255
    return (rgba[..., :3] * a + bg * (1 - a)).astype(np.uint8)


def cmd_review(items, name):
    os.makedirs(REVIEW, exist_ok=True)
    per, cols = 24, 4
    cw, ch = 3 * 128 + 16, 160 + 18
    lines = []
    for p0 in range(0, len(items), per):
        part = items[p0:p0 + per]
        sheet = Image.new("RGB", (cols * cw, ((len(part) + cols - 1) // cols) * ch), (40, 40, 40))
        dr = ImageDraw.Draw(sheet)
        for i, it in enumerate(part):
            hd = np.array(Image.open(it["files"][0]).convert("RGBA"))
            new, n = apply_item(hd, it)
            X, Y = (i % cols) * cw, (i // cols) * ch
            bg = checker(hd.shape[1], hd.shape[0])
            fr = it["fr"]
            cl = np.zeros(fr.shape + (4,), np.uint8)
            cl[..., :3] = it["ss"].pal[fr]
            cl[..., 3] = np.where(it["ss"].opaque(fr), 255, 0)
            if it["g"] is not None:
                cl[it["g"]] = (255, 0, 255, 255)
            k = hd.shape[1] // fr.shape[1]
            clb = over(np.kron(cl, np.ones((k, k, 1), np.uint8)), checker(fr.shape[1] * k, fr.shape[0] * k))
            sheet.paste(Image.fromarray(clb).resize((128, 160), Image.NEAREST), (X, Y + 18))
            sheet.paste(Image.fromarray(over(hd, bg)).resize((128, 160)), (X + 132, Y + 18))
            if new is not None:
                sheet.paste(Image.fromarray(over(new, bg)).resize((128, 160)), (X + 264, Y + 18))
            dr.text((X + 2, Y + 3), "%s  %s  стекла %d" % (it["key"], it["t"]["sub"], n), fill=(255, 255, 0))
            lines.append("%s\t%s\t%d\t%d" % (it["key"], it["t"]["sub"], it["t"]["places"], n))
        out = os.path.join(REVIEW, "%s_%03d.png" % (name, p0 // per))
        sheet.save(out)
        print(out)
    with open(os.path.join(REVIEW, name + "_plan.tsv"), "w", encoding=ENC) as f:
        f.write("кадр\tподкласс\tмест\tпикселей_стекла\n" + "\n".join(lines) + "\n")


def cmd_install(items, yes, approval):
    import build_hd_pack as bp
    os.chdir(ROOT)
    man = bp.load()
    staged = []
    for it in items:
        for path in it["files"]:
            rel = os.path.relpath(path, GAME).replace(os.sep, "/")
            entry = man["files"].get(rel)
            src = Image.open(path).convert("RGBA")
            hd = np.array(src)
            # повторный запуск не множит альфу: исходник - то, что было до прошлой установки стекла
            if entry and entry.get("generator") == "glass_alpha" and entry.get("replaced"):
                prev = bp.blob_path(entry["replaced"], rel)
                hd = np.array(Image.open(prev).convert("RGBA"))
            new, n = apply_item(hd, it)
            if new is not None and n == 0 and entry and entry.get("generator") == "glass_alpha" \
                    and entry.get("replaced") and entry.get("sha256") != entry["replaced"]:
                # стекла больше нет (были одни пятна) - вернуть кадр, каким он был до прошлой установки
                staged.append((rel, open(prev, "rb").read(), 0, entry))
                continue
            if new is None or n == 0:
                continue
            buf = io.BytesIO()
            Image.fromarray(new, "RGBA").save(buf, "PNG", optimize=True)
            staged.append((rel, buf.getvalue(), n, entry))
    print("кадров к записи %d (файлов с вариантами)" % len(staged))
    if not yes:
        raise SystemExit("сухой прогон; --yes - записать")
    rels = []
    for rel, data, n, entry in staged:
        old = entry.get("sha256") if entry else None
        if entry and entry.get("generator") == "glass_alpha" and entry.get("replaced"):
            old = entry["replaced"]
        bp.stage(man, rel, data, generator="glass_alpha", generator_version=VERSION,
                 source_path=None, approved=True, approval=approval,
                 derived_from=old, source_frame=rel.split("/")[1].replace(".PCK", "") + ":" + rel.split("/")[2].split(".")[0],
                 note="стекло окна полупрозрачно: %d пикселей, альфа %.2f" % (n, ALPHA))
        if old:
            man["files"][rel]["replaced"] = old
        rels.append(rel)
    bp.save(man, why="glass_alpha: %d файлов окон" % len(rels))
    print("game:", bp.install(man, "game", only=rels))
    print("repo:", bp.install(man, "repo", only=rels))
    bad = 0
    for r in rels:
        for root in (bp.TARGETS["game"], bp.TARGETS["repo"]):
            p = os.path.join(root, r)
            if not os.path.exists(p) or hashlib.sha256(open(p, "rb").read()).hexdigest() != man["files"][r]["sha256"]:
                print("РАСХОДИТСЯ", root, r)
                bad += 1
    print("сверка: расхождений", bad)
    sys.exit(1 if bad else 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["review", "install"])
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--missed", action="store_true", help="review: кадры окон, где стекла в классике не нашлось")
    ap.add_argument("--approval", default="Vitali 20.10: «делай всё» (прозрачные стёкла)")
    a = ap.parse_args()
    os.chdir(ROOT)
    sys.stdout.reconfigure(encoding="utf-8")
    items, why = plan(set(a.only) if a.only else None, a.missed and a.cmd == "review")
    print("к обработке %d кадров; пропущено: %s" % (len(items), dict(why)))
    if a.cmd == "review":
        cmd_review(items, "missed" if a.missed else "glass")
    else:
        cmd_install(items, a.yes, a.approval)


if __name__ == "__main__":
    main()
