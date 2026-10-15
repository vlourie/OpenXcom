#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Автоприёмка HD-оружия (указание специалиста 05.10): три раздельных итога и независимая проверка смысла.

  рисунок      - качество исполнения само по себе: не обведена ли лесенка пикселей спрайта (R-160), не каша ли
                 блоками пикселя базы, не мыльное ли увеличение, чистая ли альфа. От оригинала берётся только сетка
                 пикселя базы и силуэт - конструкцию эта ось не судит;
  конструкция  - weapon_parts по сырому ответу: доказательные мерки покрытия (концы, поворот, форма, профиль
                 детали) и размер по родной альфе. Цветовые мерки (стыки, цвет детали), неизмеренное, лишнее -
                 вопросы, а не дефекты;
  размещение   - weapon_parts.placement: срез клетками и кадром. Метку .wide автоматически не ставит.

Вопросы и серая зона решает независимая визуальная проверка ИИ (judge: Codex, только чтение, без видеокарты -
текстовая модель и Qwen вместе не грузятся НИКОГДА). Ей подаются оригинал BIGOBS, сырой ответ, карточка
боеприпаса и описание; она не видит выводов автоматики (вслепую) и называет конкретную пропавшую, добавленную,
смещённую или заменённую часть. Два независимых ответа; человеку - только разногласия.

Контроли (обязательны при правке мерок):
  py -3.13 tools/hdart/weapon_accept.py falsealarm --only W-001,...   допустимые HD-изменения оригинала (блики,
        фактура, сглаженные края, другой тон, всё вместе) - конструкция обязана быть PASS, без вопросов-дефектов;
  py -3.13 tools/hdart/weapon_accept.py detect --only ...             известные дефекты поверх тех же изменений -
        обязаны быть пойманы.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)

import numpy as np                      # noqa: E402
from PIL import Image                   # noqa: E402

import weapon_fit as wf                 # noqa: E402
import weapon_parts as wp               # noqa: E402

ENC = "utf-8-sig"
K = wp.K
VERD = wp.VERD

# ---------------------------------------------------------------- допустимые HD-изменения (контроль ложных тревог)

VARIANTS = ("light", "texture", "smooth", "tone", "all")


def _up(a, k=K, how=Image.BICUBIC):
    """Плавное увеличение массива HxW или HxWx3 (float 0..255)."""
    if a.ndim == 2:
        return np.asarray(Image.fromarray(a.astype(np.float32), "F").resize((a.shape[1] * k, a.shape[0] * k), how))
    return np.dstack([_up(a[..., c], k, how) for c in range(a.shape[2])])


def _fill_out(rgb, m, n=3):
    """Цвета вне маски - от ближайших непрозрачных соседей (чтобы плавное увеличение не тянуло чёрное с края)."""
    rgb = rgb.copy()
    have = m.copy()
    for _ in range(n):
        acc = np.zeros_like(rgb)
        cnt = np.zeros(m.shape, np.float32)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            sh = np.roll(have, (dy, dx), (0, 1))
            acc += np.roll(rgb, (dy, dx), (0, 1)) * sh[..., None]
            cnt += sh
        new = ~have & (cnt > 0)
        rgb[new] = acc[new] / cnt[new][:, None]
        have |= new
    return rgb


def variant(rgb, m, kind, seed=0):
    """Оригинал, перерисованный ДОПУСТИМО: силуэт и детали на местах, меняется исполнение. -> RGBA k=4 uint8.
      light   - другие блики: плавное поле света +-25 %, свет сверху-слева, полоса блика вдоль длинной оси;
      texture - фактура: шум HD-пикселя и штрихи вдоль оси (металл, дерево);
      smooth  - сглаженные края и плавный цвет: контур без лесенки (маска x4, размытая и обрезанная по 0.5, края
                сглажены), цвет плавным увеличением;
      tone    - другой тон: тёплый сдвиг и контраст x1.15 (дельта около 6 ΔE);
      all     - всё сразу;
      clean   - свет, сглаживание и тон без шума фактуры (контроль судьи ИИ: шум 'all' он честно читает как кашу)."""
    rng = np.random.default_rng(seed)
    H, W = m.shape
    kinds = {"all": ("light", "texture", "smooth", "tone"), "clean": ("light", "smooth", "tone")}.get(kind, (kind,))
    base = _fill_out(rgb, m)
    if "smooth" in kinds:
        c = _up(base)
        a = np.repeat(np.repeat(m.astype(np.float32), K, 0), K, 1)
        a = wf.blur(a, 2.0)
        a = wf.blur((a >= 0.5).astype(np.float32), 0.7)
    else:
        c = np.repeat(np.repeat(base, K, 0), K, 1)
        a = np.repeat(np.repeat(m.astype(np.float32), K, 0), K, 1)
        a = wf.blur(a, 0.5)
    yy, xx = np.mgrid[0:H * K, 0:W * K].astype(np.float32)
    ys, xs = np.nonzero(m)
    ax = wp.part_axis(ys, xs)
    if "light" in kinds:
        f = np.zeros((H, W), np.float32)
        for _ in range(3):
            cy, cx = rng.uniform(0, H), rng.uniform(0, W)
            f += rng.uniform(-0.25, 0.25) * np.exp(-((np.mgrid[0:H, 0:W][0] - cy) ** 2 +
                                                      (np.mgrid[0:H, 0:W][1] - cx) ** 2) / (2 * 6.0 ** 2))
        f = _up(f) + 0.15 * (1 - (xx + yy) / float(H * K + W * K)) - 0.075
        # блик: полоса шириной в пиксель базы вдоль длинной оси, сдвинутая от середины
        ux, uy = np.cos(ax[1]), np.sin(ax[1])
        cx, cy = (xs.mean() + 0.5) * K, (ys.mean() + 0.5) * K
        dperp = -(xx - cx) * uy + (yy - cy) * ux
        f += 0.35 * np.exp(-((dperp - 0.8 * K) ** 2) / (2 * (0.5 * K) ** 2))
        c = c * (1 + f)[..., None]
    if "texture" in kinds:
        c = c + rng.normal(0, 9.0, c.shape[:2])[..., None]
        ux, uy = np.cos(ax[1]), np.sin(ax[1])
        dperp = -xx * uy + yy * ux
        streak = rng.normal(0, 1.0, 4096)[(np.floor(dperp * 1.3).astype(int)) % 4096]
        c = c + 6.0 * wf.blur(streak, 0.6)[..., None]
    if "tone" in kinds:
        mu = c[a >= 0.5].mean(0)
        c = (c - mu) * 1.15 + mu
        c = c * np.array([1.06, 1.0, 0.93])
    return np.dstack([np.clip(c, 0, 255), np.clip(a, 0, 1) * 255]).astype(np.uint8)


def run_construction(ms, t, rgba, spec, rgb_o, m_o):
    """Ось конструкции на готовом RGBA k=4 (контроли): части + размер по альфе этого RGBA."""
    res, bits, unl, jn = wp.check_one(ms, t, rgba, spec, rgb_o, m_o)
    v, why, qs, li = wp.overall(res, bits, unl, spec, jn)
    size, _s = wp.size_native(rgba[..., 3].astype(np.float32) / 255.0, m_o)
    v = max(v, size["verdict"], key=VERD.get)
    if size["why"]:
        why = why + [size["why"]]
    return v, why, qs, li, res


def falsealarm(masters, seeds=(0, 1)):
    """Допустимые изменения: конструкция обязана быть PASS. Вопросы - справка (их решает ИИ), не провал."""
    L = wf.list_rows()
    rows = []
    for ms in masters:
        t = L[ms]["type"]
        spec = wp.load_parts(ms)
        rgb_o, m_o = wf.original(t)
        for kind in VARIANTS:
            for sd in (seeds if kind in ("light", "texture", "all") else (0,)):
                v, why, qs, li, _res = run_construction(ms, t, variant(rgb_o, m_o, kind, sd), spec, rgb_o, m_o)
                rows.append((ms, kind, sd, v, len(qs), why))
                print("%s %-8s s%d %-6s вопросов %2d %s" % (ms, kind, sd, v, len(qs), "; ".join(why)), flush=True)
    bad = [r for r in rows if r[3] != "PASS"]
    print("ложных тревог: %d из %d прогонов (FAIL %d, REVIEW %d)" % (
        len(bad), len(rows), sum(r[3] == "FAIL" for r in bad), sum(r[3] == "REVIEW" for r in bad)))
    return rows


def edit(rgb, m, spec, part, how):
    """Известный дефект детали оригинала (пиксели базы):
      ('shift', dx, dy)  - деталь сдвинута;      ('trim_top', n)  - снято n верхних строк детали;
      ('narrow', r0, r1) - в строках r0..r1 (от верха детали) снят крайний правый пиксель;
      ('grow_up', n)     - деталь вытянута вверх;  ('remove',)    - детали нет;
      ('add', x, y, w, h) - добавлен кусок чужого цвета там, где у оригинала пусто."""
    lab = wp.label_map(spec, m)
    z = lab == [p["name"] for p in spec["parts"]].index(part) if part else np.zeros_like(m)
    rgb2, m2 = rgb.copy(), m.copy()
    ys, xs = np.nonzero(z)
    if how[0] == "shift":
        dx, dy = how[1], how[2]
        rgb2[z] = 0
        m2[z] = False
        rgb2[ys + dy, xs + dx] = rgb[ys, xs]
        m2[ys + dy, xs + dx] = True
    elif how[0] == "trim_top":
        cut = z & (np.arange(z.shape[0])[:, None] < ys.min() + how[1])
        rgb2[cut] = 0
        m2[cut] = False
    elif how[0] == "narrow":
        for y in range(ys.min() + how[1], ys.min() + how[2] + 1):
            row = xs[ys == y]
            if len(row) >= 2:
                rgb2[y, row.max()] = 0
                m2[y, row.max()] = False
    elif how[0] == "grow_up":
        y0 = ys.min()
        for x in xs[ys == y0].tolist():
            for k in range(1, how[1] + 1):
                if y0 - k >= 0:
                    rgb2[y0 - k, x] = rgb[y0, x]
                    m2[y0 - k, x] = True
    elif how[0] == "remove":
        rgb2[z] = 0
        m2[z] = False
    elif how[0] == "add":
        x, y, w, h = how[1:]
        sl = (slice(y, y + h), slice(x, x + w))
        rgb2[sl] = (150, 150, 155)
        m2[sl] = True
    return rgb2, m2


# (мастер, деталь, дефект, ожидание): ожидание по детали - REVIEW+ / FAIL; EXTRA - вопрос «лишнее» в итоге
DETECT = [("W-015", "stock", ("shift", 2, 0), "REVIEW+"), ("W-015", "stock", ("shift", 3, 0), "FAIL"),
          ("W-015", "magazine", ("shift", 0, 2), "REVIEW+"), ("W-015", "magazine", ("shift", 0, 3), "FAIL"),
          ("W-059", "barrel", ("grow_up", 2), "REVIEW+"), ("W-059", "barrel", ("trim_top", 3), "FAIL"),
          ("W-059", "magazine", ("shift", 2, 0), "REVIEW+"), ("W-059", "magazine", ("shift", 3, 0), "FAIL"),
          ("W-059", "magazine", ("remove",), "FAIL"),
          ("W-081", "handle", ("shift", 0, 2), "REVIEW+"),
          ("W-079", "blade", ("narrow", 0, 5), "FAIL"), ("W-079", "blade", ("narrow", 12, 18), "FAIL"),
          ("W-072", None, ("add", 14, 8, 3, 4), "EXTRA")]


def detect(only=(), kinds=("plain", "all")):
    """Известные дефекты обязаны ловиться и на чистом оригинале x4, и поверх допустимых изменений ('all')."""
    L = wf.list_rows()
    miss = 0
    n = 0
    for ms, part, how, want in DETECT:
        if only and ms not in only:
            continue
        t = L[ms]["type"]
        spec = wp.load_parts(ms)
        rgb_o, m_o = wf.original(t)
        r2, m2 = edit(rgb_o, m_o, spec, part, how)
        for kind in kinds:
            rgba = variant(r2, m2, "light" if kind == "plain" else kind, 0) if kind != "plain" else None
            if rgba is None:          # чистый: nearest x4 с мягким краем, без изменений исполнения
                c = np.repeat(np.repeat(r2, K, 0), K, 1)
                a = wf.blur(np.repeat(np.repeat(m2.astype(np.float32), K, 0), K, 1), 0.5)
                rgba = np.dstack([c, a * 255]).clip(0, 255).astype(np.uint8)
            v, why, qs, _li, res = run_construction(ms, t, rgba, spec, rgb_o, m_o)
            if want == "EXTRA":
                got = "EXTRA" if any(q["kind"] == "EXTRA" for q in qs) else "нет"
                ok = got == "EXTRA"
            else:
                got = [r["verdict"] for r in res if r["part"] == part][0]
                ok = got == want or (want == "REVIEW+" and got in ("REVIEW", "FAIL"))
            n += 1
            miss += not ok
            print("%s %-9s %-24s %-5s ожидалось %-7s вышло %-6s итог %-6s %s" % (
                ms, part, how, kind, want, got, v, "OK" if ok else "ПРОМАХ"), flush=True)
    print("обнаружение: промахов %d из %d" % (miss, n))
    return miss


# ---------------------------------------------------------------- рисунок

DZ = 8          # сетка рисунка: пиксель базы = DZ пикселей
DPAD = 2        # запас холста в пикселях базы


def _phase_ratio(g, w, axis):
    """Энергия перепадов по фазе сетки пикселя базы (mod DZ): максимум к медиане. Обведённая лесенка и каша блоками
    дают пик на границе пикселя базы, рисунок - ровно по всем фазам. Фаза не задана заранее: ответ мог сесть со
    сдвигом на пиксель-два."""
    n = g.shape[axis]
    ph = np.arange(n) % DZ
    e = np.array([(g * w).take(np.nonzero(ph == p)[0], axis).sum() for p in range(DZ)])
    c = np.array([w.take(np.nonzero(ph == p)[0], axis).sum() for p in range(DZ)])
    e = e / np.maximum(c, 1)
    return float(e.max() / max(np.median(e), 1e-6))


def drawing_metrics(path, m_o):
    """Ответ на сетку «база x DZ» равномерно на габарит оригинала (как нарезка) -> мерки исполнения:
      block   - пик перепадов яркости внутри тела на границе пикселя базы (обведённая лесенка, каша блоками);
      astair  - то же по альфе: лесенка контура;
      detail  - мелкое (мельче пикселя базы) к разбросу тела: мыльное увеличение даёт около нуля;
      semi    - доля полупрозрачного внутри тела (дыры, подложка в теле)."""
    import weapon_from_ref as wr
    rgb, a, _bg = wr.ref_matte(path)
    b = wf.bbox(m_o)
    W, H = (m_o.shape[1] + 2 * DPAD) * DZ, (m_o.shape[0] + 2 * DPAD) * DZ
    box = (b[0] + DPAD, b[1] + DPAD, b[2] + DPAD, b[3] + DPAD)
    c, al, _rep = wr.place(rgb, a, box, DZ, W, H)
    Y = c @ np.array([0.299, 0.587, 0.114], np.float32)
    body = al > 0.5
    inner = ~wf.dilate(~body, 2)
    # перепады внутри тела: пара соседей обе во внутренней части
    gx, wx = np.abs(np.diff(Y, axis=1)), (inner[:, 1:] & inner[:, :-1]).astype(np.float32)
    gy, wy = np.abs(np.diff(Y, axis=0)), (inner[1:] & inner[:-1]).astype(np.float32)
    block = float(np.sqrt(_phase_ratio(gx, wx, 1) * _phase_ratio(gy, wy, 0)))
    ax_, ay_ = np.abs(np.diff(al, axis=1)), np.abs(np.diff(al, axis=0))
    astair = float(np.sqrt(_phase_ratio(ax_, np.ones_like(ax_), 1) * _phase_ratio(ay_, np.ones_like(ay_), 0)))
    small = np.asarray(Image.fromarray(Y, "F").resize((W // DZ, H // DZ), Image.BOX))
    back = _up(small, DZ, Image.BICUBIC)
    r = (Y - back)[inner]
    detail = float(r.std() / max(Y[inner].std(), 1e-3)) if inner.any() else 0.0
    core = ~wf.dilate(~body, DZ // 2)
    semi = float((al[core] < 0.9).mean()) if core.any() else 0.0
    # лесенка контура как в struct_report.stair_follow (R-160): зона - где силуэт оригинала nearest и спрямлённый
    # расходятся; в ней край ответа пошёл ступенью или линией
    import struct_guide as sg
    mp = np.pad(m_o, DPAD)
    near = np.repeat(np.repeat(mp, DZ, 0), DZ, 1)
    smooth = sg.coverage([sg.smooth_loop(L_) for L_ in sg.loops(mp)], mp.shape[1], mp.shape[0], DZ) > 0.5
    zone = near != smooth
    n_near = int((body == near)[zone].sum())
    n_line = int((body == smooth)[zone].sum())
    stair = float(n_near / max(n_near + n_line, 1))
    return {"block": round(block, 3), "astair": round(astair, 3), "detail": round(detail, 3),
            "semi": round(semi, 4), "stair": round(stair, 3), "stair_zone": int(zone.sum()),
            "inner_px": int(inner.sum())}


# Пороги рисунка (калибровка drawcalib 05.10: хорошие - 23 ответа cg0, эталоны Vitali; плохие - обводка Qwen edit A,
# literal L, qwen-literal, синтетика nearest/bicubic x8). Шкала одна: blocky = block * sqrt(astair).
# PASS - заведомо хороший, FAIL - заведомо брак, между ними серая зона: решает визуальная проверка ИИ.
D_PASS_BLOCKY, D_FAIL_BLOCKY = 2.05, 2.8     # хорошие до 2.33 (меч), плохие от 1.62
D_FAIL_BLOCK, D_FAIL_ASTAIR = 4.0, 5.0       # явная каша блоками / лесенка контура
D_PASS_DETAIL, D_FAIL_DETAIL = 0.45, 0.25    # мыло: bicubic x8 до 0.24, хорошие от 0.33
D_FAIL_SEMI = 0.02                           # полупрозрачное в теле


def drawing_verdict(mt):
    blocky = mt["block"] * np.sqrt(mt["astair"])
    why = []
    if mt["block"] >= D_FAIL_BLOCK:
        why.append("каша блоками пикселя базы (block %.1f)" % mt["block"])
    if mt["astair"] >= D_FAIL_ASTAIR:
        why.append("контур обводит лесенку пикселей (astair %.1f)" % mt["astair"])
    if blocky >= D_FAIL_BLOCKY:
        why.append("перепады по сетке пикселя базы (%.2f, брак от %.1f)" % (blocky, D_FAIL_BLOCKY))
    if mt["detail"] < D_FAIL_DETAIL:
        why.append("мыло: мелкой детали нет (%.2f)" % mt["detail"])
    if mt["semi"] > D_FAIL_SEMI:
        why.append("полупрозрачное в теле %.1f%%" % (100 * mt["semi"]))
    if why:
        return "FAIL", why, round(float(blocky), 3)
    grey = []
    if blocky > D_PASS_BLOCKY:
        grey.append("сетка пикселя базы заметна (%.2f, чисто до %.2f)" % (blocky, D_PASS_BLOCKY))
    if mt["detail"] < D_PASS_DETAIL:
        grey.append("мелкой детали мало (%.2f)" % mt["detail"])
    return ("GREY" if grey else "PASS"), grey, round(float(blocky), 3)


def _synth(rgb_o, m_o, how):
    """Плохой рисунок известного вида из оригинала: nearest x8 (каша блоками, лесенка), bicubic x8 (мыло)."""
    if how == "nearest":
        c = np.repeat(np.repeat(rgb_o, DZ, 0), DZ, 1)
        a = np.repeat(np.repeat(m_o.astype(np.float32), DZ, 0), DZ, 1)
    else:
        c = _up(_fill_out(rgb_o, m_o), DZ)
        a = np.clip(_up(m_o.astype(np.float32), DZ), 0, 1)
    return np.dstack([np.clip(c, 0, 255), (a >= 0.5) * 255.0]).astype(np.uint8)


def drawing_samples():
    """(группа, подпись, путь, тип). good - принятые человеком рисунки, bad - отклонённые за исполнение."""
    L = wf.list_rows()
    by_t = {r["type"]: ms for ms, r in L.items()}
    out = []
    raw = "art/items/weapons-chatgpt-v2/raw"
    for f in sorted(os.listdir(raw)):
        if f.endswith(".cg0.png"):
            out.append(("good", "cg0 " + f[:-8], raw + "/" + f, f[:-8]))
    out.append(("good", "AK final", "art/items/ak-final/pack/BIGOBS.PCK/1168.STR_RIFLE_AK.png", "STR_RIFLE_AK"))
    out.append(("good", "M-01 (АК, Vitali)", "art/items/refs/M-01.png", "STR_RIFLE_AK"))
    for f, t in (("autogun.png", "STR_AUTO_RIFLE"), ("street_sweeper.webp", "STR_COMBAT_SHOTGUN")):
        out.append(("good", "Vitali " + f, "art/items/refs/vitali/" + f, t))
    for d, g, nm in (("art/items/weapons-edit-v1/A", "bad", "edit-A"), ("art/items/weapons-edit-v2-literal/L", "bad",
                                                                        "literal-L"),
                     ("art/items/qwen-literal-v1", "bad", "qwen-literal"),
                     ("art/items/weapons-edit-v1/B", "drawn_wrong_item", "edit-B")):
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if f.endswith(".png") and f.startswith("STR_") and ".input" not in f:
                out.append((g, "%s %s" % (nm, f[:-4]), d + "/" + f, f[:-4]))
    return [s for s in out if s[3] in by_t or s[3] == "STR_RIFLE_AK"]


def drawing_calib(out=""):
    rows = []
    synth_done = set()
    tmp = os.path.join(ROOT, "art/items/weapons-chatgpt-v2/_synth")
    os.makedirs(tmp, exist_ok=True)
    samples = drawing_samples()
    for g, lab, p, t in samples:
        try:
            rgb_o, m_o = wf.original(t)
        except Exception as e:  # noqa: BLE001
            print("пропуск %s: %s" % (lab, e))
            continue
        if g == "good" and lab.startswith("cg0") and t not in synth_done:
            synth_done.add(t)
            for how in ("nearest", "bicubic"):
                sp = os.path.join(tmp, "%s.%s.png" % (t, how))
                Image.fromarray(_synth(rgb_o, m_o, how)).save(sp)
                samples.append(("synth_" + how, "%s x%d %s" % (how, DZ, t), os.path.relpath(sp, ROOT), t))
        mt = drawing_metrics(p, m_o)
        rows.append({"group": g, "label": lab, "path": p, "type": t, **mt})
        print("%-16s %-44s block %6.2f astair %6.2f stair %.2f detail %5.3f semi %.3f" % (
            g, lab[:44], min(mt["block"], 999), min(mt["astair"], 999), mt["stair"], mt["detail"], mt["semi"]),
            flush=True)
    if out:
        with open(out, "w", encoding=ENC) as f:
            json.dump(rows, f, ensure_ascii=False, indent=1)
    return rows


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["falsealarm", "detect", "variants", "drawcalib"])
    ap.add_argument("--only", default="")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    os.chdir(ROOT)
    masters = [x for x in a.only.split(",") if x]
    if a.cmd == "detect":
        sys.exit(1 if detect(set(masters)) else 0)
    if a.cmd == "drawcalib":
        drawing_calib(a.out)
        return
    if a.cmd == "falsealarm":
        rows = falsealarm(masters)
        if a.out:
            with open(a.out, "w", encoding=ENC) as f:
                json.dump(rows, f, ensure_ascii=False, indent=1)
    else:
        L = wf.list_rows()
        os.makedirs(a.out, exist_ok=True)
        for ms in masters:
            rgb_o, m_o = wf.original(L[ms]["type"])
            ims = [Image.fromarray(variant(rgb_o, m_o, k, 0)).resize((m_o.shape[1] * 12, m_o.shape[0] * 12),
                                                                    Image.NEAREST) for k in VARIANTS]
            sheet = Image.new("RGBA", (sum(i.width for i in ims) + 8 * len(ims), ims[0].height), (28, 30, 34, 255))
            x = 0
            for im in ims:
                sheet.alpha_composite(im, (x, 0))
                x += im.width + 8
            sheet.save(os.path.join(a.out, "variants_%s.png" % ms))


if __name__ == "__main__":
    main()
