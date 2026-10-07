#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""DERIVE_RECOLOR_ACCEPTANCE_V2 - приёмка ОПЕРАЦИИ вывода перекраски (obj_derive.derive), не рендера.

Специалист 03.10, передал Vitali в чате: алгоритм сразу не менять; сначала воспроизвести текущую
реализацию на наборе известных случаев и установить, что сломалось у FRNITURE:9 (acc-5e9f63c421c0:
перекраски ABUNKER:11 и GOVT:85 мутные, в пятнах). Qwen не запускать, target не перерисовывать.

Случаи и ворота замораживаются командой spec ДО любого прогона (spec.json, хэш тела). run проверяет,
что spec и код вывода (obj_derive.py) те же, и считает:

  жёсткие ворота (все обязаны быть 0):
    geometry_changed               пиксели, где непрозрачность вывода не та, что у HD основы (с её ориентацией)
    alpha_changed_unexpectedly     пиксели, где альфа вывода не равна альфе HD основы
    pixel_support_changed          клетки 32x40, где занятость вывода не совпала с оригиналом члена, хотя
                                   HD основа со своим оригиналом там совпадает
    wrong_palette_mapping          классы цвета члена, где вывод дальше от цвета члена, чем HD основа от
                                   цвета основы, больше чем на MAP_DE (Lab, внутренние клетки)
    source_target_alignment_error  клетки, где силуэт оригинала основы (в ориентации маршрута) не равен
                                   силуэту оригинала члена
    unintended_local_artifacts     классы (цвет основы, цвет члена), где изменение «вывод против основы»
                                   внутри ровной области пятнистое: разброс отношения яркостей или сдвига
                                   цветности выше порога
  главные ворота:
    синтетика - есть правда (тот же рисовальщик на оригинале члена): средняя и p95 разница Lab;
    настоящие - честной пиксельной правды нет: карточки сравнения, вердикт человека (answers_human.tsv).
  проверка ворот на правде: синтетическая правда обязана пройти все жёсткие ворота, иначе ворота
  этого случая недействительны (GATE_INVALID), а не провал вывода.
  воспроизведение: случаи «как в прогоне» обязаны дать те же пиксели, что лежат в acc-5e9f63c421c0/derived.

    spec    -> probes/derive-recolor-acceptance-v2/spec.json (неизменяемый)
    run     -> derived/, truth/, results.json, results.md
    cards   -> cards/<случай>.png, cards.md, answers_human.tsv (шаблон, если его нет)
    report  -> report.md: ворота, главный вердикт, ответы человека, проверка гипотез
    check   spec и код вывода не изменились

    py -3.13 tools/hdart/derive_recolor_acceptance_v2.py <команда>
"""
import argparse
import colorsys
import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np                                  # noqa: E402
from PIL import Image, ImageDraw                    # noqa: E402

ENC = "utf-8-sig"
ROOT = os.path.dirname(os.path.dirname(HERE))
PROFILE = "DERIVE_RECOLOR_ACCEPTANCE_V2"
OUT = os.path.join(ROOT, "art", "objects", "generation", "probes", "derive-recolor-acceptance-v2")
SELF = "tools/hdart/derive_recolor_acceptance_v2.py"
IMPL = "tools/hdart/obj_derive.py"
RUN = "art/objects/generation/runs/acc-5e9f63c421c0"
LEGACY = "user/mods/hd/hd/TERRAIN"
DECISION = ("специалист 03.10, передал Vitali в чате: DERIVE_RECOLOR_ACCEPTANCE_V2 - сначала воспроизвести "
            "текущую реализацию на известных случаях и установить, что сломалось у FRNITURE; Qwen не запускать, "
            "target не перерисовывать; жёсткие ворота заморожены до результатов")

# пороги - до результатов; проверяются на синтетической правде (GATE_INVALID, если правда их не проходит)
MAP_DE = 10.0          # ΔE76: вывод дальше от цвета члена, чем основа от своего цвета, больше чем на это
MAP_MIN_CELLS = 4      # класс цвета проверяется, если внутренних клеток не меньше
ART_LN = 0.15          # разброс ln((L+5)/(L+5)) вывода к основе внутри класса; до заморозки выверен ТОЛЬКО по
#                        синтетической правде (детальные кадры до 0.123) и контролю с пятнами (от 0.168)
ART_AB = 8.0           # разброс сдвига a и b внутри класса
ART_MIN_CELLS = 4
MAIN_MEAN = 3.0        # синтетика: средняя ΔE76 вывода против правды
MAIN_P95 = 10.0        # и p95
ALPHA_OPAQUE = 250     # клетка полностью непрозрачна, если минимум альфы в её 4x4 не меньше
OCC = 128              # клетка занята, если средняя альфа её 4x4 не меньше
NOISE_SEED = 20261003
NOISE_AMP = 0.10
FLOOR = (40, 40, 44)

GATES = ("geometry_changed", "alpha_changed_unexpectedly", "pixel_support_changed", "wrong_palette_mapping",
         "source_target_alignment_error", "unintended_local_artifacts")

# синтетика: оригинал основы (кадр игры или рисованный ящик), карта цвета, рисовальщик (альфа резкая/мягкая)
SYNTH = [
    {"id": "S01", "what": "simple palette substitution", "base": "FRNITURE:0", "map": "hue120",
     "alpha": "hard", "route": "recolor", "expect": "PASS"},
    {"id": "S02", "what": "large flat regions", "base": "BOX", "map": "hue120", "alpha": "hard",
     "route": "recolor", "expect": "PASS"},
    {"id": "S03", "what": "small detailed object", "base": "JUNGLE:32", "map": "hue120", "alpha": "hard",
     "route": "recolor", "expect": "PASS"},
    {"id": "S04", "what": "transparent edges and holes", "base": "BOX_HOLE", "map": "hue120", "alpha": "hard",
     "route": "recolor", "expect": "PASS"},
    {"id": "S05", "what": "partially transparent / antialiased edges", "base": "FRNITURE:0", "map": "hue120",
     "alpha": "soft", "route": "recolor", "expect": "PASS"},
    {"id": "S06", "what": "local colour variation (one base colour -> two member colours by region)",
     "base": "FRNITURE:0", "map": "split", "alpha": "hard", "route": "recolor", "expect": "PASS"},
    {"id": "S07", "what": "strong dark recolor with bright accent (R-166)", "base": "JUNGLE:32", "map": "dark",
     "alpha": "hard", "route": "recolor", "expect": "PASS"},
    {"id": "S08", "what": "FRNITURE-like: member is recolor of the MIRRORED base, routed as recolor",
     "base": "FRNITURE:9", "map": "hue120", "mirror_member": True, "alpha": "hard", "route": "recolor",
     "expect": "CAUGHT"},
    {"id": "S09", "what": "same member, routed as mirror", "base": "FRNITURE:9", "map": "hue120",
     "mirror_member": True, "alpha": "hard", "route": "mirror", "expect": "PASS"},
]
# настоящие: HD основа - ответ приёмки acc-5e9f63c421c0 или прежний пак; маршрут «как в прогоне» - из
# art/objects/families/decisions.tsv; «по силуэту» - ориентация, при которой силуэты оригиналов совпадают
REAL = [
    {"id": "R01", "what": "FRNITURE regression as run", "base": "FRNITURE:9", "member": "ABUNKER:11",
     "hd": RUN + "/photo/FRNITURE.PCK/9.png", "route": "recolor", "route_src": "families decisions.tsv (as run)",
     "repro": RUN + "/derived/ABUNKER.PCK/11.png", "expect": "CAUGHT"},
    {"id": "R02", "what": "FRNITURE regression as run", "base": "FRNITURE:9", "member": "GOVT:85",
     "hd": RUN + "/photo/FRNITURE.PCK/9.png", "route": "recolor", "route_src": "families decisions.tsv (as run)",
     "repro": RUN + "/derived/GOVT.PCK/85.png", "expect": "CAUGHT"},
    {"id": "R03", "what": "same pair, route by silhouette", "base": "FRNITURE:9", "member": "ABUNKER:11",
     "hd": RUN + "/photo/FRNITURE.PCK/9.png", "route": "mirror", "route_src": "silhouette orientation",
     "expect": "HUMAN"},
    {"id": "R04", "what": "same pair, route by silhouette", "base": "FRNITURE:9", "member": "GOVT:85",
     "hd": RUN + "/photo/FRNITURE.PCK/9.png", "route": "mirror", "route_src": "silhouette orientation",
     "expect": "HUMAN"},
    {"id": "R05", "what": "exact mirror as run", "base": "FRNITURE:9", "member": "CITYFRNITURE:8",
     "hd": RUN + "/photo/FRNITURE.PCK/9.png", "route": "mirror", "route_src": "families decisions.tsv (as run)",
     "repro": RUN + "/derived/CITYFRNITURE.PCK/8.png", "expect": "HUMAN"},
    {"id": "R06", "what": "PASS reference as run", "base": "FRNITURE:0", "member": "COMDECOR:54",
     "hd": RUN + "/photo/FRNITURE.PCK/0.png", "route": "recolor", "route_src": "families decisions.tsv (as run)",
     "repro": RUN + "/derived/COMDECOR.PCK/54.png", "expect": "HUMAN"},
    {"id": "R07", "what": "PASS reference as run", "base": "FRNITURE:0", "member": "CORP:103",
     "hd": RUN + "/photo/FRNITURE.PCK/0.png", "route": "recolor", "route_src": "families decisions.tsv (as run)",
     "repro": RUN + "/derived/CORP.PCK/103.png", "expect": "HUMAN"},
    {"id": "R08", "what": "dark recolor of a plant (R-166)", "base": "JUNGLE:32", "member": "BLACKJUNGLE:32",
     "hd": LEGACY + "/JUNGLE.PCK/32.png", "route": "recolor", "route_src": "V7 RECOLOR, exact palette function",
     "expect": "HUMAN"},
    {"id": "R09", "what": "detailed machine, gold recolor", "base": "U_DISEC2:10", "member": "U_DISEC2GOLD:10",
     "hd": LEGACY + "/U_DISEC2.PCK/10.png", "route": "recolor", "route_src": "V7 RECOLOR, exact palette function",
     "expect": "HUMAN"},
    {"id": "R10", "what": "tree, dark recolor", "base": "FOREST:14", "member": "BLACKFOREST:14",
     "hd": LEGACY + "/FOREST.PCK/14.png", "route": "recolor", "route_src": "V7 RECOLOR, exact palette function",
     "expect": "HUMAN"},
    {"id": "R11", "what": "large flat ground", "base": "DESERT:18", "member": "REDDESERT:18",
     "hd": LEGACY + "/DESERT.PCK/18.png", "route": "recolor", "route_src": "V7 RECOLOR, exact palette function",
     "expect": "HUMAN"},
    {"id": "R12", "what": "palette compressed (member has fewer colours)", "base": "LIGHTNIN:20",
     "member": "LIGHTNIN_GR:20", "hd": LEGACY + "/LIGHTNIN.PCK/20.png", "route": "recolor",
     "route_src": "V7 RECOLOR, palette function one way", "expect": "HUMAN"},
]
HYPOTHESES = [
    "H1: R01 и R02 (маршрут recolor, как в прогоне) - source_target_alignment_error > 0: член - перекраска "
    "ОТРАЖЁННОЙ основы (FRNITURE:8), а вывод не отражал",
    "H2: R03 и R04 (тот же код, маршрут по силуэту) - source_target_alignment_error = 0",
    "H3: S08 поймана воротами, S09 (тот же член, маршрут mirror) проходит",
    "H4: R01, R02, R05, R06, R07 воспроизводят файлы acc-5e9f63c421c0/derived попиксельно",
]
CARD = {
    "panels": ["1 base original x4 (route orientation)", "2 HD base (route orientation)", "3 member original x4",
               "4 derived", "5 derived on checker", "6 truth (synthetic only)"],
    "floor_rgb": list(FLOOR), "scale": 2,
    "question": ("Panel 4 is the member (panel 3) drawn with the detail of panel 2: same shape, member's "
                 "colours, no mud, blotches, halos or colour bleeding? PASS / FAIL / UNSURE"),
    "answers": "answers_human.tsv: case_id, verdict (PASS|FAIL|UNSURE), note",
}
BODY = ("profile", "decision", "implementation", "gates", "thresholds", "synthetic", "real", "inputs",
        "hypotheses", "card", "main_gate", "verdict_rule")


# ---------- общее ----------

def rel(p):
    return os.path.join(ROOT, p)


def jsha(o):
    return hashlib.sha256(json.dumps(o, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def fsha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def asha(a):
    return hashlib.sha256(np.ascontiguousarray(a).tobytes() + str(a.shape).encode()).hexdigest()


def load_json(p):
    with open(p, encoding=ENC) as f:
        return json.load(f)


def save_json(p, o):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding=ENC, newline="\n") as f:
        json.dump(o, f, ensure_ascii=False, indent=1, sort_keys=True)


_W = None


def world():
    global _W
    if _W is None:
        import map_mockup as mm
        _W = mm.World()
    return _W


def orig(key):
    s, f = key.split(":")
    im = world().sprite(s.lower(), int(f), None)
    if im is None:
        raise SystemExit("нет кадра %s" % key)
    return np.asarray(im.convert("RGBA"), np.uint8)


# ---------- синтетика ----------

def box(hole=False):
    """Рисованный ящик 32x40: три ровные грани и кайма; hole - сквозное окно в передней грани."""
    a = np.zeros((40, 32, 4), np.uint8)
    top, left, right, edge = (200, 180, 140), (150, 120, 80), (100, 80, 50), (40, 30, 20)
    for y in range(40):
        for x in range(32):
            if 6 <= y < 14 and abs(x - 16) <= (y - 6) * 2 + 1 and abs(x - 16) <= 15:
                a[y, x, :3], a[y, x, 3] = top, 255
            elif 14 <= y < 36 and 1 <= x < 31:
                a[y, x, :3], a[y, x, 3] = (left if x < 16 else right), 255
            if a[y, x, 3] and (y in (6, 35) or x in (1, 30)):
                a[y, x, :3] = edge
    if hole:
        a[20:27, 5:11, 3] = 0
        a[22:30, 20:25, 3] = 0
    return a


def hue_map(c, shift=1 / 3):
    h, s, v = colorsys.rgb_to_hsv(*(x / 255 for x in c))
    s = max(s, 0.35)
    return tuple(int(round(255 * x)) for x in colorsys.hsv_to_rgb((h + shift) % 1, s, v))


def dark_map(c, accent):
    if c == accent:
        return c
    h, s, v = colorsys.rgb_to_hsv(*(x / 255 for x in c))
    return tuple(int(round(255 * x)) for x in colorsys.hsv_to_rgb(h, s, v * 0.25))


def apply_map(a, kind):
    """Оригинал члена из оригинала основы картой цвета: hue120 - поворот тона (функция), dark - тёмная
    перекраска с ярким акцентом (самый яркий цвет остаётся), split - левая и правая половины по-разному
    (один цвет основы -> два цвета члена: не функция)."""
    out = a.copy()
    m = a[..., 3] > 0
    cols = sorted({tuple(int(v) for v in a[y, x, :3]) for y, x in zip(*np.nonzero(m))})
    accent = max(cols, key=lambda c: 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]) if cols else None
    for y, x in zip(*np.nonzero(m)):
        c = tuple(int(v) for v in a[y, x, :3])
        if kind == "hue120":
            n = hue_map(c)
        elif kind == "dark":
            n = dark_map(c, accent)
        elif kind == "split":
            n = hue_map(c) if x < 16 else hue_map(c, -0.25)
        else:
            raise SystemExit("карта %s" % kind)
        out[y, x, :3] = n
    return out


def noise(h, w, seed=NOISE_SEED):
    rng = np.random.default_rng(seed)
    n = rng.normal(size=(h // 2, w // 2)).astype(np.float32)
    im = Image.fromarray(n, "F").resize((w, h), Image.BILINEAR)
    v = np.asarray(im, np.float32)
    return (v - v.mean()) / max(float(v.std()), 1e-6)


def render(a, alpha, tex):
    """Синтетический «рисовальщик» x4: цвет - гладкое увеличение с умноженной альфой, яркость с фактурой
    tex (одна и та же для основы и правды), альфа резкая (nearest) или мягкая (bilinear)."""
    h, w = a.shape[0] * 4, a.shape[1] * 4
    al = a[..., 3].astype(np.float32) / 255
    big = lambda v: np.asarray(Image.fromarray(v.astype(np.float32), "F").resize((w, h), Image.BILINEAR),
                               np.float32)
    ab = big(al)
    rgb = np.stack([big(a[..., i] * al) for i in range(3)], -1) / np.maximum(ab, 1e-4)[..., None]
    import obj_derive as od
    y, cb, cr = od.ycc(rgb)
    rgb = np.clip(od.rgb(y * (1 + NOISE_AMP * tex), cb, cr), 0, 255)
    if alpha == "hard":
        A = np.repeat(np.repeat((a[..., 3] > 0).astype(np.float32) * 255, 4, 0), 4, 1)
    else:
        A = np.clip(ab * 255, 0, 255)
    out = np.zeros((h, w, 4), np.uint8)
    out[..., :3] = np.round(rgb).astype(np.uint8)
    out[..., 3] = np.round(A).astype(np.uint8)
    out[out[..., 3] == 0, :3] = 0
    return out


def synth_inputs(c):
    base = box() if c["base"] == "BOX" else box(hole=True) if c["base"] == "BOX_HOLE" else orig(c["base"])
    mem_src = base[:, ::-1] if c.get("mirror_member") else base
    member = apply_map(mem_src, c["map"])
    tex = noise(base.shape[0] * 4, base.shape[1] * 4)
    hd = render(base, c["alpha"], tex)
    # правда: тот же рисовальщик на оригинале члена; член отражён - и рисунок основы отражён вместе с ним
    truth = render(member, c["alpha"], tex[:, ::-1] if c.get("mirror_member") else tex)
    return base, member, hd, truth


# ---------- spec ----------

def impl_state():
    import obj_derive as od
    return {"module": IMPL, "sha256": fsha(rel(IMPL)), "derive_version": od.DERIVE_VERSION,
            "call": "obj_derive.derive(hd, base_orig, member_orig, 'перекраска' | 'зеркало')"}


def spec_body():
    inputs = {}
    for c in SYNTH:
        base, member, hd, truth = synth_inputs(c)
        inputs[c["id"]] = {"base_orig": asha(base), "member_orig": asha(member), "hd": asha(hd),
                           "truth": asha(truth)}
    for c in REAL:
        ob, ot = orig(c["base"]), orig(c["member"])
        d = {"base_orig": asha(ob), "member_orig": asha(ot), "hd_file_sha256": fsha(rel(c["hd"]))}
        if c.get("repro"):
            d["repro_file_sha256"] = fsha(rel(c["repro"]))
        inputs[c["id"]] = d
    return {
        "profile": PROFILE, "decision": DECISION, "implementation": impl_state(),
        "gates": {g: "must be 0" for g in GATES},
        "thresholds": {"MAP_DE": MAP_DE, "MAP_MIN_CELLS": MAP_MIN_CELLS, "ART_LN": ART_LN, "ART_AB": ART_AB,
                       "ART_MIN_CELLS": ART_MIN_CELLS, "MAIN_MEAN": MAIN_MEAN, "MAIN_P95": MAIN_P95,
                       "ALPHA_OPAQUE": ALPHA_OPAQUE, "OCC": OCC, "NOISE_SEED": NOISE_SEED,
                       "NOISE_AMP": NOISE_AMP},
        "synthetic": SYNTH, "real": REAL, "inputs": inputs, "hypotheses": HYPOTHESES, "card": CARD,
        "main_gate": {"synthetic": "mean ΔE76(derived, truth) <= MAIN_MEAN and p95 <= MAIN_P95 over truth-opaque "
                                   "pixels",
                      "real": "human PASS on the frozen comparison card (no honest pixel truth)"},
        "verdict_rule": ("case PASS: hard gates 0 (gates valid on truth), gates cover the case (palette and "
                         "artifact classes checked > 0; controls caught: blotched copy -> unintended_local_artifacts, "
                         "base-as-derived -> wrong_palette_mapping when member colour differs by > MAP_DE; "
                         "otherwise UNCOVERED) and main gate; expect CAUGHT: at least one "
                         "hard gate > 0; acceptance of the current implementation: every PASS/HUMAN case passes "
                         "and every CAUGHT case is caught; repro cases reproduce the run pixel for pixel"),
    }


def do_spec():
    p = os.path.join(OUT, "spec.json")
    if os.path.exists(p):
        raise SystemExit("spec.json уже записан - он неизменяем (%s)" % p)
    body = spec_body()
    body["sha256"] = jsha({k: body[k] for k in BODY})
    body["frozen_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    body["self_sha256"] = fsha(rel(SELF))
    save_json(p, body)
    print("spec заморожен: %s, случаев %d + %d, sha %s" % (p, len(SYNTH), len(REAL), body["sha256"][:12]))


def load_spec():
    sp = load_json(os.path.join(OUT, "spec.json"))
    if jsha({k: sp[k] for k in BODY}) != sp["sha256"]:
        raise SystemExit("spec.json изменён после заморозки")
    now = impl_state()
    if now != sp["implementation"]:
        raise SystemExit("код вывода изменился после заморозки: %s против %s" % (now, sp["implementation"]))
    return sp


# ---------- метрики ----------

def lab(rgb):
    c = np.asarray(rgb, np.float64) / 255
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = c @ M.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def blocks(a):
    """HD RGBA (h*4, w*4) -> по клеткам 32x40: средний цвет с весом альфы, средняя и минимальная альфа."""
    h, w = a.shape[0] // 4, a.shape[1] // 4
    v = a.astype(np.float64).reshape(h, 4, w, 4, 4)
    al = v[..., 3]
    s = al.sum((1, 3))
    rgb = (v[..., :3] * al[..., None]).sum((1, 3)) / np.maximum(s, 1e-6)[..., None]
    return rgb, al.mean((1, 3)), al.min((1, 3))


def interior(codes, m):
    """Клетка-ядро: она и 4 соседа по стороне заняты и одного кода (окно 3x3 на детальных кадрах пусто)."""
    ok = m.copy()
    ok[0, :] = ok[-1, :] = ok[:, 0] = ok[:, -1] = False
    for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        ok &= np.roll(m, (dy, dx), (0, 1)) & (np.roll(codes, (dy, dx), (0, 1)) == codes)
    return ok


def code(a):
    return (a[..., 0].astype(np.int64) << 16) | (a[..., 1].astype(np.int64) << 8) | a[..., 2].astype(np.int64)


def gates(der, hd, ob, ot):
    """Жёсткие ворота вывода der против HD основы hd и оригиналов ob, ot - всё уже в ориентации маршрута."""
    g, info = {}, {}
    g["geometry_changed"] = int(((der[..., 3] > 0) != (hd[..., 3] > 0)).sum())
    g["alpha_changed_unexpectedly"] = int((der[..., 3] != hd[..., 3]).sum())
    sb, st = ob[..., 3] > 0, ot[..., 3] > 0
    g["source_target_alignment_error"] = int((sb != st).sum())
    _rd, occ_d_mean, min_d = blocks(der)
    _rb, occ_b_mean, min_b = blocks(hd)
    occ_d, occ_b = occ_d_mean >= OCC, occ_b_mean >= OCC
    g["pixel_support_changed"] = int(((occ_d != st) & (occ_b == sb)).sum())
    rd, rb = _rd, _rb
    S, T = code(ob), code(ot)
    full = (min_d >= ALPHA_OPAQUE) & (min_b >= ALPHA_OPAQUE) & sb & st
    inn = interior(S, full) & interior(T, full)
    ed = np.linalg.norm(lab(rd) - lab(ot[..., :3]), axis=-1)
    eb = np.linalg.norm(lab(rb) - lab(ob[..., :3]), axis=-1)
    # цвет - по всем полностью непрозрачным клеткам класса: смешение на границах одинаково у основы и вывода
    wrong, checked = [], 0
    for t in np.unique(T[full]):
        sel = full & (T == t)
        if sel.sum() < MAP_MIN_CELLS:
            continue
        checked += 1
        ex = float(ed[sel].mean() - eb[sel].mean())
        if ex > MAP_DE:
            wrong.append({"member_rgb": "#%06x" % t, "cells": int(sel.sum()), "excess_de": round(ex, 1),
                          "derived_de": round(float(ed[sel].mean()), 1), "base_de": round(float(eb[sel].mean()), 1)})
    g["wrong_palette_mapping"] = len(wrong)
    info["mapping_classes_checked"] = checked
    info["mapping_wrong"] = wrong
    # пятна: изменение «вывод против основы» внутри ровной области класса (цвет основы, цвет члена)
    Ld, Lb = lab(der[..., :3]), lab(hd[..., :3])
    lnr = np.log((Ld[..., 0] + 5) / (Lb[..., 0] + 5))
    da, db = Ld[..., 1] - Lb[..., 1], Ld[..., 2] - Lb[..., 2]
    # клетки - все полностью непрозрачные, пиксели - внутренние 2x2 каждой клетки: на детальных кадрах
    # ядер почти нет, а края клетки смешаны с соседом и у правды
    big = lambda m: np.repeat(np.repeat(m, 4, 0), 4, 1)
    cell_in = np.zeros((4, 4), bool)
    cell_in[1:3, 1:3] = True
    inner_px = np.tile(cell_in, S.shape)
    opq = (der[..., 3] >= ALPHA_OPAQUE) & (hd[..., 3] >= ALPHA_OPAQUE) & inner_px
    arts, achecked = [], 0
    pairs = S * (1 << 24) + T
    for p in np.unique(pairs[full]):
        sel = full & (pairs == p)
        if sel.sum() < ART_MIN_CELLS:
            continue
        achecked += 1
        px = big(sel) & opq
        s1, s2, s3 = float(lnr[px].std()), float(da[px].std()), float(db[px].std())
        if s1 > ART_LN or s2 > ART_AB or s3 > ART_AB:
            arts.append({"base_rgb": "#%06x" % (p >> 24), "member_rgb": "#%06x" % (p & 0xFFFFFF),
                         "cells": int(sel.sum()), "std_ln_L": round(s1, 3), "std_a": round(s2, 1),
                         "std_b": round(s3, 1)})
    g["unintended_local_artifacts"] = len(arts)
    info["artifact_classes_checked"] = achecked
    info["artifacts"] = arts
    info["interior_cells"] = int(inn.sum())
    info["opaque_cells"] = int(full.sum())
    return g, info


def blotch(a, seed=NOISE_SEED + 1):
    """Контроль чувствительности: те же пиксели с пятнами яркости и цвета размером в 2-3 клетки базы."""
    import obj_derive as od
    h, w = a.shape[:2]
    rng = np.random.default_rng(seed)
    f = lambda: np.asarray(Image.fromarray(rng.normal(size=(h // 10, w // 10)).astype(np.float32), "F")
                           .resize((w, h), Image.BILINEAR), np.float32)
    y, cb, cr = od.ycc(a[..., :3].astype(np.float32))
    out = a.copy()
    out[..., :3] = np.clip(od.rgb(y * (1 + 0.35 * f()), cb + 18 * f(), cr + 18 * f()), 0, 255).astype(np.uint8)
    return out


def controls(hd, ob, ot, truth_like):
    """Ворота цвета и пятен обязаны ловить свои контроли на этом случае, иначе они его не проверяют (R-086):
    основа вместо вывода (цвет не перенесён) и правдоподобный вывод с пятнами."""
    g1, _ = gates(hd, hd, ob, ot)
    g2, _ = gates(blotch(truth_like), hd, ob, ot)
    return {"no_transfer_caught": g1["wrong_palette_mapping"] > 0,
            "blotch_caught": g2["unintended_local_artifacts"] > 0}


def main_metric(der, truth):
    m = truth[..., 3] > 0
    e = np.linalg.norm(lab(der[..., :3]) - lab(truth[..., :3]), axis=-1)[m]
    return {"mean_de": round(float(e.mean()), 2), "p95_de": round(float(np.percentile(e, 95)), 2)}


def orient(a, route):
    return a[:, ::-1].copy() if route == "mirror" else a


# ---------- run ----------

def derive_np(hd, ob, ot, route):
    import obj_derive as od
    how = "зеркало" if route == "mirror" else "перекраска"
    im = od.derive(Image.fromarray(hd, "RGBA"), Image.fromarray(ob, "RGBA"), Image.fromarray(ot, "RGBA"), how)
    return np.asarray(im.convert("RGBA"), np.uint8)


def save_png(a, *parts):
    p = os.path.join(OUT, *parts)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    Image.fromarray(a, "RGBA").save(p)
    return p


def do_run():
    sp = load_spec()
    res = {"profile": PROFILE, "spec_sha256": sp["sha256"], "implementation": sp["implementation"],
           "run_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "cases": {}}
    for c in sp["synthetic"]:
        base, member, hd, truth = synth_inputs(c)
        inp = sp["inputs"][c["id"]]
        if (asha(base), asha(member), asha(hd), asha(truth)) != (inp["base_orig"], inp["member_orig"], inp["hd"],
                                                                 inp["truth"]):
            raise SystemExit("%s: синтетические входы не те, что в spec" % c["id"])
        der = derive_np(hd, base, member, c["route"])
        r = c["route"]
        g, info = gates(der, orient(hd, r), orient(base, r), member)
        # правда - как если бы её вывели в ориентации, где силуэты сходятся
        tr_route = "mirror" if c.get("mirror_member") else "recolor"
        gt, _ = gates(truth, orient(hd, tr_route), orient(base, tr_route), member)
        mm_ = main_metric(der, truth)
        save_png(der, "derived", c["id"] + ".png")
        save_png(truth, "truth", c["id"] + ".png")
        save_png(hd, "hd", c["id"] + ".png")
        save_png(base, "orig", c["id"] + "_base.png")
        save_png(member, "orig", c["id"] + "_member.png")
        res["cases"][c["id"]] = {"kind": "synthetic", "what": c["what"], "route": r, "expect": c["expect"],
                                 "gates": g, "info": info, "truth_gates": gt,
                                 "gates_valid": not any(gt.values()), "main": mm_,
                                 "main_pass": mm_["mean_de"] <= MAIN_MEAN and mm_["p95_de"] <= MAIN_P95,
                                 "identity_baseline": main_metric(orient(hd, r), truth),
                                 "coverage": coverage(info, orient(hd, tr_route), orient(base, tr_route), member,
                                                      truth)}
    for c in sp["real"]:
        ob, ot = orig(c["base"]), orig(c["member"])
        inp = sp["inputs"][c["id"]]
        if asha(ob) != inp["base_orig"] or asha(ot) != inp["member_orig"] or fsha(rel(c["hd"])) != inp[
                "hd_file_sha256"]:
            raise SystemExit("%s: входы не те, что в spec" % c["id"])
        hd = np.asarray(Image.open(rel(c["hd"])).convert("RGBA"), np.uint8)
        if hd.shape[:2] != (ob.shape[0] * 4, ob.shape[1] * 4):
            raise SystemExit("%s: HD %s не x4 к %s" % (c["id"], hd.shape, ob.shape))
        r = c["route"]
        der = derive_np(hd, ob, ot, r)
        g, info = gates(der, orient(hd, r), orient(ob, r), ot)
        row = {"kind": "real", "what": c["what"], "base": c["base"], "member": c["member"], "route": r,
               "route_src": c["route_src"], "expect": c["expect"], "gates": g, "info": info,
               "coverage": coverage(info, orient(hd, r), orient(ob, r), ot, der)}
        if c.get("repro"):
            if fsha(rel(c["repro"])) != inp["repro_file_sha256"]:
                raise SystemExit("%s: файл прогона изменился после spec" % c["id"])
            old = np.asarray(Image.open(rel(c["repro"])).convert("RGBA"), np.uint8)
            row["repro"] = {"file": c["repro"], "identical": bool(old.shape == der.shape and (old == der).all()),
                            "diff_pixels": int((old != der).any(-1).sum()) if old.shape == der.shape else -1}
        save_png(der, "derived", c["id"] + ".png")
        save_png(hd, "hd", c["id"] + ".png")
        save_png(ob, "orig", c["id"] + "_base.png")
        save_png(ot, "orig", c["id"] + "_member.png")
        res["cases"][c["id"]] = row
    res["hypotheses"] = hypotheses(res["cases"])
    save_json(os.path.join(OUT, "results.json"), res)
    write_results_md(res, sp)
    print("прогон: %d случаев -> %s" % (len(res["cases"]), os.path.join(OUT, "results.md")))


def coverage(info, hd, ob, ot, like):
    """Проверяют ли ворота цвета и пятен этот случай: есть проверенные классы и контроли пойманы. Контроль
    «цвет не перенесён» нужен, только если цвет члена заметно другой (средняя ΔE оригиналов > MAP_DE)."""
    m = (ob[..., 3] > 0) & (ot[..., 3] > 0)
    need = bool(m.any()) and float(np.linalg.norm(lab(ob[..., :3]) - lab(ot[..., :3]), axis=-1)[m].mean()) > MAP_DE
    ctl = controls(hd, ob, ot, like)
    ok = (info["mapping_classes_checked"] > 0 and info["artifact_classes_checked"] > 0 and ctl["blotch_caught"]
          and (ctl["no_transfer_caught"] or not need))
    return dict(ctl, colour_change_needed=need, covered=ok)


def hypotheses(cs):
    al = lambda k: cs[k]["gates"]["source_target_alignment_error"]
    caught = lambda k: any(cs[k]["gates"].values())
    clean = lambda k: not any(cs[k]["gates"].values())
    return {
        "H1": al("R01") > 0 and al("R02") > 0,
        "H2": al("R03") == 0 and al("R04") == 0,
        "H3": caught("S08") and clean("S09") and cs["S09"]["main_pass"],
        "H4": all(cs[k]["repro"]["identical"] for k in cs if cs[k].get("repro")),
    }


def case_verdict(r, human=None):
    hard = any(r["gates"].values())
    if r["kind"] == "synthetic" and not r["gates_valid"]:
        return "GATE_INVALID"
    if r["expect"] == "CAUGHT":
        return "CAUGHT" if hard else "NOT_CAUGHT"
    if hard:
        return "HARD_FAIL"
    if not r["coverage"]["covered"]:
        return "UNCOVERED"
    if r["kind"] == "synthetic":
        return "PASS" if r["main_pass"] else "MAIN_FAIL"
    return {"PASS": "PASS", "FAIL": "HUMAN_FAIL", "UNSURE": "HUMAN_UNSURE"}.get(human, "AWAITING_HUMAN")


def write_results_md(res, sp):
    cs = res["cases"]
    L = ["# DERIVE_RECOLOR_ACCEPTANCE_V2 - прогон текущей реализации", "",
         "Spec `%s`, код `%s` (%s), прогон %s. Ответы человека по карточкам ещё не учтены - итог в report.md." % (
             sp["sha256"][:12], sp["implementation"]["sha256"][:12], sp["implementation"]["derive_version"],
             res["run_at"]), "",
         "| случай | что | маршрут | ожидание | " + " | ".join(GATES) + " | главные | вердикт |",
         "|" + "---|" * (6 + len(GATES))]
    for k, r in cs.items():
        main = ("%.1f / %.1f%s" % (r["main"]["mean_de"], r["main"]["p95_de"],
                                   "" if r["gates_valid"] else " (ворота на правде: %s)" %
                                   {g: v for g, v in r["truth_gates"].items() if v})
                if r["kind"] == "synthetic" else "карточка")
        rp = (" repro %s" % ("ДА" if r["repro"]["identical"] else "НЕТ (%d)" % r["repro"]["diff_pixels"])) \
            if r.get("repro") else ""
        what = r["what"] + (" %s -> %s" % (r["base"], r["member"]) if r["kind"] == "real" else "")
        L.append("| %s | %s | %s | %s | %s | %s | %s%s |" % (k, what, r["route"], r["expect"],
                                                          " | ".join(str(r["gates"][g]) for g in GATES), main,
                                                          case_verdict(r), rp))
    L += ["", "## Гипотезы (заморожены в spec)", ""]
    for h in sp["hypotheses"]:
        L.append("- %s - **%s**" % (h, "подтверждена" if res["hypotheses"][h[:2]] else "НЕ подтверждена"))
    L += ["", "## Подробности ворот", ""]
    for k, r in cs.items():
        i = r["info"]
        bad = [x for x in (i["mapping_wrong"] + i["artifacts"])]
        cv = r["coverage"]
        L.append("- %s: клеток непрозрачных %d, ядер %d, классов цвета проверено %d, пар на пятна %d; контроли: "
                 "пятна %s, цвет не перенесён %s%s%s" % (
            k, i["opaque_cells"], i["interior_cells"], i["mapping_classes_checked"], i["artifact_classes_checked"],
            "пойман" if cv["blotch_caught"] else "НЕ пойман",
            ("пойман" if cv["no_transfer_caught"] else "НЕ пойман") if cv["colour_change_needed"] else "не нужен",
            "" if cv["covered"] else " - **ворота случай не проверяют**",
            ("; " + "; ".join(json.dumps(x, ensure_ascii=False) for x in bad[:4])) if bad else ""))
    with open(os.path.join(OUT, "results.md"), "w", encoding=ENC, newline="\n") as f:
        f.write("\n".join(L) + "\n")


# ---------- карточки ----------

def on(a, bg):
    out = Image.new("RGBA", (a.shape[1], a.shape[0]), bg)
    out.alpha_composite(Image.fromarray(a, "RGBA"))
    return out


def checker(w, h, n=8):
    y, x = np.mgrid[0:h, 0:w]
    v = np.where(((x // n) + (y // n)) % 2 == 0, 200, 150).astype(np.uint8)
    return Image.fromarray(np.stack([v, v, v, np.full_like(v, 255)], -1), "RGBA")


def do_cards():
    sp = load_spec()
    res = load_json(os.path.join(OUT, "results.json"))
    if res["spec_sha256"] != sp["sha256"]:
        raise SystemExit("results.json от другого spec")
    sc = CARD["scale"]
    d = os.path.join(OUT, "cards")
    os.makedirs(d, exist_ok=True)
    lines = ["# DERIVE_RECOLOR_ACCEPTANCE_V2 - карточки сравнения", "", "Вопрос (заморожен в spec): " +
             CARD["question"], "", "Ответ - `answers_human.tsv`: case_id, verdict (PASS | FAIL | UNSURE), note. "
             "Результаты ворот на карточках не показаны.", ""]
    for k, r in res["cases"].items():
        route = r["route"]
        ob = np.asarray(Image.open(os.path.join(OUT, "orig", k + "_base.png")).convert("RGBA"), np.uint8)
        ot = np.asarray(Image.open(os.path.join(OUT, "orig", k + "_member.png")).convert("RGBA"), np.uint8)
        hd = np.asarray(Image.open(os.path.join(OUT, "hd", k + ".png")).convert("RGBA"), np.uint8)
        der = np.asarray(Image.open(os.path.join(OUT, "derived", k + ".png")).convert("RGBA"), np.uint8)
        x4 = lambda a: np.repeat(np.repeat(a, 4, 0), 4, 1)
        panels = [on(x4(orient(ob, route)), FLOOR), on(orient(hd, route), FLOOR), on(x4(ot), FLOOR),
                  on(der, FLOOR)]
        ch = checker(der.shape[1], der.shape[0])
        ch.alpha_composite(Image.fromarray(der, "RGBA"))
        panels.append(ch)
        if r["kind"] == "synthetic":
            panels.append(on(np.asarray(Image.open(os.path.join(OUT, "truth", k + ".png")).convert("RGBA"),
                                        np.uint8), FLOOR))
        pw, ph = panels[0].width * sc, panels[0].height * sc
        card = Image.new("RGBA", (pw * len(panels) + 8 * (len(panels) - 1), ph + 34), (24, 24, 28, 255))
        dr = ImageDraw.Draw(card)
        title = "%s  %s" % (k, ("%s -> %s" % (r["base"], r["member"])) if r["kind"] == "real" else r["what"])
        dr.text((4, 4), title, fill=(255, 255, 0, 255))
        for i, p in enumerate(panels):
            x = i * (pw + 8)
            card.paste(p.resize((pw, ph), Image.NEAREST), (x, 34))
            dr.text((x + 4, 20), CARD["panels"][i], fill=(220, 220, 220, 255))
        card.convert("RGB").save(os.path.join(d, k + ".png"))
        lines.append("- %s: ![%s](cards/%s.png)" % (k, k, k))
    with open(os.path.join(OUT, "cards.md"), "w", encoding=ENC, newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    ans = os.path.join(OUT, "answers_human.tsv")
    if not os.path.exists(ans):
        with open(ans, "w", encoding=ENC, newline="\n") as f:
            f.write("case_id\tverdict\tnote\n")
            for k in res["cases"]:
                f.write("%s\t\t\n" % k)
    print("карточки: %s (%d)" % (d, len(res["cases"])))


# ---------- report ----------

def read_human():
    p = os.path.join(OUT, "answers_human.tsv")
    out = {}
    if os.path.exists(p):
        with open(p, encoding=ENC) as f:
            next(f, None)
            for line in f:
                c = line.rstrip("\n").split("\t")
                if len(c) >= 2 and c[1].strip():
                    v = c[1].strip().upper()
                    if v not in ("PASS", "FAIL", "UNSURE"):
                        raise SystemExit("answers_human.tsv: %s - вердикт %r" % (c[0], c[1]))
                    out[c[0].strip()] = v
    return out


def do_report():
    sp = load_spec()
    res = load_json(os.path.join(OUT, "results.json"))
    if res["spec_sha256"] != sp["sha256"]:
        raise SystemExit("results.json от другого spec")
    hum = read_human()
    rows, verdicts = [], {}
    for k, r in res["cases"].items():
        v = case_verdict(r, hum.get(k))
        verdicts[k] = v
        rows.append("| %s | %s | %s | %s | %s |" % (k, r["what"], r["expect"], v, hum.get(k, "-")))
    want_pass = [k for k, r in res["cases"].items() if r["expect"] in ("PASS", "HUMAN")]
    want_caught = [k for k, r in res["cases"].items() if r["expect"] == "CAUGHT"]
    waiting = [k for k in want_pass if verdicts[k] == "AWAITING_HUMAN"]
    ok = (all(verdicts[k] == "PASS" for k in want_pass) and all(verdicts[k] == "CAUGHT" for k in want_caught)
          and res["hypotheses"]["H4"])
    overall = "AWAITING_HUMAN" if waiting else ("PASS" if ok else "FAIL")
    L = ["# DERIVE_RECOLOR_ACCEPTANCE_V2 - итог", "", "Итог приёмки текущей реализации: **%s**%s" % (
        overall, (" (ждут человека: %s)" % ", ".join(waiting)) if waiting else ""), "",
         "| случай | что | ожидание | вердикт | человек |", "|---|---|---|---|---|"] + rows
    with open(os.path.join(OUT, "report.md"), "w", encoding=ENC, newline="\n") as f:
        f.write("\n".join(L) + "\n")
    print("итог: %s -> %s" % (overall, os.path.join(OUT, "report.md")))


def do_check():
    load_spec()
    print("spec и код вывода не изменились")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("spec", "run", "cards", "report", "check"))
    a = ap.parse_args()
    os.chdir(ROOT)
    {"spec": do_spec, "run": do_run, "cards": do_cards, "report": do_report, "check": do_check}[a.cmd]()


if __name__ == "__main__":
    main()
