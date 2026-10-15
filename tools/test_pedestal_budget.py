"""Предохранитель пьедестала: стартовый контекст сессии Claude Code не должен разрастаться (грабли R-356).

15.10.2026 аудит кредитов показал: CLAUDE.md с импортом `@docs/RAKES.md` (576 КБ) плюс хук старта со
всеми граблями занимали 237-282 тыс. токенов при пороге сжатия около 280 тыс. - сжатие шло каждые
2-4 ответа, кэш пересоздавался целиком (docs/research/cache-resets-2026-10-15.md, раздел
«Предложение минимальной починки», пункт 1). Импорт убран, хук отдаёт индекс; этот тест не даёт
беде вернуться.

Что считается (всё, что попадает в контекст до первого вопроса):
  - CLAUDE.md в корне;
  - каждый файл, подключённый в нём как @путь (рекурсивно, как делает Claude Code: токен @путь вне
    блоков кода и вне `кода в обратных кавычках`, путь относительно подключающего файла, ~/ и
    абсолютные тоже, не глубже пяти прыжков; несуществующий файл Claude Code молча пропускает);
  - MEMORY.md из C:/Users/user/.claude/projects/E--OpenXCom/memory/ (путь выводится из корня репозитория);
  - AGENTS.md в корне;
  - additionalContext хука .claude/hooks/session-start.ps1 (запуск так же, как в settings.json:
    пустой JSON на stdin, CLAUDE_PROJECT_DIR=корень, ответ JSON, hookSpecificOutput.additionalContext).
Не считается: системный промпт Claude Code, схемы инструментов, список навыков и агентов, вывод хука
правки (до трёх правил на правку).

Падает (код 1), если какой-то @-импорт больше MAX_IMPORT_BYTES или сумма больше MAX_TOTAL_BYTES.
Сам CLAUDE.md под лимит импорта не подпадает - он не импорт. Печатает разбивку по частям.

Запуск:  PYTHONIOENCODING=utf-8 py -3.13 tools/test_pedestal_budget.py
Другой корень (проверка на копии, настоящие файлы не трогаются):
         py -3.13 tools/test_pedestal_budget.py --root <папка с CLAUDE.md и .claude/hooks/session-start.ps1>
         [--memory <путь к MEMORY.md>]     то же через PEDESTAL_ROOT и PEDESTAL_MEMORY
Хук при запуске сам обновляет .index/, если тот устарел (так же, как на старте сессии), больше ничего не пишет.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

REPO = Path(__file__).resolve().parent.parent
HOOK_REL = Path(".claude/hooks/session-start.ps1")

# КБ здесь - 1000 байт, как в отчёте о сбросах кэша (CLAUDE.md 16,5 КБ = 16519 байт).
KB = 1000
# Один @-импорт: больше - уже свалка (docs/RAKES.md был 576 КБ). Сам CLAUDE.md под лимит не подпадает.
MAX_IMPORT_BYTES = 16 * KB
# Сумма всего стартового контекста. На 15.10.2026 около 33 КБ (CLAUDE.md 16,5; MEMORY.md 8,6; AGENTS.md 4,7;
# хук 2,9); порог вдвое с запасом на естественный рост. Поднимать только осознанно, записав решение в
# docs/DECISIONS.md, а не потому, что тест покраснел.
MAX_TOTAL_BYTES = 64 * KB
# Claude Code не идёт по импортам глубже пяти прыжков.
MAX_IMPORT_DEPTH = 5
# В settings.json у хука старта timeout 120.
HOOK_TIMEOUT_S = 120


@dataclass
class Part:
    name: str
    size: int
    kind: str  # base | import | memory | agents | hook


def kb(n):
    return f"{n / KB:.1f}".replace(".", ",")


def key(p):
    return os.path.normcase(os.path.realpath(p))


def is_file(p):
    try:
        return p.is_file()
    except (OSError, ValueError):
        return False


# --- разбор @-импортов -------------------------------------------------------------------------------

# @ не после буквы/цифры/точки/слэша: адрес почты a@b.ru импортом не считается
_AT = re.compile(r"(?<![\w@./\\:-])@(\S+)")
_TRAIL = ".,;:!?)]}>'\"*"


def find_tokens(text):
    """Токены @путь из текста Markdown вне блоков кода и вне `кода в обратных кавычках`."""
    out = []
    fence = None
    for line in text.splitlines():
        m = re.match(r"^\s*(```+|~~~+)", line)
        if m:
            mark = m.group(1)[0]
            if fence is None:
                fence = mark
            elif fence == mark:
                fence = None
            continue
        if fence is not None:
            continue
        line = re.sub(r"`[^`]*`", "", line)
        for t in _AT.findall(line):
            out.append(t.rstrip(_TRAIL))
    return [t for t in out if t]


def resolve(raw, base_dir):
    try:
        if raw.startswith(("~/", "~\\")):
            return Path.home() / raw[2:]
        p = Path(raw)
        return p if p.is_absolute() else base_dir / p
    except (OSError, ValueError):
        return None


@dataclass
class Import:
    path: Path
    size: int
    depth: int
    via: Path


def collect_imports(top):
    """Рекурсивно: что подключает top строками @путь. -> (подключённые, несуществующие, глубже предела)."""
    seen = {key(top)}
    found, missing, too_deep = [], [], []

    def walk(f, depth):
        text = f.read_text(encoding="utf-8-sig", errors="replace")
        for raw in find_tokens(text):
            target = resolve(raw, f.parent)
            if target is None or not is_file(target):
                missing.append((raw, f))
                continue
            k = key(target)
            if k in seen:
                continue
            seen.add(k)
            if depth > MAX_IMPORT_DEPTH:
                too_deep.append(target)
                continue
            found.append(Import(target, target.stat().st_size, depth, f))
            walk(target, depth + 1)

    walk(top, 1)
    return found, missing, too_deep


# --- хук старта ---------------------------------------------------------------------------------------

def run_hook(root):
    """-> (байт в additionalContext, None) или (None, причина, почему измерить нельзя)."""
    hook = root / HOOK_REL
    if not is_file(hook):
        return None, f"нет файла хука {hook}"
    ps = shutil.which("powershell") or shutil.which("pwsh")
    if not ps:
        return None, "powershell не найден в PATH"
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
    try:
        r = subprocess.run([ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(hook)],
                           input=b"{}", capture_output=True, env=env, timeout=HOOK_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return None, f"хук не уложился в {HOOK_TIMEOUT_S} с"
    out = r.stdout.decode("utf-8-sig", errors="replace").strip()
    if not out:
        err = r.stderr.decode("utf-8", errors="replace").strip()[:300]
        return None, f"хук вернул пустой вывод (код {r.returncode}) {err}".strip()
    try:
        data = json.loads(out)
    except ValueError:
        try:
            data = json.loads(out.splitlines()[-1])
        except ValueError:
            return None, "вывод хука - не JSON: " + out[:200]
    try:
        ctx = data["hookSpecificOutput"]["additionalContext"]
    except (KeyError, TypeError):
        return None, "в ответе хука нет hookSpecificOutput.additionalContext"
    return len(ctx.encode("utf-8")), None


# --- сборка частей и вердикт --------------------------------------------------------------------------

def rel(p, root):
    try:
        return os.path.relpath(p, root).replace("\\", "/")
    except ValueError:
        return str(p)


def default_memory():
    mangled = re.sub(r"[^A-Za-z0-9]", "-", str(REPO))  # E:\OpenXCom -> E--OpenXCom
    return Path.home() / ".claude" / "projects" / mangled / "memory" / "MEMORY.md"


def build_parts(root, memory):
    """-> (части, проблемы-измерения, пометки)."""
    parts, problems, notes = [], [], []
    claude = root / "CLAUDE.md"
    imports = []
    if is_file(claude):
        parts.append(Part("CLAUDE.md", claude.stat().st_size, "base"))
        imports, missing, too_deep = collect_imports(claude)
        for imp in imports:
            parts.append(Part(f"@{rel(imp.path, root)}  (прыжок {imp.depth})", imp.size, "import"))
        for raw, src in missing[:5]:
            notes.append(f"@{raw} в {rel(src, root)}: файла нет, Claude Code пропускает - не считается")
        if len(missing) > 5:
            notes.append(f"... и ещё {len(missing) - 5} таких @-токенов без файла")
        for p in too_deep:
            notes.append(f"@{rel(p, root)}: глубже {MAX_IMPORT_DEPTH} прыжков, Claude Code не грузит - не считается")
    else:
        problems.append(f"нет файла {claude}")
    counted = {key(claude)} | {key(i.path) for i in imports}
    for name, path, kind in (("MEMORY.md", memory, "memory"), ("AGENTS.md", root / "AGENTS.md", "agents")):
        if not is_file(path):
            notes.append(f"{name}: файла нет ({path}) - в сумму не входит")
        elif key(path) in counted:
            notes.append(f"{name}: уже подключён через @, второй раз не считается")
        else:
            parts.append(Part(name, path.stat().st_size, kind))
    size, why = run_hook(root)
    if why:
        problems.append("хук старта не измерен: " + why)
    else:
        parts.append(Part("хук старта (additionalContext)", size, "hook"))
    return parts, problems, notes


def verdict(parts, problems):
    """-> список нарушений (пусто - всё в бюджете)."""
    fails = list(problems)
    for p in parts:
        if p.kind == "import" and p.size > MAX_IMPORT_BYTES:
            fails.append(f"{p.name}: {p.size} байт ({kb(p.size)} КБ) больше лимита импорта "
                         f"{MAX_IMPORT_BYTES} байт ({kb(MAX_IMPORT_BYTES)} КБ)")
    total = sum(p.size for p in parts)
    if total > MAX_TOTAL_BYTES:
        fails.append(f"сумма {total} байт ({kb(total)} КБ) больше лимита {MAX_TOTAL_BYTES} байт "
                     f"({kb(MAX_TOTAL_BYTES)} КБ)")
    return fails


def print_report(parts, notes):
    total = sum(p.size for p in parts)
    width = max([len(p.name) for p in parts] + [12])
    print(f"Пьедестал стартового контекста (КБ = {KB} байт)")
    print(f"  {'часть'.ljust(width)}  {'байт':>9}  {'КБ':>7}  {'доля':>5}")
    for p in parts:
        share = f"{100 * p.size / total:.0f}%" if total else "-"
        mark = "   <-- больше лимита импорта" if p.kind == "import" and p.size > MAX_IMPORT_BYTES else ""
        print(f"  {p.name.ljust(width)}  {p.size:>9}  {kb(p.size):>7}  {share:>5}{mark}")
    mark = "   <-- больше лимита суммы" if total > MAX_TOTAL_BYTES else ""
    print(f"  {'ИТОГО'.ljust(width)}  {total:>9}  {kb(total):>7}  {'':>5}"
          f"   (лимит суммы {kb(MAX_TOTAL_BYTES)} КБ, лимит импорта {kb(MAX_IMPORT_BYTES)} КБ){mark}")
    for n in notes:
        print("  примечание: " + n)


# --- самопроверка разбора (синтетическое дерево с приманками: они существуют на диске, так что любая
# ложная находка попала бы в счёт; ловит и «прочёл всё дерево», грабли R-092) ----------------------------

def selftest():
    errs = []
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "docs").mkdir()
        for name in ("a", "b", "c", "fence", "code", "mail", "bare"):
            (d / "docs" / f"{name}.md").write_text("x" * 100, encoding="utf-8-sig")
        (d / "docs" / "a.md").write_text("текст\n@c.md\n", encoding="utf-8-sig")        # относительно docs/
        (d / "docs" / "c.md").write_text("цикл @a.md\n", encoding="utf-8-sig")
        (d / "CLAUDE.md").write_text(
            "\ufeff# Тест\n"
            "@docs/a.md\n"
            "см. (@docs/b.md).\n"
            "```\n@docs/fence.md\n```\n"
            "`@docs/code.md` в обратных кавычках\n"
            "почта user@docs/mail.md не импорт\n"
            "@docs/none.md\n", encoding="utf-8")
        found, missing, _ = collect_imports(d / "CLAUDE.md")
        got = sorted(rel(i.path, d) for i in found)
        if got != ["docs/a.md", "docs/b.md", "docs/c.md"]:
            errs.append(f"разбор @ нашёл {got}, ждали a, b, c")
        if [m[0] for m in missing] != ["docs/none.md"]:
            errs.append(f"несуществующие: {[m[0] for m in missing]}")
        # цепочка из семи файлов: считаются только пять прыжков
        for i in range(1, 8):
            (d / f"n{i}.md").write_text(f"@n{i + 1}.md\n" if i < 7 else "конец\n", encoding="utf-8")
        found, _, deep = collect_imports(d / "n1.md")
        if len(found) != MAX_IMPORT_DEPTH or len(deep) != 1:
            errs.append(f"глубина: найдено {len(found)} (ждали {MAX_IMPORT_DEPTH}), глубже {len(deep)} (ждали 1)")
    big = [Part("CLAUDE.md", 1, "base"), Part("@big.md", MAX_IMPORT_BYTES + 1, "import")]
    if len(verdict(big, [])) != 1:
        errs.append("лимит импорта не сработал")
    if len(verdict([Part("x", MAX_TOTAL_BYTES + 1, "memory")], [])) != 1:
        errs.append("лимит суммы не сработал")
    if verdict([Part("x", MAX_TOTAL_BYTES - MAX_IMPORT_BYTES, "memory"),
                Part("@ok.md", MAX_IMPORT_BYTES, "import")], []) != []:
        errs.append("ровно на пороге должно проходить")
    return errs


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default="",
                    help="корень с CLAUDE.md, AGENTS.md и .claude/hooks/session-start.ps1 "
                         "(по умолчанию PEDESTAL_ROOT, иначе репозиторий)")
    ap.add_argument("--memory", default="",
                    help="путь к MEMORY.md (по умолчанию PEDESTAL_MEMORY, иначе папка памяти этого репозитория, не --root)")
    args = ap.parse_args()
    # пустая строка значит «не задано»: Path('') - это текущая папка (грабли R-092)
    root_arg = args.root.strip() or os.environ.get("PEDESTAL_ROOT", "").strip() or str(REPO)
    memory_arg = args.memory.strip() or os.environ.get("PEDESTAL_MEMORY", "").strip()
    root = Path(root_arg).resolve()
    memory = Path(memory_arg) if memory_arg else default_memory()

    errs = selftest()
    if errs:
        print("САМОПРОВЕРКА РАЗБОРА @ НЕ ПРОШЛА:")
        for e in errs:
            print("  - " + e)
        return 1

    parts, problems, notes = build_parts(root, memory)
    print_report(parts, notes)
    fails = verdict(parts, problems)
    if fails:
        print("\nПЬЕДЕСТАЛ ПРЕВЫШЕН - тест не пройден:")
        for f in fails:
            print("  - " + f)
        print("Что делать: не подключать большие файлы через @ (давать индекс и команду поиска, как хук граблей),"
              " сжать CLAUDE.md/MEMORY.md; порог поднимать только решением в docs/DECISIONS.md.")
        return 1
    print("\nOK: пьедестал в бюджете")
    return 0


if __name__ == "__main__":
    sys.exit(main())
