#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V5_COMPONENT_VALIDATION_V1 - слепая проверка новых компонентов V5_PREP (специалист 02.10, docs/DECISIONS.md).

Итог V5_PREP: formal legacy-gate PASS, freeze readiness NOT YET (R-181). До заморозки V5 проверяются вслепую:
  1. ASSEMBLY_CANDIDATE_V1 - срабатывания ASM по одному месту (AOs/AWs), повторные кандидаты (AOc/AWc/AFc),
     STRONG по нескольким местам (AO/AW/AF) и трудные отрицательные: одностороннее соседство, узор (партнёр на
     нескольких сдвигах), «просто стоят рядом» (сосед не в ядре сборки), взаимное по одному месту без конструкции
     или порядка;
  2. ALIGNED_RECOLOR_V1 - все срабатывания AR1 и отрицательные: выровнен, но не прошёл ТОЛЬКО границы
     (класс KITSUNE - слишком ли строг порог 0.80 для класса), выровнен, но не прошёл функцию цвета или остаток,
     похожий силуэт после сдвига ниже порога;
  3. класс вертикальной стопки - срабатывания ASM со сдвигом по этажу, отдельным слоем.

Пороги детекторов не меняются: модули aligned_recolor_v1 и assembly_discovery_v1 только вызываются, их хэши
записаны в FREEZE.json до отбора. Кадры наборов holdout V4 (80 кадров), кадры истины v2 и пар пула V4 в выборку не
идут; срабатывания на 80 кадрах вне пула V4 (KNOWN80) судятся отдельным слоем и в точность не входят.

Пакет - тот же, что у holdout V4 (relation_truth_v2.write_pack, JUDGE.md V4): два независимых судьи на пару,
слой пары и причина отбора судье не показываются (только key.json). Эталон пары - tv.combine_pair с авторитетом
(байтовая копия, ребро MCD), подтип - по самому ярлыку, как в зеркальной проверке: у обоих - да, ни у одного -
нет, у одного - OPEN.

Готовность (до ответов):
  ASSEMBLY candidate existence precision >= 0.95 - срабатывания ASM уровня CANDIDATE;
  ASSEMBLY STRONG typed precision        >= 0.95 - срабатывания ASM уровня STRONG, подтип COMPOSITE;
  AR1 - диагностика: точность существования и подтипа производного, разбор по корзинам границ.
Закрытый знаменатель меньше N_MIN - INSUFFICIENT_SAMPLE. Точность - по выборке и взвешенная по численности слоёв.

Команды: freeze, scan, pack, check, lockref, report. VERIFIED ставит только человек.
"""
import argparse
import json
import math
import os
import sys
import time
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aligned_recolor_v1 as ar                   # noqa: E402
import assembly_discovery_v1 as asm               # noqa: E402
import identity_routing as ir                     # noqa: E402
import relation_discovery_v2 as v2                # noqa: E402
import relation_discovery_v3 as v3                # noqa: E402
import relation_discovery_v4 as v4                # noqa: E402
import relation_taxonomy as tx                    # noqa: E402

ENC = ir.ENC
PROFILE = "V5_COMPONENT_VALIDATION_V1"
OUT = os.path.join(ir.PROBES, "v5-component-validation")
HOLD = os.path.join(ir.PROBES, "relation-holdout-v4")
V5 = os.path.join(ir.PROBES, "relation-discovery-v5-prep")
SEED = "v5-component-validation-2026-10-02"
SCAN_SOURCES = 8000             # исходных кадров просмотреть не больше
BATCH_PAIRS = 40                # как holdout V4
N_MIN = 10
GATE = 0.95
# слой -> (сколько взять, семейство, описание); порядок - приоритет при выборе одной пары на исходный кадр
STRATA = [
    ("AR1_TRIGGER", 60, "ar_pos", "срабатывание AR1"),
    ("ASM_VERTICAL", 30, "asm_pos", "срабатывание ASM любого уровня со сдвигом по этажу"),
    ("AR1_BORDER_ONLY", 40, "ar_neg", "AR1: выровнен, не прошёл только порог границ"),
    ("ASM_STRONG", 60, "asm_pos", "ASM STRONG (AO/AW/AF), сборка по нескольким местам"),
    ("ASM_SINGLE", 60, "asm_pos", "ASM CANDIDATE по одному месту (AOs/AWs)"),
    ("ASM_REPEAT_CAND", 40, "asm_pos", "ASM CANDIDATE повторный (AOc/AWc/AFc)"),
    ("ASM_NEG_SINGLE_REJECT", 20, "asm_neg", "взаимно по одному месту, без конструкции или порядка - довода нет"),
    ("ASM_NEG_ONE_SIDED", 30, "asm_neg", "партнёр ядра a, но не взаимно или другая модель - довода нет"),
    ("ASM_NEG_PATTERN", 20, "asm_neg", "сосед в ядре на нескольких сдвигах (узор) - довода нет"),
    ("AR1_NEAR_MISS", 20, "ar_neg", "AR1: выровнен, не прошёл функцию цвета, цвета или остаток"),
    ("AR1_LOOKALIKE", 15, "ar_neg", "AR1: силуэт после сдвига ниже порога (префильтр)"),
    ("ASM_NEG_NEAR", 30, "asm_neg", "стоят рядом по грани, но сосед не в ядре сборки - «просто рядом»"),
]
QUOTA = {s: n for s, n, _f, _d in STRATA}
FAMILY = {s: f for s, _n, f, _d in STRATA}
FAMILY.update({"KNOWN80_AR1": "known", "KNOWN80_ASM": "known"})
CODE = ["tools/hdart/v5_component_validation.py", "tools/test_v5_component_validation.py",
        "tools/hdart/aligned_recolor_v1.py", "tools/hdart/assembly_discovery_v1.py"]
DERIVED_SUB = set(tx.DERIVED_LABELS) | {"EXACT_COPY"}
BORDER_BINS = (0.5, 0.6, 0.7, 0.8)


def p(*a):
    return os.path.join(OUT, *a)


def order(s, salt=SEED):
    return tx_order(s, salt)


def tx_order(s, salt):
    import hashlib
    return hashlib.sha256((salt + "|" + s).encode()).hexdigest()


def pk(a, b):
    return tx.pk(a, b)


def spec():
    return {"profile": PROFILE, "decision": "специалист 02.10, передал Vitali в чате (docs/DECISIONS.md 2026-10-02)",
            "strata": [{"name": s, "quota": n, "family": f, "what": d} for s, n, f, d in STRATA],
            "known80": "срабатывания AR1 и ASM на 80 кадрах вне пула V4 (found5.json) - все, отдельным слоем",
            "scan_sources": SCAN_SOURCES, "seed": SEED, "batch_pairs": BATCH_PAIRS, "judges": 2, "n_min": N_MIN,
            "gate": GATE, "border_bins": list(BORDER_BINS),
            "sampling": "исходные кадры по хэшу; на кадр не больше одной пары, кадр в выборке один раз; в слое пара "
                        "наборов один раз; слой - первый по порядку STRATA, где ещё нужна пара",
            "exclusions": "все кадры наборов 80 кадров holdout V4, кадры истины v2, кадры пар пула V4",
            "readiness": {"asm_candidate_existence_precision": GATE, "asm_strong_typed_precision": GATE,
                          "ar1": "диагностика"},
            "subtype_rule": "ярлык у обоих судей - да, ни у одного - нет, у одного - OPEN; существование - "
                            "relation_truth_v2.combine_pair с авторитетом",
            "ar1_params": ar.PARAMS, "asm_params": asm.PARAMS}


def code_sha():
    return {c: v2.file_sha(c) for c in CODE}


def do_freeze():
    if os.path.exists(p("FREEZE.json")):
        raise SystemExit("уже заморожено: %s" % p("FREEZE.json"))
    if os.path.exists(p("key.json")):
        raise SystemExit("выборка уже есть - заморозка после неё не имеет смысла")
    os.makedirs(OUT, exist_ok=True)
    ir.dump_json(p("FREEZE.json"), {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "spec": spec(),
                                    "code_sha256": code_sha()})
    print("заморожено: %s, sha256 %s" % (p("FREEZE.json"), v2.file_sha(p("FREEZE.json"))[:12]))


def check_freeze():
    if not os.path.exists(p("FREEZE.json")):
        raise SystemExit("нет FREEZE.json - сначала freeze")
    fz = ir.load_json(p("FREEZE.json"))
    bad = [c for c, s in fz["code_sha256"].items() if v2.file_sha(c) != s]
    if json.dumps(fz["spec"], sort_keys=True, ensure_ascii=False) != \
            json.dumps(json.loads(json.dumps(spec(), ensure_ascii=False)), sort_keys=True, ensure_ascii=False):
        bad.append("spec")
    if bad:
        raise SystemExit("изменено после заморозки: %s" % ", ".join(bad))
    return fz


# ---------------------------------------------------------------- исключения

def exclusions():
    """-> (наборы, кадры, пары), которые выборка не берёт."""
    h = ir.load_json(os.path.join(HOLD, "holdout.json"))
    sets = {v2.split(x["asset_id"])[0].upper() for x in h["items"]}
    frames = set()
    for r in ir.load_json(os.path.join(HOLD, "inputs", "truth_v2.json"))["pairs"]:
        frames |= {r["a"].upper(), r["b"].upper()}
    pairs = set()
    for it in ir.load_json(os.path.join(HOLD, "key.json"))["items"]:
        frames |= {it["a"].upper(), it["b"].upper()}
        pairs.add(pk(it["a"], it["b"]))
    return sets, frames, pairs


def excluded(k, sets, frames):
    return k.upper() in frames or v2.split(k)[0].upper() in sets


# ---------------------------------------------------------------- слой пары у исходного кадра

def asm_stratum(e):
    if e["scores"]["offset"][2] != 0:
        return "ASM_VERTICAL"
    if e["level"] == "STRONG":
        return "ASM_STRONG"
    return "ASM_SINGLE" if e["rule"].endswith("s") else "ASM_REPEAT_CAND"


def need_of(n):
    return max(asm.ASM_REPEAT, asm.ASM_CORE * n) if n >= asm.ASM_REPEAT else 1


def asm_negatives(A, a):
    """Трудные отрицательные ASM у кадра a: [(слой, b, сведения)]."""
    a = a.upper()
    out = []
    for slot in sorted({la for _t, _b, _g, _x, la in A.ctx.places.of(a)}):
        core = A.core(a, slot)
        by = defaultdict(list)
        for (o, s, kb) in core["members"]:
            by[kb].append((o, s))
        for kb, offs in sorted(by.items()):
            if kb == a:
                continue
            if len(offs) > 1:
                out.append(("ASM_NEG_PATTERN", kb, {"slot": slot, "offsets": [[list(o), s] for o, s in offs]}))
                continue
            o, sb = offs[0]
            if asm.judge(A, a, slot, kb, o, sb) is not None:
                continue
            back = asm.partners(A.core(kb, sb)).get(a)
            if back != (asm.neg(o), slot) or asm.MODEL[sb] != asm.MODEL[slot]:
                why = "не взаимно" if back != (asm.neg(o), slot) else "другая модель"
                out.append(("ASM_NEG_ONE_SIDED", kb, {"slot": slot, "offset": list(o), "slot_b": sb, "why": why}))
            else:
                out.append(("ASM_NEG_SINGLE_REJECT", kb, {"slot": slot, "offset": list(o), "slot_b": sb}))
        pl = A.places(a, slot)
        if len(pl) < asm.ASM_REPEAT:
            continue
        rec = Counter()
        for _t, _b, g, xyz in pl:
            for (o, s), kb in asm.instance(g, xyz, slot, a).items():
                if kb != a and abs(o[0]) + abs(o[1]) + abs(o[2]) == 1:
                    rec[(o, s, kb)] += 1
        need = need_of(len(pl))
        for (o, s, kb), c in sorted(rec.items()):
            if c < need and kb not in by:
                out.append(("ASM_NEG_NEAR", kb, {"slot": slot, "offset": list(o), "slot_b": s, "count": c,
                                                 "places": len(pl)}))
    return out


def ar_items(ctx, si, a):
    """Срабатывания и отрицательные AR1 у кадра a: [(слой, b, сведения)]."""
    a = a.upper()
    out = []
    A = ctx.rgba(a)
    if A is None or si.generic(a) > ar.AR_GENERIC:
        return out                                     # общий силуэт: passes отвергнет любую пару, слоя нет
    skip = {a} | set(ctx.ix.exact(a)) | set(ctx.ix.mirror(a))
    for b in ar.candidates(ctx, a):
        if b in skip or si.generic(b) > ar.AR_GENERIC:
            continue
        B = ctx.rgba(b)
        if B is None or B.shape != A.shape:
            continue
        sc = ar.scores(A, B)
        if sc["shift"] == [0, 0]:
            continue                                   # область R4, не AR1
        ok, why = ar.passes(sc, si.generic(a), si.generic(b))
        info = {"scores": sc, "why": why}
        if ok:
            e = ar.pair(ctx, si, a, b)
            info["level"] = e[0]["level"] if e else "?"
            out.append(("AR1_TRIGGER", b, info))
        elif any("общий" in w for w in why):
            continue
        elif len(why) == 1 and why[0].startswith("границ"):
            out.append(("AR1_BORDER_ONLY", b, info))
        elif any(w.startswith("силуэт") for w in why):
            out.append(("AR1_LOOKALIKE", b, info))
        else:
            out.append(("AR1_NEAR_MISS", b, info))
    return out


def placed_frames(ctx):
    keys = set()
    for t in sorted(ctx.world.terrains):
        _grids, occ = ctx.places.terrain(t)
        keys |= {k.upper() for k in occ}
    return keys


def pick(cands, need, used, setpairs):
    """Первый по приоритету слой, где ещё нужна пара: -> (слой, b, сведения) или None."""
    by = defaultdict(list)
    for st, b, info in cands:
        by[st].append((b, info))
    for st, _n, _f, _d in STRATA:
        if need.get(st, 0) <= 0:
            continue
        for b, info in sorted(by.get(st, []), key=lambda x: order(x[0], SEED + "|" + st)):
            if b in used:
                continue
            return st, b, info
    return None


def do_scan():
    check_freeze()
    if os.path.exists(p("key.json")):
        raise SystemExit("выборка уже есть: %s" % p("key.json"))
    import relation_holdout_v4 as hv
    ctx = hv.ctx_v3()
    si, A = v4.SetIndex(ctx), asm.Assembly(ctx)
    ex_sets, ex_frames, ex_pairs = exclusions()
    t0 = time.time()
    placed = placed_frames(ctx)
    mk = set(ctx.masks.pos)
    pool = sorted((k for k in placed if k in mk and not excluded(k, ex_sets, ex_frames)), key=order)
    print("кадров на картах %d, в пуле после исключений %d, %.0f с" % (len(placed), len(pool), time.time() - t0),
          flush=True)
    need = dict(QUOTA)
    used, setpairs = set(), defaultdict(set)
    items, popul, seen_pairs = [], Counter(), defaultdict(set)
    seen = 0
    for a in pool:
        if seen >= SCAN_SOURCES or all(v <= 0 for v in need.values()):
            break
        seen += 1
        cands = []
        for e in asm.discover(A, a):
            cands.append((asm_stratum(e), e["target"], {"level": e["level"], "rule": e["rule"],
                                                         "evidence": e["evidence"], "scores": e["scores"]}))
        cands += asm_negatives(A, a)
        cands += ar_items(ctx, si, a)
        ok = []
        for st, b, info in cands:
            if excluded(b, ex_sets, ex_frames) or pk(a, b) in ex_pairs:
                continue
            k = pk(a, b)
            if k not in seen_pairs[st]:
                seen_pairs[st].add(k)
                popul[st] += 1
            sp = frozenset((v2.split(a)[0], v2.split(b)[0]))
            if sp in setpairs[st]:
                continue
            ok.append((st, b, info))
        if a not in used:
            got = pick(ok, need, used, setpairs)
            if got:
                st, b, info = got
                items.append({"a": a, "b": b.upper(), "stratum": st, "info": info})
                need[st] -= 1
                used |= {a, b.upper()}
                setpairs[st].add(frozenset((v2.split(a)[0], v2.split(b)[0])))
        if seen % 250 == 0:
            print("просмотрено %d, %.0f с: %s" % (seen, time.time() - t0,
                                                  {s: QUOTA[s] - need[s] for s in QUOTA}), flush=True)
    items += known80(ctx, si, {pk(it["a"], it["b"]) for it in items})
    lst = sorted(items, key=lambda it: order(it["a"] + "|" + it["b"], SEED + "|q"))
    for n, it in enumerate(lst, 1):
        it["q"] = "C%03d" % n
        if order("swap" + it["q"])[0] in "01234567":
            it["a"], it["b"], it["swapped"] = it["b"], it["a"], True
    key = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "profile": PROFILE,
           "freeze_sha256": v2.file_sha(p("FREEZE.json")), "sources_seen": seen, "pool": len(pool),
           "population": dict(popul), "taken": dict(Counter(it["stratum"] for it in lst)),
           "short": {s: max(0, need[s]) for s in QUOTA}, "items": lst,
           "note": "ключ вне пакета: слой и причина отбора судье не показываются"}
    ir.dump_json(p("key.json"), key)
    print("выборка: %d пар %s; просмотрено %d из %d; недобор %s" % (
        len(lst), key["taken"], seen, len(pool), {s: v for s, v in key["short"].items() if v}))


def known80(ctx, si, have):
    """Срабатывания AR1 и ASM на 80 кадрах вне пула V4 (found5.json) - все, по одной строке на пару."""
    f5 = ir.load_json(os.path.join(V5, "found5.json"))
    pool = {pk(it["a"], it["b"]) for it in ir.load_json(os.path.join(HOLD, "key.json"))["items"]}
    out, seen = [], set(have)
    for e in f5["edges"]:
        k = pk(e["source"], e["target"])
        if k in pool or k in seen:
            continue
        seen.add(k)
        st = "KNOWN80_AR1" if e["detector"] == ar.DETECTOR else "KNOWN80_ASM"
        info = {"level": e["level"], "rule": e["rule"], "evidence": e["evidence"], "scores": e.get("scores")}
        out.append({"a": e["source"].upper(), "b": e["target"].upper(), "stratum": st, "info": info})
    return out


# ---------------------------------------------------------------- пакет, проверка, эталон

def do_pack():
    import relation_truth_v2 as tv
    check_freeze()
    key = ir.load_json(p("key.json"))
    if os.path.exists(p("pack.lock.json")):
        raise SystemExit("пакет уже собран: %s" % p("pack.lock.json"))
    n = len(key["items"])
    tv.write_pack(OUT, [{"q": it["q"], "a": it["a"], "b": it["b"]} for it in key["items"]],
                  2 * math.ceil(n / BATCH_PAIRS), SEED, judges_per_item=2)


def do_check():
    import relation_truth_v2 as tv
    lock = ir.load_json(p("pack.lock.json"))
    res, bad = tv.read_by_judge(OUT, lock)
    done, todo = [], []
    for i, qs in enumerate(lock["batches"]):
        fn = p("answers", "judge_%d.tsv" % (i + 1))
        if not os.path.exists(fn):
            todo.append(i + 1)
            continue
        miss = [q for q in qs if not any(x["judge"] == i + 1 and x["answered"] for x in res[q])]
        done.append(i + 1)
        if miss:
            print("judge_%d: без ответа %d: %s" % (i + 1, len(miss), miss[:5]))
    print("ошибки формата:", bad[:10])
    print("сдано %d из %d; не сдано: %s" % (len(done), len(lock["batches"]), todo))
    return not bad and not todo


def do_lockref():
    import relation_truth_v2 as tv
    import routing_model_v8 as v8
    check_freeze()
    if os.path.exists(p("reference.lock.json")):
        raise SystemExit("эталон уже заморожен")
    key, lock = ir.load_json(p("key.json")), ir.load_json(p("pack.lock.json"))
    js, bad = tv.read_by_judge(OUT, lock)
    ctx = v3.Ctx(index=v2.load_index(v2.OUT))
    mcd = v8.Mcd(ctx.world)
    rows, missing = [], []
    for it in key["items"]:
        got = [x for x in js.get(it["q"], []) if x["answered"]]
        if len(got) < 2:
            missing.append(it["q"])
            continue
        au = tv.authority(ctx, mcd, it["a"], it["b"])
        ex, closed, opn = tv.combine_pair(got[0]["taken"], got[1]["taken"], bool(au))
        rows.append({"q": it["q"], "a": it["a"], "b": it["b"], "existence": ex, "closed": sorted(closed),
                     "open": sorted(opn), "authority": au, "judge1": sorted(got[0]["taken"]),
                     "judge2": sorted(got[1]["taken"]), "raw1": got[0]["raw"], "raw2": got[1]["raw"]})
    if bad or missing:
        raise SystemExit("ответы неполны или с ошибками: %s; без двух ответов: %s" % (bad[:10], missing[:10]))
    ir.dump_json(p("truth.json"), {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "pairs": rows})
    ir.dump_json(p("reference.lock.json"), {"created": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                            "key_sha256": v2.file_sha(p("key.json")),
                                            "pack_sha256": lock["pack_sha256"],
                                            "truth_sha256": v2.file_sha(p("truth.json"))})
    print("эталон заморожен: пар %d, %s" % (len(rows), dict(Counter(r["existence"] for r in rows))))


# ---------------------------------------------------------------- подсчёт

def subtype(r, labels):
    """Подтип по самому ярлыку: у обоих судей - yes, ни у одного - no, у одного - OPEN; без связи - no."""
    if r["existence"] == "NONE":
        return "no"
    if r["existence"] != "RELATED":
        return "OPEN"
    a1, a2 = bool(set(r["judge1"]) & labels), bool(set(r["judge2"]) & labels)
    return "OPEN" if a1 != a2 else ("yes" if a1 else "no")


def prec(rows, field, good):
    """-> (точность, закрытый знаменатель, верно, открыто)."""
    closed = [r for r in rows if r[field] != "OPEN"]
    ok = [r for r in closed if r[field] == good]
    return v2.rate(len(ok), len(closed)), len(closed), len(ok), len(rows) - len(closed)


def weighted(rows, field, good, popul, taken):
    """Точность, взвешенная по численности слоёв: вес пары слоя = численность слоя / взято в слой."""
    num = den = 0.0
    for r in rows:
        if r[field] == "OPEN":
            continue
        w = popul.get(r["stratum"], 0) / max(taken.get(r["stratum"], 1), 1)
        den += w
        num += w * (r[field] == good)
    return round(num / den, 4) if den else None


def verdict(v, n):
    if v is None or not n:
        return "NO_DATA"
    if n < N_MIN:
        return "INSUFFICIENT_SAMPLE"
    return "PASS" if v >= GATE else "FAIL"


def border_bin(x):
    for lo in reversed(BORDER_BINS):
        if x >= lo:
            return ">=%.1f" % lo
    return "<%.1f" % BORDER_BINS[0]


def enrich(key, truth):
    T = {r["q"]: r for r in truth["pairs"]}
    rows = []
    for it in key["items"]:
        r = dict(T[it["q"]], stratum=it["stratum"], family=FAMILY[it["stratum"]], info=it["info"])
        r["exist"] = {"RELATED": "yes", "NONE": "no"}.get(r["existence"], "OPEN")
        r["composite"] = subtype(r, {"COMPOSITE"})
        r["derived"] = subtype(r, DERIVED_SUB)
        lab = set(r["closed"]) - {"NONE"}
        r["attachment_only"] = r["existence"] == "RELATED" and bool(lab) and lab <= {
            "ATTACHMENT_CANDIDATE", "STRUCTURAL_COUNTERPART", "MODULAR_SECTION"}
        r["level"] = (it["info"] or {}).get("level")
        r["vertical"] = it["stratum"] == "ASM_VERTICAL" or (
            it["stratum"] == "KNOWN80_ASM" and ((it["info"].get("scores") or {}).get("offset") or [0, 0, 0])[2] != 0)
        rows.append(r)
    return rows


def readiness(rows, popul, taken):
    cand = [r for r in rows if r["family"] == "asm_pos" and r["level"] == "CANDIDATE"]
    strong = [r for r in rows if r["family"] == "asm_pos" and r["level"] == "STRONG"]
    arp = [r for r in rows if r["stratum"] == "AR1_TRIGGER"]
    res = {}
    v, n, ok, op = prec(cand, "exist", "yes")
    res["asm_candidate_existence_precision"] = {"value": v, "n": n, "ok": ok, "open": op,
                                                "weighted": weighted(cand, "exist", "yes", popul, taken),
                                                "verdict": verdict(v, n), "need": GATE,
                                                "attachment_only": sum(r["attachment_only"] for r in cand)}
    v, n, ok, op = prec(strong, "composite", "yes")
    res["asm_strong_typed_precision"] = {"value": v, "n": n, "ok": ok, "open": op,
                                         "weighted": weighted(strong, "composite", "yes", popul, taken),
                                         "verdict": verdict(v, n), "need": GATE}
    for name, f, good in (("ar1_existence_precision", "exist", "yes"), ("ar1_derived_precision", "derived", "yes")):
        v, n, ok, op = prec(arp, f, good)
        res[name] = {"value": v, "n": n, "ok": ok, "open": op, "verdict": "DIAGNOSTIC (%s)" % verdict(v, n)}
    gates = [res["asm_candidate_existence_precision"]["verdict"], res["asm_strong_typed_precision"]["verdict"]]
    res["verdict"] = "FAIL" if "FAIL" in gates else ("PASS" if all(g == "PASS" for g in gates) else "INCONCLUSIVE")
    return res


def by_stratum(rows):
    out = {}
    for st in [s for s, *_ in STRATA] + ["KNOWN80_AR1", "KNOWN80_ASM"]:
        rs = [r for r in rows if r["stratum"] == st]
        if not rs:
            continue
        out[st] = {"n": len(rs), "existence": dict(Counter(r["exist"] for r in rs)),
                   "composite": dict(Counter(r["composite"] for r in rs)),
                   "derived": dict(Counter(r["derived"] for r in rs)),
                   "attachment_only": sum(r["attachment_only"] for r in rs),
                   "levels": dict(Counter(r["level"] or "-" for r in rs))}
    return out


def ar1_bins(rows):
    """Корзины границ у AR1-слоёв: подтип производного yes / no / OPEN."""
    t = defaultdict(Counter)
    for r in rows:
        if r["family"] not in ("ar_pos", "ar_neg") and r["stratum"] != "KNOWN80_AR1":
            continue
        sc = (r["info"] or {}).get("scores") or {}
        if "topology" not in sc:
            continue
        t[border_bin(sc["topology"])][r["derived"]] += 1
    return {k: dict(v) for k, v in sorted(t.items())}


def vertical(rows):
    out = []
    for r in rows:
        if not r["vertical"]:
            continue
        sc = (r["info"] or {}).get("scores") or {}
        out.append({"q": r["q"], "a": r["a"], "b": r["b"], "level": r["level"], "rule": r["info"].get("rule"),
                    "offset": sc.get("offset"), "struct": sc.get("struct"), "order": sc.get("order"),
                    "mcd": sc.get("mcd"), "single": sc.get("single"), "existence": r["existence"],
                    "composite": r["composite"], "closed": r["closed"]})
    return out


def do_report():
    check_freeze()
    lk = ir.load_json(p("reference.lock.json"))
    if v2.file_sha(p("truth.json")) != lk["truth_sha256"] or v2.file_sha(p("key.json")) != lk["key_sha256"]:
        raise SystemExit("эталон или ключ изменены после заморозки")
    key, truth = ir.load_json(p("key.json")), ir.load_json(p("truth.json"))
    rows = enrich(key, truth)
    popul, taken = key["population"], key["taken"]
    res = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "profile": PROFILE,
           "freeze_sha256": v2.file_sha(p("FREEZE.json")), "truth_sha256": lk["truth_sha256"],
           "readiness": readiness(rows, popul, taken), "strata": by_stratum(rows), "population": popul,
           "taken": taken, "short": key["short"], "ar1_border_bins": ar1_bins(rows), "vertical": vertical(rows),
           "judge_agreement_existence": v2.rate(sum(tx.existence_class(set(r["judge1"])) ==
                                                    tx.existence_class(set(r["judge2"])) for r in rows), len(rows)),
           "rows": [{k: r[k] for k in ("q", "a", "b", "stratum", "level", "existence", "closed", "open", "judge1",
                                        "judge2", "composite", "derived", "attachment_only")} for r in rows]}
    ir.dump_json(p("report.json"), res)
    write_md(res, rows)
    print("готовность: %s; кандидаты ASM %s, STRONG ASM %s" % (
        res["readiness"]["verdict"], res["readiness"]["asm_candidate_existence_precision"]["verdict"],
        res["readiness"]["asm_strong_typed_precision"]["verdict"]))


def f3(x):
    return "-" if x is None else "%.3f" % x


def write_md(res, rows):
    R = res["readiness"]
    L = ["# V5_COMPONENT_VALIDATION_V1 — слепая проверка ASSEMBLY и AR1", "",
         "Решение: специалист 02.10 (docs/DECISIONS.md). Заморозка до отбора: FREEZE.json %s. Два независимых судьи "
         "на пару, слой пары судье не показан. Согласие судей по существованию %s." % (
             res["freeze_sha256"][:12], f3(res["judge_agreement_existence"])), "",
         "## Готовность", "",
         "| проверка | точность | взвешенная | закрыто | верно | OPEN | нужно | итог |", "|---|---|---|---|---|---|---|---|"]
    for k in ("asm_candidate_existence_precision", "asm_strong_typed_precision", "ar1_existence_precision",
              "ar1_derived_precision"):
        x = R[k]
        L.append("| %s | %s | %s | %d | %d | %d | %s | %s |" % (k, f3(x["value"]), f3(x.get("weighted")), x["n"],
                                                             x["ok"], x["open"], x.get("need", "-"), x["verdict"]))
    L += ["", "Итог готовности ASSEMBLY: **%s**. Кандидатов ASM, связанных только примыканием (ATTACHMENT / "
              "STRUCTURAL / MODULAR, без составного): %d." % (R["verdict"],
                                                              R["asm_candidate_existence_precision"]["attachment_only"]),
          "", "## По слоям", "",
          "| слой | взято | численность | существование | составной | производный | только примыкание | уровни |",
          "|---|---|---|---|---|---|---|---|"]
    for st, x in res["strata"].items():
        L.append("| %s | %d | %s | %s | %s | %s | %d | %s |" % (st, x["n"], res["population"].get(st, "-"),
                                                             x["existence"], x["composite"], x["derived"],
                                                             x["attachment_only"], x["levels"]))
    L += ["", "## AR1: корзины границ (подтип производного yes / no / OPEN)", ""]
    for b, x in res["ar1_border_bins"].items():
        L.append("- границ %s: %s" % (b, x))
    L += ["", "## Вертикальные стопки ASM", "", "| q | A | B | уровень | сдвиг | конструкция | порядок | MCD | "
          "одно место | существование | составной | закрыто |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for v in res["vertical"]:
        L.append("| %s | %s | %s | %s %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            v["q"], v["a"], v["b"], v["rule"], v["level"], v["offset"], v["struct"], v["order"], v["mcd"],
            v["single"], v["existence"], v["composite"], "/".join(v["closed"]) or "-"))
    L += ["", "## Все пары", "", "| q | слой | A | B | уровень | судья 1 | судья 2 | существование | составной | "
          "производный | закрыто |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: (r["stratum"], r["q"])):
        L.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r["q"], r["stratum"], r["a"], r["b"], r["level"] or "-", "/".join(r["judge1"]) or "-",
            "/".join(r["judge2"]) or "-", r["existence"], r["composite"], r["derived"], "/".join(r["closed"]) or "-"))
    L += ["", "VERIFIED ставит только человек."]
    with open(p("report.md"), "w", encoding=ENC, newline="\n") as f:
        f.write("\n".join(L) + "\n")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["freeze", "scan", "pack", "check", "lockref", "report"])
    a = ap.parse_args()
    {"freeze": do_freeze, "scan": do_scan, "pack": do_pack, "check": do_check, "lockref": do_lockref,
     "report": do_report}[a.cmd]()


if __name__ == "__main__":
    main()
