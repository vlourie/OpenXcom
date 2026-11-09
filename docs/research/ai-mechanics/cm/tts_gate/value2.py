"""NATURAL GATE, read only: one line per candidate. Accuracy with the range drop (RuleItem::calculateLimits, keys from the installed Piratez rules, defaults aim 200 auto 7 snap 15 dropoff 2),
T's health, T's attacks afterwards, the weapon's record, D0's B. Args: zip, Piratez root, then battle|turn|B|T, battle = L9_s2 or @path to a plain log."""
import gzip
import io
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import gate_lib as G

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ATT = {5, 6, 7, 8, 9, 10, 11, 12}
RULES = (Path(sys.argv[2]) / "user" / "mods" / "Piratez" / "Ruleset" / "Piratez.rul").read_text(encoding="utf-8", errors="replace").splitlines()
RK = re.compile(r"^\s+(aimRange|snapRange|autoRange|dropoff|maxRange|refNode):\s*(\S+)")


def weapon(name):
    out = {"aimRange": 200, "autoRange": 7, "snapRange": 15, "dropoff": 2, "src": "default"}
    for i, s in enumerate(RULES):
        if re.match(r"^\s*- type: " + re.escape(name) + r"\s*$", s):
            for t in RULES[i + 1:i + 90]:
                if re.match(r"^\s*- type: ", t) or re.match(r"^\S", t):
                    break
                m = RK.match(t)
                if m:
                    if m.group(1) == "refNode":
                        out["src"] = "ref"
                    else:
                        out[m.group(1)] = int(m.group(2))
            if out["src"] == "default":
                out["src"] = "rul"
            break
    return out


z = zipfile.ZipFile(sys.argv[1])
cache = {}
for q in sys.argv[3:]:
    name, turn, B, T = q.split("|")
    turn, B, T = int(turn), int(B), int(T)
    if name not in cache:
        if name.startswith("@"):
            L = [s.rstrip("\n").split("\t")[-1] for s in open(name[1:], encoding="utf-8", errors="replace")]
        else:
            raw = z.read(f"out/scpa_D_{name}/openxcom.log.gz")
            L = [s.rstrip("\n").split("\t")[-1] for s in gzip.open(io.BytesIO(raw), "rt", encoding="utf-8", errors="replace")]
        cache[name] = (L, G.Battle(L))
    L, b = cache[name]
    hp0 = hp1 = w1 = None
    fell = None
    for s in L:
        if s.startswith("[AISTATE]") and f" unit={T} " in s:
            k = G.kv(s)
            t, ev = int(k.get("turn", -1)), s.split(" ")[1]
            if t == turn and ev == "aistart":
                hp0 = k.get("hp")
            if t == turn + 1 and ev == "pstart":
                hp1, w1 = k.get("hp"), k.get("wounds")
        elif s.startswith("[AICASUALTY]") and f"victim={T} " in s:
            k = G.kv(s)
            fell = (int(k["turn"]), k["how"])
    n = harm = dmg = 0
    for d in b.by_unit.get(T, []):
        if turn <= d["turn"] <= turn + 2 and d["t"] in ATT:
            e = b.exec.get(d["rec"]) or {}
            n += 1
            dmg += e.get("dmg") or 0
            harm += 1 if (e.get("dmg") or 0) > 0 else 0
    sh = None
    for d in b.by_unit.get(B, []):
        if d["turn"] == turn and d["side"] == 1 and d["acts"]:
            sh = G.shots_by_target(b.acts(d["acts"])).get(T)
            if sh:
                break
    w = weapon(sh["w"])
    up = {7: w["autoRange"], 8: w["snapRange"], 9: w["aimRange"]}[sh["mode"]]
    pd = sh["p"] - max(0, sh["d"] - up) * w["dropoff"]
    acts = hit = dm = 0
    for d in b.dec:
        if d["side"] == 1 and d["t"] in G.SHOT and d["w"] == sh["w"]:
            e = b.exec.get(d["rec"]) or {}
            acts += 1
            hit += 1 if (e.get("dmg") or 0) > 0 else 0
            dm += e.get("dmg") or 0
    bs = [d for d in b.by_unit.get(B, []) if d["turn"] == turn and d["side"] == 1]
    ba = [d for d in bs if d["t"] in ATT]
    bd = sum((b.exec.get(d["rec"]) or {}).get("dmg") or 0 for d in ba)
    print(f"{Path(name).stem if name.startswith('@') else name} t{turn} B{B} T{T} d{sh['d']} {sh['w']} m{sh['mode']} {sh['tu']}TU p{sh['p']} range {up} drop {w['dropoff']} ({w['src']}) p_d {pd} | T hp {hp0}>{hp1} w{w1} fell {fell} | T attacks t..t+2 {n} wounding {harm} dmg {dmg} | weapon acts {acts} wounding {hit} dmg {dm} | B acts {len(bs)} attacks {len(ba)} dmg {bd}")
