"""Без карты: одно тело M24 + перекраска в тёмную кожу + своё у внешности (волосы, вещи, метки) из прежнего слоя.
Прежние слои тел - layers_before_one_body, кадр тела - body_master_M24.png.
doll_recolor_try.py check            - цифры и лист тела
doll_recolor_try.py <looks|all> <префикс>  - пары прежнее | новое, по 8 на лист
doll_recolor_try.py write            - записать все 120 слоёв тел в layers"""
import glob
import json
import os
import sys
from collections import Counter
sys.path.insert(0, r"E:\OpenXCom\tools\hdart")
sys.stdout.reconfigure(encoding="utf-8")
import cv2
import numpy as np
from PIL import Image, ImageDraw
import build_pack as bp
import doll_pipe_pilot as P

dp, db = P.dp, P.db
F = db.sprite_files()
PAL = db.game_palette()
pal = np.asarray(PAL, np.float32).reshape(-1, 3 if len(np.asarray(PAL).ravel()) % 3 == 0 else 4)[:, :3]
P.FILES, P.PAL = F, PAL
P.cp.FILES, P.cp.PAL = F, PAL
LAY = os.path.join(P.OUT, "layers_before_one_body")
OUT_LAY = os.path.join(P.OUT, "layers")
S = r"C:\Users\user\AppData\Local\Temp\claude\E--OpenXCom\7166cd73-0ba7-42c8-9a59-eae0ca9648db\scratchpad"
K = dp.K
LOOKS = json.load(open(r"E:\OpenXCom\tools\hdart\doll_looks.json", encoding="utf-8-sig"))
idx = {k: db.load_indices(F["%s__%d__%s_NUDE" % (dp.RACE, dp.BODY, k)]) for k in LOOKS}
A, B = idx["F5"], idx["M42"]
ROW = P.FACE_BOX[3] + 3
both = (A > 0) & (B > 0)
pairs = Counter(zip(A[both].tolist(), B[both].tolist()))
best = {}
for (x, y), n in pairs.items():
    if n > best.get(x, (0, 0))[0]:
        best[x] = (n, y)
LUT = np.arange(256)
RAMP = sorted([(x, v[1]) for x, v in best.items() if v[0] >= 15], key=lambda p: p[1])   # бронза -> тёмная, от светлой тени к тёмной
for x, y in RAMP:
    LUT[x] = y
PAL_LAB = bp._rgb_to_lab(pal[None] / 255.0)[0]


def lab_of(i):
    return PAL_LAB[i]


def hd_curve(a):
    """Шкала кожи: основа -> M42 по готовым кадрам, те же доли светлоты. Кадры расписаны сочнее палитры классики."""
    b = np.asarray(Image.open(glob.glob(os.path.join(LAY, "*__m42_nude.png"))[0]).convert("RGB"), np.float32)
    h, w = a.shape[:2]
    sk = np.isin(A, [x for x, y in RAMP]) & (LUT[A] == B)
    sk[:ROW] = False
    sk = cv2.erode(cv2.resize(sk.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST), np.ones((5, 5), np.uint8)) > 0
    la, lb = bp._rgb_to_lab(a / 255.0)[sk], bp._rgb_to_lab(b / 255.0)[sk]
    la, lb = la[la[:, 0] > 18], lb[lb[:, 0] > 12]   # чёрное не кожа
    la, lb = la[np.argsort(la[:, 0])], lb[np.argsort(lb[:, 0])]
    rows = []
    for q in range(16):
        pa = la[len(la) * q // 16:len(la) * (q + 1) // 16]
        pb = lb[len(lb) * q // 16:len(lb) * (q + 1) // 16]
        rows.append(np.r_[np.median(pa, 0), np.median(pb, 0)])
    return np.array(rows)


def recolor(rgb):
    """Бронза -> тёмная кожа: кривая по светлоте из пар шкал классики, мазок (отступ от шкалы по a, b) остаётся."""
    lab = bp._rgb_to_lab(rgb / 255.0)
    L = lab[..., 0]
    xs = np.r_[0.0, CURVE[:, 0]]
    tgt = [np.interp(L, xs, np.r_[v0, CURVE[:, 3 + c]]) for c, v0 in enumerate((0.0, 0.0, 0.0))]
    src = [np.interp(L, xs, np.r_[0.0, CURVE[:, c]]) for c in (1, 2)]
    top = L > CURVE[-1, 0]
    out = np.zeros(lab.shape, np.float32)
    out[..., 0] = tgt[0] + np.where(top, L - CURVE[-1, 0], 0) * 0.8
    out[..., 1] = tgt[1] + np.clip((lab[..., 1] - src[0]) * 0.8, -8, 8)   # без клипа красные точки в глубоких тенях
    out[..., 2] = tgt[2] + np.clip((lab[..., 2] - src[1]) * 0.8, -8, 8)
    # чёрное (стринги, наклейки) не трогать
    ch = np.hypot(lab[..., 1], lab[..., 2])
    w = (np.clip((ch - 8) / 10, 0, 1) * np.clip((L - 14) / 10, 0, 1))[..., None]
    out = lab * (1 - w) + out * w
    return bp._lab_to_rgb(out) * 255.0


def layer(pat):
    return np.asarray(Image.open(glob.glob(os.path.join(LAY, pat))[0]).convert("RGBA"), np.float32)


MASTER_LOOK = "M24"
_mname = "%s__%d__%s_NUDE" % (dp.RACE, dp.BODY, MASTER_LOOK)
_msil = dp.layer_mask(F, _mname) | dp.layer_mask(F, "%s__%d__HEAD_%s" % (dp.RACE, dp.HEAD, MASTER_LOOK))
_f4, _sd = P.skin_match(P.full4(np.asarray(Image.open(os.path.join(P.OUT, "body_master_M24.png")).convert("RGB"))), MASTER_LOOK, _msil)
MASTER = np.asarray(P.layer_from(P.clean_body(_f4, MASTER_LOOK), dp.layer_mask(F, _mname)).convert("RGBA"), np.float32).copy()
CURVE = hd_curve(MASTER[..., :3])
# бледные серые мазки и блики кадра: цвет кожи той же светлоты, светлота остаётся. Иначе в тёмной коже они серые
_lab = bp._rgb_to_lab(MASTER[..., :3] / 255.0)
_dk = cv2.dilate((_lab[..., 0] < 30).astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
_ea = np.interp(_lab[..., 0], CURVE[:, 0], CURVE[:, 1])
_eb = np.interp(_lab[..., 0], CURVE[:, 0], CURVE[:, 2])
_sm = (np.hypot(_lab[..., 1], _lab[..., 2]) < 0.75 * np.hypot(_ea, _eb)) & (_lab[..., 0] > 45) & (MASTER[..., 3] > 0) & ~_dk
_sm[:52 * K] = False
_w = np.clip(cv2.GaussianBlur(cv2.dilate(_sm.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(np.float32), (0, 0), 2.0) * 1.5, 0, 1)
_lab[..., 1] = _lab[..., 1] * (1 - _w) + _ea * _w
_lab[..., 2] = _lab[..., 2] * (1 - _w) + _eb * _w
MASTER[..., :3] = bp._lab_to_rgb(_lab) * 255.0
print("серых мазков и бликов, пикселей:", int(_sm.sum()))
_ml =bp._rgb_to_lab(MASTER[..., :3] / 255.0)[..., 0]
_z = ((_ml < 25) & (MASTER[..., 3] > 200)).astype(np.uint8)
_z[:ROW * K] = 0
ZONE = cv2.resize(cv2.dilate(_z, np.ones((7 * K + 1, 7 * K + 1), np.uint8)), (A.shape[1], A.shape[0]), interpolation=cv2.INTER_AREA) > 0   # шире чужой наклейки
DARK =np.dstack([recolor(MASTER[..., :3]), MASTER[..., 3]])
RGB = pal


def base_of(k):
    s = idx[k]
    return "F5" if (s[ROW:] != A[ROW:]).sum() <= (s[ROW:] != B[ROW:]).sum() else "M42"


def own_mask(k):
    """Своё у внешности: где классика заметно отличается от тела F5, приведённого к её коже."""
    s = idx[k]
    M = idx[MASTER_LOOK]
    ref = M if base_of(k) == "F5" else LUT[M]
    la, lb = PAL_LAB[s], PAL_LAB[ref]
    far = np.hypot.reduce([la[..., 0] - lb[..., 0], la[..., 1] - lb[..., 1], la[..., 2] - lb[..., 2]]) > 14
    far |= (s > 0) != (M > 0)
    far[ROW:] = (s != (A if base_of(k) == "F5" else B))[ROW:]   # ниже шеи база совпадает точно: любая разница - вещь
    return far & ((s > 0) | (M > 0))


def compose(k):
    cur = layer("*__%s_nude.png" % k.lower())
    base = MASTER if base_of(k) == "F5" else DARK
    m = cv2.resize(own_mask(k).astype(np.uint8), (cur.shape[1], cur.shape[0]), interpolation=cv2.INTER_NEAREST)
    m = cv2.dilate(m, np.ones((K + 1, K + 1), np.uint8))
    # у наклеек и стрингов из своего кадра берём только вещи: не кожу и не его чёрную наклейку
    lab = bp._rgb_to_lab(cur[..., :3] / 255.0)
    col = 3 if base_of(k) == "M42" else 0
    sa = np.interp(lab[..., 0], CURVE[:, col], CURVE[:, col + 1])
    sb = np.interp(lab[..., 0], CURVE[:, col], CURVE[:, col + 2])
    hue = np.hypot(lab[..., 1] - sa, lab[..., 2] - sb)
    black = cv2.morphologyEx((lab[..., 0] < 30).astype(np.uint8), cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    black = cv2.dilate(black, np.ones((7, 7), np.uint8)) > 0
    item = ((hue > 14) | ((np.hypot(lab[..., 1], lab[..., 2]) < 14) & (lab[..., 0] > 50))) & ~black
    item = cv2.dilate(item.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    zone = cv2.resize(ZONE.astype(np.uint8), (cur.shape[1], cur.shape[0]), interpolation=cv2.INTER_NEAREST) > 0
    foreign = idx[k] > 0
    foreign &= ~np.isin(idx[k], np.unique((A if base_of(k) == "F5" else B)[ROW:]))   # индекс, которого на теле нет: вещь
    foreign = cv2.resize(foreign.astype(np.uint8), (cur.shape[1], cur.shape[0]), interpolation=cv2.INTER_NEAREST)
    foreign = cv2.dilate(foreign, np.ones((K + 1, K + 1), np.uint8)) > 0
    m[zone & ~item & ~foreign] = 0
    m[92 * K:100 * K, 72 * K:88 * K] = 0   # метка классики в паху: закрыта стрингами, из своего кадра тянула их обрывок
    if k in ("M44", "F25", "M27", "M55"):   # лист 04.11: своя тёмная точка классики у наклейки вырывала из неё кусок
        m[cv2.dilate(((base[..., :3].mean(2) < 45) & (base[..., 3] > 200)).astype(np.uint8), np.ones((8 * K + 1, 8 * K + 1), np.uint8)) > 0] = 0
    m[base[..., 3] < 250] = 1
    w = cv2.GaussianBlur(m.astype(np.float32), (0, 0), 1.5)
    w = np.maximum(w, (base[..., 3] < 250).astype(np.float32))[..., None]
    rgb = base[..., :3] * (1 - w) + cur[..., :3] * w
    return np.dstack([rgb, cur[..., 3]])


BOX = (40 * K, 30 * K, 120 * K, 150 * K)
W, H = 240, 360
ZOOM = len(sys.argv) > 3 and sys.argv[3] == "zoom"
if ZOOM:
    BOX = (56 * K, 60 * K, 104 * K, 110 * K)
    W, H = 384, 400


def show(body, head=None):
    im = Image.new("RGBA", (body.shape[1], body.shape[0]), dp.PANEL + (255,))
    im.alpha_composite(Image.fromarray(np.clip(body + 0.5, 0, 255).astype(np.uint8), "RGBA"))
    if head is not None:
        im.alpha_composite(Image.fromarray(np.clip(head + 0.5, 0, 255).astype(np.uint8), "RGBA"))
    return im.crop(BOX).convert("RGB").resize((W, H), Image.LANCZOS)


if sys.argv[1] == "write":
    for k in sorted(LOOKS):
        fn = os.path.basename(glob.glob(os.path.join(LAY, "*__%s_nude.png" % k.lower()))[0])
        Image.fromarray(np.clip(compose(k) + 0.5, 0, 255).astype(np.uint8), "RGBA").save(os.path.join(OUT_LAY, fn))
    print("записано слоёв:", len(LOOKS), OUT_LAY)
    sys.exit()

if sys.argv[1] == "clean":
    # кандидаты в единое тело: классика ниже шеи совпала с чистым телом
    names = [k for k in sorted(LOOKS) if (idx[k][ROW:] == (A if base_of(k) == "F5" else B)[ROW:]).all()]
    print(len(names), names)
    W, H = 240, 360
    BOX = (40 * K, 60 * K, 120 * K, 150 * K)
    per = 8
    sheet = Image.new("RGB", (per * (W + 4), ((len(names) + per - 1) // per) * (H + 4)), (15, 15, 18))
    for i, k in enumerate(names):
        t = show(layer("*__%s_nude.png" % k.lower()))
        ImageDraw.Draw(t).text((3, 3), k, fill=(255, 255, 0))
        sheet.paste(t, ((i % per) * (W + 4), (i // per) * (H + 4)))
    sheet.save(os.path.join(S, "z_clean.png"))
    print(sheet.size)
    sys.exit()

if sys.argv[1] == "check":
    mapped = LUT[A]
    print("шкала бронза -> тёмная:", RAMP)
    sk = both & np.isin(A, [x for x, y in RAMP])
    print("пикселей кожи F5 и M42 вместе", int(sk.sum()), "; точно по шкале", int((mapped == B)[sk].sum()), "; не дальше 1 тени", int((np.abs(mapped.astype(int) - B.astype(int)) <= 1)[sk].sum()), "; не дальше 2", int((np.abs(mapped.astype(int) - B.astype(int)) <= 2)[sk].sum()))
    low = sk.copy()
    low[:ROW] = False
    print("то же ниже шеи", int(low.sum()), int((mapped == B)[low].sum()), int((np.abs(mapped.astype(int) - B.astype(int)) <= 2)[low].sum()))
    print("силуэт ниже шеи F5/M42 разный:", int(((A > 0) != (B > 0))[ROW:].sum()))
    own = np.array([own_mask(k).sum() for k in LOOKS])
    print("своего у внешности, пикселей классики: медиана", int(np.median(own)), "макс", int(own.max()), "из", int((A > 0).sum()), "; доля медианы %.0f%%" % (100 * np.median(own) / (A > 0).sum()))
    base_n = Counter(base_of(k) for k in LOOKS)
    print("базы", base_n)
    sheet = Image.new("RGB", (4 * (W + 4), H), (15, 15, 18))
    size = (MASTER.shape[1], MASTER.shape[0])
    cl = Image.new("RGBA", size, dp.PANEL + (255,))
    cl.alpha_composite(dp.classic(F, PAL, ["%s__%d__M42_NUDE" % (dp.RACE, dp.BODY)]).convert("RGBA").resize(size, Image.NEAREST))
    tiles = [show(MASTER), show(DARK), show(layer("*__m42_nude.png")), cl.crop(BOX).convert("RGB").resize((W, H), Image.LANCZOS)]
    for i, (t, name) in enumerate(zip(tiles, ("F5 body", "F5 recolored", "M42 own frame", "M42 classic"))):
        ImageDraw.Draw(t).text((3, 3), name, fill=(255, 255, 0))
        sheet.paste(t, (i * (W + 4), 0))
    sheet.save(os.path.join(S, "z_recolor_base.png"))
    print(sheet.size)
    sys.exit()

looks = sorted(LOOKS) if sys.argv[1] == "all" else sys.argv[1].split(",")
prefix = sys.argv[2]
per, rows = (2, 2) if ZOOM else (4, 2)
page = per * rows
for p in range(0, len(looks), page):
    part = looks[p:p + page]
    sheet = Image.new("RGB", (per * (2 * W + 8), ((len(part) + per - 1) // per) * (H + 4)), (15, 15, 18))
    for i, k in enumerate(part):
        head = np.asarray(Image.open(glob.glob(os.path.join(OUT_LAY, "*__head_%s.png" % k.lower()))[0]).convert("RGBA"), np.float32)
        x, y = (i % per) * (2 * W + 8), (i // per) * (H + 4)
        t = show(layer("*__%s_nude.png" % k.lower()), head)
        ImageDraw.Draw(t).text((3, 3), k, fill=(255, 255, 0))
        sheet.paste(t, (x, y))
        sheet.paste(show(compose(k), head), (x + W, y))
    fn = os.path.join(P.OUT, "%s_%d.png" % (prefix, p // page + 1))
    sheet.save(fn)
    print(fn, sheet.size)
