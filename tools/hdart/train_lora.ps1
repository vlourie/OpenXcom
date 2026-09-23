# Обучение edit-LoRA под Qwen-Image-2.1 на нашем датасете.
#
#   Датасет делает tools\hdart\build_dataset.py: metadata.csv со столбцами image, edit_image,
#   prompt. edit_image - оригинальная клетка на подложке (то, что подаём), image - готовая
#   клетка (то, что хотим получить). Ключи --data_file_keys и --extra_inputs как раз и
#   превращают обучение в обучение ПРАВКЕ, без них модель училась бы рисовать по тексту с нуля.
#
#   ПРАВКИ В run_train.cmd НЕ ЗАТИРАЮТСЯ. Скрипт держит рядом свою копию сгенерированного
#   (run_train.generated.cmd) и перед запуском сверяет. Если run_train.cmd отличается - значит
#   его правили руками, и скрипт запускает ЕГО КАК ЕСТЬ, ничего не перезаписывая. Чтобы
#   вернуться к сборке по параметрам - ключ -Regen.
#
#   ПОЧЕМУ ЧЕРЕЗ .cmd, А НЕ НАПРЯМУЮ.
#   Windows PowerShell 5.1 передаёт аргументы внешним программам простой склейкой строки:
#   пустая строка "" пропадает совсем, а кавычки внутри аргумента съедаются. Обучению нужно
#   и то и другое: --lora_target_modules "" (пустое значение = LoRA на все слои) и
#   --model_paths с JSON, где кавычки обязательны - его разбирает json.loads.
#
#   РАБОЧАЯ НАСТРОЙКА (найдена 22.09.2026, 1.83 с/шаг на RTX 5090).
#   Нужны обе половины сразу, поодиночке не помогает ни одна:
#     -Width 384 -Height 480   вместо родных 768x960. Клетка пака при k=4 это 128x160,
#                              больше в ней информации просто нет, а длина последовательности
#                              падает с 5888 токенов до 1568 и внимание дешевеет как квадрат.
#     --enable_model_cpu_offload   веса лежат в обычной памяти и подаются на карту послойно.
#                              Иначе не влезает: DiT 14.2 ГБ + кодировщик 17.5 + VAE = 32.3 ГБ
#                              против 31.5 ГБ видеопамяти. Без этого Windows молча свопит
#                              через шину, и шаг тянется 82 секунды вместо двух.
#   Оба включены по умолчанию. Выключаются -NoModelOffload и -Width 0 -Height 0.
#
#   Шагов выходит: пар в metadata.csv * Repeat * Epochs.
#
#   Запуск (PowerShell из E:\OpenXCom):
#       powershell -ExecutionPolicy Bypass -File tools\hdart\train_lora.ps1
#       powershell -ExecutionPolicy Bypass -File tools\hdart\train_lora.ps1 -Width 384 -Height 480
#       powershell -ExecutionPolicy Bypass -File tools\hdart\train_lora.ps1 -NoModelOffload
#       powershell -ExecutionPolicy Bypass -File tools\hdart\train_lora.ps1 -Extra "--fp8_models","dit"
#       powershell -ExecutionPolicy Bypass -File tools\hdart\train_lora.ps1 -DryRun
#       powershell -ExecutionPolicy Bypass -File tools\hdart\train_lora.ps1 -Regen   # забыть правки руками

# [CmdletBinding()] тут не для красоты: без него PowerShell складывает нераспознанные ключи
# в $args МОЛЧА - ни ошибки, ни предупреждения, код возврата 0. Строка с опечаткой или со
# старым именем ключа отрабатывает как будто всё хорошо, только без этого ключа. С ним -
# сразу ошибка с именем.
[CmdletBinding()]
param(
    [string]$Dir = "E:\train",
    [string]$Data = "E:\OpenXCom\dataset",
    [string]$Models = "E:\models",
    [string]$Out = "",
    [int]$Rank = 32,
    [int]$Epochs = 5,
    [int]$Repeat = 4,
    [int]$SaveSteps = 500,
    [double]$Lr = 1e-4,
    [int]$Width = 384,
    [int]$Height = 480,
    [string]$Task = "",
    [string[]]$Extra = @(),
    [switch]$Offload,
    [switch]$NoModelOffload,
    [switch]$Download,
    [switch]$Regen,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$venv = Join-Path $Dir ".venv-train"
$repo = Join-Path $Dir "DiffSynth-Studio"
$py = Join-Path $venv "Scripts\python.exe"
$acc = Join-Path $venv "Scripts\accelerate.exe"
$train = Join-Path $repo "examples\qwen_image_21\model_training\train.py"
$meta = Join-Path $Data "metadata.csv"

foreach ($p in @($py, $train, $meta)) {
    if (-not (Test-Path $p)) {
        throw "нет $p - сначала setup_train.ps1, а датасет собирает build_dataset.py"
    }
}
if (-not $Out) { $Out = Join-Path $Dir "lora\oxcehd" }
New-Item -ItemType Directory -Force -Path $Out | Out-Null

$pairs = @(Import-Csv -Path $meta).Count
Write-Host "пар в датасете: $pairs, шагов будет примерно $($pairs * $Repeat * $Epochs)"

# Длина последовательности - главная цена шага, внимание растёт как её квадрат.
# VAE делит сторону на 8, патч ещё на 2, картинок в паре две, плюс сотня токенов текста.
if ($Width -gt 0 -and $Height -gt 0) {
    $tok = [int](($Width / 16) * ($Height / 16)) * 2 + 128
    Write-Host ("размер картинок принудительно {0}x{1}, токенов примерно {2}" -f $Width, $Height, $tok)
    foreach ($v in @($Width, $Height)) {
        if ($v % 32 -ne 0) { Write-Host "  внимание: $v не делится на 32, загрузчик округлит сам" }
    }
} elseif ($Width -gt 0 -or $Height -gt 0) {
    throw "-Width и -Height задаются только парой"
}

$cmdArgs = @(
    "--dataset_base_path", $Data,
    "--dataset_metadata_path", $meta,
    "--data_file_keys", "image,edit_image",
    "--extra_inputs", "edit_image",
    "--max_pixels", "1048576",
    "--dataset_repeat", "$Repeat",
    "--learning_rate", "$Lr",
    "--num_epochs", "$Epochs",
    "--save_steps", "$SaveSteps",
    "--remove_prefix_in_ckpt", "pipe.dit.",
    "--output_path", $Out,
    "--lora_base_model", "dit",
    "--lora_target_modules", "",
    "--lora_rank", "$Rank",
    "--use_gradient_checkpointing",
    "--find_unused_parameters",
    "--enable_csv_log"
)
if ($Width -gt 0)   { $cmdArgs += @("--width", "$Width", "--height", "$Height") }
if ($Task)          { $cmdArgs += @("--task", $Task) }
if ($Offload)       { $cmdArgs += "--use_gradient_checkpointing_offload" }
if (-not $NoModelOffload) { $cmdArgs += "--enable_model_cpu_offload" }
if ($Extra.Count)   { $cmdArgs += $Extra }

# Веса: сперва местные из кэша huggingface, чтобы не качать 33 ГБ второй раз.
$jsonPath = Join-Path $Dir "model_paths.json"
if ((-not $Download) -and (Test-Path $jsonPath)) {
    $cmdArgs += @("--model_paths", (Get-Content -Path $jsonPath -Raw -Encoding UTF8).Trim())
    Write-Host "веса: местные, по $jsonPath"
    # Даже с местными весами processor тренер по умолчанию тянет с хаба: в train.py стоит
    # ModelConfig(model_id="Qwen/Qwen-Image-2.1", origin_file_pattern="processor/").
    $snapRoot = Join-Path $Models "hub\models--Qwen--Qwen-Image-2.1\snapshots"
    if (Test-Path $snapRoot) {
        $snap = Get-ChildItem -Path $snapRoot -Directory | Sort-Object LastWriteTime -Descending |
                Select-Object -First 1
        if ($snap) {
            $proc = Join-Path $snap.FullName "processor"
            if (Test-Path $proc) { $cmdArgs += @("--processor_path", $proc) }
        }
    }
} else {
    $ids = "Qwen/Qwen-Image-2.1:transformer/diffusion_pytorch_model*.safetensors," +
           "Qwen/Qwen-Image-2.1:text_encoder/model*.safetensors," +
           "Qwen/Qwen-Image-2.1:vae/diffusion_pytorch_model*.safetensors"
    $cmdArgs += @("--model_id_with_origin_paths", $ids)
    Write-Host "веса: качаются с ModelScope"
}

function Get-CmdArg([string]$a) {
    # Кавычки для cmd: пустое значение - "", внутренние кавычки экранируются \" (так их разберёт
    # сама программа), проценты удваиваются (иначе cmd подставит переменную окружения).
    if ($a -eq "") { return '""' }
    $a = $a -replace '%', '%%'
    if ($a -match '[ "&<>|^]') { return '"' + ($a -replace '"', '\"') + '"' }
    return $a
}

$line = @((Get-CmdArg $acc), "launch", (Get-CmdArg $train))
foreach ($a in $cmdArgs) { $line += (Get-CmdArg $a) }

$body = @(
    "@echo off",
    ("set ""MODELSCOPE_CACHE=" + (Join-Path $Models "modelscope") + """"),
    ("set ""HF_HOME=" + $Models + """"),
    ("set ""HF_HUB_CACHE=" + (Join-Path $Models "hub") + """"),
    ($line -join " ")
) -join "`r`n"
$body = $body + "`r`n"

$cmdFile = Join-Path $Dir "run_train.cmd"
$genFile = Join-Path $Dir "run_train.generated.cmd"

# Правил ли кто-то run_train.cmd руками? Сверяем с копией того, что скрипт клал сам.
$handEdited = $false
if ((Test-Path $cmdFile) -and (Test-Path $genFile) -and (-not $Regen)) {
    $now = Get-Content -Path $cmdFile -Raw -Encoding UTF8
    $was = Get-Content -Path $genFile -Raw -Encoding UTF8
    if ($now -ne $was) { $handEdited = $true }
}

if ($handEdited) {
    Write-Host ""
    Write-Host "!! $cmdFile правили руками - запускаю ЕГО, ничего не перезаписывая."
    Write-Host "   Параметры этого скрипта сейчас НЕ действуют."
    Write-Host "   Вернуться к сборке по параметрам: тот же запуск с ключом -Regen"
} else {
    # Без спецификации и без кириллицы: этот файл читает cmd, а не человек (грабли R-001)
    $enc = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($cmdFile, $body, $enc)
    [System.IO.File]::WriteAllText($genFile, $body, $enc)
    Write-Host "команда собрана в $cmdFile"
}

if ($DryRun) {
    Write-Host ""
    Get-Content -Path $cmdFile -Encoding UTF8
    return
}

Write-Host ""
Write-Host "Полоса выполнения идёт ПО ЭПОХЕ, а не по всему обучению: она досчитает до конца"
Write-Host "и начнётся заново, и так $Epochs раз. Общее время = время эпохи * $Epochs."
Write-Host "Первый шаг включает сборку ядер Triton - по нему о скорости не судить."
Write-Host ""

& cmd /c $cmdFile
$code = $LASTEXITCODE

Write-Host ""
if ($code -ne 0) {
    throw "обучение упало, код $code - выше видно, на чём. Команда лежит в $cmdFile"
}
Write-Host "LoRA лежит в $Out"
Write-Host "ПЕРВЫМ ДЕЛОМ проверить, что она не пустая:"
Write-Host "  $py tools\hdart\check_lora.py ""$Out"""
