"""Горки без сетки: объекты рельефа (склоны, кубы, грани пирамид) в цвете классики, фактура без стыков (20.10).

Брак пака у горок (MARS 24-32 пирамида, MARS 10-21 кратеры, POLARPLANE 0-14, MOUNT 27-44): каждый кадр
нарисован отдельно - со своим обводом, рельефом у края и подушкой посередине. На карте грань горки из
нескольких клеток выходит стёганым одеялом: решётка рёбер по клеткам, цвет уведён от классики.

Что делается с кадром:
  1. Тени и цвет - классики, но как в игре, а не из одиночного кадра (R-386): кадры горки перекрываются,
     поэтому цвет берётся по окружениям - все различные соседства +-2 клетки и +-1 этаж из блоков карт всех
     террейнов (до --ctx, R-387), окружение собирается в порядке движка, нормированный гаусс SIG по экрану;
     видимая часть кадра - медиана по окружениям (кроме мелких клочков-щелей и чужого: другой оттенок или
     темнее своего на 12-20%), закрытое соседом - гаусс самого кадра. Оба слоя x4 бикубикой порознь, каждый
     продолжен за свою границу своим цветом, видимый заходит под край соседа на SEEN_PAD: подмена закрытого
     экраном соседа красила грань в его цвет (жёлтый пунктир на задних гранях и боках кубов MARS там, где их
     видно), а общий слой подмешивал закрытый свой цвет в видимый край (тёмная нитка).
  2. Фактура - поле на торе 64 x 32 пикс x4: сдвиг соседней клетки (64, 32), (64, -32) и этажа (0, 96)
     - все кратны тору, поэтому поле на стыке любых двух кадров набора (рядом и друг над другом) одно и то
     же. Спектр поля - средний спектр высоких частот яркости пака по внутренним окнам кадров (--tex), фаза
     случайная: рисунок пака (рябь, зерно) сохраняет масштаб и направление, но не держит рамку клетки.
     Сдвиг P_Level записи учитывается (поле привязано к экрану, а не к кадру).
  3. Яркость: цвет классики умножается на 1 + поле; разброс поля - разброс высоких частот пака x --gain.
     --detail pack (скалы, кратеры): внутри кадра вместо поля - мелочь самого пака (минус гаусс HPD) x --pgain,
     к стыку (ближе RIMB пикс базы) плавно уходит в поле - трещины пака остаются, его обвод клетки нет.
  4. Альфа: xBRZ x4 маски классики с перехлёстом OVERLAP пикс x4 (R-291), под перехлёстом - тот же цвет.

    py tools/hdart/relief_object.py --set MARS --frames 24-32 --out <папка>/TERRAIN
Проверка - офлайн-кусок карты (классика | пак | новое) и игровой кадр через floor_batch.
"""
import argparse
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ground_seam as gs     # noqa: E402
import sprite_scale as ss    # noqa: E402
import water_build as wb     # noqa: E402

K = 4
TW, TH = 64, 32               # тор поля x4: решётка клеток и этажей
HP = 4.0                      # высокие частоты пака: минус нормированный гаусс HP пикс x4
OVERLAP = 2                   # перехлёст альфы, пикс x4
HPD = 6.0                     # --detail pack: мелочь пака - минус нормированный гаусс HPD пикс x4
SEEN_PAD = 4                  # видимый слой заходит в закрытое на столько пикс x4 (под край соседа)
RIMB = 2.0                   # --detail pack: ширина перехода к полю у стыка, пикс базы
LUMA = np.array([0.299, 0.587, 0.114], np.float32)
ALPHA = "xbrz"                # --alpha near: силуэт классики x4 как есть (для проверки стыков)


def frames_arg(spec):
    out = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            out += list(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    return out


def plevels(s):
    """Кадр -> P_Level первой записи MCD, где он кадр 0 (сдвиг рисования вверх, пикс базы)."""
    recs, plev = wb.records(s)
    out = {}
    for r, p in zip(recs, plev):
        out.setdefault(r[0], p)
    return out


MEDIAN = False                # --median: медиана 3x3 перед гауссом (на POLARPLANE хуже - проба 20.10)


def median3(rgb, w):
    """Медиана 3 x 3 по непрозрачным пикселям (по каналам): тонкая линия в пиксель - меньшинство окна и уходит.
    Тёмный обвод верха у кадров классики (POLARPLANE: край 188 против 225 внутри) после гаусса собирался в нитку
    по каждому стыку; в классике он рассыпан дизерингом и не виден. Граница граней (большие области) остаётся."""
    p = np.pad(np.where(w[..., None] > 0, rgb, np.nan), ((1, 1), (1, 1), (0, 0)), constant_values=np.nan)
    win = np.lib.stride_tricks.sliding_window_view(p, (3, 3), axis=(0, 1)).reshape(rgb.shape[0], rgb.shape[1], 3, 9)
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        m = np.nanmedian(win, -1)
    return np.where(w[..., None] > 0, m, 0).astype(np.float32)


def norm_gauss(rgb, w, sg):
    if MEDIAN:
        rgb = median3(rgb, w)
    num = np.dstack([wb.gauss(rgb[..., c] * w, sg) for c in range(3)])
    return num / np.maximum(wb.gauss(w, sg), 1e-4)[..., None]


def up(img):
    h, w = img.shape[:2]
    return np.dstack([np.asarray(Image.fromarray(np.ascontiguousarray(img[..., c], np.float32), "F")
                                 .resize((w * K, h * K), Image.BICUBIC)) for c in range(img.shape[2])])


def tex_spectrum(s, frames):
    """Средняя амплитуда спектра окон TH x TW высоких частот яркости пака, разброс этих частот."""
    amp = np.zeros((TH, TW), np.float64)
    n, var = 0, []
    for f in frames:
        p = gs.pack_dir(s) / ("%d.png" % f)
        if not p.exists():
            continue
        im = gs.load_pack(s, f)
        a = (im[..., 3] > 250).astype(np.float32)
        y = im[..., :3] @ LUMA
        hi = y - wb.gauss(y * a, HP) / np.maximum(wb.gauss(a, HP), 1e-4)
        # внутренние окна: целиком в непрозрачном и дальше 6 пикс от края (рамка пака - не фактура)
        inner = wb.gauss(a, 3.0) > 0.999
        H, W = a.shape
        for y0 in range(0, H - TH + 1, TH // 2):
            for x0 in range(0, W - TW + 1, TW // 4):
                if inner[y0:y0 + TH, x0:x0 + TW].all():
                    win = hi[y0:y0 + TH, x0:x0 + TW]
                    win = win - win.mean()
                    amp += np.abs(np.fft.fft2(win))
                    var.append(float(win.var()))
                    n += 1
    if not n:
        return None, 0.0
    return amp / n, float(np.sqrt(np.mean(var)))


def torus(amp, seed, iso=True):
    """Поле на торе: амплитуда спектра пака, фаза случайная. iso - амплитуда усреднена по кольцу в координатах
    земли (экранный y вдвое): у направленной ряби пака на торе 64 x 32 иначе в каждой клетке встаёт один и
    тот же значок (проба MARS 20.10)."""
    ph = np.fft.fft2(np.random.default_rng(seed).standard_normal((TH, TW)))
    ph = ph / np.maximum(np.abs(ph), 1e-9)
    a = amp.copy()
    if iso:
        ky = np.fft.fftfreq(TH)[:, None]
        kx = np.fft.fftfreq(TW)[None, :]
        r = np.sqrt(kx * kx + (ky / 2) ** 2)
        b = np.digitize(r, np.linspace(0, r.max() + 1e-6, 17))
        mean = np.bincount(b.ravel(), a.ravel(), minlength=18) / np.maximum(np.bincount(b.ravel(), minlength=18), 1)
        a = mean[b]
    a[0, 0] = 0
    t = np.real(np.fft.ifft2(a * ph)).astype(np.float32)
    return t / max(float(t.std()), 1e-6)


def grow(a):
    """Максимум по 4 соседям, за кадром - 0 (не np.roll: R-239)."""
    p = np.pad(a, 1)
    return np.maximum.reduce([p[:-2, 1:-1], p[2:, 1:-1], p[1:-1, :-2], p[1:-1, 2:]])


def big_parts(m, frac):
    """Маска без связных клочков (4 соседа) меньше frac от самого большого."""
    lab = np.zeros(m.shape, np.int32)
    sizes = [0]
    for y0, x0 in zip(*np.nonzero(m)):
        if lab[y0, x0]:
            continue
        k = len(sizes)
        lab[y0, x0] = k
        st, n = [(y0, x0)], 0
        while st:
            y, x = st.pop()
            n += 1
            for yy, xx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= yy < m.shape[0] and 0 <= xx < m.shape[1] and m[yy, xx] and not lab[yy, xx]:
                    lab[yy, xx] = k
                    st.append((yy, xx))
        sizes.append(n)
    if len(sizes) < 2:
        return m
    keep = np.array(sizes) >= frac * max(sizes)
    keep[0] = False
    return keep[lab]


def spread(v, n):
    """NaN-пиксели - среднее соседей-чисел (4 соседа), n проходов: цвет видимого у края в полосу за ним."""
    v = v.copy()
    for _ in range(n):
        ok = ~np.isnan(v[..., 0])
        p = np.pad(np.where(ok[..., None], v, 0), ((1, 1), (1, 1), (0, 0)))
        q = np.pad(ok.astype(np.float32), 1)
        s = p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:]
        k = q[:-2, 1:-1] + q[2:, 1:-1] + q[1:-1, :-2] + q[1:-1, 2:]
        add = ~ok & (k > 0)
        v[add] = s[add] / k[add][:, None]
    return v


_W = []


def WORLD():
    if not _W:
        _W.append(World())
    return _W[0]


CW, CH, OX, OY = 224, 232, 96, 112     # холст окружения, пикс базы; кадр клетки (0, 0, 0) - в (OX, OY)
NB = 2                                   # окружение: клетки +-NB по x, y и +-1 этаж


class World:
    """Классика наборов, записи MCD (кадр 0, P_Level) и блоки карт всех террейнов Пираток."""

    def __init__(self):
        import hill_census as hc
        import pck_census as pc
        self.pc, self.hc = pc, hc
        mod = wb.INST / "user" / "mods" / "Piratez"
        self.files = pc.Files([str(mod), str(wb.INST / "standard" / "xcom1"), str(wb.INST / "UFO")])
        self.terrains = pc.collect_terrains(str(mod))
        self.recs, self.cls = {}, {}

    def rec(self, s):
        """(кадр 0, P_Level) записей MCD - тем же поиском файла, что перепись (pck_census.Files): wb.records не
        видит standard, размер набора выходил 0, и номера записей соседей по блоку съезжали."""
        if s not in self.recs:
            p = self.files.find(os.path.join("TERRAIN", s + ".MCD"))
            b = open(p, "rb").read() if p else b""
            R = self.pc.MCD_RECORD
            self.recs[s] = [(b[i], b[i + 49]) for i in range(0, len(b) - R + 1, R)]
        return self.recs[s]

    def frame(self, s, f):
        if s not in self.cls:
            try:
                self.cls[s] = wb.read_set(s)
            except Exception:                                   # noqa: BLE001
                self.cls[s] = []
        c = self.cls[s]
        return c[f] if f < len(c) else None


def contexts(W, s, frames, maxn):
    """Кадр -> до maxn разных окружений из блоков карт: [(клетка, часть, {(dx, dy, dz, часть): (набор, кадр, P_Level)})]."""
    want = set(frames)
    out = {f: [] for f in frames}
    seen = {f: set() for f in frames}
    terr = {k: t for k, t in W.terrains.items() if s in (t.get("mapDataSets") or [])}
    for _tn, _bn, sets, g in W.hc.blocks_of(W.files, terr):
        sizes = {q: len(W.rec(q)) for q in sets}

        def look(v):
            if not v:
                return None
            q, r = W.pc.resolve(v, sets, sizes)
            if q is None or r >= len(W.rec(q)):
                return None
            f0, pl = W.rec(q)[r]
            return (q, f0, pl)

        for (x, y, z), cell in g.items():
            for p in range(4):
                me = look(cell[p])
                if not me or me[0] != s or me[1] not in want or len(out[me[1]]) >= maxn:
                    continue
                env = {}
                for dz in (-1, 0, 1):
                    for dy in range(-NB, NB + 1):
                        for dx in range(-NB, NB + 1):
                            c2 = g.get((x + dx, y + dy, z + dz))
                            if c2:
                                for p2 in range(4):
                                    q = look(c2[p2])
                                    if q:
                                        env[(dx, dy, dz, p2)] = q
                key = tuple(sorted(env.items()))
                if key in seen[me[1]]:
                    continue
                seen[me[1]].add(key)
                out[me[1]].append((p, env))
    return out


def inner_dist(m, maxd=6):
    """Расстояние внутрь маски до её края, пикс базы (крайний пиксель - 0.5), не больше maxd + 0.5."""
    d = np.full(m.shape, maxd + 0.5, np.float32)
    cur = m.copy()
    for i in range(maxd):
        p = np.pad(cur, 1)
        inner = cur & p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]
        d[cur & ~inner] = i + 0.5
        cur = inner
    return d


def context_base(W, s, f, ctx, pal, sig):
    """Цвет кадра f по окружениям: классика окружения в порядке рисования (этаж, y, x, часть), нормированный
    гаусс по экрану, вырезана видимая часть кадра; по окружениям медиана (среднее серело у края плоского верха:
    сосед на разных картах то белый верх, то серый склон - сетка ниток по POLARPLANE 20.10).
    -> (видимое rgb, где видно хоть раз; экран окружения rgb, где он есть; до стыка, пикс базы)"""
    cl = W.frame(s, f)
    H, Wd = cl.shape
    vis, env_ = [], []
    # закрытое соседом и пустое вокруг - тоже сглаженный экран: бикубика x4 подмешивает эти пиксели
    # в видимый край, и собственный цвет кадра под соседом давал тёмную нитку по стыку (MARS 20.10)
    jd = np.full((H, Wd), 99.0, np.float32)     # до ближайшего стыка по всем окружениям, пикс базы
    for p, env in ctx:
        C = np.zeros((CH, CW, 3), np.float32)
        M = np.zeros((CH, CW), np.float32)
        own = np.zeros((CH, CW), bool)
        for (dx, dy, dz, p2) in sorted(env, key=lambda k: (k[2], k[1], k[0], k[3])):
            q, fr, pl = env[(dx, dy, dz, p2)]
            a = W.frame(q, fr)
            if a is None:
                continue
            X, Y = OX + (dx - dy) * 16, OY + (dx + dy) * 8 - dz * 24 - pl
            h, w = a.shape
            if X < 0 or Y < 0 or X + w > CW or Y + h > CH:
                continue
            m = a != 0
            C[Y:Y + h, X:X + w][m] = pal[a[m]]
            M[Y:Y + h, X:X + w][m] = 1
            own[Y:Y + h, X:X + w][m] = (dx, dy, dz, p2) == (0, 0, 0, p)
        Cs = norm_gauss(C, M, sig)
        pl0 = env[(0, 0, 0, p)][2]
        if os.environ.get("RO_DUMP"):
            n = len(list(Path(os.environ["RO_DUMP"]).glob("%s_%d_*.png" % (s, f))))
            if n < 3:
                im = C.copy()
                im[own] = im[own] * 0.5 + np.array([255, 0, 255], np.float32) * 0.5
                Path(os.environ["RO_DUMP"]).mkdir(parents=True, exist_ok=True)
                Image.fromarray(np.clip(np.concatenate([im, Cs], 1), 0, 255).astype(np.uint8)).resize(
                    (CW * 4, CH * 2), Image.NEAREST).save(Path(os.environ["RO_DUMP"]) / ("%s_%d_%d.png" % (s, f, n)))
        win = (slice(OY - pl0, OY - pl0 + H), slice(OX, OX + Wd))
        sub_own = own[win]
        cs = Cs[win]
        vis.append(np.where(sub_own[..., None], cs, np.nan))
        env_.append(np.where((wb.gauss(M, sig)[win] > 0.05)[..., None], cs, np.nan))
        jd = np.minimum(jd, np.where(sub_own, inner_dist(sub_own), 99.0))
    with np.errstate(all="ignore"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            v = np.nanmedian(np.stack(vis), 0)
            e = np.nanmedian(np.stack(env_), 0)
    return v, e, jd


def build(s, frames, tex_frames, out, sig, gain, seed, maxn=400, detail="field", pgain=1.0, dry=False):
    pal = wb.palette().astype(np.float32)
    cl = wb.read_set(s)
    pl = plevels(s)
    amp, sd = tex_spectrum(s, tex_frames)
    if amp is None:
        raise SystemExit("нет внутренних окон пака у %s %s - фактуру брать неоткуда" % (s, tex_frames))
    T = torus(amp, seed)
    print("%s: фактура - разброс %.1f (x gain %.2f), окна из %d кадров" % (s, sd, gain, len(tex_frames)))
    frames = [f for f in frames if f < len(cl) and (cl[f] != 0).sum() >= 4]
    ctx = contexts(WORLD(), s, frames, maxn) if maxn > 0 else {f: [] for f in frames}
    res = {}
    for f in frames:
        c = cl[f]
        w = (c != 0).astype(np.float32)
        base = norm_gauss(pal[c], w, sig)
        jd = inner_dist(c != 0)
        if ctx[f]:
            # видимое в окружениях - сглаженная классика экрана: у стыка тот же цвет, что у соседа (п. 1)
            v, e, jd = context_base(WORLD(), s, f, ctx[f], pal, sig)
            seen = ~np.isnan(v[..., 0])
            # видимое щелью в 1 пикс между соседями (бок куба MARS 23 в толще пирамиды) - не цвет грани, а смесь
            # соседей по гауссу экрана: x4 давала тёмный шов по боку, где куб открыт (20.10). Такие щели - свой цвет
            # Щель - отдельный клочок, мелкий против главного; размыканием нельзя: оно же срезало ступеньки края
            # ромба пола POLARPLANE:8, и свой край там давал тёмный пунктир по стыкам
            seen = big_parts(seen, 0.3)
            print("  %s:%d  окружений %d, видно %.0f%%" % (s, f, len(ctx[f]), 100.0 * seen.sum() / max(1, (c != 0).sum())))
        else:
            seen = np.zeros(c.shape, bool)
        if seen.any():
            # два слоя, каждый x4 отдельно и продолжен за свою границу своим же цветом: видимое - экран окружений,
            # закрытое соседом - свой цвет кадра. Бикубика по одному слою подмешивала закрытый свой цвет в видимый
            # край (тёмная нитка R-386), а подмена закрытого экраном красила грань в цвет соседа: бок куба MARS 23
            # и задняя грань 30/32 под жёлтым верхом соседа - жёлтый пунктир там, где их видно (уровень камеры,
            # ступенчатая пирамида Сидонии, 20.10)
            # видимое, уведённое от своего цвета далеко, - не подушка классики у стыка, а чужое на экране (тёмный
            # оранжевый задних граней по гауссу экрана у острия верха куба MARS 23 - тёмный штрих на каждом верхе при
            # срезе уровня камеры). Подушки у стыков - до +-13% яркости, чужое - темнее на 20-25%
            # Сравнение по оттенку (цвет / яркость) и по яркости только вниз: светлее своего - это и есть починка
            # стыка (край верха POLARPLANE:8 свой 160-200, на экране 240), отбрасывать её нельзя
            vv = np.nan_to_num(v)
            yv, yb = vv @ LUMA + 8.0, base @ LUMA + 8.0
            d = np.linalg.norm(vv / yv[..., None] - base / yb[..., None], axis=-1)
            wv = (np.clip((0.3 - d) / 0.15, 0, 1) * np.clip((yv / yb - 0.80) / 0.08, 0, 1))[..., None]
            v = np.where(seen[..., None], np.nan_to_num(v) * wv + base * (1 - wv), np.nan)
            vf = spread(v, 4)
            vf = np.where(np.isnan(vf), base, vf)
            of = spread(np.where(seen[..., None], np.nan, base), 4)
            of = np.where(np.isnan(of), base, of)
            # за силуэтом (перехлёст альфы) - тоже продолжение видимого: свой край там - подушка классики, и
            # перехлёст ложился на соседа тёмным пунктиром по стыкам плоских верхов POLARPLANE
            # и на SEEN_PAD пикс x4 в закрытое: край соседа - xBRZ, а не ступенька nearest, и между ними выглядывал
            # свой закрытый (тёмный бок под верхом соседа) - тёмный пунктир по стыкам верхов POLARPLANE
            sk = np.repeat(np.repeat((seen | (c == 0)).astype(np.float32), K, 0), K, 1)
            for _ in range(SEEN_PAD):
                sk = np.maximum(sk, grow(sk))
            ws = wb.gauss(sk, 1.0)[..., None]
            rgb = up(vf) * ws + up(of) * (1 - ws)
        else:
            rgb = up(base)
        H, W = rgb.shape[:2]
        yo = pl.get(f, 0) * K
        rows = (np.arange(H) - yo) % TH
        field = T[rows][:, np.arange(W) % TW]
        y = rgb @ LUMA
        det = gain * sd * field
        pp = gs.pack_dir(s) / ("%d.png" % f)
        hi3 = None
        if detail in ("pack", "packrgb") and pp.exists():
            # мелочь пака (трещины, камни) внутри кадра; у стыка с соседом на любой карте (jd) - поле (п. 3а)
            pk = gs.load_pack(s, f)
            if pk.shape[:2] == rgb.shape[:2]:
                pa = np.clip((pk[..., 3] - 128.0) / 127.0, 0, 1)
                yp = pk[..., :3] @ LUMA
                hi = yp - wb.gauss(yp * pa, HPD) / np.maximum(wb.gauss(pa, HPD), 1e-4)
                wd = np.clip((up(jd[..., None])[..., 0] - 0.5) / RIMB, 0, 1)
                wd = wd * wd * (3 - 2 * wd) * (wb.gauss(pa, 2.0) > 0.98)
                if detail == "packrgb":
                    # мох на камне MOUNTROCK - мелочь цвета, а не яркости: по одной яркости склон выходил мылом
                    # (цвет классики после гаусса - ровная олива), поэтому мелочь пака по трём каналам
                    g = np.maximum(wb.gauss(pa, HPD), 1e-4)
                    lo = np.dstack([wb.gauss(pk[..., i] * pa, HPD) / g for i in range(3)])
                    hi3 = wd[..., None] * pgain * (pk[..., :3] - lo)
                    det = (1 - wd) * det
                else:
                    det = wd * pgain * hi + (1 - wd) * det
        rgb = rgb * (1.0 + det / np.maximum(y, 16.0))[..., None]
        if hi3 is not None:
            rgb = rgb + hi3
        # альфа: xBRZ x4 маски, перехлёст OVERLAP; nearest x4 не даёт дыр в стыке (R-291)
        rgba = np.dstack([pal[c], w * 255]).astype(np.float32)[None]
        near = wb.blk(w)
        al = ss.xbrz_scale(rgba, K)[0][..., 3] / 255.0 if ALPHA == "xbrz" else near.copy()
        for _ in range(OVERLAP):
            al = np.maximum(al, grow(al) * near)
        al = np.clip(al, 0, 1)
        res[f] = (rgb, al)
        if not dry:
            gs.save_rgba(rgb, al, out, s, str(f))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", required=True)
    ap.add_argument("--frames", required=True, help="кадры: 24-32,10")
    ap.add_argument("--tex", default="", help="кадры пака для спектра фактуры (по умолчанию --frames)")
    ap.add_argument("--out", required=True, help="папка TERRAIN партии")
    ap.add_argument("--sig", type=float, default=1.0, help="гаусс классики, пикс базы")
    ap.add_argument("--gain", type=float, default=0.8)
    ap.add_argument("--seed", type=int, default=5)
    ap.add_argument("--pack-root", default=None)
    ap.add_argument("--alpha", choices=("xbrz", "near"), default="xbrz")
    ap.add_argument("--ctx", type=int, default=400,
                    help="разных окружений кадра из блоков карт (0 - кадр сам по себе); первые 12 не представительны: "
                         "бок склона MOUNT 27 в них закрыт соседом, а на карте Сибири открыт")
    ap.add_argument("--detail", choices=("field", "pack", "packrgb"), default="field",
                    help="мелочь внутри кадра: field - только поле (гладкие грани), pack - трещины пака (скалы), "
                         "packrgb - мелочь пака по цвету (мох на камне)")
    ap.add_argument("--pgain", type=float, default=1.0, help="--detail pack: сила мелочи пака")
    ap.add_argument("--hpd", type=float, default=None, help="--detail pack: гаусс мелочи пака, пикс x4 (по умолчанию %g)" % 6.0)
    ap.add_argument("--median", action="store_true", help="медиана 3x3 перед гауссом")
    a = ap.parse_args()
    global ALPHA, MEDIAN, HPD
    if a.hpd:
        HPD = a.hpd
    MEDIAN = a.median
    ALPHA = a.alpha
    if a.pack_root:
        gs.PACK_ROOT = a.pack_root
    fr = frames_arg(a.frames)
    build(a.set, fr, frames_arg(a.tex) if a.tex else fr, a.out, a.sig, a.gain, a.seed, a.ctx, a.detail, a.pgain)
    print("записано %d кадров в %s" % (len(fr), Path(a.out) / (a.set + ".PCK")))


if __name__ == "__main__":
    main()
