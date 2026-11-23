"""Проверка CHANGELOG.md перед выпуском (R-801): новые пункты только в разделе «[Не выпущено]».

Сравнивает CHANGELOG.md в рабочей копии с последним тегом выпуска hd-* и ищет пункты «- », которых в теге не было
и которые лежат ниже раздела «[Не выпущено]», то есть дописаны в уже вышедший раздел. Выпуск берёт русское
«Что нового» только из «[Не выпущено]», такой пункт игроки не увидят.

    py -3 tools/changelog_check.py            # код 0 - всё в порядке, 1 - есть пункты в вышедших разделах
"""
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True).stdout.decode("utf-8", "replace")


def items(text):
    return [x.strip() for x in text.lstrip("﻿").splitlines()]


def main():
    tags = [t for t in git("tag", "--sort=-creatordate").split() if t.startswith("hd-")]
    if not tags:
        print("нет тегов выпуска hd-* - сверять не с чем")
        return 0
    old = set(x for x in items(git("show", tags[0] + ":CHANGELOG.md")) if x.startswith("- "))
    cur = items((ROOT / "CHANGELOG.md").read_text(encoding="utf-8-sig"))
    section = None
    bad = []
    for x in cur:
        if x.startswith("## "):
            section = x[3:]
        elif x.startswith("- ") and x not in old and section != "[Не выпущено]":
            bad.append((section, x))
    for section, x in bad:
        print("ВНЕ «[Не выпущено]» (раздел %s): %s" % (section, x[:120]))
    if bad:
        print("%d пункт(ов) дописаны в вышедшие разделы после %s - перенесите их в «[Не выпущено]»" % (len(bad), tags[0]))
        return 1
    print("CHANGELOG: новые пункты после %s только в «[Не выпущено]»" % tags[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
