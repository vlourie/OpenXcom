# Сайт поддержки на тестовой станции: Windows 11 + Docker Desktop, где уже крутятся другие сайты.
# Порты 80 и 443 не трогает: сайт открывается по https://<адрес машины>:<HTTPS_PORT>.
#
#   .\station.ps1            первый запуск: .env и portal.env с секретами, сборка, старт, проверка
#   .\station.ps1 up         то же самое (повторно - пересобрать и перезапустить)
#   .\station.ps1 status     контейнеры и ответ /ready
#   .\station.ps1 logs       журнал сайта (Ctrl+C - выйти)
#   .\station.ps1 admin you@example.com Имя    первый SuperAdmin (пароль спросит)
#   .\station.ps1 reset-2fa you@example.com    сбросить двухфакторную проверку
#   .\station.ps1 mail       письма, которые сайт «отправил» (SMTP не задан)
#   .\station.ps1 root-cert  выгрузить корневой сертификат Caddy (для лаунчера и чтобы браузер не ругался)
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
$compose = @('compose', '-f', 'compose.yaml', '-f', 'compose.station.yaml')
$utf8 = New-Object Text.UTF8Encoding $false   # .env читает docker compose: без спецификации

function Say([string] $text) { Write-Host "==> $text" -ForegroundColor Cyan }
function Fail([string] $text) { Write-Host "ОШИБКА: $text" -ForegroundColor Red; exit 1 }

function Invoke-Compose {
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

function Test-Ready {
    $url = Get-Url
    # curl.exe есть в Windows 11; -k - сертификат выдан собственным центром Caddy
    $answer = & curl.exe -k -s --max-time 5 "$url/ready" 2>$null
    $answer -eq 'Healthy'
}

switch ($Command) {
    'up' {
        Assert-Docker
        Initialize-Config
        $url = Get-Url
        Say "сборка и запуск (первый раз - несколько минут: образы .NET SDK, PostgreSQL, ClamAV)"
        Invoke-Compose up -d --build
        Say 'жду, пока сайт ответит...'
        $ok = $false
        for ($i = 0; $i -lt 60; $i++) {
            if (Test-Ready) { $ok = $true; break }
            Start-Sleep -Seconds 3
        }
        if (-not $ok) {
            Invoke-Compose ps -a
            Fail "сайт не ответил на $url/ready за 3 минуты. Журнал: .\station.ps1 logs"
        }
        Write-Host ''
        Write-Host "Сайт работает: $url" -ForegroundColor Green
        Write-Host 'Браузер один раз предупредит о сертификате - это нормально для теста.'
        Write-Host 'Первый администратор:  .\station.ps1 admin you@example.com Имя'
        Write-Host 'Антивирусу нужно 2-3 минуты на загрузку баз: до этого вложения висят в статусе «проверяется».'
    }
    'status' {
        Assert-Docker
        Invoke-Compose ps -a
        if (Test-Ready) { Write-Host "ready: Healthy  ($(Get-Url))" -ForegroundColor Green } else { Write-Host "ready: НЕ отвечает ($(Get-Url))" -ForegroundColor Red }
    }
    'logs' { Invoke-Compose logs -f --tail 200 portal migrate }
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
    'down' { Invoke-Compose down }
    default { Fail "неизвестная команда '$Command'. Есть: up, status, logs, admin, reset-2fa, mail, root-cert, down" }
}
