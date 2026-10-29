#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""pedia_recraft.py - перекрафт картинок педии по заметкам Vitali со страницы pedia_notes (29.10).

Вход - art\pedia_regen\<круг>\edits.json: по картинке, что изменить (core - английский для модели,
переведён с заметки), с чего рисовать (base: hd - наша HD из установки, h18 - картинка 18+, orig - только
оригинал) и куда встанет выбранное (slot). Кандидаты на картинку:
  e1, e2 - правка поверх base, два зерна: «измени только это, остальное как на фото» (сила 1.0);
  o1     - заново из оригинала (ESRGAN), промпт серии hd (pedia_batch.spec_for) плюс та же правка;
           при base h18 не делается - Vitali прямо велел брать 18+; при base orig - o1 и o2.
Выход: <круг>\<имя>__<вариант>__<метка>.png через pedia_ab.py новой моделью. В мод ничего не пишет:
выбор - на странице pedia_notes.py --round <круг>, подключение - после выбора Vitali.

--install кладёт выбранное (<круг>\picks.tsv, последняя строка на картинку) в обе копии мода hd (R-087):
slot normal - hd\UI, slot 18 - hd_18+\UI. Прежний файл с .pal.txt - в <круг>\_prev\<копия>\..., журнал -
<круг>\install_<время>.tsv. keep18 в edits.json: прежняя HD раздета, а hd_18+ её нет - она переезжает туда.
Нет .pal.txt (у картинки не было HD) - пишется по палитре оригинала, как upscale_ui.py.

    py -3.13 tools\gpuq.py add --name pedia_recraft_v1 --prio 9 --preemptible -- C:/Python313/python.exe E:/OpenXCom/tools/hdart/pedia_recraft.py
    py -3.13 tools\hdart\pedia_recraft.py --no-gen            (только jobs.json)
    py -3.13 tools\hdart\pedia_recraft.py --install --dry-run
"""
import argparse
import csv
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import time

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import pedia_batch as pb                                # noqa: E402

HD = os.path.join(pb.PIR, "hd", "hd", "UI")
H18 = os.path.join(pb.PIR, "hd", "hd_18+", "UI")
EDIT = "Edit this photograph. Change only the following: "
KEEP_EDIT = (" Everything not named above stays exactly as in the photograph: the composition and framing, the pose, "
             "the head turn and the gaze, the body, the hair colour and hairstyle, the clothing, the objects in the "
             "hands, the background with all its colours and light. The same photographic look: a real camera, "
             "realistic skin.")
NEG_EDIT = pb.NEG_PHOTO + pb.NEG_STRICT + pb.NEG_GAZE


def seed(stem, n):
    return (int(hashlib.md5(stem.encode("utf-8")).hexdigest()[:8], 16) + n) & 0x7FFFFFFF


def fill(s, d):
    return s.replace("{YOUNG}", d["YOUNG"]).replace("{NEG_YOUNG}", d["NEG_YOUNG"])


def jobs_for(d, origs, plan, caps):
    jobs, miss = [], []
    for e in d["edits"]:
        stem, k = e["stem"], e["stem"].lower()
        if k not in origs:
            miss.append(stem)
            continue
        core, neg = fill(e.get("core", ""), d), fill(e.get("neg", ""), d)
        var = {}
        if e["base"] in ("hd", "h18"):
            src = os.path.abspath(os.path.join(HD if e["base"] == "hd" else H18, stem + ".png"))
            if not os.path.exists(src):
                miss.append(stem + " (" + e["base"] + ")")
                continue
            for i in (1, 2):
                var["e%d" % i] = {"prompt": EDIT + core + KEEP_EDIT, "neg": NEG_EDIT + neg, "strength": 1.0,
                                  "input": src, "seed": seed(stem, i)}
        if e["base"] != "h18":
            add = (" In addition: " + core) if core else ""
            if k in plan and k in caps:
                s = pb.spec_for("hd", plan[k], caps[k])
                o = {"prompt": s["prompt"] + add, "neg": s["neg"] + neg, "strength": s["strength"]}
            elif e.get("desc"):
                nude = e.get("nude", False)
                o = {"prompt": pb.PHOTO + e["desc"] + pb.PEOPLE + (pb.UNDERWEAR if nude else pb.AS_DRAWN) + add +
                     pb.STRICT, "neg": pb.NEG_PHOTO + (pb.NEG_NUDE_HD if nude else "") + pb.NEG_STRICT + pb.NEG_GAZE +
                     neg, "strength": 0.92 if nude else 0.85}
            else:
                o = None
            if o:
                for i in ((1, 2) if e["base"] == "orig" else (1,)):
                    var["o%d" % i] = dict(o, seed=seed(stem, 10 + i))
        if var:
            jobs.append({"file": origs[k], "variants": var})
    return jobs, miss


MODS = {"game": os.path.join(pb.PIR, "hd"), "repo": os.path.join("user", "mods", "hd")}
PICKED = ("e1", "e2", "o1", "o2")


def picks_of(out):
    """{stem: строка picks.tsv} - последняя строка на картинку, только выбранный кандидат"""
    last = {}
    with io.open(os.path.join(out, "picks.tsv"), encoding="utf-8-sig") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            last[r["stem"]] = r
    return {s: r for s, r in last.items() if r["pick"] in PICKED and r["file"]}


def put(src, dst, dry):
    """dst заменяется копией src; прежний файл удаляется, а не перезаписывается - он может быть жёсткой
    ссылкой на тот же файл другого слота или другой копии"""
    if not dry:
        if os.path.exists(dst):
            os.remove(dst)
        shutil.copyfile(src, dst)


def install(out, d, origs, dry):
    edits = {e["stem"]: e for e in d["edits"]}
    picks = picks_of(out)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    log, bad = [], []
    for stem, r in sorted(picks.items()):
        e, src = edits.get(stem), os.path.join(out, r["file"])
        if not e or not os.path.exists(src) or stem.lower() not in origs:
            bad.append(stem)
            continue
        for name, root in MODS.items():
            ui, a18 = os.path.join(root, "hd", "UI"), os.path.join(root, "hd_18+", "UI")
            dst_dir = a18 if e.get("slot") == "18" else ui
            if not os.path.isdir(dst_dir):
                log.append((name, stem, r["pick"], "нет папки " + dst_dir))
                continue
            prev = os.path.join(out, "_prev", name, os.path.relpath(dst_dir, root))
            what = []
            for ext in (".png", ".pal.txt"):
                old = os.path.join(dst_dir, stem + ext)
                if os.path.exists(old) and not dry:
                    os.makedirs(prev, exist_ok=True)
                    shutil.copy2(old, os.path.join(prev, stem + ext))
            if e.get("keep18") and dst_dir == ui and os.path.exists(os.path.join(ui, stem + ".png")) \
                    and not os.path.exists(os.path.join(a18, stem + ".png")):
                what.append("прежняя HD -> hd_18+")
                if not dry:
                    os.makedirs(a18, exist_ok=True)
                    for ext in (".png", ".pal.txt"):
                        if os.path.exists(os.path.join(ui, stem + ext)):
                            shutil.copy2(os.path.join(ui, stem + ext), os.path.join(a18, stem + ext))
            put(src, os.path.join(dst_dir, stem + ".png"), dry)
            what.append(os.path.relpath(dst_dir, root))
            pal = os.path.join(dst_dir, stem + ".pal.txt")
            if not os.path.exists(pal):
                what.append(".pal.txt по оригиналу")
                if not dry:
                    p = Image.open(os.path.join(pb.ORIG, origs[stem.lower()])).getpalette()[:768]
                    p += [0] * (768 - len(p))
                    with open(pal, "w") as f:
                        f.write("\n".join("%d %d %d" % tuple(p[i:i + 3]) for i in range(0, 768, 3)) + "\n")
            log.append((name, stem, r["pick"], ", ".join(what)))
    for row in log:
        print("  %-5s %-32s %-3s %s" % row)
    print("выбрано %d, поставлено %d%s%s" % (len(picks), len(picks) - len(bad),
                                             ("; мимо: " + ", ".join(bad)) if bad else "", " (dry-run)" if dry else ""))
    if not dry:
        jl = os.path.join(out, "install_%s.tsv" % stamp)
        with io.open(jl, "w", encoding="utf-8-sig") as f:
            for row in log:
                f.write("\t".join(row) + "\n")
        print("журнал: %s" % jl)
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--round", default="recraft_v1", help="папка круга в art\\pedia_regen")
    ap.add_argument("--tag", default="r1")
    ap.add_argument("--no-gen", dest="no_gen", action="store_true")
    ap.add_argument("--install", action="store_true", help="выбранное из picks.tsv - в мод hd")
    ap.add_argument("--dry-run", dest="dry", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.chdir(ROOT)
    out = os.path.join(pb.ROOT, a.round)
    d = pb.load(os.path.join(out, "edits.json"), None)
    origs = {os.path.splitext(n)[0].lower(): n for n in os.listdir(pb.ORIG)}
    if a.install:
        return install(out, d, origs, a.dry)
    plan = pb.load(os.path.join(pb.ROOT, "plan.json"), {}).get("info", {})
    caps = pb.load(os.path.join(pb.ROOT, "captions.json"), {})
    jobs, miss = jobs_for(d, origs, plan, caps)
    jpath = os.path.join(out, "jobs.json")
    pb.save(jpath, jobs)
    print("круг %s: картинок %d, кандидатов %d%s" % (a.round, len(jobs), sum(len(j["variants"]) for j in jobs),
                                                    ("; мимо: " + ", ".join(miss)) if miss else ""), flush=True)
    if a.no_gen:
        return 0
    cmd = [pb.PY_NEW, os.path.join(HERE, "pedia_ab.py"), "--model", "new", "--jobs", jpath, "--out", out,
           "--tag", a.tag]
    print(" ".join(cmd), flush=True)
    return subprocess.call(cmd)                         # 75 - уступил карту, очередь перезапустит с места


if __name__ == "__main__":
    sys.exit(main())
