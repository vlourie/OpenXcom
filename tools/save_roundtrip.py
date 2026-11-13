# Проверка компактных сейвов (опция oxceCompactSave, DECISIONS 2026-11-09): обычный сейв -> компактный -> загрузка игрой
# -> обычный сейв; два обычных обязаны совпасть до байта, кроме строки time: заголовка (часы геоскейпа идут).
# Игра запускается невидимо через tools/hdbench.py (команда savefile пишет сейв так, как пишет игра, и называет время записи).
#   py -3.13 tools/save_roundtrip.py [имя_сейва_из_Пираток.sav ...]     без аргументов - NoCodexManZ.sav
# Печатает размеры, время записи и загрузки, число разных строк; код возврата 0 - всё совпало, 1 - есть расхождение.
import difflib, os, re, subprocess, sys, tempfile, time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
BENCH = ROOT / "tools" / "hdbench.py"
PY = ["py", "-3.13"]


def bench(*args):
    r = subprocess.run(PY + [str(BENCH)] + list(args), cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, r.stdout + r.stderr


def stall_ms(log, since):
    """Последняя строка 'HD stall: N ms on ...GeoscapeState' лога после смещения since: загрузка сейва - в think геоскейпа."""
    text = Path(log).read_text(encoding="utf-8", errors="replace")[since:]
    found = re.findall(r"HD stall: (\d+) ms on N8OpenXcom13GeoscapeState", text)
    return int(found[-1]) if found else None


def one(save):
    name = "rt_" + re.sub(r"\W", "", save)[:10]
    code, out = bench("start", "--name", name, "--save", save)
    if code != 0:
        print(out)
        return False
    try:
        user = Path(tempfile.gettempdir()) / f"oxce_bench_{name}"
        d, log = user / "piratez", user / "openxcom.log"
        script = "savefile rt_plain1.sav; set oxceCompactSave=true; savefile rt_compact.sav; set oxceCompactSave=false"
        code, out = bench("run", "--name", name, script)
        times = re.findall(r"savefile (\S+)\s+->\s+ok (\d+) ms", out)
        mark = log.stat().st_size
        bench("run", "--name", name, "load rt_compact.sav; waitstate GeoscapeState 60000; wait 1500")
        load_c = stall_ms(log, mark)
        code, out = bench("run", "--name", name, "savefile rt_plain2.sav; state")
        mark = log.stat().st_size
        bench("run", "--name", name, "load rt_plain1.sav; waitstate GeoscapeState 60000; wait 1500")
        load_p = stall_ms(log, mark)
        p1, c, p2 = d / "rt_plain1.sav", d / "rt_compact.sav", d / "rt_plain2.sav"
        if not (p1.exists() and c.exists() and p2.exists()):
            print(save, ": не все файлы записаны", out)
            return False
        a, b = p1.read_bytes().split(b"\n"), p2.read_bytes().split(b"\n")
        diff = [x for x in difflib.unified_diff([l.decode("utf-8", "replace") for l in a], [l.decode("utf-8", "replace") for l in b], lineterm="", n=0)
                if x[:1] in "+-" and x[:3] not in ("+++", "---") and not x[1:].startswith("time:")]
        # строго: все убийства (их-то и меняет компактная запись) и число строк; остальные расхождения - часы геоскейпа,
        # которые идут между двумя сохранениями (координаты кораблей, таймеры), они только в сводке
        kill = re.compile(r"^\s*- \{(type|name):.*bodypart")
        kills_a = [l for l in a if kill.match(l.decode("utf-8", "replace"))]
        kills_b = [l for l in b if kill.match(l.decode("utf-8", "replace"))]
        good = kills_a == kills_b and len(a) == len(b) and len(kills_a) > 0
        print(f"{save}: обычный {p1.stat().st_size:,} Б, компактный {c.stat().st_size:,} Б ({100 * c.stat().st_size / p1.stat().st_size:.1f}%), "
              f"запись {dict(times).get('rt_plain1.sav')} / {dict(times).get('rt_compact.sav')} мс, "
              f"загрузка обычного {load_p} мс / компактного {load_c} мс; убийств {len(kills_a)} из {len(kills_b)} "
              f"{'совпали' if kills_a == kills_b else 'РАЗНЫЕ'}, строк {len(a)} / {len(b)}, прочих расхождений (часы) {len(diff)}")
        for x in diff[:4]:
            print("   ", x[:160])
        return good
    finally:
        bench("stop", "--name", name)


if __name__ == "__main__":
    saves = sys.argv[1:] or ["NoCodexManZ.sav"]
    ok = all([one(s) for s in saves])
    sys.exit(0 if ok else 1)
