# VanessaAI

A Telegram bot with long-term chat memory, RAG over message history, and
controlled group-chat behavior. A pet project showcasing production-minded AI
system design — not just an LLM wrapper, but a pipeline with gating, retrieval,
and observability.

## Why it exists

In a group chat, a bot should not reply to everything. VanessaAI addresses three
common problems:

- **Memory** — finds relevant fragments from months of chat history and weaves
  them into replies.
- **Discipline** — decides when to reply, when to stay silent, and when to reset
  context.
- **Character** — persona, tone, and rules are driven by config, not hardcoded
  logic.

## What the bot can do

### For chat participants

- Replies in **group chats** when addressed or when the topic genuinely involves
  a conversation with the bot.
- Remembers **chat history**: import from Telegram Desktop (`result.json`) plus
  semantic search over the archive.
- Supports **follow-ups** after its own reply (a listen window) and correctly
  **closes context** on phrases like “stop” / “enough”.
- Does not interrupt **side conversations between people** or gossip about the
  bot in the third person.
- Can **joke with recognizable in-chat memes** — only when the planner finds a
  good moment and RAG pulls real quotes.
- Formats replies for Telegram (markdown → HTML, code blocks).
- Knows participants by **nicknames** from config.

### For developers

- **REST API** (`POST /api/v1/chat`) — bot and API are separate, easy to test
  and scale.
- **Metrics** (`GET /api/v1/metrics`) — reply/ignore counters by reason.
- **Configurability** — persona, triggers, RAG thresholds, and decision engine
  settings via YAML and env without rewriting core logic.
- **162 automated tests** covering the decision engine, RAG, orchestrator,
  prefilter, and API.

## How a message is processed

```
Telegram → Bot → API
  → Ingress (persist, session, nicknames)
  → Gate (prefilter → Turn Planner → Decision Engine)
  → Retrieve (hybrid RAG, optional ReAct, humor RAG + reflexion)
  → Compose (Claude)
  → Post (formatting, profanity filter)
```

**Gate** is the main difference from “just ChatGPT in Telegram”:

| Layer | Role |
|-------|------|
| Prefilter | No LLM: noise, dismissal, off-topic remarks |
| Turn Planner | LLM: should reply, search query, humor, deep_search |
| Decision Engine | Rule chain: rate limit, addressing, listen window, relevance |

The planner suggests `should_reply`, but it is **not the single source of
truth** — the rule engine makes the final call using addressing, session state,
and a relevance threshold.

## Tech stack

| Category | Stack |
|----------|-------|
| Language | Python 3.12 |
| Bot | aiogram 3 |
| API | FastAPI, uvicorn |
| LLM | Anthropic Claude (composer + turn planner) |
| Embeddings | sentence-transformers (`all-MiniLM-L6-v2`), local |
| Vector DB | Qdrant (HNSW, quantization, on-disk) |
| SQL | PostgreSQL 16, SQLAlchemy 2 async, Alembic |
| Infra | Docker Compose (api, bot, postgres, qdrant) |
| Dependencies | Poetry |

## Engineering highlights

- **Hybrid RAG** — vector search plus Postgres full-text, merging anchors with
  context windows around matched messages.
- **ReAct retrieval** — when `deep_search=true`, the planner runs iterative
  search (up to N steps) if the first pass is not enough.
- **Two-track humor RAG** — separate meme search plus rule-based reflexion to
  avoid irrelevant quotes.
- **Pipeline stages** — orchestrator built as `Gate → Retrieve → Compose →
  Finalize`; dependencies wired through protocols (SOLID, testability).
- **ChatSessionState** — context trimming by idle timeout and listen window,
  not just message count.
- **Async indexing** — messages are written to the DB immediately; Qdrant
  embedding runs in the background with retries.
- **History import** — script to load Telegram exports into Postgres + Qdrant in
  batches.

## Quick start

### Requirements

- Docker and Docker Compose
- Keys: `TELEGRAM_BOT_TOKEN`, `ANTHROPIC_API_KEY`
- `REQUIRED_USER_TELEGRAM_ID` — owner user ID (the bot only works in chats
  where that user is present)
- `API_INTERNAL_TOKEN` — shared secret between bot and API

### Run

```bash
cp .env.example .env
# fill in .env

docker compose up -d --build
```

Services: API `http://localhost:8000`, Qdrant `6333`, Postgres `5432`.

### Import chat history (optional)

```bash
poetry install
poetry run python scripts/import_telegram_history.py --export path/to/result.json
```

### Tests

```bash
poetry run pytest
```

## Repository layout

```
app/
  bot/          Telegram handlers, formatting, API client
  api/          FastAPI, DI, routes
  decision/     Gate: prefilter, rules, intent, rate limit
  llm/          Claude, prompt builder, turn planner, humor
  rag/          Hybrid search, Qdrant, ReAct, query rewriter
  services/     Orchestrator, pipeline stages, metrics
  ingest/       Telegram export import
config/
  content.yaml  Persona, prompts, decision triggers
  nicknames.yaml
scripts/        import_telegram_history.py, backfill_users.py
tests/          162 tests
```

## Configuration (essentials)

Behavior tuning lives in **`config/content.yaml`** (persona, conversation window,
LLM sampling). Environment variables cover secrets and infrastructure.

| `content.yaml` key | Purpose |
|--------------------|---------|
| `conversation.session_window_size` | Recent messages in session context |
| `conversation.session_idle_seconds` | Session idle timeout |
| `conversation.post_reply_listen_count` | Follow-up window after bot reply |
| `llm.generation.composer` | temperature, top_p, max_tokens for replies |
| `llm.generation.planner` | Sampling params for turn planner |
| `persona.*` | System prompt: identity, voice, rules |

`presence_penalty` / `frequency_penalty` are stored for portability; Anthropic API
does not apply them today.

| Env variable | Purpose |
|--------------|---------|
| `DECISION_RELEVANCE_THRESHOLD` | Semantic relevance threshold |
| `ANTHROPIC_PLANNER_MODEL` | Separate planner model (optional) |
| `RAG_REACT_MAX_STEPS` | ReAct steps for deep search |
| `CONTENT_CONFIG_PATH` | Path to persona and prompts |

See `.env.example` for the full list.

## Limitations

- Tuned for **a single chat / single instance** — multi-tenancy is not a goal of
  this demo.
- Embeddings run locally on CPU — very large archives may need a GPU or an
  external embedding API.
- Quality of “when to stay silent” and “when to joke” depends on rule tuning and
  how much history is available in RAG.
