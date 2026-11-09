"""DECISION ENGINE FOUNDATION: every number of the report against the tables the scripts wrote. Prints what does not match."""
import ast
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
F = Path(__file__).parent
DOC = Path("E:/OpenXCom/docs/research/ai-mechanics/HIVE_DECISION_ENGINE_FOUNDATION.md").read_text(encoding="utf-8-sig")
al = [ast.literal_eval(x.split(" ", 1)[1]) for x in (F / "alt.txt").read_text(encoding="utf-8").splitlines()[:2]]
pl = [ast.literal_eval(x) for x in (F / "plug.txt").read_text(encoding="utf-8").splitlines()[:2]]
sw = ast.literal_eval((F / "swap.txt").read_text(encoding="utf-8").splitlines()[0])
tot = ast.literal_eval(next(x for x in (F / "all.txt").read_text(encoding="utf-8").splitlines() if x.startswith("{")))
la = {}
for x in (F / "lane.txt").read_text(encoding="utf-8").splitlines():
    m = re.match(r"   (.+) (\d+)$", x)
    if m:
        la[m.group(1)] = int(m.group(2))
named = dict(ast.literal_eval((F / "lane.txt").read_text(encoding="utf-8").split("named dead ")[1].splitlines()[0]))
at, sn = al
att = at["att"] + sn["att"]
risk = at["comrade at risk"] + sn["comrade at risk"]
dmg = at["dmg"] + sn["dmg"]
fd = at["fdmg"] + sn["fdmg"]
rd = at["dmg, comrade at risk"] + sn["dmg, comrade at risk"]
rf = at["fdmg, comrade at risk"] + sn["fdmg, comrade at risk"]
hurt = at["comrade at risk and hurt"] + sn["comrade at risk and hurt"]


def sp(n):
    return f"{n:,}".replace(",", " ")


def fr(v, d=2):
    return f"{v:.{d}f}".replace(".", ",")


def cl(key):
    a = [k for k in la if k == key]
    return la[a[0]] if a else 0


def two(a, b, tail):
    return cl(f"{a}{tail}") + cl(f"{b}{tail}")


want = {
    "units-turns": sp(tot["ut"]), "dmg": sp(tot["dmg"]), "fdmg": sp(tot["fdmg"]), "fd%": f"{round(100 * tot['fdmg'] / tot['dmg'])} %", "downed": f"выбыло {tot['fdowned']}",
    "att": sp(att), "risk": f"{sp(risk)} ({round(100 * risk / att)} %)", "hurt": f"с уроном своим {hurt}", "share": f"{sp(rf)} из {sp(fd)} ({round(100 * rf / fd)} %)",
    "risk dmg": fr(rd / risk), "risk fd": fr(rf / risk), "rest dmg": fr((dmg - rd) / (att - risk)), "rest fd": fr((fd - rf) / (att - risk)),
    "lost": f"{pl[0]['lost']} ({sp(pl[0]['lost tu'])} TU из {sp(tot['ttu'])}, {fr(100 * tot['ltu'] / tot['ttu'], 1)} %)",
    "pocket": f"у {pl[0]['pocket']}", "plugged": f"{pl[0]['plugged pocket']} случаях, {sp(pl[0]['plugged tu'])} TU ({fr(100 * pl[0]['plugged tu'] / tot['ttu'], 1)} %",
    "later": f"| {pl[1]['plug decides later or not at all']} |", "nothing": f"| {pl[1]['earlier: spent nothing']} |", "walked": f"{pl[1]['earlier: walked here']}, из них патрулём {pl[1]['walked by patrol.node']}", "fired": f"| {pl[1]['earlier: fired from here']} |",
    "B": f"в {pl[0]['B later fired']} случаях из {pl[0]['plugged pocket']}, урон {pl[0]['B later dmg']}",
    "sw att": sp(sw["attacks"]), "sw out": f"ещё {sw['attack whose target is not in the list with a line']}", "sw risk": sp(sw["attacks at risk"]), "sw n": f"{sw['attacks with an exchange']} ({fr(100 * sw['attacks with an exchange'] / sw['attacks'], 1)} %)", "sw hurt": f"| {sw['hurt']} |",
    "sw fd": f"{sw['their fdmg']} ({fr(100 * sw['their fdmg'] / tot['fdmg'], 1)} % из {sp(tot['fdmg'])})", "sw dn": f"{sw['their downed']} из {tot['fdowned']}", "sw dmg": f"| {sw['their dmg']} |",
    "sw dist": f"{sp(sw['sum dist, given up'])} → {sp(sw['sum dist, taken'])} (+{round(100 * (sw['sum dist, taken'] - sw['sum dist, given up']) / sw['sum dist, given up'])} %)",
    "per battle": fr(sw["their fdmg"] / 48, 1), "cost": f"{sp(sw['comrades, sum'])} на {sw['attacks with an exchange']}", "cost2": f"{sw['attacks in the list, sum of targets']} на {sw['attacks with an exchange']}",
    "single": f"{at['at risk, clean other target'] + sn['at risk, clean other target']} решений, {at['at risk, clean other, hurt'] + sn['at risk, clean other, hurt']} с уроном, {at['fdmg, at risk, clean other'] + sn['fdmg, at risk, clean other']} урона ({fr(100 * (at['fdmg, at risk, clean other'] + sn['fdmg, at risk, clean other']) / tot['fdmg'], 1)} %)",
    "c undecided": f"{cl('not decided yet')} | {cl('not decided yet hurt')} | {sp(cl('not decided yet fdmg'))} | {cl('not decided yet fdowned')} | {named['not decided yet']} |",
    "c stood": f"{cl('stood, decided earlier')} | {cl('stood, decided earlier hurt')} | {sp(cl('stood, decided earlier fdmg'))} | {cl('stood, decided earlier fdowned')} | {named['stood, decided earlier']} |",
    "c melee": f"{two('melee, S in place', 'melee, S came later', '')} | {two('melee, S in place', 'melee, S came later', ' hurt')} | {sp(two('melee, S in place', 'melee, S came later', ' fdmg'))} | {two('melee, S in place', 'melee, S came later', ' fdowned')} | {sum(v for k, v in named.items() if k.startswith('walked by melee'))} |",
    "c patrol": f"{two('patrol, S in place', 'patrol, S came later', '')} | {two('patrol, S in place', 'patrol, S came later', ' hurt')} | {sp(two('patrol, S in place', 'patrol, S came later', ' fdmg'))} | {two('patrol, S in place', 'patrol, S came later', ' fdowned')} | {sum(v for k, v in named.items() if k.startswith('walked by patrol'))} |",
    "c place": f"{cl('loop, S in place')} | {cl('loop, S in place hurt')} | {cl('loop, S in place fdmg')} | {cl('loop, S in place fdowned')} | {sum(v for k, v in named.items() if k.startswith('walked by') and 'S in place' in k and 'melee' not in k and 'patrol' not in k)} |",
    "c later": f"{cl('loop, S came later')} | {cl('loop, S came later hurt')} | {sp(cl('loop, S came later fdmg'))} | {cl('loop, S came later fdowned')} | {sum(v for k, v in named.items() if k.startswith('walked by') and 'S came later' in k and 'melee' not in k and 'patrol' not in k)} |",
    "reaction": f"Ещё {named['not by an attack decision of this turn (reaction, blast chain)']} погибших", "no dec": f"у {named['no decision of the killer']} нет решения",
    "named": f"погибшие (`[AICASUALTY]`, {sum(named.values())})",
}
bad = 0
for k, v in want.items():
    if v not in DOC:
        print("NOT IN THE REPORT:", k, repr(v))
        bad += 1
print("checked", len(want), "bad", bad)
