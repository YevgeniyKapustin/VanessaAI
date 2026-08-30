"""RepeatedTopicLoop: detect a sender re-asking the SAME topic in a loop and
track Vanessa's rising annoyance.

The deterministic layer compares content tokens of the current message against
the same sender's own recent user messages (Jaccard overlap) — a cheap floor
that catches the same topic re-asked with moderate rewording. The LLM planner
adds the semantic layer via ``repeated_topic`` / ``loop_level``, which catches
fully rephrased loops the token overlap would miss.

``LoopRegistry`` keeps per-sender in-memory annoyance state (resets on restart):
annoyance rises sharply on each detected loop repeat, decays with time and is
hard-reset when the sender moves to a different topic. High annoyance feeds the
``LowAttitudeRule`` (maximal ignore tendency for weak messages) and the compose
annoyance note (cold replies).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from vanessa.core.messages import ContextMessage
from vanessa.decision.repeated_question import message_tokens


@dataclass(frozen=True, slots=True)
class LoopSignal:
    """Per-turn loop verdict: how deep the loop is and how annoyed Vanessa is."""

    loop_strength: int = 0  # 0..3
    annoyance: float = 0.0  # 0..1


def topic_similarity(left: set[str], right: set[str]) -> float:
    """Jaccard overlap of two token sets: 1.0 identical, 0.0 disjoint."""
    if not left or not right:
        return 0.0
    union = left | right
    return len(left & right) / len(union)


def detect_loop_strength(
    text: str,
    recent: list[ContextMessage],
    *,
    sender_telegram_id: int,
    window: int = 10,
    similarity_threshold: float = 0.4,
    planner_repeated: bool = False,
    planner_loop_level: int = 0,
) -> int:
    """Combined loop strength (0..3) from the deterministic overlap + planner.

    The deterministic tier counts how many of the sender's own recent user
    messages overlap the current topic above ``similarity_threshold``: the first
    re-ask → 1, several → 2, a constant loop → 3. The planner signal is capped
    at 3 and only counts when ``planner_repeated`` is true.
    """
    current = message_tokens(text)
    count = 0
    for message in recent[-window:]:
        if message.role != "user":
            continue
        if sender_telegram_id and message.sender_telegram_id not in (
            0,
            sender_telegram_id,
        ):
            continue
        prior = message_tokens(message.content or "")
        if topic_similarity(current, prior) >= similarity_threshold:
            count += 1
    if count >= 4:
        det_strength = 3
    elif count >= 2:
        det_strength = 2
    elif count >= 1:
        det_strength = 1
    else:
        det_strength = 0
    planner_strength = min(3, max(0, planner_loop_level)) if planner_repeated else 0
    return max(det_strength, planner_strength)


# How much each loop level adds to Vanessa's annoyance on one turn.
_ANNOYANCE_STEP = {1: 0.2, 2: 0.35, 3: 0.5}


@dataclass
class _LoopState:
    annoyance: float = 0.0
    last_tokens: frozenset[str] = frozenset()
    updated: float = 0.0


class LoopRegistry:
    """Per-sender in-memory annoyance state (resets on restart).

    Thread-safe; one shared instance is used by the gate so every turn of a
    sender accumulates into the same state. ``update`` both reads and writes
    the sender's annoyance and returns the loop signal for this turn.
    """

    def __init__(self, *, decay_half_life_seconds: float = 3600.0) -> None:
        self._lock = threading.Lock()
        self._half_life = max(60.0, decay_half_life_seconds)
        self._state: dict[int, _LoopState] = {}

    def update(
        self,
        sender_telegram_id: int,
        text: str,
        recent: list[ContextMessage],
        *,
        planner_repeated: bool = False,
        planner_loop_level: int = 0,
        window: int = 10,
        similarity_threshold: float = 0.4,
        decay_half_life_seconds: float | None = None,
        now: float | None = None,
    ) -> LoopSignal:
        if not sender_telegram_id:
            return LoopSignal()
        strength = detect_loop_strength(
            text,
            recent,
            sender_telegram_id=sender_telegram_id,
            window=window,
            similarity_threshold=similarity_threshold,
            planner_repeated=planner_repeated,
            planner_loop_level=planner_loop_level,
        )
        now = now if now is not None else time.monotonic()
        half_life = (
            decay_half_life_seconds
            if decay_half_life_seconds is not None
            else self._half_life
        )
        current_tokens = frozenset(message_tokens(text))
        with self._lock:
            state = self._state.get(sender_telegram_id)
            if state is None:
                state = _LoopState()
                self._state[sender_telegram_id] = state
            if state.updated > 0:
                dt = max(0.0, now - state.updated)
                state.annoyance *= 0.5 ** (dt / half_life)
            if strength > 0:
                # The same topic keeps coming back — irritation rises sharply.
                state.annoyance = min(1.0, state.annoyance + _ANNOYANCE_STEP[strength])
            elif state.last_tokens and current_tokens:
                # The sender moved to a different topic: Vanessa's irritation
                # about the old loop resets (annoyance already decayed with time).
                if (
                    topic_similarity(current_tokens, state.last_tokens)
                    < similarity_threshold
                ):
                    state.annoyance = 0.0
            state.last_tokens = current_tokens
            state.updated = now
            return LoopSignal(loop_strength=strength, annoyance=state.annoyance)

    def reset(self) -> None:
        with self._lock:
            self._state.clear()


# Shared singleton used by the pipeline (built once per process).
loop_registry = LoopRegistry()
