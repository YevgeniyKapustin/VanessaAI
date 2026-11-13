# 2026-11-10 — десятиминутные зависания релея и OOM на хосте

Жалоба владельца: Ванесса «тупила» — подтверждала запрос, потом молчала
минутами и в конце отвечала, что не смогла. Проверено по логам сервера.
Текст переписки в файл не переносится (см. «Приватность» в
[observability.md](../observability.md)).

## Окно

Два вечера подряд по тиблисскому времени: 2026-11-09 19:36–21:30 и
2026-11-10 11:22–11:53 (15:36–17:30 и 07:22–07:53 UTC). Личка владельца,
11 запросов в Hermes. Первый вечер — тяжёлые задачи (деплой рантаймов на
препрод, прогон тестов по MR), второй — открытие MR в QA и починка
main-MR.

## Замеры

Время от запроса в Hermes до ответа и число вызовов модели в одном
прогоне (`/root/.hermes/logs/gateway.log`, `time=`, `api_calls`):

| # | UTC | ждали | api_calls | итог |
|---|---|---|---|---|
| 1 | 09.11 15:36:47 | 208.1 s | 43 | ответ 1759 симв. |
| 2 | 09.11 15:40:15 | 44.2 s | 13 | ответ 2380 симв. |
| 3 | 09.11 15:41:43 | 66.2 s | 7 | ответ 3393 симв. |
| 4 | 09.11 15:42:50 | 562.5 s | 51 | пустой ответ → `no_answer` |
| 5 | 09.11 15:55:17 | 192.6 s | 7 | ответ 1580 симв. |
| 6 | 09.11 16:00:31 | **601.4 s** | 39 | ответ 65 симв. пришёл, но выброшен |
| 7 | 09.11 16:12:18 | **601.9 s** | 23 | пусто → `failure=timeout` |
| 8 | 09.11 17:19:41 | **601.0 s** | 19 | пусто → `failure=timeout` |
| 9 | 09.11 17:29:43 | 7.2 s | 2 | ответ 65 симв. |
| 10 | 10.11 07:22:30 | 37.6 s | 4 | ответ 1994 симв. |
| 11 | 10.11 07:32:04 | 61.9 s | 6 | ответ 713 симв. |

Worker, те же job'ы (`hermes_job_done`):

| UTC окончания | outcome | failure | секунд |
|---|---|---|---|
| 09.11 15:40:24 | answered | – | 217.0 |
| 09.11 15:41:06 | answered | – | 255.3 |
| 09.11 15:43:01 | answered | – | 78.3 |
| 09.11 15:52:15 | no_answer | timeout | 605.6 |
| 09.11 15:58:34 | answered | – | 196.6 |
| 09.11 16:10:35 | no_answer | timeout | 603.8 |
| 09.11 16:22:22 | no_answer | timeout | 603.7 |
| 09.11 17:29:45 | no_answer | timeout | 603.3 |
| 09.11 17:29:51 | no_answer | timeout | 602.7 |

Пять прогонов из одиннадцати вышли в обрезку `HERMES_MAX_WAIT_SECONDS=600`.
Собственная модель Ванессы за это окно: 18 ходов, медиана 2.3 s, максимум
11.5 s (`turn_stage llm llm_ms=`). Модель не виновата.

## Причины

1. **Хост ушёл в OOM.** 2026-11-10 07:52:50 ядро убило процесс
   `node-MainThread` внутри `hermes-gateway.service` (1.76 ГБ anon RSS,
   `oom-kill: ... global_oom`), в 07:53:01 gateway получил SIGTERM при
   `loadavg_1m=124.27`, вместе с ним перезапустился worker. Машина: 4 ГБ
   RAM, 2 vCPU, 2 ГБ swap (на момент разбора занято 675 МБ). До этого
   `kanban dispatch: system memory pressure is elevated/critical`
   с 15:51 09.11 и до 07:39 10.11.
2. **На хосте гоняли тяжёлые прогоны.** 19–51 tool-call на запрос — это
   деплой и тесты клиентских репозиториев (git, pnpm, node) прямо на
   4-гиговой машине. Разрешено было 3 параллельных job'а
   (`HERMES_MAX_PARALLEL=3`), 10
   прогонов на api_server (`max_concurrent_runs: 10`) и до 10 дочерних
   агентов у делегирования. 09.11 в 17:19 два таких прогона шли
   одновременно и оба упёрлись в 600 s.
3. **Десять минут тишины.** Поллер отправлял ровно одну строку прогресса
   на +90 s (`hermes_job_progress`), дальше молчал до обрезки. Между
   «ещё копаюсь» и «не смогла» проходило до 8.5 минуты.
4. **Гонка на границе.** Прогон `run_1d68286c…` отдал ответ на 600.3 s
   (65 симв.), а поллер остановил его на 601.1 s — ответ существовал и был
   выброшен, в чат ушла отписка. То же по времени у `run_fb48fad4…`
   (562.5 s, ответ пустой, тут потерять было нечего).
5. **Файловый лог и trace агента мертвы с 09.11 13:13.** `/opt/vanessa/data/logs`
   принадлежал `root:root 755`, контейнер работает uid 1000 →
   `failed to open log file at logs` и `trace_log_open_failed
   path=logs/trace-agent.jsonl` при старте. `TRACE_LOG_ENABLED=true`
   ничего не писал: `trace-agent.jsonl` за окно пуст. Worker не задет —
   он монтирует named volume `vanessa_app_logs`, а не этот каталог.

## Что проверили и списали

- Telegram: `TelegramRetryAfter` / `Bad Gateway` за окно — сторона
  Telegram, aiogram переподключился, ходы не потеряны.
- Bridge деплой-вотчера: `announce_source_http_error status=502` ×26 и
  `announce_source_unreachable error=ReadTimeout` ×5 (09.11 13:17–14:41) —
  не ответил PC-бридж, повтор на следующем тике, к зависаниям релея
  отношения не имеет.
- `turn_processed action=ignore reason=bot_peer_side` ×2 — рабочая группа,
  другой бот, тишина by design.
- `broker_metrics_update_failed` в 07:52:56 — следствие OOM, не причина.
- `llm_cache` и провайдер DeepSeek: кэш работает, 5xx нет.

## Что починили (2026-11-10)

1. **Строка прогресса повторяется и несёт время.** Поллер
   (`vanessa/infrastructure/hermes/poll.py`) вызывает колбэк заново каждые
   `HERMES_PROGRESS_SECONDS`; `progress_line` в
   `config/behavior/hermes/followup.yaml` теперь
   `«Ещё копаюсь в этом, вернусь с ответом ({minutes} мин).»`, где
   `{minutes}` подставляет worker (`services/worker/hermes/progress.py`).
   Интервал 90 → 120 s (`.env.defaults` + `.env.local`): строки на 2, 4, 6,
   8 минуте, тишина не больше двух минут до обрезки на 600 s.
2. **Ответ с границы больше не теряется.** Перед остановкой по дедлайну
   поллер делает ещё один опрос (`_last_look` в `poll.py`); если прогон
   успел завершиться — отдаёт ответ, а не `timeout`.
3. **Параллелизм под 4 ГБ.** `HERMES_MAX_PARALLEL` 3 → 2 в
   `.env.local`; у Hermes на хосте `delegation.max_concurrent_children`
   10 → 2 и `api_server.max_concurrent_runs` 10 → 2 (`/root/.hermes/config.yaml`).
4. **Файловый лог агента.** `chown -R 1000:1000 /opt/vanessa/data/logs`;
   после перезапуска агента `agent.log` и `trace-agent.jsonl` пишутся
   (проверка: `ls -l /opt/vanessa/data/logs` не пуст, в
   `docker logs` больше нет `failed to open log file`).

## Осталось

- Swap 2 ГБ на 4-гиговой машине всё ещё тонкий: 07:52 показал, что
  одного тяжёлого прогона хватает. Кандидат — swap 4 ГБ или вынос
  клиентских сборок и тестов с этого хоста.
- Тяжёлая задача (деплой + тесты) физически не укладывается в 600 s;
  пока это лечится только повторами прогресса и понятной причиной в чате.
  Кандидат — отдельный лимит ожидания для задач с `deploy`/`test`.

## Где лежат доказательства

- `/root/.hermes/logs/gateway.log` — `inbound message` / `response ready:
  time=… api_calls=…` по всему окну.
- `/root/.hermes/logs/errors.log` — `deadline`-обрывы терминала,
  `Hardline block`, `Shutdown context: signal=SIGTERM … loadavg_1m=124.27`.
- `dmesg -T | grep -i oom-kill` — запись 07:52:50.
- `docker logs -t --since 24h vanessa-worker-1 | grep hermes_job_done` —
  outcome/failure/seconds по каждому job'у.
- `docker logs -t --since 24h vanessa-agent-1 | grep -E "turn_stage|turn_plan"` —
  `llm_ms` Ванессы по ходам.
