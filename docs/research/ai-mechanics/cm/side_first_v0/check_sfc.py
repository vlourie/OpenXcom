"""SIDE-FIRST COMBAT: the report's numbers against the outputs of the scripts and the logs; exit 1 on any mismatch. args: sfc dir, report"""
import gzip
import io
import re
import sys
import zipfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
D = Path(sys.argv[1])
rep = Path(sys.argv[2]).read_text(encoding="utf-8-sig")
T = {n: (D / f"{n}.txt").read_text(encoding="utf-8", errors="replace") for n in ("final", "dig", "first_cause", "fair", "fair_sum", "ff_weapon", "runs_done")}
checks = []


def ru(x):
    return x.replace("-", "−").replace(".", ",") if x[0] in "+-" else x.replace(".", ",")


def rows():
    """every table row of final.txt: its D, XN, difference and interval must stand in the report"""
    want = {
        "1 здоровье, потерянное игроком": "Здоровье, потерянное игроком",
        "1 бойцов игрока вне строя": "Бойцов игрока вне строя",
        "1 урон действий врага": "Урон действий врага",
        "1 оглушение от действий врага": "Оглушение",
        "2 врагов вне строя": "Врагов вне строя",
        "3 урон по своим от действий врага": "Урон по своим, все записи",
        "3 своих сбито своими  ": "Своих сбито своими",
        "4 атак исполнено": "Атак исполнено",
        "4 доля атак с раной": "Доля атак с раной",
        "4 урон атак на 100 ОВ атак": "Урон атак на 100 ОВ атак",
        "4 урон всех действий на 100 ОВ": "Урон всех действий на 100 ОВ",
        "6 целей, раненных двумя и более за ход": "Цели, раненные двумя и более за ход",
        "6 из них сбито в этот ход": "Из них сбито в этот ход",
        "7 гражданских сбито врагом": "Гражданских сбито врагом",
        "5 ходов в бою": "Ходов в бою",
        "сп. бросков": "Бросков",
        "сп. рукопашных": "Рукопашных",
        "сп. пси-атак": "Пси-атак",
        "сп. захватов": "Захватов",
        "8 секунд на бой": "Секунд на бой",
        "8 секунд на ход": "Секунд на ход",
    }
    pat = re.compile(r"\s+(-?[\d.]+)\s+(-?[\d.]+)\s+([+-][\d.]+)\s+\[([+-][\d.]+), ([+-][\d.]+)\]")
    for key, title in want.items():
        line = next((s for s in T["final"].splitlines() if s.startswith(key.rstrip()) and (key.endswith("  ") is False or "в свой ход" not in s)), None)
        m = pat.search(line or "")
        if not m:
            checks.append((f"row {key}", False))
            continue
        a, b, d, lo, hi = m.groups()
        cell = f"| {title} | {ru(a)} | {ru(b)} | {ru(d)} [{ru(lo)}; {ru(hi)}] |"
        checks.append((f"table: {cell}", cell in rep))


def has(name, s, *subs):
    for x in subs:
        checks.append((f"{name}: {x}", x in T[s]))


def text(*subs):
    for x in subs:
        checks.append((f"report: {x}", x in rep))


rows()
# by mission
for m, line in (("M3", ("phplost 840->548", "игрок вне строя 6.8->4.8", "враг вне строя 55.8->60.2", "ходов 21.8->17.5", "урон по своим 1435->406", "атак 180->151", "с раной 43->55")),
                ("M8", ("phplost 80->60", "игрок вне строя 0.2->0.2", "враг вне строя 37.0->37.2", "ходов 7.0->6.2", "урон по своим 84->175", "атак 36->18", "с раной 4->2")),
                ("L4", ("phplost 316->529", "игрок вне строя 2.0->3.5", "враг вне строя 36.0->36.0", "ходов 9.2->6.2", "урон по своим 302->41", "атак 51->36", "с раной 9->12")),
                ("L8", ("phplost 764->835", "игрок вне строя 7.8->8.0", "враг вне строя 8.0->5.2", "ходов 5.5->4.0", "урон по своим 46->39", "атак 62->65", "с раной 14->16", "пси 2.0->0.5", "захват 5.0->1.0"))):
    src = next(s for s in T["final"].splitlines() if s.startswith(f" {m}: phplost"))
    for x in line:
        checks.append((f"{m}: {x}", x in src))
text("| M3 террор | 840 → 548 | 6,8 → 4,8 | 55,8 → 60,2 | 21,8 → 17,5 | 1435 → 406 | 180 → 151 | 43 → 55 |",
     "| M8 вилла | 80 → 60 | 0,2 → 0,2 | 37,0 → 37,2 | 7,0 → 6,2 | 84 → 175 | 36 → 18 | 4 → 2 |",
     "| L4 база | 316 → 529 | 2,0 → 3,5 | 36,0 → 36,0 | 9,2 → 6,2 | 302 → 41 | 51 → 36 | 9 → 12 |",
     "| L8 корабль | 764 → 835 | 7,8 → 8,0 | 8,0 → 5,2 | 5,5 → 4,0 | 46 → 39 | 62 → 65 | 14 → 16 |",
     "пси 2,0 → 0,5, захват 5,0 → 1,0")
# the rule
has("rule", "final", "правило: phplost -1.4 % (нужно +10 %), миссий с ростом 2/4 (нужно 3), пар с ростом 7/16 (нужно 10), потери врага +1.5 %")
has("signs", "final", "знаки phplost: {'m-': 2, 'm+': 2, 'p-': 9, 'p+': 7}", "исходы D {'win': 10, 'loss': 6} XN {'win': 12, 'loss': 4}")
has("losses on M3", "final", "M3 s2:   916->539", "win", "M3 s3:   916->549")
checks.append(("M3 s2 loss->win", re.search(r"M3 s2:.*loss->win", T["final"]) is not None))
checks.append(("M3 s3 loss->win", re.search(r"M3 s3:.*loss->win", T["final"]) is not None))
checks.append(("only two outcome flips", len(re.findall(r"loss->win|win->loss", T["final"])) == 2))
text("−1,4 %", "2 из 4", "7 из 16", "+1,5 %", "3,54 %", "| 7 | Победа врага, боёв из 16 | 6 | 4 |")
# time
has("time", "final", "время директора 37.9 с из 1071 с боя = 3.54 %", "макс. мс директора за ход: 2077")
text("37,9 с из 1071 с", "2077 мс")
# first turn and first cause
has("t1", "final", "Х1 здоровье игрока, потерянное в первый ход врага", "120.81", "137.38")
has("t1 signs", "dig", "знаки: {'-': 9, '+': 5, '=': 2}", "L8 s1: -5 -> 503")
has("first", "first_cause", "первое действие директора по парам: {'act:A': 13, 'act:M': 3}")
prefix = [int(x) for x in re.findall(r"общий префикс (\d+) строк", T["first_cause"])]
checks.append((f"16 prefixes {min(prefix)}..{max(prefix)}", len(prefix) == 16 and min(prefix) == 144 and max(prefix) == 301))
text("144–301 строк", "120,81 → 137,38", "5 выше, 9 ниже, 2 равно", "−5 → 503", "13 раз атака, 3 раза ходьба")
# director totals
dirl = next(s for s in T["final"].splitlines() if s.startswith("директор, всего"))
for k, v in (("d_A_eff", "20325.56"), ("d_A_dmg", "12023"), ("d_A_n", "944"), ("d_A_hit", "306"), ("d_veto", "407"), ("d_C", "14"), ("j_clear_fire", "15"), ("j_conc", "45"), ("j_conc_down", "23"), ("j_reveal_fire", "126"), ("d_walk_lost", "2681"), ("d_walk_down", "20"), ("d_special", "44")):
    checks.append((f"director {k} {v}", re.search(rf"'{k}': {re.escape(v)}", dirl) is not None))
text("20 325,6", "12 023", "944 атаках", "попаданий 306", "407 отклонённых", "14 раз на 16 боёв", "15 выстрелов", "2,50 → 2,81", "1,25 → 1,44", "126", "2681 здоровья и 20 выбывших")
# who chose the attacks and aimed friendly fire
fw = {}
for s in T["ff_weapon"].splitlines():
    m = re.match(r"(\w+) (D|XN): всего (\d+); (\{.*?\}); выстрелов (\{.*?\});", s)
    if m:
        fw[(m[1], m[2])] = (int(m[3]), eval(m[4]), eval(m[5]))
ms = ("M3", "M8", "L4", "L8")
aim = {a: sum(v for m in ms for k, v in fw[(m, a)][1].items() if k.startswith("attack:")) for a in ("D", "XN")}
direc = sum(fw[(m, "XN")][1].get("attack:director", 0) for m in ms)
shots_d = sum(fw[(m, "XN")][2].get("director", 0) for m in ms)
shots_all = sum(sum(fw[(m, "XN")][2].values()) for m in ms)
checks.append((f"aimed friendly per battle {aim['D'] / 16:.2f} {aim['XN'] / 16:.2f}", f"{aim['D'] / 16:.2f}" == "316.94" and f"{aim['XN'] / 16:.2f}" == "66.19"))
checks.append((f"aimed friendly {aim['XN']} of them director {direc}", aim["XN"] == 1059 and direc == 1051))
checks.append((f"attacks by director {shots_d} of {shots_all}", shots_d == 945 and shots_all == 998))
checks.append(("M8 act 0 298", fw[("M8", "XN")][1].get("other act 0") == 298))
text("945 из 998", "316,94 → 66,19", "1059 единиц", "1051", "298 единиц")
has("walk tu", "final", "6265.75", "4845.69")
text("6265,75 → 4845,69")
# legality
fs = T["fair_sum"]
for k, v in (("act", 1936), ("attack_tu_over", 10), ("walk_tu_over", 1), ("attack_on_out", 2), ("act_without_result", 1), ("walk", 946), ("walk_stopped_short", 320), ("walk_not_moved", 59)):
    checks.append((f"fair {k} {v}", re.search(rf"'{k}': {v}\b", fs) is not None))
has("BAD", "fair", "BAD 13")
text("1936 действиях", "13 отметок", "10 `attack_tu_over`", "1 `walk_tu_over`", "2 `attack_on_out`", "320 из 946", "59 не сдвинулись")
# chrysalids and rates
text("16 → 8, 33 → 32, 24 → 12, 24 → 16", "11 → 3", "133 + 25 → 196 + 36", "73 + 9 → 31 + 13", "139,0 → 208,7", "34,69 врага вне строя за 8,50 хода против 34,19 за 10,88")
has("dig M3", "dig", "('h', 'STR_CHRYSSALID_TERRORIST', 'AUX_CHRYSSALID_WEAPON', 'dead'), 11)", "('h', 'STR_CHRYSSALID_TERRORIST', 'AUX_CHRYSSALID_WEAPON', 'dead'), 3)", "(('p', 'player', 'dead'), 133)", "(('p', 'player', 'stun'), 25)", "(('h', 'player', 'dead'), 73)", "(('h', 'player', 'stun'), 9)", "(('p', 'player', 'dead'), 196)", "(('p', 'player', 'stun'), 36)", "(('h', 'player', 'dead'), 31)", "(('h', 'player', 'stun'), 13)", "phplost 3057 (139.0 за ход)", "phplost 3339 (208.7 за ход)")
# budget
has("budget", "runs_done", "40")
text("5 разработочных, 32 серии, 2 сверки, 1 V0.1, всего 40 из 40", "161 с", "3551 строка")
# the V0.1 battle and M3 s1 from the raw logs


def result(zp, label):
    z = zipfile.ZipFile(D / "res" / zp)
    ls = gzip.open(io.BytesIO(z.read(f"out/{label}/openxcom.log.gz")), "rt", encoding="utf-8", errors="replace").read().splitlines()
    return next(s.split("\t")[-1] for s in ls if "[AIRESULT]" in s)


v = result("res_sfV.zip", "sfV_XN_M3_s1")
for x in ("turn=28", "player=8", "pdead=7"):
    checks.append((f"V0.1 {x}", x in v))
d_ = result("res_sfF.zip", "sfF_D_M3_s1")
n_ = result("res_sfF.zip", "sfF_XN_M3_s1")
checks.append(("D M3 s1 turn=21 pdead=6", "turn=21" in d_ and "pdead=6" in d_))
checks.append(("frozen M3 s1 turn=16 pdead=5", "turn=16" in n_ and "pdead=5" in n_))
has("M3 s1", "final", "M3 s1:   808->688", "своим 1695->232")
text("| Потеря здоровья игрока | 808 | 688 | 861 |", "| Бойцов игрока погибло | 6 | 5 | 7 |", "| Урон по своим, все записи | 1695 | 232 | 582 |", "| Ходов | 21 | 16 | 28 |", "| Решения хризалид, первый ход | 16 | 8 | 16 |", "| Решения силакоидов, первый ход | 7 | 4 | 8 |")
checks.append(("v01 hash mention", "f853ff2a" in rep and "fa7ea1c4" in rep and "0ff1e0f7" in rep))

bad = [c for c, ok in checks if not ok]
print(f"checks {len(checks)}, bad {len(bad)}")
for c in bad:
    print("BAD:", c)
sys.exit(1 if bad else 0)
