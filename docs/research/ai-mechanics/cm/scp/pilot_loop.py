"""The turns where [AISCHED] picks exceed 8 per candidate (sc_check's loop test): picks, candidates, sites, chosen units, and
what the chosen units decided in that turn - an endless re-pick or a few units with many cheap picks.

  py -3.13 -I pilot_loop.py <out dir> <label> [<control label>]"""
import gzip
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")


def scan(label):
    picks, dec = defaultdict(list), defaultdict(list)
    for raw in gzip.open(Path(sys.argv[1]) / label / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace"):
        body = raw.rstrip("\n").split("\t", 2)[-1]
        if body.startswith("[AISCHED] "):
            d = dict(KV.findall(body))
            picks[int(d["turn"])].append(d)
        elif body.startswith("[AIDECIDE] "):
            d = dict(KV.findall(body.split(" hu=")[0]))
            if d["side"] == "1":
                dec[int(d["turn"])].append(d)
    return picks, dec


picks, dec = scan(sys.argv[2])
for t, ps in sorted(picks.items()):
    nc = max(len(p["cands"].split(",")) for p in ps)
    if len(ps) > 8 * nc:
        print(f"turn {t}: picks {len(ps)}, candidates max {nc}, sites {dict(Counter(p['site'] for p in ps))}, "
              f"why {dict(Counter(p['why'] for p in ps))}")
        print(f"  chosen {dict(Counter(p['chosen'] for p in ps))}; decisions in the turn {len(dec[t])} "
              f"{dict(Counter(d['unit'] + ':' + d['act'] for d in dec[t]))}")
        for p in ps[:12]:
            print(f"   pick {p['pick']} pass {p['pass']} site {p['site']} wrap {p['wrap']} left {p['left']} chosen {p['chosen']} why {p['why']}")
        if len(sys.argv) > 3:
            _, dc = scan(sys.argv[3])
            print(f"  control decisions in turn {t}: {len(dc[t])} {dict(Counter(d['unit'] + ':' + d['act'] for d in dc[t]))}")
