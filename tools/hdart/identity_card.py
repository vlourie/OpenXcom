#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""IDENTITY_GATE_V2 (специалист 01.10): карточка опознания с контекстом - CPU, видеокарта не нужна.

PHOTO_STRUCT_ACCEPTANCE_V1 провалилась на опознании: три описания (identity_regression.json) прошли карточку
32x40 у человека и согласие двух ответов модели (verdict agree) и всё равно неверны. Подтверждение по одному
кадру 32x40 != IDENTITY_VERIFIED. Статус IDENTITY_VISUALLY_VERIFIED выдаётся только после такой карточки:

    1. кадр крупно (x8, на тёмном и светлом)
    2. место на карте: до трёх разных блоков - вырез вокруг клетки, РЕНТГЕН и весь блок, клетка в рамке.
       Рентген (окружение притушено, кадр поверх) обязателен, это часть ворот: у C_INT:27 предмет за стеной
       корпуса, и обычный вырез его не показывает. Карточка без рентгена - неполная (card_complete ложь)
    3. соседние кадры того же набора (PCK), кадр в рамке
    4. что стоит рядом на карте (та же клетка и 8 соседних)
    5. запись MCD: кадры анимации, разрушенный вид, второе состояние
    6. семейство и кандидаты «другой бок»
    7. оба ответа модели, нынешнее описание-промпт, факты MCD и рулсетов
    8. тот же кадр в других наборах (побайтные копии - их места идут и в раздел 2) и похожие по форме и яркости
       кадры с их нынешним опознанием: аналог - улика, а не истина (FRNITURE:19 сам на проверке)

Человек: final_identity (по-английски; у куска - чего он кусок) и статус - один из четырёх:
    IDENTITY_VISUALLY_VERIFIED  самостоятельный предмет, опознан - единственный статус, годный в производство
    PART_FRAGMENT_CONFIRMED     кусок большей конструкции (R-153): одиночным предметом не рисуется
    NOT_OBJECT                  не предмет (рельеф, стена, пол, эффект)
    UNSURE                      не ясно - и какого контекста не хватило (не угадывать)
Ворота регрессии (специалист 01.10) - две независимые проверки:
    CONTEXT_GATE         карточки хватило: старые ошибки раскрыты n/n (ни одно старое ложное описание не
                         принято), 0 ложных самостоятельных (кусок назван предметом), 0 UNSURE из-за контекста
    IDENTITY_TRUTH_GATE  независимая смысловая истина установлена и совпала - закрыто k из n, остальные OPEN
Сверка --reference: asset_id, ref_status, identity_ok (yes / no / open), old_rejected (yes / no). open - истина
ещё не установлена, это не ошибка человека; статус человека сам по себе истиной не считается. Необязательный
structural_ok (yes / no / open, пусто - не оценивали) - структурное опознание отдельно от смыслового: что это за
конструкция и из каких частей (C_INT:27 - верхний модуль колонны C_INT_COLUMN, closed), когда назначение ещё
open; ворота истины считаются по смыслу, структура идёт отдельной строкой.
Необязательные truth_identity (эталонное название), relation (DAMAGED_VARIANT_OF MADDECOR:50 и т.п.) и
semantic_ok (yes / no / open / excluded) - точность НАЗВАНИЯ в ответе отдельно от класса (специалист 01.10):
identity_ok yes - истина установлена и ответ верен по классу (предмет / кусок / не предмет), а «ice vending
machine» против эталона «water cooler» - semantic_ok no; excluded - смысл не нужен для маршрутизации и в точность
названий не входит (C_INT:27: структура закрыта, назначение OPEN). Отчёт считает отдельно: точность класса
(предмет / кусок), точность названия, долю UNSURE, долю ложных самостоятельных.

    py -3.13 tools/hdart/identity_card.py make --regression
    py -3.13 tools/hdart/identity_card.py make --assets A:1,B:2 --out <папка>
    py -3.13 tools/hdart/identity_card.py report --out <папка> [--answers <tsv>] [--reference <tsv>]
Страница - <out>/index.html; под art/objects/generation её отдаёт сервер detail-probe (порт 8778).
"""
import argparse
import csv
import html
import json
import os
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
ROOT = os.path.dirname(os.path.dirname(HERE))

from PIL import Image, ImageDraw          # noqa: E402

ENC = "utf-8-sig"
DISC = os.path.join("art", "objects", "discovery")
REGRESSION = os.path.join(DISC, "identity_regression.json")
PROPOSALS = os.path.join(DISC, "proposals.json")
OUT_REG = os.path.join("art", "objects", "generation", "probes", "identity-gate-v2-regression")
PHOTO_JOBS = ["art/objects/generation/probes/photo-struct-accept-v1/jobs.json",
              "art/objects/generation/probes/photo-accept-v1/jobs.json"]
DARK, LIGHT = (24, 20, 18), (225, 225, 225)
PLACES = 3                  # разных блоков на карточке
PCK_SIDE = 8                # соседних кадров набора с каждой стороны
SIMILAR = 12                # похожих кадров из других наборов (кроме точных копий)
SIM_CACHE = os.path.join("art", "objects", "review_cache", "identity_similar.npz")
MISSING = ["larger map crop", "more map placements", "neighbouring frames in set", "neighbouring tiles on map",
           "family / other side", "animation / destroyed / second state", "how it looks in game (HD)",
           "ruleset / pedia text", "other"]
STATUS = ["IDENTITY_VISUALLY_VERIFIED", "PART_FRAGMENT_CONFIRMED", "NOT_OBJECT", "UNSURE"]
VERIFIED, FRAGMENT, NOT_OBJECT, UNSURE = STATUS


def load(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding=ENC) as f:
        return json.load(f)


def big(im, k, bg):
    """Кадр nearest xk на фоне."""
    im = im.convert("RGBA")
    out = Image.new("RGBA", im.size, bg + (255,))
    out.alpha_composite(im)
    return out.resize((im.width * k, im.height * k), Image.NEAREST).convert("RGB")


def labelled(im, text, frame=None):
    lab = Image.new("RGB", (max(im.width, 8 * len(text) + 6), im.height + 16), (20, 20, 24))
    lab.paste(im, (0, 16))
    d = ImageDraw.Draw(lab)
    d.text((3, 2), text, fill=(255, 220, 0))
    if frame:
        d.rectangle((0, 16, im.width - 1, lab.height - 1), outline=frame, width=3)
    return lab


def caption(im, lines):
    """Кадр с подписью в несколько строк снизу."""
    w = max(im.width, max(6 * len(s) + 6 for s in lines))
    out = Image.new("RGB", (w, im.height + 12 * len(lines) + 4), (20, 20, 24))
    out.paste(im, (0, 0))
    d = ImageDraw.Draw(out)
    for i, s in enumerate(lines):
        d.text((2, im.height + 2 + 12 * i), s, fill=(255, 220, 0) if i == 0 else (200, 200, 205))
    return out


def row(cells, gap=6, bg=(20, 20, 24)):
    cells = [c for c in cells if c is not None]
    if not cells:
        return None
    out = Image.new("RGB", (sum(c.width for c in cells) + gap * (len(cells) - 1), max(c.height for c in cells)), bg)
    x = 0
    for c in cells:
        out.paste(c, (x, 0))
        x += c.width + gap
    return out


def fit(im, w):
    if im is None or im.width <= w:
        return im
    return im.resize((w, max(1, int(im.height * w / im.width))), Image.LANCZOS)


class Cards:
    def __init__(self):
        import identity_propose as ip
        import map_mockup as mm
        import review_server as rs
        self.ip, self.mm = ip, mm
        items = {it["rank"]: it for it in load(rs.ITEMS)}
        with open(rs.IDENTITY, encoding=ENC, newline="") as f:
            self.rows = {r["asset_id"]: r for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE)}
        fams = {fm["family_id"]: fm for fm in load(ip.FAMS, [])}
        self.ctx = ip.Context(items, fams, self.rows)
        self.world = self.ctx.world
        self.items = items
        self.props = load(PROPOSALS, {}) or {}
        self.prompts = {}
        for p in PHOTO_JOBS:                      # описание, которым рисовали (подтверждённое на карточке 32x40)
            for j in load(p, []) or []:
                self.prompts.setdefault(j["asset_id"], (j.get("what", ""), p))

    def sprite(self, key):
        s, f = key.split(":")
        return self.world.sprite(s.lower(), int(f), None)

    # ---------------------------------------------------------------- панели

    def p_sprite(self, it):
        ims = [self.sprite(k) for k in it["src"]]
        ims = [i for i in ims if i is not None]
        if not ims:
            return None
        if len(ims) == 1:
            im = ims[0]
        else:
            import obj_review as orv
            im = orv.compose(ims, it.get("at") or [[0, 0, 0]] * len(ims))
            im = im.resize((im.width // orv.K, im.height // orv.K), Image.NEAREST)
        return row([labelled(big(im, 8, DARK), "x8 on dark"), labelled(big(im, 8, LIGHT), "x8 on light"),
                    labelled(big(im, 3, DARK), "x3 (game size x3)")])

    def places(self, keys):
        """До PLACES разных блоков по кадру и его побайтным копиям в других наборах: сначала разные террейны,
        потом больше всего вхождений. Копия в чужом наборе - независимое место (C_INT:27 есть и в банке METRO1)."""
        use = sorted(((t, b, n, k) for k in keys for t, b, n in self.ctx.usage.get(k.upper(), [])),
                     key=lambda x: -x[2])
        out, terr = [], set()
        for x in use:
            if x[0] not in terr:
                out.append(x)
                terr.add(x[0])
        for x in use:
            if len(out) >= PLACES:
                break
            if x not in out:
                out.append(x)
        return out[:PLACES], len(use)

    # ------------------------------------------------- похожие кадры во всех наборах (независимые аналоги)

    def sim_index(self):
        """Признаки всех кадров, стоящих на картах: маска и яркость 16x20 по габариту, средний цвет, хэш пикселей.
        Кэш в review_cache, ключ - список кадров."""
        if getattr(self, "_sim", None) is not None:
            return self._sim
        import hashlib
        import numpy as np
        keys = sorted(self.ctx.usage.keys())
        try:
            z = np.load(SIM_CACHE, allow_pickle=False)
            if list(z["keys"]) == keys:
                self._sim = {k: z[k] for k in z.files}
                self._sim["keys"] = list(z["keys"])
                return self._sim
        except (OSError, KeyError, ValueError):
            pass
        t0 = time.time()
        K, M, L, COL, H = [], [], [], [], []
        for k in keys:
            sp = self.sprite(k)
            if sp is None:
                continue
            a = np.asarray(sp.convert("RGBA"))
            m = a[..., 3] > 0
            if m.sum() < 20:
                continue
            ys, xs = np.nonzero(m)
            crop, cm = a[ys.min():ys.max() + 1, xs.min():xs.max() + 1], m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
            mi = np.asarray(Image.fromarray((cm * 255).astype(np.uint8)).resize((16, 20), Image.BILINEAR)) / 255.0
            lum = (crop[..., :3].astype(np.float32).mean(-1) * cm).astype(np.uint8)
            li = np.asarray(Image.fromarray(lum).resize((16, 20), Image.BILINEAR)).astype(np.float32).ravel()
            li = (li - li.mean()) / (li.std() + 1e-6)
            K.append(k)
            M.append(mi.ravel())
            L.append(li)
            COL.append(crop[cm][:, :3].astype(np.float32).mean(0))
            H.append(hashlib.sha1(np.ascontiguousarray(a[..., :3] * m[..., None]).tobytes() + m.tobytes()).hexdigest())
        os.makedirs(os.path.dirname(SIM_CACHE), exist_ok=True)
        self._sim = {"keys": K, "M": np.array(M, np.float32), "L": np.array(L, np.float32),
                     "COL": np.array(COL, np.float32), "H": np.array(H)}
        np.savez(SIM_CACHE, keys=np.array(keys), **{k: v for k, v in self._sim.items() if k != "keys"},
                 kept=np.array(K))
        self._sim["keys"] = K
        print("индекс похожих: %d кадров, %.0f с" % (len(K), time.time() - t0), flush=True)
        return self._sim

    def similar(self, key, top=SIMILAR):
        """[(score, iou, corr, dcol, key, exact)] - точные копии первыми, потом лучшие аналоги; свой кадр и
        кадры того же набора - мимо (их показывают раздел 3 и 4)."""
        import numpy as np
        S = self.sim_index()
        keys = list(S["kept"]) if "kept" in S else S["keys"]
        idx = {k: i for i, k in enumerate(keys)}
        i = idx.get(key.upper(), idx.get(key))
        if i is None:
            return []
        M, L, COL, H = S["M"], S["L"], S["COL"], S["H"]
        iou = np.minimum(M, M[i]).sum(1) / np.maximum(np.maximum(M, M[i]).sum(1), 1e-6)
        corr = (L @ L[i]) / L.shape[1]
        dcol = np.abs(COL - COL[i]).mean(1)
        score = 0.5 * iou + 0.5 * np.clip(corr, 0, None) - dcol / 255
        exact = H == H[i]
        score = np.where(exact, 2.0, score)
        own = key.split(":")[0].upper()
        out = []
        for j in np.argsort(-score):
            k = keys[j]
            if j == i or (k.split(":")[0].upper() == own and not exact[j]):
                continue
            out.append((float(score[j]), float(iou[j]), float(corr[j]), float(dcol[j]), k, bool(exact[j])))
            if len(out) >= top and not exact[j]:
                break
        return out

    def asset_of(self, key):
        if getattr(self, "_f2a", None) is None:
            r2a = {int(r["rank"]): a for a, r in self.rows.items() if r.get("rank")}
            self._f2a = {}
            for rank, it in self.items.items():
                for k in it["src"]:
                    if rank in r2a:
                        self._f2a.setdefault(k.upper(), r2a[rank])
            for a, r in self.rows.items():
                self._f2a.setdefault(a.upper(), a)
                if r.get("canonical"):
                    self._f2a.setdefault(r["canonical"].upper(), a)
        return self._f2a.get(key.upper())

    def p_similar(self, sims):
        cells = []
        for score, iou, corr, dcol, k, exact in sims:
            sp = self.sprite(k)
            if sp is None:
                continue
            a = self.asset_of(k)
            r = self.rows.get(a) or {}
            ident = (r.get("identity") or r.get("proposed_name") or "-")[:30]
            terr = ",".join(sorted({t for t, b, n in self.ctx.usage.get(k.upper(), [])})[:2])[:30]
            cells.append(caption(big(sp, 3, DARK), [k, "COPY" if exact else "sim %.2f (iou %.2f)" % (score, iou),
                                                    ident, (r.get("status") or "no identity row")[:30], terr]))
        return stack([row(cells[i:i + 6]) for i in range(0, len(cells), 6)]) if cells else None

    def p_place(self, key, terrain, block):
        """(вырез вокруг клетки x3, весь блок) с рамкой на клетке."""
        s, f = key.split(":")
        mark = (s.upper(), int(f))
        try:
            lvl = self.mm.mark_level(self.world, terrain, block, mark)
            im, marks = self.mm.render(self.world, terrain, block, None, 1, mark, maxz=lvl)
            whole, wmarks = self.mm.render(self.world, terrain, block, None, 1, mark)
        except (SystemExit, Exception) as e:          # noqa: BLE001 - блок не читается: без этого места
            return None, "блок %s/%s не читается: %s" % (terrain, block, e)
        if not marks:
            return None, "кадр в блоке %s/%s не найден" % (terrain, block)
        x0, y0, x1, y1 = marks[0][2]
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        rw, rh = 32 * 5, 40 * 4
        box = (max(0, cx - rw), max(0, cy - rh), min(im.width, cx + rw), min(im.height, cy + rh))
        k = 3
        crop = Image.new("RGBA", (box[2] - box[0], box[3] - box[1]), DARK + (255,))
        crop.alpha_composite(im.crop(box))
        crop = crop.resize((crop.width * k, crop.height * k), Image.NEAREST).convert("RGB")
        d = ImageDraw.Draw(crop)
        for m in marks:
            a = m[2]
            if a[0] >= box[0] and a[1] >= box[1] and a[2] <= box[2] and a[3] <= box[3]:
                d.rectangle(((a[0] - box[0]) * k, (a[1] - box[1]) * k, (a[2] - box[0]) * k, (a[3] - box[1]) * k),
                            outline=(255, 40, 40), width=3)
        # рентген: то же место, окружение притушено, кадр поверх всего - иначе предмет за стеной не виден
        sp = self.sprite(key)
        xr = Image.new("RGBA", (box[2] - box[0], box[3] - box[1]), DARK + (255,))
        xr.alpha_composite(im.crop(box))
        xr = Image.blend(Image.new("RGBA", xr.size, DARK + (255,)), xr, 0.35)
        self.xray = 0
        if sp is not None:
            for m in marks:
                a = m[2]
                if a[0] >= box[0] and a[1] >= box[1] and a[2] <= box[2] and a[3] <= box[3]:
                    xr.alpha_composite(sp.convert("RGBA"), (a[0] - box[0], a[1] - box[1]))
                    self.xray += 1
        xr = xr.resize((xr.width * k, xr.height * k), Image.NEAREST).convert("RGB")
        crop = row([crop, labelled(xr, "x-ray: surroundings dimmed, this frame drawn on top")])
        w = Image.new("RGBA", whole.size, DARK + (255,))
        w.alpha_composite(whole)
        w = w.convert("RGB")
        d = ImageDraw.Draw(w)
        for m in wmarks:
            d.rectangle(m[2], outline=(255, 40, 40), width=2)
        w = fit(w.resize((w.width * 2, w.height * 2), Image.NEAREST), 1100)
        note = "этаж %s, в блоке %d раз" % (lvl, len(marks))
        return (labelled(crop, "%s / %s - near the cell, x3 (floors above cut)" % (terrain, block)),
                labelled(w, "%s / %s - whole block, all floors" % (terrain, block))), note

    def p_pck(self, key):
        s, f = key.split(":")
        f = int(f)
        cells = []
        for i in range(max(0, f - PCK_SIDE), f + PCK_SIDE + 1):
            sp = self.sprite("%s:%d" % (s, i))
            if sp is None:
                continue
            cells.append(labelled(big(sp, 3, DARK), str(i), (255, 220, 0) if i == f else None))
        rows = [row(cells[i:i + 9]) for i in range(0, len(cells), 9)]
        return stack(rows)

    def p_neighbours(self, key, where):
        out = []
        for n in self.ctx.neighbours(key.upper(), where):
            sp = self.sprite(n["key"])
            if sp is not None:
                out.append(labelled(big(sp, 3, DARK), "%s %s %s" % (n["where"].replace(" cell", ""), n["part"],
                                                                     n["key"])))
        return stack([row(out[i:i + 6]) for i in range(0, len(out), 6)]) if out else None

    def p_states(self, key):
        """Записи MCD с этим кадром первым: анимация, разрушенный вид, второе состояние."""
        s, f = key.split(":")
        recs = self.world.records(s.upper())
        out = []
        for n, r in enumerate(recs):
            if r["frame"] != int(f):
                continue
            anim = list(dict.fromkeys(r["frames"]))
            if len(anim) > 1:
                out.append(labelled(row([big(self.sprite("%s:%d" % (s, a)), 3, DARK) for a in anim
                                         if self.sprite("%s:%d" % (s, a)) is not None]),
                                    "record %d: animation frames %s" % (n, anim)))
            for what, idx in (("destroyed", r["die"]), ("second state", r["alt"])):
                if idx and idx < len(recs):
                    sp = self.sprite("%s:%d" % (s, recs[idx]["frame"]))
                    if sp is not None:
                        out.append(labelled(big(sp, 3, DARK), "record %d %s: %s:%d" % (n, what, s,
                                                                                      recs[idx]["frame"])))
        return row(out) if out else None

    def p_family(self, fx):
        out = []
        for x in (fx["family"] + fx["other_sides"])[:10]:
            sp = self.sprite(x["key"])
            if sp is not None:
                out.append(labelled(big(sp, 3, DARK), "%s %s" % (x["key"], x["relation"])))
        return stack([row(out[i:i + 6]) for i in range(0, len(out), 6)]) if out else None

    # ---------------------------------------------------------------- карточка

    def card(self, asset, out_dir, n):
        r = self.rows.get(asset)
        if r is None:
            raise SystemExit("нет %s в asset_identity.tsv" % asset)
        it = self.items[int(r["rank"])]
        key = it["src"][0]
        fx = self.ctx.facts(r, it)
        panels, notes = [], []

        def add(name, title, im):
            if im is None:                        # пустой раздел называем, а не прячем: «нет» - тоже контекст
                notes.append("%s - нет" % title.strip())
                return
            fn = "%02d_%s.png" % (n, name)
            im.save(os.path.join(out_dir, "img", fn))
            panels.append((title, fn))

        add("sprite", "1. кадр крупно", self.p_sprite(it))
        sims = self.similar(key)
        copies = [s[4] for s in sims if s[5]]
        places, total = self.places([key] + copies)
        xray = 0
        for i, (t, b, cnt, k) in enumerate(places):
            self.xray = 0
            pair, note = self.p_place(k, t, b)
            notes.append("%s/%s: %s" % (t, b, note))
            xray += 1 if self.xray else 0
            if pair:
                add("place%d" % i, "2. место на карте %d из %d блоков: %s / %s%s" % (
                    i + 1, total, t, b, "" if k == key else " (копия %s)" % k), pair[0])
                add("block%d" % i, "   весь блок %s" % b, pair[1])
        add("pck", "3. соседние кадры набора %s (кадр в жёлтой рамке)" % key.split(":")[0], self.p_pck(key))
        where = "%s/%s" % (places[0][0], places[0][1]) if places else it.get("map", "")
        add("near", "4. рядом на карте (%s): та же клетка и соседние" % where,
            self.p_neighbours(places[0][3] if places else key, where))
        add("states", "5. запись MCD: анимация, разрушенный вид, второе состояние", self.p_states(key))
        add("family", "6. семейство и «другой бок»", self.p_family(fx))
        add("similar", "8. тот же кадр и похожие в других наборах: COPY - побайтная копия, sim - сходство формы и "
                       "яркости; опознание аналога - тоже гипотеза, пока у него не IDENTITY_VISUALLY_VERIFIED",
            self.p_similar(sims))
        p = self.props.get(asset) or {}
        answers = []
        for k in ("first", "second"):
            a = p.get(k) or {}
            if isinstance(a, dict) and (a.get("proposed_name") or a.get("short_description")):
                answers.append("%s: %s" % (a.get("proposed_name", ""), a.get("short_description", "")))
        prompt, src = self.prompts.get(asset, ("", ""))
        if not xray:                              # рентген - часть ворот: без него карточка неполная
            notes.append("КАРТОЧКА НЕПОЛНАЯ: нет рентгена (кадр не найден ни на одной карте)")
        return {"n": n, "asset": asset, "panels": panels, "notes": notes, "xray": xray, "card_complete": xray > 0,
                "facts": self.ip.facts_text(fx), "answers": answers,
                "verdict": p.get("verdict", ""), "status": r.get("status", ""),
                "prompt": prompt or r.get("identity") or r.get("proposed", ""),
                "prompt_src": src or "asset_identity.tsv"}


def stack(ims, gap=6, bg=(20, 20, 24)):
    ims = [i for i in ims if i is not None]
    if not ims:
        return None
    out = Image.new("RGB", (max(i.width for i in ims), sum(i.height for i in ims) + gap * (len(ims) - 1)), bg)
    y = 0
    for i in ims:
        out.paste(i, (0, y))
        y += i.height + gap
    return out


PAGE = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Опознание с контекстом</title>
<style>
:root{--bg:#1b1b1f;--card:#26262c;--fg:#e8e8ea;--mut:#9a9aa3;--acc:#f2c14e;--ok:#3f8f5a;--mid:#8a7a2e;--bad:#a3423a}
body{background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif;margin:0;padding:16px;max-width:1200px}
h1{font-size:18px;margin:0 0 4px}h2{font-size:16px;margin:0 0 8px}.mut{color:var(--mut)}
.card{background:var(--card);border-radius:8px;padding:14px;margin:16px 0}
.p{margin:10px 0}.p .t{color:var(--acc);font-weight:600;font-size:13px;margin-bottom:4px}
.p img{max-width:100%;border-radius:4px;image-rendering:pixelated}
pre{white-space:pre-wrap;background:#1f1f24;padding:8px;border-radius:4px;font-size:12px;margin:4px 0}
.ans{background:#1f1f24;border-radius:4px;padding:6px 8px;margin:4px 0}
button{background:#33333b;color:var(--fg);border:1px solid #44444d;border-radius:4px;padding:3px 10px;cursor:pointer}
button.on[data-v=IDENTITY_VISUALLY_VERIFIED]{background:var(--ok)}button.on[data-v=UNSURE]{background:var(--mid)}
button.on[data-v=PART_FRAGMENT_CONFIRMED]{background:#3a6fa8}button.on[data-v=NOT_OBJECT]{background:var(--bad)}button.on.m{background:#7a5ab8}
.btns{display:flex;gap:4px;flex-wrap:wrap;margin:6px 0}
input[type=text]{width:100%;box-sizing:border-box;background:#1f1f24;color:var(--fg);border:1px solid #44444d;border-radius:4px;padding:5px;margin:4px 0}
textarea{width:100%;height:140px;background:#1f1f24;color:var(--fg);box-sizing:border-box}
</style></head><body>
<h1>__TITLE__</h1>
<div class="mut">По каждому предмету: посмотрите всё - кадр, места на картах, соседние кадры набора, что стоит рядом,
разрушенный вид, семейство; рентген показывает кадр, даже если на карте его закрывает стена. Ответы модели и
прежнее описание - только гипотезы, они могут быть неверны.<br>Два вопроса: <b>это вообще самостоятельный предмет?</b>
и <b>что это?</b> Статус: IDENTITY_VISUALLY_VERIFIED - самостоятельный предмет, опознан; PART_FRAGMENT_CONFIRMED - кусок
большей конструкции (в поле - чего кусок); NOT_OBJECT - не предмет (стена, пол, рельеф); UNSURE - не ясно, и тогда
отметьте, какого контекста не хватило, не угадывайте. Описание - по-английски, одной фразой (предмет, материал, цвет).
TSV внизу - прислать целиком.</div>
<div id="cards"></div>
<h2>TSV</h2><textarea id="tsv" readonly></textarea>
<script>
const DATA = __DATA__, MISS = __MISS__, CERT = __STATUS__, KEY = "__KEY__-v2";
let st = {}; try { st = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
function save(){ try { localStorage.setItem(KEY, JSON.stringify(st)); } catch (e) {} tsv(); }
const clean = s => (s || "").replace(/[\\t\\n]/g, " ");
function tsv(){
  const L = [["asset_id", "final_identity", "status", "missing_context", "note"].join("\\t")];
  for (const c of DATA) { const s = st[c.asset] || {};
    L.push([c.asset, clean(s.i), s.c || "", Object.keys(s.m || {}).filter(k => s.m[k]).join(","), clean(s.n)].join("\\t")); }
  document.getElementById("tsv").value = L.join("\\n");
}
const esc = t => String(t).replace(/[&<>"]/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[ch]));
const root = document.getElementById("cards");
for (const c of DATA) {
  const s = st[c.asset] = st[c.asset] || {}; s.m = s.m || {};
  const el = document.createElement("div"); el.className = "card";
  let h = `<h2>${c.n}. ${esc(c.asset)}</h2>`;
  for (const [t, f] of c.panels) h += `<div class="p"><div class="t">${esc(t)}</div><img src="img/${f}"></div>`;
  h += `<div class="p"><div class="t">7. гипотезы (могут быть неверны)</div>`;
  h += `<div class="ans">прежнее описание-промпт: <b>${esc(c.prompt)}</b> <span class="mut">(${esc(c.prompt_src)})</span></div>`;
  for (const a of c.answers) h += `<div class="ans">модель: ${esc(a)}</div>`;
  h += `<div class="mut">ответы модели: ${esc(c.verdict || "-")}, статус ${esc(c.status)}</div>`;
  h += `<div class="t" style="margin-top:8px">факты из данных игры</div><pre>${esc(c.facts)}</pre>`;
  if (c.notes.length) h += `<div class="mut">${c.notes.map(esc).join("<br>")}</div>`;
  h += `</div>`;
  el.innerHTML = h;
  const i = document.createElement("input"); i.type = "text"; i.placeholder = "final_identity, in English: what it is, or what it is a part of";
  i.value = s.i || ""; i.oninput = () => { s.i = i.value; save(); };
  el.insertAdjacentHTML("beforeend", `<div class="t" style="color:var(--acc);font-weight:600">что это</div>`); el.appendChild(i);
  const cb = document.createElement("div"); cb.className = "btns";
  for (const v of CERT) { const b = document.createElement("button"); b.textContent = v; b.dataset.v = v;
    if (s.c === v) b.classList.add("on");
    b.onclick = () => { s.c = s.c === v ? "" : v; cb.querySelectorAll("button").forEach(x => x.classList.toggle("on", x.dataset.v === s.c)); save(); };
    cb.appendChild(b); }
  el.appendChild(cb);
  el.insertAdjacentHTML("beforeend", `<div class="mut">UNSURE - какого контекста не хватило:</div>`);
  const mb = document.createElement("div"); mb.className = "btns";
  for (const v of MISS) { const b = document.createElement("button"); b.textContent = v; b.className = "m";
    if (s.m[v]) b.classList.add("on"); b.onclick = () => { s.m[v] = !s.m[v]; b.classList.toggle("on", s.m[v]); save(); };
    mb.appendChild(b); }
  el.appendChild(mb);
  const n = document.createElement("input"); n.type = "text"; n.placeholder = "заметка (по-русски можно)";
  n.value = s.n || ""; n.oninput = () => { s.n = n.value; save(); }; el.appendChild(n);
  root.appendChild(el);
}
tsv();
</script></body></html>"""


def make(assets, out, title):
    os.makedirs(os.path.join(out, "img"), exist_ok=True)
    for f in os.listdir(os.path.join(out, "img")):
        if f.endswith(".png"):
            os.remove(os.path.join(out, "img", f))
    C = Cards()
    cards = []
    for n, a in enumerate(assets, 1):
        t0 = time.time()
        c = C.card(a, out, n)
        cards.append(c)
        print("%-24s панелей %d, %.0f с; %s" % (a, len(c["panels"]), time.time() - t0, "; ".join(c["notes"])),
              flush=True)
    key = "identity-gate-v2-" + os.path.basename(os.path.normpath(out))
    page = (PAGE.replace("__DATA__", json.dumps(cards, ensure_ascii=False)).replace("__MISS__", json.dumps(MISSING))
            .replace("__STATUS__", json.dumps(STATUS)).replace("__KEY__", key).replace("__TITLE__", html.escape(title)))
    with open(os.path.join(out, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    with open(os.path.join(out, "cards.json"), "w", encoding=ENC) as f:
        json.dump({"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "title": title, "assets": assets,
                   "cards": [{k: v for k, v in c.items() if k != "panels"} for c in cards]}, f, ensure_ascii=False,
                  indent=1)
    rel = os.path.relpath(out, os.path.join("art", "objects", "generation")).replace(os.sep, "/")
    print("страница: http://localhost:8778/%s/index.html" % rel)


def read_tsv(path):
    with open(path, encoding=ENC) as f:
        head = f.readline().rstrip("\r\n").split("\t")
        return [dict(zip(head, (l.rstrip("\r\n").split("\t") + [""] * len(head))[:len(head)])) for l in f if l.strip()]


OK_VALUES = ("yes", "no", "open")      # identity_ok: верно / неверно / истина не установлена (не «ошибка»)


def judge(a, ref):
    """Один ответ против сверки - по двум воротам отдельно (специалист 01.10).

    Контекст: раскрыта ли старая ошибка (old_rejected), не назван ли кусок предметом (false_standalone).
    Истина: identity_ok yes - закрыта верно, no - закрыта неверно, open - истина не установлена: это не
    ошибка человека, а нехватка независимой правды; верность тогда None, а не ложь.
    """
    ref = ref or {}
    st, rs = a["status"], ref.get("ref_status", "").strip()
    ok = ref.get("identity_ok", "").strip().lower() or "open"
    old = ref.get("old_rejected", "").strip().lower()
    sok = ref.get("structural_ok", "").strip().lower()
    sem = ref.get("semantic_ok", "").strip().lower()
    j = {"status_ok": None, "false_standalone": None, "truth": None, "old_rejected": old or None,
         "structure": None, "semantic": None}
    if not rs:
        return j
    j["status_ok"] = st == rs
    j["false_standalone"] = st == VERIFIED and rs in (FRAGMENT, NOT_OBJECT)
    if ok in ("yes", "no"):
        j["truth"] = j["status_ok"] and ok == "yes"
    if sok in ("yes", "no"):
        j["structure"] = j["status_ok"] and sok == "yes"
    if sem in ("yes", "no"):
        j["semantic"] = j["status_ok"] and sem == "yes"
    return j


def rate(k, n):
    return round(k / n, 3) if n else None


def gate(checks):
    """True - все да; False - хоть одно нет; None - не решено (есть проверка без данных)."""
    vals = list(checks.values())
    if any(v is False for v in vals):
        return False
    return None if any(v is None for v in vals) else True


def report(out, path="", ref_path=""):
    meta = load(os.path.join(out, "cards.json"))
    path = path or os.path.join(out, "answers_vitali.tsv")
    ans = {r["asset_id"]: r for r in read_tsv(path)}
    refs = {r["asset_id"]: r for r in read_tsv(ref_path)} if ref_path else {}
    rows, bad = [], []
    for c in meta["cards"]:
        a = ans.get(c["asset"], {})
        r = {"asset_id": c["asset"], "final_identity": a.get("final_identity", "").strip(),
             "status": a.get("status", "").strip(), "missing_context": a.get("missing_context", ""),
             "note": a.get("note", ""), "old_prompt": c["prompt"], "card_complete": c.get("card_complete", False)}
        if r["status"] not in STATUS:
            bad.append("%s: статус '%s' не из %s" % (c["asset"], r["status"], "/".join(STATUS)))
        elif r["status"] in (VERIFIED, FRAGMENT) and not r["final_identity"]:
            bad.append("%s: %s без final_identity" % (c["asset"], r["status"]))
        ref = refs.get(c["asset"]) or {}
        ok = ref.get("identity_ok", "").strip().lower()
        if ref and ok and ok not in OK_VALUES:
            bad.append("%s: identity_ok '%s' не из %s" % (c["asset"], ok, "/".join(OK_VALUES)))
        sok = ref.get("structural_ok", "").strip().lower()
        if sok and sok not in OK_VALUES:
            bad.append("%s: structural_ok '%s' не из %s" % (c["asset"], sok, "/".join(OK_VALUES)))
        r["ref_status"], r["identity_ok"] = ref.get("ref_status", ""), ok or ("open" if ref else "")
        r["structural_ok"] = sok
        sem = ref.get("semantic_ok", "").strip().lower()
        if sem and sem not in OK_VALUES + ("excluded",):
            bad.append("%s: semantic_ok '%s' не из %s" % (c["asset"], sem, "/".join(OK_VALUES + ("excluded",))))
        r["semantic_ok"] = sem
        r["truth_identity"], r["relation"] = ref.get("truth_identity", "").strip(), ref.get("relation", "").strip()
        r.update(judge(r, ref))
        rows.append(r)
    n = len(rows)
    by = Counter(r["status"] for r in rows)
    unsure = [r for r in rows if r["status"] == UNSURE]
    miss = Counter(m for r in unsure for m in r["missing_context"].split(",") if m)
    have_ref = all(r["ref_status"] for r in rows)
    fs = [r for r in rows if r["false_standalone"]]
    closed = [r for r in rows if r["truth"] is not None]
    ref_v = [r for r in rows if r["ref_status"] == VERIFIED]
    ref_f = [r for r in rows if r["ref_status"] == FRAGMENT]
    m = {"n": n, "by_status": dict(by), "cards_incomplete": sum(1 for r in rows if not r["card_complete"]),
         "unsure": len(unsure), "unsure_rate": rate(len(unsure), n),
         "unsure_missing_context": sum(1 for r in unsure if r["missing_context"]),
         "missing_context": dict(miss), "reference": ref_path or None}
    if have_ref:
        m.update({"false_standalone": len(fs), "false_standalone_rate": rate(len(fs), n),
                  "part_fragment_correct": "%d/%d" % (sum(1 for r in ref_f if r["status_ok"]), len(ref_f)),
                  "identity_correct": "%d/%d closed, %d open" % (
                      sum(1 for r in ref_v if r["truth"]), sum(1 for r in ref_v if r["truth"] is not None),
                      sum(1 for r in ref_v if r["truth"] is None)),
                  "truth_closed": len(closed), "truth_open": n - len(closed)})
    if have_ref:
        cls_ok = sum(1 for r in rows if r["status_ok"])
        m["classification_correct"] = "%d/%d" % (cls_ok, n)
        m["classification_accuracy"] = rate(cls_ok, n)
    sem = [r for r in rows if r["semantic"] is not None]
    if any(r["semantic_ok"] for r in rows):
        m["semantic_correct"] = "%d/%d, excluded %d, open %d" % (
            sum(1 for r in sem if r["semantic"]), len(sem), sum(1 for r in rows if r["semantic_ok"] == "excluded"),
            sum(1 for r in rows if r["semantic_ok"] in ("open", "")))
        m["semantic_accuracy"] = rate(sum(1 for r in sem if r["semantic"]), len(sem))
    srows = [r for r in rows if r["structural_ok"]]
    if srows:
        sc = [r for r in srows if r["structure"] is not None]
        m["structural"] = "%d/%d closed, %d open" % (sum(1 for r in sc if r["structure"]), len(sc), len(srows) - len(sc))
    old = [r["old_rejected"] for r in rows]
    ctx = {"ответы целы": not bad, "карточки полные (рентген)": m["cards_incomplete"] == 0,
           "UNSURE из-за нехватки контекста 0": not any(r["missing_context"] for r in unsure) and not unsure,
           "старые ошибки раскрыты %d/%d (ни одно старое ложное описание не принято)" % (n, n):
               None if any(o not in ("yes", "no") for o in old) else all(o == "yes" for o in old),
           "ложных самостоятельных 0": None if not have_ref else not fs}
    truth = {"истина закрыта %d/%d" % (n, n): None if len(closed) < n else True,
             "закрытые верны": None if not closed else all(r["truth"] for r in closed)}
    gates = {"CONTEXT_GATE": {"checks": ctx, "passed": gate(ctx)},
             "IDENTITY_TRUTH_GATE": {"checks": truth, "passed": gate(truth),
                                     "closed": len(closed), "open": n - len(closed)}}
    res = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "answers": path, "metrics": m, "invalid": bad,
           "gates": gates, "rows": rows,
           "note": "CONTEXT_GATE - хватило ли карточки, чтобы раскрыть старую ошибку и не принять кусок за предмет; "
                   "IDENTITY_TRUTH_GATE - установлена ли независимая истина. identity_ok open - истина не "
                   "установлена, это не ошибка человека. Статус человека сам по себе - не истина"}
    with open(os.path.join(out, "report.json"), "w", encoding=ENC) as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    word = {True: "PASS", False: "**FAIL**", None: "не решены"}
    L = ["# %s - итог" % meta["title"], ""]
    for g, v in gates.items():
        extra = " (закрыто %d, открыто %d)" % (v["closed"], v["open"]) if "closed" in v else ""
        L += ["## %s: %s%s" % (g, word[v["passed"]], extra), ""]
        L += ["- %s: %s" % (k, {True: "да", False: "**нет**", None: "нет данных"}[c]) for k, c in v["checks"].items()]
        L += [""]
    L += ["По статусам: " + ", ".join("%s %d" % kv for kv in by.most_common()),
          "UNSURE %d (%s), из них с отметкой «не хватило контекста» %d" % (len(unsure), m["unsure_rate"],
                                                                          m["unsure_missing_context"])]
    if have_ref:
        L += ["identity_correct %s; part_fragment_correct %s; ложных самостоятельных %d (rate %s)" % (
            m["identity_correct"], m["part_fragment_correct"], len(fs), m["false_standalone_rate"])]
    if m.get("classification_correct"):
        L += ["Точность класса (предмет / кусок / не предмет): %s (%s)" % (m["classification_correct"],
                                                                         m["classification_accuracy"])]
    if m.get("semantic_correct"):
        L += ["Точность названия (в ворота не входит): %s (%s)" % (m["semantic_correct"], m["semantic_accuracy"])]
    if m.get("structural"):
        L += ["Структурное опознание (отдельно от смыслового, в ворота истины не входит): %s" % m["structural"]]
    if miss:
        L += ["Чего не хватило: " + ", ".join("%s - %d" % kv for kv in miss.most_common())]
    L += ["Ошибки в ответах: " + "; ".join(bad)] if bad else []
    word3 = {True: "верно", False: "неверно", None: "OPEN"}
    L += ["", "| предмет | было (неверно) | стало | статус | сверка | эталон | старое отвергнуто | истина (смысл) "
              "| название | структура | заметка |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    L += ["| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
        r["asset_id"], r["old_prompt"], r["final_identity"], r["status"], r["ref_status"] or "-",
        " ".join(x for x in (r["truth_identity"], "(%s)" % r["relation"] if r["relation"] else "") if x) or "-",
        r["old_rejected"] or "-", word3[r["truth"]] if r["ref_status"] else "-",
        "исключено" if r["semantic_ok"] == "excluded" else (word3[r["semantic"]] if r["semantic_ok"] else "-"),
        word3[r["structure"]] if r["structural_ok"] else "-", r["note"]) for r in rows]
    with open(os.path.join(out, "report.md"), "w", encoding=ENC) as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["make", "report"])
    ap.add_argument("--regression", action="store_true", help="три провала из identity_regression.json")
    ap.add_argument("--assets", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--title", default="")
    ap.add_argument("--answers", default="", help="TSV ответов (по умолчанию <out>/answers_vitali.tsv)")
    ap.add_argument("--reference", default="", help="TSV сверки: asset_id, ref_status, identity_ok (yes/no)")
    a = ap.parse_args()
    os.chdir(ROOT)
    out = a.out or OUT_REG
    if a.cmd == "report":
        return report(out, a.answers, a.reference)
    if a.regression:
        assets = [x["asset_id"] for x in load(REGRESSION)["items"]]
        title = a.title or "IDENTITY_GATE_V2 - регрессия: 3 известных провала опознания"
    else:
        assets = [x.strip() for x in a.assets.split(",") if x.strip()]
        title = a.title or "IDENTITY_GATE_V2"
    if not assets:
        raise SystemExit("нет ассетов: --regression или --assets")
    make(assets, out, title)


if __name__ == "__main__":
    main()
