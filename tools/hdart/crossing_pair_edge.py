"""Парная проверка края бордюра у асфальта (замечание 07.10, п. 3): new против ctl_wedge - одна и та же процедурная
фактура (build.json различаются только меткой и control), отличие только выступ кадров бордюра в клин асфальта.

1. Пак: попиксельная разница кадров new и ctl_wedge (RGBA) - где именно контроль отличается.
2. Кадр игры (shot.png без пара, ракурсы na, v2, v3 - камера и свет одни): разница пикселей new против ctl_wedge по
   геометрии клетки (полоса асфальта у бордюра 0-1/16, 1/16-1/8, дальше, камень, прочее).
3. Профиль поперёк границы камень | асфальт: d - расстояние от линии края клетки (минус - камень, плюс - асфальт) в
   долях клетки, бины 1/64; медиана и среднее Y по всем сторонам одного направления, для classic, hd_now, new,
   ctl_wedge.
4. Две меры раздельно:
   камень в асфальте - по каждому отрезку края (16 вдоль) МЕДИАНА Y полосы 0-1/16 минус медиана той же клетки в
     полосе 1/8-1/4 (медиана не видит редкий крап щебня); худший отрезок и среднее по модулю;
   щебень - доля светлых точек (Y выше медианы полосы на 12) и размах p90-p50 в полосе 0-1/16 против полосы
     1/8-1/4: у одной фактуры они равны, светлый крап в полосе - зерно, а не камень.
Порог kerb_edge не меняется. Пишет pair_edge.json и pair_edge.png в census/maps/pilot2/probe_crossing/_pair_edge.

    py -3.13 tools/hdart/crossing_pair_edge.py
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, "E:/OpenXCom/tools/hdart")
import crossing_build as cb       # noqa: E402
import crossing_check as cc       # noqa: E402
import crossing_clean as ccl      # noqa: E402
import map_screen_check as msc    # noqa: E402

OUT = cb.OUT / "_pair_edge"
OUT.mkdir(exist_ok=True)
D = cb.OUT / "_dumps"
SAVES = dict(ccl.SAVES)
SAVES["v3"] = cb.OUT / "_game_ref" / "corner_noacid_v3.sav"
UNIT = dict(ccl.UNIT)
UNIT["v3"] = (55, 14)
KINDS = ("classic", "hd_now", "new", "ctl_wedge")
LUMA = cc.LUMA
NB = 32                        # бины d по 1/64 от -16/64 до +16/64


def cover_nofog(save, bt, cam, W, H):
    """cc.cover_masks без пара заморозки (в shot.png пара нет)."""
    m = np.zeros((H, W), bool)

    def box(x, y, z, l, t, r, b):
        px = x * 16 - y * 16 + cam[0]
        py = x * 8 + y * 8 - z * 24 + cam[1]
        m[max(0, py + t):max(0, min(H, py + b)), max(0, px + l):max(0, min(W, px + r))] = True
    st = msc.unit_status(save)
    us, _sel = msc.units(save)
    for uid, (x, y, z), _f in us:
        if x < 0 or st.get(uid, 0) in (6, 7) or z > cam[2]:
            continue
        for dx in (0, 1):
            for dy in (0, 1):
                box(x - dx, y - dy, z, -8, -32, 40, 44)
    for x, y, z in msc.floor_items(save):
        if z <= cam[2]:
            box(x, y, z, 0, -8, 32, 44)
    for z, y, x in zip(*np.nonzero((bt.smoke > 0) | (bt.fire > 0))):
        if z <= cam[2]:
            box(x, y, z, -4, -16, 36, 44)
    return m


def pack_diff():
    a = cb.OUT / "_mods" / "new" / "hd" / "hd" / "TERRAIN" / "ROADS.PCK"
    b = cb.OUT / "_mods" / "ctl_wedge" / "hd" / "hd" / "TERRAIN" / "ROADS.PCK"
    out = {}
    for p in sorted(a.glob("*.png")):
        x = np.asarray(Image.open(p).convert("RGBA")).astype(np.int16)
        y = np.asarray(Image.open(b / p.name).convert("RGBA")).astype(np.int16)
        d = np.abs(x - y).max(-1) > 0
        if d.any():
            ys, xs = np.nonzero(d)
            out[p.name] = dict(n=int(d.sum()), box=[int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())])
    return out


def view_data(view):
    tags = {k: "%s_%s" % (k, view) for k in KINDS}
    for t in tags.values():
        if not (D / t / "shot.png").exists():
            return None
    js = {k: json.loads((D / t / "dump.json").read_text(encoding=cb.ENC)) for k, t in tags.items()}
    cams = {(j["cameraOffsetX"], j["cameraOffsetY"], j["cameraOffsetZ"], j.get("globalShade")) for j in js.values()}
    if len(cams) != 1:
        raise SystemExit("ракурс %s: камера/свет разные %s" % (view, cams))
    bt, data, k, W, H, cam, img, owner = cc.owners(str(SAVES[view]), js["new"])
    im = {kd: np.asarray(Image.open(D / t / "shot.png").convert("RGB"))[:H * k, :W * k].astype(np.float32)
          for kd, t in tags.items()}
    t = owner - 1
    part = np.where(owner > 0, t % 4, -1)
    q = t // 4
    zc, r = np.divmod(q, bt.X * bt.Y)
    yc, xc = np.divmod(r, bt.X)
    covered = cover_nofog(str(SAVES[view]), bt, cam, W, H)
    obj = (owner > 0) & (part != 0)
    obj_d = obj.copy()
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            obj_d |= np.roll(np.roll(obj, dy, 0), dx, 1)
    rep = lambda a: np.repeat(np.repeat(a, k, 0), k, 1)
    good = ~rep(covered | obj_d)
    hide = np.zeros_like(good)
    for x0, y0, x1, y1 in ccl.HUD:
        hide[max(0, y0):max(0, y1), max(0, x0):max(0, x1)] = True
    X, Y = cb.grid_xy(UNIT[view][0] + 0.5, UNIT[view][1] + 0.5, k, cam)
    hide[max(0, int(Y - 44 * k)):int(Y + 10 * k), max(0, int(X - 18 * k)):int(X + 18 * k)] = True
    good &= ~hide[:good.shape[0], :good.shape[1]]
    # кадр ROADS клеток этажа 0
    fr_of = {}
    for x in range(bt.X):
        for y in range(bt.Y):
            cur = bt.part(0, y, x, 0)
            if cur is not None and bt.sets[cur[0]] == "ROADS":
                fr_of[(x, y)] = data.mcd("ROADS")[cur[1]]["frames"][0]
    Yi, Xi = np.mgrid[0:H * k, 0:W * k].astype(np.float32)
    sx, sy = (Xi + 0.5) / k - cam[0] - 16, (Yi + 0.5) / k - cam[1] - 24
    gu, gv = (sx / 16 + sy / 8) / 2, (sy / 8 - sx / 16) / 2
    own = np.repeat(np.repeat(np.where(owner > 0, xc * 1000 + yc, -1), k, 0), k, 1)
    opart = np.repeat(np.repeat(part, k, 0), k, 1)
    return dict(view=view, k=k, cam=cam, im=im, good=good, fr_of=fr_of, gu=gu, gv=gv, H=H, W=W, own=own, opart=opart)


def edges(V, road=(9,)):
    """Стороны бордюр | асфальт (у соседа кадр из road) на участке перекрёстка. Мера по отрезкам - только чистый
    асфальт 9 (у 10-13 в полосе разметка и решётка), классы изменённых пикселей - весь асфальт 9-13."""
    cx, cy, n = cb.WINDOW
    for (x, y), f in sorted(V["fr_of"].items()):
        if not (cx - 1 <= x <= cx + n and cy - 1 <= y <= cy + n):
            continue
        for s in cc.KERB_SIDES.get(f, {}):
            nx, ny = {"+u": (x + 1, y), "-u": (x - 1, y), "+v": (x, y + 1), "-v": (x, y - 1)}[s]
            if V["fr_of"].get((nx, ny)) in road:
                yield (x, y), f, s, (nx, ny)


def geom(V, kerb, s):
    x, y = kerb
    gu, gv = V["gu"], V["gv"]
    d = {"+u": gu - (x + 1), "-u": x - gu, "+v": gv - (y + 1), "-v": y - gv}[s]
    along = (gv - y) if s in ("+u", "-u") else (gu - x)
    return d, along


def analyse(V):
    res = dict(view=V["view"], camera=V["cam"])
    im = V["im"]
    Yk = {kd: a @ LUMA for kd, a in im.items()}
    diff = np.abs(im["new"] - im["ctl_wedge"]).max(-1) > 2
    valid = V["good"]
    # классы разницы по геометрии
    cls = np.full(diff.shape, "прочее", dtype=object)
    for kerb, f, s, road in edges(V, road=(9, 10, 11, 12, 13)):
        d, along = geom(V, kerb, s)
        inrow = (along >= -1 / 8) & (along < 1 + 1 / 8)
        cls[inrow & (d >= -0.4) & (d < 0) & (cls == "прочее")] = "камень бордюра"
        cls[inrow & (d >= 1 / 8) & (d < 0.5)] = "асфальт 1/8-1/2"
        cls[inrow & (d >= 1 / 16) & (d < 1 / 8)] = "асфальт 1/16-1/8"
        cls[inrow & (d >= 0) & (d < 1 / 16)] = "асфальт 0-1/16"
    names = ("асфальт 0-1/16", "асфальт 1/16-1/8", "асфальт 1/8-1/2", "камень бордюра", "прочее")
    res["changed_px"] = {c: int((diff & valid & (cls == c)).sum()) for c in names}
    res["class_px"] = {c: int((valid & (cls == c)).sum()) for c in names}
    res["changed_px_hidden"] = int((diff & ~valid).sum())
    # «прочее»: чей пиксель по классике (клетка и её кадр ROADS) - где лежит разница вне полос у бордюра
    oth = diff & valid & (cls == "прочее")
    by = defaultdict(int)
    oo, pp = V["own"][:oth.shape[0], :oth.shape[1]], V["opart"][:oth.shape[0], :oth.shape[1]]
    for o, p_ in zip(oo[oth], pp[oth]):
        if o < 0:
            by["нет владельца"] += 1
            continue
        f = V["fr_of"].get((int(o) // 1000, int(o) % 1000))
        by["ROADS %s" % f if f is not None and p_ == 0 else ("часть %d" % p_ if p_ else "пол не ROADS")] += 1
    res["other_by_owner_frame"] = dict(sorted(by.items(), key=lambda t: -t[1]))
    res["changed_max_dY"] = {c: round(float(np.abs(Yk["new"] - Yk["ctl_wedge"])[diff & valid & (cls == c)].max()), 1)
                             if (diff & valid & (cls == c)).any() else 0.0 for c in names}
    # профиль поперёк границы и меры по отрезкам
    prof = {kd: defaultdict(lambda: [[] for _ in range(NB)]) for kd in KINDS}
    seg = {kd: [] for kd in KINDS}
    speck = {kd: defaultdict(lambda: np.zeros(4)) for kd in KINDS}
    for kerb, f, s, road in edges(V):
        d, along = geom(V, kerb, s)
        box = valid & (along >= 0) & (along < 1) & (d > -0.25) & (d < 0.25)
        if box.sum() < 400:
            continue
        b = np.floor(d[box] * 64).astype(int) + 16
        for kd in KINDS:
            yv = Yk[kd][box]
            for i in range(NB):
                prof[kd][s][i].append(yv[b == i])
        for kd in KINDS:
            far = valid & (d >= 1 / 8) & (d < 1 / 4) & (along >= 0) & (along < 1)
            if far.sum() < 100:
                continue
            ref = float(np.median(Yk[kd][far]))
            strip = valid & (d >= 0) & (d < 1 / 16) & (along >= 0) & (along < 1)
            bb = np.clip((along[strip] * 16).astype(int), 0, 15)
            ys = Yk[kd][strip]
            for i in range(16):
                v = ys[bb == i]
                if len(v) >= 8:
                    seg[kd].append(dict(kerb=list(kerb), side=s, bin=i, n=int(len(v)),
                                        dmed=float(np.median(v) - ref), dmean=float(v.mean() - ref)))
            for nm, m in (("strip", strip), ("far", far)):
                v = Yk[kd][m]
                med = np.median(v)
                speck[kd][s] += np.array([0, 0, 0, 0])
                speck[kd][(s, nm)] += np.array([len(v), float((v > med + 12).sum()),
                                                float(np.percentile(v, 90) - med) * len(v), 1])
    res["profile"] = {}
    for kd in KINDS:
        res["profile"][kd] = {}
        for s, bins in prof[kd].items():
            res["profile"][kd][s] = [
                (round(float(np.median(np.concatenate(v))), 1) if sum(len(a) for a in v) else None,
                 round(float(np.concatenate(v).mean()), 1) if sum(len(a) for a in v) else None,
                 int(sum(len(a) for a in v))) for v in bins]
    res["stone_in_asphalt"] = {}
    for kd in KINDS:
        if not seg[kd]:
            continue
        w = max(seg[kd], key=lambda r: abs(r["dmed"]))
        res["stone_in_asphalt"][kd] = dict(
            worst_dmed=round(w["dmed"], 2), worst_at=[w["kerb"], w["side"], w["bin"]],
            mean_abs_dmed=round(float(np.mean([abs(r["dmed"]) for r in seg[kd]])), 2),
            worst_dmean=round(max(abs(r["dmean"]) for r in seg[kd]), 2), segments=len(seg[kd]),
            dark_steps_lt_m4=sum(r["dmed"] < -4 for r in seg[kd]), dark_steps_lt_m6=sum(r["dmed"] < -6 for r in seg[kd]),
            bright_gt_4=sum(r["dmed"] > 4 for r in seg[kd]))
    # парно: тот же отрезок, та же фактура - разность new минус ctl_wedge и есть действие выступа
    key = lambda r: (tuple(r["kerb"]), r["side"], r["bin"])
    sc = {key(r): r for r in seg["ctl_wedge"]}
    pairs = [(r, sc[key(r)]) for r in seg["new"] if key(r) in sc]
    dd = np.array([a["dmed"] - b["dmed"] for a, b in pairs])
    w = int(np.argmax(np.abs(dd))) if len(dd) else 0
    res["paired_new_minus_ctl"] = dict(
        segments=len(dd), mean=round(float(dd.mean()), 2), median=round(float(np.median(dd)), 2),
        share_new_brighter=round(float((dd > 0.5).mean()), 3), share_equal=round(float((np.abs(dd) <= 0.5).mean()), 3),
        max_abs=round(float(np.abs(dd).max()), 2), max_at=[list(pairs[w][0]["kerb"]), pairs[w][0]["side"], pairs[w][0]["bin"]],
        by_side={s: round(float(np.mean([a["dmed"] - b["dmed"] for a, b in pairs if a["side"] == s])), 2)
                 for s in sorted({a["side"] for a, _ in pairs})}) if len(dd) else {}
    res["new_worst_detail"] = sorted(seg["new"], key=lambda r: -abs(r["dmed"]))[:5]
    res["grain"] = {}
    for kd in KINDS:
        out = {}
        for nm in ("strip", "far"):
            tot = sum((v for kk, v in speck[kd].items() if isinstance(kk, tuple) and kk[1] == nm), np.zeros(4))
            if tot[0]:
                out[nm] = dict(bright_share=round(tot[1] / tot[0], 4), p90_minus_p50=round(tot[2] / tot[0], 2))
        res["grain"][kd] = out
    return res, diff


def plot(results, path, crops):
    Wd, h = 1800, 240
    sides = ["+u", "+v", "-u", "-v"]
    col = {"classic": (200, 200, 200), "hd_now": (255, 170, 60), "new": (60, 220, 255), "ctl_wedge": (255, 60, 160)}
    rows = len(results) * len(sides)
    img = Image.new("RGB", (Wd, 110 + rows * (h + 30) + sum(c.height + 40 for c in crops)), (24, 24, 28))
    dr = ImageDraw.Draw(img)
    font = ImageFont.truetype(cb.sp.js.FONT_B, 20)
    fs = ImageFont.truetype(cb.sp.js.FONT, 15)
    dr.text((10, 8), "Профиль Y поперёк границы камень | асфальт: медиана по всем сторонам одного направления, "
            "бины 1/64 клетки; слева от средней черты камень бордюра, справа асфальт; тонкие черты - 1/16 и 1/8",
            fill=(255, 255, 255), font=font)
    lx = 10
    for kd, nm in (("classic", "классика"), ("hd_now", "HD установки"), ("ctl_wedge", "контроль wedge (толстая)"),
                   ("new", "new (тонкая, поверх)")):
        dr.line((lx, 52, lx + 40, 52), fill=col[kd], width=5 if kd == "ctl_wedge" else 2)
        dr.text((lx + 48, 42), nm, fill=(230, 230, 230), font=font)
        lx += 70 + int(dr.textlength(nm, font=font))
    dr.text((10, 72), "Фактура асфальта и камня у new и контроля одна (тот же seed); отличается только выступ кадров "
            "бордюра за ромбом. Шкала Y 0..80.", fill=(200, 200, 200), font=fs)
    y0 = 110
    for r in results:
        for s in sides:
            dr.text((10, y0), "ракурс %s, сторона %s" % (r["view"], s), fill=(220, 220, 220), font=fs)
            x0, top = 60, y0 + 22
            dr.rectangle((x0, top, x0 + 1600, top + h), outline=(80, 80, 80))
            for yv in (0, 20, 40, 60, 80):
                yy = top + h - yv / 80.0 * h
                dr.line((x0 - 6, yy, x0, yy), fill=(150, 150, 150))
                dr.text((x0 - 40, yy - 8), str(yv), fill=(150, 150, 150), font=fs)
            xz = x0 + 800
            dr.line((xz, top, xz, top + h), fill=(140, 140, 140))
            for t in (-1 / 8, -1 / 16, 1 / 16, 1 / 8):
                dr.line((xz + t * 64 * 50, top, xz + t * 64 * 50, top + h), fill=(70, 70, 70))
            for kd in ("classic", "hd_now", "ctl_wedge", "new"):
                p = r["profile"].get(kd, {}).get(s)
                if not p:
                    continue
                pts = [(x0 + (i + 0.5) * 50, top + h - (v[0] / 80.0) * h) for i, v in enumerate(p) if v[0] is not None]
                if len(pts) > 1:
                    dr.line(pts, fill=col[kd], width=6 if kd == "ctl_wedge" else 2)
            y0 += h + 30
    for c in crops:
        img.paste(c, (10, y0))
        y0 += c.height + 40
    img.save(path)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    res = {"pack_diff": pack_diff()}
    print("разница пака new против ctl_wedge (RGBA):")
    for n, v in res["pack_diff"].items():
        print("  ", n, v)
    results, crops = [], []
    for view in ("na", "v2", "v3"):
        V = view_data(view)
        if V is None:
            print("ракурс", view, "- нет всех кадров")
            continue
        r, diff = analyse(V)
        results.append(r)
        print("ракурс", view, "изменённые пиксели:", r["changed_px"], "скрыто:", r["changed_px_hidden"])
        print("   камень в асфальте:", r["stone_in_asphalt"])
        print("   щебень:", r["grain"])
        print("   всего в классе:", r["class_px"], "макс |dY| изменённых:", r["changed_max_dY"])
        print("   парно new-ctl по отрезкам:", r["paired_new_minus_ctl"])
        print("   прочее по владельцу:", r["other_by_owner_frame"])
        print("   худшие отрезки new:", [(x["kerb"], x["side"], x["bin"], round(x["dmed"], 1)) for x in r["new_worst_detail"]])
        # вырезы: где разница
        vis = V["im"]["new"].copy()
        vis[diff] = (255, 0, 255)
        k = V["k"]
        fs = ImageFont.truetype(cb.sp.js.FONT, 15)
        cand = []
        for gx, gy in ((52, 12), (58, 12), (52, 18), (55, 11), (51, 15), (58, 15), (54, 18), (51, 11)):
            X, Y = cb.grid_xy(gx, gy, k, V["cam"])
            b = (int(X - 96), int(Y - 48), int(X + 96), int(Y + 48))
            if b[0] < 0 or b[1] < 0 or b[3] > 855 or b[2] > V["W"] * k:
                continue
            n = int((diff & V["good"])[b[1]:b[3], b[0]:b[2]].sum())
            cand.append((n, gx, gy, b))
        for n, gx, gy, b in sorted(cand, reverse=True)[:2]:
            trip = [Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).crop(b).resize((576, 288), Image.NEAREST)
                    for a in (V["im"]["new"], V["im"]["ctl_wedge"], vis)]
            row = Image.new("RGB", (3 * 586, 312), (24, 24, 28))
            ImageDraw.Draw(row).text((0, 0), "ракурс %s, у клетки %s,%s, x3: new | контроль wedge | new с изменёнными "
                                     "пикселями пурпуром (%d в вырезе)" % (view, gx, gy, n), fill=(255, 255, 255), font=fs)
            for i, t in enumerate(trip):
                row.paste(t, (i * 586, 22))
            crops.append(row)
    res["views"] = results
    (OUT / "pair_edge.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding=cb.ENC)
    plot(results, OUT / "pair_edge.png", crops)
    print("->", OUT)


if __name__ == "__main__":
    main()
