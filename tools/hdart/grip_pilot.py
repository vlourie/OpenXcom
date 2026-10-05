"""Малый пилот контракта хвата (docs/research/grip-contract.md §9): одни и те же руки GOV_1 с разным оружием.

Сборка как routine 0 (порядок слоёв, кадры рук и предмета, сдвиги - grip_matrix.emulate): стойка и прицел, отдельно
занятая вторая рука (двуручное + пистолет, прицел). Руки и тело - HD пилота AGENT (art/units/pilot-agent/full/pose/pack),
оружие - HD там, где есть; чего нет в HD, нарисовано классикой x4 и подписано красным «HD нет: ...».

Черновые зоны кистей (art/units/grip-contract/pilot/zones_draft.json) - только для пилота, размечены руками на HD-кадрах
HANDOB, не договор с веткой оружия и не перенос с BIGOBS. Касание кисти с зоной - вспомогательная проверка,
решает лист глазами: цельная фигура, естественный хват, перекрытия.

    py -3.13 tools/hdart/grip_pilot.py [--dirs 2,4]
Видеокарта не нужна, новых рендеров нет.
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grip_matrix as G  # noqa: E402

OUT = os.path.join(G.OUT, "pilot")
ZONES = os.path.join(OUT, "zones_draft.json")
K = G.K
ZOOM = 2
# конструкции пилота: (тип предмета, подпись)
PILOT = [("STR_RIFLE_AK", "автомат AK"), ("STR_SNIPER_RIFLE", "длинная винтовка"),
         ("STR_LMG", "тяжёлое: пулемёт"), ("STR_TOMMYGUN", "передняя рукоять: Томпсон")]
SIDEARM = "STR_PISTOL"
# столбцы: (подпись, правая, левая, прицел, направление-сдвиг)
# сдвиг 0 - направление d; сдвиг 2 - стойка соседнего направления d+2, где кадр предмета тот же, что в прицеле d
COLS = [("стойка", "2", None, False, 0), ("прицел", "2", None, True, 0),
         ("стойка d+2\n(тот же кадр)", "2", None, False, 2),
         ("занята левая:\n2р + пистолет, прицел", "2", "1", True, 0),
         ("занята правая:\nпистолет + 2р, прицел", "1", "2", True, 0)]
ZONE_COL = {"grip": (255, 210, 0), "support": (0, 220, 255)}


def items():
    by, _ = G.load_items()
    t = {r["type"]: hs for hs, its in by.items() for r in its}
    return t


def body(n, miss):
    l, ok = G.hd_or("GOV_1.PCK", n, G.gov(n), G.gpal)
    if not ok:
        miss.append("руки/тело %d" % n)
    return l


def item(fi, miss):
    l, ok = G.hd_or("HANDOB.PCK", fi, G.hob(fi), G.hpal)
    if not ok:
        miss.append("оружие %d" % fi)
    return l, ok


def assemble(R, L, aim, d, hs, zones):
    """Кадр routine 0 x4; возвращает картинку, список недостающего HD, зоны на кадре (прямоугольники x4) и кисти."""
    e = G.emulate(0, R, L, aim)
    P = G.ROUT[0]
    miss, placed_zones = [], []
    src = {"la": body(e["la"] + d, miss), "ra": body(e["ra"] + d, miss),
           "lg": body(P["legs"] + d, miss), "to": body(P["torso"] + d, miss)}
    for slot, (kind, rot, ox, oy, _) in e["items"].items():
        fi = hs[slot] + (d + rot) % 8
        lay, hd = item(fi, miss)
        src[slot] = G.place(lay, ox[d], oy[d])
        for zk, rects in zones.get(str(fi), {}).items():
            for x0, y0, x1, y1 in rects:
                placed_zones.append((slot, zk, (x0 + ox[d] * K, y0 + oy[d] * K, x1 + ox[d] * K, y1 + oy[d] * K)))
    seq = [n for n in G.layer_order(0, d, e["alt"]) if n in src]
    img = G.pic([src[n] for n in seq])
    hands = {}
    for arm in ("ra", "la"):
        hc = hd_hand(src[arm])
        if hc is None:      # классика x4: кисть по коже классического кадра
            hm, _how = G.hand_mask(G.gov(e[arm] + d))
            ys, xs = np.nonzero(hm)
            hc = ((xs.mean() + 0.5) * K, (ys.mean() + 0.5) * K) if len(xs) else None
        if hc is not None:
            hands[arm] = (hc[0], hc[1], e["hold"][arm])
    return img, sorted(set(miss)), placed_zones, hands, e


def hd_hand(layer):
    """Кисть на HD-слое руки: телесные пиксели (R > G > B, R - B > 40), только те, что видны сквозь альфу.
    У классики x4 блоки ровно 4x4 - она отсекается проверкой на ступени: тогда None."""
    rgb, a = layer
    if np.all(rgb[::K, ::K].repeat(K, 0).repeat(K, 1) == rgb):
        return None
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    sk = (a > 0.5) & (r > g) & (g > b) & (r - b > 40) & (r > 110)
    ys, xs = np.nonzero(sk)
    if len(xs) < 20:
        return None
    return xs.mean(), ys.mean()


def touch(hands, zones, e):
    """Вспомогательно: в какой зоне своего предмета центр кисти (с запасом 1 пикс базы). Ожидание задано только для
    двуручного в правой: правая - grip, левая - support. При двуручном в левой кадр предмета тот же, и ожидание не
    назначается - пишется только, куда кисть попала."""
    out = []
    for arm, (cx, cy, slot) in hands.items():
        if slot is None:
            continue
        side = "пр" if arm == "ra" else "лев"
        mine = [(k, r) for s, k, r in zones if s == slot]
        if not mine:
            out.append("%s: зон нет" % side)
            continue
        hit = sorted({k for k, (x0, y0, x1, y1) in mine if x0 - K <= cx <= x1 + K and y0 - K <= cy <= y1 + K})
        want = None
        if slot == "iR" and e["items"]["iR"][0] == "2":
            want = "grip" if arm == "ra" else "support"
        got = "/".join(hit) if hit else "мимо зон"
        out.append("%s %s%s" % (side, got, "" if want is None or want in hit else " (ждали %s)" % want))
    return out


def wrap(dr, text, font, width):
    lines, cur = [], ""
    for w in text.split(" "):
        t = (cur + " " + w).strip()
        if cur and dr.textlength(t, font=font) > width:
            lines.append(cur)
            cur = w
        else:
            cur = t
    return lines + ([cur] if cur else [])


def cell(img, miss, zones, hands, marks):
    big = img.resize((img.width * ZOOM, img.height * ZOOM), Image.NEAREST)
    dr = ImageDraw.Draw(big)
    if marks:
        for _s, zk, (x0, y0, x1, y1) in zones:
            dr.rectangle([x0 * ZOOM, y0 * ZOOM, x1 * ZOOM, y1 * ZOOM], outline=ZONE_COL[zk], width=2)
        for arm, (cx, cy, _slot) in hands.items():
            c = (0, 255, 0) if arm == "ra" else (255, 120, 255)
            dr.line([(cx * ZOOM - 7, cy * ZOOM), (cx * ZOOM + 7, cy * ZOOM)], fill=c, width=2)
            dr.line([(cx * ZOOM, cy * ZOOM - 7), (cx * ZOOM, cy * ZOOM + 7)], fill=c, width=2)
    return big


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dirs", default="2")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    with open(ZONES, encoding=G.ENC) as f:
        zall = json.load(f)
    t = items()
    font = ImageFont.truetype(G.FONT, 14)
    fontb = ImageFont.truetype(G.FONT, 18)
    cw, ch = 32 * K * ZOOM, 40 * K * ZOOM
    lw, top, foot = 190, 74, 64
    report = []
    for d in [int(x) for x in a.dirs.split(",")]:
        rows = []
        for typ, name in PILOT:
            if typ not in t:
                print("нет кадра в руке:", typ)
                continue
            for marks in (False, True):
                cells = []
                for cname, R, L, aim, dd in COLS:
                    dir_ = (d + dd) % 8
                    hs = {}
                    if R:
                        hs["iR"] = t[typ] if R == "2" else t[SIDEARM]
                    if L:
                        hs["iL"] = t[typ] if L == "2" else t[SIDEARM]
                    z = {}
                    for ty in (typ, SIDEARM):
                        z.update(zall.get(ty, {}))
                    img, miss, zones, hands, e = assemble(R, L, aim, dir_, hs, z)
                    tc = touch(hands, zones, e)
                    cells.append((cell(img, miss, zones, hands, marks), miss, tc, dir_))
                    if marks:
                        report.append("\t".join([str(d), typ, cname.replace("\n", " "), str(dir_),
                                                 "; ".join(miss) or "-", "; ".join(tc) or "-"]))
                rows.append(("%s\n%s" % (name, "зоны и кисти" if marks else "как в игре"), cells, marks))
        W = lw + len(COLS) * (cw + 8)
        H = top + len(rows) * (ch + foot)
        out = Image.new("RGB", (W, H), (26, 26, 28))
        dr = ImageDraw.Draw(out)
        dr.text((8, 6), "Пилот хвата, routine 0 (GOV_1 руки пилота AGENT), направление %d" % d, fill=(255, 255, 255),
                font=fontb)
        dr.text((8, 30), "зоны: жёлтая - основная кисть (grip), голубая - опорная (support), черновик пилота; "
                         "крест: зелёный - правая кисть, розовый - левая", fill=(190, 190, 190), font=font)
        for j, (cname, *_r) in enumerate(COLS):
            dr.text((lw + j * (cw + 8) + 4, top - 36), cname, fill=(255, 220, 120), font=font)
        for i, (rname, cells, marks) in enumerate(rows):
            y = top + i * (ch + foot)
            for k, line in enumerate(rname.split("\n")):
                dr.text((6, y + 120 + 18 * k), line, fill=(255, 255, 255), font=font)
            for j, (im, miss, tc, dir_) in enumerate(cells):
                x = lw + j * (cw + 8)
                out.paste(im, (x, y))
                yy = y + ch + 2
                dr.text((x + 2, yy), "d%d" % dir_, fill=(200, 200, 200), font=font)
                lines = wrap(dr, ("HD нет: " + ", ".join(miss)) if miss else "", font, cw - 34)
                for k, ln in enumerate(lines[:2]):
                    dr.text((x + 30, yy + 16 * k), ln, fill=(255, 90, 90), font=font)
                if marks and tc:
                    dr.text((x + 2, yy + 34), "; ".join(tc), fill=(160, 220, 160), font=font)
        p = os.path.join(OUT, "pilot_d%d.png" % d)
        out.save(p)
        print(p, out.size)
    tsv = os.path.join(OUT, "pilot_touch.tsv")
    with open(tsv, "w", encoding=G.ENC, newline="") as f:
        f.write("dir\ttype\tcolumn\tframe_dir\thd_missing\ttouch\n")
        f.write("\n".join(report) + "\n")
    print(tsv)


if __name__ == "__main__":
    main()
