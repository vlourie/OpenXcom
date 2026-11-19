"""R-703 stated a number the data does not have: the wording goes, in the rake and in the closure copy of its script; closure sums are recomputed by the caller."""
import sys

sys.stdout.reconfigure(encoding="utf-8")
OLD = "таблица потерь по всем строкам показывала сотни выбывших."
NEW = "счёт выбывших по всем строкам завышен."
for p, enc in (("E:/OpenXCom/docs/rakes/aibench.md", "utf-8"), (sys.argv[1], "utf-8"), (sys.argv[2], "utf-8")):
    b = open(p, "rb").read()
    n = b.count(OLD.encode(enc))
    print(p[-40:], "found", n)
    if n:
        open(p, "wb").write(b.replace(OLD.encode(enc), NEW.encode(enc)))
