"""Проверка общей схемы хвата на восьми конструкциях по ручной разметке частей (указание специалиста 06.10).

Вход - art/items/weapons100-v1/grip_check8/parts_manual.json: на каждый из восьми кадров HANDOB дуло (sure|unsure)
и части (рукоять, цевьё, магазин, приклад, рукоять клинка, плечо лука...) прямоугольниками с уверенностью.
Сборка - независимая эмуляция drawRoutine0 (grip_engine_check.engine), агент GOV_1, рост 22.
На каждую позицию (вид хвата x направление):
  - какая часть у каждой кисти: видимая кожа кадра руки (не закрытая поздним слоем) против пикселей части,
    касание - не дальше 1.5 пикс базы; кто сверху в месте касания (пальцы поверх оружия или оружие поверх кисти);
  - статус: проверено (главная кисть на рукояти, опорная на цевье, по разметке sure/med), несовместимо (кисть мимо
    оружия дальше 2 пикс или на чужой части при уверенной разметке), ещё не проверено (кисть закрыта, часть
    не размечена или разметка low);
  - дуло против точки вспышки noteTip (копия HdFx::noteTip по взгляду d) - отдельно; неуверенное дуло не подтверждено.
Касание - фильтр, а не доказательство хвата; HD-кадров тут нет, проверяется классика.

  py -3.13 tools/hdart/grip_check8.py
  -> art/items/weapons100-v1/grip_check8/: positions.tsv, summary.tsv, sheet_<W>.png, status.png
"""
import csv
import json
import os
import sys
from collections import Counter

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grip_engine_check as gec  # noqa: E402
import grip_matrix as gm  # noqa: E402
import weapon_handob_cards as whc  # noqa: E402

ROOT = gec.ROOT
ENC = "utf-8-sig"
OUT = "art/items/weapons100-v1/grip_check8"
M = gec.M
TOUCH = 1.5      # касание кисти и части, пикс базы
MISS = 2.0       # дальше - кисть мимо оружия
FAR = 3.0        # на чужой части при уверенной разметке, если до своей дальше
S = 4            # масштаб листа
VIEW = (-8, -8, 40, 44)   # окно листа в координатах юнита
NAMES = {"grip": "рукоять", "forend": "цевьё", "mag": "магазин", "stock": "приклад", "scope": "прицел",
         "box": "короб", "bipod": "сошки", "barrel": "ствол", "cylinder": "барабан", "riser": "плечо лука",
         "string": "тетива", "handle": "рукоять клинка", "blade": "клинок"}
STATUS = {"ok": "проверено", "bad": "несовместимо", "unk": "ещё не проверено"}
COL = {"ok": (90, 220, 110), "bad": (255, 90, 80), "unk": (190, 190, 190)}


def font(n, bold=False):
    return ImageFont.truetype("C:/Windows/Fonts/arial%s.ttf" % ("bd" if bold else ""), n)


def pts(mask):
    ys, xs = np.nonzero(mask)
    return np.stack([xs, ys], 1).astype(float)


def dmin(a, b):
    if not len(a) or not len(b):
        return None
    return float(np.sqrt(((a[:, None, :] - b[None, :, :]) ** 2).sum(-1)).min())


def cases_of(two):
    return ("TWO_STAND", "TWO_AIM", "LEFT_TWO_STAND", "LEFT_TWO_AIM") if two else ("ONE", "LEFT_ONE")


def position(w, spec, case, d):
    hs = spec["hs"]
    layers = gec.ctx_layers(hs, case, d)
    rgb, who = gec.render(layers)
    order = [n for n, *_ in layers]
    hob = [l for l in layers if l[1] == "hob"][0]
    iname, _, fr, ox, oy = hob
    k = fr - hs
    lab = spec["frames"][str(k)]
    idx = gm.hob(fr)
    wpts = pts(idx > 0) + (ox + M, oy + M)
    parts = {}
    for p, v in lab.items():
        if p == "muzzle":
            continue
        x0, y0, x1, y1, conf = v
        m = np.zeros(idx.shape, bool)
        m[y0:y1 + 1, x0:x1 + 1] = True
        pp = pts(m & (idx > 0)) + (ox + M, oy + M)
        parts[p] = (pp, conf, (x0 + ox + M, y0 + oy + M, x1 + ox + M, y1 + oy + M))
    arms = {}
    for n, src, afr, _, _ in layers:
        if n in ("la", "ra"):
            sk = np.isin(gm.gov(afr), gm.SKIN)
            allp = pts(sk) + (M, M)
            vis = np.zeros(who.shape, bool)
            ys, xs = np.nonzero(sk)
            vis[ys + M, xs + M] = who[ys + M, xs + M] == n
            arms[n] = (afr, allp, pts(vis), order.index(n) > order.index(iname))

    def hand(n, expect, geom=False):
        """geom - геометрия контакта до перекрытия: вся кожа кадра руки, поздние слои не закрывают;
        иначе - видимый результат сборки: только кожа, которую не закрыл поздний слой."""
        afr, allp, vis, over = arms[n]
        if geom:
            vis = allp
        r = {"arm": afr, "skin": len(allp), "skin_visible": len(vis), "on": "", "dist_weapon": "", "dist_expect": "",
             "top": ""}
        if not len(vis):
            return "unk", "кожи в кадре руки нет" if geom else "кисть закрыта", r
        dw = dmin(vis, wpts)
        r["dist_weapon"] = "%.1f" % dw
        touched = [p for p, (pp, c, _) in parts.items() if (dmin(vis, pp) or 99) <= TOUCH]
        r["on"] = ",".join(touched)
        if dw <= TOUCH and not geom:
            r["top"] = "пальцы поверх оружия" if over else "оружие поверх кисти"
        if expect == "string":      # тянущая кисть не обязана касаться рисунка лука
            return "unk", "тетива не нарисована", r
        if dw > MISS:
            return "bad", "мимо оружия, %.1f пикс" % dw, r
        if expect not in parts or not len(parts[expect][0]):
            return "unk", "%s не размечено" % NAMES[expect], r
        pp, conf, _ = parts[expect]
        de = dmin(vis, pp)
        r["dist_expect"] = "%.1f" % de
        if de <= TOUCH:
            if conf == "low":
                return "unk", "на %s? разметка неуверенна" % NAMES[expect], r
            return "ok", "держит %s" % NAMES[expect], r
        others = [p for p in touched if p != expect]
        if others and conf != "low" and de > FAR:
            return "bad", "на %s, до %s %.1f" % (NAMES[others[0]], NAMES[expect], de), r
        if conf == "low":
            return "unk", "до %s %.1f, разметка неуверенна" % (NAMES[expect], de), r
        if de > FAR:
            return "bad", "до %s %.1f пикс" % (NAMES[expect], de), r
        return "unk", "рядом с %s, %.1f" % (NAMES[expect], de), r

    left = case.startswith("LEFT")
    hold, other = ("la", "ra") if left else ("ra", "la")

    def judge(geom):
        res = {}
        note = ""
        if spec["two"]:
            a = (hand(hold, spec["main"], geom), hand(other, spec["support"], geom))
            if left and spec["main"] != spec["support"]:
                b = (hand(other, spec["main"], geom), hand(hold, spec["support"], geom))
                if [x[0] for x in b].count("ok") > [x[0] for x in a].count("ok"):
                    a, note = b, "рукоять у правой кисти"
            res["main"], res["support"] = a
        else:
            res["main"] = hand(hold, spec["main"], geom)
        sts = [v[0] for v in res.values()]
        return res, note, "bad" if "bad" in sts else "ok" if all(s == "ok" for s in sts) else "unk"

    res, note, st = judge(False)          # видимый результат после сборки
    gres, gnote, gst = judge(True)        # геометрия контакта до перекрытия
    hidden = any(v[1] == "кисть закрыта" for v in res.values())
    # дуло и точка вспышки
    mz = lab.get("muzzle")
    tip = whc.note_tip(idx, d)
    # вспышка рисуется при выстреле: у двуручного - в прицеле, у одноручного поза одна
    mrow = {"muzzle": "", "muzzle_sure": "", "notetip": "", "muzzle_vs_notetip": "",
            "shot_pose": "да" if case.endswith("AIM") or not spec["two"] else "нет"}
    if tip:
        mrow["notetip"] = "%d,%d" % (tip[0], tip[1])
    if mz:
        mrow["muzzle"] = "%d,%d" % (mz[0], mz[1])
        mrow["muzzle_sure"] = "да" if mz[2] == "sure" else "нет"
        if tip:
            mrow["muzzle_vs_notetip"] = "%.1f" % np.hypot(tip[0] - (mz[0] + 0.5), tip[1] - (mz[1] + 0.5))
    return {"rgb": rgb, "who": who, "status": st, "res": res, "note": note, "gstatus": gst, "gres": gres,
            "gnote": gnote, "hidden": hidden, "parts": parts, "arms": arms, "hold": hold,
            "frame": fr, "k": k, "ox": ox, "oy": oy, "mz": mz, "tip": tip, "m": mrow, "order": " ".join(order)}


def tile(p, marked):
    x0, y0, x1, y1 = VIEW
    rgb = p["rgb"].copy()
    bg = np.array((86, 92, 88), np.uint8)
    rgb[p["who"] == ""] = bg
    sub = rgb[y0 + M:y1 + M, x0 + M:x1 + M]
    im = Image.fromarray(sub).resize(((x1 - x0) * S, (y1 - y0) * S), Image.NEAREST)
    if not marked:
        return im
    dr = ImageDraw.Draw(im)

    def at(x, y):
        return (x - M - x0) * S, (y - M - y0) * S

    for pn, colr in (("grip", (60, 230, 255)), ("handle", (60, 230, 255)), ("riser", (60, 230, 255)),
                     ("forend", (255, 230, 60))):
        if pn in p["parts"]:
            bx0, by0, bx1, by1 = p["parts"][pn][2]
            a, b = at(bx0, by0), at(bx1 + 1, by1 + 1)
            dash = p["parts"][pn][1] == "low"
            if dash:
                for i in range(int(a[0]), int(b[0]), 6):
                    dr.line([(i, a[1]), (min(i + 3, b[0]), a[1])], fill=colr, width=2)
                    dr.line([(i, b[1]), (min(i + 3, b[0]), b[1])], fill=colr, width=2)
                for i in range(int(a[1]), int(b[1]), 6):
                    dr.line([(a[0], i), (a[0], min(i + 3, b[1]))], fill=colr, width=2)
                    dr.line([(b[0], i), (b[0], min(i + 3, b[1]))], fill=colr, width=2)
            else:
                dr.rectangle([a, b], outline=colr, width=2)
    for n, colr in (("ra", (40, 120, 255)), ("la", (40, 255, 120))):
        if n in p["arms"]:
            for x, y in p["arms"][n][2]:
                a = at(x, y)
                dr.rectangle([a, (a[0] + S - 1, a[1] + S - 1)], outline=colr, width=1)
    if p["mz"]:
        mx, my = p["mz"][0] + p["ox"] + M + 0.5, p["mz"][1] + p["oy"] + M + 0.5
        cx, cy = at(mx, my)
        if p["mz"][2] == "sure":
            dr.line([(cx - 9, cy), (cx + 9, cy)], fill=(255, 40, 40), width=3)
            dr.line([(cx, cy - 9), (cx, cy + 9)], fill=(255, 40, 40), width=3)
        else:
            dr.ellipse([(cx - 8, cy - 8), (cx + 8, cy + 8)], outline=(255, 40, 40), width=2)
    if p["tip"]:
        tx, ty = at(p["tip"][0] + p["ox"] + M, p["tip"][1] + p["oy"] + M)
        dr.line([(tx - 7, ty - 7), (tx + 7, ty + 7)], fill=(255, 160, 0), width=2)
        dr.line([(tx - 7, ty + 7), (tx + 7, ty - 7)], fill=(255, 160, 0), width=2)
    return im


def sheet(w, spec, ps):
    f, fb, ft = font(13), font(14, True), font(22, True)
    cases = cases_of(spec["two"])
    tw, th = (VIEW[2] - VIEW[0]) * S, (VIEW[3] - VIEW[1]) * S
    cw, ch = 2 * tw + 14, th + 64
    W, H = 150 + 8 * cw, 70 + len(cases) * ch + 150
    out = Image.new("RGB", (W, H), (16, 16, 18))
    dr = ImageDraw.Draw(out)
    cnt = Counter(p["status"] for p in ps.values())
    dr.text((8, 6), "%s %s (handSprite %d): слева классика без отметок, справа с отметками" % (w, spec["kind"], spec["hs"]),
            font=ft, fill=(255, 255, 255))
    dr.text((8, 38), "проверено %d, несовместимо %d, ещё не проверено %d из %d позиций" % (
        cnt["ok"], cnt["bad"], cnt["unk"], len(ps)), font=fb, fill=(230, 220, 160))
    for d in range(8):
        dr.text((150 + d * cw + 4, 58), "взгляд d%d" % d, font=fb, fill=(200, 200, 255))
    for ci, c in enumerate(cases):
        y = 78 + ci * ch
        dr.text((6, y + th // 2 - 10), c, font=fb, fill=(255, 220, 120))
        for d in range(8):
            p = ps[c, d]
            x = 150 + d * cw
            out.paste(tile(p, False), (x, y))
            out.paste(tile(p, True), (x + tw + 6, y))
            dr.rectangle([(x - 2, y - 2), (x + 2 * tw + 8, y + th + 1)], outline=COL[p["status"]], width=2)
            txt = "%s  k%d" % (STATUS[p["status"]], p["k"])
            dr.text((x, y + th + 3), txt, font=fb, fill=COL[p["status"]])
            lines = []
            for role, (s, why, _) in p["res"].items():
                lines.append(("гл: " if role == "main" else "оп: ") + why)
            if p["note"]:
                lines.append(p["note"])
            if p["m"]["muzzle_vs_notetip"] and p["m"]["shot_pose"] == "да" and spec["kind"] not in ("лук", "двуручный клинок"):
                lines.append("дуло%s - вспышка %s" % ("" if p["m"]["muzzle_sure"] == "да" else "?", p["m"]["muzzle_vs_notetip"]))
            dr.text((x, y + th + 21), "\n".join(lines[:3]), font=f, fill=(210, 210, 210), spacing=1)
    ly = 78 + len(cases) * ch + 6
    leg = ["Отметки справа: синие клетки - видимая кожа правой кисти, зелёные - левой; голубая рамка - рукоять (пунктир - разметка неуверенна),",
           "жёлтая рамка - цевьё; красный крест - дуло по разметке, красный круг - дуло не подтверждено; оранжевый X - точка вспышки noteTip по взгляду d.",
           "гл - кисть руки, держащей оружие (у LEFT_* - левая), оп - другая. Касание до 1.5 пикс базы. Мимо - дальше 2 пикс от любого пикселя оружия.",
           "Классические кадры GOV_1 и HANDOB, сборка - эмуляция drawRoutine0 (порядок слоёв, offX/offY, рост 22). HD-кадров тут нет."]
    dr.text((8, ly), "\n".join(leg), font=f, fill=(200, 200, 200), spacing=3)
    return out


def pose_table(lab, allps):
    """Общая поза кисти на направление: где части восьми конструкций (sure/med) в координатах юнита против
    нынешней кисти классики и общей точки опоры aim_support.tsv. Кисть ставится в часть, оружие не меняется."""
    aims = {int(r["dir"]): r for r in csv.DictReader(open("art/units/grip-contract/aim_support.tsv", encoding=ENC),
                                                      delimiter="\t")}
    out = []
    for case, role, arm, part in (("TWO_AIM", "опора", "la", "forend"), ("TWO_AIM", "хват", "ra", "grip"),
                                  ("TWO_STAND", "опора", "la", "forend"), ("TWO_STAND", "хват", "ra", "grip"),
                                  ("LEFT_TWO_AIM", "рука прицела", "ra", "forend"),
                                  ("LEFT_TWO_AIM", "держащая", "la", "grip")):
        for d in range(8):
            cs, names, hand = [], [], None
            for w, spec in lab.items():
                if w.startswith("_") or not spec["two"] or spec["main"] != "grip":
                    continue
                p = allps[w][case, d]
                if hand is None:
                    al = p["arms"][arm][1]
                    hand = al.mean(0) - M if len(al) else None
                pr = p["parts"].get(part)
                if pr and pr[1] != "low" and len(pr[0]):
                    cs.append(pr[0].mean(0) - M)
                    names.append(w)
            r = {"case": case, "hand": role, "arm_frame": {"la": 240, "ra": 256 if case.endswith("AIM") else 248}[arm] + d,
                 "dir": d, "part": NAMES[part], "n": len(cs), "weapons": ",".join(names)}
            if hand is not None:
                r["hand_now"] = "%.1f,%.1f" % tuple(hand)
            if cs:
                c = np.array(cs)
                mu = c.mean(0)
                r["part_mean"] = "%.1f,%.1f" % tuple(mu)
                r["spread_max"] = "%.1f" % float(np.sqrt(((c - mu) ** 2).sum(1)).max())
                r["within2_of_mean"] = int((np.sqrt(((c - mu) ** 2).sum(1)) <= 2).sum())
                if hand is not None:
                    r["move_hand_px"] = "%.1f" % float(np.hypot(*(mu - hand)))
                if case == "TWO_AIM" and part == "forend":
                    a = np.array((float(aims[d]["aim_support_x"]), float(aims[d]["aim_support_y"])))
                    r["aim_support"] = "%d,%d" % tuple(a)
                    r["aim_support_to_mean"] = "%.1f" % float(np.hypot(*(mu - a)))
            out.append(r)
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.chdir(ROOT)
    lab = json.load(open(os.path.join(OUT, "parts_manual.json"), encoding=ENC))
    allps = {}
    rows, summ = [], []
    tot, gtot, cross = Counter(), Counter(), Counter()
    for w, spec in lab.items():
        if w.startswith("_"):
            continue
        ps = {}
        for c in cases_of(spec["two"]):
            for d in range(8):
                p = position(w, spec, c, d)
                ps[c, d] = p
                r = {"master": w, "kind": spec["kind"], "case": c, "dir": d, "frame": p["frame"], "k": p["k"],
                     "offX": p["ox"], "offY": p["oy"], "status": STATUS[p["status"]],
                     "status_geom": STATUS[p["gstatus"]], "hand_hidden": "да" if p["hidden"] else "",
                     "layers": p["order"]}
                for role, (s, why, h) in p["res"].items():
                    pre = "main_" if role == "main" else "support_"
                    r[pre + "verdict"] = why
                    for kk in ("arm", "skin_visible", "on", "dist_weapon", "dist_expect", "top"):
                        r[pre + kk] = h[kk]
                for role, (s, why, h) in p["gres"].items():
                    pre = "main_geom_" if role == "main" else "support_geom_"
                    r[pre + "verdict"] = why
                    for kk in ("on", "dist_weapon", "dist_expect"):
                        r[pre + kk] = h[kk]
                r["note"] = p["note"]
                r["note_geom"] = p["gnote"]
                r.update(p["m"])
                rows.append(r)
                tot[p["status"]] += 1
                gtot[p["gstatus"]] += 1
                cross[p["status"], p["gstatus"], p["hidden"]] += 1
        allps[w] = ps
        cnt = Counter(p["status"] for p in ps.values())
        why = Counter()
        for p in ps.values():
            for s, t, _ in p["res"].values():
                if s != "ok":
                    why[t.split(",")[0].split(" ")[0] + " " + " ".join(t.split(",")[0].split(" ")[1:2])] += 1
        gcnt = Counter(p["gstatus"] for p in ps.values())
        summ.append({"master": w, "kind": spec["kind"], "positions": len(ps), "проверено": cnt["ok"],
                     "несовместимо": cnt["bad"], "ещё_не_проверено": cnt["unk"],
                     "кисть_закрыта": sum(p["hidden"] for p in ps.values()),
                     "геом_проверено": gcnt["ok"], "геом_несовместимо": gcnt["bad"], "геом_не_проверено": gcnt["unk"],
                     "причины_рук": "; ".join("%s %d" % kv for kv in why.most_common())})
        sheet(w, spec, ps).save(os.path.join(OUT, "sheet_%s.png" % w))
        print(w, spec["kind"], dict(cnt))
    keys = []
    for r in rows:
        keys += [k for k in r if k not in keys]
    pose = pose_table(lab, allps)
    pk = []
    for r in pose:
        pk += [k for k in r if k not in pk]
    for name, data, ks in (("positions", rows, keys), ("summary", summ, list(summ[0])), ("pose_r0", pose, pk)):
        with open(os.path.join(OUT, name + ".tsv"), "w", encoding=ENC, newline="") as f:
            wr = csv.DictWriter(f, ks, delimiter="\t", restval="")
            wr.writeheader()
            wr.writerows(data)
    print("всего (видимое):", {STATUS[k]: v for k, v in tot.items()}, "из", sum(tot.values()))
    print("всего (геометрия до перекрытия):", {STATUS[k]: v for k, v in gtot.items()})
    with open(os.path.join(OUT, "geom_vs_visible.tsv"), "w", encoding=ENC, newline="") as f:
        f.write("видимое\tгеометрия\tкисть_закрыта\tпозиций\n")
        for (a, b, h), v in sorted(cross.items(), key=lambda kv: -kv[1]):
            f.write("%s\t%s\t%s\t%d\n" % (STATUS[a], STATUS[b], "да" if h else "нет", v))


if __name__ == "__main__":
    main()
