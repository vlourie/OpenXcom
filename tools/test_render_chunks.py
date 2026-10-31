#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_chunks: процесс рендера живёт не больше N картинок, между процессами сверка хэшей журнала.
Без модели: дочерний скрипт - подделка, рисует PNG и пишет renders.jsonl как struct_probe.Render.record;
"память" подделки падает на 6-м рендере одного процесса (как OOM #301/#303).

    py -3.13 tools/test_render_chunks.py
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SUP = os.path.join(HERE, "hdart", "render_chunks.py")
sys.stdout.reconfigure(encoding="utf-8")

FAIL = []

CHILD = r'''
import argparse, hashlib, json, os, sys
from PIL import Image
ap = argparse.ArgumentParser()
ap.add_argument("--out"); ap.add_argument("--items", type=int); ap.add_argument("--max-renders", type=int, default=0)
ap.add_argument("--oom-after", type=int, default=5); ap.add_argument("--mode", default="")
a = ap.parse_args()
os.makedirs(os.path.join(a.out, "raw"), exist_ok=True)
done = 0
for i in range(a.items):
    raw = os.path.join(a.out, "raw", "%02d.png" % i).replace(os.sep, "/")
    if os.path.exists(raw):
        continue
    if a.max_renders and done >= a.max_renders:
        if a.mode == "corrupt":
            p = os.path.join(a.out, "raw", "00.png")
            Image.new("RGB", (8, 8), (9, 9, 9)).save(p)
        sys.exit(75)
    if a.mode == "stuck":
        sys.exit(75)
    if done >= a.oom_after:
        print("CUDA error: out of memory"); sys.exit(1)
    Image.new("RGB", (8, 8), (i * 20 % 255, 0, 0)).save(raw)
    h = hashlib.sha256(open(raw, "rb").read()).hexdigest()
    with open(os.path.join(a.out, "renders.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"raw": raw, "sha256": h}) + "\n")
    done += 1
sys.exit(0)
'''


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        FAIL.append(name)


def run(tmp, items, max_renders, mode="", oom_after=5):
    out = os.path.join(tmp, "out")
    cmd = [sys.executable, SUP, "--out", out, "--max-renders", str(max_renders), "--",
           sys.executable, os.path.join(tmp, "child.py"), "--out", out, "--items", str(items),
           "--oom-after", str(oom_after)] + (["--mode", mode] if mode else [])
    p = subprocess.run(cmd, cwd=tmp, capture_output=True, text=True, encoding="utf-8")
    return p.returncode, p.stdout + p.stderr, out


def fresh():
    tmp = tempfile.mkdtemp(prefix="rchunks_")
    with open(os.path.join(tmp, "child.py"), "w", encoding="utf-8") as f:
        f.write(CHILD)
    return tmp


def crashes(text):
    m = re.search(r"падений (\d+)", text)
    return int(m.group(1)) if m else -1


tmp = fresh()
code, text, out = run(tmp, 10, 4)
check("10 ответов при лимите 4: код 0 (%d)" % code, code == 0)
check("процессов 3", "процессов 3," in text)
check("падений 0 (%d)" % crashes(text), crashes(text) == 0)
check("в журнале 10", "ответов в журнале 10" in text)
shutil.rmtree(tmp)

# контроль: тот же прогон без лимита - процесс копит память и падает, перезапуск после падения
tmp = fresh()
code, text, out = run(tmp, 10, 100)
check("контроль: без лимита процесс падает (падений %d)" % crashes(text), crashes(text) >= 1)
check("контроль: и всё же доходит до конца по падениям (код %d)" % code, code == 0)
shutil.rmtree(tmp)

tmp = fresh()
code, text, out = run(tmp, 6, 2, mode="corrupt")
check("ответ переписан после процесса - стоп (код %d)" % code, code != 0 and "sha256" in text)
shutil.rmtree(tmp)

tmp = fresh()
code, text, out = run(tmp, 6, 2, mode="stuck")
check("лимит без новых ответов - стоп, не бесконечный круг (код %d)" % code,
      code != 0 and "новых ответов нет" in text)
shutil.rmtree(tmp)

tmp = fresh()
code, text, out = run(tmp, 6, 4, oom_after=0)
check("падает сразу каждый раз - стоп после 2 подряд (код %d)" % code, code != 0 and "подряд" in text)
shutil.rmtree(tmp)

print("итог: %s" % ("всё прошло" if not FAIL else "упало %d" % len(FAIL)))
sys.exit(1 if FAIL else 0)
