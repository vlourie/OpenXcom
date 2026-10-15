#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Мигание петель анимации террейна: классика меняется на малой площади, HD - по всему кадру.

Запись MCD перебирает кадры Frame[0..7] каждые 100 мс (Tile::animate). У монитора, лампы,
огонька в классике кадры петли различаются несколькими пикселями, а HD-кадры рисовались порознь
и различаются по всей картинке - на карте мигает вся стена. loop_twins.py (R-338) ловит только
крайний случай: классика побайтно одна. Здесь - всё, где классика отличается.

Петли собираются в группы (кадры, стоящие в одной петле записи, связаны; двери НЛО и двери
пропускаются - они анимируются только при открытии). Основа группы - кадр, который на экране
чаще всех (число мест в Frame[0..7] записей набора), при равенстве младший - как в loop_twins.
Для каждого другого кадра группы против основы:
  * классика: где индексы различаются (маска изменений) и какая это доля видимого;
  * HD: средняя разница по видимым пикселям ВНЕ маски изменений x k с запасом (там классика
    одна, значит и HD обязан быть один) и внутри неё.

Правка (--fix): HD кадра = HD основы вне маски изменений классики (x k, запас --margin пикс
базы, мягкий край). Внутри маски - одно из двух (--mode, по умолчанию auto):
  * own   - свой HD кадра; годится, когда HD кадра и основы - один рисунок (на кольце вокруг
            маски они расходятся не больше RING_SAME);
  * delta - HD основы плюс разница классики кадра и основы, увеличенная гладко: огонёк
            загорается поверх рисунка основы. Нужна, когда HD кадров петли - разные рисунки
            (волна против камней, пустая дыра против механизма): свой кусок там - заплатка.
Вне маски кадры петли становятся равны основе до пикселя, мигает только то, что мигает
в классике. Варианты .vN кадра - те же, что у основы
(вариант основы + своя середина из своего варианта или основного). Без --install правка
пишется в папку --out для листа до/после; с --install - через манифест пака (build_hd_pack:
stage, install в обе копии мода hd), как loop_twins. Режим 0 не затронут: только данные пака.

    py -3.13 tools/hdart/anim_flicker.py                       # перепись обеих копий, TSV и лист худших
    py -3.13 tools/hdart/anim_flicker.py --sets U_WALL_G_X LIGHTNIN_R --sheet 40
    py -3.13 tools/hdart/anim_flicker.py --fix                 # кандидаты правки и лист до/после, без установки
    py -3.13 tools/hdart/anim_flicker.py --fix --install       # то же через манифест в обе копии (после одобрения)
"""
import argparse
import io
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import xcom_sprites as xs                                           # noqa: E402
import loop_twins as lt                                             # noqa: E402

REC = 62
F_UFO_DOOR, F_DOOR = 30, 35
ENC_W = "utf-8-sig"
OUT_TSV = ROOT / "census" / "anim_flicker"
OUT_ART = ROOT / "art" / "_review" / "anim_flicker"
SOFT_FRAC = 0.03            # мягкий класс: классика меняется не больше чем на 3 процентах видимого
OUT_DIFF = 3.0              # ... а HD вне изменений расходится от 3 из 255
LIVE_FRAC = 0.25            # больше - живая анимация (вращение, огонь), правка не применяется
# Живые петли под порогом LIVE_FRAC (доля 0.14-0.25), проверены в игре пилотом 15.10: правка их гасит.
# Списком, а не порогом: порог 0.13 снял бы ещё 520 кадров в 120 наборах, правило 'петля с кадром выше
# LIVE_FRAC' - 100 петель (203 кадра), а WHITEBITS (у каждого кадра своя основа) не ловит ни то, ни другое.
LIVE_SETS = {"LAM_FLOOR", "WHITEBITS"}
BG = (24, 24, 28)
FRINGE_ALPHA = 16.0         # delta: альфа ниже на пустом месте основы - кайма размытия, обнуляется
RING_SAME = 12.0           # auto: HD кадра на кольце вокруг маски ближе к основе - свой кусок, иначе delta


def say(*a):
    print(*a, flush=True)


def records(mcd_bytes):
    """[(номер записи, Frame[0..7])] записей с анимацией, кроме дверей."""
    out = []
    for i in range(0, len(mcd_bytes) - REC + 1, REC):
        b = mcd_bytes[i:i + REC]
        fr8 = list(b[0:8])
        if len(set(fr8)) < 2 or b[F_UFO_DOOR] or b[F_DOOR]:
            continue
        out.append((i // REC, fr8))
    return out


def groups(recs, nframes, shown):
    """Кадры, связанные общей петлей: [(основа, [остальные...], [номера записей])]."""
    parent = {}

    def find(a):
        while parent.setdefault(a, a) != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    rec_of = defaultdict(set)
    for ri, fr8 in recs:
        fs = [f for f in dict.fromkeys(fr8) if f < nframes]
        for f in fs:
            rec_of[f].add(ri)
            parent[find(f)] = find(fs[0])
    comp = defaultdict(list)
    for f in parent:
        comp[find(f)].append(f)
    out = []
    for fs in comp.values():
        if len(fs) < 2:
            continue
        base = min(fs, key=lambda f: (-shown[f], f))
        rs = sorted(set().union(*(rec_of[f] for f in fs)))
        out.append((base, sorted(f for f in fs if f != base), rs))
    return sorted(out)


def dilate(m, r):
    """Расширение булевой маски квадратом (2r+1)."""
    if r <= 0:
        return m.copy()
    out = m.copy()
    h, w = m.shape
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            ys, yd = (slice(dy, h), slice(0, h - dy)) if dy >= 0 else (slice(0, h + dy), slice(-dy, h))
            xs_, xd = (slice(dx, w), slice(0, w - dx)) if dx >= 0 else (slice(0, w + dx), slice(-dx, w))
            out[yd, xd] |= m[ys, xs_]
    return out


def up(m, k):
    return np.repeat(np.repeat(m, k, 0), k, 1)


def rgba(p):
    return np.asarray(Image.open(p).convert("RGBA")).astype(np.float32)


def hd_diff(a, b):
    """Попиксельная разница двух RGBA: max(|цвет с учётом альфы|, |альфа|), 0..255."""
    pa, pb = a[..., :3] * (a[..., 3:] / 255.0), b[..., :3] * (b[..., 3:] / 255.0)
    return np.maximum(np.abs(pa - pb).max(2), np.abs(a[..., 3] - b[..., 3]))


def change_mask(ca, cb, margin):
    """Маска изменений классики (база) и она же с запасом."""
    ch = ca != cb
    return ch, dilate(ch, margin)


def measure(ca, cb, ha, hb, margin):
    """Числа пары: доля изменений классики и разница HD вне и внутри маски."""
    vis = (ca > 0) | (cb > 0)
    ch, chm = change_mask(ca, cb, margin)
    nvis = int(vis.sum())
    k = ha.shape[1] // ca.shape[1]
    d = hd_diff(ha, hb)
    hvis = (ha[..., 3] > 0) | (hb[..., 3] > 0)
    m4 = up(chm, k)
    out_px, in_px = hvis & ~m4, hvis & m4
    return {"ch_px": int(ch.sum()), "frac": (ch.sum() / nvis) if nvis else 0.0,
            "out_diff": float(d[out_px].mean()) if out_px.any() else 0.0,
            "out_over16": float((d[out_px] > 16).mean()) if out_px.any() else 0.0,
            "in_diff": float(d[in_px].mean()) if in_px.any() else 0.0}


def weight(ca, cb, k, margin):
    """Вес своего HD кадра: 1 на изменённых пикселях, мягкий край ВНУТРЬ маски с запасом, 0 вне неё.
    Перо не выходит за up(маска с запасом): там кадр обязан быть основой до байта."""
    ch, chm = change_mask(ca, cb, margin)
    allowed, core = up(chm, k), up(ch, k)
    ramp = max(1, k * margin)
    d = np.zeros(allowed.shape, np.float32)       # расстояние до края разрешённого (шагами x k), до ramp
    m = ~allowed
    for i in range(1, ramp + 1):
        m = dilate(m, 1)
        d[allowed & ~m & (d == 0)] = i
    d[allowed & (d == 0)] = ramp
    t = np.clip(d / ramp, 0, 1)
    w = t * t * (3 - 2 * t)                        # плавный край
    w[core] = 1.0                                  # сами изменённые пиксели - всегда свои
    w[~allowed] = 0.0
    return w[..., None]


def keep_base(out, hbase, w):
    """Где вес 0 - байты основы как есть (RGB под прозрачным тоже), без круга предумножения."""
    z = w[..., 0] <= 0
    out[z] = hbase.astype(np.uint8)[z]
    return out


def compose(hbase, hown, w):
    """HD основы вне маски, свой внутри; смешение в предумноженной альфе."""
    pa, pb = hbase[..., :3] * hbase[..., 3:] / 255.0, hown[..., :3] * hown[..., 3:] / 255.0
    a = hbase[..., 3:] * (1 - w) + hown[..., 3:] * w
    pm = pa * (1 - w) + pb * w
    rgb = np.where(a > 0, pm * 255.0 / np.maximum(a, 1e-6), 0)
    out = np.concatenate([rgb, a], 2)
    return keep_base(np.clip(np.rint(out), 0, 255).astype(np.uint8), hbase, w)


UP_SIGMA = 0.25             # размытие разницы delta, доля k: σ 1 при k 4 - край квадрата базы мягкий


def classic_up(fr, pal, k):
    """Классика в предумноженном RGBA, увеличенная x k: блоки k x k и ОДНО размытие Гаусса (R-351).
    Прежние bilinear плюс гаусс k*0.4 вдвое гасили огонёк в 1-3 пикселя базы."""
    a = np.zeros(fr.shape + (4,), np.float32)
    m = fr > 0
    a[m, :3] = pal[fr[m]]
    a[m, 3] = 255.0
    a[..., :3] *= a[..., 3:] / 255.0
    a = np.repeat(np.repeat(a, k, 0), k, 1)
    return np.stack([gauss(a[..., c], k * UP_SIGMA) for c in range(4)], 2)


def gauss(x, sigma):
    """Размытие Гаусса float-массива (PIL не размывает режим F)."""
    r = max(1, int(round(sigma * 3)))
    g = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    g /= g.sum()
    x = np.pad(x, r, mode="edge")
    x = np.apply_along_axis(lambda v: np.convolve(v, g, "valid"), 0, x)
    return np.apply_along_axis(lambda v: np.convolve(v, g, "valid"), 1, x)


def compose_delta(hbase, cb, cf, pal, w):
    """HD основы плюс гладкая разница классики (кадр минус основа), в предумноженной альфе, по весу w."""
    k = hbase.shape[1] // cb.shape[1]
    d = classic_up(cf, pal, k) - classic_up(cb, pal, k)
    a0 = hbase[..., 3:].astype(np.float32)
    a = np.clip(a0 + d[..., 3:] * w, 0, 255)
    a[(a0 <= 0) & (a < FRINGE_ALPHA)] = 0          # бледная кайма размытия на пустом месте основы - не непрозрачное
    # цвет основы в своей альфе (альфа упала - прямой цвет основы тот же), к нему разница
    pm0 = hbase[..., :3] * np.minimum(a0, a) / 255.0
    dd = d[..., :3] * w
    # разница, которая выходит за [0, a], укорачивается ЦЕЛИКОМ на пиксель: оттенок не съезжает
    with np.errstate(divide="ignore", invalid="ignore"):
        hi = np.where(dd > 0, (a - pm0) / dd, np.inf)
        lo = np.where(dd < 0, -pm0 / dd, np.inf)
    s = np.clip(np.minimum(hi, lo).min(2, keepdims=True), 0, 1)
    pm = np.clip(pm0 + dd * s, 0, a)
    rgb = np.where(a > 0, pm * 255.0 / np.maximum(a, 1e-6), 0)
    return keep_base(np.clip(np.rint(np.concatenate([rgb, a], 2)), 0, 255).astype(np.uint8), hbase, w)


def ring_diff(ca, cb, ha, hb, margin):
    """Разница HD основы и кадра на кольце в 2 пикс базы вокруг маски: один ли это рисунок."""
    _ch, chm = change_mask(ca, cb, margin)
    k = ha.shape[1] // ca.shape[1]
    ring = up(dilate(chm, 2) & ~chm, k) & ((ha[..., 3] > 0) | (hb[..., 3] > 0))
    return float(hd_diff(ha, hb)[ring].mean()) if ring.any() else 0.0


def variants(pack, f):
    """Окончания файлов кадра: '.png', '.v1.png'..."""
    return sorted(n[len(str(f)):] for n in lt.frame_files(pack, f))


def scan(hd_root, label, sets, files, margin):
    """Строки переписи по копии мода hd."""
    rows = []
    for key in sorted(files):
        if not key.endswith(".MCD"):
            continue
        name = key[:-4]
        if sets and name not in sets:
            continue
        pack = Path(hd_root) / (name + ".PCK")
        if not pack.is_dir() or name + ".PCK" not in files:
            continue
        mcd = files[key].read_bytes()
        recs = records(mcd)
        if not recs:
            continue
        shown = Counter(f for f8 in lt.loops(mcd) for f in f8)
        tab = files.get(name + ".TAB")
        frames = xs.read_pck(str(files[name + ".PCK"]), str(tab) if tab else None)
        for base, others, rs in groups(recs, len(frames), shown):
            cb = np.asarray(frames[base])
            hb_files = lt.frame_files(pack, base)
            for f in others:
                cf = np.asarray(frames[f])
                row = {"copy": label, "set": name, "records": ",".join(map(str, rs[:6])) + ("..." if len(rs) > 6 else ""),
                       "base": base, "frame": f, "var_base": len(hb_files) - (1 if "%d.png" % base in hb_files else 0),
                       "var_frame": 0, "ch_px": "", "frac": "", "out_diff": "", "out_over16": "", "in_diff": "",
                       "class": ""}
                hf_files = lt.frame_files(pack, f)
                row["var_frame"] = len(hf_files) - (1 if "%d.png" % f in hf_files else 0)
                has_b, has_f = ("%d.png" % base) in hb_files, ("%d.png" % f) in hf_files
                if cb.shape != cf.shape:
                    row["class"] = "размер классики"
                elif np.array_equal(cb, cf):
                    row["class"] = "близнец (loop_twins)"
                    row["ch_px"], row["frac"] = 0, 0.0
                elif not has_b and not has_f:
                    continue
                elif has_b != has_f:
                    row["class"] = "HD только у " + ("основы" if has_b else "кадра")
                else:
                    ha, hf = rgba(pack / ("%d.png" % base)), rgba(pack / ("%d.png" % f))
                    k = ha.shape[1] // cb.shape[1]
                    if ha.shape != hf.shape or ha.shape[0] != cb.shape[0] * k:
                        row["class"] = "размер HD"
                    else:
                        row.update(measure(cb, cf, ha, hf, margin))
                        if row["frac"] > LIVE_FRAC:
                            row["class"] = "живая анимация"
                        elif name in LIVE_SETS:
                            row["class"] = "живая анимация (контроль)"
                        elif row["out_diff"] >= OUT_DIFF:
                            row["class"] = "мигает" + (" (мягкий)" if row["frac"] <= SOFT_FRAC else "")
                        else:
                            row["class"] = "ровно"
                rows.append(row)
    return rows


COLS = ["copy", "set", "records", "base", "frame", "var_base", "var_frame", "ch_px", "frac",
        "out_diff", "out_over16", "in_diff", "class"]


def write_tsv(rows, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding=ENC_W, newline="") as fh:
        fh.write("\t".join(COLS) + "\n")
        for r in rows:
            fh.write("\t".join(("%.4f" % r[c]) if isinstance(r[c], float) else str(r[c]) for c in COLS) + "\n")


def classic_rgb(fr, pal, k):
    a = np.zeros(fr.shape + (3,), np.uint8)
    a[:] = BG
    m = fr > 0
    a[m] = pal[fr[m]]
    return Image.fromarray(a).resize((fr.shape[1] * k, fr.shape[0] * k), Image.NEAREST)


def on_bg(h):
    im = Image.new("RGB", (h.shape[1], h.shape[0]), BG)
    im.paste(Image.fromarray(h.astype(np.uint8), "RGBA"), (0, 0), Image.fromarray(h.astype(np.uint8), "RGBA"))
    return im


def heat(d):
    """Разница HD картой: 0 тёмная, 32 и выше - ярко-пурпурная."""
    t = np.clip(d / 32.0, 0, 1)
    a = np.zeros(d.shape + (3,), np.uint8)
    a[..., 0] = (24 + 231 * t).astype(np.uint8)
    a[..., 1] = (24 + 40 * t).astype(np.uint8)
    a[..., 2] = (28 + 200 * t).astype(np.uint8)
    return Image.fromarray(a)


def load_pal():
    """Боевая палитра Пираток (R-243): ей нарисована классика террейна на карте."""
    pal = xs.load_palette_file(str(ROOT / "Пиратки" / "Dioxine_XPiratez" / "user" / "mods" / "Piratez"
                                   / "Resources" / "Pals" / "delicious_regular.pal"))
    return np.array(pal[:256], np.uint8)


def sheet(items, pal, path, title, after=None):
    """Строка на пару: классика основы | классика кадра | изменения классики | HD основы | HD кадра |
    разница HD [| HD кадра после | разница после]."""
    if not items:
        return
    cells = []
    for it in items:
        k = it["ha"].shape[1] // it["cb"].shape[1]
        row = [classic_rgb(it["cb"], pal, k), classic_rgb(it["cf"], pal, k)]
        ch = up(it["cb"] != it["cf"], k)
        m = np.array(row[1]).copy()
        m[ch] = (255, 60, 220)
        row.append(Image.fromarray(m))
        row += [on_bg(it["ha"]), on_bg(it["hf"]), heat(hd_diff(it["ha"], it["hf"]))]
        if after is not None:
            na = it["new"].astype(np.float32)
            row += [on_bg(na), heat(hd_diff(it["ha"], na))]
        cells.append((it, row))
    w, h = cells[0][1][0].size
    lab = 18
    ncol = len(cells[0][1])
    heads = ["классика основы", "классика кадра", "изменения", "HD основы", "HD кадра", "разница HD"]
    if after is not None:
        heads += ["HD кадра после", "разница после"]
    im = Image.new("RGB", (ncol * (w + 4) + 4, 22 + len(cells) * (h + lab + 4)), (12, 12, 14))
    dr = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 13)
    except OSError:                             # кириллица во встроенном шрифте PIL - квадраты
        font = ImageFont.load_default()
    dr.text((6, 4), title + "   |   " + " | ".join(heads), fill=(230, 230, 230), font=font)
    for j, (it, row) in enumerate(cells):
        y = 22 + j * (h + lab + 4)
        r = it["row"]
        dr.text((6, y), "%s  %d <- основа %d   классика %d пикс (%.1f%%)   HD вне изменений %.1f, внутри %.1f%s"
                % (r["set"], r["frame"], r["base"], r["ch_px"], 100 * r["frac"], r["out_diff"], r["in_diff"],
                   ("   после (%s, кольцо %.1f): вне %.2f" % (it["mode"], it["ring"], it["after_out"]))
                   if after is not None else ""), fill=(220, 220, 160), font=font)
        for i, c in enumerate(row):
            im.paste(c, (4 + i * (w + 4), y + lab))
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)
    say("  лист:", path)


def build_fix(pack, name, base, f, cb, cf, margin, mode, pal):
    """Новые файлы кадра f: окончание -> RGBA uint8. Набор вариантов - как у основы."""
    out = {}
    own_main = rgba(pack / ("%d.png" % f))
    fv = set(variants(pack, f))
    for rest in variants(pack, base):
        hb = rgba(pack / (str(base) + rest))
        ho = rgba(pack / (str(f) + rest)) if rest in fv else own_main
        if ho.shape != hb.shape:
            return None
        k = hb.shape[1] // cb.shape[1]
        w = weight(cb, cf, k, margin)
        out[rest] = compose(hb, ho, w) if mode == "own" else compose_delta(hb, cb, cf, pal, w)
    return out


def fix_items(rows, root, files, margin, mode, pal):
    """Кандидаты правки для строк 'мигает': [{row, cb, cf, ha, hf, new, files}]."""
    items = []
    frames_cache = {}
    for r in rows:
        if not r["class"].startswith("мигает"):
            continue
        name = r["set"]
        if name not in frames_cache:
            tab = files.get(name + ".TAB")
            frames_cache[name] = xs.read_pck(str(files[name + ".PCK"]), str(tab) if tab else None)
        fr = frames_cache[name]
        pack = Path(root) / (name + ".PCK")
        cb, cf = np.asarray(fr[r["base"]]), np.asarray(fr[r["frame"]])
        ha, hf = rgba(pack / ("%d.png" % r["base"])), rgba(pack / ("%d.png" % r["frame"]))
        rd = ring_diff(cb, cf, ha, hf, margin)
        m = mode if mode != "auto" else ("own" if rd <= RING_SAME else "delta")
        new = build_fix(pack, name, r["base"], r["frame"], cb, cf, margin, m, pal)
        if new is None:
            say("  пропуск %s %d: размер варианта" % (name, r["frame"]))
            continue
        after = measure(cb, cf, ha, new[".png"].astype(np.float32), margin)
        items.append({"row": r, "cb": cb, "cf": cf, "ha": ha, "hf": hf, "new": new[".png"], "files": new,
                      "after_out": after["out_diff"], "mode": m, "ring": rd})
    return items


def write_tsv_fix_row(it):
    r = it["row"]
    return [r["set"], r["frame"], r["base"], r["class"], "%.4f" % r["frac"], "%.2f" % r["out_diff"],
            it["mode"], "%.2f" % it["ring"], "%.2f" % it["after_out"]]


def write_fix_tsv(items, path):
    """Что сделала бы правка с каждой парой: режим, кольцо, HD вне маски после."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        f.write("set\tframe\tbase\tclass\tfrac\tout_before\tmode\tring\tout_after\n")
        for it in items:
            f.write("\t".join(str(x) for x in write_tsv_fix_row(it)) + "\n")
    say("  таблица правки:", path)


def overview(items, n):
    """Обзор для приёмки: худшая пара каждого набора, отдельно own и delta, ровно по размаху out_diff."""
    best = {}
    for it in items:
        key = (it["row"]["set"], it["mode"])
        if key not in best or it["row"]["out_diff"] > best[key]["row"]["out_diff"]:
            best[key] = it
    pick = []
    for mode in ("own", "delta"):
        xs_ = sorted((it for (s_, m), it in best.items() if m == mode), key=lambda it: -it["row"]["out_diff"])
        half = n // 2
        if len(xs_) > half:
            step = (len(xs_) - 1) / (half - 1)
            xs_ = [xs_[round(i * step)] for i in range(half)]
        pick += xs_
    return pick


def read_plan(path):
    """install.tsv плана установки: (набор, кадр) -> {'mode': режим, 'sha': {окончание: sha256[:12]}}."""
    plan = {}
    with open(path, encoding="utf-8-sig") as fh:
        cols = fh.readline().rstrip("\n").split("\t")
        for line in fh:
            r = dict(zip(cols, line.rstrip("\n").split("\t")))
            sha = dict(x.split("=", 1) for x in r["sha"].split())
            plan[(r["набор"], int(r["кадр"]))] = {"mode": r["режим"], "sha": sha}
    return plan


def plan_rows(bad, plan):
    """Строки 'мигает', которые есть в плане. Кадр плана, которого нет среди мигающих, - отказ: установка ушла от плана."""
    keys = {(r["set"], r["frame"]) for r in bad}
    lost = sorted(k for k in plan if k not in keys)
    if lost:
        raise SystemExit("план не совпал с установкой: %d кадров плана не мигают сейчас (%s)"
                         % (len(lost), ", ".join("%s %d" % k for k in lost[:6])))
    return [r for r in bad if (r["set"], r["frame"]) in plan]


def plan_check(items, plan):
    """Байты правки - те, что в плане (sha PNG как его запишет install). -> список расхождений."""
    import hashlib
    errs = []
    for it in items:
        r = it["row"]
        want = plan[(r["set"], r["frame"])]["sha"]
        got = {}
        for rest, arr in it["files"].items():
            buf = io.BytesIO()
            Image.fromarray(arr, "RGBA").save(buf, "PNG")
            got[rest] = hashlib.sha256(buf.getvalue()).hexdigest()[:12]
        if got != want:
            errs.append("%s %d" % (r["set"], r["frame"]))
    return errs


def repo_whole(bp, man, repo, sd, staged):
    """Набор sd в копию user/mods/hd - целиком (все пути манифеста) или None - только правленые кадры.
    Целиком (R-257), если папки нет, она неполная или прочие её файлы не равны манифесту: иначе новый
    кадр встанет рядом со старой основой, и в этой копии петля замигает (AVENGER, BRAIN, UFO1 15.10)."""
    whole = [x for x in man["files"] if x.startswith(sd)]
    if not (repo / sd).is_dir() or len(os.listdir(repo / sd)) < len(whole):
        return whole
    if any(not (repo / x).exists() or bp.sha256_file(str(repo / x)) != man["files"][x]["sha256"]
           for x in whole if x not in staged):
        return whole
    return None


def install(items):
    """Через манифест пака: stage новых байт, снять лишние варианты, install в обе копии (как loop_twins.fix)."""
    import build_hd_pack as bp
    os.chdir(ROOT)
    man = bp.load()
    game, repo = ROOT / bp.TARGETS["game"], ROOT / bp.TARGETS["repo"]
    staged, drop, skip = [], [], 0
    for it in items:
        r = it["row"]
        name, base, f = r["set"], r["base"], r["frame"]
        src = lt.man_frame(man, name, base)
        cur = lt.man_frame(man, name, f)
        if ".png" not in src or ".png" not in cur:
            say("  пропуск %s %d: кадра или основы нет в манифесте" % (name, f))
            skip += 1
            continue
        if any(not (game / rel).exists() or bp.sha256_file(str(game / rel)) != man["files"][rel]["sha256"]
               for rel in list(src.values()) + list(cur.values())):
            say("  пропуск %s %d: файл в установке не равен манифесту" % (name, f))
            skip += 1
            continue
        for rest, arr in it["files"].items():
            buf = io.BytesIO()
            Image.fromarray(arr, "RGBA").save(buf, "PNG")
            trel = "TERRAIN/%s.PCK/%d%s" % (name, f, rest)
            bp.stage(man, trel, buf.getvalue(), generator="anim_flicker", generator_version="anim_flicker.py 15.10",
                     source_path=cur.get(rest, cur[".png"]), approved=True,
                     approval="петля анимации %s: HD %d вне изменений классики - как у основы %d" % (name, f, base),
                     asset_id="%s:%d" % (name, f), source_frame="%s:%d" % (name, base),
                     derived_from=src[rest], replaced=man["files"].get(trel, {}).get("sha256"))
            staged.append(trel)
        for rest, rel in cur.items():
            if rest not in it["files"]:
                man["files"].pop(rel, None)
                drop.append(rel)
    say("  в манифест: файлов %d, снято вариантов %d, пропущено %d" % (len(staged), len(drop), skip))
    if not staged and not drop:
        return 0
    bp.save(man, why="anim_flicker: петли анимации, HD вне изменений классики - как у основы")
    bp.log("save", "", bp.manifest_hash(man)[:16], "anim_flicker: %d файлов, снято вариантов %d" % (len(staged), len(drop)))
    rels = sorted(set(staged))
    say("  game:", bp.install(man, "game", only=rels))
    rrels = []
    by_set = defaultdict(list)
    for rel in rels:
        by_set[rel.rsplit("/", 1)[0] + "/"].append(rel)
    for sd, srels in sorted(by_set.items()):
        whole = repo_whole(bp, man, repo, sd, set(srels))
        rrels += whole if whole else srels
    say("  repo:", bp.install(man, "repo", only=sorted(set(rrels))))
    for rel in drop:
        for root in (game, repo):
            if (root / rel).exists():
                bp.unlink_ro(str(root / rel))
    errs = 0
    for rel in rels:
        for root in (game, repo):
            if bp.sha256_file(str(root / rel)) != man["files"][rel]["sha256"]:
                say("  РАСХОДИТСЯ", root, rel)
                errs += 1
    for sd in sorted({x.rsplit("/", 1)[0] + "/" for x in rels}):
        nm = len([x for x in man["files"] if x.startswith(sd)])
        ng, nr = len(os.listdir(game / sd)), len(os.listdir(repo / sd))
        if not ng == nr == nm:
            say("  ЧИСЛО ФАЙЛОВ", sd, "game", ng, "repo", nr, "манифест", nm)
            errs += 1
    say("  сверка: расхождений", errs)
    return len(staged)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sets", nargs="*", help="только эти наборы")
    ap.add_argument("--copy", choices=list(lt.COPIES), help="только эта копия мода hd")
    ap.add_argument("--margin", type=int, default=2, help="запас вокруг изменений классики, пикс базы")
    ap.add_argument("--sheet", type=int, default=30, help="худших пар на лист")
    ap.add_argument("--fix", action="store_true", help="кандидаты правки и лист до/после (без установки)")
    ap.add_argument("--mode", choices=["auto", "own", "delta"], default="auto",
                    help="что класть внутрь маски: свой HD кадра, разницу классики поверх основы, или по кольцу")
    ap.add_argument("--install", action="store_true", help="с --fix: через манифест в обе копии мода hd")
    ap.add_argument("--only", help="с --fix: только кадры install.tsv плана, байты сверяются с его sha до установки")
    ap.add_argument("--out", default=str(OUT_ART), help="папка листов и кандидатов")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if (a.install or a.only) and not a.fix:
        raise SystemExit("--install и --only только вместе с --fix")
    plan = read_plan(a.only) if a.only else None
    if plan and {p["mode"] for p in plan.values()} != {a.mode}:
        raise SystemExit("режим плана %s, а --mode %s" % (sorted({p["mode"] for p in plan.values()}), a.mode))
    sets = {s.upper() for s in a.sets} if a.sets else None
    files = lt.game_files()
    pal = load_pal()
    out = Path(a.out)
    left = 0
    for label, root in lt.COPIES.items():
        if a.copy and a.copy != label:
            continue
        rows = scan(root, label, sets, files, a.margin)
        tag = "game" if label == "установка" else "repo"
        write_tsv(rows, OUT_TSV / ("flicker_%s.tsv" % tag))
        cnt = Counter(r["class"] for r in rows)
        say("%s (%s): пар %d - %s" % (label, root, len(rows), ", ".join("%s %d" % kv for kv in cnt.most_common())))
        bad = sorted((r for r in rows if r["class"].startswith("мигает")), key=lambda r: -r["out_diff"])
        left += len(bad)
        say("  мигает: %d пар в %d наборах" % (len(bad), len({r["set"] for r in bad})))
        for r in bad[:15]:
            say("    %-18s %3d <- %3d  классика %3d пикс %5.1f%%  HD вне %5.1f  внутри %5.1f"
                % (r["set"], r["frame"], r["base"], r["ch_px"], 100 * r["frac"], r["out_diff"], r["in_diff"]))
        if label != "установка" and not a.copy:
            continue                            # листы и правка - по установке, она равна манифесту
        if not a.fix:
            items = []
            fr_cache = {}
            for r in bad[:a.sheet]:
                if r["set"] not in fr_cache:
                    tab = files.get(r["set"] + ".TAB")
                    fr_cache[r["set"]] = xs.read_pck(str(files[r["set"] + ".PCK"]), str(tab) if tab else None)
                pack = Path(root) / (r["set"] + ".PCK")
                items.append({"row": r, "cb": np.asarray(fr_cache[r["set"]][r["base"]]),
                              "cf": np.asarray(fr_cache[r["set"]][r["frame"]]),
                              "ha": rgba(pack / ("%d.png" % r["base"])), "hf": rgba(pack / ("%d.png" % r["frame"]))})
            sheet(items, pal, out / ("worst_%s.png" % tag), "мигание петель, худшие по HD вне изменений классики")
            continue
        if plan:
            bad = plan_rows(bad, plan)
            say("  по плану %s: кадров %d" % (a.only, len(bad)))
        items = fix_items(bad, root, files, a.margin, a.mode, pal)
        if plan:
            errs = plan_check(items, plan) + (["кадров правки %d, в плане %d" % (len(items), len(plan))]
                                              if len(items) != len(plan) else [])
            if errs:
                raise SystemExit("байты правки не равны плану: %d (%s) - установки нет" % (len(errs), ", ".join(errs[:6])))
            say("  план: байты всех %d кадров равны sha плана" % len(items))
        say("  правка: кандидатов %d, HD вне изменений после - макс %.2f; own %d, delta %d"
            % (len(items), max((it["after_out"] for it in items), default=0.0),
               sum(it["mode"] == "own" for it in items), sum(it["mode"] == "delta" for it in items)))
        write_fix_tsv(items, out / ("fix_%s.tsv" % tag))
        cand = out / "candidates"
        for it in items:
            r = it["row"]
            for rest, arr in it["files"].items():
                p = cand / (r["set"] + ".PCK") / ("%d%s" % (r["frame"], rest))
                p.parent.mkdir(parents=True, exist_ok=True)
                Image.fromarray(arr, "RGBA").save(p)
        for n in range(0, min(len(items), a.sheet * 4), a.sheet):
            sheet(items[n:n + a.sheet], pal, out / ("before_after_%s_%02d.png" % (tag, n // a.sheet)),
                  "мигание петель: до и после (HD основы вне изменений классики)", after=True)
        ov = overview(items, a.sheet)
        sheet(ov, pal, out / ("overview_%s.png" % tag),
              "мигание петель: обзор - по паре на набор, оба режима, весь размах", after=True)
        if a.install:
            install(items)
    return 1 if left else 0


if __name__ == "__main__":
    sys.exit(main())
