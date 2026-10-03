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
        png(pack / "10.STR_A.hand.png", (32, 48), (1, 1, 31, 47))                     # чистая рамка
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
                ("12.png", "STR_D"): "PASS", ("10.png", "STR_A"): "FAIL", ("10.STR_X.png", "-"): "FAIL"}
        bad = [(k, rows.get(k, {}).get("verdict"), v) for k, v in want.items() if rows.get(k, {}).get("verdict") != v]
        assert not bad, bad
        assert rows[("11.STR_B.png", "STR_B")]["outside"] == "1"
        assert "не кратно" in rows[("10.png", "STR_A")]["note"]
        assert code == 1
        # контроль: тот же файл без лишнего пикселя проходит
        png(pack / "11.STR_B.png", (32, 48), (1, 1, 31, 47))
        for p in (pack / "11.STR_C.hand.png", pack / "10.png", pack / "10.STR_X.png"):
            p.unlink()
        assert C.main([str(pack), "--items", str(items), "--frames", str(frames)]) == 0
    print("test_item_asset_check: OK")


if __name__ == "__main__":
    main()
