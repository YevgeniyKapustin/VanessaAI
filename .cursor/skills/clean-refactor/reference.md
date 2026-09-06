# Refactor notes

Extract-vs-not, class↔function, and behavior traps. Python style
lives in `.cursor/rules/python-clean-code.mdc`. Layout:
`.cursor/rules/package-layout.mdc`.

## Extract vs not

Extract when nested `if`/`try` hides the happy path, the same 8+ lines
appear in two+ places in scope, or a named helper drops C901 under 4
without turning the caller into a kwargs trampoline.

Extract a wall of constructor keyword arguments for existing fat DTOs
(`ChatTurnInput`, `OrchestratorConfig`, `DecisionContext`) into
`build_turn_input()` / `build_orchestrator_config()`. Fat signatures
are OK. Nested composition is OK when the object has real parts
(`llm: LLMGenerationParams`). A composition-root `build_*` may be a
bit long; stage functions must not be.

Do **not** extract when you would invent an ABC/Protocol/Factory for
two branches, or the split crosses a transaction, lock, or I/O
boundary. Do not "fix" wallpaper with `Foo(**bar.model_dump())`,
`**kwargs` forwarding, or a new Parameter Object. Do not enable
PLR0913.

Do not add a new bool that forks a large function; that is a
behavior/API change, not a refactor.

## Class vs function

Default is functions. A class is justified when **either** is true:

- mutable internal state or lifecycle invariants
- composition/DI boundary: broker, repository, store, retriever,
  completer, engine, session

**Class → functions** when the type is only `@staticmethod` /
`@classmethod`, has no instance state, and is not a wired service.
Keep the exported name if it is a public contract; otherwise rename
to a verb module function.

**Functions → class** only when you found real state or a hidden
global that belongs at a composition root. Do not wrap a stage,
handler, formatter, parser, or gate rule “for OOP”.

**Protocol** in `vanessa.core` (or the capability) when two+
interchangeable implementations already exist or are being added.
Do not add a Protocol for a single `if`/`elif`.

**Factory** only when `__init__` / construction is multi-step,
env-conditional, or messy. Not for every DTO. Prefer a plain
function `build_…()`, not a Factory/Builder class.

**Do not introduce**

- Unit of Work on top of the existing repository
- DDD `domain/` / entities / use_cases / adapters
- rich methods on contracts, messages, settings, or gate results
- inheritance trees or method-chaining as a house style

Anemic data is correct here. Behavior lives in stage functions.
Rich behavior belongs on session, outbox, stores, brokers.

## Where extracts go

Keep a new helper in the same capability as the caller
(`.cursor/rules/package-layout.mdc`). Split a file that exceeds 150–200
lines; do not merge siblings to cut file count. Do not add
`domain/use_cases/adapters` or a new top-level package for a local extract.

## Behavior traps

Do not "fix" these during a refactor unless asked — they can change
behavior:

- mutable defaults
- `==` vs `is`
- float compares
- decorator order and wrapping
- I/O, logging, or cache write order
- exception type, message, and raise-vs-return
