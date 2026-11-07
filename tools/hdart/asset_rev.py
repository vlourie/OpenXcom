#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Входы ассета и их ревизии: когда готовый HD-кадр устарел (Pipeline v2, разделы 15, 36; P1-A).

Одна общая ревизия семейства не ловит главное: Vitali сказал не «стул», а «пивной кран» - семейство то же,
а картинка уже неверна. Поэтому у выхода записываются ВСЕ входы, от которых он зависит, по отдельности:
  family_rev           - content_hash семейства (состав, связи, решения человека);
  identity_rev         - опознание ассета (статус и текст из asset_identity.tsv);
  canonical_source_rev - оригиналы канонического кадра (хэши census/frame_hash.tsv по кускам);
  member_source_rev    - оригиналы самого члена (для выведенного: перекраска считается от его оригинала);
  generator_rev        - генератор: модель, LoRA, шаги, разрешение, движок (obj_gen_spec.generator_rev);
  prompt_rev           - шаблон промпта генератора (P1-B: правка шаблона без смены модели - тоже STALE);
  derive_rev           - версия алгоритма вывода (obj_derive.DERIVE_VERSION).
input_hash - хэш всего набора. Изменился любой вход - выход STALE, и stale() называет, какой.

    py -3.13 tools/hdart/asset_rev.py FRNITURE:8      (входы ассета сейчас)
"""
import csv
import hashlib
import json
import os

ENC = "utf-8-sig"
FRAME_HASH = os.path.join("census", "frame_hash.tsv")
IDENTITY = os.path.join("art", "objects", "discovery", "asset_identity.tsv")
FIELDS = ("family_rev", "identity_rev", "canonical_source_rev", "member_source_rev", "generator_rev", "prompt_rev",
          "derive_rev")


def h12(obj):
    s = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:12]


def frame_hashes(path=FRAME_HASH):
    out = {}
    with open(path, encoding=ENC, newline="") as f:
        for r in csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            if len(r) >= 3 and r[1].isdigit():
                out[(r[0].upper(), int(r[1]))] = r[2]
    return out


def src_rev(keys, fh):
    """Ревизия оригиналов: хэши кусков по порядку; кадра нет в переписи - 'missing' (тоже вход)."""
    got = []
    for k in keys:
        s, f = k.split(":")
        got.append(fh.get((s.upper(), int(f)), "missing"))
    return h12(got)


def identity_rev(row):
    return h12([row.get("status", ""), row.get("identity", "")]) if row else h12(["NONE", ""])


def generator_rev(name, params=None):
    """Модель и её настройки; шаблон промпта - отдельно, prompt_rev."""
    return h12([name, params or {}])


def prompt_rev(template):
    return h12(template) if template else ""


def inputs(family=None, identity=None, canonical_src=(), member_src=(), fh=None, generator=None, derive=None,
           prompt=None):
    """Словарь входов; пустые компоненты тоже пишутся - чтобы появление входа было заметно."""
    fh = fh if fh is not None else {}
    return {"family_rev": family["content_hash"] if family else "",
            "identity_rev": identity_rev(identity),
            "canonical_source_rev": src_rev(canonical_src, fh) if canonical_src else "",
            "member_source_rev": src_rev(member_src, fh) if member_src else "",
            "generator_rev": generator or "",
            "prompt_rev": prompt or "",
            "derive_rev": derive or ""}


def input_hash(inp):
    return h12({k: inp.get(k, "") for k in FIELDS})


def stale(recorded, current):
    """Какие входы разошлись; [] - выход свежий. Нет записи входов вовсе - ['no_inputs']."""
    if not recorded:
        return ["no_inputs"]
    return [k for k in FIELDS if recorded.get(k, "") != current.get(k, "")]


def read_identity(path=IDENTITY):
    out = {}
    if os.path.exists(path):
        with open(path, encoding=ENC, newline="") as f:
            for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
                out[r["asset_id"]] = r
    return out


if __name__ == "__main__":
    import sys
    fh = frame_hashes()
    ident = read_identity()
    fams = {}
    p = os.path.join("art", "objects", "families", "families.json")
    if os.path.exists(p):
        with open(p, encoding=ENC) as f:
            fams = {fm["family_id"]: fm for fm in json.load(f)}
    for k in sys.argv[1:]:
        k = k.upper()
        fm = fams.get(k)
        src = fm["members"][0]["src"] if fm else [k]
        inp = inputs(fm, ident.get(k), src, (), fh)
        print(k, json.dumps(inp, ensure_ascii=False), "input_hash", input_hash(inp))
