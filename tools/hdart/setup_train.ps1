# Обучение LoRA под Qwen-Image-2.1: своё окружение, рядом со всем остальным.
#
#   Учить умеет DiffSynth-Studio (тулкит ModelScope, тех же, кто выпускает модель):
#   examples\qwen_image_21\model_training\train.py, с обучением ПРАВКЕ по входной картинке.
#   ai-toolkit и musubi-tuner 2.1 в списке поддержки не держат.
#
#   Ставится ОТДЕЛЬНО от tools\hdart\.venv-qwen21: тренер тянет свои версии torch, diffusers
#   и peft, и рабочую генерацию этим легко сломать. По умолчанию всё уезжает в E:\train,
#   то есть вне репозитория - в гит ничего не попадёт.
#
#   Запуск (PowerShell из E:\OpenXCom):
#       powershell -ExecutionPolicy Bypass -File tools\hdart\setup_train.ps1
#       powershell -ExecutionPolicy Bypass -File tools\hdart\setup_train.ps1 -Dir D:\train -NoTorch

param(
    [string]$Dir = "E:\train",
    [string]$Models = "E:\models",
    [switch]$NoClone,
    [switch]$NoTorch
)

$ErrorActionPreference = "Stop"

foreach ($tool in @("py", "git")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "нет $tool в PATH этой машины"
    }
}

$venv = Join-Path $Dir ".venv-train"
$repo = Join-Path $Dir "DiffSynth-Studio"
New-Item -ItemType Directory -Force -Path $Dir | Out-Null

if (-not (Test-Path $venv)) {
    Write-Host "== новое окружение в $venv (.venv-qwen21 не трогаем)"
    py -3 -m venv $venv
}
$py = Join-Path $venv "Scripts\python.exe"
& $py -m pip install --upgrade pip wheel

if (-not $NoTorch) {
    Write-Host "== torch (сборка под CUDA 12.8, RTX 50xx)"
    & $py -m pip install --index-url https://download.pytorch.org/whl/cu128 torch torchvision
}

if (-not $NoClone) {
    if (Test-Path (Join-Path $repo ".git")) {
        Write-Host "== обновляю DiffSynth-Studio"
        git -C $repo pull --ff-only
    } else {
        Write-Host "== клонирую DiffSynth-Studio в $repo"
        git clone --depth 1 https://github.com/modelscope/DiffSynth-Studio $repo
    }
}

Write-Host "== DiffSynth-Studio и то, что нужно обучению"
& $py -m pip install -e $repo
& $py -m pip install --upgrade accelerate peft pandas modelscope

Write-Host "== проверка"
& $py -c @"
import torch
print('torch', torch.__version__, 'cuda', torch.cuda.is_available(),
      torch.cuda.get_device_name(0) if torch.cuda.is_available() else '-')
if torch.cuda.is_available():
    print('видеопамяти', round(torch.cuda.get_device_properties(0).total_memory / 2**30), 'ГБ')
import diffsynth
print('diffsynth', getattr(diffsynth, '__version__', 'из исходников'))
"@

$train = Join-Path $repo "examples\qwen_image_21\model_training\train.py"
if (-not (Test-Path $train)) {
    throw "в клоне нет $train - значит в репозитории переименовали пример, посмотреть examples\"
}

# Модель уже скачана в E:\models кэшем huggingface. Ищем её, чтобы не тянуть 33 ГБ второй раз:
# train.py умеет --model_paths со списком локальных файлов (JSON).
$snapRoot = Join-Path $Models "hub\models--Qwen--Qwen-Image-2.1\snapshots"
$local = $null
if (Test-Path $snapRoot) {
    $local = Get-ChildItem -Path $snapRoot -Directory | Sort-Object LastWriteTime -Descending |
             Select-Object -First 1
}
if ($local) {
    $groups = @()
    foreach ($part in @("transformer", "text_encoder", "vae")) {
        $files = Get-ChildItem -Path (Join-Path $local.FullName $part) -Filter "*.safetensors" `
                 -ErrorAction SilentlyContinue | Sort-Object Name
        if ($files) { $groups += ,@($files | ForEach-Object { $_.FullName -replace '\\', '/' }) }
    }
    if ($groups.Count -eq 3) {
        $jsonPath = Join-Path $Dir "model_paths.json"
        # без спецификации: строку из этого файла получает argparse тренера, и BOM ломает
        # разбор JSON (грабли R-001, исключение - файл читает не человек)
        $json = ConvertTo-Json $groups -Depth 4 -Compress
        [System.IO.File]::WriteAllText($jsonPath, $json, (New-Object System.Text.UTF8Encoding($false)))
        Write-Host ""
        Write-Host "нашёл местную модель: $($local.FullName)"
        Write-Host "список файлов записан в $jsonPath - train_lora.ps1 возьмёт его сам"
    } else {
        Write-Host "местная модель найдена не целиком - обучение скачает веса заново"
    }
} else {
    Write-Host "местной модели в $snapRoot нет - обучение скачает веса (около 33 ГБ)"
}

Write-Host ""
Write-Host "Готово. Дальше:"
Write-Host "  powershell -ExecutionPolicy Bypass -File tools\hdart\train_lora.ps1"
