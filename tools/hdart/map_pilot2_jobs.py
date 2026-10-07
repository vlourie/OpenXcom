r"""Задания расширенного графического пилота карт (06.10): стены SCC 69/70, фасад с окном и анимированной дверью,
крыша, покрытия. Генерацию НЕ запускает - собирает для каждого задания всё, что нужно генератору и приёмке:

  - реальные записи MCD по кадрам (номер записи, кадры анимации, слот, P_Level, LOFT, die/alt) - из сейвов мест;
  - классические референсы: кадр из art/TERRAIN и места на картах (refs/<место>: классика x4 и нынешний пак
    одной камерой и одним светом, лист compare.png, числа stats.json - pilot2_refs.py / pilot2_compare.py);
  - маски защищённой геометрии (geom_mask.build: силуэт, solid, open, границы рамп) - census/maps/pilot2/masks;
  - блок ракурса и света из battle_view.prompt_block (свои слова ракурса не пишем);
  - проверки приёмки с порогами.

  py -3.13 map_pilot2_jobs.py            собрать census/maps/pilot2/jobs/*.json, маски недостающих записей и index.json

Покрытия идут отдельным способом (material): одна бесшовная текстура материала в мировых координатах, вид
строго сверху, кадры собираются из неё детерминированно. SCC стен их не исправляет.
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import map_truth as mt
import battle_view as bv
import geom_mask as gm

sys.stdout.reconfigure(encoding="utf-8")
ROOT = mt.ROOT
P2 = ROOT / "census" / "maps" / "pilot2"
REFS = P2 / "refs"
MASKS = P2 / "masks"
JOBS = P2 / "jobs"
ART = ROOT / "art" / "TERRAIN"
STATUS = "не запускалось: генерация только по слову Vitali"
# порядок пилота (07.10): тротуар с бордюрами, проезжая часть, прочие стыки -> природные (с водой и берегом) -> фасад с окнами и дверями ->
# крыша и перекрытие -> варианты прямых стен; следующее задание - только после приёмки предыдущего
ORDER = ["sidewalk_job1", "road_asphalt", "mat_asphalt", "mat_earth", "mat_forest", "mat_jungle", "mat_shore",
         "window_71_72", "door_ufo_62", "door_swing_27_28", "mat_tile", "roof_82", "wall_scc_69_70"]

# место пилота -> (сейв, центр окна); сами копии сейвов - refs/<место>/site.sav
SITES = {
    "facade": ("STR_LOC_TRAITORS_335", (10, 27, 0)),
    "facade2": ("EUROSYNDICATE_ELIMINATION_53", (37, 22, 0)),
    "roof_z2": ("STR_LOC_TRAITORS_155", (18, 32, 2)),   # крыша URBAN кадр 82 над центром
    "roof_z1": ("STR_LOC_TRAITORS_155", (18, 32, 1)),   # перекрытие второго этажа - URBAN запись 74 (кадр 78)
    "roof_z0": ("STR_LOC_TRAITORS_155", (18, 32, 0)),   # первый этаж, лестница 55/56 в 4 клетках от центра
    "asphalt": ("STR_LOC_ARSENAL_85", (41, 49, 0)),        # проезжая часть: стыки URBANDIO01 / EXPANDEDTERROR10 / 08
    "asphalt2": ("STR_ERIDIAN_TERROR_106", (61, 45, 0)),
    "asphalt_corner": ("STR_ERIDIAN_TERROR_139", (51, 11, 0)),   # угол URBAN02 (ROADS:7) у полос тротуара
    "port": ("WITCH_QUEST_RAGNAROCK_4", (16, 29, 0)),
    "tile": ("EUROSYNDICATE_ELIMINATION_368", (27, 44, 0)),
    "earth": ("STR_LOC_DOOMED_FARM_5", (26, 39, 0)),
    "beach": ("LOC_BEACH_SWEEP_2", (26, 41, 0)),
    "forest": ("STR_LOC_MONSTER_HUNT_PRIMAL_WEREWOLF_2", (38, 9, 0)),
    "jungle": ("STR_LOC_BEASTMEN_ALTAR_1", (14, 24, 0)),
}

# меры покрытия против классики (pilot2_compare: по видимым ромбам, пар исключён). С 07.10 числа цвета и фактуры -
# ДИАГНОСТИКА, а не ворота: они не заставляют воспроизводить пиксельный шум классики и не бракуют допустимые блики;
# принимает лист собранного участка (классика | новое при одном свете) глазами
MATERIAL_GATES = {
    "decision": "лист собранного участка классика | новое при одном свете; числа ниже - диагностика, не ворота",
    "dE_mean_lab": "диагностика: ~4 (средний цвет материала; связанные кадры - один опорный цвет)",
    "contrast_ratio": "диагностика: ~0.8 .. 1.5 (СКО L пак / классика: ровное не делать фактурным, R-039; ниже - зерно потеряно)",
    "coherence_delta": "диагностика: ~+0.10 к классике (направленность: борозды на ровном асфальте)",
    "lowfreq_ratio": "диагностика: ~1.5 (низкие частоты: бугры вместо низкой фактуры)",
    "ramp_edges": "границы рамп классики (граница материалов, бордюр, разметка) на месте в пределах 1 пикс базы - лист с красной линией",
    "field_9x9": "лист поля 9x9 из вариантов раскладкой движка (ground_field.py - порт groundFrameFor со смешением"
                 " на краях пятен): без решётки периода клетки, борозд, тёмных клеток и разрывов цвета (R-039, R-118)",
    "variants": "все варианты кадра (.v1..vN) перерисованы вместе с основным: старые не остаются в узоре groundFrameFor",
    "in_game": "дампы мест пилота: классика x4 | пак при одном свете; числа pilot2_compare по каждому виду",
}
GEOM_GATES = {
    "silhouette_iou": ">= 0.97 против силуэта классики того же кадра (geom_mask.check)",
    "hole_vs_classic": "видимый проём HD против видимого проёма классики (envelope минус силуэт): IoU >= 0.90 и сдвиг"
                       " центра <= 2.0 пикс x4; заложенный целиком проём - FAIL (geom_mask.check, tools/test_geom_mask_hole.py)",
    "loft": "LOFT - отдельная строка механики (open_covered_new, fake_hole); MCD не меняется. Рама, переплёт и стекло"
            " классики в механическом проёме - не дефект",
    "open_covered_new": "<= 8 пикс x4: HD не закрывает проём, где механика пропускает взгляд и выстрел",
    "fake_hole": "<= 8 пикс x4: HD не рисует дыру в механически сплошной части",
    "overlay": "наложение классика/HD в общих координатах: контур, проём, границы поверхностей - лист",
    "in_game": "дамп места пилота с HD против классики, затем ход в игре: окна - видимость и выстрел через проём;"
               " двери - полный цикл открытия (каждый кадр петли) и проход; механика та же, картинка не врёт",
    "classic_zone": "защищённая зона - не только LOFT: силуэт и видимый проём классики каждого кадра, привязки (alt, die)"
                    " и все состояния анимации (census/maps/pilot2/masks/mask_vs_classic.json)",
}

# задания: id -> описание
JOBS_DEF = [
    dict(id="wall_scc_69_70", kind="wall", sites=["facade", "facade2", "tile", "roof_z0"],
         members=[("URBAN", "f", 69, "north"), ("URBAN", "f", 70, "west")],
         linked=[("URBAN", "f", 74, "north"), ("URBAN", "f", 75, "west")],
         method=dict(name="scc_variants", address_txt="version: 1\nframes: 69:north:6 70:west:6",
                     variants="69.north1..5 и 70.west1..5 - тот же материал стены, другая мелкая деталь поверхности;"
                              " общая полоса стыка у всех вариантов (контракт SCC, раздел 7)",
                     linked_rule="разрушенный вид 74/75 - основным кадром, без адресации (ворота scc_gate: только то же n)"),
         gates=dict(GEOM_GATES, scc_gate="tools/hdart/scc_gate.py URBAN address.txt - ПРОХОДИТ",
                    seam="лист контракта SCC раздел 7: стык соседних вариантов на собранной карте")),
    dict(id="window_71_72", kind="wall", sites=["facade", "facade2"],
         members=[("URBAN", "f", 71, "north"), ("URBAN", "f", 72, "west")],
         method=dict(name="frame_edit",
                     rule="HD сравнивается с ВИДИМЫМ проёмом классики, LOFT - отдельно, как механика. LOFT записей"
                          " 67/68 пуст в слоях 10..21 на всю ширину стены - сквозная щель без косяков; классика рисует"
                          " в ней раму с неравными косяками, средний переплёт, перемычку и подоконник (1492-1513 пикс"
                          " x4 прозрачного против 2967 механического) - это рисунок окна, не дефект. Сдвиг центра"
                          " видимого проёма от механического (71: 1.6, 72: 2.4 пикс x4) объяснён разложением"
                          " (mask_vs_classic.json, shift_split): почти весь - от закрашенного рамой внутри щели (у 72"
                          " слева 679, справа 1040 пикс), то есть окно в классике смещено в клетке; чистым переносом"
                          " не объясняется. Рама и проём HD - по классике до пикселя x4, прозрачное классики остаётся"
                          " прозрачным; MCD не меняется"),
         gates=GEOM_GATES),
    dict(id="door_ufo_62", kind="wall", sites=["facade", "facade2"],
         members=[("URBAN", "r", 62, None), ("URBAN", "r", 63, None)],
         linked=[("URBAN", "r", 64, None)],
         method=dict(name="frame_edit_animation",
                     rule="все кадры петли одной серией (R-071): закрытое, каждый кадр анимации, открытое (alt);"
                          " неподвижные части (косяк, порог) у всех кадров совпадают до пикселя x4; створка по"
                          " траектории классики, силуэт каждого кадра - свой. Зона кадров петли - ТОЛЬКО по классике:"
                          " механика пропускает всю створку с первого кадра открытия, а рисунок открыт на 35, 65 и"
                          " 95 процентов (центр видимого проёма в 27, 17, 3 пикс x4 от механического); у открытой"
                          " записи 63 сплошных вокселей нет вовсе. Разрушенная дверь - запись 64 (die), кадр 68"),
         gates=dict(GEOM_GATES, anim_static="неподвижные части кадров совпадают: разница вне створки <= 8 пикс x4",
                    anim_path="габарит створки по кадрам = габарит классики +-1 пикс базы")),
    dict(id="door_swing_27_28", kind="wall", sites=["facade", "facade2"],
         members=[("URBAN", "r", 27, None), ("URBAN", "r", 28, None)],
         method=dict(name="frame_edit", rule="закрытая и открытая (alt) - пара: проём и петли на одном месте"),
         gates=GEOM_GATES),
    dict(id="roof_82", kind="floor", sites=["roof_z2", "roof_z1", "roof_z0"],
         members=[("URBAN", "f", 82, "floor"), ("URBAN", "r", 55, None), ("URBAN", "r", 56, None)],
         method=dict(name="material+frame_edit",
                     rule="крыша - материал (вид сверху) с краями по силуэту; стык со стенами 69/70 и лестницей;"
                          " проверка при переключении этажа (дампы viewLevel 0 и 1)"),
         gates=dict(GEOM_GATES, **{k: v for k, v in MATERIAL_GATES.items() if k != "in_game"},
                    separate="крыша (кадр 82) и межэтажное перекрытие (кадр 78) принимаются отдельно",
                    levels="дампы roof_z2, roof_z1 и roof_z0 одного дома: крыша (кадр 82) на этаже 2, перекрытие"
                           " (кадр 78, задание mat_tile) на этаже 1, лестница 55/56 на этаже 0 - края, проёмы и что"
                           " скрывается при каждом этаже обзора")),
    # остальные стыки дороги - после sidewalk_job1 и road_asphalt, из их материалов
    dict(id="mat_asphalt", kind="floor_unrolled", sites=["asphalt", "asphalt2", "port"],
         members=[("ROADS", "f", k, "floor") for k in (3, 4, 5, 6, 8)]
         + [("PORTROADS", "f", k, "floor") for k in (8, 10, 11, 12, 13, 14, 61)],
         linked=[("ROADS", "f", 0, "floor"), ("ROADS", "f", 9, "floor"),
                 ("ROADS", "f", 15, "object"), ("ROADS", "f", 16, "object")],
         defects="ROADS:3-6, 8 - бордюр пропал, клетка тёмная целиком; материалы тротуара и асфальта берутся из"
                 " принятых sidewalk_job1 и road_asphalt",
         method=dict(name="material"), gates=MATERIAL_GATES),
    # первое задание пилота (07.10): «тротуар ROADS с бордюрами» - связанный участок целиком: тротуар с вариантами,
    # бордюры 1, 2 и угол 7; проезжая часть и прочие бордюры - соседи стыка, остаются старыми до своих заданий
    dict(id="sidewalk_job1", kind="floor_unrolled", sites=["asphalt_corner", "asphalt", "asphalt2"],
         members=[("ROADS", "f", 0, "floor"), ("ROADS", "f", 1, "floor"), ("ROADS", "f", 2, "floor"),
                  ("ROADS", "f", 7, "floor")],
         linked=[("ROADS", "f", 9, "floor"), ("ROADS", "f", 11, "floor"), ("ROADS", "f", 3, "floor"),
                 ("ROADS", "f", 4, "floor")],
         defects="ROADS:0 - в классике ровная серая поверхность с мелкими вкраплениями, в HD крупные плитки,"
                 " направленные швы и борозды (у всех вариантов 0.v1-v3 - «пашня») - это смена материала; HD светлее"
                 " классики (L* 37 против 27); ROADS:1, 2, 7 - бордюр потерял чёткую форму, кадр тёмный целиком:"
                 " тротуар внутри них L* 17-18 против 37 у ROADS:0 (в классике везде 27) - тёмные клетки вдоль края",
         method=dict(name="material",
                     title="тротуар ROADS с бордюрами",
                     material="ровное крапчатое серое покрытие тротуара: материал и тон из классики, мелкая"
                              " ненаправленная фактура; без плиточной кладки, кирпичей, борозд и выпуклости клетки",
                     frames="один общий материал тротуара -> основа 0, варианты 0.v1-v3 и поверхность тротуара в"
                            " бордюрах 1, 2, 7; бордюры сохраняют положение, ширину и силуэт классики",
                     variants="0 и 0.v1-v3 - одинаковый основной тон и масштаб фактуры; различия - только слабые"
                              " пятна износа и мелкие детали, которые после смешения не образуют полос и лоскутов",
                     kerbs="1, 2, 7 - поверхность тротуара совпадает с ROADS:0; тёмной остаётся полоса бордюра на"
                           " исходном месте (в развёртке клетки от 0.656 до края: у 1 по u, у 2 по v, у 7 обе),"
                           " ширина, угол и силуэт классики, край - прямая линия без лесенки",
                     acceptance="новый результат на перекрёстке STR_ERIDIAN_TERROR_139 (CORNER_AT) и поле 9x9 с"
                                " вариантами раскладкой движка, рядом с классикой и нынешним HD в одном масштабе"
                                " (tools/hdart/sidewalk_probe.py sheet)",
                     probe="одна проба общего материала: tools/hdart/sidewalk_probe.py, Qwen-Image-2.1 по замку"
                           " модели; только по слову Vitali, через gpuq",
                     neighbours="ROADS:9, 11 (проезжая часть) и бордюры 3, 4 - соседи стыка, старые; не перерисовываются",
                     not_control="URBAN:52 исключён из контроля и из заданий покрытия до опознания; полосы кадра"
                                 " сохраняются точно (census/maps/pilot2/identity/URBAN_52)",
                     sheet="census/maps/pilot2/sheets/job1_sidewalk.png (tools/hdart/pilot2_job_sheet.py): кадры,"
                           " собранный участок STR_ERIDIAN_TERROR_139 и поле 9x9 с вариантами раскладкой движка",
                     model="выбирается по одному пробному результату, по слову Vitali"),
         gates=MATERIAL_GATES),
    # проезжая часть - отдельное обязательное задание; кадры подтверждены классической сборкой блоков
    # (census/maps/pilot2/identity/ROADS_9 .. ROADS_13, tools/hdart/frame_context.py)
    dict(id="road_asphalt", kind="floor_unrolled", sites=["asphalt", "asphalt_corner"],
         members=[("ROADS", "f", k, "floor") for k in (9, 10, 11, 12, 13)],
         linked=[("ROADS", "f", k, "floor") for k in (1, 2, 3, 4)],
         defects="ROADS:9 - размазня; разметка 10-12 и решётка 13 - проверить по листу задания",
         method=dict(name="material",
                     title="асфальт проезжей части",
                     confirmed="ROADS:9 - проезжая часть: URBAN00/01 и EXPANDEDTERROR03-10 - полоса между бордюрами"
                               " 2/3 или 1/4 со штриховой осью 10/11 и решёткой стока 13; CULTA_ROAD_WE00/SN00,"
                               " FOREST_ROAD_* - дорога через поле и лес; ещё стоянки (INDUSTRIALSLUMHUGE01,"
                               " EXPANDEDTERROR18/21, D_TAVERN, PRECINT_MEY_01, URBAN09d)",
                     frames="один общий материал асфальта -> 9 с новыми вариантами 9.v1-v3 (сейчас вариантов нет) и"
                            " асфальт в 10-13; белая линия 10/11/12 (индекс 240) и решётка 13 - защищённые детали,"
                            " положение и ширина по классике",
                     model="тот же способ, что принят на sidewalk_job1"),
         gates=MATERIAL_GATES),
    dict(id="mat_tile", kind="floor_unrolled", sites=["tile", "facade", "roof_z1", "roof_z0"],
         members=[("URBAN", "f", 80, "floor"), ("URBAN", "f", 78, "floor"), ("URBAN", "f", 40, "floor"),
                  ("URBAN", "f", 25, "floor")],
         defects="URBAN:78 - белые края; URBAN:80 - швы крестом",
         method=dict(name="material"), gates=MATERIAL_GATES),
    dict(id="mat_earth", kind="floor_unrolled", sites=["earth"],
         members=[("CULTIVAT", "f", 0, "floor"), ("CULTIVAT", "f", 2, "floor"), ("CULTIVAT", "f", 3, "floor"),
                  ("BARN", "f", 0, "floor"), ("BARN", "f", 19, "floor")],
         linked=[("CULTIVAT", "f", 4, "object")],
         defects="CULTIVAT - бугры и сдвиг в красное",
         method=dict(name="material"), gates=MATERIAL_GATES),
    dict(id="mat_shore", kind="floor_unrolled", sites=["beach"],
         members=[("BEACH", "f", k, "floor") for k in (83, 98, 79, 99, 113, 110, 32, 40, 46)]
         + [("SAVANNABEACH", "f", 2, "floor"), ("SAVANNABEACH", "f", 65, "floor"),
            ("JUNGLEBITS", "f", 0, "floor"), ("JUNGLEBITS", "f", 52, "floor")],
         defects="BEACH - песок буграми, вода гладкая; переход берега",
         method=dict(name="material", transitions="вода | берег | песок: переход по рампам классики, не своей линией",
                     water="вода, рябь и переход вода -> берег -> земля входят в береговой пилот целиком"),
         gates=MATERIAL_GATES),
    dict(id="mat_forest", kind="floor_unrolled", sites=["forest"],
         members=[("FOREST", "f", k, "floor") for k in (0, 1, 2, 4, 5)],
         linked=[("FOREST", "f", k, "object") for k in range(42, 58)] + [("FORESTBITS2", "f", k, "object") for k in (9, 10, 11)],
         defects="FOREST:0 - оливковый вместо травы",
         method=dict(name="material"), gates=MATERIAL_GATES),
    dict(id="mat_jungle", kind="floor_unrolled", sites=["jungle"],
         members=[("JUNGLE", "f", k, "floor") for k in (0, 43, 45, 52, 53, 54)]
         + [("JUNGLYROAD", "f", k, "floor") for k in range(0, 20)],
         linked=[("JUNGLE", "f", 1, None), ("JUNGLE", "f", 69, "object")],
         defects="JUNGLE - разный тон частей одного покрытия",
         method=dict(name="material"), gates=MATERIAL_GATES),
]

MATERIAL_METHOD = dict(
    steps=[
        "1. Разбить кадры задания на материалы по рампам классики (индекс // 16): пол, бордюр, разметка, основания"
        " предметов - один материал, если рампа и тон общие (связанные поверхности)",
        "2. Опорный цвет материала - средний Lab классики при тени 0 на всех его кадрах; связанные кадры берут один",
        "3. Одна бесшовная текстура материала в мировых координатах, вид строго сверху (battle_view floor_unrolled),"
        " масштаб фактуры от клетки: 1 клетка = 16x16 вокселей; характер оригинала - ровное ровным, низкая"
        " фактура низкой",
        "4. Кадр = аффинное отображение участка текстуры по мировым координатам клетки в ромб 2:1 x4, маска - силуэт"
        " классики (geom_mask sil), границы материалов внутри кадра - по границам рамп классики (edges)",
        "5. Не меньше 3 вариантов каждого частого кадра (.v1..v3) из разных участков той же текстуры: стык"
        " вариантов непрерывен по построению, решётки нет",
        "6. Возврат тона по клетке к опорному цвету (низкие частоты), не к пикселям классики",
    ],
    why="кадр, нарисованный отдельно, не стыкуется с соседями и уводит цвет (R-005, R-016, R-039); текстура в мировых"
        " координатах даёт непрерывность и один цвет по построению",
)


def record_of(data, sname, how, num):
    """Номера записей MCD набора: 'r' - сама запись, 'f' - записи, у которых Frame[0] == num."""
    recs = data.mcd(sname)
    if how == "r":
        return [num] if num < len(recs) else []
    return [i for i, r in enumerate(recs) if r["frames"][0] == num]


def site_save(site):
    p = REFS / site / "site.sav"
    return p if p.exists() else None


def refs_of(site):
    d = REFS / site
    out = dict(site=site, save=SITES[site][0], center=list(SITES[site][1]), dir=str(d.relative_to(ROOT)))
    for f in ("classic_map.png", "pack_map.png", "compare.png", "stats.json"):
        out[f.split(".")[0]] = (str((d / f).relative_to(ROOT)) if (d / f).exists() else None)
    if (d / "stats.json").exists():
        out["measured"] = json.loads((d / "stats.json").read_text(encoding="utf-8-sig"))
    return out


def main():
    JOBS.mkdir(parents=True, exist_ok=True)
    index = {}
    for job in JOBS_DEF:
        saves = [s for s in (site_save(x) for x in job["sites"]) if s]
        if not saves:
            print(job["id"], "нет сейвов мест - сначала pilot2_refs.py")
            continue
        battles = [mt.Battle(s) for s in saves]
        resolved, missing, want_masks = [], [], []
        for role, lst in (("member", job["members"]), ("linked", job.get("linked", []))):
            for sname, how, num, slot in lst:
                hit = None
                for s, bt in zip(saves, battles):
                    if sname in bt.sets:
                        recs = record_of(mt.Data(bt.mods), sname, how, num)
                        if recs:
                            hit = (s, recs)
                            break
                if not hit:
                    missing.append("%s %s%d" % (sname, how, num))
                    continue
                s, recs = hit
                for r in recs:
                    want_masks.append((s, "%s#%d" % (sname, r)))
                    resolved.append(dict(role=role, set=sname, record=r, by=("frame %d" % num if how == "f" else "record"),
                                         slot=slot, classic_sheet=str((ART / (sname + ".PCK") / "original.png").relative_to(ROOT)),
                                         masks=str((MASKS / ("%s_%d" % (sname, r))).relative_to(ROOT))))
        # маски недостающих записей
        by_save = {}
        for s, it in want_masks:
            if not (MASKS / it.replace("#", "_") / "masks.json").exists():
                by_save.setdefault(s, []).append(it)
        for s, items in by_save.items():
            out = MASKS / ("_build_" + job["id"])
            gm.build(str(s), str(out), sorted(set(items)))
            for it in sorted(set(items)):
                src = out / it.replace("#", "_")
                dst = MASKS / it.replace("#", "_")
                if src.exists() and not dst.exists():
                    src.rename(dst)
        for m in resolved:
            mj = ROOT / m["masks"] / "masks.json"
            if mj.exists():
                info = json.loads(mj.read_text(encoding="utf-8-sig"))
                m.update(frames=info["frames"], tile_type=info["tile_type"], p_level=info["yoff"], loft=info["loft"],
                         door=info["door"], ufo_door=info["ufo_door"], alt=info["alt"], die=info["die"],
                         stop_los=info["stop_los"], solid_px=info["solid_px"], open_px=info["open_px"],
                         per_frame=info["per_frame"])
        kind = job["kind"]
        method = dict(job["method"])
        if method.get("name") == "material":
            method.update(MATERIAL_METHOD)
        doc = dict(id=job["id"], status=STATUS, view=kind, prompt_block=bv.prompt_block(kind),
                   view_rules=bv.KINDS[kind]["rules"], defects_now=job.get("defects"),
                   records=resolved, not_found=missing, method=method, gates=job["gates"],
                   sites=[refs_of(x) for x in job["sites"]])
        p = JOBS / (job["id"] + ".json")
        p.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8-sig")
        index[job["id"]] = dict(records=len(resolved), not_found=missing, file=str(p.relative_to(ROOT)))
        print(job["id"], "записей", len(resolved), "не найдено", missing)
    assert sorted(ORDER) == sorted(j["id"] for j in JOBS_DEF), "ORDER и JOBS_DEF разошлись"
    index = dict(order=ORDER, jobs={k: index[k] for k in ORDER if k in index})
    (JOBS / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8-sig")


if __name__ == "__main__":
    main()
