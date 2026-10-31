#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""RESTORE_V1B - перепрогон двух кадров RESTORE_V1 по вердикту специалиста (03.10, передал Vitali в чате).

RESTORE_V1: PASS 5, FAIL MOUNTSNOW2:16 (сине-фиолетовая кайма по контуру), REVIEW XB3BITZ1:26 (плафоны похожи
на цилиндры). Против restore_probe_v1 меняется только это:
  - кадры: только MOUNTSNOW2:16 и XB3BITZ1:26 (ONLY), задания и зёрна те же (run1/jobs.json);
  - промпт: RESTORE плюс жёсткий запрет каймы (HALO_BAN) - край предмета только своими цветами, цвет подложки
    в предмет не заходит, и в тонкие ветки тоже;
  - негатив: NEG_ADD плюс кайма, ореол, цветной контур, контровой свет (HALO_NEG). «glow» не запрещается:
    плафоны XB3 светятся по описанию;
  - описание XB3BITZ1:26 - по форме, формулировка специалиста (restore-v1b/descriptions.tsv);
    MOUNTSNOW2:16 - то же, что в RESTORE_V1.
Отчёт сравнивает с restore-v1 (не с run1); ворота asset_fidelity с EDGE_COLOR_HALO.

Модель - только через очередь (gpu_scripts.txt):
    py -3.13 tools/gpuq.py add --name restore_v1b --cwd E:/OpenXCom -- \
        E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/render_chunks.py \
        --out art/objects/generation/probes/restore-v1b -- \
        E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe tools/hdart/restore_probe_v1b.py render
Без модели (GPUQ_BYPASS=1): prompts, report.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import restore_probe_v1 as rp       # noqa: E402

HALO_BAN = ("The edges of the object carry only the object's own colours: no coloured outline, no halo, "
            "no rim light, no colour fringe around the object. The panel colour never bleeds into the object, "
            "not even into thin parts and thin branches. ")
HALO_NEG = ", colour fringe, halo, coloured outline, rim light, colour bleeding, blue edges, purple edges"
ANCHOR = "Output one isolated object on the same flat panel."

if ANCHOR not in rp.RESTORE:
    raise SystemExit("в restore_probe_v1.RESTORE нет %r - текст изменился" % ANCHOR)
rp.RESTORE = rp.RESTORE.replace(ANCHOR, HALO_BAN + ANCHOR)
rp.NEG_ADD = rp.NEG_ADD + HALO_NEG
rp.OUT = rp.PROBES + "/restore-v1b"
rp.ONLY = {"MOUNTSNOW2:16", "XB3BITZ1:26"}
rp.PREV, rp.PREV_PREFIX, rp.PREV_LABEL = rp.PROBES + "/restore-v1", "restore_", "restore-v1"
rp.PROBE = "RESTORE_V1B"

if __name__ == "__main__":
    rp.main()
