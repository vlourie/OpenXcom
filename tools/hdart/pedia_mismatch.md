# Картинки педии против текста статей: разбор 102 непохожих

Дата: 18.09. Инструменты: `tools\hdart\pedia_text.py` (картинка → статья → текст) и
`tools\hdart\pedia_review.py` (оригинал + HD рядом, плюс метрика расхождения).
Результат разбора уложен в строки `tools\hdart\photo_hints.txt`.

## Как собирается связка «картинка ↔ текст»

`Resources/Pedia/<имя>.png` → `extraSprites: typeSingle/fileSingle` → `ufopaedia: image_id` →
`id:` (заголовок) и `text:` (тело) → `Language/en-US.yml` и `Language/ru.yml`.
Слайды концовок (`imagePath` + `caption`) подхватываются отдельно.

Из 102 имён статью нашли у 101 (`Captain_GrayNoGold` нигде не используется как `image_id` —
судил только по оригиналу). Всего картинок со статьёй в моде: **2125**.

## Что именно ломается

Семь типов, по убыванию частоты.

**1. Смена пола и вида (23 картинки).** Пиксель-арт неоднозначен, и модель сваливается
в мужчину-бодибилдера или в «породистое» животное:
`Sadako`, `C_004`, `C_042`, `C_069`, `C_199`, `Brainer_Ritsuko_Pinup`, `Ogress_Defeated`,
`VIP_3`, `Zombie_Witch_1`, `Concealed`, `CrimeLord_FG_353_CPAL`, `Nationalization`,
`ExploringTunnels_FG_345`, `Huntress`, `CA_Warbike_CPAL`, `Dragon_Galley`, `C_104`, `GDX_Out`,
`Pumas` (кошкодевочки → львы-самцы), `Big_Cat` (львица → тигр), `BeastmenScience`,
`BloodDogPed`, `Nekomimi_Warlord`.

**2. Дорисованные люди (11).** Пустая сцена получает фигуру в середине:
`Space_City`, `Cave1`, `Orbit`, `Industrial_CPAL`, `Laser_Nuclear_Ped`, `Aqua_Plastics`,
`Area_South`, `CA_13_CPAL`, `CA_17_CPAL`, `XX01`, `The_Pit`. Плюс `Shield_Ped` — там
две крошечные фигурки вдали превратились в героев на переднем плане, и `Hybrid_Examination` —
второй, лишний пришелец.

**3. Пропал ключевой элемент (18).** То, ради чего картинка нарисована:
взрыв (`XX50`, `Area_Murrica`, `Death_Race`), сияющий камень пирамиды (`XX01`),
светящийся клинок (`AI_Loknar_Assassin`), полярное сияние (`Aurora_Gnome` — вся статья про него),
вуаль (`Gudrun_Veil1_CPAL`), повязка на глаз (`C_074_CPAL`), HUD-панели и таймер 03:37
(`Aurora_Apparition_CPAL`), эмблема серпа и молота (`Nationalization`), корона в зеркале
(`MirrorMirror_CPAL`), сигарета (`Zombie_Witch_1`), маска и горящие окуляры (`VIP_14`),
светящиеся глаза (`Demonic_Transformation`, `AI_Lokk_Scav2`), «666» на знаке (`XX50`),
шлем-пузырь (`Z_Pod`), оранжевая линза камеры (`Humanist_Files`).

**4. Противоречие тексту (2, но грубое).** `MBT` и `Hovertanks_CPAL`: в статье
«MILITARY-GRADE **HOVERTANKS**», на оригинале машина парит — модель пририсовала гусеницы
и катки.

**5. Подмена предмета (9).** Пистолет → второй меч (`Akimbo_Lady`), планшет → катана
(`Brainer_Ritsuko`), M16 → фантастическая пушка (`C_073_CPAL`), энергощит → жезл с человеческим
глазом (`AlienShields`), тарелка пришельцев → кит с усоногими (`H_006`), мозг → каменный трон
(`Wojakbrain`), чертёж-контур → фотореалистичная пушка (`Gauss_Basic_Ped`), зелёный трафарет
механизмов → лицо и руки, вплавленные в трубы (`HeavyDutyPed`), жидкий металл → тётка в броне
(`Monolit`).

**6. Одели или раздели (12).** Модель добавляет одежду, которой нет:
`AI_Wild1`, `BlueWitch_FG_32_CPAL`, `Beastmen_Taming_CPAL`, `C_018_CPAL`,
`Captain_GoldGreen_CPAL`, `Demonic_Bondage`, `Aurora_Apparition_CPAL`, `Pharmacology_CPAL`,
`Gudrun_Explorations_5`, `Ice_Damsel`, `Ressurect`, `Gnome_16B` (доспехи поверх голой кожи).

**7. Артефакты модели (17).** Веснушки, поры, «чешуя» и трещины на коже, потные блики:
`Access_Denied_CPAL`, `Hoverbike`, `Aurora_Pirate_FG_364_CPAL`, `Captain_GrayGreen`,
`Captain_GrayGreenOnly_CPAL`, `Captain_GoldGreen_CPAL`, `MedExam_CPAL`, `C_018_CPAL`,
`C_069`, `C_199`, `Gnome_16B`, `Ice_Damsel`, `VIP_3`, `Zombie_Witch_1`, `Ogress_Defeated`,
`Concealed`, `Area_Murrica`. Отдельно: `Astronaughty_CPAL` — жёлтая крапина по броне,
`Gauss_Basic_Ped` — пузыри по стволу, `XX20` — слизь и человеческие зубы.

**Фоновая привычка модели:** заращивать всё мхом, плющом и травой там, где их нет
(`Nekomimi_Warlord`, `Yig`, `BeastmenScience`, `Dark_Chamber`, `C_069`, `Area_Asia`,
`AnnihilatorGal_FG_392_CPAL`, `Fungus_Adaptation`, `The_Pit`, `Animatrons`,
`Gudrun_Explorations_5`) и переводить тёплый свет в холодный синий
(`Beastmen_Taming_CPAL`, `Dark_Chamber`, `Area_Murrica`, `MedExam_CPAL`, `Ressurect`).

## Что приемлемо

Три картинки почти в порядке: `AI_Hooded_CPAL` (для неё подсказка уже была),
`C_074_CPAL`, `CA_19`, `XX20`, `Powergal`, `Dark_Chamber_2`,
`AnnihilatorGal_FG_392_CPAL` — там расхождение мелкое, но подсказки всё равно написаны.

## Дальше

1. Положить новый `photo_hints.txt` в `tools\hdart\`.
2. Перегенерировать 102 штуки **без `--fast`** (иначе негативы не работают: нужен CFG > 1):

   ```
   py -3 tools\hdart\photo_ui.py --names @tools\hdart\rejected_files.txt --force
   ```

3. Прогнать `pedia_review.py` заново по тем же именам и посмотреть листы.
4. Ужать заново: `py -3 tools\hdart\optimize_hd.py --mod ...\user\mods\hd`.

Метрика расхождения в `report.csv` (`shape` — совпадение краёв, `colour` — расстояние по цвету)
годится, чтобы прогнать её по всем 1700 картинкам и найти следующую партию кандидатов:
у разобранных здесь `shape` в основном ниже 0.55.
