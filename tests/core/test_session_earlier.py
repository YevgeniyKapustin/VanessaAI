"""The tail of the thread before the idle gap stays in the prompt context."""

from datetime import UTC, datetime, timedelta

from vanessa.core.messages import ContextMessage
from vanessa.core.session.chat_session_state import (
    EarlierWindow,
    build_chat_session_state,
)
from vanessa.core.session.session_trim import earlier_tail

_BASE = datetime(2026, 10, 24, 0, 54, tzinfo=UTC)


def _msg(msg_id: int, role: str, content: str, minutes: float) -> ContextMessage:
    return ContextMessage(
        id=msg_id,
        role=role,
        content=content,
        created_at=_BASE + timedelta(minutes=minutes),
    )


def _chat() -> list[ContextMessage]:
    # The promise at 00:54, then a 28-minute pause, then the reminder.
    return [
        _msg(1, "user", "старое", -200),
        _msg(2, "user", "ванесса что я делал сегодня", 0),
        _msg(3, "assistant", "Ща гляну… скину списком", 0.1),
        _msg(4, "user", "ну и где", 28),
        _msg(5, "assistant", "Тут я. Чего надо?", 28.2),
        _msg(6, "user", "ты обещала мне список", 29),
    ]


def test_earlier_tail_keeps_recent_dropped_messages() -> None:
    messages = _chat()
    tail = earlier_tail(messages, messages[3:], count=6, max_age_seconds=10800)
    assert [m.id for m in tail] == [2, 3]


def test_earlier_tail_respects_count() -> None:
    messages = _chat()
    tail = earlier_tail(messages, messages[3:], count=1, max_age_seconds=10800)
    assert [m.id for m in tail] == [3]


def test_earlier_tail_empty_when_off_or_nothing_dropped() -> None:
    messages = _chat()
    assert earlier_tail(messages, messages[3:], count=0, max_age_seconds=60) == []
    assert earlier_tail(messages, messages[3:], count=5, max_age_seconds=0) == []
    assert earlier_tail(messages, messages, count=5, max_age_seconds=60) == []
    assert earlier_tail(messages, [], count=5, max_age_seconds=60) == []


def test_earlier_tail_skips_messages_without_time() -> None:
    messages = [ContextMessage(id=1, role="user", content="x"), *_chat()[3:]]
    assert earlier_tail(messages, messages[1:], count=5, max_age_seconds=60) == []


def test_session_state_keeps_promise_before_pause() -> None:
    state = build_chat_session_state(
        _chat(),
        max_idle_seconds=300,
        listen_max_messages=3,
        earlier=EarlierWindow(count=6, max_age_seconds=10800),
    )
    assert [m.id for m in state.messages] == [4, 5, 6]
    assert [m.id for m in state.earlier_messages] == [2, 3]
    assert [m.id for m in state.prompt_messages] == [2, 3, 4, 5, 6]


def test_session_state_without_earlier_window() -> None:
    state = build_chat_session_state(
        _chat(), max_idle_seconds=300, listen_max_messages=3
    )
    assert state.earlier_messages == []
    assert state.prompt_messages == state.messages
