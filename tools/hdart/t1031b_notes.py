#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Строка в CHANGELOG.md (первая под «### Исправлено» блока «Не выпущено») и в Выпуск/notes/next.en.txt для тикета 384|385|389.

    py -3.13 tools\hdart\t1031b_notes.py 384
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LINES = {
    "384": (
        "- HD-графика (бой, трава на красной земле): трава на плитах MOUNTMUD (редкая трава на земле, густая трава и пятна травы) нарисована заново сплошным полем — без швов между клетками, с тремя вариантами ковра, чтобы повтор не бросался в глаза; куст на этих картах тоже заново (тикет XP-000384). Только картинка.",
        "- HD graphics (battle, grass on red earth): the grass on the MOUNTMUD tiles (sparse grass on earth, dense grass and grass patches) is redrawn as one continuous field - no seams between tiles, with three carpet variants so the repetition is not noticeable; the bush on these maps is redrawn too (ticket XP-000384). Picture only.",
    ),
    "385": (
        "- HD-графика (бой, снег): заново нарисованы снежные карты — камень, пруд, трава и склоны на снегу, а также родственные снежные наборы (полярные, снежный лес и болото); края ровные, швов между клетками нет (тикеты XP-000385, XP-000386, XP-000387). Только картинка; куст на снегу пока прежний.",
        "- HD graphics (battle, snow): the snow maps are redrawn - stone, pond, grass and slopes on snow, and the related snow sets (polar, snowy forest and swamp); the edges are straight, no seams between tiles (tickets XP-000385, XP-000386, XP-000387). Picture only; the bush on snow is still the old one.",
    ),
    "389": (
        "- HD-графика (бой, рваный асфальт): у плит рваного асфальта убраны чёрные точки и лесенка по краю; край ровный, цвет асфальта до самой кромки (тикет XP-000389).",
        "- HD graphics (battle, torn asphalt): the black dots and the stair-step along the edge of the torn asphalt tiles are removed; the edge is straight and the asphalt colour reaches the very rim (ticket XP-000389).",
    ),
}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ru, en = LINES[sys.argv[1]]
    cl = os.path.join(ROOT, "CHANGELOG.md")
    with open(cl, encoding="utf-8-sig") as fh:
        text = fh.read()
    if ru in text:
        print("CHANGELOG: уже есть")
    else:
        head, sep, rest = text.partition("### Исправлено\n")
        if not sep:
            raise SystemExit("нет раздела Исправлено")
        text = head + sep + ru + "\n" + rest
        with open(cl, "w", encoding="utf-8-sig", newline="") as fh:
            fh.write(text)
        print("CHANGELOG: добавлено")
    nt = os.path.join(ROOT, "Выпуск", "notes", "next.en.txt")
    with open(nt, "rb") as fh:
        raw = fh.read()
    bom = raw.startswith(b"\xef\xbb\xbf")
    s = raw.decode("utf-8-sig")
    if en in s:
        print("notes: уже есть")
    else:
        if not s.endswith("\n"):
            s += "\n"
        s += en + "\n"
        with open(nt, "wb") as fh:
            fh.write((b"\xef\xbb\xbf" if bom else b"") + s.encode("utf-8"))
        print("notes: добавлено")


if __name__ == "__main__":
    main()
