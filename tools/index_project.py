#!/usr/bin/env python3
"""
Карта проекта для ИИ-агентов: компактный индекс символов и файлов.

    python tools/index_project.py              пересобрать
    python tools/index_project.py --if-stale   пересобрать, только если устарел
    python tools/index_project.py --full       плюс doxygen XML (граф вызовов)

Кладёт в .index/ (в гит не идёт):
    symbols.tsv  имя | вид | файл | строка | область | сигнатура
    files.tsv    файл | строк | язык
    INDEX.md     сводка для человека и агента
    meta.json    когда собран, чем, сколько

Агенты грепают по .index/, а не читают исходники целиком. Индекс — источник
ФАКТОВ о том, где что лежит. Смысловые описания модулей — отдельно,
tools/describe_modules.py.
"""
from __future__ import annotations

import argparse, fnmatch, json, os, shutil, subprocess, sys, time
from collections import Counter
from pathlib import Path

OUT = Path(".index")
SRC_EXT = {
    ".c": "C", ".h": "C/C++ header", ".cpp": "C++", ".cc": "C++", ".cxx": "C++",
    ".hpp": "C++ header", ".cs": "C#", ".py": "Python", ".js": "JS", ".ts": "TS",
    ".lua": "Lua", ".rul": "ruleset", ".yml": "YAML", ".yaml": "YAML", ".json": "JSON",
    ".ps1": "PowerShell", ".sh": "Shell",
}
SKIP_DIRS = {".git", ".index", "build", "dist", "out", "node_modules", "__pycache__",
             ".vs", ".vscode", ".idea", "game", "assets", "venv", ".venv", "third_party",
             # каталоги сборки, данные и установленные игры: не исходники проекта
             "build-release", "obj", "deps", "libs", "bin", "user", "install",
             "Пиратки", "мурукон", "Claude outputs", "hdglobe_dl", "hdart_sheets", "art"}
# и по маске: скрытые папки (.venv-qwen21 - 729 тысяч символов чужих библиотек) и готовые
# решения конфликтов слияния (tools/merge/resolved_8.7 - копии src, символы двоились бы)
SKIP_GLOBS = [".*", "resolved_*"]


# Windows PowerShell 5.1 читает файл без BOM как cp1251 (`type INDEX.md` — мусор).
# Пишем со спецификацией, читаем utf-8-sig. Грабли R-001.
ENC_W = "utf-8-sig"
ENC_R = "utf-8-sig"


def have(tool: str) -> bool:
    return shutil.which(tool) is not None


def iter_sources(roots: list[Path]):
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not any(fnmatch.fnmatch(d, g) for g in SKIP_GLOBS)]
            for fn in filenames:
                p = Path(dirpath) / fn
                if p.suffix.lower() in SRC_EXT:
                    yield p


def newest_source_mtime(roots: list[Path]) -> float:
    return max((p.stat().st_mtime for p in iter_sources(roots)), default=0.0)


def is_stale(roots: list[Path]) -> bool:
    meta = OUT / "meta.json"
    if not meta.exists():
        return True
    try:
        built = json.loads(meta.read_text(encoding=ENC_R)).get("built_at", 0)
    except Exception:
        return True
    return newest_source_mtime(roots) > built


def run_ctags(roots: list[Path]) -> list[dict]:
    if not have("ctags"):
        return []
    excl = [f"--exclude={d}" for d in [*SKIP_DIRS, *SKIP_GLOBS]]
    cmd = ["ctags", "-R", "--output-format=json", "--fields=+nKSt", "--extras=+q",
           # данные (ключи JSON и YAML) - не символы кода
           "--languages=-JSON,-Yaml", *excl, *map(str, roots)]
    try:
        # ctags пишет UTF-8; кодировка консоли по умолчанию (cp1252) падает на кириллице в tools/
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    except Exception as e:
        print(f"ctags не отработал: {e}", file=sys.stderr)
        return []
    rows = []
    for line in res.stdout.splitlines():
        try:
            j = json.loads(line)
        except Exception:
            continue
        if j.get("_type") != "tag":
            continue
        rows.append(j)
    return rows


def write_tsv(path: Path, header: list[str], rows):
    with path.open("w", encoding=ENC_W, newline="\n") as f:
        f.write("\t".join(header) + "\n")
        for r in rows:
            f.write("\t".join(str(c).replace("\t", " ").replace("\n", " ") for c in r) + "\n")


def build(roots: list[Path], full: bool) -> int:
    t0 = time.time()
    OUT.mkdir(exist_ok=True)

    files = sorted(iter_sources(roots))
    frows = []
    total_lines = 0
    for p in files:
        try:
            n = sum(1 for _ in p.open("rb"))
        except Exception:
            n = 0
        total_lines += n
        frows.append([p.as_posix(), n, SRC_EXT.get(p.suffix.lower(), "?")])
    write_tsv(OUT / "files.tsv", ["file", "lines", "lang"], frows)

    tags = run_ctags(roots)
    srows = [[t.get("name", ""), t.get("kind", ""), t.get("path", "").replace("\\", "/"),
              t.get("line", ""), t.get("scope", ""), (t.get("signature", "") or "")]
             for t in tags]
    srows.sort(key=lambda r: (r[2], int(r[3] or 0)))
    write_tsv(OUT / "symbols.tsv", ["name", "kind", "file", "line", "scope", "signature"], srows)

    kinds = Counter(r[1] for r in srows)
    langs = Counter(r[2] for r in frows)

    doxy = False
    if full and have("doxygen") and Path("Doxyfile").exists():
        try:
            subprocess.run(["doxygen", "Doxyfile"], capture_output=True, timeout=1800)
            doxy = True
        except Exception:
            pass

    md = [
        "# Карта проекта",
        "",
        f"Собрана: {time.strftime('%Y-%m-%d %H:%M')} за {time.time()-t0:.1f} с",
        f"Файлов: {len(frows)} · строк: {total_lines} · символов: {len(srows)}",
        "",
        "## Языки",
        "",
        "| Язык | Файлов |", "|---|---|",
        *[f"| {k} | {v} |" for k, v in langs.most_common()],
        "",
        "## Символы по видам",
        "",
        "| Вид | Кол-во |", "|---|---|",
        *[f"| {k} | {v} |" for k, v in kinds.most_common(20)],
        "",
        "## Крупнейшие файлы",
        "",
        "| Файл | Строк |", "|---|---|",
        *[f"| {r[0]} | {r[1]} |" for r in sorted(frows, key=lambda r: -r[1])[:20]],
        "",
        "## Как пользоваться",
        "",
        "```",
        "# где объявлен символ",
        "grep -P '^ИмяСимвола\\t' .index/symbols.tsv",
        "# все символы файла",
        "grep -P '\\tsrc/Foo/Bar.cpp\\t' .index/symbols.tsv",
        "# кто упоминает символ (по исходникам)",
        "grep -rn 'ИмяСимвола' src/",
        "```",
        "",
        "Индекс — источник фактов о расположении. Смысловые описания модулей — .index/files.md.",
    ]
    if not have("ctags"):
        md.insert(4, "\n**ctags не установлен — символов нет.** `winget install UniversalCtags.Ctags`\n")
    (OUT / "INDEX.md").write_text("\n".join(md) + "\n", encoding=ENC_W)

    (OUT / "meta.json").write_text(json.dumps({
        "built_at": time.time(),
        "built_human": time.strftime("%Y-%m-%d %H:%M:%S"),
        "files": len(frows), "lines": total_lines, "symbols": len(srows),
        "ctags": have("ctags"), "clangd": have("clangd"), "doxygen_run": doxy,
        "seconds": round(time.time() - t0, 2),
    }, ensure_ascii=False, indent=2), encoding=ENC_W)

    print(f"Индекс собран: {len(frows)} файлов, {len(srows)} символов, {time.time()-t0:.1f} с -> .index/")
    if not have("ctags"):
        print("ВНИМАНИЕ: ctags не установлен, символы не собраны. tools/setup_workstation.ps1")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Индекс проекта для агентов")
    ap.add_argument("--if-stale", action="store_true", help="пересобрать, только если устарел")
    ap.add_argument("--full", action="store_true", help="плюс doxygen (нужен Doxyfile)")
    ap.add_argument("--quiet", action="store_true")
    # движок, инструменты и портал: без tools/ и portal/ агенты читали их файлы целиком (аудит 26.09)
    ap.add_argument("--root", nargs="+", default=["src", "tools", "portal"])
    a = ap.parse_args()

    roots = [Path(r) for r in a.root if Path(r).exists()] or [Path(".")]

    if a.if_stale and not is_stale(roots):
        if not a.quiet:
            print("Индекс свежий, пересборка не нужна.")
        return 0
    return build(roots, a.full)


if __name__ == "__main__":
    sys.exit(main())
