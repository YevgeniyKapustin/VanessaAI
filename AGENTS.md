# VanessaAI

Telegram group bot (VRChat is a second adapter). Default is silence.
Domain lives in `vanessa/`; process entrypoints in `services/`. Longer
docs: `README.md`, `docs/architecture.md`. Python style:
`.agents/rules/python-clean-code.mdc`.
Layout: `.agents/rules/package-layout.mdc`.

## Runtime

`adapter → Redis Streams → agent → ingress → gate → retrieve ∥ scene → compose → post`

Turns never go over HTTP. Agent HTTP is health/metrics only (`:8000`).
Do not add chat/notes routes or FastAPI to the agent.

Pipeline roles stay four: adapter, agent, worker, mcp. Adapters may be
several (`services/bot` Telegram, `services/presence` VRChat). Presence
is a host process — not in server compose. Do not import sibling
services. Adapters stay adapters: no `vanessa.pipeline`,
`vanessa.knowledge`, or `vanessa.infrastructure.db`.

Wire stages through `vanessa/core` protocols and `vanessa/contracts`.
`vanessa.core` must not import knowledge, pipeline, or infrastructure.
`pipeline.decision` must not import llm, vision, or infrastructure.
`vanessa.knowledge` must not import pipeline.

Planner `should_reply` is a suggestion. Decision Engine can veto.

Knowledge: Postgres only. `KNOWLEDGE_STORE=filesystem` is for tests
and local markdown. No RAG, no vector store, no embedding model: they
use too much RAM. Do not add them back. Cards feed the mood block,
the participants digest, and the MCP knowledge server.

## Python modules

Keep Python modules under 150–200 lines by modularizing logic into
separate files. Prefer a new module over growing an existing one past
that budget. Do not pack statements onto one line, stuff huge strings,
disable the CI check, or add paths to the allowlist to “fix” length.
Tests may run longer than 200; still keep them reasonably compact.

Functions are default; modules are namespaces. Use a class when there
is mutable state / lifecycle, or a composition/DI boundary (broker,
repository, store, retriever, completer, engine, session).
Pydantic/dataclasses are data, not rich domain. Do not impose uniform
OOP. Do not invent DDD `domain/entities` or Unit of Work.
Do not unpack an existing context/DTO into kwargs for a sibling that
rebuilds it — pass the object. Do not add PLR0913 or invent a Parameter
Object to dodge argument count.
Details: `.agents/rules/python-clean-code.mdc`.

## Commands

Python 3.12, Poetry 2.1.1. CI: file-length check, then `ruff check`,
then `poetry run pytest tests/ -q`. Coverage fail-under 90%
(`vanessa`, `services`). Why those Ruff families, and the 200-line
budget: `docs/linting.md`.

```bash
bash scripts/check_python_file_length.sh
poetry run pytest
poetry run ruff check .
python scripts/prepare_env.py
docker compose --env-file .env.defaults --env-file .env.local up -d --build
```

Secrets go in `.env.local` (gitignored). Do not commit them.
Persona/YAML: `config/` (one tree). `behavior/` (compose/gate/knowledge/humor)
and `channels/` are the server pipeline; People cards hold identity bindings;
`presence/avatar.yaml` is host-only (`PRESENCE_AVATAR_PATH`). Env keys:
`.env.example`, `.env.defaults`.
