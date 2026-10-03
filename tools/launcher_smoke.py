# Проверка выпускной сборки лаунчера перед повышением версии (docs/portal/VOICE_RELEASE.md, «Проверка
# перед выпуском»): лаунчер открывается, игра запускается, обновление работает. Всё невидимо (R-124):
#   1. обновление: --headless check / update / check / self-update против xp-release serve локального
#      хранилища в свежую папку --dir (3,7 ГБ на 03.10, минута-две);
#   2. окно: выпускной exe на скрытом рабочем столе ai_probe.Hidden, его окно найдено;
#   3. игра: кнопка «Играть» нажата через UI Automation на том же столе (tools/launcher_press_play.ps1),
#      игра (драйверы SDL dummy, наследует от лаунчера) жива через 90 с, в openxcom.log нет ошибок.
# settings.json лаунчер берёт из %LOCALAPPDATA% (known folder, подменить нельзя): файл сохраняется,
# переводится на --dir и локальное хранилище и возвращается побайтно. Выпускная сборка пишет в HKCU
# ссылку xpiratez:// - если её не было до прогона, она убирается. Установка Пираток только читается
# (папка UFO копируется). Папку --dir прогон не удаляет: удалить руками после просмотра.
#   py -3.13 tools/launcher_smoke.py [--rel dist/_launcher_rel] [--dir D:/xp-smoke-launcher]
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import winreg
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import ai_probe  # noqa: E402

SHIPPED = ["XPiratezLauncher.exe", "libHarfBuzzSharp.dll", "libSkiaSharp.dll", "libsodium.dll",
           "xp-bootstrap.exe", "livekit_ffi.dll", "xpaudio.dll"]
SERVE = ROOT / "dist" / "_xp-release" / "xp-release.exe"
UFO = ROOT / "Пиратки" / "Dioxine_XPiratez" / "UFO"
SETTINGS = Path(os.environ["LOCALAPPDATA"]) / "XPiratezLauncher" / "settings.json"
BS = chr(92)
LINK_KEY = "Software" + BS + "Classes" + BS + "xpiratez"
NO_WINDOW = 0x08000000
GAME_SECONDS = 90

a = argparse.ArgumentParser()
a.add_argument("--rel", default=str(ROOT / "dist" / "_launcher_rel"), help="выпускная сборка лаунчера")
a.add_argument("--dir", default="D:/xp-smoke-launcher", help="свежая папка: launcher и game; не должна существовать")
a.add_argument("--repo", default="D:" + BS + "xp-repo", help="локальное хранилище выпусков")
a.add_argument("--channel", default="stable")
a.add_argument("--port", type=int, default=8787)
a.add_argument("--out", default=str(Path(tempfile.gettempdir()) / "launcher_smoke"), help="журналы прогона")
o = a.parse_args()
REL, SMOKE, OUT = Path(o.rel), Path(o.dir), Path(o.out)
LAUNCHER, GAME = SMOKE / "launcher", SMOKE / "game"
URL = f"http://localhost:{o.port}/"
results = []


def say(text):
    print(time.strftime("%H:%M:%S"), text, flush=True)


def verdict(name, ok, detail):
    results.append((name, ok, detail))
    say(("PASS " if ok else "FAIL ") + name + ": " + detail)


def running(names):
    return [p.info for p in psutil.process_iter(["pid", "name", "exe"]) if (p.info["name"] or "").lower() in names]


def link_key():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, LINK_KEY + BS + "shell" + BS + "open" + BS + "command") as k:
            return winreg.QueryValueEx(k, "")[0]
    except FileNotFoundError:
        try:
            winreg.OpenKey(winreg.HKEY_CURRENT_USER, LINK_KEY).Close()
            return "(key without command)"
        except FileNotFoundError:
            return None


def delete_tree(path):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_ALL_ACCESS) as k:
        subs, i = [], 0
        while True:
            try:
                subs.append(winreg.EnumKey(k, i))
                i += 1
            except OSError:
                break
    for s in subs:
        delete_tree(path + BS + s)
    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)


def headless(*args, timeout=600):
    t = time.time()
    r = subprocess.run([str(LAUNCHER / "XPiratezLauncher.exe"), "--headless", *args],
                       capture_output=True, timeout=timeout, creationflags=NO_WINDOW)
    out = (r.stdout + r.stderr).decode("utf-8", "replace").strip()
    say(f"headless {args[0]}: exit {r.returncode} in {time.time() - t:.0f} s")
    for line in (out.splitlines()[-6:] if out else []):
        print("    " + line, flush=True)
    return r.returncode


def wait_http(url, seconds):
    end = time.time() + seconds
    while True:
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                return r.status
        except OSError:
            if time.time() > end:
                return None
            time.sleep(0.5)


def windows_of(pid):
    """Заголовки окон процесса на скрытом столе: (текст, видимо ли)."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    titles = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid:
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buf, 256)
            titles.append((buf.value, bool(user32.IsWindowVisible(hwnd))))
        return True

    user32.EnumDesktopWindows(ctypes.c_void_p(ai_probe.bench_desktop()), each, 0)
    return titles


def kill_tree(pid):
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True, creationflags=NO_WINDOW)


def product_version(path):
    return subprocess.run(["powershell", "-NoProfile", "-Command", f"(Get-Item '{path}').VersionInfo.ProductVersion"],
                          capture_output=True, text=True, creationflags=NO_WINDOW).stdout.strip()


def game_processes():
    out = []
    for p in psutil.process_iter(["pid", "name", "exe"]):
        exe = p.info["exe"] or ""
        if exe and Path(exe).resolve().is_relative_to(GAME.resolve()):
            out.append(p)
    return out


def update_checks():
    # headless берёт только папку, похожую на игру (GamePaths.LooksLikeGameDir); без состояния лаунчера
    # отличающийся файл - Changed, а не игроков, поэтому пустой exe заменяется выпускным
    (GAME / "common").mkdir(parents=True)
    (GAME / "user").mkdir()
    (GAME / "openxcom_hd.exe").write_bytes(b"")
    where = ["--game", str(GAME), "--channel", o.channel, "--repo", URL]
    code = headless("check", *where)
    verdict("check on an empty folder", code == 3, f"exit {code} (3 = update available)")
    code = headless("update", *where, timeout=3600)
    verdict("update installs the release", code == 0, f"exit {code}")
    code = headless("check", *where)
    verdict("check after update", code == 0, f"exit {code} (0 = up to date)")
    code = headless("self-update", "--game", str(GAME), "--repo", URL)
    after = product_version(LAUNCHER / "XPiratezLauncher.exe")
    verdict("self-update keeps the build", code == 0 and after == product_version(REL / "XPiratezLauncher.exe"),
            f"exit {code}, version after {after}")


def gui_checks():
    settings = json.loads(SETTINGS.read_bytes().decode("utf-8-sig"))
    settings["gameDir"] = str(GAME)
    settings["repoUrl"] = URL
    SETTINGS.write_bytes(json.dumps(settings, ensure_ascii=False, indent=2).encode("utf-8"))
    env = dict(os.environ, SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
    exe = LAUNCHER / "XPiratezLauncher.exe"
    launcher = ai_probe.Hidden([str(exe)], str(LAUNCHER), env)
    say(f"launcher pid {launcher.pid} on the hidden desktop")
    try:
        titles = []
        end = time.time() + 60
        while time.time() < end and launcher.poll() is None:
            titles = [t for t in windows_of(launcher.pid) if t[0] and t[1]]
            if titles:
                break
            time.sleep(1)
        verdict("the launcher opens", launcher.poll() is None and bool(titles),
                f"alive={launcher.poll() is None}, visible windows {titles}")
        if launcher.poll() is not None:
            return
        verdict("xpiratez:// registered by the release build", str(exe).lower() in (link_key() or "").lower(),
                f"{link_key()}")

        ui_log = OUT / "press_play.log"
        ps = ai_probe.Hidden(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                              str(ROOT / "tools" / "launcher_press_play.ps1"), str(launcher.pid), str(ui_log), "180"],
                             str(OUT), env)
        code = ps.wait()
        text = ui_log.read_text(encoding="utf-8-sig") if ui_log.exists() else "(no log)"
        for line in text.splitlines()[-6:]:
            print("    " + line[:300], flush=True)
        verdict("the play button pressed", code == 0, f"exit {code}")
        if code != 0:
            return

        end = time.time() + 60
        procs = []
        while time.time() < end and not procs:
            procs = [p for p in game_processes() if p.name().lower().startswith("openxcom")]
            time.sleep(1)
        if not procs:
            verdict("the game starts", False, "no game process within 60 s")
            return
        game = procs[0]
        say(f"game {game.name()} pid {game.pid}: {' '.join(game.cmdline()[1:])}")
        time.sleep(GAME_SECONDS)
        alive = game.is_running() and game.status() != psutil.STATUS_ZOMBIE
        error = ai_probe.hide_windows(game.pid) if alive else ""
        game_log = GAME / "user" / "openxcom.log"
        lines = game_log.read_text(encoding="utf-8", errors="replace").splitlines() if game_log.exists() else []
        bad = [ln for ln in lines if "[FATAL]" in ln or "[ERROR]" in ln]
        say(f"game log {game_log}: {len(lines)} lines, errors {len(bad)}")
        for line in (bad[:8] or lines[-3:]):
            print("    " + line[:200], flush=True)
        verdict("the game starts", alive and not error and bool(lines) and not bad,
                f"alive after {GAME_SECONDS} s={alive}, error window '{error}', log lines {len(lines)}, errors {len(bad)}")
    finally:
        kill_tree(launcher.pid)
        for p in game_processes():
            kill_tree(p.pid)
        for log in [GAME / "launcher" / "logs" / "launcher.log", GAME / "user" / "openxcom.log"]:
            if log.exists():
                shutil.copy2(log, OUT / log.name)


def main():
    # игры других сессий (стенд ИИ) не мешают: свою игру прогон ищет только под --dir
    busy = running({"xpiratezlauncher.exe", "xp-release.exe"})
    if busy:
        raise SystemExit(f"already running, not touching: {busy}")
    if SMOKE.exists():
        raise SystemExit(f"{SMOKE} exists: remove it after looking inside")
    if wait_http(URL + "channels/" + o.channel + ".json", 1):
        raise SystemExit(f"port {o.port} is taken")
    OUT.mkdir(parents=True, exist_ok=True)
    link_before = link_key()
    settings_before = SETTINGS.read_bytes()
    sha_before = hashlib.sha256(settings_before).hexdigest()
    (OUT / "settings.before.json").write_bytes(settings_before)
    say(f"settings.json sha {sha_before[:12]} kept in {OUT}; xpiratez link before: {link_before}")

    LAUNCHER.mkdir(parents=True)
    for f in SHIPPED:
        shutil.copy2(REL / f, LAUNCHER / f)
    say(f"release build {product_version(LAUNCHER / 'XPiratezLauncher.exe')} -> {LAUNCHER}")

    serve_log = open(OUT / "serve.log", "wb")
    serve = subprocess.Popen([str(SERVE), "serve", "--repo", o.repo, "--port", str(o.port)],
                             stdout=serve_log, stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
    try:
        status = wait_http(URL + "channels/" + o.channel + ".json", 30)
        if status != 200:
            raise SystemExit(f"xp-release serve does not answer: {status}")
        say(f"xp-release serve on {URL} (pid {serve.pid})")
        update_checks()
        if all(ok for _, ok, _ in results):
            shutil.copytree(UFO, GAME / "UFO")
            gui_checks()
    finally:
        serve.kill()
        serve.wait(10)
        serve_log.close()
        SETTINGS.write_bytes(settings_before)
        sha_after = hashlib.sha256(SETTINGS.read_bytes()).hexdigest()
        say(f"settings.json restored: {'same bytes' if sha_after == sha_before else 'DIFFERENT ' + sha_after[:12]}")
        now = link_key()
        if link_before is None and now is not None:
            delete_tree(LINK_KEY)
            say(f"xpiratez link removed again (was {now}); now {link_key()}")
        say(f"processes left: {running({'xpiratezlauncher.exe', 'xp-release.exe'}) + [p.pid for p in game_processes()]}")
    print()
    for name, ok, detail in results:
        print(("PASS " if ok else "FAIL ") + name + " - " + detail)
    passed = len(results) == 8 and all(ok for _, ok, _ in results)
    print("ALL PASS" if passed else "NOT ALL PASS")
    print(f"logs: {OUT}; the test install stays in {SMOKE} - remove it by hand")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
