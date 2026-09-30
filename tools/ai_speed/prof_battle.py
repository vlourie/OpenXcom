#!/usr/bin/env python3
"""Выборочный профиль одного боя стенда: главный поток игры останавливается каждые несколько мс,
снимается стек (StackWalk64 по таблицам .pdata), имена - из nm. Игра идёт как в серии: скрытый стол, SDL dummy.

py -3.13 tools/ai_speed/prof_battle.py --mission STR_VESSEL_SOTL_SECTOID_ELITE --seed 201 --name prof_sotl --record 1
Итог: <name>.samples.json (сырые стеки) и отчёт в stdout (prof_report.py печатает его заново из json)."""
import argparse, bisect, ctypes, json, os, subprocess, sys, threading, time
from ctypes import wintypes
from pathlib import Path

from _common import ROOT, OUT, ENC_R, ENC_W, build_dir, nm_exe


k32 = ctypes.WinDLL("kernel32", use_last_error=True)
dbghelp = ctypes.WinDLL("dbghelp", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)

TH32CS_SNAPTHREAD = 0x4
THREAD_ALL = 0x1FFFFF
PROCESS_ALL = 0x1FFFFF


class THREADENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ThreadID", wintypes.DWORD),
                ("th32OwnerProcessID", wintypes.DWORD), ("tpBasePri", wintypes.LONG), ("tpDeltaPri", wintypes.LONG),
                ("dwFlags", wintypes.DWORD)]


class ADDRESS64(ctypes.Structure):
    _fields_ = [("Offset", ctypes.c_uint64), ("Segment", wintypes.WORD), ("Mode", ctypes.c_int)]


class KDHELP64(ctypes.Structure):
    _fields_ = [("Thread", ctypes.c_uint64), ("ThCallbackStack", wintypes.DWORD), ("ThCallbackBStore", wintypes.DWORD),
                ("NextCallback", wintypes.DWORD), ("FramePointer", wintypes.DWORD), ("KiCallUserMode", ctypes.c_uint64),
                ("KeUserCallbackDispatcher", ctypes.c_uint64), ("SystemRangeStart", ctypes.c_uint64),
                ("KiUserExceptionDispatcher", ctypes.c_uint64), ("StackBase", ctypes.c_uint64),
                ("StackLimit", ctypes.c_uint64), ("BuildVersion", wintypes.DWORD),
                ("RetpolineStubFunctionTableSize", wintypes.DWORD), ("RetpolineStubFunctionTable", ctypes.c_uint64),
                ("RetpolineStubOffset", wintypes.DWORD), ("RetpolineStubSize", wintypes.DWORD),
                ("Reserved0", ctypes.c_uint64 * 2), ("pad", ctypes.c_uint64 * 8)]


class STACKFRAME64(ctypes.Structure):
    _fields_ = [("AddrPC", ADDRESS64), ("AddrReturn", ADDRESS64), ("AddrFrame", ADDRESS64), ("AddrStack", ADDRESS64),
                ("AddrBStore", ADDRESS64), ("FuncTableEntry", ctypes.c_void_p), ("Params", ctypes.c_uint64 * 4),
                ("Far", wintypes.BOOL), ("Virtual", wintypes.BOOL), ("Reserved", ctypes.c_uint64 * 3),
                ("KdHelp", KDHELP64)]


class MODULEINFO(ctypes.Structure):
    _fields_ = [("lpBaseOfDll", ctypes.c_void_p), ("SizeOfImage", wintypes.DWORD), ("EntryPoint", ctypes.c_void_p)]


k32.OpenProcess.restype = wintypes.HANDLE
k32.OpenThread.restype = wintypes.HANDLE
k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
k32.GetThreadContext.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
k32.SuspendThread.argtypes = [wintypes.HANDLE]
k32.ResumeThread.argtypes = [wintypes.HANDLE]
k32.GetThreadTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
dbghelp.SymInitializeW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, wintypes.BOOL]
dbghelp.SymRefreshModuleList.argtypes = [wintypes.HANDLE]
dbghelp.StackWalk64.argtypes = [wintypes.DWORD, wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(STACKFRAME64),
                                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
dbghelp.StackWalk64.restype = wintypes.BOOL
psapi.EnumProcessModules.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p), wintypes.DWORD,
                                     ctypes.POINTER(wintypes.DWORD)]
psapi.GetModuleBaseNameW.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.LPWSTR, wintypes.DWORD]
psapi.GetModuleInformation.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(MODULEINFO), wintypes.DWORD]


def ft(v):
    return ((v.dwHighDateTime << 32) | v.dwLowDateTime) / 1e7


def threads(pid):
    """Потоки процесса: (tid, время создания, время ЦП)."""
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
    te = THREADENTRY32()
    te.dwSize = ctypes.sizeof(te)
    out = []
    ok = k32.Thread32First(snap, ctypes.byref(te))
    while ok:
        if te.th32OwnerProcessID == pid:
            h = k32.OpenThread(THREAD_ALL, False, te.th32ThreadID)
            if h:
                c, e, kt, ut = (wintypes.FILETIME() for _ in range(4))
                k32.GetThreadTimes(h, ctypes.byref(c), ctypes.byref(e), ctypes.byref(kt), ctypes.byref(ut))
                out.append((te.th32ThreadID, ft(c), ft(kt), ft(ut)))
                k32.CloseHandle(h)
        ok = k32.Thread32Next(snap, ctypes.byref(te))
    k32.CloseHandle(snap)
    return sorted(out, key=lambda t: t[1])


def modules(hproc):
    need = wintypes.DWORD(0)
    arr = (ctypes.c_void_p * 512)()
    psapi.EnumProcessModules(hproc, arr, ctypes.sizeof(arr), ctypes.byref(need))
    out = []
    for i in range(min(512, need.value // ctypes.sizeof(ctypes.c_void_p))):
        name = ctypes.create_unicode_buffer(260)
        psapi.GetModuleBaseNameW(hproc, arr[i], name, 260)
        mi = MODULEINFO()
        psapi.GetModuleInformation(hproc, arr[i], ctypes.byref(mi), ctypes.sizeof(mi))
        out.append((mi.lpBaseOfDll or 0, mi.SizeOfImage, name.value))
    return sorted(out)


class Sampler(threading.Thread):
    def __init__(self, pid, log, interval, depth=64):
        super().__init__(daemon=True)
        self.pid, self.log, self.interval, self.depth = pid, Path(log), interval, depth
        self.samples = []      # (фаза, [адреса от листа к корню])
        self.mods = []
        self.stop = False
        self.phase = "load"
        self.cpu = []
        self.fail = 0
        self.walk_s = 0.0

    def run(self):
        hproc = k32.OpenProcess(PROCESS_ALL, False, self.pid)
        if not hproc:
            print("OpenProcess не дал доступа", ctypes.get_last_error())
            return
        time.sleep(1.0)  # загрузчик должен разложить DLL
        if not dbghelp.SymInitializeW(hproc, None, True):
            print("SymInitialize: ошибка", ctypes.get_last_error())
        th = threads(self.pid)
        if not th:
            return
        tid = th[0][0]  # главный поток - самый ранний
        hth = k32.OpenThread(THREAD_ALL, False, tid)
        raw = ctypes.create_string_buffer(1232 + 32)
        ctx = (ctypes.addressof(raw) + 15) & ~15
        fta = ctypes.cast(dbghelp.SymFunctionTableAccess64, ctypes.c_void_p)
        gmb = ctypes.cast(dbghelp.SymGetModuleBase64, ctypes.c_void_p)
        n = 0
        logpos = 0
        nxt = time.perf_counter()
        while not self.stop:
            now = time.perf_counter()
            if now < nxt:
                time.sleep(min(0.002, nxt - now))
                continue
            nxt = now + self.interval
            if k32.WaitForSingleObject(hproc, 0) == 0:
                break
            n += 1
            if n % 200 == 1:
                self.mods = modules(hproc) or self.mods
                dbghelp.SymRefreshModuleList(hproc)
                self.cpu = threads(self.pid) or self.cpu
                if self.phase == "load":
                    try:
                        with open(self.log, "rb") as f:
                            f.seek(logpos)
                            chunk = f.read()
                        if b"[AIPROBE] start" in chunk or b"[AIPROBE] battle" in chunk:
                            self.phase = "battle"
                        logpos += max(0, len(chunk) - 64)
                    except OSError:
                        pass
            t0 = time.perf_counter()
            if k32.SuspendThread(hth) == 0xFFFFFFFF:
                self.fail += 1
                continue
            ctypes.memset(ctx, 0, 1232)
            ctypes.c_uint32.from_address(ctx + 48).value = 0x100003  # CONTEXT_CONTROL | CONTEXT_INTEGER
            stack = []
            if k32.GetThreadContext(hth, ctx):
                rip = ctypes.c_uint64.from_address(ctx + 248).value
                rsp = ctypes.c_uint64.from_address(ctx + 152).value
                rbp = ctypes.c_uint64.from_address(ctx + 160).value
                sf = STACKFRAME64()
                sf.AddrPC.Offset, sf.AddrPC.Mode = rip, 3
                sf.AddrFrame.Offset, sf.AddrFrame.Mode = rbp, 3
                sf.AddrStack.Offset, sf.AddrStack.Mode = rsp, 3
                for _ in range(self.depth):
                    if not dbghelp.StackWalk64(0x8664, hproc, hth, ctypes.byref(sf), ctx, None, fta, gmb, None):
                        break
                    if not sf.AddrPC.Offset:
                        break
                    stack.append(sf.AddrPC.Offset)
                if not stack:
                    stack = [rip]
            else:
                self.fail += 1
            k32.ResumeThread(hth)
            self.walk_s += time.perf_counter() - t0
            if stack:
                self.samples.append((self.phase, stack))
        self.cpu = threads(self.pid) or self.cpu
        k32.CloseHandle(hth)
        k32.CloseHandle(hproc)


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # R-001
    ap = argparse.ArgumentParser()
    ap.add_argument("--mission", required=True)
    ap.add_argument("--seed", type=int, default=201)
    ap.add_argument("--name", default="prof")
    ap.add_argument("--build", default="build-ai36")
    ap.add_argument("--record", type=int, default=1)
    ap.add_argument("--turns", type=int, default=60)
    ap.add_argument("--interval", type=float, default=0.004)
    ap.add_argument("--env", action="append", default=[])
    a = ap.parse_args()

    os.environ["OXCE_AI_BUILD"] = a.build
    if a.record:
        os.environ["OXCE_AI_RECORD"] = "1"
        os.environ["OXCE_AI_RECORD_PATH"] = "1"
    for kv in a.env:
        k, v = kv.split("=", 1)
        os.environ[k] = v
    sys.path.insert(0, str(ROOT / "tools"))
    import ai_probe

    holder = {}
    base_hidden = ai_probe.Hidden

    class Profiled(base_hidden):
        def __init__(self, args, cwd, env):
            super().__init__(args, cwd, env)
            s = Sampler(self.pid, ai_probe.WORK / ("prof_" + a.name) / "openxcom.log", a.interval)
            holder["s"] = s
            s.start()

    ai_probe.Hidden = Profiled
    t0 = time.time()
    res = ai_probe.run(None, a.turns, name="prof_" + a.name, timeout=1500, bot=True, seed=a.seed,
                       campaign="NoCodexCatZ.sav", mission=a.mission, careful=True, squad=8)
    wall = time.time() - t0
    s = holder["s"]
    s.stop = True
    s.join(5)
    result = [l for l in res.lines if l.startswith(("[AIRESULT]", "[AIPROBE] battle"))]
    data = {"mission": a.mission, "seed": a.seed, "build": a.build, "record": a.record, "env": a.env, "wall": wall,
            "interval": a.interval, "mods": s.mods, "cpu": s.cpu, "fail": s.fail, "walk_s": s.walk_s,
            "result": result, "finished": res.finished, "samples": s.samples}
    OUT.mkdir(exist_ok=True)
    out = OUT / (a.name + ".samples.json")
    out.write_text(json.dumps(data), encoding=ENC_W)
    print(f"бой {a.mission} зерно {a.seed}: {wall:.1f} с, выборок {len(s.samples)}, сбоев {s.fail}, "
          f"поток стоял {s.walk_s:.1f} с; {out}")
    for l in result:
        print(l)


if __name__ == "__main__":
    main()
