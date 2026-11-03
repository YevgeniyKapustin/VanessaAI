# Deploy announcements (production)

Vanessa posts one message in the work chat when the project has been
deployed to production: who ran it, what changed for the product, the
pipeline link.

```
GitLab (internal)  <- glab <-  bridge.py on the PC   (deploy/vanessa-bridge)
                                        ^  reverse SSH: 172.17.0.1:8643
                                        |
worker: Announcer (60 s tick per watch) -> LLM bullets -> outbound -> bot -> chat
```

## Why a bridge on the PC

The internal GitLab answers **403** to the Vanessa server's IP (nginx allow
list), while the owner's PC has an authenticated `glab`. The bridge is a
read-only HTTP view over GitLab on the PC, exposed through the same reverse
SSH tunnel as Hermes (`docs/hermes.md`). The server never talks to GitLab.

`deploy/vanessa-bridge/bridge.py`:

- `GET /health` → `{"ok": true}`, no auth;
- `GET /deploy/latest` (Bearer token) → the newest successful
  `deploy:production` job, who pressed `deploy:production:start`, the
  pipeline, and the commits between it and the previous production deploy
  (at most 40, plus the real total).

It only reads; no writes, and the token comes from a file
(`%LOCALAPPDATA%\vanessa-bridge\token`), never the command line.

## Install (PC)

```powershell
$token = -join ((48..57) + (97..102) | Get-Random -Count 64 | % {[char]$_})
& .\deploy\vanessa-bridge\run-bridge.ps1 -Install -Token $token
& .\deploy\hermes-pc\hermes-tunnel.ps1 -SshHost <server> -SshUser root -Install
```

The second command reinstalls the tunnel task; it now forwards
`172.17.0.1:8642` (Hermes) **and** `172.17.0.1:8643` (bridge). The server's
`~/.ssh/authorized_keys` line for the tunnel key must allow both:

```
restrict,port-forwarding,permitlisten="172.17.0.1:8642",permitlisten="172.17.0.1:8643",command="/usr/sbin/nologin" ssh-ed25519 AAAA... vanessa-hermes
```

Check the bridge by hand:

```powershell
python .\deploy\vanessa-bridge\bridge.py --check --glab <glab.exe> --token-file $env:LOCALAPPDATA\vanessa-bridge\token
```

## Server (.env.local)

```
DEPLOY_WATCH_ENABLED=true
DEPLOY_BRIDGE_URL=http://host.docker.internal:8643
DEPLOY_BRIDGE_TOKEN=<same token>
DEPLOY_CHAT_ID=<real chat id>
# Optional; kept out of git on purpose:
# DEPLOY_PROBE_URL=https://<stand-host>/api/auth/methods
# DEPLOY_ROLLOUT_URL=https://<grafana>/d/<dashboard>?var-tenant=$$__all
```

`DEPLOY_ROLLOUT_URL` needs `$$__all`: an `--env-file` value is interpolated
once, so a single `$` disappears. That is also why the code carries no
default dashboard URL.

Then rebuild the agent image and recreate the worker. Verify the chain:

```bash
curl -s http://172.17.0.1:8642/health          # Hermes
curl -s http://172.17.0.1:8643/health          # bridge
docker exec vanessa-worker-1 sh -c 'curl -s http://host.docker.internal:8643/health'
docker logs --since=5m vanessa-worker-1 | grep deploy_watch
```

## Behaviour

- One tick compares `job_id` with `vanessa:deploy_last_job` (Redis). The
  first tick (empty key, a Redis flush, a new chat) records the current
  deploy as the **baseline** and posts nothing.
- A deploy finished more than `DEPLOY_MAX_LATE_HOURS` ago (worker was down)
  is remembered, not posted.
- Before composing, the worker probes `DEPLOY_PROBE_URL` (the public prod
  origin) until it answers or `DEPLOY_READY_TIMEOUT_SECONDS` pass; the model
  is told only when the stand is still not answering.
- The first line («На прод [выкатили в 14:54](pipeline) — выкатывал …») and
  the rollout line («[Раскатка тенантов на проде](Grafana)») are built in
  code, so a reply quoting the message always carries the stand, the author,
  the time and both links — no bare URLs in the text. The model writes only
  1–3 product bullets from
  the commit list (`config/behavior/announce/deploy.yaml`); header lines,
  filler («остальное техническое») and links it invents are dropped. A
  release of several changes that matter to nobody → the post is just the
  header and the rollout line; a release of exactly one change is always
  named, even a technical one. Any
  LLM failure posts raw commit titles as bullets instead. `DEPLOY_ROLLOUT_URL`
  empty → the rollout line disappears; a missing pipeline URL keeps the
  words without the anchor.
- The bridge caches its answer for a minute and keeps serving the cached
  one while a refresh runs or fails, so a slow `glab` costs freshness, not
  the endpoint.
- The deploy author is resolved to the chat participant by full name against
  Vanessa's own `users` table (GitLab names are not Telegram handles) and
  tagged with a real `tg://user?id=…` mention; an unknown author stays as the
  GitLab label, and a one-word name has to match the username exactly.
- The `message_id` is `deploy-<job_id>` and the id is stored only after
  the publish, so a failed publish retries and a retry cannot double-post.
- Only production: `deploy:qa` / `deploy:stage` are ignored. Runtime
  registration (`RUNTIME_MODE: register`) does not roll tenant boxes; the
  message is about the platform deploy.

## Limits

- No PC, no announcements: the bridge lives there, like Hermes.
- The changelog is the commit list between the two deploys; when nothing in
  it matters for the product, the post is the header and the rollout line.
- The readiness probe is the public origin, not Argo: a 200 means the stand
  answers, not that every pod is on the new digest.

## Debugging

```bash
# what the bridge sees
curl -s -H "Authorization: Bearer $DEPLOY_BRIDGE_TOKEN" http://172.17.0.1:8643/deploy/latest | head -c 400
# re-announce the last deploy into the chat (real post!)
docker exec vanessa-worker-1 python -c "import asyncio,redis.asyncio as R; \
from vanessa.config import settings; \
asyncio.run(R.from_url(settings.broker_redis_url).set('vanessa:deploy_last_job','0'))"
```

Logs: the worker writes `announce_started` / `announce_baseline` /
`announce_published` / `announce_publish_failed` with `watch=deploy`;
the bot writes `outbound_sent source=deploy`. The bridge log is
`%LOCALAPPDATA%\vanessa-bridge\bridge.log`.

## Another announcement of the same shape

The deploy watch is one instance of `services/worker/announce/`: a source
returns the newest event as an `Announcement` (`key`, `when`, `url`, `actor`,
`items`), and one generic loop does dedupe, readiness, composition and
publishing. Everything deploy-specific is `deploys/adapter.py` (payload →
`Announcement`).

To add a watch whose payload already parses:

1. Drop a YAML in `config/behavior/announce/<id>.yaml` — copy
   `deploy.yaml`, change `id`, `state_key`, the env names, the timing
   and the prompts (`{when}`, `{url}`, `{started_by}`, `{links[name]}`,
   `{count}`, `{title}` are the only placeholders).
2. Add the env keys it names to `.env.example` / `.env.defaults` and set the
   values in `.env.local`. A watch whose `enabled_env` is false, or whose URL
   or chat id is empty, is skipped with a warning and costs nothing.
3. Rebuild the agent image, recreate the worker. `announce_started
   watch=<id>` in the logs means the loop is up.

The dedupe marker is `state_key` — it must be unique per watch, otherwise two
watches overwrite each other's baseline. The first tick always only records a
baseline; to post the current event, set the key to `0`.

A new payload shape adds one parser to `PARSERS` in
`services/worker/announce/registry.py` (`kind:` in the YAML selects it) — no
change to the loop, the composer or the watcher tests.
