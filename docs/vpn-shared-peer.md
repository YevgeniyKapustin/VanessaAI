# The dev-VPN peer is shared between the server and the owner's laptop

The server reaches two private things through WireGuard `wg0`: the EKS API
(`10.30.0.0/16`) and the internal GitLab (one `/32`).
Its config is a copy of the owner's own peer — same key, same inner address
`10.8.0.12` — because the VPN host (wg-easy on an EC2 in Frankfurt) accepts new
peers only from inside, and nobody had panel access when this was wired.

```
laptop (10.8.0.12, full tunnel)  ─┐
                                  ├── same key ──> wg-easy <vpn-host>:51820
server (10.8.0.12, split tunnel) ─┘
```

## What that means, plainly

WireGuard keeps **one endpoint per peer**: the host that sent the last
authenticated packet owns the session. Two hosts with the same key trade it
back and forth:

- the server sends `PersistentKeepalive = 25`, so while the laptop is idle the
  server keeps the session;
- as soon as the laptop sends anything, it takes the session back, and the
  server's in-flight requests die (`dial tcp …: i/o timeout`);
- the server re-takes it within 25 s.

So both sides see short hiccups. Nothing is broken permanently, and nothing is
lost — but a long GitLab call can fail mid-flight.

## What already absorbs it

| Layer | What it does |
|---|---|
| `vanessa-bridge.service` | retries each `glab` call 3× (1.5 s apart) and serves the last good answer while a refresh runs or fails |
| worker `announce` | polls every 60 s, remembers a deploy for `DEPLOY_MAX_LATE_HOURS` (12), never double-posts (`state_key`) |
| `vanessa-vpn-check.timer` | every 2 min: handshake age, GitLab reachability (3 tries), bridge `/health`; restarts the bridge if it is down; one line per run into `/var/log/vanessa-vpn.log` |
| routing | only `10.30.0.0/16`, `10.8.0.0/24` and the GitLab `/32` go through the tunnel — the default route stays on eth0 |

A deploy announcement may therefore arrive a few minutes late. It is not lost.

## Diagnose it in one command

```bash
ssh vanessa 'systemctl is-active wg-quick@wg0 vanessa-bridge; \
  wg show wg0 latest-handshakes; tail -3 /var/log/vanessa-vpn.log'
```

Healthy looks like `wg_age` under ~180 s, `gitlab=200`/`401` and `bridge=200`.
`gitlab=000` with `handshake_stale` in the same line is the peer fight, not a
credential or firewall problem. `bridge_restart` appears when the timer had to
kick the bridge.

Log lines worth grepping:

- `gitlab_call_retry attempt=…` — a retry the bridge absorbed (fine);
- `gitlab_error … i/o timeout` in `/var/log/vanessa-bridge.log` — a refresh
  that failed after retries (cache kept);
- `announce_source_unreachable` in the worker — the bridge was down entirely.

## Escalation: give the server its own peer

The shared key is the only real defect. Either of these removes it:

1. **Own peer in wg-easy** (preferred). Create a client `vanessa-server` in the
   panel at `10.8.0.1:51821` (reachable only from inside the tunnel) or in AWS
   SSM on the EC2, then on the server: put its `PrivateKey`/`Address`/peer block
   into `/etc/wireguard/wg0.conf`, keep `AllowedIPs` as it is today
   (`10.30.0.0/16, 10.8.0.0/24, <gitlab-ip>/32`), `PersistentKeepalive = 25`,
   `systemctl restart wg-quick@wg0`, then `kubectl get nodes` and
   `glab api projects/29` as the smoke test. A spare keypair waits at
   `/etc/wireguard/vanessa-server.key` (public half already in the ticket/chat).
2. **Allow-list the server IP in GitLab** (the server's public IP): then the bridge
   needs no VPN at all for GitLab — remove the `/32` from `AllowedIPs`.

`kubectl` keeps needing the tunnel either way: the EKS endpoint is private-only,
and the read-only kubeconfig has no other path in.

## On the laptop

Nothing to configure. Two habits cover it:

- while you *need* the VPN, the server's GitLab lookups may fail until you go
  quiet — deploys will be announced late, not skipped;
- if a deploy announcement seems stuck, `curl -s http://172.17.0.1:8643/health`
  from the server is the one fact that separates "bridge down" from "link
  flapping".
