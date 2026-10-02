#!/bin/sh
# Боевой голосовой сервер X-Piratez: LiveKit с TURN за Caddy (README.md рядом).
#
#   ./setup.sh voice.example.org turn.example.org https://x-piratez.mywire.org:8443
#       первый раз: имя сервера, имя TURN, адрес сайта (на него LiveKit шлёт события).
#       Ключи LiveKit создаются сами и живут только в .env этой машины
#   ./setup.sh                    повторно: пересобрать livekit.yaml и caddy.yaml из .env, перезапустить
#   ./setup.sh --no-start [...]   только записать файлы, ничего не запускать
#
# Никогда не пересылайте .env в чат и в почту: в нём секрет, которым подписываются пропуска в комнаты.
set -eu
cd "$(dirname "$0")"
umask 077

fail() { echo "ОШИБКА: $*" >&2; exit 1; }
say() { echo "==> $*"; }

start=1
if [ "${1:-}" = "--no-start" ]; then start=0; shift; fi

[ -f .env ] || : > .env
chmod 600 .env
get() { sed -n "s/^$1=//p" .env | tail -n 1; }
put() {
    grep -v "^$1=" .env > .env.new || true
    echo "$1=$2" >> .env.new
    mv .env.new .env
}

if [ $# -gt 0 ]; then
    [ $# -eq 3 ] || fail "нужны три значения: имя сервера, имя TURN, адрес сайта - ./setup.sh voice.example.org turn.example.org https://сайт"
    voice=$(echo "$1" | tr 'A-Z' 'a-z')
    turn=$(echo "$2" | tr 'A-Z' 'a-z')
    portal=${3%/}
else
    voice=$(get VOICE_DOMAIN)
    turn=$(get TURN_DOMAIN)
    portal=$(get PORTAL_URL)
fi

# проверка до записи: неверное значение не попадает в .env
domain_ok() { echo "$1" | grep -Eq '^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$'; }
domain_ok "$voice" || fail "имя сервера '$voice' - не доменное имя. Первый запуск: ./setup.sh voice.example.org turn.example.org https://сайт"
domain_ok "$turn" || fail "имя TURN '$turn' - не доменное имя"
[ "$voice" != "$turn" ] || fail "имя TURN должно отличаться от имени сервера: Caddy делит порт 443 между ними по имени"
echo "$portal" | grep -Eq '^https://[A-Za-z0-9.-]+(:[0-9]+)?$' || fail "адрес сайта '$portal' - нужен https://имя[:порт] без пути"
put VOICE_DOMAIN "$voice"
put TURN_DOMAIN "$turn"
put PORTAL_URL "$portal"

command -v openssl >/dev/null 2>&1 || fail "нет openssl (sudo apt install openssl)"
if [ -z "$(get LIVEKIT_API_KEY)" ] || [ -z "$(get LIVEKIT_API_SECRET)" ]; then
    put LIVEKIT_API_KEY "API$(openssl rand -hex 6)"
    put LIVEKIT_API_SECRET "$(openssl rand -hex 32)"
    say "созданы ключи LiveKit (в .env, читать может только владелец)"
fi
key=$(get LIVEKIT_API_KEY)
secret=$(get LIVEKIT_API_SECRET)
[ ${#secret} -ge 32 ] || fail "LIVEKIT_API_SECRET в .env короче 32 знаков: LiveKit такой не примет"
secret=

umask 022
cat > livekit.yaml <<EOF
# Пишет setup.sh из .env: правка руками пропадёт при следующем запуске.
# Ключи - в LIVEKIT_KEYS (compose.yaml), здесь только имя ключа для подписи событий.
port: 7880
rtc:
  tcp_port: 7881
  # все участники на одном UDP-порту: одно правило брандмауэра вместо диапазона
  udp_port: 7882
  use_external_ip: true
turn:
  enabled: true
  domain: $turn
  # TLS снимает Caddy на 443 по имени $turn и отдаёт сюда простой TCP
  tls_port: 5349
  external_tls: true
  udp_port: 3478
room:
  # комнаты создаёт только сайт, перед каждым пропуском, со своей вместимостью
  auto_create: false
  max_participants: 16
  empty_timeout: 300
webhook:
  api_key: $key
  urls:
    - $portal/api/v1/voice/webhook
logging:
  level: info
EOF

cat > caddy.yaml <<EOF
# Пишет setup.sh из .env: правка руками пропадёт при следующем запуске.
# Шаблон генератора LiveKit (github.com/livekit/deploy, generate/templates/caddy.go).
logging:
  logs:
    default:
      level: INFO
storage:
  "module": "file_system"
  "root": "/data"
apps:
  tls:
    certificates:
      automate:
        - $voice
        - $turn
  layer4:
    servers:
      main:
        listen: [":443"]
        routes:
          - match:
            - tls:
                sni:
                  - "$turn"
            handle:
              - handler: tls
              - handler: proxy
                upstreams:
                  - dial: ["localhost:5349"]
          - match:
              - tls:
                  sni:
                    - "$voice"
            handle:
              - handler: tls
                connection_policies:
                  - alpn: ["http/1.1"]
              - handler: proxy
                upstreams:
                  - dial: ["localhost:7880"]
EOF
say "записаны livekit.yaml и caddy.yaml: сервер $voice, TURN $turn, события на $portal"

if [ "$start" -eq 1 ]; then
    [ "$(uname -s)" = "Linux" ] || fail "нужен Linux: сервер работает в сети хоста, а её Docker на Windows и macOS не даёт"
    command -v docker >/dev/null 2>&1 || fail "нет docker (https://docs.docker.com/engine/install/)"
    command -v curl >/dev/null 2>&1 || fail "нет curl (sudo apt install curl)"
    # пересоздать, а не просто поднять: файлы настроек читаются только при старте
    docker compose up -d --force-recreate
    ok=0
    for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
        if curl -fsS -o /dev/null http://127.0.0.1:7880/; then ok=1; break; fi
        sleep 1
    done
    [ "$ok" -eq 1 ] || fail "LiveKit не ответил на 127.0.0.1:7880 за 20 с: docker compose logs livekit"
    say "LiveKit отвечает. Сертификаты Caddy получает сам за минуту-две; проверка снаружи: curl https://$voice"
fi

cat <<EOF

Брандмауэр этой машины - открыть ровно это (7880 и 5349 НЕ открывать: они за Caddy):
  sudo ufw allow 80/tcp     # выпуск сертификатов
  sudo ufw allow 443/tcp    # сигналинг, API сайта и TURN/TLS
  sudo ufw allow 7881/tcp   # голос, если у игрока закрыт UDP
  sudo ufw allow 7882/udp   # голос, основной путь
  sudo ufw allow 3478/udp   # TURN/UDP

На станции с сайтом (в C:\xp-portal\portal\deploy):
  .\station.ps1 livekit
    адрес:  wss://$voice
    ключ:   $key
    секрет: значение LIVEKIT_API_SECRET из .env этой машины (grep LIVEKIT_API_SECRET .env) -
            вставить в скрытый ввод, в чат не пересылать
EOF
