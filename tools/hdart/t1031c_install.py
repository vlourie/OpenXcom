#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Установка кандидатов тикетов 443 и 395 (выбор Vitali 31.10, страница выбора, 12-й круг, пункты c1031c_NNN).

Новый арт не генерирует: ставит готовые кадры через манифест (ticket_scene.install_files: stage + save + install
в game и repo + сверка хэшей). Резерв нынешних кадров - art/_backup/t<N>_2026-10-31b/<путь пака>.

  443  балки Города гулей, 12 кадров из art/tickets/t443/fix/ (t443_fix.py): MILWAREGHOUL 47 48 49 50 52 54,
       MILWARE 48 49 50 51 53 55 (c1031c_443: Y)
  395  капуста, зерно cab7b 3961, fill 0,95, 4 кадра из art/tickets/t395/v2/cab7b_3961_f95/ (t395_v2.py):
       CULTIVAT_UBER:7, CULTIVAT:7, CULTIVAT_PP:7, VILFRNITURE:104 (c1031c_395: Y)

    py -3.13 tools\hdart\t1031c_install.py --ticket 443                  сухой прогон
    py -3.13 tools\hdart\t1031c_install.py --ticket 443 --install --yes  установить (под очередью правок)
"""
import argparse
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
os.chdir(ROOT)

from PIL import Image                        # noqa: E402

REPO_PACK = os.path.join(ROOT, "user", "mods", "hd", "hd")
ART = os.path.join(ROOT, "art", "tickets")
REV = os.path.join(ROOT, "art", "_review", "tickets_2026-10-31")

# тикет -> (число кадров, папка кандидатов, пункт страницы, описание, генератор)
TICKETS = {
    "443": (12, os.path.join(ART, "t443", "fix"), "c1031c_443: балки Города гулей, 12 кадров, Y",
            "XP-000443: балки Города гулей MILWAREGHOUL/MILWARE, 12 кадров, переделка (t443_fix, правка нынешних кадров)",
            "t443_fix"),
    "395": (4, os.path.join(ART, "t395", "v2", "cab7b_3961_f95"), "c1031c_395: капуста, зерно 3961, fill 0,95, Y",
            "XP-000395: капуста CULTIVAT_UBER:7, CULTIVAT:7, CULTIVAT_PP:7, VILFRNITURE:104 (t395_v2, зерно cab7b 3961, fill 0,95)",
            "t395_v2"),
}


def collect(t):
    n, cand, _ap, _why, _gen = TICKETS[t]
    files = {}
    for f in sorted(os.listdir(cand)):
        m = re.fullmatch(r"(.+)_(\d+)\.png", f)
        if m:
            files["TERRAIN/%s.PCK/%s.png" % (m.group(1), m.group(2))] = os.path.join(cand, f)
    if len(files) != n:
        raise SystemExit("ждали %d кадров, а %d" % (n, len(files)))
    return files


def old_path(rel):
    p = os.path.join(REPO_PACK, rel)
    if not os.path.exists(p):               # набор в копии repo неполный (R-257): размер и резерв - из установки игры
        import build_hd_pack as bp
        p = os.path.join(bp.TARGETS["game"], rel)
    return p


def make_sheet(t, files, backup):
    import ticket_scene as ts
    panels = []
    for rel, p in files.items():
        with Image.open(os.path.join(backup, rel)) as o, Image.open(os.path.join(REPO_PACK, rel)) as n:
            o = o.convert("RGBA")
            n = n.convert("RGBA")
            k = 2
            W = o.width * k
            strip = Image.new("RGB", (W * 2 + 6, o.height * k), (40, 40, 46))
            for i, im in enumerate((o, n)):
                im = im.resize((W, o.height * k), Image.NEAREST if im.width <= 64 else Image.LANCZOS)
                strip.paste(im.convert("RGB"), (i * (W + 6), 0), im.split()[3])
        panels.append(("%s:%s  [было | стало]" % (rel.split("/")[1][:-4], os.path.basename(rel)[:-4]), strip))
    out = os.path.join(REV, "install_%s.png" % t)
    ts.sheet(panels, out, cols=3 if len(panels) > 4 else 2)
    print("лист:", out)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticket", required=True, choices=sorted(TICKETS))
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    t = a.ticket
    files = collect(t)
    for rel, p in files.items():
        # with: незакрытый кадр пака держит файл, и os.replace при установке падает (R-567)
        with Image.open(p) as im, Image.open(old_path(rel)) as old:
            if im.mode != "RGBA" or im.size != old.size:
                raise SystemExit("%s: ждали RGBA %s, а %s %s" % (p, old.size, im.mode, im.size))
    print("тикет %s, файлов к установке: %d" % (t, len(files)))
    for rel in files:
        print("  ", rel)
    if not (a.install and a.yes):
        print("сухой прогон; --install --yes - записать в мод (под очередью правок)")
        return
    import build_hd_pack as bp
    backup = os.path.join(ROOT, "art", "_backup", "t%s_2026-10-31b" % t)
    for rel in files:
        dst = os.path.join(backup, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if not os.path.exists(dst):
            shutil.copyfile(old_path(rel), dst)
    print("резерв:", backup)
    man = bp.load()
    for pck in sorted({rel.split("/")[1] for rel in files}):
        want = [k for k in man["files"] if k.startswith("TERRAIN/%s/" % pck)]
        d = os.path.join(REPO_PACK, "TERRAIN", pck)
        have = os.listdir(d) if os.path.isdir(d) else []
        if len(have) < len(want):
            print("repo: набор %s неполный (%d из %d) - ставлю целиком" % (pck, len(have), len(want)))
            bp.install(man, "repo", only=want)
            have = os.listdir(d)
            if len(have) != len(want):
                raise SystemExit("набор %s в repo: %d из %d" % (pck, len(have), len(want)))
    import ticket_scene as ts
    _n, _c, approval, why, gen = TICKETS[t]
    n = ts.install_files(files, "t1031c_install", gen, "Vitali 31.10, страница выбора, пункт " + approval, why)
    print("установлено файлов:", n)
    # сверка хэшей кандидатов с обеими копиями мода
    for root in bp.TARGETS.values():
        for rel, p in files.items():
            if bp.sha256_file(os.path.join(root, rel)) != bp.sha256_file(p):
                raise SystemExit("РАСХОДИТСЯ с кандидатом %s %s" % (root, rel))
    print("хэши кандидатов совпали в game и repo:", len(files))
    make_sheet(t, files, backup)


if __name__ == "__main__":
    main()
