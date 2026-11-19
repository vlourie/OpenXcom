"""SIDE-FIRST COMBAT V0.1: does a battle log hold what is needed to count director acts by units marked dontReselect? The tags of the log, the keys of [AIREC].state and of the director's events, any field naming the mark or the second pass. args: zip label"""
import gzip
import io
import json
import re
import sys
import zipfile
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
z = zipfile.ZipFile(sys.argv[1])
ls = [s.split("\t")[-1] for s in gzip.open(io.BytesIO(z.read(f"out/{sys.argv[2]}/openxcom.log.gz")), "rt", encoding="utf-8", errors="replace").read().splitlines()]
tags = Counter()
rec_keys = Counter()
state_keys = Counter()
scd = Counter()
hits = Counter()
for s in ls:
    m = re.match(r"\[(\w+)\]", s)
    if m:
        tags[m.group(1)] += 1
    if re.search(r"reselect|secondmove|second_move|secondpass|wrapped|\bpass\b", s, re.I):
        hits[(m.group(1) if m else s[:30])] += 1
    if s.startswith("[AIREC] "):
        j = json.loads(s[8:])
        rec_keys.update(j.keys())
        state_keys.update(j["state"].keys())
    elif s.startswith("[AISCD] "):
        j = json.loads(s[8:])
        scd.update(f"{j.get('ev')}.{k}" for k in j)
print("теги:", dict(tags))
print("ключи AIREC:", sorted(rec_keys))
print("ключи AIREC.state:", sorted(state_keys))
print("события директора:", sorted({k.split(".")[0] for k in scd}))
print("строки со словами про пометку и проход:", dict(hits))
for s in ls:
    if re.search(r"reselect|secondmove|second_move|secondpass|wrapped|\bpass\b", s, re.I):
        print("  пример:", s[:200])
        break
