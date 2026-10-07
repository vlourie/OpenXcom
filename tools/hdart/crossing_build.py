r"""Сборка связанного участка перекрёстка ROADS 0-13 из одного ответа модели, без новой генерации.

Зачем (FAIL визуальной приёмки 07.10): проба тротуара заменила кадры 0, 1, 2, 7, а асфальт 9, разметка 10-12,
решётка 13 и бордюры 3-6, 8 остались старыми. В игровом кадре это сетка клеток асфальта, заплатки другой фактуры под
разметкой, разметка то широкая, то ниткой. Разбор по пикселям (crossing_check.py по дампу движка) - в отчёте.

Здесь собирается ВЕСЬ материал участка сразу:
  тротуар  - клетки вариантов из ответа модели (sidewalk_probe.make_cells), тон и зерно классики ROADS:0;
  асфальт  - те же клетки из другого места того же ответа (транспонированный ответ), тон и зерно классики ROADS:9;
             ОДНИ И ТЕ ЖЕ клетки во всех кадрах 9-13, значит асфальт под разметкой и решёткой - тот же материал;
  бордюры  - кадры 1-8: тротуар своего варианта плюс полосы камня по сторонам KERB_SIDES (crossing_check):
             +u и +v - передний бордюр 88/256, -u и -v - задний 41/256; тон поперёк полосы - профиль классики
             своей стороны (кадр 1, 2, 3 или 4), фактура камня - зерно и износ тротуара сильнее; у угла сторона
             с большей глубиной (стык по линии равной глубины), покрытие пикселя x4 по 16 подточкам;
  разметка - кадры 10-12: полоса классики вдоль края -u (10), -v (11) или обоих (12): u (v) от 1/32 до 5/32 -
             ровно там, где лежат пиксели индекса 240 классики, по всей длине края; цвет - индекс 240; кладётся
             поверх асфальта своего варианта покрытием по 16 подточкам, асфальт под ней не меняется;
  решётка 13 - решётка стока у бордюра (по пикселям классики: пластина с прутьями индексов 11-13 вдоль оси u,
             тёмная кромка 251-252 по краям -u и +v): пластина и кромка - геометрия классики, прутья - два тона
             (светлый пруток, тёмная прорезь) по фазе шага, найденного по классике; поверх того же асфальта.
             Прежняя сборка размывала пиксели 11-13 гауссом в пятно - конструкция терялась (чистый кадр 07.10).
У каждого кадра 4 картинки (<N>.png, <N>.v1-v3.png) - вариант j у всех кадров из одних и тех же клеток j. Движок
выбирает вариант по непрерывному полю (groundFrameFor: целиком или попиксельное смешение соседних), поэтому
соседние клетки, любые кадры участка, показывают одно непрерывное поле материала - сводить края к варианту 0 не
надо. Альфа - силуэт классики x4 плюс точный ромб x4: у силуэта классики в верхней половине зубцы до 1/16 клетки,
и граница материала у края клетки (разметка, камень) шла этой лесенкой (разбор 07.10).
Исключение - клин 1/8 x 1/8 у верхней вершины асфальта (кадры 9-13): там альфа - силуэт классики. В вершине «V»
(штрих по краю -u одной клетки встречает штрих по краю -v другой) классика смыкает их выступами кадров 10 и 11
сквозь зубцы третьей клетки; тем же выступом кончаются штрихи у вершины следующей клетки.

Контроли (обязаны ПРОВАЛИТЬ crossing_check по дампу игры):
  --control crop   клетки - простые вырезы ответа без складки, альфа - только силуэт классики: лесенка у края
                   разметки и бордюра (разрыв зерна на стыке в игре не виден - зерно мельче пикселя);
  --control patch  асфальт кадров 10-12 из других мест ответа и на 15 процентов светлее: заплатки под разметкой;
  --control old    кадры 2, 4, 9, 12 остаются картинками установки без вариантов - старые соседи, полосы
                   тротуар | бордюр отклонённого кадра 07.10;
  --control wedge  выступ кадров бордюра за стороной к асфальту - лицо камня (как в первой сборке 07.10): в клине
                   у верхней вершины асфальта ступенька края бордюра на каждой вершине клетки.
Выступ кадров бордюра 1-8 за стороной, обращённой к асфальту, - асфальт того же поля: в клин асфальта он и
заглядывает.

    py -3.13 tools/hdart/crossing_build.py build [--tag new] [--control crop|patch|old|wedge]
    py -3.13 tools/hdart/crossing_build.py preview --tag new        # участок без игры, раскладкой движка
    py -3.13 tools/hdart/crossing_build.py mods --tag new           # дерево модов для невидимого прогона
    py -3.13 tools/hdart/crossing_build.py sheet [--main new]       # лист по дампам игры _dumps/<метка>/dump
                                     (классика, HD сейчас, новое, контроли, без дождя - что из этого снято)

Кладёт в census/maps/pilot2/probe_crossing/<метка>/: ROADS.PCK/<кадр>.png, build.json, preview.png; дерево модов
в _mods/<метка> (соединения на установку, своя только hd/TERRAIN/ROADS.PCK - установку не трогает; снимать
соединения только rmdir, R-047). В пак мода НЕ идёт.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crossing_check as cc           # noqa: E402
import ground_field as gf             # noqa: E402
import pilot2_job_sheet as js         # noqa: E402
import sidewalk_probe as sp           # noqa: E402

ROOT = js.ROOT
OUT = ROOT / "census" / "maps" / "pilot2" / "probe_crossing"
RAW = ROOT / "census" / "maps" / "pilot2" / "probe_sidewalk" / "raw_s7101.png"
ENC = "utf-8-sig"
K = js.K
LUMA = sp.LUMA
SUFFIX = ("", ".v1", ".v2", ".v3")
FRAMES = tuple(range(14))
OLD_FRAMES = (2, 4, 9, 12)                             # контроль old: кадры установки остаются как есть
SIDE_FRAME = {"+u": 1, "+v": 2, "-v": 3, "-u": 4}      # кадр классики, где эта сторона бордюра одна
MARK_LO, MARK_HI = 1 / 32, 5 / 32                      # полоса разметки классики (пиксели индекса 240)
MARK_INDEX = 240


# ------------------------------------------------------------------ классика

def classic_tone(f, sel):
    """Средний цвет и разброс яркости пикселей кадра f классики, отобранных sel(idx)."""
    idx, _ = js.gm.classic("ROADS", f)
    px = js.PAL[idx[sel(idx)]].astype(np.float32)
    return px.mean(0), float((px @ LUMA).std())


def side_profile(side, nb=24):
    """Средний цвет камня (рампа 15, индексы 240+) поперёк полосы стороны side по глубине 0..1: nb ячеек."""
    f = SIDE_FRAME[side]
    w = cc.KERB_SIDES[f][side]
    i4 = js.classic_idx("ROADS", f)
    u, v = sp.frame_uv(1)
    d = cc.side_depth(side, u, v, w)
    m = (i4 >= 240) & (d >= 0) & (d <= 1)
    b = np.clip((d[m] * nb).astype(int), 0, nb - 1)
    rgb = js.PAL[i4[m]].astype(np.float64)
    cnt = np.bincount(b, minlength=nb).astype(float)
    prof = np.stack([np.bincount(b, rgb[:, c], minlength=nb) for c in range(3)], -1)
    have = cnt > 0
    if have.sum() < 3:
        raise SystemExit("у кадра %d мало камня в полосе %s" % (f, side))
    prof[have] /= cnt[have, None]
    xs = np.arange(nb)
    for c in range(3):
        prof[:, c] = np.interp(xs, xs[have], prof[have, c])
    k = np.exp(-0.5 * (np.arange(-2, 3) / 1.0) ** 2)
    k /= k.sum()
    pad = np.pad(prof, ((2, 2), (0, 0)), mode="edge")
    return np.stack([np.convolve(pad[:, c], k, mode="valid") for c in range(3)], -1)


def at_depth(prof, d):
    x = np.clip(d, 0, 1 - 1e-6) * len(prof) - 0.5
    return np.stack([np.interp(x, np.arange(len(prof)), prof[:, c]) for c in range(3)], -1)


def gauss(a, s):
    t = np.arange(-int(3 * s) - 1, int(3 * s) + 2)
    k = np.exp(-t * t / (2 * s * s))
    k /= k.sum()
    pad = len(t) // 2
    b = np.pad(a, ((pad, pad), (pad, pad)), mode="edge")
    b = np.apply_along_axis(lambda r: np.convolve(r, k, "valid"), 1, b)
    return np.apply_along_axis(lambda r: np.convolve(r, k, "valid"), 0, b)


def grate_layer():
    """Решётка стока кадра 13 по пикселям классики. Пластина - квадрат в осях клетки по крайним пикселям прутьев
    (индексы 11-13) с запасом в полпикселя базы; прутья идут вдоль u, шаг - сильнейшая гармоника яркости по v;
    профиль по фазе шага делится по медиане на пруток и прорезь, каждый своим средним цветом классики (контур
    чёткий, покрытие по 16 подточкам). Кромка - тёмные пиксели 251-252 классики по краям пластины -u и +v.
    Возвращает цвет и покрытие пластины, цвет и покрытие кромки (x4) и описание для build.json."""
    idx, _ = js.gm.classic("ROADS", 13)
    yy, xx = np.mgrid[0:idx.shape[0], 0:idx.shape[1]].astype(np.float64)
    U, V = sp.screen_to_uv(xx + 0.5, yy + 0.5)
    rgb = js.PAL[idx].astype(np.float64)
    g = (idx >= 11) & (idx <= 13)
    r = (idx >= 251) & (idx <= 252) & (U < 0.75)        # одиночный 251 у правого угла - точка асфальта
    lum = rgb @ LUMA
    best = max((abs(((lum[g] - lum[g].mean()) * np.exp(2j * np.pi * V[g] / p)).sum()), p)
               for p in np.arange(0.14, 0.21, 0.0025))
    step = float(best[1])
    nb = 12
    b = np.floor((V[g] / step) % 1 * nb).astype(int) % nb
    cnt = np.bincount(b, minlength=nb).astype(float)
    prof = np.stack([np.bincount(b, rgb[g][:, c], minlength=nb) for c in range(3)], -1)
    have = cnt > 0
    prof[have] /= cnt[have, None]
    xs = np.arange(nb)
    for c in range(3):
        prof[:, c] = np.interp(xs, xs[have], prof[have, c], period=nb)
    prof = (np.roll(prof, 1, 0) + 2 * prof + np.roll(prof, -1, 0)) / 4
    py_ = prof @ LUMA
    bright = py_ > np.median(py_)
    bar_rgb = (prof[bright] * cnt[bright, None]).sum(0) / cnt[bright].sum()
    slot_rgb = (prof[~bright] * cnt[~bright, None]).sum(0) / cnt[~bright].sum()
    h = 0.03
    u0, u1 = U[g].min() - h, U[g].max() + h
    v0, v1 = V[g].min() - h, V[g].max() + h
    rim_rgb = rgb[r].mean(0)
    w = 0.055                                          # кромка: пиксель базы по нормали к краю
    us, vs = sp.frame_uv(4)
    plate = (us >= u0) & (us < u1) & (vs >= v0) & (vs < v1)
    rim = ((np.abs(us - u0) < w / 2) & (vs >= v0 - w / 2) & (vs < v1 + w / 2)) | \
          ((np.abs(vs - v1) < w / 2) & (us >= u0 - w / 2) & (us < u1 + w / 2))
    on_bar = bright[np.floor((vs / step) % 1 * nb).astype(int) % nb] & plate
    n_plate = np.maximum(plate.sum(-1), 1)
    share = on_bar.sum(-1) / n_plate
    colour = slot_rgb[None, None, :] * (1 - share[..., None]) + bar_rgb[None, None, :] * share[..., None]
    info = dict(step=round(step, 4), plate_u=[round(float(u0), 3), round(float(u1), 3)],
                plate_v=[round(float(v0), 3), round(float(v1), 3)], bar_rgb=np.round(bar_rgb, 1).tolist(),
                slot_rgb=np.round(slot_rgb, 1).tolist(), rim_rgb=np.round(rim_rgb, 1).tolist(),
                bar_share=round(float(bright.mean()), 3))
    return colour, plate.mean(-1), rim_rgb, rim.mean(-1), info


# ------------------------------------------------------------------ материал

def cells_of(tex, mean_rgb, grain_std, a, control_crop=False):
    """Клетки 4 вариантов (независимых: сведения краёв нет - движок сам сшивает варианты)."""
    ns = argparse.Namespace(period=a.period, sigma_low=a.sigma_low, wear_center=True, edge_band=1e-6,
                            wear_std=a.wear_std * float(mean_rgb @ LUMA) / a.walk_l, wear_max=a.wear_max)
    cells, grains, wears, diag = sp.make_cells(tex, ns, mean_rgb, grain_std)
    if control_crop:
        # контроль: простые вырезы без складки - клетка не периодична, край клетки не продолжает соседа
        p = a.period
        lum = tex @ LUMA
        low = sp.blur_wrap(lum, a.sigma_low)
        m_l = float(mean_rgb @ LUMA)
        g_src, w_src = lum - low, low - low.mean()
        for j, (cx, cy) in enumerate(sp.CENTRES):
            g = g_src[cy - p // 2:cy + p // 2, cx - p // 2:cx + p // 2]
            w = w_src[cy - p // 2:cy + p // 2, cx - p // 2:cx + p // 2]
            g = g * (float(grains[j].std()) / max(float(g.std()), 1e-6))
            w = np.clip((w - w.mean()) * (float(wears[j].std()) / max(float(w.std()), 1e-6)), -a.wear_max, a.wear_max)
            grains[j], wears[j] = g, w
            cells[j] = np.clip(mean_rgb[None, None, :] * ((m_l + g + w) / m_l)[..., None], 0, 255)
    return cells, grains, wears, diag


def build(a):
    raw = Path(a.raw)
    tex = np.asarray(Image.open(raw).convert("RGB").resize((sp.SIDE, sp.SIDE), Image.LANCZOS)).astype(np.float32)
    walk_rgb, walk_std = classic_tone(0, lambda i: i > 0)
    asph_rgb, asph_std = classic_tone(9, lambda i: i >= 240)
    a.walk_l = float(walk_rgb @ LUMA)
    asph_l = float(asph_rgb @ LUMA)
    crop = a.control == "crop"
    W = cells_of(tex, walk_rgb, walk_std * a.grain, a, crop)
    A = cells_of(np.ascontiguousarray(tex.transpose(1, 0, 2)[::-1]), asph_rgb, asph_std * a.grain, a, crop)
    if a.control == "patch":
        # контроль: под разметкой другой асфальт - клетки из других мест ответа, светлее на 15 процентов
        P = cells_of(np.ascontiguousarray(np.roll(tex, (333, 517), (0, 1))), asph_rgb * 1.15, asph_std * 1.6, a)
    mark_rgb = js.PAL[MARK_INDEX].astype(np.float64)
    profiles = {s: side_profile(s) for s in SIDE_FRAME}
    gr_col, gr_cov, rim_rgb, rim_cov, grate_info = grate_layer()

    u, v = sp.frame_uv(1)
    us, vs = sp.frame_uv(4)
    p = a.period
    su, sv = (u % 1.0) * p, (v % 1.0) * p
    if crop:
        su, sv = np.clip(u, 0, 0.9999) * p, np.clip(v, 0, 0.9999) * p     # вырез не заворачивается
    samp = (lambda c: sp.bilinear_wrap(c, su, sv))
    # альфа - силуэт классики x4 ПЛЮС точный ромб x4 (центр пикселя в [0, 1)^2). Силуэт классики - лесенка базы:
    # в верхней половине ромба он не доходит до края на зубец до 1/16 клетки (непрозрачно только с u >= 0.065),
    # зубцы закрывал выступ соседа. Граница материала у края клетки (разметка, камень бордюра) тогда идёт этой
    # лесенкой. Полуоткрытые ромбы делят плоскость без щелей и наложений, позже нарисованная клетка закрывает
    # выступ прежней по прямой x4; выступ классики остаётся - стык со старыми наборами без щелей
    # Исключение - клин у верхней вершины асфальта (кадры 9-13, u и v меньше 1/8): там классика прозрачна нарочно,
    # сквозь зубцы видны выступы раньше нарисованных соседей. Так классика смыкает штрихи разметки в вершине «V»
    # и даёт концы штрихов (выступ кадров 10 и 11 до u, v = 1.051 ложится в этот клин следующей клетки,
    # разбор 07.10). Простой асфальт соседа в клине - то же поле, его не видно
    if a.control == "crop":
        diamond = np.zeros(u.shape, bool)
    else:
        diamond = (u >= 0) & (u < 1) & (v >= 0) & (v < 1)
    top_wedge = (u >= 0) & (v >= 0) & (u < 0.125) & (v < 0.125)
    d = OUT / a.tag / "ROADS.PCK"
    d.mkdir(parents=True, exist_ok=True)
    info = dict(tag=a.tag, control=a.control or "", source=raw.resolve().relative_to(ROOT).as_posix(),
                period=a.period, sigma_low=a.sigma_low, grain=a.grain, wear_std=a.wear_std, wear_max=a.wear_max,
                kerb_grain=a.kerb_grain, kerb_wear=a.kerb_wear, kerb_pit=a.kerb_pit, mark_grain=a.mark_grain,
                walk_rgb=[round(float(x), 2) for x in walk_rgb], walk_std=round(walk_std, 2),
                asphalt_rgb=[round(float(x), 2) for x in asph_rgb], asphalt_std=round(asph_std, 2),
                mark_rgb=mark_rgb.tolist(), mark_band=[MARK_LO, MARK_HI],
                walk_diag={k: (np.round(v, 3).tolist() if isinstance(v, list) else v) for k, v in W[3].items()
                           if k in ("grain_raw", "grain_std", "wear_std_out", "coherence", "cell_pattern")},
                asphalt_diag={k: (np.round(v, 3).tolist() if isinstance(v, list) else v) for k, v in A[3].items()
                              if k in ("grain_raw", "grain_std", "wear_std_out", "coherence", "cell_pattern")},
                grate=grate_info)
    # покрытие сторон бордюра по подточкам: у угла сторона с большей глубиной
    side_cover = {}
    for f in range(1, 9):
        best = np.full(us.shape, -1.0)
        who = np.full(us.shape, "", dtype=object)
        for s, w in cc.KERB_SIDES[f].items():
            dd = cc.side_depth(s, us, vs, w)
            take = (dd >= 0) & (dd > best)
            who[take] = s
            best = np.where(take, dd, best)
        side_cover[f] = {s: (who == s).mean(-1) for s in cc.KERB_SIDES[f]}
    mark_cover = {}
    for f, edges in cc.MARK_EDGES.items():
        m = np.zeros(us.shape, bool)
        for e in edges:
            t = us if e == "-u" else vs
            m |= (t >= MARK_LO) & (t < MARK_HI)
        mark_cover[f] = m.mean(-1)
    m_w = float(walk_rgb @ LUMA)
    for j, suf in enumerate(SUFFIX):
        walk = samp(W[0][j])
        g = samp(W[1][j])
        wr = samp(W[2][j])
        gs = float(W[1][j].std())
        stone = 1 + a.kerb_grain * g / m_w + a.kerb_wear * wr / m_w
        stone = stone * np.where(g < -a.kerb_pit * gs, 0.82, 1.0)           # выщербины - самые глубокие точки зерна
        asph = samp(A[0][j])
        ga = samp(A[1][j])
        under = samp(P[0][j]) if a.control == "patch" else asph
        for f in FRAMES:
            if f == 0:
                rgb = walk
            elif f <= 8:
                rgb = walk.copy()
                tot = np.zeros(u.shape)
                for s, cov in side_cover[f].items():
                    w_s = cc.KERB_SIDES[f][s]
                    kc = at_depth(profiles[s], cc.side_depth(s, u, v, w_s)) * stone[..., None]
                    rgb = rgb + (kc - walk) * cov[..., None]
                    tot += cov
                if a.control != "wedge":
                    # за стороной бордюра, обращённой к асфальту, - асфальт того же поля, а не лицо камня: выступ
                    # силуэта классики за ромб виден в клине у верхней вершины асфальта (альфа классики, см. выше),
                    # и лицо камня давало там ступеньку на 1/16 клетки у каждой вершины (разбор 07.10, R-248)
                    beyond = np.zeros(u.shape, bool)
                    for s in cc.KERB_SIDES[f]:
                        beyond |= {"+u": u >= 1, "-u": u < 0, "+v": v >= 1, "-v": v < 0}[s]
                    rgb = np.where(beyond[..., None], asph, rgb)
            elif f == 9:
                rgb = asph
            elif f in mark_cover:
                c = mark_cover[f][..., None]
                paint = mark_rgb[None, None, :] * (1 + a.mark_grain * ga / asph_l)[..., None]
                rgb = under * (1 - c) + paint * c
            else:
                metal = gr_col * (1 + 0.3 * ga / asph_l)[..., None]
                rgb = under * (1 - gr_cov[..., None]) + metal * gr_cov[..., None]
                rgb = rgb * (1 - rim_cov[..., None]) + rim_rgb[None, None, :] * rim_cov[..., None]
            own = diamond & ~top_wedge if f >= 9 else diamond
            alpha = np.where((js.classic_idx("ROADS", f) > 0) | own, 255, 0)
            fr = np.dstack([np.clip(rgb, 0, 255), alpha]).astype(np.uint8)
            Image.fromarray(fr, "RGBA").save(d / ("%d%s.png" % (f, suf)))
    if a.control == "old":
        # контроль: старые соседи - кадры 2, 4, 9, 12 не заменяются, в моде остаются картинки установки (одна на
        # кадр, без вариантов), как в отклонённом кадре 07.10
        for f in OLD_FRAMES:
            for pth in list(d.glob("%d.png" % f)) + list(d.glob("%d.v*.png" % f)):
                pth.unlink()
    (OUT / a.tag / "build.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding=ENC)
    print("кадры: %s (%d файлов)" % (d, len(list(d.glob("*.png")))))
    print("тротуар %s зерно %.2f; асфальт %s зерно %.2f; разметка %s, полоса %.4f..%.4f" % (
        info["walk_rgb"], walk_std, info["asphalt_rgb"], asph_std, mark_rgb.tolist(), MARK_LO, MARK_HI))
    print("узор клетки тротуара %s, асфальта %s (шум без узора ~0.125)" % (
        info["walk_diag"]["cell_pattern"], info["asphalt_diag"]["cell_pattern"]))


# ------------------------------------------------------------------ просмотр без игры

def load(tag):
    d = OUT / tag / "ROADS.PCK"
    return {f: [np.asarray(Image.open(d / ("%d%s.png" % (f, s))).convert("RGBA")) for s in SUFFIX] for f in FRAMES}


WINDOW = (47, 7, 14)        # x 47..60, y 7..20: тротуар, бордюры x 51/58, y 11/18, асфальт 52..57, разметка


def preview(a):
    fr = load(a.tag)
    bt = js.mt.Battle(js.CORNER)
    seed = gf.battle_seed(bt.X, bt.Y, bt.Z, bt.blocks)
    cx, cy, n = WINDOW
    cells = js.Blocks.battle_floor(js.CORNER, cx, cy, n)

    def pick(s, f, x, y):
        if s == "ROADS" and f in fr:
            return gf.frame_for(fr[f], cx + x, cy + y, 0, seed, K)
        return js.rgba_hd(s, str(f))
    img, *_ = js.assemble(cells, pick)
    Image.fromarray(img).save(OUT / a.tag / "preview.png")
    print("просмотр:", OUT / a.tag / "preview.png", img.shape)


# ------------------------------------------------------------------ дерево модов

def mods(tag):
    """_mods/<метка>: соединения на моды установки, hd - своя папка из соединений, кроме hd/TERRAIN/ROADS.PCK -
    копии пака установки, где кадры 0-13 и их варианты заменены сборкой."""
    root = OUT / "_mods" / tag
    frames = OUT / tag / "ROADS.PCK"
    dst = root / "hd" / "hd" / "TERRAIN" / "ROADS.PCK"
    if not root.exists():
        root.mkdir(parents=True)
        for m in sp.GAME_MODS.iterdir():
            if m.name != "hd":
                sp.junction(root / m.name, m)
        src_hd = sp.GAME_MODS / "hd"
        for sub_src, sub_dst, keep in ((src_hd, root / "hd", "hd"), (src_hd / "hd", root / "hd" / "hd", "TERRAIN"),
                                       (src_hd / "hd" / "TERRAIN", root / "hd" / "hd" / "TERRAIN", "ROADS.PCK")):
            sub_dst.mkdir(parents=True, exist_ok=True)
            for e in sub_src.iterdir():
                if e.name == keep:
                    continue
                if e.is_dir():
                    sp.junction(sub_dst / e.name, e)
                else:
                    shutil.copy2(e, sub_dst / e.name)
        shutil.copytree(src_hd / "hd" / "TERRAIN" / "ROADS.PCK", dst)
    for f in FRAMES:                       # прежние варианты кадров участка убрать: число вариантов - наше
        for old in list(dst.glob("%d.v*.png" % f)):
            old.unlink()
    n = 0
    for pth in frames.glob("*.png"):
        shutil.copy2(pth, dst / pth.name)
        n += 1
    print("моды: %s (кадров заменено %d)" % (root, n))
    return root


# ------------------------------------------------------------------ лист по дампам игры

# крупные фрагменты: узел сетки мира (gx, gy) в центре выреза, подпись
CLOSE = [((55, 12), "вершина V: штрих по -v клетки 54,12 (кадр 11) встречает штрих по -u клетки 55,11 (кадр 10)"),
         ((55, 8), "конец штриха кадра 10 (55,7) у вершины следующей клетки асфальта"),
         ((56, 14), "простой асфальт: узел четырёх клеток кадра 9 (55..56, 13..14) - сетка клеток"),
         ((52, 12), "внутренний угол бордюра 7 (51,11) и асфальт"),
         ((52, 9.5), "передний бордюр 1 (51,9) | асфальт 9 (52,9)"),
         ((49, 12), "передний бордюр 2 (49,11) | асфальт"),
         ((50, 18), "задний бордюр 3 (50,18) | асфальт"),
         ((52.5, 7.5), "решётка стока кадра 13 (52,7)"),
         ((50, 12), "вершина асфальта (50,12) под передним бордюром 2: клин у верхней вершины, край бордюра"),
         ((58, 9), "задний бордюр 4 (58,9) | асфальт 9 (57,9), вершина бордюра")]


def dump_of(tag):
    p = OUT / "_dumps" / tag / "dump"
    js_d = json.loads(Path(str(p) + ".json").read_text(encoding=ENC))
    k = int(js_d["k"])
    cam = (int(js_d["cameraOffsetX"]) // k, int(js_d["cameraOffsetY"]) // k, int(js_d["cameraOffsetZ"]))
    return Image.open(str(p) + "_map.png").convert("RGB"), k, cam, js_d


def grid_xy(gx, gy, k, cam):
    """Пиксель дампа узла сетки мира (этаж 0): обратное к sx = X/k - camX - 16, gu - gv = sx/16, gu + gv = sy/8."""
    return (16 * (gx - gy) + cam[0] + 16) * k, (8 * (gx + gy) + cam[1] + 24) * k


def sheet(a):
    tags = [t for t in a.tags.split(",") if (OUT / "_dumps" / t / "dump_map.png").exists()]
    D = {t: dump_of(t) for t in tags}
    cams = {t: D[t][2] for t in tags}
    k = D[tags[0]][1]
    sh = sp.Sheet(2400, "Перекрёсток ROADS целиком (кадры 0-13), метка %s - дампы игры Ctrl+F8, k=%d, одна камера и "
                  "свет" % (a.main, k), False)
    sh.para("Камера дампов (база): " + ";  ".join("%s %s" % (t, c) for t, c in cams.items()) +
            ("" if len(set(cams.values())) == 1 else "   !! КАМЕРЫ РАЗНЫЕ - сравнение не годится"),
            fill=(180, 220, 255) if len(set(cams.values())) == 1 else (255, 120, 120))
    cmp3 = [t for t in ("classic", "hd_now", a.main) if t in D]
    names = dict(classic="классика (режим 0)", hd_now="HD сейчас (пак установки)", classic_na="классика без дождя",
                 ctl_crop="контроль crop", ctl_patch="контроль patch", ctl_old="контроль old",
                 ctl_wedge="контроль wedge")
    names[a.main] = "новое (%s)" % a.main
    names[a.main + "_na"] = "новое без дождя"
    cx, cy, n = WINDOW
    corners = [grid_xy(gx, gy, k, cams[tags[0]]) for gx, gy in ((cx, cy), (cx + n, cy), (cx, cy + n), (cx + n, cy + n))]
    iw, ih = D[tags[0]][0].size
    box = (max(0, min(c[0] for c in corners)), max(0, min(c[1] for c in corners)), min(iw, max(c[0] for c in corners)),
           min(ih, max(c[1] for c in corners)))
    sh.para("Цветные точки по всей карте во всех дампах - пар заморозки дампа (hdTestFreeze, Map.cpp), не пол; "
            "crossing_check их исключает маской.", fill=(200, 200, 200))
    sc = (2400 - 60) / 3 / (box[2] - box[0])
    sh.head("1. Общий вид участка 14 x 14 клеток (x %d..%d, y %d..%d), уменьшено в %.1f раза" % (
        cx, cx + n - 1, cy, cy + n - 1, 1 / sc))
    ov = lambda t: D[t][0].crop(box).resize((int((box[2] - box[0]) * sc), int((box[3] - box[1]) * sc)), Image.LANCZOS)
    sh.row([(names[t], ov(t)) for t in cmp3])
    sh.head("2. Крупно, пиксели дампа x2 (один пиксель базы = %d x %d)" % (2 * k, 2 * k))
    hw, hh = 128, 64
    for (gx, gy), lbl in CLOSE:
        X, Y = grid_xy(gx, gy, k, cams[tags[0]])
        b = (int(X - hw), int(Y - hh), int(X + hw), int(Y + hh))
        sh.para(lbl)
        sh.row([(names[t], D[t][0].crop(b).resize((4 * hw, 4 * hh), Image.NEAREST)) for t in cmp3])
    # контроль - на месте своего дефекта: crop - лесенка края штриха у вершины V, patch - асфальт под штрихом,
    # old - стык тротуара со старым бордюром без вариантов, wedge - ступенька края бордюра в клине асфальта
    ctl = [(t, c) for t, c in (("ctl_crop", CLOSE[0]), ("ctl_patch", CLOSE[1]), ("ctl_old", CLOSE[3]),
                               ("ctl_wedge", CLOSE[8])) if t in D]
    if ctl:
        sh.head("3. Контроли (каждый обязан провалить crossing_check на своей мере): новое | контроль, x2 "
                "(wedge - x6: ступенька в 2 пикселя базы)")
        for t, ((gx, gy), lbl) in ctl:
            z = 6 if t == "ctl_wedge" else 2
            w2, h2 = 2 * hw // z, 2 * hh // z
            X, Y = grid_xy(gx, gy, k, cams[tags[0]])
            b = (int(X - w2), int(Y - h2), int(X + w2), int(Y + h2))
            sh.para("%s: %s, x%d" % (names[t], lbl, z))
            sh.row([(names[u], D[u][0].crop(b).resize((2 * w2 * z, 2 * h2 * z), Image.NEAREST)) for u in (a.main, t)])
    na = [t for t in ("classic", "classic_na", a.main, a.main + "_na") if t in D]
    if len(na) > 2:
        sh.head("4. Палитра: бой идёт под кислотным дождём (enviroEffectsType STR_ENVIRO_ACID_RAIN) - классика рисуется "
                "палитрой dgoodpal_grinder (зелёная), HD-слой берёт RGB пака. Копия сейва без дождя - классика "
                "в палитре боя delicious_regular")
        sc2 = (2400 - 70) / 4 / (box[2] - box[0])
        sh.row([(names[t], D[t][0].crop(box).resize((int((box[2] - box[0]) * sc2), int((box[3] - box[1]) * sc2)),
                                                     Image.LANCZOS)) for t in na], gap=12)
    chk = OUT / "_dumps" / "_check"
    rows = [t for t in tags if (chk / ("check_%s.json" % t)).exists()]
    if rows:
        sh.head("5. Меры crossing_check по дампу движка - диагностика; приёмка - глазами по листу. "
                "diag - мера не отделяет брак от нормы (проваливает и классика), в итог не идёт")
        for t in rows:
            r = json.loads((chk / ("check_%s.json" % t)).read_text(encoding=ENC))
            v = r["verdict"]
            ref = t.startswith("classic")
            bad = cc.failed(v, ref)
            nf = len(bad)
            sh.para("%s: %s, провалено мер %d%s" % (
                names.get(t, t), "FAIL" if nf else "PASS", nf,
                ": " + ", ".join(bad) if nf else ("  (эталон: требования HD - край штриха и бордюра - "
                "классика по природе не проходит, не считаются)" if ref else "")),
                fill=(255, 120, 120) if nf else (140, 255, 140))
            sh.para("     " + ";  ".join("%s %s %s" % (kk, x[0], "" if x[1] == "PASS" else x[1])
                                         for kk, x in v.items()), fill=(200, 200, 200), step=18)
    sh.save(OUT / ("sheet_%s.png" % a.main))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--raw", default=str(RAW))
    b.add_argument("--tag", default="new")
    b.add_argument("--control", default="", choices=("", "crop", "patch", "old", "wedge"))
    b.add_argument("--period", type=int, default=160)
    b.add_argument("--sigma-low", type=float, default=12.0)
    b.add_argument("--grain", type=float, default=1.0)
    b.add_argument("--wear-std", type=float, default=1.0, help="износ тротуара; у асфальта - пропорционально тону")
    b.add_argument("--wear-max", type=float, default=3.0)
    b.add_argument("--kerb-grain", type=float, default=1.0)
    b.add_argument("--kerb-wear", type=float, default=2.5)
    b.add_argument("--kerb-pit", type=float, default=1.8)
    b.add_argument("--mark-grain", type=float, default=0.3, help="зерно асфальта на краске, доля")
    pv = sub.add_parser("preview")
    pv.add_argument("--tag", default="new")
    mo = sub.add_parser("mods")
    mo.add_argument("--tag", default="new")
    st = sub.add_parser("sheet", help="лист по дампам игры _dumps/<метка>/dump: классика | HD сейчас | новое")
    st.add_argument("--main", default="new")
    st.add_argument("--tags", default="classic,hd_now,new,ctl_crop,ctl_patch,ctl_old,ctl_wedge,classic_na,new_na")
    a = ap.parse_args()
    if a.cmd == "build":
        build(a)
    elif a.cmd == "preview":
        preview(a)
    elif a.cmd == "sheet":
        sheet(a)
    else:
        mods(a.tag)


if __name__ == "__main__":
    main()
