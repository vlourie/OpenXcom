"""Установка слоя B2 предметов инвентаря (item_b2_render.py) в обе копии мода hd (слово Vitali 15.10:
«B2 годится, клади все 1205 кадров»).

Что ставится: census/items/redo/b2/pack/BIGOBS.PCK/<кадр>.wide.png - общий файл кадра с меткой (обрезка
ровно по кадру классики, перо не дальше классики, item_b2_render.make_pack). Кадр, у которого в манифесте
или в установке уже есть свой файл предмета (<кадр>.<ТИП>...png, принятый M-01 STR_RIFLE_AK), общим
файлом не дублируется: свой файл движок берёт первым (HdItems: шаг 1), общий был бы мёртвым.

  item_b2_install.py [--yes]

Без --yes - сухой прогон. С --yes - манифест (build_hd_pack.stage), установка в обе копии мода hd,
сверка sha256 и числа файлов набора с манифестом (без своих файлов предметов, которых в манифесте нет).
Файлы мода - файлы игры: запускать, держа очередь правок (py -3 tools/editq.py wait).
"""
import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

ROOT = Path(HERE).resolve().parents[1]
PACK = ROOT / "census" / "items" / "redo" / "b2" / "pack" / "BIGOBS.PCK"
GAME = ROOT / "Пиратки" / "Dioxine_XPiratez" / "user" / "mods" / "hd" / "hd"
REPO = ROOT / "user" / "mods" / "hd" / "hd"
SET = "BIGOBS.PCK/"
# <кадр>.<ТИП>[.wide][.hand].png; тип - не сама метка: общий <кадр>.wide.png своим файлом не считается
OWN = re.compile(r"^(\d+)\.(?!(?:wide|hand)\.)[^.]+\.(?:wide\.)?(?:hand\.)?png$", re.I)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--pack", default=str(PACK), help="пак B2 (остаток: census/items/redo/b2_rest/pack/BIGOBS.PCK)")
    ap.add_argument("--approval", default="Vitali 15.10: B2 годится, все 1205 кадров", help="чьё слово - в манифест")
    a = ap.parse_args()
    pack = Path(a.pack).resolve()
    os.chdir(ROOT)
    sys.stdout.reconfigure(encoding="utf-8")
    import build_hd_pack as bp
    man = bp.load()
    own = set()
    for root in (GAME / SET, REPO / SET):
        if root.is_dir():
            for f in os.listdir(root):
                m = OWN.match(f)
                if m:
                    own.add(int(m.group(1)))
    for rel in man["files"]:
        if rel.startswith(SET):
            m = OWN.match(rel[len(SET):])
            if m:
                own.add(int(m.group(1)))
    files = sorted(pack.glob("*.wide.png"), key=lambda p: int(p.name.split(".")[0]))
    plan = [(SET + p.name, p) for p in files if int(p.name.split(".")[0]) not in own]
    skip = [p.name for p in files if int(p.name.split(".")[0]) in own]
    print("в паке %d, ставится %d, пропущено (свой файл предмета) %d %s" % (len(files), len(plan), len(skip), skip))
    if not a.yes:
        raise SystemExit("сухой прогон; --yes - записать")
    for rel, p in plan:
        old = man["files"].get(rel, {}).get("sha256")
        bp.stage(man, rel, str(p), generator="item_b2", generator_version="item_b2_render.py 15.10 B2",
                 source_path=str(p.relative_to(ROOT)).replace(os.sep, "/"), approved=True,
                 approval=a.approval, source_frame="BIGOBS:" + p.name.split(".")[0],
                 replaced=old)
    rels = [r for r, _ in plan]
    bp.save(man, why="item_b2: %d кадров BIGOBS" % len(rels))
    print("game:", bp.install(man, "game", only=rels))
    print("repo:", bp.install(man, "repo", only=rels))
    bad = 0
    for r in rels:
        for root in (GAME, REPO):
            # сверка - только что поставленных; прошлые партии сверены своим запуском и посчитаны ниже числом
            if hashlib.sha256((root / r).read_bytes()).hexdigest() != man["files"][r]["sha256"]:
                print("РАСХОДИТСЯ", root, r)
                bad += 1
    nm = len([k for k in man["files"] if k.startswith(SET)])
    for root in (GAME, REPO):
        names = os.listdir(root / SET)
        common = [f for f in names if not OWN.match(f)]
        if len(common) != nm:
            print("ЧИСЛО ФАЙЛОВ", root, "общих", len(common), "манифест", nm)
            bad += 1
        print(root, "файлов", len(names), "из них своих файлов предметов", len(names) - len(common))
    print("сверка: расхождений", bad)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
