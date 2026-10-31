"""Проверка текста реплик до записи: ударения, «ё», длина, повторы, метка подачи (docs/research/voice-direction.md).

Fish / VoxCPM2 знак ударения не понимают - ошибки ударения лечатся только текстом. RUAccent (окружение
VoiceFactory, на процессоре) ставит «ё» и ударения; флаг ставится, если:
  omograph - смысловой омограф из HARD (замок, мука, пошли, плачу): модель озвучки выберет ударение сама -
             переписать. Прочие омографы словаря RUAccent (формы: поняла, деньги, готов) - столбец «омографы»,
             для глаза, флагом не считаются: синтез читает их по частоте верно;
  yo       - RUAccent вернул «ё», которой нет в тексте (все -> всё): дописать «ё»;
  long     - длиннее 7 слов или 45 знаков (реплика 1-3 с);
  dup      - повтор внутри голоса или с уже записанными репликами голоса;
  tag      - нет метки подачи [..].

    D:/VoiceFactory/runtime/venv/Scripts/python.exe tools/sfx/voice_text_check.py [--ids V001,V033]
-> art/sfx/voicepack/text_check.tsv + сводка. Код выхода 1, если есть флаги.
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import voice_script                              # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SCRIPT100 = ROOT / "docs/research/voice-script-100.md"
OUT = ROOT / "art/sfx/voicepack/text_check.tsv"
MORE = re.compile(r"^### (V\d{3})\+ — (.+?)\s*$")
SUB = re.compile(r"^\*\*([^*:]+)\*\*\s*$")
ROW = re.compile(r"^\| (\d{3}) \| (.+?) \| (.+?) \| (.*?) \|\s*$")
WORD = re.compile(r"[А-Яа-яЁё]+(?:-[А-Яа-яЁё]+)*")
# смысловые омографы: синтез ошибается по смыслу (за́мок/замо́к, пла́чу/плачу́, тру́сы/трусы́, це́лую/целу́ю)
HARD = set("""замок замка замки замков мука муки пошли запах стоит атлас белки плачу кружки дорога полки хлопок
орган броня брони писать кирка кирку трусы стрелки пили целую пропасть узнаю парить засыпать сорока жаркое
ирис мою рожки обороты хаос""".split())


def parse100(path=SCRIPT100):
    """{V###: [{n, part, ru, en, tag}]} из voice-script-100.md."""
    out, vid, part = {}, None, ""
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        m = MORE.match(line)
        if m:
            vid, part = m.group(1), ""
            out.setdefault(vid, [])
            continue
        m = SUB.match(line)
        if m and vid:
            part = m.group(1).strip()
            continue
        m = ROW.match(line)
        if m and vid:
            out[vid].append({"n": m.group(1), "part": part, "ru": m.group(2).strip(), "en": m.group(3).strip(),
                             "tag": m.group(4).strip()})
    return out


def norm(s):
    return re.sub(r"[^а-яёa-z ]", "", s.lower().replace("ё", "е")).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="")
    ap.add_argument("--src", nargs="*", default=[str(SCRIPT100)], help="файлы в формате voice-script-100.md")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    from ruaccent import RUAccent
    acc = RUAccent()
    acc.load(omograph_model_size="turbo3.1", use_dictionary=True, tiny_mode=False)
    omo = set(acc.omographs) | set(acc.yo_homographs)
    want = {x.strip() for x in a.ids.split(",") if x.strip()}
    old = {v["id"]: {norm(ln["ru"]) for ln in v["lines"]} for v in voice_script.parse()}
    rows, flags = [], 0
    src = {}
    for p in a.src:
        for vid, lines in parse100(p).items():
            src.setdefault(vid, []).extend(lines)
    for vid, lines in src.items():
        if want and vid not in want:
            continue
        seen = set(old.get(vid, ()))
        for ln in lines:
            f = []
            stressed = acc.process_all(ln["ru"])
            soft = []
            for w in WORD.findall(ln["ru"]):
                if w.lower() in HARD:
                    f.append("omograph:" + w)
                elif w.lower() in omo:
                    soft.append(w)
            plain = stressed.replace("+", "")
            if plain.count("ё") + plain.count("Ё") > ln["ru"].count("ё") + ln["ru"].count("Ё"):
                f.append("yo")
            if len(ln["ru"].split()) > 7 or len(ln["ru"]) > 45:
                f.append("long")
            k = norm(ln["ru"])
            if k in seen:
                f.append("dup")
            seen.add(k)
            if not re.fullmatch(r"\[[^\]]+\]", ln["tag"]):
                f.append("tag")
            flags += bool(f)
            rows.append((vid, ln["n"], ln["part"], ln["ru"], stressed, ln["tag"], ",".join(soft), ",".join(f)))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8-sig") as fh:
        fh.write("id\tn\tpart\tru\tударения\tподача\tомографы\tфлаги\n")
        for r in rows:
            fh.write("\t".join(r) + "\n")
    for r in rows:
        if r[7]:
            print(f"{r[0]} {r[1]} {r[3]} -> {r[4]}  [{r[7]}]")
    print(f"реплик {len(rows)}, с флагами {flags} -> {out}")
    sys.exit(1 if flags else 0)


if __name__ == "__main__":
    main()
