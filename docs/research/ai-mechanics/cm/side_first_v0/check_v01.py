"""SIDE-FIRST COMBAT V0.1: the report's numbers against the stats and the logs. Exit 1 on a mismatch. args: report full_json partial_v01_json partial_v0_json pass_check.txt idle_repeats.txt psi_effects.txt fair_v01.txt runs_done.txt partial_dig.txt"""
import json
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
doc_path, full_p, v01_p, v0_p, pass_p, idle_p, psi_p, fair_p, runs_p, dig_p = sys.argv[1:11]
doc = open(doc_path, encoding="utf-8-sig").read()
sec = doc[doc.index("## V0.1: итоговая проверка"):doc.index("## 1. Что построено")]
full = json.load(open(full_p, encoding="utf-8"))
v01 = json.load(open(v01_p, encoding="utf-8"))
v0 = json.load(open(v0_p, encoding="utf-8"))
bad = []


def f(x, d=2):
    return f"{x:.{d}f}".replace(".", ",")


def need(s, where=sec):
    if s not in where:
        bad.append(s)


ROWS = {"phplost": "Потеря здоровья игрока", "p_out": "Игрок вне строя", "h_out": "Враг вне строя", "turn": "Ходов", "fdmg": "По своим, все записи", "h_by_own": "Своих сбито своими"}
for k, name in ROWS.items():
    first = True
    for m in ("M3", "M8", "L4", "L8"):
        a, b = full["missions"][m][k]
        c = f(v01["missions"][m][k][1]) if m in v01["missions"] else "—"
        need(f"| {name if first else ''}{' ' if first else ''}| {m} | {f(a)} | {f(b)} | {c} |")
        first = False
# the direct attacks at own side, ff_weapon.py on four battles: attack:think + attack:director
DIRECT = {"M3": (3691, 760 + 8, 1711 + 1736), "M8": (145, 125, None), "L4": (1159, 163, None), "L8": (76, 3, 0)}
first = True
for m, (a, b, c) in DIRECT.items():
    cc = f(c / 4) if c is not None else "—"
    need(f"| {'По своим, прямые атаки ' if first else ''}| {m} | {f(a / 4)} | {f(b / 4)} | {cc} |")
    first = False
for m, row in {"M3": (2, 0, 1), "M8": (0, 0, None), "L4": (0, 0, None), "L8": (4, 4, 4)}.items():
    a, b = full["missions"][m]["loss_rate"]
    assert round(a * 4) == row[0] and round(b * 4) == row[1], (m, a, b)
    if row[2] is not None:
        assert round(v01["missions"][m]["loss_rate"][1] * 4) == row[2], m
TWO = {"phplost": "Потеря здоровья игрока", "p_out": "Игрок вне строя", "h_out": "Враг вне строя", "turn": "Ходов", "dmg": "Урон действий врага", "stun": "Оглушение", "att": "Атак", "hit_share": "Доля атак с раной", "att_dmg_tu": "Урон атак на 100 ОВ", "j_conc": "Целей, раненных двумя и более за ход", "j_conc_down": "Из них сбито в этот ход", "n_throw": "Бросков", "n_hit": "Рукопашных", "civ_by_h": "Гражданских сбито врагом", "t1_phplost": "Потеря игрока, первый ход врага", "seconds": "Секунд на бой", "sec_turn": "Секунд на ход"}
for k, name in TWO.items():
    m3, l8 = full["missions"]["M3"][k], full["missions"]["L8"][k]
    c3, c8 = v01["missions"]["M3"][k][1], v01["missions"]["L8"][k][1]
    need(f"| {name} | {f((m3[0] + l8[0]) / 2)} | {f((m3[1] + l8[1]) / 2)} | {f((c3 + c8) / 2)} |")
assert f"{v01['rule']['phplost_pct']:.1f}" == "-1.4", v01["rule"]
assert f"{v01['rule']['hostile_pct']:.1f}" == "4.7", v01["rule"]
assert v01["rule"]["pairs_up"] == 3 and v01["sign"]["p="] == 1 and v01["sign"]["p-"] == 4
m3 = v01["missions"]["M3"]["phplost"]
l8 = v01["missions"]["L8"]["phplost"]
need(f"M3 {f(100 * (m3[1] / m3[0] - 1), 1).replace('-', '−')} %", doc)
need(f"L8 +{f(100 * (l8[1] / l8[0] - 1), 1)} %", doc)
need(f"**Время.** Директор {f(v01['director_s'], 1)} с из {v01['battle_s']:.0f} с боя, {f(100 * v01['director_s'] / v01['battle_s'])} %, пик {v01['ms_max']} мс")
need(f"V0 на тех же миссиях {f(100 * v0['director_s'] / v0['battle_s'])} %, пик {v0['ms_max']} мс")
x = v01["xn"]
need(f"исполнил {x['d_A_n']} атак из {round(v01['metrics']['att']['XN'] * 8)}, урон {x['d_A_dmg']}, с раной {x['d_A_hit']}. Вето {x['d_veto']}. Шагов {x['d_M'] + x['d_P']} ({x['d_M']} + {x['d_P']}), уступок линии {x['d_C']}, их выстрелов по цели {x['j_clear_fire']}")
need(f"открытой другим, {x['j_reveal_fire']}")
pairs = {(r["m"], r["s"]): (r["D"]["phplost"], r["XN"]["phplost"]) for r in v01["pairs"]}
need("M3: " + ", ".join(f"{pairs[('M3', s)][0]} → {pairs[('M3', s)][1]}" for s in (1, 2, 3, 4)))
need("L8: " + ", ".join(f"{pairs[('L8', s)][0]} → {pairs[('L8', s)][1]}" for s in (1, 2, 3, 4)))

ps = open(pass_p, encoding="utf-8").read()
rows = re.findall(r"^(\w+) (\w+) (\w+): ходов (\d+), юнит-ходов (\d+), заходов \d+, доп. заходов \d+ \(([\d.]+) на юнит-ход\), макс. (\d+); прыжков назад \d+: после выбытия (\d+) \(([\d.]+) на ход\), иначе (\d+); рост ОВ rec (\d+) dec (\d+); записей \d+, без траты ОВ \d+, из них повтор того же \d+; потрачено больше ОВ решения (\d+) \(rec.tu == exec.tu\+spent (\d+)\)", ps, re.M)
if len(rows) != 6:
    bad.append(f"pass_check rows {len(rows)}")
need("| Юнит-ходов | " + " | ".join(r[4] for r in rows) + " |")
need("| Дополнительных заходов на юнит-ход | " + " | ".join(r[5].replace(".", ",") for r in rows) + " |")
need("| Максимум заходов за ход | " + " | ".join(r[6] for r in rows) + " |")
need("| Возвратов после выбытия выбранного | " + " | ".join(r[7] for r in rows) + " |")
need("| Прочих возвратов к младшему id | " + " | ".join(r[9] for r in rows) + " |")
if any(r[10] != "0" or r[11] != "0" for r in rows):
    bad.append("tu grew")
if any(r[12] != r[13] for r in rows):
    bad.append("over does not reconcile")
over_v01 = int(rows[2][12]) + int(rows[5][12])
need(f"потрачено больше `tu` из `[AIDECIDE]`, у V0.1 {over_v01}, у D0 {int(rows[0][12]) + int(rows[3][12])}")
idle = [eval(line.split(" ", 3)[3]) for line in open(idle_p, encoding="utf-8") if line.startswith("sf")]
need("| Повторов записи без траты ОВ | " + " | ".join(str(i["rep"]) for i in idle) + " |")
if any(i["rep_hurt"] or i["rep_moved"] or i.get("rep_director") for i in idle):
    bad.append("idle repeat with effect")
need("| Самая длинная серия повторов | " + " | ".join(str(i["run_max"]) for i in idle) + " |")
if idle[2]["rep_act_10"] != 11 or idle[2]["rep_act_8"] != 6 or idle[0]["rep_act_10"] != 1:
    bad.append("idle melee and snap")

pe = open(psi_p, encoding="utf-8").read()
tot = re.findall(r"^sf\w (\w+) L8: ходов (\d+), захват (\d+), паника (\d+), всего (\d+), на ход ([\d.]+); ОВ \d+; боец у врага на конец хода (\d+); решений захваченных (\d+), .*? = ([\d.]+) %; юнит-ходов игрока (\d+): потеря морали \d+ \(([\d.]+) на юнит-ход\), мораль до 0 \d+, оглушение \+\d+ \(([\d.]+)\), раны \+\d+ \(([\d.]+)\)", pe, re.M)
if len(tot) != 3:
    bad.append(f"psi rows {len(tot)}")
need("| Захватов исполнено | " + " | ".join(t[2] for t in tot[:2]) + f" | **{tot[2][2]}** |")
need("| Паники исполнено | " + " | ".join(t[3] for t in tot) + " |")
need("| Концов хода с бойцом игрока у врага | " + " | ".join(t[6] for t in tot) + " |")
need("| Решений захваченных бойцов | " + " | ".join(t[7] for t in tot) + " |")
need("| Юнит-ходов игрока | " + " | ".join(t[9] for t in tot) + " |")
need("| Потеря морали на юнит-ход | " + " | ".join(t[10].replace(".", ",") for t in tot) + " |")
need("| Оглушение на юнит-ход | " + " | ".join(t[11].replace(".", ",") for t in tot) + " |")
need("| Раны на юнит-ход | " + " | ".join(t[12].replace(".", ",") for t in tot) + " |")
need(" → ".join(t[8].replace(".", ",") + " %" for t in tot))
need(f"{f(float(tot[2][5]))} ({int(tot[2][4])} за {tot[2][1]})")
need("**0,40 (4 за 10)**")
if float(tot[2][5]) >= 0.64:
    bad.append("L8 gate passed by numbers")

fr = open(fair_p, encoding="utf-8").read()
acts = sum(int(a) for a in re.findall(r"'act': (\d+)", fr))
over = sum(int(a) for a in re.findall(r"'attack_tu_over': (\d+)", fr))
oo = sum(int(a) for a in re.findall(r"'attack_on_out': (\d+)", fr))
need(f"`fair_check` на {acts} действиях директора дал {over + oo} отметок")
need(f"{over} `attack_tu_over`")
need(f"{oo} `attack_on_out`")
need(f"0 действий из {acts}")
n = int(open(runs_p, encoding="utf-8").read().strip())
need(f"Бюджет: {n} запусков из 58")
if n != 50:
    bad.append(f"runs {n}")
dg = open(dig_p, encoding="utf-8").read()
for v0_v in ("114 -> 30",):
    if v0_v not in dg:
        bad.append(v0_v)
print("BAD:", bad if bad else "нет")
sys.exit(1 if bad else 0)
