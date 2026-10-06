r"""Проба первого задания пилота карт «тротуар ROADS с бордюрами» (sidewalk_job1): сборка кадров и лист приёмки.

Модель здесь не грузится - картинку материала рисует sidewalk_render.py (только через очередь gpuq). Этот скрипт из
её ответа собирает кадры ROADS 0, 0.v1..v3, 1, 2, 7 и показывает их на настоящем перекрёстке и поле 9 x 9.

Материал (уточнение Vitali 07.10): «ровное крапчатое серое покрытие тротуара» - материал и тон из классики, мелкая
ненаправленная фактура, без плиточной кладки, кирпичей, борозд и выпуклости клетки.

Сборка (build):
  1. ответ модели - квадрат вида сверху; из него четыре непересекающихся участка, каждый сложен в строго
     периодическую клетку окном cos^2 (probe_floor.periodic) - стык клетки с её копиями без шва;
  2. каждая клетка делится на зерно (высокие частоты) и износ (низкие, размытие --sigma-low);
     зерно всех вариантов приводится к ОДНОМУ разбросу яркости, износ ослабляется одним множителем до
     --wear-std (и не больше --wear-max) - одинаковый тон и масштаб фактуры, различия только в слабых пятнах;
     общий тон - средний цвет классики ROADS:0; зерно и износ - только по яркости, оттенок классики;
  3. клетка 0 -> 0.png и поверхность тротуара в 1, 2, 7 (совпадает с ROADS:0), клетки 1..3 -> 0.v1..v3;
  4. полоса бордюра - в развёртке клетки: у 1 по u, у 2 по v, у 7 по max(u, v), от U0 до края; U0 - доля
     тротуара в кадре классики (168 из 256 пикселей ромба = 0.656). Край - прямая, покрытие пикселя x4 по 16
     подточкам (сглаживание без лесенки). Тон поперёк полосы - профиль классики своего кадра (рампа 15), зерно
     то же, ослабленное;
  5. альфа - силуэт классики x4 без сглаживания (стык ромбов точный, R-005).
  --synthetic: вместо ответа модели - процедурный шум (проверка сборки и листа без видеокарты); лист помечен.

Лист (sheet): кадры, перекрёсток STR_ERIDIAN_TERROR_139 (pilot2_job_sheet.CORNER_AT) и поле 9 x 9 с вариантами
раскладкой движка (ground_field - порт groundFrameFor) - классика | нынешний HD | новое, в одном масштабе.
Числа (L*, разброс вариантов, направленность зерна) - диагностика, решает лист.

    py -3.13 tools/hdart/sidewalk_probe.py build --raw census/maps/pilot2/probe_sidewalk/raw_s7101.png
    py -3.13 tools/hdart/sidewalk_probe.py build --synthetic
    py -3.13 tools/hdart/sidewalk_probe.py sheet --tag s7101

Кладёт в census/maps/pilot2/probe_sidewalk/<метка>/: ROADS.PCK/<кадр>.png, uv_<j>.png, build.json, sheet.png.
В пак НЕ идёт.
"""
import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ground_field as gf             # noqa: E402
import pilot2_job_sheet as js         # noqa: E402

ROOT = js.ROOT
OUT = ROOT / "census" / "maps" / "pilot2" / "probe_sidewalk"
ENC = "utf-8-sig"
K = js.K
TOP = (16, 24)                        # верхняя вершина ромба пола в кадре 32x40
SIDE = 1024                           # ответ модели приводится к этому размеру
CENTRES = ((256, 256), (768, 256), (256, 768), (768, 768))   # участки вариантов 0, v1, v2, v3 - не пересекаются
NAMES = ("0", "0.v1", "0.v2", "0.v3")
KERB_FRAMES = (1, 2, 7)
LUMA = np.array([0.299, 0.587, 0.114], np.float32)


# ------------------------------------------------------------------ геометрия клетки

def screen_to_uv(sx, sy):
    """Точка кадра 32x40 (k=1) -> оси клетки u, v (ромб пола - квадрат [0, 1)^2)."""
    return (sx - TOP[0]) / 32.0 + (sy - TOP[1]) / 16.0, -(sx - TOP[0]) / 32.0 + (sy - TOP[1]) / 16.0


def kerb_t(f, u, v):
    """Координата поперёк бордюра: у 1 - u, у 2 - v, у угла 7 - max(u, v)."""
    return {1: u, 2: v, 7: np.maximum(u, v)}[f]


def frame_uv(sub=1):
    """u, v центров (sub=1) или sub x sub подточек каждого пикселя кадра x4: массивы (FH, FW[, sub*sub])."""
    o = (np.arange(sub) + 0.5) / sub
    oy, ox = np.meshgrid(o, o, indexing="ij")
    py, px = np.mgrid[0:js.FH, 0:js.FW].astype(np.float32)
    sx = (px[..., None] + ox.ravel()) / K
    sy = (py[..., None] + oy.ravel()) / K
    u, v = screen_to_uv(sx, sy)
    return (u[..., 0], v[..., 0]) if sub == 1 else (u, v)


def kerb_start():
    """U0 по классике: доля тротуара (рампа 0) в ромбе кадров 1 и 2 - полоса бордюра идёт от U0 до края."""
    out = {}
    for f in (1, 2, 7):
        idx, _ = js.gm.classic("ROADS", f)
        fl = idx[24:]
        walk, total = int(((fl > 0) & (fl < 16)).sum()), int((fl > 0).sum())
        out[f] = (walk, total)
    w1, t1 = out[1]
    w2, t2 = out[2]
    if w1 != w2 or t1 != t2:
        raise SystemExit("ширина бордюра 1 и 2 у классики разная: %s %s - полосу задавать по кадру" % (out[1], out[2]))
    u0 = w1 / t1
    w7, t7 = out[7]
    # у угла тротуар - квадрат U0 x U0: проверка, что полосы правда прямые и одной ширины
    if abs(w7 / t7 - u0 * u0) > 0.03:
        raise SystemExit("угол 7: тротуар %.3f против U0^2 %.3f - полосы не прямые, модель полосы не годится"
                         % (w7 / t7, u0 * u0))
    return u0, out


def kerb_profile(f, u0, nb=24):
    """Средний цвет рампы 15 классики поперёк полосы бордюра кадра f: nb ячеек на [u0, 1], сглажено."""
    i4 = js.classic_idx("ROADS", f)
    u, v = frame_uv(1)
    t = kerb_t(f, u, v)
    m = (i4 >= 240) & (t >= u0) & (t < 1.0)
    b = np.clip(((t[m] - u0) / (1 - u0) * nb).astype(int), 0, nb - 1)
    rgb = js.PAL[i4[m]].astype(np.float64)
    prof = np.zeros((nb, 3))
    cnt = np.bincount(b, minlength=nb).astype(float)
    for c in range(3):
        prof[:, c] = np.bincount(b, rgb[:, c], minlength=nb)
    have = cnt > 0
    if not have.any():
        raise SystemExit("у кадра %d нет пикселей бордюра в полосе" % f)
    prof[have] /= cnt[have, None]
    xs = np.arange(nb)
    for c in range(3):
        prof[:, c] = np.interp(xs, xs[have], prof[have, c])
    k = np.exp(-0.5 * (np.arange(-2, 3) / 1.0) ** 2)
    k /= k.sum()
    pad = np.pad(prof, ((2, 2), (0, 0)), mode="edge")
    return np.stack([np.convolve(pad[:, c], k, mode="valid") for c in range(3)], -1)


# ------------------------------------------------------------------ материал

def bilinear_wrap(arr, x, y):
    h, w = arr.shape[:2]
    x = x - 0.5
    y = y - 0.5
    x0, y0 = np.floor(x).astype(np.int64), np.floor(y).astype(np.int64)
    fx, fy = (x - x0)[..., None], (y - y0)[..., None]
    xa, xb, ya, yb = x0 % w, (x0 + 1) % w, y0 % h, (y0 + 1) % h
    a = arr[ya, xa] * (1 - fx) + arr[ya, xb] * fx
    b = arr[yb, xa] * (1 - fx) + arr[yb, xb] * fx
    return a * (1 - fy) + b * fy


def periodic(img, p, cx, cy):
    """Клетка p x p: окно cos^2 на 2 периода вокруг (cx, cy), сложенное по модулю (сумма окон ровно 1 - шва нет)."""
    t = np.arange(-p, p) + 0.5
    w = np.cos(math.pi * t / (2 * p)) ** 2
    blk = img[cy - p:cy + p, cx - p:cx + p] * (w[:, None] * w[None, :])[..., None]
    out = blk[:p, :p] + blk[:p, p:] + blk[p:, :p] + blk[p:, p:]
    return np.roll(out, (cy % p, cx % p), axis=(0, 1))


def blur_wrap(arr, sigma):
    fy = np.fft.fftfreq(arr.shape[0])[:, None]
    fx = np.fft.fftfreq(arr.shape[1])[None, :]
    g = np.exp(-2 * (math.pi * sigma) ** 2 * (fx * fx + fy * fy))
    if arr.ndim == 2:
        return np.real(np.fft.ifft2(np.fft.fft2(arr) * g))
    return np.real(np.fft.ifft2(np.fft.fft2(arr, axes=(0, 1)) * g[..., None], axes=(0, 1)))


def coherence(lum):
    """Направленность зерна: когерентность тензора структуры, 0 - ненаправленное, 1 - полосы."""
    gx = np.roll(lum, -1, 1) - np.roll(lum, 1, 1)
    gy = np.roll(lum, -1, 0) - np.roll(lum, 1, 0)
    jxx, jyy, jxy = (gx * gx).mean(), (gy * gy).mean(), (gx * gy).mean()
    return float(math.sqrt((jxx - jyy) ** 2 + 4 * jxy * jxy) / (jxx + jyy + 1e-9))


def classic_mean():
    idx, _ = js.gm.classic("ROADS", 0)
    px = js.PAL[idx[idx > 0]].astype(np.float32)
    return px.mean(0), float((px @ LUMA).std())


def synthetic(seed=1):
    """Процедурная замена ответа модели: мелкий крап + слабые пятна. Только для проверки сборки и листа."""
    rng = np.random.default_rng(seed)
    fine = blur_wrap(rng.normal(0, 1, (SIDE, SIDE)), 1.3)
    fine *= 18 / fine.std()
    spots = blur_wrap(rng.normal(0, 1, (SIDE, SIDE)), 40)
    spots *= 6 / spots.std()
    lum = 110 + fine + spots
    return np.clip(np.dstack([lum, lum, lum * 1.03]), 0, 255).astype(np.float32)


def make_cells(tex, p, sigma_low, grain_std, wear_std, wear_max, mean_rgb):
    """Четыре периодических клетки p x p: тон классики + зерно (один разброс) + износ (один множитель)."""
    cells, grains, wears, diag = [], [], [], {}
    for cx, cy in CENTRES:
        c = periodic(tex, p, cx, cy)
        lum = c @ LUMA
        low = blur_wrap(lum, sigma_low)
        grains.append(lum - low)
        wears.append(low - low.mean())
    g_raw = [float(g.std()) for g in grains]
    g_target = min(float(np.median(g_raw)), grain_std)
    w_raw = [float(w.std()) for w in wears]
    a = min(1.0, wear_std / max(max(w_raw), 1e-6))
    m_l = float(mean_rgb @ LUMA)
    for g, w in zip(grains, wears):
        g2 = g * (g_target / max(float(g.std()), 1e-6))
        w2 = np.clip(w * a, -wear_max, wear_max)
        lum = m_l + g2 + w2
        cells.append(np.clip(mean_rgb[None, None, :] * (lum / m_l)[..., None], 0, 255))
    diag.update(grain_raw=g_raw, grain_std=g_target, wear_raw=w_raw, wear_gain=a,
                coherence=[coherence(g) for g in grains])
    return cells, [g * (g_target / max(float(g.std()), 1e-6)) for g in grains], diag


def build_frames(cells, grain0, u0, kerb_grain, mean_rgb):
    """Кадры x4 RGBA: {"0", "0.v1".., "1", "2", "7"} - из клеток материала и полос бордюра."""
    p = cells[0].shape[0]
    u, v = frame_uv(1)
    su, sv = (u % 1.0) * p, (v % 1.0) * p
    out = {}
    for nm, c in zip(NAMES, cells):
        idx4 = js.classic_idx("ROADS", 0)
        rgb = bilinear_wrap(c, su, sv)
        out[nm] = np.dstack([np.clip(rgb, 0, 255), np.where(idx4 > 0, 255, 0)]).astype(np.uint8)
    walk = bilinear_wrap(cells[0], su, sv)
    g = bilinear_wrap(grain0[..., None], su, sv)[..., 0]
    m_l = float(mean_rgb @ LUMA)
    us, vs = frame_uv(4)
    for f in KERB_FRAMES:
        idx4 = js.classic_idx("ROADS", f)
        prof = kerb_profile(f, u0)
        t = np.clip(kerb_t(f, u, v), u0, 1 - 1e-6)
        x = (t - u0) / (1 - u0) * len(prof) - 0.5
        kc = np.stack([np.interp(x, np.arange(len(prof)), prof[:, ch]) for ch in range(3)], -1)
        kc = kc * (1 + kerb_grain * g / m_l)[..., None]     # зерно в той же доле яркости, что у тротуара
        cover = (kerb_t(f, us, vs) >= u0).mean(-1)[..., None]
        rgb = walk * (1 - cover) + kc * cover
        out[str(f)] = np.dstack([np.clip(rgb, 0, 255), np.where(idx4 > 0, 255, 0)]).astype(np.uint8)
    return out


def cmd_build(a):
    if a.synthetic:
        tag, tex = "_synthetic", synthetic()
        src = "синтетика (процедурный шум) - проверка сборки, не проба модели"
    else:
        raw = Path(a.raw)
        if not raw.exists():
            raise SystemExit("нет ответа модели %s - его рисует sidewalk_render.py через gpuq" % raw)
        tag = a.tag or raw.stem.replace("raw_", "")
        im = Image.open(raw).convert("RGB")
        tex = np.asarray(im.resize((SIDE, SIDE), Image.LANCZOS)).astype(np.float32)
        src = str(raw.relative_to(ROOT)) if raw.is_absolute() else str(raw)
    d = OUT / tag
    (d / "ROADS.PCK").mkdir(parents=True, exist_ok=True)
    mean_rgb, cl_std = classic_mean()
    u0, counts = kerb_start()
    grain_std = cl_std * a.grain
    cells, grains, diag = make_cells(tex, a.period, a.sigma_low, grain_std, a.wear_std, a.wear_max, mean_rgb)
    frames = build_frames(cells, grains[0], u0, a.kerb_grain, mean_rgb)
    for nm, fr in frames.items():
        Image.fromarray(fr, "RGBA").save(d / "ROADS.PCK" / (nm + ".png"))
    for j, c in enumerate(cells):
        Image.fromarray(c.astype(np.uint8), "RGB").save(d / ("uv_%d.png" % j))
    Ls = {nm: js.light(frames[nm]) for nm in NAMES}
    walk_l = {f: js.walk_light(f)[0] for f in KERB_FRAMES}
    new_walk = {}
    for f in KERB_FRAMES:
        i4 = js.classic_idx("ROADS", f)
        m = (i4 > 0) & (i4 < 16)
        m[:96] = False
        new_walk[f] = float(js.lab(frames[str(f)][..., :3][m]).mean(0)[0])
    info = dict(source=src, tag=tag, period=a.period, sigma_low=a.sigma_low, grain=a.grain, wear_std=a.wear_std,
                wear_max=a.wear_max, kerb_grain=a.kerb_grain, u0=u0, kerb_counts={str(k): v for k, v in counts.items()},
                classic_mean_rgb=[round(float(x), 2) for x in mean_rgb], classic_grain_std=round(cl_std, 2),
                L_classic=round(js.light(js.rgba_classic(js.classic_idx("ROADS", 0))), 2),
                L_variants={k: round(v, 2) for k, v in Ls.items()},
                L_walk_in_kerb={str(f): [round(walk_l[f], 2), round(new_walk[f], 2)] for f in KERB_FRAMES},
                **{k: ([round(x, 3) for x in v] if isinstance(v, list) else round(v, 3)) for k, v in diag.items()})
    (d / "build.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding=ENC)
    print("кадры: %s" % (d / "ROADS.PCK"))
    print("U0 %.4f (тротуар %s), тон классики %s, зерно классики %.2f" % (u0, counts, info["classic_mean_rgb"], cl_std))
    print("L* классики %.1f; вариантов %s" % (info["L_classic"], info["L_variants"]))
    print("тротуар внутри бордюрных кадров L* (классика, новое): %s" % info["L_walk_in_kerb"])
    print("зерно: сырое %s -> %.2f; износ: сырой %s, множитель %.3f; направленность зерна %s"
          % (info["grain_raw"], info["grain_std"], info["wear_raw"], info["wear_gain"], info["coherence"]))


# ------------------------------------------------------------------ лист приёмки

def load_frames(tag):
    d = OUT / tag / "ROADS.PCK"
    if not d.exists():
        raise SystemExit("нет кадров %s - сначала build" % d)
    return {p.stem: np.asarray(Image.open(p).convert("RGBA")) for p in d.glob("*.png")}


def cmd_sheet(a):
    new = load_frames(a.tag)
    info = json.loads((OUT / a.tag / "build.json").read_text(encoding=ENC))
    synth = a.tag.startswith("_synthetic")
    f_t = ImageFont.truetype(js.FONT_B, 24)
    f_h = ImageFont.truetype(js.FONT_B, 17)
    f_s = ImageFont.truetype(js.FONT, 15)
    WIDTH = 2400
    sheet = Image.new("RGB", (WIDTH, 5200), js.BG)
    d = ImageDraw.Draw(sheet)

    def para(t, y, fill=(240, 240, 240), step=20):
        line = ""
        for w in t.split(" "):
            if d.textlength(line + " " + w, font=f_s) > WIDTH - 40:
                d.text((14, y), line, font=f_s, fill=fill)
                y += step
                line = w
            else:
                line = (line + " " + w).strip()
        d.text((14, y), line, font=f_s, fill=fill)
        return y + step

    y = 10
    d.text((14, y), "Проба: тротуар ROADS с бордюрами (sidewalk_job1), метка %s - классика | нынешний HD | новое, "
           "один масштаб в каждой строке" % a.tag, font=f_t, fill=(255, 255, 255))
    y += 36
    if synth:
        d.rectangle((10, y, WIDTH - 10, y + 30), fill=(150, 20, 20))
        d.text((18, y + 5), "СИНТЕТИКА: процедурный шум вместо ответа модели - проверка сборки и листа, не проба",
               font=f_h, fill=(255, 255, 255))
        y += 40
    y = para("Материал: ровное крапчатое серое покрытие тротуара, тон классики. Источник: %s. Классика x4 - боевая "
             "палитра delicious_regular, тень 0; нынешний HD - мод hd в установке Пираток (его читает игра)."
             % info["source"], y)
    y += 6

    # 1. кадры
    d.text((14, y), "1. Кадры (пол - нижние 64 строки x4, показ x2)", font=f_h, fill=(255, 255, 0))
    y += 26
    crop = (0, 96, 128, 160)
    cols = [("0", "тротуар 0"), ("1", "бордюр 1"), ("2", "бордюр 2"), ("7", "угол 7"),
            ("0.v1", "вариант 0.v1"), ("0.v2", "вариант 0.v2"), ("0.v3", "вариант 0.v3")]
    cw = 290
    for j, lbl in enumerate(("классика x4", "HD сейчас", "новое")):
        d.text((14, y + 22 + j * 136 + 54), lbl, font=f_s, fill=(255, 255, 255))
    for i, (nm, lbl) in enumerate(cols):
        x0 = 130 + i * cw
        d.text((x0, y), lbl, font=f_s, fill=(255, 255, 255))
        base = int(nm.split(".")[0])
        if "." not in nm:
            js.paste(sheet, js.rgba_classic(js.classic_idx("ROADS", base)), (x0, y + 22), crop, 2)
        js.paste(sheet, js.rgba_hd("ROADS", nm), (x0, y + 22 + 136), crop, 2)
        js.paste(sheet, new[nm], (x0, y + 22 + 272), crop, 2)
    y += 22 + 3 * 136 + 8

    # 2. перекрёсток
    bt = js.mt.Battle(js.CORNER)
    seed = gf.battle_seed(bt.X, bt.Y, bt.Z, bt.blocks)
    cx, cy, n = js.CORNER_AT
    corner = js.Blocks.battle_floor(js.CORNER, cx, cy, n)
    old_found = [js.rgba_hd("ROADS", nm) for nm in NAMES]
    new_found = [new[nm] for nm in NAMES]

    def new_pick(s, f, x, yy):
        if (s, f) == ("ROADS", 0):
            return gf.frame_for(new_found, cx + x, cy + yy, 0, seed, K)
        if s == "ROADS" and str(f) in new:
            return new[str(f)]
        return js.rgba_hd(s, str(f))

    d.text((14, y), "2. Перекрёсток: бой STR_ERIDIAN_TERROR_139, угол URBAN02 у тротуара соседнего блока (клетки x %d..%d, "
           "y %d..%d, только пол), x4 в натуральную величину. Асфальт 9 и разметка 11 - старые (следующее задание)"
           % (cx, cx + n - 1, cy, cy + n - 1), font=f_h, fill=(255, 255, 0))
    y += 26
    cl, *_ = js.assemble(corner, lambda s, f, x, yy: js.rgba_classic(js.classic_idx(s, f)))
    old, *_ = js.assemble(corner, js.ground_pick(seed, cx, cy, old_found))
    nw, *_ = js.assemble(corner, new_pick)
    H, W = cl.shape[:2]
    top = 96
    gap = 16
    for i, (im, lbl) in enumerate(((cl, "классика x4"), (old, "HD сейчас"), (nw, "новое"))):
        x0 = 14 + i * (W + gap)
        d.text((x0, y), lbl, font=f_s, fill=(255, 255, 255))
        js.paste(sheet, im, (x0, y + 20), (0, top, W, H))
    y += 20 + (H - top) + 12

    # 3. поле 9 x 9
    N = 9
    fx0, fy0 = cx - 4, cy - 4
    fields = [gf.field([js.rgba_classic(js.classic_idx("ROADS", 0))], n=N, seed=seed, x0=fx0, y0=fy0, k=K, bg=js.BG)[0],
              gf.field(old_found, n=N, seed=seed, x0=fx0, y0=fy0, k=K, bg=js.BG)[0],
              gf.field(new_found, n=N, seed=seed, x0=fx0, y0=fy0, k=K, bg=js.BG)[0]]
    fh, fw = fields[0].shape[:2]
    d.text((14, y), "3. Поле 9 x 9 одного тротуара ROADS:0 с вариантами раскладкой движка (клетки x %d..%d, y %d..%d того же "
           "боя, зерно узора %d) - уменьшено вдвое, одинаково у всех трёх" % (fx0, fx0 + N - 1, fy0, fy0 + N - 1, seed),
           font=f_h, fill=(255, 255, 0))
    y += 26
    half_w = fw // 2
    for i, (im, lbl) in enumerate(zip(fields, ("классика", "HD сейчас", "новое"))):
        x0 = 14 + i * (half_w + gap)
        d.text((x0, y), lbl, font=f_s, fill=(255, 255, 255))
        h = Image.fromarray(im).crop((0, top, fw, fh))
        sheet.paste(h.resize((h.width // 2, h.height // 2), Image.LANCZOS), (x0, y + 20))
    y += 20 + (fh - top) // 2 + 12
    cwid, chei = 760, 460
    box = (fw // 2 - cwid // 2, (fh + top) // 2 - chei // 2, fw // 2 + cwid // 2, (fh + top) // 2 + chei // 2)
    d.text((14, y), "   середина того же поля x4 в натуральную величину", font=f_h, fill=(255, 255, 0))
    y += 26
    for i, (im, lbl) in enumerate(zip(fields, ("классика", "HD сейчас", "новое"))):
        x0 = 14 + i * (cwid + gap)
        d.text((x0, y), lbl, font=f_s, fill=(255, 255, 255))
        sheet.paste(Image.fromarray(im).crop(box).convert("RGB"), (x0, y + 20))
    y += 20 + chei + 12

    # 4. числа
    d.text((14, y), "4. Числа - диагностика, решает лист", font=f_h, fill=(255, 255, 0))
    y += 26
    old_L = {nm: js.light(fr) for nm, fr in zip(NAMES, old_found)}
    for t in (
        "L* пола: классика %.1f; HD сейчас %s; новое %s." % (
            info["L_classic"], ", ".join("%s %.1f" % kv for kv in old_L.items()),
            ", ".join("%s %.1f" % kv for kv in info["L_variants"].items())),
        "Тротуар внутри бордюрных кадров, L* (классика -> новое): %s; в нынешнем HD 17-18." % "; ".join(
            "%s: %.1f -> %.1f" % (k, v[0], v[1]) for k, v in info["L_walk_in_kerb"].items()),
        "Полоса бордюра: от U0 = %.4f до края клетки (у классики тротуар %s пикселей ромба); край - прямая, "
        "сглаживание по 16 подточкам пикселя x4." % (info["u0"], info["kerb_counts"]["1"]),
        "Зерно (разброс яркости по вариантам, сырое): %s -> общее %.2f (у классики %.2f); износ: сырой %s, множитель %.3f, "
        "не больше %.1f; направленность зерна (0 - нет, 1 - полосы): %s." % (
            info["grain_raw"], info["grain_std"], info["classic_grain_std"], info["wear_raw"], info["wear_gain"],
            info["wear_max"], info["coherence"]),
    ):
        y = para(t, y)
    sheet = sheet.crop((0, 0, WIDTH, y + 8))
    out = OUT / a.tag / "sheet.png"
    sheet.save(out)
    print("лист: %s %s" % (out, sheet.size))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="кадры из ответа модели (или --synthetic)")
    b.add_argument("--raw", default="", help="ответ sidewalk_render.py")
    b.add_argument("--tag", default="", help="метка папки; по умолчанию - имя ответа без raw_")
    b.add_argument("--synthetic", action="store_true", help="процедурный шум вместо ответа - проверка без видеокарты")
    b.add_argument("--period", type=int, default=160, help="сторона клетки в пикселях квадрата 1024 (6.4 клетки)")
    b.add_argument("--sigma-low", type=float, default=12.0, help="граница зерна и износа, пикс. квадрата")
    b.add_argument("--grain", type=float, default=1.0, help="потолок разброса зерна в долях разброса классики")
    b.add_argument("--wear-std", type=float, default=1.5, help="разброс износа по яркости, единиц 0..255")
    b.add_argument("--wear-max", type=float, default=4.0, help="предел отклонения износа")
    b.add_argument("--kerb-grain", type=float, default=0.5, help="доля зерна тротуара на камне бордюра")
    s = sub.add_parser("sheet", help="лист приёмки: перекрёсток и поле 9x9, классика | HD сейчас | новое")
    s.add_argument("--tag", required=True)
    a = ap.parse_args()
    if a.cmd == "build":
        if not a.synthetic and not a.raw:
            raise SystemExit("нужен --raw или --synthetic")
        cmd_build(a)
    else:
        cmd_sheet(a)


if __name__ == "__main__":
    main()
