<#
  OXCE HD — сборка одним запуском.

    -Target Exe   ninja -> openxcom.exe -> Enigma Virtual Box (DLL внутрь) -> dist\OpenXComEx_<дата>_<время>.exe
                  и dist\OXCE-HD_<дата>_<hash>_exe.zip   (внутри exe + common + standard, для второй машины)

  Перед любой сборкой common/standard из репозитория переносятся в установку игры (GameDir,
  Sync-DataToGame), а exe копируется туда же (CopyExeTo) под постоянным именем ExeName.
    -Target Mod   папка мода -> dist\OXCE-HD_<дата>_<hash>_mod.zip   (внутри user\mods\hd)
    -Target Both  оба шага   -> dist\OXCE-HD_<дата>_<hash>_full.zip  (внутри exe + user\mods\hd)

  ZIP — «накатка»: распаковать в папку игры (где OpenXcomEx.exe) и запустить exe.
  Настройки путей — build_config.json рядом со скриптом.
  Имя готового exe — ключ ExeResultName там же; в нём разворачиваются {stamp}, {date},
  {time}, {hash} и {branch}. По этому же имени считается, какие старые exe удалять.

  Примеры (PowerShell, из E:\OpenXCom):
    .\tools\build\build.ps1 -Target Both
    .\tools\build\build.ps1 -Target Exe -NoNinja      # без пересборки, упаковать текущий openxcom.exe
#>
[CmdletBinding()]
param(
    [ValidateSet('Exe', 'Mod', 'Both')]
    [string]$Target = 'Both',
    [switch]$NoNinja,
    [switch]$FromGui,
    [string]$Config = ''
)

$ErrorActionPreference = 'Stop'
$clock = [Diagnostics.Stopwatch]::StartNew()
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}

# ---------------------------------------------------------------- helpers

function Write-Step([string]$text) {
    Write-Host ''
    Write-Host ("==> {0}   [{1:mm\:ss}]" -f $text, $clock.Elapsed) -ForegroundColor Cyan
}
function Write-Ok([string]$text)   { Write-Host "    $text" -ForegroundColor Green }
function Write-Info([string]$text) { Write-Host "    $text" }
function Write-Warn([string]$text) { Write-Host "    ВНИМАНИЕ: $text" -ForegroundColor Yellow }

function Get-Cfg([string]$name, $default) {
    $v = $script:cfg.$name
    if ($null -eq $v -or ($v -is [string] -and $v -eq '')) { return $default }
    return $v
}

function Format-Size([double]$bytes) {
    if ($bytes -ge 1GB) { return '{0:N2} ГБ' -f ($bytes / 1GB) }
    if ($bytes -ge 1MB) { return '{0:N1} МБ' -f ($bytes / 1MB) }
    return '{0:N0} КБ' -f ($bytes / 1KB)
}

function ConvertTo-Arg([string]$a) {
    if ($a -eq '') { return '""' }
    if ($a -notmatch '[\s"]') { return $a }
    $s = $a -replace '(\\*)"', '$1$1\"'
    $s = $s -replace '(\\+)$', '$1$1'
    return '"' + $s + '"'
}

# Запуск внешней программы прямо в этой консоли (живой вывод), возвращает код выхода.
function Invoke-Native([string]$exe, [string[]]$argList, [string]$workDir = $null) {
    $line = ($argList | ForEach-Object { ConvertTo-Arg $_ }) -join ' '
    $sp = @{ FilePath = $exe; ArgumentList = $line; NoNewWindow = $true; Wait = $true; PassThru = $true }
    if ($workDir) { $sp.WorkingDirectory = $workDir }
    $p = Start-Process @sp
    return [int]$p.ExitCode
}

# Запуск с захватом stdout (для git); ошибки молча игнорируются.
function Get-NativeOutput([string]$exe, [string[]]$argList) {
    $ErrorActionPreference = 'Continue'
    try { return @(& $exe @argList 2>$null) } catch { return @() }
}

function Join-IfSet($base, [string]$rel) {
    if (-not $base) { return $null }
    return (Join-Path $base $rel)
}

function Find-Tool([string]$configured, [string[]]$candidates, [string]$commandName) {
    if ($configured) {
        if (Test-Path -LiteralPath $configured -PathType Leaf) { return $configured }
        throw "Не найден файл из настроек: $configured"
    }
    foreach ($c in $candidates) {
        if ($c -and (Test-Path -LiteralPath $c -PathType Leaf)) { return $c }
    }
    if ($commandName) {
        $cmd = Get-Command $commandName -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($cmd) { return $cmd.Source }
    }
    return $null
}

# ---------------------------------------------------------------- PE: какие DLL импортирует файл

function Get-PeImports([string]$Path) {
    $b = [IO.File]::ReadAllBytes($Path)
    $pe = [BitConverter]::ToInt32($b, 0x3C)
    if ([BitConverter]::ToUInt32($b, $pe) -ne 0x4550) { throw "Не PE-файл: $Path" }
    $nSec  = [BitConverter]::ToUInt16($b, $pe + 6)
    $optSz = [BitConverter]::ToUInt16($b, $pe + 20)
    $opt   = $pe + 24
    if ([BitConverter]::ToUInt16($b, $opt) -eq 0x20b) {
        $dd = $opt + 112; $imageBase = [int64][BitConverter]::ToUInt64($b, $opt + 24)
    } else {
        $dd = $opt + 96;  $imageBase = [int64][BitConverter]::ToUInt32($b, $opt + 28)
    }
    $nDirs = [BitConverter]::ToUInt32($b, $dd - 4)

    $secs = @(for ($i = 0; $i -lt $nSec; $i++) {
        $s = $opt + $optSz + 40 * $i
        $vs = [int64][BitConverter]::ToUInt32($b, $s + 8)
        $rs = [int64][BitConverter]::ToUInt32($b, $s + 16)
        [pscustomobject]@{
            VA   = [int64][BitConverter]::ToUInt32($b, $s + 12)
            Size = [Math]::Max($vs, $rs)
            Raw  = [int64][BitConverter]::ToUInt32($b, $s + 20)
        }
    })
    function RvaToOff([int64]$rva) {
        foreach ($s in $secs) {
            if ($rva -ge $s.VA -and $rva -lt ($s.VA + $s.Size)) { return [int64]($rva - $s.VA + $s.Raw) }
        }
        return [int64]-1
    }
    function ReadZ([int64]$off) {
        $e = $off
        while ($e -lt $b.Length -and $b[$e] -ne 0) { $e++ }
        return [Text.Encoding]::ASCII.GetString($b, [int]$off, [int]($e - $off))
    }

    $names = New-Object 'System.Collections.Generic.List[string]'
    # обычный импорт (каталог 1), дескриптор 20 байт
    if ($nDirs -gt 1) {
        $rva = [BitConverter]::ToUInt32($b, $dd + 8)
        if ($rva -ne 0) {
            $o = RvaToOff $rva
            while ($o -ge 0 -and ($o + 20) -le $b.Length) {
                $oft = [BitConverter]::ToUInt32($b, $o)
                $nr  = [BitConverter]::ToUInt32($b, $o + 12)
                $ft  = [BitConverter]::ToUInt32($b, $o + 16)
                if ($oft -eq 0 -and $nr -eq 0 -and $ft -eq 0) { break }
                $no = RvaToOff $nr
                if ($no -ge 0) { $names.Add((ReadZ $no)) }
                $o += 20
            }
        }
    }
    # отложенный импорт (каталог 13), дескриптор 32 байта
    if ($nDirs -gt 13) {
        $rva = [BitConverter]::ToUInt32($b, $dd + 13 * 8)
        if ($rva -ne 0) {
            $o = RvaToOff $rva
            while ($o -ge 0 -and ($o + 32) -le $b.Length) {
                $attr = [BitConverter]::ToUInt32($b, $o)
                $nr   = [int64][BitConverter]::ToUInt32($b, $o + 4)
                if ($nr -eq 0) { break }
                if (($attr -band 1) -eq 0) { $nr -= $imageBase }
                $no = RvaToOff $nr
                if ($no -ge 0) { $names.Add((ReadZ $no)) }
                $o += 32
            }
        }
    }
    return , $names.ToArray()
}

# Все не-системные DLL, нужные exe (рекурсивно). Возвращает @{ Found = [ordered]name->path; Missing = @() }
function Resolve-Dlls([string]$exe, [string[]]$dirs, [string[]]$extra = @()) {
    $found   = [ordered]@{}
    $missing = New-Object 'System.Collections.Generic.List[string]'
    $seen    = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    $queue   = New-Object 'System.Collections.Generic.Queue[string]'
    foreach ($n in (Get-PeImports $exe)) { $queue.Enqueue($n) }
    foreach ($n in $extra) { if ($n) { $queue.Enqueue($n) } }
    while ($queue.Count -gt 0) {
        $n = $queue.Dequeue()
        if (-not $seen.Add($n)) { continue }
        if ($n -match '^(api|ext)-ms-') { continue }
        $hit = $null
        foreach ($d in $dirs) {
            if (-not $d) { continue }
            $p = Join-Path $d $n
            if (Test-Path -LiteralPath $p -PathType Leaf) { $hit = $p; break }
        }
        if ($hit) {
            $found[$n] = $hit
            foreach ($m in (Get-PeImports $hit)) { $queue.Enqueue($m) }
        } elseif (-not $env:WINDIR -or -not (Test-Path -LiteralPath (Join-Path $env:WINDIR "System32\$n"))) {
            $missing.Add($n)
        }
    }
    return @{ Found = $found; Missing = $missing.ToArray() }
}

# Имена lib*.dll, которые exe грузит сам (LoadLibrary) — их нет в таблице импорта.
# Так SDL_mixer подгружает libvorbisfile-3.dll (музыка ogg), libmikmod, libfluidsynth.
function Get-DynamicDllNames([string]$Path) {
    $text = [Text.Encoding]::ASCII.GetString([IO.File]::ReadAllBytes($Path))
    $set = New-Object 'System.Collections.Generic.SortedSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    foreach ($m in [regex]::Matches($text, '(?<![\w.-])lib[A-Za-z0-9_+.-]{1,40}\.dll(?![A-Za-z0-9])', 'IgnoreCase')) { [void]$set.Add($m.Value) }
    return [string[]]@($set)
}

# ---------------------------------------------------------------- Enigma Virtual Box: проект .evb

function New-EvbText([string]$inputExe, [string]$outputExe, $dlls) {
    $esc = { param($s) [Security.SecurityElement]::Escape($s) }
    $fileEntries = foreach ($name in $dlls.Keys) {
@"
          <File>
            <Type>2</Type>
            <Name>$(& $esc $name)</Name>
            <File>$(& $esc $dlls[$name])</File>
            <ActiveX>False</ActiveX>
            <ActiveXInstall>False</ActiveXInstall>
            <Action>0</Action>
            <OverwriteDateTime>False</OverwriteDateTime>
            <OverwriteAttributes>False</OverwriteAttributes>
            <PassCommandLine>False</PassCommandLine>
            <HideFromDialogs>0</HideFromDialogs>
          </File>
"@
    }
    $registry = foreach ($r in 'Classes', 'User', 'Machine', 'Users', 'Config') {
@"
      <Registry>
        <Type>1</Type>
        <Virtual>True</Virtual>
        <Name>$r</Name>
        <ValueType>0</ValueType>
        <Value/>
        <Registries/>
      </Registry>
"@
    }
    $text = @"
<?xml version="1.0" encoding="windows-1252"?>
<>
  <InputFile>$(& $esc $inputExe)</InputFile>
  <OutputFile>$(& $esc $outputExe)</OutputFile>
  <Files>
    <Enabled>True</Enabled>
    <DeleteExtractedOnExit>False</DeleteExtractedOnExit>
    <CompressFiles>False</CompressFiles>
    <Files>
      <File>
        <Type>3</Type>
        <Name>%DEFAULT FOLDER%</Name>
        <Action>0</Action>
        <OverwriteDateTime>False</OverwriteDateTime>
        <OverwriteAttributes>False</OverwriteAttributes>
        <HideFromDialogs>0</HideFromDialogs>
        <Files>
$($fileEntries -join "`n")
        </Files>
      </File>
    </Files>
  </Files>
  <Registries>
    <Enabled>False</Enabled>
    <Registries>
$($registry -join "`n")
    </Registries>
  </Registries>
  <Packaging>
    <Enabled>False</Enabled>
  </Packaging>
  <Options>
    <ShareVirtualSystem>False</ShareVirtualSystem>
    <MapExecutableWithTemporaryFile>True</MapExecutableWithTemporaryFile>
    <TemporaryFileMask/>
    <AllowRunningOfVirtualExeFiles>True</AllowRunningOfVirtualExeFiles>
    <ProcessesOfAnyPlatforms>False</ProcessesOfAnyPlatforms>
  </Options>
  <Storage>
    <Files>
      <Enabled>False</Enabled>
      <Folder>%DEFAULT FOLDER%\</Folder>
      <RandomFileNames>False</RandomFileNames>
      <EncryptContent>False</EncryptContent>
    </Files>
  </Storage>
</>
"@
    return (($text -replace "`r`n", "`n") -replace "`n", "`r`n") + "`r`n"
}

# ---------------------------------------------------------------- дерево файлов

<#
  Один обход дерева: сколько файлов, сколько весит, что самое свежее и карта
  «путь от корня -> размер и время». Картой пользуются и выбор источника мода,
  и патч изменений, поэтому второй раз по двум гигабайтам ходить не приходится.
#>
function Get-TreeInfo([string]$root, [string[]]$excludeDirs = @()) {
    $info = @{ Root = $root; Num = 0; Bytes = [long]0; Newest = [datetime]'1980-01-01'; NewestFile = ''; Files = @{} }
    if (-not (Test-Path -LiteralPath $root)) { return $info }
    $full = (Resolve-Path -LiteralPath $root).Path.TrimEnd('\')
    $info.Root = $full
    $cut = $full.Length + 1
    $skip = @($excludeDirs | ForEach-Object { '\' + $_ + '\' })
    $di = New-Object IO.DirectoryInfo $full
    foreach ($f in $di.EnumerateFiles('*', [IO.SearchOption]::AllDirectories)) {
        $rel = $f.FullName.Substring($cut)
        $out = $false
        foreach ($s in $skip) {
            if (('\' + $rel).IndexOf($s, [StringComparison]::OrdinalIgnoreCase) -ge 0) { $out = $true; break }
        }
        if ($out) { continue }
        $info.Files[$rel] = ('{0}:{1}' -f $f.Length, $f.LastWriteTimeUtc.Ticks)
        $info.Num++
        $info.Bytes += $f.Length
        if ($f.LastWriteTimeUtc -gt $info.Newest) { $info.Newest = $f.LastWriteTimeUtc; $info.NewestFile = $rel }
    }
    return $info
}

# ---------------------------------------------------------------- проверки: на этом сборка останавливается

<#
  Рядом с деревом исходников может лежать его копия, и ninja собирать именно её:
  правка наложена, сборка зелёная, а в exe ничего нет. Это грабли R-023.
#>
function Assert-BuildTree([string]$buildDir) {
    $cache = Join-Path $buildDir 'CMakeCache.txt'
    if (-not (Test-Path -LiteralPath $cache)) { throw "Нет $cache — папка сборки не настроена (BuildDir)" }
    $m = Select-String -LiteralPath $cache -Pattern '^CMAKE_HOME_DIRECTORY:INTERNAL=(.+)$' | Select-Object -First 1
    if (-not $m) { throw "В $cache нет строки CMAKE_HOME_DIRECTORY" }
    $tree = $m.Matches[0].Groups[1].Value.Replace('/', '\').TrimEnd('\')
    $mine = $repoDir.Replace('/', '\').TrimEnd('\')
    if ($tree -ne $mine) {
        throw "Сборка настроена на другое дерево исходников: $tree, а собираем $mine (грабли R-023). Перенастройте cmake или RepoDir в build_config.json"
    }
    Write-Ok "дерево сборки то самое: $tree"
}

<#
  exe старше самого свежего исходника — значит ninja не гоняли или он упал.
  Без этой проверки -NoNinja молча упакует вчерашнюю сборку.
#>
function Assert-ExeFresh([string]$exe) {
    $src = Join-Path $repoDir 'src'
    if (-not (Test-Path -LiteralPath $src)) { return }
    $newest = $null
    $di = New-Object IO.DirectoryInfo $src
    foreach ($f in $di.EnumerateFiles('*', [IO.SearchOption]::AllDirectories)) {
        if ($f.Extension -notin '.cpp', '.h', '.txt') { continue }
        if (-not $newest -or $f.LastWriteTimeUtc -gt $newest.LastWriteTimeUtc) { $newest = $f }
    }
    if (-not $newest) { return }
    $exeItem = Get-Item -LiteralPath $exe
    if ($newest.LastWriteTimeUtc -gt $exeItem.LastWriteTimeUtc) {
        throw ("exe старше исходников: {0} изменён {1:dd.MM HH:mm}, а exe от {2:dd.MM HH:mm}. Соберите ninja (в окне — галочка «Пересобрать»)" -f $newest.Name, $newest.LastWriteTime, $exeItem.LastWriteTime)
    }
    Write-Ok ("exe новее исходников (самый свежий из них: {0}, {1:dd.MM HH:mm})" -f $newest.Name, $newest.LastWriteTime)
}

<#
  Святое правило (грабли R-003): common и standard в репозитории и в установке игры
  обязаны совпадать побайтно. Разошлись — значит правку не перенесли, и игрок увидит
  не то, что собрано, а на второй машине будет третий вариант.
#>
function Assert-DataSync {
    $gameDir = Get-Cfg 'GameDir' ''
    if (-not $gameDir) { Write-Warn 'GameDir не задан — сверку common/standard с установкой пропускаю'; return }
    if (-not (Test-Path -LiteralPath $gameDir)) { Write-Warn "нет папки игры $gameDir — сверку пропускаю"; return }
    $bad = New-Object Collections.Generic.List[string]
    foreach ($name in @(Get-Cfg 'DataDirs' @())) {
        $a = Join-Path (Join-Path $repoDir 'bin') $name
        $b = Join-Path $gameDir $name
        if (-not (Test-Path -LiteralPath $a)) { continue }
        if (-not (Test-Path -LiteralPath $b)) { $bad.Add("$name — нет в установке игры"); continue }
        $ta = Get-TreeInfo $a
        $tb = Get-TreeInfo $b
        foreach ($rel in $ta.Files.Keys) {
            if (-not $tb.Files.ContainsKey($rel)) { $bad.Add("$name\$rel — нет в установке"); continue }
            if (($ta.Files[$rel] -split ':')[0] -ne ($tb.Files[$rel] -split ':')[0]) { $bad.Add("$name\$rel — другой размер"); continue }
            $ha = (Get-FileHash -LiteralPath (Join-Path $a $rel) -Algorithm MD5).Hash
            $hb = (Get-FileHash -LiteralPath (Join-Path $b $rel) -Algorithm MD5).Hash
            if ($ha -ne $hb) { $bad.Add("$name\$rel — другое содержимое") }
        }
        foreach ($rel in $tb.Files.Keys) {
            if (-not $ta.Files.ContainsKey($rel)) { $bad.Add("$name\$rel — есть в установке, нет в репозитории") }
        }
    }
    if ($bad.Count) {
        $head = (($bad | Select-Object -First 8) -join '; ')
        if ($bad.Count -gt 8) { $head += ' …' }
        throw ("Данные движка разошлись с установкой игры ({0} шт.): {1}. Святое правило, грабли R-003: перенесите правку в установку и повторите её на второй машине" -f $bad.Count, $head)
    }
    Write-Ok ('common/standard в репозитории и в установке совпадают побайтно')
}

<#
  Второй шаг Святого правила делается сам: common и standard из репозитория переносятся
  в установку игры (GameDir) — только те файлы, что отличаются. exe без своих данных
  показывает STR_ вместо строк, поэтому данные едут вместе с ним.
  Правка, сделанная прямо в установке (файл там НОВЕЕ и другой), не затирается:
  сборка останавливается и просит перенести её в репозиторий. Лишнее в установке не удаляется.
#>
function Sync-DataToGame {
    $gameDir = Get-Cfg 'GameDir' ''
    if (-not $gameDir -or -not (Test-Path -LiteralPath $gameDir)) { Write-Warn "нет папки игры '$gameDir' — common/standard в установку не переношу"; return }
    Write-Step "common/standard -> $gameDir"
    $copy = New-Object Collections.Generic.List[object]
    $conflicts = New-Object Collections.Generic.List[string]
    $extra = 0
    foreach ($name in @(Get-Cfg 'DataDirs' @())) {
        $a = Join-Path (Join-Path $repoDir 'bin') $name
        $b = Join-Path $gameDir $name
        if (-not (Test-Path -LiteralPath $a)) { continue }
        $ta = Get-TreeInfo $a
        $tb = Get-TreeInfo $b
        foreach ($rel in $ta.Files.Keys) {
            $from = Join-Path $a $rel
            $to = Join-Path $b $rel
            if ($tb.Files.ContainsKey($rel)) {
                $same = ($ta.Files[$rel] -split ':')[0] -eq ($tb.Files[$rel] -split ':')[0] -and
                        (Get-FileHash -LiteralPath $from -Algorithm MD5).Hash -eq (Get-FileHash -LiteralPath $to -Algorithm MD5).Hash
                if ($same) { continue }
                if ((Get-Item -LiteralPath $to).LastWriteTimeUtc -gt (Get-Item -LiteralPath $from).LastWriteTimeUtc) {
                    $conflicts.Add("$name\$rel"); continue
                }
            }
            $copy.Add([pscustomobject]@{ From = $from; To = $to; Rel = "$name\$rel" })
        }
        foreach ($rel in $tb.Files.Keys) { if (-not $ta.Files.ContainsKey($rel)) { $extra++ } }
    }
    if ($conflicts.Count) {
        $head = (($conflicts | Select-Object -First 8) -join '; ')
        throw ("В установке игры правка новее репозитория ({0} шт.): {1}. Перенесите её в bin\ и повторите сборку — затирать не буду" -f $conflicts.Count, $head)
    }
    foreach ($c in $copy) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $c.To) | Out-Null
        Copy-Item -LiteralPath $c.From -Destination $c.To -Force
        Write-Info "обновлён $($c.Rel)"
    }
    if ($copy.Count) { Write-Ok ("перенесено файлов: {0}. На второй машине повторить: common/standard едут в архиве _exe.zip" -f $copy.Count) }
    else { Write-Ok 'уже совпадают' }
    if ($extra) { Write-Warn "в установке есть $extra файлов, которых нет в репозитории; не удаляю" }
}

<#
  Мод без своих ключевых файлов собирать незачем: без шрифтов HD-текст у игрока
  молча становится классическим, без metadata.yml мода просто нет в списке.
#>
function Assert-ModContents([string]$dest, [string]$name) {
    $need = @('metadata.yml')
    $rules = Get-Cfg 'ModRequire' $null
    if ($rules -and ($rules.PSObject.Properties.Name -contains $name)) { $need = @($rules.$name) }
    $miss = @($need | Where-Object { -not (Test-Path -LiteralPath (Join-Path $dest $_)) })
    if ($miss.Count) { throw ("в моде {0} не хватает: {1}" -f $name, ($miss -join ', ')) }
    Write-Ok ("на месте: {0}" -f ($need -join ', '))
}

# ---------------------------------------------------------------- слепок сборки и патч

function Save-Manifest([string]$path, $tree) {
    $sb = New-Object Text.StringBuilder
    foreach ($rel in $tree.Files.Keys) { [void]$sb.AppendLine($tree.Files[$rel] + "`t" + $rel) }
    [IO.File]::WriteAllText($path, $sb.ToString(), (New-Object Text.UTF8Encoding $true))
}

function Read-Manifest([string]$path) {
    if (-not (Test-Path -LiteralPath $path)) { return $null }
    $map = @{}
    foreach ($line in [IO.File]::ReadAllLines($path, [Text.Encoding]::UTF8)) {
        $i = $line.IndexOf("`t")
        if ($i -lt 1) { continue }
        $map[$line.Substring($i + 1)] = $line.Substring(0, $i)
    }
    return $map
}

<#
  Патч — те же файлы стейджа, но только изменившиеся с прошлой сборки того же вида.
  Раскладка внутри такая же, поэтому распаковывается поверх игры точно так же.
  Опознаём изменение по размеру и времени файла — robocopy время источника сохраняет.
#>
function New-PatchStep([string]$kind, $tree, [string]$zip, [string[]]$head) {
    $manifest = Join-Path $workDir "manifest_$kind.txt"
    $prev = Read-Manifest $manifest
    if (-not $prev) {
        Write-Info 'патча нет: прошлой сборки этого вида не найдено, сравнивать не с чем'
        Save-Manifest $manifest $tree
        return $null
    }
    Write-Step 'патч: что изменилось с прошлой сборки'
    $changed = @($tree.Files.Keys | Where-Object { -not $prev.ContainsKey($_) -or $prev[$_] -ne $tree.Files[$_] })
    $gone = @($prev.Keys | Where-Object { -not $tree.Files.ContainsKey($_) })
    if (-not $changed.Count -and -not $gone.Count) {
        Write-Info 'ничего не изменилось — патч не нужен'
        Save-Manifest $manifest $tree
        return $null
    }
    $patchDir = Join-Path $distDir '_patch'
    if (Test-Path -LiteralPath $patchDir) { Remove-Item -LiteralPath $patchDir -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $patchDir | Out-Null
    $bytes = [long]0
    foreach ($rel in $changed) {
        $to = Join-Path $patchDir $rel
        New-Item -ItemType Directory -Force -Path (Split-Path $to -Parent) | Out-Null
        Copy-Item -LiteralPath (Join-Path $stageDir $rel) -Destination $to -Force
        $bytes += (Get-Item -LiteralPath $to).Length
    }
    $txt = @($head) + @(
        '',
        'Это ПАТЧ: только то, что изменилось с прошлой сборки.',
        'Распаковать поверх игры с заменой файлов — полный архив для этого не нужен.',
        ''
    )
    if ($gone.Count) {
        $txt += ("В новой версии этих файлов нет — сотрите их руками ({0} шт.):" -f $gone.Count)
        $txt += $gone
    }
    $txt | Set-Content -LiteralPath (Join-Path $patchDir 'HD_PATCH.txt') -Encoding UTF8
    Write-Ok ("изменилось {0:N0} файлов, {1}; удалено с прошлого раза: {2}" -f $changed.Count, (Format-Size $bytes), $gone.Count)
    New-Zip $zip $patchDir
    Save-Manifest $manifest $tree
    return $zip
}

<#
  Две записки в корне архива: HD_README.txt — что с этим делать, HD_VERSION.txt — чем
  это собрано. Вторая нужна, когда через месяц спрашивают, что у человека стоит.
#>
function Save-StageNotes([string[]]$head, $mods, [string[]]$data, [string]$exeName) {
    $names = @($mods | ForEach-Object { $_.Name })
    $readme = @($head) + @(
        '',
        '1. Распаковать архив в папку игры (где лежит OpenXcomEx.exe и папка user), с заменой файлов.'
    )
    $modLine = if ($names.Count) { 'Включить в списке модов: {0}. ' -f ($names -join ', ') } else { '' }
    if ($exeName) {
        $readme += @("2. Запускать $exeName.", "3. ${modLine}HD-опции — Настройки -> HD.")
    } else {
        $readme += "2. ${modLine}HD-опции — Настройки -> HD."
    }
    if ($data.Count) {
        $readme += @('', ("В архиве есть и папки движка ({0}) — они заменят те, что лежат в игре." -f ($data -join ', ')))
    }
    $readme | Set-Content -LiteralPath (Join-Path $stageDir 'HD_README.txt') -Encoding UTF8

    $ver = @($head) + @('')
    if ($exeName) { $ver += "exe:    $exeName" }
    $ver += "ветка:  $branch"
    $ver += "коммит: $hash"
    foreach ($m in $mods) {
        $ver += ("мод {0}: {1:N0} файлов, {2}   <- {3}" -f $m.Name, $m.Num, (Format-Size $m.Bytes), $m.Source)
    }
    if ($data.Count) { $ver += ("данные движка: {0}" -f ($data -join ', ')) }
    $ver | Set-Content -LiteralPath (Join-Path $stageDir 'HD_VERSION.txt') -Encoding UTF8
}

# ---------------------------------------------------------------- шаги

function Invoke-ExeStep {
    $buildDir = Get-Cfg 'BuildDir' (Join-Path $repoDir 'build-release')
    $msysBin  = Get-Cfg 'MsysBin' 'C:\msys64\mingw64\bin'
    $exe      = Join-Path $buildDir 'bin\openxcom.exe'

    if (Test-Path -LiteralPath $msysBin) { $env:PATH = "$msysBin;$env:PATH" }
    else { Write-Warn "нет папки MSYS2: $msysBin (MsysBin в build_config.json)" }

    Write-Step 'проверки перед сборкой'
    Assert-BuildTree $buildDir

    if (-not $NoNinja) {
        Write-Step "ninja  ($buildDir)"
        $ninja = Find-Tool (Get-Cfg 'Ninja' '') @((Join-Path $msysBin 'ninja.exe')) 'ninja'
        if (-not $ninja) { throw 'ninja не найден (Ninja в build_config.json)' }
        $t = [Diagnostics.Stopwatch]::StartNew()
        $code = Invoke-Native $ninja @('-C', $buildDir)
        if ($code -ne 0) { throw "ninja завершился с ошибкой (код $code)" }
        Write-Ok ("сборка ок за {0:N0} с" -f $t.Elapsed.TotalSeconds)
    } else {
        Write-Step 'ninja пропущен (-NoNinja)'
    }

    if (-not (Test-Path -LiteralPath $exe)) { throw "Нет $exe" }
    $exeInfo = Get-Item -LiteralPath $exe
    Write-Info ("openxcom.exe: {0}, от {1:dd.MM HH:mm}" -f (Format-Size $exeInfo.Length), $exeInfo.LastWriteTime)
    Assert-ExeFresh $exe

    Write-Step 'DLL, которые нужны exe'
    $dirs = @($msysBin) + @(Get-Cfg 'ExtraDllDirs' @()) + @((Join-Path $buildDir 'bin'))
    $dlls = [ordered]@{}
    $dynamic = @(Get-Cfg 'DynamicDlls' @('libvorbisfile-3.dll'))
    try {
        $res = Resolve-Dlls $exe $dirs $dynamic
        $dlls = $res.Found
        $skipped = @(Get-DynamicDllNames $exe | Where-Object { -not $dlls.Contains($_) })
        if ($skipped.Count) {
            Write-Info ("exe умеет подгружать ещё: {0} — не вшиты (если нужны, добавьте в DynamicDlls)" -f ($skipped -join ', '))
        }
        foreach ($m in $res.Missing) { Write-Warn "не найдена $m — на другой машине exe может не запуститься (добавьте папку в ExtraDllDirs)" }
    } catch {
        Write-Warn "не удалось прочитать импорт exe ($($_.Exception.Message)); беру список FallbackDlls"
        foreach ($n in @(Get-Cfg 'FallbackDlls' @())) {
            foreach ($d in $dirs) { $p = Join-Path $d $n; if (Test-Path -LiteralPath $p) { $dlls[$n] = $p; break } }
            if (-not $dlls.Contains($n)) { Write-Warn "не найдена $n" }
        }
    }
    foreach ($k in $dlls.Keys) { Write-Info ("{0,-24} {1}" -f $k, $dlls[$k]) }

    $boxed = Join-Path $workDir 'openxcom_boxed.exe'
    if ($dlls.Count -eq 0) {
        Write-Ok 'внешних DLL нет — Enigma не нужна, exe берётся как есть'
        Copy-Item -LiteralPath $exe -Destination $boxed -Force
    } else {
        Write-Step 'Enigma Virtual Box'
        $enigma = Find-Tool (Get-Cfg 'EnigmaConsole' '') @(
            (Join-IfSet ${env:ProgramFiles(x86)} 'Enigma Virtual Box\enigmavbconsole.exe'),
            (Join-IfSet $env:ProgramFiles 'Enigma Virtual Box\enigmavbconsole.exe')
        ) 'enigmavbconsole'
        if (-not $enigma) { throw 'enigmavbconsole.exe не найден — укажите путь в EnigmaConsole (build_config.json)' }
        $evb = Join-Path $workDir 'openxcom.evb'
        [IO.File]::WriteAllText($evb, (New-EvbText $exe $boxed $dlls), (New-Object Text.UTF8Encoding $true))
        Remove-Item -LiteralPath $boxed -Force -ErrorAction SilentlyContinue
        $code = Invoke-Native $enigma @($evb)
        if (-not (Test-Path -LiteralPath $boxed)) { throw "Enigma не создала $boxed (код $code). Проект: $evb" }
        if ($code -ne 0) { Write-Warn "enigmavbconsole вернул код $code, но файл создан" }
        Write-Ok ("упаковано: {0}" -f (Format-Size (Get-Item -LiteralPath $boxed).Length))
    }
    return $boxed
}

<#
  Какие моды класть в релиз — ключ Mods в настройках. У каждого мода может быть две
  копии: в репозитории (туда по умолчанию пишут gen_hd и build_pack) и в установке игры
  (её видит игрок). Берём свежую и говорим об этом вслух — грабли R-015.
#>
function Get-ModList {
    $names = @(Get-Cfg 'Mods' @())
    if (-not $names.Count) {
        $legacy = Get-Cfg 'ModDir' ''
        if (-not $legacy) { throw 'Не сказано, какие моды класть: ключ Mods в build_config.json' }
        return @([pscustomobject]@{ Name = (Split-Path $legacy -Leaf); Sources = @($legacy) })
    }
    $gameDir = Get-Cfg 'GameDir' ''
    $out = @()
    foreach ($n in $names) {
        $src = @()
        foreach ($root in @((Join-Path $repoDir 'user\mods'), (Join-IfSet $gameDir 'user\mods'))) {
            if (-not $root) { continue }
            $p = Join-Path $root $n
            if (Test-Path -LiteralPath $p) { $src += $p }
        }
        if (-not $src.Count) { throw "Мод $n не найден ни в репозитории, ни в установке игры" }
        $out += [pscustomobject]@{ Name = $n; Sources = $src }
    }
    return $out
}

function Select-ModSource($mod, [string[]]$excludeDirs) {
    $trees = @()
    foreach ($s in $mod.Sources) {
        $t = Get-TreeInfo $s $excludeDirs
        Write-Info ("{0}: {1:N0} файлов, {2}, свежайший {3:dd.MM HH:mm} ({4})" -f $s, $t.Num, (Format-Size $t.Bytes), $t.Newest.ToLocalTime(), $t.NewestFile)
        $trees += $t
    }
    # явный выбор в настройках сильнее любых догадок
    $pick = Get-Cfg 'ModSource' $null
    if ($pick -and ($pick.PSObject.Properties.Name -contains $mod.Name)) {
        $want = [string]$pick.($mod.Name)
        $root = if ($want -eq 'repo') { Join-Path $repoDir 'user\mods' } else { Join-IfSet (Get-Cfg 'GameDir' '') 'user\mods' }
        $exp = if ($root) { Join-Path $root $mod.Name } else { '' }
        $chosen = @($trees | Where-Object { $exp -and $_.Root -eq (Resolve-Path -LiteralPath $exp -ErrorAction SilentlyContinue).Path.TrimEnd('\') })
        if (-not $chosen.Count) { throw ("ModSource для мода {0} говорит «{1}», а такой копии нет: {2}" -f $mod.Name, $want, $exp) }
        Write-Info ("источник задан в настройках (ModSource: {0})" -f $want)
        return $chosen[0].Root
    }
    $best = @($trees | Sort-Object Newest -Descending)[0]
    if ($trees.Count -gt 1) {
        Write-Warn ("у мода {0} две копии — беру свежую: {1}. Если правили другую, правка в релиз не попадёт (грабли R-015)" -f $mod.Name, $best.Root)
        # свежая, но заметно меньше другой — это не «новее», это недописанная копия
        foreach ($t in $trees) {
            if ($t.Root -eq $best.Root) { continue }
            if ($best.Num -lt $t.Num * 0.9) {
                throw ("свежая копия мода {0} заметно меньше другой: {1:N0} файлов в {2} против {3:N0} в {4}. Релиз вышел бы неполным — выберите источник явно (ключ ModSource в build_config.json: repo или game)" -f $mod.Name, $best.Num, $best.Root, $t.Num, $t.Root)
            }
        }
    }
    return $best.Root
}

function Invoke-ModStep {
    $mods = Get-ModList
    $xd = @(Get-Cfg 'ModExcludeDirs' @())
    $xf = @(Get-Cfg 'ModExcludeFiles' @())
    $modsRoot = Join-Path $stageDir 'user\mods'
    New-Item -ItemType Directory -Force -Path $modsRoot | Out-Null
    $names = @($mods | ForEach-Object { $_.Name })
    # чужое из прошлых запусков в стейдже не оставляем
    Get-ChildItem -LiteralPath $modsRoot -Directory -ErrorAction SilentlyContinue |
        Where-Object { $names -notcontains $_.Name } | Remove-Item -Recurse -Force
    $done = @()
    foreach ($mod in $mods) {
        Write-Step "мод $($mod.Name)"
        $src = Select-ModSource $mod $xd
        $dest = Join-Path $modsRoot $mod.Name
        # зеркало: при повторных запусках копируется только изменённое
        $rc = @($src, $dest, '/MIR', '/MT:16', '/R:1', '/W:1', '/NFL', '/NDL', '/NP', '/NJH', '/NJS')
        if ($xd.Count) { $rc += '/XD'; $rc += $xd }
        if ($xf.Count) { $rc += '/XF'; $rc += $xf }
        $t = [Diagnostics.Stopwatch]::StartNew()
        $code = Invoke-Native 'robocopy.exe' $rc
        if ($code -ge 8) { throw "robocopy: ошибка копирования мода $($mod.Name) (код $code)" }
        $tree = Get-TreeInfo $dest
        Write-Ok ("{0:N0} файлов, {1}, за {2:N0} с  (исключено: {3})" -f $tree.Num, (Format-Size $tree.Bytes), $t.Elapsed.TotalSeconds, (($xd + $xf) -join ', '))
        Assert-ModContents $dest $mod.Name
        $done += [pscustomobject]@{ Name = $mod.Name; Source = $src; Num = $tree.Num; Bytes = $tree.Bytes }
    }
    return $done
}

function Invoke-DataStep {
    # папки данных движка (common, standard) кладём рядом с exe: архив становится
    # самодостаточным, и версия из репозитория не может разойтись с установкой (грабли R-003)
    $names = @(Get-Cfg 'DataDirs' @())
    if (-not $names.Count) { Write-Info 'DataDirs пуст — данные движка не кладём'; return @() }
    Assert-DataSync
    $src = Get-Cfg 'DataSource' ''
    if (-not $src) { $src = Join-Path $repoDir 'bin' }
    Write-Step "данные движка: $src"
    $done = @()
    foreach ($name in $names) {
        $from = Join-Path $src $name
        if (-not (Test-Path -LiteralPath $from)) { Write-Warn "нет папки $from — пропускаю"; continue }
        $to = Join-Path $stageDir $name
        $code = Invoke-Native 'robocopy.exe' @($from, $to, '/MIR', '/MT:16', '/R:1', '/W:1', '/NFL', '/NDL', '/NP', '/NJH', '/NJS')
        if ($code -ge 8) { throw "robocopy: ошибка копирования $name (код $code)" }
        $files = Get-ChildItem -LiteralPath $to -Recurse -File
        $sum = ($files | Measure-Object Length -Sum).Sum
        Write-Ok ("{0}: {1:N0} файлов, {2}" -f $name, $files.Count, (Format-Size $sum))
        $done += $name
    }
    return $done
}

function Clear-DataDirs {
    # в стейдже они могли остаться с прошлого запуска, а этому варианту не нужны
    foreach ($name in @(Get-Cfg 'DataDirs' @())) {
        $p = Join-Path $stageDir $name
        if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Recurse -Force }
    }
}

function New-Zip([string]$zip, [string]$dir) {
    Write-Step 'архив'
    Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue
    $items = @(Get-ChildItem -LiteralPath $dir -Name)
    $t = [Diagnostics.Stopwatch]::StartNew()
    $sevenZip = Find-Tool (Get-Cfg 'SevenZip' '') @(
        (Join-IfSet $env:ProgramFiles '7-Zip\7z.exe'),
        (Join-IfSet ${env:ProgramFiles(x86)} '7-Zip\7z.exe')
    ) '7z'
    $tar = Join-IfSet $env:WINDIR 'System32\tar.exe'
    if ($sevenZip) {
        Write-Info "7-Zip: $sevenZip"
        $code = Invoke-Native $sevenZip (@('a', '-tzip', '-mx=1', '-mmt=on', '-bso0', '-bsp1', $zip) + $items) $dir
        if ($code -ne 0) { throw "7-Zip: ошибка (код $code)" }
    } elseif ($tar -and (Test-Path -LiteralPath $tar)) {
        Write-Info 'tar.exe (встроенный в Windows); с 7-Zip было бы быстрее'
        $code = Invoke-Native $tar (@('-a', '-c', '-f', $zip, '-C', $dir) + $items)
        if ($code -ne 0) { throw "tar: ошибка (код $code)" }
    } else {
        Write-Info 'Compress-Archive (медленно; поставьте 7-Zip)'
        Compress-Archive -Path (Join-Path $dir '*') -DestinationPath $zip -CompressionLevel Fastest
    }
    if (-not (Test-Path -LiteralPath $zip)) { throw "архив не создан: $zip" }
    Write-Ok ("{0} за {1:N0} с" -f (Format-Size (Get-Item -LiteralPath $zip).Length), $t.Elapsed.TotalSeconds)
}

<#
  Имя готового файла по образцу из настроек: {stamp} -> 2026-09-19_1543, {date} -> 2026-09-19,
  {time} -> 1543, {hash} -> 833caf8d5(-dirty), {branch} -> hd-render. Что не подставляется —
  остаётся как написано, так что образец без скобок даёт постоянное имя.
#>
function Expand-NameTemplate([string]$template, [hashtable]$values) {
    $out = $template
    foreach ($key in $values.Keys) { $out = $out.Replace('{' + $key + '}', [string]$values[$key]) }
    # недопустимое в имени файла — в подчёркивание, иначе Copy-Item упадёт на полпути
    foreach ($ch in [IO.Path]::GetInvalidFileNameChars()) { $out = $out.Replace([string]$ch, '_') }
    return $out.Trim()
}

<#
  Маска «свои прошлые файлы» для того же образца: каждая подстановка становится звёздочкой.
  Из образца без единой скобки маски не выйдет — тогда чистить нечего и незачем.
#>
function Get-NameMask([string]$template) {
    $mask = [regex]::Replace($template, '\{[a-z]+\}', '*')
    while ($mask.Contains('**')) { $mask = $mask.Replace('**', '*') }
    if ($mask -eq '*' -or -not $mask.Contains('*')) { return '' }
    return $mask
}

function Remove-OldResults([string]$pattern) {
    $keep = [int](Get-Cfg 'KeepLast' 5)
    if ($keep -le 0) { return }
    Get-ChildItem -LiteralPath $distDir -File -Filter $pattern |
        Sort-Object LastWriteTime -Descending | Select-Object -Skip $keep |
        ForEach-Object { Write-Info "удаляю старый: $($_.Name)"; Remove-Item -LiteralPath $_.FullName -Force }
}

# ---------------------------------------------------------------- main

$failed = $false
$resultFile = $null
# журнал последнего запуска и текст ошибки — окно с кнопками показывает их, если сборка упала
$logFile = Join-Path $env:TEMP 'oxce_build.log'
$errFile = Join-Path $env:TEMP 'oxce_build_error.txt'
Remove-Item -LiteralPath $errFile -Force -ErrorAction SilentlyContinue
try { Start-Transcript -LiteralPath $logFile -Force | Out-Null } catch {}
try {
    $scriptDir = $PSScriptRoot
    if (-not $scriptDir) { $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }
    if (-not $Config) { $Config = Join-Path $scriptDir 'build_config.json' }
    if (-not (Test-Path -LiteralPath $Config)) { throw "Нет файла настроек: $Config" }
    $script:cfg = Get-Content -LiteralPath $Config -Raw -Encoding UTF8 | ConvertFrom-Json

    $repoDir = Get-Cfg 'RepoDir' ''
    if (-not $repoDir) { $repoDir = (Resolve-Path (Join-Path $scriptDir '..\..')).Path }
    $distDir = Get-Cfg 'DistDir' (Join-Path $repoDir 'dist')
    $workDir = Join-Path $distDir '_work'
    $stageDir = Join-Path $distDir '_stage'
    $resultFile = Join-Path $distDir 'last_result.txt'
    $exeName = Get-Cfg 'ExeName' 'openxcom_hd.exe'
    New-Item -ItemType Directory -Force -Path $distDir, $workDir, $stageDir | Out-Null
    Remove-Item -LiteralPath $resultFile -Force -ErrorAction SilentlyContinue

    $hash = 'nogit'; $branch = ''
    if (Get-Command git -ErrorAction SilentlyContinue) {
        $h = Get-NativeOutput 'git' @('-C', $repoDir, 'rev-parse', '--short', 'HEAD') | Select-Object -First 1
        if ($h -is [string] -and $h -match '^[0-9a-f]+$') { $hash = $h }
        $br = Get-NativeOutput 'git' @('-C', $repoDir, 'rev-parse', '--abbrev-ref', 'HEAD') | Select-Object -First 1
        if ($br -is [string]) { $branch = $br }
        $dirty = Get-NativeOutput 'git' @('-C', $repoDir, 'status', '--porcelain', '--untracked-files=no', '--', 'src')
        if (@($dirty | Where-Object { $_ -is [string] -and $_.Trim() }).Count -gt 0) { $hash += '-dirty' }
    }
    $now = Get-Date
    $stamp = $now.ToString('yyyy-MM-dd_HHmm')
    $base = "OXCE-HD_${stamp}_$hash"
    # имя готового exe задаётся образцом: его видит игрок и по нему же OBS ищет окно
    $exeTemplate = Get-Cfg 'ExeResultName' 'OpenXComEx_{stamp}'
    $nameValues = @{
        stamp  = $stamp
        date   = $now.ToString('yyyy-MM-dd')
        time   = $now.ToString('HHmm')
        hash   = $hash
        branch = $branch
    }
    $exeBase = Expand-NameTemplate $exeTemplate $nameValues
    if (-not $exeBase) { $exeBase = "OpenXComEx_$stamp" }
    Write-Host ("OXCE HD сборка: {0}   ветка {1}, {2}" -f $Target, $branch, $hash) -ForegroundColor White

    # в корне стейджа — только то, что нужно этому варианту
    Get-ChildItem -LiteralPath $stageDir -File | Remove-Item -Force

    $result = $null
    $patch = $null
    # до сборки: и exe, и архивы берут common/standard из репозитория, установка должна им совпадать
    if (Get-Cfg 'SyncDataToGame' $true) { Sync-DataToGame }
    switch ($Target) {
        'Exe' {
            $boxed = Invoke-ExeStep
            $result = Join-Path $distDir "$exeBase.exe"
            Copy-Item -LiteralPath $boxed -Destination $result -Force
            $mask = Get-NameMask $exeTemplate
            if ($mask) { Remove-OldResults "$mask.exe" }
            else { Write-Warn "ExeResultName без {stamp} — старые exe не чищу, имя одно и то же" }
            # для второй машины: exe вместе со своими common/standard, моды не нужны
            $stageMods = Join-Path $stageDir 'user'
            if (Test-Path -LiteralPath $stageMods) { Remove-Item -LiteralPath $stageMods -Recurse -Force }
            $data = @(Invoke-DataStep)
            Copy-Item -LiteralPath $boxed -Destination (Join-Path $stageDir $exeName) -Force
            Save-StageNotes @("OXCE HD — $exeName и данные движка ($stamp, $branch $hash)") @() $data $exeName
            $exeZip = Join-Path $distDir "${base}_exe.zip"
            New-Zip $exeZip $stageDir
            Remove-OldResults 'OXCE-HD_*_exe.zip'
            Write-Ok "для второй машины: $exeZip"
        }
        'Mod' {
            $mods = @(Invoke-ModStep)
            $data = @(Invoke-DataStep)
            $head = @("OXCE HD — моды ($stamp, $branch $hash)")
            Save-StageNotes $head $mods $data $null
            $tree = Get-TreeInfo $stageDir
            $result = Join-Path $distDir "${base}_mod.zip"
            New-Zip $result $stageDir
            Remove-OldResults 'OXCE-HD_*_mod.zip'
            $patch = New-PatchStep 'mod' $tree (Join-Path $distDir "${base}_mod_patch.zip") $head
            Remove-OldResults 'OXCE-HD_*_mod_patch.zip'
        }
        'Both' {
            $boxed = Invoke-ExeStep
            $mods = @(Invoke-ModStep)
            $data = @(Invoke-DataStep)
            Copy-Item -LiteralPath $boxed -Destination (Join-Path $stageDir $exeName) -Force
            $head = @("OXCE HD — $exeName и моды ($stamp, $branch $hash)")
            Save-StageNotes $head $mods $data $exeName
            $tree = Get-TreeInfo $stageDir
            $result = Join-Path $distDir "${base}_full.zip"
            New-Zip $result $stageDir
            Remove-OldResults 'OXCE-HD_*_full.zip'
            $patch = New-PatchStep 'full' $tree (Join-Path $distDir "${base}_full_patch.zip") $head
            Remove-OldResults 'OXCE-HD_*_full_patch.zip'
        }
    }

    $copyTo = Get-Cfg 'CopyExeTo' ''
    if ($copyTo -and $Target -ne 'Mod') {
        if (Test-Path -LiteralPath $copyTo) {
            Copy-Item -LiteralPath (Join-Path $workDir 'openxcom_boxed.exe') -Destination (Join-Path $copyTo $exeName) -Force
            Write-Info "exe также скопирован в $copyTo\$exeName"
        } else { Write-Warn "CopyExeTo: нет папки $copyTo" }
    }

    [IO.File]::WriteAllText($resultFile, $result, (New-Object Text.UTF8Encoding $false))
    $patchFile = Join-Path $distDir 'last_patch.txt'
    Remove-Item -LiteralPath $patchFile -Force -ErrorAction SilentlyContinue
    if ($patch) {
        [IO.File]::WriteAllText($patchFile, $patch, (New-Object Text.UTF8Encoding $false))
        Write-Host ("ПАТЧ:  {0}  ({1})" -f $patch, (Format-Size (Get-Item -LiteralPath $patch).Length)) -ForegroundColor Green
    }
    Write-Host ''
    Write-Host ("ГОТОВО за {0:mm\:ss}:  {1}  ({2})" -f $clock.Elapsed, $result, (Format-Size (Get-Item -LiteralPath $result).Length)) -ForegroundColor Green
    if (-not $FromGui -and (Get-Cfg 'OpenExplorer' $true)) { Start-Process explorer.exe "/select,`"$result`"" }
} catch {
    $failed = $true
    Write-Host ''
    Write-Host "ОШИБКА: $($_.Exception.Message)" -ForegroundColor Red
    if ($_.InvocationInfo) { Write-Host $_.InvocationInfo.PositionMessage -ForegroundColor DarkGray }
    try { [IO.File]::WriteAllText($errFile, $_.Exception.Message, (New-Object Text.UTF8Encoding $false)) } catch {}
}
try { Stop-Transcript | Out-Null } catch {}

if ($failed) { exit 1 } else { exit 0 }
