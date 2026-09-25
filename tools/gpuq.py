#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Очередь заданий на видеокарту: одно задание на карте, следующее - сразу как она освободилась.

Всё, что грузит модель на 5090 (генерация, обучение, описания через Ollama), ставится сюда, а
не запускается напрямую. Диспетчер - отдельный процесс, он переживает закрытие сессии агента.
Пока диспетчер не запущен, его поднимает первая же команда add.

    py -3 tools/gpuq.py add --name promo -- tools/hdart/.venv-qwen21/Scripts/python.exe -u tools/hdart/gen_promo.py draw --seeds 4
    py -3 tools/gpuq.py add --urgent --name lora -- powershell -File tools/hdart/train_lora.ps1
    py -3 tools/gpuq.py list

Порядок раздаёт человек:
    urgent ID [--now]     первым в очереди; --now ещё и снимает то, что идёт, и ставит его вторым
    move ID N             поставить N-м (1 - первым)
    before ID OTHER       поставить перед OTHER
    after ID OTHER        поставить после OTHER
    last ID               в конец
Те же места задаются и при постановке: add --urgent / --pos N / --before X / --after X.
ID - номер задания или его имя (--name).

Прочее:
    rm ID                 убрать из очереди (идущее - снять деревом процессов)
    stop ID               снять идущее и НЕ возвращать в очередь
    pause / resume        не запускать новых (идущее доработает) - например, карта нужна под игру
    log ID [-n 40]        хвост лога задания
    start / shutdown      поднять / остановить диспетчер (задания он не трогает)

Как диспетчер решает, что карта свободна. Счёт памяти по процессам на Windows недоступен
(nvidia-smi под WDDM отдаёт [N/A]), поэтому три проверки вместе:
  1. нет процесса из списка GPU_SCRIPTS, запущенного МИМО очереди - если есть, ждём его;
  2. модели Ollama выгружены - диспетчер выгружает их сам (keep_alive 0): сервер держит
     модель в памяти ещё пять минут после последнего запроса;
  3. занято не больше FREE_MB - рабочий стол, браузер и прочее тоже живут на карте.
Причина ожидания пишется в list и в status.txt.

Файлы - в .gpuq/ в корне репозитория: queue.json (очередь и история), logs/<id>.log (вывод
заданий, дописывается), daemon.log, status.txt (снимок для отчёта раз в 15 минут).
Задание запускается списком аргументов, без оболочки (грабли R-045), с PYTHONIOENCODING=utf-8
(R-001), с пониженным приоритетом; снимается деревом процессов (R-073).
"""
import argparse
import contextlib
import io
import json
import msvcrt
import os
import subprocess
import sys
import time
import urllib.request

import psutil

ENC = "utf-8-sig"
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = os.environ.get("GPUQ_HOME") or os.path.join(REPO, ".gpuq")
FAKE_GPU = os.environ.get("GPUQ_FAKE_GPU") == "1"   # для теста: карту не спрашивать
QUEUE = os.path.join(HOME, "queue.json")
LOCK = os.path.join(HOME, "lock")
LOGS = os.path.join(HOME, "logs")
DAEMON_LOG = os.path.join(HOME, "daemon.log")
STATUS = os.path.join(HOME, "status.txt")

TICK = 3            # секунд между проверками
FREE_MB = 8000      # выше этого карта считается занятой кем-то посторонним
KEEP_DONE = 30      # сколько законченных заданий помнить
OLLAMA = "http://127.0.0.1:11434"

# Скрипты, которые грузят модель на карту. Нужны, чтобы увидеть запуск мимо очереди.
# Тот же список читает хук .claude/hooks/gpu-guard.ps1.
with io.open(os.path.join(REPO, "tools", "gpu_scripts.txt"), encoding="utf-8-sig") as _f:
    GPU_SCRIPTS = {l.strip().lower() for l in _f if l.strip() and not l.startswith("#")}

NO_WINDOW = 0x08000000
NEW_GROUP = 0x00000200
DETACHED = 0x00000008
BREAKAWAY = 0x01000000
BELOW_NORMAL = 0x00004000


# ---------------------------------------------------------------- хранение

@contextlib.contextmanager
def locked():
    """Очередь правят и диспетчер, и команды: читать-менять-писать только под замком."""
    os.makedirs(HOME, exist_ok=True)
    f = open(LOCK, "a+b")
    try:
        for _ in range(200):
            try:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                time.sleep(0.05)
        else:
            raise SystemExit("очередь занята другим процессом больше 10 с")
        st = load()
        yield st
        save(st)
    finally:
        try:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        f.close()


def load():
    try:
        with io.open(QUEUE, encoding=ENC) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"next_id": 1, "jobs": {}, "order": [], "running": None, "paused": False,
                "daemon": None, "wait": ""}


def save(st):
    tmp = QUEUE + ".tmp"
    with io.open(tmp, "w", encoding=ENC) as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    os.replace(tmp, QUEUE)


def find(st, ref):
    """Номер или имя. По имени - самое свежее задание, которое ещё не кончилось."""
    if ref in st["jobs"]:
        return ref
    alive = [i for i in st["order"] + [st["running"]] if i and st["jobs"][i]["name"] == ref]
    if alive:
        return alive[-1]
    same = [i for i, j in st["jobs"].items() if j["name"] == ref]
    if same:
        return max(same, key=int)
    raise SystemExit(f"нет задания {ref}")


def place(order, jid, pos=None, before=None, after=None):
    """Вставить jid в order: pos с единицы, либо рядом с другим заданием; иначе в конец."""
    if jid in order:
        order.remove(jid)
    if before is not None:
        i = order.index(before) if before in order else 0
    elif after is not None:
        i = order.index(after) + 1 if after in order else len(order)
    elif pos is not None:
        i = min(max(pos - 1, 0), len(order))
    else:
        i = len(order)
    order.insert(i, jid)


# ---------------------------------------------------------------- процессы

def proc_of(rec):
    """Живой процесс по записи {pid, ctime}; ctime защищает от повторно выданного PID."""
    if not rec:
        return None
    try:
        p = psutil.Process(rec["pid"])
        if abs(p.create_time() - rec["ctime"]) < 1:
            return p
    except (psutil.Error, KeyError, TypeError):
        pass
    return None


def kill_tree(p):
    kids = p.children(recursive=True)
    for k in kids + [p]:
        with contextlib.suppress(psutil.Error):
            k.kill()
    psutil.wait_procs(kids + [p], timeout=10)


def gpu_script(cmdline):
    for a in cmdline:
        base = os.path.basename(a.replace("\\", "/")).lower()
        if base in GPU_SCRIPTS:
            return base
    return None


def strays(own):
    """GPU-процессы, запущенные мимо очереди. own - PID идущего задания и его потомков."""
    out = []
    me = os.getpid()
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if p.info["pid"] in own or p.info["pid"] == me:
                continue
            name = (p.info["name"] or "").lower()
            if not (name.startswith("python") or name.startswith("powershell")
                    or name.startswith("accelerate")):
                continue
            s = gpu_script(p.info["cmdline"] or [])
            if s:
                out.append((p.info["pid"], s))
        except psutil.Error:
            continue
    # обёртка и её дочерний python - одно и то же задание, показываем по разу
    seen, res = set(), []
    for pid, s in out:
        if s not in seen:
            seen.add(s)
            res.append((pid, s))
    return res


def vram_used():
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total",
                            "--format=csv,noheader,nounits"], capture_output=True, text=True,
                           timeout=15, creationflags=NO_WINDOW)
        used, total = (int(x) for x in r.stdout.strip().splitlines()[0].split(","))
        return used, total
    except Exception:
        return None, None


def ollama_unload(log):
    """Выгрузить все модели Ollama. Возвращает список выгруженных (пустой - и так пусто)."""
    try:
        with urllib.request.urlopen(OLLAMA + "/api/ps", timeout=5) as r:
            models = [m["name"] for m in json.load(r).get("models", [])]
    except Exception:
        return []
    for m in models:
        body = json.dumps({"model": m, "keep_alive": 0}).encode()
        req = urllib.request.Request(OLLAMA + "/api/generate", data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=60).read()
            log(f"Ollama: выгружена {m}")
        except Exception as e:
            log(f"Ollama: не выгрузилась {m}: {e}")
    return models


def wrap(cmd):
    """.ps1 и .cmd сами не запускаются - оборачиваем. Интерпретатор .py задаёт человек."""
    head = cmd[0].lower()
    if head.endswith(".ps1"):
        return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File"] + cmd
    if head.endswith((".cmd", ".bat")):
        return ["cmd", "/c"] + cmd
    return cmd


# ---------------------------------------------------------------- диспетчер

def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def dlog(msg):
    os.makedirs(HOME, exist_ok=True)
    with io.open(DAEMON_LOG, "a", encoding="utf-8") as f:
        f.write(f"{now()}  {msg}\n")


def launch(job):
    os.makedirs(LOGS, exist_ok=True)
    env = dict(os.environ)
    env.update({"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
    env.update(job.get("env") or {})
    logf = open(os.path.join(LOGS, f"{job['id']}.log"), "ab")
    logf.write(f"\n===== {now()} запуск: {json.dumps(job['cmd'], ensure_ascii=False)}\n"
               .encode("utf-8"))
    logf.flush()
    p = subprocess.Popen(wrap(job["cmd"]), cwd=job["cwd"], env=env, stdout=logf,
                         stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                         creationflags=NEW_GROUP | NO_WINDOW | BELOW_NORMAL)
    logf.close()
    return p


def finish(st, jid, code, how):
    job = st["jobs"][jid]
    job["ended"] = now()
    job["code"] = code
    if how == "stopped":
        job["state"] = "stopped"
    elif code == 0:
        job["state"] = "done"
    elif job.get("retries", 0) > job.get("tries", 1) - 1 and code is not None:
        job["state"] = "queued"
        place(st["order"], jid, pos=1)
        dlog(f"#{jid} {job['name']}: код {code}, повтор {job['tries']} из {job['retries']}")
        return
    else:
        job["state"] = "failed" if code else ("done" if code == 0 else "ended")
    dlog(f"#{jid} {job['name']}: {job['state']} (код {code})")
    done = [i for i, j in st["jobs"].items()
            if j["state"] in ("done", "failed", "stopped", "removed", "ended")]
    for i in sorted(done, key=int)[:-KEEP_DONE]:
        del st["jobs"][i]


def serve(_args):
    with locked() as st:
        if proc_of(st.get("daemon")):
            print("диспетчер уже работает")
            return
        me = psutil.Process()
        st["daemon"] = {"pid": me.pid, "ctime": me.create_time()}
    dlog(f"диспетчер поднят, PID {os.getpid()}")
    popen = {}          # jid -> Popen: код возврата знаем только у своих детей
    last_wait = ""
    while True:
        with locked() as st:
            if not st.get("daemon") or st["daemon"]["pid"] != os.getpid():
                dlog("диспетчер снят командой shutdown")
                return
            jid = st["running"]
            if jid:
                job = st["jobs"].get(jid)
                p = proc_of(job and job.get("proc"))
                if job and job.get("kill"):
                    if p:
                        kill_tree(p)
                    how = job.pop("kill")
                    st["running"] = None
                    popen.pop(jid, None)
                    if how == "requeue":
                        job["state"] = "queued"
                        dlog(f"#{jid} {job['name']}: снято ради срочного, стоит вторым")
                    else:
                        finish(st, jid, None, "stopped")
                elif not p:
                    code = popen.pop(jid).poll() if jid in popen else None
                    st["running"] = None
                    if job:
                        finish(st, jid, code, "exit")
            wait = ""
            if not st["running"] and st["order"]:
                if st.get("paused"):
                    wait = "пауза (resume)"
                else:
                    wait = gpu_busy()
                    if not wait:
                        jid = st["order"].pop(0)
                        job = st["jobs"][jid]
                        try:
                            p = launch(job)
                        except OSError as e:
                            job["state"] = "failed"
                            job["ended"] = now()
                            job["code"] = str(e)
                            dlog(f"#{jid} {job['name']}: не запустился: {e}")
                        else:
                            popen[jid] = p
                            pp = psutil.Process(p.pid)
                            job.update(state="running", started=now(),
                                       tries=job.get("tries", 0) + 1,
                                       proc={"pid": p.pid, "ctime": pp.create_time()})
                            st["running"] = jid
                            dlog(f"#{jid} {job['name']}: запущен, PID {p.pid}")
            st["wait"] = wait
            if wait and wait != last_wait:
                dlog(f"ждём: {wait}")
            last_wait = wait
            write_status(st)
        time.sleep(TICK)


def gpu_busy():
    """Пустая строка - карта свободна; иначе причина, почему ждём."""
    if FAKE_GPU:
        return ""
    s = strays(set())
    if s:
        return "мимо очереди идёт " + ", ".join(f"{n} (PID {pid})" for pid, n in s)
    ollama_unload(dlog)
    used, total = vram_used()
    if used is None:
        return "nvidia-smi не отвечает"
    if used > FREE_MB:
        # после выгрузки память отпускается не мгновенно - это нормальное короткое ожидание
        return f"на карте занято {used} МБ из {total} неизвестно кем (порог {FREE_MB})"
    return ""


def tail(path, n):
    try:
        with io.open(path, encoding="utf-8", errors="replace") as f:
            return f.readlines()[-n:]
    except OSError:
        return []


def elapsed(start):
    try:
        s = time.time() - time.mktime(time.strptime(start, "%Y-%m-%d %H:%M:%S"))
    except (TypeError, ValueError):
        return ""
    return f"{int(s // 3600)} ч {int(s % 3600 // 60):02d} м"


def describe(st):
    lines = []
    d = "работает" if proc_of(st.get("daemon")) else "НЕ ЗАПУЩЕН (py -3 tools/gpuq.py start)"
    lines.append(f"диспетчер: {d}" + ("   ПАУЗА" if st.get("paused") else ""))
    jid = st["running"]
    if jid:
        j = st["jobs"][jid]
        last = [l.strip() for l in tail(os.path.join(LOGS, f"{jid}.log"), 5) if l.strip()]
        lines.append(f"идёт:  #{jid} {j['name']}  {elapsed(j.get('started'))}"
                     + (f"  попытка {j['tries']}" if j.get("tries", 1) > 1 else ""))
        if last:
            lines.append(f"       > {last[-1][:150]}")
    else:
        lines.append("идёт:  ничего")
    if st.get("wait"):
        lines.append(f"ждём:  {st['wait']}")
    lines.append(f"очередь ({len(st['order'])}):")
    for n, i in enumerate(st["order"], 1):
        j = st["jobs"][i]
        lines.append(f"  {n:>2}. #{i} {j['name']}   ({j['added']})")
    done = [j for j in st["jobs"].values()
            if j["state"] in ("done", "failed", "stopped", "ended")]
    done.sort(key=lambda j: int(j["id"]))
    if done:
        lines.append("закончены:")
        for j in done[-8:]:
            lines.append(f"      #{j['id']} {j['name']}  {j['state']}  код {j.get('code')}"
                         f"  {j.get('ended', '')}")
    return lines


def write_status(st):
    with io.open(STATUS, "w", encoding=ENC) as f:
        f.write(f"снято {now()}\n" + "\n".join(describe(st)) + "\n")


def ensure_daemon(quiet=False):
    if proc_of(load().get("daemon")):
        if not quiet:
            print("диспетчер уже работает")
        return
    os.makedirs(HOME, exist_ok=True)
    out = open(DAEMON_LOG, "ab")
    argv = [sys.executable, os.path.abspath(__file__), "serve"]
    kw = dict(cwd=REPO, stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
              env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1"))
    try:
        subprocess.Popen(argv, creationflags=DETACHED | NEW_GROUP | BREAKAWAY, **kw)
    except OSError:
        # задание обвязки может запрещать выход из него - тогда без BREAKAWAY
        subprocess.Popen(argv, creationflags=DETACHED | NEW_GROUP, **kw)
    for _ in range(50):
        time.sleep(0.2)
        if proc_of(load().get("daemon")):
            print("диспетчер поднят")
            return
    print("диспетчер не поднялся - смотри .gpuq/daemon.log")


# ---------------------------------------------------------------- команды

def cmd_add(a):
    if not a.cmd:
        raise SystemExit("после -- нужна команда")
    cmd = a.cmd[1:] if a.cmd[0] == "--" else a.cmd
    if cmd[0].lower().endswith(".py"):
        raise SystemExit("укажи интерпретатор перед .py: у генерации свои окружения "
                         "(.venv, .venv-qwen21, E:/train/.venv-train)")
    env = dict(kv.split("=", 1) for kv in a.env)
    with locked() as st:
        jid = str(st["next_id"])
        st["next_id"] += 1
        st["jobs"][jid] = {"id": jid, "name": a.name or os.path.basename(
            (gpu_script(cmd) or cmd[-1]).replace("\\", "/")), "cmd": cmd,
            "cwd": os.path.abspath(a.cwd), "env": env, "retries": a.retries,
            "state": "queued", "added": now()}
        place(st["order"], jid, pos=1 if a.urgent else a.pos,
              before=find(st, a.before) if a.before else None,
              after=find(st, a.after) if a.after else None)
        n = st["order"].index(jid) + 1
        print(f"#{jid} {st['jobs'][jid]['name']}: в очереди {n}-м"
              + (", карта сейчас занята" if st["running"] else ""))
    ensure_daemon(quiet=True)


def reorder(a, **kw):
    with locked() as st:
        jid = find(st, a.id)
        if jid not in st["order"]:
            raise SystemExit(f"#{jid} не в очереди (он {st['jobs'][jid]['state']})")
        place(st["order"], jid, **kw)
        print("\n".join(describe(st)))


def cmd_urgent(a):
    with locked() as st:
        jid = find(st, a.id)
        run = st["running"]
        if a.now and run and run != jid:
            st["jobs"][run]["kill"] = "requeue"
            place(st["order"], run, pos=1)
        if jid != run:
            place(st["order"], jid, pos=1)
        print("\n".join(describe(st)))
        if a.now and run and run != jid:
            print(f"#{run} будет снят и встанет вторым; начнёт СНАЧАЛА, "
                  "если сам не умеет продолжать с места")


def cmd_rm(a, how="removed"):
    with locked() as st:
        jid = find(st, a.id)
        if jid == st["running"]:
            st["jobs"][jid]["kill"] = "stop"
            print(f"#{jid} снимается")
        elif jid in st["order"]:
            st["order"].remove(jid)
            st["jobs"][jid].update(state=how, ended=now())
            print(f"#{jid} убран из очереди")
        else:
            print(f"#{jid} уже {st['jobs'][jid]['state']}")


def cmd_list(_a):
    print("\n".join(describe(load())))


def cmd_log(a):
    st = load()
    jid = find(st, a.id)
    sys.stdout.write("".join(tail(os.path.join(LOGS, f"{jid}.log"), a.n)))


def cmd_pause(a, value):
    with locked() as st:
        st["paused"] = value
    print("пауза: новые задания не запускаются" if value else "очередь снова идёт")


def cmd_shutdown(_a):
    with locked() as st:
        had = proc_of(st.get("daemon"))
        st["daemon"] = None
    print("диспетчер остановится за несколько секунд; идущее задание продолжит работать"
          if had else "диспетчер и так не работал")


def main():
    ap = argparse.ArgumentParser(description="очередь заданий на видеокарту")
    sub = ap.add_subparsers(dest="op", required=True)

    p = sub.add_parser("add", help="поставить задание")
    p.add_argument("--name")
    p.add_argument("--cwd", default=REPO)
    p.add_argument("--env", action="append", default=[], help="КЛЮЧ=значение")
    p.add_argument("--retries", type=int, default=0, help="перезапусков при ненулевом коде")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--urgent", action="store_true", help="первым")
    g.add_argument("--pos", type=int, help="N-м")
    g.add_argument("--before")
    g.add_argument("--after")
    p.add_argument("cmd", nargs=argparse.REMAINDER)
    p.set_defaults(fn=cmd_add)

    p = sub.add_parser("urgent", help="первым; --now - снять идущее")
    p.add_argument("id")
    p.add_argument("--now", action="store_true")
    p.set_defaults(fn=cmd_urgent)
    p = sub.add_parser("move", help="поставить N-м")
    p.add_argument("id")
    p.add_argument("pos", type=int)
    p.set_defaults(fn=lambda a: reorder(a, pos=a.pos))
    for op in ("before", "after"):
        p = sub.add_parser(op, help=f"поставить {'перед' if op == 'before' else 'после'}")
        p.add_argument("id")
        p.add_argument("other")
        p.set_defaults(fn=lambda a, op=op: reorder(
            a, **{op: find(load(), a.other)}))
    p = sub.add_parser("last", help="в конец")
    p.add_argument("id")
    p.set_defaults(fn=lambda a: reorder(a))

    p = sub.add_parser("rm", help="убрать (идущее - снять)")
    p.add_argument("id")
    p.set_defaults(fn=cmd_rm)
    p = sub.add_parser("stop", help="снять идущее")
    p.add_argument("id")
    p.set_defaults(fn=cmd_rm)
    p = sub.add_parser("log", help="хвост лога задания")
    p.add_argument("id")
    p.add_argument("-n", type=int, default=40)
    p.set_defaults(fn=cmd_log)
    sub.add_parser("list", help="что идёт и что ждёт").set_defaults(fn=cmd_list)
    sub.add_parser("pause").set_defaults(fn=lambda a: cmd_pause(a, True))
    sub.add_parser("resume").set_defaults(fn=lambda a: cmd_pause(a, False))
    sub.add_parser("start", help="поднять диспетчер").set_defaults(
        fn=lambda a: ensure_daemon())
    sub.add_parser("shutdown", help="остановить диспетчер").set_defaults(fn=cmd_shutdown)
    sub.add_parser("serve", help="(сам диспетчер)").set_defaults(fn=serve)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
