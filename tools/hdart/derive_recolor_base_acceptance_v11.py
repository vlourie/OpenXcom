"""DERIVE_RECOLOR_BASE_ACCEPTANCE_V1.1 - тот же вывод BASE (tools/hdart/derive_recolor_base_v1.py, Stage A +
INTERPOLATED_MAP), новая семантика жёстких ворот mapping: против правды, а не абсолютно.

Решение: специалист 03.10, передал Vitali в чате. BASE_V1 = FAIL под замороженным spec f981213fbcc6 (источник -
контракт MAPPING_TRUTH: абсолютный 0 при правде, которая сама нарушает ту же меру; вывод не менялся). V1 не трогаем:
модуль derive_recolor_base_acceptance_v1.py, его spec и результаты только читаются.

Mapping V1.1, по каждому классу цвета члена (класс и превышение - ровно как wrong_palette_mapping V2.gates):
  правда <= MAP_DE        -> BASE обязан быть <= MAP_DE, иначе NEW_MAPPING_ERROR;
  правда >  MAP_DE        -> BASE не хуже правды больше чем на EPS, иначе MAPPING_WORSENING;
  класс у правды не проверяется (меньше MAP_MIN_CELLS клеток) -> как правда <= MAP_DE.
  EPS = 1e-6 - технический допуск float64: вывод и мера детерминированы (проверяется на каждом случае), значения
  стабильны, погрешность суммы по клеткам порядка 1e-13. Подобран не по XBASE1/U_OPER2. Справочно в отчёте - граница
  сдвига от округления изображений до uint8 (q_round: оба изображения, ±0.5 по каналу, худший случай) - не порог.
Жёсткие ворота нового подтверждения (синтетика SYN, SYN_DITHER, SD): new_mapping_errors = 0, mapping_worsening = 0;
плюс STRUCT, CAUSAL_SEAM, DETERMINISM, BASE_ONLY по правилу V1 (confirm_hard V1 без MAPPING_TRUTH).

Набор подтверждения: правило отбора V3.2_DEV (v32dev_select.py: категории, sha1-порядок, ограничения на картинки и
наборы), только квоты CONFIRM, из строк пула, где ни основа, ни член, ни их картинки (хэш) не упоминаются ни в одной
папке проб derive-recolor-* и ни в одном tools/hdart/derive_recolor*.py (кроме этого модуля и его папки).

Порядок:
  devcheck  на DEV-парах V3.2 (уже открыты): контроли меры (совпадение с V2.gates, правда против себя = 0,
            положительные контроли NEW и WORSENING), BASE на DEV; набор подтверждения не отбирается;
  spec      отбор нового набора (ключи - в confirm_v11.json, в spec - только sha) и заморозка, один раз;
  confirm   один прогон;
  cards     только при PASS: карточки по замороженным маршрутам V1 (10 из старых 27, 18 из confirmation-15) плюс
            новый набор по тому же правилу маршрутизации V1;
  final, report, check.

Только numpy, без модели и видеокарты. Команды из корня репозитория:
    py -3.13 tools/hdart/derive_recolor_base_acceptance_v11.py devcheck|spec|confirm|cards|final|report|check
"""
import argparse
import csv
import glob
import hashlib
import json
import os
import random
import re
import sys
import time
import types

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import derive_recolor_acceptance_v2 as V2  # noqa: E402
import derive_recolor_base_acceptance_v1 as AC  # noqa: E402  (заморожен, только чтение)

A3, M, B, D3 = AC.A3, AC.M, AC.B, AC.D3
ENC = "utf-8-sig"
ROOT = AC.ROOT
PROFILE = "DERIVE_RECOLOR_BASE_ACCEPTANCE_V1.1"
PROBES = os.path.join(ROOT, "art", "objects", "generation", "probes")
OUT = os.path.join(PROBES, "derive-recolor-base-v11-acceptance")
CARDS = os.path.join(OUT, "human_cards")
SELF = "tools/hdart/derive_recolor_base_acceptance_v11.py"
V1_SELF = AC.SELF
V1_OUT = AC.OUT
SELECT_RULE = AC.DEV + "/scripts/v32dev_select.py"
POOL = AC.DEV + "/v32dev_pool.tsv"
NEW_SET = "confirm_v11.json"
MAP_DE, MAP_MIN_CELLS = V2.MAP_DE, V2.MAP_MIN_CELLS
TECH_EPS = 1e-6
DELTAS = [np.array(d, float) for d in np.array(np.meshgrid([-.5, .5], [-.5, .5], [-.5, .5])).T.reshape(-1, 3)] + \
    [np.array(d, float) for d in ((.5, 0, 0), (0, .5, 0), (0, 0, .5), (-.5, 0, 0), (0, -.5, 0), (0, 0, -.5))]
SYN_FORMS = ("SYN", "SYN_DITHER", "SD")
DECISION = ("специалист 03.10, передал Vitali в чате: DERIVE_RECOLOR_BASE_V1 = FAIL under frozen spec f981213fbcc6 "
            "(MAPPING_TRUTH contract defined as absolute candidate error = 0 even when truth violates the same "
            "metric; output not changed); BASE_V1.1 = same renderer/output + truth-relative mapping acceptance = NOT "
            "YET VERIFIED; hard on synthetic: new_mapping_errors = 0, mapping_worsening = 0; epsilon from metric "
            "precision before the new set, not from XBASE1/U_OPER2; confirmation-15 not valid for the new mapping "
            "gate, still valid for STRUCT/geometry/alpha/seam/determinism/BASE_ONLY; new untouched set of 10-15 pairs "
            "by the same pre-written rule; freeze spec, mapping, epsilon, selection; one run; FAIL -> no retuning; "
            "human review by the frozen V1 routes, cards after machine PASS")
BODY = ("profile", "decision", "v1", "implementation", "mapping", "selection", "new_set", "hard", "human",
        "final_rule", "sequence", "forbidden")


def rel(p):
    return os.path.join(ROOT, p)


def fsha(p):
    return hashlib.sha256(open(rel(p), "rb").read()).hexdigest()


def osha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def dump(name, obj):
    os.makedirs(OUT, exist_ok=True)
    A3.save_json(os.path.join(OUT, name), obj)


def load(name):
    return A3.load_json(os.path.join(OUT, name))


def write_md(name, lines):
    with open(os.path.join(OUT, name), "w", encoding=ENC, newline="\n") as f:
        f.write("\n".join(lines) + "\n")


# ---------- мера mapping по классам ----------

def qbound(rgb):
    """Граница сдвига ΔE76 цвета rgb (N x 3, float) от округления до uint8 (±0.5 по каналу), по каждой строке."""
    L0 = V2.lab(rgb)
    return np.max([np.linalg.norm(V2.lab(np.clip(rgb + d, 0, 255)) - L0, axis=-1) for d in DELTAS], axis=0)


def class_excess(der, hd, ob, ot):
    """Превышение по каждому классу цвета члена - тот же расчёт, что wrong_palette_mapping в V2.gates, но для всех
    проверяемых классов (не только > MAP_DE), плюс q - граница точности от округления der до uint8."""
    sb, st = ob[..., 3] > 0, ot[..., 3] > 0
    rd, _od, min_d = V2.blocks(der)
    rb, _ob, min_b = V2.blocks(hd)
    T = V2.code(ot)
    full = (min_d >= V2.ALPHA_OPAQUE) & (min_b >= V2.ALPHA_OPAQUE) & sb & st
    ed = np.linalg.norm(V2.lab(rd) - V2.lab(ot[..., :3]), axis=-1)
    eb = np.linalg.norm(V2.lab(rb) - V2.lab(ob[..., :3]), axis=-1)
    out = {}
    for t in np.unique(T[full]):
        sel = full & (T == t)
        if sel.sum() < MAP_MIN_CELLS:
            continue
        out["#%06x" % t] = {"excess": float(ed[sel].mean() - eb[sel].mean()), "cells": int(sel.sum()),
                            "q": float(qbound(rd[sel]).mean())}
    return out


def consistent(cls, der, hd, ob, ot):
    """Контроль меры: классы с превышением > MAP_DE и их превышение совпадают с V2.gates."""
    _g, info = V2.gates(der, hd, ob, ot)
    a = {w["member_rgb"]: w["excess_de"] for w in info["mapping_wrong"]}
    b = {k: round(v["excess"], 1) for k, v in cls.items() if v["excess"] > MAP_DE}
    return a == b and info["mapping_classes_checked"] == len(cls)


def relative(cb, ct):
    """NEW_MAPPING_ERROR и MAPPING_WORSENING вывода (cb) против правды (ct)."""
    new, worse = [], []
    for k, b in sorted(cb.items()):
        if b["excess"] <= MAP_DE:
            continue
        t = ct.get(k)
        if t is None or t["excess"] <= MAP_DE:
            new.append({"member_rgb": k, "base_excess": round(b["excess"], 3),
                        "truth_excess": None if t is None else round(t["excess"], 3), "cells": b["cells"]})
            continue
        if b["excess"] > t["excess"] + TECH_EPS:
            worse.append({"member_rgb": k, "base_excess": round(b["excess"], 4), "truth_excess": round(t["excess"], 4),
                          "q_round": round(b["q"] + t["q"], 3), "cells": b["cells"]})
    return new, worse


def truth_fail_view(cb, ct):
    """Для отчёта: классы, где правда > MAP_DE - превышение BASE, правды, разница и q_round (справочно)."""
    out = []
    for k, t in sorted(ct.items()):
        if t["excess"] > MAP_DE and k in cb:
            b = cb[k]
            out.append({"member_rgb": k, "base": round(b["excess"], 3), "truth": round(t["excess"], 3),
                        "diff": round(b["excess"] - t["excess"], 4), "q_round": round(b["q"] + t["q"], 3)})
    return out


def push_away(truth, ot):
    """Положительный контроль WORSENING: правда, отодвинутая от цвета члена в полтора раза (альфа та же)."""
    m = np.repeat(np.repeat(ot[..., :3].astype(np.float64), 4, 0), 4, 1)
    out = truth.copy()
    out[..., :3] = np.clip(np.rint(truth[..., :3] + 0.5 * (truth[..., :3] - m)), 0, 255).astype(np.uint8)
    return out


def mapping_rows(pair):
    """По синтетическим формам пары: BASE против правды по классам, контроли меры."""
    rows = []
    for form, ob, ot, hd, truth in M.forms(pair):
        if truth is None:
            continue
        cid = "%s>%s/%s" % (pair["base"], pair["member"], form)
        der, ch = B.derive(hd, ob, ot, "recolor")
        if der is None:
            rows.append({"case": cid, "form": form, "status": "REFUSED"})
            continue
        g = ch["geometry_transform"]
        hdo, obo = D3.geo(hd, g), D3.geo(ob, g)
        cb, ct = class_excess(der, hdo, obo, ot), class_excess(truth, hdo, obo, ot)
        new, worse = relative(cb, ct)
        inv = []
        if not consistent(cb, der, hdo, obo, ot) or not consistent(ct, truth, hdo, obo, ot):
            inv.append("классы mapping не совпали с V2.gates")
        if class_excess(der, hdo, obo, ot) != cb:
            inv.append("мера mapping не детерминирована")
        if relative(ct, ct) != ([], []):
            inv.append("правда против себя не 0")
        pn, _pw = relative(class_excess(hdo, hdo, obo, ot), ct)
        tf = [x for x in ct.values() if x["excess"] > MAP_DE]
        _cn, cw = relative(class_excess(push_away(truth, ot), hdo, obo, ot), ct) if tf else ([], [])
        rows.append({"case": cid, "form": form, "status": "DERIVED", "classes_base": len(cb), "classes_truth": len(ct),
                     "truth_over": len(tf), "new_mapping": new, "worsening": worse,
                     "truth_fail_classes": truth_fail_view(cb, ct), "ctrl_base_as_derived_new": len(pn),
                     "ctrl_push_away_worse": len(cw) if tf else None, "measure_invalid": inv})
    return rows


# ---------- devcheck ----------

def v1_state():
    sp = AC.load_spec()   # V1: spec, код BASE, Stage A, V3.1, DEV, набор confirmation-15 не изменились
    reg, conf = AC.load("regression.json"), AC.load("confirmation.json")
    return {"spec_sha256": sp["sha256"], "spec_file_sha256": osha(os.path.join(V1_OUT, "spec.json")),
            "module": V1_SELF, "module_sha256": fsha(V1_SELF),
            "regression_sha256": osha(os.path.join(V1_OUT, "regression.json")), "regression": reg["verdict"],
            "confirmation_sha256": osha(os.path.join(V1_OUT, "confirmation.json")),
            "confirmation": conf["verdict"],
            "confirmation_hard": {k: v["pass"] for k, v in conf["hard"].items()},
            "verdict": "FAIL under frozen spec (MAPPING_TRUTH contract)"}


def do_devcheck():
    if os.path.exists(os.path.join(OUT, "spec.json")):
        raise SystemExit("spec V1.1 уже заморожен - devcheck вошёл в него и не повторяется")
    v1 = v1_state()
    sp3 = A3.load_json(rel(AC.DEV_SPEC))
    rows = []
    for pair in sp3["dev"]:
        for r in mapping_rows(pair):
            rows.append(r)
            if r["status"] == "DERIVED" and (r["new_mapping"] or r["worsening"] or r["truth_over"] or
                                            r["measure_invalid"]):
                print("  %-46s new %d worse %d truth>10 %d %s" % (r["case"], len(r["new_mapping"]),
                                                                  len(r["worsening"]), r["truth_over"],
                                                                  r["measure_invalid"] or ""), flush=True)
    der = [r for r in rows if r["status"] == "DERIVED"]
    inv = [(r["case"], r["measure_invalid"]) for r in der if r["measure_invalid"]]
    pos_new = sum(r["ctrl_base_as_derived_new"] for r in der)
    tf = [r for r in der if r["truth_over"]]
    pos_w = [(r["case"], r["ctrl_push_away_worse"]) for r in tf]
    ctrl_ok = not inv and pos_new > 0 and bool(tf) and all(x[1] > 0 for x in pos_w)
    base_new = [(r["case"], r["new_mapping"]) for r in der if r["new_mapping"]]
    base_w = [(r["case"], r["worsening"]) for r in der if r["worsening"]]
    res = {"profile": PROFILE, "what": "мера mapping V1.1 на DEV-парах V3.2 (уже открыты)", "v1": v1,
           "dev_spec_sha256": fsha(AC.DEV_SPEC), "self_sha256": fsha(SELF), "cases": len(der),
           "refused": [r["case"] for r in rows if r["status"] != "DERIVED"],
           "measure_invalid": inv, "ctrl_base_as_derived_new_total": pos_new, "ctrl_push_away_worse": pos_w,
           "controls_ok": ctrl_ok, "base_new_mapping": base_new, "base_worsening": base_w,
           "truth_fail_classes": {r["case"]: r["truth_fail_classes"] for r in tf}, "rows": rows,
           "ok": ctrl_ok and not base_new and not base_w, "run_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    dump("devcheck.json", res)
    print("devcheck V1.1: синтетических случаев %d, контроли меры %s (несовпадений %d, base-as-derived new %d, "
          "push-away worse %s), BASE new %d worse %d -> %s" % (
              len(der), "OK" if ctrl_ok else "НЕ OK", len(inv), pos_new, pos_w, len(base_new), len(base_w),
              "OK" if res["ok"] else "НЕ OK - вопрос специалисту до заморозки"))
    for k, v in res["truth_fail_classes"].items():
        print("  правда > 10:", k, json.dumps(v, ensure_ascii=False))


# ---------- отбор нового набора ----------

def select_rule():
    """Правило отбора V3.2_DEV из v32dev_select.py без main() (модуль зовёт main() при импорте)."""
    S = types.ModuleType("v32dev_select_rule")
    S.__file__ = rel(SELECT_RULE)
    exec(open(rel(SELECT_RULE), encoding=ENC).read().split("\ndef main():")[0], S.__dict__)
    return S


def touched():
    """Все ключи SET:N, упомянутые в папках проб derive-recolor-* и в tools/hdart/derive_recolor*.py."""
    rx = re.compile(r"\b([A-Z][A-Z0-9_]*:\d+)\b")
    pool = os.path.abspath(rel(POOL))
    own = (os.path.abspath(OUT), os.path.abspath(rel(SELF)))
    files = sorted(f for d in glob.glob(os.path.join(PROBES, "derive-recolor*"))
                   for f in glob.glob(os.path.join(d, "**", "*"), recursive=True)
                   if os.path.isfile(f) and f.rsplit(".", 1)[-1] in ("json", "md", "txt", "tsv", "py", "log")
                   and os.path.abspath(f) != pool and not os.path.abspath(f).startswith(own[0]))
    files += sorted(f for f in glob.glob(os.path.join(HERE, "derive_recolor*.py")) if os.path.abspath(f) != own[1])
    keys = set()
    for f in files:
        keys |= set(rx.findall(open(f, encoding=ENC, errors="replace").read()))
    return keys, len(files)


def select_new():
    S = select_rule()
    rows = list(csv.DictReader(open(rel(POOL), encoding=ENC), delimiter="\t"))
    keys, nfiles = touched()
    h = {}
    for r in rows:
        h[r["base"]], h[r["member"]] = r["base_hash"], r["member_hash"]
    thash = {h[k] for k in keys if k in h}
    free = [r for r in rows if r["base"] not in keys and r["member"] not in keys
            and r["base_hash"] not in thash and r["member_hash"] not in thash]
    used_img, per_base, per_mem, per_pair, taken, conf, counts = set(), {}, {}, set(), set(), [], {}
    for c, _qd, qc, _t in S.CATS:
        cand = sorted((r for r in free if S.cat_ok(c, r)), key=S.order)
        n = 0
        for r in cand:
            if n >= qc:
                break
            bs, ms = r["base"].split(":")[0], r["member"].split(":")[0]
            und = tuple(sorted((r["base"], r["member"])))
            if und in taken or r["base_hash"] in used_img or r["member_hash"] in used_img:
                continue
            if (bs, ms) in per_pair or per_base.get(bs, 0) >= 2 or per_mem.get(ms, 0) >= 2:
                continue
            conf.append({"base": r["base"], "member": r["member"], "category": c, "order": S.order(r)[:12],
                         "features": {k: r[k] for k in ("support", "n_base_colors", "grad", "y_base", "y_member",
                                                        "changed", "func", "multi_px", "div90", "dither_frac")}})
            n += 1
            taken.add(und)
            used_img |= {r["base_hash"], r["member_hash"]}
            per_pair.add((bs, ms))
            per_base[bs] = per_base.get(bs, 0) + 1
            per_mem[ms] = per_mem.get(ms, 0) + 1
        counts[c] = {"quota": qc, "taken": n, "eligible_untouched": len(cand)}
    info = {"pool": {"file": POOL, "sha256": fsha(POOL), "rows": len(rows)},
            "rule_module": {"file": SELECT_RULE, "sha256": fsha(SELECT_RULE)},
            "touched": {"files": nfiles, "keys": len(keys), "keys_in_pool": sum(k in h for k in keys),
                        "images": len(thash), "keys_sha256": hashlib.sha256("\n".join(sorted(keys)).encode()).hexdigest()},
            "untouched_rows": len(free), "per_category": counts}
    return conf, info


# ---------- spec ----------

def spec_body(sel_info, blob):
    dc = load("devcheck.json")
    if not dc["ok"] or dc["self_sha256"] != fsha(SELF):
        raise SystemExit("devcheck V1.1 не пройден или сделан на другом коде - заморозка запрещена")
    v1 = v1_state()
    if v1 != dc["v1"]:
        raise SystemExit("V1 изменился после devcheck")
    return {
        "profile": PROFILE, "decision": DECISION, "v1": v1,
        "implementation": {"module": AC.IMPL, "sha256": fsha(AC.IMPL), "version": B.VERSION,
                           "note": "renderer and output identical to BASE_V1 (same module, same sha)"},
        "mapping": {
            "class": "member palette colour; checked if >= MAP_MIN_CELLS fully opaque cells (V2.gates); excess = "
                     "mean ΔE76(cell, member colour) - mean ΔE76(base HD cell, base colour), as V2.gates",
            "MAP_DE": MAP_DE, "MAP_MIN_CELLS": MAP_MIN_CELLS,
            "NEW_MAPPING_ERROR": "BASE excess > MAP_DE and truth excess <= MAP_DE (or class not checked on truth)",
            "MAPPING_WORSENING": "truth excess > MAP_DE and BASE excess > truth excess + EPS",
            "EPS": TECH_EPS,
            "eps_origin": "technical float64 tolerance: output and measure are deterministic (checked per case: derive "
                          "twice byte-identical, measure twice equal), values stable; summation error ~1e-13. Not "
                          "fitted to XBASE1/U_OPER2 or any case (specialist: deterministic and stable -> very small "
                          "technical epsilon)",
            "q_round": "report only, not a threshold: bound of the excess shift from uint8 rounding of both images "
                       "(mean over class cells of max ΔE76 shift under ±0.5 per channel, 8 corners + 6 faces); "
                       "global envelope 2 x max over sRGB = 1.934",
            "measure_controls": "per case: classes > MAP_DE and their excess equal V2.gates for BASE and truth; "
                                "measure deterministic; truth vs itself = 0/0. Per set: base HD as output gives "
                                ">= 1 NEW (power); push-away truth gives WORSENING > 0 on every case with truth > "
                                "MAP_DE. Not satisfied -> INVALID_MEASURE (not PASS)",
            "devcheck_sha256": osha(os.path.join(OUT, "devcheck.json")),
            "devcheck": {k: dc[k] for k in ("cases", "controls_ok", "ctrl_base_as_derived_new_total",
                                            "ctrl_push_away_worse", "base_new_mapping", "base_worsening")}},
        "selection": dict(sel_info, rule=(
            "v32dev_select.py categories, quotas CONFIRM only (dither 1, local 3, divergent 3, dark 3, flat 2, "
            "textured 3, general 0), order sha1('v32dev:<base>><member>'), pair once (undirected), image once, "
            "(base set, member set) once, base set and member set at most twice; only pool rows whose base, member "
            "and their images are not mentioned in any probes/derive-recolor-* file or tools/hdart/derive_recolor*.py; "
            "a category short of untouched rows takes what there is (no substitution)")),
        "new_set": {"file": NEW_SET, "sha256": hashlib.sha256(blob).hexdigest(), "count": len(json.loads(blob))},
        "hard": {
            "NEW_MAPPING": "sum of NEW_MAPPING_ERROR over SYN, SYN_DITHER, SD of the new set = 0",
            "MAPPING_WORSENING": "sum of MAPPING_WORSENING over SYN, SYN_DITHER, SD of the new set = 0",
            "STRUCT": "as V1 confirmation: STRUCT = 0 on all forms incl. REAL; Stage A refusal = fail",
            "CAUSAL_SEAM": "as V1 confirmation (SYN of local pairs)", "DETERMINISM": "as V1",
            "BASE_ONLY": "as V1",
            "pass": "CONFIRMATION_V11 PASS = all six PASS and every measure control satisfied",
            "fail": "any FAIL -> BASE_V1.1 FAIL; nothing is retuned on this set",
            "carried_over": "old 27 regression V1 PASS stays valid (absolute mapping 0 implies 0 new and 0 worsening); "
                            "confirmation-15 V1 stays valid for STRUCT, CAUSAL_SEAM, DETERMINISM, BASE_ONLY (all PASS), "
                            "not for mapping"},
        "human": {
            "routes": "frozen V1 rule: V1 regression human_routes (10) + V1 confirmation-15 human_routes (18) + the "
                      "new set routed by the same V1 rule (confirm_routes: REAL, SYN_DITHER, SD mandatory; SYN with "
                      "new artifacts vs truth or ΔE > min(EXACT, SOFT) + %.1f)" % AC.DE_MARGIN,
            "must_include": "LIGHTNIN:9 SYN_DITHER and U_OPER2:10 SD (already in V1 confirmation routes)",
            "card": "as V1 (card_image, scale %d, seed %d, blind, key outside the reviewer folder)" % (
                AC.CARD_SCALE, AC.CARD_SEED),
            "question": AC.QUESTION, "answers": list(AC.ANSWERS),
            "when": "cards only after CONFIRMATION_V11 PASS; the list is not changed after images are seen"},
        "final_rule": ("BASE_V1.1 eligible for VERIFIED = V1 regression PASS + V1 confirmation-15 non-mapping gates "
                       "PASS + CONFIRMATION_V11 PASS + every human card PASS. Any card FAIL -> FAIL; any UNSURE -> not "
                       "PASS, back to specialist. VERIFIED is set by a human. Then R3.3."),
        "sequence": ["devcheck (before freeze)", "spec + selection (once)", "confirm (once)",
                     "cards (only if PASS)", "human review", "final"],
        "forbidden": ["BASE_V1 spec, folder, results and module unchanged", "renderer/output unchanged",
                      "no unmix, ASL, ID/ST/CY", "MAP_DE 10 and C1 unchanged", "V7 and families unchanged",
                      "857/1030 and 173 refusals untouched", "no model, no GPU", "TEXTURE_TRANSFER not started"],
    }


def do_spec():
    p = os.path.join(OUT, "spec.json")
    if os.path.exists(p) or os.path.exists(os.path.join(OUT, NEW_SET)):
        raise SystemExit("spec V1.1 или набор уже записаны - они неизменяемы")
    conf, info = select_new()
    if not 10 <= len(conf) <= 15:
        raise SystemExit("отобрано %d пар, специалист просил 10-15 - заморозка остановлена (%s)" % (
            len(conf), info["per_category"]))
    blob = json.dumps(conf, ensure_ascii=False, sort_keys=True).encode()
    body = spec_body(info, blob)
    with open(os.path.join(OUT, NEW_SET), "wb") as f:
        f.write(blob)
    body["sha256"] = V2.jsha({k: body[k] for k in BODY})
    body["frozen_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    body["self_sha256"] = fsha(SELF)
    A3.save_json(p, body)
    print("spec V1.1 заморожен: sha %s; набор %d пар (%s); ключи - %s, не открывались" % (
        body["sha256"][:12], len(conf), ", ".join("%s %d/%d" % (c, v["taken"], v["quota"])
                                                for c, v in info["per_category"].items() if v["quota"]), NEW_SET))


def load_spec():
    sp = load("spec.json")
    if V2.jsha({k: sp[k] for k in BODY}) != sp["sha256"]:
        raise SystemExit("spec V1.1 изменён после заморозки")
    if fsha(SELF) != sp["self_sha256"]:
        raise SystemExit("приёмка V1.1 изменилась после заморозки")
    if json.loads(json.dumps(v1_state())) != sp["v1"]:
        raise SystemExit("V1 изменился после заморозки V1.1")
    if fsha(AC.IMPL) != sp["implementation"]["sha256"]:
        raise SystemExit("код BASE изменился")
    blob = open(os.path.join(OUT, NEW_SET), "rb").read()
    if hashlib.sha256(blob).hexdigest() != sp["new_set"]["sha256"]:
        raise SystemExit("набор V1.1 изменён")
    if fsha(POOL) != sp["selection"]["pool"]["sha256"] or fsha(SELECT_RULE) != sp["selection"]["rule_module"]["sha256"]:
        raise SystemExit("пул или правило отбора изменились")
    return sp, json.loads(blob.decode("utf-8"))


# ---------- подтверждение V1.1 ----------

def do_confirm():
    sp, pairs = load_spec()
    p = os.path.join(OUT, "confirmation.json")
    if os.path.exists(p):
        raise SystemExit("confirmation.json V1.1 уже есть - прогон один раз")
    rows, mrows = [], []
    AC.OUT = OUT   # картинки подтверждения - в папку V1.1 (V1 не пишется)
    for pair in pairs:
        for r in AC.eval_pair(pair, keep_img=True):
            if "_img" in r:
                der, hdo, ot, truth = r["_img"]
                stem = r["case"].replace(":", "_").replace(">", "__").replace("/", "_")
                AC.save_png(der, "confirm", stem + "_base.png")
                AC.save_png(hdo, "confirm", stem + "_hd.png")
                AC.save_png(ot, "confirm", stem + "_member.png")
                if truth is not None:
                    AC.save_png(truth, "confirm", stem + "_truth.png")
                r["stem"] = stem
            rows.append(r)
        mrows += mapping_rows(pair)
    mm = {r["case"]: r for r in mrows}
    for r in rows:
        if r["form"] in SYN_FORMS and r["status"] == "DERIVED":
            m = mm[r["case"]]
            r.update(new_mapping=m["new_mapping"], worsening=m["worsening"], truth_fail_classes=m["truth_fail_classes"],
                     map_ctrl={k: m[k] for k in ("classes_base", "classes_truth", "truth_over",
                                                 "ctrl_base_as_derived_new", "ctrl_push_away_worse")})
            r["measure_invalid"] = r["measure_invalid"] + m["measure_invalid"]
        print("%-48s %s S%s new %s worse %s art %s seam %s dE %s" % (
            r["case"], r["status"], r.get("struct"), len(r.get("new_mapping", [])) if "new_mapping" in r else "-",
            len(r.get("worsening", [])) if "worsening" in r else "-", r.get("new_art", "-"), r.get("seam_leak", "-"),
            r.get("de", "-")), flush=True)
    h1, inv = AC.confirm_hard(rows)
    h = {}
    syn = [r for r in rows if r["form"] in SYN_FORMS and r["status"] == "DERIVED"]
    nm = [(r["case"], len(r["new_mapping"])) for r in syn if r["new_mapping"]]
    wm = [(r["case"], len(r["worsening"])) for r in syn if r["worsening"]]
    h["NEW_MAPPING"] = {"pass": not nm, "detail": "NEW_MAPPING_ERROR: %s" % (", ".join("%s %d" % x for x in nm) or "нет")}
    h["MAPPING_WORSENING"] = {"pass": not wm, "detail": "MAPPING_WORSENING: %s" % (
        ", ".join("%s %d" % x for x in wm) or "нет")}
    for k in ("STRUCT", "CAUSAL_SEAM", "DETERMINISM", "BASE_ONLY"):
        h[k] = h1[k]
    pos = sum(r["map_ctrl"]["ctrl_base_as_derived_new"] for r in syn)
    if pos == 0:
        inv.append(("набор", ["положительный контроль NEW: base HD как вывод не дал ни одной ошибки"]))
    bad_w = [r["case"] for r in syn if r["map_ctrl"]["truth_over"] and not r["map_ctrl"]["ctrl_push_away_worse"]]
    if bad_w:
        inv.append(("набор", ["положительный контроль WORSENING не сработал: %s" % ", ".join(bad_w)]))
    verdict = "INVALID_MEASURE" if inv else ("PASS" if all(x["pass"] for x in h.values()) else "FAIL")
    res = {"profile": PROFILE, "spec_sha256": sp["sha256"], "run_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "pairs": pairs, "cases": AC.strip(rows), "hard": h, "measure_invalid": inv, "verdict": verdict,
           "ctrl_base_as_derived_new_total": pos, "human_routes": AC.confirm_routes(rows)}
    dump("confirmation.json", res)
    write_confirmation_md(res)
    print("подтверждение V1.1: %s; %s" % (verdict, "; ".join("%s %s" % (k, "PASS" if x["pass"] else "FAIL")
                                                           for k, x in h.items())))


def write_confirmation_md(res):
    f = AC._f
    L = ["# DERIVE_RECOLOR_BASE_ACCEPTANCE_V1.1 - новый набор подтверждения (один прогон)", "",
         "Прогон %s, spec `%s`." % (res["run_at"], res["spec_sha256"][:12]), "",
         "**CONFIRMATION_V11 %s**" % res["verdict"], "", "| условие | итог | подробно |", "|---|---|---|"]
    for k, x in res["hard"].items():
        L.append("| %s | %s | %s |" % (k, "PASS" if x["pass"] else "**FAIL**", x["detail"]))
    if res["measure_invalid"]:
        L += ["", "Контроли мер не выполнены: " + "; ".join("%s: %s" % (c, ", ".join(v)) for c, v in res["measure_invalid"])]
    L += ["", "## Случаи", "",
          "| случай | категория | STRUCT | new / worse mapping | правда > 10 (BASE / правда / q_round) | пятна | новые против правды "
          "| ΔE BASE / EXACT / SOFT | шов | human review |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in res["cases"]:
        if r["status"] != "DERIVED":
            L.append("| %s | %s | REFUSED | | | | | | | |" % (r["case"], r["category"]))
            continue
        tf = "; ".join("%s %.3f / %.3f / %.2f" % (x["member_rgb"], x["base"], x["truth"], x["q_round"])
                       for x in r.get("truth_fail_classes", [])) or "-"
        nw = ("%d / %d" % (len(r["new_mapping"]), len(r["worsening"]))) if "new_mapping" in r else "REAL map %d" % r["map"]
        de = ("%.3f / %s / %s" % (r["de"], f(r["de_exact"], "%.3f"), f(r["de_soft"], "%.3f"))) if "de" in r else "-"
        L.append("| %s | %s | %d | %s | %s | %d | %s | %s | %s | %s |" % (
            r["case"], r["category"], r["struct"], nw, tf, r["art"], r.get("new_art", "-"), de,
            ("%d из %d" % (r["seam_leak"], r["seam_counted"])) if "seam_leak" in r else "-",
            "; ".join(res["human_routes"].get(r["case"], [])) or "-"))
    write_md("confirmation.md", L)


# ---------- карточки, итог ----------

def do_cards():
    sp, _pairs = load_spec()
    conf = load("confirmation.json")
    if conf["verdict"] != "PASS" or conf["spec_sha256"] != sp["sha256"]:
        raise SystemExit("карточки - только при PASS подтверждения V1.1 (сейчас %s)" % conf["verdict"])
    if sp["v1"]["regression"] != "PASS" or not all(sp["v1"]["confirmation_hard"][k] for k in
                                                   ("STRUCT", "CAUSAL_SEAM", "DETERMINISM", "BASE_ONLY")):
        raise SystemExit("перенесённые результаты V1 не PASS")
    if os.path.exists(os.path.join(OUT, "cards_key.json")):
        raise SystemExit("карточки уже собраны - они неизменяемы")
    reg1, conf1 = AC.load("regression.json"), AC.load("confirmation.json")
    x4 = lambda a: np.repeat(np.repeat(a, 4, 0), 4, 1)
    rd = lambda d, *p: A3.read_png(os.path.join(d, *p))
    opt = lambda p: A3.read_png(p) if os.path.exists(p) else None
    items = []
    for k, why in reg1["human_routes"].items():
        items.append(({"set": "old27", "case": k, "why": why},
                      [x4(rd(V1_OUT, "orig", k + "_member.png")), rd(V1_OUT, "hd", k + ".png"),
                       rd(V1_OUT, "derived", k + ".png"), opt(os.path.join(V1_OUT, "truth", k + ".png"))]))
    for nm, d, c in (("confirmation15", V1_OUT, conf1), ("confirmation_v11", OUT, conf)):
        for r in c["cases"]:
            if r["case"] not in c["human_routes"]:
                continue
            s = r["stem"]
            items.append(({"set": nm, "case": r["case"], "why": c["human_routes"][r["case"]]},
                          [x4(rd(d, "confirm", s + "_member.png")), rd(d, "confirm", s + "_hd.png"),
                           rd(d, "confirm", s + "_base.png"), opt(os.path.join(d, "confirm", s + "_truth.png"))]))
    random.Random(AC.CARD_SEED).shuffle(items)
    os.makedirs(CARDS, exist_ok=True)
    key = []
    for i, (meta, panels) in enumerate(items, 1):
        cid = "card%03d" % i
        p = os.path.join(CARDS, cid + ".png")
        AC.card_image(panels, AC.CARD_SCALE).save(p)
        key.append(dict(meta, card=cid, png_sha256=osha(p)))
    with open(os.path.join(CARDS, "QUESTION.md"), "w", encoding=ENC, newline="\n") as f:
        f.write("# BASE recolor - human review\n\nFor every card answer one word: PASS, FAIL or UNSURE.\n\n"
                "> %s\n\nPanels: member original x4 | base HD | BASE recolor | truth (only on synthetic cards).\n"
                "UNSURE counts as not PASS. Write the answer into answers.tsv (column verdict), a note is optional.\n"
                % AC.QUESTION)
    with open(os.path.join(CARDS, "answers.tsv"), "w", encoding=ENC, newline="\n") as f:
        f.write("card\tverdict\tnote\n" + "".join("%s\t\t\n" % k["card"] for k in key))
    dump("cards_key.json", {"spec_sha256": sp["sha256"], "seed": AC.CARD_SEED, "cards": key,
                            "answers_template_sha256": osha(os.path.join(CARDS, "answers.tsv")),
                            "made_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
    print("карточек %d (%s) -> %s" % (len(key), ", ".join("%s %d" % (s, sum(k["set"] == s for k in key)) for s in
                                                         ("old27", "confirmation15", "confirmation_v11")), CARDS))


def human_state():
    key = load("cards_key.json")
    for k in key["cards"]:
        if osha(os.path.join(CARDS, k["card"] + ".png")) != k["png_sha256"]:
            raise SystemExit("%s изменилась после сборки" % k["card"])
    p = os.path.join(CARDS, "answers.tsv")
    rows = [ln.split("\t") for ln in open(p, encoding=ENC).read().splitlines()[1:] if ln.strip()]
    ans = {r[0]: (r[1].strip().upper() if len(r) > 1 else "", r[2] if len(r) > 2 else "") for r in rows}
    miss = [k["card"] for k in key["cards"] if ans.get(k["card"], ("",))[0] not in AC.ANSWERS]
    if miss:
        return "AWAITING_HUMAN", key, ans, miss
    v = [ans[k["card"]][0] for k in key["cards"]]
    return ("FAIL" if "FAIL" in v else "UNSURE" if "UNSURE" in v else "PASS"), key, ans, []


def do_final():
    sp, _pairs = load_spec()
    conf = load("confirmation.json")
    st, key, ans, miss = human_state()
    if st == "AWAITING_HUMAN":
        raise SystemExit("нет ответа по %d карточкам: %s" % (len(miss), ", ".join(miss[:20])))
    machine = "PASS" if conf["verdict"] == "PASS" and sp["v1"]["regression"] == "PASS" else "FAIL"
    over = "ELIGIBLE_FOR_VERIFIED" if machine == st == "PASS" else ("FAIL" if "FAIL" in (machine, st) else
                                                                    "NOT_PASS_" + st)
    rows = [dict(k, verdict=ans[k["card"]][0], note=ans[k["card"]][1]) for k in key["cards"]]
    dump("final.json", {"profile": PROFILE, "spec_sha256": sp["sha256"], "machine": machine, "human": st,
                        "overall": over, "cards": rows, "answers_sha256": osha(os.path.join(CARDS, "answers.tsv")),
                        "at": time.strftime("%Y-%m-%dT%H:%M:%S")})
    L = ["# DERIVE_RECOLOR_BASE_ACCEPTANCE_V1.1 - итог human review", "", "Правило: " + sp["final_rule"], "",
         "MACHINE %s, HUMAN %s -> **%s**" % (machine, st, over), "",
         "| карточка | набор | случай | вердикт | заметка | почему в review |", "|---|---|---|---|---|---|"]
    L += ["| %s | %s | %s | %s | %s | %s |" % (r["card"], r["set"], r["case"], r["verdict"], r["note"],
                                               "; ".join(r["why"])) for r in rows]
    write_md("final.md", L)
    print("\n".join(L[:5]))


def do_report():
    sp, _pairs = load_spec()
    L = ["# DERIVE_RECOLOR_BASE_ACCEPTANCE_V1.1 - сводка", "", "Spec `%s`, код BASE `%s`. BASE_V1: %s." % (
        sp["sha256"][:12], sp["implementation"]["sha256"][:12], sp["v1"]["verdict"]), "",
        "Перенесено из V1: регрессия старых 27 %s; confirmation-15 STRUCT/шов/детерминизм/BASE_ONLY %s." % (
            sp["v1"]["regression"], {k: v for k, v in sp["v1"]["confirmation_hard"].items() if k != "MAPPING_TRUTH"}),
        "", "Новый набор: %d пар (%s)." % (sp["new_set"]["count"], ", ".join(
            "%s %d" % (c, v["taken"]) for c, v in sp["selection"]["per_category"].items() if v["quota"])), ""]
    if os.path.exists(os.path.join(OUT, "confirmation.json")):
        conf = load("confirmation.json")
        L.append("**CONFIRMATION_V11 %s**" % conf["verdict"])
        L += ["- %s %s: %s" % (k, "PASS" if x["pass"] else "FAIL", x["detail"]) for k, x in conf["hard"].items()]
        L.append("- в human review из нового набора: %d" % len(conf["human_routes"]))
    else:
        L.append("Подтверждение V1.1 не прогонялось.")
    if os.path.exists(os.path.join(OUT, "final.json")):
        fin = load("final.json")
        L += ["", "**HUMAN %s -> %s**" % (fin["human"], fin["overall"])]
    elif os.path.exists(os.path.join(OUT, "cards_key.json")):
        L += ["", "Карточки human review собраны, ответов ещё нет."]
    write_md("report.md", L)
    print("\n".join(L))


def do_check():
    load_spec()
    print("spec V1.1, V1, код BASE, пул, правило отбора и набор не изменились")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("devcheck", "spec", "confirm", "cards", "final", "report", "check"))
    a = ap.parse_args()
    os.chdir(ROOT)
    {"devcheck": do_devcheck, "spec": do_spec, "confirm": do_confirm, "cards": do_cards, "final": do_final,
     "report": do_report, "check": do_check}[a.cmd]()


if __name__ == "__main__":
    main()
