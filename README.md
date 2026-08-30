# VanessaAI

<p>
  <img src="Vanessa.png" align="right" width="300" alt="Vanessa"
       style="margin-left: 20px; margin-bottom: 10px;" />

Telegram bot for a group chat that already has its own jokes and
history. Vanessa is sharp, short, a bit mean when the question is
dumb. She does not pretend she has a body or a weekend.

</p>

Most messages in a group are people talking to each other. She stays
out of those. If nobody addressed her and the topic isn't hers, she
indexes the message and shuts up. That's the whole point of the
project: knowing when not to speak.

She also remembers people. There are cards (who is who, lore, memes, old fights).
Search hits those first. Raw chat history only if the cards are empty.

<br clear="right"/>

## How a message gets handled

```
telegram → bot → api → ingress → gate → retrieve → compose → post
```

Telegram hits the bot. Photos in an album count as one turn. The
person and the text go into Postgres. Then a gate: cheap filters
kill noise without calling a model. A planner may say “reply”.
Rules can still veto that (rate limit, nobody asked her, off-topic).

If she does reply, she pulls cards / history / maybe the web / maybe
a meme, writes one answer, and sends it. Empty answers and repeats
are treated as silence. A sticker or an old photo can ride along
without a second model call. Memory updates, mood scores, image
captions run after the message is already in the chat.

Longer version: [architecture](docs/architecture.md).

## Stack, if you care

Python 3.12, aiogram, FastAPI, Postgres, Qdrant, Redis. DeepSeek by
default, Claude if you switch it. Embeddings on local CPU on purpose —
I didn't want another paid API. Bot, API, and a worker are separate
processes. Tests in `tests/`, CI fails under 90% coverage. Metrics and
Grafana exist and stay off until you turn them on
([observability](docs/observability.md)).

There's a k8s lab setup. I am not pretending this runs at scale.

## Run

Docker Compose. Copy [`.env.example`](.env.example) to `.env.local`,
put secrets there, don't commit it.

```bash
python scripts/prepare_env.py
docker compose --env-file .env.defaults --env-file .env.local up -d --build
```

API listens on `http://localhost:8000`. Prod / k8s / importing a
Telegram export: [deployment](docs/deployment.md). Persona and rules:
[configuration](docs/configuration.md).

## What's weak

CPU embeddings choke on a huge archive. The chat dialect is weird enough that fine-tuning would help. I didn't do it: even a small local 7B would cost more than the API. Not worth it for one group.

Example of the process (fictitious names)
<details>
<summary>Example turn (fake names)</summary>

```
User: Vanessa, what was that about Maxim and that duck?

Gate: reply, humor, look up Maxim + duck lore
Retrieve: Maxim's card, glossary quote
Bot: it's a concept, not a duck. Maxim already suffered this argument.
```

</details>
