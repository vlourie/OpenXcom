#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RELATION_DISCOVERY_V1 - диагностика родства кадров: почему поиск семейств пару не связал и чем её
связать. Только чтение данных, без видеокарты; obj_families.py и правила ROUTING_RULES_V4 не меняет.

Шесть проверок пары (порядок специалиста):
  1. геометрия - IoU силуэта, прямо и зеркально;
  2. топология краёв - границы цветовых областей внутри общего силуэта (не яркость: перекраска по
     палитре сохраняет границы, а порядок яркости может перемешать);
  3. раскладка - связные части силуэта и области одного цвета;
  4. перенос палитры - доля пикселей, где цвет B есть функция цвета A (и обратно), согласие порядка
     яркости, где лежат необъяснённые пиксели (одно пятно или россыпь);
  5. MCD - физика и воксели записи кадра;
  6. соседство - те же номера во всём наборе (одна функция палитры на весь набор), записи MCD набора,
     соседи кадра на картах (кто стоит рядом в каждом месте).

Метка - только КАНДИДАТ с уровнем доказательства, не маршрут: «сходство высокое -> родство» не
делается, VERIFIED ставит человек.

    py -3.13 tools/hdart/relation_probe.py pair JUNGLE:8 BLACKJUNGLE:8
    py -3.13 tools/hdart/relation_probe.py sets JUNGLE BLACKJUNGLE
    py -3.13 tools/hdart/relation_probe.py neigh C_EXT_XCOM:36
    py -3.13 tools/hdart/relation_probe.py scan --out <папка>      (все строки очереди: пропущенные перекраски)
    py -3.13 tools/hdart/relation_probe.py v1 --out art/objects/generation/probes/relation-discovery-v1
"""
import argparse
import json
import os
import sys
from collections import Counter, defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import obj_families as of   # noqa: E402

ENC = "utf-8-sig"
ITEMS = "art/objects/discovery/items.json"
FAMILIES = "art/objects/families/families.json"
SET_TERRAINS = ".index/mod/Piratez/set_terrains.tsv"

# пороги кандидата - заданы на разборе V1 (не слепо), до холдаута замораживаются отдельно
GEO = 0.98          # силуэт тот же
FUNC = 0.98         # цвет B - функция цвета A и обратно: перекраска один к одному
STATE_LO = 0.60     # объяснено перекраской хотя бы столько, остальное - местная правка
SET_FUNC = 0.95     # одна функция палитры на весь набор
SET_SHARE = 0.80    # и столько непустых общих кадров повторяют силуэт


class Ctx:
    def __init__(self):
        import map_mockup as mm
        import obj_struct as os_
        self.mm = mm
        self.world = mm.World()
        self.st = os_.Struct(self.world)
        self.os_ = os_
        self._sets = None

    def rgba(self, key):
        s, fr = of.split(key)
        im = self.world.sprite(s.lower(), fr, None)
        return None if im is None else np.asarray(im.convert("RGBA"))

    def count(self, s):
        sh = self.world.sheet(s.lower())
        return sh.lay["count"] if sh is not None else 0

    def terrains(self, s):
        if self._sets is None:
            self._sets = {}
            if os.path.exists(SET_TERRAINS):
                with open(SET_TERRAINS, encoding=ENC) as f:
                    for line in f:
                        p = line.rstrip("\n").split("\t")
                        if len(p) >= 2:
                            self._sets[p[0].upper()] = p[1]
        return self._sets.get(s.upper(), "")


# ---------- пиксели ----------

def codes(a):
    m = a[..., 3] > 0
    c = (a[..., 0].astype(np.int64) << 16) | (a[..., 1].astype(np.int64) << 8) | a[..., 2].astype(np.int64)
    return m, c


def lum_of(code):
    return 0.299 * ((code >> 16) & 255) + 0.587 * ((code >> 8) & 255) + 0.114 * (code & 255)


def func_map(ca, cb):
    """Лучшая функция цвет A -> цвет B: (доля объяснённых, {a: b}, число цветов A, B)."""
    if not len(ca):
        return 0.0, {}, 0, 0
    pair = Counter(zip(ca.tolist(), cb.tolist()))
    best, mp = {}, {}
    for (x, y), n in pair.items():
        if n > best.get(x, 0):
            best[x], mp[x] = n, y
    return sum(best.values()) / len(ca), mp, len(set(ca.tolist())), len(set(cb.tolist()))


def components(m):
    """Размеры связных частей маски (4-связность), по убыванию."""
    seen = np.zeros_like(m)
    h, w = m.shape
    out = []
    for y0, x0 in zip(*np.nonzero(m)):
        if seen[y0, x0]:
            continue
        st, n = [(y0, x0)], 0
        seen[y0, x0] = True
        while st:
            y, x = st.pop()
            n += 1
            for yy, xx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= yy < h and 0 <= xx < w and m[yy, xx] and not seen[yy, xx]:
                    seen[yy, xx] = True
                    st.append((yy, xx))
        out.append(n)
    return sorted(out, reverse=True)


def regions(m, c):
    """Число областей одного цвета (4-связность) внутри маски."""
    seen = np.zeros_like(m)
    h, w = m.shape
    n = 0
    for y0, x0 in zip(*np.nonzero(m)):
        if seen[y0, x0]:
            continue
        n += 1
        st = [(y0, x0)]
        seen[y0, x0] = True
        while st:
            y, x = st.pop()
            for yy, xx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= yy < h and 0 <= xx < w and m[yy, xx] and not seen[yy, xx] and c[yy, xx] == c[y, x]:
                    seen[yy, xx] = True
                    st.append((yy, xx))
    return n


def borders(m, c):
    """Пары соседей внутри маски: (горизонтальные, вертикальные) - True там, где цвет меняется."""
    hm = m[:, :-1] & m[:, 1:]
    vm = m[:-1, :] & m[1:, :]
    return hm, vm, c[:, :-1] != c[:, 1:], c[:-1, :] != c[1:, :]


def topology(m, ca, cb):
    hm, vm, ha, va = borders(m, ca)
    _, _, hb, vb = borders(m, cb)
    da = np.concatenate([ha[hm], va[vm]])
    db = np.concatenate([hb[hm], vb[vm]])
    if not len(da):
        return 0.0, 0.0
    agree = float((da == db).mean())
    u = (da | db).sum()
    return agree, float((da & db).sum() / u) if u else 1.0


def concordance(mp, ca):
    """Доля пар цветов A (по пикселям), у которых порядок яркости после переноса тот же."""
    cnt = Counter(ca.tolist())
    cols = list(cnt)
    if len(cols) < 2:
        return 1.0
    la = {x: lum_of(x) for x in cols}
    lb = {x: lum_of(mp[x]) for x in cols}
    good = tot = 0.0
    for i, x in enumerate(cols):
        for y in cols[i + 1:]:
            if la[x] == la[y]:
                continue
            w = cnt[x] * cnt[y]
            tot += w
            good += w * ((la[x] - la[y]) * (lb[x] - lb[y]) > 0)
    return good / tot if tot else 1.0


def pair(ctx, ka, kb):
    A, B = ctx.rgba(ka), ctx.rgba(kb)
    if A is None or B is None:
        return {"a": ka, "b": kb, "error": "нет кадра"}
    ma, ca = codes(A)
    mb, cb = codes(B)
    u = (ma | mb).sum()
    iou = float((ma & mb).sum() / u) if u else 0.0
    iou_flip = float((ma & mb[:, ::-1]).sum() / max(1, (ma | mb[:, ::-1]).sum()))
    m = ma & mb
    f_ab, mp, na, nb = func_map(ca[m], cb[m])
    f_ba, _mp2, _, _ = func_map(cb[m], ca[m])
    agree, biou = topology(m, ca, cb)
    # необъяснённое: общий силуэт, где цвет B не тот, что даёт функция, плюс разница силуэтов
    bad = np.zeros_like(m)
    if mp:
        mapped = np.vectorize(lambda x: mp.get(x, -1))(ca)
        bad = m & (mapped != cb)
    bad |= ma ^ mb
    comp = components(bad)
    nbad = int(bad.sum())
    explained = 1.0 - nbad / max(1, int((ma | mb).sum()))
    rel =of.relation(of_feats(A), of_feats(B))
    ia, ib = ctx.st.info(*of.split(ka)), ctx.st.info(*of.split(kb))
    phys_diff = []
    vox_same = None
    if ia.get("rec") and ib.get("rec"):
        phys_diff = sorted(k for k in ia["phys"] if ia["phys"][k] != ib["phys"].get(k))
        vox_same = bool((ia["vox"] == ib["vox"]).all())
    return {
        "a": ka, "b": kb,
        "1_geometry": {"iou": round(iou, 3), "iou_flip": round(iou_flip, 3), "area": [int(ma.sum()), int(mb.sum())]},
        "2_topology": {"border_agree": round(agree, 3), "border_iou": round(biou, 3)},
        "3_layout": {"parts": [len(components(ma)), len(components(mb))],
                     "color_regions": [regions(ma, ca), regions(mb, cb)]},
        "4_palette": {"f_ab": round(f_ab, 3), "f_ba": round(f_ba, 3), "colors": [na, nb],
                      "lum_order_kept": round(concordance(mp, ca[m]), 3),
                      "explained": round(explained, 3), "unexplained_px": nbad,
                      "unexplained_parts": len(comp), "largest_part_share": round(comp[0] / nbad, 3) if nbad else 0.0},
        "5_mcd": {"rec": [bool(ia.get("rec")), bool(ib.get("rec"))], "tile_type": [ia.get("tile_type"), ib.get("tile_type")],
                  "phys_diff": phys_diff, "vox_same": vox_same},
        "obj_families": {"kind": rel[0], "iou": round(rel[1], 3), "corr": round(rel[2], 3), "edge": round(rel[3], 3),
                         "thresholds": {"IOU": of.IOU, "CORR": of.CORR, "EDGE": of.EDGE}},
    }


def of_feats(a):
    from PIL import Image
    return of.feats(Image.fromarray(a, "RGBA"))


# ---------- набор и карты ----------

def sets(ctx, sa, sb):
    na, nb = ctx.count(sa), ctx.count(sb)
    n = min(na, nb)
    glob = Counter()
    per = []
    for i in range(n):
        A, B = ctx.rgba("%s:%d" % (sa, i)), ctx.rgba("%s:%d" % (sb, i))
        if A is None or B is None:
            continue
        ma, ca = codes(A)
        mb, cb = codes(B)
        if not ma.any() and not mb.any():
            continue
        u = (ma | mb).sum()
        iou = float((ma & mb).sum() / u)
        m = ma & mb
        f, _mp, _, _ = func_map(ca[m], cb[m])
        f2 = func_map(cb[m], ca[m])[0]
        glob.update(zip(ca[m].tolist(), cb[m].tolist()))
        per.append((i, round(iou, 3), round(f, 3), round(f2, 3)))
    best = defaultdict(int)
    for (x, _y), k in glob.items():
        best[x] = max(best[x], k)
    tot = sum(glob.values())
    g = sum(best.values()) / tot if tot else 0.0
    same_geo = [p for p in per if p[1] >= GEO]
    recs_a, recs_b = ctx.st.records(sa), ctx.st.records(sb)
    k = min(len(recs_a), len(recs_b))
    rec_same = sum(1 for i in range(k) if recs_a[i][8:] == recs_b[i][8:])
    # кадр B выводится из кадра A (цвет B - функция цвета A); один к одному - отдельно: тёмная
    # перекраска сводит несколько оттенков в один (BLACKJUNGLE), и это всё равно перекраска
    strict = [p for p in same_geo if p[2] >= FUNC]
    bij = [p for p in strict if p[3] >= FUNC]
    return {"a": sa, "b": sb, "frames": [na, nb], "compared": len(per),
            "same_geometry": len(same_geo), "share_same_geometry": round(len(same_geo) / max(1, len(per)), 3),
            "strict_recolor_frames": len(strict), "share_strict": round(len(strict) / max(1, len(per)), 3),
            "one_to_one_frames": len(bij),
            "not_strict": [p for p in per if p[1] < GEO or p[2] < FUNC][:40],
            "global_f_ab": round(g, 3),
            "per_frame_f_on_same_geometry": sorted(p[2] for p in same_geo),
            "mcd_records": [len(recs_a), len(recs_b)], "mcd_same_except_frames": rec_same,
            "terrains": [ctx.terrains(sa), ctx.terrains(sb)],
            "frames_detail": per}


def neigh(ctx, key, top=12):
    """Соседи кадра на картах: в каждом месте кадра - кто стоит в клетках вокруг (и в той же клетке)."""
    import pck_census as pc
    s0, f0 = of.split(key)
    s0 = s0.upper()
    w = ctx.world
    places = 0
    near = Counter()
    blocks = []
    for t in sorted(w.terrains):
        sets_t = w.sets_of(t)
        if s0 not in [x.upper() for x in sets_t]:
            continue
        sizes = {s: len(w.records(s)) for s in sets_t}
        for b in w.blocks_of(t):
            try:
                _sx, _sy, _sz, cells = ctx.mm.read_block(w, b)
            except (Exception, SystemExit):           # noqa: BLE001
                continue
            grid = {}
            for pos, cell in cells.items():
                ks = []
                for layer, v in enumerate(cell):
                    if not v:
                        continue
                    s, rec = pc.resolve(v, sets_t, sizes)
                    if s is None:
                        continue
                    ks.append((layer, "%s:%d" % (s.upper(), w.records(s)[rec]["frame"])))
                grid[pos] = ks
            here = [p for p, ks in grid.items() if any(k == "%s:%d" % (s0, f0) for _l, k in ks)]
            if here:
                blocks.append("%s/%s:%d" % (t, b, len(here)))
            for (x, y, z) in here:
                places += 1
                seen = set()
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        for dz in (-1, 0, 1):
                            for layer, k in grid.get((x + dx, y + dy, z + dz), []):
                                if (dx, dy, dz) == (0, 0, 0) and k == "%s:%d" % (s0, f0):
                                    continue
                                seen.add(((dx, dy, dz), layer, k))
                near.update(seen)
    return {"key": key, "places": places, "blocks": blocks[:20],
            "neighbours": [{"offset": list(o), "layer": l, "key": k, "n": n, "share": round(n / max(1, places), 3)}
                           for (o, l, k), n in near.most_common(top)]}


# ---------- метка-кандидат ----------

def candidate(p, s=None):
    """Кандидат родства и уровень доказательства (NONE | CANDIDATE | STRONG); VERIFIED - только человек."""
    if "error" in p:
        return "NONE", "NONE", [p["error"]]
    g, pal, mcd = p["1_geometry"], p["4_palette"], p["5_mcd"]
    why = []
    # набор-двойник: тот же номер кадра, и набор целиком - точная перекраска кадр в кадр
    twin = s is not None and s["share_strict"] >= SET_SHARE
    if s is not None:
        why.append("набор того же номера: точных перекрасок %d/%d, одна функция палитры %.3f" % (
            s["strict_recolor_frames"], s["compared"], s["global_f_ab"]))
    mcd_same = mcd["vox_same"] and not mcd["phys_diff"]
    mcd_txt = "MCD %s" % ("тот же" if mcd_same else "другой: %s, воксели %s" % (
        ",".join(mcd["phys_diff"]) or "-", "те же" if mcd["vox_same"] else "другие"))
    if g["iou"] >= GEO and pal["f_ab"] >= FUNC and pal["f_ba"] >= FUNC:
        why.insert(0, "силуэт %.3f, цвет - функция в обе стороны %.3f/%.3f" % (g["iou"], pal["f_ab"], pal["f_ba"]))
        why.append(mcd_txt)
        return "RECOLOR_OF", "STRONG" if (twin and mcd_same) else "CANDIDATE", why
    if twin and g["iou"] >= GEO:
        # пара сама по себе не доказывает ничего (контроли V1: 8 из 10 чужих пар объяснены на 0.67-0.88);
        # довод - что весь набор перекраска, а этот кадр от неё отступил
        why.insert(0, "силуэт %.3f, перекраской набора объяснено %.3f, отступ - %d пикс. в %d частях" % (
            g["iou"], pal["explained"], pal["unexplained_px"], pal["unexplained_parts"]))
        why.append(mcd_txt)
        return "RECOLOR_WITH_LOCAL_EDIT", "CANDIDATE", why
    why.insert(0, "силуэт %.3f, объяснено %.3f - без набора-двойника это не довод" % (g["iou"], pal["explained"]))
    return "NONE", "NONE", why


# ---------- скан очереди ----------

def scan(ctx, out, min_area=20):
    with open(ITEMS, encoding=ENC) as f:
        items = json.load(f)
    fam_of = {}
    if os.path.exists(FAMILIES):
        with open(FAMILIES, encoding=ENC) as f:
            for fam in json.load(f):
                for part in ("members", "review"):
                    for m in fam.get(part, []):
                        for k in m.get("keys", []):
                            fam_of.setdefault(k.upper(), fam["family_id"])
    rows = []
    for it in items:
        if it["kind"] == "составной":
            continue
        a = ctx.rgba(it["src"][0])
        if a is None:
            continue
        m, c = codes(a)
        if m.sum() < min_area:
            continue
        rows.append((int(m.sum()), it["rank"], it["src"][0], m, c, it["keys"]))
    rows.sort(key=lambda r: r[0])
    print("строк с кадром: %d" % len(rows), flush=True)
    found = []
    for i, (ar, r, k, m, c, keys) in enumerate(rows):
        for ar2, r2, k2, m2, c2, keys2 in rows[i + 1:]:
            if ar2 > ar / GEO + 1:
                break
            inter = (m & m2).sum()
            if inter / max(1, (m | m2).sum()) < GEO:
                continue
            mm_ = m & m2
            f_ab = func_map(c[mm_], c2[mm_])[0]
            f_ba = func_map(c2[mm_], c[mm_])[0]
            if f_ab < 0.90 or f_ba < 0.90:
                continue
            fa_, fb_ = fam_of.get(k.upper()), fam_of.get(k2.upper())
            linked = fa_ is not None and fa_ == fb_
            same_pix = bool((c[mm_] == c2[mm_]).all())
            found.append((k, k2, round(f_ab, 3), round(f_ba, 3), linked, same_pix, len(keys), len(keys2)))
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, "scan_recolor.tsv")
    with open(path, "w", encoding=ENC, newline="") as f:
        f.write("a\tb\tf_ab\tf_ba\tв одном семействе\tпиксели равны\tключей a\tключей b\n")
        for x in found:
            f.write("\t".join(str(v) for v in x) + "\n")
    strict = [x for x in found if x[2] >= FUNC and x[3] >= FUNC and not x[5]]
    missed = [x for x in strict if not x[4]]
    res = {"pairs_geometry_and_func_090": len(found), "strict_recolor": len(strict),
           "strict_not_in_one_family": len(missed)}
    print(json.dumps(res, ensure_ascii=False))
    return res, found


def lookalikes(ctx, out, n=24, min_area=150):
    """Кандидаты в отрицательные контроли - отобраны НЕ по функции палитры: силуэт почти тот же
    (IoU >= 0.97), наборы разные, в одно семейство не собраны, по яркости obj_families похожи
    сильнее всего. Что из них на деле разные вещи - решает просмотр листа, а не этот отбор."""
    with open(ITEMS, encoding=ENC) as f:
        items = json.load(f)
    fam_of = {}
    with open(FAMILIES, encoding=ENC) as f:
        for fam in json.load(f):
            for part in ("members", "review"):
                for m in fam.get(part, []):
                    for k in m.get("keys", []):
                        fam_of.setdefault(k.upper(), fam["family_id"])
    rows = []
    for it in items:
        if it["kind"] == "составной":
            continue
        a = ctx.rgba(it["src"][0])
        if a is None:
            continue
        m = a[..., 3] > 0
        if m.sum() < min_area:
            continue
        rows.append((int(m.sum()), it["src"][0], m, a))
    rows.sort(key=lambda r: r[0])
    cand = []
    for i, (ar, k, m, a) in enumerate(rows):
        for ar2, k2, m2, a2 in rows[i + 1:]:
            if ar2 > ar / 0.97 + 1:
                break
            if (m & m2).sum() / max(1, (m | m2).sum()) < 0.97:
                continue
            if of.split(k)[0] == of.split(k2)[0]:
                continue
            f1, f2 = fam_of.get(k.upper()), fam_of.get(k2.upper())
            if f1 is not None and f1 == f2:
                continue
            rel = of.relation(of_feats(a), of_feats(a2))
            cand.append((rel[2], k, k2))
    cand.sort(reverse=True)
    # не больше двух раз один кадр - иначе лист из одной коробки
    used = Counter()
    pick = []
    for c, k, k2 in cand:
        if used[k] >= 1 or used[k2] >= 1:
            continue
        used[k] += 1
        used[k2] += 1
        pick.append((k, k2, round(c, 3)))
        if len(pick) >= n:
            break
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "lookalikes.tsv"), "w", encoding=ENC, newline="") as f:
        f.write("a\tb\tcorr obj_families\n")
        for x in pick:
            f.write("%s\t%s\t%s\n" % x)
    print("кандидатов в похожие: %d, на лист %d" % (len(cand), len(pick)))
    return pick


def sheet(ctx, pairs, path, k=3):
    """Лист пар: A | B | B, выведенный из A функцией палитры | необъяснённое пурпуром."""
    from PIL import Image, ImageDraw
    W, H, lab = 32 * k, 40 * k, 14
    im = Image.new("RGB", (4 * W + 5 * 4 + 360, len(pairs) * (H + 6) + 6), (40, 40, 44))
    d = ImageDraw.Draw(im)
    for r, (ka, kb, note) in enumerate(pairs):
        y = 6 + r * (H + 6)
        A, B = ctx.rgba(ka), ctx.rgba(kb)
        if A is None or B is None:
            continue
        ma, ca = codes(A)
        mb, cb = codes(B)
        m = ma & mb
        _f, mp, _, _ = func_map(ca[m], cb[m])
        P = np.zeros_like(A)
        for yy, xx in zip(*np.nonzero(ma)):
            v = mp.get(int(ca[yy, xx]))
            if v is not None:
                P[yy, xx] = ((v >> 16) & 255, (v >> 8) & 255, v & 255, 255)
        bad = (m & (codes(P)[1] != cb)) | (ma ^ mb)
        D = np.zeros_like(A)
        D[..., 3] = np.where(mb | ma, 255, 0)
        D[..., :3] = np.where((mb | ma)[..., None], 90, 0)
        D[bad] = (255, 0, 255, 255)
        for c, src in enumerate((A, B, P, D)):
            t = Image.fromarray(src, "RGBA").resize((W, H), Image.NEAREST)
            bg = Image.new("RGBA", (W, H), (70, 70, 76, 255))
            bg.alpha_composite(t)
            im.paste(bg.convert("RGB"), (4 + c * (W + 4), y))
        x = 4 * (W + 4) + 8
        d.text((x, y + 4), "%s -> %s" % (ka, kb), fill=(230, 230, 230))
        for j, line in enumerate(str(note).split("|")):
            d.text((x, y + 4 + (j + 1) * lab), line.strip()[:58], fill=(200, 200, 160))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im.save(path)
    return path


NEIGH_SHARE = 0.80  # постоянный сосед: в стольких местах кадра
NEIGH_MIN = 3       # и мест не меньше


def places_of():
    """Мест кадра на картах (touch.tsv поиска семейств)."""
    out = {}
    p = os.path.join(os.path.dirname(ITEMS), "touch.tsv")
    with open(p, encoding=ENC) as f:
        for line in list(f)[1:]:
            x = line.rstrip("\n").split("\t")
            out[x[0].upper()] = int(x[1])
    return out


def discover(ctx, keys, out):
    """Родство каждого кадра из keys: кандидаты с уровнем доказательства, без маршрута.
    RECOLOR_OF - кадр выводится из более частого родственника (цвет - функция цвета, силуэт тот же);
    RECOLOR_WITH_LOCAL_EDIT - набор того же номера целиком перекраска, а этот кадр от неё отступил;
    FIXED_NEIGHBOUR - в каждом месте кадра рядом стоит один и тот же предмет (часть целого?).
    Сторона перекраски - по числу мест: чаще стоящий - основа. verified всегда False: VERIFIED ставит человек."""
    with open(ITEMS, encoding=ENC) as f:
        items = json.load(f)
    places = places_of()
    rows = []
    for it in items:
        if it["kind"] == "составной":
            continue
        a = ctx.rgba(it["src"][0])
        if a is None:
            continue
        m, c = codes(a)
        if m.any():
            rows.append((it["src"][0], m, c, it["keys"]))
    set_cache = {}
    res = {}
    for k in keys:
        A = ctx.rgba(k)
        rels = []
        if A is not None:
            ma, ca = codes(A)
            sk, fk = of.split(k)
            pk = places.get(k.upper(), 0)
            for k2, m2, c2, keys2 in rows:
                if k2.upper() == k.upper() or k.upper() in (x.upper() for x in keys2):
                    continue
                u = (ma | m2).sum()
                if not u or (ma & m2).sum() / u < GEO:
                    continue
                s2, f2 = of.split(k2)
                twin = None
                if f2 == fk and s2.upper() != sk.upper():
                    key = (s2.upper(), sk.upper())
                    if key not in set_cache:
                        set_cache[key] = sets(ctx, s2, sk)
                    twin = set_cache[key]
                p = pair(ctx, k2, k)
                kind, level, why = candidate(p, twin)
                if kind == "NONE":
                    continue
                p2 = places.get(k2.upper(), 0)
                side = "derived" if p2 > pk or (p2 == pk and k2 < k) else "base"
                if kind == "RECOLOR_OF" and side == "derived" and p["4_palette"]["f_ab"] < FUNC:
                    side = "base"           # из родственника не выводится - значит не наша сторона
                rels.append({"kind": kind, "level": level, "relative": k2, "side": side, "places": [pk, p2],
                             "why": why, "verified": False})
            nb = neigh(ctx, k, top=40)
            for x in nb["neighbours"]:
                o = x["offset"]
                if (x["layer"] == 3 and o[2] == 0 and abs(o[0]) + abs(o[1]) == 1 and x["share"] >= NEIGH_SHARE
                        and nb["places"] >= NEIGH_MIN and x["key"].upper() != k.upper()):
                    rels.append({"kind": "FIXED_NEIGHBOUR", "level": "CANDIDATE", "relative": x["key"],
                                 "side": "part?", "places": [nb["places"], None],
                                 "why": ["сосед %s на %s в %d из %d мест" % (x["key"], o, x["n"], nb["places"])],
                                 "verified": False})
        res[k] = rels
        print(k, [(r["kind"], r["level"], r["relative"], r["side"]) for r in rels], flush=True)
    os.makedirs(out, exist_ok=True)
    data = {"thresholds": {"GEO": GEO, "FUNC": FUNC, "SET_SHARE": SET_SHARE, "NEIGH_SHARE": NEIGH_SHARE,
                           "NEIGH_MIN": NEIGH_MIN},
            "note": "кандидаты родства, не маршрут; verified ставит только человек", "relations": res}
    with open(os.path.join(out, "relations.json"), "w", encoding=ENC) as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return data


# ---------- опыт V1 ----------

V1 = {
    "recolor": [("JUNGLE:8", "BLACKJUNGLE:8")],
    "state": [("CULTIVAT:12", "CULTIVAT_UBER:12")],
    "part": ["C_EXT_XCOM:36"],
    "positive_controls": [("JUNGLE:8", "NEOJUNGLE:8"), ("CULTIVAT:12", "CULTIVAT_PP:12")],
    "set_pairs": [("JUNGLE", "BLACKJUNGLE"), ("JUNGLE", "NEOJUNGLE"), ("CULTIVAT", "CULTIVAT_UBER"),
                  ("CULTIVAT", "CULTIVAT_PP")],
}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pair")
    p.add_argument("a")
    p.add_argument("b")
    p = sub.add_parser("sets")
    p.add_argument("a")
    p.add_argument("b")
    p = sub.add_parser("neigh")
    p.add_argument("key")
    p = sub.add_parser("scan")
    p.add_argument("--out", required=True)
    p = sub.add_parser("discover", help="родство кадров списка (по умолчанию 28 предметов V3)")
    p.add_argument("--out", required=True)
    p.add_argument("keys", nargs="*")
    p = sub.add_parser("lookalikes")
    p.add_argument("--out", required=True)
    p = sub.add_parser("sheet", help="лист пар из TSV a<TAB>b[<TAB>заметка]")
    p.add_argument("tsv")
    p.add_argument("png")
    p = sub.add_parser("v1")
    p.add_argument("--out", required=True)
    p.add_argument("--negatives", default="", help="TSV a<TAB>b - отрицательные контроли")
    a = ap.parse_args()
    ctx = Ctx()
    if a.cmd == "pair":
        r = pair(ctx, a.a, a.b)
        r["candidate"] = candidate(r)
        print(json.dumps(r, ensure_ascii=False, indent=1))
    elif a.cmd == "sets":
        print(json.dumps(sets(ctx, a.a, a.b), ensure_ascii=False, indent=1))
    elif a.cmd == "neigh":
        print(json.dumps(neigh(ctx, a.key), ensure_ascii=False, indent=1))
    elif a.cmd == "scan":
        scan(ctx, a.out)
    elif a.cmd == "discover":
        keys = a.keys
        if not keys:
            import identity_routing as ir
            keys = ir.load_spec(ir.OUT)["assets"]
        discover(ctx, keys, a.out)
    elif a.cmd == "lookalikes":
        lookalikes(ctx, a.out)
    elif a.cmd == "sheet":
        with open(a.tsv, encoding=ENC) as f:
            rows = [line.rstrip("\n").split("\t") for line in list(f)[1:] if line.strip()]
        print(sheet(ctx, [(r[0], r[1], " | ".join(r[2:])) for r in rows], a.png))
    elif a.cmd == "v1":
        res = {"sets": {}, "pairs": [], "neigh": {}}
        for sa, sb in V1["set_pairs"]:
            res["sets"]["%s~%s" % (sa, sb)] = sets(ctx, sa, sb)
        negs = []
        if a.negatives and os.path.exists(a.negatives):
            with open(a.negatives, encoding=ENC) as f:
                for line in list(f)[1:]:
                    x = line.rstrip("\n").split("\t")
                    if len(x) >= 2:
                        negs.append((x[0], x[1]))
        groups = [(g, ka, kb) for g in ("recolor", "state", "positive_controls") for ka, kb in V1[g]]
        groups += [("negative", ka, kb) for ka, kb in negs]
        for grp, ka, kb in groups:
            pr = pair(ctx, ka, kb)
            (sa, fa), (sb, fb) = of.split(ka), of.split(kb)
            s = None
            if fa == fb and sa.upper() != sb.upper():
                name = "%s~%s" % (sa, sb)
                if name not in res["sets"]:
                    res["sets"][name] = sets(ctx, sa, sb)
                s = res["sets"][name]
            pr["group"] = grp
            pr["candidate"] = candidate(pr, s)
            res["pairs"].append(pr)
        for k in V1["part"]:
            res["neigh"][k] = neigh(ctx, k)
        os.makedirs(a.out, exist_ok=True)
        with open(os.path.join(a.out, "probe.json"), "w", encoding=ENC) as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
        for pr in res["pairs"]:
            print(pr["group"], pr["a"], pr["b"], pr["candidate"][:2])
    return 0


if __name__ == "__main__":
    sys.exit(main())
