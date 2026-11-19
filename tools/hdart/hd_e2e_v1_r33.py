#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""HD_PIPELINE_E2E_V1_R3_3 - сухой прогон E2E: план R3.2 плюс одна перекраска-фикстура из SAFE_V1.

Специалист 03.10, передал Vitali в чате: «Прекратить E2E_AUX_RECOLOR_SCOUT. Для интеграционного R3.3 разрешено
использовать одну уже VERIFIED пару из blind SAFE_V1 как E2E_AUX_RECOLOR_FIXTURE; выбрать первую технически
подходящую пару по стабильному asset-key order. Эта пара не считается новой validation evidence, она проверяет только
plumbing. Если все E2E hard gates = 0 и присутствуют DIRECT_RENDER + EXACT_COPY + DERIVE_RECOLOR_SAFE, GPU E2E
разрешён.»

План R3.2 (r32/plan.json) не пересчитывается и не меняется: R3.3 читает его, сверяет хэш и добавляет одно действие.
Фикстура - первая по (ключ основы, ключ члена) пара из 16 SAFE_ELIGIBLE + human PASS приёмки SAFE_V1, у которой:
HD основы есть; ни основы, ни члена нет среди кадров плана R3.2; это не BATHBITZ:14 / XB3BITZ1_MAG:14; замороженный
SAFE_V1 eval_real заново даёт SAFE_ELIGIBLE, детерминированный вывод и цепочку BASE. Пропущенные пары - с причиной.

Сухой прогон считает вывод фикстуры на процессоре (тот же frozen BASE, что SAFE_V1) и требует, чтобы он совпал до
пикселя с картинкой, которую человек видел на карточке PASS (confirm/<пара>_base.png): это проверка связки, а не
новое доказательство качества. Ожидаемый хэш вывода пишется в manifest; исполнитель E2E обязан получить тот же.

Ворота (все = 0): ворота R3.2, wrong_target, lost_relation, wrong_anchor, duplicate_creative_render,
missing_expected_output, safe_recolor_without_SAFE_ELIGIBLE, safe_recolor_wrong_source,
safe_recolor_wrong_transform_chain, safe_recolor_missing_output, safe_recolor_output_not_verified_image.
Порог GPU E2E: исполнимых действий >= 10, видов >= 3, DIRECT_RENDER, EXACT_COPY и DERIVE_RECOLOR_SAFE > 0.
Видеокарта не нужна, файлов игры и пака не трогает, review.jsonl не пишет.

    spec    -> hd-e2e-v1/r33/spec.json (неизменяемый)
    plan    -> hd-e2e-v1/r33/plan.json, plan.md, manifest.json (один раз)
    check   spec, план R3.2, приёмка SAFE_V1 и manifest не изменились

    py -3.13 tools/hdart/hd_e2e_v1_r33.py <команда>
"""
import argparse
import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hd_e2e_v1 as E1                            # noqa: E402
import identity_routing as ir                     # noqa: E402

ENC = "utf-8-sig"
PROFILE = "HD_PIPELINE_E2E_V1_R3_3"
SELF = "tools/hdart/hd_e2e_v1_r33.py"
OUT = os.path.join(E1.OUT, "r33")
R32 = os.path.join(E1.OUT, "r32")
OUTPUT_DIR = os.path.join(E1.OUT, "output")
SAFE_DIR = os.path.join(ir.PROBES, "derive-recolor-safe-v1-acceptance")
SAFE_FILES = ("spec.json", "candidates.json", "confirmation.json", "cards_key.json", "final.json")
EXCLUDED = {"BATHBITZ:14", "XB3BITZ1_MAG:14"}
FIXTURE_TYPE = "E2E_AUX_RECOLOR_FIXTURE"
DECISION = ("специалист 03.10, передал Vitali в чате: разведка E2E_AUX_RECOLOR_SCOUT прекращена; в R3.3 одна "
            "VERIFIED пара blind SAFE_V1 как E2E_AUX_RECOLOR_FIXTURE, первая технически подходящая по ключам; не новое "
            "доказательство, только проверка связки; все ворота = 0 и есть DIRECT_RENDER + EXACT_COPY + "
            "DERIVE_RECOLOR_SAFE -> GPU E2E разрешён")
RULES = {
    "fixture_pool": "final.json SAFE_V1: role eligible, eligibility SAFE_ELIGIBLE, verdict PASS (16)",
    "fixture_order": "sorted by (base asset key, member asset key), plain string order; first technically fit",
    "fixture_fit": "HD основы есть; основа и член не среди кадров плана R3.2; не BATHBITZ:14 / XB3BITZ1_MAG:14; "
                   "frozen SAFE_V1 eval_real заново: SAFE_ELIGIBLE, deterministic, chain_ok",
    "fixture_meaning": "source = SAFE_V1 VERIFIED set, purpose = integration coverage only, NOT independent "
                       "recolor validation",
    "fixture_output": "вывод сухого прогона == confirm/<stem>_base.png (картинка карточки PASS) до пикселя; HD основы "
                      "в ориентации цепочки == confirm/<stem>_hd.png",
    "r32": "план R3.2 читается как есть (хэш файла), не пересчитывается",
    "threshold": "executable >= 10, action types >= 3, DIRECT_RENDER > 0, EXACT_COPY > 0, DERIVE_RECOLOR_SAFE > 0",
}
GATES = ("r32_gates_not_pass", "wrong_target", "lost_relation", "wrong_anchor", "duplicate_creative_render",
         "missing_expected_output", "safe_recolor_without_SAFE_ELIGIBLE", "safe_recolor_wrong_source",
         "safe_recolor_wrong_transform_chain", "safe_recolor_missing_output",
         "safe_recolor_output_not_verified_image")
FROZEN = ("tools/hdart/hd_e2e_v1.py", "tools/hdart/hd_e2e_v1_r3.py", "tools/hdart/hd_e2e_v1_r31.py",
          "tools/hdart/hd_e2e_v1_r32.py", "tools/hdart/derive_recolor_safe_acceptance_v1.py",
          "tools/hdart/derive_recolor_base_acceptance_v1.py", "tools/hdart/derive_recolor_base_v1.py")


def p(*a):
    return os.path.join(OUT, *a)


def fsha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def asha(a):
    """Хэш картинки по пикселям (RGBA uint8 и размер), не по байтам PNG."""
    import numpy as np
    a = np.ascontiguousarray(a, dtype=np.uint8)
    return hashlib.sha256(("%s|" % (a.shape,)).encode("ascii") + a.tobytes()).hexdigest()


def rel_path(k):
    s, f = k.split(":")
    return "TERRAIN/%s.PCK/%s.png" % (s, f)


def stem_of(case):
    return case.replace(":", "_").replace(">", "__").replace("/", "_")


# ---------------------------------------------------------------- spec

def sources():
    out = {"r32_plan": os.path.join(R32, "plan.json"), "r32_spec": os.path.join(R32, "spec.json")}
    for n in SAFE_FILES:
        out["safe_v1:" + n] = os.path.join(SAFE_DIR, n)
    for f in FROZEN:
        out["code:" + f] = f
    return {k: {"path": v.replace(os.sep, "/"), "sha256": fsha(v)} for k, v in out.items()}


def spec_body():
    return {"profile": PROFILE, "decision": DECISION, "rules": RULES, "gates": list(GATES),
            "excluded": sorted(EXCLUDED), "fixture_type": FIXTURE_TYPE, "sources": sources(),
            "self_sha256": fsha(SELF)}


def do_spec():
    body = spec_body()
    body["sha256"] = E1.jsha(body)
    if os.path.exists(p("spec.json")):
        old = ir.load_json(p("spec.json"))
        if old["sha256"] != body["sha256"]:
            if os.path.exists(p("plan.json")):
                raise SystemExit("spec R3.3 уже записан и план по нему есть - spec неизменяем")
            raise SystemExit("spec R3.3 уже записан и отличается (плана нет): удалить spec.json можно только "
                             "по решению, а не молча")
        print("spec тот же: %s" % body["sha256"][:12])
        return
    os.makedirs(OUT, exist_ok=True)
    body["created"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    ir.dump_json(p("spec.json"), body)
    print("spec R3.3: %s" % body["sha256"][:12])


def load_spec():
    if not os.path.exists(p("spec.json")):
        raise SystemExit("spec R3.3 не записан: сначала spec")
    sp = ir.load_json(p("spec.json"))
    body = {k: sp[k] for k in sp if k not in ("sha256", "created")}
    if E1.jsha(body) != sp["sha256"]:
        raise SystemExit("spec.json R3.3 изменён после записи")
    now = sources()
    bad = [k for k, v in sp["sources"].items() if now.get(k, {}).get("sha256") != v["sha256"]]
    if fsha(SELF) != sp["self_sha256"]:
        bad.append(SELF)
    if bad:
        raise SystemExit("изменились после spec R3.3: %s" % ", ".join(bad))
    return sp


# ---------------------------------------------------------------- фикстура

def fixture_pool():
    final = ir.load_json(os.path.join(SAFE_DIR, "final.json"))
    if final.get("overall") != "ELIGIBLE_FOR_VERIFIED":
        raise SystemExit("SAFE_V1 итог не ELIGIBLE_FOR_VERIFIED: %s" % final.get("overall"))
    conf = {r["case"]: r for r in ir.load_json(os.path.join(SAFE_DIR, "confirmation.json"))["rows"]}
    out = []
    for c in final["cards"]:
        if c["role"] == "eligible" and c["eligibility"] == "SAFE_ELIGIBLE" and c["verdict"] == "PASS":
            b, m = c["case"].split("/")[0].split(">")
            out.append({"base": b.upper(), "member": m.upper(), "case": c["case"], "card": c["card"],
                        "rank": c["rank"], "verdict": c["verdict"], "conf": conf[c["case"]]})
    return sorted(out, key=lambda x: (x["base"], x["member"]))


def choose_fixture(pool, plan_frames):
    import derive_recolor_safe_acceptance_v1 as S
    skipped = []
    for x in pool:
        b, m = x["base"], x["member"]
        why = []
        if b in EXCLUDED or m in EXCLUDED:
            why.append("исключена решением (BATHBITZ:14 / XB3BITZ1_MAG:14)")
        if b in plan_frames or m in plan_frames:
            why.append("кадр уже в плане R3.2: %s" % ",".join(k for k in (b, m) if k in plan_frames))
        if not os.path.exists(S.hd_file(b)):
            why.append("нет HD основы")
        if why:
            skipped.append({"pair": "%s>%s" % (b, m), "why": why})
            continue
        r = S.eval_real({"base": b, "member": m, "rank": x["rank"]}, True)
        st, w = S.eligibility(r)
        why = []
        if st != "SAFE_ELIGIBLE":
            why.append("SAFE_V1 заново: %s %s" % (st, w))
        if not r.get("deterministic"):
            why.append("вывод не детерминирован")
        if not r.get("chain_ok"):
            why.append("цепочка не BASE")
        if "_img" not in r:
            why.append("вывода нет")
        if why:
            skipped.append({"pair": "%s>%s" % (b, m), "why": why})
            continue
        return x, r, skipped
    raise SystemExit("ни одна пара SAFE_V1 не подходит технически: %s" % json.dumps(skipped, ensure_ascii=False))


# ---------------------------------------------------------------- план

def do_plan():
    import numpy as np
    import derive_recolor_acceptance_v3 as A3v
    sp = load_spec()
    if os.path.exists(p("plan.json")):
        raise SystemExit("план R3.3 уже записан (один раз): %s" % p("plan.json"))
    P = ir.load_json(os.path.join(R32, "plan.json"))
    plan_frames = {f["asset_id"].upper() for f in P["frames"]}
    pool = fixture_pool()
    fx, r, skipped = choose_fixture(pool, plan_frames)
    der, hdo, _ot = r["_img"]
    stem = stem_of(fx["case"])
    conf = fx["conf"]
    vb = A3v.read_png(os.path.join(SAFE_DIR, "confirm", stem + "_base.png"))
    vh = A3v.read_png(os.path.join(SAFE_DIR, "confirm", stem + "_hd.png"))
    import derive_recolor_safe_acceptance_v1 as S
    src_file = S.hd_file(fx["base"])

    # действия: рендер R3.2, копии R3.2, фикстура
    actions = []
    for j in P["jobs"]:
        actions.append({"action": "DIRECT_RENDER", "id": j["job_id"], "target": j["render_asset"],
                        "unit": j["render_unit"], "renderer": j["renderer"], "seed": j["seed"],
                        "identity": j["identity"], "identity_source": j["identity_source"],
                        "outputs": [os.path.join(j["output_dir"], o).replace(os.sep, "/") for o in j["outputs"]],
                        "group": j["group_id"]})
    job_of = {a["target"].upper(): a["id"] for a in actions}
    for f in P["frames"]:
        if f["status"] == "DERIVE":
            kind = {"COPY": "EXACT_COPY", "MIRROR_FLIP": "MIRROR_FLIP"}.get(f["method"], f["method"])
            actions.append({"action": kind, "id": "d:%s" % f["asset_id"], "target": f["asset_id"],
                            "from": f["from"], "via": f["via"], "group": f["relation_group_id"],
                            "anchor": f["render_anchor"],
                            "outputs": [os.path.join(OUTPUT_DIR, f["file"]).replace(os.sep, "/")],
                            "expected": "pixels of output of %s (job %s)%s" % (
                                f["from"], job_of.get(f["from"].upper(), "?"),
                                ", flipped" if f["method"] == "MIRROR_FLIP" else "")})
    out_fx = os.path.join(OUTPUT_DIR, rel_path(fx["member"])).replace(os.sep, "/")
    actions.append({"action": "DERIVE_RECOLOR_SAFE", "id": "fx:%s" % fx["member"], "type": FIXTURE_TYPE,
                    "target": fx["member"], "from": fx["base"], "anchor": fx["base"], "group": "fx:%s" % fx["base"],
                    "purpose": "integration coverage only; NOT independent recolor validation",
                    "source_set": "SAFE_V1 VERIFIED (blind human PASS)",
                    "source_provenance": {"kind": "EXISTING_HD", "path": src_file.replace(os.sep, "/"),
                                          "sha256": fsha(src_file)},
                    "transform_chain": {"geometry_transform": r["geometry"], "color_transform": "BASE_V1 recolor",
                                        "module": "tools/hdart/derive_recolor_base_v1.py"},
                    "safe_evidence": {"case": fx["case"], "card": fx["card"], "verdict": fx["verdict"],
                                      "eligibility": r["eligibility"], "struct": r.get("struct"),
                                      "art": r.get("art"), "map": r.get("map"),
                                      "safe_spec_sha256": ir.load_json(os.path.join(SAFE_DIR, "spec.json"))["sha256"]},
                    "outputs": [out_fx], "expected_pixels_sha256": asha(der),
                    "verified_image": os.path.join(SAFE_DIR, "confirm", stem + "_base.png").replace(os.sep, "/")})

    # ворота
    G = {g: [] for g in GATES}
    for g in P["gates"]:
        if g["status"] != "PASS" or g["value"] != 0:
            G["r32_gates_not_pass"].append(g["gate"])
    outs = {}
    out_root = os.path.abspath(OUTPUT_DIR)
    for a in actions:
        if not a["outputs"]:
            G["missing_expected_output"].append(a["id"])
        for o in a["outputs"]:
            if not os.path.abspath(o).startswith(out_root + os.sep) or "user/mods" in o.replace(os.sep, "/"):
                G["wrong_target"].append("%s -> %s" % (a["id"], o))
            if o in outs:
                G["wrong_target"].append("%s и %s пишут %s" % (outs[o], a["id"], o))
            outs[o] = a["id"]
    rendered = [a["target"].upper() for a in actions if a["action"] == "DIRECT_RENDER"]
    for k in sorted({k for k in rendered if rendered.count(k) > 1}):
        G["duplicate_creative_render"].append("рендер дважды: %s" % k)
    derived = {a["target"].upper() for a in actions if a["action"] != "DIRECT_RENDER"}
    for k in sorted(derived & set(rendered)):
        G["duplicate_creative_render"].append("и рендер, и вывод: %s" % k)
    for a in actions:
        if a["action"] in ("EXACT_COPY", "MIRROR_FLIP") and a["from"].upper() not in job_of:
            G["wrong_anchor"].append("%s: основы %s нет среди заданий рендера" % (a["id"], a["from"]))
    fa = actions[-1]
    if fa["from"] != fx["base"] or fa["anchor"] != fx["base"] or fa["target"] != fx["member"]:
        G["wrong_anchor"].append("фикстура: якорь/цель не те, что в паре SAFE_V1")
    if {fx["base"], fx["member"]} & (plan_frames | EXCLUDED):
        G["wrong_anchor"].append("фикстура пересекает план R3.2")
    if "%s>%s/REAL" % (fa["from"], fa["target"]) != fx["case"]:
        G["lost_relation"].append("связь фикстуры не совпадает с парой SAFE_V1")
    # связи R3.2: каждый вывод несёт свою связь
    for a in actions:
        if a["action"] in ("EXACT_COPY", "MIRROR_FLIP") and not a.get("via"):
            G["lost_relation"].append(a["id"])
    if r["eligibility"] != "SAFE_ELIGIBLE" or fx["verdict"] != "PASS":
        G["safe_recolor_without_SAFE_ELIGIBLE"].append(fx["case"])
    if not os.path.exists(src_file):
        G["safe_recolor_wrong_source"].append("нет HD основы %s" % src_file)
    elif hdo.shape != vh.shape or not np.array_equal(hdo, vh):
        G["safe_recolor_wrong_source"].append("HD основы не тот, что на карточке PASS")
    if fx["base"] in derived or fx["base"] in rendered:
        G["safe_recolor_wrong_source"].append("основа фикстуры перезаписывается другим действием")
    if r["geometry"] != conf.get("geometry") or not r.get("chain_ok") or not r.get("deterministic"):
        G["safe_recolor_wrong_transform_chain"].append("%s: %s против %s, chain_ok %s, det %s" % (
            fx["case"], r["geometry"], conf.get("geometry"), r.get("chain_ok"), r.get("deterministic")))
    if der is None or not fa["outputs"]:
        G["safe_recolor_missing_output"].append(fx["case"])
    if der is None or der.shape != vb.shape or not np.array_equal(der, vb):
        diff = None if der is None or der.shape != vb.shape else int((der != vb).any(-1).sum())
        G["safe_recolor_output_not_verified_image"].append("%s: отличается от карточки PASS (пикселей %s)" % (
            fx["case"], diff))
    gates = [{"gate": g, "value": len(G[g]), "need": 0, "status": "PASS" if not G[g] else "FAIL",
              "detail": G[g][:20]} for g in GATES]

    kinds = {}
    for a in actions:
        kinds[a["action"]] = kinds.get(a["action"], 0) + 1
    th = {"executable_actions": len(actions), "action_types": len(kinds),
          "DIRECT_RENDER": kinds.get("DIRECT_RENDER", 0), "EXACT_COPY": kinds.get("EXACT_COPY", 0),
          "DERIVE_RECOLOR_SAFE": kinds.get("DERIVE_RECOLOR_SAFE", 0)}
    th_ok = (th["executable_actions"] >= 10 and th["action_types"] >= 3 and th["DIRECT_RENDER"] > 0
             and th["EXACT_COPY"] > 0 and th["DERIVE_RECOLOR_SAFE"] > 0)
    ok = th_ok and all(g["status"] == "PASS" for g in gates)
    verdict = "DRY_RUN_PASS_GPU_E2E_ALLOWED" if ok else "DRY_RUN_FAIL"
    manifest = {"profile": PROFILE, "spec_sha256": sp["sha256"], "r32_plan_sha256": sp["sources"]["r32_plan"]["sha256"],
                "output_dir": OUTPUT_DIR.replace(os.sep, "/"), "actions": actions}
    ir.dump_json(p("manifest.json"), manifest)
    plan = {"profile": PROFILE, "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "spec_sha256": sp["sha256"],
            "verdict": verdict, "gates": gates, "threshold": th, "threshold_ok": th_ok, "action_kinds": kinds,
            "fixture": {"pair": fx["case"], "card": fx["card"], "type": FIXTURE_TYPE,
                        "geometry": r["geometry"], "expected_pixels_sha256": asha(der),
                        "pool_order": ["%s>%s" % (x["base"], x["member"]) for x in pool], "skipped": skipped},
            "manifest_sha256": fsha(p("manifest.json")), "r32_summary": P.get("r32_summary")}
    ir.dump_json(p("plan.json"), plan)
    write_md(plan, actions)
    print("R3.3: %s; действий %d %s; фикстура %s (пропущено до неё %d)" % (
        verdict, len(actions), kinds, fx["case"], len(skipped)))
    for g in gates:
        if g["status"] != "PASS":
            print("  FAIL %s = %d: %s" % (g["gate"], g["value"], g["detail"][:3]))


def write_md(plan, actions):
    fx = plan["fixture"]
    L = ["# HD_PIPELINE_E2E_V1_R3.3 - сухой прогон: %s" % plan["verdict"], "",
         "Создан %s. Spec `%s`. План R3.2 не пересчитывался: прочитан как есть, добавлено одно действие." % (
             plan["created"], plan["spec_sha256"][:12]), "",
         "Решение: %s." % DECISION, "",
         "## Фикстура перекраски", "",
         "- пара **%s** (карточка %s, human PASS), тип %s;" % (fx["pair"], fx["card"], fx["type"]),
         "- назначение: только проверка связки, **не** новое доказательство качества перекраски;",
         "- цепочка: геометрия %s, цвет BASE_V1; основа - существующий HD;" % fx["geometry"],
         "- ожидаемый вывод (хэш пикселей) `%s` - совпал с картинкой карточки PASS до пикселя, если ворота "
         "safe_recolor_output_not_verified_image = 0;" % fx["expected_pixels_sha256"][:16],
         "- порядок отбора (ключ основы, затем члена): %s;" % ", ".join(fx["pool_order"]),
         "- пропущено до неё: %s." % ("; ".join("%s (%s)" % (s["pair"], ", ".join(s["why"])) for s in fx["skipped"])
                                      or "ничего"), "",
         "## Порог GPU E2E", "", "| что | число |", "|---|---|"]
    L += ["| %s | %s |" % (k, v) for k, v in plan["threshold"].items()]
    L += ["", "Порог: %s." % ("выполнен" if plan["threshold_ok"] else "НЕ выполнен"), "",
          "## Ворота", "", "| ворота | значение | итог | что |", "|---|---|---|---|"]
    L += ["| %s | %d | %s | %s |" % (g["gate"], g["value"], g["status"], "; ".join(g["detail"][:3]) or "-")
          for g in plan["gates"]]
    L += ["", "## Действия", "", "| действие | цель | из | выход |", "|---|---|---|---|"]
    L += ["| %s | %s | %s | %s |" % (a["action"], a["target"], a.get("from") or a.get("identity", ""),
                                     a["outputs"][0] if a["outputs"] else "-") for a in actions]
    with open(p("plan.md"), "w", encoding=ENC, newline="\n") as f:
        f.write("\n".join(L) + "\n")


def do_check():
    load_spec()
    pl = ir.load_json(p("plan.json"))
    if fsha(p("manifest.json")) != pl["manifest_sha256"]:
        raise SystemExit("manifest.json изменён после плана")
    print("R3.3 цел: spec, план R3.2, SAFE_V1, код и manifest не изменились; итог %s" % pl["verdict"])


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("spec", "plan", "check"))
    a = ap.parse_args()
    os.chdir(os.path.dirname(os.path.dirname(HERE)))
    {"spec": do_spec, "plan": do_plan, "check": do_check}[a.cmd]()


if __name__ == "__main__":
    main()
