"""recipe_guard: проверки рецепта пола по классике (R-298 ковёр, R-325 свечение под pixel_lines).

Опорные примеры - вердикты рецензий b01-b09 (art/ground/queue/bNN/verdicts.tsv):
  ковёр ground_seam --speckle:
    NUKE1:16, NUKE1:17 - трещины плит, ковёр стёр повторяющийся рисунок (b08) - обязан быть hold;
    однородный крап, принятый ковром, - обязан быть ok.
  pixel_lines:
    SGR_COM:51, SGR_INT02:11, XB2BR:27 (b09), U_WALLCHURCH:23 (b07) - мягкое свечение стало вложенными
    контурами - обязан быть hold;
    чёткие швы и орнамент, принятые pixel_lines, - обязаны быть ok;
    ковёр шума (b11: FORESTSWAMP_WASTE, MOUNTTROP, SGR_CAVE, SIETCHDOOM...) - камуфляж из линий - обязан быть hold;
    решётки и доски с тем же мелким индексом, но с периодом (CYBERWAREBITS:20, LIGHTNIN_R:25...) - ok.
Контроль: RECIPE_GUARD_OFF=1 снимает пороги (бесконечность) - тест обязан упасть на NUKE1, свечении и шуме.
Запуск: py -3.13 tools/test_recipe_guard.py
"""
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent / "hdart"))
import recipe_guard as rg  # noqa: E402

CARPET = "ground_seam --speckle"
LINES = "pixel_lines"

CASES = [
    # (группа, рецепт, ожидаемый вердикт)
    ("NUKE1:16", CARPET, "hold"),
    ("NUKE1:17", CARPET, "hold"),
] + [(g, CARPET, "ok") for g in (
    "MARS:0", "MOUNTMOON:0", "CAVEMEAT:13", "CAVEAQUA:13", "CAVEAQUA:14", "CAVEAQUA:18", "CAVEAQUA:19",
    "CAVEAQUA:20", "REDDESERT:0", "ICEKING_VILLAGE:61", "BROWNHILL:0")] + [
    ("SGR_COM:51", LINES, "hold"),
    ("SGR_INT02:11", LINES, "hold"),
    ("XB2BR:27", LINES, "hold"),
    ("U_WALLCHURCH:23", LINES, "hold"),
] + [(g, LINES, "ok") for g in (
    "A_DECOR:92", "CRYPTEK1:0", "DAWNURBAN:80", "GDXOPSFLOORS:48", "SGR_WALLS_B:22", "THULBASES01:12",
    "U_EXT_P:26", "WHITECASTLE:1", "FREIGHTER_COMMAND:124", "FREIGHTER_TECHNICAL:7", "MARSEC_INT_2:74",
    "SGR_INT02:17", "ABUNKER:20", "UAC_WALL02_V:15")] + [
    # b11: ковёр шума под pixel_lines стал камуфляжем - hold; решётки и доски с тем же мелким индексом - ok
    (g, LINES, "hold") for g in (
        "FORESTSWAMP_WASTE:139", "FORESTSWAMP_WASTE:112", "MOUNTTROP:4", "MOUNTTROP:5", "SGR_CAVE:19",
        "SIETCHDOOM:68", "DESERTROCKS_RED:1", "IDT_FARM_WATER:84")] + [
    (g, LINES, "ok") for g in (
        "CYBERWAREBITS:20", "WAREBITS:20", "XOPSDESERTRUINS:11", "IDT_SNOWBARN:49", "LIGHTNIN_R:25",
        "SEAMSUNK1:35", "GOVT:25", "GDXOPSFLOORS:55")] + [
    # рецепт без проверки: ground_seam без --speckle (поле, ступени) не судится ковровой проверкой
    ("NUKE1:16", "ground_seam --iso", "ok"),
]


def main():
    if os.environ.get("RECIPE_GUARD_OFF"):
        inf = float("inf")
        rg.CARPET = {k: (inf, inf, v[2]) for k, v in rg.CARPET.items()}
        rg.GLOW_SMOOTH = (inf, inf)
        rg.NOISE_MED_MAX = -inf
    bad = []
    for g, meth, want in CASES:
        v, why, _m = rg.check(g, meth)
        mark = "ok " if v == want else "FAIL"
        print("%s %-24s %-22s ждём %-6s вышло %-6s %s" % (mark, g, meth, want, v, "; ".join(why)))
        if v != want:
            bad.append(g)
    # заметка очереди: без «;» и табуляций (TSV и judge)
    n = rg.note("carpet", "hold", ["a; b", "c\td"])
    if ";" in n or "\t" in n:
        bad.append("note")
    print("\nслучаев %d, не сошлось %d%s" % (len(CASES), len(bad), (": " + ", ".join(bad)) if bad else ""))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
