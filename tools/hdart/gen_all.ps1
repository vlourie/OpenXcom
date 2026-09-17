# HD art pipeline: paints every terrain set of vanilla UFO into the HD mod (user\mods\hd, the one mod that carries every HD asset), set after set, and can be left
# running (it skips sets whose pack already exists, so it resumes after an interruption).
#
#   powershell -ExecutionPolicy Bypass -File tools\hdart\gen_all.ps1 [-Sets CULTIVAT,BARN] [-Force] [-Mod user\mods\hd]
#       [-Variants 2] [-VariantsOnly]
#
#   -Sets   which sets (names without .PCK); default: every terrain set, farm first
#   -Units  unit sets instead (UNITS\*.PCK -> hd\<set>\): -Units -Sets XCOM_0 paints one; -Units alone all 20
#   -Force  repaint sets that already have a pack
#   -PackOnly  no painting: rebuild the packs from the painted sheets already in -Sheets (seconds per
#           set) - after a build_pack.py change, or with other -PackArgs, e.g. -PackArgs "--floor-under 0"
#   -Variants N  also paint N ground variants of every natural floor (grass, soil, sand, snow, rock, mud,
#           forest floor): the engine lays them over the map as patches (gen_hd.py --variants)
#   -VariantsOnly  paint only the variants of sets already painted (the base painting and objects stay);
#           default sets: the natural ones. A set whose variants.json already has N looks is skipped (-Force repaints)
#   -Data   the UFO data folder (bin\UFO), -Sheets the working folder (hdart_sheets)
#   Extra arguments for gen_hd.py go into -GenArgs, e.g. -GenArgs "--strength 0.85 --seed 7" (a value with spaces
#   in single quotes: -GenArgs "--variant-looks 'short grass|tall grass'")
#
# Log: <Sheets>\gen_all.log. Per set: extract -> gen_hd (about 2-6 minutes on a 5090) -> build_pack.

param(
    [string[]]$Sets = @(),
    [switch]$Units,
    [switch]$Force,
    [string]$Data = "bin\UFO",
    [string]$Sheets = "hdart_sheets",
    [string]$Mod = "user\mods\hd",
    [string]$GenArgs = "",
    [switch]$PackOnly,
    [string]$PackArgs = "",
    [int]$Variants = 0,
    [switch]$VariantsOnly
)

$ErrorActionPreference = "Stop"
# "-File gen_all.ps1 -Sets CULTIVAT,BARN" passes one string: split it
$Sets = @($Sets | ForEach-Object { $_ -split "," } | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" })
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPy = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) { throw "no venv at $venvPy - run setup_gen.ps1 first" }

$terrain = @(
    "CULTIVAT", "BARN", "ROADS", "FRNITURE",
    "FOREST", "JUNGLE", "DESERT", "MOUNT", "POLAR",
    "URBAN", "URBITS",
    "UFO1", "U_EXT02", "U_WALL02", "U_BITS", "U_DISEC2", "U_OPER2", "U_PODS", "U_BASE",
    "XBASE1", "XBASE2", "PLANE", "LIGHTNIN", "AVENGER", "MARS", "BRAIN"
)
$unitSets = @(
    "XCOM_0", "XCOM_1", "XCOM_2", "SECTOID", "FLOATER", "SNAKEMAN", "MUTON", "ETHEREAL",
    "CHRYS", "CELATID", "SILACOID", "ZOMBIE", "CYBER", "X_REAP", "X_ROB", "TANKS", "CIVM", "CIVF",
    "HANDOB", "FLOOROB"
)
$folder = "TERRAIN"
$packPath = "TERRAIN"
if ($Units) { $folder = "UNITS"; $packPath = ""; if ($Sets.Count -eq 0) { $Sets = $unitSets } }
$natural = @("CULTIVAT", "FOREST", "JUNGLE", "DESERT", "MOUNT", "POLAR", "MARS")
if ($VariantsOnly) {
    if ($Units) { throw "-VariantsOnly is for terrain sets" }
    if ($Variants -lt 1) { $Variants = 2 }
    if ($Sets.Count -eq 0) { $Sets = $natural }
}
if ($Sets.Count -eq 0) { $Sets = $terrain }

New-Item -ItemType Directory -Force -Path $Mod | Out-Null
$meta = Join-Path $Mod "metadata.yml"
if (-not (Test-Path $meta)) {
    @(
        'name: "HD graphics"',
        'version: 0.1',
        'author: "Vitali + Claude"',
        'description: "HD assets for the HD render: painted HD terrain sprites and effects (tools/hdart), and more as it grows. Needs the HD options (Advanced -> OXCE)."',
        'id: hd',
        'master: "*"',
        'reservedSpace: 1'
    ) | Set-Content -Path $meta -Encoding UTF8
}

$log = Join-Path $Sheets "gen_all.log"
New-Item -ItemType Directory -Force -Path $Sheets | Out-Null
# "-GenArgs" / "-PackArgs": split on spaces, a part in quotes ('short grass|tall grass') stays one argument
function Split-Args([string]$text) {
    $out = @()
    foreach ($m in [regex]::Matches($text, "'([^']*)'|`"([^`"]*)`"|(\S+)")) {
        if ($m.Groups[1].Success) { $out += $m.Groups[1].Value }
        elseif ($m.Groups[2].Success) { $out += $m.Groups[2].Value }
        else { $out += $m.Groups[3].Value }
    }
    return $out
}
function Log($msg) {
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Write-Host $line
    Add-Content -Path $log -Value $line
}

$started = Get-Date
foreach ($set in $Sets) {
    $set = $set.ToUpper()
    if ($set -notlike "*.PCK") { $set = "$set.PCK" }
    $packDir = if ($packPath -ne "") { Join-Path $Mod ("hd\" + $packPath + "\" + $set) } else { Join-Path $Mod ("hd\" + $set) }
    $painted = Join-Path $Sheets ($set + "\painted_x4.png")
    if ($PackOnly) {
        if (-not (Test-Path $painted)) { Log "$set : no painted sheet, skipping"; continue }
    } else {
        if ($VariantsOnly) {
            if (-not (Test-Path $painted)) { Log "$set : not painted yet, skipping (paint it first, e.g. -Sets $set -Variants $Variants)"; continue }
            $variantsJson = Join-Path $Sheets ($set + "\variants.json")
            if ((Test-Path $variantsJson) -and -not $Force) {
                $have = [int](Get-Content $variantsJson -Raw | ConvertFrom-Json).PSObject.Properties["count"].Value
                if ($have -ge $Variants) { Log "$set : has $have variants, skipping (-Force to repaint)"; continue }
            }
        } elseif ((Test-Path $packDir) -and -not $Force) {
            Log "$set : pack exists, skipping (-Force to repaint)"
            continue
        }
        Log "$set : extract"
        & py -3 (Join-Path $root "extract_pck.py") --data $Data --out $Sheets --sets "$folder/$set"
        if ($LASTEXITCODE -ne 0) { Log "$set : extract failed"; continue }
        Log "$set : paint"
        $t0 = Get-Date
        $genArgList = @("--sheets", $Sheets, "--set", $set)
        if ($Variants -gt 0) { $genArgList += @("--variants", "$Variants") }
        if ($VariantsOnly) { $genArgList += @("--only", "variants") }
        if ($GenArgs -ne "") { $genArgList += Split-Args $GenArgs }
        & $venvPy (Join-Path $root "gen_hd.py") @genArgList
        if ($LASTEXITCODE -ne 0) { Log "$set : paint failed"; continue }
        Log ("$set : painted in {0:N0} s" -f ((Get-Date) - $t0).TotalSeconds)
    }
    Log "$set : pack"
    $packArgList = @("--sheets", $Sheets, "--set", $set, "--hd", $painted, "--mod", $Mod)
    if ($packPath -ne "") { $packArgList += @("--pack-path", $packPath) }
    if ($PackArgs -ne "") { $packArgList += Split-Args $PackArgs }
    & py -3 (Join-Path $root "build_pack.py") @packArgList
    if ($LASTEXITCODE -ne 0) { Log "$set : pack failed"; continue }
    Log "$set : done"
}
Log ("all done in {0:N0} min" -f ((Get-Date) - $started).TotalMinutes)
