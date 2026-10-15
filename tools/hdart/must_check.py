"""MUST_PRESERVE_PROBE_V1 (специалист 05.10): ловит ли проверка обязательных деталей пропажу детали
на готовом кадре и сколько годных она трогает. Только замер на PROD_TWO_PASS_V2, в V3 не встроено.

Данные - финальный выбор V2 с приговором Vitali (final_select/verdicts_vitali.tsv):
  годные - 61 PASS; брак с пропавшей деталью - 9 FAIL, у которых перерисовка (retry/descriptions.tsv) группы DETAIL
  или надпись на предмете (INDUSLUM:46). Описание кадра - то, по которому он рисовался: THIRD - third/descriptions.tsv,
  остальное - descriptions.tsv (как visual_judge.labelled).

Два вопроса порознь:
  A. извлечение: попадает ли деталь, которую назвал Vitali, в список, извлечённый из описания (Codex, один прогон,
     только текст): must_auto против must_known у 9 брака;
  B. проверка: деталь X есть на картинке B? YES / NO / UNSURE, три отдельных прогона Codex, довод - большинство (R-231).
     Кадр помечен, если хоть одна деталь получила NO у двух из трёх. Мерки: брак пойман (из 9, по must_known и по
     must_auto) и годных тронуто (из 61, по must_auto). UNSURE ничего не решает (R-235).

    py -3.13 tools/hdart/must_check.py pack            кадры, картинки, пакет извлечения
    py -3.13 tools/hdart/must_check.py extract         Codex: must_auto из описаний
    py -3.13 tools/hdart/must_check.py check-pack      пакет проверки (must_auto всем, must_known браку)
    py -3.13 tools/hdart/must_check.py check --run 1   Codex, прогон 1 (2, 3 - отдельными сессиями)
    py -3.13 tools/hdart/must_check.py report
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import visual_judge as vj      # noqa: E402

ENC = "utf-8-sig"
V2 = vj.V2
OUT = os.path.join(vj.PROBES, "must-preserve-v2")
BAD_GROUPS = ("DETAIL",)
BAD_EXTRA = ("INDUSLUM:46",)       # надпись TOP SECRET XCOM - текст на предмете, тоже обязательная деталь
EX_BATCH = 20
CK_BATCH = 10
MAX_MUST = 4

EXTRACT = """# Extract must-preserve details

Each item below is a text description of a small game object that a picture was rendered from. List the details
that the final picture MUST keep to still be this object, but only of these kinds:

* exact counts of doors, drawers, shelves, rungs, steps, rods, legs, wheels, bars;
* text, labels, letters, signs written on the object;
* broken, damaged or missing parts the description states (missing door, broken leg, torn, worn through);
* distinctive decorations (ruffles, knobs, carved face, skull, emblem);
* visible wear (rust, scratches, worn patches);
* protruding parts that define the shape (narrow neck, spout, antenna, handle, horns).

Rules: only what the description itself states, never invent; general shape, colour and material are NOT details
(do not list "wooden", "brown", "rectangular"); at most 4 details, each at most 10 English words, concrete and
checkable on a picture; if the description has no such detail, answer NONE.

Answer one line per item, fields separated by TAB, details separated by " ; ":

    id<TAB>detail 1 ; detail 2 ; ...      or      id<TAB>NONE

Output only the lines.
"""

CHECK = """# Check must-preserve details

Each image shows the same game object twice: A (left) - the original pixel art enlarged, B (right) - the new HD
picture; top row on dark, bottom row on light background. For every item you get a numbered list of details.
For EACH detail decide whether it is present in picture B:

* YES - the detail is clearly visible in B (for a count: B shows exactly that number);
* NO - the detail is clearly absent in B, or B shows a different count, or it is clearly a different thing;
* UNSURE - B is too small or ambiguous to tell.

Judge B only; A is just a reference for where to look. Do not judge style, colour or overall quality - only the
listed details. Answer one line per detail, fields separated by TAB:

    item id<TAB>detail number<TAB>YES|NO|UNSURE<TAB>reason (at most 12 English words)

Output only the lines.
"""


def read_tsv(p):
    return vj.read_tsv(p)


def dump(o, p):
    vj.dump(o, p)


def load(p):
    with open(p, encoding=ENC) as f:
        return json.load(f)


def items_v2():
    desc = {r["asset_id"]: r["description"] for r in read_tsv(os.path.join(V2, "descriptions.tsv"))}
    third = {r["asset_id"]: r["what_en"] for r in read_tsv(os.path.join(V2, "third", "descriptions.tsv"))}
    retry = {r["asset_id"]: r for r in read_tsv(os.path.join(V2, "retry", "descriptions.tsv"))}
    out = []
    for r in read_tsv(os.path.join(V2, "final_select", "verdicts_vitali.tsv")):
        a, v = r["asset_id"], r["verdict"]
        if v == "PASS":
            kind = "GOOD"
        elif v == "FAIL" and a in retry and (retry[a]["group"] in BAD_GROUPS or a in BAD_EXTRA):
            kind = "BAD"
        else:
            continue
        text = (third.get(a) or desc.get(a)) if r["stage"] == "THIRD" else desc.get(a)
        if not text or not os.path.exists(r["piece"]):
            raise SystemExit("нет описания или кадра: %s %s" % (a, r["stage"]))
        out.append({"asset_id": a, "kind": kind, "stage": r["stage"], "piece": r["piece"], "description": text,
                    "must_known": retry[a]["must"] if kind == "BAD" else "", "vitali_note": r.get("note", "")})
    return out


def do_pack():
    if os.path.exists(os.path.join(OUT, "items.json")):
        raise SystemExit("пакет уже собран (items.json) - не пересобираю")
    items = items_v2()
    items.sort(key=lambda x: vj.h("must-preserve-v2:" + x["asset_id"]))
    blind = os.path.join(OUT, "blind")
    os.makedirs(os.path.join(blind, "img"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "answers"), exist_ok=True)
    for n, x in enumerate(items, 1):
        x["id"] = "M%03d" % n
        vj.compose(vj.sprite(x["asset_id"]), x["piece"], os.path.join(blind, "img", x["id"] + ".png"))
    with open(os.path.join(blind, "EXTRACT.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(EXTRACT)
    with open(os.path.join(blind, "CHECK.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(CHECK)
    dump(items, os.path.join(OUT, "items.json"))     # правда (kind) - вне blind/
    print("кадров %d: %s" % (len(items), dict(Counter(x["kind"] for x in items))))


def codex_run(task, imgs, logname, effort="medium"):
    codex = shutil.which("codex") or "codex"
    logs = os.path.join(OUT, "answers", "logs")
    os.makedirs(logs, exist_ok=True)
    blind = os.path.abspath(os.path.join(OUT, "blind"))
    last = os.path.abspath(os.path.join(logs, logname + ".last.txt"))
    cmd = [codex, "exec", "--skip-git-repo-check", "--sandbox", "read-only", "-C", blind, "--color", "never",
           "-c", "model_reasoning_effort=" + effort, "-o", last] + sum([["-i", q] for q in imgs], []) + ["-"]
    t0 = time.time()
    with open(os.path.join(logs, logname + ".log"), "w", encoding="utf-8") as lf:     # задание через stdin (R-222)
        rc = subprocess.run(cmd, cwd=blind, stdout=lf, stderr=subprocess.STDOUT, input=task.encode("utf-8"),
                            timeout=40 * 60).returncode
    text = open(last, encoding="utf-8", errors="replace").read() if os.path.exists(last) else ""
    return rc, text, time.time() - t0


def do_extract():
    items = load(os.path.join(OUT, "items.json"))
    p = os.path.join(OUT, "must_auto.json")
    got = load(p) if os.path.exists(p) else {}
    for k in range(0, len(items), EX_BATCH):
        part = [x for x in items[k:k + EX_BATCH] if x["id"] not in got]
        if not part:
            continue
        task = EXTRACT + "\n" + "\n".join("- %s: %s" % (x["id"], x["description"]) for x in part) + \
            "\n\nAnswer now: exactly %d lines.\n" % len(part)
        rc, text, dt = codex_run(task, [], "extract_%02d" % (k // EX_BATCH + 1))
        want, n = {x["id"] for x in part}, 0
        for line in text.splitlines():
            f = line.strip().strip("`").split("\t")
            if len(f) >= 2 and f[0].strip() in want:
                v = f[1].strip()
                got[f[0].strip()] = [] if v.upper() == "NONE" else [d.strip() for d in v.split(";") if d.strip()][:MAX_MUST]
                n += 1
        dump(got, p)
        print("извлечение %d: код %d, %.0f с, ответов %d из %d" % (k // EX_BATCH + 1, rc, dt, n, len(part)), flush=True)
    print("с деталями %d из %d" % (sum(1 for v in got.values() if v), len(got)))


def do_check_pack():
    items = load(os.path.join(OUT, "items.json"))
    auto = load(os.path.join(OUT, "must_auto.json"))
    if len(auto) != len(items):
        raise SystemExit("извлечение не закончено: %d из %d" % (len(auto), len(items)))
    checks = []        # (проверочный id, кадр, список деталей, откуда)
    for x in items:
        if auto[x["id"]]:
            checks.append({"cid": x["id"] + "a", "id": x["id"], "src": "auto", "must": auto[x["id"]]})
        if x["kind"] == "BAD":
            checks.append({"cid": x["id"] + "k", "id": x["id"], "src": "known",
                           "must": [d.strip() for d in x["must_known"].split(";") if d.strip()]})
    checks.sort(key=lambda c: vj.h("must-preserve-v2-check:" + c["cid"]))
    batches = {}
    for k in range(0, len(checks), CK_BATCH):
        batches["C%02d" % (k // CK_BATCH + 1)] = [c["cid"] for c in checks[k:k + CK_BATCH]]
    dump({"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "check_md_sha256": vj.sha_file(
        os.path.join(OUT, "blind", "CHECK.md")), "checks": checks, "batches": batches},
        os.path.join(OUT, "check_pack.json"))
    print("проверок %d (%s), батчи %s" % (len(checks), dict(Counter(c["src"] for c in checks)), ", ".join(batches)))


def do_check(run):
    pack = load(os.path.join(OUT, "check_pack.json"))
    if vj.sha_file(os.path.join(OUT, "blind", "CHECK.md")) != pack["check_md_sha256"]:
        raise SystemExit("CHECK.md изменён после сборки пакета")
    by = {c["cid"]: c for c in pack["checks"]}
    p = os.path.join(OUT, "answers", "run%d.json" % run)
    got = load(p) if os.path.exists(p) else {}
    for name, cids in pack["batches"].items():
        want = {"%s:%d" % (c, n) for c in cids for n in range(1, len(by[c]["must"]) + 1)}
        if want <= set(got):
            continue
        lines, imgs = [], []
        for k, c in enumerate(cids, 1):
            x = by[c]
            imgs.append(os.path.join(OUT, "blind", "img", x["id"] + ".png"))
            lines.append("## %s (image %d)" % (c, k))
            lines += ["%d. %s" % (n, d) for n, d in enumerate(x["must"], 1)]
            lines.append("")
        task = CHECK + "\n" + "\n".join(lines) + "\nAnswer now: exactly %d lines, one per detail.\n" % len(want)
        rc, text, dt = codex_run(task, imgs, "run%d_%s" % (run, name))
        n = 0
        for line in text.splitlines():
            m = re.match(r"^\s*`?(M\d{3}[ak])\s*[\t|]\s*(\d+)\s*[\t|]\s*(YES|NO|UNSURE)\s*[\t|]?\s*(.*)$", line, re.I)
            if m and "%s:%s" % (m.group(1), m.group(2)) in want:
                got["%s:%s" % (m.group(1), m.group(2))] = [m.group(3).upper(), m.group(4).strip()[:160]]
                n += 1
        dump(got, p)
        print("прогон %d %s: код %d, %.0f с, ответов %d из %d" % (run, name, rc, dt, n, len(want)), flush=True)


def do_report():
    items = {x["id"]: x for x in load(os.path.join(OUT, "items.json"))}
    pack = load(os.path.join(OUT, "check_pack.json"))
    runs = [load(os.path.join(OUT, "answers", "run%d.json" % r)) for r in (1, 2, 3)
            if os.path.exists(os.path.join(OUT, "answers", "run%d.json" % r))]
    if len(runs) < 3:
        raise SystemExit("нужны три прогона, есть %d" % len(runs))
    res, lines = {}, []
    for c in pack["checks"]:
        dets = []
        for n, d in enumerate(c["must"], 1):
            k = "%s:%d" % (c["cid"], n)
            votes = [r.get(k, ["", ""])[0] for r in runs]
            maj = next((v for v in ("NO", "YES", "UNSURE") if votes.count(v) >= 2), "SPLIT")
            dets.append((d, maj, votes))
        res[c["cid"]] = dets
    out = {"auto_good_flagged": [], "auto_bad_caught": [], "known_bad_caught": []}
    n_good = sum(1 for x in items.values() if x["kind"] == "GOOD")
    n_bad = sum(1 for x in items.values() if x["kind"] == "BAD")
    for c in pack["checks"]:
        x = items[c["id"]]
        flag = any(m == "NO" for _, m, _ in res[c["cid"]])
        if not flag:
            continue
        key = ("auto_good_flagged" if x["kind"] == "GOOD" else "auto_bad_caught") if c["src"] == "auto" \
            else "known_bad_caught"
        out[key].append(x["asset_id"])
    summary = {"good": n_good, "bad": n_bad,
               "good_with_auto_must": sum(1 for c in pack["checks"] if c["src"] == "auto" and items[c["id"]]["kind"] == "GOOD"),
               "bad_with_auto_must": sum(1 for c in pack["checks"] if c["src"] == "auto" and items[c["id"]]["kind"] == "BAD"),
               "good_flagged": len(out["auto_good_flagged"]), "bad_caught_known": len(out["known_bad_caught"]),
               "bad_caught_auto": len(out["auto_bad_caught"])}
    dump({"summary": summary, "lists": out,
          "details": {c: [{"detail": d, "majority": m, "votes": v} for d, m, v in r] for c, r in res.items()}},
         os.path.join(OUT, "report.json"))
    auto = load(os.path.join(OUT, "must_auto.json"))
    lines = ["# MUST_PRESERVE_PROBE_V1 на PROD_TWO_PASS_V2", "",
             "- годных %d, с извлечёнными деталями %d; помечено (NO у 2 из 3 хоть по одной детали): **%d**" % (
                 n_good, summary["good_with_auto_must"], summary["good_flagged"]),
             "- брака с пропавшей деталью %d: пойман по деталям Vitali **%d**, по извлечённым из описания %d "
             "(деталей извлечено у %d)" % (n_bad, summary["bad_caught_known"], summary["bad_caught_auto"],
                                           summary["bad_with_auto_must"]), "",
             "## Брак: деталь Vitali против извлечённого", "",
             "| кадр | Vitali (must_known) | извлечено из описания | по must_known | по must_auto |", "|---|---|---|---|---|"]
    for x in sorted(items.values(), key=lambda y: y["asset_id"]):
        if x["kind"] != "BAD":
            continue
        k = res.get(x["id"] + "k", [])
        a = res.get(x["id"] + "a", [])
        lines.append("| %s | %s | %s | %s | %s |" % (
            x["asset_id"], x["must_known"], " ; ".join(auto.get(x["id"], [])) or "NONE",
            ", ".join("%s=%s" % (d, m) for d, m, _ in k), ", ".join("%s=%s" % (d, m) for d, m, _ in a) or "-"))
    lines += ["", "## Годные, помеченные проверкой", "", "| кадр | деталь | голоса |", "|---|---|---|"]
    for x in sorted(items.values(), key=lambda y: y["asset_id"]):
        if x["kind"] == "GOOD":
            for d, m, v in res.get(x["id"] + "a", []):
                if m == "NO":
                    lines.append("| %s | %s | %s |" % (x["asset_id"], d, "/".join(v)))
    with open(os.path.join(OUT, "report.md"), "w", encoding=ENC) as f:
        f.write("\n".join(lines) + "\n")
    print(json.dumps(summary, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["pack", "extract", "check-pack", "check", "report"])
    ap.add_argument("--run", type=int, default=1)
    a = ap.parse_args()
    os.chdir(vj.ROOT)
    {"pack": do_pack, "extract": do_extract, "check-pack": do_check_pack, "report": do_report}.get(
        a.cmd, lambda: do_check(a.run))()


if __name__ == "__main__":
    main()
