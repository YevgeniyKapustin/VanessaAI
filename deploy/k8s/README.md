# VanessaAI — Kubernetes design (Phase 5)

> Design + local apply path. docker-compose (Phases 1–4) stays the default
> runtime. These manifests are the K8s mapping of the same topology.

This maps the async, MCP-compliant topology onto Kubernetes: every service is
an isolated pod with its own CPU/RAM limits, config comes from ConfigMaps
(never code or images), **secrets come from one CLI**, consumers scale via HPA,
and NetworkPolicies restrict who can talk to the broker and the MCP servers.

## Secrets — one entry point

Do not `kubectl apply` a Secret YAML. There is no committed `11-secrets.yaml`.
The only supported way to put secrets into the cluster is:

```bash
poetry run python scripts/k8s_secrets.py check
poetry run python scripts/k8s_secrets.py apply --ensure-namespace
```

What it does:

1. Reads a host env overlay (default: project `.env`; pass `--from-env`
   `.env.local` or `.env.production`). Non-secret defaults live in
   `.env.defaults`.
2. Keeps **only** the secret-key catalog (`app/k8s/secrets.py` /
   `deploy/k8s/secrets.env.example`). Hosts, ports, feature flags stay in
   the ConfigMap — they never leak into the Secret.
3. Validates required keys (token, DB password, broker URL, plus the active
   LLM key; web-search key if that feature is on).
4. `kubectl apply`s one Opaque Secret: `vanessa-secrets`. Pods load it via
   `envFrom.secretRef`.
5. If `.ssh/obsidian` (or `OBSIDIAN_SSH_DIR`) exists, also applies
   `vanessa-obsidian-ssh`. Missing SSH is skipped, not a hard fail.

`check` / apply logs **key names only**, never values. `--dry-run` is
`kubectl --dry-run=client`.

```bash
poetry run python scripts/k8s_secrets.py apply --dry-run --skip-ssh
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
    │ agent-core   │  tasks ──▶ │ worker       │  sweep/portrait/indexing
    │ (Deploy+HPA) │            │ (Deploy+HPA) │
    └──────┬───────┘            └──────────────┘
        │ MCP over HTTP (SSE)
        ├──────────▶ mcp-websearch
        ├──────────▶ mcp-knowledge
        └──────────▶ mcp-vision
   agent-core ──▶ Postgres / Qdrant / Redis   (managed or StatefulSets)
   worker    ──▶ Postgres / Qdrant / knowledge vault PVC
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
  - `agent-core` → broker, Postgres, Qdrant, MCP servers, (observability).
  - `worker` → broker, Postgres, Qdrant, knowledge-vault PVC.
  - MCP servers: only accept traffic from `agent-core`.
  - default-deny ingress per namespace (except monitoring + ingress-controller).

## Config: ConfigMap vs Secret

Everything is env-driven (`app.config.settings`). Mapping is mechanical:

| Kind | Examples (keys = env names) |
|---|---|
| `ConfigMap` | `TRANSPORT`, `BROKER_STREAMS_PREFIX`, `BROKER_GROUP_*`, `BROKER_RPC_TIMEOUT_SECONDS`, `WORKER_ENABLED`, `WORKER_METRICS_PORT`, `MCP_*_URL`, `POSTGRES_HOST/PORT/USER/DB`, `QDRANT_*`, `RAG_*`, `DECISION_*`, `KNOWLEDGE_*`, `VISION_*`, `LOG_*`, `METRICS_*`, `OBSIDIAN_*` paths |
| `Secret` (`scripts/k8s_secrets.py`) | `TELEGRAM_BOT_TOKEN`, `POSTGRES_PASSWORD`, `DEEPSEEK_API_KEY`, `ANTHROPIC_API_KEY`, `WEB_SEARCH_API_KEY`, `API_INTERNAL_TOKEN`, `HF_TOKEN`, `BROKER_REDIS_URL`, `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`/`LANGFUSE_ID_SALT`, `OBSIDIAN_GIT_REMOTE` |

`10-configmap.yaml` is representative; the full non-secret key set mirrors
`app/config/settings_sections.py`. The secret catalog is the allow-list in
`app/k8s/secrets.py` — not a dump of `.env`.

## Workloads, resources & HPA

| Service | Image/command | requests | limits | HPA |
|---|---|---|---|---|
| `bot` | `vanessa-app:local` / `python -m app.bot.main` | 100m / 256Mi | 500m / 1Gi | no (2 replicas fixed) |
| `agent-core` | `vanessa-app:local` / uvicorn | 250m / 512Mi | 2 CPU / 4Gi | CPU |
| `worker` | `vanessa-app:local` / `python -m app.worker.main` | 500m / 1Gi | 4 CPU / 6Gi | CPU |
| `mcp-websearch` | runner websearch | 50m / 128Mi | 500m / 512Mi | CPU |
| `mcp-knowledge` | runner knowledge | 100m / 256Mi | 1 CPU / 1Gi | CPU |
| `mcp-vision` | runner vision | 100m / 256Mi | 1 CPU / 2Gi | CPU |

Images are `vanessa-app:local` with `imagePullPolicy: IfNotPresent` so a
locally built image is visible to Docker Desktop Kubernetes without a push
(and without Docker Hub pulling `:latest`).

```bash
docker build -t vanessa-app:local .
```

## State

- Postgres / Qdrant / Redis: run as managed services (preferred) or
  StatefulSets with PVCs. Not in these manifests.
- Local hybrid: keep them in docker-compose and set `POSTGRES_HOST` /
  `QDRANT_HOST` / `BROKER_REDIS_URL` to `host.docker.internal` in the
  ConfigMap / `.env` (then re-run `k8s_secrets.py apply` so the broker URL
  in the Secret matches).
- Knowledge vault (writeable, git-backed) → `PersistentVolumeClaim`
  (`40-pvc.yaml`) shared by `worker` (writes) and `mcp-knowledge` (reads) via
  ReadWriteMany (e.g. NFS) — read-only for `agent-core` is acceptable.
- HuggingFace embedding model is baked into the image at
  `HF_HOME=/app/.cache/huggingface` (no PVC; an empty volume would hide it).

## Rollout & smoke

- Rollouts are standard `kubectl rollout restart deployment/<name>`; the
  broker consumer groups survive restarts (messages stay pending until acked),
  and the `message_id` dedup prevents double-processing.
- Zero-downtime: `maxUnavailable: 0` + `maxSurge: 1` on `agent-core` (it owns
  the turn worker), same for `worker` and the MCP servers.

## Observability

- Each pod exposes `/metrics`; scrape via a ServiceMonitor (Prometheus Operator)
  or a single `ClusterRole`-scoped prometheus. `prometheus/rules.yml` already
  contains the DLQ / consumer-lag / worker-backlog alerts.
- Langfuse stays as-is (compose or managed). Not in these manifests.
- Logs are cloud-native: apps write JSON to stdout (`LOG_JSON=true`, no files).
  A Vector DaemonSet (`deploy/k8s/logging`) tails `/var/log/pods` and ships to
  Loki. Grafana Explore uses the Loki datasource (compose: `http://loki:3100`;
  cluster: `kubectl -n logging port-forward svc/loki 3100:3100`).

```bash
kubectl apply -k deploy/k8s/logging
kubectl -n logging get pods
kubectl -n logging port-forward svc/loki 3100:3100
```

`kubectl apply -k deploy/k8s/` and the desktop overlay already include logging.

## Applying (Docker Desktop)

1. Settings → Kubernetes → Enable Kubernetes → wait for "Kubernetes running".
2. `kubectl config get-contexts` should list `docker-desktop`.
3. Build the image: `docker build -t vanessa-app:local .`
4. Put real values in `.env.local` / `.env` (never in git).
5. Apply secrets, then workloads:

```bash
poetry run python scripts/k8s_secrets.py apply --ensure-namespace
kubectl apply -k deploy/k8s/
```

`kubectl apply -k deploy/k8s/`  (base: includes PVCs, no NetworkPolicy)
`kubectl apply -k deploy/k8s/overlays/desktop`  (Docker Desktop hybrid)

Docker Desktop (hybrid: Postgres/Qdrant/Redis stay in compose):

```bash
docker compose stop api bot worker mcp-websearch mcp-knowledge mcp-vision
docker tag vanessa-app:latest vanessa-app:local
poetry run python scripts/k8s_secrets.py apply --ensure-namespace --broker-host host.docker.internal
kubectl apply -k deploy/k8s/overlays/desktop
```

The desktop overlay points DB/Qdrant at `host.docker.internal`, uses
`emptyDir` for the knowledge vault (Pod Security baseline forbids hostPath),
relaxes enforce to `baseline`, and runs a single bot replica.

```bash
kubectl -n vanessa get pods
kubectl -n vanessa get deploy,svc,hpa,pvc
kubectl -n vanessa logs deploy/agent-core
kubectl -n vanessa port-forward svc/agent-core 8000:8000
```

Opt-in NetworkPolicy (in-cluster backends only):

```bash
kubectl apply -f deploy/k8s/30-networkpolicy.yaml
```
