"""DERIVE_RECOLOR_ACCEPTANCE_V3 - приёмка детерминированного вывода перекраски V3 (tools/hdart/derive_recolor_v3.py).

Решение: специалист 03.10, передал Vitali в чате - DERIVE_RECOLOR_ACCEPTANCE_V3_PREP разрешён, видеокарта
запрещена. Две стадии вывода (геометрия, цвет), EXACT_MAP по умолчанию, SOFT_MAP только при доказанном
дизеринге. Набор V2 не меняется и идёт регрессией; добавлены контроли soft() C1-C6. Ворота разделены:
STRUCTURAL HARD (силуэт, альфа, выравнивание, преобразование геометрии - не ослабляются никогда) и VISUAL
QUALITY (цвет и пятна, пороги V2 без изменений, MAP_DE 10). Правило, записанное в spec ДО прогона: для
заранее названных визуально-пограничных случаев (R06, R07, R08, R10, R11, S03 - MACHINE_STRICT_HUMAN_PASS)
«структурные ворота 0 + PASS человека = случай PASS», даже если визуальные ворота сработали.

Запрещено в V3 (и не делается): менять V7, таксономию связей, решения семейств; поднимать порог 10; исключения
под ассет; подбирать детектор по R06/R07/...; Qwen для перекраски. Ни модели, ни видеокарты.

Команды (из корня репозитория):
    py -3.13 tools/hdart/derive_recolor_acceptance_v3.py spec     # заморозить (один раз)
    py -3.13 tools/hdart/derive_recolor_acceptance_v3.py run      # прогон, results.md
    py -3.13 tools/hdart/derive_recolor_acceptance_v3.py cards    # карточки тем, кому нужен человек
    py -3.13 tools/hdart/derive_recolor_acceptance_v3.py report   # итог с ответами answers_human.tsv
    py -3.13 tools/hdart/derive_recolor_acceptance_v3.py check    # spec, код и V2 не изменились
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
import derive_recolor_v3 as D3  # noqa: E402

ENC = "utf-8-sig"
ROOT = os.path.dirname(os.path.dirname(HERE))
PROFILE = "DERIVE_RECOLOR_ACCEPTANCE_V3"
OUT = os.path.join(ROOT, "art", "objects", "generation", "probes", "derive-recolor-acceptance-v3")
V2_OUT = "art/objects/generation/probes/derive-recolor-acceptance-v2"
SELF = "tools/hdart/derive_recolor_acceptance_v3.py"
IMPL = "tools/hdart/derive_recolor_v3.py"
V2_SELF = "tools/hdart/derive_recolor_acceptance_v2.py"
FAMILIES = "art/objects/families/families.json"
DECISION = ("специалист 03.10, передал Vitali в чате: DERIVE_RECOLOR_ACCEPTANCE_V3_PREP разрешён, GPU запрещён; "
            "Stage A геометрия (IDENTITY, MIRROR_X), Stage B EXACT_MAP по умолчанию, SOFT_MAP только при "
            "доказанном дизеринге; V2 - регрессия без изменений; контроли soft() C1-C6; ворота STRUCTURAL и "
            "VISUAL; правило MACHINE_STRICT_HUMAN_PASS записано до прогона")

STRUCT = ("geometry_changed", "alpha_changed_unexpectedly", "pixel_support_changed",
          "source_target_alignment_error", "geometry_support_mismatch", "wrong_mirror_state",
          "alpha_topology_changed")
VISUAL = ("wrong_palette_mapping", "unintended_local_artifacts")
BORDERLINE = ("R06", "R07", "R08", "R10", "R11", "S03")
FRNITURE_CHAIN = ("R01", "R02", "S08")
HOLE = 3               # контроль топологии: сквозная дыра 3x3 в непрозрачном окне 7x7
FLOOR = V2.FLOOR

# контроли soft(); C1 - выбирается правилом select_real_dither, записанным в spec вместе с таблицей кандидатов
CONTROLS = [
    {"id": "C1", "kind": "real", "what": "real dither (frozen selection rule)", "route": "recolor",
     "expect": "HUMAN", "dither_expected": True},
    {"id": "C2", "kind": "synthetic", "what": "synthetic dither: checker faces, painter renders the mean tone",
     "base": "BOX_DITHER", "map": "hue120", "alpha": "hard", "painter": "dither_mean", "route": "recolor",
     "expect": "PASS", "dither_expected": True},
    {"id": "C3", "kind": "synthetic", "what": "detailed non-dither object", "base": "U_DISEC2:10", "map": "hue120",
     "alpha": "hard", "painter": "plain", "route": "recolor", "expect": "PASS", "dither_expected": False},
    {"id": "C4", "kind": "synthetic", "what": "dark recolor with bright accent", "base": "FOREST:14", "map": "dark",
     "alpha": "hard", "painter": "plain", "route": "recolor", "expect": "PASS", "dither_expected": False},
    {"id": "C5", "kind": "synthetic", "what": "local recolor: only the left half changes colour",
     "base": "FRNITURE:22", "map": "local", "alpha": "hard", "painter": "plain", "route": "recolor",
     "expect": "PASS", "dither_expected": False},
    {"id": "C6", "kind": "synthetic", "what": "mirror + dark recolor, declared as plain recolor",
     "base": "FRNITURE:9", "map": "dark", "mirror_member": True, "alpha": "hard", "painter": "plain",
     "route": "recolor", "expect": "PASS", "dither_expected": False},
]
C1_RULE = ("families.json: член с relation recolor из одного кадра против канонического кадра семейства; силуэт "
           "оригиналов совпадает точно без преобразования; цвет члена - функция цвета основы (доля >= "
           "relation_probe.FUNC 0.98); есть HD основы в прежнем паке user/mods/hd/hd/TERRAIN; детектор V3 "
           "доказал дизеринг у основы; пара не из набора V2; берётся наибольшее число пикселей дизеринга у "
           "основы, при равенстве - меньший ключ")
HUMAN_CARRY = ("ответ человека из V2 переносится на случай V3, только если вывод V3 совпадает с выводом V2 "
               "(art/.../derive-recolor-acceptance-v2/derived/<id>.png) попиксельно; иначе - новая карточка")
CARD_Q = ("Panel 4 is the member (panel 3) drawn with the detail of panel 2: same shape and orientation, "
          "member's colours, no mud, blotches, halos, 4x4 ripple or colour bleeding? PASS / FAIL / UNSURE")
BODY = ("profile", "decision", "implementation", "v2_dependency", "gates", "thresholds", "borderline",
        "regression", "controls", "c1_selection", "inputs", "mode_rule", "verdict_rule", "overall_rule",
        "human_carry_rule", "card", "forbidden")


# ---------- общее ----------

def rel(p):
    return os.path.join(ROOT, p)


def load_json(p):
    with open(p, encoding=ENC) as f:
        return json.load(f)


def save_json(p, o):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding=ENC, newline="\n") as f:
        json.dump(o, f, ensure_ascii=False, indent=1, sort_keys=True)


def read_png(p):
    return np.asarray(Image.open(p).convert("RGBA"), np.uint8)


def save_png(a, *parts):
    p = os.path.join(OUT, *parts)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    Image.fromarray(a, "RGBA").save(p)
    return p


# ---------- входы ----------

def box_dither():
    """Ящик V2.box, но каждая грань - шахматка из двух цветов (кайма ровная)."""
    a = V2.box()
    pal = {(200, 180, 140): ((214, 192, 150), (168, 140, 100)), (150, 120, 80): ((164, 132, 92), (118, 94, 60)),
           (100, 80, 50): ((112, 92, 60), (80, 60, 36))}
    out = a.copy()
    for y, x in zip(*np.nonzero(a[..., 3])):
        c = tuple(int(v) for v in a[y, x, :3])
        if c in pal:
            out[y, x, :3] = pal[c][(x + y) % 2]
    return out


def mean2x2(a):
    """Художник видит дизеринг ровным средним тоном: цвет - среднее окна 2x2 по непрозрачным."""
    m = a[..., 3] > 0
    v = a[..., :3].astype(np.float64) * m[..., None]
    P = np.pad(v, ((0, 1), (0, 1), (0, 0)))
    M = np.pad(m.astype(np.float64), ((0, 1), (0, 1)))
    s = P[:-1, :-1] + P[1:, :-1] + P[:-1, 1:] + P[1:, 1:]
    n = M[:-1, :-1] + M[1:, :-1] + M[:-1, 1:] + M[1:, 1:]
    out = a.copy()
    out[..., :3] = np.where(m[..., None], np.round(s / np.maximum(n, 1)[..., None]), a[..., :3]).astype(np.uint8)
    return out


def apply_map3(a, kind):
    if kind != "local":
        return V2.apply_map(a, kind)
    out = a.copy()
    for y, x in zip(*np.nonzero(a[..., 3] > 0)):
        if x < a.shape[1] // 2:
            out[y, x, :3] = V2.hue_map(tuple(int(v) for v in a[y, x, :3]))
    return out


def synth3(c):
    """Синтетика контролей: оригинал основы, член, HD основы, правда - тем же художником."""
    base = box_dither() if c["base"] == "BOX_DITHER" else V2.orig(c["base"])
    mem_src = base[:, ::-1] if c.get("mirror_member") else base
    member = apply_map3(mem_src, c["map"])
    tex = V2.noise(base.shape[0] * 4, base.shape[1] * 4)
    paint = (lambda a: mean2x2(a)) if c["painter"] == "dither_mean" else (lambda a: a)
    hd = V2.render(paint(base), c["alpha"], tex)
    truth = V2.render(paint(member), c["alpha"], tex[:, ::-1] if c.get("mirror_member") else tex)
    return base, member, hd, truth


def v2_keys():
    return {c["base"] for c in V2.SYNTH} | {c["base"] for c in V2.REAL} | {c["member"] for c in V2.REAL}


def select_real_dither():
    """Правило C1 (C1_RULE). Возвращает выбранную пару и первые 8 кандидатов."""
    fams = load_json(rel(FAMILIES))
    seen, rows = set(), []
    for fam in fams:
        can = fam["canonical"]
        for mem in fam["members"]:
            if mem.get("relation") != "recolor" or len(mem["keys"]) != 1:
                continue
            key = mem["keys"][0]
            if (can, key) in seen or can in v2_keys() or key in v2_keys():
                continue
            seen.add((can, key))
            s, f = can.split(":")
            hdp = "user/mods/hd/hd/TERRAIN/%s.PCK/%s.png" % (s, f)
            if not os.path.exists(rel(hdp)):
                continue
            try:
                ob, ot = V2.orig(can), V2.orig(key)
            except SystemExit:
                continue
            sb, st = ob[..., 3] > 0, ot[..., 3] > 0
            if ob.shape != ot.shape or not sb.any() or (sb != st).any():
                continue
            if read_png(rel(hdp)).shape[:2] != (ob.shape[0] * 4, ob.shape[1] * 4):
                continue
            if D3.func_fit(D3.codes(ob)[sb], D3.codes(ot)[sb]) < 0.98:
                continue
            n = int((D3.dither_mask(ob) & sb).sum())
            frac = n / int(sb.sum())
            if n < D3.DITHER_MIN_PX or frac < D3.DITHER_MIN_FRAC:
                continue
            rows.append({"base": can, "member": key, "hd": hdp, "dither_px_base": n, "frac": round(frac, 4)})
    rows.sort(key=lambda r: (-r["dither_px_base"], r["base"], r["member"]))
    if not rows:
        raise SystemExit("правило C1 не нашло ни одной пары")
    return rows[0], rows[:8]


def controls_resolved(c1):
    out = []
    for c in CONTROLS:
        c = dict(c)
        if c["id"] == "C1":
            c.update(base=c1["base"], member=c1["member"], hd=c1["hd"])
        out.append(c)
    return out


def regression():
    rows = []
    for c in V2.SYNTH:
        rows.append(dict(c, kind="synthetic", painter="plain", expect_v2=c["expect"], expect="PASS"))
    for c in V2.REAL:
        rows.append(dict(c, kind="real", expect_v2=c["expect"], expect="HUMAN"))
    return rows


def inputs_of(c):
    """(база, член, HD, правда или None) - для регрессии через V2, для контролей через synth3."""
    if c["kind"] == "synthetic":
        if c["id"].startswith("S"):
            return V2.synth_inputs(c)
        return synth3(c)
    ob, ot = V2.orig(c["base"]), V2.orig(c["member"])
    hd = read_png(rel(c["hd"]))
    return ob, ot, hd, None


# ---------- ворота ----------

def components(m):
    """Число связных частей маски (4-связность)."""
    h, w = m.shape
    lab = np.zeros((h, w), np.int32)
    n = 0
    for y0, x0 in zip(*np.nonzero(m)):
        if lab[y0, x0]:
            continue
        n += 1
        st = [(y0, x0)]
        lab[y0, x0] = n
        while st:
            y, x = st.pop()
            for yy, xx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= yy < h and 0 <= xx < w and m[yy, xx] and not lab[yy, xx]:
                    lab[yy, xx] = n
                    st.append((yy, xx))
    return n, lab


def topology(alpha):
    m = alpha > 0
    nc, _ = components(m)
    nb, lab = components(~m)
    edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])).tolist())
    holes = len(set(range(1, nb + 1)) - edge)
    return nc, holes


def mirror_state(der, ot):
    occ = V2.blocks(der)[1] >= V2.OCC
    st = ot[..., 3] > 0
    return int((occ[:, ::-1] != st).sum() < (occ != st).sum())


def gates3(der, hd_o, ob_o, ot):
    g, info = V2.gates(der, hd_o, ob_o, ot)
    g["geometry_support_mismatch"] = int(((ob_o[..., 3] > 0) != (ot[..., 3] > 0)).sum())
    g["wrong_mirror_state"] = mirror_state(der, ot)
    td, th = topology(der[..., 3]), topology(hd_o[..., 3])
    g["alpha_topology_changed"] = abs(td[0] - th[0]) + abs(td[1] - th[1])
    info["topology_derived"], info["topology_hd"] = td, th
    return g, info


def punch(der):
    """Контроль топологии: дыра HOLE x HOLE в непрозрачном окне 7x7, ближайшем к центру тяжести."""
    op = der[..., 3] >= V2.ALPHA_OPAQUE
    ys, xs = np.nonzero(op)
    if not len(ys):
        return None
    cy, cx = ys.mean(), xs.mean()
    best = None
    for y, x in zip(ys, xs):
        if 3 <= y < der.shape[0] - 3 and 3 <= x < der.shape[1] - 3 and op[y - 3:y + 4, x - 3:x + 4].all():
            d = (y - cy) ** 2 + (x - cx) ** 2
            if best is None or d < best[0]:
                best = (d, y, x)
    if best is None:
        return None
    _, y, x = best
    out = der.copy()
    out[y - 1:y + 2, x - 1:x + 2, 3] = 0
    return out


def coverage3(info, der, hd_o, ob_o, ot, like):
    cov = V2.coverage(info, hd_o, ob_o, ot, like)
    st = ot[..., 3] > 0
    need_flip = bool((st != st[:, ::-1]).any())
    flip = gates3(der[:, ::-1].copy(), hd_o, ob_o, ot)[0]["wrong_mirror_state"] > 0 if need_flip else None
    ph = punch(der)
    hole = gates3(ph, hd_o, ob_o, ot)[0]["alpha_topology_changed"] > 0 if ph is not None else None
    ok = cov["covered"] and flip is not False and hole is not False
    return dict(cov, mirror_flip_needed=need_flip, mirror_flip_caught=flip, hole_possible=ph is not None,
                hole_caught=hole, covered=ok)


def speckle(der, hd, region):
    """Рябь вывода против основы: разброс ln((L+5)/(L+5)) за вычетом среднего окна 5x5, по HD-пикселям
    области (дизеринг, расширенный, x4); оба непрозрачны."""
    Ld, Lb = V2.lab(der[..., :3])[..., 0], V2.lab(hd[..., :3])[..., 0]
    lnr = np.log((Ld + 5) / (Lb + 5))
    op = (der[..., 3] >= V2.ALPHA_OPAQUE) & (hd[..., 3] >= V2.ALPHA_OPAQUE)
    P = np.pad(np.where(op, lnr, 0.0), 2)
    M = np.pad(op.astype(np.float64), 2)
    h, w = lnr.shape
    s = sum(P[dy:dy + h, dx:dx + w] for dy in range(5) for dx in range(5))
    n = sum(M[dy:dy + h, dx:dx + w] for dy in range(5) for dx in range(5))
    hp = lnr - s / np.maximum(n, 1)
    R = np.repeat(np.repeat(region, 4, 0), 4, 1) & op
    return round(float(hp[R].std()), 4) if R.sum() >= 16 else None


# ---------- spec ----------

def impl_state():
    st = {"module": IMPL, "sha256": V2.fsha(rel(IMPL)), "version": D3.VERSION,
          "constants": {k: getattr(D3, k) for k in ("GEOMETRIES", "MODES", "DITHER_NB", "DITHER_MIN_PX",
                                                    "DITHER_MIN_FRAC", "DITHER_GROW", "PICK_LAMBDA", "SPREAD_N",
                                                    "CHROMA_W0", "CHROMA_W1")}}
    return json.loads(json.dumps(st))      # кортежи как в spec.json - списками


def v2_state():
    return {"module": V2_SELF, "sha256": V2.fsha(rel(V2_SELF)),
            "cases_sha256": V2.jsha({"synthetic": V2.SYNTH, "real": V2.REAL}),
            "spec_sha256": load_json(rel(V2_OUT + "/spec.json"))["sha256"]}


def spec_body():
    c1, cand = select_real_dither()
    ctl = controls_resolved(c1)
    inputs = {}
    for c in regression() + ctl:
        ob, ot, hd, truth = inputs_of(c)
        d = {"base_orig": V2.asha(ob), "member_orig": V2.asha(ot), "hd": V2.asha(hd)}
        if truth is not None:
            d["truth"] = V2.asha(truth)
        if c["kind"] == "real":
            d["hd_file_sha256"] = V2.fsha(rel(c["hd"]))
        inputs[c["id"]] = d
    return {
        "profile": PROFILE, "decision": DECISION, "implementation": impl_state(), "v2_dependency": v2_state(),
        "gates": {"structural_hard": {g: "must be 0, never weakened" for g in STRUCT},
                  "visual_quality": {g: "must be 0, except the borderline rule" for g in VISUAL}},
        "thresholds": {k: getattr(V2, k) for k in ("MAP_DE", "MAP_MIN_CELLS", "ART_LN", "ART_AB", "ART_MIN_CELLS",
                                                   "MAIN_MEAN", "MAIN_P95", "ALPHA_OPAQUE", "OCC", "NOISE_SEED",
                                                   "NOISE_AMP")} | {"HOLE": HOLE},
        "borderline": {"cases": list(BORDERLINE), "class": "MACHINE_STRICT_HUMAN_PASS",
                       "rule": ("Machine structural PASS + human visual PASS = case PASS: if all STRUCTURAL gates "
                                "are 0 and coverage holds, VISUAL gates > 0 (and, for synthetic, the main metric) "
                                "do not fail the case by themselves; the human verdict on the V3 card decides. "
                                "Only these cases; any other case with a VISUAL gate > 0 is VISUAL_FAIL")},
        "regression": regression(), "controls": ctl,
        "c1_selection": {"rule": C1_RULE, "chosen": c1, "candidates": cand},
        "inputs": inputs,
        "mode_rule": ("derive_recolor_v3: EXACT_MAP by default; SOFT_MAP only when the detector proves dithering "
                      "(clustered checker pixels of base or member >= DITHER_MIN_PX and >= DITHER_MIN_FRAC of the "
                      "support), soft only inside the grown dither region. Every case is also derived in the "
                      "other mode: proven -> other = EXACT_MAP; not proven -> other = SOFT_MAP over the whole "
                      "support (soft where there is no dither). Controls: the detector decision must equal "
                      "dither_expected; proven -> SOFT_MAP better than EXACT_MAP (synthetic: mean ΔE to truth; "
                      "real: speckle); not proven -> EXACT_MAP better (synthetic: mean ΔE to truth)"),
        "verdict_rule": ("REFUSED or any STRUCTURAL gate > 0 -> STRUCT_FAIL; synthetic gates invalid on truth -> "
                         "GATE_INVALID; coverage (V2 controls + mirror flip caught when the member is asymmetric + "
                         "punched hole caught) missing -> UNCOVERED; VISUAL gate > 0 or synthetic main gate failed: "
                         "borderline case -> human (PASS -> PASS as MACHINE_STRICT_HUMAN_PASS), other -> "
                         "VISUAL_FAIL; otherwise synthetic -> PASS, real -> human PASS / HUMAN_FAIL / HUMAN_UNSURE / "
                         "AWAITING_HUMAN"),
        "overall_rule": ("V3 PASS: every regression case and every control PASS; FRNITURE chain R01, R02, S08 - "
                         "geometry MIRROR_X, STRUCTURAL 0; every control's mode check passes; each derivation run "
                         "twice is byte-identical. Any case waiting for a human -> AWAITING_HUMAN"),
        "human_carry_rule": HUMAN_CARRY,
        "card": {"question": CARD_Q, "panels": ["1 base original x4 (chain orientation)", "2 HD base (chain "
                 "orientation)", "3 member original x4", "4 derived (selected mode)", "5 derived on checker",
                 "6 truth (synthetic) / other mode (controls)"], "scale": 2, "floor_rgb": list(FLOOR),
                 "answers": "answers_human.tsv: case_id, verdict (PASS|FAIL|UNSURE), note"},
        "forbidden": ["V7 not changed", "relation taxonomy not changed", "families decisions not changed",
                      "MAP_DE stays 10", "no asset-specific exceptions in derive_recolor_v3", "detector not fitted "
                      "to R06/R07/...", "no Qwen, no model, no GPU"],
    }


def do_spec():
    p = os.path.join(OUT, "spec.json")
    if os.path.exists(p):
        raise SystemExit("spec.json уже записан - он неизменяем (%s)" % p)
    body = spec_body()
    body["sha256"] = V2.jsha({k: body[k] for k in BODY})
    body["frozen_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    body["self_sha256"] = V2.fsha(rel(SELF))
    save_json(p, body)
    c1 = body["c1_selection"]["chosen"]
    print("spec заморожен: %s, регрессия %d, контроли %d, C1 %s -> %s, sha %s" % (
        p, len(body["regression"]), len(body["controls"]), c1["base"], c1["member"], body["sha256"][:12]))


def load_spec():
    sp = load_json(os.path.join(OUT, "spec.json"))
    if V2.jsha({k: sp[k] for k in BODY}) != sp["sha256"]:
        raise SystemExit("spec.json изменён после заморозки")
    if impl_state() != sp["implementation"]:
        raise SystemExit("код вывода V3 изменился после заморозки")
    if v2_state() != sp["v2_dependency"]:
        raise SystemExit("V2 (код, случаи или spec) изменился после заморозки V3")
    if V2.fsha(rel(SELF)) != sp["self_sha256"]:
        raise SystemExit("сама приёмка V3 изменилась после заморозки")
    return sp


# ---------- run ----------

def run_case(c, sp):
    ob, ot, hd, truth = inputs_of(c)
    inp = sp["inputs"][c["id"]]
    got = {"base_orig": V2.asha(ob), "member_orig": V2.asha(ot), "hd": V2.asha(hd)}
    if truth is not None:
        got["truth"] = V2.asha(truth)
    if c["kind"] == "real":
        got["hd_file_sha256"] = V2.fsha(rel(c["hd"]))
    if got != inp:
        raise SystemExit("%s: входы не те, что в spec" % c["id"])
    der, chain = D3.derive(hd, ob, ot, c["route"])
    der2, chain2 = D3.derive(hd, ob, ot, c["route"])
    det = (der is None and der2 is None) or (der is not None and der2 is not None and (der == der2).all())
    row = {"kind": c["kind"], "what": c["what"], "route": c["route"], "expect": c["expect"],
           "base": c["base"], "member": c.get("member"), "chain": chain, "deterministic": bool(det and
                                                                                         chain == chain2)}
    if der is None:
        row.update(status="REFUSED", gates={g: 0 for g in STRUCT + VISUAL})
        row["gates"]["geometry_support_mismatch"] = min(chain["geometry_resolution"]["support_mismatch"].values())
        return row
    g = chain["geometry_transform"]
    hd_o, ob_o = D3.geo(hd, g), D3.geo(ob, g)
    gt, info = gates3(der, hd_o, ob_o, ot)
    row.update(status="DERIVED", gates=gt, info=info)
    row["coverage"] = coverage3(info, der, hd_o, ob_o, ot, truth if truth is not None else der)
    proven = chain["dither"]["proven"]
    other_mode = "EXACT_MAP" if proven else "SOFT_MAP"
    oth, och = D3.derive(hd, ob, ot, c["route"], mode=other_mode, soft_scope="detected" if proven else "support")
    dmask, _ = D3.detect(ob_o, ot)
    sup = (ob_o[..., 3] > 0) & (ot[..., 3] > 0)
    region = D3.grow(dmask, D3.DITHER_GROW) & sup if proven else sup
    sel = chain["mode_selected_by_detector"]
    row["modes"] = {"selected": sel, "other": other_mode, "other_soft_scope": och.get("soft_scope"),
                    "speckle": {sel: speckle(der, hd_o, region), other_mode: speckle(oth, hd_o, region)},
                    "other_diff_px": int((oth != der).any(-1).sum())}
    if truth is not None:
        tg = "MIRROR_X" if c.get("mirror_member") else "IDENTITY"
        tgt, _ = gates3(truth, D3.geo(hd, tg), D3.geo(ob, tg), ot)
        mm = V2.main_metric(der, truth)
        row.update(truth_gates=tgt, gates_valid=not any(tgt.values()), main=mm,
                   main_pass=mm["mean_de"] <= V2.MAIN_MEAN and mm["p95_de"] <= V2.MAIN_P95,
                   identity_baseline=V2.main_metric(hd_o, truth))
        row["modes"]["main"] = {sel: mm, other_mode: V2.main_metric(oth, truth)}
        save_png(truth, "truth", c["id"] + ".png")
    if c["id"].startswith("C"):
        row["modes"]["check"] = mode_check(c, row)
    save_png(der, "derived", c["id"] + ".png")
    save_png(oth, "other_mode", c["id"] + ".png")
    save_png(hd_o, "hd", c["id"] + ".png")
    save_png(ob_o, "orig", c["id"] + "_base.png")
    save_png(ot, "orig", c["id"] + "_member.png")
    v2p = rel(V2_OUT + "/derived/%s.png" % c["id"])
    if os.path.exists(v2p):
        old = read_png(v2p)
        row["same_as_v2"] = bool(old.shape == der.shape and (old == der).all())
    return row


def mode_check(c, row):
    m = row["modes"]
    proven = row["chain"]["dither"]["proven"]
    ok_det = proven == c["dither_expected"]
    if row["kind"] == "synthetic":
        e, s = m["main"]["EXACT_MAP"]["mean_de"], m["main"]["SOFT_MAP"]["mean_de"]
        better = s < e if proven else e < s
        metric = "mean ΔE to truth: EXACT %.2f, SOFT %.2f" % (e, s)
    else:
        e, s = m["speckle"]["EXACT_MAP"], m["speckle"]["SOFT_MAP"]
        better = (s is not None and e is not None and (s < e if proven else e < s))
        metric = "speckle: EXACT %s, SOFT %s" % (e, s)
    return {"detector_as_expected": ok_det, "right_mode_better": bool(better), "metric": metric,
            "pass": bool(ok_det and better)}


def do_run():
    sp = load_spec()
    res = {"profile": PROFILE, "spec_sha256": sp["sha256"], "implementation": sp["implementation"],
           "run_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "cases": {}}
    for c in sp["regression"] + sp["controls"]:
        res["cases"][c["id"]] = run_case(c, sp)
    save_json(os.path.join(OUT, "results.json"), res)
    write_results_md(res, sp, read_human(sp))
    print("прогон: %d случаев -> %s" % (len(res["cases"]), os.path.join(OUT, "results.md")))


# ---------- вердикты ----------

def v2_human():
    out = {}
    p = rel(V2_OUT + "/answers_human.tsv")
    with open(p, encoding=ENC) as f:
        next(f, None)
        for line in f:
            c = line.rstrip("\n").split("\t")
            if len(c) >= 2 and c[1].strip():
                out[c[0].strip()] = c[1].strip().upper()
    return out


def read_human(sp=None):
    """Ответы человека на карточки V3 плюс перенос из V2 по HUMAN_CARRY (только при попиксельном совпадении)."""
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
                    out[c[0].strip()] = (v, "V3 card")
    return out


def human_for(k, r, hum, v2h):
    if k in hum:
        return hum[k]
    if r.get("same_as_v2") and k in v2h:
        return v2h[k], "V2 card (output identical)"
    return None, None


def verdict3(k, r, human):
    if r["status"] == "REFUSED" or any(r["gates"][g] for g in STRUCT):
        return "STRUCT_FAIL"
    if r["kind"] == "synthetic" and not r["gates_valid"]:
        return "GATE_INVALID"
    if not r["coverage"]["covered"]:
        return "UNCOVERED"
    visual_bad = any(r["gates"][g] for g in VISUAL) or (r["kind"] == "synthetic" and not r["main_pass"])
    hv = {"PASS": "PASS", "FAIL": "HUMAN_FAIL", "UNSURE": "HUMAN_UNSURE"}
    if visual_bad:
        if k not in BORDERLINE:
            return "VISUAL_FAIL"
        return {"PASS": "PASS_MACHINE_STRICT_HUMAN_PASS"}.get(human, hv.get(human, "AWAITING_HUMAN"))
    if r["kind"] == "synthetic":
        return "PASS"
    return hv.get(human, "AWAITING_HUMAN")


def overall(res, hum):
    v2h = v2_human()
    cs = res["cases"]
    vs, src = {}, {}
    for k, r in cs.items():
        h, s = human_for(k, r, hum, v2h)
        vs[k] = verdict3(k, r, h)
        src[k] = s
    passed = lambda v: v.startswith("PASS")
    fr = all(cs[k]["status"] == "DERIVED" and cs[k]["chain"]["geometry_transform"] == "MIRROR_X"
             and not any(cs[k]["gates"][g] for g in STRUCT) for k in FRNITURE_CHAIN)
    modes = all(r["modes"]["check"]["pass"] for k, r in cs.items() if k.startswith("C") and r.get("modes"))
    det = all(r["deterministic"] for r in cs.values())
    waiting = [k for k, v in vs.items() if v == "AWAITING_HUMAN"]
    ok = all(passed(v) for v in vs.values()) and fr and modes and det
    bad_settled = [k for k, v in vs.items() if not passed(v) and v != "AWAITING_HUMAN"]
    if bad_settled or not (fr and modes and det):
        o = "FAIL"
    elif waiting:
        o = "AWAITING_HUMAN"
    else:
        o = "PASS" if ok else "FAIL"
    return o, vs, src, {"frniture_chain": fr, "mode_checks": modes, "deterministic": det, "waiting": waiting,
                        "settled_fail": bad_settled}


# ---------- отчёты ----------

def write_results_md(res, sp, hum):
    o, vs, src, ch = overall(res, hum)
    cs = res["cases"]
    L = ["# DERIVE_RECOLOR_ACCEPTANCE_V3 - прогон", "",
         "Spec `%s`, вывод `%s` (%s), прогон %s." % (sp["sha256"][:12], sp["implementation"]["sha256"][:12],
                                                    sp["implementation"]["version"], res["run_at"]), "",
         "Итог: **%s**; цепочка FRNITURE %s; проверки режимов %s; детерминизм %s%s%s" % (
             o, "да" if ch["frniture_chain"] else "НЕТ", "да" if ch["mode_checks"] else "НЕТ",
             "да" if ch["deterministic"] else "НЕТ",
             ("; провал: %s" % ", ".join(ch["settled_fail"])) if ch["settled_fail"] else "",
             ("; ждут человека: %s" % ", ".join(ch["waiting"])) if ch["waiting"] else ""), "",
         "| случай | что | заявлено | цепочка | режим | STRUCT | VISUAL | главные | вердикт |",
         "|---|---|---|---|---|---|---|---|---|"]
    for k, r in cs.items():
        chn = r["chain"]
        what = r["what"] + (" %s -> %s" % (r["base"], r["member"]) if r["kind"] == "real" else "")
        st = ", ".join("%s %d" % (g, r["gates"][g]) for g in STRUCT if r["gates"][g]) or "0"
        vi = ", ".join("%s %d" % (g, r["gates"][g]) for g in VISUAL if r["gates"][g]) or "0"
        main = ("%.2f / %.2f" % (r["main"]["mean_de"], r["main"]["p95_de"])) if r.get("main") else "-"
        L.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s%s |" % (
            k, what, r["route"], chn.get("geometry_transform") or "REFUSED",
            (chn.get("color_transform") or "-").replace("RECOLOR_", ""), st, vi, main, vs[k],
            (" (%s)" % src[k]) if src[k] else ""))
    L += ["", "## Режимы (выбранный против другого)", "",
          "| случай | дизеринг | выбран | другой | рябь | ΔE к правде | проверка |", "|---|---|---|---|---|---|---|"]
    for k, r in cs.items():
        if not r.get("modes"):
            continue
        m, d = r["modes"], r["chain"]["dither"]
        sp_ = ", ".join("%s %s" % (a.replace("_MAP", ""), b) for a, b in m["speckle"].items())
        de = ", ".join("%s %.2f" % (a.replace("_MAP", ""), b["mean_de"]) for a, b in m.get("main", {}).items())
        chk = m.get("check")
        L.append("| %s | %d px (%.1f%%) | %s | %s%s | %s | %s | %s |" % (
            k, d["dither_px"], 100 * d["dither_frac"], m["selected"], m["other"],
            " (%s)" % m["other_soft_scope"] if m["other_soft_scope"] else "", sp_, de or "-",
            ("PASS" if chk["pass"] else "FAIL: %s" % chk["metric"]) if chk else "-"))
    L += ["", "## Подробности", ""]
    for k, r in cs.items():
        if r["status"] == "REFUSED":
            L.append("- %s: ОТКАЗ - %s" % (k, json.dumps(r["chain"]["geometry_resolution"], ensure_ascii=False)))
            continue
        i, cv = r["info"], r["coverage"]
        bad = i["mapping_wrong"] + i["artifacts"]
        L.append("- %s: геометрия %s (%s), отличие от V2 %s; контроли: пятна %s, цвет %s, отражение %s, дыра %s"
                 "%s%s" % (
                     k, r["chain"]["geometry_transform"], r["chain"]["geometry_resolution"]["reason"],
                     {True: "нет (вывод тот же)", False: "есть", None: "-"}[r.get("same_as_v2")],
                     "пойман" if cv["blotch_caught"] else "НЕ пойман",
                     ("пойман" if cv["no_transfer_caught"] else "НЕ пойман") if cv["colour_change_needed"]
                     else "не нужен",
                     {True: "пойман", False: "НЕ пойман", None: "не нужен"}[cv["mirror_flip_caught"]],
                     {True: "поймана", False: "НЕ поймана", None: "негде"}[cv["hole_caught"]],
                     "" if cv["covered"] else " - **ворота случай не проверяют**",
                     ("; " + "; ".join(json.dumps(x, ensure_ascii=False) for x in bad[:4])) if bad else ""))
    with open(os.path.join(OUT, "results.md"), "w", encoding=ENC, newline="\n") as f:
        f.write("\n".join(L) + "\n")


def do_report():
    sp = load_spec()
    res = load_json(os.path.join(OUT, "results.json"))
    if res["spec_sha256"] != sp["sha256"]:
        raise SystemExit("results.json от другого spec")
    hum = read_human(sp)
    write_results_md(res, sp, hum)
    o, vs, src, ch = overall(res, hum)
    L = ["# DERIVE_RECOLOR_ACCEPTANCE_V3 - итог", "", "Итог: **%s**" % o, "",
         "- цепочка FRNITURE (R01, R02, S08: MIRROR_X, STRUCTURAL 0): %s" % ("да" if ch["frniture_chain"] else "НЕТ"),
         "- проверки режимов контролей: %s" % ("да" if ch["mode_checks"] else "НЕТ"),
         "- детерминизм: %s" % ("да" if ch["deterministic"] else "НЕТ")]
    if ch["settled_fail"]:
        L.append("- провал: %s" % ", ".join("%s %s" % (k, vs[k]) for k in ch["settled_fail"]))
    if ch["waiting"]:
        L.append("- ждут человека: %s" % ", ".join(ch["waiting"]))
    L += ["", "| случай | ожидание | вердикт | человек |", "|---|---|---|---|"]
    for k, r in res["cases"].items():
        h = human_for(k, r, hum, v2_human())
        L.append("| %s | %s | %s | %s |" % (k, r["expect"], vs[k], ("%s, %s" % h) if h[0] else "-"))
    with open(os.path.join(OUT, "report.md"), "w", encoding=ENC, newline="\n") as f:
        f.write("\n".join(L) + "\n")
    print("итог: %s -> %s" % (o, os.path.join(OUT, "report.md")))


# ---------- карточки ----------

def do_cards():
    sp = load_spec()
    res = load_json(os.path.join(OUT, "results.json"))
    if res["spec_sha256"] != sp["sha256"]:
        raise SystemExit("results.json от другого spec")
    hum = read_human(sp)
    v2h = v2_human()
    need = []
    for k, r in res["cases"].items():
        if r["status"] != "DERIVED":
            continue
        h, _ = human_for(k, r, {}, v2h)
        if verdict3(k, r, h) == "AWAITING_HUMAN":
            need.append(k)
    sc = sp["card"]["scale"]
    d = os.path.join(OUT, "cards")
    os.makedirs(d, exist_ok=True)
    lines = ["# DERIVE_RECOLOR_ACCEPTANCE_V3 - карточки", "", "Вопрос (заморожен в spec): " + CARD_Q, "",
             "Панель 6: у синтетики - правда, у контролей C - вывод ДРУГИМ режимом (для сравнения; оценивается "
             "панель 4). Ответ - `answers_human.tsv`. Результаты ворот на карточках не показаны.", ""]
    x4 = lambda a: np.repeat(np.repeat(a, 4, 0), 4, 1)
    for k in need:
        r = res["cases"][k]
        ld = lambda *p: read_png(os.path.join(OUT, *p))
        ob, ot, hd, der = ld("orig", k + "_base.png"), ld("orig", k + "_member.png"), ld("hd", k + ".png"), \
            ld("derived", k + ".png")
        panels = [V2.on(x4(ob), FLOOR), V2.on(hd, FLOOR), V2.on(x4(ot), FLOOR), V2.on(der, FLOOR)]
        ch = V2.checker(der.shape[1], der.shape[0])
        ch.alpha_composite(Image.fromarray(der, "RGBA"))
        panels.append(ch)
        if k.startswith("C"):
            panels.append(V2.on(ld("other_mode", k + ".png"), FLOOR))
        elif r["kind"] == "synthetic":
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
    print("spec, код вывода V3, приёмка V3 и V2 не изменились")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("spec", "run", "cards", "report", "check"))
    a = ap.parse_args()
    os.chdir(ROOT)
    {"spec": do_spec, "run": do_run, "cards": do_cards, "report": do_report, "check": do_check}[a.cmd]()


if __name__ == "__main__":
    main()
