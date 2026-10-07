"""DERIVE_RECOLOR_SAFE_ACCEPTANCE_V1 - слепое подтверждение ворот пригодности пары для вывода перекраски BASE.

Решение: специалист 03.10, передал Vitali в чате (DERIVE_RECOLOR_SAFE_V1_PREP, затем freeze). BASE_V1.1 = FINAL FAIL
(machine PASS, human 42/2) и остаётся таким; universal automatic BASE - REJECTED; алгоритм BASE (derive_recolor_base_v1.py)
- RETAIN; диагностика как глобальные FAIL-ворота - REJECTED, как ворота КАЖДОЙ пары - APPROVED.

Production-правило SAFE_V1 (только REAL - HD основы, который реально пойдёт в мод; синтетика в пригодности не участвует):
  HD основы есть, Stage A не отказал, STRUCT = 0, unintended_local_artifacts == 0, wrong_palette_mapping == 0
      -> SAFE_ELIGIBLE (DERIVE_RECOLOR_SAFE);
  иначе -> SAFE_REJECTED (DERIVE_RECOLOR_UNSAFE -> REVIEW / DIRECT_RENDER);
  HD основы нет -> ELIGIBILITY_PENDING_REAL (автоматический вывод запрещён, это не провал).
  STRUCT = 0 и отсутствие отказа - условия самого вывода BASE (контракт BASE_V1), не новая мера.

Подтверждение: 50 нетронутых пар перекраски в порядке, замороженном до прогона (sha1('safe_v1:<base>><member>'),
пара один раз, картинка один раз, пара наборов один раз, набор основы и набор члена не больше двух раз). Первая партия
1-30; если пригодных < 10 - партия 31-40; если всё ещё < 10 - 41-50; пригодных >= 10 - расширения нет. После 50 меньше 10
-> INSUFFICIENT_SAMPLE. Human review: все пригодные из прочитанных партий + 5 случайных отклонённых (seed в spec),
вперемешку, слепо - проверяющий не знает, какие карточки контрольные и сколько нужно пригодных.
Жёсткие ворота: automatic_recolor_precision = 1.000 (ни одного пригодного с FAIL), пригодных >= 10. UNSURE - не PASS.
Контрольные отклонённые - только диагностика (консервативность), coverage - не ворота.

Нетронутая пара: ни основа, ни член, ни их картинки (хэш) не упоминаются ни в одной папке probes/derive-recolor-* и ни в
одном tools/hdart/derive_recolor*.py (кроме этого модуля и его папки) - то же узкое правило, что в V1.1, теперь с
папками V1.1 и SAFE_V1_PREP.

Только numpy, без модели и видеокарты. Команды из корня репозитория:
    py -3.13 tools/hdart/derive_recolor_safe_acceptance_v1.py preview|spec|confirm|cards|final|report|check
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

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import derive_recolor_acceptance_v2 as V2  # noqa: E402
import derive_recolor_base_acceptance_v1 as AC  # noqa: E402  (заморожен, только чтение)

A3, M, B, D3 = AC.A3, AC.M, AC.B, AC.D3
ENC = "utf-8-sig"
ROOT = AC.ROOT
PROFILE = "DERIVE_RECOLOR_SAFE_ACCEPTANCE_V1"
PROBES = os.path.join(ROOT, "art", "objects", "generation", "probes")
OUT = os.path.join(PROBES, "derive-recolor-safe-v1-acceptance")
CARDS = os.path.join(OUT, "human_cards")
SELF = "tools/hdart/derive_recolor_safe_acceptance_v1.py"
V11_SELF = "tools/hdart/derive_recolor_base_acceptance_v11.py"
V11_OUT = os.path.join(PROBES, "derive-recolor-base-v11-acceptance")
POOL = AC.DEV + "/v32dev_pool.tsv"
HD_PATH = "user/mods/hd/hd/TERRAIN/%s.PCK/%s.png"
SET_FILE = "candidates.json"
SALT = "safe_v1:"
BATCHES = (30, 40, 50)
MIN_ELIGIBLE = 10
CONTROL_N = 5
CONTROL_SEED = 20261006
CARD_SEED = 20261005
DECISION = ("специалист 03.10, передал Vitali в чате: BASE_V1.1 FINAL FAIL unchanged; universal automatic BASE REJECTED; "
            "BASE algorithm RETAIN; diagnostics as global FAIL gates REJECTED, as per-pair safety gate APPROVED; "
            "production eligibility by REAL only (artifact_count == 0 and wrong_palette_mapping == 0), synthetic = "
            "diagnostic; no REAL HD -> ELIGIBILITY_PENDING_REAL, automatic derive forbidden; blind confirmation 30 "
            "untouched pairs, pre-frozen expansion 30 -> 40 -> 50 while eligible < 10, order of all 50 frozen before "
            "review; human review = all eligible + 5 random rejected controls (seed in spec), reviewer blind to which "
            "are needed; hard: automatic_recolor_precision = 1.000 and eligible >= 10; any eligible FAIL -> SAFE_V1 "
            "FAIL; < 10 after 50 -> INSUFFICIENT_SAMPLE; controls and coverage diagnostic only; PASS -> SAFE_V1 "
            "eligible for VERIFIED (set by a human), then R3.3 with DIRECT_RENDER, EXACT_COPY, DERIVE_RECOLOR_SAFE")
BODY = ("profile", "decision", "implementation", "rule", "selection", "candidates", "expansion", "hard", "human",
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


def hd_file(key):
    s, f = key.split(":")
    return rel(HD_PATH % (s, f))


# ---------- правило пригодности (production) ----------

def eligibility(row):
    """SAFE_ELIGIBLE / SAFE_REJECTED / ELIGIBILITY_PENDING_REAL по строке REAL и причины отказа."""
    if row["status"] == "NO_REAL_HD":
        return "ELIGIBILITY_PENDING_REAL", ["нет HD основы"]
    why = []
    if row["status"] != "DERIVED":
        why.append("Stage A отказал")
    else:
        if row["struct"]:
            why.append("STRUCT %d" % row["struct"])
        if row["art"]:
            why.append("пятен %d" % row["art"])
        if row["map"]:
            why.append("mapping %d" % row["map"])
    return ("SAFE_REJECTED" if why else "SAFE_ELIGIBLE"), why


def eval_real(pair, keep_img=False):
    """Только форма REAL (как eval_pair V1): вывод BASE дважды, ворота V3 по HD основы в ориентации цепочки.
    Плюс контроль мощности: HD основы, поданный как вывод, - сколько классов пятен и mapping он даёт."""
    row = {"case": "%s>%s/REAL" % (pair["base"], pair["member"]), "pair": [pair["base"], pair["member"]],
           "rank": pair["rank"], "measure_invalid": []}
    if not os.path.exists(hd_file(pair["base"])):
        row["status"] = "NO_REAL_HD"
        row["eligibility"], row["why"] = eligibility(row)
        return row
    form, ob, ot, hd, _truth = next(M.forms(dict(pair, category="general")))
    assert form == "REAL"
    der, ch = B.derive(hd, ob, ot, "recolor")
    der2, ch2 = B.derive(hd, ob, ot, "recolor")
    row["deterministic"] = bool(((der is None and der2 is None) or (der is not None and der2 is not None
                                                                      and (der == der2).all())) and ch == ch2)
    row["chain_ok"] = AC.chain_ok(ch)
    if not row["deterministic"]:
        row["measure_invalid"].append("вывод не детерминирован")
    if not row["chain_ok"]:
        row["measure_invalid"].append("цепочка не BASE")
    if der is None:
        row.update(status="REFUSED", struct=1, geometry=None)
    else:
        g = ch["geometry_transform"]
        hdo, obo = D3.geo(hd, g), D3.geo(ob, g)
        gt, info = A3.gates3(der, hdo, obo, ot)
        gt2, _ = A3.gates3(der, hdo, obo, ot)
        if gt != gt2:
            row["measure_invalid"].append("мера не детерминирована")
        pc, _ = A3.gates3(hdo, hdo, obo, ot)
        row.update(status="DERIVED", geometry=g, struct=int(sum(gt[k] for k in AC.STRUCT)),
                   struct_list={k: gt[k] for k in AC.STRUCT if gt[k]}, art=int(gt["unintended_local_artifacts"]),
                   map=int(gt["wrong_palette_mapping"]),
                   ctrl_hd_as_output={"art": int(pc["unintended_local_artifacts"]),
                                      "map": int(pc["wrong_palette_mapping"])})
        row.update(AC.fidelity(der, hdo))
        if keep_img:
            row["_img"] = (der, hdo, ot)
    row["eligibility"], row["why"] = eligibility(row)
    return row


# ---------- отбор 50 кандидатов ----------

def touched():
    """Все ключи SET:N в папках проб derive-recolor-* и в tools/hdart/derive_recolor*.py (кроме своих)."""
    rx = re.compile(r"\b([A-Z][A-Z0-9_]*:\d+)\b")
    pool = os.path.abspath(rel(POOL))
    own_dir, own_py = os.path.abspath(OUT), os.path.abspath(rel(SELF))
    files = sorted(f for d in glob.glob(os.path.join(PROBES, "derive-recolor*"))
                   for f in glob.glob(os.path.join(d, "**", "*"), recursive=True)
                   if os.path.isfile(f) and f.rsplit(".", 1)[-1] in ("json", "md", "txt", "tsv", "py", "log")
                   and os.path.abspath(f) != pool and not os.path.abspath(f).startswith(own_dir))
    files += sorted(f for f in glob.glob(os.path.join(HERE, "derive_recolor*.py")) if os.path.abspath(f) != own_py)
    keys = set()
    for f in files:
        keys |= set(rx.findall(open(f, encoding=ENC, errors="replace").read()))
    return keys, files


def order(r):
    return hashlib.sha1((SALT + "%s>%s" % (r["base"], r["member"])).encode()).hexdigest()


def select():
    rows = list(csv.DictReader(open(rel(POOL), encoding=ENC), delimiter="\t"))
    keys, files = touched()
    h = {}
    for r in rows:
        h[r["base"]], h[r["member"]] = r["base_hash"], r["member_hash"]
    thash = {h[k] for k in keys if k in h}
    free = [r for r in rows if r["base"] not in keys and r["member"] not in keys
            and r["base_hash"] not in thash and r["member_hash"] not in thash]
    with_hd = [r for r in free if os.path.exists(hd_file(r["base"]))]
    used_img, per_base, per_mem, per_pair, taken, out = set(), {}, {}, set(), set(), []
    for r in sorted(free, key=order):
        if len(out) >= BATCHES[-1]:
            break
        bs, ms = r["base"].split(":")[0], r["member"].split(":")[0]
        und = tuple(sorted((r["base"], r["member"])))
        if und in taken or r["base_hash"] in used_img or r["member_hash"] in used_img:
            continue
        if (bs, ms) in per_pair or per_base.get(bs, 0) >= 2 or per_mem.get(ms, 0) >= 2:
            continue
        out.append({"rank": len(out) + 1, "base": r["base"], "member": r["member"], "order": order(r)[:12],
                    "batch": 1 + sum(len(out) >= b for b in BATCHES[:-1]),
                    "features": {k: r[k] for k in ("geometry", "support", "n_base_colors", "grad", "y_base",
                                                   "y_member", "changed", "func", "multi_px", "div90",
                                                   "dither_frac")}})
        taken.add(und)
        used_img |= {r["base_hash"], r["member_hash"]}
        per_pair.add((bs, ms))
        per_base[bs] = per_base.get(bs, 0) + 1
        per_mem[ms] = per_mem.get(ms, 0) + 1
    info = {"pool": {"file": POOL, "sha256": fsha(POOL), "rows": len(rows)},
            "touched": {"files": len(files), "keys": len(keys), "keys_in_pool": sum(k in h for k in keys),
                        "images": len(thash),
                        "keys_sha256": hashlib.sha256("\n".join(sorted(keys)).encode()).hexdigest(),
                        "includes": ["derive-recolor-base-v11-acceptance", "derive-recolor-safe-v1-prep"]},
            "untouched_rows": len(free), "untouched_with_real_hd": len(with_hd),
            "candidates_without_real_hd": sum(not os.path.exists(hd_file(c["base"])) for c in out)}
    return out, info


def do_preview():
    if os.path.exists(os.path.join(OUT, "spec.json")):
        raise SystemExit("spec уже заморожен")
    out, info = select()
    print("пул %d строк; тронуто ключей %d (в пуле %d, картинок %d) из %d файлов; нетронутых строк %d, из них с HD "
          "основы %d; кандидатов %d (без HD основы %d)" % (
              info["pool"]["rows"], info["touched"]["keys"], info["touched"]["keys_in_pool"],
              info["touched"]["images"], info["touched"]["files"], info["untouched_rows"],
              info["untouched_with_real_hd"], len(out), info["candidates_without_real_hd"]))
    have = set(info["touched"]["includes"])
    seen = {os.path.basename(os.path.dirname(f)) for f in touched()[1]} | {
        os.path.basename(os.path.dirname(os.path.dirname(f))) for f in touched()[1]}
    print("папки V1.1 и SAFE_PREP в тронутых:", have <= seen)


# ---------- spec ----------

def spec_body(info, blob, n):
    return {
        "profile": PROFILE, "decision": DECISION,
        "implementation": {"module": AC.IMPL, "sha256": fsha(AC.IMPL), "version": B.VERSION,
                           "acceptance_helpers": {"module": AC.SELF, "sha256": fsha(AC.SELF)},
                           "note": "BASE output = BASE_V1 / V1.1 (same module, same sha); gates = A3.gates3 as V1"},
        "rule": {
            "SAFE_ELIGIBLE": "REAL HD available AND Stage A not refused AND STRUCT == 0 AND "
                             "unintended_local_artifacts == 0 AND wrong_palette_mapping == 0 -> DERIVE_RECOLOR_SAFE",
            "SAFE_REJECTED": "otherwise -> DERIVE_RECOLOR_UNSAFE -> REVIEW / DIRECT_RENDER",
            "ELIGIBILITY_PENDING_REAL": "no REAL HD base -> automatic derive forbidden, not a failure",
            "form": "REAL only; synthetic forms are diagnostic and do not enter production eligibility",
            "struct_note": "Stage A refusal and STRUCT > 0 are conditions of the BASE derivation itself (BASE_V1 "
                           "contract), not a new diagnostic",
            "measure_controls": "per pair: derive twice byte-identical, gates twice equal, chain BASE; per run: base "
                                "HD fed as output flags >= 1 class (art or map) on at least one pair (power). Not "
                                "satisfied -> INVALID_MEASURE"},
        "selection": dict(info, rule=(
            "untouched pool rows (base, member and their images not mentioned in probes/derive-recolor-* or "
            "tools/hdart/derive_recolor*.py, except this module and its folder); order sha1('%s<base>><member>'); "
            "pair once (undirected), image once, (base set, member set) once, base set and member set at most "
            "twice; first %d; no category quotas (production-representative)" % (SALT, BATCHES[-1]))),
        "candidates": {"file": SET_FILE, "sha256": hashlib.sha256(blob).hexdigest(), "count": n},
        "expansion": {"batches": list(BATCHES), "min_eligible": MIN_ELIGIBLE,
                      "rule": "evaluate ranks 1-30; if eligible < 10 evaluate 31-40; if still < 10 evaluate 41-50; "
                              "stop as soon as eligible >= 10 after a batch; eligibility computed automatically "
                              "before any card is made"},
        "hard": {"PRECISION": "automatic_recolor_precision = 1.000: no SAFE_ELIGIBLE card with human FAIL",
                 "SAMPLE": "SAFE_ELIGIBLE >= 10 among evaluated pairs, else INSUFFICIENT_SAMPLE",
                 "UNSURE": "UNSURE on an eligible card is not PASS -> back to specialist",
                 "not_gates": "coverage (eligible / evaluated REAL), rejected controls"},
        "human": {"cards": "all SAFE_ELIGIBLE of evaluated batches + %d SAFE_REJECTED drawn by random.Random(%d)."
                           "sample over evaluated rejected in rank order (all if fewer)" % (CONTROL_N, CONTROL_SEED),
                  "card": "member original x4 | base HD | BASE recolor (AC.card_image, scale %d), shuffled by seed "
                          "%d, blind: key outside the reviewer folder, controls not marked" % (AC.CARD_SCALE,
                                                                                            CARD_SEED),
                  "question": AC.QUESTION, "answers": list(AC.ANSWERS),
                  "when": "cards only after the machine run; the list is not changed after images are seen"},
        "final_rule": ("SAFE_V1 eligible for VERIFIED = machine run valid + eligible >= 10 + every eligible card PASS. "
                       "Any eligible FAIL -> SAFE_V1 FAIL; eligible UNSURE -> not PASS, back to specialist; < 10 "
                       "eligible after 50 -> INSUFFICIENT_SAMPLE. Controls: rejected PASS / FAIL reported only. "
                       "VERIFIED is set by a human. BASE_V1.1 stays FINAL FAIL."),
        "sequence": ["preview (counts only)", "spec + candidates (once)", "confirm (once)", "cards", "human review",
                     "final"],
        "forbidden": ["BASE_V1 / V1.1 spec, folders, results, modules unchanged", "BASE renderer/output unchanged",
                      "no exceptions for LIGHTNIN:9, MUJUNGLE:52, XB3BITZ1_MAG:14", "MAP_DE 10 and C1 unchanged",
                      "V7 and families unchanged", "857/1030 and 173 refusals untouched", "no model, no GPU",
                      "nothing into production pack"],
    }


def do_spec():
    p = os.path.join(OUT, "spec.json")
    if os.path.exists(p) or os.path.exists(os.path.join(OUT, SET_FILE)):
        raise SystemExit("spec или кандидаты уже записаны - они неизменяемы")
    out, info = select()
    if len(out) < BATCHES[-1]:
        raise SystemExit("нетронутых кандидатов %d, нужно %d - заморозка остановлена" % (len(out), BATCHES[-1]))
    blob = json.dumps(out, ensure_ascii=False, sort_keys=True).encode()
    body = spec_body(info, blob, len(out))
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, SET_FILE), "wb") as f:
        f.write(blob)
    body["sha256"] = V2.jsha({k: body[k] for k in BODY})
    body["frozen_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    body["self_sha256"] = fsha(SELF)
    A3.save_json(p, body)
    print("spec SAFE_V1 заморожен: sha %s; кандидатов %d (без HD основы %d); ключи - %s" % (
        body["sha256"][:12], len(out), info["candidates_without_real_hd"], SET_FILE))


def load_spec():
    sp = load("spec.json")
    if V2.jsha({k: sp[k] for k in BODY}) != sp["sha256"]:
        raise SystemExit("spec SAFE_V1 изменён после заморозки")
    if fsha(SELF) != sp["self_sha256"]:
        raise SystemExit("приёмка SAFE_V1 изменилась после заморозки")
    if fsha(AC.IMPL) != sp["implementation"]["sha256"] or \
            fsha(AC.SELF) != sp["implementation"]["acceptance_helpers"]["sha256"]:
        raise SystemExit("код BASE или помощники V1 изменились")
    blob = open(os.path.join(OUT, SET_FILE), "rb").read()
    if hashlib.sha256(blob).hexdigest() != sp["candidates"]["sha256"]:
        raise SystemExit("кандидаты изменены")
    if fsha(POOL) != sp["selection"]["pool"]["sha256"]:
        raise SystemExit("пул изменился")
    return sp, json.loads(blob.decode("utf-8"))


# ---------- прогон ----------

def do_confirm():
    sp, cand = load_spec()
    if os.path.exists(os.path.join(OUT, "confirmation.json")):
        raise SystemExit("confirmation.json уже есть - прогон один раз")
    AC.OUT = OUT   # картинки - в папку SAFE_V1 (V1 не пишется)
    rows, done = [], 0
    for b in BATCHES:
        for pair in cand[done:b]:
            r = eval_real(pair, keep_img=True)
            if "_img" in r:
                der, hdo, ot = r.pop("_img")
                stem = r["case"].replace(":", "_").replace(">", "__").replace("/", "_")
                AC.save_png(der, "confirm", stem + "_base.png")
                AC.save_png(hdo, "confirm", stem + "_hd.png")
                AC.save_png(ot, "confirm", stem + "_member.png")
                r["stem"] = stem
            r["batch"] = pair["batch"]
            rows.append(r)
            print("%2d %-46s %-9s S%s art %s map %s -> %s" % (r["rank"], r["case"], r["status"], r.get("struct", "-"),
                                                              r.get("art", "-"), r.get("map", "-"),
                                                              r["eligibility"]), flush=True)
        done = b
        n_el = sum(r["eligibility"] == "SAFE_ELIGIBLE" for r in rows)
        print("-- после %d: пригодных %d" % (b, n_el), flush=True)
        if n_el >= MIN_ELIGIBLE:
            break
    inv = [(r["case"], r["measure_invalid"]) for r in rows if r["measure_invalid"]]
    power = sum(1 for r in rows if r["status"] == "DERIVED" and
                (r["ctrl_hd_as_output"]["art"] or r["ctrl_hd_as_output"]["map"]))
    if power == 0:
        inv.append(("прогон", ["контроль мощности: HD основы как вывод не дал ни одного класса"]))
    el = [r for r in rows if r["eligibility"] == "SAFE_ELIGIBLE"]
    rej = [r for r in rows if r["eligibility"] == "SAFE_REJECTED"]
    pend = [r for r in rows if r["eligibility"] == "ELIGIBILITY_PENDING_REAL"]
    real = len(rows) - len(pend)
    verdict = "INVALID_MEASURE" if inv else ("READY_FOR_HUMAN" if len(el) >= MIN_ELIGIBLE else "INSUFFICIENT_SAMPLE")
    res = {"profile": PROFILE, "spec_sha256": sp["sha256"], "run_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "evaluated": len(rows), "batches_used": sorted({r["batch"] for r in rows}), "eligible": len(el),
           "rejected": len(rej), "pending_real": len(pend), "coverage": round(len(el) / real, 3) if real else None,
           "ctrl_power_pairs": power, "measure_invalid": inv, "verdict": verdict, "rows": rows}
    dump("confirmation.json", res)
    write_confirmation_md(res)
    print("SAFE_V1 прогон: %s; прочитано %d (партии %s), пригодных %d, отклонено %d, без HD %d, coverage %s" % (
        verdict, len(rows), res["batches_used"], len(el), len(rej), len(pend), res["coverage"]))


def write_confirmation_md(res):
    L = ["# DERIVE_RECOLOR_SAFE_ACCEPTANCE_V1 - прогон (один раз)", "",
         "Прогон %s, spec `%s`." % (res["run_at"], res["spec_sha256"][:12]), "",
         "**%s**: прочитано %d пар (партии %s), SAFE_ELIGIBLE %d, SAFE_REJECTED %d, ELIGIBILITY_PENDING_REAL %d, "
         "coverage %s. Контроль мощности: HD основы как вывод отмечен на %d парах." % (
             res["verdict"], res["evaluated"], res["batches_used"], res["eligible"], res["rejected"],
             res["pending_real"], res["coverage"], res["ctrl_power_pairs"]), ""]
    if res["measure_invalid"]:
        L += ["Контроли мер не выполнены: " + "; ".join("%s: %s" % (c, ", ".join(v)) for c, v in res["measure_invalid"]),
              ""]
    L += ["| # | пара | геометрия | STRUCT | пятна | mapping | фактура / детали (потеря) | пригодность | почему |",
          "|---|---|---|---|---|---|---|---|---|"]
    f = AC._f
    for r in res["rows"]:
        L.append("| %d | %s | %s | %s | %s | %s | %s / %s | %s | %s |" % (
            r["rank"], r["case"], r.get("geometry") or "-", r.get("struct", "-"), r.get("art", "-"), r.get("map", "-"),
            f(r.get("texture_energy_loss")), f(r.get("detail_loss")), r["eligibility"], "; ".join(r["why"]) or "-"))
    write_md("confirmation.md", L)


# ---------- карточки, итог ----------

def do_cards():
    sp, _cand = load_spec()
    conf = load("confirmation.json")
    if conf["verdict"] != "READY_FOR_HUMAN" or conf["spec_sha256"] != sp["sha256"]:
        raise SystemExit("карточки - только при READY_FOR_HUMAN (сейчас %s)" % conf["verdict"])
    if os.path.exists(os.path.join(OUT, "cards_key.json")):
        raise SystemExit("карточки уже собраны - они неизменяемы")
    rows = conf["rows"]
    el = [r for r in rows if r["eligibility"] == "SAFE_ELIGIBLE"]
    rej = sorted((r for r in rows if r["eligibility"] == "SAFE_REJECTED" and "stem" in r), key=lambda r: r["rank"])
    ctrl = random.Random(CONTROL_SEED).sample(rej, min(CONTROL_N, len(rej)))
    x4 = lambda a: np.repeat(np.repeat(a, 4, 0), 4, 1)
    rd = lambda *p: A3.read_png(os.path.join(OUT, "confirm", *p))
    items = [({"role": role, "case": r["case"], "rank": r["rank"], "eligibility": r["eligibility"], "why": r["why"]},
              [x4(rd(r["stem"] + "_member.png")), rd(r["stem"] + "_hd.png"), rd(r["stem"] + "_base.png"), None])
             for role, group in (("eligible", el), ("control_rejected", ctrl)) for r in group]
    random.Random(CARD_SEED).shuffle(items)
    os.makedirs(CARDS, exist_ok=True)
    key = []
    for i, (meta, panels) in enumerate(items, 1):
        cid = "card%03d" % i
        p = os.path.join(CARDS, cid + ".png")
        AC.card_image(panels, AC.CARD_SCALE).save(p)
        key.append(dict(meta, card=cid, png_sha256=osha(p)))
    with open(os.path.join(CARDS, "QUESTION.md"), "w", encoding=ENC, newline="\n") as f:
        f.write("# Recolor - human review\n\nFor every card answer one word: PASS, FAIL or UNSURE.\n\n"
                "> %s\n\nPanels: member original x4 | base HD | BASE recolor.\n"
                "UNSURE counts as not PASS. Write the answer into answers.tsv (column verdict), a note is optional.\n"
                % AC.QUESTION)
    with open(os.path.join(CARDS, "answers.tsv"), "w", encoding=ENC, newline="\n") as f:
        f.write("card\tverdict\tnote\n" + "".join("%s\t\t\n" % k["card"] for k in key))
    dump("cards_key.json", {"spec_sha256": sp["sha256"], "seed": CARD_SEED, "control_seed": CONTROL_SEED,
                            "cards": key, "answers_template_sha256": osha(os.path.join(CARDS, "answers.tsv")),
                            "made_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
    print("карточек %d (пригодных %d, контрольных отклонённых %d) -> %s" % (len(key), len(el), len(ctrl), CARDS))


def human_state():
    key = load("cards_key.json")
    for k in key["cards"]:
        if osha(os.path.join(CARDS, k["card"] + ".png")) != k["png_sha256"]:
            raise SystemExit("%s изменилась после сборки" % k["card"])
    rows = [ln.split("\t") for ln in open(os.path.join(CARDS, "answers.tsv"), encoding=ENC).read().splitlines()[1:]
            if ln.strip()]
    ans = {r[0]: (r[1].strip().upper() if len(r) > 1 else "", r[2] if len(r) > 2 else "") for r in rows}
    miss = [k["card"] for k in key["cards"] if ans.get(k["card"], ("",))[0] not in AC.ANSWERS]
    return key, ans, miss


def do_final():
    sp, _cand = load_spec()
    conf = load("confirmation.json")
    key, ans, miss = human_state()
    if miss:
        raise SystemExit("нет ответа по %d карточкам: %s" % (len(miss), ", ".join(miss[:20])))
    rows = [dict(k, verdict=ans[k["card"]][0], note=ans[k["card"]][1]) for k in key["cards"]]
    el = [r for r in rows if r["role"] == "eligible"]
    ct = [r for r in rows if r["role"] == "control_rejected"]
    cnt = lambda g, v: sum(r["verdict"] == v for r in g)
    prec = round(cnt(el, "PASS") / len(el), 3) if el else None
    if conf["verdict"] != "READY_FOR_HUMAN":
        over = conf["verdict"]
    elif cnt(el, "FAIL"):
        over = "FAIL"
    elif cnt(el, "UNSURE"):
        over = "NOT_PASS_UNSURE"
    else:
        over = "ELIGIBLE_FOR_VERIFIED"
    res = {"profile": PROFILE, "spec_sha256": sp["sha256"], "overall": over,
           "eligible": {"n": len(el), "PASS": cnt(el, "PASS"), "FAIL": cnt(el, "FAIL"), "UNSURE": cnt(el, "UNSURE")},
           "automatic_recolor_precision": prec,
           "controls": {"n": len(ct), "PASS": cnt(ct, "PASS"), "FAIL": cnt(ct, "FAIL"), "UNSURE": cnt(ct, "UNSURE")},
           "coverage": conf["coverage"], "evaluated": conf["evaluated"], "cards": rows,
           "answers_sha256": osha(os.path.join(CARDS, "answers.tsv")), "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    dump("final.json", res)
    L = ["# DERIVE_RECOLOR_SAFE_ACCEPTANCE_V1 - итог human review", "", "Правило: " + sp["final_rule"], "",
         "**%s**: пригодных %d - PASS %d, FAIL %d, UNSURE %d; precision %s. Контрольные отклонённые %d - PASS %d, "
         "FAIL %d, UNSURE %d. Coverage %s (прочитано %d)." % (
             over, len(el), cnt(el, "PASS"), cnt(el, "FAIL"), cnt(el, "UNSURE"), prec, len(ct), cnt(ct, "PASS"),
             cnt(ct, "FAIL"), cnt(ct, "UNSURE"), conf["coverage"], conf["evaluated"]), "",
         "| карточка | роль | случай | вердикт | заметка | почему отклонена |", "|---|---|---|---|---|---|"]
    L += ["| %s | %s | %s | %s | %s | %s |" % (r["card"], r["role"], r["case"], r["verdict"], r["note"],
                                               "; ".join(r["why"]) or "-") for r in rows]
    write_md("final.md", L)
    print("\n".join(L[:5]))


def do_report():
    sp, cand = load_spec()
    L = ["# DERIVE_RECOLOR_SAFE_ACCEPTANCE_V1 - сводка", "", "Spec `%s`, код BASE `%s`. Кандидатов %d (порядок "
         "заморожен), партии %s, нужно пригодных >= %d." % (sp["sha256"][:12], sp["implementation"]["sha256"][:12],
                                                           len(cand), list(BATCHES), MIN_ELIGIBLE), ""]
    if os.path.exists(os.path.join(OUT, "confirmation.json")):
        c = load("confirmation.json")
        L.append("Прогон: **%s**, прочитано %d (партии %s), пригодных %d, отклонено %d, без HD %d, coverage %s." % (
            c["verdict"], c["evaluated"], c["batches_used"], c["eligible"], c["rejected"], c["pending_real"],
            c["coverage"]))
    if os.path.exists(os.path.join(OUT, "final.json")):
        fin = load("final.json")
        L.append("Итог: **%s**, precision %s, контрольные %s." % (fin["overall"], fin["automatic_recolor_precision"],
                                                                 fin["controls"]))
    elif os.path.exists(os.path.join(OUT, "cards_key.json")):
        L.append("Карточки собраны, ответов ещё нет.")
    write_md("report.md", L)
    print("\n".join(L))


def do_check():
    load_spec()
    print("spec SAFE_V1, код BASE, помощники V1, пул и кандидаты не изменились")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("preview", "spec", "confirm", "cards", "final", "report", "check"))
    a = ap.parse_args()
    os.chdir(ROOT)
    {"preview": do_preview, "spec": do_spec, "confirm": do_confirm, "cards": do_cards, "final": do_final,
     "report": do_report, "check": do_check}[a.cmd]()


if __name__ == "__main__":
    main()
