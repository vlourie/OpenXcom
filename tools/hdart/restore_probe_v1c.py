#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""RESTORE_V1C - один кадр MOUNTSNOW2:16 на нейтральной подложке (специалист 03.10, передал Vitali в чате).

RESTORE_V1B: XB3BITZ1:26 PASS, MOUNTSNOW2:16 FAIL - синяя кайма по тонким веткам осталась (EDGE_COLOR_HALO 0.368),
синяя подложка уехала во всех трёх попытках. Против RESTORE_V1B меняется только подложка:
  - кадр: только MOUNTSNOW2:16 (ONLY), задание и зерно те же (run1/jobs.json), попытки с тем же сдвигом зерна;
  - подложка: только PANEL (нейтральная средне-серая photo_base grey_mid, без синего и фиолетового уклона)
    во всех попытках - список подложек из одной, RERENDER не уводит на цветную;
  - промпт по содержанию, запрет каймы, негатив, модель, шаги - как в RESTORE_V1B (restore_probe_v1b);
    фраза о цвете подложки в промпте называет серую - это и есть смена подложки;
  - описание - то же (restore-v1c/descriptions.tsv - строка MOUNTSNOW2:16 из restore-v1b).
Отчёт сравнивает с restore-v1b. Успех: EDGE_COLOR_HALO < 0.05 PASS, 0.05-0.15 REVIEW, от 0.15 FAIL; глазами - снег
белый, ветки тёмно-красно-коричневые, нет серой и цветной каймы, форма куста та же.

Модель - только через очередь (gpu_scripts.txt):
    py -3.13 tools/gpuq.py add --name restore_v1c --cwd E:/OpenXCom -- \
        E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/render_chunks.py \
        --out art/objects/generation/probes/restore-v1c -- \
        E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/restore_probe_v1c.py render
Без модели (GPUQ_BYPASS=1): prompts, report.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import restore_probe_v1b    # noqa: E402,F401  запрет каймы в промпте и негативе - как в RESTORE_V1B
import restore_probe_v1 as rp       # noqa: E402
import photo_base as pb             # noqa: E402
import photo_render as pr           # noqa: E402

PANEL = "grey_mid"
_panels = pr.panels_by_margin


def panels_neutral(frame):
    """Только нейтральная средне-серая подложка, запас тела - как считает photo_render."""
    p = [x for x in _panels(frame) if x[0] == PANEL]
    if len(p) != 1 or PANEL not in dict(pb.PANELS):
        raise SystemExit("подложки %s нет в photo_base.PANELS - список изменился" % PANEL)
    return p


pr.panels_by_margin = panels_neutral        # только в этом процессе; photo_render.py не правится
rp.OUT = rp.PROBES + "/restore-v1c"
rp.ONLY = {"MOUNTSNOW2:16"}
rp.PREV, rp.PREV_PREFIX, rp.PREV_LABEL = rp.PROBES + "/restore-v1b", "restore_", "restore-v1b"
rp.PROBE = "RESTORE_V1C"

if __name__ == "__main__":
    rp.main()
