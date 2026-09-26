"""Проверка списка tools/gpu_scripts.txt: каждый скрипт, который грузит модель на видеокарту, в нём есть.

Список читают gpu-guard (не даёт запустить мимо очереди) и gpuq.py (видит чужой запуск). Скрипт,
которого в списке нет, запускается мимо очереди и делит карту с идущим заданием (R-073).

Модель грузит:
  - питон, который сам импортирует torch / diffusers / diffsynth / transformers или ходит в Ollama;
  - питон-скрипт, который импортирует такой модуль (ab_sdxl.py -> gen_hd, run2.py -> map_paint);
  - .sh, который запускает такой питон.
Лишнее в списке тоже ошибка: имя, которого нет на диске, или скрипт без модели (score_batch.py был
в списке и останавливал безобидный подсчёт).

Запуск: python tools/test_gpu_scripts.py   (код 0 - всё верно)
"""
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
LIST = os.path.join(ROOT, "tools", "gpu_scripts.txt")
WHERE = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "art", "maps", "paint")]

MODEL = re.compile(r"^\s*(import|from)\s+(torch|diffusers|diffsynth|transformers)\b|11434|/api/generate", re.M)
LOADER = re.compile(r"(?<!def )\b(load_pipeline|load_pipe|build_pipe)\s*\(|\b_PIPE\b")
# признаки есть, а модель не грузит
NOT_GPU = {
    "gpuq.py": "сама очередь: адрес Ollama знает, чтобы выгрузить её между заданиями",
    "test_gpu_scripts.py": "эта проверка",
}
# в списке по делу, хотя признаков выше в файле нет
KEEP = {
    "gen_all.ps1": "запускает gen_hd.py",
    "train_lora.ps1": "запускает обучение LoRA",
    "train.py": "обучение LoRA, лежит вне tools (E:/train)",
    "run_batch.py": "держит gen_hd в памяти (gen_hd._PIPE)",
    "keep_batch.py": "гоняет gen_lora_batch.py",
    "gen_lora_batch.py": "DiffSynth через gen_lora_test",
    "gen_cursor.py": "Qwen-Image через gen_fire",
    "gen_fire.py": "Qwen-Image",
    "gen_tile.py": "модель через paint3",
    "make_ref.py": "модель через gen_hd",
    "map_paint.py": "модель через paint3",
    "describe_modules.py": "Ollama",
}


def read(path):
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def files():
    for top in WHERE:
        for dirpath, dirnames, names in os.walk(top):
            dirnames[:] = [d for d in dirnames if not d.startswith(".venv") and d not in ("__pycache__", "attic")]
            for n in names:
                if n.endswith((".py", ".sh", ".ps1")):
                    yield n, os.path.join(dirpath, n)


def main():
    listed = [l.strip() for l in read(LIST).splitlines() if l.strip() and not l.strip().startswith("#")]
    found = {}
    for name, path in files():
        found.setdefault(name, path)
    direct = {os.path.splitext(n)[0] for n, p in found.items()
              if n.endswith(".py") and n not in NOT_GPU and (MODEL.search(read(p)) or LOADER.search(read(p)))}
    model = {n for n in found if os.path.splitext(n)[0] in direct}
    # питон, который зовёт main() или загрузчик модуля с моделью (константы вроде gen_hd.SUBJECTS - не в счёт)
    engines = direct | {os.path.splitext(n)[0] for n in listed if n.endswith(".py")}
    for n, p in found.items():
        if n.endswith(".py") and n not in model and n not in NOT_GPU and not n.startswith("test_"):
            text = read(p)
            for m in engines:
                for alias in re.findall(r"^\s*import\s+%s(?:\s+as\s+(\w+))?" % re.escape(m), text, re.M):
                    if re.search(r"\b%s\.(main|load_pipeline|load_pipe|build_pipe)\s*\(" % re.escape(alias or m), text):
                        model.add(n)
                if re.search(r"^\s*from\s+%s\s+import\s+.*\b(main|load_pipeline|load_pipe|build_pipe)\b" % re.escape(m), text, re.M):
                    model.add(n)
    # .sh, который запускает питон с моделью
    for n, p in found.items():
        if n.endswith(".sh"):
            text = read(p)
            if any(re.search(r"[\s/]%s\b" % re.escape(m), text) for m in model if m.endswith(".py")):
                model.add(n)
    model -= {n for n in model if n.startswith("test_")}

    bad = 0
    for n in sorted(model):
        if n not in listed:
            bad += 1
            print(f"ОШИБКА нет в списке: {n}  ({os.path.relpath(found[n], ROOT)})")
    for n in listed:
        if n not in found and n not in KEEP:
            bad += 1
            print(f"ОШИБКА в списке, но на диске нет: {n}")
        elif n not in model and n not in KEEP:
            bad += 1
            print(f"ОШИБКА в списке, но модель не грузит: {n}  (если грузит - причину в KEEP)")
    print(f"скриптов с моделью: {len(model)}, в списке: {len(listed)}")
    print("всё верно" if bad == 0 else f"ошибок: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
