#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""HD_PIPELINE_E2E_V1 - сквозная партия HD: ось A -> граф связей V7 -> цель конвейера -> рендер / вывод / ревью ->
генератор -> готовый файл (специалист 03.10, передал Vitali в чате). Этот модуль - сухой прогон до видеокарты. CPU.

V7 (RELATION_SAFETY_MODEL_V7, VERIFIED 03.10) говорит только, ЧЕГО нельзя рисовать отдельно (BLOCK / REVIEW /
CANONICAL); группы, якоря, копии и выводы строит этот слой. V7 не меняется: его код только вызывается, хэши сверяются
с VERIFIED.json и FREEZE.json holdout V7. families.json, генератор, утверждения и production pack не трогаются.

    spec       состав партии, правила производства, ворота -> spec.json (неизменяемый: второй раз - только тот же)
    relations  утверждения V7 по партии с замыканием по автоматическим связям -> relations/ и relations.lock.json
    plan       сухой план: группы, якорь, задания рендера, выводы, ожидаемые файлы, ревью, ворота -> plan.json, plan.md
    check      V7 цел, spec и relations не изменились

Правила производства (PRODUCTION_RULES):
  - связь доводит до производства, только если она автоматическая по V7: существование STRONG, тип TYPE_STRONG,
    production (relation_taxonomy.auto_claim). Группа - связная компонента автоматических связей; замыкание
    relations идёт по ним же, пока не кончатся новые кадры (потолок CLOSURE_MAX - группа на ревью);
  - группа держится на ревью (HELD), если у любого кадра группы есть неавтоматическое утверждение (CANDIDATE или
    TYPE_OPEN - действие V7 REVIEW или BLOCK), улика или связывающая роль без цели, если ось A не решена, если
    конвейер спорный или замыкание не дошло до конца. Это обобщение creative V7 на группу: рисуется только то, о чём
    V7 сказал всё;
  - направленная связь: source выводится из target (target - основа, как action_of CANONICAL). Якорь - кадр без
    исходящей направленной связи внутри группы; из нескольких - сначала набор оригинальных данных игры, затем меньший
    ключ (как routing_model_v8.render_group). Обход от якоря: симметричные связи - в обе стороны, направленные - только
    от основы к выводимому; кто не достигнут - REVERSE_DERIVATION, группа на ревью;
  - кадры, связанные COMPOSITE_PART / STRUCTURAL_MODULAR / ANIMATION_FAMILY, рисуются ОДНИМ заданием (единица
    рисования); остальные типы - вывод из соседа по дереву обхода (COPY, MIRROR_FLIP, DERIVE_RECOLOR,
    DERIVE_MIRROR_RECOLOR) или состояние (STATE - конвейера нет, NOT_IMPLEMENTED);
  - конвейер группы - по оси A кадров партии в ней (routing_model_v8.pipeline_of с ролями V7); родня наследует.
    OBJECT_PIPELINE - рендер; STRUCTURAL / TERRAIN - NOT_IMPLEMENTED_DOWNSTREAM (рендера нет, копии ждут основу);
    NONE - файлов нет; REVIEW - группа на ревью.
VERIFIED ставит только человек; генерацию запускает команда специалиста, не этот модуль.

    py -3.13 tools/hdart/hd_e2e_v1.py <команда>
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
import identity_routing as ir                     # noqa: E402
import relation_holdout_v7 as H                   # noqa: E402  (ставит RAR в порядок детекторов, зерно V7)
import relation_holdout_v4 as hv                  # noqa: E402
import relation_discovery_v3 as v3                # noqa: E402
import relation_discovery_v4 as v4                # noqa: E402
import relation_taxonomy as tx                    # noqa: E402
import relation_safety_v7_prep as s7              # noqa: E402

ENC = ir.ENC
PROFILE = "HD_PIPELINE_E2E_V1"
OUT = os.path.join(ir.PROBES, "hd-e2e-v1")
SELF = "tools/hdart/hd_e2e_v1.py"
V7 = H.OUT
CLOSURE_MAX = 400
ROUNDS_MAX = 8
SEED0 = 5100

# (ключ, категория, почему); ось A кадров holdout V7 - ответы специалиста answers_vitali.tsv, анимация - вне holdout
SELECTION = (
    ("MADDECOR_WASTE:12", "standalone", "единственная связь - никакой; V7 creative"),
    ("FREIGHTER_COMMAND_2:56", "standalone", "V7 creative"),
    ("MOUNTSNOW2:16", "standalone", "V7 creative, растительность"),
    ("XB3BITZ1:26", "exact_copy", "10 EXACT_COPY_PEER STRONG"),
    ("URBAN40K:86", "exact_copy", "7 EXACT_COPY_PEER STRONG"),
    ("OSIRON_FINNIK:41", "exact_copy", "копии и кандидат ASM - группа на ревью"),
    ("XB3BITZ1_MAG:14", "recolor_peer", "RECOLOR_PEER STRONG, render_group V8 с якорем XB3BITZ1:14"),
    ("XOPSMUJUNGLEADDONSIETCH:14", "recolor_peer", "три RECOLOR_PEER STRONG и кандидат примыкания"),
    ("LIGHTNIN_GR:20", "recolor_peer", "11 RECOLOR_OF STRONG: основа для выводов"),
    ("MARSEC_FRN:10", "recolor_peer", "RECOLOR_OF STRONG и кандидат разрушенного вида"),
    ("COMMS:69", "ar2", "только AR2 (TYPE_OPEN)"),
    ("CARGO1:95", "ar2", "только AR2 (TYPE_OPEN)"),
    ("COMPLEXBITSMOON:10", "ar2", "AR2 и основа разрушенного вида STRONG"),
    ("U_DISEC2GOLD:6", "ar2", "AR2, RECOLOR_PEER STRONG, кандидат состояния"),
    ("SEACORAL:4", "state_variant", "DESTROYED_VARIANT_OF STRONG"),
    ("DECORLUX:62", "state_variant", "основа разрушенного вида STRONG (CANONICAL)"),
    ("XBASEN_BITS:22", "state_variant", "разрушенный вид STRONG, копии, RAR"),
    ("CATACDECOR:21", "composite", "COMPOSITE_PART STRONG и EXACT_MIRROR_PEER"),
    ("TRITON_PURR:19", "composite", "OBJECT_PART: COMPOSITE_PART STRONG и копия"),
    ("JUNGLESTYX:32", "composite", "COMPOSITE_PART STRONG и кандидаты ASM2"),
    ("ISLANDURBAN1:15", "structural", "STRUCTURAL_SURFACE, EXACT_MIRROR_PEER"),
    ("WHITEBASES01:90", "structural", "STRUCTURAL_SURFACE, копия"),
    ("U_BITS_VR:1", "structural", "STRUCTURAL_SURFACE, EXACT_MIRROR_PEER"),
    ("REDDESERT:18", "terrain", "TERRAIN_RELIEF, перекраски и разрушенные виды"),
    ("BLACKFOREST:14", "terrain", "TERRAIN_RELIEF, RECOLOR_OF STRONG"),
    ("SEASAND:5", "terrain", "TERRAIN_RELIEF, копия и перекраски"),
    ("CRASHEDPLANE:2", "type_open_review", "OBJECT_PART, только RAR - REVIEW"),
    ("SEASUNK6:26", "type_open_review", "только кандидаты MCD - REVIEW"),
    ("FREIGHTER_CARGO:88", "not_object", "NOT_OBJECT - конвейер NONE"),
    ("COMPUTERS:8", "animation", "MCD anim STRONG, 4 кадра; вне holdout V7 - ось A от специалиста ещё нет"),
)
CATEGORIES = ("standalone", "exact_copy", "recolor_peer", "ar2", "state_variant", "animation", "composite",
              "structural", "terrain", "type_open_review", "not_object")

# тип связи -> что с ней делает производство
RENDER_TOGETHER = {"COMPOSITE_PART": "ASSEMBLY", "STRUCTURAL_MODULAR": "ASSEMBLY", "ANIMATION_FAMILY": "ANIMATION"}
DERIVE_METHOD = {"EXACT_COPY_PEER": "COPY", "ANIMATION_FAMILY_COPY": "COPY", "EXACT_MIRROR_PEER": "MIRROR_FLIP",
                 "RECOLOR_PEER": "DERIVE_RECOLOR", "RECOLOR_OF": "DERIVE_RECOLOR", "DERIVED_FROM": "DERIVE_RECOLOR",
                 "MATERIAL_VARIANT_OF": "DERIVE_RECOLOR", "LOCAL_EDIT_VARIANT": "DERIVE_RECOLOR",
                 "SET_CORRESPONDENCE": "DERIVE_RECOLOR", "NEAR_RECOLOR": "DERIVE_RECOLOR",
                 "ALIGNED_RECOLOR": "DERIVE_RECOLOR", "MIRRORED_RECOLOR": "DERIVE_MIRROR_RECOLOR",
                 "DESTROYED_VARIANT_OF": "STATE", "STATE_VARIANT_OF": "STATE"}
METHOD_STATUS = {"COPY": "ok: побайтовая копия ответа основы",
                 "MIRROR_FLIP": "ok: переворот ответа основы (mirror_frames)",
                 "DERIVE_RECOLOR": "obj_derive recolor; слой DERIVE_RECOLOR провалился в acc-5e9f63c421c0 (FRNITURE 9)",
                 "DERIVE_MIRROR_RECOLOR": "obj_derive mirror (переворот и перенос цвета)",
                 "STATE": "NOT_IMPLEMENTED: конвейера износа нет (obj_generation: STATE_VARIANT - EXCLUDE)"}
PIPE_DOWNSTREAM = {"OBJECT_PIPELINE": "RENDER", "STRUCTURAL_PIPELINE": "NOT_IMPLEMENTED_DOWNSTREAM",
                   "TERRAIN_PIPELINE": "NOT_IMPLEMENTED_DOWNSTREAM", "NONE": "NO_OUTPUT", "REVIEW": "HELD"}
RENDERERS = {
    "qwen21_turbo_rgba": {"status": "APPROVED_FOR_ACCEPTANCE: только простые одиночные предметы (DECISIONS 30.09)",
                          "runner": "acceptance_run.py -> obj_photo.py --batch (gpuq)",
                          "supports": ["SINGLE", "ASSEMBLY", "ANIMATION"],
                          "note": "ASSEMBLY - задание с take по кускам (кровать NUKE3 30 в acc-5e9f63c421c0); "
                                  "ANIMATION - задание anim в obj_photo есть, приёмка его не выпускала"},
    "PHOTO_STRUCT_V1": {"status": "RENDERER_ACCEPTANCE_PASS_ON_VALID_IDENTITY, SYSTEM_ACCEPTANCE_FAIL (DECISIONS 01.10)",
                        "runner": "render_chunks.py -> photo_struct_render.py (gpuq), STRUCT_GUIDE_V1_C",
                        "supports": ["SINGLE"],
                        "note": "один кадр на задание; составного и анимации нет"}}
GATES = (("dangerous_independent_render", 0, "задание рендера, у кадров которого V7 сказал не всё: неавтоматическое "
                                            "утверждение, улика, связь наружу группы"),
         ("relation_decision_lost_in_handoff", 0, "утверждение V7 по кадру группы, которого нет в плане: "
                                                  "автоматическое - ни в выводе, ни в единице рисования; прочее - не в "
                                                  "очереди ревью; плюс побайтовые копии items.json без связи в графе"),
         ("wrong_pipeline_target", 0, "задание рендера не у OBJECT_PIPELINE или у кадра с осью A не OBJECT / "
                                      "OBJECT_PART; файл у NOT_OBJECT"),
         ("missing_expected_output", 0, "до видеокарты: ожидаемый файл без производителя и без причины; после - файла "
                                        "нет или хэш не тот"),
         ("unexpected_duplicate_creative_render", 0, "больше одного задания рендера в группе, кадр с двумя "
                                                     "производителями, выведенный кадр в задании рендера"),
         ("render_group_anchor_violation", 0, "задание рендера не у якоря группы; вывод не из дерева от якоря"))
DIAGNOSTICS = ("direct_renders", "derived_or_copy", "sent_to_review", "edges_reduced_generation",
               "cannot_complete_downstream", "v7_replay")
BODY = ("profile", "decision", "selection", "categories", "production_rules", "derive_method", "method_status",
        "pipe_downstream", "renderers", "renderer", "gates", "diagnostics", "closure_max", "seed0", "v7")

file_sha = s7.file_sha


def p(*a):
    return os.path.join(OUT, *a)


def jsha(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def pk(a, b):
    return tuple(sorted((a.upper(), b.upper())))


# ---------------------------------------------------------------- V7: проверенная модель, только чтение

def v7_state():
    """V7 цел: файлы VERIFIED.json, код FREEZE, живые входы и индексы детекторов. -> (freeze, holdout, verified)."""
    vp = os.path.join(V7, "VERIFIED.json")
    ver = ir.load_json(vp)
    if ver.get("status") != "VERIFIED":
        raise SystemExit("V7 не VERIFIED: %s" % vp)
    bad = [n for n, h in ver["files_sha256"].items() if file_sha(os.path.join(V7, n)) != h]
    if bad:
        raise SystemExit("файлы V7 изменены после VERIFIED: %s" % ", ".join(bad))
    d, h = H.load_freeze(V7), H.load_holdout(V7)
    ch = H.code_changed(d)
    if ch:
        raise SystemExit("код V7 изменён после заморозки: %s" % ", ".join(ch))
    H.live_same(d)
    H.detectors_same(d)
    return d, h, ver


def v7_ref(d, ver):
    return {"verified_sha256": file_sha(os.path.join(V7, "VERIFIED.json")), "freeze_sha256": d["sha256"],
            "freeze_file_sha256": file_sha(os.path.join(V7, "FREEZE.json")),
            "answers_sha256": ver["files_sha256"]["answers_vitali.tsv"], "model": ver["model"],
            "code_sha256": dict(d["code_sha256"])}


def axis_a():
    return {r["asset_id"].upper(): r for r in ir.read_tsv(os.path.join(V7, "answers_vitali.tsv"))}


# ---------------------------------------------------------------- spec

def spec_body(d, ver):
    return {"profile": PROFILE, "decision": "специалист 03.10, передал Vitali в чате: HD_PIPELINE_E2E_V1, 20-30 "
                                            "ассетов, сначала dry-run до видеокарты; V7 неизменен, рендер не меняется "
                                            "во время приёмки; production families.json не трогается",
            "selection": [{"asset_id": k, "category": c, "why": w} for k, c, w in SELECTION],
            "categories": list(CATEGORIES), "production_rules": __doc__.split("Правила производства")[1].split(
                "VERIFIED ставит")[0].strip(), "derive_method": DERIVE_METHOD, "method_status": METHOD_STATUS,
            "pipe_downstream": PIPE_DOWNSTREAM, "renderers": RENDERERS,
            "renderer": "PENDING_SPECIALIST", "gates": [{"gate": g, "need": n, "def": t} for g, n, t in GATES],
            "diagnostics": list(DIAGNOSTICS), "closure_max": CLOSURE_MAX, "seed0": SEED0, "v7": v7_ref(d, ver)}


def do_spec():
    d, _h, ver = v7_state()
    body = spec_body(d, ver)
    missing = [c for c in CATEGORIES if c not in {x["category"] for x in body["selection"]}]
    if missing:
        raise SystemExit("в партии нет категорий: %s" % ", ".join(missing))
    keys = [x["asset_id"].upper() for x in body["selection"]]
    if len(set(keys)) != len(keys) or not 20 <= len(keys) <= 30:
        raise SystemExit("партия: %d ключей, повторы %s" % (len(keys), [k for k, n in Counter(keys).items() if n > 1]))
    os.makedirs(OUT, exist_ok=True)
    sp = p("spec.json")
    if os.path.exists(sp):
        old = ir.load_json(sp)
        if old["sha256"] != jsha({k: body[k] for k in BODY}):
            raise SystemExit("spec.json уже записан и отличается - спецификация не переписывается: %s" % sp)
        print("spec.json тот же: %s" % old["sha256"][:12])
        return old
    body["created"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    body["code_sha256"] = file_sha(SELF)
    body["sha256"] = jsha({k: body[k] for k in BODY})
    ir.dump_json(sp, body)
    print("spec.json %s: %d ассетов, категории %s" % (body["sha256"][:12], len(keys),
                                                      dict(Counter(x["category"] for x in body["selection"]))))
    return body


def load_spec():
    sp = ir.load_json(p("spec.json"))
    if jsha({k: sp[k] for k in BODY}) != sp["sha256"]:
        raise SystemExit("spec.json изменён после записи")
    return sp


# ---------------------------------------------------------------- relations: V7 на партии с замыканием

class Discovery:
    """Замороженные детекторы V7 (как relation_holdout_v7.do_relations) на любых ключах, по кругам."""

    def __init__(self, inp):
        import relation_probe as rp
        import routing_rules_v7 as rr7
        import aligned_recolor_v2 as ar2
        import assembly_discovery_v1 as asm
        import assembly_group_v1 as ag
        import assembly_repeated_v1 as arc
        import two_component_v1 as tc
        self.rp, self.rr7, self.ar2, self.asm, self.ag, self.arc, self.tc = rp, rr7, ar2, asm, ag, arc, tc
        self.inp = inp
        self.ctx = rp.Ctx()
        self.c3 = hv.ctx_v3()
        self.si, self.A = v4.SetIndex(self.c3), asm.Assembly(self.c3)
        cp = s7.ae2.ctx_places()
        self.W, self.Fp, self.G = tc.Windows(cp), arc.Footprints(cp), ag.Groups(cp)

    def run(self, keys, rdir):
        os.makedirs(rdir, exist_ok=True)
        self.rp.discover(self.ctx, keys, rdir)
        rels = ir.load_json(os.path.join(rdir, "relations.json"))["relations"]
        det = self.rr7.detect(self.ctx, self.inp, keys, rels)
        f3 = v3.discover(self.c3, keys)
        f4 = v4.discover(self.c3, keys)
        E = {k: [] for k in H.FOUND_KEYS}
        for a in keys:
            E["AR2"] += self.ar2.discover(self.c3, self.si, a)
            E["ASM"] += self.asm.discover(self.A, a)
            E["AG"] += self.ag.discover(self.G, a)
            E["TC"] += self.tc.discover(self.W, a)
            E["RC"] += self.arc.discover(self.Fp, a)
        return rels, det, f3, f4, E


def merge(acc, part):
    rels, det, f3, f4, E = part
    acc["rels"].update(rels)
    for k in ("by_set", "surf", "variants", "sigs"):
        acc["det"].setdefault(k, {}).update(det[k])
    acc["det"]["origin_sets"] = det["origin_sets"]
    acc["f3"]["edges"] += f3["edges"]
    acc["f3"]["self_roles"].update(f3["self_roles"])
    acc["f4"]["edges"] += f4["edges"]
    for k in H.FOUND_KEYS:
        acc["E"][k] += E[k]


_MCD = []


def mcd_world():
    import map_mockup as mm
    import routing_model_v8 as v8
    if not _MCD:
        _MCD.append(v8.Mcd(mm.World()))
    return _MCD[0]


def build(d, keys, rels_path, det, f3, f4, E, kinds=None):
    """Строки маршрута V8 (как relation_holdout_v4.routing_rows) и утверждения V7 на ключах keys. Ось A kinds
    (ключ -> вид) рёбер не меняет: routing_model_v8.relations читает её только в улике R7t (adjacency_hit, OBJECT),
    поэтому замыкание идёт без неё, а plan ставит ось A партии и унаследованную."""
    import routing_model_v8 as v8
    import routing_rules_v7 as rr7
    kinds = kinds or {}
    inp = dict(d["inputs"])
    inp["relations"] = rels_path
    pr = rr7.prepare(det, inp, keys)
    mcd = mcd_world()
    umap = d["policy"]["relation_unit"]
    rows = [v8.decide(a, kinds.get(a.upper(), ""), pr, umap, v8.facts(mcd, a), {}) for a in keys]
    graph = v8.build_graph(rows, pr, mcd)
    for r in rows:
        r["relations_in"] = graph.relations_in(r["asset_id"])
    C = H.system_claims(rows, f3, f4, E)
    return rows, C, pr


def do_relations():
    sp = load_spec()
    d, _h, _ver = v7_state()
    lock = p("relations.lock.json")
    if os.path.exists(lock):
        raise SystemExit("утверждения уже посчитаны и заморожены: %s" % lock)
    t0 = time.time()
    disc = Discovery(d["inputs"])
    keys = [x["asset_id"] for x in sp["selection"]]
    have = []
    acc = {"rels": {}, "det": {}, "f3": {"edges": [], "self_roles": {}}, "f4": {"edges": []},
           "E": {k: [] for k in H.FOUND_KEYS}}
    rounds, frontier, capped = [], list(keys), False
    for n in range(1, ROUNDS_MAX + 1):
        if not frontier:
            break
        room = CLOSURE_MAX - len(have)
        if len(frontier) > room:
            capped = True
            frontier = frontier[:max(room, 0)]
        if not frontier:
            break
        merge(acc, disc.run(frontier, p("relations", "round_%d" % n)))
        have += frontier
        rp_ = p("relations", "relations.json")
        ir.dump_json(rp_, {"relations": acc["rels"]})
        _rows, C, _pr = build(d, have, rp_, acc["det"], acc["f3"], acc["f4"], acc["E"])
        hs = {k.upper() for k in have}
        nxt = sorted({x for a in have for c in C.of(a) if tx.auto_claim(c) for x in c["pair"]} - hs)
        rounds.append({"round": n, "keys": len(frontier), "total": len(have), "new_partners": len(nxt),
                       "seconds": round(time.time() - t0)})
        print("круг %d: ключей %d, всего %d, новых по автоматическим связям %d, %.0f с" % (
            n, len(frontier), len(have), len(nxt), time.time() - t0), flush=True)
        frontier = nxt
    closed = not frontier and not capped
    files = {"relations": p("relations", "relations.json"), "detectors": p("relations", "detectors.json"),
             "v3": p("relations", "relations_v3.json"), "v4": p("relations", "relations_v4.json"),
             "v7": p("relations", "found_v7.json")}
    ir.dump_json(files["detectors"], acc["det"])
    ir.dump_json(files["v3"], acc["f3"])
    ir.dump_json(files["v4"], acc["f4"])
    ir.dump_json(files["v7"], {"edges": acc["E"]})
    ir.dump_json(lock, {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "spec_sha256": sp["sha256"],
                        "v7_freeze_sha256": d["sha256"], "keys": have, "rounds": rounds, "closed": closed,
                        "unexpanded": frontier, "capped": capped,
                        "files": {k: {"path": v.replace(os.sep, "/"), "sha256": file_sha(v)} for k, v in files.items()}})
    print("замыкание %s за %.0f с: %d ключей; %s" % ("полное" if closed else "НЕ ПОЛНОЕ", time.time() - t0, len(have),
                                                   lock))


def load_relations():
    lk = ir.load_json(p("relations.lock.json"))
    for k, f in lk["files"].items():
        if file_sha(f["path"]) != f["sha256"]:
            raise SystemExit("%s изменён после заморозки" % f["path"])
    L = {k: ir.load_json(f["path"]) for k, f in lk["files"].items()}
    return lk, L


# ---------------------------------------------------------------- plan

def game_path(k):
    s, f = k.split(":")
    return "TERRAIN/%s.PCK/%s.png" % (s.upper(), int(f))


def items_index(inp):
    """items.json снимка V7: ключ -> (картинка-копии, составной-предмет). Копии - кадры одной картинки (sig S...),
    составной - куски предмета очереди в порядке рисования, с местом на карте."""
    copies, comp = {}, {}
    for it in ir.load_json(inp["items"]):
        ks = [k.upper() for k in it.get("keys", [])]
        if it.get("kind") == "составной":
            for k in ks:
                comp[k] = {"rank": it["rank"], "keys": ks, "src": [s.upper() for s in it.get("src", [])],
                           "map": it.get("map", ""), "at": it.get("at", [])}
        else:
            for k in ks:
                copies[k] = set(ks)
    return copies, comp


def claim_view(c, a):
    return {"pair": sorted(c["pair"]), "type": c["type"], "group": c["group"], "existence": c["existence"],
            "type_level": c["type_level"], "source": c["source"], "target": c["target"],
            "auto": tx.auto_claim(c), "action": s7.action_of(c, a.upper()),
            "why_open": list(c.get("type_open_why", [])), "detectors": sorted({e["detector"] for e in c["support"]})}


def auto_pairs(C, keys):
    ks = set(keys)
    return sorted({tuple(c["pair"]) for k in keys for c in C.of(k) if tx.auto_claim(c) and set(c["pair"]) <= ks})


def components(keys, edges):
    par = {k: k for k in keys}

    def f(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x
    for a, b in edges:
        par[f(a)] = f(b)
    comp = defaultdict(list)
    for k in keys:
        comp[f(k)].append(k)
    return [sorted(v) for v in comp.values()]


def chain_of(prod, k):
    out, x, seen = [], k, set()
    while x and x not in seen:
        seen.add(x)
        out.append(x)
        x = prod.get(x, {}).get("from")
    return out


def plan_group(members, C, rowmap, batch, origin, comp_items):
    """Одна группа (связная компонента автоматических связей V7): якорь, единицы рисования, дерево вывода, конвейер,
    причины держать на ревью. Ничего не решает за V7: всё, что V7 оставил неавтоматическим, - на ревью."""
    import routing_model_v8 as v8
    M = set(members)
    claims = {}
    for a in members:
        for c in C.of(a):
            claims[(c["group"], tuple(c["pair"]))] = c
    auto = [c for c in claims.values() if tx.auto_claim(c)]
    other = [c for c in claims.values() if not tx.auto_claim(c)]
    held, lost, review = [], [], []
    for c in auto:
        if not set(c["pair"]) <= M:
            held.append("AUTO_EDGE_OUTSIDE_CLOSURE %s" % "~".join(c["pair"]))
        elif c["type"] not in RENDER_TOGETHER and c["type"] not in DERIVE_METHOD:
            held.append("UNMAPPED_TYPE %s" % c["type"])
            lost.append("UNMAPPED_TYPE %s %s" % (c["type"], "~".join(c["pair"])))
    for c in other:
        for a in c["pair"]:
            if a in M:
                review.append(dict(claim_view(c, a), asset=a))
    if review:
        held.append("REVIEW_CLAIMS %d" % len({tuple(r["pair"]) + (r["group"],) for r in review}))
    for a in members:
        if C.evidence.get(a):
            held.append("EVIDENCE %s %s" % (a, sorted({x["rule"] for x in C.evidence[a]})))
        for x in C.self_roles.get(a, []):
            if x["level"] not in v3.BINDING:
                held.append("SELF_ROLE_CANDIDATE %s %s" % (a, x["type"]))
            elif not any(c["type"] == x["type"] and a in c["pair"] for c in auto):
                held.append("SELF_ROLE_UNRESOLVED %s %s" % (a, x["type"]))      # роль без цели: основы нет
    # единицы рисования: составной, модуль, петля анимации - одним заданием
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
    units = defaultdict(list)
    for k in members:
        units[uf(k)].append(k)
    unit_of = {k: uf(k) for k in members}
    unit_kind = {}
    for u, fs in units.items():
        ts = {c["type"] for c in auto if c["type"] in RENDER_TOGETHER and set(c["pair"]) <= set(fs)}
        unit_kind[u] = "+".join(sorted({RENDER_TOGETHER[t] for t in ts})) or "SINGLE"
        # составной очереди (items.json) обязан войти в единицу целиком, иначе куски нарисуются порознь
        for k in fs:
            it = comp_items.get(k)
            if it and not set(it["keys"]) <= set(fs):
                held.append("COMPOSITE_INCOMPLETE %s: очередь %s, единица %s" % (k, it["keys"], sorted(fs)))
                break
    # вывод: симметричные - в обе стороны, направленные - от основы (target) к выводимому (source)
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
        held.append("NO_ROOT")
        roots = sorted(members)
    anchor = min(roots, key=lambda k: (k.split(":")[0] not in origin, k))
    prod = {}
    q = deque()
    for k in sorted(units[unit_of[anchor]]):
        prod[k] = {"method": "RENDER", "from": None, "via": unit_kind[unit_of[anchor]]}
        q.append(k)
    while q:
        x = q.popleft()
        for y, t, meth in sorted(adj[x]):
            if y not in prod:
                prod[y] = {"method": meth, "from": x, "via": t}
                q.append(y)
    unreached = sorted(M - set(prod))
    if unreached:
        held.append("REVERSE_DERIVATION %s" % ",".join(unreached[:6]))
    for u, fs in units.items():
        if u != unit_of[anchor] and len(fs) > 1:
            held.append("SECOND_RENDER_UNIT %s %s" % (unit_kind[u], ",".join(sorted(fs)[:4])))
    # конвейер: по оси A (своей или унаследованной), как relation_holdout_v4.creative_of
    pipes = {}
    for k in members:
        r = rowmap[k]
        pipes[k] = v8.pipeline_of(r["semantic_eff"], r["surface"], v4.pipe_roles(C, k))[0] if r["semantic_kind"] \
            else "NO_AXIS_A"
    ps = set(pipes.values())
    if "NO_AXIS_A" in ps:
        pipe = "REVIEW"
        held.append("NO_AXIS_A %s" % ",".join(sorted(k for k, v in pipes.items() if v == "NO_AXIS_A")[:6]))
    elif len(ps) > 1:
        pipe = "REVIEW"
        held.append("PIPELINE_CONFLICT %s" % dict(Counter(pipes.values())))
    else:
        pipe = ps.pop()
        if pipe == "REVIEW":
            held.append("PIPELINE_REVIEW %s" % ",".join(rowmap[k]["pipeline_why"] for k in members if k in batch))
    return {"members": sorted(members), "anchor": anchor, "roots": roots,
            "units": {u: {"frames": sorted(fs), "kind": unit_kind[u]} for u, fs in units.items()},
            "unit_of": unit_of, "prod": prod, "pipeline": pipe, "pipelines": pipes, "held": held,
            "review": review, "lost": lost, "auto_claims": len(auto), "auto_types": dict(Counter(c["type"] for c in auto))}


def inherit_kinds(comps, batch_kind):
    """Ось A партии - родне по компоненте автоматических связей; разные виды в компоненте - не наследуется."""
    out = dict(batch_kind)
    for fs in comps:
        ks = {batch_kind[k] for k in fs if k in batch_kind}
        if len(ks) == 1:
            k0 = ks.pop()
            for k in fs:
                out.setdefault(k, k0)
    return out


def do_plan():
    sp = load_spec()
    d, h, ver = v7_state()
    lk, L = load_relations()
    if lk["spec_sha256"] != sp["sha256"]:
        raise SystemExit("relations посчитаны по другой spec")
    keys = [k.upper() for k in lk["keys"]]
    rpath = lk["files"]["relations"]["path"]
    ax = axis_a()
    batch = [x["asset_id"].upper() for x in sp["selection"]]
    cat = {x["asset_id"].upper(): x["category"] for x in sp["selection"]}
    bkind = {k: ax[k]["semantic_kind"] for k in batch if k in ax}
    ident = {k: ax[k]["final_identity"] for k in batch if k in ax}
    _rows0, C0, _pr0 = build(d, keys, rpath, L["detectors"], L["v3"], L["v4"], L["v7"]["edges"], bkind)
    comps0 = components(keys, auto_pairs(C0, keys))
    kinds = inherit_kinds(comps0, bkind)
    rows, C, pr = build(d, keys, rpath, L["detectors"], L["v3"], L["v4"], L["v7"]["edges"], kinds)
    comps = components(keys, auto_pairs(C, keys))
    if sorted(map(tuple, comps)) != sorted(map(tuple, comps0)):
        raise SystemExit("ось A изменила автоматические связи - так быть не должно (relations читает её только в R7t)")
    rowmap = {r["asset_id"].upper(): r for r in rows}
    origin = {s.upper() for s in pr["origin"]}
    copies, comp_items = items_index(d["inputs"])
    replay = v7_replay(d, h, C)
    groups, gid_of = [], {}
    for fs in comps:
        if not set(fs) & set(batch):
            continue
        g = plan_group(fs, C, rowmap, set(batch), origin, comp_items)
        g["group_id"] = "g:" + g["anchor"]
        g["batch_keys"] = sorted(set(fs) & set(batch))
        if set(fs) & {k.upper() for k in lk["unexpanded"]}:
            g["held"].append("CLOSURE_INCOMPLETE")
        if set(fs) & set(replay["keys_differ"]):
            g["held"].append("V7_REPLAY_DIFFERS %s" % ",".join(sorted(set(fs) & set(replay["keys_differ"]))))
        g["identity"] = {k: ident[k] for k in g["batch_keys"] if k in ident}
        g["downstream"] = "HELD" if g["held"] else PIPE_DOWNSTREAM[g["pipeline"]]
        groups.append(g)
        for k in fs:
            gid_of[k] = g["group_id"]
    gby = {g["group_id"]: g for g in groups}
    # задания рендера и ожидаемые файлы
    jobs, expected, review_items = [], [], []
    for n, g in enumerate(sorted((g for g in groups if g["downstream"] == "RENDER"), key=lambda g: g["anchor"]), 1):
        u = g["units"][g["unit_of"][g["anchor"]]]
        it = comp_items.get(g["anchor"])
        idk = g["anchor"] if g["anchor"] in g["identity"] else (sorted(g["identity"])[0] if g["identity"] else "")
        jobs.append({"job_id": "e%02d" % n, "group_id": g["group_id"], "render_asset": g["anchor"],
                     "render_unit": u["frames"], "needs": u["kind"],
                     "take": it["src"] if it and u["kind"] != "SINGLE" else u["frames"],
                     "map": it["map"] if it else "", "at": it["at"] if it else [],
                     "identity": g["identity"].get(idk, ""),
                     "identity_from": idk, "identity_status": "AXIS_A_FINAL_IDENTITY" if idk == g["anchor"] else
                     ("FROM_GROUP_MEMBER %s - якорь не кадр партии, текст про другой кадр группы" % idk if idk else
                      "NONE"), "seed": SEED0 + n, "pipeline": g["pipeline"],
                     "outputs": [game_path(k) for k in u["frames"]]})
        g["job_id"] = "e%02d" % n
    for g in groups:
        review_items += [dict(r, group_id=g["group_id"]) for r in g["review"]]
        down = g["downstream"]
        for k in g["members"]:
            pr_ = g["prod"].get(k)
            r = rowmap[k]
            rec = {"asset_id": k, "file": game_path(k), "group_id": g["group_id"], "batch": k in batch,
                   "category": cat.get(k, ""), "semantic_kind": kinds.get(k, ""),
                   "axis_a": "SPECIALIST" if k in bkind else ("INHERITED" if k in kinds else "NONE"),
                   "semantic_eff": r["semantic_eff"], "pipeline_target": g["pipeline"],
                   "pipeline_own": g["pipelines"][k], "render_group_id": g["group_id"], "render_anchor": g["anchor"],
                   "method": pr_["method"] if pr_ else "UNREACHED", "from": pr_["from"] if pr_ else None,
                   "via": pr_["via"] if pr_ else None,
                   "relations": ["%s %s %s/%s%s" % (c["type"], "~".join(c["pair"]), c["existence"].split("_")[-1],
                                                    c["type_level"].split("_")[-1], " AUTO" if tx.auto_claim(c) else "")
                                 for c in C.of(k)]}
            states = [x for x in chain_of(g["prod"], k) if g["prod"].get(x, {}).get("method") == "STATE"]
            if down == "HELD":
                rec["producer"], rec["reason"] = "HELD", "; ".join(g["held"])
            elif down == "NOT_IMPLEMENTED_DOWNSTREAM":
                rec["producer"], rec["reason"] = down, "нет конвейера %s" % g["pipeline"]
            elif down == "NO_OUTPUT":
                rec["producer"], rec["reason"] = down, "NOT_OBJECT - не рисуется"
            elif rec["method"] == "UNREACHED":
                rec["producer"], rec["reason"] = "", "не достигнут из якоря"
            elif states:
                rec["producer"] = "NOT_IMPLEMENTED_STATE"
                rec["reason"] = "%s; через %s" % (METHOD_STATUS["STATE"], states[-1])
            elif rec["method"] == "RENDER":
                rec["producer"] = "RENDER %s" % g["job_id"]
                rec["reason"] = "якорь группы" if k == g["anchor"] else "единица рисования якоря (%s)" % rec["via"]
            else:
                rec["producer"] = "%s from %s" % (rec["method"], rec["from"])
                rec["reason"] = "%s: %s" % (rec["via"], METHOD_STATUS[rec["method"]])
            expected.append(rec)
    # ---------------- ворота плана, считаются заново по заданиям и файлам, не по причинам выше
    G, det = Counter(), defaultdict(list)
    for gid, c in Counter(j["group_id"] for j in jobs).items():
        if c > 1:
            G["unexpected_duplicate_creative_render"] += c - 1
            det["unexpected_duplicate_creative_render"].append(gid)
    for f, c in Counter(e["file"] for e in expected).items():
        if c > 1:
            G["unexpected_duplicate_creative_render"] += c - 1
            det["unexpected_duplicate_creative_render"].append(f)
    rendered = Counter(k for j in jobs for k in j["render_unit"])
    for k, c in rendered.items():
        if c > 1:
            G["unexpected_duplicate_creative_render"] += c - 1
            det["unexpected_duplicate_creative_render"].append(k)
    for j in jobs:
        g = gby[j["group_id"]]
        M = set(g["members"])
        for k in j["render_unit"]:
            bad = [c for c in C.of(k) if not tx.auto_claim(c) or not set(c["pair"]) <= M]
            if bad or C.evidence.get(k) or \
                    any(not any(c["type"] == x["type"] and tx.auto_claim(c) and set(c["pair"]) <= M for c in C.of(k))
                        for x in C.self_roles.get(k, [])):
                G["dangerous_independent_render"] += 1
                det["dangerous_independent_render"].append(k)
            if g["prod"].get(k, {}).get("method") != "RENDER":
                G["unexpected_duplicate_creative_render"] += 1
                det["unexpected_duplicate_creative_render"].append("derived-in-render %s" % k)
            if g["pipeline"] != "OBJECT_PIPELINE" or rowmap[k]["semantic_eff"] not in ("OBJECT", "OBJECT_PART") or \
                    g["pipelines"][k] != "OBJECT_PIPELINE":
                G["wrong_pipeline_target"] += 1
                det["wrong_pipeline_target"].append(k)
        if j["render_asset"] != g["anchor"] or j["render_asset"] not in j["render_unit"]:
            G["render_group_anchor_violation"] += 1
            det["render_group_anchor_violation"].append(j["job_id"])
    for e in expected:
        g = gby[e["group_id"]]
        if e["producer"] == "NO_OUTPUT" and e["semantic_eff"] not in ("NOT_OBJECT",) and \
                g["pipeline"] != "NONE":
            G["wrong_pipeline_target"] += 1
            det["wrong_pipeline_target"].append("no-output %s" % e["asset_id"])
        if e["semantic_eff"] == "NOT_OBJECT" and e["producer"].startswith(("RENDER", "COPY", "MIRROR", "DERIVE")):
            G["wrong_pipeline_target"] += 1
            det["wrong_pipeline_target"].append("file-for-not-object %s" % e["asset_id"])
        if not e["producer"]:
            G["missing_expected_output"] += 1
            det["missing_expected_output"].append(e["asset_id"])
        if g["downstream"] == "RENDER" and e["producer"].split()[0] in ("COPY", "MIRROR_FLIP", "DERIVE_RECOLOR",
                                                                        "DERIVE_MIRROR_RECOLOR"):
            ch = chain_of(g["prod"], e["asset_id"])
            if g["prod"].get(ch[-1], {}).get("method") != "RENDER" or g["unit_of"][ch[-1]] != g["unit_of"][g["anchor"]]:
                G["render_group_anchor_violation"] += 1
                det["render_group_anchor_violation"].append(e["asset_id"])
    for k in batch:
        if k not in gid_of:
            G["missing_expected_output"] += 1
            det["missing_expected_output"].append("batch-not-planned %s" % k)
    # решение V7 не потеряно: автоматическое - выполнено (одна единица или оба кадра произведены в группе),
    # прочее - в очереди ревью и группа держится
    rv = {(r["asset"], tuple(r["pair"]), r["group"]) for r in review_items}
    for g in groups:
        for t in g["lost"]:
            G["relation_decision_lost_in_handoff"] += 1
            det["relation_decision_lost_in_handoff"].append("%s %s" % (g["group_id"], t))
        M = set(g["members"])
        for k in g["members"]:
            for c in C.of(k):
                if tx.auto_claim(c) and set(c["pair"]) <= M and g["downstream"] != "RENDER":
                    ok = True       # группа целиком держится или не рисуется - оба кадра связи в одной группе
                elif tx.auto_claim(c) and set(c["pair"]) <= M:
                    a, b = c["pair"]
                    ok = g["unit_of"][a] == g["unit_of"][b] if c["type"] in RENDER_TOGETHER else \
                        bool(g["prod"].get(a) and g["prod"].get(b))
                elif tx.auto_claim(c):
                    ok = g["downstream"] == "HELD"
                else:
                    ok = (k, tuple(c["pair"]), c["group"]) in rv and g["downstream"] == "HELD"
                if not ok:
                    G["relation_decision_lost_in_handoff"] += 1
                    det["relation_decision_lost_in_handoff"].append("%s %s %s" % (k, c["type"], "~".join(c["pair"])))
    # побайтовые копии items.json, которых нет в графе V7 (диагностика: V7 их связью не назвал)
    copies_out = sorted({"%s ~ %s" % (k, y) for g in groups for k in g["members"] for y in copies.get(k, ())
                         if y != k and gid_of.get(y) != g["group_id"]})
    if replay["lost"] or replay["weaker"]:
        G["relation_decision_lost_in_handoff"] += len(replay["lost"]) + len(replay["weaker"])
        det["relation_decision_lost_in_handoff"] += ["V7_REPLAY " + x for x in replay["lost"] + replay["weaker"]]
    # ---------------- диагностика
    live = [e for e in expected if gby[e["group_id"]]["downstream"] == "RENDER"]
    meth = Counter(e["producer"].split()[0] for e in live)
    held_groups = [g for g in groups if g["downstream"] == "HELD"]
    diag = {"direct_renders": {"jobs": len(jobs), "frames": sum(len(j["render_unit"]) for j in jobs),
                               "by_need": dict(Counter(j["needs"] for j in jobs))},
            "derived_or_copy": {m: c for m, c in meth.items() if m not in ("RENDER",)},
            "sent_to_review": {"groups": len(held_groups), "frames": sum(len(g["members"]) for g in held_groups),
                               "batch_assets": sorted(k for g in held_groups for k in g["batch_keys"]),
                               "review_claims": len({(tuple(r["pair"]), r["group"]) for r in review_items}),
                               "why": dict(Counter(x.split()[0] for g in held_groups for x in g["held"]))},
            "edges_reduced_generation": sum(c for m, c in meth.items()
                                            if m in ("COPY", "MIRROR_FLIP", "DERIVE_RECOLOR", "DERIVE_MIRROR_RECOLOR")),
            "frames_in_render_units_beyond_anchor": sum(len(j["render_unit"]) - 1 for j in jobs),
            "cannot_complete_downstream": {
                "structural_or_terrain": sorted(e["asset_id"] for e in expected
                                                if e["producer"] == "NOT_IMPLEMENTED_DOWNSTREAM"),
                "state": sorted(e["asset_id"] for e in expected if e["producer"] == "NOT_IMPLEMENTED_STATE"),
                "renderer_needs_beyond_single": ["%s %s %s" % (j["job_id"], j["render_asset"], j["needs"])
                                                 for j in jobs if j["needs"] != "SINGLE"],
                "derive_recolor_status": METHOD_STATUS["DERIVE_RECOLOR"] if meth.get("DERIVE_RECOLOR") else ""},
            "identity_for_jobs": dict(Counter(j["identity_status"].split()[0] for j in jobs)),
            "byte_copies_outside_v7_graph": copies_out[:60], "byte_copies_outside_v7_graph_n": len(copies_out),
            "v7_replay": replay}
    gates = [{"gate": g, "value": G[g], "need": need, "status": "PASS" if G[g] == need else "FAIL",
              "detail": det.get(g, [])[:40]} for g, need, _t in GATES]
    covered = defaultdict(list)
    for g in groups:
        for k in g["batch_keys"]:
            covered[cat[k]].append("%s:%s" % (k, g["downstream"]))
    res = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "profile": PROFILE, "dry_run": True,
           "spec_sha256": sp["sha256"], "relations_lock_sha256": file_sha(p("relations.lock.json")),
           "code_sha256": file_sha(SELF), "v7": v7_ref(d, ver), "renderer": sp["renderer"],
           "closure": {"keys": len(keys), "closed": lk["closed"], "rounds": lk["rounds"]},
           "gates": gates, "verdict": "PLAN_CONSISTENT" if all(x["status"] == "PASS" for x in gates) else "PLAN_FAIL",
           "diagnostics": diag, "categories": dict(covered),
           "groups": [{k: g[k] for k in ("group_id", "anchor", "roots", "members", "batch_keys", "pipeline",
                                         "pipelines", "downstream", "held", "identity", "units", "prod", "job_id",
                                         "auto_types") if k in g} for g in groups],
           "jobs": jobs, "expected": expected, "review_items": review_items}
    res["jobs_hash"] = jsha(jobs)
    ir.dump_json(p("plan.json"), res)
    write_md(res, sp)
    print("план: %s; заданий %d (кадров %d), выводится %d, на ревью групп %d; ворота %s" % (
        res["verdict"], len(jobs), diag["direct_renders"]["frames"], diag["edges_reduced_generation"],
        diag["sent_to_review"]["groups"], {x["gate"]: x["value"] for x in gates}))
    return res


def v7_replay(d, h, C):
    """Утверждения замороженного holdout V7 по кадрам партии против утверждений плана, по (группа, пара): потеряно,
    ослаблено (было автоматическим или STRONG - стало нет), усилено (V7 не довёл до автоматики, план довёл -
    соседи по замыканию добавили доводов), тип другой. Любое расхождение - не тихое: plan держит такую группу."""
    found3, found4, f7 = H.load_found(V7)
    ans = {r["asset_id"]: r for r in ir.read_tsv(os.path.join(V7, "answers_vitali.tsv"))}
    base = hv.routing_base(V7, d, h)
    rows = hv.routing_rows(base, lambda a: ans.get(a, {}).get("semantic_kind", ""))
    C7 = H.system_claims(rows, found3, found4, f7["edges"])
    batch = {x[0].upper() for x in SELECTION}
    hk = {k.upper() for k in base["keys"]} & batch
    out = {"holdout_keys": len(hk), "same": 0, "lost": [], "weaker": [], "stronger": [], "type_changed": [],
           "extra_in_plan": 0, "keys_differ": []}
    for a in sorted(hk):
        mine = {(c["group"], tuple(c["pair"])): c for c in C.of(a)}
        theirs = {(c["group"], tuple(c["pair"])): c for c in C7.of(a)}
        bad = False
        for k, c in theirs.items():
            m = mine.get(k)
            t = "%s %s %s/%s" % (a, c["type"], "~".join(c["pair"]), c["existence"].split("_")[-1])
            if m is None:
                out["lost"].append(t)
            elif (tx.auto_claim(c) and not tx.auto_claim(m)) or (c["existence"] == v3.STRONG and
                                                                m["existence"] != v3.STRONG):
                out["weaker"].append(t)
            elif tx.auto_claim(m) and not tx.auto_claim(c):
                out["stronger"].append("%s -> %s/%s" % (t, m["existence"].split("_")[-1], m["type_level"]))
            elif m["type"] != c["type"]:
                out["type_changed"].append("%s -> %s" % (t, m["type"]))
            else:
                out["same"] += 1
                continue
            bad = True
        out["extra_in_plan"] += sum(1 for k in mine if k not in theirs)
        if bad:
            out["keys_differ"].append(a)
    out["note"] = "extra - утверждения по связям с кадрами, которых не было в holdout (соседи по замыканию)"
    return out


def write_md(res, sp):
    dg = res["diagnostics"]
    cc = dg["cannot_complete_downstream"]
    rp_ = dg["v7_replay"]
    L = ["# HD_PIPELINE_E2E_V1 - сухой план: %s" % res["verdict"], "",
         "Создан %s. Spec `%s`, relations `%s`, V7 %s (VERIFIED `%s`). Рендер: **%s**. Видеокарта не запускалась, "
         "файлов игры и пака план не трогает." % (
             res["created"], res["spec_sha256"][:12], res["relations_lock_sha256"][:12], res["v7"]["model"],
             res["v7"]["verified_sha256"][:12], res["renderer"]), "",
         "Замыкание по автоматическим связям V7: %d кадров, %s; круги (кадров, новых) %s." % (
             res["closure"]["keys"], "полное" if res["closure"]["closed"] else "**не полное**",
             [(r["keys"], r["new_partners"]) for r in res["closure"]["rounds"]]),
         "", "## Ворота плана", "", "| ворота | значение | нужно | итог | что |", "|---|---|---|---|---|"]
    for g in res["gates"]:
        L.append("| %s | %d | %d | %s | %s |" % (g["gate"], g["value"], g["need"], g["status"],
                                                  "; ".join(map(str, g["detail"][:6])) or "-"))
    L += ["", "## Диагностика", "",
          "- рисуется напрямую: заданий %d, кадров %d; по виду %s" % (
              dg["direct_renders"]["jobs"], dg["direct_renders"]["frames"], dg["direct_renders"]["by_need"]),
          "- выводится и копируется: %s" % (dg["derived_or_copy"] or "-"),
          "- связи, сократившие генерацию (кадр не рисуется, а выводится): %d; кадров в единицах рисования сверх "
          "якоря: %d" % (dg["edges_reduced_generation"], dg["frames_in_render_units_beyond_anchor"]),
          "- на ревью: групп %d (кадров %d), утверждений V7 без автоматики %d; кадры партии: %s" % (
              dg["sent_to_review"]["groups"], dg["sent_to_review"]["frames"], dg["sent_to_review"]["review_claims"],
              ", ".join(dg["sent_to_review"]["batch_assets"]) or "-"),
          "- причины ревью (групп): %s" % dg["sent_to_review"]["why"],
          "- не доводится, нет конвейера структуры или рельефа: %d (%s)" % (
              len(cc["structural_or_terrain"]), ", ".join(cc["structural_or_terrain"][:10])),
          "- не доводится, нет конвейера состояния: %d (%s)" % (len(cc["state"]), ", ".join(cc["state"][:10])),
          "- рендеру нужно больше одиночного кадра: %s" % (", ".join(cc["renderer_needs_beyond_single"]) or "-"),
          "- вывод перекраски: %s" % (cc["derive_recolor_status"] or "не нужен"),
          "- опознание заданий: %s" % dg["identity_for_jobs"],
          "- побайтовые копии items.json вне графа V7: %d" % dg["byte_copies_outside_v7_graph_n"],
          "- сверка с замороженным V7 (кадры holdout в партии %d): совпало %d, потеряно %d, ослаблено %d, усилено %d, "
          "новых утверждений %d" % (rp_["holdout_keys"], rp_["same"], len(rp_["lost"]), len(rp_["weaker"]),
                                    len(rp_.get("stronger", [])), rp_["extra_in_plan"]),
          "", "## Ассеты партии до генерации", "",
          "| ассет | категория | ось A | конвейер | связи V7 | группа (кадров) | якорь | действие | причина |",
          "|---|---|---|---|---|---|---|---|---|"]
    gby = {g["group_id"]: g for g in res["groups"]}
    for e in res["expected"]:
        if not e["batch"]:
            continue
        g = gby[e["group_id"]]
        L.append("| %s | %s | %s | %s | %s | %s (%d) | %s | %s | %s |" % (
            e["asset_id"], e["category"], e["semantic_kind"], e["pipeline_target"],
            "<br>".join(e["relations"][:5]) + (" +%d" % (len(e["relations"]) - 5) if len(e["relations"]) > 5 else ""),
            e["group_id"], len(g["members"]), e["render_anchor"], e["producer"], e["reason"][:160]))
    L += ["", "## Задания рендера", "", "| задание | якорь | единица | нужно | опознание | зерно |",
          "|---|---|---|---|---|---|"]
    for j in res["jobs"]:
        L.append("| %s | %s | %s | %s | %s (%s) | %d |" % (j["job_id"], j["render_asset"], ", ".join(j["render_unit"]),
                                                         j["needs"], j["identity"], j["identity_status"], j["seed"]))
    L += ["", "## Ожидаемые файлы", "", "Всего %d; по производителю: %s" % (
        len(res["expected"]), dict(Counter((e["producer"] or "-").split()[0] for e in res["expected"]))), "",
          "| файл | группа | производитель |", "|---|---|---|"]
    for e in res["expected"]:
        L.append("| %s | %s | %s |" % (e["file"], e["group_id"], e["producer"] or "**нет**"))
    with open(p("plan.md"), "w", encoding=ENC, newline="\n") as f:
        f.write("\n".join(L) + "\n")


def do_check():
    v7_state()
    sp = load_spec()
    print("V7 цел; spec %s цел" % sp["sha256"][:12])
    if os.path.exists(p("relations.lock.json")):
        load_relations()
        print("relations целы")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("spec", "relations", "plan", "check"))
    a = ap.parse_args()
    os.chdir(os.path.dirname(os.path.dirname(HERE)))
    {"spec": do_spec, "relations": do_relations, "plan": do_plan, "check": do_check}[a.cmd]()


if __name__ == "__main__":
    main()
