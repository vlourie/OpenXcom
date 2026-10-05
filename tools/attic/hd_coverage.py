#!/usr/bin/env python3
"""
Покрытие мода HD-графикой: что уже нарисовано, чего нет, и сколько осталось кадров.

    python tools/hd_coverage.py --mod "Пиратки/Dioxine_XPiratez/user/mods/Piratez" \
                                --hd  "Пиратки/Dioxine_XPiratez/user/mods/hd"

Отвечает на вопрос «что гнать на видеокарте следующим» цифрами, а не на глаз.
Нужна карта мода: сперва tools/index_mod.py по обоим модам.

Кладёт в <out>/:
    coverage.tsv   вид | набор | кадров | вHD | покрытие,% | путьHD
    todo.tsv       то же, только непокрытое, по убыванию объёма работы
    INDEX.md       сводка

Число кадров в наборе террейна берётся из .tab (таблица смещений в .pck).
Ширина записи бывает 2 или 4 байта; скрипт определяет её сам и, если ни один
вариант не сходится, честно пишет "?" вместо выдуманного числа.
"""
from __future__ import annotations

import argparse, json, os, struct, sys, time
from pathlib import Path

# Декодер PCK живёт в tools/hdart. Без него считаем кадры по .tab, но тогда в счёт
# попадают и пустые кадры, которых в наборе бывает больше половины.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdart"))
try:
    import xcom_sprites as _xs
except Exception:
    _xs = None

ENC_W = "utf-8-sig"
ENC_R = "utf-8-sig"


def read_tsv(path: Path):
    if not path.exists():
        sys.exit(f"нет {path} — сначала python tools/index_mod.py")
    rows = []
    with path.open(encoding=ENC_R) as f:
        head = f.readline().rstrip("\n").split("\t")
        for line in f:
            c = line.rstrip("\n").split("\t")
            if len(c) >= len(head):
                rows.append(dict(zip(head, c)))
    return rows


def pck_drawable(tab: Path, pck: Path):
    """Сколько кадров в наборе реально надо рисовать: пустые не в счёт.

    Пустой кадр в PCK не нулевой длины - прозрачность кодируется пропусками, и по
    размеру записи его не отличить (самый маленький кадр CORP.PCK - 42 байта).
    Поэтому декодируем: 8 мс на набор, около 5 секунд на все 625.
    build_pack всё равно пропускает пустые (--skip-empty), так что считать их
    как работу - завышать объём втрое."""
    if _xs is None:
        return None
    try:
        frames = _xs.read_pck(str(pck), str(tab))
    except Exception:
        return None
    # read_pck отдаёт None, когда смещение из .tab уходит за конец файла: таблица
    # прочитана не той шириной или набор нестандартный. Такой кадр не нарисовать.
    n = good = 0
    for f in frames:
        if f is None:
            continue
        good += 1
        if any(any(row) for row in f):
            n += 1
    if not frames or good * 2 < len(frames):
        return None          # разобрали меньше половины - лучше "?", чем уверенное враньё
    return n


def pck_frames(tab: Path, pck: Path):
    """Всего кадров в наборе по таблице смещений. None, если формат не распознан."""
    try:
        data = tab.read_bytes()
        pck_size = pck.stat().st_size
    except OSError:
        return None
    for width, fmt in ((2, "<H"), (4, "<I")):
        if not data or len(data) % width:
            continue
        n = len(data) // width
        offs = [struct.unpack_from(fmt, data, i * width)[0] for i in range(n)]
        if offs and offs[0] == 0 and all(b > a for a, b in zip(offs, offs[1:])) and offs[-1] < pck_size:
            return n
    return None


def count_png(d: Path) -> int:
    if not d.is_dir():
        return 0
    return sum(1 for p in d.rglob("*.png"))


def build(mod: Path, hd: Path, index: Path, out: Path) -> int:
    t0 = time.time()
    hd_root = hd / "hd"
    if not hd_root.is_dir():
        print(f"ВНИМАНИЕ: в моде {hd.name} нет папки hd/ — покрытие будет нулевым", file=sys.stderr)

    rows = []

    # 1. Наборы из extraSprites: сколько кадров объявлено в рулсете.
    for s in read_tsv(index / mod.name / "sprites.tsv"):
        name = s["set"]
        try:
            frames = int(s["frames"] or 0)
        except ValueError:
            frames = 0
        if s.get("singleImage", "").lower() == "true":
            frames = max(frames, 1)
        d = hd_root / name
        rows.append({"kind": "sprites", "set": name, "frames": frames, "total": frames,
                     "hd": count_png(d), "path": d.relative_to(hd).as_posix() if hd_root.is_dir() else ""})

    # 2. Наборы террейна: кадры считаем по .tab, HD ищем в hd/TERRAIN/<имя>.PCK/
    tdir = mod / "TERRAIN"
    if tdir.is_dir():
        # glob на Windows не различает регистр: два вызова по *.PCK и *.pck дали бы
        # один и тот же файл дважды и удвоили объём работы в отчёте.
        pcks = sorted({p for p in tdir.iterdir()
                       if p.is_file() and p.suffix.lower() == ".pck"})
        for pck in pcks:
            tab = pck.with_suffix(".TAB")
            if not tab.exists():
                tab = pck.with_suffix(".tab")
            total = pck_frames(tab, pck) if tab.exists() else None
            n = pck_drawable(tab, pck) if tab.exists() else None
            if n is None:
                n = total
            d = hd_root / "TERRAIN" / pck.name
            rows.append({"kind": "terrain", "set": pck.name, "frames": n if n is not None else -1,
                         "total": total if total is not None else -1,
                         "hd": count_png(d), "path": d.relative_to(hd).as_posix() if hd_root.is_dir() else ""})

    seen = set()
    uniq = []
    for r in rows:
        key = (r["kind"], r["set"].lower())
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)
    if len(uniq) != len(rows):
        print(f"убрано повторов: {len(rows) - len(uniq)}", file=sys.stderr)
    rows = uniq

    def pct(r):
        if r["frames"] <= 0:
            return -1
        return min(100, round(100 * r["hd"] / r["frames"]))

    out.mkdir(parents=True, exist_ok=True)

    def dump(path, data):
        with path.open("w", encoding=ENC_W, newline="\n") as f:
            f.write("kind\tset\tdrawable\ttotal\tinHD\tpercent\thdPath\n")
            for r in data:
                p = pct(r)
                f.write("\t".join([r["kind"], r["set"],
                                   "?" if r["frames"] < 0 else str(r["frames"]),
                                   "?" if r.get("total", -1) < 0 else str(r.get("total", r["frames"])),
                                   str(r["hd"]), "?" if p < 0 else str(p), r["path"]]) + "\n")

    rows.sort(key=lambda r: (r["kind"], r["set"]))
    dump(out / "coverage.tsv", rows)

    todo = [r for r in rows if r["hd"] == 0 and r["frames"] != 0]
    todo.sort(key=lambda r: -(r["frames"] if r["frames"] > 0 else 0))
    dump(out / "todo.tsv", todo)

    done = [r for r in rows if r["frames"] > 0 and r["hd"] >= r["frames"]]
    part = [r for r in rows if 0 < r["hd"] < (r["frames"] if r["frames"] > 0 else 1 << 30)]
    unknown = [r for r in rows if r["frames"] < 0]
    frames_total = sum(r["frames"] for r in rows if r["frames"] > 0)
    frames_todo = sum(r["frames"] for r in todo if r["frames"] > 0)

    md = [
        f"# Покрытие HD: {mod.name} -> {hd.name}",
        "",
        f"Собрано: {time.strftime('%Y-%m-%d %H:%M')} за {time.time()-t0:.1f} с",
        "",
        "| Показатель | Значение |", "|---|---|",
        f"| Наборов всего | {len(rows)} |",
        f"| Полностью нарисовано | {len(done)} |",
        f"| Частично | {len(part)} |",
        f"| Не начато | {len(todo)} |",
        f"| Кадров к рисованию (без пустых) | {frames_total} |",
        f"| Кадров осталось нарисовать | {frames_todo} |",
        f"| Записей в наборах всего, с пустыми | {sum(r.get('total', 0) for r in rows if r.get('total', 0) > 0)} |",
        f"| Наборов с неизвестным числом кадров | {len(unknown)} |",
        "",
        "## Очередь: самое крупное из ненарисованного",
        "",
        "| Вид | Набор | Кадров |", "|---|---|---|",
        *[f"| {r['kind']} | {r['set']} | {r['frames'] if r['frames']>0 else '?'} |" for r in todo[:25]],
        "",
        "## Частично нарисованное",
        "",
        "| Вид | Набор | Кадров | В HD | % |", "|---|---|---|---|---|",
        *[f"| {r['kind']} | {r['set']} | {r['frames'] if r['frames']>0 else '?'} | {r['hd']} | "
          f"{pct(r) if pct(r)>=0 else '?'} |" for r in sorted(part, key=lambda r: pct(r))[:25]],
        "",
        "Полные таблицы — `coverage.tsv` и `todo.tsv`. Кадры террейна считаны по .tab;",
        "где формат не распознан, стоит `?`, а не выдуманное число.",
    ]
    (out / "INDEX.md").write_text("\n".join(md) + "\n", encoding=ENC_W)
    (out / "meta.json").write_text(json.dumps({
        "mod": mod.as_posix(), "hd": hd.as_posix(), "sets": len(rows),
        "done": len(done), "partial": len(part), "todo": len(todo),
        "frames_total": frames_total, "frames_todo": frames_todo,
        "unknown_frames": len(unknown), "built_human": time.strftime("%Y-%m-%d %H:%M:%S"),
    }, ensure_ascii=False, indent=2), encoding=ENC_W)

    print(f"Покрытие: наборов {len(rows)}, готово {len(done)}, частично {len(part)}, "
          f"не начато {len(todo)}; осталось кадров {frames_todo} -> {out}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Покрытие мода HD-графикой")
    ap.add_argument("--mod", required=True, help="исходный мод (Piratez)")
    ap.add_argument("--hd", required=True, help="мод с HD-графикой")
    ap.add_argument("--index", default=".index/mod", help="где лежат карты модов")
    ap.add_argument("--out", default=".index/mod/_coverage")
    a = ap.parse_args()
    return build(Path(a.mod), Path(a.hd), Path(a.index), Path(a.out))


if __name__ == "__main__":
    sys.exit(main())
