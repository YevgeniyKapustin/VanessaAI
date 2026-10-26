# Linting

Ruff is the project linter. Config lives in [`ruff.toml`](../ruff.toml).
The Ruff *package* version is still pinned in [`pyproject.toml`](../pyproject.toml)
(Poetry). Ruff in CI is `ruff check` only — no `ruff format`. File
length is a separate bash step (below).

This is not a generic flake8 catalog. The select/ignore list exists so
**coding agents and humans** do not reintroduce the bugs this stack
actually hits: naive datetimes, swallowed API errors, `print()` in
providers, blocking calls in `async def`, f-string logs that break Loki.

Style for *how* to flatten a function after Ruff complains: 
[`.agents/rules/python-clean-code.mdc`](../.agents/rules/python-clean-code.mdc).

```bash
poetry run ruff check .
poetry run ruff check --fix <paths>
bash scripts/check_python_file_length.sh
```

Do not pass `--unsafe-fixes` unless you asked for it. Do not run
`ruff format` unless you asked for it.

## Python file length

Keep Python modules under **150–200 lines** by splitting
responsibilities into separate files. Prefer a new module over
growing an existing one past that budget. This is an architectural
instruction for agents, not a linter to game: do not pack statements
onto one line, stuff huge strings, disable the check, or extend the
allowlist.

CI runs `bash scripts/check_python_file_length.sh` in the lint job
(step **Check Python file length**) before Ruff. The hard 200-line
gate covers application code in `vanessa/`, `services/`, and
`scripts/` only. Tests are out of that gate; still keep them
reasonably compact.

A temporary allowlist of modules that already exceed 200 lives in
[`scripts/python_file_length_allowlist.txt`](../scripts/python_file_length_allowlist.txt).
Those files must not grow past the recorded newline count. Do not add
new paths — split the module instead. When a listed file drops to 200
or below (or is deleted), remove it from the list.

## Why these families

Python 3.12 (`target-version = "py312"`), line length 88. McCabe
`max-complexity = 4` is intentional: gate and orchestrator flatten with
guard clauses, they do not grow a Strategy tree to chase a number.

### Bugs this bot actually gets

| Family | Why it is on |
|--------|----------------|
| **DTZ** | Logs, outbox, session trim, vault dates, Telegram `date`, Postgres. `datetime.now()` is naive vs aware. Agents love it. |
| **BLE** | LLM / network clients. `except Exception: pass` hides API and Redis failures. `except Exception` + `logger.exception` is allowed; bare swallow is not. |
| **ASYNC** | aiogram, async SQLAlchemy, Redis Streams, AsyncOpenAI. Agents drop `requests.get` / `time.sleep` into `async def`. |
| **T10 / T20** | Forgotten `breakpoint()` in the gate; `print(response)` in a provider. CLI scripts may print (see per-file). |
| **S** | SQL, subprocess, XML. Secrets live in `.env.local`, not in code. Noisy Bandit codes are ignored (below), not the whole family. |
| **LOG / G** | Grafana / Loki. `logger.info(f"turn={turn}")` breaks lazy `%s` formatting and log-pattern extractors. |
| **B / F** | Mutable defaults, unused names, dead imports after an agent tried `vanessa.pipeline` and backed out. |
| **ERA** | Agents comment out “old prompt” / “didn’t work”. |

### Shape of the code

| Family | Why it is on |
|--------|----------------|
| **RET / FBT / PTH / UP / C90** | Same contract as the clean-code rule: guard clauses, keyword-only flags, pathlib, 3.12 idioms, complexity under 4. |
| **I / TID** | First-party groups `vanessa` and `services`. Relative imports are banned (`ban-relative-imports = "all"`). Layer bans (`core` must not import `pipeline`) are **pytest**, not Ruff — see below. |
| **ARG** | Unused args in domain code are a smell. Handlers and tests are carved out per-file. |
| **PT** | Coverage fail-under 90%. Agents otherwise write fixtures and `pytest.raises` without a matcher. |
| **A / C4 / ISC / PIE / Q / SIM / N / ICN / RUF** | Cheap consistency. Cyrillic mixed-script (`RUF001–003`) is ignored: Russian gates and nicknames are domain, not typos. |

**FAST is not selected.** Agent HTTP is health/metrics only. Enabling
FastAPI lints would nudge agents toward `/chat` routes, which this repo
forbids.

## Intentionally ignored

Global ignore is for **false positives that would drown every new file**,
not for rules that are “annoying in one place”.

| Code | Why ignored |
|------|-------------|
| `E501` | Length is `line-length = 88`, not the linter. |
| `PLR0913` / `PLR0917` | Pipeline DI, LLM `generate(...)`, protocols, tracing. Counting arguments would push `**kwargs`. Keyword-only (`FBT`) is the real constraint. Do not "fix" this by enabling the lint: pass an existing context/DTO instead of unpacking it, and do not invent a Parameter Object. |
| `RUF001` / `002` / `003` | Cyrillic next to Latin in gates, stickers, humor, tests. |
| `ASYNC109` | `timeout=` on Redis RPC / MCP is the contract, not a hand-rolled `asyncio.timeout`. |
| `S101` | `assert ctx.result is not None` after a gate branch is an invariant, not a leftover debug assert. |
| `S104` | Bind `0.0.0.0` for `/health` `/metrics` in k8s. |
| `S105` / `S106` | Names like `token` / `password` in LLM metrics and pydantic settings. Real secrets are env files. |
| `S311` | `random` for stickers and Langfuse sampling, not cryptography. |

Do **not** add `BLE001`, `FBT`, `C90`, `F401`, `DTZ`, or `G` to global
ignore. Those are the mistakes this stack keeps making.

## Per-file ignores

| Path | Codes | Why |
|------|--------|-----|
| `tests/**/*` | `ARG001`, `S108`, `S310`, `S314` | Fixtures; `/tmp` in manifest tests; `urlopen` to local `/metrics`; ElementTree on sticker/prompt XML. |
| `scripts/**/*` | `T201`, `S603`, `ASYNC240` | CLI stdout; subprocess in k8s helpers; pathlib in a one-shot async importer. |
| `services/bot/handlers/**` | `ARG001` | aiogram signatures (`message` / `bot` / `state`) are not always used. |

`PLC0415` (import not at top of file) stays **on**. Lazy-import
a heavy module (for example, the DB engine) with a `# noqa: PLC0415` and
a one-line comment. A heavy import in the bot process is worse than a
noqa.

## Not Ruff’s job

Import layers are enforced by tests, not by `banned-api`:

- `tests/test_layer_boundaries.py`
- `tests/test_service_boundaries.py`

Ruff cannot say “`vanessa.core` must not import `vanessa.pipeline`, but
`services/agent` may”. A global ban would break the agent and worker.

## `# noqa`

Use a code (`# noqa: BLE001`), not a bare `# noqa`. One line of why if
it is not obvious.

Allowed when the rule is a known false positive for that line (Telegram
I/O swallow, health probe, lazy heavy import, Langfuse `input=` vs
`A002`).

Not allowed to silence a rule you do not want to follow. Do not start
sprinkling `RUF001` or `PLR0913` again — they are ignored globally on
purpose.

## Related

- Style after a leftover C90 / RET / PTH / FBT / UP: [`.agents/rules/python-clean-code.mdc`](../.agents/rules/python-clean-code.mdc)
- Where a split file goes (capability grouping, not file-count merges): [`.agents/rules/package-layout.mdc`](../.agents/rules/package-layout.mdc)
- Agent skill that only fixes violations, does not change this config: [`.agents/skills/ruff-fix/SKILL.md`](../.agents/skills/ruff-fix/SKILL.md)
- File-length check: [`scripts/check_python_file_length.sh`](../scripts/check_python_file_length.sh)
