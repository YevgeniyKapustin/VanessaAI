# Plan: cut empty / meaningless phrases when the user expects no reply

## Symptom

```
[8/27/2026 16:16] Yevgeniy: чего и следовало ожидать
[8/27/2026 16:16] Vanessa in reply to Yevgeniy:
  Ну да, я же говорила — физика не врёт
```

"чего и следовало ожидать" is a dry, empty comment — no question, no request,
no address to the bot, no expectation of an answer. The bot replied anyway.

Goal: change the prompts so such empty/no-meaning phrases are classified as
should_reply=false / respond=false when the user isn't expecting a reply.

## Why it currently slips through

Decision path for the example message (4 words, 24 chars):

1. Deterministic prefilter (`ReplyEligibility.hard_ignore`, see
   [`app/decision/gate/reply_eligibility.py`](../app/decision/gate/reply_eligibility.py:106)):
   - not caught by the noise filter (`noise_max_words=1`, `noise_max_chars=12` in
     [`config/content/decision.yaml`](../config/content/decision.yaml:2) — message is longer);
   - no closure / dismissal / unsolicited-remark / third-party-about-bot pattern
     in [`app/decision/gate/reply_expectation.py`](../app/decision/gate/reply_expectation.py:5);
   - → `run_planner=True`.
2. Reaction gate ([`app/decision/gate/reaction_gate.py`](../app/decision/gate/reaction_gate.py:211)):
   - Tier 1 deterministic finds no question/trigger/modal/address signal and the
     message is too long for the noise short-circuit → ambiguous;
   - **but** inside the post-reply listen window the gate is bypassed entirely
     (`decision_reaction_gate_bypass_listen_window=True`,
     [`app/config/settings.py`](../app/config/settings.py:137)) → `respond=True` without any gate call.
3. LLM planner ([`config/content/rag.yaml`](../config/content/rag.yaml:2) `turn_planner_prompt`):
   - the `should_reply` rules only name "side conversation, thinking out loud,
     goodbye, «ок»..." as false;
   - the listen-window clarification says "reply to a question, a follow-up, or a
     comment continuing the dialogue... stay silent only for clear side talk,
     third-person gossip («она...»), or a goodbye" — a substantive-looking dry
     comment is treated as a continuation → `should_reply=true`.

So the bot replies because the prompts give no rule for "empty phrase that
expects no answer".

## Fix (prompt-level, primary)

### 1. Planner prompt — [`config/content/rag.yaml`](../config/content/rag.yaml:2) `turn_planner_prompt`

- `## should_reply` → `false` branch: add
  "an empty/meaningless phrase that asks nothing and expects no reply — a dry
  remark, a rhetorical acknowledgment, filler («чего и следовало ожидать»,
  «ну вот», «так и знал», «ага», «ну да») → should_reply=false, skip=true".
- `## should_reply` → listen-window clarification: add "stay silent also for
  empty/no-meaning phrases that add no substance and expect no answer
  («чего и следовало ожидать», «ну вот», «так и знал») — they do not continue
  the dialogue".
- `## Examples`: add an input → JSON example
  «чего и следовало ожидать» → should_reply=false, skip=true.

This is the critical fix because the listen-window path bypasses the reaction
gate and only the planner decides.

### 2. Reaction gate prompt — [`config/content/decision.yaml`](../config/content/decision.yaml:60) `reaction_gate_prompt`

- `NO` branch: add "an empty/meaningless phrase that asks nothing and expects no
  reply — a dry comment, an acknowledgment without substance («чего и следовало
  ожидать», «ну вот», «ага»)".
This catches the non-bypass path (no listen window, no reply-to-bot) at Tier 2.

## Optional deterministic guard (needs confirmation)

Even with the prompt fixes, the planner is an LLM — it may still occasionally
reply to a dry phrase (and costs tokens). A zero-cost deterministic guard would
make it strict:

- Add `empty_phrases` list to [`config/content/decision.yaml`](../config/content/decision.yaml:1)
  (meaningless filler: "чего и следовало ожидать", "ну вот", "так и знал", "ага",
  "ну да", "ок", "понятно", ...).
- Check it in `ReplyEligibility.hard_ignore` / prefilter (alongside `noise`)
  → `DecisionReason.PREFILTER`, and/or in `ReactionGate._fast_verdict` Tier 1
  → `respond=False` (instant short-circuit, zero LLM).
- This also fixes the listen-window bypass without relying on the LLM.

## Tests

- `tests/llm/test_turn_planner.py` / `test_content.py`: assert the planner prompt
  contains the new empty-phrase rule and the example (content-level check).
- `tests/decision/test_reaction_gate.py`: a scripted Tier-2 response of "NO" for
  an empty phrase → `respond=False`; if the deterministic guard is added, assert
  an empty phrase short-circuits at Tier 1 with zero LLM calls.
- If the deterministic guard is added: `tests/decision/test_prefilter.py` and
  `tests/decision/test_reply_eligibility.py` — empty phrase → `run_planner=False`.

## Files to change

- [`config/content/rag.yaml`](../config/content/rag.yaml) — planner prompt (should_reply rules, listen-window clarification, example).
- [`config/content/decision.yaml`](../config/content/decision.yaml) — reaction gate prompt; optionally `empty_phrases`.
- Optional: [`app/decision/gate/reply_eligibility.py`](../app/decision/gate/reply_eligibility.py) and/or [`app/decision/gate/reaction_gate.py`](../app/decision/gate/reaction_gate.py) for the deterministic guard.
- Tests as above.

## Implementation status

Done (in Code mode, "prompt changes only" scope):

- [`config/content/rag.yaml`](../config/content/rag.yaml) `turn_planner_prompt`:
  - `## should_reply` false branch now lists "an empty/meaningless phrase that
    asks nothing and expects no reply" with examples («чего и следовало
    ожидать», «ну вот», «так и знал», «ага», «ну да») → should_reply=false,
    skip=true;
  - the listen-window clarification now says to stay silent also for an
    empty/no-meaning phrase that adds no substance and expects no answer;
  - a new example «чего и следовало ожидать» → should_reply=false, skip=true.
- [`config/content/decision.yaml`](../config/content/decision.yaml) `reaction_gate_prompt`:
  - the `NO` branch now includes "an empty/meaningless phrase that asks nothing
    and expects no reply" with examples.
- `tests/llm/test_content.py` — two content-level tests asserting both prompts
  contain the new empty-phrase rule and example.

Follow-up: bare agreements/acknowledgments («это правда», «верно», «именно»,
«точно», «согласен») are also covered — added to the planner `should_reply`
false rules, the listen-window note, the planner example («это правда»), the
reaction-gate NO branch, and the content-level tests.

Note: in a YAML literal block (`|`) a wrapped line keeps the newline, so the
example phrase must stay on one line inside the block (otherwise a substring
assert fails).

Result: `tests/llm/test_content.py`, `tests/llm/test_turn_planner.py`,
`tests/decision/test_reaction_gate.py`, full `tests/decision` — 229 passed.
