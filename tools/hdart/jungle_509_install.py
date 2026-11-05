"""Установка выбора Vitali 05.11 по XP-000509 и XP-000510: ступени, цветок B, лианы B, куст из листьев.

Заготовки собирают hb_stairs.py, p509_flower_build.py, p509_liana_build.py, p510_bush4.py.
    py -3.13 tools/hdart/jungle_509_install.py          # показать, что изменится
    py -3.13 tools/hdart/jungle_509_install.py --yes    # в обе копии мода через манифест
"""
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(r"E:\OpenXCom")
import build_hd_pack as bp              # noqa: E402

ART = os.path.join("art", "tickets")
FLOWER_B = "5093"
LIANA_B = "5174"
PARTS = (
    ("hb_stairs", os.path.join(ART, "hb_stairs"), "XP-000509, ступени: край по маске классики, цвет прежний (Vitali, страница 05.11: ставить)"),
    ("p509_flower_build", os.path.join(ART, "hb509", "flower", FLOWER_B), "XP-000509, красный цветок, зерно 5093 (Vitali, страница 05.11: вариант B)"),
    ("p509_liana_build", os.path.join(ART, "hb509", "liana", LIANA_B), "XP-000509, лианы, зерно 5174 (Vitali, страница 05.11: вариант B)"),
    ("p510_bush4", os.path.join(ART, "hb509", "bush4"), "XP-000510, куст: HD JUNGLE:4, цвет своего набора (Vitali, страница 05.11: ставить)"),
    ("b3b_build", os.path.join(ART, "hb510_bush3", "A"), "XP-000510, куст со стволом: силуэт и цвет классики, лист JUNGLE:4 (Vitali, страница 05.11: вариант A)"),
)
SKIP_SETS = {"SIETCH_DARK"}     # край уже прямой, свой одобренный HD


def rel_of(fn):
    s, f = fn[:-4].rsplit("_", 1)
    return s, "TERRAIN/%s.PCK/%d.png" % (s, int(f))


def sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def plan():
    root = bp.TARGETS["repo"]
    out = []
    for gen, d, word in PARTS:
        for fn in sorted(os.listdir(d)):
            s, rel = rel_of(fn)
            if s in SKIP_SETS:
                continue
            path = os.path.join(d, fn)
            cur = os.path.join(root, rel)
            if os.path.exists(cur) and sha(cur) == sha(path):
                print("без изменений:", rel)
                continue
            out.append((gen, word, rel, path))
    return out


def install(items):
    man = bp.load()
    rels = []
    for gen, word, rel, path in items:
        old = man["files"].get(rel, {})
        bp.stage(man, rel, path, generator=gen,
                 generator_version="%s 05.11; было: %s %s" % (gen, old.get("generator"), old.get("generator_version") or ""),
                 source_path=path.replace(os.sep, "/"), approved=True, approval=word)
        rels.append(rel)
    bp.save(man, why="XP-000509, XP-000510: ступени, цветок B, лианы B, куст (%d файлов)" % len(rels))
    print("game:", bp.install(man, "game", only=rels))
    print("repo:", bp.install(man, "repo", only=rels))
    for root in bp.TARGETS.values():
        for rel in rels:
            if sha(os.path.join(root, rel)) != man["files"][rel]["sha256"]:
                raise SystemExit("РАСХОДИТСЯ %s %s" % (root, rel))
    print("сверено: обе копии, файлов", len(rels))


if __name__ == "__main__":
    items = plan()
    for gen in dict.fromkeys(i[0] for i in items):
        print(gen, sum(1 for i in items if i[0] == gen))
    print("всего", len(items))
    if "--yes" in sys.argv:
        install(items)
