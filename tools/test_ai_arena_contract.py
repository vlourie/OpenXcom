"""Контракт конфигурации стенда (02.10, R-169): ai_arena --strict-flags без флага стенда - INVALID_CONFIG (код 2) до первого
боя; продолжение серии с другими отпечатками - INVALID_CONFIG (код 3); отпечаток данных меняет правка рулсета и не меняет
картинка; effective_flags включает значения по умолчанию ai_probe.bench_defaults. Без игры и сборки.
  py -3.13 tools/test_ai_arena_contract.py"""
import argparse, os, subprocess, sys, tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ai_arena, ai_probe  # noqa: E402

fails = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


# 1. --strict-flags без одного флага: код 2, строка INVALID_CONFIG, до provenance
env = {k: v for k, v in os.environ.items() if not k.startswith("OXCE_AI_")}
env["PYTHONIOENCODING"] = "utf-8"
given = [f"--env={k}=0" for k in ai_probe.BENCH_FLAGS[1:]]
r = subprocess.run([sys.executable, str(HERE / "ai_arena.py"), "--strict-flags", "--label", "contract_test", *given],
                   capture_output=True, text=True, encoding="utf-8", env=env, timeout=60)
check("strict: нет флага - код 2", r.returncode == 2)
check("strict: называет флаг", "INVALID_CONFIG" in r.stdout and ai_probe.BENCH_FLAGS[0] in r.stdout)
check("strict: provenance не писался", "fingerprint:" not in r.stdout)

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    game = tmp / "game"
    (game / "user" / "mods" / "m" / "Ruleset").mkdir(parents=True)
    (game / "user" / "mods" / "m" / "Language").mkdir()
    rul = game / "user" / "mods" / "m" / "Ruleset" / "a.rul"
    rul.write_text("items: []\n", encoding="utf-8")
    png = game / "user" / "mods" / "m" / "x.png"
    png.write_bytes(b"png")
    (game / "user" / "mods" / "m" / "Language" / "en-US.yml").write_text("a: b\n", encoding="utf-8")
    ai_probe.GAME, ai_probe.WORK, ai_probe.EXE = game, tmp / "work", tmp / "none.exe"
    a = argparse.Namespace(label="t", recruits=True, campaign="", missions="", resume=True)

    # 2. отпечаток данных: рулсет меняет, картинка и строки нет
    d0, n0 = ai_arena.data_fingerprint(a)
    png.write_bytes(b"png2")
    (game / "user" / "mods" / "m" / "Language" / "en-US.yml").write_text("a: c\n", encoding="utf-8")
    d1, _ = ai_arena.data_fingerprint(a)
    rul.write_text("items: [x]\n", encoding="utf-8")
    d2, _ = ai_arena.data_fingerprint(a)
    check("данные: один файл механики", n0 == 1)
    check("данные: картинка и строки не меняют", d0 == d1)
    check("данные: рулсет меняет", d1 != d2)

    # 3. effective_flags: явное значение и значение по умолчанию
    for k in [k for k in os.environ if k.startswith("OXCE_AI_")]:
        del os.environ[k]
    os.environ["OXCE_AI_FAST"] = "0"
    os.environ["OXCE_AI_GAME"] = "C:/x"  # путь в флаги не входит
    flags = ai_arena.effective_flags()
    check("флаги: явное значение", "OXCE_AI_FAST=0" in flags.split(";"))
    check("флаги: значение по умолчанию", all(any(p.startswith(k + "=") for p in flags.split(";")) for k in ai_probe.BENCH_FLAGS))
    check("флаги: без путей", "OXCE_AI_GAME" not in flags)

    # 4. продолжение серии: те же отпечатки - идёт, другие флаги - код 3
    arena = ai_probe.WORK / "arena"
    arena.mkdir(parents=True)
    (arena / "t.tsv").write_text("seed\n", encoding="utf-8")
    sys.argv = ["ai_arena.py"]
    ai_arena.provenance(a)
    ai_arena.provenance(a)
    check("продолжение: те же отпечатки - идёт", True)
    os.environ["OXCE_AI_FAST"] = "1"
    try:
        ai_arena.provenance(a)
        code = 0
    except SystemExit as e:
        code = e.code
    check("продолжение: другие флаги - код 3", code == 3)
    fp = ai_arena.read_fingerprint(arena / "t.prov.txt")
    check("отпечатки: четыре", fp is not None and sorted(fp) == ["ai_probe", "data", "exe", "flags"])

print("итог:", "OK" if not fails else f"FAIL {len(fails)}")
sys.exit(1 if fails else 0)
