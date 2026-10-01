"""R-162: бой серии ai_arena пишется целиком или никак.

Процесс записи убивается os._exit в четырёх местах commit_battle (посреди cand.gz, перед строкой таблицы,
посреди строки таблицы, после строки до снятия журнала). После каждого обрыва: recover(), затем бой дописывается
заново, как сделал бы --resume. Итог обязан совпасть с серией без обрыва: те же строки таблицы, каждый архив
проходит gzip целиком (и gzip -t, если он есть), в архивах ровно бои таблицы.
Контроль: до recover() обрыв посреди cand.gz даёт битый архив - иначе тест не ловил бы саму беду.

  py -3.13 tools/test_ai_arena_commit.py
"""
import gzip, os, random, shutil, subprocess, sys, tempfile, zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ai_arena

CRASHES = ("torn_cand", "before_row", "torn_row", "after_row")
GZ = [ext for _, ext in ai_arena.ARCHIVES if ext.endswith(".gz")]


def battle(seed):
    row = {c: "" for c in ai_arena.COLS}
    row.update(seed=seed, want=f"STR_TEST_{seed}", how="over", mission=f"STR_TEST_{seed}", seconds=1,
               hleft=0, livesoldiers=1, livealiens=0, aborted=0, player=1)
    # cand крупный и плохо сжимаемый - запись посреди него рвётся на середине члена gzip
    rnd = random.Random(seed)
    row["_cand"] = [f"[AICAND] i={i} v={rnd.getrandbits(192):048x}" for i in range(4000)]
    row["_rec"] = [f"[AIREC] i={i}" for i in range(300)]
    row["_path"] = [f"[AIPATH] i={i}" for i in range(50)]
    row["_tiles"] = [f"[AITILE] i={i}" for i in range(200)]
    row["_casualties"] = [f"[AICASUALTY] i={i}" for i in range(3)]
    return row


def fresh(folder):
    table = Path(folder) / "t.tsv"
    table.write_text("\t".join(ai_arena.COLS + ("outcome",)) + "\n", encoding=ai_arena.ENC_W)
    return table


def child(folder, crash):
    """Запись боя 2 с обрывом в точке crash. Бои 1 и 3 пишет родитель, бой 2 - этот процесс."""
    table = Path(folder) / "t.tsv"
    real = ai_arena._append

    def append(path, data):
        if crash == "torn_cand" and path.name.endswith(".cand.gz"):
            real(path, data[: len(data) // 2])
            os._exit(9)
        if path == table and crash == "before_row":
            os._exit(9)
        if path == table and crash == "torn_row":
            real(path, data[: len(data) // 2])
            os._exit(9)
        real(path, data)
        if path == table and crash == "after_row":
            os._exit(9)

    ai_arena._append = append
    ai_arena.commit_battle(table, battle(2))
    os._exit(0)


def gz_whole(path):
    """Архив читается целиком (как rec_diff); исключение - битый."""
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return f.read()


def gzip_t(path):
    tool = shutil.which("gzip")
    return tool is None or subprocess.run([tool, "-t", str(path)], capture_output=True).returncode == 0


def content(folder):
    """Таблица и архивы серии: битый архив - AssertionError."""
    table = Path(folder) / "t.tsv"
    seeds = [r["seed"] for r in ai_arena.read_table(table)]
    out = {"seeds": seeds}
    for ext in GZ:
        p = table.with_suffix(ext)
        if not p.exists():  # decide - только по OXCE_AI_KEEP_DECIDE, в тестовом бою его нет
            out[ext] = None
            continue
        assert gzip_t(p), f"gzip -t: {p.name}"
        text = gz_whole(p)
        tags = sorted({ln.split(" ", 1)[0] for ln in text.splitlines() if ln})
        assert tags == sorted(f"seed={s}" for s in seeds), f"{p.name}: бои {tags}, в таблице {seeds}"
        out[ext] = text
    out["cas"] = table.with_suffix(".casualties.txt").read_bytes()
    return out


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "--child":
        child(sys.argv[2], sys.argv[3])
    fails = 0
    root = Path(tempfile.mkdtemp(prefix="arena_commit_"))
    # эталон: три боя без обрыва (строки боя - от зерна, у оборванного процесса те же)
    ref = root / "ref"
    ref.mkdir()
    t = fresh(ref)
    rows = {s: battle(s) for s in (1, 2, 3)}
    for s in (1, 2, 3):
        ai_arena.commit_battle(t, rows[s])
    want = content(ref)
    for crash in CRASHES:
        d = root / crash
        d.mkdir()
        t = fresh(d)
        ai_arena.commit_battle(t, rows[1])
        r = subprocess.run([sys.executable, __file__, "--child", str(d), crash])
        if r.returncode != 9:
            print(f"FAIL {crash}: процесс записи не оборван (код {r.returncode})")
            fails += 1
            continue
        if crash == "torn_cand":
            # контроль: без восстановления архив битый и в таблице боя нет - тест видит беду R-162
            try:
                gz_whole(t.with_suffix(".cand.gz"))
                print(f"FAIL {crash}: контроль - оборванный cand.gz читается целиком, тест ничего не проверяет")
                fails += 1
            except (EOFError, OSError, zlib.error):
                pass
        note = ai_arena.recover(t)
        if t.with_suffix(".journal").exists():
            print(f"FAIL {crash}: журнал не снят")
            fails += 1
        # --resume: сыграть то, чего нет в таблице
        have = {r["seed"] for r in ai_arena.read_table(t)}
        for s in (2, 3):
            if str(s) not in have:
                ai_arena.commit_battle(t, rows[s])
        try:
            got = content(d)
        except AssertionError as e:
            print(f"FAIL {crash}: {e} ({note})")
            fails += 1
            continue
        bad = [k for k in want if got[k] != want[k]]
        if bad:
            print(f"FAIL {crash}: не как без обрыва: {bad} ({note})")
            fails += 1
        else:
            print(f"ok   {crash}: {note}")
    shutil.rmtree(root, ignore_errors=True)
    print("всё верно" if not fails else f"ошибок: {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
