# -*- coding: utf-8 -*-
"""Приёмка этапа 3 (LUA_MODS.md §9): заявка на настоящем сайте, локально на одноразовой базе: архив и токен устройства -> очередь ->
lua_mods.py pull -> автопроверка с боем -> решение -> статус у автора. Моды наши (--own-test-mod): Windows Sandbox здесь не участвует.

XP_TEST_PG - строка подключения к одноразовому Postgres. Станцию и её ключи скрипт не трогает."""
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
MAIN = Path(os.environ.get("XP_MAIN_TREE") or ROOT)
PROJECT = ROOT / "portal/src/Xp.Portal"
WORK = Path(os.environ["TEMP"]) / "lua_stage4_portal"
PORT = 5097
URL = f"http://127.0.0.1:{PORT}"
PG = dict(p.split("=", 1) for p in os.environ["XP_TEST_PG"].split(";") if p)
DB = "xp_lua_path"
PSQL_ENV = dict(os.environ, PGPASSWORD=PG["Password"], PATH="C:/msys64/mingw64/bin;" + os.environ["PATH"])
LUA = 'game.on("newTurnUnit", function(unit, battle, turn, side)\n  game.log("portal path: turn", turn)\nend)\n'
failures = []


def check(what, ok, detail=""):
    print(("OK   " if ok else "FAIL ") + what + (f": {detail}" if detail else ""), flush=True)
    if not ok:
        failures.append(what)


def sql(text, db=DB):
    r = subprocess.run(["C:/msys64/mingw64/bin/psql.exe", "-h", PG["Host"], "-p", PG["Port"], "-U", PG["Username"], "-d", db, "-Atc", text], capture_output=True, text=True, encoding="utf-8", errors="replace", env=PSQL_ENV)
    if r.returncode:
        raise RuntimeError(r.stderr)
    return r.stdout.strip()


def portal_env():
    return dict(os.environ, ASPNETCORE_ENVIRONMENT="Development", ASPNETCORE_URLS=URL, DOTNET_NOLOGO="1",
                ConnectionStrings__Portal=f"Host={PG['Host']};Port={PG['Port']};Database={DB};Username={PG['Username']};Password={PG['Password']}",
                Portal__PublicUrl=URL, Attachments__StorageRoot=str(WORK / "files"), Email__PickupDir=str(WORK / "mail"))


def cli(*args, **env):
    return subprocess.run(["dotnet", "run", "--project", str(PROJECT), "--no-build", "--no-launch-profile", "--", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", env={**portal_env(), **env}, timeout=300)


def http(method, path, token, data=None, headers=None):
    req = urllib.request.Request(URL + path, data=data, method=method, headers={"X-Device-Token": token, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def submit(token, mod, master):
    archive = WORK / f"{mod}.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("metadata.yml", f'id: {mod}\nname: "{mod}"\nversion: 0.1\nmaster: "{master}"\nluaApi: 1\n')
        z.writestr("lua/main.lua", LUA)
    meta = {"id": mod, "version": "0.1", "license": "CC0", "description": "Пишет номер хода в журнал", "rightsConfirmed": True, "language": "ru"}
    boundary = uuid.uuid4().hex
    body = b"".join([
        f'--{boundary}\r\nContent-Disposition: form-data; name="meta"\r\nContent-Type: application/json\r\n\r\n'.encode(), json.dumps(meta).encode(), b"\r\n",
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{mod}.zip"\r\nContent-Type: application/zip\r\n\r\n'.encode(), archive.read_bytes(), b"\r\n",
        f"--{boundary}--\r\n".encode()])
    return http("POST", "/api/v1/lua-mods", token, body, {"Content-Type": f"multipart/form-data; boundary={boundary}", "Idempotency-Key": uuid.uuid4().hex})


def author_status(token, number):
    code, rows = http("GET", "/api/v1/lua-mods", token)
    return next((r["status"] for r in rows if r["number"] == number), f"нет заявки ({code})")


def queue(*args):
    env = dict(os.environ, XP_BOT_CONFIG=str(WORK / "bot.json"), XP_TICKETS_DIR=str(WORK / "tickets"), PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, str(MAIN / "tools/lua_mods.py"), *map(str, args)], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=1500)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sql(f'DROP DATABASE IF EXISTS "{DB}"', "postgres")
    sql(f'CREATE DATABASE "{DB}"', "postgres")
    WORK.mkdir(parents=True, exist_ok=True)
    build = subprocess.run(["dotnet", "build", str(PROJECT), "--nologo", "-v", "q"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    check("сайт собран", build.returncode == 0, build.stdout[-300:] if build.returncode else "")
    r = cli("migrate")
    check("база создана", r.returncode == 0, (r.stdout + r.stderr)[-300:] if r.returncode else "")
    email = "author@example.invalid"
    r = cli("admin", "create", "--email", email, "--name", "Author", XP_ADMIN_PASSWORD="T1-" + secrets.token_urlsafe(18))
    check("пользователь", r.returncode == 0, r.stderr[-300:] if r.returncode else "")
    uid = sql(f"SELECT \"Id\" FROM \"AspNetUsers\" WHERE \"Email\"='{email}'")
    token = secrets.token_urlsafe(32)
    sql(f"INSERT INTO \"DeviceTokens\" (\"Id\",\"UserId\",\"TokenHash\",\"Name\",\"CreatedAt\") VALUES ('{uuid.uuid4()}','{uid}','{hashlib.sha256(token.encode()).hexdigest()}','e2e',now())")
    r = cli("admin", "bot", "create", "--name", "lua", "--categories", "luamod")
    check("ключ бота с категорией luamod", r.returncode == 0, r.stderr[-300:] if r.returncode else "")
    (WORK / "bot.json").write_text(json.dumps({"url": URL, "key": r.stdout.strip().splitlines()[-1]}), encoding="utf-8")
    r2 = cli("admin", "bot", "create", "--name", "plain")   # без --categories: ключ обычного разбора тикетов
    site = subprocess.Popen(["dotnet", "run", "--project", str(PROJECT), "--no-build", "--no-launch-profile"], env=portal_env(), stdout=open(WORK / "site.log", "w", encoding="utf-8"), stderr=subprocess.STDOUT)
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(URL + "/healthz", timeout=2)
                break
            except urllib.error.HTTPError:
                break
            except OSError:
                time.sleep(1)
        numbers = {}
        for mod, master, label in (("path_pirates", "piratez", "Пиратки"), ("path_ufo", "xcom1", "UFO")):
            code, view = submit(token, mod, master)
            check(f"{label}: заявка принята", code == 201 and view.get("status") == "queue", str(view)[:300])
            numbers[label] = view["number"]
            check(f"{label}: автор видит очередь", author_status(token, view["number"]) == "queue")
        # обычный ключ разбора тикетов заявок не видит
        plain = dict(os.environ, XP_BOT_CONFIG=str(WORK / "bot_plain.json"), XP_TICKETS_DIR=str(WORK / "tickets_plain"), PYTHONIOENCODING="utf-8")
        (WORK / "bot_plain.json").write_text(json.dumps({"url": URL, "key": r2.stdout.strip().splitlines()[-1]}), encoding="utf-8")
        seen = subprocess.run([sys.executable, str(MAIN / "tools/tickets.py"), "pull", "--no-take"], capture_output=True, text=True, encoding="utf-8", errors="replace", env=plain)
        check("обычный разбор заявок не видит", "новых тикетов нет" in seen.stdout, seen.stdout[-200:] + seen.stderr[-200:])

        # файл отдаётся только после антивируса (круг сканера 10 с): pull докачивает то, что ждало
        r = queue("pull", "--no-take")
        check("очередь забрала обе", r.returncode == 0 and "path_pirates" in r.stdout and "path_ufo" in r.stdout, r.stdout[-400:] + r.stderr[-300:])
        for _ in range(12):
            if len(list((WORK / "tickets").glob("XP-*/files/*.zip"))) == 2:
                break
            time.sleep(10)
            queue("pull", "--no-take")
        check("архивы докачаны после антивируса", len(list((WORK / "tickets").glob("XP-*/files/*.zip"))) == 2)
        for label, number in numbers.items():
            r = queue("check", number, "--own-test-mod")
            check(f"{label}: автопроверка с боем прошла", r.returncode == 0, r.stdout[-300:] + r.stderr[-300:])
            check(f"{label}: автор видит разбор", author_status(token, number) == "review")
            r = queue("reply", number, "Спасибо, одобрено.")
            print((r.stdout + r.stderr).strip()[-200:])
            r = queue("status", number, "Resolved", "--note", "Одобрено: приёмочный прогон")
            check(f"{label}: решение дошло до автора", author_status(token, number) == "approved", r.stdout[-200:] + r.stderr[-200:])
    finally:
        site.terminate()
        try:
            site.wait(20)
        except subprocess.TimeoutExpired:
            site.kill()
        subprocess.run(["taskkill", "/f", "/im", "Xp.Portal.exe"], capture_output=True)
    sql(f'DROP DATABASE IF EXISTS "{DB}" WITH (FORCE)', "postgres")
    shutil.rmtree(WORK, ignore_errors=True)
    print("ИТОГ:", "PASS" if not failures else f"FAIL {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
