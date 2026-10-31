"""DERIVE_RECOLOR_BASE_ACCEPTANCE_V1 - приёмка tools/hdart/derive_recolor_base_v1.py
(Stage A + INTERPOLATED_MAP, без unmix, ASL и ID/ST/CY).

Решение: специалист 03.10, передал Vitali в чате. Контракт делит безопасность и верность:
  HARD (машина):  STRUCTURAL = 0 (в т.ч. geometry_support_mismatch, alpha_topology_changed), отказа Stage A нет,
                  causal seam leakage = 0, determinism PASS, R01 = R02 = R12 = 0 (unintended_local_artifacts),
                  wrong_palette_mapping = 0 там, где есть правда (синтетика), никаких unmix / ASL / eligibility.
  DIAGNOSTIC:     пятна и mapping на REAL, ΔE к правде, верность дизера (C2, SYN_DITHER, SD - новые пятна против
                  правды), потеря энергии фактуры, потеря деталей. Не валят, а направляют в human review по
                  правилу, замороженному в spec.
  VERIFIED:       hard PASS на старых 27, затем hard PASS на confirmation-15, затем human review PASS по всем
                  карточкам (UNSURE - не PASS). VERIFIED ставит человек; модуль только считает, готово ли.

Порядок (каждый шаг проверяет предыдущий и неизменность кода и spec):
  devcheck  на DEV-парах вывод BASE побайтно равен PRIOR стенда V3.3_DEV, меры повторяют dev3_results.json
            (вариант PRIOR); набор подтверждения и старые 27 не читаются;
  spec      заморозить: код, контракт, правило отбора human review, вопрос и правило итога (один раз);
  regress   старые 27 (входы - spec приёмки V3.1), один раз;
  confirm   15 пар - только при REGRESSION PASS, один раз;
  cards     слепые карточки human review по замороженному правилу - только при PASS обоих;
  final     итог по ответам answers.tsv; report - сводка; check - spec и код не изменились.

Только numpy, без модели и видеокарты. Команды из корня репозитория:
    py -3.13 tools/hdart/derive_recolor_base_acceptance_v1.py devcheck|spec|regress|confirm|cards|final|report|check
"""
import argparse
import ast
import hashlib
import json
import os
import random
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
import derive_recolor_acceptance_v32 as M  # noqa: E402
import derive_recolor_base_v1 as B  # noqa: E402
import derive_recolor_v3 as D3  # noqa: E402
import derive_recolor_v31 as D31  # noqa: E402
import derive_recolor_v33_dev as E  # noqa: E402

ENC = "utf-8-sig"
ROOT = A3.ROOT
PROFILE = "DERIVE_RECOLOR_BASE_ACCEPTANCE_V1"
OUT = os.path.join(ROOT, "art", "objects", "generation", "probes", "derive-recolor-base-v1-acceptance")
CARDS = os.path.join(OUT, "human_cards")
SELF = "tools/hdart/derive_recolor_base_acceptance_v1.py"
IMPL = "tools/hdart/derive_recolor_base_v1.py"
STAGE_A = "tools/hdart/derive_recolor_v3.py"
STAGE_B_REF = "tools/hdart/derive_recolor_v31.py"
DEV = M.DEV
DEV_SPEC = E.DEV_SPEC
DEV_SPEC_SHA = M.DEV_SPEC_V3_SHA
V31_OUT = M.V31_OUT
CONFIRM_SHA = M.CONFIRM_SHA
DECISION = ("специалист 03.10, передал Vitali в чате: DERIVE_RECOLOR_BASE_V1 = Stage A + INTERPOLATED_MAP; "
            "universal unmix, ASL, ID/ST/CY REJECTED; REAL без правды: пятна и mapping - diagnostic + обязательный "
            "human review (не V3.1 и не = 0); синтетический дизер - fidelity, не safety; wrong_palette_mapping hard "
            "только при правде; R01/R02/R12 = 0 hard; VERIFIED = hard machine PASS + mandatory human review PASS, "
            "UNSURE не PASS; порядок: freeze, старые 27, при PASS один раз confirmation-15, human review")
STRUCT = A3.STRUCT
H5_CASES, H5_GATE, LEAK = A31.H5_CASES, A31.H5_GATE, A31.LEAK
ALLOWED_IMPORTS = ("numpy", "derive_recolor_v3", "derive_recolor_v31")
FORBIDDEN_WORDS = ("unmix", "asl", "eligib", "derive_recolor_v32", "derive_recolor_v33")
DITHER_FORMS = M.DITHER_FORMS
# human review: обязательные случаи старых 27 и маршрутизация (только в review, не FAIL)
HUMAN_OLD = ("R01", "R02", "R12", "R05", "R06", "R10", "C1", "C2")
HUMAN_CONFIRM_FORMS = ("REAL", "SYN_DITHER", "SD")
DE_MARGIN = 1.0          # синтетика: ΔE BASE > min(EXACT_MAP, SOFT_MAP) + 1.0 -> review
CARD_SEED = 20261003
CARD_SCALE = 3
QUESTION = ("Is the BASE recolor visually acceptable as a production HD recolor of this member, preserving geometry "
            "and recognizable material/detail, without obvious introduced artifacts?")
ANSWERS = ("PASS", "FAIL", "UNSURE")
BODY = ("profile", "decision", "implementation", "stage_a", "stage_b_ref", "v31_dependency", "dev_dependency",
        "confirm_reserved", "hard", "diagnostic", "human", "final_rule", "sequence", "forbidden")


def rel(p):
    return os.path.join(ROOT, p)


def fsha(p):
    return hashlib.sha256(open(rel(p), "rb").read()).hexdigest()


def osha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


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


def write_md(name, lines):
    with open(os.path.join(OUT, name), "w", encoding=ENC, newline="\n") as f:
        f.write("\n".join(lines) + "\n")


# ---------- чистота реализации ----------

def impl_purity():
    """Импорты модуля BASE - только ALLOWED_IMPORTS, в коде нет следов unmix/ASL/eligibility (кроме докстроки)."""
    src = open(rel(IMPL), encoding="utf-8").read()
    tree = ast.parse(src)
    imps = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            imps |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            imps.add(n.module)
    doc = ast.get_docstring(tree) or ""
    code = src.replace(doc, "").lower()
    words = [w for w in FORBIDDEN_WORDS if w in code]
    return {"imports": sorted(imps), "extra_imports": sorted(imps - set(ALLOWED_IMPORTS)), "forbidden_words": words,
            "pure": not (imps - set(ALLOWED_IMPORTS)) and not words}


def chain_ok(ch):
    return ch.get("version") == B.VERSION and ch.get("color_transform") in (B.COLOR_TRANSFORM, None) and \
        not any(w in json.dumps(ch).lower() for w in ("unmix", "asl_", "eligib"))


# ---------- диагностические меры верности ----------

def _hp(L, op):
    P = np.pad(np.where(op, L, 0.0), 2)
    Mk = np.pad(op.astype(np.float64), 2)
    h, w = L.shape
    s = sum(P[dy:dy + h, dx:dx + w] for dy in range(5) for dx in range(5))
    n = sum(Mk[dy:dy + h, dx:dx + w] for dy in range(5) for dx in range(5))
    return L - s / np.maximum(n, 1)


def fidelity(der, ref):
    """Потеря энергии фактуры (1 - std высоких частот L вывода / опоры) и потеря деталей (1 - средний модуль
    градиента L вывода / опоры). Опора - правда, без правды - HD основы в ориентации цепочки. Диагностика."""
    op = (der[..., 3] >= V2.ALPHA_OPAQUE) & (ref[..., 3] >= V2.ALPHA_OPAQUE)
    if op.sum() < 64:
        return {"texture_energy_loss": None, "detail_loss": None}
    Ld, Lr = V2.lab(der[..., :3])[..., 0], V2.lab(ref[..., :3])[..., 0]
    ed, er = float(_hp(Ld, op)[op].std()), float(_hp(Lr, op)[op].std())
    g = lambda L: np.hypot(*np.gradient(L))
    in2 = op & np.roll(op, 1, 0) & np.roll(op, -1, 0) & np.roll(op, 1, 1) & np.roll(op, -1, 1)
    gd, gr = float(g(Ld)[in2].mean()), float(g(Lr)[in2].mean())
    return {"texture_energy_loss": round(1 - ed / er, 4) if er > 1e-9 else None,
            "detail_loss": round(1 - gd / gr, 4) if gr > 1e-9 else None}


# ---------- оценка формы (DEV и подтверждение) ----------

def eval_pair(pair, keep_img=False):
    """Формы пары как в DEV: BASE дважды (детерминизм), EXACT_MAP и SOFT_MAP - база маршрутизации ΔE."""
    rows = []
    for form, ob, ot, hd, truth in M.forms(pair):
        cid = "%s>%s/%s" % (pair["base"], pair["member"], form)
        row = {"case": cid, "pair": [pair["base"], pair["member"]], "category": pair["category"], "form": form,
               "measure_invalid": []}
        der, ch = B.derive(hd, ob, ot, "recolor")
        der2, ch2 = B.derive(hd, ob, ot, "recolor")
        row["deterministic"] = bool(((der is None and der2 is None) or (der is not None and der2 is not None
                                                                          and (der == der2).all())) and ch == ch2)
        row["chain_ok"] = chain_ok(ch)
        if der is None:
            row.update(status="REFUSED", struct=1, geometry=None)
            rows.append(row)
            continue
        g = ch["geometry_transform"]
        hdo, obo = D3.geo(hd, g), D3.geo(ob, g)
        gt, _ = A3.gates3(der, hdo, obo, ot)
        row.update(status="DERIVED", geometry=g, struct=int(sum(gt[k] for k in STRUCT)),
                   struct_list={k: gt[k] for k in STRUCT if gt[k]}, art=int(gt["unintended_local_artifacts"]),
                   map=int(gt["wrong_palette_mapping"]))
        row.update(fidelity(der, truth if truth is not None else hdo))
        if truth is not None:
            ts = M.art_stats(truth, hdo, obo, ot)
            tg, _ = A3.gates3(truth, hdo, obo, ot)
            cs = M.art_stats(der, hdo, obo, ot)
            if len(M.flagged(ts)) != tg["unintended_local_artifacts"] or \
                    len(M.flagged(cs)) != gt["unintended_local_artifacts"]:
                row["measure_invalid"].append("счёт классов пятен не равен воротам")
            new, over = M.new_artifacts(cs, ts)
            ex, _ = D3.derive(hd, ob, ot, "recolor", mode="EXACT_MAP")
            so, _ = D3.derive(hd, ob, ot, "recolor", mode="SOFT_MAP", soft_scope="support")
            row.update(truth_art=int(tg["unintended_local_artifacts"]), truth_map=int(tg["wrong_palette_mapping"]),
                       new_art=len(new), new_art_list=new, de=round(M.de_mean(der, truth), 4),
                       de_exact=round(M.de_mean(ex, truth), 4) if ex is not None else None,
                       de_soft=round(M.de_mean(so, truth), 4) if so is not None else None)
        if form == "SYN" and pair["category"] == "local":
            lk = M.seam_setup(obo, ot)
            tl, tc, _td = M.seam(truth, lk)
            pos = sum(M.closer_other(e["tb"], e, e["sideA"], np.zeros_like(e["sideA"]))[0] +
                      M.closer_other(e["ta"], e, np.zeros_like(e["sideB"]), e["sideB"])[0] for e in lk)
            if tl != 0 or pos != tc:
                row["measure_invalid"].append("контроль причинной утечки: правда %d, считается %d, положительный %d"
                                              % (tl, tc, pos))
            sl, _c, sdiag = M.seam(der, lk)
            row.update(seam_leak=sl, seam_counted=tc, seam_positive=pos, seam_truth=tl, seam_diag=sdiag)
        if keep_img:
            row["_img"] = (der, hdo, ot, truth)
        rows.append(row)
    return rows


def strip(rows):
    return [{k: v for k, v in r.items() if k != "_img"} for r in rows]


def de_routed(r):
    base = [x for x in (r.get("de_exact"), r.get("de_soft")) if x is not None]
    return "de" in r and base and r["de"] > min(base) + DE_MARGIN + 1e-12


def confirm_hard(rows):
    h = {}
    bad = [r["case"] for r in rows if r["status"] != "DERIVED" or r["struct"]]
    h["STRUCT"] = {"pass": not bad, "detail": "STRUCT > 0 / отказ Stage A: %s" % (", ".join(bad) or "нет")}
    sl = [(r["case"], r["seam_leak"], r["seam_counted"]) for r in rows if "seam_leak" in r]
    h["CAUSAL_SEAM"] = {"pass": all(x[1] == 0 for x in sl),
                        "detail": "; ".join("%s %d из %d" % x for x in sl) or "local-пар с причинным следом нет"}
    mp = [(r["case"], r["map"]) for r in rows if r["status"] == "DERIVED" and r["form"] != "REAL" and r["map"]]
    h["MAPPING_TRUTH"] = {"pass": not mp, "detail": "wrong_palette_mapping > 0 при правде: %s" % (
        ", ".join("%s %d" % x for x in mp) or "нет")}
    nd = [r["case"] for r in rows if not r["deterministic"]]
    h["DETERMINISM"] = {"pass": not nd, "detail": "не детерминированы: %s" % (", ".join(nd) or "нет")}
    nc = [r["case"] for r in rows if not r["chain_ok"]]
    h["BASE_ONLY"] = {"pass": not nc and impl_purity()["pure"],
                      "detail": "цепочка не BASE: %s; чистота кода %s" % (", ".join(nc) or "нет", impl_purity())}
    inv = [(r["case"], r["measure_invalid"]) for r in rows if r["measure_invalid"]]
    return h, inv


def confirm_routes(rows):
    """Замороженное правило: все REAL, SYN_DITHER, SD; SYN - при новых пятнах против правды или ΔE сверх базы."""
    out = {}
    for r in rows:
        if r["status"] != "DERIVED":
            continue
        why = []
        if r["form"] in HUMAN_CONFIRM_FORMS:
            why.append("форма %s" % r["form"])
        if r["form"] == "REAL" and r["art"]:
            why.append("REAL пятна %d" % r["art"])
        if r["form"] == "REAL" and r["map"]:
            why.append("REAL mapping %d" % r["map"])
        if r.get("new_art"):
            why.append("новые пятна против правды %d" % r["new_art"])
        if de_routed(r):
            why.append("ΔE %.3f > min(EXACT, SOFT) + %.1f" % (r["de"], DE_MARGIN))
        if why:
            out[r["case"]] = why
    return out


# ---------- devcheck ----------

def do_devcheck():
    if os.path.exists(os.path.join(OUT, "spec.json")):
        raise SystemExit("spec уже заморожен - devcheck вошёл в него и не повторяется")
    if fsha(DEV_SPEC) != DEV_SPEC_SHA:
        raise SystemExit("dev_spec_v3.json не тот")
    sp3 = A3.load_json(rel(DEV_SPEC))
    R = A3.load_json(rel(DEV + "/dev3_results.json"))
    ref = {c["case"]: c for c in R["cases"]}
    rows, diffs = [], []
    for pair in sp3["dev"]:
        for r in eval_pair(pair):
            p = ref[r["case"]]["variants"]["PRIOR"]
            want = {k: p[k] for k in ("struct", "art", "map", "new_art", "seam_leak") if p.get(k) is not None}
            if p.get("de") is not None:
                want["de"] = round(p["de"], 4)
            got = {k: r.get(k) for k in want}
            same = True
            for form, ob, ot, hd, _t in M.forms(pair):
                if "%s>%s/%s" % (pair["base"], pair["member"], form) != r["case"]:
                    continue
                der, ch = B.derive(hd, ob, ot, "recolor")
                g = ch["geometry_transform"]
                hdo, obo = D3.geo(hd, g), D3.geo(ob, g)
                d = E.weights(hdo, obo, ot)
                same = bool((E.colorize(hdo, d, d["pri"]) == der).all())
            ok = same and r["deterministic"] and r["chain_ok"] and not r["measure_invalid"] and all(
                abs(got[k] - want[k]) < 1e-3 if isinstance(want[k], float) else got[k] == want[k] for k in want)
            if not ok:
                diffs.append({"case": r["case"], "byte_equal_prior": same, "want": want, "got": got,
                              "invalid": r["measure_invalid"]})
            rows.append(r)
    h, inv = confirm_hard(rows)
    rt = confirm_routes(rows)
    res = {"profile": PROFILE, "what": "BASE на DEV-парах против PRIOR стенда V3.3_DEV и dev3_results.json",
           "dev_spec_sha256": DEV_SPEC_SHA, "dev3_results_sha256": fsha(DEV + "/dev3_results.json"),
           "impl_sha256": fsha(IMPL), "self_sha256": fsha(SELF), "purity": impl_purity(), "cases": len(rows),
           "diffs": diffs, "hard_on_dev": {k: v["pass"] for k, v in h.items()},
           "hard_detail": {k: v["detail"] for k, v in h.items() if not v["pass"]}, "measure_invalid": inv,
           "human_routes_on_dev": rt, "rows": strip(rows),
           "ok": not diffs and not inv and all(v["pass"] for v in h.values()),
           "run_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    dump("devcheck.json", res)
    print("devcheck: случаев %d, расхождений %d, контроли мер %s, hard на DEV %s, в human review %d -> %s" % (
        len(rows), len(diffs), "ok" if not inv else inv, res["hard_on_dev"], len(rt), "OK" if res["ok"] else "НЕ OK"))
    for d in diffs[:10]:
        print("  ", json.dumps(d, ensure_ascii=False)[:400])


# ---------- spec ----------

def impl_state():
    return {"module": IMPL, "sha256": fsha(IMPL), "version": B.VERSION, "color_transform": B.COLOR_TRANSFORM,
            "purity": impl_purity(), "constants_from_v31": {"CHROMA_W0": D31.CHROMA_W0, "CHROMA_W1": D31.CHROMA_W1}}


def stage_a_state():
    return {"module": STAGE_A, "sha256": fsha(STAGE_A), "version": D3.VERSION}


def stage_b_ref_state():
    return {"module": STAGE_B_REF, "sha256": fsha(STAGE_B_REF), "version": D31.VERSION}


def v31_state():
    sp = A3.load_json(rel(V31_OUT + "/spec.json"))
    return {"spec_sha256": sp["sha256"], "spec_file_sha256": fsha(V31_OUT + "/spec.json"),
            "cases": [c["id"] for c in sp["cases"]]}


def dev_state():
    dc = load("devcheck.json")
    return {"dev_spec_sha256": fsha(DEV_SPEC), "dev3_results_sha256": fsha(DEV + "/dev3_results.json"),
            "devcheck_sha256": osha(os.path.join(OUT, "devcheck.json")), "devcheck_ok": dc["ok"],
            "devcheck_impl_sha256": dc["impl_sha256"], "devcheck_self_sha256": dc["self_sha256"]}


def confirm_state():
    p = DEV + "/confirm_reserved.json"
    return {"file": p, "file_sha256": fsha(p), "sha256": hashlib.sha256(M.confirm_blob(p)).hexdigest(), "count": 15}


def spec_body():
    sp31 = A3.load_json(rel(V31_OUT + "/spec.json"))
    if stage_a_state()["sha256"] != sp31["stage_a"]["sha256"]:
        raise SystemExit("Stage A не тот, что в приёмке V3.1")
    if stage_b_ref_state()["sha256"] != sp31["implementation"]["sha256"]:
        raise SystemExit("derive_recolor_v31.py не тот, что в приёмке V3.1")
    cs = confirm_state()
    if cs["sha256"] != CONFIRM_SHA:
        raise SystemExit("confirm_reserved.json не тот, что отложен в dev_spec.json")
    dv = dev_state()
    if not dv["devcheck_ok"] or dv["devcheck_impl_sha256"] != fsha(IMPL) or dv["devcheck_self_sha256"] != fsha(SELF):
        raise SystemExit("devcheck не пройден или сделан на другом коде - сначала devcheck")
    if not impl_purity()["pure"]:
        raise SystemExit("в реализации BASE есть лишние импорты или следы unmix/ASL/eligibility: %s" % impl_purity())
    return {
        "profile": PROFILE, "decision": DECISION, "implementation": impl_state(), "stage_a": stage_a_state(),
        "stage_b_ref": stage_b_ref_state(), "v31_dependency": v31_state(), "dev_dependency": dv,
        "confirm_reserved": cs,
        "hard": {
            "regression_old27": {
                "H1_STRUCT": "every case DERIVED, every STRUCTURAL gate 0 (%s)" % ", ".join(STRUCT),
                "H4_SEAM": "cases %s: causal seam leakage BASE = 0 (leak_rule V3.1); measure controls: truth = 0, "
                           "SOFT_MAP > 0 (otherwise INVALID_MEASURE)" % ", ".join(LEAK),
                "H5_REGRESSION": "cases %s: %s = 0 literally" % (", ".join(H5_CASES), H5_GATE),
                "H6_DETERMINISM": "every case: derive twice -> byte-identical output and equal chain",
                "H7_MAPPING_TRUTH": "every synthetic case (truth known): BASE wrong_palette_mapping = 0 literally; "
                                    "truth's own count is diagnostic only (dithered truth can fail the gate itself: "
                                    "DEV URBAN40K:24 SD truth = 3, BASE = 0) - literal gate is the stricter reading",
                "H8_BASE_ONLY": "chain version/color_transform = BASE; implementation imports only %s, no "
                                "unmix/ASL/eligibility in code" % ", ".join(ALLOWED_IMPORTS)},
            "confirmation15": {
                "STRUCT": "STRUCT = 0 on all forms; Stage A refusal = fail",
                "CAUSAL_SEAM": "causal seam leakage = 0 (dev_spec_v3 CAUSAL_SEAM, SYN of local pairs)",
                "MAPPING_TRUTH": "BASE wrong_palette_mapping = 0 on SYN, SYN_DITHER, SD (truth known); truth's own "
                                 "count diagnostic only, as H7",
                "DETERMINISM": "derive twice -> byte-identical, equal chain",
                "BASE_ONLY": "as H8"},
            "measure_controls": "not satisfied -> INVALID_MEASURE (not PASS), specialist decides",
            "regression_pass": "REGRESSION PASS = H1, H4, H5, H6, H7, H8 all PASS and measure controls satisfied",
            "confirmation_pass": "CONFIRMATION PASS = all five PASS and measure controls satisfied",
            "fail": "any hard FAIL -> BASE_V1 FAIL; nothing is retuned"},
        "diagnostic": {
            "measures": ["REAL unintended_local_artifacts", "REAL wrong_palette_mapping",
                         "ΔE to truth (BASE, EXACT_MAP, SOFT_MAP support; V3.1 only in report)",
                         "new artifacts vs truth (incl. dither fidelity C2, SYN_DITHER, SD)",
                         "texture_energy_loss = 1 - std(highpass5x5 L) BASE / reference",
                         "detail_loss = 1 - mean |grad L| BASE / reference",
                         "reference = truth, without truth - base HD in chain orientation"],
            "rule": "diagnostics never FAIL BASE; they only route cases into mandatory human review"},
        "human": {
            "old27_mandatory": list(HUMAN_OLD),
            "old27_routed": "any real case with unintended_local_artifacts > 0 or wrong_palette_mapping > 0; "
                            "any synthetic case with new artifacts vs truth > 0 or ΔE > min(EXACT_MAP, SOFT_MAP) + %.1f"
                            % DE_MARGIN,
            "confirmation_mandatory_forms": list(HUMAN_CONFIRM_FORMS),
            "confirmation_routed": "SYN forms: new artifacts vs truth > 0 or ΔE > min(EXACT_MAP, SOFT_MAP) + %.1f; "
                                   "REAL with artifacts/mapping > 0 already mandatory" % DE_MARGIN,
            "card": ["member original x4", "base HD (chain orientation)", "BASE output", "truth (if known)"],
            "card_scale": CARD_SCALE, "card_floor_rgb": list(A3.FLOOR),
            "blind": "cards shuffled (seed %d), anonymous ids; no case id, no machine gates, no V3.1/V3.2; the key "
                     "is kept outside the reviewer folder" % CARD_SEED,
            "question": QUESTION, "answers": list(ANSWERS)},
        "final_rule": ("BASE_V1 eligible for VERIFIED = REGRESSION PASS + CONFIRMATION PASS + every human card PASS. "
                       "Any card FAIL -> BASE_V1 FAIL (the case is FAIL even if machine gates are green). Any UNSURE "
                       "(no FAIL) -> not PASS, back to specialist. VERIFIED is set by a human."),
        "sequence": ["devcheck (before freeze)", "spec", "regress (once)", "confirm (only if REGRESSION PASS, once)",
                     "cards (only if both PASS)", "human review", "final"],
        "forbidden": ["no unmix, ASL, ID/ST/CY eligibility", "no new coefficients; DE_MARGIN routes only",
                      "Stage A, INTERPOLATED_MAP, threshold 10, old cases, C1 unchanged", "V7 and families unchanged",
                      "857/1030 and 173 refusals untouched", "no model, no GPU",
                      "TEXTURE_TRANSFER not started"],
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
    print("spec заморожен: %s, sha %s, код BASE %s" % (p, body["sha256"][:12], body["implementation"]["sha256"][:12]))


def load_spec():
    sp = load("spec.json")
    if V2.jsha({k: sp[k] for k in BODY}) != sp["sha256"]:
        raise SystemExit("spec.json изменён после заморозки")
    for nm, now, was in (("код BASE", impl_state(), sp["implementation"]), ("Stage A", stage_a_state(), sp["stage_a"]),
                         ("V3.1", stage_b_ref_state(), sp["stage_b_ref"]), ("приёмка V3.1", v31_state(),
                                                                            sp["v31_dependency"]),
                         ("DEV", dev_state(), sp["dev_dependency"]), ("набор подтверждения", confirm_state(),
                                                                       sp["confirm_reserved"])):
        if json.loads(json.dumps(now)) != was:
            raise SystemExit("%s изменился после заморозки" % nm)
    if fsha(SELF) != sp["self_sha256"]:
        raise SystemExit("сама приёмка BASE_V1 изменилась после заморозки")
    return sp


# ---------- регрессия ----------

def run_case(c, inputs):
    ob, ot, hd, truth = A3.inputs_of(c)
    if A31.got_inputs(c) != inputs[c["id"]]:
        raise SystemExit("%s: входы не те, что в spec V3.1" % c["id"])
    der, chain = B.derive(hd, ob, ot, c["route"])
    der2, chain2 = B.derive(hd, ob, ot, c["route"])
    det = (der is None and der2 is None) or (der is not None and der2 is not None and (der == der2).all())
    row = {"kind": c["kind"], "what": c["what"], "route": c["route"], "base": c["base"], "member": c.get("member"),
           "chain": chain, "chain_ok": chain_ok(chain), "deterministic": bool(det and chain == chain2),
           "measure_invalid": []}
    if der is None:
        row.update(status="REFUSED", gates={g: 0 for g in STRUCT})
        row["gates"]["geometry_support_mismatch"] = min(chain["geometry_resolution"]["support_mismatch"].values())
        return row
    g = chain["geometry_transform"]
    hd_o, ob_o = D3.geo(hd, g), D3.geo(ob, g)
    gt, info = A3.gates3(der, hd_o, ob_o, ot)
    row.update(status="DERIVED", gates=gt)
    row["coverage"] = A3.coverage3(info, der, hd_o, ob_o, ot, truth if truth is not None else der)
    d31, _ = D31.derive(hd, ob, ot, c["route"])
    ex, _ = D3.derive(hd, ob, ot, c["route"], mode="EXACT_MAP")
    so, _ = D3.derive(hd, ob, ot, c["route"], mode="SOFT_MAP", soft_scope="support")
    sup = (ob_o[..., 3] > 0) & (ot[..., 3] > 0)
    row["modes"] = {nm: A31.mode_diag(a, hd_o, ob_o, ot, truth, sup) for nm, a in
                    (("BASE", der), ("V3.1", d31), ("EXACT_MAP", ex), ("SOFT_MAP", so))}
    row.update(fidelity(der, truth if truth is not None else hd_o))
    if truth is not None:
        tg = "MIRROR_X" if c.get("mirror_member") else "IDENTITY"
        tgt, _ = A3.gates3(truth, D3.geo(hd, tg), D3.geo(ob, tg), ot)
        row["truth_gates"] = tgt
        row["truth_map"] = int(tgt["wrong_palette_mapping"])
        new, _over = M.new_artifacts(M.art_stats(der, hd_o, ob_o, ot), M.art_stats(truth, hd_o, ob_o, ot))
        row.update(new_art=len(new), new_art_list=new, de=row["modes"]["BASE"]["main"]["mean_de"],
                   de_exact=row["modes"]["EXACT_MAP"]["main"]["mean_de"],
                   de_soft=row["modes"]["SOFT_MAP"]["main"]["mean_de"])
        save_png(truth, "truth", c["id"] + ".png")
    if c["id"] in LEAK:
        ta, tb, split = A31.side_truths(c, ob)
        row["leak"] = {"split": split, "BASE": A31.leakage(der, ta, tb, split), "V3.1": A31.leakage(d31, ta, tb, split),
                       "EXACT_MAP": A31.leakage(ex, ta, tb, split), "SOFT_MAP": A31.leakage(so, ta, tb, split),
                       "truth": A31.leakage(truth, ta, tb, split)}
    save_png(der, "derived", c["id"] + ".png")
    save_png(d31, "v31", c["id"] + ".png")
    save_png(hd_o, "hd", c["id"] + ".png")
    save_png(ob_o, "orig", c["id"] + "_base.png")
    save_png(ot, "orig", c["id"] + "_member.png")
    return row


def hard(res):
    cs = res["cases"]
    h = {}
    bad1 = [k for k, r in cs.items() if r["status"] != "DERIVED" or any(r["gates"][g] for g in STRUCT)]
    h["H1_STRUCT"] = {"pass": not bad1, "detail": "STRUCTURAL > 0 / отказ: %s" % (", ".join(
        "%s %s" % (k, {g: cs[k]["gates"][g] for g in STRUCT if cs[k]["gates"][g]} or cs[k]["status"]) for k in bad1)
        or "нет")}
    d4, ok4, inv4 = [], True, []
    for k in LEAK:
        lk = cs[k].get("leak")
        if lk is None:
            ok4 = False
            d4.append("%s нет меры (отказ)" % k)
            continue
        li, lt, ls = lk["BASE"]["leak_px"], lk["truth"]["leak_px"], lk["SOFT_MAP"]["leak_px"]
        ok4 &= li == 0
        if lt != 0 or ls == 0:
            inv4.append(k)
        d4.append("%s утечка BASE %d, правда %d, SOFT %d из %d" % (k, li, lt, ls, lk["BASE"]["counted_px"]))
    h["H4_SEAM"] = {"pass": ok4, "detail": "; ".join(d4), "measure_invalid": inv4}
    h["H5_REGRESSION"] = {"pass": all(cs[k].get("gates", {}).get(H5_GATE, 0) == 0 and cs[k]["status"] == "DERIVED"
                                      for k in H5_CASES),
                          "detail": "%s: %s" % (H5_GATE, ", ".join("%s %s" % (k, cs[k].get("gates", {}).get(H5_GATE))
                                                                   for k in H5_CASES))}
    bad6 = [k for k, r in cs.items() if not r["deterministic"]]
    h["H6_DETERMINISM"] = {"pass": not bad6, "detail": "не детерминированы: %s" % (", ".join(bad6) or "нет")}
    bad7 = [(k, r["gates"]["wrong_palette_mapping"]) for k, r in cs.items()
            if r["kind"] == "synthetic" and r["status"] == "DERIVED" and r["gates"]["wrong_palette_mapping"]]
    h["H7_MAPPING_TRUTH"] = {"pass": not bad7, "detail": "синтетика с mapping > 0: %s" % (
        ", ".join("%s %d" % x for x in bad7) or "нет")}
    nc = [k for k, r in cs.items() if not r["chain_ok"]]
    pu = impl_purity()
    h["H8_BASE_ONLY"] = {"pass": not nc and pu["pure"], "detail": "цепочка не BASE: %s; импорты %s, слова %s" % (
        ", ".join(nc) or "нет", pu["imports"], pu["forbidden_words"] or "нет")}
    return h


def measure_invalid(res, h):
    inv = [(k, r["measure_invalid"]) for k, r in res["cases"].items() if r["measure_invalid"]]
    inv += [(k, ["контроль утечки: правда > 0 или SOFT = 0"]) for k in h["H4_SEAM"]["measure_invalid"]]
    return inv


def old27_routes(res):
    out = {}
    for k, r in res["cases"].items():
        why = []
        if k in HUMAN_OLD:
            why.append("обязательный")
        if r["status"] == "DERIVED" and r["kind"] == "real":
            if r["gates"]["unintended_local_artifacts"]:
                why.append("REAL пятна %d" % r["gates"]["unintended_local_artifacts"])
            if r["gates"]["wrong_palette_mapping"]:
                why.append("REAL mapping %d" % r["gates"]["wrong_palette_mapping"])
        if r.get("new_art"):
            why.append("новые пятна против правды %d" % r["new_art"])
        if de_routed(r):
            why.append("ΔE %.2f > min(EXACT, SOFT) + %.1f" % (r["de"], DE_MARGIN))
        if why:
            out[k] = why
    return out


def do_regress():
    sp = load_spec()
    if os.path.exists(os.path.join(OUT, "regression.json")):
        raise SystemExit("regression.json уже есть - регрессия прогоняется один раз")
    sp31 = A3.load_json(rel(V31_OUT + "/spec.json"))
    res = {"profile": PROFILE, "spec_sha256": sp["sha256"], "implementation": sp["implementation"],
           "run_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "cases": {}}
    for c in sp31["cases"]:
        res["cases"][c["id"]] = run_case(c, sp31["inputs"])
        print(c["id"], res["cases"][c["id"]]["status"], flush=True)
    h = hard(res)
    inv = measure_invalid(res, h)
    v = "INVALID_MEASURE" if inv else ("PASS" if all(x["pass"] for x in h.values()) else "FAIL")
    res.update(verdict=v, hard=h, measure_invalid=inv, human_routes=old27_routes(res))
    dump("regression.json", res)
    write_regression_md(res, sp)
    print("регрессия: %s; %s" % (v, "; ".join("%s %s" % (k, "PASS" if x["pass"] else "FAIL") for k, x in h.items())))


def _f(x, fmt="%.2f"):
    return "-" if x is None else fmt % x


def write_regression_md(res, sp):
    cs, h = res["cases"], res["hard"]
    L = ["# DERIVE_RECOLOR_BASE_ACCEPTANCE_V1 - регрессия старых 27", "",
         "Spec `%s`, код BASE `%s` (%s), прогон %s." % (sp["sha256"][:12], sp["implementation"]["sha256"][:12],
                                                       sp["implementation"]["version"], res["run_at"]), "",
         "**REGRESSION %s** (%s)." % (res["verdict"], sp["hard"]["regression_pass"]), "",
         "| | условие | итог | подробно |", "|---|---|---|---|"]
    for k, x in h.items():
        L.append("| %s | %s | %s | %s |" % (k, sp["hard"]["regression_old27"][k], "PASS" if x["pass"] else "**FAIL**",
                                            x["detail"]))
    if res["measure_invalid"]:
        L += ["", "Контроли мер не выполнены: " + "; ".join("%s: %s" % (c, ", ".join(v)) for c, v in res["measure_invalid"])]
    L += ["", "## Диагностика (не валит; направляет в human review)", "",
          "| случай | что | цепочка | пятна BASE / V3.1 | mapping BASE / V3.1 | новые против правды | ΔE BASE / EXACT / SOFT / V3.1 "
          "| потеря фактуры | потеря деталей | human review |", "|---|---|---|---|---|---|---|---|---|---|"]
    for k, r in cs.items():
        what = r["what"] + (" %s -> %s" % (r["base"], r["member"]) if r["kind"] == "real" else "")
        if r["status"] != "DERIVED":
            L.append("| %s | %s | REFUSED | | | | | | | %s |" % (k, what, "; ".join(res["human_routes"].get(k, []))))
            continue
        m = r["modes"]
        vb, v31 = m["BASE"]["visual"], m["V3.1"]["visual"]
        de = "-" if "main" not in m["BASE"] else "%.2f / %.2f / %.2f / %.2f" % tuple(
            m[n]["main"]["mean_de"] for n in ("BASE", "EXACT_MAP", "SOFT_MAP", "V3.1"))
        L.append("| %s | %s | %s | %d / %d | %d / %d | %s | %s | %s | %s | %s |" % (
            k, what, r["chain"]["geometry_transform"], vb.get("unintended_local_artifacts", 0),
            v31.get("unintended_local_artifacts", 0), vb.get("wrong_palette_mapping", 0), v31.get("wrong_palette_mapping", 0),
            r.get("new_art", "-"), de, _f(r["texture_energy_loss"], "%.3f"), _f(r["detail_loss"], "%.3f"),
            "; ".join(res["human_routes"].get(k, [])) or "-"))
    write_md("regression.md", L)


# ---------- подтверждение ----------

def do_confirm():
    sp = load_spec()
    reg = load("regression.json")
    if reg["spec_sha256"] != sp["sha256"]:
        raise SystemExit("regression.json от другого spec")
    if reg["verdict"] != "PASS":
        raise SystemExit("REGRESSION %s - набор подтверждения не открывается" % reg["verdict"])
    p = os.path.join(OUT, "confirmation.json")
    if os.path.exists(p):
        raise SystemExit("confirmation.json уже есть - подтверждение прогоняется один раз")
    raw = M.confirm_blob(sp["confirm_reserved"]["file"])
    if hashlib.sha256(raw).hexdigest() != CONFIRM_SHA:
        raise SystemExit("confirm_reserved.json не тот")
    pairs = json.loads(raw.decode("utf-8"))
    if len(pairs) != 15:
        raise SystemExit("в наборе подтверждения %d пар, ожидалось 15" % len(pairs))
    rows = []
    for pair in pairs:
        for r in eval_pair(pair, keep_img=True):
            if "_img" in r:
                der, hdo, ot, truth = r["_img"]
                stem = r["case"].replace(":", "_").replace(">", "__").replace("/", "_")
                save_png(der, "confirm", stem + "_base.png")
                save_png(hdo, "confirm", stem + "_hd.png")
                save_png(ot, "confirm", stem + "_member.png")
                if truth is not None:
                    save_png(truth, "confirm", stem + "_truth.png")
                r["stem"] = stem
            rows.append(r)
            print("%-48s %s S%s map %s new %s seam %s dE %s" % (r["case"], r["status"], r["struct"], r.get("map", "-"),
                                                               r.get("new_art", "-"), r.get("seam_leak", "-"),
                                                               r.get("de", "-")), flush=True)
    h, inv = confirm_hard(rows)
    verdict = "INVALID_MEASURE" if inv else ("PASS" if all(x["pass"] for x in h.values()) else "FAIL")
    res = {"profile": PROFILE, "spec_sha256": sp["sha256"],
           "regression_sha256": osha(os.path.join(OUT, "regression.json")), "run_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "pairs": pairs, "cases": strip(rows), "hard": h, "measure_invalid": inv, "verdict": verdict,
           "human_routes": confirm_routes(rows)}
    dump("confirmation.json", res)
    write_confirmation_md(res)
    print("подтверждение: %s; %s" % (verdict, "; ".join("%s %s" % (k, "PASS" if x["pass"] else "FAIL") for k, x in h.items())))


def write_confirmation_md(res):
    L = ["# DERIVE_RECOLOR_BASE_ACCEPTANCE_V1 - подтверждение 15 пар (один прогон)", "",
         "Прогон %s, spec `%s`." % (res["run_at"], res["spec_sha256"][:12]), "", "**CONFIRMATION %s**" % res["verdict"], "",
         "| условие | итог | подробно |", "|---|---|---|"]
    for k, x in res["hard"].items():
        L.append("| %s | %s | %s |" % (k, "PASS" if x["pass"] else "**FAIL**", x["detail"]))
    if res["measure_invalid"]:
        L += ["", "Контроли мер не выполнены: " + "; ".join("%s: %s" % (c, ", ".join(v)) for c, v in res["measure_invalid"])]
    L += ["", "## Диагностика (не валит; направляет в human review)", "",
          "| случай | категория | цепочка | STRUCT | пятна | mapping | новые против правды | ΔE BASE / EXACT / SOFT | шов "
          "| потеря фактуры | потеря деталей | human review |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in res["cases"]:
        if r["status"] != "DERIVED":
            L.append("| %s | %s | REFUSED | 1 | | | | | | | | |" % (r["case"], r["category"]))
            continue
        de = ("%.3f / %s / %s" % (r["de"], _f(r["de_exact"], "%.3f"), _f(r["de_soft"], "%.3f"))) if "de" in r else "-"
        L.append("| %s | %s | %s | %d | %d | %d | %s | %s | %s | %s | %s | %s |" % (
            r["case"], r["category"], r["geometry"], r["struct"], r["art"], r["map"], r.get("new_art", "-"), de,
            ("%d из %d" % (r["seam_leak"], r["seam_counted"])) if "seam_leak" in r else "-",
            _f(r["texture_energy_loss"], "%.3f"), _f(r["detail_loss"], "%.3f"),
            "; ".join(res["human_routes"].get(r["case"], [])) or "-"))
    write_md("confirmation.md", L)


# ---------- карточки human review ----------

def card_image(panels, scale):
    pw = max(a.shape[1] for a in panels if a is not None) * scale
    ph = max(a.shape[0] for a in panels if a is not None) * scale
    heads = ["member original x4", "base HD", "BASE recolor", "truth"]
    n = 4 if panels[3] is not None else 3
    im = Image.new("RGB", (n * pw + (n - 1) * 8 + 16, ph + 40), (24, 24, 28))
    dr = ImageDraw.Draw(im)
    for i in range(n):
        dr.text((8 + i * (pw + 8), 6), heads[i], fill=(220, 220, 220))
        im.paste(M.panel(panels[i], scale).convert("RGB"), (8 + i * (pw + 8), 30))
    return im


def do_cards():
    sp = load_spec()
    reg, conf = load("regression.json"), load("confirmation.json")
    if reg["verdict"] != "PASS" or conf["verdict"] != "PASS" or conf["spec_sha256"] != sp["sha256"]:
        raise SystemExit("карточки - только при PASS регрессии и подтверждения (сейчас %s / %s)" % (
            reg["verdict"], conf["verdict"]))
    if os.path.exists(os.path.join(OUT, "cards_key.json")):
        raise SystemExit("карточки уже собраны - они неизменяемы")
    x4 = lambda a: np.repeat(np.repeat(a, 4, 0), 4, 1)
    ld = lambda *p: A3.read_png(os.path.join(OUT, *p))
    items = []
    for k, why in reg["human_routes"].items():
        tp = os.path.join(OUT, "truth", k + ".png")
        items.append(({"set": "old27", "case": k, "why": why},
                      [x4(ld("orig", k + "_member.png")), ld("hd", k + ".png"), ld("derived", k + ".png"),
                       A3.read_png(tp) if os.path.exists(tp) else None]))
    for r in conf["cases"]:
        if r["case"] not in conf["human_routes"]:
            continue
        s = r["stem"]
        tp = os.path.join(OUT, "confirm", s + "_truth.png")
        items.append(({"set": "confirmation15", "case": r["case"], "why": conf["human_routes"][r["case"]]},
                      [x4(ld("confirm", s + "_member.png")), ld("confirm", s + "_hd.png"), ld("confirm", s + "_base.png"),
                       A3.read_png(tp) if os.path.exists(tp) else None]))
    random.Random(CARD_SEED).shuffle(items)
    os.makedirs(CARDS, exist_ok=True)
    key = []
    for i, (meta, panels) in enumerate(items, 1):
        cid = "card%03d" % i
        p = os.path.join(CARDS, cid + ".png")
        card_image(panels, CARD_SCALE).save(p)
        key.append(dict(meta, card=cid, png_sha256=osha(p)))
    with open(os.path.join(CARDS, "QUESTION.md"), "w", encoding=ENC, newline="\n") as f:
        f.write("# BASE recolor - human review\n\nFor every card answer one word: PASS, FAIL or UNSURE.\n\n"
                "> %s\n\nPanels: member original x4 | base HD | BASE recolor | truth (only on synthetic cards).\n"
                "UNSURE counts as not PASS. Write the answer into answers.tsv (column verdict), a note is optional.\n"
                % QUESTION)
    with open(os.path.join(CARDS, "answers.tsv"), "w", encoding=ENC, newline="\n") as f:
        f.write("card\tverdict\tnote\n" + "".join("%s\t\t\n" % k["card"] for k in key))
    dump("cards_key.json", {"spec_sha256": sp["sha256"], "seed": CARD_SEED, "cards": key,
                            "answers_template_sha256": osha(os.path.join(CARDS, "answers.tsv")),
                            "made_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
    print("карточек %d (старые 27: %d, подтверждение: %d) -> %s" % (
        len(key), sum(k["set"] == "old27" for k in key), sum(k["set"] != "old27" for k in key), CARDS))


# ---------- итог ----------

def read_answers():
    p = os.path.join(CARDS, "answers.tsv")
    rows = [ln.rstrip("\n").split("\t") for ln in open(p, encoding=ENC).read().splitlines()[1:] if ln.strip()]
    return {r[0]: (r[1].strip().upper() if len(r) > 1 else "", r[2] if len(r) > 2 else "") for r in rows}


def human_state():
    key = load("cards_key.json")
    for k in key["cards"]:
        if osha(os.path.join(CARDS, k["card"] + ".png")) != k["png_sha256"]:
            raise SystemExit("%s изменилась после сборки" % k["card"])
    ans = read_answers()
    miss = [k["card"] for k in key["cards"] if ans.get(k["card"], ("",))[0] not in ANSWERS]
    if miss:
        return "AWAITING_HUMAN", key, ans, miss
    v = [ans[k["card"]][0] for k in key["cards"]]
    return ("FAIL" if "FAIL" in v else "UNSURE" if "UNSURE" in v else "PASS"), key, ans, []


def do_final():
    sp = load_spec()
    reg, conf = load("regression.json"), load("confirmation.json")
    st, key, ans, miss = human_state()
    if st == "AWAITING_HUMAN":
        raise SystemExit("нет ответа по %d карточкам: %s" % (len(miss), ", ".join(miss[:20])))
    over = "ELIGIBLE_FOR_VERIFIED" if reg["verdict"] == conf["verdict"] == st == "PASS" else (
        "FAIL" if st == "FAIL" or "FAIL" in (reg["verdict"], conf["verdict"]) else "NOT_PASS_" + st)
    rows = [dict(k, verdict=ans[k["card"]][0], note=ans[k["card"]][1]) for k in key["cards"]]
    res = {"profile": PROFILE, "spec_sha256": sp["sha256"], "regression": reg["verdict"],
           "confirmation": conf["verdict"], "human": st, "overall": over, "cards": rows,
           "answers_sha256": osha(os.path.join(CARDS, "answers.tsv")), "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    dump("final.json", res)
    L = ["# DERIVE_RECOLOR_BASE_ACCEPTANCE_V1 - итог human review", "", "Правило: " + sp["final_rule"], "",
         "REGRESSION %s, CONFIRMATION %s, HUMAN %s -> **%s**" % (reg["verdict"], conf["verdict"], st, over), "",
         "| карточка | набор | случай | вердикт | заметка | почему в review |", "|---|---|---|---|---|---|"]
    for r in rows:
        L.append("| %s | %s | %s | %s | %s | %s |" % (r["card"], r["set"], r["case"], r["verdict"], r["note"],
                                                     "; ".join(r["why"])))
    write_md("final.md", L)
    print("\n".join(L[:5]))


def do_report():
    sp = load_spec()
    L = ["# DERIVE_RECOLOR_BASE_ACCEPTANCE_V1 - сводка", "", "Spec `%s`, код BASE `%s` (%s)." % (
        sp["sha256"][:12], sp["implementation"]["sha256"][:12], sp["implementation"]["version"]), ""]
    if not os.path.exists(os.path.join(OUT, "regression.json")):
        L.append("Регрессия не прогонялась.")
    else:
        reg = load("regression.json")
        L.append("**REGRESSION %s**" % reg["verdict"])
        L += ["- %s %s: %s" % (k, "PASS" if x["pass"] else "FAIL", x["detail"]) for k, x in reg["hard"].items()]
        L.append("- в human review из старых 27: %d (%s)" % (len(reg["human_routes"]), ", ".join(reg["human_routes"])))
        L.append("")
        if os.path.exists(os.path.join(OUT, "confirmation.json")):
            conf = load("confirmation.json")
            L.append("**CONFIRMATION %s**" % conf["verdict"])
            L += ["- %s %s: %s" % (k, "PASS" if x["pass"] else "FAIL", x["detail"]) for k, x in conf["hard"].items()]
            L.append("- в human review из подтверждения: %d" % len(conf["human_routes"]))
        elif reg["verdict"] != "PASS":
            L.append("**BASE_V1: %s** - набор подтверждения не открывался." % reg["verdict"])
        else:
            L.append("Подтверждение не прогонялось.")
        if os.path.exists(os.path.join(OUT, "final.json")):
            fin = load("final.json")
            L += ["", "**HUMAN %s -> %s**" % (fin["human"], fin["overall"])]
        elif os.path.exists(os.path.join(OUT, "cards_key.json")):
            L += ["", "Карточки human review собраны, ответов ещё нет."]
    write_md("report.md", L)
    print("\n".join(L))


def do_check():
    load_spec()
    print("spec, код BASE, Stage A, V3.1, DEV и набор подтверждения не изменились")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("devcheck", "spec", "regress", "confirm", "cards", "final", "report", "check"))
    a = ap.parse_args()
    os.chdir(ROOT)
    {"devcheck": do_devcheck, "spec": do_spec, "regress": do_regress, "confirm": do_confirm, "cards": do_cards,
     "final": do_final, "report": do_report, "check": do_check}[a.cmd]()


if __name__ == "__main__":
    main()
