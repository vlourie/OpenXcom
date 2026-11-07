"""Наборы террейна, которые игра показывает под подменой палитры боя (enviroEffects paletteTransformations), R-314.

Под подменой HdPaletteShift красит HD-кадр сеткой сдвигов, и кадр точными цветами палитры (pixel_lines) выходит
не тем цветом (MANSIONFLOOR_MAG:30 - бирюзовые и пурпурные ступени, CARGO1:48 - R-320). Принимать такой кадр
можно только по игровому кадру под той же подменой.

Окружение боя - у миссии (alienDeployments.enviroEffects), иначе у террейна (BattlescapeGenerator:549);
террейн без миссий - своё. Набор -> террейны по .index/mod/Piratez/set_terrains.tsv (tools/index_mod.py).
state: always - подмена у всех миссий всех его террейнов, some - у части.

    py -3.13 tools/hdart/palette_shift_sets.py          # пересобрать art/ground/queue/palshift.json и сводку
Из кода: load() -> {НАБОР: {"state", "envs": {окружение: миссий}, "to": {окружение: {палитра: палитра}}}},
save_env(путь сейва) -> (enviroEffectsType или "", depth), shifted(инфо набора, окружение, глубина).
"""
import collections
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IDX = ROOT / ".index" / "mod" / "Piratez"
OUT = ROOT / "art" / "ground" / "queue" / "palshift.json"
ENC = "utf-8-sig"
_CACHE = {}


def build():
    csv.field_size_limit(1 << 30)
    vals = collections.defaultdict(dict)
    with open(IDX / "rul" / "values.tsv", encoding=ENC, newline="") as f:
        for row in csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE):        # R-109
            if len(row) >= 4 and row[0] in ("enviroEffects", "terrains", "alienDeployments"):
                try:
                    vals[(row[0], row[1])][row[2]] = json.loads(row[3])
                except ValueError:
                    pass
    to = {k[1]: v["paletteTransformations"] for k, v in vals.items()
          if k[0] == "enviroEffects" and v.get("paletteTransformations")}
    if not to:
        raise SystemExit("в values.tsv ни одного окружения с подменой палитры - индекс рулсетов не тот")
    tenv = {k[1]: v.get("enviroEffects") for k, v in vals.items() if k[0] == "terrains"}
    uses = collections.defaultdict(list)
    for k, v in vals.items():
        if k[0] == "alienDeployments":
            for t in v.get("terrains") or []:
                uses[t].append(v.get("enviroEffects") or tenv.get(t))
    out = {}
    with open(IDX / "set_terrains.tsv", encoding=ENC, newline="") as f:
        sets = collections.defaultdict(list)
        for row in csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            if row and row[0] != "set":
                sets[row[0].upper()] += [t.strip() for t in row[1].split(",") if t.strip()]
    for s, ts in sorted(sets.items()):
        envs = [e for t in ts for e in (uses.get(t) or [tenv.get(t)])]
        sh = [e for e in envs if e in to]
        if sh:
            c = collections.Counter(sh)
            out[s] = {"state": "always" if len(sh) == len(envs) else "some", "envs": dict(c),
                      "to": {e: to[e] for e in c}}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding=ENC)
    return out


def load():
    if "sets" not in _CACHE:
        _CACHE["sets"] = json.loads(OUT.read_text(encoding=ENC)) if OUT.exists() else build()
    return _CACHE["sets"]


def save_env(path):
    """(enviroEffectsType, depth) сейва боя: строки battleGame, как их пишет SavedBattleGame::save"""
    t = Path(path).read_text(encoding="utf-8", errors="replace")
    e = re.search(r"(?m)^  enviroEffectsType: (\S+)", t)
    d = re.search(r"(?m)^  depth: (\d+)", t)
    return (e.group(1) if e else ""), (int(d.group(1)) if d else 0)


def shifted(info, env, depth=0):
    """игра красит набор подменой в бою с этим окружением и глубиной (syncHdPaletteShift: PAL_BATTLESCAPE или
    PAL_BATTLESCAPE_<глубина>)"""
    if not info or env not in info["to"]:
        return False
    return ("PAL_BATTLESCAPE" if depth == 0 else "PAL_BATTLESCAPE_%d" % depth) in info["to"][env]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    out = build()
    c = collections.Counter(v["state"] for v in out.values())
    e = collections.Counter(x for v in out.values() for x in v["envs"])
    print("%s: наборов под подменой %d (always %d, some %d)" % (OUT, len(out), c["always"], c["some"]))
    for k, n in e.most_common():
        print("  %-34s наборов %d" % (k, n))


if __name__ == "__main__":
    main()
