#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Разметка правды контрольной сотни руками Codex (P1-C), вместо человека - по слову Vitali 30.09.

Вход ровно тот, что на листе truth_sheet.py: страницы PNG и текст карточек. Слепота держится так:
  * Codex запускается в пустой рабочей папке вне репозитория (в дереве лежат ответы арбитра -
    answers.json, report.md - и ключ карточек key.json);
  * в запросе запрет запускать команды и открывать файлы: всё нужное приложено;
  * после прогона журнал проверяется на команды и на упоминания запретных файлов - нашлось, ответ не принят.
Ответ - по JSON-схеме, пачками по 25 карточек (5 страниц).

    py -3.13 tools/hdart/truth_codex.py <снимок.json> [--effort high] [--batches 1,2]
    -> <снимок>/truth_sheet/codex/answers_codex.tsv, затем
    py -3.13 tools/hdart/truth_sheet.py import <снимок.json> <...>/answers_codex.tsv --who codex
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import arbiter as ar                                   # noqa: E402
import truth_sheet as ts                               # noqa: E402

ENC = "utf-8-sig"
BATCH = 25
FORBIDDEN = ("answers.json", "report.md", "report.json", "key.json", "summary.txt", "run.json",
             "identity", "proposals", "arbiter.py", "truth.tsv")

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["labels"],
    "properties": {"labels": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["card", "truth", "note"],
        "properties": {"card": {"type": "integer"},
                       "truth": {"type": "string", "enum": list(ar.TRUTHS)},
                       "note": {"type": "string"}}}}}}

ASK = """Ты размечаешь правду для проверки другой модели (арбитра). Ниже инструкция разметчика, затем текст
карточек {lo}..{hi}; приложены листы PNG с этими карточками (номер карточки крупно слева на листе).

Правила этой работы:
- не запускай никаких команд и не открывай файлы: всё нужное - в приложенных картинках и в тексте ниже;
- смотри на кадр, место на карте (предмет в красной рамке) и данные движка, а не на то, какое название звучит лучше;
- ответ арбитра тебе неизвестен и не нужен; порядок A/B - по алфавиту и ничего не значит;
- по каждой карточке {lo}..{hi} ровно одна метка; у NEITHER в note - что это на самом деле (коротко, по-английски);
  у остальных note - одна короткая фраза, почему (можно пусто);
- если по карточке честно нельзя решить - CANNOT_TELL, это лучше угадывания.

<инструкция>
{instr}
</инструкция>

<карточки>
{cards}
</карточки>
"""


def batches(n, size=BATCH):
    return [(lo, min(lo + size - 1, n)) for lo in range(1, n + 1, size)]


def pages_for(up, lo, hi):
    out = []
    for fn in sorted(os.listdir(up)):
        m = re.match(r"page_\d+_cards_(\d+)-(\d+)\.png$", fn)
        if m and int(m.group(1)) <= hi and int(m.group(2)) >= lo:
            out.append(os.path.join(up, fn))
    return out


def audit(log_text):
    """Команды в журнале и упоминания запретных файлов. Пусто - прогон слепой."""
    bad = []
    for line in log_text.splitlines():
        low = line.lower()
        if re.match(r"^\s*(exec|\$ |running|shell)\b", low) or "command:" in low:
            bad.append(line.strip()[:160])
        elif any(f in low for f in FORBIDDEN):
            bad.append(line.strip()[:160])
    return bad


def run_batch(k, lo, hi, up, cards_text, instr, out_dir, effort, codex):
    work = tempfile.mkdtemp(prefix="truth_codex_")          # пустая папка вне репозитория
    try:
        schema_p = os.path.join(out_dir, "schema.json")
        res_p = os.path.join(out_dir, "batch_%d.json" % k)
        log_p = os.path.join(out_dir, "batch_%d.log" % k)
        prompt = ASK.format(lo=lo, hi=hi, instr=instr, cards=cards_text)
        with open(os.path.join(out_dir, "batch_%d.prompt.txt" % k), "w", encoding=ENC) as f:
            f.write(prompt)
        cmd = [codex, "exec", "--sandbox", "read-only", "-C", work, "--skip-git-repo-check", "--color", "never",
               "-c", "model_reasoning_effort=" + effort, "--output-schema", schema_p, "-o", res_p]
        for p in pages_for(up, lo, hi):
            cmd += ["-i", p]
        cmd.append("-")
        r = subprocess.run(cmd, input=prompt.encode("utf-8"), capture_output=True, cwd=work, timeout=60 * 60)
        log = (r.stdout + r.stderr).decode("utf-8", "replace")
        with open(log_p, "w", encoding=ENC) as f:
            f.write(log)
        return k, lo, hi, r.returncode, res_p, log
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("snapshot")
    ap.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh"])
    ap.add_argument("--batches", default="", help="номера пачек через запятую (1..4); пусто - все")
    ap.add_argument("--parallel", type=int, default=2)
    a = ap.parse_args()
    codex = shutil.which("codex")
    if not codex:
        raise SystemExit("codex не найден в PATH")
    snap, d = ar.check_snapshot(a.snapshot)
    sheet = os.path.abspath(os.path.join(d, "truth_sheet"))   # Codex идёт из пустой папки - пути только полные
    up = os.path.join(sheet, "upload")
    with open(os.path.join(sheet, "key.json"), encoding=ENC) as f:
        key = json.load(f)
    if (key["snapshot_id"], key["items_hash"]) != (snap["snapshot_id"], snap["items_hash"]):
        raise SystemExit("лист от другого снимка: truth_sheet.py make")
    items = ts.items_in_order(snap)
    with open(os.path.join(up, "INSTRUCTIONS.md"), encoding=ENC) as f:
        instr = f.read()
    out_dir = os.path.join(sheet, "codex")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "schema.json"), "w", encoding="utf-8") as f:
        json.dump(SCHEMA, f)
    plan = list(enumerate(batches(len(items)), 1))
    if a.batches:
        want = {int(x) for x in a.batches.split(",")}
        plan = [p for p in plan if p[0] in want]
    jobs = []
    for k, (lo, hi) in plan:
        text = "\n".join(ts.card_text(i, items[i - 1]) for i in range(lo, hi + 1))
        jobs.append((k, lo, hi, up, text, instr, out_dir, a.effort, codex))
    print("пачек %d, глубина %s, параллельно %d" % (len(jobs), a.effort, a.parallel), flush=True)
    with ThreadPoolExecutor(a.parallel) as ex:
        results = list(ex.map(lambda j: run_batch(*j), jobs))
    ok = True
    for k, lo, hi, code, res_p, log in results:
        bad = audit(log)
        got = {}
        if os.path.exists(res_p):
            try:
                with open(res_p, encoding=ENC) as f:
                    got = {int(x["card"]): x for x in json.load(f)["labels"]}
            except (ValueError, KeyError) as e:
                print("пачка %d: ответ не по схеме: %s" % (k, e))
        miss = [c for c in range(lo, hi + 1) if c not in got]
        extra = [c for c in got if not lo <= c <= hi]
        state = "ok" if code == 0 and not bad and not miss and not extra else "НЕ ПРИНЯТА"
        print("пачка %d (%d..%d): код %s, меток %d, нет %s, лишние %s, подозрительных строк журнала %d - %s" % (
            k, lo, hi, code, len(got), miss, extra, len(bad), state))
        for line in bad[:10]:
            print("   журнал: " + line)
        ok &= state == "ok"
    # сводный ответ из всех пачек, что лежат на диске (перезапуск одной пачки не теряет остальные)
    rows = {}
    for k, (lo, hi) in enumerate(batches(len(items)), 1):
        p = os.path.join(out_dir, "batch_%d.json" % k)
        if os.path.exists(p):
            with open(p, encoding=ENC) as f:
                for x in json.load(f)["labels"]:
                    if lo <= int(x["card"]) <= hi:
                        rows[int(x["card"])] = x
    tsv = os.path.join(out_dir, "answers_codex.tsv")
    with open(tsv, "w", encoding=ENC, newline="") as f:
        f.write("card\ttruth\tnote\n")
        for c in sorted(rows):
            f.write("%d\t%s\t%s\n" % (c, rows[c]["truth"], " ".join(rows[c]["note"].split())))
    print("сводный ответ: %d из %d -> %s" % (len(rows), len(items), tsv))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
