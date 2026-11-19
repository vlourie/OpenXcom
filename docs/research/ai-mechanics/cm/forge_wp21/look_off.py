"""AI FORGE WP2.1, final OFF: against the archived D0, A1 and C1, by the engine's own lines: every decision's fields, every kind of line, the raw differences, and which exe and flags the run itself recorded."""
import gzip
import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import AIForgeCounterfactualRunner as rr

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
FIELDS = ("turn", "side", "unit", "n", "from", "tu", "mode", "act", "to", "run", "kneel", "aim", "weapon", "seen", "hu", "hi", "ho", "hou", "hm", "hr", "hr0", "ha0", "ha")
KV = re.compile(r"(\w+)=(\S+)")


def kinds(lines):
    return Counter(re.match(r"(\[AI[A-Z0-9_]*\])", s).group(1) for s in lines)


def decides(run):
    return [dict(KV.findall(s)) for s in run.game if s.startswith("[AIDECIDE]")]


off = rr.Run("OFF")
print("forge lines in OFF", len(off.forge), "dumps", len(off.dumps), "branch", len(off.branch), "legal", len(off.legal), "time", len(off.time))
print("search paths", [s for s in off.lines if "/exe/" in s][:3])
print("engine line kinds", dict(kinds(off.game)))
out = {}
for other in ("arch:D0", "A1", "C1"):
    o = rr.Run(other)
    g = rr.game_compare("OFF", other)
    da, db = decides(off), decides(o)
    per = {f: sum(1 for x, y in zip(da, db) if x.get(f) != y.get(f)) for f in FIELDS}
    by = {k: [v, kinds(o.game)[k]] for k, v in kinds(off.game).items()}
    print(f"== OFF / {other}: identical {g['identical']}, lines {g['game_lines']}, first {g['first_difference']}")
    print("   decisions", len(da), len(db), "fields that differ", {k: v for k, v in per.items() if v})
    print("   kinds that differ in count", {k: v for k, v in by.items() if v[0] != v[1]})
    print("   raw differences", g["raw_differences"]["lines"], [[a[-40:], b[-40:]] for a, b in g["raw_differences"]["first"]])
    out[other] = {"identical": g["identical"], "game_lines": g["game_lines"], "decisions": [len(da), len(db)], "fields_that_differ": {k: v for k, v in per.items() if v}, "raw_lines": g["raw_differences"]["lines"], "first_difference": g["first_difference"]}
print("normalised", rr.normalised_fields(off.lines))
print("result", off.result().get("how"), off.result().get("turn"), off.result().get("vms"), off.result().get("ms"), {k: off.result().get(k) for k in ("hdead", "phplost", "pdead", "hmoves", "hattacks")})
# what the arena recorded of the run itself
files = {}
for name, zp, label in (("OFF", rr.RES / "res_fxOFF.zip", "fxOFF_YO_L8_s1"), ("D0", rr.ARCHIVE_D0, "sfF_D_L8_s1"), ("A1", rr.RES / "res_fxA1.zip", "fxA1_YA_L8_s1")):
    with zipfile.ZipFile(zp) as z:
        files[name] = {k: z.read(f"arena/{label}.{k}.txt").decode("utf-8", errors="replace") for k in ("prov", "result", "casualties")}
print("-- prov OFF\n" + files["OFF"]["prov"][:1500])
for k in ("prov", "result", "casualties"):
    a = files["OFF"][k].replace("fxOFF_YO", "L").replace("/exe/FX/", "/exe/X/")
    b = files["D0"][k].replace("sfF_D", "L").replace("/exe/D0/", "/exe/X/")
    print(f"-- {k}: OFF / D0 the same apart from the label and the exe's folder:", a == b)
    if a != b:
        for x, y in zip(a.splitlines(), b.splitlines()):
            if x != y:
                print("   OFF", x[:300])
                print("   D0 ", y[:300])
(Path(__file__).resolve().parent / "WP21_OFF.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8-sig")
