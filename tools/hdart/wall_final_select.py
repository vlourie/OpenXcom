"""WALL_FINAL_SELECT: для каждой используемой стены выбрать CURRENT_HD, A или B2 (решение специалиста 08.10).

Варианты A (xbrz) и B2 (esrgan) рисует wall_final_render.py (через очередь gpuq). Здесь модели нет вовсе -
только замеры и правила, всё на процессоре.

  measure   замеры: текущий HD каждого кадра (пак установки, R-087), A и B2 каждой картинки - против
            классики в боевой палитре (wall_final_render.Classic); признак материала по классике.
            -> <out>/measure_frames.tsv, <out>/measure_pictures.tsv
  select    правила -> <out>/select.tsv (решение на кадр), <out>/seams.tsv, <out>/SUMMARY.md
  sheet     лист спорного хвоста ОРИГИНАЛ | CURRENT_HD | A | B2 и малая выборка автоматических решений

Правила (порядок важности: геометрия, стыки, окна и проёмы, материал, деталь):
  - кадр, поставленный другой сессией (ставила_сессия), и закрытые кадры OWNED - KEEP_CURRENT;
  - гладкий материал: B2, если он чист (тон, строение, новых линий нет); иначе A; оба не чисты - текущий
    HD, если он годен, иначе хвост;
  - фактурный (и неясный - безопасная сторона): текущий HD остаётся, если он годен или отличается от классики
    только рисунком (lum_corr, линии - свой рисунок кирпича и досок, лист калибровки 08.10); брак геометрии
    (промах, вылет, залитый проём, край, сдвиг) - B2 или A; тон или сильное расхождение строения сразу по
    двум мерам - хвост; нет текущего - B2/A;
  - зеркало - решение источника; петля анимации - один способ на всю петлю (R-071);
  - стык разных источников с расхождением тона против классики - в отчёт стыков, сильные - в хвост.
Альфа сквозной стены в итоге всегда из геометрии оригинала (wall_restore.alpha_of), какой бы вариант ни
выбран; у текущего HD расхождение его альфы с оригиналом меряется (open_fill, miss_in) и решает годность.
В мод ничего не кладётся: выбор принимает Vitali.

  wall_final_select.py measure|select|sheet [--out census/walls/final_select]
"""
import argparse
import csv
import json
import os
import sys
import time
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np                                  # noqa: E402
import cv2                                          # noqa: E402
from PIL import Image, ImageDraw, ImageFont         # noqa: E402
import map_mockup as mm                             # noqa: E402
import probe_object as po                           # noqa: E402
import wall_final_render as wfr                     # noqa: E402
import wall_restore as wr                           # noqa: E402
import wall_restore_c as wrc                        # noqa: E402
import wall_section as ws                           # noqa: E402

ENC = "utf-8-sig"
ROOT = os.path.dirname(os.path.dirname(HERE))
FRAMES = "census/walls/wall_render_frames.tsv"
PLAN = "census/walls/wall_render_plan.tsv"
JUNCTIONS = "census/walls/wall_junctions.tsv"
OWNED = {"ROADS:0", "ROADSLUX:0", "TAVERN:14", "TAVERN:16", "CATACDECOR_CONC:21"}   # закрыто для этой работы

# признак материала по классике: доля ровных мест (окно 3x3, перепад яркости < FLAT_RANGE) внутри силуэта.
# Калибровка на census/walls/restore/c_materials.json (26 кадров): гладкие 0.09-0.81, фактурные 0.00-0.08.
FLAT_RANGE = 6.0
SMOOTH_MIN, TEXTURED_MAX = 0.15, 0.06       # между ними - неясный, идёт как фактурный (безопасная сторона)

# ворота нового варианта (A, B2) против классики; альфа у них - маска оригинала по построению
NEW_LUM_CORR, NEW_DLUM, NEW_COLOR, NEW_LINES = 0.95, 4.0, 10.0, 40
# годность текущего HD: геометрия, проёмы, строение, тон, выдуманные линии (против A)
CUR_OK = dict(miss=0.01, spill=0.01, open_fill=0.10, edge=1, shift=0.75, lum_corr=0.80, dlum=10.0, lines=120)
CUR_BAD = dict(miss=0.04, spill=0.04, open_fill=0.30, edge=3, shift=1.5, lum_corr=0.55, dlum=25.0, lines=400)
SEAM_DTONE, SEAM_TAIL = 8.0, 14.0           # расхождение сдвига тона двух соседей против классики


def frame_key(t):
    s, n = t.rsplit(":", 1)
    return "%s:%d" % (s.upper(), int(n))


def read_tsv(p):
    with open(p, encoding=ENC, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def write_tsv(p, head, rows):
    with open(p, "w", encoding=ENC, newline="") as f:
        f.write("\t".join(head) + "\n")
        for r in rows:
            f.write("\t".join("" if v is None else str(v) for v in r) + "\n")


def lum(rgb):
    return 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]


def flat_share(rgba):
    m = rgba[..., 3] > 0
    l = lum(rgba[..., :3].astype(np.float32)).astype(np.float32)
    k = np.ones((3, 3), np.uint8)
    inner = cv2.erode(m.astype(np.uint8), k) > 0
    if inner.sum() < 8:
        return None
    rng = cv2.dilate(np.where(m, l, -1e4).astype(np.float32), k) - cv2.erode(np.where(m, l, 1e4).astype(np.float32), k)
    return float((rng[inner] < FLAT_RANGE).mean())


def material(fs):
    if fs is None:
        return "textured"
    return "smooth" if fs >= SMOOTH_MIN else ("textured" if fs <= TEXTURED_MAX else "unclear")


def small_of(hd):
    a = np.asarray(hd, np.float32)
    al = a[..., 3:4] / 255.0
    pm = (a[..., :3] * al).reshape(40, 4, 32, 4, 3).mean((1, 3))
    am = al.reshape(40, 4, 32, 4, 1).mean((1, 3))
    return pm / np.maximum(am, 1e-3), am[..., 0]


def measure_hd(hd, frame, mask, base):
    """HD x4 против классики k=1 (frame RGBA) и против A (base): геометрия, проёмы, строение, тон, новые линии."""
    m = wr.metrics(hd, frame, mask)
    small, cov = small_of(hd)
    n = max(int(mask.sum()), 1)
    op = ws.openings(mask)
    o = np.asarray(frame, np.float32)[..., :3]
    dl = float((lum(small) - lum(o))[mask].mean()) if mask.any() else 0.0
    return dict(miss=round(float(((cov <= 0.5) & mask).sum()) / n, 4),
                spill=round(float(((cov > 0.5) & ~mask).sum()) / n, 4),
                open_fill=round(float(((cov > 0.5) & op).sum()) / op.sum(), 3) if op.any() else 0.0,
                edge=ws.edge_diff(hd, frame), shift=round(float(np.hypot(*m["shift"])), 2),
                lum_corr=m["lum_corr"], edge_corr=m["edge_corr"], color=m["color_diff"], dlum=round(dl, 2),
                lines=wrc.new_lines(hd, base))


MCOLS = ["miss", "spill", "open_fill", "edge", "shift", "lum_corr", "edge_corr", "color", "dlum", "lines"]


def cur_path(key):
    s, n = key.rsplit(":", 1)
    return os.path.join(po.MOD_TERRAIN, s + ".PCK", n + ".png")


def find_cur(key):
    """Путь текущего HD в паке установки с учётом регистра папки набора (папки паков - заглавными)."""
    s, n = key.rsplit(":", 1)
    for name in (s, s.upper()):
        p = os.path.join(po.MOD_TERRAIN, name + ".PCK", n + ".png")
        if os.path.exists(p):
            return p
    return None


def do_measure(a):
    os.makedirs(a.out, exist_ok=True)
    render = os.path.join(a.out, "render")
    world = mm.World()
    cl = wfr.Classic(world)
    rows = read_tsv(FRAMES)
    prow, frow, t0 = [], [], time.time()
    for i, r in enumerate(rows):
        h = r["картинка"]
        frames = [frame_key(t) for t in r["кадры"].split()]
        rep = None
        for k in frames:
            s, n = k.rsplit(":", 1)
            ix = cl.idx(s, int(n))
            if ix is not None:
                rep = ix
                break
        if rep is None:
            prow.append([h, "", "", "", ""] + [""] * (2 * len(MCOLS)))
            continue
        mask = rep > 0
        frame = Image.fromarray(cl.rgba(rep), "RGBA")
        fs = flat_share(np.asarray(frame))
        A = Image.open(os.path.join(render, "xbrz", h + ".png")).convert("RGBA")
        B = Image.open(os.path.join(render, "esrgan", h + ".png")).convert("RGBA")
        ma, mb = measure_hd(A, frame, mask, A), measure_hd(B, frame, mask, A)
        thru = bool(ws.openings(mask).any())
        prow.append([h, "1" if thru else "0", "" if fs is None else "%.3f" % fs, material(fs), int(mask.sum())]
                    + [ma[c] for c in MCOLS] + [mb[c] for c in MCOLS])
        for k in frames:
            p = find_cur(k)
            if p is None:
                frow.append([k, h, "нет"] + [""] * len(MCOLS))
                continue
            im = Image.open(p).convert("RGBA")
            if im.size != (128, 160):
                frow.append([k, h, "размер %dx%d" % im.size] + [""] * len(MCOLS))
                continue
            mc = measure_hd(im, frame, mask, A)
            frow.append([k, h, "есть"] + [mc[c] for c in MCOLS])
        if (i + 1) % 300 == 0:
            print("картинок %d из %d, %.0f с" % (i + 1, len(rows), time.time() - t0), flush=True)
    write_tsv(os.path.join(a.out, "measure_pictures.tsv"),
              ["картинка", "сквозная", "ровных", "материал", "пикселей"] + ["A_" + c for c in MCOLS]
              + ["B2_" + c for c in MCOLS], prow)
    write_tsv(os.path.join(a.out, "measure_frames.tsv"), ["кадр", "картинка", "текущий"] + MCOLS, frow)
    print("замер: картинок %d, кадров %d, %.0f с" % (len(prow), len(frow), time.time() - t0), flush=True)


def fnum(v):
    return None if v in ("", None, "None") else float(v)


def new_ok(m):
    return (fnum(m["lum_corr"]) is not None and fnum(m["lum_corr"]) >= NEW_LUM_CORR
            and abs(fnum(m["dlum"])) <= NEW_DLUM and fnum(m["color"]) <= NEW_COLOR and int(m["lines"]) <= NEW_LINES)


def cur_state(m):
    """OK / BAD / BORDER и причины (что не прошло ворота годности, что прошло ворота явного брака)."""
    lc = fnum(m["lum_corr"])
    v = dict(miss=fnum(m["miss"]), spill=fnum(m["spill"]), open_fill=fnum(m["open_fill"]), edge=fnum(m["edge"]),
             shift=fnum(m["shift"]), lum_corr=lc if lc is not None else 0.0, dlum=abs(fnum(m["dlum"])),
             lines=fnum(m["lines"]))
    bad = [k for k in CUR_BAD if (v[k] < CUR_BAD[k] if k == "lum_corr" else v[k] > CUR_BAD[k])]
    notok = [k for k in CUR_OK if (v[k] < CUR_OK[k] if k == "lum_corr" else v[k] > CUR_OK[k])]
    if bad:
        return "BAD", bad
    return ("OK", []) if not notok else ("BORDER", notok)


GEOM = ("miss", "spill", "open_fill", "edge", "shift")
STRUCT_LC, STRUCT_LINES, STRUCT_LINES_ALONE = 0.55, 400, 1000


def struct_strong(m):
    """Строение текущего далеко от классики сразу по двум мерам (или по линиям очень сильно) - вероятная
    выдуманная деталь (UAC_BASE_V 61: двустворчатая дверь вместо пятен), решает человек."""
    lc, ln = fnum(m["lum_corr"]), fnum(m["lines"])
    lc = 0.0 if lc is None else lc
    return (lc < STRUCT_LC and ln > STRUCT_LINES) or ln > STRUCT_LINES_ALONE


def loops():
    """Петли анимации: множества кадров (записи с анимацией), объединённые по общим кадрам."""
    parent = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for r in read_tsv(PLAN):
        if r["анимация"] != "1":
            continue
        s = r["запись"].rsplit(":", 1)[0].upper()
        fr = ["%s:%d" % (s, int(n)) for n in r["кадры"].split()]
        for f in fr[1:]:
            parent[find(f)] = find(fr[0])
    groups = defaultdict(set)
    for f in list(parent):
        groups[find(f)].add(f)
    return [g for g in groups.values() if len(g) > 1]


def do_select(a):
    pics = {r["картинка"]: r for r in read_tsv(os.path.join(a.out, "measure_pictures.tsv"))}
    meas = {r["кадр"]: r for r in read_tsv(os.path.join(a.out, "measure_frames.tsv"))}
    rows = read_tsv(FRAMES)
    info, pic_of = {}, {}
    for r in rows:
        for t in r["кадры"].split():
            k = frame_key(t)
            pic_of[k] = r["картинка"]
            info[k] = r
    picstate = {}
    for h, p in pics.items():
        if not p["материал"]:
            picstate[h] = dict(mat="", A=False, B2=False)
            continue
        A = {c: p["A_" + c] for c in MCOLS}
        B = {c: p["B2_" + c] for c in MCOLS}
        picstate[h] = dict(mat=p["материал"], A=new_ok(A), B2=new_ok(B), thru=p["сквозная"] == "1")

    def best_new(h):
        st = picstate[h]
        return "B2" if st["B2"] else ("A" if st["A"] else None)

    dec = {}                                    # кадр -> (способ, авто/хвост, причина)
    for k, r in info.items():
        h = r["картинка"]
        st = picstate.get(h, dict(mat="", A=False, B2=False))
        m = meas.get(k)
        has_cur = m is not None and m["текущий"] == "есть"
        cs, why = cur_state(m) if has_cur else ("NONE", [])
        if r["ставила_сессия"] or k in OWNED:
            dec[k] = ("CURRENT_HD", "auto", "OWNED: кадр другой работы", cs, why)
            continue
        if r["маршрут"].startswith("MIRROR"):
            dec[k] = ("MIRROR", "follow", "зеркало " + frame_key(r["источник"]), cs, why)
            continue
        if not st["mat"]:
            dec[k] = ("CURRENT_HD" if has_cur else "", "tail", "нет классики", cs, why)
            continue
        nb = best_new(h)
        if st["mat"] == "smooth":
            if nb:
                dec[k] = (nb, "auto", "гладкий, %s чист" % nb, cs, why)
            elif cs == "OK":
                dec[k] = ("CURRENT_HD", "auto", "гладкий, A и B2 не прошли ворота, текущий годен", cs, why)
            else:
                dec[k] = ("B2", "tail", "гладкий, A и B2 не прошли ворота, текущий " + cs, cs, why)
        else:
            # фактурный: строение (lum_corr, линии) у своего рисунка кирпича и досок расходится с классикой
            # законно - лист калибровки 08.10: BARN 10/12, доски BARN 5/6 у текущего лучше A/B2. Заменяет
            # только брак геометрии; тон и сильное расхождение строения - человеку
            geo = [w for w in why if w in GEOM]
            if cs == "OK":
                dec[k] = ("CURRENT_HD", "auto", "фактурный, текущий годен", cs, why)
            elif cs == "NONE":
                dec[k] = (nb or "B2", "auto" if nb else "tail", "фактурный, текущего нет", cs, why)
            elif cs == "BAD" and geo and nb:
                dec[k] = (nb, "auto", "фактурный, текущий плох геометрией: " + ",".join(why), cs, why)
            elif geo or (cs == "BAD" and "dlum" in why) or struct_strong(m):
                dec[k] = (nb or "CURRENT_HD", "tail", "фактурный, текущий %s: %s" % (cs, ",".join(why)), cs, why)
            else:
                dec[k] = ("CURRENT_HD", "auto", "фактурный, текущий отличается только рисунком: %s"
                          % ",".join(why), cs, why)
    # зеркало - решение источника
    for k, d in list(dec.items()):
        if d[0] == "MIRROR":
            src = frame_key(info[k]["источник"])
            sd = dec.get(src)
            if sd is None or sd[0] == "MIRROR":
                dec[k] = ("CURRENT_HD", "tail", "зеркало без решения источника " + src, d[3], d[4])
            else:
                dec[k] = (sd[0], sd[1] if sd[1] == "tail" else "auto", "зеркало %s (%s)" % (src, sd[0]), d[3], d[4])
    # петли анимации - один способ
    nloop_fix = 0
    for g in loops():
        g = [f for f in g if f in dec and dec[f][2].split(":")[0] != "OWNED"]
        meths = {dec[f][0] for f in g}
        if len(meths) <= 1 and not any(dec[f][1] == "tail" for f in g):
            continue
        nloop_fix += 1
        hs = {pic_of[f] for f in g}
        if all(dec[f][3] != "NONE" and not any(w in GEOM for w in dec[f][4]) for f in g):
            m, how = "CURRENT_HD", "auto"
        elif all(picstate[h]["B2"] for h in hs):
            m, how = "B2", "auto"
        elif all(picstate[h]["A"] or picstate[h]["B2"] for h in hs):
            m, how = "A", "auto"
        else:
            m, how = sorted(meths)[0], "tail"
        for f in g:
            dec[f] = (m, how, "петля из %d кадров: один способ (%s)" % (len(g), dec[f][2]), dec[f][3], dec[f][4])
    # стыки: сдвиг тона против классики у двух соседей, когда источники разные
    meas_dl = {}
    for k, d in dec.items():
        if d[0] == "CURRENT_HD" and k in meas and meas[k]["текущий"] == "есть":
            meas_dl[k] = fnum(meas[k]["dlum"])
        elif d[0] in ("A", "B2") and pic_of.get(k) in pics and pics[pic_of[k]]["материал"]:
            meas_dl[k] = fnum(pics[pic_of[k]][d[0] + "_dlum"])
    seam_rows, seam_tail = [], set()
    for r in read_tsv(JUNCTIONS):
        x, y = frame_key(r["a"]), frame_key(r["b"])
        if x not in dec or y not in dec or x not in meas_dl or y not in meas_dl:
            continue
        sx, sy = dec[x][0], dec[y][0]
        if (sx == "CURRENT_HD") == (sy == "CURRENT_HD"):
            continue
        dt = abs(meas_dl[x] - meas_dl[y])
        if dt < SEAM_DTONE:
            continue
        seam_rows.append([x, sx, y, sy, r["мест"], "%.1f" % dt])
        if dt >= SEAM_TAIL:
            for f in (x, y):
                if dec[f][0] == "CURRENT_HD" and dec[f][2].startswith("OWNED"):
                    continue
                seam_tail.add(f)
    for f in seam_tail:
        d = dec[f]
        if d[1] != "tail":
            dec[f] = (d[0], "tail", d[2] + "; стык с другим источником, тон расходится", d[3], d[4])
    seam_rows.sort(key=lambda r: -int(r[4]))
    write_tsv(os.path.join(a.out, "seams.tsv"), ["a", "способ_a", "b", "способ_b", "мест", "расхождение_тона"],
              seam_rows)
    out = []
    for k in sorted(dec, key=lambda k: (-int(info[k]["вес_мест"] or 0), k)):
        d = dec[k]
        h = info[k]["картинка"]
        st = picstate.get(h, {})
        out.append([k, h, info[k]["роль"], info[k]["вес_мест"], st.get("mat", ""), "1" if st.get("thru") else "0",
                    d[3], ",".join(d[4]), "1" if st.get("A") else "0", "1" if st.get("B2") else "0", d[0], d[1], d[2]])
    write_tsv(os.path.join(a.out, "select.tsv"),
              ["кадр", "картинка", "роль", "мест", "материал", "сквозная", "текущий", "текущий_не_прошёл",
               "A_чист", "B2_чист", "выбор", "как", "причина"], out)
    # сквозная стена с выбранным текущим HD: альфу в итоге берём из геометрии оригинала (решение 08.10), здесь
    # только список кадров, где альфа пака с ней расходится - на них итог заметно отличается от пака
    afix = []
    for r in out:
        m = meas.get(r[0])
        if r[10] == "CURRENT_HD" and r[5] == "1" and m is not None and m["текущий"] == "есть":
            v = [fnum(m[c]) or 0.0 for c in ("miss", "spill", "open_fill")]
            if max(v) > 0.002:
                afix.append([r[0], r[1], r[3]] + ["%.4f" % x for x in v])
    write_tsv(os.path.join(a.out, "alpha_fix.tsv"), ["кадр", "картинка", "мест", "miss", "spill", "open_fill"], afix)
    summary(a, out, seam_rows, nloop_fix, len(afix))


def summary(a, out, seam_rows, nloop_fix, nafix=0):
    from collections import Counter
    c = Counter((r[10], r[11]) for r in out)
    mat = Counter(r[4] for r in out)
    cur = Counter(r[6] for r in out)
    tail = [r for r in out if r[11] == "tail"]
    tail_pics = {r[1] for r in tail}
    L = ["# WALL_FINAL_SELECT", "",
         "Решение специалиста 08.10 (DECISIONS): стены - выбор лучшего из CURRENT_HD / A / B2 по материалу.",
         "Модели здесь нет: A и B2 нарисованы wall_final_render.py (gpuq #487), отбор - wall_final_select.py.", "",
         "Кадров %d, картинок %d." % (len(out), len({r[1] for r in out})), "",
         "## Материал по классике (доля ровных мест, калибровка c_materials.json 26/26)", ""]
    L += ["- %s: %d" % (k or "нет классики", v) for k, v in mat.most_common()]
    L += ["", "## Текущий HD (против классики в боевой палитре)", ""]
    L += ["- %s: %d" % (k, v) for k, v in cur.most_common()]
    L += ["", "## Выбор", "", "| способ | авто | хвост |", "|---|---|---|"]
    for m in ("CURRENT_HD", "A", "B2", ""):
        L.append("| %s | %d | %d |" % (m or "-", c[(m, "auto")], c[(m, "tail")]))
    L += ["", "Хвост: %d кадров, %d картинок - на лист человеку." % (len(tail), len(tail_pics)),
          "Петель анимации, сведённых к одному способу: %d." % nloop_fix,
          "Стыков разных источников с расхождением тона >= %.0f: %d (>= %.0f - в хвост)."
          % (SEAM_DTONE, len(seam_rows), SEAM_TAIL), "",
          "Ворота нового варианта: lum_corr >= %.2f, |dlum| <= %.0f, color <= %.0f, новых линий против A <= %d."
          % (NEW_LUM_CORR, NEW_DLUM, NEW_COLOR, NEW_LINES),
          "Годность текущего: %s; явный брак: %s." % (CUR_OK, CUR_BAD), "",
          "Альфа сквозной стены в итоге - из геометрии оригинала при любом выборе; у выбранного текущего HD она"
          " расходится с альфой пака на %d кадрах (alpha_fix.tsv, порог 0.2 процента силуэта)." % nafix,
          "В мод ничего не положено."]
    with open(os.path.join(a.out, "SUMMARY.md"), "w", encoding=ENC) as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L))


def on_floor(im, size):
    b = Image.new("RGBA", size, (34, 34, 40, 255))
    if im is not None:
        b.alpha_composite(im.resize(size, Image.NEAREST) if im.size != size else im)
    return b.convert("RGB")


def build_sheet(out, cl, rows, path, title):
    """Лист: ОРИГИНАЛ (x4 nearest) | CURRENT_HD | A | B2 на тёмном полу, справа замеры и причина."""
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 13)
    W, H = 128, 160
    if True:
        cols = ["ОРИГИНАЛ", "CURRENT_HD", "A", "B2"]
        sh = Image.new("RGB", (4 * (W + 6) + 360, len(rows) * (H + 6) + 30), (18, 18, 22))
        d = ImageDraw.Draw(sh)
        d.text((6, 6), title, fill=(255, 220, 90), font=font)
        for j, c in enumerate(cols):
            d.text((6 + j * (W + 6), 18), c, fill=(200, 200, 200), font=font)
        for i, r in enumerate(rows):
            y = 30 + i * (H + 6)
            s, n = r["кадр"].rsplit(":", 1)
            ix = cl.idx(s, int(n))
            ims = [Image.fromarray(cl.rgba(ix), "RGBA") if ix is not None else None]
            p = find_cur(r["кадр"])
            ims.append(Image.open(p).convert("RGBA") if p else None)
            for m in ("xbrz", "esrgan"):
                q = os.path.join(out, "render", m, r["картинка"] + ".png")
                ims.append(Image.open(q).convert("RGBA") if os.path.exists(q) else None)
            for j, im in enumerate(ims):
                sh.paste(on_floor(im, (W, H)), (6 + j * (W + 6), y))
            tx = 6 + 4 * (W + 6)
            lines = [r["кадр"], "%s, мест %s, %s%s" % (r["роль"], r["мест"], r["материал"],
                                                      ", сквозная" if r["сквозная"] == "1" else ""),
                     "текущий %s %s" % (r["текущий"], r["текущий_не_прошёл"]),
                     "A чист %s, B2 чист %s" % (r["A_чист"], r["B2_чист"]),
                     "предложено: %s" % r["выбор"]]
            reason = r["причина"]
            while reason:
                lines.append(reason[:48])
                reason = reason[48:]
            for li, t in enumerate(lines[:10]):
                d.text((tx, y + 4 + li * 15), t, fill=(230, 230, 230) if li else (255, 220, 90), font=font)
        sh.save(path)
        print(path, sh.size, len(rows))


def build_compact(out, cl, rows, path, title, per_row=4):
    """Один лист хвоста: номер, ОРИГИНАЛ | CURRENT_HD | A | B2 по 96x120, под ними кадр и предложение."""
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 12)
    W, H, G = 96, 120, 2
    bw, bh = 4 * (W + G) + 12, H + 34
    nrow = (len(rows) + per_row - 1) // per_row
    sh = Image.new("RGB", (per_row * bw + 6, nrow * bh + 40), (18, 18, 22))
    d = ImageDraw.Draw(sh)
    d.text((6, 6), title, fill=(255, 220, 90), font=font)
    d.text((6, 22), "в каждой ячейке: ОРИГИНАЛ | CURRENT_HD | A (xBRZ) | B2 (xBRZ+ESRGAN); номер = строка tail.tsv",
           fill=(200, 200, 200), font=font)
    for i, r in enumerate(rows):
        x0, y0 = 6 + (i % per_row) * bw, 40 + (i // per_row) * bh
        s, n = r["кадр"].rsplit(":", 1)
        ix = cl.idx(s, int(n))
        ims = [Image.fromarray(cl.rgba(ix), "RGBA") if ix is not None else None]
        p = find_cur(r["кадр"])
        ims.append(Image.open(p).convert("RGBA") if p else None)
        for m in ("xbrz", "esrgan"):
            q = os.path.join(out, "render", m, r["картинка"] + ".png")
            ims.append(Image.open(q).convert("RGBA") if os.path.exists(q) else None)
        for j, im in enumerate(ims):
            sh.paste(on_floor(im, (W, H)), (x0 + j * (W + G), y0))
        d.text((x0, y0 + H + 2), "%d. %s  мест %s  %s" % (i + 1, r["кадр"], r["мест"], r["материал"]),
               fill=(255, 220, 90), font=font)
        d.text((x0, y0 + H + 16), ("предл. %s; текущий %s %s" % (r["выбор"], r["текущий"],
                                                                r["текущий_не_прошёл"]))[:62],
               fill=(220, 220, 220), font=font)
    sh.save(path)
    print(path, sh.size, len(rows))


def do_sheet(a):
    sel = read_tsv(os.path.join(a.out, "select.tsv"))
    cl = wfr.Classic(mm.World())

    def build(rows, path, title):
        build_sheet(a.out, cl, rows, path, title)

    seen, tail = set(), []
    for r in sel:
        if r["как"] == "tail" and r["картинка"] not in seen:
            seen.add(r["картинка"])
            tail.append(r)
    os.makedirs(os.path.join(a.out, "sheets", "detail"), exist_ok=True)
    build_compact(a.out, cl, tail, os.path.join(a.out, "sheets", "tail.png"),
                  "WALL_FINAL_SELECT: спорный хвост, %d картинок (по весу мест)" % len(tail))
    # вердикты человека: одна строка на картинку хвоста, кадры той же картинки идут за ней
    frames = defaultdict(list)
    for r in sel:
        if r["как"] == "tail":
            frames[r["картинка"]].append(r["кадр"])
    write_tsv(os.path.join(a.out, "tail.tsv"),
              ["№", "картинка", "кадры", "мест", "материал", "текущий", "не_прошёл", "предложено", "причина",
               "вердикт"],
              [[i + 1, r["картинка"], " ".join(frames[r["картинка"]]), r["мест"], r["материал"], r["текущий"],
                r["текущий_не_прошёл"], r["выбор"], r["причина"], ""] for i, r in enumerate(tail)])
    per = 40
    for i in range(0, len(tail), per):
        build(tail[i:i + per], os.path.join(a.out, "sheets", "detail", "tail_%02d.png" % (i // per + 1)),
              "ХВОСТ %d-%d из %d картинок (по весу мест)" % (i + 1, min(i + per, len(tail)), len(tail)))
    # выборка автоматических решений: по 8 самых частых каждого способа и материала
    pick, seen = [], set()
    for meth in ("B2", "A", "CURRENT_HD"):
        for mat in ("smooth", "textured", "unclear"):
            k = 0
            for r in sel:
                if r["как"] == "auto" and r["выбор"] == meth and r["материал"] == mat and r["картинка"] not in seen:
                    seen.add(r["картинка"])
                    pick.append(r)
                    k += 1
                    if k >= 4:
                        break
    build(pick, os.path.join(a.out, "sheets", "auto_sample.png"), "АВТО: выборка по способу и материалу")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["measure", "select", "sheet"])
    ap.add_argument("--out", default="census/walls/final_select")
    a = ap.parse_args()
    os.chdir(ROOT)
    sys.stdout.reconfigure(encoding="utf-8")
    {"measure": do_measure, "select": do_select, "sheet": do_sheet}[a.cmd](a)


if __name__ == "__main__":
    main()
