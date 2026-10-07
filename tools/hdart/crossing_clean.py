r"""Чистый просмотр перекрёстка ROADS так, как его видит игрок: кадры игры без пара заморозки дампа.

Зачем (замечание специалиста 07.10): лист crossing_build.py sheet собран по дампам Ctrl+F8, а дамп всегда рисует
неподвижное облако пара (Map::hdTestFreeze: цветные клубки на каждой третьей клетке) - они прячут дефекты пола.
Здесь берётся shot.png - обычный кадр игры (OXCE_HD_DUMP через game_hidden.py), снятый через секунду после
кадра дампа: облако заморозки движок снимает сразу после своего кадра (Map::draw, «the fixed test cloud is not the
game's»), курсор и анимация - как у игрока. Диагностический дамп и его меры - отдельно (crossing_build.py sheet).

Метки снимков (census/maps/pilot2/probe_crossing/_dumps/<метка>/shot.png, все без кислотного дождя):
  ракурс 1 (corner_noacid.sav, камера на юните у тротуара 49,9):  classic_na, hd_now_na, new_na
  ракурс 2 (corner_noacid_v2.sav, юнит переставлен на 60,15 - в кадре все четыре угла бордюра): classic_v2,
           hd_now_v2, new_v2
У каждого ракурса камера и свет одни на три метки (сверяется по dump.json).

Лист: 1 - участок целиком в масштабе игры 1:1 (k=4, пиксель экрана 1920x1080); 2 - крупно x3: разметка обеих
ориентаций, вершина V, прямые бордюры, углы 5-8, решётка 13; 3 - поля асфальта и тротуара 1:1 (варианты включены,
oxceHdGroundVariants); 4 - материалы: тротуар, асфальт, камень бордюра - вырезы и числа рисунка (диагностика,
не приёмка: приёмка - глазами по листу).

    py -3.13 tools/hdart/crossing_clean.py [--out census/maps/pilot2/probe_crossing/clean.png]
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crossing_build as cb           # noqa: E402
import crossing_check as cc           # noqa: E402
import sidewalk_probe as sp           # noqa: E402

D = cb.OUT / "_dumps"
SAVES = {"na": cb.OUT / "_game_ref" / "corner_noacid.sav", "v2": cb.OUT / "_game_ref" / "corner_noacid_v2.sav"}
NAMES = {"classic": "классика (режим 0)", "hd_now": "HD сейчас (пак установки)", "new": "новое (сборка new)"}
KINDS = ("classic", "hd_now", "new")
# то, что закрывает карту в кадре игры: панель боя, кнопки этажей, значок справа сверху (пиксели экрана)
HUD = [(320, 855, 1600, 1080), (1518, 688, 1582, 842), (1790, 98, 1902, 198), (0, 0, 90, 100)]
# выбранный юнит (горит - состояние сейва) и стрелка над ним: клетка юнита в каждом ракурсе
UNIT = {"na": (49, 9), "v2": (60, 15)}
ZOOM = 3
# крупно: узел сетки мира в центре выреза, полуширина и полувысота выреза (пиксели экрана), подпись
CLOSE = [
    ((55, 8), 112, 56, "разметка -u (кадр 10): штрихи столбца x=55 и конец штриха у вершины следующей клетки"),
    ((54.5, 15.5), 128, 48, "разметка -v (кадр 11): штрихи ряда y=15"),
    ((55, 12), 112, 56, "вершина V (55,12): штрих -v клетки 54,12 встречает штрих -u клетки 55,11"),
    ((52, 9.5), 112, 56, "прямой передний бордюр 1 (51,9) | асфальт"),
    ((49, 12), 112, 56, "прямой передний бордюр 2 (49,11) | асфальт"),
    ((50, 18), 112, 56, "прямой задний бордюр 3 (50,18) | асфальт"),
    ((58, 9.5), 112, 56, "прямой задний бордюр 4 (58,9) | асфальт"),
    ((51.5, 11.5), 112, 64, "угол 7 (51,11): внутренний угол тротуара"),
    ((58.5, 11.5), 112, 64, "угол 6 (58,11)"),
    ((51.5, 18.5), 112, 64, "угол 5 (51,18)"),
    ((58.5, 18.5), 112, 64, "угол 8 (58,18)"),
    ((52.5, 7.5), 96, 48, "решётка стока 13 (52,7) у переднего бордюра"),
    ((47.5, 17.5), 96, 48, "решётка стока 13 (47,17) у заднего бордюра"),
]
# поля 1:1: узел в центре, полуширина, полувысота, подпись
FIELDS = [((54.5, 15.5), 280, 140, "поле асфальта: клетки 9 и разметка 11 (x 52..57, y 13..18)"),
          ((60, 8.5), 200, 110, "поле тротуара справа (кадр 0, x 59..61, y 6..10)"),
          ((48, 8), 260, 120, "поле тротуара слева (кадр 0 и бордюр 1, x 46..51, y 6..10; урна, ящик, столб - предметы)")]


def shot(tag):
    p = D / tag / "shot.png"
    js_d = json.loads((D / tag / "dump.json").read_text(encoding=cb.ENC))
    k = int(js_d["k"])
    cam = (int(js_d["cameraOffsetX"]) // k, int(js_d["cameraOffsetY"]) // k, int(js_d["cameraOffsetZ"]))
    return Image.open(p).convert("RGB"), k, cam, js_d


def unit_box(view, k, cam):
    X, Y = cb.grid_xy(UNIT[view][0] + 0.5, UNIT[view][1] + 0.5, k, cam)
    return (int(X - 18 * k), int(Y - 44 * k), int(X + 18 * k), int(Y + 10 * k))


def blocked(b, ub=None):
    if ub is not None and b[0] < ub[2] and ub[0] < b[2] and b[1] < ub[3] and ub[1] < b[3]:
        return True
    return b[0] < 0 or b[1] < 0 or b[2] > 1920 or b[3] > 1080 or any(
        b[0] < h[2] and h[0] < b[2] and b[1] < h[3] and h[1] < b[3] for h in HUD)


def gauss_blur(a, s):
    return cb.gauss(a, s)


def material_stats(views, dbg=None):
    """Числа рисунка материалов по кадрам игры: центральные части клеток материала (без края и без того, что
    рисуется поверх пола). Яркость Y; зерно - Y минус размытие 2 пикселя базы; рисунок - корреляция зерна через
    один пиксель базы (4 пикселя экрана) и эксцесс зерна (редкие точки - большой, ровный шум - около 0)."""
    out = {}
    for view, tags in views.items():
        _im, k, cam, js_d = shot(tags["classic"])
        bt, data, k, W, H, cam, img, owner = cc.owners(str(SAVES[view]), js_d)
        covered = cc.cover_masks(str(SAVES[view]), bt, cam, W, H)
        t = owner - 1
        part = np.where(owner > 0, t % 4, -1)
        q = t // 4
        zc, r = np.divmod(q, bt.X * bt.Y)
        yc, xc = np.divmod(r, bt.X)
        floor = (part == 0) & (zc == 0) & ~covered
        hide = np.zeros((H * k, W * k), bool)
        for x0, y0, x1, y1 in HUD + [unit_box(view, k, cam)]:
            hide[max(0, y0):max(0, y1), max(0, x0):max(0, x1)] = True
        rep = lambda a: np.repeat(np.repeat(a, k, 0), k, 1)
        Yi, Xi = np.mgrid[0:H * k, 0:W * k].astype(np.float32)
        sx, sy = (Xi + 0.5) / k - cam[0] - 16, (Yi + 0.5) / k - cam[1] - 24
        gu, gv = (sx / 16 + sy / 8) / 2, (sy / 8 - sx / 16) / 2
        fu, fv = gu - rep(xc), gv - rep(yc)
        frame = np.full((H, W), -1)
        for key in np.unique(q[floor]):
            z, rr = divmod(int(key), bt.X * bt.Y)
            y, x = divmod(rr, bt.X)
            cur = bt.part(z, y, x, 0)
            if cur is not None and bt.sets[cur[0]] == "ROADS":
                frame[floor & (q == key)] = data.mcd("ROADS")[cur[1]]["frames"][0]
        FR = rep(frame)
        inner = (fu > 0.2) & (fu < 0.8) & (fv > 0.2) & (fv < 0.8)
        w1 = cc.KERB_SIDES[1]["+u"]
        cx, cy, n = cb.WINDOW          # только участок перекрёстка: дальние клетки - другие постройки и свет
        hide |= ~rep((xc >= cx - 1) & (xc <= cx + n) & (yc >= cy - 1) & (yc <= cy + n))
        inner &= ~hide
        masks = {"тротуар": (FR == 0) & inner,
                 "асфальт": (FR == 9) & inner,
                 "камень бордюра": (FR == 1) & (fu > 1 - w1 + 0.06) & (fu < 0.96) & (fv > 0.15) & (fv < 0.85) & ~hide}
        if dbg:
            ov = np.asarray(shot(tags["classic"])[0]).astype(np.float32)[:H * k, :W * k].copy()
            for m, c in zip(masks.values(), ((255, 0, 0), (0, 255, 0), (0, 128, 255))):
                ov[m[:ov.shape[0], :ov.shape[1]]] = ov[m[:ov.shape[0], :ov.shape[1]]] * 0.4 + np.array(c) * 0.6
            Image.fromarray(ov.astype(np.uint8)).save(Path(dbg) / ("masks_%s.png" % view))
        for kind, tag in tags.items():
            im = np.asarray(shot(tag)[0]).astype(np.float32)[:H * k, :W * k]
            Y = im @ cb.LUMA
            g = Y - gauss_blur(Y, 2.0 * k)
            for mat, m in masks.items():
                m = m[:im.shape[0], :im.shape[1]]
                mm = m & np.roll(m, -k, 1)
                if m.sum() < 200:
                    continue
                gs = g[m]
                kurt = float(((gs - gs.mean()) ** 4).mean() / max(gs.var() ** 2, 1e-9) - 3)
                corr = float(np.corrcoef(g[mm], np.roll(g, -k, 1)[mm])[0, 1])
                out.setdefault(mat, {}).setdefault(kind, []).append(dict(
                    view=view, n=int(m.sum()), rgb=[round(float(x), 1) for x in im[m].mean(0)],
                    Y=round(float(Y[m].mean()), 1), grain=round(float(gs.std()), 2), kurt=round(kurt, 2),
                    corr=round(corr, 3)))
    return out


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(cb.OUT / "clean.png"))
    a = ap.parse_args()
    views = {"v2": {k: k + "_v2" for k in KINDS}, "na": {k: k + "_na" for k in KINDS}}
    S = {}
    for view, tags in views.items():
        cams = set()
        for kind, tag in tags.items():
            if not (D / tag / "shot.png").exists():
                raise SystemExit("нет кадра %s - снять невидимо (scratchpad cross_dumps2.py / cross_dumps3.py)" % tag)
            S[tag] = shot(tag)
            cams.add((S[tag][2], S[tag][3].get("globalShade")))
        if len(cams) != 1:
            raise SystemExit("ракурс %s: камера или свет у меток разные: %s" % (view, cams))
    k = S["new_v2"][1]
    sh = sp.Sheet(2400, "Перекрёсток ROADS - чистые кадры игры (без пара заморозки дампа), без кислотного дождя, "
                  "k=%d" % k, False)
    sh.im = Image.new("RGB", (2400, 24000), (24, 24, 28))
    sh.d = ImageDraw.Draw(sh.im)
    sh.d.text((14, 10), "Перекрёсток ROADS - чистые кадры игры (без пара заморозки дампа), без кислотного дождя, "
              "k=%d" % k, font=sh.f_t, fill=(255, 255, 255))
    sh.para("Кадр - обычный кадр экрана игры 1920x1080 (невидимый прогон game_hidden.py, через секунду после дампа "
            "Ctrl+F8: облако пара заморозки к этому кадру снято движком). Камера и свет у трёх меток одного ракурса "
            "одни: " + ";  ".join("%s: камера %s, тень %s" % (v, S[t["new"]][2], S[t["new"]][3].get("globalShade"))
                                  for v, t in views.items()) +
            ". Ракурс 2 - юнит переставлен на 60,15 (в кадре все четыре угла бордюра). Юнит в огне - состояние "
            "сейва, не пол. Новая сборка: все 14 кадров участка по 4 варианта, решётка 13 пересобрана по "
            "конструкции классики (07.10, после чистого кадра).", fill=(200, 220, 255))
    # 1. участок целиком 1:1
    _im, k, cam, _ = S["new_v2"]
    cx, cy, n = cb.WINDOW
    xs = [cb.grid_xy(gx, gy, k, cam) for gx, gy in ((cx, cy), (cx + n, cy), (cx, cy + n), (cx + n, cy + n))]
    box = (max(0, int(min(p[0] for p in xs))), max(0, int(min(p[1] for p in xs))),
           min(1920, int(max(p[0] for p in xs))), min(855, int(max(p[1] for p in xs))))
    sh.head("1. Участок целиком в масштабе игры 1:1 (ракурс 2, вырез %d x %d пикселей экрана, без панели боя)" % (
        box[2] - box[0], box[3] - box[1]))
    for kind in KINDS:
        sh.row([(NAMES[kind], S[kind + "_v2"][0].crop(box))])
    # 2. крупно
    sh.head("2. Крупно x%d (пиксель экрана = %d x %d; пиксель базы = %d x %d). Вырез берётся из ракурса, где место не "
            "закрыто панелью боя" % (ZOOM, ZOOM, ZOOM, ZOOM * k, ZOOM * k))
    for (gx, gy), hw, hh, lbl in CLOSE:
        got = None
        for view, tags in views.items():
            X, Y = cb.grid_xy(gx, gy, k, S[tags["new"]][2])
            b = (int(X - hw), int(Y - hh), int(X + hw), int(Y + hh))
            if not blocked(b, unit_box(view, k, S[tags["new"]][2])):
                got = (view, tags, b)
                break
        if got is None:
            sh.para("%s - закрыто панелью боя в обоих ракурсах" % lbl, fill=(255, 140, 140))
            continue
        view, tags, b = got
        sh.para("%s  [ракурс %s]" % (lbl, view))
        sh.row([(NAMES[kd], S[tags[kd]][0].crop(b).resize(((b[2] - b[0]) * ZOOM, (b[3] - b[1]) * ZOOM),
                                                            Image.NEAREST)) for kd in KINDS], gap=12)
    # 3. поля
    sh.head("3. Поля 1:1, варианты включены (oxceHdGroundVariants: движок раскладывает 4 варианта кадра узором и "
            "смешивает соседние)")
    for (gx, gy), hw, hh, lbl in FIELDS:
        got = None
        for view, tags in views.items():
            X, Y = cb.grid_xy(gx, gy, k, S[tags["new"]][2])
            b = (int(X - hw), int(Y - hh), int(X + hw), int(Y + hh))
            if not blocked(b, unit_box(view, k, S[tags["new"]][2])):
                got = (view, tags, b)
                break
        if got is None:
            sh.para("%s - закрыто в обоих ракурсах" % lbl, fill=(255, 140, 140))
            continue
        view, tags, b = got
        sh.para("%s  [ракурс %s]" % (lbl, view))
        sh.row([(NAMES[kd], S[tags[kd]][0].crop(b)) for kd in KINDS], gap=12)
    # 4. материалы
    st = material_stats(views, Path(a.out).parent)
    sh.head("4. Материалы: тротуар, асфальт, камень бордюра (числа - диагностика рисунка, не приёмка)")
    sh.para("Y - средняя яркость; зерно - разброс яркости после вычета размытия в 2 пикселя базы; корр - корреляция "
            "зерна через пиксель базы (крупные пятна - ближе к 1, мелкий шум - к 0); эксцесс - форма разброса "
            "(редкие яркие точки на ровном - большой, обычный шум - около 0). Среднее по ракурсам.", fill=(200, 200, 200))
    with open(Path(a.out).with_suffix(".json"), "w", encoding=cb.ENC) as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    for mat, by in st.items():
        line = "%-15s " % mat
        for kind in KINDS:
            rs = by.get(kind, [])
            if not rs:
                continue
            avg = lambda key: sum(r[key] for r in rs) / len(rs)
            line += "|  %s: Y %.1f, зерно %.2f, корр %.2f, эксцесс %.2f   " % (
                NAMES[kind].split(" (")[0], avg("Y"), avg("grain"), avg("corr"), avg("kurt"))
        sh.para(line, fill=(240, 240, 200))
    mats = [((51.8, 9.5), "камень переднего бордюра 1, тротуар и асфальт рядом"),
            ((47.5, 7.5), "тротуар"), ((55.5, 14.5), "асфальт")]
    for (gx, gy), lbl in mats:
        for view, tags in views.items():
            X, Y = cb.grid_xy(gx, gy, k, S[tags["new"]][2])
            b = (int(X - 64), int(Y - 32), int(X + 64), int(Y + 32))
            if not blocked(b, unit_box(view, k, S[tags["new"]][2])):
                sh.para("%s, x4  [ракурс %s]" % (lbl, view))
                sh.row([(NAMES[kd], S[tags[kd]][0].crop(b).resize((512, 256), Image.NEAREST)) for kd in KINDS], gap=12)
                break
    sh.im = sh.im.crop((0, 0, 2400, sh.y + 8))
    sh.im.save(a.out)
    print("лист: %s (2400 x %d)" % (a.out, sh.y + 8))
    for mat, by in st.items():
        for kind, rs in by.items():
            print(mat, kind, rs)


if __name__ == "__main__":
    main()
