#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка tools/hdart/routing_rules_v6.py на синтетике, у каждого правила - контроль:
перекраска без доказанной основы не DERIVED (контроль: подтверждённая человеком - DERIVED); MCD alt даёт только
REVIEW и не входит в точность родства; die без подтверждения - REVIEW (контроль: обломок меньше основы -
STATE_VARIANT; та же связь внутри петли анимации - REVIEW); анимация - ANIMATION_FAMILY; структура раньше
зеркала и состояния; MATERIAL_VARIANT по набору-двойнику, без набора - не довод (R-166), строгая перекраска - не
вариант; перекраска внутри одной петли анимации снимается с утверждений.
V6_PREP_R2: слабая улика стены ось A не переопределяет (контроль: в V6-prep - EXCLUDE S), сильная - да; die без
проверки объёма, но не внутри петли и не общий обломок; R0p - только REVIEW R7o, DERIVED не даёт никогда
(контроль: в post-hoc V6-prep - DERIVED).

    py -3.13 tools/test_routing_rules_v6.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hdart"))
import routing_rules_v6 as v6  # noqa: E402

FAILS = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def meta(gen=None, rels=None, fam_rel=None, modular=None, cls=None, review=None):
    return (gen or {}, fam_rel or {}, review or set(), set(), modular or set(), cls or {}, rels or {})


NONE = ("", "")
WALL = ("STRONG", "запись стены (Tile_Type 2)")
REC = {"kind": "RECOLOR_OF", "level": "STRONG", "relative": "T:1", "side": "derived", "verified": False}
NB = {"kind": "FIXED_NEIGHBOUR", "level": "CANDIDATE", "side": "part?", "relative": "S:9"}


def link(state, base, via, level="STRONG", root=None):
    return {"state": state, "base": base, "via": via, "level": level, "root": root or base, "why": "",
            "kind": {"die": "STATE_VARIANT_OF", "alt": "STATE_VARIANT_OF", "anim": "ANIMATION_FRAME_OF"}[via]}


def view(links, groups=None, vols=None, mode="corroborated"):
    idx = v6.ms.index({"S": links})
    vol = (lambda k: (vols or {}).get(k))
    return {k: v6.mcd_view(v, groups or {}, vol, mode) for k, v in idx.items()}


def r(a, sk, m, mv=None, surf=NONE, variants=None, **opts):
    return v6.route_v6(a, sk, m, (mv or {}).get(a, []), surf, variants or [], opts=opts)


def pair(iou=1.0, fab=1.0, fba=0.9, vox=True, phys=()):
    return {"1_geometry": {"iou": iou}, "4_palette": {"f_ab": fab, "f_ba": fba},
            "5_mcd": {"vox_same": vox, "phys_diff": list(phys)}}


def sets(share=0.85, strict=0.6, n=59):
    return {"compared": n, "share_same_geometry": share, "share_strict": strict}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    # 1. перекраска симметрична
    u = r("S:1", "OBJECT", meta(rels={"S:1": [REC]}))
    check("доказанная перекраска без основы - не DERIVED, одиночный с pair_pick",
          u[0] == "STANDALONE_RENDER" and u[4] is True)
    u = r("S:1", "OBJECT", meta(rels={"S:1": [dict(REC, verified=True)]}))
    check("контроль: основа подтверждена человеком - DERIVED R0v", u[:2] == ("DERIVED", "R0v"))
    u = r("S:1", "OBJECT", meta(gen={"S:1": {"relation": "recolor"}}, fam_rel={"S:1": "recolor"}))
    check("recolor семейства (канон семьи) маршрут не меняет", u[0] == "STANDALONE_RENDER" and u[4] is False)
    cand = dict(REC, level="CANDIDATE")
    check("перекраска CANDIDATE маршрут не меняет",
          r("S:1", "OBJECT", meta(rels={"S:1": [cand]}))[0] == "STANDALONE_RENDER")
    check("вариант V5: перекраска CANDIDATE -> REVIEW R7r",
          r("S:1", "OBJECT", meta(rels={"S:1": [cand]}), recolor_candidate_review=True)[:2] == ("REVIEW", "R7r"))

    # 2. MCD
    alt = view([link("S:2", "S:3", "alt")])
    check("alt - только REVIEW R7a", r("S:2", "OBJECT", meta(), alt)[:2] == ("REVIEW", "R7a"))
    check("alt у основы - тоже улика", r("S:3", "OBJECT", meta(), alt)[:2] == ("REVIEW", "R7a"))
    check("контроль: alt без REVIEW - одиночный",
          r("S:2", "OBJECT", meta(), alt, alt_review=False)[0] == "STANDALONE_RENDER")
    raw, dropped = v6.claims_v6(["S:2"], {}, alt, {}, {}, {})
    check("alt не входит в точность родства", raw == [] and len(dropped) == 1)
    die = [link("S:2", "S:3", "die")]
    ok = view(die, vols={"S:2": 40, "S:3": 300})
    check("die, обломок меньше основы - STATE_VARIANT R3m", r("S:2", "OBJECT", meta(), ok)[:2] == ("STATE_VARIANT", "R3m"))
    big = view(die, vols={"S:2": 300, "S:3": 300})
    check("die, объём не меньше - REVIEW R7m", r("S:2", "OBJECT", meta(), big)[:2] == ("REVIEW", "R7m"))
    loop = view(die, groups={"S:2": "S:3", "S:3": "S:3"}, vols={"S:2": 40, "S:3": 300})
    check("die внутри петли анимации - REVIEW R7m", r("S:2", "OBJECT", meta(), loop)[:2] == ("REVIEW", "R7m"))
    check("вариант V5: die без подтверждения - R3m",
          r("S:2", "OBJECT", meta(), view(die, vols={"S:2": 300, "S:3": 300}, mode="as_v5"))[1] == "R3m")
    raw, _ = v6.claims_v6(["S:2"], {}, big, {}, {}, {})
    check("die без подтверждения не утверждение", raw == [])
    raw, _ = v6.claims_v6(["S:2"], {}, ok, {}, {}, {})
    check("контроль: die с подтверждением - утверждение", len(raw) == 1 and raw[0][5] == "mcd_die")
    an = view([link("S:5", "S:4", "anim")])
    check("анимация - ANIMATION_FAMILY R3a", r("S:5", "OBJECT", meta(), an)[:2] == ("ANIMATION_FAMILY", "R3a"))

    # 3. структура раньше родства
    mir = meta(gen={"S:1": {"relation": "mirror"}}, modular={"S:1"})
    check("модуль раньше зеркала - STRUCTURAL_MODULAR", r("S:1", "OBJECT", mir)[:2] == ("STRUCTURAL_MODULAR", "R6"))
    check("контроль: без модуля зеркало - DERIVED R4",
          r("S:1", "OBJECT", meta(gen={"S:1": {"relation": "mirror"}}))[:2] == ("DERIVED", "R4"))
    comp = meta(gen={"S:1": {"relation": "mirror", "kind": "составной"}})
    check("составной раньше зеркала - COMPOSITE_PART", r("S:1", "OBJECT", comp)[0] == "COMPOSITE_PART")
    check("поверхность раньше состояния MCD - EXCLUDE S", r("S:2", "OBJECT_PART", meta(), ok, WALL)[:2] == ("EXCLUDE", "S"))
    check("OBJECT_PART раньше состояния - REVIEW R8a", r("S:2", "OBJECT_PART", meta(), ok)[:2] == ("REVIEW", "R8a"))
    check("part_fragment_suspect раньше зеркала - REVIEW R7p",
          r("S:1", "OBJECT", meta(gen={"S:1": {"relation": "mirror", "blockers": "part_fragment_suspect:x"}}))[1] == "R7p")
    check("вариант: R5/R6 раньше S",
          r("S:1", "OBJECT_PART", meta(modular={"S:1"}), surf=WALL, modular_before_surface=True)[1] == "R6" and
          r("S:1", "OBJECT_PART", meta(modular={"S:1"}), surf=WALL)[1] == "S")

    # 4. MATERIAL_VARIANT_OF / STYLE_VARIANT_OF
    k = v6.variant_kind(pair(phys=("flammable", "footstep")), sets())
    check("снег: силуэт, воксели, набор-двойник, функция в одну сторону - MATERIAL_VARIANT_OF",
          k[0] == "MATERIAL_VARIANT_OF" and k[2] == "a->b")
    check("та же физика - STYLE_VARIANT_OF", v6.variant_kind(pair(), sets())[0] == "STYLE_VARIANT_OF")
    check("без набора-двойника - не довод (R-166)", v6.variant_kind(pair(), sets(share=0.5))[0] == "")
    check("набор мал - не довод", v6.variant_kind(pair(), sets(n=3))[0] == "")
    check("строгая перекраска - не вариант", v6.variant_kind(pair(fba=1.0), sets())[0] == "")
    check("набор - строгая перекраска - не вариант (это LOCAL_EDIT)", v6.variant_kind(pair(), sets(strict=0.9))[0] == "")
    check("другие воксели - не вариант", v6.variant_kind(pair(vox=False), sets())[0] == "")
    check("другой силуэт - не вариант", v6.variant_kind(pair(iou=0.9), sets())[0] == "")
    var = [{"kind": "MATERIAL_VARIANT_OF", "level": "CANDIDATE", "relative": "T:11", "side": "derived",
            "one_way": "b->a", "why": ""}]
    check("вариант - REVIEW R4v", r("S:11", "OBJECT", meta(), variants=var)[:2] == ("REVIEW", "R4v"))
    check("контроль: без варианта одиночный", r("S:11", "OBJECT", meta())[0] == "STANDALONE_RENDER")
    check("вариант: функция в одну сторону -> DERIVED",
          r("S:11", "OBJECT", meta(), variants=var, variant_one_way_derived=True)[0] == "DERIVED")

    # post-hoc R0p: основа - набор оригинала (только в чувствительности)
    check("R0p: основа в наборе оригинала - DERIVED",
          r("S:1", "OBJECT", meta(rels={"S:1": [REC]}), origin_sets={"T"})[:2] == ("DERIVED", "R0p"))
    check("контроль R0p: оба набора не из оригинала - одиночный",
          r("S:1", "OBJECT", meta(rels={"S:1": [REC]}), origin_sets={"U"})[0] == "STANDALONE_RENDER")
    check("контроль R0p: сам кадр из оригинала - не производный",
          r("T:5", "OBJECT", meta(rels={"T:5": [dict(REC, relative="T:1")]}), origin_sets={"T"})[0] == "STANDALONE_RENDER")
    check("контроль R0p: перекраска CANDIDATE - не довод",
          r("S:1", "OBJECT", meta(rels={"S:1": [cand]}), origin_sets={"T"})[0] == "STANDALONE_RENDER")

    # V6_PREP_R2: три изменения
    R2 = dict(v6.R2_OPTS, origin_sets={"T"})
    WEAK = ("CANDIDATE", "блок на всю клетку, закрывает обзор (Big_Wall 1, Stop_LOS)")
    check("R2: OBJECT_PART + слабая улика стены - не поверхность, REVIEW R8a",
          r("S:3", "OBJECT_PART", meta(), surf=WEAK, **R2)[:2] == ("REVIEW", "R8a"))
    check("контроль R2: та же слабая улика в V6-prep - EXCLUDE S",
          r("S:3", "OBJECT_PART", meta(), surf=WEAK)[:2] == ("EXCLUDE", "S"))
    check("R2: OBJECT_PART + сильная улика - EXCLUDE S",
          r("S:3", "OBJECT_PART", meta(), surf=WALL, **R2)[:2] == ("EXCLUDE", "S"))
    check("R2: OBJECT_PART + слабая улика + модуль по метаданным - R6",
          r("S:3", "OBJECT_PART", meta(modular={"S:3"}), surf=WEAK, **R2)[1] == "R6")
    check("R2: NOT_OBJECT + слабая улика - EXCLUDE R2 по оси A",
          r("S:3", "NOT_OBJECT", meta(), surf=WEAK, **R2)[:2] == ("EXCLUDE", "R2"))
    check("R2: OBJECT + слабая улика - REVIEW R7s", r("S:3", "OBJECT", meta(), surf=WEAK, **R2)[:2] == ("REVIEW", "R7s"))
    big2 = view(die, vols={"S:2": 300, "S:3": 300}, mode="anim_only")
    check("R2: die без проверки объёма - STATE_VARIANT R3m",
          r("S:2", "OBJECT", meta(), big2, **R2)[:2] == ("STATE_VARIANT", "R3m"))
    loop2 = view(die, groups={"S:2": "S:3", "S:3": "S:3"}, mode="anim_only")
    check("контроль R2: die внутри петли - REVIEW R7m", r("S:2", "OBJECT", meta(), loop2, **R2)[:2] == ("REVIEW", "R7m"))
    shared = view([link("S:2", "S:3", "die", level="CANDIDATE")], mode="anim_only")
    check("контроль R2: die CANDIDATE (общий обломок) - REVIEW R7m",
          r("S:2", "OBJECT", meta(), shared, **R2)[:2] == ("REVIEW", "R7m"))
    check("R2: R0p - только улика, REVIEW R7o", r("S:1", "OBJECT", meta(rels={"S:1": [REC]}), **R2)[:2] == ("REVIEW", "R7o"))
    tvar = [dict(var[0], relative="T:1")]
    check("R2: R0p при варианте к оригиналу - тоже не DERIVED (REVIEW R4v)",
          r("S:1", "OBJECT", meta(), variants=tvar, **R2)[:2] == ("REVIEW", "R4v"))
    check("контроль: тот же вариант в post-hoc V6-prep - DERIVED R0p",
          r("S:1", "OBJECT", meta(), variants=tvar, origin_sets={"T"})[:2] == ("DERIVED", "R0p"))
    check("контроль R2: основа не в оригинале - одиночный",
          r("S:1", "OBJECT", meta(rels={"S:1": [REC]}), **dict(R2, origin_sets={"U"}))[0] == "STANDALONE_RENDER")
    check("контроль R2: перекраска CANDIDATE к оригиналу - не улика",
          r("S:1", "OBJECT", meta(rels={"S:1": [cand]}), **R2)[0] == "STANDALONE_RENDER")
    check("R2: подтверждённая человеком основа по-прежнему DERIVED R0v",
          r("S:1", "OBJECT", meta(rels={"S:1": [dict(REC, verified=True)]}), **R2)[:2] == ("DERIVED", "R0v"))

    # +. перекраска внутри петли анимации
    rels = {"S:21": [dict(REC, relative="S:14", level="CANDIDATE"), dict(REC, relative="U:1", level="CANDIDATE")]}
    g = {"S:21": "S:14", "S:14": "S:14"}
    raw, dropped = v6.claims_v6(["S:21"], rels, {}, {}, {}, g)
    check("перекраска внутри петли снята, вне петли осталась",
          [x[1] for x in raw] == ["U:1"] and [x[1] for x in dropped] == ["S:14"])
    raw, dropped = v6.claims_v6(["S:21"], rels, {}, {}, {}, {})
    check("контроль: без петли обе остаются", len(raw) == 2 and not dropped)
    raw, _ = v6.claims_v6(["S:1"], {"S:1": [NB]}, {}, {}, {}, {})
    check("FIXED_NEIGHBOUR не входит в точность родства", raw == [])
    sc = v6.score([("S:21", "S:14", "ANIMATION_FRAME_OF", "STRONG", "derived", "mcd_anim")],
                  [{"asset_id": "S:21", "relative": "S:14", "ref_pair_relation": "ANIMATION_FRAME_OF"}])
    check("анимация против эталона ANIMATION_FRAME_OF - ok", sc[0]["status"] == "ok")
    sc = v6.score([("S:21", "S:14", "RECOLOR_OF", "STRONG", "base", "detector")],
                  [{"asset_id": "S:21", "relative": "S:14", "ref_pair_relation": "ANIMATION_FRAME_OF"}])
    check("контроль: перекраска против ANIMATION_FRAME_OF - wrong", sc[0]["status"] == "wrong")
    print("\nпровалов: %d" % len(FAILS))
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
