# Приёмка №12 (LUA_MODS §11): плохие архивы получают отказ с понятной причиной, хороший проходит. Архивы наши собственные.
# Запуск: py -3.13 tools/lua_stage3/test_check.py
import io, json, os, shutil, struct, subprocess, sys, tempfile, warnings, wave, zipfile, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/lua_mod_check.py"
EXE = ROOT / "build-release/bin" / ("openxcom" + ".e" + "xe")
TMP = Path(tempfile.mkdtemp(prefix="lua_check_"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
failed = []
os.environ["PATH"] = "C:/msys64/mingw64/bin;" + os.environ["PATH"]

META = b'id: test_mod\nname: "Test"\nversion: 0.1\nmaster: "piratez"\nluaApi: 1\n'
MAIN = b'game.on("newTurnUnit", function(unit, battle, turn, side)\n  game.log("turn", turn)\nend)\n'


def png(colour=3):
    raw = b"\x00\x01\x02" * 2
    head = struct.pack(">IIBBBBB", 2, 2, 8, colour, 0, 0, 0)
    def chunk(k, p):
        return struct.pack(">I", len(p)) + k + p + struct.pack(">I", zlib.crc32(k + p))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", head) + chunk(b"PLTE", bytes(range(9))) + chunk(b"tEXt", b"evil\x00payload") + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"") + b"TAIL"


def wav():
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(22050); w.writeframes(b"\x00\x01" * 100)
    return buf.getvalue()


def archive(name, files):
    path = TMP / f"{name}.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for n, body in files.items():
            # ZipInfo при создании сам меняет обратную косую: имя кладём как есть, как сделал бы чужой архиватор
            info = zipfile.ZipInfo("x")
            info.filename = n
            info.compress_type = zipfile.ZIP_DEFLATED
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                z.writestr(info, body)
    return path


def check(name, files, verdict, code=None, signal=None, raw=None):
    path = raw or archive(name, files)
    out = TMP / f"out_{name}"
    r = subprocess.run([sys.executable, str(TOOL), str(path), "--out", str(out), "--exe", str(EXE), "--own-test-mod"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    doc = json.loads((out / "report.json").read_text(encoding="utf-8-sig")) if (out / "report.json").exists() else {}
    got = doc.get("verdict")
    codes = [e["code"] for e in doc.get("errors", [])]
    sig = [s["code"] for s in doc.get("signals", [])]
    # стадия 5 здесь не запрошена: хороший архив честно отвечает «проверка не закончена», а не «пройдено»
    ok = got == verdict and (code is None or code in codes) and (signal is None or signal in sig)
    print(("PASS " if ok else "FAIL ") + name, got, codes or "", sig or "", (doc.get("errors") or [{}])[0].get("text", "")[:100])
    if not ok:
        failed.append(name)
        print(r.stdout, r.stderr)
    return out, doc


good = {"metadata.yml": META, "lua/main.lua": MAIN}
out, doc = check("good", good, "unfinished")
if not (out / "clean" / "lua" / "main.lua").exists():
    failed.append("clean")

out, doc = check("data_clean", {**good, "Resources/a.png": png(), "Sound/a.wav": wav(), "Ruleset/a.rul": b"items:\n  - type: STR_A\n"}, "unfinished")
saved = (out / "clean/Resources/a.png").read_bytes()
good_png = b"tEXt" not in saved and not saved.endswith(b"TAIL") and b"PLTE" in saved
print(("PASS " if good_png else "FAIL ") + "PNG пересохранён: чужой блок и хвост ушли, палитра на месте")
if not good_png:
    failed.append("png_resave")

# №12
check("dotdot", {**good, "../evil.txt": b"x"}, "refuse", "path_parent")
check("backslash", {**good, "lua\\..\\evil.txt": b"x"}, "refuse", "path_absolute")
check("backslash_no_parent", {**good, "lua\\evil.txt": b"x"}, "refuse", "path_absolute")
check("absolute", {**good, "/etc/evil.txt": b"x"}, "refuse", "path_absolute")
check("exe", {**good, "tool.exe": b"MZ"}, "refuse", "file_executable")
check("dll", {**good, "lua/x.dll": b"MZ"}, "refuse", "file_executable")
check("bat", {**good, "run.bat": b"del *"}, "refuse", "file_executable")
check("ps1", {**good, "run.ps1": b"x"}, "refuse", "file_executable")
check("scr", {**good, "x.scr": b"x"}, "refuse", "file_executable")
check("luac", {**good, "lua/x.luac": b"\x1bLuaT"}, "refuse", "lua_bytecode")
check("bytecode_as_text", {**good, "lua/x.lua": b"\x1bLuaT\x00"}, "refuse", "text_binary")
check("broken_png", {**good, "Resources/a.png": png()[:40]}, "refuse", "png_broken")
check("fake_png", {**good, "Resources/a.png": b"not a png at all"}, "refuse", "png_broken")
check("broken_wav", {**good, "Sound/a.wav": b"RIFFxxxxWAVE"}, "refuse", "wav_broken")
check("broken_yaml", {**good, "Ruleset/a.rul": b"items:\n  - type: [unclosed\n"}, "refuse", "yaml_broken")
check("broken_meta", {"metadata.yml": b"id test_mod\n???\n", "lua/main.lua": MAIN}, "refuse", "metadata_broken")
check("no_meta", {"lua/main.lua": MAIN}, "refuse", "metadata_missing")
check("no_main", {"metadata.yml": META, "lua/other.lua": MAIN}, "refuse", "lua_main_missing")
check("bad_api", {"metadata.yml": META.replace(b"luaApi: 1", b"luaApi: 99"), "lua/main.lua": MAIN}, "refuse", "metadata_luaapi")
check("bad_engine", {"metadata.yml": META + b"requiredExtendedEngine: Brutal\n", "lua/main.lua": MAIN}, "refuse", "metadata_engine")
check("bad_id", {"metadata.yml": META.replace(b"test_mod", b"../x"), "lua/main.lua": MAIN}, "refuse", "metadata_id")
check("syntax", {"metadata.yml": META, "lua/main.lua": b"function(\n"}, "refuse", "lua_syntax")
check("duplicate", {**good, "A.txt": b"1", "a.txt": b"2"}, "refuse", "path_duplicate")
check("reserved", {**good, "con.txt": b"1"}, "refuse", "path_name")
garbage = TMP / "garbage.zip"
garbage.write_bytes(b"PK\x03\x04 this is no archive")
check("garbage_zip", {}, "refuse", "archive_corrupt", raw=garbage)

# подозрительное - сигнал, а не отказ
check("escape_signal", {"metadata.yml": META, "lua/main.lua": b'local f = io.open("x")\nos.execute("y")\nrequire("z")\n'}, "unfinished", signal="api_escape")
check("unknown_signal", {"metadata.yml": META, "lua/main.lua": b'game.nothing()\nlocal u = nil\nu:killEveryone()\ngame.on("noSuchEvent", function() end)\n'}, "unfinished", signal="api_unknown")
check("event_signal", {"metadata.yml": META, "lua/main.lua": b'game.on("noSuchEvent", function() end)\n'}, "unfinished", signal="api_event")
check("encoded_signal", {"metadata.yml": META, "lua/main.lua": b'local s = "' + b"QUJD" * 200 + b'"\n'}, "unfinished", signal="encoded_block")
# комментарий и строка - не вызовы
check("comment_no_signal", {"metadata.yml": META, "lua/main.lua": b'-- io.open("x")\nlocal s = "os.execute"\ngame.log(s)\n'}, "unfinished")
out, doc = TMP / "out_comment_no_signal", json.loads((TMP / "out_comment_no_signal/report.json").read_text(encoding="utf-8-sig"))
if doc["signals"]:
    failed.append("comment_no_signal")
    print("FAIL сигнал на комментарий", doc["signals"])

# без разрешения вне песочницы скрипт не работает
r = subprocess.run([sys.executable, str(TOOL), str(TMP / "good.zip"), "--out", str(TMP / "nope")], capture_output=True, text=True, encoding="utf-8", errors="replace")
guard = r.returncode == 2 and not (TMP / "nope").exists()
print(("PASS " if guard else "FAIL ") + "чужой архив вне песочницы не проверяется")
if not guard:
    failed.append("guard")

shutil.rmtree(TMP, ignore_errors=True)
print("ИТОГ:", "FAIL " + "; ".join(failed) if failed else "PASS")
sys.exit(1 if failed else 0)
