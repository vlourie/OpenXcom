# Проверка tools/hdtest_compare.py --same-mode на синтетических дампах:
# одинаковые кадры в режиме 1 - IDENTICAL только с ключом (без ключа режим 1 по-прежнему не сравнивается);
# пиксель изменён - DIFFERENT; режимы A и B разные - DIFFERENT и с ключом; режим 0 - IDENTICAL без ключа.
import json, os, subprocess, sys, tempfile
from PIL import Image

TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdtest_compare.py")


def dump(d, name, mode, poke=False, **state):
    p = os.path.join(d, name)
    im = Image.new("RGB", (16, 8), (40, 80, 120))
    if poke:
        im.putpixel((3, 5), (41, 80, 120))
    im.save(p + "_map.png")
    im.save(p + "_frame.png")
    js = {"format": 1, "hdMode": mode, "mods": ["m"], "save": "", "cameraOffsetX": 1, "mapWidth": 60,
          "drawMs": 1.0, "flipMs": 1.0}
    js.update(state)
    with open(p + ".json", "w", encoding="utf-8") as f:
        json.dump(js, f)
    return p


def verdict(a, b, *extra):
    r = subprocess.run([sys.executable, TOOL, a, b, "--no-diff"] + list(extra), capture_output=True, text=True)
    return "IDENTICAL" if r.returncode == 0 else "DIFFERENT"


def main():
    ok = True
    with tempfile.TemporaryDirectory() as d:
        a1, b1 = dump(d, "a1", 1), dump(d, "b1", 1)
        c1 = dump(d, "c1", 1, poke=True)
        b2 = dump(d, "b2", 2)
        a0, b0 = dump(d, "a0", 0), dump(d, "b0", 0)
        cases = [("режим 1, одинаковые, --same-mode", verdict(a1, b1, "--same-mode"), "IDENTICAL"),
                 ("режим 1, одинаковые, без ключа (прежнее поведение)", verdict(a1, b1), "DIFFERENT"),
                 ("режим 1, один пиксель изменён, --same-mode", verdict(a1, c1, "--same-mode"), "DIFFERENT"),
                 ("режимы 1 и 2, --same-mode", verdict(a1, b2, "--same-mode"), "DIFFERENT"),
                 ("режим 0, одинаковые, без ключа", verdict(a0, b0), "IDENTICAL")]
        # П-5: дамп до и после быстрого сохранения и загрузки - имя сейва меняется закономерно
        q = dump(d, "q", 1, save="_quick_.asav")
        q_cam = dump(d, "q_cam", 1, save="_quick_.asav", cameraOffsetX=2)
        q_map = dump(d, "q_map", 1, save="_quick_.asav", mapWidth=70)
        q_px = dump(d, "q_px", 1, poke=True, save="_quick_.asav")
        cases += [("сохранение и загрузка, без ключа", verdict(a1, q, "--same-mode"), "DIFFERENT"),
                  ("сохранение и загрузка, --expect-save-change", verdict(a1, q, "--same-mode", "--expect-save-change"), "IDENTICAL"),
                  ("ключ, а имя сейва то же (загрузки не было)", verdict(a1, b1, "--same-mode", "--expect-save-change"), "DIFFERENT"),
                  ("ключ, камера сдвинута", verdict(a1, q_cam, "--same-mode", "--expect-save-change"), "DIFFERENT"),
                  ("ключ, карта другая", verdict(a1, q_map, "--same-mode", "--expect-save-change"), "DIFFERENT"),
                  ("ключ, пиксель изменён", verdict(a1, q_px, "--same-mode", "--expect-save-change"), "DIFFERENT")]
        for name, got, want in cases:
            print(("ok   " if got == want else "FAIL ") + "%s: %s (ждали %s)" % (name, got, want))
            ok &= got == want
    print("PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
