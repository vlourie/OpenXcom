#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Автопроверка заявки на Lua-мод (docs/portal/LUA_MODS.md §8.2). Только стандартная библиотека: в песочнице больше ничего нет.

ЧУЖОЙ АРХИВ - ТОЛЬКО В ОДНОРАЗОВОЙ ИЗОЛИРОВАННОЙ СРЕДЕ: tools/lua_mod_sandbox.py. Чужие YAML и PNG читает наш C++, а песочница
Lua это не закрывает. Вне Windows Sandbox скрипт работает только с --own-test-mod: наши собственные тестовые архивы.

Стадии:
  1 архив      пути, расширения, размеры; битый zip
  2 метаданные id, master, luaApi, движок, lua/main.lua
  3 Lua        компиляция каждого файла движком (-modcheck) без исполнения; вызовы вне API и подозрительное - сигнал разбору
  4 данные     PNG и WAV пересохраняются (в clean/ только то, что нужно игре), YAML читает движок, конфликты с hd (R-175)
  5 запуск     невидимая игра с модом и без него, те же бои: падение, зависание, ошибки Lua, лимиты, время

Итог: <out>/report.json, <out>/report.md, <out>/clean/ (пересохранённый мод, он и идёт в каталог). Код выхода: 0 пройдено,
1 отказ, 2 проверка не довела дело до конца (нет движка, не тот запуск): это не решение о моде.

py -3.13 tools/lua_mod_check.py <архив.zip> --out <папка> --own-test-mod
py -3.13 tools/lua_mod_check.py <архив.zip> --out <папка> --exe <игра> --game <папка игры> [--battle] [--turns 2]
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import time
import wave
import zipfile
import zlib
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
NAMES = ROOT / "portal/src/Xp.Launcher.Core/Docs/lua_api.names.txt"
BENCH = ROOT / "tools/hdbench.py"
SAVE = ROOT / "tools/lua_stage1/lua_battle.sav"

# те же пределы в лаунчере и на сайте: portal/src/Xp.Manifest/LuaModArchive.cs
MAX_ARCHIVE = 50 * 1024 * 1024
MAX_UNPACKED = 200 * 1024 * 1024
MAX_FILE = 50 * 1024 * 1024
MAX_FILES = 2000
ALLOWED = {".lua", ".yml", ".rul", ".txt", ".md", ".png", ".wav"}
EXECUTABLE = {".exe", ".dll", ".bat", ".cmd", ".com", ".ps1", ".psm1", ".scr", ".vbs", ".vbe", ".js", ".jse", ".msi", ".lnk", ".sh", ".jar", ".pyd", ".py", ".hta", ".wsf", ".reg", ".cpl", ".sys", ".so"}
TEXT = {".lua", ".yml", ".rul", ".txt", ".md"}
RESERVED = {"con", "prn", "aux", "nul"} | {f"com{i}" for i in range(1, 10)} | {f"lpt{i}" for i in range(1, 10)}
ENGINES = {"", "Extended", "OXCE-HD"}
PNG_MAX_SIDE = 16384
LONG_LINE = 2000
LONG_STRING = 4000
ENCODED_RUN = 512
ESCAPES = 200
STRING_METHODS = {"byte", "find", "format", "gmatch", "gsub", "len", "lower", "match", "rep", "reverse", "sub", "upper"}
ESCAPE_NAMES = {"io", "os", "debug", "package", "coroutine"}
ESCAPE_CALLS = {"require", "load", "loadstring", "loadfile", "dofile", "collectgarbage"}


class Report:
    def __init__(self):
        self.errors = []
        self.signals = []
        self.files = []
        self.mod = {}
        self.stages = {}
        self.unfinished = []

    def error(self, stage, code, text, file=""):
        self.errors.append({"stage": stage, "code": code, "file": file, "text": text})

    def signal(self, stage, code, text, file=""):
        self.signals.append({"stage": stage, "code": code, "file": file, "text": text})

    def verdict(self):
        return "refuse" if self.errors else "unfinished" if self.unfinished else "pass"


# ---- 1. архив ----

def check_path(name):
    """Причина отказа по имени записи, или None. Лаунчер делает то же (LuaModArchive.cs)."""
    if "\\" in name or ":" in name or name.startswith("/") or "\x00" in name:
        return "path_absolute", "абсолютный путь или недопустимый символ в имени"
    parts = PurePosixPath(name).parts
    if ".." in name.split("/"):
        return "path_parent", "путь выходит из папки мода (..)"
    for p in parts:
        if p != p.strip() or p.endswith("."):
            return "path_name", "имя с пробелом или точкой на конце"
        if p.split(".")[0].lower() in RESERVED:
            return "path_name", "зарезервированное имя Windows"
    ext = PurePosixPath(name).suffix.lower()
    if ext == ".luac":
        return "lua_bytecode", "скомпилированный Lua (.luac): нужен исходный текст"
    if ext in EXECUTABLE:
        return "file_executable", f"исполняемый файл ({ext}) в архиве мода запрещён"
    if ext not in ALLOWED:
        return "file_type", f"тип файла {ext or '(без расширения)'} не разрешён; можно: {', '.join(sorted(ALLOWED))}"
    return None


def read_archive(path, rep):
    """Имя -> байты, только если весь архив чист: распаковка идёт после проверки заголовков."""
    size = path.stat().st_size
    if size > MAX_ARCHIVE:
        rep.error("archive", "archive_too_large", f"архив {size} байт больше предела {MAX_ARCHIVE}")
        return None
    try:
        with zipfile.ZipFile(path) as z:
            infos = z.infolist()
            names = [i for i in infos if not i.is_dir()]
            if len(names) > MAX_FILES:
                rep.error("archive", "too_many_files", f"файлов {len(names)} больше предела {MAX_FILES}")
                return None
            if not names:
                rep.error("archive", "archive_empty", "архив пуст")
                return None
            total = 0
            seen = set()
            for i in names:
                # zipfile сам меняет обратную косую на прямую: смотреть надо на то, что лежит в архиве
                bad = check_path(i.orig_filename)
                if bad:
                    rep.error("archive", bad[0], bad[1], i.filename)
                if i.flag_bits & 1:
                    rep.error("archive", "archive_encrypted", "файл в архиве зашифрован", i.filename)
                if i.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                    rep.error("archive", "archive_method", "неизвестный способ сжатия", i.filename)
                if (i.external_attr >> 16) & 0o170000 == 0o120000:
                    rep.error("archive", "archive_link", "символическая ссылка в архиве", i.filename)
                if i.file_size > MAX_FILE:
                    rep.error("archive", "file_too_large", f"файл {i.file_size} байт больше предела {MAX_FILE}", i.filename)
                key = i.filename.lower()
                if key in seen:
                    rep.error("archive", "path_duplicate", "два файла с одним именем без учёта регистра", i.filename)
                seen.add(key)
                total += i.file_size
            if total > MAX_UNPACKED:
                rep.error("archive", "unpacked_too_large", f"распакованный размер {total} больше предела {MAX_UNPACKED}")
            if rep.errors:
                return None
            data = {}
            for i in names:
                # заголовок мог соврать о размере: читаем не больше заявленного и сверяем CRC самим zipfile
                with z.open(i) as f:
                    body = f.read(i.file_size + 1)
                if len(body) != i.file_size:
                    rep.error("archive", "archive_corrupt", "размер файла не совпал с заголовком архива", i.filename)
                    return None
                data[i.filename] = body
            return data
    except (zipfile.BadZipFile, EOFError, OSError, zlib.error, NotImplementedError, RuntimeError) as e:
        rep.error("archive", "archive_corrupt", f"архив не читается: {e}")
        return None


# ---- 2. метаданные ----

def parse_metadata(text):
    """Плоский разбор metadata.yml: строка верхнего уровня без двоеточия - ошибка. Настоящий YAML дальше читает движок."""
    values, bad = {}, []
    for number, line in enumerate(text.lstrip("\ufeff").splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or line[0] in " \t" or stripped == "---":
            continue
        m = re.match(r"^([A-Za-z_][\w-]*)\s*:(?:\s+(.*))?$", stripped)
        if not m:
            bad.append(number)
            continue
        value = (m.group(2) or "").split(" #")[0].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[m.group(1)] = value
    return values, bad


def check_metadata(data, rep, api):
    if "metadata.yml" not in data:
        rep.error("metadata", "metadata_missing", "нет metadata.yml в корне архива", "metadata.yml")
        return
    try:
        text = data["metadata.yml"].decode("utf-8")
    except UnicodeDecodeError:
        rep.error("metadata", "metadata_encoding", "metadata.yml не в UTF-8", "metadata.yml")
        return
    values, bad = parse_metadata(text)
    if bad:
        rep.error("metadata", "metadata_broken", f"metadata.yml не разбирается, строки {bad[:5]}", "metadata.yml")
    mod_id = values.get("id", "")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,39}", mod_id):
        rep.error("metadata", "metadata_id", f"id '{mod_id}': нужны строчные латинские буквы, цифры, _ и -, до 40 знаков", "metadata.yml")
    if not values.get("master"):
        rep.error("metadata", "metadata_master", "нет master: для какой игры мод", "metadata.yml")
    elif values["master"] == "*":
        rep.signal("metadata", "master_any", "master: \"*\", мод включится в любой игре: проверить, работает ли он без Пираток")
    if not values.get("version"):
        rep.error("metadata", "metadata_version", "нет version", "metadata.yml")
    lua_api = values.get("luaApi", "")
    if not lua_api.isdigit() or not 1 <= int(lua_api) <= api:
        rep.error("metadata", "metadata_luaapi", f"luaApi '{lua_api}': нужно целое от 1 до {api}", "metadata.yml")
    engine = values.get("requiredExtendedEngine", "")
    if engine not in ENGINES:
        rep.error("metadata", "metadata_engine", f"requiredExtendedEngine '{engine}': наша сборка так не отвечает", "metadata.yml")
    if values.get("isMaster", "").lower() == "true":
        rep.signal("metadata", "is_master", "isMaster: true, мод объявляет себя отдельной игрой")
    if "lua/main.lua" not in data:
        rep.error("metadata", "lua_main_missing", "нет lua/main.lua: игра запускает этот файл", "lua/main.lua")
    rep.mod = {k: values.get(k, "") for k in ("id", "name", "version", "master", "luaApi", "requiredExtendedEngine")}


# ---- 3. Lua ----

def load_names():
    names = {"event": set(), "const": set(), "base": set(), "method": set()}
    api = 1
    for line in NAMES.read_text(encoding="utf-8").splitlines():
        kind, name = line.split("\t")
        if kind == "api":
            api = int(name)
        else:
            names[kind].add(name)
    return names, api


def strip_lua(text):
    """Код без комментариев и строк, и сами строки отдельно. Настоящий лексер не нужен: файл уже скомпилирован движком."""
    code, strings = [], []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if text.startswith("--", i):
            m = re.match(r"--\[(=*)\[", text[i:i + 80])
            if m:
                end = text.find("]" + m.group(1) + "]", i)
                i = n if end < 0 else end + len(m.group(1)) + 2
            else:
                end = text.find("\n", i)
                i = n if end < 0 else end
            continue
        m = re.match(r"\[(=*)\[", text[i:i + 80]) if c == "[" else None
        if m:
            close = "]" + m.group(1) + "]"
            end = text.find(close, i + len(m.group(0)))
            end = n if end < 0 else end
            strings.append(text[i + len(m.group(0)):end])
            code.append('""')
            i = end + len(close)
            continue
        if c in "\"'":
            j = i + 1
            while j < n and text[j] != c and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            strings.append(text[i + 1:j])
            code.append('""')
            i = j + 1
            continue
        code.append(c)
        i += 1
    return "".join(code), strings


def scan_lua(path, text, names, rep):
    code, strings = strip_lua(text)
    if not path.startswith("lua/"):
        rep.signal("lua", "lua_outside", "файл Lua вне папки lua/: игра его сама не запускает", path)
    for m in re.finditer(r"\b([A-Za-z_]\w*)\s*\.", code):
        if m.group(1) in ESCAPE_NAMES:
            rep.signal("lua", "api_escape", f"обращение к {m.group(1)}: в песочнице его нет, вызов даст ошибку", path)
    for m in re.finditer(r"(?<![.:\w])([A-Za-z_]\w*)\s*\(", code):
        if m.group(1) in ESCAPE_CALLS:
            rep.signal("lua", "api_escape", f"вызов {m.group(1)}: в песочнице его нет", path)
    if re.search(r"\bstring\s*\.\s*dump\b", code):
        rep.signal("lua", "api_escape", "string.dump: в песочнице его нет", path)
    for m in re.finditer(r"\bgame\s*\.\s*(\w+)", code):
        if m.group(1) not in {"on", "log"} and m.group(1) not in names["const"]:
            rep.signal("lua", "api_unknown", f"game.{m.group(1)}: такого в API нет", path)
    for m in re.finditer(r":\s*([A-Za-z_]\w*)\s*[(\"'{]", code):
        if m.group(1) not in names["method"] and m.group(1) not in STRING_METHODS:
            rep.signal("lua", "api_unknown", f":{m.group(1)}(): такого метода в API нет", path)
    for m in re.finditer(r"\bgame\s*\.\s*on\s*\(\s*[\"']([^\"']*)[\"']", text):
        if m.group(1) not in names["event"]:
            rep.signal("lua", "api_event", f"обработчик '{m.group(1)}': такого события в API нет", path)
    if any(len(line) > LONG_LINE for line in text.splitlines()):
        rep.signal("lua", "long_line", f"строка кода длиннее {LONG_LINE} знаков: прочитать глазами", path)
    for s in strings:
        if len(s) > LONG_STRING:
            rep.signal("lua", "long_string", f"строковая константа {len(s)} знаков", path)
        if re.search(r"[A-Za-z0-9+/=]{%d,}" % ENCODED_RUN, s):
            rep.signal("lua", "encoded_block", "похоже на закодированный блок (base64)", path)
        if len(re.findall(r"\\(?:x[0-9a-fA-F]{2}|\d{1,3})", s)) > ESCAPES:
            rep.signal("lua", "encoded_block", "много числовых экранирований: похоже на спрятанные байты", path)


def native_check(exe, folder, out, rep):
    """Движок компилирует Lua и читает YAML без исполнения. Нет итоговой строки - парсер упал на чужом файле."""
    report = out / "modcheck.txt"
    report.unlink(missing_ok=True)
    # сначала сам движок на пустой папке: не запустился он (нет библиотек, старая сборка) - это не вина мода
    empty = out / "empty"
    empty.mkdir(exist_ok=True)
    try:
        probe = subprocess.run([str(exe), "-modcheck", str(empty), str(report)], capture_output=True, timeout=30).returncode
    except (OSError, subprocess.TimeoutExpired) as e:
        probe = str(e)
    empty.rmdir()
    if probe != 0 or not report.exists():
        rep.unfinished.append(f"компиляция Lua и чтение YAML: движок не запустился ({probe})")
        return
    report.unlink()
    try:
        code = subprocess.run([str(exe), "-modcheck", str(folder), str(report)], capture_output=True, timeout=120).returncode
    except subprocess.TimeoutExpired:
        rep.error("data", "parser_hang", "движок завис на разборе файлов мода")
        return
    lines = report.read_text(encoding="utf-8", errors="replace").splitlines() if report.exists() else []
    if not lines or not lines[-1].startswith("done\t"):
        rep.error("data", "parser_crash", f"движок упал на разборе файлов мода, код {code}; разобрано файлов {len(lines)}")
        return
    for line in lines[:-1]:
        part = line.split("\t")
        if part[0] == "bad":
            ext = PurePosixPath(part[1]).suffix.lower()
            stage, what = ("lua", "lua_syntax") if ext == ".lua" else ("data", "yaml_broken")
            rep.error(stage, what, ("ошибка компиляции Lua: " if ext == ".lua" else "YAML не читается: ") + part[2], part[1])


# ---- 4. данные ----

def png_chunks(body):
    if body[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("нет подписи PNG")
    at = 8
    while True:
        if at + 12 > len(body):
            raise ValueError("файл обрезан")
        length, kind = struct.unpack(">I4s", body[at:at + 8])
        end = at + 8 + length
        if end + 4 > len(body):
            raise ValueError("файл обрезан")
        payload = body[at + 8:end]
        if struct.unpack(">I", body[end:end + 4])[0] != zlib.crc32(kind + payload):
            raise ValueError(f"контрольная сумма блока {kind.decode('latin1')} не сошлась")
        yield kind, payload
        at = end + 4
        if kind == b"IEND":
            return


def png_chunk(kind, payload):
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))


def resave_png(body):
    """Только то, что нужно игре: заголовок, палитра, прозрачность, пиксели. Индексы палитры не меняются, чужие блоки и хвост уходят."""
    head, palette, trans, idat = None, None, None, bytearray()
    for kind, payload in png_chunks(body):
        if kind == b"IHDR":
            head = payload
        elif kind == b"PLTE":
            palette = payload
        elif kind == b"tRNS":
            trans = payload
        elif kind == b"IDAT":
            idat += payload
        elif kind == b"IEND":
            pass
        elif not kind[0] & 0x20:
            raise ValueError(f"неизвестный обязательный блок {kind.decode('latin1')}")
    if head is None or len(head) != 13:
        raise ValueError("нет заголовка")
    width, height, depth, colour, method, flt, interlace = struct.unpack(">IIBBBBB", head)
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(colour)
    if not channels or depth not in (1, 2, 4, 8, 16) or method or flt:
        raise ValueError("неизвестный формат пикселей")
    if not 0 < width <= PNG_MAX_SIDE or not 0 < height <= PNG_MAX_SIDE:
        raise ValueError(f"размер {width}x{height} вне предела {PNG_MAX_SIDE}")
    if interlace:
        raise ValueError("чересстрочный PNG: сохраните без чересстрочности")
    if colour == 3 and palette is None:
        raise ValueError("индексный PNG без палитры")
    stride = (width * channels * depth + 7) // 8 + 1
    expected = stride * height
    inflate = zlib.decompressobj()
    # распаковка не больше ожидаемого: сжатая бомба упрётся здесь
    pixels = inflate.decompress(bytes(idat), expected + 1)
    if len(pixels) != expected:
        raise ValueError("пикселей не столько, сколько заявлено в заголовке")
    if any(f > 4 for f in pixels[0::stride]):
        raise ValueError("неверный фильтр строки")
    out = bytearray(b"\x89PNG\r\n\x1a\n") + png_chunk(b"IHDR", head)
    if palette is not None:
        out += png_chunk(b"PLTE", palette)
    if trans is not None:
        out += png_chunk(b"tRNS", trans)
    out += png_chunk(b"IDAT", zlib.compress(pixels, 9)) + png_chunk(b"IEND", b"")
    return bytes(out)


def resave_wav(body, tmp):
    src = tmp / "in.wav"
    dst = tmp / "out.wav"
    src.write_bytes(body)
    with wave.open(str(src), "rb") as r:
        params = r.getparams()
        frames = r.readframes(params.nframes)
    if params.sampwidth not in (1, 2) or not 1 <= params.nchannels <= 2 or len(frames) != params.nframes * params.nchannels * params.sampwidth:
        raise ValueError("нужен обычный WAV: 8 или 16 бит, моно или стерео")
    with wave.open(str(dst), "wb") as w:
        w.setparams(params)
        w.writeframes(frames)
    return dst.read_bytes()


def check_data(data, clean, out, rep):
    tmp = out / "tmp"
    tmp.mkdir(exist_ok=True)
    for name, body in sorted(data.items()):
        ext = PurePosixPath(name).suffix.lower()
        action = "copied"
        result = body
        try:
            if ext in TEXT:
                if body.startswith(b"\x1bLua"):
                    raise ValueError("скомпилированный Lua под видом текста")
                if b"\x00" in body:
                    raise ValueError("нулевые байты в текстовом файле")
                body.decode("utf-8")
            elif ext == ".png":
                result = resave_png(body)
                action = "resaved"
            elif ext == ".wav":
                result = resave_wav(body, tmp)
                action = "resaved"
        except UnicodeDecodeError:
            rep.error("data", "text_encoding", "текстовый файл не в UTF-8", name)
            continue
        except (ValueError, wave.Error, EOFError, zlib.error, struct.error) as e:
            code = "png_broken" if ext == ".png" else "wav_broken" if ext == ".wav" else "text_binary"
            rep.error("data", code, f"файл не читается: {e}", name)
            continue
        target = clean / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(result)
        rep.files.append({"path": name, "size": len(body), "sha256": hashlib.sha256(body).hexdigest(), "action": action,
                          "cleanSize": len(result), "cleanSha256": hashlib.sha256(result).hexdigest()})
    shutil.rmtree(tmp, ignore_errors=True)


def hd_conflicts(data, game, rep):
    """R-175: мод меняет кадры набора, у которого есть HD-пак мода hd - на экране останется старая HD-картинка."""
    if not game:
        return
    hd = game / "user" / "mods" / "hd" / "hd"
    if not hd.is_dir():
        return
    have = {p.name.lower() for p in hd.iterdir()}
    for name, body in data.items():
        if PurePosixPath(name).suffix.lower() != ".rul":
            continue
        text = body.decode("utf-8", errors="replace")
        block = re.search(r"^extraSprites:\s*$(.*?)(?=^\S|\Z)", text, re.M | re.S)
        if not block:
            continue
        for sprite in re.findall(r"^\s*-\s*type(?:Single)?:\s*['\"]?([\w.+-]+)", block.group(1), re.M):
            if sprite.lower() in have or sprite.lower().replace(".pck", "") in have:
                rep.signal("data", "hd_conflict", f"набор {sprite} есть в HD-паке мода hd: новые кадры останутся под старой HD-картинкой (R-175). Нужен свой набор", name)


def graphics_changed(data):
    return any(PurePosixPath(n).suffix.lower() == ".png" for n in data)


# ---- 5. запуск ----

class Bench:
    def __init__(self, exe, out):
        self.exe, self.out = str(exe), out
        self.log = open(out / "run.log", "a", encoding="utf-8-sig")

    def call(self, *args, timeout=420):
        r = subprocess.run([sys.executable, str(BENCH), *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        self.log.write(r.stdout + r.stderr)
        self.log.flush()
        return r.stdout

    def run(self, name, script, timeout=60):
        return self.call("run", "--name", name, "--timeout", str(timeout), script, timeout=timeout + 20)

    def state(self, name):
        m = re.search(r"state (\w+) stack=\S+(?: side=(\w+))?(?: turn=(\d+))?", self.run(name, "state", 30))
        return m.groups() if m else ("", None, None)

    def end_turn(self, name, limit=300):
        first = int(self.state(name)[2] or 0)
        self.run(name, "key 8", 30)
        t0 = time.time()
        top = ""
        while time.time() - t0 < limit:
            time.sleep(1.5)
            top, side, turn = self.state(name)
            if top == "NextTurnState":
                self.run(name, "click 160,100", 30)
            elif top in ("InfoboxOKState", "InfoboxState"):
                self.run(name, "key 13", 30)
            elif top == "BattlescapeState" and side == "player" and int(turn or 0) > first:
                return time.time() - t0
            elif not top:
                raise RuntimeError("игра не отвечает")
        raise RuntimeError(f"ход не закончился за {limit} с, экран {top}")

    def battle(self, name, mods_dir, mod_id, save, master):
        a = ["start", "--name", name, "--exe", self.exe, "--mods-dir", str(mods_dir), "--set", "oxceLuaMods=true", "--timeout", "400"]
        if mod_id:
            a += ["--mods", f"{mod_id}=true"]
        if save:
            a += ["--save", str(save)]
        if master:
            a += ["--master", master]
        self.call(*a, timeout=460)

    def folder(self, name):
        return Path(os.environ["TEMP"]) / f"oxce_bench_{name}"


def link_or_copy(src, dst):
    """Соединение на чужую папку мода снимать только os.rmdir (R-047): rmtree снёс бы моды установки."""
    if dst.exists():
        return
    try:
        subprocess.run(["cmd", "/c", "mklink", "/J", str(dst), str(src)], check=True, capture_output=True)
    except subprocess.CalledProcessError:
        shutil.copytree(src, dst)


def unlink_all(top):
    for base, dirs, _ in os.walk(top):
        for d in list(dirs):
            p = os.path.join(base, d)
            if os.path.isjunction(p):
                os.rmdir(p)
                dirs.remove(d)
    shutil.rmtree(top, ignore_errors=True)


def run_stage(exe, game, clean, out, rep, turns):
    mod_id, master = rep.mod.get("id", ""), rep.mod.get("master", "")
    bench = Bench(exe, out)
    mods = out / "mods"
    mods.mkdir(exist_ok=True)
    pirates = master in ("piratez", "*") and (game / "user" / "mods" / "Piratez").exists() or (game / "user" / "mods" / "piratez").exists()
    if pirates:
        for d in (game / "user" / "mods").iterdir():
            if d.is_dir():
                link_or_copy(d, mods / d.name)
    shutil.copytree(clean, mods / mod_id, dirs_exist_ok=True)
    save_plain = None
    if pirates:
        # сейв этапа 1 числит пробные моды этапа 1: тот же бой и тот же сид, в списке только проверяемый мод
        text = SAVE.read_text(encoding="utf-8")
        save_mod, save_plain = out / "with.sav", out / "without.sav"
        save_mod.write_text(re.sub(r"(?:  - 'lua_\w+ ver: [^']*'\n)+", f"  - '{mod_id} ver: {rep.mod.get('version', '')}'\n", text, count=1), encoding="utf-8", newline="\n")
        save_plain.write_text(re.sub(r"(?:  - 'lua_\w+ ver: [^']*'\n)+", "", text, count=1), encoding="utf-8", newline="\n")
    elif master == "xcom1":
        os.environ["OXCE_HIDDEN_DATA"] = str(game)
    else:
        rep.unfinished.append(f"запуск: для master '{master}' нет готового боя, проверить руками")
        return {}

    times = {}
    for label, mid, save in (("without", "", save_plain), ("with", mod_id, save_plain and out / "with.sav")):
        name = f"lmc{label}"
        try:
            bench.battle(name, mods, mid, save, "" if pirates else "xcom1")
            if not pirates:
                bench.run(name, "open battle; wait 4000; state; key 13; wait 2500; key 27; wait 1500; state; key f5; wait 4000; state", 400)
            times[label] = [round(bench.end_turn(name), 1) for _ in range(turns)]
        except (RuntimeError, subprocess.TimeoutExpired) as e:
            if label == "with":
                rep.error("run", "run_failed", f"бой с модом не дошёл до конца: {e}")
            else:
                rep.unfinished.append(f"запуск: бой без мода не дошёл до конца, сравнивать не с чем: {e}")
        finally:
            folder = bench.folder(name)
            log = bench.call("log", "--name", name, "-n", "20000", timeout=60)
            if label == "with":
                if "FATAL" in log or "Unhandled" in log:
                    rep.error("run", "run_fatal", "в журнале игры FATAL при бое с модом")
                errors = folder / "lua_errors.log"
                text = errors.read_text(encoding="utf-8", errors="replace") if errors.exists() else ""
                count = text.count("\n")
                if count:
                    rep.signal("run", "lua_errors", f"ошибки Lua в бою: {count} строк журнала. Первая: {text.splitlines()[0][:300]}")
                    shutil.copy(errors, out / "lua_errors.log")
                limits = len(re.findall(r"limit|too many instructions|out of memory", text))
                if limits:
                    rep.signal("run", "lua_limits", f"срабатывания лимитов песочницы: {limits}")
                if not re.search(rf"\[lua\] {re.escape(mod_id)}:", log) and not count:
                    rep.signal("run", "lua_silent", "мод за бой ничего не написал в журнал: сработал ли он, видно только по коду")
            bench.call("stop", "--name", name, timeout=60)
    if "with" in times and "without" in times:
        a, b = sum(times["with"]), sum(times["without"])
        if b > 0 and a > b * 1.5 and a - b > 10:
            rep.signal("run", "slow", f"ходы с модом {a:.0f} с против {b:.0f} с без него")
    unlink_all(mods)
    return times


# ---- итог ----

def write_report(rep, out, archive, extra):
    verdict = rep.verdict()
    doc = {"verdict": verdict, "archive": archive.name, "archiveSha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "mod": rep.mod,
           "errors": rep.errors, "signals": rep.signals, "unfinished": rep.unfinished, "files": rep.files, **extra}
    (out / "report.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8-sig", newline="\n")
    word = {"pass": "пройдено", "refuse": "отказ", "unfinished": "проверка не закончена"}[verdict]
    lines = [f"# Автопроверка: {rep.mod.get('id') or archive.name} {rep.mod.get('version', '')}", "", f"Итог: **{word}**", ""]
    if rep.errors:
        lines += ["## Причины отказа", ""] + [f"- {e['text']}" + (f" (`{e['file']}`)" if e["file"] else "") for e in rep.errors] + [""]
    if rep.unfinished:
        lines += ["## Не проверено", ""] + [f"- {u}" for u in rep.unfinished] + [""]
    if rep.signals:
        lines += ["## Сигналы разбору", ""] + [f"- {s['text']}" + (f" (`{s['file']}`)" if s["file"] else "") for s in rep.signals] + [""]
    if rep.files:
        lines += [f"## Файлы: {len(rep.files)}", ""] + [f"- `{f['path']}`, {f['size']} байт, {'пересохранён' if f['action'] == 'resaved' else 'без изменений'}" for f in rep.files] + [""]
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8-sig", newline="\n")
    return verdict


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Автопроверка заявки на Lua-мод")
    ap.add_argument("archive", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--exe", type=Path, help="игра: компиляция Lua и чтение YAML её разборщиками, бой")
    ap.add_argument("--game", type=Path, help="папка игры: конфликты с hd и бой")
    ap.add_argument("--battle", action="store_true", help="стадия 5: невидимые бои с модом и без него")
    ap.add_argument("--turns", type=int, default=2)
    ap.add_argument("--own-test-mod", action="store_true", help="наш собственный тестовый архив: можно вне песочницы")
    a = ap.parse_args()

    if os.environ.get("USERNAME") != "WDAGUtilityAccount" and not a.own_test_mod:
        print("Чужой архив проверяется только в Windows Sandbox: py -3.13 tools/lua_mod_sandbox.py. Наш тестовый архив: --own-test-mod", file=sys.stderr)
        return 2

    a.out.mkdir(parents=True, exist_ok=True)
    clean = a.out / "clean"
    shutil.rmtree(clean, ignore_errors=True)
    clean.mkdir()
    names, api = load_names()
    rep = Report()
    extra = {}
    data = read_archive(a.archive, rep)
    if data is not None:
        check_metadata(data, rep, api)
        for name, body in sorted(data.items()):
            if PurePosixPath(name).suffix.lower() == ".lua":
                try:
                    scan_lua(name, body.decode("utf-8-sig"), names, rep)
                except UnicodeDecodeError:
                    pass  # стадия данных скажет об этом сама
        check_data(data, clean, a.out, rep)
        hd_conflicts(data, a.game, rep)
        extra["graphics"] = graphics_changed(data)
        if not a.exe:
            rep.unfinished.append("компиляция Lua и чтение YAML: не указан --exe")
        elif not rep.errors:
            native_check(a.exe, clean, a.out, rep)
        if a.battle and not rep.errors:
            if a.exe and a.game:
                extra["turnSeconds"] = run_stage(a.exe, a.game, clean, a.out, rep, a.turns)
            else:
                rep.unfinished.append("запуск: нужны --exe и --game")
        elif not a.battle:
            rep.unfinished.append("запуск: стадия 5 не запрошена (--battle)")
    if rep.errors:
        shutil.rmtree(clean, ignore_errors=True)
    verdict = write_report(rep, a.out, a.archive, extra)
    print(f"ИТОГ: {verdict}, отказов {len(rep.errors)}, сигналов {len(rep.signals)}, файлов {len(rep.files)}: {a.out / 'report.md'}")
    for e in rep.errors:
        print(f"  ОТКАЗ {e['code']}: {e['text']}" + (f" ({e['file']})" if e["file"] else ""))
    return {"pass": 0, "refuse": 1, "unfinished": 2}[verdict]


if __name__ == "__main__":
    sys.exit(main())
