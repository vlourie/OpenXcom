"""DERIVE_RECOLOR_V3.3_DEV: диагностика R01/R02/R12 на ФИКСИРОВАННОЙ точке id2_J1.5_c0.1 (специалист 03.10,
передал Vitali в чате). Только диагностика: вердикт V3.3_DEV (FAIL_NO_CANDIDATE) не меняется, точка не выбирается,
параметры не подбираются, confirmation 15 не читается, заморозки V3.3 нет. Прогон ровно один - повтор отказывается.

Для каждого случая: пятна PRIOR / V3.1 / V3.2 / V3.3-диагностика; пиксели unmix attempted / accepted / rejected;
отказы по ID, ST, CY; для проблемных классов (пятно хотя бы у одного варианта) - пары unmix на их пикселях с
ID, ST, CY и допуском.

    py -3.13 tools/hdart/derive_recolor_v33_rdiag.py run
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import derive_recolor_v33_dev as E  # noqa: E402

M, A3, A31, V2, D3, D31 = E.M, E.A3, E.A31, E.V2, E.D3, E.D31
POINT = {"T_id": 2.0, "T_J": 1.5, "T_c": 0.1}
OUT_J = E.OUT + "/r_diag_v33.json"
OUT_MD = E.OUT + "/r_diag_v33.md"
DECISION = ("специалист 03.10, передал Vitali в чате: один диагностический прогон R01/R02/R12 на id2_J1.5_c0.1; "
            "diagnostic only, вердикт V3.3_DEV не меняется, другую точку не выбирать, coverage не менять, "
            "confirmation 15 закрыт, V3.3 не замораживается")


def class_masks(out, hdo, obo, ot):
    """Как M.art_stats: маска HD-пикселей каждого класса (основа, член) с >= ART_MIN_CELLS клетками."""
    sb, st = obo[..., 3] > 0, ot[..., 3] > 0
    _r, _m, min_d = V2.blocks(out)
    _r, _m, min_b = V2.blocks(hdo)
    full = (min_d >= V2.ALPHA_OPAQUE) & (min_b >= V2.ALPHA_OPAQUE) & sb & st
    S, T = V2.code(obo), V2.code(ot)
    cell_in = np.zeros((4, 4), bool)
    cell_in[1:3, 1:3] = True
    opq = (out[..., 3] >= V2.ALPHA_OPAQUE) & (hdo[..., 3] >= V2.ALPHA_OPAQUE) & np.tile(cell_in, S.shape)
    pairs = S * (1 << 24) + T
    res = {}
    for p in np.unique(pairs[full]):
        sel = full & (pairs == p)
        if sel.sum() < V2.ART_MIN_CELLS:
            continue
        res[int(p)] = np.repeat(np.repeat(sel, 4, 0), 4, 1) & opq
    return res


def arts(out, hdo, obo, ot):
    cs = M.art_stats(out, hdo, obo, ot)
    fl = M.flagged(cs)
    g = A3.gates3(out, hdo, obo, ot)[0]["unintended_local_artifacts"]
    if len(fl) != g:
        raise SystemExit("счёт классов не равен воротам")
    return fl, cs


def why(r):
    if r["reason"]:
        return r["reason"]
    bad = [n for n, b in (("ID", r["ID"] < POINT["T_id"]), ("ST", r["ST"] > POINT["T_J"]),
                          ("CY", r["CY"] > POINT["T_c"])) if b]
    return "+".join(bad) or "OK"


def hexk(k):
    return "#%06x>#%06x" % (k >> 24, k & 0xFFFFFF)


def one(c):
    ob, ot, hd, _t = A3.inputs_of(c)
    g, hdo, obo, d, op, sig, der31 = E.prepare(hd, ob, ot, c["route"])
    keys = tuple(sorted(k for k, v in sig.items() if E.eligible(v[2], POINT)))
    w, acc = E.compose(d, sig, keys)
    v33 = E.colorize(hdo, d, w)
    v33b = E.colorize(hdo, d, E.compose(d, sig, keys)[0])
    prior = E.colorize(hdo, d, d["pri"])
    v32, ch32 = M.D32.derive(hd, ob, ot, c["route"])
    if v32 is None or ch32["geometry_transform"] != g:
        raise SystemExit("V3.2: другая геометрия или отказ")
    var = {"PRIOR": prior, "V3.1": der31, "V3.2": v32, "V3.3_diag": v33}
    fl = {}
    for nm, o in var.items():
        fl[nm], _cs = arts(o, hdo, obo, ot)
    cov = E.coverage(d, sig, keys, op)
    dwm = np.abs(d["wgt"] - d["pri"]).sum(-1) / 2
    att = (dwm > E.EPS) & op
    okp = att & (acc >= 0.5 * dwm)
    # отказы по сигналам: пиксели пар (поле px сигналов), пересекаются между ID/ST/CY
    rej = {"ID": 0, "ST": 0, "CY": 0, "same_base": 0, "few_px": 0}
    combo = {}
    for _k, (_p, _m, r) in sig.items():
        wy = why(r)
        combo[wy] = combo.get(wy, 0) + r["px"]
        for n in wy.split("+"):
            if n in rej:
                rej[n] += r["px"]
    # проблемные классы: пятно хотя бы у одного варианта
    masks = class_masks(der31, hdo, obo, ot)
    probs = []
    for k in sorted(set().union(*fl.values())):
        if k not in masks:
            masks_k = class_masks(v33, hdo, obo, ot).get(k)
        else:
            masks_k = masks[k]
        if masks_k is None:
            continue
        pxm = masks_k
        pa = pxm & att
        prs = []
        for kk, (_part, mass, r) in sig.items():
            on = pxm & (mass > E.EPS) & op
            if not on.any():
                continue
            prs.append({"pair": "%d~%d" % kk, "colours": "#%06x~#%06x" % (int(d["bcode"][kk[0]]), int(d["bcode"][kk[1]])),
                        "px_in_class": int(on.sum()), "ID": r.get("ID"), "ST": r.get("ST"), "CY": r.get("CY"),
                        "reason": r["reason"], "verdict": why(r), "accepted": kk in keys})
        prs.sort(key=lambda x: -x["px_in_class"])
        probs.append({"class": hexk(k), "flag": {nm: k in fl[nm] for nm in var},
                      "px": int(pxm.sum()), "unmix_attempted": int(pa.sum()), "unmix_accepted": int((pa & okp).sum()),
                      "unmix_rejected": int((pa & ~okp).sum()), "pairs": prs})
    return {"geometry": g, "art": {nm: len(f) for nm, f in fl.items()}, "deterministic": bool((v33 == v33b).all()),
            "pairs_total": len(sig), "pairs_eligible": len(keys), "cov": cov, "rejects_px": rej, "verdict_px": combo,
            "problem_classes": probs}


def fmt(x):
    return "-" if x is None else "%.2f" % x


def md(res):
    L = ["﻿# V3.3_DEV — диагностика R01/R02/R12 на id2_J1.5_c0.1 (diagnostic only)", "",
         DECISION + ".", "", "Вердикт V3.3_DEV не меняется: FAIL_NO_CANDIDATE. Точка задана, а не выбрана.", "",
         "| Случай | PRIOR | V3.1 | V3.2 | V3.3 diag | пар / допущено | unmix attempted | accepted | rejected |",
         "|---|---|---|---|---|---|---|---|---|"]
    for k, r in res["cases"].items():
        a, cv = r["art"], r["cov"]
        L.append("| %s | %d | %d | %d | **%d** | %d / %d | %d | %d | %d |" % (
            k, a["PRIOR"], a["V3.1"], a["V3.2"], a["V3.3_diag"], r["pairs_total"], r["pairs_eligible"],
            cv["attempted_px"], cv["accepted_px"], cv["rejected_px"]))
    L += ["", "Отказы по сигналам (пиксели пар; одна пара может провалить несколько сигналов):", "",
          "| Случай | ID | ST | CY | same_base | few_px | по сочетаниям |", "|---|---|---|---|---|---|---|"]
    for k, r in res["cases"].items():
        j = r["rejects_px"]
        L.append("| %s | %d | %d | %d | %d | %d | %s |" % (k, j["ID"], j["ST"], j["CY"], j["same_base"], j["few_px"],
                                                       " ".join("%s:%d" % kv for kv in sorted(r["verdict_px"].items()))))
    L += ["", "## Проблемные классы (пятно хотя бы у одного варианта)", ""]
    for k, r in res["cases"].items():
        L.append("### " + k)
        for p in r["problem_classes"]:
            L.append("- класс %s: пятно %s; пикселей %d, unmix attempted %d / accepted %d / rejected %d" % (
                p["class"], ", ".join("%s %s" % (n, "да" if f else "нет") for n, f in p["flag"].items()),
                p["px"], p["unmix_attempted"], p["unmix_accepted"], p["unmix_rejected"]))
            for q in p["pairs"][:8]:
                L.append("  - пара %s (%s): px %d, ID %s, ST %s, CY %s -> %s, %s" % (
                    q["pair"], q["colours"], q["px_in_class"], fmt(q["ID"]), fmt(q["ST"]), fmt(q["CY"]), q["verdict"],
                    "допущена" if q["accepted"] else "отвергнута"))
        L.append("")
    return "\n".join(L) + "\n"


def run():
    if os.path.exists(E.rel(OUT_J)):
        raise SystemExit("диагностика уже сделана - повтор запрещён")
    E.load_spec()
    sp31 = A3.load_json(A31.rel(A31.OUT + "/spec.json"))
    cases = {c["id"]: c for c in sp31["cases"]}
    res = {"profile": "DERIVE_RECOLOR_V3_3_R_DIAG", "decision": DECISION, "point": POINT,
           "dev_verdict": "FAIL_NO_CANDIDATE (не меняется)", "code_sha256": E.fsha("tools/hdart/derive_recolor_v33_rdiag.py"),
           "dev_code_sha256": E.fsha(E.SELF), "cases": {}}
    # сверка с записанным: регрессия V3.2 (regression.md) - V3.2 1/2/2, V3.1 1/2/6
    known = {"R01": (1, 1), "R02": (2, 2), "R12": (2, 6)}
    for k in E.R_CASES:
        res["cases"][k] = one(cases[k])
        r = res["cases"][k]
        if (r["art"]["V3.2"], r["art"]["V3.1"]) != known[k]:
            raise SystemExit("сверка с регрессией V3.2 не сошлась: %s %s" % (k, r["art"]))
        print(k, "пятна", r["art"], "unmix", r["cov"]["attempted_px"], r["cov"]["accepted_px"], r["cov"]["rejected_px"],
              flush=True)
    E.jdump(res, OUT_J)
    open(E.rel(OUT_MD), "w", encoding="utf-8").write(md(res))
    print("записано", OUT_J, OUT_MD)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1:] == ["run"]:
        run()
    else:
        raise SystemExit(__doc__)
