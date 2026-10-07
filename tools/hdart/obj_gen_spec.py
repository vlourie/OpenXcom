#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Чем рисуется предмет и чем выводится член семейства - описание для плана и ревизий (P1-B).

План генерации должен сказать, КАКОЙ генератор и КАКОЙ промпт получит ассет, а ревизии - заметить,
что поменялось: модель, её настройки (generator_rev), шаблон промпта (prompt_rev), алгоритм вывода
(derive_rev). Значения берутся из самих скриптов разбором текста (ast), без импорта: obj_photo тянет
torch и diffusers, а план считается без видеокарты.

Генератор: 30.09 специалист утвердил turbo --rgba --mp 2.0 ДЛЯ ПРИЁМКИ (APPROVED_FOR_ACCEPTANCE) - только
для приёмочной десятки v1 и только для generator_rev, названной в утверждении; в производство
(PRODUCTION_APPROVED) - после просмотра десятки в игре. approved_for() это и проверяет. Итог приёмки
acc-5e9f63c421c0: годен для простых одиночных предметов (approved_scope); не годен как производственный по
умолчанию, для точной внутренней геометрии (рейки, проёмы), модульных конструкций и другого бока (not_approved).
Эти границы - GENERATOR_POLICY со своей версией generator_policy_rev: политика меняется, рендер нет.

R-145 (30.09): generator_rev считается по замку модели (model_lock.py: коммиты, sha256 файлов, библиотеки),
тексту кода генератора (CODE_PARTS) и параметрам. 8b9025eb1447 посчитана без замка; ревизия с замком
наследует её утверждение только через equivalent_to со status VERIFIED - после smoke, который побайтно
воспроизвёл приёмку (repro_smoke.py). Без замка approved_for всегда ложь.

Промпт v2 (30.09): общий шаблон плюс модификатор по типу ассета - одиночный, основа перекраски, основа
зеркала, другой бок (первый и второй заказ одной multiview-группы), составной, плитка. Цвет - не «как у
спрайта»: преобладающие цвета и их соотношение, палитра и дизеринг оригинала - не истинный RGB.
prompt_rev считается по всему набору (шаблон и все модификаторы): правка любого - новая ревизия.

    py -3.13 tools/hdart/obj_gen_spec.py            (генератор, ревизии, пример промпта)
"""
import ast
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import asset_rev as ar                     # noqa: E402

OBJ_PHOTO = os.path.join(HERE, "obj_photo.py")
OBJ_DERIVE = os.path.join(HERE, "obj_derive.py")
ROOT = os.path.dirname(os.path.dirname(HERE))
# R-145: модель, LoRA, конфиги и библиотеки закреплены файлом-замком (tools/hdart/model_lock.py make);
# generator_rev считается по замку, коду генератора и параметрам - сменился любой байт весов, версия
# diffusers или функция вырезки - новая ревизия, и утверждение на неё само не переходит
LOCK = os.path.join(ROOT, "art", "models", "qwen21_turbo_rgba.lock.json")
GENERATOR = {
    "name": "qwen21_turbo_rgba",
    "script": "tools/hdart/obj_photo.py",
    "args": ["--engine", "turbo", "--rgba", "--mp", "2.0"],
    "model": "Qwen-Image-2.1",
    "mp": 2.0,
    "lock": "art/models/qwen21_turbo_rgba.lock.json",
    "status": "PRODUCTION_PILOT_SIMPLE_OBJECTS",
    "approved_rev": "8b9025eb1447",
    "note": "DECISIONS 30.09: утверждён для приёмочной десятки v1 (generator_rev 8b9025eb1447); вечером 30.09 "
            "специалист и Vitali утвердили пилот простых предметов (PILOT_PRODUCTION_V1) в границах "
            "qwen21-policy-2026-09-30.2 - не PRODUCTION_DEFAULT и не другие классы",
    # 8b9025eb1447 считалась без замка (модель - веткой main). Ревизия с замком получает утверждение
    # 8b9025eb1447, только когда smoke воспроизвёл приёмку: status VERIFIED и generator_rev совпадает с живой
    # smk-c3bfb42cef83 (gpuq #280, 30.09): j03, j06, j09 приёмки - raw и все куски побайтно = acc-5e9f63c421c0
    # (так утверждена 438d6841d129). 30.09 21:25 obj_photo.py правился под пробу полного Qwen - code_rev
    # 7029c93c6473, generator_rev 5c4846840fd9; замок переснят 01.10 (lock_rev тот же 98453a1542c9, веса те же)
    # smk-c6aa68f8ca3a (gpuq #295, 01.10): те же j03, j06, j09 - raw и куски побайтно, pixel_diff 0 (специалист 01.10)
    "equivalent_to": {"rev": "8b9025eb1447", "generator_rev": "5c4846840fd9", "status": "VERIFIED",
                      "reason": "exact same model/LoRA bytes, revision pinned; code change outside the turbo path",
                      "smoke": "smk-c6aa68f8ca3a: REPRODUCED_BYTE_IDENTICAL 3/3 raw, 4/4 кусков",
                      "verified_equivalent_to": "438d6841d129"},
}
# границы применимости - своя версия: меняются по итогам приёмок, рендер от них не меняется
GENERATOR_POLICY = {
    "rev": "qwen21-policy-2026-09-30.2",
    "generator": "qwen21_turbo_rgba",
    "applies_to": "8b9025eb1447",
    "source": "DECISIONS 30.09, итог приёмки acc-5e9f63c421c0; пилот PILOT_PRODUCTION_V1 утверждён специалистом",
    "approved_scope": ["acceptance_infrastructure", "simple_isolated_object"],
    # пилот - только партия из списка, просмотренного человеком (pilot_batch.py), не любой заказ
    "production_pilot": {"approved_for": "PRODUCTION_PILOT_SIMPLE_OBJECTS",
                         "scope": ["simple handcrafted objects", "single-frame", "human-reviewed candidate list",
                                   "no recolor families", "no alt_view", "no structural_modular",
                                   "no complex geometry", "no unresolved identity/family blockers"]},
    "not_approved": ["production_default", "exact_structural_object", "structural_modular", "alternate_view"],
}
# код, от которого зависят сырой ответ и вырезка: (файл, имена верхнего уровня). Текст этих функций и
# присваиваний целиком, с комментариями: правка любого - новая ревизия. Вызовы глубже не отслеживаются
CODE_PARTS = (
    ("obj_photo.py", ("TURBO_SIGMAS", "TURBO_REPO", "TURBO_FILE", "RGBA_HEAD", "RGBA_TAIL", "PHOTO_RGBA",
                      "NEGATIVE", "own_alpha", "edge_matte", "main")),
    ("gen_hd.py", ("QWEN21_REPO", "Qwen21Painter", "qwen21_size", "save_png")),
    ("vx_control.py", ("smooth_ref",)),
    ("probe_object.py", ("cut_out", "match_tone", "pick_background")),
    ("obj_series.py", ("compose", "split")),
    ("model_lock.py", ("pin", "check_runtime")),
)
# зерно j-го задания партии: SEED0 + j (у obj_photo по умолчанию 2713 + номер в списке заданий)
SEED0 = 2713
RGBA_HEAD = "This is an RGBA image with transparency. "
RGBA_TAIL = " The image has alpha channel and the background is transparent."
PROMPT_V2 = {
    "base": (
        "<image1> is the low-resolution original sprite of {what}, on a transparent background. {context}"
        "Make a photorealistic picture of this same real object: {what}. It must look like a real "
        "photograph of a real thing, physically correct materials and light, seen from above at 30 "
        "degrees in isometric view exactly like the sprite. Keep the position, the size and the silhouette "
        "of <image1>. Preserve the exact number, arrangement, and proportions of all meaningful structural "
        "parts, openings, and attached elements visible in the source. Preserve the "
        "object's intended dominant colors and color relationships; the limited palette and dithering of "
        "the sprite are not exact colors. {modifiers}Real surface detail of each material, natural wear, "
        "soft daylight from the upper left, sharp focus. One isolated object, no ground, no floor, no "
        "shadow, no other objects, no text."),
    "composite_context": "<image1> shows its {n} parts placed together exactly as they stand in the game. ",
    "composite": ("All parts belong to one continuous physical object: draw it as one object across the "
                  "whole outline, with no seams, gaps or doubled edges between the parts. "),
    "alt_view_a": ("The same physical object is also drawn from its other isometric side in a separate "
                   "picture, so give it one clear and consistent construction. "),
    "alt_view_b_context": ("<image2> is the finished photograph of this same physical object, seen from its "
                           "other isometric side. "),
    "alt_view_b": ("Same physical object, same materials, proportions, details and construction as <image2>, "
                   "shown from the alternate isometric side: take the shape and position from <image1> and "
                   "the materials, colors and details from <image2>. "),
    "recolor": ("Other color variants of this object are made from this picture afterwards, so keep each "
                "material clean and evenly shaded, without stains, markings or labels that belong to one "
                "color only. "),
    "mirror": ("A mirrored copy of this picture is also used in the game, so the object must look right when "
               "flipped left to right: no text, numbers, logos or one-sided markings. "),
    "tileable": ("This is a repeating modular game asset. Its geometry must remain identical when copies are "
                 "placed directly adjacent. Do not create protruding decorative details that prevent seamless "
                 "repetition. Keep all connection points and outer structural boundaries exactly aligned with "
                 "the original sprite. "),
}
MODIFIER_ORDER = ("composite", "alt_view_a", "alt_view_b", "recolor", "mirror", "tileable")


def constants(path, names):
    """Значения присваиваний верхнего уровня (строки, числа, списки, сложение строк) по тексту файла."""
    with open(path, encoding="utf-8-sig") as f:
        tree = ast.parse(f.read())
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            n = node.targets[0].id
            if n in names:
                out[n] = ast.literal_eval(node.value)
    missing = [n for n in names if n not in out]
    if missing:
        raise SystemExit("%s: нет констант %s - генератор изменился, поправь obj_gen_spec" % (path, missing))
    return out


def code_parts(parts=CODE_PARTS, folder=HERE):
    """{файл: {имя: текст}} - исходный текст названных функций, классов и присваиваний верхнего уровня."""
    out = {}
    for fn, names in parts:
        with open(os.path.join(folder, fn), encoding="utf-8-sig") as f:
            src = f.read().replace("\r\n", "\n")
        got = {}
        for node in ast.parse(src).body:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                n = node.name
            elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                n = node.targets[0].id
            else:
                continue
            if n in names:
                got[n] = ast.get_source_segment(src, node)
        missing = [n for n in names if n not in got]
        if missing:
            raise SystemExit("%s: нет %s - генератор изменился, поправь CODE_PARTS" % (fn, missing))
        out[fn] = got
    return out


def code_rev(parts=CODE_PARTS, folder=HERE):
    return ar.h12(code_parts(parts, folder))


def load_lock(path=LOCK):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


# поля замка, которые на рендер не влияют: когда и кем снят, чем проверен, на какой карте
LOCK_INFO = ("created", "created_by", "source_run", "code", "hardware", "notes", "verified")


def lock_rev(lock):
    return ar.h12({k: v for k, v in lock.items() if k not in LOCK_INFO}) if lock else ""


def spec(gen=GENERATOR, lock=None, code=None):
    """Полное описание генератора: параметры (для generator_rev) и набор шаблонов промпта (для prompt_rev).
    generator_rev - по замку модели, живому коду генератора и параметрам; без замка - как до R-145
    (так посчитана 8b9025eb1447), и такая ревизия утверждения не получает."""
    c = constants(OBJ_PHOTO, ("TURBO_REPO", "TURBO_FILE", "TURBO_SIGMAS"))
    params = {"model": gen["model"], "args": gen["args"], "lora": c["TURBO_REPO"] + "/" + c["TURBO_FILE"],
              "sigmas": c["TURBO_SIGMAS"], "steps": len(c["TURBO_SIGMAS"]), "cfg": 1.0, "mp": gen["mp"]}
    lock = load_lock() if lock is None else lock
    code = code_rev() if code is None else code
    pinned = dict(params, lock_rev=lock_rev(lock), code_rev=code) if lock else params
    template = {"head": RGBA_HEAD, "tail": RGBA_TAIL, "parts": PROMPT_V2, "order": list(MODIFIER_ORDER)}
    return dict(gen, params=pinned, template=template, pinned=bool(lock),
                lock_rev=lock_rev(lock), code_rev=code,
                lock_code_rev=(lock or {}).get("code", {}).get("rev"),
                generator_rev=ar.generator_rev(gen["name"], pinned), prompt_rev=ar.prompt_rev(template),
                generator_policy_rev=GENERATOR_POLICY["rev"], policy=GENERATOR_POLICY)


def effective_rev(gen):
    """Ревизия, на которую действует утверждение: своя, либо approved_rev через проверенную эквивалентность
    (smoke побайтно воспроизвёл приёмку именно этой generator_rev)."""
    eq = gen.get("equivalent_to") or {}
    if eq.get("status") == "VERIFIED" and eq.get("generator_rev") and eq["generator_rev"] == gen.get("generator_rev"):
        return eq["rev"]
    return gen.get("generator_rev")


def approved_for(gen, use):
    """Можно ли этим генератором: use='acceptance' - приёмочная десятка, 'pilot' - пилотная партия простых
    предметов (PILOT_PRODUCTION_V1), 'production' - массовый заказ.
    Утверждение привязано к generator_rev: сменились модель или настройки - утверждения нет."""
    if gen.get("pinned") is False:               # R-145: без замка модели ничего не утверждено
        return False
    if effective_rev(gen) != gen.get("approved_rev"):
        return False
    ok = {"acceptance": ("APPROVED_FOR_ACCEPTANCE", "PRODUCTION_PILOT_SIMPLE_OBJECTS", "PRODUCTION_APPROVED"),
          "pilot": ("PRODUCTION_PILOT_SIMPLE_OBJECTS", "PRODUCTION_APPROVED"),
          "production": ("PRODUCTION_APPROVED",)}
    return gen.get("status") in ok[use]


def derive_version():
    return constants(OBJ_DERIVE, ("DERIVE_VERSION",))["DERIVE_VERSION"]


def build_prompt(template, identity, modifiers=(), parts=1):
    """Промпт заказа: общий шаблон, контекст (куски составного, готовый первый бок) и модификаторы по типу.
    modifiers - имена из MODIFIER_ORDER; в тексте они всегда в порядке MODIFIER_ORDER, не в порядке вызова."""
    P = template["parts"]
    bad = [m for m in modifiers if m not in template["order"]]
    if bad:
        raise ValueError("неизвестные модификаторы промпта: %s" % bad)
    context = ""
    if "composite" in modifiers:
        context += P["composite_context"].replace("{n}", str(parts))
    if "alt_view_b" in modifiers:
        context += P["alt_view_b_context"]
    mods = "".join(P[m] for m in template["order"] if m in modifiers)
    body = P["base"].replace("{context}", context).replace("{modifiers}", mods)
    return template["head"] + body.replace("{what}", identity) + template["tail"]


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    s = spec()
    print(json.dumps({k: v for k, v in s.items() if k != "template"}, ensure_ascii=False, indent=1))
    if s["pinned"] and s["lock_code_rev"] != s["code_rev"]:
        print("!! код генератора изменился после замка: в замке %s, сейчас %s" % (s["lock_code_rev"], s["code_rev"]))
    print("действующая ревизия утверждения:", effective_rev(s))
    print("derive_rev", derive_version())
    print("для приёмки: %s, для производства: %s" % (approved_for(s, "acceptance"), approved_for(s, "production")))
    for mods in ((), ("alt_view_b",), ("composite", "mirror"), ("tileable", "recolor")):
        print()
        print("[%s]" % " + ".join(mods or ("single",)))
        print(build_prompt(s["template"], "a plain square wooden dining table on four straight legs", mods, 2))
