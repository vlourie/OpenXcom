"""Лица героинь интро на головах кукол UBERGAL - вставкой по точкам, без модели (CPU).

doll_face_pilot (Edit-2511, два входа) отдал героиню целиком - её волосы и кадр, голову куклы не взял (R-211). Здесь
геометрия задаётся руками: лицо героини (F:\\AIStudio\\Escape\\cast, только чтение) переносится аффинно по трём точкам -
центры глаз и рот, размечены по сетке - в те же точки классической головы. Вставляется только в лицо классики (кожа
слоя головы с залитыми дырами глаз и рта), волосы и всё прочее - B2; альфа слоя - силуэт классики x4 ровно.
Цвет кожи подтягивается к классике (TONES - доли), чтобы лицо сошлось с телом.

Выход: art/doll/face_paste/ - layers/<слой>_t<доля>.png (холст 1280x800, k=4), sheet.png. В мод ничего не ставит.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import cv2                                          # noqa: E402
import numpy as np                                  # noqa: E402
from PIL import Image, ImageDraw                    # noqa: E402

import doll_b2_render as db                         # noqa: E402
import doll_photo_pilot as dp                       # noqa: E402
import doll_face_pilot as fp                        # noqa: E402
import wall_section as ws                           # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
OUT = os.path.join(db.ROOT, "art", "doll", "face_paste")
# точки: левый глаз, правый глаз, рот. Героиня - в картинке лица, приведённой к ширине 512; голова - в пикселях
# холста 320x200 (непрерывные: пиксель p занимает [p, p+1])
HEROINE_PTS = {"M1": ((205, 203), (298, 203), (255, 297)), "M2": ((178, 240), (268, 237), (228, 345)),
               "M3": ((128, 253), (237, 242), (190, 368)), "M4": ((195, 165), (258, 165), (230, 240)),
               "M5": ((195, 277), (315, 277), (262, 402)), "M6": ((143, 260), (258, 260), (200, 377))}
HEAD_PTS = {"M0": ((76.0, 53.5), (81.0, 53.5), (78.0, 57.5)), "M56": ((76.0, 53.5), (81.5, 53.5), (79.0, 58.5)),
            "F36": ((76.5, 54.0), (80.5, 54.0), (78.5, 57.5)), "F22": ((77.0, 54.0), (80.5, 54.0), (78.5, 57.5)),
            "F8": ((77.0, 53.5), (81.0, 53.5), (78.5, 57.5)), "F4": ((75.5, 53.5), (81.5, 53.5), (78.5, 57.5))}
TONES = (1.0, 0.6)
SS = 8                              # вставка рисуется в 8 раз крупнее k=4 и потом уменьшается (без лесенки)


def face_mask(files, body, head, look):
    """Лицо классики: пиксели слоя головы цветами кожи тела внутри эллипса по точкам лица, мелкие дыры (глаза, рот)
    залиты. Цвета кожи - только из глубины тела (контур тела теми же индексами обводит и волосы - вся голова
    становилась «дырой»), и не реже 2% глубины."""
    hi = db.load_indices(files[head])
    bi = db.load_indices(files[body])
    deep = cv2.erode((bi != 0).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    idx, cnt = np.unique(bi[deep], return_counts=True)
    skin = idx[(cnt >= 0.02 * deep.sum()) & (idx != 0)]
    (lx, ly), (rx, ry), (mx, my) = HEAD_PTS[look]
    cx, ey = (lx + rx) / 2.0, (ly + ry) / 2.0
    top, bot = ey - 2.5, my + 3.0
    hw = 0.75 * (rx - lx) + 1.5
    yy, xx = np.mgrid[0:hi.shape[0], 0:hi.shape[1]] + 0.5
    ell = ((xx - cx) / hw) ** 2 + ((yy - (top + bot) / 2.0) / ((bot - top) / 2.0)) ** 2 <= 1.0
    m = np.isin(hi, skin) & (hi != 0) & ell
    n, lab, st, _c = cv2.connectedComponentsWithStats((~m & ell).astype(np.uint8), connectivity=4)
    for i in range(1, n):
        if st[i, cv2.CC_STAT_AREA] <= 8:
            m |= lab == i
    n, lab = cv2.connectedComponents(m.astype(np.uint8), connectivity=4)
    keep = {lab[int(y) + dy, int(x) + dx] for x, y in HEAD_PTS[look] for dy in (-1, 0, 1) for dx in (-1, 0, 1)} - {0}
    return np.isin(lab, list(keep)) & (hi != 0)


def warp_face(m, look):
    """Лицо героини -> холст k=4 RGB (float), аффинно по трём точкам; рисуется в SS раз крупнее."""
    ref, _n = fp.face_ref(m)
    s = ref.width / 512.0
    src = np.float32([(x * s, y * s) for x, y in HEROINE_PTS[m]])
    dst = np.float32([(x * dp.K * SS, y * dp.K * SS) for x, y in HEAD_PTS[look]])
    x0, y0, x1, y1 = fp.box4()
    dst -= np.float32([x0 * SS, y0 * SS])
    A = cv2.getAffineTransform(src, dst)
    big = cv2.warpAffine(np.asarray(ref, np.float32), A, ((x1 - x0) * SS, (y1 - y0) * SS),
                         flags=cv2.INTER_AREA if False else cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    small = Image.fromarray(np.clip(big, 0, 255).astype(np.uint8)).resize((x1 - x0, y1 - y0), Image.LANCZOS)
    return np.asarray(small, np.float32)


def tone(rgb, wgt, target, amount):
    """Среднее и разброс каждого канала лица (вес wgt) - к коже классики target (N,3), разброс не раздуваем."""
    w = wgt.reshape(-1) > 0.5
    src = rgb.reshape(-1, 3)[w]
    ms, ss = src.mean(0), src.std(0) + 1e-3
    mo, so = target.mean(0), target.std(0) + 1e-3
    toned = (rgb - ms) * np.minimum(so / ss, 1.0) + mo
    return rgb + (toned - rgb) * amount


def main():
    os.makedirs(os.path.join(OUT, "layers"), exist_ok=True)
    files, pal = db.sprite_files(), db.game_palette()
    x0, y0, x1, y1 = fp.box4()
    rows = []
    for m, look in fp.CAST_LOOK:
        body = "%s__%d__%s_NUDE" % (dp.RACE, dp.BODY, look)
        head = "%s__%d__HEAD_%s" % (dp.RACE, dp.HEAD, look)
        b2head = np.asarray(fp.b2_canvas(files, pal, [head]), np.float32)
        b2body = fp.b2_canvas(files, pal, [body])
        fm = face_mask(files, body, head, look)
        f4 = ws.sil4(fm)[y0:y1, x0:x1]
        sil = ws.sil4(dp.layer_mask(files, head))
        face = warp_face(m, look)
        skin_px = b2head[y0:y1, x0:x1, :3][(f4 > 0.9)]
        cl = dp.classic(files, pal, [body, head]).resize((db.W * dp.K, db.H * dp.K), Image.NEAREST)
        ref, _n = fp.face_ref(m)
        tiles = [ref, cl.crop((x0, y0, x1, y1)), fp.b2_canvas(files, pal, [body, head]).crop((x0, y0, x1, y1))]
        for t in TONES:
            rgb = tone(face, f4, skin_px, t)
            out = b2head.copy()
            reg = out[y0:y1, x0:x1, :3]
            out[y0:y1, x0:x1, :3] = reg * (1 - f4[..., None]) + rgb * f4[..., None]
            out[..., 3] = sil * 255
            lay = Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8), "RGBA")
            lay.save(os.path.join(OUT, "layers", "%s_t%02d.png" % (head.lower(), int(t * 10))))
            doll = b2body.copy()
            doll.alpha_composite(lay)
            tiles.append(doll.crop((x0, y0, x1, y1)))
        rows.append(("%s -> %s" % (m, look), tiles))
        print(m, look, "лицо классики %d пикс." % int(fm.sum()), flush=True)
    fp.SEEDS = (0,)                                 # лист пилота на два столбца (по TONES), подписи - свои
    sh = fp.sheet(rows)
    d = ImageDraw.Draw(sh)
    S = (x1 - x0) * 3
    for i, t in enumerate(TONES):
        d.rectangle((S * (3 + i), 0, S * (4 + i), 20), fill=(24, 25, 30))
        d.text((S * (3 + i) + 6, 5), "paste, skin tone %.1f" % t, fill=(230, 230, 230))
    sh.save(os.path.join(OUT, "sheet.png"))
    print("готово:", os.path.join(OUT, "sheet.png"))


if __name__ == "__main__":
    main()
