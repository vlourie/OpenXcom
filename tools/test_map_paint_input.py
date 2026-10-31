"""Проверка входа модели в tools/hdart/map_paint.py (грабли R-004).

Модель получает только гладкое увеличение. Фильтр перед ней (nearest, xBRZ) оставляет пятна и
лесенки оригинала, и модель рисует их как содержание: прогон 7 амбара дал пол из клякс вместо досок.
Тест проверяет две вещи: --pre отказывается запускаться ещё до загрузки модели, и в Brush.paint
нет ни nearest, ни xBRZ.
Запуск: python tools/test_map_paint_input.py   (код 0 - всё верно)
"""
import inspect
import os
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SCRIPT = os.path.join(ROOT, "tools", "hdart", "map_paint.py")
VENV = os.path.join(ROOT, "tools", "hdart", ".venv", "Scripts", "python.exe")
PY = VENV if os.path.exists(VENV) else sys.executable

bad = 0

# 1. --pre отказывается сразу: без модели это секунды, с моделью - полминуты
t = time.time()
r = subprocess.run([PY, SCRIPT, "--terrain", "CULTA_UBER", "--block", "CULTAFARM01", "--mode", "regions",
                    "--pre", "xbrz"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                   env=dict(os.environ, PYTHONIOENCODING="utf-8"), cwd=ROOT)
el = time.time() - t
out = r.stdout + r.stderr
if r.returncode == 0 or "R-004" not in out:
    print("ОШИБКА: --pre xbrz не остановлен (код %d)\n%s" % (r.returncode, out[-600:]))
    bad += 1
elif "Loading pipeline" in out or el > 20:
    print("ОШИБКА: --pre остановлен только после загрузки модели (%.0f с)" % el)
    bad += 1
else:
    print("ok  --pre xbrz остановлен за %.1f с" % el)

# 2. в самой кисти нет фильтров перед моделью
sys.path[:0] = [os.path.join(ROOT, "tools", "hdart"), os.path.join(ROOT, "tools")]
try:
    import map_paint
    src = inspect.getsource(map_paint.Brush.paint)
except Exception as e:  # noqa: BLE001 - нет numpy/PIL в этом питоне: проверяем текстом файла
    print("  (модуль не импортирован: %s - проверка по тексту файла)" % e)
    with open(SCRIPT, encoding="utf-8-sig") as f:
        text = f.read()
    a = text.index("    def paint(self, rgba, g, prompt, seed):")
    src = text[a:text.index("\ndef ", a)]
for word in ("xbrz", "NEAREST"):
    if any(word in line.split("#")[0] for line in src.splitlines()):
        print("ОШИБКА: в Brush.paint есть %s" % word)
        bad += 1
    else:
        print("ok  в Brush.paint нет %s" % word)

print("итог:", "всё верно" if not bad else "ошибок %d" % bad)
sys.exit(1 if bad else 0)
