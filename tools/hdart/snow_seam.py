"""Согласование снега у рамок взаимозаменяемых кадров составного дерева (FOREST_SNOW, после edge_rule).

Снег - светлая почти бесцветная накладка на хвое. Кадры одного номера стоят в раскладках T1/T1b/T2/T3/clump
рядом с разными соседями; где сосед у рамки без снега, а кадр со снегом до самой рамки, виден прямой срез снега.
Контракт шва: снег либо продолжается у соседа, либо плавно кончается до рамки. Материал - только готовые кадры
(то же MAIN): GPU и модель не нужны. Альфа, форма веток, положения кадров не меняются; один номер кадра -
одна картинка во всех раскладках.

Операции (SNOW_SEAM_OPS, по очереди, каждая к итогу предыдущей):
  quilt  A side B          - полоса A у рамки заменяется продолжением B с того же места холста; граница замены -
                             путь наименьшей разницы (quilting), снег путь не режет; пиксели A, видимые в
                             раскладках без этой пары, не трогаются
  twin   A B (ключ)        - в A у обрыва ключа снег берётся у двойника B (тот же номер места, кадры меняются
                             местами в раскладках): связный снег B у точек обрыва
  recede A side B@L x0 x1 D - снег A у рамки плавно кончается дугой глубиной до D в столбцах x0..x1, под ним -
                             хвоя соседа B (ключ раскладки L) того же места холста
Проверка - обрывы: подряд точки рамки (пропуск до GAP) с расхождением снега > CUT длиной >= RUN; новым считается
обрыв пары, которой нет в T1 (T1 принят как есть)."""
import numpy as np
import cv2
from PIL import Image

v2 = None                        # модуль tree_render_v2 (_layouts, _compose) - передаёт apply(), без повторного импорта

CUT, GAP, RUN = 0.6, 2, 10
E, D = 4, 4                      # поиск своего пикселя у рамки и глубина точек связи, пикс x4
Q_W, Q_MINW, Q_STEP, Q_SNOWPEN, Q_MISPEN = 40, 6, 2, 4.0, 300.0
INF = 1e9
SIDE_D = {"T": (-1, 0), "B": (1, 0), "L": (0, -1), "R": (0, 1)}
TO = {"R": lambda x: x, "L": lambda x: x[:, ::-1], "T": lambda x: np.rot90(x, -1), "B": lambda x: np.rot90(x, 1)}
FROM = {"R": lambda x: x, "L": lambda x: x[:, ::-1], "T": lambda x: np.rot90(x, 1), "B": lambda x: np.rot90(x, -1)}

SNOW_SEAM_OPS = {
    "FOREST_SNOW": [
        ("quilt", 46, "R", 56),                         # T2: прямой срез снега 46|56
        ("twin", 52, 53, (54, "T", 52)),                # T1b/T2/T3 z<=2: снег 54 у верхней рамки продолжается в 52
        ("recede", 48, "T", "49@T2", 41, 62, 6),        # T2 и clump: снег 48 у верхней рамки
        ("recede", 50, "T", "49@T2", 70, 85, 6),        # T2: снег 50 у верхней рамки
    ],
}


def snow_mask(rgb255):
    lab = cv2.cvtColor(np.clip(rgb255, 0, 255).astype(np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32)
    L = lab[..., 0] * 100 / 255
    C = np.hypot(lab[..., 1] - 128, lab[..., 2] - 128)
    return (L > 55) & (C < 20)


def constraints(world, CL, S, fr):
    """Связи у рамок по всем раскладкам: (раскладка, ключ (f, side, fj, dx, dy, dz), f, точки f у рамки, fj,
    точки fj за рамкой, (раскладка, zmax, строка, side, t)). fr: {f: float 0..1 160x128x4}."""
    out = []
    for name, zmax, rows in v2._layouts(world, CL, S):
        _rgb, _al, own, (x0, y0) = v2._compose(rows, lambda i, f: fr[f])
        H, W = own.shape
        for i, ((z, y, x, _p), f, sx, sy) in enumerate(rows):
            ox, oy = sx - x0, sy - y0
            for side in ("T", "B", "L", "R"):
                dy, dx = SIDE_D[side]
                for t in range(128 if side in "TB" else 160):
                    for k in range(E):
                        if side == "T": yy, xx = oy + k, ox + t
                        elif side == "B": yy, xx = oy + 159 - k, ox + t
                        elif side == "L": yy, xx = oy + t, ox + k
                        else: yy, xx = oy + t, ox + 127 - k
                        if 0 <= yy < H and 0 <= xx < W and own[yy, xx] == i:
                            break
                    else:
                        continue
                    yo, xo = yy + dy, xx + dx
                    if not (0 <= yo < H and 0 <= xo < W):
                        continue
                    j = own[yo, xo]
                    if j < 0 or j == i:
                        continue
                    (zj, yj, xj, _pj), fj, sxj, syj = rows[j]
                    pa = [(yy - dy * q - oy, xx - dx * q - ox) for q in range(D)
                          if 0 <= yy - dy * q < H and 0 <= xx - dx * q < W and own[yy - dy * q, xx - dx * q] == i]
                    pb = [(yo + dy * q - (syj - y0), xo + dx * q - (sxj - x0)) for q in range(D)
                          if 0 <= yo + dy * q < H and 0 <= xo + dx * q < W and own[yo + dy * q, xo + dx * q] == j]
                    if pa and pb:
                        out.append((name, (f, side, fj, xj - x, yj - y, zj - z), f, pa, fj, pb, (name, zmax, i, side, t)))
    return out


def visibility(world, CL, S, fr):
    """{(раскладка, zmax): {кадр: маска 160x128 видимых пикселей}}"""
    out = {}
    for name, zmax, rows in v2._layouts(world, CL, S):
        _rgb, _al, own, (x0, y0) = v2._compose(rows, lambda i, f: fr[f])
        d = out.setdefault((name, zmax), {})
        H, W = own.shape
        for i, (_k, f, sx, sy) in enumerate(rows):
            ox, oy = sx - x0, sy - y0
            m = d.setdefault(f, np.zeros((160, 128), bool))
            ya, yb, xa, xb = max(oy, 0), min(oy + 160, H), max(ox, 0), min(ox + 128, W)
            m[ya - oy:yb - oy, xa - ox:xb - ox] |= own[ya:yb, xa:xb] == i
    return out


def _snow_at(sg, pts):
    return float(np.mean([sg[v, u] for v, u in pts]))


def _sig(fr):
    return {f: (snow_mask(a[..., :3] * 255) & (a[..., 3] >= 0.5)).astype(np.float32) for f, a in fr.items()}


def _bad(c, sig):
    return abs(_snow_at(sig[c[2]], c[3]) - _snow_at(sig[c[4]], c[5])) > CUT


def runs(cons, sig, run=RUN):
    """[(ключ, раскладка, zmax, длина, индексы связей)]"""
    by = {}
    for k, c in enumerate(cons):
        by.setdefault(c[6][:4], []).append(k)
    res = []
    for g, ks in by.items():
        ks.sort(key=lambda k: cons[k][6][4])
        cur, last = [], None

        def close():
            if cur and len(cur) >= run:
                res.append((cons[cur[0]][1], g[0], g[1], cons[cur[-1]][6][4] - cons[cur[0]][6][4] + 1, list(cur)))

        for k in ks:
            c = cons[k]
            t = c[6][4]
            bad = _bad(c, sig)
            if cur and (t - last > GAP + 1 or (bad and c[1] != cons[cur[-1]][1])):
                close()
                cur, last = [], None
            if bad:
                cur.append(k)
                last = t
        close()
    return res


def _shift(cons, key):
    dy, dx = SIDE_D[key[1]]
    dl = {(c[5][0][0] - c[3][0][0] - dy, c[5][0][1] - c[3][0][1] - dx) for c in cons if c[1] == key}
    assert len(dl) == 1, (key, dl)
    return dl.pop()


def _warp(a, dv, du):
    return cv2.warpAffine(a, np.float32([[1, 0, -du], [0, 1, -dv]]), (128, 160), flags=cv2.INTER_NEAREST,
                          borderValue=0)


def _quilt_key(world, CL, S, cur, alpha0, key):
    A, SIDE, B = key[:3]
    fr = {f: a.astype(np.float32) / 255.0 for f, a in cur.items()}
    cons = constraints(world, CL, S, fr)
    ddv, ddu = _shift(cons, key)
    lays = {(c[6][0], c[6][1]) for c in cons if c[1] == key}
    forb = np.zeros((160, 128), bool)
    for l, d in visibility(world, CL, S, fr).items():
        if l not in lays and A in d:
            forb |= d[A]
    Bs = _warp(fr[B], ddv, ddu)
    fA = fr[A]
    opA, opB = fA[..., 3] >= 0.5, Bs[..., 3] >= 0.5
    snA = snow_mask(fA[..., :3] * 255) & opA
    snB = snow_mask(Bs[..., :3] * 255) & opB
    t = TO[SIDE]
    a3, b3 = t(fA[..., :3]), t(Bs[..., :3])
    oA, oB, sA, sB, fb = t(opA), t(opB), t(snA), t(snB), t(forb)
    H, Wd = oA.shape
    d = np.sqrt(((a3 - b3) ** 2).sum(-1)) + Q_SNOWPEN * (sA | sB)
    cost = np.zeros((H, Wd + 1), np.float32)
    for v in range(H):
        for cc in range(Wd - Q_W, Wd + 1):
            need = oA[v, cc:]
            if need.any() and ((~oB[v, cc:] & need).any() or (fb[v, cc:] & need).any()):
                cost[v, cc] = INF
                continue
            if cc == Wd:
                cost[v, cc] = d[v, Wd - 1] if oA[v, Wd - 1] else 0
            else:
                l, r = max(cc - 1, 0), cc
                cost[v, cc] = (d[v, l] if oA[v, l] else 0) + (d[v, r] if oA[v, r] else 0)
        # связь берёт до D пикселей A у рамки: при расхождении снега у рамки заменять не уже Q_MINW
        if oA[v, Wd - D:].any() and (sA[v, Wd - D:] != sB[v, Wd - D:]).any():
            cost[v, Wd - Q_MINW + 1:] += Q_MISPEN
        cost[v, :Wd - Q_W] = INF
    acc = cost.copy()
    back = np.zeros((H, Wd + 1), np.int32)
    for v in range(1, H):
        for cc in range(Wd + 1):
            lo, hi = max(cc - Q_STEP, 0), min(cc + Q_STEP + 1, Wd + 1)
            j = lo + int(np.argmin(acc[v - 1, lo:hi]))
            back[v, cc] = j
            acc[v, cc] = cost[v, cc] + acc[v - 1, j]
    cut = np.zeros(H, np.int32)
    cut[H - 1] = int(np.argmin(acc[H - 1]))
    for v in range(H - 1, 0, -1):
        cut[v - 1] = back[v, cut[v]]
    m = np.zeros((H, Wd), np.float32)
    for v in range(H):
        m[v, cut[v]:] = 1
    m *= oA
    mf = cv2.GaussianBlur(m, (0, 0), 0.8) * oA
    mf = np.where(m > 0, np.maximum(mf, 0.5), mf)
    mf = np.where(fb, 0, mf)
    res3 = FROM[SIDE](mf[..., None] * b3 + (1 - mf[..., None]) * a3)
    mf = FROM[SIDE](mf)
    img = cur[A].copy()
    img[..., :3] = (np.clip(res3, 0, 1) * 255 + 0.5).astype(np.uint8)
    img[..., 3] = alpha0[A]
    cur[A] = img
    return dict(op="quilt", key=list(map(str, key)), layouts=sorted(map(list, lays)), shift=[ddv, ddu],
                replaced_px=int((mf > 0.01).sum()), snow_before=int(snA.sum()),
                snow_after=int((snow_mask(img[..., :3].astype(np.float32)) & opA).sum()))


def _halo(a):
    """снежность с ободком полутонов: всё светлое и почти бесцветное, 0..1"""
    lab = cv2.cvtColor(np.clip(a[..., :3] * 255, 0, 255).astype(np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32)
    L, C = lab[..., 0] * 100 / 255, np.hypot(lab[..., 1] - 128, lab[..., 2] - 128)
    return np.clip((L - 33) / 15, 0, 1) * np.clip((30 - C) / 10, 0, 1) * (a[..., 3] >= 0.5)


TW_SEED_R, TW_G0, TW_T, TW_NA, TW_FREE = 2, 4.0, 6.0, 4.0, 3


def _twin(world, CL, S, cur, alpha0, A, B, key):
    """Снег A у обрывов ключа key (точки на стороне A) - снег двойника B того же места кадра (B стоит в T1 там же,
    где A в новой раскладке): по снегу B геодезически от точек обрыва, до TW_G0 целиком и спад на TW_T с шумом -
    конец волнистый; там, где A уже граничит с соседями в T1, не трогается."""
    fr = {f: a.astype(np.float32) / 255.0 for f, a in cur.items()}
    cons = constraints(world, CL, S, fr)
    sig = _sig(fr)
    t1 = {c[1] for c in cons if c[0] == "T1"}
    seed = np.zeros((160, 128), np.uint8)
    for k_, _lay, _z, _ln, ks in runs(cons, sig, RUN):
        if k_[:3] == tuple(key) and k_ not in t1:
            for k in ks:
                c = cons[k]
                for v, u in (c[5] if c[4] == A else c[3]):
                    cv2.circle(seed, (int(u), int(v)), TW_SEED_R, 1, -1)
    if not seed.any():
        return dict(op="twin", a=A, b=B, key=list(map(str, key)), replaced_px=0)
    t1used = np.zeros((160, 128), np.uint8)
    for c in cons:
        if c[0] == "T1":
            for f_, pts in ((c[2], c[3]), (c[4], c[5])):
                if f_ == A:
                    for v, u in pts:
                        t1used[v, u] = 1
    t1used = cv2.dilate(t1used, np.ones((TW_FREE, TW_FREE), np.uint8)) > 0
    fA, fB = fr[A], fr[B]
    opA = fA[..., 3] >= 0.5
    snA = snow_mask(fA[..., :3] * 255) & opA
    hB = _halo(fB)
    net = (cv2.dilate(sig[B].astype(np.uint8), np.ones((3, 3), np.uint8)) > 0) & (hB > 0.05)
    s = (seed > 0) & net
    dist = np.full((160, 128), 1e9, np.float32)
    dist[s] = 0
    cw = s.astype(np.uint8)
    for d in range(1, int(TW_G0 + TW_T + TW_NA) + 2):
        nxt = cv2.dilate(cw, np.ones((3, 3), np.uint8)) & net.astype(np.uint8)
        new = (nxt > 0) & (dist > 1e8)
        if not new.any():
            break
        dist[new] = d
        cw = nxt
    rs = np.random.RandomState(1000 + B)
    nz = cv2.GaussianBlur(rs.randn(160, 128).astype(np.float32), (0, 0), 3.0)
    nz /= np.abs(nz).max() + 1e-6
    wa = np.clip(1 - (dist + TW_NA * nz - TW_G0) / TW_T, 0, 1) * (dist < 1e8)
    ra = ((wa > 0.5) & (hB > 0.02)).astype(np.uint8)
    ra = cv2.morphologyEx(ra, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    ra &= (opA & ~t1used).astype(np.uint8)
    mf = np.clip(cv2.GaussianBlur(ra.astype(np.float32), (0, 0), 0.7) * 1.4, 0, 1) * np.clip(hB * 1.5, 0, 1) * opA
    img = cur[A].copy()
    rgb = mf[..., None] * fB[..., :3] + (1 - mf[..., None]) * fA[..., :3]
    img[..., :3] = (np.clip(rgb, 0, 1) * 255 + 0.5).astype(np.uint8)
    img[..., 3] = alpha0[A]
    cur[A] = img
    return dict(op="twin", a=A, b=B, key=list(map(str, key)), replaced_px=int((mf > 0.01).sum()),
                snow_before=int(snA.sum()), snow_after=int((snow_mask(img[..., :3].astype(np.float32)) & opA).sum()))


def _recede(world, CL, S, cur, alpha0, A, SIDE, Bspec, x0, x1, Dmax):
    B, lay = (str(Bspec).split("@") + [None])[:2]
    B = int(B)
    fr = {f: a.astype(np.float32) / 255.0 for f, a in cur.items()}
    cons = [c for c in constraints(world, CL, S, fr) if c[1][:3] == (A, SIDE, B) and (lay is None or c[6][0] == lay)]
    key = cons[0][1]
    ddv, ddu = _shift(cons, key)
    Bs = _warp(fr[B], ddv, ddu)
    fA = fr[A]
    opA, opB = fA[..., 3] >= 0.5, Bs[..., 3] >= 0.5
    snA = snow_mask(fA[..., :3] * 255) & opA
    snB = snow_mask(Bs[..., :3] * 255) & opB
    t = TO[SIDE]
    a3, b3 = t(fA[..., :3]), t(Bs[..., :3])
    sA, sB, oB = t(snA), t(snB), t(opB)
    H, Wd = sA.shape
    idx = np.zeros((160, 128, 2), np.int32)
    idx[..., 0], idx[..., 1] = np.mgrid[0:160, 0:128]
    along = t(idx)[..., 0 if SIDE in "LR" else 1][:, 0]
    m = np.zeros((H, Wd), np.float32)
    for v in range(H):
        x = along[v]
        if not (x0 <= x <= x1):
            continue
        dep = Dmax * np.sin(np.pi * (x - x0 + 0.5) / (x1 - x0 + 1)) ** 0.6     # дуга: 0 на концах
        for c in range(Wd - 1, -1, -1):
            if Wd - 1 - c > dep:
                break
            if sA[v, c] and oB[v, c] and not sB[v, c]:
                m[v, c] = 1
    mf = cv2.GaussianBlur(m, (0, 0), 0.8)
    mf = np.where(m > 0, np.maximum(mf, 0.6), mf) * t(opA)
    res = FROM[SIDE](mf[..., None] * b3 + (1 - mf[..., None]) * a3)
    mf = FROM[SIDE](mf)
    img = cur[A].copy()
    img[..., :3] = (np.clip(res, 0, 1) * 255 + 0.5).astype(np.uint8)
    img[..., 3] = alpha0[A]
    cur[A] = img
    return dict(op="recede", key=list(map(str, key)), shift=[ddv, ddu], cols=[x0, x1], depth=Dmax,
                replaced_px=int((mf > 0.01).sum()), snow_before=int(snA.sum()),
                snow_after=int((snow_mask(img[..., :3].astype(np.float32)) & opA).sum()))


def run_report(world, CL, S, fr, run=RUN):
    cons = constraints(world, CL, S, fr)
    t1 = {c[1] for c in cons if c[0] == "T1"}
    rr = runs(cons, _sig(fr), run)
    new = [r for r in rr if r[0] not in t1]
    return dict(runs=len(rr), new=len(new),
                new_list=["%s z<=%d %d%s%d %s len %d" % (r[1], r[2], r[0][0], r[0][1], r[0][2], r[0][3:], r[3])
                          for r in new])


def apply(world, CL, S, frames, mod):
    """frames: {f: PIL RGBA}, mod - модуль tree_render_v2. Возвращает (кадры, сводка). Наборы без операций - как есть."""
    global v2
    v2 = mod
    ops = SNOW_SEAM_OPS.get(S)
    if not ops:
        return frames, None
    cur = {f: np.asarray(im.convert("RGBA"), np.uint8).copy() for f, im in frames.items()}
    alpha0 = {f: a[..., 3].copy() for f, a in cur.items()}
    fr0 = {f: a.astype(np.float32) / 255.0 for f, a in cur.items()}
    info = dict(before={"run%d" % r: run_report(world, CL, S, fr0, r) for r in (RUN, 6)}, ops=[])
    for op in ops:
        if op[0] == "quilt":
            fr = {f: a.astype(np.float32) / 255.0 for f, a in cur.items()}
            keys = sorted({c[1] for c in constraints(world, CL, S, fr) if c[1][:3] == tuple(op[1:4])})
            for key in keys:
                info["ops"].append(_quilt_key(world, CL, S, cur, alpha0, key))
        elif op[0] == "twin":
            info["ops"].append(_twin(world, CL, S, cur, alpha0, *op[1:]))
        elif op[0] == "recede":
            info["ops"].append(_recede(world, CL, S, cur, alpha0, *op[1:]))
        else:
            raise SystemExit("snow_seam: неизвестная операция %s" % (op,))
    for f in cur:
        assert np.array_equal(cur[f][..., 3], alpha0[f]), f        # альфа не меняется
    fr1 = {f: a.astype(np.float32) / 255.0 for f, a in cur.items()}
    info["after"] = {"run%d" % r: run_report(world, CL, S, fr1, r) for r in (RUN, 6)}
    info["changed_px"] = {str(f): int((np.abs(cur[f].astype(int) - np.asarray(frames[f].convert("RGBA"), int))
                                       .max(-1) > 0).sum()) for f in sorted(cur)}
    info["changed_px"] = {k: v for k, v in info["changed_px"].items() if v}
    return {f: Image.fromarray(a, "RGBA") for f, a in cur.items()}, info
