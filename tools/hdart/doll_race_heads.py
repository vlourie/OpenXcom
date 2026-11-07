"""Головы расы поверх собранных тел (doll_race_assemble.py): кадр на внешность, тот же рисовальщик, что у doll_pipe_pilot.

У FHUMAN волосы лежат в трёх слоях: слой 13 повторяет волосы слоя головы, а афро F23 и пряди на груди - в слое тела. Зона кадра
собирается по всем трём (docs/research/doll-pipeline-2026-11-03.md, 10.18). Описания - doll_looks_<раса>.json, глазами по классике.
Выход art/doll/pipe_pilot/<раса>/heads/: raw/, layers/, лист heads.png. layers/ UBERGAL и мод не трогает.

  py -3 tools/gpuq.py add --name doll_fhuman_heads --prio 1 -- E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe E:/OpenXCom/tools/hdart/doll_race_heads.py --looks F40,F23
  --dry-run - без модели: входы кадров и зоны на листе.
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from concurrent.futures import ThreadPoolExecutor
import doll_pipe_pilot as P                         # до numpy: пилот ставит окружение модели
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import build_pack as bp
import doll_b2_render as db
import doll_ctl_pilot as cp
import doll_photo_pilot as dp
import vx_control as vc
import wall_section as ws

RACE = "FHUMAN"
OUT = os.path.join(db.ROOT, "art", "doll", "pipe_pilot", RACE.lower())
BODIES = os.path.join(OUT, "assembled")
HEADS = os.path.join(OUT, "heads")
BODY, HEAD, HAIR = 2, 10, 13
FACE_BOX = (77, 56, 84, 66)                         # проверено на 6 внешностях крупно, 05.11
NECK_ROW = 69                                       # выше - цвет и альфа кадра головы, ниже - тело как собрано
PAGE = 8                                            # внешностей на лист
SHEET_CLOSE = (56, 38, 104, 90)
SHEET_FULL = (50, 38, 110, 148)


def names_of(look):
    return ["%s__%d__%s_NUDE" % (RACE, BODY, look), "%s__%d__HEAD_%s" % (RACE, HEAD, look), "%s__%d__HAIR_%s" % (RACE, HAIR, look)]


def saved_names(look):
    """Под какими именами слои идут в layers/: у NEKOMIMI свои."""
    return names_of(look)


def mask_of(n):
    return dp.layer_mask(P.FILES, n) if n in P.FILES else np.zeros((db.H, db.W), bool)


def classic_parts(look):
    """Как P._classic_parts, но голова - слои головы и волос вместе."""
    bn, hn, rn = names_of(look)
    body = db.load_indices(P.FILES[bn])
    head = db.load_indices(P.FILES[hn])
    hair = db.load_indices(P.FILES[rn]) if rn in P.FILES else np.zeros_like(head)
    bm, hm = body != 0, (head != 0) | (hair != 0)
    idx = np.where(hair != 0, hair, np.where(head != 0, head, body))
    torso = bm.copy()
    torso[:np.nonzero(hm)[0].max() + 6] = False
    halves = np.nonzero(np.bincount(body[torso] // 8, minlength=32) / float(torso.sum()) >= 0.02)[0]
    allm = bm | hm
    pad = np.pad(allm, 1)
    inner = pad[:-2, 1:-1] & pad[2:, 1:-1] & pad[1:-1, :-2] & pad[1:-1, 2:]
    return bm, hm, inner, np.isin(idx // 8, halves)


def setup(looks_file):
    dp.RACE, dp.BODY, dp.HEAD = RACE, BODY, HEAD
    P.FILES, P.PAL = db.sprite_files(), db.game_palette()
    cp.FILES, cp.PAL = P.FILES, P.PAL
    P.FACE_BOX = FACE_BOX
    P._classic_parts = classic_parts
    with open(looks_file, encoding="utf-8-sig") as f:
        P.LOOKS = json.load(f)


def frame_box(look):
    bm, hm, _i, _r = classic_parts(look)
    xs = np.nonzero(hm)[1]
    w, h = P.RUN["head"]["w"], P.RUN["head"]["h"]
    cx, top = int(xs.min() + xs.max() + 1) // 2, int(np.nonzero(hm | bm)[0].min()) - 1
    return cx - w // 2, top, cx - w // 2 + w, top + h


def job(i, look):
    names = [n for n in names_of(look) if n in P.FILES]
    pz = P.passport(P.FILES, P.PAL, look)
    box = frame_box(look)
    z = P.RUN["head"]["zoom"]
    b4 = tuple(v * dp.K for v in box)
    size = ((box[2] - box[0]) * z, (box[3] - box[1]) * z)
    start = Image.new("RGBA", (db.W * dp.K, db.H * dp.K), dp.PANEL + (255,))
    start.alpha_composite(cp.b2_canvas(names))
    zone = P.hair_zone(look, box)
    hs = ws.sil4(zone)[b4[1]:b4[3], b4[0]:b4[2]]
    cl = dp.classic(P.FILES, P.PAL, names)
    whole_zone = P.hair_zone(look, (0, 0, db.W, db.H))
    return {"look": look, "tag": "head_%s" % look, "names": names, "pz": pz, "box": box, "b4": b4, "zone": zone, "classic": cl,
            "lost": int((whole_zone & ~zone).sum()),                    # что зона хотела бы, а в кадр не влезло
            "prompt": P.head_text(pz), "negative": P.negative_for(pz), "seed": P.RUN["seed"] + 50 + i,
            "init": start.crop(b4).resize(size, Image.LANCZOS),
            "mask": Image.fromarray((hs > 0.5).astype(np.uint8) * 255).resize(size, Image.NEAREST),
            "control": vc.control_map(cl.crop(box), z, "gray"), "kind": "head", "items": item_jobs(i, look, pz, cl)}


def item_jobs(i, look, pz, cl):
    """Вещи на теле, которых нет на основе (полосы на голенях F21): кадр поверх собранного тела, как в P.main. box - на месте вещи."""
    if not pz["items"]:
        return []
    iw, ih, iz = P.RUN["item"]["w"], P.RUN["item"]["h"], P.RUN["item"]["zoom"]
    base = Image.open(os.path.join(BODIES, look.lower() + ".png")).convert("RGBA")
    bm = mask_of(names_of(look)[0])
    out = []
    for n, it in enumerate(pz["items"]):
        ix0, iy0, ix1, iy1 = it["box"]
        bx, by = (ix0 + ix1) // 2 - iw // 2, (iy0 + iy1) // 2 - ih // 2
        ib = (bx * dp.K, by * dp.K, (bx + iw) * dp.K, (by + ih) * dp.K)
        im = np.zeros(bm.shape, bool)
        im[iy0:iy1, ix0:ix1] = bm[iy0:iy1, ix0:ix1]
        grown = ws.sil4(im)
        mark4 = cl.resize((db.W * dp.K, db.H * dp.K), Image.NEAREST).convert("RGBA")
        mark4.putalpha(Image.fromarray((grown > 0.5).astype(np.uint8) * 255))
        start = Image.new("RGBA", base.size, dp.PANEL + (255,))
        start.alpha_composite(base)
        start.alpha_composite(mark4)
        size = (iw * iz, ih * iz)
        out.append({"tag": "item_%s_%d" % (look, n), "kind": "item", "ib": ib, "grown": grown, "seed": P.RUN["seed"] + 500 + i * 10 + n,
                    "prompt": P.item_text(pz, it), "negative": P.negative_for(pz),
                    "init": start.crop(ib).resize(size, Image.LANCZOS),
                    "mask": Image.fromarray((grown[ib[1]:ib[3], ib[0]:ib[2]] > 0.5).astype(np.uint8) * 255).resize(size, Image.NEAREST),
                    "control": vc.control_map(cl.crop((bx, by, bx + iw, by + ih)), iz, "gray")})
    return out


def frames(jobs):
    return jobs + [it for j in jobs for it in j["items"]]


def worker(jobs):
    painter = None
    todo = frames(jobs)
    for j in todo:
        done = os.path.join(HEADS, "raw", j["tag"] + "_out.png")
        if os.path.exists(done):
            continue
        if painter is None:
            painter = P.Painter([x["prompt"] for x in todo] + [x["negative"] for x in todo])
            print("модель загружена за %d с" % painter.load_s, flush=True)
        t = time.time()
        try:
            run = P.RUN[j["kind"]]
            rgb, s0 = painter.paint(j["init"], j["mask"], j["control"], j["prompt"], j["seed"], run["strength"], run["control"], j["negative"])
        except Exception as e:                          # память карты: новый процесс продолжит
            print("кадр %s упал: %s" % (j["tag"], str(e)[:300]), flush=True)
            sys.exit(75)
        Image.fromarray(rgb).save(done)
        with open(os.path.join(HEADS, "raw", j["tag"] + "_render.json"), "w", encoding=db.ENC) as f:
            json.dump({"seconds": round(time.time() - t), "sigma0": s0, "seed": j["seed"], "prompt": j["prompt"]}, f, ensure_ascii=False)
        print("  %s: %.0f с" % (j["tag"], time.time() - t), flush=True)


def fill_backdrop(h4, sil, neck, face, band=20):
    """Волосы на кадре уже силуэта классики: в щели подложка ответа, альфа слоя показывает её серой каймой (F16, M45, лист 05.11).
    Щель - серое, связанное с полем кадра, только у края силуэта: седые волосы в глубине не задеваются. Закрашивается соседними волосами."""
    lab = bp._rgb_to_lab(h4 / 255.0)
    field = cv2.dilate(sil.astype(np.uint8), np.ones((9, 9), np.uint8)) == 0
    field[neck:] = False                                # ниже шеи в кадре торс, его цвет в медиане вместо подложки (F18, M8)
    de = np.linalg.norm(lab - np.median(lab[field], axis=0), axis=-1)
    d = cv2.distanceTransform(sil.astype(np.uint8), cv2.DIST_L2, 5)
    inner = sil & (d > band)
    inner[neck:] = False
    # седые волосы цвета подложки (F37, M50 - доля 0.12, у остальных не больше 0.05): порог уже, иначе край волос закрашивается лицом
    near = de < (5 if (de[inner] < 18).mean() > 0.08 else 10)
    _n, lb = cv2.connectedComponents(near.astype(np.uint8), connectivity=4)
    grey = near & np.isin(lb, np.unique(lb[field & near]))
    gap = grey & sil & (d <= band)
    gap = (cv2.dilate(gap.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))) > 0) & sil
    if not gap.any():
        return h4
    # цвет только волос: лицо, повязка и макияж в широкой щели давали грязно-зелёное пятно (F63, F36). Широкой щели - большее размытие
    rest = sil & ~gap & ~face
    ring = (cv2.dilate(gap.astype(np.uint8), np.ones((15, 15), np.uint8)) > 0) & rest
    src = rest & (np.linalg.norm(lab - np.median(lab[ring if ring.any() else rest], axis=0), axis=-1) < 35)
    fill, c = P._blur_in(h4, src, 6.0)
    for s in (16.0, 40.0):
        f2, c2 = P._blur_in(h4, src, s)
        a = np.clip(c / 0.15, 0, 1)[..., None]
        fill, c = fill * a + f2 * (1 - a), np.maximum(c, c2)
    # узкая щель берет цвет соседей: от волос до плеча вдоль шеи тянулась линия цвета волос (M34, M57, M61, M26)
    wide = cv2.morphologyEx(gap.astype(np.uint8), cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13))) > 0
    near, cn = P._blur_in(h4, sil & ~gap, 4.0)
    far, _c = P._blur_in(h4, sil & ~gap, 12.0)
    a = np.clip(cn / 0.05, 0, 1)[..., None]
    near = near * a + far * (1 - a)
    # и размытый край заливки за щелью, он виден сквозь шов тела: иначе кайма волос у края шеи (M34)
    thin = (cv2.dilate((gap & ~wide).astype(np.uint8), np.ones((7, 7), np.uint8)) > 0) & ~wide
    w = cv2.GaussianBlur(thin.astype(np.float32), (0, 0), 1.0)[..., None]
    fill = fill * (1 - w) + near * w
    # на самой щели вес полный: размытие у края альфы оставляло половину серого, светлые кончики прядей (F18, M8, лист 05.11)
    t = np.maximum(cv2.GaussianBlur(gap.astype(np.float32), (0, 0), 1.0), gap.astype(np.float32))[..., None]
    return h4 * (1 - t) + fill * t


def compose(j, rgb):
    """Кадр головы на собранное тело -> слои тела, головы и волос. Шаги те же, что в P.main: кожа, тон волос, плавный шов."""
    look, zone, b4 = j["look"], j["zone"], j["b4"]
    bn, hn, rn = names_of(look)
    k = dp.K
    base = np.asarray(Image.open(os.path.join(BODIES, look.lower() + ".png")).convert("RGBA"), np.float32).copy()
    for it in j["items"]:
        ib = it["ib"]
        rgbi = Image.open(os.path.join(HEADS, "raw", it["tag"] + "_out.png")).convert("RGB")
        i4 = np.asarray(rgbi.resize((ib[2] - ib[0], ib[3] - ib[1]), Image.LANCZOS), np.float32)
        a = cv2.GaussianBlur((it["grown"] > 0.5).astype(np.float32), (0, 0), 1.5)[ib[1]:ib[3], ib[0]:ib[2], None]
        base[ib[1]:ib[3], ib[0]:ib[2], :3] = base[ib[1]:ib[3], ib[0]:ib[2], :3] * (1 - a) + i4 * a
    f4 = base[..., :3]
    h4 = np.asarray(Image.fromarray(rgb).resize((b4[2] - b4[0], b4[3] - b4[1]), Image.LANCZOS), np.float32)
    # пряди классики в слое тела вне зоны: у собранного тела там нет данных, в слой шла подложка сборки (F16, M19, лист 05.11)
    hole = (ws.sil4(mask_of(bn)) > 0) & (base[..., 3] < 128)
    hole[NECK_ROW * k:] = False
    zone4 = ws.sil4(zone) > 0.5
    # все, что альфа покажет хоть немного: тонкие кончики прядей у сглаженного силуэта слабее половины, по порогу 0.5 их нет (F18, M8)
    shown = (ws.sil4(zone) > 0) | (ws.sil4(mask_of(hn)) > 0) | (ws.sil4(mask_of(rn)) > 0) | hole
    face4 = np.zeros(shown.shape, bool)
    face4[(FACE_BOX[1] - 4) * k:(NECK_ROW + 1) * k, (FACE_BOX[0] - 2) * k:(FACE_BOX[2] + 4) * k] = True
    h4 = fill_backdrop(h4, shown[b4[1]:b4[3], b4[0]:b4[2]], NECK_ROW * k - b4[1], face4[b4[1]:b4[3], b4[0]:b4[2]])
    fh = f4.copy()
    fh[b4[1]:b4[3], b4[0]:b4[2]] = h4
    x0, y0, x1, y1 = FACE_BOX
    cheeks = np.zeros((db.H, db.W), bool)
    cheeks[y0 + 4:y1 + 1, x0:x1 + 1] = True
    fi = fh
    fh, sd = P.skin_match(fi, look, zone, cheeks, (0, 0, 0))
    # сдвиг Lab один на всю кожу, в тени он меняет оттенок: тень у шеи становилась тёмно-красным пятном (M33, M35). В тени слабее по яркости
    li = bp._rgb_to_lab(fi / 255.0)[..., 0]
    fh = fi + (fh - fi) * np.clip(li / np.median(li[ws.sil4(cheeks) > 0.5]), 0, 1)[..., None] ** 2
    yy, xx = np.indices(cheeks.shape)
    off_face = ((xx < x0 - 1) | (xx > x1 + 2) | (yy < y0)) & (yy <= y1)
    fface = (xx >= x0) & (xx <= x1) & (yy >= y0) & (yy <= y1)
    # шея под подбородком: тёмные пиксели классики там тень, а не волосы; подтяжка красила её в тёмно-красное пятно с каймой у подбородка (M33, M35)
    throat = (xx >= x0 - 2) & (xx <= x1 + 4) & (yy > y1) & (yy <= NECK_ROW)
    fh0 = fh
    fh, d0, d1 = P.tone_lock(fh, j["names"], zone & (~P.skin_cover(look) | off_face) & ~fface & ~throat)
    # подтяжка только по волосам и плавно: лоб выше линии волос классики тянуло к волосам - шов поперёк лба (M5, F2), чёрную прядь к серому пятну классики - клякса (M45)
    lab = bp._rgb_to_lab(fh0 / 255.0)
    dl = lab - np.median(lab[ws.sil4(cheeks) > 0.5], axis=0)
    hairish = cv2.GaussianBlur(np.clip((np.sqrt((dl[..., 0] * 0.5) ** 2 + dl[..., 1] ** 2 + dl[..., 2] ** 2) - 16) / 10, 0, 1).astype(np.float32), (0, 0), 1.5)[..., None]
    fh = fh0 + cv2.GaussianBlur((fh - fh0) * hairish, (0, 0), 8.0).reshape(fh.shape) * hairish
    if j["pz"]["face_to_body"]:
        fh = P.face_to_body(fh, f4)
    w = np.clip(cv2.GaussianBlur(zone4.astype(np.float32), (0, 0), 4.0) * 2, 0, 1)
    w = np.maximum(w, cv2.GaussianBlur(hole.astype(np.float32), (0, 0), 1.0) * 2).clip(0, 1)[..., None]
    whole = f4 * (1 - w) + fh * w
    body = np.asarray(P.layer_from(whole, mask_of(bn)), np.float32).copy()
    # ниже шеи вне зоны - тело как собрано: layer_from красит край классики и тянет серое из щели, которую вырезала сборка
    below = np.zeros(cheeks.shape, bool)
    below[NECK_ROW:] = True
    keep = np.arange(body.shape[0])[:, None] >= NECK_ROW * k
    near = w[..., 0] * keep
    body[..., :3] = np.where(keep[..., None], base[..., :3] * (1 - near[..., None]) + body[..., :3] * near[..., None], body[..., :3])
    body[..., 3] = np.where(keep, np.maximum(base[..., 3], ws.sil4(zone & below) * 255), body[..., 3])
    body = Image.fromarray(np.clip(body + 0.5, 0, 255).astype(np.uint8), "RGBA")
    # край слоя головы и волос у фигуры внутри: подложки за ним нет, а цвет изнутри давал светлую рамку подбородка (M33, M35)
    outer = (ws.sil4(mask_of(bn)) > 0) | (ws.sil4(mask_of(hn)) > 0) | (ws.sil4(mask_of(rn)) > 0)
    inside = cv2.distanceTransform(outer.astype(np.uint8), cv2.DIST_L2, 5) > 5

    def part(n):
        a = np.asarray(P.layer_from(fh, mask_of(n)), np.float32).copy()
        a[..., :3][inside] = fh[inside]
        return Image.fromarray(np.clip(a + 0.5, 0, 255).astype(np.uint8), "RGBA")

    return body, (part(hn) if hn in P.FILES else None), (part(rn) if rn in P.FILES else None), {"skin": sd, "hair_dE": [d0, d1]}


def finish(jobs, dry):
    """Листы постранично: на странице столько внешностей, сколько можно разглядеть крупно."""
    report = {}
    # потоки: cv2 и numpy отпускают GIL, 16 листов подряд шли 16 минут
    with ThreadPoolExecutor(8) as ex:
        for rep in ex.map(lambda p: finish_page(jobs[p:p + PAGE], dry, p // PAGE + 1), range(0, len(jobs), PAGE)):
            report.update(rep)
    with open(os.path.join(HEADS, "report.json"), "w", encoding=db.ENC) as f:
        json.dump(report, f, ensure_ascii=False, indent=0)


def finish_page(jobs, dry, page):
    FONT = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 18)
    k = dp.K
    close = tuple(v * k for v in SHEET_CLOSE)
    full = tuple(v * k for v in SHEET_FULL)
    Z = 2
    cw, ch = (close[2] - close[0]) * Z, (close[3] - close[1]) * Z
    fw, fh_ = (full[2] - full[0]) * ch // (full[3] - full[1]), ch
    per = 2 if not dry else 3
    tile_w = (cw * 2 + fw + 8) if not dry else (cw * 2 + 8)
    n = (len(jobs) + per - 1) // per
    sheet = Image.new("RGB", (per * tile_w, n * (ch + 26)), (15, 15, 18))
    d = ImageDraw.Draw(sheet)
    report = {}
    for i, j in enumerate(jobs):
        look = j["look"]
        x, y = (i % per) * tile_w, (i // per) * (ch + 26)
        cl = j["classic"].resize((db.W * k, db.H * k), Image.NEAREST)
        a = P.tile(cl, close).resize((cw, ch), Image.NEAREST)
        sheet.paste(a, (x, y + 26))
        if dry:
            t = j["init"].convert("RGB").resize((cw, ch), Image.LANCZOS)
            m = np.asarray(j["mask"].resize((cw, ch), Image.NEAREST)) > 0
            arr = np.asarray(t).copy()
            arr[~m] = arr[~m] // 3
            sheet.paste(Image.fromarray(arr), (x + cw, y + 26))
            d.text((x + 3, y + 3), "%s: классика | вход и зона; вне кадра %d" % (look, j["lost"]), fill=(255, 230, 0), font=FONT)
            continue
        rgb = np.asarray(Image.open(os.path.join(HEADS, "raw", j["tag"] + "_out.png")).convert("RGB"))
        body, head, hair, info = compose(j, rgb)
        report[look] = info
        for nm, lay in zip(saved_names(look), (body, head, hair)):
            if lay is not None:
                lay.save(os.path.join(HEADS, "layers", nm.lower() + ".png"))
        all_ = Image.new("RGBA", (db.W * k, db.H * k), (40, 42, 50, 255))
        for lay in (body, head, hair):
            if lay is not None:
                all_.alpha_composite(lay)
        sheet.paste(all_.convert("RGB").crop(close).resize((cw, ch), Image.LANCZOS), (x + cw, y + 26))
        sheet.paste(all_.convert("RGB").crop(full).resize((fw, fh_), Image.LANCZOS), (x + 2 * cw, y + 26))
        d.text((x + 3, y + 3), "%s: классика | новое | фигура; кожа %s" % (look, info["skin"]), fill=(255, 230, 0), font=FONT)
    fn = os.path.join(HEADS, ("heads_dry_%02d.png" if dry else "heads_%02d.png") % page)
    sheet.save(fn)
    print(fn, sheet.size, flush=True)
    return report


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--looks", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--worker", action="store_true", help="(служебное) рисовать недостающие кадры подряд")
    ns = ap.parse_args()
    for d in ("raw", "layers"):
        os.makedirs(os.path.join(HEADS, d), exist_ok=True)
    setup(os.path.join(HERE, "doll_looks_%s.json" % RACE.lower()))
    jobs = [job(i, look) for i, look in enumerate(ns.looks.split(",") if ns.looks else P.LOOKS)]
    if ns.worker:
        worker(jobs)
        return
    if not ns.dry_run:
        for attempt in range(3):
            if all(os.path.exists(os.path.join(HEADS, "raw", j["tag"] + "_out.png")) for j in frames(jobs)):
                break
            r = subprocess.run([sys.executable, os.path.abspath(sys.argv[0]), "--worker"] + (["--looks", ns.looks] if ns.looks else []))
            print("рабочий процесс вышел с кодом %s (попытка %d)" % (r.returncode, attempt + 1), flush=True)
        missing = [j["tag"] for j in frames(jobs) if not os.path.exists(os.path.join(HEADS, "raw", j["tag"] + "_out.png"))]
        if missing:
            raise SystemExit("не нарисованы: %s" % missing)
    finish(jobs, ns.dry_run)


if __name__ == "__main__":
    main()
