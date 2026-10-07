"""Проверка проёма в geom_mask.check: HD сравнивается с ВИДИМЫМ проёмом классики, а не с LOFT (07.10).

Окно URBAN 71/72 (записи 67/68): LOFT пуст на всю ширину стены в слоях 10..21, классика рисует внутри раму,
переплёт, перемычку и подоконник - 58 процентов механического проёма. Это не дефект, и проверка не должна
его так называть. Контроли:
  - классика x4 как HD - PASS, проём совпадает точно (IoU 1.0, сдвиг 0);
  - окно сдвинуто на базовый пиксель - FAIL по проёму;
  - проём заложен целиком - FAIL, сдвиг не считается (None), а не мусорное число.
Нужны маски census/maps/pilot2/masks/URBAN_67 и URBAN_68 (map_pilot2_jobs.py); без них тест пропускается.

    py -3.13 tools/test_geom_mask_hole.py
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "hdart"))
import numpy as np                    # noqa: E402
from PIL import Image                 # noqa: E402
import geom_mask as gm                # noqa: E402


def cases(f, md):
    idx, pal = gm.classic("URBAN", f)
    rgba = np.zeros((40, 32, 4), np.uint8)
    rgba[..., :3] = pal[idx]
    rgba[..., 3] = np.where(idx > 0, 255, 0)
    a = np.array(Image.fromarray(rgba).resize((128, 160), Image.NEAREST))
    sh = a.copy()
    sh[20:110, 4:] = a[20:110, :-4]       # окно вправо на базовый пиксель
    env = np.array(Image.open(md / "envelope.png")) > 127
    br = a.copy()
    br[env & (br[..., 3] == 0)] = (120, 120, 120, 255)
    return dict(classic=a, shift1=sh, bricked=br)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    fails = 0
    with tempfile.TemporaryDirectory() as tmp:
        for r, f in ((67, 71), (68, 72)):
            md = ROOT / "census" / "maps" / "pilot2" / "masks" / ("URBAN_%d" % r)
            if not (md / "envelope.png").exists():
                print("пропуск: нет масок", md)
                return 0
            for k, arr in cases(f, md).items():
                d = Path(tmp) / k
                d.mkdir(exist_ok=True)
                p = d / ("%d.png" % f)
                Image.fromarray(arr).save(p)
                v = gm.check(md, p)
                want = "PASS" if k == "classic" else "FAIL"
                good = v["verdict"] == want
                if k == "classic":
                    good &= v["hole_iou_vs_classic"] == 1.0 and v["hole_shift_vs_classic_x4"] == 0.0
                if k == "shift1":
                    good &= v["hole_iou_vs_classic"] < 0.90
                if k == "bricked":
                    good &= v["hole_shift_vs_classic_x4"] is None
                print("%s f%d %-8s %s  IoU %s сдвиг %s" % ("ok " if good else "ОШИБКА", f, k, v["verdict"],
                      v.get("hole_iou_vs_classic"), v.get("hole_shift_vs_classic_x4")))
                fails += not good
    print("FAIL" if fails else "PASS")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
