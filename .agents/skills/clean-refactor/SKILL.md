---
name: clean-refactor
description: >-
  Refactors existing code in place to improve readability, structure,
  and maintainability without changing external behavior. Use when
  the user asks to refactor, clean up, apply SOLID, DRY, KISS,
  reduce complexity, or improve maintainability — including Russian
  requests: рефакторинг, почисти код, приведи в порядок, упростить,
  без смены поведения. Also use when converting class vs function,
  extracting a Protocol, fixing hidden DI or god objects,
  staticmethod-only wrappers, or questions about Factory / Unit of
  Work / anemic vs rich models (класс или функция, протокол, DI).
---

# Clean refactor

Surgical, behavior-preserving edits in VanessaAI. Chat is a short
report. The deliverable is the file diffs — not a rewritten dump,
not a design-pattern showcase.

This repo is Python 3.12. Follow `.agents/rules/python-clean-code.mdc`
for RET, PTH, FBT, C90, UP, YAGNI, functions vs classes, and public
signatures. Follow `.agents/rules/package-layout.mdc` for where
extracts live: keep them in the same capability; do not invent CRUD
feature folders or `domain/use_cases/adapters`, and do not merge files
to shrink folder file-count. Use [reference.md](reference.md) for
extract-vs-not, class↔function, and behavior traps.

## Mission

Improve structure and readability **without** changing external
behavior. Frozen unless the user explicitly asked otherwise:

- public APIs, exported names, signatures, types
- return values; exception types and messages
- I/O, CLI flags, HTTP routes, event names
- log side-effects and error-message text
- business contracts

If a change would alter behavior: **stop that change**. Ask or skip.
Do not fix bugs or add features during a refactor pass unless asked.

A **design-pass** (class vs function, DI, Protocol, god object) is
in-bounds only when the user asked for it. Still preserve behavior.
Structural splits that keep the same results are OK. Do not rewrite
working functions into classes “for OOP”. Do not add Unit of Work,
DDD entities, or a Factory per DTO.

## Scope before any edit

1. Name the exact files and symbols in scope. No drive-by refactors.
2. Capture the public contract first (signatures, types, exported
   names, CLI flags, HTTP routes, event names).
3. Prefer existing tests for that area **before** and after editing.
   No tests → keep the refactor smaller and obviously
   behavior-preserving. Do not invent architecture to "make it
   testable" unless asked.

## Workflow

1. **Audit** — read the target code, neighboring tests, and linter
   config (`ruff.toml`).
2. **Overview** — bullets of *real* issues only. Skip theoretical
   nits and SOLID lectures with no payoff in this code.
3. **Refactor** — edit files in place, one concern at a time.
   Prefer extract / inline / guard-clause moves over rewriting a
   working function from memory.
4. **Verify** — project linter, typecheck, and tests for touched
   files. If verification fails, fix the *refactor*. Do not change
   assertions or production behavior to make tests pass.
5. **Rationale** — name only techniques actually used (e.g. Guard
   Clause, Extract Method). Skip unused pattern namedropping.
   Replace Conditional with Polymorphism only when there is real
   type/variant branching already in the code — then a Protocol,
   not a Strategy class tree.

## Language routing

Detect language from the files being refactored.

**Python:** follow `.agents/rules/python-clean-code.mdc` and
`.agents/rules/package-layout.mdc`. Use [reference.md](reference.md)
for extract-vs-not, class↔function, and behavior traps.

**YAML, shell, and other non-Python files in this repo:** same
refactor workflow and extract-vs-not rule. Use that file's idioms
and the project's linter. Do **not** cite pathlib or Ruff codes
on them.

## Extract vs not

Extract when nested `if`/`try` hides the happy path, the same 8+
lines appear in two+ places in scope, a named helper drops C901
under 4 without a kwargs trampoline, **or** a function is a wall of
constructor kwargs for 1+ fat DTOs already in the codebase → named
`build_*` helper (function, not Factory class). Do **not** invent an
ABC/Protocol/Factory for two branches, split across a transaction,
lock, or I/O boundary, or "clean up" with `Foo(**bar.model_dump())`,
`**kwargs` forwarding, or a new Parameter Object. Pass the existing
object; do not unpack and rebuild.

## Design shape

If the **named scope** already has these shapes, apply
`.agents/rules/python-clean-code.mdc`. Convert `@staticmethod`-only
classes to module functions when the name is not a public contract
(or keep an alias). Pass hidden clients as arguments at composition
roots. Split a god module along capability lines. Do **not** turn a
Pydantic DTO, contract, or gate result into a rich entity. Convert
functions → class only when you found real mutable state or a DI
boundary that was faking it with globals.

Do not roam the tree hunting OOP nits unless the user asked for a
design-pass. Details: [reference.md](reference.md).

## Hard anti-patterns

- Drive-by edits outside the named scope
- Renaming public APIs
- Whole-file reformat or unrelated style churn
- Rewriting working code from scratch
- Adding dependencies
- Speculative performance tweaks
- Fixing bugs or adding features during the refactor pass
- Changing tests or assertions to make a refactor "pass"
- Uniform OOP / method-chaining across a functional pipeline
- New `domain/`, Unit of Work, or Factory-per-DTO
- `Foo(**bar.model_dump())` / `**kwargs` trampolines, or a new
  Parameter Object to shorten signatures

## Chat output

Keep short. Do **not** paste a rewritten file unless the user asked
for a snippet.

```markdown
## Overview
- real issue …

## Changes
- `path`: what changed (not a code dump)

## Rationale
- technique → why it preserves behavior and helps maintenance

## Left on purpose
- what looked like a violation but is a DI boundary / data DTO / real invariant

## Verification
- command and result
```
