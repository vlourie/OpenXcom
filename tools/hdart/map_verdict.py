"""Конфликты повторного использования кадров и вывод по семействам - по каталогу census/maps.

Читает то, что собрал map_catalog.py (frame_usage, record_usage, adjacency, seams, state_graph),
и пишет рядом:
  conflicts.tsv  - кадр, вид конфликта, мера, пример карт;
  families.tsv   - семейство (набор + основной слот) и вывод: READY / VARIANTS / ADDRESSING;
  verdict.json   - пороги, счётчики, контроль меры стыка.

Исходное ограничение HD-слоя (DECISIONS 05.10): ключ HD - кадр SET:frame, одна картинка на кадр
во всех местах; силуэт = силуэт классики x k; склейки в движке нет. Поэтому вопрос к каждому кадру:
выглядит ли ОДНА картинка верно во всех местах, где кадр стоит.

Виды конфликтов (каждый - мерой по каталогу, ничего не угадывается по картинке):
  CARPET        пол стоит рядом с собой в большинстве стыков - одна картинка даёт решётку (R-039)
  EDGE_LINE     на краю ковра в классике нарисована линия (шов плитки, стык досок) - HD обязан её сохранить,
                и в вариантах тоже; мера калибрована листом: отношение >= 4 - линия, < 2 - гладко, между - не решено
  MULTI_SLOT    кадр стоит в разных слотах (пол и предмет, стена и предмет)
  ANIM_SHARED   кадр - фаза анимации одной записи и неподвижный кадр другой (или фаза разных петель)
  WALL_ROLES    кадр стены стоит и серединой ряда, и концом/одиночкой
  STATE_SLOT    переход двери/разрушения ставит запись в другой слот
  MODULAR       предмет стыкуется по одной оси с разными соседями-предметами (живая изгородь, прилавок,
                стол со стульями): одной картинки хватает, если концы взаимозаменяемых секций нарисованы
                одинаково; лист scratchpad piece_view показал, что это ряды секций и соседство, а не куски
  REPEAT        стена или предмет стоит рядом с СОБОЙ вдоль ряда в большинстве своих клеток - ковёр без
                вариантов: варианты движок выбирает только для пола (Map.cpp, setGroundCell у O_FLOOR)
  HASH_ROLES    одна и та же картинка (хэш) у кадров с разными слотами
Вывод по семейству:
  ADDRESSING    есть REPEAT с заметной долей клеток - нужна новая адресация HD (варианты не только пола)
  VARIANTS      есть CARPET - хватит вариантов пола (.vN, Canvas32::groundFrameFor)
  READY         готовых кадров хватает (HD держит силуэт и края классики; ограничения - в conflicts.tsv)
"""
import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENC_W = "utf-8-sig"
ENC_R = "utf-8-sig"


def read_tsv(p):
    with open(p, encoding=ENC_R, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def write_tsv(p, head, rows):
    with open(p, "w", encoding=ENC_W, newline="") as f:
        w = csv.writer(f, delimiter="\t", quoting=csv.QUOTE_NONE, escapechar="\\", lineterminator="\n")
        w.writerow(head)
        w.writerows(rows)


def pairs(s):
    """'floor 12 north 3' -> Counter."""
    t = s.split()
    return Counter({t[i]: int(t[i + 1]) for i in range(0, len(t) - 1, 2)})


def named(s):
    """'A:1 12, B:2 3' -> Counter."""
    out = Counter()
    for part in s.split(", "):
        k, _, v = part.rpartition(" ")
        if k and v.isdigit():
            out[k] = int(v)
    return out


def seam_class(cross, tex, a):
    """line - перепад через край в разы больше перепада внутри кадра; smooth - сравним; ? - не решено."""
    r = cross / max(tex, 4.0)
    if cross >= a.seam_abs and r >= a.seam_ratio:
        return "line"
    if r < a.seam_smooth:
        return "smooth"
    return "?"


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cat", default=str(ROOT / "census" / "maps"))
    ap.add_argument("--carpet-share", type=float, default=0.5, help="доля стыков пола с самим собой")
    ap.add_argument("--carpet-edges", type=int, default=400, help="стыков пола не меньше")
    ap.add_argument("--seam-abs", type=float, default=20.0)
    ap.add_argument("--seam-ratio", type=float, default=4.0, help="отношение перепада через край к перепаду внутри")
    ap.add_argument("--seam-smooth", type=float, default=2.0)
    ap.add_argument("--minor", type=float, default=0.05, help="доля меньшинства, ниже - не конфликт")
    ap.add_argument("--piece-min", type=int, default=20, help="стыков предмет-предмет у второго соседа не меньше")
    a = ap.parse_args(argv)
    cat = Path(a.cat)

    fu = read_tsv(cat / "frame_usage.tsv")
    ru = {r["record_id"]: r for r in read_tsv(cat / "record_usage.tsv")}
    adj = read_tsv(cat / "adjacency.tsv")
    seams = read_tsv(cat / "seams.tsv") if (cat / "seams.tsv").exists() else []
    states = read_tsv(cat / "state_graph.tsv")

    F = {r["frame_id"]: r for r in fu}
    main_slot = {}
    for r in fu:
        sl = pairs(r["slots"])
        main_slot[r["frame_id"]] = sl.most_common(1)[0][0] if sl else "anim"
    conf = []           # kind, frame, set, slot, cells, value, detail, maps
    by_frame = defaultdict(set)

    def add(kind, fid, value, detail):
        r = F.get(fid, {})
        conf.append([kind, fid, fid.split(":")[0], main_slot.get(fid, ""), r.get("cells", ""), value, detail,
                     r.get("maps", "")])
        by_frame[fid].add(kind)

    # стыки классики: по кадру с самим собой
    self_seam = {}
    seam_rows = defaultdict(list)
    for s in seams:
        if not s["cross_diff"]:
            continue
        cross, tex = float(s["cross_diff"]), float(s["texture"])
        vis = seam_class(cross, tex, a)
        seam_rows[s["frame_a"]].append((s, vis))
        if s["frame_a"] == s["frame_b"]:
            self_seam.setdefault(s["frame_a"], []).append((s["rel"], int(s["count"]), cross, tex, vis))

    for r in fu:
        fid = r["frame_id"]
        sl = pairs(r["slots"])
        tot = sum(sl.values())
        # CARPET и SEAM_SELF
        if r["floor_edges"] and int(r["floor_edges"]) >= a.carpet_edges and r["floor_self_share"] \
                and float(r["floor_self_share"]) >= a.carpet_share:
            vis = [x for x in self_seam.get(fid, []) if x[4] == "line"]
            add("CARPET", fid, r["floor_self_share"], "стыков %s, с собой %s; стык с собой в классике: %s"
                % (r["floor_edges"], r["floor_self_share"],
                   ", ".join("%s cross %.0f tex %.0f %s" % (x[0], x[2], x[3], x[4])
                             for x in self_seam.get(fid, [])) or "не мерился"))
            if vis:
                add("EDGE_LINE", fid, "%.0f" % max(x[2] for x in vis),
                    "линия на краю в классике: " + ", ".join("%s %d" % (x[0], x[1]) for x in vis))
        # MULTI_SLOT
        if len(sl) > 1:
            minor = tot - sl.most_common(1)[0][1]
            if minor / tot >= a.minor:
                add("MULTI_SLOT", fid, "%.2f" % (minor / tot), r["slots"])
        # ANIM_SHARED
        phase_of = r["anim_phase_of"].split()
        if phase_of:
            static = [x for x in r["records"].split() if x in ru and ru[x]["animated"] == "0"]
            loops = {ru[x]["frames"] for x in phase_of if x in ru}
            if static or len(loops) > 1:
                add("ANIM_SHARED", fid, len(phase_of) + len(static),
                    "фаза: %s; неподвижный: %s" % (" ".join(phase_of), " ".join(static) or "-"))
        # WALL_ROLES
        if r["wall_roles"]:
            roles = pairs(r["wall_roles"])
            n = sum(roles.values())
            mid = roles.get("mid", 0)
            edge = roles.get("end", 0) + roles.get("solo", 0)
            if mid and edge and min(mid, edge) / n >= a.minor:
                add("WALL_ROLES", fid, "%.2f" % (edge / n), r["wall_roles"])

    # STATE_SLOT
    for s in states:
        if s["slot_changes"] == "1" and s["slot_to"] not in ("?", ""):
            rec = ru.get(s["record_from"])
            if rec:
                fid = "%s:%s" % (rec["set"], rec["frames"].split()[0])
                add("STATE_SLOT", fid, s["observed_cells"], "%s %s %s -> %s %s"
                    % (s["record_from"], s["slot_from"], s["transition"], s["record_to"], s["slot_to"]))

    # MODULAR: предмет-предмет по одной оси, разные соседи
    nb = defaultdict(Counter)            # (кадр, ось) -> сосед -> стыков
    for r in adj:
        if r["slot_a"] == "object" and r["slot_b"] == "object" and r["rel"] in ("E", "S") \
                and r["frame_a"] != r["frame_b"]:
            n = int(r["count"])
            nb[(r["frame_a"], r["rel"] + "+")][r["frame_b"]] += n
            nb[(r["frame_b"], r["rel"] + "-")][r["frame_a"]] += n
    for (fid, ax), c in nb.items():
        top = c.most_common()
        if len(top) < 2 or top[1][1] < a.piece_min:
            continue
        tot = sum(c.values())
        cells = int(F[fid]["cells"]) if fid in F and F[fid]["cells"] else 0
        if cells and top[0][1] / cells < 0.3:
            continue
        add("MODULAR", fid, "%.2f" % (1 - top[0][1] / tot),
            "ось %s: %s" % (ax, ", ".join("%s %d" % kv for kv in top[:4])))

    # REPEAT: стена/предмет рядом с собой вдоль своего ряда (запад - по S, север - по E, предмет - любая ось)
    axis = {"west": ("S",), "north": ("E",), "object": ("E", "S")}
    selfrun = Counter()
    for r in adj:
        if r["frame_a"] == r["frame_b"] and r["slot_a"] == r["slot_b"] and r["rel"] in axis.get(r["slot_a"], ()):
            selfrun[(r["frame_a"], r["slot_a"])] += int(r["count"])
    for (fid, slot), n in selfrun.items():
        sl = pairs(F[fid]["slots"]) if fid in F else Counter()
        cells = sl.get(slot, 0)
        if cells and n >= a.carpet_edges and n / cells >= a.carpet_share:
            add("REPEAT", fid, "%.2f" % (n / cells), "%s: рядом с собой %d раз на %d клеток" % (slot, n, cells))

    # HASH_ROLES
    by_hash = defaultdict(list)
    for r in fu:
        if r["image_hash"]:
            by_hash[r["image_hash"]].append(r["frame_id"])
    for h, fids in by_hash.items():
        roles = {main_slot[f] for f in fids}
        if len(fids) > 1 and len(roles) > 1:
            for f in fids:
                add("HASH_ROLES", f, len(fids), "та же картинка: " + " ".join(
                    "%s(%s)" % (g, main_slot[g]) for g in fids if g != f))

    conf.sort(key=lambda r: (r[0], -int(r[4] or 0)))
    write_tsv(cat / "conflicts.tsv", ["kind", "frame_id", "set", "slot", "cells", "value", "detail", "maps"], conf)

    # семейства: набор + основной слот
    fam = defaultdict(list)
    for r in fu:
        fam[(r["set"], main_slot[r["frame_id"]])].append(r)
    rows = []
    for (s, slot), frames in fam.items():
        cells = sum(int(r["cells"] or 0) for r in frames)
        kinds = Counter()
        ex = defaultdict(list)
        for r in frames:
            for k in by_frame.get(r["frame_id"], ()):
                kinds[k] += 1
                ex[k].append((int(r["cells"] or 0), r["frame_id"]))
        rep_cells = sum(c for c, _ in ex.get("REPEAT", []))
        if kinds.get("REPEAT") and rep_cells >= 0.05 * cells:
            verdict = "ADDRESSING"
        elif kinds.get("CARPET"):
            verdict = "VARIANTS"
        else:
            verdict = "READY"
        exs = "; ".join("%s: %s" % (k, " ".join(f for _, f in sorted(v, reverse=True)[:3]))
                        for k, v in sorted(ex.items()))
        rows.append([s, slot, len(frames), cells, verdict, " ".join("%s %d" % kv for kv in kinds.most_common()),
                     exs, top_terr(frames)])
    rows.sort(key=lambda r: -r[3])
    write_tsv(cat / "families.tsv", ["set", "slot", "frames", "cells", "verdict", "conflicts", "examples",
                                     "terrains"], rows)
    stat = Counter(r[4] for r in rows)
    stat_cells = Counter()
    for r in rows:
        stat_cells[r[4]] += r[3]
    out = {"thresholds": {k: getattr(a, k) for k in ("carpet_share", "carpet_edges", "seam_abs", "seam_ratio",
                                                     "seam_smooth", "minor", "piece_min")},
           "conflicts": dict(Counter(r[0] for r in conf)),
           "families": dict(stat), "family_cells": dict(stat_cells)}
    (cat / "verdict.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding=ENC_W)
    print(json.dumps(out, ensure_ascii=False, indent=1))


def top_terr(frames):
    c = Counter()
    for r in frames:
        c.update(named(r["terrains"]))
    return ", ".join("%s %d" % kv for kv in c.most_common(4))


if __name__ == "__main__":
    sys.exit(main())
