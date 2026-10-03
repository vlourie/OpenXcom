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
import argparse, json, os, re, shutil, subprocess, sys, tempfile, threading, time
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
# трассы охоты за недетерминизмом ([AIMELEE], [AIPATH]) тоже: без них ai_arena --env OXCE_AI_TRACE_* пишет пустоту;
# запись решений по OXCE_AI_RECORD ([AIREC], списки ходов [AICAND]) - план V2, шаг 2
TAGS = ("[AISTATE]", "[AIDECIDE]", "[AIPROBE]", "[AIRESULT]", "[AICASUALTY]", "[AIMELEE]", "[AIPATH]", "[AIRECHEAD]", "[AIREC]",
        "[AIEXEC]", "[AIAFTER]", "[AITRACE]", "[AICAND]", "[AIPATROL]", "[AIPF]",
        # зонд ESCAPE_DEATH_ATTRIBUTION (OXCE_AI_ATTRIB_PROBE, build-ai64): что сделала смена хода с юнитом, по стадиям
        "[AITURNFX]",
        # зонд ESCAPE_ALT (OXCE_AI_ESCAPE_ALT_PROBE, build-ai68): достижимые клетки рядом с выбранной клеткой побега
        "[AIESCALT]",
        # зонд WOUNDED_COMBAT_DECISION_V1 (OXCE_AI_MEDIPROBE, build-ai70): проверка аптечки в начале хода
        "[AIMEDI]",
        # правило PATROL_STUN_RESERVE_V1 (OXCE_AI_PATROL_STUN_RESERVE, build-ai71): проверка патрульного шага на восстановление оглушения
        "[AISTUNRES]",
        # итоги приборов стенда после [AIRESULT] (свет, отход, FOV на шаге) - архив <метка>.result.txt серии ai_arena.py
        "[AILIGHT]", "[AIESCRF]", "[AIWALKFOV]", "[AIWALKFOVSKIP]", "[AIAMBMEMO]")


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
    # нежный режим: вопрос при запуске не встаёт, темп прогона прежний (ключей может ещё не быть в конфиге - дописываем)
    added = []
    for key, value in (("battleEdgeScroll", "0"), ("oxceAdultAsk", "false"), ("playIntro", "false"),
                       ("oxceHdThreads", "1"), ("oxceHdScale", "1"), ("oxceHdMode", "0"),
                       ("oxceGentleAsk", "false"), ("oxceGentle", "false")):
        cfg, n = re.subn(rf"(?m)^(\s*){key}: .*$", rf"\g<1>{key}: {value}", cfg)
        if not n:
            added.append(f"  {key}: {value}")
    if added:
        cfg = re.sub(r"(?m)^options:\s*$", "options:\n" + "\n".join(added), cfg, count=1)
    # options.cfg читает игра (yaml-cpp), а не PowerShell: без спецификации (R-001, исключение)
    (work / "options.cfg").write_bytes(cfg.encode("utf-8"))


def campaign_path(name):
    """Сейв кампании: путь как есть или имя в user/piratez установки (сам файл не трогаем, берём копию)."""
    p = Path(name)
    return p if p.is_file() else GAME / "user" / "piratez" / name


def bench_defaults(env):
    """Флаги стенда: меняют то, КАК считается, а не как играет; у каждого своя приёмка (tools/ai_speed/README.md).
    Не заданный явно флаг получает значение ниже. ai_arena --strict-flags требует все явно (контракт конфигурации
    02.10, R-169): у станций свои версии этого файла, и setdefault разных версий тихо даёт разные серии.
    Возвращает env; имена флагов - BENCH_FLAGS."""
    # быстрый режим стенда (AiProbe::fast, с build-ai39): ни кадра, ни анимации кроме дверей НЛО, ни сцены добивания,
    # ни звука, один открытый лог, выход сразу за строкой итога - решения, запись и итог те же (p39a = p39f2 на fair22, 22 из 22,
    # tools/ai_speed/README.md). Выключить для контрольного опыта: OXCE_AI_FAST=0 (ai_arena --env OXCE_AI_FAST=0).
    # Сборки до build-ai39 переменную не знают и играют как прежде
    env.setdefault("OXCE_AI_FAST", "1")
    # свет (AiProbe::lightSkip, с build-ai41): шаг юнита, который сам не светит, не пересчитывает освещение карты - все
    # события, меняющие свет, пересчитывают его сами. Приёмка отдельно от FAST: 8 карт парами без/с флагом (в том числе
    # ночь и квады-фонари с personalLightHostile 26), все потоки =, fair22 IDENTICAL 22 из 22 (tools/ai_speed/README.md).
    # Контрольный опыт: OXCE_AI_LIGHTSKIP=0. Сборки до build-ai41 переменную не знают и играют как прежде
    env.setdefault("OXCE_AI_LIGHTSKIP", "1")
    # память засады (AiProbe::ambushMemo, с build-ai43, AMBUSH_NEGATIVE_MEMO_V1): внутри одного setupAmbush узел, куда враг
    # заведомо не дойдёт (закрытые узлы его первого неудачного A* в этом вызове), пропускает поиск врага; помнится только
    # «нет пути», только до выхода из вызова. Приёмка: семь потоков = на станции и бомбардировщике, режим 2 (проверка) - 99
    # ответов, 0 расхождений, fair22 IDENTICAL 22 из 22 (tools/ai_speed/README.md); включено по умолчанию 01.10 по второму
    # мнению. Контрольный опыт обязателен: OXCE_AI_AMBUSH_MEMO=0. Сборки до build-ai43 переменную не знают и играют как прежде.
    # 02.10 V1 выключена: спрашивала память про узел, а враг ищет к tryCalculateFinalPosition(узел) - GUNS 2352 режим 2:
    # 173 ответа, 9 неверных (R-169). V2 (build-ai53, Pathfinding::finalPositionFor) включена по умолчанию 02.10 по второму
    # мнению: fair22 память выкл ai52 = ai53, режим 1 и 2 = выкл (22 из 22); режим 2 на fair22 и четырёх картах - 1052
    # ответа, 0 неверных, контроль V1 - 25. На сборках до build-ai53 значение 1 включает V1 - серии на них задавать =0 явно
    env.setdefault("OXCE_AI_AMBUSH_MEMO", "1")
    # отход (AiProbe::escapeReachFirst, с build-ai45, ESCAPE_REACH_FIRST_V1): setupEscape отбрасывает недосягаемую клетку ДО
    # трасс canTargetUnit к ней, а не после (трассы const, RNG не трогают; счёт, выбор клетки и действие те же). Приёмка: три
    # карты флаг 0/1 - шесть потоков =, трассы оценок [AITRACE] те же, трасс на недосягаемых 0, досягаемых столько же; fair22
    # IDENTICAL 22 из 22 против p43d1 и p44f2 (tools/ai_speed/README.md); включено по умолчанию 01.10 по второму мнению.
    # Контрольный опыт обязателен: OXCE_AI_ESCAPE_REACH_FIRST=0. Сборки до build-ai45 переменную не знают и играют как прежде
    env.setdefault("OXCE_AI_ESCAPE_REACH_FIRST", "1")
    # FOV экрана на шаге бота (AiProbe::walkFovKeep, с build-ai48, BOT_WALKFOV_UI_SKIP_V1): после законченного шага ходока бота
    # updateSoldierInfo обновляет только панель, без полного FOV выбранного (его юнитовую часть тут же заново считает FOV шага
    # UnitWalkBState 228, тайловую между шагами никто не читает); только когда бот играет сторону игрока, выбранный - ходок и
    # sneakyAI выключен, иначе как в движке. Приёмка: 8 карт флаг 0/1/2 (в том числе тень 11-12) - шесть потоков =, тень (=2:
    # что вызов ставил под старым светом, а FOV шага не повторил) - все счётчики 0; fair22 зерно 201 и 301 IDENTICAL 22 из 22
    # (tools/ai_speed/README.md); включено по умолчанию 01.10 по второму мнению. Контрольный опыт обязателен:
    # OXCE_AI_WALKFOV_SKIP=0; тень - =2. Сборки до build-ai48 переменную не знают и играют как прежде
    env.setdefault("OXCE_AI_WALKFOV_SKIP", "1")
    return env


BENCH_FLAGS = tuple(bench_defaults({}))


def run(save, turns=1, save_as="", name="probe", timeout=900, bot=False, seed=None, diff=None, campaign=None,
        mission=None, tactics=False, careful=False, squad=0):
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
    # окна нет вовсе: SDL показывает своё окно мимо STARTUPINFO, и прятать его после - значит дать мелькнуть
    # (Vitali 27.09: «нельзя открывать игру даже на секунду на экране»)
    env["SDL_VIDEODRIVER"] = "dummy"
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
    env["OXCE_AI_SQUAD"] = str(squad) if squad else ""  # отряд: n самых опытных бойцов самого опытного экипажа
    bench_defaults(env)
    args = [str(EXE), "-data", str(GAME), "-user", str(work), "-cfg", str(work),
            "-fullscreen", "false", "-borderless", "false", "-displayWidth", "1280", "-displayHeight", "720",
            "-soundVolume", "0", "-musicVolume", "0", "-uiVolume", "0"]
    if save is not None:
        args[5:5] = ["-load", "probe.asav"]
    else:
        env["OXCE_HD_START"] = "battle"  # главное меню сразу собирает бой (MainMenuState.cpp)
    t0 = time.time()
    p = Hidden(args, str(EXE.parent), env)
    stuck = ""
    watch = Watch(log)
    try:
        while p.poll() is None:
            # окно ошибки игры ждёт нажатия вечно: ищем его на скрытом столе прогона
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


DESK_NAME = "oxce_ai_bench"
_desk = None
_desk_lock = threading.Lock()


def bench_desktop():
    """Свой рабочий стол для игры (CreateDesktop): всё, что она покажет, - окно SDL, окно ошибки,
    системный диалог - живёт там и на экран Vitali не попадает ни на миг. Один на процесс питона."""
    global _desk
    with _desk_lock:  # серия зовёт из 12 потоков сразу: без замка второй CreateDesktop получал отказ (ошибка 5)
        if _desk is None:
            import ctypes
            user32 = ctypes.windll.user32
            user32.CreateDesktopW.restype = user32.OpenDesktopW.restype = ctypes.c_void_p
            # стол уже есть (соседняя серия) - открыть его
            _desk = user32.OpenDesktopW(DESK_NAME, 0, False, 0x10000000) \
                or user32.CreateDesktopW(DESK_NAME, None, None, 0, 0x10000000, None)  # GENERIC_ALL
            if not _desk:
                raise OSError(f"не создан скрытый рабочий стол: ошибка {ctypes.GetLastError()}")
    return _desk


class Hidden:
    """Процесс игры на скрытом рабочем столе (CreateProcessW с lpDesktop), приоритет ниже обычного.
    Повторяет то, что прогону нужно от Popen: pid, poll(), wait()."""

    def __init__(self, args, cwd, env):
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.windll.kernel32
        bench_desktop()
        # системные окна об ошибке (сбой, нет диска) не показывать вовсе; режим наследует игра
        k32.SetErrorMode(0x0001 | 0x0002 | 0x8000)

        class SI(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR), ("lpDesktop", wintypes.LPWSTR),
                        ("lpTitle", wintypes.LPWSTR), ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
                        ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD), ("dwXCountChars", wintypes.DWORD),
                        ("dwYCountChars", wintypes.DWORD), ("dwFillAttribute", wintypes.DWORD),
                        ("dwFlags", wintypes.DWORD), ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD),
                        ("lpReserved2", ctypes.c_void_p), ("hStdInput", wintypes.HANDLE),
                        ("hStdOutput", wintypes.HANDLE), ("hStdError", wintypes.HANDLE)]

        class PI(ctypes.Structure):
            _fields_ = [("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE),
                        ("dwProcessId", wintypes.DWORD), ("dwThreadId", wintypes.DWORD)]

        si = SI()
        si.cb = ctypes.sizeof(SI)
        si.lpDesktop = "WinSta0" + chr(92) + DESK_NAME
        si.dwFlags = 0x0001  # STARTF_USESHOWWINDOW
        si.wShowWindow = 0   # SW_HIDE - и на скрытом столе
        pi = PI()
        block = ctypes.create_unicode_buffer("".join(f"{k}={v}\0" for k, v in env.items()) + "\0")
        cmd = ctypes.create_unicode_buffer(subprocess.list2cmdline(args))
        k32.CreateProcessW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p, ctypes.c_void_p,
                                       wintypes.BOOL, wintypes.DWORD, ctypes.c_void_p, wintypes.LPCWSTR,
                                       ctypes.POINTER(SI), ctypes.POINTER(PI)]
        # BELOW_NORMAL_PRIORITY_CLASS | CREATE_UNICODE_ENVIRONMENT
        if not k32.CreateProcessW(None, cmd, None, None, False, 0x4000 | 0x0400, block, cwd,
                                  ctypes.byref(si), ctypes.byref(pi)):
            raise OSError(f"CreateProcessW: ошибка {ctypes.GetLastError()}")
        k32.CloseHandle(pi.hThread)
        self._k32, self._h, self.pid, self.returncode = k32, pi.hProcess, pi.dwProcessId, None

    def poll(self):
        if self.returncode is None and self._k32.WaitForSingleObject(self._h, 0) == 0:
            import ctypes
            code = ctypes.c_ulong(0)
            self._k32.GetExitCodeProcess(self._h, ctypes.byref(code))
            self.returncode = code.value
            self._k32.CloseHandle(self._h)
        return self.returncode

    def wait(self):
        while self.poll() is None:
            time.sleep(0.1)
        return self.returncode


def hide_windows(pid):
    """Прячет видимые окна процесса (ShowWindow SW_HIDE): Vitali работает за той же машиной.
    Возвращает первую строку окна 'OpenXcom Error', если игра упала: оно спрятано вместе с игрой
    и ждёт нажатия вечно."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    found, errors = [], []

    def text(hwnd):
        # с таймаутом: окно игры, повисшей на выходе, на SendMessage не отвечает, и сторож ждал вечно,
        # мимо своего таймаута - серия вставала (SMTO_ABORTIFHUNG | SMTO_BLOCK, 200 мс)
        send = user32.SendMessageTimeoutW
        send.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, ctypes.c_void_p, wintypes.UINT, wintypes.UINT,
                         ctypes.POINTER(ctypes.c_size_t)]
        n = ctypes.c_size_t(0)
        if not send(hwnd, 0x000E, 0, None, 0x0002 | 0x0001, 200, ctypes.byref(n)):  # WM_GETTEXTLENGTH
            return ""
        buf = ctypes.create_unicode_buffer(n.value + 1)
        got = ctypes.c_size_t(0)
        if not send(hwnd, 0x000D, n.value + 1, ctypes.cast(buf, ctypes.c_void_p), 0x0002 | 0x0001, 200, ctypes.byref(got)):  # WM_GETTEXT
            return ""
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

    user32.EnumDesktopWindows(ctypes.c_void_p(bench_desktop()), each, 0)  # игра живёт на своём столе
    for hwnd in found:
        user32.ShowWindowAsync(hwnd, 0)  # не ждёт окно чужого потока: повисшее не держит сторожа
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
