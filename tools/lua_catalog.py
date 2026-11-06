# -*- coding: utf-8 -*-
"""Каталог одобренных Lua-модов (docs/portal/LUA_MODS.md §8.4): то, что выпуск ставит как необязательные компоненты cm-<id>.

Лежит в Выпуск/lua_catalog: папки cm-<id>, catalog.json с sha256 каждого файла, revoked.json для манифеста.
Добавить мод можно только словом Vitali: скрипт этого проверить не может, поэтому в записи есть номер заявки.

py -3.13 tools/lua_catalog.py add <папка clean из автопроверки> --ticket XP-000123
py -3.13 tools/lua_catalog.py revoke <id> --reason-ru "..." --reason-en "..."
py -3.13 tools/lua_catalog.py verify
py -3.13 tools/lua_catalog.py sync --stage dist/_stage      каталог в стейдж: снимает прошлые cm-*, кладёт текущие (шаг release.ps1)
py -3.13 tools/lua_catalog.py min-launcher 0.6.0            лаунчер, начиная с которого каталог работает: release.ps1 требует его в выпуске с модами
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lua_mod_check  # noqa: E402

HOME = Path(os.environ.get("XP_LUA_CATALOG") or ROOT / "Выпуск" / "lua_catalog")
PREFIX = "cm-"
ENC = "utf-8-sig"
ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")


def die(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)


def load():
    path = HOME / "catalog.json"
    if path.exists():
        return json.loads(path.read_text(encoding=ENC))
    return {"schema": 1, "minLauncher": "", "mods": [], "revoked": []}


def save(cat):
    HOME.mkdir(parents=True, exist_ok=True)
    (HOME / "catalog.json").write_text(json.dumps(cat, ensure_ascii=False, indent=2) + "\n", encoding=ENC, newline="\n")
    # манифест читает System.Text.Json: без спецификации
    (HOME / "revoked.json").write_text(json.dumps(cat["revoked"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def walk(top):
    """Все файлы папки; соединение или ссылка в папке из песочницы - отказ: она могла писать туда что угодно."""
    files = {}
    for base, dirs, names in os.walk(top):
        for name in dirs + names:
            full = os.path.join(base, name)
            if os.path.islink(full) or os.path.isjunction(full):
                die(f"{full}: ссылка внутри мода")
        for name in names:
            full = Path(base) / name
            files[full.relative_to(top).as_posix()] = full
    return files


def checked_clean(clean):
    """Папка clean пришла из песочницы, поэтому те же правила архива ещё раз, уже на этой стороне."""
    files = walk(clean)
    if "metadata.yml" not in files or "lua/main.lua" not in files:
        die(f"{clean}: нет metadata.yml или lua/main.lua, это не папка clean автопроверки")
    for rel in files:
        problem = lua_mod_check.check_path(rel)
        if problem:
            die(f"{rel}: {problem[1]}")
    meta, bad = lua_mod_check.parse_metadata(files["metadata.yml"].read_text(encoding="utf-8-sig"))
    if bad:
        die(f"metadata.yml: не разобраны строки {bad}")
    if not ID.match(meta.get("id", "")) or meta.get("isMaster", "") == "true":
        die(f"id '{meta.get('id')}' не подходит для каталога")
    return meta, files


def ours():
    cfg = json.loads((ROOT / "tools/build/build_config.json").read_text(encoding=ENC))
    return {m.lower() for m in cfg["Mods"]}


def cmd_add(a):
    meta, files = checked_clean(a.clean)
    mod = meta["id"]
    if mod in ours():
        die(f"'{mod}': так называется мод выпуска")
    cat = load()
    folder = HOME / (PREFIX + mod)
    shutil.rmtree(folder, ignore_errors=True)
    for rel, src in files.items():
        target = folder / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, target)
    cat["mods"] = [m for m in cat["mods"] if m["id"] != mod] + [{
        "id": mod, "version": meta.get("version", ""), "folder": PREFIX + mod, "ticket": a.ticket,
        "approved": datetime.date.today().isoformat(), "files": {rel: sha(folder / rel) for rel in sorted(files)}}]
    cat["mods"].sort(key=lambda m: m["id"])
    # снова одобрен: отзыв старой версии больше не про него
    cat["revoked"] = [r for r in cat["revoked"] if r["mod"] != mod]
    save(cat)
    print(f"{PREFIX}{mod} {meta.get('version', '')}: файлов {len(files)}. Выйдет с ближайшим выпуском.")


def cmd_revoke(a):
    cat = load()
    entry = next((m for m in cat["mods"] if m["id"] == a.id), None)
    if entry is None:
        die(f"в каталоге нет '{a.id}'")
    shutil.rmtree(HOME / entry["folder"], ignore_errors=True)
    cat["mods"].remove(entry)
    cat["revoked"].append({"mod": entry["id"], "version": entry["version"], "folder": entry["folder"], "reason": {"ru": a.reason_ru, "en": a.reason_en}})
    save(cat)
    print(f"{entry['folder']} отозван. Дальше срочный выпуск: только он снимет файлы и скажет игрокам почему.")


def verify(cat):
    problems = []
    listed = {m["folder"] for m in cat["mods"]}
    if HOME.exists():
        for d in HOME.iterdir():
            if d.is_dir() and d.name not in listed:
                problems.append(f"{d.name}: папка не в списке")
    for m in cat["mods"]:
        have = {rel: sha(p) for rel, p in walk(HOME / m["folder"]).items()} if (HOME / m["folder"]).is_dir() else {}
        if have != m["files"]:
            problems.append(f"{m['folder']}: файлы не сходятся со списком: {sorted(set(have.items()) ^ set(m['files'].items()))[:3]}")
    return problems


def cmd_verify(a):
    problems = verify(load())
    for p in problems:
        print(p)
    print("сходится" if not problems else f"расхождений: {len(problems)}")
    return 1 if problems else 0


def cmd_sync(a):
    cat = load()
    problems = verify(cat)
    if problems:
        die("каталог не сходится, в выпуск не кладу: " + "; ".join(problems))
    mods = a.stage / "user" / "mods"
    if not mods.is_dir():
        die(f"{mods}: нет такой папки")
    for d in list(mods.iterdir()):
        if d.name.startswith(PREFIX):
            # соединение снимать только os.rmdir (R-047)
            if os.path.isjunction(d):
                os.rmdir(d)
            else:
                shutil.rmtree(d)
    for m in cat["mods"]:
        shutil.copytree(HOME / m["folder"], mods / m["folder"])
    print(f"каталог в стейдже: модов {len(cat['mods'])}, отозванных {len(cat['revoked'])}")
    return 0


def cmd_min_launcher(a):
    cat = load()
    cat["minLauncher"] = a.version
    save(cat)
    print(f"каталог: лаунчер от {a.version}")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Каталог одобренных Lua-модов")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("add"); s.add_argument("clean", type=Path); s.add_argument("--ticket", required=True); s.set_defaults(fn=cmd_add)
    s = sub.add_parser("revoke"); s.add_argument("id"); s.add_argument("--reason-ru", required=True); s.add_argument("--reason-en", required=True); s.set_defaults(fn=cmd_revoke)
    s = sub.add_parser("verify"); s.set_defaults(fn=cmd_verify)
    s = sub.add_parser("sync"); s.add_argument("--stage", type=Path, required=True); s.set_defaults(fn=cmd_sync)
    s = sub.add_parser("min-launcher"); s.add_argument("version"); s.set_defaults(fn=cmd_min_launcher)
    a = ap.parse_args()
    return a.fn(a) or 0


if __name__ == "__main__":
    sys.exit(main())
