"""STRIKE-V0: reaction fire of the hostile side in the battles with the order on against D0 (what the spent TU may cost on the player's
turn), and why hostile walk decisions in the shadow run spent nothing (the first word of the AIEXEC trail).

  py -3.13 -I fl_sv4.py <out dir> <D0 prefix> <shadow prefix> <on prefix>"""
import gzip
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")


def lines(d):
    for raw in gzip.open(d / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace"):
        yield raw.rstrip("\n").split("\t", 2)[-1]


def hostile_reactions(d):
    return sum(1 for b in lines(d) if b.startswith("[AIEVENT] ") and "what=reaction" in b and int(dict(KV.findall(b))["unit"]) >= 1000000)


out, pd, ps, pn = Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
a = b = 0
for nd in sorted(out.glob(f"{pn}_*")):
    dd = out / nd.name.replace(f"{pn}_", f"{pd}_", 1)
    x, y = hostile_reactions(dd), hostile_reactions(nd)
    a += x
    b += y
    print(f"  {nd.name[len(pn) + 1:]:8s} hostile reactions D0 {x} on {y}")
print(f"  together D0 {a} on {b}")

why = Counter()
modes = Counter()
walks = zero = 0
for d in sorted(out.glob(f"{ps}_*")):
    pend = None
    for s in lines(d):
        if s.startswith("[AIDECIDE] "):
            pend = dict(KV.findall(s.split(" hu=")[0]))
        elif s.startswith("[AIEXEC] ") and pend:
            x = json.loads(s[9:])
            if str(x["unit"]) == pend["unit"] and pend["side"] == "1" and pend["act"] == "2":
                walks += 1
                if not x.get("spent"):
                    zero += 1
                    modes[pend["mode"]] += 1
                    t = x.get("trail") or ["(no trail)"]
                    why[t[-1].split(" ")[0]] += 1
            pend = None
print(f"hostile walk decisions in the shadow run {walks}, spent nothing {zero}")
print("  by mode: " + ", ".join(f"{k}={v}" for k, v in modes.most_common()))
print("  by the trail's last word: " + ", ".join(f"{k}={v}" for k, v in why.most_common(12)))
