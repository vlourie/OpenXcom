#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""PROD_TWO_PASS_V3SF - пары SAME_FRAMEWORK_DIFFERENT_OBJECT классификации V4 как независимые предметы через
замороженный V3 (Vitali 07.10).

Классификация пула V4 (prod-two-pass-v4/pool_cls/classified.tsv) нашла 66 пар «тот же каркас, другой предмет»:
это не стороны одного предмета, связывать их не надо. Каждый кадр пары - самостоятельный предмет; цепочка та же,
что V3 (опознание -> RENDER -> судьи -> STRICT -> пересмотр опознания -> THIRD -> final_select -> лист Vitali).
Код V3 не правится (замок v3_baseline, 123 файла): здесь своя папка и свой отбор; check зовётся перед каждым
шагом, который строит партию или грузит модель.

Отбор (select):
    кадры всех SF-пар; кадр берётся, только если ВСЕ его вопросы семейства (families.json review) - сами SF-пары.
    Вне партии с причиной (excluded_sf.tsv): уже установлен V4; пара с ним UNCERTAIN или NOT_OBJECT (residual V4);
    есть вопрос вне SF (weak_mirror, indirect_chain - новое исследование связей не открываем); action не GENERATE
    (выводится из канонического - DERIVE, GENERATE_WITH); не один кадр (анимация); нет строки плана.
    Дальше - pilot_batch.select и фильтры V3 без изменений, уровни опознания любые (HARD - гипотеза «спорная»).
Связи (relations): замороженные V7 и classify RESTORE_BATCH_V1; у кадров партии снимаются только SF-вопросы
(вопрос семейства, блокеры in_review / family_review) и V7-связь с самим SF-партнёром.

    py -3.13 tools/hdart/prod_two_pass_v3sf.py select
    py -3.13 tools/hdart/prod_two_pass_v3sf.py cards     (identity_card.make, без SF-партнёров в «семействе»)
    py -3.13 tools/hdart/identity_auto.py --batch art/objects/generation/probes/prod-two-pass-v3sf pack ...
    py -3.13 tools/hdart/prod_two_pass_v3sf.py build | relations | freeze | prompts | report | strict | third
    рендер - только через очередь:
        py -3.13 tools/gpuq.py add --name prod_two_pass_v3sf_restore --cwd E:/OpenXCom -- \
            E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/render_chunks.py \
            --out art/objects/generation/probes/prod-two-pass-v3sf -- \
            E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/prod_two_pass_v3sf.py render
"""
import csv
import json
import os
import subprocess
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import prod_two_pass_v1 as v1      # noqa: E402
import prod_two_pass_v2 as v2      # noqa: E402
import prod_two_pass_v3 as v3      # noqa: E402  (настраивает v1/v2 на V3 - ниже переставляется на V3SF)

V3_OUT = os.path.join(v1.PROBES, "prod-two-pass-v3")
V4_OUT = os.path.join(v1.PROBES, "prod-two-pass-v4")
CLS = os.path.join(V4_OUT, "pool_cls", "classified.tsv")
SF = "SAME_FRAMEWORK_DIFFERENT_OBJECT"
V4_RESIDUAL = ("UNCERTAIN", "NOT_OBJECT")
v1.PROFILE = "PROD_TWO_PASS_V3SF"
v1.OUT = os.path.join(v1.PROBES, "prod-two-pass-v3sf")
v1.THIRD = os.path.join(v1.OUT, "third")
v1.TARGET = 1000
v1.EXCLUDE, v1.EXCLUDE_LIKE = {}, {}
v1.__file__ = os.path.abspath(__file__)
v2.__file__ = os.path.abspath(__file__)
v2.ALL = os.path.join(v1.OUT, "candidates_all.json")
v2.IDENTITY = os.path.join(v1.OUT, "identity", "auto", "identity.tsv")
v2.JUDGE = os.path.join(v1.OUT, "judge")
_tuning = v1.tuning_assets                 # опыты, V1, V2 (prod_two_pass_v3)


def tsv(p):
    with open(p, encoding=v1.ENC, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def tuning_assets():
    """Опыты, V1, V2, все кандидаты V3 и установленное V4."""
    out = _tuning()
    with open(os.path.join(V3_OUT, "candidates_all.json"), encoding=v1.ENC) as f:
        v3c = [c["asset_id"].upper() for c in json.load(f)]
    if len(v3c) < 100:
        raise SystemExit("кандидаты V3 прочитались не целиком: %d" % len(v3c))
    for a in v3c:
        out.setdefault(a, "партия PROD_TWO_PASS_V3")
    for r in tsv(os.path.join(V4_OUT, "status.tsv")):
        for k in r["installed"].split():
            out.setdefault(k.upper(), "установлен V4")
    return out


v1.tuning_assets = tuning_assets


def sf_state():
    """-> (кадры SF, партнёры SF по кадру, категория пары, рёбра вопросов семейств по кадру)."""
    import pilot_batch as pbt
    rows = tsv(CLS)
    cat = {frozenset((r["a"].upper(), r["b"].upper())): (r["category"], r["confidence"]) for r in rows}
    partners = {}
    for r in rows:
        if r["category"] == SF:
            a, b = r["a"].upper(), r["b"].upper()
            partners.setdefault(a, set()).add(b)
            partners.setdefault(b, set()).add(a)
    if len([r for r in rows if r["category"] == SF]) != 66:
        raise SystemExit("пар SF не 66 - classified.tsv не тот")
    with open(pbt.FAMS, encoding=v1.ENC) as f:
        fams = json.load(f)
    edges, fam_edges = {}, {}
    for fm in fams:
        can = fm["canonical"].upper()
        for x in fm.get("review", []):
            b = x["keys"][0].upper()
            for p, q in ((can, b), (b, can)):
                edges.setdefault(p, []).append((q, x.get("reason", "")))
            fam_edges.setdefault(fm["family_id"].upper(), []).append((can, b))
    return partners, cat, edges, fam_edges


def sf_free(partners, cat, edges):
    """Кадр SF, у которого каждый вопрос семейства - его SF-пара; -> (свободные, {кадр: причина вне партии})."""
    free, why = set(), {}
    for k in sorted(partners):
        own = edges.get(k, [])
        res = [(b, r, cat.get(frozenset((k, b)), ("НЕ РАЗОБРАНО", ""))) for b, r in own]
        resid = [b for b, _r, c in res if c[0] in V4_RESIDUAL]
        other = ["%s %s %s" % (b, r, c[0]) for b, r, c in res if c[0] != SF]
        if resid:
            why[k] = "residual V4: пара с %s %s" % (" ".join(resid), "/".join(sorted({c[0] for _b, _r, c in res
                                                                                      if c[0] in V4_RESIDUAL})))
        elif other:
            why[k] = "вопрос вне SF (новое исследование связей не открываем): " + "; ".join(other)
        else:
            free.add(k)
    return free, why


def fsplit(blockers):
    return " ".join(b for b in blockers.split() if b.split(":")[0] not in ("in_review", "family_review"))


def baseline_check():
    r = subprocess.run([sys.executable, os.path.join(HERE, "v3_baseline.py"), "check"], cwd=v1.ROOT)
    if r.returncode:
        raise SystemExit("замок V3 нарушен - партия на изменённом коде не идёт")


def do_select():
    lp = os.path.join(v1.OUT, "identity_list.json")
    if os.path.exists(lp):
        raise SystemExit("identity_list.json уже есть - список не переписываю")
    import re
    import photo_accept as pa
    import pilot_batch as pbt
    partners, cat, edges, fam_edges = sf_state()
    free, out_why = sf_free(partners, cat, edges)
    used = tuning_assets()
    plan = {r["asset_id"].upper(): r for r in tsv(pbt.PLAN)}
    for k in sorted(partners):
        r = plan.get(k)
        if k in used:
            out_why[k] = used[k]
        elif r is None:
            out_why.setdefault(k, "нет строки в generation.tsv")
        elif r["action"] != "GENERATE":
            out_why[k] = "action %s: выводится из канонического, не самостоятельный заказ" % r["action"]
        elif r["kind"] != "один":
            out_why[k] = "не один кадр (%s) - V3 рисует только одиночные" % r["kind"]
    free -= set(out_why)
    # вопрос семейства снимается целиком, только если все его рёбра - SF-пары (иначе остаётся у семейства)
    sf_fams = {f for f, es in fam_edges.items()
               if all(cat.get(frozenset(e), ("",))[0] == SF for e in es)}
    keep = (pbt.LEVELS, pbt.GEOMETRY, pbt.open_questions, pbt.read_tsv)

    def questions(fams):
        return keep[2](fams) - free - sf_fams

    def read_tsv(p):
        rows = keep[3](p)
        if os.path.abspath(p) == os.path.abspath(pbt.PLAN):
            rows = [dict(r, blockers=fsplit(r["blockers"])) if r["asset_id"].upper() in free else r for r in rows]
        return rows

    pbt.LEVELS = dict(keep[0], HARD=v3.LEVEL, OLD_AGENT="OLD_AGENT_CARD", UNKNOWN="UNKNOWN_CARD")
    pbt.GEOMETRY = re.compile(r"(?!x)x")
    pbt.open_questions, pbt.read_tsv = questions, read_tsv
    try:
        cands, _drop = pbt.select()
    finally:
        pbt.LEVELS, pbt.GEOMETRY, pbt.open_questions, pbt.read_tsv = keep
    got = {c["asset_id"].upper(): c for c in cands}
    for k in sorted(free):
        if k not in got:
            r = plan[k]
            out_why[k] = "отсеян pilot_batch.select: %s" % (
                "не object (%s)" % r["asset_class"] if r["asset_class"] != "object" else
                "кусок большего (R-153)" if "part_fragment_suspect" in r["blockers"] else
                "блокеры %s" % fsplit(r["blockers"]) if fsplit(r["blockers"]).strip() else
                "природа, перекраска семейства или другой бок")
    ident = {r["asset_id"]: r for r in v1.read_tsv(v1.IDENT)}
    dec = {r["asset_id"]: r for r in v1.read_tsv(v1.ID_LOG)}
    picked, taken = [], []
    for c in sorted((got[k] for k in free if k in got), key=lambda c: (-c["places"], c["asset_id"])):
        aid = c["asset_id"].upper()
        key = c["asset_id"] if c["asset_id"] in ident else c["family"]
        row = ident.get(key, {})
        d = dec.get(key, {}).get("decision", "") or dec.get(c["family"], {}).get("decision", "")
        why = None
        if pa.DEBRIS.search(c["name"]) or pa.DEBRIS.search(c["other_name"]):
            why = "обломки или кусок по названию (R-153)"
        elif d in v1.REJECTED or (not d and row.get("status") in v1.REJECTED):
            why = "опознание отклонено человеком"
        elif not [n for n in (c["name"], c["other_name"]) if n.strip() and n.strip().upper() != "UNKNOWN"]:
            why = "нет ни одного старого названия"
        elif set(c["categories"]) & v3.NATURE_ANY or pbt.NATURE.search(c["name"] + " " + c["other_name"]):
            why = "природа или рельеф хотя бы у одной модели (пул природы закрыт)"
        elif v1.set_variant(aid, taken):
            why = "вероятная перекраска набора (R-166)"
        if why:
            out_why[aid] = why
            continue
        if c["level"] == v3.LEVEL:
            card = v3.hypothesis(c)
        else:
            card = (dec[key]["identity"] if d == "EDIT" else row.get("identity") or row.get("proposed")
                    or c["name"]).strip()
        taken.append(aid)
        picked.append(dict(c, ident_key=c["asset_id"], card=card, confirmed=False,
                           sf_partners=sorted(partners[aid])))
    os.makedirs(v1.OUT, exist_ok=True)
    v1.dump(picked, v2.ALL)
    v1.dump([{"category": "prod %d" % (i + 1), "asset_id": c["ident_key"], "rank": c["rank"], "places": c["places"],
              "kind": "один", "identity_status": c["level"], "identity": c["card"], "for": c["asset_id"]}
             for i, c in enumerate(picked)], lp)
    with open(os.path.join(v1.OUT, "excluded_sf.tsv"), "w", encoding=v1.ENC, newline="") as f:
        f.write("asset_id\tsf_partners\treason\n")
        for k in sorted(out_why):
            f.write("%s\t%s\t%s\n" % (k, " ".join(sorted(partners.get(k, ()))), out_why[k]))
    v1.dump({"created": v1.time.strftime("%Y-%m-%dT%H:%M:%S"), "profile": v1.PROFILE,
             "group": "SAME_FRAMEWORK_DIFFERENT_OBJECT V4 (66 pairs) as independent objects, Vitali 07.10",
             "sf_frames": len(partners), "eligible": len(picked), "excluded": len(out_why),
             "levels": dict(Counter(c["level"] for c in picked)),
             "excluded_reasons": dict(Counter(w.split(":")[0] for w in out_why.values())),
             "sf_family_questions_lifted": sorted(sf_fams)},
            os.path.join(v1.OUT, "candidates_manifest.json"))
    if len(picked) + len(out_why) != len(partners):
        raise SystemExit("счёт не сходится: %d + %d != %d" % (len(picked), len(out_why), len(partners)))
    print("кадров SF %d: в партию %d, вне %d" % (len(partners), len(picked), len(out_why)))
    print("вне партии: %s" % dict(Counter(w.split(":")[0] for w in out_why.values())))
    print("уровни: %s" % dict(Counter(c["level"] for c in picked)))
    for i, c in enumerate(picked, 1):
        print("  %3d %-24s мест %-4d %-16s %s" % (i, c["asset_id"], c["places"], c["level"], c["card"][:80]))


def do_relations():
    """Шаг связей V3; у кадров партии сняты только SF-вопросы и V7-связь с SF-партнёром."""
    partners, cat, edges, fam_edges = sf_state()
    with open(v2.ALL, encoding=v1.ENC) as f:
        batch = {c["asset_id"].upper() for c in json.load(f)}
    rb = v1.use_rb()
    base = rb.classify

    def classify(a, claims, batch_, comp, questions, gen_row):
        A = a.upper()
        if A in batch:
            questions = questions - {A}
            gen_row = dict(gen_row, blockers=fsplit(gen_row["blockers"]))
            claims = [c for c in claims if not ({x.upper() for x in c["pair"]} - {A}) & partners.get(A, set())]
        return base(a, claims, batch_, comp, questions, gen_row)

    rb.classify = classify
    try:
        v1.do_relations()
    finally:
        rb.classify = base


def do_cards():
    """Карточки опознания партии: identity_card.make без правки кода V3; у кадров партии из раздела «семейство»
    (панель и факты) убраны только SF-партнёры - подпись possible other side противоречит итогу V4 (Vitali 07.10).
    Остальные связи семейства не трогаются."""
    import identity_card as ic
    import identity_propose as ip
    partners = sf_state()[0]
    with open(os.path.join(v1.OUT, "identity_list.json"), encoding=v1.ENC) as f:
        assets = [x["asset_id"] for x in json.load(f)]
    out = os.path.join(v1.OUT, "identity", "cards")
    if os.path.exists(os.path.join(out, "cards.json")):
        raise SystemExit("карточки уже есть: %s - убрать папку перед пересборкой" % out)
    facts, dropped = ip.Context.facts, Counter()

    def facts_sf(self, row, it):
        fx = facts(self, row, it)
        sf = partners.get(row["asset_id"].upper(), set())
        for part in ("family", "other_sides"):
            keep = [x for x in fx[part] if x["key"].upper() not in sf]
            dropped[row["asset_id"]] += len(fx[part]) - len(keep)
            fx[part] = keep
        return fx
    ip.Context.facts = facts_sf
    ic.make(assets, out, "PROD_TWO_PASS_V3SF: SAME_FRAMEWORK_DIFFERENT_OBJECT")
    print("карточек %d, SF-партнёров убрано %d у %d кадров" % (len(assets), sum(dropped.values()),
                                                             len([a for a in dropped if dropped[a]])))


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    sys.stdout.reconfigure(encoding="utf-8")
    os.chdir(v1.ROOT)
    if cmd in ("build", "relations", "freeze", "prompts", "render", "strict", "strict-chunk", "third",
               "third-chunk"):
        baseline_check()
    if cmd == "select":
        do_select()
    elif cmd == "relations":
        do_relations()
    elif cmd == "cards":
        do_cards()
    else:
        v2.main()


if __name__ == "__main__":
    main()
