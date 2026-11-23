"""Сводный прогон модели обрушения (этап 0e) с зафиксированными правилами.

py -3.13 tools/collapse_summary.py lock            - записать замок правил (флаги, параметры, хэши кода и данных)
py -3.13 tools/collapse_summary.py intact FLAGS    - целые блоки групп 1-3: что висит до боя и почему; что держат
                                                      только экспериментальные правила (S, I, M, Q, N, B)
py -3.13 tools/collapse_summary.py maps FLAGS      - 90 собранных карт: висящее в проверенных и непроверенных клетках
py -3.13 tools/collapse_summary.py scen FLAGS      - все наборы ожиданий (v1, v2, матрица v3, уточнённые v4)

Висящее до боя модель не роняет никогда: это «не поддерживается моделью», а не обвал. Категории висящего:
  судно      - блок из vessels() или террейн группы 2/3 (корпус по классам MCD, шасси не размечены);
  край       - клетка на краю блока (опора может быть в соседнем блоке карты);
  спорно     - под частью (та же клетка этажом ниже или край) запись со спорной ролью или непросмотренная
               колонна/ферма, либо террейн группы 1 с низкой уверенностью;
  необъяснено - остальное, с тем, что под частью (пусто, висящая стена, предмет)."""
import collections, hashlib, json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import collapse_census as cc
import collapse_v2 as V
import collapse_v3 as T

ENC = "utf-8-sig"
OUT = "census/collapse/stage0e"
LOCK = OUT + "/rules.lock.txt"
FIXED = "RUADHSNQIMGOW"            # предлагаемый набор: без J (всё судно жёсткое) и без E (направленная консоль)
EXPERIMENTAL = "SIMQNB"            # правила-гипотезы: держат то, что без них висит
CODE = ["tools/collapse_census.py", "tools/collapse_v2.py", "tools/collapse_v3.py", "tools/collapse_summary.py"]
DATA = ["census/collapse/stage0c/roles.tsv", "census/collapse/ships/conn_blocks.tsv",
        "census/collapse/ships/terrain_groups.tsv", "census/collapse/stage0d/tree_offsets.tsv"]
EXPECTS = ["census/collapse/expect.tsv", "census/collapse/expect_v2.tsv", "census/collapse/expect_v3_matrix.tsv",
           "census/collapse/expect_v4_refined.tsv"]


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def cmd_lock():
    lines = ["правила сводного прогона этапа 0e, записано %s" % time.strftime("%Y-%m-%d %H:%M:%S"),
             "основной набор флагов %s; вариант %sB (B - концы балки только прямые опоры, эксперимент 0e)" % (FIXED, FIXED),
             "параметры: C=2 L=12 order=2 cp=1 LINTEL=%d L_TARP=%d L_ROOF=%d C_CANOPY=%d" % (
                 V.LINTEL, V.L_TARP, T.L_ROOF, T.C_CANOPY),
             "экспериментальные (не правила, а гипотезы): S (кровля 16, навес 0), I, M, Q, N, B; E и J в набор не входят"]
    for p in CODE + DATA + EXPECTS:
        lines.append("%s sha256 %s" % (p, sha(p)))
    with open(LOCK, "w", encoding=ENC) as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


def check_lock():
    if not os.path.exists(LOCK):
        raise SystemExit("нет замка %s - сначала lock" % LOCK)
    txt = open(LOCK, encoding=ENC).read()
    bad = [p for p in CODE + DATA + EXPECTS if sha(p) not in txt]
    print("замок правил:", "совпадает" if not bad else "НЕ СОВПАДАЕТ: " + ", ".join(bad))
    return not bad


def groups():
    g, low = {}, set()
    with open(T.TERRAIN_GROUPS_TSV, encoding=ENC) as f:
        for ln in f.read().splitlines()[1:]:
            r = ln.split("\t")
            g[r[0].upper()] = r[1]
            if len(r) > 3 and r[3] == "низкая":
                low.add(r[0].upper())
    return g, low


def disputed_records():
    out = set()
    with open("census/collapse/stage0c/roles.tsv", encoding=ENC) as f:
        lines = f.read().splitlines()
    head = lines[0].split("\t")
    for ln in lines[1:]:
        r = dict(zip(head, ln.split("\t")))
        if r.get("disputed") == "1" or (r.get("source") == "авто" and r.get("mcd_class") in ("column", "truss")):
            out.add((r["set"].upper(), int(r["idx"]), r["slot"]))
    return out


def below_keys(key):
    k, x, y, z = key
    if z == 0:
        return []
    return [("o", x, y, z - 1), ("f", x, y, z), ("w", x, y, z - 1), ("w", x + 1, y, z - 1),
            ("n", x, y, z - 1), ("n", x, y + 1, z - 1), ("f", x, y, z - 1)]


def under_label(blk, key, sup):
    k, x, y, z = key
    o = blk.parts.get(("o", x, y, z - 1))
    if k != "f":
        f = blk.parts.get(("f", x, y, z))
        if f is not None and ("f", x, y, z) not in sup:
            return "на висящем полу"
    if o is not None:
        return "предмет %s" % (o.get("role") or o.get("cls"))
    ws = [w for w in (("w", x, y, z - 1), ("w", x + 1, y, z - 1), ("n", x, y, z - 1), ("n", x, y + 1, z - 1))
          if w in blk.parts]
    if ws:
        return "стены ниже: " + ("висят" if not any(w in sup for w in ws) else "стоят")
    return "пусто"


def classify(blk, key, sup, vessel, terr_low, disp, sx, sy):
    k, x, y, z = key
    if vessel:
        return "судно", ""
    xs = (x,) if k != "w" else (x - 1, x)
    ys = (y,) if k != "n" else (y - 1, y)
    if any(c in (0, sx - 1) for c in xs) or any(c in (0, sy - 1) for c in ys):
        return "край", ""
    for b in [key] + below_keys(key):
        p = blk.parts.get(b)
        if p is not None and (p["set"].upper(), p["idx"], b[0]) in disp:
            return "спорно", "роль %s:%s" % (p["set"], p["idx"])
    if terr_low:
        return "спорно", "террейн низкой уверенности"
    return "необъяснено", under_label(blk, key, sup)


def cmd_intact(fl):
    check_lock()
    roles = V.load_roles()
    g, low = groups()
    disp = disputed_records()
    vs = T.vessels()
    tot = collections.Counter()
    cat = collections.Counter()
    sub = collections.Counter()
    expo = collections.Counter()
    rows = []
    t0 = time.time()
    n = 0
    for tname, kind, t, bname, blk, err, cache in cc.all_blocks(V.game_args()):
        grp = g.get(tname.upper(), "?")
        if blk is None or blk.sz < 2 or grp not in ("1", "2", "3"):
            continue
        V.apply_roles(blk, roles)
        n += 1
        vessel = (tname.upper(), bname.upper()) in vs or grp in ("2", "3")
        sup, _ = T.evaluate3(blk, frozenset(), fl)
        up = [k for k in blk.parts if k[3] > 0]
        hung = [k for k in up if k not in sup]
        tot["up"] += len(up)
        tot["hung"] += len(hung)
        bc = collections.Counter()
        for key in hung:
            c, why = classify(blk, key, sup, vessel, tname.upper() in low, disp, blk.sx, blk.sy)
            cat[c] += 1
            bc[c] += 1
            if c in ("необъяснено", "спорно"):
                sub[(c, why)] += 1
        only = {}
        for e in EXPERIMENTAL:
            if e not in fl:
                continue
            s2, _ = T.evaluate3(blk, frozenset(), fl.replace(e, ""))
            only[e] = sum(1 for k in up if k in sup and k not in s2)
            expo[e] += only[e]
        if hung or any(only.values()):
            rows.append([tname, bname, grp, "судно" if vessel else "", len(up), len(hung)] +
                        [bc[c] for c in ("судно", "край", "спорно", "необъяснено")] +
                        [only.get(e, "") for e in EXPERIMENTAL] + [T.compress(sorted(hung))[:300]])
        if n % 200 == 0:
            print("  блоков %d, %.0f с" % (n, time.time() - t0), flush=True)
    tag = "intact_" + fl
    cc.write_tsv(OUT + "/%s.tsv" % tag, ["terrain", "block", "group", "vessel", "parts_up", "hung",
                                          "h_vessel", "h_edge", "h_disputed", "h_unexplained"] +
                 ["only_" + e for e in EXPERIMENTAL] + ["hung_parts"], rows)
    res = {"flags": fl, "blocks": n, "parts_up": tot["up"], "hung": tot["hung"], "by_category": dict(cat),
           "detail": {"%s | %s" % k: v for k, v in sub.most_common(40)},
           "held_only_by_experimental": dict(expo)}
    with open(OUT + "/%s.json" % tag, "w", encoding=ENC) as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))


def cmd_maps(fl):
    check_lock()
    import collapse_battles as cb
    roles = V.load_roles()
    g, low = groups()
    disp = disputed_records()
    d = cb.Data(V.game_args())
    names = sorted(n[:-4] + ".sav" for n in os.listdir(V.OUT + "/source") if n.endswith(".pkl"))
    tot = collections.Counter()
    cat = collections.Counter()
    byterr = collections.defaultdict(collections.Counter)
    rows = []
    for name in names:
        m, src = V.load_map(d, name, roles)
        ver = V.verified_cells(d, name, m, src)
        grp = g.get(src["terrain"].upper(), "?")
        sup, _ = T.evaluate3(m, frozenset(), fl)
        up = [k for k in m.parts if k[3] > 0]
        hv = hu = 0
        mc = collections.Counter()
        for key in up:
            v = (key[1], key[2], key[3]) in ver
            tot["up_ver" if v else "up_unver"] += 1
            if key in sup:
                continue
            if not v:
                hu += 1
                cat["непроверенная клетка (реконструкция)"] += 1
                continue
            hv += 1
            bt = ver[(key[1], key[2], key[3])][0].upper()
            vessel = g.get(bt) in ("2", "3")
            c, why = classify(m, key, sup, vessel, bt in low, disp, m.sx, m.sy)
            c = {"край": "край карты"}.get(c, c)
            cat[c] += 1
            mc[c] += 1
            byterr[bt][c] += 1
        tot["hung_ver"] += hv
        tot["hung_unver"] += hu
        rows.append([name, src["terrain"], grp, len(up), hv, hu] +
                    [mc[c] for c in ("судно", "край карты", "спорно", "необъяснено")])
        print(name, src["terrain"], "верх", len(up), "висит в проверенных", hv, "в непроверенных", hu, flush=True)
    tag = "maps_" + fl
    cc.write_tsv(OUT + "/%s.tsv" % tag, ["save", "terrain", "group", "parts_up", "hung_verified", "hung_unverified",
                                          "h_vessel", "h_map_edge", "h_disputed", "h_unexplained"], rows)
    res = {"flags": fl, "maps": len(names), "total": dict(tot), "by_category": dict(cat),
           "by_block_terrain": {t: dict(c) for t, c in sorted(byterr.items(), key=lambda kv: -sum(kv[1].values()))[:40]}}
    with open(OUT + "/%s.json" % tag, "w", encoding=ENC) as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: res[k] for k in ("flags", "maps", "total", "by_category")}, ensure_ascii=False, indent=1))


def cmd_scen(fl):
    check_lock()
    roles = V.load_roles()
    out = {}
    for path in EXPECTS[:3]:
        expect, res = T.run_expect(path, [fl], roles)
        rr = {e["id"]: res[e["id"]][fl] for e in expect}
        out[os.path.basename(path)] = rr
    vc = {}
    for name, rr in out.items():
        c = collections.Counter(r["verdict"] for r in rr.values())
        vc[name] = dict(c)
        print("%-22s %s" % (name, dict(c)))
        for i, r in rr.items():
            if r["verdict"] == "FAIL" or r["verdict"] == "PASS*":
                print("   %-8s %-5s устояло %d/%d упало %d/%d висело %d | %s %s" % (
                    i, r["verdict"], r["stood"], r["must_fall"], r["fell"], r["must_stand"], r["hung_before"],
                    r["stood_keys"][:120], r["fell_keys"][:120]))
    with open(OUT + "/scen_%s.json" % fl, "w", encoding=ENC) as f:
        json.dump({"flags": fl, "verdicts": vc, "result": out}, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "lock":
        cmd_lock()
    elif cmd == "intact":
        cmd_intact(sys.argv[2])
    elif cmd == "maps":
        cmd_maps(sys.argv[2])
    elif cmd == "scen":
        cmd_scen(sys.argv[2])
