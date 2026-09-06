from datetime import UTC, datetime

from vanessa.core.messages import ContextMessage


def _idle_gap_exceeded(
    older: ContextMessage,
    newer: ContextMessage,
    max_idle_seconds: float,
) -> bool:
    if older.created_at is None or newer.created_at is None:
        return False
    gap = (newer.created_at - older.created_at).total_seconds()
    return gap > max_idle_seconds


def _trim_from_newest(
    messages: list[ContextMessage],
    max_idle_seconds: float,
) -> list[ContextMessage]:
    result = [messages[-1]]
    for index in range(len(messages) - 2, -1, -1):
        older = messages[index]
        newer = messages[index + 1]
        if _idle_gap_exceeded(older, newer, max_idle_seconds):
            break
        result.insert(0, older)
    return result


def trim_session_by_idle_gap(
    messages: list[ContextMessage],
    *,
    max_idle_seconds: float,
    now: datetime | None = None,
) -> list[ContextMessage]:
    del now
    if not messages or max_idle_seconds <= 0:
        return messages
    return _trim_from_newest(messages, max_idle_seconds)


def seconds_since_last_role(
    messages: list[ContextMessage],
    role: str,
    *,
    now: datetime | None = None,
) -> float | None:
    current = now or datetime.now(UTC)
    for message in reversed(messages):
        if message.role != role or message.created_at is None:
            continue
        return max(0.0, (current - message.created_at).total_seconds())
    return None
