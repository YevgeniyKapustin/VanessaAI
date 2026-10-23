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
- A run longer than `HERMES_MAX_WAIT_SECONDS` is stopped.
- Streaming is not used: its error chunks are not redacted upstream.
- A worker restart loses jobs in progress. The Hermes run itself continues.

## Server

1. In `/etc/ssh/sshd_config.d/70-vanessa-hermes.conf`, set
   `GatewayPorts clientspecified`. Run `sudo sshd -t`, then
   `sudo systemctl reload ssh` (the unit is `sshd` on some distros).
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

5. Test the tunnel, then install it as a logon task:

```
powershell -ExecutionPolicy Bypass -File deploy\hermes-pc\hermes-tunnel.ps1 -SshHost <server> -SshUser <user>
powershell -ExecutionPolicy Bypass -File deploy\hermes-pc\hermes-tunnel.ps1 -SshHost <server> -SshUser <user> -Install
```

## Hermes profile for Vanessa

Anyone in the chat can trigger a question. The topic rule in Vanessa's
prompt does not protect the PC: a user can write "ignore the rules".
Only the Hermes tool set can enforce it.

Native Windows Hermes runs tools on the PC itself. With
`terminal.backend: local` a terminal tool runs commands as the Windows
user, and `approvals.mode: off` runs them without a prompt. Never expose
that profile to Vanessa. Use a separate Hermes profile for Vanessa:

- Tools: only the MCP servers for Plane, GitLab, agent sessions, Grafana
  and k8s.
- Off: terminal, file, code execution and browser tools.
- Tokens: Plane and GitLab may read and create. Grafana and k8s are
  read-only.
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
