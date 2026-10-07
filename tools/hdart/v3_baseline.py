r"""Замок production baseline V3 (DECISIONS 07.10): хэши всего кода цепочки, замка модели и опорных данных.

V3 заморожен целиком - опознание и маршрутизация, арбитры, V7, RESTORE, STRICT, пересмотр опознания, THIRD,
final_select. Следующая партия идёт тем же кодом; правка любого файла цепочки - только с новым решением.

Состав находится сам: от входов цепочки (ENTRY) - импорты модулей из tools/hdart и tools, затем имена *.py этих
папок, упомянутые в коде строкой (скрипты, которые цепочка зовёт отдельным процессом, в том числе через gpuq).

    py -3.13 tools/hdart/v3_baseline.py freeze     пишет замок (только если его ещё нет), файл только для чтения
    py -3.13 tools/hdart/v3_baseline.py check      код 0 - всё как в замке; 1 - список изменённых и пропавших
                                                   (разница только в концах строк LF/CRLF - не изменение)
    py -3.13 tools/hdart/v3_baseline.py list       состав без записи

Новый скрипт следующей партии (V4 и дальше) зовёт check перед build и перед каждым запуском модели.
"""
import argparse
import ast
import hashlib
import json
import os
import re
import stat
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
ENC = "utf-8-sig"
LOCK = os.path.join("art", "objects", "generation", "v3_baseline.lock.json")
ENTRY = ["tools/hdart/prod_two_pass_v3.py", "tools/hdart/identity_auto.py", "tools/hdart/visual_judge.py",
         "tools/hdart/final_select.py", "tools/hdart/prod2_final.py"]
DATA = ["art/models/qwen21_turbo_rgba.lock.json"]
DIRS = ["tools/hdart", "tools"]
PY_REF = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\.py\b")


def rel(p):
    return os.path.relpath(p, ROOT).replace(os.sep, "/")


def find_module(name):
    for d in DIRS:
        p = os.path.join(ROOT, d, name + ".py")
        if os.path.isfile(p):
            return p
    return None


def refs(path):
    """Импорты и имена *.py в строках кода - не в справке (docstring) и не в комментариях; тесты не берутся."""
    with open(path, encoding=ENC) as f:
        tree = ast.parse(f.read())
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docs.add(id(first.value))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.add(node.module.split(".")[0])
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
            names.update(n for n in PY_REF.findall(node.value) if not n.startswith("test_"))
    return names


def members():
    todo = [os.path.join(ROOT, p) for p in ENTRY]
    seen = set()
    while todo:
        p = os.path.normpath(todo.pop())
        if p in seen:
            continue
        seen.add(p)
        for n in refs(p):
            q = find_module(n)
            if q and os.path.normpath(q) not in seen:
                todo.append(q)
    files = sorted(rel(p) for p in seen)
    if os.path.normpath(os.path.abspath(__file__)) in seen:
        files.remove(rel(os.path.abspath(__file__)))
    return files + [p for p in DATA if os.path.isfile(os.path.join(ROOT, p))]


def sha(p):
    with open(os.path.join(ROOT, p), "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def eol_shas(p):
    """sha256 файла в LF и в CRLF. Git с autocrlf выкладывает файл не теми концами строк, что в замке (на диске
    при заморозке - смесь: 108 в LF, 15 в CRLF); содержимое при этом то же, а хэш байтов другой."""
    with open(os.path.join(ROOT, p), "rb") as f:
        lf = f.read().replace(b"\r\n", b"\n")
    return {hashlib.sha256(lf).hexdigest(), hashlib.sha256(lf.replace(b"\n", b"\r\n")).hexdigest()}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["freeze", "check", "list"])
    a = ap.parse_args()
    lock = os.path.join(ROOT, LOCK)
    if a.cmd == "list":
        for p in members():
            print(p)
        return 0
    if a.cmd == "freeze":
        if os.path.exists(lock):
            raise SystemExit("замок уже есть: %s - заморозка не переписывается" % LOCK)
        files = {p: sha(p) for p in members()}
        with open(lock, "w", encoding=ENC, newline="\n") as f:
            json.dump({"baseline": "PROD_TWO_PASS_V3", "frozen": time.strftime("%Y-%m-%d %H:%M"),
                       "decision": "DECISIONS 2026-10-07: V3 production baseline, заморожен целиком",
                       "entry": ENTRY, "files": files}, f, ensure_ascii=False, indent=1)
        os.chmod(lock, stat.S_IREAD)
        print("замок %s: %d файлов" % (LOCK, len(files)))
        return 0
    if not os.path.exists(lock):
        raise SystemExit("замка нет: %s" % LOCK)
    with open(lock, encoding=ENC) as f:
        files = json.load(f)["files"]
    bad, eol = [], 0
    for p, h in files.items():
        if not os.path.isfile(os.path.join(ROOT, p)):
            bad.append("нет      " + p)
        elif sha(p) != h:
            if h in eol_shas(p):
                eol += 1
            else:
                bad.append("изменён  " + p)
    new = sorted(set(members()) - set(files))
    for p in new:
        bad.append("новый в цепочке  " + p)
    if bad:
        print("V3 baseline НАРУШЕН (%d):" % len(bad))
        for b in bad:
            print("  " + b)
        return 1
    print("V3 baseline цел: %d файлов как в замке%s" % (
        len(files), "" if not eol else " (у %d отличаются только концы строк - checkout git)" % eol))
    return 0


if __name__ == "__main__":
    sys.exit(main())
