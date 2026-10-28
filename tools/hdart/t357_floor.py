"""XP-000357: пол URBAN_WASTE 40 (целый) и 41 (повреждённый) процедурно по классике, без видеокарты.

40: низкие частоты - классика 40, уложенная в изорешётку (пиксели обода выкинуты и залиты из соседей по
    решётке), сглаженная x4; поэтому прожилки идут через границу ромба. Мелкая фактура - шум на торе
    изорешётки (периодичен по клетке, изотропен на земле). Цвет - рампа индексов 163-174 по яркости.
    Варианты .v1-.v3: те же низкие частоты, отражённые (x, y, x и y), и другое зерно; у края клетки
    (d > 0.9) все варианты равны основному - стык любых двух вариантов бесшовный.
41: то же поле 40 (того же варианта) плюс пятно по яркости классики 41; край пятна уходит в поле неровно
    (рваная кромка по шуму), у края клетки 41 = 40. Варианты 41.v1-v3 - то же отражение, что у 40.v1-v3.
"""
import sys
import numpy as np
from scipy import ndimage as ndi

sys.path.insert(0, r'E:\OpenXCom\tools\hdart')
import water_build as wb          # noqa: E402

K = 4
LUMA = np.array([0.299, 0.587, 0.114], np.float32)
PAL = wb.palette().astype(np.float32)
FR = wb.read_set('URBAN_WASTE')
CELL_PX = 90.5                     # ребро клетки в пикселях HD (128 / sqrt 2): сигма шума в долях клетки
WROWS = 160                        # окно: строки кадра 50..209, центр клетки (строка 130) - в строке 80 окна
WOFF = 50
FLIPS = [(1, 1), (-1, 1), (1, -1), (-1, -1)]      # (x, y) у основного и v1-v3
SHIFTS = [(0, 0), (32, 16), (-32, 16), (0, 32)]     # сдвиг низких частот у v1-v3 (HD px; решётка (64,32), (64,-32))

# параметры вида
P = dict(
    low_sig=0.85,        # сглаживание классики в пикселях базы
    low_gain=0.9,        # усиление низких частот классики
    g1=(0.9, 3.4), g2=(2.2, 3.2), g3=(5.0, 2.6),      # зерно: (сигма HD px, размах в ед. яркости)
    pit_g=((1.3, 7.0), (3.0, 6.0)),
    pit_ref=96.0, pit_span=46.0,
    rag_amp=0.10, rag_d0=0.64, rag_w=0.26,
    ember=0.55, ember_sig=1.2,
)


def smooth(t):
    t = np.clip(t, 0, 1)
    return t * t * (3 - 2 * t)


def dmap_win():
    y, x = np.mgrid[0:WROWS, 0:128].astype(np.float32) + 0.5
    return np.abs(x - 64) / 64 + np.abs(y + WOFF - 130) / 32


def classic_arrays(f):
    a = FR[f]
    m = a != 0
    lum = (PAL[a] @ LUMA) * m
    return a, m, lum


def rim_mask():
    yb, xb = np.mgrid[0:40, 0:32].astype(np.float32) + 0.5
    db = np.abs(xb - 16) / 16 + np.abs(yb - 32.5) / 8
    return db > 0.88


def tiled_lows(f, sig=None, rim_fill=True, shift=(0, 0)):
    """Яркость классики кадра f, уложенная в изорешётку, обод залит из соседей, сглажена x4; окно WROWS x 128."""
    sig = P['low_sig'] if sig is None else sig
    a, m, lum = classic_arrays(f)
    rim = rim_mask() & m
    n = 3
    PX = PY = 24
    W = 32 + 2 * 32 * n + 2 * PX
    H = 40 + 2 * 16 * n + 2 * PY
    ox0, oy0 = 32 * n + PX, 16 * n + PY
    cv = np.zeros((H, W), np.float32)
    ok = np.zeros((H, W), np.float32)
    rm = np.zeros((H, W), bool)
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            ox, oy = ox0 + (i - j) * 16, oy0 + (i + j) * 8
            reg = (slice(oy, oy + 40), slice(ox, ox + 32))
            cv[reg] = np.where(m, lum, cv[reg])
            ok[reg] = np.where(m, 1.0, ok[reg])
            rm[reg] = np.where(m, rim, rm[reg])
    valid = ok * (~rm if rim_fill else 1)
    num = ndi.gaussian_filter(cv * valid, 1.6)
    den = ndi.gaussian_filter(valid, 1.6)
    fill = num / np.maximum(den, 1e-4)
    if rim_fill:
        cv = np.where(rm, fill, cv)
    mean = float((cv[oy0:oy0 + 40, ox0:ox0 + 32] * m).sum() / m.sum())
    hd = np.kron(cv, np.ones((K, K), np.float32))
    hd = ndi.gaussian_filter(hd, sig * K)
    y0 = oy0 * K + WOFF + shift[1]
    x0 = ox0 * K + shift[0]
    return hd[y0:y0 + WROWS, x0:x0 + 128], mean


def torus_noise(seed, sig_px, M=256):
    """Шум на торе изорешётки, единичный разброс; сигма в пикселях HD вдоль земли."""
    rng = np.random.default_rng(seed)
    n = rng.standard_normal((M, M))
    F = np.fft.fft2(n)
    k = np.fft.fftfreq(M)
    ss = sig_px / CELL_PX * M          # сигма в отсчётах тора
    g = np.exp(-2 * (np.pi * ss) ** 2 * (k[:, None] ** 2 + k[None, :] ** 2))
    t = np.real(np.fft.ifft2(F * g))
    t = (t - t.mean()) / t.std()
    return t.astype(np.float32)


_ab = None


def ab_coords():
    global _ab
    if _ab is None:
        y, x = np.mgrid[0:WROWS, 0:128].astype(np.float32) + 0.5
        dx, dy = x - 64, y + WOFF - 130
        _ab = ((dx / 64 + dy / 32) / 2, (dx / 64 - dy / 32) / 2)
    return _ab


def sample_torus(t):
    M = t.shape[0]
    a, b = ab_coords()
    return ndi.map_coordinates(t, [a * M, b * M], order=3, mode='grid-wrap').astype(np.float32)


def grain(seed):
    out = 0
    for i, key in enumerate(('g1', 'g2', 'g3')):
        sg, amp = P[key]
        out = out + amp * sample_torus(torus_noise(seed * 10 + i + 1, sg))
    return out


def flip(arr, fx, fy):
    if fx < 0:
        arr = arr[:, ::-1]
    if fy < 0:
        arr = arr[::-1]
    return arr


def mixw(base, var, w):
    """Вариант внутри, основной у края; разброс сохраняется."""
    nrm = np.sqrt(w * w + (1 - w) ** 2)
    return base * (1 - w) / nrm + var * w / nrm


# рампа цвета по яркости: индексы 163-174 палитры классики, выше 115 - продолжение
RAMP_IDX = [163, 164, 165, 166, 167, 168, 169, 170, 171, 172, 174]


def ramp_rgb(Y):
    idx = np.array(RAMP_IDX)
    col = PAL[idx]
    ly = col @ LUMA
    order = np.argsort(ly)
    ly, col = ly[order], col[order]
    top = col[-1] + (col[-1] - col[-2]) / (ly[-1] - ly[-2]) * 16.0
    ly = np.append(ly, ly[-1] + 16.0)
    col = np.vstack([col, top])
    return np.dstack([np.interp(Y, ly, col[:, c]) for c in range(3)])


def alpha_frame(f):
    a = FR[f] != 0
    return np.kron(a, np.ones((K, K), np.uint8)).astype(np.uint8)


def to_frame(rgb_win, f):
    out = np.zeros((160, 128, 4), np.uint8)
    out[WOFF:, :, :3] = np.clip(np.round(rgb_win[:160 - WOFF]), 0, 255).astype(np.uint8)
    out[..., 3] = alpha_frame(f) * 255
    out[..., :3] = np.where(out[..., 3:4] > 0, out[..., :3], 0)
    return out


def d_weights():
    d = dmap_win()
    w = 1 - smooth((d - 0.45) / 0.45)      # 1 внутри d < 0.45, 0 у края d > 0.9
    return d, w


def pit_arrays():
    """Пятно классики 41: сглаженная яркость и крапины-угли в окне (без отражений)."""
    a, m, lum = classic_arrays(41)
    mf = m.astype(np.float32)
    num = ndi.gaussian_filter(lum * mf, 0.9)
    den = ndi.gaussian_filter(mf, 0.9)
    base = np.where(m, num / np.maximum(den, 1e-4), 0)
    # снаружи маски - ближайшее значение (отражение окна заходит туда; там альфа 0 и край пятна выцвечен)
    idx = ndi.distance_transform_edt(~m, return_distances=False, return_indices=True)
    base = base[tuple(idx)]
    ember = np.isin(a, [104, 105, 106]).astype(np.float32)
    big = ndi.zoom(base, K, order=3, mode='nearest', grid_mode=True)
    emb = ndi.zoom(ember, K, order=1, mode='nearest', grid_mode=True)
    emb = np.clip(ndi.gaussian_filter(emb, P['ember_sig']) * 5.0, 0, 1) * P['ember']
    # окно: строки кадра 50..209; ниже кадра - повтор последней строки
    pad = np.vstack([big, np.repeat(big[-1:], WROWS - (160 - WOFF), 0)])[WOFF:WOFF + WROWS]
    pade = np.vstack([emb, np.zeros((WROWS - (160 - WOFF), 128), np.float32)])[WOFF:WOFF + WROWS]
    return pad, pade


def build(verbose=True):
    d, w = d_weights()
    L0, mean = tiled_lows(40)
    ember_rgb = PAL[105]
    pit, emb = pit_arrays()
    nz_r = [sample_torus(torus_noise(777 + v, 3.5)) for v in range(4)]
    out = {}
    fields = []
    G0 = grain(1)
    for v, (fx, fy) in enumerate(FLIPS):
        Lv = flip(tiled_lows(40, shift=SHIFTS[v])[0], fx, fy) if v else L0
        Lm = mixw(L0 - mean, Lv - mean, w) if v else L0 - mean
        Gv = grain(1 + v) if v else G0
        Gm = mixw(G0, Gv, w) if v else G0
        Y = mean + P['low_gain'] * Lm + Gm
        fields.append(Y)
    # подгонка среднего тона к классике (по маске классики 40, в окне)
    a40 = alpha_frame(40)[WOFF:] > 0
    tgt = np.array([128.5, 87.9, 46.3], np.float32)
    off = 0.0
    for it in range(8):
        c = ramp_rgb(fields[0] + off)[:160 - WOFF][a40].mean(0)
        off -= float(c @ LUMA) - float(tgt @ LUMA)
    if verbose:
        print('сдвиг яркости %.2f' % off)
    for v, Y in enumerate(fields):
        Y = Y + off
        name = '40' if v == 0 else '40.v%d' % v
        out[name] = to_frame(ramp_rgb(Y), 40)
        # 41
        fx, fy = FLIPS[v]
        Pv = flip(pit, fx, fy)
        Ev = flip(emb, fx, fy)
        rag = nz_r[v]
        t = (d + P['rag_amp'] * np.clip(rag, -1, 1) - P['rag_d0']) / P['rag_w']
        band = 1 - smooth(t)
        m = smooth((P['pit_ref'] - Pv) / P['pit_span'])
        pg = 0
        for k, (sg, amp) in enumerate(P['pit_g']):
            pg = pg + amp * sample_torus(torus_noise(5000 + 10 * v + k, sg))
        Ypit = Pv + pg * (0.4 + 0.6 * m)
        mb = m * band
        Y41 = Y * (1 - mb) + Ypit * mb
        rgb = ramp_rgb(Y41)
        eb = (Ev * band)[..., None]
        rgb = rgb * (1 - eb) + ember_rgb * eb
        out['41' if v == 0 else '41.v%d' % v] = to_frame(rgb, 41)
    return out


if __name__ == '__main__':
    import os
    from PIL import Image
    dst = sys.argv[1]
    os.makedirs(dst, exist_ok=True)
    o = build()
    for k, v in o.items():
        Image.fromarray(v, 'RGBA').save(os.path.join(dst, k + '.png'))
    print(sorted(o))
