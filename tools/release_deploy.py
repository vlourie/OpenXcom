#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Выкладка готового выпуска игрокам одним запуском (после editq: архив dist\xp-releases_*.zip).

    py -3 tools/release_deploy.py                 последний архив из dist
    py -3 tools/release_deploy.py <архив.zip>     указанный
    py -3 tools/release_deploy.py --no-tickets    без закрытия тикетов (сессия не командир)

По шагам, первый сбой останавливает:
 1. архив на станцию C:\XPiratezModHD\ (scp), хэш SHA-256 там сверяется с местным; файл с тем же именем
    и другим хэшем не перезаписывается - остановка;
 2. station.ps1 releases - разворачивает выпуск, каналы переключаются;
 3. /releases/channels/stable.json на портале должен показать тот же выпуск, что назвал station.ps1;
 4. зеркало на Google Диске: mirror_gdrive.py sync, затем sync --check - «не хватает 0»
    (Vitali 11.11: на Диск выпуск попадает сам, утром 11.11 его забыли - не хватало 1,66 ГБ);
 5. tickets.py release-sync - закрыть тикеты, чьё исправление вышло.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOST = "user@100.83.70.95"
KEY = str(Path.home() / ".ssh" / "oxce_worker")
DROP = "C:\\XPiratezModHD\\"
PORTAL = "https://x-piratez.mywire.org:8443/releases/channels/stable.json"
SSH = ["ssh", "-i", KEY, "-o", "BatchMode=yes", HOST]


def step(msg):
    print(f"==> {msg}", flush=True)


def fail(msg):
    print(f"!! {msg}", flush=True)
    sys.exit(1)


def remote(cmd, timeout=900):
    """Команда на станции (там cmd: ';' не разделяет, R-603). Предупреждения ssh о ключах убираются."""
    p = subprocess.run(SSH + [cmd], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    out = "\n".join(l for l in (p.stdout + p.stderr).splitlines()
                    if not l.startswith("** ") and "post-quantum" not in l)
    return p.returncode, out


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def remote_sha(name):
    rc, out = remote(f"certutil -hashfile {DROP}{name} SHA256", timeout=900)
    m = re.search(r"^([0-9a-f]{64})$", out.replace(" ", ""), re.M)
    return m.group(1) if rc == 0 and m else None


def py(*args, timeout=3600):
    return subprocess.run([sys.executable, *args], cwd=ROOT, timeout=timeout,
                          env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("zip", nargs="?")
    ap.add_argument("--no-tickets", action="store_true")
    a = ap.parse_args()
    if a.zip:
        zp = Path(a.zip).resolve()
    else:
        zips = sorted((ROOT / "dist").glob("xp-releases_*.zip"), key=lambda p: p.stat().st_mtime)
        if not zips:
            fail("в dist нет xp-releases_*.zip")
        zp = zips[-1]
    if not zp.is_file():
        fail(f"нет файла {zp}")
    name = zp.name

    step(f"архив {name}, {zp.stat().st_size / 1e9:.2f} ГБ: хэш")
    local = sha256(zp)
    print(f"   местный {local}")

    rc, out = remote(f"if exist {DROP}{name} (echo EXISTS) else (echo FREE)", timeout=60)
    if rc != 0:
        fail(f"станция не отвечает: {out[-300:]}")
    if "EXISTS" in out:
        there = remote_sha(name)
        if there != local:
            fail(f"на станции уже лежит {name} с другим хэшем ({there}) - не перезаписываю, разберись руками")
        step("на станции уже тот же архив - заливку пропускаю")
    else:
        step(f"заливаю на станцию {DROP}")
        p = subprocess.run(["scp", "-i", KEY, "-o", "BatchMode=yes", str(zp), f"{HOST}:C:/XPiratezModHD/"], timeout=7200)
        if p.returncode != 0:
            fail("scp не прошёл")
        there = remote_sha(name)
        if there != local:
            fail(f"хэш на станции {there} не совпал с местным - выпуск не разворачиваю")
        print("   хэш на станции совпал")

    step("station.ps1 releases")
    rc, out = remote(f"cd /d C:\\xp-portal\\portal\\deploy && powershell -ExecutionPolicy Bypass -File .\\station.ps1 releases {DROP}{name}",
                     timeout=1800)
    print("\n".join(out.splitlines()[-8:]))
    m = re.search(r"^stable\s+->\s+(\S+)", out, re.M)
    if rc != 0 or not m:
        fail("station.ps1 закончил с ошибкой или не назвал выпуск канала stable")
    rid = m.group(1)

    step("канал stable на портале")
    try:
        with urllib.request.urlopen(PORTAL, timeout=30) as r:
            live = json.loads(r.read().decode("utf-8")).get("releaseId")
    except Exception as e:
        fail(f"портал не ответил: {e}")
    if live != rid:
        fail(f"на портале {live}, а станция выставила {rid}")
    print(f"   stable = {live}")

    step("зеркало на Google Диске")
    if py("tools/mirror_gdrive.py", "sync").returncode != 0:
        fail("mirror_gdrive.py sync не прошёл (токен Google? - py -3 tools/mirror_gdrive.py auth); выпуск у игроков со станции уже есть")
    chk = subprocess.run([sys.executable, "tools/mirror_gdrive.py", "sync", "--check"], cwd=ROOT, capture_output=True, text=True,
                         encoding="utf-8", errors="replace", env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
    print(chk.stdout.strip())
    if chk.returncode != 0 or "не хватает 0 " not in chk.stdout:
        fail("на Диске не всё - повтори py -3 tools/mirror_gdrive.py sync")

    if not a.no_tickets:
        step("тикеты, чьё исправление вышло")
        py("tools/tickets.py", "release-sync")

    print(f"готово: {rid} у игроков со станции и с Google Диска")


if __name__ == "__main__":
    main()
