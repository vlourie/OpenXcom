"""Автопроверка собранного семейства деревьев (конвейер TREE_RENDER_V2, партии по 20 семейств).

Проверяется только то, что ломает картинку на карте, а не художественность:
  размер    - кадр 128x160 RGBA;
  дырки     - сквозные дырки внутри силуэта кадра (замкнутые, до PIN_MAX пикс x4), которые в какой-либо раскладке
              показывают чужое (другой кадр или фон) с перепадом больше TOL;
  лесенка   - шов двух кадров по сетке базы (доля рёбер на сетке >= GRID_STEP) с перепадом больше STEP_R средних
              перепадов внутри кадров - в ЛЮБОЙ раскладке, и в T1 тоже (сканер ta.scan брал T1 за опору и его не видел);
  срез      - прямой жёсткий край альфы (вертикаль или горизонталь подряд >= CUT_RUN x4) внутри кадра, за которым
              в раскладке фон или чужое, а у классики рисунок. Брак - только край ПО СЕТКЕ базы (линия, начало и
              конец на границах клеток 4x4: след блочной маски); прочие прямые края (бок ствола, низ ветки) - рисунок,
              они идут предупреждением warn_vertical;
  рамка     - срез рамкой кадра (ta.scan frame_cuts), сверка с классикой той же раскладки: брак - только новые.
Вход - кадры <семейство>/asm/frames/<НАБОР>.PCK. Итог - <семейство>/asm/qc.json и строка PASS / FAIL со списком.

  py tools/hdart/tree_qc.py --root census/trees/groups/batchA TG035 TG009 ...
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tree_render as tr  # noqa: E402
import tree_family as tf  # noqa: E402
import tree_family_asm as ta  # noqa: E402

ENC = "utf-8-sig"
PIN_MAX = 64        # x4: дырка не больше 2x2 пикселя базы - это дырка в маске, а не просвет кроны
TOL = 30            # перепад цвета (макс. канала), который виден
GRID_STEP = 0.9     # шов почти целиком по сетке базы
STEP_R = 3.0        # перепад на шве против среднего перепада внутри кадров
MIN_SEAM = 24       # x4: короче - не шов
CUT_RUN = 12        # x4: прямой жёсткий край альфы подряд


def pinholes(a):
    """Замкнутые прозрачные пятна внутри силуэта - след маски по сетке базы: прямоугольник по сетке 4x4, не больше
    PIN_MAX. Щели между листьями (неправильной формы) - рисунок, не дырка. Маска (160, 128)."""
    tp = (a < 128).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(tp, connectivity=4)
    m = np.zeros(a.shape, bool)
    H, W = a.shape
    for k in range(1, n):
        x, y, w, h, ar = st[k]
        if ar <= PIN_MAX and x > 0 and y > 0 and x + w < W and y + h < H and ar == w * h \
                and x % 4 == 0 and y % 4 == 0 and w % 4 == 0 and h % 4 == 0:
            m |= lab == k
    return m


def notches(a, rgb, bare=False):
    """Выемки по сетке: клетка 4x4 целиком прозрачна, а соседние клетки хотя бы с трёх сторон из четырёх почти
    сплошь непрозрачны (12 из 16) - след блочной маски, открытый с одной стороны (pinholes видит только замкнутые).
    След маски, а не просвет рисунка: под прозрачной клеткой лежит RGB вида (кадр = вид x маска), у 12 из 16
    пикселей он не чёрный; естественный просвет между голыми ветками (TG036 65) вид не рисовал. Клетки у рамки
    кадра не берутся. bare=False - выемки, под которыми рисунок (RGB не ровный), их сборка закрывает;
    bare=True - под клеткой ровная заливка (TG037 63: вид там сам пуст, ступенчатый низ кроны) - закрывать нечем.
    a - альфа, rgb - (160, 128, 3). Маска (160, 128)."""
    H, W = a.shape
    b = (a >= 128).reshape(H // 4, 4, W // 4, 4).sum((1, 3))
    tr_ = (a < 128).reshape(H // 4, 4, W // 4, 4).sum((1, 3)) == 16
    rgb = np.asarray(rgb, np.float32)
    tr_ &= (rgb.max(-1) > 8).reshape(H // 4, 4, W // 4, 4).sum((1, 3)) >= 12
    flat = rgb.reshape(H // 4, 4, W // 4, 4, 3).std((1, 3)).mean(-1) < 1.0
    tr_ &= flat if bare else ~flat
    full = b >= 12
    p = np.pad(full, 1)
    sides = p[:-2, 1:-1].astype(int) + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:]
    cell = tr_ & (sides >= 3)
    cell[0, :] = cell[-1, :] = False
    cell[:, 0] = cell[:, -1] = False
    return np.repeat(np.repeat(cell, 4, 0), 4, 1)


def hard_edges(a):
    """Прямые жёсткие края альфы внутри кадра: список (сторона, x или y, начало, длина) и маска наружных пикселей."""
    out, mask, mask_v = [], np.zeros(a.shape, bool), np.zeros(a.shape, bool)
    on = a >= 200
    off = a <= 30
    H, W = a.shape
    # вертикальный край: on в (y, x), off в (y, x+d) или (y, x-d), d = 1..2; x не у рамки
    for side, sh in (("R", 1), ("L", -1)):
        e = np.zeros(a.shape, bool)
        for d in (1, 2):
            o = np.zeros(a.shape, bool)
            if sh > 0:
                o[:, :-d] = off[:, d:]
            else:
                o[:, d:] = off[:, :-d]
            e |= on & o
        e[:, :3] = False
        e[:, -3:] = False
        for x in range(W):
            col = e[:, x]
            y = 0
            while y < H:
                if col[y]:
                    y0 = y
                    while y < H and col[y]:
                        y += 1
                    if y - y0 >= CUT_RUN:
                        xo = min(W - 1, x + 2) if sh > 0 else max(0, x - 2)
                        bx = x + 1 if sh > 0 else x
                        if bx % 4 == 0 and y0 % 4 == 0 and y % 4 == 0:
                            out.append((side, x, y0, y - y0))
                            mask[y0:y, xo] = True
                        else:
                            mask_v[y0:y, xo] = True
                else:
                    y += 1
    for side, sh in (("B", 1), ("T", -1)):
        e = np.zeros(a.shape, bool)
        for d in (1, 2):
            o = np.zeros(a.shape, bool)
            if sh > 0:
                o[:-d] = off[d:]
            else:
                o[d:] = off[:-d]
            e |= on & o
        e[:3] = False
        e[-3:] = False
        for y in range(H):
            row = e[y]
            x = 0
            while x < W:
                if row[x]:
                    x0 = x
                    while x < W and row[x]:
                        x += 1
                    if x - x0 >= CUT_RUN:
                        yo = min(H - 1, y + 2) if sh > 0 else max(0, y - 2)
                        by = y + 1 if sh > 0 else y
                        if by % 4 == 0 and x0 % 4 == 0 and x % 4 == 0:
                            out.append((side, y, x0, x - x0))
                            mask[yo, x0:x] = True
                        else:
                            mask_v[yo, x0:x] = True
                else:
                    x += 1
    return out, mask, mask_v


def floor_allow(root, fid, frames):
    """Пиксели кадра, равные подставленному HD-полу (ta.floor_base): вершины ромба пола касаются рамки кадра по
    построению, срезом рамкой они не считаются (TG018). Ствол и ветки у рамки проверяются как прежде."""
    p = os.path.join(root, fid, "asm", "summary.json")
    fb = json.load(open(p, encoding=ENC)).get("floor_base", {}) if os.path.exists(p) else {}
    out = {}
    for f, v in fb.items():
        f = int(f)
        if f not in frames or "floor" not in v:
            continue
        s2, f2 = v["floor"].split(":")
        fp = os.path.join(tr.OLD, s2 + ".PCK", "%s.png" % f2)
        if not os.path.exists(fp):
            continue
        fl = np.asarray(Image.open(fp).convert("RGBA")).astype(np.int16)
        a = np.asarray(frames[f]).astype(np.int16)
        out[f] = (fl[..., 3] > 0) & (a[..., 3] > 0) & (np.abs(a[..., :3] - fl[..., :3]).max(-1) <= 3)
    return out


def check(world, CL, S, frames, classic, allow=None):
    res = dict(size=[], pinholes={}, notches={}, grid_seams=[], hard_cuts={}, frame_cuts_new=[])
    for f, im in frames.items():
        if im.size != (128, 160) or im.mode != "RGBA":
            res["size"].append([f, list(im.size), im.mode])
    A = {f: np.asarray(frames[f], np.uint8) for f in frames}
    pin = {f: pinholes(A[f][..., 3]) for f in frames}
    hard = {f: hard_edges(A[f][..., 3]) for f in frames}
    notch = {kind: {f: notches(A[f][..., 3], A[f][..., :3], kind == "notches_bare") for f in frames}
             for kind in ("notches", "notches_bare")}
    res["notches_bare"] = {}
    vis_pin, vis_cut, vis_vcut = {}, {}, {}
    vis_notch = {"notches": {}, "notches_bare": {}}
    for name, i in tr.LAYOUTS[S]:
        sig = CL[S]["sigs"][i]["sig"]
        for zmax in (0, 1, 2, 99):
            sg = [e for e in sig if e[4] <= zmax]
            if not sg:
                continue
            lay = "%s|z%d" % (name, zmax)
            rgb, own, alpha, names, boxes = ta._build(world, S, sg, frames)
            c_alpha = ta._build(world, S, sg, classic)[2]
            for pair, (n, g, r) in ta._inner(rgb, own, names, MIN_SEAM).items():
                if g >= GRID_STEP and r > STEP_R:
                    res["grid_seams"].append([lay, pair, n, round(g, 2), round(r, 2)])
            for k, nm in enumerate(names):
                f = int(nm.split("@")[0])
                ox, oy, w, h = boxes[k]
                fr = A[f][..., :3].astype(np.int16)
                vis = rgb[oy:oy + h, ox:ox + w].astype(np.int16)
                ow = own[oy:oy + h, ox:ox + w]
                al = alpha[oy:oy + h, ox:ox + w]
                diff = np.abs(vis - fr).max(-1) > TOL
                # видно сквозь кадр только то, что нарисовано РАНЬШЕ него (или фон); кадр, нарисованный позже, его
                # закрывает, и за краем тогда не дыра, а сосед (порядок _build - порядок рисования)
                under = (al < 32) | ((ow >= 0) & (ow < k) & diff)
                m = pin[f] & under
                if m.any():
                    vis_pin.setdefault(f, set()).add(lay)
                    vis_pin[(f, "px")] = [max(vis_pin.get((f, "px"), [0])[0], int(m.sum()))]
                for kind, vn in vis_notch.items():
                    if notch[kind][f].any():
                        # выемка по сетке: сквозь неё видно раньше нарисованное или фон там, где классика рисует
                        m = notch[kind][f] & under & (c_alpha[oy:oy + h, ox:ox + w] >= 128)
                        if m.sum() >= 16:
                            vn.setdefault(f, set()).add(lay)
                            vn[(f, "px")] = [max(vn.get((f, "px"), [0])[0], int(m.sum()))]
                e, em, ev = hard[f]
                if e or ev.any():
                    # разрыв: за прямым жёстким краем у HD пусто или чужое, а у классики там рисунок. Брак - только
                    # горизонтальный (срез поперёк ствола и кроны); вертикальный жёсткий край - бок ствола, это
                    # рисунок, его только показываем (warn)
                    ca = c_alpha[oy:oy + h, ox:ox + w]
                    seen = (ca >= 128) & under
                    for store, mm in ((vis_cut, em), (vis_vcut, ev)):
                        m2 = mm & seen
                        if m2.sum() >= CUT_RUN:
                            store.setdefault(f, set()).add(lay)
                            store[(f, "px")] = [max(store.get((f, "px"), [0])[0], int(m2.sum()))]
    for f in frames:
        if f in vis_pin:
            res["pinholes"][str(f)] = dict(px=vis_pin[(f, "px")][0], views=len(vis_pin[f]))
        for kind, vn in vis_notch.items():
            if f in vn:
                res[kind][str(f)] = dict(px=vn[(f, "px")][0], views=len(vn[f]))
        if f in vis_cut:
            res["hard_cuts"][str(f)] = dict(px=vis_cut[(f, "px")][0], views=len(vis_cut[f]),
                                            edges=[list(map(int, x[1:])) + [x[0]] for x in hard[f][0]][:8])
        if f in vis_vcut:
            res.setdefault("warn_vertical", {})[str(f)] = dict(px=vis_vcut[(f, "px")][0], views=len(vis_vcut[f]))
    new = ta.scan(world, CL, S, frames, allow)["frame_cuts"]
    old = {(c[0], c[1]) for c in ta.scan(world, CL, S, classic)["frame_cuts"]}
    res["frame_cuts_new"] = [c for c in new if (c[0], c[1]) not in old]
    bad = []
    if res["size"]:
        bad.append("размер %d" % len(res["size"]))
    if res["pinholes"]:
        bad.append("дырки " + ",".join(sorted(res["pinholes"], key=int)))
    if res["notches"]:
        bad.append("выемки " + ",".join(sorted(res["notches"], key=int)))
    if res["notches_bare"]:
        bad.append("ступени без рисунка вида " + ",".join(sorted(res["notches_bare"], key=int)))
    if res["grid_seams"]:
        pr = sorted({p[1] for p in res["grid_seams"]})
        bad.append("лесенка %d швов (%s)" % (len(res["grid_seams"]), "; ".join(pr[:4])))
    if res["hard_cuts"]:
        bad.append("срез " + ",".join(sorted(res["hard_cuts"], key=int)))
    if res["frame_cuts_new"]:
        bad.append("рамка %d" % len(res["frame_cuts_new"]))
    res["verdict"] = "FAIL" if bad else "PASS"
    res["defects"] = bad
    return res


def run_family(root, fid, world):
    D, CLs, sets = tf.load([fid])
    S, CL = sets[fid], CLs[fid]
    if fid not in tf.COPY_OF:
        tf.patch(fid, S, CL)
    ta.set_layouts(S, CL)
    fs = sorted({e[0] for L in CL[S]["sigs"] for e in L["sig"]})
    fd = os.path.join(root, fid, "asm", "frames", S + ".PCK")
    frames = {f: Image.open(os.path.join(fd, "%d.png" % f)).convert("RGBA") for f in fs
              if os.path.exists(os.path.join(fd, "%d.png" % f))}
    miss = [f for f in fs if f not in frames]
    if miss:
        res = dict(verdict="FAIL", defects=["нет кадров %s" % miss])
    else:
        cl = {f: tr.sprite(world, S, f).convert("RGBA").resize((128, 160), Image.NEAREST) for f in fs}
        res = check(world, CL, S, frames, cl, floor_allow(root, fid, frames))
    res.update(family=fid, set=S)
    with open(os.path.join(root, fid, "asm", "qc.json"), "w", encoding=ENC) as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1)
    print("%s %s: %s %s" % (fid, S, res["verdict"], "; ".join(res["defects"])), flush=True)
    return res


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="census/trees/groups/batchA")
    ap.add_argument("fids", nargs="+")
    a = ap.parse_args()
    world = tr.mm.World()
    for fid in a.fids:
        run_family(a.root, fid, world)


if __name__ == "__main__":
    main()
