"""Грабли R-137: каждая метка [AI...] движка обязана быть в ai_probe.TAGS, иначе ai_probe.run выбросит её строки из лога
и серия ai_arena молча останется без трассы. Метки, которые в TAGS не входили и на 22.10.2026 так и живут, - в OUTSIDE;
новая метка в src/ без записи в TAGS роняет тест. Запуск: py -3.13 tools/test_ai_tags.py"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import ai_probe  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# были вне TAGS до проверки (22.10.2026): трассы для локального лога, не для арены
OUTSIDE = {"[AIAMBN]", "[AIAMB]", "[AIBHIT]", "[AIBLAST]", "[AIBLOCKSTEP]", "[AIEFF]", "[AIESC]", "[AIREUSE]"}

found = set()
for p in (ROOT / "src").rglob("*.cpp"):
    found |= set(re.findall(r'"(\[AI[A-Z0-9]+\])', p.read_text(encoding="utf-8", errors="replace")))
missing = sorted(found - set(ai_probe.TAGS) - OUTSIDE)
if missing:
    print("метки движка не в ai_probe.TAGS (R-137):", ", ".join(missing))
    sys.exit(1)
print(f"ok: {len(found)} меток движка, в TAGS {len(found & set(ai_probe.TAGS))}, вне по списку {len(found & OUTSIDE)}")
