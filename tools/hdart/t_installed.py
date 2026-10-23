#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Листы «было / стало» для арта, поставленного в мод по выбору Vitali 23.10 (тикеты 242, 243, 249, 251, 262, 222).

Снимки идут с УСТАНОВЛЕННОГО пака игры (user/mods/hd/hd/TERRAIN), поэтому порядок такой:
    py -3.13 tools/hdart/t_installed.py before ПУНКТ   # до установки: классика + «было» в art/tickets/installed/
    ... установка (скрипт пункта --install --yes, под очередью правок) ...
    py -3.13 tools/hdart/t_installed.py after ПУНКТ    # после: «стало» + склейка art/_review/tickets_2026-10-23/installed_ПУНКТ.png
Пункты: grass, pits, roof, wheel, mud5, mud48, lines, path, box, bin, rails, crate. Кадры-ряды (frames) - классика | было | стало по списку кадров.
Только чтение мода, пишет лишь в art/.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
from PIL import Image  # noqa: E402

TMP = ROOT / "art" / "tickets" / "installed"
REVIEW = ROOT / "art" / "_review" / "tickets_2026-10-23"

# kind map: (terrain, block, [ключи окна (набор, кадр)], w, h, maxz|None, pick, подпись)
SPECS = {
    "grass": {"scenes": [
        ("map", "PLAINS_ARBOREAL", "PLAINS11", [("MOUNTGRASS", 3), ("MOUNTGRASS", 2)], 170, 105, None, 0),
        ("map", "WESTOWN_GRASS", "WESTOWN_05", [("MOUNTGRASS", 1), ("MOUNTGRASS", 2)], 170, 105, None, 0)]},
    "pits": {"scenes": [("save", (38, 12, 5, 5)), ("save", (47, 16, 4, 4))]},
    "roof": {"scenes": [("map", "URBAN_WASTE", "URBANWASTE62", [("URBAN_WASTE", 52)], 250, 150, 2, 0)]},
    "wheel": {"scenes": [("map", "URBAN_WASTE", "URBANWASTE62", [("URBAN_WASTE", 86)], 150, 100, 0, 0)],
              "frames": [("URBAN_WASTE", 86), ("URBANWAR", 86), ("URBAN_GOODS", 86), ("VILBAN", 82), ("URBAN", 86),
                         ("CULTAREA", 86), ("DAWNURBAN", 86), ("DUSKURBAN", 86), ("IDT_SNOWVILBAN", 82),
                         ("MILURBAN", 86), ("SEAURBANDIO", 86), ("NUKE1", 18)]},
    "mud5": {"scenes": [("map", "PLAINS_MUD", "PLAINS12", [("MOUNTMUD", 5)], 150, 100, None, 0)],
             "frames": [("MOUNTMUD", 5), ("MOUNTSAND", 5), ("GOTHIC", 5)]},
    "mud48": {"scenes": [("map", "PLAINS_MUD", "PLAINS00", [("MOUNTMUD", 48)], 130, 85, None, 0)],
              "frames": [("MOUNTMUD", 48)]},
    "lines": {"scenes": [], "frames": [("PORTROADS", f) for f in range(9, 15)]},
    "path": {"scenes": [], "frames": [("PORTROADS", 16), ("CAFEENTRY", 0), ("COMROADS", 8), ("CULTEXTRA", 8), ("FLOORSET", 10),
                                      ("FLOORSETSTYX", 10), ("FREIGHTER_PASSENGER", 39), ("GOVROADS", 8),
                                      ("MANSIONFLOOR_MAG", 10), ("MILBARR", 11), ("MILBARRGHOUL", 11)]},
    # ящик 91/92 на картах не стоит (появляется при разрушении ящика): кадры кладутся на свободные клетки URBANWASTE49 (не игра)
    "box": {"scenes": [("overlay", "URBAN_WASTE", "URBANWASTE49", [("URBAN_WASTE", 91, 7, 8), ("URBAN_WASTE", 92, 9, 8)], 240, 125)],
            "frames": [("URBAN_WASTE", 91), ("COMDECOR", 43), ("CRIBDECOR", 44), ("IDT_SNOWVILBAN", 87), ("URBANLUX", 91),
                       ("URBANWAR", 91), ("URBAN_GOODS", 91), ("VILBAN", 87), ("URBAN", 91),
                       ("URBAN_WASTE", 92), ("COMDECOR", 44), ("CRIBDECOR", 45), ("CULTDECOR", 20), ("IDT_SNOWVILBAN", 88),
                       ("MADDECOR", 19), ("MADDECOR_WASTE", 18), ("SEAMADDECOR", 19), ("URBANLUX", 92), ("URBANWAR", 92),
                       ("URBAN_GOODS", 92), ("VILBAN", 88), ("URBAN", 92)]},
    "crate": {"scenes": [("map", "WESTOWN_GRASS", "WESTOWN_13", [("CONTAINERS", 2)], 150, 100, None, 0)],
              "frames": [("CONTAINERS", 2), ("DOOM_BASE2", 9)]},
    "bin": {"scenes": [("map", "URBAN_WASTE", "URBANWASTE08", [("URBAN_WASTE", 98)], 150, 100, None, 0),
                       ("map", "URBAN_WASTE", "URBANWASTEHUGE36", [("URBAN_WASTE", 98)], 150, 100, None, 0)],
            "frames": [("URBAN_WASTE", 98)]},
    "rails": {"scenes": [("map", "PORTUFO", "PORTUFOHUGE01", [("PORTROADS", 73), ("PORTROADS", 74)], 260, 150, None, 0),
                         ("map", "METRO", "METRO_NS10", [("METROBITS", 2), ("METROBITS", 3)], 260, 150, 0, 0)],
              "frames": [("PORTROADS", 73), ("PORTROADS", 74), ("METROBITS", 2), ("METROBITS", 3)]},
}
# сцены lines/path добавляются из t222_scenes.json (находит скрипт пункта)
_extra = ROOT / "art" / "tickets" / "installed" / "scenes.json"
if _extra.exists():
    for k, v in json.loads(_extra.read_text(encoding="utf-8")).items():
        if k in SPECS:
            SPECS[k]["scenes"] = [tuple(x) if x[0] == "map" else (x[0], tuple(x[1])) for x in v]


def render_scene(spec, mode, scn):
    import ticket_scene as ts
    if spec[0] == "save":
        sys.path.insert(0, str(ROOT / "art" / "tickets"))
        import scene_save
        os.chdir(ROOT)
        return scene_save.render(*spec[1], mode="classic" if mode == "classic" else "hd")
    if spec[0] == "overlay":
        return render_overlay(spec, mode, scn)
    _, terr, block, keys, w, h, maxz, pick = spec
    keys = [tuple(k) for k in keys]
    c, found = scn.render(terr, block, "classic", k=4, marks=set(keys), maxz=maxz)
    f = found[pick:pick + 1] if found else []
    box = ts.window(f, w, h, 4) if f else (c.width // 2 - w * 2, c.height // 2 - h * 2, c.width // 2 + w * 2, c.height // 2 + h * 2)
    im = c if mode == "classic" else scn.render(terr, block, "hd", k=4, maxz=maxz)[0]
    return ts.crop_pad(im, box)


def render_overlay(spec, mode, scn):
    """Кадры предмета кладутся на клетки блока (на карте их нет): классика x4 | HD из пака игры. Окно - вокруг клеток."""
    import map_mockup as mm
    import ticket_scene as ts
    _, terr, block, items, w, h = spec
    base = scn.render(terr, block, "classic" if mode == "classic" else "hd", k=4, maxz=0)[0]
    sx, sy, sz, _c = mm.read_block(scn.w, block)
    ox, oy = sy * 16, sz * 24 + 8
    cxs, cys = [], []
    for s, f, x, y in items:
        im = scn.classic(s, f) if mode == "classic" else scn.hd(s, f)
        px, py = ox + (x - y) * 16, oy + (x + y) * 8
        base.alpha_composite(im.convert("RGBA").resize((128, 160), Image.LANCZOS), (px * 4, py * 4))
        cxs.append(px + 16)
        cys.append(py + 24)
    cx, cy = sum(cxs) / len(cxs) * 4, sum(cys) / len(cys) * 4
    return ts.crop_pad(base, (int(cx - w * 2), int(cy - h * 2), int(cx + w * 2), int(cy + h * 2)))


def frames_strip(scn, items, mode):
    from PIL import ImageDraw
    cols = []
    for s, f in items:
        try:
            im = scn.classic(s, f) if mode == "classic" else scn.hd(s, f)
        except TypeError:          # нет листа классики набора в art/TERRAIN
            print("нет классики:", s, f)
            im = None
        base = Image.new("RGBA", (128, 160), (60, 60, 66, 255))
        if im is not None:
            base.alpha_composite(im.convert("RGBA").resize((128, 160)))
        cols.append(base)
    out = Image.new("RGBA", (len(cols) * 132, 160), (12, 12, 14, 255))
    for i, c in enumerate(cols):
        out.paste(c, (i * 132, 0))
    return out


def snap(item, tag):
    import ticket_scene as ts
    spec = SPECS[item]
    TMP.mkdir(parents=True, exist_ok=True)
    scn = ts.Scene()
    for i, sc in enumerate(spec["scenes"]):
        if tag == "before":
            render_scene(sc, "classic", scn).convert("RGB").save(TMP / ("%s_classic_%d.png" % (item, i)))
        render_scene(sc, "hd", scn).convert("RGB").save(TMP / ("%s_%s_%d.png" % (item, tag, i)))
    if spec.get("frames"):
        if tag == "before":
            frames_strip(scn, spec["frames"], "classic").convert("RGB").save(TMP / ("%s_classic_f.png" % item))
        frames_strip(scn, spec["frames"], "hd").convert("RGB").save(TMP / ("%s_%s_f.png" % (item, tag)))


def compose(item):
    import ticket_scene as ts
    spec = SPECS[item]
    panels = []
    for i, sc in enumerate(spec["scenes"]):
        for tag, name in (("classic", "классика x4"), ("before", "было (HD до установки)"), ("after", "стало (HD в игре)")):
            panels.append(("%s: %s" % (item, name), Image.open(TMP / ("%s_%s_%d.png" % (item, tag, i)))))
    if panels:
        ts.sheet(panels, REVIEW / ("installed_%s.png" % item), cols=3, width=900)
    if spec.get("frames"):
        rows = [(n, Image.open(TMP / ("%s_%s_f.png" % (item, t)))) for t, n in
                (("classic", "классика"), ("before", "было"), ("after", "стало"))]
        # кадры: подписи - список
        p = REVIEW / ("installed_%s_frames.png" % item)
        ts.sheet([("%s: %s  [%s]" % (item, n, ", ".join("%s:%d" % x for x in spec["frames"])), im) for n, im in rows], p, cols=1)
    print("лист:", REVIEW / ("installed_%s.png" % item))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) != 3 or sys.argv[1] not in ("before", "after") or sys.argv[2] not in SPECS:
        raise SystemExit(__doc__)
    cmd, item = sys.argv[1:]
    snap(item, cmd)
    if cmd == "after":
        compose(item)


if __name__ == "__main__":
    main()
