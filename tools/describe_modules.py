#!/usr/bin/env python3
"""
Смысловые описания модулей локальной моделью (Ollama + Qwen3.8-27B).

    python tools/describe_modules.py --check
    python tools/describe_modules.py              только новые/изменённые
    python tools/describe_modules.py --all        переписать всё

Пишет .index/files.md: по абзацу на файл — за что отвечает, что наружу отдаёт.

ГРАНИЦА ОТВЕТСТВЕННОСТИ. Здесь живёт СМЫСЛ, а не факты. Имена функций, сигнатуры
и номера строк берутся из .index/symbols.tsv (ctags), модель их не изобретает.
Всё, что модель написала, помечено как черновик: агент вправе не верить.
"""
from __future__ import annotations

import argparse, hashlib, json, os, sys, time, urllib.request
from pathlib import Path

OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
MODEL = os.environ.get("LOCAL_MODEL", "qwen3.8:27b")
OUT = Path(".index")
CACHE = OUT / "describe_cache.json"

SYSTEM = (
    "Ты описываешь исходные файлы проекта для другого разработчика. "
    "Пиши по-русски, 2-4 предложения, по делу. Отвечай на три вопроса: "
    "за что отвечает файл; что он предоставляет наружу; с чем связан. "
    "НЕ придумывай имена функций и полей, которых нет в тексте. "
    "Не пересказывай код построчно. Без вступлений и без списков."
)


def api(path: str, payload=None, timeout=300):
    url = OLLAMA + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def check() -> int:
    try:
        tags = api("/api/tags", timeout=5)
    except Exception:
        print(f"Ollama не отвечает на {OLLAMA}")
        print("Поставить:  winget install Ollama.Ollama")
        print("Запустить:  ollama serve")
        print(f"Модель:     ollama pull {MODEL}    (~18 ГБ, 256K контекст)")
        return 1
    names = [m["name"] for m in tags.get("models", [])]
    print(f"Ollama на {OLLAMA}, моделей: {len(names)}")
    for n in names:
        print("  " + n + ("   <- используется" if n.startswith(MODEL.split(":")[0]) else ""))
    if not any(n.startswith(MODEL.split(":")[0]) for n in names):
        print(f"\nНужной модели нет. ollama pull {MODEL}")
        return 1
    return 0


def describe(text: str, path: str, symbols: str) -> str:
    prompt = (
        f"Файл: {path}\n\n"
        f"Символы, объявленные в нём (из ctags, это факты):\n{symbols or '(нет данных)'}\n\n"
        f"Исходник (возможно урезан):\n```\n{text}\n```\n"
    )
    r = api("/api/chat", {
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.2, "num_ctx": 16384},
    })
    return r["message"]["content"].strip()


def load_symbols():
    p = OUT / "symbols.tsv"
    by_file = {}
    if not p.exists():
        return by_file
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines()):
        if i == 0:
            continue
        c = line.split("\t")
        if len(c) < 4:
            continue
        by_file.setdefault(c[2], []).append(f"{c[1]} {c[0]}{c[5] if len(c) > 5 else ''}")
    return by_file


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--max-bytes", type=int, default=60000)
    ap.add_argument("--limit", type=int, default=0, help="сколько файлов максимум за прогон")
    a = ap.parse_args()

    if a.check:
        return check()
    if check() != 0:
        return 1

    files_tsv = OUT / "files.tsv"
    if not files_tsv.exists():
        sys.exit("нет .index/files.tsv — сначала python tools/index_project.py")

    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() and not a.all else {}
    symbols = load_symbols()

    paths = [l.split("\t")[0] for l in files_tsv.read_text(encoding="utf-8").splitlines()[1:] if l.strip()]
    todo = []
    for p in paths:
        f = Path(p)
        if not f.exists():
            continue
        h = hashlib.sha1(f.read_bytes()).hexdigest()[:16]
        if cache.get(p, {}).get("hash") == h:
            continue
        todo.append((p, h))
    if a.limit:
        todo = todo[: a.limit]

    if not todo:
        print("Все описания актуальны.")
    else:
        print(f"Описываю {len(todo)} файлов моделью {MODEL}. Это долго — можно оставить работать.")

    t0 = time.time()
    for i, (p, h) in enumerate(todo, 1):
        f = Path(p)
        try:
            text = f.read_text(encoding="utf-8", errors="replace")[: a.max_bytes]
            syms = "\n".join(symbols.get(p, [])[:80])
            desc = describe(text, p, syms)
            cache[p] = {"hash": h, "desc": desc, "at": time.strftime("%Y-%m-%d")}
            print(f"  [{i}/{len(todo)}] {p}")
        except Exception as e:
            print(f"  [{i}/{len(todo)}] {p} — ошибка: {e}", file=sys.stderr)
        if i % 10 == 0:
            CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")

    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")

    lines = [
        "# Описания модулей (черновик)",
        "",
        f"Сгенерировано локальной моделью {MODEL}, {time.strftime('%Y-%m-%d %H:%M')}.",
        "",
        "**Это смысл, а не факты.** Имена, сигнатуры и строки — только из "
        "`.index/symbols.tsv`. Если описание противоречит коду, прав код.",
        "",
    ]
    for p in sorted(cache):
        lines += [f"## {p}", "", cache[p]["desc"], ""]
    (OUT / "files.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Готово за {time.time()-t0:.0f} с -> .index/files.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
