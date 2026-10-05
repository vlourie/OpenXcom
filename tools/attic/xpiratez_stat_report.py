# -*- coding: utf-8 -*-
"""Собирает docs/research/xpiratez-stat-caps.md: таблицы считаются из рулсетов, текст рядом.

Запуск из корня репозитория:
    py -3 tools\\xpiratez_stat_report.py [каталог-кэша]
Разбор рулсетов идёт около минуты; если задан каталог кэша, разобранное кладётся
в <каталог>\\pz.pkl и в следующий раз читается оттуда.
"""
import pickle, os, sys, time, collections, yaml

RULESET = os.path.join("Пиратки", "Dioxine_XPiratez", "user", "mods", "Piratez", "Ruleset")


def load_rulesets(cache_dir):
    """Рулсеты Пираток целиком: якоря yaml разворачиваются, поэтому только CSafeLoader."""
    cache = os.path.join(cache_dir, "pz.pkl") if cache_dir else None
    if cache and os.path.exists(cache):
        return pickle.load(open(cache, "rb"))
    data = {}
    for fn in sorted(os.listdir(RULESET)):
        if not fn.lower().endswith(".rul"):
            continue
        t0 = time.time()
        with open(os.path.join(RULESET, fn), encoding="utf-8", errors="replace") as f:
            try:
                d = yaml.load(f, Loader=yaml.CSafeLoader)
            except Exception as e:
                print("  !", fn, type(e).__name__, str(e)[:120])
                continue
        data[fn] = d
        print("  %-28s %5.1f с" % (fn, time.time() - t0))
    if cache:
        pickle.dump(data, open(cache, "wb"))
    return data


D = load_rulesets(sys.argv[1] if len(sys.argv) > 1 else None)
sol = D["Piratez.rul"]["soldiers"]
solById = {s["type"]: s for s in sol}
tr = D["Piratez_Transformations.rul"]["soldierTransformation"]
bon = {b["name"]: b for b in D["Piratez_Bonuses.rul"]["soldierBonuses"]}
com = D["Piratez_Globals.rul"]["commendations"]
arm = []
for fn in ("Piratez.rul", "Piratez_Armors.rul", "Yankes_Scripts.rul"):
    arm += [a for a in (D[fn].get("armors") or []) if a.get("stats")]
armAll = sum(len(D[fn].get("armors") or []) for fn in ("Piratez.rul", "Piratez_Armors.rul", "Yankes_Scripts.rul"))

ST = ["tu","stamina","health","bravery","reactions","firing","throwing","strength","melee","psiStrength","psiSkill","mana"]
RU = ["ОВ","Вын","Здр","Хра","Реа","Стр","Мет","Сил","Рук","ПсС","Пси","Ман"]
PRIMARY = {"reactions","firing","throwing","melee","psiSkill","psiStrength"}


LANG = os.path.join("Пиратки", "Dioxine_XPiratez", "user", "mods", "Piratez", "Language", "ru.yml")
NAMES = {}
import io, re
for line in io.open(LANG, encoding="utf-8-sig", errors="replace"):
    m = re.match(r'\s*(STR_SOLDIER(?:_[A-Z_]+)?): "(.+)"\s*$', line)
    if m:
        NAMES.setdefault(m.group(1), m.group(2))


def short(t):
    n = NAMES.get(t)
    if n:
        return n
    return t.replace("STR_SOLDIER_", "").replace("STR_SOLDIER", "ГАЛ")


def trow(name, d, fmt="%s"):
    return "| " + name + " | " + " | ".join(fmt % (d.get(k, 0) if d else 0) for k in ST) + " |"


def head(first):
    return ("| " + first + " | " + " | ".join(RU) + " |\n|" + "---|" * (len(ST) + 1))


L = []
w = L.append

w("# Потолок раскачки бойца в X-Piratez")
w("")
w("Отчёт по вопросу «до какого уровня вообще можно докачать персонажа и чем это ограничено».")
w("Числа посчитаны скриптом прямо из рулсетов установки")
w("(`Пиратки/Dioxine_XPiratez/user/mods/Piratez/Ruleset/*.rul`, мод `v.o1.1.1`) и сверены с кодом")
w("движка в `src/`.")
w("")
w("## Короткий ответ")
w("")
w("У бойца две разные величины, и путать их нельзя:")
w("")
w("1. **База** (`currentStats` в сейве) — то, что растёт от боёв, спортзала и псилаборатории.")
w("   Она жёстко упирается в `statCaps` своего типа и выше не идёт (перелёт максимум 1–5 единиц).")
w("   У базовой гал («Псих», `STR_SOLDIER`) это 100 ОВ, 150 выносливости, 90 здоровья, 120 стрельбы,")
w("   130 рукопашной, 80 силы, 63 псисилы, 40 пси, 70 маны.")
w("2. **Надбавки** — постоянные бонусы от трансформаций и наград плюс статы брони. Складываются")
w("   поверх базы и **потолком не ограничены вообще**: ни `statCaps`, ни `maxStats` к ним не применяются.")
w("")
w("Отсюда главный вывод для баланса: **потолок задаёт не `statCaps`, а сумма надбавок.**")
w("У полностью увешанной наградами гал надбавки дают больше, чем вся её база.")
w("")

w("## Пять источников роста и что каждый ограничивает")
w("")
w("| Источник | Что растёт | Предел | Можно ли пробить |")
w("|---|---|---|---|")
w("| Боевой опыт (`BattleUnit::postMissionProcedures`, `src/Savegame/BattleUnit.cpp:4200`) | стрельба, рукопашная, реакции, метание, пси, храбрость + вторичные ОВ/здоровье/сила/выносливость | `statCaps` | перелёт: первичные до `cap+5`, вторичные до `cap+1`, храбрость до `cap+9` |")
w("| Спортзал (`Soldier::trainPhys`, `src/Savegame/Soldier.cpp:1578`) | ОВ, выносливость, здоровье, сила, стрельба, метание, рукопашная | `trainingStatCaps` вероятностно, жёстко `statCaps` | нет, условие строго `< statCaps` |")
w("| Псилаборатория (`Soldier::trainPsi`, `:1364`; `trainPsi1Day`, `:1398`) | пси-навык, псисила | `statCaps` | нет, срезается через `std::min` |")
w("| Трансформации (`Soldier::calculateStatChanges`, `:1994`) | любой стат: плоско, процентом от текущего, процентом от нажитого | `upperBoundAtStatCaps` / `upperBoundAtMaxStats`, если заданы | да, если границы не заданы — в Пиратках это одна трансформация из 83 |")
w("| Надбавки (`Soldier::prepareStatsWithBonuses`, `:2154`) | всё | **нет предела** | — |")
w("")
w("Формула прироста от боя (`BattleUnit::improveStat`, `:4309`): опыт больше 10 даёт +2…6,")
w("больше 5 даёт +1…4, больше 2 даёт +1…3, больше 0 даёт +0…1. Условие проверяется **до** прибавки")
w("(`stats->firing < caps.firing`), поэтому боец на единицу ниже капа за один бой уходит на пять выше —")
w("это и есть весь легальный перелёт базы.")
w("")
w("Вторичные статы растут иначе: `v = cap - текущий`, прибавка `RNG(0, v/10 + 2)`")
w("(выносливость `v/15 + 2`), и только если в бою был хоть какой-то опыт. Отсюда знакомая кривая:")
w("первые двадцать боёв ОВ летят вверх, у самого капа ползут по единице.")
w("")
w("Храбрость растёт особняком: не через `improveStat`, а скачком на 10 с вероятностью")
w("`exp.bravery > RNG(0,10)`. Отсюда и самый большой перелёт — до `cap+9`.")
w("")
w("Мана в Пиратках включена и объявлена **и первичной, и вторичной** (`mana:` в")
w("`Piratez_Globals.rul`: `trainingPrimary: true`, `trainingSecondary: true`), то есть растёт дважды")
w("за бой — и от собственного опыта, и как вторичный стат. `replenishAfterMission: false`:")
w("потраченная мана остаётся потраченной и лечится временем.")
w("")
w("Спортзал считает по-своему, и для баланса это важно: прибавка идёт, если")
w("`RNG(0, trainingStatCaps.X) > текущий`. То есть `trainingStatCaps` — не жёсткий предел, а точка,")
w("где вероятность прироста падает до нуля. Жёсткий предел и здесь `statCaps`.")
w("")

w("## Потолок базы по всем %d типам бойцов (`statCaps`)" % len(sol))
w("")
w("Имена типов взяты из `Piratez/Language/ru.yml`, порядок — как в `Piratez.rul`.")
w("")
w(head("тип"))
for s in sol:
    w(trow(short(s["type"]), s.get("statCaps"), "%d"))
w("")
w("Ноль означает, что стат у типа выключен: синты и киллботы без пси, доги без стрельбы.")
w("")

w("## Потолок спортзала (`trainingStatCaps`)")
w("")
w("Зал тренирует только семь статов: ОВ, выносливость, здоровье, силу, стрельбу, метание,")
w("рукопашную (`Soldier::trainPhys`). Реакции и храбрость в зале не растут вовсе — эти столбцы")
w("движок не читает.")
w("")
w("Столбец **Пси здесь — не потолок, а пропуск в псилабораторию**: при")
w("`trainingStatCaps.psiSkill <= 0` тип бойца вообще нельзя поставить на пси-обучение")
w("(`AllocatePsiTrainingState.cpp:333`, `GeoscapeState.cpp:4861`, `Soldier.cpp:1855`). Величина")
w("при этом не используется ни для чего — важен только знак.")
w("")
w("Скорость зала можно придушить глобально полем `customTrainingFactor` (проценты, применяется к")
w("каждой прибавке). Пиратки его не задают, значит действует умолчание 100.")
w("")
w(head("тип"))
for s in sol:
    tc = s.get("trainingStatCaps")
    if tc:
        w(trow(short(s["type"]), tc, "%d"))
w("")
w("Типы, которых нет в таблице (куклы, киллботы, ксенфорсеры, доги), в зале не тренируются.")
w("")
w("Мест в зале: " + ", ".join(
    "%s %d" % (f["type"].replace("STR_", "").replace("_", " ").lower(), f["trainingRooms"])
    for f in D["Piratez.rul"]["facilities"] if f.get("trainingRooms")) + ".")
w("")

w("## Стартовый разброс (`minStats`…`maxStats`)")
w("")
w("То, с чем боец приходит. Разница между стартом и капом и есть запас роста.")
w("")
w(head("тип"))
for s in sol:
    mn, mx = s.get("minStats") or {}, s.get("maxStats") or {}
    w("| " + short(s["type"]) + " | " + " | ".join("%s–%s" % (mn.get(k, 0), mx.get(k, 0)) for k in ST) + " |")
w("")

allowedCount = collections.Counter()
for t in tr:
    for a in (t.get("allowedSoldierTypes") or []):
        allowedCount[a] += 1
noBound = [t for t in tr if not (t.get("upperBoundAtStatCaps") or t.get("upperBoundAtMaxStats"))]
withBonus = [t for t in tr if t.get("soldierBonusType")]
withFlat = [t for t in tr if t.get("flatOverallStatChange")]
prod = [t for t in tr if t.get("producedSoldierType")]

w("## Трансформации: %d штук" % len(tr))
w("")
w("Файл `Piratez_Transformations.rul`. Из них:")
w("")
w("- **%d** выдают постоянный бонус (`soldierBonusType`) — именно они и пробивают потолок;" % len(withBonus))
w("- **%d** меняют базовые статы плоско (`flatOverallStatChange`);" % len(withFlat))
w("- **%d** ограничены `upperBoundAtStatCaps`, **%d** — `upperBoundAtMaxStats`;" % (
    sum(1 for t in tr if t.get("upperBoundAtStatCaps")), sum(1 for t in tr if t.get("upperBoundAtMaxStats"))))
w("- **%d** меняют тип бойца (%s);" % (len(prod), ", ".join(sorted({short(t["producedSoldierType"]) for t in prod}))))
w("- **%d** без верхней границы вообще." % len(noBound))
w("")
w("Из этих %d без границы плюсы к базе даёт ровно одна — `STR_REVOLUTIONARY_TRAINING`:" % len(noBound))
w("она одновременно срезает проценты от текущих статов (−25 % по большинству, −50 % по стрельбе,")
w("метанию, рукопашной, псисиле и мане) и добавляет случайную плоскую прибавку (стрельба +15…40,")
w("рукопашная +15…40, псисила +15…40, мана +15…35). На прокачанном бойце это понижение,")
w("на слабом подъём; выше капа выводит только тот стат, у которого кап мал. Остальные «без потолка»")
w("либо только выдают бонус, либо режут статы (оживления, перенос тела).")
w("")
w("Границы работают в двух режимах (`RuleSoldierTransformation::isSoftLimit`): мягком — прибавка")
w("подрезается до границы, но уже набранное выше границы не отнимается; жёстком — стат срезается")
w("до границы. По умолчанию режим выбирается сам: мягкий, если тип бойца не меняется.")
w("")
w("Доступность по типам (сколько трансформаций открыто типу):")
w("")
w("| тип | трансформаций |")
w("|---|---|")
for t, c in allowedCount.most_common():
    w("| %s | %d |" % (short(t), c))
w("")
w("Пороги входа (`requiredMinStats`) — то, ради чего статы качают прицельно:")
w("")
w("| трансформация | требует |")
w("|---|---|")
for t in tr:
    r = t.get("requiredMinStats")
    if r:
        w("| %s | %s |" % (t["name"].replace("STR_", ""), ", ".join("%s %d" % (k, v) for k, v in r.items())))
w("")

withStats = [b for b in bon.values() if b.get("stats")]
w("## Постоянные бонусы: %d определений" % len(bon))
w("")
w("Файл `Piratez_Bonuses.rul`, со статами из них — **%d**. Бонус прибавляется в" % len(withStats))
w("`Soldier::prepareStatsWithBonuses` обычным сложением и **не проверяется ни против какого потолка**.")
w("Источников у бонуса два: трансформация (`soldierBonusType`) и награда.")
w("")
w("Кроме статов бонус умеет: броню со всех сторон (`frontArmor`, `sideArmor`, `rearArmor`,")
w("`underArmor`), скорость лечения (`recovery`), тепловидение (`heatVision`), псизрение (`psiVision`),")
w("видимость в темноте (`visibilityAtDark`).")
w("")
w("Самые крупные бонусы:")
w("")
w("| бонус | статы |")
w("|---|---|")
for b in sorted(withStats, key=lambda b: -sum(v for v in b["stats"].values() if v > 0))[:15]:
    w("| %s | %s |" % (b["name"].replace("STR_", ""),
                       ", ".join("%s %+d" % (k, v) for k, v in b["stats"].items())))
w("")

withB = [c for c in com if c.get("soldierBonusTypes")]
lvl = collections.Counter(len(c["soldierBonusTypes"]) for c in withB)
medal = {k: 0 for k in ST}
medalNoNeko = {k: 0 for k in ST}
for c in withB:
    st = (bon.get(c["soldierBonusTypes"][-1]) or {}).get("stats") or {}
    for k, v in st.items():
        if k in medal:
            medal[k] += v
            if "NEKO" not in c["type"]:
                medalNoNeko[k] += v
w("## Награды: %d штук, из них с бонусом %d" % (len(com), len(withB)))
w("")
w("Раздел `commendations` в `Piratez_Globals.rul`. Ступеней у наград:")
w(", ".join("%d ступ. — %d наград" % (k, v) for k, v in sorted(lvl.items())) + ".")
w("Действует **только бонус достигнутой ступени**, ступени не складываются")
w("(`RuleCommendations::getSoldierBonus` берёт бонус по индексу уровня, а не сумму).")
w("Награды могут быть ограничены типом бойца (`isSupportedBy`), поэтому неко-классовые обычной гал")
w("не достаются.")
w("")
w("Если собрать все награды на высшую ступень, надбавка составит:")
w("")
w(head("источник"))
w(trow("все награды", medal, "%+d"))
w(trow("без неко-классов", medalNoNeko, "%+d"))
w("")
w("Это и есть главный перекос: **+%d ОВ от наград против потолка базы в %d ОВ** у гал." % (
    medalNoNeko["tu"], solById["STR_SOLDIER"]["statCaps"]["tu"]))
w("")

gal = [a for a in arm if "STR_SOLDIER" in (a.get("units") or [])]
galFoot = [a for a in gal if (a.get("size") or 1) < 2]
galBig = [a for a in gal if (a.get("size") or 1) >= 2]
w("## Броня: %d комплектов, со статами %d" % (armAll, len(arm)))
w("")
w("Статы брони прибавляются последними и тоже без потолка (`prepareStatsWithBonuses`, шаг 5).")
w("Лучшее, что доступно базовой гал пешком (из %d её пеших комплектов; транспорт `size: 2` вынесен" % len(galFoot))
w("отдельно):")
w("")
w("| стат | лучшая броня |")
w("|---|---|")
for k, ru in zip(ST, RU):
    best = sorted([a for a in galFoot if (a["stats"].get(k) or 0) > 0], key=lambda a: -a["stats"][k])[:2]
    if best:
        w("| %s | %s |" % (ru, ", ".join("%s %+d" % (b["type"].replace("STR_", "").replace("_UC", ""), b["stats"][k]) for b in best)))
w("")
w("Отдельная статья — транспортная броня `size: 2` (%d комплектов у гал). Она даёт сотни единиц" % len(galBig))
w("ОВ и выносливости и в сумму пешего бойца не входит, хотя складывается ровно так же:")
w("")
w("| броня | ОВ | Вын |")
w("|---|---|---|")
for a in sorted([a for a in galBig if not a["type"].startswith("STR_ACAR")],
                key=lambda a: -(a["stats"].get("tu") or 0)):
    w("| %s | %+d | %+d |" % (a["type"].replace("STR_", "").replace("_UC", ""),
                              a["stats"].get("tu", 0), a["stats"].get("stamina", 0)))
w("| боевые машины ACAR, %d варианта | +175 | +700 |" % sum(1 for a in galBig if a["type"].startswith("STR_ACAR")))
w("")

w("## Что добавляет скриптовый слой")
w("")
w("`Yankes_Scripts.rul`, хук `returnFromMissionUnit`:")
w("")
w("- **`YSCRIPT_EXTRA_SECONDARY_XP_GAINS`** — броня с тегом")
w("  `ARMOR_GAINS_EXTRA_SECONDARY_STATS_PERCENT` ускоряет рост вторичных статов после боя:")
w("  к текущему прибавляется случайная доля остатка до капа. Тег стоит у 38 комплектов:")
w("  5 % у шести, 10 % у четырнадцати, 15 % у четырёх, 20 % у четырнадцати (спортивная форма,")
w("  купальник, рабская роба, голые варианты). Ограничение капом в скрипте есть.")
w("- **`YSCRIPT_REGEN_FULL_AFTER_MISSION`** — полное восстановление после боя для помеченных типов.")
w("")
w("Ещё один хук, задающий темп раскачки, — `awardExperience`: он блокирует опыт за добивание уже")
w("оглушённого или подконтрольного врага (`xpBlockLevel`).")
w("")

TYPE = "STR_SOLDIER"
caps = solById[TYPE]["statCaps"]
allowed = [t for t in tr if TYPE in (t.get("allowedSoldierTypes") or [])]
names = {t["name"] for t in allowed}
forb = {t["name"]: set(t.get("forbiddenPreviousTransformations") or []) & names for t in allowed}


def bs(t):
    b = bon.get(t.get("soldierBonusType") or "")
    return dict(b.get("stats") or {}) if b else {}


def net(t):
    return sum(bs(t).values())


chosen = []
for t in sorted(allowed, key=lambda t: -net(t)):
    if net(t) <= 0:
        continue
    n = t["name"]
    if any(n in forb[c["name"]] or c["name"] in forb[n] for c in chosen):
        continue
    chosen.append(t)
T = {k: 0 for k in ST}
for t in chosen:
    for k, v in bs(t).items():
        if k in T:
            T[k] += v
over = {k: (5 if k in PRIMARY else 1) for k in ST}
best_armor = max(galFoot, key=lambda a: sum(v for k, v in a["stats"].items() if k in ST and v > 0))
A = {k: best_armor["stats"].get(k, 0) for k in ST}
total = {k: caps.get(k, 0) + over[k] + T[k] + medalNoNeko[k] + A[k] for k in ST}

w("## Сводка: потолок обычной гал (`STR_SOLDIER`)")
w("")
w("Совместимый набор трансформаций подобран жадно: %d штук из %d доступных, берутся только те, у" % (len(chosen), len(allowed)))
w("которых сумма изменений положительна, взаимоисключения по `forbiddenPreviousTransformations`")
w("учтены. Броня — пешая, с наибольшей суммой плюсов из доступных гал. Это оценка сверху: часть")
w("наград и трансформаций в одной карьере может оказаться недостижимой по сюжету.")
w("")
w(head("слагаемое"))
w(trow("потолок базы", caps, "%d"))
w(trow("перелёт роста", over, "%+d"))
w(trow("бонусы трансформаций", T, "%+d"))
w(trow("все награды", medalNoNeko, "%+d"))
w(trow("броня " + best_armor["type"].replace("STR_", "").replace("_UC", ""), A, "%+d"))
w(trow("**ИТОГО в бою**", total, "%d"))
w("")
w("Читать так: база даёт %d ОВ, всё остальное — ещё %d сверху. По стрельбе: %d базы против %d надбавок." % (
    caps["tu"], total["tu"] - caps["tu"], caps["firing"], total["firing"] - caps["firing"]))
w("")
w("Трансформации в наборе:")
w("")
for t in chosen:
    s = bs(t)
    w("- `%s` — %s" % (t["name"].replace("STR_", ""), ", ".join("%s %+d" % (k, v) for k, v in s.items())))
w("")

w("## Где крутить, если правим баланс")
w("")
w("По убыванию влияния на итог:")
w("")
w("1. **Бонусы наград** (`Piratez_Bonuses.rul`, %d определений с `MEDAL` в имени). Они дают больше," % sum(1 for b in bon if "MEDAL" in b))
w("   чем весь потолок базы, и приходят сами за настрел. Правка ступени 10 у десятка самых щедрых")
w("   медалей меняет баланс сильнее, чем любая правка `statCaps`.")
w("2. **Бонусы трансформаций** — разовый выбор игрока, но их набирается %d штук сразу. Ограничение" % len(chosen))
w("   только через `forbiddenPreviousTransformations`: кто не запрещён явно, тот складывается.")
w("3. **Статы брони** — %d комплектов со статами; транспортные дают сотни единиц ОВ и выносливости." % len(arm))
w("4. **`statCaps`** — влияет только на базу и на то, докуда доводит боевой рост. Самый безопасный")
w("   и самый слабый рычаг: опустив кап, надбавки ты не тронешь.")
w("5. **`trainingStatCaps`** — докуда доводит зал без единого боя. Сейчас у гал зал даёт стрельбу")
w("   до 85 при капе 120 и рукопашную до 100 при 130.")
w("")
w("Чего в рулсете **нет** и чем ограничить нельзя: общего потолка на сумму надбавок, ограничения на")
w("число надетых бонусов, потолка на итоговый стат в бою. Движок таких полей не читает —")
w("`prepareStatsWithBonuses` просто складывает. Нужен глобальный предел — это правка движка либо")
w("скрипт на `returnFromMissionUnit` / `createUnit`, который срежет лишнее.")
w("")
w("## Как проверять правку")
w("")
w("- **Ufopaedia → Stats for Nerds** печатает `statCaps` и `trainingStatCaps` типа прямо в игре")
w("  (`src/Ufopaedia/StatsForNerdsState.cpp:4083`) — быстрый способ убедиться, что рулсет перечитан.")
w("- В окне бойца база и база с бонусами показаны раздельно: расхождение и есть сумма надбавок.")
w("- Числа этого отчёта пересчитываются скриптом из рулсетов; руками их не переписывать.")
w("")
w("---")
w("")
w("Сверено с кодом: `src/Savegame/BattleUnit.cpp` (рост после боя), `src/Savegame/Soldier.cpp`")
w("(зал, псилаб, трансформации, бонусы), `src/Mod/RuleSoldier.cpp`,")
w("`src/Mod/RuleSoldierTransformation.cpp`, `src/Mod/RuleCommendations.cpp`, `src/Mod/RuleSoldierBonus.h`.")

out = os.path.join("docs", "research", "xpiratez-stat-caps.md")
open(out, "w", encoding="utf-8-sig", newline="\n").write("\n".join(L) + "\n")
print("записано:", out, len(L), "строк")
