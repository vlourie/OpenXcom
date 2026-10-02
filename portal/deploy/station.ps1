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
#   .\station.ps1 smtp       настроить отправку писем: сервер, порт 587, логин, обратный адрес;
#                            пароль спрашивает скрыто и пишет только в portal.env этой машины
#   .\station.ps1 mail-test you@example.com    одно пробное письмо через SMTP; сбой - с причиной
#   .\station.ps1 root-cert  выгрузить корневой сертификат Caddy (для лаунчера и чтобы браузер не ругался)
#   .\station.ps1 internet [имя]  доступ из интернета: Let's Encrypt через Dynu на том же порту,
#                            ddns держит имя на текущем IP. Нужен DYNU_API_KEY в .env и проброс
#                            HTTPS_PORT на роутере. Имя по умолчанию - x-piratez.mywire.org
#   .\station.ps1 lan        обратно: только локальная сеть, свой сертификат
#   .\station.ps1 releases <архив.zip>   выложить релизы: архив от portal\deploy\pack-releases.ps1
#                            раскладывается в deploy\releases (blobs, потом releases, последними
#                            channels), Caddy раздаёт их по адресу <сайт>/releases/
#   .\station.ps1 voice      проба голоса (docs/portal/VOICE_PROBE.md): LiveKit и эхо-бот поверх сайта,
#                            ключи LiveKit в .env. Нужен режим internet и проброс 7882/UDP и 7881/TCP
#   .\station.ps1 voice-check    что видно изнутри: контейнеры, /rtc через Caddy, порты, брандмауэр
#   .\station.ps1 voice-token <имя> [часы]   ссылка на страницу пробы с пропуском (по умолчанию 24 ч)
#   .\station.ps1 voice-off  убрать пробу голоса; сайт остаётся
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
    $env_ = Read-DotEnv '.env'
    $files = @('compose', '-f', 'compose.yaml', '-f', 'compose.station.yaml')
    if ($env_['STATION_MODE'] -eq 'internet') { $files += @('-f', 'compose.internet.yaml') }
    # проба голоса (docs/portal/VOICE_PROBE.md): последним, чтобы её том Caddy лёг поверх !override
    if ($env_['VOICE_PROBE'] -eq '1') { $files += @('-f', 'compose.voice.yaml') }
    if ($env_['STATION_MODE'] -eq 'internet') { $files += @('--profile', 'ddns') }
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

# FRONT_SUBNET для нового .env: задана в окружении - она; сеть прошлого запуска уже есть - её настоящий
# адрес (раньше здесь стояло 172.30.10.0/24 наугад, а сеть могла быть создана с другим); иначе свободная
function Get-FrontSubnet {
    if ($env:FRONT_SUBNET) {
        if ($env:FRONT_SUBNET -notmatch '^\d+\.\d+\.\d+\.\d+/\d+$') { Fail "FRONT_SUBNET='$env:FRONT_SUBNET' - не подсеть вида 172.30.10.0/24" }
        return $env:FRONT_SUBNET
    }
    $existing = @(& docker network ls --filter 'name=xp-portal_front' -q)
    if ($existing) {
        $s = ((& docker network inspect $existing[0] --format '{{range .IPAM.Config}}{{.Subnet}} {{end}}') -split ' ') |
            Where-Object { $_ -match '^\d+\.\d+\.\d+\.\d+/\d+$' } | Select-Object -First 1
        if ($s) { return $s }
        return '172.30.10.0/24'   # подсеть не прочиталась: прежнее значение, как в compose.yaml
    }
    Get-FreeSubnet
}

function Initialize-Config {
    if (-not (Test-Path '.env')) {
        Say 'создаю .env'
        $host_ = Get-LanAddress
        $port = Get-FreePort 8443
        $subnet = Get-FrontSubnet
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
    # перепись наборов арта: без неё дорожная карта открывается пустой, потому что знаменатель
    # («сколько всего картинок») берётся отсюда, а не из присланных отметок
    if (Test-Path 'seed/packs.json') {
        Say 'перепись наборов графики'
        Invoke-Compose run --rm migrate packs --file /seed/packs.json
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

# ---- проба голоса ----

function ConvertTo-B64Url([byte[]] $b) { [Convert]::ToBase64String($b).TrimEnd('=').Replace('+', '-').Replace('/', '_') }

# пропуск LiveKit (JWT HS256) в комнату probe: только для пробы, в боевой схеме его выдаёт портал
function New-VoiceToken([string] $identity, [int] $hours) {
    $env_ = Read-DotEnv '.env'
    $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $header = '{"alg":"HS256","typ":"JWT"}'
    $payload = '{"iss":"' + $env_['LIVEKIT_API_KEY'] + '","sub":"' + $identity + '","name":"' + $identity +
        '","nbf":' + ($now - 30) + ',"exp":' + ($now + $hours * 3600) +
        ',"video":{"room":"probe","roomJoin":true,"canPublish":true,"canSubscribe":true}}'
    $data = (ConvertTo-B64Url $utf8.GetBytes($header)) + '.' + (ConvertTo-B64Url $utf8.GetBytes($payload))
    $hmac = New-Object Security.Cryptography.HMACSHA256 (, $utf8.GetBytes($env_['LIVEKIT_API_SECRET']))
    $sig = ConvertTo-B64Url $hmac.ComputeHash($utf8.GetBytes($data))
    $hmac.Dispose()
    "$data.$sig"
}

# ответ LiveKit через Caddy: /rtc/validate без пропуска - 401 от LiveKit. 404 - старый Caddyfile,
# 502 - Caddy не достучался до контейнера livekit
function Test-Rtc {
    $env_ = Read-DotEnv '.env'
    $check = @('-s', '-o', 'NUL', '-w', '%{http_code}', '--max-time', '5', '--resolve', "$($env_['PORTAL_HOST']):$($env_['HTTPS_PORT']):127.0.0.1")
    if ($env_['STATION_MODE'] -ne 'internet') { $check += '-k' }
    [string](& curl.exe @check "$($env_['PORTAL_PUBLIC_URL'])/rtc/validate" 2>$null)
}

function Show-VoiceCheck {
    $env_ = Read-DotEnv '.env'
    Invoke-Compose ps -a livekit voice-echo caddy
    $code = Test-Rtc
    if ($code -match '^4\d\d$' -and $code -ne '404') { Write-Host "сигналинг /rtc через Caddy: отвечает LiveKit (HTTP $code)" -ForegroundColor Green }
    else { Write-Host "сигналинг /rtc через Caddy: HTTP '$code' - 404 значит старый Caddyfile, 502 - livekit не запущен" -ForegroundColor Red }

    $tcp = Get-NetTCPConnection -State Listen -LocalPort 7881 -ErrorAction SilentlyContinue
    $udp = Get-NetUDPEndpoint -LocalPort 7882 -ErrorAction SilentlyContinue
    Write-Host ('7881/TCP на машине: ' + $(if ($tcp) { 'слушает (' + (($tcp | ForEach-Object { (Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue).Name } | Sort-Object -Unique) -join ', ') + ')' } else { 'НЕ слушает' })) -ForegroundColor $(if ($tcp) { 'Green' } else { 'Red' })
    Write-Host ('7882/UDP на машине: ' + $(if ($udp) { 'открыт (' + (($udp | ForEach-Object { (Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue).Name } | Sort-Object -Unique) -join ', ') + ')' } else { 'НЕ открыт' })) -ForegroundColor $(if ($udp) { 'Green' } else { 'Red' })

    # входящие правила брандмауэра Windows для Docker и профиль сети: без правила на профиль текущей
    # сети пакеты снаружи до Docker Desktop не дойдут, даже если роутер их пробросил
    $profiles = @(Get-NetConnectionProfile -ErrorAction SilentlyContinue | ForEach-Object { "$($_.InterfaceAlias): $($_.NetworkCategory)" })
    Write-Host ('профиль сети: ' + ($profiles -join '; '))
    $rules = @(Get-NetFirewallRule -Direction Inbound -Enabled True -Action Allow -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -match 'Docker|com\.docker' })
    if ($rules) { $rules | ForEach-Object { Write-Host ("брандмауэр: {0} [{1}]" -f $_.DisplayName, $_.Profile) } }
    else { Write-Host 'брандмауэр: входящих разрешающих правил Docker не нашлось' -ForegroundColor Yellow }

    # внешний адрес: по имени сайта (его держит ddns) и тот, что LiveKit узнал через STUN при старте
    if ($env_['STATION_MODE'] -eq 'internet') {
        $dns = @(Resolve-DnsName $env_['PORTAL_HOST'] -Type A -Server 1.1.1.1 -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress } | ForEach-Object IPAddress)
        Write-Host "внешний IP по DNS ($($env_['PORTAL_HOST'])): $($dns -join ', ')"
    }
    $compose = Get-Compose
    $lines = @(& docker @compose logs livekit 2>&1 | Select-String -Pattern 'nodeIP|external|STUN' | Select-Object -Last 3)
    if ($lines) { $lines | ForEach-Object { Write-Host "livekit: $($_.Line.Trim())" } }
    else { Write-Host 'livekit: строки с внешним IP в журнале не нашлось - смотреть docker compose logs livekit' -ForegroundColor Yellow }
    $echo = @(& docker @compose logs --tail 5 voice-echo 2>&1)
    Write-Host 'эхо-бот, последние строки:'
    $echo | ForEach-Object { Write-Host "  $_" }
}

switch ($Command) {
    'voice' {
        Assert-Docker
        Initialize-Config
        $env_ = Read-DotEnv '.env'
        if ($env_['STATION_MODE'] -ne 'internet') {
            Write-Host 'Сайт в режиме lan: снаружи проба не пройдёт (свой сертификат, локальный адрес). Сначала .\station.ps1 internet' -ForegroundColor Yellow
        }
        if (-not $env_['LIVEKIT_API_KEY'] -or -not $env_['LIVEKIT_API_SECRET']) {
            Say 'создаю ключи LiveKit в .env'
            Set-DotEnv 'LIVEKIT_API_KEY' ('API' + (-join ((New-Secret 6) | ForEach-Object { $_.ToString('x2') })))
            Set-DotEnv 'LIVEKIT_API_SECRET' (-join ((New-Secret 32) | ForEach-Object { $_.ToString('x2') }))
        }
        Set-DotEnv 'VOICE_PROBE' '1'
        Say 'запускаю LiveKit, эхо-бот и Caddy с маршрутом /rtc'
        Invoke-Compose up -d --build livekit voice-echo caddy
        Start-Sleep -Seconds 5
        Show-VoiceCheck
        Write-Host ''
        Write-Host 'Дальше: на роутере пробросить на эту машину 7882/UDP и 7881/TCP (если ещё нет).' -ForegroundColor Green
        Write-Host 'Ссылка для участника:  .\station.ps1 voice-token vitali'
    }
    'voice-check' {
        Assert-Docker
        Show-VoiceCheck
    }
    'voice-token' {
        $env_ = Read-DotEnv '.env'
        if (-not $env_['LIVEKIT_API_SECRET']) { Fail 'ключей LiveKit нет - сначала .\station.ps1 voice' }
        if ($Email -notmatch '^[A-Za-z0-9_-]{1,32}$') { Fail 'имя участника - латиница, цифры, _ и -, до 32 знаков: .\station.ps1 voice-token vitali' }
        $hours = if ($Name) { [int]$Name } else { 24 }
        $jwt = New-VoiceToken $Email $hours
        Write-Host "$(Get-Url)/voice-probe/#t=$jwt"
        Write-Host "Пропуск на $hours ч для '$Email'. Одно имя - одно подключение: второй вход с той же ссылкой выбьет первый." -ForegroundColor DarkGray
    }
    'voice-off' {
        Assert-Docker
        if ((Read-DotEnv '.env')['VOICE_PROBE'] -eq '1') { Invoke-Compose rm -s -f livekit voice-echo }
        Set-DotEnv 'VOICE_PROBE' '0'
        # Caddy без тома страницы пробы
        Invoke-Compose up -d caddy
        Write-Host 'Проба голоса убрана; ключи LiveKit остались в .env. Проброс 7881/7882 на роутере можно снять.'
    }
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
    'smtp' {
        # Секреты почты живут только в portal.env этой машины: в чат, в гит и в архивы они не попадают.
        # Пустой ответ оставляет прежнее значение. Пароль - в одинарных кавычках: так compose не
        # разбирает в нём $ и #. Порт 465 (TLS сразу при подключении) сайт не умеет, только 587 (STARTTLS)
        if (-not (Test-Path 'portal.env')) { Fail 'нет portal.env: сначала .\station.ps1 up' }
        $penv = Read-DotEnv 'portal.env'
        function Ask([string] $what, [string] $key, [string] $default) {
            $now = if ($penv[$key]) { $penv[$key] } else { $default }
            $a = Read-Host "$what [$now]"
            if ($a.Trim()) { $a.Trim() } else { $now }
        }
        $smtpHost = Ask 'SMTP-сервер (например smtp.yandex.ru)' 'Email__SmtpHost' ''
        if (-not $smtpHost) { Fail 'сервер не задан: без него письма только складываются в папку (.\station.ps1 mail)' }
        $port = Ask 'порт' 'Email__SmtpPort' '587'
        if ($port -eq '465') { Fail 'порт 465 сайт не умеет (TLS сразу при подключении). Почти все почтовые службы принимают и 587 - укажите его' }
        if ($port -notmatch '^\d+$') { Fail "порт - число, а не '$port'" }
        $user = Ask 'логин SMTP (обычно полный адрес ящика)' 'Email__SmtpUser' ''
        $from = Ask 'обратный адрес писем (у большинства служб обязан совпадать с ящиком или его доменом)' 'Email__From' $user
        $secure = Read-Host 'пароль SMTP (не отображается; пусто - оставить прежний)' -AsSecureString
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        try { $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
        if ($password.Contains("'")) { Fail 'в пароле одинарная кавычка: её нельзя записать в portal.env. Задайте пароль приложения без неё' }
        Set-DotEnv 'Email__SmtpHost' $smtpHost 'portal.env'
        Set-DotEnv 'Email__SmtpPort' $port 'portal.env'
        Set-DotEnv 'Email__SmtpUser' $user 'portal.env'
        Set-DotEnv 'Email__From' $from 'portal.env'
        if ($password) { Set-DotEnv 'Email__SmtpPassword' "'$password'" 'portal.env' }
        $password = $null
        if (-not (Read-DotEnv 'portal.env')['Email__SmtpPassword']) { Write-Host 'Пароль не задан: большинство служб без него письмо не примут.' -ForegroundColor Yellow }
        Say 'перезапускаю сайт с новыми настройками почты'
        Invoke-Compose up -d --no-deps --force-recreate portal
        Say 'готово. Проверка: .\station.ps1 mail-test <ваш адрес>'
    }
    'mail-test' {
        if (-not $Email) { Fail 'укажите адрес: .\station.ps1 mail-test you@example.com' }
        # отдельным контейнером с тем же portal.env: сайт сбои почты глотает, а здесь видна причина
        Invoke-Compose run --rm migrate mail test --to $Email
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
        if (-not (Test-Path -LiteralPath $keysFile)) { Fail "нет $keysFile - файлы релизов разложены, но ключа нет: распакуйте свежий архив сайта (pack.ps1) и повторите" }
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
            # указатель канала едет в КАЖДОМ архиве, а файлы выпуска - только в том, где они новые.
            # Если архив с ними не доехал, канал зовёт лаунчеры за тем, чего здесь нет (грабли R-065)
            if ($id) {
                $mf = Join-Path $dest "releases\$id\manifest.json"
                if (-not (Test-Path -LiteralPath $mf)) {
                    Write-Host ("  НЕТ выпуска {0}: канал на него указывает, а файлов нет. Разложите архив, в котором он собран." -f $id) -ForegroundColor Red
                } else {
                    $all = (Get-Content -LiteralPath $mf -Raw | ConvertFrom-Json).files
                    $gone = 0
                    foreach ($f in $all) {
                        $h = $f.sha256
                        if (-not (Test-Path -LiteralPath (Join-Path $dest ("blobs\sha256\{0}\{1}" -f $h.Substring(0, 2), $h)))) { $gone++ }
                    }
                    if ($gone) { Write-Host ("  У выпуска {0} нет {1} файлов из {2} - обновление не пройдёт" -f $id, $gone, $all.Count) -ForegroundColor Red }
                }
            }
        }
        Write-Host "Лаунчеры берут обновления с $url/releases/"
    }
    'down' { Invoke-Compose down }
    default { Fail "неизвестная команда '$Command'. Есть: up, status, content, logs, admin, reset-2fa, mail, root-cert, internet, lan, releases, voice, voice-check, voice-token, voice-off, down" }
}
