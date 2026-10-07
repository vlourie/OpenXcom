# Новые модели Hugging Face с 01.09.2026 — что годится HD-арту

Перепись 28.09.2026: API Hugging Face, модели, созданные с 01.09, по задачам text-to-image,
image-to-image, image-to-3d, сегментация, глубина; 431 модель, отбор по лайкам и загрузкам
(скрипт в блокноте сессии `hf_new.py`). Повод — обе фото-пробы предметов забракованы (R-125).

## Годится

| Модель | Дата | Что даёт нам | Цена |
|---|---|---|---|
| `Qwen/Qwen-Image-2.1` (у нас уже есть) | 14–20.09 | **Родная прозрачность**: VAE на 4 канала (`AutoencoderKLQwenImage21`, `in_channels: 4` в нашей копии). Включается словами в промпте: «This is an RGBA image with transparency… The image has alpha channel and the background is transparent». Убирает подложку и всю вырезку по ней (R-089, дыры в серых вещах партии 1). Родное разрешение 2 Мп, 40 шагов; мы гоняли 1 Мп — там открыт баг гало #14824 | скачивать нечего |
| `alibaba-pai/Qwen-Image-2.1-Fun-Controlnet-Union` | 23.09 | ControlNet для 2.1: Canny, Depth, HED, Lineart, MLSD, Scribble, Grayscale, inpaint. Модель рисует с нуля (фото, strict), но **по контуру оригинала**: силуэт, число ступеней, полок и ящиков держит контроль, а не слова промпта | 7 ГБ; не diffusers — свой код VideoX-Fun (`predict_t2i_control.py`) |
| `Viggle/Qwen-Image-2.1-viggle-turbo` | 22.09 | LoRA-дистилляция 2.1: 6 шагов вместо 40, примерно в 5 раз быстрее, «на большинстве промптов не отличить». Умеет правку с 1–3 опорами и RGBA. Это «быстрая модель», но на базе 2.1, а не Edit-2511 | LoRA 680 МБ (r128) или 1,3 ГБ (r256) |
| `Qwen/Qwen-Image-2.1-PE-I2I`, `-PE-T2I` | 20.09 | переписчик промпта (Qwen3.5-VL 9B): короткое задание превращает в подробный промпт. Опознание не заменяет — только формулировку | 18 ГБ, отдельный проход |

Лицензия всей линейки 2.1 — Qwen Research License: без коммерческого использования.

## Не годится или рано

- `inclusionAI/Ming-Image-0.1-Design-Layer` — раскладка картинки на RGBA-слои, но проверена на 80 ГБ видеопамяти.
- `AiArtLab/zen-image-edit` — та же 2.1 с лёгким текстовым энкодером под слабые карты; у нас 32 ГБ, выигрыша нет. Как у неё включается RGBA, в карточке не сказано.
- `e-n-v-y/Qwen-Image-2.1-Fix` — LoRA «чинит большую часть проблем», но каких именно, не сказано; только с их настройками.
- `lilylilith/QI_2.1_AnyAngle` — смена ракурса по 3D-рендеру в Blender; нам ракурс менять не нужно.
- Видео (MiniMax-H3, LTX-2.5), 3D из картинки (Fire3D, Pixal3D, TRELLIS-копии) — не наша задача сейчас.
- Новых моделей вырезки фона за сентябрь нет; последнее — BiRefNet-Lucida (июль, через ComfyUI-RMBG).

## Прежний опыт с прозрачностью 2.1

`docs/GENERATORS.md`, грабли 1: «2.1 возвращает фиолетовый фон, а не прозрачный». Проверено тогда
не официальной фразой, а своей («on a fully transparent RGBA background», `gen_fire.py`), при
`--alpha unpanel` ответ переводится в RGB. Официальная фраза и сохранение альфы не пробовались.

## Предлагаемый порядок

1. Проба RGBA на своей 2.1 (без загрузок): те же 13 предметов, strict (одобренный стиль),
   официальная фраза прозрачности, 2 Мп, альфа из ответа. Лист на пурпурной подложке — видно дыры.
2. Если альфа честная — Viggle turbo (680 МБ) для скорости, сверка листом против 40 шагов.
3. ControlNet Union (7 ГБ) — для вещей, где важно число деталей (лестницы, полки).

## Источники

- https://huggingface.co/Qwen/Qwen-Image-2.1
- https://qwenimages.com/blog/qwen-image-2-1-release
- https://huggingface.co/alibaba-pai/Qwen-Image-2.1-Fun-Controlnet-Union
- https://huggingface.co/Viggle/Qwen-Image-2.1-viggle-turbo
- https://huggingface.co/Qwen/Qwen-Image-2.1-PE-T2I
- https://huggingface.co/inclusionAI/Ming-Image-0.1-Design-Layer
- https://huggingface.co/AiArtLab/zen-image-edit
- https://huggingface.co/e-n-v-y/Qwen-Image-2.1-Fix
- https://huggingface.co/lilylilith/QI_2.1_AnyAngle
- https://technode.com/2026/09/21/alibabas-qwen-open-sources-qwen-image-2-1-for-unified-image-generation-and-editing/
- https://www.eesel.ai/blog/qwen-image-2-1-review
