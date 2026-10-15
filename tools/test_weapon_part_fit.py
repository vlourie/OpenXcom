"""Проверка операций доводки по частям (tools/hdart/weapon_part_fit.py) без видеокарты.

Синтетика: прямоугольное тело с рукоятью вниз. Сужение рукояти меняет только её область, шов на границе области
по телу меньше 0.5 пикс, защищённый ствол не изменён. Контроли: операция, у которой область режет тело там, где
смещение большое, обязана упасть на проверке шва; защищённое, задетое операцией, обязано упасть.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdart"))
import weapon_part_fit as wpf  # noqa: E402


def body():
    a = np.zeros((200, 160, 4), np.float32)
    a[20:60, 10:150] = (120, 90, 60, 255)          # ствол и рамка
    a[60:180, 90:130] = (90, 60, 40, 255)          # рукоять
    a[100:140, 100:120, :3] = (200, 200, 200)      # винт на рукояти
    return a


def raises(fn):
    try:
        fn()
    except AssertionError:
        return True
    return False


def main():
    a = body()
    grip = [[60, 62], [140, 62], [140, 190], [60, 190]]
    # рукоять расширяется влево от правого края (u=130): у основания 1.0, внизу 1.3
    op = {"name": "grip", "type": "taper", "from": [130, 62], "to": [130, 180], "anchor": [130, 62],
          "scale": [[0.0, 1.0], [1.0, 1.3]], "region": grip, "feather": 6}
    out, log, summ = wpf.apply_ops(a, [op], {"barrel": [[10, 20], [150, 20], [150, 55], [10, 55]]})
    e = log[0]
    assert e["changed_outside_region"] == 0 and summ["changed_outside_all_regions"] == 0
    assert e["seam_displacement_px"] < 0.5, e
    assert summ["protect"]["barrel"] == 0
    # низ рукояти стал шире: левый край у строки 175 левее 90 примерно на 0.3*40*(113/118)
    row = out[175, :, 3] > 127
    left = int(np.nonzero(row)[0].min())
    assert 74 <= left <= 81, left
    assert (out[175, 129, 3] > 127) and not (out[175, 131, 3] > 127), "правый край ушёл"
    # контроль шва: область кончается посреди рукояти, где смещение уже 6 пикс
    bad = dict(op, region=[[60, 62], [140, 62], [140, 150], [60, 150]], feather=0)
    assert raises(lambda: wpf.apply_ops(a, [bad])), "шов не пойман"
    # контроль защиты: рукоять защищена, а операция её меняет
    assert raises(lambda: wpf.apply_ops(a, [op], {"grip": grip})), "защита не поймана"
    # перенос заплатки из исходного ответа: винт переезжает, вне области - ничего
    mv = {"name": "screw", "type": "move", "shift": [-8, 0], "source": "answer",
          "region": [[88, 96], [124, 96], [124, 144], [88, 144]], "feather": 2}
    out2, log2, _ = wpf.apply_ops(a, [mv])
    assert log2[0]["changed_outside_region"] == 0
    assert out2[120, 94, 0] > 180 and out2[120, 113, 0] < 120, (out2[120, 94], out2[120, 113])
    # обратное отображение сходится
    assert e["inverse_error_px"] < 0.01, e["inverse_error_px"]
    print("test_weapon_part_fit: OK (лево низа рукояти %d, шов %.3f)" % (left, e["seam_displacement_px"]))


if __name__ == "__main__":
    main()
