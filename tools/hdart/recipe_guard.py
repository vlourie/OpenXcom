"""Проверка рецепта пола по классике ДО сборки: подходит ли кадру ковёр ground_seam --speckle и pixel_lines.

Две защиты по рецензиям b08/b09 (14.10):

  carpet  - ковёр (ground_seam --speckle) годится только однородному крапу. Повторяющийся или направленный
            рисунок, крупные пятна и сильный контраст классики ковёр стирает (R-298: NUKE1 16/17 - трещины плит,
            MUJUNGLE - камни с мхом, COMMERCE_MAG - доски).
  lines   - pixel_lines годится чётким швам и орнаменту. Мягкое свечение (плавная рампа без плоских участков)
            он превращает во вложенные контуры (R-325: SGR_COM 51, SGR_INT02 11, XB2BR 27, U_WALLCHURCH 23).
  ornament - любой ковёр ground_seam (и без --speckle) стирает орнамент: рамку, крест, кольцо, дыры, деталь
            над ромбом (R-332: ISLANDURBAN1 48, LINERSHIPA 95/19, SIETCHDOOM 68, LAM_FLOOR 13).

Итог проверки - ok, review (на просмотр: мера в полосе сомнения) или hold (нужен другой рецепт). Ни review,
ни hold не отклоняют картинку: группа просто не идёт в партию этим рецептом.

Пороги - край проверенных примеров (art/ground/queue, вердикты b01-b09) с полосой сомнения сверху: однородный
крап, принятый ковром, весь ниже порогов review; что выше - решает человек. Меры считаются по яркости классики
внутри ромба (индекс 0 прозрачен), палитра боя Пираток (water_build.palette).

    py -3.13 tools/hdart/recipe_guard.py NUKE1:16 SGR_COM:51 ...   # меры и вердикт обеих проверок
"""
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import water_build as wb          # noqa: E402

_PAL = None
_SETS = {}

# carpet: мера -> (порог review, порог hold). Край принятого крапа (MARS, MOUNTMOON, CAVEMEAT 13, CAVEAQUA 13/14/
# 18/19/20, REDDESERT, ICEKING_VILLAGE 61, BROWNHILL) - sd 22.7, big 0.18, coh 0.29, low2 0.28, clump 12.6, smooth 0.46
CARPET = {
    "sd":     (23.0, 28.0, "контраст яркости (СКО)"),
    "big":    (0.19, 0.25, "доля резких перепадов соседей"),
    "coh":    (0.30, 0.40, "направленность рисунка"),
    "low2":   (0.29, 0.33, "крупные пятна (доля СКО в размытии 2 пикс)"),
    "clump":  (13.0, 15.0, "тёмные или светлые выбросы слиты в линии и пятна"),
    "smooth": (0.47, 0.55, "плавная рампа, а не крап"),
}
# lines: свечение = плавные переходы (smooth) без плоских участков (flat) и без резких перепадов (big).
# Свечение b09: smooth 0.63-0.93, flat 0.32-0.44, big 0. Принятые pixel_lines без резких перепадов:
# smooth до 0.50 (одиночная ступень даёт ровно 0.5) при любом flat, выше - только с flat от 0.57
# (UAC_WALL02_V 15: 0.72/0.57, SPACESTATION_INT 26: 0.83/1.00); DAWNURBAN 80 (0.61) отсеян big 0.18.
GLOW_SMOOTH = (0.55, 0.60)          # review, hold
GLOW_FLAT_MAX = (0.52, 0.48)        # review, hold
GLOW_BIG_MAX = 0.05
# lines: ковёр шума - индекс лежит пятнами в 1-2 пикселя без периода (грунт, трава, щебень). pixel_lines ведёт
# каждую границу индекса линией, и шум становится камуфляжем (b11: FORESTSWAMP_WASTE 111-139, MOUNTTROP 4/5,
# SGR_CAVE 19/20, SIETCHDOOM 68 - med 1-2.5, per 0.17-0.52). Решётки при том же med - с периодом:
# CYBERWAREBITS 20 0.76, WAREBITS 20 0.77, XOPSDESERTRUINS 11 0.75, IDT_SNOWBARN 49 0.73, LIGHTNIN_R 25 0.97,
# доски SEAMSUNK1 35 0.68.
NOISE_MED_MAX = 2.5
NOISE_PER_MAX = 0.60
# carpet, любой ground_seam (и без --speckle): орнамент - не ковёр (R-332). Ковёр стирает рамку, крест,
# кольцо, дыры и деталь над ромбом: b12 ISLANDURBAN1 48 (крест и кольцо: линия 7.4/5.4, кромка 0.72),
# LINERSHIPA 95 и 19 (решётка и рамка с прозрачной серединой: дыры 0.41/0.34), SIETCHDOOM 68 (крест над
# ромбом: выступ 18 пикс), LAM_FLOOR 13 (шашечка в тёмной рамке: кромка 0.81). Принятые ковры (cp1, cp2,
# проверенные ground_seam): кромка до 0.42, линия до 4.9 (CAVEAQUA 19 - поэтому review линии с 5.5, а не
# впритык), выступ до 6, дыр 0.
# carpet, любой ground_seam: правильный рисунок крупнее пикселя - не ковёр (R-298, третий раз). cp1 14.10: борозды
# FORESTSWAMP_WASTE 111-114 (low2 0.35-0.49, ac1 0.53-0.85), ряды ростков 117/118 (0.42-0.57), сетка плит
# AGROUND 13 (0.33/0.47), борозды CUNTTRYROAD_LT 13 (0.31/0.95) - ковёр стёр рисунок. Проверенные ковры: low2 до
# 0.27 (CAVEMEAT 13), ac1 до 0.54 (CAVEAQUA 13); по очереди правило не задело ни одного verified, задело 22
# rejected и 8 keep_old. Ступени review нет: review тоже hold, а запаса до проверенных мало.
PATTERN = {
    "low2": (0.30, 0.30, "крупные пятна или борозды (доля СКО в размытии 2 пикс)"),
    "ac1":  (0.60, 0.60, "правильный рисунок (автокорреляция по сдвигу 3-10 пикс)"),
}
ORNAMENT = {
    "hole": (0.005, 0.02, "прозрачное внутри плитки (доля)"),
    "out":  (8, 12, "деталь над ромбом плитки (пикс)"),
    "rim":  (0.50, 0.60, "кромка индексами, которых нет в середине (рамка)"),
    "line": (5.5, 6.5, "прямая линия через плитку (z)"),
    "cross": (4.5, 4.5, "линии по обеим осям (крест, z)"),
}


def palette_y():
    global _PAL
    if _PAL is None:
        p = np.asarray(wb.palette()).reshape(-1, 3)[:256].astype(np.float64)
        _PAL = p @ np.array([0.299, 0.587, 0.114])
    return _PAL


def classic(g):
    s, f = g.split(":")
    if s not in _SETS:
        _SETS[s] = wb.read_set(s)
    return np.asarray(_SETS[s][int(f)])


def _erode(m):
    p = np.pad(m, 1)
    out = np.ones_like(m)
    for dy in (0, 1, 2):
        for dx in (0, 1, 2):
            out &= p[dy:dy + m.shape[0], dx:dx + m.shape[1]]
    return out


def _gauss(sig):
    r = int(np.ceil(3 * sig))
    x = np.arange(-r, r + 1, dtype=np.float64)
    k = np.exp(-x * x / (2 * sig * sig))
    return k / k.sum()


def _blur(y, m, sig):
    """Размытие по маске: вне ромба ничего не подмешивается."""
    k = _gauss(sig)
    r = len(k) // 2
    mm = m.astype(np.float64)

    def sep(a):
        p = np.pad(a, r)
        h = sum(k[i] * p[:, i:i + a.shape[1]] for i in range(len(k)))
        return sum(k[i] * h[i:i + a.shape[0], :] for i in range(len(k)))
    return sep(y * mm) / np.maximum(sep(mm), 1e-9)


def _components(mask):
    """Размеры 8-связных компонент маски (без scipy и cv2)."""
    seen = np.zeros_like(mask)
    H, W = mask.shape
    sizes = []
    for y0, x0 in zip(*np.nonzero(mask)):
        if seen[y0, x0]:
            continue
        st = [(y0, x0)]
        seen[y0, x0] = True
        n = 0
        while st:
            y, x = st.pop()
            n += 1
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    yy, xx = y + dy, x + dx
                    if 0 <= yy < H and 0 <= xx < W and mask[yy, xx] and not seen[yy, xx]:
                        seen[yy, xx] = True
                        st.append((yy, xx))
        sizes.append(n)
    return np.array(sizes, np.float64)


def _region_med(a):
    """Размер 4-связной области одного индекса, медиана по пикселям: у шума 1-2, у рисунка десятки."""
    m = a != 0
    seen = np.zeros_like(m)
    H, W = a.shape
    sizes = []
    for y0, x0 in zip(*np.nonzero(m)):
        if seen[y0, x0]:
            continue
        v = a[y0, x0]
        st = [(y0, x0)]
        seen[y0, x0] = True
        n = 0
        while st:
            y, x = st.pop()
            n += 1
            for dy, dx in ((0, 1), (1, 0), (0, -1), (-1, 0)):
                yy, xx = y + dy, x + dx
                if 0 <= yy < H and 0 <= xx < W and not seen[yy, xx] and a[yy, xx] == v:
                    seen[yy, xx] = True
                    st.append((yy, xx))
        sizes.append(n)
    s = np.array(sizes, np.int64)
    return float(np.median(np.repeat(s, s))) if s.size else 0.0


def _period(a):
    """Периодичность индексов: лучшая доля a[y,x] == a[y+dy,x+dx] по сдвигам до 8 (не ближе 2): решётка - высокая."""
    H, W = a.shape
    best = 0.0
    for dy in range(0, 9):
        for dx in range(-8, 9):
            if (dy == 0 and dx <= 0) or max(abs(dx), dy) < 2:
                continue
            x0, x1 = max(0, -dx), W - max(0, dx)
            A, B = a[0:H - dy, x0:x1], a[dy:H, x0 + dx:x1 + dx]
            ok = (A != 0) & (B != 0)
            if ok.sum() >= 100:
                best = max(best, float((A == B)[ok].mean()))
    return best


def _pairs(y, m, dy, dx):
    """Пары соседей со сдвигом (dy, dx), dy и dx - 0 или 1."""
    H, W = y.shape
    a, b = y[:H - dy, :W - dx], y[dy:, dx:]
    return a, b, m[:H - dy, :W - dx] & m[dy:, dx:]


def measures(a):
    """Меры кадра классики (массив индексов 40x32). Все - по яркости внутри ромба."""
    Y = palette_y()
    m0 = a != 0
    if m0.sum() < 30:
        return None
    m = _erode(m0)
    if m.sum() < 30:            # тонкий кадр (кромка, бордюр): мерить по всему непрозрачному
        m = m0
    y = Y[a]
    v = y[m]
    sd = float(v.std())
    low2 = float(_blur(y, m0, 2.0)[m].std() / sd) if sd >= 1 else 0.0
    d = np.concatenate([np.abs(p - q)[ok] for p, q, ok in (_pairs(y, m, 0, 1), _pairs(y, m, 1, 0))])
    flat = float((d < 0.5).mean())
    big = float((d >= 40).mean())
    clump = 0.0
    for sign in (-1, 1):
        ext = m & ((sign * (y - v.mean())) > max(sd, 1e-6))
        sz = _components(ext)
        if sz.size:
            clump = max(clump, float((sz ** 2).sum() / sz.sum()))
    # Собель 3x3 по размытой яркости (как cv2.Sobel с краем-отражением)
    b = np.pad(_blur(y, m0, 0.7), 1, mode="reflect")
    dx = b[:, 2:] - b[:, :-2]
    dy = b[2:, :] - b[:-2, :]
    gx = dx[:-2] + 2 * dx[1:-1] + dx[2:]
    gy = dy[:, :-2] + 2 * dy[:, 1:-1] + dy[:, 2:]
    jxx, jyy, jxy = (gx * gx)[m].sum(), (gy * gy)[m].sum(), (gx * gy)[m].sum()
    coh = float(np.sqrt((jxx - jyy) ** 2 + 4 * jxy ** 2) / max(jxx + jyy, 1e-9)) if sd >= 1 else 0.0
    # плавность: первая разность через пиксель против второй разности; на рампе вторая мала,
    # на шве, линии и крапе велика
    f1 = f2 = 0.0
    H, W = y.shape
    for c, l, r, ok in ((y[:, 1:-1], y[:, :-2], y[:, 2:], m0[:, 1:-1] & m0[:, :-2] & m0[:, 2:]),
                        (y[1:-1], y[:-2], y[2:], m0[1:-1] & m0[:-2] & m0[2:])):
        f1 += np.abs(r - l)[ok].sum() / 2
        f2 += np.abs(r - 2 * c + l)[ok].sum()
    smooth = float(f1 / max(f2, 1e-9))
    return {"sd": sd, "low2": low2, "flat": flat, "big": big, "clump": clump, "coh": coh, "smooth": smooth,
            "med": _region_med(a), "per": _period(a), "ac1": _acorr(y, m0, m), "n": int(m.sum())}


def _acorr(y, m0, m):
    """Правильный рисунок крупнее пикселя (борозды, ряды ростков, сетка плит): лучшая автокорреляция яркости,
    размытой на пиксель, по сдвигам 3..10 пикс (R-298)."""
    z = _blur(y, m0, 1.0)
    z = z - z[m].mean()
    var = float((z[m] ** 2).mean())
    if var < 1e-6:
        return 0.0
    H, W = z.shape
    best = 0.0
    for dy in range(0, 11):
        for dx in range(-10, 11):
            if (dy == 0 and dx <= 0) or dx * dx + dy * dy < 9:
                continue
            x0, x1 = max(0, -dx), W - max(0, dx)
            ok = m[0:H - dy, x0:x1] & m[dy:H, x0 + dx:x1 + dx]
            if ok.sum() >= 120:
                best = max(best, float((z[0:H - dy, x0:x1] * z[dy:H, x0 + dx:x1 + dx])[ok].mean() / var))
    return best


def _std_floor():
    """Силуэт полной плитки, как pixel_lines.STD_FLOOR (ряды 24-39, ширина 4..32..4)."""
    m = np.zeros((40, 32), bool)
    for yy in range(24, 40):
        k = yy - 23 if yy <= 31 else 40 - yy
        m[yy, 16 - 2 * k:16 + 2 * k] = True
    return m


def _line_z(y, m, sd):
    """Полоса в 1-2 пикселя по ряду, отличная от ОБЕИХ соседних полос той же ширины в одну сторону: max z
    (разность средних на корень числа пикселей полосы, в долях СКО кадра)."""
    best = 0.0
    for w in (1, 2):
        for r in range(w, y.shape[0] - 2 * w + 1):
            c, lo, hi = m[r:r + w], m[r - w:r], m[r + w:r + 2 * w]
            if c.sum() < 6 or lo.sum() < 6 or hi.sum() < 6:
                continue
            mc, ml, mh = y[r:r + w][c].mean(), y[r - w:r][lo].mean(), y[r + w:r + 2 * w][hi].mean()
            if (mc - ml) * (mc - mh) > 0:
                best = max(best, min(abs(mc - ml), abs(mc - mh)) * np.sqrt(c.sum()) / sd)
    return float(best)


def ornament(a):
    """Признаки орнамента на классике (R-332): дыры внутри плитки, деталь над ромбом, рамка чужими индексами,
    прямые линии через плитку по рядам и столбцам экрана."""
    op = a != 0
    S = _std_floor()
    # прозрачное, замкнутое непрозрачным и по ряду, и по столбцу (край плитки сдвинутой формы - не дыра)
    cs = np.maximum.accumulate(op, 1) & np.maximum.accumulate(op[:, ::-1], 1)[:, ::-1]
    rs = np.maximum.accumulate(op, 0) & np.maximum.accumulate(op[::-1], 0)[::-1]
    hole = float((~op & cs & rs).sum() / max(op.sum(), 1))
    out = int((op & ~S).sum())
    inner = _erode(_erode(_erode(op)))
    rim = op & ~_erode(_erode(op))
    rimf = 0.0
    if inner.any() and rim.any():
        cnt = np.bincount(a[inner], minlength=256) / inner.sum()
        rimf = float((cnt[a[rim]] < 0.03).mean())
    y = palette_y()[a]
    m = op & S
    sd = float(y[m].std()) if m.sum() >= 30 else 0.0
    lr = _line_z(y, m, sd) if sd >= 1 else 0.0
    lc = _line_z(y.T, m.T, sd) if sd >= 1 else 0.0
    return {"hole": hole, "out": out, "rim": rimf, "line": max(lr, lc), "cross": min(lr, lc)}


def ornament_verdict(o):
    """ok / review / hold: орнамент, который ковёр ground_seam сотрёт."""
    hold = [ORNAMENT[k][2] + " %.2f" % o[k] for k in ORNAMENT if o[k] >= ORNAMENT[k][1]]
    if hold:
        return "hold", hold
    rev = [ORNAMENT[k][2] + " %.2f" % o[k] for k in ORNAMENT if o[k] >= ORNAMENT[k][0]]
    return ("review", rev) if rev else ("ok", [])


def pattern_verdict(r):
    """ok / hold: правильный рисунок крупнее пикселя, который любой ковёр ground_seam сотрёт (R-298)."""
    hold = [PATTERN[k][2] + " %.2f" % r[k] for k in PATTERN if r[k] >= PATTERN[k][1]]
    return ("hold", hold) if hold else ("ok", [])


def carpet_verdict(r):
    """ok / review / hold для ковра ground_seam --speckle и список причин."""
    hold = [CARPET[k][2] + " %.2f" % r[k] for k in CARPET if r[k] >= CARPET[k][1]]
    if hold:
        return "hold", hold
    rev = [CARPET[k][2] + " %.2f" % r[k] for k in CARPET if r[k] >= CARPET[k][0]]
    return ("review", rev) if rev else ("ok", [])


def lines_verdict(r):
    """ok / review / hold для pixel_lines: свечение без плоских участков и резких перепадов, ковёр шума."""
    if r["med"] <= NOISE_MED_MAX and r["per"] < NOISE_PER_MAX:
        return "hold", ["ковёр шума: области индекса %.1f пикс, период %.2f - нужна фактура, не линии"
                        % (r["med"], r["per"])]
    if r["big"] > GLOW_BIG_MAX:
        return "ok", []
    why = "мягкое свечение: плавность %.2f, плоских пар %.2f" % (r["smooth"], r["flat"])
    if r["smooth"] >= GLOW_SMOOTH[1] and r["flat"] <= GLOW_FLAT_MAX[1]:
        return "hold", [why]
    if r["smooth"] >= GLOW_SMOOTH[0] and r["flat"] <= GLOW_FLAT_MAX[0]:
        return "review", [why]
    return "ok", []


def check(g, method):
    """Проверка группы под рецепт строки очереди. -> (вердикт, причины, меры). Рецепт без проверки - ok."""
    tool = (method or "pixel_lines").split()[0]
    if tool not in ("pixel_lines", "ground_seam"):
        return "ok", [], None
    a = classic(g)
    r = measures(a)
    if r is None:
        return "review", ["в ромбе меньше 30 пикселей - мерить нечем"], None
    if tool == "pixel_lines":
        v, why = lines_verdict(r)
        if v == "hold" and why[0].startswith("ковёр шума"):
            # мелкий рисунок в самой плитке, который ковёр сотрёт (R-332): рамка, дыры, крест - форма, а не шум.
            # Деталь над ромбом не в счёт (она не рисунок пола); свечение (R-325) проверяется дальше как обычно
            r.update(ornament(a))
            ow = [ORNAMENT[k][2] + " %.2f" % r[k] for k in ORNAMENT if k != "out" and r[k] >= ORNAMENT[k][1]]
            if ow:
                v2, why2 = lines_verdict(dict(r, med=NOISE_MED_MAX + 1))
                if v2 == "ok":
                    return "review", [why[0] + ", но орнамент (" + ", ".join(ow) + ")"], r
                return v2, why2, r
        return v, why, r
    # ковёр: орнамент (R-332) и правильный рисунок (R-298) проверяются всегда, однородность крапа - только
    # у --speckle
    r.update(ornament(a))
    vs = [ornament_verdict(r), pattern_verdict(r)]
    if "--speckle" in method.split():
        vs.append(carpet_verdict(r))
    rank = {"ok": 0, "review": 1, "hold": 2}
    worst = max((v for v, _w in vs), key=rank.get)
    return worst, [w for v, ws in vs if v == worst for w in ws], r


def note(kind, verdict, why):
    """Текст заметки очереди: без «;» и табуляций (judge и TSV)."""
    head = {"carpet": "проверка ковра", "lines": "проверка pixel_lines"}[kind]
    tail = {"hold": "нужен другой рецепт", "review": "на просмотр"}[verdict]
    return ("%s: %s - %s" % (head, tail, ", ".join(why))).replace(";", ",").replace("\t", " ")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    print("%-24s %5s %5s %5s %5s %5s %5s %5s  ковёр / pixel_lines" %
          ("группа", "sd", "low2", "flat", "big", "clump", "coh", "smooth"))
    for g in sys.argv[1:]:
        r = measures(classic(g))
        if r is None:
            print("%-24s мерить нечем" % g)
            continue
        o = ornament(classic(g))
        cv, cw = carpet_verdict(r)
        lv, lw = lines_verdict(r)
        ov, ow = ornament_verdict(o)
        print("%-24s %5.1f %5.2f %5.2f %5.2f %5.1f %5.2f %5.2f  %-6s / %-6s / орнамент %-6s %s" %
              (g, r["sd"], r["low2"], r["flat"], r["big"], r["clump"], r["coh"], r["smooth"], cv, lv, ov,
               "; ".join(cw + lw + ow)))


if __name__ == "__main__":
    main()
