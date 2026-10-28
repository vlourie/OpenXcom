#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Лаунчер на mod.io: новый файл на странице мода после выпуска в launcher-stable
(docs/research/modio-launcher-page-2026-10-27.md, раздел 4).

Что выкладывается. Тот же установщик, что сайт раздаёт кнопкой «Скачать» (/download/launcher, R-077):
xp-bootstrap.exe опубликованного выпуска канала под именем XPiratezHD-Setup-<версия>.exe, плюс README.txt,
одним zip. Файл берётся из хранилища выпусков, а не из dist: указатель канала -> манифест (SHA-256 сверяется
с указателем) -> блоб (SHA-256 сверяется с манифестом). Установщик сам ставит лаунчер в
%LOCALAPPDATA%\Programs\XPiratezHD и тянет его файлы с нашего сервера.

    py -3.13 tools/modio_publish.py                       выложить текущий выпуск launcher-stable
    py -3.13 tools/modio_publish.py --dry-run             всё проверить и спросить mod.io, но не выкладывать
    py -3.13 tools/modio_publish.py --offline             только собрать архив, без сети
    py -3.13 tools/modio_publish.py --changelog Выпуск\notes\2026.10.28.en.txt

Версия, которая на mod.io уже есть, второй раз не выкладывается (код 0). Мод - --mod (номер, name_id или ссылка;
release.ps1 берёт его из ModioMod в release_config.json), иначе единственный мод владельца токена в игре 51.

Токен - OAuth 2 с правом записи (https://mod.io/me/access), один в файле %USERPROFILE%\.modio_token
(вне репозитория; другой файл - переменная MODIO_TOKEN_FILE). Токен не печатается.

Коды выхода: 0 - выложено или уже было, 1 - ошибка, 2 - нет файла токена (выкладка пропущена).
"""
import argparse
import hashlib
import io
import json
import os
import sys
import zipfile
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # R-484: иначе cp1252 падает на кириллице
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
GAME_ID = 51
API = f"https://g-{GAME_ID}.modapi.io/v1"
SITE = "https://x-piratez.mywire.org:8443/"
SETUP = "xp-bootstrap.exe"
CHANGELOG_MAX = 50000  # предел поля changelog у mod.io

README = """OXCE-HD Launcher {version} - X-Piratez HD Edition

1. Run XPiratezHD-Setup-{version}.exe.
   It installs the launcher into %LOCALAPPDATA%\\Programs\\XPiratezHD, downloads its files
   from our server and creates shortcuts.
2. In the launcher, point it to your copy of X-COM: UFO Defense / UFO: Enemy Unknown
   (Steam, GOG or a folder) and install X-Piratez HD.
3. The launcher updates itself and the game automatically.

Website, news and support: {site}
X-Piratez was created by Dioxine: https://www.moddb.com/mods/x-piratez
"""


def fail(msg):
    print(f"ОШИБКА: {msg}", file=sys.stderr)
    sys.exit(1)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def read_release(repo, channel):
    """(id, версия, байты установщика) опубликованного выпуска канала, всё сверено по SHA-256."""
    ptr_file = repo / "channels" / f"{channel}.json"
    if not ptr_file.is_file():
        fail(f"нет {ptr_file} - хранилище не то или канал не выпускался (R-499)")
    ptr = json.loads(ptr_file.read_text(encoding="utf-8-sig"))
    rid = ptr["releaseId"]
    raw = (repo / "releases" / rid / "manifest.json").read_bytes()
    if sha256(raw) != ptr["manifestSha256"]:
        fail(f"манифест {rid} не совпадает с указателем канала {channel}")
    man = json.loads(raw.decode("utf-8-sig"))
    entry = next((f for f in man["files"] if f["path"].lower() == SETUP), None)
    if entry is None:
        fail(f"в выпуске {rid} нет {SETUP}")
    sha = entry["sha256"]
    blob = (repo / "blobs" / "sha256" / sha[:2] / sha).read_bytes()
    if sha256(blob) != sha or len(blob) != entry["size"]:
        fail(f"блоб {SETUP} выпуска {rid} не совпадает с манифестом")
    return rid, man["release"]["version"], blob


def build_zip(out_dir, version, setup):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr(f"XPiratezHD-Setup-{version}.exe", setup)
        z.writestr("README.txt", README.format(version=version, site=SITE).replace("\n", "\r\n"))
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"OXCE-HD-Launcher-{version}.zip"
    path.write_bytes(buf.getvalue())
    return path


def read_token():
    path = Path(os.environ.get("MODIO_TOKEN_FILE") or Path.home() / ".modio_token")
    if not path.is_file():
        return None, path
    token = path.read_text(encoding="utf-8-sig").strip()
    return (token or None), path


class Modio:
    def __init__(self, token):
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/json"})

    def call(self, method, path, **kw):
        r = self.s.request(method, API + path, timeout=kw.pop("timeout", 60), **kw)
        if r.status_code >= 400:
            try:
                e = r.json().get("error", {})
                detail = f"{e.get('code')}/{e.get('error_ref')}: {e.get('message')}"
                if e.get("errors"):
                    detail += " " + json.dumps(e["errors"], ensure_ascii=False)
            except ValueError:
                detail = r.text[:300]
            fail(f"mod.io {method} {path} -> HTTP {r.status_code} {detail}")
        return r.json() if r.content else {}

    def find_mod(self, mod):
        """Мод по номеру, имени из адреса (name_id) или ссылке .../m/<name_id>; без него - единственный мод
        владельца токена в игре. Личный токен mod.io может не пускать в /me (403, error_ref 11139) -
        тогда мод задаётся явно, через /me он не ищется."""
        if mod:
            mod = mod.strip().rstrip("/")
            if "/m/" in mod:
                mod = mod.split("/m/")[1].split("/")[0]
            if mod.isdigit():
                return self.call("GET", f"/games/{GAME_ID}/mods/{mod}")
            got = self.call("GET", f"/games/{GAME_ID}/mods", params={"name_id": mod})["data"]
            if not got:
                fail(f"мода «{mod}» в игре {GAME_ID} не видно - нет страницы или токен её не видит")
            return got[0]
        mods = [m for m in self.call("GET", "/me/mods", params={"game_id": GAME_ID})["data"]
                if m.get("game_id") == GAME_ID]
        if not mods:
            fail(f"у владельца токена нет модов в игре {GAME_ID} (OpenXcom) - сначала страница на mod.io")
        if len(mods) > 1:
            fail("модов несколько, выберите --mod: " + "; ".join(f"{m['id']} {m['name']}" for m in mods))
        return mods[0]

    def has_version(self, mod_id, version):
        got = self.call("GET", f"/games/{GAME_ID}/mods/{mod_id}/files", params={"version": version})["data"]
        return [f for f in got if f.get("version") == version]

    def upload(self, mod_id, zip_path, version, changelog):
        data = zip_path.read_bytes()
        form = {"version": version, "changelog": changelog, "active": "true",
                "filehash": hashlib.md5(data).hexdigest()}
        return self.call("POST", f"/games/{GAME_ID}/mods/{mod_id}/files", data=form,
                         files={"filedata": (zip_path.name, data, "application/zip")}, timeout=600)


def main():
    ap = argparse.ArgumentParser(description="лаунчер на mod.io после выпуска launcher-stable")
    ap.add_argument("--repo", default=r"D:\xp-repo", help="хранилище выпусков")
    ap.add_argument("--channel", default="launcher-stable")
    ap.add_argument("--changelog", help="файл «Что нового» по-английски (иначе одна строка с версией)")
    ap.add_argument("--mod", help="мод на mod.io: номер, name_id или ссылка на страницу (иначе ищется через /me)")
    ap.add_argument("--out", default=str(ROOT / "dist" / "_modio"), help="куда положить архив")
    ap.add_argument("--dry-run", action="store_true", help="не выкладывать, только проверить")
    ap.add_argument("--offline", action="store_true", help="только собрать архив, mod.io не спрашивать")
    a = ap.parse_args()

    rid, version, setup = read_release(Path(a.repo), a.channel)
    zip_path = build_zip(Path(a.out), version, setup)
    print(f"выпуск {rid} (канал {a.channel}), версия {version}")
    print(f"архив {zip_path} ({zip_path.stat().st_size / 1e6:.1f} МБ), установщик {len(setup) / 1e6:.1f} МБ")

    changelog = f"OXCE-HD Launcher {version}."
    if a.changelog:
        text = Path(a.changelog).read_text(encoding="utf-8-sig").strip()
        if text:
            changelog = text[:CHANGELOG_MAX]
    print(f"changelog: {len(changelog)} знаков{' из ' + a.changelog if a.changelog else ''}")
    if a.offline:
        return

    token, token_file = read_token()
    if not token:
        print(f"нет токена mod.io в {token_file} - выкладка пропущена", file=sys.stderr)
        sys.exit(2)
    api = Modio(token)
    mod = api.find_mod(a.mod)
    print(f"мод {mod['id']} «{mod['name']}» {mod.get('profile_url', '')}"
          f" (visible={mod.get('visible')}, status={mod.get('status')})")
    have = api.has_version(mod["id"], version)
    if have:
        print(f"версия {version} на mod.io уже есть (файл {have[0]['id']}) - не выкладываю")
        return
    if a.dry_run:
        print(f"--dry-run: выложил бы {zip_path.name} как версию {version}")
        return
    f = api.upload(mod["id"], zip_path, version, changelog)
    print(f"выложено: файл {f.get('id')}, версия {f.get('version')}, {f.get('filesize')} байт,"
          f" проверка антивирусом: virus_status={f.get('virus_status')}")


if __name__ == "__main__":
    main()
