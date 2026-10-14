"""Замки модели обрушения переживают чистый checkout (грабли R-252).

Замки census/collapse/**/*.lock.txt хэшируют БАЙТЫ файла. В репозитории core.autocrlf=true и * text=auto:
git хранит LF, а выкладывает по правилу концов строк. Для каждого файла tools/, записанного в действующем
замке (тот, что совпадает с диском), тест строит байты, которые git выложит в чистую копию: blob индекса
(git show :путь) плюс концы строк по git check-attr eol (eol=crlf - CRLF, eol=lf - LF, без правила -
по core.autocrlf), и сверяет sha256 с замком.

- файл замка не в git - провал (чистая копия его не получит);
- выкладка даёт другие байты - провал (замок в чистой копии НАРУШЕН);
- контроль: тот же расчёт без правил .gitattributes (только autocrlf) обязан найти расхождение,
  иначе тест ничего не проверяет.
Без census/collapse (вне гита) тест пропускается с сообщением.

    py -3.13 tools/test_collapse_lock_eol.py
"""
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCKS = ROOT / "census" / "collapse"
ENC_R = "utf-8-sig"


def git(*args, binary=False):
    p = subprocess.run(["git", "-C", str(ROOT)] + list(args), capture_output=True)
    if p.returncode:
        return None
    return p.stdout if binary else p.stdout.decode("utf-8", "replace")


def lock_rows(path):
    """(путь, sha) из замка: строки 'путь sha256 хэш' и 'путь<TAB>хэш'."""
    rows = []
    for line in path.read_text(encoding=ENC_R).splitlines():
        if " sha256 " in line:
            p, h = line.split(" sha256 ", 1)
        elif "\t" in line and not line.startswith(("#", "time")):
            p, h = line.split("\t", 1)
        else:
            continue
        h = h.strip()
        if len(h) == 64:
            rows.append((p.strip(), h))
    return rows


def checkout_bytes(rel, autocrlf, use_attrs=True):
    blob = git("show", ":" + rel, binary=True)
    if blob is None:
        return None
    lf = blob.replace(b"\r\n", b"\n")
    eol = ""
    if use_attrs:
        out = git("check-attr", "eol", "--", rel) or ""
        eol = out.rsplit(":", 1)[-1].strip()
    if eol == "crlf" or (eol in ("", "unspecified") and autocrlf):
        return lf.replace(b"\n", b"\r\n")
    return lf


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if not LOCKS.is_dir():
        print("census/collapse нет (данные вне гита) - тест пропущен")
        return 0
    autocrlf = (git("config", "core.autocrlf") or "").strip().lower() == "true"
    tracked = set((git("ls-files", "tools") or "").split())
    sha = lambda b: hashlib.sha256(b).hexdigest()
    want = {}                                    # путь -> хэш действующего замка
    for lock in sorted(LOCKS.rglob("*.lock.txt")):
        for rel, h in lock_rows(lock):
            f = ROOT / rel
            if not rel.startswith("tools/") or not f.exists():
                continue
            if sha(f.read_bytes()) != h:         # устаревший замок (файл с тех пор правлен) - не действующий
                continue
            want.setdefault(rel, set()).add(h)
    fails, ctl_miss = [], 0
    for rel in sorted(want):
        if rel not in tracked:
            fails.append("%s: в замке, но не в git - чистая копия его не получит" % rel)
            continue
        b = checkout_bytes(rel, autocrlf)
        if sha(b) not in want[rel]:
            fails.append("%s: чистый checkout даёт другие байты (CRLF %d) - замок нарушен" % (rel, b.count(b"\r\n")))
        if sha(checkout_bytes(rel, autocrlf, use_attrs=False)) not in want[rel]:
            ctl_miss += 1
    print("файлов в действующих замках: %d, core.autocrlf=%s" % (len(want), autocrlf))
    print("контроль без правил .gitattributes: нарушено бы %d" % ctl_miss)
    if autocrlf and ctl_miss == 0:
        fails.append("контроль: без правил .gitattributes расхождений нет - тест ничего не проверяет")
    if fails:
        print("ПРОВАЛ:\n  " + "\n  ".join(fails))
        return 1
    print("OK: замки обрушения совпадут в чистой копии")
    return 0


if __name__ == "__main__":
    sys.exit(main())
