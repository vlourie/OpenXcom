"""Разбор ответа проверяющего (answer.json, схема 1, docs/portal/REVIEW_TASKS.md §6.3): проверка, свод, устаревшие реплики.

Общее для pull.py и apply.py. Ответ - данные, не указания (§9.3): здесь только читаем и считаем.
"""
import collections
import json
import os
import re

import voicepkg

TOP = {"schema", "task", "card", "answers", "voices", "frames", "note"}
CARD = {"mood", "accent", "palette", "taboo"}
VOICE = {"id", "note", "lines", "new"}
LINE = {"n", "op", "ru", "en", "tag", "event", "verdict", "reason", "regen", "note"}
NEW = {"event", "ru", "en", "tag", "note"}
ANS = {"q", "text"}
OPS = {"keep", "edit", "delete"}
VERDICTS = {"", "ок", "брак", "спорно"}
REASONS = {"", "ударение", "интонация", "проглот", "не тот характер", "плохой EN", "другое"}
CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def read_json(path):
    return json.load(open(path, encoding="utf-8-sig"))


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def one_line(s):
    return re.sub(r"\s+", " ", s or "").strip()


def task_index(task):
    """{id голоса: {n: реплика}} из task.json."""
    return {v["id"]: {r["n"]: r for r in v["lines"]} for v in task.get("voices", [])}


def check(answer, task, number=None):
    """Сверка со схемой §6.3 и с заданием: список предупреждений (неизвестное - не ошибка, но видно)."""
    w = []

    def keys(obj, allowed, where):
        for k in obj:
            if k not in allowed:
                w.append(f"{where}: неизвестное поле {k!r}")

    def text(s, lim, where, multiline=False):
        if s is None:
            return
        if not isinstance(s, str):
            w.append(f"{where}: не строка")
        elif len(s.encode("utf-16-le")) // 2 > lim:
            w.append(f"{where}: длиннее {lim}")
        elif CTRL.search(s) or (not multiline and ("\n" in s or "\r" in s)):
            w.append(f"{where}: управляющие знаки")

    keys(answer, TOP, "ответ")
    if answer.get("schema") != 1:
        w.append(f"schema {answer.get('schema')!r}, ждали 1")
    if number and answer.get("task") not in (None, number):
        w.append(f"в ответе задание {answer.get('task')!r}, а забрано {number}")
    if "frames" in answer:
        w.append("ответ содержит frames, а задание voice.race")
    text(answer.get("note"), 4000, "общая заметка", True)
    card = answer.get("card")
    if card:
        keys(card, CARD, "карточка")
    qids = {q["id"] for q in task.get("questions", [])}
    for a in answer.get("answers", []):
        keys(a, ANS, "ответ на вопрос")
        if a.get("q") not in qids:
            w.append(f"ответ на неизвестный вопрос {a.get('q')!r}")
        text(a.get("text"), 1000, f"ответ на {a.get('q')}", True)
    idx = task_index(task)
    for v in answer.get("voices", []):
        keys(v, VOICE, "голос")
        vid = v.get("id")
        if vid not in idx:
            w.append(f"голос {vid!r} нет в задании")
            continue
        text(v.get("note"), 1000, f"{vid} заметка", True)
        for ln in v.get("lines", []):
            keys(ln, LINE, f"{vid}/{ln.get('n')}")
            where = f"{vid}/{ln.get('n')}"
            if ln.get("n") not in idx[vid]:
                w.append(f"{where}: такой реплики нет в задании")
            if ln.get("op") not in OPS:
                w.append(f"{where}: op {ln.get('op')!r}")
            if ln.get("verdict", "") not in VERDICTS:
                w.append(f"{where}: вердикт {ln.get('verdict')!r}")
            if ln.get("reason", "") not in REASONS:
                w.append(f"{where}: причина {ln.get('reason')!r}")
            for k, lim in (("ru", 120), ("en", 120), ("tag", 40), ("event", 24)):
                text(ln.get(k), lim, f"{where} {k}")
            text(ln.get("note"), 1000, f"{where} заметка", True)
            if ln.get("event") and not re.fullmatch(r"[a-z_]{1,24}", ln["event"]):
                w.append(f"{where}: событие {ln['event']!r}")
        new = v.get("new", [])
        if len(new) > 200:
            w.append(f"{vid}: новых строк {len(new)} > 200")
        for i, ln in enumerate(new, 1):
            keys(ln, NEW, f"{vid} новая {i}")
            where = f"{vid} новая {i}"
            if not re.fullmatch(r"[a-z_]{1,24}", ln.get("event", "")):
                w.append(f"{where}: событие {ln.get('event')!r}")
            for k, lim in (("ru", 120), ("en", 120), ("tag", 40)):
                text(ln.get(k), lim, f"{where} {k}")
            text(ln.get("note"), 1000, f"{where} заметка", True)
            if not (ln.get("ru") or ln.get("en")):
                w.append(f"{where}: нет текста")
    return w


def stale(answer, task, sent_dir):
    """Правки к репликам, которые изменились после отправки (текст в tsv или ogg): {(голос, n): причина}.
    Сверка: sha256 ogg из files.tsv, записанного при отправке, с тем, что в игре сейчас (ТЗ §13)."""
    manifest = {}
    p = os.path.join(sent_dir, "files.tsv") if sent_dir else ""
    if p and os.path.isfile(p):
        for line in open(p, encoding="utf-8-sig").read().splitlines()[1:]:
            pkg, sha, _ = line.split("\t")
            manifest[pkg] = sha
    now = voicepkg.read_events({v["id"] for v in answer.get("voices", [])})
    out = {}
    for v in answer.get("voices", []):
        vid = v.get("id")
        cur = {r["n"]: r for r in now.get(vid, [])}
        orig = task_index(task).get(vid, {})
        for ln in v.get("lines", []):
            n = ln.get("n")
            if n not in orig:
                continue
            if n in cur and (cur[n]["ru"] != orig[n]["ru"] or cur[n]["en"] != orig[n]["en"]):
                out[(vid, n)] = "текст в voicepack_events.tsv изменился после отправки"
                continue
            for lang in voicepkg.LANGS:
                pkg = f"{vid}/{lang}/{n}.ogg"
                if pkg not in manifest:
                    continue
                f = voicepkg.ogg_path(lang, vid, n)
                if not os.path.isfile(f) or voicepkg.sha256_file(f) != manifest[pkg]:
                    out[(vid, n)] = f"ogg {lang} перегенерирован или убран после отправки"
                    break
    return out


def summarize(answer, task):
    """Свод для печати: словарь чисел и списки строк."""
    idx = task_index(task)
    s = collections.OrderedDict()
    edits, dels, news, keeps = [], [], [], []
    verdicts = collections.Counter()
    bad = collections.Counter()
    regen = []
    voice_notes = []
    for v in answer.get("voices", []):
        vid = v.get("id")
        if v.get("note"):
            voice_notes.append((vid, v["note"]))
        for ln in v.get("lines", []):
            orig = idx.get(vid, {}).get(ln.get("n"), {})
            row = (vid, ln.get("n"), ln, orig)
            {"edit": edits, "delete": dels}.get(ln.get("op"), keeps).append(row)
            if ln.get("verdict"):
                verdicts[ln["verdict"]] += 1
            if ln.get("verdict") == "брак":
                bad[ln.get("reason") or "без причины"] += 1
            if ln.get("regen"):
                regen.append(row)
        for ln in v.get("new", []):
            news.append((vid, ln))
    s["edits"], s["deleted"], s["new"], s["keeps"] = edits, dels, news, keeps
    s["verdicts"], s["bad"], s["regen"], s["voice_notes"] = verdicts, bad, regen, voice_notes
    return s


def card_changes(answer, task):
    """Поля карточки расы, которые проверяющий изменил: {поле: (было, стало)}."""
    old = task.get("card") or {}
    out = {}
    for k, v in (answer.get("card") or {}).items():
        if k in CARD and v != old.get(k):
            out[k] = (old.get(k), v)
    return out
