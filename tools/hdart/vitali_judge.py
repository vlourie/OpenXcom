#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""VITALI_JUDGE: визуальный судья few-shot по критерию Vitali (специалист 05.10, передал Vitali в чате).

Финальный арбитр спора (dispute_arbiter.py) признан непригодным: из 22 годных споров калибровки не принял ни
одного (R-234). Причина у судей общая: каждый держит свой стандарт - Claude считает браком почти любое отличие от
оригинала, Codex мягче. Этот судья перед каждым батчем видит эталоны: оригинал | HD | приговор Vitali и его слова
о дефекте, и решает не «есть ли отличие», а «принял бы это Vitali, судя по эталонам».

Разметка Vitali (всё, что есть, без оценок специалиста):
    V1    - первая производственная партия: RESTORE, STRICT, THIRD (visual-judge-v1/key.json)
    RB1   - RESTORE_BATCH_V1: 11 FAIL (shape-fail-control-v1) и 16 PASS (regression_pass.tsv)
    SCF   - STRICT_CTL_V1 по 11 FAIL: варианты STRICT и PHOTO с его вердиктом вслепую (RESTORE этих 11 уже в RB1)
    SCR   - STRICT_CTL_V1 регрессия: STRICT по 16 PASS, PASS/FAIL
Одна и та же картинка с разными вердиктами выкидывается. Деление по ПРЕДМЕТУ (все кадры предмета - в одну сторону),
по хэшу: примерно 2/3 пул, 1/3 запечатанный тест. Из пула 20 эталонов показываются судье (10 PASS, 10 FAIL; половина
каждой стороны - трудные: годное, которое строгий судья забраковал, и брак, который мягкий судья пропустил), остальное
пула - DEV, на нём можно править текст правил. TEST вскрывается один раз, после заморозки правил (sha в pack.json).

Ворота производства (специалист): на TEST False PASS <= 5 процентов (доля брака Vitali, которую судья принял) и
PASS recall >= 70 процентов (доля годных Vitali, которые судья принял). Только после этого - применение к V2.

    GPUQ_BYPASS=1 py -3.13 tools/hdart/vitali_judge.py pack
    GPUQ_BYPASS=1 py -3.13 tools/hdart/vitali_judge.py codex --split DEV --run r1
    GPUQ_BYPASS=1 py -3.13 tools/hdart/vitali_judge.py freeze          заморозить правила перед TEST
    GPUQ_BYPASS=1 py -3.13 tools/hdart/vitali_judge.py codex --split TEST --run r1
    GPUQ_BYPASS=1 py -3.13 tools/hdart/vitali_judge.py report

Агенты Claude пишут answers/claude_<run>_<батч>.tsv. Папка: art/objects/generation/probes/vitali-judge-v1.
"""
import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import visual_judge as vj        # noqa: E402

ENC = "utf-8-sig"
PROBES = vj.PROBES
OUT = os.path.join(PROBES, "vitali-judge-v1")
SALT = "vitali-judge-v1"
BATCH = 10
N_EX = 10                      # эталонов каждой стороны
HEAD = ["id", "verdict", "confidence", "reason"]

RULES = """# Judge with the owner's eye

You decide whether an HD replacement picture for an object of an old isometric tactical game (X-COM style,
X-Piratez mod) would be ACCEPTED by the owner, Vitali. Not whether it differs from the original - every HD
redraw differs - but whether the difference is of the kind Vitali accepts or of the kind he rejects.

Every picture (exemplar `ex/E##.png` and item `img/T###.png`) has two columns:

* **A (left)** - the original game sprite, 32x40 pixel art, enlarged x4 without smoothing. What the object is.
* **B (right)** - the HD picture that would replace A in the game.

Top row on a dark floor, bottom row on a light floor (to see holes, see-through parts, halos).

## Exemplars - Vitali's own decisions

`EXEMPLARS.md` lists 20 exemplars with his verdict. For a FAIL it gives his words about the defect (in Russian).
Look at ALL exemplar pictures first and learn his standard from them:

* the PASS exemplars show how much change he tolerates: new texture, light, rounding, more detail, small
  shifts - an HD redraw is supposed to look different from pixel art;
* the FAIL exemplars show what he rejects: a part broken or melted, the inner structure changed (number or
  position of shelves, legs, doors, slats, rungs), a characteristic detail lost, the object turned into
  another object, a wrong material or colour region, see-through body, pixel steps left.

## Your decision for each item

Compare the item with the exemplars, not with an ideal. Ask: is there a defect of the same kind and size as
in his FAIL exemplars? If yes - FAIL. If the changes are of the kind and size he accepted in PASS exemplars -
PASS. Do not fail an item for a difference that a PASS exemplar also has. If you cannot place it between his
PASS and FAIL exemplars - UNCERTAIN (he will look himself).

Answer for EVERY item of the batch, one line per item, tab-separated:

    id<TAB>verdict<TAB>confidence<TAB>reason

* verdict: PASS, FAIL or UNCERTAIN
* confidence: sure or unsure
* reason: at most 20 English words; for FAIL name the defect and the exemplar it resembles (e.g. "like E07")

Do not open any file outside this folder. Output only the lines, no table, no header.
"""


def h(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def read_tsv(p):
    return vj.read_tsv(p)


def P(*a):
    return os.path.join(PROBES, *a)


def collect():
    """Вся разметка Vitali: [{key, asset_id, piece, truth, why, src}]."""
    items = []
    with open(P("visual-judge-v1", "key.json"), encoding=ENC) as f:
        for x in json.load(f):
            why = " ".join(t for t in (x.get("truth_types", ""), x.get("truth_note", "")) if t).strip()
            items.append({"key": "V1/%s/%s" % (x["stage"], x["asset_id"]), "asset_id": x["asset_id"],
                          "piece": x["piece"], "truth": x["truth"], "why": why, "src": "V1-" + x["stage"],
                          "cal_id": x["id"]})
    for r in read_tsv(P("restore-batch-v1", "verdicts_vitali.tsv")):
        if r["verdict"] == "FAIL":
            s, f = r["asset_id"].split(":")
            items.append({"key": "RB1/" + r["asset_id"], "asset_id": r["asset_id"], "truth": "FAIL",
                          "piece": P("restore-batch-v1", "render", s + ".PCK", f + ".png"), "why": r["note"],
                          "src": "RB1"})
    for r in read_tsv(P("shape-fail-control-v1", "regression_pass.tsv")):
        items.append({"key": "RB1/" + r["asset_id"], "asset_id": r["asset_id"], "truth": "PASS",
                      "piece": r["restore_piece"], "why": "", "src": "RB1"})
    with open(P("strict-ctl-v1", "key.json"), encoding=ENC) as f:
        sk = json.load(f)
    photo = {r["asset_id"]: r["photo_piece"] for r in read_tsv(P("shape-fail-control-v1", "control.tsv"))}

    def strict_piece(a):
        s, f = a.split(":")
        return P("strict-ctl-v1", "series", s + ".PCK", f + ".png")
    for r in read_tsv(P("strict-ctl-v1", "verdicts_fail_vitali.tsv")):
        a = r["asset_id"]
        for col in "XYZ":
            v, var = r[col], sk["fail"][a][col]
            if v not in ("PASS", "FAIL") or var == "restore":
                continue
            fixed = r[col + "_fixed"]
            why = "" if v == "PASS" else "дефект прежнего RESTORE: %s%s" % (
                r["defect"], "; исправлен: " + fixed if fixed else "")
            items.append({"key": "SCF/%s/%s" % (var, a), "asset_id": a, "truth": v, "why": why, "src": "SCF-" + var,
                          "piece": strict_piece(a) if var == "strict" else photo[a]})
    for r in read_tsv(P("strict-ctl-v1", "verdicts_regress_vitali.tsv")):
        if r["strict"] in ("PASS", "FAIL"):
            items.append({"key": "SCR/" + r["asset_id"], "asset_id": r["asset_id"], "truth": r["strict"],
                          "piece": strict_piece(r["asset_id"]), "why": "", "src": "SCR"})
    # одна картинка - один вердикт: повторы с тем же вердиктом схлопнуть, с разным - выкинуть
    by = defaultdict(list)
    for x in items:
        if not os.path.exists(x["piece"]):
            raise SystemExit("нет рендера %s: %s" % (x["key"], x["piece"]))
        x["sha"] = vj.sha_file(x["piece"])
        by[x["sha"]].append(x)
    out, dropped = [], []
    for sha, xs in by.items():
        if len(set(x["truth"] for x in xs)) > 1:
            dropped += [x["key"] for x in xs]
        else:
            out.append(xs[0])
    return out, dropped


def hard_flags(items):
    """Трудные эталоны по ответам старых судей калибровки V1: годное, которое Claude забраковал, и брак,
    который Codex пропустил."""
    A = vj.load_answers(vj.OUT_CAL, "claude")
    B = vj.load_answers(vj.OUT_CAL, "codex")
    for x in items:
        cid = x.get("cal_id")
        x["hard"] = bool(cid and ((x["truth"] == "PASS" and A.get(cid, {}).get("verdict") == "FAIL") or
                                  (x["truth"] == "FAIL" and B.get(cid, {}).get("verdict") == "PASS")))


def do_pack():
    if os.path.exists(os.path.join(OUT, "pack.json")):
        raise SystemExit("пакет уже собран (pack.json) - не пересобираю")
    items, dropped = collect()
    hard_flags(items)
    groups = defaultdict(list)
    for x in items:
        groups[x["asset_id"]].append(x)
    order = sorted(groups, key=lambda a: h(SALT + ":split:" + a))
    for n, a in enumerate(order):
        for x in groups[a]:
            x["split"] = "TEST" if n % 3 == 0 else "POOL"
    pool = [x for x in items if x["split"] == "POOL"]
    # эталоны: по N_EX каждой стороны, половина - трудные; разные предметы, у FAIL - со словами Vitali
    ex, used = [], set()
    for truth in ("PASS", "FAIL"):
        cand = [x for x in pool if x["truth"] == truth and (truth == "PASS" or x["why"])]
        cand.sort(key=lambda x: h(SALT + ":ex:" + x["key"]))
        take = []
        for want_hard in (True, False):
            for x in cand:
                if len(take) >= (N_EX // 2 if want_hard else N_EX):
                    break
                if x["hard"] == want_hard and x["asset_id"] not in used:
                    take.append(x)
                    used.add(x["asset_id"])
        ex += take
    for x in pool:
        if x in ex:
            x["split"] = "EXEMPLAR"
        elif x["asset_id"] in used:
            x["split"] = "EXEMPLAR_SIBLING"          # другой кадр того же предмета - ни в DEV, ни в TEST
        else:
            x["split"] = "DEV"
    ex.sort(key=lambda x: h(SALT + ":exorder:" + x["key"]))
    blind = os.path.join(OUT, "blind")
    os.makedirs(os.path.join(blind, "ex"), exist_ok=True)
    os.makedirs(os.path.join(blind, "img"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "answers"), exist_ok=True)
    lines = ["# Exemplars - Vitali's decisions", ""]
    for n, x in enumerate(ex, 1):
        x["id"] = "E%02d" % n
        vj.compose(vj.sprite(x["asset_id"]), x["piece"], os.path.join(blind, "ex", x["id"] + ".png"))
        lines.append("- %s: ex/%s.png - %s%s" % (x["id"], x["id"], x["truth"],
                                                 (" - Vitali: " + x["why"]) if x["truth"] == "FAIL" else ""))
    with open(os.path.join(blind, "EXEMPLARS.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(blind, "RULES.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(RULES)
    batches = {}
    for split in ("DEV", "TEST"):
        part = sorted((x for x in items if x["split"] == split), key=lambda x: h(SALT + ":" + split + x["key"]))
        for n, x in enumerate(part, 1):
            x["id"] = "T%s%03d" % (split[0], n)
            vj.compose(vj.sprite(x["asset_id"]), x["piece"], os.path.join(blind, "img", x["id"] + ".png"))
        for k in range(0, len(part), BATCH):
            name = "%s_%02d" % (split, k // BATCH + 1)
            batches[name] = [x["id"] for x in part[k:k + BATCH]]
            bl = ["# Batch %s" % name, "", "Instructions: RULES.md, exemplars: EXEMPLARS.md (pictures ex/E01-E%02d)."
                  % len(ex), "Items:", ""] + ["- %s: img/%s.png" % (x["id"], x["id"]) for x in part[k:k + BATCH]]
            with open(os.path.join(blind, name + ".md"), "w", encoding="utf-8", newline="\n") as f:
                f.write("\n".join(bl) + "\n")
    c = Counter((x["split"], x["truth"]) for x in items)
    vj.dump({"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "salt": SALT, "n": len(items), "dropped": dropped,
             "counts": {"%s/%s" % k: v for k, v in sorted(c.items())},
             "src": dict(Counter(x["src"] for x in items)), "exemplars": [x["key"] for x in ex],
             "batches": batches, "rules_sha256": None, "frozen": False}, os.path.join(OUT, "pack.json"))
    vj.dump(items, os.path.join(OUT, "key.json"))
    print("разметка %d (выкинуто конфликтов %d), %s" % (len(items), len(dropped), dict(Counter(x["src"] for x in items))))
    print("деление: %s" % ", ".join("%s/%s %d" % (k[0], k[1], v) for k, v in sorted(c.items())))
    print("эталоны: %s" % ", ".join("%s %s%s" % (x["id"], x["truth"], " hard" if x["hard"] else "") for x in ex))
    print("батчи: %s" % ", ".join(batches))


def rules_sha():
    blind = os.path.join(OUT, "blind")
    return h(open(os.path.join(blind, "RULES.md"), encoding="utf-8").read() +
             open(os.path.join(blind, "EXEMPLARS.md"), encoding="utf-8").read())


def do_rules():
    """Переписать RULES.md по тексту в коде - только до заморозки (правка по DEV)."""
    with open(os.path.join(OUT, "pack.json"), encoding=ENC) as f:
        pack = json.load(f)
    if pack["frozen"]:
        raise SystemExit("правила заморожены - TEST уже идёт")
    with open(os.path.join(OUT, "blind", "RULES.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(RULES)
    print("RULES.md переписан: %s" % rules_sha()[:12])


def do_freeze():
    with open(os.path.join(OUT, "pack.json"), encoding=ENC) as f:
        pack = json.load(f)
    if pack["frozen"]:
        raise SystemExit("уже заморожено: %s" % pack["rules_sha256"][:12])
    pack["rules_sha256"], pack["frozen"] = rules_sha(), True
    pack["frozen_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    vj.dump(pack, os.path.join(OUT, "pack.json"))
    print("правила и эталоны заморожены: %s" % pack["rules_sha256"][:12])


def parse_lines(text, want):
    got = {}
    for line in text.splitlines():
        line = line.strip().strip("`")
        m = re.match(r"^(T[DTV]\d{3})\s*[\t|]\s*(PASS|FAIL|UNCERTAIN)\s*[\t|]\s*(sure|unsure)\s*[\t|]?\s*(.*)$",
                     line, re.I)
        if not m or m.group(1) not in want:
            continue
        got[m.group(1)] = {"id": m.group(1), "verdict": m.group(2).upper(), "confidence": m.group(3).lower(),
                           "reason": m.group(4).strip()[:240]}
    return got


def load_votes(who):
    d = os.path.join(OUT, "answers")
    res = {}
    for f in sorted(os.listdir(d)):
        if f.endswith(".tsv") and (f == who + ".tsv" or f.startswith(who + "_")):
            for r in read_tsv(os.path.join(d, f)):
                res.update(parse_lines("\t".join(r.get(c) or "" for c in HEAD), {r.get("id", "")}))
    return res


def save_answers(who, ans):
    p = os.path.join(OUT, "answers", who + ".tsv")
    with open(p + ".tmp", "w", encoding=ENC, newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEAD, delimiter="\t", quoting=csv.QUOTE_NONE, lineterminator="\n")
        w.writeheader()
        for k in sorted(ans):
            w.writerow({c: ans[k].get(c, "").replace("\t", " ") for c in HEAD})
    os.replace(p + ".tmp", p)


def check_frozen(split):
    with open(os.path.join(OUT, "pack.json"), encoding=ENC) as f:
        pack = json.load(f)
    if split in ("TEST", "V2"):
        if not pack["frozen"]:
            raise SystemExit("TEST и V2 только после freeze")
        if rules_sha() != pack["rules_sha256"]:
            raise SystemExit("правила или эталоны изменены после заморозки")
    return pack


def do_codex(split, run, only, effort):
    pack = check_frozen(split)
    blind = os.path.abspath(os.path.join(OUT, "blind"))
    who = "codex_" + run
    ans = load_votes(who)
    codex = shutil.which("codex") or "codex"
    logs = os.path.join(OUT, "answers", "codex_logs")
    os.makedirs(logs, exist_ok=True)
    rules = open(os.path.join(blind, "RULES.md"), encoding="utf-8").read()
    exm = open(os.path.join(blind, "EXEMPLARS.md"), encoding="utf-8").read()
    exs = sorted(f[:-4] for f in os.listdir(os.path.join(blind, "ex")))
    for name, ids in pack["batches"].items():
        if not name.startswith(split) or (only and name not in only) or all(i in ans for i in ids):
            continue
        batch = open(os.path.join(blind, name + ".md"), encoding="utf-8").read()
        imgs = [os.path.join(blind, "ex", e + ".png") for e in exs] + [os.path.join(blind, "img", i + ".png")
                                                                       for i in ids]
        names = exs + ids
        task = (rules + "\n\n" + exm + "\n\n" + batch + "\nThe images are attached in this order: " +
                ", ".join("image %d = %s" % (k + 1, i) for k, i in enumerate(names)) +
                ".\nAnswer now: exactly %d lines, one per item %s, as specified.\n" % (len(ids), ", ".join(ids)))
        last = os.path.abspath(os.path.join(logs, "%s_%s.last.txt" % (run, name)))
        t0 = time.time()
        cmd = [codex, "exec", "--skip-git-repo-check", "--sandbox", "read-only", "-C", blind, "--color", "never",
               "-c", "model_reasoning_effort=" + effort, "-o", last] + sum([["-i", q] for q in imgs], []) + ["-"]
        # задание через stdin: codex.cmd режет аргумент на первом переводе строки (R-222)
        with open(os.path.join(logs, "%s_%s.log" % (run, name)), "w", encoding="utf-8") as lf:
            rc = subprocess.run(cmd, cwd=blind, stdout=lf, stderr=subprocess.STDOUT, input=task.encode("utf-8"),
                                timeout=40 * 60).returncode
        text = open(last, encoding="utf-8", errors="replace").read() if os.path.exists(last) else ""
        got = parse_lines(text, set(ids))
        ans.update(got)
        save_answers(who, ans)
        print("%s %s: код %d, %.0f с, ответов %d из %d" % (run, name, rc, time.time() - t0, len(got), len(ids)),
              flush=True)


def do_v2pack():
    """Кадры партии V2 (все 75 нарисованных из final_auto.tsv) - тем же видом в ту же слепую папку, батчи V2_##.
    Только после заморозки: эталоны и правила те же, что на TEST."""
    pack = check_frozen("V2")
    if any(k.startswith("V2") for k in pack["batches"]):
        raise SystemExit("V2 уже упакован")
    rows = read_tsv(os.path.join(vj.V2, "final_auto.tsv"))
    rows.sort(key=lambda r: h(SALT + ":V2" + r["asset_id"]))
    blind = os.path.join(OUT, "blind")
    key = []
    for n, r in enumerate(rows, 1):
        i = "TV%03d" % n
        vj.compose(vj.sprite(r["asset_id"]), r["piece"], os.path.join(blind, "img", i + ".png"))
        key.append({"id": i, "asset_id": r["asset_id"], "status_v2": r["status"], "stage": r["stage"],
                    "piece": r["piece"], "sha": vj.sha_file(r["piece"])})
    for k in range(0, len(key), BATCH):
        name = "V2_%02d" % (k // BATCH + 1)
        pack["batches"][name] = [x["id"] for x in key[k:k + BATCH]]
        bl = ["# Batch %s" % name, "", "Instructions: RULES.md, exemplars: EXEMPLARS.md (pictures ex/E01-E20).",
              "Items:", ""] + ["- %s: img/%s.png" % (x["id"], x["id"]) for x in key[k:k + BATCH]]
        with open(os.path.join(blind, name + ".md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(bl) + "\n")
    vj.dump(key, os.path.join(OUT, "v2_key.json"))
    vj.dump(pack, os.path.join(OUT, "pack.json"))
    print("V2: %d кадров, %s" % (len(key), dict(Counter(x["status_v2"] for x in key))))


def gate(part, dec):
    """dec: id -> PASS/FAIL/UNCERTAIN. False PASS - доля брака Vitali, принятого судьёй; recall - доля годных."""
    nf = sum(x["truth"] == "FAIL" for x in part)
    np_ = sum(x["truth"] == "PASS" for x in part)
    fp = sum(x["truth"] == "FAIL" and dec.get(x["id"]) == "PASS" for x in part)
    tp = sum(x["truth"] == "PASS" and dec.get(x["id"]) == "PASS" for x in part)
    unc = sum(dec.get(x["id"]) == "UNCERTAIN" for x in part)
    miss = sum(x["id"] not in dec for x in part)
    acc = sum(dec.get(x["id"]) == "PASS" for x in part)
    return {"n": len(part), "fail": nf, "pass": np_, "false_pass": fp, "false_pass_rate": fp / nf if nf else None,
            "accepted": acc, "bad_in_accepted": fp / acc if acc else None, "pass_recall": tp / np_ if np_ else None,
            "uncertain": unc, "missing": miss}


def majority(vs):
    c = Counter(v["verdict"] for v in vs)
    v, k = c.most_common(1)[0]
    return v if k * 2 > len(vs) else "UNCERTAIN"


def do_report():
    with open(os.path.join(OUT, "key.json"), encoding=ENC) as f:
        items = json.load(f)
    whos = sorted(set(re.match(r"^(\w+?_r\d+)", f).group(1) for f in os.listdir(os.path.join(OUT, "answers"))
                      if f.endswith(".tsv") and re.match(r"^\w+?_r\d+", f)))
    votes = {w: load_votes(w) for w in whos}
    md = ["# VITALI_JUDGE V1 - замер", "",
          "Ворота: False PASS (доля брака Vitali, принятого судьёй) не больше 5 процентов; PASS recall (доля "
          "годных Vitali, принятых судьёй) не меньше 70 процентов. UNCERTAIN - не принят.", ""]
    res = {}
    for split in ("DEV", "TEST"):
        part = [x for x in items if x["split"] == split]
        if not part:
            continue
        md += ["## %s: %d кадров (годных %d, брака %d)" % (split, len(part), sum(x["truth"] == "PASS" for x in part),
                                                           sum(x["truth"] == "FAIL" for x in part)), "",
               "| судья | ответов | принято | из них брак | False PASS | PASS recall | UNCERTAIN |",
               "|---|---|---|---|---|---|---|"]
        rows = {}
        for w in whos:
            dec = {x["id"]: votes[w][x["id"]]["verdict"] for x in part if x["id"] in votes[w]}
            if dec:
                rows[w] = gate(part, dec)
        fams = defaultdict(list)
        for w in whos:
            fams[w.split("_")[0]].append(w)
        for fam, ws in fams.items():
            if len(ws) >= 2:
                dec = {x["id"]: majority([votes[w][x["id"]] for w in ws]) for x in part
                       if all(x["id"] in votes[w] for w in ws)}
                if dec:
                    rows["%s большинство %d" % (fam, len(ws))] = gate(part, dec)
        for k, m in rows.items():
            md.append("| %s | %d | %d | %d | %s | %s | %d |" % (
                k, m["n"] - m["missing"], m["accepted"], m["false_pass"],
                "%.1f%%" % (100 * m["false_pass_rate"]) if m["false_pass_rate"] is not None else "-",
                "%.1f%%" % (100 * m["pass_recall"]) if m["pass_recall"] is not None else "-", m["uncertain"]))
        res[split] = rows
        md.append("")
        for w in whos:
            bad = [x for x in part if x["truth"] == "FAIL" and votes[w].get(x["id"], {}).get("verdict") == "PASS"]
            if bad:
                md += ["%s, %s - брак принят: " % (split, w) + "; ".join(
                    "%s %s (Vitali: %s)" % (x["id"], x["key"], x["why"][:60]) for x in bad), ""]
    vj.dump(res, os.path.join(OUT, "report.json"))
    with open(os.path.join(OUT, "report.md"), "w", encoding=ENC, newline="\n") as f:
        f.write("\n".join(md) + "\n")
    print("\n".join(md))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["pack", "rules", "freeze", "codex", "report", "v2pack"])
    ap.add_argument("--split", default="DEV", choices=["DEV", "TEST", "V2"])
    ap.add_argument("--run", default="r1")
    ap.add_argument("--only", default="")
    ap.add_argument("--effort", default="high")
    a = ap.parse_args()
    os.chdir(vj.ROOT)
    if a.cmd == "pack":
        do_pack()
    elif a.cmd == "rules":
        do_rules()
    elif a.cmd == "v2pack":
        do_v2pack()
    elif a.cmd == "freeze":
        do_freeze()
    elif a.cmd == "codex":
        do_codex(a.split, a.run, set(x for x in a.only.split(",") if x), a.effort)
    else:
        do_report()


if __name__ == "__main__":
    main()
