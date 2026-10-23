"""Проверка: HD-кадры всего, что оставляет обрушение: записи завала из таблицы RUBBLE, стволы (logsOf),
мёртвые записи объектов и стен наборов таблицы (деревья, столбы, заборы). Обе копии мода hd."""
import os, re, sys

ROOT = "E:/OpenXCom"
SRC = os.path.join(ROOT, "src/Battlescape/CollapsePilot.cpp")
MCD_DIRS = [os.path.join(ROOT, "Пиратки/Dioxine_XPiratez/user/mods/Piratez/TERRAIN"),
            os.path.join(ROOT, "bin/UFO/TERRAIN"), os.path.join(ROOT, "user/mods/hd/TERRAIN"),
            os.path.join(ROOT, "user/mods/hd_core/TERRAIN")]
HD = [os.path.join(ROOT, "user/mods/hd/hd/TERRAIN"),
      os.path.join(ROOT, "Пиратки/Dioxine_XPiratez/user/mods/hd/hd/TERRAIN")]

text = open(SRC, encoding="utf-8").read()
defs = dict(re.findall(r'#define (\w+) "([^"]*)"', text))
body = text[text.index("const RubbleRow RUBBLE[]"):]
body = body[:body.index("\n};")]
for k, v in defs.items():
    body = re.sub(r"\b%s\b" % k, '"%s"' % v, body)
rows = []
for m in re.finditer(r'\{\s*"([^"]*)",\s*(true|false),\s*\{\s*"([^"]*)",\s*"([^"]*)",\s*"([^"]*)",\s*"([^"]*)"\s*\},\s*("[^"]*"|nullptr),\s*("[^"]*"|nullptr)', body):
    rows.append(m.groups())

cache = {}
def mcd(name):
    if name in cache:
        return cache[name]
    recs = None
    for d in MCD_DIRS:
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            if f.upper() == name.upper() + ".MCD":
                data = open(os.path.join(d, f), "rb").read()
                recs = [data[i:i + 62] for i in range(0, len(data) - 61, 62)]
                break
        if recs is not None:
            break
    cache[name] = recs
    return recs

def hd_missing(name, rec):
    r = mcd(name)
    if r is None or rec >= len(r):
        return ["нет MCD/записи"]
    frames = sorted(set(r[rec][0:8]))
    miss = []
    for i, root in enumerate(HD):
        lost = [fr for fr in frames if not os.path.isfile(os.path.join(root, name + ".PCK", "%d.png" % fr))]
        if lost:
            miss.append("копия%d кадры %s" % (i + 1, lost))
    return miss

checked = {}
def check(tag, name, rec):
    key = (name, rec)
    if key in checked:
        return
    checked[key] = (tag, hd_missing(name, rec))

sets = set()
for names, land, stone, wood, metal, plant, heap, block in rows:
    sets.update(names.split())
    for kind, lst in (("камень", stone), ("дерево", wood), ("металл", metal), ("бурелом", plant)):
        for item in lst.split():
            s, r = item.split(":")
            sets.add(s)
            check("завал/" + kind, s, int(r))
    for lst in (heap, block):
        if lst != "nullptr":
            for item in lst.strip('"').split():
                s, r = item.split(":")
                check("куча/глыба", s, int(r))
for r in range(1, 19):
    check("COLLAPSE_DEBRIS", "COLLAPSE_DEBRIS", r)

# стволы и мёртвые записи объектов/стен наборов таблицы
for s in sorted(sets):
    recs = mcd(s)
    if not recs:
        continue
    for i, d in enumerate(recs):
        die = d[44]
        typ = d[53]
        if die and typ in (1, 2, 3) and die < len(recs):
            check("смерть типа%d из %d" % (typ, i), s, die)

bad = [(k, v) for k, v in checked.items() if v[1]]
print("проверено записей:", len(checked), " без HD:", len(bad))
for (s, r), (tag, miss) in sorted(bad):
    print("  %s:%d  [%s]  %s" % (s, r, tag, "; ".join(miss)))

# --- все наборы: живая запись в HD, а её мёртвая (Die_MCD) нет
names = set()
for d in MCD_DIRS:
    if os.path.isdir(d):
        names.update(f[:-4] for f in os.listdir(d) if f.upper().endswith(".MCD"))
def has(root, s, fr):
    return os.path.isfile(os.path.join(root, s + ".PCK", "%d.png" % fr))
out = []
for s in sorted(names):
    recs = mcd(s)
    if not recs: continue
    for i, d in enumerate(recs):
        die, typ = d[44], d[53]
        if not die or typ not in (1, 2, 3) or die >= len(recs): continue
        alive = sorted(set(d[0:8])); dead = sorted(set(recs[die][0:8]))
        for c, root in enumerate(HD):
            if all(has(root, s, f) for f in alive) and not all(has(root, s, f) for f in dead):
                out.append((s, i, die, c + 1, [f for f in dead if not has(root, s, f)]))
print("живое в HD, мёртвое нет:", len(out))
from collections import Counter
print(Counter((o[0], o[3]) for o in out).most_common(60))
for o in out:
    if o[3] == 2: print("  ", o[0], "живая", o[1], "-> мёртвая", o[2], "нет кадров", o[4])
