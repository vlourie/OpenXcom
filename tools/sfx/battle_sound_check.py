"""Доказать скрытым прогоном боя, что звук играет: реплики бойца (voiceSets) и шаги мода hd_test_steps.

Два скрытых прогона одного боя параллельно (tools/game_hidden.py, драйвер звука disk):
  with    - моды шагов и голосов включены;
  without - те же, но без мода шагов (шаги Пираток по материалу пола).
Сценарий одинаковый: Tab x4 выбирает бойца (камера встаёт на него), щелчок по нему - «отстань»,
три раза туда-обратно на соседнюю клетку - «пошёл» и шаги. Частота реплик в прогоне - 100 %
(пробный мод zz_hd_sound_probe в своей папке модов: соединения на моды установки + он), иначе
голос то есть, то нет (выбор 70 %, ход 35 %, «отстань» 20 %).

Запись сверяется с самими файлами звуков: поиск совпадений (нормированная корреляция) с
вычитанием найденного - реплика под шагами не прячет шаги. Итог: report.md, energy.png и вердикт.
    py -3.13 tools/sfx/battle_sound_check.py
    py -3.13 tools/sfx/battle_sound_check.py --analyse-only     # разобрать готовые записи заново
Нужны numpy, scipy, Pillow и ffmpeg в PATH. Игра - только скрыто (game_hidden.py, R-124).
"""
import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from scipy.signal import fftconvolve, resample_poly

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).resolve().parents[2]
GAME = ROOT / "Пиратки" / "Dioxine_XPiratez"
MODS = GAME / "user" / "mods"
SAVE = ROOT / "census" / "collapse" / "battles" / "collapse_STR_GOVT_BASE_DEFENSE_1.sav"
PROBE = "zz_hd_sound_probe"
RATE = 22050
SR = 11025               # сверка на половинной частоте: шаги и голос там целы, считать вчетверо быстрее
MIN_GAIN = 0.2           # меньше - не звук сценария, а тихое случайное сходство
FILLER_KEY = "296"      # F15: ничем не занята, держит паузу в очереди клавиш
# центр ромба клетки бойца, на которого встала камера, в пикселях базового экрана (дамп / 4); клетка (a, b)
# от бойца - (CX + 16(a-b), CY + 8(a+b)). (256,136) - нижняя вершина ромба: щелчок уходил в соседнюю клетку
CX, CY = 256, 128

# сценарий: (что, a, b) - щелчок по клетке бойца + (a, b) или пауза 1,2 с
SCENARIO = [("click", 0, 0), ("wait", 0, 0), ("wait", 0, 0)]
for _ in range(3):
    SCENARIO += [("click", 0, 1), ("wait", 0, 0), ("wait", 0, 0), ("click", 0, 0), ("wait", 0, 0), ("wait", 0, 0)]
SCENARIO += [("wait", 0, 0)] * 2


def clicks():
    out = []
    for what, a, b in SCENARIO:
        x, y = CX + 16 * (a - b), CY + 8 * (a + b)
        out.append(f"{x},{y}" if what == "click" else "h1,1")
    return ";".join(out)


def junction(link, target):
    subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)


def mods_farm(work):
    """Папка модов прогона: соединения на моды установки (снимать только rmdir - R-047) и пробный мод."""
    farm = work / "mods"
    farm.mkdir(parents=True, exist_ok=True)
    for d in MODS.iterdir():
        if d.is_dir() and not (farm / d.name).exists():
            junction(farm / d.name, d)
    probe = farm / PROBE
    (probe / "Ruleset").mkdir(parents=True, exist_ok=True)
    (probe / "metadata.yml").write_text(
        f'name: "Проба звука: реплики всегда"\nversion: 0.1\nid: {PROBE}\nmaster: piratez\n'
        'description: "Только для tools/sfx/battle_sound_check.py: частота реплик 100 %."\n', encoding="utf-8")
    (probe / "Ruleset" / "probe.rul").write_text(
        "unitResponseSoundsFrequency: [100, 100, 100, 100]   # выбор, ход, оружие, отстань\n", encoding="utf-8")
    return farm


def run_games(work, after, steps_mod, voices_mod):
    farm = mods_farm(work)
    n = len(SCENARIO)
    keys = ";".join(["9"] * 4 + [FILLER_KEY] * (n + 1))   # Tab x4 кончаются до первого щелчка
    off = "hd_voices_ru=false;hd_voices_en=false;hd_test_voices_ru=false;hd_test_voices_en=false"
    procs = {}
    for name, steps in (("with", True), ("without", False)):
        raw = work / f"{name}.raw"
        if raw.exists():
            raw.unlink()
        mods = f"{off};{voices_mod}=true;{steps_mod}={'true' if steps else 'false'};{PROBE}=true"
        cmd = [sys.executable, str(ROOT / "tools" / "game_hidden.py"), "--out", str(work / f"{name}.png"),
               "--save", str(SAVE), "--after", str(after), "--user", str(work / f"u_{name}"),
               "--mods-dir", str(farm), "--mods", mods, "--audio-disk", str(raw),
               "--key", keys, "--clicks", clicks()]
        log = open(work / f"{name}.log", "w", encoding="utf-8-sig")
        procs[name] = (subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT), log)
        time.sleep(2)
    for name, (p, log) in procs.items():
        p.wait()
        log.close()
        print(name, "код", p.returncode)


def decode(path):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
                       capture_output=True, check=True)
    return np.frombuffer(r.stdout, "<i2").astype(np.float32)


def templates(steps_mod, voices_mod):
    """Все звуки, которые могли сыграть: реплики мода голосов, шаги мода шагов, шаги Пираток (BATTLE.CAT 24-35)."""
    out = []
    for p in sorted((MODS / voices_mod / "Resources" / "Sounds").rglob("*.ogg")):
        out.append(("голос", p.parent.name + "/" + p.stem, decode(p)))
    for p in sorted((MODS / steps_mod / "Resources" / "Sounds").rglob("*.ogg")):
        out.append(("шаг мода", p.parent.name + "/" + p.stem, decode(p)))
    for p in sorted((MODS / "Piratez" / "Resources" / "Sounds" / "HQ").glob("walk_*.ogg")):
        out.append(("шаг Пираток", p.stem, decode(p)))
    return [(k, n, t) for k, n, t in out if len(t) > SR // 50 and np.abs(t).max() > 0]


def segments(x, thr=20.0, gap=0.3):
    """Участки со звуком (окна 10 мс выше порога), слитые через паузы короче gap."""
    w = SR // 100
    n = len(x) // w
    rms = np.sqrt((x[: n * w].reshape(n, w) ** 2).mean(axis=1))
    on = np.flatnonzero(rms > thr)
    segs = []
    for i in on:
        if segs and i - segs[-1][1] <= gap * 100:
            segs[-1][1] = i
        else:
            segs.append([i, i])
    return [(max(0, a * w - SR // 4), min(len(x), (b + 1) * w + SR // 4)) for a, b in segs]


def ncc(x, t):
    """Нормированная корреляция шаблона t со всеми сдвигами x."""
    L = len(t)
    if len(x) < L:
        return np.zeros(0)
    num = fftconvolve(x, t[::-1], mode="valid")
    c = np.concatenate([[0.0], np.cumsum(x.astype(np.float64) ** 2)])
    en = np.sqrt(np.maximum(c[L:] - c[:-L], 0))
    # окно почти тишины (RMS меньше 3 из 32768) - не совпадение: деление на ноль давало корреляцию 25
    return np.where(en > 3 * np.sqrt(L), num / (en * np.linalg.norm(t) + 1e-9), 0.0)


def pursue(x, temps, thr=0.6, max_hits=200):
    """Поиск совпадений с вычитанием (OMP): лучший шаблон и сдвиг по остатку, затем усиления всех найденных
    на участке подбираются вместе и вычитаются из записи. По одному усилению реплика, наложенная на шаги,
    вычиталась с ошибкой, и её остаток прятал шаги (совпадение 0,68 вместо 0,99)."""
    hits = []
    res = x.copy()
    for a, b in segments(x):
        seg0 = x[a:b]
        seg = seg0.copy()
        atoms = []                                   # (k, i, score) на этом участке
        while len(hits) + len(atoms) < max_hits:
            best = None
            for k, (kind, name, t) in enumerate(temps):
                c = ncc(seg, t)
                if len(c) == 0:
                    continue
                for k2, i2, _ in atoms:              # уже взятый звук на своём месте - не новый
                    if k2 == k:
                        c[max(0, i2 - SR // 100): i2 + SR // 100] = 0
                i = int(np.argmax(c))
                if best is None or c[i] > best[0]:
                    best = (float(c[i]), k, i)
            if best is None or best[0] < thr:
                break
            atoms.append((best[1], best[2], best[0]))
            A = np.zeros((len(seg0), len(atoms)), np.float32)
            for j, (k, i, _) in enumerate(atoms):
                t = temps[k][2][: len(seg0) - i]
                A[i:i + len(t), j] = t
            gains = np.linalg.lstsq(A, seg0, rcond=None)[0]
            seg = seg0 - A @ gains
        for (k, i, score), g in zip(atoms, gains if atoms else []):
            hits.append(((a + i) / SR, temps[k][0], temps[k][1], score, float(g)))
        res[a:b] = seg
    hits.sort()
    return hits, res


def load_raw(path):
    a = np.fromfile(path, "<i2").astype(np.float32).reshape(-1, 2).mean(axis=1)
    return resample_poly(a, SR, RATE).astype(np.float32) if len(a) else a


def run_info(work, name):
    """Длина записи против длины прогона по логу игры (драйвер disk пишет почти в реальном времени)."""
    log = (work / f"u_{name}" / "openxcom.log").read_text(encoding="utf-8", errors="replace")
    stamps = re.findall(r"^\[(\d\d)-(\d\d)-(\d{4})_(\d\d)-(\d\d)-(\d\d)\]", log, re.M)
    to_s = lambda s: int(s[3]) * 3600 + int(s[4]) * 60 + int(s[5])
    wall = to_s(stamps[-1]) - to_s(stamps[0]) if stamps else 0
    missing = [l for l in log.splitlines() if re.search(r"Sound .* not found|\[ERROR\].*[Ss]ound", l)]
    battle = "BattlescapeState" in log
    return wall, missing, battle


def plot(work, results, n_clicks):
    """energy.png: огибающая последних секунд каждой записи, щелчки сценария и найденные звуки."""
    from PIL import Image, ImageDraw, ImageFont
    span = 1.2 * n_clicks + 3
    W, H, pad = 1600, 220, 60
    colors = {"голос": (220, 60, 60), "шаг мода": (40, 170, 70), "шаг Пираток": (60, 110, 220)}
    img = Image.new("RGB", (W, H * len(results) + 30), "white")
    d = ImageDraw.Draw(img)
    try:                       # шрифт PIL по умолчанию без кириллицы - квадратики
        d.font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 13)
    except OSError:
        pass
    for row, (name, x, hits, ratio) in enumerate(results):
        y0 = row * H + 20
        end = len(x) / SR
        t0 = end - span
        sx = lambda t: pad + (t - t0) / span * (W - 2 * pad)
        w = SR // 100
        seg = x[max(0, int(t0 * SR)):]
        n = len(seg) // w
        rms = np.sqrt((seg[: n * w].reshape(n, w) ** 2).mean(axis=1)) if n else np.zeros(0)
        db = 20 * np.log10(np.maximum(rms, 1) / 32768)
        pts = [(sx(t0 + i / 100), y0 + H - 40 - (max(v, -80) + 80) / 80 * (H - 70)) for i, v in enumerate(db)]
        # конец записи - не миг дампа (игра ещё выходит), поэтому щелчки ставятся от первого звука сценария
        first = next((h[0] for h in hits if h[0] >= t0 and h[4] >= MIN_GAIN), end - 1.2 * n_clicks)
        # темп записи в бою - по шагу реплик (щелчок через 3 паузы по 1,2 с): от прогона к прогону 0,9-1 (R-446)
        voices = [h[0] for h in hits if h[1] == "голос" and h[4] >= MIN_GAIN]
        pace = float(np.median(np.diff(voices))) / 3.6 if len(voices) > 2 else 1.0
        d.text((pad, y0), f"{name}: последние {span:.0f} с записи, огибающая в дБ; серые линии - щелчки сценария "
               f"по первой реплике (запись с загрузкой - {ratio:.2f} реального времени, в бою {pace:.2f})", fill="black")
        for j, (what, _, _) in enumerate(SCENARIO):
            if what == "click":
                tc = first + 1.2 * j * pace
                d.line([(sx(tc), y0 + 15), (sx(tc), y0 + H - 40)], fill=(170, 170, 170))
        if len(pts) > 1:
            d.line(pts, fill="black")
        for t, kind, nm, score, gain in hits:
            if t >= t0 and gain >= MIN_GAIN:     # своя полоса у каждого вида: реплика и шаг начинаются вместе
                c, r = colors[kind], list(colors).index(kind)
                d.rectangle([sx(t) - 2, y0 + 18 + r * 10, sx(t) + 2, y0 + 26 + r * 10], fill=c)
        for i, (k, c) in enumerate(colors.items()):
            d.rectangle([W - 330 + i * 110, y0 + 2, W - 320 + i * 110, y0 + 12], fill=c)
            d.text((W - 316 + i * 110, y0), k, fill="black")
        for s in range(0, int(span) + 1, 2):
            d.text((sx(t0 + s) - 8, y0 + H - 20), f"-{span - s:.0f}", fill=(90, 90, 90))
    img.save(work / "energy.png")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default=str(ROOT / "census" / "sound_check"))
    ap.add_argument("--after", type=int, default=220, help="секунд до дампа: бой с модами звука грузится ~130 с, сценарий ~35 с")
    ap.add_argument("--steps-mod", default="hd_test_steps")
    ap.add_argument("--voices-mod", default="hd_test_voices_ru")
    ap.add_argument("--analyse-only", action="store_true")
    o = ap.parse_args()
    work = Path(o.work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    if not o.analyse_only:
        run_games(work, o.after, o.steps_mod, o.voices_mod)
    temps = templates(o.steps_mod, o.voices_mod)
    print("шаблонов", len(temps))
    n_clicks = len(SCENARIO)
    lines = ["# Звук боя: скрытый прогон", "",
             f"Сейв `{SAVE.relative_to(ROOT).as_posix()}`, моды: `{o.voices_mod}`, `{o.steps_mod}` (with) / без него (without), "
             f"частота реплик 100 % (`{PROBE}`). Сценарий: Tab x4, щелчок по бойцу, 3 раза туда-обратно на соседнюю клетку.", ""]
    results, summary = [], {}
    for name in ("with", "without"):
        raw = work / f"{name}.raw"
        x = load_raw(raw) if raw.exists() else np.zeros(0, np.float32)
        wall, missing, battle = run_info(work, name) if (work / f"u_{name}").exists() else (0, [], False)
        hits, res = pursue(x, temps) if len(x) else ([], x)
        results.append((name, x, hits, len(x) / SR / wall if wall else 1.0))
        # звуки игры при громкости 100 ложатся с усилением 0,5-1 (шаги - с поправкой на расстояние); 0,06 -
        # тихий посторонний звук, похожий на шаблон формой (claws/snow_2 на 0,64 в обоих прогонах) - не в счёт
        cnt = {k: sum(1 for h in hits if h[1] == k and h[4] >= MIN_GAIN) for k in ("голос", "шаг мода", "шаг Пираток")}
        summary[name] = cnt
        loud = float(np.sqrt((x ** 2).mean())) if len(x) else 0.0
        left = float(np.sqrt((res ** 2).mean())) if len(x) else 0.0
        lines += [f"## {name}", "",
                  f"- запись {len(x) / SR:.1f} с, прогон по логу {wall} с; бой загружен: {'да' if battle else 'НЕТ'}; "
                  f"ненулевых отсчётов {int((x != 0).sum())}",
                  f"- найдено: реплик {cnt['голос']}, шагов мода {cnt['шаг мода']}, шагов Пираток {cnt['шаг Пираток']}; "
                  f"не объяснено файлами {100 * left / max(loud, 1e-9):.0f} % громкости (RMS остатка к RMS записи)",
                  f"- строк лога про ненайденный звук: {len(missing)}" + ("" if not missing else " - " + missing[0][:120]), "",
                  "| время от конца, с | что | файл | совпадение | усиление |", "|---|---|---|---|---|"]
        end = len(x) / SR
        for t, kind, nm, score, gain in hits:
            lines.append(f"| -{end - t:.3f} | {kind if gain >= MIN_GAIN else '(тихое, не в счёт)'} | {nm} | {score:.3f} | {gain:.2f} |")
        lines.append("")
    w, wo = summary["with"], summary["without"]
    ok = (w["голос"] >= 1 and wo["голос"] >= 1 and w["шаг мода"] >= 4 and w["шаг Пираток"] == 0
          and wo["шаг Пираток"] >= 4 and wo["шаг мода"] == 0)
    verdict = ("ПРОШЛО: реплики звучат в обоих прогонах, шаги с модом - из мода, без мода - Пираток"
               if ok else "НЕ ПРОШЛО: см. таблицы выше и energy.png")
    lines += ["## Вердикт", "", verdict, "", "Картинка: `energy.png` (огибающая, щелчки, найденные звуки)."]
    plot(work, results, n_clicks)
    (work / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    print("\n".join(lines[-6:]))
    print("отчёт", work / "report.md")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
