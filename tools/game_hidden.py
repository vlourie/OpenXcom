# Проверка игры НЕВИДИМО: свежий exe на копии сейва Пираток, на отдельном рабочем столе
# (ai_probe.Hidden) плюс SDL_VIDEODRIVER=dummy - окно игры на экране Vitali не появляется ни на миг (R-124).
# Щелчки, клавиши и дамп кадра делает сам движок (OXCE_HD_CLICK / OXCE_HD_KEY / OXCE_HD_DUMP).
# Щелчки - в пикселях базового экрана (R-103): при 1920x1080 и geoscapeScale 6 это дамп / 4.
#   py -3.13 tools/game_hidden.py --out E:/tmp/sell.png --save NoCodexCatZ.sav --after 100 --clicks "447,52;336,216"
# Показать игру на экране - только если Vitali сам попросил; этот скрипт так не умеет нарочно.
import argparse, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ai_probe
# вывод с кириллицей в трубу или файл без PYTHONIOENCODING падал в cp1252 (R-001, аудит 05.10)
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / "Пиратки" / "Dioxine_XPiratez"
EXE = ROOT / "build-release" / "bin" / "openxcom.exe"

a = argparse.ArgumentParser()
a.add_argument("--out", required=True, help="куда положить дамп кадра (png)")
a.add_argument("--save", default="NoCodexCatZ.sav", help="сейв из user/piratez установки; пусто - без сейва, до главного меню")
a.add_argument("--after", type=int, default=100, help="секунд до дампа (загрузка сейва ~60-90)")
a.add_argument("--clicks", default="")
a.add_argument("--key", default="")
a.add_argument("--set", default="", help="ключи options.cfg: a=1;b=false")
a.add_argument("--user", default=str(Path(tempfile.gettempdir()) / "oxce_hidden_user"))
a.add_argument("--exe", default=str(EXE), help="другая сборка - эталон для сравнения кадров")
a.add_argument("--mods-dir", default="", help="папка модов вместо user/mods установки (раскладка tools/compat/hd_layout.py)")
a.add_argument("--mods", default="", help="список модов options.cfg: id=true;id2=false (нет в списке - дописать в конец)")
a.add_argument("--master", default="", help="мастер-мод вместо записанного в options.cfg (x-com-files - XCF из --mods-dir)")
# с dummy-звуком Mix_OpenAudio падает и звуковой код не выполняется вовсе (AUDIO_ROADMAP.md);
# драйвер disk SDL 1.2 пишет всё, что сыграла игра, сырым PCM в файл
a.add_argument("--audio-disk", default="", help="файл для записи звука игры (драйвер disk); пусто - без звука")
o = a.parse_args()
EXE = Path(o.exe).resolve()

u = Path(o.user)
(u / "piratez").mkdir(parents=True, exist_ok=True)
mods_dir = Path(o.mods_dir).resolve() if o.mods_dir else GAME / "user" / "mods"
if (u / "mods").exists() and Path(os.path.realpath(u / "mods")) != Path(os.path.realpath(mods_dir)):
    os.rmdir(u / "mods")   # соединение на другую папку модов: снимается только связь (R-047)
if not (u / "mods").exists():
    # соединение на моды установки, а не копия (5 ГБ); снимать только rmdir (R-047)
    subprocess.run(["cmd", "/c", "mklink", "/J", str(u / "mods"), str(mods_dir)],
                   check=True, capture_output=True)
cfg = (GAME / "user" / "options.cfg").read_text(encoding="utf-8")
# всё, что спрашивает игрока или крутит камеру мышью человека (R-093, R-095)
fixed = {"battleEdgeScroll": "0", "oxceAdultAsk": "false", "playIntro": "false", "oxceGentleAsk": "false"}
for kv in filter(None, o.set.split(";")):
    n, v = kv.split("=", 1)
    fixed[n] = v
added = []
for n, v in fixed.items():
    cfg, k = re.subn(rf"(?m)^(\s*){n}: .*$", lambda m: f"{m.group(1)}{n}: {v}", cfg)
    if not k:
        added.append(f"  {n}: {v}")
if added:
    cfg = re.sub(r"(?m)^options:\s*$", "options:\n" + "\n".join(added), cfg, count=1)
for kv in filter(None, o.mods.split(";")):
    n, v = kv.split("=", 1)
    cfg, k = re.subn(rf"(?m)^(  - active: )\S+(\r?\n    id: {re.escape(n)}\r?)$", rf"\g<1>{v}\g<2>", cfg)
    if not k:
        cfg = re.sub(r"(?m)^options:\s*$", f"  - active: {v}\n    id: {n}\noptions:", cfg, count=1)
(u / "options.cfg").write_text(cfg, encoding="utf-8")
# имя - из user/piratez установки; путь к существующему файлу - своя копия сейва (установку не трогаем)
if o.save:
    save = Path(o.save) if Path(o.save).is_file() else GAME / "user" / "piratez" / o.save
    # игра читает сейвы из user/<мастер> (-master xcom1 - user/xcom1)
    (u / (o.master or "piratez")).mkdir(parents=True, exist_ok=True)
    shutil.copy(save, u / (o.master or "piratez") / "hiddentest.sav")

dump = Path(o.out).resolve()
if dump.exists():
    dump.unlink()
# ключи окружения в верхний регистр: Path и PATH вдвоём дают exe без DLL (код 0xC0000135)
env = {k.upper(): v for k, v in os.environ.items()}
env["PATH"] = "C:\\msys64\\mingw64\\bin;" + env.get("PATH", "")
env.update(SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy", OXCE_HD_DUMP=str(dump),
           OXCE_HD_DUMP_AFTER=str(o.after), OXCE_HD_CLICK=o.clicks, OXCE_HD_KEY=o.key)
if o.audio_disk:
    env.update(SDL_AUDIODRIVER="disk", SDL_DISKAUDIOFILE=str(Path(o.audio_disk).resolve()))
args = [str(EXE), "-data", str(GAME), "-user", str(u), "-cfg", str(u)] + (["-load", "hiddentest.sav"] if o.save else []) + (
        ["-master", o.master] if o.master else []) + [
        "-fullscreen", "false", "-borderless", "false", "-displayWidth", "1920", "-displayHeight", "1080",
        "-soundVolume", "100" if o.audio_disk else "0", "-musicVolume", "0", "-FPSInactive", "60"]
p = ai_probe.Hidden(args, str(EXE.parent), env)
print("pid", p.pid, "(скрытый рабочий стол)", flush=True)


def unthrottle(pid):
    """R-199: Windows 11 не держит timeBeginPeriod(1) процессу без видимого окна - SDL_Delay(1) спит тик 15,6 мс,
    кадр 16/31 мс (~42 к/с) то в одном прогоне, то в другом. У игрока окно видно: снимаем троттлинг, как у него -
    ProcessPowerThrottling (4), EXECUTION_SPEED | IGNORE_TIMER_RESOLUTION, StateMask 0."""
    import ctypes
    from ctypes import wintypes

    class PPT(ctypes.Structure):
        _fields_ = [("Version", wintypes.ULONG), ("ControlMask", wintypes.ULONG), ("StateMask", wintypes.ULONG)]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.SetProcessInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    h = k32.OpenProcess(0x0200 | 0x1000, False, pid)        # SET_INFORMATION | QUERY_LIMITED_INFORMATION
    if not h:
        return f"OpenProcess ошибка {ctypes.get_last_error()}"
    try:
        st = PPT(1, 0x1 | 0x4, 0)
        return "снят" if k32.SetProcessInformation(h, 4, ctypes.byref(st), ctypes.sizeof(st)) else \
            f"SetProcessInformation ошибка {ctypes.get_last_error()}"
    finally:
        k32.CloseHandle(h)


print("троттлинг таймера:", unthrottle(p.pid), flush=True)
t0 = time.time()
while p.poll() is None:
    ai_probe.hide_windows(p.pid)
    if time.time() - t0 > o.after + 60:
        subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
        print("таймаут")
        break
    time.sleep(0.2)
print("код", p.returncode)
print("дамп", dump if dump.exists() else "НЕТ")
log = (u / "openxcom.log").read_text(encoding="utf-8", errors="replace").splitlines()
for line in [l for l in log if re.search(r"\[ERROR\]|\[FATAL\]|not found|rash", l)][-10:]:
    print(line)
# R-384: Ctrl+F8 вне боя пишет только _frame.png (экран загрузки или геоскейп) - .json пишет лишь дамп боя
if "ctrl+289" in o.key:
    battle = [f for f in (u / (o.master or "piratez")).glob("hdtest*.json") if f.stat().st_mtime >= t0 - 5]
    if not battle:
        print(f"ДАМП НЕ ИЗ БОЯ (R-384): за {o.after} с бой не загрузился - нет hdtest*.json; больше --after или меньше прогонов разом")
        sys.exit(2)
sys.exit(0 if dump.exists() else 1)
