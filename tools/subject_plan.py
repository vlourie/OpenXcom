#!/usr/bin/env python3
"""
Где тема набора реально окупается: доля полов и известное место из рулсетов.

    python tools/subject_plan.py --mod "Пиратки/Dioxine_XPiratez/user/mods/Piratez"

Зачем. Тема набора (SUBJECTS в gen_hd.py) идёт в промпт и заметно влияет там, где
художнику дана свобода - на полах, которые красятся полной силой. Объекты мы красим
силой 0.55, и промпт на них влияет слабо: проверено на A_PODS (0 полов, разница между
темой и заглушкой едва заметна) против ACHURCH (24 пола, разница видна).

Поэтому писать 600 тем подряд смысла нет. Скрипт считает по каждому набору, сколько
у него кадров-полов, и подставляет место из set_terrains.tsv (его строит index_mod.py):
имя набора врёт - CORP оказывается складом мафии, ASHEN1 тёмной башней.

Кладёт в <out>/:
    subject_plan.tsv  набор | кадров | полов | доля,% | естьТема | террейны
    INDEX.md          верх списка: где тема даст больше всего
"""
from __future__ import annotations

import argparse, os, sys, time
from pathlib import Path

ENC = "utf-8-sig"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdart"))
try:
    import xcom_sprites as xs
except Exception as e:
    sys.exit("нет tools/hdart/xcom_sprites.py: %s" % e)


def read_tsv(path: Path):
    if not path.exists():
        return []
    rows = []
    with path.open(encoding=ENC) as f:
        head = f.readline().rstrip("\n").split("\t")
        for line in f:
            c = line.rstrip("\n").split("\t")
            if len(c) >= len(head):
                rows.append(dict(zip(head, c)))
    return rows


def subjects_in_gen_hd() -> set:
    """Какие наборы уже имеют тему - читаем прямо из gen_hd.py, чтобы не держать список дважды."""
    p = Path(__file__).parent / "hdart" / "gen_hd.py"
    if not p.exists():
        return set()
    out, inside = set(), False
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if s.startswith("SUBJECTS"):
            inside = True
            continue
        if inside:
            if s.startswith("}"):
                break
            if s.startswith('"') and '":' in s:
                out.add(s.split('"')[1].upper())
    return out


def build(mod: Path, index: Path, out: Path) -> int:
    t0 = time.time()
    tdir = mod / "TERRAIN"
    if not tdir.is_dir():
        sys.exit("нет %s" % tdir)

    places = {r["set"].upper(): r["terrains"] for r in read_tsv(index / mod.name / "set_terrains.tsv")}
    if not places:
        print("ВНИМАНИЕ: нет set_terrains.tsv - сначала python tools/index_mod.py", file=sys.stderr)
    have = subjects_in_gen_hd()

    rows = []
    pcks = sorted({p for p in tdir.iterdir() if p.is_file() and p.suffix.lower() == ".pck"})
    for pck in pcks:
        tab = pck.with_suffix(".TAB")
        if not tab.exists():
            tab = pck.with_suffix(".tab")
        mcd = pck.with_suffix(".MCD")
        if not mcd.exists():
            mcd = pck.with_suffix(".mcd")
        if not tab.exists() or not mcd.exists():
            continue
        try:
            frames = xs.read_pck(str(pck), str(tab))
            recs = xs.read_mcd(str(mcd))
        except Exception:
            continue
        drawable = [i for i, f in enumerate(frames)
                    if f is not None and any(any(r) for r in f)]
        if not drawable:
            continue
        types, walkable, raised = xs.frame_types(recs, len(frames))
        # Формула ровно как в extract_pck.py: "земля" - это не только полы по MCD,
        # но и проходимые объекты, закрывающие ромб (посевы, цветы), и без наклона.
        # Считать иначе - значит строить план по цифрам, которых конвейер не знает.
        floors = 0
        for i in drawable:
            fr = frames[i]
            if fr is None or len(fr) != 40 or len(fr[0]) != 32:
                continue
            cov = xs.diamond_coverage(fr, 32, 40)
            top = min((y for y in range(40) if any(fr[y])), default=40)
            if not raised[i] and ((types[i] == xs.MCD_FLOOR and top >= 40 - 16 - 8) or
                                  (types[i] == xs.MCD_OBJECT and walkable[i] and cov >= 0.85)):
                floors += 1
        name = pck.stem.upper()
        rows.append({
            "set": pck.name, "frames": len(drawable), "floors": floors,
            "pct": round(100 * floors / len(drawable)),
            "has": "да" if (name + ".PCK") in have or name in have else "нет",
            "place": places.get(name, ""),
        })

    out.mkdir(parents=True, exist_ok=True)
    rows.sort(key=lambda r: -r["floors"])
    with (out / "subject_plan.tsv").open("w", encoding=ENC, newline="\n") as f:
        f.write("set\tframes\tfloors\tpct\thasSubject\tterrains\n")
        for r in rows:
            f.write("\t".join([r["set"], str(r["frames"]), str(r["floors"]),
                               str(r["pct"]), r["has"], r["place"]]) + "\n")

    todo = [r for r in rows if r["has"] == "нет" and r["floors"] > 0]
    total_floors = sum(r["floors"] for r in rows)
    cover = 0
    cut = 0
    for i, r in enumerate(todo, 1):
        cover += r["floors"]
        if cover >= 0.8 * sum(x["floors"] for x in todo):
            cut = i
            break

    md = [
        f"# Где тема набора окупается: {mod.name}",
        "",
        f"Собрано: {time.strftime('%Y-%m-%d %H:%M')} за {time.time()-t0:.1f} с",
        "",
        "| Показатель | Значение |", "|---|---|",
        f"| Наборов с тайлами | {len(rows)} |",
        f"| Кадров-полов всего | {total_floors} |",
        f"| Наборов без темы, но с полами | {len(todo)} |",
        f"| Хватит тем, чтобы покрыть 80 % полов | **{cut}** |",
        "",
        "Полы красятся полной силой, объекты - 0.55, поэтому тема влияет прежде всего",
        "на полы. Список отсортирован по числу кадров-полов: сверху те, где тема даст больше всего.",
        "",
        "Число полов здесь меньше, чем печатает extract_pck: там в счёт идут и пустые кадры",
        "(у пустого кадра проверка высоты проходит формально). Рисовать их не надо, поэтому",
        "план считает только непустые.",
        "",
        "## Верх списка",
        "",
        "| Набор | Кадров | Полов | % | Место по рулсетам |", "|---|---|---|---|---|",
        *[f"| {r['set']} | {r['frames']} | {r['floors']} | {r['pct']} | {r['place'][:60]} |"
          for r in todo[:40]],
        "",
        "Полная таблица - `subject_plan.tsv`.",
    ]
    (out / "INDEX.md").write_text("\n".join(md) + "\n", encoding=ENC)
    print(f"Наборов {len(rows)}, кадров-полов {total_floors}; без темы с полами {len(todo)}; "
          f"80 % полов закрывают {cut} тем -> {out}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="План: каким наборам нужна тема")
    ap.add_argument("--mod", required=True)
    ap.add_argument("--index", default=".index/mod")
    ap.add_argument("--out", default=".index/mod/_subjects")
    a = ap.parse_args()
    return build(Path(a.mod), Path(a.index), Path(a.out))


if __name__ == "__main__":
    sys.exit(main())
