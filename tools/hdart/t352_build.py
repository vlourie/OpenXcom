# -*- coding: utf-8 -*-
r"""XP-000352 (выбор Vitali: вариант A по обоим пунктам): готовые кадры ROADS_WASTE 0-8 (кромка шоссе) и 18/19
(трещины и воронки; побайтные копии XOPSDESERTRUINS 37 = 18, 38 = 19). Процедурно, без видеокарты, ничего в мод
не ставит (установка - t352_install.py). Вывод - art/_review/tickets_2026-10-28/t352_install/TERRAIN/... + MANIFEST.json.

  1-8  t249_asphalt_edge.build (маска классики x4, асфальт HD ROADS_WASTE:9, песок HD URBITS_WASTE:16, затенение
       песка у кромки по классике, альфа - силуэт классики + точный ромб, R-247). 5 и 6 - зеркало с перекраской
       друг друга, каждый строится по СВОЕЙ маске классики.
  0    щебёнка: кадр классики - сплошная смесь серого (индексы 9-14), песка (85-94) и тёмного асфальта (244-251).
       Камешки Вороного (шаг ~5.5 пикс HD, свой посев): класс и яркость камешка - по классике в его центре,
       фактура - серый камень (асфальт 9 + светлая крупа), песок 16 или асфальт 9; грань камешка с купольным
       светом сверху-слева, щель между камешками темнее; зерно асфальта 9 поверх. Тёмных клякс нет: щели не темнее
       асфальта 9 x0.6.
  18,19 трещины и воронки: основа - текстура асфальта 9 (зерно и тон), поверх множитель по цветам классики
       (яркость и красноватый тон трещин из классики, контур с шумовым сдвигом, чтобы не было блоков), затухающий
       к кромке ромба (шов с соседним асфальтом 9 не виден); средний тон кадра подтянут к асфальту 9.
       Альфа - как у кадров 1-8 (силуэт классики + точный ромб).

    py -3.13 tools\hdart\t352_build.py            # кадры + манифест
    py -3.13 tools\hdart\t352_build.py --sheet    # + лист t352_B_sheet.png и замер швов
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ground_seam as gs                  # noqa: E402
import t249_asphalt_edge as t249          # noqa: E402  (кандидат 1-8; файл надо коммитить вместе с этим)
import ticket_scene as ts                 # noqa: E402
import water_build as wb                  # noqa: E402

ROOT = HERE.parent.parent
REVIEW = ROOT / "art" / "_review" / "tickets_2026-10-28"
INST = REVIEW / "t352_install"
SET = "ROADS_WASTE"
COPIES = {18: ("XOPSDESERTRUINS", 37), 19: ("XOPSDESERTRUINS", 38)}   # побайтные копии (ticket_family.py)
SEED0 = 35201
PEB = 5.6                      # шаг камешков кадра 0, пикс HD
CR_LOW, CR_HIGH = 0.3, 1.5     # предел яркости множителя трещин: чернот и свечения нет
CR_CHROMA = 0.6                # доля красноватости классики
CR_GAIN = 1.0                  # сила множителя трещин 18/19 относительно классики
CR_EDGE = 7.0                  # затухание трещин к кромке ромба, пикс HD
CR_MEAN = 0.93                 # средний тон кадра 18/19 не темнее асфальта 9 x0.93


def _pal():
    return wb.palette()[:, :3].astype(np.float32)


def _up(arr, k=4):
    return np.kron(arr, np.ones((k, k) + (1,) * (arr.ndim - 2), arr.dtype))


def _smooth_up(rgb40x32, sig, warp=None):
    """Классика (40x32x3) -> 160x128, билинейно с размытием sig (пикс HD), с шумовым сдвигом warp=(dx,dy)."""
    h, w = rgb40x32.shape[:2]
    out = []
    ys, xs = np.mgrid[0:160, 0:128].astype(np.float32)
    sy = (ys + 0.5) / 4 - 0.5
    sx = (xs + 0.5) / 4 - 0.5
    if warp is not None:
        sx = sx + warp[0] / 4
        sy = sy + warp[1] / 4
    for c in range(rgb40x32.shape[2]):
        v = ndi.map_coordinates(rgb40x32[..., c], [sy, sx], order=1, mode="nearest")
        out.append(ndi.gaussian_filter(v, sig) if sig > 0 else v)
    return np.dstack(out)


def _extend_known(a):
    """Индексы классики; за силуэтом - ближайший известный (для кадров 0, 18, 19 силуэт полный ромб)."""
    known = a > 0
    idx = ndi.distance_transform_edt(~known, return_distances=False, return_indices=True)
    return a[idx[0], idx[1]]


def _noise(seed, sig):
    g = np.random.RandomState(seed).randn(160, 128).astype(np.float32)
    g = ndi.gaussian_filter(g, sig, mode="wrap")
    return g / (g.std() + 1e-6)


def _grain(t, sig=2.5):
    """Высокие частоты текстуры (она минус размытие), по каналам."""
    return t - np.dstack([ndi.gaussian_filter(t[..., i], sig, mode="nearest") for i in range(3)])


def build0(tex_asph, tex_sand):
    pal = _pal()
    a = wb.read_set(SET)[0]
    ae = _extend_known(a)
    ref9 = float((pal[wb.read_set(SET)[9][wb.read_set(SET)[9] > 0]] @ gs.LUMA).mean())
    sand_ref = t249.sand_ref_luma(wb.palette())
    rs = np.random.RandomState(SEED0)
    # точки Вороного: сетка со сдвигом рядов и шумом
    pts = []
    for j, y in enumerate(np.arange(-4, 168, PEB * 0.87)):
        for x in np.arange(-6 + (PEB / 2 if j % 2 else 0), 134, PEB):
            pts.append((x + rs.uniform(-0.38, 0.38) * PEB, y + rs.uniform(-0.38, 0.38) * PEB))
    pts = np.array(pts, np.float32)
    from scipy.spatial import cKDTree
    tr = cKDTree(pts)
    yy, xx = np.mgrid[0:160, 0:128].astype(np.float32)
    # искажение расстояния шумом: камешки неровные
    wx = _noise(SEED0 + 1, 3.0) * 1.1
    wy = _noise(SEED0 + 2, 3.0) * 1.1
    q = np.stack([(xx + wx).ravel(), (yy + wy).ravel()], 1)
    d2, lab = tr.query(q, k=2)
    lab = lab[:, 0]
    d1, dsec = d2[:, 0], d2[:, 1]
    d1 = d1.reshape(160, 128)
    dsec = dsec.reshape(160, 128)
    lab = lab.reshape(160, 128)
    # класс и яркость камешка - по классике в центре
    cx = np.clip((pts[:, 0] / 4).astype(int), 0, 31)
    cy = np.clip((pts[:, 1] / 4).astype(int), 0, 39)
    idx = ae[cy, cx]
    sand = (idx >= 85) & (idx <= 94)
    gray = (idx >= 9) & (idx <= 14)
    cl_luma = pal[idx] @ gs.LUMA
    jit = 1.0 + rs.uniform(-0.12, 0.12, len(pts))
    # цвет камешка по классу
    cls = np.where(sand, 1, np.where(gray, 2, 0))
    pc = cls[lab]
    pl = (cl_luma * jit)[lab]
    # фактуры: песок, асфальт 9, серый камень = асфальт 9 + светлая крупа
    t_gray = tex_asph * 1.0
    gray_rgb = np.dstack([ndi.gaussian_filter(t_gray[..., i], 4.0, mode="wrap") for i in range(3)])
    gtone = np.clip(pl / 70.0, 0.25, 1.15)[..., None]
    # серый камень: нейтральный серый классики, чуть теплее (в сцене всё красноватое), + зерно асфальта 9
    cool = np.array([1.0, 0.93, 0.95], np.float32)
    rgb_gray = (pl[..., None] * 0.95 * cool) + 0.8 * _grain(tex_asph, 1.6)
    rgb_sand = tex_sand * np.clip(pl / sand_ref, 0.3, 1.1)[..., None]
    rgb_asph = tex_asph * 1.0 + 0.0 * gtone + 0.0 * gray_rgb
    rgb = np.where((pc == 1)[..., None], rgb_sand, np.where((pc == 2)[..., None], rgb_gray, rgb_asph))
    # объём камешка: купол (свет сверху-слева) и тёмная щель по границе
    r = np.maximum(PEB * 0.55, 1.0)
    cxy = pts[lab]
    dx = (xx - cxy[..., 0]) / r
    dy = (yy - cxy[..., 1]) / r
    dome = 1.0 - 0.5 * np.clip(d1 / (PEB * 0.6), 0, 1.2) ** 2
    lit = 1.0 + 0.30 * (-(dx + dy) * 0.7) * np.clip(1.2 - d1 / (PEB * 0.6), 0, 1)
    gap = np.clip((dsec - d1) / 1.6, 0, 1)                  # 0 на границе, 1 внутри
    shade = lit * (0.55 + 0.45 * gap) * (0.88 + 0.12 * dome)
    # щель - к асфальту 9 (не чернота)
    asph_dark = tex_asph * 0.75
    rgb = rgb * shade[..., None]
    rgb = np.where(gap[..., None] < 1.0, rgb * gap[..., None] + asph_dark * (1 - gap[..., None]), rgb)
    rgb = ndi.gaussian_filter(rgb, (0.55, 0.55, 0))
    # мелкое зерно по яркости классики
    rgb = rgb + 0.55 * _grain(tex_asph, 1.2) * np.clip((rgb @ gs.LUMA) / 60.0, 0.4, 1.6)[..., None]
    # средний цвет кадра - как у классики (купол и щели иначе делают щебёнку темнее на треть)
    inside = gs.dmap() < 0.96
    want = pal[a[a > 0]].mean(0)
    gain = np.clip(want / np.maximum(rgb[inside].mean(0), 1e-3), 0.8, 1.8)
    rgb = rgb * gain
    al = gs.classic_alpha(a)
    out = np.dstack([np.clip(rgb, 0, 255), al * 255]).round().astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def build_crack(f, tex_asph):
    pal = _pal()
    a = wb.read_set(SET)[f]
    a9 = wb.read_set(SET)[9]
    m9 = pal[a9[a9 > 0]].mean(0)                          # средний цвет асфальта 9 в классике
    ae = _extend_known(a)
    c = pal[ae]
    yc = np.maximum(c @ gs.LUMA, 1.0)
    y9 = float(m9 @ gs.LUMA)
    lr = np.clip(yc / y9, CR_LOW, CR_HIGH)                # яркость классики к асфальту 9, без чернот и свечения
    chroma = np.clip((c / yc[..., None]) / (m9 / y9), 0.7, 1.7) ** CR_CHROMA   # красноватость классики
    ratio = lr[..., None] * chroma
    warp = (_noise(SEED0 + 10 + f, 2.6) * 2.4, _noise(SEED0 + 20 + f, 2.6) * 2.4)
    rup = _smooth_up(ratio, 0.8, warp)
    r = 1.0 + CR_GAIN * (rup - 1.0)
    # затухание к кромке ромба
    d = gs.dmap()
    edge = np.clip((1.0 - d) * 64 / CR_EDGE, 0, 1)
    w = edge * edge * (3 - 2 * edge)
    r = 1.0 + (r - 1.0) * w[..., None]
    rgb = tex_asph * r
    # средний тон - близко к асфальту 9
    inside = d < 0.96
    m_new = rgb[inside].mean(0)
    m_tex = tex_asph[inside].mean(0)
    low = (m_tex * CR_MEAN) / np.maximum(m_new, 1e-3)
    gain = np.where(low > 1, low, 1.0)
    rgb = rgb * gain
    al = gs.classic_alpha(a)
    out = np.dstack([np.clip(rgb, 0, 255), al * 255]).round().astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def build_all():
    pal = wb.palette()
    ref = t249.sand_ref_luma(pal)
    tex = (t249.extend(t249.load_hd(*t249.ASPH_SRC)), t249.extend(t249.load_hd(*t249.SAND_SRC)))
    res = {f: t249.build(f, tex, ref) for f in range(1, 9)}
    res[0] = build0(*tex)
    for f in (18, 19):
        res[f] = build_crack(f, tex[0])
    return res


def save_all(res):
    files = {}
    for f, im in sorted(res.items()):
        rel = "TERRAIN/%s.PCK/%d.png" % (SET, f)
        p = INST / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        im.save(p, optimize=True)
        files[rel] = p
        if f in COPIES:
            s2, n2 = COPIES[f]
            rel2 = "TERRAIN/%s.PCK/%d.png" % (s2, n2)
            p2 = INST / rel2
            p2.parent.mkdir(parents=True, exist_ok=True)
            im.save(p2, optimize=True)
            files[rel2] = p2
    man = {"ticket": "XP-000352", "generator": "t352_build.py", "variant": "A",
           "note": "ROADS_WASTE 0-8 кромка шоссе, 18/19 трещины; XOPSDESERTRUINS 37/38 - побайтные копии 18/19",
           "files": {r: hashlib.sha256(p.read_bytes()).hexdigest() for r, p in files.items()}}
    (INST / "MANIFEST.json").write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8-sig")
    return files


# ---------------------------------------------------------------- лист для Vitali и проверка швов
SHEET = REVIEW / "t352_B_sheet.png"
BR = 1.8                                  # яркость листа (кадры тёмные), одинакова для классики, сейчас и нового
BGC = (30, 30, 34)


def _bright(im, k=BR):
    a = np.asarray(im.convert("RGB")).astype(np.float32) * k
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def _flat_scene(res):
    """Сцена, где каждый кадр - плоский цвет с номером (для карты владения пикселей); кадры res - из res."""
    sc = ts.Scene()
    ids = {}

    def hd(s, f, var=0):
        if var:
            return None
        key = (s, f)
        if key not in ids:
            ids[key] = len(ids) + 1
        base = Image.open(ts.PACK / (s + ".PCK") / ("%d.png" % f)).convert("RGBA") if (s, f) not in res else res[(s, f)]
        a = np.asarray(base)[..., 3]
        out = np.zeros(a.shape + (4,), np.uint8)
        out[..., 0] = 40 + ids[key]
        out[..., 3] = np.where(a > 127, 255, 0)
        return Image.fromarray(out, "RGBA")
    sc.hd = hd
    return sc, ids


def seam_report(block, over, k=4, only=(0, 1, 2, 3, 4, 5, 6, 7, 8, 18, 19)):
    """Шов: средний |dY| между соседними пикселями РАЗНЫХ клеток-кадров (с участием кадров 0-8, 18, 19) против
    среднего |dY| внутри кадра. Считается по сцене блока, как рисует движок (без смешения пятен groundFrameFor)."""
    sc2, ids = _flat_scene(over)
    flat_over = {}
    for key in over:
        flat_over[key] = sc2.hd(key[0], key[1])
    own, _ = sc2.render("URBAN_WASTE", block, "hd", override=flat_over, k=k, maxz=0)
    own = np.asarray(own.convert("RGBA"))[..., 0].astype(int)
    inv = {40 + v: key for key, v in ids.items()}
    out = {}
    for tag, ov in (("сейчас", None), ("новое", over)):
        im, _ = ts.Scene().render("URBAN_WASTE", block, "hd", override=ov, k=k, maxz=0)
        y = np.asarray(im.convert("RGB")).astype(np.float32) @ gs.LUMA
        acc = {}
        for dy, dx in ((0, 1), (1, 0)):
            a = own[: own.shape[0] - dy, : own.shape[1] - dx]
            b = own[dy:, dx:]
            ya = y[: y.shape[0] - dy, : y.shape[1] - dx]
            yb = y[dy:, dx:]
            ok = (a > 40) & (b > 40)
            d = np.abs(ya - yb)
            sel = np.zeros_like(ok)
            for v, (s_, f_) in inv.items():
                if s_ == SET and f_ in only:
                    sel |= (a == v) | (b == v)
            for mat, lo, hi in (("асфальт", 0, 45), ("песок", 70, 999)):
                same_m = ok & (ya >= lo) & (ya < hi) & (yb >= lo) & (yb < hi)
                acc.setdefault((mat, "стык"), []).append(d[same_m & (a != b) & sel])
                acc.setdefault((mat, "внутри"), []).append(d[same_m & (a == b)])
        out[tag] = {k_: (float(np.concatenate(v).mean()) if len(np.concatenate(v)) else 0.0, int(len(np.concatenate(v)))) for k_, v in acc.items()}
    return out


def _grid_scene(sc, over, k=4, n=5):
    """Сцена n x n клеток асфальта ROADS_WASTE 9 (вариантов нет: только основа) с 18 и 19 внутри."""
    put = {(1, 1): 18, (3, 3): 18, (2, 3): 19, (3, 1): 19, (1, 3): 19}
    W = (2 * n) * 16 * k + 32 * k
    H = (2 * n) * 8 * k + 48 * k
    out = []
    for tag in ("классика", "HD сейчас", "новое"):
        im = Image.new("RGBA", (W, H), BGC + (255,))
        for y in range(n):
            for x in range(n):
                f = put.get((x, y), 9)
                if tag == "классика":
                    spr = sc.classic(SET, f)
                elif tag == "HD сейчас":
                    spr = sc.hd(SET, f)
                else:
                    spr = over.get((SET, f)) or sc.hd(SET, f)
                if spr.width != 32 * k:
                    spr = spr.resize((32 * k, 40 * k), Image.NEAREST if tag == "классика" else Image.LANCZOS)
                px = n * 16 + (x - y) * 16
                py = (x + y) * 8
                im.alpha_composite(spr, (px * k, py * k))
        out.append((tag, im.crop((0, 40 * k, W, H - 16 * k))))
    return out


def make_sheet(res):
    sc = ts.Scene()
    over = {(SET, f): im for f, im in res.items()}
    frames = [0, 1, 2, 3, 4, 5, 6, 7, 8, 18, 19]
    z = 2.2
    box = (0, 92, 128, 160)
    cols = []
    for f in frames:
        col = Image.new("RGB", (int(128 * z), int(68 * z) * 3 + 8), (12, 12, 14))
        for j, im in enumerate((sc.classic(SET, f), sc.hd(SET, f), res[f])):
            c = Image.new("RGBA", (128, 160), BGC + (255,))
            c.alpha_composite(im.convert("RGBA"))
            c = c.crop(box).resize((int(128 * z), int(68 * z)), Image.NEAREST if j == 0 else Image.LANCZOS)
            col.paste(_bright(c), (0, j * (int(68 * z) + 4)))
        cols.append(ts.label(col, "%s:%d" % (SET[:5], f) + (" =XOPS %d" % COPIES[f][1] if f in COPIES else ""), 15))
    gap = 6
    row1 = Image.new("RGB", (sum(c.width for c in cols) + gap * (len(cols) + 1), cols[0].height + 2 * gap), (12, 12, 14))
    x = gap
    for c in cols:
        row1.paste(c, (x, gap))
        x += c.width + gap
    row1 = ts.label(_pad_top(row1, 24), "кадры: сверху классика, середина HD сейчас (sdxl_legacy 21.09), снизу новое (t352_build.py, процедурно). Яркость x%.1f" % BR, 17)

    def scene_row(block, box4, title, width=1050):
        ims = []
        for tag, ov in (("классика", None), ("HD сейчас", None), ("новое (не одобрено)", over)):
            mode = "classic" if tag == "классика" else "hd"
            im, _ = sc.render("URBAN_WASTE", block, mode, override=ov, k=4, maxz=0)
            im = im.convert("RGB").crop(box4)
            im = im.resize((width, int(im.height * width / im.width)), Image.LANCZOS)
            ims.append(ts.label(_bright(im), "%s, %s, яркость x%.1f" % (tag, block[-4:], BR), 17))
        return _hrow(ims)

    row2 = scene_row("URBANWASTEROAD_NS08", (53, 507, 1347, 1160), "NS08")
    row3 = scene_row("URBANWASTEROAD_WE01", _crack_box(sc, "URBANWASTEROAD_WE01"), "WE01")
    g = _grid_scene(sc, over)
    gi = []
    for tag, im in g:
        im = im.convert("RGB")
        im = im.resize((1050, int(im.height * 1050 / im.width)), Image.LANCZOS if tag != "классика" else Image.NEAREST)
        gi.append(ts.label(_bright(im), "%s: асфальт 9 + трещины 18/19 (3 шт. по 19, 2 по 18), x%.1f" % (tag, BR), 17))
    row4 = _hrow(gi)
    W = max(r.width for r in (row1, row2, row3, row4))
    H = sum(r.height for r in (row1, row2, row3, row4)) + 30
    sheet = Image.new("RGB", (W, H), (12, 12, 14))
    y = 6
    for r in (row1, row2, row3, row4):
        sheet.paste(r, (0, y))
        y += r.height + 6
    sheet.save(SHEET)
    return SHEET, sheet.size


def _pad_top(im, n):
    out = Image.new("RGB", (im.width, im.height + n), (12, 12, 14))
    out.paste(im, (0, n))
    return out


def _hrow(ims, gap=6):
    row = Image.new("RGB", (sum(i.width for i in ims) + gap * (len(ims) + 1), max(i.height for i in ims) + 2 * gap), (12, 12, 14))
    x = gap
    for i in ims:
        row.paste(i, (x, gap))
        x += i.width + gap
    return row


def _crack_box(sc, block, w=1294, h=650):
    _im, found = sc.render("URBAN_WASTE", block, "classic", k=4, maxz=0, marks={(SET, 18), (SET, 19)})
    xs = [(f[2][0] + f[2][2]) / 2 for f in found]
    ys = [(f[2][1] + f[2][3]) / 2 for f in found]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    return (int(cx - w / 2), int(cy - h / 2), int(cx + w / 2), int(cy + h / 2))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sheet = "--sheet" in sys.argv
    res = build_all()
    files = save_all(res)
    print("кадров: %d, файлов: %d -> %s" % (len(res), len(files), INST))
    if sheet:
        over = {(SET, f): im for f, im in res.items()}
        for blk in ("URBANWASTEROAD_NS08", "URBANWASTEROAD_WE01"):
            for nm, only in (("все", (0, 1, 2, 3, 4, 5, 6, 7, 8, 18, 19)), ("1-8", tuple(range(1, 9))), ("0", (0,)), ("18/19", (18, 19))):
                r = seam_report(blk, over, only=only)
                for tag, d in r.items():
                    print("шов %s кадры %s, %s: " % (blk[-4:], nm, tag) + "; ".join("%s %s dY=%.2f (%d)" % (m, w, v[0], v[1]) for (m, w), v in sorted(d.items())))
        print("лист: %s %s" % make_sheet(res))


if __name__ == "__main__":
    main()
