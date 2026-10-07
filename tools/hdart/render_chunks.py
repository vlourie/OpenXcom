#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Рендер кусками: процесс модели рисует не больше N картинок, потом новый процесс (DECISIONS 01.10).

Qwen-2.1 падала по CUDA OOM после 5 и 14 рендеров одного процесса (gpuq #301, #303) - не на одном предмете,
значит копится память процесса, а не велик кадр. Пока утечка не найдена, процесс модели живёт не больше
--max-renders рендеров (4):

    дописать вывод -> сверить хэши -> завершить процесс -> новый процесс -> продолжить

Дочерний скрипт обязан понимать --max-renders N, не перерисовывать готовое, писать каждый ответ строкой в
<out>/renders.jsonl (raw, sha256) и выходить с кодом 75, когда лимит кончился, а работа осталась; 0 - всё
готово (struct_probe.Render). После каждого процесса здесь сверяются ВСЕ записи журнала: файл на месте,
читается, sha256 тот же. Расхождение - стоп: ответ переписан или побит, продолжать на нём нельзя.
Падение процесса (OOM и прочее) - ещё один процесс, но не больше --max-crashes подряд без новых ответов.
Каждый процесс - строка <out>/processes.jsonl: pid, код выхода, его ответы с номером рендера после загрузки
модели (1..N), model_lock и generator_rev - проверить, не зависит ли качество от места в процессе.

    py -3.13 tools/gpuq.py add --name <имя> --cwd E:/OpenXCom -- <venv-python> tools/hdart/render_chunks.py \
        --out <папка с renders.jsonl> -- <venv-python> tools/hdart/<скрипт>.py <ключи>
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time

EXIT_MORE = 75
MANIFEST = "renders.jsonl"
PROCESSES = "processes.jsonl"           # границы процессов (специалист 01.10): что нарисовал каждый, каким замком


def records(out):
    path = os.path.join(out, MANIFEST)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(s) for s in f if s.strip()]


def log_process(out, n, pid, code, started, new):
    """Строка processes.jsonl: процесс, pid, код выхода, его ответы по порядку, замок и generator_rev ответов."""
    rec = {"process": n, "pid": pid, "exit_code": code, "started": started,
           "finished": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "jobs_rendered": [{"asset_id": r.get("asset_id"), "attempt": r.get("attempt"), "raw": r["raw"],
                              "process_render": r.get("process_render"), "found": bool(r.get("found"))}
                             for r in new],
           "renders": sum(1 for r in new if not r.get("found")),
           "model_lock": sorted({r["model_lock"] for r in new if r.get("model_lock")}),
           "generator_rev": sorted({r["generator_rev"] for r in new if r.get("generator_rev")}),
           "gpuq_job": os.environ.get("GPUQ_JOB_ID", "")}
    with open(os.path.join(out, PROCESSES), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def sha256_file(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def verify(out):
    """-> (записей, ошибки). Последняя запись по файлу главная; разные хэши одного файла - ошибка."""
    path = os.path.join(out, MANIFEST)
    if not os.path.exists(path):
        return 0, []
    seen, errs = {}, []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                errs.append("строка %d журнала не читается" % n)
                continue
            raw = r["raw"]
            if raw in seen and seen[raw] != r["sha256"]:
                errs.append("%s записан дважды с разным хэшем" % raw)
            seen[raw] = r["sha256"]
    for raw, h in sorted(seen.items()):
        if not os.path.exists(raw):
            errs.append("%s: файла нет" % raw)
            continue
        got = sha256_file(raw)
        if got != h:
            errs.append("%s: sha256 %s, в журнале %s" % (raw, got[:12], h[:12]))
            continue
        try:
            from PIL import Image
            Image.open(raw).verify()
        except Exception as e:                      # noqa: BLE001 - любая поломка картинки - ошибка сверки
            errs.append("%s: не читается (%s)" % (raw, e))
    return len(seen), errs


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    argv = sys.argv[1:]
    if "--" not in argv:
        raise SystemExit("нужно: render_chunks.py [ключи] -- <команда рендера>")
    cut = argv.index("--")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="папка, где дочерний скрипт пишет renders.jsonl")
    ap.add_argument("--max-renders", type=int, default=4, dest="max_renders")
    ap.add_argument("--max-crashes", type=int, default=2, dest="max_crashes",
                    help="падений подряд без нового ответа до остановки")
    ap.add_argument("--max-procs", type=int, default=200, dest="max_procs")
    a = ap.parse_args(argv[:cut])
    cmd = argv[cut + 1:]
    if not cmd:
        raise SystemExit("пустая команда рендера")
    if a.max_renders < 1:
        raise SystemExit("--max-renders не меньше 1")
    n0, errs = verify(a.out)
    if errs:
        raise SystemExit("сверка до старта: %d ошибок, первая: %s" % (len(errs), errs[0]))
    print("render_chunks: до %d рендеров на процесс; в журнале уже %d ответов, сверены" % (a.max_renders, n0),
          flush=True)
    procs, crashes, total_crashes, t0 = 0, 0, 0, time.time()
    while True:
        procs += 1
        if procs > a.max_procs:
            raise SystemExit("процессов больше %d - что-то не так, стоп" % a.max_procs)
        before, _e = verify(a.out)
        nrec = len(records(a.out))
        print("render_chunks: процесс %d" % procs, flush=True)
        started = time.strftime("%Y-%m-%dT%H:%M:%S")
        p = subprocess.Popen(cmd + ["--max-renders", str(a.max_renders)])
        code = p.wait()
        log_process(a.out, procs, p.pid, code, started, records(a.out)[nrec:])
        after, errs = verify(a.out)
        new = after - before
        if errs:
            for e in errs[:10]:
                print("   СВЕРКА:", e, flush=True)
            raise SystemExit("сверка после процесса %d: %d ошибок - стоп" % (procs, len(errs)))
        print("render_chunks: процесс %d вышел с кодом %d, новых ответов %d, сверено %d" % (procs, code, new, after),
              flush=True)
        if code == 0:
            break
        if code == EXIT_MORE:
            crashes = 0
            if new == 0:
                raise SystemExit("лимит кончился, а новых ответов нет - стоп, иначе бесконечный круг")
        else:
            total_crashes += 1
            crashes = 0 if new else crashes + 1
            if crashes >= a.max_crashes:
                raise SystemExit("процесс падал %d раз подряд без новых ответов (код %d) - стоп" % (crashes, code))
            print("render_chunks: падение (код %d) - новый процесс продолжит" % code, flush=True)
        time.sleep(3)                               # карта освобождается после выхода процесса
    print("render_chunks: готово - процессов %d, падений %d, ответов в журнале %d, %.0f мин" % (
        procs, total_crashes, after, (time.time() - t0) / 60), flush=True)


if __name__ == "__main__":
    main()
