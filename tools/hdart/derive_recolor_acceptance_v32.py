"""DERIVE_RECOLOR_ACCEPTANCE_V3.2 - приёмка tools/hdart/derive_recolor_v32.py (INTERPOLATED_MAP_V1 + ASL c = 0.75).

Решение: специалист 03.10, передал Vitali в чате - DEV3 PASS, ASL c = 0.75 утверждён, V3.2 freeze разрешён;
регрессия старых 27 - после заморозки; 15 пар подтверждения - один раз и только при полном PASS регрессии;
провал подтверждения - V3.2 = FAIL без перенастройки.

Порядок (каждый шаг проверяет, что предыдущий сделан и ничего не изменилось):
  devcheck  меры подтверждения, прогнанные на DEV-парах, обязаны повторить dev3_results.json (ASL_0.75 и V31):
            проверка переноса мер из стенда DEV3 в приёмку. Набор подтверждения не читается;
  spec      заморозить spec (один раз): код V3.2, V3.1, Stage A, правила регрессии и подтверждения, sha devcheck;
  regress   регрессия старых 27 случаев (случаи, входы, ворота, H1-H6 - как в приёмке V3.1, вывод - V3.2);
  confirm   подтверждение 15 пар - только при REGRESSION PASS, только один раз (повтор отказывает);
  sheet     лист member | V3.1 | V3.2 | truth: R05-R11 (R06 и R10 крупно) и случаи подтверждения -
            только при PASS регрессии и подтверждения;
  report    итог; check - spec и код не изменились.

Регрессия PASS = H1..H6 все PASS (специалист: «Что должно доказать V3.2 ... H1..H6 = PASS», H5 буквально
R01 = R02 = R12 = 0). Вердикты случаев по правилу V3 (VISUAL_FAIL, AWAITING_HUMAN) печатаются как в V3.1, но
регрессию не решают; R05-R11 - human validation после подтверждения.

Подтверждение - жёсткие условия DEV3 без изменений (dev_spec_v3.json): STRUCT = 0, причинная утечка через
шов = 0, новых пятен = 0, дизер: среднее ухудшение ΔE против V3.1 <= 0.25 и каждый случай <= 1.5,
детерминизм. Только numpy, без модели и видеокарты.

Команды (из корня репозитория):
    py -3.13 tools/hdart/derive_recolor_acceptance_v32.py devcheck|spec|regress|confirm|sheet|report|check
"""
import argparse
import hashlib
import json
import os
import sys
import time

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import derive_recolor_acceptance_v2 as V2  # noqa: E402
import derive_recolor_acceptance_v3 as A3  # noqa: E402
import derive_recolor_acceptance_v31 as A31  # noqa: E402
import derive_recolor_v3 as D3  # noqa: E402
import derive_recolor_v31 as D31  # noqa: E402
import derive_recolor_v32 as D32  # noqa: E402

ENC = "utf-8-sig"
ROOT = A3.ROOT
PROFILE = "DERIVE_RECOLOR_ACCEPTANCE_V3_2"
OUT = os.path.join(ROOT, "art", "objects", "generation", "probes", "derive-recolor-acceptance-v32")
DEV = "art/objects/generation/probes/derive-recolor-v32-dev"
V31_OUT = "art/objects/generation/probes/derive-recolor-acceptance-v31"
SELF = "tools/hdart/derive_recolor_acceptance_v32.py"
IMPL = "tools/hdart/derive_recolor_v32.py"
STAGE_B_BASE = "tools/hdart/derive_recolor_v31.py"
STAGE_A = "tools/hdart/derive_recolor_v3.py"
V31_SELF = "tools/hdart/derive_recolor_acceptance_v31.py"
DEV_SPEC_V3_SHA = "2d12803373941b93c31d66b31a68c83cbd31ff0dbc56e05c2fe1cea71c70d6de"
CONFIRM_SHA = "97c3621106f6f635ddf7ecc0186c356251df00364191b44155419e627ed88690"
DECISION = ("специалист 03.10, передал Vitali в чате: DEV3 PASS, selected ASL c = 0.75, selection methodology "
            "VALID; V3.2 freeze AUTHORIZED; old-27 regression AUTHORIZED AFTER FREEZE; 15-pair confirmation "
            "AUTHORIZED ONLY IF REGRESSION PASS; c после заморозки не меняется; neighbor regularization, GN и TCr "
            "global limiter REJECTED; PRIOR и V3.1 - только базы; R3.3 и GPU E2E BLOCKED")
STALE_AFTER_NOTE = ("dev_spec_v3.after содержит устаревшую формулировку, унаследованную от редакции 2 («TCr ...»). "
                    "Для выбора DEV3 она не действовала. Замороженная реализация: ASL c = 0.75")
STRUCT, VISUAL = A3.STRUCT, A3.VISUAL
FLOOR = A3.FLOOR
H3_CASES, H5_CASES, H5_GATE, TIE_DE, LEAK = A31.H3_CASES, A31.H5_CASES, A31.H5_GATE, A31.TIE_DE, A31.LEAK
# меры подтверждения - как dev_spec_v3.json
SEED = 20261004
SCALE = 4
LEAK_DIST = 2.0
LEAK_MIN_BASE_PX = 4
SIDE = 0.75
DIAG = ("EDGE", "MULTI", "AMBIG", "ONE")
THR = np.array([V2.ART_LN, V2.ART_AB, V2.ART_AB])
DITHER_MEAN, DITHER_CASE = 0.25, 1.5
DITHER_FORMS = ("SYN_DITHER", "SD")
SHEET_REAL = ("R05", "R06", "R07", "R08", "R09", "R10", "R11")
SHEET_ZOOM = ("R06", "R10")
BODY = ("profile", "decision", "implementation", "stage_b_base", "stage_a", "v31_dependency", "dev_dependency",
        "confirm_reserved", "note_stale_after", "regression", "confirmation", "sequence", "sheet", "forbidden")


def rel(p):
    return os.path.join(ROOT, p)


def fsha(p):
    return hashlib.sha256(open(rel(p), "rb").read()).hexdigest()


def save_png(a, *parts):
    p = os.path.join(OUT, *parts)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    Image.fromarray(a, "RGBA").save(p)
    return p


def dump(name, obj):
    os.makedirs(OUT, exist_ok=True)
    A3.save_json(os.path.join(OUT, name), obj)


def load(name):
    return A3.load_json(os.path.join(OUT, name))


# ---------- меры подтверждения (перенос из стенда DEV3) ----------

def code_rgb(c):
    return np.array([(c >> 16) & 255, (c >> 8) & 255, c & 255], np.uint8)


def dom_map(ob, ot):
    m = (ob[..., 3] > 0) & (ot[..., 3] > 0)
    cb, ct = D3.codes(ob)[m], D3.codes(ot)[m]
    f = {}
    for c in np.unique(cb):
        v, n = np.unique(ct[cb == c], return_counts=True)
        f[int(c)] = [int(x) for x in v[np.argsort(-n, kind="stable")]], [int(x) for x in np.sort(n)[::-1]]
    return f


def inject_dither(ob, ot):
    """SD: самый частый цвет основы, внутренние пиксели через один - самый частый соседний цвет."""
    m = ob[..., 3] > 0
    cb = np.where(m, D3.codes(ob), -1)
    v, n = np.unique(cb[m], return_counts=True)
    A = int(v[np.argmax(n)])
    P = np.pad(cb, 1, constant_values=-1)
    nb = [P[1 + dy:P.shape[0] - 1 + dy, 1 + dx:P.shape[1] - 1 + dx] for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0))]
    inner = (cb == A) & np.all([x == A for x in nb], 0)
    ne = np.concatenate([x[(cb == A) & (x >= 0) & (x != A)] for x in nb])
    if not len(ne) or not inner.any():
        return None
    vv, nn = np.unique(ne, return_counts=True)
    B = int(vv[np.argmax(nn)])
    yy, xx = np.mgrid[0:cb.shape[0], 0:cb.shape[1]]
    put = inner & ((yy + xx) % 2 == 0)
    f = dom_map(ob, ot)
    bd, td = ob.copy(), ot.copy()
    bd[put, :3] = code_rgb(B)
    td[put, :3] = code_rgb(f[B][0][0])
    return bd, td


def forms(pair):
    """Формы пары, как в DEV (dev_spec.json forms): REAL, SYN, SYN_DITHER (dither), SD (flat)."""
    base, mem, cat = pair["base"], pair["member"], pair["category"]
    ob, ot = V2.orig(base), V2.orig(mem)
    s, f = base.split(":")
    hd = A3.read_png(A3.rel("user/mods/hd/hd/TERRAIN/%s.PCK/%s.png" % (s, f)))
    yield "REAL", ob, ot, hd, None
    tex = V2.noise(ob.shape[0] * 4, ob.shape[1] * 4, seed=SEED)
    yield "SYN", ob, ot, V2.render(ob, "hard", tex), V2.render(ot, "hard", tex)
    if cat == "dither":
        yield "SYN_DITHER", ob, ot, V2.render(A3.mean2x2(ob), "hard", tex), V2.render(A3.mean2x2(ot), "hard", tex)
    if cat == "flat":
        r = inject_dither(ob, ot)
        if r is not None:
            bd, td = r
            yield "SD", bd, td, V2.render(A3.mean2x2(bd), "hard", tex), V2.render(A3.mean2x2(td), "hard", tex)


def seam_setup(obo, ot):
    """Пары категории local, форма SYN: у цвета основы с двумя цветами члена (второй >= 4 px) - области A/B и
    правды A/B; основа в ориентации цепочки (при IDENTITY - как в DEV)."""
    tex = V2.noise(ot.shape[0] * 4, ot.shape[1] * 4, seed=SEED)
    out = []
    m = (obo[..., 3] > 0) & (ot[..., 3] > 0)
    cb, ct = D3.codes(obo), D3.codes(ot)
    for c, (vals, cnts) in dom_map(obo, ot).items():
        if len(vals) < 2 or cnts[1] < LEAK_MIN_BASE_PX:
            continue
        a, b = vals[0], vals[1]
        ta_src, tb_src = ot.copy(), ot.copy()
        sel = m & (cb == c)
        ta_src[sel, :3] = code_rgb(a)
        tb_src[sel, :3] = code_rgb(b)
        out.append({"code": "#%06x" % c, "ra": sel & (ct == a), "rb": sel & (ct == b),
                    "ta": V2.render(ta_src, "hard", tex), "tb": V2.render(tb_src, "hard", tex)})
    s = SCALE
    h, w = m.shape
    Y, X = np.mgrid[0:h * s, 0:w * s]
    u, v = (X + 0.5) / s - 0.5, (Y + 0.5) / s - 0.5
    x0, y0 = np.floor(u).astype(np.int64), np.floor(v).astype(np.int64)
    fx, fy = u - x0, v - y0
    slots = []
    for dy, dx in ((0, 0), (0, 1), (1, 0), (1, 1)):
        yy, xx = y0 + dy, x0 + dx
        inb = (yy >= 0) & (yy < h) & (xx >= 0) & (xx < w)
        slots.append((inb, np.clip(yy, 0, h - 1), np.clip(xx, 0, w - 1), (fy if dy else 1 - fy) * (fx if dx else 1 - fx)))
    for e in out:
        inA = np.stack([inb & e["ra"][yc, xc] for inb, yc, xc, _ in slots])
        inB = np.stack([inb & e["rb"][yc, xc] for inb, yc, xc, _ in slots])
        inm = np.stack([inb & m[yc, xc] for inb, yc, xc, _ in slots])
        wts = np.stack([wt for *_, wt in slots])
        nA, nB = inA.sum(0), inB.sum(0)
        anyAB = (nA + nB) > 0
        allAB = (inA | inB).all(0)
        massA, massB = (wts * inA).sum(0), (wts * inB).sum(0)
        la, lb = V2.lab(e["ta"][..., :3]), V2.lab(e["tb"][..., :3])
        okd = (e["ta"][..., 3] >= V2.ALPHA_OPAQUE) & (np.linalg.norm(la - lb, axis=-1) > LEAK_DIST)
        causal = allAB & (nA > 0) & (nB > 0)
        e["sideA"] = causal & (massA >= SIDE) & okd
        e["sideB"] = causal & (massA <= 1 - SIDE) & okd
        e["major_a"] = massA >= massB
        e["diag"] = {"EDGE": anyAB & ~inm.all(0) & okd, "MULTI": anyAB & inm.all(0) & ~allAB & okd,
                     "AMBIG": causal & (massA > 1 - SIDE) & (massA < SIDE) & okd,
                     "ONE": allAB & ((nA == 0) | (nB == 0)) & okd}
        e["la"], e["lb"] = la, lb
    return out


def closer_other(der, e, sel_a, sel_b):
    ld = V2.lab(der[..., :3])
    ok = der[..., 3] >= V2.ALPHA_OPAQUE
    da = np.linalg.norm(ld - e["la"], axis=-1)
    db = np.linalg.norm(ld - e["lb"], axis=-1)
    a, b = sel_a & ok, sel_b & ok
    return int((a & (db < da)).sum() + (b & (da < db)).sum()), int(a.sum() + b.sum())


def seam(der, lk):
    leak = cnt = 0
    diag = {k: [0, 0] for k in DIAG}
    for e in lk:
        n, c = closer_other(der, e, e["sideA"], e["sideB"])
        leak, cnt = leak + n, cnt + c
        for k in DIAG:
            msk = e["diag"][k]
            n, c = closer_other(der, e, msk & e["major_a"], msk & ~e["major_a"])
            diag[k][0] += n
            diag[k][1] += c
    return leak, cnt, diag


def art_stats(der, hd, ob, ot):
    """Три величины ворот V2 unintended_local_artifacts по всем классам с >= ART_MIN_CELLS клетками."""
    sb, st = ob[..., 3] > 0, ot[..., 3] > 0
    _r, _m, min_d = V2.blocks(der)
    _r, _m, min_b = V2.blocks(hd)
    full = (min_d >= V2.ALPHA_OPAQUE) & (min_b >= V2.ALPHA_OPAQUE) & sb & st
    S, T = V2.code(ob), V2.code(ot)
    Ld, Lb = V2.lab(der[..., :3]), V2.lab(hd[..., :3])
    lnr = np.log((Ld[..., 0] + 5) / (Lb[..., 0] + 5))
    da, db = Ld[..., 1] - Lb[..., 1], Ld[..., 2] - Lb[..., 2]
    cell_in = np.zeros((4, 4), bool)
    cell_in[1:3, 1:3] = True
    opq = (der[..., 3] >= V2.ALPHA_OPAQUE) & (hd[..., 3] >= V2.ALPHA_OPAQUE) & np.tile(cell_in, S.shape)
    out = {}
    pairs = S * (1 << 24) + T
    for p in np.unique(pairs[full]):
        sel = full & (pairs == p)
        if sel.sum() < V2.ART_MIN_CELLS:
            continue
        px = np.repeat(np.repeat(sel, 4, 0), 4, 1) & opq
        out[int(p)] = np.array([float(lnr[px].std()), float(da[px].std()), float(db[px].std())])
    return out


def flagged(st):
    return {k for k, v in st.items() if (v > THR).any()}


def new_artifacts(cand, truth):
    new, over = [], []
    for k, sc in cand.items():
        st = truth.get(k, np.zeros(3))
        hard = (st <= THR) & (sc > THR)
        if hard.any():
            new.append({"class": "#%06x>#%06x" % (k >> 24, k & 0xFFFFFF), "axes": [int(i) for i in np.nonzero(hard)[0]],
                        "cand": [round(float(x), 3) for x in sc], "truth": [round(float(x), 3) for x in st]})
        o = st > THR
        if o.any():
            over.append(float(np.max((sc - st)[o])))
    return new, over


def de_mean(der, truth):
    m = truth[..., 3] > 0
    return float(np.linalg.norm(V2.lab(der[..., :3]) - V2.lab(truth[..., :3]), axis=-1)[m].mean())


def eval_pair(pair):
    """Все формы пары: V3.2 (дважды - детерминизм) и V3.1 (база дизера и справка). Возвращает строки случаев;
    поле measure_invalid - контроль меры не выполнен."""
    rows = []
    for form, ob, ot, hd, truth in forms(pair):
        cid = "%s>%s/%s" % (pair["base"], pair["member"], form)
        row = {"case": cid, "pair": [pair["base"], pair["member"]], "category": pair["category"], "form": form,
               "measure_invalid": []}
        der, ch = D32.derive(hd, ob, ot, "recolor")
        der2, ch2 = D32.derive(hd, ob, ot, "recolor")
        d31, ch31 = D31.derive(hd, ob, ot, "recolor")
        row["deterministic"] = bool(((der is None and der2 is None) or (der is not None and der2 is not None
                                                                          and (der == der2).all())) and ch == ch2)
        if der is None:
            row.update(status="REFUSED", struct=1, geometry=None)
            rows.append(row)
            continue
        g = ch["geometry_transform"]
        hdo, obo = D3.geo(hd, g), D3.geo(ob, g)
        gt, _ = A3.gates3(der, hdo, obo, ot)
        g31, _ = A3.gates3(d31, hdo, obo, ot)
        row.update(status="DERIVED", geometry=g, struct=int(sum(gt[k] for k in STRUCT)),
                   art=int(gt["unintended_local_artifacts"]), map=int(gt["wrong_palette_mapping"]),
                   art_v31=int(g31["unintended_local_artifacts"]), asl_limited_px=ch["transfer"]["asl_limited_px"])
        if truth is not None:
            ts = art_stats(truth, hdo, obo, ot)
            tg, _ = A3.gates3(truth, hdo, obo, ot)
            cs = art_stats(der, hdo, obo, ot)
            if len(flagged(ts)) != tg["unintended_local_artifacts"] or \
                    len(flagged(cs)) != gt["unintended_local_artifacts"]:
                row["measure_invalid"].append("счёт классов пятен не равен воротам")
            new, over = new_artifacts(cs, ts)
            row.update(truth_art=int(tg["unintended_local_artifacts"]), new_art=len(new), new_art_list=new,
                       over_truth_max=round(max(over), 3) if over else None,
                       de=round(de_mean(der, truth), 4), de_v31=round(de_mean(d31, truth), 4))
        if form == "SYN" and pair["category"] == "local":
            lk = seam_setup(obo, ot)
            tl, tc, tdiag = seam(truth, lk)
            pos = sum(closer_other(e["tb"], e, e["sideA"], np.zeros_like(e["sideA"]))[0] +
                      closer_other(e["ta"], e, np.zeros_like(e["sideB"]), e["sideB"])[0] for e in lk)
            if tl != 0 or pos != tc:
                row["measure_invalid"].append("контроль причинной утечки: правда %d, считается %d, положительный %d"
                                              % (tl, tc, pos))
            sl, _c, sdiag = seam(der, lk)
            sl31, _c31, sdiag31 = seam(d31, lk)
            row.update(seam_leak=sl, seam_counted=tc, seam_positive=pos, seam_truth=tl, seam_diag=sdiag,
                       seam_truth_diag=tdiag, seam_leak_v31=sl31, seam_diag_v31=sdiag31)
        row["_img"] = (der, d31, hdo, obo, ot, truth)
        rows.append(row)
    return rows


def strip(rows):
    return [{k: v for k, v in r.items() if k != "_img"} for r in rows]


def confirm_verdict(rows):
    """Жёсткие условия DEV3 на наборе случаев."""
    h = {}
    bad = [r["case"] for r in rows if r["status"] != "DERIVED" or r["struct"]]
    h["STRUCT"] = {"pass": not bad, "detail": "STRUCT > 0 / отказ Stage A: %s" % (", ".join(bad) or "нет")}
    sl = [(r["case"], r["seam_leak"], r["seam_counted"]) for r in rows if "seam_leak" in r]
    h["CAUSAL_SEAM"] = {"pass": all(x[1] == 0 for x in sl),
                        "detail": "; ".join("%s %d из %d" % x for x in sl) or "local-пар с причинным следом нет"}
    na = [(r["case"], r["new_art_list"]) for r in rows if r.get("new_art")]
    h["NEW_ARTIFACT"] = {"pass": not na, "detail": "; ".join("%s %s" % (c, ", ".join(
        "%s оси %s" % (x["class"], x["axes"]) for x in lst)) for c, lst in na) or "нет"}
    dd = [(r["case"], r["de"] - r["de_v31"]) for r in rows if r["form"] in DITHER_FORMS and r["status"] == "DERIVED"]
    mean = sum(x[1] for x in dd) / len(dd) if dd else 0.0
    over = [c for c, x in dd if x > DITHER_CASE + 1e-12]
    h["DITHER"] = {"pass": mean <= DITHER_MEAN + 1e-12 and not over,
                   "detail": "среднее %+.3f по %d случаям%s; %s" % (
                       mean, len(dd), "" if dd else " (нет случаев дизера)",
                       ", ".join("%s %+.3f" % x for x in dd) or "-")}
    nd = [r["case"] for r in rows if not r["deterministic"]]
    h["DETERMINISM"] = {"pass": not nd, "detail": "не детерминированы: %s" % (", ".join(nd) or "нет")}
    inv = [(r["case"], r["measure_invalid"]) for r in rows if r["measure_invalid"]]
    return h, inv


# ---------- devcheck ----------

def do_devcheck():
    if os.path.exists(os.path.join(OUT, "spec.json")):
        raise SystemExit("spec уже заморожен - devcheck вошёл в него и не повторяется")
    sp3p = rel(DEV + "/dev_spec_v3.json")
    if fsha(DEV + "/dev_spec_v3.json") != DEV_SPEC_V3_SHA:
        raise SystemExit("dev_spec_v3.json не тот, по которому выбран c")
    sp3 = A3.load_json(sp3p)
    R = A3.load_json(rel(DEV + "/dev3_results.json"))
    if R["spec_sha256"] != DEV_SPEC_V3_SHA:
        raise SystemExit("dev3_results.json от другого spec")
    ref = {c["case"]: c for c in R["cases"]}
    rows, diffs = [], []
    for pair in sp3["dev"]:
        for r in eval_pair(pair):
            rr = ref[r["case"]]
            a, b = rr["variants"]["ASL_0.75"], rr["variants"]["V31"]
            want = {"struct": a["struct"], "art": a["art"], "map": a["map"], "art_v31": b["art"],
                    "asl_limited_px": a["clamped"]}
            if "de" in a:
                want.update(new_art=a["new_art"], de=a["de"], de_v31=b["de"], over_truth_max=a["over_truth_max"])
            if "seam_leak" in a:
                want.update(seam_leak=a["seam_leak"], seam_diag=a["seam_diag"], seam_counted=rr["seam_counted"],
                            seam_positive=rr["seam_positive"], seam_leak_v31=b["seam_leak"], seam_diag_v31=b["seam_diag"])
            got = {k: r.get(k) for k in want}
            if got != want or r["measure_invalid"] or not r["deterministic"]:
                diffs.append({"case": r["case"], "want": want, "got": got, "invalid": r["measure_invalid"]})
            rows.append(r)
    h, inv = confirm_verdict(rows)
    res = {"profile": PROFILE, "what": "меры подтверждения на DEV-парах против dev3_results.json (ASL_0.75, V31)",
           "dev_spec_v3_sha256": DEV_SPEC_V3_SHA, "dev3_results_sha256": fsha(DEV + "/dev3_results.json"),
           "impl_sha256": fsha(IMPL), "self_sha256": fsha(SELF), "cases": len(rows), "diffs": diffs,
           "verdict_on_dev": {k: v["pass"] for k, v in h.items()}, "measure_invalid": inv,
           "ok": not diffs and not inv and all(v["pass"] for v in h.values()),
           "run_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    dump("devcheck.json", res)
    print("devcheck: случаев %d, расхождений %d, контроли мер %s, условия DEV3 на DEV %s -> %s" % (
        len(rows), len(diffs), "ok" if not inv else inv, res["verdict_on_dev"], "OK" if res["ok"] else "НЕ OK"))
    for d in diffs[:10]:
        print("  ", json.dumps(d, ensure_ascii=False)[:400])


# ---------- spec ----------

def impl_state():
    return json.loads(json.dumps({
        "module": IMPL, "sha256": fsha(IMPL), "version": D32.VERSION, "color_transform": D32.COLOR_TRANSFORM,
        "constants": {"ASL_C": D32.ASL_C, "ASL_TLN": D32.ASL_TLN, "ASL_TAB": D32.ASL_TAB},
        "formula": "w = доля + lambda (w_unmix - доля), lambda = min(1, c S / D), c = 0.75"}))


def stage_b_state():
    return {"module": STAGE_B_BASE, "sha256": fsha(STAGE_B_BASE), "version": D31.VERSION}


def stage_a_state():
    return {"module": STAGE_A, "sha256": fsha(STAGE_A), "version": D3.VERSION}


def v31_state():
    sp = A3.load_json(rel(V31_OUT + "/spec.json"))
    return {"module": V31_SELF, "sha256": fsha(V31_SELF), "spec_sha256": sp["sha256"],
            "results_file_sha256": fsha(V31_OUT + "/results.json"),
            "v3_pass_set": sp["v3_dependency"]["pass_set"], "v3_dependency_sha": V2.jsha(sp["v3_dependency"])}


def dev_state():
    dc = load("devcheck.json")
    return {"dev_spec_v3_sha256": fsha(DEV + "/dev_spec_v3.json"), "dev3_results_sha256": fsha(DEV + "/dev3_results.json"),
            "devcheck_sha256": hashlib.sha256(open(os.path.join(OUT, "devcheck.json"), "rb").read()).hexdigest(),
            "devcheck_ok": dc["ok"], "devcheck_impl_sha256": dc["impl_sha256"], "devcheck_self_sha256": dc["self_sha256"]}


def confirm_blob(p):
    """Содержимое без BOM: dev_spec.json хранит sha256 от conf_blob (v32dev_select.py), файл записан с BOM."""
    raw = open(rel(p), "rb").read()
    return raw[3:] if raw.startswith(b"\xef\xbb\xbf") else raw


def confirm_state():
    p = DEV + "/confirm_reserved.json"
    return {"file": p, "file_sha256": fsha(p), "sha256": hashlib.sha256(confirm_blob(p)).hexdigest(), "count": 15}


def spec_body():
    sp31 = A3.load_json(rel(V31_OUT + "/spec.json"))
    if stage_a_state()["sha256"] != sp31["stage_a"]["sha256"]:
        raise SystemExit("Stage A не тот, что в приёмке V3.1")
    if stage_b_state()["sha256"] != sp31["implementation"]["sha256"]:
        raise SystemExit("derive_recolor_v31.py не тот, что в приёмке V3.1")
    if fsha(DEV + "/dev_spec_v3.json") != DEV_SPEC_V3_SHA:
        raise SystemExit("dev_spec_v3.json изменён")
    cs = confirm_state()
    if cs["sha256"] != CONFIRM_SHA:
        raise SystemExit("confirm_reserved.json не тот, что отложен в dev_spec.json")
    dv = dev_state()
    if not dv["devcheck_ok"] or dv["devcheck_impl_sha256"] != fsha(IMPL) or dv["devcheck_self_sha256"] != fsha(SELF):
        raise SystemExit("devcheck не пройден или сделан на другом коде - сначала devcheck")
    return {
        "profile": PROFILE, "decision": DECISION, "implementation": impl_state(), "stage_b_base": stage_b_state(),
        "stage_a": stage_a_state(), "v31_dependency": v31_state(), "dev_dependency": dv, "confirm_reserved": cs,
        "note_stale_after": STALE_AFTER_NOTE,
        "regression": {
            "cases": [c["id"] for c in sp31["cases"]],
            "inputs": "те же, что в spec приёмки V3.1 (сверка sha входов каждого случая перед прогоном)",
            "hard_acceptance": {
                "H1": "every case: DERIVED and every STRUCTURAL gate 0",
                "H2": "every case in V3 pass_set %s has a V3.2 verdict starting with PASS" % sp31["v3_dependency"]["pass_set"],
                "H3": "cases %s: mean ΔE to truth V3.2 <= min(EXACT_MAP, SOFT_MAP support) + %s" % (", ".join(H3_CASES), TIE_DE),
                "H4": "cases %s: leakage V3.2 = 0, truth leakage = 0, SOFT_MAP leakage > 0 (leak_rule V3.1)" % ", ".join(LEAK),
                "H5": "cases %s: %s = 0 literally (R01 = 0, R02 = 0, R12 = 0)" % (", ".join(H5_CASES), H5_GATE),
                "H6": "every case: derive twice -> byte-identical output and equal chain"},
            "leak_rule": A31.LEAK_RULE, "leak_cases": LEAK,
            "pass_rule": ("REGRESSION PASS = H1..H6 все PASS. Вердикты случаев по правилу V3 (verdict3: VISUAL_FAIL, "
                          "AWAITING_HUMAN) печатаются как в V3.1, но регрессию не решают; AWAITING_HUMAN (R05-R11) - "
                          "human validation финального кандидата после подтверждения"),
            "fail_rule": "REGRESSION FAIL -> V3.2 FAIL, набор подтверждения не открывается",
            "diagnostics": "V3.1 (из той же реализации D31), EXACT_MAP и SOFT_MAP: ворота, ΔE, рябь, утечка; не решают"},
        "confirmation": {
            "set": "15 пар confirm_reserved.json (отобраны правилом dev_spec.json вместе с DEV, не открывались)",
            "forms": "как DEV: REAL; SYN (V2.render hard, tex seed %d); SYN_DITHER для dither; SD для flat" % SEED,
            "hard": {
                "STRUCT": "STRUCT = 0 на всех формах; отказ Stage A - провал",
                "CAUSAL_SEAM": "causal seam leakage = 0 суммарно (dev_spec_v3 measures.CAUSAL_SEAM; основа в "
                               "ориентации цепочки - при IDENTITY ровно как DEV)",
                "NEW_ARTIFACT": "новых пятен = 0: ось, где правда <= порога (0.15/8/8), а кандидат > порога",
                "DITHER": "формы SYN_DITHER и SD: среднее ΔE(V3.2) - ΔE(V3.1) <= +%s и каждый <= +%s" % (DITHER_MEAN, DITHER_CASE),
                "DETERMINISM": "derive дважды -> побайтно равно, цепочка равна"},
            "measure_controls": ("у правды причинная утечка 0; положительный контроль = все считаемые; счёт классов "
                                 "пятен = ворота. Не выполнено - CONFIRMATION INVALID_MEASURE (не PASS), решает специалист"),
            "pass_rule": "CONFIRMATION PASS = все пять PASS и контроли мер выполнены",
            "fail_rule": "любое не PASS -> V3.2 = FAIL; c и пороги не перенастраиваются на этих 15",
            "diagnostics": "REAL-пятна V3.2 против V3.1, диагностика следа EDGE/MULTI/AMBIG/ONE, оси выше порога"},
        "sequence": ["devcheck (до заморозки)", "spec", "regress", "confirm только при REGRESSION PASS, один раз",
                     "sheet только при PASS обоих"],
        "sheet": {"panels": ["member original x4", "V3.1", "V3.2", "truth (если есть)"], "real": list(SHEET_REAL),
                  "zoom": list(SHEET_ZOOM), "confirmation": "все случаи подтверждения", "scale": 2, "zoom_scale": 4,
                  "floor_rgb": list(FLOOR)},
        "forbidden": ["c = 0.75 не меняется", "Stage A, INTERPOLATED_MAP_V1, порог 10, старые случаи, C1 не меняются",
                      "MULTI_REGION_FOOTPRINT остаётся диагностикой", "V7, семейства не меняются",
                      "857/1030 и 173 отказа не трогаются", "без модели и видеокарты"],
    }


def do_spec():
    p = os.path.join(OUT, "spec.json")
    if os.path.exists(p):
        raise SystemExit("spec.json уже записан - он неизменяем (%s)" % p)
    body = spec_body()
    body["sha256"] = V2.jsha({k: body[k] for k in BODY})
    body["frozen_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    body["self_sha256"] = fsha(SELF)
    A3.save_json(p, body)
    print("spec заморожен: %s, sha %s, код V3.2 %s" % (p, body["sha256"][:12], body["implementation"]["sha256"][:12]))


def load_spec():
    sp = load("spec.json")
    if V2.jsha({k: sp[k] for k in BODY}) != sp["sha256"]:
        raise SystemExit("spec.json изменён после заморозки")
    for nm, now, was in (("код V3.2", impl_state(), sp["implementation"]), ("V3.1", stage_b_state(), sp["stage_b_base"]),
                         ("Stage A", stage_a_state(), sp["stage_a"]), ("приёмка V3.1", v31_state(), sp["v31_dependency"]),
                         ("DEV", dev_state(), sp["dev_dependency"]), ("набор подтверждения", confirm_state(),
                                                                       sp["confirm_reserved"])):
        if now != was:
            raise SystemExit("%s изменился после заморозки" % nm)
    if fsha(SELF) != sp["self_sha256"]:
        raise SystemExit("сама приёмка V3.2 изменилась после заморозки")
    return sp


# ---------- регрессия ----------

def run_case(c, inputs):
    ob, ot, hd, truth = A3.inputs_of(c)
    if A31.got_inputs(c) != inputs[c["id"]]:
        raise SystemExit("%s: входы не те, что в spec V3.1" % c["id"])
    der, chain = D32.derive(hd, ob, ot, c["route"])
    der2, chain2 = D32.derive(hd, ob, ot, c["route"])
    det = (der is None and der2 is None) or (der is not None and der2 is not None and (der == der2).all())
    row = {"kind": c["kind"], "what": c["what"], "route": c["route"], "expect": c["expect"], "base": c["base"],
           "member": c.get("member"), "chain": chain, "deterministic": bool(det and chain == chain2)}
    if der is None:
        row.update(status="REFUSED", gates={g: 0 for g in STRUCT + VISUAL})
        row["gates"]["geometry_support_mismatch"] = min(chain["geometry_resolution"]["support_mismatch"].values())
        return row
    g = chain["geometry_transform"]
    hd_o, ob_o = D3.geo(hd, g), D3.geo(ob, g)
    gt, info = A3.gates3(der, hd_o, ob_o, ot)
    row.update(status="DERIVED", gates=gt, info=info)
    row["coverage"] = A3.coverage3(info, der, hd_o, ob_o, ot, truth if truth is not None else der)
    d31, _ = D31.derive(hd, ob, ot, c["route"])
    ex, _ = D3.derive(hd, ob, ot, c["route"], mode="EXACT_MAP")
    so, _ = D3.derive(hd, ob, ot, c["route"], mode="SOFT_MAP", soft_scope="support")
    sup = (ob_o[..., 3] > 0) & (ot[..., 3] > 0)
    row["modes"] = {nm: A31.mode_diag(a, hd_o, ob_o, ot, truth, sup) for nm, a in
                    (("V3.2", der), ("V3.1", d31), ("EXACT_MAP", ex), ("SOFT_MAP", so))}
    if truth is not None:
        tg = "MIRROR_X" if c.get("mirror_member") else "IDENTITY"
        tgt, _ = A3.gates3(truth, D3.geo(hd, tg), D3.geo(ob, tg), ot)
        mm = V2.main_metric(der, truth)
        row.update(truth_gates=tgt, gates_valid=not any(tgt.values()), main=mm,
                   main_pass=mm["mean_de"] <= V2.MAIN_MEAN and mm["p95_de"] <= V2.MAIN_P95,
                   identity_baseline=V2.main_metric(hd_o, truth))
        save_png(truth, "truth", c["id"] + ".png")
    if c["id"] in LEAK:
        ta, tb, split = A31.side_truths(c, ob)
        row["leak"] = {"split": split, "V3.2": A31.leakage(der, ta, tb, split), "V3.1": A31.leakage(d31, ta, tb, split),
                       "EXACT_MAP": A31.leakage(ex, ta, tb, split), "SOFT_MAP": A31.leakage(so, ta, tb, split),
                       "truth": A31.leakage(truth, ta, tb, split)}
    save_png(der, "derived", c["id"] + ".png")
    save_png(d31, "v31", c["id"] + ".png")
    save_png(hd_o, "hd", c["id"] + ".png")
    save_png(ob_o, "orig", c["id"] + "_base.png")
    save_png(ot, "orig", c["id"] + "_member.png")
    return row


def hard(res, sp, vs):
    cs = res["cases"]
    h = {}
    bad1 = [k for k, r in cs.items() if r["status"] != "DERIVED" or any(r["gates"][g] for g in STRUCT)]
    h["H1"] = {"pass": not bad1, "detail": "STRUCTURAL > 0 / отказ: %s" % (", ".join(bad1) or "нет")}
    ps = sp["v31_dependency"]["v3_pass_set"]
    bad2 = [k for k in ps if not vs[k].startswith("PASS")]
    h["H2"] = {"pass": not bad2, "detail": "V3 PASS %s; регрессия: %s" % (", ".join(ps), ", ".join(bad2) or "нет")}
    d3, ok3 = [], True
    for k in H3_CASES:
        m = cs[k]["modes"]
        i, e, s, o = (m[n]["main"]["mean_de"] for n in ("V3.2", "EXACT_MAP", "SOFT_MAP", "V3.1"))
        ok = i <= min(e, s) + TIE_DE
        ok3 &= ok
        d3.append("%s V3.2 %.2f / E %.2f / S %.2f (V3.1 %.2f) %s" % (k, i, e, s, o, "ok" if ok else "ХУЖЕ"))
    h["H3"] = {"pass": ok3, "detail": "; ".join(d3)}
    d4, ok4 = [], True
    for k in LEAK:
        lk = cs[k]["leak"]
        li, lt, ls = lk["V3.2"]["leak_px"], lk["truth"]["leak_px"], lk["SOFT_MAP"]["leak_px"]
        ok = li == 0 and lt == 0 and ls > 0
        ok4 &= ok
        d4.append("%s утечка V3.2 %d, правда %d, SOFT %d, V3.1 %d из %d%s" % (
            k, li, lt, ls, lk["V3.1"]["leak_px"], lk["V3.2"]["counted_px"],
            "" if ok else (" - ПРОВАЛ" if li else " - НЕ ПОКРЫТ")))
    h["H4"] = {"pass": ok4, "detail": "; ".join(d4)}
    d5 = ["%s %d (V3.1 %s)" % (k, cs[k]["gates"].get(H5_GATE, 0),
                               cs[k]["modes"]["V3.1"]["visual"].get(H5_GATE, 0)) for k in H5_CASES]
    h["H5"] = {"pass": all(cs[k]["gates"].get(H5_GATE, 0) == 0 for k in H5_CASES),
               "detail": "%s: %s" % (H5_GATE, ", ".join(d5))}
    bad6 = [k for k, r in cs.items() if not r["deterministic"]]
    h["H6"] = {"pass": not bad6, "detail": "не детерминированы: %s" % (", ".join(bad6) or "нет")}
    return h


def regression_verdict(res, sp):
    vs = {k: A3.verdict3(k, r, None) for k, r in res["cases"].items()}
    h = hard(res, sp, vs)
    return ("PASS" if all(x["pass"] for x in h.values()) else "FAIL"), vs, h


def do_regress():
    sp = load_spec()
    if os.path.exists(os.path.join(OUT, "regression.json")):
        raise SystemExit("regression.json уже есть - регрессия прогоняется один раз")
    sp31 = A3.load_json(rel(V31_OUT + "/spec.json"))
    res = {"profile": PROFILE, "spec_sha256": sp["sha256"], "implementation": sp["implementation"],
           "run_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "cases": {}}
    for c in sp31["cases"]:
        res["cases"][c["id"]] = run_case(c, sp31["inputs"])
    o, vs, h = regression_verdict(res, sp)
    res.update(verdict=o, hard=h, case_verdicts=vs)
    dump("regression.json", res)
    write_regression_md(res, sp)
    print("регрессия: %s; %s" % (o, "; ".join("%s %s" % (k, "PASS" if x["pass"] else "FAIL") for k, x in h.items())))


def write_regression_md(res, sp):
    cs, h, vs = res["cases"], res["hard"], res["case_verdicts"]
    v31 = A3.load_json(rel(V31_OUT + "/results.json"))["cases"]
    vs31 = {k: A3.verdict3(k, r, None) for k, r in v31.items()}
    L = ["# DERIVE_RECOLOR_ACCEPTANCE_V3.2 - регрессия старых 27", "",
         "Spec `%s`, вывод `%s` (%s), прогон %s." % (sp["sha256"][:12], sp["implementation"]["sha256"][:12],
                                                     sp["implementation"]["version"], res["run_at"]), "",
         "**REGRESSION %s** (правило: H1..H6 все PASS)." % res["verdict"], "",
         "| | условие | итог | подробно |", "|---|---|---|---|"]
    for k, x in h.items():
        L.append("| %s | %s | %s | %s |" % (k, sp["regression"]["hard_acceptance"][k], "PASS" if x["pass"] else "**FAIL**",
                                            x["detail"]))
    L += ["", "## Случаи (вердикт по правилу V3 - диагностика, регрессию не решает)", "",
          "| случай | что | цепочка | STRUCT | VISUAL V3.2 | VISUAL V3.1 | ΔE V3.2 / V3.1 | ограничено ASL | вердикт V3.2 | V3.1 |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for k, r in cs.items():
        what = r["what"] + (" %s -> %s" % (r["base"], r["member"]) if r["kind"] == "real" else "")
        st = ", ".join("%s %d" % (g, r["gates"][g]) for g in STRUCT if r["gates"][g]) or "0"
        if r["status"] != "DERIVED":
            L.append("| %s | %s | REFUSED | %s | - | - | - | - | %s | %s |" % (k, what, st, vs[k], vs31.get(k, "-")))
            continue
        m = r["modes"]
        de = ("%.2f / %.2f" % (m["V3.2"]["main"]["mean_de"], m["V3.1"]["main"]["mean_de"])) if "main" in m["V3.2"] else "-"
        L.append("| %s | %s | %s | %s | %s | %s | %s | %d | %s | %s |" % (
            k, what, r["chain"]["geometry_transform"], st, A31.fmt_gates(m["V3.2"]["visual"]),
            A31.fmt_gates(m["V3.1"]["visual"]), de, r["chain"]["transfer"]["asl_limited_px"], vs[k], vs31.get(k, "-")))
    L += ["", "## Рябь над опорой (V3.2 / V3.1 / EXACT / SOFT)", ""]
    for k, r in cs.items():
        if r.get("modes"):
            L.append("- %s: %s" % (k, " / ".join(str(r["modes"][n]["speckle"]) for n in ("V3.2", "V3.1", "EXACT_MAP", "SOFT_MAP"))))
    with open(os.path.join(OUT, "regression.md"), "w", encoding=ENC, newline="\n") as f:
        f.write("\n".join(L) + "\n")


# ---------- подтверждение ----------

def do_confirm():
    sp = load_spec()
    reg = load("regression.json")
    if reg["spec_sha256"] != sp["sha256"]:
        raise SystemExit("regression.json от другого spec")
    o, _vs, _h = regression_verdict(reg, sp)
    if o != "PASS" or reg["verdict"] != "PASS":
        raise SystemExit("REGRESSION %s - набор подтверждения не открывается (V3.2 FAIL)" % o)
    p = os.path.join(OUT, "confirmation.json")
    if os.path.exists(p):
        raise SystemExit("confirmation.json уже есть - подтверждение прогоняется один раз")
    raw = confirm_blob(sp["confirm_reserved"]["file"])
    if hashlib.sha256(raw).hexdigest() != CONFIRM_SHA:
        raise SystemExit("confirm_reserved.json не тот")
    pairs = json.loads(raw.decode("utf-8"))
    if len(pairs) != 15:
        raise SystemExit("в наборе подтверждения %d пар, ожидалось 15" % len(pairs))
    rows = []
    for pair in pairs:
        for r in eval_pair(pair):
            if "_img" in r:
                der, d31, hdo, obo, ot, truth = r["_img"]
                stem = r["case"].replace(":", "_").replace(">", "__").replace("/", "_")
                save_png(der, "confirm", stem + "_v32.png")
                save_png(d31, "confirm", stem + "_v31.png")
                save_png(ot, "confirm", stem + "_member.png")
                if truth is not None:
                    save_png(truth, "confirm", stem + "_truth.png")
                r["stem"] = stem
            rows.append(r)
            print("%-48s %s S%s new %s seam %s dE %s/%s" % (r["case"], r["status"], r["struct"], r.get("new_art", "-"),
                                                          r.get("seam_leak", "-"), r.get("de", "-"), r.get("de_v31", "-")),
                  flush=True)
    h, inv = confirm_verdict(rows)
    verdict = "INVALID_MEASURE" if inv else ("PASS" if all(x["pass"] for x in h.values()) else "FAIL")
    res = {"profile": PROFILE, "spec_sha256": sp["sha256"], "regression_sha256": hashlib.sha256(
        open(os.path.join(OUT, "regression.json"), "rb").read()).hexdigest(), "run_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "pairs": pairs, "cases": strip(rows), "hard": h, "measure_invalid": inv, "verdict": verdict}
    dump("confirmation.json", res)
    write_confirmation_md(res)
    print("подтверждение: %s; %s" % (verdict, "; ".join("%s %s" % (k, "PASS" if x["pass"] else "FAIL") for k, x in h.items())))


def write_confirmation_md(res):
    L = ["# DERIVE_RECOLOR_ACCEPTANCE_V3.2 - подтверждение 15 пар (один прогон)", "",
         "Прогон %s, spec `%s`." % (res["run_at"], res["spec_sha256"][:12]), "", "**CONFIRMATION %s**" % res["verdict"], "",
         "| условие | итог | подробно |", "|---|---|---|"]
    for k, x in res["hard"].items():
        L.append("| %s | %s | %s |" % (k, "PASS" if x["pass"] else "**FAIL**", x["detail"]))
    if res["measure_invalid"]:
        L += ["", "Контроли мер не выполнены: " + "; ".join("%s: %s" % (c, ", ".join(v)) for c, v in res["measure_invalid"])]
    L += ["", "## Случаи", "", "| случай | категория | цепочка | STRUCT | пятна V3.2 / V3.1 | новые | ΔE V3.2 / V3.1 | "
          "шов V3.2 / V3.1 | ограничено ASL |", "|---|---|---|---|---|---|---|---|---|"]
    for r in res["cases"]:
        if r["status"] != "DERIVED":
            L.append("| %s | %s | REFUSED | 1 | | | | | |" % (r["case"], r["category"]))
            continue
        L.append("| %s | %s | %s | %d | %d / %d | %s | %s | %s | %d |" % (
            r["case"], r["category"], r["geometry"], r["struct"], r["art"], r["art_v31"], r.get("new_art", "-"),
            ("%.3f / %.3f" % (r["de"], r["de_v31"])) if "de" in r else "-",
            ("%d / %d из %d" % (r["seam_leak"], r["seam_leak_v31"], r["seam_counted"])) if "seam_leak" in r else "-",
            r["asl_limited_px"]))
    L += ["", "## Диагностика следа (ближе к чужой правде / всего): V3.2, V3.1, правда", ""]
    for r in res["cases"]:
        if "seam_diag" in r:
            L.append("- %s: V3.2 %s; V3.1 %s; правда %s" % (r["case"], r["seam_diag"], r["seam_diag_v31"], r["seam_truth_diag"]))
    with open(os.path.join(OUT, "confirmation.md"), "w", encoding=ENC, newline="\n") as f:
        f.write("\n".join(L) + "\n")


# ---------- лист ----------

def panel(img, sc):
    return V2.on(img, FLOOR).resize((img.shape[1] * sc, img.shape[0] * sc), Image.NEAREST)


def strip_sheet(rows, sc, title):
    """rows: (подпись, [картинки или None]); колонки member | V3.1 | V3.2 | truth."""
    heads = ["member x4", "V3.1", "V3.2", "truth"]
    pw = max(r[1][1].shape[1] for r in rows) * sc
    ph = max(r[1][1].shape[0] for r in rows) * sc
    W, Hh = 4 * pw + 3 * 8 + 160, len(rows) * (ph + 8) + 40
    im = Image.new("RGB", (W, Hh), (24, 24, 28))
    dr = ImageDraw.Draw(im)
    dr.text((4, 4), title, fill=(255, 255, 0))
    for i, hname in enumerate(heads):
        dr.text((160 + i * (pw + 8) + 4, 22), hname, fill=(220, 220, 220))
    for j, (lab, imgs) in enumerate(rows):
        y = 40 + j * (ph + 8)
        dr.text((4, y + 4), lab, fill=(220, 220, 220))
        for i, a in enumerate(imgs):
            if a is not None:
                im.paste(panel(a, sc).convert("RGB"), (160 + i * (pw + 8), y))
    return im


def do_sheet():
    sp = load_spec()
    reg, conf = load("regression.json"), load("confirmation.json")
    if reg["verdict"] != "PASS" or conf["verdict"] != "PASS" or conf["spec_sha256"] != sp["sha256"]:
        raise SystemExit("лист - только при PASS регрессии и подтверждения (сейчас %s / %s)" % (reg["verdict"], conf["verdict"]))
    x4 = lambda a: np.repeat(np.repeat(a, 4, 0), 4, 1)
    ld = lambda *p: A3.read_png(os.path.join(OUT, *p))
    d = os.path.join(OUT, "sheet")
    os.makedirs(d, exist_ok=True)
    rows = [("%s %s" % (k, reg["cases"][k]["member"]), [x4(ld("orig", k + "_member.png")), ld("v31", k + ".png"),
                                                       ld("derived", k + ".png"), None]) for k in SHEET_REAL]
    strip_sheet(rows, sp["sheet"]["scale"], "V3.2 human validation: R05-R11").save(os.path.join(d, "real_R05_R11.png"))
    for k in SHEET_ZOOM:
        r = [(k, [x4(ld("orig", k + "_member.png")), ld("v31", k + ".png"), ld("derived", k + ".png"), None])]
        strip_sheet(r, sp["sheet"]["zoom_scale"], "V3.2 zoom %s" % k).save(os.path.join(d, "zoom_%s.png" % k))
    crow = []
    for r in conf["cases"]:
        if "stem" not in r:
            continue
        s = r["stem"]
        tp = os.path.join(OUT, "confirm", s + "_truth.png")
        crow.append((r["case"][:22], [x4(ld("confirm", s + "_member.png")), ld("confirm", s + "_v31.png"),
                                      ld("confirm", s + "_v32.png"), A3.read_png(tp) if os.path.exists(tp) else None]))
    for i in range(0, len(crow), 12):
        strip_sheet(crow[i:i + 12], sp["sheet"]["scale"], "V3.2 confirmation %d" % (i // 12 + 1)).save(
            os.path.join(d, "confirm_%02d.png" % (i // 12 + 1)))
    ans = os.path.join(OUT, "answers_human.tsv")
    if not os.path.exists(ans):
        with open(ans, "w", encoding=ENC, newline="\n") as f:
            f.write("case_id\tverdict\tnote\n" + "".join("%s\t\t\n" % k for k in SHEET_REAL))
    print("лист -> %s" % d)


# ---------- итог ----------

def do_report():
    sp = load_spec()
    L = ["# DERIVE_RECOLOR_ACCEPTANCE_V3.2 - итог", "", "Spec `%s`, код V3.2 `%s`, c = %s." % (
        sp["sha256"][:12], sp["implementation"]["sha256"][:12], D32.ASL_C), "", "NOTE: " + STALE_AFTER_NOTE, ""]
    rp = os.path.join(OUT, "regression.json")
    if not os.path.exists(rp):
        L.append("Регрессия не прогонялась.")
    else:
        reg = load("regression.json")
        L.append("**REGRESSION %s**" % reg["verdict"])
        L += ["- %s %s: %s" % (k, "PASS" if x["pass"] else "FAIL", x["detail"]) for k, x in reg["hard"].items()]
        cp = os.path.join(OUT, "confirmation.json")
        L.append("")
        if os.path.exists(cp):
            conf = load("confirmation.json")
            L.append("**CONFIRMATION %s**" % conf["verdict"])
            L += ["- %s %s: %s" % (k, "PASS" if x["pass"] else "FAIL", x["detail"]) for k, x in conf["hard"].items()]
            L.append("")
            L.append("**V3.2: %s**" % ("PASS по автоматике; human validation R05-R11 по листу" if conf["verdict"] == "PASS"
                                       else "FAIL (подтверждение %s)" % conf["verdict"]))
        elif reg["verdict"] != "PASS":
            L.append("**V3.2: FAIL** - регрессия не пройдена, набор подтверждения не открывался.")
        else:
            L.append("Подтверждение не прогонялось.")
    with open(os.path.join(OUT, "report.md"), "w", encoding=ENC, newline="\n") as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L))


def do_check():
    load_spec()
    print("spec, код V3.2, V3.1, Stage A, приёмка V3.1, DEV и набор подтверждения не изменились")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("devcheck", "spec", "regress", "confirm", "sheet", "report", "check"))
    a = ap.parse_args()
    os.chdir(ROOT)
    {"devcheck": do_devcheck, "spec": do_spec, "regress": do_regress, "confirm": do_confirm, "sheet": do_sheet,
     "report": do_report, "check": do_check}[a.cmd]()


if __name__ == "__main__":
    main()
