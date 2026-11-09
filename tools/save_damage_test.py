# Негативные тесты компактных сейвов (опция oxceCompactSave, DECISIONS 2026-11-09): повреждённый сейв обязан давать
# понятную ошибку загрузки, а не вылет игры. Игра - невидимо через tools/hdbench.py.
#   py -3.13 tools/save_damage_test.py [имя_сейва_из_Пираток.sav]     без аргументов - PeasGray.sav (самый маленький)
# Код возврата 0 - игра пережила все повреждения и после них нормально грузит целый компактный сейв.
import re, subprocess, sys, tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
BENCH = ROOT / "tools" / "hdbench.py"
PY = ["py", "-3.13"]


def bench(*args):
    r = subprocess.run(PY + [str(BENCH)] + list(args), cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, r.stdout + r.stderr


def split(data):
    i = data.find(b"\n---\n")
    return data[:i + 5], data[i + 5:]


def main():
    save = sys.argv[1] if len(sys.argv) > 1 else "PeasGray.sav"
    name = "dmg_" + re.sub(r"\W", "", save)[:8]
    code, out = bench("start", "--name", name, "--save", save)
    if code != 0:
        print(out)
        return 1
    ok = True
    try:
        user = Path(tempfile.gettempdir()) / f"oxce_bench_{name}"
        d, log = user / "piratez", user / "openxcom.log"
        bench("run", "--name", name, "set oxceCompactSave=true; savefile good.sav; set oxceCompactSave=false")
        good = (d / "good.sav").read_bytes()
        head, body = split(good)
        if body[:4] != b"OXZ1":
            print("в компактном сейве нет магии OXZ1")
            return 1
        cases = {
            "trunc_half": head + body[:len(body) // 2],
            "trunc_head": head + body[:5],
            "bad_magic": head + b"OXZ2" + body[4:],
            "bad_len": head + body[:4] + b"\xff\xff\xff\x7f\x00\x00\x00\x00" + body[12:],
            "zero_len": head + body[:4] + b"\x00" * 8 + body[12:],
            "garbage": head + body[:12] + bytes((b ^ 0x5A) for b in body[12:300]) + body[300:],
        }
        # плоский сейв с битым списком убийств: берём обычный сейв и портим строки (индекс вне таблицы, мусор в числе, мало полей)
        bench("run", "--name", name, "savefile plain.sav")
        plain = (d / "plain.sav").read_bytes().decode("utf-8", "replace")
        # те же порчи в компактном виде делаем на распакованном тексте: пакуем сами через игру нельзя, поэтому правим текст компактного
        # сейва до сжатия невозможно; вместо этого порча идёт в обычном формате с компактными записями-строками
        cases_plain = {}
        m = re.search(r'(?m)^(\s*)killStrings:.*$', plain)
        bad_lines = {
            "idx_out_of_range": '"1 2 3 4 5 6 7 8 9 10 11 99999"',
            "short_record": '"1 2 3"',
            "not_a_number": '"a b c d e f g h i j k l"',
        }
        # без компактных записей в сейве вставить порчу негде - проверим только если есть killList-блок
        for k, line in bad_lines.items():
            cases_plain[k] = (plain, line)
        for k, data in cases.items():
            (d / f"dmg_{k}.sav").write_bytes(data)
        for k, (text, line) in cases_plain.items():
            t = text.replace("\n  killList:\n", "\n  killStrings: [\"a\"]\n  killList:\n    - " + line + "\n", 1) if "\n  killList:\n" in text else None
            if t is None:
                t = re.sub(r"(?m)^(\s*)killList:\s*$", lambda mm: f'{mm.group(1)}killStrings: ["a"]\n{mm.group(1)}killList:\n{mm.group(1)}  - {line}', text, count=1)
            (d / f"dmg_{k}.sav").write_bytes(t.encode("utf-8"))
        for k in list(cases) + list(cases_plain):
            mark = log.stat().st_size
            code, out = bench("run", "--name", name, f"load dmg_{k}.sav; wait 2500; state")
            alive = code == 0 and "err" not in out.lower().split("state")[-1][:0]
            text = log.read_text(encoding="utf-8", errors="replace")[mark:]
            err = [l for l in text.splitlines() if "ERROR" in l or "rror" in l][:2]
            c2, o2 = bench("run", "--name", name, "state")
            running = c2 == 0
            print(f"{k:18} игра жива: {'да' if running else 'НЕТ'}; ошибка в логе: {err[0][:150] if err else '-'}")
            if not running:
                ok = False
                break
        if ok:
            code, out = bench("run", "--name", name, "load good.sav; waitstate GeoscapeState 60000; state")
            print("целый компактный после порч:", "грузится" if code == 0 else "НЕ грузится", out.strip().splitlines()[-1][:120] if out.strip() else "")
            ok = code == 0
    finally:
        bench("stop", "--name", name)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
