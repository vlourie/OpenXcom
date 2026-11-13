"""Сквозные стены: проём по маске оригинала поверх ответа WALL_RENDER_V1 (THRU_CHECK_V1).

Модель закрывает сквозные проёмы (R-284: open_raw 0.94-1.0 и с подсказкой «no glass»), а перо альфы
wall_section.sil4_frame (R-289) выносит край наружу на ЛЮБОМ вертикальном переходе - и на косяке окна,
и на щели забора: проём в 1 пиксель базы закрывается самим пером (C6p URBITS:8 open_fin 0.91).

Здесь - технический путь, без модели: тот же ответ (raw.png), та же вырезка wall_section, но
  1) альфа у проёма - силуэт оригинала x4 без сдвига пера (sil4): форма проёма - геометрия оригинала;
     перо наружу остаётся только на внешних вертикалях, вдали от проёмов (стык кадров, R-289);
  2) кромка тела у проёма, окрашенная заливкой, которой модель закрыла проём (стекло, стена, подложка),
     перекрашивается из чистого тела рядом (inpaint). Если заливка неотличима от тела по цвету
     (dE меньше HOLE_SAME), чистить нечего: тело и так своего цвета.
Модель не грузится: --recut по raw.png, скопированным в новую папку (V1 рядом не трогается).

  wall_thru.py --src <папка wall_section> --out <новая папка> --terrain ... (ключи wall_section)
  wall_thru.py --key --out <папка> --terrain ... (ключи wall_section) - рендер с проёмом пурпурным на входе;
      грузит модель - только через gpuq; с --dry-run - только input.png
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import numpy as np                  # noqa: E402
import cv2                          # noqa: E402
from PIL import Image               # noqa: E402
import wall_section as ws           # noqa: E402

NEAR = 7          # пикселей x4: окрестность проёма, где перо наружу не действует
RING = 4          # пикселей x4: кромка тела у проёма, где ищутся пятна заливки
HOLE_SAME = 10.0  # dE: заливка проёма цветом тела - чистить нечего
STAIN_DE = 22.0   # dE: пиксель кромки ближе к заливке, чем к телу, и не дальше этого от заливки
# наращивание пятна по цвету соседа (M2) проверено 08.10 и отвергнуто: inpaint из тела мажет переплёт
# кирпичом и объедает раму - переплёт, вместо которого модель нарисовала стекло, чисткой не вернуть
STAIN_MAX = 0.6   # доля кромки: больше - прутья сами цвета заливки, не чистим, а пишем в отчёт

# --key: проём на ВХОДЕ модели залит чистым пурпурным, промпт велит его держать - модель рисует только
# непрозрачную часть, а переплёт, который она иначе заменяет стеклом, остаётся её рисунком
KEY = (255, 0, 255)
KEY_NOTE = (" Areas of <image1> filled with flat pure magenta are see-through openings in the walls: keep every "
            "magenta area flat pure magenta with exactly the same shape and size; draw nothing inside them - no "
            "glass, no bars, no wall; draw every bar, mullion and frame between them as in <image1>.")

_sil4_frame = ws.sil4_frame
_assemble = ws.assemble
_compose = ws.compose
_model_input = ws.model_input
_seen = {}
PAD = 3


def disk(r):
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def up4(m):
    return np.repeat(np.repeat(m, 4, 0), 4, 1)


def sil4_frame_open(mask):
    f = _sil4_frame(mask)
    op = ws.openings(mask)
    if not op.any():
        return f
    near = cv2.dilate(up4(op).astype(np.uint8), disk(NEAR)).astype(np.float32)
    w = np.clip(cv2.GaussianBlur(near, (0, 0), 2.0), 0.0, 1.0)
    return f * (1.0 - w) + ws.sil4(mask) * w


def lab(rgb):
    return cv2.cvtColor(np.clip(rgb, 0, 255).astype(np.uint8)[None], cv2.COLOR_RGB2LAB)[0].astype(np.float32)


def clean(img, own):
    """img - RGBA float 160x128 (цвет ответа, альфа силуэта); own - маска оригинала k=1."""
    op = ws.openings(own)
    if not op.any():
        return img, None
    op4 = up4(op)
    op4i = cv2.erode(op4.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    hole = op4i if op4i.sum() >= 8 else op4
    body = img[..., 3] > 127
    near = cv2.dilate(op4.astype(np.uint8), disk(RING)) > 0
    ring = body & near
    if ring.sum() < 8:
        return img, None
    rgb = img[..., :3]
    lb = lab(rgb.reshape(-1, 3)).reshape(rgb.shape)
    hole_c = np.median(lb[hole], 0)
    deep = body & ~(cv2.dilate(op4.astype(np.uint8), disk(RING + 4)) > 0)
    body_c = np.median(lb[deep if deep.sum() >= 32 else ring], 0)
    d_hb = float(np.linalg.norm(hole_c - body_c))
    rep = dict(ring=int(ring.sum()), hole_vs_body=round(d_hb, 1), stain=0.0, cleaned=False, flag="")
    if d_hb < HOLE_SAME:
        rep["flag"] = "проём залит цветом тела"
        return img, rep
    dF = np.linalg.norm(lb - hole_c, axis=-1)
    dB = np.linalg.norm(lb - body_c, axis=-1)
    stain = ring & (dF < dB) & (dF < STAIN_DE)
    share = float(stain.sum() / ring.sum())
    rep["stain"] = round(share, 3)
    if share > STAIN_MAX:
        rep["flag"] = "кромка цвета заливки - прутья не отделены"
        return img, rep
    if not stain.any():
        return img, rep
    m = stain | (~body & (cv2.dilate(stain.astype(np.uint8), disk(6)) > 0)) | op4
    rgb8 = np.clip(rgb, 0, 255).astype(np.uint8)
    fixed = cv2.inpaint(rgb8, m.astype(np.uint8), 3, cv2.INPAINT_TELEA).astype(np.float32)
    out = img.copy()
    out[..., :3] = np.where(stain[..., None], fixed, rgb)
    rep["cleaned"] = True
    return out, rep


def assemble_open(mem, at, size, lab_, cut, band):
    out, info, refs, lab4 = _assemble(mem, at, size, lab_, cut, band)
    owns = {}
    for m in mem:
        if m["role"] == "paint":
            owns.setdefault((m["set"].upper(), m["frame"]), np.asarray(m["full"])[..., 3] > 0)
    for f in list(out):
        im = np.asarray(out[f], np.float32)
        new, rep = clean(im, owns[f])
        out[f] = Image.fromarray(np.clip(np.rint(new), 0, 255).astype(np.uint8), "RGBA")
        if rep is not None:
            info[f]["thru"] = rep
    return out, info, refs, lab4


def compose_rec(mem, at, size, imgs=None, k=1):
    im = _compose(mem, at, size, imgs, k)
    if imgs is None and k == 1 and "whole" not in _seen:
        _seen.update(mem=mem, at=at, whole=im)
    return im


def key_mask(frame):
    """Проёмы своих кадров (ws.openings по спрайту, как он лёг в участок), где участок прозрачен,
    в координатах входа: участок обрезан по габариту с полем PAD, как в wall_section.main."""
    whole, mem, at = _seen["whole"], _seen["mem"], _seen["at"]
    a = np.asarray(whole)[..., 3] > 0
    key = np.zeros_like(a)
    for i, m in enumerate(mem):
        if m["role"] != "paint" or m["spr"] is None:
            continue
        op = ws.openings(np.asarray(m["spr"])[..., 3] > 0)
        x, y = at[i]
        key[y:y + op.shape[0], x:x + op.shape[1]] |= op
    key &= ~a
    bb = whole.split()[3].getbbox()
    box = (bb[0] - PAD, bb[1] - PAD, bb[2] + PAD, bb[3] + PAD)
    out = np.asarray(Image.fromarray(key.astype(np.uint8) * 255).crop(box)) > 0
    if out.shape != (frame.height, frame.width):
        raise SystemExit("маска проёма не совпала с входом: %s против %s" % (out.shape, frame.size))
    return out


def model_input_key(frame, zoom):
    inp = _model_input(frame, zoom)
    key = key_mask(frame)
    if "printed" not in _seen:
        _seen["printed"] = True
        print("  проём на входе залит пурпурным: %d пикс k=1" % int(key.sum()), flush=True)
    if not key.any():
        return inp
    arr = np.asarray(inp).copy()
    arr[np.repeat(np.repeat(key, zoom, 0), zoom, 1)] = KEY
    return Image.fromarray(arr)


def main():
    global PAD
    argv = sys.argv[1:]
    if "--pad" in argv:
        PAD = int(argv[argv.index("--pad") + 1])
    ws.sil4_frame = sil4_frame_open
    ws.assemble = assemble_open
    if "--key" in argv:
        argv.remove("--key")
        ws.compose = compose_rec
        ws.model_input = model_input_key
        ws.STYLE = ws.STYLE + KEY_NOTE
        if "--src" not in argv:
            # рендер: модель грузится - только через очередь видеокарты (tools/gpu_scripts.txt)
            sys.argv = [sys.argv[0]] + argv
            ws.main()
            return
    if "--src" not in argv or "--out" not in argv:
        raise SystemExit(__doc__)
    i = argv.index("--src")
    src = argv[i + 1]
    del argv[i:i + 2]
    out = argv[argv.index("--out") + 1]
    if os.path.abspath(out) == os.path.abspath(src):
        raise SystemExit("--out должен быть новой папкой: V1 в --src не перезаписывается")
    seeds = argv[argv.index("--seeds") + 1].split(",") if "--seeds" in argv else ["2711"]
    os.makedirs(out, exist_ok=True)
    if os.path.exists(os.path.join(src, "input.png")):
        shutil.copy2(os.path.join(src, "input.png"), os.path.join(out, "input.png"))
    for s in seeds:
        raw = os.path.join(src, "s" + s, "raw.png")
        if not os.path.exists(raw):
            raise SystemExit("нет ответа %s - модель здесь не грузится (R-127)" % raw)
        os.makedirs(os.path.join(out, "s" + s), exist_ok=True)
        shutil.copy2(raw, os.path.join(out, "s" + s, "raw.png"))
    sys.argv = [sys.argv[0]] + argv + ["--recut"]
    ws.main()


if __name__ == "__main__":
    main()
