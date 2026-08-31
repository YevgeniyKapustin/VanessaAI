"""Repeated topic loop: same sender, same ask, more than once.

A follow-up is not a loop. The current turn is not compared to itself.
Planner ``repeated_topic`` only counts from loop_level 2 (several empty re-asks).
Annoyance is per-turn — it does not stick across the chat.
"""

from __future__ import annotations

from dataclasses import dataclass

from vanessa.core.messages import ContextMessage
from vanessa.pipeline.decision.repeated_question import (
    message_tokens,
    normalize_content,
)

_MIN_PRIOR_HITS = 2
_PLANNER_MIN_LEVEL = 2
_ANNOYANCE = {0: 0.0, 1: 0.0, 2: 0.7, 3: 1.0}


@dataclass(frozen=True, slots=True)
class LoopSignal:
    loop_strength: int = 0
    annoyance: float = 0.0


def topic_similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    return len(left & right) / len(union)


def _drop_current_turn(
    messages: list[ContextMessage],
    *,
    sender_telegram_id: int,
    text: str,
) -> list[ContextMessage]:
    if not messages:
        return messages
    last = messages[-1]
    if last.role != "user":
        return messages
    if sender_telegram_id and last.sender_telegram_id not in (
        0,
        sender_telegram_id,
    ):
        return messages
    if normalize_content(last.content or "") == normalize_content(text):
        return messages[:-1]
    return messages


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
    current = message_tokens(text)
    priors = _drop_current_turn(
        recent[-window:],
        sender_telegram_id=sender_telegram_id,
        text=text,
    )
    count = 0
    for message in priors:
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
    elif count >= _MIN_PRIOR_HITS:
        det_strength = 2
    else:
        det_strength = 0
    if not planner_repeated or planner_loop_level < _PLANNER_MIN_LEVEL:
        return det_strength
    planner_strength = min(3, max(0, planner_loop_level))
    return max(det_strength, planner_strength)


class LoopRegistry:
    def __init__(self, *, decay_half_life_seconds: float = 3600.0) -> None:
        del decay_half_life_seconds

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
        del decay_half_life_seconds, now
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
        return LoopSignal(
            loop_strength=strength,
            annoyance=_ANNOYANCE.get(strength, 0.0),
        )

    def reset(self) -> None:
        return None


loop_registry = LoopRegistry()
