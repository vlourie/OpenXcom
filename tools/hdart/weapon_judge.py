#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Независимая визуальная проверка HD-оружия (указание специалиста 05.10) и свод трёх итогов автоприёмки.

Судья - Codex (codex exec, только чтение, без видеокарты: рисует и думает сервис; текстовая модель и Qwen на карте
вместе не грузятся НИКОГДА). Вход вслепую - выводов автоматики судья не видит:
  1. оригинал BIGOBS слева и ответ справа в одном масштабе (ответ равномерно на габарит оригинала, без деформаций);
  2. ответ отдельно, крупно - для оценки исполнения;
  3. кадр боеприпаса (если есть);
  текст: опознание и описание (what_v2), боеприпас из карточки, список деталей разметки с местом в пикселях спрайта.
Ответ - JSON по схеме: по каждой детали OK / MISSING / SHIFTED / RESIZED / REPLACED / TURNED / UNSURE с местом,
лишние детали, исполнение GOOD / BAD / UNSURE, тот же ли это предмет. Три ПОВТОРНЫЕ оценки одной модели (отдельные
сессии): довод - только то, что назвало большинство. Это не независимые судьи - ошибки одной модели могут совпадать;
голосование снижает случайные промахи (одиночные ложные тревоги контролей 05.10), но независимости не доказывает.
Каждая оценка даёт по детали не больше одного голоса: деталь, названная дважды с разными статусами, или не
названная вовсе - голоса нет (run_votes); большинство считается от ЗАПЛАНИРОВАННОГО числа оценок.

Свод (decide, правка 05.10 по разбору специалиста): рисунок - weapon_accept.drawing_verdict, серую зону снимает только
большинство GOOD; конструкция - надёжное нарушение (габарит по родной альфе вне ±3 %, FAIL детали, устойчивый к
разметке - weapon_parts.label_check) стоит само. Всё остальное - открытые вопросы, и вопрос снимается только ЯВНЫМ
большинством OK; UNSURE, пропуск и отсутствие большинства - вопрос не решён. Нерешённое и всё, что зависит от
выделения детали, идёт на крупный фрагмент (frag: оригинал и ответ x24 с сеткой пикселей и контуром детали, три
повторные оценки), и только остаток - человеку, отложенным списком. Фрагмент только ПОДТВЕРЖДАЕТ дефект: по
контролям 05.10 его SAME пропускает 4 из 10 дефектов в 1-2 пикселя (FRAG_SAME_RESOLVES). Размещение - weapon_parts.placement; .wide не
предполагается.

    py -3.13 tools/hdart/weapon_judge.py run --only W-001,... --cut <cut> --tag <tag> [--runs 3] [--jobs 4]
    py -3.13 tools/hdart/weapon_judge.py controls --tag <tag>      контроли судьи: допустимое (оригинал x4 с другими
                                  бликами, фактурой, сглаженным краем) - без дефектов; вставленный дефект - назван у
                                  своей детали; хороший рисунок чужого предмета (edit-B) - 'другой предмет'
    py -3.13 tools/hdart/weapon_judge.py frag-controls --tag <tag>  контроли крупного фрагмента: допустимое - SAME,
                                  дефект в 1-2 пикселя спрайта и добавленный кусок - DIFFERENT (большинством)
    py -3.13 tools/hdart/weapon_judge.py decide --parts <parts_*.json> ... --tag <tag> [--no-frag]
    py -3.13 tools/hdart/weapon_judge.py freeze --version V2       заморозить код и задания (sha256)
    --version V2 у run / frag-controls / decide: отказ, если код или задания изменились после заморозки
"""
import argparse
import concurrent.futures as cf
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)

import numpy as np                      # noqa: E402
from PIL import Image, ImageDraw        # noqa: E402

import weapon_fit as wf                 # noqa: E402
import weapon_parts as wp               # noqa: E402

ENC = "utf-8-sig"
JZ = 12                                 # масштаб листа судьи: пиксель спрайта = JZ пикселей
OUT = "art/items/weapons-chatgpt-v2/judge"
STATUS = ["OK", "MISSING", "SHIFTED", "RESIZED", "REPLACED", "TURNED", "UNSURE"]
DEFECT = {"MISSING", "SHIFTED", "RESIZED", "REPLACED", "TURNED"}

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["parts", "extra", "drawing", "drawing_defects", "same_weapon", "summary"],
    "properties": {
        "parts": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["part", "status", "where", "note"],
            "properties": {"part": {"type": "string"}, "status": {"type": "string", "enum": STATUS},
                           "where": {"type": "string"}, "note": {"type": "string"}}}},
        "extra": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["what", "where"],
            "properties": {"what": {"type": "string"}, "where": {"type": "string"}}}},
        "drawing": {"type": "string", "enum": ["GOOD", "BAD", "UNSURE"]},
        "drawing_defects": {"type": "array", "items": {"type": "string"}},
        "same_weapon": {"type": "string", "enum": ["YES", "NO", "UNSURE"]},
        "summary": {"type": "string"}}}

TASK = """You are an independent visual inspector of HD game art. Work only from the attached images and this text.
Do not run tools, do not open files. Answer with JSON matching the given schema.

Image 1: LEFT - the ORIGINAL inventory sprite of a weapon (low-resolution pixel art, %(w)dx%(h)d sprite pixels,
each sprite pixel shown as a %(z)dx%(z)d block). RIGHT - the HD redraw, scaled uniformly onto the same frame at the
same scale. Image 2: the HD redraw alone, larger. %(ammo_img)s
The ORIGINAL is the truth for the design: which parts exist, where each part is, its size, proportions, orientation.
The HD redraw must be the SAME weapon: the same parts in the same places, same proportions; only resolution,
materials and finish improve.

ALLOWED (not defects): different highlights and shading, different metal or wood texture, smoother and cleaner edges,
finer detail inside a part (screws, grooves, rivets), slightly different colour tone, small differences under about
one sprite pixel.
DEFECTS - name the exact part:
  MISSING  - a part of the original is absent in the redraw;
  SHIFTED  - the part is there but clearly moved (about 2 sprite pixels or more);
  RESIZED  - clearly longer, shorter, thicker or thinner (about 2 sprite pixels or more);
  REPLACED - a different kind of part in its place (e.g. a box magazine instead of a drum, a lever instead of a trigger);
  TURNED   - the part points in another direction;
  UNSURE   - you cannot tell.
List EXTRA parts the redraw added that the original does not have (a second barrel, an added scope, a strap...).
Rate the EXECUTION of the redraw by itself (drawing): GOOD - clean painted HD art; BAD - traced pixel staircase,
blotchy flat patches, pixel mush, blur, holes or see-through body, leftover background. Put concrete problems in
drawing_defects. same_weapon: is it recognisably the same weapon as the original?

Weapon: %(name)s (%(type)s). Identity: %(identity)s.
Description of the original sprite: %(desc)s
Ammunition: %(ammo)s
Parts of the original (name, kind, place in sprite pixels x0,y0-x1,y1 with y down, note) - give one entry per part,
using exactly these names:
%(parts)s
"""


def _crop_box(a_o, a_n, pad=2):
    """Общая рамка оригинала и ответа (канвас k=JZ) с запасом pad пикселей спрайта: лишнее и сдвинутое за
    габаритом оригинала судья обязан видеть."""
    b0, b1 = wf.bbox(a_o > 0), wf.bbox(a_n > 8) if (a_n > 8).any() else wf.bbox(a_o > 0)
    H, W = a_o.shape
    return (max(0, min(b0[0], b1[0]) - pad * JZ), max(0, min(b0[1], b1[1]) - pad * JZ),
            min(W, max(b0[2], b1[2]) + pad * JZ), min(H, max(b0[3], b1[3]) + pad * JZ))


def placed_answer(path, m_o, z=JZ):
    """Ответ равномерно на габарит оригинала, канвас размера спрайта x z (как нарезка; ничего не тянется)."""
    import weapon_from_ref as wr
    rgb, a, _bg = wr.ref_matte(path)
    b = wf.bbox(m_o)
    c, al, _rep = wr.place(rgb, a, b, z, m_o.shape[1] * z, m_o.shape[0] * z)
    return np.dstack([c, al * 255.0]).clip(0, 255).astype(np.uint8)


def orig_k(rgb_o, m_o):
    c = np.repeat(np.repeat(rgb_o, JZ, 0), JZ, 1)
    a = np.repeat(np.repeat(m_o.astype(np.float32) * 255, JZ, 0), JZ, 1)
    return np.dstack([c, a]).clip(0, 255).astype(np.uint8)


def build(key, ms, t, ans_rgba, path_big, dst):
    """Картинки судьи и текст задания. ans_rgba - ответ уже на канвасе JZ; path_big - файл для крупного вида."""
    os.makedirs(dst, exist_ok=True)
    rgb_o, m_o = wf.original(t)
    ok_ = orig_k(rgb_o, m_o)
    box = _crop_box(ok_[..., 3], ans_rgba[..., 3])
    left, right = Image.fromarray(ok_).crop(box), Image.fromarray(ans_rgba).crop(box)
    f = wp.font(20)
    sheet = Image.new("RGB", (left.width * 2 + 24, left.height + 34), (28, 30, 34))
    sheet.paste(wp.on_dark(left), (0, 34))
    sheet.paste(wp.on_dark(right), (left.width + 24, 34))
    d = ImageDraw.Draw(sheet)
    d.text((4, 6), "ORIGINAL", fill=(230, 230, 230), font=f)
    d.text((left.width + 28, 6), "HD REDRAW", fill=(230, 230, 230), font=f)
    p1 = os.path.join(dst, key + ".pair.png")
    sheet.save(p1)
    big = Image.open(path_big).convert("RGBA") if isinstance(path_big, str) else path_big
    s = 1100.0 / max(big.size)
    if s < 1:
        big = big.resize((int(big.width * s), int(big.height * s)), Image.LANCZOS)
    p2 = os.path.join(dst, key + ".big.png")
    wp.on_dark(big).save(p2)
    imgs = [p1, p2]
    card = wp.cards().get(ms, {})
    ammo_txt, ammo_img = "none (melee or no magazine)", ""
    for sl in card.get("slots", []):
        for am in sl.get("ammo", []):
            ammo_txt = "%s, %s rounds" % (am.get("en"), am.get("clipSize"))
            fr = wp.ammo_frame(am["frame"]) if am.get("frame") is not None else None
            if fr is not None and len(imgs) == 2:
                fr = fr.resize((fr.width * 8, fr.height * 8), Image.NEAREST)
                p3 = os.path.join(dst, key + ".ammo.png")
                wp.on_dark(fr).save(p3)
                imgs.append(p3)
                ammo_img = "Image 3: the ammunition item (magazine / clip) sprite, for reference."
            break
        break
    w2 = wp.what2().get(ms, {})
    spec = wp.load_parts(ms)
    lab = wp.label_map(spec, m_o)
    lines = []
    for i, p in enumerate(spec["parts"]):
        ys, xs = np.nonzero(lab == i)
        place = "%d,%d-%d,%d" % (xs.min(), ys.min(), xs.max(), ys.max()) if len(xs) else "-"
        lines.append("  - %s (%s) at %s%s" % (p["name"], p.get("kind", ""), place,
                                              ("; " + p["note"]) if p.get("note") else ""))
    task = TASK % {"w": m_o.shape[1], "h": m_o.shape[0], "z": JZ, "ammo_img": ammo_img,
                   "name": card.get("en", t), "type": t, "identity": w2.get("identity", "-"),
                   "desc": "; ".join(x for x in (w2.get("orientation"), w2.get("details"), w2.get("materials"))
                                     if x) or "-",
                   "ammo": ammo_txt, "parts": "\n".join(lines)}
    with open(os.path.join(dst, key + ".task.txt"), "w", encoding="utf-8") as fo:
        fo.write(task)
    return imgs, task


def ask(imgs, task, last, log, effort="medium", schema=None):
    codex = shutil.which("codex") or "codex"
    schema = schema or SCHEMA
    sch = os.path.join(os.path.dirname(last), "schema.json")
    if not os.path.exists(sch):
        with open(sch, "w", encoding="utf-8") as fo:
            json.dump(schema, fo)
    with open(sch, encoding="utf-8") as fo:
        if json.load(fo) != schema:
            raise SystemExit("в %s другая схема ответа" % sch)
    cmd = [codex, "exec", "--skip-git-repo-check", "--sandbox", "read-only", "--color", "never",
           "-c", "model_reasoning_effort=" + effort, "--output-schema", os.path.abspath(sch),
           "-o", os.path.abspath(last)] + sum([["-i", os.path.abspath(q)] for q in imgs], []) + ["-"]
    t0 = time.time()
    # задание через stdin: codex.cmd режет аргумент на первом переводе строки (R-222)
    with open(log, "w", encoding="utf-8") as lf:
        rc = subprocess.run(cmd, cwd=os.path.dirname(os.path.abspath(last)), stdout=lf, stderr=subprocess.STDOUT,
                            input=task.encode("utf-8"), timeout=30 * 60).returncode
    with open(log, encoding="utf-8", errors="replace") as lf:
        got = task.strip().splitlines()[-1].strip()[:50] in lf.read()
    try:
        with open(last, encoding="utf-8") as fo:
            ans = json.load(fo)
    except (OSError, ValueError):
        ans = None
    return ans, rc, time.time() - t0, got


def run_items(items, tag, runs=3, jobs=4, effort="medium"):
    """items: (ключ, мастер, тип, ответ RGBA на канвасе JZ, крупный вид). Готовые ответы не переспрашиваются."""
    dst = os.path.join(ROOT, OUT, tag)
    jobs_l = []
    for key, ms, t, ans_rgba, big in items:
        imgs, task = build(key, ms, t, ans_rgba, big, os.path.join(dst, "in")) if ms else (None, None)
        for k in range(1, runs + 1):
            last = os.path.join(dst, "%s.r%d.json" % (key, k))
            if not os.path.exists(last):
                jobs_l.append((key, k, imgs, task, last))
    print("заданий судье: %d (%s)" % (len(jobs_l), dst), flush=True)

    def one(j):
        key, k, imgs, task, last = j
        ans, rc, sec, got = ask(imgs, task, last, last[:-5] + ".log", effort)
        print("%s r%d: код %d, %.0f с, задание целиком %s, ответ %s" % (
            key, k, rc, sec, "да" if got else "НЕТ", "есть" if ans else "НЕТ"), flush=True)
        return key, k, ans
    with cf.ThreadPoolExecutor(jobs) as ex:
        list(ex.map(one, jobs_l))


def load(tag, key, runs=3):
    out = []
    for k in range(1, runs + 1):
        p = os.path.join(ROOT, OUT, tag, "%s.r%d.json" % (key, k))
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fo:
                out.append(json.load(fo))
    return out


def part_status(ans, name):
    for p in ans.get("parts", []):
        if p["part"].strip().lower() == name.lower():
            return p["status"], p.get("where", ""), p.get("note", "")
    return "UNSURE", "", "деталь не названа"


# ------------------------------------------------------------------------------------------------ контроли

def edit_placed(ans_k, spec, m_o, part, how):
    """Вставленный дефект на ответе (канвас JZ): деталь убрана / сдвинута на n пикселей спрайта / лишний кусок."""
    lab = wp.label_map(spec, m_o)
    i = [p["name"] for p in spec["parts"]].index(part)
    up = lambda m: np.repeat(np.repeat(m, JZ, 0), JZ, 1)  # noqa: E731
    z = up(lab == i)
    z = (wf.dilate(z, JZ // 3) & ~up((lab >= 0) & (lab != i))) | z     # кромка детали, но не соседние детали
    out = ans_k.copy()
    if how[0] == "remove":
        out[z, 3] = 0
    elif how[0] in ("shift", "copy"):
        dx, dy = how[1] * JZ, how[2] * JZ
        ys, xs = np.nonzero(z & (ans_k[..., 3] > 0))
        ok = (ys + dy >= 0) & (ys + dy < out.shape[0]) & (xs + dx >= 0) & (xs + dx < out.shape[1])
        piece = ans_k[ys[ok], xs[ok]].copy()
        if how[0] == "shift":
            out[z, 3] = 0
        out[ys[ok] + dy, xs[ok] + dx] = piece
    return out


# (ключ, мастер, что): ok - допустимые изменения оригинала (weapon_accept 'all'), обязаны пройти без дефектов;
# дефект поверх настоящего ответа cg0 - обязан быть назван у этой детали (или EXTRA для копии)
CONTROLS = [("ok", m, v) for v in ("all", "clean") for m in ("W-015", "W-059", "W-036", "W-079")] + [
            ("def", "W-059", ("magazine", ("remove",), "MISSING")),
            ("def", "W-015", ("magazine", ("shift", 0, 3), "SHIFTED")),
            ("def", "W-013", ("magazine", ("remove",), "MISSING")),
            ("def", "W-066", ("magazine", ("copy", 7, 0), "EXTRA")),
            ("def", "W-089", ("blade", ("shift", 3, 0), "SHIFTED"))] + [
            # хороший рисунок ЧУЖОГО предмета (Edit-2511 вариант B: АК вместо кольта и мачете, прибор вместо дробовика)
            ("wrong", m, "art/items/weapons-edit-v1/B/%s.png" % t) for m, t in (
                ("W-040", "STR_COLT45"), ("W-081", "STR_MACHETE"), ("W-015", "STR_COMBAT_SHOTGUN"),
                ("W-014", "STR_TOMMYGUN"))]


def control_items(cuts):
    import weapon_accept as wa
    L = wf.list_rows()
    items, want = [], {}
    for kind, ms, d in CONTROLS:
        t = L[ms]["type"]
        rgb_o, m_o = wf.original(t)
        spec = wp.load_parts(ms)
        if kind == "ok":
            v = wa.variant(rgb_o, m_o, d, 0)          # k=4
            big = Image.fromarray(v).resize((v.shape[1] * JZ // 4, v.shape[0] * JZ // 4), Image.BICUBIC)
            key = "ctl_ok_" + ms + ("" if d == "all" else "_" + d)
            items.append((key, ms, t, np.asarray(big), big))
            want[key] = ("ok", None, None)
            continue
        if kind == "wrong":
            key = "ctl_wrong_" + ms
            items.append((key, ms, t, placed_answer(os.path.join(ROOT, d), m_o), os.path.join(ROOT, d)))
            want[key] = ("wrong", None, None)
            continue
        meta = None
        for c in cuts:
            mp = os.path.join(ROOT, c, "meta", t + ".json")
            if os.path.exists(mp):
                with open(mp, encoding=ENC) as fo:
                    meta = json.load(fo)
        if meta is None:
            print("контроль %s: нет нарезки" % ms)
            continue
        if d[0] not in [p["name"] for p in spec["parts"]]:
            print("контроль %s: нет детали %s" % (ms, d[0]))
            continue
        ans_k = placed_answer(meta["ref"], m_o)
        e = edit_placed(ans_k, spec, m_o, d[0], d[1])
        key = "ctl_def_%s_%s_%s" % (ms, d[0], d[1][0])
        items.append((key, ms, t, e, Image.fromarray(e)))
        want[key] = ("def", d[0], d[2])
    return items, want


def controls(tag, cuts, runs=3, jobs=4):
    items, want = control_items(cuts)
    run_items(items, tag, runs, jobs)
    res = []
    for key, (kind, part, exp) in want.items():
        for k, ans in enumerate(load(tag, key, runs), 1):
            if kind == "ok":
                bad = [p["part"] + ":" + p["status"] for p in ans["parts"] if p["status"] in DEFECT]
                ok = not bad and not ans["extra"]
                got = "дефектов нет" if ok else "назвал: %s%s" % (", ".join(bad), " +лишнее" if ans["extra"] else "")
            elif kind == "wrong":
                bad = [p["part"] for p in ans["parts"] if p["status"] in DEFECT]
                ok = ans["same_weapon"] == "NO" or len(bad) >= 2
                got = "тот же предмет: %s, дефектов %d" % (ans["same_weapon"], len(bad))
            elif exp == "EXTRA":
                ok = bool(ans["extra"]) or part_status(ans, part)[0] in DEFECT
                got = "лишнее: %s" % "; ".join(e["what"] for e in ans["extra"]) if ans["extra"] else \
                    "лишнего нет (%s %s)" % (part, part_status(ans, part)[0])
            else:
                st = part_status(ans, part)[0]
                ok = st in DEFECT
                got = "%s %s" % (part, st)
            res.append((key, k, ok))
            print("%-44s r%d %-5s %s" % (key, k, "OK" if ok else "ПРОМАХ", got))
    print("контроли судьи по прогонам: верно %d из %d" % (sum(r[2] for r in res), len(res)))
    maj = []
    for key, (kind, part, exp) in want.items():
        ms = key.split("_")[2]
        names = [p["name"] for p in wp.load_parts(ms)["parts"]]
        vt = vote(load(tag, key, runs), names, runs)
        if kind == "ok":
            # допустимое проходит, только если КАЖДАЯ деталь получила явное большинство OK и лишнего нет большинством
            no_ok = sorted(n for n in names if n.lower() not in vt["ok_major"])
            ok = not no_ok and vt["no_extra"]
            got = "все детали OK большинством" if ok else "без большинства OK: %s%s" % (
                ", ".join(no_ok) or "-", "" if vt["no_extra"] else " +нет большинства 'лишнего нет'")
        elif kind == "wrong":
            ok = vt["same"] == "NO" or len(vt["major"]) >= 2
            got = "тот же предмет большинством: %s, дефектов большинством %d" % (vt["same"], len(vt["major"]))
        elif exp == "EXTRA":
            ok = vt["extra"] or part.lower() in vt["major"]
            got = "лишнее большинством" if vt["extra"] else "лишнего нет"
        else:
            ok = part.lower() in vt["major"]
            got = "%s %s" % (part, "назван большинством" if ok else "НЕ назван")
        maj.append(ok)
        print("большинство %d из %d (ответов %d)  %-40s %-5s %s" % (vt["need"], vt["n_plan"], vt["n"], key,
                                                                    "OK" if ok else "ПРОМАХ", got))
    print("контроли судьи большинством: верно %d из %d" % (sum(maj), len(maj)))
    return res


def run_votes(ans, names):
    """Голос ОДНОЙ оценки по каждой детали разметки - не больше одного. Деталь, названная дважды с разными
    статусами, - голоса нет (оценка сама себе противоречит); не названная - голоса нет. Чужие имена - в отчёт.
    -> ({деталь: 'OK' | 'DEFECT' | 'UNSURE' | 'NONE'}, {деталь: статус}, полнота)."""
    want = {n.lower(): n for n in names}
    seen, unknown = {}, []
    for p in ans.get("parts", []):
        k = p["part"].strip().lower()
        if k not in want:
            unknown.append(p["part"])
            continue
        seen.setdefault(k, []).append(p)
    vote_, stat, conflict = {}, {}, []
    for k in want:
        st = [p["status"] for p in seen.get(k, [])]
        if not st or len(set(st)) > 1:
            vote_[k] = "NONE"
            if st:
                conflict.append(k)
            continue
        stat[k] = st[0]
        vote_[k] = "OK" if st[0] == "OK" else ("DEFECT" if st[0] in DEFECT else "UNSURE")
    comp = {"missing": sorted(k for k in want if k not in seen), "conflict": sorted(conflict), "unknown": unknown,
            "repeated": sorted(k for k, v in seen.items() if len(v) > 1 and k not in conflict)}
    return vote_, stat, comp


def vote(judges, names=None, runs=3):
    """Голоса повторных оценок. Большинство - больше половины ЗАПЛАНИРОВАННЫХ оценок (runs): пропавший ответ не
    уменьшает порог. По детали у оценки один голос (run_votes). names - детали разметки; без них - все названные."""
    n_plan = max(runs, len(judges))
    need = n_plan // 2 + 1
    if names is None:
        names = sorted({p["part"].strip() for a in judges for p in a.get("parts", [])}, key=str.lower)
    per = [run_votes(a, names) for a in judges]
    keys = [x.lower() for x in names]
    votes = {k: [v[0][k] for v in per] for k in keys}
    cnt = {k: sum(x == "DEFECT" for x in v) for k, v in votes.items()}
    okc = {k: sum(x == "OK" for x in v) for k, v in votes.items()}
    notes = {}
    for a in judges:
        for p in a.get("parts", []):
            k = p["part"].strip().lower()
            if p["status"] in DEFECT:
                notes.setdefault(k, "%s: %s" % (p["status"], p.get("note", "")))
    dr = [a["drawing"] for a in judges]
    sw = [a["same_weapon"] for a in judges]
    return {"n": len(judges), "n_plan": n_plan, "need": need, "votes": votes,
            "defects": [sorted(k for k, x in v[0].items() if x == "DEFECT") for v in per],
            "major": {k for k, c in cnt.items() if c >= need},
            "split": {k for k, c in cnt.items() if 0 < c < need},
            "ok_major": {k for k, c in okc.items() if c >= need},
            "extra": sum(bool(a["extra"]) for a in judges) >= need,
            "no_extra": sum(not a["extra"] for a in judges) >= need,
            "drawing": next((d for d in ("GOOD", "BAD") if dr.count(d) >= need), "SPLIT") if judges else "NONE",
            "same": next((d for d in ("YES", "NO") if sw.count(d) >= need), "SPLIT") if judges else "NONE",
            "completeness": [v[2] for v in per], "notes": notes}


# ------------------------------------------------------------------------------------------------ крупный фрагмент

# Крупный фрагмент только ПОДТВЕРЖДАЕТ дефект (DIFFERENT большинством). Контроли fctl2 05.10: допустимое - SAME 18
# из 18 (ложных DIFFERENT 0), но вставленные дефекты в 1-2 пикселя спрайта - SAME у 4 из 10 (сужение клинка W-079
# дважды, срезанный конец ствола W-059, сдвиг рукояти W-081). SAME фрагмента не довод - вопрос уходит человеку.
FRAG_SAME_RESOLVES = False
FZ = 24                                 # фрагмент: пиксель спрайта = FZ пикселей
FRAG_PAD = 3                            # запас вокруг детали, пиксели спрайта
FRAG = "frag"
FRAG_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["status", "differences", "note"],
    "properties": {
        "status": {"type": "string", "enum": ["SAME", "DIFFERENT", "UNSURE"]},
        "differences": {"type": "array", "items": {"type": "string", "enum": [
            "NARROWER", "WIDER", "SHORTER", "LONGER", "SHIFTED", "MISSING", "ADDED", "OTHER_SHAPE"]}},
        "note": {"type": "string"}}}

FRAG_HEAD = """You are an independent visual inspector of HD game art. Work only from the attached image and this text.
Do not run tools, do not open files. Answer with JSON matching the given schema.

The image is one magnified fragment of a weapon sprite. LEFT - the ORIGINAL low-resolution sprite. RIGHT - the HD
redraw, placed uniformly on exactly the same frame at the same scale (nothing stretched). The faint grid marks
sprite pixels (one cell = one sprite pixel) and is at the same place on both sides.
Weapon: %(name)s. %(desc)s
"""
FRAG_PART = FRAG_HEAD + """
The %(part)s (%(kind)s) is outlined in cyan on BOTH sides at the same place; on the LEFT the outline follows the
original part exactly. Question: does the redraw's %(part)s match the original part in length, width and position?
SAME - it fills the same outline: allowed are smoother or rounder edges, different shading, highlights, texture,
colour tone, fine detail inside the outline, and differences under about half a sprite pixel.
DIFFERENT - over a run of several pixels the redraw's part is narrower, wider, shorter, longer or moved by about one
sprite pixel or more against the outline, or it is missing, or a different kind of part stands there. Count grid
cells against the outline; do not judge by impression.
UNSURE - you cannot tell from this image.
"""
FRAG_BOX = FRAG_HEAD + """
A dashed yellow box marks the same area on both sides; in the ORIGINAL there is nothing inside it.
Question: did the redraw ADD something there?
SAME - nothing added: empty, or only the smoothed or rounded edge of a neighbouring part (under about one sprite pixel).
DIFFERENT - the redraw has a part or a piece of a part there that the original does not have (difference ADDED).
UNSURE - you cannot tell from this image.
"""


def frag_sheet(rgb_o, m_o, ans_z, lab=None, i=None, box=None):
    """Лист фрагмента: оригинал x FZ и ответ x FZ (канвас спрайта), сетка пикселей спрайта, контур детали i (голубой)
    или рамка box (x, y, w, h, жёлтый пунктир) на обеих сторонах. -> PIL RGB."""
    H, W = m_o.shape
    if i is not None:
        ys, xs = np.nonzero(lab == i)
        x0, y0, x1, y1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
    else:
        x0, y0, x1, y1 = box[0], box[1], box[0] + box[2], box[1] + box[3]
    X0, Y0 = max(0, x0 - FRAG_PAD), max(0, y0 - FRAG_PAD)
    X1, Y1 = min(W, x1 + FRAG_PAD), min(H, y1 + FRAG_PAD)
    o = np.dstack([np.repeat(np.repeat(rgb_o, FZ, 0), FZ, 1),
                   np.repeat(np.repeat(m_o.astype(np.float32) * 255, FZ, 0), FZ, 1)]).clip(0, 255).astype(np.uint8)
    sides = []
    for img in (o, ans_z):
        crop = Image.fromarray(img[Y0 * FZ:Y1 * FZ, X0 * FZ:X1 * FZ])
        bg = Image.new("RGBA", crop.size, (28, 30, 34, 255))
        bg.alpha_composite(crop)
        im = bg.convert("RGB")
        d = ImageDraw.Draw(im)
        for gx in range(0, im.width + 1, FZ):
            d.line([(gx, 0), (gx, im.height)], fill=(64, 66, 76))
        for gy in range(0, im.height + 1, FZ):
            d.line([(0, gy), (im.width, gy)], fill=(64, 66, 76))
        if i is not None:
            z = (lab == i)[Y0:Y1, X0:X1]
            hh, ww = z.shape
            for y in range(hh):
                for x in range(ww):
                    if not z[y, x]:
                        continue
                    for dy, dx, seg in ((-1, 0, ((0, 0), (1, 0))), (1, 0, ((0, 1), (1, 1))),
                                        (0, -1, ((0, 0), (0, 1))), (0, 1, ((1, 0), (1, 1)))):
                        yy, xx = y + dy, x + dx
                        if 0 <= yy < hh and 0 <= xx < ww and z[yy, xx]:
                            continue
                        (a0, b0), (a1, b1) = seg
                        d.line([((x + a0) * FZ, (y + b0) * FZ), ((x + a1) * FZ, (y + b1) * FZ)],
                               fill=(0, 225, 255), width=2)
        else:
            bx0, by0, bx1, by1 = (x0 - X0) * FZ, (y0 - Y0) * FZ, (x1 - X0) * FZ, (y1 - Y0) * FZ
            for (p0, p1) in (((bx0, by0), (bx1, by0)), ((bx1, by0), (bx1, by1)), ((bx1, by1), (bx0, by1)),
                             ((bx0, by1), (bx0, by0))):
                n_ = max(1, int(np.hypot(p1[0] - p0[0], p1[1] - p0[1]) // 8))
                for k in range(0, n_, 2):
                    t0, t1 = k / n_, min(1.0, (k + 1) / n_)
                    d.line([(p0[0] + (p1[0] - p0[0]) * t0, p0[1] + (p1[1] - p0[1]) * t0),
                            (p0[0] + (p1[0] - p0[0]) * t1, p0[1] + (p1[1] - p0[1]) * t1)], fill=(255, 220, 40), width=2)
        sides.append(im)
    f = wp.font(20)
    sh = Image.new("RGB", (sides[0].width * 2 + 24, sides[0].height + 34), (28, 30, 34))
    sh.paste(sides[0], (0, 34))
    sh.paste(sides[1], (sides[0].width + 24, 34))
    d = ImageDraw.Draw(sh)
    d.text((4, 6), "ORIGINAL", fill=(230, 230, 230), font=f)
    d.text((sides[0].width + 28, 6), "HD REDRAW", fill=(230, 230, 230), font=f)
    return sh


def frag_task(ms, t, part=None, kind=""):
    card = wp.cards().get(ms, {})
    w2 = wp.what2().get(ms, {})
    desc = "Identity: %s." % w2.get("identity", "-")
    v = {"name": card.get("en", t), "desc": desc, "part": part or "", "kind": kind}
    return (FRAG_PART if part else FRAG_BOX) % v


def frag_key(ms, q):
    return "%s.%s" % (ms, q.replace(" ", "_").replace("/", "_"))


def run_frag(reqs, tag, runs=3, jobs=4, effort="medium"):
    """reqs: (ключ, мастер, тип, ответ RGBA на канвасе FZ, деталь | None, рамка | None). Готовые не переспрашиваются;
    первые ответы сохраняются как есть."""
    dst = os.path.join(ROOT, OUT, tag, FRAG)
    os.makedirs(os.path.join(dst, "in"), exist_ok=True)
    jobs_l = []
    for key, ms, t, ans_z, part, box in reqs:
        rgb_o, m_o = wf.original(t)
        spec = wp.load_parts(ms)
        lab = wp.part_labels(spec, m_o, wp.to_lab(rgb_o))[0]
        names = [p["name"] for p in spec["parts"]]
        img = os.path.join(dst, "in", key + ".png")
        if part is not None:
            i = [n.lower() for n in names].index(part.lower())
            frag_sheet(rgb_o, m_o, ans_z, lab=lab, i=i).save(img)
            task = frag_task(ms, t, names[i], spec["parts"][i].get("kind", ""))
        else:
            frag_sheet(rgb_o, m_o, ans_z, box=box).save(img)
            task = frag_task(ms, t)
        with open(os.path.join(dst, "in", key + ".task.txt"), "w", encoding="utf-8") as fo:
            fo.write(task)
        for k in range(1, runs + 1):
            last = os.path.join(dst, "%s.r%d.json" % (key, k))
            if not os.path.exists(last):
                jobs_l.append((key, k, [img], task, last))
    print("заданий крупного фрагмента: %d (%s)" % (len(jobs_l), dst), flush=True)

    def one(j):
        key, k, imgs, task, last = j
        ans, rc, sec, got = ask(imgs, task, last, last[:-5] + ".log", effort, FRAG_SCHEMA)
        print("%s r%d: код %d, %.0f с, задание целиком %s, ответ %s" % (
            key, k, rc, sec, "да" if got else "НЕТ", (ans or {}).get("status", "НЕТ")), flush=True)
    with cf.ThreadPoolExecutor(jobs) as ex:
        list(ex.map(one, jobs_l))


def frag_vote(tag, key, runs=3):
    """Голоса фрагмента от запланированного числа оценок: SAME / DIFFERENT большинством, иначе UNRESOLVED."""
    got = []
    for k in range(1, runs + 1):
        p = os.path.join(ROOT, OUT, tag, FRAG, "%s.r%d.json" % (key, k))
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fo:
                got.append(json.load(fo))
    need = runs // 2 + 1
    st = [a["status"] for a in got]
    res = next((s for s in ("SAME", "DIFFERENT") if st.count(s) >= need), "UNRESOLVED")
    return {"result": res, "votes": st, "diff": [a["differences"] for a in got], "notes": [a["note"] for a in got]}


# ------------------------------------------------------------------------------------------------ свод

def decide_one(ms, rep, draw, judges, tag=None, runs=3):
    """Три итога и решение. rep - weapon_parts check()[ms] (с construction.proven/label_sensitive), draw - (вердикт,
    почему), judges - ответы повторных оценок. tag=None - только план: какие фрагменты нужны (out['frag_needed']).
    Вопрос снимается ТОЛЬКО явным большинством OK (SAME у фрагмента); UNSURE, пропуск, нет большинства - не решён."""
    con = rep["construction"]
    names = [r["part"] for r in rep["raw"]["parts"]]
    lower = {n.lower(): n for n in names}
    vt = vote(judges, names, runs)
    need = vt["need"]
    out = {"master": ms, "type": rep["type"], "human": [], "frag_needed": [],
           "judges": {"answers": vt["n"], "planned": vt["n_plan"], "completeness": vt["completeness"]}}
    if vt["n"] < vt["n_plan"]:
        out["human"].append("оценок судьи %d из %d" % (vt["n"], vt["n_plan"]))
    # рисунок
    dv, dwhy = draw
    jdraw = [a["drawing"] for a in judges]
    if dv == "GREY":
        dv2 = {"GOOD": "PASS", "BAD": "FAIL"}.get(vt["drawing"], "HUMAN")
        if dv2 == "HUMAN":
            out["human"].append("рисунок: серая зона (%s), нет большинства GOOD: %s" % ("; ".join(dwhy), "/".join(jdraw)))
    elif dv == "PASS" and vt["drawing"] == "BAD":
        dv2 = "HUMAN"
        out["human"].append("рисунок: мерка PASS, большинство оценок BAD (%s)" % "; ".join(
            sum([a["drawing_defects"] for a in judges], [])[:3]))
    else:
        dv2 = dv
    out["drawing"] = {"auto": dv, "why": dwhy, "judges": jdraw, "verdict": dv2}
    # конструкция: надёжные нарушения стоят сами
    proven = con.get("proven", [])
    qs = {}

    def addq(part, kind, why, fr):
        e = qs.setdefault(part.lower(), {"part": lower.get(part.lower(), part), "kinds": [], "why": [], "frag": False})
        e["kinds"].append(kind)
        e["why"].append(why)
        e["frag"] = e["frag"] or fr
    for r in rep["raw"]["parts"]:
        if r["verdict"] == "REVIEW":
            addq(r["part"], "MEASURE_REVIEW", "; ".join(r.get("why", [])), False)
    for s in con.get("label_sensitive", []):
        # FAIL детали, зависящий от разметки: общий вид таких расхождений не различает (13 из 21 acc1) - фрагмент
        addq(s["part"], "MEASURE_FAIL_LABEL", "%s | разметка: %s%s" % (
            s["why"], ", ".join("%s %s" % kv for kv in s["variants"].items()) or "-",
            ("; " + "; ".join(s["doubt"])) if s["doubt"] else ""), True)
    boxes = []
    for q in con["questions"]:
        if q["kind"] == "EXTRA":
            boxes.append(q)
        else:
            for p in q.get("parts", []):
                addq(p, q["kind"], q["what"], False)
    for p in sorted(vt["major"]):
        if p not in qs:
            addq(lower.get(p, p), "JUDGES_DEFECT", vt["notes"].get(p, ""), True)
    confirmed, rows = [], []
    for k, e in sorted(qs.items()):
        v = vt["votes"].get(k, [])
        okc, dfc = v.count("OK"), v.count("DEFECT")
        row = {"part": e["part"], "kinds": e["kinds"], "why": e["why"], "judges": v, "frag": None}
        if dfc >= need and "JUDGES_DEFECT" not in e["kinds"]:
            row["result"] = "CONFIRMED_BY_JUDGES"
        elif okc >= need and not e["frag"]:
            row["result"] = "RESOLVED_BY_JUDGES"
        else:
            row["need_frag"] = True
        rows.append(row)
    for q in boxes:
        x, y = q["box"][0], q["box"][1]          # рамка weapon_parts: x0, y0, x1, y1 включительно
        w_, h_ = q["box"][2] - x + 1, q["box"][3] - y + 1
        ex = [bool(a["extra"]) for a in judges]
        row = {"part": "", "box": [int(x), int(y), int(w_), int(h_)], "kinds": ["EXTRA"], "why": [q["what"]],
               "judges": ["ADDED" if e_ else "NONE_ADDED" for e_ in ex], "frag": None}
        if vt["no_extra"]:
            row["result"] = "RESOLVED_BY_JUDGES"
        else:
            row["need_frag"] = True
        rows.append(row)
    if vt["extra"] and not boxes:
        out["human"].append("конструкция: большинство оценок видит лишнее, а мерка лишнего не нашла: %s" % "; ".join(
            e["what"] for a in judges for e in a["extra"][:1]))
    if vt["same"] != "YES":
        out["human"].append("тот же предмет: нет большинства YES (%s)" % "/".join(a["same_weapon"] for a in judges))
    early = bool(proven) or dv2 == "FAIL" or any(r.get("result") == "CONFIRMED_BY_JUDGES" for r in rows)
    for r in rows:
        if not r.get("need_frag"):
            continue
        key = frag_key(ms, r["part"] or "box_%d_%d" % (r["box"][0], r["box"][1]))
        if early:
            r["result"] = "NOT_CHECKED"          # предмет уже на перерисовке по надёжному нарушению
            continue
        if tag is None:
            out["frag_needed"].append((key, r["part"] or None, r.get("box")))
            r["result"] = "PENDING"
            continue
        fv = frag_vote(tag, key, runs)
        r["frag"] = fv
        if fv["result"] == "DIFFERENT":
            r["result"] = "CONFIRMED_BY_FRAGMENT"
        elif fv["result"] == "SAME" and FRAG_SAME_RESOLVES:
            r["result"] = "RESOLVED_BY_FRAGMENT"
        else:
            r["result"] = "UNRESOLVED"
            out["human"].append("%s: не решено ни оценками, ни фрагментом (оценки %s, фрагмент %s%s)" % (
                r["part"] or "лишнее у %s" % r["box"][:2], "/".join(r["judges"]), "/".join(fv["votes"]) or "нет",
                "; SAME фрагмента вопрос не снимает" if fv["result"] == "SAME" else ""))
    for r in rows:
        if r.get("result", "").startswith("CONFIRMED"):
            confirmed.append(r["part"] or "лишнее у %d,%d" % tuple(r["box"][:2]))
    cv2 = "FAIL" if proven or confirmed else ("PENDING" if any(r.get("result") == "PENDING" for r in rows)
                                             else ("HUMAN" if any(r.get("result") == "UNRESOLVED" for r in rows)
                                                   else "PASS"))
    out["construction"] = {"measures": con.get("measures_verdict", con["verdict"]), "verdict": cv2,
                           "proven": proven, "confirmed": confirmed, "questions": rows,
                           "why": list(con["why"])}
    pl = rep["placement"]
    out["placement"] = pl
    if dv2 == "FAIL" or cv2 == "FAIL":
        dec = "REDRAW"
    elif cv2 == "PENDING":
        dec = "PENDING"
    elif out["human"] or cv2 == "HUMAN" or dv2 == "HUMAN":
        dec = "DEFERRED"
    elif pl["verdict"] == "FAIL":
        dec = "PLACEMENT_FIX"
    elif pl["verdict"] == "DECISION_WIDE":
        dec = "CANDIDATE_PLACEMENT_OPEN"
    else:
        dec = "CANDIDATE"
    out["decision"] = dec
    return out


DECISION_RU = {"CANDIDATE": "автоматически принятый кандидат",
               "CANDIDATE_PLACEMENT_OPEN": "кандидат, размещение не решено (.wide не предполагается)",
               "PLACEMENT_FIX": "рисунок и конструкция годны, исправлять размещение",
               "REDRAW": "перерисовать", "DEFERRED": "спорный, отложен человеку", "PENDING": "ждёт фрагмента"}


def decide(parts_files, tag, runs=3, frag=True, jobs=4):
    """Свод по отчётам weapon_parts (parts_*.json; позднее перекрывает раннее) и ответам судьи тега tag: план ->
    крупные фрагменты для нерешённого -> итог."""
    import weapon_accept as wa
    reps = {}
    for p in parts_files:
        with open(p, encoding=ENC) as fo:
            reps.update(json.load(fo))
    for ms, r in reps.items():
        if "proven" not in r["construction"]:
            raise SystemExit("%s: отчёт мерок без proven/label_sensitive - пересчитать weapon_parts check" % ms)
    cuts = {os.path.dirname(os.path.dirname(os.path.abspath(p))) for p in parts_files}
    items = []
    for ms in sorted(reps):
        rep = reps[ms]
        meta = None
        for c in cuts:
            mp = os.path.join(c, "meta", rep["type"] + ".json")
            if os.path.exists(mp):
                with open(mp, encoding=ENC) as fo:
                    meta = json.load(fo)
        _rgb, m_o = wf.original(rep["type"])
        mt = wa.drawing_metrics(meta["ref"], m_o)
        dv, dwhy, blocky = wa.drawing_verdict(mt)
        items.append((ms, rep, meta, m_o, mt, (dv, dwhy), blocky))
    reqs = []
    for ms, rep, meta, m_o, mt, draw, blocky in items:
        plan = decide_one(ms, rep, draw, load(tag, ms, runs), None, runs)
        if plan["frag_needed"]:
            ans_z = placed_answer(meta["ref"], m_o, FZ)
            reqs += [(key, ms, rep["type"], ans_z, part, box) for key, part, box in plan["frag_needed"]]
    if reqs and frag:
        run_frag(reqs, tag, runs, jobs)
    rows = []
    for ms, rep, meta, m_o, mt, draw, blocky in items:
        out = decide_one(ms, rep, draw, load(tag, ms, runs), tag if frag else None, runs)
        out["drawing"]["metrics"] = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in mt.items()}
        out["drawing"]["blocky"] = round(blocky, 2)
        out["ref"] = meta["ref"]
        rows.append(out)
        qtxt = "; ".join("%s %s" % (q["part"] or "лишнее", q["result"]) for q in out["construction"]["questions"])
        print("%s %-22s рисунок %-5s(%s) | конструкция %-7s(мерки %s, надёжных %d) | размещение %-13s | %s%s%s" % (
            ms, rep["type"], out["drawing"]["verdict"], out["drawing"]["auto"], out["construction"]["verdict"],
            out["construction"]["measures"], len(out["construction"]["proven"]), out["placement"]["verdict"],
            out["decision"], ("\n      вопросы: " + qtxt) if qtxt else "",
            ("\n      <- " + "; ".join(out["human"])) if out["human"] else ""))
    from collections import Counter
    print("итог:", dict(Counter(r["decision"] for r in rows)))
    dst = os.path.join(ROOT, OUT, tag)
    with open(os.path.join(dst, "decide.json"), "w", encoding=ENC) as fo:
        json.dump(rows, fo, ensure_ascii=False, indent=1)
    return rows


# (мастер, деталь | None, вариант исполнения, дефект | None, рамка лишнего | None, ожидание SAME / DIFFERENT)
# Дефекты на 1-2 пикселя спрайта - как раз то, чего общий вид не различает (13 FAIL acc1 по одним меркам);
# клинок W-079 - деталь с сомнительной разметкой (цвет больстера), FAIL по ней уходит именно сюда.
FRAG_CONTROLS = [(m, p, v, None, None, "SAME") for m, ps in (
                     ("W-015", ("barrel", "stock")), ("W-059", ("barrel", "magazine")),
                     ("W-036", ("barrel", "grip")), ("W-079", ("blade", "handle"))) for p in ps for v in ("all", "clean")] + [
                 ("W-079", "blade", "all", ("narrow", 0, 5), None, "DIFFERENT"),
                 ("W-079", "blade", "all", ("narrow", 12, 18), None, "DIFFERENT"),
                 ("W-059", "barrel", "all", ("trim_top", 2), None, "DIFFERENT"),
                 ("W-059", "magazine", "all", ("shift", 2, 0), None, "DIFFERENT"),
                 ("W-015", "stock", "all", ("shift", 2, 0), None, "DIFFERENT"),
                 ("W-015", "magazine", "all", ("shift", 0, 2), None, "DIFFERENT"),
                 ("W-081", "handle", "all", ("shift", 0, 2), None, "DIFFERENT"),
                 ("W-036", "barrel", "all", ("trim_top", 2), None, "DIFFERENT"),
                 ("W-072", None, "all", ("add", 14, 8, 3, 4), (14, 8, 3, 4), "DIFFERENT"),
                 ("W-072", None, "all", None, (14, 8, 3, 4), "SAME")]


def frag_controls(tag, runs=3, jobs=4):
    """Контроли крупного фрагмента до работы на партии: допустимое исполнение - SAME большинством, дефект в 1-2
    пикселя спрайта и добавленный кусок - DIFFERENT большинством. UNRESOLVED - промах (человеку ушло бы лишнее)."""
    import weapon_accept as wa
    L = wf.list_rows()
    reqs, want = [], {}
    for ms, part, kind, how, box, exp in FRAG_CONTROLS:
        t = L[ms]["type"]
        rgb_o, m_o = wf.original(t)
        spec = wp.load_parts(ms)
        r2, m2 = (rgb_o, m_o) if how is None else wa.edit(rgb_o, m_o, spec, part, how)
        v = wa.variant(r2, m2, kind, 0)               # k=4
        z = Image.fromarray(v).resize((v.shape[1] * FZ // 4, v.shape[0] * FZ // 4), Image.BICUBIC)
        key = "fctl_%s_%s_%s_%s" % (ms, part or "box", kind, "ok" if how is None else "_".join(map(str, how)))
        reqs.append((key, ms, t, np.asarray(z), part, box))
        want[key] = exp
    run_frag(reqs, tag, runs, jobs)
    good = false_diff = caught = n_def = 0
    for key, exp in want.items():
        fv = frag_vote(tag, key, runs)
        ok = fv["result"] == exp
        good += ok
        false_diff += exp == "SAME" and fv["result"] == "DIFFERENT"
        n_def += exp == "DIFFERENT"
        caught += exp == "DIFFERENT" and fv["result"] == "DIFFERENT"
        print("%-52s ждали %-9s вышло %-10s %-6s %s" % (key, exp, fv["result"], "OK" if ok else "ПРОМАХ",
                                                         "/".join(fv["votes"])))
    print("контроли фрагмента большинством: верно %d из %d" % (good, len(want)))
    # роль фрагмента - только подтвердить дефект (FRAG_SAME_RESOLVES): годен, пока нет ложного DIFFERENT;
    # пропущенный дефект уходит человеку, а не в приём
    print("ложных DIFFERENT на допустимом: %d из %d; дефектов подтверждено: %d из %d (остальные - человеку)" % (
        false_diff, len(want) - n_def, caught, n_def))
    return false_diff == 0


# ------------------------------------------------------------------------------------------------ заморозка

FROZEN = ["tools/hdart/weapon_judge.py", "tools/hdart/weapon_parts.py", "tools/hdart/weapon_accept.py",
          "tools/hdart/weapon_fit.py", "tools/hdart/weapon_from_ref.py", "tools/hdart/weapons_chatgpt.py"]
FREEZE = "art/items/weapons-chatgpt-v2/judge/freeze_%s.json"


def _sha(path):
    import hashlib
    with open(path, "rb") as fo:
        return hashlib.sha256(fo.read()).hexdigest()


def fingerprint():
    """Версия проверки: sha256 кода и текстов заданий (общий вид, фрагмент части и лишнего, схемы)."""
    import hashlib
    h = lambda s: hashlib.sha256(s.encode("utf-8")).hexdigest()  # noqa: E731
    return {"code": {p: _sha(os.path.join(ROOT, p)) for p in FROZEN},
            "prompts": {"TASK": h(TASK), "FRAG_PART": h(FRAG_PART), "FRAG_BOX": h(FRAG_BOX),
                        "SCHEMA": h(json.dumps(SCHEMA, sort_keys=True)),
                        "FRAG_SCHEMA": h(json.dumps(FRAG_SCHEMA, sort_keys=True))},
            "numbers": {"JZ": JZ, "FZ": FZ, "FRAG_PAD": FRAG_PAD}}


def freeze(version):
    p = os.path.join(ROOT, FREEZE % version)
    if os.path.exists(p):
        raise SystemExit("%s уже есть - версия заморожена, новую называть другим именем" % p)
    fp = fingerprint()
    fp["version"] = version
    fp["time"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(p, "w", encoding=ENC) as fo:
        json.dump(fp, fo, ensure_ascii=False, indent=1)
    print("заморожено: %s" % p)


def check_frozen(version):
    """Код и задания обязаны совпадать с замороженной версией: пороги по ходу партии не меняются."""
    if not version:
        return
    p = os.path.join(ROOT, FREEZE % version)
    with open(p, encoding=ENC) as fo:
        fr = json.load(fo)
    fp = fingerprint()
    diff = [k for k in fr["code"] if fr["code"][k] != fp["code"].get(k)] + \
           [k for k in fr["prompts"] if fr["prompts"][k] != fp["prompts"].get(k)] + \
           [k for k in fr["numbers"] if fr["numbers"][k] != fp["numbers"].get(k)]
    if diff:
        raise SystemExit("версия %s изменена после заморозки: %s" % (version, ", ".join(diff)))
    print("версия %s: код и задания совпадают с заморозкой %s" % (version, fr["time"]))


def sheet(tag):
    """Лист разногласий: только предметы, которые ушли человеку (decide.json), - пара оригинал|ответ и причины."""
    import textwrap
    from PIL import ImageFont
    dst = os.path.join(ROOT, OUT, tag)
    with open(os.path.join(dst, "decide.json"), encoding=ENC) as fo:
        rows = [r for r in json.load(fo) if r["decision"] == "DEFERRED"]
    if not rows:
        print("разногласий нет - лист не нужен")
        return None
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 18)
    W, tiles = 1400, []
    for r in rows:
        pair = Image.open(os.path.join(dst, "in", r["master"] + ".pair.png")).convert("RGB")
        s_ = min(1.0, (W - 20) / pair.width, 420.0 / pair.height)
        pair = pair.resize((int(pair.width * s_), int(pair.height * s_)), Image.LANCZOS)
        lines = ["%s %s - рисунок %s, конструкция %s, размещение %s" % (
            r["master"], r["type"], r["drawing"]["verdict"], r["construction"]["verdict"],
            r["placement"]["verdict"])]
        for h in r["human"]:
            lines += textwrap.wrap(h, 140)
        th = 24 * len(lines) + 10
        t = Image.new("RGB", (W, pair.height + th + 20), (32, 32, 36))
        d = ImageDraw.Draw(t)
        for i, ln in enumerate(lines):
            d.text((10, 6 + 24 * i), ln, fill=(240, 240, 240) if i == 0 else (255, 200, 120), font=font)
        t.paste(pair, (10, th + 10))
        tiles.append(t)
    out = Image.new("RGB", (W, sum(t.height for t in tiles)), (32, 32, 36))
    y = 0
    for t in tiles:
        out.paste(t, (0, y))
        y += t.height
    p = os.path.join(dst, "disagreements.png")
    out.save(p)
    print("лист разногласий: %d предметов -> %s" % (len(rows), p))
    return p


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "controls", "frag-controls", "decide", "sheet", "freeze"])
    ap.add_argument("--only", default="")
    ap.add_argument("--cut", action="append", default=[])
    ap.add_argument("--parts", action="append", default=[])
    ap.add_argument("--tag", default="")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--no-frag", action="store_true", help="decide без крупного фрагмента (нерешённое - PENDING)")
    ap.add_argument("--version", default="", help="замороженная версия проверки: код и задания обязаны совпасть")
    a = ap.parse_args()
    os.chdir(ROOT)
    if a.cmd == "freeze":
        freeze(a.version or ap.error("freeze: нужен --version"))
        return
    if not a.tag:
        ap.error("нужен --tag")
    check_frozen(a.version)
    if a.cmd == "frag-controls":
        frag_controls(a.tag, a.runs, a.jobs)
        return
    if a.cmd == "decide":
        decide(a.parts, a.tag, a.runs, not a.no_frag, a.jobs)
        sheet(a.tag)
        return
    if a.cmd == "sheet":
        sheet(a.tag)
        return
    if a.cmd == "controls":
        controls(a.tag, a.cut or ["art/items/weapons-chatgpt-v2/cut20", "art/items/weapons-chatgpt-v2/cut3"],
                 a.runs, a.jobs)
        return
    L = wf.list_rows()
    items = []
    for ms in [x for x in a.only.split(",") if x]:
        t = L[ms]["type"]
        meta = None
        for c in a.cut:
            mp = os.path.join(c, "meta", t + ".json")
            if os.path.exists(mp):
                with open(mp, encoding=ENC) as fo:
                    meta = json.load(fo)
        if meta is None:
            print("%s: нет нарезки в %s" % (ms, a.cut))
            continue
        _rgb, m_o = wf.original(t)
        items.append((ms, ms, t, placed_answer(meta["ref"], m_o), meta["ref"]))
    run_items(items, a.tag, a.runs, a.jobs)


if __name__ == "__main__":
    main()
