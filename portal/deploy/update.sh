#!/bin/sh
# Обновление сайта на сервере: пересборка образа, схема базы, каталог разделов и вики.
#
#   cd portal/deploy && ./update.sh
#   ./update.sh --no-wiki     только код и каталог, вики не трогать
#
# Данные не трогаются вовсе: база, вложения, ключи и сертификаты лежат в томах Docker и
# переживают пересборку. Ни одна команда здесь не удаляет том.
set -eu
cd "$(dirname "$0")"

wiki=yes
for a in "$@"; do
    case "$a" in
        --no-wiki) wiki=no ;;
        *) echo "неизвестный ключ: $a (есть --no-wiki)" >&2; exit 2 ;;
    esac
done

command -v docker >/dev/null 2>&1 || { echo 'docker не найден' >&2; exit 1; }
[ -f .env ] || { echo 'нет .env: скопируйте .env.example в .env и заполните' >&2; exit 1; }
[ -f portal.env ] || { echo 'нет portal.env: скопируйте portal.env.example в portal.env и заполните' >&2; exit 1; }

echo '==> сборка образа и запуск (схему базы приводит в порядок контейнер migrate)'
docker compose up -d --build

# каталог сайта: моды и доски форума. Повторное применение безопасно - записи сверяются
# по адресу и переписываются, ничего не удаляется
if [ -f seed/community.json ]; then
    echo '==> разделы модов и доски форума'
    docker compose run --rm migrate seed --file /seed/community.json
fi

# вики, собранная из рулсетов (tools/portal_wiki.py на машине, где установлен мод).
# Импорт переписывает собранные страницы целиком; написанные человеком не трогает
if [ "$wiki" = yes ]; then
    for f in wiki/*.json; do
        [ -e "$f" ] || { echo '==> вики: в папке wiki нет файлов, пропускаю'; break; }
        echo "==> вики из рулсетов: $f"
        docker compose run --rm migrate wiki import --file "/wiki/$(basename "$f")"
    done
fi

host=$(grep -E '^PORTAL_HOST=' .env | cut -d= -f2-)
echo '==> проверка'
docker compose ps
curl -sS --max-time 10 "https://$host/ready" && echo " <- /ready" || echo 'сайт не ответил; журнал: docker compose logs -f portal'
