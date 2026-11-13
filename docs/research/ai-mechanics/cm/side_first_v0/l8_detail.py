"""SIDE-FIRST COMBAT V0.1, L8: every psi or capture action with the target's state before and after, per-turn counts, what the units that ever used psi did, the director's special/veto events, and attacks on a target already out.
args: zip:prefix:arm ..."""
import gzip
import io
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
KV = re.compile(r"(\w+)=([^ ]*)")
PSI = {"13": "psi", "14": "mc"}
NAME = {"2": "ход", "6": "бросок", "7": "авто", "8": "снимок", "9": "прицел", "10": "рук", "12": "вп", "13": "пси", "14": "захват"}


def load(z, label):
    raw = gzip.open(io.BytesIO(z.read(f"out/{label}/openxcom.log.gz")), "rt", encoding="utf-8", errors="replace").read().splitlines()
    return [s.split("\t")[-1] for s in raw]


def battle(ls, label):
    print("---", label)
    typ = {}
    state = {}
    psi_units = Counter()
    by_turn = Counter()
    pend = None
    pend_i = 0
    rows = []
    for i, s in enumerate(ls):
        if s.startswith("[AISTATE] "):
            d = dict(KV.findall(s))
            if d.get("unit") and d.get("type"):
                typ[d["unit"]] = d["type"]
        elif s.startswith("[AIDECIDE] "):
            d = dict(KV.findall(s.split(" hu=")[0]))
            if d.get("side") == "1" and d.get("act") in PSI:
                psi_units[d["unit"]] += 1
                by_turn[int(d["turn"])] += 1
                rows.append((i, d))
    for i, d in rows:
        after = []
        for t in ls[i + 1:i + 40]:
            if t.startswith("[AICASUALTY]") or t.startswith("[AISCD] ") and '"special"' in t:
                after.append(t[:210])
            if t.startswith("[AIEXEC] "):
                x = json.loads(t[9:])
                print(f"  ход {d['turn']} {typ.get(d['unit'], d['unit'])} {PSI[d['act']]} aim={d.get('aim')} ОВ {x.get('spent')} dmg {x.get('dmg')} stun {x.get('stunned')} downed {x.get('downed')}")
                break
        for a in after[:2]:
            print("     ", a)
    print("  пси/захват по ходам:", sorted(by_turn.items()))
    return set(psi_units), typ


def behaviour(ls, types):
    """the actions of units of the given types, per turn, by the kind of action"""
    c = defaultdict(Counter)
    typ = {}
    for s in ls:
        if s.startswith("[AISTATE] "):
            d = dict(KV.findall(s))
            if d.get("unit") and d.get("type"):
                typ[d["unit"]] = d["type"]
        elif s.startswith("[AIDECIDE] "):
            d = dict(KV.findall(s.split(" hu=")[0]))
            if d.get("side") == "1" and typ.get(d["unit"]) in types:
                c[int(d["turn"])][NAME.get(d.get("act"), d.get("act"))] += 1
    return c


def director(ls):
    c = Counter()
    ex = []
    outs = {}
    for s in ls:
        if not s.startswith("[AISCD] "):
            continue
        j = json.loads(s[8:])
        e = j.get("ev")
        if e == "act":
            c["act_" + j["kind"]] += 1
            if j["kind"] == "T" and len(ex) < 6:
                ex.append(s[8:220])
            if j["kind"] == "A" and outs.get(j["target"]) is not None and outs[j["target"]] <= j["turn"]:
                print("   attack_on_out:", s[8:300])
        elif e == "result" and j["kind"] == "A" and j.get("tOut"):
            outs[j["target"]] = j["turn"]
        elif e in ("special", "veto"):
            c[e] += 1
            if e == "special" and len(ex) < 6:
                ex.append(s[8:220])
    return c, ex


seen_types = set()
done = []
for a in sys.argv[1:]:
    zp, prefix, arm = a.rsplit(":", 2)
    z = zipfile.ZipFile(zp)
    for s_ in (1, 2, 3, 4):
        label = f"{prefix}_{arm}_L8_s{s_}"
        ls = load(z, label)
        units, typ = battle(ls, label)
        seen_types |= {typ[u] for u in units if u in typ}
        c, ex = director(ls)
        print("  директор:", dict(sorted(c.items())))
        for e in ex:
            print("    ", e)
        done.append((label, ls))
print("типы, применявшие пси:", sorted(seen_types))
for label, ls in done:
    c = behaviour(ls, seen_types)
    print(label, {t: dict(v) for t, v in sorted(c.items())})
