# Голос у Stoat (бывший Revolt): что можно взять

2026-10-02. Вопрос Vitali: «https://github.com/stoatchat — может нам воспользоваться частью их наработок?»

## Что это

Stoat — открытый аналог Discord, до октября 2025 назывался Revolt. Голос у них, как и у нас, на
LiveKit: свой сервер Vortex выбросили, LiveKit в боевой выкладке с февраля 2026
([история](https://vale.rocks/posts/stoat-history)). Из их же слов: сам клиент был готов раньше, а
в бой не выходил из-за проблем с развёртыванием сервера.

| Репозиторий | Что | Язык | Лицензия |
|---|---|---|---|
| [stoatchat](https://github.com/stoatchat/stoatchat) | бэкенд: выдача пропусков, присутствие, вебхуки LiveKit | Rust | AGPL-3.0 |
| [for-web](https://github.com/stoatchat/for-web) | клиент (браузер и Electron) | TypeScript, Solid.js, `livekit-client` 2.22 | AGPL-3.0 |
| [for-android](https://github.com/stoatchat/for-android), [for-ios](https://github.com/stoatchat/for-ios) | мобильные клиенты | Kotlin, Swift | — |
| [livekit-server](https://github.com/stoatchat/livekit-server) | копия сервера LiveKit v1.13.4 плюс три своих правки | Go | Apache-2.0 |
| [livekit-protocol](https://github.com/stoatchat/livekit-protocol) | копия протокола под эти правки | Go | Apache-2.0 |
| [javascript-solid-livekit-components](https://github.com/stoatchat/javascript-solid-livekit-components) | виджеты LiveKit для Solid | TypeScript | Apache-2.0 |

## Звуковой тракт — взять нечего

Их клиент живёт в браузере. Микрофон, колонки, эхоподавление, усиление и шумодав делает Chrome
или Electron через `getUserMedia` (`echoCancellation`, `noiseSuppression`, `autoGainControl`,
`voiceIsolation` — `for-web/packages/client/components/rtc/state.tsx`). Всего, с чем мы возимся в
лаунчере — открытие устройств, дуплекс на одной карте, часы микрофона против часов колонок,
троттлинг свёрнутого окна, — у них просто нет: это решает браузер. Для нашего нативного пути
(`Xp.Voice`, `livekit_ffi.dll`) их код не применим.

Одна идея на потом: у них три ступени шумодава — выключен, браузерный, «усиленный» на RNNoise
(`livekit-rnnoise-processor`: ФВЧ 50 Гц → RNNoise → компрессор, `rtc/VoiceProcessor.ts`), и по
умолчанию стоит именно RNNoise — браузерного им не хватило. У нас шумодав — из WebRTC APM
(умеренный). Если шум микрофонов станет жалобой, RNNoise есть как C-библиотека (BSD), встаёт в
насос перед APM. Не для текущей проблемы.

## Серверная часть — хорошая шпаргалка к этапам 2–4 VOICE_CHAT.md

Их бэкенд делает ровно то, что у нас в плане, и уже год в бою. Код брать нельзя (Rust и AGPL против
нашего C# `Xp.Portal`), решения — можно:

- **Вход** (`crates/delta/src/routes/channels/voice_join.rs`): проверка прав → пропуск JWT с
  **TTL 10 секунд** (у нас в плане минута), в грантах `room_join`, `can_publish_sources` только
  `microphone` и только при праве говорить, `can_subscribe` по праву слушать; комната создаётся с
  `empty_timeout` 5 минут и метаданными. Один человек — одна комната: прежнее подключение
  снимается через `RemoveParticipant` (`force_disconnect`).
- **Присутствие** (`crates/daemons/voice-ingress`): отдельный демон принимает вебхуки LiveKit
  (`participant_joined/left`, `track_published/unpublished/muted/unmuted`, `room_finished`),
  проверяет подпись `TokenVerifier`, держит «кто где» в Redis. На `track_published` с
  недопустимым треком (данные, видео сверх лимита) — сразу `RemoveParticipant`. Это наша сверка на
  `participant_joined` из §7 плана, только шире.
- **Смена прав на лету** (`crates/core/database/src/voice/mod.rs`, `sync_user_voice_permissions`):
  изменилась роль — `UpdateParticipant {can_subscribe, can_publish}` каждому, кто сидит в комнате.
  Это наше «запретить говорить».
- **Клиент**: `autoSubscribe: false`, подписка руками только на звуковые треки
  (`RoomAudioManager.tsx`); у каждого собеседника своя громкость и свой mute, общий «оглохнуть»,
  усиление входа и выхода 0–300 %, звуки входа и выхода (`stores/Voice.ts`). Для окна лаунчера —
  список того, что ждут игроки от голосового чата.

## Их правки сервера нам не нужны

Три коммита поверх upstream (июль 2026): вебхуки `track_muted`/`track_unmuted` (в upstream имена
событий есть, но сервер их не шлёт), число участников в телеметрии, метаданные комнаты в
событиях. Нужны им, потому что mute у них клиентский и бэкенд узнаёт о нём по вебхуку. У нас
запрет речи серверный (`UpdateParticipant`), вебхук не нужен. Их копия — v1.13.4, мы уже на
v1.13.7 (`portal/deploy/compose.voice.yaml`); садиться на чужую ветку с тремя правками и
собственной сборкой ради этого не стоит.

Развёртывание у них минимальное (`livekit.example.yml`: порт 7880, Redis, вебхук с ключом узла).
Из опыта их самохостеров ([javif89/stoat-selfhost](https://github.com/javif89/stoat-selfhost),
[обсуждение 593](https://github.com/orgs/stoatchat/discussions/593)): беды только сетевые —
UDP-диапазон и TURN, то же, что у нас в VOICE_PROBE.md.

## Вывод

К сегодняшней проблеме лаунчера (звуковые устройства, см. аудит 30.09) Stoat отношения не имеет.
Для серверной части — сверить наш план с их `voice_join.rs`, `voice-ingress` и
`sync_user_voice_permissions`, перенять TTL пропуска 10 с и снятие по запрещённому треку.
Зависимостей и форков не добавлять.
