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
TMP = tempfile.mkdtemp(prefix="gpuq_test_")
ENV = dict(os.environ, GPUQ_HOME=os.path.join(TMP, "q"), GPUQ_FAKE_GPU="1",
           PYTHONIOENCODING="utf-8")
MARKS = os.path.join(TMP, "marks.txt")

sys.path.insert(0, HERE)
import gpuq  # noqa: E402  (только чистые функции, без HOME)


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
    while "start hot" not in io.open(MARKS, encoding="utf-8").read():
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


def main():
    try:
        test_place()
        print("place: порядок верный")
        test_run()
        test_now_retry_stop()
        print("OK")
    finally:
        subprocess.run([sys.executable, os.path.join(HERE, "gpuq.py"), "shutdown"],
                       env=ENV, capture_output=True)
        time.sleep(gpuq.TICK + 1)
        shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    main()
