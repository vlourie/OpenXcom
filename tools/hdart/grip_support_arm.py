"""Пробная общая опорная рука двуручного прицела d2 (специалист 06.10, grip-contract.md §9.3).

Опорная (левая) рука прицела d2 - кадр 242, тот же, что в стойке; движок при STATUS_AIMING берёт его вариант
242.v1, если он есть (UnitSprite: setFrameVariant(1) на всё тело), поэтому пробная рука - это 242.v1, движок не
меняется. Рука одна на все стволы: подгонки под отдельное оружие нет, оружие не двигается.

Как получена: HD-кадр 242 пилота AGENT сдвинут ЦЕЛИКОМ (жёстко, без растяжки, R-208), анатомия руки не меняется.
Верх рукава в 242 срезан ровно и прячется под выступом плеча торса 34 (порядок слоёв d2: la lg to iL iR ra), поэтому
сдвиг вправо открывает срез «коробкой», а сдвиг вниз больше 0.75 - дыру у плеча. Стык мерит seam() в строках
плеча (выше SEAM_Y): дыра (было закрыто, стало фоном) и открытый срез (новый верхний край рукава над фоном). Общая рука - наибольший
сдвиг строго вниз, при котором оба числа 0 -> 242.v1.png.
Контроли, жёстким сдвигом кисти на цель (база), стык у них ломается - видно на листе и в числах:
  classic   - центр кисти классического кадра 242 (22.5, 18.5);
  consensus - общая область опоры цевья по grip_check8 (support_common_r0.tsv).
Прежний 242.v1 (AIM_RAISE, отклонён) был подогнан под AK с поднятым оружием - здесь не используется.

Лист: прицел d2 как в игре и с меткой кисти; AK - HD пилота, остальные - классика x4: они проверяют только
положение кисти против договорного места оружия, видимость кисти по ним не судится (классика толще HD и закрывает
её). Числа - grip_support_arm.tsv.

    py -3.13 tools/hdart/grip_support_arm.py
Видеокарта не нужна.
"""
import csv
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grip_matrix as G  # noqa: E402
import grip_pilot as P  # noqa: E402

K = G.K
OUT = os.path.join(P.OUT, "arm")
ARM = os.path.join(G.HD, "GOV_1.PCK", "242.png")
TORSO = os.path.join(G.HD, "GOV_1.PCK", "34.png")     # торс прицела d2 (32 + d)
SEAM_Y = 13                     # строки плеча, база: выступ торса 34 над рукавом кончается на y 12; ниже - наружный
                                # край предплечья, он при сдвиге смещается законно и стыком не считается
D = 2
CLASSIC_HAND = (22.5, 18.5)
# общая область опоры ветки оружия (grip_check8/support_common_r0.tsv, TWO_AIM d2: consensus_centre по W-059, W-071,
# W-015 - место на цевье, общее для большинства конструкций)
CONSENSUS = (24.3, 18.6)
# стволы: (подпись, handSprite, HD или классика)
GUNS = [("AK (HD)", 1352, True), ("Снайперка W-071", 3680, False), ("Автоган W-018", 1784, False),
        ("Томпсон W-014", 1640, False), ("W-059", 3416, False), ("W-015", 1592, False)]
CROP = (60, 40, 116, 96)        # x4: кисть и цевьё
ZOOM = 7
SEAM_CROP = (68, 36, 104, 80)   # x4: плечо, рукав и кисть
SEAM_ZOOM = 12


def skin(rgb, a):
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    return (a > 0.5) & (r > g) & (g > b) & (r - b > 40) & (r > 110)


def hand_centre(layer):
    ys, xs = np.nonzero(skin(*layer))
    return (xs.mean() + 0.5) / K, (ys.mean() + 0.5) / K


def gun_layer(hs, hd):
    fi = hs + (D + 2) % 8      # TWO_AIM: кадр hs + (d+2)%8
    if hd:
        lay, ok = P.item(fi, [])
    else:
        lay = G.rgba_classic(G.hob(fi), G.hpal)
    ox, oy = G.OFF["TWO_AIM"]
    return G.place(lay, ox[D], oy[D]), fi


def shifted_arm(layer, dx, dy):
    rgb, a = layer
    return G.shifted(rgb, dx, dy), G.shifted(a, dx, dy)


def contact(arm, gun):
    """Кожа кисти против оружия: доля кожи под оружием (закрыта им - кисть за цевьём) и зазор, пикс базы."""
    sk = skin(*arm)
    g = gun[1] > 0.5
    covered = (sk & g).sum() / max(sk.sum(), 1)
    if (sk & g).any():
        gap = 0.0
    else:
        gy, gx = np.nonzero(g)
        sy, sx = np.nonzero(sk)
        gap = float(np.sqrt(((sx[:, None] - gx[None, :]) ** 2 + (sy[:, None] - gy[None, :]) ** 2).min())) / K
    return covered, gap


def seam(arm, base, torso):
    """Стык рукава у торса после сдвига, пикс x4 в строках плеча (выше SEAM_Y базы):
    hole - было закрыто рукой или торсом, стало фоном (дыра у плеча);
    cut  - открытый ровный срез рукава: видимый пиксель руки, над которым фон, а в кадре 242 над этим местом
           ни руки, ни открытого края не было (срез верха рукава, прятавшийся под торсом)."""
    t = torso[1] > 0.5
    a0 = base[1] > 0.5
    a = arm[1] > 0.5
    rows = np.zeros_like(t)
    rows[:SEAM_Y * K] = True
    hole = int((rows & (t | a0) & ~(t | a)).sum())
    vis = a & ~t
    above = np.zeros_like(vis)
    above[1:] = ~(t | a)[:-1]
    vis0 = a0 & ~t
    above0 = np.zeros_like(vis0)
    above0[1:] = ~(t | a0)[:-1]
    cut = int(max(0, (rows & vis & above).sum() - (rows & vis0 & above0).sum()))
    return hole, cut


def main():
    os.makedirs(OUT, exist_ok=True)
    base = G.ld(ARM)
    torso = G.ld(TORSO)
    hc = hand_centre(base)
    # общая рука: сдвиг строго вниз, наибольший, при котором стык цел (hole и cut 0); оружие не двигается
    down = 0
    for dy in range(1, 4 * K):
        if seam(shifted_arm(base, 0, dy), base, torso) != (0, 0):
            break
        down = dy
    variants = [("242 (как сейчас)", base, (0, 0)),
                ("down: общая рука, сдвиг 0,%+.2f" % (down / K), shifted_arm(base, 0, down), (0, down))]
    # контроли: кисть на место классической кисти и на общую область цевья - жёстким сдвигом с dx
    for name, (tx, ty) in (("classic", CLASSIC_HAND), ("consensus", CONSENSUS)):
        dx, dy = int(round((tx - hc[0]) * K)), int(round((ty - hc[1]) * K))
        variants.append(("%s: цель %.2f,%.2f, сдвиг %+.2f,%+.2f" % (name, tx, ty, dx / K, dy / K),
                         shifted_arm(base, dx, dy), (dx, dy)))
    for f in os.listdir(OUT):           # прежние пробы (axis и др.) не оставлять рядом с выбранной
        if f.startswith("242.v1.") and f.endswith(".png"):
            os.remove(os.path.join(OUT, f))
    rgb, a = variants[1][1]
    Image.fromarray(np.dstack([np.clip(rgb, 0, 255), np.clip(a * 255, 0, 255)]).astype(np.uint8),
                    "RGBA").save(os.path.join(OUT, "242.v1.png"))
    seams = {v[0]: seam(v[1], base, torso) for v in variants}
    font = ImageFont.truetype(G.FONT, 14)
    fontb = ImageFont.truetype(G.FONT, 17)
    x0, y0, x1, y1 = CROP
    cw, ch = (x1 - x0) * ZOOM // 2, (y1 - y0) * ZOOM // 2
    lw, top, foot = 150, 70, 40
    out = Image.new("RGB", (lw + len(variants) * 2 * (cw + 6) + 20, top + len(GUNS) * (ch + foot)), (26, 26, 28))
    dr = ImageDraw.Draw(out)
    dr.text((8, 6), "Общая опорная рука, прицел d2: одна рука на все стволы, оружие на своём месте", fill=(255, 255, 255),
            font=fontb)
    dr.text((8, 30), "кисть HD 242: центр %.2f,%.2f база; классика 242: %.2f,%.2f. Крест - центр кожи кисти. "
                     "AK - HD, остальные - классика x4 (договор положения)" % (hc + CLASSIC_HAND),
            fill=(190, 190, 190), font=font)
    rows = []
    for j, (vname, _l, _s) in enumerate(variants):
        dr.text((lw + j * 2 * (cw + 6) + 4, top - 20), vname, fill=(255, 220, 120), font=font)
    for i, (gname, hs, hd) in enumerate(GUNS):
        y = top + i * (ch + foot)
        dr.text((6, y + ch // 2 - 8), gname, fill=(255, 255, 255), font=font)
        gun, fi = gun_layer(hs, hd)
        old = P.HOBF
        if not hd:
            P.HOBF = {}
        for j, (vname, arm, sh) in enumerate(variants):
            img, _miss, _z, _h, _e, _f = P.assemble("2", None, True, D, {"iR": hs}, {}, arms={"la": arm})
            cov, gap = contact(arm, gun)
            c = hand_centre(arm)
            hole, cut = seams[vname]
            rows.append([gname, str(fi), vname.split(":")[0], "%.2f,%.2f" % c, "%.2f" % cov, "%.2f" % gap,
                         str(hole), str(cut)])
            for k, marks in enumerate((False, True)):
                big = img.crop((x0, y0, x1, y1)).resize((cw, ch), Image.NEAREST)
                if marks:
                    d2 = ImageDraw.Draw(big)
                    cx, cy = (c[0] * K - x0) * ZOOM / 2, (c[1] * K - y0) * ZOOM / 2
                    d2.line([(cx - 8, cy), (cx + 8, cy)], fill=(255, 120, 255), width=2)
                    d2.line([(cx, cy - 8), (cx, cy + 8)], fill=(255, 120, 255), width=2)
                x = lw + (2 * j + k) * (cw + 6)
                out.paste(big, (x, y))
            dr.text((lw + 2 * j * (cw + 6) + 2, y + ch + 3),
                    "под оружием %d %%, зазор %.1f; стык: дыра %d, срез %d" % (round(cov * 100), gap, hole, cut),
                    fill=(160, 220, 160) if (hole, cut) == (0, 0) else (255, 140, 120), font=font)
        P.HOBF = old
    p = os.path.join(OUT, "support_arm_d2.png")
    out.save(p)
    print(p, out.size)
    # плечо крупно: стык рукава у торса, с AK HD
    sx0, sy0, sx1, sy1 = SEAM_CROP
    sw, sh = (sx1 - sx0) * SEAM_ZOOM // 2, (sy1 - sy0) * SEAM_ZOOM // 2
    so = Image.new("RGB", (len(variants) * (sw + 8), sh + 28), (26, 26, 28))
    ds = ImageDraw.Draw(so)
    for j, (vname, arm, _s) in enumerate(variants):
        img = P.assemble("2", None, True, D, {"iR": GUNS[0][1]}, {}, arms={"la": arm})[0]
        so.paste(img.crop(SEAM_CROP).resize((sw, sh), Image.NEAREST), (j * (sw + 8), 28))
        hole, cut = seams[vname]
        ds.text((j * (sw + 8) + 2, 4), "%s - дыра %d, срез %d" % (vname.split(":")[0], hole, cut),
                fill=(160, 220, 160) if (hole, cut) == (0, 0) else (255, 140, 120), font=font)
    p = os.path.join(OUT, "support_arm_seam.png")
    so.save(p)
    print(p, so.size)
    tsv = os.path.join(OUT, "grip_support_arm.tsv")
    with open(tsv, "w", encoding=G.ENC, newline="") as f:
        w = csv.writer(f, delimiter="\t", quoting=csv.QUOTE_NONE, lineterminator="\n")
        w.writerow(["gun", "frame", "arm", "hand_centre", "skin_under_gun", "gap_base_px", "seam_hole_x4",
                    "seam_cut_x4"])
        w.writerows(rows)
    print(tsv)
    for r in rows:
        print("\t".join(r))


if __name__ == "__main__":
    main()
