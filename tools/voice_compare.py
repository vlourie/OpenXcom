"""Сверка записей голоса двух сторон одного разговора: что одна сторона послала и что другая получила.

    py -3.13 tools/voice_compare.py <rec стороны A> <rec стороны B> [--names a b] [--a-start ЧЧ:ММ:СС.с]

В каждой папке rec лежат mic.wav (сырой микрофон), sent.wav (после эхоподавителя - что ушло в сеть),
heard.wav (расшифрованный голос собеседника - ровно то, что отдано звуковому устройству) и out.wav
(loopback WASAPI - что Windows реально проиграла). Все 48 кГц моно 16 бит, пишет лаунчер с --record.

Печатает:
  1. каждая сторона отдельно: уровни, что эхоподавитель сделал с голосом (mic против sent), нулевые
     разрывы и щелчки в heard/out/sent;
  2. A/sent -> B/heard и B/sent -> A/heard: задержка по огибающей, затем по каждой секунде речи -
     задержка (её скачки - работа джиттер-буфера), корреляция волны по кадрам 20 мс, кадры, где
     принято молчание; худшие секунды; выпадения (нули в принятом там, где послана речь);
     совпадает ли порча с одновременной речью другой стороны;
  3. out.wav против heard.wav у каждой стороны: следует ли огибающая, совпадает ли волна, усиление,
     разрывы между соседними отсчётами и доля заполнителя 0xAAAA (сломанный loopback);
  4. остаточное эхо: голос собеседника внутри своего sent, свой голос, вернувшийся в heard.

Время печатается по часам стороны A (--a-start - момент начала её записи, из строки лога
«recording the first 10 min»); начало записи B находится по огибающей.
Пример разбора 2026-10-02: docs/research/voice-robot-2026-10-02.md.
"""
import argparse, pathlib, sys, wave
import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
RATE = 48000
FL = RATE // 50      # кадр 20 мс
S = 96               # локальный поиск сдвига +-2 мс


def load(p):
    with wave.open(str(p), "rb") as w:
        assert w.getnchannels() == 1 and w.getsampwidth() == 2 and w.getframerate() == RATE, p
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)


def fdb(x, win):
    n = len(x) // win
    fr = x[:n * win].reshape(n, win).astype(np.float64) / 32768.0
    return 20 * np.log10(np.sqrt((fr * fr).mean(axis=1)) + 1e-9)


def xcorr_fft(a, b):
    """c[k] = sum_n b[n + k] a[n] (кольцевая)."""
    N = 1 << int(np.ceil(np.log2(len(a) + len(b))))
    return np.fft.irfft(np.fft.rfft(b, N) * np.conj(np.fft.rfft(a, N)), N), N


def env_lag(a, b, win):
    """Задержка L в отсчётах: b[t] ~ a[t - L]."""
    ea = np.maximum(fdb(a, win), -60); eb = np.maximum(fdb(b, win), -60)
    ea = ea - ea.mean(); eb = eb - eb.mean()
    c, N = xcorr_fft(ea, eb)
    k = int(np.argmax(c))
    return (k - N if k > N // 2 else k) * win


def ncc_lag(a_seg, b_reg):
    """Где внутри b_reg лучше всего ложится a_seg: смещение в отсчётах и нормированная корреляция."""
    la, lb = len(a_seg), len(b_reg)
    A = a_seg.astype(np.float64); B = b_reg.astype(np.float64)
    c, N = xcorr_fft(A, B)
    c = c[:lb - la + 1]
    cs = np.r_[0.0, np.cumsum(B * B)]
    norms = np.sqrt(np.maximum(cs[la:lb + 1] - cs[:lb - la + 1], 1e-9)) * (np.linalg.norm(A) + 1e-9)
    ncc = c / norms
    k = int(np.argmax(ncc))
    return k, float(ncc[k])


def frame_corr(a, b):
    """a: n*FL отсчётов; b: n*FL + 2S, начинается на S раньше. Лучшая корреляция Пирсона по кадру и уровень b там."""
    n = len(a) // FL
    af = a[:n * FL].astype(np.float64).reshape(n, FL)
    af -= af.mean(axis=1, keepdims=True)
    an = np.linalg.norm(af, axis=1) + 1e-9
    bd = b.astype(np.float64)
    best = np.full(n, -1.0); bsh = np.zeros(n, int)
    for sh in range(-S, S + 1, 6):
        bf = bd[S + sh: S + sh + n * FL].reshape(n, FL)
        bf = bf - bf.mean(axis=1, keepdims=True)
        c = (af * bf).sum(axis=1) / (an * (np.linalg.norm(bf, axis=1) + 1e-9))
        m = c > best
        best[m] = c[m]; bsh[m] = sh
    blev = np.array([fdb(bd[S + bsh[i] + i * FL: S + bsh[i] + (i + 1) * FL], FL)[0] for i in range(n)])
    return best, blev


class Clock:
    def __init__(self, a_start):
        self.t0 = a_start

    def __call__(self, sec):
        t = self.t0 + sec
        return f"{int(t // 3600) % 24:02d}:{int(t % 3600 // 60):02d}:{t % 60:04.1f}"


def side(name, d, clock, t0):
    print(f"\n######## {name}: {d}")
    w = {}
    for k in ("mic", "sent", "heard", "out"):
        p = d / f"{k}.wav"
        if p.exists():
            x = load(p); w[k] = x
            print(f"  {k}.wav {len(x) / RATE:.1f} с, пик {20 * np.log10(np.abs(x.astype(np.int32)).max() / 32768 + 1e-9):.1f} dBFS, "
                  f"rms {fdb(x, len(x))[0]:.1f} dBFS, обрезанных отсчётов {(np.abs(x.astype(np.int32)) >= 32700).sum()}")
    if "mic" in w and "sent" in w:
        F10 = RATE // 100
        m = fdb(w["mic"], F10); s = fdb(w["sent"], F10); n = min(len(m), len(s)); m, s = m[:n], s[:n]
        sp = m > -35
        eaten = sp & (s < m - 20)
        print(f"  микрофон говорит (кадры 10 мс > -35 dBFS): {sp.sum() / 100:.1f} с; средний уровень mic {m[sp].mean():.1f} -> sent {s[sp].mean():.1f} dBFS; "
              f"sent цифровой ноль при речи: {(sp & (s < -80)).sum()} кадров; sent тише mic на 20 дБ и больше: {eaten.sum()} кадров")
        runs, i = [], 0
        while i < n:
            if eaten[i]:
                j = i
                while j < n and eaten[j]: j += 1
                if j - i >= 20: runs.append((i, j - i))
                i = j
            else:
                i += 1
        print(f"  съеденные участки речи >= 200 мс: {len(runs)}" + ("" if not runs else "  " + ", ".join(f"{clock(t0 + a / 100)}/{l * 10} мс" for a, l in runs[:15])))
    for k in ("heard", "out", "sent"):
        if k not in w: continue
        x = w[k]
        z = np.abs(x) < 2
        dz = np.diff(z.astype(np.int8)); st = np.where(dz == 1)[0] + 1; en = np.where(dz == -1)[0] + 1
        if z[0]: st = np.r_[0, st]
        if z[-1]: en = np.r_[en, len(z)]
        gaps = [(a, b - a) for a, b in zip(st, en) if b - a >= RATE // 50]
        jumps = np.where(np.abs(np.diff(x.astype(np.int32))) > 16000)[0]
        print(f"  {k}: нулевых разрывов >= 20 мс: {len(gaps)} (всего {sum(g[1] for g in gaps) / RATE:.1f} с); скачков > 0.5 шкалы между соседними отсчётами: {len(jumps)}")
        print("     rms по 10 с:", " ".join(f"{v:.0f}" for v in fdb(x, RATE * 10)))
    return w


def track(title, a, b, a_t0, far_level, clock):
    """a - послано (sent), b - принято (heard) у другой стороны; far_level - уровни 20 мс собственного sent
    принимающей стороны (одни часы с b) - для отметки одновременной речи."""
    print(f"\n######## {title}")
    lag0 = env_lag(a, b, RATE // 10)
    print(f"  задержка по огибающей: принято = послано {lag0 / RATE:+.1f} с")
    nblk = len(a) // RATE
    lag = lag0
    rows = []; per_frame = []
    R = int(0.06 * RATE)
    for i in range(nblk):
        s0 = i * RATE
        aseg = a[s0:s0 + RATE]
        alev = fdb(aseg, FL)
        speech = alev > -35
        if speech.sum() < 5:
            continue
        b0 = s0 + lag - R
        if b0 < 0 or b0 + RATE + 2 * R > len(b):
            continue
        k, ncc = ncc_lag(aseg, b[b0:b0 + RATE + 2 * R])
        if ncc >= 0.3:
            lag = lag - R + k
        bwin = b[s0 + lag - S: s0 + lag + RATE + S]
        if len(bwin) < RATE + 2 * S:
            continue
        corr, blev = frame_corr(aseg, bwin)
        low = speech & (corr < 0.5)
        drop = speech & (blev < -60)
        fi = np.clip(((s0 + lag) // FL) + np.arange(len(corr)), 0, len(far_level) - 1)
        dt = far_level[fi] > -35
        rows.append((i, lag * 1000 / RATE, ncc, int(speech.sum()), int(low.sum()), int(drop.sum()), float(np.median(corr[speech])), int((speech & dt).sum()), int((low & dt).sum())))
        per_frame += [(corr[j], dt[j], drop[j]) for j in range(len(corr)) if speech[j]]
    if not rows:
        print("  сравнивать нечего"); return lag0
    pf = np.array(per_frame, dtype=float)
    c_all = pf[:, 0]; dt_all = pf[:, 1] > 0
    print(f"  секунд с речью {len(rows)}, кадров речи (20 мс) {len(pf)}; корреляция < 0.5: {(c_all < 0.5).sum()} ({100 * (c_all < 0.5).mean():.1f}%), "
          f"< 0.75: {(c_all < 0.75).sum()} ({100 * (c_all < 0.75).mean():.1f}%); принято молчание: {int(pf[:, 2].sum())}")
    if dt_all.any() and (~dt_all).any():
        print(f"  другая сторона говорит одновременно: {dt_all.sum()} кадров, из них корреляция < 0.5: {100 * (c_all[dt_all] < 0.5).mean():.1f}%; "
              f"молчит: {(~dt_all).sum()} кадров, < 0.5: {100 * (c_all[~dt_all] < 0.5).mean():.1f}%")
    lags = np.array([r[1] for r in rows]); dl = np.diff(lags); big = np.where(np.abs(dl) >= 3)[0]
    print(f"  задержка за разговор: {lags.min():.1f}..{lags.max():.1f} мс; скачков >= 3 мс между соседними секундами речи: {len(big)}; сумма |скачков| {np.abs(dl).sum():.0f} мс")
    if len(big):
        print("    скачки: " + ", ".join(f"{clock(a_t0 + rows[j + 1][0])} {dl[j]:+.0f}" for j in big[:40]))
    print("  по 30 с: кадров речи, корреляция < 0.5 %, принято молчание, задержка мс")
    for b30 in range(0, nblk, 30):
        rr = [r for r in rows if b30 <= r[0] < b30 + 30]
        if not rr: continue
        sp = sum(r[3] for r in rr); lo = sum(r[4] for r in rr); dr = sum(r[5] for r in rr); lg = [r[1] for r in rr]
        print(f"    {clock(a_t0 + b30)}  речь {sp:4d}  плохих {100 * lo / max(1, sp):5.1f}%  молчание {dr:3d}  задержка {min(lg):.0f}..{max(lg):.0f}")
    worst = sorted(rows, key=lambda r: -r[4] / max(1, r[3]))[:12]
    print("  худшие секунды: время, кадров речи, плохих, молчание, медиана корреляции, ncc секунды, задержка мс, одновременная речь (кадров/плохих)")
    for r in sorted(worst):
        print(f"    {clock(a_t0 + r[0])}  речь {r[3]:2d}  плохих {r[4]:2d}  молч {r[5]:2d}  corr {r[6]:.2f}  ncc {r[2]:.2f}  lag {r[1]:.1f}  вместе {r[7]:2d}/{r[8]:2d}")
    return lag0


def dropouts(title, a, b, lag0, a_t0, clock):
    z = np.abs(b) < 2
    dz = np.diff(z.astype(np.int8)); st = np.where(dz == 1)[0] + 1; en = np.where(dz == -1)[0] + 1
    if z[0]: st = np.r_[0, st]
    if z[-1]: en = np.r_[en, len(z)]
    gaps = [(s, e - s) for s, e in zip(st, en) if e - s >= RATE // 50]
    bad = []
    for s, ln in gaps:
        a0 = s - lag0
        if a0 - RATE // 20 < 0 or a0 + ln + RATE // 20 > len(a): continue
        seg = a[a0 + RATE // 40: a0 + ln - RATE // 40] if ln > RATE // 10 else a[a0: a0 + ln]
        lev = fdb(seg, len(seg))[0] if len(seg) else -180
        if lev > -45:
            bad.append((s, ln, lev))
    print(f"\n######## {title}: нулевых разрывов в принятом {len(gaps)}; из них в посланном была речь (> -45 dBFS) - выпадений: {len(bad)}")
    for s, ln, lev in bad[:20]:
        print(f"    {clock(a_t0 + (s - lag0) / RATE)}  {ln * 1000 / RATE:.0f} мс  уровень посланного {lev:.0f} дБ")


def out_probe(name, w, t0, clock):
    if "out" not in w or "heard" not in w:
        return
    h, o = w["heard"], w["out"]
    n = min(len(h), len(o)); h, o = h[:n], o[:n]
    print(f"\n######## {name}: out.wav (что проиграла Windows) против heard.wav (что отдано устройству)")
    W = RATE // 10
    eh = np.maximum(fdb(h, W), -70); eo = np.maximum(fdb(o, W), -70)
    k = min(len(eh), len(eo)); eh, eo = eh[:k] - eh[:k].mean(), eo[:k] - eo[:k].mean()
    print(f"  корреляция огибающих (100 мс, без сдвига): {(eh * eo).sum() / (np.linalg.norm(eh) * np.linalg.norm(eo) + 1e-9):.2f}")
    hw = fdb(h, W)[:k]; ow = fdb(o, W)[:k]
    msk = hw > -35
    if msk.sum():
        print(f"  усиление out над heard при речи (медиана по окнам 100 мс): {np.median(ow[msk] - hw[msk]):+.1f} дБ; при тишине heard < -70: "
              f"{np.median(ow[hw < -70] - hw[hw < -70]) if (hw < -70).sum() else float('nan'):+.1f} дБ")
    jumps = np.where(np.abs(np.diff(o.astype(np.int32))) > 16000)[0]
    aaaa = (o == -21846) | (o == -21845) | (o == -21847)
    print(f"  скачков > 0.5 шкалы между соседними отсчётами: {len(jumps)} ({len(jumps) / (n / RATE):.0f} в секунду); отсчётов, равных заполнителю 0xAAAA (-21846+-1): "
          f"{aaaa.sum()} ({100 * aaaa.mean():.1f}%)")
    print("  по 20 с: ncc волны out~heard (сдвиг до 300 мс), усиление, скачков")
    for s0 in range(0, n - 25 * RATE, 20 * RATE):
        seg = h[s0:s0 + 2 * RATE]
        if fdb(seg, 2 * RATE)[0] < -45:
            continue
        kk, ncc = ncc_lag(seg, o[s0: s0 + 2 * RATE + int(0.3 * RATE)])
        oseg = o[s0 + kk: s0 + kk + 2 * RATE]
        j = (np.abs(np.diff(oseg.astype(np.int32))) > 16000).sum()
        print(f"    {clock(t0 + s0 / RATE)}  ncc {ncc:.2f}  сдвиг {kk * 1000 / RATE:5.1f} мс  усиление {fdb(oseg, 2 * RATE)[0] - fdb(seg, 2 * RATE)[0]:+5.1f} дБ  скачков {j:5d}")
    if len(jumps):
        j = jumps[len(jumps) // 2]
        print(f"  отсчёты out вокруг скачка {clock(t0 + j / RATE)}: {o[j - 12:j + 12].tolist()}")
        print(f"  heard там же:                      {h[j - 12:j + 12].tolist()}")


def echo(title, ref, x, lo_ms, hi_ms, t0, clock):
    """Сколько ref (что эта машина проиграла или послала) есть в x на задержках lo..hi мс."""
    W = RATE // 10
    e = fdb(ref, W)
    cnt = np.convolve((e > -30).astype(int), np.ones(10, int), "valid")
    picked = []
    for i in np.argsort(-cnt):
        if cnt[i] < 6: break
        s0 = i * W
        if s0 + int(hi_ms * RATE / 1000) + RATE >= len(x): continue
        if any(abs(s0 - p) < 20 * RATE for p in picked): continue
        picked.append(s0)
        if len(picked) >= 6: break
    res = []
    for s0 in sorted(picked):
        seg = ref[s0:s0 + RATE]
        lo = int(lo_ms * RATE / 1000); hi = int(hi_ms * RATE / 1000)
        k, ncc = ncc_lag(seg, x[s0 + lo: s0 + hi + RATE])
        res.append((s0 / RATE, (lo + k) * 1000 / RATE, ncc))
    print(f"\n######## {title} (задержки {lo_ms}..{hi_ms} мс): " + "; ".join(f"{clock(t0 + t)} lag {lag:.0f} ncc {ncc:.2f}" for t, lag, ncc in res))
    if res and max(r[2] for r in res) < 0.3:
        print("  эха нет (ncc < 0.3 везде)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rec_a"); ap.add_argument("rec_b")
    ap.add_argument("--names", nargs=2, default=["A", "B"], metavar=("A", "B"))
    ap.add_argument("--a-start", default="00:00:00", help="начало записи стороны A по её часам, ЧЧ:ММ:СС[.с]")
    args = ap.parse_args()
    hh, mm, ss = args.a_start.split(":")
    clock = Clock(int(hh) * 3600 + int(mm) * 60 + float(ss))
    A, B = pathlib.Path(args.rec_a), pathlib.Path(args.rec_b)
    na, nb = args.names

    wa = side(na, A, clock, 0.0)
    lagAB = env_lag(wa["sent"], load(B / "heard.wav"), RATE // 10)
    b_t0 = -lagAB / RATE
    print(f"\nзапись {nb} начинается в {clock(b_t0)} по часам {na} (сдвиг {lagAB / RATE:+.2f} с)")
    wb = side(nb, B, clock, b_t0)

    track(f"голос {na}, как его получил {nb} ({na}/sent -> {nb}/heard)", wa["sent"], wb["heard"], 0.0, fdb(wb["sent"], FL), clock)
    dropouts(f"{nb}/heard против {na}/sent", wa["sent"], wb["heard"], lagAB, 0.0, clock)
    track(f"голос {nb}, как его получил {na} ({nb}/sent -> {na}/heard)", wb["sent"], wa["heard"], b_t0, fdb(wa["sent"], FL), clock)
    dropouts(f"{na}/heard против {nb}/sent", wb["sent"], wa["heard"], env_lag(wb["sent"], wa["heard"], RATE // 10), b_t0, clock)

    out_probe(na, wa, 0.0, clock)
    out_probe(nb, wb, b_t0, clock)

    echo(f"{na}: голос {nb} (heard) внутри своего sent - остаточное эхо после эхоподавителя", wa["heard"], wa["sent"], 0, 400, 0.0, clock)
    echo(f"{nb}: голос {na} (heard) внутри своего sent - остаточное эхо после эхоподавителя", wb["heard"], wb["sent"], 0, 400, b_t0, clock)
    echo(f"{na}: свой sent внутри heard - свой голос, вернувшийся от {nb}", wa["sent"], wa["heard"], 100, 1500, 0.0, clock)
    echo(f"{nb}: свой sent внутри heard - свой голос, вернувшийся от {na}", wb["sent"], wb["heard"], 100, 1500, b_t0, clock)


if __name__ == "__main__":
    main()
