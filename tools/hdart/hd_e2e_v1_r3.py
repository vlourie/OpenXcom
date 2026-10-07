#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""HD_PIPELINE_E2E_V1_R3 - сухой план E2E, ревью по действию (специалист 03.10, передал Vitali в чате). Замыкание и
утверждения V7 - те же, что у V1 и R2 (hd-e2e-v1/relations.lock.json); меняется только планировщик. V7, правила
связей, families.json, рендер и онтология опознания не меняются. Видеокарта не нужна.

    spec    -> hd-e2e-v1/r3/spec.json (неизменяемый: второй раз - только тот же)
    plan    -> hd-e2e-v1/r3/plan.json, plan.md; тикеты -> review/e2e-v1/review.jsonl (прежний R2 - копия в r2/)
    check   V7, spec V1, R2 и R3, relations и код рендера не изменились

Правила производства R3 (PRODUCTION_RULES_R3):
  - группа связей, единица рисования и дерево производства - как в R2; якорь (S2): из корней дерева берётся прежний
    (набор оригинала, затем меньший ключ), а среди его ТОЧНЫХ копий (EXACT_COPY_PEER между корнями) - кадр со своим
    подтверждённым опознанием, затем кадр партии, затем прежний порядок. Выбор якоря среди копий - не утверждение
    об оригинале;
  - рисуется только кадр со СВОИМ опознанием; нет - IDENTITY_MISSING, текст другого кадра не берётся;
  - открытое решение (неавтоматическое утверждение V7, улика, роль без цели, расхождение с V7) - тикет. Тикет
    блокирует не кадры, которых касается, а только те действия, которые его решение может изменить:
    candidate_affects_action(форма решения, кадр, действие) -> YES / NO. Формы решения - что значит «принять»:
    составной, модуль, анимация, примыкание, повтор сборки - общая единица (TOG); копия, перекраска-пара, правка -
    равноправная пара (SYM); перекраска от основы, износ - вывод одного из другого (DIR); тип на ревью или
    неизвестный тип - все формы; не production (перекраска при сильной анимации) - формы нет. Улика и роль без цели -
    вывод из неизвестного кадра или общая единица с ним;
  - YES, если: TOG касается кадра, геометрически равного действующему (его класс копий, отражений и перекрасок-пар,
    включая цепочки ещё не решённых SYM - «надкласс»): у копии куска сборки своего одиночного рисунка нет; DIR
    делает выводимым кадр надкласса из кадра вне его класса: основа может смениться; SYM к кадру вне замыкания:
    его связи неизвестны; расхождение с V7 - у концов пары. Основа DIR (база перекраски или износа) и SYM внутри
    надкласса - NO; но в одном надклассе отпускается только ОДИН рисунок (лучший по своему опознанию, партии,
    набору оригинала, ключу), остальные - дубль творческого рисунка;
  - автоматические связи проверяются тем же правилом: якорь в выведенном классе или копия куска сборки - блок;
  - заблокированное действие блокирует единицу целиком и всё, что из неё выводится (как в R2);
  - выводы: COPY и MIRROR_FLIP исполняются; DERIVE_RECOLOR и DERIVE_MIRROR_RECOLOR - DERIVE_NOT_VERIFIED (до
    DERIVE_RECOLOR_ACCEPTANCE_V2), STATE - STATE_NOT_IMPLEMENTED; OBJECT исполняется, STRUCTURAL и TERRAIN - только
    план, NONE - файлов нет; рендер PHOTO_STRUCT_V1, только одиночный кадр.
  Ворота unresolved_candidate_changed_completed_action проверяют правило независимо: строят миры, где решения
  приняты (каждое форма за формой, все разом, случайные наборы), и в каждом мире ищут отпущенное действие, которое
  стало бы неверным: рисунок в выведенном классе, копию куска сборки, два рисунка одного класса, вывод не из своего
  рисунка или другим способом.
VERIFIED ставит только человек; генерацию запускает команда специалиста, не этот модуль.

    py -3.13 tools/hdart/hd_e2e_v1_r3.py <команда>
"""
import argparse
import hashlib
import json
import os
import random
import shutil
import sys
import time
from collections import Counter, defaultdict, deque

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hd_e2e_v1 as E1                            # noqa: E402
import hd_e2e_v1_r2 as R2                         # noqa: E402
import identity_routing as ir                     # noqa: E402
import relation_discovery_v3 as v3                # noqa: E402
import relation_discovery_v4 as v4                # noqa: E402
import relation_taxonomy as tx                    # noqa: E402
import relation_safety_v7_prep as s7              # noqa: E402

ENC = ir.ENC
PROFILE = "HD_PIPELINE_E2E_V1_R3"
OUT = os.path.join(E1.OUT, "r3")
REVIEW_DIR = R2.REVIEW_DIR
OUTPUT_DIR = R2.OUTPUT_DIR
SELF = "tools/hdart/hd_e2e_v1_r3.py"
SEED0 = 5300
WORLDS_RANDOM = 400
WORLDS_SEED = 3

RENDERER, RENDERER_SUPPORTS, RENDERER_FILES = R2.RENDERER, R2.RENDERER_SUPPORTS, R2.RENDERER_FILES
RENDER_TOGETHER, DERIVE_METHOD = E1.RENDER_TOGETHER, E1.DERIVE_METHOD
METHOD_STATUS, METHOD_NOTE, PIPE_SCOPE = R2.METHOD_STATUS, R2.METHOD_NOTE, R2.PIPE_SCOPE
EXEC, PLAN_ONLY, STATUSES = R2.EXEC, R2.PLAN_ONLY, R2.STATUSES
ACTIONS = dict(R2.ACTIONS)
ACTIONS["TREE_CONFLICT"] = ["CHOOSE_BASE", "SPLIT_RELATION"]
# что значит «принять» утверждение: форма решения
TOGETHER_T = tuple(sorted(set(RENDER_TOGETHER) | {"ATTACHMENT_CANDIDATE", "REPEATED_ASSEMBLY_RELATION"}))
STATE_T = tuple(sorted(t for t, m in DERIVE_METHOD.items() if m == "STATE"))
DERIVE_T = dict({t: m for t, m in DERIVE_METHOD.items() if m != "STATE"}, NEAR_SILHOUETTE_RECOLOR="DERIVE_RECOLOR")
KNOWN_WHY = ("существование - кандидат", "примыкание - улика")
ROLE_TOG = ("COMPOSITE_PART", "STRUCTURAL_MODULAR", "ANIMATION_FAMILY")
DECISION_KINDS = ("UNRESOLVED_RELATION", "EVIDENCE", "SELF_ROLE_CANDIDATE", "SELF_ROLE_UNRESOLVED", "V7_REPLAY_DIFFERS")
# тикеты, которые не блокируют кадр сами по себе: решает candidate_affects_action
RELEASABLE = ("UNRESOLVED_RELATION",)
REL_CODES = ("UNIT_MAY_CHANGE", "SOURCE_MAY_CHANGE", "PARTNER_OUTSIDE_CLOSURE", "DUPLICATE_RENDER",
             "METHOD_MAY_CHANGE")

GATES = R2.GATES[:6] + (
    ("unresolved_relation_used_for_render", "исполняемый кадр задет тикетом, который блокирует сам (не "
                                            "UNRESOLVED_RELATION), или выведен по неавтоматической связи"),
    ("review_dependency_leak", "исполняемый кадр, в цепочке которого до якоря (с соседями по единице) есть "
                               "неисполняемый кадр"),
    ("identity_borrowed_from_other_asset", "задание без своего опознания или с опознанием другого кадра"),
    ("wrongly_sent_to_object_renderer", "в задании рендера кадр с конвейером не OBJECT_PIPELINE"),
    ("unresolved_candidate_changed_completed_action", "в мире, где открытые решения приняты (по одному, все разом, "
                                                      "случайные наборы), отпущенное действие стало неверным: "
                                                      "рисунок в выведенном классе или у копии куска сборки, два "
                                                      "рисунка одного класса, вывод не из своего рисунка или другим "
                                                      "способом"))
GATES = tuple((g, t) if g != "relation_decision_lost_in_handoff" else
              (g, "утверждение V7 по кадру группы, которого нет в плане: автоматическое нарушено (разные единицы "
                  "для рисуемых вместе, исполняемые кадры не из одного якоря), неавтоматическое - без тикета; "
                  "плюс расхождения с замороженным V7 (потеряно, ослаблено или исполняется)")
              for g, t in GATES)
if [g for g, _t in GATES] != [g for g, _t in R2.GATES] + ["unresolved_candidate_changed_completed_action"]:
    raise SystemExit("ворота R3 - те же десять, что R2, плюс одни новые")
BODY = ("profile", "decision", "v1_spec_sha256", "r2_spec_sha256", "relations_lock_sha256", "production_rules",
        "decision_forms", "method_status", "pipe_scope", "renderer", "gates", "worlds", "review_dir", "output_dir",
        "seed0", "v7")


def p(*a):
    return os.path.join(OUT, *a)


# ---------------------------------------------------------------- spec

def spec_body(d, ver, sp1, sp2):
    return {"profile": PROFILE,
            "decision": "специалист 03.10, передал Vitali в чате: S2 - якорь среди точных копий по своему опознанию, "
                        "партии, прежнему порядку; candidate_affects_action - открытое решение блокирует только "
                        "действия, которые может изменить; решение выше по дереву, способное сменить основу, "
                        "блокирует зависящее; опознание никогда не заимствуется; DERIVE_RECOLOR не исполняется; "
                        "новые ворота unresolved_candidate_changed_completed_action. V7, relations, рендер, "
                        "families.json не меняются",
            "v1_spec_sha256": sp1["sha256"], "r2_spec_sha256": sp2["sha256"],
            "relations_lock_sha256": E1.file_sha(E1.p("relations.lock.json")),
            "production_rules": __doc__.split("Правила производства R3")[1].split("VERIFIED ставит")[0].strip(),
            "decision_forms": {"TOG": list(TOGETHER_T), "SYM_or_DIR": sorted(DERIVE_T), "STATE_DIR": list(STATE_T),
                               "type_open": "все формы", "unknown_type": "все формы", "not_production": "нет формы",
                               "evidence": "DIR из неизвестного кадра или TOG с ним",
                               "self_role": "%s - TOG, иначе DIR" % "/".join(ROLE_TOG),
                               "v7_replay": "тип пары V7 вместо типа замыкания"},
            "method_status": METHOD_STATUS, "pipe_scope": PIPE_SCOPE,
            "renderer": {"name": RENDERER, "supports": list(RENDERER_SUPPORTS),
                         "config_sha256": R2.renderer_config(),
                         "runner": "render_chunks.py -> photo_struct_render.py (gpuq), вариант C"},
            "gates": [{"gate": g, "need": 0, "def": t} for g, t in GATES],
            "worlds": {"single": "каждое решение, каждая форма", "all": "все решения разом, 3 варианта форм",
                       "random": WORLDS_RANDOM, "seed": WORLDS_SEED},
            "review_dir": REVIEW_DIR.replace(os.sep, "/"), "output_dir": OUTPUT_DIR.replace(os.sep, "/"),
            "seed0": SEED0, "v7": E1.v7_ref(d, ver)}


def do_spec():
    d, _h, ver = E1.v7_state()
    sp1 = E1.load_spec()
    sp2 = R2.load_spec()
    body = spec_body(d, ver, sp1, sp2)
    os.makedirs(OUT, exist_ok=True)
    sp = p("spec.json")
    if os.path.exists(sp):
        old = ir.load_json(sp)
        if old["sha256"] != E1.jsha({k: body[k] for k in BODY}):
            raise SystemExit("spec.json R3 уже записан и отличается - спецификация не переписывается: %s" % sp)
        print("spec.json R3 тот же: %s" % old["sha256"][:12])
        return old
    body["created"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    body["code_sha256"] = E1.file_sha(SELF)
    body["sha256"] = E1.jsha({k: body[k] for k in BODY})
    ir.dump_json(sp, body)
    print("spec.json R3 %s: рендер %s" % (body["sha256"][:12], RENDERER))
    return body


def load_spec():
    sp = ir.load_json(p("spec.json"))
    if E1.jsha({k: sp[k] for k in BODY}) != sp["sha256"]:
        raise SystemExit("spec.json R3 изменён после записи")
    return sp


def check_frozen(sp):
    sp2 = R2.load_spec()
    sp1 = R2.check_frozen(sp2)
    if sp2["sha256"] != sp["r2_spec_sha256"] or sp1["sha256"] != sp["v1_spec_sha256"]:
        raise SystemExit("spec V1 или R2 не тот, на котором записан R3")
    if E1.file_sha(E1.p("relations.lock.json")) != sp["relations_lock_sha256"]:
        raise SystemExit("relations.lock.json изменён после spec R3")
    bad = [f for f, h in sp["renderer"]["config_sha256"].items() if E1.file_sha(f) != h]
    if bad:
        raise SystemExit("конфигурация рендера изменена после spec R3: %s" % ", ".join(bad))
    return sp1


# ---------------------------------------------------------------- формы решений

def edge_of(t, a, b, src, tgt):
    """Утверждение типа t, принятое как есть -> [ребро] или None (тип неизвестен). Ребро (вид, x, y, ярлык):
    TOG - общая единица, SYM - равноправная пара, DIR - x выводится из y."""
    if t in TOGETHER_T:
        return [("TOG", a, b, t)]
    if t in STATE_T:
        return [("DIR", src, tgt, "STATE")]
    if t in DERIVE_T:
        return [("SYM", a, b, DERIVE_T[t])] if t in v4.SYMMETRIC else [("DIR", src, tgt, DERIVE_T[t])]
    return None


def all_forms(a, b, lab="?", tog=True):
    out = [("SYM", a, b, lab), ("DIR", a, b, lab), ("DIR", b, a, lab)]
    return out + [("TOG", a, b, lab)] if tog else out


def forms_of(c):
    """Неавтоматическое утверждение V7 -> допустимые формы «принято» (список рёбер; пусто - производство не меняется)."""
    if not c.get("production", True):
        return []
    a, b = c["pair"]
    base = edge_of(c["type"], a, b, c["source"].upper(), c["target"].upper())
    why = [w for w in c.get("type_open_why", []) if w not in KNOWN_WHY]
    if base is None:
        return all_forms(a, b)
    if why:
        return all_forms(a, b, base[0][3], tog=c["group"] != "derived")
    return base


def auto_edges_of(C, keys):
    """Автоматические утверждения замыкания -> рёбра (по (группа, пара) один раз). Неотображённый тип - TOG."""
    seen, out = set(), []
    for k in keys:
        for c in C.of(k):
            if not tx.auto_claim(c) or (c["group"], tuple(c["pair"])) in seen:
                continue
            seen.add((c["group"], tuple(c["pair"])))
            a, b = c["pair"]
            out += edge_of(c["type"], a, b, c["source"].upper(), c["target"].upper()) or [("TOG", a, b, c["type"])]
    return out


def decision_key(kind, frames, claim_key=None):
    return hashlib.sha256(json.dumps([kind, sorted(frames), claim_key], ensure_ascii=False)
                          .encode("utf-8")).hexdigest()[:12]


def build_decisions(keys, C, rpairs):
    """Все открытые решения замыкания: утверждения V7, улики, роли, расхождения с V7. -> {ключ: решение}."""
    D = {}

    def add(kind, frames, forms, reason, claim=None, evidence=None):
        ck = [claim["group"], list(claim["pair"])] if claim else None
        k = decision_key(kind, frames, ck)
        D.setdefault(k, {"id": k, "kind": kind, "frames": sorted(set(frames)), "forms": forms, "reason": reason,
                         "claim": claim, "claim_key": ck, "evidence": evidence or []})
    for a in keys:
        for c in C.of(a):
            if tx.auto_claim(c):
                continue
            add("UNRESOLVED_RELATION", c["pair"], forms_of(c), "%s %s %s/%s%s" % (
                c["type"], "~".join(c["pair"]), c["existence"].split("_")[-1], c["type_level"].split("_")[-1],
                "" if c.get("production", True) else " не production"), claim=c)
    for a in keys:
        ext = "EXT:ev:" + a
        if C.evidence.get(a):
            ev = [{k: v for k, v in x.items() if isinstance(v, (str, int, float))} for x in C.evidence[a]]
            add("EVIDENCE", [a], [("DIR", a, ext, "?"), ("TOG", a, ext, "?")],
                "улика %s" % sorted({x["rule"] for x in C.evidence[a]}), evidence=ev)
        auto_types = {c["type"] for c in C.of(a) if tx.auto_claim(c)}
        for x in C.self_roles.get(a, []):
            ext = "EXT:role:%s:%s" % (x["type"], a)
            f = [("TOG", a, ext, x["type"])] if x["type"] in ROLE_TOG else [("DIR", a, ext, x["type"])]
            if x["level"] not in v3.BINDING:
                add("SELF_ROLE_CANDIDATE", [a], f, "роль %s %s" % (x["type"], x["level"]), evidence=[x.get("rule", "")])
            elif x["type"] not in auto_types:
                add("SELF_ROLE_UNRESOLVED", [a], f, "роль %s %s без цели: основы нет" % (x["type"], x["level"]),
                    evidence=[x.get("rule", "")])
    for pair, s in rpairs:
        v7t = s.split(": ", 1)[1].split()[1]
        add("V7_REPLAY_DIFFERS", pair, [("RETYPE", pair[0], pair[1], v7t)],
            "утверждение плана не то, что в holdout V7: %s" % s)
    return D


# ---------------------------------------------------------------- дерево группы

def key_old(origin):
    return lambda k: (k.split(":")[0] not in origin, k)


def key_s2(origin, ident, batch):
    return lambda k: (not ident.get(k, "").strip(), k not in batch, k.split(":")[0] not in origin, k)


def plan_tree(members, C, rowmap, origin, comp_items, ident, batch):
    """Группа связей: единицы рисования, дерево производства от якоря S2, структурные тикеты (как R2), конвейеры."""
    import routing_model_v8 as v8
    M = set(members)
    claims = {}
    for a in members:
        for c in C.of(a):
            claims[(c["group"], tuple(c["pair"]))] = c
    auto = [c for c in claims.values() if tx.auto_claim(c)]
    tickets, lost = [], []

    def T(kind, frames, reason):
        fs = sorted(set(frames) & M)
        if fs:
            tickets.append({"kind": kind, "frames": fs, "reason": reason, "claim": None, "claim_key": None,
                            "evidence": [], "possible_actions": ACTIONS[kind]})
    for c in auto:
        if not set(c["pair"]) <= M:
            T("AUTO_EDGE_OUTSIDE_CLOSURE", c["pair"], "%s %s вне замыкания" % (c["type"], "~".join(c["pair"])))
        elif c["type"] not in RENDER_TOGETHER and c["type"] not in DERIVE_METHOD:
            T("UNMAPPED_TYPE", c["pair"], "тип %s не отображён в производство" % c["type"])
            lost.append("UNMAPPED_TYPE %s %s" % (c["type"], "~".join(c["pair"])))
    upar = {k: k for k in members}

    def uf(x):
        while upar[x] != x:
            upar[x] = upar[upar[x]]
            x = upar[x]
        return x
    for c in auto:
        if c["type"] in RENDER_TOGETHER and set(c["pair"]) <= M:
            a, b = c["pair"]
            upar[uf(a)] = uf(b)
    ufs = defaultdict(list)
    for k in members:
        ufs[uf(k)].append(k)
    units, unit_of = {}, {}
    for fs in ufs.values():
        fs = sorted(fs)
        u = "u:" + fs[0]
        ts = {c["type"] for c in auto if c["type"] in RENDER_TOGETHER and set(c["pair"]) <= set(fs)}
        units[u] = {"frames": fs, "kind": "+".join(sorted({RENDER_TOGETHER[t] for t in ts})) or "SINGLE"}
        for k in fs:
            unit_of[k] = u
        for k in fs:
            it = comp_items.get(k)
            if it and not set(it["keys"]) <= set(fs):
                T("COMPOSITE_INCOMPLETE", set(fs) | set(it["keys"]),
                  "составной очереди %s шире единицы %s" % (it["keys"], fs))
                break
    adj = defaultdict(list)
    directed_src = set()
    copies = defaultdict(set)
    for c in auto:
        if c["type"] not in DERIVE_METHOD or not set(c["pair"]) <= M:
            continue
        meth = DERIVE_METHOD[c["type"]]
        if c["type"] in v4.SYMMETRIC:
            a, b = c["pair"]
            adj[a].append((b, c["type"], meth))
            adj[b].append((a, c["type"], meth))
            if c["type"] == "EXACT_COPY_PEER":
                copies[a].add(b)
                copies[b].add(a)
        else:
            src, tgt = c["source"].upper(), c["target"].upper()
            adj[tgt].append((src, c["type"], meth))
            directed_src.add(src)
    roots = sorted(k for k in members if k not in directed_src)
    if not roots:
        T("NO_ROOT", members, "у всех кадров есть основа - цикл направленных связей")
        roots = sorted(members)
    a0 = min(roots, key=key_old(origin))
    # S2: среди точных копий прежнего якоря (только корни) - своё опознание, партия, прежний порядок
    rs, cls, q = set(roots), {a0}, deque([a0])
    while q:
        x = q.popleft()
        for y in copies[x]:
            if y in rs and y not in cls:
                cls.add(y)
                q.append(y)
    anchor = min(cls, key=key_s2(origin, ident, batch))
    prod, order = {}, []
    q = deque()
    for k in units[unit_of[anchor]]["frames"]:
        prod[k] = {"method": "RENDER", "from": None, "via": units[unit_of[anchor]]["kind"]}
        q.append(k)
    while q:
        x = q.popleft()
        order.append(x)
        for y, t, meth in sorted(adj[x]):
            if y not in prod:
                prod[y] = {"method": meth, "from": x, "via": t}
                q.append(y)
    unreached = sorted(M - set(prod))
    for u, un in units.items():
        fs = un["frames"]
        if u != unit_of[anchor] and len(fs) > 1 and set(fs) & set(unreached):
            T("SECOND_RENDER_UNIT", fs, "единица %s %s не выводится целиком из якоря" % (un["kind"], fs))
    single_unreached = [k for k in unreached if len(units[unit_of[k]]["frames"]) == 1]
    if single_unreached:
        T("REVERSE_DERIVATION", single_unreached, "не достигнуты из якоря %s: основа не одна или вывод назад" % anchor)
    order += unreached
    pipes = {}
    for k in members:
        r = rowmap[k]
        pipes[k] = v8.pipeline_of(r["semantic_eff"], r["surface"], v4.pipe_roles(C, k))[0] if r["semantic_kind"] \
            else "NO_AXIS_A"
        if pipes[k] == "NO_AXIS_A":
            T("NO_AXIS_A", [k], "нет оси A ни своей, ни унаследованной")
        elif pipes[k] == "REVIEW":
            T("PIPELINE_REVIEW", [k], r["pipeline_why"])
    for k, pr_ in prod.items():
        x = pr_["from"]
        if x and {pipes[k], pipes[x]} <= set(PIPE_SCOPE) and pipes[k] != pipes[x]:
            T("PIPELINE_CONFLICT", [k, x], "%s %s, основа %s %s" % (k, pipes[k], x, pipes[x]))
    for u, un in units.items():
        ps = {pipes[k] for k in un["frames"]}
        if len(ps) > 1 and ps <= set(PIPE_SCOPE):
            T("PIPELINE_CONFLICT", un["frames"], "единица %s: конвейеры %s" % (u, sorted(ps)))
    if PIPE_SCOPE.get(pipes[anchor]) == "EXECUTE" and not ident.get(anchor, "").strip():
        T("IDENTITY_MISSING", [anchor], "у якоря %s нет своего опознания (ось A); текст другого кадра не берётся" %
          anchor)
    seen, tk = set(), []
    for t in tickets:
        t["ticket_key"] = decision_key(t["kind"], t["frames"])
        if t["ticket_key"] not in seen:
            seen.add(t["ticket_key"])
            tk.append(t)
    return {"members": sorted(members), "anchor": anchor, "anchor_old": a0, "roots": roots, "units": units,
            "unit_of": unit_of, "prod": prod, "order": order, "pipes": pipes, "tickets": tk, "lost": lost,
            "auto_claims": len(auto)}


# ---------------------------------------------------------------- классы

class UF:
    def __init__(self):
        self.par = {}

    def find(self, x):
        p_ = self.par.setdefault(x, x)
        while p_ != x:
            self.par[x] = self.par.setdefault(p_, p_)
            x, p_ = p_, self.par[p_]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.par[ra] = rb

    def copy(self):
        u = UF()
        u.par = dict(self.par)
        return u


class Ctx:
    """Классы для правила: класс - кадры, связанные автоматическими SYM (копия, отражение, перекраска-пара); надкласс -
    классы, связанные ещё и SYM-формами открытых решений. mode combo - решения могут приниматься вместе; single -
    по одному (только для сравнения)."""

    def __init__(self, auto_edges, D, closure, mode="combo"):
        self.mode, self.closure = mode, set(closure)
        self.cls = UF()
        for k in closure:
            self.cls.find(k)
        for e in auto_edges:
            if e[0] == "SYM":
                self.cls.union(e[1], e[2])
        self.cadj = defaultdict(list)          # класс -> [(класс, решение)]
        self.sc = UF()
        for d in D.values():
            for e in d["forms"]:
                if e[0] == "SYM":
                    a, b = self.cls.find(e[1]), self.cls.find(e[2])
                    if a != b:
                        self.cadj[a].append((b, d["id"]))
                        self.cadj[b].append((a, d["id"]))
                        self.sc.union(a, b)
        self._path = {}

    def same_class(self, a, b):
        return self.cls.find(a) == self.cls.find(b)

    def reach(self, f, z, link=False):
        """Решения, при принятии которых кадр z геометрически равен кадру f (None - не бывает): [] - один класс;
        combo - путь по SYM-решениям надкласса; single - только при link (автоматический довод) одно решение."""
        a, b = self.cls.find(f), self.cls.find(z)
        if a == b:
            return []
        if self.mode == "single":
            if not link:
                return None
            ds = sorted(d for c, d in self.cadj[a] if c == b)
            return ds[:1] or None
        if self.sc.find(a) != self.sc.find(b):
            return None
        if (a, b) not in self._path:
            prev, q = {a: None}, deque([a])
            while q:
                x = q.popleft()
                if x == b:
                    break
                for y, d in sorted(self.cadj[x]):
                    if y not in prev:
                        prev[y] = (x, d)
                        q.append(y)
            path, x = [], b
            while prev[x]:
                x, d = prev[x]
                path.append(d)
            self._path[(a, b)] = sorted(set(path))
        return self._path[(a, b)]

    def peers(self, f):
        """Классы, геометрически равные классу f при каком-то принятии: combo - надкласс, single - соседи по одному
        решению."""
        a = self.cls.find(f)
        if self.mode == "single":
            return {a} | {c for c, _d in self.cadj[a]}
        return {c for c in self.cadj_nodes() if self.sc.find(c) == self.sc.find(a)} | {a}

    def cadj_nodes(self):
        return set(self.cadj)


def candidate_affects_action(e, f, action, ctx, auto=False, unit=()):
    """Форма решения e (принятое утверждение, улика, роль, расхождение с V7) меняет ли действие action кадра f?
    -> ("YES" | "NO", код, решения-связки). auto - довод автоматический (проверка самого дерева)."""
    kind, x, y, _lab = e
    if kind == "TOG":
        if auto and x in unit and y in unit:
            return "NO", "", []
        for z in (x, y):
            pth = ctx.reach(f, z, link=auto)
            if pth is not None:
                return "YES", "UNIT_MAY_CHANGE", pth
    elif kind == "DIR":                                      # x выводится из y
        if auto and action != "RENDER":
            return "NO", "", []
        pth = ctx.reach(f, x, link=auto)
        if pth is not None and not ctx.same_class(f, y):
            return "YES", "SOURCE_MAY_CHANGE", pth
    elif kind == "SYM":
        for z, w in ((x, y), (y, x)):
            if w not in ctx.closure and not w.startswith("EXT:"):
                pth = ctx.reach(f, z)
                if pth is not None:
                    return "YES", "PARTNER_OUTSIDE_CLOSURE", pth
    elif kind == "RETYPE":
        if f in (x, y):
            return "YES", "METHOD_MAY_CHANGE", []
    return "NO", "", []


def rule_affects(groups, D, auto_edges, ctx, rule=candidate_affects_action):
    """Кадр группы партии -> [(код, [ключи решений и тикетов])]: какие решения меняют его действие."""
    aff = defaultdict(list)
    frames = [(g, k) for g in groups for k in g["members"]]
    for d in D.values():
        for e in d["forms"]:
            for g, k in frames:
                act = (g["prod"].get(k) or {}).get("method", "UNREACHED")
                yes, code, pth = rule(e, k, act, ctx)
                if yes == "YES":
                    aff[k].append((code, sorted(set([d["id"]] + pth))))
    for e in auto_edges:
        if e[0] not in ("TOG", "DIR"):
            continue
        for g, k in frames:
            act = (g["prod"].get(k) or {}).get("method", "UNREACHED")
            unit = g["units"][g["unit_of"][k]]["frames"]
            yes, code, pth = rule(e, k, act, ctx, auto=True, unit=unit)
            if yes == "YES":
                aff[k].append((code, ["TREE:%s:%s~%s" % (e[0], e[1], e[2])] + pth))
    return aff


# ---------------------------------------------------------------- план

def plan_all(groups, D, auto_edges, ctx, ident, origin, batch, rule=candidate_affects_action):
    """Статусы всех групп: правило, единицы целиком, вниз по дереву, один рисунок на надкласс."""
    aff = rule_affects(groups, D, auto_edges, ctx, rule)
    dup = defaultdict(list)
    pk = key_s2(origin, ident, batch)
    for _round in range(len(groups) + 2):
        for g in groups:
            touched = defaultdict(list)
            for t in g["tickets"]:                           # структурные тикеты блокируют свои кадры
                for k in t["frames"]:
                    touched[k].append(t["ticket_key"])
            for k in g["members"]:
                for _code, ids in aff.get(k, []) + dup.get(k, []):
                    touched[k] += ids
            blocked0 = {g["unit_of"][k] for k in touched}
            g["status"], g["cause"] = R2.statuses(g["order"], g["prod"], g["units"], g["unit_of"], g["pipes"],
                                                  touched, blocked0, RENDERER_SUPPORTS)
        renders = sorted((g["anchor"] for g in groups if g["status"][g["anchor"]] == "RENDER"), key=pk)
        new = False
        kept = []
        for r in renders:
            clash = [(k, ctx.reach(r, k)) for k in kept]
            clash = [(k, pth) for k, pth in clash if pth is not None and
                     (ctx.mode == "combo" or len(pth) <= 1)]
            if clash:
                k, pth = clash[0]
                dup[r].append(("DUPLICATE_RENDER", sorted(set(pth)) or ["TREE:SAME_CLASS:%s~%s" % (k, r)]))
                new = True
            else:
                kept.append(r)
        if not new:
            break
    for g in groups:
        g["affects"] = {k: aff.get(k, []) + dup.get(k, []) for k in g["members"] if aff.get(k) or dup.get(k)}
        for un in g["units"].values():
            un["status"] = sorted({g["status"][k] for k in un["frames"]})
    return groups


# ---------------------------------------------------------------- миры (ворота)

def world_check(base_cls, auto_edges, world, renders, derived):
    """Мир: формы принятых решений. -> нарушения отпущенного: рисунок в выведенном классе или у копии куска сборки,
    два рисунка одного класса, вывод не из класса своего рисунка или другим способом."""
    cls = base_cls.copy()
    dirs, togs, retype = [], [], {}
    for e in list(auto_edges) + list(world):
        if e[0] == "SYM":
            cls.union(e[1], e[2])
        elif e[0] == "DIR":
            dirs.append(e)
        elif e[0] == "TOG":
            togs.append(e)
        elif e[0] == "RETYPE":
            retype[frozenset((e[1], e[2]))] = e[3]
    derived_cls = {cls.find(e[1]) for e in dirs if cls.find(e[1]) != cls.find(e[2])}
    tog_cls = {cls.find(z) for e in togs for z in (e[1], e[2])}
    out = []
    rc = Counter(cls.find(r) for r in renders)
    for r in renders:
        c = cls.find(r)
        if c in derived_cls:
            out.append("render %s: класс выводится" % r)
        if c in tog_cls:
            out.append("render %s: класс - кусок сборки" % r)
        if rc[c] > 1:
            out.append("render %s: второй рисунок класса" % r)
    for k, (top, x, via) in derived.items():
        if cls.find(k) != cls.find(top):
            out.append("derive %s: не из класса рисунка %s" % (k, top))
        if frozenset((k, x)) in retype and retype[frozenset((k, x))] != via:
            out.append("derive %s: способ другой (%s вместо %s)" % (k, retype[frozenset((k, x))], via))
    return out


def worlds_of(D, n_random=WORLDS_RANDOM, seed=WORLDS_SEED):
    ds = [d for d in sorted(D.values(), key=lambda d: d["id"]) if d["forms"]]
    out = [("W0", [])]
    for d in ds:
        for i, e in enumerate(d["forms"]):
            out.append(("one:%s/%d" % (d["id"], i), [e]))
    out.append(("all:first", [d["forms"][0] for d in ds]))
    out.append(("all:last", [d["forms"][-1] for d in ds]))
    out.append(("all:sym", [next((e for e in d["forms"] if e[0] == "SYM"), d["forms"][0]) for d in ds]))
    rnd = random.Random(seed)
    for i in range(n_random):
        out.append(("rnd:%d" % i, [rnd.choice(d["forms"]) for d in ds if rnd.random() < 0.5]))
    return out


def simulate(groups, D, auto_edges, closure, n_random=WORLDS_RANDOM, seed=WORLDS_SEED):
    """Ворота unresolved_candidate_changed_completed_action: -> (число миров, {действие: [(мир, нарушение)]})."""
    base = UF()
    for k in closure:
        base.find(k)
    renders = [k for g in groups for k in g["members"] if g["status"].get(k) == "RENDER"]
    derived = {}
    for g in groups:
        for k in g["members"]:
            if g["status"].get(k) == "DERIVE":
                pr_ = g["prod"][k]
                derived[k] = (E1.chain_of(g["prod"], k)[-1], pr_["from"], pr_["via"])
    bad = defaultdict(list)
    ws = worlds_of(D, n_random, seed)
    for name, w in ws:
        for v in world_check(base, auto_edges, w, renders, derived):
            bad[v.split(":")[0].split()[-1]].append((name, v))
    return len(ws), bad


# ---------------------------------------------------------------- ворота R3

def gates_r3(groups, jobs, C, tickets, D, auto_edges, closure, replay=None, batch=(), n_random=WORLDS_RANDOM):
    G, det = Counter({g: 0 for g, _t in GATES}), defaultdict(list)

    def hit(gate, what):
        G[gate] += 1
        det[gate].append(what)
    gby = {g["group_id"]: g for g in groups}
    gid_of = {k: g["group_id"] for g in groups for k in g["members"]}
    for gid, n in Counter(j["group_id"] for j in jobs).items():
        if n > 1:
            hit("unexpected_duplicate_creative_render", "jobs %s x%d" % (gid, n))
    for k, n in Counter(k for j in jobs for k in j["render_unit"]).items():
        if n > 1:
            hit("unexpected_duplicate_creative_render", "frame %s x%d" % (k, n))
    for j in jobs:
        g = gby[j["group_id"]]
        M = set(g["members"])
        if j["render_asset"] != g["anchor"] or j["render_asset"] not in j["render_unit"]:
            hit("render_group_anchor_violation", j["job_id"])
        if j.get("identity_source") != j["render_asset"] or not j.get("identity", "").strip():
            hit("identity_borrowed_from_other_asset", "%s %s <- %s" % (j["job_id"], j["render_asset"],
                                                                      j.get("identity_source")))
        for k in j["render_unit"]:
            # опасен кадр, у которого САМОГО открыта общая единица, вывод из чужого, улика, роль без цели, связь наружу
            own = [c for c in C.of(k) if not tx.auto_claim(c) and any(
                e[0] == "TOG" or (e[0] == "DIR" and e[1] == k) for e in forms_of(c))]
            outside = [c for c in C.of(k) if tx.auto_claim(c) and not set(c["pair"]) <= M]
            roles = [x for x in C.self_roles.get(k, []) if not any(
                c["type"] == x["type"] and tx.auto_claim(c) and set(c["pair"]) <= M for c in C.of(k))]
            if own or outside or C.evidence.get(k) or roles:
                hit("dangerous_independent_render", k)
            if g["status"].get(k) != "RENDER" or g["prod"].get(k, {}).get("method") != "RENDER":
                hit("unexpected_duplicate_creative_render", "derived-in-render %s" % k)
            if g["pipes"].get(k) != "OBJECT_PIPELINE":
                hit("wrongly_sent_to_object_renderer", "%s %s" % (k, g["pipes"].get(k)))
                hit("wrong_pipeline_target", "job %s %s" % (k, g["pipes"].get(k)))
            if g.get("kinds", {}).get(k, "OBJECT") not in ("OBJECT", "OBJECT_PART"):
                hit("wrong_pipeline_target", "axis A %s %s" % (k, g["kinds"][k]))
    job_units = {(j["group_id"], gby[j["group_id"]]["unit_of"][j["render_asset"]]) for j in jobs}
    tk_claims = {tuple([t["claim_key"][0]] + sorted(t["claim_key"][1])) for t in tickets if t.get("claim_key")}
    blocking = defaultdict(list)
    for t in tickets:
        if t["kind"] not in RELEASABLE:
            for k in t["frames"]:
                blocking[k].append(t["kind"])
    for g in groups:
        M = set(g["members"])
        for k in g["members"]:
            s = g["status"].get(k)
            if s not in STATUSES:
                hit("missing_expected_output", "%s status %s" % (k, s))
                continue
            if s in EXEC and g.get("kinds", {}).get(k) == "NOT_OBJECT":
                hit("wrong_pipeline_target", "file-for-not-object %s" % k)
            if s == "DERIVE":
                pr_ = g["prod"].get(k) or {}
                x = pr_.get("from")
                if not x or not any(tx.auto_claim(c) and c["type"] == pr_.get("via") and set(c["pair"]) == {k, x}
                                    for c in C.of(k)):
                    hit("unresolved_relation_used_for_render", "derive %s <- %s via %s" % (k, x, pr_.get("via")))
                top = E1.chain_of(g["prod"], k)[-1]
                if g["prod"].get(top, {}).get("method") != "RENDER" or \
                        (g["group_id"], g["unit_of"][top]) not in job_units:
                    hit("render_group_anchor_violation", "derive %s from %s without job" % (k, top))
            if s in EXEC:
                if blocking.get(k):
                    hit("unresolved_relation_used_for_render", "touched %s %s" % (k, sorted(set(blocking[k]))))
                leak = sorted(y for y in R2.chain_frames(g, k) if y != k and g["status"].get(y) not in EXEC)
                if leak:
                    hit("review_dependency_leak", "%s <- %s" % (k, ",".join(leak[:3])))
            for c in C.of(k):
                a, b = c["pair"]
                if tx.auto_claim(c):
                    if not set(c["pair"]) <= M:
                        hit("relation_decision_lost_in_handoff", "auto outside %s %s" % (k, "~".join(c["pair"])))
                    elif c["type"] in RENDER_TOGETHER and g["unit_of"][a] != g["unit_of"][b]:
                        hit("relation_decision_lost_in_handoff", "unit split %s %s" % (c["type"], "~".join(c["pair"])))
                elif tuple([c["group"]] + sorted(c["pair"])) not in tk_claims:
                    hit("relation_decision_lost_in_handoff", "no ticket %s %s" % (c["type"], "~".join(c["pair"])))
        for t in g["lost"]:
            hit("relation_decision_lost_in_handoff", "%s %s" % (g["group_id"], t))
        tops = {E1.chain_of(g["prod"], k)[-1] for k in g["members"] if g["status"].get(k) in EXEC}
        if len({g["unit_of"][t] for t in tops}) > 1:
            hit("relation_decision_lost_in_handoff", "two sources in %s" % g["group_id"])
    for k in batch:
        if k not in gid_of:
            hit("missing_expected_output", "batch-not-planned %s" % k)
    if replay:
        st_all = {k: g["status"].get(k) for g in groups for k in g["members"]}
        for pair, s in R2.replay_pairs(replay):
            if s.startswith(("lost", "weaker")) or any(st_all.get(k) in EXEC for k in pair):
                hit("relation_decision_lost_in_handoff", "V7_REPLAY " + s)
    nw, bad = simulate(groups, D, auto_edges, closure, n_random)
    for k, vs in sorted(bad.items()):
        hit("unresolved_candidate_changed_completed_action", "%s: %s (%s; миров %d)" % (k, vs[0][1], vs[0][0],
                                                                                    len(vs)))
    return G, det, nw


# ---------------------------------------------------------------- сборка плана

def load_world():
    """Всё, что план берёт с диска: V7, замыкание, ось A, утверждения. -> словарь."""
    d, h, _ver = E1.v7_state()
    lk, L = E1.load_relations()
    keys = [k.upper() for k in lk["keys"]]
    rpath = lk["files"]["relations"]["path"]
    ax = E1.axis_a()
    sp1 = E1.load_spec()
    batch = [x["asset_id"].upper() for x in sp1["selection"]]
    own = {k: ax[k] for k in keys if k in ax and ax[k]["semantic_kind"]}
    kind0 = {k: r["semantic_kind"] for k, r in own.items()}
    ident = {k: r["final_identity"] for k, r in own.items() if r["final_identity"].strip()}
    _r0, C0, _p0 = E1.build(d, keys, rpath, L["detectors"], L["v3"], L["v4"], L["v7"]["edges"], kind0)
    comps0 = E1.components(keys, E1.auto_pairs(C0, keys))
    kinds = E1.inherit_kinds(comps0, kind0)
    rows, C, pr = E1.build(d, keys, rpath, L["detectors"], L["v3"], L["v4"], L["v7"]["edges"], kinds)
    comps = E1.components(keys, E1.auto_pairs(C, keys))
    if sorted(map(tuple, comps)) != sorted(map(tuple, comps0)):
        raise SystemExit("ось A изменила автоматические связи - так быть не должно")
    _copies, comp_items = E1.items_index(d["inputs"])
    replay = E1.v7_replay(d, h, C)
    return {"d": d, "lk": lk, "keys": keys, "batch": batch, "sp1": sp1, "kind0": kind0, "kinds": kinds,
            "ident": ident, "C": C, "rowmap": {r["asset_id"].upper(): r for r in rows},
            "origin": {s.upper() for s in pr["origin"]}, "comps": comps, "comp_items": comp_items,
            "where": R2.items_where(d["inputs"]), "replay": replay}


def build_plan(W, mode="combo", rule=candidate_affects_action):
    """План R3 на загруженном мире: группы партии, решения, правило, статусы, тикеты, задания."""
    keys, batch, C, ident, origin = W["keys"], W["batch"], W["C"], W["ident"], W["origin"]
    rpairs = R2.replay_pairs(W["replay"])
    D = build_decisions(keys, C, rpairs)
    auto_edges = auto_edges_of(C, keys)
    groups = []
    for fs in W["comps"]:
        if not set(fs) & set(batch):
            continue
        g = plan_tree(fs, C, W["rowmap"], origin, W["comp_items"], ident, set(batch))
        g["group_id"] = "g:" + g["anchor"]
        g["batch_keys"] = sorted(set(fs) & set(batch))
        g["kinds"] = {k: W["kinds"].get(k, "") for k in fs}
        groups.append(g)
    ctx = Ctx(auto_edges, D, keys, mode)
    plan_all(groups, D, auto_edges, ctx, ident, origin, set(batch), rule)
    return {"groups": groups, "D": D, "auto_edges": auto_edges, "ctx": ctx}


def make_tickets(P, batch):
    """Тикеты: структурные - по группам; решения - по одному на вопрос, если касаются кадра группы партии или
    меняют его действие. Номера по порядку, ключ стабилен."""
    groups, D = P["groups"], P["D"]
    gid_of = {k: g["group_id"] for g in groups for k in g["members"]}
    used = defaultdict(set)                              # решение -> кадры групп, чьи действия оно меняет
    for g in groups:
        for k, lst in g["affects"].items():
            for _code, ids in lst:
                for i in ids:
                    used[i].add(k)
    tickets = []
    for g in sorted(groups, key=lambda g: g["group_id"]):
        for t in g["tickets"]:
            t["group_ids"] = [g["group_id"]]
            tickets.append(t)
    for d in sorted(D.values(), key=lambda d: (d["kind"], d["frames"])):
        if not (set(d["frames"]) & set(gid_of) or used.get(d["id"])):
            continue
        t = {"kind": d["kind"], "frames": d["frames"], "reason": d["reason"], "claim": None,
             "claim_key": d["claim_key"], "evidence": d["evidence"], "possible_actions": ACTIONS[d["kind"]],
             "ticket_key": d["id"], "forms": [list(e) for e in d["forms"]],
             "group_ids": sorted({gid_of[k] for k in d["frames"] if k in gid_of} |
                                 {gid_of[k] for k in used.get(d["id"], ())})}
        if d["claim"]:
            c = d["claim"]
            a0 = next((a for a in c["pair"] if a in gid_of), c["pair"][0])
            cv = E1.claim_view(c, a0)
            cv["actions_v7"] = {a: s7.action_of(c, a) for a in c["pair"]}
            t["claim"] = cv
            t["evidence"] = cv["detectors"] + cv["why_open"]
        tickets.append(t)
    tickets.sort(key=lambda t: (t["group_ids"][0] if t["group_ids"] else "", t["kind"], t["frames"]))
    for i, t in enumerate(tickets):
        t["review_id"] = "R%05d" % (i + 1)
        t["batch_assets"] = sorted(set(t["frames"]) & set(batch))
    rid = {t["ticket_key"]: t["review_id"] for t in tickets}
    for t in tickets:
        aff = sorted(used.get(t["ticket_key"], set()) | (set(t["frames"]) & set(gid_of)
                                                          if t["kind"] not in RELEASABLE else set()))
        unit_of = {k: (g["group_id"], g["unit_of"][k]) for g in groups for k in g["members"]}
        t["affected_frames"] = aff
        t["affected_render_units"] = sorted({"%s/%s" % unit_of[k] for k in aff})
        st = {k: g["status"][k] for g in groups for k in g["members"]}
        t["downstream_blocked"] = sorted({"%s/%s" % unit_of[k] for g in groups for k in g["members"]
                                          if st[k] == "BLOCKED_UPSTREAM" and t["ticket_key"] in g["cause"][k]} -
                                         set(t["affected_render_units"]))
        t["released_despite"] = sorted(k for k in t["frames"] if st.get(k) in EXEC)
        t["scope"] = sorted({PIPE_SCOPE.get(g["pipes"][k], g["pipes"][k]) for g in groups for k in g["members"]
                             if k in t["frames"] or k in aff})
    return tickets, rid


def make_jobs(groups, ident, where):
    jobs = []
    for g in sorted(groups, key=lambda g: g["anchor"]):
        a = g["anchor"]
        if g["status"][a] != "RENDER":
            continue
        u = g["units"][g["unit_of"][a]]
        w = where.get(a, {})
        n = len(jobs) + 1
        jobs.append({"job_id": "r%02d" % n, "group_id": g["group_id"], "render_asset": a, "render_unit": u["frames"],
                     "needs": u["kind"], "renderer": RENDERER, "pipeline": g["pipes"][a],
                     "identity": ident.get(a, ""), "identity_source": a if ident.get(a) else "",
                     "identity_status": "AXIS_A_FINAL_IDENTITY" if ident.get(a) else "IDENTITY_MISSING",
                     "anchor_rule": "S2" if a != g["anchor_old"] else "OLD",
                     "map": w.get("map", ""), "at": w.get("at", []), "take": ["%s@0" % a],
                     "seed": SEED0 + n, "outputs": [E1.game_path(k) for k in u["frames"]],
                     "output_dir": OUTPUT_DIR.replace(os.sep, "/")})
        g["job_id"] = jobs[-1]["job_id"]
    return jobs


def do_plan():
    sp = load_spec()
    sp1 = check_frozen(sp)
    W = load_world()
    keys, batch, C = W["keys"], W["batch"], W["C"]
    cat = {x["asset_id"].upper(): x["category"] for x in sp1["selection"]}
    P = build_plan(W, "combo")
    groups, D = P["groups"], P["D"]
    tickets, rid = make_tickets(P, batch)
    jobs = make_jobs(groups, W["ident"], W["where"])
    frames = []
    for g in groups:
        for k in g["members"]:
            s = g["status"][k]
            pr_ = g["prod"].get(k) or {}
            prodr = "RENDER %s" % g["job_id"] if s == "RENDER" else (
                "%s from %s" % (pr_["method"], pr_["from"]) if s == "DERIVE" else "")
            frames.append({
                "asset_id": k, "file": E1.game_path(k), "batch": k in batch, "category": cat.get(k, ""),
                "relation_group_id": g["group_id"], "render_unit": g["unit_of"][k],
                "render_unit_kind": g["units"][g["unit_of"][k]]["kind"], "render_anchor": g["anchor"],
                "semantic_kind": W["kinds"].get(k, ""), "axis_a": "SPECIALIST" if k in W["kind0"] else
                ("INHERITED" if W["kinds"].get(k) else "NONE"), "identity_own": bool(W["ident"].get(k)),
                "pipeline_target": g["pipes"][k], "method": pr_.get("method", "UNREACHED"), "from": pr_.get("from"),
                "via": pr_.get("via"), "status": s, "producer": prodr,
                "cause": sorted({rid.get(c, c) for c in g["cause"][k]}),
                "affects": [{"code": code, "by": sorted({rid.get(i, i) for i in ids})}
                            for code, ids in g["affects"].get(k, [])],
                "tickets": [t["review_id"] for t in tickets if k in t["frames"]],
                "released_despite": [t["review_id"] for t in tickets if k in t["frames"] and s in EXEC],
                "upstream_exposed_by": [],
                "relations": ["%s %s %s/%s%s" % (c["type"], "~".join(c["pair"]), c["existence"].split("_")[-1],
                                                 c["type_level"].split("_")[-1], " AUTO" if tx.auto_claim(c) else "")
                              for c in C.of(k)]})
    G, det, nw = gates_r3(groups, jobs, C, tickets, D, P["auto_edges"], keys, W["replay"], batch)
    # то же правило, если решения принимаются только по одному - для сравнения, не план
    Ps = build_plan(W, "single")
    nws, bads = simulate(Ps["groups"], Ps["D"], Ps["auto_edges"], keys)
    single = {"jobs": sum(1 for g in Ps["groups"] if g["status"][g["anchor"]] == "RENDER"),
              "derived": dict(Counter(g["prod"][k]["method"] for g in Ps["groups"] for k in g["members"]
                                      if g["status"][k] == "DERIVE")),
              "unsafe_in_combined_worlds": sorted(bads), "worlds": nws,
              "examples": {k: v[0] for k, v in sorted(bads.items())[:10]}}
    diag = diagnostics(groups, jobs, frames, tickets, keys, W["replay"], W["lk"], nw, single, W)
    ok = all(v == 0 for v in G.values())
    res = {"profile": PROFILE, "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "spec_sha256": sp["sha256"],
           "v1_spec_sha256": sp1["sha256"], "r2_spec_sha256": sp["r2_spec_sha256"],
           "relations_lock_sha256": sp["relations_lock_sha256"], "code_sha256": E1.file_sha(SELF),
           "renderer": RENDERER, "verdict": "PLAN_CONSISTENT" if ok else "PLAN_FAIL",
           "gates": [{"gate": gn, "value": G[gn], "need": 0, "status": "PASS" if G[gn] == 0 else "FAIL",
                      "detail": det[gn][:40]} for gn, _t in GATES],
           "diagnostics": diag, "jobs": jobs, "frames": frames,
           "groups": [{"group_id": g["group_id"], "anchor": g["anchor"], "anchor_old": g["anchor_old"],
                       "members": g["members"], "batch_keys": g["batch_keys"], "units": g["units"],
                       "auto_claims": g["auto_claims"],
                       "tickets": [t["review_id"] for t in tickets if g["group_id"] in t["group_ids"]]}
                      for g in groups],
           "tickets_file": os.path.join(REVIEW_DIR, "review.jsonl").replace(os.sep, "/")}
    res["jobs_sha256"] = E1.jsha(jobs)
    os.makedirs(OUT, exist_ok=True)
    ir.dump_json(p("plan.json"), res)
    keep_r2_review()
    write_review(tickets)
    write_md(res, tickets)
    print("план R3: %s; заданий %d, выводится %d, тикетов %d, единиц освобождено %d из %d, миров %d; ворота %s" % (
        res["verdict"], len(jobs), diag["derived_outputs"]["frames"], len(tickets),
        diag["render_units_released"], diag["render_units"], nw, {g["gate"]: g["value"] for g in res["gates"]}))


def keep_r2_review():
    """Тикеты R2 лежат в review.jsonl; R3 пишет туда свои - прежние один раз копируются в r2/review_r2.jsonl."""
    src = os.path.join(REVIEW_DIR, "review.jsonl")
    dst = R2.p("review_r2.jsonl")
    if os.path.exists(src) and not os.path.exists(dst):
        first = open(src, encoding=ENC).readline()
        if '"affected_frames_status"' in first:               # формат R2
            shutil.copyfile(src, dst)


def diagnostics(groups, jobs, frames, tickets, keys, replay, lk, nw, single, W):
    dg = R2.diagnostics(groups, jobs, frames, tickets, keys, replay, lk)
    dg.pop("upstream_exposed", None)
    fr = {f["asset_id"]: f for f in frames}
    by_t = {t["review_id"]: t for t in tickets}
    rel = Counter()
    rel_frames = set()
    for t in tickets:
        if t["kind"] in RELEASABLE:
            for k in t["released_despite"]:
                rel_frames.add(k)
                c = t["claim"]
                side = "SYM" if c["type"] in v4.SYMMETRIC else ("base" if c["target"] == k else "derived")
                rel["%s %s/%s %s%s" % (c["type"], c["existence"].split("_")[-1], c["type_level"].split("_")[-1],
                                       side, "" if c["auto"] or t["forms"] else " no-production")] += 1
    exe = [f for f in frames if f["status"] in EXEC]
    blocked_src = Counter()
    blocked_src_frames = []
    for f in frames:
        if f["status"] in EXEC:
            continue
        codes = {a["code"] for a in f["affects"]} & set(REL_CODES)
        if codes:
            blocked_src_frames.append(f["asset_id"])
            for c in codes:
                blocked_src[c] += 1
        elif f["status"] == "BLOCKED_UPSTREAM":
            blocked_src["UPSTREAM_BLOCKED"] += 1
    noaxis = []
    for g in groups:
        if any(t["kind"] == "NO_AXIS_A" for t in g["tickets"]):
            a = g["anchor"]
            noaxis.append({"group_id": g["group_id"], "frames": len(g["members"]), "anchor": a,
                           "anchor_unit": g["units"][g["unit_of"][a]]["frames"],
                           "anchor_unit_kind": g["units"][g["unit_of"][a]]["kind"],
                           "roots": len(g["roots"]),
                           "anchor_relation_blocks": sorted({x["code"] for x in fr[a]["affects"]} & set(REL_CODES)),
                           "anchor_other_tickets": sorted({by_t[r]["kind"] for r in fr[a]["tickets"]
                                                           if by_t[r]["kind"] not in RELEASABLE + ("NO_AXIS_A",)})})
    dg.update({"released_despite_unresolved": {"frames": len(rel_frames), "by_type": dict(rel),
                                               "assets": sorted(rel_frames)},
               "invariant_actions": {"count": len(exe), "worlds": nw,
                                     "without_any_open_decision": sum(1 for f in exe if not f["tickets"])},
               "source_could_change_blocked": {"frames": len(blocked_src_frames), "by_reason": dict(blocked_src)},
               "action_types": sorted({f["method"] for f in exe}),
               "anchors_s2": [{"group_id": g["group_id"], "anchor": g["anchor"], "was": g["anchor_old"]}
                              for g in groups if g["anchor"] != g["anchor_old"]],
               "single_reading": single, "no_axis_a_groups": noaxis})
    dg["executable_actions"] = len(jobs) + dg["derived_outputs"]["frames"]
    return dg


def write_review(tickets):
    os.makedirs(REVIEW_DIR, exist_ok=True)
    with open(os.path.join(REVIEW_DIR, "review.jsonl"), "w", encoding=ENC, newline="\n") as f:
        for t in tickets:
            f.write(json.dumps({k: t.get(k) for k in (
                "review_id", "ticket_key", "group_ids", "kind", "frames", "batch_assets", "affected_render_units",
                "affected_frames", "claim", "forms", "reason", "evidence", "possible_actions", "downstream_blocked",
                "released_despite", "scope")}, ensure_ascii=False) + "\n")
    dp = os.path.join(REVIEW_DIR, "decisions.tsv")
    if not os.path.exists(dp):
        with open(dp, "w", encoding=ENC, newline="\n") as f:
            f.write("\t".join(("review_id", "ticket_key", "decision", "type", "partner", "note", "who", "when"))
                    + "\n")


def write_md(res, tickets):
    dg = res["diagnostics"]
    rp_ = dg["v7_replay"]
    L = ["# HD_PIPELINE_E2E_V1_R3 - сухой план: %s" % res["verdict"], "",
         "Создан %s. Spec R3 `%s` (R2 `%s`, V1 `%s`), relations `%s`. Рендер **%s**, конфигурация заморожена "
         "хэшами. Видеокарта не запускалась, файлов игры и пака план не трогает." % (
             res["created"], res["spec_sha256"][:12], res["r2_spec_sha256"][:12], res["v1_spec_sha256"][:12],
             res["relations_lock_sha256"][:12], res["renderer"]), "", "## Сводка", "", "| что | число |", "|---|---|"]
    rd = dg["released_despite_unresolved"]
    inv = dg["invariant_actions"]
    sc = dg["source_could_change_blocked"]
    for k, v in (("кадров в замыкании", dg["total_closure_frames"]), ("групп связей", dg["relation_groups"]),
                 ("единиц рисования", dg["render_units"]), ("тикетов ревью", dg["review_tickets"]),
                 ("единиц заблокировано", dg["render_units_blocked"]),
                 ("единиц освобождено", dg["render_units_released"]),
                 ("прямых рисунков (заданий)", dg["direct_renders"]["jobs"]),
                 ("точных копий", dg["copies"]),
                 ("выводов всего", "%d %s" % (dg["derived_outputs"]["frames"], dg["derived_outputs"]["by_method"])),
                 ("исполняемых действий", dg["executable_actions"]), ("видов действий", ", ".join(dg["action_types"])),
                 ("отпущено, хотя на кадре открыто решение", "%d" % rd["frames"]),
                 ("действий, не меняющихся ни при каком решении (миров проверено)", "%d (%d)" % (inv["count"],
                                                                                              inv["worlds"])),
                 ("  из них без единого открытого решения на кадре", inv["without_any_open_decision"]),
                 ("заблокировано: решение может сменить основу или единицу", "%d %s" % (sc["frames"],
                                                                                        sc["by_reason"])),
                 ("только план: структура / рельеф", "%d / %d" % (dg["plan_only_structural"],
                                                                 dg["plan_only_terrain"])),
                 ("DERIVE_NOT_VERIFIED", dg["derive_not_verified"]), ("RENDERER_UNSUPPORTED",
                                                                      dg["renderer_unsupported"]),
                 ("IDENTITY_MISSING", dg["identity_missing"])):
        L.append("| %s | %s |" % (k, v))
    L += ["", "Статусы кадров: %s." % dg["frame_status"], "Тикеты по виду: %s." % dg["tickets_by_kind"],
          "Отпущено при открытом решении, по типу: %s." % rd["by_type"],
          "Якорь сменён правилом S2: %s." % (", ".join("%s (был %s)" % (x["anchor"], x["was"])
                                                      for x in dg["anchors_s2"]) or "нет"),
          "Сверка с V7: совпало %d, потеряно %d, ослаблено %d, тип другой %s - тикет V7_REPLAY_DIFFERS." % (
              rp_["same"], len(rp_["lost"]), len(rp_["weaker"]), rp_.get("type_changed", [])),
          "Если решения принимать только по одному (сравнение, не план): заданий %d, выводов %s; из этого в мирах, "
          "где решений принято несколько, становится неверным: %s." % (
              dg["single_reading"]["jobs"], dg["single_reading"]["derived"],
              dg["single_reading"]["unsafe_in_combined_worlds"] or "ничего"),
          "", "## Ворота", "", "| ворота | значение | итог | что |", "|---|---|---|---|"]
    for g in res["gates"]:
        L.append("| %s | %d | %s | %s |" % (g["gate"], g["value"], g["status"], "; ".join(g["detail"][:5]) or "-"))
    L += ["", "## Группы без оси A", "", "| группа | кадров | якорь (единица) | связи блокируют якорь | ещё тикеты якоря |",
          "|---|---|---|---|---|"]
    for x in dg["no_axis_a_groups"]:
        L.append("| %s | %d | %s (%s %s) | %s | %s |" % (x["group_id"], x["frames"], x["anchor"],
                                                       x["anchor_unit_kind"], len(x["anchor_unit"]),
                                                       ", ".join(x["anchor_relation_blocks"]) or "-",
                                                       ", ".join(x["anchor_other_tickets"]) or "-"))
    L += ["", "## Ассеты партии", "",
          "| ассет | категория | статус | производитель | якорь | блокирует (код: тикеты) | отпущено при |",
          "|---|---|---|---|---|---|---|"]
    for f in sorted((f for f in res["frames"] if f["batch"]),
                    key=lambda f: (E1.CATEGORIES.index(f["category"]), f["asset_id"])):
        aff = "; ".join("%s: %s" % (a["code"], ",".join(a["by"][:3])) for a in f["affects"][:3])
        L.append("| %s | %s | %s | %s | %s | %s | %s |" % (
            f["asset_id"], f["category"], f["status"], f["producer"] or "-", f["render_anchor"],
            aff or (", ".join(f["cause"][:3]) or "-"), ", ".join(f["released_despite"][:4]) or "-"))
    L += ["", "## Задания рендера", "", "| задание | якорь | правило | опознание (источник) | зерно |",
          "|---|---|---|---|---|"]
    for j in res["jobs"]:
        L.append("| %s | %s | %s | %s (%s) | %d |" % (j["job_id"], j["render_asset"], j["anchor_rule"],
                                                     j["identity"], j["identity_source"], j["seed"]))
    L += ["", "## Исполняемые выводы", "", "| кадр | как | из | группа | отпущено при |", "|---|---|---|---|---|"]
    for f in res["frames"]:
        if f["status"] == "DERIVE":
            L.append("| %s | %s | %s | %s | %s |" % (f["asset_id"], f["method"], f["from"], f["relation_group_id"],
                                                     ", ".join(f["released_despite"]) or "-"))
    L += ["", "Все тикеты - `%s`; решения человека - `decisions.tsv` там же." % res["tickets_file"]]
    with open(p("plan.md"), "w", encoding=ENC, newline="\n") as f:
        f.write("\n".join(L) + "\n")


def do_check():
    sp = load_spec()
    check_frozen(sp)
    print("R3: V7, spec V1, R2 и R3, relations и конфигурация рендера целы")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("spec", "plan", "check"))
    a = ap.parse_args()
    {"spec": do_spec, "plan": do_plan, "check": do_check}[a.cmd]()


if __name__ == "__main__":
    main()
