#!/usr/bin/env python3
"""
Разбор рулсетов мода по содержимому: что в записях, как они ссылаются друг на друга,
что движок из написанного не прочтёт.

    py -3 tools/rul_map.py
    py -3 tools/rul_map.py --mod <папка мода> --master <папка мастер-мода> --out <папка>

tools/index_mod.py отвечает «где объявлено» (id -> файл:строка). Этот скрипт идёт дальше:
грузит ВСЕ рулсеты мастер-мода и мода в порядке движка, сливает записи так же, как
Mod::loadRule, и кладёт в <out>/:

    values.tsv        раздел | id | поле | значение (JSON) - итог после всех файлов
    entries.tsv       раздел | id | файл | строка | сколько раз правилась | где
    fields.tsv        раздел | поле | записей | знает ли движок | пример
    refs.tsv          раздел | id | путь поля | куда ссылается | id цели
    ref_schema.tsv    какое поле какого раздела на какой раздел указывает (выведено из данных)
    dangling.tsv      ссылка в поле-ссылке, а такой записи нет
    unknown_keys.tsv  ключ записи, которого движок не читает, - он молча пропадает
    dup_keys.tsv      повтор ключа в одном отображении: движок берёт ПЕРВЫЙ, PyYAML - последний
    overrides.tsv     поле задано в одном файле и перезаписано другим (кто победил)
    globals.tsv       ключи верхнего уровня, которые не списки записей
    RUL.md            сводка: разделы, цифры, дерево исследований, находки

Почему так, а не иначе (всё сверено с кодом, а не по памяти):
  * порядок файлов: Mod::loadMod сортирует рулсеты по полному пути ПО УБЫВАНИЮ
    (a.fullpath > b.fullpath), мастер-мод грузится раньше мода;
  * повтор ключа: YamlNodeReader::useIndex строит индекс через emplace, а findChildNode
    ищет с начала - в обоих случаях побеждает ПЕРВЫЙ ключ. PyYAML оставляет последний,
    поэтому значения здесь строятся из дерева узлов самим скриптом, а не yaml.load;
  * запись с type/name/id создаёт или дополняет, delete удаляет, new/override/update -
    как в Mod::loadRule; refNode читается раньше собственных полей записи.
Слияние полей повторной записи - поверхностное: поле верхнего уровня заменяется целиком.
Для большинства полей движка это так и есть; исключения (tags и подобные словари, которые
движок дописывает) помечены в RUL.md как ограничение.

Рулсеты читаются PyYAML с терпимостью к повторному якорю (грабли R-046).
"""
from __future__ import annotations

import argparse, json, re, sys, time
from collections import Counter, defaultdict
from pathlib import Path

import yaml
from yaml.events import AliasEvent
from yaml.nodes import MappingNode, ScalarNode, SequenceNode

ENC_W = "utf-8-sig"   # R-001: читает и PowerShell, и человек
ENC_R = "utf-8-sig"

ROOT = Path(__file__).resolve().parent.parent
DEF_MOD = ROOT / "Пиратки/Dioxine_XPiratez/user/mods/Piratez"
DEF_MASTER = ROOT / "Пиратки/Dioxine_XPiratez/standard/xcom1"
DEF_OUT = ROOT / ".index/mod/Piratez/rul"

# Разделы, которые Mod::loadFile читает через iterateRulesSpecific, - ключ записи свой.
SPECIFIC_KEY = {
    "ufopaedia": "id", "mapScripts": "type", "extraSprites": "type",
    "extraSounds": "type", "extraStrings": "type", "customPalettes": "type",
    "unitResponseSounds": "name", "cutscenes": "type", "musics": "type",
    "interfaces": "type", "globe": None,
}
# Эти разделы - не записи по id, а списки добавок: одинаковый type не сливается.
NO_MERGE = {"extraSprites", "extraSounds", "extraStrings", "musics"}
OPS = ("new", "override", "update", "delete")
# Запасной ключ id: ExtraSprites::load берёт typeSingle, если он есть.
ID_ALT = {"extraSprites": ("typeSingle",)}

# Значения, которые движок понимает сам, - это не ссылки на записи:
#   STR_NONE - «нет»; dummy в waves[].ufo - волна без НЛО (AlienMission::think, «Some missions
#   may not spawn a UFO»); globeTerrain - террейн по месту на глобусе (BattlescapeGenerator);
#   STR_SCIENTIST/STR_ENGINEER - персонал, не солдат; PAL_* - встроенные палитры движка.
SENTINELS = {"STR_NONE", "dummy", "globeTerrain", "STR_SCIENTIST", "STR_ENGINEER", ""}
SENTINEL_RE = re.compile(r"^PAL_[A-Z_]+$")
# Поле, чьё значение - ключ строки перевода, а не id записи, даже если совпало с id.
NAME_PATH = re.compile(r"(^|[.\[\]{}])(name|title|text|desc\w*|\w+Name|\w+Title|briefing\.\w+)$")
# Цели, которые движок принимает в поле помимо главной (RuleManufacture::afterLoad:
# в requiredItems допускаются корабли - getCraft(i.first, false)).
EXTRA_TARGETS = {("manufacture", "requiredItems{}"): {"crafts"}}
MIRRORS = {"ufopaedia", "research", "manufacture"}

# Помощники, которые читают ключи за класс записи (свои литералы у них, а не у класса).
HELPERS = ("Mod/RuleStatBonus", "Mod/RuleDamageType", "Mod/ModScript", "Engine/Script",
           "Engine/ScriptBind", "Engine/Yaml")
# Разделы, чьи поля читает не только класс записи: RuleUfo::load зовёт RuleCraftStats
# (объявлен в RuleCraft.h), команды mapScripts разбирает Mod::loadFile.
SECTION_HELPERS = {"ufos": ("Mod/RuleCraft",), "mapScripts": ("Mod/Mod",)}

# Приставки, из которых движок собирает имя ключа на ходу: RuleItem::loadCost ("tu" + name),
# loadFlat ("flat" + name), loadConfAction ("conf" + name), RuleItemUseCost ("cost" + name).
KEY_PREFIXES = ("tu", "cost", "flat", "conf")


class Tolerant(yaml.SafeLoader):
    """Повторный якорь, как у yaml-cpp/ryml; псевдоним не трогаем (R-046)."""

    def compose_node(self, parent, index):
        ev = self.peek_event()
        if (ev is not None and not isinstance(ev, AliasEvent)
                and getattr(ev, "anchor", None) and ev.anchor in self.anchors):
            del self.anchors[ev.anchor]
        return super().compose_node(parent, index)


def compose(path: Path):
    text = path.read_bytes()
    try:
        return yaml.compose(text, Loader=yaml.CSafeLoader)
    except yaml.YAMLError:
        return yaml.compose(text, Loader=Tolerant)


_SC = yaml.constructor.SafeConstructor()


def to_py(node, dups=None, where=""):
    """Узел -> значение. В отображении побеждает первый ключ, как у движка."""
    if isinstance(node, ScalarNode):
        try:
            return _SC.construct_object(node)
        except Exception:
            return node.value
    if isinstance(node, SequenceNode):
        return [to_py(n, dups, where) for n in node.value]
    if isinstance(node, MappingNode):
        out = {}
        for k, v in node.value:
            key = to_py(k)
            if isinstance(key, (list, dict)):
                key = json.dumps(key, ensure_ascii=False)
            if key in out:
                if dups is not None:
                    dups.append((where, str(key), k.start_mark.line + 1,
                                 out[key], to_py(v)))
                continue
            out[key] = to_py(v, dups, where)
        return out
    return None


def map_get(node: MappingNode, key: str):
    """Первый узел значения по ключу - как findChildNode."""
    for k, v in node.value:
        if isinstance(k, ScalarNode) and k.value == key:
            return v
    return None


def rul_files(folder: Path):
    """Рулсеты папки в порядке Mod::loadMod: полный путь по убыванию."""
    files = [p for p in folder.rglob("*.rul")]
    return sorted(files, key=lambda p: str(p).replace("\\", "/"), reverse=True)


def section_keys(src: Path):
    """Раздел -> ключ id, как в iterateRules("<раздел>", "<ключ>") в Mod.cpp."""
    keys = dict(SPECIFIC_KEY)
    text = (src / "Mod/Mod.cpp").read_text(encoding="utf-8", errors="replace")
    for sec, k in re.findall(r'iterateRules\("(\w+)",\s*"(\w+)"\)', text):
        keys[sec] = k
    return keys


def engine_literals(src: Path):
    """Все строковые литералы движка, похожие на имя ключа рулсета."""
    lit = set()
    for p in src.rglob("*"):
        if p.suffix in (".cpp", ".h"):
            lit.update(re.findall(r'"([A-Za-z_][A-Za-z0-9_]*)"',
                                  p.read_text(encoding="utf-8", errors="replace")))
    return lit


def section_classes(src: Path):
    """Раздел -> класс правила: строка после iterateRules("<раздел>") в Mod::loadFile."""
    lines = (src / "Mod/Mod.cpp").read_text(encoding="utf-8", errors="replace").splitlines()
    out = {}
    for i, ln in enumerate(lines):
        m = re.search(r'iterateRules(?:Specific)?\("(\w+)"', ln)
        if not m:
            continue
        for nxt in lines[i + 1:i + 6]:
            c = re.search(r"\b([A-Z]\w+)\s*\*\s*\w+\s*=\s*(?:loadRule|new)\b", nxt) or \
                re.search(r"new\s+([A-Z]\w+)\(", nxt)
            if c:
                out.setdefault(m.group(1), c.group(1))
                break
    out.setdefault("ufopaedia", "ArticleDefinition")
    out.setdefault("mapScripts", "MapScript")
    return out


def class_literals(src: Path, cls: str, extra=()):
    """Литералы файлов класса и его помощников."""
    lit = set()
    stems = [f"Mod/{cls}", f"Ufopaedia/{cls}"] + list(HELPERS) + list(extra)
    for stem in stems:
        for ext in (".cpp", ".h"):
            p = src / (stem + ext)
            if p.is_file():
                lit.update(re.findall(r'"([A-Za-z_][A-Za-z0-9_]*)"',
                                      p.read_text(encoding="utf-8", errors="replace")))
    return lit


def is_sentinel(s: str) -> bool:
    return s in SENTINELS or bool(SENTINEL_RE.match(s))


def key_known(key: str, lit: set) -> bool:
    if key in lit:
        return True
    for pre in KEY_PREFIXES:
        if key.startswith(pre) and len(key) > len(pre) and key[len(pre)].isupper() \
                and key[len(pre):] in lit:
            return True
    return False


# ------------------------------------------------------------------ загрузка и слияние

class Store:
    def __init__(self):
        self.rules = {}            # (sec, id) -> {"fields": {}, "setby": {field: (file, line)}}
        self.defs = defaultdict(list)   # (sec, id) -> [(file, line, op)]
        self.deleted = defaultdict(list)
        self.lists = defaultdict(list)  # NO_MERGE: sec -> [(id, file, line, fields)]
        self.globals = []          # (file, key, line, summary)
        self.dups = []             # (file, where, key, line, взято движком, потеряно)
        self.dup_seen = set()
        self.overrides = []        # (sec, id, field, file_old, line_old, file_new, line_new, old, new)
        self.unmerged = []         # запись без ключа id
        self.load_errors = []


def flatten_entry(node: MappingNode, dups, where):
    """Поля записи: сперва refNode, поверх - свои (как RuleItem::load / Armor::load)."""
    fields = {}
    lines = {}
    ref = map_get(node, "refNode")
    if isinstance(ref, MappingNode):
        rf, rl = flatten_entry(ref, dups, where + ".refNode")
        fields.update(rf)
        lines.update(rl)
    own = to_py(node, dups, where)
    for k, v in own.items():
        if k != "refNode":
            fields[k] = v
    for kn, _ in node.value:
        if isinstance(kn, ScalarNode) and kn.value != "refNode":
            lines[kn.value] = kn.start_mark.line + 1
    return fields, lines


def load_file(st: Store, path: Path, rel: str, keys: dict):
    try:
        root = compose(path)
    except yaml.YAMLError as e:
        st.load_errors.append((rel, str(e).replace("\n", " ")))
        return
    if not isinstance(root, MappingNode):
        return
    seen_top = set()
    for kn, vn in root.value:
        sec = kn.value
        if sec in seen_top:
            st.dups.append((rel, "<верхний уровень>", sec, kn.start_mark.line + 1, "", "весь раздел"))
            continue            # движок читает только первый раздел с этим именем
        seen_top.add(sec)
        idkey = keys.get(sec, "__none__")
        # список без ключа записи (constants: [- damageRange: 100, ...]) - это настройки
        if idkey == "__none__" and isinstance(vn, SequenceNode) and not any(
                isinstance(x, MappingNode) and map_get(x, "type") is not None for x in vn.value[:5]):
            idkey = None
        if not isinstance(vn, SequenceNode) or idkey is None:
            summ = to_py(vn)
            s = json.dumps(summ, ensure_ascii=False, default=str)
            st.globals.append((rel, sec, kn.start_mark.line + 1, s if len(s) < 300 else s[:297] + "..."))
            continue
        if idkey == "__none__":
            idkey = "type"
        for en in vn.value:
            if not isinstance(en, MappingNode):
                continue
            line = en.start_mark.line + 1
            op, rid = None, None
            for cand in (idkey,) + ID_ALT.get(sec, ()) + OPS:
                n = map_get(en, cand)
                if isinstance(n, ScalarNode):
                    op, rid = cand, n.value
                    break
            if rid is None:
                st.unmerged.append((sec, rel, line))
                continue
            dups = []
            fields, lines = flatten_entry(en, dups, f"{sec}:{rid}")
            for where, k, ln, kept, lost in dups:
                # один узел под якорем входит в несколько записей - считаем его один раз
                if (rel, ln, k) not in st.dup_seen:
                    st.dup_seen.add((rel, ln, k))
                    st.dups.append((rel, where, k, ln, jdump(kept)[:80],
                                    "= то же" if kept == lost else jdump(lost)[:80]))
            for k in (idkey,) + ID_ALT.get(sec, ()) + OPS:
                fields.pop(k, None)
            key = (sec, rid)
            if sec in NO_MERGE:
                st.lists[sec].append((rid, rel, line, fields))
                st.defs[key].append((rel, line, op))
                continue
            if op == "delete":
                if key in st.rules:
                    del st.rules[key]
                st.deleted[key].append((rel, line))
                st.defs[key].append((rel, line, op))
                continue
            exists = key in st.rules
            if op == "new" and exists:
                continue
            if op in ("override", "update") and not exists:
                st.defs[key].append((rel, line, op + " (нет записи)"))
                continue
            rec = st.rules.setdefault(key, {"fields": {}, "setby": {}})
            for f, v in fields.items():
                if f in rec["fields"] and rec["fields"][f] != v:
                    of, ol = rec["setby"][f]
                    st.overrides.append((sec, rid, f, of, ol, rel, lines.get(f, line),
                                         rec["fields"][f], v))
                rec["fields"][f] = v
                rec["setby"][f] = (rel, lines.get(f, line))
            st.defs[key].append((rel, line, op))


# ------------------------------------------------------------------ ссылки

FIELD_NAME = re.compile(r"^[a-z][A-Za-z0-9]*$")


def walk_strings(val, path):
    """(путь, строка) для всех строк значения. Ключ словаря - путь{}; под ключом-именем
    поля путь продолжается .имя, под ключом-данными (STR_..., числа) - {}."""
    if isinstance(val, str):
        yield path, val
    elif isinstance(val, list):
        for x in val:
            yield from walk_strings(x, path + "[]")
    elif isinstance(val, dict):
        for k, v in val.items():
            ks = str(k)
            if FIELD_NAME.match(ks):
                yield from walk_strings(v, path + "." + ks)
            else:
                if isinstance(k, str):
                    yield path + "{}", k
                yield from walk_strings(v, path + "{}.")


def build_refs(st: Store):
    ids = defaultdict(set)   # id -> разделы
    for (sec, rid) in st.rules:
        ids[rid].add(sec)
    for (sec, rid) in st.deleted:
        ids.setdefault(rid, set())
    stats = defaultdict(Counter)   # (sec, path) -> Counter(раздел-цель)
    occ = []                        # (sec, rid, path, value)
    for (sec, rid), rec in st.rules.items():
        for f, v in rec["fields"].items():
            for path, s in walk_strings(v, f):
                if NAME_PATH.search(path) or is_sentinel(s):
                    continue
                occ.append((sec, rid, path, s))
                for t in ids.get(s, ()):
                    stats[(sec, path)][t] += 1
                stats[(sec, path)]["__total__"] += 1
    # Поле - ссылка, если 60 и больше процентов его строк находятся в одном разделе.
    # Цели поля - все разделы, куда попало от 5 процентов: waves[].ufo бывает и НЛО,
    # и развёртыванием, requiredItems - и предметом, и кораблём.
    schema = {}
    for (sec, path), c in stats.items():
        tot = c.pop("__total__")
        if not c:
            continue
        tgt, n = c.most_common(1)[0]
        # Педия, исследования и производство повторяют имена почти всего остального: статья
        # STR_X есть у брони STR_X. Если «настоящий» раздел покрывает поле не хуже порога,
        # главной целью берём его, а не зеркало.
        real = [(k, t) for t, k in c.items() if t not in MIRRORS and k >= 0.6 * tot]
        if tgt in MIRRORS and real:
            n, tgt = max(real)
        share = n / tot
        if share >= 0.6 and n >= 3 or (share == 1.0 and n >= 1):
            schema[(sec, path)] = [tgt, n, tot, share, {tgt} | EXTRA_TARGETS.get((sec, path), set())]
    # Вторая цель - только по строкам, которых НЕТ в главной: одно имя живёт сразу в items,
    # research и ufopaedia, и простой подсчёт записал бы в цели все три.
    extra = defaultdict(Counter)
    for sec, rid, path, s in occ:
        sch = schema.get((sec, path))
        if sch and (sch[0], s) not in st.rules:
            for t in ids.get(s, ()):
                extra[(sec, path)][t] += 1
    for key, c in extra.items():
        sch = schema[key]
        for t, k in c.items():
            if k >= 0.05 * sch[2] and k >= 2:
                sch[4].add(t)
    refs, dangling = [], []
    for sec, rid, path, s in occ:
        sch = schema.get((sec, path))
        if not sch:
            continue
        hit = [t for t in sorted(sch[4]) if (t, s) in st.rules]
        if hit:
            for t in hit:
                refs.append((sec, rid, path, t, s))
        elif sch[3] >= 0.6 and sch[1] >= 3:
            gone = [t for t in sch[4] if (t, s) in st.deleted]
            why = "удалена" if gone else "нет такой"
            other = ",".join(sorted(ids.get(s, ())))
            dangling.append((sec, rid, path, "|".join(sorted(sch[4])), s, why, other))
    return schema, refs, dangling


# ------------------------------------------------------------------ дерево исследований

GRANT_FIELDS = re.compile(r"^(unlocks|getOneFree|getOneFreeProtected|disables|reenables)")
NOT_GRANT = re.compile(r"(?i)(requires|required|dependencies|needItem|lookup)")


def research_cycles(res, deps, refs):
    """Циклы в dependencies (сильные компоненты Тарьяна) и чем в них входят.

    SavedGame::getAvailableResearchProjects: тема из чьего-то unlocks берётся БЕЗ проверки
    dependencies - так моды и делают «тему только через открытие». Цикл без такого входа
    (и без выдачи из другого раздела: событие, миссия, трансформация) не откроется никогда.
    """
    index, low, stack, on, comps = {}, {}, [], set(), []
    cnt = [0]

    def strong(v):
        index[v] = low[v] = cnt[0]
        cnt[0] += 1
        stack.append(v)
        on.add(v)
        for w in deps[v]:
            if w not in index:
                strong(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                on.discard(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1 or v in deps[v]:
                comps.append(sorted(comp))

    for r in res:
        if r not in index:
            strong(r)
    grants = defaultdict(list)
    for sec, rid, path, tgt, tid in refs:
        if tgt != "research":
            continue
        if sec == "research" and GRANT_FIELDS.match(path):
            grants[tid].append(f"research:{rid}.{path.split('[')[0].split('{')[0]}")
        elif sec != "research" and not NOT_GRANT.search(path):
            grants[tid].append(f"{sec}:{rid}.{path}")
    out = []
    for comp in comps:
        entry = {m: grants[m][:3] for m in comp if grants.get(m)}
        out.append((comp, entry))
    return out


def research_stats(st: Store, refs):
    res = {rid: rec["fields"] for (sec, rid), rec in st.rules.items() if sec == "research"}
    deps = {r: [d for d in (f.get("dependencies") or []) if d in res] for r, f in res.items()}
    memo, onstack = {}, set()

    sys.setrecursionlimit(20000)
    cycles = research_cycles(res, deps, refs)

    def depth(r):
        if r in memo:
            return memo[r]
        if r in onstack:
            return 0
        onstack.add(r)
        d = 1 + max((depth(x) for x in deps[r]), default=0)
        onstack.discard(r)
        memo[r] = d
        return d

    for r in res:
        depth(r)
    deepest = sorted(memo.items(), key=lambda x: -x[1])[:10]
    # цепочка самого глубокого
    chain = []
    if deepest:
        cur = deepest[0][0]
        while cur:
            chain.append(cur)
            nxt = [x for x in deps[cur] if memo.get(x) == memo[cur] - 1]
            cur = nxt[0] if nxt else None
    roots = [r for r, f in res.items() if not f.get("dependencies") and not f.get("requires")]
    cost = [f.get("cost", 0) or 0 for f in res.values()]
    return {
        "count": len(res),
        "roots": len(roots),
        "needItem": sum(1 for f in res.values() if f.get("needItem")),
        "zero_cost": sum(1 for c in cost if not c),
        "cost_sum": sum(c for c in cost if isinstance(c, (int, float))),
        "max_depth": deepest[0][1] if deepest else 0,
        "deepest": deepest,
        "chain": chain,
        "cycles": cycles,
        "with_getOneFree": sum(1 for f in res.values() if f.get("getOneFree")),
        "with_unlocks": sum(1 for f in res.values() if f.get("unlocks")),
    }


# ------------------------------------------------------------------ вывод

def jdump(v):
    return json.dumps(v, ensure_ascii=False, default=str, separators=(",", ":"))


def tsv(path: Path, header, rows):
    with open(path, "w", encoding=ENC_W, newline="\n") as f:
        f.write("\t".join(header) + "\n")
        for r in rows:
            f.write("\t".join(str(x).replace("\t", " ").replace("\n", " ") for x in r) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--mod", type=Path, default=DEF_MOD)
    ap.add_argument("--master", default=str(DEF_MASTER),
                    help="мастер-мод (для Пираток - standard/xcom1); '' - без него")
    ap.add_argument("--src", type=Path, default=ROOT / "src", help="исходники движка")
    ap.add_argument("--out", type=Path, default=DEF_OUT)
    a = ap.parse_args()
    t0 = time.time()
    a.out.mkdir(parents=True, exist_ok=True)
    keys = section_keys(a.src)
    lit = engine_literals(a.src)

    order = []
    # Path("") - это ".", и без этой проверки грузились бы все рулсеты текущей папки
    a.master = Path(a.master) if a.master else None
    if a.master and a.master.is_dir():
        order += [(p, "master:" + str(p.relative_to(a.master)).replace("\\", "/"))
                  for p in rul_files(a.master)]
    rdir = a.mod / "Ruleset" if (a.mod / "Ruleset").is_dir() else a.mod
    order += [(p, str(p.relative_to(a.mod)).replace("\\", "/")) for p in rul_files(rdir)]

    st = Store()
    for p, rel in order:
        t = time.time()
        load_file(st, p, rel, keys)
        print(f"  {rel}: {time.time() - t:.1f} с", flush=True)

    mod_files = {rel for _, rel in order if not rel.startswith("master:")}

    # entries.tsv / values.tsv
    ent_rows, val_rows = [], []
    for (sec, rid), rec in sorted(st.rules.items()):
        d = st.defs[(sec, rid)]
        first = d[0]
        ent_rows.append((sec, rid, first[0], first[1], len(d) - 1,
                         ";".join(f"{f}:{l}" for f, l, _ in d[1:]),
                         ",".join(rec["fields"].keys())))
        for f, v in rec["fields"].items():
            val_rows.append((sec, rid, f, jdump(v)))
    for sec, lst in st.lists.items():
        for rid, rel, line, fields in lst:
            ent_rows.append((sec, rid, rel, line, 0, "", ",".join(fields.keys())))
    tsv(a.out / "entries.tsv",
        ["section", "id", "file", "line", "updates", "updated_at", "fields"], ent_rows)
    tsv(a.out / "values.tsv", ["section", "id", "field", "value"], val_rows)

    # fields.tsv / unknown_keys.tsv
    # Два уровня: ключа нет среди литералов движка ВООБЩЕ - точно пропадает; ключ есть,
    # но не в классе раздела и не в его помощниках - вероятно, поле другого раздела.
    classes = section_classes(a.src)
    clit = {sec: class_literals(a.src, cls, SECTION_HELPERS.get(sec, ()))
            for sec, cls in classes.items()}

    def verdict(sec, f):
        if not key_known(f, lit):
            return "НЕТ"
        if sec in clit and clit[sec] and not key_known(f, clit[sec]):
            return "не в классе " + classes[sec]
        return "да"

    fcount = defaultdict(Counter)
    fex = {}
    unknown = []
    for (sec, rid), rec in st.rules.items():
        for f, v in rec["fields"].items():
            fcount[sec][f] += 1
            fex.setdefault((sec, f), (rid, jdump(v)[:80]))
            vd = verdict(sec, str(f))
            if vd != "да":
                file, line = rec["setby"][f]
                unknown.append((sec, rid, f, vd, file, line, jdump(v)[:100]))
    for sec, lst in st.lists.items():
        for rid, rel, line, fields in lst:
            for f in fields:
                fcount[sec][f] += 1
    frows = []
    for sec in sorted(fcount):
        for f, n in fcount[sec].most_common():
            ex = fex.get((sec, f), ("", ""))
            frows.append((sec, f, n, verdict(sec, str(f)), ex[0], ex[1]))
    tsv(a.out / "fields.tsv", ["section", "field", "entries", "engine_reads", "example_id", "example"], frows)
    tsv(a.out / "unknown_keys.tsv", ["section", "id", "field", "verdict", "file", "line", "value"],
        sorted(unknown))
    top_unknown = sorted({(r[3], g) for r in st.globals for g in [r[1]] if not key_known(g, lit)})

    tsv(a.out / "dup_keys.tsv", ["file", "where", "key", "line", "engine_takes", "lost"], st.dups)
    tsv(a.out / "globals.tsv", ["file", "key", "line", "value"], st.globals)
    tsv(a.out / "overrides.tsv",
        ["section", "id", "field", "was_file", "was_line", "now_file", "now_line", "was", "now"],
        [(s, i, f, of, ol, nf, nl, jdump(ov)[:120], jdump(nv)[:120])
         for s, i, f, of, ol, nf, nl, ov, nv in st.overrides])

    schema, refs, dangling = build_refs(st)
    tsv(a.out / "ref_schema.tsv", ["section", "path", "target", "all_targets", "resolved", "strings", "share"],
        sorted(((s, p, t, "|".join(sorted(tg)), n, tot, f"{sh:.2f}")
                for (s, p), (t, n, tot, sh, tg) in schema.items()),
               key=lambda r: (r[0], -r[4])))
    tsv(a.out / "refs.tsv", ["section", "id", "path", "target", "target_id"], sorted(refs))
    tsv(a.out / "dangling.tsv", ["section", "id", "path", "target", "missing_id", "why", "exists_in"],
        sorted(dangling))

    rs = research_stats(st, refs)
    tsv(a.out / "research_cycles.tsv", ["topics", "entries"],
        [(",".join(comp), "; ".join(f"{m} <- {', '.join(g)}" for m, g in entry.items()) or "НЕТ ВХОДА")
         for comp, entry in rs["cycles"]])

    # ------------------------------------------------------------ RUL.md
    by_sec = Counter(sec for sec, _ in st.rules)
    for sec, lst in st.lists.items():
        by_sec[sec] += len(lst)
    mod_origin = Counter()
    for (sec, rid) in st.rules:
        if st.defs[(sec, rid)][0][0] in mod_files:
            mod_origin[sec] += 1
    per_file = Counter()
    for key, d in st.defs.items():
        for f, _, _ in d:
            per_file[f] += 1
    ov_pairs = Counter((of, nf) for _, _, _, of, _, nf, _, _, _ in st.overrides)
    L = []
    w = L.append
    w(f"# Рулсеты мода: {a.mod.name}\n")
    w(f"Собрано: {time.strftime('%Y-%m-%d %H:%M')} за {time.time() - t0:.0f} с, "
      f"скриптом `tools/rul_map.py`. Разбор по СОДЕРЖИМОМУ; где что объявлено - "
      f"`.index/mod/{a.mod.name}/entries.tsv` (index_mod.py).\n")
    w("## Порядок загрузки\n")
    w("Как в `Mod::loadMod`: мастер-мод, затем мод; внутри - полный путь по убыванию. "
      "Кто позже, тот и прав в поле, которое задают оба.\n")
    w("| # | Файл | Записей и правок |\n|---|---|---|")
    for i, (_, rel) in enumerate(order, 1):
        w(f"| {i} | {rel} | {per_file.get(rel, 0)} |")
    w("")
    w("## Разделы после слияния\n")
    w("| Раздел | Записей | Из них заведены модом | Ключ id |\n|---|---|---|---|")
    for sec, n in by_sec.most_common():
        w(f"| {sec} | {n} | {mod_origin.get(sec, '')} | {keys.get(sec, 'type') or '-'} |")
    w("")
    w("## Находки\n")
    w(f"* ошибок разбора YAML: {len(st.load_errors)}")
    for rel, e in st.load_errors:
        w(f"  * {rel}: {e[:200]}")
    hard = [r for r in unknown if r[3] == "НЕТ"]
    soft = [r for r in unknown if r[3] != "НЕТ"]
    w(f"* ключей, которых движок не знает НИГДЕ (`unknown_keys.tsv`, verdict НЕТ): **{len(hard)}** "
      f"в {len({(r[0], r[2]) for r in hard})} разных именах - пропадают молча")
    for (sec, f), n in Counter((r[0], r[2]) for r in hard).most_common(40):
        w(f"  * `{sec}.{f}` - {n}")
    w(f"* ключей, которые движок знает, но не у этого раздела (verdict «не в классе»): "
      f"**{len(soft)}** в {len({(r[0], r[2]) for r in soft})} именах - проверять по коду класса")
    for (sec, f, vd), n in Counter((r[0], r[2], r[3]) for r in soft).most_common(40):
        w(f"  * `{sec}.{f}` - {n} ({vd})")
    if top_unknown:
        w(f"* ключи верхнего уровня, которых движок не знает: " +
          ", ".join(f"`{k}` ({f})" for f, k in top_unknown))
    w(f"* повторов ключа в одном отображении (`dup_keys.tsv`, движок берёт ПЕРВЫЙ): **{len(st.dups)}**")
    for rel, where, k, ln, kept, lost in st.dups[:30]:
        w(f"  * {rel}:{ln} `{where}` - `{k}`: взято {kept}, потеряно {lost}")
    w(f"* битых ссылок (`dangling.tsv`): **{len(dangling)}**")
    for (s, p, t), n in Counter((d[0], d[2], d[3]) for d in dangling).most_common(20):
        w(f"  * `{s}.{p}` -> {t}: {n}")
    w(f"* записей без ключа id (движок их пропустит): {len(st.unmerged)}")
    for sec, rel, ln in st.unmerged[:10]:
        w(f"  * {rel}:{ln} ({sec})")
    w(f"* полей, перезаписанных более поздним файлом (`overrides.tsv`): {len(st.overrides)}")
    for (of, nf), n in ov_pairs.most_common(15):
        w(f"  * {of} -> {nf}: {n}")
    w("")
    w("## Дерево исследований\n")
    w(f"Тем {rs['count']}, без dependencies и requires {rs['roots']}, "
      f"нужен предмет (needItem) {rs['needItem']}, нулевая стоимость {rs['zero_cost']}, "
      f"сумма cost {rs['cost_sum']}, с getOneFree {rs['with_getOneFree']}, с unlocks {rs['with_unlocks']}.\n")
    w(f"Самая длинная цепочка dependencies: {rs['max_depth']} тем.\n")
    w("```\n" + " <- ".join(rs["chain"][:60]) + "\n```\n")
    if rs["cycles"]:
        closed = [c for c, e in rs["cycles"] if not e]
        w(f"Циклов в dependencies: {len(rs['cycles'])} (`research_cycles.tsv`). Тема из чьего-то "
          f"unlocks берётся без проверки dependencies, так что цикл с таким входом - приём мода, "
          f"а не ошибка. Циклов без единого входа (не откроются никогда): **{len(closed)}**\n")
        for comp, entry in rs["cycles"][:30]:
            ent = "; ".join(f"{m} <- {g[0]}" for m, g in list(entry.items())[:2]) or "НЕТ ВХОДА"
            w(f"* {', '.join(comp[:6])}{' ...' if len(comp) > 6 else ''} - {ent}")
        w("")
    w("## Схема ссылок (выведена из данных)\n")
    w("Поле считается ссылкой, если 60 и больше процентов его строк - id одного раздела. "
      "Полный список - `ref_schema.tsv`.\n")
    w("| Откуда | Поле | Куда | Попало |\n|---|---|---|---|")
    for (s, p), (t, n, tot, sh, tg) in sorted(schema.items(), key=lambda x: -x[1][1])[:80]:
        w(f"| {s} | {p} | {'/'.join(sorted(tg))} | {n}/{tot} |")
    w("")
    w("## Как пользоваться\n")
    w("```\n# все поля предмета после слияния всех файлов\n"
      "grep -P '^items\\tSTR_PISTOL\\t' values.tsv\n"
      "# кто ссылается на тему исследования\n"
      "grep -P '\\tresearch\\tSTR_LASER_WEAPONS$' refs.tsv\n"
      "# какие поля бывают у брони и сколько раз\n"
      "grep -P '^armors\\t' fields.tsv\n```\n")
    w("Ограничение: повторная запись заменяет поле верхнего уровня целиком. Движок так делает "
      "почти везде, но словари вроде tags и списки, которые он дописывает, здесь могут выглядеть "
      "иначе, чем в игре. Спорное проверять по коду `Rule*::load`.")
    (a.out / "RUL.md").write_text("\n".join(L) + "\n", encoding=ENC_W)

    meta = {"mod": str(a.mod), "master": str(a.master), "files": len(order),
            "entries": len(st.rules), "unknown_keys": len(unknown), "dup_keys": len(st.dups),
            "dangling": len(dangling), "overrides": len(st.overrides),
            "seconds": round(time.time() - t0, 1), "built": time.strftime("%Y-%m-%d %H:%M:%S")}
    (a.out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding=ENC_W)
    print(json.dumps(meta, ensure_ascii=False))


if __name__ == "__main__":
    main()
