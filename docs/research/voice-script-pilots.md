# Голоса пилотов на глобусе (тикет XP-000246)

Реплики экипажа посудин на глобусе: выбор, приказ, цель, сопровождение, возврат, перелёт на другую базу,
вылет звена, отбой, повреждение, пустые стволы. Летающая техника (maxAltitude 2 и выше) говорит голосом
пилота V901, наземная (байки, машины, танки, пешие отряды - maxAltitude 1 и ниже) - водителя V902.
Подзаголовок раздела - событие движка (HdPilotVoice), файлы - hd/PILOT/<air|ground>/<событие>/<ru|en>_NN.ogg.
Формат карточки - как в voice-recording-script.md (tools/sfx/voice_script.py), запись - tools/sfx/gen_pilot_voices.py.

## Пилоты

### V901 — Пилот посудины [Ж]

**Для кого:** летающие посудины игрока на глобусе.

**По игре:** Пиратка за штурвалом, говорит по рации с базой: коротко, дерзко, с весельем человека, который любит летать.

**Как играть голосом:** Женский голос средней высоты, бодрый и собранный, говорит в рацию: чётко, быстро, с улыбкой; при повреждении - напряжённо, но без истерики.

**select**

| № | Русский | English |
| --- | --- | --- |
| 01 | Борт на связи. | Bird here. |
| 02 | Слушаю, кэп. | Listening, Cap. |
| 03 | За штурвалом. Куда летим? | At the stick. Where to? |
| 04 | Моторы тёплые, жду приказа. | Engines warm, awaiting orders. |
| 05 | На связи. Говори. | On the line. Talk. |
| 06 | Пилот слушает. | Pilot listening. |

**order**

| № | Русский | English |
| --- | --- | --- |
| 07 | Принято, ложусь на курс. | Copy, setting course. |
| 08 | Курс взят. | Course locked. |
| 09 | Понял, лечу. | Got it, flying. |
| 10 | Есть. Будем там раньше, чем ждут. | Aye. We'll beat them there. |
| 11 | Принято. Держитесь крепче. | Copy. Hold on tight. |
| 12 | Уже в пути. | Already on my way. |

**attack**

| № | Русский | English |
| --- | --- | --- |
| 13 | Цель вижу. Иду на перехват. | Target sighted. Moving to intercept. |
| 14 | Перехват. Стволы к бою. | Intercept. Guns hot. |
| 15 | Сейчас мы их пощиплем. | Time to pluck some feathers. |
| 16 | Цель взята. Захожу. | Target locked. Going in. |
| 17 | Ну держись, железяка. | Brace yourself, tin can. |
| 18 | На перехват, кэп. | Intercepting, Cap. |

**escort**

| № | Русский | English |
| --- | --- | --- |
| 19 | Прикрываю. | Covering you. |
| 20 | Иду ведомой. | Flying wing. |
| 21 | Держусь рядом. | Staying close. |
| 22 | Сопровождаю, хвост чистый. | Escorting, your tail's clear. |
| 23 | Пристраиваюсь сзади. | Forming up behind. |
| 24 | Есть сопровождение. | Escort, aye. |

**return**

| № | Русский | English |
| --- | --- | --- |
| 25 | Возвращаюсь на базу. | Heading home. |
| 26 | Домой. Ставьте чайник. | Going home. Put the kettle on. |
| 27 | Принято, иду на базу. | Copy, back to base. |
| 28 | Разворачиваюсь. Домой. | Turning around. Home. |
| 29 | Возвращаюсь. Ангар не закрывайте. | Returning. Keep the hangar open. |
| 30 | Иду на посадку к своим. | Coming in to land. |

**rebase**

| № | Русский | English |
| --- | --- | --- |
| 31 | Перебазируюсь. | Relocating. |
| 32 | Новая база? Ну, посмотрим. | New base? Let's have a look. |
| 33 | Принято, лечу к соседям. | Copy, off to the neighbours. |
| 34 | Меняю прописку. | Changing address. |
| 35 | Курс на другую базу. | Course for the other base. |
| 36 | Перелёт. Вещи не забыла. | Transfer. Got my stuff. |

**wing**

| № | Русский | English |
| --- | --- | --- |
| 37 | Звено, за мной! | Flight, on me! |
| 38 | Взлетаем вместе. | Taking off together. |
| 39 | Звено в воздухе. | Flight's airborne. |
| 40 | Строимся, девочки. | Form up, girls. |
| 41 | Все за мной, не отставать. | Everyone follow, keep up. |
| 42 | Звено готово, идём. | Flight ready, moving out. |

**cancel**

| № | Русский | English |
| --- | --- | --- |
| 43 | Отбой. | Stand down. |
| 44 | Ну, как скажешь. | Well, if you say so. |
| 45 | Отбой. Жду дальше. | Standing down. Waiting. |
| 46 | Ладно, остаюсь. | Fine, I'll stay. |
| 47 | Понял, отмена. | Copy, cancelled. |
| 48 | Передумал, кэп? | Changed your mind, Cap? |

**damaged**

| № | Русский | English |
| --- | --- | --- |
| 49 | Нас задели! | We're hit! |
| 50 | Пробоина! Держусь! | Hull breach! Holding on! |
| 51 | Дымим, кэп! | We're smoking, Cap! |
| 52 | Попали в нас! | They got us! |
| 53 | Обшивка трещит! | The hull's cracking! |
| 54 | Тяну, но нам досталось. | Holding it together, but we're hurt. |

**noammo**

| № | Русский | English |
| --- | --- | --- |
| 55 | Стволы пустые! | Guns are dry! |
| 56 | Боезапас кончился! | Out of ammo! |
| 57 | Нечем стрелять, кэп! | Nothing left to shoot, Cap! |
| 58 | Пусто! Только ругаться осталось. | Empty! All I've got left is swearing. |
| 59 | Патроны всё. | That's the last round. |
| 60 | Пушка молчит, нужен ремонт и патроны. | Gun's quiet, need ammo. |

### V902 — Водитель наземной техники [Ж]

**Для кого:** наземная техника игрока на глобусе: байки, машины, танки, конвои, пешие отряды.

**По игре:** Механик-водитель пиратской команды: грубоватая, весёлая, любит мотор и дорогу, говорит по рации.

**Как играть голосом:** Женский голос средней высоты, хрипловатый от дорожной пыли, уверенный и насмешливый; в рацию, коротко.

**select**

| № | Русский | English |
| --- | --- | --- |
| 01 | За рулём. | Behind the wheel. |
| 02 | Мотор урчит, кэп. | Engine's purring, Cap. |
| 03 | Водила на связи. | Driver here. |
| 04 | Ну, куда едем? | So, where are we going? |
| 05 | Колёса накачаны, жду. | Tyres pumped, waiting. |
| 06 | Слушаю. | Listening. |

**order**

| № | Русский | English |
| --- | --- | --- |
| 07 | Едем. | Rolling. |
| 08 | Принято, выдвигаюсь. | Copy, moving out. |
| 09 | По газам. | Pedal down. |
| 10 | Дорога есть, доеду. | There's a road, I'll get there. |
| 11 | Есть. Пыль за мной. | Aye. Eat my dust. |
| 12 | Трогаемся. | Moving. |

**attack**

| № | Русский | English |
| --- | --- | --- |
| 13 | Цель вижу, давлю газ. | Target sighted, flooring it. |
| 14 | Сейчас переедем. | We'll run them over. |
| 15 | Едем бить морды. | Off to smash faces. |
| 16 | Цель взята, иду напролом. | Target locked, going straight through. |
| 17 | Держитесь, будет тряско. | Hold on, it'll get bumpy. |
| 18 | На таран, кэп! | Ramming speed, Cap! |

**escort**

| № | Русский | English |
| --- | --- | --- |
| 19 | Еду следом. | Following. |
| 20 | Держусь в колонне. | Keeping in convoy. |
| 21 | Прикрываю сзади. | Covering the rear. |
| 22 | Не отстану. | I won't fall behind. |
| 23 | В хвосте, всё чисто. | At the tail, all clear. |
| 24 | Есть сопровождение. | Escort, aye. |

**return**

| № | Русский | English |
| --- | --- | --- |
| 25 | Еду домой. | Driving home. |
| 26 | Разворот, на базу. | U-turn, back to base. |
| 27 | Принято, возвращаюсь. | Copy, returning. |
| 28 | Домой, к ужину успею. | Home, I'll make it for dinner. |
| 29 | Гараж открывайте. | Open the garage. |
| 30 | Возвращаюсь, бак почти пустой. | Coming back, tank's nearly empty. |

**rebase**

| № | Русский | English |
| --- | --- | --- |
| 31 | Переезжаю. | Moving out. |
| 32 | Новая база, новая дорога. | New base, new road. |
| 33 | Принято, еду к соседям. | Copy, off to the neighbours. |
| 34 | Далеко? Ну, доеду. | Far? I'll get there. |
| 35 | Курс на другую базу. | Heading for the other base. |
| 36 | Перегон. Ничего не забыла. | Long haul. Got everything. |

**wing**

| № | Русский | English |
| --- | --- | --- |
| 37 | Колонна, за мной! | Convoy, follow me! |
| 38 | Едем все вместе. | All rolling together. |
| 39 | Колонна пошла. | Convoy's moving. |
| 40 | Строимся, девочки, едем. | Line up, girls, let's go. |
| 41 | Не растягиваться! | Don't string out! |
| 42 | Все по машинам. | Everyone mount up. |

**cancel**

| № | Русский | English |
| --- | --- | --- |
| 43 | Глушу мотор. | Killing the engine. |
| 44 | Ну и ладно. | Fine then. |
| 45 | Отбой. Стою. | Stand down. Parked. |
| 46 | Стою, жду. | Parked, waiting. |
| 47 | Понял, отмена. | Copy, cancelled. |
| 48 | Передумал? Бывает. | Changed your mind? Happens. |

**damaged**

| № | Русский | English |
| --- | --- | --- |
| 49 | Нас задели! | We're hit! |
| 50 | Броню пробили! | Armour's breached! |
| 51 | Дымим, кэп! | We're smoking, Cap! |
| 52 | Колесо, мать его! | The wheel, damn it! |
| 53 | Попали! Еду дальше! | Hit! Still rolling! |
| 54 | Досталось, но едем. | Took a beating, but we're moving. |

**noammo**

| № | Русский | English |
| --- | --- | --- |
| 55 | Стволы пустые! | Guns are dry! |
| 56 | Боезапас кончился! | Out of ammo! |
| 57 | Нечем стрелять, кэп! | Nothing left to shoot, Cap! |
| 58 | Пусто! Остаётся таранить. | Empty! Only ramming left. |
| 59 | Патроны всё. | That's the last round. |
| 60 | Пушка молчит. | Gun's quiet. |
