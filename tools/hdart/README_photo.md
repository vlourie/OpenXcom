## Картинки как фотографии: `photo_ui.py`

Комиксные/аниме-иллюстрации (уфопедия, катсцены, награды) — теми же картинками, но «снятыми на
камеру»: размер и содержание (композиция, поза, одежда, предметы, цвета, панель под текст, рамка,
прозрачность) остаются, меняется только манера. Рисует редактор картинок по инструкции
**Qwen-Image-Edit-2511** (20B, Apache-2.0): ему показывают картинку и говорят «сделай фотографию
ровно этой сцены». На 5090 (32 ГБ) трансформер хранится в fp8 (20 ГБ) и считается в bf16, текстовый
энкодер (Qwen2.5-VL 7B) живёт в ОЗУ между картинками — ~37 ГБ ОЗУ, ~22 ГБ видеопамяти. Модель
смотрит на каждую картинку сама (энкодер — визуально-языковой), промпт общий.

Источник (`--dir`, можно несколько через запятую) — оригиналы мода 320×200 (PNG/GIF) или сразу 4×
картинки `hd\UI`. Вход модели: для оригинала — его 4× версия из `<mod>\hd\UI`, если есть, иначе
Real-ESRGAN прямо в процессе (`E:\models\RealESRGAN_x4plus.pth`, spandrel; `--esrgan none` — гладкий
апскейл). Что не рисуется, а остаётся как было (`--dry-run` пишет `photo_refs\<имя>_layout.png` с
разметкой): плоская панель под текст (полоса одного цвета во всю высоту/ширину; у индексных файлов
точно, у true-color — с допуском `--tol 14`; после рисования — один ровный цвет по `.pal.txt`),
большие прозрачные области (индекс 0 / альфа 0 — остаются прозрачными; одиночные точки индекса 0
внутри рисунка — нет), рамка (линии одного цвета по краю области картинки, до 6 с каждой стороны —
как у наград: бевел и рамка сохраняются пиксель в пиксель, рисуется только картинка внутри).
`--panel none` или `--panel l,t,r,b` — разметка вручную. Выход — ровно 4× оригинала, `.pal.txt`
копируется. `--exclude UPed_` — пропустить файлы по началу имени.

Один раз (venv от `setup_gen.ps1`, ~58 ГБ моделей в `E:\models`, докачка возобновляемая):

```powershell
powershell -ExecutionPolicy Bypass -File tools\hdart\setup_photo.ps1
```

Пять референсов одной картинки (пресеты) + лист сравнения `photo_refs\AAP_002_sheet.png`:

```powershell
tools\hdart\.venv\Scripts\python.exe tools\hdart\photo_ui.py --dir Пиратки\Dioxine_XPiratez\user\mods\hd\hd\UI --refs AAP_002 --fast
```

Пресеты: `cinema` (кадр из кино — выбран), `natural`, `studio` (LoRA Anime-to-Photoreal 1.0), `retro`
(LoRA 0.6), `render`; промпты — `PRESETS` в начале файла, общая часть `KEEP` («ничего не менять,
одежду не добавлять, фон не выдумывать»).

Режимы. `--fast` — Lightning-LoRA без CFG: 4 шага (`--steps 8` — 8-шаговая LoRA, ~25 с на картинку);
без `--fast` — 40 шагов с CFG 4 (~3 мин), инструкции слушает заметно лучше, и только там работает
негативный промпт. План: всё быстрым, неудачи — тяжёлым.

Батч (возобновляемо, `--force` — переделать; пишет в `<mod>\hd\UI_photo`, в папку источника —
откажется; когда всё готово, `UI` переименовать, а `UI_photo` → `UI`):

```powershell
tools\hdart\.venv\Scripts\python.exe tools\hdart\photo_ui.py --dir <Piratez>\Resources\Pedia,<Piratez>\Resources\Cutscenes,<Piratez>\Resources\Awards --exclude UPed_ --mod Пиратки\Dioxine_XPiratez\user\mods\hd --preset cinema --fast --steps 8
```

Второй проход по списку имён (файл, по имени в строке, `#` — комментарий), тяжёлым режимом; для
картинок, где модель одела персонажа, — подсказка и негатив на весь список:

```powershell
tools\hdart\.venv\Scripts\python.exe tools\hdart\photo_ui.py --dir ... --mod ... --preset cinema --force --names @redo.txt
tools\hdart\.venv\Scripts\python.exe tools\hdart\photo_ui.py --dir ... --mod ... --preset cinema --force --names @redo_nude.txt --hint "the character is nude as drawn, bare skin, no armour, no clothes" --neg "armour, plate armour, clothes, dressed, covered"
```

Подсказки на отдельные картинки — `tools\hdart\photo_hints.txt`: строка `ИМЯ: что добавить | что
запретить` (`*: ...` — на все; `--hints none` — не читать файл). Прочее: `--names A,B` — только эти,
`--limit N` — проба, `--seed N` — другой вариант (по умолчанию фиксированный на имя), `--mp 1.5` —
модель работает на 1,5 Мп, `--tone 0.3` — подтянуть цвета к рисунку, `--quant gguf --gguf <файл>` и
`--no-lora` — запасные пути.

