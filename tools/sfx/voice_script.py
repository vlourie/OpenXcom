"""Сценарий озвучки бойцов и юнитов (docs/research/voice-recording-script.md) - в данные для генерации.

Карточка голоса в сценарии:
    ### V025 — Киллбот / Destroid [Н]
    **Для кого:** ...   **По игре:** ...   **Как играть голосом:** ...
    **Выбор бойца**            <- подзаголовок раздела реплик, есть не у всех
    | № | Русский | English |
    | 01 | ... | ... |
Раздел верхнего уровня (## Команда..., ## Машины...) - часть голоса (section).

    py -3 tools/sfx/voice_script.py                       сводка по разделам
    py -3 tools/sfx/voice_script.py --import <файл.md>    положить новую версию сценария в docs (со спецификацией)
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "docs/research/voice-recording-script.md"

HEAD = re.compile(r"^### (V\d{3}) — (.+?) \[([МЖН])\]\s*$")
ROW = re.compile(r"^\| (\d{2}) \| (.+?) \| (.+?) \|\s*$")
FIELD = re.compile(r"^\*\*(Для кого|По игре|Как играть голосом):\*\*\s*(.*)$")
SUB = re.compile(r"^\*\*([^*:]+)\*\*\s*$")
KEYS = {"Для кого": "for", "По игре": "game", "Как играть голосом": "direction"}


def parse(path=SCRIPT):
    voices = []
    section = ""
    cur = None
    sub = ""
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
            cur = None
            continue
        m = HEAD.match(line)
        if m:
            cur = {"id": m.group(1), "name": m.group(2).strip(), "reg": m.group(3), "section": section,
                   "for": "", "game": "", "direction": "", "lines": []}
            voices.append(cur)
            sub = ""
            continue
        if cur is None:
            continue
        m = FIELD.match(line)
        if m:
            cur[KEYS[m.group(1)]] = m.group(2).strip()
            continue
        m = SUB.match(line)
        if m:
            sub = m.group(1).strip()
            continue
        m = ROW.match(line)
        if m:
            cur["lines"].append({"n": m.group(1), "ru": m.group(2).strip(), "en": m.group(3).strip(),
                                 "part": sub})
    return voices


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--import", dest="src", default="", help="новая версия сценария - скопировать в docs")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if a.src:
        b = Path(a.src).read_bytes()
        SCRIPT.write_bytes(b if b.startswith(b"\xef\xbb\xbf") else b"\xef\xbb\xbf" + b)
        print("сценарий:", SCRIPT)
    voices = parse()
    secs = {}
    for v in voices:
        s = secs.setdefault(v["section"], [0, 0, {"М": 0, "Ж": 0, "Н": 0}])
        s[0] += 1
        s[1] += len(v["lines"])
        s[2][v["reg"]] += 1
    for name, (n, k, reg) in secs.items():
        print(f"{n:4} голосов {k:5} реплик  М{reg['М']} Ж{reg['Ж']} Н{reg['Н']}  {name}")
    print(f"всего: {len(voices)} голосов, {sum(len(v['lines']) for v in voices)} реплик на язык")
    bad = [v["id"] for v in voices if not v["lines"] or not v["direction"]]
    if bad:
        print("без реплик или без указаний голосу:", bad)


if __name__ == "__main__":
    main()
