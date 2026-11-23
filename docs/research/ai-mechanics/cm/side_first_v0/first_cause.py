"""SIDE-FIRST COMBAT: the first causal point of each pair. The record lines of D and XN compared in order (time stamps off): the first line that differs, what D decided there and what the director did.
Proves that the two arms are the same battle up to that line: the common prefix is printed. args: zip prefix"""
import gzip
import io
import json
import re
import sys
import zipfile
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
TAGS = ("[AIDECIDE]", "[AIEXEC]", "[AICASUALTY]", "[AISTATE]")
KV = re.compile(r"(\w+)=([^ ]*)")
MISSIONS = ["M3", "M8", "L4", "L8"]


def load(z, label):
    raw = gzip.open(io.BytesIO(z.read(f"out/{label}/openxcom.log.gz")), "rt", encoding="utf-8", errors="replace").read().splitlines()
    rec, scd = [], []
    for s in raw:
        s = s.split("\t")[-1]
        if s.startswith(TAGS):
            rec.append(re.sub(r'"(us|ms|t_us)":\d+,?', "", s))
            if s.startswith("[AIDECIDE]"):
                scd.append(None)
        elif s.startswith("[AISCD] "):
            scd.append(json.loads(s[8:]))
    return rec, scd


def main():
    z = zipfile.ZipFile(sys.argv[1])
    P = sys.argv[2]
    kinds = Counter()
    for m in MISSIONS:
        for s in (1, 2, 3, 4):
            a, _ = load(z, f"{P}_D_{m}_s{s}")
            b, sc = load(z, f"{P}_XN_{m}_s{s}")
            i = 0
            n = min(len(a), len(b))
            while i < n and a[i] == b[i]:
                i += 1
            x = dict(KV.findall(a[i].split(" hu=")[0])) if i < len(a) else {}
            y = dict(KV.findall(b[i].split(" hu=")[0])) if i < len(b) else {}
            first = next((j for j in sc if j and j.get("ev") in ("act", "veto", "special")), None)
            k = first.get("ev") + ":" + first.get("kind", "") if first else "-"
            kinds[k] += 1
            d_txt = f"ход {x.get('turn')} сторона {x.get('side')} юнит {x.get('unit')} act {x.get('act')} к {x.get('to')} оружие {x.get('weapon')}"
            n_txt = f"юнит {y.get('unit')} act {y.get('act')} к {y.get('to')} оружие {y.get('weapon')}"
            print(f"{m} s{s}: общий префикс {i} строк; D: {d_txt}; XN: {n_txt}; первое действие директора {k} {json.dumps({q: first.get(q) for q in ('actor', 'target', 'to', 'w', 'eff', 'net') if q in first}, ensure_ascii=False) if first else ''}"[:330])
    print("первое действие директора по парам:", dict(kinds))


main()
