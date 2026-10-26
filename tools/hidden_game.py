# Общие куски невидимого запуска игры: game_hidden.py (один кадр) и hdbench.py (живой стенд).
# Игра на скрытом рабочем столе (ai_probe.Hidden) + SDL_VIDEODRIVER=dummy: окно на экране Vitali не появляется (R-124).
import os, re, shutil, subprocess, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ai_probe

ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / "Пиратки" / "Dioxine_XPiratez"
EXE = ROOT / "build-release" / "bin" / "openxcom.exe"
DEFAULT_USER = Path(tempfile.gettempdir()) / "oxce_hidden_user"


def utf8_streams():
    """Вывод с кириллицей в трубу или файл без PYTHONIOENCODING падал в cp1252 (R-001, аудит 05.10)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def prepare_user(user, mods_dir="", set_opts="", mods="", save="", master=""):
    """Папка пользователя игры: options.cfg установки с правками, соединение на моды, копия сейва hiddentest.sav.
    Возвращает текст options.cfg (звук берёт из него частоту и буфер)."""
    u = Path(user)
    (u / "piratez").mkdir(parents=True, exist_ok=True)
    mods_dir = Path(mods_dir).resolve() if mods_dir else GAME / "user" / "mods"
    if (u / "mods").exists() and Path(os.path.realpath(u / "mods")) != Path(os.path.realpath(mods_dir)):
        os.rmdir(u / "mods")   # соединение на другую папку модов: снимается только связь (R-047)
    if not (u / "mods").exists():
        # соединение на моды установки, а не копия (5 ГБ); снимать только rmdir (R-047)
        subprocess.run(["cmd", "/c", "mklink", "/J", str(u / "mods"), str(mods_dir)],
                       check=True, capture_output=True)
    cfg = (GAME / "user" / "options.cfg").read_text(encoding="utf-8")
    # всё, что спрашивает игрока или крутит камеру мышью человека (R-093, R-095)
    fixed = {"battleEdgeScroll": "0", "oxceAdultAsk": "false", "playIntro": "false", "oxceGentleAsk": "false"}
    for kv in filter(None, set_opts.split(";")):
        n, v = kv.split("=", 1)
        fixed[n] = v
    added = []
    for n, v in fixed.items():
        cfg, k = re.subn(rf"(?m)^(\s*){n}: .*$", lambda m: f"{m.group(1)}{n}: {v}", cfg)
        if not k:
            added.append(f"  {n}: {v}")
    if added:
        cfg = re.sub(r"(?m)^options:\s*$", "options:\n" + "\n".join(added), cfg, count=1)
    for kv in filter(None, mods.split(";")):
        n, v = kv.split("=", 1)
        cfg, k = re.subn(rf"(?m)^(  - active: )\S+(\r?\n    id: {re.escape(n)}\r?)$", rf"\g<1>{v}\g<2>", cfg)
        if not k:
            cfg = re.sub(r"(?m)^options:\s*$", f"  - active: {v}\n    id: {n}\noptions:", cfg, count=1)
    (u / "options.cfg").write_text(cfg, encoding="utf-8")
    # имя - из user/piratez установки; путь к существующему файлу - своя копия сейва (установку не трогаем)
    if save:
        src = Path(save) if Path(save).is_file() else GAME / "user" / "piratez" / save
        # игра читает сейвы из user/<мастер> (-master xcom1 - user/xcom1)
        (u / (master or "piratez")).mkdir(parents=True, exist_ok=True)
        shutil.copy(src, u / (master or "piratez") / "hiddentest.sav")
    return cfg


def game_env(**extra):
    """Окружение игры. Ключи в верхний регистр: Path и PATH вдвоём дают exe без DLL (код 0xC0000135)."""
    env = {k.upper(): v for k, v in os.environ.items()}
    env["PATH"] = "C:\\msys64\\mingw64\\bin;" + env.get("PATH", "")
    env.update(SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
    env.update({k: str(v) for k, v in extra.items()})
    return env


def game_args(exe, user, load=False, master="", sound=False):
    return [str(exe), "-data", str(GAME), "-user", str(user), "-cfg", str(user)] + (
        ["-load", "hiddentest.sav"] if load else []) + (["-master", master] if master else []) + [
        "-fullscreen", "false", "-borderless", "false", "-displayWidth", "1920", "-displayHeight", "1080",
        "-soundVolume", "100" if sound else "0", "-musicVolume", "0", "-FPSInactive", "60"]


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


def launch(exe, args, env):
    """Запуск на скрытом столе; возвращает ai_probe.Hidden (pid, poll, wait)."""
    return ai_probe.Hidden(args, str(Path(exe).parent), env)
