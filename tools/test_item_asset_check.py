"""Тест tools/hdart/item_asset_check.py на синтетике: чистые картинки проходят, один пиксель вне допуска - FAIL.

  py -3.13 tools/test_item_asset_check.py
"""
import sys, tempfile
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent / "hdart"))
import item_asset_check as C

K = 4


def png(path, size, rect, extra=None, alpha=255):
    """Картинка size (база) x K, непрозрачна только внутри rect базы; extra - (x, y) пикселя картинки снаружи."""
    w, h = size
    a = np.zeros((h * K, w * K, 4), np.uint8)
    x0, y0, x1, y1 = (v * K for v in rect)
    a[y0:y1, x0:x1] = (120, 110, 90, 255)
    if extra:
        a[extra[1], extra[0]] = (255, 0, 0, alpha)
    Image.fromarray(a, "RGBA").save(path)


def main():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        items = d / "items.tsv"
        items.write_text("type\tbigSprite\tinvWidth\tinvHeight\n"
                         "STR_A\t10\t1\t3\nSTR_B\t11\t2\t3\nSTR_C\t11\t1\t1\nSTR_D\t12\t3\t3\n", encoding="utf-8-sig")
        frames = d / "frames.tsv"
        frames.write_text("frame\tsize\n10\t32x48\n11\t32x48\n12\t48x48\n", encoding="utf-8-sig")
        pack = d / "BIGOBS.PCK"
        pack.mkdir()
        png(pack / "10.STR_A.png", (32, 48), (1, 1, 16, 47))                          # чистая 1x3
        png(pack / "10.STR_A.hand.png", (32, 48), (9, 1, 24, 47))                     # 1x3 в руке: клетки со сдвигом 8
        png(pack / "12.STR_D.hand.png", (32, 48), (1, 1, 31, 47))                     # 3x3 больше рамки: вся рамка
        png(pack / "11.STR_B.hand.png", (32, 48), (1, 1, 31, 47))                     # 2x3: клетки = вся рамка
        png(pack / "11.STR_B.png", (32, 48), (1, 1, 31, 47), extra=(31 * K, 10))      # 2x3: столбец 31 - линия
        png(pack / "11.STR_C.hand.png", (32, 48), (1, 1, 31, 47), extra=(0, 0), alpha=1)   # альфа 1 в углу
        png(pack / "12.png", (48, 48), (1, 1, 47, 47))                                # 3x3 общий, чистый
        Image.new("RGBA", (130, 192)).save(pack / "10.png")                          # общий, не кратно 32x48
        Image.new("RGBA", (128, 192)).save(pack / "10.STR_X.png")                    # такого предмета у кадра нет
        out = d / "report.tsv"
        code = C.main([str(pack), "--items", str(items), "--frames", str(frames), "--out", str(out)])
        rows = {(r["file"], r["item"]): r for r in C.read_tsv(out)}
        want = {("10.STR_A.png", "STR_A"): "PASS", ("10.STR_A.hand.png", "STR_A"): "PASS",
                ("11.STR_B.png", "STR_B"): "FAIL", ("11.STR_C.hand.png", "STR_C"): "FAIL",
                ("12.png", "STR_D"): "PASS", ("10.png", "STR_A"): "FAIL", ("10.STR_X.png", "-"): "FAIL",
                ("12.STR_D.hand.png", "STR_D"): "PASS", ("11.STR_B.hand.png", "STR_B"): "PASS"}
        bad = [(k, rows.get(k, {}).get("verdict"), v) for k, v in want.items() if rows.get(k, {}).get("verdict") != v]
        assert not bad, bad
        assert rows[("11.STR_B.png", "STR_B")]["outside"] == "1"
        assert "не кратно" in rows[("10.png", "STR_A")]["note"]
        assert code == 1
        # маленький предмет на всю рамку руки: 1x1 в руке - клетка [8, 24) x [16, 32) (сдвиг 8, 16; ТЗ §5.4)
        assert C.hand_rect(1, 1) == (8, 16, 24, 32) and C.hand_rect(2, 2) == (1, 8, 31, 40)
        assert C.hand_rect(1, 3) == (8, 1, 24, 47) and C.hand_rect(2, 3) == (1, 1, 31, 47)
        assert C.hand_rect(3, 2) == C.hand_rect(3, 3) == (1, 1, 31, 47)
        full = d / "full.png"
        png(full, (32, 48), (1, 1, 31, 47))
        alpha = np.asarray(Image.open(full))[:, :, 3]
        assert C.outside(alpha, C.hand_rect(1, 1), K) > 0
        # контроль: прежнее правило (вся рамка всем) этот файл пропускало
        assert C.outside(alpha, (1, 1, 31, 47), K) == 0
        # контроль: тот же файл без лишнего пикселя проходит
        png(pack / "11.STR_B.png", (32, 48), (1, 1, 31, 47))
        for p in (pack / "11.STR_C.hand.png", pack / "10.png", pack / "10.STR_X.png", full):
            p.unlink()
        assert C.main([str(pack), "--items", str(items), "--frames", str(frames)]) == 0
        # .wide (M-01, магазин АК во втором столбце): за свои клетки до рамки кадра и рамки руки после сдвига
        assert C.wide_rect(1, 3, (32, 48)) == (0, 1, 23, 47)        # в руке сдвиг 8: 23 + 8 = 31, линия рамки
        assert C.wide_rect(2, 3, (32, 48)) == (1, 1, 31, 47) and C.wide_rect(3, 3, (48, 48)) == (0, 0, 48, 48)
        assert C.wide_rect(1, 1, (32, 48)) == (0, 0, 23, 31)
        png(pack / "10.STR_A.wide.png", (32, 48), (0, 1, 20, 47))                    # магазин до x = 20, ствол на линии 0
        png(pack / "11.STR_B.wide.hand.png", (32, 48), (1, 1, 31, 47))               # .wide у .hand не бывает
        rows = {}
        code = C.main([str(pack), "--items", str(items), "--frames", str(frames), "--out", str(out)])
        rows = {(r["file"], r["item"]): r for r in C.read_tsv(out)}
        assert rows[("10.STR_A.wide.png", "STR_A")]["verdict"] == "PASS"
        assert rows[("10.STR_A.wide.png", "STR_A")]["variant"] == "wide"
        assert rows[("11.STR_B.wide.hand.png", "-")]["verdict"] == "FAIL" and code == 1
        # контроль: тот же рисунок без метки - FAIL (за клеткой 1x3), метка не снимает правило с остальных
        png(pack / "10.STR_A.png", (32, 48), (1, 1, 20, 47))
        C.main([str(pack), "--items", str(items), "--frames", str(frames), "--out", str(out)])
        rows = {(r["file"], r["item"]): r for r in C.read_tsv(out)}
        assert rows[("10.STR_A.png", "STR_A")]["verdict"] == "FAIL"
        # за рамку руки после сдвига: столбец 23 у 1x3 - уже линия рамки
        png(pack / "10.STR_A.wide.png", (32, 48), (0, 1, 20, 47), extra=(23 * K, 40))
        C.main([str(pack), "--items", str(items), "--frames", str(frames), "--out", str(out)])
        rows = {(r["file"], r["item"]): r for r in C.read_tsv(out)}
        assert rows[("10.STR_A.wide.png", "STR_A")]["verdict"] == "FAIL"
        # строка 0 у 1x3 - в руке верхняя линия рамки (сдвиг по высоте 0), альфа 1 - уже FAIL
        png(pack / "10.STR_A.wide.png", (32, 48), (0, 1, 20, 47), extra=(4 * K, 0), alpha=1)
        C.main([str(pack), "--items", str(items), "--frames", str(frames), "--out", str(out)])
        rows = {(r["file"], r["item"]): r for r in C.read_tsv(out)}
        assert rows[("10.STR_A.wide.png", "STR_A")]["outside"] == "1"
    print("test_item_asset_check: OK")


if __name__ == "__main__":
    main()
