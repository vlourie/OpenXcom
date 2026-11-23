#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Лист разметки правды для внешнего разметчика (P1-C): та же сотня, что на странице arbiter.py label.

Разметчик получает то же, что видел бы человек на странице: кадр, место на карте, семейство, данные MCD
и две догадки A/B. Ответов арбитра в листе нет. Имена ассетов (набор и номер кадра) заменены номером
карточки - арбитру их тоже не показывали; ключ номер -> ассет остаётся здесь и в пакет не входит.

    py -3.13 tools/hdart/truth_sheet.py make   <снимок.json>
    py -3.13 tools/hdart/truth_sheet.py import <снимок.json> <ответы.tsv> --who specialist

make   -> <снимок>/truth_sheet/upload/ (страницы PNG, cards.md, INSTRUCTIONS.md, answers_template.tsv)
          и upload.zip рядом; ключ - <снимок>/truth_sheet/key.json.
import -> truth.tsv рядом со снимком, who = --who. Чужие метки (другой who) не перезаписываются:
          расхождения печатаются, в файл идёт прежняя метка.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import textwrap
import time
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import arbiter as ar                                   # noqa: E402
from PIL import Image, ImageDraw, ImageFont            # noqa: E402

ENC = "utf-8-sig"
PER_PAGE = 5
W, H = 1800, 440                                        # карточка
FONT = "C:/Windows/Fonts/arial.ttf"
FONT_B = "C:/Windows/Fonts/arialbd.ttf"

INSTRUCTIONS = """# Разметка правды: контрольные 100 карточек

Ты размечаешь правду для проверки арбитра. На каждой карточке - один предмет из игры (X-Piratez на движке
OpenXcom): кадр предмета в увеличении, его место на карте, иногда родственные кадры (перекраска, зеркало,
плитка) и данные движка (MCD). Две модели предложили для предмета по названию - это догадки A и B.
Ответов арбитра здесь нет, и что он выбрал - неизвестно. A и B расставлены по алфавиту, порядок ничего не значит.

## Метки

- **A** - верна догадка A, B хуже
- **B** - верна догадка B, A хуже
- **BOTH** - обе верны, это одно и то же
- **NEITHER** - ни одна не верна (в заметке напиши, что это на самом деле)
- **CANNOT_TELL** - по карточке сказать нельзя

## Что на карточке

- слева номер карточки;
- кадр предмета x4 на сером фоне;
- место на карте (кадр в окружении соседей, та же сцена, что в игре); сам предмет обведён красной рамкой;
- если есть - полоса родственных кадров с подписью связи;
- справа A и B: название, категория, короткое описание, и строки данных движка (MCD, объём в вокселях, семейство).

Текст карточек продублирован в `cards.md` - если на картинке что-то не читается, смотри там.

## Ответ

Ровно 100 строк, по одной на карточку, в форме `answers_template.tsv`:

```
card<TAB>truth<TAB>note
1<TAB>A<TAB>
2<TAB>NEITHER<TAB>wooden barrel
```

`truth` - одна из пяти меток латиницей. `note` можно оставить пустым, у NEITHER - обязательно.
Номера карточек - как на листах (1..100). Можно прислать и через пробелы: `1 A`, `2 NEITHER wooden barrel`.
"""


def items_in_order(snap):
    """Порядок как на странице разметки: по хэшу, не по классу - класс не угадывается по номеру."""
    return sorted(snap["items"], key=lambda x: hashlib.sha1(("truth:" + x["asset_id"]).encode()).hexdigest())


def pic(d, x, kind):
    p = os.path.join(d, "inputs", "%s_%s.png" % (x["asset_id"].replace(":", "_"), kind))
    return Image.open(p).convert("RGBA") if kind in x["inputs"] and os.path.exists(p) else None


def fit(im, w, h, nearest=False):
    s = min(w / im.width, h / im.height)
    return im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))),
                     Image.NEAREST if nearest else Image.LANCZOS)


def paste_on(dst, im, x, y, bg):
    tile = Image.new("RGBA", im.size, bg)
    tile.alpha_composite(im)
    dst.paste(tile.convert("RGB"), (x, y))


def card_text(n, x):
    L = ["## Карточка %d" % n, ""]
    for k in ("A", "B"):
        c = x[k]
        L.append("**%s: %s** (%s) - %s" % (k, c.get("proposed_name", ""), c.get("proposed_category", ""),
                                            c.get("short_description", "")))
    L += ["", "```", x["facts"], "```", ""]
    return "\n".join(L)


def draw_card(d, n, x, fonts):
    big, bold, reg, small = fonts
    im = Image.new("RGB", (W, H), (24, 24, 28))
    g = ImageDraw.Draw(im)
    g.rectangle((0, 0, W - 1, H - 1), outline=(80, 80, 90), width=2)
    g.text((16, 12), "#%d" % n, font=big, fill=(230, 180, 34))
    xx = 130
    sp = pic(d, x, "sprite")
    if sp:
        s = fit(sp, 256, 320, nearest=True)
        paste_on(im, s, xx, 60, (128, 128, 128, 255))
        g.text((xx, 32), "sprite x4", font=small, fill=(160, 160, 160))
        xx += 256 + 20
    mc = pic(d, x, "map_crop")
    if mc:
        s = fit(mc, 400, 400)
        paste_on(im, s, xx, 30, (0, 0, 0, 255))
        g.text((xx, 8), "map", font=small, fill=(160, 160, 160))
        xx += 400 + 20
    fv = pic(d, x, "family_views")
    if fv:
        s = fit(fv, 330, 400)
        paste_on(im, s, xx, 30, (0, 0, 0, 255))
        g.text((xx, 8), "family", font=small, fill=(160, 160, 160))
    tx = W - 640
    y = 12
    for k in ("A", "B"):
        c = x[k]
        g.text((tx, y), "%s: %s" % (k, c.get("proposed_name", "")), font=bold, fill=(230, 180, 34))
        y += 30
        g.text((tx, y), "(%s)" % c.get("proposed_category", ""), font=reg, fill=(200, 200, 200))
        y += 24
        for line in textwrap.wrap(c.get("short_description", ""), 70)[:3]:
            g.text((tx, y), line, font=reg, fill=(225, 225, 225))
            y += 22
        y += 10
    for raw in x["facts"].splitlines():
        for line in textwrap.wrap(raw, 86)[:2]:
            if y > H - 20:
                break
            g.text((tx, y), line, font=small, fill=(150, 150, 150))
            y += 18
    return im


def make(path):
    snap, d = ar.check_snapshot(path)
    items = items_in_order(snap)
    out = os.path.join(d, "truth_sheet")
    up = os.path.join(out, "upload")
    os.makedirs(up, exist_ok=True)
    fonts = (ImageFont.truetype(FONT_B, 44), ImageFont.truetype(FONT_B, 24),
             ImageFont.truetype(FONT, 19), ImageFont.truetype(FONT, 15))
    pages = []
    for p0 in range(0, len(items), PER_PAGE):
        chunk = items[p0:p0 + PER_PAGE]
        page = Image.new("RGB", (W, H * len(chunk)), (16, 16, 19))
        for i, x in enumerate(chunk):
            page.paste(draw_card(d, p0 + i + 1, x, fonts), (0, H * i))
        name = "page_%02d_cards_%03d-%03d.png" % (p0 // PER_PAGE + 1, p0 + 1, p0 + len(chunk))
        page.save(os.path.join(up, name), optimize=True)
        pages.append(name)
    with open(os.path.join(up, "cards.md"), "w", encoding=ENC) as f:
        f.write("# Карточки 1..%d (текст с листов)\n\n" % len(items))
        f.write("\n".join(card_text(i + 1, x) for i, x in enumerate(items)))
    with open(os.path.join(up, "INSTRUCTIONS.md"), "w", encoding=ENC) as f:
        f.write(INSTRUCTIONS)
    with open(os.path.join(up, "answers_template.tsv"), "w", encoding=ENC, newline="") as f:
        f.write("card\ttruth\tnote\n" + "".join("%d\t\t\n" % (i + 1) for i in range(len(items))))
    key = {"snapshot_id": snap["snapshot_id"], "items_hash": snap["items_hash"],
           "cards": {str(i + 1): x["asset_id"] for i, x in enumerate(items)}}
    with open(os.path.join(out, "key.json"), "w", encoding=ENC) as f:
        json.dump(key, f, ensure_ascii=False, indent=1)
    zp = os.path.join(out, "upload.zip")
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for fn in sorted(os.listdir(up)):
            z.write(os.path.join(up, fn), fn)
    leak = [x["asset_id"] for x in items if x["asset_id"] in open(os.path.join(up, "cards.md"), encoding=ENC).read()]
    if leak:
        raise SystemExit("в cards.md попали имена ассетов: %s" % leak[:3])
    print("карточек %d, страниц %d -> %s" % (len(items), len(pages), up))
    print("пакет -> %s (%.1f МБ); ключ -> %s" % (zp, os.path.getsize(zp) / 1e6, os.path.join(out, "key.json")))
    return up


LINE = re.compile(r"^\s*#?(\d+)\s*[\t,; ]\s*([A-Za-z_]+)\s*(?:[\t,;]\s*|\s+)?(.*)$")


def parse_answers(p):
    got, bad = {}, []
    with open(p, encoding=ENC) as f:
        for n, line in enumerate(f, 1):
            s = line.rstrip("\r\n")
            if not s.strip() or s.lower().startswith("card"):
                continue
            m = LINE.match(s)
            t = m and m.group(2).upper()
            if not m or t not in ar.TRUTHS:
                bad.append((n, s))
                continue
            got[int(m.group(1))] = (t, m.group(3).strip())
    return got, bad


def import_truth(path, answers, who):
    snap, d = ar.check_snapshot(path)
    with open(os.path.join(d, "truth_sheet", "key.json"), encoding=ENC) as f:
        key = json.load(f)
    if (key["snapshot_id"], key["items_hash"]) != (snap["snapshot_id"], snap["items_hash"]):
        raise SystemExit("ключ листа от другого снимка - лист устарел, собрать заново: make")
    cards = {int(k): v for k, v in key["cards"].items()}
    got, bad = parse_answers(answers)
    for n, s in bad:
        print("строка %d не разобрана: %r" % (n, s))
    unknown = sorted(set(got) - set(cards))
    missing = sorted(set(cards) - set(got))
    no_note = sorted(c for c, (t, note) in got.items() if t == "NEITHER" and not note)
    if bad or unknown:
        raise SystemExit("ответ не принят: не разобрано %d строк, чужих номеров %s" % (len(bad), unknown))
    truth = {k: dict(v) for k, v in ar.load_truth(d).items()}
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    kept, put = [], 0
    for c, (t, note) in sorted(got.items()):
        aid = cards[c]
        old = truth.get(aid)
        if old and old.get("who") != who:
            if old["truth"] != t:
                kept.append((c, aid, old["who"], old["truth"], t))
            continue
        truth[aid] = {"asset_id": aid, "truth": t, "who": who, "when": now, "note": note[:300]}
        put += 1
    ar.save_truth(d, truth)
    print("принято %d меток от %s; всего в truth.tsv %d из %d" % (put, who, len(truth), len(cards)))
    if missing:
        print("нет ответа по карточкам: %s" % missing)
    if no_note:
        print("NEITHER без заметки: %s" % no_note)
    for c, aid, w, t0, t1 in kept:
        print("карточка %d (%s): у %s уже %s, у %s %s - оставлена прежняя" % (c, aid, w, t0, who, t1))
    return put


def main():
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["make", "import"])
    ap.add_argument("snapshot")
    ap.add_argument("answers", nargs="?")
    ap.add_argument("--who", default="specialist")
    a = ap.parse_args()
    if a.cmd == "make":
        make(a.snapshot)
    else:
        if not a.answers:
            raise SystemExit("import: нужен файл ответов")
        import_truth(a.snapshot, a.answers, a.who)


if __name__ == "__main__":
    main()
