"""Листы выбора завала v2, этап A: карточки кандидатов collapse_debris_census.py (census/collapse/debris/
candidates.tsv). На карточке номер для ответа, HD-кадр и классический x3, набор:номер, ход, LOFT, броня, горит ли,
сколько участков игрокам без завала v1 могут его взять.

Темы:
- О (обломки): крошка и куча, в которые что-то превращается при разрушении, кроме горючих растений; для построек;
- Б (бурелом): горючие проходимые объекты из растительных наборов; для упавших крон;
- С (ствол): низкие горючие стены; для поваленного ствола.
Одинаковые картинки (тот же классический кадр и HD-кадр) - одна карточка, остальные в cards.tsv как alias.
    py -3.13 tools/collapse_debris_sheet.py
-> art/collapse_debris/<тема>_NN.png, census/collapse/debris/cards.tsv"""
import hashlib
import os
import sys
from collections import Counter, defaultdict

from PIL import Image, ImageDraw, ImageFont

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "hdart"))
import collapse_census as cc   # noqa: E402
import collapse_v2 as V        # noqa: E402
import xcom_sprites as XS      # noqa: E402

DIR = "census/collapse/debris"
ART = "art/collapse_debris"
HD_ROOT = "user/mods/hd/hd/TERRAIN"
PLANT = {"grass", "dirt", "water", "snow", "sand"}
THEMES = [("О", "обломки - крошка и куча для построек"), ("Б", "бурелом - для упавших крон"),
          ("С", "ствол - низкие горючие стены")]
CW, CH, COLS, ROWS = 214, 196, 8, 7


def read_tsv(path):
    with open(path, encoding="utf-8-sig") as f:
        lines = f.read().splitlines()
    head = lines[0].split("\t")
    return [dict(zip(head, ln.split("\t"))) for ln in lines[1:] if ln.strip()]


def theme_of(c):
    tiers = c["tiers"].split(",")
    burns = int(c["flammable"]) < 255 and int(c["fuel"]) > 0
    if "ствол" in tiers:
        return "С"
    if "бурелом" in tiers and c["material"] in PLANT:
        return "Б"
    # обломки - только то, во что что-то превращается при разрушении: прочие низкие объекты - таблички, грибы, ящики
    if ("крошка" in tiers or "куча" in tiers) and c["die_target"] == "1":
        return "О"
    # бурелом - горючий и не плоский ковёр: 2 слоя LOFT у ковра травы и лиан, если в него ничто не превращается
    if burns and "бурелом" in tiers and (c["die_target"] == "1" or int(c["loft"]) >= 3):
        return "Б"
    return None


def main():
    mod_dir, files, loft_path, loft_occ = cc.open_data(V.game_args())
    pal = XS.load_palette("bin/UFO/GEODATA/PALETTES.DAT")
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 12)
    big = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 16)
    bold = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 18)
    hd_dirs = {d.upper(): os.path.join(HD_ROOT, d) for d in os.listdir(HD_ROOT)}
    pck = {}

    def classic(s, frame):
        if s not in pck:
            p = files.find(os.path.join("TERRAIN", s + ".PCK"))
            t = files.find(os.path.join("TERRAIN", s + ".TAB"))
            pck[s] = XS.read_pck(p, t) if p else []
        fr = pck[s]
        return XS.frame_to_image(fr[frame], pal) if frame < len(fr) else None

    def hd_path(s, frame):
        d = hd_dirs.get((s + ".PCK").upper())
        p = os.path.join(d, "%d.png" % frame) if d else None
        return p if p and os.path.exists(p) else None

    cands = read_tsv(os.path.join(DIR, "candidates.tsv"))
    blocks = read_tsv(os.path.join(DIR, "blocks.tsv"))
    use = Counter()                                  # набор -> участков игрокам без завала v1
    for b in blocks:
        if b["to"] == "игрокам" and not b["rubble_v1"]:
            for s in b["sets"].split():
                use[s] += 1

    by_theme = defaultdict(list)
    for c in cands:
        th = theme_of(c)
        if th:
            by_theme[th].append(c)

    os.makedirs(ART, exist_ok=True)
    for old in os.listdir(ART):
        if old.endswith(".png"):
            os.remove(os.path.join(ART, old))
    card_rows = []
    for th, title in THEMES:
        # ствол - только свои наборы участков (забор чужого набора посреди леса неуместен); свои - впереди доноров
        items = [c for c in by_theme[th] if th != "С" or c["own"] == "1"]
        items = sorted(items, key=lambda c: (c["own"] != "1", -use[c["set"]], c["set"], int(c["idx"])))
        cards, seen = [], {}
        for c in items:
            s, i, frame = c["set"], int(c["idx"]), int(c["frame"])
            im = classic(s, frame)
            hp = hd_path(s, frame)
            h = hashlib.md5((im.tobytes() if im else b"") + (open(hp, "rb").read() if hp else b"")).hexdigest()
            if h in seen:
                seen[h]["alias"].append("%s:%d" % (s, i))
                seen[h]["use"] = max(seen[h]["use"], use[s])
                continue
            card = dict(c=c, im=im, hp=hp, alias=[], use=use[s])
            seen[h] = card
            cards.append(card)
        per = COLS * ROWS
        pages = (len(cards) + per - 1) // per
        for n, card in enumerate(cards):
            card["id"] = "%s%d" % (th, n + 1)
        for pg in range(pages):
            part = cards[pg * per:(pg + 1) * per]
            rows = (len(part) + COLS - 1) // COLS
            img = Image.new("RGB", (CW * COLS, 44 + CH * rows), (36, 38, 44))
            dr = ImageDraw.Draw(img)
            dr.text((8, 12), "%s - %s, лист %d из %d (карточек %d)" % (th, title, pg + 1, pages, len(cards)),
                    font=bold, fill=(240, 220, 150))
            for k, card in enumerate(part):
                c = card["c"]
                x0, y0 = (k % COLS) * CW, 44 + (k // COLS) * CH
                dr.rectangle((x0 + 2, y0 + 2, x0 + CW - 3, y0 + CH - 3), outline=(70, 74, 84))
                if card["hp"]:
                    h = Image.open(card["hp"]).convert("RGBA").resize((96, 120), Image.LANCZOS)
                    img.paste(h, (x0 + 6, y0 + 22), h)
                else:
                    dr.text((x0 + 24, y0 + 70), "нет HD", font=font, fill=(200, 120, 120))
                if card["im"]:
                    im = card["im"].resize((96, 120), Image.NEAREST)
                    img.paste(im, (x0 + 110, y0 + 22), im)
                dr.text((x0 + 6, y0 + 3), card["id"], font=big, fill=(255, 235, 120))
                if c["own"] == "1":
                    dr.text((x0 + 70, y0 + 5), "участков %d" % card["use"], font=font, fill=(150, 200, 240))
                else:
                    dr.text((x0 + 70, y0 + 5), "донор", font=font, fill=(240, 160, 110))
                tu = "непрох." if int(c["tu"]) >= 255 else "TU %s" % c["tu"]
                if c["slot"] != "объект":
                    tu = c["slot"]
                dr.text((x0 + 6, y0 + 145), "%s:%s  %s" % (c["set"], c["idx"], tu), font=font, fill=(230, 230, 230))
                dr.text((x0 + 6, y0 + 160), "LOFT %s/12, броня %s, %s" % (
                    c["loft"], c["armor"], "горит" if int(c["flammable"]) < 255 and int(c["fuel"]) > 0 else "не горит"),
                    font=font, fill=(190, 190, 190))
                extra = ("+%d такие же" % len(card["alias"])) if card["alias"] else ""
                dr.text((x0 + 6, y0 + 175), ("обломок " if c["die_target"] == "1" else "") + extra,
                        font=font, fill=(160, 200, 160))
            img.save(os.path.join(ART, "%s_%02d.png" % ({"О": "debris", "Б": "brush", "С": "trunk"}[th], pg + 1)))
        for card in cards:
            c = card["c"]
            card_rows.append((card["id"], "%s:%s" % (c["set"], c["idx"]), c["tiers"], c["kind"], c["loft"], c["tu"],
                              c["armor"], card["use"], c["die_target"], c["own"], " ".join(card["alias"])))
        print("%s: записей %d, карточек %d, листов %d" % (th, len(items), len(cards), pages))
    cc.write_tsv(os.path.join(DIR, "cards.tsv"),
                 ["card", "record", "tiers", "kind", "loft", "tu", "armor", "blocks", "die_target", "own", "same_picture"],
                 card_rows)


if __name__ == "__main__":
    main()
