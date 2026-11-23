"""Задания пробного прогона моделей эффектов (этап 0, docs/AUDIO_ROADMAP.md).

Один список на все модели: сравнивать можно только ответы на одно и то же задание.
(имя, длительность в секундах, промпт).

Длительность не на глаз, а от звука, который игра играет на этом событии сейчас
(перепись tools/sound_census.py -> census/sounds.tsv): самый длинный из эталонов REFS,
округлённый вверх до 0.1 с, плюс 0.3 с запаса на хвост. Первая проба шла с длинами 2-4 с
на глаз - в 2-5 раз длиннее, чем звучит игра (шаг в игре 0.3 с, а заказано было 2).
"""
TASKS = [
    ("step_metal", 0.8, "a single heavy boot footstep on a metal deck floor, close, dry, no music"),
    ("pistol", 0.8, "a single pistol gunshot, close, punchy, short tail, no music"),
    ("laser_rifle", 1.3, "a single sci-fi laser rifle shot, electric zap, short, no music"),
    ("knife_hit", 0.9, "a knife slash hitting flesh, wet impact, short, no music"),
    ("grenade", 2.2, "a hand grenade explosion outdoors, loud blast with debris, no music"),
    ("alien_roar", 1.6, "a monstrous alien creature roar, guttural and wet, no music"),
    ("scream_female", 2.4, "a woman screaming in pain as she dies, short, no music, no speech"),
    ("ricochet", 1.6, "a bullet missing and ricocheting off concrete, whizz and ping, no music"),
    ("reload", 1.0, "a rifle magazine being removed and a new one inserted, metallic clicks, no music"),
    ("door_slide", 1.5, "a heavy metal sliding door opening with a hydraulic hiss, no music"),
]
NEGATIVE = "music, speech, talking, singing, background noise, hum"
SEED_BASE = 1000

# эталоны в игре: (набор, номер в census/sounds.tsv, откуда взят)
REFS = {
    "step_metal": [("BATTLE.CAT", 24, "шаг по металлу, фаза 1"), ("BATTLE.CAT", 25, "шаг по металлу, фаза 2")],
    "pistol": [("BATTLE.CAT", 83, "PistolFire2: старый пистолет, MP")],
    "laser_rifle": [("BATTLE.CAT", 11, "лазерная винтовка")],
    "knife_hit": [("BATTLE.CAT", 75, "StabHit: ножи")],
    "grenade": [("BATTLE.CAT", 5, "большой взрыв (largeExplosion)")],
    "alien_roar": [("BATTLE.CAT", 130, "агро зомби")],
    "scream_female": [("BATTLE.CAT", 191, "смерть наёмницы"), ("BATTLE.CAT", 193, "смерть наёмницы")],
    # отдельного звука промаха у стрельбы нет: мимо играет тот же hitSound (ExplosionBState)
    "ricochet": [("BATTLE.CAT", 22, "попадание пули - его же игра играет и на промахе")],
    "reload": [("BATTLE.CAT", 17, "перезарядка (itemReload)"), ("BATTLE.CAT", 535, "Reload_Energy")],
    "door_slide": [("BATTLE.CAT", 20, "раздвижная дверь")],
}
