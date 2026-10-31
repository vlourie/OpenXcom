"""Порт раскладки вариантов пола (tools/hdart/ground_field.py) против кода движка.

1. Из src/Engine/HdCanvas.cpp вырезаются сами функции узора (groundHash, groundNoise, groundRagged, groundPure,
   константы и тело Canvas32::groundLevel), собираются с маленьким main и печатают уровень, рваную линию и выбор
   чистого варианта на сетке точек для нескольких зёрен; питон считает то же и сравнивает. Нужен c++ (MSYS2,
   путь из tools/build/build_config.json или C:/msys64/mingw64/bin); без компилятора эта часть пропускается.
2. Без компилятора: шкала вариантов [v3, v1, 0, v2]; один кадр без вариантов не меняется; клетка, где узор чистый,
   отдаёт кадр шкалы как есть; смешение не выходит из диапазона двух соседних кадров.
Контроль: порт с другой константой волны (GROUND_WAVE 5) обязан разойтись с движком.

    py -3.13 tools/test_ground_field.py
"""
import json
import os

import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
import ground_field as gf   # noqa: E402

SEEDS = (1, 2166136261, 0xDEADBEEF)
PTS = [(x * 0.37 - 3.1, y * 0.53 + 11.7) for x in range(25) for y in range(25)]


def cxx():
    cands = []
    cfg = ROOT / "tools" / "build" / "build_config.json"
    if cfg.exists():
        try:
            cands.append(Path(json.loads(cfg.read_text(encoding="utf-8-sig"))["MsysBin"]) / "g++.exe")
        except Exception:                                     # noqa: BLE001
            pass
    cands.append(Path("C:/msys64/mingw64/bin/g++.exe"))
    return next((c for c in cands if c.exists()), None)


def engine_source():
    src = (ROOT / "src" / "Engine" / "HdCanvas.cpp").read_text(encoding="utf-8", errors="replace")
    a = src.index("\tinline Uint32 groundHash(")
    b = src.index("float Canvas32::groundLevel(")
    c = src.index("void Canvas32::setGroundSeed(")
    helpers = src[a:b]
    level = src[b:c].replace("float Canvas32::groundLevel(", "float groundLevelE(", 1)
    return helpers, level


def run_engine(tmp, gxx):
    helpers, level = engine_source()
    pts = ",".join("{%r,%r}" % p for p in PTS)
    code = ("#include <cstdio>\n#include <cmath>\n#include <algorithm>\n#include <cstdint>\ntypedef uint32_t Uint32;\n"
            "namespace {\n" + helpers + "\n" + level +
            "\nstatic const float P[][2] = {" + pts + "};\n"
            "int main(){ const Uint32 S[] = {" + ",".join("%du" % s for s in SEEDS) + "};\n"
            " for (Uint32 s : S) for (int c = 2; c <= 4; ++c) for (auto &p : P) {\n"
            "  float l = groundLevelE(s, p[0], p[1], 0, c); float r = groundRagged(s, p[0], p[1], 0);\n"
            "  std::printf(\"%u %d %.6f %.6f %d\\n\", s, c, l, r, groundPure(l, c)); }\n return 0; }\n")
    # вырезка начинается внутри namespace { движка и кончается его закрывающей скобкой - открываем свой
    f = Path(tmp) / "g.cpp"
    f.write_text(code, encoding="utf-8")
    exe = Path(tmp) / "g.exe"
    env = dict(os.environ, PATH=str(gxx.parent) + os.pathsep + os.environ.get("PATH", ""))
    r = subprocess.run([str(gxx), "-O1", "-o", str(exe), str(f)], capture_output=True, text=True, env=env)
    if r.returncode:
        print(r.stderr[-2000:])
        raise SystemExit("не собралось")
    out = subprocess.run([str(exe)], capture_output=True, text=True, env=env).stdout.split("\n")
    return [ln.split() for ln in out if ln.strip()]


def compare(rows, wave=None):
    old = gf.GROUND_WAVE
    if wave is not None:
        gf.GROUND_WAVE = np.float32(wave)
    try:
        worst_l = worst_r = 0.0
        pure_bad = 0
        i = 0
        for s in SEEDS:
            for c in (2, 3, 4):
                for (u, v) in PTS:
                    es, ec, el, er, ep = rows[i]
                    i += 1
                    pl = float(gf.ground_level(s, np.float32(u), np.float32(v), 0, c))
                    pr = float(gf.ground_ragged(s, np.float32(u), np.float32(v), 0))
                    worst_l = max(worst_l, abs(pl - float(el)))
                    worst_r = max(worst_r, abs(pr - float(er)))
                    pure_bad += gf.ground_pure(pl, c) != int(ep)
        return worst_l, worst_r, pure_bad
    finally:
        gf.GROUND_WAVE = old


def logic():
    ok = True
    mk = lambda v: np.full((160, 128, 4), v, np.uint8)
    found = [mk(10), mk(20), mk(30), mk(40)]                 # основной, v1, v2, v3
    order = [int(f[0, 0, 0]) for f in gf.scale_order(found)]
    ok &= order == [40, 20, 10, 30]
    print("шкала [v3, v1, 0, v2]:", order, "ok" if order == [40, 20, 10, 30] else "ОШИБКА")
    one = mk(77)
    ok &= gf.frame_for([one], 3, 4, 0, 1) is one
    blends = pures = 0
    for x in range(30):
        for y in range(30):
            fr = gf.frame_for(found, x, y, 0, 5)
            p = gf.pick(4, x, y, 0, 5)
            if p >= 0:
                pures += 1
                ok &= int(fr[0, 0, 0]) == order[p] and len(np.unique(fr[..., 0])) == 1
            else:
                blends += 1
                vals = np.unique(fr[..., 0])
                ok &= vals.min() >= 10 and vals.max() <= 40
    print("клеток чистых %d, на краю пятна %d" % (pures, blends))
    ok &= pures > 0 and blends > 0
    return ok


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ok = logic()
    gxx = cxx()
    if gxx is None:
        print("c++ не найден - сверка с движком пропущена")
    else:
        with tempfile.TemporaryDirectory() as tmp:
            rows = run_engine(tmp, gxx)
        wl, wr, pb = compare(rows)
        print("против движка: уровень до %.2e, рваная линия до %.2e, выбор варианта расходится в %d из %d"
              % (wl, wr, pb, len(rows)))
        ok &= wl < 1e-4 and wr < 1e-4 and pb == 0
        cl, cr, cb = compare(rows, wave=5.0)
        print("контроль (волна 5 вместо 6): уровень до %.2e, выбор расходится в %d" % (cl, cb))
        ok &= cl > 1e-2
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
