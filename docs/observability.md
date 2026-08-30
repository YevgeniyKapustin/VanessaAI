# Observability

Bot and API share a `request_id` via `X-Request-ID`. Features stay
**off** until you set flags in [`.env.defaults`](../.env.defaults) /
[`.env.example`](../.env.example). Code lives under `vanessa/infrastructure/observability/`.

## Prometheus and Grafana

`vanessa/infrastructure/observability/metrics.py` exports:

- turns (reply vs ignore by reason)
- per-stage latency (gate, retrieve, compose)
- LLM tokens, requests, errors
- RAG hits, empty retrieval, scores
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
`LOKI_URL=http://host.docker.internal:3100`. Grafana/Prometheus/Alertmanager
bind `127.0.0.1` so they are not on the LAN. Compose Loki is Cluster-network
only (no host port).

Scrape targets in `prometheus/prometheus.yml` are Compose DNS names
(`agent:8000`, `bot:9101`, `worker:9102`, `mcp-websearch:8101`, …), not
`host.docker.internal`. Kubernetes pods: `prometheus.k8s.yml`. After a
reload, check Prometheus **Status → Targets**. The `nginx` job is DOWN
unless `docker-compose.prod.yml` (nginx-exporter) is in the stack.

Labeled counters and histograms appear only after the first event, so
turn / LLM / RAG Grafana panels stay empty until live traffic. Nginx
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

`vanessa/infrastructure/observability/tracing.py` wraps the orchestrator, pipeline stages,
LLM providers, and completers. You see gate → retrieve → compose as
spans plus per-call token usage.

User and chat ids are hashed with `LANGFUSE_ID_SALT` before they leave
the process. Sampling: `LANGFUSE_SAMPLE_RATE`. Self-hosted Langfuse is
`docker-compose.langfuse.yml`. Off until `LANGFUSE_ENABLED=true` and
keys are set — see [`.env.example`](../.env.example).

## RAG Triad evaluation

Deterministic signals are always collected on replied turns. A sampled
LLM-as-judge in `vanessa/infrastructure/observability/eval.py` scores:

- context relevance
- groundedness
- answer relevance

This is how “did we hallucinate the duck story?” is checked without
running a second expensive model on every turn.

## Alerting

`vanessa/infrastructure/observability/alerting.py` watches local rolling windows:

- LLM error rate
- turn p95 latency
- empty RAG retrieval
- Telegram errors
- provider HTTP 402 (balance)

Alerts go to `ALERTING_DEV_CHAT_ID` with per-rule cooldown so the owner
chat is not spammed.

## Ops notes

Prometheus scrapes api, bot, worker, and MCP on the Compose network.
Grafana is preloaded from the files above. There is no separate
`plans/observability.md` — this file is the catalog. Env flags:
[`.env.defaults`](../.env.defaults).
