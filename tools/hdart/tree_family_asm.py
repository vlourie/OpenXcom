"""Сборка кадров партии TREE_RENDER_V2 по семействам (CPU, модель не грузится; зовётся из tree_family.py
--assemble). Одно семейство - одна производственная единица: один номер кадра - одна картинка, все раскладки
переписи (batchA_layouts.json) собираются из ТЕХ ЖЕ кадров, на каждой - сканер швов и срезов рамкой.

Три вида семейств:
  FOREST-устройство (TG035, кадры 42-57) - tree_render_v2.do_assemble как есть (вид z<=1 составной, кромка,
      снег, ворота спилов), пень 58 - вырезка V1;
  двухэтажные (верх z1, ствол z0) - вид z<=0 из среза V1 с замком латентов, кромка edge_rule на кадрах верха;
  пальмы (верх z2, кусок ствола z1 под кроной) - свободного среза z1 нет (решение 09.10), вид z<=1 строится
      кодом: закрытая кроной часть ствола - кора MAIN тех строк, где ствол виден (перенос строки в профиль
      силуэта классики, недостающие строки - пинг-понгом по видимым), спил сверху - торец древесины v2.wood_face.

Листы - census/trees/groups/batchA/<семейство>/asm/: whole, layouts_<n>, frames, scan.json, summary.json.
"""
import json
import os

import cv2
import numpy as np
from PIL import Image

import tree_render as tr
import tree_render_v2 as v2

po = tr.po
ENC = "utf-8-sig"
BODY_A = 100                 # плотность тела ствола пальмы в MAIN (body_mask)
GOOD_RUN = 0.6               # строка ствола: тело подряд на такой доле пролёта силуэта классики
GRID, RUN = 0.6, 12          # сканер: доля рёбер по сетке базы, длина среза рамкой x4 (seam_scan3, R-313)


def old_frames(S, fs):
    out = {}
    for f in fs:
        p = os.path.join(tr.OLD, S + ".PCK", "%d.png" % f)
        if os.path.exists(p):
            out[f] = Image.open(p).convert("RGBA")
    return out


def stump_cut(world, S, f, sd, args):
    """Пень V1: ответ -> кадр (как tr.do_assemble). Путь кадра или None."""
    p = os.path.join(sd, "stump_%s_%d.png" % (S, f))
    if not os.path.exists(p):
        return None
    spr = tr.sprite(world, S, f)
    box = tr.crop_box(spr, args.pad)
    fr = spr.crop(box)
    part = po.match_tone(po.cut_out(Image.open(p).convert("RGB"), fr, args.grow, args.soft), fr, args.tone)
    cut = Image.new("RGBA", (128, 160), (0, 0, 0, 0))
    cut.paste(part, (box[0] * 4, box[1] * 4))
    od = os.path.join(sd, "stumps", S + ".PCK")
    os.makedirs(od, exist_ok=True)
    out = os.path.join(od, "%d.png" % f)
    po.gen_hd.save_png(cut, out)
    return out


def set_layouts(S, CL):
    tr.LAYOUTS[S] = tuple(("T1" if i == 0 else "L%d" % i, i) for i in range(len(CL[S]["sigs"])))


# ---------------------------------------------------------------- виды этажей
def view0(job, hd, g, tp, V):
    """Вид z<=0 x4 из среза V1 (как tr.views для z = 0) и числа шва и дрейфа."""
    t, b = job.tree, job.box
    known, _cond, free, _U_r = job.canvases(0, hd, g, {})
    raw = Image.open(job.raw_cut(0)).convert("RGB")
    cut = tr.apply_tone(tr.limit_alpha(tr.to_body(raw, g), job.frame_z(0), job.args.grow), tp, job.args.tone)
    cut4 = np.asarray(tr.paste4(cut, b, t), np.uint8)
    U, own, _F = job.masks(0)
    U4, own4 = tr.rep4(U), tr.rep4(own)
    v = np.asarray(V[t.top], np.uint8).copy()
    v[U4 & (own4 == 0)] = cut4[U4 & (own4 == 0)]
    v[U4 & (own4 < 0)] = 0
    ring = (cv2.dilate(U4.astype(np.uint8), np.ones((13, 13), np.uint8)) > 0) & ~U4
    m4 = np.asarray(V[t.top], np.uint8)
    ring &= m4[..., 3] > 200
    seam = float(np.abs(cut4[..., :3].astype(np.int16) - m4[..., :3])[ring].mean()) if ring.any() else -1
    W, H = hd.size
    lock = ~(cv2.resize(cv2.dilate(free.astype(np.uint8), np.ones((5, 5), np.uint8)), (W, H),
                        interpolation=cv2.INTER_NEAREST) > 0)
    drift = float(np.abs(np.asarray(raw, np.int16) - np.asarray(known, np.int16))[lock].mean())
    return Image.fromarray(v), dict(seam_mean_abs=round(seam, 2), locked_vae_drift=round(drift, 2),
                                    free_cells=round(float(free.mean()), 3))


CROWN_FILL_MIN_GREEN = 256    # пикс x4 листвы классики в зоне U, ниже - заливку не делать


def crown_fill(job, V):
    """Вид z<=0, где классика кадра z0 несёт низ кроны (TG037 63): срез V1 там рисует обрубленную лесенкой
    крону и оставляет пустым то, что у классики листва. Под срезом в зоне U (своя часть z0) - MAIN, ограниченный
    силуэтом классики вида z<=0 с запасом grow; срез ложится поверх. Где срез непрозрачен, ничего не меняется."""
    t, b = job.tree, job.box
    lim = tr.sil_limit(job.frame_z(0), job.args.grow)
    L4 = np.zeros((t.H * 4, t.W * 4), np.float32)
    y0, x0 = b[1] * 4, b[0] * 4
    L4[y0:y0 + lim.shape[0], x0:x0 + lim.shape[1]] = lim[:L4.shape[0] - y0, :L4.shape[1] - x0]
    c = np.asarray(job.frame_z(0).convert("RGBA"), np.float32)
    green = (c[..., 3] > 0) & (c[..., 1] > c[..., 0] + 8)
    gw = cv2.GaussianBlur(np.repeat(np.repeat(green, 4, 0), 4, 1).astype(np.float32), (0, 0), 1.5)
    G4 = np.zeros_like(L4)
    G4[y0:y0 + gw.shape[0], x0:x0 + gw.shape[1]] = gw[:L4.shape[0] - y0, :L4.shape[1] - x0]
    U, own, _F = job.masks(0)
    R = tr.rep4(U) & (tr.rep4(own) == 0)
    green_in_zone = int((R & (G4 > 0.5)).sum())
    if green_in_zone < CROWN_FILL_MIN_GREEN:     # у классики в зоне нет листвы (пень пальмы TG021 64) - MAIN не нужен
        return dict(skipped=True, green_in_zone_px=green_in_zone, zone_px=int(R.sum()))
    v = np.asarray(V[0], np.float32)
    m = np.asarray(V[t.top], np.float32)
    v[R, 3] *= 1.0 - G4[R]                   # листва классики - из MAIN; срез остаётся на стволе и спиле
    va = v[..., 3:] / 255.0
    ba = (m[..., 3] * L4)[..., None] / 255.0 * (1.0 - va)
    oa = va + ba
    rgb = (v[..., :3] * va + m[..., :3] * ba) / np.maximum(oa, 1e-6)
    out = v.copy()
    out[R, :3] = rgb[R]
    out[R, 3] = (oa[..., 0] * 255.0)[R]
    if os.environ.get("CROWN_DEBUG"):
        dbg = np.asarray(V[0]).copy()
        dbg[R, 0] = 255
        dbg[G4 > 0.5, 2] = 255
        Image.fromarray(dbg).save(os.environ["CROWN_DEBUG"])
    v0 = np.asarray(V[0])[..., 3]
    filled = int((R & (v0 < 128) & (out[..., 3] >= 128)).sum())
    replaced = int((R & (v0 >= 128) & (G4 > 0.5)).sum())
    V[0] = Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8))
    return dict(filled_px=filled, replaced_px=replaced, zone_px=int(R.sum()),
                zone_opaque_px=int((R & (v0 >= 128)).sum()), classic_green_px=int((G4 > 0.5).sum()),
                green_in_zone_px=int((R & (G4 > 0.5)).sum()))


def body_mask(a, S1):
    """Тело ствола пальмы в MAIN: плотный пиксель у силуэта классики. Ни насыщенность, ни оттенок кору от
    листьев не отличают: теневая сторона коры (29,48,17) насыщенна, как лист; светлый край ствола после матта
    полупрозрачен (альфа 80-200). Листья в строке отсекает выбор строк (пролёт почти целиком тело, ниже кроны)."""
    near = cv2.dilate(S1.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    return (a > BODY_A) & near


def longest_run(cols):
    """Самый длинный отрезок подряд идущих столбцов -> (x0, x1) или None."""
    if len(cols) == 0:
        return None
    br = np.nonzero(np.diff(cols) > 1)[0]
    starts = np.r_[0, br + 1]
    ends = np.r_[br, len(cols) - 1]
    k = int(np.argmax(ends - starts))
    return int(cols[starts[k]]), int(cols[ends[k]])


def palm_view1(job, V, world):
    """Вид z<=1 пальмы x4: MAIN; закрытый кроной кусок ствола z1 - кора MAIN по строкам, спил - торец.
    Где в виде z<=1 владеет кусок ниже - вид z<=0."""
    t = job.tree
    main = np.asarray(V[t.top], np.uint8)
    H, W = main.shape[:2]
    U, own, _F = job.masks(1)
    U4, own4 = tr.rep4(U), tr.rep4(own)
    R = U4 & (own4 == 1)                                     # кусок z1 под кроной: в MAIN его не видно
    cls = np.asarray(tr.xbrz(t.compose(1)), np.uint8)       # гладкий силуэт классики z<=1 x4
    S1 = cls[..., 3] > 127
    bark = body_mask(main[..., 3], S1)
    rows = np.nonzero(S1.any(1))[0]
    span = {}
    for y in rows:
        r = longest_run(np.nonzero(S1[y])[0])
        if r is not None:
            span[y] = r
    # ствол ведём снизу вверх по самому HD-стволу, а не по пролёту классики (у классики ствол прямее и шире:
    # растяжка на пролёт давала щепки сбоку, обрезка по силуэту - ровный срез изогнутого ствола).
    # Строка чистая, если отрезок тела у ожидаемого центра не шире ожидаемого в 1.3 раза и рядом нет
    # других плотных пикселей (лист поперёк ствола или рядом); иначе центр и ширина - продолжением.
    rR = np.nonzero(R.any(1))[0]
    if not len(rR):
        raise SystemExit("%s: у куска z1 нет места под кроной" % job.S)
    ytop, ybot = int(rR[0]), int(rR[-1])
    Z1 = np.zeros((H, W), bool)                              # маска рисования кусков z1 - кадр их и возьмёт
    for q in t.pcs:
        if q["z"] == 1:
            Z1 |= tr.rep4(q["draw"])
    scen = {y: (a + b) / 2.0 for y, (a, b) in span.items()}  # центр ствола классики по строкам
    start = [y for y in range(ybot + 1, min(H, ybot + 41)) if y in span]  # опора: ствол z0 под куском z1
    trk = []
    for y in start:
        x0, x1 = span[y]
        br = longest_run(np.nonzero(bark[y, max(0, x0 - 6):x1 + 7])[0] + max(0, x0 - 6))
        if br and (br[1] - br[0] + 1) >= GOOD_RUN * (x1 - x0 + 1):
            trk.append((y, (br[0] + br[1]) / 2.0, br[1] - br[0] + 1.0))
    if len(trk) < 4:
        raise SystemExit("%s: нет видимого ствола под куском z1 в MAIN - вести ствол неоткуда" % job.S)
    trk.sort()
    band, good = {}, {}
    hist = trk[:12]                                          # ближние к куску строки опоры
    covered = 0
    for y in range(ybot, ytop - 1, -1):
        # центр - ход ствола классики плюс сдвиг HD-ствола от него у ближних строк: продолжение наклона
        # по прямой уводило изогнутый ствол за край кадра, а в классике ствол z1 бывает прямым
        cs = np.array([h[1] for h in hist], np.float32)
        ws = np.array([h[2] for h in hist], np.float32)
        ds = [h[1] - scen[h[0]] for h in hist if h[0] in scen]
        w = float(np.median(ws))
        if y in scen and ds:
            c = scen[y] + float(np.median(ds))
        elif band:
            c = (band[y + 1][0] + band[y + 1][1]) / 2.0     # выше силуэта классики - как строка ниже
        else:
            c = float(cs.mean())
        zc = np.nonzero(Z1[y])[0]                            # полоса - внутри маски кадра куска z1
        if len(zc):
            c = min(max(c, zc[0] + w / 2), zc[-1] - w / 2)
        lo, hi = int(round(c - w / 2)), int(round(c + w / 2))
        bc = np.nonzero(bark[y, max(0, lo - 4):hi + 5])[0] + max(0, lo - 4)
        br = longest_run(bc)
        clean = False
        if covered < 3 and br and br[0] <= c <= br[1]:
            bw = br[1] - br[0] + 1
            wide = bark[y, max(0, int(c - 2.0 * w)):int(c + 2.0 * w) + 1].sum()
            clean = (0.8 * w <= bw <= 1.2 * w) and abs((br[0] + br[1]) / 2.0 - c) <= 0.15 * w + 1 \
                and wide <= bw * 1.05
        covered = 0 if clean else covered + 1               # лист начался - выше ствол только продолжением
        if clean:
            good[y] = br
            band[y] = br
            hist = ([(y, (br[0] + br[1]) / 2.0, float(br[1] - br[0] + 1))] + hist)[:12]
        else:
            band[y] = (max(0, lo), min(W - 1, hi))
    for y, c_, w_ in trk:                                    # опорные строки - тоже источник коры
        good.setdefault(y, (int(round(c_ - w_ / 2)), int(round(c_ + w_ / 2))))
    Gs = sorted(good)
    out = main.copy()
    fill = np.zeros((H, W), bool)
    for zz in range(1):                                      # где в виде z<=1 владеет кусок ниже - вид z<=0
        m = U4 & (own4 == zz)
        out[m] = np.asarray(V[zz], np.uint8)[m]
    out[U4 & (own4 < 0)] = 0
    # место ствола: кусок z1 под кроной и маска его кадра до низа куска (листья MAIN в маске кадра вне R
    # иначе ложились на ствол блоками 4x4); где владеет кусок ниже - не трогаем
    A = (R | (Z1 & (np.arange(H)[:, None] <= ybot))) & ~(U4 & (own4 == 0))
    keep = np.zeros((H, W), bool)                            # чистые строки MAIN - как есть
    for y, (b0, b1) in band.items():
        if y in good and y >= ytop:
            keep[y, b0:b1 + 1] = True
    src_rows = {}
    for y in range(ytop, ybot + 1):
        b0, b1 = band[y]
        if y in good:
            continue
        i = int(np.argmin([abs(g - y) for g in Gs]))         # ближайшая чистая строка, дальше - пинг-понг
        g0, d = Gs[i], abs(Gs[i] - y)
        s = 1 if g0 > y else -1
        P = max(1, min(48, (len(Gs) - 1 - i) if s > 0 else i))
        pp = (d - 1) % (2 * P)
        pp = 2 * P - 1 - pp if pp >= P else pp
        ys = Gs[int(np.clip(i + s * pp, 0, len(Gs) - 1))]
        a0, a1 = good[ys]
        xs = np.arange(b0, b1 + 1)
        sx = np.clip(np.round(a0 + (xs - b0) * (a1 - a0) / max(1, b1 - b0)).astype(int), a0, a1)
        m = A[y, b0:b1 + 1]
        out[y, xs[m], :3] = main[ys, sx[m], :3]
        out[y, xs[m], 3] = main[ys, sx[m], 3]               # край коры полупрозрачен, как в строке-источнике
        fill[y, xs[m]] = True
        src_rows[int(y)] = int(ys)
    out[A & ~fill & ~keep] = 0                               # в куске z1 - только ствол (листья рисует крона)
    # ниже куска z1 в маске его кадра вне силуэта классики - только ствол MAIN (листья кроны мимо)
    for y in range(ybot + 1, H):
        zc = Z1[y] & ~U4[y]
        if not zc.any():
            continue
        c = scen.get(y, (band[ybot][0] + band[ybot][1]) / 2.0)
        w = band[ybot][1] - band[ybot][0] + 1
        br = longest_run(np.nonzero(bark[y, max(0, int(c - w)):int(c + w) + 1])[0] + max(0, int(c - w)))
        ok = np.zeros(W, bool)
        if br:
            ok[max(0, br[0] - 3):br[1] + 4] = True
        out[y, zc & ~ok] = 0
    # стык с видимой корой у границы места ствола: плавно, только где снаружи кора (листья в ствол не тянуть)
    dist = cv2.distanceTransform((~A).astype(np.uint8), cv2.DIST_L2, 3)
    near = (dist > 0) & (dist < 5) & fill
    w = np.clip(dist / 5.0, 0, 1)
    nb = cv2.dilate((bark & ~A).astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    bl = near & nb
    out[bl, :3] = np.round(out[bl, :3] * w[bl, None] + main[bl, :3] * (1 - w[bl, None])).astype(np.uint8)
    # спил сверху: торец древесины по месту верха силуэта ствола в R
    cap = {}
    trunk = fill | keep
    if trunk.any():
        x0, x1 = band[min(ytop + 6, ybot)]
        rx = max(3.0, (x1 - x0) / 2.0)
        ry = max(3.0, rx * 0.45)
        cx, cy = (x0 + x1) / 2.0, ytop + ry
        lab = v2._lab8(out[trunk][:, :3].astype(np.float32))
        bark_lab = lab.mean(0)
        k1 = np.asarray(t.compose(1), np.uint8)          # спил классики: светлые пиксели верха куска z1
        top1 = ytop // 4
        sel = (k1[top1:top1 + 3, :, 3] > 0)
        cl = v2._lab8(k1[top1:top1 + 3][sel][:, :3].astype(np.float32)) if sel.any() else bark_lab[None]
        lt = cl[cl[:, 0] > bark_lab[0] + 5]
        wood = lt.mean(0) if len(lt) else np.array([bark_lab[0] + 25, bark_lab[1], bark_lab[2] + 6])
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        box, crgb, wcap, _rr = v2.wood_face(xx, yy, cx, cy, rx, ry, float(wood[0]), wood[1:], bark_lab,
                                            np.random.default_rng(57))
        full = np.zeros((H, W, 3), np.float32)
        full[box] = crgb
        wc = wcap * (box & A)
        out[..., :3] = np.round(out[..., :3] * (1 - wc[..., None]) + full * wc[..., None]).astype(np.uint8)
        # верх ствола - верхняя половина эллипса спила: углы полосы над ним прозрачны (иначе прямоугольник)
        e = np.sqrt(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2)
        up = (yy < cy) & A
        k = np.clip((1.0 - e) * min(rx, ry) + 0.5, 0, 1)
        out[up, 3] = np.round(out[up, 3] * k[up]).astype(np.uint8)
        cap = dict(cx=round(cx, 1), cy=round(cy, 1), rx=round(rx, 1), ry=round(ry, 1), wood_L=round(float(wood[0]), 1))
    info = dict(R_px=int(R.sum()), filled_px=int(fill.sum()), kept_px=int(keep.sum()),
                rows=ybot - ytop + 1, clean_rows=sum(1 for y in range(ytop, ybot + 1) if y in good),
                synthetic_rows=len(src_rows), cap=cap)
    return Image.fromarray(out), info


# ---------------------------------------------------------------- сканер швов (seam_scan3, R-313)
def _build(world, S, sig, frames, k=4):
    rows = []
    for f, p, x, y, z in sig:
        rows.append(((z, y, x, p), f, (x - y) * 16, (x + y) * 8 - z * 24 - tr.plevel(world, S, f)))
    rows.sort()
    x0 = min(r[2] for r in rows) - 8
    y0 = min(r[3] for r in rows) - 8
    W = (max(r[2] for r in rows) - x0 + 40) * k
    H = (max(r[3] for r in rows) - y0 + 48) * k
    own = np.full((H, W), -1, np.int32)
    names, boxes = [], []
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for i, (key, f, sx, sy) in enumerate(rows):
        s = frames[f]
        ox, oy = (sx - x0) * k, (sy - y0) * k
        im.alpha_composite(s, (ox, oy))
        a = np.asarray(s, np.uint8)[..., 3] >= 128
        own[oy:oy + a.shape[0], ox:ox + a.shape[1]][a] = i
        names.append("%d@z%d(%d,%d)" % (f, key[0], key[2], key[1]))
        boxes.append((ox, oy, a.shape[1], a.shape[0]))
    alpha = np.asarray(im, np.uint8)[..., 3]
    rgb = np.asarray(tr.on_floor(im).convert("RGB"), np.float32)
    return rgb, own, alpha, names, boxes


def _inner(rgb, own, names, minlen=24):
    pairs, steps_in = {}, []
    H, W = own.shape
    for dy, dx in ((0, 1), (1, 0)):
        a, b = own[:H - dy, :W - dx], own[dy:, dx:]
        st = np.abs(rgb[:H - dy, :W - dx] - rgb[dy:, dx:]).mean(-1)
        same = (a == b) & (a >= 0)
        steps_in.append(st[same])
        diff = (a != b) & (a >= 0) & (b >= 0)
        yy, xx = np.nonzero(diff)
        on = ((yy + dy) % 4 == 0) if dy else ((xx + dx) % 4 == 0)
        for u, v, s, g in zip(a[diff], b[diff], st[diff], on):
            pairs.setdefault((min(u, v), max(u, v)), []).append((s, g))
    base = float(np.concatenate(steps_in).mean())
    out = {}
    for (u, v), L in pairs.items():
        if len(L) >= minlen:
            s = np.array(L, np.float32)
            out["%s|%s" % (names[u], names[v])] = [len(L), float(s[:, 1].mean()), float(s[:, 0].mean()) / base]
    return out


def _longest(m):
    best = cur = 0
    for v in m:
        cur = cur + 1 if v else 0
        best = max(best, cur)
    return best


def _border(own, alpha, names, boxes, allow=None):
    # allow: кадр -> маска 160x128 пикселей, которые у рамки срезом не считаются (вершины ромба подставленного пола)
    out = {}
    for i, (ox, oy, w, h) in enumerate(boxes):
        ok = (allow or {}).get(int(names[i].split("@")[0]))
        if ok is None:
            ok = np.zeros((h, w), bool)
        for sd, ys, xin, xout in (("L", slice(oy, oy + h), ox, ox - 1), ("R", slice(oy, oy + h), ox + w - 1, ox + w)):
            m = (own[ys, xin] == i) & (alpha[ys, xout] < 32) & ~ok[:, xin - ox]
            if m.any():
                out["%s|%s" % (names[i], sd)] = (_longest(m), int(m.sum()))
        for sd, yin, yout in (("T", oy, oy - 1), ("B", oy + h - 1, oy + h)):
            m = (own[yin, ox:ox + w] == i) & (alpha[yout, ox:ox + w] < 32) & ~ok[yin - oy]
            if m.any():
                out["%s|%s" % (names[i], sd)] = (_longest(m), int(m.sum()))
    return out


def _rel(pair):
    import re
    rx = re.compile(r"(\d+)@z(\d+)\((\d+),(\d+)\)")
    a, b = [tuple(map(int, rx.match(p).groups())) for p in pair.split("|")]
    return (a[0], b[0], b[1] - a[1], b[2] - a[2], b[3] - a[3])


def scan(world, CL, S, frames, allow=None):
    res = {}
    for name, i in tr.LAYOUTS[S]:
        sig = CL[S]["sigs"][i]["sig"]
        for zmax in (0, 1, 2, 99):
            sg = [e for e in sig if e[4] <= zmax]
            if not sg:
                continue
            rgb, own, alpha, names, boxes = _build(world, S, sg, frames)
            res["%s|z%d" % (name, zmax)] = {"inner": _inner(rgb, own, names),
                                             "border": _border(own, alpha, names, boxes, allow)}
    ref = {}
    for lay, v in res.items():
        if lay.startswith("T1|"):
            for pair, (n, g, r) in v["inner"].items():
                k = _rel(pair)
                ref[k] = max(ref.get(k, 0), r)
    seams, cuts = [], []
    for lay, v in res.items():
        for pair, (n, g, r) in v["inner"].items():
            e = ref.get(_rel(pair), 1.7)
            if not lay.startswith("T1|") and g >= GRID and r > max(2.0, e + 0.5):
                seams.append([lay, pair, n, round(g, 2), round(r, 2), round(e, 2)])
        for k, (run, tot) in v["border"].items():
            if run >= RUN:
                cuts.append([lay, k, run, tot])
    return dict(layouts=len(tr.LAYOUTS[S]), views=len(res), open_seams=seams, frame_cuts=cuts)


# ---------------------------------------------------------------- листы
def sheets(world, CL, S, frames, olds, whole_rows, od, title, fs):
    tr.grid(whole_rows, os.path.join(od, "%s_whole.png" % S), "%s: whole tree" % title)
    rows = []
    for name, i in tr.LAYOUTS[S]:
        sig = CL[S]["sigs"][i]["sig"]
        ztop = max(e[4] for e in sig)
        n = CL[S]["sigs"][i]["n"]
        for kind, fr in (("classic", None), ("old", olds), ("new", frames)):
            rows.append(("%s n%d %s" % (name, n, kind),
                         [("z<=%d" % z, tr.assemble(world, S, sig, fr, z)) for z in range(ztop, -1, -1)]))
    per = 18                                                 # шесть раскладок на лист
    for j in range(0, len(rows), per):
        tr.grid(rows[j:j + per], os.path.join(od, "%s_layouts_%d.png" % (S, j // per + 1)),
                "%s: layouts from the SAME frames; classic | old | new; columns = floors" % title, scale=0.5)
    frow = [("%d" % f, [("classic", tr.sprite(world, S, f).resize((128, 160), Image.NEAREST)),
                        ("old", olds.get(f, Image.new("RGBA", (128, 160)))), ("new", frames[f])]) for f in fs]
    half = (len(frow) + 1) // 2
    pairs = [(a[0] + " | " + b[0], a[1] + b[1]) for a, b in zip(frow[:half], frow[half:])]
    if len(frow) % 2:
        pairs.append(frow[half - 1])
    tr.grid(pairs if len(frow) > 1 else frow, os.path.join(od, "%s_frames.png" % S),
            "%s: frames classic | old | new" % title)


# ---------------------------------------------------------------- семейство
def assemble_v1(args, fid, S, world, CL, hints, seed):
    """Двухэтажные и пальмы: вид верха - MAIN, вид z<=0 - срез V1, у пальм вид z<=1 - кодом."""
    job = tr.Job(world, CL, hints, S, seed, args)
    t = job.tree
    if not (os.path.exists(job.raw_main) and (t.top == 0 or os.path.exists(job.raw_cut(0)))):
        print("  %s %s s%d: ответов нет - пропуск" % (fid, S, seed), flush=True)
        return None
    if t.top == 0:                           # модуль в один этаж (крона ели): весь вид - MAIN, срезов нет
        hd, g, tp, main = job.main_cut()
        job._g = g
        V, stats = {0: tr.paste4(main, job.box, t)}, {}
    elif t.top == 1:
        V, stats = tr.views(job)
    else:
        hd, g, tp, main = job.main_cut()
        job._g = g
        V = {t.top: tr.paste4(main, job.box, t)}
        V[0], st0 = view0(job, hd, g, tp, V)
        stats = {"z0": st0}
    if t.top > 0:
        stats["crown_fill"] = crown_fill(job, V)
    if t.top == 2:
        V[1], stats["z1_code"] = palm_view1(job, V, world)
    elif t.top > 2:
        raise SystemExit("%s: верх на этаже %d - выше трёх этажей" % (S, t.top))
    frames, multi = tr.pieces(job, V)
    srcs = {q["f"]: (V[q["z"]], q) for q in t.pcs}
    fam = {q["f"]: ("FULL" if q["z"] == t.top else "Z%d_EXPOSED" % q["z"]) for q in t.pcs}
    crown = tuple(sorted({q["f"] for q in t.pcs if q["z"] == t.top}))
    keep = v2.EDGE_FRAMES
    v2.EDGE_FRAMES = crown
    try:
        frames, edge = v2.edge_rule(world, CL, S, frames, srcs, fam)
    finally:
        v2.EDGE_FRAMES = keep
    stats["edge"] = edge
    stats["valpha"] = {q["f"]: np.asarray(Image.fromarray(np.asarray(V[q["z"]], np.uint8))
                                          .crop(v2.pos_box(q)))[..., 3] for q in t.pcs}
    stats["multi_position_frames"] = multi
    sig0 = CL[S]["sigs"][0]["sig"]
    stats["T1_assembled_vs_intended"] = {"z<=%d" % z: tr.diff(tr.assemble(world, S, sig0, frames, z),
                                                              tr.crop_like(V[z], tr.assemble(world, S, sig0, frames, z)))
                                         for z in range(t.top, -1, -1)}
    return job, V, frames, fam, stats


BUSH_SRC = (54, 53, 55, 47, 46, 45, 43)     # кадры кроны - плотная листва для клона (FOREST-устройство)
BUSH_SHIFTS = ((0, 0),) + v2.CLONE_SHIFTS + ((-16, 0), (-32, 0), (0, 16), (0, -16), (0, 32), (0, -32))
TOP_BAND = 40                # x4: полоса у верхней рамки, где листва уходит дугой силуэта классики
TOP_GROW = 6                 # x4: запас силуэта классики наружу у верхней рамки


def z0_bushes(world, S, frames):
    """Кадр 57 FOREST-устройства, у которого на классике вокруг ствола листва и трава (FJS): ни MAIN, ни срез z0
    их не рисуют, v2.z0_trunk вырезает V1 вне ствола блоками рамок 4x4 - квадратные выемки. Под существующим -
    клон плотной листвы кадров кроны того же набора по маске зелёного классики 57 (мягко, R-311), край - по
    фактуре листьев (яркость клона), тон к классике на месте (трава светлее листвы). Непрозрачное не меняется."""
    c = np.asarray(tr.sprite(world, S, 57).convert("RGBA"), np.float32)
    green = (c[..., 3] > 0) & (c[..., 1] > c[..., 0] + 8)
    b = cv2.GaussianBlur(tr.rep4(green).astype(np.float32), (0, 0), 4.0)
    zone = b > 0.12
    v = np.asarray(frames[57], np.float32)
    fcol = np.zeros(v.shape[:2] + (3,), np.float32)
    have = np.zeros(v.shape[:2], bool)
    for f in BUSH_SRC:
        m = np.asarray(frames[f], np.float32)
        for dy, dx in BUSH_SHIFTS:
            sh = np.roll(np.roll(m, -dy, 0), -dx, 1)
            ok = zone & ~have & (sh[..., 3] > 230)
            fcol[ok] = sh[..., :3][ok]
            have |= ok
    lum = fcol @ np.array([0.299, 0.587, 0.114], np.float32)
    mu, sd = float(lum[have].mean()), float(lum[have].std()) + 1e-3
    a_f = np.clip((b - 0.45) * 4.0 + (lum - mu) / sd * 0.35, 0.0, 1.0) * have
    # у боковых рамок клон гаснет: иначе листва ровно по рамке - новый срез (57|L)
    xs = np.arange(v.shape[1], dtype=np.float32)[None, :]
    a_f *= np.clip(np.minimum(xs, v.shape[1] - 1 - xs) / 12.0, 0.0, 1.0)
    # тон: размытое классики против размытого клона, по зоне (трава у основания светлее листвы кроны)
    c4 = np.repeat(np.repeat(c[..., :3], 4, 0), 4, 1)
    g4 = tr.rep4(green).astype(np.float32)[..., None]
    k = (0, 0)
    cl = cv2.GaussianBlur(c4 * g4, k, 10.0) / np.maximum(cv2.GaussianBlur(g4[..., 0], k, 10.0)[..., None], 1e-3)
    hv = have.astype(np.float32)[..., None]
    fl = cv2.GaussianBlur(fcol * hv, k, 10.0) / np.maximum(cv2.GaussianBlur(hv[..., 0], k, 10.0)[..., None], 1e-3)
    fcol = np.clip(fcol + 0.6 * (cl - fl), 0, 255)
    a = v[..., 3:] / 255.0
    out = v.copy()
    out[..., :3] = np.where(a_f[..., None] > 0, v[..., :3] * a + fcol * (1 - a), v[..., :3])
    out[..., 3] = np.maximum(v[..., 3], 255.0 * a_f)
    frames[57] = Image.fromarray(np.clip(np.round(out), 0, 255).astype(np.uint8), "RGBA")
    return dict(zone_px=int(zone.sum()), filled_px=int(((a_f > 0) & (v[..., 3] < 255)).sum()))


def top_recede(world, S, frames, fs):
    """Листва HD дотягивает до верхней рамки, а у классики верхние строки кадра пусты: на виде открывается
    прямой срез рамкой (FJS 44@z2, 48@z1, 52@z1). В полосе у верхней рамки альфа - не шире силуэта классики
    с запасом TOP_GROW, мягко (дуга кроны, не прямая, R-318). Ниже полосы и у кадров с верхом классики - как было."""
    done = {}
    yy = np.arange(160, dtype=np.float32)[:, None]
    wband = np.clip((TOP_BAND - yy) / 12.0, 0.0, 1.0)            # 1 у рамки, 0 ниже полосы
    for f in fs:
        c = np.asarray(tr.sprite(world, S, f).convert("RGBA"))[..., 3] > 0
        if not c.any() or c[0].any():
            continue
        v = np.asarray(frames[f], np.float32)
        if not (v[:4, :, 3] > 32).any():
            continue
        # запас вбок TOP_GROW, вверх 1: у классики пуста часто одна строка базы (4 x4), запас 6 её закрывал
        ker = np.zeros((3, 2 * TOP_GROW + 1), np.uint8)
        ker[1] = 1
        ker[:, TOP_GROW] = 1
        m = cv2.dilate(tr.rep4(c).astype(np.uint8), ker).astype(np.float32)
        m = cv2.GaussianBlur(m, (0, 0), 1.5)
        lim = 1.0 - wband * (1.0 - m)
        na = v[..., 3] * lim
        cut = int(((v[..., 3] > 32) & (na <= 32)).sum())
        v[..., 3] = na
        frames[f] = Image.fromarray(np.clip(np.round(v), 0, 255).astype(np.uint8), "RGBA")
        done[f] = cut
    return done


GRID_R = 8                   # x4: насколько кадр дорастает за прямой край по сетке базы (как v2.EDGE_R)


def grid_heal(world, S, frames, valpha=None):
    """След блочной маски (кадр = вид x rep4(маска рисования)) у ЛЮБОГО кадра семейства, не только у кроны
    edge_rule: дырки - замкнутые прямоугольники по сетке 4x4 внутри силуэта (tree_qc.pinholes), и прямые жёсткие
    края по сетке (tree_qc.hard_edges). Под прозрачным у кадра лежит RGB вида: дырка закрывается им (где вид сам
    прозрачен - inpaint), за краем по сетке кадр дорастает видом с мягким сходом по пучкам листвы, не дальше
    GRID_R x4 и не дальше силуэта СВОЕЙ классики (R-315). valpha: {f: альфа вида в рамке кадра}; без неё (путь
    TG035) - вид там, где под прозрачным есть RGB. Выемки по сетке (tree_qc.notches) закрываются видом.
    Меняет frames на месте, возвращает сводку по кадрам."""
    import tree_qc as q
    info = {}
    yy, xx = np.mgrid[0:160, 0:128].astype(np.float32)
    wbox = np.clip(np.minimum(xx, 127 - xx) / 12.0, 0, 1) * np.clip(np.minimum(yy, 159 - yy) / 6.0, 0, 1)
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * GRID_R + 1, 2 * GRID_R + 1))
    for f in sorted(frames):
        a = np.asarray(frames[f]).copy()
        al = a[..., 3]
        if valpha is not None and f in valpha:
            va = valpha[f].astype(np.float32)
        else:
            va = np.where((al > 0) | (a[..., :3].max(-1) > 8), 255.0, 0.0).astype(np.float32)
        hole = q.pinholes(al)
        notch = q.notches(al, a[..., :3])
        _e, em, _ev = q.hard_edges(al)
        if not hole.any() and not notch.any() and not em.any():
            continue
        st = {}
        if notch.any():
            # выемка по сетке, открытая с одной стороны (TG011 35, TG035 54, TG037 63): под ней RGB вида - тот же
            # рисунок, срезанный клеткой маски; закрыть им, где вид непрозрачен
            nm = notch & ((va >= 128) if valpha is not None and f in valpha else (a[..., :3].max(-1) > 8))
            a[..., 3][nm] = 255
            st["notch_px"] = int(nm.sum())
            if (notch & ~nm).any():
                st["notch_left_px"] = int((notch & ~nm).sum())
        if hole.any():
            bad = hole & (va < 128)
            if bad.any():
                rgb = cv2.inpaint(np.ascontiguousarray(a[..., :3]), bad.astype(np.uint8), 3, cv2.INPAINT_TELEA)
                a[..., :3][bad] = rgb[bad]
            a[..., 3][hole] = 255
            st["holes_px"] = int(hole.sum())
        if em.any():
            c = np.asarray(tr.sprite(world, S, f).convert("RGBA"))[..., 3] > 0
            lim = cv2.GaussianBlur(cv2.dilate(tr.rep4(c).astype(np.uint8), np.ones((5, 5), np.uint8))
                                   .astype(np.float32), (0, 0), 1.5)
            on = (a[..., 3] >= 128).astype(np.uint8)
            d = cv2.distanceTransform(1 - on, cv2.DIST_L2, 5)
            zone = np.clip(cv2.GaussianBlur(cv2.dilate(em.astype(np.uint8), ker).astype(np.float32), (0, 0), 3.0)
                           * 1.5, 0, 1)
            Y = a[..., :3].astype(np.float32).mean(-1)
            tn = np.clip((cv2.GaussianBlur(Y, (0, 0), 1.5) - cv2.GaussianBlur(Y, (0, 0), 6)) / 14.0, -1, 1)
            w = np.clip((GRID_R - d + 2.5 * tn) / 1.6 + 0.5, 0, 1) * wbox * lim * zone
            # где вид за краем пуст, а своя классика там рисует (TG038 62, TG037 63: веточка классики, которой у
            # вида нет), кадр дорастает своим же рисунком, отражённым через край: заливка из-под края
            ref = grid_mirror(a, _e)
            al0 = a[..., 3].astype(np.float32)
            add_v, add_r = va * w, ref[..., 3].astype(np.float32) * w
            use_r = (add_r > add_v + 32) & (add_r > al0)
            a[..., :3][use_r] = ref[..., :3][use_r]
            new = np.maximum(al0, np.maximum(add_v, np.where(use_r, add_r, 0)))
            st["skirt_px"] = int(((new >= 128) & (a[..., 3] < 128)).sum())
            st["mirror_px"] = int((use_r & (new >= 128)).sum())
            st["grid_edges"] = len(_e)
            a[..., 3] = np.clip(np.round(new), 0, 255).astype(np.uint8)
        frames[f] = Image.fromarray(a, "RGBA")
        info[str(f)] = st
    return info


ACCENT_RATIO = 1.8           # красного HD больше, чем красного классики x16, во столько раз - кадр правится
ACCENT_MIN = 150             # x4: и столько красного HD вне запаса классики (шум коры TG011 32/33 - 83-167)
ACCENT_GROW = 3              # x4: запас вокруг красного классики
ACCENT_SHIFTS = sorted(((dy, dx) for dy in range(-64, 65, 8) for dx in range(-48, 49, 8) if abs(dy) + abs(dx) >= 16),
                       key=lambda s: (s[0] < 0, abs(s[0]) + abs(s[1])))    # сначала снизу: под спилом - листва


def _accent(a):
    r, g, b = (a[..., i].astype(np.int32) for i in range(3))
    return (a[..., 3] > 128) & (r > g + 30) & (r > b + 10)


def accent_limit(world, S, frames, fs):
    """Спилы на верхах кроны (TG035 49/51): у классики мелкие красные обрубки и веточки, модель рисует их крупными
    дисками торца. В кадре, где красного HD много больше, чем у классики, красное (с каймой) заменяется листвой
    клоном из того же кадра в пределах силуэта классики (вне силуэта - прозрачно), поверх - обрубки по форме
    красного классики x4 мягко, цвет классики, фактура - яркость прежнего красного HD. fs - кадры кроны, без
    нижнего этажа (ствол у земли шире классики нарочно, R-319). Меняет frames на месте."""
    info = {}
    el = lambda r: cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    for f in fs:
        a = np.asarray(frames[f]).copy()
        c = np.asarray(tr.sprite(world, S, f).convert("RGBA"))
        c4 = tr.rep4(_accent(c))
        hr = _accent(a)
        out = hr & ~(cv2.dilate(c4.astype(np.uint8), el(ACCENT_GROW)) > 0)
        if hr.sum() <= ACCENT_RATIO * c4.sum() or out.sum() < ACCENT_MIN:
            continue
        zone = cv2.dilate(hr.astype(np.uint8), el(3)) > 0
        src = (a[..., 3] > 230) & ~(cv2.dilate(hr.astype(np.uint8), el(6)) > 0)
        fol = np.zeros(a.shape[:2] + (3,), np.uint8)
        have = np.zeros(a.shape[:2], bool)
        for dy, dx in ACCENT_SHIFTS:
            sh = np.roll(np.roll(a, -dy, 0), -dx, 1)
            ok = zone & ~have & np.roll(np.roll(src, -dy, 0), -dx, 1)
            fol[ok] = sh[..., :3][ok]
            have |= ok
        sil = cv2.GaussianBlur(cv2.dilate(tr.rep4(c[..., 3] > 0).astype(np.uint8), np.ones((5, 5), np.uint8))
                               .astype(np.float32), (0, 0), 1.5)
        L = a[..., :3].astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)
        det = np.where(hr, L / np.maximum(cv2.GaussianBlur(L, (0, 0), 6.0), 1.0), 1.0)
        rgb = a[..., :3].astype(np.float32)
        al = a[..., 3].astype(np.float32)
        rgb[zone & have] = fol[zone & have]
        rgb[zone & ~have] = cv2.inpaint(np.ascontiguousarray(a[..., :3]), (zone & ~have).astype(np.uint8), 3,
                                        cv2.INPAINT_TELEA)[zone & ~have]
        al[zone] = np.minimum(np.where(have[zone], 255.0, al[zone]), 255.0 * sil[zone])
        cm = c4.astype(np.float32)
        c4rgb = np.repeat(np.repeat(c[..., :3].astype(np.float32), 4, 0), 4, 1)
        k = (0, 0)
        crgb = cv2.GaussianBlur(c4rgb * cm[..., None], k, 2.0) / np.maximum(cv2.GaussianBlur(cm, k, 2.0)[..., None], 1e-3)
        sa = np.clip((cv2.GaussianBlur(cm, k, 1.4) - 0.35) * 4.0, 0, 1)
        srgb = np.clip(crgb * np.clip(det, 0.7, 1.3)[..., None], 0, 255)
        rgb = srgb * sa[..., None] + rgb * (1 - sa[..., None])
        al = np.maximum(al, 255.0 * sa)
        frames[f] = Image.fromarray(np.dstack([np.clip(np.round(rgb), 0, 255), np.clip(np.round(al), 0, 255)])
                                    .astype(np.uint8), "RGBA")
        info[str(f)] = dict(hd_red_px=int(hr.sum()), classic_red_x16=int(c4.sum()), out_px=int(out.sum()),
                            zone_px=int(zone.sum()), cloned_px=int((zone & have).sum()))
    return info


def grid_mirror(a, edges):
    """Рисунок кадра, отражённый через прямые края по сетке (tree_qc.hard_edges): за краем на GRID_R x4 - то, что
    лежит под краем внутри кадра, зеркально. Остальное прозрачно."""
    out = np.zeros_like(a)
    H, W = a.shape[:2]
    for side, pos, s0, n in edges:
        for dd in range(1, GRID_R + 1):
            if side == "T":
                yo, yi = pos - dd, pos + dd - 1
                if 0 <= yo and yi < H:
                    out[yo, s0:s0 + n] = a[yi, s0:s0 + n]
            elif side == "B":
                yo, yi = pos + dd, pos - dd + 1
                if yo < H and yi >= 0:
                    out[yo, s0:s0 + n] = a[yi, s0:s0 + n]
            elif side == "L":
                xo, xi = pos - dd, pos + dd - 1
                if 0 <= xo and xi < W:
                    out[s0:s0 + n, xo] = a[s0:s0 + n, xi]
            else:
                xo, xi = pos + dd, pos - dd + 1
                if xo < W and xi >= 0:
                    out[s0:s0 + n, xo] = a[s0:s0 + n, xi]
    return out


def f57_v1(args, world, CL, hints, S, seed):
    """Кадр 57 по пути V1: срез модели под силуэтом классики (limit_alpha, запас args.grow) и тоном MAIN, без
    построчной подгонки ствола V2 (z0_trunk, even_rows, f57_details). У FJS эта подгонка тянет ствол под профиль
    классики с высоким сучком: верх ствола - прямоугольник, по стволу горизонтальные полосы, шов с кроной
    54@z1 скачок ширины 26.2 и цвета 35.4 против 2.5 и 4.2 у V1 (summary_comp.json, seam_v1 / seam_v2)."""
    job = tr.Job(world, CL, hints, S, seed, args)
    t = job.tree
    hd, g, tp, main = job.main_cut()
    job._g = g
    V = {t.top: tr.paste4(main, job.box, t)}
    _v0, st = view0(job, hd, g, tp, V)
    # кадр целиком из среза: вид z<=0 (view0) берёт срез только в клетках, где кадр 57 виден на z<=0, а в
    # остальных - MAIN; на границе клеток в кадре квадраты тёмной коры MAIN, в T1 - полосы торца (проба 13.10)
    raw = Image.open(job.raw_cut(0)).convert("RGB")
    cut = tr.apply_tone(tr.limit_alpha(tr.to_body(raw, g), job.frame_z(0), args.grow), tp, args.tone)
    q57 = next(q for q in t.pcs if q["f"] == 57)
    fr, st["cut_face"] = sawn_face(world, S, v2.frame_from(tr.paste4(cut, job.box, t), q57))
    return fr, st


def sawn_face(world, S, frame):
    """Торец спила на верху ствола кадра 57: модель рисует спил ребром (тонкая линия), у классики - кольцо.
    Как в v2.f57_details: эллипс под верхом ствола, только внутри непрозрачного (силуэт прежний), древесина -
    пень HD, оттенок - торец классики (верхние 4 строки, красное), кора обода - средняя коры кадра."""
    fr = np.asarray(frame, np.float32).copy()
    a = fr[..., 3]
    rows = np.where((a > 200).sum(1) >= 8)[0]
    ht = int(rows[0])
    xs = np.where(a[ht + 8] > 200)[0]
    mid = int(np.median(xs))
    run = xs[np.abs(xs - mid) <= 64]
    x0, x1 = int(run.min()), int(run.max())
    cl = np.asarray(tr.sprite(world, S, 57), np.int16)
    clt = int(np.where(cl[..., 3].any(1))[0][0])
    top = cl[clt:clt + 4]
    om = (top[..., 3] > 0) & (top[..., 0] > top[..., 1] + 25)
    face_lab = v2._lab8(top[..., :3][om].astype(np.float32)).mean(0)
    sp = np.asarray(Image.open(v2.stump_src(S)).convert("RGBA"), np.float32)
    wood = v2._lab8(sp[(sp[..., 3] > 200) & (sp[..., :3].mean(-1) > 60)][:, :3])
    L0 = float(np.percentile(wood[:, 0], 60))
    tm = (a > 200) & (fr[..., 0] >= fr[..., 1])
    bm = v2._lab8(fr[..., :3][tm]).mean(0)
    rx = (x1 - x0) / 2.0 - 2.0
    ry = max(rx * 0.32, 5.0)
    cx, cy = (x0 + x1) / 2.0, ht + ry + 1.0
    yy, xx = np.mgrid[0:fr.shape[0], 0:fr.shape[1]].astype(np.float32)
    box, crgb, wcap, _rr = v2.wood_face(xx, yy, cx, cy, rx, ry, L0, face_lab[1:], bm, np.random.default_rng(57))
    wcap = wcap * np.clip((a - 200) / 55.0, 0, 1)
    wb = wcap[box][..., None]
    fr[..., :3][box] = fr[..., :3][box] * (1 - wb) + crgb * wb
    return (Image.fromarray(np.clip(np.round(fr), 0, 255).astype(np.uint8), "RGBA"),
            dict(top_row_x4=ht, x=[x0, x1], rx=round(rx, 1), ry=round(ry, 1)))


GROUND_FROM = 80             # x4: строка, ниже которой у кадра 57 трава и корни (полоса ограничения)
GROUND_GROW = 2              # пикс базы: запас силуэта классики наружу, как у limit_alpha срезов
GROUND_EDGE = 16             # x4: у боковых рамок запас сходит на ноль


def ground_limit(world, S, frames, f=57):
    """Низ MAIN под стволом - круглая лужайка шире ромба классики (FJS 57: на y140 HD 11..127 против 24..103) и
    упирается в правую рамку строками 91-142 - срезы 57|R во всех раскладках. В полосе ниже GROUND_FROM альфа не
    шире силуэта классики (tr.sil_limit, гладкий край) с запасом GROUND_GROW, а у боковых рамок без запаса: ромб
    классики касается рамки только вершиной, запас вдоль рамки дотянул бы его до среза. Выше полосы - как было."""
    v = np.asarray(frames[f], np.float32)
    cl = tr.sprite(world, S, f).convert("RGBA")
    xs = np.arange(v.shape[1], dtype=np.float32)[None, :]
    e = np.clip((GROUND_EDGE - np.minimum(xs, v.shape[1] - 1 - xs)) / GROUND_EDGE, 0.0, 1.0)
    lim = tr.sil_limit(cl, GROUND_GROW) * (1.0 - e) + tr.sil_limit(cl, 0) * e
    yy = np.arange(v.shape[0], dtype=np.float32)[:, None]
    w = np.clip((yy - GROUND_FROM) / 12.0, 0.0, 1.0)
    na = v[..., 3] * (1.0 - w * (1.0 - lim))
    cut = int(((v[..., 3] > 32) & (na <= 32)).sum())
    v[..., 3] = na
    frames[f] = Image.fromarray(np.clip(np.round(v), 0, 255).astype(np.uint8), "RGBA")
    return dict(cut_px=cut)


BARK_SIGMA = 3.0             # x4: окно доли коры классики вокруг пикселя
BARK_LOCAL = 8.0             # x4: окно местного тона коры (2 пикс базы) - мельче вернёт лесенку классики
BARK_ITERS = 3
BARK_AB_SQUEEZE = 0.85       # доля отклонения цветности коры от местного среднего, которая снимается (0.6 - у JUNGLE
                             # освещённая половина ствола оставалась зелёной; яркость фактуры не трогается)
BARK_TRUNK_R = 24           # x4: ствол - в пределах 6 пикс базы от ядра коры HD (полоса мха)
BARK_LEAF_K = 4             # центров цвета листвы HD (там, где классика зелёная)
BARK_SNOW_L, BARK_SNOW_C = 60.0, 14.0   # светлое и почти серое у классики - снег, не кора


def _lab(rgb):
    return cv2.cvtColor((rgb / 255.0).astype(np.float32), cv2.COLOR_RGB2LAB)


def _rgb(lab):
    return np.clip(cv2.cvtColor(lab.astype(np.float32), cv2.COLOR_LAB2RGB) * 255.0, 0, 255)


def _blur(a, s):
    return cv2.GaussianBlur(a.astype(np.float32), (0, 0), s)


def _ground_mask(h=160, w=128, up=4.0):
    """Ромб пола клетки в кадре x4 (база: центр 15.5, 31.5, полуоси 16 и 8), верх поднят на up пикс базы -
    травинки; край мягкий в 2 пикс x4."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    x, y = (xx + 0.5) / 4.0 - 0.5, (yy + 0.5) / 4.0 - 0.5
    dy = np.where(y < 31.5, (31.5 - y) / (8.0 + up), (y - 31.5) / 8.0)
    d = np.abs(x - 15.5) / 16.0 + dy
    return np.clip((1.0 - d) * 8.0 + 0.5, 0.0, 1.0)


_ground = _ground_mask()


def _trunk_down(tm, g, rows=40, cls=None):
    """Ствол в ромбе земли: края ствола tm по строкам над землёй (g > 0.5 - не земля), прямая с отсевом выбросов
    по последним rows строкам, продолжена до низа кадра; край мягкий в 2 пикс x4. Ствола над землёй нет - нули.
    cls - кора классики x4: ниже края земли центр ствола ведётся по ней строка за строкой (ствол у корня гнётся,
    прямая этого не видит - у JUNGLE 32 уходила на 16 пикс x4 вбок), ширина - по прямой; кора классики в строке
    кончилась - ствола ниже нет."""
    h, w = tm.shape
    yg = int(np.argmax((g < 0.5).any(1))) if (g < 0.5).any() else h
    ys, ls, rs = [], [], []
    for y in range(max(0, yg - rows), yg):
        xs = np.flatnonzero(tm[y])
        if len(xs) >= 3:
            ys.append(y); ls.append(xs[0]); rs.append(xs[-1])
    out = np.zeros((h, w), np.float32)
    if len(ys) < 8:
        return out
    ys = np.array(ys, np.float32)
    fit = []
    for v in (np.array(ls, np.float32), np.array(rs, np.float32)):
        keep = np.ones(len(ys), bool)
        for _ in range(3):
            p = np.polyfit(ys[keep], v[keep], 1)
            r = np.abs(np.polyval(p, ys) - v)
            keep = r <= max(2.0, 2.0 * float(np.median(r)))
        fit.append(p)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    left, right = np.polyval(fit[0], yy), np.polyval(fit[1], yy)
    if cls is not None:
        hw = max(2.0, float(right[yg - 1, 0] - left[yg - 1, 0]) / 2.0)
        c = float(left[yg - 1, 0] + right[yg - 1, 0]) / 2.0
        offs = []                              # ствол HD сдвинут против коры классики - сдвиг по строкам над землёй
        for y in ys.astype(int):
            xs = np.flatnonzero(cls[y])
            if len(xs):
                offs.append(float(np.polyval(fit[0], y) + np.polyval(fit[1], y)) / 2.0 - (xs[0] + xs[-1]) / 2.0)
        off = int(round(float(np.median(offs)))) if offs else 0
        cls = np.roll(cls, off, axis=1)
        if off > 0:
            cls[:, :off] = False
        elif off < 0:
            cls[:, off:] = False
        for y in range(yg, h):
            xs = np.flatnonzero(cls[y])
            if not len(xs):
                left[y:], right[y:] = 1e6, -1e6
                break
            runs = np.split(xs, np.flatnonzero(np.diff(xs) > 1) + 1)
            best = max(runs, key=lambda r: min(r[-1], c + hw) - max(r[0], c - hw))
            if min(best[-1], c + hw) - max(best[0], c - hw) < 0:       # ствол оборвался
                left[y:], right[y:] = 1e6, -1e6
                break
            lo, hi = best[0] + hw, best[-1] - hw                         # шире ствола (корни) - центр ближе к прежнему
            c = float(np.clip(c, lo, hi)) if lo <= hi else float(best[0] + best[-1]) / 2.0
            left[y], right[y] = c - hw, c + hw
    out = np.clip(np.minimum(xx - left, right - xx) / 2.0 + 0.5, 0.0, 1.0)
    out[: max(0, yg - rows)] = 0.0
    return out * (1.0 - g)


def _trunk_rows(core, alpha, wide=1.4):
    """Ствол по строкам кадра z0: непрозрачный (альфа > 64) отрезок строки, в котором есть ядро коры, целиком - мох
    края ствола (у JUNGLE освещённая сторона, вне следа коры классики) тоже ствол. Отрезок шире wide медианной
    ширины - ствол с ветвями (ель) или с травой: не берётся."""
    runs = []
    for y in range(core.shape[0]):
        cx = np.flatnonzero(core[y])
        if not len(cx):
            continue
        xs = np.flatnonzero(alpha[y] > 64)
        for r in np.split(xs, np.flatnonzero(np.diff(xs) > 1) + 1):
            if len(r) and r[0] <= cx[-1] and r[-1] >= cx[0]:
                runs.append((y, r[0], r[-1]))
    out = np.zeros(core.shape, np.float32)
    if not runs:
        return out
    wmed = float(np.median([b - a + 1 for _, a, b in runs]))
    for y, a, b in runs:
        if b - a + 1 <= wide * wmed:
            out[y, a:b + 1] = 1.0
    return out


def bark_tone(world, S, frames, fs, floor_fs=()):
    """Кора к тону классики (как ствол FOREST 57 у v2.f57_details, но для любого семейства): модель красит кору
    по-своему - у JUNGLE замшелая серо-зелёная вместо розово-бурой, у FJS тёмная вместо малиновой (R-254: неверный
    основной тон материала - брак). Кора классики - не зелёное (g <= r+2) и не снег (светлое серое). Вес пикселя =
    доля коры среди непрозрачного классики рядом x гейт: цвет HD ближе к коре, чем к листве (средние по ядрам
    семейства, листва - BARK_LEAF_K центров k-means); в глубине коры классики (доля > 0.95) гейт не действует - там
    мох модели тоже кора (освещённый мох цветом не отличить от светлой листвы), - кроме ромба земли у кадров z0
    (floor_fs): трава HD там, где у классики корни, остаётся травой. Ствол по МЕСТУ, а не по цвету: ядро коры,
    раздутое на BARK_TRUNK_R, - кора целиком (мох края ствола цветом не отличить от листвы); у кадров z0 ещё ствол
    по строкам (_trunk_rows: непрозрачный отрезок строки с ядром, не шире 1.4 медианы) и ниже края земли - ствол,
    продолженный по коре классики (_trunk_down). Цель - МЕСТНЫЙ
    тон коры классики (окно BARK_LOCAL), а не одно среднее: светлый ствол и тёмные ягоды в кроне - разные цели.
    Сдвиг - разность местных средних, дожим до BARK_ITERS раз; цветность коры дополнительно сжимается к местному
    среднему на BARK_AB_SQUEEZE (зелёный мох освещённой стороны). Яркость фактуры HD и альфа не меняются."""
    wc, opq, labs, cb, cbn, bk = {}, {}, {}, {}, {}, {}
    for f in fs:
        c = np.asarray(tr.sprite(world, S, f).convert("RGBA"), np.float32)
        op = c[..., 3] > 0
        cl = _lab(c[..., :3])
        snow = (cl[..., 0] > BARK_SNOW_L) & (np.hypot(cl[..., 1], cl[..., 2]) < BARK_SNOW_C)
        bark = op & (c[..., 1] <= c[..., 0] + 2) & ~snow
        b4 = tr.rep4(bark).astype(np.float32)
        b = _blur(b4, BARK_SIGMA)
        o = _blur(tr.rep4(op), BARK_SIGMA)
        wc[f] = np.where(o > 1e-3, b / np.maximum(o, 1e-3), 0.0)
        bl = _blur(b4, BARK_LOCAL)
        cb[f] = _blur(tr.rep4(cl) * b4[..., None], BARK_LOCAL) / np.maximum(bl, 1e-3)[..., None]
        cbn[f] = bl
        bk[f] = b4 > 0.5
        v = np.asarray(frames[f], np.float32)
        opq[f] = v[..., 3] > 200
        labs[f] = _lab(v[..., :3])
    core_b = [labs[f][opq[f] & (wc[f] > 0.9)] for f in fs]
    core_l = [labs[f][opq[f] & (wc[f] < 0.1)] for f in fs]
    core_b = np.concatenate([x for x in core_b if len(x)]) if any(len(x) for x in core_b) else None
    core_l = np.concatenate([x for x in core_l if len(x)]) if any(len(x) for x in core_l) else None
    if core_b is None or len(core_b) < 50:
        return dict(skipped="ядра коры в HD нет")
    mb = core_b.mean(0)
    w = {}
    ml = None
    if core_l is not None and len(core_l) >= 50:       # листва - несколько центров: тёмная крона, светлая трава, земля
        cv2.setRNGSeed(0)
        k = min(BARK_LEAF_K, len(core_l))
        _, _, cen = cv2.kmeans(core_l.astype(np.float32), k, None,
                               (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.2), 3, cv2.KMEANS_PP_CENTERS)
        cen = cen[np.sqrt(((cen - mb) ** 2).sum(-1)) > 12.0]          # центр цвета коры (ствол за кроной) - не листва
        ml = cen if len(cen) else None
    for f in fs:
        db = ((labs[f] - mb) ** 2).sum(-1)
        if ml is not None:
            dl = np.min([((labs[f] - c) ** 2).sum(-1) for c in ml], axis=0)
            gate = dl / np.maximum(dl + db, 1e-3)
            gate = np.clip((gate - 0.5) * 3.0 + 0.5, 0.0, 1.0)
        else:
            gate = np.ones(labs[f].shape[:2], np.float32)
        deep = np.clip((wc[f] - 0.75) / 0.2, 0.0, 1.0)
        # ствол по месту: у ядра коры HD (BARK_TRUNK_R x4) и у коры классики - мох освещённой стороны тоже кора,
        # цветом его от светлой листвы не отличить
        core = ((gate > 0.5) & opq[f] & (wc[f] > 0.5)).astype(np.uint8)
        trunk = _blur(cv2.dilate(core, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * BARK_TRUNK_R + 1,) * 2))
                      .astype(np.float32), 1.5) * np.clip((wc[f] - 0.3) / 0.2, 0.0, 1.0)
        if f in floor_fs:                      # ромб земли: трава HD там, где у классики корни, - не кора,
            g = 1.0 - _ground[:deep.shape[0], :deep.shape[1]]      # кроме продолжения ствола вниз
            rows = _trunk_rows(core, np.asarray(frames[f])[..., 3])
            col = _trunk_down(((trunk > 0.5) | (rows > 0.5)) & (np.asarray(frames[f])[..., 3] > 64), g,
                              cls=bk[f])                                  # мох края полупрозрачный
            deep, trunk = deep * np.maximum(g, col), np.maximum(np.maximum(trunk, rows) * g,
                                                                col * np.clip(wc[f] / 0.2, 0.0, 1.0))
        if os.environ.get("BARK_DEBUG"):
            for k, a in (("gate", gate), ("core", core), ("trunk", trunk), ("cbn", cbn[f] > 0.05), ("opq", opq[f])):
                Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8)).save(
                    os.path.join(os.environ["BARK_DEBUG"], "%s_%d_%s.png" % (S, f, k)))
        gate = np.maximum(gate, deep)
        w[f] = (np.maximum(wc[f] * gate, trunk) * (np.asarray(frames[f])[..., 3] > 0) * (cbn[f] > 0.05)).astype(np.float32)

    def gap(cur):                              # взвешенная разность HD - классика по семейству
        num = sum(((cur[f] - cb[f]) * w[f][..., None]).reshape(-1, 3).sum(0) for f in fs)
        return num / max(float(sum(w[f].sum() for f in fs)), 1e-3)

    if os.environ.get("BARK_DEBUG"):
        for f in fs:
            Image.fromarray((w[f] * 255).astype(np.uint8)).save(os.path.join(os.environ["BARK_DEBUG"], "%s_%d_w.png" % (S, f)))
            Image.fromarray((np.clip(wc[f], 0, 1) * 255).astype(np.uint8)).save(
                os.path.join(os.environ["BARK_DEBUG"], "%s_%d_wc.png" % (S, f)))
    cur = {f: labs[f].copy() for f in fs}
    hist = [[round(float(x), 1) for x in gap(cur)]]
    for f in fs:                               # кора - один материал: чужой оттенок (мох) сжать к местному среднему,
        if not w[f].any():                     # яркость (фактура, тени) не трогать
            continue
        ww = _blur(w[f], BARK_LOCAL)
        hb = _blur(cur[f] * w[f][..., None], BARK_LOCAL) / np.maximum(ww, 1e-3)[..., None]
        cur[f][..., 1:] += (BARK_AB_SQUEEZE * w[f])[..., None] * (hb[..., 1:] - cur[f][..., 1:])
    for _ in range(BARK_ITERS):
        for f in fs:
            if not w[f].any():
                continue
            ww = _blur(w[f], BARK_LOCAL)
            hb = _blur(cur[f] * w[f][..., None], BARK_LOCAL) / np.maximum(ww, 1e-3)[..., None]
            cur[f] = cur[f] + w[f][..., None] * (cb[f] - hb)
        hist.append([round(float(x), 1) for x in gap(cur)])
        if float(np.linalg.norm(hist[-1])) < 0.5:
            break
    for f in fs:
        if not w[f].any():
            continue
        v = np.asarray(frames[f], np.float32).copy()
        m = w[f] > 0
        v[..., :3][m] = _rgb(cur[f])[m]
        frames[f] = Image.fromarray(np.clip(np.round(v), 0, 255).astype(np.uint8), "RGBA")
    deep = np.concatenate([labs[f][opq[f] & (wc[f] > 0.95) & (w[f] < 0.3)] for f in fs])
    return dict(hd_bark_lab=[round(float(x), 1) for x in mb], gap_iter=hist,
                leaf_centres=[[round(float(x), 1) for x in c] for c in ml] if ml is not None else None,
                deep_unshifted=dict(n=int(len(deep)), lab=[round(float(x), 1) for x in deep.mean(0)] if len(deep) else None),
                weighted_px=int(sum((w[f] > 0.5).sum() for f in fs)))


FLOOR_COVER_MIN = 0.35   # доля пола, которую классика кадра повторяет пиксель в пиксель
FLOOR_TOL = 24           # пиксель классики - земля, если от пиксела пола не дальше этого по каналу
LAWN_DY = 8              # газон модели в зоне дерева: светлее пола и классики на столько по Y
LUMA = np.array([0.299, 0.587, 0.114], np.float32)


def _floor_sets(world, S):
    out = [S]
    for d in world.terrains.values():
        ss = [str(x) for x in (d.get("mapDataSets") or [])]
        if S in ss:
            out += [x for x in ss if x not in out]
    return out


def floor_base(world, S, frames, z0):
    """Земля под деревом из установленного HD-пола (R-006). Классика кадра z0 рисует дерево на своей клетке травы
    или снега; модель рисует её отдельной плиткой с тёмной кромкой, и на поле деревья стоят островками (TG006, TG012,
    TG016, TG017, TG018 партии 1). Пол ищется среди записей пола (type 0) наборов тех же террейнов: классика кадра
    повторяет его пиксели на доле от FLOOR_COVER_MIN. В ромбе пола от ответа остаётся только дерево (классика не
    равна полу, с запасом 2 пикс x4), под ним - HD этого пола как есть."""
    out = {}
    for f in z0:
        a = np.asarray(tr.sprite(world, S, f)).astype(int)
        best = None
        for s2 in _floor_sets(world, S)[:40]:
            for r in world.records(s2):
                if r["type"] != 0 or (s2, r["frame"]) == (S, f):
                    continue
                o = world.sprite(s2, r["frame"], None)
                if o is None or o.size != (32, 40):
                    continue
                b = np.asarray(o).astype(int)
                fb = b[..., 3] > 0
                if fb.sum() < 100:
                    continue
                c = (fb & (a[..., 3] > 0) & (np.abs(a[..., :3] - b[..., :3]).max(-1) == 0)).sum() / fb.sum()
                if best is None or c > best[0]:
                    best = (c, s2, r["frame"], b)
        if best is None or best[0] < FLOOR_COVER_MIN:
            continue
        c, s2, f2, b = best
        p = os.path.join(tr.OLD, s2.upper() + ".PCK", "%d.png" % f2)
        if not os.path.exists(p):
            out[f] = dict(floor="%s:%d" % (s2, f2), cover=round(float(c), 3), skipped="нет HD пола")
            continue
        fb = b[..., 3] > 0
        ground = fb & (a[..., 3] > 0) & (np.abs(a[..., :3] - b[..., :3]).max(-1) <= FLOOR_TOL)
        tree = (a[..., 3] > 0) & ~ground
        t4 = cv2.dilate(tr.rep4(tree).astype(np.uint8), np.ones((5, 5), np.uint8))
        new = np.asarray(frames[f].convert("RGBA")).astype(np.float32)
        flo = np.asarray(Image.open(p).convert("RGBA")).astype(np.float32)
        # своя трава модели в зоне дерева: классика под стволом рисует тень, модель - светлый газон, и на поле под
        # каждым деревом светлый островок (TG006). Газон - зелёный пиксель ответа светлее HD-пола и светлее классики
        # того же места (классика в тоне HD-пола); освещённая листва, где классика тоже светлая, не трогается
        fb4 = tr.rep4(fb)
        yn, yf = new[..., :3] @ LUMA, flo[..., :3] @ LUMA
        yc = tr.rep4(a[..., :3].astype(np.float32) @ LUMA) * (yf[fb4].mean() / max(float((b[..., :3] @ LUMA)[fb].mean()), 1.0))
        g = new[..., 1]
        lawn = fb4 & (new[..., 3] > 0) & (g >= new[..., 0]) & (g >= new[..., 2]) & (yn > yf + LAWN_DY) & (yn > yc + LAWN_DY)
        t4 = t4.astype(np.float32) * (1 - cv2.dilate(lawn.astype(np.uint8), np.ones((3, 3), np.uint8)))
        w = cv2.GaussianBlur(t4, (0, 0), 1.2)[..., None]
        new[..., 3:] *= np.where(fb4[..., None], w, 1.0)
        ta = new[..., 3:] / 255.0
        fa = flo[..., 3:] / 255.0 * (1 - ta)
        oa = ta + fa
        rgb = (new[..., :3] * ta + flo[..., :3] * fa) / np.maximum(oa, 1e-6)
        frames[f] = Image.fromarray(np.clip(np.concatenate([rgb, oa * 255.0], -1) + 0.5, 0, 255).astype(np.uint8))
        out[f] = dict(floor="%s:%d" % (s2, f2), cover=round(float(c), 3), ground_px=int(ground.sum()),
                      tree_in_floor_px=int((tree & fb).sum()), lawn_px4=int(lawn.sum()))
    return out


def assemble_copy(args, fid, S, world, CL, cp):
    """Семейство - побайтная копия канона: кадр канона под своим номером (f - shift в наборе src), рендера нет.
    Кадр без побайтной копии классики или без кадра канона в раскладках стоит прежним HD и в asm/frames не пишется."""
    set_layouts(S, CL)
    od = os.path.join(args.out, "asm")
    os.makedirs(od, exist_ok=True)
    fs = sorted({e[0] for L in CL[S]["sigs"] for e in L["sig"]})
    olds = old_frames(S, fs)
    frames, copied, kept = {}, [], []
    fd = os.path.join(od, "frames", S + ".PCK")
    os.makedirs(fd, exist_ok=True)
    for f in fs:
        g = f - cp["shift"]
        p = os.path.join(cp["frames"], "%d.png" % g)
        same = np.array_equal(np.asarray(tr.sprite(world, S, f).convert("RGBA")),
                              np.asarray(tr.sprite(world, cp["src"], g).convert("RGBA")))
        if same and os.path.exists(p):
            frames[f] = Image.open(p).convert("RGBA")
            po.gen_hd.save_png(frames[f], os.path.join(fd, "%d.png" % f))
            copied.append(f)
        else:
            kept.append(f)
            frames[f] = olds[f] if f in olds else tr.sprite(world, S, f).convert("RGBA").resize((128, 160), Image.NEAREST)
    summary = dict(family=fid, set=S, layouts=len(CL[S]["sigs"]), frames=fs, copy_of=cp, copied=copied, kept=kept)
    summary["scan"] = scan(world, CL, S, frames)
    sig0 = CL[S]["sigs"][0]["sig"]
    whole = [("whole", [("classic", tr.assemble(world, S, sig0, None, 99)),
                        ("old HD", tr.assemble(world, S, sig0, olds, 99)),
                        ("T1 from frames", tr.assemble(world, S, sig0, frames, 99))])]
    title = "%s %s = %s (copy)" % (fid, S, cp["src"])
    sheets(world, CL, S, frames, olds, whole, od, title, fs)
    with open(os.path.join(od, "summary.json"), "w", encoding=ENC) as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1, default=v2._js)
    sc = summary["scan"]
    print("  %s %s: копий %d, прежних %s, раскладок %d (видов %d), открытых швов %d, срезов рамкой %d -> %s"
          % (fid, S, len(copied), kept, sc["layouts"], sc["views"], len(sc["open_seams"]), len(sc["frame_cuts"]), od),
          flush=True)
    return summary


def assemble_joint(args, fid, S, world, CL, parts):
    """Общая сборка модулей одного набора (ель: ствол 21/22 + крона 23-26) без рендера: кадры берутся из asm
    модулей как есть, проверяются во всех сочетаниях набора - швы ствол|крона, кадр 23 на месте 25, смешанная пара."""
    set_layouts(S, CL)
    od = os.path.join(args.out, "asm")
    fd = os.path.join(od, "frames", S + ".PCK")
    os.makedirs(fd, exist_ok=True)
    fs = sorted({e[0] for L in CL[S]["sigs"] for e in L["sig"]})
    frames, src = {}, {}
    for p in parts:
        pd = os.path.join(p, "asm", "frames", S + ".PCK")
        for f in fs:
            q = os.path.join(pd, "%d.png" % f)
            if os.path.exists(q):
                if f in frames:
                    raise SystemExit("%s: кадр %d в двух модулях (%s и %s)" % (fid, f, src[f], p))
                frames[f], src[f] = Image.open(q).convert("RGBA"), p
    miss = [f for f in fs if f not in frames]
    if miss:
        print("  %s: нет кадров %s - модули не собраны" % (fid, miss), flush=True)
        return None
    for f, im in frames.items():
        po.gen_hd.save_png(im, os.path.join(fd, "%d.png" % f))
    olds = old_frames(S, fs)
    summary = dict(family=fid, set=S, layouts=len(CL[S]["sigs"]), frames=fs,
                   parts={f: os.path.basename(p) for f, p in src.items()}, scan=scan(world, CL, S, frames))
    sig0 = CL[S]["sigs"][0]["sig"]
    whole = [("whole", [("classic", tr.assemble(world, S, sig0, None, 99)),
                        ("old HD", tr.assemble(world, S, sig0, olds, 99)),
                        ("T1 from frames", tr.assemble(world, S, sig0, frames, 99))])]
    sheets(world, CL, S, frames, olds, whole, od, "%s %s" % (fid, S), fs)
    with open(os.path.join(od, "summary.json"), "w", encoding=ENC) as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1, default=v2._js)
    print("  %s: раскладок %d, новых швов %d, срезов рамкой %d" % (fid, len(CL[S]["sigs"]),
          len(summary["scan"]["open_seams"]), len(summary["scan"]["frame_cuts"])), flush=True)
    return summary


def assemble_family(args, fid, S, world, CL, hints):
    set_layouts(S, CL)
    seed = args.seeds[0]
    fdir = args.out                                        # batchA/<fid>
    sd = os.path.join(fdir, "s%d" % seed)
    od = os.path.join(fdir, "asm")
    os.makedirs(od, exist_ok=True)
    fs = sorted({e[0] for L in CL[S]["sigs"] for e in L["sig"]})
    olds = old_frames(S, fs)
    stumps = {}
    for (S2, f) in list(tr.STUMPS):
        p = stump_cut(world, S2, f, sd, args)
        if p:
            stumps[f] = p
    summary = dict(family=fid, set=S, layouts=len(CL[S]["sigs"]), frames=fs, stumps=sorted(stumps))
    upper = [f for f in fs if f not in {e[0] for e in CL[S]["sigs"][0]["sig"] if e[4] == 0}]
    if fid == "TG035":
        import argparse
        if 58 in stumps:
            v2.STUMP_OWN[S] = stumps[58]
        # GEOM_FROM строится при импорте v2 из tr.DERIVED, а patch() кладёт туда набор семейства: у FJS альфа кадров
        # 42-58 своя (57: 455 px против FOREST), геометрия и маски коры - по своей классике, не по FOREST
        v2.GEOM_FROM.pop(S, None)
        a2 = argparse.Namespace(out=os.path.join(fdir, "v2"), v1=fdir, seeds=[seed], sets=[S], z1_composite=True,
                                release=[], dry=False, recolour=True, grow=args.grow, soft=args.soft, pad=args.pad,
                                tone=args.tone)
        v2.do_assemble(a2, world, CL, hints)
        fd = os.path.join(a2.out, "s%d" % seed, S, "comp", "frames", S + ".PCK")
        frames = {f: Image.open(os.path.join(fd, "%d.png" % f)).convert("RGBA") for f in fs}
        summary["v2_summary"] = os.path.join(a2.out, "summary_comp.json")
        frames[57], summary["f57_v1"] = f57_v1(args, world, CL, hints, S, seed)
        summary["z0_bushes"] = z0_bushes(world, S, frames)
        summary["top_recede"] = top_recede(world, S, frames, fs)
        summary["ground_limit"] = ground_limit(world, S, frames)
        summary["grid_heal"] = grid_heal(world, S, frames)
        fd = os.path.join(od, "frames", S + ".PCK")
        os.makedirs(fd, exist_ok=True)
        for f, im in frames.items():
            po.gen_hd.save_png(im, os.path.join(fd, "%d.png" % f))
        whole = None
    else:
        r = assemble_v1(args, fid, S, world, CL, hints, seed)
        if r is None:
            return None
        job, V, frames, fam, stats = r
        valpha = stats.pop("valpha")
        summary.update(stats)
        t = job.tree
        sig0 = CL[S]["sigs"][0]["sig"]
        summary["grid_heal"] = grid_heal(world, S, frames, valpha)
        fd = os.path.join(od, "frames", S + ".PCK")
        os.makedirs(fd, exist_ok=True)
        for f, im in frames.items():
            po.gen_hd.save_png(im, os.path.join(fd, "%d.png" % f))
        whole = [("whole", [("classic x4", job.whole.resize((t.W * 4, t.H * 4), Image.NEAREST)),
                            ("old HD (T1)", tr.assemble(world, S, sig0, olds, 99)),
                            ("MAIN (render)", V[t.top]),
                            ("T1 from frames", tr.assemble(world, S, sig0, frames, 99))]),
                 ("floors", [("view z<=%d" % z, V[z]) for z in range(t.top - 1, -1, -1)] +
                            [("T1 z<=%d" % z, tr.assemble(world, S, sig0, frames, z)) for z in range(t.top - 1, -1, -1)])]
        if t.top == 0:                                     # одноэтажный модуль: ряда этажей нет
            whole.pop()
    miss = [f for f in fs if f not in frames]
    if miss:
        raise SystemExit("%s: нет кадров %s - раскладки не собрать" % (fid, miss))
    summary["bark_tone"] = bark_tone(world, S, frames, fs,
                                     {e[0] for L in CL[S]["sigs"] for e in L["sig"] if e[4] == 0})
    summary["accent_limit"] = accent_limit(world, S, frames, upper)    # после тона коры: диск краснеет им
    summary["floor_base"] = floor_base(world, S, frames,
                                       sorted({e[0] for L in CL[S]["sigs"] for e in L["sig"] if e[4] == 0}))
    for f, im in frames.items():
        po.gen_hd.save_png(im, os.path.join(od, "frames", S + ".PCK", "%d.png" % f))
    if whole is not None:                                  # T1 из кадров - после сдвига коры
        whole[0][1][3] = ("T1 from frames", tr.assemble(world, S, sig0, frames, 99))
        if len(whole) > 1:
            whole[1] = ("floors", whole[1][1][:len(whole[1][1]) // 2] +
                        [("T1 z<=%d" % z, tr.assemble(world, S, sig0, frames, z))
                         for z in range(t.top - 1, -1, -1)])
    title = "%s %s s%d" % (fid, S, seed)
    summary["scan"] = scan(world, CL, S, frames)
    if whole is None:
        sig0 = CL[S]["sigs"][0]["sig"]
        whole = [("whole", [("classic", tr.assemble(world, S, sig0, None, 99)),
                            ("old HD", tr.assemble(world, S, sig0, olds, 99)),
                            ("T1 from frames", tr.assemble(world, S, sig0, frames, 99))])]
    sheets(world, CL, S, frames, olds, whole, od, title, fs)
    if stumps:
        prow = []
        for f, p in stumps.items():
            spr = tr.sprite(world, S, f)
            o = os.path.join(tr.OLD, S + ".PCK", "%d.png" % f)
            prow.append(("%s:%d" % (S, f), [("classic", spr.resize((128, 160), Image.NEAREST)),
                                            ("old", Image.open(o).convert("RGBA") if os.path.exists(o)
                                             else Image.new("RGBA", (128, 160))),
                                            ("new", Image.open(p).convert("RGBA"))]))
        tr.grid(prow, os.path.join(od, "stumps.png"), "%s stumps: classic | old | new" % title)
    with open(os.path.join(od, "summary.json"), "w", encoding=ENC) as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1, default=v2._js)
    sc = summary["scan"]
    print("  %s %s: кадров %d, раскладок %d (видов %d), открытых швов %d, срезов рамкой %d -> %s"
          % (fid, S, len(fs), sc["layouts"], sc["views"], len(sc["open_seams"]), len(sc["frame_cuts"]), od),
          flush=True)
    return summary
