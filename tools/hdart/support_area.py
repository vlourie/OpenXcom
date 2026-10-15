"""Опора второй руки в одной системе координат (указание специалиста 06.10, drawRoutine0).

Вопрос: «мимо 2.8-11.7 пикс» и «перенос до 16.5» - одна мера или разные? Здесь обе рядом, в координатах кадра
юнита 32x40 (пиксель базы, x вправо, y вниз, начало - левый верх кадра юнита; кадр предмета уже сдвинут offX/offY).

На вид хвата x направление x конструкцию (пять огнестрельных из parts_manual.json, опора - цевьё):
  - исходная кисть: вся кожа кадра опорной руки (до перекрытия) и видимая после сборки, центр кожи;
  - цевьё: пиксели рисунка в рамке разметки (sure/med), центр;
  - старые меры: «мимо» - видимая кожа до БЛИЖАЙШЕГО пикселя оружия любой части (positions.tsv);
    «перенос» - центр кожи до СРЕДНЕГО центров цевья (pose_r0.tsv);
  - новые: вся кожа до ближайшего пикселя цевья (вектор между ближайшими пикселями) и центр до центра.
Общая цель - область, а не точка:
  - область цевья: пиксели, где цевьё лежит у большинства конструкций (не меньше половины), и их объединение;
  - область переноса: сдвиги t всей кожи кисти, при которых она касается (до 1.5 пикс) цевья КАЖДОЙ конструкции;
    ближайший к нулю такой сдвиг и размер области. Это геометрия жёсткого переноса кисти, не поза руки.

  py -3.13 tools/hdart/support_area.py
  -> art/items/weapons100-v1/grip_check8/: support_area_r0.tsv (по конструкциям), support_common_r0.tsv (общая),
     support_area_r0.png (лист)
"""
import csv
import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grip_check8 as g8  # noqa: E402
import grip_engine_check as gec  # noqa: E402
import grip_matrix as gm  # noqa: E402

ROOT, ENC, OUT, M = g8.ROOT, g8.ENC, g8.OUT, g8.M
TOUCH = g8.TOUCH
TR = 24                      # перебор сдвигов кисти, пикс базы
S = 8                        # масштаб листа
VIEW = g8.VIEW
CASES = (("TWO_AIM", "la"), ("TWO_STAND", "la"), ("LEFT_TWO_AIM", "ra"), ("LEFT_TWO_STAND", "ra"))


def f1(v):
    return "%.1f" % v


def xy(v):
    return "%.1f,%.1f" % (v[0], v[1])


def nearest(a, b):
    """Ближайшая пара a->b: (расстояние, вектор b-a)."""
    d = b[None, :, :] - a[:, None, :]
    n = np.sqrt((d ** 2).sum(-1))
    i, j = np.unravel_index(n.argmin(), n.shape)
    return float(n[i, j]), d[i, j]


def feasible(skin, fore):
    """Сдвиги t (целые, |tx|,|ty| <= TR), при которых skin+t касается fore."""
    d = (fore[None, :, :] - skin[:, None, :]).reshape(-1, 2)
    t = np.stack(np.meshgrid(np.arange(-TR, TR + 1), np.arange(-TR, TR + 1)), -1).reshape(-1, 2).astype(float)
    best = np.full(len(t), np.inf)
    for k in range(0, len(d), 256):
        dd = d[k:k + 256]
        best = np.minimum(best, np.sqrt(((t[:, None, :] - dd[None, :, :]) ** 2).sum(-1)).min(1))
    return {tuple(map(int, v)) for v in t[best <= TOUCH]}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.chdir(ROOT)
    lab = json.load(open(os.path.join(OUT, "parts_manual.json"), encoding=ENC))
    ws = [w for w, s in lab.items() if not w.startswith("_") and s["two"] and s["support"] == "forend"]
    aims = {int(r["dir"]): (float(r["aim_support_x"]), float(r["aim_support_y"]))
            for r in csv.DictReader(open("art/units/grip-contract/aim_support.tsv", encoding=ENC), delimiter="\t")}
    old = {}
    for r in csv.DictReader(open(os.path.join(OUT, "positions.tsv"), encoding=ENC), delimiter="\t",
                            quoting=csv.QUOTE_NONE):
        old[r["master"], r["case"], int(r["dir"])] = r
    rows, common, tiles = [], [], {}
    for case, arm in CASES:
        for d in range(8):
            per, fores, skin_all, skin_vis, body = {}, {}, None, None, None
            for w in ws:
                p = g8.position(w, lab[w], case, d)
                afr, allp, vis, _ = p["arms"][arm]
                allp, vis = allp - M, vis - M
                if skin_all is None:
                    skin_all, skin_vis, arm_frame = allp, vis, afr
                    body = p
                hob = [l for l in gec.ctx_layers(lab[w]["hs"], case, d) if l[1] == "hob"][0]
                idx = gm.hob(hob[2])
                wp = g8.pts(idx > 0) + (hob[3], hob[4])
                fr = p["parts"].get("forend")
                r = {"case": case, "dir": d, "master": w, "arm_frame": afr, "skin": len(allp), "skin_visible": len(vis),
                     "hand_centre": xy(allp.mean(0)) if len(allp) else ""}
                o = old.get((w, case, d), {})
                r["old_miss_visible_to_any_weapon_px"] = o.get("support_dist_weapon", "")
                r["old_verdict"] = o.get("support_verdict", "")
                if len(allp):
                    dw, vw = nearest(allp, wp)
                    r["geom_to_any_weapon_px"] = f1(dw)
                    tgt = allp[np.sqrt(((allp[:, None] - wp[None]) ** 2).sum(-1)).min(1).argmin()] + vw
                    on = [n for n, (pp, c, _) in p["parts"].items() if len(pp) and
                          np.sqrt(((pp - M - tgt) ** 2).sum(-1)).min() < 0.5]
                    r["nearest_weapon_pixel_part"] = ",".join(g8.NAMES[n] for n in on) or "без разметки"
                if fr and fr[1] != "low" and len(fr[0]):
                    fp = fr[0] - M
                    fores[w] = fp
                    bx = fr[2]
                    r["forend_box"] = "%d,%d-%d,%d" % (bx[0] - M, bx[1] - M, bx[2] - M, bx[3] - M)
                    r["forend_conf"] = fr[1]
                    r["forend_px"] = len(fp)
                    r["forend_centre"] = xy(fp.mean(0))
                    if len(allp):
                        dn, vn = nearest(allp, fp)
                        r["geom_to_forend_px"] = f1(dn)
                        r["vec_nearest_skin_to_forend"] = xy(vn)
                        c = fp.mean(0) - allp.mean(0)
                        r["vec_centre_to_centre"] = xy(c)
                        r["centre_to_centre_px"] = f1(float(np.hypot(*c)))
                    if len(vis):
                        r["visible_to_forend_px"] = f1(nearest(vis, fp)[0])
                else:
                    r["forend_conf"] = fr[1] if fr else "нет разметки"
                rows.append(r)
                per[w] = (wp, p)
            # общая область
            cr = {"case": case, "dir": d, "arm_frame": arm_frame, "weapons_with_forend": len(fores),
                  "weapons": ",".join(fores), "hand_centre": xy(skin_all.mean(0)) if len(skin_all) else "",
                  "skin": len(skin_all), "skin_visible": len(skin_vis)}
            cnt = {}
            for fp in fores.values():
                for v in {tuple(map(int, q)) for q in fp}:
                    cnt[v] = cnt.get(v, 0) + 1
            need = math.ceil(len(fores) / 2) if fores else 0
            union = np.array(sorted(cnt), float) if cnt else np.zeros((0, 2))
            cons = np.array(sorted(v for v, n in cnt.items() if n >= need), float) if cnt else np.zeros((0, 2))
            feas, tbest = None, None
            if fores and len(skin_all):
                mu = np.array([fp.mean(0) for fp in fores.values()]).mean(0)
                cr["forend_centres_mean"] = xy(mu)
                cr["old_move_centre_to_mean_px"] = f1(float(np.hypot(*(mu - skin_all.mean(0)))))
                cr["union_px"] = len(union)
                cr["consensus_need"] = need
                cr["consensus_px"] = len(cons)
                if len(cons):
                    cr["consensus_box"] = "%d,%d-%d,%d" % (cons[:, 0].min(), cons[:, 1].min(), cons[:, 0].max(),
                                                          cons[:, 1].max())
                    cr["consensus_centre"] = xy(cons.mean(0))
                    dn, vn = nearest(skin_all, cons)
                    cr["skin_to_consensus_px"] = f1(dn)
                    cr["vec_skin_to_consensus"] = xy(vn)
                du, vu = nearest(skin_all, union)
                cr["skin_to_union_px"] = f1(du)
                sets = [feasible(skin_all, fp) for fp in fores.values()]
                feas = set.intersection(*sets)
                cr["shift_area_all_weapons"] = len(feas)
                if feas:
                    tbest = min(feas, key=lambda t: (t[0] ** 2 + t[1] ** 2, t))
                    cr["shift_nearest_all_weapons"] = "%d,%d" % tbest
                    cr["shift_nearest_all_weapons_px"] = f1(math.hypot(*tbest))
                    fa = np.array(sorted(feas), float)
                    cr["shift_area_box"] = "%d,%d-%d,%d" % (fa[:, 0].min(), fa[:, 1].min(), fa[:, 0].max(),
                                                            fa[:, 1].max())
                else:   # сколько конструкций можно взять одним сдвигом
                    best = {}
                    for s_ in sets:
                        for t in s_:
                            best[t] = best.get(t, 0) + 1
                    if best:
                        k = max(best.values())
                        t = min((t for t, n in best.items() if n == k), key=lambda t: (t[0] ** 2 + t[1] ** 2, t))
                        cr["shift_max_weapons"] = k
                        cr["shift_for_max_weapons"] = "%d,%d" % t
                        tbest = t
                if case == "TWO_AIM":
                    a = np.array(aims[d])
                    cr["aim_support"] = "%d,%d" % tuple(a)
                    cr["aim_support_in_consensus"] = "да" if len(cons) and (
                        np.sqrt(((cons - a) ** 2).sum(1)).min() < 0.5) else "нет"
                    cr["aim_support_to_consensus_px"] = f1(float(np.sqrt(((cons - a) ** 2).sum(1)).min())) if len(
                        cons) else ""
            common.append(cr)
            tiles[case, d] = (body, arm, skin_all, skin_vis, per, cnt, need, feas, tbest, cr)
    for name, data in (("support_area_r0", rows), ("support_common_r0", common)):
        ks = []
        for r in data:
            ks += [k for k in r if k not in ks]
        with open(os.path.join(OUT, name + ".tsv"), "w", encoding=ENC, newline="") as f:
            wr = csv.DictWriter(f, ks, delimiter="\t", restval="")
            wr.writeheader()
            wr.writerows(data)
    sheet(tiles).save(os.path.join(OUT, "support_area_r0.png"))
    for cr in common:
        if cr["case"] in ("TWO_AIM", "TWO_STAND"):
            print(cr["case"], cr["dir"], "центр->среднее", cr.get("old_move_centre_to_mean_px"), "кожа->область",
                  cr.get("skin_to_consensus_px"), "сдвиг на все", cr.get("shift_nearest_all_weapons", "-"),
                  "область", cr.get("shift_area_all_weapons"), "макс", cr.get("shift_max_weapons", ""))


def tile(t):
    body, arm, skin_all, skin_vis, per, cnt, need, feas, tbest, cr = t
    x0, y0, x1, y1 = VIEW
    W, H = (x1 - x0) * S, (y1 - y0) * S
    im = Image.new("RGB", (W, H), (40, 44, 42))
    dr = ImageDraw.Draw(im)

    def at(x, y):
        return (x - x0) * S, (y - y0) * S

    # тело без оружия - серым, по слоям сборки
    rgb, who = body["rgb"], body["who"]
    for (yy, xx) in zip(*np.nonzero((who != "") & (who != "iR") & (who != "iL"))):
        x, y = xx - M, yy - M
        if x0 <= x < x1 and y0 <= y < y1:
            v = int(rgb[yy, xx].mean() * 0.45 + 40)
            a = at(x, y)
            dr.rectangle([a, (a[0] + S - 1, a[1] + S - 1)], fill=(v, v, v))
    # силуэты оружия - тонкие точки
    for wp, _ in per.values():
        for x, y in wp:
            if x0 <= x < x1 and y0 <= y < y1:
                a = at(x + 0.5, y + 0.5)
                dr.rectangle([(a[0] - 1, a[1] - 1), (a[0] + 1, a[1] + 1)], fill=(150, 150, 220))
    # цевьё: интенсивность по числу конструкций, большинство - оранжевая рамка
    n = max(cnt.values()) if cnt else 1
    for (x, y), c in cnt.items():
        a = at(x, y)
        k = c / max(n, 1)
        dr.rectangle([a, (a[0] + S - 1, a[1] + S - 1)], fill=(int(120 + 135 * k), int(100 + 120 * k), 30))
        if c >= need:
            dr.rectangle([a, (a[0] + S - 1, a[1] + S - 1)], outline=(255, 140, 0), width=1)
    # кожа кисти: вся - зелёная рамка, видимая - заливка
    vis = {tuple(map(int, v)) for v in skin_vis}
    for x, y in skin_all:
        a = at(x, y)
        if (int(x), int(y)) in vis:
            dr.rectangle([a, (a[0] + S - 1, a[1] + S - 1)], fill=(60, 200, 90))
        dr.rectangle([a, (a[0] + S - 1, a[1] + S - 1)], outline=(80, 255, 120), width=1)
    if not len(skin_all):
        return im
    hc = skin_all.mean(0) + 0.5
    # область сдвигов центра кисти, касающихся цевья всех конструкций - голубые точки
    if feas:
        for tx, ty in feas:
            a = at(hc[0] + tx, hc[1] + ty)
            dr.ellipse([(a[0] - 2, a[1] - 2), (a[0] + 2, a[1] + 2)], fill=(80, 220, 255))
    ac = at(*hc)
    if "forend_centres_mean" in cr:
        mu = np.array(list(map(float, cr["forend_centres_mean"].split(",")))) + 0.5
        b = at(*mu)
        dr.line([ac, b], fill=(255, 60, 220), width=3)
        dr.ellipse([(b[0] - 5, b[1] - 5), (b[0] + 5, b[1] + 5)], outline=(255, 60, 220), width=2)
    if tbest is not None:
        b = at(hc[0] + tbest[0], hc[1] + tbest[1])
        dr.line([ac, b], fill=(80, 220, 255), width=3)
    if "vec_skin_to_consensus" in cr:
        pass
    dr.ellipse([(ac[0] - 5, ac[1] - 5), (ac[0] + 5, ac[1] + 5)], fill=(255, 255, 255))
    if "aim_support" in cr:
        a = np.array(list(map(float, cr["aim_support"].split(",")))) + 0.5
        b = at(*a)
        dr.line([(b[0] - 7, b[1] - 7), (b[0] + 7, b[1] + 7)], fill=(255, 255, 255), width=2)
        dr.line([(b[0] - 7, b[1] + 7), (b[0] + 7, b[1] - 7)], fill=(255, 255, 255), width=2)
    return im


def sheet(tiles):
    f, fb, ft = g8.font(14), g8.font(15, True), g8.font(24, True)
    tw, th = (VIEW[2] - VIEW[0]) * S, (VIEW[3] - VIEW[1]) * S
    cw, ch = tw + 12, th + 96
    W, H = 170 + 8 * cw, 90 + len(CASES) * ch + 190
    out = Image.new("RGB", (W, H), (16, 16, 18))
    dr = ImageDraw.Draw(out)
    dr.text((8, 6), "Опора второй руки, drawRoutine0: кисть, область цевья пяти конструкций и вектор переноса в координатах кадра юнита",
            font=ft, fill=(255, 255, 255))
    dr.text((8, 40), "W-059 автомат, W-071 винтовка, W-015 дробовик, W-018 пулемёт, W-007 пусковая; классика GOV_1, рост 22, без HD",
            font=fb, fill=(230, 220, 160))
    for d in range(8):
        dr.text((170 + d * cw + 4, 66), "взгляд d%d" % d, font=fb, fill=(200, 200, 255))
    for ci, (case, arm) in enumerate(CASES):
        y = 88 + ci * ch
        dr.text((6, y + th // 2 - 20), "%s\nопора: %s" % (case, "левая" if arm == "la" else "правая"), font=fb,
                fill=(255, 220, 120))
        for d in range(8):
            t = tiles[case, d]
            cr = t[-1]
            x = 170 + d * cw
            out.paste(tile(t), (x, y))
            lines = ["кадр руки %d, кожа %d (видна %d)" % (cr["arm_frame"], cr["skin"], cr["skin_visible"]),
                     "центр -> среднее центров %s" % cr.get("old_move_centre_to_mean_px", "-"),
                     "кожа -> область цевья %s" % cr.get("skin_to_consensus_px", "-")]
            if "shift_nearest_all_weapons" in cr:
                lines.append("сдвиг на все %d: %s (%s), вариантов %d" % (
                    cr["weapons_with_forend"], cr["shift_nearest_all_weapons"], cr["shift_nearest_all_weapons_px"],
                    cr["shift_area_all_weapons"]))
            elif "shift_max_weapons" in cr:
                lines.append("одним сдвигом не больше %d из %d: %s" % (cr["shift_max_weapons"],
                                                                     cr["weapons_with_forend"],
                                                                     cr["shift_for_max_weapons"]))
            dr.text((x, y + th + 4), "\n".join(lines), font=f, fill=(210, 210, 210), spacing=2)
    ly = 88 + len(CASES) * ch + 6
    leg = ["Серое - тело и руки без оружия. Сиреневые точки - пиксели рисунка оружия пяти конструкций. Жёлтое - цевьё по разметке (sure/med): ярче - у большего",
           "числа конструкций; оранжевая рамка - цевьё у большинства (область цевья). Зелёная рамка - вся кожа кадра опорной руки (до перекрытия), заливка - видимая после сборки.",
           "Белая точка - центр кожи. Сиреневая линия - старая мера «перенос»: центр кожи -> среднее центров цевья (одна точка, которой может не быть ни на одном рисунке).",
           "Голубая линия и голубые точки - область переноса: куда можно сдвинуть центр кисти целиком, чтобы кожа коснулась (до 1.5 пикс) цевья КАЖДОЙ конструкции;",
           "линия - ближайший такой сдвиг. Если общего сдвига нет - линия к сдвигу, который берёт больше всего конструкций. Белый крест - прежняя точка aim_support.",
           "Старая мера «мимо» (positions.tsv) - от видимой кожи до ближайшего пикселя оружия ЛЮБОЙ части; её столбец в support_area_r0.tsv рядом с новыми."]
    dr.text((8, ly), "\n".join(leg), font=f, fill=(200, 200, 200), spacing=3)
    return out


if __name__ == "__main__":
    main()
