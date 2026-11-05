"""Установка выбора Vitali 06.11 по XP-000516: 4 крылатые ракеты на стенде, вариант A (основа rockets4, зерно 5142), 6 кадров:
XB2BR 10, 11 и перекраски PLANE2, PLANE2R 118, 119.

Кандидаты собирает hb516_v4.py (art/tickets/hb517/cand/rockets4A).
    py -3.13 tools/hdart/hb516_install.py          # показать, что изменится
    py -3.13 tools/hdart/hb516_install.py --yes    # в обе копии мода через манифест
"""
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(r"E:\OpenXCom")
import build_hd_pack as bp              # noqa: E402

SRC = os.path.join("art", "tickets", "hb517", "cand", "rockets4A")
GEN = "hb516_v4"
WORD = "XP-000516, 4 крылатые ракеты на стенде по заметкам Vitali, зерно 5142 (Vitali, страница 06.11: вариант A)"


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
                 generator_version="%s 06.11; было: %s %s" % (GEN, old.get("generator"), old.get("generator_version") or ""),
                 source_path=path.replace(os.sep, "/"), approved=True, approval=WORD)
        rels.append(rel)
    bp.save(man, why="XP-000516: ракеты, вариант A (%d файлов)" % len(rels))
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
