"""Точный движок стен: увеличение стены ВМЕСТЕ с её соседями по карте - без швов на стыках.

Прежние способы (текущий HD, A и B2 WALL_FINAL_SELECT) увеличивали каждый кадр отдельно: край кадра
продолжался заливкой наружу (fill_outside), а на карте рядом стоит другой кадр - и на стыке двух кадров
увеличитель видел разное. Здесь кадр увеличивается в поле соседей так, как они стоят на картах
(census/walls/exact/neighbors.json, wall_neighbors.py): самый частый сосед с каждой стороны линии стены,
этажом выше и ниже. Увеличитель локальный и не зависит от сдвига (сдвиги соседей кратны пикселю базы), и
тот же сосед на карте получает своё изображение из того же поля - стык считается как одна картинка.

  * цвет - классика индексами PCK в боевой палитре (wall_final_render.Classic), поле - соседи, кадр сверху;
  * A  (xbrz)   xBRZ x4 поля, вырезка кадра;
  * B2 (b2)     A плюс мелкая фактура Real-ESRGAN x4plus по тому же полю (wall_restore.detail);
  * альфа - всегда маска оригинала (wall_restore.alpha_of: sil4_frame, у сквозных sil4_frame_open);
  * зеркала: кадр, который побайтно есть зеркало уже нарисованного, с зеркальными соседями - переворот
    готового (правая/левая стена, нижние правая/левая - одна картинка, а не две похожие).

B2 грузит модель на видеокарту - только через gpuq. --no-model даёт один A.

  wall_exact.py [--out census/walls/exact/render] [--no-model] [--limit N] [--only хэш,хэш]

Выход: <out>/xbrz/<картинка>.png, <out>/b2/<картинка>.png (128x160) и <out>/render.tsv. В мод не кладётся.
"""
import argparse
import csv
import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                                  # noqa: E402
from PIL import Image                               # noqa: E402
import map_mockup as mm                             # noqa: E402
import sprite_scale as ss                           # noqa: E402
import wall_final_render as wf                      # noqa: E402
import wall_restore as wr                           # noqa: E402
import wall_section as ws                           # noqa: E402

ENC = "utf-8-sig"
ROOT = os.path.dirname(os.path.dirname(HERE))
NEIGHBORS = "census/walls/exact/neighbors.json"
K = 4
PAD = 6                  # поле вокруг всех соседей, пикселей базы
PRESENT = 0.35           # сосед берётся, если на этом месте стоит хоть что-то в такой доле мест
TOP_SHARE = 0.5          # ...и самая частая картинка - не меньше половины того, что там стоит


def rows():
    with open(os.path.join(ROOT, wf.FRAMES), encoding=ENC, newline="") as f:
        rs = list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))
    rs.sort(key=lambda r: -int(r["вес_мест"] or 0))
    return rs


class Pics:
    """Картинка -> индексы классики (кадр-представитель), хэши прямо и в зеркале."""

    def __init__(self, cl, rs):
        self.cl, self.frames, self.cache = cl, {}, {}
        for r in rs:
            self.frames[r["картинка"]] = [wf.parse_frame(t) for t in r["кадры"].split()]

    def idx(self, p):
        if p not in self.cache:
            out = None
            for s, n in self.frames.get(p, []):
                out = self.cl.idx(s, n)
                if out is not None:
                    out = (out, "%s:%d" % (s.upper(), n))
                    break
            self.cache[p] = out
        return self.cache[p]

    def hashes(self, p):
        ix = self.idx(p)[0]
        return (hashlib.sha1(ix.tobytes()).hexdigest()[:16],
                hashlib.sha1(np.ascontiguousarray(ix[:, ::-1]).tobytes()).hexdigest()[:16])


def field_members(p, nb):
    """[(dz, dy, dx, q, экранный x, экранный y, картинка)] соседей в игровом порядке; сам кадр - последним."""
    v = nb.get(p)
    out = []
    if v:
        part = max(v["parts"], key=lambda k: v["parts"][k])
        for key, c in v["nb"].items():
            pt, dx, dy, dz, q = (int(t) for t in key.split(","))
            if pt != int(part):
                continue
            tot = sum(c.values())
            top = max(c, key=c.get)
            if tot / v["n"] < PRESENT or c[top] / tot < TOP_SHARE:
                continue
            out.append((dz, dy, dx, q, (dx - dy) * 16, (dx + dy) * 8 - dz * 24, top))
    me = (0, 0, 0, int(part) if v else 1)
    # только те, кого игра рисует РАНЬШЕ (z, y, x, часть): они фон кадра. Кто рисуется позже, закроет кадр
    # своей гладкой альфой, и стык с ним считает его собственный рендер, где этот кадр - фон. В поле поверх
    # кадра они не кладутся: ступени классики (лесенка верхнего этажа на карнизе) дали бы пунктир.
    out = sorted(m for m in out if m[:4] < me)
    out.append(me + (0, 0, p))
    return out


def compose(members, pics):
    """Поле k=1: RGB, маска, положение кадра (x0, y0) на холсте. Порядок members - порядок рисования."""
    xs = [m[4] for m in members]
    ys = [m[5] for m in members]
    x0, y0 = PAD - min(xs), PAD - min(ys)
    w, h = max(xs) - min(xs) + 32 + 2 * PAD, max(ys) - min(ys) + 40 + 2 * PAD
    rgb = np.zeros((h, w, 3), np.float32)
    mask = np.zeros((h, w), bool)
    for *_k, sx, sy, q in members:
        got = pics.idx(q)
        if got is None:
            continue
        ix = got[0]
        a = pics.cl.rgba(ix)
        m = ix > 0
        X, Y = x0 + sx, y0 + sy
        rgb[Y:Y + 40, X:X + 32][m] = a[..., :3][m]
        mask[Y:Y + 40, X:X + 32] |= m
    return rgb, mask, (x0, y0)


def compose_at(members, pics, x0, y0, shape):
    """То же поле на готовом холсте (размер и положение кадра - от полного поля)."""
    rgb = np.zeros(shape + (3,), np.float32)
    mask = np.zeros(shape, bool)
    for *_k, sx, sy, q in members:
        got = pics.idx(q)
        if got is None:
            continue
        m = got[0] > 0
        X, Y = x0 + sx, y0 + sy
        rgb[Y:Y + 40, X:X + 32][m] = pics.cl.rgba(got[0])[..., :3][m]
        mask[Y:Y + 40, X:X + 32] |= m
    return rgb, mask, (x0, y0)


def under_hd(members, pics, prev, shape, x0, y0, fallback):
    """Что игра покажет под кадром: готовые HD-рендеры соседей (прошлый проход) в порядке рисования поверх
    запасного поля. Сосед без рендера - запасное поле (xBRZ поля «соседи сверху»)."""
    rgb = fallback.copy()
    for *_k, sx, sy, q in members[:-1]:
        img = prev(q) if prev else None
        if img is None:
            continue
        X, Y = (x0 + sx) * K, (y0 + sy) * K
        a = img[..., 3:4] / 255.0
        dst = rgb[Y:Y + 160, X:X + 128]
        dst[:] = img[..., :3] * a + dst * (1 - a)
    return rgb[y0 * K:(y0 + 40) * K, x0 * K:(x0 + 32) * K]


def render(p, nb, pics, up, prev=None):
    members = field_members(p, nb)
    # два поля, как два слоя игры: «кадр сверху» - для самого кадра, «соседи сверху» (кадр - только там, где
    # соседей нет) - для полосы мягкой альфы за силуэтом кадра. Там в игре виден сосед, нарисованный раньше,
    # а не сосед, обрезанный лесенкой самого кадра в классике (иначе тонкий карниз нижнего этажа - пунктиром)
    rgb, mask, (x0, y0) = compose(members, pics)
    under, _m, _o = compose([members[-1]] + members[:-1], pics)
    own_f = np.zeros(mask.shape, np.float32)
    own = pics.idx(p)[0] > 0
    own_f[y0:y0 + 40, x0:x0 + 32] = own * 255.0
    src = ss.fill_outside(rgb[None], mask[None])[0]
    src_u = ss.fill_outside(under[None], mask[None])[0]
    # цвет самого кадра - xBRZ только его пикселей (вне силуэта - продолжение своих же): xBRZ поля подмешивал
    # в пиксели у края кадра цвет соседа (светлый карниз нижнего этажа - зубцами над карнизом). Форму края
    # задаёт w, а что под краем - below
    top_mode = os.environ.get("WALL_EXACT_TOP", "floor")
    if top_mode == "floor":
        # соседи своего этажа (стена продолжается по линии) - контекст xBRZ нужен, чтобы рисунок шёл через
        # стык; этаж ниже - другой предмет (верх стены, карниз), его цвет в свой кадр не тянуть
        same = [m for m in members if m[0] == 0]
        rgb_s, mask_s, _o = compose_at(same, pics, x0, y0, mask.shape)
        src_o = ss.fill_outside(rgb_s[None], mask_s[None])[0]
    else:
        src_o = ss.fill_outside(rgb[None], (own_f > 0)[None])[0]
    one = np.full(src.shape[:2] + (1,), 255.0, np.float32)
    batch = np.stack([np.concatenate([src, one], -1), np.concatenate([src_u, one], -1),
                      np.concatenate([np.repeat(own_f[..., None], 3, -1), one], -1),
                      np.concatenate([src_o, one], -1)])
    big = ss.xbrz_scale(batch, K)
    box = (slice(y0 * K, (y0 + 40) * K), slice(x0 * K, (x0 + 32) * K))
    w = np.clip(big[2][box][..., :1] / 255.0, 0, 1)
    thru = bool(ws.openings(own).any())
    alpha = wr.alpha_of(own, thru)
    # под кромкой - только соседи своего этажа (стык по линии, R-337). Этаж ниже под нижней кромкой в игре
    # почти всегда закрыт полом этой клетки: светлый карниз нижнего этажа, подмешанный сюда, на полу - светлые
    # крючки у основания стены (R-352). Вне соседей - продолжение своего кадра (src_o)
    if os.environ.get("WALL_EXACT_UNDER", "floor") == "floor" and top_mode == "floor":
        same_u = [m for m in members[:-1] if m[0] == 0] + [members[-1]]
        below = under_hd(same_u, pics, prev, big[3].shape, x0, y0, big[3][..., :3])
    else:
        below = under_hd(members, pics, prev, big[1].shape, x0, y0, big[1][..., :3])
    top = big[0] if top_mode == "field" else big[3]
    base = top[box][..., :3] * w + below * (1 - w)
    res = {"xbrz": base}
    if up is not None:
        model = up.run(np.clip(src + 0.5, 0, 255).astype(np.uint8)[None])[0].astype(np.float32)
        res["b2"] = wr.detail(base, model[box], wr.DETAIL[0], wr.DETAIL[1], alpha)
    imgs = {m: wf.to_img(v, alpha) for m, v in res.items()}
    return imgs, members, thru


def desc(members, pics, mirror=False):
    """Поле как набор (экранный x, y, картинка по пикселям) - для поиска зеркального двойника."""
    out = set()
    for *_k, sx, sy, q in members:
        if pics.idx(q) is None:
            continue
        h, hm = pics.hashes(q)
        out.add((-sx, sy, hm) if mirror else (sx, sy, h))
    return frozenset(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="census/walls/exact/render")
    ap.add_argument("--no-model", action="store_true", help="только A, модель не грузится")
    ap.add_argument("--limit", type=int, default=0, help="только первые N картинок по весу мест")
    ap.add_argument("--only", default="", help="картинки через запятую")
    ap.add_argument("--force", action="store_true", help="пересчитать готовые")
    ap.add_argument("--batch", type=int, default=0, help="пачка N (с 1) по весу мест: рисуются только её картинки, "
                    "все раньше - готовые с диска (соседи и зеркальные двойники)")
    ap.add_argument("--size", type=int, default=100, help="картинок в пачке")
    a = ap.parse_args()
    os.chdir(ROOT)
    sys.stdout.reconfigure(encoding="utf-8")
    methods = ("xbrz",) if a.no_model else ("xbrz", "b2")
    for m in methods:
        os.makedirs(os.path.join(a.out, m), exist_ok=True)
    nb = json.load(open(NEIGHBORS, encoding=ENC))
    up = None
    if not a.no_model:
        import upscale_units as uu
        up = uu.Upscaler(wr.MODELS["esrgan"])
    cl = wf.Classic(mm.World())
    rs = rows()
    pics = Pics(cl, rs)
    if a.only:
        want = set(a.only.split(","))
        rs = [r for r in rs if r["картинка"] in want]
    if a.limit:
        rs = rs[:a.limit]
    lo = 0
    if a.batch:
        lo = (a.batch - 1) * a.size
        rs = rs[:a.batch * a.size]
    t0 = time.time()
    todo = [r for r in rs[lo:] if pics.idx(r["картинка"]) is not None and
            (a.force or not all(os.path.exists(os.path.join(a.out, m, r["картинка"] + ".png")) for m in methods))]
    # проход 1: каждая картинка, под кромкой - поле «соседи сверху». Проход 2: под кромкой - готовые рендеры
    # соседей из прохода 1 (или с диска, из прошлых пачек): так кромка кадра ложится ровно на то, что игра
    # нарисует под ним, а не на классику соседа, увеличенную ещё раз
    mem = {}

    def load(q):
        if q in mem:
            return mem[q]
        f = os.path.join(a.out, "xbrz", q + ".png")
        if os.path.exists(f):
            mem[q] = np.asarray(Image.open(f).convert("RGBA"), np.float32)
            return mem[q]
        return None

    first, canon1 = {}, {}
    want_p = {r["картинка"] for r in todo}
    for r in rs:                      # двойники из прошлых пачек - готовые с диска
        p = r["картинка"]
        if p not in want_p and pics.idx(p) is not None and load(p) is not None:
            canon1.setdefault(desc(field_members(p, nb), pics), p)
    for r in todo:
        p = r["картинка"]
        members = field_members(p, nb)
        twin = canon1.get(desc(members, pics, mirror=True))
        if twin and twin != p:
            first[p] = (first[twin] if twin in first else load(twin))[:, ::-1].copy()
        else:
            imgs, _m, _t = render(p, nb, pics, None)
            first[p] = np.asarray(imgs["xbrz"], np.float32)
        canon1.setdefault(desc(members, pics), p)
    print("проход 1: %d картинок за %.0f с" % (len(first), time.time() - t0), flush=True)
    mem.update(first)

    canon = {}               # описание поля -> картинка, уже нарисованная
    report, stat = [], dict(field=0, mirror=0, ready=0, none=0)
    for i, r in enumerate(rs):
        p = r["картинка"]
        if i < lo:                    # прошлые пачки: только как двойники для зеркал
            if p not in want_p and pics.idx(p) is not None and load(p) is not None:
                canon.setdefault(desc(field_members(p, nb), pics), p)
            continue
        if pics.idx(p) is None:
            report.append([p, "", "нет кадра", "0", "0", ""])
            stat["none"] += 1
            continue
        members = field_members(p, nb)
        d, dm = desc(members, pics), desc(members, pics, mirror=True)
        paths = {m: os.path.join(a.out, m, p + ".png") for m in methods}
        twin = canon.get(dm)
        thru = bool(ws.openings(pics.idx(p)[0] > 0).any())
        if p not in want_p:
            how = "готово"
            stat["ready"] += 1
        elif twin and twin != p:
            for m in methods:
                Image.open(os.path.join(a.out, m, twin + ".png")).transpose(Image.FLIP_LEFT_RIGHT).save(paths[m])
            how = "зеркало " + twin
            stat["mirror"] += 1
        else:
            imgs, members, thru = render(p, nb, pics, up, prev=lambda q: mem.get(q) if q in want_p else load(q))
            for m in methods:
                imgs[m].save(paths[m])
            how = "поле"
            stat["field"] += 1
        canon.setdefault(d, p)
        report.append([p, pics.idx(p)[1], how, "1" if thru else "0", str(len(members) - 1),
                       " ".join("%+d%+d:%s" % (m[4], m[5], pics.idx(m[6])[1] if pics.idx(m[6]) else m[6])
                                for m in members[:-1])])
        if (i + 1) % 100 == 0:
            print("картинок %d из %d, %.0f с" % (i + 1, len(rs), time.time() - t0), flush=True)
    name = "render_b%03d.tsv" % a.batch if a.batch else "render.tsv"
    with open(os.path.join(a.out, name), "w", encoding=ENC, newline="") as f:
        f.write("\t".join(["картинка", "представитель", "как", "сквозная", "соседей", "поле"]) + "\n")
        for row in report:
            f.write("\t".join(row) + "\n")
    print("готово: полем %(field)d, зеркалом %(mirror)d, готовых раньше %(ready)d, без кадра %(none)d" % stat,
          "за %.0f с" % (time.time() - t0), flush=True)


if __name__ == "__main__":
    main()
