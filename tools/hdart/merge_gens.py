# -*- coding: utf-8 -*-
"""Сборка TERRAIN из всех поколений арта: по кадру - лучший, основа - прежний пак (R-061, R-066).

merge_best.py оставлял LoRA при ничьей «годен и там и там» - а глазами прежний пак лучше
(R-063, R-066), и на 8769 таких кадрах у него и балл выше. Здесь правило обратное:
  основа - прежний пак (TERRAIN_before_lora, 09-21);
  другое поколение ставится, только если оно ГОДНО, а основа НЕ годна; из нескольких таких -
  с наибольшим баллом score_batch;
  брак глазами (reject_eye.txt у LoRA, reject_old.txt у прежнего пака) снимает годность.
Решение переходит на копии той же картинки (census дублей, R-049) и на зеркала (R-051),
если у копии есть файл нужного поколения.

Поколения и их оценки (score_batch.py --mod <папка> --out <папка>):
  old   art/_backup/TERRAIN_before_lora_20260924_1057   art/_review/batch_score_old
  lora  LoRA 09-24: art/_backup/TERRAIN_lora_20260924_1353, остальное - в моде
                                                        art/_review/batch_score
  g0916 user/mods/hd/hd/TERRAIN                          art/_review/score_g0916
  g0922 art/_backup/hd_TERRAIN_2026-09-22                art/_review/score_g0922

Перед записью текущий TERRAIN мода целиком копируется в art/_backup/TERRAIN_mod_<время>.
    py -3 tools/hdart/merge_gens.py --dry-run
"""
import argparse
import csv
import glob
import io
import os
import shutil
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.join("tools", "hdart"))
import dupe_plan as dup  # noqa: E402

ENC = "utf-8-sig"
MOD = os.path.join(u"Пиратки", "Dioxine_XPiratez", "user", "mods", "hd", "hd", "TERRAIN")
BK = os.path.join("art", "_backup")
OLD = os.path.join(BK, "TERRAIN_before_lora_20260924_1057")
LORA_BK = os.path.join(BK, "TERRAIN_lora_20260924_1353")
GENS = {
    "old": (OLD, os.path.join("art", "_review", "batch_score_old")),
    "lora": (None, os.path.join("art", "_review", "batch_score")),
    "g0916": ("user/mods/hd/hd/TERRAIN", os.path.join("art", "_review", "score_g0916")),
    "g0922": (os.path.join(BK, "hd_TERRAIN_2026-09-22"), os.path.join("art", "_review", "score_g0922")),
}


def load_scores(d):
    out = {}
    with io.open(os.path.join(d, "score.tsv"), encoding=ENC, newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            out[(r[u"набор"], int(r[u"кадр"]))] = [int(r[u"годен"]), float(r[u"балл"])]
    return out


def load_rejects(p):
    out = set()
    if not os.path.exists(p):
        return out
    with io.open(p, encoding=ENC) as f:
        for line in f:
            s = line.split()
            if len(s) >= 2 and not line.startswith("#") and s[1].isdigit():
                n = s[0].upper()
                out.add((n if n.endswith(".PCK") else n + ".PCK", int(s[1])))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", dest="dry")
    ap.add_argument("--mod", default=MOD)
    args = ap.parse_args()

    scores = {g: load_scores(sd) for g, (_, sd) in GENS.items()}
    for k in load_rejects(os.path.join("art", "_review", "batch_score", "reject_eye.txt")):
        if k in scores["lora"]:
            scores["lora"][k][0] = 0
    for k in load_rejects(os.path.join("art", "_review", "batch_score", "reject_old.txt")):
        if k in scores["old"]:
            scores["old"][k][0] = 0

    def path(g, key, mod_copy):
        name, i = key
        if g == "lora":
            p = os.path.join(LORA_BK, name, "%d.png" % i)
            return p if os.path.exists(p) else os.path.join(mod_copy, name, "%d.png" % i)
        p = os.path.join(GENS[g][0], name, "%d.png" % i)
        return p if os.path.exists(p) else None

    def decide(key):
        """Поколение для кадра с прямой оценкой, или None, если оценок нет вовсе."""
        o = scores["old"].get(key)
        rivals = [(s[1], g) for g in ("lora", "g0916", "g0922")
                  for s in [scores[g].get(key)] if s and s[0]]
        if o is None and not any(key in scores[g] for g in scores):
            return None
        if o is not None and o[0]:
            return "old"
        if rivals:
            return max(rivals)[1]
        return "old"

    # решения по картинке: копии (census дублей) и точный хэш переписи (для зеркал)
    by_frame, _ = dup.load(os.path.join("art", "TERRAIN"))
    exact, mirror = {}, {}
    with io.open(os.path.join("census", "frames.tsv"), encoding=ENC, newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            if r[u"раздел"] != "TERRAIN":
                continue
            key = (r[u"набор"] + ".PCK", int(r[u"кадр"]))
            exact[key] = (r.get(u"точный") or "").strip()
            mirror[key] = (r.get(u"зеркало") or "").strip()
    scored = set()
    for g in scores:
        scored |= set(scores[g])
    by_dupe, by_exact = {}, {}
    for key in scored:
        g = decide(key)
        h = by_frame.get((key[0][:-4], key[1]), "")
        if h:
            by_dupe.setdefault(h, g)
        e = exact.get(key, "")
        if e:
            by_exact.setdefault(e, g)

    stamp = time.strftime("%Y%m%d_%H%M")
    mod_copy = os.path.join(BK, "TERRAIN_mod_%s" % stamp)
    src_mod = args.mod if args.dry else mod_copy
    if not args.dry:
        # LoRA-кадры, оставшиеся только в моде, читаем из резерва: мод перезаписывается
        print(u"резерв текущего мода -> %s" % mod_copy)
        shutil.copytree(args.mod, mod_copy)

    why, pick, plan = Counter(), Counter(), []
    for p in sorted(glob.glob(os.path.join(args.mod, "*.PCK", "*.png"))):
        name = os.path.basename(os.path.dirname(p))
        b = os.path.basename(p)[:-4]
        if not b.isdigit():
            continue
        key = (name, int(b))
        g = decide(key)
        tag = u"кадр"
        if g is None:
            h = by_frame.get((name[:-4], key[1]), "")
            e, m = exact.get(key, ""), mirror.get(key, "")
            if h in by_dupe:
                g, tag = by_dupe[h], u"копия"
            elif e in by_exact:
                g, tag = by_exact[e], u"точный"
            elif m in by_exact:
                g, tag = by_exact[m], u"зеркало"
            else:
                g, tag = "old", u"без оценки"
        src = path(g, key, src_mod)
        if src is None or not os.path.exists(src):
            g, tag = "old", tag + u", нет файла"
            src = path("old", key, src_mod)
        if src is None:
            continue
        why[tag] += 1
        pick[g] += 1
        plan.append((src, p))

    print(u"клеток: %d; откуда решение: %s" % (len(plan), dict(why)))
    print(u"поколение по кадру: %s" % dict(pick))
    if args.dry:
        print(u"пробный прогон, ничего не записано")
        return 0

    n = 0
    for src, dst in plan:
        if os.path.getsize(src) != os.path.getsize(dst) or open(src, "rb").read() != open(dst, "rb").read():
            shutil.copy2(src, dst)
            n += 1
    print(u"заменено клеток: %d" % n)
    with io.open(os.path.join("art", "_review", "merge_gens_%s.tsv" % stamp), "w", encoding=ENC, newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow([u"клетка", u"источник"])
        for src, dst in plan:
            w.writerow([dst, src])
    return 0


if __name__ == "__main__":
    sys.exit(main())
