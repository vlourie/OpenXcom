"""XP-000531: кошачьи морды у шести внешностей NEKOMIMI (F3, F7, F17, M5, M11, M23), варианты для страницы выбора.
Тот же doll_neko_heads.py с полем muzzle в doll_looks_nekomimi.json, но выход в art/_review/xp531_v1/<вариант>/heads, пак и слои мода не трогает.
Вариант - --variant A (или XP531_VARIANT), сдвиг сида - --shift 0 (A - 0, B - 1000); у перегенерации свой вариант и свой сдвиг.

  py -3.13 tools/gpuq.py add --name doll_neko_heads_531 -- E:/OpenXCom/tools/hdart/.venv-qwen21/Scripts/python.exe E:/OpenXCom/tools/hdart/doll_neko_heads_531.py --paint --variant A --shift 0 --looks F3,F7,F17,M5,M11,M23
"""
import os
import sys

for _k in ("variant", "shift"):                     # аргументы в окружение: рабочий процесс H.main запускается заново и берёт их оттуда
    if "--" + _k in sys.argv:
        _i = sys.argv.index("--" + _k)
        os.environ["XP531_" + _k.upper()] = sys.argv[_i + 1]
        del sys.argv[_i:_i + 2]

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import doll_neko_heads as NH                        # до numpy: ставит окружение модели
import doll_race_heads as H
import doll_b2_render as db

SIX = ("F3", "F7", "F17", "M5", "M11", "M23")
VARIANT = os.environ.get("XP531_VARIANT", "A")
SHIFT = int(os.environ.get("XP531_SHIFT", "0"))
NH.PIN.clear()                                      # варианты страницы идут по своим сдвигам, не по закреплённым сидам выбора
H.HEADS = os.path.join(db.ROOT, "art", "_review", "xp531_v1", VARIANT, "heads")
H.RESEED = {look: SHIFT for look in SIX}

if __name__ == "__main__":
    H.main()
