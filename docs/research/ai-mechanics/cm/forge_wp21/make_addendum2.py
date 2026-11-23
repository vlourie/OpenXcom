"""AI FORGE WP2.1: the addendum's second part, before the final OFF; the runner's hash as it now stands."""
import hashlib
from pathlib import Path

F = Path(__file__).resolve().parent
text = """
## Разрешение на седьмой бой

GO Vitali 06.11, FINAL OFF CONTROL: один дополнительный запуск сверх 6, разовое исключение из-за ошибки маршрутизации `XO`, итого не больше 7. Других запусков нет.

До запуска проверено на самой rabota: файл exe и его SHA256, путь в `env_FX.txt`, единственность имени `YO`, что у плеча нет флагов сверх `COMMON_D0`, сценарий в `scen.tsv`, лимит ходов, отсутствие `OXCE*` в переменных машины и пользователя (`preflight_off.py`, `preflight_off2.py`). Во время боя у системы запрашивается путь и хэш запущенного процесса (`OFF_process.txt`).

У OFF нет строк монитора, поэтому цепочка, TU, RNG и состояние сверяются по строкам движка: `[AIDECIDE]` несёт `tu`, `act`, `hu`, `hi`, `ho`, `hou`, `hm`, `hr`, `hr0`, `ha0`, `ha` на каждом решении, `[AIREC]`, `[AIEXEC]`, `[AIAFTER]` и остальные — как записал движок. Сравнения: архивный D0, A1, C1. Нормализация прежняя: `[AIRESULT] ms=`, `[AIREUSE] fallback_us=`.

Совпал: WP2.1 PASS для контролируемого исполнения одного альтернативного действия. Разошёлся: BLOCKED с первой существенной разницей. В обоих случаях без исправлений, пересборок и новых прогонов.
"""
with open(F / "WP2_1_PLAN_ADDENDUM.md", "a", encoding="utf-8") as f:
    f.write(text)
h = hashlib.sha256((F / "AIForgeCounterfactualRunner.py").read_bytes()).hexdigest()
with open(F / "FROZEN.txt", "a", encoding="utf-8") as f:
    f.write(f"runner_final_off={h}\n")
print(h)
