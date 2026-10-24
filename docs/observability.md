# Observability

Bot and API share a `request_id` via `X-Request-ID`. Features stay
**off** until you set flags in [`.env.defaults`](../.env.defaults) /
[`.env.example`](../.env.example). Code lives under `vanessa/infrastructure/observability/`.

## Prometheus and Grafana

`vanessa/infrastructure/observability/metrics/` (`__init__` is the facade; helpers like `observability.metrics.metrics_http`) exports:

- turns (reply vs ignore by reason)
- per-stage latency (gate, retrieve, compose)
- LLM tokens, requests, errors
- Telegram errors and HTTP latency

The agent serves `GET /metrics` on `API_PORT` (typically `:8000`), same
threaded probe server as bot/worker. The bot runs a threaded endpoint on
`BOT_METRICS_PORT` (typically `:9101`); the worker on
`WORKER_METRICS_PORT` (`:9102`). MCP processes expose `/metrics` on
`:8101`–`:8103`. All four gate `/metrics` with `METRICS_REQUIRE_TOKEN`
+ `API_INTERNAL_TOKEN` (`Authorization: Bearer` or `X-Internal-Token`).
Probes stay on `/health` and `/health/ready`.

Compose stack: include `docker-compose.monitoring.yml` (Prometheus,
Grafana, Alertmanager) in the **same** project as the app so Prometheus
shares the `backend` network. Include `docker-compose.logging.yml` for
Compose Loki/Vector. Do **not** also apply `deploy/k8s/logging` — one
Loki only. Hybrid: omit the logging compose file and set
`LOKI_URL=http://kubernetes.docker.internal:3100` (Docker Desktop
hostPort is on the k8s node, not Windows `localhost`). Grafana/Prometheus/Alertmanager
bind `127.0.0.1` so they are not on the LAN. Compose Loki is Cluster-network
only (no host port).

Scrape targets in `prometheus/prometheus.yml` are Compose DNS names
(`agent:8000`, `bot:9101`, `worker:9102`, `mcp-websearch:8101`, …), not
`host.docker.internal`. Kubernetes pods: `prometheus.k8s.yml`. After a
reload, check Prometheus **Status → Targets**. The `nginx` job is DOWN
unless `docker-compose.prod.yml` (nginx-exporter) is in the stack.

Labeled counters and histograms appear only after the first event, so
turn / LLM Grafana panels stay empty until live traffic. Nginx
latency needs nginx JSON logs plus Vector `log_to_metric`. Broker
panels need Redis stream transport.

If processes bind on the Docker host instead, mount
`prometheus/prometheus.host.yml` — do not mix both target sets in one
job.

Prometheus loads `prometheus/prometheus.yml` and evaluates alerts from
`prometheus/rules.yml`. Alertmanager is `alertmanager:9093` (default
receiver is a no-op until you add Slack/Telegram). Dashboards:

- `grafana/dashboards/vanessa.json`
- `grafana/dashboards/vanessa-broker.json`
- `grafana/dashboards/logs.json`

Enable with `METRICS_ENABLED` (and `METRICS_REQUIRE_TOKEN` in prod, with
Prometheus `authorization.credentials` / `bearer_token` or
`X-Internal-Token` on every scrape job).
Flags and defaults: [`.env.defaults`](../.env.defaults) /
[`.env.example`](../.env.example).

## Langfuse

`vanessa/infrastructure/observability/tracing/` wraps the orchestrator, pipeline stages,
LLM providers, and completers. You see gate → retrieve → compose as
spans plus per-call token usage.

User and chat ids are hashed with `LANGFUSE_ID_SALT` before they leave
the process. Sampling: `LANGFUSE_SAMPLE_RATE`. Self-hosted Langfuse is
`docker-compose.langfuse.yml`. Off until `LANGFUSE_ENABLED=true` and
keys are set — see [`.env.example`](../.env.example).

## Trace log

A per-turn debug log without Langfuse (no extra containers, no RAM). It
answers "why did she say that": the planner output, what retrieve gave
to compose, the prompt, the raw model output and the Hermes job.

Enable: add `TRACE_LOG_ENABLED=true` to `.env.local`, then recreate
`agent` and `worker`. Default is off. Code:
`vanessa/infrastructure/observability/trace_log/`.

File: `<LOG_DIR>/trace-<service>.jsonl` (`trace-agent.jsonl`,
`trace-worker.jsonl`). In Compose this is `/app/logs` in the `app_logs`
volume. Each process writes its own file, because two processes must not
rotate one file. Rotation: `TRACE_LOG_MAX_BYTES` (20 MB) ×
`TRACE_LOG_BACKUP_COUNT` (5) per file. A string field is clipped at
`TRACE_LOG_MAX_FIELD_CHARS`, reasoning at `TRACE_LOG_MAX_REASONING_CHARS`,
an image data URL at a short head.

One JSON line per step. Every line has `ts` (UTC), `service`,
`request_id` (`<chat_id>:<message_id>`, for example `-5441986530:174`),
`chat_id` and `stage`:

| stage | content |
|---|---|
| `planner` | planner LLM call: messages, raw output, reasoning, usage |
| `planner_plan` | the parsed plan |
| `gate_decision` | Decision Engine result |
| `reaction_gate` | reaction gate LLM call |
| `retrieve` | Hermes ask, web, pinned and knowledge notes (text), memes, session and earlier lines |
| `compose_prompt` | compose model, system prompt, user prompt |
| `compose_output` | every compose API call; `strict=true` is the untagged retry |
| `compose_reply` | the reply after post-processing |
| `compose_false_promise` | a "later" promise that compose retries |
| `compose_result` | the final reply or the refuse reason |
| `hermes_query` / `hermes_answer` / `hermes_sent` | the worker job: question, raw answer, parts sent |
| `hermes_followup` | the retell LLM call |

The Hermes job uses the request_id of the turn that asked, so one read
shows the turn and its late follow-up. LLM calls outside a turn (memory,
metrics, portraits, reminders) get one compact record each, with
`request_id` `-`.

Read one turn (the request_id is in the `turn_stage` lines of the agent
log; chat ids are negative, the script accepts them as they are):

```bash
cd /opt/vanessa
docker compose --env-file .env.defaults --env-file .env.local exec -T agent \
  python - -5441986530:174 < scripts/trace_turn.py
# recent turns:
docker compose --env-file .env.defaults --env-file .env.local exec -T agent \
  python - --last 20 < scripts/trace_turn.py
```

Locally: `python scripts/trace_turn.py <request_id> [--dir logs] [--file path]`.

Tracing never breaks a turn: a failed write logs one warning
(`trace_log_write_failed` / `trace_log_record_failed`) and the turn goes on.

Privacy: the file holds the full chat text, prompts and Hermes answers.
It stays on the server. Do not copy it into the repo, an issue or a chat.
Turn it off when the debug is done.

## RAG Triad evaluation

A sampled LLM-as-judge in `vanessa/infrastructure/observability/eval.py` scores:

- context relevance
- groundedness
- answer relevance

This is how “did we hallucinate the duck story?” is checked without
running a second expensive model on every turn.

## Alerting

`vanessa/infrastructure/observability/alerting/` watches local rolling windows:

- LLM error rate
- turn p95 latency
- Telegram errors
- provider HTTP 402 (balance)

Alerts go to `ALERTING_DEV_CHAT_ID` with per-rule cooldown so the owner
chat is not spammed.

## Ops notes

Prometheus scrapes api, bot, worker, and MCP on the Compose network.
Grafana is preloaded from the files above. There is no separate
`plans/observability.md` — this file is the catalog. Env flags:
[`.env.defaults`](../.env.defaults).
