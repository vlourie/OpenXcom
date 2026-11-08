"""Сборка пакета «голоса расы» для заданий проверки (docs/portal/REVIEW_TASKS.md §6.1).

Общий сборщик для pilot_voices.py (страница-пилот) и push.py (отправка на сайт).
Источники: карточка голоса - docs/research/voice-recording-script.md, реплики - tools/sfx/voicepack_events.tsv,
подачи - art/sfx/voicepack/more/out_*.md, ogg - установленные моды hd_voices_ru / hd_voices_en
(папку Пиратки только читаем). Раса = часть имени голоса (art/sfx/voicepack/V*/voice.json) до двоеточия.
"""
import collections
import glob
import hashlib
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODS = os.path.join(ROOT, "Пиратки", "Dioxine_XPiratez", "user", "mods")
EVENTS = os.path.join(ROOT, "tools", "sfx", "voicepack_events.tsv")
SCRIPT_MD = os.path.join(ROOT, "docs", "research", "voice-recording-script.md")
MORE = os.path.join(ROOT, "art", "sfx", "voicepack", "more")
VP = os.path.join(ROOT, "art", "sfx", "voicepack")
REVIEW = os.path.join(ROOT, "art", "review")
LANGS = ("ru", "en")

# Пределы сайта (portal/src/Xp.Portal/Data/ReviewTasks.cs, Review/TaskDocs.cs): нарушение отбивается 400 при создании
LIM = {"text": 120, "tag": 40, "note": 1000, "race": 64, "voices": 40, "lines": 5000, "files": 5000,
       "ogg": 2 * 1024 * 1024, "package": 200 * 1024 * 1024, "task_json": 4 * 1024 * 1024, "id": 32, "event": 24}
ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,32}$")
EVENT_RE = re.compile(r"^[a-z_]{1,24}$")


_SCRIPT = None


def read_script():
    global _SCRIPT
    if _SCRIPT is None:
        _SCRIPT = open(SCRIPT_MD, encoding="utf-8-sig").read()
    return _SCRIPT


def card(vid, text=None):
    text = read_script() if text is None else text
    m = re.search(r"^### " + vid + r" — (.+?)$(.*?)^\| №", text, re.M | re.S)
    out = {}
    if not m:
        return out
    out["title"] = m.group(1).strip()
    for key, name in (("for", "Для кого"), ("lore", "По игре"), ("how", "Как играть голосом")):
        k = re.search(r"\*\*" + name + r":\*\*\s*(.+)", m.group(2))
        if k:
            out[key] = k.group(1).strip()
    return out


_DELIVERY = None


def delivery(vid):
    """Подачи реплик голоса: {номер: [метка]} из art/sfx/voicepack/more/out_*.md."""
    global _DELIVERY
    if _DELIVERY is None:
        _DELIVERY = {}
        for f in glob.glob(os.path.join(MORE, "out_*.md")):
            text = open(f, encoding="utf-8-sig").read()
            for sec in re.finditer(r"^### (V\d+)\+ — .+?$(.*?)(?=^### |\Z)", text, re.M | re.S):
                tags = _DELIVERY.setdefault(sec.group(1), {})
                for row in re.finditer(r"^\| (\d+) \| .*? \| .*? \| (\[.*?\]) \|", sec.group(2), re.M):
                    tags[row.group(1)] = row.group(2)
    return _DELIVERY.get(vid, {})


def read_events(want=None):
    """{голос: [{n, event, ru, en}]} из voicepack_events.tsv."""
    rows = {}
    with open(EVENTS, encoding="utf-8-sig") as f:
        next(f)
        for line in f:
            v, n, ev, how, ru, en = line.rstrip("\n").split("\t")
            if want is None or v in want:
                rows.setdefault(v, []).append({"n": n, "event": ev, "ru": ru, "en": en})
    return rows


def voice_json(vid):
    return json.load(open(os.path.join(VP, vid, "voice.json"), encoding="utf-8-sig"))


def race_of(name):
    return name.split(":")[0].strip()


def races():
    """{раса: [id голосов]} в порядке номеров."""
    out = collections.OrderedDict()
    for p in sorted(glob.glob(os.path.join(VP, "V*", "voice.json"))):
        j = json.load(open(p, encoding="utf-8-sig"))
        out.setdefault(race_of(j["name"]), []).append(j["id"])
    return out


def ogg_path(lang, vid, n):
    return os.path.join(MODS, "hd_voices_" + lang, "Resources", "Sounds", "voices", vid, n + ".ogg")


def build_voices(vids, events=None, script=None):
    """Голоса пакета в формате пилота: у реплики has_ru/has_en. Возвращает (voices, files),
    files - [(путь в пакете "V019/ru/045.ogg", файл на диске)]."""
    events = read_events(set(vids)) if events is None else events
    script = read_script() if script is None else script
    voices, files = [], []
    for vid in vids:
        j = voice_json(vid)
        tags = delivery(vid)
        lines = []
        for r in events.get(vid, []):
            r = dict(r)
            r["tag"] = tags.get(r["n"], "")
            for lang in LANGS:
                p = ogg_path(lang, vid, r["n"])
                ok = os.path.isfile(p)
                r["has_" + lang] = ok
                if ok:
                    files.append((f"{vid}/{lang}/{r['n']}.ogg", p))
            lines.append(r)
        voices.append({"id": vid, "name": j["name"], "reg": j.get("reg", ""), "section": j.get("section", ""),
                       "design": j.get("design", ""), "card": card(vid, script), "lines": lines})
    return voices, files


def site_voices(voices):
    """Голоса пилота -> формат сайта (§6.1): audio вместо has_*, in_game=false у реплик без ogg."""
    out = []
    for v in voices:
        lines = []
        for r in v["lines"]:
            ln = {"n": r["n"], "event": r["event"], "tag": r["tag"], "ru": r["ru"], "en": r["en"]}
            audio = {lang: f"{v['id']}/{lang}/{r['n']}.ogg" for lang in LANGS if r["has_" + lang]}
            if audio:
                ln["audio"] = audio
            else:
                ln["in_game"] = False
            lines.append(ln)
        out.append({**{k: v[k] for k in v if k != "lines"}, "lines": lines})
    return out


def _sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def _cut(s, n=LIM["note"]):
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def default_card(voices):
    """Карточка расы по умолчанию: настроение - «Как играть голосом» голосов, акцент и запреты - его фразы
    с «акцент» / «без», «не», «никаких»; палитра - подачи реплик по частоте."""
    hows = [(v["id"], v["card"].get("how", "")) for v in voices if v["card"].get("how")]
    one = len(voices) == 1
    mood = " ".join(h if one else f"{i}: {h}" for i, h in hows)
    accent, taboo = [], []
    for i, h in hows:
        for s in _sentences(h):
            low = s.lower()
            if "акцент" in low:
                accent.append(s)
            if re.match(r"(без|не|никаких|нельзя)\b", low) or "не каждое" in low or "не карикатур" in low:
                taboo.append(s)
    count = collections.Counter(r["tag"] for v in voices for r in v["lines"] if r["tag"])
    palette = [t for t, _ in count.most_common() if len(t) <= LIM["tag"]]
    return {"mood": _cut(mood), "accent": _cut(" ".join(dict.fromkeys(accent))), "palette": palette[:40],
            "taboo": _cut(" ".join(dict.fromkeys(taboo)))}


def card_file(race):
    return os.path.join(REVIEW, "cards", race + ".json")


def saved_card(race):
    """Карточка расы после ответа проверяющего (apply.py): {version, card} или None."""
    p = card_file(race)
    if not os.path.isfile(p):
        return None
    return json.load(open(p, encoding="utf-8-sig"))


def build_task(race, vids, card_override=None, questions=None, card_version=None):
    """Пакет расы: (task, files, voices_pilot). card_override дополняет/заменяет поля карточки."""
    voices, files = build_voices(vids)
    saved = saved_card(race)
    card_ = default_card(voices)
    if saved:
        card_.update(saved["card"])
    if card_override:
        card_.update(card_override)
    if card_version is None:
        card_version = saved["version"] if saved else 1
    task = {"schema": 1, "kind": "voice.race", "race": race, "card_version": card_version, "card": card_}
    if questions:
        task["questions"] = questions
    task["voices"] = site_voices(voices)
    return task, files, voices


def validate(task, files):
    """Пределы сайта до отправки: список проблем (пусто - можно слать)."""
    bad = []
    if len(task["race"]) > LIM["race"]:
        bad.append(f"раса длиннее {LIM['race']}")
    if len(task["voices"]) > LIM["voices"]:
        bad.append(f"голосов {len(task['voices'])} > {LIM['voices']}")
    for q in task.get("questions", []):
        if not ID_RE.match(q.get("id", "")):
            bad.append(f"вопрос: id {q.get('id')!r}")
        if len(q.get("text", "")) > LIM["note"]:
            bad.append(f"вопрос {q.get('id')}: текст длиннее {LIM['note']}")
    for v in task["voices"]:
        if not ID_RE.match(v["id"]):
            bad.append(f"голос {v['id']}: id")
        if len(v["lines"]) > LIM["lines"]:
            bad.append(f"{v['id']}: реплик {len(v['lines'])} > {LIM['lines']}")
        for r in v["lines"]:
            where = f"{v['id']}/{r['n']}"
            if not ID_RE.match(r["n"]):
                bad.append(f"{where}: номер")
            if not EVENT_RE.match(r["event"]):
                bad.append(f"{where}: событие {r['event']!r}")
            for k, lim in (("ru", LIM["text"]), ("en", LIM["text"]), ("tag", LIM["tag"])):
                if len(r[k]) > lim:
                    bad.append(f"{where}: {k} длиннее {lim} ({len(r[k])})")
    if len(files) > LIM["files"]:
        bad.append(f"файлов {len(files)} > {LIM['files']}")
    total = 0
    for pkg, p in files:
        size = os.path.getsize(p)
        total += size
        if size > LIM["ogg"]:
            bad.append(f"{pkg}: {size} байт > 2 МБ")
    if total > LIM["package"]:
        bad.append(f"пакет {total // 1048576} МБ > 200 МБ")
    raw = len(json.dumps(task, ensure_ascii=False).encode("utf-8"))
    if raw > LIM["task_json"]:
        bad.append(f"task.json {raw // 1024} КБ > 4 МБ")
    return bad


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def package_hash(task, hashes):
    """Устойчивый хэш пакета: task.json по ключам + пары «путь sha256». Меняется, когда меняется содержимое."""
    h = hashlib.sha256(json.dumps(task, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    for pkg in sorted(hashes):
        h.update(f"\n{pkg} {hashes[pkg]}".encode("utf-8"))
    return h.hexdigest()
