#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Перепись всех PCK игры: где кадры повторяются и что чаще всего видно на картах.

Зачем. Перерисовывать 33 тысячи кадров подряд бессмысленно: часть из них побайтовые копии
друг друга, часть - тот же рисунок в другой раскраске или зеркально, часть - фазы одной
анимации, которые обязаны остаться похожими. И видно их игроку очень по-разному: один пол
лежит на тысячах клеток всех карт, другой - на двенадцати клетках одной-единственной.

Инструмент отвечает на три вопроса числами:
  1. СКОЛЬКО РАЗНОГО. Кадры сводятся в группы: точная копия, тот же силуэт в другом цвете,
     зеркало, фаза анимации. Рисовать надо по одному представителю группы.
  2. ЧТО ЧАЩЕ ВИДНО. Каждая клетка каждого блока карты разбирается по MCD до номера кадра
     в PCK, и кадр получает число клеток, блоков и террейнов, где он встречается.
  3. ЧТО РИСОВАТЬ ПЕРВЫМ. Наборы сортируются по охвату, а не по числу кадров.

    py -3 tools\pck_census.py --install "Пиратки\Dioxine_XPiratez" --out census

Порядок поиска файлов такой же, как у движка: сначала мод, потом мастер-мод, потом
оригинальные данные. Кто не нашёлся - попадает в census\missing.tsv, а не молча теряется.
"""
import argparse
import hashlib
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.join(HERE, "hdart")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import yaml                                     # noqa: E402
from yaml.events import AliasEvent              # noqa: E402

import xcom_sprites as xs                       # noqa: E402

ENC = "utf-8-sig"
MCD_RECORD = 62


class Tolerant(yaml.SafeLoader):
    """yaml-cpp разрешает переопределить якорь, PyYAML - нет, и падает на рулсетах Пираток.

    Псевдоним не трогаем: у события AliasEvent в поле anchor лежит имя ССЫЛКИ, и удаление
    записи сломало бы её разрешение (проверено: "found undefined alias").
    """

    def compose_node(self, parent, index):
        ev = self.peek_event()
        if (ev is not None and not isinstance(ev, AliasEvent)
                and getattr(ev, "anchor", None) and ev.anchor in self.anchors):
            del self.anchors[ev.anchor]
        return super().compose_node(parent, index)


def load_yaml(path):
    with open(path, "rb") as f:
        try:
            return yaml.load(f, Loader=yaml.CSafeLoader)
        except yaml.YAMLError:
            f.seek(0)
            return yaml.load(f, Loader=Tolerant)


# ------------------------------------------------------------------ поиск файлов

class Files:
    """Слои данных в том же порядке, в каком их читает движок: мод, мастер-мод, оригинал."""

    def __init__(self, roots):
        self.roots = [r for r in roots if os.path.isdir(r)]
        self.missing = set()

    def find(self, rel):
        for r in self.roots:
            p = os.path.join(r, rel)
            if os.path.exists(p):
                return p
        self.missing.add(rel)
        return None


# ------------------------------------------------------------------ террейны из рулсетов

def collect_terrains(mod_dir):
    """Все определения террейнов: из terrains, а также из кораблей и НЛО.

    У крафта и НЛО поле battlescapeTerrainData - это такой же террейн со своими наборами
    и блоками, и его тайлы игрок видит в каждом штурме. Пропустить их - потерять
    самые ходовые наборы игры.
    """
    terrains = {}
    rul_dir = os.path.join(mod_dir, "Ruleset")
    for name in sorted(os.listdir(rul_dir)):
        if not name.lower().endswith(".rul"):
            continue
        try:
            doc = load_yaml(os.path.join(rul_dir, name))
        except Exception as e:                                  # noqa: BLE001
            print("  рулсет %s не разобран: %s" % (name, e), file=sys.stderr)
            continue
        if not isinstance(doc, dict):
            continue
        found = list(doc.get("terrains") or [])
        for section in ("crafts", "ufos"):
            for item in doc.get(section) or []:
                if isinstance(item, dict) and isinstance(item.get("battlescapeTerrainData"), dict):
                    found.append(item["battlescapeTerrainData"])
        for t in found:
            if not isinstance(t, dict) or not t.get("name"):
                continue
            if not t.get("mapDataSets") or not t.get("mapBlocks"):
                continue
            terrains[t["name"]] = t
    return terrains


# ------------------------------------------------------------------ MCD и карты

def mcd_records(files, set_name, cache):
    """Записи MCD набора: кадры и тип на запись. Пустой список - набора нет на диске."""
    if set_name in cache:
        return cache[set_name]
    path = files.find(os.path.join("TERRAIN", set_name + ".MCD"))
    recs = []
    if path:
        with open(path, "rb") as f:
            data = f.read()
        recs = [{"frames": list(data[i:i + 8]), "type": data[i + 53]}
                for i in range(0, len(data) - MCD_RECORD + 1, MCD_RECORD)]
    cache[set_name] = recs
    return recs


def read_map(path):
    """Клетки блока карты: кортежи по четыре байта (пол, стена З, стена С, объект)."""
    with open(path, "rb") as f:
        data = f.read()
    if len(data) < 3:
        return []
    body = data[3:]
    return [tuple(body[i:i + 4]) for i in range(0, len(body) - 3, 4)]


def resolve(value, sets, sizes):
    """Байт клетки -> (набор, номер записи MCD). Ровно как RuleTerrain::getMapData."""
    idx = value
    for s in sets:
        size = sizes.get(s, 0)
        if idx < size:
            return s, idx
        idx -= size
    return None, None


def count_usage(files, terrains):
    """Сколько клеток всех карт приходится на каждую запись MCD каждого набора."""
    sizes = {}
    mcds = {}
    tiles = defaultdict(int)
    blocks = defaultdict(set)
    terr_of = defaultdict(set)
    set_terrains = defaultdict(set)
    set_blocks = defaultdict(set)
    set_tiles = defaultdict(int)            # по ЗАПИСЯМ, а не по кадрам: у анимации
                                            # восемь фаз рисуют одну и ту же клетку
    all_blocks = set()
    broken = []

    for ti, (tname, t) in enumerate(sorted(terrains.items()), 1):
        sets = list(t.get("mapDataSets") or [])
        for s in sets:
            if s not in sizes:
                sizes[s] = len(mcd_records(files, s, mcds))
            set_terrains[s].add(tname)
        for b in t.get("mapBlocks") or []:
            bname = b.get("name") if isinstance(b, dict) else None
            if not bname:
                continue
            mp = files.find(os.path.join("MAPS", bname + ".MAP"))
            if not mp:
                broken.append((tname, bname, "нет .MAP"))
                continue
            all_blocks.add(bname)
            try:
                cells = read_map(mp)
            except Exception as e:                              # noqa: BLE001
                broken.append((tname, bname, str(e)))
                continue
            for cell in cells:
                for part in range(4):
                    v = cell[part]
                    if not v:
                        continue
                    s, rec = resolve(v, sets, sizes)
                    if s is None:
                        continue
                    tiles[(s, rec)] += 1
                    set_tiles[s] += 1
                    blocks[(s, rec)].add(bname)
                    terr_of[(s, rec)].add(tname)
                    set_blocks[s].add(bname)
        if ti % 50 == 0:
            print("  террейнов разобрано %d из %d" % (ti, len(terrains)))

    return {"tiles": tiles, "blocks": blocks, "terrains": terr_of, "sizes": sizes,
            "mcds": mcds, "set_terrains": set_terrains, "set_blocks": set_blocks,
            "set_tiles": set_tiles, "all_blocks": all_blocks, "broken": broken}


# ------------------------------------------------------------------ отпечатки кадров

def sha(b):
    return hashlib.sha1(b).hexdigest()[:12]


def fingerprints(frame):
    """Четыре отпечатка кадра: рисунок, силуэт, зеркало, рисунок без учёта раскраски.

    recolor получается перенумерацией индексов по порядку первого появления: два кадра,
    нарисованные одной формой в разных рампах палитры, дают одинаковый ключ. Это КАНДИДАТ
    в перекраску, а не доказательство - решает глаз на листе сравнения.
    """
    flat = bytes(v for row in frame for v in row)
    mask = bytes(1 if v else 0 for v in flat)
    mirror = bytes(v for row in frame for v in reversed(row))
    order = {}
    norm = bytearray(len(flat))
    for i, v in enumerate(flat):
        if v:
            if v not in order:
                order[v] = len(order) + 1
            norm[i] = order[v]
    return {"exact": sha(flat), "shape": sha(mask), "mirror": sha(mirror),
            "recolor": sha(bytes(norm)), "pixels": sum(1 for v in flat if v),
            "colours": len(order)}


def read_set(files, rel):
    """Кадры набора по его PCK и TAB. (None, None) - набор не читается."""
    pck = files.find(rel)
    if not pck:
        return None, None
    tab = os.path.splitext(pck)[0] + ".TAB"
    w, h = xs.frame_size_for(os.path.basename(rel))
    try:
        frames = xs.read_pck(pck, tab if os.path.exists(tab) else None, w, h)
    except Exception as e:                                      # noqa: BLE001
        print("  %s не прочитан: %s" % (rel, e), file=sys.stderr)
        return None, None
    return frames, (w, h)


def list_pck_sets(roots):
    """Все PCK во всех слоях данных: ключ - относительный путь, значение - он же как на диске."""
    out = {}
    for root in roots:
        for dirpath, _dirs, names in os.walk(root):
            for n in names:
                if not n.upper().endswith(".PCK"):
                    continue
                rel = os.path.relpath(os.path.join(dirpath, n), root)
                out.setdefault(rel.replace("/", os.sep).upper(), rel)
    return out


# ------------------------------------------------------------------ отчёт

def write_tsv(path, header, rows):
    with open(path, "w", encoding=ENC, newline="") as f:
        f.write("\t".join(header) + "\n")
        for r in rows:
            f.write("\t".join("" if v is None else str(v) for v in r) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", default=os.path.join("Пиратки", "Dioxine_XPiratez"))
    ap.add_argument("--mod", default="Piratez")
    ap.add_argument("--master", default="xcom1")
    ap.add_argument("--hd", default="", help="каталог hd мода (чтобы отметить уже сделанное)")
    ap.add_argument("--out", default="census")
    args = ap.parse_args()

    mod_dir = os.path.join(args.install, "user", "mods", args.mod)
    files = Files([mod_dir,
                   os.path.join(args.install, "standard", args.master),
                   os.path.join(args.install, "UFO")])
    os.makedirs(args.out, exist_ok=True)
    if not args.hd:
        args.hd = os.path.join(args.install, "user", "mods", "hd", "hd")

    print("слои данных:")
    for r in files.roots:
        print("  " + r)

    print("разбираю рулсеты...")
    terrains = collect_terrains(mod_dir)
    print("  террейнов с наборами и блоками: %d" % len(terrains))

    print("считаю клетки карт...")
    u = count_usage(files, terrains)
    total_tiles = sum(u["tiles"].values())
    total_blocks = len(u["all_blocks"])
    print("  блоков карт: %d, клеток с содержимым: %d" % (total_blocks, total_tiles))
    if u["broken"]:
        print("  не прочитано блоков: %d" % len(u["broken"]))

    # запись MCD -> кадры PCK. Кадр виден столько раз, сколько клеток у записи, которая его
    # рисует; у анимированной записи так считается КАЖДАЯ её фаза - рисовать надо все.
    f_tiles = defaultdict(int)
    f_blocks = defaultdict(set)
    f_terr = defaultdict(set)
    anim_of = {}
    for (s, rec), n in u["tiles"].items():
        recs = u["mcds"].get(s) or []
        if rec >= len(recs):
            continue
        uniq = sorted(set(recs[rec]["frames"]))
        for fr in uniq:
            f_tiles[(s, fr)] += n
            f_blocks[(s, fr)] |= u["blocks"][(s, rec)]
            f_terr[(s, fr)] |= u["terrains"][(s, rec)]
            if len(uniq) > 1:
                anim_of[(s, fr)] = "%s:%d" % (s, uniq[0])

    print("читаю PCK...")
    sets = list_pck_sets(files.roots)
    rows = []
    by_exact = defaultdict(list)
    by_recolor = defaultdict(list)
    set_stat = {}
    done = 0
    for key in sorted(sets):
        rel = sets[key]
        frames, size = read_set(files, rel)
        done += 1
        if frames is None:
            continue
        w, h = size
        name = os.path.basename(rel)
        stem = os.path.splitext(name)[0]
        kind = rel.split(os.sep)[0].upper() if os.sep in rel else "."
        hd_dir = os.path.join(args.hd, "TERRAIN", name) if kind == "TERRAIN" \
            else os.path.join(args.hd, name)
        hd_have = set()
        if os.path.isdir(hd_dir):
            for fn in os.listdir(hd_dir):
                base = fn.split(".")[0]
                if base.isdigit():
                    hd_have.add(int(base))
        n_frames = 0
        for i, fr in enumerate(frames):
            if fr is None:
                continue
            fp = fingerprints(fr)
            if fp["pixels"] == 0:
                continue
            n_frames += 1
            gid = "%s#%d" % (stem, i)
            by_exact[fp["exact"]].append(gid)
            by_recolor[fp["recolor"]].append(gid)
            rows.append([kind, stem, i, w, h, fp["pixels"], fp["colours"],
                         fp["exact"], fp["shape"], fp["recolor"], fp["mirror"],
                         f_tiles.get((stem, i), 0), len(f_blocks.get((stem, i), ())),
                         len(f_terr.get((stem, i), ())),
                         anim_of.get((stem, i), ""), 1 if i in hd_have else 0])
        set_stat[stem] = {"kind": kind, "frames": n_frames, "hd": len(hd_have),
                          "tiles": u["set_tiles"].get(stem, 0),
                          "blocks": len(u["set_blocks"].get(stem, ())),
                          "terrains": len(u["set_terrains"].get(stem, ()))}
        if done % 60 == 0:
            print("  наборов прочитано %d из %d" % (done, len(sets)))

    # зеркало: кадр зеркален другому, если его зеркальный отпечаток совпал с чужим точным
    exact_seen = set(by_exact)
    for r in rows:
        r.append(1 if (r[10] in exact_seen and r[10] != r[7]) else 0)

    write_tsv(os.path.join(args.out, "frames.tsv"),
              ["раздел", "набор", "кадр", "ш", "в", "пикселей", "цветов",
               "точный", "силуэт", "раскраска", "зеркало",
               "клеток", "блоков", "террейнов", "анимация", "есть_hd", "зеркален"],
              rows)

    per_set = defaultdict(list)
    for r in rows:
        per_set[r[1]].append(r)
    srows = []
    for stem, st in sorted(set_stat.items()):
        idx = per_set.get(stem, [])
        srows.append([st["kind"], stem, st["frames"],
                      len({r[7] for r in idx}), len({r[9] for r in idx}),
                      len({r[14] for r in idx if r[14]}),
                      st["tiles"], st["blocks"], st["terrains"], st["hd"],
                      round(100.0 * st["blocks"] / total_blocks, 2) if total_blocks else 0,
                      round(100.0 * st["tiles"] / total_tiles, 3) if total_tiles else 0])
    srows.sort(key=lambda r: -r[6])
    write_tsv(os.path.join(args.out, "sets.tsv"),
              ["раздел", "набор", "кадров", "разных", "разных_без_цвета", "анимаций",
               "клеток", "блоков", "террейнов", "есть_hd", "доля_блоков_%", "доля_клеток_%"],
              srows)

    write_tsv(os.path.join(args.out, "missing.tsv"), ["не найдено"],
              [[m] for m in sorted(files.missing)])

    dup = sum(len(v) - 1 for v in by_exact.values() if len(v) > 1)
    rc = sum(len(v) - 1 for v in by_recolor.values() if len(v) > 1)
    print("")
    print("кадров с рисунком: %d" % len(rows))
    print("точных повторов: %d, разных рисунков: %d" % (dup, len(by_exact)))
    print("повторов с точностью до раскраски: %d, разных: %d" % (rc, len(by_recolor)))
    print("наборов: %d, блоков карт: %d, клеток: %d" % (len(set_stat), total_blocks, total_tiles))
    print("таблицы: %s" % os.path.abspath(args.out))


if __name__ == "__main__":
    main()
