"""COUNTERFIRE: for every hostile casualty of a hostile turn, the hostile decision during which it happened (the last
[AIDECIDE] before it) and the reactions logged in that decision's window.

  py -3.13 -I fl_who.py <log (timestamps cut)> <turn>
"""
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
KV = re.compile(r"(\w+)=(\S+)")
T = sys.argv[2]
dec, react = None, []
for l in open(sys.argv[1], encoding="utf-8", errors="replace"):
    l = l.rstrip("\n")
    if l.startswith("[AIDECIDE] "):
        d = dict(KV.findall(l.split(" hu=")[0]))
        dec = d if d.get("turn") == T and d.get("side") == "1" else None
        react = []
    elif dec and l.startswith("[AIEVENT] ") and " what=reaction " in l:
        react.append(dict(KV.findall(l)).get("unit"))
    elif dec and l.startswith("[AICASUALTY] "):
        c = dict(KV.findall(l))
        if c.get("turn") == T and c.get("vfaction") == "1":
            print(f"{c['victim']} {c['how']} at {c['pos']} by {c['killer']} {c['weapon'][:20]} | during {dec['unit']} n={dec['n']} "
                  f"act={dec['act']} to={dec['to']} aim={dec['aim']} from={dec.get('from')} | reactions so far: {','.join(react) or '-'}")
