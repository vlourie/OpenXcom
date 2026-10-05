#!/usr/bin/env python3
"""По одному стеку КАЖДОГО потока идущего процесса игры (повисшего, R-150).

  py -3.13 tools/ai_speed/attach_all.py <pid> <имя> <сборка>

Итог: runs/<имя>.samples.json (фаза hang, по выборке на поток) - смотреть hang_stack.py"""
import ctypes, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import prof_battle as pb
from _common import OUT, ENC_W

sys.stdout.reconfigure(encoding="utf-8")  # R-001
pid, name, build = int(sys.argv[1]), sys.argv[2], sys.argv[3]
k32, dbghelp = pb.k32, pb.dbghelp
hproc = k32.OpenProcess(pb.PROCESS_ALL, False, pid)
if not hproc:
    sys.exit("OpenProcess не дал доступа")
dbghelp.SymInitializeW(hproc, None, True)
mods = pb.modules(hproc)
raw = ctypes.create_string_buffer(1232 + 32)
ctx = (ctypes.addressof(raw) + 15) & ~15
fta = ctypes.cast(dbghelp.SymFunctionTableAccess64, ctypes.c_void_p)
gmb = ctypes.cast(dbghelp.SymGetModuleBase64, ctypes.c_void_p)
samples = []
th = pb.threads(pid)
for tid, created, kt, ut in th:
    hth = k32.OpenThread(pb.THREAD_ALL, False, tid)
    if not hth or k32.SuspendThread(hth) == 0xFFFFFFFF:
        print(f"поток {tid}: нет доступа")
        continue
    ctypes.memset(ctx, 0, 1232)
    ctypes.c_uint32.from_address(ctx + 48).value = 0x100003
    stack = []
    if k32.GetThreadContext(hth, ctx):
        rip = ctypes.c_uint64.from_address(ctx + 248).value
        sf = pb.STACKFRAME64()
        sf.AddrPC.Offset, sf.AddrPC.Mode = rip, 3
        sf.AddrFrame.Offset, sf.AddrFrame.Mode = ctypes.c_uint64.from_address(ctx + 160).value, 3
        sf.AddrStack.Offset, sf.AddrStack.Mode = ctypes.c_uint64.from_address(ctx + 152).value, 3
        for _ in range(64):
            if not dbghelp.StackWalk64(0x8664, hproc, hth, ctypes.byref(sf), ctx, None, fta, gmb, None):
                break
            if not sf.AddrPC.Offset:
                break
            stack.append(sf.AddrPC.Offset)
        stack = stack or [rip]
    k32.ResumeThread(hth)
    k32.CloseHandle(hth)
    print(f"поток {tid}: создан +{created - th[0][1]:.2f} с, ЦП {kt + ut:.2f} с, кадров {len(stack)}")
    # у каждого потока свой стек: чтобы hang_stack.py показал все, метка потока идёт первым «адресом»
    samples.append(("hang", stack + [tid]))
data = {"mission": "-", "seed": 0, "build": build, "record": 0, "env": [], "wall": 0, "interval": 0.02, "mods": mods,
        "cpu": th, "fail": 0, "walk_s": 0, "result": [], "finished": False, "samples": samples}
OUT.mkdir(exist_ok=True)
(OUT / (name + ".samples.json")).write_text(json.dumps(data), encoding=ENC_W)
