---
name: ruff-fix
description: >-
  Fixes Ruff lint violations in VanessaAI with the smallest possible
  diff until `poetry run ruff check` is clean on the scoped paths.
  Use when the user asks to fix ruff, lint, flake8, F401, or other
  Ruff codes, or says fix linter, почини ruff, линтер, or ruff ошибки.
  Not a refactor or architecture pass — use clean-refactor for those.
---

# Ruff fix

Make `poetry run ruff check` clean on the scoped paths with the
smallest possible diff. This is **not** a refactor or architecture
pass. Do not "improve" structure unless a remaining rule (C90, RET,
etc.) cannot be fixed without a small extract or guard clause.

Python 3.12. Config lives in `ruff.toml` (`target-version = "py312"`,
`line-length = 88`). Honor that line length, not 100.

For leftover C90 / RET / PTH / FBT / UP style after auto-fix, follow
`.agents/rules/python-clean-code.mdc` on **those functions only**.
Do not copy that rule into this skill.

## Commands

Poetry; ruff is a dev dependency. CI (`.github/workflows/ci.yml`)
runs `ruff check` on `.` — no `ruff format`, no `--unsafe-fixes`.

```bash
poetry run ruff check --fix <paths>
poetry run ruff check <paths>
```

Do **not** pass `--unsafe-fixes` unless the user asked. Do **not**
run `ruff format` unless the user asked.

## Workflow

1. **Scope** — files/dirs the user named, else `git diff` paths, else
   the paths `ruff check` reports. Do not boil the ocean unless asked
   to fix the whole repo.
2. **Auto-fix** — `poetry run ruff check --fix` on that scope first.
3. **Re-run** — `poetry run ruff check <paths>`. List remaining codes.
4. **Hand-fix** — remaining violations with minimal edits. One
   violation cluster at a time. Preserve behavior.
5. **Structure leftovers** — if a leftover is complexity / structure
   (C90, nested RET that needs extract): smallest clean-refactor-style
   change on **those functions only**, following
   `.agents/rules/python-clean-code.mdc`. No SOLID tour.
6. **Verify** — `poetry run ruff check` clean on scope. If a hand-fix
   could change behavior, run existing tests for the touched files.
7. **Chat** — short list of codes fixed, leftovers if any, commands
   run. No file dumps.

## Hard constraints

- Preserve behavior, public APIs, exception messages, I/O, log text
- No drive-by refactors, no new deps, no rewriting files from scratch
- Don't disable ruff rules (`# noqa`) unless the user asked or the
  violation is a false positive you can justify in one line
- Don't change tests to silence ruff
- Don't invent architecture to satisfy C90; extract or flatten only
  as far as the rule requires

## Chat output

```markdown
## Fixed
- CODE: where / how (one line)

## Leftover
- CODE: why it remains (or "none")

## Commands
- `poetry run ruff check --fix …` → result
- `poetry run ruff check …` → result
```
