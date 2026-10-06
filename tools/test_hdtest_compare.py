# Проверка tools/hdtest_compare.py --same-mode на синтетических дампах:
# одинаковые кадры в режиме 1 - IDENTICAL только с ключом (без ключа режим 1 по-прежнему не сравнивается);
# пиксель изменён - DIFFERENT; режимы A и B разные - DIFFERENT и с ключом; режим 0 - IDENTICAL без ключа.
import json, os, subprocess, sys, tempfile
from PIL import Image

TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdtest_compare.py")


def dump(d, name, mode, poke=False):
    p = os.path.join(d, name)
    im = Image.new("RGB", (16, 8), (40, 80, 120))
    if poke:
        im.putpixel((3, 5), (41, 80, 120))
    im.save(p + "_map.png")
    im.save(p + "_frame.png")
    with open(p + ".json", "w", encoding="utf-8") as f:
        json.dump({"format": 1, "hdMode": mode, "mods": ["m"], "cameraOffsetX": 1, "drawMs": 1.0, "flipMs": 1.0}, f)
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
        for name, got, want in cases:
            print(("ok   " if got == want else "FAIL ") + "%s: %s (ждали %s)" % (name, got, want))
            ok &= got == want
    print("PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
