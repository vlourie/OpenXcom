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
    py -3 tools/sfx/voice_script.py --pin-ready           закрепить голоса с готовой «сотней» для сборки модов
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "docs/research/voice-recording-script.md"
# 16.10 Vitali: «1-2 фразы это мало». Дополнение к сценарию: «### V001+ — имя» - ещё реплики голоса
# (extra), «### V401 — имя [Ж]» с «**Реплики как:** V001» - запасной голос того же типа бойца
EXTRA = ROOT / "docs/research/voice-script-extra.md"
# 21.10 Vitali: «минимум сотня каждому» на выбор и движение - номера трёхзначные, четвёртый столбец - подача
MORE100 = ROOT / "docs/research/voice-script-100.md"
VOICEPACK = ROOT / "art/sfx/voicepack"
READY = VOICEPACK / "more100_ready.txt"

HEAD = re.compile(r"^### (V\d{3}) — (.+?) \[([МЖН])\]\s*$")
MORE = re.compile(r"^### (V\d{3})\+ — (.+?)\s*$")
ROW = re.compile(r"^\| (\d{2,3}) \| (.+?) \| (.+?) \|(?: (\[.*?\]) \|)?\s*$")
FIELD = re.compile(r"^\*\*(Для кого|По игре|Как играть голосом|Реплики как):\*\*\s*(.*)$")
SUB = re.compile(r"^\*\*([^*:]+)\*\*\s*$")
KEYS = {"Для кого": "for", "По игре": "game", "Как играть голосом": "direction", "Реплики как": "same_as"}


def parse(path=SCRIPT, extra=EXTRA, more=None, only=None):
    # more=MORE100 - со «сотней»; по умолчанию без неё: сборка модов сверяет сценарий с записанным целиком.
    # only - голоса, которым брать «сотню» (сборка модов: pinned(), записанные целиком), None - всем
    voices = _read(path, {})
    by_id = {v["id"]: v for v in voices}
    if extra and Path(extra).exists():
        alts = _read(extra, by_id)
        for v in alts:
            src = by_id[v["same_as"]]
            v.update(section=src["section"], game=src["game"], **{"for": src["for"]})
        for v in alts:
            v["lines"] = [dict(ln) for ln in by_id[v["same_as"]]["lines"]]
        voices += alts
    if more and Path(more).exists() and (only is None or only):
        _read(more, by_id, only)
    return voices


def pinned():
    """Голоса, у которых «сотня» идёт в моды: список, закреплённый --pin-ready (нет файла - ни у кого)."""
    return set(READY.read_text(encoding="utf-8-sig").split()) if READY.exists() else set()


def pin_ready():
    """Закрепить голоса с «сотней», записанной и распознанной целиком: аудит, события и сборка берут один список,
    а запись остальных идёт дальше."""
    out = []
    for v in parse(more=MORE100):
        p = VOICEPACK / v["id"] / "voice.json"
        if p.exists():
            st = json.loads(p.read_text(encoding="utf-8-sig"))
            if st.get("asr_done") and len(st.get("script") or []) == len(v["lines"]):
                out.append(v["id"])
    READY.write_text("\n".join(out) + "\n", encoding="utf-8-sig")
    return out


def _read(path, by_id, only=None):
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
            cur = by_id[m.group(1)] if only is None or m.group(1) in only else None
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
            if m.group(4):
                ln["tag"] = m.group(4)
            if extra:
                ln["extra"] = True
            cur["lines"].append(ln)
    return voices


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--import", dest="src", default="", help="новая версия сценария - скопировать в docs")
    ap.add_argument("--pin-ready", action="store_true",
                    help="закрепить голоса с готовой «сотней» для сборки модов (art/sfx/voicepack/more100_ready.txt)")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if a.pin_ready:
        ids = pin_ready()
        print(f"«сотня» в моды: {len(ids)} голосов -> {READY}")
        print(" ".join(ids))
        return
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
