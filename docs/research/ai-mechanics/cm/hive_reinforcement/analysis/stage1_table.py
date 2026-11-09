"""Stage 1's table of all REINFORCE assignments, by the nine points of the GO, from assignments.tsv and members.tsv; to STAGE1_ASSIGNMENTS.md (with BOM). Read only."""
import ast
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
A = list(csv.DictReader(open(HERE / "assignments.tsv", encoding="utf-8-sig"), delimiter="\t"))
M = list(csv.DictReader(open(HERE / "members.tsv", encoding="utf-8-sig"), delimiter="\t"))
by = defaultdict(list)
for r in M:
    by[(r["run"], r["squad"], r["turn"])].append(r)
out = [
    "# REINFORCE: все назначения журналов CC по девяти пунктам",
    "",
    "Составлено `ri/stage1_table.py` по `cc8` (M6 s1), `cc5` (M6 s2), `cc6` (M3 s1), `cc7` (загрузка M3 s1, ходы после сейва). Прогон `cc1` шёл до правки кода CC и в свод не входит.",
    "Скрытых данных нет: здесь только своя сторона и контакт, который сторона видит в этот ход. `lof` из журнала кандидатов в вывод о пригодности не входит.",
    "Огневая позиция — возможность по линии на момент плана, не гарантия (R-635 не задет: линия считается только по клетке с реальным юнитом).",
    "",
    "Колонки: 1 — бойцов с приказом; 2 — оружие; 3 — выстрел по TU и патронам (сколько); 4 — способны стрелять вообще, рукопашные не считаются; 5 — огневая позиция: на месте + с узла; 6 — ход до позиции; 7 — стояли на прошлом ходу / решений в режиме 3 на этом ходу; 8 — какая задача оставлена; 9 — атаки по контакту за назначение (прочие), первый ход атаки от назначения.",
    "",
    "| Бой | Подр. | Ход | Контакт | Дист. | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | Потери | Конец |",
    "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
]
for a in A:
    if a["run"].startswith("cc1_"):
        continue
    ms = by[(a["run"], a["squad"], a["from"])]
    ip = sum(r["kind"] == "in_place" for r in ms)
    fi = sum(r["kind"] == "fire" for r in ms)
    ap = sum(r["kind"] == "approach" for r in ms)
    no = sum(r["kind"] == "no_node" for r in ms)
    shots = sum(int(r["shot"]) > 0 for r in ms)
    fits = sum(int(r["shot"]) > 0 and int(r["shot"]) <= int(r["tu"]) for r in ms)
    stood = sum(r["prev_fate"] == "stand" for r in ms)
    m3 = sum("3" in r["modes"].split("/") for r in ms)
    turns = "0" if ip else "1" if fi else ("нет пути к линии: подход %d, узла нет %d" % (ap, no))
    task = "поиск, цели ещё нет" if a["objective_left"] == "-" else "контакт " + a["objective_left"] if a["why"].startswith("contact_not") else "поиск " + a["objective_left"]
    weapons = a["weapons"].replace(",", ", ").replace("AUX_", "")
    why = "автосмена" if a["why"].startswith("contact_not") else "выбор"
    nolog = f"+{no}?" if no else ""  # an order with no node writes no shot cost
    out.append(f"| {a['run'][:6]} | {a['squad']} | {a['from']}–{a['to']} ({why}) | {a['contact']} | {a['dist']} | {len(ms)} | {weapons} | {fits}{nolog} | {shots}{nolog} | {ip}+{fi} | {turns} | {stood}/{m3} | {task} | {a['atk_contact']} ({a['atk_other']}), {a['first_atk_after']} | {a['lost']} | {a['end']} |")
(HERE / "STAGE1_ASSIGNMENTS.md").write_text("\n".join(out) + "\n", encoding="utf-8-sig")
print(len(out) - 10, "rows")
