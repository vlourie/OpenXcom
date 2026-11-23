# OXCE-HD

**OXCE-HD is an unofficial fork of [OpenXcom Extended](https://github.com/MeridianOXC/OpenXcom) 8.7.1**
(which is itself a fork of [OpenXcom](https://github.com/OpenXcom/OpenXcom)). It adds a 32-bit HD rendering
layer, an HD interface, battle effects and Lua mods on top of the classic 8-bit renderer and is used by the
X-Piratez HD build.

- **Not affiliated.** OXCE-HD is not made, endorsed or supported by the OpenXcom or OXCE developers, nor by
  Dioxine (the author of X-Piratez). Please report problems with this build to
  [our tracker](https://x-piratez.mywire.org:8443/tickets/new), not to the OpenXcom forum.
- **Licence.** GNU GPL v3, the same as OpenXcom and OXCE: see `LICENSE.txt`. No warranty.
- **Changes.** Modified by the OXCE-HD team since September 2026; everything we changed is in the Git history
  of the `hd-render` branch (new code lives mostly in `src/Engine/Hd*`) and in `CHANGELOG.md`.
- **Source of released binaries.** Every build shipped to players is tagged `hd-<release>`, for example
  `hd-2026.11.16-2`. The game folder contains `OXCE-HD-README.txt` with the link to the exact commit.
- **Building.** CMake + Ninja, MinGW-w64 (MSYS2), SDL 1.2: see `BUILD.md` and `docs/SETUP.md`.
- The launcher and the web site are separate programs: they only download and start the game and are not part
  of this repository.

---

Форк [OpenXcom Extended](https://github.com/MeridianOXC/OpenXcom) (OXCE 8.7) с новым
графическим слоем для X-Piratez: HD-террейн и спрайты, HD-интерфейс с TTF-шрифтами,
HD-эффекты боя. **Механика игры не меняется**: правила, баланс, ИИ и сохранения — как в OXCE.
В классическом режиме графики (F11 в бою, режим 0) кадр побайтно совпадает с оригинальным.

## Для игрока

Игра ставится лаунчером: мастер установки сам скачивает сборку, X-Piratez и русский патч,
а оригинальный UFO ищет в Steam, GOG и прежних установках. Что изменилось — `CHANGELOG.md`.

Показом интро управляет опция `playIntro`. Озвучка интро использует ползунок громкости музыки: при нуле она не слышна; обновление сохраняет существующие настройки.

## Для разработчика

- что за проект и его границы — `docs/PROJECT.md`;
- журнал решений — `docs/DECISIONS.md`, грабли — `docs/RAKES.md`;
- сборка — `docs/SETUP.md` и раздел «Сборка» в `CLAUDE.md` (CMake + Ninja, MinGW из MSYS2);
- проверка рендера — `tools/hdtest_README.md`;
- сайт и лаунчер — отдельные программы в своём репозитории, в этот они не входят.

Код движка распространяется на условиях GPL v3, как OpenXcom (`LICENSE.txt`).
