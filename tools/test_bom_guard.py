"""Проверка хука .claude/hooks/bom-guard.ps1: после записи *.ps1 файл приводится к UTF-8 с BOM и CRLF (R-001).

Файл без BOM / с LF - хук пересохраняет и сообщает; уже верный файл, не .ps1, пустой, не UTF-8 и несуществующий - не трогает.
Запуск: python tools/test_bom_guard.py   (код 0 - всё верно)
"""
import json
import os
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".claude", "hooks", "bom-guard.ps1")
BOM = b"\xef\xbb\xbf"
TXT = "# Привет, мир\nWrite-Host 'тест'\n"


def run(raw):
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", HOOK],
                       input=raw, capture_output=True, text=True, encoding="utf-8")
    return r.returncode, r.stdout.strip()


def fire(path, field="file_path"):
    return run(json.dumps({"tool_name": "Write", "tool_input": {field: path}}, ensure_ascii=False))


bad = 0


def check(name, cond, extra=""):
    global bad
    bad += not cond
    print(("ok   " if cond else "FAIL ") + name + (f": {extra}" if extra and not cond else ""))


with tempfile.TemporaryDirectory() as d:
    def mk(name, data):
        p = os.path.join(d, name)
        with open(p, "wb") as f:
            f.write(data)
        return p

    def body(p):
        with open(p, "rb") as f:
            return f.read()

    # 1. без BOM, LF: BOM + CRLF, хук сообщает
    p = mk("a.ps1", TXT.encode("utf-8"))
    rc, out = fire(p)
    want = BOM + TXT.replace("\n", "\r\n").encode("utf-8")
    check("без BOM и LF: пересохранён с BOM и CRLF", body(p) == want, repr(body(p)[:20]))
    check("без BOM и LF: хук сообщает о пересохранении", rc == 0 and "additionalContext" in out and "BOM" in out, out)

    # 2. повторный запуск на уже верном файле: байты те же, вывода нет
    before = body(p)
    rc, out = fire(p)
    check("уже верный файл: байты не меняются", body(p) == before)
    check("уже верный файл: вывода нет", rc == 0 and out == "", out)

    # 3. BOM есть, но LF: CRLF дописан, BOM один
    p = mk("b.ps1", BOM + TXT.encode("utf-8"))
    fire(p)
    check("BOM и LF: CRLF, один BOM", body(p) == BOM + TXT.replace("\n", "\r\n").encode("utf-8") and body(p).count(BOM) == 1)

    # 4. смешанные концы строк: не удваивать \r
    p = mk("c.ps1", "a\r\nb\nc\r\n".encode("utf-8"))
    fire(p)
    check("смешанные концы: без \\r\\r\\n", body(p) == BOM + b"a\r\nb\r\nc\r\n", repr(body(p)))

    # 5. другие расширения - не трогать
    for ext in ("py", "md", "txt", "cmd"):
        p = mk("d." + ext, TXT.encode("utf-8"))
        rc, out = fire(p)
        check(f".{ext}: не трогать", body(p) == TXT.encode("utf-8") and out == "")

    # 6. .psm1 и .psd1 хук обрабатывает (шаблон \.ps(m|d)?1$)
    for ext in ("psm1", "psd1"):
        p = mk("e." + ext, TXT.encode("utf-8"))
        fire(p)
        check(f".{ext}: BOM добавлен", body(p).startswith(BOM))

    # 7. cp1251 (не UTF-8): не портить
    raw = "# Привет\n".encode("cp1251")
    p = mk("f.ps1", raw)
    rc, out = fire(p)
    check("не UTF-8: не трогать", body(p) == raw and out == "")

    # 8. пустой файл
    p = mk("g.ps1", b"")
    rc, out = fire(p)
    check("пустой файл: не трогать", body(p) == b"" and out == "")

    # 9. несуществующий файл, пустой ввод, сломанный JSON, событие без пути: выход 0 и тишина
    rc, out = fire(os.path.join(d, "нет.ps1"))
    check("несуществующий файл: тихо", rc == 0 and out == "")
    for name, raw in [("пустой ввод", ""), ("сломанный JSON", "{не json"), ("без пути", "{}"),
                      ("Bash без пути", json.dumps({"tool_input": {"command": "x.ps1"}}))]:
        rc, out = run(raw)
        check(f"{name}: тихо", rc == 0 and out == "", out)

    # 10. путь в поле path
    p = mk("h.ps1", TXT.encode("utf-8"))
    fire(p, "path")
    check("поле path: пересохранён", body(p).startswith(BOM))

print("ВСЁ ВЕРНО" if bad == 0 else f"ОШИБОК: {bad}")
sys.exit(1 if bad else 0)
