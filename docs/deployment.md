# Deployment

Local Docker Compose is the default runtime. Kubernetes manifests map
the same topology for a Docker Desktop hybrid lab (apps in-cluster;
Postgres, Redis, and Qdrant stay on Compose). Hosted production on a
single machine is the Compose prod overlay (unpublished API + Nginx).
CI ([`.github/workflows/ci.yml`](../.github/workflows/ci.yml)) runs tests
on push/PR; image build and cluster apply are not in GitHub Actions yet.

## Repository layout

```
services/
  bot/          Telegram transport
  agent/        Turn pipeline + notes/health HTTP
  worker/       Indexing, sweep, memory jobs
  mcp/          Tool servers
vanessa/
  core/             DTOs, ports, session
  pipeline/         Gate, retrieve, compose, orchestrator
  knowledge/        Vault, memory, nicknames
  infrastructure/   db, broker, ingest, observability
  config/ contracts/
  k8s/              Deploy helpers
config/content/ Per-section YAML (persona, conversation, llm, …)
knowledge/      Runtime vault data
scripts/        import, reindex, portraits, stickers, k8s secrets
tests/          Automated tests
deploy/k8s/     Kubernetes manifests
```

## Local Compose

Copy [`.env.example`](../.env.example) to `.env.local` and fill it. That
file is the overlay recipe (secrets, flags, `COMPOSE_FILE`). Defaults:
[`.env.defaults`](../.env.defaults).

```bash
python scripts/prepare_env.py
# python scripts/prepare_env.py --from .env --dry-run

docker compose --env-file .env.defaults --env-file .env.local up -d --build
```

`prepare_env.py` copies secrets and non-default knobs from `.env` into
`.env.local`. If `up` fails because `migrate` exited non-zero, inspect
`docker compose logs migrate` and re-run migrate. `agent` waits on
`service_completed_successfully`.

Services: agent `http://localhost:8000`, Qdrant `6333`, Postgres `5432`.
Nginx under `deploy/nginx/` is only for the Compose prod path.

## Production Compose

No bind-mounts, agent unpublished, Nginx. Copy `.env.example` to
`.env.production` (gitignored; host or CI). Uncomment the production
block in that file. Then:

```bash
docker compose --env-file .env.defaults --env-file .env.production \
  -f docker-compose.yml -f docker-compose.infra.yml \
  -f docker-compose.langfuse.yml -f docker-compose.monitoring.yml \
  -f docker-compose.logging.yml -f docker-compose.prod.yml up -d --build
```

YAML content (not env): [Configuration](configuration.md).

## Import history (optional)

```bash
poetry install
poetry run python scripts/import_telegram_history.py --export path/to/result.json
```

## Tests

```bash
poetry run pytest
```

## Kubernetes

Rolling updates: `maxUnavailable: 0` + `maxSurge: 1` on agent /
worker / MCP; probes on `/health/live` and `/health/ready`. Design,
topology, NetworkPolicy, and secrets CLI: **[deploy/k8s/README.md](../deploy/k8s/README.md)**.
Do not duplicate that doc here.

```bash
poetry run python scripts/k8s_secrets.py apply --ensure-namespace
kubectl apply -k deploy/k8s/
kubectl -n vanessa rollout restart deploy
```

- `GET /health` / `/health/live` — liveness (process only). Bot and worker
  serve `/health` on the metrics port even when metrics are off.
- `GET /health/ready` — Postgres `SELECT 1`; kubelet keeps the pod out of
  Service until 200.
- API: uvicorn `--timeout-graceful-shutdown`; bot: aiogram drain on
  SIGTERM.

`scripts/k8s_secrets.py apply` reads a host overlay (not git) and applies
`vanessa-secrets` plus `vanessa-config`. Do not `kubectl apply` the example
`10-configmap.yaml`.
