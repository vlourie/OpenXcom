#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""MCD_STATE_RELATIONS - связи состояний кадров по данным игры (специалист 01.10, ROUTING_RULES_V5_PREP №1). CPU.

Holdout V4_R1 отправил NUKE2:2 одиночным заказом, а это разрушенный вид NUKE2:3: запись 3 набора NUKE2 ссылается
на запись с кадром 2 полем Die_MCD. Такая связь не догадка по пикселям, а данные игры - и до неё правила не
доходили. Здесь она собирается для всех наборов очереди предметов:

    die   запись X -> Die_MCD -> запись с кадром S        S - разрушенный вид кадра X  (STATE_VARIANT_OF)
    alt   запись X -> Alt_MCD -> запись с кадром S        S - второе состояние X (дверь открыта)
    anim  кадр S стоит в Frame[1..7] записи с Frame[0] X  S - кадр анимации X        (ANIMATION_FRAME_OF)

Маршрут: каноническая основа рисуется, состояние выводится из неё (STATE_VARIANT), одиночным заказом не идёт.

Уровень:
    STRONG     die/alt одной-двух разных основ; alt в одну сторону; кадр анимации
    CANDIDATE  общий обломок: один кадр - die трёх и более разных основ (это груда мусора набора, а не
               состояние одной вещи); alt взаимный при равном числе клеток на картах (что основа - не видно);
               die-цель стоит на картах в 20+ клетках и втрое чаще основы цепочки - это обычный кадр набора
               (FORESTRED:4: пол в 1188 клетках, die записей 1 и 3; правило найдено на holdout V4_R1)
Основа цепочки (X die -> Y die -> Z) - корень: Z выводится из X. Направление у STRONG известно всегда.

Связь - улика маршрута, не родство, подтверждённое человеком; кадр, на который ссылаются записи, на карте может
стоять и сам (NUKE2:2 стоит в 8 клетках) - выводится всё равно.

    py -3.13 tools/hdart/mcd_state.py build     связи по наборам очереди -> mcd_state_relations.json / .md
    py -3.13 tools/hdart/mcd_state.py show NUKE2:2 MUJUNGLE_2:37
"""
import argparse
import csv
import os
import sys
import time
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import identity_routing as ir          # noqa: E402

ROOT = ir.ROOT
OUT = os.path.join(ir.PROBES, "routing-rules-v5-prep")
GENERATION = os.path.join("art", "objects", "generation", "generation.tsv")
CENSUS = os.path.join("census", "frames.tsv")
SHARED_DEBRIS_MIN = 3          # кадр - die стольких разных основ и больше: общий обломок набора
DOMINANT_MIN, DOMINANT_RATIO = 20, 3     # состояние в DOMINANT_MIN+ клетках и в RATIO раз чаще основы - не состояние
# правило частоты найдено на тех же 40, что проверяли (специалист 01.10): не менять, проверить слепо;
# связь, понижённая им, несёт dominance = True - holdout считает срабатывания, помог / навредил
MCD_DOMINANCE_RULE = {"status": "PROVISIONAL", "origin": "FORESTRED:4 diagnostic", "requires_blind_validation": True}
KIND = {"die": "STATE_VARIANT_OF", "alt": "STATE_VARIANT_OF", "anim": "ANIMATION_FRAME_OF"}


def placements(path=CENSUS):
    """(НАБОР, кадр) -> клеток на картах по переписи; нет переписи - пусто (взаимный alt тогда CANDIDATE)."""
    res = {}
    if not os.path.exists(path):
        return res
    with open(path, encoding=ir.ENC, newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            if r.get("раздел") == "TERRAIN":
                res[(r["набор"].upper(), int(r["кадр"]))] = int(r.get("клеток") or 0)
    return res


def set_links(s, recs, cells=None, dominant=True):
    """Связи одного набора по записям MCD: [{state, base, via, records, bases, level, why}].

    recs - записи map_mockup.World.records: frame, frames (Frame[0..7]), die, alt (индексы записей, 0 - нет)."""
    cells = cells or {}
    edges = defaultdict(set)                 # (кадр состояния, via) -> {кадр основы}
    recn = defaultdict(list)
    for n, r in enumerate(recs):
        for via in ("die", "alt"):
            i = r.get(via) or 0
            if 0 < i < len(recs) and recs[i]["frame"] != r["frame"]:
                edges[(recs[i]["frame"], via)].add(r["frame"])
                recn[(recs[i]["frame"], via)].append(n)
    # петля анимации - группа кадров (записи со сдвигом фазы 20-21-22 / 21-22-20 - одна петля); основа - кадр
    # Frame[0] записи группы, что чаще стоит на картах (при равенстве младший), остальные кадры - из неё (R-071)
    parent = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    loops = [(n, r) for n, r in enumerate(recs) if len(set(r.get("frames") or [r["frame"]])) > 1]
    for _n, r in loops:
        for fr in r["frames"]:
            parent[find(fr)] = find(r["frame"])
    groups = defaultdict(set)
    heads = defaultdict(set)
    for n, r in loops:
        g = find(r["frame"])
        groups[g].update(r["frames"])
        heads[g].add(r["frame"])
    for g, frs in groups.items():
        base = min(heads[g], key=lambda f: (-cells.get((s, f), 0), f))
        for fr in frs - {base}:
            edges[(fr, "anim")].add(base)
            recn[(fr, "anim")] += [n for n, r in loops if fr in r["frames"]]
    alt = {(st, b) for (st, via), bs in edges.items() if via == "alt" for b in bs}
    out = []
    for (st, via), bs in sorted(edges.items()):
        for b in sorted(bs):
            level, why = "STRONG", ""
            if via == "die" and len(bs) >= SHARED_DEBRIS_MIN:
                level, why = "CANDIDATE", "общий обломок: die %d разных основ" % len(bs)
            elif via == "alt" and (b, st) in alt:
                cs, cb = cells.get((s, st), 0), cells.get((s, b), 0)
                if cs == cb:
                    level, why = "CANDIDATE", "alt взаимный, клеток поровну (%d) - что основа, не видно" % cs
                elif cs > cb:
                    continue                    # основа - этот кадр: связь пишется в обратную сторону
                else:
                    why = "alt взаимный, основа стоит на картах чаще (%d против %d)" % (cb, cs)
            out.append({"state": "%s:%d" % (s, st), "base": "%s:%d" % (s, b), "via": via, "kind": KIND[via],
                        "records": sorted(set(recn[(st, via)])), "bases": len(bs), "level": level, "why": why})
    strong = defaultdict(set)
    for x in out:
        if x["level"] == "STRONG":
            strong[x["state"]].add(x["base"])

    def root(k, seen=()):
        bs = strong.get(k)
        if not bs or k in seen or len(bs) != 1:
            return k
        return root(next(iter(bs)), seen + (k,))

    for x in out:
        x["root"] = root(x["base"], (x["state"],))
    # «состояние» на картах стоит в разы чаще основы цепочки - это обычный кадр набора (земля, стоящий обломок),
    # а не разрушенный вид вещи: FORESTRED:4 - die 1 и 3, но сам пол в 1188 клетках (найдено на holdout 40)
    for x in out:
        if not dominant or x["level"] != "STRONG" or x["via"] != "die":
            continue
        frame = lambda k: (s, int(k.split(":")[1]))        # noqa: E731
        cs = cells.get(frame(x["state"]), 0)
        cb = max(cells.get(frame(x["base"]), 0), cells.get(frame(x["root"]), 0))
        if cs >= DOMINANT_MIN and cs > DOMINANT_RATIO * max(cb, 1):
            x["level"], x["why"] = "CANDIDATE", "кадр на картах чаще основы (%d клеток против %d)" % (cs, cb)
            x["dominance"] = True
    return out


def build(sets, world=None, cells=None, dominant=True):
    """{набор: [связи]} по списку наборов; набор без MCD - пустой список."""
    if world is None:
        import map_mockup as mm
        world = mm.World()
    cells = placements() if cells is None else cells
    res = {}
    for s in sorted({x.upper() for x in sets}):
        try:
            recs = world.records(s) or []
        except (Exception, SystemExit):         # noqa: BLE001 - набор не читается: связей нет
            recs = []
        res[s] = set_links(s, recs, cells, dominant)
    return res


def index(by_set):
    """Ключ кадра -> связи, где он состояние (side derived) или основа (side base)."""
    idx = defaultdict(list)
    for links in by_set.values():
        for x in links:
            idx[x["state"]].append(dict(x, side="derived", relative=x["base"]))
            idx[x["base"]].append(dict(x, side="base", relative=x["state"]))
    return dict(idx)


def queue_sets(path=GENERATION):
    return sorted({r["key"].split(":")[0].upper() for r in ir.read_tsv(path)})


def do_build(out=OUT):
    os.makedirs(out, exist_ok=True)
    sets = queue_sets()
    by_set = build(sets)
    queue = {r["key"].upper() for r in ir.read_tsv(GENERATION)}
    links = [x for v in by_set.values() for x in v]
    in_q = [x for x in links if x["state"] in queue]
    st = Counter((x["via"], x["level"]) for x in links)
    stq = Counter((x["via"], x["level"]) for x in in_q)
    states_q = sorted({x["state"] for x in in_q if x["level"] == "STRONG"})
    data = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "source": "MCD установки (map_mockup.World), перепись "
            "census/frames.tsv для взаимного alt", "sets": len(sets), "links": len(links),
            "by_via_level": {"%s %s" % k: v for k, v in sorted(st.items())},
            "queue_states_strong": len(states_q), "dominance_rule": MCD_DOMINANCE_RULE,
            "dominance_downgraded": sum(1 for x in links if x.get("dominance")), "relations": by_set}
    ir.dump_json(os.path.join(out, "mcd_state_relations.json"), data)
    L = ["# MCD_STATE_RELATIONS - связи состояний по данным игры", "",
         "Наборов очереди: %d, связей: %d. Кадров очереди, которые по MCD - состояние другой записи (STRONG): %d." % (
             len(sets), len(links), len(states_q)), "",
         "| via | уровень | связей всего | состояние - кадр очереди |", "|---|---|---|---|"]
    for k in sorted(st):
        L.append("| %s | %s | %d | %d |" % (k[0], k[1], st[k], stq.get(k, 0)))
    L += ["", "STRONG - die/alt одной-двух основ, alt в одну сторону, кадр анимации. CANDIDATE - общий обломок "
          "(die %d+ основ) или взаимный alt без перевеса по клеткам." % SHARED_DEBRIS_MIN, "",
          "MCD_DOMINANCE_RULE: status = PROVISIONAL, origin = FORESTRED:4 diagnostic, requires_blind_validation = "
          "yes. Понижено им до CANDIDATE: %d связей." % data["dominance_downgraded"], ""]
    with open(os.path.join(out, "mcd_state_relations.md"), "w", encoding=ir.ENC) as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L))
    return data


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["build", "show"])
    ap.add_argument("keys", nargs="*")
    a = ap.parse_args()
    os.chdir(ROOT)
    if a.cmd == "build":
        do_build()
        return
    idx = index(build({k.split(":")[0] for k in a.keys}))
    for k in a.keys:
        for x in idx.get(k.upper(), []):
            print("%-22s %-7s %-4s %-9s %-22s root %-22s %s" % (k, x["side"], x["via"], x["level"], x["relative"],
                                                                x["root"], x["why"]))


if __name__ == "__main__":
    main()
