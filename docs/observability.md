# Observability

Bot and API share a `request_id` via `X-Request-ID`. Features stay
**off** until you set flags in [`.env.defaults`](../.env.defaults) /
[`.env.example`](../.env.example). Code lives under `app/observability/`.

## Prometheus and Grafana

`app/observability/metrics.py` exports:

- turns (reply vs ignore by reason)
- per-stage latency (gate, retrieve, compose)
- LLM tokens, requests, errors
- RAG hits, empty retrieval, scores
- Telegram errors and HTTP latency

The API serves `GET /metrics`. The bot runs a threaded endpoint on
`BOT_METRICS_PORT` (typically `:9101`). Product counters also exist at
`GET /api/v1/metrics`.

Compose stack: `docker-compose.monitoring.yml`. Prometheus loads
`prometheus/prometheus.yml` and evaluates alerts from
`prometheus/rules.yml` (`rule_files`). Dashboards:

- `grafana/dashboards/vanessa.json`
- `grafana/dashboards/vanessa-broker.json`

Enable with `METRICS_ENABLED` (and `METRICS_REQUIRE_TOKEN` in prod).
Flags and defaults: [`.env.defaults`](../.env.defaults) /
[`.env.example`](../.env.example).

## Langfuse

`app/observability/tracing.py` wraps the orchestrator, pipeline stages,
LLM providers, and completers. You see gate → retrieve → compose as
spans plus per-call token usage.

User and chat ids are hashed with `LANGFUSE_ID_SALT` before they leave
the process. Sampling: `LANGFUSE_SAMPLE_RATE`. Self-hosted Langfuse is
`docker-compose.langfuse.yml`. Off until `LANGFUSE_ENABLED=true` and
keys are set — see [`.env.example`](../.env.example).

## RAG Triad evaluation

Deterministic signals are always collected on replied turns. A sampled
LLM-as-judge in `app/observability/eval.py` scores:

- context relevance
- groundedness
- answer relevance

This is how “did we hallucinate the duck story?” is checked without
running a second expensive model on every turn.

## Alerting

`app/observability/alerting.py` watches local rolling windows:

- LLM error rate
- turn p95 latency
- empty RAG retrieval
- Telegram errors
- provider HTTP 402 (balance)

Alerts go to `ALERTING_DEV_CHAT_ID` with per-rule cooldown so the owner
chat is not spammed.

## Ops notes

Prometheus scrapes both processes; Grafana is preloaded from the files
above. There is no separate `plans/observability.md` — this file is the
catalog. Env flags: [`.env.defaults`](../.env.defaults).
