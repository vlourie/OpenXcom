"""ОСТАНОВЛЕН 03.10 по решению специалиста: манекен из примитивов вышел схематичной куклой (плоский торс, длинная
шея, руки без кистей, хват оружия потерян) - в генерацию не подавать. Позу и габариты задаёт оригинал, облик -
кукла инвентаря: tools/hdart/unit_direct.py.

Чистый референс позы для генерации юнита (специалист 03.10, после R-208): манекен с нормальной анатомией,
построенный по координатам, а не растяжкой готового снимка. Габариты задаёт оригинал: макушка и стопы (высота),
плечи (ширина), локти и кисти (хват), колени, щиколотки, носки и пятки - опорные точки kp.json позы (первые
координаты - оригинал, холст фигуры x4). Формы - капсулы с переменным радиусом, тень по нормали, свет сверху
слева; края считаются с запасом 8 отсчётов на пиксель холста x4 и усредняются (R-042). Цвета - кукла пилота:
тёмный комбинезон, рукава закатаны до локтя, голые предплечья, чёрные ботинки, светлые волосы, тёмные очки.
Оружия нет: оно - отдельный слой с заданным положением и дулом, кисти сжаты под хват. Меток во входе нет (R-204):
опорные точки и контур оригинала - только на проверочном листе.

    py -3.13 tools/hdart/unit_ref.py --pose 1
Выход art/units/pilot-gov4/ref/d<d>_p<n>/: ref.png (вход модели: кроп рендера на подложке, как у unit_pilot
render), ref_alpha.png (манекен на прозрачном, холст фигуры x4), check.png (оригинал x4 | референс | контур
оригинала поверх референса, точки), ref.json (габариты против оригинала)."""
import argparse
import json
import os
import sys
import time

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import item_photo as ip         # noqa: E402
import unit_pilot as up         # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
ENC = "utf-8-sig"
K = up.K
SS = 8                          # отсчётов на пиксель холста x4
OUT = os.path.join("art", "units", "pilot-gov4", "ref")
RAW = (896, 1120)               # размер входа рендера (кроп фигуры, как у unit_pilot render)
PANEL = (176, 176, 182)         # grey_light
LIGHT = np.array([-0.45, -0.55, 0.70])
LIGHT = LIGHT / np.linalg.norm(LIGHT)

SUIT = (54, 60, 74)
SUIT_CUFF = (66, 72, 88)
SKIN = (212, 160, 128)
HAIR = (222, 196, 122)
BOOT = (30, 30, 32)
GLASS = (22, 22, 26)
PATCH = (168, 32, 32)
ZIP = (186, 188, 194)


def blur(a, r):
    """Три прохода окна (2r+1) - почти гаусс, края повтором."""
    for _ in range(3):
        p = np.pad(a, r, mode="edge")
        c = np.pad(p.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
        n = 2 * r + 1
        a = (c[n:, n:] - c[:-n, n:] - c[n:, :-n] + c[:-n, :-n]) / float(n * n)
    return a


class Canvas:
    """Цвет и альфа на холсте фигуры x4 с запасом SS; части рисуются по порядку (дальняя - первой). Объём части -
    размытая маска как высота: тень мягкая, без шаров и колбас."""

    def __init__(self, w4, h4):
        self.w, self.h = w4 * SS, h4 * SS
        self.rgb = np.zeros((self.h, self.w, 3), np.float32)
        self.a = np.zeros((self.h, self.w), np.float32)

    # ---- маски частей (координаты холста x4)
    def grid(self, x0, y0, x1, y1):
        X0, Y0 = max(0, int(x0 * SS)), max(0, int(y0 * SS))
        X1, Y1 = min(self.w, int(np.ceil(x1 * SS))), min(self.h, int(np.ceil(y1 * SS)))
        yy, xx = np.mgrid[Y0:Y1, X0:X1].astype(np.float32)
        return (X0, Y0, X1, Y1), (xx + 0.5) / SS, (yy + 0.5) / SS

    def capsule(self, p, q, r1, r2):
        p, q = np.asarray(p, np.float32), np.asarray(q, np.float32)
        r = max(r1, r2)
        box, x, y = self.grid(min(p[0], q[0]) - r, min(p[1], q[1]) - r, max(p[0], q[0]) + r, max(p[1], q[1]) + r)
        v = q - p
        L2 = max(float(v @ v), 1e-6)
        t = np.clip(((x - p[0]) * v[0] + (y - p[1]) * v[1]) / L2, 0, 1)
        rr = r1 + (r2 - r1) * t
        m = (x - p[0] - t * v[0]) ** 2 + (y - p[1] - t * v[1]) ** 2 < rr * rr
        return box, m

    def ellipse(self, c, rx, ry, clip=None):
        box, x, y = self.grid(c[0] - rx, c[1] - ry, c[0] + rx, c[1] + ry)
        m = ((x - c[0]) / rx) ** 2 + ((y - c[1]) / ry) ** 2 < 1
        if clip is not None:
            m &= clip(x, y)
        return box, m

    def poly(self, pts):
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        box, x, y = self.grid(min(xs), min(ys), max(xs) + 1, max(ys) + 1)
        im = Image.new("L", (box[2] - box[0], box[3] - box[1]), 0)
        ImageDraw.Draw(im).polygon([((px * SS - box[0]), (py * SS - box[1])) for px, py in pts], fill=255)
        return box, np.asarray(im) > 127

    @staticmethod
    def union(*parts):
        X0 = min(b[0] for b, _m in parts)
        Y0 = min(b[1] for b, _m in parts)
        X1 = max(b[2] for b, _m in parts)
        Y1 = max(b[3] for b, _m in parts)
        m = np.zeros((Y1 - Y0, X1 - X0), bool)
        for b, mm in parts:
            m[b[1] - Y0:b[3] - Y0, b[0] - X0:b[2] - X0] |= mm
        return (X0, Y0, X1, Y1), m

    # ---- заливка части с объёмом
    def fill(self, part, col, depth=3.0, spec=0.10, amb=0.40, flat=False):
        """depth - на сколько пикселей x4 размыта высота: толщина формы на краю."""
        (X0, Y0, X1, Y1), m = part
        c = np.asarray(col, np.float32)
        if flat:
            v = np.broadcast_to(c, m.shape + (3,))
        else:
            r = max(1, int(depth * SS / 3))
            pad = 3 * r
            h = blur(np.pad(m.astype(np.float32), pad), r)[pad:-pad, pad:-pad]
            gy, gx = np.gradient(h)
            k = 3.0 * r
            n = np.stack([-gx * k, -gy * k, np.ones_like(h)], -1)
            n /= np.linalg.norm(n, axis=-1, keepdims=True)
            shade = amb + (1 - amb) * np.clip(n @ LIGHT, 0, 1)
            half = (LIGHT + np.array([0, 0, 1])) / np.linalg.norm(LIGHT + np.array([0, 0, 1]))
            hl = spec * np.clip(n @ half, 0, 1) ** 20
            v = c * shade[..., None] + 255.0 * hl[..., None]
        rgb = self.rgb[Y0:Y1, X0:X1]
        rgb[m] = v[m]
        self.a[Y0:Y1, X0:X1][m] = 1.0

    def down(self):
        """Усреднение SSxSS -> холст x4, RGBA (цвет без подложки)."""
        h, w = self.h // SS, self.w // SS
        a4 = self.a.reshape(h, SS, w, SS)
        c = (self.rgb * self.a[..., None]).reshape(h, SS, w, SS, 3).sum((1, 3)) / np.maximum(
            a4.sum((1, 3)), 1e-6)[..., None]
        return np.dstack([np.clip(c, 0, 255), a4.mean((1, 3)) * 255]).astype(np.float32)


def read_kp(d):
    with open(os.path.join(d, "kp.json"), encoding=ENC) as f:
        kp = json.load(f)
    return {k: np.array(v[0], np.float32) for k, v in kp.items() if not k.startswith("_")}


def unit(v):
    return v / max(float(np.linalg.norm(v)), 1e-6)


def mannequin(w4, h4, kp):
    """Манекен пилота по опорным точкам оригинала (холст фигуры x4). Пропорции - человека: толщины конечностей и
    размер стоп свои, не спрайта; положение суставов, кистей, стоп, макушки и плеч - оригинала."""
    C = Canvas(w4, h4)
    P = kp
    cx = float((P["head_l"][0] + P["head_r"][0]) / 2)
    top, chin = float(P["head_top"][1]), float(P["chin"][1])
    sh_line = float((P["shoulder_l"][1] + P["shoulder_r"][1]) / 2) + 4      # верх плеча
    shl = np.array([P["shoulder_l"][0] + 6, sh_line + 4])                  # плечевой сустав
    shr = np.array([P["shoulder_r"][0] - 6, sh_line + 4])
    hip_y = float((P["hip_l"][1] + P["hip_r"][1]) / 2)
    # ноги: брючина от таза до щиколотки, ботинок - голенище и стопа нормальной длины к носку оригинала
    for s in ("l", "r"):
        ank, toe = P["ankle_" + s], P["toe_" + s]
        # тазобедренный сустав уже внешнего края бедра; колено - между точкой оригинала и прямой бедро-щиколотка
        hip = np.array([cx + (-1 if s == "l" else 1) * 12.0, hip_y - 2])
        knee = 0.5 * P["knee_" + s] + 0.5 * (hip + (ank - hip) * 0.52)
        C.fill(C.union(C.capsule(hip, knee, 6.4, 5.2),
                       C.capsule(knee, ank + np.array([0, 1]), 5.4, 4.6)), SUIT, depth=3.5)
        sole = ank + np.array([0, 10])
        tip = sole + unit(toe - sole) * 9.0
        C.fill(C.union(C.capsule(ank + np.array([0, 1]), sole, 4.1, 4.3),
                       C.capsule(sole, tip, 4.3, 3.4)), BOOT, depth=2.5, spec=0.22)
        C.fill(C.capsule(ank + np.array([0, -1]), ank + np.array([0, 1.5]), 5.0, 5.0), SUIT_CUFF, depth=1.5)
    # торс: контур плеч, талии и таза
    w_sh = float(shr[0] - shl[0])
    torso = [(shl[0] - 2, sh_line + 3), (cx - 6, sh_line - 2), (cx + 6, sh_line - 2), (shr[0] + 2, sh_line + 3),
             (shr[0] + 1, sh_line + 12), (cx + w_sh * 0.30, sh_line + 22), (cx + w_sh * 0.29, hip_y - 6),
             (cx + 17, hip_y), (cx + 3, hip_y + 5), (cx - 3, hip_y + 5), (cx - 17, hip_y),
             (cx - w_sh * 0.29, hip_y - 6), (cx - w_sh * 0.30, sh_line + 22), (shl[0] - 1, sh_line + 12)]
    C.fill(C.union(C.poly(torso), C.capsule(shl, shr, 5.5, 5.5)), SUIT, depth=6.0)
    # шея, воротник, молния, нашивка на левой груди (справа на экране)
    C.fill(C.poly([(cx - 7, sh_line - 1), (cx, sh_line + 9), (cx + 7, sh_line - 1), (cx + 4, sh_line + 3),
                   (cx, sh_line + 11), (cx - 4, sh_line + 3)]), SUIT_CUFF, depth=1.5)
    C.fill(C.capsule((cx, sh_line + 9), (cx, hip_y - 2), 0.6, 0.6), ZIP, flat=True)
    C.fill(C.poly([(cx + 5, sh_line + 6), (cx + 11, sh_line + 6), (cx + 11, sh_line + 10), (cx + 5, sh_line + 10)]),
           PATCH, flat=True)
    # голова: лицо, каре, очки
    # голова взрослого: шестая часть роста (стойка широкая, колени согнуты), не голова спрайта (у него четверть)
    hry = (float(P["toe_l"][1]) - top) / 6.0 / 2
    hrx = hry * 0.78
    hy = sh_line - 7.0 - hry          # подбородок над плечами на длину шеи
    C.fill(C.capsule((cx, hy + hry - 3), (cx, sh_line), 3.4, 3.8), SKIN, depth=2.0)
    C.fill(C.ellipse((cx, hy + 0.8), hrx, hry), SKIN, depth=3.0)
    C.fill(C.ellipse((cx, hy - 1.6), hrx + 1.3, hry - 0.4,
                     clip=lambda x, y: (y < hy - 2.5) | ((np.abs(x - cx) > hrx * 0.66) & (y < hy + hry * 0.5))),
           HAIR, depth=3.0, spec=0.18)
    gy = hy + 0.6
    for sx in (-1, 1):
        C.fill(C.ellipse((cx + sx * hrx * 0.42, gy), hrx * 0.34, hry * 0.17), GLASS, depth=0.8, spec=0.5)
    C.fill(C.capsule((cx - 1.4, gy - 0.4), (cx + 1.4, gy - 0.4), 0.45, 0.45), GLASS, flat=True)
    # руки: плечо в рукаве, закатанный край у локтя, голое предплечье, кулак под хват
    for s, sh in (("l", shl), ("r", shr)):
        el, hand = P["elbow_" + s], P["hand_" + s]
        wrist = hand + unit(el - hand) * 3.2
        C.fill(C.capsule(sh, el, 4.9, 4.2), SUIT, depth=3.0)
        C.fill(C.union(C.capsule(el, wrist, 3.2, 2.5), C.ellipse(hand, 3.4, 2.9)), SKIN, depth=2.0, spec=0.12)
        C.fill(C.capsule(el + unit(sh - el) * 2.0, el + unit(wrist - el) * 0.6, 4.6, 4.5), SUIT_CUFF, depth=1.5)
    C.fill(C.ellipse(shr + np.array([3.5, 1.5]), 2.2, 2.8), PATCH, flat=True)   # нашивка на левом плече
    return C.down()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pose", type=int, default=1)
    ap.add_argument("--dir", type=int, default=up.RENDER_DIR)
    ap.add_argument("--kp", default=None, help="kp.json (по умолчанию art/units/pilot-gov4/refit/d<d>_p<n>)")
    a = ap.parse_args()
    os.chdir(ROOT)
    s = up.Sources()
    L = s.layers(up.POSES[a.pose], a.dir)
    full, _o = up.compose(L, s.classic, 1)
    crop, box = ip.crop_job(full)
    off4 = ((box[0] - ip.PAD) * K, (box[1] - ip.PAD) * K)
    c4 = (crop.width * K, crop.height * K)
    tag = "d%d_p%d" % (a.dir, a.pose)
    kp_dir = os.path.dirname(a.kp) if a.kp else os.path.join("art", "units", "pilot-gov4", "refit", tag)
    kp = read_kp(kp_dir)
    body = [l for l in L if l[1][0] == "unit"]                # оригинал без оружия
    o4, _own = up.compose(body, s.classic, K)
    W4, H4 = o4.size
    ref = mannequin(W4, H4, kp)
    od = os.path.join(OUT, tag)
    os.makedirs(od, exist_ok=True)
    ra = Image.fromarray(np.uint8(ref + 0.5), "RGBA")
    ra.save(os.path.join(od, "ref_alpha.png"))
    # вход модели: кроп фигуры на подложке в размере рендера
    pan = Image.new("RGBA", ra.size, PANEL + (255,))
    pan.alpha_composite(ra)
    cr = pan.crop((off4[0], off4[1], off4[0] + c4[0], off4[1] + c4[1])).convert("RGB").resize(RAW, Image.LANCZOS)
    cr.save(os.path.join(od, "ref.png"))
    # габариты против оригинала (без оружия)
    om = np.asarray(o4)[..., 3] > 0
    rm = ref[..., 3] > 127

    def box_of(m):
        ys, xs = np.nonzero(m)
        return [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]
    ob, rb = box_of(om), box_of(rm)
    rows = {}
    for nm, (y0, y1) in (("плечи (y 84-104)", (84, 104)), ("кисти (y 104-120)", (104, 120)),
                         ("стопы (y 156-170)", (156, 170))):
        def span(m):
            xs = np.nonzero(m[y0:y1].any(0))[0]
            return [int(xs.min()), int(xs.max()) + 1] if len(xs) else None
        rows[nm] = {"orig": span(om), "ref": span(rm)}
    rep = {"pose": a.pose, "dir": a.dir, "kp": os.path.join(kp_dir, "kp.json").replace("\\", "/"),
           "bbox_orig4": ob, "bbox_ref4": rb,
           "height_pct": round(100.0 * ((rb[3] - rb[1]) / (ob[3] - ob[1]) - 1), 1),
           "width_pct": round(100.0 * ((rb[2] - rb[0]) / (ob[2] - ob[0]) - 1), 1),
           "spans": rows, "iou_body": round(float((om & rm).sum() / (om | rm).sum()), 3),
           "input": os.path.join(od, "ref.png").replace("\\", "/"), "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
    with open(os.path.join(od, "ref.json"), "w", encoding=ENC) as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    # проверочный лист: оригинал x4 | референс | контур оригинала и точки поверх референса
    Z = 3
    X0, Y0, X1, Y1 = 40, 48, 152, 176
    cells = []
    orig = Image.new("RGBA", o4.size, PANEL + (255,))
    orig.alpha_composite(o4)
    cells.append(("оригинал x4 (без оружия)", orig.crop((X0, Y0, X1, Y1)).resize(((X1 - X0) * Z, (Y1 - Y0) * Z),
                                                                             Image.NEAREST)))
    cells.append(("референс (вход модели)", pan.crop((X0, Y0, X1, Y1)).resize(((X1 - X0) * Z, (Y1 - Y0) * Z),
                                                                           Image.LANCZOS)))
    ov = pan.crop((X0, Y0, X1, Y1)).resize(((X1 - X0) * Z, (Y1 - Y0) * Z), Image.LANCZOS).convert("RGB")
    er = np.zeros_like(om)                                  # контур оригинала: пиксель силуэта с пустым соседом
    er[1:-1, 1:-1] = om[1:-1, 1:-1] & ~(om[:-2, 1:-1] & om[2:, 1:-1] & om[1:-1, :-2] & om[1:-1, 2:])
    d = ImageDraw.Draw(ov)
    ys, xs = np.nonzero(er[Y0:Y1, X0:X1])
    for x, y in zip(xs, ys):
        d.rectangle((x * Z, y * Z, x * Z + Z - 1, y * Z + Z - 1), fill=(60, 230, 90))
    for nm, v in kp.items():
        x, y = (v[0] - X0) * Z, (v[1] - Y0) * Z
        d.ellipse((x - 4, y - 4, x + 4, y + 4), outline=(255, 220, 40), width=2)
    cells.append(("контур оригинала (зелёный) и опорные точки поверх референса", ov.convert("RGBA")))
    cw, ch = cells[0][1].size
    lab = 22
    sheet = Image.new("RGB", (len(cells) * (cw + 8) + 8, ch + lab + 8), (20, 20, 20))
    dd = ImageDraw.Draw(sheet)
    fn = up.font(13)
    for i, (nm, im) in enumerate(cells):
        x = 8 + i * (cw + 8)
        sheet.paste(im.convert("RGB"), (x, lab))
        dd.text((x, 4), nm, fill=(230, 220, 160), font=fn)
    sheet.save(os.path.join(od, "check.png"))
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    print("лист:", os.path.join(od, "check.png"))


if __name__ == "__main__":
    main()
