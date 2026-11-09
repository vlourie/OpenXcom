"""SIDE-FIRST COMBAT V0.1: the tables of the report from the json of the stats: per mission D0 / V0 / V0.1, the mean of the missions that have all three, the pairs. Director's acts with few time units. args: full_json partial_v01_json res_dir"""
import gzip
import io
import json
import sys
import zipfile
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
full = json.load(open(sys.argv[1], encoding="utf-8"))
v01 = json.load(open(sys.argv[2], encoding="utf-8"))
res = sys.argv[3]
KEYS = [("phplost", "Потеря здоровья игрока"), ("p_out", "Игрок вне строя"), ("h_out", "Враг вне строя"), ("turn", "Ходов"), ("loss_rate", "Доля поражений игрока"), ("dmg", "Урон действий врага"), ("stun", "Оглушение"), ("fdmg", "По своим, все записи"), ("h_by_own", "Своих сбито своими"), ("att", "Атак"), ("att_hit", "Атак с раной"), ("hit_share", "Доля атак с раной"), ("att_dmg_tu", "Урон атак на 100 ОВ"), ("j_conc", "Целей, раненных двумя и более за ход"), ("j_conc_down", "Из них сбито в этот ход"), ("n_throw", "Бросков"), ("n_hit", "Рукопашных"), ("n_psi", "Захватов (BA_MINDCONTROL)"), ("n_mc", "Паники (BA_PANIC)"), ("civ_by_h", "Гражданских сбито врагом"), ("seconds", "Секунд на бой"), ("sec_turn", "Секунд на ход"), ("t1_phplost", "Потеря игрока, первый ход врага")]


def f(x, d=2):
    return f"{x:.{d}f}".replace(".", ",")


for m in ("M3", "M8", "L4", "L8"):
    print(f"\n{m}")
    for k, name in KEYS:
        a, b = full["missions"][m][k]
        c = v01["missions"][m][k][1] if m in v01["missions"] else None
        print(f"| {name} | {f(a)} | {f(b)} | {f(c) if c is not None else '—'} |")
print("\nсреднее M3 и L8")
for k, name in KEYS:
    a = [full["missions"][m][k][0] for m in ("M3", "L8")]
    b = [full["missions"][m][k][1] for m in ("M3", "L8")]
    c = [v01["missions"][m][k][1] for m in ("M3", "L8")]
    print(f"| {name} | {f(sum(a) / 2)} | {f(sum(b) / 2)} | {f(sum(c) / 2)} |")
print("\nпары V0.1:", [(r["m"], r["s"], r["D"]["phplost"], r["XN"]["phplost"], r["D"]["h_out"], r["XN"]["h_out"], r["outD"], r["outXN"]) for r in v01["pairs"]])
print("пары V0 всех:", [(r["m"], r["s"], r["XN"]["phplost"], r["outXN"]) for r in full["pairs"]])
print("правило V0.1:", v01["rule"], v01["sign"], v01["outcomes"], v01["ms_max"], v01["director_s"], v01["battle_s"])
print("директор V0.1:", {k: round(v, 1) for k, v in v01["xn"].items()})

for zp, prefix, missions in ((f"{res}/res_sfH.zip", "sfH", ["M3"]), (f"{res}/res_sfI.zip", "sfI", ["L8"]), (f"{res}/res_sfF.zip", "sfF", ["M3", "L8"])):
    z = zipfile.ZipFile(zp)
    c = Counter()
    for m in missions:
        for s_ in (1, 2, 3, 4):
            for s in gzip.open(io.BytesIO(z.read(f"out/{prefix}_XN_{m}_s{s_}/openxcom.log.gz")), "rt", encoding="utf-8", errors="replace"):
                s = s.split("\t")[-1]
                if s.startswith("[AISCD] ") and '"ev":"act"' in s:
                    j = json.loads(s[8:])
                    c["acts"] += 1
                    c["acts_tu_le5"] += 1 if j["tu"] <= 5 else 0
    print(prefix, missions, dict(c))
