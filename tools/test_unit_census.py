#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""unit_census.py собирает цепочку модов и сдвиги номеров так же, как движок.

Синтетическая установка, без Пираток:
  * мод без id в metadata.yml получает id по имени папки (ModInfo: _id(_name), _name -
    CrossPlatform::baseFilename(path)) - иначе он выпадает из цепочки, и сдвиги всех модов
    после него уезжают на его reservedSpace (так было с UFOextender_Psionic_Line_Of_Fire);
  * порядок - активные моды из options.cfg, неактивные не входят;
  * сдвиг - 1000 x накопленный reservedSpace (Mod.cpp: _modData[i].offset = 1000 * offset),
    reservedSpace зажат в 1..100 (ModInfo::load).

Контроль: прежнее чтение id (без запасного имени папки) обязано дать другие сдвиги.

    py -3.13 tools\\test_unit_census.py
"""
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import unit_census as uc  # noqa: E402

OPTIONS = """\
mods:
  - id: xcom1
    active: true
  - id: piratez
    active: true
  - id: NoIdMod
    active: true
  - id: sleeper
    active: false
  - id: after
    active: true
"""

MODS = {
    "standard/xcom1": 'id: xcom1\nname: "UFO: Enemy Unknown"\nisMaster: true\n',
    "user/mods/Piratez": 'id: piratez\nname: "X-Piratez"\nisMaster: true\nreservedSpace: 3\n',
    "user/mods/NoIdMod": 'name: "Mod without id"\nmaster: piratez\n',
    "user/mods/Sleeper": 'id: sleeper\nmaster: piratez\n',
    "user/mods/After": 'id: after\nmaster: piratez\nreservedSpace: 500\n',
}

# по правилам движка, посчитано руками: xcom1 1, piratez 3, NoIdMod 1, after 500 -> 100
WANT_CHAIN = ["xcom1", "piratez", "NoIdMod", "after"]
WANT_OFF = {"xcom1": (0, 1000), "piratez": (1000, 3000), "NoIdMod": (4000, 1000), "after": (5000, 100000)}


def make_tree(root: Path):
    (root / "user").mkdir(parents=True)
    (root / "user" / "options.cfg").write_text(OPTIONS, encoding="utf-8")
    for rel, meta in MODS.items():
        d = root / rel
        d.mkdir(parents=True)
        (d / "metadata.yml").write_text(meta, encoding="utf-8")


def old_chain(pz: Path):
    """Прежняя логика: id только из metadata.yml - мод без id не находится."""
    import yaml
    cfg = yaml.safe_load((pz / "user" / "options.cfg").read_text(encoding="utf-8"))
    active = [m["id"] for m in cfg.get("mods", []) if m.get("active")]
    dirs = {}
    for base in (pz / "user" / "mods", pz / "standard"):
        for d in base.iterdir():
            if d.is_dir():
                mid = uc.read_meta(d).get("id")
                if mid:
                    dirs.setdefault(mid, d)
    chain = [("xcom1", pz / "standard" / "xcom1")]
    for mid in active:
        if mid in dirs and mid != "xcom1":
            chain.append((mid, dirs[mid]))
    return chain


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    bad = 0

    def check(ok, what):
        nonlocal bad
        print(("ok    " if ok else "FAIL  ") + what)
        bad += not ok

    with tempfile.TemporaryDirectory() as tmp:
        pz = Path(tmp)
        make_tree(pz)

        chain = uc.piratez_chain(pz)
        ids = [m for m, _ in chain]
        check(ids == WANT_CHAIN, f"цепочка {ids}")
        check(dict(chain).get("NoIdMod") == pz / "user" / "mods" / "NoIdMod",
              "мод без id найден по имени папки")
        off = uc.mod_offsets(chain)
        check(off == WANT_OFF, f"сдвиги {off}")

        # контроль: прежняя логика теряет мод без id, и сдвиг следующего уезжает
        old = old_chain(pz)
        old_off = uc.mod_offsets(old)
        check("NoIdMod" not in dict(old) and old_off.get("after") != WANT_OFF["after"],
              f"контроль: прежнее чтение даёт after {old_off.get('after')} вместо {WANT_OFF['after']}")

    print("ИТОГ:", "все проверки прошли" if not bad else f"провалено {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
