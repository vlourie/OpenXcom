"""Задания малого пилота хвата (указание специалиста 06.10): кадры HANDOB handSprite+2 и handSprite+4.

Генерации здесь нет. На каждый кадр - что сохранить и где у него кисти:
  - образец конструкции и материалов: BIGOBS ствола и его боеприпасы (ammo_cards/ammo.tsv);
  - вид, хват, опора и дуло - сам кадр HANDOB: рамка рисунка, дуло, зоны основной и опорной кисти (ручная разметка
    ниже, в координатах кадра 32x40 и x4 - формат art/units/grip-contract/pilot/zones_draft.json);
  - где кадр стоит в бою: виды хвата drawRoutine0 (стойка и прицел, правая и левая рука), offX/offY, порядок слоёв,
    кадры рук; классические кисти GOV_1 в координатах кадра предмета - до перекрытия и видимые после сборки;
    сколько зоны хвата видно после сборки (её не закрыл поздний слой).
Зона - область контакта (прямоугольник по пикселям рисунка), не точка. Неустановленная деталь - не место хвата.

  py -3.13 tools/hdart/grip_pilot_tasks.py
  -> art/items/weapons100-v1/grip_pilot/: tasks.json, zones.json, task_<W>_<кадр>.png, sheet.png
"""
import csv
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grip_check8 as g8  # noqa: E402
import grip_engine_check as gec  # noqa: E402
import grip_matrix as gm  # noqa: E402

ROOT, ENC, M = g8.ROOT, g8.ENC, g8.M
OUT = "art/items/weapons100-v1/grip_pilot"
BIGOBS = "census/items/export/exp_piratez/BIGOBS.PCK.png"
K = 4            # масштаб HD-кадра
TOL = 0.03       # допуск размеров и дула

# Ручная разметка кадров +2 и +4 (06.10), координаты кадра 32x40 включительно, [x0, y0, x1, y1, уверенность].
# W-071 и W-018 - из grip_check8/parts_manual.json; W-013 и W-014 размечены здесь по сеткам пикселей.
PILOT = {
    "W-071": {"type": "STR_OLD_SNIPER_RIFLE", "name": "Старина Снайперка", "hs": 3680, "bigobs": 4432,
              "main_on": "шейка приклада", "support_on": "цевьё", "status": "пилот",
              "frames": {
                  2: {"muzzle": [25, 14, "sure"], "main": [15, 19, 17, 20, "low"], "support": [18, 16, 22, 18, "med"],
                      "parts": {"приклад": [11, 20, 14, 23, "sure"], "прицел": [16, 15, 23, 16, "med"]}},
                  4: {"muzzle": [22, 20, "sure"], "main": [10, 16, 12, 17, "low"], "support": [15, 17, 19, 19, "med"],
                      "parts": {"приклад": [6, 14, 8, 16, "sure"], "прицел": [13, 14, 17, 16, "med"]}}}},
    "W-018": {"type": "STR_SAW", "name": "Автоган", "hs": 1784, "bigobs": 1341,
              "main_on": "пистолетная рукоять", "support_on": "цевьё (кожух)", "status": "пилот",
              "frames": {
                  2: {"muzzle": [28, 12, "unsure"], "main": [15, 19, 17, 20, "low"], "support": [21, 13, 26, 16, "med"],
                      "parts": {"короб и лента": [19, 19, 22, 22, "med"], "приклад": [8, 19, 13, 22, "med"]},
                      "unidentified": [[23, 16, 26, 17, "low"]]},
                  4: {"muzzle": [25, 23, "unsure"], "main": [10, 18, 12, 19, "low"], "support": [18, 19, 23, 22, "low"],
                      "parts": {"короб и лента": [11, 20, 15, 23, "med"], "приклад": [6, 12, 10, 16, "med"]},
                      "unidentified": [[17, 21, 19, 22, "low"]]}},
              "note": "выступ на кожухе (BIGOBS 1341, лист art/units/grip-contract/pilot/saw_protrusion.png): рукоять или "
                      "сошка - не установлено. Деталь сохранить, назначение не выдумывать, местом хвата не назначать. "
                      "HD-картинку инвентаря pack/BIGOBS.PCK/1341 эталоном конструкции не брать - выступ там потерян. "
                      "Пиксели выступа в HANDOB - кандидат по положению, не подтверждены."},
    "W-013": {"type": "STR_MP40", "name": "Мессер (MP40)", "hs": 2472, "bigobs": 1683,
              "main_on": "пистолетная рукоять", "support_on": "горловина магазина",
              "status": "исключён из пилота (Vitali 06.10: третий ствол - Томпсон)",
              "frames": {
                  2: {"muzzle": [23, 15, "sure"], "main": [14, 19, 15, 20, "med"], "support": [19, 18, 20, 19, "med"],
                      "parts": {"магазин": [19, 18, 20, 21, "sure"], "ствол": [20, 15, 23, 16, "med"]}},
                  4: {"muzzle": [16, 18, "unsure"], "main": [9, 16, 11, 17, "low"], "support": [12, 18, 13, 19, "med"],
                      "parts": {"магазин": [12, 19, 13, 22, "sure"], "ствол": [14, 17, 16, 19, "med"]}}},
              "note": "кадр +4: дуло справа внизу - по точке вспышки и по аналогии с W-071 +4; рукоять отдельно не "
                      "нарисована (сливается с коробом), её зона - догадка (low)."},
    "W-014": {"type": "STR_TOMMYGUN", "name": "Томми (Томпсон)", "hs": 1640, "bigobs": 1279,
              "main_on": "пистолетная рукоять", "support_on": "передняя рукоять или цевьё - не установлено",
              "status": "пилот",
              "frames": {
                  2: {"muzzle": [25, 14, "sure"], "main": [15, 20, 17, 21, "low"], "support": [18, 21, 19, 21, "low"],
                      "parts": {"приклад": [11, 20, 14, 23, "sure"], "барабан?": [18, 19, 20, 20, "low"]},
                      "unidentified": [[18, 21, 19, 21, "low"]]},
                  4: {"muzzle": [22, 20, "sure"], "main": [10, 16, 12, 17, "low"], "support": [14, 20, 16, 21, "low"],
                      "parts": {"приклад": [6, 14, 8, 16, "sure"], "барабан?": [14, 18, 16, 19, "low"]},
                      "unidentified": [[14, 20, 16, 21, "low"]]}},
              "note": "снизу под коробом - передняя рукоять или барабан (Tommy Drum, BIGOBS 1280): по пикселям не "
                      "установить; опора - догадка."},
}
CASES = ("TWO_STAND", "TWO_AIM", "LEFT_TWO_STAND", "LEFT_TWO_AIM")
S = 8            # масштаб листа
VIEW = g8.VIEW


def bigobs_loader():
    sh = Image.open(BIGOBS)
    pal = np.asarray(sh.getpalette()[:768], np.uint8).reshape(-1, 3)
    idx = np.asarray(sh)

    def frame(n):
        r, c = divmod(n, 16)
        return idx[r * 48:(r + 1) * 48, c * 32:(c + 1) * 32], pal
    return frame


def box_pts(idx, b):
    m = np.zeros(idx.shape, bool)
    m[b[1]:b[3] + 1, b[0]:b[2] + 1] = True
    return g8.pts(m & (idx > 0))


def x4(b):
    return [b[0] * K, b[1] * K, b[2] * K + K - 1, b[3] * K + K - 1]


def uses_of(hs, k):
    """Где кадр hs+k рисуется в бою: (вид хвата, взгляд d)."""
    out = []
    for case in CASES:
        for d in range(8):
            hob = [l for l in gec.ctx_layers(hs, case, d) if l[1] == "hob"]
            if hob and hob[0][2] == hs + k:
                out.append((case, d))
    return out


def use_info(spec, k, fr, case, d):
    hs = spec["hs"]
    layers = gec.ctx_layers(hs, case, d)
    rgb, who = gec.render(layers)
    order = [n for n, *_ in layers]
    iname, _, f, ox, oy = [l for l in layers if l[1] == "hob"][0]
    idx = gm.hob(f)
    left = case.startswith("LEFT")
    roles = {"main": "la" if left else "ra", "support": "ra" if left else "la"}
    r = {"case": case, "dir": d, "offX": ox, "offY": oy, "layers": " ".join(order),
         "arm_frames": {n: a for n, s, a, _, _ in layers if n in ("la", "ra")}}
    hands = {}
    for role, arm in roles.items():
        afr = r["arm_frames"][arm]
        sk = np.isin(gm.gov(afr), gm.SKIN)
        allp = g8.pts(sk)                                     # координаты юнита
        ys, xs = np.nonzero(sk)
        vis = g8.pts(np.zeros_like(sk)) if not len(ys) else allp[who[ys + M, xs + M] == arm]
        zone = fr[role]
        zp = box_pts(idx, zone) + (ox, oy)                     # зона в координатах юнита
        h = {"arm": arm, "arm_frame": afr, "skin": len(allp), "skin_visible": len(vis),
             "skin_in_item_frame": [[int(x - ox), int(y - oy)] for x, y in allp],
             "skin_visible_in_item_frame": [[int(x - ox), int(y - oy)] for x, y in vis],
             "zone_px": len(zp)}
        if len(zp):
            zy, zx = (zp[:, 1] + M).astype(int), (zp[:, 0] + M).astype(int)
            h["zone_visible_share"] = round(float((who[zy, zx] == iname).mean()), 2)
            if len(allp):
                h["dist_geom"] = round(g8.dmin(allp, zp), 1)
            if len(vis):
                h["dist_visible"] = round(g8.dmin(vis, zp), 1)
        hands[role] = h
    r["hands"] = hands
    return r, rgb, who, (ox, oy)


def tile(rgb, who, fr, off, hands, idx, marked, layer_all=True):
    x0, y0, x1, y1 = VIEW
    sub = rgb.copy()
    sub[who == ""] = (86, 92, 88)
    im = Image.fromarray(sub[y0 + M:y1 + M, x0 + M:x1 + M]).resize(((x1 - x0) * S, (y1 - y0) * S), Image.NEAREST)
    if not marked:
        return im
    dr = ImageDraw.Draw(im)
    ox, oy = off

    def at(x, y):
        return (x - x0) * S, (y - y0) * S
    zones(dr, fr, lambda x, y: at(x + ox, y + oy))
    if hands:
        for role, colr in (("main", (40, 120, 255)), ("support", (40, 255, 120))):
            h = hands[role]
            vis = {tuple(v) for v in h["skin_visible_in_item_frame"]}
            for x, y in h["skin_in_item_frame"]:
                a = at(x + ox, y + oy)
                if (x, y) in vis:
                    dr.rectangle([a, (a[0] + S - 1, a[1] + S - 1)], outline=colr, width=2)
                else:
                    dr.rectangle([(a[0] + 2, a[1] + 2), (a[0] + S - 3, a[1] + S - 3)], outline=colr, width=1)
    return im


def zones(dr, fr, at):
    def rect(b, colr, dash):
        a, c = at(b[0], b[1]), at(b[2] + 1, b[3] + 1)
        if not dash:
            dr.rectangle([a, c], outline=colr, width=3)
            return
        for i in range(int(a[0]), int(c[0]), 8):
            dr.line([(i, a[1]), (min(i + 4, c[0]), a[1])], fill=colr, width=3)
            dr.line([(i, c[1]), (min(i + 4, c[0]), c[1])], fill=colr, width=3)
        for i in range(int(a[1]), int(c[1]), 8):
            dr.line([(a[0], i), (a[0], min(i + 4, c[1]))], fill=colr, width=3)
            dr.line([(c[0], i), (c[0], min(i + 4, c[1]))], fill=colr, width=3)
    for b in fr.get("unidentified", []):
        rect(b, (255, 60, 255), True)
    rect(fr["main"], (60, 230, 255), fr["main"][4] == "low")
    rect(fr["support"], (255, 230, 60), fr["support"][4] == "low")
    mx, my, ms = fr["muzzle"]
    cx, cy = at(mx + 0.5, my + 0.5)
    if ms == "sure":
        dr.line([(cx - 10, cy), (cx + 10, cy)], fill=(255, 40, 40), width=3)
        dr.line([(cx, cy - 10), (cx, cy + 10)], fill=(255, 40, 40), width=3)
    else:
        dr.ellipse([(cx - 9, cy - 9), (cx + 9, cy + 9)], outline=(255, 40, 40), width=3)


def frame_alone(idx, fr, marked):
    pal = gm.hpal
    rgb = np.zeros(idx.shape + (3,), np.uint8)
    rgb[:] = (86, 92, 88)
    rgb[idx > 0] = pal[idx[idx > 0]]
    im = Image.fromarray(rgb).resize((32 * S, 40 * S), Image.NEAREST)
    if marked:
        zones(ImageDraw.Draw(im), fr, lambda x, y: (x * S, y * S))
    return im


def bo_img(bo, n, sc=6):
    idx, pal = bo(n)
    rgb = np.zeros(idx.shape + (3,), np.uint8)
    rgb[:] = (86, 92, 88)
    rgb[idx > 0] = pal[idx[idx > 0]]
    return Image.fromarray(rgb).resize((32 * sc, 48 * sc), Image.NEAREST)


def card(w, spec, k, task, bo, ammo, renders):
    f, fb, ft = g8.font(15), g8.font(16, True), g8.font(24, True)
    fr = spec["frames"][k]
    idx = gm.hob(spec["hs"] + k)
    tw, th = (VIEW[2] - VIEW[0]) * S, (VIEW[3] - VIEW[1]) * S
    right = [(c, d) for c, d in task["uses_list"] if not c.startswith("LEFT")]
    W = max(60 + 2 * (32 * S) + 40 + (1 + len(ammo)) * (32 * 6 + 20), 20 + len(right) * (2 * tw + 30))
    H = 70 + max(40 * S, 48 * 6) + 90 + th + 200 + 150
    out = Image.new("RGB", (W, H), (16, 16, 18))
    dr = ImageDraw.Draw(out)
    dr.text((10, 6), "%s %s - %s, кадр HANDOB %d (handSprite+%d) - %s" % (w, spec["type"], spec["name"],
                                                                           spec["hs"] + k, k, spec["status"]),
            font=ft, fill=(255, 255, 255))
    dr.text((10, 38), "основная кисть: %s; опорная: %s; сохранить рамку рисунка %s (x4 %s) и дуло %s, допуск %d%%" % (
        spec["main_on"], spec["support_on"], task["bbox"], task["bbox_x4"], task["muzzle_x4"], TOL * 100),
        font=f, fill=(230, 220, 160))
    y = 70
    out.paste(frame_alone(idx, fr, False), (10, y))
    out.paste(frame_alone(idx, fr, True), (20 + 32 * S, y))
    dr.text((10, y + 40 * S + 4), "кадр в руке x%d: без отметок | с отметками" % S, font=fb, fill=(200, 200, 255))
    x = 60 + 2 * 32 * S
    out.paste(bo_img(bo, spec["bigobs"]), (x, y))
    dr.text((x, y + 48 * 6 + 4), "BIGOBS %d (ствол)" % spec["bigobs"], font=f, fill=(210, 210, 210))
    for i, a in enumerate(ammo):
        xx = x + (i + 1) * (32 * 6 + 20)
        out.paste(bo_img(bo, int(a["frame"])), (xx, y))
        lab = [a["ru"], "BIGOBS %s" % a["frame"]] + ([a["same_frame_as"]] if a["same_frame_as"] else [])
        dr.text((xx, y + 48 * 6 + 4), "\n".join(lab), font=g8.font(13), fill=(210, 210, 210))
    y += max(40 * S, 48 * 6) + 70
    for i, (c, d) in enumerate(right):
        u = [u for u in task["uses"] if u["case"] == c and u["dir"] == d][0]
        rgb, who, off = renders[c, d]
        xx = 10 + i * (2 * tw + 30)
        out.paste(tile(rgb, who, fr, off, None, idx, False), (xx, y))
        out.paste(tile(rgb, who, fr, off, u["hands"], idx, True), (xx + tw + 8, y))
        dr.text((xx, y - 22), "%s взгляд d%d (%s): offX %d, offY %d" % (c, d, "прицел" if c.endswith("AIM") else "стойка",
                                                                     u["offX"], u["offY"]), font=fb, fill=(255, 220, 120))
        lines = ["слои: %s; руки %s" % (u["layers"], ", ".join("%s %d" % kv for kv in u["arm_frames"].items()))]
        for role, nm in (("main", "основная"), ("support", "опорная")):
            h = u["hands"][role]
            lines.append("%s (%s, кадр %d): до зоны %s пикс до перекрытия, %s видимой кожей; зоны видно %s" % (
                nm, "левая" if h["arm"] == "la" else "правая", h["arm_frame"], h.get("dist_geom", "-"),
                h.get("dist_visible", "кожа закрыта"), h.get("zone_visible_share", "-")))
        dr.text((xx, y + th + 6), "\n".join(lines), font=f, fill=(210, 210, 210), spacing=3)
    y += th + 90
    leg = ["Голубая рамка - зона основной кисти, жёлтая - опорной (пунктир - разметка неуверенна, low); розовый пунктир - деталь не установлена,",
           "место хвата не назначать. Красный крест - дуло, красный круг - дуло не подтверждено. В сборке: синие клетки - кожа основной кисти классики GOV_1,",
           "зелёные - опорной; толстая рамка - видна после сборки, тонкий квадрат - закрыта поздним слоем (геометрия до перекрытия).",
           "Классика: кадры GOV_1 и HANDOB, эмуляция drawRoutine0 (рост 22). Кисти классики показаны как есть - оружие под них не подгоняется."]
    if spec.get("note"):
        line = ""
        for word in ("Заметка: " + spec["note"]).split():
            if dr.textlength(line + " " + word, font=f) > W - 30:
                leg.append(line)
                line = word
            else:
                line = (line + " " + word).strip()
        leg.append(line)
    dr.text((10, y), "\n".join(leg), font=f, fill=(200, 200, 200), spacing=3)
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.chdir(ROOT)
    os.makedirs(OUT, exist_ok=True)
    bo = bigobs_loader()
    ammo = {}
    for r in csv.DictReader(open("art/items/weapons100-v1/ammo_cards/ammo.tsv", encoding=ENC), delimiter="\t",
                            quoting=csv.QUOTE_NONE):
        ammo.setdefault(r["master"], []).append(r)
    tips = {}
    for r in csv.DictReader(open("art/items/weapons100-v1/handob_cards/tips.tsv", encoding=ENC), delimiter="\t"):
        if r["tipX"] and r["frame"]:
            tips[r["master"], int(r["frame"])] = (int(r["tipX"]), int(r["tipY"]), int(r["look_d"]))
    tasks, zj, cards = [], {"_note": "Зоны кистей пилота хвата (ветка предметов, 06.10): кадры HANDOB handSprite+2 и +4, "
                                     "прямоугольники [x0,y0,x1,y1] в координатах HD-кадра x4 (128x160) до сдвига offX/offY. "
                                     "main - основная кисть, support - опорная, unidentified - деталь не установлена, "
                                     "местом хвата не назначать. conf: sure/med/low. Разметка по классике, не по HD."}, []
    for w, spec in PILOT.items():
        if spec["status"].startswith("исключ"):
            print(w, spec["status"])
            continue
        zj[spec["type"]] = {}
        for k in (2, 4):
            fr = spec["frames"][k]
            f = spec["hs"] + k
            idx = gm.hob(f)
            ys, xs = np.nonzero(idx)
            bb = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
            tw, th = (bb[2] - bb[0] + 1) * K, (bb[3] - bb[1] + 1) * K
            us = uses_of(spec["hs"], k)
            task = {"master": w, "type": spec["type"], "name": spec["name"], "status": spec["status"],
                    "frame": f, "k": k, "handSprite": spec["hs"], "bigobs": spec["bigobs"],
                    "ammo": [{"type": a["ammo"], "ru": a["ru"], "bigobs": int(a["frame"]),
                              "recolor_of": a["same_frame_as"]} for a in ammo.get(w, [])],
                    "bbox": bb, "bbox_x4": x4(bb), "size_x4": [tw, th],
                    "size_tolerance_px_x4": [max(1, round(tw * TOL)), max(1, round(th * TOL))],
                    "muzzle": fr["muzzle"], "muzzle_x4": [fr["muzzle"][0] * K + K // 2, fr["muzzle"][1] * K + K // 2,
                                                          fr["muzzle"][2]],
                    "muzzle_tolerance_px_x4": max(1, round(max(tw, th) * TOL)),
                    "zones": {"main": fr["main"], "support": fr["support"], "unidentified": fr.get("unidentified", []),
                              "parts": fr["parts"]},
                    "main_on": spec["main_on"], "support_on": spec["support_on"], "note": spec.get("note", ""),
                    "uses_list": us, "uses": []}
            tp = tips.get((w, f))
            if tp:
                task["notetip_aim"] = {"look_d": tp[2], "tip": [tp[0], tp[1]]}
            renders = {}
            for c, d in us:
                u, rgb, who, off = use_info(spec, k, fr, c, d)
                task["uses"].append(u)
                renders[c, d] = (rgb, who, off)
            tasks.append(task)
            zj[spec["type"]][str(f)] = {"grip": [x4(fr["main"])], "support": [x4(fr["support"])],
                                        "unidentified": [x4(b) for b in fr.get("unidentified", [])],
                                        "muzzle": task["muzzle_x4"][:2], "muzzle_conf": fr["muzzle"][2],
                                        "conf": {"grip": fr["main"][4], "support": fr["support"][4]},
                                        "status": spec["status"]}
            im = card(w, spec, k, task, bo, ammo.get(w, []), renders)
            p = os.path.join(OUT, "task_%s_%d.png" % (w, f))
            im.save(p)
            cards.append(p)
            print(w, f, "видов хвата", len(us), us)
    for t in tasks:
        t.pop("uses_list")
    json.dump(tasks, open(os.path.join(OUT, "tasks.json"), "w", encoding=ENC), ensure_ascii=False, indent=1)
    json.dump(zj, open(os.path.join(OUT, "zones.json"), "w", encoding=ENC), ensure_ascii=False, indent=1)
    print("заданий", len(tasks))


if __name__ == "__main__":
    main()
