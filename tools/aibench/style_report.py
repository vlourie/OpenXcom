# -*- coding: utf-8 -*-
"""Похож ли спарринг-партнёр стенда на живого игрока.

На арене сторона игрока играется автобоем (R-031). Пока непонятно, насколько
этот автобой похож на того, против кого ИИ будет играть в жизни, любой вывод
серии повисает в воздухе - это ровно грабли R-024, замер не на том случае.

Скрипт кладёт рядом два столбца: как воюет живой игрок (по дневникам его
кампании, tools/save_profile.py) и как воюет автобой (по выбытиям и геометрии
серии). Числа считаны по-разному, и это указано у каждой строки честно.

Запуск:
    py -3 tools\\aibench\\style_report.py logs\\style_pz_deaths.csv
        [--states logs\\style_pz_states.csv] [--rows logs\\style_pz.csv]
"""
import argparse, csv, io, os

ENC = "utf-8-sig"

# Числа живого игрока: py -3 tools\save_profile.py, срез «последние 500 боёв»,
# сохранение NoCodexCatZ.sav от 20.09.2026. Разбор - docs/research/player-profile.md
HUMAN = {
    "melee": 53.3,      # доля добиваний оружием ближе трёх клеток
    "onfoe": 16.0,      # доля добиваний на ходу противника (стена отстрела)
    "stun": 18.2,       # доля взятых живьём
    "len_med": 5,       # ходов между первым и последним убийством, медиана
    "len_p90": 26,
}

FACTION_PLAYER, FACTION_HOSTILE = 0, 1


def read(path):
    if not path or not os.path.exists(path):
        return []
    with io.open(path, encoding=ENC, newline="") as f:
        return list(csv.DictReader(f))


def med(values):
    v = sorted(values)
    return v[len(v) // 2] if v else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("deaths", help="CSV выбытий из run_series.py --deaths")
    ap.add_argument("--states", default="", help="CSV геометрии из --states")
    ap.add_argument("--rows", default="", help="основной CSV серии")
    ap.add_argument("--near", type=float, default=1.5,
                    help="расстояние, которое считаем «вплотную» (клеток)")
    a = ap.parse_args()

    deaths = read(a.deaths)
    if not deaths:
        raise SystemExit("нет выбытий: %s" % a.deaths)
    states = read(a.states)
    rows = read(a.rows)

    arms = sorted({d["arm"] for d in deaths})
    print("выбытий в файле: %d, вариантов: %s" % (len(deaths), ", ".join(arms)))

    for arm in arms:
        dd = [d for d in deaths if d["arm"] == arm]
        ai = [d for d in dd if int(d["fac"]) == FACTION_HOSTILE]
        pl = [d for d in dd if int(d["fac"]) == FACTION_PLAYER]
        if not ai:
            continue
        n = float(len(ai))

        # на чьём ходу выбыл юнит ИИ: onSide - сторона, чей слепок показал пропажу
        on_self = sum(1 for d in ai if int(d["onSide"]) == FACTION_HOSTILE)

        # вплотную: считаем только там, где расстояние вообще известно
        known = [float(d["dist"]) for d in ai if float(d["dist"]) >= 0]
        near = sum(1 for x in known if x <= a.near)
        far8 = sum(1 for x in known if x > 8)

        # длина боя по выбытиям
        by_battle = {}
        for d in ai:
            by_battle.setdefault(d["battle"], []).append(int(d["turn"]))
        spans = sorted(max(t) - min(t) for t in by_battle.values())

        print("")
        print("=== вариант «%s»: выбытий ИИ %d, выбытий игрока %d ===" % (arm, len(ai), len(pl)))
        print("")
        print("  %-46s %14s %14s" % ("", "живой игрок", "автобой"))
        print("  %-46s %13.1f%% %13.1f%%"
              % ("добито на ходу ИИ (стена отстрела)", HUMAN["onfoe"], 100 * on_self / n))
        if known:
            print("  %-46s %13.1f%% %13.1f%%"
                  % ("вплотную (у него по оружию, тут по клеткам)",
                     HUMAN["melee"], 100.0 * near / len(known)))
            print("  %-46s %14s %13.1f%%"
                  % ("добито дальше восьми клеток", "нет в дневнике", 100.0 * far8 / len(known)))
            print("  %-46s %14s %14.1f"
                  % ("медиана расстояния в момент гибели", "нет в дневнике", med(known)))
        if spans:
            print("  %-46s %14d %14d"
                  % ("ходов от первого выбытия до последнего", HUMAN["len_med"], med(spans)))
            print("  %-46s %14d %14d"
                  % ("то же, 90-й процентиль", HUMAN["len_p90"],
                     spans[int(len(spans) * 0.9)] if len(spans) > 1 else spans[0]))

        st = [s for s in states if s["arm"] == arm]
        if st:
            print("  %-46s %14s %14.1f"
                  % ("разброс отряда игрока, клеток", "нет в дневнике",
                     med([float(s["plSpread"]) for s in st])))
            print("  %-46s %14s %14.1f"
                  % ("разброс отряда ИИ, клеток", "-",
                     med([float(s["spread"]) for s in st])))
        rr = [r for r in rows if r["arm"] == arm and r.get("outcome") == "done"]
        if rr:
            print("  %-46s %14s %14.1f"
                  % ("ходов на бой всего", "нет в дневнике",
                     sum(int(r["turns"]) for r in rr) / float(len(rr))))
            stun = sum(int(r["alienStunned"]) for r in rr)
            dead = sum(int(r["alienDead"]) for r in rr)
            if stun + dead:
                print("  %-46s %13.1f%% %13.1f%%"
                      % ("взято живьём", HUMAN["stun"], 100.0 * stun / (stun + dead)))

    print("")
    print("Что с чем сравнивается. «На ходу ИИ» - величина одна и та же с обеих")
    print("сторон и сравнима прямо. «Вплотную» у живого игрока считается по типу")
    print("оружия (дальность <= 3 по рулсету), на стенде - по расстоянию до")
    print("ближайшего бойца в момент гибели: это разные способы мерить одно и то")
    print("же, и расхождение в пару процентов ни о чём не говорит, а в разы -")
    print("говорит. Строки «нет в дневнике» сравнивать не с чем: сохранение")
    print("кампании не хранит ни позиций, ни расстояний.")


if __name__ == "__main__":
    main()
