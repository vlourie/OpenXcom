#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Где мы в очереди на перерисовку: состояние каждого набора, считанное с диска.

Следить за генерацией по памяти нельзя - наборов 626, проходов много, и через неделю
не вспомнить, какой набор уже прогнан новым конвейером, а какой только выглядит готовым,
потому что HD-пак у него остался от старого. Поэтому состояние НЕ ведётся руками:
оно каждый раз вычисляется заново по тому, что реально лежит на диске.

Состояния набора:
    нет       HD-пака нет вовсе - игра рисует классику через xBRZ
    старый    пак есть, но отчёта сверки нет: собран прежним конвейером (SDXL-апскейл)
    в работе  ответ модели пришёл, в пак ещё не вписан
    готов     есть и пак, и отчёт tile_forge - набор прошёл новый конвейер

    py -3 tools\art_status.py
    py -3 tools\art_status.py --top 40

Пишет docs\ART_STATUS.md и печатает сводку. Прогресс меряется НЕ в наборах, а в клетках
карт: набор из 41 кадра может стоить больше, чем сорок наборов по сто кадров.
"""
import argparse
import csv
import os

ENC = "utf-8-sig"


def read_tsv(path):
    with open(path, encoding=ENC, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def count_frames(d):
    if not os.path.isdir(d):
        return 0
    return sum(1 for f in os.listdir(d) if f.lower().endswith(".png") and f.split(".")[0].isdigit())


def state_of(name, mod_terrain, forge_dir, art_dir):
    """Состояние набора по следам на диске. Отчёт сверки - единственная надёжная метка
    нового конвейера: его пишет только tile_forge fit."""
    pack = count_frames(os.path.join(mod_terrain, name + ".PCK"))
    report = os.path.join(art_dir, "TERRAIN", name + ".PCK", "report", "forge.tsv")
    fitted = 0
    if os.path.exists(report):
        try:
            fitted = len(read_tsv(report))
        except Exception:                                       # noqa: BLE001
            fitted = 0
    # ответ модели приходит партиями: art\TERRAIN\<НАБОР>.PCK
    # ответ модели приходит партиями: art\TERRAIN\<НАБОР>.PCK\returned\01, \02 ...
    returned = 0
    rdir = os.path.join(art_dir, "TERRAIN", name + ".PCK", "returned")
    for r, _dirs, files in os.walk(rdir):
        returned += sum(1 for f in files if f.lower().endswith(".png"))
    if fitted and pack:
        return "готов", pack, fitted, returned
    if returned:
        return "в работе", pack, fitted, returned
    if pack:
        return "старый", pack, fitted, returned
    return "нет", pack, fitted, returned


def bar(done, total, width=28):
    n = int(round(width * done / total)) if total else 0
    return "#" * n + "." * (width - n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--census", default="census")
    ap.add_argument("--install", default=os.path.join("Пиратки", "Dioxine_XPiratez"))
    ap.add_argument("--forge", default="forge")
    ap.add_argument("--art", default="art")
    ap.add_argument("--out", default=os.path.join("docs", "ART_STATUS.md"))
    ap.add_argument("--top", type=int, default=25, help="сколько ближайших наборов показать")
    args = ap.parse_args()

    road = read_tsv(os.path.join(args.census, "roadmap.tsv"))
    mod_terrain = os.path.join(args.install, "user", "mods", "hd", "hd", "TERRAIN")

    total_tiles = sum(int(r["клеток"]) for r in road)
    rows = []
    for r in road:
        st, pack, fitted, returned = state_of(r["набор"], mod_terrain, args.forge, args.art)
        rows.append({"место": int(r["место"]), "набор": r["набор"], "состояние": st,
                     "кадров": int(r["кадров"]), "рисовать": int(r["рисовать"]),
                     "клеток": int(r["клеток"]), "блоков": int(r["блоков"]),
                     "пак": pack, "сверено": fitted, "охват": float(r["охват_клеток_%"])})

    by_state = {}
    for r in rows:
        s = by_state.setdefault(r["состояние"], {"наборов": 0, "клеток": 0, "рисовать": 0})
        s["наборов"] += 1
        s["клеток"] += r["клеток"]
        s["рисовать"] += r["рисовать"]

    done_tiles = by_state.get("готов", {}).get("клеток", 0)
    any_tiles = done_tiles + by_state.get("старый", {}).get("клеток", 0)
    todo = [r for r in rows if r["состояние"] in ("старый", "нет", "в работе")]

    lines = ["# Состояние перерисовки", "",
             "Считано с диска `tools/art_status.py`. Руками не править - перезаписывается.", "",
             "## Прогресс по клеткам карт", "",
             "```",
             "новый конвейер  [%s] %5.1f%%  (%d клеток)" % (bar(done_tiles, total_tiles),
                                                            100.0 * done_tiles / total_tiles if total_tiles else 0,
                                                            done_tiles),
             "любой HD-пак    [%s] %5.1f%%  (%d клеток)" % (bar(any_tiles, total_tiles),
                                                            100.0 * any_tiles / total_tiles if total_tiles else 0,
                                                            any_tiles),
             "```", "",
             "## По состояниям", "",
             "| состояние | наборов | клеток | доля клеток | рисовать кадров |",
             "|---|---|---|---|---|"]
    for st in ("готов", "в работе", "старый", "нет"):
        s = by_state.get(st)
        if not s:
            continue
        lines.append("| %s | %d | %d | %.1f%% | %d |"
                     % (st, s["наборов"], s["клеток"],
                        100.0 * s["клеток"] / total_tiles if total_tiles else 0, s["рисовать"]))
    lines += ["", "## Ближайшие %d наборов" % args.top, "",
              "| # | набор | состояние | кадров | рисовать | клеток | блоков | охват |",
              "|---|---|---|---|---|---|---|---|"]
    for r in todo[:args.top]:
        lines.append("| %d | %s | %s | %d | **%d** | %d | %d | %.1f%% |"
                     % (r["место"], r["набор"], r["состояние"], r["кадров"], r["рисовать"],
                        r["клеток"], r["блоков"], r["охват"]))
    lines += ["", "## Уже прошли новый конвейер", ""]
    ready = [r for r in rows if r["состояние"] == "готов"]
    if ready:
        lines.append("| # | набор | кадров в паке | сверено | клеток |")
        lines.append("|---|---|---|---|---|")
        for r in sorted(ready, key=lambda r: r["место"]):
            lines.append("| %d | %s | %d | %d | %d |"
                         % (r["место"], r["набор"], r["пак"], r["сверено"], r["клеток"]))
    else:
        lines.append("Пока ни одного.")
    lines.append("")

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding=ENC, newline="") as f:
        f.write("\n".join(lines) + "\n")

    print("новый конвейер: %.1f%% клеток, любой HD-пак: %.1f%%"
          % (100.0 * done_tiles / total_tiles if total_tiles else 0,
             100.0 * any_tiles / total_tiles if total_tiles else 0))
    for st in ("готов", "в работе", "старый", "нет"):
        s = by_state.get(st)
        if s:
            print("  %-9s наборов %3d, клеток %8d, рисовать %5d кадров"
                  % (st, s["наборов"], s["клеток"], s["рисовать"]))
    print("следующий: %s (%d кадров рисовать, %d клеток)"
          % (todo[0]["набор"], todo[0]["рисовать"], todo[0]["клеток"]) if todo else "всё готово")
    print("отчёт: %s" % os.path.abspath(args.out))


if __name__ == "__main__":
    main()
