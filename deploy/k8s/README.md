# VanessaAI — Kubernetes design (Phase 5)

> Docker Desktop hybrid lab. docker-compose (Phases 1–4) is the default
> runtime and the honest hosted path. These manifests map the same
> topology; they are not a production cluster by themselves.

This maps the async, MCP-compliant topology onto Kubernetes: every service is
an isolated pod with its own CPU/RAM limits, config comes from ConfigMaps
(never code or images), **secrets come from one CLI**, consumers scale via HPA,
and NetworkPolicies restrict who can talk to the broker and the MCP servers.

## Secrets — one entry point

Do not `kubectl apply` a Secret YAML. There is no committed `11-secrets.yaml`.
The only supported way to put secrets **and** the live ConfigMap into the
cluster is:

```bash
poetry run python scripts/k8s_secrets.py check
poetry run python scripts/k8s_secrets.py apply --ensure-namespace
```

What it does:

1. Reads `.env.defaults` then the overlay (default: `.env.local`; pass
   `--from-env` `.env` or `.env.production`). Overlay keys win. Non-secret
   `.env.defaults`.
2. Keeps **only** the secret-key catalog (`vanessa/k8s/secrets.py` /
   `deploy/k8s/secrets.env.example`). Hosts, ports, feature flags stay in
   the ConfigMap — they never leak into the Secret.
3. Validates required keys (token, DB password, broker URL, plus the active
   LLM key; web-search key if that feature is on).
4. `kubectl apply`s Opaque Secret `vanessa-secrets` and ConfigMap
   `vanessa-config`. Pods load the ConfigMap via `envFrom` and secrets via
   per-workload `secretKeyRef` (MCP servers do not get the Telegram token).

`check` / apply logs **key names only**, never values. `--dry-run` is
`kubectl --dry-run=client`.

```bash
poetry run python scripts/k8s_secrets.py apply --dry-run
poetry run python scripts/k8s_secrets.py example
```

Re-running `apply` updates the live Secret (idempotent). After rotating a
key, restart the workloads so they pick up the new env:

```bash
kubectl -n vanessa rollout restart deploy
```

## Topology

```
              ┌──────────────┐
 Telegram ──▶ │ bot (Deploy) │  long-polling; publishes turns
              └──────┬───────┘
                     │ Redis Streams (broker)
        ┌────────────┴─────────────┐
        ▼                          ▼
    ┌──────────────┐            ┌──────────────┐
    │ agent   │  tasks ──▶ │ worker       │  sweep/portrait/indexing
    │ (Deploy+HPA) │            │ (Deploy+HPA) │
    └──────┬───────┘            └──────────────┘
        │ MCP over HTTP (SSE)
        ├──────────▶ mcp-websearch
        ├──────────▶ mcp-knowledge
        └──────────▶ mcp-vision
   agent ──▶ Postgres / Qdrant / Redis   (managed or StatefulSets)
   worker    ──▶ Postgres / Qdrant
```

## Namespace & network

- Single namespace `vanessa`. Everything below uses it.
- `NetworkPolicy` (`30-networkpolicy.yaml`) is **opt-in**. Do not apply it
  for a Docker Desktop run that reaches Postgres/Qdrant/Redis on the host
  (`host.docker.internal`) — default-deny will black-hole that traffic.
  Apply it only when those backends run in-cluster with `component:
  redis|postgres|qdrant` labels.
- When applied, isolation is:
  - `bot` → broker (Redis 6379) only; never to Postgres/Qdrant/MCP.
  - `agent` → broker, Postgres, Qdrant, MCP servers, (observability).
  - `worker` → broker, Postgres, Qdrant.
  - `mcp-knowledge` → Postgres (vault reads).
  - MCP servers: only accept traffic from `agent`.
  - default-deny ingress per namespace (except monitoring + ingress-controller).

## Config: ConfigMap vs Secret

Everything is env-driven (`vanessa.config.settings`). Mapping is mechanical:

| Kind | Examples (keys = env names) |
|---|---|
| `ConfigMap` | `BROKER_STREAMS_PREFIX`, `BROKER_GROUP_*`, `BROKER_RPC_TIMEOUT_SECONDS`, `WORKER_ENABLED`, `WORKER_METRICS_PORT`, `MCP_*_URL`, `POSTGRES_HOST/PORT/USER/DB`, `QDRANT_*`, `RAG_*`, `DECISION_*`, `KNOWLEDGE_*`, `VISION_*`, `LOG_*`, `METRICS_*` |
| `Secret` (`scripts/k8s_secrets.py`) | `TELEGRAM_BOT_TOKEN`, `POSTGRES_PASSWORD`, `DEEPSEEK_API_KEY`, `ANTHROPIC_API_KEY`, `WEB_SEARCH_API_KEY`, `API_INTERNAL_TOKEN`, `HF_TOKEN`, `BROKER_REDIS_URL`, `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`/`LANGFUSE_ID_SALT` |

`10-configmap.yaml` is an example only — kustomize does not apply it.
`kubectl apply -k` would otherwise clobber the generated ConfigMap. The
secret catalog is the allow-list in `vanessa/k8s/secrets.py`.

## Workloads, resources & HPA

| Service | Image/command | requests | limits | HPA |
|---|---|---|---|---|
| `bot` | `vanessa-agent:local` / `python -m services.bot.main` | 100m / 256Mi | 500m / 1Gi | no (1 replica; long poll) |
| `agent` | `vanessa-agent:local` / uvicorn | 250m / 512Mi | 2 CPU / 4Gi | CPU |
| `worker` | `vanessa-agent:local` / `python -m services.worker.main` | 500m / 1Gi | 4 CPU / 6Gi | CPU |
| `mcp-websearch` | runner websearch | 50m / 128Mi | 500m / 512Mi | no |
| `mcp-knowledge` | runner knowledge | 100m / 256Mi | 1 CPU / 1Gi | no |
| `mcp-vision` | runner vision | 100m / 256Mi | 1 CPU / 2Gi | no |

Images are `vanessa-agent:local` with `imagePullPolicy: IfNotPresent` so a
locally built Compose image is visible to Docker Desktop Kubernetes without a
push (and without Docker Hub pulling `:latest`).

```bash
docker compose build agent
docker tag vanessa-agent:latest vanessa-agent:local
```

## State

- Postgres / Qdrant / Redis: run as managed services (preferred) or
  StatefulSets with PVCs. Not in these manifests.
- Local hybrid: keep them in docker-compose and set `POSTGRES_HOST` /
  `QDRANT_HOST` / `BROKER_REDIS_URL` to `host.docker.internal` in the
  ConfigMap / `.env` (then re-run `k8s_secrets.py apply` so the broker URL
  in the Secret matches).
- Knowledge vault is Postgres (`KNOWLEDGE_STORE=postgres`). There is no
  shared knowledge PVC.
- HuggingFace embedding model is baked into the image at
  `HF_HOME=/app/.cache/huggingface` (no PVC; an empty volume would hide it).

## Rollout & smoke

- Rollouts are standard `kubectl rollout restart deployment/<name>`; the
  broker consumer groups survive restarts (messages stay pending until acked),
  and the `message_id` dedup prevents double-processing.
- Zero-downtime: `maxUnavailable: 0` + `maxSurge: 1` on `agent` (it owns
  the turn worker), same for `worker` and the MCP servers.

## Observability

- `GET /metrics` on agent `:8000`, bot `:9101`, worker `:9102`, MCP
  tool ports. All four honor `METRICS_REQUIRE_TOKEN`. Compose Prometheus
  (`prometheus.yml` or `prometheus.k8s.yml`) scrapes them. Rules in
  `prometheus/rules.yml` go to Compose Alertmanager (`:9093`). There is
  no in-cluster Prometheus Operator / ServiceMonitor.
- Langfuse stays compose or managed. Not in these manifests.
- Logs: JSON stdout (`LOG_JSON=true`). Vector DaemonSet in
  `deploy/k8s/logging` tails `/var/log/pods` into Loki (PVC `loki-data`).
  `kubectl apply -k deploy/k8s/` is **apps only**. Logging is
  `kubectl apply -k deploy/k8s/logging` or the desktop overlay.
- Hybrid: omit `docker-compose.logging.yml`, set
  `LOKI_URL=http://host.docker.internal:3100` (desktop overlay hostPort 3100).
  Grafana stays in Compose.

```bash
kubectl apply -k deploy/k8s/logging
kubectl -n logging get pods
```

## Applying (Docker Desktop)

1. Settings → Kubernetes → Enable Kubernetes → wait for "Kubernetes running".
2. `kubectl config get-contexts` should list `docker-desktop`.
3. Build the image: `docker compose build agent && docker tag vanessa-agent:latest vanessa-agent:local`
4. Put real values in `.env.local` / `.env` (never in git).
5. Apply Secret + ConfigMap, then workloads:

```bash
poetry run python scripts/k8s_secrets.py apply --ensure-namespace
kubectl apply -k deploy/k8s/
```

`kubectl apply -k deploy/k8s/`  (apps only, no ConfigMap, no NetworkPolicy)
`kubectl apply -k deploy/k8s/overlays/desktop`  (Docker Desktop hybrid)

Docker Desktop (hybrid: Postgres/Qdrant/Redis stay in compose):

```bash
docker compose stop agent bot worker mcp-websearch mcp-knowledge mcp-vision
# Keep Compose Prometheus/Grafana; omit docker-compose.logging.yml
# (cluster Loki). Set LOKI_URL=http://host.docker.internal:3100
docker compose --env-file .env.defaults --env-file .env.local \
  -f docker-compose.infra.yml -f docker-compose.monitoring.yml up -d
docker tag vanessa-agent:latest vanessa-agent:local
python scripts/k8s_secrets.py apply --ensure-namespace \
  --broker-host host.docker.internal \
  --postgres-host host.docker.internal \
  --qdrant-host host.docker.internal \
  --langfuse-host http://host.docker.internal:3000
kubectl apply -k deploy/k8s/overlays/desktop
kubectl -n vanessa port-forward svc/agent 8000:8000
```

The desktop overlay publishes Loki hostPort 3100 so Compose Grafana can
reach it. That port binds every host interface — Desktop only. Hosts
come from the CLI flags above, not from kustomize. Vanessa stays
restricted PSS; logging stays privileged for Vector.

```bash
kubectl -n vanessa get pods
kubectl -n vanessa get deploy,svc,hpa
kubectl -n vanessa logs deploy/agent
kubectl -n vanessa port-forward svc/agent 8000:8000
```

Opt-in NetworkPolicy (in-cluster backends only):

```bash
kubectl apply -f deploy/k8s/base/30-networkpolicy.yaml
```
