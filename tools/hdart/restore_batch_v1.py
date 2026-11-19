#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""RESTORE_BATCH_V1 - первая рабочая партия прямого рендера на production baseline RESTORE (DECISIONS 2026-10-03,
специалист 03.10, передал Vitali в чате). Состав - 33 одиночных кадра READY из generation.tsv (выбор Vitali 03.10).

Baseline - RESTORE_V1 с исправлениями V1B и V1C, во время партии не меняется:
  - промпт реставрации RESTORE плюс запрет каймы HALO_BAN, негатив V1 плюс HALO_NEG (restore_probe_v1, v1b);
  - точное описание каждого ассета - человеческое опознание из generation.tsv, перед рендером подтверждает Vitali
    (descriptions.tsv, status OK у всех; R-125);
  - модель по замку, 40 шагов, cfg 4, 1 Мп, вход варианта C, до трёх попыток (struct_probe.Render без правки);
  - ворота asset_fidelity COLOR, DARK, PARTS, EDGE_COLOR_HALO поверх машины photo_accept;
  - THIN_EDGE_NEUTRAL_BACKGROUND: если выбор по запасу (photo_render.panels_by_margin) дал насыщенную подложку
    (photo_base.CHROMA), а у оригинала доля тела в деталях тоньше 3 пикселей (что снимает открытие 3x3) не меньше
    THIN_MIN - подложки только серые, первой grey_mid. Серый не делается общим фоном: у остальных выбор прежний.
    Калибровка на контрольных 7 (restore-batch-v1/thin.tsv): насыщенную получал только MOUNTSNOW2:16 (тонкое 0.106)
    - правило меняет подложку ему одному.
Связи (relations): замороженные детекторы V7; поверх - решение человека relations_human.tsv (Vitali 03.10: восемь
кандидатов сборки R-153 - самостоятельные предметы, рисовать). Исключение одного кадра - EXCEPTIONS (ржавчина
оригинала у IDT_SNOWVILBAN:81), в baseline.json вместе с текстом негатива.
baseline.json пишется один раз (хэши кода и замка, текст промпта и негатива, правило подложки); render и report
сверяют его и не работают, если baseline изменился. Сомнительное - REVIEW, параметры по ходу не подстраиваются.

    select   задания jobs.json и черновик descriptions.tsv (status PENDING) по generation.tsv; thin.tsv
    freeze   baseline.json (второй раз - только тот же)
    prompts  промпты в prompts.md (без модели)
    render   рендер - только через очередь (gpu_scripts.txt):
        py -3.13 tools/gpuq.py add --name restore_batch_v1 --cwd E:/OpenXCom -- \
            E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/render_chunks.py \
            --out art/objects/generation/probes/restore-batch-v1 -- \
            E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/restore_batch_v1.py render
    report   итог по каждому кадру (машина и верность, худшее из двух), доли PASS / REVIEW / FAIL, лист sheet.png
Без модели (GPUQ_BYPASS=1): select, freeze, prompts, report.
"""
import argparse
import csv
import hashlib
import inspect
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import restore_probe_v1b  # noqa: E402,F401  (ставит HALO_BAN и HALO_NEG в restore_probe_v1)
import restore_probe_v1 as rp  # noqa: E402

PROFILE = "RESTORE_BATCH_V1"
OUT = rp.PROBES + "/restore-batch-v1"
GEN = "art/objects/generation/generation.tsv"
RUNS = "art/objects/generation/runs"
PILOT_RUNS = ("acc-5e9f63c421c0", "pilot-v2-18e401ad31e8")      # партии 1 и 2 generation.tsv
SEED0 = 6100
THIN_MIN = 0.05
THIN_PANEL = "grey_mid"
CONTROLS = ("BATHBITZ:14", "FREIGHTER_COMMAND_2:56", "MADDECOR_WASTE:12", "MOUNTSNOW2:16", "OSIRON_FINNIK:41",
            "URBAN40K:86", "XB3BITZ1:26")
BASE_CODE = ("tools/hdart/restore_probe_v1.py", "tools/hdart/restore_probe_v1b.py", "tools/hdart/asset_fidelity.py",
             "tools/hdart/photo_render.py", "tools/hdart/photo_base.py", "tools/hdart/photo_accept.py",
             "tools/hdart/struct_probe.py", "tools/hdart/struct_guide.py", "tools/hdart/gen_hd.py",
             "tools/hdart/obj_photo.py", "tools/hdart/gen_fire.py", "art/models/qwen21_turbo_rgba.lock.json")
ARTICLES = ("a", "an", "the", "one", "two", "three", "four", "pair", "pile", "set")
ENC = rp.ENC
HUMAN_REL = "relations_human.tsv"   # решение человека поверх relations.json: asset_id, decision, note
# Исключения baseline для одного кадра (решение Vitali 03.10): замена фраз промпта и негатива, по одному вхождению.
# Общий запрет ржавчины остаётся; ржавчина, которая есть в оригинале, сохраняется и обязательна.
EXCEPTIONS = {
    "IDT_SNOWVILBAN:81": {
        "why": "Vitali 03.10: бочка в оригинале буро-ржавая - ржавчину оригинала сохранить, лишней не добавлять",
        "prompt": [("Clean surfaces: no wear, no rust, no dirt, no stains. ",
                    "Clean surfaces: no wear, no dirt, no stains. The rust-brown colour of the sprite is part of this "
                    "object: preserve the original rust-brown colour, do not add extra corrosion beyond the sprite. ")],
        "negative": [("rust, ", "")]}}

rp.OUT = OUT
rp.RUN1 = OUT                   # rp.jobs() читает <RUN1>/jobs.json
rp.ONLY = None
rp.PROBE = PROFILE


def fsha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def rd(path):
    with open(path, encoding=ENC) as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


# ---------------------------------------------------------------- THIN_EDGE_NEUTRAL_BACKGROUND

def thin_ratio(frame):
    """Доля непрозрачного тела оригинала в деталях тоньше 3 пикселей: что снимает открытие 3x3 (8 соседей)."""
    import numpy as np
    m = np.asarray(frame.convert("RGBA"))[..., 3] > 0
    if not m.any():
        return 0.0
    p = np.pad(m, 1, mode="edge")           # граница кадра - не край предмета: срезанный кадром край не тонкий
    e = m.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            e &= p[1 + dy:1 + dy + m.shape[0], 1 + dx:1 + dx + m.shape[1]]
    q = np.pad(e, 1, mode="edge")
    d = e.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            d |= q[1 + dy:1 + dy + m.shape[0], 1 + dx:1 + dx + m.shape[1]]
    return round(float((m & ~d).sum()) / float(m.sum()), 3)


_panels_by_margin = None


def panels_rule(frame):
    """photo_render.panels_by_margin с правилом THIN_EDGE_NEUTRAL_BACKGROUND -> (подложки, правило сработало, тонкое)."""
    import photo_base as pb
    ps = _panels_by_margin(frame)
    chroma = {n for n, _rgb in pb.CHROMA}
    t = thin_ratio(frame)
    if ps[0][0] not in chroma or t < THIN_MIN:
        return ps, False, t
    greys = [p for p in ps if p[0] not in chroma]
    first = [p for p in greys if p[0] == THIN_PANEL]
    if len(first) != 1:
        raise SystemExit("подложки %s нет в photo_base.PANELS - список изменился" % THIN_PANEL)
    return first + [p for p in greys if p[0] != THIN_PANEL], True, t


def install_rule():
    """Подменить photo_render.panels_by_margin в этом процессе (photo_render.py не правится)."""
    global _panels_by_margin
    import photo_render as pr
    if _panels_by_margin is None:
        _panels_by_margin = pr.panels_by_margin
        pr.panels_by_margin = lambda frame: panels_rule(frame)[0]


# ---------------------------------------------------------------- исключения одного кадра

def apply_swaps(text, swaps, where):
    for old, new in swaps:
        if text.count(old) != 1:
            raise SystemExit("исключение: %r встречается в %s %d раз, нужно 1 - baseline изменился" % (
                old, where, text.count(old)))
        text = text.replace(old, new)
    return text


_current = {"asset": None}


def install_exceptions():
    """В этом процессе: промпт и негатив кадра из EXCEPTIONS (restore_probe_v1 и struct_probe не правятся).
    Кадр узнаётся по заданию (Render.job) или, без рендера, по описанию (prompts). Негатив задания ставится
    перед job и возвращается после finish - meta пишет негатив того кадра, которым он рисовался."""
    import gen_fire
    import struct_probe as sp
    by_what = {j["what"]: j["asset_id"] for j in rp.jobs(False)}
    base_prompt_for = rp.prompt_for

    def prompt_for(what, name, rgb):
        a = _current["asset"] or by_what.get(what)
        text = base_prompt_for(what, name, rgb)
        return apply_swaps(text, EXCEPTIONS[a]["prompt"], "промпте") if a in EXCEPTIONS else text

    base_job, base_finish = sp.Render.job, sp.Render.finish

    def job(self, v, j, *args, **kw):
        _current["asset"] = j["asset_id"]
        gen_fire.NEGATIVE = negative_for(j["asset_id"])
        return base_job(self, v, j, *args, **kw)

    def finish(self, *args, **kw):
        try:
            return base_finish(self, *args, **kw)
        finally:
            _current["asset"] = None
            gen_fire.NEGATIVE = rp.negative()

    rp.prompt_for = prompt_for
    sp.Render.job, sp.Render.finish = job, finish


def negative_for(asset):
    n = rp.negative()
    return apply_swaps(n, EXCEPTIONS[asset]["negative"], "негативе") if asset in EXCEPTIONS else n


# ---------------------------------------------------------------- select

def describe(text):
    """Человеческое опознание -> подпись для промпта: без точки в конце, со строчной буквы, с артиклем.
    Смысл не меняется; правит Vitali в descriptions.tsv."""
    t = " ".join(text.strip().split()).rstrip(".")
    if len(t) > 1 and t[0].isupper() and not t[1].isupper():
        t = t[0].lower() + t[1:]
    if t.split(" ", 1)[0].lower() not in ARTICLES:
        t = ("an " if t[:1].lower() in "aeiou" else "a ") + t
    return t


def do_select():
    import map_mockup as mm
    import hd_e2e_v1_run as e2e
    install_rule()
    rows = rd(GEN)
    ready = [r for r in rows if r["status"] == "READY"]
    jobs, desc, skipped = [], [], []
    for r in sorted(ready, key=lambda x: int(x["rank"])):
        if r["kind"] != "один":
            skipped.append((r["asset_id"], "kind %s: baseline только для одиночного кадра" % r["kind"]))
            continue
        if r["identity_status"] not in ("HUMAN_CONFIRMED", "HUMAN_EDITED") or not r["identity"].strip():
            skipped.append((r["asset_id"], "нет опознания человеком"))
            continue
        k = r["asset_id"]
        s, f = k.split(":")
        jobs.append({"name": "bat_%s_%s" % (s.lower(), f), "job_id": "b%02d" % (len(jobs) + 1), "map": "", "at": [],
                     "take": ["%s@0" % k], "what": r["identity"].strip(), "asset_id": k, "src": k,
                     "seed": SEED0 + len(jobs) + 1, "stratum": "restore_batch", "group": "restore_batch",
                     "identity_how": r["identity_status"], "identity_source": "generation.tsv", "output": ""})
        desc.append({"asset_id": k, "rank": r["rank"], "places": r["places"], "identity_status": r["identity_status"],
                     "identity": r["identity"].strip(), "description": describe(r["identity"]), "status": "PENDING",
                     "note": ""})
    os.makedirs(OUT, exist_ok=True)
    jp = os.path.join(OUT, "jobs.json")
    if os.path.exists(jp) and rp.load(jp) != jobs:
        raise SystemExit("jobs.json уже есть и отличается - состав партии не переписывается")
    rp.dump(jp, jobs)
    dp = os.path.join(OUT, "descriptions.tsv")
    if os.path.exists(dp):
        print("descriptions.tsv уже есть - не трогаю (правки Vitali)")
    else:
        with open(dp, "w", encoding=ENC, newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(desc[0]), delimiter="\t", quoting=csv.QUOTE_NONE,
                               lineterminator="\n")
            w.writeheader()
            w.writerows(desc)
    world = mm.World()
    lines = ["asset_id\tset\tthin\tby_margin\tmargin\tpanel\tpanel_margin\trule"]
    for tag, keys in (("control", CONTROLS), ("batch", [j["asset_id"] for j in jobs])):
        for k in keys:
            frame = e2e.sprite_frame(world, k)[4]
            ps0 = _panels_by_margin(frame)
            ps, hit, t = panels_rule(frame)
            lines.append("%s\t%s\t%.3f\t%s\t%.0f\t%s\t%.0f\t%s" % (k, tag, t, ps0[0][0], ps0[0][2], ps[0][0], ps[0][2],
                                                                 "THIN_NEUTRAL" if hit else ""))
    with open(os.path.join(OUT, "thin.tsv"), "w", encoding=ENC, newline="") as f:
        f.write("\n".join(lines) + "\n")
    hits = [x.split("\t")[0] for x in lines[1:] if x.endswith("THIN_NEUTRAL")]
    print("заданий %d, пропущено %d: %s" % (len(jobs), len(skipped), "; ".join("%s (%s)" % x for x in skipped)))
    print("правило тонкого края сработало: %s" % (", ".join(hits) or "ни у кого"))
    print("%s/jobs.json, descriptions.tsv, thin.tsv" % OUT)


# ---------------------------------------------------------------- relations

ASSEMBLY_TYPES = ("COMPOSITE_PART", "STRUCTURAL_MODULAR", "ANIMATION_FAMILY", "REPEATED_ASSEMBLY_RELATION")


def classify(a, claims, batch, comp, questions, gen_row):
    """Связи кадра a -> (решение, причины). OK - одиночный рендер ничего не ломает; остальное - не рисовать сейчас.

    Направление (как hd_e2e_v1.plan_group): у направленной связи source выводится из target. У симметричной
    (relation_discovery_v4.SYMMETRIC: копия, зеркало, перекраска-пара, правка) направления нет - рисуется один кадр
    группы, остальные выводятся из него; кадр партии и есть этот рендер, если сам ни из чего не выводится.
    Кандидат сборки (COMPOSITE_PART и др. не STRONG) - REVIEW: если подтвердится, кадр - кусок целого (R-153)."""
    import relation_discovery_v4 as v4
    A = a.upper()
    why, holds = [], []
    if gen_row["kind"] != "один" or A in comp:
        holds.append("HOLD_ASSEMBLY")
        why.append("составной предмет очереди (items.json): %s" % " ".join(comp.get(A, {}).get("keys", [])))
    if A in questions:
        holds.append("HOLD_FAMILY_QUESTION")
        why.append("открытый вопрос семейства (families.json review)")
    if gen_row["blockers"]:
        holds.append("HOLD_BLOCKERS")
        why.append("блокеры generation.tsv: %s" % gen_row["blockers"])
    for c in claims:
        other = [x for x in c["pair"] if x != A]
        o = other[0] if other else A
        tag = "%s %s %s/%s" % (c["type"], o, c["existence"], c["type_level"])
        sym = c["type"] in v4.SYMMETRIC
        derived = not sym and c["source"] == A and c["target"] and c["target"] != A
        if c["type"] in ASSEMBLY_TYPES:
            if c["auto"]:
                holds.append("HOLD_ASSEMBLY")
                why.append("связь сборки: " + tag)
            else:
                holds.append("REVIEW_ASSEMBLY_CANDIDATE")
                why.append("кандидат сборки: " + tag)
        elif derived:
            holds.append("HOLD_DERIVED" if c["auto"] else "REVIEW_MAYBE_DERIVED")
            why.append("кадр выводится из %s: %s" % (c["target"], tag))
        elif o in batch:
            holds.append("HOLD_DUPLICATE_IN_BATCH")
            why.append("связанный кадр тоже в партии: " + tag)
        elif sym:
            why.append(("выводится из этого рендера: " if c["auto"] else "кандидат родства (если подтвердится - "
                        "выводится из этого рендера): ") + tag)
        else:
            why.append(("основа для вывода позже: " if c["auto"] else "кандидат: кадр - основа: ") + tag)
    order = ("HOLD_ASSEMBLY", "HOLD_DERIVED", "HOLD_DUPLICATE_IN_BATCH", "HOLD_FAMILY_QUESTION", "HOLD_BLOCKERS",
             "REVIEW_ASSEMBLY_CANDIDATE", "REVIEW_MAYBE_DERIVED")
    dec = next((h for h in order if h in holds), "OK")
    return dec, why


def shared_groups(out):
    """Два кадра партии через общего родственника по автоматической симметричной связи - одна группа, рисуется
    один (меньший ключ), второй выводится. Связь через два шага и дальше здесь не видна - только соседи."""
    import relation_discovery_v4 as v4
    seen = {}
    for x in sorted(out, key=lambda x: x["asset_id"]):
        A = x["asset_id"].upper()
        peers = {p for c in x["claims"] if c["auto"] and c["type"] in v4.SYMMETRIC for p in c["pair"] if p != A}
        for p in sorted(peers):
            if p in seen and seen[p] != A and x["decision"] == "OK":
                x["decision"] = "HOLD_DUPLICATE_IN_BATCH"
                x["why"].append("общий родственник %s с кадром партии %s - рисуется тот" % (p, seen[p]))
            seen.setdefault(p, A)


def do_relations():
    """Замороженные детекторы V7 (hd_e2e_v1.Discovery, build) на кадрах партии, без замыкания - только чтение V7."""
    import hd_e2e_v1 as E
    import pilot_batch as pb_
    jobs = rp.load(os.path.join(OUT, "jobs.json"))
    keys = [j["asset_id"] for j in jobs]
    d, _h, _ver = E.v7_state()
    rdir = os.path.join(OUT, "relations")
    disc = E.Discovery(d["inputs"])
    rels, det, f3, f4, Ev = disc.run(keys, rdir)
    rp_ = os.path.join(rdir, "relations.json")
    _rows, C, _pr = E.build(d, keys, rp_, det, f3, f4, Ev)
    _copies, comp = E.items_index(d["inputs"])
    with open(pb_.FAMS, encoding=ENC) as f:
        questions = pb_.open_questions(json.load(f))
    gen = {r["asset_id"]: r for r in rd(GEN)}
    batch = {k.upper() for k in keys}
    out, lines = [], ["asset_id\tdecision\tclaims\twhy"]
    for k in keys:
        claims = [E.claim_view(c, k) for c in C.of(k)]
        dec, why = classify(k, claims, batch, comp, questions, gen[k])
        out.append({"asset_id": k, "decision": dec, "why": why, "claims": claims})
    shared_groups(out)
    for x in out:
        lines.append("%s\t%s\t%d\t%s" % (x["asset_id"], x["decision"], len(x["claims"]),
                                           " | ".join(x["why"]) or "связей нет"))
    rp.dump(os.path.join(OUT, "relations.json"), {"v7_freeze_sha256": d["sha256"], "items": out})
    with open(os.path.join(OUT, "relations.tsv"), "w", encoding=ENC, newline="") as f:
        f.write("\n".join(lines) + "\n")
    cnt = Counter(x["decision"] for x in out)
    print("связи: %s" % ", ".join("%s %d" % kv for kv in cnt.most_common()))
    for x in out:
        if x["decision"] != "OK" or x["why"]:
            print("  %-24s %-24s %s" % (x["asset_id"], x["decision"], " | ".join(x["why"])[:300]))
    print("%s/relations.tsv" % OUT)


# ---------------------------------------------------------------- baseline

def baseline_body():
    import asset_fidelity as AF
    return {"profile": PROFILE, "baseline": "RESTORE_V1 + V1B (HALO_BAN, HALO_NEG) + V1C (нейтральная подложка тонкому)",
            "decision": "специалист 03.10, передал Vitali в чате: RESTORE production baseline; DECISIONS 2026-10-03",
            "prompt": rp.RESTORE, "negative": rp.negative(), "variant": rp.VARIANT,
            "gates": list(AF.CHECKS), "machine": "photo_accept", "seed0": SEED0,
            "thin_rule": {"name": "THIN_EDGE_NEUTRAL_BACKGROUND", "thin_min": THIN_MIN, "panel": THIN_PANEL,
                          "code": inspect.getsource(thin_ratio) + inspect.getsource(panels_rule)},
            "code_sha256": {p: fsha(p) for p in BASE_CODE},
            "exceptions": {a: dict(e, negative_text=negative_for(a)) for a, e in EXCEPTIONS.items()},
            "batch": {"jobs_sha256": fsha(os.path.join(OUT, "jobs.json")),
                      "descriptions_sha256": fsha(os.path.join(OUT, "descriptions.tsv")),
                      "relations_human": human_relations(),
                      "render": render_set(), "held": held_set()}}


def human_relations():
    """relations_human.tsv: решение человека по кадру поверх машинного (только OK или HOLD_*)."""
    p = os.path.join(OUT, HUMAN_REL)
    if not os.path.exists(p):
        return {}
    out = {}
    for r in rd(p):
        if r["decision"] != "OK" and not r["decision"].startswith("HOLD_"):
            raise SystemExit("%s: решение %s у %s - только OK или HOLD_*" % (HUMAN_REL, r["decision"], r["asset_id"]))
        out[r["asset_id"]] = {"decision": r["decision"], "note": r["note"]}
    return out


def relation_decisions():
    """Машинные решения relations.json, поверх - решение человека (relations_human.tsv); машинное остаётся в machine."""
    p = os.path.join(OUT, "relations.json")
    if not os.path.exists(p):
        raise SystemExit("relations.json нет - сначала relations")
    out = {x["asset_id"]: x for x in rp.load(p)["items"]}
    for k, h in human_relations().items():
        if k not in out:
            raise SystemExit("%s: %s не в партии" % (HUMAN_REL, k))
        out[k] = dict(out[k], machine=out[k]["decision"], decision=h["decision"], human_note=h["note"])
    return out


def render_set():
    """Кадры к рендеру: связи OK (relations.json). Остальные держатся и в партию не идут."""
    return sorted(k for k, x in relation_decisions().items() if x["decision"] == "OK")


def held_set():
    return {k: x["decision"] for k, x in sorted(relation_decisions().items()) if x["decision"] != "OK"}


def check_descriptions():
    bad = [r["asset_id"] for r in rd(os.path.join(OUT, "descriptions.tsv"))
           if r["asset_id"] in set(render_set()) and r["status"] != "OK"]
    if bad:
        raise SystemExit("описания не подтверждены (status не OK): %s - заморозку не делаю (R-125)" % ", ".join(bad))


def check_baseline():
    bp = os.path.join(OUT, "baseline.json")
    if not os.path.exists(bp):
        raise SystemExit("baseline.json нет - сначала freeze")
    old = rp.load(bp)
    body = json.loads(json.dumps(baseline_body(), ensure_ascii=False))     # кортежи EXCEPTIONS -> списки, как в файле
    diff =sorted(k for k in body if body[k] != old["body"].get(k))
    if diff:
        bad = [p for p in BASE_CODE if body["code_sha256"][p] != old["body"]["code_sha256"].get(p)]
        raise SystemExit("baseline изменился во время партии: %s %s" % (", ".join(diff), ", ".join(bad)))
    return old


def do_freeze():
    check_descriptions()
    bp = os.path.join(OUT, "baseline.json")
    body = baseline_body()
    sha = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    if os.path.exists(bp):
        old = rp.load(bp)
        if old["sha256"] != sha:
            check_baseline()
        print("baseline.json тот же: %s" % sha[:12])
        return
    os.makedirs(OUT, exist_ok=True)
    rp.dump(bp, {"sha256": sha, "body": body})
    print("baseline.json %s" % sha[:12])


# ---------------------------------------------------------------- report

WORST = {"PASS": 0, "REVIEW": 1, "FAIL": 2}


def machine_class(outcome):
    return "PASS" if outcome in ("PASS", "PASS_AFTER_RERENDER") else outcome


def pilot_piece(k):
    """Прежний рендер пилота (партия 1 - acc-5e9f63c421c0, партия 2 - pilot-v2-18e401ad31e8) или None."""
    s, n = k.split(":")
    for run in PILOT_RUNS:
        p = os.path.join(RUNS, run, "photo", s.upper() + ".PCK", "%d.png" % int(n))
        if os.path.exists(p):
            return p.replace("\\", "/")
    return None


def visual_verdicts():
    """Визуальная приёмка: verdicts_vitali.tsv (asset_id, verdict PASS / REVIEW / FAIL, note) - ставит человек."""
    p = os.path.join(OUT, "verdicts_vitali.tsv")
    if not os.path.exists(p):
        return {}
    return {r["asset_id"]: r for r in rd(p) if r.get("verdict", "").strip() in ("PASS", "REVIEW", "FAIL")}


def share(cnt, v, n):
    return "%d (%.0f%%)" % (cnt[v], 100.0 * cnt[v] / n) if n else "0"


def do_report():
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    import asset_fidelity as AF
    import map_mockup as mm
    base = check_baseline()
    world = mm.World()
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 13)
    except OSError:
        font = ImageFont.load_default()
    thin = {r["asset_id"]: r for r in rd(os.path.join(OUT, "thin.tsv"))}
    vis = visual_verdicts()
    res, tiles = [], []
    for j in rp.jobs(False):
        mp = os.path.join(OUT, "render", "meta", j["name"] + ".json")
        rule = [thin.get(j["asset_id"], {}).get("rule", "")] + (["EXCEPTION"] if j["asset_id"] in EXCEPTIONS else [])
        row = {"asset_id": j["asset_id"], "what": j["what"], "rule": " ".join(x for x in rule if x),
               "pilot": pilot_piece(j["asset_id"]), "visual": vis.get(j["asset_id"], {}).get("verdict", ""),
               "visual_note": vis.get(j["asset_id"], {}).get("note", "")}
        if not os.path.exists(mp):
            res.append(dict(row, machine_final="NOT_RENDERED"))
            continue
        m = rp.load(mp)
        s, n = j["asset_id"].split(":")
        o = np.asarray(world.sprite(s.lower(), int(n), None).convert("RGBA"))
        r = AF.measure(o, Image.open(m["piece"]))
        mc, fv = machine_class(m["outcome"]), AF.verdict(r)
        final = max((mc, fv), key=lambda v: WORST.get(v, 2))
        why = ["photo_accept %s" % m["outcome"]] if mc != "PASS" else []
        why += ["%s %s" % (c, r[c][0]) for c in AF.CHECKS if r[c][0] != "PASS"]
        res.append(dict(row, machine_final=final, photo_accept=m["outcome"], fidelity=fv, attempts=len(m["attempts"]),
                        panel=m["attempts"][-1]["panel"], why="; ".join(why), raw=m["attempts"][-1]["raw"],
                        checks={c: list(r[c]) for c in AF.CHECKS}, piece=m["piece"]))
        tiles.append((j, o, m["piece"], row["pilot"], final, row["visual"], why))
    mcnt = Counter(x["machine_final"] for x in res)
    vcnt = Counter(x["visual"] for x in res if x["visual"])
    done = sum(mcnt[v] for v in ("PASS", "REVIEW", "FAIL"))
    vdone = sum(vcnt.values())
    held = held_set()
    md = ["# %s: итог партии" % PROFILE, "",
          "baseline `%s`; к рендеру %d кадров, отрисовано %d; задержано связями %d (relations.tsv)." % (
              base["sha256"][:12], len(res), done, len(held)), "",
          "Машинный итог кадра - худшее из photo_accept и ворот верности %s. Визуальная приёмка - "
          "verdicts_vitali.tsv, ставит человек; машина её не заменяет." % ", ".join(AF.CHECKS), "",
          "| | PASS | REVIEW | FAIL | всего |", "|---|---|---|---|---|",
          "| машина | %s | %s | %s | %d |" % (share(mcnt, "PASS", done), share(mcnt, "REVIEW", done),
                                             share(mcnt, "FAIL", done), done),
          "| визуальная приёмка | %s | %s | %s | %d из %d |" % (share(vcnt, "PASS", vdone), share(vcnt, "REVIEW", vdone),
                                                            share(vcnt, "FAIL", vdone), vdone, done)]
    if mcnt["NOT_RENDERED"]:
        md.append("\nНе отрисовано: %d." % mcnt["NOT_RENDERED"])
    md += ["", "| кадр | машина | photo_accept | верность | глаз | попыток | подложка | правило | почему |",
           "|---|---|---|---|---|---|---|---|---|"]
    for x in res:
        md.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            x["asset_id"], x["machine_final"], x.get("photo_accept", "—"), x.get("fidelity", "—"), x["visual"] or "—",
            x.get("attempts", "—"), x.get("panel", "—"), x["rule"] or "—", x.get("why", "") or "—"))
    if held:
        md += ["", "Задержано связями (не рисовалось):", ""] + ["- %s: %s" % kv for kv in held.items()]
    with open(os.path.join(OUT, "report.md"), "w", encoding=ENC) as f:
        f.write("\n".join(md) + "\n")
    rp.dump(os.path.join(OUT, "report.json"), {"baseline_sha256": base["sha256"], "machine": dict(mcnt),
                                               "visual": dict(vcnt), "held": held, "items": res})
    vp = os.path.join(OUT, "verdicts_vitali.tsv")
    if not os.path.exists(vp) and done:            # заготовка визуальной приёмки - пустые вердикты
        with open(vp, "w", encoding=ENC, newline="") as f:
            f.write("asset_id\tverdict\tnote\n" + "".join("%s\t\t\n" % x["asset_id"] for x in res
                                                          if x["machine_final"] != "NOT_RENDERED"))
    if tiles:
        rows = []
        for j, o, piece, pilot, final, visual, why in tiles:
            imgs = [np.repeat(np.repeat(o, 4, 0), 4, 1),
                    np.asarray(Image.open(pilot).convert("RGBA")) if pilot else None,
                    np.asarray(Image.open(piece).convert("RGBA"))]
            H, W = imgs[0].shape[:2]
            row = Image.new("RGBA", (3 * (W * 2 + 10) + 440, H * 2), (18, 18, 18, 255))
            for i, t in enumerate(imgs):
                bg = Image.new("RGBA", (W, H), (28, 26, 24, 255))
                if t is not None and t.shape[:2] == (H, W):
                    bg.alpha_composite(Image.fromarray(t))
                row.paste(bg.resize((W * 2, H * 2), Image.LANCZOS), (i * (W * 2 + 10), 0))
            d = ImageDraw.Draw(row)
            x = 3 * (W * 2 + 10)
            d.text((x, 8), j["asset_id"], fill=(235, 235, 235), font=font)
            d.text((x, 28), "orig x4 | pilot%s | RESTORE" % ("" if pilot else " (нет)"), fill=(150, 150, 150),
                   font=font)
            d.text((x, 48), j["what"][:64], fill=(170, 170, 170), font=font)
            d.text((x, 70), "машина: %s   глаз: %s" % (final, visual or "—"), fill=(235, 235, 235), font=font)
            for i, w in enumerate(why[:6]):
                d.text((x, 92 + 18 * i), w[:64], fill=(200, 160, 120), font=font)
            rows.append(row)
        sheet = Image.new("RGBA", (max(r.width for r in rows), sum(r.height for r in rows)), (18, 18, 18, 255))
        y = 0
        for r in rows:
            sheet.paste(r, (0, y))
            y += r.height
        sheet.save(os.path.join(OUT, "sheet.png"))
    print("\n".join(md[6:10]))
    print("%s/report.md, sheet.png" % OUT)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["select", "relations", "freeze", "prompts", "render", "report"])
    ap.add_argument("--max-renders", type=int, default=4)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if a.cmd == "select":
        do_select()
    elif a.cmd == "relations":
        do_relations()
    elif a.cmd == "freeze":
        do_freeze()
    elif a.cmd == "prompts":
        rp.ONLY = set(render_set())
        install_rule()
        install_exceptions()
        rp.do_prompts()
        with open(os.path.join(OUT, "prompts.md"), "a", encoding=ENC) as f:
            f.write("\n## Исключения одного кадра\n\n" + "".join(
                "- %s: %s\n  негатив: `%s`\n" % (k, e["why"], negative_for(k)) for k, e in EXCEPTIONS.items()))
    elif a.cmd == "render":
        base = check_baseline()
        rp.ONLY = set(base["body"]["batch"]["render"])
        install_rule()
        install_exceptions()
        rp.do_render(a.max_renders)
    else:
        rp.ONLY = set(check_baseline()["body"]["batch"]["render"])
        do_report()


if __name__ == "__main__":
    main()
