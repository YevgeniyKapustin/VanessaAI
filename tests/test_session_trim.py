from datetime import datetime, timedelta, timezone

from app.core.messages import ContextMessage
from app.core.session_trim import (
    seconds_since_last_role,
    trim_session_by_idle_gap,
)


def test_trim_session_keeps_contiguous_block():
    base = datetime(2026, 7, 4, 10, 0, tzinfo=timezone.utc)
    messages = [
        ContextMessage(id=1, role="user", content="old", created_at=base),
        ContextMessage(
            id=2,
            role="assistant",
            content="reply",
            created_at=base + timedelta(minutes=1),
        ),
        ContextMessage(
            id=3,
            role="user",
            content="new",
            created_at=base + timedelta(minutes=2),
        ),
    ]

    trimmed = trim_session_by_idle_gap(messages, max_idle_seconds=300)

    assert len(trimmed) == 3


def test_trim_session_drops_messages_after_idle_gap():
    base = datetime(2026, 7, 4, 10, 0, tzinfo=timezone.utc)
    messages = [
        ContextMessage(id=1, role="user", content="old", created_at=base),
        ContextMessage(
            id=2,
            role="assistant",
            content="reply",
            created_at=base + timedelta(minutes=10),
        ),
        ContextMessage(
            id=3,
            role="user",
            content="new",
            created_at=base + timedelta(minutes=11),
        ),
    ]

    trimmed = trim_session_by_idle_gap(messages, max_idle_seconds=300)

    assert len(trimmed) == 2
    assert trimmed[0].content == "reply"


def test_seconds_since_last_bot():
    now = datetime(2026, 7, 4, 10, 10, tzinfo=timezone.utc)
    messages = [
        ContextMessage(
            id=1,
            role="assistant",
            content="reply",
            created_at=now - timedelta(minutes=2),
        ),
        ContextMessage(
            id=2,
            role="user",
            content="follow",
            created_at=now - timedelta(minutes=1),
        ),
    ]

    assert seconds_since_last_role(messages, "assistant", now=now) == 120.0
