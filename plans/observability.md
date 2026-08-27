# Observability for VanessaAI (Telegram bot + RAG)

Target stack (chosen): **Langfuse (self-hosted)** for LLM/RAG tracing, **Prometheus + Grafana**
for metrics and dashboards, **structured logs + Telegram alerts** for incidents. Implemented in
phases; each phase is independently shippable and testable.

The project is a two-process system: `bot` (aiogram, Telegram long-polling) and `api`
(FastAPI) that runs the reply pipeline `Gate -> Retrieve -> Compose -> Critique -> Finalize`
in [`conversation_orchestrator.py`](../app/services/orchestrator/conversation_orchestrator.py:54).
Observability must therefore be split across both processes and correlated by `request_id`
(already propagated via `X-Request-ID`, see [`middleware.py`](../app/api/middleware.py:8)).

---

## 1. Layers

| Layer | Tool | Where |
|---|---|---|
| Metrics (APM) | `prometheus-client` + Prometheus + Grafana | `/metrics` on `api:8000`, HTTP endpoint on `bot:<BOT_METRICS_PORT>` (default 9101) |
| LLM/RAG traces | Langfuse (self-hosted, docker-compose) | `api` process — pipeline, providers, retrievers |
| Logs | existing structured logging (`api.log` / `bot.log`) + `request_id` | both processes |
| Evaluation | deterministic RAG signals + LLM-as-judge sampler (RAG Triad) | `api` post-reply background job |
| Alerting | in-process `AlertManager` -> Telegram dev channel | both processes (each alerts on its own metrics) |

Correlation: `request_id` is the trace id; Langfuse trace `session_id = chat_id`, `user_id = sha256(sender_telegram_id)` (privacy), `metadata.request_id = request_id`.

---

## 2. Metric catalog (Prometheus)

All metrics live in a dedicated collector registry
([`app/observability/metrics.py`](../app/observability/metrics.py)) so tests never collide with
the default registry.

### Application / pipeline
- `vanessa_turns_total{action, reason}` — every processed message (reply / ignore + reason).
- `vanessa_turn_duration_seconds{action}` — end-to-end turn latency histogram.
- `vanessa_stage_duration_seconds{stage}` — per-stage latency: `plan`, `decision`, `embed`,
  `rag`, `humor_rag`, `llm`, `critic`, `total`.
- `vanessa_background_queue_length` — background executor queue depth (dropped jobs = overload).

### HTTP / API
- `vanessa_http_requests_total{method, path, status}`.
- `vanessa_http_request_duration_seconds{method, path}`.
- `vanessa_http_client_requests_total{service, status}` (bot -> API).

### LLM
- `vanessa_llm_requests_total{provider, model, kind, status}` — `kind` = `generation`
  (composer) or `planner` / `critic` / `memory` / `metrics` (completer callers).
- `vanessa_llm_tokens_total{provider, model, kind, token_type}` — `token_type` = `prompt` / `completion` / `total`.
- `vanessa_llm_errors_total{provider, model, kind, error_type}` — e.g. `rate_limit`,
  `server_error`, `auth`, `network`.
- `vanessa_llm_duration_seconds{provider, model, kind}`.

### RAG
- `vanessa_rag_search_total{source}` — `semantic` (knowledge vault), `raw` (hybrid history), `humor`.
- `vanessa_rag_hits_total{source}` — number of blocks returned.
- `vanessa_rag_score{source}` — histogram of the top retrieval score (proxy for context relevance).
- `vanessa_rag_empty_total{source}` — empty retrieval (drives "context not found" alert).

### Telegram
- `vanessa_telegram_requests_total{operation, status}` — `send_reply`, `typing`, `get_me`, ...
- `vanessa_telegram_errors_total{operation, error_type}` — `flood`, `network`, `bad_request`, ...

### Process / finance
- `vanessa_process_start_time_seconds` — uptime.
- `vanessa_rag_eval_score{dimension}` — RAG Triad gauge: `context_relevance`, `groundedness`, `answer_relevance`.

---

## 3. Tracing / span map (Langfuse)

One trace per processed message, named `telegram_rag_pipeline`.

```
telegram_rag_pipeline                    (trace; metadata: request_id, chat_id_hash, message preview)
├── gate                                  (span: plan_ms, decision_ms, action, reason)
│   ├── llm_planner                       (generation via completer, kind=planner)
│   └── decision                          (span: relevance score)
├── retrieve                              (span)
│   ├── rag_semantic                      (span: query, indexes, hits, top_score)
│   ├── rag_hybrid                        (span: query, vector_hits, fts_hits, top_score)
│   └── rag_humor                         (span: query, quotes)
├── compose                               (span)
│   └── llm_generation                    (generation via provider: prompt, output, usage)
├── critique                              (span; verdict status/score)        [optional]
│   └── llm_critic                        (generation via completer, kind=critic)
└── finalize                              (span: reply_len, sticker_tag)
```

Background LLM work (post-reply) is traced under its own traces so it never bloats the reply
trace: `memory_extraction` (kind=memory), `metrics_extraction` (kind=metrics),
`knowledge_sweep` (kind=sweep).

Tracing is **off by default** (`LANGFUSE_ENABLED=false`) and wrapped in a `NullTracer` so the
pipeline and all tests run unchanged. `LANGFUSE_SAMPLE_RATE` (0..1) controls volume; user/chat
ids are hashed with a salt before being sent.

---

## 4. RAG Triad evaluation

- **Deterministic signals (always on, free):** top retrieval score histograms, hits per query,
  empty-retrieval counter, context length in the prompt, LLM duration vs. retrieval duration.
- **LLM-as-judge (sampled, `RAG_EVAL_SAMPLE_RATE`):** for a fraction of turns with a reply,
  a background job runs three judge prompts over the final trace payload:
  - `context_relevance` — does the retrieved context answer the user's question?
  - `groundedness` — is the answer supported only by the retrieved context (hallucination check)?
  - `answer_relevance` — does the answer address the user's question?
  Judge verdicts are posted as Langfuse `score` on the trace and exported as
  `vanessa_rag_eval_score{dimension}` gauges. Judge model: `RAG_EVAL_MODEL` (defaults to the
  active planner model).

---

## 5. Alerting (Telegram dev channel)

`AlertManager` ([`app/observability/alerting.py`](../app/observability/alerting.py)) runs a
periodic task in each process and evaluates local rolling windows:

| Alert | Condition | Window |
|---|---|---|
| High error rate | error share of all turns / LLM calls > `ALERTING_ERROR_RATE_THRESHOLD` (5%) | `ALERTING_WINDOW_SECONDS` (300s) |
| Slow replies | turn p95 > `ALERTING_LATENCY_P95_THRESHOLD` (7s) | 300s |
| LLM error spike | LLM error count / requests > threshold | 300s |
| Empty RAG | empty-retrieval share > threshold (context not found) | 300s |
| Queue overload | background queue 100% full | window |

Alerts are sent via the bot token to `ALERTING_DEV_CHAT_ID` with a cooldown per rule
(`ALERTING_COOLDOWN_SECONDS`, default 10 min) to avoid spam. Balance check
(`ALERTING_BALANCE_CHECK_HOURS`) pings the provider (DeepSeek) and alerts on HTTP 402.

---

## 6. Infra (docker-compose additions)

- `langfuse` (self-hosted) + dedicated `langfuse-db` (Postgres) — traces UI on `:3000`.
- `prometheus` — scrapes `api:8000/metrics` and `bot:9101/metrics`.
- `grafana` — provisioning with datasource + dashboard JSON on `:3001` (avoid clash with Langfuse).

Grafana dashboard `vanessa.json` includes panels: RPS, turn latency p50/p95/p99, LLM tokens by
provider/model, LLM error rate, RAG hits/empty, RAG eval scores, Telegram errors, queue depth.

---

## 7. Implementation phases

1. **Metrics foundation** — `app/observability/metrics.py`, `/metrics` endpoint, token usage
   capture in providers + completers, latency/error instrumentation of stages, middleware,
   bot send path, RAG retrievers.
2. **LLM/RAG tracing** — `app/observability/tracing.py` (Null/Langfuse tracer), spans in the
   orchestrator, stages, providers, completers, retrievers; privacy hashing + sampling.
3. **RAG Triad eval** — deterministic signals + LLM-as-judge sampler background job.
4. **Dashboards + alerting** — docker-compose (prometheus/grafana/langfuse), Grafana
   provisioning, `AlertManager` + Telegram delivery, balance check.
5. **Docs** — `.env.example`, README observability section, tests for all new modules.

Each phase keeps the default config **off** so existing behavior and the 400+ tests stay green.
