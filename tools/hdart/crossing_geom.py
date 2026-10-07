"""Геометрия перекрёстка ROADS против классики (замечание специалиста 07.10, пп. 1-2): что держит сборка new
на чистых кадрах игры, а что нет. Без генерации, по готовым кадрам и дампам crossing_clean.

ends    - концы штрихов разметки и вершина V на shot.png ракурсов v3, v2, na: маска разметки классики (режим 0)
          и new в координатах клетки, положение концов вдоль штриха, ширина у концов, положение поперёк, IoU;
          лист ends_zoom.png - крупно классика | new | контуры (красный классика, голубой new, белый совпали).
corners - камень бордюра кадров 1-8: классика x4 (индексы 243-252) против владения kerb_owner у new;
          IoU, только классика, только new; положение полосы камня поперёк стороны в середине стороны.
edge    - непрозрачное за точным ромбом x4 в кадрах new (зубцы силуэта классики по сторонам +u, +v): тон
          против тела у края. Внутри карты их закрывает сосед, видны только на краю карты.

Пишет census/maps/pilot2/probe_crossing/_geom/{ends.json, ends_zoom.png, corners.json, corners.png, edge.json}.

    py -3.13 tools/hdart/crossing_geom.py [ends|corners|edge ...]
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crossing_build as cb         # noqa: E402
import crossing_pair_edge as pe     # noqa: E402
import pilot2_job_sheet as js       # noqa: E402
import sidewalk_probe as sp         # noqa: E402

OUT = cb.OUT / "_geom"
NEW = cb.OUT / "_mods" / "new" / "hd" / "hd" / "TERRAIN" / "ROADS.PCK"
FONT = ImageFont.truetype(cb.sp.js.FONT, 16)
CELL = float(np.hypot(16, 8))   # базовых пикселей на клетку вдоль u или v
LUMA = np.array([0.299, 0.587, 0.114], np.float32)
STONE = (243, 252)              # индексы камня бордюра в классике


# ---------------------------------------------------------------- концы штрихов и V

def strokes(fr_of):
    """Прогоны клеток разметки: кадр 10 - полоса по -u, идёт вдоль v; кадр 11 - по -v, вдоль u."""
    out = []
    for f, ax in ((10, "v"), (11, "u")):
        key = (lambda c: (c[0], c[1])) if ax == "v" else (lambda c: (c[1], c[0]))
        runs = []
        for c in sorted((c for c, fr in fr_of.items() if fr == f), key=key):
            fx, mv = key(c)
            if runs and runs[-1][0] == fx and runs[-1][2] == mv - 1:
                runs[-1][2] = mv
            else:
                runs.append([fx, mv, mv])
        out += [dict(frame=f, axis=ax, fixed=fx, t0=a, t1=b + 1) for fx, a, b in runs]
    return out


def mark_masks(V):
    """Разметка: светлее середины между медианой и p99.7 яркости дороги (кадры 9-13), только чистое."""
    cu, cv = np.floor(V["gu"]).astype(int), np.floor(V["gv"]).astype(int)
    road = np.zeros(V["gu"].shape, bool)
    for (x, y), fr in V["fr_of"].items():
        if 9 <= fr <= 13:
            road |= (cu == x) & (cv == y)
    road &= V["good"]
    M = {}
    for kd in ("classic", "new"):
        Y = V["im"][kd] @ LUMA
        r = Y[road]
        M[kd] = road & (Y > (np.median(r) + np.percentile(r, 99.7)) / 2)
    return M


def measure(V, M, s):
    a = (V["gu"] - s["fixed"]) if s["axis"] == "v" else (V["gv"] - s["fixed"])
    t = V["gv"] if s["axis"] == "v" else V["gu"]
    reg = (a > -0.12) & (a < 0.32) & (t > s["t0"] - 0.35) & (t < s["t1"] + 0.35)
    r = {}
    for kd in ("classic", "new"):
        m = M[kd] & reg
        if m.sum() < 20:
            return None
        tt, aa = t[m], a[m]
        r[kd] = dict(n=int(m.sum()), t_lo=float(np.percentile(tt, 0.3)), t_hi=float(np.percentile(tt, 99.7)),
                     a_lo=float(np.percentile(aa, 2)), a_hi=float(np.percentile(aa, 98)))
        for end, sel in (("lo", tt < r[kd]["t_lo"] + 0.1), ("hi", tt > r[kd]["t_hi"] - 0.1)):
            r[kd]["w_" + end] = float(np.percentile(aa[sel], 98) - np.percentile(aa[sel], 2)) if sel.sum() > 4 else None
    cm, nm = M["classic"] & reg, M["new"] & reg
    r["iou"] = float((cm & nm).sum() / max(1, (cm | nm).sum()))
    r["good_cover"] = float(V["good"][reg].mean())
    r["d_end_lo_px"] = (r["new"]["t_lo"] - r["classic"]["t_lo"]) * CELL
    r["d_end_hi_px"] = (r["new"]["t_hi"] - r["classic"]["t_hi"]) * CELL
    return r


def contour(m):
    e = m.copy()
    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        e &= np.roll(np.roll(m, dy, 0), dx, 1)
    return m & ~e


# узлы для листа: свободные концы обеих ориентаций (v3) и вершина V (na)
ZOOM_AT = [("v3", (55, 7), "кадр 10: верхний (свободный) конец, узел 55,7"),
           ("v3", (55, 8), "кадр 10: боковой (свободный) конец, узел 55,8"),
           ("v3", (42, 15), "кадр 11: верхний (свободный) конец, узел 42,15"),
           ("v3", (43, 15), "кадр 11: боковой (свободный) конец, узел 43,15"),
           ("na", (55, 12), "вершина V: кадр 10 (55,11) и кадр 11 (54,12), узел 55,12")]


def ends():
    res, cache = {}, {}
    for view in ("v3", "v2", "na"):
        V = pe.view_data(view)
        M = mark_masks(V)
        cache[view] = (V, M)
        res[view] = []
        for s in strokes(V["fr_of"]):
            m = measure(V, M, s)
            if m is None:
                continue
            res[view].append(dict(s, **m))
            print(view, "кадр %d %s=%d %d..%d" % (s["frame"], "x" if s["axis"] == "v" else "y", s["fixed"], s["t0"],
                                                 s["t1"] - 1),
                  "IoU %.3f; концы классика %.3f..%.3f new %.3f..%.3f (сдвиг %+.1f / %+.1f пикс базы);" % (
                      m["iou"], m["classic"]["t_lo"], m["classic"]["t_hi"], m["new"]["t_lo"], m["new"]["t_hi"],
                      m["d_end_lo_px"], m["d_end_hi_px"]),
                  "поперёк классика %.3f..%.3f new %.3f..%.3f" % (
                      m["classic"]["a_lo"], m["classic"]["a_hi"], m["new"]["a_lo"], m["new"]["a_hi"]))
    (OUT / "ends.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding=cb.ENC)
    HALF, Z = 12, 7
    rows = []
    for view, (gx, gy), lbl in ZOOM_AT:
        V, M = cache[view]
        k, cam = V["k"], V["cam"]
        X, Y = cb.grid_xy(gx, gy, k, cam)
        b = (int(X - HALF * k), int(Y - HALF * k * 0.6), int(X + HALF * k), int(Y + HALF * k * 0.6))
        ims = [np.clip(V["im"][kd][b[1]:b[3], b[0]:b[2]], 0, 255).astype(np.uint8) for kd in ("classic", "new")]
        ov = V["im"]["new"][b[1]:b[3], b[0]:b[2]].copy() * 0.55
        cc_, cn = contour(M["classic"]), contour(M["new"])
        ov[cc_[b[1]:b[3], b[0]:b[2]]] = (255, 40, 40)
        ov[cn[b[1]:b[3], b[0]:b[2]]] = (60, 230, 255)
        ov[(cc_ & cn)[b[1]:b[3], b[0]:b[2]]] = (255, 255, 255)
        ims.append(np.clip(ov, 0, 255).astype(np.uint8))
        tiles = [Image.fromarray(a).resize((a.shape[1] * Z, a.shape[0] * Z), Image.NEAREST) for a in ims]
        for t in tiles:
            d = ImageDraw.Draw(t)
            cx, cy = (X - b[0]) * Z, (Y - b[1]) * Z
            d.line((cx - 10, cy, cx + 10, cy), fill=(255, 255, 0))
            d.line((cx, cy - 10, cx, cy + 10), fill=(255, 255, 0))
        w, h = tiles[0].size
        row = Image.new("RGB", (3 * (w + 8), h + 26), (24, 24, 28))
        ImageDraw.Draw(row).text((4, 4), "%s (ракурс %s) - классика | new | контуры" % (lbl, view), font=FONT,
                                 fill=(255, 255, 255))
        for i, t in enumerate(tiles):
            row.paste(t, (i * (w + 8), 26))
        rows.append(row)
    out = Image.new("RGB", (rows[0].width, sum(r.height + 8 for r in rows) + 30), (24, 24, 28))
    ImageDraw.Draw(out).text((6, 6), "Разметка крупно: красный - контур классики, голубой - new, белый - совпали; "
                             "жёлтый крест - узел сетки", font=FONT, fill=(255, 255, 255))
    y = 30
    for r in rows:
        out.paste(r, (0, y))
        y += r.height + 8
    out.save(OUT / "ends_zoom.png")
    print(OUT / "ends_zoom.png", out.size)


# ---------------------------------------------------------------- углы и полоса камня

def corners():
    Z = 3
    us, vs = sp.frame_uv(4)
    u1, v1 = sp.frame_uv(1)
    uc, vc = us.mean(-1), vs.mean(-1)
    inside = (u1 >= 0) & (u1 < 1) & (v1 >= 0) & (v1 < 1)
    res, tiles = {}, []
    for f in range(1, 9):
        idx = js.classic_idx("ROADS", f)
        cl = (idx >= STONE[0]) & (idx <= STONE[1])
        sides, owner, _x, beyond = cb.kerb_owner(f, us, vs)
        na = np.asarray(Image.open(NEW / ("%d.png" % f)))[..., 3] > 127
        nw = (((owner >= 0) & ~beyond).mean(-1) > 0.5) & na
        both, oc, on = cl & nw, cl & ~nw, nw & ~cl
        r = dict(sides=[s for s, _ in sides], iou=round(float(both.sum() / max(1, (cl | nw).sum())), 3),
                 classic_only=int(oc.sum()), new_only=int(on.sum()), band={})
        # полоса камня поперёк стороны: расстояние от края клетки, середина стороны (без 1/8 у вершин)
        ins = (uc >= 0) & (uc < 1) & (vc >= 0) & (vc < 1)
        for s, _w in sides:
            E = {"+u": 1 - uc, "+v": 1 - vc, "-u": uc, "-v": vc}[s]
            along = {"+u": vc, "-u": vc, "+v": uc, "-v": uc}[s]
            mid = ins & (along > 0.125) & (along < 0.875) & (E < 0.5)
            r["band"][s] = {nm: [round(float(np.percentile(E[mid & m], 2)), 3),
                                 round(float(np.percentile(E[mid & m], 98)), 3),
                                 round(float(E[mid & m].mean()), 3)] for nm, m in (("classic", cl), ("new", nw))}
        res[f] = r
        print("ROADS %d %s: IoU %.3f, только классика %d, только new %d; полоса E (p2, p98, ср.): %s" % (
            f, " ".join(r["sides"]), r["iou"], r["classic_only"], r["new_only"], r["band"]))
        im = np.zeros(idx.shape + (3,), np.uint8) + np.array([40, 40, 46], np.uint8)
        im[inside] = (70, 70, 76)
        im[both] = (170, 170, 170)
        im[oc] = (235, 50, 50)
        im[on] = (60, 190, 255)
        t = Image.fromarray(im).resize((128 * Z, 160 * Z), Image.NEAREST)
        d = ImageDraw.Draw(t)
        d.line([(x * Z, y * Z) for x, y in [(64, 96), (128, 128), (64, 160), (0, 128), (64, 96)]], fill=(0, 255, 0))
        d.text((6, 6), "ROADS %d  стороны %s" % (f, " ".join(r["sides"])), font=FONT, fill=(255, 255, 255))
        d.text((6, 26), "IoU %.3f  только классика %d  только new %d" % (r["iou"], r["classic_only"], r["new_only"]),
               font=FONT, fill=(255, 255, 255))
        tiles.append(t)
    out = Image.new("RGB", (4 * (128 * Z + 8), 2 * (160 * Z + 8) + 40), (24, 24, 28))
    ImageDraw.Draw(out).text((8, 8), "Камень бордюра: серый - у обоих, красный - только классика x4, голубой - только "
                             "new; зелёный - ромб клетки", font=FONT, fill=(255, 255, 255))
    for i, t in enumerate(tiles):
        out.paste(t, ((i % 4) * (128 * Z + 8), 40 + (i // 4) * (160 * Z + 8)))
    out.save(OUT / "corners.png")
    (OUT / "corners.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding=cb.ENC)
    print(OUT / "corners.png")


# ---------------------------------------------------------------- зубцы за ромбом

def edge():
    yy, xx = np.mgrid[0:160, 0:128] + 0.5
    a, b = (xx - 64) / 64, (yy - 96) / 32
    u, v = (a + b) / 2, (b - a) / 2
    inside = (u >= 0) & (u < 1) & (v >= 0) & (v < 1)
    res = {}
    for f in range(14):
        im = np.asarray(Image.open(NEW / ("%d.png" % f)).convert("RGBA")).astype(np.float32)
        al = im[..., 3] > 0
        out = al & ~inside & (yy > 90)
        lum = im[..., :3] @ LUMA
        body = al & inside & ((u > 0.9) | (v > 0.9))
        res[f] = dict(outside_px=int(out.sum()), plus_u=int((out & (u >= 1)).sum()), plus_v=int((out & (v >= 1)).sum()),
                      y_outside=round(float(lum[out].mean()), 1) if out.any() else None,
                      y_body_edge=round(float(lum[body].mean()), 1))
        print("ROADS %2d: за ромбом %d пикс x4 (+u %d, +v %d), Y за ромбом %s, у края тела %.1f" % (
            f, res[f]["outside_px"], res[f]["plus_u"], res[f]["plus_v"], res[f]["y_outside"], res[f]["y_body_edge"]))
    (OUT / "edge.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding=cb.ENC)


def main():
    OUT.mkdir(exist_ok=True)
    what = sys.argv[1:] or ["ends", "corners", "edge"]
    for w in what:
        {"ends": ends, "corners": corners, "edge": edge}[w]()


if __name__ == "__main__":
    main()
