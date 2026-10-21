"""Короткий лист выбора завала v2 (этап A): из 1129 карточек collapse_debris_sheet.py отобраны глазами записи, похожие
на обломки, по ролям и краям. Номер карточки - для ответа Vitali. Ряд «Ст» - записи уже действующего завала v1,
для сравнения. Только чтение установки Пираток.
    py -3.13 tools/collapse_debris_short.py
-> art/collapse_debris/short.png, census/collapse/debris/short.tsv"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "hdart"))
import collapse_census as cc   # noqa: E402
import collapse_v2 as V        # noqa: E402
import xcom_sprites as XS      # noqa: E402

HD_ROOT = "user/mods/hd/hd/TERRAIN"
ROWS = [
    ("Б", "бурелом - сломанные деревья и брёвна (в горных наборах это то, во что превращается дерево)",
     ["MOUNTGRASS:74", "MOUNTGRASS:75", "MOUNTGRASS:76", "MOUNTROCK:74", "MOUNTROCK:75", "MOUNTROCK:76",
      "MOUNTTROP:74", "MOUNTTROP:75", "MOUNTTROP:76", "MOUNTMUD:74", "MOUNTMUD:75", "MOUNTMUD:76",
      "MOUNTWASTE2:74", "MOUNTWASTE2:75", "MOUNTWASTE2:76", "MOUNTSNOW2:74", "MOUNTSNOW2:75", "MOUNTSNOW2:76",
      "FOREST_SNOW:18", "FOREST_SNOW:19", "MOUNT:74", "MOUNT:75", "MOUNT:76"]),
    ("К", "бурелом - кусты и заросли (выше по укрытию)",
     ["VILBITS:19", "VILBITS:20", "FORESTSWAMP:6", "MOUNTGRASS:9", "DAWNURBITS:20", "GOTHIC:7", "FOREST_NORD:9",
      "FOREST_NORD:10"]),
    ("Кр", "камень - крошка и куча",
     ["MOUNTROCK:8", "MOUNTGRASS:8", "MOUNTMUD:8", "MOUNTSNOW2:8", "MUJUNGLE:36", "MUJUNGLE:37", "SIETCH:36",
      "SIETCH:37", "SIETCH_DARK:36", "MUSTYX:10", "INDUSLUM:56", "INDUSLUM:57", "INDUSLUM:58", "INDUSLUM:59"]),
    ("Ст", "завал v1 - уже в игре (камень, дерево, металл)",
     ["URBAN:50", "URBAN:57", "COMMERCE:50", "URBAN40K:57", "MILTECHDIO:26", "URBAN:87", "URBAN:88", "MADDECOR:80",
      "MADDECOR:83", "COMDECOR:68", "VILBAN:87", "CULTIVAT:11", "FRNITURE:7", "URBAN_GOODS:24", "MILBARR:48",
      "MILBARR:49"]),
]
CW, CH, COLS = 214, 176, 8


def main(rows_in=None, png="art/collapse_debris/short.png", tsv="census/collapse/debris/short.tsv"):
    """rows_in - свои ряды (префикс, заголовок, записи) вместо ROWS: так строит лист семейств этапа B
    tools/collapse_debris_families.py."""
    mod_dir, files, loft_path, loft_occ = cc.open_data(V.game_args())
    pal = XS.load_palette("bin/UFO/GEODATA/PALETTES.DAT")
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 12)
    big = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 16)
    bold = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 17)
    hd_dirs = {d.upper(): os.path.join(HD_ROOT, d) for d in os.listdir(HD_ROOT)}
    mcd, raw, pck = {}, {}, {}

    def rec(s, i):
        if s not in mcd:
            mcd[s] = cc.read_mcd(files, s, loft_occ, {})
            p = files.find(os.path.join("TERRAIN", s + ".MCD"))
            raw[s] = open(p, "rb").read() if p else b""
            p = files.find(os.path.join("TERRAIN", s + ".PCK"))
            t = files.find(os.path.join("TERRAIN", s + ".TAB"))
            pck[s] = XS.read_pck(p, t) if p else []
        if i >= len(mcd[s]):
            return None, None
        return mcd[s][i], raw[s][i * cc.REC:(i + 1) * cc.REC]

    rows = []
    for pre, title, recs in rows_in or ROWS:
        seen, items = set(), []
        for r in recs:
            if r not in seen:
                seen.add(r)
                items.append(r)
        rows.append((pre, title, items))
    height = sum(36 + CH * ((len(it) + COLS - 1) // COLS) for _, _, it in rows)
    img = Image.new("RGB", (CW * COLS, height), (36, 38, 44))
    dr = ImageDraw.Draw(img)
    out = []
    y = 0
    for pre, title, items in rows:
        dr.text((8, y + 9), "%s - %s" % (pre, title), font=bold, fill=(240, 220, 150))
        y += 36
        for n, r in enumerate(items):
            s, i = r.split(":")
            i = int(i)
            m, b = rec(s, i)
            x0, y0 = (n % COLS) * CW, y + (n // COLS) * CH
            dr.rectangle((x0 + 2, y0 + 2, x0 + CW - 3, y0 + CH - 3), outline=(70, 74, 84))
            cid = "%s%d" % (pre, n + 1)
            dr.text((x0 + 6, y0 + 3), cid, font=big, fill=(255, 235, 120))
            if m is None:
                dr.text((x0 + 6, y0 + 60), "%s - нет записи" % r, font=font, fill=(200, 120, 120))
                continue
            frame = b[0]
            d = hd_dirs.get((s + ".PCK").upper())
            hp = os.path.join(d, "%d.png" % frame) if d else None
            if hp and os.path.exists(hp):
                h = Image.open(hp).convert("RGBA").resize((96, 120), Image.LANCZOS)
                img.paste(h, (x0 + 6, y0 + 20), h)
            else:
                dr.text((x0 + 24, y0 + 70), "нет HD", font=font, fill=(200, 120, 120))
            if frame < len(pck[s]):
                c = XS.frame_to_image(pck[s][frame], pal).resize((96, 120), Image.NEAREST)
                img.paste(c, (x0 + 110, y0 + 20), c)
            burns = b[45] < 255 and b[57] > 0
            tu = "непрох." if m["tu_walk"] >= 255 else "TU %d" % m["tu_walk"]
            dr.text((x0 + 6, y0 + 142), "%s  %s" % (r, tu), font=font, fill=(230, 230, 230))
            dr.text((x0 + 6, y0 + 157), "LOFT %d/12, броня %d, %s" % (m["nl"], m["armor"], "горит" if burns else "не горит"),
                    font=font, fill=(190, 190, 190))
            out.append((cid, r, m["nl"], m["tu_walk"], m["armor"], int(burns), int(bool(hp and os.path.exists(hp)))))
        y += CH * ((len(items) + COLS - 1) // COLS)
    os.makedirs("art/collapse_debris", exist_ok=True)
    img.save(png)
    cc.write_tsv(tsv, ["card", "record", "loft", "tu", "armor", "burns", "hd"], out)
    print(png, img.size, "карточек", len(out))


if __name__ == "__main__":
    main()
