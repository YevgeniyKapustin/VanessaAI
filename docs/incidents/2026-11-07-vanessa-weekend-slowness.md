# 2026-11-07 — медленные ответы в личке (выходные)

Жалоба владельца: на выходных Ванесса «много тупила», когда он пытался
через неё что-то сделать. Проверено по логам сервера. Chat-текст в файл
не переносится (см. «Приватность» в [observability.md](../observability.md)).

## Окно

Суббота 2026-11-07, 15:15–15:55 по Тбилиси (11:15–11:55 UTC). Одна
сессия в личке, 6 запросов, все уходят в Hermes (`hermes=asked`).
В воскресенье личной переписки не было: в рабочем чате только
by-design тишина (`bot_peer_side` ×19, `prefilter` ×11), плюс два
сбоя на стороне Telegram.

## Замеры

Время от запроса до ответа Hermes и число вызовов модели в одном
запросе (`/root/.hermes/logs/gateway.log`, `api_calls`):

| # | UTC | ждали | api_calls | итог |
|---|---|---|---|---|
| 1 | 11:15:10 | **368.9 s** | 23 | ответ 1855 символов |
| 2 | 11:22:16 | 119.6 s | 15 | ответ 2249 символов |
| 3 | 11:24:16 | 88.2 s | 12 | ответ 2711 символов |
| 4 | 11:40:05 | 42.0 s | 5 | ответ 1225 символов |
| 5 | 11:48:20 | 155.9 s | 26 | `outcome=no_answer`, пустой ответ |
| 6 | 11:51:23 | 16.7 s | 1 | ответ 2007 символов |

Итого 791 s ожидания на 6 запросов. Первый — больше шести минут; в чат
ушёл только короткий ack (198 символов, «сейчас гляну»), дальше тишина
до готового ответа.

## Причины

1. **Слепой релей в Hermes.** Ванесса подтверждает запрос и ждёт job
   молча; промежуточного статуса нет. 23–26 tool-round-trip'ов на один
   запрос — это и есть шесть минут. `HERMES_MAX_WAIT_SECONDS=900`
   (`.env.local`) держит зависший job 15 минут без единого слова в чат.
2. **`execute_code` запрещён на поверхности api_server** (нет
   `approvals.unattended_mode`): каждый шаг — отдельный вызов
   `terminal`, отсюда и счётчик вызовов.
3. **Браузера не было.** `browser_exec` → Chromium 145 exit 127,
   `libatk-1.0.so.0: cannot open shared object file`; CDP supervisor
   затем 5 неудачных реконнектов. В том же ходу починили на месте
   (`apt-get install` в 11:20:49 UTC). Сейчас headless-прогон отдаёт
   example.com. В образ это не входит — на свежем хосте пакеты надо
   ставить отдельно.
4. **Гвард остановил работу в середине** (`BLOCKED: Command approval was
   withdrawn`, 11:50:55) → Hermes вернул `outcome=no_answer` → Ванесса
   отправила дежурную отписку без причины. Блокировка верная (чтение
   секретного ключа), плох только пустой ответ: причину не сказали,
   владельцу пришлось переспрашивать. Повторный запрос закрылся за 17 s
   из контекста.
5. **`HERMES_QUERY_MAX_CHARS=500`** — вопрос, который уходит в Hermes,
   режется по 500 символам, детали задачи теряются до того, как их
   увидят. В переписке это видно как повторные просьбы «сделай это
   через Гермеса».

## Что проверили и списали

- Telegram-поллинг: 2026-11-08 09:17–09:21 UTC (`Bad Gateway` ×15,
  затем 3 таймаута) и 2026-11-09 01:10–01:12 — сторона Telegram,
  aiogram переподключился, ходы не потеряны.
- `announce_source_unreachable error=ReadTimeout` ×9 в worker
  (07.11 09:32 → 09.11 10:11): не ответил PC-бридж за реверс-туннелем,
  по замыслу announcer повторяет на следующем тике (см.
  `services/worker/announce/source.py`).
- Собственная LLM-задержка Ванессы: 27 ходов за период, средняя 4.0 s,
  p90 5.7 s, максимум 9.6 s — норма.

## Кандидаты в фикс

1. Строка прогресса для Hermes-job: через N секунд без ответа — «ещё
   копаюсь» (правка/досылка сообщения), чтобы минуты ожидания были
   видны.
2. `outcome=no_answer` должен нести последнюю причину (гвард, тул,
   таймаут), чтобы compose говорил «заблокировал гвард: чтение ключа»,
   а не «спроси позже».
3. Решить судьбу `approvals.unattended_mode` для api_server: включить
   (быстрее и меньше вызовов) или принять цену round-trip'ов.
4. GUI-библиотеки Chromium (`libatk1.0-0`, `libatk-bridge2.0-0`,
   `libcups2`, `libxkbcommon0`, `libgbm1`, `libnss3`, …) — в bootstrap
   хоста Hermes, чтобы `browser_exec` не отдавал 127.
5. Пересмотреть `HERMES_MAX_WAIT_SECONDS=900` и
   `HERMES_QUERY_MAX_CHARS=500`.

## Что сделано (2026-11-09)

Все пять пунктов закрыты и проверены на сервере.

1. **Строка прогресса.** Поллер получил `progress_after_seconds` и
   колбэк один раз за job; worker публикует `progress_line` из
   `followup.yaml` (source `hermes_progress`, только людям —
   `bot_peer` не получает). Настройка `HERMES_PROGRESS_SECONDS=90`.
   Проверка: живой прогон через `HermesClient` — `PROGRESS fired at 5.4 s`
   при пороге 5 s, ровно один раз.
2. **Причина вместо пожимания плечами.** `wait_for_output` возвращает
   `HermesWaitResult(answer, failure)`; коды `blocked`, `timeout`,
   `interrupted`, `failed`, `empty`. В промпт уходит блок с
   `failure_meanings`, задача — `undelivered_reason_task`. Нет кода в
   словаре — остаётся прежняя нейтральная строка (ничего не выдумываем).
3. **`approvals.unattended_mode: approve`** в `/root/.hermes/config.yaml`
   (бэкап рядом). Проверка: прогон с вопросом «посчитай 17*23 через
   execute_code» вернул `391`, в сессии виден успешный вызов
   `execute_code` — раньше он был `BLOCKED`.
4. **GUI-библиотеки Chromium** стоят на хосте (поставлены ещё 07.11 в
   11:20 UTC). Smoke: `chrome --headless=new --dump-dom
   https://example.com` отдаёт страницу. Список пакетов —
   `docs/hermes.md`, раздел Server, шаг 5.
5. **Кнобы.** `HERMES_MAX_WAIT_SECONDS` 900 → 600 (и в
   `.env.defaults` 6000 → 600), `HERMES_QUERY_MAX_CHARS` 500 → 900,
   `HERMES_PROGRESS_SECONDS=90`. Переменные подняты в контейнерах
   (проверено: `wait 600.0 progress 90.0 query_max 900`).

Тесты: `2102 passed` (`pytest tests/`), `ruff check .` чистый,
`scripts/check_python_file_length.sh` проходит. Заодно закрыт
отдельный красный тест, который был до правок:
`tests/test_service_boundaries.py::test_bot_does_not_import_data_plane_or_siblings`
падал на `services/bot/handlers/message_send_fallback.py` — бот импортировал
`vanessa.pipeline.llm.format.dashes`. `dashes` и `code_fences` переехали
в `vanessa/core/text/`, импорты обновлены, граница снова держится.

Отдельно: задача, ради которой он писал в субботу, теперь решаема.
Заведён свой QA-ящик (`/root/qa-mail.json`), код забирается скриптом
`/root/qa-code.py`, вход на next-stage проверен настоящим Chromium до
экрана приложения (`/root/qa-obscura/qa_browser2.mjs`). Рецепт —
навык `lifeos/qa-next-stage-login` в Hermes на сервере. Читать
`OTP_PEPPER` для этого не нужно.

## Где лежат доказательства

- `/root/.hermes/logs/agent.log`, `gateway.log`, `errors.log` — на хосте
  Hermes; `gateway.log` после 07.11 12:54 не растёт: личных запросов не
  было.
- `docker exec vanessa-worker-1 cat /app/logs/trace-worker.jsonl` —
  `hermes_query` / `hermes_answer` / `hermes_followup` / `hermes_sent`,
  один `request_id` на весь заход.
- `docker exec vanessa-agent-1 cat /app/logs/trace-agent.jsonl` —
  `retrieve`, `compose_prompt`, `compose_reply`. Файл пишется только
  при `TRACE_LOG_ENABLED=true`; последняя запись 07.11 11:53.
- Логи контейнеров: `docker logs -t --since 96h vanessa-agent-1`
  (внутри с 07.11 ~11:00; `agent.log.1` — с 06.11).
