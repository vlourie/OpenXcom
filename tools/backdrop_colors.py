# Таблица hd/backdrop.txt (тикет XP-000263, часть А): цвет пустоты за краем карты боя по местности.
# Для каждого террейна Пираток берётся средний тон ПОЛА его блоков карт: клетки с полом (первый байт клетки),
# запись MCD -> кадр -> HD-картинка hd/TERRAIN/<набор>.PCK/<кадр>.png, среднее по непрозрачным пикселям,
# взвешенное числом клеток. Итог затемняется (--dim): пустота должна отступать за картой, а не светиться.
# Движок только читает файл (Map::hdBackdropRgb), строки "ИМЯ RRGGBB"; строки руками правит Vitali.
#   py -3 tools/backdrop_colors.py --out user/mods/hd/hd/backdrop.txt [--out2 ...]
import argparse
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np                                    # noqa: E402
from PIL import Image                                 # noqa: E402
import pck_census as pc                               # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", default=os.path.join("Пиратки", "Dioxine_XPiratez"))
    ap.add_argument("--mod", default="Piratez")
    ap.add_argument("--master", default="xcom1")
    ap.add_argument("--hd", default="", help="каталог hd мода (по умолчанию hd установки)")
    ap.add_argument("--dim", type=float, default=0.6)
    ap.add_argument("--out", required=True)
    ap.add_argument("--out2", default="")
    args = ap.parse_args()
    hd = args.hd or os.path.join(args.install, "user", "mods", "hd", "hd")
    mod_dir = os.path.join(args.install, "user", "mods", args.mod)
    files = pc.Files([mod_dir, os.path.join(args.install, "standard", args.master), os.path.join(args.install, "UFO")])
    terrains = pc.collect_terrains(mod_dir)
    # крафты и НЛО в боевую карту идут под своим типом, а не именем террейна: в таблицу нужны только настоящие террейны
    real = set()
    for name in os.listdir(os.path.join(mod_dir, "Ruleset")):
        if name.lower().endswith(".rul"):
            doc = pc.load_yaml(os.path.join(mod_dir, "Ruleset", name))
            real.update(t["name"] for t in (doc or {}).get("terrains") or [] if isinstance(t, dict) and t.get("name"))
    terrains = {n: t for n, t in terrains.items() if n in real}
    mcds, sizes, tone = {}, {}, {}

    def frame_tone(s, frame):
        key = (s, frame)
        if key not in tone:
            p = os.path.join(hd, "TERRAIN", s + ".PCK", "%d.png" % frame)
            t = None
            if os.path.exists(p):
                a = np.asarray(Image.open(p).convert("RGBA"), dtype=np.float64)
                m = a[..., 3] > 128
                if m.any():
                    t = a[..., :3][m].mean(axis=0)
            tone[key] = t
        return tone[key]

    rows = []
    for tname, t in sorted(terrains.items()):
        sets = list(t.get("mapDataSets") or [])
        for s in sets:
            if s not in sizes:
                sizes[s] = len(pc.mcd_records(files, s, mcds))
        cells = defaultdict(int)
        for b in t.get("mapBlocks") or []:
            name = b.get("name") if isinstance(b, dict) else None
            mp = files.find(os.path.join("MAPS", name + ".MAP")) if name else None
            if not mp:
                continue
            for cell in pc.read_map(mp):
                if cell[0]:
                    s, rec = pc.resolve(cell[0], sets, sizes)
                    if s is not None and rec < len(mcds[s]):
                        cells[(s, mcds[s][rec]["frames"][0])] += 1
        total, acc = 0, np.zeros(3)
        for (s, frame), n in cells.items():
            c = frame_tone(s, frame)
            if c is not None:
                total += n
                acc += c * n
        if total:
            rgb = np.clip(acc / total * args.dim, 0, 255).round().astype(int)
            rows.append((tname, "%02X%02X%02X" % tuple(rgb), total))
    text = "# hd/backdrop.txt: the void beyond the edge of the battle map, by ground (option 'Gradient beyond the map edge').\n" \
           "# A line is NAME RRGGBB: a terrain (the one most of the map's blocks come from) or a mission type; no line - the\n" \
           "# environment's own color. Made by tools/backdrop_colors.py (the mean tone of the floor x %.2f); edit by hand.\n" % args.dim
    text += "".join("%s %s\n" % (n, h) for n, h, _ in rows)
    for out in filter(None, [args.out, args.out2]):
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        with open(out, "w", encoding="utf-8-sig", newline="\n") as f:
            f.write(text)
    print("terrains: %d of %d" % (len(rows), len(terrains)))


main()
