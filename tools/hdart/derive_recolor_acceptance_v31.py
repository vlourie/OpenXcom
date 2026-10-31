"""DERIVE_RECOLOR_ACCEPTANCE_V3.1 - приёмка Stage B INTERPOLATED_MAP_V1 (tools/hdart/derive_recolor_v31.py).

Решение: специалист 03.10, передал Vitali в чате - DERIVE_RECOLOR_V3.1_PREP разрешён, GPU и R3.3 запрещены.
Stage A V3 заморожен как есть (derive_recolor_v3.resolve_geometry, тот же sha, что в spec V3). EXACT_MAP и
SOFT_MAP V3 отвергнуты как общий метод и считаются только диагностическими базами; выбора EXACT/SOFT нет.
Случаи, входы, ворота, пороги (MAP_DE 10) и правило пограничных случаев - из V3 без изменений; выбор C1
(LIGHTNIN:10 -> LIGHTNIN_BL2:10) заморожен в V3 и не пересчитывается.

Жёсткая приёмка (записана в spec до прогона, все шесть):
  H1 все STRUCTURAL ворота 0 на всех случаях (отказ - провал);
  H2 нет регрессии: каждый случай с PASS в V3 (по results.json V3) - PASS и в V3.1;
  H3 C2, C3, C6: средняя ΔE к правде у INTERPOLATED не хуже лучшего из EXACT / SOFT (допуск TIE_DE);
  H4 S06, C5: утечка через границу областей 0 (метрика LEAK, с контролем чувствительности на SOFT и правде);
  H5 R01, R02, R12: unintended_local_artifacts 0;
  H6 детерминизм: каждый вывод дважды побайтово равен, цепочка равна.
Итог V3.1 PASS - все шесть И каждый случай PASS (пограничные - через человека по карточкам V3.1).

Команды (из корня репозитория):
    py -3.13 tools/hdart/derive_recolor_acceptance_v31.py spec     # заморозить (один раз)
    py -3.13 tools/hdart/derive_recolor_acceptance_v31.py run      # прогон, results.md
    py -3.13 tools/hdart/derive_recolor_acceptance_v31.py cards    # карточки тем, кому нужен человек
    py -3.13 tools/hdart/derive_recolor_acceptance_v31.py report   # итог с ответами answers_human.tsv
    py -3.13 tools/hdart/derive_recolor_acceptance_v31.py check    # spec, код, V2 и V3 не изменились
"""
import argparse
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
import derive_recolor_v3 as D3  # noqa: E402
import derive_recolor_v31 as D31  # noqa: E402

ENC = "utf-8-sig"
ROOT = A3.ROOT
PROFILE = "DERIVE_RECOLOR_ACCEPTANCE_V3_1"
OUT = os.path.join(ROOT, "art", "objects", "generation", "probes", "derive-recolor-acceptance-v31")
V3_OUT = "art/objects/generation/probes/derive-recolor-acceptance-v3"
SELF = "tools/hdart/derive_recolor_acceptance_v31.py"
IMPL = "tools/hdart/derive_recolor_v31.py"
STAGE_A = "tools/hdart/derive_recolor_v3.py"
V3_SELF = "tools/hdart/derive_recolor_acceptance_v3.py"
DECISION = ("специалист 03.10, передал Vitali в чате: DERIVE_RECOLOR_V3.1_PREP разрешён; Stage A заморожен как есть; "
            "Stage B - INTERPOLATED_MAP_V1 без глобального выбора EXACT/SOFT; EXACT и SOFT - диагностические базы; "
            "GPU и R3.3 запрещены")
STRUCT, VISUAL, BORDERLINE = A3.STRUCT, A3.VISUAL, A3.BORDERLINE
FLOOR = A3.FLOOR
TIE_DE = 0.05                 # «не хуже»: ΔE INTERPOLATED <= лучшая база + TIE_DE
H3_CASES = ("C2", "C3", "C6")
H5_CASES = ("R01", "R02", "R12")
H5_GATE = "unintended_local_artifacts"
# утечка через границу областей: правда стороны A и стороны B - тем же художником и той же фактурой, карта
# стороны на всё тело; split - граница по x в клетках оригинала
LEAK = {"S06": {"A": "hue120", "B": "hue-0.25", "split": 16},
        "C5": {"A": "hue120", "B": "identity", "split": "w//2"}}
LEAK_BAND = 2.0               # HD-пиксели ближе к шву (по центру пикселя) - зона законного смешения художника
LEAK_DIST = 2.0               # пиксель считается, только если правды сторон различимы (ΔE76 больше)
LEAK_RULE = ("Для S06 и C5: правда A и правда B - V2.render оригинала основы, перекрашенного картой стороны A "
             "(B) по всему телу, той же фактурой V2.noise. Считаются HD-пиксели, непрозрачные (>= ALPHA_OPAQUE) "
             "в выводе и в правде A, у которых |X + 0.5 - 4 * split| > LEAK_BAND (вне зоны билинейного смешения "
             "художника на шве) и ΔE76(правда A, правда B) > LEAK_DIST. Своя сторона - A при X + 0.5 < 4 * split. "
             "Утечка - пиксель, у которого ΔE76(вывод, правда чужой стороны) < ΔE76(вывод, правда своей). H4: "
             "утечка INTERPOLATED = 0. Контроль чувствительности: у самой правды случая утечка 0 (метрика верна) и "
             "у SOFT_MAP (support) утечка > 0 (метрика её видит); не выполнено - H4 не пройден как непокрытый")
HUMAN_RULE = ("Ответы человека - только на карточки V3.1 (answers_human.tsv этой папки): вывод V3.1 другой, "
              "ответы V2 и V3 не переносятся. Пограничные случаи (BORDERLINE V3) - правило "
              "MACHINE_STRICT_HUMAN_PASS V3 без изменений")
BODY = ("profile", "decision", "implementation", "stage_a", "v3_dependency", "gates", "thresholds", "borderline",
        "cases", "inputs", "hard_acceptance", "leak_rule", "verdict_rule", "overall_rule", "human_rule",
        "diagnostics", "card", "forbidden")


def rel(p):
    return os.path.join(ROOT, p)


def save_png(a, *parts):
    p = os.path.join(OUT, *parts)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    Image.fromarray(a, "RGBA").save(p)
    return p


# ---------- spec ----------

def impl_state():
    st = {"module": IMPL, "sha256": V2.fsha(rel(IMPL)), "version": D31.VERSION,
          "color_transform": D31.COLOR_TRANSFORM,
          "constants": {k: getattr(D31, k) for k in ("SIGMA_MIN", "SIGMA_FALLBACK", "STAT_ALPHA", "MIXED_W",
                                                     "SHADE_MIN", "SHADE_FALLBACK", "PRIOR_W", "CHROMA_W0",
                                                     "CHROMA_W1")}}
    return json.loads(json.dumps(st))


def stage_a_state():
    return {"module": STAGE_A, "sha256": V2.fsha(rel(STAGE_A)), "version": D3.VERSION}


def v3_pass_set():
    res = A3.load_json(rel(V3_OUT + "/results.json"))
    sp3 = A3.load_json(rel(V3_OUT + "/spec.json"))
    o, vs, _src, _ch = A3.overall(res, A3.read_human(sp3))
    return o, sorted(k for k, v in vs.items() if v.startswith("PASS")), vs


def v3_state():
    o, ps, vs = v3_pass_set()
    sp3 = A3.load_json(rel(V3_OUT + "/spec.json"))
    return {"module": V3_SELF, "sha256": V2.fsha(rel(V3_SELF)), "spec_sha256": sp3["sha256"],
            "spec_impl_sha256": sp3["implementation"]["sha256"],
            "results_file_sha256": V2.fsha(rel(V3_OUT + "/results.json")),
            "answers_file_sha256": V2.fsha(rel(V3_OUT + "/answers_human.tsv")),
            "overall": o, "pass_set": ps, "verdicts": vs, "v2": A3.v2_state()}


def v3_cases():
    sp3 = A3.load_json(rel(V3_OUT + "/spec.json"))
    return sp3["regression"] + sp3["controls"], sp3["inputs"]


def got_inputs(c):
    ob, ot, hd, truth = A3.inputs_of(c)
    d = {"base_orig": V2.asha(ob), "member_orig": V2.asha(ot), "hd": V2.asha(hd)}
    if truth is not None:
        d["truth"] = V2.asha(truth)
    if c["kind"] == "real":
        d["hd_file_sha256"] = V2.fsha(rel(c["hd"]))
    return d


def spec_body():
    cases, inp3 = v3_cases()
    inputs = {}
    for c in cases:
        d = got_inputs(c)
        if d != inp3[c["id"]]:
            raise SystemExit("%s: входы расходятся со spec V3" % c["id"])
        inputs[c["id"]] = d
    sa = stage_a_state()
    v3 = v3_state()
    if sa["sha256"] != v3["spec_impl_sha256"]:
        raise SystemExit("Stage A (derive_recolor_v3.py) не тот, что заморожен в spec V3")
    return {
        "profile": PROFILE, "decision": DECISION, "implementation": impl_state(), "stage_a": sa,
        "v3_dependency": v3,
        "gates": {"structural_hard": {g: "must be 0, never weakened" for g in STRUCT},
                  "visual_quality": {g: "must be 0, except the borderline rule" for g in VISUAL}},
        "thresholds": {k: getattr(V2, k) for k in ("MAP_DE", "MAP_MIN_CELLS", "ART_LN", "ART_AB", "ART_MIN_CELLS",
                                                   "MAIN_MEAN", "MAIN_P95", "ALPHA_OPAQUE", "OCC", "NOISE_SEED",
                                                   "NOISE_AMP")} | {"HOLE": A3.HOLE, "TIE_DE": TIE_DE,
                                                                    "LEAK_BAND": LEAK_BAND, "LEAK_DIST": LEAK_DIST},
        "borderline": {"cases": list(BORDERLINE), "class": "MACHINE_STRICT_HUMAN_PASS",
                       "rule": "as in V3 spec, unchanged"},
        "cases": cases, "inputs": inputs,
        "hard_acceptance": {
            "H1": "every case: DERIVED and every STRUCTURAL gate 0",
            "H2": "every case in V3 pass_set (v3_dependency) has a V3.1 verdict starting with PASS",
            "H3": "cases %s: mean ΔE to truth INTERPOLATED <= min(EXACT_MAP, SOFT_MAP support) + TIE_DE" % (
                ", ".join(H3_CASES)),
            "H4": "cases %s: leakage INTERPOLATED = 0, truth leakage = 0, SOFT_MAP leakage > 0 (leak_rule)" % (
                ", ".join(LEAK)),
            "H5": "cases %s: %s = 0" % (", ".join(H5_CASES), H5_GATE),
            "H6": "every case: derive twice -> byte-identical output and equal chain"},
        "leak_rule": {"rule": LEAK_RULE, "cases": LEAK},
        "verdict_rule": ("as V3 verdict3: REFUSED or STRUCTURAL > 0 -> STRUCT_FAIL; synthetic gates invalid on truth "
                         "-> GATE_INVALID; coverage missing -> UNCOVERED; VISUAL > 0 or synthetic main failed: "
                         "borderline -> human, other -> VISUAL_FAIL; otherwise synthetic PASS, real -> human"),
        "overall_rule": ("V3.1 PASS: H1..H6 all pass AND every case PASS. Any H fails or any settled case not PASS "
                         "-> FAIL; else cases waiting for a human -> AWAITING_HUMAN. Both layers are reported"),
        "human_rule": HUMAN_RULE,
        "diagnostics": ("every case is also derived by EXACT_MAP and SOFT_MAP (support) of derive_recolor_v3; "
                        "gates, ΔE to truth, speckle over the support and leakage are reported for all three; "
                        "diagnostics do not decide anything except H3 and the H4 sensitivity control"),
        "card": {"question": A3.CARD_Q, "panels": ["1 base original x4 (chain orientation)", "2 HD base (chain "
                 "orientation)", "3 member original x4", "4 derived INTERPOLATED", "5 derived on checker",
                 "6 truth (synthetic only)"], "scale": 2, "floor_rgb": list(FLOOR),
                 "answers": "answers_human.tsv: case_id, verdict (PASS|FAIL|UNSURE), note"},
        "forbidden": ["Stage A not changed", "structural gates not changed", "MAP_DE stays 10",
                      "V2/V3 regression cases not changed", "V7, families, taxonomy not changed",
                      "borderline rule not changed", "173 refused pairs not weakened", "C1 selection not changed",
                      "no asset-specific exceptions", "not fitted to R06/R07 by hand", "no Qwen, no model, no GPU"],
    }


def do_spec():
    p = os.path.join(OUT, "spec.json")
    if os.path.exists(p):
        raise SystemExit("spec.json уже записан - он неизменяем (%s)" % p)
    body = spec_body()
    body["sha256"] = V2.jsha({k: body[k] for k in BODY})
    body["frozen_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    body["self_sha256"] = V2.fsha(rel(SELF))
    A3.save_json(p, body)
    print("spec заморожен: %s, случаев %d, V3 PASS %s, sha %s" % (
        p, len(body["cases"]), ",".join(body["v3_dependency"]["pass_set"]), body["sha256"][:12]))


def load_spec():
    sp = A3.load_json(os.path.join(OUT, "spec.json"))
    if V2.jsha({k: sp[k] for k in BODY}) != sp["sha256"]:
        raise SystemExit("spec.json изменён после заморозки")
    if impl_state() != sp["implementation"]:
        raise SystemExit("код вывода V3.1 изменился после заморозки")
    if stage_a_state() != sp["stage_a"]:
        raise SystemExit("Stage A изменился после заморозки")
    if v3_state() != sp["v3_dependency"]:
        raise SystemExit("V3 (приёмка, spec, results или ответы) изменилась после заморозки V3.1")
    if V2.fsha(rel(SELF)) != sp["self_sha256"]:
        raise SystemExit("сама приёмка V3.1 изменилась после заморозки")
    return sp


# ---------- утечка ----------

def side_truths(c, base):
    lk = LEAK[c["id"]]
    tex = V2.noise(base.shape[0] * 4, base.shape[1] * 4)
    m = base[..., 3] > 0

    def mp(kind, col):
        return {"hue120": lambda: V2.hue_map(col), "hue-0.25": lambda: V2.hue_map(col, -0.25),
                "identity": lambda: col}[kind]()
    A, B = base.copy(), base.copy()
    for y, x in zip(*np.nonzero(m)):
        col = tuple(int(v) for v in base[y, x, :3])
        A[y, x, :3], B[y, x, :3] = mp(lk["A"], col), mp(lk["B"], col)
    split = base.shape[1] // 2 if lk["split"] == "w//2" else int(lk["split"])
    return V2.render(A, c["alpha"], tex), V2.render(B, c["alpha"], tex), split


def leakage(der, ta, tb, split):
    H, W = der.shape[:2]
    d = np.arange(W)[None, :].repeat(H, 0) + 0.5 - 4 * split
    la, lb, ld = V2.lab(ta[..., :3]), V2.lab(tb[..., :3]), V2.lab(der[..., :3])
    de = lambda p, q: np.sqrt(((p - q) ** 2).sum(-1))
    sel = ((der[..., 3] >= V2.ALPHA_OPAQUE) & (ta[..., 3] >= V2.ALPHA_OPAQUE) & (de(la, lb) > LEAK_DIST)
           & (np.abs(d) > LEAK_BAND))
    a_side = d < 0
    own = np.where(a_side, de(ld, la), de(ld, lb))
    oth = np.where(a_side, de(ld, lb), de(ld, la))
    band = sel & (np.abs(d) <= 3 * LEAK_BAND)
    return {"leak_px": int((sel & (oth < own)).sum()), "counted_px": int(sel.sum()),
            "near_seam_mean_de_own": round(float(own[band].mean()), 3) if band.any() else None}


# ---------- run ----------

def mode_diag(der, hd_o, ob_o, ot, truth, region):
    gt, _ = A3.gates3(der, hd_o, ob_o, ot)
    d = {"struct": {g: gt[g] for g in STRUCT if gt[g]}, "visual": {g: gt[g] for g in VISUAL if gt[g]},
         "speckle": A3.speckle(der, hd_o, region)}
    if truth is not None:
        d["main"] = V2.main_metric(der, truth)
    return d


def run_case(c, sp):
    ob, ot, hd, truth = A3.inputs_of(c)
    if got_inputs(c) != sp["inputs"][c["id"]]:
        raise SystemExit("%s: входы не те, что в spec" % c["id"])
    der, chain = D31.derive(hd, ob, ot, c["route"])
    der2, chain2 = D31.derive(hd, ob, ot, c["route"])
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
    ex, _ = D3.derive(hd, ob, ot, c["route"], mode="EXACT_MAP")
    so, _ = D3.derive(hd, ob, ot, c["route"], mode="SOFT_MAP", soft_scope="support")
    sup = (ob_o[..., 3] > 0) & (ot[..., 3] > 0)
    row["modes"] = {nm: mode_diag(a, hd_o, ob_o, ot, truth, sup) for nm, a in
                    (("INTERPOLATED", der), ("EXACT_MAP", ex), ("SOFT_MAP", so))}
    if truth is not None:
        tg = "MIRROR_X" if c.get("mirror_member") else "IDENTITY"
        tgt, _ = A3.gates3(truth, D3.geo(hd, tg), D3.geo(ob, tg), ot)
        mm = V2.main_metric(der, truth)
        row.update(truth_gates=tgt, gates_valid=not any(tgt.values()), main=mm,
                   main_pass=mm["mean_de"] <= V2.MAIN_MEAN and mm["p95_de"] <= V2.MAIN_P95,
                   identity_baseline=V2.main_metric(hd_o, truth))
        save_png(truth, "truth", c["id"] + ".png")
    if c["id"] in LEAK:
        ta, tb, split = side_truths(c, ob)
        row["leak"] = {"split": split, "INTERPOLATED": leakage(der, ta, tb, split),
                       "EXACT_MAP": leakage(ex, ta, tb, split), "SOFT_MAP": leakage(so, ta, tb, split),
                       "truth": leakage(truth, ta, tb, split)}
    save_png(der, "derived", c["id"] + ".png")
    save_png(ex, "exact", c["id"] + ".png")
    save_png(so, "soft", c["id"] + ".png")
    save_png(hd_o, "hd", c["id"] + ".png")
    save_png(ob_o, "orig", c["id"] + "_base.png")
    save_png(ot, "orig", c["id"] + "_member.png")
    return row


def do_run():
    sp = load_spec()
    res = {"profile": PROFILE, "spec_sha256": sp["sha256"], "implementation": sp["implementation"],
           "run_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "cases": {}}
    for c in sp["cases"]:
        res["cases"][c["id"]] = run_case(c, sp)
    A3.save_json(os.path.join(OUT, "results.json"), res)
    write_results_md(res, sp, read_human())
    print("прогон: %d случаев -> %s" % (len(res["cases"]), os.path.join(OUT, "results.md")))


# ---------- вердикты ----------

def read_human():
    out = {}
    p = os.path.join(OUT, "answers_human.tsv")
    if os.path.exists(p):
        with open(p, encoding=ENC) as f:
            next(f, None)
            for line in f:
                c = line.rstrip("\n").split("\t")
                if len(c) >= 2 and c[1].strip():
                    v = c[1].strip().upper()
                    if v not in ("PASS", "FAIL", "UNSURE"):
                        raise SystemExit("answers_human.tsv: %s - вердикт %r" % (c[0], c[1]))
                    out[c[0].strip()] = v
    return out


def hard(res, sp, vs):
    cs = res["cases"]
    h = {}
    bad1 = [k for k, r in cs.items() if r["status"] != "DERIVED" or any(r["gates"][g] for g in STRUCT)]
    h["H1"] = {"pass": not bad1, "detail": "STRUCTURAL > 0 / отказ: %s" % (", ".join(bad1) or "нет")}
    ps = sp["v3_dependency"]["pass_set"]
    bad2 = [k for k in ps if not vs[k].startswith("PASS")]
    h["H2"] = {"pass": not bad2, "detail": "V3 PASS %s; регрессия: %s" % (", ".join(ps), ", ".join(bad2) or "нет")}
    d3, ok3 = [], True
    for k in H3_CASES:
        m = cs[k]["modes"]
        i, e, s = (m[n]["main"]["mean_de"] for n in ("INTERPOLATED", "EXACT_MAP", "SOFT_MAP"))
        ok = i <= min(e, s) + TIE_DE
        ok3 &= ok
        d3.append("%s I %.2f / E %.2f / S %.2f %s" % (k, i, e, s, "ok" if ok else "ХУЖЕ"))
    h["H3"] = {"pass": ok3, "detail": "; ".join(d3)}
    d4, ok4 = [], True
    for k in LEAK:
        lk = cs[k]["leak"]
        li, lt, ls = lk["INTERPOLATED"]["leak_px"], lk["truth"]["leak_px"], lk["SOFT_MAP"]["leak_px"]
        ok = li == 0 and lt == 0 and ls > 0
        ok4 &= ok
        d4.append("%s утечка I %d, правда %d, SOFT %d, EXACT %d из %d%s" % (
            k, li, lt, ls, lk["EXACT_MAP"]["leak_px"], lk["INTERPOLATED"]["counted_px"],
            "" if ok else (" - ПРОВАЛ" if li else " - НЕ ПОКРЫТ")))
    h["H4"] = {"pass": ok4, "detail": "; ".join(d4)}
    d5 = ["%s %d" % (k, cs[k]["gates"].get(H5_GATE, 0)) for k in H5_CASES]
    h["H5"] = {"pass": all(cs[k]["gates"].get(H5_GATE, 0) == 0 for k in H5_CASES),
               "detail": "%s: %s" % (H5_GATE, ", ".join(d5))}
    bad6 = [k for k, r in cs.items() if not r["deterministic"]]
    h["H6"] = {"pass": not bad6, "detail": "не детерминированы: %s" % (", ".join(bad6) or "нет")}
    return h


def overall(res, sp, hum):
    vs = {k: A3.verdict3(k, r, hum.get(k)) for k, r in res["cases"].items()}
    h = hard(res, sp, vs)
    hard_ok = all(x["pass"] for x in h.values())
    waiting = [k for k, v in vs.items() if v == "AWAITING_HUMAN"]
    settled = [k for k, v in vs.items() if not v.startswith("PASS") and v != "AWAITING_HUMAN"]
    o = "FAIL" if (not hard_ok or settled) else ("AWAITING_HUMAN" if waiting else "PASS")
    return o, vs, h, {"hard_ok": hard_ok, "waiting": waiting, "settled_fail": settled}


# ---------- отчёты ----------

def fmt_gates(d):
    return ", ".join("%s %d" % (g.replace("unintended_local_", "").replace("wrong_palette_", ""), v)
                     for g, v in d.items()) or "0"


def write_results_md(res, sp, hum):
    o, vs, h, ch = overall(res, sp, hum)
    cs = res["cases"]
    L = ["# DERIVE_RECOLOR_ACCEPTANCE_V3.1 - прогон", "",
         "Spec `%s`, вывод `%s` (%s), Stage A `%s`, прогон %s." % (
             sp["sha256"][:12], sp["implementation"]["sha256"][:12], sp["implementation"]["version"],
             sp["stage_a"]["sha256"][:12], res["run_at"]), "",
         "Итог: **%s**; жёсткая приёмка %s%s%s" % (
             o, "пройдена" if ch["hard_ok"] else "НЕ пройдена",
             ("; провал случаев: %s" % ", ".join(ch["settled_fail"])) if ch["settled_fail"] else "",
             ("; ждут человека: %s" % ", ".join(ch["waiting"])) if ch["waiting"] else ""), "",
         "## Жёсткая приёмка", "", "| | условие | итог | подробно |", "|---|---|---|---|"]
    for k, x in h.items():
        L.append("| %s | %s | %s | %s |" % (k, sp["hard_acceptance"][k], "PASS" if x["pass"] else "**FAIL**",
                                            x["detail"]))
    L += ["", "## Случаи", "",
          "| случай | что | цепочка | STRUCT | VISUAL | главные | вердикт V3.1 | V3 |", "|---|---|---|---|---|---|---|---|"]
    v3v = sp["v3_dependency"]["verdicts"]
    for k, r in cs.items():
        what = r["what"] + (" %s -> %s" % (r["base"], r["member"]) if r["kind"] == "real" else "")
        st = ", ".join("%s %d" % (g, r["gates"][g]) for g in STRUCT if r["gates"][g]) or "0"
        vi = ", ".join("%s %d" % (g, r["gates"][g]) for g in VISUAL if r["gates"][g]) or "0"
        main = ("%.2f / %.2f" % (r["main"]["mean_de"], r["main"]["p95_de"])) if r.get("main") else "-"
        L.append("| %s | %s | %s | %s | %s | %s | %s%s | %s |" % (
            k, what, r["chain"].get("geometry_transform") or "REFUSED", st, vi, main, vs[k],
            " (человек)" if k in hum else "", v3v.get(k, "-")))
    L += ["", "## Три режима (диагностика: EXACT и SOFT - базы V3, не кандидаты)", "",
          "| случай | VISUAL I / E / S | ΔE к правде I / E / S | рябь I / E / S |", "|---|---|---|---|"]
    for k, r in cs.items():
        if not r.get("modes"):
            continue
        m = [r["modes"][n] for n in ("INTERPOLATED", "EXACT_MAP", "SOFT_MAP")]
        de = " / ".join("%.2f" % x["main"]["mean_de"] for x in m) if "main" in m[0] else "-"
        L.append("| %s | %s | %s | %s |" % (k, " / ".join(fmt_gates(x["visual"]) for x in m), de,
                                             " / ".join(str(x["speckle"]) for x in m)))
    L += ["", "## Утечка через границу областей (H4)", "",
          "| случай | шов x | I | EXACT | SOFT | правда | считано пикселей | ΔE к своей у шва I / E / S |",
          "|---|---|---|---|---|---|---|---|"]
    for k in LEAK:
        lk = cs[k]["leak"]
        L.append("| %s | %d | %d | %d | %d | %d | %d | %s / %s / %s |" % (
            k, lk["split"], lk["INTERPOLATED"]["leak_px"], lk["EXACT_MAP"]["leak_px"], lk["SOFT_MAP"]["leak_px"],
            lk["truth"]["leak_px"], lk["INTERPOLATED"]["counted_px"], lk["INTERPOLATED"]["near_seam_mean_de_own"],
            lk["EXACT_MAP"]["near_seam_mean_de_own"], lk["SOFT_MAP"]["near_seam_mean_de_own"]))
    L += ["", "## Подробности", ""]
    for k, r in cs.items():
        if r["status"] == "REFUSED":
            L.append("- %s: ОТКАЗ - %s" % (k, json.dumps(r["chain"]["geometry_resolution"], ensure_ascii=False)))
            continue
        i, cv, t = r["info"], r["coverage"], r["chain"]["transfer"]
        bad = i["mapping_wrong"] + i["artifacts"]
        L.append("- %s: геометрия %s; классов %d, областей %d, пикселей на шве областей %d, смешанных %d из %d; "
                 "сигма цветности %s, штриховки %s; контроли ворот: %s%s" % (
                     k, r["chain"]["geometry_transform"], t["classes"], t["regions"], t["region_boundary_px"],
                     t["mixed_px"], t["opaque_px"], t["sigma_chroma"], t["sigma_shade"],
                     "покрыто" if cv["covered"] else "**НЕ покрыто**",
                     ("; " + "; ".join(json.dumps(x, ensure_ascii=False) for x in bad[:4])) if bad else ""))
    with open(os.path.join(OUT, "results.md"), "w", encoding=ENC, newline="\n") as f:
        f.write("\n".join(L) + "\n")


def do_report():
    sp = load_spec()
    res = A3.load_json(os.path.join(OUT, "results.json"))
    if res["spec_sha256"] != sp["sha256"]:
        raise SystemExit("results.json от другого spec")
    hum = read_human()
    write_results_md(res, sp, hum)
    o, vs, h, ch = overall(res, sp, hum)
    L = ["# DERIVE_RECOLOR_ACCEPTANCE_V3.1 - итог", "", "Итог: **%s**" % o, ""]
    for k, x in h.items():
        L.append("- %s %s: %s" % (k, "PASS" if x["pass"] else "FAIL", x["detail"]))
    if ch["settled_fail"]:
        L.append("- провал случаев: %s" % ", ".join("%s %s" % (k, vs[k]) for k in ch["settled_fail"]))
    if ch["waiting"]:
        L.append("- ждут человека: %s" % ", ".join(ch["waiting"]))
    L += ["", "| случай | ожидание | вердикт | человек |", "|---|---|---|---|"]
    for k, r in res["cases"].items():
        L.append("| %s | %s | %s | %s |" % (k, r["expect"], vs[k], hum.get(k, "-")))
    with open(os.path.join(OUT, "report.md"), "w", encoding=ENC, newline="\n") as f:
        f.write("\n".join(L) + "\n")
    print("итог: %s -> %s" % (o, os.path.join(OUT, "report.md")))


# ---------- карточки ----------

def do_cards():
    sp = load_spec()
    res = A3.load_json(os.path.join(OUT, "results.json"))
    if res["spec_sha256"] != sp["sha256"]:
        raise SystemExit("results.json от другого spec")
    need = [k for k, r in res["cases"].items() if r["status"] == "DERIVED"
            and A3.verdict3(k, r, None) == "AWAITING_HUMAN"]
    sc = sp["card"]["scale"]
    d = os.path.join(OUT, "cards")
    os.makedirs(d, exist_ok=True)
    lines = ["# DERIVE_RECOLOR_ACCEPTANCE_V3.1 - карточки", "", "Вопрос (заморожен в spec): " + A3.CARD_Q, "",
             "Панель 4 - вывод INTERPOLATED_MAP_V1. Панель 6 - правда (только синтетика). Ответ - "
             "`answers_human.tsv`. Результаты ворот на карточках не показаны.", ""]
    x4 = lambda a: np.repeat(np.repeat(a, 4, 0), 4, 1)
    ld = lambda *p: A3.read_png(os.path.join(OUT, *p))
    for k in need:
        r = res["cases"][k]
        ob, ot, hd, der = ld("orig", k + "_base.png"), ld("orig", k + "_member.png"), ld("hd", k + ".png"), \
            ld("derived", k + ".png")
        panels = [V2.on(x4(ob), FLOOR), V2.on(hd, FLOOR), V2.on(x4(ot), FLOOR), V2.on(der, FLOOR)]
        chk = V2.checker(der.shape[1], der.shape[0])
        chk.alpha_composite(Image.fromarray(der, "RGBA"))
        panels.append(chk)
        if r["kind"] == "synthetic":
            panels.append(V2.on(ld("truth", k + ".png"), FLOOR))
        pw, ph = panels[0].width * sc, panels[0].height * sc
        card = Image.new("RGBA", (pw * len(panels) + 8 * (len(panels) - 1), ph + 34), (24, 24, 28, 255))
        dr = ImageDraw.Draw(card)
        title = "%s  %s" % (k, ("%s -> %s" % (r["base"], r["member"])) if r["kind"] == "real" else r["what"])
        dr.text((4, 4), title, fill=(255, 255, 0, 255))
        for i, p in enumerate(panels):
            x = i * (pw + 8)
            card.paste(p.resize((pw, ph), Image.NEAREST), (x, 34))
            dr.text((x + 4, 20), sp["card"]["panels"][i], fill=(220, 220, 220, 255))
        card.convert("RGB").save(os.path.join(d, k + ".png"))
        lines.append("- %s: ![%s](cards/%s.png)" % (k, k, k))
    with open(os.path.join(OUT, "cards.md"), "w", encoding=ENC, newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    ans = os.path.join(OUT, "answers_human.tsv")
    if not os.path.exists(ans):
        with open(ans, "w", encoding=ENC, newline="\n") as f:
            f.write("case_id\tverdict\tnote\n")
            for k in need:
                f.write("%s\t\t\n" % k)
    print("карточки: %d (%s) -> %s" % (len(need), ", ".join(need), d))


def do_check():
    load_spec()
    print("spec, код вывода V3.1, Stage A, приёмка V3.1, V3 и V2 не изменились")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("spec", "run", "cards", "report", "check"))
    a = ap.parse_args()
    os.chdir(ROOT)
    {"spec": do_spec, "run": do_run, "cards": do_cards, "report": do_report, "check": do_check}[a.cmd]()


if __name__ == "__main__":
    main()
