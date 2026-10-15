#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Разведка: локальная Qwen3.8 27B (Ollama) как визуальный судья приёмки предметов (05.10, Vitali в чате).

Не новый судья для конвейера (специалист 05.10: «нового универсального судьи не строить»), а замер: может ли
бесплатная локальная модель хотя бы так же, как Codex и Claude, отличать годное от брака по приговору Vitali.
Последствий для конвейера у замера нет.

Честность сравнения: те же картинки (оригинал x4 | HD, тёмный и светлый пол), то же описание и тот же
замороженный JUDGE.md (visual-judge-v1/blind/JUDGE.md, sha сверяется), что видели Codex и Claude. Правила под Qwen
не правятся. Отличия только в транспорте: один кадр на запрос и ответ JSON вместо строки таблицы.
Три ответа на кадр (температура 0.2 / 0.7 / 0.7, разные seed) - один прогон модели не мера (R-231, R-143).

Наборы с приговором Vitali:
  v2 - 75 выбранных кадров листа V2 (final_select/verdicts_vitali.tsv), в подбор правил не входили;
  v1 - 111 рендеров калибровки visual-judge-v1 (DEV и TEST, TEST там уже вскрыт отчётом Codex и Claude).
Запечатанный TEST vitali-judge-v1 не трогается.

    py -3.13 tools/gpuq.py add --name qwen_judge -- py -3.13 tools/hdart/qwen_judge.py run --sets v2,v1
    py -3.13 tools/hdart/qwen_judge.py report        (без видеокарты, по готовым ответам)
"""
import argparse
import base64
import csv
import hashlib
import json
import os
import sys
import time
import urllib.request
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
ENC = "utf-8-sig"
PROBES = os.path.join(ROOT, "art", "objects", "generation", "probes")
CAL = os.path.join(PROBES, "visual-judge-v1")
V2 = os.path.join(PROBES, "prod-two-pass-v2")
OUT = os.path.join(PROBES, "qwen-judge-v1")
MODEL = "orcarouter/Qwen3.8-27B-Uncensored:q5_K_M"     # как в triage/caption.py и identity_propose.py
TYPES = ["IDENTITY", "INTERNAL_GEOMETRY", "MISSING_DETAIL", "MALFORMED_PART", "MATERIAL", "PIXEL_STEPS",
         "STRETCHED", "ALPHA"]
RUNS = ((0.2, 1), (0.7, 2), (0.7, 3))

TAIL = """
# This run

One item only (the image is attached):

- {id}: description the HD picture was rendered from (may be wrong): {desc}

Instead of the tab-separated line, answer with ONE JSON object with exactly these keys:
{{"verdict": "PASS" or "FAIL", "types": [codes for FAIL, empty for PASS], "confidence": "sure" or "unsure",
"reason": "at most 15 English words, what you saw"}}
"""


def read_tsv(path):
    with open(path, encoding=ENC, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def load_json(path):
    with open(path, encoding=ENC) as f:
        return json.load(f)


def answers_of(d, who):
    """Ответы судьи <who> пакета d (<who>.tsv и части <who>_*.tsv), как visual_judge.load_answers."""
    res = {}
    for f in sorted(os.listdir(d)):
        if f.endswith(".tsv") and (f == who + ".tsv" or f.startswith(who + "_")):
            res.update({r["id"]: r for r in read_tsv(os.path.join(d, f))})
    return res


def items_v2():
    truth = {r["asset_id"]: r for r in read_tsv(os.path.join(V2, "final_select", "verdicts_vitali.tsv"))}
    out = []
    for stage in ("RESTORE", "STRICT", "THIRD"):
        d = os.path.join(V2, "judge", stage.lower())
        key = {x["asset_id"]: x for x in load_json(os.path.join(d, "key.json"))}
        claude, codex = answers_of(os.path.join(d, "answers"), "claude"), answers_of(os.path.join(d, "answers"), "codex")
        for a, t in sorted(truth.items()):
            if t["stage"] != stage:
                continue
            x = key.get(a)
            if x is None:
                raise SystemExit("v2: нет %s в пакете %s" % (a, stage))
            out.append({"key": "v2/" + stage + "/" + a, "set": "v2", "split": stage, "asset_id": a,
                        "img": os.path.join(d, "blind", "img", x["id"] + ".png"), "desc": x["description"],
                        "truth": t["verdict"], "note": t.get("note", ""),
                        "claude": claude.get(x["id"]), "codex": codex.get(x["id"])})
    if len(out) != len(truth):
        raise SystemExit("v2: собрано %d из %d" % (len(out), len(truth)))
    return out


def items_v1():
    d = os.path.join(CAL, "answers")
    claude, codex = answers_of(d, "claude"), answers_of(d, "codex")
    return [{"key": "v1/" + x["key"], "set": "v1", "split": x["split"], "asset_id": x["asset_id"],
             "img": os.path.join(CAL, "blind", "img", x["id"] + ".png"), "desc": x["description"],
             "truth": x["truth"], "note": x.get("truth_types", ""),
             "claude": claude.get(x["id"]), "codex": codex.get(x["id"])}
            for x in load_json(os.path.join(CAL, "key.json"))]


SETS = {"v2": items_v2, "v1": items_v1}


def judge_md():
    pack = load_json(os.path.join(CAL, "pack.json"))
    p = os.path.join(CAL, "blind", "JUDGE.md")
    with open(p, "rb") as f:
        raw = f.read()
    if hashlib.sha256(raw).hexdigest() != pack["judge_md_sha256"]:
        raise SystemExit("JUDGE.md не тот, что заморожен калибровкой")
    return raw.decode("utf-8")


def normalize(r):
    v = str(r.get("verdict", "")).strip().upper()
    if v not in ("PASS", "FAIL"):
        raise ValueError("verdict %r" % r.get("verdict"))
    t = r.get("types", [])
    if isinstance(t, str):
        t = t.split(",")
    c = str(r.get("confidence", "")).strip().lower()
    return {"verdict": v, "types": [x.strip().upper() for x in t if x.strip().upper() in TYPES],
            "confidence": c if c in ("sure", "unsure") else "unsure", "reason": str(r.get("reason", ""))[:200]}


def ask(host, prompt, img, temperature, seed):
    with open(img, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    # num_ctx тот же, что у caption.py и identity_propose.py: иначе слои уходят на процессор (R-064)
    body = {"model": MODEL, "stream": False, "think": False, "format": "json",
            "options": {"temperature": temperature, "seed": seed, "num_predict": 300, "num_ctx": 4096},
            "prompt": prompt, "images": [b64]}
    req = urllib.request.Request(host + "/api/generate", json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        resp = json.loads(r.read().decode())
    return normalize(json.loads(resp["response"])), resp.get("prompt_eval_count", 0)


def load_done():
    p = os.path.join(OUT, "answers.jsonl")
    done = {}
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    r = json.loads(line)
                    done[(r["key"], r["run"])] = r
    return done


def do_run(sets, host):
    os.makedirs(OUT, exist_ok=True)
    jm = judge_md()
    items = [x for s in sets for x in SETS[s]()]
    done = load_done()
    todo = [(x, k) for x in items for k in range(len(RUNS)) if (x["key"], k) not in done]
    print("кадров %d, запросов к модели %d (готово %d)" % (len(items), len(todo), len(done)), flush=True)
    t0, errs = time.time(), 0
    with open(os.path.join(OUT, "answers.jsonl"), "a", encoding="utf-8") as f:
        for n, (x, k) in enumerate(todo, 1):
            temp, seed = RUNS[k]
            prompt = jm + TAIL.format(id="J001", desc=x["desc"])
            for attempt in range(3):
                try:
                    a, ptok = ask(host, prompt, x["img"], temp, seed + 10 * attempt)
                    break
                except (ValueError, json.JSONDecodeError) as e:
                    a, ptok = None, 0
                    print("  %s run %d: плохой ответ (%s), повтор" % (x["key"], k, e), flush=True)
            if a is None:
                errs += 1
                continue
            f.write(json.dumps(dict(a, key=x["key"], run=k, prompt_tokens=ptok), ensure_ascii=False) + "\n")
            f.flush()
            if n == 1:
                print("  первый ответ: %s, токенов запроса %d" % (a, ptok), flush=True)
            if n % 25 == 0 or n == len(todo):
                el = time.time() - t0
                print("%d/%d, %.1f с/запрос, осталось ~%.0f мин, ошибок %d" % (
                    n, len(todo), el / n, el / n * (len(todo) - n) / 60, errs), flush=True)
    do_report(sets)


def vote(rs):
    """Большинство трёх ответов: PASS, если PASS у двух из трёх; sure - если все PASS и все sure."""
    p = sum(r["verdict"] == "PASS" for r in rs)
    return {"maj": "PASS" if p * 2 > len(rs) else "FAIL",
            "all_sure_pass": len(rs) == 3 and all(r["verdict"] == "PASS" and r["confidence"] == "sure" for r in rs),
            "stable": p in (0, len(rs))}


def row(name, items, acc):
    """acc(x) -> True (принял) / False / None (нет ответа). Ложный PASS - доля брака Vitali среди принятых."""
    c = Counter()
    for x in items:
        a = acc(x)
        if a is None:
            c["miss"] += 1
            continue
        c[(a, x["truth"])] += 1
    good = c[(True, "PASS")] + c[(False, "PASS")]
    bad = c[(True, "FAIL")] + c[(False, "FAIL")]
    acc_n = c[(True, "PASS")] + c[(True, "FAIL")]
    return "| %s | %d | %d | %d | %s | %d/%d | %d/%d |" % (
        name, len(items) - c["miss"], acc_n, c[(True, "FAIL")],
        "%.0f%%" % (100 * c[(True, "FAIL")] / acc_n) if acc_n else "-",
        c[(True, "PASS")], good, c[(False, "FAIL")], bad)


def do_report(sets):
    done = load_done()
    md = ["# Qwen3.8 27B как визуальный судья - разведка", "",
          "Модель %s, JUDGE.md калибровки без правок, три ответа на кадр (t 0.2/0.7/0.7). "
          "Правда - приговор Vitali. Принял брак - судья PASS, Vitali FAIL." % MODEL, ""]
    for s in sets:
        items = SETS[s]()
        q = {x["key"]: [done[(x["key"], k)] for k in range(len(RUNS)) if (x["key"], k) in done] for x in items}
        full = [x for x in items if len(q[x["key"]]) == len(RUNS)]
        v = {x["key"]: vote(q[x["key"]]) for x in full}
        for split in sorted(set(x["split"] for x in full)) + ["ALL"]:
            part = [x for x in full if split == "ALL" or x["split"] == split]
            if split != "ALL" and s == "v2":
                continue                       # у v2 части - проходы, отдельно не интересны
            md += ["## %s / %s: %d кадров, правда %s" % (s, split, len(part), dict(Counter(x["truth"] for x in part))),
                   "", "| судья | ответов | принял | из них брак | доля брака в принятом | годных принял | брака поймал |",
                   "|---|---|---|---|---|---|---|"]
            for k in range(len(RUNS)):
                md.append(row("qwen ответ %d" % (k + 1), part, lambda x, k=k: q[x["key"]][k]["verdict"] == "PASS"))
            md.append(row("qwen большинство 2/3", part, lambda x: v[x["key"]]["maj"] == "PASS"))
            md.append(row("qwen все 3 PASS sure", part, lambda x: v[x["key"]]["all_sure_pass"]))
            md.append(row("claude", part, lambda x: None if not x["claude"] else x["claude"]["verdict"] == "PASS"))
            md.append(row("codex", part, lambda x: None if not x["codex"] else x["codex"]["verdict"] == "PASS"))
            both = lambda x: None if not (x["claude"] and x["codex"]) else all(
                y["verdict"] == "PASS" and y["confidence"] == "sure" for y in (x["claude"], x["codex"]))
            md.append(row("claude+codex оба PASS sure", part, both))
            md.append(row("claude+codex+qwen(все 3 sure)", part,
                          lambda x: None if both(x) is None else both(x) and v[x["key"]]["all_sure_pass"]))
            st = sum(v[x["key"]]["stable"] for x in part)
            md += ["", "Три ответа Qwen совпали: %d из %d кадров." % (st, len(part)), ""]
        bad = [x for x in full if v[x["key"]]["maj"] == "PASS" and x["truth"] == "FAIL"]
        if bad:
            md += ["### %s: брак, принятый большинством Qwen" % s, ""] + [
                "- %s: «%s»; Vitali: %s" % (x["key"], q[x["key"]][0]["reason"], (x["note"] or "-")[:90]) for x in bad] + [""]
        ptok = [r["prompt_tokens"] for r in done.values() if r["key"].startswith(s + "/")]
        if ptok:
            md += ["Токенов запроса: %d-%d (num_ctx 4096)." % (min(ptok), max(ptok)), ""]
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, "report.md")
    with open(p, "w", encoding=ENC) as f:
        f.write("\n".join(md) + "\n")
    print("\n".join(md))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["run", "report"])
    ap.add_argument("--sets", default="v2,v1")
    ap.add_argument("--host", default="http://127.0.0.1:11434")
    a = ap.parse_args()
    sets = [s for s in a.sets.split(",") if s]
    for s in sets:
        if s not in SETS:
            raise SystemExit("набор %s неизвестен" % s)
    if a.cmd == "run":
        do_run(sets, a.host)
    else:
        do_report(sets)


if __name__ == "__main__":
    main()
