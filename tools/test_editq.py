#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка очереди правок игры tools/editq.py на временном git-репозитории.

Сборка и выпуск подменены (EDITQ_BUILD_CMD, EDITQ_RELEASE_CMD), хуки зовутся так же, как их
зовёт Claude Code: JSON события на stdin. Проверяется:
  - первая сессия занимает очередь, вторая получает отказ на правку и на сборку;
  - git add -A / git commit -a отклоняются, git add по имени и -m "... -a ..." - нет;
  - напоминания PostToolUse и Stop приходят по одному разу;
  - done коммитит только файлы своей сессии и передаёт очередь следующему;
  - R-108: файл игры, изменённый скриптом мимо списка сессии, - done отказывает; с --add -
    собирает и коммитит, с --drop - оставляет в дереве, с --force - коммитит без него;
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


def hook(kind, sid, tool, agent=None, env=None, **ti):
    ev = {"session_id": sid, "tool_name": tool, "tool_input": ti, "hook_event_name": kind}
    if "stop_hook_active" in ti:
        ev = {"session_id": sid, "stop_hook_active": ti["stop_hook_active"]}
    if agent:
        ev["agent_id"] = agent
    r = run(["hook", kind], stdin=json.dumps(ev, ensure_ascii=False), env=env)
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
    write("src/a.h", "header\n")
    git("add", "--", "CHANGELOG.md", "src/a.cpp", "src/a.h")
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
    # R-158, 22.10: ninja -t compdb в дереве взял билет и отложил выпуск
    check(hook("pre", "B", "Bash", command="cd build-release && ninja -t compdb > /e/tmp/c.json") is None,
          "ninja -t compdb - не сборка")
    check(hook("pre", "B", "Bash", command="ninja -C build-release -t targets all") is None,
          "ninja -C <папка> -t targets - не сборка")
    check(denied(hook("pre", "B", "Bash", command="ninja -t compdb > c.json && ninja")),
          "ninja после ninja -t - сборка")
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
    # R-108: this header was changed by a script, without an Edit/Write hook.
    write("src/a.h", "header2\n")
    write("docs/x.md", "чужое\n")
    marker = os.path.join(TMP, "built.txt")
    mark = dict(ENV, EDITQ_BUILD_CMD=f'"{sys.executable}" -c "open(r\'{marker}\',\'w\').write(\'1\')"')
    r = cli("A", "done", "-m", "hdui: a", env=mark)
    out = r.stdout + r.stderr
    check(r.returncode != 0 and "R-108" in out and "src/a.h" in out and "--add" in out and "--drop" in out,
          "R-108: src/a.h, правленный скриптом мимо списка, - done отказывает и называет файл")
    check("src/a.cpp" not in out.split("НЕ идут:")[-1].split("Коммита нет")[0], "свой файл в отказ не попал")
    check(state()["q"][0]["st"] == "hold" and not os.path.exists(marker)
          and "hdui: a" not in git("log", "--format=%s"), "R-108: после отказа очередь у A, сборки и коммита нет")
    bad = dict(ENV, EDITQ_BUILD_CMD="exit 1")
    r = cli("A", "done", "-m", "hdui: a", "--add", "src/a.h", env=bad)
    check(r.returncode != 0 and state()["q"][0]["st"] == "hold", "упавшая сборка: очередь у A, коммита нет")
    check("hdui: a" not in git("log", "--format=%s"), "после упавшей сборки коммита нет")

    r = cli("A", "done", "-m", "hdui: a", "--add", "src/a.h", env=mark)
    check(r.returncode == 0, "A done: " + (r.stderr.strip() or "прошёл"))
    check(os.path.exists(marker), "R-108: done с --add собирал")
    files = git("show", "--name-only", "--format=", "HEAD").split()
    check(files == ["src/a.cpp", "src/a.h"], f"в коммите только файлы A, включая --add: {files}")
    check(git("show", "HEAD:src/a.h") == "header2\n", "R-108: коммит содержит правку заголовка без хука")
    check("docs/x.md" in git("status", "--porcelain", "-uall"), "посторонний файл не включён через --add")
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
    cli("D", "leave")

    # R-271: свои куски общего документа разложены в индекс (git_hunks.py stage), в дереве ещё
    # чужие - done --add обязан взять версию индекса, а не файл целиком. Чужой файл, разложенный
    # в общий индекс другой сессией, в коммит не идёт. R-108: парный .h без --add - предупреждение
    body = "".join(f"строка {i}\n" for i in range(30))
    write("docs/RAKES.md", body)
    write("src/e.h", "eh\n")
    write("src/e.cpp", "e\n")
    git("add", "--", "docs/RAKES.md", "src/e.h", "src/e.cpp")
    git("commit", "-qm", "base e")
    mine = "## R-900 моя\n" + body
    write("docs/RAKES.md", mine)
    git("add", "--", "docs/RAKES.md")                      # как git_hunks.py stage
    write("docs/RAKES.md", mine + "## R-901 чужая\n")
    write("docs/other.md", "чужое в индексе\n")
    git("add", "--", "docs/other.md")
    check(hook("pre", "E", "Edit", file_path=os.path.join(REPO, "src", "e.cpp")) is None, "E правит")
    write("src/e.cpp", "e2\n")
    write("src/e.h", "eh2\n")                              # скриптом, без хука и без --add
    r = cli("E", "done", "-m", "hd: e", "--add", "docs/RAKES.md")
    out = r.stdout + r.stderr
    check(r.returncode != 0 and "src/e.h" in out and "src/c.cpp" not in out,
          "R-108: отказ из-за src/e.h; src/c.cpp сессии C на паузе - не в отказе")
    r = cli("E", "done", "-m", "hd: e", "--add", "docs/RAKES.md", "--force")
    out = r.stdout + r.stderr
    check(r.returncode == 0, "E done: " + (r.stderr.strip() or "прошёл"))
    files = git("show", "--name-only", "--format=", "HEAD").split()
    check(files == ["docs/RAKES.md", "src/e.cpp"], f"R-271: в коммите ровно файлы E: {files}")
    check(git("show", "HEAD:docs/RAKES.md") == mine, "R-271: документ ушёл версией индекса, без чужой записи")
    check(git("show", "HEAD:src/e.cpp") == "e2\n", "свой файл целиком - из рабочего дерева")
    check("R-901" in git("diff", "--", "docs/RAKES.md") and not git("diff", "--cached", "--", "docs/RAKES.md"),
          "чужая запись осталась в дереве, индекс документа = новый HEAD")
    check(not git("diff", "--cached", "--", "src/e.cpp"), "общий индекс по своему файлу = новый HEAD")
    check(git("diff", "--cached", "--name-only").split() == ["docs/other.md"],
          "чужое разложенное в индексе не тронуто и не закоммичено")
    check("R-271" in out and "docs/RAKES.md" in out, "done сказал, что документ взят версией индекса")
    check("R-108" in out and "src/e.h" in out, "R-108 --force: коммит без src/e.h, предупреждение")
    check("src/a.h" not in out, "неизменённый файл не называется")
    git("checkout", "--", "src/e.h")

    # R-108: в списке сессии только не-src файл, а src/ правил скрипт: --add src -> сборка и коммит;
    # --drop - файл чужой, в коммит не идёт, в дереве остаётся
    check(hook("pre", "F", "Edit", file_path=os.path.join(REPO, "CHANGELOG.md")) is None, "F правит CHANGELOG")
    write("CHANGELOG.md", "## [Не выпущено]\n- f\n")
    write("src/f.h", "fh\n")                               # новый, скриптом (как collapse_pilot_export.py)
    write("src/g.cpp", "чужое\n")
    if os.path.exists(marker):
        os.remove(marker)
    r = cli("F", "done", "-m", "tools: f", "--add", "src/f.h", "--drop", "src/g.cpp", env=mark)
    check(r.returncode == 0, "F done --add src/f.h --drop src/g.cpp: " + (r.stderr.strip() or "прошёл"))
    check(os.path.exists(marker), "R-108: src/ только через --add - сборка всё равно идёт")
    files = git("show", "--name-only", "--format=", "HEAD").split()
    check(files == ["CHANGELOG.md", "src/f.h"], f"R-108: --add src/f.h в коммите, --drop нет: {files}")
    check("?? src/g.cpp" in git("status", "--porcelain", "-uall"), "--drop: файл остался в дереве")

    # R-476: два субагента одной сессии S - у каждого свой билет; done второго не закрывает
    # билет первого и не уносит его файлы. Отдельная очередь, чтобы выпуск выше не мешал.
    env2 = dict(ENV, EDITQ_HOME=os.path.join(TMP, "q2"), EDITQ_RELEASE_DELAY="3600")
    env2s = dict(env2, CLAUDE_CODE_SESSION_ID="S")
    h_cpp, k_cpp = os.path.join(REPO, "src", "h.cpp"), os.path.join(REPO, "src", "k.cpp")
    check(hook("pre", "S", "Edit", agent="ag1", env=env2, file_path=h_cpp) is None, "R-476: ag1 занял очередь")
    write("src/h.cpp", "h ag1\n")
    check(denied(hook("pre", "S", "Edit", agent="ag2", env=env2, file_path=k_cpp)),
          "R-476: ag2 той же сессии получает отказ на правку src")
    check(hook("pre", "S", "Edit", env=env2, file_path=k_cpp) is not None,
          "R-476: главный разговор той же сессии тоже ждёт")
    run(["leave", "--session", "S"], env=env2)
    hook("pre", "S", "Bash", agent="ag2", env=env2, command='py -3.13 tools/editq.py done -m "x"')
    r = run(["done", "-m", "hdart: ag2"], env=env2s)
    check(r.returncode != 0 and "держишь не ты" in (r.stdout + r.stderr), "R-476: done ag2 - отказ, коммита нет")
    check("src/h.cpp" in git("status", "--porcelain", "-uall"), "R-476: файл ag1 не закоммичен чужим done")
    hook("pre", "S", "Bash", agent="ag1", env=env2, command='py -3.13 tools/editq.py done -m "x"')
    r = run(["done", "-m", "src: ag1", "--drop", "src/g.cpp", "src/c.cpp"], env=env2s)    # остатки проверок выше
    check(r.returncode == 0 and git("log", "-1", "--format=%s").strip() == "src: ag1",
          "R-476: done ag1 коммитит своё: " + (r.stderr.strip() or "прошёл"))
    check(git("show", "--name-only", "--format=", "HEAD").split() == ["src/h.cpp"], "R-476: в коммите только h.cpp")
    hook("pre", "S", "Bash", agent="ag2", env=env2, command="py -3.13 tools/editq.py wait --name k")
    r = run(["wait", "--name", "k", "--max", "5"], env=env2s)
    check(r.returncode == 0 and "твоя очередь" in r.stdout, "R-476: после done ag1 ag2 получает очередь")
    hook("pre", "S", "Bash", agent="ag2", env=env2, command="py -3.13 tools/editq.py leave")
    run(["leave"], env=env2s)

    shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{'ВСЁ ПРОШЛО' if not fails else f'УПАЛО {len(fails)}'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
