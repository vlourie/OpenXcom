"""Этап 0d: какие консоли и пролёты нужны полам ЦЕЛЫХ блоков, по типу конструкции.

Для каждого пола выше земли на целом блоке (вариант R+A модели v2, C=2, L=12, и отдельно с большим L, чтобы
увидеть пролёт, который полу на самом деле нужен) - тип клетки:
  над улицей  - клетка этажом ниже снаружи здания (достижима от края блока, не пересекая стен, окон и
                дверей); навес, балкон, карниз, крыльцо;
  над помещ.  - клетка этажом ниже внутри;
и нагрузка:
  кровля      - на клетке и над ней ничего нет (кроме самого пола);
  нагружен    - на клетке стоит стена или предмет, или выше есть хоть что-то.
Плюс группа террейна (наземные / суда / подземные) по census/collapse/ships/terrain_groups.tsv, если файл есть.

Выход: census/collapse/stage0d/spans_by_type.tsv (по клетке) и сводка в stdout.
py -3.13 tools/collapse_spans.py [--limit N]
"""
import argparse
import os
import sys
from collections import Counter, defaultdict, deque

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collapse_census as cc                      # noqa: E402
import collapse_v2 as V                           # noqa: E402

ENC = "utf-8-sig"
OUT = os.path.join("census", "collapse", "stage0d")
LS = (12, 16, 20, 24, 99)
CLOSED = {"wall", "window", "hard", "door", "block", "edgewall"}


def exterior(blk, z):
    """Клетки уровня z, достижимые от края блока без пересечения стен, окон, дверей и сплошных предметов."""
    lv = blk.lv[z]
    w = {xy for xy, key in lv["w"].items() if blk.parts[key]["cls"] in CLOSED}
    n = {xy for xy, key in lv["n"].items() if blk.parts[key]["cls"] in CLOSED}
    solid = {xy for xy, key in lv["o"].items() if blk.parts[key]["cls"] in CLOSED}
    seen = set()
    q = deque()
    # вход снаружи блока: через западный край клетки x=0 и северный y=0 - если там нет стены; восточный и
    # южный края блока стен не несут (стена принадлежит клетке за краем), туда вход открыт
    for x in range(blk.sx):
        if (x, 0) not in n:
            q.append((x, 0))
        q.append((x, blk.sy - 1))
    for y in range(blk.sy):
        if (0, y) not in w:
            q.append((0, y))
        q.append((blk.sx - 1, y))
    while q:
        xy = q.popleft()
        if xy in seen or xy in solid:
            continue
        seen.add(xy)
        x, y = xy
        if x + 1 < blk.sx and (x + 1, y) not in w:
            q.append((x + 1, y))
        if x > 0 and (x, y) not in w:
            q.append((x - 1, y))
        if y + 1 < blk.sy and (x, y + 1) not in n:
            q.append((x, y + 1))
        if y > 0 and (x, y) not in n:
            q.append((x, y - 1))
    return seen


def groups():
    p = os.path.join("census", "collapse", "ships", "terrain_groups.tsv")
    out = {}
    if os.path.exists(p):
        with open(p, encoding=ENC) as f:
            lines = f.read().splitlines()
        head = lines[0].split("\t")
        for ln in lines[1:]:
            r = dict(zip(head, ln.split("\t")))
            out[r.get("terrain", "").upper()] = r.get("group", "")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    roles = V.load_roles()
    grp = groups()
    rows = []
    nb = 0
    for tname, kind, t, bname, blk, err, cache in cc.all_blocks(V.game_args()):
        if blk is None or blk.sz < 2:
            continue
        nb += 1
        if a.limit and nb > a.limit:
            break
        V.apply_roles(blk, roles)
        runs = {L: V.evaluate2(blk, frozenset(), V.VARIANTS["R+A"], L=L) for L in LS}
        s12, i12 = runs[12]
        ext = {z: exterior(blk, z) for z in range(blk.sz)}
        g = grp.get(tname.upper(), "?")
        for z in range(1, blk.sz):
            for xy, key in blk.lv[z]["f"].items():
                x, y = xy
                over = "улица" if xy in ext[z - 1] else "помещ"
                on = [blk.lv[z]["w"].get(xy), blk.lv[z]["w"].get((x + 1, y)), blk.lv[z]["n"].get(xy),
                      blk.lv[z]["n"].get((x, y + 1)), blk.lv[z]["o"].get(xy)]
                above = any(xy in blk.lv[zz][k] for zz in range(z + 1, blk.sz) for k in cc.KINDS)
                load = "нагружен" if any(on) or above else "кровля"
                d12, c12, l12 = i12.get(key, (None, None, None))
                need = next((L for L in LS if key in runs[L][0]), "")
                if d12:
                    how = "прямо"
                elif key in s12 and c12 is not None and c12 <= 2:
                    how = "конс%d" % c12
                elif key in s12:
                    how = "пр<=12"
                elif need:
                    how = "пр<=%d" % need if need < 99 else "пр>24"
                else:
                    how = "висит"
                rows.append((g, kind, tname, bname, x, y, z, blk.parts[key]["set"], blk.parts[key]["idx"], over,
                             load, how, "" if c12 is None else c12, need))
    cc.write_tsv(OUT + "/spans_by_type.tsv",
                 ["group", "kind", "terrain", "block", "x", "y", "z", "set", "idx", "over", "load", "how",
                  "console_L12", "held_from_L"], rows)
    print("блоков", nb, "полов выше земли", len(rows))
    # сводка: по группе и типу - чем держится пол целого блока
    tab = defaultdict(Counter)
    for r in rows:
        k = (r[0], r[9], r[10])
        tab[k]["всего"] += 1
        tab[k][r[11]] += 1
    cols = ["всего", "прямо", "конс1", "конс2", "пр<=12", "пр<=16", "пр<=20", "пр<=24", "пр>24", "висит"]
    print("%-12s %-6s %-9s " % ("группа", "под", "нагрузка") + " ".join("%8s" % c for c in cols))
    for k in sorted(tab, key=lambda k: (k[0], k[1], k[2])):
        print("%-12s %-6s %-9s " % k + " ".join("%8d" % tab[k][c] for c in cols))


if __name__ == "__main__":
    main()
