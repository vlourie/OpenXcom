#!/bin/sh
# Keeps a Dynu hostname pointed at this server's public IPv4.
# Protocol: https://www.dynu.com/en-US/DynamicDNS/IP-Update-Protocol
#
# Environment (see .env.example):
#   DYNU_HOSTNAME           x-piratez.mywire.org
#   DYNU_PASSWORD_SHA256    SHA-256 of the IP update password (preferred), or
#   DYNU_PASSWORD           the password itself; hashed here, never sent in clear
#   DYNU_INTERVAL           seconds between IP checks, default 300
#   DYNU_FORCE_DAYS         re-send an unchanged IP this often, default 7
#   DYNU_API, DYNU_CHECKIP  endpoints; overridden only by tests
#   DYNU_ONCE=1             one pass and exit (tests, cron)
#
# Dynu is only called when the IP changed (or once a week): it treats frequent
# identical updates as abuse. Fatal answers (bad password, unknown host, abuse)
# stop the updates instead of hammering the service.

set -u
API=${DYNU_API:-https://api.dynu.com/nic/update}
CHECKIP=${DYNU_CHECKIP:-https://checkip.dynu.com/}
INTERVAL=${DYNU_INTERVAL:-300}
BUSY_WAIT=${DYNU_BUSY_WAIT:-600}
FORCE=$(( ${DYNU_FORCE_DAYS:-7} * 86400 ))
STATE=${DYNU_STATE:-/state/last-ip}

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*"; }

[ -n "${DYNU_HOSTNAME:-}" ] || { log "FATAL DYNU_HOSTNAME is not set"; exit 2; }
if [ -n "${DYNU_PASSWORD_SHA256:-}" ]; then
    HASH=$DYNU_PASSWORD_SHA256
elif [ -n "${DYNU_PASSWORD:-}" ]; then
    HASH=$(printf '%s' "$DYNU_PASSWORD" | sha256sum | cut -d' ' -f1)
else
    log "FATAL set DYNU_PASSWORD_SHA256 or DYNU_PASSWORD"; exit 2
fi

public_ip() {
    curl -fsS -m 20 "$CHECKIP" | grep -oE '([0-9]{1,3}\.){3}[0-9]{1,3}' | head -n1
}

# one update; returns 0 done, 1 retry later, 2 fatal
update() {
    ip=$1
    answer=$(curl -sS -m 30 -G "$API" \
        --data-urlencode "hostname=$DYNU_HOSTNAME" \
        --data-urlencode "myip=$ip" \
        --data-urlencode "myipv6=no" \
        --data-urlencode "password=$HASH" 2>&1) || { log "network error: $answer"; return 1; }
    code=$(echo "$answer" | awk '{print $1; exit}')
    case "$code" in
        good|nochg) log "$code $DYNU_HOSTNAME -> $ip"; return 0 ;;
        911|dnserr|servererror) log "dynu busy ($code), retry in ${BUSY_WAIT}s"; sleep "$BUSY_WAIT"; return 1 ;;
        badauth|nohost|notfqdn|numhost|abuse|'!donator'|unknown)
            log "FATAL dynu answered '$answer' - check DYNU_HOSTNAME and the password"; return 2 ;;
        *) log "unexpected answer '$answer', retry later"; return 1 ;;
    esac
}

mkdir -p "$(dirname "$STATE")" 2>/dev/null
log "watching $DYNU_HOSTNAME every ${INTERVAL}s"
while :; do
    ip=$(public_ip)
    if [ -z "$ip" ]; then
        log "cannot learn the public IP, retry later"
    else
        last=""; age=$FORCE
        if [ -f "$STATE" ]; then
            last=$(cat "$STATE")
            age=$(( $(date +%s) - $(date -r "$STATE" +%s) ))
        fi
        if [ "$ip" != "$last" ] || [ "$age" -ge "$FORCE" ]; then
            [ "$ip" != "$last" ] && [ -n "$last" ] && log "IP changed: $last -> $ip"
            update "$ip"; rc=$?
            [ $rc -eq 0 ] && echo "$ip" > "$STATE"
            [ $rc -eq 2 ] && exit 2
        fi
    fi
    [ "${DYNU_ONCE:-0}" = 1 ] && exit 0
    sleep "$INTERVAL"
done
