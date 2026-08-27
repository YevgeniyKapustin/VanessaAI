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
- Keeps an internal **knowledge vault** — dossiers on people, a glossary of
  in-chat memes, recommendations and weekly logs — and consults it to answer
  “что было про Макса и утку?” and to joke with the chat's own lore.

### For developers

- **REST API** (`POST /api/v1/chat`) — bot and API are separate, easy to test
  and scale.
- **Metrics** (`GET /api/v1/metrics`) — reply/ignore counters by reason.
- **Configurability** — persona, triggers, RAG thresholds, and decision engine
  settings via YAML and env without rewriting core logic.
- **400 automated tests** covering the decision engine, RAG, orchestrator,
  prefilter, API, and the knowledge vault.

## Knowledge vault

Beyond raw message history, Vanessa keeps her own structured memory in a
repo-local `knowledge/` folder. No human browses it — the format is
machine-only, a deterministic contract for the LLM.

| Folder | Contents |
|--------|----------|
| `People/` | One stable card per participant: life context, mood, triggers, quote book |
| `Lore/glossary/` | In-chat memes and neologisms (stable per-meme files) |
| `Lore/events/` | Chronicles of events and weird arguments |
| `Culture/` | Movie / game / music recommendations |
| `Logs/` | Daily and weekly chat logs |
| `Metrics/` | Per-participant mood & relationship time series (machine YAML) |
| `inbox/` | Manual `/note` entries |

Every folder keeps a machine `_index.yaml` (alias → file maps), so retrieval
resolves nicknames to notes in O(1) without scanning the vault. Notes carry
typed YAML frontmatter and fixed section headings, so the LLM writes and updates
them deterministically; git gives auditability + rollback.

**Write** happens two ways:

- **Post-reply**: at the end of each reply the bot runs a small LLM decision
  over recent messages, and anything worth keeping is merged into the vault
  (idempotent — no duplicate quotes or facts).
- **Sweep every N messages**: because the bot ignores most messages, a
  background worker chunks the accumulated chat into context-window-sized
  windows and extracts what it missed — including weekly digests.

**Read** is semantic-first: the vault notes are already semantic summaries (raw
chat messages embed poorly), so they are embedded into a dedicated Qdrant
`knowledge` collection and retrieved by embedding similarity to the composed
query, merged with exact alias matches. The turn planner decides which archive to
consult (`people` / `lore` / `culture` / `logs`); the humor module always
consults the `lore` part. The matched notes become the **primary RAG context** —
raw message history is only a fallback when the archive has nothing relevant.
The vault is re-embedded on every write, so Vanessa's regularly-updated
participant summaries stay fresh in the vectors (`scripts/reindex_knowledge_vectors.py`
rebuilds the whole collection).

### Mood & relationship metrics

Each participant gets a typed, machine-readable profile combining qualitative
and quantitative signals:

| Group | Metrics | Source |
|-------|---------|--------|
| Sentiment & valence | `valence`, `volatility`, `sarcasm_index` | LLM |
| Engagement & dynamics | `constructiveness`, `toxicity`, `support_index` | LLM |
| Relation to Vanessa | `trust_score`, `distance`, `sympathy` | LLM |
| Behavioral meta | `presence_stability`, `reactivity_median_s`, `peak_hour`, `active_days`, `message_count`, `reply_rate_to_bot` | DB |

- **Storage** — the current snapshot lives in the person card frontmatter
  (`People/*.md` → `metrics:`), and a per-date time series is appended to
  `Metrics/<person>.yaml` for volatility, trends and digests.
- **Computation** — behavioral metrics are computed from the message DB
  (`DeterministicMetricsCalculator`); semantic metrics come from an LLM
  (`MetricsPlanner`). The full pass runs in the background sweep; a throttled
  deterministic-only pass runs per replied turn.
- **Behavioral feedback** — the `SenderMetricsRule` in the decision engine can
  ignore chronically toxic, low-trust senders (with hard guards: never the
  owner, never direct/triggered/expected replies), and the composer gets a
  compact “mood and relationship” block to tune the tone — within the fixed
  persona rules.

## How a message is processed

```
Telegram → Bot → API
  → Ingress (persist, session, nicknames)
  → Gate (prefilter → Turn Planner → Decision Engine)
  → Retrieve (semantic vault RAG first, raw-message RAG fallback, optional ReAct, humor RAG + reflexion)
  → Compose (DeepSeek)
  → Critique (optional humor critic: approve or regenerate with feedback)
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
| LLM | DeepSeek (default) or Claude, via provider adapter |
| Embeddings | sentence-transformers (`all-MiniLM-L6-v2`), local |
| Vector DB | Qdrant (HNSW, quantization, on-disk) |
| SQL | PostgreSQL 16, SQLAlchemy 2 async, Alembic |
| Infra | Docker Compose (api, bot, postgres, qdrant) |
| Dependencies | Poetry |

## Engineering highlights

- **Knowledge vault** — a machine-only structured memory (People/Lore/Culture/
  Logs) with index-based retrieval, post-reply extraction, and a periodic sweep
  over messages the bot never replied to; the semantic notes are embedded into a
  Qdrant `knowledge` collection and re-embedded on every write.
- **Semantic-first RAG** — the query is matched by meaning against the vault's
  semantic notes (People/Lore/Culture/Logs); raw-message vector + Postgres
  full-text search is only the fallback when the archive has nothing relevant.
- **Participant-aware query planning** — the planner prompt receives compact
  per-participant summaries (mood + recent facts from the People dossiers) so
  the composed embedding query references the right aliases and topics.
- **ReAct retrieval** — when `deep_search=true`, the planner runs iterative
  search (up to N steps) if the first pass is not enough.
- **Two-track humor RAG** — separate meme search plus rule-based reflexion to
  avoid irrelevant quotes.
- **Generator–Critic humor loop** — optional critic agent reviews humor turns
  (strict JSON verdict), rejects flat replies, and regenerates with a fix
  instruction; bounded rounds and fail-open, so a reply is never blocked.
- **Pipeline stages** — orchestrator built as `Gate → Retrieve → Compose →
  Critique → Finalize`; dependencies wired through protocols (SOLID,
  testability).
- **ChatSessionState** — context trimming by idle timeout and listen window,
  not just message count.
- **Async indexing** — messages are written to the DB immediately; Qdrant
  embedding runs in the background with retries.
- **History import** — script to load Telegram exports into Postgres + Qdrant in
  batches.

## Quick start

### Requirements

- Docker and Docker Compose
- Keys: `TELEGRAM_BOT_TOKEN`, `DEEPSEEK_API_KEY` (or `ANTHROPIC_API_KEY` if
  `LLM_PROVIDER=claude`)
- `REQUIRED_USER_TELEGRAM_ID` — owner user ID (the bot only works in chats
  where that user is present)
- `ALLOWED_CHAT_TELEGRAM_ID` — optional chat ID; when set (> 0) the bot works
  only in that single chat (0 = no chat restriction)
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
  llm/          Providers (DeepSeek/Claude), prompts, planner, humor
  knowledge/    Structured memory vault: format, indexes, retriever, writer, sweep
  rag/          Hybrid search, Qdrant, ReAct, query rewriter
  services/     Orchestrator, pipeline stages, metrics
  ingest/       Telegram export import
config/
  content/      Per-section YAML: bot, persona, conversation, llm, decision,
                memory, metrics, rag, profanity (SRP)
  nicknames.yaml
knowledge/      Vanessa's memory vault (runtime data)
scripts/        import_telegram_history.py, backfill_users.py, reindex_knowledge_vectors.py
tests/          400 tests
```

## Configuration (essentials)

Behavior tuning lives in **`config/content/`** — one YAML file per concern
(persona, conversation window, LLM sampling). Environment variables cover
secrets and infrastructure.

| `content/` key | Purpose |
|--------------------|---------|
| `conversation.session_window_size` | Recent messages in session context |
| `conversation.session_idle_seconds` | Session idle timeout |
| `conversation.post_reply_listen_count` | Follow-up window after bot reply |
| `llm.generation.composer` | temperature, top_p, max_tokens for replies |
| `llm.generation.planner` | Sampling params for turn planner |
| `llm.generation.critic` | Sampling params for the humor critic |
| `llm.critic` | Critic system/user prompts, fix-instruction header |
| `persona.*` | System prompt: identity, voice, rules |
| `metrics.extraction_prompt` | Semantic metric scoring prompt for the sweep |
| `metrics.feedback_header` / `feedback_line` | Tone block injected into the compose prompt |

`presence_penalty` / `frequency_penalty` are stored for portability; DeepSeek API
does not apply them today.

| Env variable | Purpose |
|--------------|---------|
| `LLM_PROVIDER` | LLM backend: `deepseek` (default) or `claude` |
| `DEEPSEEK_PLANNER_MODEL` | Separate DeepSeek planner model (optional) |
| `ANTHROPIC_PLANNER_MODEL` | Separate Claude planner model (optional) |
| `CRITIC_ENABLED` | Enable the humor critic loop (humor turns only) |
| `CRITIC_MAX_ITERATIONS` | Max regeneration rounds after a REJECTED draft |
| `CRITIC_MODEL` | Optional separate model for the critic |
| `CRITIC_APPLY_TO_ALL` | Critique all replies instead of humor-only |
| `DECISION_RELEVANCE_THRESHOLD` | Semantic relevance threshold |
| `DECISION_METRICS_RULE_ENABLED` | Enable the metrics-based toxicity/trust gate |
| `DECISION_TOXICITY_IGNORE_THRESHOLD` | Toxicity at/above which a low-trust sender may be ignored |
| `DECISION_TRUST_IGNORE_THRESHOLD` | Trust at/below which a toxic sender may be ignored |
| `KNOWLEDGE_METRICS_ENABLED` | Enable per-participant mood & relationship metrics |
| `QDRANT_KNOWLEDGE_COLLECTION` | Qdrant collection for the semantic vault notes |
| `KNOWLEDGE_VECTOR_TOP_K` | Top-K for the semantic vault vector search |
| `KNOWLEDGE_VECTOR_MIN_SCORE` | Min cosine score for a vault note to be used |
| `KNOWLEDGE_PARTICIPANT_MAX_PEOPLE` | Max people in the planner's participants digest |
| `KNOWLEDGE_PARTICIPANT_MAX_FACTS` | Max recent facts per person in the digest |
| `RAG_REACT_MAX_STEPS` | ReAct steps for deep search |
| `EMBEDDING_THREADS` | Dedicated thread pool size for local embedding inference (default 1) |
| `BACKGROUND_QUEUE_SIZE` | Bounded queue size for post-reply background work (memory/metrics/indexing) |
| `BACKGROUND_WORKERS` | Worker tasks consuming the background queue |
| `CONTENT_CONFIG_PATH` | Path to content dir (one YAML per section) or a single file |

See `.env.example` for the full list.

## Limitations

- Tuned for **a single chat / single instance** — multi-tenancy is not a goal of
  this demo.
- Embeddings run locally on CPU — very large archives may need a GPU or an
  external embedding API.
- Quality of “when to stay silent” and “when to joke” depends on rule tuning and
  how much history is available in RAG.
