"""Нежный режим (src/Engine/HdGentle.h) - только картинка и темп, механику он не видит.

Решение 2026-10-01 (docs/DECISIONS.md, docs/research/gentle-mode.md): режим подставляет свои значения
лишь там, где игра решает, КАК показывать. Тест ищет каждый вызов HdGentle:: в src и пропускает его
только в файлах рендера, таймеров и экранов, а в файлах боя - только строку известного вида
(интервал шага, скорость снаряда, слежение камеры, добивание). Вызов в любом другом месте - падение:
значит режим полез в правила (стрельба, видимость, ИИ, сохранение).

    py -3 tools/test_gentle_scope.py            # дерево src
    py -3 tools/test_gentle_scope.py --control  # контрольный опыт: вызов в TileEngine.cpp обязан поймать
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
CALL = re.compile(r"\bHdGentle::")

# файлы, где режим вправе стоять в любой строке: только картинка, звук и экраны
FREE = [
    re.compile(r"^Engine/Hd[^/]*$"),
    re.compile(r"^Engine/Screen\.cpp$"),
    re.compile(r"^Menu/[^/]*$"),
    re.compile(r"^Interface/[^/]*$"),
    re.compile(r"^Geoscape/Globe\.cpp$"),
    re.compile(r"^Basescape/BaseView\.cpp$"),
    re.compile(r"^Battlescape/(Map|Camera|UnitSprite|ItemSprite|BattlescapeState)\.cpp$"),
]

# файлы боя: режим вправе стоять лишь в строке такого вида
LINES = {
    "Battlescape/UnitWalkBState.cpp": re.compile(r"setStateInterval\(HdGentle::(xcom|alien)Speed\(\)\);"),
    "Battlescape/UnitTurnBState.cpp": re.compile(r"setStateInterval\(HdGentle::(xcom|alien)Speed\(\)\);"),
    "Battlescape/UnitFallBState.cpp": re.compile(r"setStateInterval\(HdGentle::(xcom|alien)Speed\(\)\);"),
    "Battlescape/Projectile.cpp": re.compile(r"_speed = HdGentle::fireSpeed\(\);"),
    "Battlescape/ProjectileFlyBState.cpp": re.compile(r"const bool byOptions = .*HdGentle::traceProjectiles\(\)"),
    "Battlescape/UnitDieBState.cpp": re.compile(r"if \(!HdGentle::killCam\(\) \|\|"),
}


def check(files):
    """files: {путь от src через /: текст}. Возвращает список нарушений и число найденных вызовов."""
    bad, calls = [], 0
    for rel, text in files.items():
        for n, line in enumerate(text.splitlines(), 1):
            if not CALL.search(line) or line.lstrip().startswith("//"):
                continue
            calls += 1
            if any(p.match(rel) for p in FREE):
                continue
            rule = LINES.get(rel)
            if rule and rule.search(line):
                continue
            bad.append(f"src/{rel}:{n}: {line.strip()}")
    return bad, calls


def tree():
    out = {}
    for p in SRC.rglob("*"):
        if p.suffix in (".cpp", ".h") and p.is_file():
            out[p.relative_to(SRC).as_posix()] = p.read_text(encoding="utf-8", errors="replace")
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # R-001: вывод в трубу иначе cp1252
    ap = argparse.ArgumentParser()
    ap.add_argument("--control", action="store_true", help="подмешать вызов в TileEngine.cpp - тест обязан упасть")
    a = ap.parse_args()
    files = tree()
    if len(files) < 500:
        sys.exit(f"прочитано {len(files)} файлов src - не то дерево")
    if a.control:
        files["Battlescape/TileEngine.cpp"] += "\n\tif (HdGentle::on()) return false;\n"
        files["Battlescape/UnitWalkBState.cpp"] += "\n\tint tu = HdGentle::xcomSpeed();\n"
    bad, calls = check(files)
    print(f"вызовов HdGentle:: в src: {calls}, файлов прочитано: {len(files)}")
    if bad:
        print("нежный режим вне картинки и темпа:")
        for b in bad:
            print("  " + b)
        sys.exit(1)
    if calls == 0:
        sys.exit("ни одного вызова HdGentle:: - режим не подключён, проверять нечего")
    print("ok")


if __name__ == "__main__":
    main()
