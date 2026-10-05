"""Умолчание опции, которая уже уходила игрокам, сменили без смены ключа (грабли R-105).

options.cfg игрока хранит значение каждого ключа, и сохранённое перебивает умолчание из кода:
новое умолчание до игрока, запускавшего прежний выпуск, не доходит. Тест сравнивает
OptionInfo(..., "ключ", &переменная, умолчание, ...) в src/Engine/Options.cpp с последним
коммитом выпуска (сообщение "release: ...") и падает на ключе, у которого умолчание другое.

    py -3.13 tools/test_option_defaults.py                       # рабочее дерево против выпуска
    py -3.13 tools/test_option_defaults.py --base 34c6a8ba5 --head 9c4283e8e   # контрольный опыт: падает
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = "src/Engine/Options.cpp"
# OptionInfo(OPTION_OXCE, "key", &var, default, "STR_...", ...) - умолчание до первой запятой вне кавычек
OPT = re.compile(r'OptionInfo\(\s*OPTION_\w+\s*,\s*"([^"]+)"\s*,\s*&[\w:]+\s*,\s*("[^"]*"|[^,)]+)')


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", check=True).stdout


def defaults(text):
    return {m.group(1): m.group(2).strip() for m in OPT.finditer(text)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="", help="коммит выпуска (по умолчанию последний 'release: ...')")
    ap.add_argument("--head", default="", help="коммит для проверки (по умолчанию рабочее дерево)")
    a = ap.parse_args()
    base = a.base or git("log", "-1", "--format=%h", "--grep=^release:").strip()
    old = defaults(git("show", f"{base}:{FILE}"))
    new = defaults(git("show", f"{a.head}:{FILE}") if a.head else (ROOT / FILE).read_text(encoding="utf-8"))
    if len(old) < 100 or len(new) < 100:
        print(f"FAIL: разобрано опций {len(old)} / {len(new)} - регулярка не видит OptionInfo")
        return 1
    bad = [(k, old[k], new[k]) for k in sorted(old.keys() & new.keys()) if old[k] != new[k]]
    print(f"опций: выпуск {base} - {len(old)}, проверяемое - {len(new)}, общих ключей {len(old.keys() & new.keys())}")
    for k, o, n in bad:
        print(f"FAIL: {k}: умолчание {o} -> {n}, а ключ прежний - у игрока останется сохранённое {o}. Смени ключ")
    if not bad:
        print("OK: умолчания выпущенных ключей не менялись")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
