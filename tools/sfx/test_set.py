"""Тестовый набор звука: шаги по персонажу и голоса бойцов на двух языках.

Общие данные для генераторов (gen_steps_test.py - Stable Audio 3, gen_voices_test.py -
VoxCPM2 + Fish S2 Pro) и сборщика модов (build_test_mods.py). Всё сгенерированное лежит в
art/sfx/test_set/, моды собираются в user/mods установки Пираток.

Как устроено в игре и почему так - docs/research/sound-test-set.md.
"""

# ---------------------------------------------------------------------------- шаги
# Материал пола - смещение footstepSound в MCD (WALK_OFFSET + 2*тип). Тип 0 играет удар и
# крик (22/23), а не шаг, - его не трогаем (перепись в AUDIO_ROADMAP.md, «Сколько звучит сейчас»).
MATERIALS = [
    (1, "metal", "a metal deck floor plate"),
    (2, "ground", "packed dirt ground"),
    (3, "rock", "crunchy alien gravel and rock"),
    (4, "water", "a shallow water puddle"),
    (5, "sand", "dry loose sand"),
    (6, "snow", "crunchy fresh snow"),
]

# Класс обуви: подпись, кусок промпта и брони Пираток, которым он достаётся в тесте.
# Брони выбраны без своего moveSound (у таких скрипт брони не трогает ход техники).
STEP_CLASSES = [
    ("barefoot", "босиком", "a single bare foot slap step",
     ["STR_PIR_NUDE_UC", "STR_PIR_TOPLESS_UC", "STR_PIR_CASTAWAY_ARMOR_UC", "STR_RAGS_UC",
      "STR_NEKO_NUDE_UC", "STR_SYNTH_NUDE_UC"]),
    ("boots", "ботинки", "a single leather combat boot footstep",
     ["STR_GANGER_OUTFIT_UC", "STR_BASIC_ARMOR_UC", "STR_SLAVE_PUNK_UC", "STR_NEKO_STS_UC",
      "STR_GNOME_DRESS_UC"]),
    ("heels", "каблуки", "a single high heel shoe click footstep",
     ["STR_DAMSEL_PATRON_DRESS_UC"]),
    ("heavy", "тяжёлая броня", "a single heavy armored metal boot footstep with a servo whir",
     ["STR_LOOTED_RAIDER_BOSS_ARMOR_UC", "STR_KILLBOT_ARMOR_UC"]),
    ("claws", "лапы с когтями", "a single large dog paw step with claws clicking",
     ["STR_DOGE_UNARMORED_UC", "STR_BLOODOGE_UNARMORED_UC"]),
]
STEP_VARIANTS = 4        # в игре на материал
STEP_CANDIDATES = 8      # генерируем, лучшие STEP_VARIANTS - в мод
STEP_MAX_S = 0.45        # длина шага в игре 0.24-0.47 с (census/sounds.tsv)
STEP_TAIL = ", close perspective, dry, isolated sound effect, no music, no voice"

# ---------------------------------------------------------------------------- голоса
CATEGORIES = ["select", "move", "weapon", "annoyed"]
# Подача по категории - тег Fish S2 Pro (свободный текст в квадратных скобках)
CATEGORY_TAG = {
    "select": "[casual]",
    "move": "[confident]",
    "weapon": "[excited]",
    "annoyed": "[annoyed]",
}

# gender: 0 мужской, 1 женский (SoldierGender); soldiers - кому выдаётся набор.
HUMAN_GALS = ["STR_SOLDIER", "STR_SOLDIER_M", "STR_SOLDIER_S", "STR_SOLDIER_R", "STR_SOLDIER_V",
              "STR_SOLDIER_W", "STR_SOLDIER_X", "STR_SOLDIER_SLAVE", "STR_SOLDIER_HERO",
              "STR_SOLDIER_PEASANT", "STR_SOLDIER_DAMSEL", "STR_SOLDIER_GNOME"]
NEKO = ["STR_SOLDIER_NEKOMIMI", "STR_SOLDIER_NEKOMIMI_H", "STR_SOLDIER_NEKOMIMI_O",
        "STR_SOLDIER_NEKOMIMI_W"]

VOICES = {
    "bosun": {
        "title": "Боцманша",
        "soldiers": HUMAN_GALS, "genders": [1],
        "f0": (180, 500),
        # «низкий прокуренный» VoxCPM2 понял как мужской (15.10, 140-155 Гц) - пол прямо, высота средняя
        "design": "женщина лет сорока, женский голос средней высоты с лёгкой хрипотцой, пиратка-боцман, грубовато и насмешливо",
        "ref_text": "Слушай сюда, юнга. На этом корабле я решаю, кто пьёт ром, а кто драит палубу. Усёк?",
        "lines": {
            "ru": {
                "select": ["Чё надо?", "Слушаю, капитан.", "Ну?", "Боцман на связи.", "Быстрее, ром стынет."],
                "move": ["Пошла.", "Ладно, ладно.", "Шевелю булками!", "Уже бегу. Медленно.", "Курс принят."],
                "weapon": ["О, моя прелесть.", "Сейчас будет громко.", "Заряжено.", "Кого валим?", "Дай пострелять!"],
                "annoyed": ["Отвали, а?", "Ещё раз ткнёшь — укушу.", "Я тебе не кнопка!", "Капитан, ну хорош.", "Тыкай юнгу."],
            },
            "en": {
                "select": ["What now?", "Aye, captain.", "Well?", "Bosun here.", "Quick, my rum's getting warm."],
                "move": ["Going.", "Fine, fine.", "Moving my rear!", "On my way. Slowly.", "Course set."],
                "weapon": ["Hello, gorgeous.", "This'll be loud.", "Locked and loaded.", "Who do we kill?", "Gimme, gimme!"],
                "annoyed": ["Back off, will ya?", "Poke me again, I bite.", "I'm not a button!", "Captain, quit it.", "Go poke the cabin boy."],
            },
        },
    },
    "kawaii": {
        "title": "Кавайка",
        "soldiers": HUMAN_GALS, "genders": [1],
        "f0": (180, 500),
        "design": "высокий звонкий девичий голос в стиле аниме, очень бодро, мило и восторженно",
        "ref_text": "Ура-ура, меня взяли в команду! Я буду самой полезной пираткой на всём корабле, честно-честно!",
        "lines": {
            "ru": {
                "select": ["Да-да, семпай!", "Я тут!", "Ня? Ой, то есть да!", "Готова на всё!", "Кья, меня выбрали!"],
                "move": ["Бегу-бегу!", "Вперёд, к приключениям!", "Хай-хай!", "Топ-топ-топ!", "Лечу!"],
                "weapon": ["Время пиу-пиу!", "Сила дружбы и свинца!", "Сейчас бахну!", "Кавайный калибр!", "Получат по попке!"],
                "annoyed": ["Ну семпа-ай!", "Хватит тыкать, бака!", "Я обижусь!", "Щекотно же!", "Сейчас покусаю!"],
            },
            "en": {
                "select": ["Yes, yes, senpai!", "I'm here!", "Nya? I mean, yes!", "Ready for anything!", "Kya, you picked me!"],
                "move": ["Running, running!", "Adventure time!", "Hai, hai!", "Zoom zoom!", "Flying!"],
                "weapon": ["Pew pew time!", "Power of friendship and lead!", "Gonna go boom!", "Kawaii caliber!", "Spanking time!"],
                "annoyed": ["Senpa-ai!", "Stop poking, baka!", "I'm gonna sulk!", "That tickles!", "I'll bite you!"],
            },
        },
    },
    "brute": {
        "title": "Громила",
        "soldiers": HUMAN_GALS, "genders": [0],
        "f0": (60, 130),
        "design": "очень низкий глубокий мужской бас, крупный мужчина, простоватый громила, говорит с ленцой и ухмылкой",
        "ref_text": "Короче, братан, мне без разницы, кого бить. Ты только покажи, а дальше я сам разберусь.",
        "lines": {
            "ru": {
                "select": ["Ну чё?", "Здорово, начальник.", "Слушаю, братан.", "Кого бить?", "Я тут, я тут."],
                "move": ["Иду, иду.", "Без проблем.", "Ща сделаем.", "Расступись!", "Поехали."],
                "weapon": ["Ща как дам!", "Тяжёлая артиллерия.", "О, железяка!", "Ну всё, держитесь.", "Бах — и нету."],
                "annoyed": ["Слышь, не тыкай.", "Я ж нервный.", "Ещё раз — и в бубен.", "Ты чё, самый умный?", "Отвянь."],
            },
            "en": {
                "select": ["Yeah, what?", "Hey, boss.", "Talk to me, bro.", "Who do I punch?", "Here, here."],
                "move": ["Going, going.", "No problem.", "On it.", "Make way!", "Let's roll."],
                "weapon": ["Gonna smack 'em!", "Heavy artillery.", "Ooh, shiny!", "That's it, you're done.", "Bang. Gone."],
                "annoyed": ["Hey, no poking.", "I'm the nervous type.", "Once more and you get it.", "Think you're smart?", "Buzz off."],
            },
        },
    },
    "neko": {
        "title": "Кошкодевочка",
        "soldiers": NEKO, "genders": [0, 1],
        "f0": (180, 500),
        "design": "молодая девушка, мягкий женский голос выше среднего, ленивый и мурлыкающий, игриво и чуть свысока",
        "ref_text": "Мрр... Человек, ты опять забыл насыпать мне корм. Я подумаю, стоит ли тебя прощать. Мяу.",
        "lines": {
            "ru": {
                "select": ["Мур?", "Мяу. Слушаю.", "Чего тебе, человек?", "Мрр, да?", "Кошка на месте."],
                "move": ["Крадусь...", "Мяу, иду.", "Лапками, лапками.", "Ладно уж.", "Тихо, как мышь. То есть кошка."],
                "weapon": ["Когти наготове.", "Мрр, игрушка!", "Охота началась.", "Сейчас поймаю.", "Шшш!"],
                "annoyed": ["Не гладь против шерсти!", "Мяу! Отстань!", "Сейчас поцарапаю!", "Где мой корм?", "Фыр!"],
            },
            "en": {
                "select": ["Mrr?", "Meow. Listening.", "What do you want, human?", "Purr, yes?", "Kitty's here."],
                "move": ["Sneaking...", "Meow, going.", "Paws, paws, paws.", "Fine, whatever.", "Quiet as a mouse. I mean, a cat."],
                "weapon": ["Claws out.", "Ooh, a toy!", "The hunt begins.", "Gonna catch it.", "Hiss!"],
                "annoyed": ["Not against the fur!", "Meow! Go away!", "I will scratch you!", "Where's my food?", "Pfft!"],
            },
        },
    },
    "killbot": {
        "title": "Киллбот",
        "soldiers": ["STR_SOLDIER_KILLBOT"], "genders": [0, 1],
        "robot": True,     # после синтеза - металлический фильтр (build_test_mods.py)
        "design": "ровный механический голос без эмоций, монотонно и чётко, как автоответчик",
        "ref_text": "Внимание. Система наведения активна. Все органические формы жизни будут внесены в список.",
        "lines": {
            "ru": {
                "select": ["Юнит на связи.", "Жду команд, мешок с мясом.", "Бип. Слушаю.", "Система активна.", "Протокол вежливости загружен."],
                "move": ["Выполняю.", "Перемещение.", "Маршрут рассчитан.", "Бип-буп, иду.", "Шагаю. Скрип-скрип."],
                "weapon": ["Оружие активно.", "Цель: всё живое.", "Протокол уничтожения.", "Калибровка. Готово.", "Бип. Бабах."],
                "annoyed": ["Ошибка: слишком много кликов.", "Перегрев терпения.", "Прекратите. Тыкать. В робота.", "Вношу вас в список.", "Бип. Бип. БИП!"],
            },
            "en": {
                "select": ["Unit online.", "Awaiting orders, meatbag.", "Beep. Listening.", "System active.", "Politeness protocol loaded."],
                "move": ["Executing.", "Relocating.", "Route calculated.", "Beep boop, moving.", "Walking. Squeak squeak."],
                "weapon": ["Weapon hot.", "Target: all organics.", "Extermination protocol.", "Calibrating. Done.", "Beep. Boom."],
                "annoyed": ["Error: too many clicks.", "Patience overheating.", "Stop. Poking. The robot.", "Adding you to the list.", "Beep. Beep. BEEP!"],
            },
        },
    },
}

# Собаки не говорят ни на каком языке - их набор общий для обоих модов голосов и
# делается моделью эффектов (gen_steps_test.py), а не речью.
DOGE = {
    "title": "Доги",
    "soldiers": ["STR_SOLDIER_DOGE", "STR_SOLDIER_BLOODOGE"], "genders": [0, 1],
    "sfx": {
        "select": ["a single happy dog bark", "a short friendly dog woof", "a curious dog huff and one bark"],
        "move": ["an excited dog panting", "an eager dog yip"],
        "weapon": ["an aggressive dog growl", "a fierce dog snarl and bark"],
        "annoyed": ["a sad dog whine", "an annoyed dog grumble"],
    },
}
DOGE_CANDIDATES = 4
DOGE_MAX_S = 1.3
SFX_TAIL = ", close, dry, isolated sound effect, no music"

VOICE_TAKES = 2          # дублей на реплику, лучший по распознаванию - в мод
VOICE_MAX_S = 2.2        # реплика занимает канал 4 и глушит следующие (AUDIO_ROADMAP.md)
DESIGN_TAKES = 3         # кандидатов голоса по описанию
# Порог высоты голоса (медиана F0, поле "f0" голоса): опорный и реплика вне полосы в мод не идут -
# отбор только по распознаванию дал мужские голоса на месте женских (15.10).
DESIGN_TAKES_MAX = 10    # кандидатов голоса, пока в полосе не наберётся DESIGN_TAKES
VOICE_TAKES_MAX = 6      # дублей реплики, пока в полосе не наберётся VOICE_TAKES

# Частота реплик в процентах: выбор, начало хода, выбор оружия, «отстань».
# В движке по умолчанию 100/100/100/20 - на длинном ходе надоедает.
RESPONSE_FREQUENCY = [70, 35, 50, 20]
