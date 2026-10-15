#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Карточки опознания «оружие + все связанные боеприпасы» для сотни weapons100 (указание специалиста 05.10).

Оружие и боеприпас изучаются вместе ДО генерации: W-015 нарисован с магазином-«фильтром», потому что кадр
боеприпаса никто не смотрел. Карточка - часть опознания, генерации не делает.

Данные - как их читает игра:
- поля предметов и статьи педии - итог слияния рулсетов Пираток .index/mod/Piratez/rul/values.tsv (QUOTE_NONE, R-109);
  боеприпас - compatibleAmmo и слоты ammo (OXCE: ammo: {0: {compatibleAmmo: [...]}, ...});
- кадры - выгрузка движка census/items/export/exp_piratez/BIGOBS.PCK.png (16 столбцов 32x48, индекс 0 прозрачен,
  R-043); номер кадра предмета - по столбцу users переписи census/items/bigobs_frames.tsv;
- строки - Language Пираток en-US и ru, ru поверх - RU-патч (как в игре).

Выход art/items/weapons100-v1/ammo_cards/: <W-NNN>.<тип>.png - карточка, ammo.tsv - связи (одна строка на пару
ствол-боеприпас), cards.json - всё, sheet_NN.png - листы по 10.
Запуск: py -3.13 tools/hdart/weapon_ammo_cards.py [--only W-015,W-019]
"""
import argparse
import csv
import json
import os
import re
import sys
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

import numpy as np                          # noqa: E402
import yaml                                 # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

ENC = "utf-8-sig"
LIST = "art/items/weapons100-v1/list.tsv"
OUT = "art/items/weapons100-v1/ammo_cards"
VALUES = ".index/mod/Piratez/rul/values.tsv"
FRAMES = "census/items/bigobs_frames.tsv"
EXPORT = "census/items/export/exp_piratez/BIGOBS.PCK.png"
MODS = "Пиратки/Dioxine_XPiratez/user/mods"
LANG = [("en", MODS + "/Piratez/Language/en-US.yml"), ("ru", MODS + "/Piratez/Language/ru.yml"),
        ("ru", MODS + "/XPZ RU-patch/Language/ru.yml")]
# OXCE ItemDamageType (Mod/RuleDamageType.h): номера; у Пираток часть переименована строками, но номер - факт рулсета
DT = {0: "NONE", 1: "AP", 2: "IN", 3: "HE", 4: "LASER", 5: "PLASMA", 6: "STUN", 7: "MELEE", 8: "ACID", 9: "SMOKE",
      # 10-18 - типы Пираток, имена из STR_DAMAGE_1x в Piratez Language/en-US.yml
      10: "ANTI-E511", 11: "BIO", 12: "ELECTRIC", 13: "EMP", 14: "WARP", 15: "MIND", 16: "STABBING",
      17: "HEAT", 18: "COLD"}
BG = (40, 40, 44)
K = 4


def jv(s):
    try:
        return json.loads(s)
    except (ValueError, TypeError):
        return s


def load_rules():
    csv.field_size_limit(1 << 30)
    items, arts = {}, {}
    with open(VALUES, encoding=ENC, newline="") as f:
        for sec, id_, fld, val in csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            if sec == "items":
                items.setdefault(id_, {})[fld] = jv(val)
            elif sec == "ufopaedia":
                arts.setdefault(id_, {})[fld] = jv(val)
    return items, arts


def load_frames():
    """тип -> кадр BIGOBS, кадр -> строка переписи (dup_of, recolor_of, mirror_of)."""
    by_type, rows = {}, {}
    with open(FRAMES, encoding=ENC, newline="") as f:
        rd = csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
        head = next(rd)
        for r in rd:
            d = dict(zip(head, r))
            rows[int(d["frame"])] = d
            for t in jv(d.get("users", "[]").replace("\\\"", "\"")) or []:
                by_type.setdefault(t, int(d["frame"]))
    return by_type, rows


def load_strings():
    st = {"en": {}, "ru": {}}
    for lang, p in LANG:
        if not os.path.exists(p):
            print("  ! нет файла строк %s" % p)
            continue
        with open(p, encoding="utf-8-sig") as f:
            # yaml-cpp игры терпит управляющие символы в строках (у RU-патча есть 0x16), PyYAML - нет (как R-046)
            data = yaml.load(re.sub("[\x00-\x08\x0b\x0c\x0e-\x1f]", "", f.read()), Loader=yaml.CSafeLoader)
        for v in data.values():
            if isinstance(v, dict):
                st[lang].update({k: str(x) for k, x in v.items()})
    return st


def ammo_of(it):
    """Слоты боеприпаса: [(слот, [типы])]. compatibleAmmo - слот 0; ammo - слоты OXCE."""
    slots = []
    if isinstance(it.get("compatibleAmmo"), list):
        slots.append(("0", list(it["compatibleAmmo"])))
    if isinstance(it.get("ammo"), dict):
        for k in sorted(it["ammo"], key=lambda s: int(s) if str(s).isdigit() else 99):
            ca = (it["ammo"][k] or {}).get("compatibleAmmo") or []
            if k == "0" and slots:
                slots[0] = ("0", list(dict.fromkeys(slots[0][1] + ca)))
            elif ca:
                slots.append((str(k), list(ca)))
    return slots


PIRATEZ = os.path.join(ROOT, "Пиратки", "Dioxine_XPiratez", "user", "mods", "Piratez")
_MOD_FILES = None


def mod_files():
    """Кадры BIGOBS.PCK, заданные файлами мода (extraSprites Piratez_Resources.rul): {кадр движка: путь}.
    Нужны там, где выгрузка движка пуста - набор не был загружен к моменту выгрузки (ленивая загрузка, R-182)."""
    global _MOD_FILES
    if _MOD_FILES is None:
        _MOD_FILES = {}
        inside = False
        with open(os.path.join(PIRATEZ, "Ruleset", "Piratez_Resources.rul"), encoding="utf-8") as f:
            for line in f:
                m = re.match(r"\s*- type:\s*(\S+)", line)
                if m:
                    inside = m.group(1) == "BIGOBS.PCK"
                    continue
                m = re.match(r"\s+(\d+):\s*(\S+\.png)\s*$", line)
                if inside and m:
                    _MOD_FILES[int(m.group(1)) + 1000] = os.path.join(PIRATEZ, m.group(2))
    return _MOD_FILES


def frame_img(sheet_idx, pal, n):
    r, c = divmod(n, 16)
    idx = sheet_idx[r * 48:(r + 1) * 48, c * 32:(c + 1) * 32]
    if not idx.any() and n in mod_files() and os.path.exists(mod_files()[n]):
        # кадра нет в выгрузке - из файла мода по индексам, как движок: левый верх 32x48, индекс 0 прозрачен (R-043)
        im = Image.open(mod_files()[n])
        mp = np.array(im.getpalette()[:768] + [0] * (768 - len(im.getpalette()[:768]))).reshape(-1, 3).astype(np.uint8)
        src = np.asarray(im)[:48, :32]
        idx = np.zeros((48, 32), np.uint8)
        idx[:src.shape[0], :src.shape[1]] = src
        print("  кадр %d взят из файла мода %s" % (n, os.path.relpath(mod_files()[n], PIRATEZ)))
        return Image.fromarray(np.dstack([mp[idx], np.where(idx == 0, 0, 255).astype(np.uint8)]), "RGBA"), idx
    return Image.fromarray(np.dstack([pal[idx], np.where(idx == 0, 0, 255).astype(np.uint8)]), "RGBA"), idx


def on_bg(im, scale):
    im = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
    bg = Image.new("RGBA", im.size, BG + (255,))
    bg.alpha_composite(im)
    return bg.convert("RGB")


def pedia(arts, st, t):
    """Статья педии предмета: раздел и текст (en, ru). Статья ищется по id типа, иначе по requires."""
    a = arts.get(t)
    if a is None:
        for aid, x in arts.items():
            if x.get("requires") == [t] and x.get("type_id") in (4, "4"):
                a = x
                break
    if a is None:
        return {"article": "-", "section": "-", "en": "", "ru": ""}
    key = a.get("text") or ""
    return {"article": t if t in arts else "requires", "section": a.get("section", "-"),
            "en": st["en"].get(key, "") if key else "", "ru": st["ru"].get(key, "") if key else ""}


def fit(dr, line, font, w):
    """Подпись в ширину колонки: не влезает - обрезать с многоточием, а не налезать на соседа."""
    if dr.textlength(line, font=font) <= w:
        return line
    while line and dr.textlength(line + "…", font=font) > w:
        line = line[:-1]
    return line + "…"


def build(rows, items, arts, by_type, frows, st, sheet_idx, pal, out):
    try:
        F = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 15)
        FB = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 17)
        FS = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 13)
    except OSError:
        F = FB = FS = ImageFont.load_default()
    users = {}
    for t, it in items.items():
        for _s, lst in ammo_of(it):
            for a in lst:
                users.setdefault(a, []).append(t)
    links, cards, pngs = [], [], []
    for r in rows:
        t = r["type"]
        it = items.get(t, {})
        slots = ammo_of(it)
        gun = {"master": r["master"], "type": t, "kind": r["kind"], "frame": int(r["frame"]), "cells": r["cells"],
               "en": st["en"].get(t, r.get("en", "")), "ru": st["ru"].get(t, r.get("ru", "")),
               "battleType": it.get("battleType"), "clipSize": it.get("clipSize"), "pedia": pedia(arts, st, t),
               "slots": []}
        for s, lst in slots:
            sl = []
            for a in lst:
                ai = items.get(a, {})
                fr = by_type.get(a)
                fx = frows.get(fr, {}) if fr is not None else {}
                rec = {"type": a, "en": st["en"].get(a, ""), "ru": st["ru"].get(a, ""), "frame": fr,
                       "bigSprite": ai.get("bigSprite"), "clipSize": ai.get("clipSize"),
                       "damageType": ai.get("damageType"), "power": ai.get("power"),
                       "pellets": ai.get("shotgunPellets"), "bbox": fx.get("bbox", ""),
                       "same_as": fx.get("dup_of") or fx.get("recolor_of") or fx.get("mirror_of") or "",
                       "same_how": ("копия" if fx.get("dup_of") else "перекраска" if fx.get("recolor_of")
                                    else "зеркало" if fx.get("mirror_of") else ""),
                       "shared_with": [u for u in users.get(a, []) if u != t], "pedia": pedia(arts, st, a)}
                sl.append(rec)
                links.append([r["master"], t, s, a, rec["en"], rec["ru"], fr if fr is not None else "-",
                              rec["same_how"] + (" " + str(rec["same_as"]) if rec["same_as"] else ""),
                              rec["clipSize"], DT.get(rec["damageType"], rec["damageType"]), rec["power"],
                              len(rec["shared_with"]), ",".join(rec["shared_with"][:12]),
                              rec["pedia"]["section"], "да" if rec["pedia"]["ru"] or rec["pedia"]["en"] else "нет"])
            gun["slots"].append({"slot": s, "ammo": sl})
        if not slots:
            cs = it.get("clipSize") or 0
            # clipSize -1 - бесконечный заряд (холодное), больше 0 - заряд встроен в сам предмет (одноразовые пусковые)
            how = ("встроенный заряд, clipSize %s - боеприпас нарисован на самом предмете" % cs if cs > 0
                   else "без боеприпаса (clipSize %s)" % cs)
            gun["no_ammo"] = how
            links.append([r["master"], t, "-", "-", how, "", "-", "", it.get("clipSize", ""), "", "", 0, "", "", ""])
        cards.append(gun)
        # картинка карточки
        gimg, _ = frame_img(sheet_idx, pal, gun["frame"])
        tiles = [(on_bg(gimg, K), ["СТВОЛ  кадр %d" % gun["frame"] + (", клетки %s" % gun["cells"] if gun["cells"] else ""), gun["ru"], gun["en"]])]
        for sd in gun["slots"]:
            for a in sd["ammo"]:
                if a["frame"] is None:
                    img = Image.new("RGB", (32 * K, 48 * K), BG)
                    ImageDraw.Draw(img).text((8, 80), "кадра нет", fill=(255, 120, 120), font=F)
                else:
                    img = on_bg(frame_img(sheet_idx, pal, a["frame"])[0], K)
                lab = ["слот %s  кадр %s" % (sd["slot"], a["frame"] if a["frame"] is not None else "-"),
                       a["ru"] or a["type"], a["en"] or "",
                       "заряд %s  %s %s%s" % (a["clipSize"], DT.get(a["damageType"], a["damageType"]), a["power"],
                                             ("  дробь %s" % a["pellets"]) if a["pellets"] else ""),
                       ("%s кадра %s" % (a["same_how"], a["same_as"])) if a["same_how"] else "свой кадр",
                       "ещё у %d: %s" % (len(a["shared_with"]), ", ".join(a["shared_with"][:3]) +
                                        ("..." if len(a["shared_with"]) > 3 else "")) if a["shared_with"] else "только у этого ствола",
                       "педия: %s" % ("статья" if a["pedia"]["ru"] or a["pedia"]["en"] else "нет текста")]
                tiles.append((img, lab))
        per_row = 6
        tw, th, lab_h = 32 * K + 72, 48 * K, 7 * 17 + 6
        nrow = (len(tiles) + per_row - 1) // per_row
        text = gun["pedia"]["ru"] or gun["pedia"]["en"] or "(у ствола нет текста педии)"
        tlines = textwrap.wrap(re.sub(r"\{NEWLINE\}|\\n", " ", text), 120)[:6]
        if gun.get("no_ammo"):
            tlines = ["БОЕПРИПАС: " + gun["no_ammo"]] + tlines
        W = max(per_row, min(len(tiles), per_row)) * tw + 16
        H = 40 + nrow * (th + lab_h + 10) + 20 * len(tlines) + 16
        card = Image.new("RGB", (W, H), (24, 24, 26))
        dr = ImageDraw.Draw(card)
        dr.text((10, 10), "%s  %s  (%s)  -  %s" % (r["master"], t, r["kind"], gun["ru"]), fill=(240, 240, 240), font=FB)
        for i, (img, lab) in enumerate(tiles):
            x = 10 + (i % per_row) * tw
            y = 40 + (i // per_row) * (th + lab_h + 10)
            card.paste(img, (x, y))
            for j, line in enumerate(lab):
                dr.text((x, y + th + 4 + j * 17), fit(dr, line, FS, tw - 8), fill=(230, 210, 140) if j == 0 else (220, 220, 220),
                        font=FS)
        y = 40 + nrow * (th + lab_h + 10)
        for j, line in enumerate(tlines):
            dr.text((10, y + j * 20), line, fill=(200, 200, 200), font=F)
        p = os.path.join(out, "%s.%s.png" % (r["master"], t))
        card.save(p)
        pngs.append(p)
        n = sum(len(sd["ammo"]) for sd in gun["slots"])
        print("%s %s: слотов %d, боеприпасов %d%s" % (r["master"], t, len(gun["slots"]), n,
                                                     (", " + gun["no_ammo"]) if gun.get("no_ammo") else ""), flush=True)
    return links, cards, pngs


def sheets(pngs, out, per=10):
    for k in range(0, len(pngs), per):
        ims = [Image.open(p) for p in pngs[k:k + per]]
        W = max(i.width for i in ims)
        H = sum(i.height for i in ims) + 6 * len(ims)
        s = Image.new("RGB", (W, H), (60, 60, 64))
        y = 0
        for i in ims:
            s.paste(i, (0, y))
            y += i.height + 6
        s.save(os.path.join(out, "sheet_%02d.png" % (k // per + 1)))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="мастера через запятую, W-015")
    a = ap.parse_args()
    os.chdir(ROOT)
    with open(LIST, encoding=ENC, newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))
    if a.only:
        want = set(a.only.split(","))
        rows = [r for r in rows if r["master"] in want]
    items, arts = load_rules()
    by_type, frows = load_frames()
    st = load_strings()
    sh = Image.open(EXPORT)
    if sh.mode != "P":
        raise SystemExit("выгрузка %s не в индексах (%s)" % (EXPORT, sh.mode))
    pal = np.asarray(sh.getpalette()[:768], np.uint8).reshape(-1, 3)
    os.makedirs(OUT, exist_ok=True)
    links, cards, pngs = build(rows, items, arts, by_type, frows, st, np.asarray(sh), pal, OUT)
    tag = "_only" if a.only else ""
    with open(os.path.join(OUT, "ammo%s.tsv" % tag), "w", encoding=ENC, newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["master", "type", "slot", "ammo", "en", "ru", "frame", "same_frame_as", "clipSize", "damageType",
                    "power", "n_shared", "shared_with", "pedia_section", "pedia_text"])
        w.writerows(links)
    with open(os.path.join(OUT, "cards%s.json" % tag), "w", encoding=ENC) as f:
        json.dump(cards, f, ensure_ascii=False, indent=1)
    if not a.only:
        sheets(pngs, OUT)
    na = sum(1 for c in cards if c.get("no_ammo"))
    nf = sum(1 for c in cards for sd in c["slots"] for x in sd["ammo"] if x["frame"] is None)
    print("итог: стволов %d, связей ствол-боеприпас %d, без боеприпаса %d, боеприпасов без кадра %d" % (
        len(cards), len([l for l in links if l[3] != "-"]), na, nf))


if __name__ == "__main__":
    main()
