"""Movement diagnosis: reads a battle log into lines and keeps every unit's place by line (read only)."""
import gzip
import json
import re
from pathlib import Path

OUT = Path("C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/256842df-d34a-4d31-a77d-3f9de8ee29de/scratchpad/hive/res/out")
KV = re.compile(r"(\w+)=([^ ]*)")
POS = re.compile(r"\((-?\d+),(-?\d+),(-?\d+)\)")


def read(n):
    with gzip.open(OUT / n / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace") as f:
        return [ln.rstrip("\n").split("\t")[-1] for ln in f]


def kv(s):
    return dict(KV.findall(s))


def tup(p):
    m = POS.match(p)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def cells(list_text):
    """A candidate list: cell -> time units of the way there, the engine's own reachable set."""
    out = {}
    for c in list_text.split(";"):
        m = re.match(r"(-?\d+)\.(-?\d+)\.(-?\d+):(\d+)", c)
        if m:
            out[(int(m.group(1)), int(m.group(2)), int(m.group(3)))] = int(m.group(4))
    return out


def place_events(L):
    """(line, unit, place, source, dead) in log order: each place a unit is said to stand on, from every line that names one."""
    ev = []
    for i, s in enumerate(L):
        if s.startswith("[HIVEUNIT]"):
            k = kv(s)
            ev.append((i, int(k["id"]), tup(k["pos"]), "init", int(k["status"]) >= 3 if False else False))
        elif s.startswith("[HIVEORD]"):
            k = kv(s)
            if "at" in k and k.get("unit"):
                ev.append((i, int(k["unit"]), tup(k["at"]), "ord", False))
        elif s.startswith("[HIVEREACH]"):
            k = kv(s)
            ev.append((i, int(k["unit"]), tup(k["at"]), "reach", False))
        elif s.startswith("[AIDECIDE]"):
            k = kv(s)
            ev.append((i, int(k["unit"]), tup(k["from"]), "decide", False))
        elif s.startswith("[AIEXEC]"):
            j = json.loads(s[len("[AIEXEC] "):])
            if "pos" in j:
                ev.append((i, int(j["unit"]), tuple(j["pos"]), "exec", False))
        elif s.startswith("[AISTATE]"):
            k = kv(s)
            if "pos" in k:
                ev.append((i, int(k["unit"]), tup(k["pos"]), "state", False))
        elif s.startswith("[AICASUALTY]"):
            k = kv(s)
            ev.append((i, int(k["victim"]), tup(k["pos"]), "casualty", True))
    return ev


class Places:
    """Who stands where at a given line, by the last line that named the unit before it."""

    def __init__(self, L):
        self.ev = place_events(L)

    def at(self, line):
        here, out = {}, set()
        for i, u, p, src, dead in self.ev:
            if i > line:
                break
            if dead:
                out.add(u)
            if p:
                here[u] = p
        return here, out
