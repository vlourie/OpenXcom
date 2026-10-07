#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка очереди видеокарты tools/gpuq.py без видеокарты.

Очередь живёт во временной папке (GPUQ_HOME), карта считается свободной (GPUQ_FAKE_GPU),
задания - короткие python, которые пишут в общий файл отметки начала и конца. Проверяется:
  - задания идут строго по одному и без простоя между ними;
  - перестановки urgent / move / before / after / last дают тот порядок, который назван;
  - urgent --now снимает идущее деревом и ставит его вторым;
  - --retries перезапускает упавшее, stop снимает без возврата.

    py -3 tools/test_gpuq.py
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
sys.path.insert(0, HERE)
# без psutil gpuq перезапускает этот тест под другим питоном - до создания TMP
import gpuq  # noqa: E402  (только чистые функции, без HOME)

sys.stdout.reconfigure(encoding="utf-8")  # кириллица при перенаправлении (R-001)
TMP = tempfile.mkdtemp(prefix="gpuq_test_")
ENV = dict(os.environ, GPUQ_HOME=os.path.join(TMP, "q"), GPUQ_FAKE_GPU="1",
           PYTHONIOENCODING="utf-8", GPUQ_PREEMPT_GRACE="4")
MARKS = os.path.join(TMP, "marks.txt")


def q(*args):
    r = subprocess.run([sys.executable, os.path.join(HERE, "gpuq.py")] + list(args),
                       env=ENV, capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        raise AssertionError(f"gpuq {args}: {r.stdout}{r.stderr}")
    return r.stdout


def state():
    with io.open(os.path.join(ENV["GPUQ_HOME"], "queue.json"), encoding="utf-8-sig") as f:
        return json.load(f)


def job(name, secs, code=0):
    body = (f"import time,sys\n"
            f"open({MARKS!r},'a').write('start {name} %.2f' % time.time() + chr(10))\n"
            f"time.sleep({secs})\n"
            f"open({MARKS!r},'a').write('end {name} %.2f' % time.time() + chr(10))\n"
            f"sys.exit({code})\n")
    return ["--", sys.executable, "-c", body]


def wait_idle(limit=60):
    t = time.time()
    while time.time() - t < limit:
        st = state()
        if not st["running"] and not st["order"]:
            return st
        time.sleep(0.5)
    raise AssertionError("очередь не опустела: " + q("list"))


def marks():
    with io.open(MARKS, encoding="utf-8") as f:
        return [l.split() for l in f if l.strip()]


def test_place():
    o = ["1", "2", "3", "4"]
    gpuq.place(o, "4", pos=1)
    assert o == ["4", "1", "2", "3"], o
    gpuq.place(o, "4", pos=2)
    assert o == ["1", "4", "2", "3"], o
    gpuq.place(o, "3", before="1")
    assert o == ["3", "1", "4", "2"], o
    gpuq.place(o, "3", after="2")
    assert o == ["1", "4", "2", "3"], o
    gpuq.place(o, "1")
    assert o == ["4", "2", "3", "1"], o
    gpuq.place(o, "5", pos=99)
    assert o == ["4", "2", "3", "1", "5"], o


def test_run():
    q("pause")                                  # набрать очередь, пока ничего не идёт
    q("add", "--name", "a", *job("a", 1))
    q("add", "--name", "b", *job("b", 1))
    q("add", "--name", "c", *job("c", 1))
    q("add", "--name", "d", "--urgent", *job("d", 1))      # d a b c
    q("move", "c", "2")                                     # d c a b
    q("before", "b", "a")                                   # d c b a
    q("after", "d", "b")                                    # c b d a
    q("last", "c")                                          # b d a c
    order = [state()["jobs"][i]["name"] for i in state()["order"]]
    assert order == ["b", "d", "a", "c"], order
    q("start")
    q("resume")
    wait_idle()
    m = marks()
    starts = [x[1] for x in m if x[0] == "start"]
    assert starts == ["b", "d", "a", "c"], starts
    # строго по одному: за каждым start идёт end того же, и только потом следующий start
    for i in range(0, len(m), 2):
        assert m[i][0] == "start" and m[i + 1] == ["end", m[i][1], m[i + 1][2]], m
    gaps = [float(m[i + 1][2]) - float(m[i][2]) for i in range(1, len(m) - 1, 2)]
    assert max(gaps) < gpuq.TICK + 2.5, f"простой между заданиями {gaps}"
    print(f"  по одному, простой между заданиями {max(gaps):.1f} с")


def test_now_retry_stop():
    os.remove(MARKS)
    q("add", "--name", "long", *job("long", 30))
    t = time.time()
    while state()["running"] is None:
        assert time.time() - t < 15, "long не запустился"
        time.sleep(0.3)
    q("add", "--name", "hot", *job("hot", 1))
    q("urgent", "hot", "--now")
    t = time.time()
    # long уже идёт, но marks.txt его питон мог ещё не создать
    while not os.path.exists(MARKS) or "start hot" not in io.open(MARKS, encoding="utf-8").read():
        assert time.time() - t < 20, "hot не запустился"
        time.sleep(0.3)
    st = state()
    names = [st["jobs"][i]["name"] for i in st["order"]]
    assert names[:1] == ["long"], f"снятый long не стоит следующим: {names}"
    q("rm", "long")
    q("add", "--name", "flaky", "--retries", "2", *job("flaky", 0, code=3))
    st = wait_idle()
    flaky = [j for j in st["jobs"].values() if j["name"] == "flaky"][0]
    assert flaky["tries"] == 3 and flaky["state"] == "failed", flaky
    q("add", "--name", "gone", *job("gone", 30))
    t = time.time()
    while state()["running"] is None:
        assert time.time() - t < 15
        time.sleep(0.3)
    pid = state()["jobs"][state()["running"]]["proc"]["pid"]
    q("stop", "gone")
    st = wait_idle()
    gone = [j for j in st["jobs"].values() if j["name"] == "gone"][0]
    assert gone["state"] == "stopped", gone
    assert not gpuq.psutil.pid_exists(pid), "снятое задание осталось жить"
    print("  urgent --now, повторы и stop - как задумано")


def frames(name, n, listen=True):
    """Серия как педия: по картинке в секунду, готовую не рисует заново, флаг уступки - между картинками."""
    d = os.path.join(TMP, name)
    body = (f"import os,sys,time\n"
            f"os.makedirs({d!r},exist_ok=True)\n"
            f"for n in range({n}):\n"
            f"    f=os.path.join({d!r},'%d.done'%n)\n"
            f"    if os.path.exists(f): continue\n"
            f"    y=os.environ.get('GPUQ_YIELD_FILE')\n"
            f"    if {listen} and y and os.path.exists(y): sys.exit(75)\n"
            f"    time.sleep(1)\n"
            f"    open(f,'w').write('x')\n"
            f"    open({MARKS!r},'a').write('frame {name} %d %.2f' % (n, time.time()) + chr(10))\n")
    return ["--", sys.executable, "-c", body]


def wait_mark(text, limit=30):
    t = time.time()
    while not os.path.exists(MARKS) or text not in io.open(MARKS, encoding="utf-8").read():
        assert time.time() - t < limit, f"нет отметки '{text}': " + q("list")
        time.sleep(0.2)


def test_prio_order():
    q("pause")
    q("add", "--name", "p9", "--prio", "9", *job("p9", 0))
    q("add", "--name", "p1", *job("p1", 0))
    q("add", "--name", "p0", "--prio", "0", *job("p0", 0))
    q("add", "--name", "p1b", *job("p1b", 0))
    os.remove(MARKS) if os.path.exists(MARKS) else None
    q("resume")
    wait_idle()
    starts = [x[1] for x in marks() if x[0] == "start"]
    assert starts == ["p0", "p1", "p1b", "p9"], starts
    # место, назначенное руками, настоящее: P подтягивается к соседям
    q("pause")
    q("add", "--name", "m1", *job("m1", 0))
    q("add", "--name", "m9", "--prio", "9", *job("m9", 0))
    q("add", "--name", "m1b", *job("m1b", 0))
    st = state()
    assert [st["jobs"][i]["name"] for i in st["order"]] == ["m1", "m1b", "m9"], "P9 не в конце своего уровня"
    q("before", "m9", "m1")
    q("last", "m1")
    st = state()
    assert [st["jobs"][i]["name"] for i in st["order"]] == ["m9", "m1b", "m1"], [st["jobs"][i]["name"] for i in st["order"]]
    assert [st["jobs"][i]["prio"] for i in st["order"]] == [1, 1, 1]
    # серия переведена в P9 по одному заданию - порядок серии прежний
    q("add", "--name", "s1", *job("s1", 0))
    q("add", "--name", "s2", *job("s2", 0))
    for n in ("s1", "s2", "m9", "m1b"):
        q("prio", n, "9")
    names = [l.split()[2] for l in q("list").splitlines() if l.strip()[:1].isdigit()]
    assert names == ["m1", "m9", "m1b", "s1", "s2"], names
    q("resume")
    wait_idle()
    print("  приоритет: P0, затем P1 по порядку, P9 последним; before/last меняют P по соседям")


def test_preempt():
    os.remove(MARKS)
    q("add", "--name", "pedia", "--prio", "9", "--preemptible", *frames("pedia", 6))
    wait_mark("frame pedia 1")
    q("add", "--name", "hot", "--prio", "1", *job("hot", 1))
    wait_idle(60)
    m = marks()
    drawn = [x[2] for x in m if x[0] == "frame"]
    assert sorted(drawn) == [str(i) for i in range(6)], f"картинки не по разу: {drawn}"
    seq = [(x[0], x[1]) for x in m]
    hot = seq.index(("start", "hot"))
    assert ("frame", "pedia") in seq[:hot] and ("frame", "pedia") in seq[hot:], f"не уступила посередине: {seq}"
    st = state()
    pedia = [j for j in st["jobs"].values() if j["name"] == "pedia"][0]
    assert pedia["state"] == "done" and pedia.get("yields") == 1, pedia
    assert not os.path.exists(os.path.join(ENV["GPUQ_HOME"], "yield", pedia["id"])), "флаг уступки остался"
    print(f"  уступка: педия отдала карту после картинки, продолжила с места, все 6 по разу")
    # не слушает флаг - снимается по сроку (GPUQ_PREEMPT_GRACE 4 с) и тоже продолжает
    os.remove(MARKS)
    q("add", "--name", "deaf", "--prio", "9", "--preemptible", *frames("deaf", 12, listen=False))
    wait_mark("frame deaf 0")
    t = time.time()
    q("add", "--name", "hot2", *job("hot2", 0))
    wait_mark("start hot2", 30)
    took = time.time() - t
    wait_idle(60)
    drawn = [x[2] for x in marks() if x[0] == "frame"]
    deaf = [j for j in state()["jobs"].values() if j["name"] == "deaf"][0]
    assert deaf["state"] == "done" and deaf.get("yields") == 1 and len(set(drawn)) == 12, (deaf, drawn)
    assert took < 4 + 2 * gpuq.TICK + 4, f"снятие по сроку заняло {took:.0f} с"
    print(f"  глухое к флагу снято по сроку за {took:.0f} с, дорисовало с места")
    # уступающее и нет никого выше - не уступает; P1 не уступающее P0 не снимает
    os.remove(MARKS)
    q("add", "--name", "solid", *job("solid", 3))
    wait_mark("start solid")
    q("add", "--name", "p0late", "--prio", "0", *job("p0late", 0))
    wait_idle(30)
    seq = [(x[0], x[1]) for x in marks()]
    assert seq.index(("end", "solid")) < seq.index(("start", "p0late")), seq
    print("  не уступающее задание доработало, P0 пошло после")
    st = state()
    pedia = [j for j in st["jobs"].values() if j["name"] == "pedia"][0]
    deaf = [j for j in st["jobs"].values() if j["name"] == "deaf"][0]
    assert pedia.get("yields_coop") == 1 and not pedia.get("yields_forced"), pedia
    assert deaf.get("yields_forced") == 1 and not deaf.get("yields_coop"), deaf
    log = io.open(os.path.join(ENV["GPUQ_HOME"], "daemon.log"), encoding="utf-8-sig").read()
    for ev in ("PREEMPT_REQUESTED", "PREEMPT_COOPERATIVE", "PREEMPT_TIMEOUT", "PREEMPT_FORCED"):
        assert ev in log, f"в журнале диспетчера нет {ev}"
    print("  журнал: PREEMPT_REQUESTED / COOPERATIVE / TIMEOUT / FORCED, счётчики сам 1 и по сроку 1")


def test_exit_codes():
    """75 у уступающего без запроса - PREEMPTED, по кругу больше 3 раз - сбой; 75 у обычного - сбой;
    потомки вышедшего задания не переживают его."""
    q("add", "--name", "loop75", "--prio", "9", "--preemptible", *job("loop75", 0, code=75))
    q("add", "--name", "plain75", *job("plain75", 0, code=75))
    st = wait_idle(60)
    loop = [j for j in st["jobs"].values() if j["name"] == "loop75"][0]
    plain = [j for j in st["jobs"].values() if j["name"] == "plain75"][0]
    assert loop["state"] == "failed" and loop.get("yields_coop") == 3 and loop.get("spurious") == 4, loop
    assert plain["state"] == "failed" and plain.get("code") == 75 and not plain.get("yields"), plain
    print("  код 75: у уступающего - уступка (3 раза без запроса, потом сбой), у обычного - сбой")
    os.remove(MARKS)
    body = (f"import subprocess,sys\n"
            f"c=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])\n"
            f"open({MARKS!r},'a').write('child %d' % c.pid + chr(10))\n"
            f"import time;time.sleep(2*{gpuq.TICK}+1)\n")
    q("add", "--name", "parent", "--", sys.executable, "-c", body)
    wait_idle(60)
    child = int([x for x in marks() if x[0] == "child"][0][1])
    t = time.time()
    while gpuq.psutil.pid_exists(child) and time.time() - t < 15:
        time.sleep(0.3)
    assert not gpuq.psutil.pid_exists(child), "потомок вышедшего задания жив"
    print("  потомок вышедшего задания снят: один процесс на задание")


def main():
    try:
        test_place()
        print("place: порядок верный")
        test_run()
        test_now_retry_stop()
        test_prio_order()
        test_preempt()
        test_exit_codes()
        print("OK")
    finally:
        subprocess.run([sys.executable, os.path.join(HERE, "gpuq.py"), "shutdown"],
                       env=ENV, capture_output=True)
        time.sleep(gpuq.TICK + 1)
        shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    main()
