# tools

| Скрипт | Кто использует | Что делает |
|---|---|---|
| `gen_gpu.py` | `gpu-forge` | мост к локальному бэкенду генерации; `--check` проверяет, поднят ли он |
| `attic/optimize_assets.ps1` | никто (в чулане с 05.10, аудит) | ресайз, палитра, сжатие PNG из `10_generated` в `20_optimized` |

Правило: любая операция, сделанная над ассетами руками дважды, оформляется скриптом здесь.
Иначе следующая партия из 40 картинок съест день.

## Что нужно поставить

```powershell
winget install ImageMagick.ImageMagick
winget install --id oxipng.oxipng        # если доступен, иначе с GitHub releases
```

Бэкенд генерации (ComfyUI или Forge) — см. вывод `python tools/gen_gpu.py --check`.
