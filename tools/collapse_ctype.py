#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Этап 0k обрушения: явная разметка типа конструкции (рецензия 0j). Модель не трогается.

Рецензия 0j: тип конструкции по данным карты не восстановить, его задаёт отдельная разметка. Рецензент
размечает по геометрии и картинкам, с категорией «неизвестно»; разметка фиксируется замком ДО прогона модели;
одни и те же правила типа проверяются на нескольких зданиях. «Тяжёлая плита» не назначается потому, что по
ожиданию крыша должна упасть: пакет не содержит ни ожиданий, ни результатов модели.

Единица разметки - связный (по сторонам клеток) участок пола на этаже z >= 1 здания, вместе с примыкающими
скатами и тентами (роли ROOF, TARP в слоте o). Здания - блоки и вырезки сценариев 0h и 0i (у них есть
ожидания рецензента; сами ожидания в пакет не идут).

Правила типов записаны заранее в census/collapse/stage0k/ctype_rules.md и закрыты замком вместе с пакетом.

    py -3.13 tools\collapse_ctype.py pack     пакет census/collapse/review0k (TASK.md, units.tsv, geom, units, frames)
    py -3.13 tools\collapse_ctype.py lock     замок ответа ctype.tsv - до любого прогона модели по типам
    py -3.13 tools\collapse_ctype.py check    ответ полон, типы из списка, замок цел
"""
import collections
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collapse_census as cc                      # noqa: E402
import collapse_v2 as V                           # noqa: E402
import collapse_v3 as T                           # noqa: E402
import collapse_pilot as P                        # noqa: E402
import collapse_v6 as M                           # noqa: E402

ENC = "utf-8-sig"
REVIEW = "census/collapse/review0k"
RULES = "census/collapse/stage0k/ctype_rules.md"
PACK_LOCK = "census/collapse/stage0k/ctype_pack.lock.txt"
ANSWER = REVIEW + "/ctype.tsv"
ANSWER_LOCK = "census/collapse/stage0k/ctype_answer.lock.txt"
TYPES = ["MASS", "HEAVY_SLAB", "FRAMED", "CANOPY_POSTS", "CANTILEVER", "LIGHT_DECK", "ARCH", "HULL", "UNKNOWN"]
ROOF_ROLES = {"ROOF", "TARP"}
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"


def buildings():
    """Здания сценариев 0h и 0i: {(terrain, block): blk}, без ожиданий."""
    import collapse_span_probe as SP
    out = {}
    for st, i, kind, group, blk, rm, mf, ms in SP.scenarios():
        out.setdefault((blk.terrain.upper(), blk.name.upper()), blk)
    return out


def units(blk):
    """Участки: [(z, [части f], [части o скатов и тентов])], z >= 1."""
    res = []
    for z in range(1, blk.sz):
        lv = blk.lv[z]
        cells = set(lv["f"])
        roof = {xy for xy, k in lv["o"].items() if blk.parts[k].get("role") in ROOF_ROLES}
        todo = cells | roof
        seen = set()
        for start in sorted(todo):
            if start in seen:
                continue
            comp, q = [], [start]
            seen.add(start)
            while q:
                x, y = q.pop()
                comp.append((x, y))
                for nb in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if nb in todo and nb not in seen:
                        seen.add(nb)
                        q.append(nb)
            fl = sorted(lv["f"][xy] for xy in comp if xy in lv["f"])
            ro = sorted(lv["o"][xy] for xy in comp if xy in roof)
            res.append((z, fl, ro))
    return res


def fname(tn, bn):
    return "%s__%s" % (tn, bn.replace("@", "_at_").replace(",", "_"))


def frame_png(st, idx, path):
    """Кадр записи MCD (r[0], R-259) на тёмном фоне x4 из art/TERRAIN; False - листа набора нет."""
    import glob
    from PIL import Image
    st = st.upper()
    mcd = [p for p in glob.glob("Пиратки/Dioxine_XPiratez/**/TERRAIN/*.MCD", recursive=True)
           if os.path.basename(p).upper() == st + ".MCD"]
    if not mcd or not os.path.exists("art/TERRAIN/%s.PCK/layout.json" % st):
        return False
    r = open(mcd[0], "rb").read()[idx * 62:(idx + 1) * 62]
    with open("art/TERRAIN/%s.PCK/layout.json" % st, encoding=ENC) as f:
        L = json.load(f)
    im = Image.open("art/TERRAIN/%s.PCK/original.png" % st).convert("RGBA")
    pw, ph = im.size[0] // L["columns"], im.size[1] // L["rows"]
    c, rr = r[0] % L["columns"], r[0] // L["columns"]
    cell = im.crop((c * pw, rr * ph, c * pw + pw, rr * ph + ph)).resize((32, 40), Image.NEAREST)
    bg = Image.new("RGBA", (32, 40), (40, 40, 48, 255))
    bg.alpha_composite(cell)
    bg.convert("RGB").resize((128, 160), Image.NEAREST).save(path)
    return True


def unit_map(blk, labels):
    """Этажи блока: у клеток участков - буква участка, у прочих пол '=' без буквы, '.' - пусто."""
    out = ["блок %s (%s) - буквы участков разметки; '.' - нет участка" % (blk.name, blk.terrain)]
    for z in range(blk.sz - 1, 0, -1):
        lab = {xy: l for (zz, xy), l in labels.items() if zz == z}
        if not lab:
            continue
        out.append("z=%d" % z)
        out.append("    " + "".join("%-2d" % (x % 100) for x in range(blk.sx)))
        for y in range(blk.sy):
            out.append("%3d " % y + "".join("%-2s" % lab.get((x, y), ".") for x in range(blk.sx)))
    return "\n".join(out)


def cmd_pack():
    if os.path.exists(PACK_LOCK):
        raise SystemExit("пакет уже закрыт замком: " + PACK_LOCK)
    if not os.path.exists(RULES):
        raise SystemExit("сначала правила типов: " + RULES)
    for d in ("geom", "units", "frames"):
        os.makedirs(REVIEW + "/" + d, exist_ok=True)
    rows, recs, n = [], collections.Counter(), 0
    for (tn, bn), blk in sorted(buildings().items()):
        labels = {}
        for j, (z, fl, ro) in enumerate(units(blk)):
            n += 1
            uid = "U-%03d" % n
            let = LETTERS[j] if j < len(LETTERS) else "?"
            for k in fl + ro:
                labels[(z, (k[1], k[2]))] = let
            rc = collections.Counter("%s:%d" % (blk.parts[k]["set"].upper(), blk.parts[k]["idx"]) for k in fl + ro)
            recs.update(rc)
            xs = [k[1] for k in fl + ro]
            ys = [k[2] for k in fl + ro]
            rows.append([uid, tn, bn, let, z, len(fl), len(ro), "%d-%d:%d-%d" % (min(xs), max(xs), min(ys), max(ys)),
                         T.compress(fl + ro), " ".join("%s x%d" % kv for kv in rc.most_common())])
        with open("%s/geom/%s.txt" % (REVIEW, fname(tn, bn)), "w", encoding=ENC) as f:
            f.write(V.geom_text(blk) + "\n")
        with open("%s/units/%s.txt" % (REVIEW, fname(tn, bn)), "w", encoding=ENC) as f:
            f.write(unit_map(blk, labels) + "\n")
    miss = []
    for r in sorted(recs):
        st, idx = r.rsplit(":", 1)
        if not frame_png(st, int(idx), "%s/frames/%s_%s.png" % (REVIEW, st, idx)):
            miss.append(r)
    cc.write_tsv(REVIEW + "/units.tsv", ["id", "terrain", "block", "letter", "z", "floors", "roof_parts", "bbox_x_y",
                                         "parts", "records"], rows)
    cc.write_tsv(ANSWER, ["id", "type", "confidence", "note"], [[r[0], "", "", ""] for r in rows])
    with open(REVIEW + "/TASK.md", "w", encoding=ENC) as f:
        f.write(TASK_MD)
    lines = ["пакет разметки типа конструкции, записано %s - до ответа и до любого прогона модели по типам" %
             time.strftime("%Y-%m-%d %H:%M:%S"),
             "участков %d, зданий %d, записей %d, без картинки %d" % (len(rows), len({(r[1], r[2]) for r in rows}),
                                                                       len(recs), len(miss))]
    for p in [RULES, REVIEW + "/units.tsv", REVIEW + "/TASK.md", "tools/collapse_ctype.py"]:
        lines.append("%s sha256 %s" % (p, M.sha(p)))
    with open(PACK_LOCK, "w", encoding=ENC) as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    if miss:
        print("без картинки:", " ".join(miss[:40]))


def read_answer():
    rows = P.read_tsv(ANSWER)
    bad = [r["id"] for r in rows if r["type"] not in TYPES]
    return rows, bad


def cmd_check():
    rows, bad = read_answer()
    print("участков %d, без типа или с чужим типом %d" % (len(rows), len(bad)))
    print(dict(collections.Counter(r["type"] for r in rows)))
    if os.path.exists(ANSWER_LOCK):
        with open(ANSWER_LOCK, encoding=ENC) as f:
            ok = M.sha(ANSWER) in f.read()
        print("замок ответа", "цел" if ok else "НАРУШЕН")
    return 1 if bad else 0


def cmd_lock():
    rows, bad = read_answer()
    if bad:
        raise SystemExit("ответ не полон: %d участков без типа из списка (%s...)" % (len(bad), " ".join(bad[:10])))
    if os.path.exists(ANSWER_LOCK):
        raise SystemExit("замок уже есть: " + ANSWER_LOCK)
    lines = ["ответ разметки типа конструкции закрыт %s - до прогона модели по типам" % time.strftime("%Y-%m-%d %H:%M:%S"),
             "типы: " + json.dumps(dict(collections.Counter(r["type"] for r in rows)), ensure_ascii=False),
             "%s sha256 %s" % (ANSWER, M.sha(ANSWER))]
    with open(ANSWER_LOCK, "w", encoding=ENC) as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


TASK_MD = """# Задание рецензенту: тип конструкции (этап 0k)

Ты определяешь, КАК устроено перекрытие или кровля здания из игры, по срезу этажей и по картинкам
плиток. Что упадёт, решать НЕ нужно. Ответ задаёт модели обрушения тип конструкции; модель потом будет
проверяться на этих зданиях, поэтому разметка должна опираться только на то, что видно.

## Что можно и что нельзя читать

Можно: только эта папка `census/collapse/review0k` (этот файл, `units.tsv`, `geom/`, `units/`, `frames/`).

Нельзя:
- `tools/collapse_*.py` и любой другой код модели;
- всё остальное в `census/collapse/` (`stage0*`, `review0*` кроме этой папки, `expect*.tsv`);
- `docs/research/building-collapse-*.md` и `docs/DECISIONS.md` в части обрушения.

Тип не выбирается по тому, что должно случиться при разрушении. Если тянет написать «тяжёлая плита,
потому что крыша такого дома должна рухнуть» - это довод о последствиях, а не об устройстве: ставь то,
что видно, или `UNKNOWN`.

## Единица разметки

Участок - связный кусок пола на одном этаже (z >= 1) здания вместе с примыкающими скатами и тентами.
`units.tsv`: `id`, здание (`terrain`, `block`), буква участка на карте участков, этаж `z`, число полов и
скатов, рамка `x`, `y`, части (`f:x:y:z`, `o:x:y:z`) и записи плиток (`НАБОР:номер xN`).

- `geom/<terrain>__<block>.txt` - срез здания буквами (как в прошлых заданиях: `#` несущая стена или окно,
  `D` дверь, `_` низкая; пол `=`; предмет `C` столб, `T` ферма, `M` массив, `B` блок-стена, `f` мебель,
  `t` ствол, `x` машина, `s` лестница, `k` крона, `r` скат, `a` тент, `p` трасса, `h` подвес, `o` мелочь).
  Помни: буквы предметов и стен частично взяты из класса плитки, а не из просмотра.
- `units/<terrain>__<block>.txt` - те же этажи, где у клеток участка стоит его буква.
- `frames/<НАБОР>_<номер>.png` - как плитка выглядит в игре (кадр 32x40 x4).

## Типы

| тип | что видно |
|---|---|
| `MASS` | массив: скала, грунт, кладка во всю клетку; «пол» - верх массива |
| `HEAVY_SLAB` | тяжёлое перекрытие (бетон, камень, плита) на стенах или колоннах, без видимых балок |
| `FRAMED` | перекрытие или кровля на балках, фермах, каркасе: доски, металлический настил, обычный дом, склад |
| `CANOPY_POSTS` | навес на отдельных стойках, под ним открыто (стены рядом не делают его плитой) |
| `CANTILEVER` | консоль: балкон, козырёк, навес, держится одной стороной за стену |
| `LIGHT_DECK` | лёгкий настил: мостки, решётка, галерея, переход |
| `ARCH` | арка или свод: держится пятами |
| `HULL` | корпус судна или летательного аппарата |
| `UNKNOWN` | по срезу и картинкам устройство не видно, или видно противоречивое |

Если участок явно состоит из двух устройств (например, плита дома и прилегающий навес), поставь тип
бо́льшей части и напиши в `note`, какие клетки устроены иначе (`f:x:y:z`).

## Что сделать

Заполни `ctype.tsv`: для каждого `id` - `type` (ровно одно слово из таблицы), `confidence`
(`high`, `medium`, `low`) и `note` (что видно: материал, на чём лежит; для `UNKNOWN` - чего не хватает).
`UNKNOWN` - честный ответ, а не ошибка. Строк не добавляй и не удаляй.
"""


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    os.chdir(os.path.dirname(HERE))
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    fn = {"pack": cmd_pack, "lock": cmd_lock, "check": cmd_check}.get(cmd)
    if fn is None:
        print(__doc__)
        sys.exit(0)
    sys.exit(fn() or 0)
