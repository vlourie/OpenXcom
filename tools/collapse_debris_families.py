"""Лист семейств этапа B завала (docs/research/collapse-debris-mechanics-2026-10-21.md, «Этап B — свой набор»):
что уже лежит в игре (поваленный ствол из горных наборов) и записи, по которым рисуются эскизы своего набора
COLLAPSE_DEBRIS - куча, глыба, ствол-забор. До генерации: Vitali выбирает основы и семейства.
Только чтение установки Пираток.
    py -3.13 tools/collapse_debris_families.py
-> art/collapse_debris/stage_b_families.png, census/collapse/debris/stage_b_families.tsv"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import collapse_debris_short as S   # noqa: E402

LANDS = ["MOUNTGRASS", "MOUNTMUD", "MOUNTTROP", "MOUNTSNOW2", "MOUNTWASTE2", "MOUNTROCK", "MOUNT"]
ROWS = [
    ("П", "поваленный ствол - уже в игре с 22.10: целое бревно (72) и куски (73) горного набора края, сбитые - бурелом",
     ["%s:%d" % (s, i) for s in LANDS for i in (72, 73)]),
    ("Кч", "куча (свой арт): основа эскиза - высокая крошка трущоб, бетон завала v1, каменная крошка гор",
     ["INDUSLUM:56", "INDUSLUM:57", "INDUSLUM:58", "INDUSLUM:59", "URBAN:50", "URBAN:57", "COMMERCE:50",
      "MOUNTROCK:8", "MOUNTGRASS:8", "MOUNTMUD:8", "MOUNTSNOW2:8"]),
    ("Гл", "глыба (свой арт): основа - тёмная плита URBAN40K и валуны гор (их цвет края - образец перекраски)",
     ["URBAN40K:57", "MILTECHDIO:26"] + ["%s:%d" % (s, i) for s in ("MOUNTROCK", "MOUNTGRASS", "MOUNTSNOW2", "MOUNTMUD")
                                         for i in (69, 70)]),
    ("Сз", "ствол-забор в слоте стены (свой арт): основа - лежащее бревно, стена западная и зеркалом северная",
     ["MOUNTGRASS:72", "MOUNTROCK:72", "MOUNTSNOW2:72", "MOUNTTROP:72"]),
]

if __name__ == "__main__":
    S.main(ROWS, "art/collapse_debris/stage_b_families.png", "census/collapse/debris/stage_b_families.tsv")
