#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Автоматическое опознание кандидатов PROD_TWO_PASS_V2 (специалист 05.10, передал Vitali в чате).

Ручной identity-review партии отменён. Имеющиеся описания - гипотезы, а не истина. Каждый кандидат опознают ДВА
независимых судьи разных семейств - Codex (GPT, codex exec read-only с картинками) и агент Claude - по карточке
контекста identity_card.py: кадр крупно, место на карте с рентгеном, соседи на карте, состояния MCD, семейство,
факты MCD и рулсетов, гипотеза (помечена непроверенной). Каждый пишет структурный ответ:
    kind         OBJECT (самостоятельный предмет) / STRUCTURAL_PART (часть стены, колонны, машины, большой
                 конструкции - одиночным предметом не рисуется) / NOT_OBJECT (рельеф, пол, эффект) / UNSURE
    name         короткое английское название
    description  одна фраза для рендера: предмет, части с числом и раскладкой, материал и цвета как на кадре
    hypothesis   CORRECT / PARTLY / WRONG - гипотеза против того, что видно
    confidence   sure / unsure
Сведение (merge): оба OBJECT sure и одно и то же по смыслу - AGREE; оба STRUCTURAL_PART / NOT_OBJECT - туда же
без рендера; иначе - автоматический арбитр (третий судья видит обе версии и картинки; ARBITER.md), а не человек.
Человеку - только то, что арбитр оставил UNSURE.

    py -3.13 tools/hdart/identity_auto.py pack                   слепой пакет (CPU)
    py -3.13 tools/hdart/identity_auto.py codex [--only B01,B02]  ответы Codex
    py -3.13 tools/hdart/identity_auto.py merge                  сведение двух судей -> merge.json
    py -3.13 tools/hdart/identity_auto.py arbiter-pack           пакет арбитра (blind/ARBITER.md, A##.md);
                                                                 арбитр - свежий агент Claude, пишет answers/arbiter_*.tsv
    py -3.13 tools/hdart/identity_auto.py final                  identity.tsv: RENDER / STRUCTURAL_PART / NOT_OBJECT / HUMAN

V3 (специалист 05.10): --batch <папка партии>; HUMAN не идёт человеку, а второму арбитру (Codex) с упором на место
на карте, соседей и спрайт крупно; его неуверенность - RESIDUAL_IDENTITY (человек только на финальном остатке):
    arbiter2-pack  -> blind/ARBITER2.md, C##.md (HUMAN из identity.tsv, версии обоих судей и первого арбитра)
    arbiter2       -> answers/arbiter2.tsv; затем снова final

Пересмотр после STRICT (identity-rethink, та же схема в папке identity/rethink): FAIL судей STRICT, к карточке
добавлены оба отклонённых рендера рядом с оригиналом и причины судей; гипотеза - описание, по которому рисовали.
    rethink-pack; codex / merge / arbiter-pack / final с --round rethink; third-desc -> third/descriptions.tsv
    (STRICT - новое описание, если хоть один судья назвал прежнее неверным; SAME_DESCRIPTION - прежнее верно,
    третий проход ничего не даст; остальное - как в final).
"""
import argparse
import csv
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
V2 = os.path.join("art", "objects", "generation", "probes", "prod-two-pass-v2")
CARDS = os.path.join(V2, "identity", "cards")
OUT = os.path.join(V2, "identity", "auto")
BATCH = 6
PANELS = ("sprite", "place0", "near", "states", "family")
KINDS = ("OBJECT", "STRUCTURAL_PART", "NOT_OBJECT", "UNSURE")
HEAD = ["id", "kind", "name", "description", "hypothesis", "confidence", "reason"]

IDENTIFY = """# Identify a game sprite

You identify objects of an old isometric tactical game (X-COM style, the X-Piratez mod). Each object is a
32x40 pixel-art sprite that sits in one map cell. Its HD picture will be rendered from your description, so
the description must say what is REALLY drawn - not what the old text says.

For each item you get several images in `img/` (id prefix + panel name):

* `<id>_sprite.png` - the sprite enlarged, on dark and light floor
* `<id>_place0.png` - where it stands on a real game map: left the area around it (the frame in red boxes),
  right an x-ray (surroundings dimmed, this frame on top - it shows the frame even behind walls)
* `<id>_near.png` - what stands in the same and neighbouring cells on the map
* `<id>_states.png` (if present) - animation frames / destroyed version / second state from the game data
* `<id>_family.png` (if present) - related frames (recolours, mirrored, other side)

plus facts from the game data (tileset, map blocks, movement, armour, volume, neighbours) and a HYPOTHESIS -
an old description written without context. The hypothesis is UNVERIFIED and is often wrong: check it against
the pictures, never copy it blindly.

Decide:

* **kind**
  * OBJECT - a self-contained object that makes sense alone in its cell (furniture, crate, machine, statue,
    lamp, painting, plant pot, barrel...). An object that only stands next to others of its kind is still an object.
  * STRUCTURAL_PART - a piece of something bigger: a segment of a column, a section of a wall, roof, pipe,
    vehicle hull, a part of a multi-cell machine, a decoration that only exists on a wall joint. Look at the map:
    if neighbouring cells continue the same shape, it is a part.
  * NOT_OBJECT - terrain relief, floor, rubble field, effect.
  * UNSURE - the pictures do not let you decide.
* **name** - short English name (2-6 words).
* **description** - ONE English sentence for an image generator: what the object is, its main parts WITH COUNT
  and LAYOUT (top / bottom / left / right / front), materials and colours exactly as on the sprite. No guesses
  beyond what is visible, no style words.
* **hypothesis** - CORRECT (same object, same parts), PARTLY (right object, wrong or missing parts/colours),
  WRONG (a different object).
* **confidence** - sure or unsure.
* **reason** - at most 15 English words: the decisive evidence.

Answer for EVERY item of the batch, one line per item, fields separated by TAB:

    id<TAB>kind<TAB>name<TAB>description<TAB>hypothesis<TAB>confidence<TAB>reason

No tabs inside fields. Look at every image yourself. Do not open any file outside this folder.
Output only the lines, no table, no header.
"""


def read_tsv(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding=ENC, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def dump(obj, path):
    with open(path + ".tmp", "w", encoding=ENC) as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(path + ".tmp", path)


def do_pack():
    if os.path.exists(os.path.join(OUT, "pack.json")):
        raise SystemExit("пакет уже собран (pack.json)")
    with open(os.path.join(CARDS, "cards.json"), encoding=ENC) as f:
        cards = json.load(f)["cards"]
    with open(os.path.join(V2, "candidates_all.json"), encoding=ENC) as f:
        hyp = {c["asset_id"]: c["card"] for c in json.load(f)}
    blind = os.path.join(OUT, "blind")
    os.makedirs(os.path.join(blind, "img"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "answers"), exist_ok=True)
    items = []
    for c in cards:
        i = "I%03d" % c["n"]
        panels = []
        for p in PANELS:
            src = os.path.join(CARDS, "img", "%02d_%s.png" % (c["n"], p))
            if os.path.exists(src):
                shutil.copy(src, os.path.join(blind, "img", "%s_%s.png" % (i, p)))
                panels.append("%s_%s.png" % (i, p))
        if "%s_sprite.png" % i not in panels or "%s_place0.png" % i not in panels:
            raise SystemExit("у %s нет кадра или места на карте" % c["asset"])
        # имя набора и кадра из фактов убрано: судья решает по картинкам и физике, а не по слову в имени PCK
        facts = [ln for ln in c["facts"].splitlines() if not ln.startswith("- tileset")]
        items.append({"id": i, "asset_id": c["asset"], "panels": panels, "facts": facts,
                      "hypothesis": hyp.get(c["asset"], c.get("prompt", ""))})
    with open(os.path.join(blind, "IDENTIFY.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(IDENTIFY)
    batches = {}
    for k in range(0, len(items), BATCH):
        name = "B%02d" % (k // BATCH + 1)
        part = items[k:k + BATCH]
        batches[name] = [x["id"] for x in part]
        lines = ["# Batch %s" % name, "", "Instructions: IDENTIFY.md in this folder.", ""]
        for x in part:
            lines += ["## %s" % x["id"], "", "images: " + ", ".join("img/" + p for p in x["panels"]), "",
                      "facts:"] + x["facts"] + ["", "HYPOTHESIS (unverified): " + x["hypothesis"], ""]
        with open(os.path.join(blind, name + ".md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines) + "\n")
    dump({"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "n": len(items), "batches": batches}, os.path.join(OUT, "pack.json"))
    dump(items, os.path.join(OUT, "key.json"))
    print("пакет %s: %d кандидатов, %d батчей" % (blind, len(items), len(batches)))


def save_answers(who, ans):
    p = os.path.join(OUT, "answers", who + ".tsv")
    with open(p + ".tmp", "w", encoding=ENC, newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEAD, delimiter="\t", quoting=csv.QUOTE_NONE, lineterminator="\n")
        w.writeheader()
        for k in sorted(ans):
            w.writerow({c: ans[k].get(c, "").replace("\t", " ") for c in HEAD})
    os.replace(p + ".tmp", p)


def load_answers(who):
    """Ответы судьи: <who>.tsv и части <who>_*.tsv (агенты Claude пишут каждый свой файл)."""
    d = os.path.join(OUT, "answers")
    out = {}
    for f in sorted(os.listdir(d)):
        if f.endswith(".tsv") and (f == who + ".tsv" or f.startswith(who + "_")):
            out.update({r["id"]: r for r in read_tsv(os.path.join(d, f))})
    return out


def parse_lines(text, want):
    got = {}
    for line in text.splitlines():
        f = [x.strip() for x in line.strip().strip("`").split("\t")]
        if len(f) < 6 or f[0] not in want or f[1].upper() not in KINDS:
            continue
        got[f[0]] = {"id": f[0], "kind": f[1].upper(), "name": f[2], "description": f[3],
                     "hypothesis": f[4].upper(), "confidence": f[5].lower(), "reason": f[6] if len(f) > 6 else ""}
    return got


def do_codex(only, effort):
    with open(os.path.join(OUT, "pack.json"), encoding=ENC) as f:
        pack = json.load(f)
    blind = os.path.abspath(os.path.join(OUT, "blind"))
    ans = load_answers("codex")
    codex = shutil.which("codex") or "codex"
    logs = os.path.join(OUT, "answers", "codex_logs")
    os.makedirs(logs, exist_ok=True)
    with open(os.path.join(blind, "IDENTIFY.md"), encoding="utf-8") as f:
        rules = f.read()
    for name, ids in pack["batches"].items():
        if (only and name not in only) or all(i in ans for i in ids):
            continue
        with open(os.path.join(blind, name + ".md"), encoding="utf-8") as f:
            batch = f.read()
        imgs = sorted(os.path.join(blind, "img", p) for p in os.listdir(os.path.join(blind, "img"))
                      if p.split("_")[0] in ids)
        task = (rules + "\n\n" + batch + "\nThe images are attached in this order: " +
                ", ".join("image %d = %s" % (k + 1, os.path.basename(q)) for k, q in enumerate(imgs)) +
                ".\nAnswer now: exactly %d lines, one per item, as specified.\n" % len(ids))
        last = os.path.abspath(os.path.join(logs, name + ".last.txt"))
        t0 = time.time()
        cmd = [codex, "exec", "--skip-git-repo-check", "--sandbox", "read-only", "-C", blind, "--color", "never",
               "-c", "model_reasoning_effort=" + effort, "-o", last] + sum([["-i", q] for q in imgs], []) + ["-"]
        with open(os.path.join(logs, name + ".log"), "w", encoding="utf-8") as lf:     # задание через stdin (R-222)
            rc = subprocess.run(cmd, cwd=blind, stdout=lf, stderr=subprocess.STDOUT, input=task.encode("utf-8"),
                                timeout=40 * 60).returncode
        text = open(last, encoding="utf-8", errors="replace").read() if os.path.exists(last) else ""
        got = parse_lines(text, set(ids))
        ans.update(got)
        save_answers("codex", ans)
        print("%s: код %d, %.0f с, ответов %d из %d" % (name, rc, time.time() - t0, len(got), len(ids)), flush=True)


def words(s):
    return set(w for w in re.findall(r"[a-z]+", s.lower()) if len(w) > 3)


def do_merge():
    with open(os.path.join(OUT, "key.json"), encoding=ENC) as f:
        items = json.load(f)
    a, b = load_answers("claude"), load_answers("codex")
    rows, arb = [], []
    for x in items:
        p, q = a.get(x["id"]), b.get(x["id"])
        if not p or not q:
            rows.append(dict(x, route="WAIT", why="нет ответа %s" % ("claude" if not p else "codex")))
            continue
        same_kind = p["kind"] == q["kind"]
        sure = p["confidence"] == "sure" and q["confidence"] == "sure"
        overlap = len(words(p["name"]) & words(q["name"]))
        if same_kind and p["kind"] in ("STRUCTURAL_PART", "NOT_OBJECT") and sure:
            rows.append(dict(x, route=p["kind"], name=p["name"], description=p["description"], why="оба судьи"))
        elif same_kind and p["kind"] == "OBJECT" and sure and overlap:
            rows.append(dict(x, route="AGREE", name=p["name"], description=p["description"],
                             why="оба OBJECT sure, общее в названии: %s" % ", ".join(sorted(words(p["name"]) & words(q["name"])))))
        else:
            arb.append(x["id"])
            rows.append(dict(x, route="ARBITER", why="%s/%s %s/%s, общих слов %d" % (
                p["kind"], q["kind"], p["confidence"], q["confidence"], overlap)))
    c = Counter(r["route"] for r in rows)
    print("сведение: %s" % dict(c))
    with open(os.path.join(OUT, "merge.json"), "w", encoding=ENC) as f:
        json.dump({"routes": dict(c), "arbiter": arb, "rows": rows}, f, ensure_ascii=False, indent=1)


ARBITER = """# Arbitrate a game sprite identification

Same task as IDENTIFY.md (read it first: the panels, the kinds, the description rules). Two independent judges
already answered each item below and did not agree, or one of them was unsure. Their answers are VERSION 1 and
VERSION 2 - in random order, both may be wrong, the hypothesis may be wrong too.

Look at every image of the item yourself, then give the FINAL answer:

* kind, name, description - as in IDENTIFY.md; you may take one version, fix it, or write your own;
* pick - V1, V2, BOTH (they say the same), NEW (your own, neither is right);
* confidence - sure only if the pictures leave no real doubt; otherwise unsure (a human will look);
* reason - at most 15 English words: the decisive evidence.

Answer for EVERY item, one line per item, fields separated by TAB, no tabs inside fields:

    id<TAB>kind<TAB>name<TAB>description<TAB>pick<TAB>confidence<TAB>reason

Output only the lines, no table, no header. Do not open any file outside this folder.
"""
ARB_HEAD = ["id", "kind", "name", "description", "pick", "confidence", "reason"]
ARB_BATCH = 6


def do_arbiter_pack():
    """Пакет арбитра для ARBITER из merge.json: картинки те же, обе версии в случайном (по хэшу) порядке."""
    import hashlib
    with open(os.path.join(OUT, "merge.json"), encoding=ENC) as f:
        m = json.load(f)
    if any(r["route"] == "WAIT" for r in m["rows"]):
        raise SystemExit("не все ответили (WAIT) - сначала все ответы, потом арбитр")
    a, b = load_answers("claude"), load_answers("codex")
    rows = {r["id"]: r for r in m["rows"]}
    blind = os.path.join(OUT, "blind")
    with open(os.path.join(blind, "ARBITER.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(ARBITER)
    order, batches = {}, {}
    ids = m["arbiter"]
    for k in range(0, len(ids), ARB_BATCH):
        name = "A%02d" % (k // ARB_BATCH + 1)
        part = ids[k:k + ARB_BATCH]
        batches[name] = part
        lines = ["# Arbiter batch %s" % name, "", "Instructions: ARBITER.md, then IDENTIFY.md in this folder.", ""]
        for i in part:
            x = rows[i]
            flip = hashlib.sha256(("identity-arbiter:" + i).encode()).digest()[0] & 1
            v = [b[i], a[i]] if flip else [a[i], b[i]]
            order[i] = ["codex", "claude"] if flip else ["claude", "codex"]
            lines += ["## %s" % i, "", "images: " + ", ".join("img/" + p for p in x["panels"]), "",
                      "facts:"] + x["facts"] + ["", "HYPOTHESIS (unverified): " + x["hypothesis"], ""]
            for n, y in enumerate(v, 1):
                lines.append("VERSION %d: kind %s, %s; name: %s; description: %s; reason: %s" % (
                    n, y["kind"], y["confidence"], y["name"], y["description"], y["reason"]))
            lines.append("")
        with open(os.path.join(blind, name + ".md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines) + "\n")
    dump({"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "batches": batches, "order": order},
         os.path.join(OUT, "arbiter_pack.json"))
    print("арбитру: %d кандидатов, батчи %s" % (len(ids), ", ".join(batches)))


def do_final():
    """identity.tsv: итог опознания на каждого кандидата и маршрут.
    RENDER - оба судьи OBJECT sure и согласны, или арбитр OBJECT sure; STRUCTURAL_PART / NOT_OBJECT - оба судьи или
    арбитр sure; HUMAN - арбитр не уверен или UNSURE (единственное, что идёт человеку); WAIT - ответа ещё нет."""
    with open(os.path.join(OUT, "merge.json"), encoding=ENC) as f:
        m = json.load(f)
    arb, arb2 = load_answers("arbiter"), load_answers("arbiter2")
    out = []
    for r in m["rows"]:
        row = {"id": r["id"], "asset_id": r["asset_id"], "route": r["route"], "name": r.get("name", ""),
               "description": r.get("description", ""), "source": "оба судьи (%s)" % r["why"]}
        if r["route"] == "AGREE":
            row["route"] = "RENDER"
        elif r["route"] == "ARBITER":
            z = arb.get(r["id"])
            if not z:
                row.update(route="WAIT", source="нет ответа арбитра")
            else:
                kind, sure = z["kind"].upper(), z["confidence"].lower() == "sure"
                row.update(name=z["name"], description=z["description"],
                           source="арбитр, pick %s, %s: %s" % (z["pick"], z["confidence"], z["reason"]))
                row["route"] = ("HUMAN" if not sure or kind == "UNSURE" else
                                "RENDER" if kind == "OBJECT" else kind)
                z2 = arb2.get(r["id"])
                if row["route"] == "HUMAN" and z2:      # второй арбитр по контексту карты (V3)
                    kind, sure = z2["kind"].upper(), z2["confidence"].lower() == "sure"
                    row.update(name=z2["name"], description=z2["description"],
                               source="второй арбитр (контекст карты), pick %s, %s: %s" % (
                                   z2["pick"], z2["confidence"], z2["reason"]))
                    row["route"] = ("RESIDUAL_IDENTITY" if not sure or kind == "UNSURE" else
                                    "RENDER" if kind == "OBJECT" else kind)
        out.append(row)
    p = os.path.join(OUT, "identity.tsv")
    head = ["id", "asset_id", "route", "name", "description", "source"]
    with open(p + ".tmp", "w", encoding=ENC, newline="") as f:
        w = csv.DictWriter(f, fieldnames=head, delimiter="\t", quoting=csv.QUOTE_NONE, lineterminator="\n")
        w.writeheader()
        for row in out:
            w.writerow({k: str(row[k]).replace("\t", " ") for k in head})
    os.replace(p + ".tmp", p)
    c = Counter(r["route"] for r in out)
    print("итог опознания: %s" % dict(c))
    print("человеку (HUMAN): %s" % (", ".join(r["asset_id"] for r in out if r["route"] == "HUMAN") or "никого"))
    if any(r["route"] == "RESIDUAL_IDENTITY" for r in out):
        print("residual identity (оба арбитра не уверены): %s" % ", ".join(
            r["asset_id"] for r in out if r["route"] == "RESIDUAL_IDENTITY"))


ARBITER2 = """# Second arbitration: decide from the MAP CONTEXT

Same task as IDENTIFY.md (read it first: the panels, the kinds, the description rules). For each item below the
two judges did not agree AND the first arbiter was still unsure. Their answers are listed as VERSION 1..3 - in
random order, all of them unverified, any of them may be wrong.

Do not start from the versions. Start from the pictures, in this order:

1. `<id>_place0.png` - the map: what room or area is this (kitchen, office, street, cave, ship...)? What stands
   around the cell? The x-ray on the right shows the frame itself even behind walls.
2. `<id>_near.png` - the objects in the same and the 8 neighbouring cells: does the shape continue into a
   neighbour (then it is a STRUCTURAL_PART), or is it a separate thing that fits this room?
3. `<id>_sprite.png` - the sprite large: count the parts, read the colours.
4. `<id>_states.png` / `<id>_family.png` if present - the destroyed version or animation often tells what it is.

Only then compare with the versions: take one, fix it, or write your own.

* kind, name, description - as in IDENTIFY.md;
* pick - V1, V2, V3, NEW;
* confidence - sure only if the context leaves no real doubt; unsure otherwise (it goes to the residual list,
  not to a render - an honest unsure is better than a guess);
* reason - at most 15 English words: the decisive evidence FROM THE CONTEXT.

Answer for EVERY item, one line per item, fields separated by TAB, no tabs inside fields:

    id<TAB>kind<TAB>name<TAB>description<TAB>pick<TAB>confidence<TAB>reason

Output only the lines, no table, no header. Do not open any file outside this folder.
"""


def do_arbiter2_pack():
    """Второй арбитр (V3, специалист 05.10): кадры, где первый арбитр не уверен (identity.tsv route HUMAN) - не
    человеку, а ещё одному арбитру другого семейства (Codex) с упором на место на карте, соседей и спрайт крупно.
    Версии: оба судьи и первый арбитр, порядок по хэшу."""
    import hashlib
    rows = [r for r in read_tsv(os.path.join(OUT, "identity.tsv")) if r["route"] == "HUMAN"]
    if not rows:
        raise SystemExit("второму арбитру нечего: в identity.tsv нет HUMAN (сначала final)")
    with open(os.path.join(OUT, "key.json"), encoding=ENC) as f:
        key = {x["id"]: x for x in json.load(f)}
    vers = {"claude": load_answers("claude"), "codex": load_answers("codex"), "arbiter": load_answers("arbiter")}
    blind = os.path.join(OUT, "blind")
    with open(os.path.join(blind, "ARBITER2.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(ARBITER2)
    order, batches = {}, {}
    ids = [r["id"] for r in rows]
    for k in range(0, len(ids), ARB_BATCH):
        name = "C%02d" % (k // ARB_BATCH + 1)
        part = ids[k:k + ARB_BATCH]
        batches[name] = part
        lines = ["# Second arbiter batch %s" % name, "", "Instructions: ARBITER2.md, then IDENTIFY.md in this folder.", ""]
        for i in part:
            x = key[i]
            who = sorted(vers, key=lambda w: hashlib.sha256(("identity-arbiter2:%s:%s" % (i, w)).encode()).digest())
            order[i] = who
            lines += ["## %s" % i, "", "images: " + ", ".join("img/" + p for p in x["panels"]), "",
                      "facts:"] + x["facts"] + ["", "OLD HYPOTHESIS (unverified): " + x["hypothesis"], ""]
            for n, w in enumerate(who, 1):
                y = vers[w].get(i, {})
                lines.append("VERSION %d: kind %s, %s; name: %s; description: %s; reason: %s" % (
                    n, y.get("kind", "-"), y.get("confidence", "-"), y.get("name", "-"), y.get("description", "-"),
                    y.get("reason", "-")))
            lines.append("")
        with open(os.path.join(blind, name + ".md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines) + "\n")
    dump({"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "batches": batches, "order": order},
         os.path.join(OUT, "arbiter2_pack.json"))
    print("второму арбитру: %d кадров, батчи %s" % (len(ids), ", ".join(batches)))


def do_arbiter2(effort):
    """Второй арбитр - Codex (codex exec read-only, задание через stdin, R-222) -> answers/arbiter2.tsv."""
    with open(os.path.join(OUT, "arbiter2_pack.json"), encoding=ENC) as f:
        pack = json.load(f)
    blind = os.path.abspath(os.path.join(OUT, "blind"))
    ans = load_answers("arbiter2")
    codex = shutil.which("codex") or "codex"
    logs = os.path.join(OUT, "answers", "arbiter2_logs")
    os.makedirs(logs, exist_ok=True)
    rules = "".join(open(os.path.join(blind, n), encoding="utf-8").read() + "\n\n" for n in ("ARBITER2.md", "IDENTIFY.md"))
    for name, ids in pack["batches"].items():
        if all(i in ans for i in ids):
            continue
        with open(os.path.join(blind, name + ".md"), encoding="utf-8") as f:
            batch = f.read()
        imgs = sorted(os.path.join(blind, "img", p) for p in os.listdir(os.path.join(blind, "img"))
                      if p.split("_")[0] in ids)
        task = (rules + batch + "\nThe images are attached in this order: " +
                ", ".join("image %d = %s" % (k + 1, os.path.basename(q)) for k, q in enumerate(imgs)) +
                ".\nAnswer now: exactly %d lines, one per item, as specified in ARBITER2.md.\n" % len(ids))
        last = os.path.abspath(os.path.join(logs, name + ".last.txt"))
        t0 = time.time()
        cmd = [codex, "exec", "--skip-git-repo-check", "--sandbox", "read-only", "-C", blind, "--color", "never",
               "-c", "model_reasoning_effort=" + effort, "-o", last] + sum([["-i", q] for q in imgs], []) + ["-"]
        with open(os.path.join(logs, name + ".log"), "w", encoding="utf-8") as lf:
            rc = subprocess.run(cmd, cwd=blind, stdout=lf, stderr=subprocess.STDOUT, input=task.encode("utf-8"),
                                timeout=40 * 60).returncode
        text = open(last, encoding="utf-8", errors="replace").read() if os.path.exists(last) else ""
        got = {}
        for line in text.splitlines():
            f = [x.strip() for x in line.strip().strip("`").split("\t")]
            if len(f) >= 6 and f[0] in ids and f[1].upper() in KINDS:
                got[f[0]] = {"id": f[0], "kind": f[1].upper(), "name": f[2], "description": f[3],
                             "pick": f[4].upper(), "confidence": f[5].lower(), "reason": f[6] if len(f) > 6 else ""}
        ans.update(got)
        p = os.path.join(OUT, "answers", "arbiter2.tsv")
        with open(p + ".tmp", "w", encoding=ENC, newline="") as f:
            w = csv.DictWriter(f, fieldnames=ARB_HEAD, delimiter="\t", quoting=csv.QUOTE_NONE, lineterminator="\n")
            w.writeheader()
            for k in sorted(ans):
                w.writerow({c: ans[k].get(c, "").replace("\t", " ") for c in ARB_HEAD})
        os.replace(p + ".tmp", p)
        print("%s: код %d, %.0f с, ответов %d из %d" % (name, rc, time.time() - t0, len(got), len(ids)), flush=True)


RETHINK = """
# RETHINK round

These objects were already rendered TWICE from the description given as HYPOTHESIS, and both HD pictures were
rejected by the acceptance judges (their reasons are listed with the item). Two more images per item:

* `<id>_restore.png` and `<id>_strict.png` - left the original sprite x4 (the truth), right the rejected HD
  picture, top on a dark floor, bottom on a light floor.

Find out WHY the renders went wrong. Very often the description named the wrong object, missed or miscounted
parts, put them in the wrong place or gave wrong colours/materials - then write a NEW, more precise description
that fixes exactly that. Describe only what the ORIGINAL sprite shows; never describe the rejected pictures.
hypothesis: CORRECT if the old description was already right (the renders failed for other reasons), PARTLY or
WRONG if your new description fixes it.
"""


def use_batch(path):
    """Другая партия (V3 и далее): та же раскладка identity/cards, identity/auto внутри её папки."""
    global V2, CARDS, OUT
    V2 = path
    CARDS = os.path.join(V2, "identity", "cards")
    OUT = os.path.join(V2, "identity", "auto")


def use_rethink():
    """Раунд пересмотра: те же pack/codex/merge/arbiter-pack/final, другая папка."""
    global OUT
    OUT = os.path.join(V2, "identity", "rethink")


def do_rethink_pack():
    """FAIL после STRICT (judge/strict/verdicts_auto.tsv, всё кроме AUTO_ACCEPT): карточка контекста, оба
    отклонённых рендера рядом с оригиналом, причины судей; гипотеза - описание, по которому рисовали."""
    import visual_judge as vj
    if os.path.exists(os.path.join(OUT, "pack.json")):
        raise SystemExit("пакет пересмотра уже собран")
    ver = {r["asset_id"]: r for r in read_tsv(os.path.join(V2, "judge", "strict", "verdicts_auto.tsv"))}
    restore = {r["asset_id"]: r for r in read_tsv(os.path.join(V2, "judge", "restore", "verdicts_auto.tsv"))}
    if not ver or any(r["route"] == "WAIT" for r in ver.values()):
        raise SystemExit("приговоры STRICT не готовы")
    desc = {r["asset_id"]: r["description"] for r in read_tsv(os.path.join(V2, "descriptions.tsv"))}
    with open(os.path.join(V2, "identity", "auto", "key.json"), encoding=ENC) as f:
        first = {x["asset_id"]: x for x in json.load(f)}
    src_blind = os.path.join(V2, "identity", "auto", "blind", "img")
    blind = os.path.join(OUT, "blind")
    os.makedirs(os.path.join(blind, "img"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "answers"), exist_ok=True)
    items = []
    for n, a in enumerate(sorted(a for a, r in ver.items() if r["route"] != "AUTO_ACCEPT"), 1):
        i, x = "R%03d" % n, first[a]
        panels = []
        for p in x["panels"]:
            q = "%s_%s" % (i, p.split("_", 1)[1])
            shutil.copy(os.path.join(src_blind, p), os.path.join(blind, "img", q))
            panels.append(q)
        s, f = a.split(":")
        for stage, sub in (("restore", "render"), ("strict", os.path.join("strict", "series"))):
            vj.compose(vj.sprite(a), os.path.join(V2, sub, s + ".PCK", f + ".png"),
                       os.path.join(blind, "img", "%s_%s.png" % (i, stage)))
            panels.append("%s_%s.png" % (i, stage))
        why = ["RESTORE rejected: " + restore.get(a, {}).get("note", "-"), "STRICT rejected: " + ver[a]["note"]]
        items.append({"id": i, "asset_id": a, "panels": panels, "facts": x["facts"] + why, "hypothesis": desc[a]})
    with open(os.path.join(blind, "IDENTIFY.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(IDENTIFY + RETHINK)
    batches = {}
    for k in range(0, len(items), BATCH):
        name = "B%02d" % (k // BATCH + 1)
        part = items[k:k + BATCH]
        batches[name] = [x["id"] for x in part]
        lines = ["# Batch %s (RETHINK)" % name, "", "Instructions: IDENTIFY.md in this folder, RETHINK round.", ""]
        for x in part:
            lines += ["## %s" % x["id"], "", "images: " + ", ".join("img/" + p for p in x["panels"]), "",
                      "facts:"] + x["facts"] + ["", "HYPOTHESIS (the description both renders used): " + x["hypothesis"], ""]
        with open(os.path.join(blind, name + ".md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines) + "\n")
    dump({"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "n": len(items), "batches": batches}, os.path.join(OUT, "pack.json"))
    dump(items, os.path.join(OUT, "key.json"))
    print("пересмотр: %d кадров, батчи %s" % (len(items), ", ".join(batches)))


def do_third_desc():
    """third/descriptions.tsv из итога пересмотра: STRICT - новое описание, если оно RENDER и хоть один судья
    назвал прежнее неверным (PARTLY/WRONG); прежнее верно у обоих - THIRD не нужен (рисует то же), остаток."""
    rows = read_tsv(os.path.join(OUT, "identity.tsv"))
    a, b, arb = load_answers("claude"), load_answers("codex"), load_answers("arbiter")
    out = []
    for r in rows:
        hyp = {a.get(r["id"], {}).get("hypothesis", ""), b.get(r["id"], {}).get("hypothesis", "")}
        if r["route"] == "WAIT":
            raise SystemExit("пересмотр не закончен: %s" % r["asset_id"])
        # Арбитр назвал предмет, но не уверен: THIRD всё равно рисуется по его описанию - рендер дешевле взгляда
        # человека, а не прошедший судей кадр и так уходит в конечный хвост (специалист 05.10: минимум касаний).
        z = arb.get(r["id"], {})
        if r["route"] == "HUMAN" and z.get("kind", "").upper() == "OBJECT" and r["description"].strip():
            r = dict(r, route="RENDER", source=r["source"] + " (арбитр не уверен - THIRD рисуется, хвост при FAIL)")
        route = ("STRICT" if r["route"] == "RENDER" and hyp - {"CORRECT"} else
                 "SAME_DESCRIPTION" if r["route"] == "RENDER" else r["route"])
        out.append({"asset_id": r["asset_id"], "route": route, "what_en": r["description"] if route == "STRICT" else "",
                    "source_ru": "пересмотр опознания (identity_auto rethink): " + r["source"]})
    d = os.path.join(V2, "third")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "descriptions.tsv")
    head = ["asset_id", "route", "what_en", "source_ru"]
    with open(p + ".tmp", "w", encoding=ENC, newline="") as f:
        w = csv.DictWriter(f, fieldnames=head, delimiter="\t", quoting=csv.QUOTE_NONE, lineterminator="\n")
        w.writeheader()
        for r in out:
            w.writerow({k: r[k].replace("\t", " ") for k in head})
    os.replace(p + ".tmp", p)
    print("THIRD: %s" % dict(Counter(r["route"] for r in out)))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["pack", "codex", "merge", "arbiter-pack", "final", "arbiter2-pack", "arbiter2",
                                    "rethink-pack", "third-desc"])
    ap.add_argument("--only", default="")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--round", default="first", choices=["first", "rethink"])
    ap.add_argument("--batch", default=V2, help="папка партии (по умолчанию PROD_TWO_PASS_V2)")
    a = ap.parse_args()
    os.chdir(ROOT)
    use_batch(a.batch)
    if a.cmd == "arbiter2-pack":
        return do_arbiter2_pack()
    if a.cmd == "arbiter2":
        return do_arbiter2(a.effort)
    if a.round == "rethink" or a.cmd in ("rethink-pack", "third-desc"):
        use_rethink()
    if a.cmd == "rethink-pack":
        return do_rethink_pack()
    if a.cmd == "third-desc":
        return do_third_desc()
    if a.cmd == "pack":
        do_pack()
    elif a.cmd == "codex":
        do_codex(set(x for x in a.only.split(",") if x), a.effort)
    elif a.cmd == "merge":
        do_merge()
    elif a.cmd == "arbiter-pack":
        do_arbiter_pack()
    else:
        do_final()


if __name__ == "__main__":
    main()
