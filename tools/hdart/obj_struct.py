#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Структура кадра-предмета: запись MCD, объёмная форма по LOFT и строение силуэта (Pipeline v2, P1-A).

Цвет - слабый признак: по пересечению цветовых гистограмм «другим боком» оказывалась половина соседних
кадров набора (2141 кандидат на 29.09). Здесь то, что у другого бока одной вещи обязано совпасть:
  * физика записи MCD - броня, ОВ, горючесть, топливо, взрыв, звук шага, свет, высота (как читает
    MapDataSet::loadMCD, src/Mod/MapDataSet.cpp): у двух боков одного кресла она одна;
  * объём по LOFT (12 слоёв по 2 вокселя, каждый - 16x16 бит из LOFTEMPS.DAT, как TileEngine::voxelCheck):
    другой бок - та же форма, повёрнутая на 90 градусов в плоскости пола; перекраска - та же форма без
    поворота. Форма, одинаковая при любом повороте (полный куб), ничего не доказывает - это отмечается;
  * силуэт: высота рамки, площадь, профиль ширины по строкам (не меняется при отражении), число частей.

Класс кадра для очереди предметов (раздел 20, «полы никогда не идут конвейером предметов»):
  floor_like  - плоское на полу: весь силуэт в ромбе пола и объём не выше одного слоя (ковёр, разметка,
                лужа, обломок-пятно); рисуется способом полов;
  structural  - часть здания: пандус (T_Level меньше нуля и форма клином), большая стена (Big_Wall),
                дверь; рисуется со стенами и полами;
  object      - всё остальное.

    py -3.13 tools/hdart/obj_struct.py FRNITURE:8 FRNITURE:9
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np                                      # noqa: E402

MCD_RECORD = 62
# физика записи, по которой два бока одной вещи совпадают (смещения - struct MCD в MapDataSet.cpp)
PHYS = {"stop_los": 31, "big_wall": 33, "door": 35, "ufo_door": 30, "block_fire": 36, "block_smoke": 37,
        "tu_walk": 39, "tu_slide": 40, "tu_fly": 41, "armor": 42, "he_block": 43, "flammable": 45,
        "t_level": 48, "light_block": 51, "footstep": 52, "he_type": 54, "he_strength": 55, "fuel": 57,
        "light_source": 58}
PHYS_KEY = ("armor", "tu_walk", "flammable", "fuel", "he_block", "big_wall", "t_level", "footstep",
            "stop_los", "light_block")
FLOOR_Y0 = 24           # ромб пола в кадре 32x40: строки 24..39 (клетка 32x16 внизу кадра)


def diamond():
    m = np.zeros((40, 32), bool)
    for y in range(16):
        h = min(y, 15 - y) * 2 + 2
        m[FLOOR_Y0 + y, 16 - h:16 + h] = True
    return m


DIAMOND = diamond()


class Struct:
    """Записи MCD и LOFTEMPS установки; world - map_mockup.World (у него поиск файлов мода)."""

    def __init__(self, world):
        self.world = world
        self.raw = {}
        p = world.files.find(os.path.join("TERRAIN", "LOFTEMPS.DAT")) or \
            world.files.find(os.path.join("GEODATA", "LOFTEMPS.DAT"))
        data = np.frombuffer(open(p, "rb").read(), "<u2")
        bits = ((data[:, None] >> np.arange(16)) & 1).astype(bool)          # [строка, x]
        self.loft = bits.reshape(-1, 16, 16)                                # [id, y, x]
        self.cache = {}

    def records(self, s):
        s = s.upper()
        if s not in self.raw:
            p = self.world.files.find(os.path.join("TERRAIN", s + ".MCD"))
            d = open(p, "rb").read() if p else b""
            self.raw[s] = [d[i:i + MCD_RECORD] for i in range(0, len(d) - MCD_RECORD + 1, MCD_RECORD)]
        return self.raw[s]

    def record(self, s, frame):
        """Запись, у которой кадр frame первый; из нескольких - предмет (Tile_Type 3) раньше."""
        best = None
        for r in self.records(s):
            if r[0] == frame and (best is None or (r[53] == 3 and best[53] != 3)):
                best = r
        return best

    def phys(self, rec):
        out = {k: rec[o] for k, o in PHYS.items()}
        out["t_level"] = int(np.int8(np.uint8(rec[48])))
        return out

    def voxels(self, rec):
        """Объём [12 слоёв, y, x]; LOFT 0 - пусто."""
        ids = [min(int(v), len(self.loft) - 1) for v in rec[8:20]]
        return np.stack([self.loft[i] if i else np.zeros((16, 16), bool) for i in ids])

    def info(self, s, frame, im=None):
        key = (s.upper(), frame)
        if key in self.cache:
            return self.cache[key]
        rec = self.record(s, frame)
        out = {"rec": rec is not None}
        if rec is not None:
            out["phys"] = self.phys(rec)
            out["tile_type"] = rec[53]
            out["vox"] = self.voxels(rec)
        if im is None:
            im = self.world.sprite(s.lower(), frame, None)
        if im is not None:
            a = np.asarray(im.convert("RGBA"))
            out.update(silhouette(a[..., 3] > 0))
            out["col"] = a[..., :3][a[..., 3] > 0].mean(0) if out["area"] else np.zeros(3)
        self.cache[key] = out
        return out


def silhouette(m):
    ys, xs = np.nonzero(m)
    if not len(ys):
        return {"mask": m, "area": 0, "h": 0, "w": 0, "top": 40, "rows": np.zeros(40), "parts": 0,
                "in_floor": 1.0}
    rows = m.sum(1).astype(np.float32)
    return {"mask": m, "area": int(m.sum()), "h": int(ys.max() - ys.min() + 1), "w": int(xs.max() - xs.min() + 1),
            "top": int(ys.min()), "bottom": int(ys.max()), "rows": rows, "parts": parts(m),
            "in_floor": float((m & DIAMOND).sum() / m.sum()), "cover": float((m & DIAMOND).sum() / DIAMOND.sum())}


def parts(m):
    """Число связных частей силуэта (4-связность), мелочь меньше 4 пикселей не считается."""
    seen = np.zeros_like(m)
    n = 0
    h, w = m.shape
    for y0, x0 in zip(*np.nonzero(m)):
        if seen[y0, x0]:
            continue
        st, size = [(y0, x0)], 0
        seen[y0, x0] = True
        while st:
            y, x = st.pop()
            size += 1
            for yy, xx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= yy < h and 0 <= xx < w and m[yy, xx] and not seen[yy, xx]:
                    seen[yy, xx] = True
                    st.append((yy, xx))
        n += size >= 4
    return n


# повороты и отражения клетки в плоскости пола: [y, x] -> ...
D4 = {"id": lambda v: v, "rot90": lambda v: np.rot90(v, 1, (1, 2)), "rot180": lambda v: np.rot90(v, 2, (1, 2)),
      "rot270": lambda v: np.rot90(v, 3, (1, 2)), "transpose": lambda v: np.swapaxes(v, 1, 2),
      "flip_x": lambda v: v[:, :, ::-1], "flip_y": lambda v: v[:, ::-1, :],
      "anti": lambda v: np.rot90(np.swapaxes(v, 1, 2), 2, (1, 2))}
TURNS = ("rot90", "rot270", "transpose", "anti")        # те, что меняют ось предмета: другой бок


def viou(a, b):
    u = (a | b).sum()
    return float((a & b).sum() / u) if u else 1.0


def voxel_relation(va, vb):
    """(same, turned, symmetric): IoU как есть, лучший IoU после поворота на 90 градусов, и насколько
    форма A сама себе равна при таком повороте (1.0 - куб или цилиндр: объём ничего не доказывает)."""
    same = viou(va, vb)
    turned = max(viou(D4[t](va), vb) for t in TURNS)
    sym = max(viou(D4[t](va), va) for t in TURNS)
    return same, turned, sym


def row_corr(ra, rb):
    """Сходство профилей ширины по строкам (кадры выровнены низом рамки - стоят на полу)."""
    x, y = ra - ra.mean(), rb - rb.mean()
    d = np.sqrt((x * x).sum() * (y * y).sum())
    return float((x * y).sum() / d) if d else 0.0


def phys_diff(pa, pb):
    return [k for k in PHYS_KEY if pa.get(k) != pb.get(k)]


ALT_HIGH, ALT_POSSIBLE, ALT_REJECT = "ALT_VIEW_HIGH", "ALT_VIEW_POSSIBLE", "REJECT"
# класс, который правила не решили: идёт конвейером предметов, но заказ держит вопрос на карточке
UNCERTAIN = "object_or_relief"
OBJECTISH = ("object", UNCERTAIN)


CORE = ("armor", "tu_walk", "flammable", "t_level", "footstep")   # физика самой вещи; fuel, he_block,
# light_block, big_wall у двух боков одной вещи расходятся (THULBASES02 78/79: объём повёрнут 1.00, а fuel
# и big_wall разные) - в CORE их нет
COLOR_MIN = 0.25        # другой материал: чёрный и розовый куб, два разных плаката
ALT_REQUIRED = 0.70     # ниже - кандидат необязательный: точность ~25% против ~60% выше 0.76 (листы alt_*, 29.09)


def alt_view(a, b, color):
    """Другой бок? a, b - Struct.info двух одиночных кадров, color - пересечение цветовых гистограмм.
    -> (класс, score 0..1, причины).

    Калибровка 29.09 по листам (alt_high, alt_reject_top): силуэт и физика совпадают и у разных вещей на
    одном каркасе - плакаты с разными картинками, витрины с разным содержимым, экраны. Отличить их от
    другого бока строение силуэта не может, поэтому ALT_VIEW_HIGH - только когда ОБЪЁМ доказывает поворот:
    форма несимметрична, после поворота на 90 градусов совпадает, а как есть - нет (стул FRNITURE 2/3:
    1.00 против 0.68). Одинаковый силуэт при симметричном объёме - ALT_VIEW_POSSIBLE, решает человек."""
    why = []
    if not a.get("area") or not b.get("area"):
        return ALT_REJECT, 0.0, ["пустой кадр"]
    dh, darea = abs(a["h"] - b["h"]), abs(a["area"] - b["area"]) / max(a["area"], b["area"])
    rc = row_corr(a["rows"], b["rows"])
    mi = viou(a["mask"], b["mask"][:, ::-1])
    s_sil = max(0.0, 1 - dh / 6) * 0.3 + max(0.0, 1 - darea / 0.35) * 0.2 + max(0.0, rc) * 0.3 + mi * 0.2
    if a["parts"] != b["parts"]:
        s_sil *= 0.85
        why.append("частей %d/%d" % (a["parts"], b["parts"]))
    why.insert(0, "высота %d/%d, профиль %.2f, зеркальный силуэт %.2f, цвет %.2f" % (a["h"], b["h"], rc, mi, color))
    s_phys, s_vox, core, strong, differ = 0.5, 0.5, 0, False, False
    if a.get("rec") and b.get("rec"):
        pd = phys_diff(a["phys"], b["phys"])
        core = sum(1 for k in pd if k in CORE)
        s_phys = max(0.0, 1 - 0.3 * core - 0.1 * (len(pd) - core))
        if pd:
            why.append("MCD: " + ",".join(pd))
        same, turned, sym = voxel_relation(a["vox"], b["vox"])
        if sym < 0.9:                   # форма несимметрична - объём что-то доказывает
            s_vox = turned
            strong = turned >= 0.85 and turned >= same + 0.15
            # LOFT у Пираток берутся из небольшой библиотеки, и у другого бока форма часто подобрана
            # на глаз (бревно XOPSDESERTRUINS 3/2: 0.39 после поворота). Сам по себе объём не отказывает -
            # только вместе с несовпавшим силуэтом
            differ = turned < 0.6 and same < 0.6 and (mi < 0.7 or rc < 0.85)
            why.append("объём повёрнут %.2f (как есть %.2f)%s" % (turned, same, " - поворот доказан" if strong else ""))
        else:
            why.append("объём симметричен")
    else:
        why.append("нет записи MCD")
    score = round(0.3 * s_phys + 0.25 * s_vox + 0.35 * s_sil + 0.1 * min(1.0, color), 3)
    if core >= 2 or color < COLOR_MIN or differ or (not strong and (dh > 6 or rc < 0.6)):
        return ALT_REJECT, score, why
    # второй круг калибровки: в HIGH попали «тот же короб, сверху другое» (URBANWAR 90/89: высота 26/29) и
    # «шкаф и сейф» (FRNITURE 19 / MILBARR 19: тон другой). Другой бок держит высоту до пикселя и тон
    dcol = float(np.abs(a["col"] - b["col"]).max()) if "col" in a and "col" in b else 0.0
    if strong and core == 0 and color >= 0.35 and dh <= 1 and darea <= 0.1 and dcol <= 40:
        return ALT_HIGH, score, why
    if score >= 0.62:
        return ALT_POSSIBLE, score, why
    return ALT_REJECT, score, why


def asset_class(info):
    """floor_like | structural | object по записи MCD и силуэту (докстрока модуля).

    Калибровка 29.09 (лист class_*): Big_Wall 1 - «блок на всю клетку», это и валун, и ящик, и лестница
    INDUSLUM 9 - по нему не делится. Стена в клетке предмета - Big_Wall 2..9 (диагональ, сторона).
    Рельеф - клетка, по которой ходят (TU_Walk не 255), с полным нижним слоем объёма, который к верху
    сужается: холмы MOUNTSAND 34, пандусы FOREST_SNOW 31, кучи обломков INDUSLUM 57."""
    if not info.get("area"):
        return "object", "пустой кадр"
    p = info.get("phys", {})
    vox = info.get("vox")
    fill = vox.reshape(12, -1).sum(1) if vox is not None else None
    layers = int((fill > 0).sum()) if fill is not None else None
    walk = p.get("tu_walk", 255) < 255
    # доля ромба пола, которую кадр закрывает: покров (трава, лужа, свечение) - заметная; лейка VILBAN 83
    # и камешки лежат на полу, но закрывают крохи - это предметы (лист class_floor_like, 29.09)
    cover = info.get("cover", 0.0)
    # высота: запись пола с сухим деревом FOREST 8 (31 px) - предмет; покров пола не выше 22 (лист excl, 29.09)
    if info.get("tile_type") == 0 and info["in_floor"] >= 0.6 and cover >= 0.2 and info["h"] <= 22:
        return "floor_like", "запись пола (Tile_Type 0), ромб закрыт на %.0f%%" % (cover * 100)
    bw = p.get("big_wall", 0)
    if bw in (2, 3) or (4 <= bw <= 9 and p.get("stop_los")):
        # стена в клетке предмета: диагональ или сторона, закрывающая обзор (обшивка C_EXT_WALL - Big_Wall
        # 5 и Stop_LOS). Сторона без Stop_LOS - терминалы URBAN40K у стены, это предметы (29.09)
        return "structural", "стена в клетке предмета (Big_Wall %d%s)" % (bw, ", Stop_LOS" if p.get("stop_los") else "")
    if p.get("door") or p.get("ufo_door"):
        return "structural", "дверь"
    if walk and fill is not None and fill[0] >= 200 and layers >= 2 and all(np.diff(fill[:layers]) <= 0) \
            and fill[layers - 1] <= 0.7 * fill[0]:          # сужается кверху; куб-ящик MUJUNGLE_2 34 - нет
        prof = "/".join(str(int(v)) for v in fill[:layers])
        # негорючее (земля, камень, бетон) - рельеф уверенно; горючее - это и травяной холм FOREST 31, и кресло
        # MANSIONFURNITURE 11, и диван SLUM_FURNITURE 10: объёмом не делятся, решает человек на карточке
        if p.get("flammable", 255) >= 255:
            return "structural", "рельеф: пандус, холм, куча (слои %s)" % prof
        return UNCERTAIN, "рельеф или предмет? горит (%d), слои %s" % (p.get("flammable", 0), prof)
    if info["in_floor"] >= 0.92 and info["h"] <= 18 and (layers is None or layers <= 1 or walk) and cover >= 0.3:
        return "floor_like", "плоское: в ромбе пола %.0f%%, ромб закрыт на %.0f%%, высота %d, слоёв %s" % (
            info["in_floor"] * 100, cover * 100, info["h"], layers)
    return "object", ""


if __name__ == "__main__":
    import map_mockup as mm
    st = Struct(mm.World())
    infos = []
    for k in sys.argv[1:]:
        s, f = k.split(":")
        i = st.info(s, int(f))
        infos.append(i)
        print(k, asset_class(i), {kk: v for kk, v in i.get("phys", {}).items() if v}, "h", i.get("h"),
              "area", i.get("area"))
    if len(infos) == 2:
        print(alt_view(infos[0], infos[1], 1.0))
