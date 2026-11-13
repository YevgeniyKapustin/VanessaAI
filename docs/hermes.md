# Hermes

Hermes Agent runs on the owner's PC. Vanessa runs on the server. Vanessa
asks Hermes about work (Plane, GitLab, agent sessions, Grafana, k8s) and
uses the answer in her reply. Hermes never talks to people directly.

## Flow

```
Telegram → bot → agent: gate (planner ask_hermes) → retrieve
  retrieve: GET /health
    offline → compose says "Hermes is offline" and answers alone
    online  → task hermes_ask → worker; compose says "I asked Hermes"
worker (background job): POST /v1/runs → poll GET /v1/runs/{id}
  → follow-up in Vanessa's persona → stream outbound → bot → Telegram
```

- One Hermes session per chat: `session_id = <channel>-<chat_id>`.
- A run that waits for approval or clarification is stopped (deny-and-stop).
- A run longer than `HERMES_MAX_WAIT_SECONDS` is stopped: the poller takes one
  last look first, so an answer that lands on the deadline is kept.
- A run alive past `HERMES_PROGRESS_SECONDS` (120) gets a "still looking" line
  in the chat, repeated every 120 s with the elapsed minutes
  (`progress_line` in the follow-up YAML; `{minutes}` is the number). Agents
  (`bot_peer`) never see it.
- A run that ends with nothing names why: the poller reports `blocked`,
  `timeout`, `interrupted`, `failed` or `empty`, and the follow-up task
  says it in one line from `failure_meanings` instead of shrugging.
- Streaming is not used: its error chunks are not redacted upstream.
- A worker restart loses jobs in progress. The Hermes run itself continues.
- One open job per question in a chat. A new ask that repeats an open job
  in the same chat (a rephrase or a correction) does not start a second
  run: the worker logs `hermes_ask_merged` and skips it. The open job's
  follow-up answers both messages. "Repeats" means at least 3 shared word
  stems and 60% of the shorter question's stems (`hermes/dedupe.py`).
- The follow-up prompt gets the real run time. Vanessa never claims a
  second check or a wait that did not happen.

## Generated HTML reports

When the user asks for an HTML report (a file or a page), Hermes returns
the page inline, once, in one block:

```
<vanessa_file name="short-slug.html">
<!doctype html>…</html>
</vanessa_file>
```

The worker (`services/worker/hermes/html_file.py`) takes the block out
before the follow-up LLM sees the answer. A short note takes its place.
The bot sends the page as a `.html` document.

Vanessa's follow-up is split into short messages, like her normal
replies: `[next]` lines from the model, or a sentence split
(`services/worker/hermes/blocks.py`). One `OutboundMessage` carries them
all: `text` is the first message (the file caption), `more_texts` holds
the rest. The bot posts them in order, with `BOT_MESSAGE_DELAY_SECONDS`
between them, and stops on the first failure. A first message longer
than 1024 characters goes before the file, and the file has no caption.

The worker sends the file only when all of these are true:

- It is one whole document: `<!doctype html>` or `<html>` up to `</html>`.
- It is static: no `<script>`, frames, `<object>`, `<embed>`, `<form>`,
  `<base>`, `on…=` handlers, `javascript:` or refresh redirects.
- It is one file per answer.
- Its size is at most `HERMES_FILE_MAX_BYTES` (default 262144).

The file name is made safe: letters, digits, `_` and `-`, at most 60
characters, then `.html`. A fenced ```` ```html ```` block or a bare page
also counts as a file. An HTML start with no end is a cut file: the rest
of the answer is dropped and no file is sent. HTML never goes to the
chat as text. If Telegram refuses the file, the text still goes out.

Hermes writes the markup only: the sheet classes listed in
`run_instructions` (`config/behavior/hermes/followup.yaml`). After the
checks, the worker adds the report stylesheet
`config/behavior/hermes/report_sheet.css` (the EngineerUI blueprint
sheet) right after `<head>`, so every report has the same look
(`services/worker/hermes/report_style.py`). The rules for the report
content (panel order, tones, language) live in the Hermes profile
memory on the PC, not in this repo.

## Server

1. Copy `deploy/hermes-pc/70-vanessa-hermes.conf` to
   `/etc/ssh/sshd_config.d/70-vanessa-hermes.conf`. It sets
   `GatewayPorts clientspecified`, `ClientAliveInterval 30` and
   `ClientAliveCountMax 3`. Run `sudo sshd -t`, then
   `sudo systemctl reload ssh` (the unit is `sshd` on some distros).
   Reconnect an existing tunnel after the reload to apply the keepalive.
2. If `ufw` runs, allow port 8642 only from the Docker subnets.
   Do not open it to the internet.
3. In `.env.local`, set:

```
HERMES_ENABLED=true
HERMES_URL=http://host.docker.internal:8642
HERMES_API_KEY=<same as API_SERVER_KEY on the PC>
```

4. Test from the server:

```
docker compose exec worker curl -s http://host.docker.internal:8642/health
```

5. `browser_exec` on the Hermes host needs the GUI libraries Chromium
   links against. Without them it exits 127 with
   `libatk-1.0.so.0: cannot open shared object file`, and the CDP
   supervisor then burns its five reconnects. Ubuntu 24.04 (`t64` names):

```
sudo apt-get install -y libatk1.0-0t64 libatk-bridge2.0-0t64 libcups2t64 \
  libxkbcommon0 libgbm1 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
  libpango-1.0-0 libcairo2 libasound2t64 libnss3 libnspr4 libx11-xcb1
```

   Check: `/root/.hermes/tools/chromium-*/chrome-linux64/chrome --headless=new
   --no-sandbox --disable-gpu --dump-dom https://example.com | head -c 100`.

6. `execute_code` is refused on the `api_server` surface unless Hermes
   `config.yaml` sets `approvals.unattended_mode: approve` (default
   `deny`). Nothing can approve a card in `/v1/runs`, so every step
   becomes its own `terminal` call: 23–26 round-trips per task, minutes
   of silence. `terminal` on that surface already runs unsandboxed under
   `approvals.mode: smart`, and a heredoc script is auto-approved there,
   so the flag removes round-trips, not a sandbox. Keep the smart policy
   (`approvals.smart_policy`) as it is: it still denies the five
   dangerous classes.

## Deploy announcements share the tunnel

The same tunnel carries a second forward, `172.17.0.1:8643`, for the
read-only GitLab bridge on the PC (`deploy/vanessa-bridge`). The worker
asks it for the newest successful production deploy and posts one message
in the work chat. Setup, env keys and behaviour:
`docs/deploy-watch.md`.

## PC (native Windows Hermes)

1. In `%LOCALAPPDATA%\hermes\.env`, set:

```
API_SERVER_ENABLED=true
API_SERVER_KEY=<long secret>
```

   Keep `API_SERVER_HOST` at the default `127.0.0.1`. Restart Hermes.
   Test: `curl http://127.0.0.1:8642/health`.
2. Make a key only for the tunnel:

```
ssh-keygen -t ed25519 -N "" -f %USERPROFILE%\.ssh\vanessa_hermes_ed25519
```

3. On the server, add the public key to `~/.ssh/authorized_keys` of the
   SSH user. The options let this key open only the one reverse forward.
   `restrict` does not block commands, so `command=` is required:

```
restrict,port-forwarding,permitlisten="172.17.0.1:8642",command="/usr/sbin/nologin" ssh-ed25519 AAAA... vanessa-hermes
```

   Test: `ssh -i <key> <user>@<server> id` must print
   `This account is currently not available.`

4. Connect once by hand to save the server host key (`StrictHostKeyChecking`
   is on in the script):

```
ssh -i %USERPROFILE%\.ssh\vanessa_hermes_ed25519 <user>@<server> exit
```

5. Test the tunnel, then install it as a scheduled task:

```
powershell -ExecutionPolicy Bypass -File deploy\hermes-pc\hermes-tunnel.ps1 -SshHost <server> -SshUser <user>
powershell -ExecutionPolicy Bypass -File deploy\hermes-pc\hermes-tunnel.ps1 -SshHost <server> -SshUser <user> -Install
```

`-Install` copies the script to `%LOCALAPPDATA%\hermes-tunnel`, so a
branch switch in the repo does not change the running tunnel. Run
`-Install` again after you change the script. It replaces the running
tunnel at once.

The tunnel heals itself on two levels:

- The script runs `ssh` in a loop. The retry waits 5 s, then doubles up
  to 60 s. A connection that lived 120 s or more resets the wait.
  `ServerAliveInterval=15` with `ServerAliveCountMax=3` drops a dead
  link in about 45 s. `ExitOnForwardFailure=yes` makes `ssh` exit when
  the server does not open the forward, so the loop tries again.
- The task `VanessaHermesTunnel` starts the script at logon, every
  5 minutes, on resume from sleep, and on network connect. "Do not
  start a new instance" keeps one copy. Battery power does not stop it.

The task runs PowerShell with `-WindowStyle Hidden`, so the tunnel has
no visible console. Reinstalling the task stops the old loop and its
SSH child before it starts the new loop.

Logs: `%LOCALAPPDATA%\hermes-tunnel\tunnel.log` (one line per `ssh`
exit) and `ssh.log` (the `ssh` client errors).

If the PC loses the network, the server can keep the old session and
its listen port until its own TCP timeout. With sshd defaults
(`ClientAliveInterval 0`, kernel keepalive 7200 s) that is about 2 hours.
Until then the new `ssh` fails the forward and the loop retries. The
server config above drops a lost connection after about 90 seconds.
The loop can then bind the port again.

## Hermes profile for Vanessa

Anyone in the chat can trigger a question. The topic rule in Vanessa's
prompt does not protect the PC: a user can write "ignore the rules".
Only the Hermes tool set can enforce it.

Native Windows Hermes runs tools on the PC itself. With
`terminal.backend: local` a terminal tool runs commands as the Windows
user, and `approvals.mode: off` runs them without a prompt. Never expose
that profile to Vanessa. Use a separate Hermes profile for Vanessa:

- Tools: only the MCP servers for Plane, GitLab, agent sessions, Grafana,
  k8s and the work project's Figma designs.
- Off: terminal, file, code execution and browser tools.
- Tokens: Plane and GitLab may read and create. Grafana, k8s and Figma
  are read-only.
- Approvals: deny by default. The worker also stops any run that waits
  for approval.

Tested with Hermes 0.22.2 on Windows:

```
hermes profile create vanessa --clone --no-alias
```

Then, in `%LOCALAPPDATA%\hermes\profiles\vanessa\config.yaml`:

```yaml
gateway:
  standalone: true          # own process, own API server on 127.0.0.1:8642
agent:
  disabled_toolsets: [terminal, file, code_execution, browser, computer_use,
                      delegation, cronjob, skills, connections, kanban]
platform_toolsets:
  api_server: [plane, grafana, kubernetes]   # MCP server names only
approvals:
  mode: "manual"
  unattended_mode: "deny"
mcp_servers:
  plane: {command: node.exe, args: [...], tools: {exclude: [plane_update_issue]}}
  grafana: {command: powershell.exe, args: [..., mcp-grafana.ps1]}  # --disable-write
  kubernetes: {command: kubernetes-mcp-server.cmd, args: ["--read-only"]}
```

Put the `API_SERVER_*` keys from the PC section into the profile's `.env`.
Start the profile with `hermes -p vanessa gateway install --start-on-login`.
Test it: the run must list only `mcp__*` tools and must refuse `whoami`.

If the login item logs `no dependency environment is committed`, its
`gateway-service\Hermes_Gateway_vanessa.{vbs,cmd}` must start
`installs\<id>\environments\<id>\venv\Scripts\hermes.exe`, not the base
`tools\python-*\python.exe`.

With a multiplexed host gateway instead of `standalone`, `HERMES_URL`
ends with `/p/vanessa`.

## Gateway recovery on Windows

The gateway's internal liveness watchdog can exit with code 75. The
Startup VBS runs only at login and does not recover this exit. Install
the separate process check after the gateway and tunnel are installed:

```powershell
& ./deploy/hermes-pc/hermes-gateway-watchdog.ps1 -Install
```

`VanessaHermesGatewayWatchdog` runs a hidden supervisor at login. The
supervisor checks the `vanessa` profile every 15 seconds. A repeated
one-minute task trigger restores the supervisor if it stops. The check
compares the profile path and process creation time
before trusting `gateway.pid`. If the process is absent, it starts the
existing gateway VBS. It does not change profile secrets or other
profiles. PowerShell runs without a visible console; battery power
does not stop it. Files live beside the tunnel in
`%LOCALAPPDATA%\hermes-tunnel`; its log is `watchdog.log`.

After installation, verify recovery by stopping only the process
identified in the profile's `gateway.pid`. Wait for the next scheduled
check. Verify `/health` locally and from the server's worker container.

## Find work designs in Figma

The local MCP has five read-only tools: search files in configured work
folders, list team folders, search screen names or UI text, list file
pages, and read a selected node. The default file is the main design file
configured in `FIGMA_DEFAULT_FILE`. The supplied link points to `12188:511735`.
Search covers bounded depths, not the whole design tree. Its response
includes the scope and `incomplete: true`; an empty result does not
prove that a design is absent. Inspect page outlines and search within
the relevant page when needed.

Use a separate Python environment: Hermes's bundled MCP client does not
necessarily include the FastMCP server package. Install from this repo:

```powershell
$figmaDir = "$env:LOCALAPPDATA\vanessa-figma-mcp"
uv venv --python 3.12 "$figmaDir\.venv"
uv pip install --python "$figmaDir\.venv\Scripts\python.exe" -r deploy/hermes-pc/requirements-figma.txt
& "$figmaDir\.venv\Scripts\python.exe" deploy/hermes-pc/install_figma.py --profile-home "$env:LOCALAPPDATA\hermes\profiles\vanessa" --install-dir $figmaDir
```

The installer copies the four MCP modules outside the checkout, enables
`figma` for `platform_toolsets.api_server`, and adds the lookup rules to
profile memory. It backs up changed config and memory files. Existing
tool restrictions remain in place.

In the profile `.env`, set `FIGMA_ACCESS_TOKEN` (`FIGMA_TOKEN` also works).
The token needs `file_content:read`. To search other files, configure
`FIGMA_TEAM_IDS` or `FIGMA_PROJECT_IDS` with comma-separated team/folder
IDs and add `folders:read`. Additional known file keys can be listed in
`FIGMA_FILE_KEYS`. Keep tokens out of the repo and logs. See the
[Figma token guide](https://developers.figma.com/docs/rest-api/personal-access-tokens/).

Restart the profile after changing these settings. Without folder IDs,
Hermes searches the main file and related links in Plane/GitLab. Reading
another file requires adding its key or discovering it through a
configured work folder. Missing access produces an explicit error.

The server also needs the updated `gate/planner.yaml` and
`hermes/followup.yaml` from `config/behavior`. Production images contain
these files; update both agent and worker and restart those services.
