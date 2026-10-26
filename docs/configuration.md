# Configuration

YAML defaults live in one git tree, **`config/`**. Loaders try the
path as given (cwd), then the repo root. Empty slice env falls back
to `{CONFIG_ROOT}/…`.

| Slice | Who reads it | Env |
|------|----------------|-----|
| `behavior/` | agent, bot, worker | `BEHAVIOR_CONFIG_PATH` |
| `channels/` | agent (per turn); bot `speech` flag | `CHANNELS_CONFIG_PATH` |
| `presence/avatar.yaml` | host `services/presence` only | `PRESENCE_AVATAR_PATH` |

Presence on the game PC does not need `behavior/` or `channels/`.
Channel flags travel on the turn. Copy `avatar.yaml` next to VRChat
if OSC names differ, then point `PRESENCE_AVATAR_PATH` at that file.

**Env is not documented here.** Two files, nothing else:

- [`.env.defaults`](../.env.defaults) — every non-secret key and its
  default (the catalog).
- [`.env.example`](../.env.example) — overlay you copy: secrets, local vs
  prod flags, `COMPOSE_FILE` (Linux `:` vs Windows `;`), copy commands.

Empty overlay values wipe defaults; leave a key unset unless you mean
to override. Kubernetes secret names: [deploy/k8s/README.md](../deploy/k8s/README.md)
and `deploy/k8s/secrets.env.example`.

`config/behavior/` is grouped like the pipeline: `compose/`, `gate/`,
`knowledge/`, `humor/`. Persona, conversation, and bot copy stay
at the root of `behavior/` (one file each). Compose copy is four files:
system + layout + notes + generation (merged into `llm`).

## `config/behavior/` keys

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
| `rag.*` | Turn Planner prompts (`gate/planner.yaml`) |
| `memory.*` | Vault write / sweep cadence |
| `profanity.*` | Post-filter substitutions |
| `memes.*` / `stickers.*` | Humor and sticker catalogs |
| `portrait.*` | Portrait / image-related prompts |

`presence_penalty` / `frequency_penalty` are stored for portability;
DeepSeek API does not apply them today.

Files under `behavior/`: `persona.yaml`, `conversation.yaml`, `bot.yaml`,
`compose/system.yaml`, `compose/layout.yaml`, `compose/notes.yaml`,
`compose/generation.yaml`, `gate/decision.yaml`,
`gate/reaction_gate.yaml`, `gate/planner.yaml`,
`knowledge/memory.yaml`, `knowledge/metrics.yaml`, `knowledge/mood.yaml`,
`knowledge/portrait.yaml`, `humor/profanity.yaml`, `humor/memes.yaml`,
`humor/stickers.yaml`.

A section may merge several files (system + layout + notes + generation
→ `llm`; gate knobs + reaction prompt;
metrics extract + mood).

## `config/channels/`

Per-turn `ChannelProfile` loaded from `TurnRequest.channel` — not a
process-level orchestrator flag. One `config/behavior/` persona for every
channel; VRChat adds a short `prompt_addendum` here.

| Flag | telegram | vrchat |
|------|----------|--------|
| `stickers` / `photos` / `split_messages` | on | off |
| `scene` | off | on |
| `speech` | false | true |
| `listen_window` | current session window | on |
| `addressing` | telegram mention entity | addressed (no TG entity) |

HTML, typing, `/note`, and access stay in the adapter, not this profile.

## Identity

Telegram profiles supply incoming sender names. People cards store canonical
names, aliases and Telegram IDs. There is no separate nickname roster in YAML.

Each People card can declare `vrchat_names` alongside its existing `telegram_id`.
The People index derives VRChat bindings from those fields. This avoids a second
ID mapping in configuration. Names without an explicit binding stay name-keyed;
do not infer a binding from a similar Telegram nickname.

For the owner's card, set `vrchat_names: [Yevgeniy]`. Keep the existing
`telegram_id`; `REQUIRED_USER_TELEGRAM_ID` in env controls owner access.

## Presence (host)

`config/presence/avatar.yaml` is a template for OSC / gestures on the
game PC. Server images may contain it; the agent does not load it.
