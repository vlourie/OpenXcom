# Вики, собранная из рулсетов

Сюда кладутся файлы `<мод>.json`, которые собирает `tools/portal_wiki.py` на машине, где
установлен сам мод. В гит они не идут: у Пираток это 12,7 МБ на 13 563 страницы, и файл
пересобирается при каждом обновлении мода.

Папка монтируется в контейнер `migrate` как `/wiki`, только на чтение:

```sh
docker compose run --rm migrate wiki import --file /wiki/piratez.json
```

Импорт переписывает собранные страницы целиком: те, которых больше нет в рулсетах, удаляются,
а страницы, написанные человеком, не трогаются вовсе.

Собрать файл заново (на машине разработчика, там же где лежит мод):

```powershell
py -3 tools/portal_wiki.py --mod "Пиратки/Dioxine_XPiratez/user/mods/Piratez" `
    --base bin/standard/xcom1 --slug piratez --lang ru --lang en --out dist/wiki/piratez.json
```
