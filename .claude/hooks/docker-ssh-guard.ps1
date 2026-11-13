# PreToolUse guard для команд оболочки: сборка и скачивание образов Docker на станции через ssh (R-510).
#
# Docker Desktop на станциях берёт учётные данные реестра через помощник wincred/desktop, ему нужен
# интерактивный сеанс входа Windows. В сеансе OpenSSH его нет: docker build / pull / compose --build
# падают с «error getting credentials ... A specified logon session does not exist», пустой DOCKER_CONFIG
# не помогает. 27.10 наступили третий раз (station.ps1 up дважды, образ для проверки под Wine).
#
# Останавливается команда, где есть ssh и на удалённой стороне docker build / buildx / pull,
# compose ... --build / pull или station.ps1 up. docker run / exec / ps / rm уже скачанного образа проходят.
# Пропускается: DOCKER_SSH_OK=1 в команде.
#
# stdin: JSON события. Выход 0 = решение в stdout либо пропуск.
# Проверка: python tools/test_docker_ssh_guard.py

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = New-Object Text.UTF8Encoding $false } catch {}

$Ssh = '(?i)(^|[\s;&|("''])ssh(\.exe)?\s'
$Pull = @(
    '(?i)\b(docker(\.exe)?|d\.cmd)\s+(build|buildx|pull|image\s+pull|image\s+build)\b',
    '(?i)\bdocker(\.exe)?\s+compose\b[^;&|]*\s(--build|build|pull)\b',
    '(?i)\bdocker-compose(\.exe)?\b[^;&|]*\s(--build|build|pull)\b',
    '(?i)station\.ps1["'']?\s+up\b'
)

function Test-Command([string]$cmd) {
    if (-not $cmd) { return $null }
    if ($cmd -match 'DOCKER_SSH_OK=1') { return $null }
    if ($cmd -notmatch $Ssh) { return $null }
    foreach ($p in $Pull) {
        $m = [regex]::Match($cmd, $p)
        if ($m.Success) { return $m.Value }
    }
    return $null
}

try {
    $raw = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($raw)) { exit 0 }
    $ev = $raw | ConvertFrom-Json
    $cmd = $null
    if ($ev.tool_input -and ($ev.tool_input.PSObject.Properties.Name -contains 'command')) { $cmd = [string]$ev.tool_input.command }
    $what = Test-Command $cmd
    if (-not $what) { exit 0 }

    @{ hookSpecificOutput = @{
        hookEventName            = 'PreToolUse'
        permissionDecision       = 'deny'
        permissionDecisionReason = "Docker через ssh (R-510): '$what'. На станциях docker build / pull / compose --build / station.ps1 up из сеанса OpenSSH падают на помощнике учётных данных (нужен сеанс входа Windows), пустой DOCKER_CONFIG не помогает. Выкладку сайта делает Vitali в своём сеансе; для проверок брать уже скачанный образ (docker images) через docker run. Если точно понятно, что делаешь, - DOCKER_SSH_OK=1 в начале команды."
    } } | ConvertTo-Json -Depth 5 -Compress
    exit 0
}
catch {
    exit 0
}
