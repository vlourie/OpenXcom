#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""HD_PIPELINE_E2E_V1_R2 - сухой план E2E с ревью на уровне единиц рисования (специалист 03.10, передал Vitali в
чате). Замыкание и утверждения V7 - те же, что у HD_PIPELINE_E2E_V1 (hd-e2e-v1/relations.lock.json, не
пересчитываются); меняется только граница ревью в планировщике. V7, правила связей, families.json, рендер и онтология
опознания не меняются. Видеокарта не нужна.

    spec    -> hd-e2e-v1/r2/spec.json (неизменяемый: второй раз - только тот же)
    plan    -> hd-e2e-v1/r2/plan.json, plan.md; тикеты ревью -> review/e2e-v1/review.jsonl (+ decisions.tsv - шапка
               для решений человека, пишется один раз и не перезаписывается)
    check   V7, spec V1 и R2, relations и код рендера не изменились

Правила производства R2 (PRODUCTION_RULES_R2):
  - RELATION_GROUP - связная компонента автоматических связей V7 (существование STRONG, тип TYPE_STRONG,
    production): только знание о родстве и аудит, не единица ревью;
  - RENDER_UNIT - кадры, связанные автоматическими COMPOSITE_PART / STRUCTURAL_MODULAR / ANIMATION_FAMILY: рисуются
    или выводятся вместе. Дерево производства как в V1: якорь группы (кадр без исходящей направленной связи; набор
    оригинала, затем меньший ключ) рисуется, остальное выводится по автоматическим связям от основы к выводимому;
  - REVIEW_UNIT (тикет) - один открытый вопрос: неавтоматическое утверждение V7 (CANDIDATE, TYPE_OPEN, не production),
    улика правила, роль без цели или кандидат роли, неполный составной, обратный вывод, вторая единица рисования,
    спорный конвейер, нет оси A, нет своего опознания у якоря. Тикет блокирует единицы рисования кадров, которых
    касается, и всё, что из них выводится (вниз по дереву производства). Остальные единицы той же группы идут дальше,
    если вся их цепочка до якоря - автоматика V7 и ни один кадр цепочки не заблокирован;
  - якорь рисуется только со СВОИМ опознанием (ось A этого кадра, answers_vitali.tsv V7); нет - тикет
    IDENTITY_MISSING, текст другого кадра не берётся;
  - выводы: COPY и MIRROR_FLIP исполняются; DERIVE_RECOLOR и DERIVE_MIRROR_RECOLOR - DERIVE_NOT_VERIFIED (до
    DERIVE_RECOLOR_ACCEPTANCE_V2), STATE - STATE_NOT_IMPLEMENTED; всё, что выводится из них, - BLOCKED_UPSTREAM;
  - OBJECT_PIPELINE исполняется; STRUCTURAL_PIPELINE и TERRAIN_PIPELINE - только план; NONE - файлов нет;
  - рендер PHOTO_STRUCT_V1, конфигурация заморожена хэшами кода и замка модели: только одиночный кадр; единица из
    нескольких кадров - RENDERER_UNSUPPORTED.
  Освобождённая единица не зависит от решений НИЖЕ себя по дереву. Решение по кадру ниже может сказать, что этот кадр
  (а с ним и основа дерева) выводится из чужого кадра; такие освобождённые единицы считаются отдельно (upstream_exposed)
  и показываются, но не блокируются - правило специалиста: блокировать A, B и зависящее от них вниз.
VERIFIED ставит только человек; генерацию запускает команда специалиста, не этот модуль.

    py -3.13 tools/hdart/hd_e2e_v1_r2.py <команда>
"""
import argparse
import hashlib
import json
import os
import sys
import time
from collections import Counter, defaultdict, deque

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hd_e2e_v1 as E1                            # noqa: E402
import identity_routing as ir                     # noqa: E402
import relation_discovery_v3 as v3                # noqa: E402
import relation_discovery_v4 as v4                # noqa: E402
import relation_taxonomy as tx                    # noqa: E402
import relation_safety_v7_prep as s7              # noqa: E402

ENC = ir.ENC
PROFILE = "HD_PIPELINE_E2E_V1_R2"
OUT = os.path.join(E1.OUT, "r2")
REVIEW_DIR = os.path.join("art", "objects", "generation", "review", "e2e-v1")
OUTPUT_DIR = os.path.join(E1.OUT, "output")
SELF = "tools/hdart/hd_e2e_v1_r2.py"
SEED0 = 5200

RENDERER = "PHOTO_STRUCT_V1"
RENDERER_SUPPORTS = ("SINGLE",)
RENDERER_FILES = ("tools/hdart/photo_struct_render.py", "tools/hdart/render_chunks.py", "tools/hdart/struct_probe.py",
                  "tools/hdart/struct_guide.py", "tools/hdart/photo_base.py", "tools/hdart/photo_render.py",
                  "tools/hdart/photo_accept.py", "tools/hdart/model_lock.py", "tools/hdart/obj_gen_spec.py",
                  "art/models/qwen21_turbo_rgba.lock.json")
RENDER_TOGETHER = E1.RENDER_TOGETHER
DERIVE_METHOD = E1.DERIVE_METHOD
METHOD_STATUS = {"COPY": "DERIVE", "MIRROR_FLIP": "DERIVE",
                 "DERIVE_RECOLOR": "DERIVE_NOT_VERIFIED", "DERIVE_MIRROR_RECOLOR": "DERIVE_NOT_VERIFIED",
                 "STATE": "STATE_NOT_IMPLEMENTED"}
METHOD_NOTE = {"DERIVE_NOT_VERIFIED": "RECOLOR relation VERIFIED, реализация DERIVE_RECOLOR NOT VERIFIED "
                                      "(acc-5e9f63c421c0 FRNITURE 9) - до DERIVE_RECOLOR_ACCEPTANCE_V2",
               "STATE_NOT_IMPLEMENTED": "конвейера износа нет (obj_generation: STATE_VARIANT - EXCLUDE)"}
PIPE_SCOPE = {"OBJECT_PIPELINE": "EXECUTE", "STRUCTURAL_PIPELINE": "PLAN_ONLY_STRUCTURAL",
              "TERRAIN_PIPELINE": "PLAN_ONLY_TERRAIN", "NONE": "NO_OUTPUT"}
EXEC = ("RENDER", "DERIVE")
PLAN_ONLY = ("PLAN_ONLY_STRUCTURAL", "PLAN_ONLY_TERRAIN", "NO_OUTPUT")
STATUSES = EXEC + PLAN_ONLY + ("BLOCKED_REVIEW", "BLOCKED_UPSTREAM", "DERIVE_NOT_VERIFIED", "STATE_NOT_IMPLEMENTED",
                               "RENDERER_UNSUPPORTED")
# тикет: что человек может решить
ACTIONS = {"UNRESOLVED_RELATION": ["CONFIRM_TYPE", "OTHER_TYPE", "NO_RELATION"],
           "EVIDENCE": ["NO_RELATION", "NAME_RELATION (партнёр, тип)"],
           "SELF_ROLE_CANDIDATE": ["CONFIRM_ROLE (партнёр)", "REJECT_ROLE"],
           "SELF_ROLE_UNRESOLVED": ["NAME_BASE", "REJECT_ROLE"],
           "COMPOSITE_INCOMPLETE": ["EXTEND_UNIT", "SPLIT_QUEUE_ITEM"],
           "REVERSE_DERIVATION": ["CHOOSE_BASE", "RENDER_SEPARATELY"],
           "SECOND_RENDER_UNIT": ["DERIVE_FROM_ANCHOR", "SPLIT_RELATION"],
           "NO_ROOT": ["CHOOSE_BASE"],
           "NO_AXIS_A": ["SET_AXIS_A"], "PIPELINE_REVIEW": ["SET_AXIS_A"], "PIPELINE_CONFLICT": ["SET_AXIS_A"],
           "IDENTITY_MISSING": ["PROVIDE_IDENTITY (ворота опознания, своя карточка)"],
           "AUTO_EDGE_OUTSIDE_CLOSURE": ["EXTEND_CLOSURE"], "UNMAPPED_TYPE": ["MAP_TYPE"],
           "V7_REPLAY_DIFFERS": ["CHOOSE_TYPE (holdout V7 или замыкание)"]}
# решение по кадру t может сменить основу дерева над ним: кадр окажется выводом из чужого кадра
RESOURCING = ("EVIDENCE", "SELF_ROLE_CANDIDATE", "SELF_ROLE_UNRESOLVED")

GATES = (("dangerous_independent_render", "кадр задания рендера с неавтоматическим утверждением, уликой, ролью без "
                                          "цели или автоматической связью наружу группы"),
         ("relation_decision_lost_in_handoff", "утверждение V7 по кадру группы, которого нет в плане: автоматическое "
                                               "нарушено (разные единицы для рисуемых вместе, исполняемые кадры не из "
                                               "одного якоря), неавтоматическое - не в тикете или его кадр исполняется; "
                                               "плюс расхождения с замороженным V7"),
         ("wrong_pipeline_target", "задание рендера не у OBJECT_PIPELINE или ось A не OBJECT / OBJECT_PART; "
                                   "исполняемый файл у NOT_OBJECT"),
         ("missing_expected_output", "кадр без статуса из списка или исполняемый без производителя; кадр партии вне "
                                     "плана"),
         ("unexpected_duplicate_creative_render", "больше одного задания в группе связей, кадр в двух заданиях, "
                                                  "выведенный кадр в задании"),
         ("render_group_anchor_violation", "задание не у якоря группы; вывод не из единицы якоря"),
         ("unresolved_relation_used_for_render", "исполняемый кадр задет тикетом или выведен по неавтоматической связи"),
         ("review_dependency_leak", "исполняемый кадр, в цепочке которого до якоря (с соседями по единице) есть "
                                    "кадр, задетый тикетом, или неисполняемый кадр"),
         ("identity_borrowed_from_other_asset", "задание без своего опознания или с опознанием другого кадра"),
         ("wrongly_sent_to_object_renderer", "в задании рендера кадр с конвейером не OBJECT_PIPELINE"))
DIAGNOSTICS = ("total_closure_frames", "relation_groups", "render_units", "review_tickets", "render_units_blocked",
               "render_units_released", "direct_renders", "derived_outputs", "copies", "plan_only_structural",
               "plan_only_terrain", "no_output", "derive_not_verified", "state_not_implemented",
               "renderer_unsupported", "identity_missing", "upstream_exposed", "executable_actions", "v7_replay")
BODY = ("profile", "decision", "v1_spec_sha256", "relations_lock_sha256", "production_rules", "method_status",
        "pipe_scope", "renderer", "gates", "diagnostics", "review_dir", "output_dir", "seed0", "v7")


def p(*a):
    return os.path.join(OUT, *a)


# ---------------------------------------------------------------- spec

def renderer_config():
    return {f: E1.file_sha(f) for f in RENDERER_FILES}


def spec_body(d, ver, sp1):
    return {"profile": PROFILE,
            "decision": "специалист 03.10, передал Vitali в чате: relation group != review group; ревью на уровне "
                        "единиц рисования и зависимостей; рендер PHOTO_STRUCT_V1 с замороженной конфигурацией; "
                        "опознание только своё; DERIVE_RECOLOR не исполняется; STRUCTURAL и TERRAIN - только план. "
                        "V7, правила связей, families.json, рендер, онтология опознания не меняются",
            "v1_spec_sha256": sp1["sha256"], "relations_lock_sha256": E1.file_sha(E1.p("relations.lock.json")),
            "production_rules": __doc__.split("Правила производства R2")[1].split("VERIFIED ставит")[0].strip(),
            "method_status": METHOD_STATUS, "pipe_scope": PIPE_SCOPE,
            "renderer": {"name": RENDERER, "supports": list(RENDERER_SUPPORTS), "config_sha256": renderer_config(),
                         "runner": "render_chunks.py -> photo_struct_render.py (gpuq), вариант C"},
            "gates": [{"gate": g, "need": 0, "def": t} for g, t in GATES], "diagnostics": list(DIAGNOSTICS),
            "review_dir": REVIEW_DIR.replace(os.sep, "/"), "output_dir": OUTPUT_DIR.replace(os.sep, "/"),
            "seed0": SEED0, "v7": E1.v7_ref(d, ver)}


def do_spec():
    d, _h, ver = E1.v7_state()
    sp1 = E1.load_spec()
    body = spec_body(d, ver, sp1)
    os.makedirs(OUT, exist_ok=True)
    sp = p("spec.json")
    if os.path.exists(sp):
        old = ir.load_json(sp)
        if old["sha256"] != E1.jsha({k: body[k] for k in BODY}):
            raise SystemExit("spec.json R2 уже записан и отличается - спецификация не переписывается: %s" % sp)
        print("spec.json R2 тот же: %s" % old["sha256"][:12])
        return old
    body["created"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    body["code_sha256"] = E1.file_sha(SELF)
    body["sha256"] = E1.jsha({k: body[k] for k in BODY})
    ir.dump_json(sp, body)
    print("spec.json R2 %s: рендер %s, файлов конфигурации %d" % (body["sha256"][:12], RENDERER, len(RENDERER_FILES)))
    return body


def load_spec():
    sp = ir.load_json(p("spec.json"))
    if E1.jsha({k: sp[k] for k in BODY}) != sp["sha256"]:
        raise SystemExit("spec.json R2 изменён после записи")
    return sp


def check_frozen(sp):
    E1.v7_state()
    sp1 = E1.load_spec()
    if sp1["sha256"] != sp["v1_spec_sha256"]:
        raise SystemExit("spec V1 не тот, на котором записан R2")
    if E1.file_sha(E1.p("relations.lock.json")) != sp["relations_lock_sha256"]:
        raise SystemExit("relations.lock.json изменён после spec R2")
    bad = [f for f, h in sp["renderer"]["config_sha256"].items() if E1.file_sha(f) != h]
    if bad:
        raise SystemExit("конфигурация рендера изменена после spec R2: %s" % ", ".join(bad))
    return sp1


# ---------------------------------------------------------------- планировщик группы

def ticket_key(t):
    return hashlib.sha256(json.dumps([t["kind"], sorted(t["frames"]), t.get("claim_key")], ensure_ascii=False)
                          .encode("utf-8")).hexdigest()[:12]


def replay_pairs(replay):
    """Сверка с V7 (hd_e2e_v1.v7_replay): пары, по которым утверждение плана не то, что в holdout V7 ->
    [(пара, строка сверки)]. Строка: '<кадр> <тип> <A~B>/<существование>[ -> ...]'."""
    out = []
    for kind in ("lost", "weaker", "stronger", "type_changed"):
        for s in replay.get(kind, []):
            pair = s.split()[2].split("/")[0].split("~")
            out.append((pair, "%s: %s" % (kind, s)))
    return out


def plan_group_r2(members, C, rowmap, origin, comp_items, ident, supports=RENDERER_SUPPORTS, replay=()):
    """Одна группа связей: единицы рисования, дерево производства от якоря, тикеты и статус каждого кадра.
    rowmap: кадр -> {semantic_kind, semantic_eff, surface, pipeline_why}; ident: кадр -> своё опознание (ось A);
    replay - replay_pairs: расхождения с holdout V7, каждое - тикет на кадры пары."""
    import routing_model_v8 as v8
    M = set(members)
    claims = {}
    for a in members:
        for c in C.of(a):
            claims[(c["group"], tuple(c["pair"]))] = c
    auto = [c for c in claims.values() if tx.auto_claim(c)]
    other = sorted((c for c in claims.values() if not tx.auto_claim(c)), key=lambda c: (c["group"], c["pair"]))
    tickets, lost = [], []

    def T(kind, frames, reason, claim=None, evidence=None):
        fs = sorted(set(frames) & M)
        if not fs:
            return
        tickets.append({"kind": kind, "frames": fs, "reason": reason, "claim": claim,
                        "claim_key": [claim["group"], list(claim["pair"])] if claim else None,
                        "evidence": evidence or [], "possible_actions": ACTIONS[kind]})
    for c in auto:
        if not set(c["pair"]) <= M:
            T("AUTO_EDGE_OUTSIDE_CLOSURE", c["pair"], "%s %s вне замыкания" % (c["type"], "~".join(c["pair"])))
        elif c["type"] not in RENDER_TOGETHER and c["type"] not in DERIVE_METHOD:
            T("UNMAPPED_TYPE", c["pair"], "тип %s не отображён в производство" % c["type"])
            lost.append("UNMAPPED_TYPE %s %s" % (c["type"], "~".join(c["pair"])))
    for c in other:
        a0 = next(a for a in c["pair"] if a in M)
        cv = E1.claim_view(c, a0)
        cv["actions_v7"] = {a: s7.action_of(c, a) for a in c["pair"]}
        T("UNRESOLVED_RELATION", c["pair"], "%s %s %s/%s%s" % (
            c["type"], "~".join(c["pair"]), c["existence"].split("_")[-1], c["type_level"].split("_")[-1],
            "" if c.get("production", True) else " не production"), claim=cv,
          evidence=cv["detectors"] + cv["why_open"])
    for pair, s in replay:
        T("V7_REPLAY_DIFFERS", pair, "утверждение плана не то, что в holdout V7: %s" % s)
    for a in members:
        if C.evidence.get(a):
            ev = [{k: v for k, v in x.items() if isinstance(v, (str, int, float))} for x in C.evidence[a]]
            T("EVIDENCE", [a], "улика %s" % sorted({x["rule"] for x in C.evidence[a]}), evidence=ev)
        for x in C.self_roles.get(a, []):
            if x["level"] not in v3.BINDING:
                T("SELF_ROLE_CANDIDATE", [a], "роль %s %s" % (x["type"], x["level"]), evidence=[x.get("rule", "")])
            elif not any(c["type"] == x["type"] and a in c["pair"] for c in auto):
                T("SELF_ROLE_UNRESOLVED", [a], "роль %s %s без цели: основы нет" % (x["type"], x["level"]),
                  evidence=[x.get("rule", "")])
    # единицы рисования
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
    # дерево производства
    adj = defaultdict(list)
    directed_src = set()
    for c in auto:
        if c["type"] not in DERIVE_METHOD or not set(c["pair"]) <= M:
            continue
        meth = DERIVE_METHOD[c["type"]]
        if c["type"] in v4.SYMMETRIC:
            a, b = c["pair"]
            adj[a].append((b, c["type"], meth))
            adj[b].append((a, c["type"], meth))
        else:
            src, tgt = c["source"].upper(), c["target"].upper()
            adj[tgt].append((src, c["type"], meth))
            directed_src.add(src)
    roots = sorted(k for k in members if k not in directed_src)
    if not roots:
        T("NO_ROOT", members, "у всех кадров есть основа - цикл направленных связей")
        roots = sorted(members)
    anchor = min(roots, key=lambda k: (k.split(":")[0] not in origin, k))
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
    # конвейер по кадру: ось A (своя или унаследованная), роли V7
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
    # тикеты одного вопроса - один (одинаковый вид, кадры и утверждение)
    seen, tk = set(), []
    for t in tickets:
        t["ticket_key"] = ticket_key(t)
        if t["ticket_key"] not in seen:
            seen.add(t["ticket_key"])
            tk.append(t)
    tickets = tk
    touched = defaultdict(list)
    for t in tickets:
        for k in t["frames"]:
            touched[k].append(t["ticket_key"])
    blocked0 = {unit_of[k] for k in touched}
    st, cause = statuses(order, prod, units, unit_of, pipes, touched, blocked0, supports)
    # тикет: какие единицы задевает и какие блокирует ниже по дереву
    for t in tickets:
        aff = sorted({unit_of[k] for k in t["frames"]})
        t["affected_render_units"] = aff
        t["downstream_blocked"] = sorted({unit_of[y] for y in members if st[y] == "BLOCKED_UPSTREAM" and
                                          t["ticket_key"] in cause[y]} - set(aff))
        t["scope"] = sorted({PIPE_SCOPE.get(pipes[k], pipes[k]) for k in t["frames"]})
    # освобождённое, над которым есть решение, способное сменить основу дерева
    exposed = defaultdict(set)
    for t in tickets:
        for k in t["frames"]:
            act = (t["claim"] or {}).get("actions_v7", {}).get(k)
            if t["kind"] in RESOURCING or (t["kind"] == "UNRESOLVED_RELATION" and act != "CANONICAL"):
                for x in E1.chain_of(prod, k)[1:]:
                    for y in units[unit_of[x]]["frames"]:
                        if st[y] in EXEC:
                            exposed[y].add(t["ticket_key"])
    for u in units.values():
        u["status"] = sorted({st[k] for k in u["frames"]})
    return {"members": sorted(members), "anchor": anchor, "roots": roots, "units": units, "unit_of": unit_of,
            "prod": prod, "pipes": pipes, "status": st, "cause": cause, "tickets": tickets, "lost": lost,
            "exposed": {k: sorted(v) for k, v in exposed.items()}, "auto_claims": len(auto)}


def statuses(order, prod, units, unit_of, pipes, touched, blocked0, supports):
    """Статус кадра по дереву сверху вниз; единица исполняется только целиком (до неподвижной точки)."""
    forced = {}
    for _ in range(len(order) + 1):
        st, cause = {}, {}
        for k in order:
            u = unit_of[k]
            pr_ = prod.get(k)
            x = pr_["from"] if pr_ else None
            if k in forced:
                st[k], cause[k] = forced[k]
            elif u in blocked0 or not pr_:
                st[k] = "BLOCKED_REVIEW"
                cause[k] = sorted({t for y in units[u]["frames"] for t in touched.get(y, [])})
            elif x and st[x] not in EXEC and st[x] not in PLAN_ONLY:
                st[k] = "BLOCKED_UPSTREAM"
                cause[k] = cause[x] if st[x] in ("BLOCKED_REVIEW", "BLOCKED_UPSTREAM") else ["%s@%s" % (st[x], x)]
            elif PIPE_SCOPE.get(pipes[k]) != "EXECUTE":
                st[k], cause[k] = PIPE_SCOPE.get(pipes[k], "BLOCKED_REVIEW"), []
            elif x and st[x] in PLAN_ONLY:
                st[k], cause[k] = "BLOCKED_UPSTREAM", ["%s@%s" % (st[x], x)]
            elif pr_["method"] == "RENDER":
                st[k] = "RENDER" if units[u]["kind"] in supports else "RENDERER_UNSUPPORTED"
                cause[k] = [] if st[k] == "RENDER" else ["%s: рендер умеет %s" % (units[u]["kind"], list(supports))]
            else:
                st[k] = METHOD_STATUS[pr_["method"]]
                cause[k] = [] if st[k] == "DERIVE" else ["%s@%s" % (st[k], k)]
        changed = False
        for u, un in units.items():
            fs = un["frames"]
            bad = [k for k in fs if st[k] not in EXEC]
            for k in fs:
                if bad and st[k] in EXEC:
                    forced[k] = ("BLOCKED_UPSTREAM", cause[bad[0]] or ["unit %s: %s %s" % (u, bad[0], st[bad[0]])])
                    changed = True
        if not changed:
            return st, cause
    raise SystemExit("статусы не сошлись")


# ---------------------------------------------------------------- ворота

def chain_frames(g, k):
    """Кадр, его соседи по единице, предки по дереву и их соседи по единице."""
    out = set()
    for x in E1.chain_of(g["prod"], k):
        out |= set(g["units"][g["unit_of"][x]]["frames"])
    return out


def gates_r2(groups, jobs, C, replay=None, batch=()):
    """Десять ворот, считаются заново по статусам, заданиям и утверждениям V7, не по причинам планировщика."""
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
            bad = [c for c in C.of(k) if not tx.auto_claim(c) or not set(c["pair"]) <= M]
            roles = [x for x in C.self_roles.get(k, []) if not any(
                c["type"] == x["type"] and tx.auto_claim(c) and set(c["pair"]) <= M for c in C.of(k))]
            if bad or C.evidence.get(k) or roles:
                hit("dangerous_independent_render", k)
            if g["status"].get(k) != "RENDER" or g["prod"].get(k, {}).get("method") != "RENDER":
                hit("unexpected_duplicate_creative_render", "derived-in-render %s" % k)
            if g["pipes"].get(k) != "OBJECT_PIPELINE":
                hit("wrongly_sent_to_object_renderer", "%s %s" % (k, g["pipes"].get(k)))
                hit("wrong_pipeline_target", "job %s %s" % (k, g["pipes"].get(k)))
            if g.get("kinds", {}).get(k, "OBJECT") not in ("OBJECT", "OBJECT_PART"):
                hit("wrong_pipeline_target", "axis A %s %s" % (k, g["kinds"][k]))
    job_units = {(j["group_id"], g_u) for j in jobs for g_u in {gby[j["group_id"]]["unit_of"][j["render_asset"]]}}
    for g in groups:
        M = set(g["members"])
        tk_claims = {tuple([t["claim_key"][0]] + sorted(t["claim_key"][1])) for t in g["tickets"] if t["claim_key"]}
        touched = {k for t in g["tickets"] for k in t["frames"]}
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
                if k in touched:
                    hit("unresolved_relation_used_for_render", "touched %s" % k)
                leak = sorted(y for y in chain_frames(g, k) if y != k and (y in touched or g["status"].get(y) not in
                                                                             EXEC))
                if leak:
                    hit("review_dependency_leak", "%s <- %s" % (k, ",".join(leak[:3])))
            for c in C.of(k):
                a, b = c["pair"]
                if tx.auto_claim(c):
                    if not set(c["pair"]) <= M:
                        hit("relation_decision_lost_in_handoff", "auto outside %s %s" % (k, "~".join(c["pair"])))
                    elif c["type"] in RENDER_TOGETHER and g["unit_of"][a] != g["unit_of"][b]:
                        hit("relation_decision_lost_in_handoff", "unit split %s %s" % (c["type"], "~".join(c["pair"])))
                else:
                    key = tuple([c["group"]] + sorted(c["pair"]))
                    if key not in tk_claims:
                        hit("relation_decision_lost_in_handoff", "no ticket %s %s" % (c["type"], "~".join(c["pair"])))
                    if any(g["status"].get(y) in EXEC for y in c["pair"] if y in M):
                        hit("relation_decision_lost_in_handoff", "open claim on exec %s %s" % (c["type"],
                                                                                             "~".join(c["pair"])))
        for t in g["lost"]:
            hit("relation_decision_lost_in_handoff", "%s %s" % (g["group_id"], t))
        # исполняемые кадры группы - из одного якоря
        tops = {E1.chain_of(g["prod"], k)[-1] for k in g["members"] if g["status"].get(k) in EXEC}
        if len({g["unit_of"][t] for t in tops}) > 1:
            hit("relation_decision_lost_in_handoff", "two sources in %s" % g["group_id"])
    for k in batch:
        if k not in gid_of:
            hit("missing_expected_output", "batch-not-planned %s" % k)
    if replay:
        st_all = {k: g["status"].get(k) for g in groups for k in g["members"]}
        for pair, s in replay_pairs(replay):
            if s.startswith(("lost", "weaker")) or any(st_all.get(k) in EXEC for k in pair):
                hit("relation_decision_lost_in_handoff", "V7_REPLAY " + s)
    return G, det


# ---------------------------------------------------------------- план

def items_where(inp):
    """items.json: кадр -> место на карте и представитель (src) его предмета очереди."""
    out = {}
    for it in ir.load_json(inp["items"]):
        for k in it.get("keys", []):
            out.setdefault(k.upper(), {"map": it.get("map", ""), "at": it.get("at", []), "rank": it.get("rank"),
                                       "src": [s.upper() for s in it.get("src", [])]})
    return out


def do_plan():
    sp = load_spec()
    sp1 = check_frozen(sp)
    d, h, _ver = E1.v7_state()
    lk, L = E1.load_relations()
    keys = [k.upper() for k in lk["keys"]]
    rpath = lk["files"]["relations"]["path"]
    ax = E1.axis_a()
    batch = [x["asset_id"].upper() for x in sp1["selection"]]
    cat = {x["asset_id"].upper(): x["category"] for x in sp1["selection"]}
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
    rowmap = {r["asset_id"].upper(): r for r in rows}
    origin = {s.upper() for s in pr["origin"]}
    _copies, comp_items = E1.items_index(d["inputs"])
    where = items_where(d["inputs"])
    replay = E1.v7_replay(d, h, C)
    groups = []
    for fs in comps:
        if not set(fs) & set(batch):
            continue
        g = plan_group_r2(fs, C, rowmap, origin, comp_items, ident,
                          replay=[x for x in replay_pairs(replay) if set(x[0]) & set(fs)])
        g["group_id"] = "g:" + g["anchor"]
        g["batch_keys"] = sorted(set(fs) & set(batch))
        g["kinds"] = {k: kinds.get(k, "") for k in fs}
        groups.append(g)
    # тикеты: номера по порядку, ключ стабилен
    tickets = []
    for g in sorted(groups, key=lambda g: g["group_id"]):
        for t in sorted(g["tickets"], key=lambda t: (t["kind"], t["frames"])):
            t["review_id"] = "R%05d" % (len(tickets) + 1)
            t["group_id"] = g["group_id"]
            t["batch_assets"] = sorted(set(t["frames"]) & set(batch))
            tickets.append(t)
    rid = {t["ticket_key"]: t["review_id"] for t in tickets}
    # задания
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
                     "map": w.get("map", ""), "at": w.get("at", []), "take": ["%s@0" % a],
                     "seed": SEED0 + n, "outputs": [E1.game_path(k) for k in u["frames"]],
                     "output_dir": OUTPUT_DIR.replace(os.sep, "/")})
        g["job_id"] = jobs[-1]["job_id"]
    # кадры
    frames = []
    for g in groups:
        for k in g["members"]:
            s = g["status"][k]
            pr_ = g["prod"].get(k) or {}
            if s == "RENDER":
                prodr = "RENDER %s" % g["job_id"]
            elif s == "DERIVE":
                prodr = "%s from %s" % (pr_["method"], pr_["from"])
            else:
                prodr = ""
            frames.append({
                "asset_id": k, "file": E1.game_path(k), "batch": k in batch, "category": cat.get(k, ""),
                "relation_group_id": g["group_id"], "render_unit": g["unit_of"][k],
                "render_unit_kind": g["units"][g["unit_of"][k]]["kind"], "render_anchor": g["anchor"],
                "semantic_kind": kinds.get(k, ""), "axis_a": "SPECIALIST" if k in kind0 else
                ("INHERITED" if kinds.get(k) else "NONE"), "identity_own": bool(ident.get(k)),
                "pipeline_target": g["pipes"][k], "method": pr_.get("method", "UNREACHED"), "from": pr_.get("from"),
                "via": pr_.get("via"), "status": s, "producer": prodr,
                "cause": [rid.get(c, c) for c in g["cause"][k]],
                "tickets": [t["review_id"] for t in g["tickets"] if k in t["frames"]],
                "upstream_exposed_by": [rid.get(c, c) for c in g["exposed"].get(k, [])],
                "relations": ["%s %s %s/%s%s" % (c["type"], "~".join(c["pair"]), c["existence"].split("_")[-1],
                                                 c["type_level"].split("_")[-1], " AUTO" if tx.auto_claim(c) else "")
                              for c in C.of(k)]})
    G, det = gates_r2(groups, jobs, C, replay, batch)
    for t in tickets:
        t["affected_frames_status"] = dict(Counter(f["status"] for f in frames if f["asset_id"] in t["frames"]))
    diag = diagnostics(groups, jobs, frames, tickets, keys, replay, lk)
    ok = all(v == 0 for v in G.values())
    res = {"profile": PROFILE, "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "spec_sha256": sp["sha256"],
           "v1_spec_sha256": sp1["sha256"], "relations_lock_sha256": sp["relations_lock_sha256"],
           "code_sha256": E1.file_sha(SELF), "renderer": RENDERER,
           "verdict": "PLAN_CONSISTENT" if ok else "PLAN_FAIL",
           "gates": [{"gate": gn, "value": G[gn], "need": 0, "status": "PASS" if G[gn] == 0 else "FAIL",
                      "detail": det[gn][:40]} for gn, _t in GATES],
           "diagnostics": diag, "jobs": jobs, "frames": frames,
           "groups": [{"group_id": g["group_id"], "anchor": g["anchor"], "members": g["members"],
                       "batch_keys": g["batch_keys"], "units": g["units"], "auto_claims": g["auto_claims"],
                       "tickets": [t["review_id"] for t in g["tickets"]]} for g in groups],
           "tickets_file": os.path.join(REVIEW_DIR, "review.jsonl").replace(os.sep, "/")}
    res["jobs_sha256"] = E1.jsha(jobs)
    os.makedirs(OUT, exist_ok=True)
    ir.dump_json(p("plan.json"), res)
    write_review(tickets)
    write_md(res, tickets)
    print("план R2: %s; заданий %d, выводится %d, тикетов %d, единиц освобождено %d из %d; ворота %s" % (
        res["verdict"], len(jobs), diag["derived_outputs"]["frames"], len(tickets),
        diag["render_units_released"], diag["render_units"], {g["gate"]: g["value"] for g in res["gates"]}))


def diagnostics(groups, jobs, frames, tickets, keys, replay, lk):
    st = Counter(f["status"] for f in frames)
    unit_st = {}
    for g in groups:
        for u, un in g["units"].items():
            unit_st[(g["group_id"], u)] = un["status"]
    released = [u for u, s in unit_st.items() if set(s) <= set(EXEC)]
    blocked = [u for u, s in unit_st.items() if set(s) & {"BLOCKED_REVIEW", "BLOCKED_UPSTREAM"}]
    der = Counter(f["method"] for f in frames if f["status"] == "DERIVE")
    exposed = [f["asset_id"] for f in frames if f["upstream_exposed_by"]]
    batch_st = {f["asset_id"]: f["status"] for f in frames if f["batch"]}
    cats = defaultdict(list)
    for f in frames:
        if f["batch"]:
            cats[f["category"]].append("%s:%s" % (f["asset_id"], f["status"]))
    return {"total_closure_frames": len(keys), "closure_complete": lk["closed"],
            "relation_groups": len(groups), "render_units": len(unit_st),
            "review_tickets": len(tickets), "tickets_by_kind": dict(Counter(t["kind"] for t in tickets)),
            "tickets_execute_scope": sum(1 for t in tickets if "EXECUTE" in t["scope"]),
            "render_units_blocked": len(blocked), "render_units_released": len(released),
            "unit_status": dict(Counter("+".join(s) for s in unit_st.values())),
            "frame_status": dict(st),
            "direct_renders": {"jobs": len(jobs), "frames": sum(len(j["render_unit"]) for j in jobs),
                               "assets": [j["render_asset"] for j in jobs]},
            "derived_outputs": {"frames": sum(der.values()), "by_method": dict(der)},
            "copies": der.get("COPY", 0),
            "plan_only_structural": st.get("PLAN_ONLY_STRUCTURAL", 0), "plan_only_terrain": st.get("PLAN_ONLY_TERRAIN",
                                                                                                     0),
            "no_output": st.get("NO_OUTPUT", 0), "derive_not_verified": st.get("DERIVE_NOT_VERIFIED", 0),
            "state_not_implemented": st.get("STATE_NOT_IMPLEMENTED", 0),
            "renderer_unsupported": st.get("RENDERER_UNSUPPORTED", 0),
            "identity_missing": sum(1 for t in tickets if t["kind"] == "IDENTITY_MISSING"),
            "upstream_exposed": {"frames": len(exposed), "assets": exposed},
            "executable_actions": len(jobs) + sum(der.values()),
            "batch_status": dict(Counter(batch_st.values())), "category_status": dict(cats),
            "v7_replay": replay}


def write_review(tickets):
    os.makedirs(REVIEW_DIR, exist_ok=True)
    with open(os.path.join(REVIEW_DIR, "review.jsonl"), "w", encoding=ENC, newline="\n") as f:
        for t in tickets:
            f.write(json.dumps({k: t[k] for k in ("review_id", "ticket_key", "group_id", "kind", "frames",
                                                  "batch_assets", "affected_render_units", "claim", "reason",
                                                  "evidence", "possible_actions", "downstream_blocked", "scope",
                                                  "affected_frames_status")},
                               ensure_ascii=False) + "\n")
    dp = os.path.join(REVIEW_DIR, "decisions.tsv")
    if not os.path.exists(dp):
        with open(dp, "w", encoding=ENC, newline="\n") as f:
            f.write("\t".join(("review_id", "ticket_key", "decision", "type", "partner", "note", "who", "when"))
                    + "\n")


def write_md(res, tickets):
    dg = res["diagnostics"]
    rp_ = dg["v7_replay"]
    L = ["# HD_PIPELINE_E2E_V1_R2 - сухой план: %s" % res["verdict"], "",
         "Создан %s. Spec R2 `%s` (V1 `%s`), relations `%s`. Рендер **%s**, конфигурация заморожена хэшами. "
         "Видеокарта не запускалась, файлов игры и пака план не трогает." % (
             res["created"], res["spec_sha256"][:12], res["v1_spec_sha256"][:12], res["relations_lock_sha256"][:12],
             res["renderer"]), "", "## Сводка", "", "| что | число |", "|---|---|"]
    for k, v in (("кадров в замыкании", dg["total_closure_frames"]), ("групп связей", dg["relation_groups"]),
                 ("единиц рисования", dg["render_units"]), ("тикетов ревью", dg["review_tickets"]),
                 ("  из них в области исполнения (OBJECT)", dg["tickets_execute_scope"]),
                 ("единиц заблокировано ревью или выше по дереву", dg["render_units_blocked"]),
                 ("единиц освобождено (все кадры исполняются)", dg["render_units_released"]),
                 ("заданий рендера (кадров)", "%d (%d)" % (dg["direct_renders"]["jobs"],
                                                          dg["direct_renders"]["frames"])),
                 ("выводится (COPY, MIRROR_FLIP)", "%d %s" % (dg["derived_outputs"]["frames"],
                                                             dg["derived_outputs"]["by_method"])),
                 ("из них копий", dg["copies"]), ("исполняемых действий всего", dg["executable_actions"]),
                 ("только план: структура", dg["plan_only_structural"]),
                 ("только план: рельеф", dg["plan_only_terrain"]), ("без файла (NONE)", dg["no_output"]),
                 ("DERIVE_NOT_VERIFIED", dg["derive_not_verified"]),
                 ("STATE_NOT_IMPLEMENTED", dg["state_not_implemented"]),
                 ("RENDERER_UNSUPPORTED", dg["renderer_unsupported"]), ("IDENTITY_MISSING", dg["identity_missing"]),
                 ("освобождённых кадров под решением, способным сменить основу", dg["upstream_exposed"]["frames"])):
        L.append("| %s | %s |" % (k, v))
    L += ["", "Статусы кадров: %s." % dg["frame_status"], "Тикеты по виду: %s." % dg["tickets_by_kind"],
          "Сверка с замороженным V7 (кадры holdout в партии %d): совпало %d, потеряно %d, ослаблено %d, усилено %d, "
          "тип другой %d %s - каждое расхождение тикет V7_REPLAY_DIFFERS." % (
              rp_["holdout_keys"], rp_["same"], len(rp_["lost"]), len(rp_["weaker"]), len(rp_.get("stronger", [])),
              len(rp_.get("type_changed", [])), rp_.get("type_changed", [])),
          "", "## Ворота", "", "| ворота | значение | итог | что |", "|---|---|---|---|"]
    for g in res["gates"]:
        L.append("| %s | %d | %s | %s |" % (g["gate"], g["value"], g["status"], "; ".join(g["detail"][:5]) or "-"))
    L += ["", "## Ассеты партии", "",
          "| ассет | категория | ось A | конвейер | статус | производитель | единица | группа | тикеты | причина |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for f in sorted((f for f in res["frames"] if f["batch"]),
                    key=lambda f: (E1.CATEGORIES.index(f["category"]), f["asset_id"])):
        L.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            f["asset_id"], f["category"], f["semantic_kind"] or "-", f["pipeline_target"], f["status"],
            f["producer"] or "-", f["render_unit"], f["relation_group_id"],
            ", ".join(f["tickets"][:4]) + (" +%d" % (len(f["tickets"]) - 4) if len(f["tickets"]) > 4 else ""),
            ", ".join(f["cause"][:3]) or "-"))
    L += ["", "## Задания рендера", "", "| задание | якорь | единица | опознание (источник) | зерно |",
          "|---|---|---|---|---|"]
    for j in res["jobs"]:
        L.append("| %s | %s | %s | %s (%s) | %d |" % (j["job_id"], j["render_asset"], ", ".join(j["render_unit"]),
                                                     j["identity"], j["identity_source"], j["seed"]))
    L += ["", "## Исполняемые выводы", "", "| кадр | как | из | группа |", "|---|---|---|---|"]
    for f in res["frames"]:
        if f["status"] == "DERIVE":
            L.append("| %s | %s | %s | %s |" % (f["asset_id"], f["method"], f["from"], f["relation_group_id"]))
    L += ["", "## Тикеты, задевающие кадры партии", "",
          "| тикет | вид | кадры | вопрос | блокирует ниже | область |", "|---|---|---|---|---|---|"]
    for t in tickets:
        if t["batch_assets"]:
            L.append("| %s | %s | %s | %s | %d | %s |" % (t["review_id"], t["kind"], ", ".join(t["frames"][:4]),
                                                         t["reason"][:120], len(t["downstream_blocked"]),
                                                         ",".join(t["scope"])))
    L += ["", "Все тикеты - `%s`; решения человека - `decisions.tsv` там же." % res["tickets_file"]]
    with open(p("plan.md"), "w", encoding=ENC, newline="\n") as f:
        f.write("\n".join(L) + "\n")


def do_check():
    sp = load_spec()
    check_frozen(sp)
    print("R2: V7, spec V1 и R2, relations и конфигурация рендера целы")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("spec", "plan", "check"))
    a = ap.parse_args()
    {"spec": do_spec, "plan": do_plan, "check": do_check}[a.cmd]()


if __name__ == "__main__":
    main()
