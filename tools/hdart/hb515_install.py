"""Установка выбора Vitali 05.11 по XP-000515: металлический баррель, вариант B (зерно 5242), вся семья, 12 кадров.

Кандидаты собирает hb517_build.py (art/tickets/hb517/cand/barrelB).
    py -3.13 tools/hdart/hb515_install.py          # показать, что изменится
    py -3.13 tools/hdart/hb515_install.py --yes    # в обе копии мода через манифест
"""
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(r"E:\OpenXCom")
import build_hd_pack as bp              # noqa: E402

SRC = os.path.join("art", "tickets", "hb517", "cand", "barrelB")
GEN = "hb517_build"
WORD = "XP-000515, баррель вместо деревянной бочки, зерно 5242 (Vitali, страница 05.11: вариант B)"


def rel_of(fn):
    s, f = fn[:-4].rsplit("_", 1)
    return "TERRAIN/%s.PCK/%d.png" % (s, int(f))


def sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def plan():
    root = bp.TARGETS["repo"]
    out = []
    for fn in sorted(os.listdir(SRC)):
        rel, path = rel_of(fn), os.path.join(SRC, fn)
        cur = os.path.join(root, rel)
        if os.path.exists(cur) and sha(cur) == sha(path):
            print("без изменений:", rel)
            continue
        out.append((rel, path))
    return out


def install(items):
    man = bp.load()
    rels = []
    for rel, path in items:
        old = man["files"].get(rel, {})
        bp.stage(man, rel, path, generator=GEN,
                 generator_version="%s 05.11; было: %s %s" % (GEN, old.get("generator"), old.get("generator_version") or ""),
                 source_path=path.replace(os.sep, "/"), approved=True, approval=WORD)
        rels.append(rel)
    bp.save(man, why="XP-000515: баррель, вариант B (%d файлов)" % len(rels))
    print("game:", bp.install(man, "game", only=rels))
    print("repo:", bp.install(man, "repo", only=rels))
    for root in bp.TARGETS.values():
        for rel in rels:
            if sha(os.path.join(root, rel)) != man["files"][rel]["sha256"]:
                raise SystemExit("РАСХОДИТСЯ %s %s" % (root, rel))
    print("сверено: обе копии, файлов", len(rels))


if __name__ == "__main__":
    items = plan()
    print("всего", len(items))
    if "--yes" in sys.argv:
        install(items)
