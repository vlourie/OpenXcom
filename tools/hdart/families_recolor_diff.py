#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Семейства по новому поиску перекрасок против рабочего families.json - отдельный выход и разница (специалист 01.10).

Поиск перекрасок RELATION_DISCOVERY принят как компонент (holdout V4_R1: первичных 17/17, дополнение 5/5, STRONG 5/5).
Рабочий families.json не меняется: миграция - отдельное решение. Здесь новый поиск идёт по всей очереди отдельным
выходом, и печатается, что изменилось бы:

  новые пары          строгая перекраска (силуэт >= 0.98, цвет - функция цвета в обе стороны >= 0.98), а в рабочих
                      семействах пара не в одном семействе (members и review);
  слияния семейств    связная компонента новых пар задевает два и больше рабочих семейства;
  ложные цепочки      в компоненте есть пары, связанные только через третий кадр: напрямую строгий тест не проходят
                      (замыкание по цепочке склеило бы разные вещи);
  не подтверждены     рабочие связи recolor (канон -> член), которые строгий тест напрямую не проходит (для сведения:
                      старый поиск шёл по корреляции яркости, R-166).

Уровень пары: STRONG - набор того же номера целиком перекраска (relation_probe.sets, доля >= SET_SHARE) и MCD тот же;
иначе CANDIDATE. Только чтение, без видеокарты.

    py -3.13 tools/hdart/families_recolor_diff.py      -> art/objects/generation/probes/families-recolor-v2/
"""
import argparse
import json
import os
import sys
import time
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import identity_routing as ir          # noqa: E402
import relation_probe as rp            # noqa: E402

ROOT = ir.ROOT
OUT = os.path.join(ir.PROBES, "families-recolor-v2")


def strict(ma, ca, mb, cb):
    """(силуэт, f_ab, f_ba, проходит строгий тест)."""
    u = (ma | mb).sum()
    iou = float((ma & mb).sum() / u) if u else 0.0
    m = ma & mb
    f_ab = rp.func_map(ca[m], cb[m])[0] if m.any() else 0.0
    f_ba = rp.func_map(cb[m], ca[m])[0] if m.any() else 0.0
    return iou, f_ab, f_ba, iou >= rp.GEO and f_ab >= rp.FUNC and f_ba >= rp.FUNC


def production(path=rp.FAMILIES):
    """Ключ -> семейство (members и review); рабочие связи recolor (канон, член)."""
    fams = ir.load_json(path)
    fam_of, links = {}, []
    for fam in fams:
        for part in ("members", "review"):
            for m in fam.get(part, []):
                for k in m.get("keys", []):
                    fam_of.setdefault(k.upper(), fam["family_id"])
        for m in fam.get("members", []):
            if m.get("relation") == "recolor":
                links.append((fam["canonical"], m["src"][0] if m.get("src") else m["keys"][0], fam["family_id"]))
    return fam_of, links


def unconf_why(iou, f_ab, f_ba):
    """Почему рабочая связь recolor не проходит строгий тест."""
    if iou < rp.GEO:
        return "силуэт ниже %.2f" % rp.GEO
    if max(f_ab, f_ba) >= rp.FUNC:
        return "функция в одну сторону (палитра сжата)"
    if min(f_ab, f_ba) >= 0.90:
        return "функция 0.90-0.98 в обе стороны"
    return "цвет не функция цвета"


class UF:
    def __init__(self):
        self.p = {}

    def find(self, x):
        while self.p.setdefault(x, x) != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)


def diff(pairs, keys_of, fam_of, direct):
    """pairs: [(a, b, level)] строгих перекрасок; keys_of: представитель -> все ключи предмета;
    direct(a, b) -> строгий тест напрямую. Возвращает новые пары, слияния, ложные цепочки."""
    fams = lambda k: {fam_of[x.upper()] for x in keys_of.get(k, [k]) if x.upper() in fam_of}   # noqa: E731
    new = []
    for a, b, lv in pairs:
        fa, fb = fams(a), fams(b)
        if not (fa & fb):
            new.append({"a": a, "b": b, "level": lv, "fam_a": sorted(fa), "fam_b": sorted(fb),
                        "case": "оба вне семейств" if not fa and not fb else
                                "один вне семейств" if not fa or not fb else "разные семейства"})
    uf = UF()
    for a, b, _lv in pairs:
        uf.union(a, b)
    comp = defaultdict(set)
    for a, b, _lv in pairs:
        comp[uf.find(a)].update((a, b))
    edges = {frozenset((a, b)) for a, b, _lv in pairs}
    merges, chains = [], []
    for root, ks in comp.items():
        ks = sorted(ks)
        fs = sorted(set().union(*(fams(k) for k in ks)))
        if len(fs) >= 2:
            merges.append({"members": ks, "families": fs})
        bad = []
        for i, a in enumerate(ks):
            for b in ks[i + 1:]:
                if frozenset((a, b)) in edges:
                    continue
                ok = direct(a, b)
                if not ok:
                    bad.append([a, b])
        if bad:
            chains.append({"members": ks, "families": fs, "not_direct": bad,
                           "pairs_total": len(ks) * (len(ks) - 1) // 2})
    return new, merges, chains, comp


def run(out=OUT):
    t0 = time.time()
    ctx = rp.Ctx()
    items = ir.load_json(rp.ITEMS)
    keys_of = {it["src"][0]: it["keys"] for it in items if it["kind"] != "составной"}
    os.makedirs(out, exist_ok=True)
    _res, found = rp.scan(ctx, out)
    fam_of, links = production()
    cache = {}

    def arr(k):
        if k not in cache:
            a = ctx.rgba(k)
            cache[k] = None if a is None else rp.codes(a)
        return cache[k]

    def direct(a, b):
        A, B = arr(a), arr(b)
        return bool(A is not None and B is not None and strict(A[0], A[1], B[0], B[1])[3])

    set_cache = {}

    def level(a, b):
        sa, fa = rp.of.split(a)
        sb, fb = rp.of.split(b)
        twin = False
        if fa == fb and sa.upper() != sb.upper():
            key = tuple(sorted((sa.upper(), sb.upper())))
            if key not in set_cache:
                set_cache[key] = rp.sets(ctx, key[0], key[1])
            twin = set_cache[key]["share_strict"] >= rp.SET_SHARE
        if not twin:
            return "CANDIDATE"
        ia, ib = ctx.st.info(sa, fa), ctx.st.info(sb, fb)
        same = (ia.get("rec") and ib.get("rec") and not [k for k in ia["phys"] if ia["phys"][k] != ib["phys"].get(k)]
                and bool((ia["vox"] == ib["vox"]).all()))
        return "STRONG" if same else "CANDIDATE"

    pairs = [(x[0], x[1], level(x[0], x[1])) for x in found if x[2] >= rp.FUNC and x[3] >= rp.FUNC and not x[5]]
    new, merges, chains, comp = diff(pairs, keys_of, fam_of, direct)
    unconf = []
    for c, m, fid in links:
        A, B = arr(c), arr(m)
        if A is None or B is None:
            continue
        iou, f_ab, f_ba, ok = strict(A[0], A[1], B[0], B[1])
        if not ok:
            unconf.append({"family": fid, "canonical": c, "member": m, "iou": round(iou, 3),
                           "f_ab": round(f_ab, 3), "f_ba": round(f_ba, 3), "why": unconf_why(iou, f_ab, f_ba)})
    res = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "production_untouched": rp.FAMILIES,
           "thresholds": {"GEO": rp.GEO, "FUNC": rp.FUNC, "SET_SHARE": rp.SET_SHARE},
           "pairs": len(pairs), "pairs_by_level": dict(Counter(p[2] for p in pairs)),
           "components": len(comp), "new_pairs": new, "new_by_case": dict(Counter(x["case"] for x in new)),
           "new_by_level": dict(Counter(x["level"] for x in new)), "merges": merges, "false_chains": chains,
           "production_recolor_links": len(links), "production_not_confirmed": unconf,
           "not_confirmed_by_why": dict(Counter(x["why"] for x in unconf)),
           "seconds": round(time.time() - t0)}
    ir.dump_json(os.path.join(out, "diff.json"), res)
    with open(os.path.join(out, "recolor_pairs.tsv"), "w", encoding=ir.ENC, newline="") as f:
        f.write("a\tb\tlevel\n")
        for a, b, lv in pairs:
            f.write("%s\t%s\t%s\n" % (a, b, lv))
    write_md(out, res)
    return res


def write_md(out, res):
    L = ["# Семейства: новый поиск перекрасок против рабочего families.json", "",
         "Отдельный выход; рабочий %s не менялся, миграция - отдельное решение." % res["production_untouched"], "",
         "| что | число |", "|---|---|",
         "| строгих пар перекраски | %d (%s) |" % (res["pairs"], ", ".join("%s %d" % kv for kv in
                                                                         sorted(res["pairs_by_level"].items()))),
         "| компонент | %d |" % res["components"],
         "| новых пар (не в одном рабочем семействе) | %d: %s |" % (
             len(res["new_pairs"]), ", ".join("%s %d" % kv for kv in sorted(res["new_by_case"].items()))),
         "| из них STRONG / CANDIDATE | %d / %d |" % (res["new_by_level"].get("STRONG", 0),
                                                     res["new_by_level"].get("CANDIDATE", 0)),
         "| слияний рабочих семейств | %d |" % len(res["merges"]),
         "| компонент с ложной цепочкой | %d (пар не напрямую: %d) |" % (
             len(res["false_chains"]), sum(len(c["not_direct"]) for c in res["false_chains"])),
         "| рабочих связей recolor не проходят строгий тест | %d из %d |" % (
             len(res["production_not_confirmed"]), res["production_recolor_links"])]
    L += ["| не подтверждены: %s | %d |" % kv for kv in sorted(res["not_confirmed_by_why"].items())]
    L += ["",
         "## Слияния семейств (первые 40)", "", "| семейства | кадры |", "|---|---|"]
    L += ["| %s | %s |" % (", ".join(m["families"]), ", ".join(m["members"][:8]) + (" ..." if len(m["members"]) > 8
                                                                                    else ""))
          for m in res["merges"][:40]]
    L += ["", "## Ложные цепочки (первые 30)", "", "| кадры компоненты | не напрямую |", "|---|---|"]
    L += ["| %s | %s |" % (", ".join(c["members"][:8]), "; ".join(" ~ ".join(p) for p in c["not_direct"][:4]))
          for c in res["false_chains"][:30]]
    L += ["", "## Новые пары STRONG (первые 40)", "", "| a | b | случай | семейства |", "|---|---|---|---|"]
    L += ["| %s | %s | %s | %s / %s |" % (x["a"], x["b"], x["case"], ",".join(x["fam_a"]) or "-",
                                         ",".join(x["fam_b"]) or "-")
          for x in res["new_pairs"] if x["level"] == "STRONG"][:40]
    with open(os.path.join(out, "diff.md"), "w", encoding=ir.ENC) as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L[:L.index("## Слияния семейств (первые 40)")]))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    os.chdir(ROOT)
    run()


if __name__ == "__main__":
    main()
