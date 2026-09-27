#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Очередь правок игры: файлы игры правит одна сессия за раз, её работа коммитится сама,
после последней в очереди - выпуск для игроков.

Зачем. Несколько сессий Claude в одном рабочем дереве дерутся: правят один файл, собирают
чужую недоделку, коммитят чужие правки, выпускают полуготовое. Очередь делает правку игры
поочерёдной: держит очередь одна сессия, остальные пока читают и планируют.

Как устроено. Хуки (.claude/settings.json) зовут этот скрипт сами:
  - PreToolUse Edit/Write по файлу игры (список - tools/editq_paths.txt) и Bash со сборкой
    (ninja, cmake --build, build.ps1, OXCE_Build/Release, release.ps1): если очередь свободна,
    сессия её занимает и работает дальше; если занята - правка отклоняется, сессия встаёт в
    очередь и получает подсказку ждать;
  - PreToolUse Bash: git add -A / git add . / git commit -a отклоняются всегда - в общем дереве
    они сметают чужие правки;
  - PostToolUse Edit/Write: сессии, получившей очередь, один раз напоминает, как её отдать;
  - Stop: держателю, который заканчивает ход без done, один раз напоминает про done / pause.
Сессия узнаётся по CLAUDE_CODE_SESSION_ID (команды) и session_id (хуки) - это одно и то же.

Команды сессии (номер билета не нужен - сессия узнаётся сама):
    py -3 tools/editq.py wait [--name "щит в инвентаре"]   ждать очереди (до 9 мин, повторять)
    py -3 tools/editq.py done -m "hdui: ..." [--add F ...] [--drop F ...] [--no-build]
        собрать (если менялся src), закоммитить СВОИ файлы, отдать очередь следующему
    py -3 tools/editq.py pause "жду ответа Vitali"          отдать очередь, правки остаются
    py -3 tools/editq.py leave                             выйти из очереди без коммита
    py -3 tools/editq.py list                              кто держит, кто ждёт, что с выпуском

Команды человека:
    list | kick N | release now|off|on|cancel | log [-n 40]

Выпуск. Когда после done в очереди никого не осталось, через EDITQ_RELEASE_DELAY секунд
(по умолчанию 900 - вдруг следом придёт ещё правка) запускается Выпуск/release.ps1 (канал
stable, сборка -> подпись -> публикация -> архив для станции) скрытым окном. Пока он идёт,
очередь никому не выдаётся. Выпуска не будет, если в дереве есть незакоммиченные файлы игры
(выпуск собирается из рабочего дерева, а должен - ровно из закоммиченного) или не было ни
одного коммита с прошлого выпуска. После выпуска его правки CHANGELOG.md и notes коммитятся,
инструкция для станции - в .editq/release_last.txt.

Файлы - .editq/ в корне: state.json, release.log, release_last.txt, build.log.
Проверка: py -3 tools/test_editq.py
"""
import argparse
import contextlib
import fnmatch
import io
import json
import msvcrt
import os
import re
import shutil
import subprocess
import sys
import time

ENC = "utf-8-sig"
REPO = os.environ.get("EDITQ_REPO") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = os.environ.get("EDITQ_HOME") or os.path.join(REPO, ".editq")
STATE = os.path.join(HOME, "state.json")
LOCK = os.path.join(HOME, "lock")
REL_LOG = os.path.join(HOME, "release.log")
REL_LAST = os.path.join(HOME, "release_last.txt")
BUILD_LOG = os.path.join(HOME, "build.log")
PATHS_FILE = os.environ.get("EDITQ_PATHS") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "editq_paths.txt")

ALIVE = 15 * 60          # ждущий, которого не видно дольше, очередь не получает (спит)
FORGET = 3 * 3600        # ждущего без правок, которого не видно дольше, из очереди убрать
RELEASE_DELAY = int(os.environ.get("EDITQ_RELEASE_DELAY", "900"))
WAIT_MAX = 540           # wait возвращается раньше 10-минутного предела Bash
KEEP_HIST = 50

NO_WINDOW = 0x08000000
NEW_GROUP = 0x00000200
DETACHED = 0x00000008
BREAKAWAY = 0x01000000
BELOW_NORMAL = 0x00004000


# ---------------------------------------------------------------- хранение

@contextlib.contextmanager
def locked():
    """Состояние правят хуки семи сессий сразу: читать-менять-писать только под замком."""
    os.makedirs(HOME, exist_ok=True)
    f = open(LOCK, "a+b")
    try:
        for _ in range(300):
            try:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                time.sleep(0.05)
        else:
            raise SystemExit("очередь правок занята другим процессом больше 15 с")
        st = load()
        yield st
        save(st)
    finally:
        with contextlib.suppress(OSError):
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        f.close()


def load():
    try:
        with io.open(STATE, encoding=ENC) as f:
            st = json.load(f)
    except (OSError, ValueError):
        st = {}
    st.setdefault("next", 1)
    st.setdefault("q", [])
    st.setdefault("hist", [])
    st.setdefault("rel", {"st": "idle", "auto": True})
    st["rel"].setdefault("auto", True)
    return st


def save(st):
    tmp = STATE + ".tmp"
    with io.open(tmp, "w", encoding=ENC) as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE)


def now():
    return time.time()


def ago(t):
    s = int(now() - t)
    if s < 90:
        return f"{s} с"
    if s < 5400:
        return f"{s // 60} мин"
    return f"{s // 3600} ч {s % 3600 // 60:02d} мин"


def stamp(t=None):
    return time.strftime("%d.%m %H:%M", time.localtime(t or now()))


# ---------------------------------------------------------------- пути

def game_patterns():
    try:
        with io.open(PATHS_FILE, encoding=ENC) as f:
            lines = [l.strip() for l in f]
    except OSError:
        lines = ["src/**"]
    out = []
    for l in lines:
        if not l or l.startswith("#"):
            continue
        rx = re.escape(l).replace(r"\*\*", ".*").replace(r"\*", "[^/]*").replace(r"\?", "[^/]")
        out.append(re.compile("^" + rx + "$", re.I))
    return out


def rel(path):
    """Путь от корня репозитория через /, либо None, если он вне репозитория."""
    if not path:
        return None
    p = path.replace("\\", "/")
    m = re.match(r"^/([a-zA-Z])/(.*)$", p)          # /e/OpenXCom/... из Git Bash
    if m:
        p = f"{m.group(1)}:/{m.group(2)}"
    if not os.path.isabs(p):
        p = os.path.join(REPO, p)
    p = os.path.normpath(p)
    root = os.path.normpath(REPO)
    if os.path.normcase(p) == os.path.normcase(root):
        return None
    if not os.path.normcase(p).startswith(os.path.normcase(root) + os.sep):
        return None
    return p[len(root) + 1:].replace("\\", "/")


def is_game(r, pats=None):
    return bool(r) and any(rx.match(r) for rx in (pats or game_patterns()))


# ---------------------------------------------------------------- очередь

def entry_of(st, sid):
    for e in st["q"]:
        if e["sid"] == sid:
            return e
    return None


def by_ticket(st, t):
    for e in st["q"]:
        if str(e["t"]) == str(t):
            return e
    raise SystemExit(f"нет билета {t} в очереди")


def holder(st):
    for e in st["q"]:
        if e["st"] == "hold":
            return e
    return None


def label(e):
    return f"#{e['t']}" + (f" «{e['name']}»" if e.get("name") else "")


def advance(st):
    """Выдать очередь первому живому ждущему, если её никто не держит и не идёт выпуск."""
    t = now()
    st["q"] = [e for e in st["q"]
               if not (e["st"] == "wait" and not e["files"] and t - e["seen"] > FORGET)]
    if holder(st) or st["rel"]["st"] == "running":
        return None
    for e in st["q"]:
        if e["st"] == "wait" and t - e["seen"] <= ALIVE:
            e["st"] = "hold"
            e["granted"] = t
            e["told"] = False
            e["stopwarn"] = False
            return e
    return None


def join(st, sid, name=None):
    e = entry_of(st, sid)
    if not e:
        e = {"t": st["next"], "sid": sid, "name": name or "", "st": "wait", "files": [],
             "joined": now(), "seen": now(), "granted": None, "told": False, "stopwarn": False,
             "note": ""}
        st["next"] += 1
        st["q"].append(e)
    elif e["st"] == "pause":
        # вернулся после паузы - в конец очереди, как все
        st["q"].remove(e)
        st["q"].append(e)
        e["st"] = "wait"
        e["note"] = ""
    if name:
        e["name"] = name
    e["seen"] = now()
    if st["rel"]["st"] == "pending":
        st["rel"] = {"st": "idle", "auto": st["rel"]["auto"],
                     "note": f"отложен: в очередь пришёл #{e['t']}"}
    return e


def position(st, e):
    waiting = [x for x in st["q"] if x["st"] == "wait"]
    return waiting.index(e) + 1 if e in waiting else 0


def queue_text(st, me=None):
    h = holder(st)
    parts = []
    if st["rel"]["st"] == "running":
        parts.append(f"идёт выпуск для игроков (с {stamp(st['rel'].get('started'))})")
    if h:
        parts.append(f"держит {label(h)} уже {ago(h['granted'])}")
    if me and me["st"] == "wait":
        parts.append(f"ты {label(me)}, ждёшь {position(st, me)}-м")
    return "; ".join(parts)


# ---------------------------------------------------------------- git и сборка

def git(*args, check=True):
    for attempt in range(20):
        r = subprocess.run(["git", "-C", REPO] + list(args), capture_output=True,
                           text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
        if r.returncode and "index.lock" in r.stderr and attempt < 19:
            time.sleep(0.5)          # другая сессия как раз делает git status
            continue
        if check and r.returncode:
            raise SystemExit(f"git {' '.join(args)}: {r.stderr.strip() or r.stdout.strip()}")
        return r


def changed(paths):
    """Из путей - те, что отличаются от HEAD (изменённые, новые, удалённые), без игнорируемых."""
    if not paths:
        return []
    out = set()
    for i in range(0, len(paths), 100):
        r = git("status", "--porcelain=v1", "-z", "--untracked-files=all", "--",
                *paths[i:i + 100])
        items = r.stdout.split("\0")
        k = 0
        while k < len(items):
            it = items[k]
            if len(it) > 3:
                out.add(it[3:])
                if it[0] in "RC":
                    k += 1           # у переименования следом старое имя
            k += 1
    return sorted(out)


def dirty_game():
    pats = game_patterns()
    r = git("status", "--porcelain=v1", "-z", "--untracked-files=all")
    out = []
    for it in r.stdout.split("\0"):
        if len(it) > 3 and is_game(it[3:], pats):
            out.append(it[3:])
    return out


def msys_env():
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    try:
        with io.open(os.path.join(REPO, "tools", "build", "build_config.json"), encoding=ENC) as f:
            msys = json.load(f).get("MsysBin") or r"C:\msys64\mingw64\bin"
    except (OSError, ValueError):
        msys = r"C:\msys64\mingw64\bin"
    env["PATH"] = msys + os.pathsep + env.get("PATH", "")
    return env


def build():
    """Инкрементальная сборка ninja в build-release. (код, хвост лога)"""
    custom = os.environ.get("EDITQ_BUILD_CMD")
    env = msys_env()
    if custom:
        argv = custom
    else:
        ninja = shutil.which("ninja", path=env["PATH"])
        if not ninja:
            return 127, "ninja не найден ни в PATH, ни в MsysBin (tools/build/build_config.json)"
        argv = [ninja, "-C", os.path.join(REPO, "build-release")]
    os.makedirs(HOME, exist_ok=True)
    with open(BUILD_LOG, "wb") as log:
        p = subprocess.run(argv, cwd=REPO, env=env, stdout=log, stderr=subprocess.STDOUT,
                           shell=isinstance(argv, str), creationflags=NO_WINDOW | BELOW_NORMAL)
    return p.returncode, tail(BUILD_LOG, 30)


def tail(path, n):
    try:
        with io.open(path, encoding="utf-8", errors="replace") as f:
            return "".join(f.readlines()[-n:])
    except OSError:
        return ""


def needs_build(files):
    return any(f.startswith(("src/", "cmake/")) or f == "CMakeLists.txt" for f in files)


# ---------------------------------------------------------------- хуки

BUILD_RX = re.compile(r"(?i)((^|[\s;&|(/\\\"'])ninja(\.exe)?[\"']?(\s|$)|cmake(\.exe)?[\"']?\s+--build"
                      r"|build\.ps1|OXCE_Build\.cmd|OXCE_Release\.cmd|release\.ps1)")
READ_CMDS = {"git", "grep", "rg", "cat", "head", "tail", "sed", "less", "ls", "echo", "find",
             "type", "get-content", "select-string", "wc", "diff"}


def strip_quotes(cmd):
    """Без тел heredoc и строк в кавычках: текст сообщения коммита - не команда."""
    cmd = re.sub(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?^\s*\2\s*$", " ", cmd, flags=re.S | re.M)
    return re.sub(r"\"(\\.|[^\"])*\"|'[^']*'", " ", cmd)


def sweeping_git(cmd):
    """git add -A / . / -u и git commit -a: в общем дереве сметают чужие правки."""
    c = strip_quotes(cmd)
    for part in re.split(r"&&|\|\||;|\|", c):
        m = re.search(r"(?:^|\s)git\s+(?:-C\s+\S+\s+)?(add|commit)\b(.*)", part)
        if not m:
            continue
        toks = m.group(2).split()
        if "--" in toks:
            paths = toks[toks.index("--") + 1:]
            toks = toks[:toks.index("--")]
            if paths and not set(paths) & {".", "*", ":/", "./"}:
                continue             # -A -- <пути>: ограничено названными путями
        if m.group(1) == "add":
            if any(t in ("-A", "--all", "-u", "--update", ".", "*", ":/", "./") for t in toks):
                return "git add -A / . / -u"
        else:
            if any(t == "--all" or re.fullmatch(r"-[A-Za-z]*a[A-Za-z]*", t) for t in toks):
                return "git commit -a"
    return None


def builds(cmd):
    if "editq.py" in cmd or "EDITQ_BYPASS=1" in cmd:
        return False
    for part in re.split(r"&&|\|\||;|\|", strip_quotes(cmd)):
        words = part.strip().split()
        if not words:
            continue
        first = os.path.basename(words[0].replace("\\", "/")).lower()
        if first in READ_CMDS:
            continue
        if BUILD_RX.search(part):
            return True
    return False


def out(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False))
    sys.stdout.flush()


def deny(reason):
    out({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                "permissionDecisionReason": reason}})


def claim(sid, what, path=None):
    """Сессия хочет трогать игру: занять очередь или встать в неё. (разрешено, текст отказа)"""
    with locked() as st:
        e = entry_of(st, sid)
        if e and e["st"] == "hold":
            e["seen"] = now()
            if path and path not in e["files"]:
                e["files"].append(path)
            return True, None
        e = join(st, sid)
        g = advance(st)
        if g is e:
            if path:
                e["files"].append(path)
            return True, None
        why = queue_text(st, e)
    return False, (
        f"Очередь правок игры ({what}): {why}. Файлы игры сейчас правит другая сессия - "
        f"правка отклонена, чтобы не драться. Пока можно читать, искать и планировать. "
        f"Жди очереди командой: py -3 tools/editq.py wait --name \"<о чём правка, 3-5 слов>\" "
        f"(Bash, timeout 600000; вернётся кодом 3 через 9 минут - повторить). Когда wait скажет "
        f"«твоя очередь» - повтори правку. Общее состояние: py -3 tools/editq.py list")


def hook(kind):
    raw = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")
    if not raw.strip():
        return
    ev = json.loads(raw)
    sid = ev.get("session_id") or ""
    if not sid:
        return
    tool = ev.get("tool_name") or ""
    ti = ev.get("tool_input") or {}

    if kind == "pre":
        if tool in ("Bash", "PowerShell"):
            cmd = ti.get("command") or ""
            sw = sweeping_git(cmd)
            if sw:
                deny(f"{sw} запрещено: в одном рабочем дереве работают несколько сессий, и такая "
                     f"команда заберёт в коммит их незаконченные правки. Добавляй файлы по именам "
                     f"(git add -- путь). Правки игры коммитит сама очередь: py -3 tools/editq.py done")
                return
            if builds(cmd):
                ok, why = claim(sid, "сборка")
                if not ok:
                    deny(why)
            return
        path = ti.get("file_path") or ti.get("notebook_path") or ti.get("path")
        r = rel(path)
        if not is_game(r):
            return
        ok, why = claim(sid, r, r)
        if not ok:
            deny(why)
        return

    if kind == "post":
        with locked() as st:
            e = entry_of(st, sid)
            if not e or e["st"] != "hold" or e.get("told"):
                return
            e["told"] = True
            t = e["t"]
        out({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": (
            f"Ты держишь очередь правок игры (билет #{t}): остальные сессии ждут, пока ты не отдашь "
            f"её. Когда правка собрана и проверена: py -3 tools/editq.py done -m \"область: что "
            f"сделано\" [--add docs/...] - скрипт соберёт (если менялся src), закоммитит ТОЛЬКО "
            f"твои файлы и передаст очередь. Нужно ждать ответа Vitali - "
            f"py -3 tools/editq.py pause \"причина\". Не коммить и не отдавай очередь, пока сборка "
            f"не прошла.")}})
        return

    if kind == "stop":
        if ev.get("stop_hook_active"):
            return
        with locked() as st:
            e = entry_of(st, sid)
            if not e or e["st"] != "hold" or e.get("stopwarn"):
                return
            e["stopwarn"] = True
            t, files, waiting = e["t"], len(e["files"]), sum(x["st"] == "wait" for x in st["q"])
        out({"decision": "block", "reason": (
            f"Ты держишь очередь правок игры (билет #{t}, файлов {files}), ждут ещё {waiting}. "
            f"Работа закончена и собирается - py -3 tools/editq.py done -m \"область: что сделано\". "
            f"Ждёшь ответа Vitali - py -3 tools/editq.py pause \"о чём спросил\", чтобы очередь "
            f"не стояла. Ни то ни другое не подходит - просто закончи ход, это напоминание одно.")})


# ---------------------------------------------------------------- команды сессии

def my_sid(a):
    sid = getattr(a, "session", None) or os.environ.get("CLAUDE_CODE_SESSION_ID")
    if not sid:
        raise SystemExit("не знаю, какая это сессия: нет CLAUDE_CODE_SESSION_ID (или --session)")
    return sid


def cmd_wait(a):
    sid = my_sid(a)
    deadline = now() + a.max
    last = None
    while True:
        with locked() as st:
            e = join(st, sid, a.name)
            e["host"] = os.environ.get("CLAUDE_CODE_HOST_SESSION_ID", e.get("host", ""))
            advance(st)
            if e["st"] == "hold":
                print(f"твоя очередь: {label(e)}. Правь файлы игры; закончишь - "
                      f"py -3 tools/editq.py done -m \"область: что сделано\"")
                return 0
            text = queue_text(st, e)
        if text != last:
            print(f"{time.strftime('%H:%M:%S')} {text}", flush=True)
            last = text
        if now() >= deadline:
            print("ещё не очередь - запусти wait снова")
            return 3
        time.sleep(3)


def cmd_done(a):
    sid = my_sid(a)
    with locked() as st:
        e = entry_of(st, sid)
        if not e or e["st"] != "hold":
            raise SystemExit("очередь держишь не ты - done не к чему. Сначала wait")
        e["seen"] = now()
        files = list(e["files"])
        others = {f: label(x) for x in st["q"] if x is not e for f in x["files"]}
        t = e["t"]
    drop = {rel(p) or p for p in a.drop}
    files = [f for f in files + [rel(p) or p for p in a.add] if f not in drop]
    files = list(dict.fromkeys(files))
    todo = changed(files)
    clash = [f"{f} (у {others[f]})" for f in todo if f in others]
    if clash and not a.force:
        raise SystemExit("эти файлы трогала и другая сессия, в коммит уйдут и её правки:\n  "
                         + "\n  ".join(clash) + "\nРазберись с ней (list) или --force")
    sha = None
    if todo:
        if needs_build(todo) and not a.no_build:
            print("собираю (ninja, build-release) ...", flush=True)
            code, log = build()
            if code:
                print(log)
                raise SystemExit(f"сборка упала (код {code}) - очередь осталась за тобой, "
                                 f"коммита нет. Полный лог: {BUILD_LOG}")
            print("сборка прошла")
        msg = a.message
        if a.file:
            with io.open(a.file, encoding=ENC) as f:
                msg = f.read()
        if not msg:
            raise SystemExit("нужно сообщение коммита: -m \"область: что сделано\" или -F файл")
        git("add", "--", *todo)
        r = git("commit", "-q", "-m", msg, "--", *todo, check=False)
        if r.returncode:
            raise SystemExit(f"git commit не прошёл - очередь осталась за тобой:\n{r.stdout}{r.stderr}")
        sha = git("rev-parse", "--short", "HEAD").stdout.strip()
        print(f"коммит {sha}: {msg.splitlines()[0]} ({len(todo)} файл.)")
    else:
        print("изменённых файлов нет - коммита не будет")
    with locked() as st:
        e = entry_of(st, sid)
        if e:
            st["q"].remove(e)
        st["hist"].append({"t": t, "name": e.get("name", "") if e else "", "sha": sha,
                           "msg": (msg.splitlines()[0] if todo else ""), "files": todo, "at": now()})
        st["hist"] = st["hist"][-KEEP_HIST:]
        if sha:
            st["rel"]["dirty"] = True
        g = advance(st)
        if g:
            print(f"очередь передана {label(g)}")
        schedule_release(st)
    return 0


def cmd_pause(a):
    sid = my_sid(a)
    with locked() as st:
        e = entry_of(st, sid)
        if not e or e["st"] != "hold":
            raise SystemExit("очередь держишь не ты")
        e["st"] = "pause"
        e["note"] = a.why
        g = advance(st)
        print(f"очередь отдана{' ' + label(g) if g else ''}. Твои правки ({len(e['files'])} файл.) "
              f"остались в дереве незакоммиченными; вернёшься - wait, встанешь в конец")
        if e["files"]:
            print("пока ты на паузе, выпуска не будет: в дереве твои незакоммиченные файлы игры")


def cmd_leave(a):
    sid = my_sid(a)
    with locked() as st:
        e = entry_of(st, sid)
        if not e:
            print("тебя нет в очереди")
            return
        st["q"].remove(e)
        g = advance(st)
        print(f"вышел из очереди; правки, если были, остались в дереве"
              f"{'; очередь у ' + label(g) if g else ''}")
        schedule_release(st)


# ---------------------------------------------------------------- выпуск

def schedule_release(st):
    """Очередь опустела после коммитов - через RELEASE_DELAY поднять выпуск."""
    r = st["rel"]
    if not r.get("auto") or not r.get("dirty") or r["st"] == "running":
        return
    if any(e["st"] in ("wait", "hold", "pause") and (e["st"] != "wait" or e["files"]
                                                        or now() - e["seen"] <= ALIVE)
           for e in st["q"]):
        return
    st["rel"] = {"st": "pending", "auto": True, "dirty": True, "due": now() + RELEASE_DELAY}
    spawn_worker()
    print(f"очередь пуста - выпуск для игроков в {stamp(st['rel']['due'])}, если никто не придёт "
          f"(py -3 tools/editq.py release cancel - отменить)")


def spawn_worker():
    os.makedirs(HOME, exist_ok=True)
    logf = open(REL_LOG, "ab")
    argv = [sys.executable, os.path.abspath(__file__), "release-worker"]
    kw = dict(cwd=REPO, stdout=logf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
              env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1"))
    try:
        subprocess.Popen(argv, creationflags=DETACHED | NEW_GROUP | BREAKAWAY, **kw)
    except OSError:
        subprocess.Popen(argv, creationflags=DETACHED | NEW_GROUP, **kw)


def rlog(msg):
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}", flush=True)


def release_worker(_a):
    """Ждёт срока; если очередь так и пуста - выпуск. Лишний рабочий (их поднимает каждый done)
    выходит сам: выпуск берёт тот, кто первым перевёл состояние в running."""
    while True:
        with locked() as st:
            r = st["rel"]
            if r["st"] != "pending":
                return
            if now() < r["due"]:
                wait = min(30, r["due"] - now())
            else:
                dirty = dirty_game()
                if dirty:
                    st["rel"] = {"st": "blocked", "auto": r["auto"], "dirty": True,
                                 "note": "в дереве незакоммиченные файлы игры: "
                                         + ", ".join(dirty[:8]) + (" ..." if len(dirty) > 8 else "")}
                    rlog("выпуск не начат: " + st["rel"]["note"])
                    return
                st["rel"] = {"st": "running", "auto": r["auto"], "dirty": True,
                             "started": now(), "pid": os.getpid(),
                             "head": git("rev-parse", "--short", "HEAD").stdout.strip()}
                break
        time.sleep(wait)
    rlog("выпуск: старт")
    code = run_release()
    with locked() as st:
        r = st["rel"]
        if code == 0:
            rid, commit = after_release()
            zipname = newest_zip()
            st["rel"] = {"st": "done", "auto": r["auto"], "dirty": False, "at": now(),
                         "id": rid, "zip": zipname, "commit": commit}
            write_instructions(rid, zipname)
            rlog(f"выпуск {rid} готов, архив {zipname}")
        else:
            st["rel"] = {"st": "failed", "auto": r["auto"], "dirty": True, "at": now(),
                         "note": f"release.ps1 код {code}, лог {REL_LOG}"}
            rlog(f"выпуск упал: код {code}")
        g = advance(st)
        if g:
            rlog(f"очередь выдана {label(g)}")


def run_release():
    custom = os.environ.get("EDITQ_RELEASE_CMD")
    if custom:
        return subprocess.run(custom, shell=True, cwd=REPO, creationflags=NO_WINDOW).returncode
    ps1 = os.path.join(REPO, "Выпуск", "release.ps1")
    p = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps1],
                       cwd=REPO, stdout=sys.stdout, stderr=subprocess.STDOUT,
                       stdin=subprocess.DEVNULL, creationflags=NO_WINDOW | BELOW_NORMAL)
    return p.returncode


def after_release():
    """release.ps1 закрыл раздел CHANGELOG и переименовал notes - закоммитить это."""
    paths = changed(["CHANGELOG.md", "Выпуск/notes"])
    rid = ""
    for p in paths:
        m = re.match(r"Выпуск/notes/(.+)\.ru\.txt$", p)
        if m and m.group(1) != "next":
            rid = m.group(1)
    if not paths:
        return rid, None
    git("add", "--", *paths)
    msg = f"release: выпуск {rid or 'для игроков'} - CHANGELOG и «Что нового» (очередь правок)"
    r = git("commit", "-q", "-m", msg, "--", *paths, check=False)
    if r.returncode:
        rlog(f"коммит выпуска не прошёл: {r.stderr.strip()}")
        return rid, None
    return rid, git("rev-parse", "--short", "HEAD").stdout.strip()


def newest_zip():
    d = os.path.join(REPO, "dist")
    try:
        z = [f for f in os.listdir(d) if f.startswith("xp-releases_") and f.endswith(".zip")]
    except OSError:
        return ""
    return max(z, key=lambda f: os.path.getmtime(os.path.join(d, f))) if z else ""


def write_instructions(rid, zipname):
    text = (
        f"Выпуск {rid} для игроков готов ({stamp()}).\n\n"
        f"1. Архив: E:\\OpenXCom\\dist\\{zipname}\n"
        f"   Скопировать на станцию в C:\\XPiratezModHD\\\n\n"
        f"2. На станции, PowerShell:\n"
        f"   cd C:\\xp-portal\\portal\\deploy\n"
        f"   powershell -ExecutionPolicy Bypass -File .\\station.ps1 releases C:\\XPiratezModHD\\{zipname}\n\n"
        f"3. Проверить: station.ps1 закончил без ошибок, лаунчер на своей машине предлагает "
        f"обновление до {rid}.\n")
    with io.open(REL_LAST, "w", encoding=ENC) as f:
        f.write(text)


def cmd_release(a):
    with locked() as st:
        r = st["rel"]
        if a.what == "off":
            r["auto"] = False
            if r["st"] == "pending":
                r["st"] = "idle"
            print("автовыпуск выключен (release on - включить)")
        elif a.what == "on":
            r["auto"] = True
            print("автовыпуск включён")
            schedule_release(st)
        elif a.what == "cancel":
            if r["st"] == "pending":
                r["st"] = "idle"
                print("ждущий выпуск отменён; следующий done запланирует снова")
            else:
                print(f"отменять нечего: {r['st']}")
        elif a.what == "now":
            if r["st"] == "running":
                print("выпуск уже идёт")
                return
            st["rel"] = {"st": "pending", "auto": r.get("auto", True), "dirty": True, "due": now()}
            spawn_worker()
            print("выпуск запускается (если в дереве нет незакоммиченных файлов игры)")


# ---------------------------------------------------------------- для человека

def describe(st):
    lines = []
    if not st["q"]:
        lines.append("очередь правок игры пуста")
    for e in st["q"]:
        if e["st"] == "hold":
            s = f"ДЕРЖИТ {ago(e['granted'])}"
        elif e["st"] == "pause":
            s = f"пауза: {e.get('note') or '-'}"
        else:
            s = "ждёт" + (f" (не видно {ago(e['seen'])} - спит)" if now() - e["seen"] > ALIVE else "")
        files = ", ".join(e["files"][:4]) + (" ..." if len(e["files"]) > 4 else "")
        lines.append(f"  {label(e):40} {s}" + (f"  [{files}]" if files else ""))
    r = st["rel"]
    rs = {"idle": "не запланирован", "pending": f"в {stamp(r.get('due'))}",
          "running": f"идёт с {stamp(r.get('started'))}",
          "done": f"{r.get('id', '')} готов {stamp(r.get('at'))}, архив dist\\{r.get('zip', '')}",
          "failed": f"УПАЛ {stamp(r.get('at'))}: {r.get('note', '')}",
          "blocked": f"НЕ НАЧАТ: {r.get('note', '')}"}.get(r["st"], r["st"])
    lines.append(f"выпуск: {rs}" + ("" if r.get("auto") else " (автовыпуск выключен)"))
    if r.get("note") and r["st"] == "idle":
        lines.append(f"  {r['note']}")
    for h in st["hist"][-5:]:
        lines.append(f"  сделано {stamp(h['at'])} #{h['t']} {h.get('sha') or '-'} {h.get('msg', '')}")
    return "\n".join(lines)


def cmd_list(_a):
    with locked() as st:
        advance(st)
        print(describe(st))
    if os.path.exists(REL_LAST) and load()["rel"]["st"] == "done":
        print()
        print(tail(REL_LAST, 20).rstrip())


def cmd_brief(_a):
    """Строка для SessionStart: только если есть о чём сказать."""
    st = load()
    if st["q"] or st["rel"]["st"] in ("pending", "running", "failed", "blocked"):
        print("ОЧЕРЕДЬ ПРАВОК ИГРЫ (tools/editq.py): файлы игры правит одна сессия за раз, "
              "хук сам ставит в очередь.")
        print(describe(st))


def cmd_kick(a):
    with locked() as st:
        e = by_ticket(st, a.ticket)
        st["q"].remove(e)
        g = advance(st)
        print(f"{label(e)} убран из очереди, его правки остались в дереве"
              f"{'; очередь у ' + label(g) if g else ''}")
        schedule_release(st)


def cmd_log(a):
    print(tail(REL_LOG, a.n))


def main():
    for s in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError):
            s.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="очередь правок игры")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("hook"); p.add_argument("kind", choices=["pre", "post", "stop"])
    p = sub.add_parser("wait"); p.add_argument("--name"); p.add_argument("--max", type=int, default=WAIT_MAX)
    p.add_argument("--session")
    p = sub.add_parser("done"); p.add_argument("-m", "--message"); p.add_argument("-F", "--file")
    p.add_argument("--add", nargs="*", default=[]); p.add_argument("--drop", nargs="*", default=[])
    p.add_argument("--no-build", action="store_true"); p.add_argument("--force", action="store_true")
    p.add_argument("--session")
    p = sub.add_parser("pause"); p.add_argument("why", nargs="?", default=""); p.add_argument("--session")
    p = sub.add_parser("leave"); p.add_argument("--session")
    sub.add_parser("list")
    sub.add_parser("brief")
    p = sub.add_parser("kick"); p.add_argument("ticket")
    p = sub.add_parser("release"); p.add_argument("what", choices=["now", "off", "on", "cancel"])
    sub.add_parser("release-worker")
    p = sub.add_parser("log"); p.add_argument("-n", type=int, default=40)
    a = ap.parse_args()
    if a.cmd == "hook":
        try:
            hook(a.kind)
        except Exception as ex:          # хук не должен ронять сессию
            sys.stderr.write(f"editq hook: {ex}\n")
        return 0
    fn = {"wait": cmd_wait, "done": cmd_done, "pause": cmd_pause, "leave": cmd_leave,
          "list": cmd_list, "brief": cmd_brief, "kick": cmd_kick, "release": cmd_release,
          "release-worker": release_worker, "log": cmd_log}[a.cmd]
    return fn(a) or 0


if __name__ == "__main__":
    sys.exit(main())
