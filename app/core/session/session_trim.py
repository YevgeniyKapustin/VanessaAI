from datetime import datetime, timezone

from app.core.messages import ContextMessage


def trim_session_by_idle_gap(
    messages: list[ContextMessage],
    *,
    max_idle_seconds: float,
    now: datetime | None = None,
) -> list[ContextMessage]:
    if not messages or max_idle_seconds <= 0:
        return messages

    current = now or datetime.now(timezone.utc)
    result = [messages[-1]]
    for index in range(len(messages) - 2, -1, -1):
        older = messages[index]
        newer = messages[index + 1]
        if older.created_at is None or newer.created_at is None:
            result.insert(0, older)
            continue
        gap = (newer.created_at - older.created_at).total_seconds()
        if gap > max_idle_seconds:
            break
        result.insert(0, older)
    return result


def seconds_since_last_role(
    messages: list[ContextMessage],
    role: str,
    *,
    now: datetime | None = None,
) -> float | None:
    current = now or datetime.now(timezone.utc)
    for message in reversed(messages):
        if message.role != role or message.created_at is None:
            continue
        return max(0.0, (current - message.created_at).total_seconds())
    return None
