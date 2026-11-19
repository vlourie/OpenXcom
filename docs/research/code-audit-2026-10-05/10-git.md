# Гит (git-warden + мои проверки), 05.10

Факты:
- hd-render e6af0d5ed, на 472 коммита впереди origin/hd-render (origin последний 143d97808 от 27.09); последний fetch 04.10.
- Незакоммичено: 31 M + 231 ??; из них tools/hdart 219 новых (29.09–05.10, приёмочный инструментарий: acceptance_*, derive_*, relation_*, routing_*, obj_*, asset_*, unit_*, weapon_*), docs 9 новых, .claude 2 новых, AGENTS.md.
- Мусора в трекинге нет (файлов >2 МБ нет, бинарников/логов нет), .gitignore покрывает build-release, art, census, user/mods/hd, Пиратки; .claude/worktrees исключён через .git/info/exclude.
- Секретов в трекаемых файлах нет (только игровые строки и LICENSE).
- Стиль коммитов: 60/60 «область: что сделано», русский; самое длинное сообщение 1802 символа (c11286ce4).
- .git 168 МБ, gc не нужен.

Ветки (мои замеры):
| ветка | коммит | впереди hd-render | назад | вывод |
| claude/elegant-gauss-40b634 | 911ca487f (=oxce-plus, май) | 0 | 933 | мусор сессии Claude, worktree чистый, detached |
| claude/vigorous-easley-829978 | 911ca487f | 0 | 933 | то же |
| claude/keen-robinson-8bc1d3 | 911ca487f | 0 | 933 | то же; его worktree стоит на claude/gpuq-psutil |
| claude/gpuq-psutil | 1f559b8c5 (29.09) | 0 | 354 | влита (R-139), worktree чистый |
| worktree-agent-a9746e1040e51735b | c841720c7 (26.09) | 13 | 526 | все 13 патчей уже в hd-render (git cherry: 13 «-») — влита по содержимому |
| hd-render-before-8.7 | 017eb82bb (17.09) | 0 | 823 | контрольная точка — лучше тег |
| hdglue-test | 7503cba0f (28.09) | 0 | 425 | влита, но worktree E:/OpenXCom-glue держит 5 изменённых src (BattlescapeState, Map, HdCanvas.*, HdSprites.*) + build-glue/ — чей-то незавершённый опыт склейки (R-123) |
| oxce-plus | 911ca487f | 0 | 933 | базовая |

Удаление веток/worktree классификатор auto-режима отклонил (вмешательство в чужие рабочие нагрузки) — команды для Vitali в отчёте.
