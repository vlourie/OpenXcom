#!/usr/bin/env python3
"""Перепись существующих откровенных (18+, нагота) вариантов внешности юнитов в бою X-Piratez.

Только читает игру и перепись юнитов, ничего не генерирует (HD_UNITS.md, раздел 12, решение 8).

    set PYTHONIOENCODING=utf-8
    py -3.13 tools/unit_explicit.py              # таблица, обзорный лист, справочные числа
    py -3.13 tools/unit_explicit.py --review     # плюс листы ВСЕХ кукол для просмотра глазами

Как ищется (каждая находка - с источником):
  * текст: ID брони, её название (Language/*.yml активных модов + extraStrings, позже - сильнее),
    статья педии брони (ufopaedia id = ufopediaType или ID брони), ID трупа, имя куклы spriteInv;
    слова: nude, naked, topless, nudity, голая/голый/голыш, нагота, обнаж, топлес, стрип...;
    купальник, бельё, бикини - отдельно: это одежда, кандидат, а не находка;
  * кукла инвентаря собирается так, как её рисует движок (InventoryState::init):
    слоёная броня - слои layersDefinition по порядку списка, имя <префикс>__<номер>__<элемент>
    (Armor::afterLoad), версия <M|F><look> (Soldier::getArmorLayers); иначе spriteInv:
    <spriteInv><M|F><look>.SPK, <spriteInv>.SPK, <spriteInv> (+ <spriteInv>M0.SPK у чужих);
    индексы, индекс 0 прозрачен (R-043), палитра боя мастер-мода;
  * мера для слоёной: какая доля пикселей «голого» базового слоя (элемент с NUDE) осталась видна
    после одежды, отдельно в зоне груди и в зоне паха; зоны - по слою купальника той же версии
    (BIKINI_<версия> у Убер-девочек), верх и низ купальника;
  * решение «откровенно / нет» - глазами, по листам кукол (--review), записано ниже в VERDICTS
    с причиной; кукла, которой нет в VERDICTS, выходит со статусом unsure;
  * лист боя и труп - тот же просмотр: стоящий юнит направления 3 (UnitSprite::drawRoutine0:
    ноги 16, торс 32 / 267, руки 0 / 8), последний кадр смерти, картинка трупа BIGOBS.

Пара «откровенный - обычный» берётся только из данных:
  * soldiers: armorForAvatar (кукла бойца на базе) и armor (броня по умолчанию) одного типа бойца;
  * тот же базовый слой тела (один и тот же <префикс>__2__<версия>_NUDE) у слоёной брони;
  * семейство листа боя (census/units/families.tsv) - как подтверждение «тот же скелет».

Вывод: census/units/explicit_variants.tsv, art/_review/units-18plus/explicit_overview.png,
rejected_overview.png, review/*.png (с --review), справка docs/research/units-explicit-variants.md
пишется руками по этим числам.
"""
from __future__ import annotations

import argparse
import colorsys
import csv
import hashlib
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import yaml
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import unit_census as uc  # noqa: E402

ENC = "utf-8-sig"
ROOT = uc.ROOT
CENSUS = ROOT / "census" / "units"
REVIEW = ROOT / "art" / "_review" / "units-18plus"
FONT = "C:/Windows/Fonts/arial.ttf"

# ------------------------------------------------------------------ слова

# нагота прямо
RX_NUDE_EN = re.compile(r"\b(nude|naked|topless|nudity|bottomless|in the buff|birthday suit|stripper|striptease)\b", re.I)
RX_NUDE_RU = re.compile(r"(гол(ая|ый|ые|ой|ую|ых|ыш\w*)\b|\bнаг(ая|ой|ие|ую|их|ота|оту|оты|ишом)\b|обнаж|топлес|стрип|раздет|раздева|догола)", re.I)
# одежда, которая может быть откровенной, - только кандидат
RX_SKIMPY_EN = re.compile(r"\b(bikini|lingerie|underwear|panties|pantless|thong|bra|teddy|swimsuit|loincloth|erotic|sexy)\b")
RX_SKIMPY_RU = re.compile(r"(бикини|бель[её]|трусик|трусел|трусы|купальн|набедрен|эрот)", re.I)
# тело, без вывода
RX_BODY = re.compile(r"\b(boobs?|tits|nipples?|breasts?)\b|сиськ|сосок|соски", re.I)

# ------------------------------------------------------------------ решения по просмотру глазами
# armor -> (inv, battle, corpse, причина); статусы confirmed / rejected / unsure / "" (нет вида)
# Заполнено по листам art/_review/units-18plus/review/*.png (03.10).
# броня-представитель группы одинаковых кукол -> (статус, вид наготы, что видно);
# решение действует на все брони с той же куклой (тот же хэш составной картинки)
VERDICTS: dict[str, tuple[str, str, str]] = {
    "STR_ARMOR_SAINT_FAKE_UC": ("confirmed", "голая", "голое тело, нимб"),
    "STR_PIR_NUDE_DREAMLAND_UC": ("confirmed", "голая", "голое тело"),
    "STR_PATIENT_OUTFIT_UC": ("confirmed", "топлес", "топлес, трусики, маска"),
    "STR_PIR_TOPLESS_UC": ("confirmed", "топлес", "топлес, стринги"),
    "STR_PIR_CHAINS_UC": ("confirmed", "голая", "голое тело, кандалы"),
    "STR_BRAINER_OUTFIT_SEA_UC": ("confirmed", "топлес", "топлес, стринги, перчатки"),
    "STR_PIR_SLAVE_ARMOR_FAKE_UC": ("confirmed", "голая", "голое тело, ошейник и ремни"),
    "STR_PIR_MINX_UC": ("confirmed", "топлес", "топлес, стринги, плащ и шляпа"),
    "STR_AMAZON_ARMOR_SEA_UC": ("confirmed", "голая", "голое тело, наручи и гетры"),
    "STR_HYENA_RIDER_ARMOR_UC": ("confirmed", "голая", "голое тело верхом на гиене"),
    "STR_THEBAN_DRESS_SEA_UC": ("confirmed", "топлес", "топлес, бусы-стринги"),
    "STR_THEBAN_DRESS_UC": ("confirmed", "топлес", "топлес, юбка"),
    "STR_SAVAGE_ARMOR_UC": ("confirmed", "топлес", "топлес, ремни, набедренник"),
    "STR_PIR_GREMRIN_DREAMLAND_UC": ("confirmed", "топлес", "топлес, ремни, крылья"),
    "STR_SWIFTSUIT_SEA_UC": ("confirmed", "топлес", "ремни сбруи, грудь открыта"),
    "STR_HOLOSUIT_UC": ("unsure", "топлес", "голографические полосы поверх груди"),
    "STR_LINGERIE_SET_X_UC": ("confirmed", "топлес", "открытые чашки, сетка"),
    "STR_HERMIT_UC": ("confirmed", "топлес", "грудь открыта под тёмным плащом"),
    "STR_NEKO_NUDE_UC": ("confirmed", "голая", "голое тело"),
    "STR_HYBRID_NUDE_DREAMLAND_UC": ("confirmed", "голая", "голое тело"),
    "STR_GNOME_NUDE_DREAMLAND_UC": ("confirmed", "голая", "голое тело"),
    "STR_LAMIA_NUDE_DREAMLAND_UC": ("confirmed", "топлес", "топлес, хвост ламии"),
    "STR_PEASANT_NUDE_DREAMLAND_UC": ("confirmed", "голая", "голое тело"),
    "STR_SYNTH_NUDE_SEA_UC": ("confirmed", "голая", "голое тело, вид со спины"),
    "STR_CHORT_ARMOR_UC": ("confirmed", "голая", "демоническое тело без одежды, грудь"),
    "STR_OGRE_NUDE_DREAMLAND_UC": ("confirmed", "голая", "голый мужчина-огр"),
    "STR_SLAVE_NUDE_DREAMLAND_UC": ("confirmed", "голая", "голый мужчина"),
    "STR_LOKNAR_NUDE_DREAMLAND_UC": ("confirmed", "голая", "голое тело"),
    "STR_HYBRID_THONG_SEA_UC": ("confirmed", "топлес", "топлес, стринги"),
    "STR_NIGHTGOWN_DREAMLAND_UC": ("unsure", "топлес", "сетчатая ночнушка, просвечивает"),
    "STR_SLAVE_ARMOR_SAINT_UC": ("confirmed", "голая", "голый мужчина, нимб"),
    "STR_PEASANT_ARMOR_SAINT_UC": ("confirmed", "голая", "голое тело, нимб"),
    "STR_RAGS_UC": ("confirmed", "голая", "лохмотья на плечах, тело спереди открыто"),
    "STR_PEASANT_MUD_UC": ("confirmed", "голая", "голое тело в грязи"),
    "STR_NEKO_BELLE_UC": ("confirmed", "топлес", "топлес, грудь прикрыта руками, стринги"),
    "STR_NEKO_PATIENT_OUTFIT_UC": ("confirmed", "топлес", "топлес, трусики"),
    "STR_SYNTH_REFRACTOR_UC": ("unsure", "голая", "вид со спины, ягодицы открыты, ремни"),
    "STR_PEASANT_BONDAGE_GEAR_UC": ("confirmed", "голая", "голое тело, сбруя"),
    "STR_SYNTH_NUDE_A_SPACE_UC": ("confirmed", "голая", "голое тело, вид со спины"),
    "STR_HYBRID_PSICRYSTAL_DREAMLAND_UC": ("confirmed", "голая", "голое тело, кристаллы"),
    "STR_LINGERIE_BRA_UC": ("confirmed", "голая", "только лифчик, низ открыт"),
    "STR_LAMIA_NUDE_S_UC": ("confirmed", "топлес", "топлес, щит"),
    "STR_NEKO_GRAV_ARMOR_UC": ("confirmed", "топлес", "топлес, стринги, ботинки"),
    "STR_PEASANT_ARMOR_HUNTER_UC": ("confirmed", "топлес", "топлес, набедренник"),
    "STR_GNOME_EXPERIMENT_UC": ("unsure", "топлес", "белые полосы поверх груди"),
    "STR_NEKO_HOLOSUIT_UC": ("unsure", "топлес", "голографические полосы поверх груди"),
    "RETICULAN_ARMOR_P1": ("unsure", "голая", "голый гуманоид-гибрид, признаки неясны"),
    "RETICULAN_ARMOR_P2": ("confirmed", "голая", "голое женское тело (рептилоид-сирена)"),
    "STR_LOST_SOUL_M_ARMOR": ("confirmed", "голая", "голый мужчина-зомби"),
    "STR_DAMSEL_VICTIM_ARMOR": ("confirmed", "голая", "голое тело, кандалы"),
    "ARMOR_AWAKENED_CORPSE": ("confirmed", "топлес", "топлес, ремень"),
    "STR_ARMOR_DOCTOR_X_GNOME": ("confirmed", "голая", "голое тело"),
    "STR_CAMO_PAINT_UC": ("confirmed", "голая", "голое тело в раскраске"),
    "ZOMBIE_CARRIE_ARMOR": ("confirmed", "голая", "голое тело (зомби)"),
    "UBER_BELTER_ARMOR": ("confirmed", "топлес", "топлес, стринги, сбруя"),
    "STR_NEKO_NUDE_DREAMLAND_UC": ("confirmed", "голая", "голое тело, руки на груди"),
    "CIV_ARMOR_MUT_4": ("confirmed", "топлес", "топлес, хвост ламии"),
    "STR_CIV_ARMOR_CASTAWAY_GAL": ("unsure", "топлес", "распахнутая прозрачная рубашка"),
    "STR_NEKO_CAMO_PAINT_UC": ("confirmed", "голая", "голое тело в раскраске"),
    "CIV_ARMOR_SLAVE_GLADIATRIX": ("confirmed", "топлес", "ремни вокруг открытой груди"),
    "STR_LOST_SOUL_F_ARMOR": ("confirmed", "голая", "голое тело (призрак)"),
    "DAMSEL_SACRIFICE_ARMOR": ("confirmed", "топлес", "топлес, стринги"),
    "GOLDEN_SAINT_2_ARMOR": ("confirmed", "голая", "голое тело, пламя"),
    "SUCCUBUS_ARMOR": ("confirmed", "топлес", "топлес, сбруя, крылья"),
    "CHURCH_ARMOR_P4": ("unsure", "", "название «(голая)», а кукла в купальнике"),
    "STR_BERSERKER_ARMOR_UC": ("confirmed", "голая", "голое тело в раскраске, плащ"),
    "STR_WRAITH_ARMOR": ("unsure", "голая", "голое тёмное тело (чудовище), деталей нет"),
    "STR_SPACE_POD_LAMIA_UC": ("confirmed", "топлес", "голое тело за стеклом капсулы"),
    "STR_WRAITH_FEM_ARMOR": ("confirmed", "голая", "голое женское тело (чудовище)"),
    "STR_SPACE_POD_UC": ("confirmed", "топлес", "голое тело за стеклом капсулы"),
    "STR_SPACE_POD_PEASANT_UC": ("confirmed", "топлес", "голое тело за стеклом капсулы"),
    "GHOST_0_ARMOR": ("confirmed", "голая", "голое тело (призрак)"),
    "STR_SPACE_POD_GNOME_UC": ("confirmed", "топлес", "голое тело за стеклом капсулы"),
    "SPIDERGIRL_ARMOR": ("confirmed", "голая", "голое женское тело (паучиха)"),
    "STR_SLIMEGAL_BODY_SEA_UC": ("confirmed", "голая", "голое тело (слизь)"),
    "STR_SPACE_POD_HYBRID_UC": ("confirmed", "топлес", "голое тело за стеклом капсулы"),
    "AUR_ARMOR_2": ("confirmed", "голая", "голое тело"),
    "HOLOGAL_ARMOR": ("confirmed", "топлес", "топлес, шорты"),
    "STR_NEKO_SPACE_POD_UC": ("confirmed", "топлес", "голое тело за стеклом капсулы"),
    "STR_SPACE_POD_LOKNAR_UC": ("unsure", "топлес", "капсула, тело за стеклом почти не видно"),
    "STR_STEALTH_ARMOR_SEA_UC": ("confirmed", "голая", "голое тело полупрозрачным растром"),
    "STYGIAN_GUARD_ARMOR": ("confirmed", "голая", "голый мужчина (чудовище)"),
    "STR_MAGICAL_GIRL_OUTFIT_SEA_UC": ("rejected", "", "бельё, грудь закрыта"),
    "STR_GNOME_BIKINI_SEA_UC": ("rejected", "", "бикини"),
    "STR_NEKO_BIKINI_UC": ("rejected", "", "бикини"),
    "STR_SLAVE_ARMOR_LOINCLOTH_SEA_UC": ("rejected", "", "мужчина в набедренной повязке"),
    "STR_SWIMSUIT_PEASANT_SEA_UC": ("rejected", "", "купальник"),
    "STR_GNOME_GLITTERARMOR_DREAMLAND_UC": ("rejected", "", "купальник"),
    "STR_OGRE_SWIM_SEA_UC": ("rejected", "", "мужчина в плавках"),
    "STR_LAMIA_STRAPS_UC": ("rejected", "", "грудь закрыта сбруей"),
    "STR_VOODOO_ARMOR_UC": ("rejected", "", "корсет, грудь закрыта"),
    "STR_PEASANT_GLITTERARMOR_DREAMLAND_UC": ("rejected", "", "купальник"),
    "STR_NURSE_OUTFIT_ADV_UC": ("rejected", "", "грудь закрыта"),
    "STR_LAMIA_SCALE_MAIL_UC": ("rejected", "", "чешуйчатая броня"),
    "STR_LINGERIE_TEDDY_UC": ("rejected", "", "боди"),
    "STR_SLAVE_ARMOR_TUNIC_A_UC": ("rejected", "", "мужской торс, туника"),
    "STR_SYNTH_CATSUIT_UC": ("rejected", "", "комбинезон"),
    "STR_PIR_ROGUE_UC": ("rejected", "", "одета"),
    "STR_GNOME_FIRESTARTER_UC": ("rejected", "", "ремни-купальник"),
    "STR_PEASANT_ARMOR_MILITIA_UC": ("rejected", "", "грудь закрыта"),
    "STR_PEASANT_ARMOR_GLADIATRIX_UC": ("rejected", "", "ремни поверх груди"),
    "STR_PARTY_DRESS_UC": ("rejected", "", "платье"),
    "STR_BARBARIAN_RAGS_UC": ("rejected", "", "купальник"),
    "STR_CLOTHING_UC": ("rejected", "", "вырез рубашки"),
    "STR_NEKO_UNIPUMA_UC": ("rejected", "", "одета"),
    "STR_PIR_SWASHBUCKLER_UC": ("rejected", "", "одета"),
    "STR_MEIDO_OUTFIT_UC": ("rejected", "", "платье горничной"),
    "STR_PIR_CASTAWAY_ARMOR_UC": ("rejected", "", "вырез рубашки"),
    "STR_BARBARIAN_ARMOR_UC": ("rejected", "", "лифчик и юбка"),
    "STR_BARBARIAN_ARMOR_S_UC": ("rejected", "", "лифчик и юбка"),
    "STR_FORCE_ARMOR_SEA_UC": ("rejected", "", "лифчик"),
    "STR_GRAV_ARMOR_UC": ("rejected", "", "сбруя закрывает грудь"),
    "STR_FORCE_ARMOR_UC": ("rejected", "", "лифчик"),
    "STR_LINGERIE_SET_UC": ("rejected", "", "платье"),
    "STR_AMAZON_ARMOR_UC": ("rejected", "", "бикини"),
    "STR_NURSE_OUTFIT_UC": ("rejected", "", "платье медсестры"),
    "STR_SWIMSUIT_SEA_UC": ("rejected", "", "купальник"),
    "STR_CHILLER_SEA_UC": ("rejected", "", "купальник"),
    "RETICULAN_ARMOR_P7": ("rejected", "", "пришелец без половых признаков"),
    "DANCER_ARMOR": ("rejected", "", "стриптизерша в бикини"),
    "RETICULAN_ARMOR_P0": ("rejected", "", "пришелец без половых признаков"),
    "STR_AURORA_DOLL_ARMOR_UC": ("rejected", "", "бикини"),
    "CIV_ARMOR_TRIBAL": ("rejected", "", "мужчина в набедренной повязке"),
    "HOE_ARMOR_P1": ("rejected", "", "лифчик и юбка"),
    "STR_BLITZ_ARMOR_SEA_UC": ("rejected", "", "одета"),
    "SMUGGLER_ARMOR_P2": ("rejected", "", "одета"),
    "STR_RUNT_OUTFIT_UC": ("rejected", "", "одета"),
    "STR_BIKINI_SEA_UC": ("rejected", "", "бикини"),
    "STR_ARMOR_RED_MAGE_BIKINI_SEA": ("rejected", "", "бикини"),
    "NINJA_ARMOR_1": ("rejected", "", "одета, вырез"),
    "ZOMBIE_SADAKO_ARMOR": ("rejected", "", "голый торс без половых признаков"),
    "HUMAN_ARMOR_F8": ("rejected", "", "комбинезон"),
    "CIV_ARMOR_BUSY_CATGIRL": ("rejected", "", "одета"),
    "GOLDEN_SAINT_1_ARMOR": ("rejected", "", "фигура в пламени, тела не видно"),
    "STR_ARMOR_RED_MAGE_DRESS": ("rejected", "", "платье"),
    "STR_SCOUT_OUTFIT_UC": ("rejected", "", "лифчик"),
    "RAIDER_ARMOR_P1": ("rejected", "", "бикини"),
    "SECTOID_ARMOR_P12": ("rejected", "", "купальник"),
    "RAIDER_ARMOR_P3": ("rejected", "", "бикини"),
    "STR_SPACE_POD_SLAVE_UC": ("rejected", "", "мужской торс в капсуле"),
    "BANDIT_ARMOR_P13": ("rejected", "", "мужчина в плавках"),
    "ARMOR_KOBOLD_HUNTRESS": ("rejected", "", "сетчатая броня"),
    "STR_CHORT_ARMOR_INFILTRATION_UC": ("rejected", "", "чёрный облегающий силуэт без деталей"),
    "STR_ARMOR_DOCTOR_X_KNIGHT": ("rejected", "", "только педия: без брони была бы голой; кукла в броне"),
    "STR_GNOME_EXPLORER_SEA_UC": ("rejected", "", "только педия: про ныряние голышом; кукла одета"),
}

# лист боя -> (статус, что видно); заполнено по листам review/battle_*.png
BATTLE: dict[str, tuple[str, str]] = {
    "BFARM_DEF.PCK": ("confirmed", "голое тело"),
    "AUR_02.PCK": ("confirmed", "голое тело"),
    "COS_3.PCK": ("rejected", "купальник, как у куклы"),
    "MUT_4.PCK": ("confirmed", "топлес, хвост ламии"),
    "PIR_563.PCK": ("confirmed", "ремни, грудь открыта"),
    "SACRIFICE1.PCK": ("confirmed", "голое тело у столба"),
    "GHOST_GAL.PCK": ("confirmed", "голое серое тело"),
    "AVT_2.PCK": ("confirmed", "голое тело"),
    "HOLOGAL.PCK": ("unsure", "голубой силуэт, деталей не разобрать"),
    "RET_1.PCK": ("unsure", "голый гуманоид, признаков не видно"),
    "RET_2.PCK": ("confirmed", "голое тело"),
    "SPIDERGIRL.PCK": ("confirmed", "голое зелёное тело"),
    "PIR_500.PCK": ("confirmed", "голое тело (общий лист голой пиратки)"),
    "PIR_901.PCK": ("confirmed", "голое тело"),
    "PIR_360.PCK": ("confirmed", "голое тело в сиянии"),
    "PIR_378.PCK": ("confirmed", "голое тело, тёмный плащ"),
    "PIR_281.PCK": ("confirmed", "топлес, перчатки"),
    "PIR_111.PCK": ("confirmed", "топлес"),
    "CHORT.PCK": ("unsure", "демон, кадр неразборчив"),
    "PIR_489.PCK": ("rejected", "обычный лист оборванки STR_PIR_CASTAWAY_ARMOR_UC"),
    "PIR_490.PCK": ("confirmed", "голое тело, ремни"),
    "PIR_903.PCK": ("unsure", "белые полосы поверх тела"),
    "PIR_484.PCK": ("unsure", "серый плащ, тело видно частично"),
    "PIR_460.PCK": ("unsure", "голое тело с точками голограммы"),
    "PIR_601.PCK": ("confirmed", "голое тело"),
    "PIR_637.PCK": ("confirmed", "голое тело"),
    "PIR_602.PCK": ("confirmed", "стринги"),
    "HYENA_RIDER.PCK": ("unsure", "большой юнит, кадр стоящего не собран"),
    "PIR_701.PCK": ("confirmed", "топлес, хвост ламии"),
    "PIR_452.PCK": ("confirmed", "лифчик, низ открыт"),
    "PIR_450.PCK": ("confirmed", "открытые чашки, сетка"),
    "PIR_801.PCK": ("unsure", "серое тело без деталей (цвет даёт скрипт)"),
    "PIR_551.PCK": ("confirmed", "голое тело"),
    "PIR_501.PCK": ("confirmed", "голый мужчина"),
    "XNEKO_009.PCK": ("confirmed", "топлес, стринги"),
    "XNEKO_050.PCK": ("confirmed", "голое тело в раскраске"),
    "XNEKO_100.PCK": ("confirmed", "топлес, ботинки"),
    "XNEKO_105.PCK": ("unsure", "голографические полосы"),
    "XNEKO_301.PCK": ("confirmed", "голое тело"),
    "XNEKO_008.PCK": ("confirmed", "голое тело"),
    "XNEKO_025.PCK": ("confirmed", "топлес, трусики"),
    "PIR_112.PCK": ("rejected", "закрытая капсула, тела не видно"),
    "PIR_455.PCK": ("rejected", "чёрная ночнушка"),
    "PIR_851.PCK": ("confirmed", "голый мужчина-огр"),
    "PIR_391.PCK": ("confirmed", "топлес"),
    "PIR_556.PCK": ("confirmed", "топлес"),
    "PIR_313.PCK": ("confirmed", "топлес, крылья"),
    "PIR_151.PCK": ("confirmed", "топлес, плащ"),
    "PIR_481.PCK": ("confirmed", "тело открыто, лохмотья"),
    "PIR_373.PCK": ("confirmed", "топлес"),
    "PIR_530.PCK": ("confirmed", "голый мужчина в сиянии"),
    "PIR_46.PCK": ("unsure", "растровый полупрозрачный силуэт"),
    "PIR_180.PCK": ("confirmed", "сбруя, грудь открыта"),
    "PIR_663.PCK": ("confirmed", "голое тело синта"),
    "PIR_668.PCK": ("confirmed", "голое тело синта"),
    "PIR_666.PCK": ("confirmed", "голое тело синта"),
    "PIR_667.PCK": ("unsure", "тело синта, как у голой"),
    "PIR_451.PCK": ("confirmed", "топлес, юбка"),
    "WRAITH.PCK": ("unsure", "тёмное тело без деталей"),
    "STYGIAN_GUARD.PCK": ("confirmed", "голый мужчина (чудовище)"),
    "SUCCUBUS.PCK": ("confirmed", "топлес, крылья"),
    "UBR_BLT.PCK": ("confirmed", "топлес"),
    "ZOMBIE_CARRIE.PCK": ("confirmed", "голое тело"),
}

# предмет трупа -> (статус, что видно)
# заполнено по листам review/battle_*.png и картинкам трупов BIGOBS (250 самых телесных из 573)
CORPSE: dict[str, tuple[str, str]] = {
    "STR_RETICULAN_2_CORPSE_BATTLE": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_DAMSEL_VICTIM_CORPSE": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_CORPSE_CASTAWAY": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_CORPSE_NEKO_NUDE": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_CORPSE_PEASANT_DRESS": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_CORPSE_PEASANT_GLITTER": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_CORPSE_NEKO_BELLE": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_CORPSE_NEKO_PATIENT": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_ZOMBIE_CARRIE_CORPSE": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_JUNGLE_GAL_CORPSE_BATTLE": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_CORPSE_GNOME_GLITTER": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_CORPSE_SAVAGE": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_CORPSE_PEASANT_HUNTER": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_CORPSE_PEASANT_NUDE": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_UBER_BELTER_CORPSE_BATTLE": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "CIVF_CORPSE": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "CIVF_CORPSE_TRAITOR": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_CORPSE_RAGS": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_CORPSE_PATIENT": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_CORPSE": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_CORPSE_PIR_MAGICAL_OUTFIT": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_CORPSE_PIR_NUDE": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_CORPSE_PIR_NUDE_DREAMLAND": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_DAMSEL_SACRIFICE_CORPSE": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_CORPSE_DOLL": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_CORPSE_TOPLESS": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_CORPSE_NEKO_NUDE_DREAMLAND": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_CORPSE_GOWN": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_CORPSE_NEKO_CAMO_PAINT": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_CORPSE_HOLOSUIT": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_CORPSE_STEALTH": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_CORPSE_DOCTOR_X_KNIGHT_GEO": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_CORPSE_PANTLESS": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_CORPSE_GNOME_NUDE": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_CORPSE_NEKO_GRAV_ARMOR": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_CORPSE_PIR_CLOTHING": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_ZOMBIE_SADAKO_CORPSE": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_CORPSE_BRAINER_SEA": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_CORPSE_GNOME_EXPLORER_SEA": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_CORPSE_HERMIT": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_CORPSE_PARTY_DRESS": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_CORPSE_PEASANT_CAMO": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_CORPSE_THEBAN_DRESS": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_SUCCUBUS_CORPSE": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_CORPSE_PEASANT_GLADIATRIX": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_CORPSE_PEASANT_FUSILIER": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_CORPSE_PIR_GREMRIN": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_CORPSE_WENCH": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_CORPSE_GNOME_EXPERIMENT": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_SMUGGLER_5_CORPSE_BATTLE": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_CORPSE_DOCTOR_X_VAMPIRE": ("confirmed", "на картинке трупа открыта грудь или всё тело"),
    "STR_RETICULAN_1_CORPSE_BATTLE": ("unsure", "открыто ли тело, на 32x48 не разобрать (поза, вырез, полосы)"),
    "STR_CORPSE_HYBRID_NUDE": ("unsure", "открыто ли тело, на 32x48 не разобрать (поза, вырез, полосы)"),
    "STR_CORPSE_NURSE_ADV": ("unsure", "открыто ли тело, на 32x48 не разобрать (поза, вырез, полосы)"),
    "STR_CORPSE_HYBRID_PSICRYSTAL_NUDE": ("unsure", "открыто ли тело, на 32x48 не разобрать (поза, вырез, полосы)"),
    "STR_CORPSE_HYBRID_THONG": ("unsure", "открыто ли тело, на 32x48 не разобрать (поза, вырез, полосы)"),
    "STR_HUMAN_5_CORPSE_BATTLE": ("unsure", "открыто ли тело, на 32x48 не разобрать (поза, вырез, полосы)"),
    "STR_CORPSE_NEKO_BIKINI": ("unsure", "открыто ли тело, на 32x48 не разобрать (поза, вырез, полосы)"),
    "STR_CORPSE_PEASANT_MILITIA": ("unsure", "открыто ли тело, на 32x48 не разобрать (поза, вырез, полосы)"),
    "STR_CORPSE_PEASANT_SAILOR": ("unsure", "открыто ли тело, на 32x48 не разобрать (поза, вырез, полосы)"),
    "STR_CORPSE_AMAZON": ("unsure", "открыто ли тело, на 32x48 не разобрать (поза, вырез, полосы)"),
    "STR_CORPSE_NEKO_HERBALIST": ("unsure", "открыто ли тело, на 32x48 не разобрать (поза, вырез, полосы)"),
    "STR_CORPSE_NEKO_PARTY_DRESS": ("unsure", "открыто ли тело, на 32x48 не разобрать (поза, вырез, полосы)"),
    "STR_CORPSE_REDMAGE_I": ("unsure", "открыто ли тело, на 32x48 не разобрать (поза, вырез, полосы)"),
    "STR_CORPSE_RUNT": ("unsure", "открыто ли тело, на 32x48 не разобрать (поза, вырез, полосы)"),
    "STR_HUMAN_1_CORPSE_BATTLE": ("unsure", "открыто ли тело, на 32x48 не разобрать (поза, вырез, полосы)"),
    "STR_CORPSE_NEKO_HOLOSUIT": ("unsure", "открыто ли тело, на 32x48 не разобрать (поза, вырез, полосы)"),
    "STR_CORPSE_GNOME_CAMO_PAINT": ("unsure", "открыто ли тело, на 32x48 не разобрать (поза, вырез, полосы)"),
    "STR_CORPSE_PEASANT_MEIDO": ("unsure", "открыто ли тело, на 32x48 не разобрать (поза, вырез, полосы)"),
    "STR_HUMAN_8_CORPSE_BATTLE": ("unsure", "открыто ли тело, на 32x48 не разобрать (поза, вырез, полосы)"),
    "STR_RETBANDIT_1_CORPSE_BATTLE": ("unsure", "открыто ли тело, на 32x48 не разобрать (поза, вырез, полосы)"),
    "STR_CORPSE_DOCTOR_X_SORCERESS": ("unsure", "открыто ли тело, на 32x48 не разобрать (поза, вырез, полосы)"),
    "STR_CORPSE_PEASANT_SCAVENGER": ("unsure", "открыто ли тело, на 32x48 не разобрать (поза, вырез, полосы)"),
    "STR_CORPSE_GNOME_EXPLORER": ("unsure", "открыто ли тело, на 32x48 не разобрать (поза, вырез, полосы)"),
    "STR_CORPSE_BRAINER": ("unsure", "открыто ли тело, на 32x48 не разобрать (поза, вырез, полосы)"),
    "STR_CORPSE_SP_AMBER": ("unsure", "открыто ли тело, на 32x48 не разобрать (поза, вырез, полосы)"),
    "STR_CORPSE_SMOKEY": ("unsure", "открыто ли тело, на 32x48 не разобрать (поза, вырез, полосы)"),
    "CIV_MUT_4_CORPSE": ("confirmed", "ламия топлес"),
    "STR_CORPSE_LAMIA_NUDE": ("confirmed", "ламия топлес"),
    "STR_SPIDERGIRL_CORPSE_BATTLE": ("confirmed", "голое тело"),
    "STR_AURORA_2_CORPSE_BATTLE": ("confirmed", "голое тело"),
    "STR_CORPSE_SLAVE_SAINT": ("confirmed", "голый мужчина"),
    "STR_CORPSE_SLAVE_NUDE": ("confirmed", "голый мужчина"),
    "STR_CORPSE_SLIMEGAL": ("confirmed", "голое тело"),
    "STR_CORPSE_OGRE_NUDE": ("unsure", "окровавленное тело огра"),
    "STR_CORPSE_GRAV_ARMOR": ("rejected", "ремни закрывают грудь"),
    "STR_CORPSE_LOKNAR_NUDE": ("rejected", "тёмная груда, тела не видно"),
    "STR_CORPSE_SYNTH_NUDE": ("rejected", "тёмная груда, тела не видно"),
    "STR_CORPSE_SYNTH_NUDE_A": ("rejected", "тёмная груда, тела не видно"),
    "STR_CORPSE_SYNTH_NUDE_SPACE": ("rejected", "тёмная груда, тела не видно"),
    "STR_GOLDEN_SAINT_CORPSE_BATTLE": ("rejected", "шар, не тело"),
    "STR_CHURCH_3_CORPSE_BATTLE": ("rejected", "бикини"),
    "STR_CORPSE_CHORT": ("unsure", "тёмное тело демона"),
    "STR_WRAITH_CORPSE": ("unsure", "тёмное тело без деталей"),
    "STR_STYGIAN_GUARD_CORPSE": ("unsure", "синее тело без деталей"),
    "STR_CORPSE_SPACE_POD": ("rejected", "капсула"),
}

# ------------------------------------------------------------------ загрузка


def load_lang(chain, st):
    """Строки en-US и ru: Language/*.yml модов по порядку, затем extraStrings (Game::loadLanguages)."""
    loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    lang = {"en-US": {}, "ru": {}}
    src = {"en-US": {}, "ru": {}}
    for mid, d in chain:
        for code in lang:
            p = d / "Language" / f"{code}.yml"
            if not p.is_file():
                continue
            txt = p.read_text(encoding="utf-8-sig", errors="replace")
            # yaml-cpp терпит управляющие символы (в ru.yml RU-патча есть 0x16), PyYAML - нет
            txt = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", txt)
            data = yaml.load(txt, Loader=loader) or {}
            for k, v in (data.get(code) or {}).items():
                if isinstance(v, str):
                    lang[code][k] = v
                    src[code][k] = f"{mid}:Language/{code}.yml"
    for _rid, rel, _line, fields in st.lists.get("extraStrings", []):
        code = fields.get("languageId", _rid)
        if code in lang:
            for k, v in (fields.get("strings") or {}).items():
                if isinstance(v, str):
                    lang[code][k] = v
                    src[code][k] = f"{uc.mod_of(rel)}:extraStrings"
    return lang, src


def read_spk(path: Path):
    """UFOGRAPH/*.SPK 320x200: 0xFFFF n - пропустить 2n, 0xFFFE n - 2n байт, 0xFFFD - конец."""
    data = path.read_bytes()
    out = bytearray(320 * 200)
    pos = x = 0
    while pos + 1 < len(data):
        cmd = data[pos] | data[pos + 1] << 8
        pos += 2
        if cmd == 0xFFFD:
            break
        n = (data[pos] | data[pos + 1] << 8) * 2
        pos += 2
        if cmd == 0xFFFF:
            x += n
        elif cmd == 0xFFFE:
            chunk = data[pos:pos + n]
            out[x:x + len(chunk)] = chunk
            x += n
            pos += n
    return np.frombuffer(bytes(out[:320 * 200]), np.uint8).reshape(200, 320)


class Game:
    def __init__(self):
        g = uc.games()["piratez"]
        self.g = g
        self.st, ops = uc.load_rules(g["chain"], ROOT / "src")
        self.offsets = uc.mod_offsets(g["chain"])
        self.vfs = uc.VFS(g["data"])
        self.pal = uc.load_battle_palette(*g["battle_pal"]).astype(np.uint8)
        self.lang, self.lsrc = load_lang(g["chain"], self.st)
        sec = defaultdict(dict)
        for (s, rid), rec in self.st.rules.items():
            sec[s][rid] = rec
        self.sec = sec
        self.extras = defaultdict(list)
        self.singles = {}
        for rid, rel, line, fields in self.st.lists.get("extraSprites", []):
            op = ops.get((rel, line), "type")
            self.extras[rid].append((rid, rel, line, fields, op))
            if op == "delete":
                self.singles.pop(rid, None)
                continue
            if op == "typeSingle" or fields.get("singleImage"):
                f = fields.get("fileSingle")
                if not f:
                    fl = fields.get("files") or {}
                    f = next(iter(fl.values()), "") if isinstance(fl, dict) and fl else ""
                self.singles[rid] = (uc.mod_of(rel), str(f), f"{rel}:{line}")
        for n, (mid, p) in self.vfs.folder("UFOGRAPH").items():
            if n.endswith(".SPK"):
                self.singles.setdefault(n, (mid, f"UFOGRAPH/{p.name}", "UFOGRAPH"))
        self._sets = {}
        self._surf = {}

    # ---- строки
    def tr(self, code, key):
        return self.lang[code].get(key, "") if key else ""

    def setby(self, sec, rid, field):
        rec = self.sec[sec].get(rid)
        if not rec:
            return ""
        sb = rec.get("setby", {}).get(field)
        if not sb:
            return ""
        return f"{sb[0].replace('|', ':')}:{sb[1]}"

    # ---- поверхности
    def surface(self, name):
        """(индексы, мод файла, путь) поверхности по имени, как Mod::getSurface."""
        if name in self._surf:
            return self._surf[name]
        res = None
        s = self.singles.get(name)
        if s and s[1]:
            hit = self.vfs.resolve(s[1])
            if hit:
                mid, p = hit
                if p.suffix.upper() == ".SPK":
                    arr = read_spk(p)
                else:
                    arr, _pal, _err = uc.read_image(p)
                if arr is not None:
                    res = (arr, mid, s[1])
        self._surf[name] = res
        return res

    def sheet(self, name):
        if name not in self._sets:
            self._sets[name] = uc.build_set(name, self.vfs, self.extras, self.offsets, None)
        return self._sets[name]


# ------------------------------------------------------------------ кукла


def doll_versions(f):
    ld = f.get("layersDefinition")
    if isinstance(ld, dict) and ld and f.get("layersDefaultPrefix"):
        return list(ld.keys())
    return []


def layer_names(f, version):
    ld = f.get("layersDefinition") or {}
    pre = f.get("layersDefaultPrefix", "")
    spec = f.get("layersSpecificPrefix") or {}
    out = []
    for li, item in enumerate(ld.get(version) or []):
        if not item:
            continue
        pfx = spec.get(li, spec.get(str(li), pre)) if isinstance(spec, dict) else pre
        out.append((li, str(item), f"{pfx}__{li}__{item}"))
    return out


def pick_version(vers):
    for v in ("F0", "M0"):
        if v in vers:
            return v
    return vers[0]


def compose(game, names):
    canvas = np.zeros((200, 320), np.uint8)
    srcs = []
    for n in names:
        s = game.surface(n)
        if not s:
            srcs.append(f"{n}=НЕТ")
            continue
        arr, mid, path = s
        h, w = min(200, arr.shape[0]), min(320, arr.shape[1])
        a = arr[:h, :w]
        m = a != 0
        canvas[:h, :w][m] = a[m]
        srcs.append(f"{mid}:{path}")
    return canvas, srcs


def armor_doll(game, aid, f, version=None):
    """(индексы 200x320, описание, источники файлов, имена слоёв) как InventoryState::init."""
    vers = doll_versions(f)
    if vers:
        v = version or pick_version(vers)
        lays = layer_names(f, v)
        canvas, srcs = compose(game, [n for _li, _it, n in lays])
        return canvas, f"layers {v}", srcs, lays
    p = f.get("spriteInv")
    if not p:
        return None, "", [], []
    cands = [f"{p}F0.SPK", f"{p}M0.SPK", f"{p}.SPK", p]
    for n in cands:
        if game.surface(n):
            canvas, srcs = compose(game, [n])
            return canvas, f"spriteInv {n}", srcs, []
    return None, f"spriteInv {p}: нет поверхности", [], []


def bikini_zones(game, f, version):
    """Маска купальника той же версии (верх и низ) - зона груди и паха; None, если купальника нет."""
    pre = f.get("layersDefaultPrefix", "")
    for li in range(2, 6):
        s = game.surface(f"{pre}__{li}__BIKINI_{version}")
        if s:
            m = s[0][:200, :320] != 0
            ys = np.where(m.any(axis=1))[0]
            if ys.size == 0:
                return None
            # верх и низ купальника разделены пустыми строками
            gaps = [y for y in range(ys[0], ys[-1]) if not m[y].any()]
            cut = gaps[len(gaps) // 2] if gaps else (ys[0] + ys[-1]) // 2
            top, bot = m.copy(), m.copy()
            top[cut:] = False
            bot[:cut] = False
            return top, bot
    return None


def nude_metrics(game, f, version, canvas, lays):
    """Доля видимых пикселей голого базового слоя: всего, в зоне груди, в зоне паха."""
    base = [n for _li, it, n in lays if "NUDE" in it.upper()]
    if not base:
        return None
    s = game.surface(base[0])
    if not s:
        return None
    b = s[0][:200, :320]
    bm = b != 0
    if not bm.any():
        return None
    vis = bm & (canvas == b)
    out = {"all": float(vis.sum() / bm.sum())}
    z = bikini_zones(game, f, version)
    if z:
        for key, zm in zip(("chest", "groin"), z):
            zz = zm & bm
            out[key] = float((vis & zz).sum() / zz.sum()) if zz.any() else None
    return out


def skin_fraction(pal, canvas):
    m = canvas != 0
    if not m.any():
        return 0.0
    rgb = pal[canvas[m]].astype(np.float32) / 255.0
    r, g, b = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    mx, mn = rgb.max(1), rgb.min(1)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    skin = (r >= g) & (g >= b * 0.9) & (sat > 0.15) & (sat < 0.75) & (mx > 0.3) & ((r - g) < 0.45)
    return float(skin.mean())


def doll_hash(canvas):
    return hashlib.sha1(canvas.tobytes()).hexdigest()[:10] if canvas is not None else ""


# ------------------------------------------------------------------ бой и труп

def battle_figure(game, sheet, routine, torso_female=True, d=3):
    sb = game.sheet(sheet)
    fr = sb.frames
    w, h = (sb.fw or 32), (sb.fh or 40)

    def get(i):
        a = fr.get(i)
        return a if a is not None and a.shape == (h, w) else None

    parts = []
    if routine in (0, 10, 13, 14, 15, 17, 18):
        torso = (267 if torso_female else 32) + d
        parts = [16 + d, 0 + d, torso, 8 + d]
        death = 266
    elif routine == 6:
        parts, death = [16 + d, 0 + d, 24 + d, 8 + d], 98
    elif routine == 4:
        parts, death = [d], 74
    elif routine == 1:
        parts, death = [16 + d], None
    elif routine in (16,):
        parts, death = [d], None
    elif routine == 19:
        parts, death = [d], None
    elif routine == 9:
        parts, death = [0], 25
    else:
        nz = [i for i in sorted(fr) if fr[i] is not None and fr[i].any()]
        parts, death = nz[:1], None
    canvas = np.zeros((h, w), np.uint8)
    for i in parts:
        a = get(i)
        if a is not None:
            m = a != 0
            canvas[m] = a[m]
    dead = get(death) if death is not None else None
    return canvas, dead


def corpse_picture(game, corpse_item):
    rec = game.sec["items"].get(corpse_item)
    if not rec:
        return None, ""
    f = rec["fields"]
    big = f.get("bigSprite")
    if big is None:
        return None, ""
    big = int(big)
    defs = game.st.defs.get(("items", corpse_item), [])
    setby = rec.get("setby", {}).get("bigSprite")
    mid = uc.mod_of(setby[0]) if setby else (uc.mod_of(defs[0][0]) if defs else "")
    sb = game.sheet("BIGOBS.PCK")
    shared = sb.vanilla
    idx = big
    if big >= shared:
        idx = big + game.offsets.get(mid, (0, 0))[0]
    return sb.frames.get(idx), f"BIGOBS #{idx}"


# ------------------------------------------------------------------ картинки

def rgba(pal, idx, scale=1, bg=None):
    if idx is None:
        return None
    a = np.zeros(idx.shape + (4,), np.uint8)
    m = idx != 0
    a[..., :3] = pal[idx]
    a[..., 3] = np.where(m, 255, 0)
    im = Image.fromarray(a, "RGBA")
    if scale != 1:
        im = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
    if bg is not None:
        base = Image.new("RGBA", im.size, bg)
        base.alpha_composite(im)
        im = base
    return im


def crop_box(idx, pad=2):
    ys, xs = np.where(idx != 0)
    if ys.size == 0:
        return None
    return (max(0, xs.min() - pad), max(0, ys.min() - pad), min(idx.shape[1], xs.max() + 1 + pad),
            min(idx.shape[0], ys.max() + 1 + pad))


def font(size):
    try:
        return ImageFont.truetype(FONT, size)
    except OSError:
        return ImageFont.load_default()


# ------------------------------------------------------------------ перепись


def text_evidence(game, aid, f):
    ev = []          # (сила, откуда, текст)
    defs = game.st.defs.get(("armors", aid), [])
    where = f"{defs[0][0].replace('|', ':')}:{defs[0][1]}" if defs else ""
    for rx, kind in ((RX_NUDE_EN, "nude"), (RX_SKIMPY_EN, "skimpy")):
        m = rx.search(aid)
        if m:
            ev.append((kind, f"ID ({where})", m.group(0)))
    for code, rxs in (("en-US", (RX_NUDE_EN, RX_SKIMPY_EN)), ("ru", (RX_NUDE_RU, RX_SKIMPY_RU))):
        name = game.tr(code, aid)
        for rx, kind in zip(rxs, ("nude", "skimpy")):
            m = rx.search(name)
            if m:
                ev.append((kind, f"название {code} ({game.lsrc[code].get(aid, '')})", name))
                break
    art_id = f.get("ufopediaType") or aid
    art = game.sec["ufopaedia"].get(art_id) or game.sec["ufopaedia"].get(aid)
    if art:
        tkey = art["fields"].get("text", "")
        for code, rxs in (("en-US", (RX_NUDE_EN, RX_SKIMPY_EN)), ("ru", (RX_NUDE_RU, RX_SKIMPY_RU))):
            txt = game.tr(code, tkey)
            for rx, kind in zip(rxs, ("nude", "skimpy")):
                m = rx.search(txt)
                if m:
                    s0, e0 = max(0, m.start() - 50), min(len(txt), m.end() + 50)
                    frag = txt[s0:e0].replace("{NEWLINE}", " ").replace("\n", " ")
                    ev.append((kind + "_pedia", f"педия {code} {tkey} ({game.lsrc[code].get(tkey, '')})", frag))
                    break
    for c in (f.get("corpseBattle") or []):
        for rx, kind in ((RX_NUDE_EN, "nude"), (RX_SKIMPY_EN, "skimpy")):
            m = rx.search(str(c))
            if m:
                ev.append((kind + "_corpse", f"corpseBattle ({game.setby('armors', aid, 'corpseBattle')})", str(c)))
    inv = f.get("spriteInv") or ""
    if inv and RX_NUDE_EN.search(inv):
        ev.append(("nude", f"spriteInv ({game.setby('armors', aid, 'spriteInv')})", inv))
    return ev


def soldier_links(game):
    """armor -> [(тип бойца, роль, другая броня)] по soldiers: armor и armorForAvatar."""
    out = defaultdict(list)
    for sid, rec in game.sec["soldiers"].items():
        f = rec["fields"]
        a, av = f.get("armor"), f.get("armorForAvatar")
        if a:
            out[a].append((sid, "armor", av))
        if av:
            out[av].append((sid, "armorForAvatar", a))
    return out


def read_tsv(path):
    with open(path, encoding=ENC, newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t", quoting=csv.QUOTE_NONE))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--review", action="store_true", help="листы всех кукол для просмотра глазами")
    ap.add_argument("--per-sheet", type=int, default=40)
    ap.add_argument("--battle-review", action="store_true", help="листы боя и трупов откровенных броней")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    game = Game()
    armors = {rid: rec["fields"] for rid, rec in game.sec["armors"].items()}
    print(f"броней: {len(armors)}; строк en-US {len(game.lang['en-US'])}, ru {len(game.lang['ru'])}")

    fam = {}
    for r in read_tsv(CENSUS / "families.tsv"):
        if r["game"] == "piratez":
            fam[r["sheet"]] = r["family"]
    sheets_info = {r["sheet"]: r for r in read_tsv(CENSUS / "sheets.tsv") if r["game"] == "piratez"}
    slinks = soldier_links(game)

    # ---- куклы всех броней
    info = {}
    for aid, f in sorted(armors.items()):
        canvas, how, srcs, lays = armor_doll(game, aid, f)
        vers = doll_versions(f)
        nm = nude_metrics(game, f, pick_version(vers), canvas, lays) if vers else None
        info[aid] = dict(canvas=canvas, how=how, srcs=srcs, lays=lays, nm=nm,
                         skin=skin_fraction(game.pal, canvas) if canvas is not None else 0.0,
                         hash=doll_hash(canvas), ev=text_evidence(game, aid, f))
    groups = defaultdict(list)
    for aid, d in info.items():
        if d["canvas"] is not None and d["canvas"].any():
            groups[d["hash"]].append(aid)

    if a.review:
        review_sheets(game, info, groups, a.per_sheet)

    # ---- решение по кукле: представитель группы -> все брони с той же куклой
    inv_v = {}
    for rep, v in VERDICTS.items():
        if rep not in info:
            print(f"!! в VERDICTS брони нет: {rep}")
            continue
        for aid in groups.get(info[rep]["hash"], [rep]):
            inv_v[aid] = (v, rep)
    explicit = {aid for aid, (v, _r) in inv_v.items() if v[0] in ("confirmed", "unsure")}
    text_only = sorted(aid for aid, d in info.items()
                       if aid not in inv_v and any(k.startswith("nude") for k, _w, _t in d["ev"]))
    print(f"кукол с решением: {len(inv_v)} броней; откровенных (confirmed+unsure) {len(explicit)}; "
          f"нагота только в тексте: {len(text_only)}")
    for aid in text_only:
        print("   текст:", aid, "|", "; ".join(f"{w}: {t[:60]}" for _k, w, t in info[aid]["ev"]))

    # ---- пара «откровенный - обычный»
    def base_body(aid):
        lays = info[aid]["lays"]
        b = [n for _li, it, n in lays if "NUDE" in it.upper()]
        return b[0] if b else ""

    soldier_order = [(sid, rec["fields"].get("armor"), rec["fields"].get("armorForAvatar"))
                     for sid, rec in game.sec["soldiers"].items()]

    def normal_for(aid):
        for sid, role, other in slinks.get(aid, []):
            if role == "armorForAvatar" and other and other not in explicit:
                return other, (f"soldiers {sid}: armorForAvatar {aid}, armor {other} "
                               f"({game.setby('soldiers', sid, 'armorForAvatar')})")
        bb = base_body(aid)
        if bb:
            for sid, arm, _av in soldier_order:
                if arm and arm not in explicit and arm in info and base_body(arm) == bb:
                    return arm, f"тот же базовый слой тела {bb}; {arm} - броня по умолчанию soldiers {sid}"
        sheet = armors[aid].get("spriteSheet", "")
        fm = fam.get(sheet, "")
        if fm:
            cands = [b for b in armors if b != aid and b not in explicit and b not in inv_v
                     and fam.get(armors[b].get("spriteSheet", "")) == fm]
            if cands:
                def cp(b):
                    n = 0
                    for x, y in zip(aid, b):
                        if x != y:
                            break
                        n += 1
                    return n
                best = max(cands, key=lambda b: (cp(b), b))
                if cp(best) >= 6:
                    return best, (f"семейство листов {fm} (census/units/families.tsv): {sheet} ~ "
                                  f"{armors[best].get('spriteSheet', '')}, общее начало ID")
        return "", "нет пары"

    corpse_pic = {}
    for r in read_tsv(CENSUS / "corpses.tsv"):
        if r["game"] == "piratez" and r["big_index"]:
            corpse_pic[r["item"]] = (int(r["big_index"]), r["big_hash"])
    bigobs = game.sheet("BIGOBS.PCK")

    def corpse_of(aid):
        cs = armors.get(aid, {}).get("corpseBattle") or []
        if not cs:
            return "", None, ""
        c = str(cs[0])
        if c in corpse_pic:
            i, h = corpse_pic[c]
            return c, bigobs.frames.get(i), h
        return c, None, ""

    def female(aid):
        return "F" in "".join(doll_versions(armors[aid]))[:1] or any(
            v.startswith("F") for v in doll_versions(armors[aid]))

    def battle(aid):
        f = armors.get(aid, {})
        sh = f.get("spriteSheet", "")
        if not sh:
            return sh, None, None
        try:
            fig, dead = battle_figure(game, sh, int(f.get("drawingRoutine", 0) or 0), female(aid))
        except Exception as e:  # noqa: BLE001
            print(f"!! лист {sh}: {e}")
            return sh, None, None
        return sh, fig, dead

    pairs = {aid: normal_for(aid) for aid in sorted(explicit)}

    if a.battle_review:
        battle_review(game, sorted(explicit), pairs, battle, corpse_of, inv_v)

    # ---- строки таблицы
    rows = []
    stat = defaultdict(set)
    for aid in sorted(inv_v, key=lambda x: (inv_v[x][0][0] != "confirmed", inv_v[x][0][0], x)):
        (st, kind, note), rep = inv_v[aid]
        f = armors[aid]
        normal, link = pairs.get(aid, ("", "")) if aid in explicit else ("", "")
        nf = armors.get(normal, {})
        ev_text = "; ".join(f"{w}: {t[:80]}" for _k, w, t in info[aid]["ev"])
        lay_src = "layersDefinition" if doll_versions(f) else "spriteInv"
        inv_mod = game.setby("armors", aid, lay_src) or game.setby("armors", aid, "spriteInv")
        doll_files = ", ".join(sorted(set(info[aid]["srcs"])))[:300]
        ev = f"кукла ({info[aid]['how']}): {kind + ', ' if kind else ''}{note}"
        if ev_text:
            ev += f" | текст: {ev_text}"
        ndoll = info.get(normal, {}).get("how", "") if normal else ""
        rows.append(["piratez", aid, "inv", f"{info[aid]['how']} [{doll_files}]", inv_mod, ev, normal,
                     ndoll, link, st])
        stat[("inv", st)].add(aid)
        if aid not in explicit:
            continue
        sh, fig, dead = battle(aid)
        nsh = nf.get("spriteSheet", "")
        if sh:
            if normal and sh == nsh:
                bst, bnote = "rejected", f"лист общий с обычной бронёй {normal}"
            elif sh in BATTLE:
                bst, bnote = BATTLE[sh]
            else:
                bst, bnote = "unsure", "лист боя не просмотрен"
            rows.append(["piratez", aid, "battle", sh, game.setby("armors", aid, "spriteSheet"),
                         f"лист боя, стоящий юнит и смерть: {bnote}", normal, nsh, link, bst])
            stat[("battle", bst)].add(sh)
        c, cimg, chash = corpse_of(aid)
        nc, _ni, nhash = corpse_of(normal) if normal else ("", None, "")
        if c:
            if chash and chash == nhash:
                cst, cnote = "rejected", f"картинка трупа та же, что у {nc}"
            elif c in CORPSE:
                cst, cnote = CORPSE[c]
            elif not chash:
                cst, cnote = "rejected", "у трупа нет своей картинки BIGOBS"
            else:
                cst, cnote = "unsure", "труп не просмотрен"
            rows.append(["piratez", aid, "corpse", f"{c} BIGOBS #{corpse_pic.get(c, ('', ''))[0]}",
                         game.setby("armors", aid, "corpseBattle"), f"труп (corpseBattle): {cnote}",
                         normal, nc, link, cst])
            stat[("corpse", cst)].add(c)
    # ---- трупы обычных (одетых) броней, у которых картинка трупа сама открытая
    for aid in sorted(armors):
        if aid in explicit:
            continue
        c, _ci, chash = corpse_of(aid)
        if not c or not chash or c not in CORPSE or CORPSE[c][0] == "rejected":
            continue
        cst, cnote = CORPSE[c]
        doll = (f"кукла {inv_v[aid][0][0]} ({inv_v[aid][0][2]})" if aid in inv_v
                else "кукла не откровенная")
        rows.append(["piratez", aid, "corpse", f"{c} BIGOBS #{corpse_pic[c][0]}",
                     game.setby("armors", aid, "corpseBattle"),
                     f"труп обычной брони, {doll}: {cnote}", "", "",
                     "одетой пары у трупа нет: сама броня обычная, открыта только картинка трупа", cst])
        stat[("corpse_n", cst)].add(c)
    uc.write_tsv(CENSUS / "explicit_variants.tsv",
                 ["game", "armor", "kind", "sheet", "source_mod", "evidence", "normal_armor", "normal_sheet",
                  "link_evidence", "status"], rows)
    print(f"census/units/explicit_variants.tsv: {len(rows)} строк")
    for (k, s), v in sorted(stat.items()):
        print(f"   {k:7s} {s:9s} {len(v)}")
    unpaired = [x for x in explicit if not pairs[x][0]]
    print(f"откровенных без пары: {len(unpaired)}")

    overview(game, info, inv_v, explicit, pairs, battle, corpse_of, armors)


def review_sheets(game, info, groups, per):
    def key(h):
        d = info[groups[h][0]]
        nm = d["nm"] or {}
        return (-(nm.get("chest") if nm.get("chest") is not None else nm.get("all", 0) * 0.5), -d["skin"])
    order = sorted(groups, key=key)
    rv = REVIEW / "review"
    rv.mkdir(parents=True, exist_ok=True)
    for old in rv.glob("dolls_*.png"):
        old.unlink()
    cw, ch, cols = 120, 196, 10
    ft = font(10)
    rows_out = []
    for si in range(0, len(order), per):
        chunk = order[si:si + per]
        rows = (len(chunk) + cols - 1) // cols
        img = Image.new("RGBA", (cw * cols, ch * rows), (52, 52, 58, 255))
        dr = ImageDraw.Draw(img)
        for k, h in enumerate(chunk):
            aids = groups[h]
            d = info[aids[0]]
            im = rgba(game.pal, d["canvas"]).crop(crop_box(d["canvas"]))
            sc = min(2.0, (cw - 4) / im.width, (ch - 30) / im.height)
            im = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.NEAREST)
            x0, y0 = (k % cols) * cw, (k // cols) * ch
            img.alpha_composite(im, (x0 + (cw - im.width) // 2, y0 + 2))
            n = si + k + 1
            nm = d["nm"] or {}
            dr.text((x0 + 2, y0 + ch - 27), f"{n} {aids[0][:19]}", fill=(255, 255, 160), font=ft)
            c = nm.get("chest")
            dr.text((x0 + 2, y0 + ch - 15), f"+{len(aids) - 1} c{-1 if c is None else round(c, 2)} s{d['skin']:.2f}",
                    fill=(200, 200, 200), font=ft)
            rows_out.append([n, h, len(aids), ",".join(aids), d["how"], f"{d['skin']:.3f}",
                             "" if not nm else f"{nm.get('all', 0):.2f}/{nm.get('chest')}/{nm.get('groin')}"])
        img.convert("RGB").save(rv / f"dolls_{si // per + 1:02d}.png")
    uc.write_tsv(rv / "dolls_index.tsv",
                 ["n", "doll_hash", "armors_n", "armors", "doll", "skin", "nude_visible_all/chest/groin"], rows_out)
    print(f"просмотр: {len(order)} разных кукол, {(len(order) + per - 1) // per} листов в {rv}")


def fit(im, w, h, up=4):
    if im is None:
        return None
    sc = min(up, w / im.width, h / im.height)
    return im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.NEAREST)


def cropped(pal, idx):
    if idx is None or not idx.any():
        return None
    return rgba(pal, idx).crop(crop_box(idx, 1))


def battle_review(game, aids, pairs, battle, corpse_of, inv_v):
    """Лист боя и трупа: откровенная броня против обычной, по уникальным парам листов."""
    seen = {}
    for aid in aids:
        sh = battle(aid)[0]
        c = corpse_of(aid)[0]
        seen.setdefault((sh, c, pairs[aid][0]), aid)
    items = list(seen.values())
    rv = REVIEW / "review"
    rv.mkdir(parents=True, exist_ok=True)
    for old in rv.glob("battle_*.png"):
        old.unlink()
    cw, ch, cols, per = 600, 210, 2, 16
    ft = font(12)
    lines = []
    for si in range(0, len(items), per):
        chunk = items[si:si + per]
        rows = (len(chunk) + cols - 1) // cols
        img = Image.new("RGBA", (cw * cols, ch * rows), (58, 60, 52, 255))
        dr = ImageDraw.Draw(img)
        for k, aid in enumerate(chunk):
            x0, y0 = (k % cols) * cw, (k // cols) * ch
            n = si + k + 1
            sh, fig, dead = battle(aid)
            c, cimg, _h = corpse_of(aid)
            nrm = pairs[aid][0]
            nsh, nfig, _nd = battle(nrm) if nrm else ("", None, None)
            nc, ncimg, _nh = corpse_of(nrm) if nrm else ("", None, "")
            x = x0 + 4
            for im in (cropped(game.pal, fig), cropped(game.pal, dead), cropped(game.pal, cimg)):
                im = fit(im, 110, 165)
                if im is not None:
                    img.alpha_composite(im, (x, y0 + 4))
                x += 114
            x = x0 + 4 + 114 * 3 + 12
            dr.line([(x - 6, y0 + 4), (x - 6, y0 + 170)], fill=(120, 120, 120))
            for im in (cropped(game.pal, nfig), cropped(game.pal, ncimg)):
                im = fit(im, 110, 165)
                if im is not None:
                    img.alpha_composite(im, (x, y0 + 4))
                x += 114
            dr.text((x0 + 4, y0 + ch - 36), f"{n} {aid[:30]} {sh} / {c[:24]}", fill=(255, 255, 140), font=ft)
            dr.text((x0 + 4, y0 + ch - 20), f"   {nrm[:30]} {nsh} / {nc[:24]}", fill=(210, 210, 210), font=ft)
            lines.append([n, aid, sh, c, nrm, nsh, nc])
        img.convert("RGB").save(rv / f"battle_{si // per + 1:02d}.png")
    uc.write_tsv(rv / "battle_index.tsv", ["n", "armor", "sheet", "corpse", "normal", "normal_sheet",
                                           "normal_corpse"], lines)
    print(f"просмотр боя: {len(items)} пар листов, {(len(items) + per - 1) // per} листов")


def overview(game, info, inv_v, explicit, pairs, battle, corpse_of, armors):
    REVIEW.mkdir(parents=True, exist_ok=True)
    ft, fs = font(15), font(12)
    order = sorted(explicit, key=lambda x: (inv_v[x][0][0] != "confirmed", x))
    rh, cw, cols = 196, 1180, 2
    rows = (len(order) + cols - 1) // cols
    img = Image.new("RGBA", (cw * cols, rh * rows + 60), (44, 44, 50, 255))
    dr = ImageDraw.Draw(img)
    dr.text((10, 10), f"X-Piratez: откровенные варианты внешности юнитов в бою - {len(order)} броней "
                      f"(слева кукла | бой | смерть | труп откровенной брони, справа - обычная пара). "
                      f"Жёлтая подпись - подтверждено, оранжевая - неясно.", fill=(255, 255, 255), font=ft)
    dr.text((10, 32), "Только существующие данные игры; кукла - как InventoryState, бой - стоящий юнит, "
                      "направление 3; tools/unit_explicit.py", fill=(190, 190, 190), font=fs)
    for k, aid in enumerate(order):
        x0, y0 = (k % cols) * cw, 60 + (k // cols) * rh
        (st, kind, note), _rep = inv_v[aid]
        nrm, _link = pairs[aid]
        x = x0 + 6
        sh, fig, dead = battle(aid)
        c, cimg, _ = corpse_of(aid)
        parts = [(cropped(game.pal, info[aid]["canvas"]), 120, 160, 2),
                 (cropped(game.pal, fig), 90, 160, 4), (cropped(game.pal, dead), 90, 160, 4),
                 (cropped(game.pal, cimg), 90, 160, 4)]
        for im, w, h, up in parts:
            im = fit(im, w, h, up)
            if im is not None:
                img.alpha_composite(im, (x + (w - im.width) // 2, y0 + 4))
            x += w + 6
        x += 10
        dr.line([(x - 8, y0 + 4), (x - 8, y0 + 165)], fill=(110, 110, 110), width=2)
        if nrm:
            nsh, nfig, _nd = battle(nrm)
            nc, ncimg, _ = corpse_of(nrm)
            for im, w, h, up in [(cropped(game.pal, info.get(nrm, {}).get("canvas")), 120, 160, 2),
                                 (cropped(game.pal, nfig), 90, 160, 4), (cropped(game.pal, ncimg), 90, 160, 4)]:
                im = fit(im, w, h, up)
                if im is not None:
                    img.alpha_composite(im, (x + (w - im.width) // 2, y0 + 4))
                x += w + 6
        else:
            dr.text((x, y0 + 70), "нет пары", fill=(200, 120, 120), font=ft)
        col = (255, 235, 120) if st == "confirmed" else (255, 160, 70)
        name = game.tr("ru", aid)
        dr.text((x0 + 6, y0 + 168), f"{aid}  «{name[:34]}»  {kind}{'?' if st != 'confirmed' else ''}",
                fill=col, font=fs)
        dr.text((x0 + 6, y0 + 182), f"лист {sh}  |  пара: {nrm or '-'} {armors.get(nrm, {}).get('spriteSheet', '')}",
                fill=(200, 200, 200), font=fs)
    img.convert("RGB").save(REVIEW / "explicit_overview.png")
    print(f"обзор: {REVIEW / 'explicit_overview.png'} ({img.width}x{img.height})")

    rej = sorted(aid for aid, (v, _r) in inv_v.items() if v[0] == "rejected")
    cwr, chr_, colsr = 150, 230, 12
    rows = (len(rej) + colsr - 1) // colsr
    img = Image.new("RGBA", (cwr * colsr, chr_ * rows + 40), (44, 44, 50, 255))
    dr = ImageDraw.Draw(img)
    dr.text((10, 10), f"Отвергнутые кандидаты: {len(rej)} броней - одеты (купальник, бельё, вырез) или нагота "
                      f"без признаков; причина под куклой", fill=(255, 255, 255), font=ft)
    for k, aid in enumerate(rej):
        x0, y0 = (k % colsr) * cwr, 40 + (k // colsr) * chr_
        im = fit(cropped(game.pal, info[aid]["canvas"]), cwr - 8, chr_ - 40, 2)
        if im is not None:
            img.alpha_composite(im, (x0 + (cwr - im.width) // 2, y0 + 2))
        dr.text((x0 + 3, y0 + chr_ - 36), aid[:22], fill=(255, 255, 160), font=font(10))
        dr.text((x0 + 3, y0 + chr_ - 22), inv_v[aid][0][2][:26], fill=(210, 210, 210), font=font(10))
    img.convert("RGB").save(REVIEW / "rejected_overview.png")
    print(f"отвергнутые: {REVIEW / 'rejected_overview.png'}")


if __name__ == "__main__":
    main()
