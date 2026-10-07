"""Тот же пак ROADS на втором реальном участке, без подгонки кадров под сцену: чистые кадры игры (shot.png, без пара)
классики (режим 0), пака установки и сборки new на копиях сейва EUROSYNDICATE_279 (e2_cross.sav - перекрёсток с
решётками стока x 21..28, y 51..58, e2_park.sav - парковка с кадром 12). Условия съёмки: globalShade 0, весь пол
этажа 0 открыт - так видны все клетки участка; на настоящей миссии свет и туман другие.

Лист: обзор участка 1:1 (три вида друг под другом) и вырезы x2 по каждому кадру ROADS, который на участке есть
(бордюры обоих направлений, углы, разметка, решётка, кадр 12, асфальт у тротуара без бордюра), и по узлам на
границах MAP-блоков (каждые 10 клеток), где с обеих сторон ROADS. Вырез берётся у клетки, где середина окна меньше всего закрыта
юнитом, предметом, стеной или объектом, интерфейсом (доля в подписи). Съёмка - scratchpad e2_dumps.py
(game_hidden --key ctrl+289, метки classic_/hd_now_/new_ + e2c, e2p).

    py -3.13 tools/hdart/crossing_second.py
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crossing_build as cb         # noqa: E402
import crossing_check as cc         # noqa: E402
import crossing_clean as ccl        # noqa: E402
import map_screen_check as msc      # noqa: E402

D = cb.OUT / "_dumps"
SITES = {"e2c": ("e2_cross.sav", "перекрёсток с решётками стока", (31, 55), (19, 49, 32, 61)),
         "e2p": ("e2_park.sav", "парковка с кадром 12", (52, 27), (40, 18, 54, 30))}
KINDS = ccl.KINDS
NAMES = ccl.NAMES
FRAME_NAME = {0: "тротуар", 1: "бордюр +u (передний)", 2: "бордюр +v (передний)", 3: "бордюр -v (задний)",
              4: "бордюр -u (задний)", 5: "угол +u -v", 6: "угол +v -u", 7: "угол +u +v (передний)",
              8: "угол -u -v (задний)", 9: "асфальт", 10: "разметка по -u", 11: "разметка по -v",
              12: "разметка по -u и -v", 13: "решётка стока"}
HALF_X, HALF_Y = 44, 28          # окно выреза в базовых пикселях вокруг точки
ZOOM = 2
MAX_COVER = 0.25                 # закрыто больше четверти середины окна - выреза нет
FONT = ImageFont.truetype(cb.sp.js.FONT, 18)


def site_data(tag):
    save = cb.OUT / "_game_ref" / SITES[tag][0]
    jd = {kd: json.loads((D / ("%s_%s" % (kd, tag)) / "dump.json").read_text(encoding=cb.ENC)) for kd in KINDS}
    cams = {(j["cameraOffsetX"], j["cameraOffsetY"], j["cameraOffsetZ"], j.get("globalShade")) for j in jd.values()}
    if len(cams) != 1:
        raise SystemExit("участок %s: камера/свет разные %s" % (tag, cams))
    bt, data, k, W, H, cam, _img, owner = cc.owners(str(save), jd["new"])
    im = {kd: Image.open(D / ("%s_%s" % (kd, tag)) / "shot.png").convert("RGB") for kd in KINDS}
    # закрытое: юниты, предметы, дым и огонь (как cc.cover_masks, без пара), стены и объекты, интерфейс
    bad = np.zeros((H, W), bool)

    def box(x, y, z, l_, t, r, b):
        px = x * 16 - y * 16 + cam[0]
        py = x * 8 + y * 8 - z * 24 + cam[1]
        bad[max(0, py + t):max(0, min(H, py + b)), max(0, px + l_):max(0, min(W, px + r))] = True
    st = msc.unit_status(str(save))
    us, _sel = msc.units(str(save))
    for uid, (x, y, z), _f in us:
        if x >= 0 and st.get(uid, 0) not in (6, 7) and z <= cam[2]:
            for dx in (0, 1):
                for dy in (0, 1):
                    box(x - dx, y - dy, z, -8, -32, 40, 44)
    for x, y, z in msc.floor_items(str(save)):
        if z <= cam[2]:
            box(x, y, z, 0, -8, 32, 44)
    for z, y, x in zip(*np.nonzero((bt.smoke > 0) | (bt.fire > 0))):
        if z <= cam[2]:
            box(x, y, z, -4, -16, 36, 44)
    part = np.where(owner > 0, (owner - 1) % 4, -1)
    bad |= (owner > 0) & (part != 0)
    for x0, y0, x1, y1 in ccl.HUD:
        bad[max(0, y0 // k):max(0, y1 // k), max(0, x0 // k):max(0, x1 // k)] = True
    fr = {}
    for x in range(bt.X):
        for y in range(bt.Y):
            cur = bt.part(0, y, x, 0)
            if cur is not None:
                fr[(x, y)] = (bt.sets[cur[0]], data.mcd(bt.sets[cur[0]])[cur[1]]["frames"][0])
    return dict(tag=tag, k=k, cam=cam, W=W, H=H, im=im, bad=bad, fr=fr, js=jd["new"])


def window(S, gx, gy):
    X, Y = cb.grid_xy(gx, gy, 1, S["cam"])
    b = (int(X - HALF_X), int(Y - HALF_Y), int(X + HALF_X), int(Y + HALF_Y))
    if b[0] < 0 or b[1] < 0 or b[2] > S["W"] or b[3] > S["H"]:
        return None, 1.0
    # закрытая доля: в средней половине окна (сам узел и ближайшие соседи)
    q = S["bad"][b[1] + HALF_Y // 2:b[3] - HALF_Y // 2, b[0] + HALF_X // 2:b[2] - HALF_X // 2]
    return tuple(c * S["k"] for c in b), float(q.mean())


def cut(S, b, label):
    tiles = []
    for kd in KINDS:
        t = S["im"][kd].crop(b)
        tiles.append(t.resize((t.width * ZOOM, t.height * ZOOM), Image.NEAREST))
    w, h = tiles[0].size
    row = Image.new("RGB", (3 * (w + 8), h + 28), (24, 24, 28))
    ImageDraw.Draw(row).text((4, 4), label + "   |   " + "  -  ".join(NAMES[kd] for kd in KINDS), font=FONT,
                             fill=(255, 255, 255))
    for i, t in enumerate(tiles):
        row.paste(t, (i * (w + 8), 28))
    return row


def picks(S):
    """(узел, подпись) для вырезов: каждый кадр ROADS участка, потом узлы на границах MAP-блоков."""
    x0, y0, x1, y1 = SITES[S["tag"]][3]
    out, seen = [], set()
    roads = {c: f for c, (s, f) in S["fr"].items() if s == "ROADS" and x0 <= c[0] <= x1 and y0 <= c[1] <= y1}
    for f in sorted(set(roads.values())):
        (b, frac), c = min(((window(S, c[0] + 0.5, c[1] + 0.5), c) for c in roads if roads[c] == f),
                           key=lambda t: (t[0][1], t[1]))
        if frac <= MAX_COVER:
            nb = sorted({S["fr"].get((c[0] + dx, c[1] + dy), ("-", -1))[1]
                         for dx in (-1, 0, 1) for dy in (-1, 0, 1) if (dx, dy) != (0, 0)})
            out.append((b, "ROADS %d (%s), клетка %d,%d; соседи - кадры %s; закрыто %d%%" % (
                f, FRAME_NAME.get(f, "?"), c[0], c[1], ",".join(str(n) for n in nb), round(100 * frac))))
            seen.add(f)
        else:
            out.append((None, "ROADS %d (%s): на участке %d клеток, чистого окна нет" % (
                f, FRAME_NAME.get(f, "?"), sum(1 for ff in roads.values() if ff == f))))
    # границы MAP-блоков: узлы на x = 10n или y = 10n, с обеих сторон ROADS разных кадров - сначала
    done = 0
    for line in ("x", "y"):
        cand = []
        for c, f in roads.items():
            if line == "x" and c[0] % 10 == 0 and (c[0] - 1, c[1]) in roads:
                cand.append(((c[0], c[1] + 0.5), (c[0] - 1, c[1]), c))
            if line == "y" and c[1] % 10 == 0 and (c[0], c[1] - 1) in roads:
                cand.append(((c[0] + 0.5, c[1]), (c[0], c[1] - 1), c))
        cand.sort(key=lambda t: (roads[t[1]] == roads[t[2]], t[2]))
        n = 0
        for (gx, gy), a, b_ in cand:
            b, frac = window(S, gx, gy)
            if frac > MAX_COVER:
                continue
            out.append((b, "граница MAP-блоков %s = %d: клетки %d,%d (кадр %d) | %d,%d (кадр %d)" % (
                line, b_[0] if line == "x" else b_[1], a[0], a[1], roads[a], b_[0], b_[1], roads[b_])))
            n += 1
            if n == 2:
                break
        done += n
    return out, roads


def overview(S):
    x0, y0, x1, y1 = SITES[S["tag"]][3]
    pts = [cb.grid_xy(x, y, S["k"], S["cam"]) for x in (x0, x1 + 1) for y in (y0, y1 + 1)]
    b = [int(min(p[0] for p in pts)), int(min(p[1] for p in pts)), int(max(p[0] for p in pts)),
         int(max(p[1] for p in pts))]
    b = (max(0, b[0]), max(0, b[1]), min(1920, b[2]), min(1080 - 230, b[3]))
    tiles = [S["im"][kd].crop(b) for kd in KINDS]
    w, h = tiles[0].size
    out = Image.new("RGB", (w, 3 * (h + 30)), (24, 24, 28))
    d = ImageDraw.Draw(out)
    for i, t in enumerate(tiles):
        d.text((4, i * (h + 30) + 4), "%s: %s, 1:1" % (SITES[S["tag"]][1], NAMES[KINDS[i]]), font=FONT,
               fill=(255, 255, 255))
        out.paste(t, (0, i * (h + 30) + 30))
    return out


def main():
    res = {}
    for tag in SITES:
        S = site_data(tag)
        rows, roads = picks(S)
        ov = overview(S)
        cuts = [cut(S, b, lbl) for b, lbl in rows if b is not None]
        W = max([ov.width] + [c.width for c in cuts])
        H = 60 + ov.height + sum(c.height + 10 for c in cuts) + 30 * sum(1 for b, _ in rows if b is None)
        sheet = Image.new("RGB", (W, H), (24, 24, 28))
        d = ImageDraw.Draw(sheet)
        d.text((8, 8), "Второй участок ROADS (%s, юнит на %d,%d): пак сборки new без подгонки под сцену; съёмка при "
               "globalShade 0, пол этажа 0 открыт" % (SITES[tag][1], *SITES[tag][2]), font=FONT, fill=(255, 255, 255))
        d.text((8, 32), "кадры ROADS на участке: %s" % ", ".join(
            "%d x%d" % (f, sum(1 for v in roads.values() if v == f)) for f in sorted(set(roads.values()))),
            font=FONT, fill=(255, 255, 255))
        sheet.paste(ov, (0, 60))
        y = 60 + ov.height + 10
        for (b, lbl) in rows:
            if b is None:
                d.text((8, y), lbl, font=FONT, fill=(255, 120, 120))
                y += 30
        for c in cuts:
            sheet.paste(c, (0, y))
            y += c.height + 10
        p = cb.OUT / ("second_%s.png" % tag)
        sheet.save(p)
        res[tag] = dict(save=SITES[tag][0], camera=list(S["cam"]), globalShade=S["js"].get("globalShade"),
                        frames={str(f): sum(1 for v in roads.values() if v == f) for f in sorted(set(roads.values()))},
                        cuts=[lbl for b, lbl in rows])
        print(p, sheet.size)
        for b, lbl in rows:
            print("  ", "" if b else "НЕТ ОКНА:", lbl)
    (cb.OUT / "second.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding=cb.ENC)


if __name__ == "__main__":
    main()
