"""DERIVE_RECOLOR_V3.3_DEV - стенд UNMIX_ELIGIBILITY_V1 (решение: специалист 03.10, передал Vitali в чате).

Архитектура: INTERPOLATED_MAP_V1 -> UNMIX_ELIGIBILITY_V1 -> unmix только у допущенных пар классов, иначе PRIOR.
PRIOR (интерполяционная доля следа, без unmix) - безопасная база; unmix - улучшение, которое обязано доказать
право примениться. Единица допуска - ПАРА классов основы (A, B) внутри одной пространственной области одного
кадра: перенос веса unmix раскладывается на потоки между местами следа (только внутри области), поток пары
применяется целиком или не применяется (R-195: решение на пиксель даёт соль).

Сигналы пары - только из самой пары основа/член, без правил по цвету, тёмности, набору или имени:
  ID  различимость: sep / max(sigma_perp, 1). sep - расстояние классов A и B в единицах шума unmix; sigma_perp -
      поперечный к линии A-B разброс HD-пикселей, где в следе есть оба класса (самокалибровка фактуры, в
      единицах шума; меньше 1 не берётся - не тише модели шума). sep = 0 (один цвет основы у двух классов) или
      меньше 8 пикселей для sigma_perp - пара неразличима, не допускается.
  ST  устойчивость: скачок переноса (ln(L+5) / 0.15, a / 8, b / 8 - единицы порогов ворот пятен) при сдвиге
      исходного цвета на 1 sigma_eff вдоль A-B; медиана по пикселям пары. Не глобальный порог усиления:
      расхождение переносов умножено на свою фактуру пары и поделено на своё разделение классов.
  CY  цикл: вывод с потоком только этой пары -> разложение в цветах члена (та же модель шума, яркость вывода)
      -> веса w'; невязка |w' - w| / 2. CY = средняя невязка пары минус средняя невязка PRIOR на тех же
      пикселях: обратный путь обязан быть не хуже PRIOR больше чем на порог.
Пара допускается, если ID >= T_id, ST <= T_J, CY <= T_c.

Порядок: spec (заморозить сетку, выбор, стоп-условия, sha кода; один раз) -> run (один раз). Набор подтверждения
15 пар не читается. Сетка выбирается ТОЛЬКО по 23 DEV-парам (dev_spec_v3.json); R01/R02/R12 - стоп-условие для
выбранной точки, в выборе не участвуют и для других точек сетки не считаются.

    py -3.13 tools/hdart/derive_recolor_v33_dev.py spec|smoke|run|check
"""
import hashlib
import itertools
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import derive_recolor_acceptance_v2 as V2  # noqa: E402
import derive_recolor_acceptance_v3 as A3  # noqa: E402
import derive_recolor_acceptance_v31 as A31  # noqa: E402
import derive_recolor_acceptance_v32 as M  # noqa: E402
import derive_recolor_v3 as D3  # noqa: E402
import derive_recolor_v31 as D31  # noqa: E402

ENC = "utf-8-sig"
PROFILE = "DERIVE_RECOLOR_V3_3_DEV"
OUT = "art/objects/generation/probes/derive-recolor-v33-dev"
SELF = "tools/hdart/derive_recolor_v33_dev.py"
DEV_SPEC = M.DEV + "/dev_spec_v3.json"
DECISION = ("специалист 03.10, передал Vitali в чате: V3.2 = FAIL окончательно; c = 0.75 не трогать; "
            "разрешён DERIVE_RECOLOR_V3.3_DEV - INTERPOLATED_MAP_V1 -> UNMIX_ELIGIBILITY_V1 -> unmix только "
            "допущенным, иначе PRIOR; сигналы - local transform stability и cycle consistency из самой пары; "
            "порогов по R01/R02/R12 не подбирать; confirmation 15 закрыт")

EPS = 0.01          # пиксель «с unmix», если перенос веса |w - pri| / 2 больше
FLOW_MIN = 1e-6     # поток пары на пикселе существует
SIG_FLOOR = 1.0     # sigma_perp не ниже модели шума unmix
POOL_MIN = 8        # пикселей с обоими классами в следе для sigma_perp
DELTA = 0.05        # шаг центральной разности по весу
TLN, TAB = 0.15, 8.0
GRID = {"T_id": [2.0, 3.0, 4.0], "T_J": [0.5, 0.75, 1.0, 1.5], "T_c": [0.05, 0.1, 0.2]}
COVER_MIN = 0.5     # доля пикселей с unmix, допущенных на формах дизера (SYN_DITHER, SD)
R_CASES = ("R01", "R02", "R12")
BUCKET = {"dither": "DITHER", "textured": "TEXTURED", "divergent": "DIVERGENT", "flat": "FLAT",
          "local": "BOUNDARY", "dark": "DARK", "general": "GENERAL"}


class Stop(Exception):
    pass


def rel(p):
    return os.path.join(A3.ROOT, p)


def fsha(p):
    return hashlib.sha256(open(rel(p), "rb").read()).hexdigest()


def jdump(obj, p):
    with open(rel(p), "w", encoding=ENC) as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


# ---------- INTERPOLATED_MAP_V1 до весов (копия derive_recolor_v31.transfer) ----------

def noise_scale(sig_n, sig_g, y):
    return np.stack([1.0 / np.sqrt(sig_n ** 2 + (sig_g * y) ** 2), np.full(y.shape, 1.0 / sig_n),
                     np.full(y.shape, 1.0 / sig_n)], -1)


def region_unmix(hs, Rs, PR, valid, G):
    tot = np.maximum(PR.sum(-1), 1e-300)
    w = np.zeros(PR.shape)
    for s in range(4):
        first = valid[..., s] & ~((G[..., :s] == G[..., s:s + 1]) & valid[..., :s]).any(-1)
        if not first.any():
            continue
        inr = valid & (G == G[..., s:s + 1]) & first[..., None]
        mass = (PR * inr).sum(-1)
        pri = PR * inr / np.maximum(mass, 1e-300)[..., None]
        w += (mass / tot)[..., None] * D31.unmix(hs, Rs, pri, inr, D31.PRIOR_W)
    return w


def weights(hd, ob_o, ot):
    m = (ob_o[..., 3] > 0) & (ot[..., 3] > 0)
    h, w = m.shape
    cls, bcode, pb, pt = D31.classes(ob_o, ot, m)
    n = len(bcode)
    sn, sg, _npx = D31.class_spread(hd, cls, n)
    sig_n = max(D31.SIGMA_MIN, float(np.nanmedian(sn))) if np.isfinite(sn).any() else D31.SIGMA_FALLBACK
    sig_g = max(D31.SHADE_MIN, float(np.nanmedian(sg))) if np.isfinite(sg).any() else D31.SHADE_FALLBACK
    idx = D3._spread_index(m)
    cls_flat = cls.reshape(-1)
    H, W = hd.shape[:2]
    Y, X = np.mgrid[0:H, 0:W]
    u, v = (X + 0.5) / 4 - 0.5, (Y + 0.5) / 4 - 0.5
    x0, y0 = np.floor(u).astype(np.int64), np.floor(v).astype(np.int64)
    fx, fy = u - x0, v - y0
    C, PR = [], []
    for dy, dx in ((0, 0), (0, 1), (1, 0), (1, 1)):
        yy, xx = np.clip(y0 + dy, 0, h - 1), np.clip(x0 + dx, 0, w - 1)
        loc = idx[yy, xx]
        c = np.where(loc >= 0, cls_flat[np.maximum(loc, 0)], -1)
        C.append(c)
        PR.append(np.where(c >= 0, (fy if dy else 1 - fy) * (fx if dx else 1 - fx), 0.0))
    C, PR = np.stack(C, -1), np.stack(PR, -1)
    for i, j in ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)):
        same = (C[..., i] >= 0) & (C[..., i] == C[..., j])
        PR[..., i] = np.where(same, PR[..., i] + PR[..., j], PR[..., i])
        C[..., j] = np.where(same, -1, C[..., j])
        PR[..., j] = np.where(same, 0.0, PR[..., j])
    valid = C >= 0
    Cc = np.maximum(C, 0)
    hcol = np.stack(D3.ycc(hd[..., :3].astype(np.float64)), -1)
    sc = noise_scale(sig_n, sig_g, hcol[..., 0])
    grp = D31.regions(cls, bcode, n)
    G = np.where(valid, grp[Cc], -1)
    hs, Rs = hcol * sc, pb[Cc] * sc[..., None, :]
    wgt = region_unmix(hs, Rs, PR, valid, G)
    pri = PR / np.maximum(PR.sum(-1, keepdims=True), 1e-300)
    return dict(bcode=bcode, pb=pb, pt=pt, Cc=Cc, PR=PR, valid=valid, G=G, wgt=wgt, pri=pri, hcol=hcol,
                sc=sc, hs=hs, Rs=Rs, sig_n=sig_n, sig_g=sig_g)


def colour(d, w, sel=None):
    """Шаг цвета V3.1 без округления: Y, Cb, Cr. sel - маска пикселей (тогда w уже по ней)."""
    g = (lambda a: a) if sel is None else (lambda a: a[sel])
    pb, pt, Cc, hcol, valid = d["pb"], d["pt"], g(d["Cc"]), g(d["hcol"]), g(d["valid"])
    have = valid.any(-1)
    beff = (w[..., None] * pb[Cc]).sum(-2)
    teff = (w[..., None] * pt[Cc]).sum(-2)
    k = np.where(have, (teff[..., 0] + 2.0) / (beff[..., 0] + 2.0), 1.0)
    dcb = np.where(have, teff[..., 1] - beff[..., 1], 0.0)
    dcr = np.where(have, teff[..., 2] - beff[..., 2], 0.0)
    wch = np.where(have, np.clip((np.hypot(dcb, dcr) - D31.CHROMA_W0) / D31.CHROMA_W1, 0.0, 1.0), 0.0)
    tcb, tcr = np.where(have, teff[..., 1], hcol[..., 1]), np.where(have, teff[..., 2], hcol[..., 2])
    cb2 = (1 - wch) * (hcol[..., 1] + dcb) + wch * tcb
    cr2 = (1 - wch) * (hcol[..., 2] + dcr) + wch * tcr
    return np.stack([hcol[..., 0] * k, cb2, cr2], -1)


def colorize(hd, d, w):
    o = colour(d, w)
    out = hd.copy()
    out[..., :3] = np.round(np.clip(D3.rgb(o[..., 0], o[..., 1], o[..., 2]), 0, 255)).astype(np.uint8)
    out[out[..., 3] == 0, :3] = 0
    return out


def lab_of(ycc):
    return V2.lab(np.clip(D3.rgb(ycc[..., 0], ycc[..., 1], ycc[..., 2]), 0, 255))


def gate_units(l1, l0):
    return np.maximum.reduce([np.abs(np.log((l1[..., 0] + 5) / (l0[..., 0] + 5))) / TLN,
                              np.abs(l1[..., 1] - l0[..., 1]) / TAB, np.abs(l1[..., 2] - l0[..., 2]) / TAB])


# ---------- UNMIX_ELIGIBILITY_V1 ----------

def pair_flows(d):
    """Перенос unmix - потоки между местами следа ВНУТРИ области: F(i, j) = gain_i loss_j / gain области i.
    Сумма потоков = wgt - pri точно; часть потоков оставляет веса >= 0, сумму 1 и массу каждой области.
    Возвращает {(a, b): (part, mass)} по парам классов a < b."""
    dw = d["wgt"] - d["pri"]
    gain, loss = np.clip(dw, 0, None), np.clip(-dw, 0, None)
    G, Cc, valid = d["G"], d["Cc"], d["valid"]
    same = (G[..., :, None] == G[..., None, :]) & valid[..., :, None] & valid[..., None, :]
    rg = (gain[..., None, :] * same).sum(-1)
    pairs = {}
    for i in range(4):
        for j in range(4):
            if i == j:
                continue
            f = np.where(same[..., i, j], gain[..., i] * loss[..., j] / np.maximum(rg[..., i], 1e-300), 0.0)
            on = f > FLOW_MIN
            if not on.any():
                continue
            ci, cj = Cc[..., i], Cc[..., j]
            lo, hi = np.minimum(ci, cj), np.maximum(ci, cj)
            for a, b in set(zip(lo[on].tolist(), hi[on].tolist())):
                m = on & (lo == a) & (hi == b)
                part, mass = pairs.setdefault((a, b), (np.zeros_like(dw), np.zeros(dw.shape[:-1])))
                fm = np.where(m, f, 0.0)
                part[..., i] += fm
                part[..., j] -= fm
                mass += fm
    return pairs


def cycle_residual(d, w, sel):
    """Вывод -> разложение в цветах члена -> веса w'; |w' - w| / 2 на пикселях sel."""
    o = colour(d, w, sel)
    sct = noise_scale(d["sig_n"], d["sig_g"], o[..., 0])
    Cc = d["Cc"][sel]
    w2 = region_unmix(o * sct, d["pt"][Cc] * sct[..., None, :], d["PR"][sel], d["valid"][sel], d["G"][sel])
    return np.abs(w2 - w).sum(-1) / 2


def signals(d, op):
    """Сигналы каждой пары: ID, ST, CY, причина неразличимости."""
    pairs = pair_flows(d)
    hs, Rs, Cc, valid = d["hs"], d["Rs"], d["Cc"], d["valid"]
    out = {}
    for (a, b), (part, mass) in pairs.items():
        att = (mass > EPS) & op
        if not att.any():
            att = (mass > FLOW_MIN) & op
        if not att.any():
            continue
        ina, inb = (Cc == a) & valid, (Cc == b) & valid
        both = ina.any(-1) & inb.any(-1) & op
        Ra = (Rs * ina[..., None]).sum(-2)
        Rb = (Rs * inb[..., None]).sum(-2)
        ax = Rb - Ra
        sep = np.linalg.norm(ax, axis=-1)
        r = {"px": int(att.sum()), "mass": float(mass[att].sum()), "pool": int(both.sum())}
        sep_m = float(np.median(sep[att]))
        r["sep"] = sep_m
        if sep_m <= 1e-9:
            r.update(reason="same_base")
            out[(a, b)] = (part, mass, r)
            continue
        if both.sum() < POOL_MIN:
            r.update(reason="few_px")
            out[(a, b)] = (part, mass, r)
            continue
        u = ax / np.maximum(sep, 1e-9)[..., None]
        v = hs - Ra
        perp2 = ((v - (v * u).sum(-1)[..., None] * u) ** 2).sum(-1)
        sig = float(np.sqrt(np.median(perp2[both]) / (2 * np.log(2))))
        sig_eff = max(sig, SIG_FLOOR)
        r["sigma_perp"], r["ID"] = sig, sep_m / sig_eff
        # ST: d вывод / d вес вдоль A -> B (центральная разность без обрезки), на сдвиг 1 sigma_eff источника
        wq = d["wgt"][att]
        e = np.zeros_like(wq)
        sa, sb = np.argmax(ina[att], -1), np.argmax(inb[att], -1)
        rows = np.arange(len(wq))
        e[rows, sb] += 1.0
        e[rows, sa] -= 1.0
        l0 = lab_of(colour(d, wq - DELTA / 2 * e, att))
        l1 = lab_of(colour(d, wq + DELTA / 2 * e, att))
        J = gate_units(l1, l0) / DELTA * sig_eff / np.maximum(sep[att], 1e-9)
        r["ST"] = float(np.median(J))
        # CY: цикл с потоком только этой пары против PRIOR
        pri = d["pri"][att]
        cu = cycle_residual(d, pri + part[att], att)
        cp = cycle_residual(d, pri, att)
        r["cyc_pair"], r["cyc_prior"] = float(cu.mean()), float(cp.mean())
        r["CY"] = r["cyc_pair"] - r["cyc_prior"]
        r["reason"] = None
        out[(a, b)] = (part, mass, r)
    return out


def eligible(r, t):
    return r["reason"] is None and r["ID"] >= t["T_id"] and r["ST"] <= t["T_J"] and r["CY"] <= t["T_c"]


def compose(d, sig, keys):
    w = d["pri"].copy()
    acc = np.zeros(w.shape[:-1])
    for k in keys:
        part, mass, _r = sig[k]
        w += part
        acc += mass
    return w, acc


def coverage(d, sig, keys, op):
    dwm = np.abs(d["wgt"] - d["pri"]).sum(-1) / 2
    att = (dwm > EPS) & op
    _w, acc = compose(d, {k: sig[k] for k in keys}, keys)
    ok = att & (acc >= 0.5 * dwm)
    return {"attempted_px": int(att.sum()), "accepted_px": int(ok.sum()), "rejected_px": int((att & ~ok).sum()),
            "attempted_mass": round(float(dwm[att].sum()), 3), "accepted_mass": round(float(acc[att].sum()), 3)}


def combos():
    return [dict(zip(GRID, v)) for v in itertools.product(*GRID.values())]


def cname(t):
    return "id%g_J%g_c%g" % (t["T_id"], t["T_J"], t["T_c"])


# ---------- spec ----------

def spec_body():
    return {
        "profile": PROFILE, "decision": DECISION, "code_sha256": fsha(SELF),
        "inputs": {"dev_spec_v3": DEV_SPEC, "dev_spec_v3_sha256": fsha(DEV_SPEC),
                   "acceptance_v32_sha256": fsha(M.SELF), "derive_recolor_v31_sha256": fsha(M.STAGE_B_BASE),
                   "derive_recolor_v3_sha256": fsha(M.STAGE_A), "confirmation_15": "НЕ ЧИТАЕТСЯ"},
        "architecture": "INTERPOLATED_MAP_V1 -> UNMIX_ELIGIBILITY_V1 -> допущенная пара: unmix (поток пары целиком), "
                        "иначе PRIOR",
        "unit": "пара классов основы (A, B) внутри одной пространственной области одного кадра",
        "signals": {"ID": "sep / max(sigma_perp, %g); sep = 0 -> same_base, пикселей с обоими классами < %d -> few_px"
                          % (SIG_FLOOR, POOL_MIN),
                    "ST": "медиана по пикселям пары: скачок переноса в порогах ворот (ln(L+5)/%g, a/%g, b/%g) на сдвиг "
                          "1 sigma_eff источника вдоль A-B (центральная разность, шаг %g)" % (TLN, TAB, TAB, DELTA),
                    "CY": "средняя невязка цикла (вывод с потоком пары -> разложение в цветах члена) минус та же у "
                          "PRIOR"},
        "rule": "eligible = ID >= T_id и ST <= T_J и CY <= T_c",
        "constants": {"EPS": EPS, "FLOW_MIN": FLOW_MIN, "SIG_FLOOR": SIG_FLOOR, "POOL_MIN": POOL_MIN, "DELTA": DELTA},
        "grid": GRID,
        "dev_gates": {"STRUCT": 0, "CAUSAL_SEAM": 0, "NEW_ARTIFACT": 0,
                      "DITHER": "среднее ухудшение ΔE против V3.1 <= %g, каждый случай <= %g (формы %s)"
                                % (M.DITHER_MEAN, M.DITHER_CASE, ", ".join(M.DITHER_FORMS)),
                      "COVERAGE": "на формах дизера допущено >= %g пикселей с unmix; всего допущено > 0" % COVER_MIN},
        "selection": "среди точек сетки, прошедших все dev_gates на 23 DEV-парах, - с наименьшим числом допущенных "
                     "пикселей по всем DEV-случаям (минимально достаточный unmix: PRIOR - база, unmix - по праву); "
                     "при равенстве - строже: больше T_id, меньше T_J, меньше T_c",
        "stop_conditions": {"no_candidate": "ни одна точка не прошла dev_gates -> FAIL_NO_CANDIDATE",
                            "R": "выбранная точка: unintended_local_artifacts R01 = R02 = R12 = 0, иначе FAIL_R; "
                                 "R считаются только для выбранной точки",
                            "after": "провал -> без перенастройки; по решению специалиста следующий шаг - отказ от "
                                     "unmix как универсального метода"},
        "metrics": "attempted / accepted / rejected пикселей unmix (пиксель допущен, если допущенный поток >= половины "
                   "его переноса) по корзинам %s" % ", ".join(sorted(set(BUCKET.values()))),
        "controls": ["V3.1-харнесс = derive_recolor_v31 побайтно", "все пары -> вывод V3.1 (округление: <= 1 на канал)",
                     "ни одной пары -> PRIOR побайтно", "мера утечки и счёт пятен - контроли acceptance_v32"],
        "forbidden": ["правила по тёмности, цвету, набору, имени ассета", "пороги по R01/R02/R12",
                      "C2/C3/C6, S01-S09, R-случаи для выбора", "чтение набора подтверждения"],
    }


def do_spec():
    p = OUT + "/dev_spec_v33.json"
    if os.path.exists(rel(p)):
        raise SystemExit("spec уже заморожен")
    if fsha(DEV_SPEC) != M.DEV_SPEC_V3_SHA:
        raise SystemExit("dev_spec_v3.json не тот")
    os.makedirs(rel(OUT), exist_ok=True)
    body = spec_body()
    body["spec_sha256"] = V2.jsha({k: v for k, v in body.items()})
    jdump(body, p)
    print("spec", body["spec_sha256"][:12], "код", body["code_sha256"][:12])


def load_spec():
    sp = A3.load_json(rel(OUT + "/dev_spec_v33.json"))
    now = spec_body()
    for k in ("code_sha256", "inputs", "grid", "constants", "selection", "dev_gates", "rule"):
        if sp[k] != now[k]:
            raise SystemExit("spec не совпадает с кодом/входами: " + k)
    return sp


# ---------- прогон ----------

def prepare(hd, ob, ot, route):
    der31, ch = D31.derive(hd, ob, ot, route)
    if der31 is None:
        raise Stop("отказ Stage A")
    g = ch["geometry_transform"]
    hdo, obo = D3.geo(hd, g), D3.geo(ob, g)
    d = weights(hdo, obo, ot)
    if not (colorize(hdo, d, d["wgt"]) == der31).all():
        raise Stop("V3.1 харнесса не равен derive_recolor_v31")
    op = hdo[..., 3] > 0
    sig = signals(d, op)
    allw, _ = compose(d, sig, list(sig))
    dev = np.abs(colorize(hdo, d, allw).astype(int) - der31.astype(int)).max()
    if dev > 1:
        raise Stop("все пары не дают V3.1: %d" % dev)
    if not (colorize(hdo, d, d["pri"]) == colorize(hdo, d, compose(d, sig, [])[0])).all():
        raise Stop("ни одной пары не даёт PRIOR")
    return g, hdo, obo, d, op, sig, der31


def measure(out, hdo, obo, ot, truth, tstats, lk):
    gt, _ = A3.gates3(out, hdo, obo, ot)
    v = {"struct": int(sum(gt[k] for k in M.STRUCT)), "art": int(gt["unintended_local_artifacts"])}
    if truth is not None:
        cs = M.art_stats(out, hdo, obo, ot)
        if len(M.flagged(cs)) != gt["unintended_local_artifacts"]:
            raise Stop("счёт классов кандидата не равен воротам")
        new, _over = M.new_artifacts(cs, tstats)
        v["new_art"], v["new_art_list"] = len(new), new
        v["de"] = M.de_mean(out, truth)
    if lk is not None:
        v["seam_leak"] = M.seam(out, lk)[0]
    return v


def dev_cases():
    sp3 = A3.load_json(rel(DEV_SPEC))
    for pair in sp3["dev"]:
        for form, ob, ot, hd, truth in M.forms(pair):
            yield pair, form, ob, ot, hd, truth


def gate_eval(rows, nm):
    h = {}
    bad = [r["case"] for r in rows if r["v"][nm]["struct"]]
    h["STRUCT"] = not bad
    h["CAUSAL_SEAM"] = all(r["v"][nm].get("seam_leak", 0) == 0 for r in rows)
    na = [r["case"] for r in rows if r["v"][nm].get("new_art")]
    h["NEW_ARTIFACT"] = not na
    dd = [r["v"][nm]["de"] - r["de_v31"] for r in rows if r["form"] in M.DITHER_FORMS]
    mean = sum(dd) / len(dd)
    h["DITHER"] = mean <= M.DITHER_MEAN + 1e-12 and max(dd) <= M.DITHER_CASE + 1e-12
    dat = sum(r["cov"][nm]["attempted_px"] for r in rows if r["form"] in M.DITHER_FORMS)
    dac = sum(r["cov"][nm]["accepted_px"] for r in rows if r["form"] in M.DITHER_FORMS)
    tot = sum(r["cov"][nm]["accepted_px"] for r in rows)
    h["COVERAGE"] = dat > 0 and dac >= COVER_MIN * dat and tot > 0
    return h, {"dither_mean": round(mean, 4), "dither_max": round(max(dd), 4), "new_art_cases": na,
               "struct_cases": bad, "dither_cover": round(dac / max(dat, 1), 4), "accepted_total": tot}


def do_run(smoke=False):
    sp = None if smoke else load_spec()
    res_p = OUT + "/dev_v33_results.json"
    if not smoke and os.path.exists(rel(res_p)):
        raise SystemExit("прогон уже сделан - повтор запрещён")
    grid = combos()
    rows = []
    t0 = time.time()
    for pair, form, ob, ot, hd, truth in dev_cases():
        cid = "%s>%s/%s" % (pair["base"], pair["member"], form)
        g, hdo, obo, d, op, sig, der31 = prepare(hd, ob, ot, "recolor")
        lk = None
        if form == "SYN" and pair["category"] == "local":
            lk = M.seam_setup(obo, ot)
            tl = M.seam(truth, lk)[0]
            if tl != 0:
                raise Stop("контроль утечки: правда %d в %s" % (tl, cid))
        tstats = None
        if truth is not None:
            tstats = M.art_stats(truth, hdo, obo, ot)
            if len(M.flagged(tstats)) != A3.gates3(truth, hdo, obo, ot)[0]["unintended_local_artifacts"]:
                raise Stop("счёт классов правды не равен воротам: " + cid)
        row = {"case": cid, "category": pair["category"], "bucket": BUCKET[pair["category"]], "form": form,
               "geometry": g, "pairs": {"%d~%d" % k: v[2] for k, v in sig.items()}, "v": {}, "cov": {}, "elig": {}}
        row["de_v31"] = M.de_mean(der31, truth) if truth is not None else None
        cache = {}
        for t in grid:
            keys = tuple(sorted(k for k, v in sig.items() if eligible(v[2], t)))
            nm = cname(t)
            if keys not in cache:
                w, _ = compose(d, sig, keys)
                cache[keys] = (measure(colorize(hdo, d, w), hdo, obo, ot, truth, tstats, lk),
                               coverage(d, sig, keys, op))
            row["v"][nm], row["cov"][nm] = cache[keys]
            row["elig"][nm] = ["%d~%d" % k for k in keys]
        rows.append(row)
        print("%-46s пар %2d вариантов %2d (%.0fs)" % (cid, len(sig), len(cache), time.time() - t0), flush=True)
        if smoke:
            print("smoke: контроли пройдены")
            return
    table = []
    for t in grid:
        nm = cname(t)
        h, info = gate_eval(rows, nm)
        table.append({"point": nm, "t": t, "gates": h, "pass": all(h.values()), **info})
    cands = [x for x in table if x["pass"]]
    sel = None
    if cands:
        sel = min(cands, key=lambda x: (x["accepted_total"], -x["t"]["T_id"], x["t"]["T_J"], x["t"]["T_c"]))
    rres = None
    verdict = "FAIL_NO_CANDIDATE"
    if sel:
        sp31 = A3.load_json(A31.rel(A31.OUT + "/spec.json"))
        cases = {c["id"]: c for c in sp31["cases"]}
        rres = {}
        for k in R_CASES:
            c = cases[k]
            ob, ot, hd, _t = A3.inputs_of(c)
            g, hdo, obo, d, op, sig, der31 = prepare(hd, ob, ot, c["route"])
            keys = tuple(sorted(kk for kk, v in sig.items() if eligible(v[2], sel["t"])))
            w, _ = compose(d, sig, keys)
            out = colorize(hdo, d, w)
            out2 = colorize(hdo, d, compose(d, sig, keys)[0])
            gt, info = A3.gates3(out, hdo, obo, ot)
            rres[k] = {"art": int(gt["unintended_local_artifacts"]), "deterministic": bool((out == out2).all()),
                       "classes": [(a["base_rgb"], a["member_rgb"]) for a in info.get("artifacts", [])],
                       "cov": coverage(d, sig, keys, op), "pairs_total": len(sig), "pairs_eligible": len(keys)}
        verdict = "PASS" if all(v["art"] == 0 for v in rres.values()) else "FAIL_R"
    buckets = {}
    if sel:
        for r in rows:
            for key in (r["bucket"], "DITHER_FORMS" if r["form"] in M.DITHER_FORMS else None):
                if key is None:
                    continue
                b = buckets.setdefault(key, {"attempted_px": 0, "accepted_px": 0, "rejected_px": 0})
                for f in b:
                    b[f] += r["cov"][sel["point"]][f]
    res = {"profile": PROFILE, "spec_sha256": sp["spec_sha256"], "verdict": verdict,
           "selected": sel, "grid": table, "R": rres, "coverage_by_bucket": buckets,
           "cases": [{k: v for k, v in r.items()} for r in rows]}
    jdump(res, res_p)
    print("итог", verdict, "выбрано", sel["point"] if sel else None, "R", rres and {k: v["art"] for k, v in rres.items()})


def do_check():
    load_spec()
    print("spec и код совпадают")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        if cmd == "spec":
            do_spec()
        elif cmd == "smoke":
            do_run(smoke=True)
        elif cmd == "run":
            do_run()
        elif cmd == "check":
            do_check()
        else:
            raise SystemExit(__doc__)
    except Stop as e:
        print("ОСТАНОВКА:", e)
        sys.exit(2)
