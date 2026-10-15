#!/usr/bin/env python3
"""Второе мнение: отдать работу на проверку Codex (ChatGPT) и получить замечания файлом.

Codex запускается в песочнице «только чтение»: он читает дерево и критикует, правит
Claude. Хуки проекта (editq, gpuq, game-guard) на Codex не действуют, поэтому запреты
повторены в AGENTS.md и в самом запросе.

    py -3 tools/gpt_check.py diff src/Engine/HdUi.cpp            # незакоммиченные правки файлов
    py -3 tools/gpt_check.py commit a90ff6f05                     # коммит
    py -3 tools/gpt_check.py file tools/hdart/model_lock.py      # файлы как есть
    py -3 tools/gpt_check.py text plan.md                        # ответ или план: сверить с кодом
    py -3 tools/gpt_check.py reply <session> answer.md           # ответить на замечания в той же беседе

Общие ключи: --ask "на что смотреть", --effort low|medium|high|xhigh, --model, --timeout МИН,
--dry-run (показать запрос и команду, Codex не звать).

Результат - .gptcheck/<время>-<режим>.md (последнее сообщение Codex), рядом .log с ходом работы.
В шапке результата номер беседы - его берёт reply.
"""
import argparse
import datetime
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / ".gptcheck"
ENC_W = "utf-8-sig"
ENC_R = "utf-8-sig"

RULES = """Ты второй проверяющий в проекте OXCE-HD. Работу делал Claude Code, твоя задача - найти в ней ошибки.
Только чтение: ничего не правь, не трогай индекс гита, не собирай, не запускай игру и ничего, что грузит видеокарту.
Правила проекта и твоей роли - AGENTS.md и CLAUDE.md в корне, прочитай их до проверки."""

ANSWER = """Формат ответа (по-русски):
1. Замечания от тяжёлых к лёгким. У каждого: файл:строка, что не так, конкретный сценарий, при котором это проявится, чем подтверждено (что ты прочитал или запустил).
2. Что проверил и ошибок не нашёл.
3. Что проверить не смог и что для этого надо запустить.
Ошибок нет - так и скажи. Замечаний ради числа не придумывай, диф не пересказывай, не хвали."""


def git(*args):
    r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True)
    if r.returncode:
        raise SystemExit("git %s: %s" % (" ".join(args), r.stderr.decode("utf-8", "replace").strip()))
    return r.stdout.decode("utf-8", "replace")


def changed(paths):
    """(изменённые, новые) файлы рабочего дерева; -z - чтобы кириллица в именах не экранировалась."""
    out = git("status", "--porcelain", "-z", "--untracked-files=all", "--", *paths)
    tracked, fresh = [], []
    items = out.split("\0")
    i = 0
    while i < len(items):
        it = items[i]
        i += 1
        if len(it) < 4:
            continue
        code, name = it[:2], it[3:]
        if code[0] in "RC":
            i += 1  # у переименования следом идёт прежнее имя
        (fresh if code == "??" else tracked).append(name)
    return tracked, fresh


def task_diff(a):
    if not a.target:
        raise SystemExit("diff: назови файлы или папки - в дереве работают несколько сессий, "
                         "проверять чужие правки заодно незачем")
    tracked, fresh = changed(a.target)
    if not tracked and not fresh:
        raise SystemExit("diff: в названных путях нет незакоммиченных правок")
    lines = ["Проверь незакоммиченные правки рабочего дерева. Другие изменённые файлы дерева - чужая работа, их не трогай."]
    if tracked:
        lines.append("Изменённые файлы (смотри `git diff HEAD -- <файл>` и сам файл вокруг правки):")
        lines += ["  " + n for n in tracked]
    if fresh:
        lines.append("Новые файлы, в гите их ещё нет (читай целиком):")
        lines += ["  " + n for n in fresh]
    return "\n".join(lines)


def task_commit(a):
    if not a.target:
        raise SystemExit("commit: назови коммит")
    lines = ["Проверь коммиты (смотри `git show <коммит>` и файлы вокруг правки):"]
    for sha in a.target:
        lines.append("  " + git("log", "-1", "--format=%h %s", sha).strip())
    return "\n".join(lines)


def task_file(a):
    if not a.target:
        raise SystemExit("file: назови файлы")
    miss = [t for t in a.target if not (ROOT / t).exists()]
    if miss:
        raise SystemExit("file: нет файла " + ", ".join(miss))
    return "Проверь файлы в их нынешнем виде:\n" + "\n".join("  " + t for t in a.target)


def task_text(a):
    if len(a.target) != 1:
        raise SystemExit("text: назови один файл с текстом")
    body = Path(a.target[0]).read_text(encoding=ENC_R)
    return ("Ниже ответ или план Claude. Сверь каждое утверждение о коде, данных и поведении игры с деревом: "
            "что подтверждается, что нет, что упущено.\n\n<текст>\n" + body.strip() + "\n</текст>")


def task_reply(a):
    if len(a.target) != 2:
        raise SystemExit("reply: <номер беседы> <файл с ответом>")
    body = Path(a.target[1]).read_text(encoding=ENC_R)
    return ("Ниже ответ Claude на твои замечания. По каждому пункту: согласен или нет и почему, "
            "с проверкой по коду. Где возражение не подтверждается - настаивай и покажи строку. "
            "Правила прежние: только чтение.\n\n<ответ>\n" + body.strip() + "\n</ответ>")


TASKS = {"diff": task_diff, "commit": task_commit, "file": task_file, "text": task_text, "reply": task_reply}


def build_prompt(a):
    task = TASKS[a.mode](a)
    if a.mode == "reply":
        return task + "\n"
    parts = [RULES, task]
    if a.ask:
        parts.append("На что смотреть в первую очередь: " + a.ask)
    parts.append(ANSWER)
    return "\n\n".join(parts) + "\n"


def build_cmd(a, codex, out):
    cmd = [codex, "exec"]
    if a.mode == "reply":
        # у resume нет ключа --sandbox и -C: песочница задаётся настройкой, папка - cwd запуска
        cmd += ["resume", a.target[0], "-c", "sandbox_mode=read-only"]
    else:
        cmd += ["--sandbox", "read-only", "-C", str(ROOT), "--color", "never"]
    if a.effort:
        cmd += ["-c", "model_reasoning_effort=" + a.effort]
    if a.model:
        cmd += ["-m", a.model]
    cmd += ["-o", str(out), "-"]
    return cmd


def run(cmd, prompt, log, timeout):
    """Codex пишет ход работы в stdout и stderr; печатаем его и кладём в журнал, оттуда же номер беседы."""
    p = subprocess.Popen(cmd, cwd=str(ROOT), stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def feed():
        try:
            p.stdin.write(prompt.encode("utf-8"))
            p.stdin.close()
        except OSError:
            pass

    threading.Thread(target=feed, daemon=True).start()
    timer = threading.Timer(timeout * 60, p.kill)
    timer.start()
    session = None
    try:
        with open(log, "w", encoding=ENC_W) as f:
            for raw in p.stdout:
                line = raw.decode("utf-8", "replace").rstrip("\r\n")
                f.write(line + "\n")
                f.flush()
                print(line, flush=True)
                m = re.search(r"session id:\s*([0-9a-f-]{36})", line, re.I)
                if m and not session:
                    session = m.group(1)
        code = p.wait()
    finally:
        timer.cancel()
    return code, session


def main():
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Проверка работы вторым мнением (Codex, только чтение)")
    ap.add_argument("mode", choices=sorted(TASKS))
    ap.add_argument("target", nargs="*", help="файлы, коммиты или <беседа> <файл> - по режиму")
    ap.add_argument("--ask", default="", help="на что смотреть в первую очередь")
    ap.add_argument("--effort", choices=["low", "medium", "high", "xhigh"],
                    help="глубина рассуждения; без ключа - как в ~/.codex/config.toml")
    ap.add_argument("--model", help="модель; без ключа - как в ~/.codex/config.toml")
    ap.add_argument("--timeout", type=int, default=40, help="минут до остановки (40)")
    ap.add_argument("--dry-run", action="store_true", help="показать запрос и команду, Codex не звать")
    a = ap.parse_args()

    prompt = build_prompt(a)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = OUT_DIR / ("%s-%s.md" % (stamp, a.mode))
    log = out.with_suffix(".log")
    codex = shutil.which("codex")
    cmd = build_cmd(a, codex or "codex", out)
    if a.dry_run:
        print(prompt)
        print("команда: " + " ".join(cmd))
        return 0
    if not codex:
        raise SystemExit("codex не найден в PATH: npm install -g @openai/codex, затем codex login")

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / (stamp + "-" + a.mode + ".prompt.txt")).write_text(prompt, encoding=ENC_W)
    started = datetime.datetime.now()
    code, session = run(cmd, prompt, log, a.timeout)
    took = (datetime.datetime.now() - started).total_seconds()
    if a.mode == "reply":
        session = a.target[0]

    if not out.exists() or not out.read_bytes().strip():
        print("\ngpt_check: ответа нет (код %s), ход работы - %s" % (code, log))
        return code or 1
    body = out.read_text(encoding=ENC_R)
    head = "<!-- gpt_check %s | %s | беседа %s | %.0f с | код %s -->\n\n" % (
        a.mode, " ".join(a.target) if a.mode != "text" else a.target[0], session or "?", took, code)
    out.write_text(head + body.strip() + "\n", encoding=ENC_W)
    print("\ngpt_check: %s (%.0f с, беседа %s)" % (out, took, session or "?"))
    return code


if __name__ == "__main__":
    sys.exit(main())
