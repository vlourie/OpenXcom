#!/usr/bin/env python3
"""Общее для скриптов замера стенда: корень репозитория, папка результатов, nm из тулчейна.

Аудит скорости стенда 30.09.2026 - docs/research/ai-sim-speed-audit-2026-09-30.md."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # E:\OpenXCom
HERE = Path(__file__).resolve().parent               # tools\ai_speed
OUT = HERE / "runs"                                  # итоги прогонов <имя>.json (в гит не идут)
ENC_W = "utf-8-sig"                                  # R-001: всё своё - со спецификацией
ENC_R = "utf-8-sig"


def nm_exe():
    """nm.exe из тулчейна по tools/build/build_config.json (MsysBin), R-002."""
    cfg = json.loads((ROOT / "tools" / "build" / "build_config.json").read_text(encoding=ENC_R))
    p = Path(cfg.get("MsysBin") or "C:/msys64/mingw64/bin") / "nm.exe"
    if not p.is_file():
        sys.exit(f"нет nm.exe: {p} (MsysBin в tools/build/build_config.json)")
    return str(p)


def build_dir(build):
    """Каталог сборки: имя вида build-ai36 - от корня репозитория, абсолютный путь - как есть."""
    b = Path(build)
    return b if b.is_absolute() else ROOT / build


def build_exe(build):
    """Файл игры этой сборки - для nm и grep -a по строкам; запускает игру только ai_probe (скрыто, R-124)."""
    return build_dir(build) / "bin" / "openxcom.exe"


def probe_work():
    """Рабочая папка проб стенда (ai_probe.WORK), чтобы не дублировать путь."""
    sys.path.insert(0, str(ROOT / "tools"))
    import ai_probe
    return ai_probe.WORK
