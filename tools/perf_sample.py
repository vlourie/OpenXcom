# Выборочный профиль работающей игры по функциям (R-091: прежде чем оптимизировать - доля функции в живой игре).
# Раз в --every мс останавливает поток, который с прошлого раза тратил процессор, снимает стек (dbghelp StackWalk64
# по .pdata exe) и продолжает поток. Лист стека в ожидании (кадровый ограничитель, пустая очередь работ) в доли
# работы не входит. Поток с Game::run в стеке - главный, остальные с адресами exe - рабочие (HdWorkers и др.).
# Имена: без --relink - таблица экспорта exe (--export-all-symbols: лямбды и static видны под именем ближайшей
# экспортированной функции перед ними - доверять только листам с понятным именем); с --relink - те же объекты
# build-release перелинкованы без -s в отдельный файл, имена по его таблице COFF (nm), .text сверяется с exe байт
# в байт - адреса те же. demangle - c++filt из MSYS2.
#   py -3.13 tools/perf_sample.py --stand A [--main] [--relink] [--secs 10] [--every 2] [--top 30] [--out файл.txt]
#   py -3.13 tools/perf_sample.py --pid N ...
# --main: только главный поток (он находится по Game::run в первом проходе) - выборок в разы больше.
# Свой процесс того же пользователя, права администратора не нужны. Остановка потока на ~50 мкс за выборку.
import argparse, bisect, collections, ctypes, hashlib, os, subprocess, sys, tempfile, time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MINGW = Path(r"C:/msys64/mingw64/bin")

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)
dbg = ctypes.WinDLL("dbghelp", use_last_error=True)
for f, res, args in (
        ("OpenProcess", wintypes.HANDLE, [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]),
        ("OpenThread", wintypes.HANDLE, [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]),
        ("SuspendThread", wintypes.DWORD, [wintypes.HANDLE]),
        ("ResumeThread", wintypes.DWORD, [wintypes.HANDLE]),
        ("GetThreadContext", wintypes.BOOL, [wintypes.HANDLE, ctypes.c_void_p]),
        ("QueryThreadCycleTime", wintypes.BOOL, [wintypes.HANDLE, ctypes.POINTER(ctypes.c_uint64)]),
        ("CloseHandle", wintypes.BOOL, [wintypes.HANDLE])):
    getattr(k32, f).restype, getattr(k32, f).argtypes = res, args
psapi.GetModuleFileNameExW.argtypes = [wintypes.HANDLE, wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
dbg.SymInitializeW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, wintypes.BOOL]
dbg.SymGetModuleBase64.restype = ctypes.c_uint64
dbg.SymGetModuleBase64.argtypes = [wintypes.HANDLE, ctypes.c_uint64]
dbg.SymFunctionTableAccess64.restype = ctypes.c_void_p
dbg.SymFunctionTableAccess64.argtypes = [wintypes.HANDLE, ctypes.c_uint64]
dbg.StackWalk64.argtypes = [wintypes.DWORD, wintypes.HANDLE, wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]


class SYMBOL_INFOW(ctypes.Structure):
    _fields_ = [("SizeOfStruct", wintypes.ULONG), ("TypeIndex", wintypes.ULONG), ("Reserved", ctypes.c_uint64 * 2),
                ("Index", wintypes.ULONG), ("Size", wintypes.ULONG), ("ModBase", ctypes.c_uint64),
                ("Flags", wintypes.ULONG), ("Value", ctypes.c_uint64), ("Address", ctypes.c_uint64),
                ("Register", wintypes.ULONG), ("Scope", wintypes.ULONG), ("Tag", wintypes.ULONG),
                ("NameLen", wintypes.ULONG), ("MaxNameLen", wintypes.ULONG), ("Name", wintypes.WCHAR * 2001)]


dbg.SymFromAddrW.argtypes = [wintypes.HANDLE, ctypes.c_uint64, ctypes.POINTER(ctypes.c_uint64), ctypes.c_void_p]
# лист стека в этих функциях - поток ждёт (кадровый ограничитель, пустая очередь работ), а не считает
IDLE = ("NtDelayExecution", "NtWaitFor", "NtRemoveIoCompletion", "ZwWaitFor", "ZwDelayExecution", "NtUserMsgWaitFor",
        "NtUserGetMessage", "NtUserPeekMessage", "NtYieldExecution", "NtAlertThreadByThreadId", "NtWaitForAlertByThreadId",
        "SwitchToThread", "SleepConditionVariable", "WaitOnAddress")
FTA = ctypes.cast(dbg.SymFunctionTableAccess64, ctypes.c_void_p)
GMB = ctypes.cast(dbg.SymGetModuleBase64, ctypes.c_void_p)

CTX_SIZE, CTX_FLAGS, CTX_RSP, CTX_RBP, CTX_RIP = 0x4D0, 0x30, 0x98, 0xA0, 0xF8
CONTEXT_FULL = 0x10000B
THREAD_ACCESS = 0x0002 | 0x0008 | 0x0040 | 0x0800   # suspend/resume, get context, query information (+limited)


def pe(path):
    """Разбор PE32+ без pefile: (ImageBase, {секция: (rva, размер, sha1)}, {rva: имя экспорта})."""
    b = Path(path).read_bytes()
    u16 = lambda o: int.from_bytes(b[o:o + 2], "little")
    u32 = lambda o: int.from_bytes(b[o:o + 4], "little")
    h = u32(0x3C)
    nsec, opt = u16(h + 6), h + 24
    secs = {}
    for i in range(nsec):
        s = opt + u16(h + 20) + 40 * i
        va, vsize, raw, rsize = u32(s + 12), u32(s + 8), u32(s + 20), u32(s + 16)
        secs[b[s:s + 8].rstrip(b"\0").decode()] = (va, vsize, raw, hashlib.sha1(b[raw:raw + min(vsize, rsize)]).hexdigest())

    def off(rva):
        for va, size, raw, _ in secs.values():
            if va <= rva < va + max(size, 1):
                return rva - va + raw
        raise ValueError(rva)

    e = off(u32(opt + 112))                         # каталог данных 0 - экспорт
    nnames, funcs, names, ords = u32(e + 24), off(u32(e + 28)), off(u32(e + 32)), off(u32(e + 36))
    exp = {}
    for i in range(nnames):
        n = off(u32(names + 4 * i))
        exp[u32(funcs + 4 * u16(ords + 2 * i))] = b[n:b.index(0, n)].decode("ascii", "replace")
    return int.from_bytes(b[opt + 24:opt + 32], "little"), secs, exp


def relink(out):
    """Объекты build-release тем же компоновщиком без -s (build.ninja: правило exe, $in, LINK_PATH, LINK_LIBRARIES)."""
    B = ROOT / "build-release"
    lines = (B / "build.ninja").read_text(encoding="utf-8").splitlines()
    i = next(n for n, l in enumerate(lines) if l.startswith("build bin/") and l.split(":")[0].endswith(".exe"))
    stmt = lines[i]
    while stmt.endswith("$"):
        i += 1
        stmt = stmt[:-1] + " " + lines[i].strip()
    ins = stmt.split(":", 1)[1].split("||")[0].split("|")[0].split()[1:]
    var = {}
    for l in lines[i + 1:]:
        if not l.startswith("  "):
            break
        k, _, v = l.strip().partition(" = ")
        var[k] = v
    rsp = out.with_suffix(".rsp")
    rsp.write_text(" ".join(ins + [var.get("LINK_PATH", ""), var.get("LINK_LIBRARIES", "")]), encoding="utf-8")
    flags = [f for f in var.get("FLAGS", "").split() + var.get("LINK_FLAGS", "").split() if f != "-s"]
    env = {**os.environ, "PATH": str(MINGW) + os.pathsep + os.environ["PATH"]}
    r = subprocess.run([str(MINGW / "c++.exe"), *flags, "@" + str(rsp), "-o", str(out)], cwd=B, capture_output=True,
                       text=True, env=env)
    if r.returncode:
        sys.exit("перелинковка не вышла: " + r.stderr[-1500:])


def coff_names(path, image_base):
    """rva -> имя по таблице символов (nm): функции, включая static и лямбды."""
    r = subprocess.run([str(MINGW / "nm.exe"), "--defined-only", str(path)], capture_output=True, text=True)
    out = {}
    for l in r.stdout.splitlines():
        p = l.split(" ", 2)
        if len(p) == 3 and p[1] in "Tt":
            out.setdefault(int(p[0], 16) - image_base, p[2])
    return out


def demangle(names):
    if not (MINGW / "c++filt.exe").exists():
        return {n: n for n in names}
    r = subprocess.run([str(MINGW / "c++filt.exe")], input="\n".join(names), capture_output=True, text=True)
    return dict(zip(names, r.stdout.splitlines()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid", type=int)
    ap.add_argument("--stand")
    ap.add_argument("--secs", type=float, default=10)
    ap.add_argument("--every", type=float, default=2, help="мс между выборками")
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--main", action="store_true", help="только главный поток")
    ap.add_argument("--relink", action="store_true", help="имена static и лямбд: exe с символами из тех же объектов")
    ap.add_argument("--focus", action="append", default=[], help="подстрока имени: кто её зовёт (3 кадра вверх)")
    ap.add_argument("--out")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    pid = a.pid or int((ROOT / "scratchpad" / "hdbench" / a.stand / "pid").read_text().split()[0])
    import psutil
    proc = psutil.Process(pid)
    exe = Path(proc.exe())
    image_base, secs, exp = pe(exe)
    names_by_rva = exp
    if a.relink:
        sym_exe = Path(tempfile.gettempdir()) / "perf_sample" / "openxcom_sym.bin"
        sym_exe.parent.mkdir(parents=True, exist_ok=True)
        relink(sym_exe)
        _, s2, _ = pe(sym_exe)
        if s2[".text"][3] != secs[".text"][3]:
            sys.exit(f"{exe} собран не из нынешних объектов build-release (.text различается) - имена были бы чужие")
        names_by_rva = coff_names(sym_exe, image_base)
    rvas = sorted(names_by_rva.items())
    keys = [r for r, _ in rvas]

    hp = k32.OpenProcess(0x0400 | 0x0010, False, pid)   # query information, read memory
    if not hp or not dbg.SymInitializeW(hp, None, True):
        sys.exit(f"нет доступа к процессу {pid}: {ctypes.get_last_error()}")
    exe_base = None
    modname = {}

    def where(addr):
        nonlocal exe_base
        base = dbg.SymGetModuleBase64(hp, addr)
        if not base:
            return "?"
        if base not in modname:
            buf = ctypes.create_unicode_buffer(520)
            psapi.GetModuleFileNameExW(hp, ctypes.c_void_p(base), buf, 520)
            modname[base] = Path(buf.value).name
            if Path(buf.value).name.lower() == exe.name.lower():
                exe_base = base
        if base != exe_base:
            sym = SYMBOL_INFOW()
            sym.SizeOfStruct, sym.MaxNameLen = ctypes.sizeof(SYMBOL_INFOW) - 2000 * 2, 2000
            disp = ctypes.c_uint64()
            if dbg.SymFromAddrW(hp, addr, ctypes.byref(disp), ctypes.byref(sym)):
                return "[" + modname[base] + "!" + sym.Name + "]"
            return "[" + modname[base] + "]"
        i = bisect.bisect_right(keys, addr - base) - 1
        return rvas[i][1] if i >= 0 else "?"

    raw = ctypes.create_string_buffer(CTX_SIZE + 16)
    ctx = (ctypes.addressof(raw) + 15) & ~15
    frame = ctypes.create_string_buffer(512)
    fa = ctypes.addressof(frame)
    handles, cycles = {}, {}

    def walk(tid):
        """Стек потока, если он с прошлого раза тратил процессор; иначе None."""
        h = handles.get(tid)
        if h is None:
            h = handles[tid] = k32.OpenThread(THREAD_ACCESS, False, tid)
        if not h:
            return None
        c = ctypes.c_uint64()
        k32.QueryThreadCycleTime(h, ctypes.byref(c))
        if cycles.get(tid) == c.value:
            return None                                    # поток спал - не процессор
        cycles[tid] = c.value
        if k32.SuspendThread(h) == 0xFFFFFFFF:
            return None
        st = []
        try:
            ctypes.memset(ctx, 0, CTX_SIZE)
            ctypes.c_uint32.from_address(ctx + CTX_FLAGS).value = CONTEXT_FULL
            if not k32.GetThreadContext(h, ctx):
                return None
            ctypes.memset(frame, 0, 512)
            for o, reg in ((0, CTX_RIP), (32, CTX_RBP), (48, CTX_RSP)):
                ctypes.c_uint64.from_address(fa + o).value = ctypes.c_uint64.from_address(ctx + reg).value
                ctypes.c_uint32.from_address(fa + o + 12).value = 3   # AddrModeFlat
            while len(st) < 64 and dbg.StackWalk64(0x8664, hp, h, fa, ctx, None, FTA, GMB, None):
                pc = ctypes.c_uint64.from_address(fa).value
                if not pc:
                    break
                st.append(pc)
        finally:
            k32.ResumeThread(h)
        return tuple(st) or None

    tids = [th.id for th in proc.threads()]
    if a.main:
        game_run = next((r for r, n in exp.items() if n == "_ZN8OpenXcom4Game3runEv"), None)
        main_tid, t_find = None, time.perf_counter() + 5
        while main_tid is None and time.perf_counter() < t_find:
            for tid in tids:
                cycles.pop(tid, None)
                st = walk(tid)
                if st and game_run is not None and exe_base is None:
                    for pc in st:
                        where(pc)
                if st and exe_base and any(0 <= pc - exe_base - game_run < 0x4000 for pc in st):
                    main_tid = tid
                    break
        if main_tid is None:
            sys.exit("главный поток (Game::run) не найден")
        tids = [main_tid]

    stacks = collections.defaultdict(collections.Counter)   # tid -> Counter(кортеж адресов)
    t_end = time.perf_counter() + a.secs
    while time.perf_counter() < t_end:
        if not a.main:
            tids = [th.id for th in proc.threads()]
        for tid in tids:
            st = walk(tid)
            if st:
                stacks[tid][st] += 1
        time.sleep(a.every / 1000)

    names_cache = {}

    def name(pc):
        if pc not in names_cache:
            names_cache[pc] = where(pc)
        return names_cache[pc]

    # адрес возврата смотрит на команду после call - имя берём по адресу на байт раньше
    sym = {tid: {st: [name(pc if i == 0 else pc - 1) for i, pc in enumerate(st)] for st in c} for tid, c in stacks.items()}
    dem = demangle(sorted({n for d in sym.values() for l in d.values() for n in l}))
    groups = collections.defaultdict(lambda: (collections.Counter(), collections.Counter(), [0, 0]))
    focus = {f: collections.Counter() for f in a.focus}
    for tid, c in stacks.items():
        for st, n in c.items():
            names = [dem[x] for x in sym[tid][st]]
            if any(t in names[0] for t in IDLE):
                continue
            for f, cnt in focus.items():
                i = next((j for j, x in enumerate(names) if f in x), None)
                if i is not None:
                    cnt[" <- ".join(x.split("(")[0] for x in names[i:i + 4])] += n
        all_names = {dem[n] for l in sym[tid].values() for n in l}
        g = "главный" if any("Game::run" in n for n in all_names) else (
            "рабочие" if any(not n.startswith("[") for n in all_names) else "чужие (без exe)")
        selfc, incl, tot = groups[g]
        for st, n in c.items():
            names = [dem[x] for x in sym[tid][st]]
            tot[1] += n
            if any(t in names[0] for t in IDLE):
                continue                                   # ждёт - в доли работы не входит
            selfc[names[0]] += n
            for x in set(names):
                incl[x] += n
            tot[0] += n
    lines = [f"{exe.name} pid {pid}: {a.secs} с, выборка раз в {a.every} мс; имена: "
             f"{'COFF перелинковки' if a.relink else 'экспорт'}; потоков с процессором {len(stacks)}"]
    for g, (selfc, incl, tot) in sorted(groups.items()):
        n = max(tot[0], 1)
        lines.append(f"\n== {g}: выборок {tot[1]}, из них работа {tot[0]} ({100 * tot[0] / max(tot[1], 1):.0f}%); "
                     "доли ниже - от работы")
        lines.append("-- своё время (лист стека)")
        lines += [f"{100 * v / n:6.1f}%  {k[:160]}" for k, v in selfc.most_common(a.top)]
        lines.append("-- с вызванными (функция в стеке)")
        lines += [f"{100 * v / n:6.1f}%  {k[:160]}" for k, v in incl.most_common(a.top)]
    work = sum(g[2][0] for g in groups.values()) or 1
    for f, cnt in focus.items():
        lines.append(f"\n-- кто зовёт «{f}» (доля от всей работы снятых потоков)")
        lines += [f"{100 * v / work:6.1f}%  {k[:220]}" for k, v in cnt.most_common(12)]
    text = "\n".join(lines)
    print(text)
    if a.out:
        Path(a.out).write_text(text + "\n", encoding="utf-8-sig")
    for h in handles.values():
        if h:
            k32.CloseHandle(h)


if __name__ == "__main__":
    main()
