# Qwen-Image-2.1 (--painter qwen21): своё окружение, рядом со старым.
#
#   Qwen-Image-2.1 просит diffusers из исходников и transformers >= 5.17. Ставить их в
#   tools\hdart\.venv нельзя - там живут SDXL, photo_ui и вся остальная кухня, они от такого
#   обновления ломаются. Поэтому здесь отдельный venv tools\hdart\.venv-qwen21, а модели
#   лежат в общей папке -Models (E:\models), как у всех прочих.
#
#   Качает Qwen/Qwen-Image-2.1 (около 33 ГБ). Скачивание возобновляемое: если оборвалось -
#   просто запусти ещё раз.
#
#   Запуск (PowerShell из E:\OpenXCom):
#       powershell -ExecutionPolicy Bypass -File tools\hdart\setup_qwen21.ps1 [-Models E:\models] [-NoModel]

param(
    [string]$Models = "E:\models",
    [switch]$NoModel
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$venv = Join-Path $root ".venv-qwen21"
$env:HF_HOME = $Models
$env:HF_HUB_CACHE = Join-Path $Models "hub"
$env:HD_MODELS = $Models
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
New-Item -ItemType Directory -Force -Path $env:HF_HUB_CACHE | Out-Null

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "нет py (Python launcher) - поставь Python 3 с python.org"
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "нет git - diffusers ставится из исходников, без git не выйдет"
}

if (-not (Test-Path $venv)) {
    Write-Host "== новое окружение в $venv (старое .venv не трогаем)"
    py -3 -m venv $venv
}
$py = Join-Path $venv "Scripts\python.exe"
& $py -m pip install --upgrade pip wheel

Write-Host "== torch (сборка под CUDA 12.8, RTX 50xx)"
& $py -m pip install --index-url https://download.pytorch.org/whl/cu128 torch torchvision

Write-Host "== diffusers из исходников + transformers 5.x"
& $py -m pip install --upgrade "transformers>=5.17" accelerate safetensors huggingface_hub pillow numpy opencv-python-headless
& $py -m pip install --upgrade "git+https://github.com/huggingface/diffusers"

Write-Host "== проверка"
& $py -c @"
import torch, diffusers, transformers
print('torch', torch.__version__, 'cuda', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else '-')
print('diffusers', diffusers.__version__, 'transformers', transformers.__version__)
names = [n for n in ('QwenImage21Pipeline','QwenImage21EditPipeline','QwenImageEdit21Pipeline','QwenImage2_1Pipeline') if hasattr(diffusers, n)]
print('конвейер Qwen-Image-2.1:', names[0] if names else 'НЕ НАЙДЕН - обнови diffusers')
"@

if (-not $NoModel) {
    Write-Host "== модель -> $Models (около 33 ГБ, один раз, с возобновлением)"
    & $py -c @"
import os
from huggingface_hub import snapshot_download
p = snapshot_download('Qwen/Qwen-Image-2.1', max_workers=8)
print('скачано в', p)
"@
}

Write-Host ""
Write-Host "Готово. Пробный пол (DESERT, кадр 7, поле 3x3):"
Write-Host "  $py tools\hdart\gen_hd.py --sheets art/TERRAIN --set DESERT.PCK --only ground --ground-field 3 --painter qwen21 --frame 7"
