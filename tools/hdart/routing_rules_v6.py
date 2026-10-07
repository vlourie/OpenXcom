#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""ROUTING_RULES_V6_PREP - правила маршрута V6 и диагностический пересчёт на тех же 50 (специалист 02.10). CPU.

Слепой holdout V5 - FAIL (routing-holdout-v5/report.md, diag.md), итог стоит и не пересчитывается; замороженные
файлы V5 (FREEZE 619a119e54ca и код из него) не меняются - V6 отдельный модуль, папка holdout только читается.
Четыре решения специалиста и одно дополнение:

1. Доказанная перекраска без известной основы - не DERIVED. RECOLOR_OF - симметричное отношение (детектор,
   прямые рёбра FAMILY_RELATION_V2, recolor семейства, RECOLOR_WITH_LOCAL_EDIT): маршрут не меняет. Производным
   кадр делает только независимое доказательство канонической основы - сейчас это только подтверждение человеком
   (R0v: verified у родства детектора). Основа по числу мест на картах или по канону семьи маршрут не меняет.
   FAMILY_RELATION_V2 остаётся, смысл другой: verified direct relation != verified derivation; base и
   direction_source в нём - подсказка, не доказательство направления.
2. MCD alt - только улика: в точность родства не входит, маршрута не даёт; одиночный заказ при ней уходит в
   REVIEW (как FIXED_NEIGHBOUR). Анимация STRONG -> ANIMATION_FAMILY, как в V5 (16/16). die STRONG маршрутизирует
   только с подтверждающим сигналом (ниже), без него - REVIEW.
3. Структурная роль раньше родства: STRUCTURAL_SURFACE, COMPOSITE_PART, STRUCTURAL_MODULAR, ограничения
   OBJECT_PART - и только потом семейство, зеркало, перекраска, состояния.
4. Снег, грязь, ржавчина - не перекраска: MATERIAL_VARIANT_OF / STYLE_VARIANT_OF. Силуэт тот же, материал
   добавлен, поэтому функция цвета один к одному закономерно ломается.
+. Пара внутри одной доказанной петли анимации MCD (SGR_COM:21 ~ SGR_COM:14) - не перекраска: утверждение
   перекраски детектора по ней снимается. Мигание ламп ложных перекрасок не даёт.

Объявлено ДО пересчёта (выбор агента, не специалиста; на пересчёте не подбиралось, варианты - в чувствительности):

    подтверждение die      (а) кадр-состояние и его основа не в одной петле анимации MCD - петля это фазы, а не
                           разрушенный вид; (б) у состояния воксельный объём LOFT меньше, чем у основы, - обломок
                           ниже и меньше целой вещи. Нужны оба; не прошло - REVIEW (R7m).
    MATERIAL_VARIANT_OF    кадр X и кадр того же номера в наборе-двойнике T: силуэт >= GEO (0.98), воксели те же,
                           набор T повторяет силуэты набора X на >= SET_SHARE (0.80) общих кадров, но набор не
                           строгая перекраска (share_strict < SET_SHARE) и пара не строгая перекраска (функция цвета
                           в обе стороны >= FUNC - это RECOLOR_OF детектора). Физика MCD отличается
                           (горючесть, звук шага, броня) - MATERIAL_VARIANT_OF, та же - STYLE_VARIANT_OF.
                           Частичная функция без набора-двойника - не довод (R-166).
    маршрут варианта       REVIEW: основа не доказана (решение 1). Функция цвета в одну сторону (снег - функция
                           леса, обратно нет) - подсказка направления, не доказательство; вариант «одностороння
                           функция -> DERIVED» - в чувствительности.
    непроверенная перекраска  CANDIDATE детектора маршрута не меняет (симметрична, как и STRONG); вариант V5 «R7r
                           -> REVIEW» - в чувствительности.
    порядок блока структуры   S, R5, R6 - как перечислил специалист; вариант «R5/R6 раньше S» - в чувствительности.
    пара без основы        одиночный заказ при доказанной симметричной перекраске помечается pair_pick: из пары
                           рисуется один кадр, второй выводится - кто основа, решает человек (R-136).

Правила V6 по порядку (первое сработавшее решает):
    R1   A = TERRAIN_RELIEF                                       EXCLUDE
    R2   A = NOT_OBJECT без улики поверхности                     EXCLUDE
    -- структура --
    S    вид V6 STRUCTURAL_SURFACE (OBJECT_PART/NOT_OBJECT + улика MCD)   EXCLUDE (конвейер поверхностей)
    R5   составной заказ / part_fragment                          COMPOSITE_PART
    R6   modular_objects / structural_modular                     STRUCTURAL_MODULAR
    R7s  A = OBJECT при улике поверхности                         REVIEW
    R8a  A = OBJECT_PART                                          REVIEW
    R7p  part_fragment_suspect                                    REVIEW
    -- родство --
    R0v  родство с основой, подтверждённой человеком              по родству
    R3a  кадр петли анимации MCD, STRONG                          ANIMATION_FAMILY
    R3m  die MCD STRONG с подтверждением                          STATE_VARIANT (из основы)
    R3   state_variants.json / class_decisions state_variant      STATE_VARIANT
    R4   зеркало семейства                                        DERIVED
    R4v  MATERIAL_VARIANT_OF / STYLE_VARIANT_OF                   REVIEW
    R7   открытый вопрос (family_review, in_review, class_check, alternate_view)   REVIEW
    R7m  MCD CANDIDATE или die без подтверждения                  REVIEW
    R7a  MCD alt - улика                                          REVIEW
    R7n  FIXED_NEIGHBOUR - улика                                  REVIEW
    R8   A = OBJECT                                               STANDALONE_RENDER (+ pair_pick)
    R9   иначе                                                    REVIEW

Пересчёт на 50 - диагностика, не PASS: правила V6 написаны после того, как ответы и эталон этих 50 были видны.
Цели для заморозки V6 (специалист): опасных 0, точность маршрута >= 0.90, точность родства >= 0.95, охват >= 0.70.

V6_PREP_R2 (специалист 02.10, после пересчёта V6-prep; ровно три изменения, профиль R2_OPTS):

1. Структурная улика по уровням. STRONG (surface_evidence V5: запись стены Tile_Type 1/2, Big_Wall 2/3 или 4-9
   со Stop_LOS, дверь, пол floor_like) может переопределить ось A: OBJECT_PART / NOT_OBJECT -> STRUCTURAL_SURFACE.
   WEAK (одна стеноподобная отметка: Big_Wall 1 + Stop_LOS) ось A не переопределяет и маршрута не даёт:
   OBJECT_PART идёт как OBJECT_PART (R5/R6 по метаданным, иначе REVIEW R8a), NOT_OBJECT - как NOT_OBJECT (R2),
   OBJECT - REVIEW R7s, как и прежде. Модуль по внешнему виду не угадывается: без метаданных - не R6.
2. die: проверка объёма снята. Подтверждение - связь STRONG mcd_state (Die_MCD одной-двух основ, не общий
   обломок, состояние на картах не чаще основы) и не одна петля анимации; иначе REVIEW R7m.
3. R0p - только улика: перекраска STRONG или MATERIAL/STYLE_VARIANT к кадру набора из оригинальных данных игры,
   а набора кадра там нет, -> REVIEW R7o с подсказкой основы. Сам по себе DERIVED не даёт никогда.

    py -3.13 tools/hdart/routing_rules_v6.py recount            -> routing-rules-v6-prep/recount.md / .json
    py -3.13 tools/hdart/routing_rules_v6.py recount --r2       -> routing-rules-v6-prep-r2/recount.md / .json
"""
import argparse
import os
import sys
import time
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import identity_routing as ir          # noqa: E402
import mcd_state as ms                 # noqa: E402
import routing_holdout as rh           # noqa: E402
import routing_rules as rr             # noqa: E402

ROOT = ir.ROOT
OUT = os.path.join(ir.PROBES, "routing-rules-v6-prep")
HOLDOUT = os.path.join(ir.PROBES, "routing-holdout-v5")
TARGETS = {"dangerous_false_standalone_max": 0, "routing_accuracy_min": 0.90, "relation_precision_min": 0.95,
           "routing_coverage_min": 0.70}
CODE = ("tools/hdart/routing_rules_v6.py",)
GEO, FUNC, SET_SHARE = 0.98, 0.98, 0.80          # пороги relation_probe (V1), здесь не меняются
MIN_SET_FRAMES = 5                               # набор-двойник меньше этого - не довод
MATERIAL_PHYS = ("armor", "flammable", "footstep", "fuel", "he_block")   # obj_struct.PHYS: свойства материала
EVIDENCE_ONLY = ("FIXED_NEIGHBOUR",)
RECOLOR = ("RECOLOR_OF", "RECOLOR_WITH_LOCAL_EDIT")
VARIANT = ("MATERIAL_VARIANT_OF", "STYLE_VARIANT_OF")
CLAIM_GROUP = {"RECOLOR_OF": "derived", "RECOLOR_WITH_LOCAL_EDIT": "derived", "STATE_VARIANT_OF": "derived",
               "ANIMATION_FRAME_OF": "animation", "MATERIAL_VARIANT_OF": "derived", "STYLE_VARIANT_OF": "derived"}
CLAIM_EXACT = {"RECOLOR_OF": ("RECOLOR_OF",), "RECOLOR_WITH_LOCAL_EDIT": ("DERIVED_FROM",),
               "STATE_VARIANT_OF": ("STATE_VARIANT_OF",), "ANIMATION_FRAME_OF": ("ANIMATION_FRAME_OF",),
               "MATERIAL_VARIANT_OF": ("DERIVED_FROM",), "STYLE_VARIANT_OF": ("DERIVED_FROM",)}
REF_GROUP = {"RECOLOR_OF": "derived", "DERIVED_FROM": "derived", "STATE_VARIANT_OF": "derived",
             "STRUCTURAL_RELATION": "structure", "ANIMATION_FRAME_OF": "animation"}
DANGEROUS = tuple(ir.DANGEROUS_REF) + ("ANIMATION_FAMILY",)
OPEN_V6 = ("family_review", "in_review", "class_check")       # part_fragment_suspect - в блоке структуры (R7p)
# варианты, объявленные до пересчёта (чувствительность, не итог)
DEFAULT_OPTS = {"die": "corroborated", "mirror_routes": True, "recolor_candidate_review": False,
                "alt_review": True, "variant_one_way_derived": False, "modular_before_surface": False,
                "origin_sets": None, "surface_override": "any", "object_strong_surface": False,
                "origin_mode": "derived"}
# V6_PREP_R2: три изменения специалиста; origin_sets подставляет recount (наборы оригинала)
R2_OPTS = dict(DEFAULT_OPTS, die="anim_only", surface_override="strong", origin_mode="evidence")
OUT_R2 = os.path.join(ir.PROBES, "routing-rules-v6-prep-r2")
# найдено ПОСЛЕ пересчёта (post-hoc, не правило V6, решает специалист): основа - кадр набора, который есть в
# оригинальных данных игры (UFO/TERRAIN, standard/xcom1/TERRAIN), а набора кадра там нет. Это происхождение
# файла, а не число мест и не канон семьи. Включается только в чувствительности (origin_sets)
ORIGIN_DIRS = (os.path.join("UFO", "TERRAIN"), os.path.join("standard", "xcom1", "TERRAIN"))


# ---------------------------------------------------------------- MCD: петли и подтверждение die

def anim_groups(by_set):
    """Ключ кадра -> ключ основы его петли анимации (основа - сама себе). Только связи anim из mcd_state."""
    g = {}
    for links in by_set.values():
        for x in links:
            if x["via"] == "anim":
                g[x["state"]] = x["base"]
                g.setdefault(x["base"], x["base"])
    return g


def same_anim(groups, a, b):
    ga, gb = groups.get(a.upper()), groups.get(b.upper())
    return ga is not None and ga == gb


def volume(info):
    v = info.get("vox") if info else None
    if v is None:
        return None
    import numpy as np
    return int(np.asarray(v).sum())


def die_check(x, groups, vol, use_volume=True):
    """(подтверждено, почему) для связи die STRONG: не одна петля анимации и (V6-prep) объём состояния меньше
    основы. vol - функция ключ -> воксельный объём или None; use_volume=False - R2, только петля."""
    if same_anim(groups, x["state"], x["base"]) or same_anim(groups, x["state"], x["root"]):
        return False, "die внутри одной петли анимации - фазы, не разрушенный вид"
    if not use_volume:
        return True, "STRONG, не одна петля анимации"
    vs, vb = vol(x["state"]), vol(x["base"])
    if vs is None or vb is None:
        return False, "объём LOFT не прочитан"
    if vs >= vb:
        return False, "объём состояния %d не меньше основы %d" % (vs, vb)
    return True, "объём состояния %d < основы %d" % (vs, vb)


# ---------------------------------------------------------------- MATERIAL_VARIANT_OF / STYLE_VARIANT_OF

def variant_kind(p, s):
    """(вид, почему) по паре relation_probe.pair и набору relation_probe.sets; вид '' - не вариант."""
    if "error" in p or s is None:
        return "", "нет данных"
    g, pal, mcd = p["1_geometry"], p["4_palette"], p["5_mcd"]
    if g["iou"] < GEO:
        return "", "силуэт %.3f" % g["iou"]
    if pal["f_ab"] >= FUNC and pal["f_ba"] >= FUNC:
        return "", "строгая перекраска - это RECOLOR_OF"
    if s["compared"] < MIN_SET_FRAMES or s["share_same_geometry"] < SET_SHARE:
        return "", "набор-двойника нет (силуэты %.3f из %d)" % (s["share_same_geometry"], s["compared"])
    if s["share_strict"] >= SET_SHARE:
        return "", "набор - строгая перекраска (это RECOLOR_WITH_LOCAL_EDIT детектора)"
    if mcd["vox_same"] is not True:
        return "", "воксели другие"
    mat = [k for k in mcd["phys_diff"] if k in MATERIAL_PHYS]
    one_way = ("a->b" if pal["f_ab"] >= FUNC > pal["f_ba"] else "b->a" if pal["f_ba"] >= FUNC > pal["f_ab"] else "")
    why = "силуэт %.3f, воксели те же, набор повторяет силуэты %.3f (строгих %.3f), цвет %.3f/%.3f%s" % (
        g["iou"], s["share_same_geometry"], s["share_strict"], pal["f_ab"], pal["f_ba"],
        ", физика: %s" % ",".join(mcd["phys_diff"]) if mcd["phys_diff"] else "")
    return ("MATERIAL_VARIANT_OF" if mat else "STYLE_VARIANT_OF"), why + (
        "; функция в одну сторону %s" % one_way if one_way else ""), one_way


def all_sets(world):
    return sorted({s.upper() for t in world.terrains for s in world.sets_of(t)})


def find_variants(ctx, key, set_list, cache):
    """Варианты кадра key в наборах того же номера: [{kind, level, relative, side, one_way, why}]."""
    import numpy as np
    import relation_probe as rp
    s0, f0 = key.split(":")
    f0 = int(f0)
    A = ctx.rgba(key)
    if A is None:
        return []
    ma = A[..., 3] > 0
    if not ma.any():
        return []
    out = []
    for t in set_list:
        if t == s0.upper() or ctx.count(t) <= f0:
            continue
        B = ctx.rgba("%s:%d" % (t, f0))
        if B is None:
            continue
        mb = B[..., 3] > 0
        u = (ma | mb).sum()
        if not u or (ma & mb).sum() / u < GEO:
            continue
        ck = (s0.upper(), t)
        if ck not in cache:
            cache[ck] = rp.sets(ctx, s0, t)
        p = rp.pair(ctx, key, "%s:%d" % (t, f0))
        kind, why, *rest = variant_kind(p, cache[ck])
        if kind:
            ow = rest[0] if rest else ""
            # a = key, b = родственник: функция a->b - родственник выводится из кадра (подсказка, не доказательство)
            side = "base" if ow == "a->b" else "derived" if ow == "b->a" else "open"
            out.append({"kind": kind, "level": "CANDIDATE", "relative": "%s:%d" % (t, f0), "side": side,
                        "one_way": ow, "why": why})
    return out


# ---------------------------------------------------------------- улики и маршрут

def mcd_view(links, groups, vol, die_mode="corroborated"):
    """Связи кадра по MCD с решением V6: [dict(связь, v6=...)]: anim | die_ok | die_weak | alt | candidate."""
    out = []
    for x in links:
        y = dict(x)
        if x["level"] != "STRONG":
            y["v6"], y["v6_why"] = "candidate", x["why"]
        elif x["via"] == "anim":
            y["v6"], y["v6_why"] = "anim", ""
        elif x["via"] == "alt":
            y["v6"], y["v6_why"] = "alt", "alt - улика (0/3 на holdout V5)"
        elif die_mode == "as_v5":
            y["v6"], y["v6_why"] = "die_ok", "die как в V5"
        else:
            ok, why = die_check(x, groups, vol, use_volume=die_mode != "anim_only")
            y["v6"], y["v6_why"] = ("die_ok" if ok else "die_weak"), why
        out.append(y)
    return out


def semantic_v6(sk, surf_level, override="any", object_strong=False):
    """Вид V6. override 'any' (V6-prep): любая улика поверхности переопределяет OBJECT_PART/NOT_OBJECT;
    'strong' (R2): только STRONG, WEAK (CANDIDATE surface_evidence) ось A не трогает. object_strong - вариант
    чувствительности R2: STRONG переопределяет и OBJECT."""
    if not surf_level or (override == "strong" and surf_level != "STRONG"):
        return sk
    if sk in ("OBJECT_PART", "NOT_OBJECT") or (object_strong and sk == "OBJECT"):
        return "STRUCTURAL_SURFACE"
    return sk


def route_v6(a, sk, meta, mlinks, surf, variants, unit_map=None, opts=None):
    """(маршрут, правило, улика, вид V6, pair_pick). mlinks - mcd_view кадра; surf - (уровень, почему) улики
    поверхности (routing_rules_v5.surface_evidence); variants - find_variants кадра."""
    o = dict(DEFAULT_OPTS, **(opts or {}))
    unit_map = unit_map or rr.RELATION_UNIT_HOLDOUT
    gen, fam_rel, fam_review, state, modular, cls, rels = meta
    lvl, swhy = surf
    kind = semantic_v6(sk, lvl, o["surface_override"], o["object_strong_surface"])
    weak = " (слабая улика стены: %s - ось A не переопределяет)" % swhy if lvl and kind == sk and \
        o["surface_override"] == "strong" and lvl != "STRONG" else ""
    g = gen.get(a, {})
    blockers = [b.split(":")[0] for b in (g.get("blockers") or "").split()]
    rel = g.get("relation", "")
    fr = fam_rel.get(a, "canonical")
    rs = (rels or {}).get(a, [])
    rec = [r for r in rs if r["kind"] in RECOLOR]
    pick = bool([r for r in rec if r["level"] == "STRONG"])

    def ret(u, rule, why):
        return u, rule, why, kind, pick and u == "STANDALONE_RENDER"

    if sk == "TERRAIN_RELIEF":
        return ret("EXCLUDE", "R1", "A " + sk)
    if sk == "NOT_OBJECT" and kind == "NOT_OBJECT":
        return ret("EXCLUDE", "R2", "A " + sk + weak)
    # -- структура (решение 3)
    composite = g.get("kind") == "составной" or cls.get(a) == "part_fragment"
    mod = a in modular or cls.get(a) == "structural_modular"
    struct = [("S", kind == "STRUCTURAL_SURFACE", "EXCLUDE", "поверхность: %s" % swhy),
              ("R5", composite, "COMPOSITE_PART", "kind %s, class %s" % (g.get("kind", "-"), cls.get(a, "-"))),
              ("R6", mod, "STRUCTURAL_MODULAR", "modular_objects / class_decisions")]
    if o["modular_before_surface"]:
        struct = struct[1:] + struct[:1]
    for rule, hit, u, why in struct:
        if hit:
            return ret(u, rule, why)
    if sk == "OBJECT" and lvl:
        return ret("REVIEW", "R7s", "вещь или поверхность? %s" % swhy)
    if sk == "OBJECT_PART":
        return ret("REVIEW", "R8a", "OBJECT_PART, подтверждённой одиночности нет" + weak)
    if "part_fragment_suspect" in blockers:
        return ret("REVIEW", "R7p", "part_fragment_suspect")
    # -- родство
    ver = [r for r in rs if r.get("verified") and r["kind"] in unit_map and r["side"] == "derived"]
    if ver:
        return ret(unit_map[ver[0]["kind"]], "R0v", "%s %s (основа подтверждена человеком)" % (
            ver[0]["kind"], ver[0]["relative"]))
    orig, src = o["origin_sets"], []
    if orig is not None and a.split(":")[0].upper() not in orig:
        proven = [r for r in rec if r["level"] == "STRONG"] + list(variants)
        src = [r for r in proven if r["relative"].split(":")[0].upper() in orig]
        if src and o["origin_mode"] == "derived":
            return ret("DERIVED", "R0p", "%s %s: основа в оригинальных данных игры (post-hoc)" % (
                src[0]["kind"], src[0]["relative"]))
    der = [x for x in mlinks if x["side"] == "derived"]
    anim = [x for x in der if x["v6"] == "anim"]
    if anim:
        x = anim[0]
        return ret("ANIMATION_FAMILY", "R3a", "MCD anim %s, основа %s" % (x["base"], x["root"]))
    die = [x for x in der if x["v6"] == "die_ok"]
    if die:
        x = die[0]
        return ret("STATE_VARIANT", "R3m", "MCD die %s, основа %s (%s)" % (x["base"], x["root"], x["v6_why"]))
    if a in state or cls.get(a) == "state_variant":
        return ret("STATE_VARIANT", "R3", "state_variants / class_decisions")
    if o["mirror_routes"] and (rel == "mirror" or fr == "mirror"):
        return ret("DERIVED", "R4", "зеркало семейства")
    if variants:
        v = variants[0]
        if o["variant_one_way_derived"] and v["side"] == "derived":
            return ret("DERIVED", "R4v", "%s %s, функция в одну сторону" % (v["kind"], v["relative"]))
        return ret("REVIEW", "R4v", "%s %s - основа не доказана" % (v["kind"], v["relative"]))
    if src and o["origin_mode"] == "evidence":
        return ret("REVIEW", "R7o", "улика основы: %s %s - набор из оригинальных данных игры, DERIVED не даёт" % (
            src[0]["kind"], src[0]["relative"]))
    opened = [b for b in blockers if b in OPEN_V6]
    if a in fam_review:
        opened.append("review семейства")
    if rel == "alternate_view" or fr == "alternate_view":
        opened.append("alternate_view")
    if opened:
        return ret("REVIEW", "R7", " ".join(opened))
    if o["recolor_candidate_review"]:
        cand = [r for r in rec if r["level"] != "STRONG"]
        if cand:
            return ret("REVIEW", "R7r", "; ".join("%s %s" % (r["kind"], r["relative"]) for r in cand))
    weak = [x for x in der if x["v6"] in ("candidate", "die_weak")]
    if weak:
        return ret("REVIEW", "R7m", "; ".join("MCD %s %s: %s" % (x["via"], x["base"], x["v6_why"]) for x in weak))
    alt = [x for x in mlinks if x["v6"] == "alt"]
    if alt and o["alt_review"]:
        return ret("REVIEW", "R7a", "улика: " + "; ".join("MCD alt %s" % x["relative"] for x in alt))
    nb = [r for r in rs if r["kind"] in EVIDENCE_ONLY]
    if nb:
        return ret("REVIEW", "R7n", "улика: " + "; ".join("%s %s" % (r["kind"], r["relative"]) for r in nb))
    if sk == "OBJECT":
        return ret("STANDALONE_RENDER", "R8", "нет структурной роли и доказанной основы")
    return ret("REVIEW", "R9", "A " + (sk or "-"))


# ---------------------------------------------------------------- утверждения родства

def claims_v6(keys, rels, mlinks, fr2, variants, groups):
    """Утверждения V6 и снятые: [(ключ, родственник, вид, уровень, сторона, источник)], [снятые с причиной]."""
    raw, dropped, seen = [], [], set()

    def add(k, rel_to, kind, level, side, src):
        sk = (k.upper(), rel_to.upper(), CLAIM_GROUP[kind])
        if sk in seen:
            return
        seen.add(sk)
        raw.append((k, rel_to, kind, level, side, src))

    for k in keys:
        for c in rels.get(k, []):
            if c["kind"] in EVIDENCE_ONLY:
                continue
            if c["kind"] in RECOLOR and same_anim(groups, k, c["relative"]):
                dropped.append([k, c["relative"], c["kind"], "одна петля анимации MCD"])
                continue
            add(k, c["relative"], c["kind"], c["level"], c["side"], "detector")
        for x in mlinks.get(k, []):
            if x["v6"] == "anim":
                add(k, x["relative"], x["kind"], "STRONG", x["side"], "mcd_anim")
            elif x["v6"] == "die_ok":
                add(k, x["relative"], x["kind"], "STRONG", x["side"], "mcd_die")
            elif x["level"] == "STRONG":
                dropped.append([k, x["relative"], "mcd_" + x["via"], x["v6_why"]])
        for e in fr2.get(k.upper(), []):
            if e["status"] not in ("VERIFIED_DIRECT", "DIRECT_NEW"):
                continue
            if same_anim(groups, k, e["relative"]):
                dropped.append([k, e["relative"], "fr2 " + e["relation"], "одна петля анимации MCD"])
                continue
            add(k, e["relative"], e["relation"], e["confidence"], e["side"], "fr2_" + e["status"])
        for v in variants.get(k, []):
            add(k, v["relative"], v["kind"], v["level"], v["side"], "variant")
    return raw, dropped


def score(raw, refp):
    ref = {(r["asset_id"].upper(), r["relative"].upper()): r for r in refp}
    out = []
    for k, rel_to, kind, level, side, src in raw:
        r = ref.get((k.upper(), rel_to.upper()))
        rel = (r or {}).get("ref_pair_relation") or "OPEN"
        st = "open" if rel == "OPEN" else ("ok" if REF_GROUP.get(rel) == CLAIM_GROUP[kind] else "wrong")
        out.append({"asset_id": k, "relative": rel_to, "kind": kind, "level": level, "side": side, "source": src,
                    "ref": rel, "direction": (r or {}).get("direction") or "open", "status": st,
                    "exact": rel in CLAIM_EXACT[kind], "judged": r is not None})
    return out


def precision(claims):
    closed = [c for c in claims if c["status"] != "open"]
    ok = sum(c["status"] == "ok" for c in closed)
    return {"claims": len(claims), "closed": len(closed), "ok": ok, "wrong": len(closed) - ok,
            "open": len(claims) - len(closed), "unjudged": sum(not c["judged"] for c in claims),
            "relation_precision": rh.rate(ok, len(closed))}


def metrics(rows):
    m = rh.routing_metrics(rows)
    m["dangerous_false_standalone"] = sum(r["rule_unit"] == "STANDALONE_RENDER" and r["ref_route"] in DANGEROUS
                                          for r in rows)
    return m


def targets(tot, prec):
    t = TARGETS

    def ge(v, lim):
        return None if v is None else v >= lim
    return {"опасных = 0": tot["dangerous_false_standalone"] <= t["dangerous_false_standalone_max"],
            "точность маршрута >= 0.90": ge(tot["routing_accuracy"], t["routing_accuracy_min"]),
            "точность родства >= 0.95": ge(prec["relation_precision"], t["relation_precision_min"]),
            "охват >= 0.70": ge(tot["routing_coverage"], t["routing_coverage_min"])}


# ---------------------------------------------------------------- пересчёт

def recount(out=OUT, hold=HOLDOUT, profile="prep"):
    import family_relation_v2 as fr2m
    import map_mockup as mm
    import obj_struct as os_
    import relation_probe as rp
    import routing_holdout_v5 as h5
    import routing_rules_v5 as v5
    before = v5.dir_sha(hold)
    d, h = h5.load_freeze(hold), h5.load_holdout(hold)
    v5_code_changed = h5.code_changed(d)
    h5.live_same(d)
    ref, refp, lk = h5.load_reference(hold)
    rels = h5.load_relations(hold)
    ans = {r["asset_id"]: r for r in ir.read_tsv(os.path.join(hold, "answers_vitali.tsv"))}
    v5rep = ir.load_json(os.path.join(hold, "report.json"))
    v5row = {r["asset_id"]: r for r in v5rep["rows"]}
    keys = [x["asset_id"] for x in h["items"]]
    layer = {x["asset_id"]: x for x in h["items"]}
    inp = dict(d["inputs"])
    inp["relations"] = rh.load_json_path(hold)
    meta = rr.metadata(inp)
    umap = d["routing"]["relation_unit"]
    fr2 = fr2m.load(inp["family_relation_v2"])
    ctx = rp.Ctx()
    st = os_.Struct(ctx.world)
    sets = {k.split(":")[0] for k in keys} | {c["relative"].split(":")[0] for k in keys for c in rels.get(k, [])}
    by_set = ms.build(sets, ctx.world, cells=ms.placements(inp["census_frames"]))
    idx = ms.index(by_set)
    groups = anim_groups(by_set)

    def vol(k):
        s, f = k.split(":")
        try:
            return volume(st.info(s, int(f)))
        except (Exception, SystemExit):     # noqa: BLE001
            return None

    surf = {a: v5.surface_evidence(st, a) for a in keys}
    t0 = time.time()
    set_list, cache = all_sets(ctx.world), {}
    variants = {a: find_variants(ctx, a, set_list, cache) for a in keys}
    var_sec = round(time.time() - t0, 1)
    views = {mode: {a: mcd_view(idx.get(a.upper(), []), groups, vol, mode) for a in keys}
             for mode in ("corroborated", "as_v5", "anim_only")}
    origin = {n[:-4].upper() for dd in ORIGIN_DIRS if os.path.isdir(os.path.join(mm.INSTALL, dd))
              for n in os.listdir(os.path.join(mm.INSTALL, dd)) if n.upper().endswith(".PCK")}
    r2 = profile == "r2"
    base = dict(R2_OPTS, origin_sets=origin) if r2 else dict(DEFAULT_OPTS)

    def build(ref_axis=False, **opts):
        o = dict(base, **opts)
        mode = o["die"]
        rows = []
        for a in keys:
            sk = ans.get(a, {}).get("semantic_kind", "")
            if ref_axis and (ref.get(a, {}).get("ref_semantic_kind") or "open") != "open":
                sk = ref[a]["ref_semantic_kind"]
            u, rule, why, kind, pick = route_v6(a, sk, meta, views[mode][a], surf[a], variants[a], umap, o)
            r = ref.get(a, {})
            rows.append({"asset_id": a, "layer": layer[a]["layer"], "sub": layer[a]["sub"], "semantic_kind": sk,
                         "semantic_v6": kind, "surface": surf[a][0], "rule_unit": u, "rule": rule, "why": why,
                         "pair_pick": pick, "ref_route": r.get("ref_route") or "open",
                         "ref_semantic_kind": r.get("ref_semantic_kind") or "open",
                         "ref_relation": r.get("ref_relation") or "OPEN", "ref_relation_to": r.get("ref_relation_to", ""),
                         "v5_unit": v5row[a]["rule_unit"], "v5_rule": v5row[a]["rule"]})
        return rows

    rows = build()
    tot = metrics(rows)
    raw, dropped = claims_v6(keys, rels, views[base["die"]], fr2, variants, groups)
    claims = score(raw, refp)
    prec = precision(claims)
    raw5, _ = claims_v6(keys, rels, views["as_v5"], fr2, {}, {})
    if r2:
        return _finish_r2(out, hold, d, before, v5_code_changed, v5rep, build, rows, tot, claims, prec, dropped,
                          refp, variants, var_sec, cache, keys, rels, views, fr2, groups, origin)
    sens = {"die как в V5 (без подтверждения)": metrics(build(die="as_v5")),
            "die: только проверка петли": metrics(build(die="anim_only")),
            "зеркало тоже симметрично (R4 не маршрутизирует)": metrics(build(mirror_routes=False)),
            "перекраска CANDIDATE -> REVIEW (R7r V5)": metrics(build(recolor_candidate_review=True)),
            "alt не даёт и REVIEW": metrics(build(alt_review=False)),
            "вариант с функцией в одну сторону -> DERIVED": metrics(build(variant_one_way_derived=True)),
            "R5/R6 раньше S": metrics(build(modular_before_surface=True))}
    sens_prec = {"без снятия пар петли и без подтверждения die (как V5, без вариантов)": precision(score(raw5, refp)),
                 "без MATERIAL/STYLE_VARIANT": precision([c for c in claims if c["source"] != "variant"])}
    for mode, name in (("as_v5", "die как в V5"), ("anim_only", "die: только проверка петли")):
        rm, _ = claims_v6(keys, rels, views[mode], fr2, variants, groups)
        sens_prec[name] = precision(score(rm, refp))
    # post-hoc: найдено после пересчёта, не правило V6 - решает специалист
    phase = [c for c in claims if c["kind"] in RECOLOR and c["asset_id"].upper() in groups
             and c["relative"].upper() in groups]
    posthoc = {"origin_sets": sorted(origin),
               "routing": {"ось A из эталона (сколько ошибок - от оси A, а не от правил)": metrics(build(ref_axis=True)),
                           "основа - набор из оригинальных данных игры (R0p)": metrics(build(origin_sets=origin)),
                           "R0p + ось A из эталона": metrics(build(ref_axis=True, origin_sets=origin)),
                           "R0p + перекраска CANDIDATE -> REVIEW": metrics(build(origin_sets=origin,
                                                                                 recolor_candidate_review=True))},
               "r0p_rows": [[r["asset_id"], r["rule_unit"], r["ref_route"], r["why"]]
                            for r in build(origin_sets=origin) if r["rule"] == "R0p"],
               "ref_axis_rows": [[r["asset_id"], r["semantic_kind"], r["rule_unit"], r["rule"], r["ref_route"]]
                                 for r in build(ref_axis=True) if r["ref_route"] != "open" and
                                 r["rule_unit"] not in ("REVIEW", r["ref_route"])],
               "phase_pairs": [[c["asset_id"], c["relative"], c["ref"], c["status"]] for c in phase],
               "precision_without_phase_pairs": precision([c for c in claims if c not in phase])}
    mc = [c for c in claims if c["source"].startswith("mcd_")]
    after = v5.dir_sha(hold)
    changed = [[r["asset_id"], r["v5_unit"], r["v5_rule"], r["rule_unit"], r["rule"], r["ref_route"], r["why"]]
               for r in rows if (r["v5_unit"], r["v5_rule"]) != (r["rule_unit"], r["rule"])]
    res = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "diagnostic_only": True,
           "not_blind": "правила V6 написаны после ответов и эталона этих 50 - PASS не заявляется, V6 не заморожен",
           "holdout": hold.replace(os.sep, "/"), "holdout_freeze_sha256": d["sha256"],
           "holdout_untouched": before == after, "holdout_files": len(before),
           "v5_code_changed": v5_code_changed, "code_sha256": {c: rh.file_sha(c) for c in CODE},
           "declared_before_recount": {"die_corroboration": "не одна петля анимации И объём LOFT состояния меньше основы",
                                       "variant_route": "REVIEW", "recolor_candidate": "маршрут не меняет",
                                       "struct_order": "S, R5, R6"},
           "targets": targets(tot, prec), "total": tot, "v5_total": v5rep["total"],
           "v5_relations": v5rep["relations"], "relations": prec,
           "by_source": {s: precision([c for c in claims if c["source"] == s]) for s in sorted({c["source"] for c in claims})},
           "mcd_claims": {"anim": precision([c for c in mc if c["source"] == "mcd_anim"]),
                          "die": precision([c for c in mc if c["source"] == "mcd_die"])},
           "dropped": dropped, "dropped_scored": score([(x[0], x[1], "RECOLOR_OF" if "RECOLOR" in x[2] else
                                                         "STATE_VARIANT_OF", "-", "-", x[2]) for x in dropped], refp),
           "variants": {k: v for k, v in variants.items() if v}, "variant_scan_sec": var_sec,
           "variant_sets_compared": len(cache), "sensitivity": sens, "sensitivity_precision": sens_prec, "posthoc": posthoc,
           "semantic_note": "ось A - ответы специалиста V5, не менялись", "rules_fired": dict(Counter(r["rule"] for r in rows)),
           "outcomes": dict(Counter(outcome(r) for r in rows)), "changed_vs_v5": changed,
           "pair_pick": [r["asset_id"] for r in rows if r["pair_pick"]], "claims": claims, "rows": rows}
    os.makedirs(out, exist_ok=True)
    ir.dump_json(os.path.join(out, "recount.json"), res)
    write_md(out, res)
    if not res["holdout_untouched"]:
        raise SystemExit("папка holdout изменилась во время пересчёта - так быть не должно")
    return res


def _finish_r2(out, hold, d, before, v5_code_changed, v5rep, build, rows, tot, claims, prec, dropped, refp,
               variants, var_sec, cache, keys, rels, views, fr2, groups, origin):
    """Итог V6_PREP_R2: сравнение с V5 и V6-prep, чувствительность к трём изменениям."""
    import routing_rules_v5 as v5
    prep = ir.load_json(os.path.join(OUT, "recount.json"))
    prow = {r["asset_id"]: r for r in prep["rows"]}
    sens = {"слабая улика тоже переопределяет ось A (как V6-prep)": metrics(build(surface_override="any")),
            "STRONG переопределяет и OBJECT": metrics(build(object_strong_surface=True)),
            "die с проверкой объёма (как V6-prep)": metrics(build(die="corroborated")),
            "die как в V5 (без подтверждения)": metrics(build(die="as_v5")),
            "R0p -> DERIVED (post-hoc V6-prep)": metrics(build(origin_mode="derived")),
            "без R0p вовсе": metrics(build(origin_sets=None)),
            "ось A из эталона (потолок правил)": metrics(build(ref_axis=True))}
    sens_prec = {"без MATERIAL/STYLE_VARIANT": precision([c for c in claims if c["source"] != "variant"])}
    for mode, name in (("corroborated", "die с проверкой объёма (как V6-prep)"), ("as_v5", "die как в V5")):
        rm, _ = claims_v6(keys, rels, views[mode], fr2, variants, groups)
        sens_prec[name] = precision(score(rm, refp))
    ref_axis_rows = [[r["asset_id"], r["semantic_kind"], r["rule_unit"], r["rule"], r["ref_route"]]
                     for r in build(ref_axis=True) if r["ref_route"] != "open" and
                     r["rule_unit"] not in ("REVIEW", r["ref_route"])]
    mc = [c for c in claims if c["source"].startswith("mcd_")]
    after = v5.dir_sha(hold)
    changed = [[r["asset_id"], prow[r["asset_id"]]["rule_unit"], prow[r["asset_id"]]["rule"], r["rule_unit"],
                r["rule"], r["ref_route"], r["why"]] for r in rows
               if (prow[r["asset_id"]]["rule_unit"], prow[r["asset_id"]]["rule"]) != (r["rule_unit"], r["rule"])]
    res = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "profile": "V6_PREP_R2", "diagnostic_only": True,
           "not_blind": "правила написаны после ответов и эталона этих 50 - PASS не заявляется, V6 не заморожен",
           "holdout": hold.replace(os.sep, "/"), "holdout_freeze_sha256": d["sha256"],
           "holdout_untouched": before == after, "holdout_files": len(before),
           "v5_code_changed": v5_code_changed, "code_sha256": {c: rh.file_sha(c) for c in CODE},
           "changes": {"structural": "STRONG (surface_evidence STRONG) переопределяет OBJECT_PART/NOT_OBJECT; WEAK "
                                     "(Big_Wall 1 + Stop_LOS) ось A не трогает: OBJECT_PART -> R5/R6/R8a, NOT_OBJECT -> R2, "
                                     "OBJECT -> R7s REVIEW",
                       "die": "проверка объёма снята: STRONG mcd_state и не одна петля анимации",
                       "r0p": "улика: перекраска STRONG или вариант к набору оригинала -> REVIEW R7o, DERIVED не даёт"},
           "origin_sets": sorted(origin), "targets": targets(tot, prec), "total": tot,
           "v5_total": v5rep["total"], "v5_relations": v5rep["relations"],
           "prep_total": prep["total"], "prep_relations": prep["relations"], "relations": prec,
           "by_source": {s: precision([c for c in claims if c["source"] == s]) for s in sorted({c["source"] for c in claims})},
           "mcd_claims": {"anim": precision([c for c in mc if c["source"] == "mcd_anim"]),
                          "die": precision([c for c in mc if c["source"] == "mcd_die"])},
           "dropped": dropped, "dropped_scored": score([(x[0], x[1], "RECOLOR_OF" if "RECOLOR" in x[2] else
                                                         "STATE_VARIANT_OF", "-", "-", x[2]) for x in dropped], refp),
           "variants": {k: v for k, v in variants.items() if v}, "variant_scan_sec": var_sec,
           "variant_sets_compared": len(cache), "sensitivity": sens, "sensitivity_precision": sens_prec,
           "ref_axis_rows": ref_axis_rows, "semantic_note": "ось A - ответы специалиста V5, не менялись",
           "rules_fired": dict(Counter(r["rule"] for r in rows)),
           "outcomes": dict(Counter(outcome(r) for r in rows)), "changed_vs_prep": changed,
           "pair_pick": [r["asset_id"] for r in rows if r["pair_pick"]], "claims": claims, "rows": rows}
    os.makedirs(out, exist_ok=True)
    ir.dump_json(os.path.join(out, "recount.json"), res)
    write_md_r2(out, res)
    if not res["holdout_untouched"]:
        raise SystemExit("папка holdout изменилась во время пересчёта - так быть не должно")
    return res


def write_md_r2(out, res):
    word = {True: "да", False: "**нет**", None: "нет данных"}
    t, tp, t5 = res["total"], res["prep_total"], res["v5_total"]
    pr, pp, p5 = res["relations"], res["prep_relations"], res["v5_relations"]
    tg = res["targets"]

    def acc(x):
        return "%s (%d/%d)" % (x["routing_accuracy"], x["correct"], x["decided"])

    def rp_(x):
        return "%s (%d/%d)" % (x["relation_precision"], x["ok"], x["closed"])

    L = ["# V6_PREP_R2 - диагностический пересчёт на тех же 50", "",
         "Не слепо и не PASS: правила написаны после ответов специалиста и эталона этих 50. Итог holdout V5 (FAIL) "
         "стоит; папка holdout только читалась (файлов %d, не изменились: %s); код V5 из FREEZE %s." % (
             res["holdout_files"], "да" if res["holdout_untouched"] else "**НЕТ**",
             "тот же" if not res["v5_code_changed"] else "**ИЗМЕНЁН: %s**" % ", ".join(res["v5_code_changed"])), "",
         "Три изменения специалиста против V6-prep, больше ничего:", ""]
    L += ["- %s: %s" % kv for kv in res["changes"].items()]
    L += ["", "## Цели для заморозки", "", "| показатель | V5 (слепо) | V6-prep | R2 | цель | достигнута |",
          "|---|---|---|---|---|---|",
          "| опасных одиночных | %d | %d | %d | 0 | %s |" % (t5["dangerous_false_standalone"],
                                                        tp["dangerous_false_standalone"], t["dangerous_false_standalone"],
                                                        word[tg["опасных = 0"]]),
          "| точность маршрута | %s | %s | %s | >= 0.90 | %s |" % (acc(t5), acc(tp), acc(t),
                                                                  word[tg["точность маршрута >= 0.90"]]),
          "| точность родства | %s | %s | %s | >= 0.95 | %s |" % (rp_(p5), rp_(pp), rp_(pr),
                                                                  word[tg["точность родства >= 0.95"]]),
          "| охват | %s | %s | %s (%d/%d) | >= 0.70 | %s |" % (t5["routing_coverage"], tp["routing_coverage"],
                                                              t["routing_coverage"], t["decided"], t["ref_closed"],
                                                              word[tg["охват >= 0.70"]]),
          "| сверхосторожно | %s | %s | %s (%d/%d) | - | |" % (t5["overconservative_rate"], tp["overconservative_rate"],
                                                             t["overconservative_rate"], t["overconservative"],
                                                             t["ref_standalone"]), "",
          "Исходы R2: %s. Правила: %s." % (", ".join("%s %d" % kv for kv in sorted(res["outcomes"].items())),
                                           ", ".join("%s %d" % kv for kv in sorted(res["rules_fired"].items()))), ""]
    bad = [r for r in res["rows"] if outcome(r) in ("ОПАСНО", "неверно")]
    L += ["## Ошибки маршрута", "", "| предмет | A / R2 / эталон | правило | R2 | эталон | исход | почему |",
          "|---|---|---|---|---|---|---|"]
    L += ["| %s | %s / %s / %s | %s | %s | %s | %s | %s |" % (
        r["asset_id"], r["semantic_kind"], r["semantic_v6"], r["ref_semantic_kind"], r["rule"], r["rule_unit"],
        r["ref_route"], outcome(r), r["why"]) for r in bad] or ["| нет | | | | | | |"]
    over = [r for r in res["rows"] if r["rule_unit"] == "REVIEW" and r["ref_route"] == "STANDALONE_RENDER"]
    L += ["", "Сверхосторожно (REVIEW при эталоне STANDALONE): %s." % (
        "; ".join("%s %s (%s)" % (r["asset_id"], r["rule"], r["why"]) for r in over) or "нет")]
    L += ["", "Неверные маршруты при оси A из эталона (что остаётся за правилами):", ""]
    L += ["- %s: A специалиста %s, R2 %s %s, эталон %s" % tuple(x) for x in res["ref_axis_rows"]] or ["- нет"]
    L += ["", "## Сменили маршрут против V6-prep", "", "| кадр | V6-prep | R2 | эталон | почему |", "|---|---|---|---|---|"]
    L += ["| %s | %s %s | %s %s | %s | %s |" % tuple(c) for c in res["changed_vs_prep"]] or ["| нет | | | | |"]
    L += ["", "## Родство", "", "| источник | утверждений | закрыто | верно | точность |", "|---|---|---|---|---|"]
    for s, x in res["by_source"].items():
        L.append("| %s | %d | %d | %d | %s |" % (s, x["claims"], x["closed"], x["ok"], x["relation_precision"]))
    L += ["", "MCD: анимация %s, die %s; alt - улика, в точность не входит." % (
        rp_(res["mcd_claims"]["anim"]), rp_(res["mcd_claims"]["die"])), ""]
    wrong = [c for c in res["claims"] if c["status"] == "wrong"]
    L += ["Неверные утверждения: %s." % ("; ".join("%s ~ %s %s (%s, эталон %s)" % (
        c["asset_id"], c["relative"], c["kind"], c["source"], c["ref"]) for c in wrong) or "нет"), "",
        "Снято с утверждений (%d): по эталону ok - %d, wrong - %d, open - %d." % (
            len(res["dropped"]), sum(c["status"] == "ok" for c in res["dropped_scored"]),
            sum(c["status"] == "wrong" for c in res["dropped_scored"]),
            sum(c["status"] == "open" for c in res["dropped_scored"])), ""]
    L += ["## Чувствительность (не итог)", "", "| вариант | опасных | точность | охват | сверхосторожно |",
          "|---|---|---|---|---|"]
    for k, s in res["sensitivity"].items():
        L.append("| %s | %d | %s | %s | %s |" % (k, s["dangerous_false_standalone"], acc(s), s["routing_coverage"],
                                                 s["overconservative_rate"]))
    for k, x in res["sensitivity_precision"].items():
        L.append("| родство: %s | | %s | | |" % (k, rp_(x)))
    L += ["", "Одиночный заказ при доказанной симметричной перекраске (pair_pick): %s." % (
        ", ".join(res["pair_pick"]) or "нет"), "",
          "## По предметам", "", "| предмет | A / R2 / эталон | правило | R2 | эталон | исход | почему |",
          "|---|---|---|---|---|---|---|"]
    for r in res["rows"]:
        L.append("| %s | %s / %s / %s | %s | %s | %s | %s | %s |" % (
            r["asset_id"], r["semantic_kind"], r["semantic_v6"], r["ref_semantic_kind"], r["rule"], r["rule_unit"],
            r["ref_route"], outcome(r), r["why"]))
    with open(os.path.join(out, "recount.md"), "w", encoding=ir.ENC) as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L[:40]))


def outcome(r):
    if r["ref_route"] == "open":
        return "эталон открыт"
    if r["rule_unit"] == "REVIEW":
        return "REVIEW"
    if r["rule_unit"] == "STANDALONE_RENDER" and r["ref_route"] in DANGEROUS:
        return "ОПАСНО"
    return "верно" if r["rule_unit"] == r["ref_route"] else "неверно"


def write_md(out, res):
    word = {True: "да", False: "**нет**", None: "нет данных"}
    t, t5, pr, p5 = res["total"], res["v5_total"], res["relations"], res["v5_relations"]
    L = ["# ROUTING_RULES_V6_PREP - диагностический пересчёт на тех же 50", "",
         "Не слепо и не PASS: правила V6 написаны после ответов специалиста и эталона этих 50. Итог holdout V5 (FAIL) "
         "стоит; папка holdout только читалась (файлов %d, не изменились: %s); код V5 из FREEZE %s." % (
             res["holdout_files"], "да" if res["holdout_untouched"] else "**НЕТ**",
             "тот же" if not res["v5_code_changed"] else "**ИЗМЕНЁН: %s**" % ", ".join(res["v5_code_changed"])), "",
         "Объявлено до пересчёта: подтверждение die - %s; маршрут MATERIAL/STYLE_VARIANT - %s; перекраска "
         "CANDIDATE - %s; порядок структуры - %s." % tuple(res["declared_before_recount"].values()), "",
         "## Цели для заморозки V6", "", "| показатель | V5 (слепо) | V6-prep (не слепо) | цель | достигнута |",
         "|---|---|---|---|---|",
         "| опасных одиночных | %d | %d | 0 | %s |" % (t5["dangerous_false_standalone"], t["dangerous_false_standalone"],
                                                     word[res["targets"]["опасных = 0"]]),
         "| точность маршрута | %s (%d/%d) | %s (%d/%d) | >= 0.90 | %s |" % (
             t5["routing_accuracy"], t5["correct"], t5["decided"], t["routing_accuracy"], t["correct"], t["decided"],
             word[res["targets"]["точность маршрута >= 0.90"]]),
         "| точность родства | %s (%d/%d) | %s (%d/%d) | >= 0.95 | %s |" % (
             p5["relation_precision"], p5["ok"], p5["closed"], pr["relation_precision"], pr["ok"], pr["closed"],
             word[res["targets"]["точность родства >= 0.95"]]),
         "| охват | %s (%d/%d) | %s (%d/%d) | >= 0.70 | %s |" % (
             t5["routing_coverage"], t5["decided"], t5["ref_closed"], t["routing_coverage"], t["decided"],
             t["ref_closed"], word[res["targets"]["охват >= 0.70"]]),
         "| сверхосторожно | %s (%d/%d) | %s (%d/%d) | - | |" % (
             t5["overconservative_rate"], t5["overconservative"], t5["ref_standalone"], t["overconservative_rate"],
             t["overconservative"], t["ref_standalone"]), "",
         "Исходы V6: %s. Правила: %s." % (", ".join("%s %d" % kv for kv in sorted(res["outcomes"].items())),
                                          ", ".join("%s %d" % kv for kv in sorted(res["rules_fired"].items()))), "",
         "## Родство", "", "| источник | утверждений | закрыто | верно | точность |", "|---|---|---|---|---|"]
    for s, x in res["by_source"].items():
        L.append("| %s | %d | %d | %d | %s |" % (s, x["claims"], x["closed"], x["ok"], x["relation_precision"]))
    L += ["", "MCD: анимация %s (%d/%d), die с подтверждением %s (%d/%d); alt - улика, в точность не входит." % (
        res["mcd_claims"]["anim"]["relation_precision"], res["mcd_claims"]["anim"]["ok"],
        res["mcd_claims"]["anim"]["closed"], res["mcd_claims"]["die"]["relation_precision"],
        res["mcd_claims"]["die"]["ok"], res["mcd_claims"]["die"]["closed"]), "",
        "Снято с утверждений (%d): по эталону ok - %d, wrong - %d, open - %d." % (
            len(res["dropped"]), sum(c["status"] == "ok" for c in res["dropped_scored"]),
            sum(c["status"] == "wrong" for c in res["dropped_scored"]),
            sum(c["status"] == "open" for c in res["dropped_scored"])), "",
        "| кадр | родственник | что | почему снято | эталон |", "|---|---|---|---|---|"]
    for x, c in zip(res["dropped"], res["dropped_scored"]):
        L.append("| %s | %s | %s | %s | %s |" % (x[0], x[1], x[2], x[3], c["ref"]))
    L += ["", "| утверждение | вид | источник | эталон | статус |", "|---|---|---|---|---|"]
    for c in res["claims"]:
        L.append("| %s ~ %s | %s | %s | %s | %s |" % (c["asset_id"], c["relative"], c["kind"], c["source"], c["ref"],
                                                      c["status"]))
    L += ["", "## MATERIAL_VARIANT_OF / STYLE_VARIANT_OF (новый поиск)", "",
          "Наборов-двойников сравнено %d за %s с." % (res["variant_sets_compared"], res["variant_scan_sec"]), ""]
    L += ["- %s: %s" % (k, "; ".join("%s %s (%s)" % (v["kind"], v["relative"], v["why"]) for v in vs))
          for k, vs in sorted(res["variants"].items())] or ["- не найдено"]
    L += ["", "## Чувствительность (не итог)", "", "| вариант | опасных | точность | охват | сверхосторожно |",
          "|---|---|---|---|---|"]
    for k, s in res["sensitivity"].items():
        L.append("| %s | %d | %s (%d/%d) | %s | %s |" % (k, s["dangerous_false_standalone"], s["routing_accuracy"],
                                                         s["correct"], s["decided"], s["routing_coverage"],
                                                         s["overconservative_rate"]))
    for k, x in res["sensitivity_precision"].items():
        L.append("| родство: %s | | %s (%d/%d) | | |" % (k, x["relation_precision"], x["ok"], x["closed"]))
    ph = res["posthoc"]
    L += ["", "## Найдено после пересчёта (post-hoc, не правила V6 - решает специалист)", "",
          "| вариант | опасных | точность | охват | сверхосторожно |", "|---|---|---|---|---|"]
    for k, s in ph["routing"].items():
        L.append("| %s | %d | %s (%d/%d) | %s | %s |" % (k, s["dangerous_false_standalone"], s["routing_accuracy"],
                                                         s["correct"], s["decided"], s["routing_coverage"],
                                                         s["overconservative_rate"]))
    L += ["", "R0p (наборы оригинала: %s):" % ", ".join(ph["origin_sets"]), ""]
    L += ["- %s -> %s (эталон %s): %s" % tuple(x) for x in ph["r0p_rows"]] or ["- не сработало"]
    L += ["", "Неверные маршруты при оси A из эталона (то, что остаётся за правилами):", ""]
    L += ["- %s: A специалиста %s, V6 %s %s, эталон %s" % tuple(x) for x in ph["ref_axis_rows"]] or ["- нет"]
    x = ph["precision_without_phase_pairs"]
    L += ["", "Перекраска между двумя кадрами петель анимации (каждый в своей петле MCD): %s. Точность родства "
          "без них: %s (%d/%d)." % ("; ".join("%s ~ %s (%s, %s)" % tuple(p) for p in ph["phase_pairs"]) or "нет",
                                     x["relation_precision"], x["ok"], x["closed"])]
    L += ["", "Одиночный заказ при доказанной симметричной перекраске (pair_pick - из пары рисуется один кадр): %s." % (
        ", ".join(res["pair_pick"]) or "нет"), "",
          "## Сменили маршрут против V5", "", "| кадр | V5 | V6 | эталон | почему |", "|---|---|---|---|---|"]
    L += ["| %s | %s %s | %s %s | %s | %s |" % tuple(c) for c in res["changed_vs_v5"]]
    L += ["", "## По предметам", "", "| предмет | A / V6 / эталон | правило | V6 | эталон | исход | почему |",
          "|---|---|---|---|---|---|---|"]
    for r in res["rows"]:
        L.append("| %s | %s / %s / %s | %s | %s | %s | %s | %s |" % (
            r["asset_id"], r["semantic_kind"], r["semantic_v6"], r["ref_semantic_kind"], r["rule"], r["rule_unit"],
            r["ref_route"], outcome(r), r["why"]))
    with open(os.path.join(out, "recount.md"), "w", encoding=ir.ENC) as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L[:30]))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["recount"])
    ap.add_argument("--r2", action="store_true", help="V6_PREP_R2 -> routing-rules-v6-prep-r2")
    ap.add_argument("--out", default="", help="папка вывода (проверка воспроизводимости)")
    a = ap.parse_args()
    os.chdir(ROOT)
    prof = "r2" if a.r2 else "prep"
    recount(out=a.out or (OUT_R2 if a.r2 else OUT), profile=prof)


if __name__ == "__main__":
    main()
