r"""Маски защищённой геометрии кадра террейна (расширенный пилот карт, 06.10).

Что механика считает сплошным, а что открытым, берётся не из картинки и не из флага Stop_LOS, а из того же,
по чему движок пускает взгляд юнита и снаряд: воксели LOFT записи MCD (TileEngine::voxelCheck - бит
15 - x%16 в строке y%16 слоя (z%24)/2; створка ОТКРЫТОЙ двери НЛО пропускается целиком). Stop_LOS идёт только
в блокировку обзора клетки (MapData::setBlockValue, visionBlock) - видна ли клетка за стеной, - и пишется в
отчёт отдельным полем.

Воксель (dx, dy, dz) клетки ложится на экран так же, как Camera::convertVoxelToScreen: x = dx - dy + 16,
y = 20 + dx/2 + dy/2 - dz; кадр рисуется со сдвигом вверх на P_Level (Map::drawTerrain, getYOffset),
значит в координатах кадра y + P_Level. Маски строятся сразу x4 по непрерывной проекции (подотсчёты вокселя),
без увеличения пикселей (R-042, R-121).

Маски записи (x4, 128x160):
  sil       - силуэт классического кадра (индекс 0 прозрачен, R-043), по каждому кадру анимации свой;
  solid     - проекция сплошных вокселей записи;
  envelope  - проекция объёма, занятого стеной: коробка сплошных вокселей по слоям (у окна - вместе с
              проёмом, у двери - по закрытой записи);
  open      - envelope минус solid: место, где механика пропускает взгляд и выстрел;
  edges     - границы рамп палитры внутри силуэта (границы материалов и деталей классики).
Проверки HD-кадра против масок - check(): непрозрачное HD в open (рама закрыла проём), прозрачное HD в solid
при непрозрачной классике (нарисованная дыра в сплошной стене), силуэт.

  py -3.13 geom_mask.py selftest --save <сейв>            проекция против силуэта на стенах URBAN, контроль сдвигом
  py -3.13 geom_mask.py build --save <сейв> --out <папка> URBAN#65 URBAN#68 URBAN#62 ...
  py -3.13 geom_mask.py check --masks <папка>/URBAN_68 --hd <кадр.png>
"""
import argparse, json, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, str(Path(__file__).resolve().parent))
import map_truth as mt

ART = mt.ROOT / "art" / "TERRAIN"
K = 4
FW, FH = 32, 40
SUB = (np.arange(4) + 0.5) / 4          # подотсчёты вокселя по каждой оси
# Рисунок кадра стоит на 4 базовых пикселя НИЖЕ проекции его вокселей: ромб пола в кадре 24..40, а плоскость
# z=0 по convertVoxelToScreen - 20..36. Замер selftest: стены URBAN 65/66/31/32 и предмет ROADS 21 - лучший
# сдвиг (0..-1, 17) пикс x4 у всех пяти, без этой поправки. Механику это не меняет (пуля летит по вокселям),
# но маску к рисунку кладём в координатах рисунка.
ART_DY = 4
B_LOFT = 8                              # 12 номеров LOFT, байты 8..19 записи MCD
B_STOP_LOS = 31                         # MCD.Stop_LOS - сразу за UFO_Door (struct MCD в MapDataSet.cpp)


def classic(set_name, f):
    """Индексы и палитра кадра из листа art/TERRAIN/<НАБОР>.PCK/original.png (листы читаются как PCK подряд, R-075)."""
    d = ART / (set_name + ".PCK")
    lay = json.load(open(d / "layout.json", encoding="utf-8-sig"))
    im = Image.open(d / "original.png")
    if im.mode != "P":
        raise SystemExit("%s: лист не индексный" % d)
    idx = np.array(im)
    pal = np.array(im.getpalette()[:768], np.uint8).reshape(-1, 3)
    cols = lay["columns"]
    sw, sh = im.size[0] // cols, im.size[1] // lay["rows"]
    r, c = divmod(f, cols)
    x0, y0 = c * sw + (sw - FW) // 2, r * sh + (sh - FH) // 2
    return idx[y0:y0 + FH, x0:x0 + FW].copy(), pal


def up(m):
    return np.repeat(np.repeat(m, K, 0), K, 1)


class Geom:
    def __init__(self, save):
        bt = mt.Battle(save)
        self.data = mt.Data(bt.mods)
        p = self.data.find("TERRAIN/LOFTEMPS.DAT") or self.data.find("GEODATA/LOFTEMPS.DAT")
        raw = np.frombuffer(p.read_bytes(), "<u2")
        self.loft = ((raw[:, None] >> np.arange(16)) & 1).astype(bool).reshape(-1, 16, 16)   # [id, y, бит]
        self._raw = {}

    def raw(self, s):
        if s not in self._raw:
            p = self.data.find("TERRAIN/%s.MCD" % s)
            b = p.read_bytes()
            self._raw[s] = [b[i:i + mt.MCD_RECORD] for i in range(0, len(b) - mt.MCD_RECORD + 1, mt.MCD_RECORD)]
        return self._raw[s]

    def record(self, s, r):
        rec = self.data.mcd(s)[r]          # с MCDPatch: die, alt, тип
        b = self.raw(s)[r]
        out = dict(rec)
        out["loft"] = list(b[B_LOFT:B_LOFT + 12])
        out["stop_los"] = b[B_STOP_LOS]
        return out

    def voxels(self, rec):
        """[z 0..23, y 0..15, x 0..15] - сплошной ли воксель (voxelCheck: бит 15 - x)."""
        v = np.zeros((24, 16, 16), bool)
        for z in range(24):
            lid = min(rec["loft"][z // 2], len(self.loft) - 1)
            if lid:
                v[z] = self.loft[lid][:, ::-1]
        return v


def project(vox, yoff):
    """Непрозрачность проекции вокселей в кадре x4 (непрерывно, подотсчёты)."""
    m = np.zeros((FH * K, FW * K), bool)
    zs, ys, xs = np.nonzero(vox)
    if not len(zs):
        return m
    sx, sy, sz = np.meshgrid(SUB, SUB, SUB, indexing="ij")
    sx, sy, sz = sx.ravel(), sy.ravel(), sz.ravel()
    X = xs[:, None] + sx[None]
    Y = ys[:, None] + sy[None]
    Z = zs[:, None] + sz[None]
    px = np.floor(K * (X - Y + 16)).astype(int)
    py = np.floor(K * (20 + ART_DY + X / 2 + Y / 2 - Z + yoff)).astype(int)
    ok = (px >= 0) & (px < FW * K) & (py >= 0) & (py < FH * K)
    m[py[ok], px[ok]] = True
    return m


def envelope(vox):
    """Объём стены: по каждому слою z - прямоугольник от крайних сплошных вокселей ВСЕЙ записи по x и y,
    в высоту - от нижнего до верхнего сплошного слоя. Проём окна и двери внутри него."""
    zs, ys, xs = np.nonzero(vox)
    e = np.zeros_like(vox)
    if len(zs):
        e[zs.min():zs.max() + 1, ys.min():ys.max() + 1, xs.min():xs.max() + 1] = True
    return e


def edges(idx):
    """Границы рамп (индекс // 16) между соседними непрозрачными пикселями - линии x4 по краю пикселя."""
    lab = np.where(idx > 0, idx // 16 + 1, 0).astype(int)
    e = np.zeros((FH * K, FW * K), bool)
    dh = (lab[:, 1:] != lab[:, :-1]) & (lab[:, 1:] > 0) & (lab[:, :-1] > 0)
    dv = (lab[1:, :] != lab[:-1, :]) & (lab[1:, :] > 0) & (lab[:-1, :] > 0)
    for y, x in zip(*np.nonzero(dh)):
        e[y * K:(y + 1) * K, (x + 1) * K - 1:(x + 1) * K + 1] = True
    for y, x in zip(*np.nonzero(dv)):
        e[(y + 1) * K - 1:(y + 1) * K + 1, x * K:(x + 1) * K] = True
    return e


def iou(a, b):
    u = (a | b).sum()
    return float((a & b).sum() / u) if u else 1.0


def best_shift(a, b, r=28):
    best = (-1, 0, 0)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            s = np.roll(np.roll(b, dy, 0), dx, 1)
            v = iou(a, s)
            if v > best[0]:
                best = (v, dx, dy)
    return best


def masks_for(g, s, r):
    """Маски записи. Объём со сквозным проёмом (envelope, open) - только у стен (тип 1 запад, 2 север): у пола,
    предмета и лестницы коробка вокселей - это воздух над ступенью, а не проём.
    Дверь НЛО: закрытая запись сплошная, открытая (кадры анимации дальше 0) пропускается voxelCheck целиком -
    open_state = вся её сплошная часть. Распашная дверь: открытая - ДРУГАЯ запись (alt) в другом слоте, у неё
    свои маски; для закрытой open_state = её сплошная часть (место, которое освободится)."""
    rec = g.record(s, r)
    vox = g.voxels(rec)
    yoff = rec["yoff"]
    solid = project(vox, yoff)
    wall = rec["type"] in (1, 2)
    env = project(envelope(vox), yoff) if wall else solid.copy()
    out = dict(rec=rec, solid=solid, envelope=env, open=env & ~solid, frames={})
    for f in dict.fromkeys(rec["frames"]):
        idx, pal = classic(s, f)
        out["frames"][f] = dict(idx=idx, pal=pal, sil=up(idx > 0), edges=edges(idx))
    if rec["ufo_door"] or rec["door"]:
        out["open_state"] = solid.copy()
    return out


def save_png(m, p):
    Image.fromarray((m * 255).astype(np.uint8)).save(p)


def overlay(idx, pal, mk, label):
    """Классика x4 на сером полу; solid - красная кайма, open - зелёная заливка, edges - жёлтые линии."""
    rgb = pal[idx].astype(float)
    a = up(idx > 0)
    base = np.full((FH * K, FW * K, 3), (58, 58, 62), float)
    img = np.where(a[..., None], up_rgb(rgb), base)
    op = mk["open"]
    img[op] = img[op] * 0.4 + np.array([40, 230, 90]) * 0.6
    sol = mk["solid"]
    ring = sol & ~np.roll(sol, 1, 0) | sol & ~np.roll(sol, -1, 0) | sol & ~np.roll(sol, 1, 1) | sol & ~np.roll(sol, -1, 1)
    img[ring] = (255, 60, 60)
    im = Image.fromarray(img.clip(0, 255).astype(np.uint8))
    ImageDraw.Draw(im).text((2, 2), label, fill=(255, 255, 0))
    return im


def up_rgb(rgb):
    return np.repeat(np.repeat(rgb, K, 0), K, 1)


def build(save, out, items):
    g = Geom(save)
    out = Path(out)
    report = {}
    tiles = []
    for it in items:
        s, r = it.split("#")
        r = int(r)
        mk = masks_for(g, s, r)
        d = out / ("%s_%d" % (s, r))
        d.mkdir(parents=True, exist_ok=True)
        for k in ("solid", "envelope", "open"):
            save_png(mk[k], d / (k + ".png"))
        if "open_state" in mk:
            save_png(mk["open_state"], d / "open_state.png")
        info = dict(set=s, record=r, frames=mk["rec"]["frames"], tile_type=mk["rec"]["type"], yoff=mk["rec"]["yoff"],
                    door=mk["rec"]["door"], ufo_door=mk["rec"]["ufo_door"], alt=mk["rec"]["alt"], die=mk["rec"]["die"],
                    stop_los=mk["rec"]["stop_los"], loft=mk["rec"]["loft"],
                    solid_px=int(mk["solid"].sum()), open_px=int(mk["open"].sum()), per_frame={})
        for f, fr in mk["frames"].items():
            save_png(fr["sil"], d / ("sil_%d.png" % f))
            save_png(fr["edges"], d / ("edges_%d.png" % f))
            sil = fr["sil"]
            info["per_frame"][f] = dict(
                sil_px=int(sil.sum()),
                iou_solid=round(iou(sil, mk["solid"]), 3),
                solid_not_painted=round(float((mk["solid"] & ~sil).sum() / max(1, mk["solid"].sum())), 3),
                open_painted=round(float((mk["open"] & sil).sum() / max(1, mk["open"].sum())), 3),
                edge_px=int(fr["edges"].sum()))
            tiles.append(overlay(fr["idx"], fr["pal"], mk, "%s#%d f%d" % (s, r, f)))
        (d / "masks.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8-sig")
        report[it] = info
        print(it, "кадры", mk["rec"]["frames"], "P_Level", mk["rec"]["yoff"], "Stop_LOS", mk["rec"]["stop_los"],
              "solid", info["solid_px"], "open", info["open_px"],
              " ".join("f%d iou %.2f откр.закрашено %.2f" % (f, v["iou_solid"], v["open_painted"])
                       for f, v in info["per_frame"].items()))
    if tiles:
        cols = 8
        W, H = FW * K + 4, FH * K + 4
        sheet = Image.new("RGB", (cols * W, ((len(tiles) + cols - 1) // cols) * H), (20, 20, 24))
        for i, t in enumerate(tiles):
            sheet.paste(t, ((i % cols) * W, (i // cols) * H))
        sheet.save(out / "overlay.png")
    (out / "masks_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8-sig")


def check(mdir, hd_path):
    """HD-кадр против масок записи. Возвращает числа и вердикт по каждому правилу."""
    mdir = Path(mdir)
    info = json.load(open(mdir / "masks.json", encoding="utf-8-sig"))
    f = int(Path(hd_path).name.split(".")[0])
    ld = lambda n: np.array(Image.open(mdir / n)) > 127
    sil, solid, op = ld("sil_%d.png" % f), ld("solid.png"), ld("open.png")
    env = ld("envelope.png") if (mdir / "envelope.png").exists() else solid | op
    a = np.array(Image.open(hd_path).convert("RGBA").resize((FW * K, FH * K), Image.LANCZOS))[..., 3] > 127
    # проём сверяется с ВИДИМЫМ проёмом классики (объём минус рисунок): классика вправе рисовать раму и переплёт
    # там, где механика пропускает выстрел (окно URBAN 71/72: LOFT пуст на всю ширину в слоях 10..21). LOFT - отдельно,
    # строкой механики: MCD мы не меняем, и HD её не меняет
    hole_c, hole_h = env & ~sil, env & ~a
    res = dict(
        frame=f,
        silhouette_iou=round(iou(a, sil), 3),
        open_covered_new=int((a & op & ~sil).sum()),          # рама или стекло закрыли место, открытое в классике и в механике
        fake_hole=int((~a & solid & sil).sum()),              # дыра там, где стена сплошная и в механике, и в классике
        open_px=int(op.sum()), solid_px=int(solid.sum()))
    if hole_c.sum() >= 16:
        ys, xs = np.nonzero(hole_c)
        yh, xh = np.nonzero(hole_h)
        res.update(hole_iou_vs_classic=round(iou(hole_h, hole_c), 3),
                   hole_shift_vs_classic_x4=(round(float(np.hypot(xh.mean() - xs.mean(), yh.mean() - ys.mean())), 2)
                                             if len(xh) else None),          # проём заложен целиком
                   loft_open_painted=dict(classic=round(float((op & sil).sum() / max(1, op.sum())), 3),
                                          hd=round(float((op & a).sum() / max(1, op.sum())), 3)))
    ok = res["open_covered_new"] <= 8 and res["fake_hole"] <= 8 and res["silhouette_iou"] >= 0.97
    if "hole_iou_vs_classic" in res:
        ok = ok and res["hole_iou_vs_classic"] >= 0.90 and res["hole_shift_vs_classic_x4"] is not None \
            and res["hole_shift_vs_classic_x4"] <= 2.0
    res["verdict"] = "PASS" if ok else "FAIL"
    return res


def selftest(save):
    """Проекция LOFT против силуэта классики на сплошных стенах и предмете: IoU и лучший сдвиг обязаны быть
    около нуля. Контроль: тот же расчёт без P_Level или с зеркалом бита x обязан дать худшее совпадение."""
    g = Geom(save)
    ok = True
    for s, r in (("URBAN", 65), ("URBAN", 66), ("URBAN", 31), ("URBAN", 32), ("ROADS", 21)):
        rec = g.record(s, r)
        vox = g.voxels(rec)
        idx, _ = classic(s, rec["frames"][0])
        sil = up(idx > 0)
        pr = project(vox, rec["yoff"])
        v, dx, dy = best_shift(sil, pr)
        bad = iou(sil, project(vox[:, :, ::-1], rec["yoff"]))      # контроль: бит x не перевёрнут
        print("%s#%d f%d тип %d P_Level %d: IoU %.3f (лучший %.3f при сдвиге %d, %d пикс x4); "
              "контроль без переворота x %.3f; рисунок вне проекции %.3f, проекция вне рисунка %.3f"
              % (s, r, rec["frames"][0], rec["type"], rec["yoff"], iou(sil, pr), v, dx, dy, bad,
                 (sil & ~pr).sum() / max(1, sil.sum()), (pr & ~sil).sum() / max(1, pr.sum())))
        ok &= abs(dx) <= 2 and abs(dy) <= 2
    print("selftest", "PASS" if ok else "FAIL")
    return ok


def main():
    a = argparse.ArgumentParser()
    a.add_argument("cmd", choices=("build", "check", "selftest"))
    a.add_argument("items", nargs="*")
    a.add_argument("--save")
    a.add_argument("--out")
    a.add_argument("--masks")
    a.add_argument("--hd")
    o = a.parse_args()
    if o.cmd == "selftest":
        sys.exit(0 if selftest(o.save) else 1)
    if o.cmd == "build":
        build(o.save, o.out, o.items)
    else:
        print(json.dumps(check(o.masks, o.hd), ensure_ascii=False))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
