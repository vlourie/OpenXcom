"""ОСТАНОВЛЕН 03.10 по решению специалиста (R-208): растяжка готового ответа по опорным точкам и вырезка автомата
разницей генераций портят картинку; эталоны и ретушь отсюда не использовать.

Пилот GOV_4, одна поза до приёмки (специалист 03.10): геометрия - по размеченным опорным точкам оригинала,
оружие - отдельно от тела. Qwen-Image-2.1 сужает фигуру при любом входе (у предметов то же, item_photo --engine
edit), поэтому геометрию собираем сами, а Edit-2511 + Lightning только правит снимок, не двигая контур: одна
картинка на входе (R-205), меток на входе нет (R-204).

Стадии, поза n и направление d (unit_pilot.POSES), папка art/units/pilot-gov4/refit/d<d>_p<n>/:
  gpu --stages strip0,isolate0 ответ рендера C (unit_pilot render) -> без автомата: B0; только автомат: I0
  warp                         автомат целиком - I0 (свой матт); видимый автомат - где I0 совпал с ответом, где
                               не совпал - кисти поверх; тело = ответ вне видимого автомата, B0 под ним (Edit при
                               снятии автомата опускает руки - из B0 берём только место под автоматом). Тело - TPS
                               по опорным точкам kp.json на геометрию оригинала, автомат - подобием по концу
                               приклада и дулу на автомат оригинала, кисти и рука rarm поверх -> эталон guide.png
  gpu --stages retouch,strip1,isolate1  эталон -> цельный снимок R1 (геометрия эталона - закон) -> B1, I1
  frames                       кадры тела: R1 вне видимого автомата, B1 под ним, по карте владельцев без предмета;
                               кадр предмета - I1 целиком (под рукой rarm он закрыт ею, как в движке)
  check                        наложение, покрытие и тонкое по частям отдельно (руки, автомат), сборки как в
                               движке: без предмета, AK, два чужих двуручных

Модель грузит только gpu (через tools/gpuq.py); warp, frames и check её не импортируют.
    py -3.13 tools/hdart/unit_refit.py warp --pose 1
kp.json: {"имя": [[x, y] оригинала, [x, y] рендера C]} в пикселях HD-холста фигуры (K=4, поля PAD)."""
import argparse
import json
import os
import sys
import time

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# Edit-2511 - веса только из кэша; флаг до импорта diffusers, как item_photo --engine edit (R-145)
if sys.argv[1:2] == ["gpu"]:
    os.environ["HF_HUB_OFFLINE"] = "1"
import item_photo as ip         # noqa: E402
import photo_base as pb         # noqa: E402
import photo_render as pr       # noqa: E402
import unit_pilot as up         # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
ENC = "utf-8-sig"
K = up.K
OUT = os.path.join("art", "units", "pilot-gov4", "refit")
GUN_MIN = 0.002                 # кусок снимка «только автомат» меньше этой доли кадра - шум правки, не автомат
OTHER_2H = (("HuntingRifle", "HuntingRifle.png"), ("Flamethrower", "Flamethrower.png"))

STRIP = ("<image1> is a photograph of a person holding a rifle, seen from above, on a flat plain panel of colour "
         "RGB({r}, {g}, {b}). Remove the rifle completely. Keep everything else exactly as it is: the same person, "
         "the same face, hair and sunglasses, the same clothing, the same pose, size and position, the same light. "
         "The hands stay exactly where they are and keep their grip, holding nothing. Where the rifle covered the "
         "body, show the clothing and the hands that are behind it; where it covered the panel, show the plain "
         "panel. Do not move, resize, bend or redraw the body, add nothing. Keep the flat plain panel exactly as it "
         "is: no shadow on it, no other objects, no frame, no text.")
RETOUCH = ("<image1> is a photograph of {who}, seen from above at a steep angle, assembled from separate photos of "
           "its parts and stretched to fit, on a flat plain panel of colour RGB({r}, {g}, {b}). Retouch it into one "
           "seamless real photograph of the same person. Fix the seams and the stretched, smeared areas, make the "
           "lighting consistent over the whole figure with soft light from the upper left, crisp detail. The "
           "coverall is dark slate grey with a cool bluish sheen and clear light grey highlights on the folds, a "
           "light grey zipper and collar on the chest; the sleeves are rolled up to the elbows and the forearms are "
           "bare skin; heavy black boots. The rifle has dark worn steel and red-brown wood and is perfectly "
           "straight. Do not change the geometry: keep exactly the outline, the size, the position and the "
           "thickness of the head, the shoulders, the arms, the hands, the legs, the boots and the rifle; do not "
           "move, bend, shorten, lengthen, thin or narrow anything, add nothing and remove nothing. Keep the flat "
           "plain panel exactly as it is: no shadow on it, no other objects, no frame, no text.")
ISOLATE = ("<image1> is a photograph of a person holding a rifle, seen from above, on a flat plain panel of "
           "colour RGB({r}, {g}, {b}). Remove the person completely and keep only the rifle. The rifle stays exactly "
           "where it is: the same position, angle, size and shape, the same light. Where the hands and arms covered "
           "the rifle, show the rifle parts that are behind them. Everything else becomes the plain panel. Do not "
           "move, resize, bend or redraw the rifle, add nothing. Keep the flat plain panel exactly as it is: no "
           "shadow on it, no other objects, no frame, no text.")
GUN_SAME = 18.0                 # закрытый автомат: ответ отличается от «только автомат» на dE Lab (окно 5x5)
WHO = ("a female government pilot with short blond hair and dark aviator sunglasses in a one-piece flight coverall "
       "with a small red patch on the left chest and on the left shoulder, holding an old Kalashnikov-pattern "
       "assault rifle across the body")
EDIT_SEED = 5300
CODE = (("unit_refit.py", ("STRIP", "RETOUCH", "ISOLATE", "WHO", "gun_split", "body_fill", "align_shift", "tps_fit", "tps_eval", "build_guide",
                           "similarity", "gun_ends")),)


# ------------------------------------------------------------------ общее

class Pose:
    """Классика позы и её кроп так же, как у unit_pilot render (кроп - вход и холст вырезки)."""

    def __init__(self, n, d):
        self.n, self.d = n, d
        self.s = up.Sources()
        self.L = self.s.layers(up.POSES[n], d)
        self.full, _o = up.compose(self.L, self.s.classic, 1)
        self.crop, self.box = ip.crop_job(self.full)
        self.off4 = np.array([(self.box[0] - ip.PAD) * K, (self.box[1] - ip.PAD) * K], float)  # c4 = f4 - off4
        self.c4 = (self.crop.width * K, self.crop.height * K)
        self.dir = os.path.join(OUT, "d%d_p%d" % (d, n))
        self.tag = "d%d_p%d" % (d, n)

    def body_layers(self):
        return [l for l in self.L if l[1][0] == "unit"]

    def item_index(self):
        return [i for i, l in enumerate(self.L) if l[1][0] == "item"]

    def to_c4(self, f4):
        """Холст фигуры x4 -> холст кропа x4 (RGBA или маска)."""
        a = np.asarray(f4)
        x, y = int(self.off4[0]), int(self.off4[1])
        return a[y:y + self.c4[1], x:x + self.c4[0]]

    def fig_from_c4(self, c4im):
        return up.place(c4im, self.box, self.full)


def raw_of(meta_path):
    with open(meta_path, encoding=ENC) as f:
        m = json.load(f)
    a = m["attempts"][-1]
    return a["raw"], tuple(a["panel_rgb"]), a["panel"], m


def load_rgb(p):
    return np.asarray(Image.open(p).convert("RGB"), np.float32)


def box_blur(a, r):
    """Среднее по окну (2r+1)^2, края - повтором."""
    p = np.pad(a, [(r, r), (r, r)] + [(0, 0)] * (a.ndim - 2), mode="edge")
    c = p.cumsum(0).cumsum(1)
    c = np.pad(c, [(1, 0), (1, 0)] + [(0, 0)] * (a.ndim - 2))
    n = 2 * r + 1
    return (c[n:, n:] - c[:-n, n:] - c[n:, :-n] + c[:-n, :-n]) / float(n * n)


def lab(rgb):
    """sRGB 0..255 -> CIE Lab (D65)."""
    c = rgb / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    xyz = c @ np.array([[0.4124, 0.2126, 0.0193], [0.3576, 0.7152, 0.1192], [0.1805, 0.0722, 0.9505]])
    xyz = xyz / np.array([0.9505, 1.0, 1.089])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116.0)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def align_shift(a, b, mask, r=10):
    """Сдвиг b (dx, dy) в пределах r, при котором b ближе всего к a внутри маски (медиана макс. по каналам)."""
    ys, xs = np.nonzero(mask)
    y0, y1, x0, x1 = max(0, ys.min() - r), ys.max() + r + 1, max(0, xs.min() - r), xs.max() + r + 1
    A, B, M = a[y0:y1, x0:x1], b[y0:y1, x0:x1], mask[y0:y1, x0:x1]
    best = (np.inf, 0, 0)
    for dy in range(-r, r + 1, 2):
        for dx in range(-r, r + 1, 2):
            sm = np.roll(np.roll(M, dy, 0), dx, 1)
            v = np.median(np.abs(A - np.roll(np.roll(B, dy, 0), dx, 1)).max(-1)[sm])
            best = min(best, (v, dx, dy))
    _v, bx, by = best
    for dy in range(by - 1, by + 2):
        for dx in range(bx - 1, bx + 2):
            sm = np.roll(np.roll(M, dy, 0), dx, 1)
            v = np.median(np.abs(A - np.roll(np.roll(B, dy, 0), dx, 1)).max(-1)[sm])
            best = min(best, (v, dx, dy))
    return best[1], best[2], float(best[0])


def shift(a, dx, dy):
    return np.roll(np.roll(a, dy, 0), dx, 1)


def gun_split(with_gun, iso, iso_matte):
    """Автомат по снимку «только автомат» I (Edit сдвигает его на несколько пикселей - сначала выравнивание):
    целиком - матт I без шума GUN_MIN; закрытый - где ответ отличается от I по цвету Lab больше GUN_SAME (кисти и
    рукав поверх: рукав тёмен как сталь, но не цвета дерева - по максимуму каналов не различить); видимый -
    остальное. -> (целиком 0..1, видимый 0..1, закрытый 0..1, I и его матт после сдвига, отчёт)."""
    full = iso_matte > 0.5
    lb, n = pb.label(full, 8)
    sizes = np.bincount(lb.ravel(), minlength=n + 1)
    keep = np.zeros(n + 1, bool)
    keep[1:] = sizes[1:] >= GUN_MIN * full.size
    full = keep[lb]
    dx, dy, med = align_shift(with_gun, iso, full)
    iso, iso_matte, full = shift(iso, dx, dy), shift(iso_matte, dx, dy), shift(full, dx, dy)
    d = box_blur(np.sqrt(((lab(with_gun) - lab(iso)) ** 2).sum(-1)), 2)
    core = ~pb.grow(~full, 3)                    # кромка в 3 пикселя - видимый автомат (сдвиг в доли пикселя)
    occ = core & (d >= GUN_SAME)
    # закрытое - кисти и рукав: куски заметного размера и толщины; тонкие полосы и пятна - свет, которым Edit
    # перерисовал автомат (верх ствольной коробки, блик магазина)
    occ = pb.grow(~pb.grow(~occ, 3), 3) & occ
    lb, n = pb.label(occ, 8)
    sizes = np.bincount(lb.ravel(), minlength=n + 1)
    big = np.zeros(n + 1, bool)
    big[1:] = sizes[1:] >= 0.5 * GUN_MIN * full.size
    occ = pb.grow(big[lb], 2) & full
    vis = full & ~occ

    def soft(m):
        return np.clip(box_blur(m.astype(np.float32), 1), 0, 1)
    fm = np.minimum(soft(full), np.clip(iso_matte, 0, 1))
    return fm, soft(vis) * fm, soft(occ), iso, iso_matte, {
        "pieces": int(keep[1:].sum()), "px": int(full.sum()), "visible_px": int(vis.sum()),
        "occluded_px": int(occ.sum()), "frac": round(float(full.mean()), 4), "iso_shift": [dx, dy],
        "iso_median_diff": round(med, 1)}


def body_fill(a, ma, hole, gun):
    """Тело без автомата: снимок a, где видимый автомат (hole 0..1) - заливка от соседей (нормированная свёртка
    со всё большим окном), цвет - только от тела, не от автомата (gun 0..1, весь). Матт - так же. Фактуру
    дорисует ретушь. -> (цвет, матт)."""
    hole = np.clip(box_blur(pb.grow(hole > 0.3, 2).astype(np.float32), 1), 0, 1)   # без кромки автомата
    known = (1 - np.maximum(hole, gun)) * (ma > 0.5)
    need = hole > 0.02
    fill_c = np.zeros_like(a)
    fill_m = np.zeros_like(ma)
    done = np.zeros(hole.shape, bool)
    kn_m = 1 - np.maximum(hole, gun)
    for r in (2, 4, 8, 16, 32, 64):
        w = box_blur(known, r)
        c = box_blur(a * known[..., None], r)
        wm = box_blur(kn_m, r)
        cm = box_blur(ma * kn_m, r)
        ok = need & ~done & (w > 0.05)
        fill_c[ok] = c[ok] / w[ok][:, None]
        fill_m[ok] = cm[ok] / np.maximum(wm[ok], 1e-3)
        done |= ok
    h = hole[..., None]
    col = a * (1 - h) + fill_c * h
    mat = ma * (1 - hole) + fill_m * hole
    return col, mat


def gun_ends(mask):
    """Концы автомата по главной оси силуэта: приклад (меньшая проекция), дуло (большая); точка - медиана
    пикселей у края в 2 % длины. -> (приклад, дуло, ось)."""
    ys, xs = np.nonzero(mask)
    pts = np.stack([xs, ys], 1).astype(float)
    c = pts.mean(0)
    _u, _s, vt = np.linalg.svd(pts - c, full_matrices=False)
    ax = vt[0] if vt[0][0] > 0 else -vt[0]          # ось слева направо: дуло у направления 3 справа
    t = (pts - c) @ ax
    span = t.max() - t.min()
    lo = pts[t <= t.min() + 0.02 * span].mean(0)
    hi = pts[t >= t.max() - 0.02 * span].mean(0)
    return lo, hi, ax


def similarity(p, q):
    """Подобие (поворот, масштаб, сдвиг) по двум точкам: p[i] -> q[i]. -> матрица 2x3."""
    vp, vq = p[1] - p[0], q[1] - q[0]
    zp, zq = complex(*vp), complex(*vq)
    z = zq / zp
    a, b = z.real, z.imag
    A = np.array([[a, -b], [b, a]])
    t = q[0] - A @ p[0]
    return np.hstack([A, t[:, None]])


def U(r2):
    with np.errstate(divide="ignore", invalid="ignore"):
        u = r2 * np.log(r2)
    return np.nan_to_num(u)


def tps_fit(p, q, lam=1.0):
    n = len(p)
    Kx = U(((p[:, None] - p[None]) ** 2).sum(-1)) + lam * np.eye(n)
    P = np.hstack([np.ones((n, 1)), p])
    A = np.zeros((n + 3, n + 3))
    A[:n, :n], A[:n, n:], A[n:, :n] = Kx, P, P.T
    b = np.zeros((n + 3, 2))
    b[:n] = q
    return np.linalg.solve(A, b)


def tps_eval(p, coef, xy, chunk=200000):
    out = np.empty_like(xy)
    for i in range(0, len(xy), chunk):
        z = xy[i:i + chunk]
        out[i:i + chunk] = (U(((z[:, None] - p[None]) ** 2).sum(-1)) @ coef[:len(p)] + coef[len(p)]
                            + z @ coef[len(p) + 1:])
    return out


def sample(img, x, y):
    """Билинейная выборка HxW[xC] в точках x, y (вне кадра - 0)."""
    h, w = img.shape[:2]
    x0 = np.clip(np.floor(x).astype(int), 0, w - 2)
    y0 = np.clip(np.floor(y).astype(int), 0, h - 2)
    fx = np.clip(x - x0, 0, 1)
    fy = np.clip(y - y0, 0, 1)
    if img.ndim == 3:
        fx, fy = fx[..., None], fy[..., None]
    v = (img[y0, x0] * (1 - fx) * (1 - fy) + img[y0, x0 + 1] * fx * (1 - fy)
         + img[y0 + 1, x0] * (1 - fx) * fy + img[y0 + 1, x0 + 1] * fx * fy)
    inside = (x >= 0) & (x <= w - 1) & (y >= 0) & (y <= h - 1)
    return np.where(inside[..., None] if img.ndim == 3 else inside, v, 0)


def item_mask4(P):
    """Целый кадр предмета (не закрытый рукой) на холсте кропа x4."""
    lay = [P.L[i] for i in P.item_index()]
    im, _o = up.compose(lay, P.s.classic, K)
    return P.to_c4(im)[..., 3] > 0


def owner4(P, layers=None):
    _c, own = up.compose(layers or P.L, P.s.classic, K)
    return P.to_c4(own)


def read_kp(P):
    p = os.path.join(P.dir, "kp.json")
    with open(p, encoding=ENC) as f:
        kp = {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    dst = np.array([v[0] for v in kp.values()], float) - P.off4
    src = np.array([v[1] for v in kp.values()], float) - P.off4
    return list(kp), dst, src


# ------------------------------------------------------------------ warp: эталон геометрии

def build_guide(P, raw0, rgb0, raw_i0, panel):
    """Эталон на сетке ответа: тело (ответ C, видимый автомат залит от соседей) по TPS (оригинал -> рендер),
    автомат I0 целиком подобием, поверх него кисти, закрывавшие автомат в ответе, и рука rarm. Снимок без
    автомата B0 сюда не идёт: Edit, снимая автомат, опускает руки, и под TPS это даёт дыры в рукаве."""
    a0, i0 = load_rgb(raw0), load_rgb(raw_i0)
    H, W = a0.shape[:2]
    m0, bg0, _own = pb.render_matte(Image.open(raw0).convert("RGB"))
    mi, bgi, _own = pb.render_matte(Image.open(raw_i0).convert("RGB"))
    sx, sy = W / float(P.c4[0]), H / float(P.c4[1])
    names, dst, src = read_kp(P)
    im4 = item_mask4(P)
    gm, vis, occ, i0, mi, grep_ = gun_split(a0, i0, mi)
    b0, mb = body_fill(a0, m0, vis, gm)
    gun4 = np.asarray(Image.fromarray((gm * 255).astype(np.uint8)).resize(P.c4, Image.BOX), np.float32) / 255 > 0.5
    lo_r, hi_r, _ax = gun_ends(gun4)
    lo_o, hi_o, _ax = gun_ends(im4)
    S = similarity(np.array([lo_o, hi_o]), np.array([lo_r, hi_r]))       # оригинал -> рендер, холст кропа x4
    scale = float(np.hypot(S[0, 0], S[1, 0]))
    angle = float(np.degrees(np.arctan2(S[1, 0], S[0, 0])))
    # рамка холста стоит на месте
    cw, ch = P.c4
    fr = np.array([(x, y) for x in (0, cw / 2, cw - 1) for y in (0, ch / 2, ch - 1) if (x, y) != (cw / 2, ch / 2)])
    coef = tps_fit(np.vstack([dst, fr]), np.vstack([src, fr]))
    pts = np.vstack([dst, fr])
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    c4x, c4y = (xx + 0.5) / sx - 0.5, (yy + 0.5) / sy - 0.5
    grid = np.stack([c4x.ravel(), c4y.ravel()], 1)
    m = tps_eval(pts, coef, grid).reshape(H, W, 2)
    rx, ry = (m[..., 0] + 0.5) * sx - 0.5, (m[..., 1] + 0.5) * sy - 0.5
    body = sample(b0, rx, ry)
    bm = sample(mb, rx, ry)
    g = grid @ S[:, :2].T + S[:, 2]
    gx, gy = (g[:, 0].reshape(H, W) + 0.5) * sx - 0.5, (g[:, 1].reshape(H, W) + 0.5) * sy - 0.5
    gun = sample(i0, gx, gy)
    gmm = sample(gm, gx, gy)
    occ_b = sample(occ, rx, ry) * bm             # кисти поверх автомата - вместе с телом, по TPS
    # снять подложку с цветов кромки (как decontaminate): цвет = (снимок - (1-m) * подложка) / m
    body = np.where(bm[..., None] > 0.05, (body - (1 - bm[..., None]) * bg0) / np.maximum(bm[..., None], 0.05), 0)
    gun = np.where(gmm[..., None] > 0.05, (gun - (1 - gmm[..., None]) * bgi) / np.maximum(gmm[..., None], 0.05), 0)
    own = owner4(P)
    rarm_i = [i + 1 for i, l in enumerate(P.L) if l[0] == "rarm"][0]
    ro = np.asarray(Image.fromarray((own == rarm_i).astype(np.uint8) * 255).resize((W, H), Image.NEAREST)) > 0
    # лесенку клеток базы во вход не пускать (R-121): край области руки размыт на полпикселя базы
    ro = np.clip(box_blur(ro.astype(np.float32), max(1, int(round(sx * K / 2)))), 0, 1)
    out = np.ones((H, W, 3), np.float32) * np.asarray(panel, np.float32)
    bm3, gm3 = bm[..., None], gmm[..., None]
    out = out * (1 - bm3) + body * bm3
    out = out * (1 - gm3) + gun * gm3
    top = np.maximum(bm * ro, occ_b)[..., None]
    out = out * (1 - top) + body * top
    jx, jy = np.gradient(m[..., 0]), np.gradient(m[..., 1])
    det = jx[1] * jy[0] - jx[0] * jy[1]
    inside = bm > 0.5
    area = 1.0 / (np.abs(det[inside]) * sx * sy)   # площадь на оригинале / площадь на рендере
    rep = {"keypoints": names, "gun_mask": grep_, "gun_scale": round(scale, 3), "gun_angle_deg": round(angle, 2),
           "gun_orig_ends4": [list(np.round(lo_o + P.off4, 1)), list(np.round(hi_o + P.off4, 1))],
           "gun_render_ends4": [list(np.round(lo_r + P.off4, 1)), list(np.round(hi_r + P.off4, 1))],
           "area_stretch": {"median": round(float(np.median(area)), 2),
                            "p5": round(float(np.percentile(area, 5)), 2),
                            "p95": round(float(np.percentile(area, 95)), 2)},
           "fold_px": int((det[inside] <= 0).sum())}
    alpha = np.clip(np.maximum(bm, gmm), 0, 1)
    return Image.fromarray(np.uint8(np.clip(out, 0, 255) + 0.5)), alpha, rep


def cmd_warp(a):
    os.chdir(ROOT)
    P = Pose(a.pose, a.dir)
    raw0, rgb0, pn0, _m = raw_of(os.path.join(up.RENDER_OUT, "meta", "%s.C.json" % P.tag))
    raw_i0, rgbi, _pn, _m = raw_of(os.path.join(P.dir, "meta", "isolate0.json"))
    guide, alpha, rep = build_guide(P, raw0, rgb0, raw_i0, rgb0)
    gp = os.path.join(P.dir, "guide.png")
    guide.save(gp)
    # мерка эталона: его силуэт на холсте x4 против оригинала
    al4 = np.asarray(Image.fromarray(np.uint8(alpha * 255)).resize(P.c4, Image.BOX), np.float32) / 255 > 0.5
    o4 = P.to_c4(up.compose(P.L, P.s.classic, K)[0])[..., 3] > 0
    rep["iou_guide"] = round(float((al4 & o4).sum() / (al4 | o4).sum()), 3)
    rep.update(guide=gp.replace("\\", "/"), panel=pn0, panel_rgb=list(rgb0),
               created=time.strftime("%Y-%m-%dT%H:%M:%S"))
    with open(os.path.join(P.dir, "guide.json"), "w", encoding=ENC) as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    print(json.dumps(rep, ensure_ascii=False))


# ------------------------------------------------------------------ gpu: правки Edit-2511

def cmd_gpu(a):
    import argparse as ap_
    import asset_rev as ar
    import gen_fire
    import obj_gen_spec as ogs
    import obj_photo as op
    import struct_probe as sp
    os.chdir(ROOT)
    P = Pose(a.pose, a.dir)
    raw_dir, meta_dir = os.path.join(P.dir, "raw"), os.path.join(P.dir, "meta")
    for x in (raw_dir, meta_dir):
        os.makedirs(x, exist_ok=True)
    R = sp.Render(P.dir, a.models)
    R.run = ap_.Namespace(mp=ip.EDIT_RUN["mp"], steps=ip.EDIT_RUN["steps"], cfg=ip.EDIT_RUN["cfg"])
    R.painter = ip.EditPainter(R.ns.models)
    ip.edit_model_check(R.ns.models)
    R.check_lock()
    gen_fire.NEGATIVE = R.po.gen_fire.NEGATIVE = op.NEGATIVE
    pb.cut = ip.cut_fixed
    R.grev = ar.h12({"run": ip.EDIT_RUN, "model_rev": ip.EDIT_MODEL_REV, "strip": STRIP, "retouch": RETOUCH, "isolate": ISOLATE,
                     "who": WHO, "seed": EDIT_SEED, "lock_rev": ogs.lock_rev(R.lock),
                     "code": ogs.code_parts(CODE)})
    print("unit_refit %s: generator_rev %s, стадии %s" % (P.tag, R.grev, a.stages), flush=True)
    c_meta = os.path.join(up.RENDER_OUT, "meta", "%s.C.json" % P.tag)
    r_meta = os.path.join(meta_dir, "retouch.json")
    src = {"strip0": c_meta, "isolate0": c_meta, "strip1": r_meta, "isolate1": r_meta}
    for stage in a.stages.split(","):
        if stage == "retouch":
            gj = os.path.join(P.dir, "guide.json")
            with open(gj, encoding=ENC) as f:
                g = json.load(f)
            inp, rgb, pname = g["guide"], tuple(g["panel_rgb"]), g["panel"]
            text = RETOUCH
            tries = pr.MAX_ATTEMPTS
        else:
            inp, rgb, pname, _m = raw_of(src[stage])
            text = ISOLATE if stage.startswith("isolate") else STRIP
            tries = 1                       # силуэт другой (без автомата, только автомат) - перерисовка не нужна
        r, g_, b = [int(v) for v in rgb]
        im_in = Image.open(inp).convert("RGB")
        sp.inputs = lambda v, frame, rgb_, im_in=im_in: ([im_in], "", {"inputs": "photo"})
        pr.prompt_for = lambda what, name, rgb_, text=text: text.format(r=int(rgb_[0]), g=int(rgb_[1]),
                                                                       b=int(rgb_[2]), who=WHO)
        old = pr.MAX_ATTEMPTS
        pr.MAX_ATTEMPTS = tries
        j = {"asset_id": "GOV_4:%s:%s" % (P.tag, stage), "name": stage, "seed": EDIT_SEED, "what": ""}
        try:
            final, attempts = R.job("E", j, P.crop, [(pname, (r, g_, b), 0.0)], raw_dir)
        finally:
            pr.MAX_ATTEMPTS = old
        im, rep, _g, _m, c, verdict = final
        fig = P.fig_from_c4(im)
        fp = os.path.join(P.dir, "%s.fig.png" % stage)
        fig.save(fp)
        meta = {"asset_id": j["asset_id"], "stage": stage, "input": inp.replace("\\", "/"), "generator_rev": R.grev,
                "attempts": attempts, "report": rep, "checks": {x: list(c[x]) for x in sp.pa.MACHINE_CHECKS},
                "machine": verdict, "figure": fp.replace("\\", "/"), "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
        with open(os.path.join(meta_dir, "%s.json" % stage), "w", encoding=ENC) as f:
            json.dump(meta, f, ensure_ascii=False, indent=1)
        print("%s %s: %s, модель %s / %s, края %s" % (P.tag, stage, verdict, rep["model"].get("dw_pct"),
                                                     rep["model"].get("dh_pct"), rep["model"].get("edges")),
              flush=True)


# ------------------------------------------------------------------ frames: кадры частей

def frame_piece(P, fig, layer, mine):
    _n, _src, ox, oy = layer
    x, y = (up.PAD + ox) * K, (up.PAD + oy) * K
    a = np.asarray(fig)
    piece = a[y:y + up.H * K, x:x + up.W * K].copy()
    piece[..., 3] = np.where(mine[y:y + up.H * K, x:x + up.W * K], piece[..., 3], 0)
    return piece


def cmd_frames(a):
    os.chdir(ROOT)
    P = Pose(a.pose, a.dir)
    meta = {}
    for st in ("retouch", "strip1", "isolate1"):
        with open(os.path.join(P.dir, "meta", "%s.json" % st), encoding=ENC) as f:
            meta[st] = json.load(f)
    r1, b1, i1 = (Image.open(meta[st]["figure"]).convert("RGBA") for st in ("retouch", "strip1", "isolate1"))
    raw_r, _rgb, _pn, _m = raw_of(os.path.join(P.dir, "meta", "retouch.json"))
    raw_i, _rgb, _pn, _m = raw_of(os.path.join(P.dir, "meta", "isolate1.json"))
    ar_, ai_ = load_rgb(raw_r), load_rgb(raw_i)
    mi, _bg, _own = pb.render_matte(Image.open(raw_i).convert("RGB"))
    gm, vis, _occ, _i, _mi, grep_ = gun_split(ar_, ai_, mi)
    gm = shift(gm, -grep_["iso_shift"][0], -grep_["iso_shift"][1])    # кадр предмета - из I1 на своём месте
    x, y = int(P.off4[0]), int(P.off4[1])

    def to_fig(m):
        m4 = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).resize(P.c4, Image.BOX), np.float32) / 255
        out = np.zeros((r1.height, r1.width), np.float32)
        out[y:y + P.c4[1], x:x + P.c4[0]] = m4
        return out
    big, vis_f = to_fig(gm), to_fig(vis)
    fd = os.path.join(P.dir, "frames")
    os.makedirs(fd, exist_ok=True)
    # автомат: снимок I1 целиком, альфа = альфа I1 x маска автомата (без шума правки)
    ga = np.asarray(i1).copy()
    ga[..., 3] = (ga[..., 3] * big).astype(np.uint8)
    gun_fig = Image.fromarray(ga, "RGBA")
    rep = {"gun_mask": grep_, "frames": {}}
    for i in P.item_index():
        piece = frame_piece(P, gun_fig, P.L[i], np.ones(big.shape, bool))
        nm = up.frame_name(P.L[i][1]).replace(" ", "_")
        Image.fromarray(piece, "RGBA").save(os.path.join(fd, nm + ".png"))
        rep["frames"][nm] = {"from": "isolate1", "px": int((piece[..., 3] > 127).sum())}
    # тело: R1 вне видимого автомата, B1 под ним
    ra, ba, ia = (np.asarray(im_, np.float32) for im_ in (r1, b1, i1))
    v4 = vis_f[..., None]
    b1 = Image.fromarray(np.uint8(np.clip(ra * (1 - v4) + ba * v4, 0, 255) + 0.5), "RGBA")
    # по карте владельцев без предмета (что под автоматом - торсу и рукам)
    bl = P.body_layers()
    _c, own = up.compose(bl, P.s.classic, K)
    own = up.owners_grown(own, np.asarray(b1)[..., 3])
    for i, l in enumerate(bl):
        piece = frame_piece(P, b1, l, own == i + 1)
        nm = up.frame_name(l[1]).replace(" ", "_")
        Image.fromarray(piece, "RGBA").save(os.path.join(fd, nm + ".png"))
        # остаток автомата в кадре тела: пиксели кадра в области автомата, совпавшие по цвету с I1
        x0, y0 = (up.PAD + l[2]) * K, (up.PAD + l[3]) * K
        sl = (slice(y0, y0 + up.H * K), slice(x0, x0 + up.W * K))
        same = np.abs(piece[..., :3].astype(np.float32) - ia[sl][..., :3]).max(-1) < GUN_SAME
        rep["frames"][nm] = {"from": "retouch + strip1 под автоматом", "px": int((piece[..., 3] > 127).sum()),
                             "gun_region_px": int(((piece[..., 3] > 127) & (big[sl] > 0.5)).sum()),
                             "gun_px_in_frame": int(((piece[..., 3] > 127) & (big[sl] > 0.5) & same).sum())}
    with open(os.path.join(P.dir, "frames.json"), "w", encoding=ENC) as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    print(json.dumps(rep, ensure_ascii=False))


# ------------------------------------------------------------------ check: мерки и сборки

def other_handob(name_file, d):
    """Кадр направления d чужого двуручного из Resources/HANDOB (лист по 8 направлений, как AK.png)."""
    p = os.path.join(os.path.dirname(up.HANDOB_AK), name_file)
    fr = up.load_frames(p)
    return fr, p


def assemble(P, frames, item_img):
    """Сборка как движок: слои позы в порядке P.L, HD-кадр части или item_img на месте предмета (None - без)."""
    cw, ch = (up.W + 2 * up.PAD) * K, (up.H + 2 * up.PAD) * K
    out = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    for _n, src, ox, oy in P.L:
        im = item_img if src[0] == "item" else frames.get(src)
        if im is None:
            continue
        out.alpha_composite(im, ((up.PAD + ox) * K, (up.PAD + oy) * K))
    return out


def part_stats(P, fig_frames, g):
    """Покрытие каждой части оригинала своим HD-кадром и тонкого в ней (g['thin4'] на холсте кропа)."""
    _c, own = up.compose(P.L, P.s.classic, K)
    thin = np.zeros(own.shape, bool)
    x, y = int(P.off4[0]), int(P.off4[1])
    thin[y:y + P.c4[1], x:x + P.c4[0]] = g["thin4"]
    rows = {}
    for i, (_n, src, ox, oy) in enumerate(P.L):
        im = fig_frames.get(src)
        lay = np.zeros(own.shape, bool)
        if im is not None:
            x0, y0 = (up.PAD + ox) * K, (up.PAD + oy) * K
            lay[y0:y0 + up.H * K, x0:x0 + up.W * K] = np.asarray(im)[..., 3] > 127
        _ci, own_i = up.compose([P.L[i]], P.s.classic, K)  # вся часть, не только видимое сверху
        part = own_i > 0
        vis = own == i + 1
        rows[up.frame_name(src)] = {
            "part": _n, "orig_px": int(part.sum()), "cover": round(float((lay & part).sum() / max(1, part.sum())), 3),
            "cover_visible": round(float((lay & vis).sum() / max(1, vis.sum())), 3),
            "thin_px": int((thin & vis).sum()),
            "thin_cover": round(float((lay & thin & vis).sum() / max(1, (thin & vis).sum())), 3),
            "spill_px": int((lay & ~pb.grow(part, K)).sum())}
    return rows


def cmd_check(a):
    os.chdir(ROOT)
    P = Pose(a.pose, a.dir)
    fd = os.path.join(P.dir, "frames")
    frames = {}
    for _n, src, _x, _y in P.L:
        p = os.path.join(fd, up.frame_name(src).replace(" ", "_") + ".png")
        if os.path.exists(p):
            frames[src] = Image.open(p).convert("RGBA")
    g = pb.guide(P.crop)
    rows = part_stats(P, frames, g)
    orig, _o = up.compose(P.L, P.s.classic, K)
    item_src = [l[1] for l in P.L if l[1][0] == "item"][0]
    variants = [("без предмета", None), ("AK (HD)", frames.get(item_src))]
    for name, fn in OTHER_2H:
        fr, _p = other_handob(fn, P.d)
        im = up.rgba(fr[item_src[1]], P.s.pal).resize((up.W * K, up.H * K), Image.NEAREST)
        variants.append(("%s (классика x4)" % name, im))
    asm = [(nm, assemble(P, frames, im)) for nm, im in variants]
    o = np.asarray(orig)[..., 3] > 0
    f = np.asarray(asm[1][1])[..., 3] > 127
    ob, fb = ip.main_bbox(o, 4 * K), ip.main_bbox(f, 4 * K)
    rep = {"iou": round(float((o & f).sum() / (o | f).sum()), 3),
           "size_pct": [round(100.0 * ((fb[2] - fb[0]) / (ob[2] - ob[0]) - 1), 1),
                        round(100.0 * ((fb[3] - fb[1]) / (ob[3] - ob[1]) - 1), 1)],
           "bbox_orig4": list(ob), "bbox_new4": list(fb), "parts": rows}
    # дуло: правый край кадра предмета HD против классики (направление 3 - дуло справа)
    gi = frames.get(item_src)
    if gi is not None:
        ga = np.asarray(gi)[..., 3] > 127
        ca = np.asarray(P.s.classic(item_src, K))[..., 3] > 0
        lo_h, hi_h, _a = gun_ends(ga)
        lo_c, hi_c, _a = gun_ends(ca)
        rep["muzzle_shift_base_px"] = [round(float(v) / K, 2) for v in hi_h - hi_c]
        rep["stock_shift_base_px"] = [round(float(v) / K, 2) for v in lo_h - lo_c]
    with open(os.path.join(P.dir, "check.json"), "w", encoding=ENC) as f_:
        json.dump(rep, f_, ensure_ascii=False, indent=1)
    # лист: оригинал x4 | целый R1 | наложение | сборки
    cells = [("оригинал x4", orig)]
    r1p = os.path.join(P.dir, "retouch.fig.png")
    if os.path.exists(r1p):
        cells.append(("R1 целиком", Image.open(r1p).convert("RGBA")))
    ov = np.zeros(o.shape + (4,), np.uint8)
    ov[..., 3] = 255
    ov[..., :3] = 30
    ov[o & f, :3] = (150, 150, 150)
    ov[o & ~f, :3] = (40, 220, 60)
    ov[~o & f, :3] = (230, 50, 50)
    cells.append(("наложение: зелёный - только оригинал, красный - только новое", Image.fromarray(ov, "RGBA")))
    cells += [("сборка: " + nm, im) for nm, im in asm]
    X0, Y0, X1, Y1 = 32, 40, 168, 184
    Z = 2
    cw, chh = (X1 - X0) * Z, (Y1 - Y0) * Z
    lab = 34
    sheet = Image.new("RGB", (len(cells) * (cw + 8) + 8, chh + lab + 8), (20, 20, 20))
    d = ImageDraw.Draw(sheet)
    fn = up.font(12)
    for i, (nm, im) in enumerate(cells):
        t = up.bg_tile(im.width, im.height)
        t.alpha_composite(im)
        c = t.crop((X0, Y0, X1, Y1)).resize((cw, chh), Image.NEAREST if i in (0, 2) else Image.LANCZOS)
        x = 8 + i * (cw + 8)
        sheet.paste(c.convert("RGB"), (x, lab))
        words, line, yy = nm.split(" "), "", 2
        for w_ in words:
            if d.textlength(line + " " + w_, font=fn) > cw and line:
                d.text((x, yy), line, fill=(230, 220, 160), font=fn)
                line, yy = w_, yy + 14
            else:
                line = (line + " " + w_).strip()
        d.text((x, yy), line, fill=(230, 220, 160), font=fn)
    sp_ = os.path.join(P.dir, "check_%s.png" % P.tag)
    sheet.save(sp_)
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    print("лист:", sp_)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("gpu", "warp", "frames", "check"):
        p = sub.add_parser(name)
        p.add_argument("--pose", type=int, default=1)
        p.add_argument("--dir", type=int, default=up.RENDER_DIR)
        if name == "gpu":
            p.add_argument("--stages", required=True, help="strip0,isolate0 | retouch,strip1,isolate1")
            p.add_argument("--models", default=None)
    a = ap.parse_args()
    if a.cmd == "gpu":                      # явный вызов: граф test_gpu_scripts видит загрузку модели
        cmd_gpu(a)
    else:
        {"warp": cmd_warp, "frames": cmd_frames, "check": cmd_check}[a.cmd](a)


if __name__ == "__main__":
    main()
