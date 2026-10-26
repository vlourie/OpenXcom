# Проверка игры НЕВИДИМО: свежий exe на копии сейва Пираток, на отдельном рабочем столе
# (ai_probe.Hidden) плюс SDL_VIDEODRIVER=dummy - окно игры на экране Vitali не появляется ни на миг (R-124).
# Щелчки, клавиши и дамп кадра делает сам движок (OXCE_HD_CLICK / OXCE_HD_KEY / OXCE_HD_DUMP).
# Щелчки - в пикселях базового экрана (R-103): при 1920x1080 и geoscapeScale 6 это дамп / 4.
#   py -3.13 tools/game_hidden.py --out E:/tmp/sell.png --save NoCodexCatZ.sav --after 100 --clicks "447,52;336,216"
# Один кадр = один запуск (загрузка 60-90 с). Несколько экранов подряд - живой стенд tools/hdbench.py.
# Показать игру на экране - только если Vitali сам попросил; этот скрипт так не умеет нарочно.
import argparse, re, subprocess, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ai_probe
import hidden_game
from hidden_game import GAME, EXE, DEFAULT_USER, unthrottle
hidden_game.utf8_streams()

a = argparse.ArgumentParser()
a.add_argument("--out", required=True, help="куда положить дамп кадра (png)")
a.add_argument("--save", default="NoCodexCatZ.sav", help="сейв из user/piratez установки; пусто - без сейва, до главного меню")
a.add_argument("--after", type=int, default=100, help="секунд до дампа (загрузка сейва ~60-90)")
a.add_argument("--clicks", default="")
a.add_argument("--key", default="")
a.add_argument("--set", default="", help="ключи options.cfg: a=1;b=false")
a.add_argument("--user", default=str(DEFAULT_USER))
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
cfg = hidden_game.prepare_user(u, o.mods_dir, o.set, o.mods, o.save, o.master)

dump = Path(o.out).resolve()
if dump.exists():
    dump.unlink()
env = hidden_game.game_env(OXCE_HD_DUMP=dump, OXCE_HD_DUMP_AFTER=o.after, OXCE_HD_CLICK=o.clicks, OXCE_HD_KEY=o.key)
if o.audio_disk:
    # драйвер disk спит SDL_DISKAUDIODELAY (по умолчанию 150 мс) на каждый буфер, а буфер 1024 при 22050 Гц -
    # 46 мс: запись шла втрое медленнее игры (30 с на 100). Задержка = длина буфера, запись ~ в реальном времени
    num = lambda n, d: int(m.group(1)) if (m := re.search(rf"(?m)^\s*{n}: (\d+)", cfg)) else d
    rate, chunk = num("audioSampleRate", 22050), num("audioChunkSize", 1024)
    env.update(SDL_AUDIODRIVER="disk", SDL_DISKAUDIOFILE=str(Path(o.audio_disk).resolve()),
               SDL_DISKAUDIODELAY=str(max(1, chunk * 1000 // rate)))
    print(f"звук: {rate} Гц, буфер {chunk}, задержка disk {chunk * 1000 // rate} мс")
args = hidden_game.game_args(EXE, u, load=bool(o.save), master=o.master, sound=bool(o.audio_disk))
p = hidden_game.launch(EXE, args, env)
print("pid", p.pid, "(скрытый рабочий стол)", flush=True)

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
