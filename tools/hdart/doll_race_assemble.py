"""Тела всех внешностей расы из основ без карты: основа торса, кожа внешности, её косметика мягким цветом.
Основы рисует doll_race_bodies.py, группы - fhuman_groups.json (docs/research/doll-pipeline-2026-11-03.md, 10.15-10.17).
Цифры кожи берутся с размытой классики: дизеринг даёт две светлоты вместо одной, медиана по пикселям врёт (05.11).
Куски B2 не вставляются: хуже всего на теле смотрелись именно они. Что идёт от шеи вниз (волосы, бусы) - дело кадра головы, поле neck в отчёте.
Выход art/doll/pipe_pilot/fhuman/: assembled/<внешность>.png, assembled.json, asm_N.png (классика | новое). layers/ и мод не трогает.
Голова на листе - B2 классики, только чтобы узнать внешность; * у имени - волосы на груди ждут кадра головы.

  E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe E:/OpenXCom/tools/hdart/doll_race_assemble.py [внешности через запятую]
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import build_pack as bp
import doll_b2_render as db
import doll_photo_pilot as dp

RACE = "FHUMAN"
ROOT = os.path.join(db.ROOT, "art", "doll", "pipe_pilot")
OUT = os.path.join(ROOT, RACE.lower())
# группа торса -> основа; F40 и F60 выделились только волосами, торс как у M2 и F14 (10.16)
BASE = {"F27": "M2", "F40": "M2", "M55": "F14", "F60": "F14", "F0": "M19", "F3": "F10", "F1": "F1"}
BASES = ("M2", "F14", "M19", "F10", "F1")
BY_EYE = {"F47": "M2"}  # кубики в классике, перепись и подбор их не видят (лист 05.11)
ROW = 69                # шея классики
HEAD_ROW = 66           # выше - черновая голова основы, её в теле нет
HEAD_X = db.W           # и левее этого столбца: у NEKOMIMI правее поднята кисть
TORSO = (72, 108)
CROTCH = (88, 102, 66, 95)  # строки и столбцы: трусы и волосы в паху, там стринги
GROUPS = "fhuman_groups.json"
SHEET_BOX = (50, 44, 110, 148)
WIDE_SKIN = False       # не кожа - только тёмное и бесцветное: цветная основа, её глубокая тень и белые блики перекрашиваются
LIFT = {}               # внешность -> прибавка к светлоте: у контрастной классики медиана темнее того, что видит глаз
S_MIN = 0.7             # контраст основы сжимается не сильнее этого
MARK_DIST, MARK_MIN = 18, 5
MOVE_GAIN = 30          # на другую основу - если своего меньше хотя бы на столько пикселей
DITHER = 1.0            # размытие классики против дизеринга, пиксели k=1
TINT_SIGMA = 0.6
TINT_GAIN = 1.3         # возмещает, что размытие дизеринга срезало пик пятна
CLEAN_AB = 12           # кривая кожи без пятен: иначе блики берут их цвет
SPOT_AB, SPOT_DARK, SPOT_MIN = 7, -14, 6
K = dp.K
F = db.sprite_files()
PALR = db.game_palette()
PAL = np.asarray(PALR, np.float32)[:, :3]
LAB = bp._rgb_to_lab(PAL[None] / 255.0)[0]
CLASSIC, SOFT, LAYERS = {}, {}, {}


def classic(n):
    if n not in CLASSIC:
        CLASSIC[n] = db.load_indices(F["%s__2__%s_NUDE" % (RACE, n)])
    return CLASSIC[n]


def soft_lab(rgb, a, sigma=DITHER):
    w = cv2.GaussianBlur(a.astype(np.float32), (0, 0), sigma)
    b = cv2.GaussianBlur(rgb * a[..., None], (0, 0), sigma) / np.maximum(w, 1e-3)[..., None]
    return bp._rgb_to_lab(np.clip(b, 0, 1))


def curve_of(lab, m):
    """Кривая светлота -> цвет, сглаженная: скачок кривой рисует на теле полосы по линии равной светлоты."""
    cur = []
    for b in np.arange(4, 100, 4):
        s = m & (np.abs(lab[..., 0] - b) < 4)
        if s.sum() >= 12:
            cur.append((b, *np.median(lab[s], 0)[1:]))
    cur = np.array(cur, np.float32)
    if len(cur) > 2:
        for c in (1, 2):
            cur[:, c] = cv2.GaussianBlur(cur[:, c].reshape(-1, 1), (0, 0), 1.0, borderType=cv2.BORDER_REPLICATE).ravel()
    return cur


def on_curve(L, cur):
    return np.interp(L, cur[:, 0], cur[:, 1]), np.interp(L, cur[:, 0], cur[:, 2])


def soft_of(n):
    """Размытая классика: Lab, кожа тела, кривая, квартили светлоты."""
    if n not in SOFT:
        idx = classic(n)
        lab = soft_lab(PAL[idx] / 255.0, idx > 0)
        m = cv2.erode((idx > 0).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
        m[:ROW] = False
        m[CROTCH[0]:CROTCH[1], CROTCH[2]:CROTCH[3]] = False
        SOFT[n] = (lab, m, curve_of(lab, m), np.percentile(lab[..., 0][m], (25, 50, 75)))
    return SOFT[n]


def skin_islands(w, area=300):
    """Кожа - большие связные области веса; островок посреди чёрного - блик наклейки или стрингов, а не кожа. Он светлел
    при сдвиге к светлой коже в полосу (F48, M10, лист 05.11). Закрытие тёмного и поиск кругов тут не годятся: у тёмной
    основы наклейка сливается с тенью под грудью."""
    n_c, lab, st, _c = cv2.connectedComponentsWithStats((w > 0.1).astype(np.uint8), connectivity=8)
    small = np.isin(lab, [i for i in range(1, n_c) if st[i, 4] < area])
    return cv2.dilate(small.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0


def base_layer(n):
    if n not in LAYERS:
        im = np.asarray(Image.open(os.path.join(OUT, "bases", n.lower() + ".png")).convert("RGBA"), np.float32)
        lab = bp._rgb_to_lab(im[..., :3] / 255.0)
        L, chroma = lab[..., 0], np.hypot(lab[..., 1], lab[..., 2])
        # чёрные наклейки и стринги - не кожа
        w = np.clip((L - 16) / 10, 0, 1) * np.clip((chroma - 5) / 6, 0, 1) * (im[..., 3] / 255.0)
        if WIDE_SKIN:
            w = (1 - np.clip((30 - L) / 10, 0, 1) * np.clip((11 - chroma) / 6, 0, 1)) * (im[..., 3] / 255.0)
        w[skin_islands(w)] = 0
        small = cv2.resize(np.dstack([im[..., :3] / 255.0, w]), (db.W, db.H), interpolation=cv2.INTER_AREA)
        a = small[..., 3] > 0.9
        s = soft_lab(small[..., :3], a)
        m = cv2.erode(a.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
        m[:ROW] = False
        LAYERS[n] = (im, lab, w, curve_of(lab, (w > 0.9) & (np.arange(im.shape[0])[:, None] >= ROW * K)),
                     np.percentile(s[..., 0][m], (25, 50, 75)))
    return LAYERS[n]


def own_mask(base, look):
    """Чем классика внешности отличается от классики основы, если кожу привести таблицей (k=1)."""
    a, b = classic(base), classic(look)
    both = (a[ROW:] > 0) & (b[ROW:] > 0)
    u, c = np.unique(a[ROW:][both].astype(np.int64) * 256 + b[ROW:][both], return_counts=True)
    t, best = np.arange(256), np.zeros(256, np.int64)
    for x, n in zip(u.tolist(), c.tolist()):
        if n > best[x // 256]:
            best[x // 256], t[x // 256] = n, x % 256
    own = (np.linalg.norm(LAB[t[a]] - LAB[b], axis=-1) > MARK_DIST) & (b > 0)
    own[:ROW] = False
    own[CROTCH[0]:CROTCH[1], CROTCH[2]:CROTCH[3]] = False
    return own


def neck_items(base, look):
    """Пятна, идущие от шеи вниз: волосы на груди и бусы. Их нарисует кадр головы."""
    own = own_mask(base, look)
    n_c, lab, st, _c = cv2.connectedComponentsWithStats(own.astype(np.uint8), connectivity=8)
    keep = np.zeros_like(own)
    for i in range(1, n_c):
        if st[i, 1] <= ROW + 1 and st[i, 4] >= MARK_MIN:
            keep |= lab == i
    return keep


def choose_base(group_base, look):
    """Группа торса грубая (порог 40 пикселей): кубики F47 попали к гладкому животу F14. Берём основу с наименьшим своим."""
    cnt = {}
    for b in BASES:
        o = own_mask(b, look)
        cnt[b] = int(o[TORSO[0]:TORSO[1]].sum())
    best = min(cnt, key=cnt.get)
    return best if cnt[best] + MOVE_GAIN <= cnt[group_base] else group_base


def residual(base, look):
    """Что классика внешности делает не так, как классика основы при той же светлоте. Медиана по телу, пятна на 5% площади её не сдвигают."""
    lb, mb, _c, _q = soft_of(base)
    lk, mk, _c, _q = soft_of(look)
    m = mb & mk
    exp = []
    for b in np.arange(4, 100, 3):
        s = m & (np.abs(lb[..., 0] - b) < 3)
        if s.sum() >= 12:
            exp.append((b, *np.median(lk[s], 0)))
    exp = np.array(exp, np.float32)
    return lk - np.dstack([np.interp(lb[..., 0], exp[:, 0], exp[:, c]) for c in (1, 2, 3)]), m


def tint_maps(base, look, neck):
    """Косметика k=1 мягким цветом; мелочь отсекается порогом. Кривая кожи - без пятен, иначе блики берут их цвет."""
    r, m = residual(base, look)
    lk, _m, _c, q = soft_of(look)
    cur = curve_of(lk, m & (np.hypot(r[..., 1], r[..., 2]) < CLEAN_AB))
    ca, cb = on_curve(lk[..., 0], cur)
    ra, rb = lk[..., 1] - ca, lk[..., 2] - cb
    # кубики другой основы лежат на кривой кожи и косметикой не считаются; пятно - цвет мимо кривой или тёмная полоса
    free = m & ~(cv2.dilate(neck.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0)
    spot = free & ((np.hypot(ra, rb) > SPOT_AB) | (r[..., 0] < SPOT_DARK))
    n_c, lab, st, _c = cv2.connectedComponentsWithStats(spot.astype(np.uint8), connectivity=8)
    out = [np.zeros((db.H * K, db.W * K), np.float32) for _ in range(3)]
    for i in range(1, n_c):
        if st[i, 4] < SPOT_MIN:
            continue
        c = lab == i
        shift = (np.median(r[..., 0][c]), np.median(ra[c]) * TINT_GAIN, np.median(rb[c]) * TINT_GAIN)
        big = cv2.resize(cv2.GaussianBlur(c.astype(np.float32), (0, 0), TINT_SIGMA), (db.W * K, db.H * K), interpolation=cv2.INTER_CUBIC)
        big = np.clip((big - 0.3) / 0.3, 0, 1)
        for o, v in zip(out, shift):
            o += big * v
    return out, cur, q


def assemble(base, look):
    im, lab, w, cur_b, q_b = base_layer(base)
    neck = neck_items(base, look)
    if base == look:
        out = im.copy()
        tint = 0.0
    else:
        (dL, da, db_), cur, q = tint_maps(base, look, neck)
        s = np.clip((q[2] - q[0]) / max(q_b[2] - q_b[0], 1.0), S_MIN, 1.0)   # выше 1 складки тёмной кожи стали чёрной обводкой (F37, F15)
        L = q[1] + (lab[..., 0] - q_b[1]) * s + dL
        # блики и наклейки сдвигают медиану основы: без поправки всё выходит на 5 темнее, бледное - оливковым
        m = soft_of(look)[1] & (cv2.resize(w, (db.W, db.H), interpolation=cv2.INTER_AREA) > 0.9)
        L = np.clip(L + np.clip(q[1] - np.median(cv2.resize(L.astype(np.float32), (db.W, db.H), interpolation=cv2.INTER_AREA)[m]), -12, 12) + LIFT.get(look, 0), 6, 97)
        ca0, cb0 = on_curve(lab[..., 0], cur_b)
        ca, cb = on_curve(L, cur)
        # остаток цвета основы - в долю цветности цели: на тёмной коже те же ±6 выводят слабую линию основы в штрих
        c = np.clip(np.hypot(ca, cb) / np.maximum(np.hypot(ca0, cb0), 1.0), 0.0, 1.0)
        new = np.dstack([L, ca + c * np.clip((lab[..., 1] - ca0) * 0.8, -6, 6) + da,
                         cb + c * np.clip((lab[..., 2] - cb0) * 0.8, -6, 6) + db_])
        rgb = bp._lab_to_rgb(lab * (1 - w[..., None]) + new * w[..., None]) * 255.0
        out = np.dstack([rgb, im[..., 3]])
        tint = float((np.abs(dL) + np.abs(da) + np.abs(db_) > 4)[w > 0.5].mean() * 100)      # доля кожи
    out[:HEAD_ROW * K, :HEAD_X * K, 3] = 0
    return Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8), "RGBA"), int(neck.sum()), tint


def head_over(look):
    im = Image.new("RGBA", (db.W * K, db.H * K), (0, 0, 0, 0))
    for n in ("%s__10__HEAD_%s" % (RACE, look), "%s__13__HAIR_%s" % (RACE, look)):
        if n in F:
            bl, _how = dp.b2_layer(n)
            im.alpha_composite(bl if bl is not None else
                               Image.fromarray(db.to_rgba(db.load_indices(F[n]), PALR), "RGBA").resize(im.size, Image.NEAREST))
    return im


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    groups = json.load(open(os.path.join(ROOT, GROUPS), encoding="utf-8-sig"))
    os.makedirs(os.path.join(OUT, "assembled"), exist_ok=True)
    only = sys.argv[1].split(",") if len(sys.argv) > 1 else None
    todo, moved = [], []
    for g, m in groups.items():
        for n in m:
            if only is None or n in only:
                base = n if n in BASES else BY_EYE.get(n) or choose_base(BASE[g], n)
                if base != BASE[g]:
                    moved.append("%s %s>%s" % (n, BASE[g], base))
                todo.append((base, n))
    print("другая основа:", len(moved), moved, flush=True)
    todo.sort(key=lambda x: (x[0], x[1].rstrip("0123456789"), int(x[1][len(x[1].rstrip("0123456789")):])))
    box = tuple(v * K for v in SHEET_BOX)
    w, h = (box[2] - box[0]) // 2, (box[3] - box[1]) // 2
    FONT = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 15)
    per, page = 8, 24
    stat = {}
    for p in range(0, len(todo), page):
        part = todo[p:p + page]
        rows = (len(part) + per - 1) // per
        sheet = Image.new("RGB", (per * (2 * w + 6), rows * (h + 20)), (15, 15, 18))
        d = ImageDraw.Draw(sheet)
        for i, (base, n) in enumerate(part):
            lay, neck, tint = assemble(base, n)
            lay.save(os.path.join(OUT, "assembled", n.lower() + ".png"))
            stat[n] = {"base": base, "neck": neck, "tint": round(tint, 2)}
            cl = Image.new("RGBA", (db.W, db.H), (40, 42, 50, 255))
            cl.alpha_composite(Image.fromarray(db.to_rgba(classic(n), PALR), "RGBA"))
            for nm in ("%s__10__HEAD_%s" % (RACE, n), "%s__13__HAIR_%s" % (RACE, n)):
                if nm in F:
                    cl.alpha_composite(Image.fromarray(db.to_rgba(db.load_indices(F[nm]), PALR), "RGBA"))
            cl = cl.resize((db.W * K, db.H * K), Image.NEAREST)
            new = Image.new("RGBA", (db.W * K, db.H * K), (40, 42, 50, 255))
            new.alpha_composite(lay)
            new.alpha_composite(head_over(n))
            x, y = (i % per) * (2 * w + 6), (i // per) * (h + 20)
            d.text((x + 2, y + 1), "%s (%s)%s" % (n, base, " *" if neck >= 20 else ""), fill=(255, 230, 0), font=FONT)
            sheet.paste(cl.convert("RGB").crop(box).resize((w, h), Image.LANCZOS), (x, y + 20))
            sheet.paste(new.convert("RGB").crop(box).resize((w, h), Image.LANCZOS), (x + w, y + 20))
        fn = os.path.join(OUT, "asm_%d.png" % (p // page + 1))
        sheet.save(fn)
        print(fn, sheet.size, flush=True)
    json.dump(stat, open(os.path.join(OUT, "assembled.json"), "w", encoding="utf-8-sig"), ensure_ascii=False, indent=0)
    print("собрано", len(stat), flush=True)


if __name__ == "__main__":
    main()
