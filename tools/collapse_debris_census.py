"""Завал v2, этап A (docs/research/collapse-debris-mechanics-2026-10-21.md): «похожие клетки» из наборов самих
участков заголовка обрушения. Только чтение установки Пираток и заголовка; в игре ничего не меняет.

Ярусы по записи MCD (тип 53: 0 пол, 1 западная стена, 2 северная, 3 объект):
- крошка: объект, проходим, 1-4 слоя LOFT;
- куча: объект, проходим, 5-7 слоёв LOFT;
- бурелом: объект, проходим, горит (Flammable < 255 и Fuel > 0), 2-8 слоёв;
- ствол: стена (тип 1 или 2), низкая (не выше 8 слоёв, верх клетки пуст), горит.
Всем: не дверь, не лифт, броня < 255, не взрывчатка (HE_Strength 55), не цель миссии (Target_Type 59), не поднимает
бойца (T_Level 48: склон, лестница), не светит (Light_Source 58); объекту - ход от 2 TU.
Пометка die: в запись что-то превращается при разрушении (так отбирал этап 0 завала v1).

Ключ строки завала - первый набор блока (как rubble_cov), материал - как HdFx::materialOf.
    py -3.13 tools/collapse_debris_census.py
-> census/collapse/debris/candidates.tsv, groups.tsv, blocks.tsv"""
import os
import re
import sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import collapse_census as cc   # noqa: E402
import collapse_v2 as V        # noqa: E402

HEADER = "src/Battlescape/CollapsePilotData.bin"
OUT = "census/collapse/debris"
RUBBLE_V1 = ["URBANWAR", "URBAN", "COMMERCE", "MILBARR", "VILBAN", "IDT_FARM", "URBAN40K", "BARN_JUNK", "BARN"]
TIERS = ("крошка", "куча", "бурелом", "ствол")


def header_blocks():
    import collapse_blob
    return [(b.label, b.name, [s.upper() for s in b.sets], b.experimental == 1) for b in collapse_blob.load(HEADER)]


def has(s, *keys):
    return any(k in s for k in keys)


def material(step, setname):
    """HdFx::materialOf по шагу и имени набора."""
    m = {1: "metal", 3: "soft", 4: "water", 5: "sand"}.get(step)
    if m:
        return m
    s = setname.upper()
    if has(s, "SNOW", "POLAR", "ICE", "ARCTIC"):
        return "snow"
    if has(s, "DESERT", "SAND", "DUNE"):
        return "sand"
    if has(s, "WATER", "SEA", "SWAMP"):
        return "water"
    if has(s, "FOREST", "JUNGLE", "FARM", "GRASS", "CULT", "FIELD"):
        return "grass"
    if has(s, "BARN", "WOOD", "SHACK", "HUT"):
        return "wood"
    if has(s, "URBAN", "ROAD", "CITY", "STREET", "MOUNT", "ROCK", "CAVE", "STONE"):
        return "stone"
    return "snow" if step == 6 else "stone" if step == 0 else "dirt"


def kind_of(mat):
    """Вид завала v1 (CollapsePilot rubbleKind)."""
    return "дерево" if mat in ("wood", "soft") else "металл" if mat == "metal" else "камень"


def main():
    mod_dir, files, loft_path, loft_occ = cc.open_data(V.game_args())
    blocks = header_blocks()
    mcd, raw = {}, {}

    def recs(s):
        if s not in mcd:
            mcd[s] = cc.read_mcd(files, s, loft_occ, {})
            p = files.find(os.path.join("TERRAIN", s + ".MCD"))
            raw[s] = open(p, "rb").read() if p else b""
        return mcd[s]

    # наборы участков заголовка, затем все прочие наборы мода и мастера - доноры: сейв хранит набор по имени
    # (SavedBattleGame «mapdatasets», Mod::getMapDataSet), так что бой может взять обломок чужого набора
    header_sets = {s for _, _, ss, _ in blocks for s in ss}
    order = [s for _, _, ss, _ in blocks for s in ss]
    for root in files.roots:
        d = os.path.join(root, "TERRAIN")
        if os.path.isdir(d):
            order += sorted(os.path.splitext(f)[0].upper() for f in os.listdir(d) if f.upper().endswith(".MCD"))
    cand = {}                                        # (set, idx) -> строка
    for s in order:
        if (s, -1) in cand:
            continue
        cand[(s, -1)] = None
        rs = recs(s)
        targets = {r["die"] for r in rs if r["die"]}
        src = defaultdict(Counter)
        for r in rs:
            if r["die"]:
                src[r["die"]][("пол", "з.стена", "с.стена", "объект")[min(r["type"], 3)]] += 1
        for i, r in enumerate(rs):
            b = raw[s][i * cc.REC:(i + 1) * cc.REC]
            if len(b) < cc.REC:
                continue
            # склоны и лестницы (T_Level) поднимают бойца, фонари светят (Light_Source 58) - не обломки
            if r["door"] or r["ufo_door"] or b[34] or r["armor"] >= 255 or b[55] or b[59] or r["t_level"] or b[58]:
                continue
            flam, fuel, step, frame = b[45], b[57], b[52], b[0]
            burns = flam < 255 and fuel > 0
            nl, walk, typ = r["nl"], 2 <= r["tu_walk"] < 255, r["type"]   # ход 0-1 TU - трава, не завал
            tiers = []
            if typ == 3 and walk and 1 <= nl <= 4:
                tiers.append("крошка")
            if typ == 3 and walk and 5 <= nl <= 7:
                tiers.append("куча")
            if typ == 3 and walk and burns and 2 <= nl <= 8:
                tiers.append("бурелом")
            if typ in (1, 2) and burns and nl <= 8 and not (r["layers"][11] or r["layers"][10]):
                tiers.append("ствол")
            if not tiers:
                continue
            mat = material(step, s)
            cand[(s, i)] = dict(set=s, idx=i, frame=frame, tiers=tiers, slot=("пол", "з.стена", "с.стена", "объект")[min(typ, 3)],
                                nl=nl, tu=r["tu_walk"], armor=r["armor"], stop_los=r["stop_los"], flam=flam,
                                fuel=fuel, mat=mat, kind=kind_of(mat), die=r["die"], is_target=i in targets,
                                own=s in header_sets,
                                src=" ".join("%s %d" % kv for kv in src[i].most_common()))
    cand = {k: v for k, v in cand.items() if v}

    groups = defaultdict(lambda: dict(blocks=[], exp=0, sets=Counter()))
    brow = []
    for lab, name, ss, exp in blocks:
        v1 = next((k for k in RUBBLE_V1 if k in ss), None)
        key = ss[0] if ss else "?"
        have = {t: sorted({(s, i) for (s, i), c in cand.items() if s in ss and t in c["tiers"]}) for t in TIERS}
        brow.append((lab, name, "эксп" if exp else "игрокам", v1 or "", key,
                     *[len(have[t]) for t in TIERS], " ".join(ss)))
        if v1:
            continue
        g = groups[key]
        g["blocks"].append(lab)
        g["exp"] += exp
        for s in ss:
            g["sets"][s] += 1

    os.makedirs(OUT, exist_ok=True)
    cc.write_tsv(os.path.join(OUT, "candidates.tsv"),
                 ["set", "idx", "frame", "tiers", "slot", "loft", "tu", "armor", "stop_los", "flammable", "fuel",
                  "material", "kind", "die", "die_target", "from", "own"],
                 [(c["set"], c["idx"], c["frame"], ",".join(c["tiers"]), c["slot"], c["nl"], c["tu"], c["armor"],
                   c["stop_los"], c["flam"], c["fuel"], c["mat"], c["kind"], c["die"], int(c["is_target"]), c["src"], int(c["own"]))
                  for c in sorted(cand.values(), key=lambda c: (c["set"], c["idx"]))])
    cc.write_tsv(os.path.join(OUT, "blocks.tsv"),
                 ["label", "block", "to", "rubble_v1", "key"] + list(TIERS) + ["sets"], brow)
    grow = []
    for key, g in sorted(groups.items(), key=lambda kv: -len(kv[1]["blocks"])):
        n = len(g["blocks"])
        common = [s for s, c in g["sets"].items() if c == n]
        cnt = {t: sum(1 for (s, i), c in cand.items() if s in common and t in c["tiers"]) for t in TIERS}
        kinds = Counter(c["kind"] for (s, i), c in cand.items() if s in common and "крошка" in c["tiers"])
        grow.append((key, n - g["exp"], g["exp"], *[cnt[t] for t in TIERS],
                     " ".join("%s %d" % kv for kv in kinds.most_common()), " ".join(sorted(common))))
    cc.write_tsv(os.path.join(OUT, "groups.tsv"),
                 ["key", "blocks_players", "blocks_exp"] + list(TIERS) + ["crumb_kinds", "common_sets"], grow)

    tot = Counter()
    for c in cand.values():
        for t in c["tiers"]:
            tot[t] += 1
    print("кандидатов записей:", len(cand), dict(tot))
    pl = [r for r in brow if r[2] == "игрокам" and not r[3]]
    print("блоков игрокам без завала v1:", len(pl))
    for i, t in enumerate(TIERS):
        print("  есть %-8s %d" % (t, sum(1 for r in pl if r[5 + i])))
    print("  нет ничего   %d" % sum(1 for r in pl if not any(r[5:9])))
    print("групп по ключу:", len(groups))
    for r in grow[:30]:
        print("  ", *r[:8])


if __name__ == "__main__":
    main()
