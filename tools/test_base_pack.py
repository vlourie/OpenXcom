"""Проверка записи HD-клеток базы (tools/hdart/base_pack.py).

Прежний генератор писал в <N>.png первую фазу петли, и при выключенной анимации база застывала
посреди эффектов: огни погашены, дым и искры на месте. Тест собирает постройку 2x1 с водой в левой
клетке и огнём в правой и проверяет: <N>.png - чистая картинка без эффектов, петля и вспышка
лежат своими кусками там, где меняют клетку, описание верно, старые фазы клетки удалены.
Запуск: python tools/test_base_pack.py   (код 0 - всё верно)
"""
import os
import sys
import tempfile

import numpy as np
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdart"))
import base_pack  # noqa: E402

bad = 0


def check(ok, what):
    global bad
    print(("ok   " if ok else "FAIL ") + what)
    bad += 0 if ok else 1


T = 32 * base_pack.K
rng = np.random.default_rng(1)
still = rng.random((T, 2 * T, 3)).astype(np.float32) * 0.5
alpha = np.ones((T, 2 * T), np.float32)
alpha[:8, :8] = 0
# вода: левая клетка, квадрат 40..60; огонь: правая клетка, квадрат 20..30 (в своей клетке)
loop = []
for p in range(16):
    f = still.copy()
    f[40:60, 40:60] += 0.1 * (p % 4 + 1)     # и в фазе 0 вода не равна чистой картинке
    loop.append(f)
burst = []
for q in range(16):
    f = loop[q].copy()
    f[20:30, T + 20:T + 30] += 0.4 * base_pack.envelope(q, 16)
    burst.append(f)

with tempfile.TemporaryDirectory() as out:
    dest = os.path.join(out, "hd", "BASEBITS.PCK")
    os.makedirs(dest)
    # хвост прежней петли: обязан исчезнуть
    for p in range(1, 20):
        Image.new("RGBA", (T, T)).save(os.path.join(dest, "7.v%d.png" % p))
    base_pack.write(out, [7, 8], 2, T, T, alpha, still, loop, burst, 45, "test")
    files = set(os.listdir(dest))

    got = np.asarray(Image.open(os.path.join(dest, "7.png")), np.float32) / 255
    check(np.abs(got[..., :3] - still[:, :T]).max() < 1.5 / 255, "7.png - чистая картинка, без эффектов")
    check(np.array_equal(got[..., 3] > 0.5, alpha[:, :T] > 0.5), "7.png - альфа постройки")
    got8 = np.asarray(Image.open(os.path.join(dest, "8.png")), np.float32) / 255
    check(np.abs(got8[..., :3] - still[:, T:]).max() < 1.5 / 255, "8.png - чистая картинка, без эффектов")
    check(not any(("7.v%d.png" % p) in files for p in range(17, 20)), "старые фазы 7.v17..v19 удалены")
    check(all(("7.v%d.png" % p) in files for p in range(1, 17)), "петля 7.v1..v16 на месте")
    check(not any(f.startswith("7.b") for f in files), "у клетки без огня нет вспышки")
    check(not any(f.startswith("8.v") for f in files), "у клетки без воды нет петли")
    check(all(("8.b%d.png" % q) in files for q in range(1, 17)), "вспышка 8.b1..b16 на месте")

    def desc(index):
        d = {}
        for line in open(os.path.join(dest, "%d.anim.txt" % index), encoding="utf-8"):
            w = line.split()
            if w and not w[0].startswith("#"):
                d[w[0]] = [int(v) for v in w[1:]]
        return d

    d7, d8 = desc(7), desc(8)
    check(d7.get("size") == [T, T] and d8.get("size") == [T, T], "size в описании")
    x, y, w, h = d7["loop"]
    check(x <= 40 and y <= 40 and x + w >= 60 and y + h >= 60 and w < T and h < T, "кусок петли накрывает воду и меньше клетки")
    check(all(v % base_pack.K == 0 for v in d7["loop"] + d8["burst"]), "куски кратны пикселю классики")
    x, y, w, h = d8["burst"]
    check(x <= 20 and y <= 20 and x + w >= 30 and y + h >= 30 and w < T, "кусок вспышки накрывает огонь")
    check(d8.get("every") == [45], "every 45")
    piece = np.asarray(Image.open(os.path.join(dest, "8.b8.png")), np.float32) / 255
    check(piece.shape[:2] == (h, w) and np.abs(piece[..., :3] - burst[7][y:y + h, T + x:T + x + w]).max() < 1.5 / 255,
          "8.b8 - кусок восьмой фазы вспышки")
    check(base_pack.envelope(0, 16) == 0 and base_pack.envelope(15, 16) == 0 and base_pack.envelope(8, 16) == 1,
          "вспышка начинается и кончается нулём")

print("итог:", "ошибок %d" % bad if bad else "всё верно")
sys.exit(1 if bad else 0)
