"""AI FORGE WP2.1: the addendum to the plan after the stray run; the ledger's line says what it was; its files out of the results; the hash of the runner as it now stands."""
import hashlib
from pathlib import Path

F = Path(__file__).resolve().parent
text = """# AI FORGE WP2.1 — дополнение к плану

Записано после одного ошибочного прогона, до всех остальных. Сам план не меняется, ниже только отклонения от него.

## Что случилось

Первый прогон (id OFF, 06.11, 22:02) ушёл не на FX. Имя плеча `XO` уже было занято старым плечом `("env_SD.txt", [], COMMON_D0)`, патч `run_cm.py` увидел имя и пропустил себя (R-773, повтор). Runner сверял только хэш файла в папке FX, а не то, на какой exe указывает плечо, поэтому в журнал записался хэш FX, хотя бой шёл на exe SD. Для WP2.1 этот бой ничего не показывает, в сравнения не входит. Файлы лежат в `stray/`.

## Что меняется

- Плечи переименованы: `YO`, `YA`, `YB`, `YC`, состав тот же. Runner теперь падает, если имя занято, и перед каждым прогоном проверяет, что плечо указывает на `env_FX.txt`, а `run_cm.py` на rabota тот же. Exe и монитор не менялись, SHA256 FX тот же.
- Бюджет считается вместе с этим боем: 1 израсходован, осталось 5. Лимит сам не повышаю.
- Порядок: A1, A2, B1, B2, C1. Настоящий OFF на FX, то есть седьмой бой, запускается только с разрешения Vitali; без него условие про OFF остаётся непроверенным, и в итоге об этом написано прямо. Первая ступень «OFF отличается от D0» снята из runner; строки движка A1 и C1 всё так же сверяются с архивным D0.
"""
(F / "WP2_1_PLAN_ADDENDUM.md").write_text(text, encoding="utf-8-sig")
lines = (F / "ledger.tsv").read_text(encoding="utf-8").splitlines()
assert len(lines) == 1 and lines[0].startswith("OFF\t")
parts = lines[0].split("\t")
parts[0] = "STRAY"
parts[2] = "not_FX_arm_XO_env_SD"
parts[5] = "a stray run: the arm name XO was taken, see WP2_1_PLAN_ADDENDUM.md; counted in the budget"
(F / "ledger.tsv").write_text("\t".join(parts) + "\n", encoding="utf-8")
(F / "stray").mkdir(exist_ok=True)
for name in ("res_fxOFF.zip", "run_fxOFF.txt"):
    (F / "res" / name).rename(F / "stray" / name)
h = hashlib.sha256((F / "AIForgeCounterfactualRunner.py").read_bytes()).hexdigest()
with open(F / "FROZEN.txt", "a", encoding="utf-8") as f:
    f.write(f"runner_after_addendum={h}\n")
print(h)
