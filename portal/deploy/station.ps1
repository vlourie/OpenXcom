# Сайт поддержки на тестовой станции: Windows 11 + Docker Desktop, где уже крутятся другие сайты.
# Порты 80 и 443 не трогает: сайт открывается по https://<адрес машины>:<HTTPS_PORT>.
#
#   .\station.ps1            первый запуск: .env и portal.env с секретами, сборка, старт, проверка
#   .\station.ps1 up         то же самое (повторно - пересобрать и перезапустить)
#   .\station.ps1 status     контейнеры и ответ /ready
#   .\station.ps1 content    разделы модов и вики из файлов seed\ и wiki\ (up делает это сам)
#   .\station.ps1 logs       журнал сайта (Ctrl+C - выйти)
#   .\station.ps1 admin you@example.com Имя    первый SuperAdmin (пароль спросит)
#   .\station.ps1 reset-2fa you@example.com    сбросить двухфакторную проверку
#   .\station.ps1 mail       письма, которые сайт «отправил» (SMTP не задан)
#   .\station.ps1 root-cert  выгрузить корневой сертификат Caddy (для лаунчера и чтобы браузер не ругался)
#   .\station.ps1 internet [имя]  доступ из интернета: Let's Encrypt через Dynu на том же порту,
#                            ddns держит имя на текущем IP. Нужен DYNU_API_KEY в .env и проброс
#                            HTTPS_PORT на роутере. Имя по умолчанию - x-piratez.mywire.org
#   .\station.ps1 lan        обратно: только локальная сеть, свой сертификат
#   .\station.ps1 releases <архив.zip>   выложить релизы: архив от portal\deploy\pack-releases.ps1
#                            раскладывается в deploy\releases (blobs, потом releases, последними
#                            channels), Caddy раздаёт их по адресу <сайт>/releases/
#   .\station.ps1 down       остановить; данные в томах остаются
#
# Никогда не звать 'docker compose down -v': это удаляет базу, файлы и ключи.
param(
    [Parameter(Position = 0)] [string] $Command = 'up',
    [Parameter(Position = 1)] [string] $Email,
    [Parameter(Position = 2)] [string] $Name
)
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = New-Object Text.UTF8Encoding $false } catch {}
Set-Location -LiteralPath $PSScriptRoot
$utf8 = New-Object Text.UTF8Encoding $false   # .env читает docker compose: без спецификации

function Say([string] $text) { Write-Host "==> $text" -ForegroundColor Cyan }
function Fail([string] $text) { Write-Host "ОШИБКА: $text" -ForegroundColor Red; exit 1 }

# режим из .env: lan (свой сертификат, только локальная сеть) или internet (Let's Encrypt через Dynu,
# доступ снаружи через проброс HTTPS_PORT на роутере, ddns держит имя на текущем IP)
function Get-Compose {
    $files = @('compose', '-f', 'compose.yaml', '-f', 'compose.station.yaml')
    if ((Read-DotEnv '.env')['STATION_MODE'] -eq 'internet') { $files += @('-f', 'compose.internet.yaml', '--profile', 'ddns') }
    $files
}

function Invoke-Compose {
    $compose = Get-Compose
    & docker @compose @args
    if ($LASTEXITCODE -ne 0) { Fail "docker compose $($args -join ' ') завершился с кодом $LASTEXITCODE" }
}

function Assert-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Fail 'docker не найден в PATH. Установлен ли Docker Desktop?' }
    & docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { Fail 'Docker Desktop не запущен (docker info не отвечает).' }
    # !override в compose.station.yaml понимает Compose 2.24.4 и новее
    $v = (& docker compose version --short 2>$null) -replace '^v', ''
    if (-not $v -or [version]($v -replace '[^0-9.].*$', '') -lt [version]'2.24.4') { Fail "нужен Docker Compose 2.24.4 или новее, а тут '$v'. Обновите Docker Desktop." }
}

function Read-DotEnv([string] $path) {
    $map = @{}
    if (Test-Path $path) {
        foreach ($line in Get-Content -LiteralPath $path -Encoding UTF8) {
            if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$') { $map[$Matches[1]] = $Matches[2].Trim() }
        }
    }
    $map
}

function New-Secret([int] $bytes) {
    $b = New-Object byte[] $bytes
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($b)
    $rng.Dispose()
    $b
}

# адрес машины в локальной сети: интерфейс маршрута по умолчанию, а не vEthernet WSL или Docker
function Get-LanAddress {
    $route = Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue | Sort-Object RouteMetric | Select-Object -First 1
    if ($route) {
        $ip = Get-NetIPAddress -InterfaceIndex $route.InterfaceIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($ip) { return $ip.IPAddress }
    }
    'localhost'
}

# первый свободный порт, начиная с 8443: слушающие порты видны и у Docker Desktop (com.docker.backend)
function Get-FreePort([int] $from) {
    for ($p = $from; $p -lt $from + 100; $p++) {
        if (-not (Get-NetTCPConnection -State Listen -LocalPort $p -ErrorAction SilentlyContinue)) { return $p }
    }
    Fail "нет свободного порта в $from..$($from + 99)"
}

function ConvertTo-Range([string] $cidr) {
    $parts = $cidr.Split('/')
    $bytes = ([Net.IPAddress]::Parse($parts[0])).GetAddressBytes()
    [Array]::Reverse($bytes)
    $start = [BitConverter]::ToUInt32($bytes, 0)
    $size = [math]::Pow(2, 32 - [int]$parts[1])
    $first = [math]::Floor($start / $size) * $size
    $last = $first + $size - 1
    @($first, $last)
}

# подсеть между Caddy и сайтом, не пересекающаяся ни с одной сетью Docker на этой машине
function Get-FreeSubnet {
    $taken = @()
    foreach ($id in (& docker network ls -q)) {
        foreach ($s in ((& docker network inspect $id --format '{{range .IPAM.Config}}{{.Subnet}} {{end}}') -split ' ')) {
            if ($s -match '^\d+\.\d+\.\d+\.\d+/\d+$') { $taken += , (ConvertTo-Range $s) }
        }
    }
    # своя сеть прошлого запуска не мешает: она пересоздаётся с тем же адресом
    for ($n = 10; $n -lt 250; $n++) {
        $cand = "172.30.$n.0/24"
        $r = ConvertTo-Range $cand
        $clash = $false
        foreach ($t in $taken) { if ($r[0] -le $t[1] -and $t[0] -le $r[1]) { $clash = $true; break } }
        if (-not $clash) { return $cand }
    }
    Fail 'не нашлось свободной подсети 172.30.N.0/24'
}

function Initialize-Config {
    if (-not (Test-Path '.env')) {
        Say 'создаю .env'
        $host_ = Get-LanAddress
        $port = Get-FreePort 8443
        $existing = & docker network ls --filter 'name=xp-portal_front' -q
        $subnet = if ($existing) { '172.30.10.0/24' } else { Get-FreeSubnet }
        $pg = -join ((New-Secret 24) | ForEach-Object { $_.ToString('x2') })
        $text = @(
            '# made by station.ps1 for a test station; the public server uses .env.example instead'
            "PORTAL_HOST=$host_"
            "HTTPS_PORT=$port"
            "PORTAL_PUBLIC_URL=https://${host_}:$port"
            "POSTGRES_PASSWORD=$pg"
            "FRONT_SUBNET=$subnet"
            'TZ=UTC'
        ) -join "`n"
        [IO.File]::WriteAllText((Join-Path $PSScriptRoot '.env'), $text + "`n", $utf8)
    }
    if (-not (Test-Path 'portal.env')) {
        Say 'создаю portal.env с новым Portal__Secret'
        $secret = [Convert]::ToBase64String((New-Secret 48))
        $lines = Get-Content -LiteralPath 'portal.env.example' -Encoding UTF8 | ForEach-Object {
            if ($_ -match '^Portal__Secret=') { "Portal__Secret=$secret" } else { $_ }
        }
        [IO.File]::WriteAllText((Join-Path $PSScriptRoot 'portal.env'), ($lines -join "`n") + "`n", $utf8)
    }
}

function Get-Url { (Read-DotEnv '.env')['PORTAL_PUBLIC_URL'] }

# меняет или дописывает строку KEY=value в .env, остальное не трогает
function Set-DotEnv([string] $key, [string] $value, [string] $file = '.env') {
    $path = Join-Path $PSScriptRoot $file
    $lines = @(Get-Content -LiteralPath $path -Encoding UTF8)
    $found = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match "^\s*$key\s*=") { $lines[$i] = "$key=$value"; $found = $true }
    }
    if (-not $found) { $lines += "$key=$value" }
    [IO.File]::WriteAllText($path, ($lines -join "`n") + "`n", $utf8)
}

# Каталог сайта и вики: контейнер видит их как /seed и /wiki (монтирует compose.yaml), потому что
# в образе папки deploy нет вовсе. Применять можно сколько угодно раз: разделы сверяются по адресу,
# собранная вики переписывается целиком, написанное человеком не трогается
function Update-Content([switch] $Build) {
    # Отдельной командой - сначала пересборка: скрипты приехали из нового архива, а образ на машине
    # может быть собран из старых исходников, где 'seed' ещё не команда. Тогда контейнер молча
    # поднимет веб-сервер вместо загрузки и будет висеть. С кэшем пересборка - несколько секунд
    if ($Build) {
        Say 'сверяю образ с исходниками'
        Invoke-Compose build migrate
    }
    if (Test-Path 'seed/community.json') {
        Say 'разделы модов и доски форума'
        Invoke-Compose run --rm migrate seed --file /seed/community.json
    }
    foreach ($f in @(Get-ChildItem -Path 'wiki' -Filter '*.json' -ErrorAction SilentlyContinue)) {
        Say "вики из рулсетов: $($f.Name)"
        Invoke-Compose run --rm migrate wiki import --file "/wiki/$($f.Name)"
    }
}

function Test-Ready {
    $env_ = Read-DotEnv '.env'
    $url = $env_['PORTAL_PUBLIC_URL']
    # curl.exe есть в Windows 11. Запрос идёт на 127.0.0.1, но с настоящим именем (--resolve): так
    # проверяется и сертификат на это имя, и не нужен заход снаружи через роутер (NAT loopback умеют
    # не все роутеры). В режиме lan сертификат свой, его не проверяем (-k)
    $check = @('-s', '--max-time', '5', '--resolve', "$($env_['PORTAL_HOST']):$($env_['HTTPS_PORT']):127.0.0.1")
    if ($env_['STATION_MODE'] -ne 'internet') { $check += '-k' }
    $answer = & curl.exe @check "$url/ready" 2>$null
    $answer -eq 'Healthy'
}

switch ($Command) {
    'up' {
        Assert-Docker
        Initialize-Config
        $url = Get-Url
        Say "сборка и запуск (первый раз - несколько минут: образы .NET SDK, PostgreSQL, ClamAV)"
        Invoke-Compose up -d --build
        $internet = (Read-DotEnv '.env')['STATION_MODE'] -eq 'internet'
        Say ($(if ($internet) { 'жду сертификат Let''s Encrypt и ответ сайта (до 5 минут)...' } else { 'жду, пока сайт ответит...' }))
        $ok = $false
        for ($i = 0; $i -lt 100; $i++) {
            if (Test-Ready) { $ok = $true; break }
            Start-Sleep -Seconds 3
        }
        if (-not $ok) {
            Invoke-Compose ps -a
            if ($internet) { Write-Host 'Сертификат: в журнале caddy ищи certificate obtained или ошибку dynu' }
            Fail "сайт не ответил на $url/ready за 5 минут. Журнал: .\station.ps1 logs"
        }
        Update-Content
        Write-Host ''
        Write-Host "Сайт работает: $url" -ForegroundColor Green
        if ($internet) {
            Write-Host "Снаружи он откроется, когда роутер пробрасывает TCP $((Read-DotEnv '.env')['HTTPS_PORT']) на эту машину."
            Write-Host 'Проверять с телефона на мобильном интернете: из своей сети на свой внешний адрес многие роутеры не пускают.'
        } else {
            Write-Host 'Браузер один раз предупредит о сертификате - это нормально для теста.'
        }
        Write-Host 'Первый администратор:  .\station.ps1 admin you@example.com Имя'
        Write-Host 'Антивирусу нужно 2-3 минуты на загрузку баз: до этого вложения висят в статусе «проверяется».'
    }
    'status' {
        Assert-Docker
        Invoke-Compose ps -a
        if (Test-Ready) { Write-Host "ready: Healthy  ($(Get-Url))" -ForegroundColor Green } else { Write-Host "ready: НЕ отвечает ($(Get-Url))" -ForegroundColor Red }
    }
    'content' {
        Assert-Docker
        Update-Content -Build
    }
    'logs' {
        # в режиме internet видно и выдачу сертификата (caddy), и обновление адреса (ddns)
        $services = @('portal', 'migrate')
        if ((Read-DotEnv '.env')['STATION_MODE'] -eq 'internet') { $services += @('caddy', 'ddns') }
        Invoke-Compose logs -f --tail 200 @services
    }
    'admin' {
        if (-not $Email) { Fail 'укажите почту: .\station.ps1 admin you@example.com Имя' }
        $extra = @()
        if ($Name) { $extra = @('--name', $Name) }
        Invoke-Compose run --rm -it migrate admin create --email $Email @extra
    }
    'reset-2fa' {
        if (-not $Email) { Fail 'укажите почту: .\station.ps1 reset-2fa you@example.com' }
        Invoke-Compose run --rm migrate admin reset-2fa --email $Email
    }
    'mail' {
        # без двойных кавычек внутри: PowerShell 5.1 портит их в аргументах внешних программ (R-045)
        Invoke-Compose exec portal sh -c 'd=/data/files/_mail; [ -d $d ] || { echo no mail yet; exit 0; }; for f in $(ls -t $d | head -5); do echo === $f; cat $d/$f; echo; done'
    }
    'root-cert' {
        # корень собственного центра Caddy: добавить в «Доверенные корневые центры» машины, с которой
        # проверяют - тогда браузер не ругается, а лаунчер (ему предупреждение не нажать) может слать отчёты
        Invoke-Compose cp caddy:/data/caddy/pki/authorities/local/root.crt ./caddy-root.crt
        Write-Host "Сохранён $(Join-Path $PSScriptRoot 'caddy-root.crt')"
        Write-Host 'Установить на этой машине (от администратора):  certutil -addstore -f Root caddy-root.crt'
    }
    'internet' {
        Assert-Docker
        Initialize-Config
        $env_ = Read-DotEnv '.env'
        if (-not $env_['DYNU_API_KEY']) {
            Fail 'впишите в .env строку DYNU_API_KEY=<ключ> (dynu.com: Control Panel -> API Credentials -> API Key) и повторите'
        }
        $name = if ($Email) { $Email } elseif ($env_['DYNU_HOSTNAME']) { $env_['DYNU_HOSTNAME'] } else { 'x-piratez.mywire.org' }
        $port = $env_['HTTPS_PORT']
        Say "перевожу сайт на https://${name}:$port (Let's Encrypt через Dynu)"
        # в режиме lan тут записан внутренний адрес; запоминаем его, чтобы lan вернул как было
        if ($env_['STATION_MODE'] -ne 'internet') { Set-DotEnv 'LAN_HOST' $env_['PORTAL_HOST'] }
        Set-DotEnv 'PORTAL_HOST' $name
        Set-DotEnv 'PORTAL_PUBLIC_URL' "https://${name}:$port"
        Set-DotEnv 'DYNU_HOSTNAME' $name
        Set-DotEnv 'STATION_MODE' 'internet'
        & $PSCommandPath up
    }
    'lan' {
        Assert-Docker
        $env_ = Read-DotEnv '.env'
        $lanHost = if ($env_['LAN_HOST']) { $env_['LAN_HOST'] } else { Get-LanAddress }
        Say "возвращаю сайт на https://${lanHost}:$($env_['HTTPS_PORT']) (только локальная сеть)"
        # ddns и собранный Caddy из режима internet гасим тем же набором файлов, что их поднимал
        if ($env_['STATION_MODE'] -eq 'internet') { Invoke-Compose stop ddns }
        Set-DotEnv 'PORTAL_HOST' $lanHost
        Set-DotEnv 'PORTAL_PUBLIC_URL' "https://${lanHost}:$($env_['HTTPS_PORT'])"
        Set-DotEnv 'STATION_MODE' 'lan'
        & $PSCommandPath up
    }
    'releases' {
        Assert-Docker
        if (-not $Email) { Fail 'укажите архив: .\station.ps1 releases C:\путь\xp-releases_....zip' }
        if (-not (Test-Path -LiteralPath $Email -PathType Leaf)) {
            $near = Get-ChildItem -LiteralPath (Split-Path -Parent $Email) -Filter 'xp-releases_*' -ErrorAction SilentlyContinue | ForEach-Object Name
            Fail ("нет файла $Email" + $(if ($near) { "`n  рядом лежит: " + ($near -join ', ') } else { '' }))
        }
        $zip = (Resolve-Path -LiteralPath $Email).Path
        $env_ = Read-DotEnv '.env'
        $dest = if ($env_['RELEASES_DIR']) { $env_['RELEASES_DIR'] } else { Join-Path $PSScriptRoot 'releases' }
        New-Item -ItemType Directory -Force -Path $dest | Out-Null
        $tmp = Join-Path $env:TEMP ('xp-releases-' + [Guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Force -Path $tmp | Out-Null
        try {
            Say "распаковываю $zip"
            # tar из Windows по полному пути: tar из Git в PATH принимает 'C:' за имя сервера
            & (Join-Path $env:WINDIR 'System32\tar.exe') -xf $zip -C $tmp
            if ($LASTEXITCODE -ne 0) { Fail "tar не распаковал архив (код $LASTEXITCODE)" }
            if (-not (Test-Path (Join-Path $tmp 'channels'))) { Fail 'в архиве нет папки channels - это не архив релизов' }
            # порядок важен: указатель канала, пришедший раньше своих файлов, отправит лаунчеры
            # за тем, чего на сервере ещё нет
            foreach ($part in 'blobs', 'releases', '.', 'channels') {
                $from = Join-Path $tmp $part
                if (-not (Test-Path $from)) { continue }
                $to = if ($part -eq '.') { $dest } else { Join-Path $dest $part }
                $rc = if ($part -eq '.') { @($from, $to, 'catalog.json', 'catalog.json.sig') } else { @($from, $to, '/E') }
                Say "releases\$part"
                & robocopy.exe @rc /R:1 /W:1 /NFL /NDL /NP /NJH /NJS | Out-Null
                if ($LASTEXITCODE -ge 8) { Fail "robocopy: ошибка при копировании $part (код $LASTEXITCODE)" }
            }
        } finally {
            Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
        }

        # открытый ключ, которым сайт проверяет релизы: строки prod из keys\release-keys.txt
        $keysFile = Join-Path $PSScriptRoot '..\keys\release-keys.txt'
        $prod = @(Get-Content -LiteralPath $keysFile -Encoding UTF8 | Where-Object { $_ -match '^prod\s+\S+' } | ForEach-Object { ($_ -split '\s+')[1] })
        $penv = Read-DotEnv 'portal.env'
        $changed = $false
        for ($i = 0; $i -lt $prod.Count; $i++) {
            if ($penv["Portal__ReleaseKeys__$i"] -ne $prod[$i]) { Set-DotEnv "Portal__ReleaseKeys__$i" $prod[$i] 'portal.env'; $changed = $true }
        }
        if ($changed) { Say 'ключ релизов записан в portal.env' }
        # новый portal.env и папку releases контейнеры видят только после пересоздания
        Invoke-Compose up -d caddy portal

        $url = Get-Url
        $check = @('-s', '--max-time', '10', '--resolve', "$($env_['PORTAL_HOST']):$($env_['HTTPS_PORT']):127.0.0.1")
        if ($env_['STATION_MODE'] -ne 'internet') { $check += '-k' }
        Start-Sleep -Seconds 3
        foreach ($ch in @(Get-ChildItem -LiteralPath (Join-Path $dest 'channels') -Filter '*.json' | Where-Object { $_.Name -notlike '*.history.json' })) {
            $answer = & curl.exe @check "$url/releases/channels/$($ch.Name)" 2>$null
            $id = if ($answer -match '"releaseId":"([^"]+)"') { $Matches[1] } else { $null }
            if ($id) { Write-Host ("{0,-20} -> {1}" -f $ch.BaseName, $id) -ForegroundColor Green }
            else { Write-Host ("{0,-20} НЕ отвечает: $url/releases/channels/$($ch.Name)" -f $ch.BaseName) -ForegroundColor Red }
        }
        Write-Host "Лаунчеры берут обновления с $url/releases/"
    }
    'down' { Invoke-Compose down }
    default { Fail "неизвестная команда '$Command'. Есть: up, status, content, logs, admin, reset-2fa, mail, root-cert, internet, lan, releases, down" }
}
