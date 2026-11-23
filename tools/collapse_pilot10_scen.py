#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Пилот обрушения, десятая партия: охват после ветки D (лес и столбы в движке с 20.10, партия 9).

Те же правила отбора, что у партии 9 (единственный стоп по переписи - деревья, на целом ничего не висит, нет
неопределённой разметки, не базы, корабли, пещеры и Марс; нет непросмотренных предметов слота o выше z0 вне деревьев),
но сейвы переписи добраны 21.10 боями с закреплённым террейном (collapse_battles gen --terrain, по 8 боёв на 51 террейн):
блоков целиком в боях стало 374 вместо 56. Одноимённые блоки с той же моделью, что уже в пилоте, не берутся (их и так
узнаёт движок); одноимённые с другой моделью получают в движке имя ТЕРРЕЙН/БЛОК (NAME_AS) - по имени модель ищется
после загрузки сейва. Отбор - scratchpad cp15/cand10.py, dup10.py, mk10.py. Модель M0j4 с веткой D.

    py -3.13 tools\collapse_pilot10_scen.py define   census/collapse/pilot10/pilot_scen.tsv и замок
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collapse_pilot_scen as PS
from collapse_pilot9_scen import trees  # noqa: F401  (колонны и кроны ветки D - как в партии 9)

OUT = "census/collapse/pilot10"
# (террейн, блок, метка по-русски, метка в логе игры и в OXCE_COLLAPSE_REMOVE - одно слово)
BUILDINGS = [
    ('CHEMTOWN', 'CHEMTOWN09', 'городской блок CHEMTOWN/CHEMTOWN09', 'chemtown09'),
    ('CITY_OF_THE_DEAD', 'DEATHCITY_LZ00', 'городской блок CITY_OF_THE_DEAD/DEATHCITY_LZ00', 'deathcitylz00'),
    ('COMRCURBAN', 'COMRCURBANHUGE01', 'городской блок COMRCURBAN/COMRCURBANHUGE01', 'comrcurbanhuge01'),
    ('ISLANDURBAN', 'ISLANDURBAN10', 'городской блок ISLANDURBAN/ISLANDURBAN10', 'islandurban10'),
    ('ISLANDURBAN', 'ISLANDURBAN11', 'городской блок ISLANDURBAN/ISLANDURBAN11', 'islandurban11'),
    ('MUMMY_VILLAGE_SETTLEMENT', 'MUM_VILLAGE_NW00', 'городской блок MUMMY_VILLAGE_SETTLEMENT/MUM_VILLAGE_NW00', 'mumvillagenw00'),
    ('NECROPOLIS', 'NECROPOLIS_NS_00', 'городской блок NECROPOLIS/NECROPOLIS_NS_00', 'necropolisns00'),
    ('NECROPOLIS', 'NECROPOLIS_WE_00', 'городской блок NECROPOLIS/NECROPOLIS_WE_00', 'necropoliswe00'),
    ('PORTTFTD5', 'PORTUFO31', 'городской блок PORTTFTD5/PORTUFO31', 'portufo31'),
    ('URBAN', 'EXPANDEDTERROR18', 'городской блок URBAN/EXPANDEDTERROR18', 'urbanexpandedterror18'),
    ('URBANJUNKUFO', 'URBANJUNK01', 'городской блок URBANJUNKUFO/URBANJUNK01', 'urbanjunkufourbanjunk01'),
    ('URBANJUNKUFO', 'URBANJUNK18', 'городской блок URBANJUNKUFO/URBANJUNK18', 'urbanjunkufourbanjunk18'),
    ('URBANJUNKUFO', 'URBANJUNK19', 'городской блок URBANJUNKUFO/URBANJUNK19', 'urbanjunkufourbanjunk19'),
    ('URBANJUNKUFO', 'URBANJUNK23', 'городской блок URBANJUNKUFO/URBANJUNK23', 'urbanjunkufourbanjunk23'),
    ('URBANJUNKUFO', 'URBANJUNK30', 'городской блок URBANJUNKUFO/URBANJUNK30', 'urbanjunk30'),
    ('URBANJUNKUFO', 'URBANJUNKDIO_08', 'городской блок URBANJUNKUFO/URBANJUNKDIO_08', 'urbanjunkufourbanjunkdio08'),
    ('URBANJUNKWOODUFO', 'URBANJUNK01', 'городской блок URBANJUNKWOODUFO/URBANJUNK01', 'urbanjunkwoodufourbanjunk01'),
    ('URBANJUNKWOODUFO', 'URBANJUNK02', 'городской блок URBANJUNKWOODUFO/URBANJUNK02', 'urbanjunk02'),
    ('URBANJUNKWOODUFO', 'URBANJUNK04', 'городской блок URBANJUNKWOODUFO/URBANJUNK04', 'urbanjunk04'),
    ('URBANJUNKWOODUFO', 'URBANJUNK05', 'городской блок URBANJUNKWOODUFO/URBANJUNK05', 'urbanjunk05'),
    ('URBANJUNKWOODUFO', 'URBANJUNK08', 'городской блок URBANJUNKWOODUFO/URBANJUNK08', 'urbanjunk08'),
    ('URBANJUNKWOODUFO', 'URBANJUNK10', 'городской блок URBANJUNKWOODUFO/URBANJUNK10', 'urbanjunkwoodufourbanjunk10'),
    ('URBANJUNKWOODUFO', 'URBANJUNK18', 'городской блок URBANJUNKWOODUFO/URBANJUNK18', 'urbanjunkwoodufourbanjunk18'),
    ('URBANJUNKWOODUFO', 'URBANJUNK19', 'городской блок URBANJUNKWOODUFO/URBANJUNK19', 'urbanjunkwoodufourbanjunk19'),
    ('URBANJUNKWOODUFO', 'URBANJUNK22', 'городской блок URBANJUNKWOODUFO/URBANJUNK22', 'urbanjunk22'),
    ('URBANJUNKWOODUFO', 'URBANJUNK23', 'городской блок URBANJUNKWOODUFO/URBANJUNK23', 'urbanjunkwoodufourbanjunk23'),
    ('URBANJUNKWOODUFO', 'URBANJUNK38', 'городской блок URBANJUNKWOODUFO/URBANJUNK38', 'urbanjunk38'),
    ('URBANJUNKWOODUFO', 'URBANJUNK40', 'городской блок URBANJUNKWOODUFO/URBANJUNK40', 'urbanjunk40'),
    ('URBANJUNKWOODUFO', 'URBANJUNK42', 'городской блок URBANJUNKWOODUFO/URBANJUNK42', 'urbanjunk42'),
    ('URBANJUNKWOODUFO', 'URBANJUNK46', 'городской блок URBANJUNKWOODUFO/URBANJUNK46', 'urbanjunk46'),
    ('URBANJUNKWOODUFO', 'URBANJUNKDIO_08', 'городской блок URBANJUNKWOODUFO/URBANJUNKDIO_08', 'urbanjunkwoodufourbanjunkdio08'),
    ('URBANWAR', 'EXPANDEDTERROR14', 'городской блок URBANWAR/EXPANDEDTERROR14', 'urbanwarexpandedterror14'),
    ('URBANWAR', 'EXPANDEDTERROR18', 'городской блок URBANWAR/EXPANDEDTERROR18', 'urbanwarexpandedterror18'),
    ('URBAN_WASTE', 'URBANWASTE15', 'городской блок URBAN_WASTE/URBANWASTE15', 'urbanwaste15'),
    ('URBAN_WASTE', 'URBANWASTEROAD_NS10', 'городской блок URBAN_WASTE/URBANWASTEROAD_NS10', 'urbanwasteroadns10'),
    ('FOREST', 'FINNIKFOREST01', 'природный блок FOREST/FINNIKFOREST01', 'forestfinnikforest01'),
    ('FOREST', 'SOLFOREST15', 'природный блок FOREST/SOLFOREST15', 'forestsolforest15'),
    ('FOREST', 'SOLFOREST17', 'природный блок FOREST/SOLFOREST17', 'forestsolforest17'),
    ('FOREST2BLACK', 'CIVFOREST00', 'природный блок FOREST2BLACK/CIVFOREST00', 'forest2blackcivforest00'),
    ('FOREST2BLACK', 'FINNIKFOREST00', 'природный блок FOREST2BLACK/FINNIKFOREST00', 'forest2blackfinnikforest00'),
    ('FOREST2BLACK', 'FINNIKFOREST01', 'природный блок FOREST2BLACK/FINNIKFOREST01', 'forest2blackfinnikforest01'),
    ('FOREST2BLACK', 'FINNIKFOREST04', 'природный блок FOREST2BLACK/FINNIKFOREST04', 'forest2blackfinnikforest04'),
    ('FOREST2BLACK', 'FINNIKFOREST05', 'природный блок FOREST2BLACK/FINNIKFOREST05', 'forest2blackfinnikforest05'),
    ('FOREST2BLACK', 'FINNIKFOREST06', 'природный блок FOREST2BLACK/FINNIKFOREST06', 'forest2blackfinnikforest06'),
    ('FOREST2BLACK', 'FOREST05', 'природный блок FOREST2BLACK/FOREST05', 'forest2blackforest05'),
    ('FOREST2BLACK', 'FOREST06', 'природный блок FOREST2BLACK/FOREST06', 'forest2blackforest06'),
    ('FOREST2BLACK', 'FOREST07', 'природный блок FOREST2BLACK/FOREST07', 'forest2blackforest07'),
    ('FOREST2BLACK', 'FOREST08', 'природный блок FOREST2BLACK/FOREST08', 'forest2blackforest08'),
    ('FOREST2BLACK', 'SOLFOREST12', 'природный блок FOREST2BLACK/SOLFOREST12', 'forest2blacksolforest12'),
    ('FOREST2BLACK', 'SOLFOREST13', 'природный блок FOREST2BLACK/SOLFOREST13', 'forest2blacksolforest13'),
    ('FOREST2BLACK', 'SOLFOREST14', 'природный блок FOREST2BLACK/SOLFOREST14', 'forest2blacksolforest14'),
    ('FOREST2BLACK', 'SOLFOREST15', 'природный блок FOREST2BLACK/SOLFOREST15', 'forest2blacksolforest15'),
    ('FOREST2BLACK', 'SOLFOREST16', 'природный блок FOREST2BLACK/SOLFOREST16', 'forest2blacksolforest16'),
    ('FOREST2BLACK', 'SOLFOREST17', 'природный блок FOREST2BLACK/SOLFOREST17', 'forest2blacksolforest17'),
    ('FOREST2BLACK', 'SOLFOREST18', 'природный блок FOREST2BLACK/SOLFOREST18', 'forest2blacksolforest18'),
    ('FORESTRED', 'CIVFOREST00', 'природный блок FORESTRED/CIVFOREST00', 'forestredcivforest00'),
    ('FORESTRED', 'FINNIKFOREST00', 'природный блок FORESTRED/FINNIKFOREST00', 'forestredfinnikforest00'),
    ('FORESTRED', 'FINNIKFOREST01', 'природный блок FORESTRED/FINNIKFOREST01', 'forestredfinnikforest01'),
    ('FORESTRED', 'FINNIKFOREST05', 'природный блок FORESTRED/FINNIKFOREST05', 'forestredfinnikforest05'),
    ('FORESTRED', 'FINNIKFOREST06', 'природный блок FORESTRED/FINNIKFOREST06', 'forestredfinnikforest06'),
    ('FORESTRED', 'FOREST06', 'природный блок FORESTRED/FOREST06', 'forestredforest06'),
    ('FORESTRED', 'FOREST07', 'природный блок FORESTRED/FOREST07', 'forestredforest07'),
    ('FORESTRED', 'FOREST08', 'природный блок FORESTRED/FOREST08', 'forestredforest08'),
    ('FORESTRED', 'FOREST_ROAD_SN00', 'природный блок FORESTRED/FOREST_ROAD_SN00', 'forestredforestroadsn00'),
    ('FORESTRED', 'FOREST_ROAD_SN01', 'природный блок FORESTRED/FOREST_ROAD_SN01', 'forestredforestroadsn01'),
    ('FORESTRED', 'FOREST_ROAD_SN02', 'природный блок FORESTRED/FOREST_ROAD_SN02', 'forestredforestroadsn02'),
    ('FORESTRED', 'SOLFOREST13', 'природный блок FORESTRED/SOLFOREST13', 'forestredsolforest13'),
    ('FORESTRED', 'SOLFOREST14', 'природный блок FORESTRED/SOLFOREST14', 'forestredsolforest14'),
    ('FORESTRED', 'SOLFOREST15', 'природный блок FORESTRED/SOLFOREST15', 'forestredsolforest15'),
    ('FORESTRED', 'SOLFOREST16', 'природный блок FORESTRED/SOLFOREST16', 'forestredsolforest16'),
    ('FORESTRED', 'SOLFOREST17', 'природный блок FORESTRED/SOLFOREST17', 'forestredsolforest17'),
    ('FORESTSNOW', 'CIVFOREST00', 'природный блок FORESTSNOW/CIVFOREST00', 'forestsnowcivforest00'),
    ('FORESTSNOW', 'FINNIKFOREST00', 'природный блок FORESTSNOW/FINNIKFOREST00', 'forestsnowfinnikforest00'),
    ('FORESTSNOW', 'FINNIKFOREST01', 'природный блок FORESTSNOW/FINNIKFOREST01', 'forestsnowfinnikforest01'),
    ('FORESTSNOW', 'FINNIKFOREST04', 'природный блок FORESTSNOW/FINNIKFOREST04', 'forestsnowfinnikforest04'),
    ('FORESTSNOW', 'FINNIKFOREST05', 'природный блок FORESTSNOW/FINNIKFOREST05', 'forestsnowfinnikforest05'),
    ('FORESTSNOW', 'FINNIKFOREST06', 'природный блок FORESTSNOW/FINNIKFOREST06', 'forestsnowfinnikforest06'),
    ('FORESTSNOW', 'FOREST05', 'природный блок FORESTSNOW/FOREST05', 'forestsnowforest05'),
    ('FORESTSNOW', 'FOREST06', 'природный блок FORESTSNOW/FOREST06', 'forestsnowforest06'),
    ('FORESTSNOW', 'FOREST07', 'природный блок FORESTSNOW/FOREST07', 'forestsnowforest07'),
    ('FORESTSNOW', 'FOREST08', 'природный блок FORESTSNOW/FOREST08', 'forestsnowforest08'),
    ('FORESTSNOW', 'FOREST_ROAD_SN00', 'природный блок FORESTSNOW/FOREST_ROAD_SN00', 'forestsnowforestroadsn00'),
    ('FORESTSNOW', 'FOREST_ROAD_SN01', 'природный блок FORESTSNOW/FOREST_ROAD_SN01', 'forestsnowforestroadsn01'),
    ('FORESTSNOW', 'FOREST_ROAD_SN02', 'природный блок FORESTSNOW/FOREST_ROAD_SN02', 'forestsnowforestroadsn02'),
    ('FORESTSNOW', 'FOREST_ROAD_WE00', 'природный блок FORESTSNOW/FOREST_ROAD_WE00', 'forestsnowforestroadwe00'),
    ('FORESTSNOW', 'FOREST_ROAD_WE01', 'природный блок FORESTSNOW/FOREST_ROAD_WE01', 'forestsnowforestroadwe01'),
    ('FORESTSNOW', 'FOREST_ROAD_WE02', 'природный блок FORESTSNOW/FOREST_ROAD_WE02', 'forestsnowforestroadwe02'),
    ('FORESTSNOW', 'FOREST_ROAD_XX00', 'природный блок FORESTSNOW/FOREST_ROAD_XX00', 'forestsnowforestroadxx00'),
    ('FORESTSNOW', 'SOLFOREST12', 'природный блок FORESTSNOW/SOLFOREST12', 'forestsnowsolforest12'),
    ('FORESTSNOW', 'SOLFOREST13', 'природный блок FORESTSNOW/SOLFOREST13', 'forestsnowsolforest13'),
    ('FORESTSNOW', 'SOLFOREST14', 'природный блок FORESTSNOW/SOLFOREST14', 'forestsnowsolforest14'),
    ('FORESTSNOW', 'SOLFOREST15', 'природный блок FORESTSNOW/SOLFOREST15', 'forestsnowsolforest15'),
    ('FORESTSNOW', 'SOLFOREST16', 'природный блок FORESTSNOW/SOLFOREST16', 'forestsnowsolforest16'),
    ('FORESTSNOW', 'SOLFOREST17', 'природный блок FORESTSNOW/SOLFOREST17', 'forestsnowsolforest17'),
    ('FORESTSNOW', 'SOLFORESTHUGE00', 'природный блок FORESTSNOW/SOLFORESTHUGE00', 'solforesthuge00'),
    ('FORESTSWAMP', 'FINNIKFOREST01', 'природный блок FORESTSWAMP/FINNIKFOREST01', 'forestswampfinnikforest01'),
    ('FORESTSWAMP', 'FINNIKFOREST04', 'природный блок FORESTSWAMP/FINNIKFOREST04', 'forestswampfinnikforest04'),
    ('FORESTSWAMP', 'FINNIKFOREST05', 'природный блок FORESTSWAMP/FINNIKFOREST05', 'forestswampfinnikforest05'),
    ('FORESTSWAMP', 'FORESTSWAMP01', 'природный блок FORESTSWAMP/FORESTSWAMP01', 'forestswampforestswamp01'),
    ('FORESTSWAMP', 'FORESTSWAMP02', 'природный блок FORESTSWAMP/FORESTSWAMP02', 'forestswamp02'),
    ('FORESTSWAMP', 'FORESTSWAMP05', 'природный блок FORESTSWAMP/FORESTSWAMP05', 'forestswampforestswamp05'),
    ('FORESTSWAMP', 'FORESTSWAMP07', 'природный блок FORESTSWAMP/FORESTSWAMP07', 'forestswampforestswamp07'),
    ('FORESTSWAMP', 'FORESTSWAMP08', 'природный блок FORESTSWAMP/FORESTSWAMP08', 'forestswampforestswamp08'),
    ('FORESTSWAMP', 'FORESTSWAMP11', 'природный блок FORESTSWAMP/FORESTSWAMP11', 'forestswamp11'),
    ('FORESTSWAMP', 'FORESTSWAMP13', 'природный блок FORESTSWAMP/FORESTSWAMP13', 'forestswampforestswamp13'),
    ('FORESTSWAMP', 'FORESTSWAMP15', 'природный блок FORESTSWAMP/FORESTSWAMP15', 'forestswampforestswamp15'),
    ('FORESTSWAMP', 'FORESTSWAMP20', 'природный блок FORESTSWAMP/FORESTSWAMP20', 'forestswampforestswamp20'),
    ('FORESTSWAMP', 'FORESTSWAMPHUGE21', 'природный блок FORESTSWAMP/FORESTSWAMPHUGE21', 'forestswamphuge21'),
    ('FORESTSWAMP', 'FOREST_ROAD_SN02', 'природный блок FORESTSWAMP/FOREST_ROAD_SN02', 'forestswampforestroadsn02'),
    ('FORESTSWAMP', 'FOREST_ROAD_WE00', 'природный блок FORESTSWAMP/FOREST_ROAD_WE00', 'forestswampforestroadwe00'),
    ('FORESTSWAMP', 'SOLFOREST18', 'природный блок FORESTSWAMP/SOLFOREST18', 'forestswampsolforest18'),
    ('FORESTSWAMP_WASTE', 'CIVFOREST00', 'природный блок FORESTSWAMP_WASTE/CIVFOREST00', 'forestswampwastecivforest00'),
    ('FORESTSWAMP_WASTE', 'FINNIKFOREST00', 'природный блок FORESTSWAMP_WASTE/FINNIKFOREST00', 'forestswampwastefinnikforest00'),
    ('FORESTSWAMP_WASTE', 'FINNIKFOREST01', 'природный блок FORESTSWAMP_WASTE/FINNIKFOREST01', 'forestswampwastefinnikforest01'),
    ('FORESTSWAMP_WASTE', 'FINNIKFOREST04', 'природный блок FORESTSWAMP_WASTE/FINNIKFOREST04', 'forestswampwastefinnikforest04'),
    ('FORESTSWAMP_WASTE', 'FINNIKFOREST05', 'природный блок FORESTSWAMP_WASTE/FINNIKFOREST05', 'forestswampwastefinnikforest05'),
    ('FORESTSWAMP_WASTE', 'FINNIKFOREST06', 'природный блок FORESTSWAMP_WASTE/FINNIKFOREST06', 'forestswampwastefinnikforest06'),
    ('FORESTSWAMP_WASTE', 'FOREST05', 'природный блок FORESTSWAMP_WASTE/FOREST05', 'forestswampwasteforest05'),
    ('FORESTSWAMP_WASTE', 'FOREST06', 'природный блок FORESTSWAMP_WASTE/FOREST06', 'forestswampwasteforest06'),
    ('FORESTSWAMP_WASTE', 'FOREST08', 'природный блок FORESTSWAMP_WASTE/FOREST08', 'forestswampwasteforest08'),
    ('FORESTSWAMP_WASTE', 'FORESTSWAMP00', 'природный блок FORESTSWAMP_WASTE/FORESTSWAMP00', 'forestswampwasteforestswamp00'),
    ('FORESTSWAMP_WASTE', 'FORESTSWAMP01', 'природный блок FORESTSWAMP_WASTE/FORESTSWAMP01', 'forestswampwasteforestswamp01'),
    ('FORESTSWAMP_WASTE', 'FORESTSWAMP05', 'природный блок FORESTSWAMP_WASTE/FORESTSWAMP05', 'forestswampwasteforestswamp05'),
    ('FORESTSWAMP_WASTE', 'FORESTSWAMP06', 'природный блок FORESTSWAMP_WASTE/FORESTSWAMP06', 'forestswampwasteforestswamp06'),
    ('FORESTSWAMP_WASTE', 'FORESTSWAMP07', 'природный блок FORESTSWAMP_WASTE/FORESTSWAMP07', 'forestswampwasteforestswamp07'),
    ('FORESTSWAMP_WASTE', 'FORESTSWAMP13', 'природный блок FORESTSWAMP_WASTE/FORESTSWAMP13', 'forestswampwasteforestswamp13'),
    ('FORESTSWAMP_WASTE', 'FORESTSWAMP15', 'природный блок FORESTSWAMP_WASTE/FORESTSWAMP15', 'forestswampwasteforestswamp15'),
    ('FORESTSWAMP_WASTE', 'FORESTSWAMP16', 'природный блок FORESTSWAMP_WASTE/FORESTSWAMP16', 'forestswampwasteforestswamp16'),
    ('FORESTSWAMP_WASTE', 'SOLFOREST12', 'природный блок FORESTSWAMP_WASTE/SOLFOREST12', 'forestswampwastesolforest12'),
    ('FORESTSWAMP_WASTE', 'SOLFOREST13', 'природный блок FORESTSWAMP_WASTE/SOLFOREST13', 'forestswampwastesolforest13'),
    ('FORESTSWAMP_WASTE', 'SOLFOREST15', 'природный блок FORESTSWAMP_WASTE/SOLFOREST15', 'forestswampwastesolforest15'),
    ('FORESTSWAMP_WASTE', 'SOLFOREST16', 'природный блок FORESTSWAMP_WASTE/SOLFOREST16', 'forestswampwastesolforest16'),
    ('FORESTSWAMP_WASTE', 'SOLFOREST17', 'природный блок FORESTSWAMP_WASTE/SOLFOREST17', 'forestswampwastesolforest17'),
    ('FORESTSWAMP_WASTE', 'SOLFOREST18', 'природный блок FORESTSWAMP_WASTE/SOLFOREST18', 'forestswampwastesolforest18'),
    ('JUNGLE', 'JUNGLE10', 'природный блок JUNGLE/JUNGLE10', 'junglejungle10'),
    ('JUNGLE', 'JUNGLE11', 'природный блок JUNGLE/JUNGLE11', 'junglejungle11'),
    ('JUNGLE', 'JUNGLE12', 'природный блок JUNGLE/JUNGLE12', 'junglejungle12'),
    ('JUNGLE', 'JUNGLE13', 'природный блок JUNGLE/JUNGLE13', 'junglejungle13'),
    ('JUNGLE', 'JUNGLEDIO02', 'природный блок JUNGLE/JUNGLEDIO02', 'junglejungledio02'),
    ('JUNGLE', 'JUNGLEDIO03', 'природный блок JUNGLE/JUNGLEDIO03', 'junglejungledio03'),
    ('JUNGLE', 'JUNGLEDIO04', 'природный блок JUNGLE/JUNGLEDIO04', 'junglejungledio04'),
    ('JUNGLE', 'JUNGLEDIO05', 'природный блок JUNGLE/JUNGLEDIO05', 'junglejungledio05'),
    ('JUNGLE', 'JUNGLEDIO07', 'природный блок JUNGLE/JUNGLEDIO07', 'junglejungledio07'),
    ('JUNGLE2BLACK', 'JUNGLE10', 'природный блок JUNGLE2BLACK/JUNGLE10', 'jungle2blackjungle10'),
    ('JUNGLE2BLACK', 'JUNGLE11', 'природный блок JUNGLE2BLACK/JUNGLE11', 'jungle2blackjungle11'),
    ('JUNGLE2BLACK', 'JUNGLE12', 'природный блок JUNGLE2BLACK/JUNGLE12', 'jungle2blackjungle12'),
    ('JUNGLE2BLACK', 'JUNGLE13', 'природный блок JUNGLE2BLACK/JUNGLE13', 'jungle2blackjungle13'),
    ('JUNGLE2BLACK', 'JUNGLEDIO02', 'природный блок JUNGLE2BLACK/JUNGLEDIO02', 'jungle2blackjungledio02'),
    ('JUNGLE2NEO', 'JUNGLE10', 'природный блок JUNGLE2NEO/JUNGLE10', 'jungle2neojungle10'),
    ('JUNGLE2NEO', 'JUNGLE11', 'природный блок JUNGLE2NEO/JUNGLE11', 'jungle2neojungle11'),
    ('JUNGLE2NEO', 'JUNGLE12', 'природный блок JUNGLE2NEO/JUNGLE12', 'jungle2neojungle12'),
    ('JUNGLE2NEO', 'JUNGLE13', 'природный блок JUNGLE2NEO/JUNGLE13', 'jungle2neojungle13'),
    ('JUNGLE2NEO', 'JUNGLEDIO02', 'природный блок JUNGLE2NEO/JUNGLEDIO02', 'jungle2neojungledio02'),
    ('JUNGLESTYX', 'JUNGLE10', 'природный блок JUNGLESTYX/JUNGLE10', 'junglestyxjungle10'),
    ('JUNGLESTYX', 'JUNGLE11', 'природный блок JUNGLESTYX/JUNGLE11', 'junglestyxjungle11'),
    ('JUNGLESTYX', 'JUNGLE12', 'природный блок JUNGLESTYX/JUNGLE12', 'junglestyxjungle12'),
    ('JUNGLESTYX', 'JUNGLEDIO02', 'природный блок JUNGLESTYX/JUNGLEDIO02', 'junglestyxjungledio02'),
    ('JUNGLESTYX', 'JUNGLEDIO03', 'природный блок JUNGLESTYX/JUNGLEDIO03', 'junglestyxjungledio03'),
    ('JUNGLESTYX', 'JUNGLEDIO04', 'природный блок JUNGLESTYX/JUNGLEDIO04', 'junglestyxjungledio04'),
    ('JUNGLESTYX', 'JUNGLEDIO05', 'природный блок JUNGLESTYX/JUNGLEDIO05', 'junglestyxjungledio05'),
    ('JUNGLESTYX', 'JUNGLEDIO07', 'природный блок JUNGLESTYX/JUNGLEDIO07', 'junglestyxjungledio07'),
    ('JUNGLETEMPLE', 'MUJUNGLE02', 'природный блок JUNGLETEMPLE/MUJUNGLE02', 'mujungle02'),
    ('STYXSWAMP', 'FORESTSWAMP00', 'природный блок STYXSWAMP/FORESTSWAMP00', 'styxswampforestswamp00'),
    ('STYXSWAMP', 'FORESTSWAMP05', 'природный блок STYXSWAMP/FORESTSWAMP05', 'styxswampforestswamp05'),
    ('STYXSWAMP', 'FORESTSWAMP06', 'природный блок STYXSWAMP/FORESTSWAMP06', 'styxswampforestswamp06'),
    ('STYXSWAMP', 'FORESTSWAMP08', 'природный блок STYXSWAMP/FORESTSWAMP08', 'styxswampforestswamp08'),
    ('STYXSWAMP', 'FORESTSWAMP13', 'природный блок STYXSWAMP/FORESTSWAMP13', 'styxswampforestswamp13'),
    ('STYXSWAMP', 'FORESTSWAMP15', 'природный блок STYXSWAMP/FORESTSWAMP15', 'styxswampforestswamp15'),
    ('STYXSWAMP', 'FORESTSWAMP16', 'природный блок STYXSWAMP/FORESTSWAMP16', 'styxswampforestswamp16'),
    ('STYXSWAMP', 'FORESTSWAMP20', 'природный блок STYXSWAMP/FORESTSWAMP20', 'styxswampforestswamp20'),
]
PILOT = [(tn, bn, ru) for tn, bn, ru, en in BUILDINGS]
LABEL_EN = {ru: en for tn, bn, ru, en in BUILDINGS}
SIZE = {
    'городской блок COMRCURBAN/COMRCURBANHUGE01': (30, 30),
    'городской блок URBAN/EXPANDEDTERROR18': (20, 20),
    'городской блок URBANJUNKUFO/URBANJUNK23': (20, 20),
    'городской блок URBANJUNKUFO/URBANJUNK30': (20, 20),
    'городской блок URBANJUNKUFO/URBANJUNKDIO_08': (20, 20),
    'городской блок URBANJUNKWOODUFO/URBANJUNK22': (20, 20),
    'городской блок URBANJUNKWOODUFO/URBANJUNK23': (20, 20),
    'городской блок URBANJUNKWOODUFO/URBANJUNK38': (20, 20),
    'городской блок URBANJUNKWOODUFO/URBANJUNK40': (20, 20),
    'городской блок URBANJUNKWOODUFO/URBANJUNK42': (20, 20),
    'городской блок URBANJUNKWOODUFO/URBANJUNKDIO_08': (20, 20),
    'городской блок URBANWAR/EXPANDEDTERROR18': (20, 20),
    'природный блок FOREST/SOLFOREST17': (20, 20),
    'природный блок FOREST2BLACK/CIVFOREST00': (20, 20),
    'природный блок FOREST2BLACK/SOLFOREST17': (20, 20),
    'природный блок FORESTRED/CIVFOREST00': (20, 20),
    'природный блок FORESTRED/SOLFOREST17': (20, 20),
    'природный блок FORESTSNOW/CIVFOREST00': (20, 20),
    'природный блок FORESTSNOW/SOLFOREST17': (20, 20),
    'природный блок FORESTSNOW/SOLFORESTHUGE00': (30, 30),
    'природный блок FORESTSWAMP/FORESTSWAMP01': (20, 20),
    'природный блок FORESTSWAMP/FORESTSWAMP02': (20, 20),
    'природный блок FORESTSWAMP/FORESTSWAMP07': (20, 20),
    'природный блок FORESTSWAMP/FORESTSWAMP08': (20, 20),
    'природный блок FORESTSWAMP/FORESTSWAMP11': (20, 20),
    'природный блок FORESTSWAMP/FORESTSWAMP20': (20, 20),
    'природный блок FORESTSWAMP/FORESTSWAMPHUGE21': (30, 30),
    'природный блок FORESTSWAMP_WASTE/CIVFOREST00': (20, 20),
    'природный блок FORESTSWAMP_WASTE/FORESTSWAMP01': (20, 20),
    'природный блок FORESTSWAMP_WASTE/FORESTSWAMP07': (20, 20),
    'природный блок FORESTSWAMP_WASTE/SOLFOREST17': (20, 20),
    'природный блок STYXSWAMP/FORESTSWAMP08': (20, 20),
    'природный блок STYXSWAMP/FORESTSWAMP20': (20, 20),
}
BOX = {ru: (0, SIZE.get(ru, (10, 10))[0] - 1, 0, SIZE.get(ru, (10, 10))[1] - 1) for tn, bn, ru, en in BUILDINGS}
TREES_IN = set(LABEL_EN)             # ветка D в модели (collapse_pilot_export)
# имя модели в движке: у одноимённых блоков другой модели - с террейном (CollapsePilot ищет модель сейва по имени)
NAME_AS = {
    'городской блок URBAN/EXPANDEDTERROR18': 'URBAN/EXPANDEDTERROR18',
    'городской блок URBANJUNKUFO/URBANJUNK01': 'URBANJUNKUFO/URBANJUNK01',
    'городской блок URBANJUNKUFO/URBANJUNK18': 'URBANJUNKUFO/URBANJUNK18',
    'городской блок URBANJUNKUFO/URBANJUNK19': 'URBANJUNKUFO/URBANJUNK19',
    'городской блок URBANJUNKUFO/URBANJUNK23': 'URBANJUNKUFO/URBANJUNK23',
    'городской блок URBANJUNKUFO/URBANJUNKDIO_08': 'URBANJUNKUFO/URBANJUNKDIO_08',
    'городской блок URBANJUNKWOODUFO/URBANJUNK01': 'URBANJUNKWOODUFO/URBANJUNK01',
    'городской блок URBANJUNKWOODUFO/URBANJUNK10': 'URBANJUNKWOODUFO/URBANJUNK10',
    'городской блок URBANJUNKWOODUFO/URBANJUNK18': 'URBANJUNKWOODUFO/URBANJUNK18',
    'городской блок URBANJUNKWOODUFO/URBANJUNK19': 'URBANJUNKWOODUFO/URBANJUNK19',
    'городской блок URBANJUNKWOODUFO/URBANJUNK23': 'URBANJUNKWOODUFO/URBANJUNK23',
    'городской блок URBANJUNKWOODUFO/URBANJUNKDIO_08': 'URBANJUNKWOODUFO/URBANJUNKDIO_08',
    'городской блок URBANWAR/EXPANDEDTERROR14': 'URBANWAR/EXPANDEDTERROR14',
    'городской блок URBANWAR/EXPANDEDTERROR18': 'URBANWAR/EXPANDEDTERROR18',
    'природный блок FOREST/FINNIKFOREST01': 'FOREST/FINNIKFOREST01',
    'природный блок FOREST/SOLFOREST15': 'FOREST/SOLFOREST15',
    'природный блок FOREST/SOLFOREST17': 'FOREST/SOLFOREST17',
    'природный блок FOREST2BLACK/CIVFOREST00': 'FOREST2BLACK/CIVFOREST00',
    'природный блок FOREST2BLACK/FINNIKFOREST00': 'FOREST2BLACK/FINNIKFOREST00',
    'природный блок FOREST2BLACK/FINNIKFOREST01': 'FOREST2BLACK/FINNIKFOREST01',
    'природный блок FOREST2BLACK/FINNIKFOREST04': 'FOREST2BLACK/FINNIKFOREST04',
    'природный блок FOREST2BLACK/FINNIKFOREST05': 'FOREST2BLACK/FINNIKFOREST05',
    'природный блок FOREST2BLACK/FINNIKFOREST06': 'FOREST2BLACK/FINNIKFOREST06',
    'природный блок FOREST2BLACK/FOREST05': 'FOREST2BLACK/FOREST05',
    'природный блок FOREST2BLACK/FOREST06': 'FOREST2BLACK/FOREST06',
    'природный блок FOREST2BLACK/FOREST07': 'FOREST2BLACK/FOREST07',
    'природный блок FOREST2BLACK/FOREST08': 'FOREST2BLACK/FOREST08',
    'природный блок FOREST2BLACK/SOLFOREST12': 'FOREST2BLACK/SOLFOREST12',
    'природный блок FOREST2BLACK/SOLFOREST13': 'FOREST2BLACK/SOLFOREST13',
    'природный блок FOREST2BLACK/SOLFOREST14': 'FOREST2BLACK/SOLFOREST14',
    'природный блок FOREST2BLACK/SOLFOREST15': 'FOREST2BLACK/SOLFOREST15',
    'природный блок FOREST2BLACK/SOLFOREST16': 'FOREST2BLACK/SOLFOREST16',
    'природный блок FOREST2BLACK/SOLFOREST17': 'FOREST2BLACK/SOLFOREST17',
    'природный блок FOREST2BLACK/SOLFOREST18': 'FOREST2BLACK/SOLFOREST18',
    'природный блок FORESTRED/CIVFOREST00': 'FORESTRED/CIVFOREST00',
    'природный блок FORESTRED/FINNIKFOREST00': 'FORESTRED/FINNIKFOREST00',
    'природный блок FORESTRED/FINNIKFOREST01': 'FORESTRED/FINNIKFOREST01',
    'природный блок FORESTRED/FINNIKFOREST05': 'FORESTRED/FINNIKFOREST05',
    'природный блок FORESTRED/FINNIKFOREST06': 'FORESTRED/FINNIKFOREST06',
    'природный блок FORESTRED/FOREST06': 'FORESTRED/FOREST06',
    'природный блок FORESTRED/FOREST07': 'FORESTRED/FOREST07',
    'природный блок FORESTRED/FOREST08': 'FORESTRED/FOREST08',
    'природный блок FORESTRED/FOREST_ROAD_SN00': 'FORESTRED/FOREST_ROAD_SN00',
    'природный блок FORESTRED/FOREST_ROAD_SN01': 'FORESTRED/FOREST_ROAD_SN01',
    'природный блок FORESTRED/FOREST_ROAD_SN02': 'FORESTRED/FOREST_ROAD_SN02',
    'природный блок FORESTRED/SOLFOREST13': 'FORESTRED/SOLFOREST13',
    'природный блок FORESTRED/SOLFOREST14': 'FORESTRED/SOLFOREST14',
    'природный блок FORESTRED/SOLFOREST15': 'FORESTRED/SOLFOREST15',
    'природный блок FORESTRED/SOLFOREST16': 'FORESTRED/SOLFOREST16',
    'природный блок FORESTRED/SOLFOREST17': 'FORESTRED/SOLFOREST17',
    'природный блок FORESTSNOW/CIVFOREST00': 'FORESTSNOW/CIVFOREST00',
    'природный блок FORESTSNOW/FINNIKFOREST00': 'FORESTSNOW/FINNIKFOREST00',
    'природный блок FORESTSNOW/FINNIKFOREST01': 'FORESTSNOW/FINNIKFOREST01',
    'природный блок FORESTSNOW/FINNIKFOREST04': 'FORESTSNOW/FINNIKFOREST04',
    'природный блок FORESTSNOW/FINNIKFOREST05': 'FORESTSNOW/FINNIKFOREST05',
    'природный блок FORESTSNOW/FINNIKFOREST06': 'FORESTSNOW/FINNIKFOREST06',
    'природный блок FORESTSNOW/FOREST05': 'FORESTSNOW/FOREST05',
    'природный блок FORESTSNOW/FOREST06': 'FORESTSNOW/FOREST06',
    'природный блок FORESTSNOW/FOREST07': 'FORESTSNOW/FOREST07',
    'природный блок FORESTSNOW/FOREST08': 'FORESTSNOW/FOREST08',
    'природный блок FORESTSNOW/FOREST_ROAD_SN00': 'FORESTSNOW/FOREST_ROAD_SN00',
    'природный блок FORESTSNOW/FOREST_ROAD_SN01': 'FORESTSNOW/FOREST_ROAD_SN01',
    'природный блок FORESTSNOW/FOREST_ROAD_SN02': 'FORESTSNOW/FOREST_ROAD_SN02',
    'природный блок FORESTSNOW/FOREST_ROAD_WE00': 'FORESTSNOW/FOREST_ROAD_WE00',
    'природный блок FORESTSNOW/FOREST_ROAD_WE01': 'FORESTSNOW/FOREST_ROAD_WE01',
    'природный блок FORESTSNOW/FOREST_ROAD_WE02': 'FORESTSNOW/FOREST_ROAD_WE02',
    'природный блок FORESTSNOW/FOREST_ROAD_XX00': 'FORESTSNOW/FOREST_ROAD_XX00',
    'природный блок FORESTSNOW/SOLFOREST12': 'FORESTSNOW/SOLFOREST12',
    'природный блок FORESTSNOW/SOLFOREST13': 'FORESTSNOW/SOLFOREST13',
    'природный блок FORESTSNOW/SOLFOREST14': 'FORESTSNOW/SOLFOREST14',
    'природный блок FORESTSNOW/SOLFOREST15': 'FORESTSNOW/SOLFOREST15',
    'природный блок FORESTSNOW/SOLFOREST16': 'FORESTSNOW/SOLFOREST16',
    'природный блок FORESTSNOW/SOLFOREST17': 'FORESTSNOW/SOLFOREST17',
    'природный блок FORESTSWAMP/FINNIKFOREST01': 'FORESTSWAMP/FINNIKFOREST01',
    'природный блок FORESTSWAMP/FINNIKFOREST04': 'FORESTSWAMP/FINNIKFOREST04',
    'природный блок FORESTSWAMP/FINNIKFOREST05': 'FORESTSWAMP/FINNIKFOREST05',
    'природный блок FORESTSWAMP/FORESTSWAMP01': 'FORESTSWAMP/FORESTSWAMP01',
    'природный блок FORESTSWAMP/FORESTSWAMP05': 'FORESTSWAMP/FORESTSWAMP05',
    'природный блок FORESTSWAMP/FORESTSWAMP07': 'FORESTSWAMP/FORESTSWAMP07',
    'природный блок FORESTSWAMP/FORESTSWAMP08': 'FORESTSWAMP/FORESTSWAMP08',
    'природный блок FORESTSWAMP/FORESTSWAMP13': 'FORESTSWAMP/FORESTSWAMP13',
    'природный блок FORESTSWAMP/FORESTSWAMP15': 'FORESTSWAMP/FORESTSWAMP15',
    'природный блок FORESTSWAMP/FORESTSWAMP20': 'FORESTSWAMP/FORESTSWAMP20',
    'природный блок FORESTSWAMP/FOREST_ROAD_SN02': 'FORESTSWAMP/FOREST_ROAD_SN02',
    'природный блок FORESTSWAMP/FOREST_ROAD_WE00': 'FORESTSWAMP/FOREST_ROAD_WE00',
    'природный блок FORESTSWAMP/SOLFOREST18': 'FORESTSWAMP/SOLFOREST18',
    'природный блок FORESTSWAMP_WASTE/CIVFOREST00': 'FORESTSWAMP_WASTE/CIVFOREST00',
    'природный блок FORESTSWAMP_WASTE/FINNIKFOREST00': 'FORESTSWAMP_WASTE/FINNIKFOREST00',
    'природный блок FORESTSWAMP_WASTE/FINNIKFOREST01': 'FORESTSWAMP_WASTE/FINNIKFOREST01',
    'природный блок FORESTSWAMP_WASTE/FINNIKFOREST04': 'FORESTSWAMP_WASTE/FINNIKFOREST04',
    'природный блок FORESTSWAMP_WASTE/FINNIKFOREST05': 'FORESTSWAMP_WASTE/FINNIKFOREST05',
    'природный блок FORESTSWAMP_WASTE/FINNIKFOREST06': 'FORESTSWAMP_WASTE/FINNIKFOREST06',
    'природный блок FORESTSWAMP_WASTE/FOREST05': 'FORESTSWAMP_WASTE/FOREST05',
    'природный блок FORESTSWAMP_WASTE/FOREST06': 'FORESTSWAMP_WASTE/FOREST06',
    'природный блок FORESTSWAMP_WASTE/FOREST08': 'FORESTSWAMP_WASTE/FOREST08',
    'природный блок FORESTSWAMP_WASTE/FORESTSWAMP00': 'FORESTSWAMP_WASTE/FORESTSWAMP00',
    'природный блок FORESTSWAMP_WASTE/FORESTSWAMP01': 'FORESTSWAMP_WASTE/FORESTSWAMP01',
    'природный блок FORESTSWAMP_WASTE/FORESTSWAMP05': 'FORESTSWAMP_WASTE/FORESTSWAMP05',
    'природный блок FORESTSWAMP_WASTE/FORESTSWAMP06': 'FORESTSWAMP_WASTE/FORESTSWAMP06',
    'природный блок FORESTSWAMP_WASTE/FORESTSWAMP07': 'FORESTSWAMP_WASTE/FORESTSWAMP07',
    'природный блок FORESTSWAMP_WASTE/FORESTSWAMP13': 'FORESTSWAMP_WASTE/FORESTSWAMP13',
    'природный блок FORESTSWAMP_WASTE/FORESTSWAMP15': 'FORESTSWAMP_WASTE/FORESTSWAMP15',
    'природный блок FORESTSWAMP_WASTE/FORESTSWAMP16': 'FORESTSWAMP_WASTE/FORESTSWAMP16',
    'природный блок FORESTSWAMP_WASTE/SOLFOREST12': 'FORESTSWAMP_WASTE/SOLFOREST12',
    'природный блок FORESTSWAMP_WASTE/SOLFOREST13': 'FORESTSWAMP_WASTE/SOLFOREST13',
    'природный блок FORESTSWAMP_WASTE/SOLFOREST15': 'FORESTSWAMP_WASTE/SOLFOREST15',
    'природный блок FORESTSWAMP_WASTE/SOLFOREST16': 'FORESTSWAMP_WASTE/SOLFOREST16',
    'природный блок FORESTSWAMP_WASTE/SOLFOREST17': 'FORESTSWAMP_WASTE/SOLFOREST17',
    'природный блок FORESTSWAMP_WASTE/SOLFOREST18': 'FORESTSWAMP_WASTE/SOLFOREST18',
    'природный блок JUNGLE/JUNGLE10': 'JUNGLE/JUNGLE10',
    'природный блок JUNGLE/JUNGLE11': 'JUNGLE/JUNGLE11',
    'природный блок JUNGLE/JUNGLE12': 'JUNGLE/JUNGLE12',
    'природный блок JUNGLE/JUNGLE13': 'JUNGLE/JUNGLE13',
    'природный блок JUNGLE/JUNGLEDIO02': 'JUNGLE/JUNGLEDIO02',
    'природный блок JUNGLE/JUNGLEDIO03': 'JUNGLE/JUNGLEDIO03',
    'природный блок JUNGLE/JUNGLEDIO04': 'JUNGLE/JUNGLEDIO04',
    'природный блок JUNGLE/JUNGLEDIO05': 'JUNGLE/JUNGLEDIO05',
    'природный блок JUNGLE/JUNGLEDIO07': 'JUNGLE/JUNGLEDIO07',
    'природный блок JUNGLE2BLACK/JUNGLE10': 'JUNGLE2BLACK/JUNGLE10',
    'природный блок JUNGLE2BLACK/JUNGLE11': 'JUNGLE2BLACK/JUNGLE11',
    'природный блок JUNGLE2BLACK/JUNGLE12': 'JUNGLE2BLACK/JUNGLE12',
    'природный блок JUNGLE2BLACK/JUNGLE13': 'JUNGLE2BLACK/JUNGLE13',
    'природный блок JUNGLE2BLACK/JUNGLEDIO02': 'JUNGLE2BLACK/JUNGLEDIO02',
    'природный блок JUNGLE2NEO/JUNGLE10': 'JUNGLE2NEO/JUNGLE10',
    'природный блок JUNGLE2NEO/JUNGLE11': 'JUNGLE2NEO/JUNGLE11',
    'природный блок JUNGLE2NEO/JUNGLE12': 'JUNGLE2NEO/JUNGLE12',
    'природный блок JUNGLE2NEO/JUNGLE13': 'JUNGLE2NEO/JUNGLE13',
    'природный блок JUNGLE2NEO/JUNGLEDIO02': 'JUNGLE2NEO/JUNGLEDIO02',
    'природный блок JUNGLESTYX/JUNGLE10': 'JUNGLESTYX/JUNGLE10',
    'природный блок JUNGLESTYX/JUNGLE11': 'JUNGLESTYX/JUNGLE11',
    'природный блок JUNGLESTYX/JUNGLE12': 'JUNGLESTYX/JUNGLE12',
    'природный блок JUNGLESTYX/JUNGLEDIO02': 'JUNGLESTYX/JUNGLEDIO02',
    'природный блок JUNGLESTYX/JUNGLEDIO03': 'JUNGLESTYX/JUNGLEDIO03',
    'природный блок JUNGLESTYX/JUNGLEDIO04': 'JUNGLESTYX/JUNGLEDIO04',
    'природный блок JUNGLESTYX/JUNGLEDIO05': 'JUNGLESTYX/JUNGLEDIO05',
    'природный блок JUNGLESTYX/JUNGLEDIO07': 'JUNGLESTYX/JUNGLEDIO07',
    'природный блок STYXSWAMP/FORESTSWAMP00': 'STYXSWAMP/FORESTSWAMP00',
    'природный блок STYXSWAMP/FORESTSWAMP05': 'STYXSWAMP/FORESTSWAMP05',
    'природный блок STYXSWAMP/FORESTSWAMP06': 'STYXSWAMP/FORESTSWAMP06',
    'природный блок STYXSWAMP/FORESTSWAMP08': 'STYXSWAMP/FORESTSWAMP08',
    'природный блок STYXSWAMP/FORESTSWAMP13': 'STYXSWAMP/FORESTSWAMP13',
    'природный блок STYXSWAMP/FORESTSWAMP15': 'STYXSWAMP/FORESTSWAMP15',
    'природный блок STYXSWAMP/FORESTSWAMP16': 'STYXSWAMP/FORESTSWAMP16',
    'природный блок STYXSWAMP/FORESTSWAMP20': 'STYXSWAMP/FORESTSWAMP20',
}


def load():
    """Как collapse_pilot9_scen.load: целые блоки карт своего террейна (collapse_census.all_blocks)."""
    import collapse_ctype as CT
    import collapse_v2 as V
    import collapse_census as cc
    import collapse_attach_v2 as A2
    C = A2.use()
    roles = V.load_roles()
    args = V.game_args()
    out = []
    for tn, bn, label in PILOT:
        got = [blk for _, _, _, _, blk, err, _ in cc.all_blocks(args, only_block=bn, only_terrain=tn) if blk]
        if len(got) != 1:
            raise SystemExit("блок %s/%s: найдено %d" % (tn, bn, len(got)))
        blk = got[0]
        if (blk.sx, blk.sy) != (BOX[label][1] + 1, BOX[label][3] + 1):
            raise SystemExit("блок %s/%s: размер %dx%d не совпал с участком" % (tn, bn, blk.sx, blk.sy))
        V.apply_roles(blk, roles)
        C.apply_marks(blk)
        out.append((tn, bn, label, blk))
    return C, CT, out


def use():
    """Переключает collapse_pilot_scen на список, загрузку и файлы этой партии."""
    PS.OUT = OUT
    PS.SCEN = OUT + "/pilot_scen.tsv"
    PS.LOCK = OUT + "/pilot_scen.lock.txt"
    PS.RESULT = OUT + "/pilot_result.tsv"
    PS.PILOT = PILOT
    PS.load = load
    return PS


def cmd_define():
    use()
    PS.cmd_define()
    with open(PS.LOCK, "a", encoding=PS.ENC) as f:
        f.write("%s\t%s\n" % ("tools/collapse_pilot10_scen.py", PS.sha("tools/collapse_pilot10_scen.py")))


if __name__ == "__main__":
    os.chdir(os.path.dirname(HERE))
    sys.stdout.reconfigure(encoding="utf-8")
    import collapse_v7d as D
    D.install()                                   # M0j4, как заголовок игры
    cmd = sys.argv[1] if len(sys.argv) > 1 else "define"
    if cmd == "define":
        cmd_define()
