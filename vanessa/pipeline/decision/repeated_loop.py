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
_HIGH_STRENGTH_HITS = 4
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


def _is_current_turn(
    last: ContextMessage,
    *,
    sender_telegram_id: int,
    text: str,
) -> bool:
    if last.role != "user":
        return False
    if sender_telegram_id and last.sender_telegram_id not in (
        0,
        sender_telegram_id,
    ):
        return False
    return normalize_content(last.content or "") == normalize_content(text)


def _drop_current_turn(
    messages: list[ContextMessage],
    *,
    sender_telegram_id: int,
    text: str,
) -> list[ContextMessage]:
    if not messages:
        return messages
    last = messages[-1]
    if _is_current_turn(last, sender_telegram_id=sender_telegram_id, text=text):
        return messages[:-1]
    return messages


def _same_sender(message: ContextMessage, sender_telegram_id: int) -> bool:
    if not sender_telegram_id:
        return True
    return message.sender_telegram_id in (0, sender_telegram_id)


def _is_similar_prior(
    message: ContextMessage,
    current: set[str],
    *,
    sender_telegram_id: int,
    similarity_threshold: float,
) -> bool:
    if message.role != "user":
        return False
    if not _same_sender(message, sender_telegram_id):
        return False
    prior = message_tokens(message.content or "")
    return topic_similarity(current, prior) >= similarity_threshold


def _prior_hit_count(
    priors: list[ContextMessage],
    current: set[str],
    *,
    sender_telegram_id: int,
    similarity_threshold: float,
) -> int:
    count = 0
    for message in priors:
        if _is_similar_prior(
            message,
            current,
            sender_telegram_id=sender_telegram_id,
            similarity_threshold=similarity_threshold,
        ):
            count += 1
    return count


def _strength_from_count(count: int) -> int:
    if count >= _HIGH_STRENGTH_HITS:
        return 3
    if count >= _MIN_PRIOR_HITS:
        return 2
    return 0


def _merge_planner_strength(
    det_strength: int,
    *,
    planner_repeated: bool,
    planner_loop_level: int,
) -> int:
    if not planner_repeated:
        return det_strength
    if planner_loop_level < _PLANNER_MIN_LEVEL:
        return det_strength
    planner_strength = min(3, max(0, planner_loop_level))
    return max(det_strength, planner_strength)


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
    count = _prior_hit_count(
        priors,
        current,
        sender_telegram_id=sender_telegram_id,
        similarity_threshold=similarity_threshold,
    )
    det_strength = _strength_from_count(count)
    return _merge_planner_strength(
        det_strength,
        planner_repeated=planner_repeated,
        planner_loop_level=planner_loop_level,
    )


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
