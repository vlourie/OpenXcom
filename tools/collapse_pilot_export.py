#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Пилот обрушения в движке (этап 1): выгрузка модели M0j4 (M0j3 плюс консоль стены, tools/collapse_v7d.py)
с разметкой v2 и слоем связей M0j5 (tools/collapse_v8.py, с 21.10) для зданий пилота
(дом амбара и бункер - collapse_pilot_scen.PILOT, третья партия - collapse_pilot3_scen.PILOT) в C++ и
проверка переноса.

Модель под замками не меняется и не копируется целиком: на этих зданиях живы не все её ветки. Всё,
что зависит только от целого блока (тип пола, настил, стойки навеса, несущее целого блока carry0, касание
стены с предметом ниже, цели разметки, роль и класс), считается здесь моделью и выгружается готовым; в бою
считается только ядро evaluate2w (плита Z, перемычки k с консолью стены, X, a, b) и слой разметки v7c.

Ветки, которых в переносе нет (деревья D, корпус G/O, особые роли A, STRUCTURE разметки, половинная консоль c),
останавливают выгрузку, если в здании есть хоть одна их часть.

    py -3.13 tools\collapse_pilot_export.py check    упрощённая копия на Python против evaluate7c: сценарии
                                                     pilot_scen.tsv и случайные наборы - бит в бит
    py -3.13 tools\collapse_pilot_export.py export   src/Battlescape/CollapsePilotData.h и векторы
                                                     census/collapse/pilot1/vectors.txt (с проверкой check)
"""
import hashlib
import os
import random
import sys
import time
from collections import Counter, deque

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

ENC = "utf-8-sig"
OUT = "census/collapse/pilot1"
HEADER = "src/Battlescape/CollapsePilotData.h"
VECTORS = OUT + "/vectors.txt"
SCENS = ["census/collapse/stage0m/pilot_scen.tsv", "census/collapse/pilot3/pilot_scen.tsv",
         "census/collapse/pilot4/pilot_scen.tsv", "census/collapse/pilot5/pilot_scen.tsv",
         "census/collapse/pilot6/pilot_scen.tsv", "census/collapse/pilot7/pilot_scen.tsv",
         "census/collapse/pilot8/pilot_scen.tsv", "census/collapse/pilot9/pilot_scen.tsv",
         "census/collapse/partial9/partial_scen.tsv", "census/collapse/pilot10/pilot_scen.tsv",
         "census/collapse/partial10/partial_scen.tsv", "census/collapse/pilot11/pilot_scen.tsv",
         "census/collapse/partial11/partial_scen.tsv", "census/collapse/pilot12/pilot_scen.tsv",
         "census/collapse/partial12/partial_scen.tsv", "census/collapse/pilot13/pilot_scen.tsv",
         "census/collapse/partial13/partial_scen.tsv"]
BOX = {"амбар": (2, 11, 2, 11), "бункер": (1, 7, 1, 7)}     # здание пилота: клетки x0..x1, y0..y1
LABEL_EN = {"амбар": "barn", "бункер": "bunker"}            # метка здания в логе игры
# здания, у которых остались провальные сценарии (census/collapse/pilot3/fail_cases.md): в заголовке с флагом
# experimental, движок берёт их только в сборке стенда (OXCE_AI_DEV), игрокам не выходят
EXPERIMENTAL = {
                # 21.10 модель M0j5 (collapse_v8): сценарии всех партий перепрогнаны, M0j4 - census/collapse/m0j4_results;
                # к игрокам ушли 30 зданий (banditbarn1-2, urbandio04, westown16, culta17, cultafarm06, cultasol01,
                # culthouse05, cultafarm03, cultafarm05, cultnew17, chemtown91, urbandio03, induslum27, culta19, cultnew16,
                # comrcurban11, comrcurban53, expterror24, madurban33, madurban37, urban05, urban18, urban19,
                # comrcurban23, comrcurban58, induslum10, urbanwaste15, urbanwasteroadns10, urbanjunk41)
                # четвёртая партия: провальные сценарии в census/collapse/pilot4/pilot_result.tsv
                "chemtown94", "culta30", "madurban27", "madurban28",
                # пятая партия: census/collapse/pilot5/pilot_result.tsv; chemtown13 - сценариев нет, не проверен
                "chemtown92", "chemtown13",
                # шестая партия: census/collapse/pilot6/pilot_result.tsv
                "comrcurban22",
                # седьмая партия: разбор census/collapse/pilot7/split.tsv (tools/collapse_pilot7_split.py) - провал
                # рода МОДЕЛЬ или лишнее падение в частичных сценариях
                "urbandio02",
                # восьмая партия (деревья вне модели): census/collapse/pilot8/split.tsv (tools/collapse_pilot8_split.py)
                "chemtown04", "chemtown20r", "comrcurban06", "comrcurbanmey02", "urbanmy",
                # десятая партия (охват после ветки D): census/collapse/pilot10/split.tsv (tools/collapse_pilot10_split.py)
                "comrcurbanhuge01",
                # одиннадцатая партия (разобранные виды предметов): census/collapse/pilot11/split.tsv
                "chemtownghoulchemtown04",
                # двенадцатая партия (второй лист видов): census/collapse/pilot12/split.tsv
                "lamvillagemiddlebig01",
                # тринадцатая партия (третий лист видов): census/collapse/pilot13/split.tsv
                "chemtown95"}
# urban14, urban17, madurban19, 22-26, culta18, cultafarm21, urbanjunk11, comrcurban50: частичное падение
# не доказано (census/collapse/partial/model_result.tsv, R-353), но по решению Vitali 15.10 в сборке игрока -
# приёмку ведут игроки
# третья партия: рамки и метки в collapse_pilot3_scen (метка обязана быть уникальной - по ней removal_sets
# берёт сценарии здания)
# восьмая партия (collapse_pilot8_scen.TREES_OUT): деревья вне модели - части keep заголовка
TREES_OUT = set()
# ветка D в переносе (лес и столбы, слово Vitali 20.10): колонны и кроны collapse_v5.tree_structure5 по целому
# блоку выгружаются готовыми, в бою - только держание collapse_v4.tree_hold4 (tie all)
TREES_IN = set()
# имя модели в заголовке, если не имя блока (collapse_pilot10_scen.NAME_AS): одноимённые блоки другой модели на
# других террейнах - CollapsePilot ищет модель сейва по имени
NAME_AS = {}
KIND ={"f": 0, "w": 1, "n": 2, "o": 3}                   # O_FLOOR, O_WESTWALL, O_NORTHWALL, O_OBJECT
N_RANDOM = 1500
SEED = 20261008
SOURCES = ["tools/collapse_v7c.py", "tools/collapse_v7b.py", "tools/collapse_v7.py", "tools/collapse_v6.py",
           "tools/collapse_v5.py", "tools/collapse_v4.py", "tools/collapse_v3.py", "tools/collapse_v2.py", "tools/collapse_attach_v2.py",
           "tools/collapse_pilot_scen.py", "tools/collapse_pilot3_scen.py", "tools/collapse_pilot4_scen.py",
           "tools/collapse_pilot5_scen.py", "tools/collapse_pilot6_scen.py", "tools/collapse_pilot7_scen.py",
           "tools/collapse_pilot8_scen.py", "tools/collapse_pilot9_scen.py", "tools/collapse_pilot10_scen.py",
           "tools/collapse_pilot11_scen.py", "tools/collapse_pilot12_scen.py", "tools/collapse_pilot13_scen.py",
           "tools/collapse_v7d.py", "tools/collapse_v8.py",
           "tools/collapse_pilot_export.py"]


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def inside(k, b):
    sl, x, y, z = k
    x0, x1, y0, y1 = b
    if sl == "w":
        return x0 <= x <= x1 + 1 and y0 <= y <= y1
    if sl == "n":
        return x0 <= x <= x1 and y0 <= y <= y1 + 1
    return x0 <= x <= x1 and y0 <= y <= y1


# ------------------------------------------------------------------ статика из модели

def static(C, blk, label):
    """Плоские данные блока: всё, что считается по целому блоку, - готовым."""
    import collapse_v2 as V
    import collapse_v3 as T
    import collapse_v5 as H
    import collapse_v6 as M
    import collapse_v7 as J
    import collapse_v7b as K
    import collapse_v7d as D
    flags = C.MODEL
    f2 = "".join(c for c in flags if c not in T.V3_FLAGS).replace("V", "")
    stop = []
    if (blk.terrain.upper(), blk.name.upper()) in T.vessels() or blk.terrain.upper() in T.hull_terrains():
        stop.append("судно или террейн без земли (G/O)")
    # восьмая партия: деревья вне модели (части keep, правило collapse_pilot8_scen.tree_parts), прочие здания
    # с деревьями - стоп
    if label in TREES_OUT:
        import collapse_pilot8_scen as P8
        tree = P8.tree_parts(C, blk)
    else:
        tree = set()
    with C.marked_roles(blk):
        cls = {k: V.eff_cls(k, p, f2) for k, p in blk.parts.items()}
        role = {k: p.get("role", "") for k, p in blk.parts.items()}
        cols, crowns = H.tree_structure5(blk, cls, role)
        if (cols or crowns) and label not in TREES_OUT and label not in TREES_IN:
            stop.append("деревья (D): стволов %d, крон %d" % (len(cols), len(crowns)))
        keys = sorted((k for k in blk.parts if k not in tree), key=lambda k: (k[3], KIND[k[0]], k[2], k[1]))
        idx = {k: i for i, k in enumerate(keys)}
        for k, p in blk.parts.items():
            if role[k] in V.SPECIAL:
                stop.append("особая роль %s у %s" % (role[k], k))
            if role[k] == "HULL":
                stop.append("роль HULL у %s" % (k,))
            m = p.get("mark")
            if m and m[0] == "STRUCTURE":
                stop.append("разметка STRUCTURE у %s" % (k,))
        if "c" in flags:
            stop.append("флаг c (половинная консоль)")
        if stop:
            raise SystemExit("выгрузка %s остановлена: %s" % (label, "; ".join(stop)))
        with K.items_only():
            attach_roles = set(J.ATTACH_ROLES)
            carry0 = D.intact_carry(blk, f2, dict(C=2, L=12, mass_rule=True, order=2, carry_rule="any",
                                                  run_c=2, roof_reach=1))
        ft = T.floor_types(blk)
        tg = C.marked_parts(blk)
        parts = []
        for k in keys:
            p = blk.parts[k]
            sl, x, y, z = k
            e = dict(key=k, set=p["set"].upper(), mcd=p["idx"], kind=KIND[sl], x=x, y=y, z=z,
                     bearing=cls[k] in V.BEARING, furn=cls[k] == "furniture",
                     attach=role[k] in attach_roles or bool(p.get("attach")),
                     carry0=k in carry0, edge=[], contact=0, liml=12, can=False, posted0=False, light=False,
                     mark=0, targets=[], inbox=inside(k, BOX[label]))
            if sl == "o":
                e["edge"] = list(__import__("collapse_census").EDGE_NB.get(p["rec"]["big_wall"], ()))
            if sl in ("w", "n") and z > 0:
                ok = blk.lv[z - 1]["o"].get((x, y))
                if ok is not None:
                    e["contact"] = len(J.part_foot(blk, k, "bottom") & J.part_foot(blk, ok, "top"))
            if sl == "f" and z > 0:
                t = ft.get(k)
                e["liml"] = max(12, T.L_ROOF) if t == ("помещ", "кровля") else 12
                e["can"] = t == ("улица", "кровля")
                e["posted0"] = (x, y) in M.canopy_posted_intact(blk, z, carry0)
                e["light"] = (x, y) in H.light_intact(blk, z)
            if k in tg:
                kind_, ts = tg[k]
                if any(t in tree for t in ts):
                    raise SystemExit("выгрузка %s остановлена: разметка %s цепляет дерево" % (label, k))
                e["mark"] = 1 if ts else 2            # 1 - цели есть, 2 - место без цели (держится как ядро)
                e["targets"] = [idx[t] for t in ts]
            parts.append(e)
        keep = [dict(key=k, set=blk.parts[k]["set"].upper(), mcd=blk.parts[k]["idx"], kind=KIND[k[0]], x=k[1],
                     y=k[2], z=k[3]) for k in sorted(tree, key=lambda k: (k[3], KIND[k[0]], k[2], k[1]))]
        # ветка D: колонна - номера частей снизу вверх, кусок кроны - (номер, этаж нужды, номера колонн)
        tcols, tcrowns = [], []
        if label in TREES_IN:
            cxy = sorted(cols)
            tcols = [[idx[k] for k in cols[xy]] for xy in cxy]
            for k, (how, cs) in sorted(crowns.items(), key=lambda kv: idx[kv[0]]):
                if cs:
                    need = min(k[3], max(len(cols[c]) - 1 for c in cs))
                    tcrowns.append((idx[k], need, [cxy.index(c) for c in cs]))
    # слой M0j5 (collapse_v8): что держит ядро M0j4 на целом блоке и что из частей - дерево (вне слоя)
    import collapse_v8 as E
    if E.BASE is None:
        raise SystemExit("выгрузка: модель M0j5 не установлена (collapse_v8.install)")
    lay = E.layer(blk)
    lost = E.hanging(blk)
    if lost:
        raise SystemExit("выгрузка %s остановлена: висит и по связям %d частей: %s" % (label, len(lost), lost[:6]))
    for e in parts:
        e["held0"] = e["key"] in lay["held0"]
        e["tree"] = e["key"] in lay["tree"]
    return dict(label=label, terrain=blk.terrain, name=NAME_AS.get(label, blk.name), sx=blk.sx, sy=blk.sy, sz=blk.sz,
                box=BOX[label], parts=parts, idx=idx, keep=keep, tcols=tcols, tcrowns=tcrowns)


# ------------------------------------------------------------------ упрощённая копия расчёта

def ref_eval(d, removed):
    """evaluate7c под M0j4 на этих зданиях: ядро evaluate2w (Z, X, F, k с консолью стены, a, b; R U A Q I M без своих частей) и слой v7c.
    removed - множество номеров частей. Возвращает множество номеров держащихся частей."""
    P = d["parts"]
    sx, sy, sz = d["sx"], d["sy"], d["sz"]
    grid = [[{} for _ in range(4)] for _ in range(sz)]    # [z][kind][(x, y)] -> номер
    for i, e in enumerate(P):
        grid[e["z"]][e["kind"]][(e["x"], e["y"])] = i
    C_, L_ = 2, 12
    X = bool(removed)
    sup, carry, fallen_x = set(), set(), set()
    for z in range(sz):
        lv = grid[z]
        live = [{xy: i for xy, i in lv[k].items() if i not in removed} for k in range(4)]
        if z == 0:
            for k in range(4):
                sup.update(live[k].values())
                carry.update(i for i in live[k].values() if P[i]["bearing"])
            continue
        below = grid[z - 1]
        props = set()
        for (x, y), i in below[1].items():
            if i in carry:
                props.update(((x, y), (x - 1, y)))
        for (x, y), i in below[2].items():
            if i in carry:
                props.update(((x, y), (x, y - 1)))
        for (x, y), i in below[3].items():
            if i in carry:
                props.add((x, y))
                for dx, dy in P[i]["edge"]:
                    props.add((x + dx, y + dy))
        floors = set(live[0])
        mass = {xy for xy, i in live[3].items() if P[i]["bearing"]}
        msup = set()
        for xy in mass:
            if below[3].get(xy) in carry or (xy in floors and xy in props):
                msup.add(xy)
        q = deque(msup)
        while q:
            x, y = q.popleft()
            for nb in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if nb in mass and nb not in msup:
                    msup.add(nb)
                    q.append(nb)
        direct = floors & (props | msup)
        direct_b = set(direct)
        direct_b |= {(x, y) for (x, y) in floors - direct_b
                     if ((x + 1, y) in direct_b or (x - 1, y) in direct_b) and
                     ((x, y + 1) in direct_b or (x, y - 1) in direct_b)}
        okf, strong = ref_slab(P, live, floors, direct_b, C_, L_)
        nobase = set()
        if X:
            for k in (1, 2, 3):
                for xy, i in live[k].items():
                    if not P[i]["bearing"]:
                        continue
                    u = below[k].get(xy)
                    if u is not None and P[u]["carry0"] and u not in carry:
                        nobase.add(i)
            x_fall_o = {xy for xy, i in live[3].items() if i in nobase and xy not in msup and xy not in strong}
            tier = {xy for xy in okf - strong if xy in x_fall_o or below[3].get(xy) in fallen_x}
            okf -= tier
        for xy in floors:
            if xy in okf:
                sup.add(live[0][xy])
        lint = ref_lintels(P, live, below, carry, strong)
        cons = ref_consoles(P, live, below, carry, strong, lint)
        lint |= cons
        for k, sides in ((1, lambda x, y: ((x, y), (x - 1, y))), (2, lambda x, y: ((x, y), (x, y - 1)))):
            for (x, y), i in live[k].items():
                u = below[k].get((x, y))
                on_obj = 0
                ob = below[3].get((x, y))
                if ob is not None and ob in carry:
                    on_obj = P[i]["contact"]
                if i in nobase:
                    held = any(s in strong for s in sides(x, y)) or i in lint
                else:
                    held = any(s in okf for s in sides(x, y)) or u in carry or i in lint or on_obj > 0
                cons_only = i in cons and not (any(s in okf for s in sides(x, y)) or u in carry or on_obj > 0)
                if held:
                    sup.add(i)
                    if P[i]["bearing"] and not cons_only:
                        carry.add(i)
                elif i in nobase:
                    fallen_x.add(i)
        furn = {xy for xy, i in live[3].items() if P[i]["furn"]}
        fsup = set()
        for (x, y), i in live[3].items():
            u = below[3].get((x, y))
            walls = [live[1].get((x, y)), live[1].get((x + 1, y)), live[2].get((x, y)), live[2].get((x, y + 1))]
            by_wall = any(w in carry for w in walls if w is not None) and P[i]["attach"]
            if i in nobase:
                held = (x, y) in msup or (x, y) in strong
            else:
                held = (x, y) in okf or (x, y) in msup or u in carry or \
                    (u is not None and u in sup and P[u]["furn"]) or by_wall
            if held:
                sup.add(i)
                if P[i]["bearing"]:
                    carry.add(i)
                if (x, y) in furn:
                    fsup.add((x, y))
            elif i in nobase:
                fallen_x.add(i)
        q = deque(fsup | {xy for xy, i in live[3].items() if i in sup and P[i]["bearing"]})
        while q:
            x, y = q.popleft()
            for nb in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if nb in furn and nb not in fsup:
                    fsup.add(nb)
                    sup.add(live[3][nb])
                    q.append(nb)
    # ветка D (collapse_v4.tree_hold4, tie all): колонна держится цепочкой от основания, кусок кроны - всеми
    # своими колоннами до этажа нужды; часть у несущей стены своей клетки - по ядру
    if d["tcols"]:
        def on_wall(i):
            e = P[i]
            lv = grid[e["z"]]
            ws = (lv[1].get((e["x"], e["y"])), lv[1].get((e["x"] + 1, e["y"])), lv[2].get((e["x"], e["y"])),
                  lv[2].get((e["x"], e["y"] + 1)))
            return any(w is not None and w in carry and w not in removed for w in ws)
        held_to, tree_held, managed = [], set(), set()
        for st in d["tcols"]:
            top = -1
            for z, i in enumerate(st):
                if i in removed:
                    break
                top = z
                tree_held.add(i)
            held_to.append(top)
            managed.update(i for i in st[1:] if not on_wall(i))
        for i, need, cs in d["tcrowns"]:
            if on_wall(i):
                continue
            managed.add(i)
            if i not in removed and all(held_to[c] >= need for c in cs):
                tree_held.add(i)
        sup = (sup - managed) | (tree_held & managed)
    # слой разметки v7c
    held = {i for i in sup if not (P[i]["mark"] and i not in removed)}
    pending = {}
    for i, e in enumerate(P):
        if not e["mark"] or i in removed:
            continue
        if e["mark"] == 2:
            if i in sup:
                held.add(i)
        else:
            pending[i] = [t for t in e["targets"] if t not in removed]
    changed = True
    while changed:
        changed = False
        for i in list(pending):
            if any(t in held for t in pending[i]):
                held.add(i)
                del pending[i]
                changed = True
    # слой M0j5 (collapse_v8): связи по геометрии частей; часть, которую ядро не держит на целом (U0), держится
    # путём от держащейся не длиннее d0 + SU; часть, которую ядро держало на целом, а теперь роняет, - путём не
    # длиннее SC, если уровнем ниже стоит несущая опора не дальше SD клеток; затем разметка по своим целям
    import collapse_v8 as E
    adj, d0, sup = ref_links(d)
    budget = {i: v + E.SU for i, v in d0.items()}
    for i, sp in sup.items():
        if i not in held and any(j not in removed for j in sp):
            budget[i] = E.SC
    if budget:
        got = ref_reach(adj, budget, [i for i in held if not P[i]["tree"]], removed)
        if got:
            held |= set(got)
            changed = True
            while changed:
                changed = False
                for i, e in enumerate(P):
                    if e["mark"] == 1 and not e["tree"] and i not in held and i not in removed and \
                            any(t in held and t not in removed for t in e["targets"]):
                        held.add(i)
                        changed = True
    return held


def ref_walk(xy, d, med, ends, slab, bridge, lim):
    dx, dy = d
    x, y = xy
    dist = 0
    while True:
        x += dx
        y += dy
        dist += 1
        if dist > lim:
            return None
        if (x, y) in ends:
            return dist
        if (x, y) in med:
            continue
        if not bridge:
            return None
        run = [(x, y)]
        cx, cy = x, y
        while True:
            cx += dx
            cy += dy
            if dist + len(run) > lim:
                return None
            if (cx, cy) in med or (cx, cy) in ends:
                break
            run.append((cx, cy))
        cover = [(x - dx, y - dy)] + run + [(cx, cy)]
        px, py = dy, dx
        if not any(all((a + px * s, b + py * s) in slab for a, b in cover) for s in (1, -1)):
            return None
        x, y = cx, cy
        dist += len(run)
        if (x, y) in ends:
            return dist


def ref_beam(xy, med, ends, slab, bridge, lim):
    if xy in ends:
        return 0
    best = None
    for ax in ((1, 0), (0, 1)):
        a = ref_walk(xy, ax, med, ends, slab, bridge, lim)
        if a is None:
            continue
        b = ref_walk(xy, (-ax[0], -ax[1]), med, ends, slab, bridge, lim)
        if b is None:
            continue
        best = a + b if best is None else min(best, a + b)
    return best


def ref_bfs(start, floors):
    dist = {xy: 0 for xy in start}
    q = deque(start)
    while q:
        x, y = q.popleft()
        for nb in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if nb in floors and nb not in dist:
                dist[nb] = dist[(x, y)] + 1
                q.append(nb)
    return dist


def ref_slab(P, live, floors, direct_b, C_, L_):
    fk = live[0]
    med = floors
    slab = {xy for xy in floors if not P[fk[xy]]["light"]}

    def lim_l(xy):
        return P[fk[xy]]["liml"]

    def lim_c(xy):
        e = P[fk[xy]]
        return 0 if e["can"] and not e["posted0"] else C_

    held = set(direct_b)
    for _ in range(2):
        base = set(held)
        for xy in floors:
            nl = ref_beam(xy, med, base, slab, xy in slab, lim_l(xy))
            if nl is not None and nl <= lim_l(xy):
                held.add(xy)
    okf = set(held)
    geo_held = ref_bfs(held & med, floors)
    geo_dir = ref_bfs(direct_b, floors)
    for xy in floors - okf:
        c = lim_c(xy)
        if xy in slab:
            if geo_held.get(xy) is not None and geo_held[xy] <= c:
                okf.add(xy)
                continue
            for dd in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                w = ref_walk(xy, dd, med, held, slab, True, c)
                if w is not None and w <= c:
                    okf.add(xy)
                    break
        elif geo_dir.get(xy) is not None and geo_dir[xy] <= c:
            okf.add(xy)
    return okf, held


def ref_lintels(P, live, below, carry, strong):
    def based(k, xy, i):
        if not P[i]["bearing"]:
            return False
        if below[k].get(xy) in carry:
            return True
        x, y = xy
        sides = ((x, y), (x - 1, y)) if k == 1 else ((x, y), (x, y - 1))
        return any(s in strong for s in sides)

    base = {k: {xy for xy, i in live[k].items() if based(k, xy, i)} for k in (1, 2)}

    def corner(k, px, py):
        if k == 1:
            return (px - 1, py) in base[2] or (px, py) in base[2]
        return (px, py - 1) in base[1] or (px, py) in base[1]

    out = set()
    for k, (dx, dy) in ((1, (0, 1)), (2, (1, 0))):
        lw = live[k]
        for (x, y), i in lw.items():
            if below[k].get((x, y)) in carry or not P[i]["bearing"]:
                continue
            run, ok = 1, True
            for sgn in (1, -1):
                cx, cy = x, y
                while True:
                    px, py = (cx + dx, cy + dy) if sgn > 0 else (cx, cy)
                    if corner(k, px, py):
                        break
                    cx += dx * sgn
                    cy += dy * sgn
                    nk = lw.get((cx, cy))
                    if nk is None or not P[nk]["bearing"]:
                        ok = False
                        break
                    if (cx, cy) in base[k]:
                        break
                    run += 1
                if not ok:
                    break
            if ok and run <= 4:
                out.add(i)
    return out


def ref_consoles(P, live, below, carry, strong, lint, wc=2):
    """collapse_v7d.wall_consoles: ряд несущих стен до wc клеток, упёртый в базу или угол хотя бы с одной стороны."""
    def based(k, xy, i):
        if not P[i]["bearing"]:
            return False
        if below[k].get(xy) in carry:
            return True
        x, y = xy
        sides = ((x, y), (x - 1, y)) if k == 1 else ((x, y), (x, y - 1))
        return any(s in strong for s in sides)

    base = {k: {xy for xy, i in live[k].items() if based(k, xy, i)} for k in (1, 2)}

    def corner(k, px, py):
        if k == 1:
            return (px - 1, py) in base[2] or (px, py) in base[2]
        return (px, py - 1) in base[1] or (px, py) in base[1]

    out = set()
    for k, (dx, dy) in ((1, (0, 1)), (2, (1, 0))):
        lw = live[k]
        for (x, y), i in lw.items():
            if i in lint or below[k].get((x, y)) in carry or not P[i]["bearing"]:
                continue
            run, anchored = 1, 0
            for sgn in (1, -1):
                cx, cy = x, y
                while True:
                    px, py = (cx + dx, cy + dy) if sgn > 0 else (cx, cy)
                    if corner(k, px, py):
                        anchored += 1
                        break
                    cx += dx * sgn
                    cy += dy * sgn
                    nk = lw.get((cx, cy))
                    if nk is None or not P[nk]["bearing"]:
                        break
                    if (cx, cy) in base[k]:
                        anchored += 1
                        break
                    run += 1
            if anchored >= 1 and run <= wc:
                out.add(i)
    return out


# ------------------------------------------------------------------ наборы снятого

def ref_links(d):
    """Слой M0j5 по целому блоку (кэш в d): связи частей вне деревьев, d0 частей U0, опоры (несущие уровнем ниже
    не дальше SD) частей, которые ядро держит на целом."""
    if "_links" not in d:
        import collapse_v8 as E
        P = d["parts"]
        slot = {v: k for k, v in KIND.items()}
        at = {(slot[e["kind"]], e["x"], e["y"], e["z"]): i for i, e in enumerate(P)}
        adj = []
        for i, e in enumerate(P):
            js = [at.get(q) for q in E.carries((slot[e["kind"]], e["x"], e["y"], e["z"]), e["bearing"])] \
                if not e["tree"] else []
            adj.append([j for j in js if j is not None and not P[j]["tree"]])
        u0 = {i: 1 << 30 for i, e in enumerate(P) if e["z"] > 0 and not e["held0"] and not e["tree"]}
        d0 = ref_reach(adj, u0, [i for i, e in enumerate(P) if e["held0"] and not e["tree"]], frozenset())
        bear = {}
        for j, f in enumerate(P):
            if f["bearing"] and f["held0"] and not f["tree"]:
                bear.setdefault(f["z"], []).append(j)
        sup = {}
        for i, e in enumerate(P):
            if e["z"] > 0 and e["held0"] and not e["tree"]:
                ti = E.touch((slot[e["kind"]], e["x"], e["y"], e["z"]))
                sup[i] = [j for j in bear.get(e["z"] - 1, ()) if any(
                    max(abs(a - c), abs(b - g)) <= E.SD for a, b in ti
                    for c, g in E.touch((slot[P[j]["kind"]], P[j]["x"], P[j]["y"], P[j]["z"])))]
        d["_links"] = (adj, d0, sup)
    return d["_links"]


def ref_reach(adj, budget, sources, removed):
    """Расстояния по связям от источников: часть с бюджетом берётся, если путь до неё не длиннее бюджета."""
    dist = {}
    q = deque()
    for a in sources:
        for k in adj[a]:
            if budget.get(k, 0) >= 1 and k not in removed and k not in dist:
                dist[k] = 1
                q.append(k)
    while q:
        k = q.popleft()
        for m in adj[k]:
            if budget.get(m, 0) >= dist[k] + 1 and m not in removed and m not in dist:
                dist[m] = dist[k] + 1
                q.append(m)
    return dist


def removal_sets(d, rows, rng):
    """Сценарии pilot_scen.tsv этого здания и случайные наборы: одиночные, кучки у клетки, полосы, всё
    здание этажа. Возвращает [(метка, frozenset номеров)]."""
    import collapse_pilot_scen as PS
    idx, P = d["idx"], d["parts"]
    out = [("EMPTY", frozenset())]
    for r in rows:
        if r[1] != d["label"]:
            continue
        out.append(("%s/z%s" % (r[2], r[3]), frozenset(idx[PS.kparse(s)] for s in r[5].split())))
    box = [i for i, e in enumerate(P) if e["inbox"]]
    allp = list(range(len(P)))
    for n in range(N_RANDOM):
        kind = n % 5
        if kind == 0:
            s = rng.sample(box, rng.randint(1, 3))
        elif kind == 1:
            s = rng.sample(box, rng.randint(4, 40))
        elif kind == 2:          # кучка: все части в квадрате клеток на 1-2 этажах
            e = P[rng.choice(box)]
            r_ = rng.randint(0, 2)
            zs = {e["z"], e["z"] + rng.choice((-1, 0, 1))}
            s = [i for i in box if abs(P[i]["x"] - e["x"]) <= r_ and abs(P[i]["y"] - e["y"]) <= r_ and P[i]["z"] in zs]
        elif kind == 3:          # несущие этажа: доля стен и колонн
            z = rng.randint(0, d["sz"] - 1)
            cand = [i for i in box if P[i]["z"] == z and P[i]["bearing"]]
            s = rng.sample(cand, rng.randint(1, len(cand))) if cand else []
        else:                    # где угодно в блоке
            s = rng.sample(allp, rng.randint(1, 60))
        out.append(("R%d" % n, frozenset(s)))
    return out


def run_check(C, blds, write=None):
    import collapse_pilot_scen as PS
    rows = []
    for scen in SCENS:
        rows += [ln.split("\t") for ln in open(scen, encoding=PS.ENC).read().splitlines()[1:]]
    rng = random.Random(SEED)
    datas = []
    bad = shown = 0
    for bi, (tn, bn, label, blk) in enumerate(blds):
        d = static(C, blk, label)
        keys = [e["key"] for e in d["parts"]]
        sets = removal_sets(d, rows, rng)
        t0 = time.time()
        vec = []
        tree = [e["key"] for e in d["keep"]]
        tree_fell = 0
        rng_cut = random.Random(SEED + bi)       # свой генератор: наборы прежних зданий не сдвигаются
        tree_base = set(C.evaluate7c(blk, frozenset())[0]) & set(tree)
        if len(tree_base) != len(tree):
            print("   %s: деревья, что не держатся и у целого: %s" % (label, sorted(set(tree) - tree_base)[:6]))
        for n, (lab, rm) in enumerate(sets):
            # деревья вне модели (TREES_OUT): в бою их рубят и жгут как угодно - модель здания обязана не
            # заметить этого (снятые деревья: ни одного, все, случайная часть), а деревья - устоять при любом
            # снятом здания
            cut = frozenset() if not tree or n % 3 == 0 else frozenset(tree) if n % 3 == 1 else \
                frozenset(rng_cut.sample(tree, rng_cut.randint(1, len(tree))))
            exp = C.evaluate7c(blk, frozenset(keys[i] for i in rm) | cut)[0]
            exp_i = frozenset(d["idx"][k] for k in exp if k in d["idx"])
            if not cut:
                fell = [k for k in tree_base if k not in exp]
                if fell:
                    tree_fell += 1
                    if tree_fell <= 3:
                        print("  ДЕРЕВО ПАДАЕТ %s %s: %s" % (label, lab, sorted(fell)[:6]))
            got = ref_eval(d, rm)
            if got != exp_i:
                bad += 1
                shown += 1
                if shown <= 10:
                    print("  РАСХОЖДЕНИЕ %s %s%s: лишние %s, нет %s" % (
                        label, lab, " (снято деревьев %d)" % len(cut) if cut else "",
                        sorted(keys[i] for i in got - exp_i)[:6], sorted(keys[i] for i in exp_i - got)[:6]))
            vec.append((lab, rm, got))
        bad += tree_fell
        if tree:
            print("   деревья вне модели: частей %d, наборов, где дерево падает, %d" % (len(tree), tree_fell))
        nsc = sum(1 for lab, _ in sets if not lab.startswith("R") and lab != "EMPTY")
        print("%s: частей %d (в здании %d), наборов %d (сценариев %d, случайных %d), %.1f с" % (
            label, len(keys), sum(e["inbox"] for e in d["parts"]), len(sets), nsc, N_RANDOM, time.time() - t0))
        falls = [len(keys) - len(rm) - len(h) for _, rm, h in vec]
        print("   наборов с обрушением %d, частей упало всего %d, больше 20 частей - %d наборов" % (
            sum(1 for f in falls if f), sum(falls), sum(1 for f in falls if f > 20)))
        d["vectors"] = vec
        datas.append(d)
    print("расхождений упрощённой копии с evaluate7c: %d" % bad)
    if bad:
        raise SystemExit(1)
    return datas


# ------------------------------------------------------------------ выгрузка

def cpp_header(datas):
    L = ["// Сгенерировано tools/collapse_pilot_export.py - руками не править.",
         "// Пилот обрушения: модель M0j5 (M0j4 = M0j3 плюс консоль стены, и слой связей) с разметкой v2 "
         "(stage0l/stage0m, pilot3), здания пилота.",
         "// Источники модели (sha256):"]
    L += ["//   %s %s" % (p, sha(p)) for p in SOURCES]
    L += ["#pragma once", "#include \"CollapseCore.h\"", "", "namespace OpenXcom", "{", "namespace CollapsePilotData",
          "{", ""]
    for bi, d in enumerate(datas):
        P = d["parts"]
        sets = sorted({e["set"] for e in P} | {e["set"] for e in d["keep"]})
        L.append("// %s: %s / %s, %dx%dx%d, частей %d" % (d["label"], d["terrain"], d["name"], d["sx"], d["sy"],
                                                          d["sz"], len(P)))
        L.append("static const char *const sets%d[] = { %s };" % (bi, ", ".join('"%s"' % s for s in sets)))
        L.append("static const CollapsePart parts%d[] = {" % bi)
        tg = []
        for e in P:
            off = len(tg)
            tg += e["targets"]
            ex, ey = (e["edge"] + [(0, 0), (0, 0)])[0], (e["edge"] + [(0, 0), (0, 0)])[1]
            nedge = len(e["edge"])
            fl = (1 if e["bearing"] else 0) | (2 if e["furn"] else 0) | (4 if e["attach"] else 0) | \
                 (8 if e["carry0"] else 0) | (16 if e["can"] else 0) | (32 if e["posted0"] else 0) | \
                 (64 if e["light"] else 0) | (128 if e["inbox"] else 0) | (256 if e["held0"] else 0) | \
                 (512 if e["tree"] else 0)
            L.append("\t{ %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d },"
                     % (e["kind"], e["x"], e["y"], e["z"], sets.index(e["set"]), e["mcd"], fl, e["contact"],
                        e["liml"], nedge, ex[0], ex[1], ey[0], ey[1], e["mark"], off, len(e["targets"])))
        L.append("};")
        L.append("static const int targets%d[] = { %s };" % (bi, ", ".join(map(str, tg)) or "-1"))
        if d["keep"]:
            L.append("static const CollapsePart keep%d[] = {" % bi)
            for e in d["keep"]:
                L.append("\t{ %d, %d, %d, %d, %d, %d, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0 }," % (
                    e["kind"], e["x"], e["y"], e["z"], sets.index(e["set"]), e["mcd"]))
            L.append("};")
        if d["tcols"]:
            L.append("static const int treeCols%d[] = { %s };" % (
                bi, ", ".join(str(v) for st in d["tcols"] for v in [len(st)] + st)))
            L.append("static const int crowns%d[] = { %s };" % (
                bi, ", ".join(str(v) for i, need, cs in d["tcrowns"] for v in [i, need, len(cs)] + cs) or "-1"))
        L.append("")
    L.append("static const CollapseBlock blocks[] = {")
    for bi, d in enumerate(datas):
        b = d["box"]
        L.append('\t{ "%s", "%s", %d, %d, %d, %d, %d, %d, %d, sets%d, %d, parts%d, %d, targets%d, %d, %s, %d, '
                 '%s, %d, %s, %d },' % (
            LABEL_EN[d["label"]], d["name"], d["sx"], d["sy"], d["sz"], b[0], b[1], b[2], b[3], bi,
            len({e["set"] for e in d["parts"]} | {e["set"] for e in d["keep"]}), bi, len(d["parts"]), bi,
            1 if LABEL_EN[d["label"]] in EXPERIMENTAL else 0, "keep%d" % bi if d["keep"] else "nullptr",
            len(d["keep"]), "treeCols%d" % bi if d["tcols"] else "nullptr", len(d["tcols"]),
            "crowns%d" % bi if d["tcols"] else "nullptr", len(d["tcrowns"])))
    L.append("};")
    L.append("static const int blockCount = %d;" % len(datas))
    L += ["", "}", "}", ""]
    return "\n".join(L)


def write_vectors(datas):
    os.makedirs(OUT, exist_ok=True)
    L = []
    for bi, d in enumerate(datas):
        for lab, rm, exp in d["vectors"]:
            L.append("%d %s R %s H %s" % (bi, lab, " ".join(map(str, sorted(rm))) or "-",
                                          " ".join(map(str, sorted(exp))) or "-"))
    with open(VECTORS, "w", encoding="ascii", newline="\n") as f:
        f.write("\n".join(L) + "\n")
    print("векторов %d -> %s" % (len(L), VECTORS))


def main():
    os.chdir(os.path.dirname(HERE))
    sys.stdout.reconfigure(encoding="utf-8")
    import collapse_pilot_scen as PS
    import collapse_pilot3_scen as P3
    import collapse_v8 as E
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    E.install()                                   # evaluate7c в этом процессе считает M0j5 = M0j4 + связи (PS.load ORIG7 не трогает)
    # порядок в заголовке: сначала здания 0m (их векторы и номера блоков прежние), затем третья партия
    C, CT, blds = PS.load()
    first = PS.PILOT
    PS.PILOT = P3.PILOT
    blds += PS.load()[2]
    PS.PILOT = first
    BOX.update(P3.BOX)
    LABEL_EN.update(P3.LABEL_EN)
    # четвёртая партия - целые блоки карт, своя загрузка (collapse_pilot4_scen.load), номера блоков после третьей
    import collapse_pilot4_scen as P4
    blds += P4.load()[2]
    BOX.update(P4.BOX)
    LABEL_EN.update(P4.LABEL_EN)
    import collapse_pilot5_scen as P5             # пятая партия так же, номера блоков после четвёртой
    blds += P5.load()[2]
    BOX.update(P5.BOX)
    LABEL_EN.update(P5.LABEL_EN)
    import collapse_pilot6_scen as P6             # шестая партия так же, номера блоков после пятой
    blds += P6.load()[2]
    BOX.update(P6.BOX)
    LABEL_EN.update(P6.LABEL_EN)
    import collapse_pilot7_scen as P7             # седьмая партия так же, номера блоков после шестой
    blds += P7.load()[2]
    BOX.update(P7.BOX)
    LABEL_EN.update(P7.LABEL_EN)
    import collapse_pilot8_scen as P8             # восьмая партия так же, деревья вне модели
    blds += P8.load()[2]
    BOX.update(P8.BOX)
    LABEL_EN.update(P8.LABEL_EN)
    TREES_IN.update(P8.TREES_OUT)                 # 20.10: деревья партии 8 - уже в модели (ветка D)
    import collapse_pilot9_scen as P9             # девятая партия - лес и столбы, ветка D в модели
    blds += P9.load()[2]
    BOX.update(P9.BOX)
    LABEL_EN.update(P9.LABEL_EN)
    TREES_IN.update(P9.TREES_IN)
    import collapse_pilot10_scen as P10           # десятая партия - охват после ветки D, свои имена моделей
    blds += P10.load()[2]
    BOX.update(P10.BOX)
    LABEL_EN.update(P10.LABEL_EN)
    TREES_IN.update(P10.TREES_IN)
    NAME_AS.update(P10.NAME_AS)
    import collapse_pilot11_scen as P11           # одиннадцатая - кандидаты десятой с разобранными видами предметов
    blds += P11.load()[2]
    BOX.update(P11.BOX)
    LABEL_EN.update(P11.LABEL_EN)
    TREES_IN.update(P11.TREES_IN)
    NAME_AS.update(P11.NAME_AS)
    import collapse_pilot12_scen as P12           # двенадцатая - второй лист разобранных видов
    blds += P12.load()[2]
    BOX.update(P12.BOX)
    LABEL_EN.update(P12.LABEL_EN)
    TREES_IN.update(P12.TREES_IN)
    NAME_AS.update(P12.NAME_AS)
    import collapse_pilot13_scen as P13           # тринадцатая - третий лист разобранных видов
    blds += P13.load()[2]
    BOX.update(P13.BOX)
    LABEL_EN.update(P13.LABEL_EN)
    TREES_IN.update(P13.TREES_IN)
    NAME_AS.update(P13.NAME_AS)
    if len({b[2] for b in blds}) != len(blds) or len(set(LABEL_EN.values())) != len(LABEL_EN):
        raise SystemExit("метки зданий пилота не уникальны")
    # после загрузки сейва движок ищет модель по имени (последняя с этим именем) - одноимённые блоки другой модели
    # обязаны получить своё имя в NAME_AS
    names = Counter(NAME_AS.get(b[2], b[3].name).upper() for b in blds)
    if any(n > 1 for n in names.values()):
        raise SystemExit("имена моделей в заголовке не уникальны: %s" % sorted(k for k, n in names.items() if n > 1))
    if EXPERIMENTAL - set(LABEL_EN.values()):
        raise SystemExit("в EXPERIMENTAL метки не из пилота: %s" % sorted(EXPERIMENTAL - set(LABEL_EN.values())))
    only = os.environ.get("COLLAPSE_EXPORT_ONLY")      # проверка части зданий по меткам игры - без выгрузки
    if only:
        if cmd == "export":
            raise SystemExit("COLLAPSE_EXPORT_ONLY - только для check")
        blds = [b for b in blds if LABEL_EN[b[2]] in only.split(",")]
    datas = run_check(C, blds)
    if cmd == "export":
        # третий аргумент - другой путь заголовка (проверка переноса в блокноте, без очереди правок)
        header = sys.argv[2] if len(sys.argv) > 2 else HEADER
        # ASCII-only заголовок не обязателен: исходники проекта - UTF-8 без спецификации (R-001, исключение .cpp/.h)
        with open(header, "w", encoding="utf-8", newline="\n") as f:
            f.write(cpp_header(datas))
        print("заголовок ->", header)
        write_vectors(datas)


if __name__ == "__main__":
    main()
