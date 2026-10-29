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

    py -3.13 tools\gpuq.py add --name pedia_recraft_v1 --prio 9 --preemptible -- C:/Python313/python.exe E:/OpenXCom/tools/hdart/pedia_recraft.py
    py -3.13 tools\hdart\pedia_recraft.py --no-gen            (только jobs.json)
"""
import argparse
import hashlib
import io
import json
import os
import subprocess
import sys

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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--round", default="recraft_v1", help="папка круга в art\\pedia_regen")
    ap.add_argument("--tag", default="r1")
    ap.add_argument("--no-gen", dest="no_gen", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.chdir(ROOT)
    out = os.path.join(pb.ROOT, a.round)
    d = pb.load(os.path.join(out, "edits.json"), None)
    origs = {os.path.splitext(n)[0].lower(): n for n in os.listdir(pb.ORIG)}
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
