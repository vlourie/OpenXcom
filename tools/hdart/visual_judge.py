#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Визуальный судья приёмки предметов (PROD_TWO_PASS_V2, специалист 05.10, передал Vitali в чате).

V2 должен идти без человека на каждом кадре: RESTORE -> STRICT для FAIL -> пересмотр опознания -> THIRD, человеку
только хвост. Решать «FAIL -> STRICT» и «принять» должен кто-то вместо Vitali. Машинный итог (photo_accept +
asset_fidelity) для этого не годится: на V1 из 37 машинных PASS глаз Vitali забраковал 17 (R-210). Поэтому сначала
калибровка: судьи-модели вслепую судят 111 рендеров V1, у которых есть приговор Vitali и типы брака
(RESTORE 60, STRICT 33, THIRD 18), и считается главное - ЛОЖНЫЙ PASS (судья принял, Vitali забраковал).

Судьи независимые, разных семейств: Codex (GPT, codex exec read-only с картинками) и агент Claude (читает картинки
пакета). Видят одно и то же: оригинал 32x40 x4 nearest и HD-рендер рядом, на тёмном и на светлом, и описание,
по которому рисовали (оно само может быть неверным). Ни приговора, ни прохода, ни имени набора в пакете нет.

Раздел DEV (треть по хэшу) - на нём можно править JUDGE.md; TEST замораживается вместе с JUDGE.md до первого
ответа на нём (sha256 в pack.json), приговор судье - только по TEST.

    py -3.13 tools/hdart/visual_judge.py calib                    пакет калибровки (CPU)
    py -3.13 tools/hdart/visual_judge.py codex --split DEV        ответы Codex по пакетам раздела (без видеокарты)
    py -3.13 tools/hdart/visual_judge.py report                   метрики каждого судьи и связки судей
Ответ судьи - <pack>/answers/<кто>.tsv: id, verdict (PASS / FAIL), types, confidence (sure / unsure), reason.
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
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
ROOT = os.path.dirname(os.path.dirname(HERE))

ENC = "utf-8-sig"
PROBES = os.path.join("art", "objects", "generation", "probes")
V1 = os.path.join(PROBES, "prod-two-pass-v1")
OUT_CAL = os.path.join(PROBES, "visual-judge-v1")
SALT = "visual-judge-v1"
BATCH = 12
DARK, LIGHT = (28, 26, 24, 255), (205, 205, 205, 255)
TYPES = ["IDENTITY", "INTERNAL_GEOMETRY", "MISSING_DETAIL", "MALFORMED_PART", "MATERIAL", "PIXEL_STEPS",
         "STRETCHED", "ALPHA"]
HEAD = ["id", "verdict", "types", "confidence", "reason"]

JUDGE = """# Visual acceptance judge

You judge HD replacement pictures for objects of an old isometric tactical game (X-COM style, X-Piratez mod).
Each item is ONE image `img/<id>.png` with two columns:

* **A (left)** - the original game sprite, 32x40 pixel art, enlarged x4 without smoothing. This is the truth:
  what the object is, which parts it has and where they are, its colours and materials.
* **B (right)** - the new HD picture that should replace A in the game, same size and position.

Top row on a dark floor, bottom row the same pictures on a light floor (to see holes and halos).
Each item also has the text description the HD picture was rendered from. The description MAY BE WRONG:
judge B against A, not against the text.

The owner is a picky art director: he rejected more than half of such pictures, mostly ones that looked
"roughly the same object" at a glance. Judge in two steps, for every item:

1. **Same object.** List to yourself the parts you see in A (body, legs, doors, shelves, screens, items on
   top, handles...) with their count and place. Find each of them in B. Any part missing, added, moved,
   multiplied or replaced by something else - FAIL.
2. **Every part is good.** Now look at B alone, part by part, as a finished game picture. Every part must
   read as a recognisable, well-formed real thing. FAIL if any part is a shapeless blob or abstract lump,
   melted or fused with a neighbour, smeared, patchy or noisy, has a strange texture that does not belong
   to its material, or if you cannot tell what a part is. Small things matter: objects on a table, handles,
   blades, screens, legs.

PASS only if both steps find nothing. If you hesitate on any part - FAIL. A PASS must be "sure".

FAIL reasons (use the codes, several allowed):

| code | meaning |
|---|---|
| IDENTITY | B shows a different object or a different kind of object than A (e.g. A a roll of cloth, B a crate) |
| INTERNAL_GEOMETRY | the inner structure differs: number or position of shelves, drawers, legs, panels, doors, screens, steps |
| MISSING_DETAIL | a distinct detail clearly visible in A is gone in B |
| MALFORMED_PART | a part of B is warped, melted, broken, fused, illogical, or looks like a different part |
| MATERIAL | colour regions, material or lighting differ from A (grey where A is coloured, wood where A is metal, translucent, purple cast) |
| PIXEL_STEPS | B still looks like pixel art: stair-stepped edges, cubes, blocky texture, or almost unchanged from A |
| STRETCHED | proportions of the object or a part are distorted, a part stretched or squashed |
| ALPHA | holes in the body, background remnants, coloured halo around the edge |

Answer for EVERY item of the batch, one line per item, tab-separated, in this order of fields:

    id<TAB>verdict<TAB>types<TAB>confidence<TAB>reason

* verdict: PASS or FAIL
* types: comma-separated codes for FAIL, empty for PASS
* confidence: sure or unsure
* reason: at most 15 English words, what you saw

Look at every image yourself. Do not open any file outside this folder. Output only the lines, no table, no header.
"""


def h(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def sha_file(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def read_tsv(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding=ENC, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def dump(obj, path):
    with open(path + ".tmp", "w", encoding=ENC) as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(path + ".tmp", path)


_W = None


def sprite(key):
    import numpy as np
    global _W
    if _W is None:
        import map_mockup as mm
        _W = mm.World()
    s, f = key.split(":")
    im = _W.sprite(s.lower(), int(f), None)
    if im is None:
        raise SystemExit("нет кадра %s" % key)
    return np.asarray(im.convert("RGBA"), np.uint8)


def piece_of(stage, aid):
    s, f = aid.split(":")
    sub = {"RESTORE": "render", "STRICT": os.path.join("strict", "series"),
           "THIRD": os.path.join("third", "strict", "series")}[stage]
    return os.path.join(V1, sub, s + ".PCK", f + ".png")


def labelled():
    """Приговоры Vitali по трём проходам V1 и описание, по которому рисовали."""
    desc = {r["asset_id"]: r["description"] for r in read_tsv(os.path.join(V1, "descriptions.tsv"))}
    third = {r["asset_id"]: r["what_en"] for r in read_tsv(os.path.join(V1, "third", "descriptions.tsv"))}
    out = []
    for stage, tsv in (("RESTORE", "verdicts_vitali.tsv"), ("STRICT", os.path.join("strict", "verdicts_vitali.tsv")),
                       ("THIRD", os.path.join("third", "verdicts_vitali.tsv"))):
        for r in read_tsv(os.path.join(V1, tsv)):
            if r["verdict"] not in ("PASS", "FAIL"):
                continue
            a = r["asset_id"]
            text = third.get(a) if stage == "THIRD" else desc.get(a)
            p = piece_of(stage, a)
            if not text or not os.path.exists(p):
                raise SystemExit("нет описания или рендера: %s %s" % (stage, a))
            out.append({"key": stage + "/" + a, "stage": stage, "asset_id": a, "piece": p, "description": text,
                        "truth": r["verdict"], "truth_types": r.get("types", ""), "truth_note": r.get("note", "")})
    return out


def compose(orig, piece_path, dst):
    import numpy as np
    from PIL import Image, ImageDraw
    o = Image.fromarray(np.repeat(np.repeat(orig, 4, 0), 4, 1))
    b = Image.open(piece_path).convert("RGBA")
    if b.size != o.size:
        raise SystemExit("размер рендера %s не x4 оригинала %s: %s" % (b.size, o.size, piece_path))
    # предмет занимает часть клетки 32x40: вырез по общему габариту обоих с запасом, крупно
    al = np.maximum(np.asarray(o)[:, :, 3], np.asarray(b)[:, :, 3])
    ys, xs = np.nonzero(al > 16)
    box = (max(0, xs.min() - 8), max(0, ys.min() - 8), min(o.width, xs.max() + 9), min(o.height, ys.max() + 9))
    o, b = o.crop(box), b.crop(box)
    k = min(360 / o.width, 400 / o.height)
    W, H = int(o.width * k), int(o.height * k)
    gap, top = 12, 22
    sheet = Image.new("RGBA", (2 * W + 3 * gap, top + 2 * H + 3 * gap), (12, 12, 12, 255))
    d = ImageDraw.Draw(sheet)
    d.text((gap, 5), "A original (pixel art x4)", fill=(230, 230, 230))
    d.text((2 * gap + W, 5), "B HD picture", fill=(230, 230, 230))
    for r, bg in enumerate((DARK, LIGHT)):
        for c, im, res in ((0, o, Image.NEAREST), (1, b, Image.LANCZOS)):
            cell = Image.new("RGBA", im.size, bg)
            cell.alpha_composite(im)
            sheet.paste(cell.resize((W, H), res), (gap + c * (W + gap), top + gap + r * (H + gap)))
    sheet.convert("RGB").save(dst)


def do_calib():
    out = OUT_CAL
    if os.path.exists(os.path.join(out, "pack.json")):
        raise SystemExit("пакет уже собран (pack.json) - не пересобираю: TEST заморожен")
    items = labelled()
    items.sort(key=lambda x: h(SALT + ":" + x["key"]))
    blind = os.path.join(out, "blind")
    os.makedirs(os.path.join(blind, "img"), exist_ok=True)
    os.makedirs(os.path.join(out, "answers"), exist_ok=True)
    for n, x in enumerate(items, 1):
        x["id"] = "J%03d" % n
        x["split"] = "DEV" if n % 3 == 1 else "TEST"
        compose(sprite(x["asset_id"]), x["piece"], os.path.join(blind, "img", x["id"] + ".png"))
    with open(os.path.join(blind, "JUDGE.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(JUDGE)
    batches = {}
    for split in ("DEV", "TEST"):
        part = [x for x in items if x["split"] == split]
        for k in range(0, len(part), BATCH):
            name = "%s_%02d" % (split, k // BATCH + 1)
            batches[name] = [x["id"] for x in part[k:k + BATCH]]
            lines = ["# Batch %s" % name, "", "Instructions: JUDGE.md in this folder. Items (image, description "
                     "the HD picture was rendered from - may be wrong):", ""]
            lines += ["- %s: img/%s.png - %s" % (x["id"], x["id"], x["description"]) for x in part[k:k + BATCH]]
            with open(os.path.join(blind, name + ".md"), "w", encoding="utf-8", newline="\n") as f:
                f.write("\n".join(lines) + "\n")
    pack = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "salt": SALT, "n": len(items),
            "split": dict(Counter(x["split"] for x in items)),
            "truth": {s: dict(Counter(x["truth"] for x in items if x["split"] == s)) for s in ("DEV", "TEST")},
            "judge_md_sha256": sha_file(os.path.join(blind, "JUDGE.md")), "batches": batches,
            "test_frozen": False}
    dump(pack, os.path.join(out, "pack.json"))
    dump([{k: v for k, v in x.items()} for x in items], os.path.join(out, "key.json"))     # правда - вне blind/
    print("пакет %s: %d кадров, %s; правда %s" % (blind, len(items), pack["split"], pack["truth"]))
    print("батчи: %s" % ", ".join(batches))


def do_rules():
    """Переписать JUDGE.md по тексту в коде - только пока TEST не заморожен (правка по DEV)."""
    with open(os.path.join(OUT_CAL, "pack.json"), encoding=ENC) as f:
        pack = json.load(f)
    if pack.get("test_frozen"):
        raise SystemExit("TEST заморожен - JUDGE.md не меняется")
    p = os.path.join(OUT_CAL, "blind", "JUDGE.md")
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(JUDGE)
    pack["judge_md_sha256"] = sha_file(p)
    pack.setdefault("rules_history", []).append([time.strftime("%Y-%m-%dT%H:%M:%S"), pack["judge_md_sha256"]])
    dump(pack, os.path.join(OUT_CAL, "pack.json"))
    print("JUDGE.md переписан: %s" % pack["judge_md_sha256"][:12])


def load_answers(out, who):
    """<who>.tsv и части <who>_*.tsv (агенты Claude пишут каждый свой файл)."""
    d = os.path.join(out, "answers")
    res = {}
    for f in sorted(os.listdir(d)):
        if f.endswith(".tsv") and (f == who + ".tsv" or f.startswith(who + "_")):
            res.update({r["id"]: r for r in read_tsv(os.path.join(d, f))})
    return res


def save_answers(out, who, ans):
    p = os.path.join(out, "answers", who + ".tsv")
    with open(p + ".tmp", "w", encoding=ENC, newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEAD, delimiter="\t", quoting=csv.QUOTE_NONE, escapechar=None,
                           lineterminator="\n")
        w.writeheader()
        for k in sorted(ans):
            w.writerow({c: ans[k].get(c, "").replace("\t", " ") for c in HEAD})
    os.replace(p + ".tmp", p)


def parse_lines(text, want):
    """Строки ответа судьи; принимает и табы, и ' | '. Только id из батча."""
    got = {}
    for line in text.splitlines():
        line = line.strip().strip("`")
        m = re.match(r"^(J\d{3})\s*[\t|]\s*(PASS|FAIL)\s*[\t|]\s*([A-Z_, ]*)\s*[\t|]\s*(sure|unsure)\s*[\t|]?\s*(.*)$",
                     line, re.I)
        if not m or m.group(1) not in want:
            continue
        types = ",".join(t.strip().upper() for t in m.group(3).split(",") if t.strip().upper() in TYPES)
        got[m.group(1)] = {"id": m.group(1), "verdict": m.group(2).upper(), "types": types,
                           "confidence": m.group(4).lower(), "reason": m.group(5).strip()[:200]}
    return got


def freeze_test(out, pack):
    """Первый ответ на TEST замораживает JUDGE.md: дальше его менять нельзя."""
    jm = sha_file(os.path.join(out, "blind", "JUDGE.md"))
    if pack.get("test_frozen"):
        if jm != pack["judge_md_sha256"]:
            raise SystemExit("JUDGE.md изменён после заморозки TEST - ответы на TEST не годятся")
        return
    pack["judge_md_sha256"], pack["test_frozen"] = jm, True
    pack["test_frozen_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    dump(pack, os.path.join(out, "pack.json"))
    print("TEST заморожен: JUDGE.md %s" % jm[:12])


def do_codex(split, only, effort, out=OUT_CAL):
    with open(os.path.join(out, "pack.json"), encoding=ENC) as f:
        pack = json.load(f)
    blind = os.path.abspath(os.path.join(out, "blind"))
    names = [n for n in pack["batches"] if (not split or n.startswith(split)) and (not only or n in only)]
    if any(n.startswith("TEST") for n in names) or out != OUT_CAL:
        freeze_test(out, pack)
    who = "codex"
    ans = load_answers(out, who)
    codex = shutil.which("codex") or "codex"
    logs = os.path.join(out, "answers", "codex_logs")
    os.makedirs(logs, exist_ok=True)
    with open(os.path.join(blind, "JUDGE.md"), encoding="utf-8") as f:
        judge = f.read()
    for name in names:
        ids = pack["batches"][name]
        if all(i in ans for i in ids):
            continue
        with open(os.path.join(blind, name + ".md"), encoding="utf-8") as f:
            batch = f.read()
        imgs = [os.path.join(blind, "img", i + ".png") for i in ids]
        task = (judge + "\n\n" + batch + "\nThe images are attached in this order: " +
                ", ".join("image %d = %s" % (k + 1, i) for k, i in enumerate(ids)) +
                ".\nAnswer now: exactly %d lines, one per item, as specified.\n" % len(ids))
        last = os.path.abspath(os.path.join(logs, name + ".last.txt"))
        logp = os.path.join(logs, name + ".log")
        if os.path.exists(logp):        # прежний прогон: ответ есть в журнале, хоть -o и не записался
            got = parse_lines(open(logp, encoding="utf-8", errors="replace").read(), set(ids))
            if len(got) == len(ids):
                ans.update(got)
                save_answers(out, who, ans)
                print("%s: из журнала прежнего прогона, ответов %d" % (name, len(got)), flush=True)
                continue
        t0 = time.time()
        cmd = [codex, "exec", "--skip-git-repo-check", "--sandbox", "read-only", "-C", blind, "--color", "never",
               "-c", "model_reasoning_effort=" + effort, "-o", last] + sum([["-i", q] for q in imgs], []) + ["-"]
        # задание через stdin: codex.cmd режет аргумент на первом переводе строки (R-222)
        with open(os.path.join(logs, name + ".log"), "w", encoding="utf-8") as lf:
            rc = subprocess.run(cmd, cwd=blind, stdout=lf, stderr=subprocess.STDOUT, input=task.encode("utf-8"),
                                timeout=40 * 60).returncode
        text = open(last, encoding="utf-8", errors="replace").read() if os.path.exists(last) else ""
        got = parse_lines(text, set(ids))
        ans.update(got)
        save_answers(out, who, ans)
        print("%s: код %d, %.0f с, ответов %d из %d" % (name, rc, time.time() - t0, len(got), len(ids)), flush=True)


def verdict_of(row):
    return (row or {}).get("verdict", "")


def metrics(items, ans):
    n = len(items)
    c = Counter()
    for x in items:
        a = ans.get(x["id"])
        if not a:
            c["missing"] += 1
            continue
        c[(a["verdict"], x["truth"])] += 1
        if a["verdict"] == "PASS" and a["confidence"] == "sure":
            c["sure_pass"] += 1
            c["sure_pass_bad"] += x["truth"] == "FAIL"
    jp = c[("PASS", "PASS")] + c[("PASS", "FAIL")]
    tf = c[("PASS", "FAIL")] + c[("FAIL", "FAIL")]
    return {"n": n, "answered": n - c["missing"], "judge_pass": jp, "false_pass": c[("PASS", "FAIL")],
            "false_pass_rate": round(c[("PASS", "FAIL")] / jp, 3) if jp else None,
            "fail_caught": round(c[("FAIL", "FAIL")] / tf, 3) if tf else None,
            "good_lost": c[("FAIL", "PASS")], "agree": c[("PASS", "PASS")] + c[("FAIL", "FAIL")],
            "sure_pass": c["sure_pass"], "sure_pass_bad": c["sure_pass_bad"]}


def combined(items, judges):
    """Связка: AUTO_ACCEPT - все судьи PASS sure; AUTO_FAIL - все FAIL; иначе UNCERTAIN (человеку)."""
    c = Counter()
    for x in items:
        rows = [j.get(x["id"]) for j in judges]
        if not all(rows):
            c["missing"] += 1
            continue
        if all(r["verdict"] == "PASS" and r["confidence"] == "sure" for r in rows):
            k = "AUTO_ACCEPT"
        elif all(r["verdict"] == "FAIL" for r in rows):
            k = "AUTO_FAIL"
        else:
            k = "UNCERTAIN"
        c[(k, x["truth"])] += 1
    return c


def do_report():
    out = OUT_CAL
    with open(os.path.join(out, "key.json"), encoding=ENC) as f:
        items = json.load(f)
    whos = sorted(set(f[:-4].split("_")[0] for f in os.listdir(os.path.join(out, "answers")) if f.endswith(".tsv")))
    md = ["# Калибровка визуального судьи V1", "",
          "Правда - приговоры Vitali по V1 (RESTORE, STRICT, THIRD). Ложный PASS - судья принял, Vitali забраковал.", ""]
    res = {}
    for split in ("DEV", "TEST", "ALL"):
        part = [x for x in items if split == "ALL" or x["split"] == split]
        md += ["## %s (%d кадров, правда %s)" % (split, len(part), dict(Counter(x["truth"] for x in part))), "",
               "| судья | ответов | PASS судьи | ложный PASS | доля ложного PASS | FAIL пойман | годных потеряно | sure PASS (из них брак) |",
               "|---|---|---|---|---|---|---|---|"]
        for who in whos:
            m = metrics(part, load_answers(out, who))
            res["%s/%s" % (split, who)] = m
            md.append("| %s | %d | %d | %d | %s | %s | %d | %d (%d) |" % (
                who, m["answered"], m["judge_pass"], m["false_pass"], m["false_pass_rate"], m["fail_caught"],
                m["good_lost"], m["sure_pass"], m["sure_pass_bad"]))
        if len(whos) > 1:
            c = combined(part, [load_answers(out, w) for w in whos])
            res["%s/combined" % split] = {"%s|%s" % k if isinstance(k, tuple) else k: v for k, v in c.items()}
            md += ["", "Связка всех судей: " + ", ".join("%s при правде %s: %d" % (k[0], k[1], v) for k, v in
                                                         sorted((kv for kv in c.items() if isinstance(kv[0], tuple))))]
        md.append("")
    for who in whos:
        ans = load_answers(out, who)
        bad = [x for x in items if verdict_of(ans.get(x["id"])) == "PASS" and x["truth"] == "FAIL"]
        if bad:
            md += ["### %s: ложные PASS" % who, ""] + ["- %s %s %s: судья «%s»; Vitali %s %s" % (
                x["id"], x["split"], x["key"], ans[x["id"]]["reason"], x["truth_types"] or "-", x["truth_note"][:60])
                for x in bad] + [""]
    with open(os.path.join(out, "report.md"), "w", encoding=ENC) as f:
        f.write("\n".join(md) + "\n")
    dump(res, os.path.join(out, "report.json"))
    print("\n".join(md))


V2 = os.path.join(PROBES, "prod-two-pass-v2")
PROD_SUB = {"RESTORE": "render", "STRICT": os.path.join("strict", "series"),
            "THIRD": os.path.join("third", "strict", "series")}


def prod_dir(stage):
    return os.path.join(V2, "judge", stage.lower())


def prod_items(stage):
    """Рендеры прохода V2 и описание, по которому рисовали (RESTORE/STRICT - descriptions.tsv партии, THIRD -
    third/descriptions.tsv). Только то, что уже нарисовано."""
    desc = {r["asset_id"]: r["description"] for r in read_tsv(os.path.join(V2, "descriptions.tsv"))}
    if stage == "THIRD":
        desc = {r["asset_id"]: r["what_en"] for r in read_tsv(os.path.join(V2, "third", "descriptions.tsv"))}
    out = []
    for a in sorted(desc):
        s, f = a.split(":")
        p = os.path.join(V2, PROD_SUB[stage], s + ".PCK", f + ".png")
        if os.path.exists(p):
            out.append({"asset_id": a, "piece": p, "description": desc[a]})
    return out


def do_prod_pack(stage):
    """Слепой пакет боевого прохода: JUDGE.md - замороженный калибровкой (sha сверяется), раскладка та же."""
    with open(os.path.join(OUT_CAL, "pack.json"), encoding=ENC) as f:
        cal = json.load(f)
    src = os.path.join(OUT_CAL, "blind", "JUDGE.md")
    if not cal.get("test_frozen") or sha_file(src) != cal["judge_md_sha256"]:
        raise SystemExit("правила судьи не заморожены проверкой TEST - в бой не идут")
    out = prod_dir(stage)
    if os.path.exists(os.path.join(out, "pack.json")):
        raise SystemExit("пакет %s уже собран" % stage)
    items = prod_items(stage)
    if not items:
        raise SystemExit("рендеров %s нет" % stage)
    blind = os.path.join(out, "blind")
    os.makedirs(os.path.join(blind, "img"), exist_ok=True)
    os.makedirs(os.path.join(out, "answers"), exist_ok=True)
    shutil.copy(src, os.path.join(blind, "JUDGE.md"))
    items.sort(key=lambda x: h(SALT + ":prod:" + stage + ":" + x["asset_id"]))
    for n, x in enumerate(items, 1):
        x["id"] = "J%03d" % n
        compose(sprite(x["asset_id"]), x["piece"], os.path.join(blind, "img", x["id"] + ".png"))
    batches = {}
    for k in range(0, len(items), BATCH):
        name = "P_%02d" % (k // BATCH + 1)
        part = items[k:k + BATCH]
        batches[name] = [x["id"] for x in part]
        lines = ["# Batch %s" % name, "", "Instructions: JUDGE.md in this folder. Items (image, description "
                 "the HD picture was rendered from - may be wrong):", ""]
        lines += ["- %s: img/%s.png - %s" % (x["id"], x["id"], x["description"]) for x in part]
        with open(os.path.join(blind, name + ".md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines) + "\n")
    dump({"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "stage": stage, "n": len(items),
          "judge_md_sha256": cal["judge_md_sha256"], "batches": batches, "test_frozen": True},
         os.path.join(out, "pack.json"))
    dump(items, os.path.join(out, "key.json"))
    print("пакет %s: %d кадров, батчи %s" % (blind, len(items), ", ".join(batches)))


def do_prod_verdict(stage):
    """verdicts_auto.tsv прохода по связке судей (правило TEST): AUTO_ACCEPT - все PASS sure, AUTO_FAIL - все FAIL,
    UNCERTAIN - остальное. Столбец verdict для следующего прохода: PASS только у AUTO_ACCEPT."""
    out = prod_dir(stage)
    with open(os.path.join(out, "key.json"), encoding=ENC) as f:
        items = json.load(f)
    whos = sorted(set(f[:-4].split("_")[0] for f in os.listdir(os.path.join(out, "answers")) if f.endswith(".tsv")))
    judges = {w: load_answers(out, w) for w in whos}
    rows, c = [], Counter()
    for x in items:
        r = [judges[w].get(x["id"]) for w in whos]
        if len(whos) < 2 or not all(r):
            k = "WAIT"
        elif all(y["verdict"] == "PASS" and y["confidence"] == "sure" for y in r):
            k = "AUTO_ACCEPT"
        elif all(y["verdict"] == "FAIL" for y in r):
            k = "AUTO_FAIL"
        else:
            k = "UNCERTAIN"
        c[k] += 1
        rows.append({"asset_id": x["asset_id"], "route": k, "verdict": "PASS" if k == "AUTO_ACCEPT" else "FAIL",
                     "types": ",".join(sorted(set(t for y in r if y for t in y["types"].split(",") if t))),
                     "note": " | ".join("%s %s %s: %s" % (w, y["verdict"], y["confidence"], y["reason"])
                                        for w, y in zip(whos, r) if y)})
    p = os.path.join(out, "verdicts_auto.tsv")
    head = ["asset_id", "route", "verdict", "types", "note"]
    with open(p + ".tmp", "w", encoding=ENC, newline="") as f:
        w = csv.DictWriter(f, fieldnames=head, delimiter="\t", quoting=csv.QUOTE_NONE, lineterminator="\n")
        w.writeheader()
        for r in sorted(rows, key=lambda r: r["asset_id"]):
            w.writerow({k: r[k].replace("\t", " ") for k in head})
    os.replace(p + ".tmp", p)
    print("%s, судьи %s: %s" % (stage, ", ".join(whos), dict(c)))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["calib", "rules", "codex", "report", "prod-pack", "prod-codex", "prod-verdict"])
    ap.add_argument("--split", default="", choices=["", "DEV", "TEST"])
    ap.add_argument("--only", default="", help="батчи через запятую")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--stage", default="RESTORE", choices=list(PROD_SUB))
    ap.add_argument("--batch", default="", help="папка производственной партии для prod-* (по умолчанию V2)")
    a = ap.parse_args()
    os.chdir(ROOT)
    if a.batch:
        global V2
        V2 = a.batch
    if a.cmd == "calib":
        do_calib()
    elif a.cmd == "rules":
        do_rules()
    elif a.cmd == "codex":
        do_codex(a.split, set(x for x in a.only.split(",") if x), a.effort)
    elif a.cmd == "prod-pack":
        do_prod_pack(a.stage)
    elif a.cmd == "prod-codex":
        do_codex("", set(x for x in a.only.split(",") if x), a.effort, out=prod_dir(a.stage))
    elif a.cmd == "prod-verdict":
        do_prod_verdict(a.stage)
    else:
        do_report()


if __name__ == "__main__":
    main()
