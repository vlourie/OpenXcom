# HD art pipeline: one-time setup of the image generation environment (Windows, RTX 50xx).
#
#   py -3 -m venv is used, torch comes from the CUDA 12.8 index (the Blackwell / RTX 5090 build),
#   and the models (about 12 GB: SDXL base, the fp16 VAE, the tile and canny ControlNets) are
#   downloaded into the models folder.
#
#   Usage (PowerShell, from E:\OpenXCom):   powershell -ExecutionPolicy Bypass -File tools\hdart\setup_gen.ps1 [-Models E:\models]
#   The models (~12 GB) are downloaded into -Models (default E:\models) at the end; gen_hd.py reads them from there.

param(
    [string]$Models = "E:\models"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$venv = Join-Path $root ".venv"
$env:HF_HOME = $Models
$env:HF_HUB_CACHE = Join-Path $Models "hub"
$env:HD_MODELS = $Models
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
New-Item -ItemType Directory -Force -Path $Models | Out-Null

if (-not (Test-Path $venv)) {
    Write-Host "== creating venv in $venv"
    py -3 -m venv $venv
}
$py = Join-Path $venv "Scripts\python.exe"
& $py -m pip install --upgrade pip wheel

Write-Host "== torch (CUDA 12.8 build for RTX 50xx)"
& $py -m pip install --index-url https://download.pytorch.org/whl/cu128 torch torchvision

Write-Host "== diffusers stack"
& $py -m pip install diffusers transformers accelerate safetensors huggingface_hub pillow numpy opencv-python-headless

Write-Host "== check"
& $py -c "import torch; print('torch', torch.__version__, 'cuda', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else '-')"

Write-Host "== models -> $Models (about 12 GB, one time)"
& $py (Join-Path $root "gen_hd.py") --models $Models --download-only

Write-Host ""
Write-Host "Done. Models are in $Models. Try:"
Write-Host "  $py tools\hdart\gen_hd.py --sheets hdart_sheets --set CULTIVAT.PCK --test"
