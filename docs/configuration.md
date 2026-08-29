# Configuration

Behavior lives in **`config/content/`** — one YAML file per concern.

**Env is not documented here.** Two files, nothing else:

- [`.env.defaults`](../.env.defaults) — every non-secret key and its
  default (the catalog).
- [`.env.example`](../.env.example) — overlay you copy: secrets, local vs
  prod flags, `COMPOSE_FILE` (Linux `:` vs Windows `;`), copy commands.

Empty overlay values wipe defaults; leave a key unset unless you mean
to override. Kubernetes secret names: [deploy/k8s/README.md](../deploy/k8s/README.md)
and `deploy/k8s/secrets.env.example`.

## `config/content/` keys

| Key | Purpose |
|------|---------|
| `conversation.session_window_size` | Recent messages in session context |
| `conversation.session_idle_seconds` | Session idle timeout |
| `conversation.post_reply_listen_count` | Follow-up window after bot reply |
| `llm.generation.composer` | temperature, top_p, max_tokens for replies |
| `llm.generation.planner` | Sampling for the turn planner |
| `persona.*` | System prompt: identity, voice, rules |
| `metrics.extraction_prompt` | Semantic metric scoring for the sweep |
| `metrics.feedback_header` / `feedback_line` | Tone block in the compose prompt |
| `bot.photo_placeholder` | Copy when vision caption is missing |
| `decision.*` | Gate / rule-engine thresholds |
| `rag.*` | Retrieval sizes and score cutoffs |
| `memory.*` | Vault write / sweep cadence |
| `profanity.*` | Post-filter substitutions |
| `memes.*` / `stickers.*` | Humor and sticker catalogs |
| `portrait.*` | Portrait / image-related prompts |

`presence_penalty` / `frequency_penalty` are stored for portability;
DeepSeek API does not apply them today.

Files: `bot.yaml`, `persona.yaml`, `conversation.yaml`, `llm.yaml`,
`decision.yaml`, `memory.yaml`, `metrics.yaml`, `rag.yaml`,
`profanity.yaml`, `memes.yaml`, `stickers.yaml`, `portrait.yaml`.

Nicknames: `config/nicknames.yaml`.
