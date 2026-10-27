# Живой стенд проверок OXCE-HD: одна загрузка игры - сколько угодно кадров (docs/research/hd-test-bench-2026-10-26.md).
# Игра запускается невидимо (hidden_game: скрытый стол, SDL dummy) с OXCE_HD_CONTROL=<папка стенда> и не выходит
# после кадра: каждые 100 мс смотрит <папка>/cmd.txt, исполняет команды по одной за кадр и пишет <папка>/done.<n>.
# Папка стенда - scratchpad/hdbench/<имя>/ (pid, cmd.*, done.*). Без OXCE_HD_CONTROL движок ничего этого не делает.
#
#   py -3.13 tools/hdbench.py start --name A [--exe путь] [--save NoCodexCatZ.sav|""] [--set k=v;...] [--user папка]
#   py -3.13 tools/hdbench.py run --name A "click 447,52; wait 1500; shot E:/tmp/base.png"
#   py -3.13 tools/hdbench.py run --name A --file script.txt
#   py -3.13 tools/hdbench.py stop --name A        |   list   |   log --name A [-n 40]
#
# Команды (по одной в строке или через ';' в аргументе; '#' - комментарий). Координаты - пиксели БАЗОВОГО экрана (R-103):
#   click|rclick|mclick|hover [ctrl+]x,y     wheel [ctrl+]up|down x,y      key [ctrl+|shift+|alt+]N|имя|fN (289 = F8)
#   type текст     wait мс     shot файл.png (путь латиницей)     state     reinit     quit
#   record папка кадров fps [night от до]   ролик: кадры f00000.png.. подряд, часы картинок базы (HdControl::ticks)
#                        шагают на 1000/fps за кадр, а не по стенке - без рывков; night - ночь «Живой базы» от и до
#                        (0..1) за ролик; склейка: ffmpeg -framerate fps -i папка/f%05d.png -c:v libx264 -pix_fmt yuv420p
#   waitstate Имя [мс]   ждать, пока наверху стека класс Имя (окно, которое игра открывает по своему таймеру, например
#                        CraftErrorState после загрузки NoCodexCatZ.sav: сразу после start наверху ещё GeoscapeState)
#   set ключ=значение [ключ=значение...]   любая опция игры (oxceHdWoundedRed=true), k=N - масштаб мира; затем сброс экрана
#   load имя.sav|путь   сейв без перезагрузки модов (чужой файл копируется в папку пользователя стенда)
#   open geoscape|base|battle|load|newbattle|options|save|ufopaedia   тот же переход, что OXCE_HD_START
# Параметры, зависящие от ';': type с ';' и пара set с пробелом в значении - только через --file.
# Кадр после щелчка: между щелчком и shot движок сам выдерживает 3 нарисованных кадра; анимации и наезды камеры
# (R-450) - явным wait. Несколько стендов (эталонный и новый exe) - разные --name.
# Код возврата run: 0 - все ok, 1 - есть err, 2 - стенд мёртв или не ответил за срок.
import argparse, json, os, shutil, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ai_probe
import hidden_game
from hidden_game import GAME, ROOT

STANDS = ROOT / "scratchpad" / "hdbench"
# игра ещё грузит моды или сейв: эти экраны наверху - не готова
LOADING = ("StartState", "LoadGameState", "ListLoadState", "GoToMainMenuState", "none")


class Dead(Exception):
    pass


def sdir(name):
    return STANDS / name


def read_pid(name):
    try:
        return int((sdir(name) / "pid").read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return None


def pid_alive(pid):
    if not pid:
        return False
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    h = k32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    try:
        code = wintypes.DWORD()
        return bool(k32.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == 259   # STILL_ACTIVE
    finally:
        k32.CloseHandle(h)


def meta(name):
    try:
        return json.loads((sdir(name) / "meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def kill(pid):
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)   # свой pid, деревом (R-073)


def last_n(d):
    """Наибольший номер пачки, который движок уже взял (cmd.<n>.run) или закончил (done.<n>)."""
    n = 0
    for f in d.iterdir():
        parts = f.name.split(".")
        if len(parts) >= 2 and parts[0] in ("cmd", "done") and parts[1].isdigit():
            n = max(n, int(parts[1]))
    return n


def sanitize(lines, name):
    """Подготовка строк: папка для shot, чужой сейв для load. Возвращает (строки, срок в секундах)."""
    out, timeout = [], 60.0
    m = meta(name)
    master = m.get("master") or "piratez"
    for line in lines:
        cmd, _, arg = line.partition(" ")
        arg = arg.strip()
        if cmd == "shot" and arg:
            if not arg.isascii():
                raise SystemExit(f"shot: путь латиницей (игра пишет файл через ANSI-вызов): {arg}")
            Path(arg).parent.mkdir(parents=True, exist_ok=True)
        elif cmd == "record" and arg:
            parts = arg.split()
            if not parts[0].isascii():
                raise SystemExit(f"record: папка латиницей (игра пишет файлы через ANSI-вызов): {parts[0]}")
            Path(parts[0]).mkdir(parents=True, exist_ok=True)
            # кадр 1920x1080 пишется в PNG за десятки мс; с запасом - секунда на кадр
            timeout += int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        elif cmd == "wait":
            timeout += int(arg or 0) / 1000
        elif cmd == "waitstate":
            parts = arg.split()
            timeout += (int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 30000) / 1000
        elif cmd == "load" and arg:
            src = Path(arg) if Path(arg).is_file() else GAME / "user" / master / arg
            if src.is_file() and m.get("user"):
                dst = Path(m["user"]) / master / src.name
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dst)
                line = f"load {src.name}"
            timeout += 300
        elif cmd == "open":
            timeout += 300
        out.append(line)
    return out, timeout


def parse_script(text):
    lines = []
    for raw in text.replace("\r", "").split("\n"):
        raw = raw.strip()
        if raw.startswith("type ") or raw.startswith("#"):   # type - строка целиком, с ';'
            lines.append(raw)
            continue
        lines += [p.strip() for p in raw.split(";")]
    return [l for l in lines if l and not l.startswith("#")]


class Busy:
    """Стенд ведёт один клиент: файл busy с pid клиента."""

    def __init__(self, name):
        self.path = sdir(name) / "busy"

    def __enter__(self):
        if self.path.exists():
            try:
                other = int(self.path.read_text().split()[0])
            except (OSError, ValueError, IndexError):
                other = 0
            if other != os.getpid() and pid_alive(other):
                raise SystemExit(f"стенд занят другим клиентом (pid {other}); подожди или stop")
        self.path.write_text(str(os.getpid()))
        return self

    def __exit__(self, *a):
        try:
            self.path.unlink()
        except OSError:
            pass


def send(name, lines, timeout):
    """Кладёт пачку и ждёт done.<n>. Возвращает (результаты по строкам, секунд). Dead - игра умерла, TimeoutError - не ответила."""
    d = sdir(name)
    pid = read_pid(name)
    if not pid_alive(pid):
        raise Dead(f"стенд {name} не запущен или игра закрылась (pid {pid})")
    stale = d / "cmd.txt"
    if stale.exists():   # пачка прошлого клиента, которую игра так и не взяла
        stale.unlink()
    n = last_n(d) + 1
    tmp = d / "cmd.tmp"
    tmp.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    os.replace(tmp, stale)   # игра никогда не видит половину файла
    done = d / f"done.{n}"
    t0 = time.perf_counter()
    last_check = 0.0
    while True:
        if done.exists():
            try:
                text = done.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:   # игра как раз переименовывает файл (Windows не даёт читать)
                text = []
            if text and text[-1] == "end":
                return text[:-1], time.perf_counter() - t0
        now = time.perf_counter()
        if now - t0 > timeout:
            raise TimeoutError(f"стенд {name}: нет ответа за {timeout:.0f} с (done.{n})")
        if now - last_check > 1.0:
            last_check = now
            if not pid_alive(pid):
                raise Dead(f"игра стенда {name} закрылась во время пачки (pid {pid}); смотри log --name {name}")
            ai_probe.hide_windows(pid)
        time.sleep(0.03)


def show_log(name, n=40):
    m = meta(name)
    log = Path(m.get("user", "")) / "openxcom.log"
    if not log.exists():
        print("лога нет")
        return
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]:
        print(line)


def cmd_start(a):
    name = a.name
    d = sdir(name)
    if pid_alive(read_pid(name)):
        raise SystemExit(f"стенд {name} уже работает (pid {read_pid(name)}); stop или другое имя")
    if d.exists():
        for f in d.iterdir():
            if f.is_file():
                f.unlink()
    d.mkdir(parents=True, exist_ok=True)
    exe = Path(a.exe).resolve()
    # resolved here: the game runs from its own folder and would look for a relative path there
    user = Path(a.user).resolve() if a.user else Path(os.environ.get("TEMP", ".")) / f"oxce_bench_{name}"
    log = user / "openxcom.log"
    if log.exists():
        log.unlink()   # лог этого запуска, а не прошлого (R-246)
    hidden_game.prepare_user(user, a.mods_dir, a.set, a.mods, a.save, a.master)
    env = hidden_game.game_env(OXCE_HD_CONTROL=d)
    t0 = time.perf_counter()
    p = hidden_game.launch(exe, hidden_game.game_args(exe, user, load=bool(a.save), master=a.master), env)
    (d / "pid").write_text(str(p.pid))
    (d / "meta.json").write_text(json.dumps({"exe": str(exe), "user": str(user), "master": a.master, "save": a.save,
                                             "started": time.time()}, ensure_ascii=False), encoding="utf-8")
    print(f"стенд {name}: pid {p.pid}, троттлинг таймера: {hidden_game.unthrottle(p.pid)}", flush=True)
    with Busy(name):
        while True:
            if p.poll() is not None:
                show_log(name, 15)
                raise SystemExit(f"игра закрылась при запуске, код {p.returncode}")
            if time.perf_counter() - t0 > a.timeout:
                kill(p.pid)
                raise SystemExit(f"стенд {name}: не готов за {a.timeout} с, игра снята")
            try:
                res, _ = send(name, ["state"], timeout=30)
            except TimeoutError:
                ai_probe.hide_windows(p.pid)   # игра грузит моды: кадров нет, команда ждёт
                continue
            top = (res[0].split() + ["", ""])[1] if res else ""
            ready = top == "MainMenuState" if not a.save else top not in LOADING + ("MainMenuState",)
            if ready:
                print(f"готов за {time.perf_counter() - t0:.1f} с: {res[0]}")
                return 0
            time.sleep(0.5)


def cmd_run(a):
    text = Path(a.file).read_text(encoding="utf-8-sig") if a.file else "\n".join(a.script)
    lines = parse_script(text)
    if not lines:
        raise SystemExit("пустой сценарий")
    lines, timeout = sanitize(lines, a.name)
    timeout = a.timeout or timeout
    with Busy(a.name):
        try:
            res, secs = send(a.name, lines, timeout)
        except (Dead, TimeoutError) as e:
            print(e)
            return 2
    bad = 0
    for i, line in enumerate(lines):
        r = res[i] if i < len(res) else "(нет ответа)"
        bad += r.startswith("err") or r.startswith("(нет")
        print(f"  {line}  ->  {r}")
    print(f"пачка из {len(lines)}: {secs:.2f} с" + (f", ошибок {bad}" if bad else ""))
    return 1 if bad else 0


def cmd_stop(a):
    pid = read_pid(a.name)
    if pid_alive(pid):
        try:
            with Busy(a.name):
                send(a.name, ["quit"], 20)
        except (Dead, TimeoutError, SystemExit):
            pass
        t0 = time.time()
        while pid_alive(pid) and time.time() - t0 < 30:
            time.sleep(0.2)
        if pid_alive(pid):
            kill(pid)
            print(f"стенд {a.name}: не вышел за 30 с, снят (pid {pid})")
        else:
            print(f"стенд {a.name}: вышел")
    else:
        print(f"стенд {a.name}: не работает")
    try:
        (sdir(a.name) / "pid").unlink()
    except OSError:
        pass
    return 0


def cmd_list(a):
    found = False
    if STANDS.exists():
        for d in sorted(STANDS.iterdir()):
            pid = read_pid(d.name)
            if pid is None:
                continue
            m = meta(d.name)
            alive = pid_alive(pid)
            found = found or alive
            age = (time.time() - m.get("started", time.time())) / 60
            print(f"{d.name}: pid {pid}, {'жив' if alive else 'нет'}, {age:.0f} мин, {m.get('exe', '?')}")
    if not found:
        print("живых стендов нет")
    return 0


def main():
    hidden_game.utf8_streams()
    ap = argparse.ArgumentParser(description="Живой стенд проверок OXCE-HD")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start")
    s.add_argument("--name", required=True)
    s.add_argument("--exe", default=str(hidden_game.EXE))
    s.add_argument("--save", default="NoCodexCatZ.sav", help="сейв установки или путь; пусто - главное меню")
    s.add_argument("--set", default="", help="опции игры: a=1;b=false")
    s.add_argument("--user", default="", help="папка пользователя стенда (по умолчанию %TEMP%/oxce_bench_<имя>)")
    s.add_argument("--mods-dir", default="")
    s.add_argument("--mods", default="")
    s.add_argument("--master", default="")
    s.add_argument("--timeout", type=int, default=600)
    r = sub.add_parser("run")
    r.add_argument("--name", required=True)
    r.add_argument("--file", default="")
    r.add_argument("--timeout", type=int, default=0, help="сек; по умолчанию 60 + сумма wait (+300 на load/open)")
    r.add_argument("script", nargs="*")
    for n in ("stop", "log"):
        x = sub.add_parser(n)
        x.add_argument("--name", required=True)
        if n == "log":
            x.add_argument("-n", type=int, default=40)
    sub.add_parser("list")
    a = ap.parse_args()
    if a.cmd == "log":
        show_log(a.name, a.n)
        return 0
    return {"start": cmd_start, "run": cmd_run, "stop": cmd_stop, "list": cmd_list}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
