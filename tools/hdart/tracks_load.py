# -*- coding: utf-8 -*-
"""Загрузка брони из рулсетов мода (только чтение): тип -> поля, с refNode как в движке (родитель слабее)."""
import yaml
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MOD = ROOT / "Пиратки" / "Dioxine_XPiratez" / "user" / "mods" / "Piratez"
LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


def merged(node):
    """refNode: поля узла-родителя берутся, если у самого узла их нет (рекурсивно)."""
    ref = node.get("refNode")
    if isinstance(ref, dict):
        base = merged(ref)
        base.update({k: v for k, v in node.items() if k != "refNode"})
        return base
    return dict(node)


def load_armors(mod=MOD):
    arm = {}
    for f in sorted((mod / "Ruleset").glob("*.rul")):
        text = f.read_text(encoding="utf-8-sig")
        if "armors:" not in text:
            continue
        data = yaml.load(text, Loader=LOADER) or {}
        for x in data.get("armors") or []:
            if isinstance(x, dict) and "type" in x:
                arm.setdefault(x["type"], {}).update(merged(x))
    return arm


def load_names(mod=MOD, lang="en-US"):
    p = mod / "Language" / (lang + ".yml")
    d = yaml.load(p.read_text(encoding="utf-8-sig"), Loader=LOADER) or {}
    return (d.get(lang) or next(iter(d.values()))) if d else {}
