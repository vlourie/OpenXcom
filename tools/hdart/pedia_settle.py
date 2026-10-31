"""Поставленное в мод перекрафтом - в заметках «в порядке» (ok).

Страница досмотра (pedia_notes.py) берёт статус из последней строки art\\pedia_regen\\review_notes.tsv.
Выбор на странице круга (picks.tsv) и установка (pedia_recraft.py --install) этот статус не меняли,
и уже принятые картинки оставались «переделать» и снова шли на досмотр. Скрипт дописывает строку ok
(заметка и промпт Vitali - как были) для каждой картинки, у которой выбранный кандидат поставлен
по журналу круга (install_*.tsv, откатанные .undone не в счёт) или выбор - «оставить как было» (keep).
«again» и невыбранное не трогает. pedia_recraft.py --install зовёт его сам; повторный запуск ничего не дописывает.

    py -3.13 tools\\hdart\\pedia_settle.py [--dry-run]
"""
import argparse
import csv
import glob
import io
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pedia_notes as pn  # noqa: E402

REGEN = os.path.join(pn.ROOT, "art", "pedia_regen")


def settled():
    """{stem: (круг, выбор)} - что по кругам уже решено: поставлено или оставлено как было."""
    out = {}
    for rd in sorted(glob.glob(os.path.join(REGEN, "recraft_v*")), key=lambda p: int(p.rsplit("_v", 1)[1])):
        picks = pn.read_picks(rd)
        done = set()
        for jl in glob.glob(os.path.join(rd, "install_*.tsv")):
            if jl.endswith(".undone.tsv"):
                continue
            with io.open(jl, encoding="utf-8-sig") as f:
                done |= {r[1].lower() for r in csv.reader(f, delimiter="\t") if len(r) > 2}
        for k, p in picks.items():
            if p["pick"] == "keep" or (p.get("file") and k in done):
                out[k] = (os.path.basename(rd), p["pick"], p["stem"])
            elif p["pick"] == "again":
                out.pop(k, None)
    return out


def main(dry=False):
    notes = pn.read_notes()
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    n = 0
    for k, (rd, pick, stem) in sorted(settled().items()):
        r = notes.get(k)
        if not r or r.get("status") == "ok":
            continue
        n += 1
        print("  %-32s %-5s -> ok  (%s %s)" % (stem, r.get("status") or "-", rd, pick))
        if not dry:
            pn.append_note({"stem": r["stem"], "status": "ok", "note": r.get("note", ""),
                            "prompt": r.get("prompt", ""), "when": now})
    print("в порядке по перекрафту: %d%s" % (n, " (dry-run)" if dry else ""))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", dest="dry", action="store_true")
    sys.exit(main(ap.parse_args().dry))
