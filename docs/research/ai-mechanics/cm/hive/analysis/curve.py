"""HIVE COMMAND CORE V0: the state of both sides at each player's turn start, active against D0 (read only). Only the lines of that very turn count, so a fallen unit cannot stay counted (the error of the 'live' columns of evalhive.py). Usage: curve.py <active dir> <D0 dir> <last turn>"""
import gzip
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
kv = re.compile(r"(\w+)=([^ ]*)")
last = int(sys.argv[3])


def read(d):
    with gzip.open(Path(d) / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        return [ln.rstrip("\n").split("\t")[-1] for ln in f]


def curve(lines):
    """turn -> (player alive, player hp, player armed-or-not ignored, hostile alive, hostile hp); turn is the one the player's start line carries"""
    tab = {}
    res = {}
    for s in lines:
        if s.startswith("[AISTATE] pstart "):
            k = dict(kv.findall(s))
            t = int(k["turn"])
            e = tab.setdefault(t, [0, 0, 0, 0])
            if k.get("status") in ("6", "7"):
                continue
            hp = int(k["hp"].split("/")[0])
            if k.get("faction") == "0":
                e[0] += 1
                e[1] += hp
            elif k.get("faction") == "1":
                e[2] += 1
                e[3] += hp
        elif s.startswith("[AIRESULT]"):
            res = dict(kv.findall(s))
    return tab, res


ta, ra = curve(read(sys.argv[1]))
td, rd = curve(read(sys.argv[2]))
print("at the player's turn start: player alive/hp | hostile alive/hp; active  //  D0")
for t in range(1, last + 2):
    fa = ta.get(t)
    fd = td.get(t)
    sa = f"{fa[0]:2d}/{fa[1]:4d} | {fa[2]:2d}/{fa[3]:5d}" if fa else "    -     |     -   "
    sd = f"{fd[0]:2d}/{fd[1]:4d} | {fd[2]:2d}/{fd[3]:5d}" if fd else "    -     |     -   "
    print(f"  {t:2d}: {sa}  //  {sd}")
for name, r in (("active", ra), ("D0", rd)):
    print(name, {k: r.get(k) for k in ("how", "turn", "pdead", "hdead", "phplost", "hattacks", "pattacks", "livesoldiers", "livealiens")})
