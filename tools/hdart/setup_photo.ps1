# "Photo" pictures (photo_ui.py): one-time setup on top of setup_gen.ps1's venv (Windows, RTX 5090).
#
#   Updates the diffusers stack in tools\hdart\.venv (Qwen-Image-Edit-2511 needs diffusers >= 0.36 and peft)
#   and downloads the models into -Models (default E:\models): Qwen-Image-Edit-2511 (about 57 GB),
#   the Lightning LoRA (0.85 GB) and the Anime-to-Photoreal LoRA (0.3 GB). Resumable: run it again
#   if the download breaks.
#
#   Usage (PowerShell, from E:\OpenXCom):   powershell -ExecutionPolicy Bypass -File tools\hdart\setup_photo.ps1 [-Models E:\models]

param(
    [string]$Models = "E:\models"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$venv = Join-Path $root ".venv"
$py = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path $py)) {
    throw "no venv in $venv - run tools\hdart\setup_gen.ps1 first"
}
$env:HF_HOME = $Models
$env:HF_HUB_CACHE = Join-Path $Models "hub"
$env:HD_MODELS = $Models
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
New-Item -ItemType Directory -Force -Path $env:HF_HUB_CACHE | Out-Null

Write-Host "== diffusers stack (upgrade)"
& $py -m pip install --upgrade "diffusers>=0.36" "transformers>=4.57" accelerate peft huggingface_hub safetensors pillow numpy

Write-Host "== check"
& $py -c "import torch, diffusers, transformers, peft; print('torch', torch.__version__, 'cuda', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else '-'); print('diffusers', diffusers.__version__, 'transformers', transformers.__version__, 'peft', peft.__version__); from diffusers import QwenImageEditPlusPipeline; print('QwenImageEditPlusPipeline ok')"

Write-Host "== models -> $Models (about 58 GB, one time, resumable)"
& $py (Join-Path $root "photo_ui.py") --models $Models --download-only

Write-Host ""
Write-Host "Done. Try (5 presets of one picture, ~2 min):"
Write-Host "  $py tools\hdart\photo_ui.py --dir Пиратки\Dioxine_XPiratez\user\mods\Piratez\Resources\Pedia --mod user\mods\hd --refs AAP_002 --fast"
