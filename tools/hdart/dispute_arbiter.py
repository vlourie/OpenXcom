#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Финальный арбитр спора судей PROD_TWO_PASS_V2 (специалист 05.10): без видеокарты, человеку - только его UNCERTAIN.

Связка судей (visual_judge.py, Codex + Claude) даёт три ветки: оба PASS sure - AUTO_ACCEPT, оба FAIL - AUTO_FAIL
(в residual, человеку не показывается), остальное - UNCERTAIN. UNCERTAIN идёт сюда: арбитр не судит кадр с нуля,
а проверяет ровно спор - «судья 1 говорит, что деталь X сломана, судья 2 - что всё на месте».

Арбитру вслепую подмешаны споры калибровки V1 (visual-judge-v1, приговор Vitali известен) - это контроль меры
(R-231): по ним считается, сколько брака арбитр пропустил бы и сколько годного потерял. Судьи в задании безымянны
(«судья 1/2», порядок по хэшу), семья судьи не называется.

Голоса (R-231: не один прогон): codex_r1, codex_r2 - отдельные сессии codex exec; claude_r1, claude_r2 - свежие
агенты Claude, каждый пишет answers/claude_r<N>_<батч>.tsv. Правило, заданное до ответов:
    ARBITER_PASS  - PASS не меньше 3 из 4 голосов (значит, обе семьи)
    ARBITER_FAIL  - FAIL не меньше 3 из 4
    UNCERTAIN     - остальное, это и только это идёт Vitali

    GPUQ_BYPASS=1 py -3.13 tools/hdart/dispute_arbiter.py pack
    GPUQ_BYPASS=1 py -3.13 tools/hdart/dispute_arbiter.py codex --run r1 [--only B_01]
    GPUQ_BYPASS=1 py -3.13 tools/hdart/dispute_arbiter.py verdict      арбитр, калибровка, итог партии, листы

Папка: art/objects/generation/probes/prod-two-pass-v2/judge/arbiter/ (blind/ - всё, что видит арбитр).
"""
import argparse
import csv
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import visual_judge as vj        # noqa: E402

ENC = "utf-8-sig"
V2 = vj.V2
OUT = os.path.join(V2, "judge", "arbiter")
SALT = "dispute-arbiter-v1"
BATCH = 10
STAGES = ["RESTORE", "STRICT", "THIRD"]
VOTES = ["codex_r1", "codex_r2", "claude_r1", "claude_r2"]
HEAD = ["id", "verdict", "confidence", "claim", "reason"]
AUDIT_N = 6

ARBITER = """# Final arbiter of a judges' dispute

You are the final arbiter for HD replacement pictures of objects in an old isometric tactical game
(X-COM style, X-Piratez mod). Each item is ONE image `img/<id>.png` with two columns:

* **A (left)** - the original game sprite, 32x40 pixel art, enlarged x4 without smoothing. This is the truth:
  what the object is, which parts it has, their count and place, colours and materials.
* **B (right)** - the new HD picture that should replace A in the game.

Top row on a dark floor, bottom row the same pictures on a light floor (to see holes, see-through parts, halos).

Two independent judges already looked at each item and DISAGREED (or one of them was unsure). Their rule was:
B must show the same object with the same parts in the same places, and every part of B must be a
well-formed, recognisable real thing (no blobs, melted or fused parts, smears, wrong material, pixel steps,
stretching, holes or halos). The owner is a picky art director who rejects pictures that are only "roughly
the same object".

Your task is NOT to judge the item from scratch. Your task is to settle THE DISPUTE:

1. Read what each judge claims. A FAIL claim names a concrete defect ("seat floats above the base",
   "five rungs instead of four", "tabletop is blotchy").
2. Look at exactly that part in A and in B, on both floors. Count, compare positions, compare materials.
3. Decide whether the claimed defect is REAL in B (CONFIRMED), NOT THERE (REJECTED), or you cannot tell
   (UNCLEAR). A PASS claim that lists parts as present can be checked the same way.
4. Verdict:
   * FAIL - the claimed defect is real (even if it is small: the owner rejects such things), or you see
     another clear defect of the same kind while checking.
   * PASS - the claimed defect is not there and the disputed part of B matches A and is well-formed.
     A PASS must be sure.
   * UNCERTAIN - you honestly cannot tell from the pictures; the owner will look himself.

The judges can both be wrong. Do not side with the more confident judge; side with what you see.

Answer for EVERY item of the batch, one line per item, tab-separated:

    id<TAB>verdict<TAB>confidence<TAB>claim<TAB>reason

* verdict: PASS, FAIL or UNCERTAIN
* confidence: sure or unsure
* claim: CONFIRMED, REJECTED or UNCLEAR - about the FAIL claim of the dispute
* reason: at most 20 English words: what exactly you saw in the disputed part

Look at every image yourself. Do not open any file outside this folder. Output only the lines, no table, no header.
"""


def h(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def read_tsv(p):
    if not os.path.exists(p):
        return []
    with open(p, encoding=ENC, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def judges_of(rows):
    """[(verdict, confidence, types, reason)] обоих судей; route связки: AUTO_ACCEPT / AUTO_FAIL / UNCERTAIN."""
    if all(r["verdict"] == "PASS" and r["confidence"] == "sure" for r in rows):
        return "AUTO_ACCEPT"
    if all(r["verdict"] == "FAIL" for r in rows):
        return "AUTO_FAIL"
    return "UNCERTAIN"


def prod_disputes():
    """Хвост партии: последний проход кадра с приговором; UNCERTAIN - спор, AUTO_FAIL - в residual."""
    disputes, residual = [], []
    for r in read_tsv(os.path.join(V2, "final.tsv")):
        if r["status"] != "TAIL":
            continue
        st, a = r["stage"], r["asset_id"]
        out = vj.prod_dir(st)
        with open(os.path.join(out, "key.json"), encoding=ENC) as f:
            jid = {x["asset_id"]: x for x in json.load(f)}[a]
        rows = [vj.load_answers(out, w)[jid["id"]] for w in ("claude", "codex")]
        route = judges_of(rows)
        x = {"src": "PROD", "asset_id": a, "stage": st, "piece": jid["piece"], "description": jid["description"],
             "judges": rows, "route": route}
        (disputes if route == "UNCERTAIN" else residual).append(x)
    return disputes, residual


def cal_disputes():
    """Споры калибровки V1: правда - приговор Vitali."""
    out = vj.OUT_CAL
    with open(os.path.join(out, "key.json"), encoding=ENC) as f:
        items = json.load(f)
    A, B = vj.load_answers(out, "claude"), vj.load_answers(out, "codex")
    res = []
    for x in items:
        if x["id"] not in A or x["id"] not in B:
            continue
        rows = [A[x["id"]], B[x["id"]]]
        if judges_of(rows) == "UNCERTAIN":
            res.append({"src": "CAL", "asset_id": x["asset_id"], "stage": x["stage"], "piece": x["piece"],
                        "description": x["description"], "judges": rows, "route": "UNCERTAIN",
                        "truth": x["truth"], "cal_id": x["id"], "split": x["split"]})
    return res


def do_pack():
    if os.path.exists(os.path.join(OUT, "pack.json")):
        raise SystemExit("пакет арбитра уже собран (pack.json) - не пересобираю")
    prod, residual = prod_disputes()
    cal = cal_disputes()
    items = prod + cal
    items.sort(key=lambda x: h(SALT + ":" + x["src"] + ":" + x["stage"] + ":" + x["asset_id"]))
    blind = os.path.join(OUT, "blind")
    os.makedirs(os.path.join(blind, "img"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "answers"), exist_ok=True)
    for n, x in enumerate(items, 1):
        x["id"] = "D%03d" % n
        vj.compose(vj.sprite(x["asset_id"]), x["piece"], os.path.join(blind, "img", x["id"] + ".png"))
        x["flip"] = h(SALT + ":flip:" + x["id"])[0] in "01234567"      # порядок судей в задании
    with open(os.path.join(blind, "ARBITER.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(ARBITER)
    batches = {}
    for k in range(0, len(items), BATCH):
        name = "B_%02d" % (k // BATCH + 1)
        part = items[k:k + BATCH]
        batches[name] = [x["id"] for x in part]
        lines = ["# Batch %s" % name, "", "Instructions: ARBITER.md in this folder.", ""]
        for x in part:
            js = x["judges"][::-1] if x["flip"] else x["judges"]
            lines += ["## %s: img/%s.png" % (x["id"], x["id"]),
                      "Rendered from (may be wrong): %s" % x["description"]]
            lines += ["Judge %d: %s %s%s - %s" % (i + 1, j["verdict"], j["confidence"],
                                                   (" [%s]" % j["types"]) if j["types"] else "", j["reason"])
                      for i, j in enumerate(js)]
            lines.append("")
        with open(os.path.join(blind, name + ".md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines))
    vj.dump({"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "salt": SALT, "n": len(items),
             "src": dict(Counter(x["src"] for x in items)),
             "cal_truth": dict(Counter(x["truth"] for x in cal)),
             "arbiter_md_sha256": vj.sha_file(os.path.join(blind, "ARBITER.md")), "batches": batches,
             "votes": VOTES, "rule": "PASS >=3 of 4, FAIL >=3 of 4, else UNCERTAIN"},
            os.path.join(OUT, "pack.json"))
    vj.dump(items, os.path.join(OUT, "key.json"))
    vj.dump(residual, os.path.join(OUT, "residual.json"))
    print("пакет %s: %d спорных (партия %d, калибровка %d, правда калибровки %s); residual %d; батчи %s"
          % (blind, len(items), len(prod), len(cal), dict(Counter(x["truth"] for x in cal)), len(residual),
             ", ".join(batches)))


def parse_lines(text, want):
    got = {}
    for line in text.splitlines():
        line = line.strip().strip("`")
        m = re.match(r"^(D\d{3})\s*[\t|]\s*(PASS|FAIL|UNCERTAIN)\s*[\t|]\s*(sure|unsure)\s*[\t|]\s*"
                     r"(CONFIRMED|REJECTED|UNCLEAR)\s*[\t|]?\s*(.*)$", line, re.I)
        if not m or m.group(1) not in want:
            continue
        got[m.group(1)] = {"id": m.group(1), "verdict": m.group(2).upper(), "confidence": m.group(3).lower(),
                           "claim": m.group(4).upper(), "reason": m.group(5).strip()[:240]}
    return got


def save_answers(who, ans):
    p = os.path.join(OUT, "answers", who + ".tsv")
    with open(p + ".tmp", "w", encoding=ENC, newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEAD, delimiter="\t", quoting=csv.QUOTE_NONE, lineterminator="\n")
        w.writeheader()
        for k in sorted(ans):
            w.writerow({c: ans[k].get(c, "").replace("\t", " ") for c in HEAD})
    os.replace(p + ".tmp", p)


def load_votes(who):
    d = os.path.join(OUT, "answers")
    res = {}
    for f in sorted(os.listdir(d)):
        if f.endswith(".tsv") and (f == who + ".tsv" or f.startswith(who + "_")):
            for r in read_tsv(os.path.join(d, f)):
                got = parse_lines("\t".join(r.get(c) or "" for c in HEAD), {r["id"]})
                res.update(got)
    return res


def do_codex(run, only, effort):
    with open(os.path.join(OUT, "pack.json"), encoding=ENC) as f:
        pack = json.load(f)
    blind = os.path.abspath(os.path.join(OUT, "blind"))
    if vj.sha_file(os.path.join(blind, "ARBITER.md")) != pack["arbiter_md_sha256"]:
        raise SystemExit("ARBITER.md изменён после сборки пакета")
    who = "codex_" + run
    ans = load_votes(who)
    codex = shutil.which("codex") or "codex"
    logs = os.path.join(OUT, "answers", "codex_logs")
    os.makedirs(logs, exist_ok=True)
    with open(os.path.join(blind, "ARBITER.md"), encoding="utf-8") as f:
        rules = f.read()
    for name, ids in pack["batches"].items():
        if (only and name not in only) or all(i in ans for i in ids):
            continue
        with open(os.path.join(blind, name + ".md"), encoding="utf-8") as f:
            batch = f.read()
        imgs = [os.path.join(blind, "img", i + ".png") for i in ids]
        task = (rules + "\n\n" + batch + "\nThe images are attached in this order: " +
                ", ".join("image %d = %s" % (k + 1, i) for k, i in enumerate(ids)) +
                ".\nAnswer now: exactly %d lines, one per item, as specified.\n" % len(ids))
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


def decide(votes):
    """Правило, заданное до ответов: 3 из 4 голосов."""
    c = Counter(v["verdict"] for v in votes)
    if c["PASS"] >= 3:
        return "ARBITER_PASS"
    if c["FAIL"] >= 3:
        return "ARBITER_FAIL"
    return "UNCERTAIN"


def write_tsv(p, head, rows):
    with open(p + ".tmp", "w", encoding=ENC, newline="") as f:
        w = csv.DictWriter(f, fieldnames=head, delimiter="\t", quoting=csv.QUOTE_NONE, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: str(r.get(k, "")).replace("\t", " ") for k in head})
    os.replace(p + ".tmp", p)


def do_verdict():
    import prod2_final as pf
    with open(os.path.join(OUT, "key.json"), encoding=ENC) as f:
        items = json.load(f)
    with open(os.path.join(OUT, "residual.json"), encoding=ENC) as f:
        residual = json.load(f)
    votes = {w: load_votes(w) for w in VOTES}
    miss = {w: sum(x["id"] not in votes[w] for x in items) for w in VOTES}
    if any(miss.values()):
        raise SystemExit("не хватает голосов: %s" % miss)
    rows = []
    for x in items:
        vs = [votes[w][x["id"]] for w in VOTES]
        x["arbiter"] = decide(vs)
        x["votes"] = " | ".join("%s %s %s %s: %s" % (w, v["verdict"], v["confidence"], v["claim"], v["reason"])
                                for w, v in zip(VOTES, vs))
        rows.append(x)
    write_tsv(os.path.join(OUT, "arbiter.tsv"), ["id", "src", "asset_id", "stage", "arbiter", "truth", "votes"], rows)

    # калибровка: споры V1 с приговором Vitali
    cal = [x for x in rows if x["src"] == "CAL"]
    cc = Counter((x["arbiter"], x["truth"]) for x in cal)
    single = {}
    for w in VOTES:
        c = Counter((votes[w][x["id"]]["verdict"], x["truth"]) for x in cal)
        single[w] = c

    # итог партии
    final = read_tsv(os.path.join(V2, "final.tsv"))
    arb = {x["asset_id"]: x for x in rows if x["src"] == "PROD"}
    res = {x["asset_id"] for x in residual}
    acc = sorted(r["asset_id"] for r in final if r["status"] == "ACCEPTED_BY_JUDGES")
    audit = sorted(acc, key=lambda a: h(SALT + ":audit:" + a))[:AUDIT_N]
    out_rows = []
    for r in final:
        a = r["asset_id"]
        if r["status"] == "ACCEPTED_BY_JUDGES":
            st, human = "AUTO_ACCEPT", "AUDIT" if a in audit else ""
        elif a in res:
            st, human = "AUTO_FAIL", ""
        else:
            st = arb[a]["arbiter"]
            human = "REVIEW" if st == "UNCERTAIN" else ""
        out_rows.append({"asset_id": a, "status": st, "stage": r["stage"], "human": human, "piece": r["piece"],
                         "note": arb[a]["votes"] if a in arb else r["note"]})
    write_tsv(os.path.join(V2, "final_auto.tsv"), ["asset_id", "status", "stage", "human", "piece", "note"],
              out_rows)
    by = Counter(r["status"] for r in out_rows)
    review = [r for r in out_rows if r["human"] == "REVIEW"]
    aud = [r for r in out_rows if r["human"] == "AUDIT"]
    accepted = by["AUTO_ACCEPT"] + by["ARBITER_PASS"]
    n = len(out_rows)

    pf.sheet([("%s  %s" % (r["asset_id"], r["stage"]), [pf.orig_img(r["asset_id"]),
                                                        pf.hd_img(r["stage"], r["asset_id"])]) for r in review],
             4, os.path.join(V2, "arbiter_uncertain.png"),
             "Арбитр не уверен - %d кадров Vitali: оригинал x4 | HD" % len(review))
    pf.sheet([("%s  %s" % (r["asset_id"], r["stage"]), [pf.orig_img(r["asset_id"]),
                                                        pf.hd_img(r["stage"], r["asset_id"])]) for r in aud],
             3, os.path.join(V2, "audit_sample.png"),
             "Аудит: %d случайных из %d AUTO_ACCEPT - оригинал x4 | HD" % (len(aud), by["AUTO_ACCEPT"]))
    for st, fn in (("ARBITER_PASS", "arbiter_pass.png"), ("ARBITER_FAIL", "arbiter_fail.png")):
        part = [r for r in out_rows if r["status"] == st]
        pf.sheet([("%s  %s" % (r["asset_id"], r["stage"]), [pf.orig_img(r["asset_id"]),
                                                            pf.hd_img(r["stage"], r["asset_id"])]) for r in part],
                 4, os.path.join(OUT, fn), "%s %d: оригинал x4 | HD" % (st, len(part)))

    def cnt(k, t):
        return cc[(k, t)]
    md = ["# PROD_TWO_PASS_V2 - автоматическая приёмка с финальным арбитром", "",
          "Правило (специалист 05.10): оба судьи PASS sure - AUTO_ACCEPT, оба FAIL - AUTO_FAIL (residual, человеку не "
          "идёт), спор - финальный арбитр; человеку только UNCERTAIN арбитра и выборочный аудит принятого.", "",
          "Арбитр: 4 голоса в отдельных сессиях (%s), решение 3 из 4." % ", ".join(VOTES), "",
          "## Партия (%d нарисованных кадров)" % n, "",
          "| статус | кадров |", "|---|---|"]
    md += ["| %s | %d |" % (k, by[k]) for k in ("AUTO_ACCEPT", "ARBITER_PASS", "ARBITER_FAIL", "AUTO_FAIL",
                                                  "UNCERTAIN")]
    md += ["", "Принято автоматикой: %d. Residual (AUTO_FAIL + ARBITER_FAIL): %d." % (
        accepted, by["AUTO_FAIL"] + by["ARBITER_FAIL"]), "",
        "Человеку: UNCERTAIN арбитра %d + аудит %d = %d касаний на %d нарисованных (%.0f%%), "
        "%.1f на 100 принятых." % (len(review), len(aud), len(review) + len(aud), n,
                                   100.0 * (len(review) + len(aud)) / n,
                                   100.0 * (len(review) + len(aud)) / accepted if accepted else 0), "",
        "Аудит: %s (первые %d по sha256('%s:audit:<кадр>'))." % (", ".join(audit), AUDIT_N, SALT), "",
        "## Калибровка арбитра (споры V1, приговор Vitali известен, %d кадров)" % len(cal), "",
        "| арбитр | правда PASS | правда FAIL |", "|---|---|---|"]
    md += ["| %s | %d | %d |" % (k, cnt(k, "PASS"), cnt(k, "FAIL")) for k in ("ARBITER_PASS", "ARBITER_FAIL",
                                                                              "UNCERTAIN")]
    ap = cnt("ARBITER_PASS", "PASS") + cnt("ARBITER_PASS", "FAIL")
    md += ["", "Ложный ARBITER_PASS: %d из %d принятых арбитром; брака в споре всего %d." % (
        cnt("ARBITER_PASS", "FAIL"), ap, sum(1 for x in cal if x["truth"] == "FAIL")), "",
        "Отдельные голоса (вердикт против правды):", ""]
    md += ["- %s: %s" % (w, ", ".join("%s/%s %d" % (k[0], k[1], v) for k, v in sorted(single[w].items())))
           for w in VOTES]
    md += ["", "## Кадры партии, решённые арбитром", "", "| кадр | арбитр | голоса |", "|---|---|---|"]
    md += ["| %s | %s | %s |" % (x["asset_id"], x["arbiter"], x["votes"].replace("|", "/")[:300])
           for x in rows if x["src"] == "PROD"]
    with open(os.path.join(V2, "final_auto.md"), "w", encoding=ENC, newline="\n") as f:
        f.write("\n".join(md) + "\n")
    print("\n".join(md[:40]))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["pack", "codex", "verdict"])
    ap.add_argument("--run", default="r1", choices=["r1", "r2"])
    ap.add_argument("--only", default="")
    ap.add_argument("--effort", default="high")
    a = ap.parse_args()
    os.chdir(vj.ROOT)
    random.seed(0)
    if a.cmd == "pack":
        do_pack()
    elif a.cmd == "codex":
        do_codex(a.run, set(x for x in a.only.split(",") if x), a.effort)
    else:
        do_verdict()


if __name__ == "__main__":
    main()
