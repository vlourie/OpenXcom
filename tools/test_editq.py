#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка очереди правок игры tools/editq.py на временном git-репозитории.

Сборка и выпуск подменены (EDITQ_BUILD_CMD, EDITQ_RELEASE_CMD), хуки зовутся так же, как их
зовёт Claude Code: JSON события на stdin. Проверяется:
  - первая сессия занимает очередь, вторая получает отказ на правку и на сборку;
  - git add -A / git commit -a отклоняются, git add по имени и -m "... -a ..." - нет;
  - напоминания PostToolUse и Stop приходят по одному разу;
  - done коммитит только файлы своей сессии и передаёт очередь следующему;
  - упавшая сборка оставляет очередь за сессией и не коммитит;
  - после последнего done выпуск запускается сам и его правки коммитятся;
  - незакоммиченный файл игры не даёт начать выпуск.

    py -3.13 tools/test_editq.py
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="editq_test_")
REPO = os.path.join(TMP, "repo")
REL_SCRIPT = os.path.join(TMP, "fake_release.py")
ENV = dict(os.environ, EDITQ_REPO=REPO, EDITQ_HOME=os.path.join(TMP, "q"),
           EDITQ_RELEASE_DELAY="1", EDITQ_BUILD_CMD="exit 0",
           EDITQ_RELEASE_CMD=f'"{sys.executable}" "{REL_SCRIPT}"', PYTHONIOENCODING="utf-8")
for k in ("CLAUDE_CODE_SESSION_ID",):
    ENV.pop(k, None)
fails = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        fails.append(what)


def run(args, stdin=None, env=None):
    return subprocess.run([sys.executable, os.path.join(HERE, "editq.py")] + args, input=stdin,
                          env=env or ENV, capture_output=True, text=True, encoding="utf-8")


def hook(kind, sid, tool, **ti):
    ev = {"session_id": sid, "tool_name": tool, "tool_input": ti, "hook_event_name": kind}
    if "stop_hook_active" in ti:
        ev = {"session_id": sid, "stop_hook_active": ti["stop_hook_active"]}
    r = run(["hook", kind], stdin=json.dumps(ev, ensure_ascii=False))
    return json.loads(r.stdout) if r.stdout.strip() else None


def denied(res):
    return bool(res) and res["hookSpecificOutput"]["permissionDecision"] == "deny"


def cli(sid, *args, env=None):
    return run(list(args) + ["--session", sid], env=env)


def git(*a):
    return subprocess.run(["git", "-C", REPO] + list(a), capture_output=True, text=True,
                          encoding="utf-8").stdout


def write(rel, text):
    p = os.path.join(REPO, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with io.open(p, "w", encoding="utf-8") as f:
        f.write(text)


def state():
    with io.open(os.path.join(TMP, "q", "state.json"), encoding="utf-8-sig") as f:
        return json.load(f)


def main():
    sys.stdout.reconfigure(encoding="utf-8")         # вывод в файл - иначе cp1252 (R-001)
    os.makedirs(REPO)
    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    write("CHANGELOG.md", "## [Не выпущено]\n")
    write("src/a.cpp", "a\n")
    git("add", "--", "CHANGELOG.md", "src/a.cpp")
    git("commit", "-qm", "init")
    with io.open(REL_SCRIPT, "w", encoding="utf-8") as f:
        f.write("import os\nr=os.environ['EDITQ_REPO']\n"
                "open(os.path.join(r,'CHANGELOG.md'),'a',encoding='utf-8').write('## 2026.01.01\\n')\n"
                "os.makedirs(os.path.join(r,'Выпуск','notes'),exist_ok=True)\n"
                "open(os.path.join(r,'Выпуск','notes','2026.01.01.ru.txt'),'w',encoding='utf-8').write('x')\n")

    a_cpp = os.path.join(REPO, "src", "a.cpp")
    check(hook("pre", "A", "Edit", file_path=a_cpp) is None, "A занимает свободную очередь")
    check(hook("pre", "A", "Write", file_path=os.path.join(REPO, "docs", "x.md")) is None,
          "не файл игры - без очереди")
    check(denied(hook("pre", "B", "Edit", file_path=os.path.join(REPO, "src", "b.cpp"))),
          "B получает отказ на правку src")
    check(denied(hook("pre", "B", "Bash", command="cd build-release && ninja")), "B: ninja отклонён")
    check(hook("pre", "B", "Bash", command="grep -n ninja CLAUDE.md") is None, "grep ninja - не сборка")
    check(hook("pre", "A", "Bash", command="ninja -C build-release") is None, "держателю сборка можно")
    # R-158: копия скрипта сборки, поиск ninja в PATH и сборка черновика вне дерева - не сборка дерева
    check(hook("pre", "B", "Bash", command="cp tools/build/build.ps1 /e/tmp/tree/tools/build/build.ps1") is None,
          "cp build.ps1 - не сборка")
    check(hook("pre", "B", "Bash", command="command -v cmake ninja c++") is None, "command -v ninja - не сборка")
    check(hook("pre", "B", "Bash", command="ninja -C E:/tmp/scratch/build > n.log") is None,
          "ninja -C вне дерева - не сборка")
    check(hook("pre", "B", "Bash", command="cmake --build /e/tmp/scratch/build") is None,
          "cmake --build вне дерева - не сборка")
    check(denied(hook("pre", "B", "Bash", command="ninja -C " + os.path.join(REPO, "build-release"))),
          "ninja -C в дереве (полный путь) - сборка")
    check(denied(hook("pre", "B", "Bash", command="cp a b && ninja -C E:/tmp/x && ninja")),
          "ninja без папки после черновика - сборка")
    check(denied(hook("pre", "C", "Bash", command="git add -A && git commit -m x")), "git add -A отклонён")
    check(denied(hook("pre", "C", "Bash", command="git commit -am 'x'")), "git commit -am отклонён")
    check(hook("pre", "C", "Bash", command="git add -A -- tools/x.py") is None,
          "git add -A -- <путь> ограничен путём - можно")
    check(denied(hook("pre", "C", "Bash", command="git add -A -- .")), "git add -A -- . отклонён")
    check(hook("pre", "C", "Bash", command="git commit -q -F - <<'EOF'\nтекст: git add -A и commit -a\nEOF\n"
                                           "git log -1") is None, "git add -A в теле heredoc - не команда")
    check(denied(hook("pre", "C", "Bash", command="cat <<EOF > f\nx\nEOF\ngit add .")),
          "git add . после heredoc отклонён")
    check(hook("pre", "C", "Bash", command='git add -- docs/a.md && git commit -m "fix -a flag"') is None,
          "git add по имени и -m с -a внутри - можно")

    p1 = hook("post", "A", "Edit", file_path=a_cpp)
    check(bool(p1) and "#1" in p1["hookSpecificOutput"]["additionalContext"], "A: напоминание о done")
    check(hook("post", "A", "Edit", file_path=a_cpp) is None, "напоминание одно")
    s1 = hook("stop", "A", None, stop_hook_active=False)
    check(bool(s1) and s1.get("decision") == "block", "Stop держателя: одно напоминание")
    check(hook("stop", "A", None, stop_hook_active=False) is None, "второй Stop пропускается")
    check(hook("stop", "B", None, stop_hook_active=False) is None, "Stop не держателя - тихо")

    write("src/a.cpp", "a2\n")
    write("docs/x.md", "чужое\n")
    bad = dict(ENV, EDITQ_BUILD_CMD="exit 1")
    r = cli("A", "done", "-m", "hdui: a", env=bad)
    check(r.returncode != 0 and state()["q"][0]["st"] == "hold", "упавшая сборка: очередь у A, коммита нет")
    check("hdui: a" not in git("log", "--format=%s"), "после упавшей сборки коммита нет")

    r = cli("A", "done", "-m", "hdui: a")
    check(r.returncode == 0, "A done: " + (r.stderr.strip() or "прошёл"))
    files = git("show", "--name-only", "--format=", "HEAD").split()
    check(files == ["src/a.cpp"], f"в коммите только файл A: {files}")
    st = state()
    check(st["q"] and st["q"][0]["sid"] == "B" and st["q"][0]["st"] == "hold", "очередь перешла к B")
    check(st["rel"]["st"] != "pending", "пока B держит, выпуска нет")

    check(hook("pre", "B", "Edit", file_path=os.path.join(REPO, "src", "b.cpp")) is None, "B правит")
    write("src/b.cpp", "b\n")
    r = cli("B", "done", "-m", "hdui: b")
    check(r.returncode == 0 and "выпуск" in r.stdout, "B done - выпуск запланирован")
    for _ in range(60):
        if state()["rel"]["st"] in ("done", "failed", "blocked"):
            break
        time.sleep(0.5)
    st = state()
    check(st["rel"]["st"] == "done" and st["rel"].get("id") == "2026.01.01",
          f"выпуск прошёл: {st['rel']}")
    log = git("log", "--format=%s")
    check("release: выпуск 2026.01.01" in log, "правки выпуска закоммичены")
    check("docs/x.md" in git("status", "--porcelain", "-uall"), "чужой не-игровой файл не тронут")

    write("src/c.cpp", "грязь\n")
    run(["release", "now"])
    for _ in range(40):
        if state()["rel"]["st"] == "blocked":
            break
        time.sleep(0.5)
    check(state()["rel"]["st"] == "blocked", "грязный файл игры не пускает выпуск")

    # пауза и столкновение файлов
    hook("pre", "C", "Edit", file_path=os.path.join(REPO, "src", "c.cpp"))
    cli("C", "pause", "жду ответа")
    check(hook("pre", "D", "Edit", file_path=os.path.join(REPO, "src", "c.cpp")) is None,
          "после паузы C очередь свободна для D")
    r = cli("D", "done", "-m", "x")
    check(r.returncode != 0 and "другая сессия" in (r.stdout + r.stderr), "done не забирает файл C на паузе")

    shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{'ВСЁ ПРОШЛО' if not fails else f'УПАЛО {len(fails)}'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
