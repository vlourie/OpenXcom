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

ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / "Пиратки" / "Dioxine_XPiratez"
EXE = ROOT / "build-release" / "bin" / "openxcom.exe"

a = argparse.ArgumentParser()
a.add_argument("--out", required=True, help="куда положить дамп кадра (png)")
a.add_argument("--save", default="NoCodexCatZ.sav", help="сейв из user/piratez установки")
a.add_argument("--after", type=int, default=100, help="секунд до дампа (загрузка сейва ~60-90)")
a.add_argument("--clicks", default="")
a.add_argument("--key", default="")
a.add_argument("--set", default="", help="ключи options.cfg: a=1;b=false")
a.add_argument("--user", default=str(Path(tempfile.gettempdir()) / "oxce_hidden_user"))
o = a.parse_args()

u = Path(o.user)
(u / "piratez").mkdir(parents=True, exist_ok=True)
if not (u / "mods").exists():
    # соединение на моды установки, а не копия (5 ГБ); снимать только rmdir (R-047)
    subprocess.run(["cmd", "/c", "mklink", "/J", str(u / "mods"), str(GAME / "user" / "mods")],
                   check=True, capture_output=True)
cfg = (GAME / "user" / "options.cfg").read_text(encoding="utf-8")
# всё, что спрашивает игрока или крутит камеру мышью человека (R-093, R-095)
fixed = {"battleEdgeScroll": "0", "oxceAdultAsk": "false", "playIntro": "false"}
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
(u / "options.cfg").write_text(cfg, encoding="utf-8")
shutil.copy(GAME / "user" / "piratez" / o.save, u / "piratez" / "hiddentest.sav")

dump = Path(o.out).resolve()
if dump.exists():
    dump.unlink()
# ключи окружения в верхний регистр: Path и PATH вдвоём дают exe без DLL (код 0xC0000135)
env = {k.upper(): v for k, v in os.environ.items()}
env["PATH"] = "C:\\msys64\\mingw64\\bin;" + env.get("PATH", "")
env.update(SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy", OXCE_HD_DUMP=str(dump),
           OXCE_HD_DUMP_AFTER=str(o.after), OXCE_HD_CLICK=o.clicks, OXCE_HD_KEY=o.key)
args = [str(EXE), "-data", str(GAME), "-user", str(u), "-cfg", str(u), "-load", "hiddentest.sav",
        "-fullscreen", "false", "-borderless", "false", "-displayWidth", "1920", "-displayHeight", "1080",
        "-soundVolume", "0", "-musicVolume", "0", "-FPSInactive", "60"]
p = ai_probe.Hidden(args, str(EXE.parent), env)
print("pid", p.pid, "(скрытый рабочий стол)")
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
sys.exit(0 if dump.exists() else 1)
