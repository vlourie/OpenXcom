"""Раскладка реплик сценария по событиям OXCE: выбор, движение, оружие, «отстань» (+ запас «после убийства»).

В OXCE у голоса 4 события (RuleVoiceSet: selectUnit, startMoving, selectWeapon, annoyed). Сценарий пишет
реплики карточки в постоянном порядке - он и решает (проверено по всем 157 карточкам):
  8 реплик (команда, машины, попугай): 01 выбор, 02 приказ/ход, 03-04 угроза, 05 угроза или «руки убрал»,
                                       06 после убийства, 07 «не тыкай», 08 характерная;
  6 реплик (фракции, пришельцы, нежить): 01 выбор, 02 ход, 03 угроза, 04 после убийства, 05 «не тыкай»,
                                       06 характерная;
  национальные (4 общие + 2 свои):      01 «есть/иду», 02 угроза, 03 «не тыкай», 04-06 характерные;
  киллбот V025 - по своим разделам.
Характерные идут в выбор. «После убийства» и «под огнём» движок не играет: запас, если Vitali решит
добавить события.

  py -3 tools/sfx/voicepack_events.py            -> tools/sfx/voicepack_events.tsv + сводка
  py -3 tools/sfx/voicepack_events.py --show V001,V014   -> как разложены реплики голосов
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import voice_script  # noqa: E402

OUT = Path(__file__).with_name("voicepack_events.tsv")
EVENTS = ("select", "move", "weapon", "annoyed", "kill", "hit")
WORD = {"select": "выбор", "move": "движение", "weapon": "оружие", "annoyed": "отстань", "kill": "после убийства",
        "hit": "под огнём"}

SLOTS = {
    8: {"01": "select", "02": "move", "03": "weapon", "04": "weapon", "05": "weapon", "06": "kill",
        "07": "annoyed", "08": "select"},
    6: {"01": "select", "02": "move", "03": "weapon", "04": "kill", "05": "annoyed", "06": "select"},
    "nation": {"01": "move", "02": "weapon", "03": "annoyed", "04": "select", "05": "select", "06": "select"},
}
PART_EVENT = {"Выбор бойца": "select", "Приказ и движение": "move", "Перед атакой": "weapon",
              "Повторные нажатия": "annoyed", "Под огнём": "hit", "После убийства": "kill",
              "Редкие реплики": "select"}
# пятая реплика восьмистрочной карточки: «руки убрал / не трогай» - это «отстань», а не угроза
TOUCH = re.compile(r"тыка|трога|лапа|руки|щекот|выкручива|уши|hands|touch|pok|twist|ears", re.I)
# где порядок карточки нарушен (сверено глазами)
OVERRIDE = {
    "V001": {"02": "weapon", "05": "move"},       # «Сами напросились» / «Подвинься, я с топором»
}


def classify(v, ln):
    o = OVERRIDE.get(v.get("same_as", v["id"]), {}).get(ln["n"])
    if o:
        return o, "руками"
    if ln["part"]:
        return PART_EVENT[ln["part"]], "раздел"
    # место - по строкам самой карточки, без дополнения (voice-script-extra.md)
    kind = "nation" if v["section"].startswith("Национальные") else sum(not x.get("extra") for x in v["lines"])
    ev = SLOTS[kind][ln["n"]]
    if kind == 8 and ln["n"] == "05" and TOUCH.search(ln["ru"] + " " + ln["en"]):
        return "annoyed", "место+слово"
    return ev, "место"


def build():
    return [(v, [(ln, *classify(v, ln)) for ln in v["lines"]]) for v in voice_script.parse(
        more=voice_script.MORE100, only=voice_script.pinned())]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", default="", help="голоса через запятую - показать раскладку")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    rows = build()
    if a.show:
        want = set(a.show.split(","))
        for v, evs in rows:
            if v["id"] in want:
                print(f"== {v['id']} {v['name']}")
                for ln, ev, how in evs:
                    print(f"  {ln['n']} {WORD[ev]:<15} ({how}) {ln['ru']}  //  {ln['en']}")
        return
    with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
        f.write("voice\tline\tevent\thow\tru\ten\n")
        for v, evs in rows:
            for ln, ev, how in evs:
                f.write(f"{v['id']}\t{ln['n']}\t{ev}\t{how}\t{ln['ru']}\t{ln['en']}\n")
    tot = {e: 0 for e in EVENTS}
    empty = {e: [] for e in EVENTS[:4]}
    for v, evs in rows:
        for _, ev, _ in evs:
            tot[ev] += 1
        for e in EVENTS[:4]:
            if not any(ev == e for _, ev, _ in evs):
                empty[e].append(v["id"])
    print("реплик по событиям:", ", ".join(f"{WORD[e]} {tot[e]}" for e in EVENTS))
    for e, ids in empty.items():
        print(f"нет «{WORD[e]}» ({len(ids)}):", ",".join(ids) if ids else "-")
    print("таблица:", OUT)


if __name__ == "__main__":
    main()
