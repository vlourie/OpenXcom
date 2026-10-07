# Проверка почты сайта мимо самого сайта: разговор с SMTP-сервером по шагам, с настоящими ответами.
# Сайт (System.Net.Mail) показывает только общую ошибку - «Authentication Required» или «connection was
# closed», - а сервер в своём ответе называет причину: неверный пароль, нужен пароль приложения, вход
# заблокирован, временный отказ после неудачных попыток. Настройки берутся из portal.env (их пишет
# station.ps1 smtp); пароль и логин в разговоре не печатаются, portal.env не меняется.
#   .\smtp-probe.ps1                       вход с паролем из portal.env
#   .\smtp-probe.ps1 -Ask                  пароль спросить заново (скрытый ввод) - проверить до записи
#   .\smtp-probe.ps1 -To ваш@адрес         после входа отправить пробное письмо
#   .\smtp-probe.ps1 -Ask -Login ящик@gmail.com   другой логин, не трогая portal.env
param([switch] $Ask, [string] $To, [string] $Login)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

function Fail([string] $m) { Write-Host "ОШИБКА: $m" -ForegroundColor Red; exit 1 }

if (-not (Test-Path 'portal.env')) { Fail 'нет portal.env рядом со скриптом: запускайте из папки deploy станции' }
$penv = @{}
foreach ($line in Get-Content -LiteralPath 'portal.env' -Encoding UTF8) {
    if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$') {
        $v = $Matches[2].Trim()
        # compose снимает внешние кавычки: station.ps1 smtp пишет пароль в одинарных
        if ($v.Length -ge 2 -and $v[0] -eq $v[$v.Length - 1] -and ($v[0] -eq "'" -or $v[0] -eq '"')) { $v = $v.Substring(1, $v.Length - 2) }
        $penv[$Matches[1]] = $v
    }
}
$server = $penv['Email__SmtpHost']
$port = if ($penv['Email__SmtpPort']) { [int]$penv['Email__SmtpPort'] } else { 587 }
$user = if ($Login) { $Login } else { [string]$penv['Email__SmtpUser'] }
$from = if ($penv['Email__From']) { $penv['Email__From'] } else { $user }
$password = [string]$penv['Email__SmtpPassword']
if (-not $server) { Fail 'в portal.env нет Email__SmtpHost: сначала .\station.ps1 smtp' }
if ($port -eq 465) { Fail 'порт 465 сайт не умеет, проверка тоже - только 587 (STARTTLS)' }
if ($Ask) {
    $secure = Read-Host 'пароль SMTP (не отображается)' -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
}
$plain = $password -replace '\s', ''
Write-Host "сервер $server`:$port, логин '$user', обратный адрес $from"
Write-Host ("пароль: {0} знаков{1}" -f $password.Length, $(if ($plain.Length -ne $password.Length) { ", из них пробелов $($password.Length - $plain.Length) - у пароля приложения Google их быть не должно" } else { '' }))
# скрытый ввод не показывает раскладку: набранный в русской пароль - те же 16 звёздочек, но кириллицей
$cyr = ([regex]::Matches($password, '[Ѐ-ӿ]')).Count
if ($cyr) { Write-Host "  в пароле $cyr кириллических букв - набран в русской раскладке? Переключите на английскую и введите снова" -ForegroundColor Red }
if ($server -match 'gmail\.com$') {
    if ($plain -cmatch '^[a-z]{16}$') { Write-Host '  по виду это пароль приложения Google: 16 строчных латинских букв' }
    else {
        $why = @()
        if ($plain.Length -ne 16) { $why += "длина $($plain.Length), а не 16" }
        if ($plain -cmatch '[A-Z]') { $why += 'есть заглавные (включён Caps Lock?)' }
        if ($plain -match '[0-9]') { $why += 'есть цифры' }
        if ($cyr) { $why += 'есть кириллица' }
        if ($plain -match '[^A-Za-z0-9Ѐ-ӿ]') { $why += 'есть знаки' }
        Write-Host ("  это НЕ пароль приложения Google (у него 16 строчных латинских букв): " + ($why -join ', ')) -ForegroundColor Red
    }
}

$script:reader = $null
$script:writer = $null
$script:last = ''
function Reply {
    # ответ SMTP бывает многострочным: 250-..., последняя строка 250 ...
    while ($true) {
        $l = $script:reader.ReadLine()
        if ($null -eq $l) { throw 'сервер закрыл соединение, ничего не ответив' }
        Write-Host "  <- $l"
        $script:last = $l
        if ($l.Length -lt 4 -or $l.Substring(3, 1) -ne '-') { return [int]$l.Substring(0, 3) }
    }
}
function Say([string] $line, [string] $shown) {
    Write-Host ('  -> ' + $(if ($shown) { $shown } else { $line }))
    $script:writer.Write($line + "`r`n")
    $script:writer.Flush()
}
function Streams($s) {
    $script:reader = New-Object IO.StreamReader($s, [Text.Encoding]::ASCII)
    $script:writer = New-Object IO.StreamWriter($s, [Text.Encoding]::ASCII)
}
function B64([string] $s) { [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($s)) }

$step = 'адрес сервера'
$code = 0
$tcp = $null
try {
    $ips = [Net.Dns]::GetHostAddresses($server) | ForEach-Object { $_.IPAddressToString }
    Write-Host "адрес: $($ips -join ', ')"
    $step = 'подключение'
    $tcp = New-Object Net.Sockets.TcpClient
    $tcp.ReceiveTimeout = 20000
    $tcp.SendTimeout = 20000
    $tcp.Connect($server, $port)
    $net = $tcp.GetStream()
    Streams $net
    $step = 'приветствие сервера'
    $code = Reply
    if ($code -ne 220) { throw "сервер не готов принимать почту (код $code)" }
    $step = 'EHLO'
    Say 'EHLO xp-portal'
    $code = Reply
    $step = 'STARTTLS'
    Say 'STARTTLS'
    $code = Reply
    if ($code -ne 220) { throw "сервер не включил шифрование (код $code)" }
    $step = 'шифрование TLS'
    $ssl = New-Object Net.Security.SslStream($net, $false)
    $ssl.AuthenticateAsClient($server, $null, [Security.Authentication.SslProtocols]::Tls12, $false)
    Write-Host "  TLS: $($ssl.SslProtocol), сертификат $($ssl.RemoteCertificate.Subject)"
    Streams $ssl
    $step = 'EHLO после TLS'
    Say 'EHLO xp-portal'
    $code = Reply
    if (-not $user) {
        Write-Host 'логина в portal.env нет - вход не проверяю' -ForegroundColor Yellow
    } else {
        # AUTH LOGIN - так входит и сайт
        $step = 'вход: AUTH LOGIN'
        Say 'AUTH LOGIN'
        $code = Reply
        if ($code -ne 334) { throw "сервер не принял AUTH LOGIN (код $code)" }
        $step = 'вход: логин'
        Say (B64 $user) '(логин)'
        $code = Reply
        if ($code -ne 334) { throw "сервер не принял логин (код $code)" }
        $step = 'вход: пароль'
        Say (B64 $password) '(пароль)'
        $code = Reply
        if ($code -eq 235 -and $To) {
            $step = 'письмо: MAIL FROM'
            Say "MAIL FROM:<$from>"
            $code = Reply
            if ($code -ne 250) { throw "сервер не принял обратный адрес (код $code)" }
            $step = 'письмо: RCPT TO'
            Say "RCPT TO:<$To>"
            $code = Reply
            if ($code -ne 250 -and $code -ne 251) { throw "сервер не принял получателя (код $code)" }
            $step = 'письмо: DATA'
            Say 'DATA'
            $code = Reply
            if ($code -ne 354) { throw "сервер не готов принять текст (код $code)" }
            $date = (Get-Date).ToUniversalTime().ToString('ddd, dd MMM yyyy HH:mm:ss +0000', [Globalization.CultureInfo]::InvariantCulture)
            foreach ($l in @("From: <$from>", "To: <$To>", 'Subject: X-Piratez portal: smtp-probe', "Date: $date", '', 'Test letter from smtp-probe.ps1 on the station.', '.')) { Say $l }
            $code = Reply
        }
    }
    $step = 'QUIT'
    $keep = $script:last
    Say 'QUIT'
    try { $null = Reply } catch { }
    $script:last = $keep
} catch {
    Write-Host ("ОБРЫВ на шаге «{0}»: {1}" -f $step, $_.Exception.Message) -ForegroundColor Red
    if ($_.Exception.InnerException) { Write-Host ("  {0}" -f $_.Exception.InnerException.Message) -ForegroundColor Red }
} finally {
    if ($tcp) { $tcp.Close() }
}

# что значит последний ответ сервера
$l = $script:last
Write-Host ''
if ($step -eq 'QUIT' -and $code -eq 235 -and -not $To) { Write-Host 'ВХОД ПРИНЯТ: логин и пароль верные. Если mail-test всё равно падает - пришлите вывод, дело уже в сайте' -ForegroundColor Green }
elseif ($step -eq 'QUIT' -and $To -and $code -eq 250) { Write-Host "ПИСЬМО ПРИНЯТО сервером для $To - проверьте входящие и спам" -ForegroundColor Green }
elseif ($step -eq 'QUIT' -and -not $user) { Write-Host 'соединение и шифрование в порядке; вход не проверен' -ForegroundColor Yellow }
elseif ($l -match '5\.7\.9') { Write-Host 'Gmail требует ПАРОЛЬ ПРИЛОЖЕНИЯ, а не обычный пароль ящика: myaccount.google.com/apppasswords (нужна двухэтапная проверка)' -ForegroundColor Red }
elseif ($l -match '5\.7\.14|534') { Write-Host 'Google ЗАБЛОКИРОВАЛ ВХОД: откройте этот ящик в браузере, найдите письмо или уведомление о входе и подтвердите, что это вы; потом повторите' -ForegroundColor Red }
elseif (($l -match '5\.7\.8|^535') -and $server -match 'gmail\.com$' -and $plain -cmatch '^[a-z]{16}$') {
    # пароль по виду верный - значит он не от этого ящика: Google сам выбирает аккаунт по умолчанию, если вошли в несколько
    Write-Host "НЕВЕРНЫЙ ЛОГИН ИЛИ ПАРОЛЬ, хотя пароль по виду - пароль приложения: он создан в ДРУГОМ аккаунте Google, чем '$user', или в логине опечатка, или пароль уже отозван" -ForegroundColor Red
    Write-Host '  создайте пароль приложения в окне инкогнито, войдя только в этот ящик, и сверьте логин с адресом ящика по буквам' -ForegroundColor Red
}
elseif ($l -match '5\.7\.8|^535') { Write-Host 'НЕВЕРНЫЙ ЛОГИН ИЛИ ПАРОЛЬ: пароль приложения не тот, отозван или введён с пробелами - создайте новый и задайте его .\station.ps1 smtp' -ForegroundColor Red }
elseif ($l -match '^4\d\d|4\.7\.') { Write-Host 'сервер ВРЕМЕННО ОТКАЗЫВАЕТ (часто после серии неудачных входов): подождите час и повторите, ничего не меняя' -ForegroundColor Red }
else { Write-Host 'пришлите весь вывод: по нему видно, на каком шаге и что ответил сервер' -ForegroundColor Yellow }
