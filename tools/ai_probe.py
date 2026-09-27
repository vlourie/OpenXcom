#!/usr/bin/env python3
"""Проба хода ИИ: наша сборка грузит сохранённый бой Пираток и отыгрывает ход ИИ без человека.

Движок (src/Battlescape/AiProbe.cpp, переменная OXCE_AI_PROBE) сам завершает ход игрока,
ИИ играет на виртуальных часах, в лог идут строки:
  [AISTATE] before|aistart|after ...  - слепок всех юнитов (клетка, ОВ, здоровье, кого видит)
  [AIDECIDE] ...                      - отпечаток каждого решения ИИ
  [AIPROBE] ...                       - начало, конец, сохранённый бой

Прогон невидимый и тихий: скрытое окно, звук в dummy, приоритет ниже обычного. Установку Пираток
не трогает: своя папка пользователя, моды - ссылкой, сейв - копией.

  py -3.13 tools/ai_probe.py <сейв> [--turns N] [--save-as имя.asav] [--out отпечатки.txt]

Справка: docs/AI_ROADMAP.md, этап Ф2.1.
"""
import argparse, json, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path

ENC_W = "utf-8-sig"
ENC_R = "utf-8-sig"

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "tools/build/build_config.json").read_text(encoding=ENC_R))
GAME = ROOT / CFG["GameDir"]
# стенд ИИ живёт только в локальной сборке с OXCE_AI_DEV: в сборке для игроков его нет
# OXCE_AI_BUILD - другой каталог сборки стенда (build-ai2): новая правка собирается и играет, пока идёт серия на прежней
EXE = ROOT / (os.environ.get("OXCE_AI_BUILD") or "build-ai") / "bin" / "openxcom.exe"
WORK = Path(tempfile.gettempdir()) / "oxce_ai_probe"
TAGS = ("[AISTATE]", "[AIDECIDE]", "[AIPROBE]", "[AIRESULT]")


class Probe:
    """Итог одного прогона: строки пробы, путь к логу и к сохранённому бою."""

    def __init__(self, lines, log, saved, seconds, finished):
        self.lines, self.log, self.saved, self.seconds, self.finished = lines, log, saved, seconds, finished

    def tagged(self, tag, when=None):
        out = [l for l in self.lines if l.startswith(tag)]
        if when:
            out = [l for l in out if l.split()[1] == when]
        return out


def fields(line):
    """[AISTATE] before turn=1 unit=7 pos=(54,52,1) ... -> {'turn': '1', 'unit': '7', 'pos': '(54,52,1)'}"""
    return dict(p.split("=", 1) for p in line.split() if "=" in p)


def prepare_user(work):
    """Папка пользователя прогона: ссылка на моды установки, options.cfg установки без вопросов к игроку."""
    (work / "piratez").mkdir(parents=True, exist_ok=True)
    mods = work / "mods"
    if not mods.exists():
        subprocess.run(["cmd", "/c", "mklink", "/J", str(mods), str(GAME / "user" / "mods")],
                       check=True, capture_output=True)
    if not (mods / "hd").exists():
        sys.exit(f"нет ссылки на моды: {mods}")
    cfg = (GAME / "user" / "options.cfg").read_text(encoding=ENC_R)
    # R-093, R-095: камеру не крутит мышь человека, экран выбора версии не встаёт
    # картинку прогона никто не смотрит: один поток рисования и масштаб 1, иначе 8 боёв разом съедают весь процессор
    for key, value in (("battleEdgeScroll", "0"), ("oxceAdultAsk", "false"), ("playIntro", "false"),
                       ("oxceHdThreads", "1"), ("oxceHdScale", "1"), ("oxceHdMode", "0")):
        cfg = re.sub(rf"(?m)^(\s*){key}: .*$", rf"\g<1>{key}: {value}", cfg)
    # options.cfg читает игра (yaml-cpp), а не PowerShell: без спецификации (R-001, исключение)
    (work / "options.cfg").write_bytes(cfg.encode("utf-8"))


def campaign_path(name):
    """Сейв кампании: путь как есть или имя в user/piratez установки (сам файл не трогаем, берём копию)."""
    p = Path(name)
    return p if p.is_file() else GAME / "user" / "piratez" / name


def run(save, turns=1, save_as="", name="probe", timeout=900, bot=False, seed=None, diff=None, campaign=None,
        mission=None, tactics=False, careful=False):
    """Прогоняет пробу и возвращает Probe.
    save - сейв боя (копируется) или None вместе с seed: тогда игра сама собирает случайный бой мода.
    campaign - сейв кампании: отряд боя - самый большой экипаж оттуда, со снаряжением, сложностью и месяцем.
    bot - сторону игрока тоже ведёт ИИ, до конца боя или turns ходов.
    mission - закрепить миссию случайного боя (тип развёртывания), остальное по зерну."""
    if save is not None:
        save = Path(save)
        if not save.is_file():
            sys.exit(f"нет сейва: {save}")
    elif seed is None:
        sys.exit("нужен сейв или --seed")
    if not EXE.is_file():
        sys.exit(f"нет сборки стенда: {EXE} (cmake -DOXCE_AI_DEV=ON, каталог build-ai)")
    work = WORK / name
    prepare_user(work)
    for old in (work / "battle.cfg", work / "piratez" / "battle.cfg"):
        if old.exists():
            old.unlink()  # иначе бой соберётся по настройкам прошлого прогона
    if save is not None:
        shutil.copyfile(save, work / "piratez" / "probe.asav")
    if campaign:
        src = campaign_path(campaign)
        if not src.is_file():
            sys.exit(f"нет сейва кампании: {src}")
        shutil.copyfile(src, work / "piratez" / "campaign.sav")
    log = work / "openxcom.log"
    if log.exists():
        log.unlink()
    saved = work / "piratez" / save_as if save_as else None
    if saved and saved.exists():
        saved.unlink()

    env = {k: v for k, v in os.environ.items() if not k.startswith("OXCE_HD_")}
    env["PATH"] = CFG["MsysBin"] + os.pathsep + env.get("PATH", "")
    env["SDL_AUDIODRIVER"] = "dummy"
    env["OXCE_AI_PROBE"] = "1"
    env["OXCE_AI_PROBE_TURNS"] = str(turns)
    env["OXCE_AI_PROBE_SAVE"] = save_as or ""
    env["OXCE_AI_BOT"] = "1" if bot else ""
    env["OXCE_AI_SEED"] = "" if seed is None else str(seed)
    env["OXCE_AI_DIFF"] = "" if diff is None else str(diff)
    env["OXCE_AI_CAMPAIGN"] = "campaign.sav" if campaign else ""
    env["OXCE_AI_MISSION"] = mission or ""
    # правила под опытом задаются явно: унаследованная переменная не должна тихо включить их в базовой серии
    env["OXCE_AI_TACTICS"] = "1" if tactics else ""
    env["OXCE_AI_CAREFUL"] = "1" if careful else ""
    args = [str(EXE), "-data", str(GAME), "-user", str(work), "-cfg", str(work),
            "-fullscreen", "false", "-borderless", "false", "-displayWidth", "1280", "-displayHeight", "720",
            "-soundVolume", "0", "-musicVolume", "0", "-uiVolume", "0"]
    if save is not None:
        args[5:5] = ["-load", "probe.asav"]
    else:
        env["OXCE_HD_START"] = "battle"  # главное меню сразу собирает бой (MainMenuState.cpp)
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0  # SW_HIDE: ни окна, ни кнопки на панели задач
    t0 = time.time()
    p = subprocess.Popen(args, cwd=str(EXE.parent), env=env, startupinfo=si,
                         creationflags=subprocess.BELOW_NORMAL_PRIORITY_CLASS,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    stuck = ""
    watch = Watch(log)
    try:
        while p.poll() is None:
            # SDL показывает окно сам, мимо STARTUPINFO: прячем, пока процесс жив
            crash = hide_windows(p.pid)
            stuck = f"crash: {crash}" if crash else watch.stuck()
            if stuck or time.time() - t0 > timeout:
                break
            time.sleep(0.3)
    finally:
        if p.poll() is None:  # и на своей ошибке тоже: скрытая игра не должна пережить прогон
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)  # R-073: деревом
            p.wait()
    seconds = time.time() - t0
    text = log.read_text(encoding=ENC_R, errors="replace") if log.exists() else ""
    lines = []
    for raw in text.splitlines():
        body = raw.split("\t", 2)[-1]
        if body.startswith(TAGS):
            lines.append(body)
    finished = any(l.startswith(("[AIPROBE] done", "[AIRESULT]")) for l in lines)
    if stuck:
        lines.append(f"[AIPROBE] stuck: {stuck}")
    return Probe(lines, log, saved if saved and saved.exists() else None, seconds, finished)


def hide_windows(pid):
    """Прячет видимые окна процесса (ShowWindow SW_HIDE): Vitali работает за той же машиной.
    Возвращает первую строку окна 'OpenXcom Error', если игра упала: оно спрятано вместе с игрой
    и ждёт нажатия вечно."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    found, errors = [], []

    def text(hwnd):
        n = user32.SendMessageW(hwnd, 0x000E, 0, 0)  # WM_GETTEXTLENGTH
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.SendMessageW(hwnd, 0x000D, n + 1, buf)  # WM_GETTEXT
        return buf.value

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid:
            if user32.IsWindowVisible(hwnd):
                found.append(hwnd)
            if text(hwnd) == "OpenXcom Error":
                errors.append(hwnd)
        return True

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def child(hwnd, _):
        t = text(hwnd)
        if len(t) > 3:
            found_text.append(t.splitlines()[0])
        return True

    user32.EnumWindows(each, 0)
    for hwnd in found:
        user32.ShowWindow(hwnd, 0)
    found_text = []
    for hwnd in errors:
        user32.EnumChildWindows(hwnd, child, 0)
    return found_text[0] if found_text else ("OpenXcom Error" if errors else "")


# экраны, на которых ход ИИ может стоять законно: бой, смена хода, сообщения с таймером
MOVING = ("BattlescapeState", "NextTurnState", "InfoboxState")


class Watch:
    """Читает лог прогона по мере записи. Сторож включается со строки [AIPROBE] start: до неё игра грузится."""

    def __init__(self, log):
        self.log, self.pos, self.started, self.states = log, 0, False, []

    def stuck(self):
        """Имя экрана, если игра стоит на чужом экране три отчёта HD frame подряд (около 6 с): окно ждёт нажатия.
        Такое окно надо научить закрываться в пробе, как InfoboxOKState (R-110)."""
        try:
            with open(self.log, "rb") as f:
                f.seek(self.pos)
                chunk = f.read()
        except OSError:
            return ""  # лога ещё нет или игра держит его открытым на запись
        cut = chunk.rfind(b"\n") + 1
        self.pos += cut
        text = chunk[:cut].decode("utf-8", "replace")
        if not self.started:
            hits = [i for i in (text.find("[AIPROBE] start"), text.find("[AIPROBE] battle")) if i >= 0]
            if not hits:
                return ""
            i = min(hits)
            self.started, text = True, text[i:]
        self.states += re.findall(r"HD frame: .*?\(N8OpenXcom\d+(\w+?)E\)", text)
        last = self.states[-3:]
        if len(last) == 3 and len(set(last)) == 1 and not last[0].startswith(MOVING):
            return last[0]
        return ""


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # R-001: вывод в трубу иначе cp1252 и падение на кириллице
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("save", nargs="?", help="сейв боя (копируется, оригинал не трогаем); без него нужен --seed")
    ap.add_argument("--seed", type=int, help="случайный бой мода по зерну (миссия, корабль, местность, раса, тьма)")
    ap.add_argument("--bot", action="store_true", help="сторону игрока тоже ведёт ИИ, до конца боя")
    ap.add_argument("--diff", type=int, help="сложность сгенерированного боя 0-4 (по умолчанию из кампании, иначе 4)")
    ap.add_argument("--campaign", default="", help="сейв кампании для отряда (имя в user/piratez установки или путь)")
    ap.add_argument("--turns", type=int, default=0, help="сколько ходов ИИ отыграть (1; с --bot - предел, 60)")
    ap.add_argument("--save-as", default="", help="сохранить бой после них (фикстура)")
    ap.add_argument("--out", default="", help="записать строки пробы в файл")
    ap.add_argument("--name", default="probe", help="имя рабочей папки прогона")
    ap.add_argument("--timeout", type=int, default=900)
    a = ap.parse_args()
    r = run(a.save, a.turns, a.save_as, a.name, a.timeout, bot=a.bot, seed=a.seed, diff=a.diff,
            campaign=a.campaign or None)
    print(f"прогон {r.seconds:.0f} с, {'закончен' if r.finished else 'НЕ закончен - смотри лог'}: {r.log}")
    print(f"AISTATE {len(r.tagged('[AISTATE]'))}, AIDECIDE {len(r.tagged('[AIDECIDE]'))}")
    for l in r.tagged("[AIPROBE]") + r.tagged("[AIRESULT]"):
        print(l)
    if a.save_as:
        if r.saved:
            dest = Path(a.out).with_name(a.save_as) if a.out else Path(a.save_as)
            shutil.copyfile(r.saved, dest)
            print(f"сейв: {dest}")
        else:
            print("сейва нет")
    if a.out:
        Path(a.out).write_text("\n".join(r.lines) + "\n", encoding=ENC_W)
        print(f"строки: {a.out}")
    return 0 if r.finished else 1


if __name__ == "__main__":
    sys.exit(main())
