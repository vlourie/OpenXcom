#!/usr/bin/env python3
"""Один скрытый бой стенда без профилировщика: время, ЦП, память и отпечатки потоков записи.

  py -3.13 tools/ai_speed/run_one.py --build build-ai36 --mission STR_VESSEL_BOMBER_SECTOID_ELITE --seed 201 --name base
  py -3.13 tools/ai_speed/run_one.py --build <путь к опытной сборке> --env OXCE_AI_FASTLOG=1 --unthrottle 1 --name p

Итог - runs/<имя>.json и одна строка в stdout; сравнение вариантов - cmp_runs.py.
Игра идёт как в серии: скрытый стол, SDL dummy (ai_probe.Hidden), на экране ничего (R-124)."""
import argparse, ctypes, hashlib, json, os, re, sys, threading, time

from _common import OUT, ROOT, ENC_W


def ecores():
    """Номера логических процессоров с низшим классом эффективности (E-ядра) - GetLogicalProcessorInformationEx."""
    k32 = ctypes.windll.kernel32
    size = ctypes.c_ulong(0)
    k32.GetLogicalProcessorInformationEx(0, None, ctypes.byref(size))  # 0 = RelationProcessorCore
    buf = ctypes.create_string_buffer(size.value)
    if not k32.GetLogicalProcessorInformationEx(0, buf, ctypes.byref(size)):
        return set()
    raw, off, cls = buf.raw, 0, {}
    while off < size.value:
        length = int.from_bytes(raw[off + 4:off + 8], "little")
        eff = raw[off + 9]
        mask = int.from_bytes(raw[off + 32:off + 40], "little")
        for bit in range(64):
            if mask >> bit & 1:
                cls[bit] = eff
        off += length
    low = min(cls.values()) if cls else 0
    return {c for c, e in cls.items() if e == low} if len(set(cls.values())) > 1 else set()


class Meter(threading.Thread):
    """ЦП и память процесса игры, пока он жив; по просьбе снимает EcoQoS (R-126)."""

    def __init__(self, pid, unthrottle):
        super().__init__(daemon=True)
        self.pid, self.unthrottle, self.cpu, self.peak, self.cores = pid, unthrottle, 0.0, 0, {}

    def run(self):
        import psutil
        try:
            p = psutil.Process(self.pid)
        except psutil.Error:
            return
        if self.unthrottle:
            k32 = ctypes.windll.kernel32
            k32.OpenProcess.restype = ctypes.c_void_p
            h = k32.OpenProcess(0x0200, False, self.pid)  # PROCESS_SET_INFORMATION

            class Throttle(ctypes.Structure):
                _fields_ = [("Version", ctypes.c_ulong), ("ControlMask", ctypes.c_ulong), ("StateMask", ctypes.c_ulong)]

            st = Throttle(1, 1, 0)  # EXECUTION_SPEED под управлением, состояние 0 - без EcoQoS
            ok = k32.SetProcessInformation(ctypes.c_void_p(h), 4, ctypes.byref(st), ctypes.sizeof(st))
            self.unthrottle = "ok" if ok else f"ошибка {ctypes.GetLastError()}"
            k32.CloseHandle(ctypes.c_void_p(h))
        while True:
            try:
                t = p.cpu_times()
                self.cpu = t.user + t.system
                self.peak = max(self.peak, p.memory_info().rss)
                # cpu_num в Windows нет: доля E-ядер - по загрузке ядер всей машины (годится, когда бой один)
                for n, busy in enumerate(psutil.cpu_percent(percpu=True)):
                    self.cores[n] = self.cores.get(n, 0) + busy
            except psutil.Error:
                return
            time.sleep(0.25)


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # R-001
    ap = argparse.ArgumentParser()
    ap.add_argument("--mission", required=True)
    ap.add_argument("--seed", type=int, default=201)
    ap.add_argument("--name", required=True)
    ap.add_argument("--build", default="build-ai36")
    ap.add_argument("--rec", type=int, default=1)
    ap.add_argument("--path", type=int, default=1)
    ap.add_argument("--turns", type=int, default=60)
    ap.add_argument("--unthrottle", type=int, default=0, help="1 - снять EcoQoS с процесса игры (R-126)")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--env", action="append", default=[], help="окружение стенда: OXCE_AI_FASTLOG=1")
    ap.add_argument("--opt", action="append", default=[], help="ключ options.cfg прогона: oxceHdKillCam=false")
    ap.add_argument("--penv", action="append", default=[], help="окружение процесса игры поверх ai_probe: SDL_AUDIODRIVER=none")
    ap.add_argument("--display", default="", help="размер окна вместо 1280x720: 640x400")
    a = ap.parse_args()

    os.environ["OXCE_AI_BUILD"] = a.build
    for k in ("OXCE_AI_RECORD", "OXCE_AI_RECORD_PATH"):
        os.environ.pop(k, None)
    if a.rec:
        os.environ["OXCE_AI_RECORD"] = "1"
    if a.path:
        os.environ["OXCE_AI_RECORD_PATH"] = "1"
    for kv in a.env:
        k, v = kv.split("=", 1)
        os.environ[k] = v
    sys.path.insert(0, str(ROOT / "tools"))
    import ai_probe

    if not ai_probe.EXE.is_file():
        sys.exit(f"нет exe: {ai_probe.EXE}")
    # the build this run measures, for cmp_runs: a base run of another build compares another record (R-087)
    st = ai_probe.EXE.stat()
    exe = {"exe": str(ai_probe.EXE), "exe_mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)),
           "exe_size": st.st_size, "exe_sha256": hashlib.sha256(ai_probe.EXE.read_bytes()).hexdigest()[:16]}
    holder = {}
    base_hidden = ai_probe.Hidden
    base_prepare = ai_probe.prepare_user

    def prepare(work):
        """Как ai_probe.prepare_user, плюс ключи --opt: есть строка - заменить, нет - дописать в блок options."""
        base_prepare(work)
        if not a.opt:
            return
        cfg = (work / "options.cfg").read_bytes().decode("utf-8")
        for kv in a.opt:
            k, v = kv.split("=", 1)
            cfg, n = re.subn(rf"(?m)^(\s*){k}: .*$", rf"\g<1>{k}: {v}", cfg)
            if not n:
                cfg = re.sub(r"(?m)^options:\s*$", lambda m: m.group(0) + f"\n  {k}: {v}", cfg, count=1)
        (work / "options.cfg").write_bytes(cfg.encode("utf-8"))  # читает игра - без спецификации

    ai_probe.prepare_user = prepare

    class Metered(base_hidden):
        def __init__(self, args, cwd, env):
            for kv in a.penv:
                k, v = kv.split("=", 1)
                env[k] = v
            if a.display:
                w, h = a.display.split("x")
                args[args.index("-displayWidth") + 1] = w
                args[args.index("-displayHeight") + 1] = h
            super().__init__(args, cwd, env)
            holder["m"] = Meter(self.pid, a.unthrottle)
            holder["m"].start()

    ai_probe.Hidden = Metered
    t0 = time.time()
    res = ai_probe.run(None, a.turns, name="var_" + a.name, timeout=a.timeout, bot=True, seed=a.seed,
                       campaign="NoCodexCatZ.sav", mission=a.mission, careful=True, squad=8)
    wall = time.time() - t0
    m = holder["m"]
    log = ai_probe.WORK / ("var_" + a.name) / "openxcom.log"
    result = next((l for l in res.lines if l.startswith("[AIRESULT]")), "")
    ms = int((re.search(r" ms=(\d+)", result) or [0, 0])[1])
    vms = int((re.search(r" vms=(\d+)", result) or [0, 0])[1])
    OUT.mkdir(exist_ok=True)
    eset = ecores()
    on_e = sum(v for k, v in m.cores.items() if k in eset)
    data = {"name": a.name, "mission": a.mission, "seed": a.seed, "build": a.build, "rec": a.rec, "path": a.path,
            "env": a.env + a.opt + a.penv + ([a.display] if a.display else []), "wall": round(wall, 1), "ms": ms,
            "vms": vms, "log_mb": round(log.stat().st_size / 1e6, 1),
            "log_lines": sum(1 for _ in open(log, "rb")), "finished": res.finished, "cpu": round(m.cpu, 1),
            "peak_mb": round(m.peak / 1e6), "unthrottle": m.unthrottle,
            "ecore_share": round(on_e / max(1, sum(m.cores.values())), 2), "ecores": len(eset), **exe}
    (OUT / (a.name + ".json")).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding=ENC_W)
    turn = (re.search(r" turn=(\d+)", result) or [0, "?"])[1]
    how = (re.search(r" how=(\S+)", result) or [0, "?"])[1]
    print(f"{a.name}: всего {wall:.1f} с, бой {ms / 1000:.1f} с, ЦП {m.cpu:.1f} с, память {data['peak_mb']} МБ, "
          f"E-ядра {data['ecore_share']:.0%}, вирт. {vms / 1000:.0f} с, ход {turn} {how}, "
          f"лог {data['log_mb']} МБ / {data['log_lines']} строк")


if __name__ == "__main__":
    main()
