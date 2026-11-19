# Обвязка imgdecode.
#   imgtest.py compare <список> <exe старой> <exe новой> <папка вывода>
#   imgtest.py fuzz <список> <exe под ASan> <папка вывода> <имя>
#   imgtest.py time <список> <exe> <повторов>
# Процесс перезапускается со следующего файла после каждого отчёта санитайзера, сбоя и зависания
# (зависание - 15 секунд без перехода к следующему файлу).
import os, sys, subprocess, collections, pathlib, time, threading

mode = sys.argv[1]
lst = sys.argv[2]
paths = [l.strip() for l in open(lst, encoding="utf-8") if l.strip()]
HANG_S = int(os.environ.get("IMGTEST_HANG_S", "15"))


def ext(i):
    return paths[i].rsplit(".", 1)[-1].lower()


def env_for(exe):
    e = dict(os.environ)
    tc = "clang64" if "asan" in os.path.basename(exe) else "mingw64"
    e["PATH"] = "C:\\msys64\\%s\\bin;" % tc + e["PATH"]
    e["ASAN_OPTIONS"] = "detect_leaks=0:allocator_may_return_null=1:max_allocation_size_mb=2048:abort_on_error=0:exitcode=77"
    e["UBSAN_OPTIONS"] = "halt_on_error=1:print_stacktrace=0:exitcode=77"
    return e


def run_all(exe, tsv, repeat=1):
    """Возвращает (события {индекс: что случилось}, строка DONE последнего запуска)."""
    if os.path.exists(tsv):
        os.remove(tsv)
    start, events, done = 0, {}, ""
    while start < len(paths):
        p = subprocess.Popen([exe, lst, tsv, str(start), str(repeat)], env=env_for(exe), stderr=subprocess.PIPE,
                             text=True, errors="replace")
        state = {"last": start, "t": time.time(), "lines": []}

        def reader():
            for l in p.stderr:
                l = l.rstrip("\n")
                if l.startswith("BEGIN "):
                    state["last"] = int(l.split()[1])
                    state["t"] = time.time()
                    state["lines"] = []
                else:
                    state["lines"].append(l)
        th = threading.Thread(target=reader, daemon=True)
        th.start()
        hang = False
        while p.poll() is None:
            time.sleep(0.2)
            if time.time() - state["t"] > HANG_S:
                hang = True
                p.kill()
                break
        p.wait()
        th.join(5)
        dl = [l for l in state["lines"] if l.startswith("DONE")]
        if dl and not hang:
            done = dl[-1]
            break
        summ = [l for l in state["lines"] if "SUMMARY:" in l or "runtime error:" in l]
        events[state["last"]] = "ЗАВИСАНИЕ" if hang else (summ[0].strip() if summ else "процесс завершился, код %s" % p.returncode)
        start = state["last"] + 1
    return events, done


def short(what):
    for key in ("heap-buffer-overflow", "stack-buffer-overflow", "global-buffer-overflow", "heap-use-after-free",
                "stack-overflow", "SEGV", "runtime error", "ЗАВИСАНИЕ", "allocation-size-too-big", "negative-size-param",
                "bad-free", "out-of-memory", "double-free"):
        if key in what:
            return key
    return what[:40]


def load(tsv, events):
    d = {}
    if os.path.exists(tsv):
        for l in open(tsv, encoding="utf-8", errors="replace").read().splitlines():
            p = l.split("\t")
            d[int(p[0])] = p[1:]
    for i, what in events.items():
        d[i] = [short(what)]
    return d


if mode == "compare":
    old, new, outdir = sys.argv[3], sys.argv[4], pathlib.Path(sys.argv[5])
    outdir.mkdir(parents=True, exist_ok=True)
    res = []
    for exe, o in ((old, "old.tsv"), (new, "new.tsv")):
        t = time.time()
        ev, done = run_all(exe, str(outdir / o))
        print("%s: %s, всего %.1f с, сбоев и зависаний %d" % (os.path.basename(exe), done, time.time() - t, len(ev)))
        res.append(load(str(outdir / o), ev))
    da, db = res
    same, diff, okboth, rows = collections.Counter(), collections.Counter(), collections.Counter(), []
    for i in range(len(paths)):
        x, y, e = da.get(i), db.get(i), ext(i)
        if x == y:
            same[e] += 1
            if x and x[0] == "OK":
                okboth[e] += 1
        else:
            kind = "%s -> %s" % (x[0] if x else "НЕТ", y[0] if y else "НЕТ")
            if x and y and x[0] == y[0] == "OK":
                kind = "OK, отличаются: " + ",".join(q.rstrip("0123456789abcdefx:.") for p, q in zip(x[1:], y[1:]) if p != q)
            diff[(e, kind)] += 1
            rows.append("%s\t%s\t%s\t%s" % (paths[i], kind, " ".join(x or []), " ".join(y or [])))
    print("файлов %d; совпало по расширениям (из них декодировано обеими):" % len(paths))
    for e, n in sorted(same.items()):
        print("  .%-5s %7d  (%d)" % (e, n, okboth[e]))
    print("отличий: %d" % sum(diff.values()))
    for (e, k), n in sorted(diff.items()):
        print("  .%-5s %-50s %6d" % (e, k, n))
    (outdir / "diff.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8-sig")

elif mode == "fuzz":
    exe, outdir, name = sys.argv[3], pathlib.Path(sys.argv[4]), sys.argv[5]
    outdir.mkdir(parents=True, exist_ok=True)
    tsv = str(outdir / (name + ".tsv"))
    t = time.time()
    events, done = run_all(exe, tsv)
    kinds = collections.Counter()
    with open(outdir / (name + "_reports.tsv"), "w", encoding="utf-8-sig") as f:
        for i, what in sorted(events.items()):
            kinds[(ext(i), short(what))] += 1
            f.write("%s\t%s\n" % (paths[i], what))
    st = collections.Counter(v[0] for v in load(tsv, {}).values())
    print("%s: файлов %d, декодировано %d, отказ декодера %d, отчётов санитайзера, сбоев и зависаний %d, %.0f с" % (
        name, len(paths), st["OK"], st["ERR"], len(events), time.time() - t))
    for (e, k), n in sorted(kinds.items()):
        print("  .%-5s %-40s %5d" % (e, k, n))

elif mode == "time":
    exe, repeat = sys.argv[3], int(sys.argv[4])
    for k in range(3):
        ev, done = run_all(exe, os.path.join(os.environ.get("TEMP", "."), "imgtest_time.tsv"), repeat)
        print("%s: %s (сбоев %d)" % (os.path.basename(exe), done, len(ev)))
