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
# 16.10 Vitali: «1-2 фразы это мало». Дополнение к сценарию: «### V001+ — имя» - ещё реплики голоса
# (extra), «### V401 — имя [Ж]» с «**Реплики как:** V001» - запасной голос того же типа бойца
EXTRA = ROOT / "docs/research/voice-script-extra.md"

HEAD = re.compile(r"^### (V\d{3}) — (.+?) \[([МЖН])\]\s*$")
MORE = re.compile(r"^### (V\d{3})\+ — (.+?)\s*$")
ROW = re.compile(r"^\| (\d{2}) \| (.+?) \| (.+?) \|\s*$")
FIELD = re.compile(r"^\*\*(Для кого|По игре|Как играть голосом|Реплики как):\*\*\s*(.*)$")
SUB = re.compile(r"^\*\*([^*:]+)\*\*\s*$")
KEYS = {"Для кого": "for", "По игре": "game", "Как играть голосом": "direction", "Реплики как": "same_as"}


def parse(path=SCRIPT, extra=EXTRA):
    voices = _read(path, {})
    if extra and Path(extra).exists():
        by_id = {v["id"]: v for v in voices}
        alts = _read(extra, by_id)
        for v in alts:
            src = by_id[v["same_as"]]
            v.update(section=src["section"], game=src["game"], **{"for": src["for"]})
        for v in alts:
            v["lines"] = [dict(ln) for ln in by_id[v["same_as"]]["lines"]]
        voices += alts
    return voices


def _read(path, by_id):
    voices = []
    section = ""
    cur = None
    sub = ""
    extra = bool(by_id)
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
            cur = None
            continue
        m = MORE.match(line) if extra else None
        if m:
            cur = by_id[m.group(1)]
            sub = ""
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
            ln = {"n": m.group(1), "ru": m.group(2).strip(), "en": m.group(3).strip(), "part": sub}
            if extra:
                ln["extra"] = True
            cur["lines"].append(ln)
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
